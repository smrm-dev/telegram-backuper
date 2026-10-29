import os

from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')

# Telegram API credentials
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

SOURCE_CHAT_ENTITY = int(os.getenv('SOURCE_CHAT_ENTITY'))
TARGET_CHAT_ID = int(os.getenv('TARGET_CHAT_ID'))
NUMBER_OF_ACCOUNTS = int(os.getenv('NUMBER_OF_ACCOUNTS'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE'))
