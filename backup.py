import asyncio
import logging
import os

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError

from logger.logger import init_logger
from settings import API_ID, API_HASH, SOURCE_CHAT_ENTITY, collection

last_message_file = "last_message_id.txt"


def get_last_message_id():
    """Read the last sent message ID from the file."""
    if os.path.exists(last_message_file):
        with open(last_message_file, "r") as file:
            return int(file.read().strip())
    return 0


def save_last_message_id(message_id):
    """Save the last sent message ID to the file."""
    with open(last_message_file, "w") as file:
        file.write(str(message_id))


async def fetch_and_store_messages():
    """Fetch messages from source channel and store in MongoDB."""
    async with TelegramClient('sessions/session_name', API_ID, API_HASH) as client:
        source_channel = await client.get_entity(SOURCE_CHAT_ENTITY)

        last_message_id = get_last_message_id()
        logging.info(f"Resuming from message ID: {last_message_id if last_message_id else 'start'}")

        async for message in client.iter_messages(source_channel, offset_id=last_message_id, reverse=True):
            retries = 3
            while retries > 0:
                try:
                    # Prepare the message data
                    message_data = {
                        'id': message.id,
                        'date': message.date,
                        'text': message.text,
                        'media': message.media.to_dict() if message.media else None,
                        'from_id': message.from_id,
                    }

                    # Insert into MongoDB if not already stored
                    if collection.find_one({'id': message.id}) is None:
                        collection.insert_one(message_data)
                        logging.info(f"Stored message ID: {message.id}")
                    else:
                        logging.info(f"Message ID {message.id} already in database.")

                    save_last_message_id(message.id)  # Save progress
                    break
                except FloodWaitError as e:
                    logging.warning(f"Rate limit hit. Sleeping for {e.seconds} seconds.")
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    retries -= 1
                    logging.error(f"Error processing message: {e}")
                    await asyncio.sleep(5)


async def main():
    await fetch_and_store_messages()


if __name__ == '__main__':
    init_logger()
    asyncio.run(main())
