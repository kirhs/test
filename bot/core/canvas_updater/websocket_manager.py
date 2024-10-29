from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Self
from uuid import uuid4

import aiohttp
from attr import define, field
import jwt
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType

from bot.core.canvas_updater.exceptions import (
    CentrifugeError,
    SessionErrors,
    TokenError,
    WebSocketErrors,
)
from bot.utils.logger import logger


@define
class SessionData:
    """Represents a WebSocket session with its associated data."""

    id: str = field()
    notpx_headers: Dict[str, str] = field()
    websocket_headers: Dict[str, str] = field()
    image_notpx_headers: Dict[str, str] = field()
    aiohttp_session: ClientSession = field()
    websocket_token: Optional[str] = field(default=None)
    proxy_connector: Optional[str] = field(default=None)
    active: bool = field(default=False)

    @classmethod
    def create(
        cls,
        notpx_headers: Dict[str, str],
        websocket_headers: Dict[str, str],
        image_notpx_headers: Dict[str, str],
        aiohttp_session: ClientSession,
        websocket_token: Optional[str] = None,
        proxy_connector: Optional[str] = None,
    ) -> SessionData:
        """Factory method to create a new session."""
        return cls(
            id=uuid4().hex,
            notpx_headers=notpx_headers,
            websocket_headers=websocket_headers,
            image_notpx_headers=image_notpx_headers,
            aiohttp_session=aiohttp_session,
            websocket_token=websocket_token,
            proxy_connector=proxy_connector,
        )


