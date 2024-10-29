import asyncio
from typing import Dict, Self
import aiohttp
from bot.utils.logger import logger


class DynamicCanvasRenderer:
    MAX_ATTEMPTS = 3
    RETRY_DELAY = 5

    _instance = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self._canvas: bytes
        self._lock = asyncio.Lock()

    async def retrieve_image(
        self,
        session: aiohttp.ClientSession,
        image_notpx_headers: Dict[str, str],
        attempts: int = 1,
    ) -> None:
        """Get the canvas from the server."""

        try:
            async with self._lock:
                response = await session.get(
                    "https://image.notpx.app/api/v2/image", headers=image_notpx_headers
                )
                response.raise_for_status()
                self._canvas = await response.read()
        except Exception:
            if attempts <= self.MAX_ATTEMPTS:
                logger.warning(
                    f"DynamicCanvasRenderer | Image retrieval attempt {attempts} failed, retrying in {self.RETRY_DELAY}s"
                )
                await asyncio.sleep(self.RETRY_DELAY)
                return await self.retrieve_image(
                    session=session,
                    image_notpx_headers=image_notpx_headers,
                    attempts=attempts + 1,
                )
            raise Exception(f"DynamicCanvasRenderer | Image retrieval failed after {attempts} attempts")
