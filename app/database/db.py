import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

class Database:
    client: AsyncIOMotorClient = None
    db = None

db = Database()

async def connect_to_mongo():
    db.client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db.db = db.client[os.getenv("DATABASE_NAME", "arrhythmia_db")]
    
    # Create indexes for performance
    await db.db.predictions.create_index([("user_id", 1), ("timestamp", -1)])
    await db.db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
    await db.db.chat_messages.create_index([("conversation_id", 1), ("timestamp", 1)])
    
    print(f"Connected to MongoDB: {os.getenv('DATABASE_NAME')} and initialized indexes")

async def close_mongo_connection():
    db.client.close()
    print("Closed MongoDB connection")

def get_database():
    return db.db
