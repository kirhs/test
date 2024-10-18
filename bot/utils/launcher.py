import argparse
import asyncio
import traceback
from random import randint
from typing import Dict, List

from better_proxy import Proxy

from bot.config.config import settings
from bot.core.notpxbot import run_notpxbot
from bot.core.registrator import get_telegram_client, register_sessions
from bot.utils.accounts_manager import AccountsManager
from bot.utils.banner_animation import print_banner_animation
from bot.utils.logger import dev_logger, logger

options = """
1. Register session
2. Start bot
"""


async def process() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--action", type=int, help="Action to perform")

    # print_banner_animation()

    action = parser.parse_args().action

    if not action:
        print(options)

        while True:
            action = input("> ")

            if not action.isdigit():
                logger.warning("Action must be number")
                print(options)
            elif action not in ["1", "2"]:
                logger.warning("Action must be 1 or 2")
                print(options)
            else:
                action = int(action)
                break

    if action == 1:
        await register_sessions()
    elif action == 2:
        accounts = await AccountsManager().get_accounts()
        await run_tasks(accounts=accounts)


async def run_tasks(accounts: List[Dict[str, str]]) -> None:
    tasks = []
    try:
        for account in accounts:
            session_name, user_agent, raw_proxy = account.values()
            telegram_client = await get_telegram_client(
                session_name=session_name, raw_proxy=raw_proxy
            )
            proxy = Proxy.from_str(proxy=raw_proxy).as_url if raw_proxy else None

            start_delay = randint(settings.START_DELAY[0], settings.START_DELAY[1])

            tasks.append(
                asyncio.create_task(
                    run_notpxbot(
                        telegram_client=telegram_client,
                        user_agent=user_agent,
                        proxy=proxy,
                        start_delay=start_delay,
                    )
                )
            )
    except Exception as error:
        logger.error(f"{error or 'Something went wrong'}")
        dev_logger.error(f"{traceback.format_exc()}")

    await asyncio.gather(*tasks)
