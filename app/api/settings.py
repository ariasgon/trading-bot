"""
Settings API endpoints for configuring bot parameters.
"""
import logging
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


class AlpacaSettings(BaseModel):
    """Alpaca API configuration."""
    api_key: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"


@router.post("/alpaca")
async def update_alpaca_settings(settings: AlpacaSettings):
    """
    Update Alpaca API credentials.

    Note: This stores credentials in environment variables for the current session.
    For persistent storage, credentials should be saved to .env file manually.
    """
    try:
        # Validate URL
        valid_urls = [
            "https://paper-api.alpaca.markets",
            "https://api.alpaca.markets"
        ]

        if settings.base_url not in valid_urls:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid API URL. Must be one of: {', '.join(valid_urls)}"
            )

        # Validate API keys (basic validation)
        if not settings.api_key or len(settings.api_key) < 10:
            raise HTTPException(
                status_code=400,
                detail="Invalid API key format"
            )

        if not settings.secret_key or len(settings.secret_key) < 10:
            raise HTTPException(
                status_code=400,
                detail="Invalid secret key format"
            )

        # Update environment variables for current session
        os.environ['ALPACA_API_KEY'] = settings.api_key
        os.environ['ALPACA_SECRET_KEY'] = settings.secret_key
        os.environ['ALPACA_BASE_URL'] = settings.base_url

        logger.info(f"Alpaca settings updated - Base URL: {settings.base_url}")

        return {
            "success": True,
            "message": "Settings updated successfully. Restart the bot for changes to take effect.",
            "base_url": settings.base_url,
            "is_paper_trading": "paper" in settings.base_url.lower()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Alpaca settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update settings: {str(e)}"
        )


@router.get("/alpaca")
async def get_alpaca_settings():
    """
    Get current Alpaca API configuration (without exposing keys).
    """
    try:
        current_url = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        has_api_key = bool(os.getenv('ALPACA_API_KEY'))
        has_secret_key = bool(os.getenv('ALPACA_SECRET_KEY'))

        return {
            "base_url": current_url,
            "is_paper_trading": "paper" in current_url.lower(),
            "has_api_key": has_api_key,
            "has_secret_key": has_secret_key,
            "is_configured": has_api_key and has_secret_key
        }

    except Exception as e:
        logger.error(f"Error getting Alpaca settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get settings: {str(e)}"
        )


@router.get("/status")
async def get_settings_status():
    """
    Get overall settings status and configuration health.
    """
    try:
        alpaca_configured = bool(os.getenv('ALPACA_API_KEY')) and bool(os.getenv('ALPACA_SECRET_KEY'))
        database_url = os.getenv('DATABASE_URL', '')
        redis_url = os.getenv('REDIS_URL', '')

        return {
            "alpaca": {
                "configured": alpaca_configured,
                "base_url": os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets'),
                "is_paper_trading": "paper" in os.getenv('ALPACA_BASE_URL', 'paper').lower()
            },
            "database": {
                "configured": bool(database_url),
                "type": "PostgreSQL" if "postgresql" in database_url.lower() else "SQLite"
            },
            "redis": {
                "configured": bool(redis_url)
            }
        }

    except Exception as e:
        logger.error(f"Error getting settings status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )
