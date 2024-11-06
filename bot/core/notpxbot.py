import asyncio
import io
import json
import random
import traceback
from datetime import datetime
from random import choice, randint
from time import time
from typing import Dict, List, NoReturn
from urllib.parse import parse_qs, quote, unquote
from uuid import uuid4

import aiohttp
import numpy as np
from aiohttp_socks import ProxyConnector
from better_proxy import Proxy
from PIL import Image
from pyrogram.client import Client
from pyrogram.errors import (
    AuthKeyUnregistered,
    FloodWait,
    Unauthorized,
    UserDeactivated,
)
from pyrogram.raw.functions.messages.request_app_web_view import RequestAppWebView
from pyrogram.raw.types.input_bot_app_short_name import InputBotAppShortName

from bot.config.config import settings
from bot.core.canvas_updater.dynamic_canvas_renderer import DynamicCanvasRenderer
from bot.core.canvas_updater.websocket_manager import WebSocketManager
from bot.utils.logger import dev_logger, logger


class NotPXBot:
    def __init__(self, telegram_client: Client, websocket_manager: WebSocketManager):
        self.telegram_client = telegram_client
        self.session_name = telegram_client.name
        self.websocket_manager = websocket_manager
        self.headers = self._create_headers()
        self.max_boosts = {"paintReward": 7, "reChargeSpeed": 11, "energyLimit": 7}
        self.boost_prices = {
            "paintReward": {2: 5, 3: 100, 4: 200, 5: 300, 6: 500, 7: 600},
            "reChargeSpeed": {
                2: 5,
                3: 100,
                4: 200,
                5: 300,
                6: 400,
                7: 500,
                8: 600,
                9: 700,
                10: 800,
                11: 900,
            },
            "energyLimit": {2: 5, 3: 100, 4: 200, 5: 300, 6: 400, 7: 10},
        }
        self._canvas_renderer = DynamicCanvasRenderer()

    def _create_headers(self):
        base_headers = {
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://app.notpx.app",
            "Referer": "https://app.notpx.app/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "",
        }

        websocket_headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "websocket",
            "Sec-Fetch-Mode": "websocket",
            "Sec-Fetch-Site": "same-site",
        }

        def create_headers(additional_headers=None):
            headers = base_headers.copy()
            if additional_headers:
                headers.update(additional_headers)
            return headers

        return {
            "notpx": create_headers({"Authorization": ""}),
            "tganalytics": create_headers(),
            "plausible": create_headers({"Sec-Fetch-Site": "cross-site"}),
            "websocket": create_headers(websocket_headers),
            "image_notpx": create_headers(),
        }

    async def run(self, user_agent: str, proxy: str | None) -> NoReturn:
        for header in self.headers.values():
            header["User-Agent"] = user_agent

        self.proxy = proxy
        proxy_connector = ProxyConnector().from_url(proxy) if proxy else None

        async with aiohttp.ClientSession(connector=proxy_connector) as session:
            while True:
                try:
                    if proxy:
                        await self._proxy_checker(session, proxy)

                        await self._execute_main_loop(session)
                except Exception as error:
                    handle_error(self.session_name, error)
                    logger.info(f"{self.session_name} | Retrying in 60 seconds")
                    await asyncio.sleep(60)

    async def _proxy_checker(self, session: aiohttp.ClientSession, proxy: str):
        try:
            response = await session.get(
                "https://ipinfo.io/ip", timeout=aiohttp.ClientTimeout(10)
            )
            response.raise_for_status()
            ip = await response.text()

            logger.info(f"{self.session_name} | Proxy connected | IP: {ip}")
        except Exception:
            logger.info(f"{self.session_name} | Proxy error | {proxy}")
            raise Exception(f"{self.session_name} | Proxy error | {proxy}")

    async def _execute_main_loop(self, session: aiohttp.ClientSession):
        if settings.SLEEP_AT_NIGHT:
            await self._handle_night_sleep()

        telegram_web_data = await self._get_telegram_web_data(
            "notpixel", "app", settings.REF_ID
        )
        if not telegram_web_data:
            return

        self.headers["notpx"]["Authorization"] = f"initData {telegram_web_data}"

        await self._send_tganalytics_event(session)

        plausible_payload = await self._create_plausible_payload(self.auth_url)
        await self._send_plausible_event(session, plausible_payload)

        about_me_data = await self._get_me(session)

        websocket_token = about_me_data.get("websocketToken")

        await self._get_status(session)

        if not await self._check_my(session):
            await self._set_template(session)

        await self.websocket_manager.add_session(
            notpx_headers=self.headers["notpx"],
            websocket_headers=self.headers["websocket"],
            image_notpx_headers=self.headers["notpx"],
            aiohttp_session=session,
            session_name=self.session_name,
            websocket_token=websocket_token,
        )

        if settings.UPGRADE_BOOSTS:
            if (
                self.boost_energyLimit != self.max_boosts["energyLimit"]
                or self.boost_paintReward != self.max_boosts["paintReward"]
                or self.boost_reChargeSpeed != self.max_boosts["reChargeSpeed"]
            ):
                await self._upgrade_boosts(session)
            else:
                logger.info(f"{self.session_name} | All boosts are maxed out")

        while not self.websocket_manager.websocket:
            await asyncio.sleep(1)

        if settings.PAINT_PIXELS:
            await self._paint_pixels(session)

        if settings.CLAIM_PX:
            await self._claim_px(session)

        sleep_time = (
            randint(
                settings.ITERATION_SLEEP_MINUTES[0], settings.ITERATION_SLEEP_MINUTES[1]
            )
            * 60
        )
        total_minutes = sleep_time // 60
        logger.info(
            f"{self.session_name} | Sleeping for: {total_minutes // 60} hours and {total_minutes % 60} minutes"
        )
        await asyncio.sleep(sleep_time)

    async def _handle_night_sleep(self) -> None:
        current_hour = datetime.now().hour
        start_night_time = randint(
            settings.NIGHT_START_HOURS[0], settings.NIGHT_START_HOURS[1]
        )
        end_night_time = randint(
            settings.NIGHT_END_HOURS[0], settings.NIGHT_END_HOURS[1]
        )
        if start_night_time <= current_hour <= end_night_time:
            random_minutes_to_sleep_time = randint(
                settings.ADDITIONAL_NIGHT_SLEEP_MINUTES[0],
                settings.ADDITIONAL_NIGHT_SLEEP_MINUTES[1],
            )
            sleep_time_in_hours = end_night_time - current_hour
            logger.info(
                f"{self.session_name} | It's night time. Sleeping for: {int(sleep_time_in_hours)} hours and {random_minutes_to_sleep_time} minutes"
            )

            await asyncio.sleep(
                (sleep_time_in_hours * 60 * 60) + (random_minutes_to_sleep_time * 60)
            )

    async def _get_telegram_web_data(
        self, peer_id: str, short_name: str, start_param: str, attempt: int = 1
    ) -> str:
        try:
            if self.proxy:
                proxy = Proxy.from_str(self.proxy)
                self.telegram_client.proxy = {
                    "scheme": proxy.protocol,
                    "hostname": proxy.host,
                    "port": proxy.port,
                    "username": proxy.login,
                    "password": proxy.password,
                }

            if not self.telegram_client.is_connected:
                await self._connect_telegram_client()

            peer = await self.telegram_client.resolve_peer(peer_id=peer_id)
            web_view = await self.telegram_client.invoke(
                RequestAppWebView(
                    peer=peer,  # type: ignore
                    platform="android",
                    app=InputBotAppShortName(bot_id=peer, short_name=short_name),  # type: ignore
                    write_allowed=True,
                    start_param=start_param,
                )
            )

            self.auth_url = web_view.url
            telegram_web_data = unquote(
                unquote(
                    self.auth_url.split("tgWebAppData=")[1].split("tgWebAppVersion")[0]
                )
            )

            query_params = parse_qs(telegram_web_data)
            self._set_user_data(query_params, peer_id)

            init_data = self._create_init_data(query_params)

            if self.telegram_client.is_connected:
                await self.telegram_client.disconnect()

            return init_data
        except FloodWait as error:
            if attempt <= 3:
                logger.warning(
                    f"{self.session_name} | Rate limit exceeded. Will retry in {error.value} seconds"
                )
                await asyncio.sleep(error.value)  # type: ignore
                return await self._get_telegram_web_data(
                    peer_id, short_name, start_param, attempt + 1
                )
            raise Exception(
                f"{self.session_name} | Error while getting telegram web data"
            )
        except Exception:
            if attempt <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to get telegram web data, retrying in 5 seconds | Attempts: {attempt}"
                )
                await asyncio.sleep(5)
                return await self._get_telegram_web_data(
                    peer_id, short_name, start_param, attempt + 1
                )
            raise Exception(
                f"{self.session_name} | Error while getting telegram web data"
            )

    async def _connect_telegram_client(self):
        try:
            await self.telegram_client.connect()
        except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
            logger.error(f"{self.session_name} | Invalid session")
            raise

    def _set_user_data(self, query_params, peer_id):
        user_data = json.loads(query_params["user"][0])
        if peer_id == "notpixel":
            self.start_param = query_params["start_param"][0]
            self.telegram_client_id = user_data["id"]
            self.language_code = user_data["language_code"]
            self.is_premium_user = user_data.get("is_premium_user", False)

    def _create_init_data(self, query_params):
        user_data_encoded = quote(query_params["user"][0])
        auth_date = query_params["auth_date"][0]
        hash_value = query_params["hash"][0]
        chat_param = self._get_chat_param(query_params)
        start_param = (
            f"&start_param={self.start_param}" if hasattr(self, "start_param") else ""
        )
        return f"user={user_data_encoded}{chat_param}{start_param}&auth_date={auth_date}&hash={hash_value}"

    def _get_chat_param(self, query_params):
        chat_instance = query_params.get("chat_instance", [None])[0]
        chat_type = query_params.get("chat_type", [None])[0]
        return (
            f"&chat_instance={chat_instance}&chat_type={chat_type}"
            if chat_instance and chat_type
            else ""
        )

    async def _get_me(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> Dict[str, str]:
        try:
            response = await session.get(
                "https://notpx.app/api/v1/users/me", headers=self.headers["notpx"]
            )
            response.raise_for_status()
            response_json = await response.json()

            return response_json

        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to get info about me, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._get_me(session=session, attempts=attempts + 1)
            raise Exception(f"{self.session_name} | Error while getting info about me")

    async def _send_tganalytics_event(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> None:
        try:
            response = await session.get(
                "https://tganalytics.xyz/aee7c93a9ae7930fb19732325d2c560c53849aa7",
                headers=self.headers["tganalytics"],
            )
            response.raise_for_status()

            task = await response.text()
            solution = await self._solve_task(task)

            headers = self.headers["tganalytics"]
            headers["Content"] = solution
            headers["TGA-Auth-Token"] = (
                "eyJhcHBfbmFtZSI6Ik5vdFBpeGVsIiwiYXBwX3VybCI6Imh0dHBzOi8vdC5tZS9ub3RwaXhlbC9hcHAiLCJhcHBfZG9tYWluIjoiaHR0cHM6Ly9hcHAubm90cHguYXBwIn0=!qE41yKlb/OkRyaVhhgdePSZm5Nk7nqsUnsOXDWqNAYE="
            )

            random_event_delay = randint(2500, 2800)

            payload = self._create_tganalytics_payload(random_event_delay)

            await asyncio.sleep(random_event_delay / 1000)

            response = await session.post(
                "https://tganalytics.xyz/events", headers=headers, json=payload
            )
            response.raise_for_status()

            logger.info(f"{self.session_name} | Sent tganalytics event")
        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to send tganalytics event, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._send_tganalytics_event(
                    session=session, attempts=attempts + 1
                )
            raise Exception(
                f"{self.session_name} | Error while sending tganalytics event"
            )

    def _create_tganalytics_payload(self, random_event_delay) -> List[Dict[str, str]]:
        base_event = {
            "session_id": str(uuid4()),
            "user_id": int(self.telegram_client_id),
            "app_name": "NotPixel",
            "is_premium": self.is_premium_user,
            "platform": "android",
            "locale": self.language_code,
        }
        return [
            {
                **base_event,
                "event_name": "app-hide",
                "client_timestamp": str(int(time() * 1000)),
            },
            {
                **base_event,
                "event_name": "app-init",
                "client_timestamp": str(int(time() * 1000) + random_event_delay),
            },
        ]

    async def _send_plausible_event(
        self,
        session: aiohttp.ClientSession,
        payload: Dict[str, str | None],
        attempts: int = 1,
    ) -> None:
        try:
            response = await session.post(
                "https://plausible.joincommunity.xyz/api/event",
                headers=self.headers["plausible"],
                data=payload,
            )
            response.raise_for_status()
            logger.info(f"{self.session_name} | Plausible event sent")
        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to send plausible event, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._send_plausible_event(
                    session=session, payload=payload, attempts=attempts + 1
                )
            raise Exception(
                f"{self.session_name} | Error while sending plausible event"
            )

    async def _create_plausible_payload(self, url: str) -> Dict[str, str | None]:
        return {"n": "pageview", "u": url, "d": "notpx.app", "r": None}

    async def _solve_task(self, task: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                "bot/core/poh_solver/main.js",
                task,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if stderr:
                raise Exception(
                    f"{self.session_name} | Error while solving task | {stderr.decode('utf-8').strip()}"
                )
            return stdout.decode("utf-8").strip()
        except Exception:
            raise Exception(f"{self.session_name} | Unknown error while solving task")

    async def _claim_px(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> None:
        try:
            plausible_payload = await self._create_plausible_payload(
                "https://app.notpx.app/claiming"
            )
            await self._send_plausible_event(session, plausible_payload)

            response = await session.get(
                "https://notpx.app/api/v1/mining/claim", headers=self.headers["notpx"]
            )
            response.raise_for_status()
            response_json = await response.json()

            logger.info(
                f"{self.session_name} | Successfully claimed {response_json['claimed']} px"
            )

            plausible_payload = await self._create_plausible_payload(
                "https://app.notpx.app/"
            )
            await self._send_plausible_event(session, plausible_payload)
        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to claim px, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._claim_px(session=session, attempts=attempts + 1)
            raise Exception(f"{self.session_name} | Error while claiming px")

    async def _set_template(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> None:
        try:
            plausible_payload = await self._create_plausible_payload(
                "https://app.notpx.app/template"
            )
            await self._send_plausible_event(session, plausible_payload)

            response = await session.get(
                "https://notpx.app/api/v1/image/template/list?limit=12&offset=0",
                headers=self.headers["notpx"],
            )
            response.raise_for_status()
            response_json = await response.json()

            random_template = choice(response_json)

            response = await session.get(
                f"https://notpx.app/api/v1/image/template/{random_template['templateId']}",
                headers=self.headers["notpx"],
            )
            response.raise_for_status()
            response_json = await response.json()

            self.template_id = response_json.get("id")
            self.template_url = response_json.get("url")
            self.template_x = response_json.get("x")
            self.template_y = response_json.get("y")
            self.template_size = response_json.get("imageSize")

            response = await session.put(
                f"https://notpx.app/api/v1/image/template/subscribe/{self.template_id}",
                headers=self.headers["notpx"],
            )
            response.raise_for_status()

            logger.info(f"{self.session_name} | Successfully changed template")

            plausible_payload = await self._create_plausible_payload(
                "https://app.notpx.app/"
            )
            await self._send_plausible_event(session, plausible_payload)
        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to change template, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._set_template(session=session, attempts=attempts + 1)
            raise Exception(f"{self.session_name} | Error while changing template")

    async def _check_my(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> bool | None:
        try:
            response = await session.get(
                "https://notpx.app/api/v1/image/template/my",
                headers=self.headers["notpx"],
            )
            if response.status == 404:
                return False
            elif response.status == 200:
                response_json = await response.json()

                self.template_id = response_json.get("templateId")
                self.template_url = response_json.get("url")
                self.template_x = response_json.get("x")
                self.template_y = response_json.get("y")
                self.template_size = response_json.get("imageSize")
                return True
            else:
                response.raise_for_status()
        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to check my, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._check_my(session=session, attempts=attempts + 1)
            raise Exception(f"{self.session_name} | Error while checking my")

    async def _get_status(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> None:
        try:
            response = await session.get(
                "https://notpx.app/api/v1/mining/status", headers=self.headers["notpx"]
            )
            response.raise_for_status()

            response_json = await response.json()
            self.boost_energyLimit = response_json.get("boosts", {}).get("energyLimit")
            self.boost_paintReward = response_json.get("boosts", {}).get("paintReward")
            self.boost_reChargeSpeed = response_json.get("boosts", {}).get(
                "reChargeSpeed"
            )
            self.balance = response_json.get("userBalance")
            self.league = response_json.get("league")
            self._charges = response_json.get("charges")

            logger.info(
                f"{self.session_name} | Successfully logged in | Balance: {self.balance} | League: {self.league.capitalize()}"
            )

        except Exception:
            if attempts <= 3:
                logger.warning(
                    f"{self.session_name} | Failed to get status, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._get_status(session=session, attempts=attempts + 1)
            raise Exception(f"{self.session_name} | Error while getting status")

    async def _upgrade_boosts(
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> None:
        boost_order = ["energyLimit", "paintReward", "reChargeSpeed"]

        try:
            plausible_payload = await self._create_plausible_payload(
                "https://app.notpx.app/claiming"
            )
            await self._send_plausible_event(session, plausible_payload)

            while True:
                for boost_type in boost_order:
                    current_boost = getattr(self, f"boost_{boost_type}")
                    if current_boost < self.max_boosts[boost_type]:
                        if await self._upgrade_boost(session, boost_type):
                            break
                        return
                else:
                    return

        except Exception:
            if attempts < 3:
                logger.warning(
                    f"{self.session_name} | Failed to upgrade boosts, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                await self._upgrade_boosts(session=session, attempts=attempts + 1)
            else:
                raise Exception(f"{self.session_name} | Error while upgrading boosts")

    async def _upgrade_boost(self, session, boost_type) -> bool:
        url = f"https://notpx.app/api/v1/mining/boost/check/{boost_type}"

        if (
            self.balance
            < self.boost_prices[boost_type][getattr(self, f"boost_{boost_type}") + 1]
        ):
            logger.info(
                f"{self.session_name} | Not enough balance to upgrade {boost_type.capitalize()}"
            )
            return False

        response = await session.get(url, headers=self.headers["notpx"])
        response.raise_for_status()
        response_json = await response.json()

        if not response_json.get(boost_type):
            raise Exception(
                f"{self.session_name} | Couldn't retrieve {boost_type.capitalize} from response json while upgrading boost"
            )

        old_boost = getattr(self, f"boost_{boost_type}")
        setattr(self, f"boost_{boost_type}", old_boost + 1)
        self.balance -= self.boost_prices[boost_type][
            getattr(self, f"boost_{boost_type}")
        ]
        logger.info(
            f"{self.session_name} | Successfully leveled up {boost_type.capitalize()}! | LVL.{old_boost} -> LVL.{old_boost + 1}"
        )
        return True

    async def _paint_pixel(
        self,
        session: aiohttp.ClientSession,
        canvas_x: int,
        canvas_y: int,
        template_pixel: np.ndarray,
    ) -> None:
        """Paint a single pixel and handle the response."""

        template_pixel_hex = self._canvas_renderer.rgba_to_hex(
            tuple(template_pixel.flatten().tolist())
        )
        canvas_pixel_id = self._canvas_renderer._xy_to_pixel_id(canvas_x, canvas_y)

        payload = {
            "pixelId": canvas_pixel_id,
            "newColor": template_pixel_hex,
        }

        async with session.post(
            "https://notpx.app/api/v1/repaint/start",
            headers=self.headers["notpx"],
            json=payload,
        ) as response:
            response.raise_for_status()
            self._charges -= 1

            response_json = await response.json()
            new_balance = response_json.get("balance")

            if new_balance > self.balance:
                balance_increase = new_balance - self.balance
                logger.info(
                    f"{self.session_name} | Successfully painted pixel | +{balance_increase} PX"
                )
                self.balance = new_balance
                return

            logger.warning(
                f"{self.session_name} | Failed to paint pixel | Current balance: {self.balance}"
            )

    async def _paint_pixels(
        self, session: aiohttp.ClientSession, attempts: int = 0
    ) -> None:
        try:
            response = await session.get(
                self.template_url, headers=self.headers["image_notpx"]
            )
            response.raise_for_status()

            template_from_response = Image.open(io.BytesIO(await response.read()))
            template_from_response = template_from_response.convert("RGBA")
            template_array = np.array(template_from_response)
            template_2d = template_array.reshape(
                (self.template_size, self.template_size, 4)
            )

            for ty in range(self.template_size):
                if self._charges <= 0:
                    break

                for tx in range(self.template_size):
                    if self._charges <= 0:
                        break

                    canvas_array = self._canvas_renderer.get_canvas
                    canvas_2d = canvas_array.reshape(
                        (
                            self._canvas_renderer.CANVAS_SIZE,
                            self._canvas_renderer.CANVAS_SIZE,
                            4,
                        )
                    )

                    canvas_x = self.template_x + tx
                    canvas_y = self.template_y + ty

                    template_pixel = template_2d[ty, tx]
                    canvas_pixel = canvas_2d[canvas_y, canvas_x]

                    if template_pixel[3] == 0:
                        continue

                    if not np.array_equal(template_pixel[:3], canvas_pixel[:3]):
                        await self._paint_pixel(
                            session=session,
                            canvas_x=canvas_x,
                            canvas_y=canvas_y,
                            template_pixel=template_pixel,
                        )
                        await asyncio.sleep(random.uniform(0.95, 2.3))

        except Exception as e:
            if attempts <= 1:
                logger.warning(
                    f"{self.session_name} | Failed to paint pixel, retrying in 5 seconds | Attempts: {attempts + 1}"
                )
                await asyncio.sleep(5)
                await self._paint_pixels(session=session, attempts=attempts + 1)
            else:
                raise Exception(
                    f"{self.session_name} | Max retry attempts reached while painting pixels: {str(e)}"
                )


def handle_error(session_name, error: Exception) -> None:
    logger.error(
        f"{session_name} | {error.__str__() or 'NotPXBot | Something went wrong'}"
    )
    dev_logger.error(f"{session_name} | {traceback.format_exc()}")


async def run_notpxbot(
    telegram_client: Client,
    user_agent: str,
    proxy: str | None,
    start_delay: int,
) -> None:
    websocket_manager = None
    try:
        websocket_manager = WebSocketManager(
            token_endpoint="https://notpx.app/api/v1/users/me",
            websocket_url="wss://notpx.app/connection/websocket",
        )
        logger.info(f"{telegram_client.name} | Starting in {start_delay} seconds")
        await asyncio.sleep(start_delay)

        await NotPXBot(
            telegram_client=telegram_client, websocket_manager=websocket_manager
        ).run(user_agent=user_agent, proxy=proxy)
    except Exception as error:
        handle_error(telegram_client.name, error)
    finally:
        if telegram_client.is_connected:
            await telegram_client.disconnect()

        if websocket_manager and websocket_manager._running:
            await websocket_manager.stop()

        logger.warning(f"{telegram_client.name} | Stopped")
