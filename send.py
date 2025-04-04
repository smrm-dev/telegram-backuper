import asyncio
import logging

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError

from logger.logger import init_logger
from settings import API_ID, API_HASH, TARGET_CHAT_ID, BATCH_SIZE, NUMBER_OF_ACCOUNTS, async_collection


async def fetch_messages(batch_size):
    """Fetch up to batch_size unsent messages from MongoDB."""
    cursor = async_collection.find({'sent': {'$ne': True}, 'id': {'$gte': 13149}}).sort('id').limit(batch_size)
    return await cursor.to_list(length=batch_size)


async def send_message(client, message, account_index):
    """Send a single message using a Telegram account."""
    retries = 3
    while retries > 0:
        try:
            text = message.get('text', '')
            media = message.get('media', None)
            await client.send_message(TARGET_CHAT_ID, text, file=media)
            logging.info(f"Sent message ID: {message['id']} {account_index=}")

            # Mark message as sent in MongoDB
            await async_collection.update_one({'_id': message['_id']}, {'$set': {'sent': True}})
            await asyncio.sleep(1)
            break
        except FloodWaitError as e:
            logging.warning(f"Rate limit hit. Sleeping for {e.seconds} seconds.")
            return e.seconds
            # await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logging.error(f"Error sending message ID {message['id']}: {e}")
            logging.info(message)
            retries -= 1
    return 0


async def process_batch(account_index, messages):
    """Process a batch of messages with a single Telegram account."""
    async with TelegramClient(f'sessions/account_{account_index}', API_ID, API_HASH) as client:
        # Use asyncio.gather for concurrent message sending within the batch
        for message in messages:
            hit_rate_limit = await send_message(client, message, account_index)
            if hit_rate_limit:
                return hit_rate_limit
        return 0


async def distribute_work():
    """Fetch messages and distribute them across multiple accounts."""
    while True:
        # Fetch the next batch of unsent messages
        messages = await fetch_messages(BATCH_SIZE)
        if not messages:
            logging.info("No more unsent messages found.")
            break

        # Split messages among available accounts
        account_tasks = []
        messages_per_account = len(messages) // NUMBER_OF_ACCOUNTS
        for i in range(NUMBER_OF_ACCOUNTS):
            if i in [7, 3]:
                continue
                # Determine the chunk of messages for this account
            start_idx = i * messages_per_account
            end_idx = (i + 1) * messages_per_account if i != NUMBER_OF_ACCOUNTS - 1 else len(messages)
            account_messages = messages[start_idx:end_idx]

            if account_messages:
                account_tasks.append(process_batch(i, account_messages))

        # Process all accounts concurrently
        results = await asyncio.gather(*account_tasks)

        if all(results):
            sleep_time = max(results)
            logging.info(f'sleeping for {sleep_time} seconds')
            await asyncio.sleep(sleep_time)


async def main():
    await distribute_work()


# Run the script
if __name__ == "__main__":
    init_logger()
    asyncio.run(main())
