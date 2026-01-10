from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.integrations.mongodb import connect_db, close_db
from app.integrations.gemini import init_gemini
from app.api import health, webhook

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting Convergence...")
    await connect_db()
    init_gemini()
    logger.info("Convergence started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Convergence...")
    await close_db()
    logger.info("Convergence shutdown complete")


app = FastAPI(
    title="Convergence",
    description="Multi-Agent Pull Request Review System",
    version="0.1.0",
    lifespan=lifespan
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Convergence",
        "version": "0.1.0",
        "description": "Multi-Agent PR Review System"
    }