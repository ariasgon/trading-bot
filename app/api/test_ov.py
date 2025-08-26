"""
Test endpoint for Oliver Velez analysis and position management.
This creates simulated OV analysis logs and managed positions for dashboard testing.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
import asyncio

router = APIRouter()


@router.post("/simulate-ov-analysis/{symbol}")
async def simulate_ov_analysis(symbol: str):
    """Simulate Oliver Velez analysis for a symbol."""
    try:
        from app.services.analysis_logger import analysis_logger
        from app.strategies.ov_position_manager import ov_position_manager
        
        # Simulate OV analysis results
        simulated_ov_results = {
            'symbol': symbol.upper(),
            'total_candles': 100,
            'max_score': 7.5,
            'strongest_signals': [
                {
                    'index': 98,
                    'composite_score': 7.5,
                    'candle': {
                        'open': 100.50,
                        'high': 101.20,
                        'low': 100.10,
                        'close': 100.85,
                        'range': 1.10,
                        'body': 0.35
                    },
                    'bt_tt': {
                        'is_bt': True,
                        'is_tt': False,
                        'bt_strength': 0.68,
                        'pattern_quality': 'strong'
                    },
                    'elephant': {
                        'is_elephant': True,
                        'type': 'ignition',
                        'interpretation': 'continuation_signal',
                        'range_multiple': 2.1
                    },
                    'reversal_3_5': {
                        'is_reversal': False
                    },
                    'nrb_nbb': {
                        'is_nrb': False,
                        'is_nbb': False,
                        'breakout_probability': 'medium'
                    },
                    'lost_control': {
                        'has_lost_control': False
                    }
                },
                {
                    'index': 99,
                    'composite_score': 6.2,
                    'candle': {
                        'open': 100.85,
                        'high': 101.05,
                        'low': 100.60,
                        'close': 100.95,
                        'range': 0.45,
                        'body': 0.10
                    },
                    'bt_tt': {
                        'is_bt': False,
                        'is_tt': False
                    },
                    'elephant': {
                        'is_elephant': False
                    },
                    'reversal_3_5': {
                        'is_reversal': True,
                        'consecutive_count': 4,
                        'reversal_direction': 'bullish',
                        'reversal_signals': ['bt_tt_pattern', 'compression'],
                        'signal_strength': 2
                    },
                    'nrb_nbb': {
                        'is_nrb': True,
                        'is_nbb': True,
                        'breakout_probability': 'high',
                        'compression_quality': 'high'
                    },
                    'lost_control': {
                        'has_lost_control': True,
                        'body_erase_ratio': 0.72,
                        'flip_strength': 'strong'
                    }
                }
            ]
        }
        
        # Log the analysis
        analysis_logger.log_ov_analysis(symbol.upper(), simulated_ov_results)
        
        # Also log a simulated trade entry
        analysis_logger.log_trade_entry(
            symbol=symbol.upper(),
            entry_price=100.95,
            shares=100,
            setup_reasons=['OV Bottom Tail (BT) reversal', 'OV Elephant (ignition)', 'Gap up detected', 'High volume confirmation']
        )
        
        return {
            "message": f"Simulated OV analysis for {symbol.upper()}",
            "analysis": simulated_ov_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}")


@router.post("/simulate-ov-position/{symbol}")
async def simulate_ov_position(symbol: str):
    """Create a simulated OV managed position."""
    try:
        from app.strategies.ov_position_manager import ov_position_manager
        
        # Create managed position
        managed_id = await ov_position_manager.create_managed_position(
            symbol=symbol.upper(),
            entry_price=100.95,
            stop_loss=98.50,
            quantity=100,
            risk_reward_ratios=(1.5, 2.5, 4.0)
        )
        
        from app.services.analysis_logger import analysis_logger
        
        # Simulate some position management actions
        analysis_logger.log_position_update(
            symbol=symbol.upper(),
            action="trailing_stop_update",
            details={
                "old_stop": 98.50,
                "new_stop": 99.20,
                "old_level": "initial",
                "new_level": "breakeven",
                "bars_in_favor": 2
            }
        )
        
        return {
            "message": f"Created simulated OV managed position for {symbol.upper()}",
            "managed_position_id": managed_id,
            "entry_price": 100.95,
            "stop_loss": 98.50,
            "quantity": 100,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Position simulation failed: {e}")


@router.post("/simulate-scale-out/{symbol}")
async def simulate_scale_out(symbol: str):
    """Simulate scale-out actions for an OV position."""
    try:
        from app.services.analysis_logger import analysis_logger
        
        # Simulate T1 scale-out
        analysis_logger.log_position_update(
            symbol=symbol.upper(),
            action="scale_out_t1",
            details={
                "sale_price": 104.65,
                "shares_sold": 30,
                "percentage": "30%"
            }
        )
        
        # Wait a bit then simulate T2
        await asyncio.sleep(1)
        
        analysis_logger.log_position_update(
            symbol=symbol.upper(),
            action="scale_out_t2", 
            details={
                "sale_price": 107.85,
                "shares_sold": 40,
                "percentage": "40%"
            }
        )
        
        # Update trailing stop to MA-based
        analysis_logger.log_position_update(
            symbol=symbol.upper(),
            action="trailing_stop_update",
            details={
                "old_stop": 102.50,
                "new_stop": 105.20,
                "old_level": "bar_by_bar", 
                "new_level": "ma_20_trail",
                "bars_in_favor": 8
            }
        )
        
        return {
            "message": f"Simulated scale-out sequence for {symbol.upper()}",
            "t1_executed": True,
            "t2_executed": True,
            "runner_remaining": 30,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scale-out simulation failed: {e}")


@router.delete("/clear-ov-test-data")
async def clear_ov_test_data():
    """Clear all test OV data."""
    try:
        from app.services.analysis_logger import analysis_logger
        from app.strategies.ov_position_manager import ov_position_manager
        
        # Clear analysis logs
        analysis_logger.clear_logs()
        
        # Close all managed positions
        await ov_position_manager.end_of_day_cleanup()
        
        return {
            "message": "All OV test data cleared",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clear failed: {e}")


@router.get("/ov-dashboard-summary")
async def get_ov_dashboard_summary():
    """Get comprehensive OV data for dashboard."""
    try:
        from app.services.analysis_logger import analysis_logger
        from app.strategies.ov_position_manager import ov_position_manager
        
        # Get logs and positions
        logs_data = analysis_logger.get_logs(limit=50)
        positions_data = ov_position_manager.get_all_managed_positions()
        
        return {
            "analysis_logs": logs_data,
            "managed_positions": positions_data,
            "summary": {
                "total_logs": len(logs_data.get('logs', [])),
                "total_positions": len(positions_data),
                "last_analysis": logs_data.get('last_analysis'),
                "active_symbols": list(positions_data.keys())
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard summary failed: {e}")