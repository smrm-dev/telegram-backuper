import pymongo
from motor.motor_asyncio import AsyncIOMotorClient

from .config import *

# MongoDB connection (using Motor for async queries)
async_mongo_client = AsyncIOMotorClient("mongodb://localhost:27017/")
db = async_mongo_client['telegram_backup']
async_collection = db['messages']

mongo_client = pymongo.MongoClient("mongodb://localhost:27017/")
db = mongo_client['telegram_backup']
collection = db['messages']
