import asyncio
import io
from functools import lru_cache
from typing import Any, Dict, List, Self, Tuple

import aiohttp
import numpy as np
from PIL import Image

from bot.utils.logger import logger


class DynamicCanvasRenderer:
    MAX_ATTEMPTS = 3
    RETRY_DELAY = 5
    CANVAS_SIZE = 1000
    DYNAMITE_COLOR = "#171F2A"
    DYNAMITE_SIZE = 5
    PUMPKIN_COLORS = [
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#fdbf13",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
        "#ff1600",
        "#ff8600",
    ]
    PUMPKIN_SIZE = 7

    _instance = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self._canvas: np.ndarray = np.zeros(
            self.CANVAS_SIZE * self.CANVAS_SIZE * 4, dtype=np.uint8
        )
        self._lock = asyncio.Lock()

    async def retrieve_image(
        self,
        session: aiohttp.ClientSession,
        image_notpx_headers: Dict[str, str],
        attempts: int = 1,
    ) -> None:
        try:
            async with self._lock:
                response = await session.get(
                    "https://image.notpx.app/api/v2/image", headers=image_notpx_headers
                )
                response.raise_for_status()

                canvas_from_response = Image.open(io.BytesIO(await response.read()))
                canvas_from_response = canvas_from_response.convert("RGBA")
                self._canvas = np.array(canvas_from_response).flatten()
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
            raise Exception(
                f"DynamicCanvasRenderer | Image retrieval failed after {attempts} attempts"
            )

    async def update_canvas(
        self,
        pixels_data: Dict[str, Any],
    ) -> None:
        if pixels_data["channel"] == "event:message":
            await self._paint_squares(self._canvas, pixels_data["data"])
        elif pixels_data["channel"] == "pixel:message":
            await self._paint_pixels(self._canvas, pixels_data["data"])

    async def _paint_squares(
        self, canvas_array, pixels_data: List[Dict[str, Any]]
    ) -> None:
        for pixel_data in pixels_data:
            pixel_id: int = pixel_data["pixel"]
            if pixel_id > self.CANVAS_SIZE * self.CANVAS_SIZE:
                continue

            x, y = self._pixel_id_to_xy(pixel_id)
            x = x - (getattr(self, f"{pixel_data['type'].upper()}_SIZE") // 2)
            y = y - (getattr(self, f"{pixel_data['type'].upper()}_SIZE") // 2)
            colors = (
                self.PUMPKIN_COLORS
                if pixel_data["type"] == "Pumpkin"
                else [self.DYNAMITE_COLOR] * (self.DYNAMITE_SIZE * self.DYNAMITE_SIZE)
            )
            for i, color in enumerate(colors):
                px = x + (i % self.CANVAS_SIZE)
                py = y + (i // self.CANVAS_SIZE)

                rgb_color = self._hex_to_rgb(color)
                pixel_index = (px + py * self.CANVAS_SIZE) * 4
                canvas_array[pixel_index] = rgb_color[0]
                canvas_array[pixel_index + 1] = rgb_color[1]
                canvas_array[pixel_index + 2] = rgb_color[2]
                canvas_array[pixel_index + 3] = 255

    async def _paint_pixels(self, canvas_array, pixels_data: Dict[str, Any]) -> None:
        for hex_color, pixels_id in pixels_data.items():
            if hex_color == "#171F2A":
                continue

            for pixel_id in pixels_id:
                if pixel_id > self.CANVAS_SIZE * self.CANVAS_SIZE:
                    continue

                rgb_color = self._hex_to_rgb(hex_color)
                pixel_index = (pixel_id - 1) * 4
                canvas_array[pixel_index] = rgb_color[0]
                canvas_array[pixel_index + 1] = rgb_color[1]
                canvas_array[pixel_index + 2] = rgb_color[2]
                canvas_array[pixel_index + 3] = 255

    @lru_cache(maxsize=1024)
    def _pixel_id_to_xy(self, pixel_id: int) -> Tuple[int, int]:
        x = (pixel_id - 1) % self.CANVAS_SIZE
        y = (pixel_id - 1) // self.CANVAS_SIZE
        return x, y

    @lru_cache(maxsize=256)
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, ...]:
        return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
