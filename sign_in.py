import asyncio
import logging

from telethon import TelegramClient

from logger.logger import init_logger
from settings import API_ID, API_HASH, NUMBER_OF_ACCOUNTS

start_from = 21


async def create_session(account_index):
    """Create a session file for a single Telegram account."""
    logging.info(f"Logging in for session: {account_index}")
    async with TelegramClient(f'account_{account_index}', API_ID, API_HASH) as client:
        # Start the client, prompting for a phone number and verification code
        await client.start()
        logging.info(f"Session file created: account_{account_index}.session")


async def main():
    """Loop through accounts and create session files."""
    for i in range(start_from, NUMBER_OF_ACCOUNTS):
        await create_session(i)


if __name__ == "__main__":
    init_logger()
    asyncio.run(main())
