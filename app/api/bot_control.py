"""
Bot control API endpoints for managing the trading bot.
"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from datetime import datetime

from app.services.trading_bot import trading_bot

logger = logging.getLogger(__name__)
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
    """
    Get currently active positions from Trading API.

    Uses: Alpaca Trading API list_positions()
    """
    try:
        from app.services.order_manager import order_manager

        # Get real positions from Trading API
        api_positions = order_manager.get_open_positions()

        positions = {}

        for pos in api_positions:
            symbol = pos.get('symbol')
            qty = pos.get('quantity', 0)
            side = pos.get('side', 'long')

            # Get additional data from bot tracking if available
            bot_position_data = trading_bot.active_positions.get(symbol, {})

            positions[symbol] = {
                'symbol': symbol,
                'quantity': abs(qty),
                'side': side,
                'entry_price': pos.get('avg_entry_price', 0),
                'current_price': pos.get('current_price', 0),
                'market_value': pos.get('market_value', 0),
                'unrealized_pl': pos.get('unrealized_pnl', 0),
                'unrealized_plpc': pos.get('unrealized_pnl_percent', 0),  # Percent
                'cost_basis': pos.get('cost_basis', 0),
                # From bot tracking (if available)
                'stop_loss': bot_position_data.get('stop_loss'),
                'target_1': bot_position_data.get('target_price'),
                'entry_time': bot_position_data.get('entry_time').isoformat() if bot_position_data.get('entry_time') else None,
                'partial_profit_taken': bot_position_data.get('partial_profit_taken', False)
            }

        return {
            "active_positions": positions,
            "position_count": len(positions),
            "data_source": "trading_api",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting active positions: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        # Use REAL market data service instead of mock
        from app.services.market_data import market_data_service
        
        if not trading_bot.current_watchlist:
            return {
                "watchlist": {},
                "count": 0,
                "summary": {"error": "No watchlist symbols configured"},
                "timestamp": datetime.now().isoformat()
            }
        
        # Get COMPREHENSIVE market data for each symbol
        watchlist_data = {}
        for symbol in trading_bot.current_watchlist:
            try:
                # Get comprehensive quote data with OHLC
                quote_data = market_data_service.get_quote(symbol)
                if quote_data:
                    watchlist_data[symbol] = {
                        "symbol": symbol,
                        "current_price": quote_data.get('price', 0),
                        "previous_close": quote_data.get('previous_close', 0),
                        "today_open": quote_data.get('today_open', 0),
                        "premarket_price": quote_data.get('premarket_price', 0),
                        "bid": quote_data.get('bid', 0),
                        "ask": quote_data.get('ask', 0),
                        "volume": quote_data.get('volume', 0),
                        "gap_amount": quote_data.get('gap_amount', 0),
                        "gap_percent": quote_data.get('gap_percent', 0),
                        "premarket_gap": quote_data.get('premarket_gap', 0),
                        "premarket_gap_percent": quote_data.get('premarket_gap_percent', 0),
                        "gap_from_open": quote_data.get('gap_from_open', 0),
                        "gap_open_percent": quote_data.get('gap_open_percent', 0),
                        "timestamp": quote_data.get('timestamp', datetime.now().isoformat()),
                        "data_source": "real_alpaca_ohlc_premarket_data"
                    }
                else:
                    watchlist_data[symbol] = {
                        "symbol": symbol,
                        "error": "No market data available",
                        "data_source": "alpaca_api_error"
                    }
            except Exception as e:
                watchlist_data[symbol] = {
                    "symbol": symbol,
                    "error": str(e),
                    "data_source": "api_exception"
                }
        
        summary_data = {
            "total_symbols": len(watchlist_data),
            "symbols_with_data": len([s for s in watchlist_data.values() if "error" not in s]),
            "data_source": "real_alpaca_api",
            "last_updated": datetime.now().isoformat()
        }
        
        return {
            "watchlist": watchlist_data,
            "count": len(watchlist_data),
            "summary": summary_data,
            "symbols": trading_bot.current_watchlist,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get real watchlist data: {e}")


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
    """
    Close a specific position using Trading API.

    Uses: Alpaca Trading API to place offsetting market order
    """
    try:
        from app.services.order_manager import order_manager

        # First get the position data from Trading API
        position = order_manager.get_position(symbol)

        if not position:
            raise HTTPException(status_code=404, detail=f"No open position found for {symbol}")

        # Log position details before closing
        qty = position.get('quantity', 0)
        market_value = position.get('market_value', 0)
        current_price = position.get('current_price', 0)
        unrealized_pl = position.get('unrealized_pnl', 0)

        logger.info(f"Closing position: {symbol}")
        logger.info(f"  Quantity: {qty}")
        logger.info(f"  Current Price: ${current_price:.2f}")
        logger.info(f"  Market Value: ${market_value:.2f}")
        logger.info(f"  Unrealized P/L: ${unrealized_pl:.2f}")

        # Close the position using Trading API
        success = order_manager.close_position(symbol)

        if success:
            # Remove from active positions tracking
            if symbol in trading_bot.active_positions:
                del trading_bot.active_positions[symbol]

            return {
                "status": "position_closed",
                "symbol": symbol,
                "quantity": qty,
                "market_value": market_value,
                "unrealized_pl": unrealized_pl,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to close position via Trading API")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in close_single_position: {e}")
        import traceback
        logger.error(traceback.format_exc())
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


@router.get("/strategy/info")
async def get_strategy_info():
    """Get information about active trading strategy."""
    try:
        strategy_info = trading_bot.get_strategy_info()
        return {
            **strategy_info,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy info: {e}")


@router.post("/strategy/switch/{strategy_name}")
async def switch_strategy(strategy_name: str):
    """
    Switch between trading strategies.

    Args:
        strategy_name: Strategy to switch to ("proprietary" or "velez")
    """
    try:
        result = await trading_bot.switch_strategy(strategy_name)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))

        return {
            **result,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to switch strategy: {e}")