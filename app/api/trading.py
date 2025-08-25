"""
Trading API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from app.core.database import get_db
from app.core.cache import redis_cache

router = APIRouter()


@router.get("/status")
async def get_trading_status():
    """Get current trading status."""
    try:
        # Get cached status or default
        status = redis_cache.get("trading_status") or {
            "is_trading": False,
            "market_open": False,
            "positions_count": 0,
            "daily_pnl": 0.0
        }
        
        status["timestamp"] = datetime.now().isoformat()
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trading status: {e}")


@router.get("/positions")
async def get_positions(db: Session = Depends(get_db)):
    """Get current open positions."""
    try:
        # TODO: Implement with database models
        # For now, return cached positions
        positions = redis_cache.get("open_positions") or []
        
        return {
            "positions": positions,
            "count": len(positions),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {e}")


@router.post("/start")
async def start_trading():
    """Start the trading bot."""
    try:
        # Set trading status
        redis_cache.set("trading_status", {
            "is_trading": True,
            "started_at": datetime.now().isoformat()
        })
        
        return {"message": "Trading bot started successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start trading: {e}")


@router.post("/stop")
async def stop_trading():
    """Stop the trading bot."""
    try:
        # Set trading status
        redis_cache.set("trading_status", {
            "is_trading": False,
            "stopped_at": datetime.now().isoformat()
        })
        
        return {"message": "Trading bot stopped successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop trading: {e}")


@router.get("/watchlist")
async def get_watchlist():
    """Get current trading watchlist."""
    try:
        watchlist = redis_cache.get("watchlist") or []
        
        return {
            "watchlist": watchlist,
            "count": len(watchlist),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get watchlist: {e}")