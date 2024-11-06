import asyncio
import sys
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Self
from uuid import uuid4

import jwt
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType
from attr import define, field

from bot.core.canvas_updater.centrifuge import decode_message, encode_commands
from bot.core.canvas_updater.dynamic_canvas_renderer import DynamicCanvasRenderer
from bot.core.canvas_updater.exceptions import (
    SessionErrors,
    TokenError,
    WebSocketErrors,
)
from bot.utils.logger import dev_logger, logger


@define
class SessionData:
    """Represents a WebSocket session with its associated data."""

    name: str = field()
    notpx_headers: Dict[str, str] = field()
    websocket_headers: Dict[str, str] = field()
    image_notpx_headers: Dict[str, str] = field()
    aiohttp_session: ClientSession = field()
    websocket_token: Optional[str] = field(default=None)
    active: bool = field(default=False)

    @classmethod
    def create(
        cls,
        notpx_headers: Dict[str, str],
        websocket_headers: Dict[str, str],
        image_notpx_headers: Dict[str, str],
        aiohttp_session: ClientSession,
        name: str,
        websocket_token: Optional[str] = None,
    ) -> Self:
        """Factory method to create a new session."""
        return cls(
            name=name,
            notpx_headers=notpx_headers,
            websocket_headers=websocket_headers,
            image_notpx_headers=image_notpx_headers,
            aiohttp_session=aiohttp_session,
            websocket_token=websocket_token,
        )


class WebSocketManager:
    """Manages WebSocket connections and sessions."""

    REFRESH_TOKEN_IF_NEEDED_INTERVAL = 60  # seconds
    MAX_RECONNECT_ATTEMPTS = 3  # after initial attempt
    RETRY_DELAY = 5  # seconds

    _instance = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, token_endpoint: str, websocket_url: str) -> None:
        self.token_endpoint = token_endpoint
        self.websocket_url = websocket_url
        self.sessions: List[SessionData] = []
        self.active_session: Optional[SessionData] = None
        self.websocket: Optional[ClientWebSocketResponse] = None
        self.websocket_token: Optional[str] = None
        self.canvas_renderer = DynamicCanvasRenderer()
        self._lock = asyncio.Lock()
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None
        self._connection_attempts = 1

    async def add_session(
        self,
        notpx_headers: Dict[str, str],
        websocket_headers: Dict[str, str],
        image_notpx_headers: Dict[str, str],
        aiohttp_session: ClientSession,
        session_name: str,
        websocket_token: Optional[str] = None,
    ) -> None:
        """Add a new session to the manager."""
        async with self._lock:
            self._validate_session_params(
                notpx_headers, websocket_headers, image_notpx_headers, aiohttp_session
            )

            if session_name in [session.name for session in self.sessions]:
                return

            session = SessionData.create(
                name=session_name,
                notpx_headers=notpx_headers,
                websocket_headers=websocket_headers,
                image_notpx_headers=image_notpx_headers,
                aiohttp_session=aiohttp_session,
                websocket_token=websocket_token,
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
            raise SessionErrors.NoAvailableSessionsError(
                "Can not switch to next session, no sessions available"
            )

        if not self.active_session:
            raise SessionErrors.NoActiveSessionError("No active session available")

        current_session_index = self.sessions.index(self.active_session)
        next_session_index = (current_session_index + 1) % len(self.sessions)

        if next_session_index == 0:
            raise SessionErrors.NoAvailableSessionsError("No available sessions")

        next_session = self.sessions[next_session_index]

        logger.info(
            f"WebSocketManager | Switching from session {self.sessions[current_session_index].name} to session {next_session.name}"
        )
        await self._activate_session(next_session)

    async def _initialize_connection(self) -> None:
        """Initialize the WebSocket connection."""
        try:
            if not self.active_session:
                raise SessionErrors.NoActiveSessionError("No active session available")

            if not self.websocket_token:
                self.websocket_token = await self._get_token()

            await self.canvas_renderer.retrieve_image(
                self.active_session.aiohttp_session,
                self.active_session.image_notpx_headers,
            )

            if not self._refresh_task or self._refresh_task.done():
                self._refresh_task = asyncio.create_task(self._token_refresh_loop())

            websocket_task = asyncio.create_task(self._connect_websocket())
            websocket_task.add_done_callback(handle_task_completion)
        except WebSocketErrors.ConnectionError as error:
            logger.error(f"WebSocketManager | {error}")
            await self._switch_to_next_session()
        except Exception:
            await self.stop()
            raise Exception("Failed to initialize connection")

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
                    f"WebSocketManager | Token retrieval attempt {attempts} failed, retrying in {self.RETRY_DELAY}s"
                )
                await asyncio.sleep(self.RETRY_DELAY)
                return await self._get_token(attempts + 1)
            raise TokenError("Failed to get token")

    async def _connect_websocket(self) -> None:
        """Establish WebSocket connection."""
        if not self.active_session:
            raise SessionErrors.NoActiveSessionError("No active session available")

        try:
            async with self.active_session.aiohttp_session.ws_connect(
                self.websocket_url,
                headers=self.active_session.websocket_headers,
                protocols=["centrifuge-protobuf"],
            ) as websocket:
                self.websocket = websocket
                peername = websocket.get_extra_info("peername")
                logger.info(
                    f"WebSocketManager | WebSocket connection established | IP: {peername[0]}"
                )
                await self._handle_websocket_connection()
        except Exception:
            await self._handle_websocket_connection_error()
        finally:
            logger.warning(
                "WebSocketManager | Stopping..."
            )
            await self.stop()

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

        auth_command = [
            {"connect": {"token": self.websocket_token, "name": "js"}, "id": 1}
        ]
        encoded_auth_command = encode_commands(auth_command)

        await self.websocket.send_bytes(encoded_auth_command)

        while True:
            try:
                message = await self.websocket.receive()

                if message.type == WSMsgType.CLOSE:
                    raise WebSocketErrors.ServerClosedConnectionError(
                        "WebSocket server closed connection"
                    )
                if message.data == b"\x00":
                    await self.websocket.send_bytes(b"\x00")
                    continue

                await self._handle_websocket_message(decode_message(message.data))
            except Exception:
                raise WebSocketErrors.ConnectionError("WebSocket connection failed")

    async def _handle_websocket_message(self, message) -> None:
        """Handle a decoded WebSocket message."""
        if self.websocket is None:
            raise WebSocketErrors.NoConnectionError("No WebSocket connection available")

        if not message:
            return

        if self._connection_attempts > 1:
            dev_logger.info(
                "WebSocketManager | Connection established, reset connection attempts to 1"
            )
            self._connection_attempts = 1

        await self.canvas_renderer.update_canvas(message)

    async def _handle_websocket_connection_error(self) -> None:
        """Handle WebSocket connection errors with retry logic."""
        if self._connection_attempts <= self.MAX_RECONNECT_ATTEMPTS:
            logger.warning(
                f"WebSocketManager | WebSocket connection attempt {self._connection_attempts} failed, retrying in {self.RETRY_DELAY}s"
            )
            await asyncio.sleep(self.RETRY_DELAY)
            self._connection_attempts += 1
            await self._connect_websocket()
        else:
            raise WebSocketErrors.ConnectionError(
                f"WebSocket connection failed after {self._connection_attempts} attempts"
            )

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
                await asyncio.sleep(self.RETRY_DELAY)

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


def handle_task_completion(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as error:
        logger.error(f"{error.__str__() or 'WebSocketManager | Something went wrong'}")
        dev_logger.error(f"{traceback.format_exc()}")
        sys.exit(1)
