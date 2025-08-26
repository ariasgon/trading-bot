"""
Trading API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.core.cache import redis_cache
from app.services.portfolio import portfolio_service
from app.services.market_data import market_data_service
from app.services.order_manager import order_manager
from app.services.risk_manager import risk_manager
from app.strategies.ov_position_manager import ov_position_manager


class OrderRequest(BaseModel):
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    order_type: str = 'market'  # 'market', 'limit', 'stop'
    price: float = None
    stop_price: float = None

router = APIRouter()


@router.get("/status")
async def get_trading_status():
    """Get current trading status."""
    try:
        # Get market status
        market_status = market_data_service.get_market_status()
        
        # Get account summary
        account_summary = portfolio_service.get_account_summary()
        
        # Get cached trading bot status
        bot_status = redis_cache.get("trading_status") or {
            "is_trading": False,
            "started_at": None
        }
        
        status = {
            "is_trading": bot_status.get("is_trading", False),
            "started_at": bot_status.get("started_at"),
            "market_open": market_status.get("is_open", False),
            "positions_count": account_summary.get("positions_count", 0),
            "daily_pnl": account_summary.get("daily_pnl", 0.0),
            "account_equity": account_summary.get("account_equity", 0.0),
            "buying_power": account_summary.get("buying_power", 0.0),
            "timestamp": datetime.now().isoformat()
        }
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trading status: {e}")


@router.get("/positions")
async def get_positions():
    """Get current open positions."""
    try:
        positions = portfolio_service.get_open_positions()
        
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
        watchlist = portfolio_service.get_watchlist()
        
        return {
            "watchlist": watchlist,
            "count": len(watchlist),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get watchlist: {e}")


@router.post("/place-order")
async def place_order(order: OrderRequest):
    """Place a new order."""
    try:
        order_id = None
        
        if order.order_type.lower() == 'market':
            order_id = order_manager.place_market_order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity
            )
        elif order.order_type.lower() == 'limit':
            if not order.price:
                raise HTTPException(status_code=400, detail="Limit price required for limit orders")
            order_id = order_manager.place_limit_order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                limit_price=order.price
            )
        elif order.order_type.lower() == 'stop':
            if not order.stop_price:
                raise HTTPException(status_code=400, detail="Stop price required for stop orders")
            order_id = order_manager.place_stop_loss_order(
                symbol=order.symbol,
                quantity=order.quantity,
                stop_price=order.stop_price
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported order type: {order.order_type}")
        
        if not order_id:
            raise HTTPException(status_code=400, detail="Failed to place order")
        
        return {
            "message": "Order placed successfully",
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "order_type": order.order_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to place order: {e}")


@router.get("/market-data/{symbol}")
async def get_market_data(symbol: str):
    """Get current market data for a symbol."""
    try:
        current_price = market_data_service.get_current_price(symbol.upper())
        
        if current_price is None:
            raise HTTPException(status_code=404, detail=f"No market data found for {symbol}")
        
        # Try to get cached quote data
        quote_data = redis_cache.get(f"quote:{symbol.upper()}")
        
        return {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "bid": quote_data.get("bid") if quote_data else None,
            "ask": quote_data.get("ask") if quote_data else None,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get market data: {e}")


@router.get("/account-summary")
async def get_account_summary():
    """Get complete account summary."""
    try:
        summary = portfolio_service.get_account_summary()
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get account summary: {e}")


@router.get("/calculate-position-size/{symbol}")
async def calculate_position_size(symbol: str, entry_price: float, stop_loss: float, 
                                risk_percentage: float = None):
    """Calculate optimal position size based on risk management."""
    try:
        shares, info = risk_manager.calculate_position_size(
            symbol=symbol.upper(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_percentage=risk_percentage
        )
        
        return {
            "symbol": symbol.upper(),
            "recommended_shares": shares,
            "sizing_info": info,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate position size: {e}")


@router.post("/validate-setup")
async def validate_trade_setup(symbol: str, entry_price: float, stop_loss: float, 
                             target_price: float = None):
    """Validate a trade setup before execution."""
    try:
        validation = risk_manager.validate_trade_setup(
            symbol=symbol.upper(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price
        )
        
        return validation
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate setup: {e}")


@router.get("/pre-trade-check")
async def check_pre_trade_conditions():
    """Check if conditions are suitable for new trades."""
    try:
        conditions = risk_manager.check_pre_trade_conditions()
        return conditions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check conditions: {e}")


@router.get("/ov-positions")
async def get_ov_managed_positions():
    """Get all Oliver Velez managed positions with detailed status."""
    try:
        managed_positions = ov_position_manager.get_all_managed_positions()
        
        return {
            "managed_positions": managed_positions,
            "count": len(managed_positions),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get OV positions: {e}")


@router.get("/ov-positions/{symbol}")
async def get_ov_position_detail(symbol: str):
    """Get detailed status of a specific OV managed position."""
    try:
        position_status = ov_position_manager.get_position_status(symbol.upper())
        return position_status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get OV position for {symbol}: {e}")


@router.post("/ov-positions/{symbol}/force-close")
async def force_close_ov_position(symbol: str):
    """Force close an OV managed position."""
    try:
        result = await ov_position_manager.force_close_position(symbol.upper(), "manual_close")
        
        if result and "error" not in result:
            return {
                "message": f"Successfully force closed position for {symbol}",
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to close position"))
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to force close position: {e}")


@router.post("/risk-management/daily-cleanup")
async def execute_daily_risk_cleanup():
    """Execute end-of-day risk management cleanup."""
    try:
        # Close all OV managed positions
        ov_cleanup = await ov_position_manager.end_of_day_cleanup()
        
        # Check risk limits one final time
        risk_check = risk_manager.monitor_positions_risk()
        
        return {
            "cleanup_summary": {
                "ov_positions_closed": len(ov_cleanup),
                "positions_closed": ov_cleanup,
                "risk_alerts": risk_check.get("risk_alerts", []),
                "cleanup_time": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute daily cleanup: {e}")