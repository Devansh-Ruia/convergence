from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os

from app.config import settings
from app.integrations.mongodb import connect_db, close_db
from app.integrations.gemini import init_gemini
from app.api import health, webhook, events

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

# CORS middleware - allow dashboard to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
app.include_router(events.router, prefix="/api", tags=["events"])

# Serve static files (dashboard)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Root endpoint - redirect to dashboard if available."""
    dashboard_path = os.path.join(static_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {
        "name": "Convergence",
        "version": "0.1.0",
        "description": "Multi-Agent PR Review System",
        "dashboard": "/static/dashboard.html"
    }


@app.get("/dashboard")
async def dashboard():
    """Serve the dashboard."""
    dashboard_path = os.path.join(static_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {"error": "Dashboard not found. Create static/dashboard.html"}