class WebSocketManager:
    """Manages WebSocket connections and sessions."""

    REFRESH_TOKEN_IF_NEEDED_INTERVAL = 60  # seconds
    MAX_RECONNECT_ATTEMPTS = 3  # after initial attempt
    RECONNECT_DELAY = 5  # seconds

    _instance = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        

    def __init__(
        self, token_endpoint: str, websocket_url: str, canvas_endpoint: str
    ) -> None:
        self.token_endpoint = token_endpoint
        self.websocket_url = websocket_url
        self.canvas_endpoint = canvas_endpoint
        self.sessions: List[SessionData] = []
        self.active_session: Optional[SessionData] = None
        self.websocket: Optional[ClientWebSocketResponse] = None
        self.websocket_token: Optional[str] = None
        self.image_notpx: Optional[bytes] = None
        self._lock = asyncio.Lock()
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None

    async def add_session(
        self,
        notpx_headers: Dict[str, str],
        websocket_headers: Dict[str, str],
        image_notpx_headers: Dict[str, str],
        aiohttp_session: ClientSession,
        websocket_token: Optional[str] = None,
        raw_proxy: Optional[str] = None,
    ) -> None:
        """Add a new session to the manager."""
        async with self._lock:
            self._validate_session_params(
                notpx_headers, websocket_headers, image_notpx_headers, aiohttp_session
            )

            session = SessionData.create(
                notpx_headers=notpx_headers,
                websocket_headers=websocket_headers,
                image_notpx_headers=image_notpx_headers,
                aiohttp_session=aiohttp_session,
                websocket_token=websocket_token,
                proxy_connector=raw_proxy,
            )

            self.sessions.append(session)

            if not self.active_session:
                await self._activate_session(session)

    @staticmethod
    def _validate_session_params(
        notpx_headers: Dict[str, str],
        websocket_headers: Dict[str, str],
        image_notpx_headers: Dict[str, str],
        aiohttp_session: ClientSession,
    ) -> None:
        """Validate session parameters."""
        if not all(
            [notpx_headers, websocket_headers, image_notpx_headers, aiohttp_session]
        ):
            raise ValueError("Missing required session parameters")

    async def _activate_session(self, session: SessionData) -> None:
        """Activate a session and initialize the connection."""
        if self.active_session:
            self.active_session.active = False
        self.active_session = session
        session.active = True
        self._running = True
        await self._initialize_connection()

    async def _switch_to_next_session(self) -> None:
        """Switch to the next available session in the list."""
        if not self.sessions:
            raise SessionErrors.NoAvailableSessionsError("Can not switch to next session, no sessions available")

        current_index = (
            next(
                (
                    i
                    for i, s in enumerate(self.sessions)
                    if s.id == self.active_session.id
                ),
                -1,
            )
            if self.active_session
            else -1
        )

        next_index = (current_index + 1) % len(self.sessions)

        if next_index == current_index:
            raise SessionErrors.NoAvailableSessionsError("No available sessions")

        next_session = self.sessions[next_index]

        logger.info(
            f"WebSocketManager | Switching from session {self.sessions[current_index].id} to session {next_session.id}"
        )
        await self._activate_session(next_session)

    async def _initialize_connection(self) -> None:
        """Initialize the WebSocket connection."""
        try:
            if not self.websocket_token:
                self.websocket_token = await self._get_token()
            await self._get_image()
            await self._connect_websocket()

            if not self._refresh_task or self._refresh_task.done():
                self._refresh_task = asyncio.create_task(self._token_refresh_loop())
        except WebSocketErrors.ConnectionError as error:
            logger.error(f"WebSocketManager | {error}")
            await self._switch_to_next_session()
        except Exception:
            await self.stop()
            raise Exception("Failed to initialize connection")

    async def _get_image(self) -> None:
        """Get the image from the server."""
        if not self.active_session:
            raise ValueError("No active session available")
        pass

    async def _get_token(self, attempts: int = 1) -> str:
        """Get a new WebSocket token."""
        if not self.active_session:
            raise SessionErrors.NoActiveSessionError("No active session available")

        try:
            async with self.active_session.aiohttp_session.get(
                "https://notpx.app/api/v1/users/me",
                headers=self.active_session.notpx_headers,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data["websocketToken"]
        except Exception:
            if attempts <= self.MAX_RECONNECT_ATTEMPTS:
                logger.warning(
                    f"WebSocketManager | Token retrieval attempt {attempts} failed, retrying in {self.RECONNECT_DELAY}s"
                )
                await asyncio.sleep(self.RECONNECT_DELAY)
                return await self._get_token(attempts + 1)
            raise TokenError("Failed to get token")

    async def _connect_websocket(self, attempts: int = 1) -> None:
        """Establish WebSocket connection."""
        if not self.active_session:
            raise SessionErrors.NoActiveSessionError("No active session available")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    self.websocket_url,
                    headers=self.active_session.websocket_headers,
                    proxy=self.active_session.proxy_connector,
                    protocols=["centrifuge-protobuf"],
                    autoping=False,
                ) as websocket:
                    self.websocket = websocket
                    await self._handle_websocket_connection()
        except Exception as error:
            await self._handle_websocket_connection_error(error, attempts)

    async def _reconnect_websocket(self) -> None:
        """Reconnect to the WebSocket server."""
        if self.websocket is not None:
            await self.websocket.close()
        self.websocket = None
        await self._connect_websocket()

    async def _handle_websocket_connection(self) -> None:
        """Handle the WebSocket connection and message processing."""
        if self.websocket is None:
            raise WebSocketErrors.NoConnectionError(
                "WebSocket connection not established"
            )

        auth_data = await self._authenticate_websocket()
        await self.websocket.send_bytes(base64.b64decode(auth_data))

        while True:
            try:
                message = await self.websocket.receive()
                if message.type == WSMsgType.CLOSE:
                    raise WebSocketErrors.ServerClosedConnectionError(
                        "WebSocket server closed connection"
                    )
                await self._decode_websocket_message(message.data)
            except Exception:
                raise WebSocketErrors.ConnectionError("WebSocket connection failed")

    async def _decode_websocket_message(self, message_data: bytes) -> None:
        """Decode a WebSocket message."""
        decoded_message = await asyncio.create_subprocess_exec(
            "node",
            "bot/core/canvas_updater/centrifuge.js",
            base64.b64encode(message_data).decode(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await decoded_message.communicate()

        if stderr:
            raise CentrifugeError(
                "Error while decoding websocket message"
            )

        if stdout:
            await self._handle_websocket_message(stdout.decode().strip())

    async def _authenticate_websocket(self) -> bytes:
        """Authenticate the WebSocket connection."""
        auth_command = json.dumps(
            [{"connect": {"token": self.websocket_token, "name": "js"}, "id": 1}]
        )

        process = await asyncio.create_subprocess_exec(
            "node",
            "bot/core/canvas_updater/centrifuge.js",
            f"command:{auth_command}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        if stderr:
            raise WebSocketErrors.AuthenticationError(
                "Error while authenticating WebSocket connection"
            )
        if not stdout:
            raise WebSocketErrors.AuthenticationError("No authentication data received")

        return stdout

    async def _handle_websocket_connection_error(
        self, error: Exception, attempts: int
    ) -> None:
        try:
            """Handle WebSocket connection errors with retry logic."""
            if attempts <= self.MAX_RECONNECT_ATTEMPTS:
                logger.warning(
                    f"WebSocketManager | WebSocket connection attempt {attempts} failed, retrying in {self.RECONNECT_DELAY}s"
                )
                await asyncio.sleep(self.RECONNECT_DELAY)
                await self._connect_websocket(attempts + 1)
            else:
                raise WebSocketErrors.ConnectionError(
                    f"WebSocket connection failed after {attempts} attempts"
                )
        except (asyncio.exceptions.CancelledError, KeyboardInterrupt):
            logger.warning(
                "WebSocketManager | WebSocket connection interrupted by user"
            )
            await self.stop()
            raise

    async def _handle_websocket_message(self, message: str) -> None:
        """Handle a decoded WebSocket message."""
        if self.websocket is None:
            raise WebSocketErrors.NoConnectionError("No WebSocket connection available")

        if message == "null":
            await self.websocket.send_bytes(b"\x00")
        else:
            await self._handle_image(message)

    async def _handle_image(self, message: str) -> None:
        """Handle an image message."""
        pass

    async def _refresh_token_if_needed(self) -> None:
        """Refresh the token if it's expired or about to expire."""
        if self._is_token_expired():
            try:
                self.websocket_token = None
                await self._switch_to_next_session()
                self.websocket_token = await self._get_token()
                if self.websocket is not None:
                    await self._reconnect_websocket()
            except TokenError:
                logger.warning(
                    "WebSocketManager | Token refresh failed, switching to next session"
                )
                await self._switch_to_next_session()

    async def _token_refresh_loop(self) -> None:
        """Periodic token refresh loop."""
        while self._running:
            try:
                await self._refresh_token_if_needed()
                await asyncio.sleep(self.REFRESH_TOKEN_IF_NEEDED_INTERVAL)
            except Exception as error:
                logger.error(f"WebSocketManager | Token refresh error | {error}")
                await asyncio.sleep(self.RECONNECT_DELAY)

    def _is_token_expired(self) -> bool:
        """Check if the current token is expired or about to expire."""
        if not self.websocket_token:
            return True

        try:
            payload = jwt.decode(
                self.websocket_token, options={"verify_signature": False}
            )
            exp_time = datetime.fromtimestamp(payload["exp"])
            return datetime.now() + timedelta(minutes=5) >= exp_time
        except jwt.InvalidTokenError:
            return True

    async def stop(self) -> None:
        """Stop the WebSocket manager and clean up resources."""
        self._running = False
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        if self.websocket:
            await self.websocket.close()
