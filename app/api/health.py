from fastapi import APIRouter, status
from app.integrations.mongodb import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint."""
    # Quick DB ping to verify connection
    try:
        db = get_db()
        await db.command("ping")
        db_status = "connected"
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        db_status = "disconnected"
    
    return {
        "status": "ok",
        "database": db_status
    }