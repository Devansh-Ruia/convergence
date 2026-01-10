from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Global client and database references
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Initialize MongoDB connection and create indexes."""
    global _client, _db
    
    logger.info(f"Connecting to MongoDB database: {settings.mongodb_database}")
    
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.mongodb_database]
    
    # Verify connection
    await _client.admin.command("ping")
    logger.info("MongoDB connection established")
    
    # Create indexes
    await _db.review_sessions.create_index([
        ("github.repo_owner", 1),
        ("github.repo_name", 1),
        ("github.pr_number", 1)
    ])
    await _db.review_sessions.create_index([("status", 1), ("created_at", -1)])
    await _db.review_sessions.create_index([("created_at", -1)])
    
    await _db.agent_findings.create_index([
        ("session_id", 1),
        ("agent_type", 1)
    ], unique=True)
    await _db.agent_findings.create_index([("session_id", 1)])
    
    logger.info("MongoDB indexes created")


async def close_db() -> None:
    """Close MongoDB connection."""
    global _client, _db
    
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    """Get database instance. Raises if not connected."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _db