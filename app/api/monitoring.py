"""
Monitoring and performance API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional

from app.core.database import get_db
from app.core.cache import redis_cache
from app.services.portfolio import portfolio_service

router = APIRouter()


@router.get("/performance/daily")
async def get_daily_performance(trade_date: Optional[date] = None):
    """Get daily performance metrics."""
    try:
        if not trade_date:
            trade_date = date.today()
        
        performance = portfolio_service.get_daily_performance(trade_date)
        
        if not performance:
            # Return default values if no data exists
            performance = {
                "trade_date": trade_date.isoformat(),
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "largest_win": 0.0,
                "largest_loss": 0.0
            }
        
        performance["timestamp"] = datetime.now().isoformat()
        return performance
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance: {e}")


@router.get("/performance/summary")
async def get_performance_summary(days: int = 30):
    """Get overall performance summary."""
    try:
        summary = portfolio_service.get_performance_summary(days=days)
        
        if not summary:
            summary = {
                "period_days": days,
                "total_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0
            }
        
        summary["timestamp"] = datetime.now().isoformat()
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {e}")


@router.get("/logs")
async def get_recent_logs(limit: int = 50):
    """Get recent trading logs."""
    try:
        # TODO: Implement log retrieval
        logs = redis_cache.get("recent_logs") or []
        
        return {
            "logs": logs[-limit:],
            "count": len(logs),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {e}")


@router.get("/risk")
async def get_risk_metrics():
    """Get current risk metrics."""
    try:
        risk_metrics = portfolio_service.calculate_risk_metrics()
        return risk_metrics
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get risk metrics: {e}")


@router.get("/account-summary")
async def get_account_summary():
    """Get complete account summary."""
    try:
        summary = portfolio_service.get_account_summary()
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get account summary: {e}")


@router.get("/risk/check-limits")
async def check_risk_limits():
    """Check if any risk limits are violated."""
    try:
        risk_check = portfolio_service.check_risk_limits()
        return risk_check
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check risk limits: {e}")