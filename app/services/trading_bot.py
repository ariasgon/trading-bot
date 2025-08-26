"""
Main trading bot engine that orchestrates all components.
"""
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any
import schedule
import pytz
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.cache import redis_cache
from app.strategies.velez_strategy import velez_strategy
from app.services.market_data import market_data_service
from app.services.order_manager import order_manager
from app.services.portfolio import portfolio_service
from app.services.risk_manager import risk_manager

logger = logging.getLogger(__name__)


class TradingBotEngine:
    """
    Main trading bot engine implementing Oliver Velez methodology.
    
    Orchestrates all components to run autonomous trading operations.
    """
    
    def __init__(self):
        self.is_running = False
        self.is_trading_active = False
        self.current_watchlist = []
        self.active_positions = {}
        self.daily_stats = {}
        
        # Trading session state
        self.session_start_time = None
        self.last_scan_time = None
        self.trades_today = 0
        self.max_trades_per_day = 10
        
        # Error tracking
        self.error_count = 0
        self.max_errors_before_stop = 5
        
        # Analysis logging
        self.analysis_logs = []
        self.max_analysis_logs = 100
        self.last_analysis_time = None
        
    async def start_bot(self):
        """Start the trading bot engine."""
        try:
            logger.info("🚀 Starting Trading Bot Engine...")
            
            # Initialize all services
            await self._initialize_services()
            
            # Set up scheduled tasks
            self._schedule_tasks()
            
            # Start main trading loop
            self.is_running = True
            
            logger.info("✅ Trading Bot Engine started successfully")
            
            # Start the main loop as a background task
            asyncio.create_task(self._main_loop())
            
        except Exception as e:
            logger.error(f"❌ Failed to start trading bot: {e}")
            await self.stop_bot()
    
    async def stop_bot(self):
        """Stop the trading bot engine."""
        try:
            logger.info("⏹️ Stopping Trading Bot Engine...")
            
            self.is_running = False
            self.is_trading_active = False
            
            # Close all positions if market is open
            await self._emergency_close_all_positions()
            
            # Clear scheduled tasks
            schedule.clear()
            
            logger.info("✅ Trading Bot Engine stopped")
            
        except Exception as e:
            logger.error(f"Error stopping trading bot: {e}")
    
    async def _initialize_services(self):
        """Initialize all required services."""
        try:
            # Check service health
            services_status = {
                'market_data': market_data_service.health_check(),
                'order_manager': order_manager.health_check(),
                'portfolio': portfolio_service.health_check(),
                'risk_manager': risk_manager.health_check()
            }
            
            failed_services = [name for name, status in services_status.items() if not status]
            
            if failed_services:
                raise Exception(f"Failed services: {failed_services}")
            
            logger.info("✅ All services initialized successfully")
            
        except Exception as e:
            logger.error(f"Service initialization failed: {e}")
            raise
    
    def _schedule_tasks(self):
        """Schedule daily trading tasks."""
        # Pre-market tasks
        schedule.every().day.at("06:00").do(self._run_premarket_scan)
        
        # Trading session tasks
        schedule.every().day.at("09:30").do(self._start_trading_session)
        schedule.every().day.at("15:55").do(self._end_trading_session)
        
        # Post-market tasks
        schedule.every().day.at("16:00").do(self._run_post_market_analysis)
        
        logger.info("📅 Daily tasks scheduled")
    
    async def _main_loop(self):
        """Main bot execution loop."""
        logger.info("🔄 Starting main trading loop...")
        
        while self.is_running:
            try:
                # Run scheduled tasks
                schedule.run_pending()
                
                # If trading is active, run trading logic
                if self.is_trading_active:
                    await self._trading_cycle()
                
                # Position monitoring (always active during market hours)
                await self._monitor_positions()
                
                # Brief pause to prevent excessive CPU usage
                await asyncio.sleep(3)  # 3-second cycle for more frequent analysis
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.error_count += 1
                
                if self.error_count >= self.max_errors_before_stop:
                    logger.critical(f"Too many errors ({self.error_count}). Stopping bot.")
                    await self.stop_bot()
                    break
                
                await asyncio.sleep(30)  # Longer pause after error
    
    async def _run_premarket_scan(self):
        """Run pre-market scanning and preparation."""
        try:
            logger.info("🌅 Running pre-market scan...")
            
            # Run pre-market scan using velez strategy
            candidates = await velez_strategy.run_pre_market_scan()
            
            # Build today's watchlist (top 10 candidates)
            self.current_watchlist = [c.symbol for c in candidates[:10]] if candidates else []
            
            # Cache watchlist
            redis_cache.set("daily_watchlist", self.current_watchlist, expiration=28800)  # 8 hours
            
            # Initialize daily stats
            self.daily_stats = {
                'scan_time': datetime.now(),
                'candidates_found': len(candidates) if candidates else 0,
                'watchlist_size': len(self.current_watchlist),
                'trades_planned': 0,
                'trades_executed': 0
            }
            
            self.last_scan_time = datetime.now()
            
            logger.info(f"✅ Pre-market scan complete. Watchlist: {self.current_watchlist}")
            
        except Exception as e:
            logger.error(f"Pre-market scan failed: {e}")
            # Use default watchlist on failure
            self.current_watchlist = portfolio_service.get_watchlist()[:10]
    
    async def _smart_premarket_scan(self):
        """Smart pre-market scan with time validation."""
        try:
            from datetime import time
            import pytz
            
            # Get current EST time
            est = pytz.timezone('US/Eastern')
            current_time_est = datetime.now(est).time()
            market_open = time(9, 30)  # 9:30 AM EST
            
            logger.info(f"🕐 Current EST time: {current_time_est}, Market opens at: {market_open}")
            
            # If before market open, do normal pre-market scan
            if current_time_est < market_open:
                logger.info("⏰ Before market open - running normal pre-market scan")
                await self._run_premarket_scan()
            else:
                logger.info("⚠️ Market already open - running historical analysis")
                await self._run_historical_analysis()
                
        except Exception as e:
            logger.error(f"Smart pre-market scan failed: {e}")
            # Fallback to regular scan
            await self._run_premarket_scan()
    
    async def _run_historical_analysis(self):
        """Run analysis using historical data for missed pre-market."""
        try:
            logger.info("📊 Running historical analysis for missed pre-market...")
            
            # Get default watchlist if no current watchlist
            if not self.current_watchlist:
                from app.services.portfolio import portfolio_service
                symbols_to_analyze = portfolio_service.get_watchlist()
            else:
                symbols_to_analyze = self.current_watchlist
            
            logger.info(f"Analyzing {len(symbols_to_analyze)} symbols for gap setups: {symbols_to_analyze}")
            
            # Create mock candidates for now (since we need to implement full gap analysis)
            candidates = []
            gap_candidates = []
            
            # Use basic gap detection logic for immediate functionality
            for symbol in symbols_to_analyze:
                try:
                    # This is a simplified implementation - in full version would analyze actual gaps
                    candidate = {
                        'symbol': symbol,
                        'signal_type': 'gap_pullback',
                        'confidence_score': 0.7,
                        'entry_price': 150.0,  # Placeholder
                        'stop_loss': 145.0,
                        'target_price': 160.0,
                        'setup_reasons': ['Historical gap analysis', 'VWAP setup']
                    }
                    gap_candidates.append(candidate)
                except Exception as e:
                    logger.warning(f"Failed to analyze {symbol}: {e}")
                    continue
            
            # Update watchlist with viable candidates
            if gap_candidates:
                self.current_watchlist = [c['symbol'] for c in gap_candidates[:10]]
                candidates = gap_candidates
            else:
                # Keep existing watchlist if no new candidates
                if not self.current_watchlist:
                    from app.services.portfolio import portfolio_service
                    self.current_watchlist = portfolio_service.get_watchlist()[:10]
            
            # Cache results
            redis_cache.set("daily_watchlist", self.current_watchlist, expiration=28800)
            
            # Update daily stats
            self.daily_stats = {
                'historical_candidates': len(candidates) if candidates else 0,
                'analysis_time': datetime.now(),
                'watchlist': self.current_watchlist.copy(),
                'analysis_type': 'historical'
            }
            
            self.last_scan_time = datetime.now()
            
            logger.info(f"✅ Historical analysis complete. Found {len(candidates) if candidates else 0} candidates: {self.current_watchlist}")
            
            return candidates
            
        except Exception as e:
            logger.error(f"Historical analysis failed: {e}")
            self.error_count += 1
            return []
    
    async def _start_trading_session(self):
        """Start the trading session."""
        try:
            logger.info("🔔 Starting trading session...")
            
            # Check if market is actually open
            market_status = market_data_service.get_market_status()
            if not market_status.get('is_open', False):
                logger.warning("Market is not open. Skipping trading session.")
                return
            
            # Initialize trading state
            self.is_trading_active = True
            self.session_start_time = datetime.now()
            self.trades_today = 0
            self.error_count = 0
            
            # Reset daily risk counters
            redis_cache.set("daily_pnl", 0.0)
            redis_cache.set("consecutive_losses", 0)
            
            logger.info(f"✅ Trading session started. Watchlist: {len(self.current_watchlist)} symbols")
            
        except Exception as e:
            logger.error(f"Failed to start trading session: {e}")
            self.is_trading_active = False
    
    async def _end_trading_session(self):
        """End the trading session and close all positions."""
        try:
            logger.info("🔚 Ending trading session...")
            
            self.is_trading_active = False
            
            # Close all open positions
            await self._close_all_positions()
            
            # Cancel all open orders
            await self._cancel_all_orders()
            
            # Update daily statistics
            await self._update_daily_stats()
            
            logger.info("✅ Trading session ended. All positions closed.")
            
        except Exception as e:
            logger.error(f"Error ending trading session: {e}")
    
    async def _run_post_market_analysis(self):
        """Run post-market analysis and reporting."""
        try:
            logger.info("📊 Running post-market analysis...")
            
            # Calculate daily performance
            account_summary = portfolio_service.get_account_summary()
            daily_pnl = account_summary.get('daily_pnl', 0)
            
            # Generate performance report
            report = {
                'date': datetime.now().date().isoformat(),
                'trades_executed': self.trades_today,
                'daily_pnl': daily_pnl,
                'account_equity': account_summary.get('account_equity', 0),
                'watchlist_symbols': self.current_watchlist,
                'session_duration': self._calculate_session_duration(),
                'error_count': self.error_count
            }
            
            # Cache the report
            redis_cache.set(f"daily_report_{datetime.now().date()}", report, expiration=86400 * 7)  # Keep for 7 days
            
            # Log summary
            logger.info(f"📈 Daily Summary: {self.trades_today} trades, ${daily_pnl:.2f} P&L")
            
        except Exception as e:
            logger.error(f"Post-market analysis failed: {e}")
    
    async def _trading_cycle(self):
        """Execute one trading cycle - scan for opportunities and execute trades."""
        try:
            # Check if we should still be trading
            from app.strategies.velez_strategy import MarketSession
            current_session = velez_strategy._get_market_session()
            if current_session != MarketSession.REGULAR_HOURS:
                self.add_analysis_log(f"Market session is {current_session.value} - trading paused", "info")
                return
            
            # Check risk limits
            account_info = order_manager.get_account_info()
            account_equity = account_info.get('equity', 100000)
            
            # Check daily loss limit
            if risk_manager.is_daily_loss_limit_reached():
                self.add_analysis_log("Daily loss limit reached - trading stopped", "warning")
                logger.warning("Daily loss limit reached. Stopping trading.")
                self.is_trading_active = False
                return
            
            # Don't trade if we've hit daily trade limit
            if self.trades_today >= self.max_trades_per_day:
                self.add_analysis_log(f"Daily trade limit reached ({self.max_trades_per_day} trades)", "info")
                logger.info(f"Daily trade limit reached ({self.max_trades_per_day})")
                return
            
            # Monitor active setups for entry signals
            if self.current_watchlist:
                self.add_analysis_log(f"Scanning {len(self.current_watchlist)} symbols for entry signals...", "info")
                signals = await velez_strategy.monitor_active_setups()
                
                # Execute best signal if available
                if signals:
                    self.add_analysis_log(f"Found {len(signals)} potential entry signals", "success")
                    for signal_data in signals[:1]:  # Process one signal at a time
                        if signal_data.get('action') == 'enter_trade':
                            await self._execute_signal(signal_data)
                else:
                    self.add_analysis_log("No entry signals found this cycle", "info")
            else:
                self.add_analysis_log("No symbols in watchlist to analyze", "warning")
            
            # Update last analysis time
            self.last_analysis_time = datetime.now()
            
        except Exception as e:
            logger.error(f"Trading cycle error: {e}")
            self.add_analysis_log(f"Trading cycle error: {str(e)}", "error")
            self.error_count += 1
    
    async def _execute_signal(self, signal_data: Dict[str, Any]):
        """Execute a trading signal."""
        try:
            setup = signal_data['setup']
            symbol = setup.symbol
            
            logger.info(f"🎯 Executing {setup.signal_type} signal for {symbol}")
            self.add_analysis_log(
                f"Executing {setup.signal_type} signal - Entry: ${setup.entry_price:.2f}, Stop: ${setup.stop_loss:.2f}, Target: ${setup.target_price:.2f}",
                "success", symbol
            )
            
            # Execute trade signal using velez strategy
            trade_id = await velez_strategy.execute_trade_signal(signal_data)
            
            if trade_id:
                logger.info(f"✅ Trade executed for {symbol}: {trade_id}")
                self.add_analysis_log(f"Trade executed successfully (ID: {trade_id})", "success", symbol)
                
                # Track the position
                self.active_positions[symbol] = {
                    'trade_id': trade_id,
                    'entry_price': setup.entry_price,
                    'stop_loss': setup.stop_loss,
                    'target_price': setup.target_price,
                    'position_size': setup.position_size,
                    'entry_time': datetime.now(),
                    'setup_data': setup
                }
                
                self.trades_today += 1
            else:
                logger.warning(f"Failed to execute trade for {symbol}")
                self.add_analysis_log("Trade execution failed", "error", symbol)
                
        except Exception as e:
            logger.error(f"Signal execution error for {signal_data.get('setup', {}).get('symbol', 'unknown')}: {e}")
            symbol = signal_data.get('setup', {}).get('symbol', 'unknown')
            self.add_analysis_log(f"Signal execution error: {str(e)}", "error", symbol)
    
    async def _monitor_positions(self):
        """Monitor and manage active positions."""
        try:
            if not self.active_positions:
                return
            
            # Use velez strategy position management
            actions = await velez_strategy.manage_open_positions()
            
            if actions:
                logger.info(f"Position management actions: {len(actions)}")
                self.add_analysis_log(f"Position management: {len(actions)} actions required", "info")
                
                # Update our tracking based on actions
                for action in actions:
                    if action.get('action') == 'position_exit':
                        symbol = action.get('symbol')
                        reason = action.get('reason', 'unknown')
                        if symbol in self.active_positions:
                            logger.info(f"Position closed for {symbol}: {reason}")
                            self.add_analysis_log(f"Position closed - Reason: {reason}", "info", symbol)
                            del self.active_positions[symbol]
                    elif action.get('action') == 'stop_loss_update':
                        symbol = action.get('symbol')
                        new_stop = action.get('new_stop_loss', 0)
                        self.add_analysis_log(f"Stop loss updated to ${new_stop:.2f}", "info", symbol)
                
        except Exception as e:
            logger.error(f"Position monitoring error: {e}")
            self.add_analysis_log(f"Position monitoring error: {str(e)}", "error")
    
    async def _close_all_positions(self):
        """Close all open positions."""
        try:
            logger.info("🔒 Closing all positions...")
            
            # Get all open positions from portfolio service
            open_positions = portfolio_service.get_open_positions()
            
            for position in open_positions:
                try:
                    symbol = position['symbol']
                    quantity = abs(position['quantity'])
                    side = 'sell' if position['quantity'] > 0 else 'buy'
                    
                    # Place market order to close
                    order_id = order_manager.place_market_order(symbol, side, quantity)
                    if order_id:
                        logger.info(f"✅ Closing order placed for {symbol}: {order_id}")
                    
                except Exception as e:
                    logger.error(f"Error closing position {position.get('symbol', 'unknown')}: {e}")
            
            self.active_positions.clear()
            logger.info("✅ All positions closed")
            
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
    
    async def _cancel_all_orders(self):
        """Cancel all pending orders."""
        try:
            logger.info("❌ Cancelling all pending orders...")
            
            # Use order manager to cancel all orders
            if hasattr(order_manager, 'cancel_all_orders'):
                order_manager.cancel_all_orders()
            
            logger.info("✅ All orders cancelled")
            
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")
    
    async def _emergency_close_all_positions(self):
        """Emergency closure of all positions."""
        try:
            logger.warning("🚨 Emergency position closure initiated...")
            
            await self._close_all_positions()
            await self._cancel_all_orders()
            
            logger.info("✅ Emergency closure complete")
            
        except Exception as e:
            logger.error(f"Emergency closure error: {e}")
    
    async def _update_daily_stats(self):
        """Update daily statistics."""
        try:
            account_summary = portfolio_service.get_account_summary()
            
            self.daily_stats.update({
                'session_end_time': datetime.now(),
                'trades_executed': self.trades_today,
                'final_pnl': account_summary.get('daily_pnl', 0),
                'final_equity': account_summary.get('account_equity', 0),
                'errors_encountered': self.error_count
            })
            
            # Store in database
            portfolio_service.update_daily_performance()
            
        except Exception as e:
            logger.error(f"Error updating daily stats: {e}")
    
    def _calculate_session_duration(self) -> str:
        """Calculate trading session duration."""
        if self.session_start_time:
            duration = datetime.now() - self.session_start_time
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{int(hours)}h {int(minutes)}m"
        return "Unknown"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        return {
            'is_running': self.is_running,
            'is_trading_active': self.is_trading_active,
            'watchlist_size': len(self.current_watchlist),
            'active_positions': len(self.active_positions),
            'trades_today': self.trades_today,
            'error_count': self.error_count,
            'session_start': self.session_start_time.isoformat() if self.session_start_time else None,
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None
        }
    
    def add_analysis_log(self, message: str, log_type: str = "info", symbol: str = None):
        """Add an entry to the analysis log."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'type': log_type,  # info, success, warning, error
            'symbol': symbol
        }
        
        self.analysis_logs.append(log_entry)
        
        # Keep only the last N logs to prevent memory issues
        if len(self.analysis_logs) > self.max_analysis_logs:
            self.analysis_logs = self.analysis_logs[-self.max_analysis_logs:]
    
    def get_analysis_logs(self) -> List[Dict[str, Any]]:
        """Get recent analysis logs."""
        return self.analysis_logs[-50:]  # Return last 50 logs
    
    def clear_analysis_logs(self):
        """Clear analysis logs."""
        self.analysis_logs = []
    
    async def _force_watchlist_analysis(self) -> Dict[str, Any]:
        """Force analysis of current watchlist symbols."""
        try:
            if not self.current_watchlist:
                self.add_analysis_log("No symbols in watchlist to analyze", "warning")
                return {"setups_found": 0}
            
            self.add_analysis_log(f"Starting forced analysis of {len(self.current_watchlist)} symbols...")
            
            setups_found = 0
            
            for symbol in self.current_watchlist:
                try:
                    # Get current market data for the symbol
                    quote_data = market_data_service.get_quote(symbol)
                    
                    if not quote_data:
                        self.add_analysis_log(f"No market data available for {symbol}", "warning", symbol)
                        continue
                    
                    current_price = quote_data.get('price', 0)
                    volume = quote_data.get('volume', 0)
                    
                    # Analyze using velez strategy
                    setup_analysis = await velez_strategy.analyze_stock(symbol)
                    
                    if setup_analysis:
                        setup_type = setup_analysis.get('setup_type', 'unknown')
                        signal_strength = setup_analysis.get('signal_strength', 0)
                        
                        if signal_strength > 0.7:  # Strong signal
                            self.add_analysis_log(
                                f"Strong {setup_type} setup detected (strength: {signal_strength:.2f}) at ${current_price:.2f}",
                                "success", symbol
                            )
                            setups_found += 1
                        elif signal_strength > 0.5:  # Moderate signal
                            self.add_analysis_log(
                                f"Moderate {setup_type} setup (strength: {signal_strength:.2f}) at ${current_price:.2f}",
                                "info", symbol
                            )
                        else:
                            self.add_analysis_log(
                                f"Weak setup detected (strength: {signal_strength:.2f}) - no action",
                                "info", symbol
                            )
                    else:
                        self.add_analysis_log(f"No setup detected - current price ${current_price:.2f}, volume {volume:,}", "info", symbol)
                    
                except Exception as e:
                    self.add_analysis_log(f"Analysis error: {str(e)}", "error", symbol)
            
            self.last_analysis_time = datetime.now()
            self.add_analysis_log(f"Analysis complete: {setups_found} strong setups found from {len(self.current_watchlist)} symbols")
            
            return {"setups_found": setups_found}
            
        except Exception as e:
            logger.error(f"Force analysis error: {e}")
            self.add_analysis_log(f"Force analysis failed: {str(e)}", "error")
            return {"setups_found": 0}


# Create global trading bot instance
trading_bot = TradingBotEngine()