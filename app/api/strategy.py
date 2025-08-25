"""
Trading strategy API endpoints.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from pydantic import BaseModel

from app.core.database import get_db
from app.strategies.velez_strategy import velez_strategy
from app.strategies.indicators import VelezSignalGenerator
from app.services.portfolio import portfolio_service
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class StrategyControlRequest(BaseModel):
    action: str  # 'start', 'stop', 'restart'


class SymbolAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str = '1d'
    interval: str = '5m'


class WatchlistScanRequest(BaseModel):
    symbols: Optional[List[str]] = None  # If None, use default watchlist


router = APIRouter()


@router.get("/status")
async def get_strategy_status():
    """Get current strategy status and active setups."""
    try:
        status = velez_strategy.get_strategy_status()
        
        return {
            "strategy_name": "Oliver Velez Gap Pullback Strategy",
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy status: {e}")


@router.post("/control")
async def control_strategy(request: StrategyControlRequest, background_tasks: BackgroundTasks):
    """Control strategy execution (start/stop/restart)."""
    try:
        action = request.action.lower()
        
        if action == 'start':
            if velez_strategy.is_active:
                return {"message": "Strategy is already active"}
            
            # Initialize strategy in background
            background_tasks.add_task(velez_strategy.initialize_strategy)
            return {"message": "Strategy initialization started"}
            
        elif action == 'stop':
            if not velez_strategy.is_active:
                return {"message": "Strategy is already stopped"}
            
            # Shutdown strategy in background
            background_tasks.add_task(velez_strategy.shutdown_strategy)
            return {"message": "Strategy shutdown initiated"}
            
        elif action == 'restart':
            # Restart strategy in background
            background_tasks.add_task(_restart_strategy)
            return {"message": "Strategy restart initiated"}
            
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to control strategy: {e}")


@router.get("/pre-market-scan")
async def run_pre_market_scan():
    """Run pre-market gap scan for trading opportunities."""
    try:
        if not velez_strategy.is_active:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        # Run pre-market scan
        candidates = await velez_strategy.run_pre_market_scan()
        
        # Format results
        results = []
        for setup in candidates[:10]:  # Limit to top 10
            results.append({
                "symbol": setup.symbol,
                "signal_type": setup.signal_type,
                "signal_strength": setup.signal_strength,
                "confidence_score": setup.confidence_score,
                "entry_price": setup.entry_price,
                "stop_loss": setup.stop_loss,
                "target_price": setup.target_price,
                "risk_reward_ratio": setup.risk_reward_ratio,
                "setup_reasons": setup.setup_reasons,
                "timestamp": setup.timestamp.isoformat()
            })
        
        return {
            "scan_time": datetime.now().isoformat(),
            "candidates_found": len(candidates),
            "top_candidates": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run pre-market scan: {e}")


@router.get("/active-setups")
async def get_active_setups():
    """Get currently active trade setups being monitored."""
    try:
        active_setups = []
        
        for symbol, setup in velez_strategy.active_setups.items():
            active_setups.append({
                "symbol": setup.symbol,
                "signal_type": setup.signal_type,
                "signal_strength": setup.signal_strength,
                "confidence_score": setup.confidence_score,
                "entry_price": setup.entry_price,
                "stop_loss": setup.stop_loss,
                "target_price": setup.target_price,
                "risk_reward_ratio": setup.risk_reward_ratio,
                "setup_reasons": setup.setup_reasons,
                "created_at": setup.timestamp.isoformat()
            })
        
        return {
            "active_setups_count": len(active_setups),
            "setups": active_setups,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get active setups: {e}")


@router.post("/monitor-setups")
async def monitor_active_setups():
    """Monitor active setups and return actionable signals."""
    try:
        if not velez_strategy.is_active:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        # Monitor setups for entry signals
        signals = await velez_strategy.monitor_active_setups()
        
        # Format signals
        actionable_signals = []
        for signal in signals:
            setup = signal['setup']
            entry_signal = signal['entry_signal']
            
            actionable_signals.append({
                "symbol": setup.symbol,
                "action": signal['action'],
                "setup_info": {
                    "entry_price": setup.entry_price,
                    "stop_loss": setup.stop_loss,
                    "target_price": setup.target_price,
                    "confidence_score": setup.confidence_score
                },
                "entry_conditions": {
                    "current_price": entry_signal.get('current_price'),
                    "vwap_level": entry_signal.get('vwap_level'),
                    "near_vwap": entry_signal.get('near_vwap'),
                    "bullish_reversal": entry_signal.get('bullish_reversal'),
                    "volume_confirmation": entry_signal.get('volume_confirmation')
                },
                "should_enter": entry_signal.get('should_enter', False)
            })
        
        return {
            "monitoring_time": datetime.now().isoformat(),
            "signals_found": len(actionable_signals),
            "actionable_signals": actionable_signals
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to monitor setups: {e}")


@router.post("/execute-signal")
async def execute_trade_signal(symbol: str, background_tasks: BackgroundTasks):
    """Execute a trade signal for a specific symbol."""
    try:
        if not velez_strategy.is_active:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        # Check if symbol has an active setup
        if symbol not in velez_strategy.active_setups:
            raise HTTPException(status_code=404, detail=f"No active setup found for {symbol}")
        
        # Get the setup and create a signal
        setup = velez_strategy.active_setups[symbol]
        
        # Monitor the specific setup to get current entry signal
        df = await velez_strategy._get_market_data(symbol, period='1d', interval='1m')
        if df is None or df.empty:
            raise HTTPException(status_code=400, detail=f"No market data available for {symbol}")
        
        entry_signal = await velez_strategy._check_entry_conditions(setup, df)
        
        if not entry_signal.get('should_enter', False):
            raise HTTPException(
                status_code=400, 
                detail=f"Entry conditions not met for {symbol}: {entry_signal}"
            )
        
        # Create signal object
        signal = {
            'setup': setup,
            'entry_signal': entry_signal,
            'action': 'enter_trade'
        }
        
        # Execute trade in background
        background_tasks.add_task(_execute_trade_signal, signal)
        
        return {
            "message": f"Trade execution initiated for {symbol}",
            "symbol": symbol,
            "entry_price": setup.entry_price,
            "stop_loss": setup.stop_loss,
            "target_price": setup.target_price,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute trade signal: {e}")


@router.post("/analyze-symbol")
async def analyze_symbol(request: SymbolAnalysisRequest):
    """Get detailed technical analysis for a specific symbol."""
    try:
        symbol = request.symbol.upper()
        
        # Get market data
        df = market_data_service.get_historical_data(
            symbol, 
            period=request.timeframe, 
            interval=request.interval
        )
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No market data found for {symbol}")
        
        # Run analysis
        signal_generator = VelezSignalGenerator()
        analysis = signal_generator.analyze_stock(df, symbol)
        
        if 'error' in analysis:
            raise HTTPException(status_code=400, detail=analysis['error'])
        
        return {
            "analysis_time": datetime.now().isoformat(),
            "analysis": analysis
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze symbol: {e}")


@router.post("/scan-watchlist")
async def scan_watchlist(request: WatchlistScanRequest = None):
    """Scan watchlist for trading opportunities."""
    try:
        # Get symbols to scan
        if request and request.symbols:
            symbols = request.symbols
        else:
            symbols = portfolio_service.get_watchlist()
        
        if not symbols:
            raise HTTPException(status_code=400, detail="No symbols to scan")
        
        # Initialize signal generator
        signal_generator = VelezSignalGenerator()
        
        # Scan symbols
        results = signal_generator.scan_watchlist(
            symbols, 
            lambda symbol: market_data_service.get_historical_data(symbol, '1d', '5m')
        )
        
        # Filter and format results
        opportunities = []
        for result in results:
            if result.get('signal_strength', 0) > 0:
                opportunities.append({
                    "symbol": result['symbol'],
                    "signal": result.get('signal', 'none'),
                    "signal_strength": result.get('signal_strength', 0),
                    "current_price": result.get('current_price', 0),
                    "entry_price": result.get('entry_price', 0),
                    "stop_loss": result.get('stop_loss', 0),
                    "target_price": result.get('target_price', 0),
                    "risk_reward_ratio": result.get('risk_reward_ratio', 0),
                    "vwap": result.get('vwap', 0),
                    "rsi": result.get('rsi', 0),
                    "gap_percent": result.get('gap_percent', 0),
                    "trend_alignment": result.get('trend_alignment', 'neutral'),
                    "reversal_patterns": result.get('reversal_patterns', {}),
                    "volume_analysis": result.get('volume_analysis', {})
                })
        
        return {
            "scan_time": datetime.now().isoformat(),
            "symbols_scanned": len(symbols),
            "opportunities_found": len(opportunities),
            "opportunities": opportunities
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan watchlist: {e}")


@router.post("/manage-positions")
async def manage_open_positions():
    """Manage open positions for exits and trailing stops."""
    try:
        if not velez_strategy.is_active:
            raise HTTPException(status_code=400, detail="Strategy is not active")
        
        # Manage positions
        actions = await velez_strategy.manage_open_positions()
        
        return {
            "management_time": datetime.now().isoformat(),
            "actions_taken": len(actions),
            "actions": actions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to manage positions: {e}")


@router.get("/strategy-performance")
async def get_strategy_performance(days: int = 30):
    """Get strategy performance metrics."""
    try:
        # Get overall performance
        performance = portfolio_service.get_performance_summary(days=days)
        
        # Get strategy-specific metrics
        strategy_status = velez_strategy.get_strategy_status()
        
        return {
            "performance_period": days,
            "overall_performance": performance,
            "strategy_metrics": {
                "daily_trades_count": strategy_status.get('daily_trades_count', 0),
                "max_daily_trades": strategy_status.get('max_daily_trades', 0),
                "active_setups_count": strategy_status.get('active_setups_count', 0),
                "is_active": strategy_status.get('is_active', False)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy performance: {e}")


# Background task functions
async def _restart_strategy():
    """Background task to restart strategy."""
    try:
        await velez_strategy.shutdown_strategy()
        await velez_strategy.initialize_strategy()
    except Exception as e:
        logger.error(f"Error restarting strategy: {e}")


async def _execute_trade_signal(signal: Dict[str, Any]):
    """Background task to execute trade signal."""
    try:
        trade_id = await velez_strategy.execute_trade_signal(signal)
        if trade_id:
            logger.info(f"Successfully executed trade signal, trade ID: {trade_id}")
        else:
            logger.warning("Failed to execute trade signal")
    except Exception as e:
        logger.error(f"Error executing trade signal: {e}")