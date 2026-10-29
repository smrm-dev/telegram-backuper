import pymongo
from motor.motor_asyncio import AsyncIOMotorClient

from .config import *

# MongoDB connection (using Motor for async queries)
async_mongo_client = AsyncIOMotorClient(MONGODB_URI)
db = async_mongo_client['telegram_backup']
async_collection = db['messages']

mongo_client = pymongo.MongoClient(MONGODB_URI)
db = mongo_client['telegram_backup']
collection = db['messages']
