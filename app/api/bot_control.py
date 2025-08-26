"""
Bot control API endpoints for managing the trading bot.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from datetime import datetime

from app.services.trading_bot import trading_bot

router = APIRouter()


@router.post("/start")
async def start_bot(background_tasks: BackgroundTasks):
    """Start the trading bot."""
    try:
        if trading_bot.is_running:
            return {
                "status": "already_running",
                "message": "Trading bot is already running",
                "timestamp": datetime.now().isoformat()
            }
        
        # Start bot in background
        background_tasks.add_task(trading_bot.start_bot)
        
        return {
            "status": "starting",
            "message": "Trading bot is starting...",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e}")


@router.post("/stop")
async def stop_bot():
    """Stop the trading bot."""
    try:
        if not trading_bot.is_running:
            return {
                "status": "not_running",
                "message": "Trading bot is not running",
                "timestamp": datetime.now().isoformat()
            }
        
        await trading_bot.stop_bot()
        
        return {
            "status": "stopped",
            "message": "Trading bot stopped successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {e}")


@router.get("/status")
async def get_bot_status():
    """Get current bot status."""
    try:
        status = trading_bot.get_status()
        
        return {
            "bot_status": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@router.post("/pause")
async def pause_trading():
    """Pause active trading but keep monitoring."""
    try:
        if not trading_bot.is_running:
            return {
                "status": "not_running",
                "message": "Trading bot is not running"
            }
        
        trading_bot.is_trading_active = False
        
        return {
            "status": "paused",
            "message": "Trading paused - monitoring continues",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause trading: {e}")


@router.post("/resume")
async def resume_trading():
    """Resume active trading."""
    try:
        if not trading_bot.is_running:
            return {
                "status": "not_running",
                "message": "Trading bot is not running"
            }
        
        # Check if we should be trading now
        from app.strategies.velez_strategy import velez_strategy, MarketSession
        current_session = velez_strategy._get_market_session()
        
        if current_session != MarketSession.REGULAR_HOURS:
            return {
                "status": "cannot_resume",
                "message": f"Cannot resume: Market is {current_session.value}",
                "timestamp": datetime.now().isoformat()
            }
        
        trading_bot.is_trading_active = True
        
        return {
            "status": "resumed",
            "message": "Trading resumed",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume trading: {e}")


@router.post("/emergency-stop")
async def emergency_stop():
    """Emergency stop - close all positions and stop bot."""
    try:
        await trading_bot._emergency_close_all_positions()
        await trading_bot.stop_bot()
        
        return {
            "status": "emergency_stopped",
            "message": "Emergency stop executed - all positions closed",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emergency stop failed: {e}")


@router.get("/active-positions")
async def get_active_positions():
    """Get currently active positions."""
    try:
        positions = {}
        
        for symbol, position_data in trading_bot.active_positions.items():
            positions[symbol] = {
                'entry_price': position_data['entry_price'],
                'stop_loss': position_data['stop_loss'],
                'target_1': position_data['target_price'],
                'quantity': position_data.get('position_size', 0),
                'side': 'buy',  # Default to buy since we're only doing longs in Velez strategy
                'entry_time': position_data['entry_time'].isoformat(),
                'partial_profit_taken': position_data.get('partial_profit_taken', False)
            }
        
        return {
            "active_positions": positions,
            "position_count": len(positions),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {e}")


@router.get("/daily-stats")
async def get_daily_stats():
    """Get daily trading statistics."""
    try:
        stats = trading_bot.daily_stats.copy()
        
        # Add current session info
        stats.update({
            'current_trades_today': trading_bot.trades_today,
            'current_error_count': trading_bot.error_count,
            'session_duration': trading_bot._calculate_session_duration()
        })
        
        return {
            "daily_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get daily stats: {e}")


@router.get("/watchlist")
async def get_current_watchlist():
    """Get current trading watchlist."""
    try:
        # Use mock market data service for enhanced watchlist display
        from app.services.mock_enhanced_market_data import mock_enhanced_market_data
        
        if not trading_bot.current_watchlist:
            return {
                "watchlist": {},
                "count": 0,
                "summary": {"error": "No watchlist symbols configured"},
                "timestamp": datetime.now().isoformat()
            }
        
        # Get enhanced market data using mock service
        enhanced_data = await mock_enhanced_market_data.get_enhanced_watchlist_data(trading_bot.current_watchlist)
        summary_data = await mock_enhanced_market_data.get_watchlist_summary(trading_bot.current_watchlist)
        
        return {
            "watchlist": enhanced_data,
            "count": len(enhanced_data),
            "summary": summary_data,
            "symbols": trading_bot.current_watchlist,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get enhanced watchlist: {e}")


@router.post("/force-scan")
async def force_premarket_scan():
    """Force run pre-market scan."""
    try:
        await trading_bot._smart_premarket_scan()
        
        return {
            "status": "scan_completed",
            "watchlist": trading_bot.current_watchlist,
            "count": len(trading_bot.current_watchlist),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forced scan failed: {e}")


@router.post("/historical-analysis")
async def force_historical_analysis():
    """Force historical analysis for missed pre-market."""
    try:
        candidates = await trading_bot._run_historical_analysis()
        
        return {
            "status": "historical_analysis_completed",
            "candidates_found": len(candidates) if candidates else 0,
            "watchlist": trading_bot.current_watchlist,
            "count": len(trading_bot.current_watchlist),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run historical analysis: {e}")


@router.post("/activate-trading")
async def activate_trading_session():
    """Manually activate trading session."""
    try:
        await trading_bot._start_trading_session()
        
        return {
            "status": "trading_activated",
            "message": "Trading session activated manually",
            "is_trading_active": trading_bot.is_trading_active,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to activate trading: {e}")


@router.post("/close-position/{symbol}")
async def close_single_position(symbol: str):
    """Close a specific position."""
    try:
        if symbol not in trading_bot.active_positions:
            raise HTTPException(status_code=404, detail=f"No active position found for {symbol}")
        
        position_data = trading_bot.active_positions[symbol]
        
        # Close the position using portfolio service
        from app.services.portfolio import portfolio_service
        from app.services.order_manager import order_manager
        
        # Get position details from portfolio service
        open_positions = portfolio_service.get_open_positions()
        target_position = None
        
        for pos in open_positions:
            if pos['symbol'] == symbol:
                target_position = pos
                break
        
        if target_position:
            quantity = abs(target_position['quantity'])
            side = 'sell' if target_position['quantity'] > 0 else 'buy'
            
            order_id = order_manager.place_market_order(symbol, side, quantity)
            
            if order_id:
                # Remove from active positions
                del trading_bot.active_positions[symbol]
                
                return {
                    "status": "position_closed",
                    "symbol": symbol,
                    "order_id": order_id,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to place closing order")
        else:
            raise HTTPException(status_code=404, detail=f"No open position found for {symbol}")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to close position: {e}")


@router.get("/analysis-logs")
async def get_analysis_logs():
    """Get recent trading analysis logs."""
    try:
        from app.services.analysis_logger import analysis_logger
        logs_data = analysis_logger.get_logs()
        return logs_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analysis logs: {e}")


@router.delete("/analysis-logs")
async def clear_analysis_logs():
    """Clear analysis logs."""
    try:
        from app.services.analysis_logger import analysis_logger
        success = analysis_logger.clear_logs()
        
        if success:
            return {
                "status": "cleared",
                "message": "Analysis logs cleared successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clear logs")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear analysis logs: {e}")


@router.post("/force-analysis")
async def force_analysis():
    """Force analysis of current watchlist."""
    try:
        if not trading_bot.is_running:
            raise HTTPException(status_code=400, detail="Bot is not running")
        
        if not trading_bot.current_watchlist:
            raise HTTPException(status_code=400, detail="No symbols in watchlist")
        
        # Force analysis on current watchlist
        analysis_results = await trading_bot._force_watchlist_analysis()
        
        return {
            "status": "analysis_completed",
            "symbols_analyzed": len(trading_bot.current_watchlist),
            "setups_found": analysis_results.get("setups_found", 0),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to force analysis: {e}")