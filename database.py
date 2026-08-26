from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)

db = client["contentproxbot"]
users = db["users"]
access_requests = db["access_requests"]
