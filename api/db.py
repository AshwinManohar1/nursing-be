from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from api.config import settings

client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongodb_uri)


def get_db(client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    return client[settings.database_name]
