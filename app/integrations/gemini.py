import google.generativeai as genai
from app.config import settings
import logging

logger = logging.getLogger(__name__)

_model = None


def init_gemini() -> None:
    """Initialize Gemini API client."""
    global _model
    
    genai.configure(api_key=settings.google_api_key)
    _model = genai.GenerativeModel(settings.gemini_model)
    logger.info(f"Gemini initialized with model: {settings.gemini_model}")


def get_model() -> genai.GenerativeModel:
    """Get Gemini model instance."""
    if _model is None:
        raise RuntimeError("Gemini not initialized. Call init_gemini() first.")
    return _model