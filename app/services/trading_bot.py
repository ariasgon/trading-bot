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
from app.services.market_data import market_data_service
from app.services.order_manager import order_manager
from app.services.portfolio import portfolio_service
from app.services.risk_manager import risk_manager
from app.services.analysis_logger import analysis_logger

logger = logging.getLogger(__name__)


class TradingBotEngine:
    """
    Main trading bot engine using Proprietary Strategy.

    Orchestrates all components to run autonomous trading operations.
    """
    
    def __init__(self):
        self.is_running = False
        self.is_trading_active = False
        self.current_watchlist = []
        self.active_positions = {}
        self.daily_stats = {}

        # Import strategy
        from app.strategies.proprietary_strategy import proprietary_strategy

        # Use proprietary strategy (MACD + Volume + RSI)
        self.active_strategy = proprietary_strategy
        self.strategy_name = "proprietary"

        # Trading session state
        self.session_start_time = None
        self.last_scan_time = None
        self.trades_today = 0
        self.base_max_trades_per_day = 10  # Base limit when PnL is neutral/negative
        self.max_trades_when_profitable = 20  # Increased limit when daily PnL is positive

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
            
            # Initialize all services first
            await self._initialize_services()
            
            # CRITICAL: Initialize stock analysis watchlist FIRST
            logger.info("🔍 Initializing dynamic market scanner and watchlist...")
            await self._initialize_watchlist()
            
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

            # Initialize active strategy
            logger.info(f"Initializing {self.strategy_name.upper()} trading strategy...")
            strategy_initialized = await self.active_strategy.initialize_strategy()
            if not strategy_initialized:
                logger.warning(f"{self.strategy_name} strategy initialization returned False, but continuing...")
            else:
                logger.info(f"✅ {self.strategy_name.upper()} strategy initialized and activated")

        except Exception as e:
            logger.error(f"Service initialization failed: {e}")
            raise
    
    async def _initialize_watchlist(self):
        """Initialize stock analysis watchlist using dynamic market scanner."""
        try:
            logger.info("🔍 DYNAMIC SCANNER: Building initial watchlist from S&P 500 + NASDAQ...")
            
            # Use the dynamic market scanner to build watchlist
            self.current_watchlist = await portfolio_service.get_watchlist()
            
            if self.current_watchlist and len(self.current_watchlist) > 0:
                logger.info(f"✅ INITIAL WATCHLIST: {len(self.current_watchlist)} gappers found")
                logger.info(f"📊 TOP SYMBOLS: {', '.join(self.current_watchlist[:5])}")
                
                # Log to analysis log for visibility
                self.add_analysis_log(f"Dynamic scanner initialized: {len(self.current_watchlist)} gappers found", "success")
                self.add_analysis_log(f"Top gappers: {', '.join(self.current_watchlist[:5])}", "info")
                
                # CRITICAL: Auto-activate trading session after successful watchlist initialization
                logger.info("🚀 Auto-activating trading session to start opportunity monitoring...")
                self.is_trading_active = True
                self.add_analysis_log("Trading session activated - monitoring for opportunities", "success")
                
            else:
                logger.warning("⚠️ No gappers found in initial scan, using fallback")
                self.add_analysis_log("No significant gappers found in market scan", "warning")
                
        except Exception as e:
            logger.error(f"Error initializing watchlist: {e}")
            # Use fallback list if scanner fails
            # Expanded fallback watchlist (30 stocks)
            self.current_watchlist = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX", "AMD", "CRM",
                "COIN", "RBLX", "HOOD", "SOFI", "SHOP", "SQ", "UBER",
                "MRNA", "BNTX", "PFE", "JPM", "BAC", "GS",
                "MARA", "RIOT", "SOXL", "TQQQ", "SPXL", "SPY", "QQQ"
            ]
            self.add_analysis_log(f"Watchlist scanner error, using fallback: {e}", "error")
    
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
                    try:
                        # Add timeout to prevent hanging
                        await asyncio.wait_for(self._trading_cycle(), timeout=60)  # 60-second timeout
                    except asyncio.TimeoutError:
                        logger.warning("Trading cycle timeout - continuing with next cycle")
                        self.add_analysis_log("Trading cycle timeout - continuing", "warning")
                    except Exception as cycle_error:
                        logger.error(f"Trading cycle error: {cycle_error}")
                        self.add_analysis_log(f"Trading cycle error: {str(cycle_error)}", "error")
                
                # Position monitoring (always active during market hours)
                try:
                    await asyncio.wait_for(self._monitor_positions(), timeout=30)  # 30-second timeout
                except asyncio.TimeoutError:
                    logger.warning("Position monitoring timeout - continuing")
                except Exception as monitor_error:
                    logger.error(f"Position monitoring error: {monitor_error}")

                # Pause between analysis cycles - run every minute
                await asyncio.sleep(60)  # 60-second cycle (1 minute) for trade analysis
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.error_count += 1
                
                if self.error_count >= self.max_errors_before_stop:
                    logger.critical(f"Too many errors ({self.error_count}). Stopping bot.")
                    await self.stop_bot()
                    break
                
                await asyncio.sleep(30)  # Longer pause after error
    
    async def _run_premarket_scan(self):
        """Run pre-market scanning and preparation using dynamic market scanner."""
        try:
            logger.info("🌅 Running pre-market scan with dynamic market scanner...")

            # Use the dynamic market scanner to find gappers
            # This calls portfolio_service.get_watchlist() which calls market_scanner.scan_for_gappers()
            self.current_watchlist = await portfolio_service.get_watchlist()

            if not self.current_watchlist or len(self.current_watchlist) == 0:
                logger.warning("⚠️ Market scanner found no gappers, using fallback list")
                # Expanded fallback watchlist (30 stocks)
            self.current_watchlist = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX", "AMD", "CRM",
                "COIN", "RBLX", "HOOD", "SOFI", "SHOP", "SQ", "UBER",
                "MRNA", "BNTX", "PFE", "JPM", "BAC", "GS",
                "MARA", "RIOT", "SOXL", "TQQQ", "SPXL", "SPY", "QQQ"
            ]

            # Cache watchlist
            redis_cache.set("daily_watchlist", self.current_watchlist, expiration=28800)  # 8 hours

            # Initialize daily stats
            self.daily_stats = {
                'scan_time': datetime.now(),
                'candidates_found': len(self.current_watchlist),
                'watchlist_size': len(self.current_watchlist),
                'trades_planned': 0,
                'trades_executed': 0
            }

            self.last_scan_time = datetime.now()

            logger.info(f"✅ Pre-market scan complete. Watchlist: {len(self.current_watchlist)} stocks - {self.current_watchlist[:5]}")

        except Exception as e:
            logger.error(f"Pre-market scan failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Use fallback watchlist on failure
            # Expanded fallback watchlist (30 stocks)
            self.current_watchlist = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX", "AMD", "CRM",
                "COIN", "RBLX", "HOOD", "SOFI", "SHOP", "SQ", "UBER",
                "MRNA", "BNTX", "PFE", "JPM", "BAC", "GS",
                "MARA", "RIOT", "SOXL", "TQQQ", "SPXL", "SPY", "QQQ"
            ]
    
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
                symbols_to_analyze = await portfolio_service.get_watchlist()
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
                    self.current_watchlist = await portfolio_service.get_watchlist()
            
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
            # Check risk limits
            account_info = order_manager.get_account_info()
            account_equity = account_info.get('equity', 100000)
            
            # Check daily loss limit
            if risk_manager.is_daily_loss_limit_reached():
                self.add_analysis_log("Daily loss limit reached - trading stopped", "warning")
                logger.warning("Daily loss limit reached. Stopping trading.")
                self.is_trading_active = False
                return
            
            # Don't trade if we've hit daily trade limit (dynamic based on PnL)
            max_trades_today = self.get_dynamic_trade_limit()
            if self.trades_today >= max_trades_today:
                self.add_analysis_log(f"Daily trade limit reached ({self.trades_today}/{max_trades_today} trades)", "info")
                logger.info(f"Daily trade limit reached ({self.trades_today}/{max_trades_today})")
                return
            
            # STEP 1: Find new gap setups from watchlist (this was missing!)
            if self.current_watchlist:
                self.add_analysis_log(f"Scanning {len(self.current_watchlist)} symbols for entry signals...", "info")
                
                # First, analyze watchlist for new gap setups
                await self._analyze_watchlist_for_setups()
                
                # Then, monitor existing setups for entry signals  
                signals = await self.active_strategy.monitor_active_setups()
                
                # Execute best signals if available (process up to 3 per cycle)
                if signals:
                    self.add_analysis_log(f"Found {len(signals)} potential entry signals", "success")

                    # Get current position count from Alpaca (source of truth for actual open positions)
                    current_positions = risk_manager.get_open_positions_count()
                    max_positions = settings.max_concurrent_positions

                    signals_processed = 0
                    for signal_data in signals[:3]:  # Process top 3 signals per cycle (increased from 1)
                        # Check if we've hit position limit
                        if current_positions >= max_positions:
                            self.add_analysis_log(f"Max position limit reached ({current_positions}/{max_positions}) - skipping remaining signals", "warning")
                            break

                        if signal_data.get('action') == 'enter_trade':
                            await self._execute_signal(signal_data)
                            signals_processed += 1
                            current_positions += 1  # Increment for next check

                    if signals_processed > 0:
                        self.add_analysis_log(f"Processed {signals_processed} signal(s) this cycle", "success")
                else:
                    self.add_analysis_log("No entry signals found this cycle", "info")
            else:
                self.add_analysis_log("No symbols in watchlist to analyze", "warning")
            
            # Update last analysis time
            self.last_analysis_time = datetime.now()
            
        except Exception as e:
            import traceback
            logger.error(f"Trading cycle error: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            self.add_analysis_log(f"Trading cycle error: {str(e)}", "error")
            self.error_count += 1
    
    async def _execute_signal(self, signal_data: Dict[str, Any]):
        """Execute a trading signal."""
        try:
            setup = signal_data['setup']
            symbol = setup.symbol
            
            logger.info(f"🎯 Executing {setup.signal_type} signal for {symbol}")

            # Handle different target naming (target_price vs target_1)
            target_price = getattr(setup, 'target_price', getattr(setup, 'target_1', 0))

            self.add_analysis_log(
                f"Executing {setup.signal_type} signal - Entry: ${setup.entry_price:.2f}, Stop: ${setup.stop_loss:.2f}, Target: ${target_price:.2f}",
                "success", symbol
            )
            
            # Execute trade signal using velez strategy
            trade_id = await self.active_strategy.execute_trade_signal(signal_data)
            
            if trade_id:
                logger.info(f"✅ Trade executed for {symbol}: {trade_id}")
                self.add_analysis_log(f"Trade executed successfully (ID: {trade_id})", "success", symbol)
                
                # Track the position
                target_price = getattr(setup, 'target_price', getattr(setup, 'target_1', 0))

                self.active_positions[symbol] = {
                    'trade_id': trade_id,
                    'entry_price': setup.entry_price,
                    'stop_loss': setup.stop_loss,
                    'target_price': target_price,
                    'position_size': setup.position_size,
                    'entry_time': datetime.now(),
                    'setup_data': setup
                }
                
                self.trades_today += 1
            else:
                logger.warning(f"Failed to execute trade for {symbol}")
                self.add_analysis_log("Trade execution failed", "error", symbol)
                
        except Exception as e:
            # Handle TradeSetup object (not a dict) - extract symbol safely
            import traceback
            try:
                setup = signal_data.get('setup')
                symbol = setup.symbol if setup and hasattr(setup, 'symbol') else 'unknown'
            except:
                symbol = 'unknown'

            logger.error(f"Signal execution error for {symbol}: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            self.add_analysis_log(f"Signal execution error: {str(e)}", "error", symbol)
    
    async def _monitor_positions(self):
        """Monitor and manage active positions."""
        try:
            if not self.active_positions:
                return
            
            # Use proprietary strategy position management
            actions = await self.active_strategy.monitor_positions()
            
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
    
    async def _analyze_watchlist_for_setups(self):
        """Analyze current watchlist for new gap trading setups."""
        try:
            if not self.current_watchlist:
                return
            
            from app.services.market_data import market_data_service
            
            gap_threshold = 0.75  # 0.75% minimum gap (matches proprietary strategy)
            new_setups_found = 0
            
            for symbol in self.current_watchlist:
                try:
                    # Get comprehensive quote data
                    quote_data = market_data_service.get_quote(symbol)
                    if not quote_data:
                        continue
                    
                    gap_percent = abs(quote_data.get('gap_percent', 0))
                    premarket_gap_percent = abs(quote_data.get('premarket_gap_percent', 0))
                    
                    # Check if this symbol has a significant gap
                    if gap_percent >= gap_threshold or premarket_gap_percent >= gap_threshold:
                        # Create a gap setup for this symbol
                        setup_created = await self._create_gap_setup(symbol, quote_data)
                        if setup_created:
                            new_setups_found += 1
                            
                except Exception as e:
                    logger.warning(f"Error analyzing {symbol}: {e}")
                    continue
            
            if new_setups_found > 0:
                self.add_analysis_log(f"Created {new_setups_found} new gap setups from watchlist", "success")
                logger.info(f"Created {new_setups_found} gap setups")
            
        except Exception as e:
            logger.error(f"Error analyzing watchlist for setups: {e}")
            self.add_analysis_log(f"Watchlist analysis error: {str(e)}", "error")
    
    async def _create_gap_setup(self, symbol: str, quote_data: dict) -> bool:
        """Create a gap trading setup for a symbol."""
        try:
            current_price = quote_data.get('price', 0)
            gap_percent = quote_data.get('gap_percent', 0)
            premarket_gap_percent = quote_data.get('premarket_gap_percent', 0)
            volume = quote_data.get('volume', 0)
            
            # Determine gap direction and strength
            is_gap_up = gap_percent > 0 or premarket_gap_percent > 0
            gap_strength = max(abs(gap_percent), abs(premarket_gap_percent))
            
            # Only create setups for significant gaps (volume will be checked by strategy)
            if gap_strength < 0.75:
                return False
            
            # Create setup data
            setup_data = {
                'symbol': symbol,
                'setup_type': 'gap_up' if is_gap_up else 'gap_down',
                'gap_percent': gap_percent,
                'premarket_gap_percent': premarket_gap_percent,
                'current_price': current_price,
                'volume': volume,
                'previous_close': quote_data.get('previous_close', current_price),
                'premarket_price': quote_data.get('premarket_price', current_price),
                'timestamp': datetime.now(),
                'priority': gap_strength  # Higher gap = higher priority
            }
            
            # Add the setup to velez strategy for monitoring
            setup_added = await self.active_strategy.add_gap_setup(setup_data)
            
            if setup_added:
                self.add_analysis_log(
                    f"Gap setup created - {gap_strength:.1f}% gap, monitoring for entry signal",
                    "success", 
                    symbol
                )
                logger.info(f"Gap setup created for {symbol}: {gap_strength:.1f}% gap")
                return True
            
        except Exception as e:
            logger.error(f"Error creating gap setup for {symbol}: {e}")
            self.add_analysis_log(f"Setup creation error for {symbol}: {str(e)}", "error", symbol)
        
        return False
    
    def _calculate_session_duration(self) -> str:
        """Calculate trading session duration."""
        if self.session_start_time:
            duration = datetime.now() - self.session_start_time
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{int(hours)}h {int(minutes)}m"
        return "Unknown"

    def get_dynamic_trade_limit(self) -> int:
        """
        Calculate dynamic trade limit based on daily PnL.

        Returns more trades allowed when daily PnL is positive.
        """
        try:
            # Get daily PnL
            account_summary = portfolio_service.get_account_summary()
            daily_pnl = account_summary.get('daily_pnl', 0)

            if daily_pnl > 0:
                # Positive PnL: Allow more trades (20 instead of 10)
                logger.info(f"📈 Daily PnL is positive (${daily_pnl:.2f}) - increasing trade limit to {self.max_trades_when_profitable}")
                return self.max_trades_when_profitable
            else:
                # Negative or neutral PnL: Use base limit
                return self.base_max_trades_per_day

        except Exception as e:
            logger.error(f"Error calculating dynamic trade limit: {e}")
            return self.base_max_trades_per_day  # Fallback to base limit

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
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'last_analysis': self.last_analysis_time.isoformat() if self.last_analysis_time else None
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
        
        # Also add to the shared analysis logger for API access
        try:
            analysis_logger._add_log(log_type, message, symbol, analysis_logger._get_trading_time())
        except Exception as e:
            logger.error(f"Failed to add log to analysis_logger: {e}")
    
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
                    previous_close = quote_data.get('previous_close', 0)
                    gap_percent = quote_data.get('gap_percent', 0)
                    volume = quote_data.get('volume', 0)
                    
                    # Check for significant gaps
                    if abs(gap_percent) >= 2.0:  # 2% gap threshold
                        gap_direction = "UP" if gap_percent > 0 else "DOWN"
                        self.add_analysis_log(
                            f"🚀 SIGNIFICANT GAP {gap_direction}: {gap_percent:.2f}% (${previous_close:.2f} → ${current_price:.2f})",
                            "success", symbol
                        )
                        setups_found += 1

                    gap_info = f", gap: {gap_percent:.2f}%" if abs(gap_percent) > 0.5 else ""
                    self.add_analysis_log(f"Analyzed - price ${current_price:.2f}, volume {volume:,}{gap_info}", "info", symbol)
                    
                except Exception as e:
                    self.add_analysis_log(f"Analysis error: {str(e)}", "error", symbol)
            
            self.last_analysis_time = datetime.now()
            self.add_analysis_log(f"Analysis complete: {setups_found} strong setups found from {len(self.current_watchlist)} symbols")
            
            return {"setups_found": setups_found}

        except Exception as e:
            logger.error(f"Force analysis error: {e}")
            self.add_analysis_log(f"Force analysis failed: {str(e)}", "error")
            return {"setups_found": 0}

    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about active strategy."""
        return {
            "active_strategy": self.strategy_name,
            "is_active": self.active_strategy.is_active if hasattr(self.active_strategy, 'is_active') else False,
            "strategy_description": "Gap + Volume + MACD + RSI strategy for long and short trades"
        }


# Global trading bot instance (lazy initialization to avoid circular imports)
_trading_bot_instance = None

def get_trading_bot():
    """Get or create the global trading bot instance."""
    global _trading_bot_instance
    if _trading_bot_instance is None:
        _trading_bot_instance = TradingBotEngine()
    return _trading_bot_instance

# For backward compatibility, create a property-like object
class TradingBotProxy:
    """Proxy object that lazily creates the trading bot instance."""
    def __getattr__(self, name):
        return getattr(get_trading_bot(), name)

    def __setattr__(self, name, value):
        return setattr(get_trading_bot(), name, value)

trading_bot = TradingBotProxy()