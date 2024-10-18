import asyncio
import json
import traceback
from datetime import datetime
from random import randint
from time import time
from typing import Dict, List
from urllib.parse import parse_qs, quote, unquote
from uuid import uuid4

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram.client import Client
from pyrogram.errors import AuthKeyUnregistered, Unauthorized, UserDeactivated
from pyrogram.raw.functions.messages.request_app_web_view import RequestAppWebView
from pyrogram.raw.types.input_bot_app_short_name import InputBotAppShortName

from bot.config.config import settings
from bot.utils.logger import dev_logger, logger


class NotPXBot:
    def __init__(self, telegram_client: Client):
        self.telegram_client = telegram_client
        self.session_name = telegram_client.name
        self.headers = self._create_headers()

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
        return {
            "notpx": {**base_headers, "Authorization": ""},
            "tganalytics": base_headers.copy(),
            "plausible": {**base_headers, "Sec-Fetch-Site": "cross-site"},
        }

    async def run(self, user_agent: str, proxy: str | None):
        for header in self.headers.values():
            header["User-Agent"] = user_agent

        self.proxy = proxy
        proxy_connection = ProxyConnector().from_url(proxy) if proxy else None

        async with aiohttp.ClientSession(connector=proxy_connection) as session:
            if proxy:
                await self._proxy_checker(session, proxy)

            while True:
                try:
                    await self._execute_main_loop(session)
                except Exception as error:
                    self._handle_error(error)
                    await asyncio.sleep(10)

    async def _proxy_checker(self, session: aiohttp.ClientSession, proxy: str):
        try:
            response = await session.get(
                "https://ipinfo.io/ip", timeout=aiohttp.ClientTimeout(10)
            )
            ip = await response.text()
            logger.info(f"{self.session_name} | Proxy connected | IP: {ip}")
        except Exception as error:
            raise Exception(f"Proxy: {proxy} | {error or 'Unknown error'}")

    async def _execute_main_loop(self, session: aiohttp.ClientSession):
        if settings.SLEEP_AT_NIGHT:
            await self._handle_night_sleep()

        telegram_web_data = await self._get_telegram_web_data(
            "notpixel", "app", settings.REF_ID
        )
        if not telegram_web_data:
            return

        self.headers["notpx"]["Authorization"] = f"initData {telegram_web_data}"

        await self._send_plausible_event(session)
        info_about_me = await self._get_me(session)
        logger.info(
            f"{self.session_name} | Successfully logged in | Balance: {info_about_me['balance']} | League: {info_about_me['league']}"
        )

        await self._send_tganalytics_event(session)

        sleep_time = randint(settings.SLEEP_TIME[0], settings.SLEEP_TIME[1]) * 60
        logger.info(
            f"{self.session_name} | Sleeping for: {round(sleep_time / 60 / 60, 1)} hours"
        )
        await asyncio.sleep(sleep_time)

    async def _handle_night_sleep(self):
        current_hour = datetime.now().hour
        start_night_time = randint(settings.NIGHT_START[0], settings.NIGHT_START[1])
        end_night_time = randint(settings.NIGHT_END[0], settings.NIGHT_END[1])
        if start_night_time <= current_hour <= end_night_time:
            sleep_time = end_night_time - current_hour
            logger.info(
                f"{self.session_name} | It's night time. Sleeping for: {sleep_time} hours"
            )
            await asyncio.sleep(sleep_time * 60 * 60)

    async def _get_telegram_web_data(
        self, peer_id: str, short_name: str, start_param: str
    ):
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
        except Exception as error:
            raise Exception(
                f"{self.session_name} | Error while getting telegram web data | {error or 'Unknown error'}"
            )

    async def _connect_telegram_client(self):
        try:
            await self.telegram_client.connect()
        except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
            logger.error(f"{self.session_name} | Invalid")
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

    async def _get_me(self, session: aiohttp.ClientSession, attempts: int = 1):
        try:
            response = await session.get(
                "https://notpx.app/api/v1/users/me", headers=self.headers["notpx"]
            )
            response.raise_for_status()
            return await response.json()
        except Exception as error:
            if attempts <= 3:
                logger.info(
                    f"{self.session_name} | Failed to get info about me, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._get_me(session=session, attempts=attempts + 1)
            raise Exception(
                f"{self.session_name} | Error while getting info about me | {error or 'Unknown error'}"
            )

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
        except Exception as error:
            if attempts < 1:
                logger.info(
                    f"{self.session_name} | Failed to send tganalytics event, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._send_tganalytics_event(
                    session=session, attempts=attempts + 1
                )
            raise Exception(
                f"{self.session_name} | Error while sending tganalytics event | {error or 'Unknown error'}"
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
        self, session: aiohttp.ClientSession, attempts: int = 1
    ) -> None:
        try:
            payload = {"n": "pageview", "u": self.auth_url, "d": "notpx.app", "r": None}
            response = await session.post(
                "https://plausible.joincommunity.xyz/api/event",
                headers=self.headers["plausible"],
                data=payload,
            )
            response.raise_for_status()
            logger.info(f"{self.session_name} | Plausible event sent")
        except Exception as error:
            if attempts < 1:
                logger.info(
                    f"{self.session_name} | Failed to send plausible event, retrying in 5 seconds | Attempts: {attempts}"
                )
                await asyncio.sleep(5)
                return await self._send_plausible_event(
                    session=session, attempts=attempts + 1
                )
            raise Exception(
                f"{self.session_name} | Error while sending plausible event | {error or 'Unknown error'}"
            )

    async def _solve_task(self, task: str) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "node",
                "bot/utils/task_solver/main.js",
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
        except Exception as error:
            raise Exception(f"{self.session_name} | Error while solving task | {error}")

    def _handle_error(self, error) -> None:
        logger.error(f"{self.session_name} | {error or 'Something went wrong'}")
        dev_logger.error(f"{self.session_name} | {traceback.format_exc()}")


async def run_notpxbot(
    telegram_client: Client, user_agent: str, proxy: str | None, start_delay: int
) -> None:
    try:
        logger.info(f"{telegram_client.name} | Starting in {start_delay} seconds")
        await asyncio.sleep(start_delay)
        await NotPXBot(telegram_client=telegram_client).run(
            user_agent=user_agent, proxy=proxy
        )
    except Exception as error:
        logger.error(f"{telegram_client.name} | {error or 'Something went wrong'}")
        dev_logger.error(f"{telegram_client.name} | {traceback.format_exc()}")
