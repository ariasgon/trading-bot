"""
Analysis Logger Service for Trading Bot Dashboard.

Provides comprehensive logging of trading analysis, OV signals, and position management
for display on the dashboard.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import deque
import json

from app.core.cache import redis_cache
from app.strategies.ov_core_signals import OVCoreSignals
from app.strategies.ov_position_manager import ov_position_manager

logger = logging.getLogger(__name__)


class AnalysisLogger:
    """Centralized analysis logging for dashboard display."""
    
    def __init__(self, max_logs: int = 100):
        self.max_logs = max_logs
        self.ov_signals = OVCoreSignals()
        self.analysis_logs = deque(maxlen=max_logs)
        self.last_analysis_time = None
        
    def log_ov_analysis(self, symbol: str, ov_results: Dict[str, Any]) -> None:
        """Log Oliver Velez analysis results."""
        try:
            timestamp = datetime.now()
            
            if 'error' in ov_results:
                self._add_log('error', f"OV Analysis failed: {ov_results['error']}", symbol, timestamp)
                return
            
            max_score = ov_results.get('max_score', 0)
            strongest_signals = ov_results.get('strongest_signals', [])
            
            # Log overall analysis
            if max_score > 5:
                self._add_log('success', f"Strong OV signals detected (score: {max_score:.1f})", symbol, timestamp)
            elif max_score > 2:
                self._add_log('warning', f"Moderate OV signals (score: {max_score:.1f})", symbol, timestamp)
            else:
                self._add_log('info', f"Weak OV signals (score: {max_score:.1f})", symbol, timestamp)
            
            # Log specific signal details
            for signal in strongest_signals[:2]:  # Top 2 signals
                score = signal.get('composite_score', 0)
                candle_data = signal.get('candle', {})
                
                signal_details = []
                
                # BT/TT patterns
                bt_tt = signal.get('bt_tt', {})
                if bt_tt.get('is_bt'):
                    strength = bt_tt.get('bt_strength', 0)
                    signal_details.append(f"BT ({strength:.0%})")
                if bt_tt.get('is_tt'):
                    strength = bt_tt.get('tt_strength', 0)
                    signal_details.append(f"TT ({strength:.0%})")
                
                # Elephant patterns
                elephant = signal.get('elephant', {})
                if elephant.get('is_elephant'):
                    elephant_type = elephant.get('type', 'unknown')
                    signal_details.append(f"Elephant ({elephant_type})")
                
                # Reversal patterns
                reversal = signal.get('reversal_3_5', {})
                if reversal.get('is_reversal'):
                    count = reversal.get('consecutive_count', 0)
                    direction = reversal.get('reversal_direction', 'unknown')
                    signal_details.append(f"{count}-bar {direction} reversal")
                
                # NRB/NBB
                nrb_nbb = signal.get('nrb_nbb', {})
                if nrb_nbb.get('breakout_probability') == 'high':
                    compression = nrb_nbb.get('compression_quality', 'unknown')
                    signal_details.append(f"NRB/NBB {compression} compression")
                
                # Lost control
                lost_control = signal.get('lost_control', {})
                if lost_control.get('has_lost_control'):
                    flip_strength = lost_control.get('flip_strength', 'unknown')
                    signal_details.append(f"Lost control ({flip_strength})")
                
                if signal_details:
                    price = candle_data.get('close', 0)
                    details_str = ', '.join(signal_details)
                    self._add_log('setup', f"${price:.2f}: {details_str} [Score: {score:.1f}]", symbol, timestamp)
            
            self.last_analysis_time = timestamp
            
        except Exception as e:
            logger.error(f"Error logging OV analysis: {e}")
            self._add_log('error', f"Logging error: {str(e)}", symbol, datetime.now())
    
    def log_position_update(self, symbol: str, action: str, details: Dict[str, Any]) -> None:
        """Log position management actions."""
        try:
            timestamp = datetime.now()
            
            if action == "scale_out_t1":
                price = details.get('sale_price', 0)
                shares = details.get('shares_sold', 0)
                self._add_log('success', f"T1 Scale-out: {shares} shares @ ${price:.2f} (30%)", symbol, timestamp)
                
            elif action == "scale_out_t2":
                price = details.get('sale_price', 0)
                shares = details.get('shares_sold', 0)
                self._add_log('success', f"T2 Scale-out: {shares} shares @ ${price:.2f} (40%)", symbol, timestamp)
                
            elif action == "trailing_stop_update":
                old_level = details.get('old_level', '')
                new_level = details.get('new_level', '')
                new_stop = details.get('new_stop', 0)
                bars_in_favor = details.get('bars_in_favor', 0)
                self._add_log('info', f"Trailing stop: {old_level} → {new_level} @ ${new_stop:.2f} ({bars_in_favor} bars)", symbol, timestamp)
                
            elif action == "stop_loss_exit":
                price = details.get('exit_price', 0)
                shares = details.get('shares_sold', 0)
                trailing_level = details.get('trailing_level', 'unknown')
                self._add_log('warning', f"Stop hit: {shares} shares @ ${price:.2f} ({trailing_level})", symbol, timestamp)
                
            elif action == "force_close":
                price = details.get('exit_price', 0)
                shares = details.get('shares_sold', 0)
                reason = details.get('reason', 'manual')
                self._add_log('info', f"Position closed: {shares} shares @ ${price:.2f} ({reason})", symbol, timestamp)
                
        except Exception as e:
            logger.error(f"Error logging position update: {e}")
    
    def log_trade_entry(self, symbol: str, entry_price: float, shares: int, setup_reasons: List[str], protective_orders: Dict[str, Any] = None) -> None:
        """Log new trade entry with protective orders information."""
        try:
            timestamp = datetime.now()
            reasons_str = ', '.join(setup_reasons[:3])  # Top 3 reasons
            
            # Basic entry log
            entry_msg = f"ENTRY: {shares} shares @ ${entry_price:.2f} - {reasons_str}"
            
            # Add protective orders status
            if protective_orders:
                orders_placed = protective_orders.get('orders_placed', 0)
                if orders_placed > 0:
                    entry_msg += f" [🛡️ {orders_placed} protective orders placed]"
                    
                    # Log stop loss order specifically
                    if protective_orders.get('stop_loss_order_id'):
                        self._add_log('success', f"🛡️ Stop-Loss order active at Alpaca (Order: {protective_orders['stop_loss_order_id'][:8]}...)", symbol, timestamp)
                    
                    # Log take profit order
                    if protective_orders.get('take_profit_t1_order_id'):
                        self._add_log('success', f"🎯 Take-Profit T1 order active at Alpaca", symbol, timestamp)
                else:
                    entry_msg += f" [⚠️ NO protective orders placed]"
                    self._add_log('warning', f"⚠️ RISK: Position has NO protective orders at broker level", symbol, timestamp)
            
            self._add_log('success', entry_msg, symbol, timestamp)
            
        except Exception as e:
            logger.error(f"Error logging trade entry: {e}")
    
    def log_watchlist_scan(self, symbols_scanned: int, setups_found: int, top_symbols: List[str]) -> None:
        """Log watchlist scanning results."""
        try:
            timestamp = datetime.now()
            if setups_found > 0:
                symbols_str = ', '.join(top_symbols[:3])
                self._add_log('success', f"Scan complete: {setups_found} setups found in {symbols_scanned} symbols - Top: {symbols_str}", None, timestamp)
            else:
                self._add_log('info', f"Scan complete: No strong setups in {symbols_scanned} symbols", None, timestamp)
        except Exception as e:
            logger.error(f"Error logging watchlist scan: {e}")
    
    def log_market_session_change(self, old_session: str, new_session: str) -> None:
        """Log market session changes."""
        try:
            timestamp = datetime.now()
            self._add_log('info', f"Market session: {old_session} → {new_session}", None, timestamp)
        except Exception as e:
            logger.error(f"Error logging session change: {e}")
    
    def _add_log(self, log_type: str, message: str, symbol: Optional[str], timestamp: datetime) -> None:
        """Add a log entry to the collection."""
        log_entry = {
            'type': log_type,  # 'success', 'warning', 'error', 'info', 'setup'
            'message': message,
            'symbol': symbol,
            'timestamp': timestamp.isoformat()
        }
        
        self.analysis_logs.append(log_entry)
        
        # Cache latest logs for API access
        self._cache_logs()
    
    def _cache_logs(self) -> None:
        """Cache logs to Redis for API access."""
        try:
            logs_data = {
                'logs': list(self.analysis_logs),
                'count': len(self.analysis_logs),
                'last_analysis': self.last_analysis_time.isoformat() if self.last_analysis_time else None,
                'updated_at': datetime.now().isoformat()
            }
            
            redis_cache.set("analysis_logs", logs_data, expiration=3600)
        except Exception as e:
            logger.error(f"Error caching analysis logs: {e}")
    
    def get_logs(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Get analysis logs for API consumption."""
        try:
            logs_list = list(self.analysis_logs)
            if limit:
                logs_list = logs_list[-limit:]
            
            return {
                'logs': logs_list,
                'count': len(logs_list),
                'last_analysis': self.last_analysis_time.isoformat() if self.last_analysis_time else None,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return {'logs': [], 'count': 0, 'last_analysis': None, 'error': str(e)}
    
    def clear_logs(self) -> bool:
        """Clear all analysis logs."""
        try:
            self.analysis_logs.clear()
            self.last_analysis_time = None
            self._cache_logs()
            return True
        except Exception as e:
            logger.error(f"Error clearing logs: {e}")
            return False
    
    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of managed positions for dashboard."""
        try:
            managed_positions = ov_position_manager.get_all_managed_positions()
            
            summary = {
                'total_positions': len(managed_positions),
                'positions': [],
                'total_unrealized_pnl': 0.0
            }
            
            for symbol, position_data in managed_positions.items():
                if 'error' in position_data:
                    continue
                    
                # Calculate unrealized P&L (would need current price)
                entry_price = position_data.get('entry_price', 0)
                remaining_qty = position_data.get('remaining_quantity', 0)
                
                position_summary = {
                    'symbol': symbol,
                    'quantity': remaining_qty,
                    'entry_price': entry_price,
                    'current_stop': position_data.get('current_stop', 0),
                    'trailing_level': position_data.get('trailing_level', 'initial'),
                    'scale_out_plan': position_data.get('scale_out_plan', {}),
                    'bars_in_favor': position_data.get('bars_in_favor', 0)
                }
                
                summary['positions'].append(position_summary)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting position summary: {e}")
            return {'total_positions': 0, 'positions': [], 'error': str(e)}


# Create global analysis logger instance
analysis_logger = AnalysisLogger()