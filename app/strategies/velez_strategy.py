"""
Oliver Velez Trading Strategy Implementation.

This module implements the complete Oliver Velez trading methodology including:
- Pre-market gap analysis
- VWAP pullback entries
- Bullish reversal pattern recognition
- Risk management and position sizing
"""
import asyncio
import logging
import pandas as pd
from decimal import Decimal
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from app.strategies.indicators import VelezSignalGenerator, TechnicalIndicators
from app.services.market_data import market_data_service
from app.services.order_manager import order_manager
from app.services.risk_manager import risk_manager
from app.services.portfolio import portfolio_service
from app.core.cache import redis_cache
from app.core.database import get_db_session
from app.models.trade import Trade, TradeStatus
from app.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)


class MarketSession(Enum):
    """Market session types."""
    PRE_MARKET = "pre_market"
    MARKET_OPEN = "market_open"
    REGULAR_HOURS = "regular_hours"
    AFTER_HOURS = "after_hours"
    CLOSED = "closed"


@dataclass
class TradeSetup:
    """Represents a potential trade setup."""
    symbol: str
    signal_type: str
    signal_strength: int
    entry_price: float
    stop_loss: float
    target_price: float
    position_size: int
    risk_reward_ratio: float
    setup_reasons: List[str]
    timestamp: datetime
    confidence_score: float = 0.0


class VelezTradingStrategy:
    """
    Main Oliver Velez trading strategy implementation.
    
    The strategy focuses on:
    1. Gap up stocks with pullback to VWAP
    2. Bullish reversal patterns at support levels
    3. Volume confirmation
    4. Risk management with 1% position sizing
    """
    
    def __init__(self):
        self.signal_generator = VelezSignalGenerator()
        self.indicators = TechnicalIndicators()
        self.is_active = False
        self.active_setups = {}
        self.daily_trades_count = 0
        self.max_daily_trades = 10
        
        # Strategy parameters
        self.min_gap_percent = 0.75
        self.max_gap_percent = 8.0
        self.min_pullback_percent = 1.0
        self.max_pullback_percent = 5.0
        self.min_volume_ratio = 1.5
        self.min_signal_strength = 3
        
    async def initialize_strategy(self) -> bool:
        """Initialize the strategy for the trading day."""
        try:
            logger.info("Initializing Velez trading strategy...")
            
            # Reset daily counters
            self.daily_trades_count = 0
            self.active_setups = {}
            
            # Check pre-trade conditions
            conditions = risk_manager.check_pre_trade_conditions()
            if not conditions.get('can_trade', False):
                logger.warning(f"Cannot trade: {conditions.get('reasons', [])}")
                return False
            
            # Cache strategy status
            redis_cache.set("velez_strategy_status", {
                "is_active": True,
                "initialized_at": datetime.now().isoformat(),
                "daily_trades_count": 0
            })
            
            self.is_active = True
            logger.info("Velez trading strategy initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing strategy: {e}")
            return False
    
    async def run_pre_market_scan(self) -> List[TradeSetup]:
        """
        Run pre-market scan to identify gap up candidates.
        
        Returns:
            List of potential trade setups
        """
        try:
            logger.info("Running pre-market gap scan...")
            
            watchlist = portfolio_service.get_watchlist()
            gap_candidates = []
            
            for symbol in watchlist:
                try:
                    # Get pre-market data
                    df = await self._get_market_data(symbol, period='1d', interval='5m')
                    if df is None or df.empty:
                        continue
                    
                    # Analyze for gaps
                    gap_analysis = self._analyze_pre_market_gap(df, symbol)
                    
                    if gap_analysis.get('is_gap_candidate'):
                        setup = await self._create_gap_setup(symbol, gap_analysis, df)
                        if setup:
                            gap_candidates.append(setup)
                            
                except Exception as e:
                    logger.error(f"Error analyzing {symbol} in pre-market: {e}")
                    continue
            
            # Sort by confidence score
            gap_candidates.sort(key=lambda x: x.confidence_score, reverse=True)
            
            # Cache results
            redis_cache.set("pre_market_candidates", [
                {
                    'symbol': setup.symbol,
                    'signal_strength': setup.signal_strength,
                    'confidence_score': setup.confidence_score,
                    'entry_price': setup.entry_price,
                    'gap_percent': gap_analysis.get('gap_percent', 0)
                }
                for setup in gap_candidates
            ], expiration=3600)
            
            logger.info(f"Found {len(gap_candidates)} pre-market gap candidates")
            return gap_candidates
            
        except Exception as e:
            logger.error(f"Error in pre-market scan: {e}")
            return []
    
    async def monitor_active_setups(self) -> List[Dict[str, Any]]:
        """
        Monitor active trade setups for entry signals.
        
        Returns:
            List of actionable trade signals
        """
        try:
            if not self.is_active:
                return []
            
            actionable_signals = []
            current_session = self._get_market_session()
            
            # Only trade during regular market hours
            if current_session != MarketSession.REGULAR_HOURS:
                return []
            
            for symbol, setup in self.active_setups.items():
                try:
                    # Get current market data
                    df = await self._get_market_data(symbol, period='1d', interval='1m')
                    if df is None or df.empty:
                        continue
                    
                    # Check if entry conditions are met
                    entry_signal = await self._check_entry_conditions(setup, df)
                    
                    if entry_signal.get('should_enter', False):
                        actionable_signals.append({
                            'setup': setup,
                            'entry_signal': entry_signal,
                            'action': 'enter_trade'
                        })
                        
                except Exception as e:
                    logger.error(f"Error monitoring setup for {symbol}: {e}")
                    continue
            
            return actionable_signals
            
        except Exception as e:
            logger.error(f"Error monitoring active setups: {e}")
            return []
    
    async def execute_trade_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """
        Execute a trade based on the signal.
        
        Args:
            signal: Trade signal from monitoring
            
        Returns:
            Trade ID if successful, None otherwise
        """
        try:
            setup: TradeSetup = signal['setup']
            entry_signal = signal['entry_signal']
            
            # Final validation before entry
            validation = risk_manager.validate_trade_setup(
                symbol=setup.symbol,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                target_price=setup.target_price
            )
            
            if not validation.get('is_valid', False):
                logger.warning(f"Trade setup validation failed for {setup.symbol}: {validation.get('errors', [])}")
                return None
            
            # Calculate position size
            shares, sizing_info = risk_manager.calculate_position_size(
                symbol=setup.symbol,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss
            )
            
            if shares <= 0:
                logger.warning(f"Invalid position size for {setup.symbol}: {sizing_info}")
                return None
            
            # Place the order
            order_id = order_manager.place_market_order(
                symbol=setup.symbol,
                side='buy',
                quantity=shares
            )
            
            if order_id:
                # Create trade record
                trade_id = await self._create_trade_record(setup, order_id, shares)
                
                # Remove from active setups
                self.active_setups.pop(setup.symbol, None)
                
                # Update daily trade count
                self.daily_trades_count += 1
                
                # Place stop-loss order
                await self._place_stop_loss_order(setup.symbol, shares, setup.stop_loss)
                
                logger.info(f"Successfully entered trade: {setup.symbol} - {shares} shares at ${setup.entry_price}")
                return trade_id
            else:
                logger.error(f"Failed to place order for {setup.symbol}")
                return None
                
        except Exception as e:
            logger.error(f"Error executing trade signal: {e}")
            return None
    
    async def manage_open_positions(self) -> List[Dict[str, Any]]:
        """
        Manage open positions for exits and stops.
        
        Returns:
            List of position management actions taken
        """
        try:
            actions = []
            open_positions = portfolio_service.get_open_positions()
            
            for position in open_positions:
                try:
                    symbol = position['symbol']
                    
                    # Get current market data
                    df = await self._get_market_data(symbol, period='1d', interval='1m')
                    if df is None or df.empty:
                        continue
                    
                    current_price = df['close'].iloc[-1]
                    
                    # Check exit conditions
                    exit_signal = self._check_exit_conditions(position, current_price, df)
                    
                    if exit_signal.get('should_exit', False):
                        action = await self._execute_position_exit(
                            position, exit_signal['reason'], current_price
                        )
                        if action:
                            actions.append(action)
                            
                except Exception as e:
                    logger.error(f"Error managing position {symbol}: {e}")
                    continue
            
            return actions
            
        except Exception as e:
            logger.error(f"Error managing open positions: {e}")
            return []
    
    def _analyze_pre_market_gap(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Analyze pre-market price data for gap opportunities."""
        try:
            # Get yesterday's close and today's open
            yesterday_close = df['close'].iloc[-2]  # Previous session close
            today_open = df['open'].iloc[-1]  # Current session open
            
            # Calculate gap
            gap_amount = today_open - yesterday_close
            gap_percent = (gap_amount / yesterday_close) * 100
            
            # Check if it's a valid gap
            is_gap_up = gap_percent >= self.min_gap_percent
            is_reasonable_gap = gap_percent <= self.max_gap_percent
            
            # Volume analysis
            volume_analysis = self.indicators.analyze_volume_profile(df)
            sufficient_volume = volume_analysis.get('volume_ratio', 0) >= self.min_volume_ratio
            
            # Price action since open
            current_price = df['close'].iloc[-1]
            high_since_open = df['high'].tail(10).max()
            pullback_from_high = (high_since_open - current_price) / high_since_open * 100
            
            is_gap_candidate = (is_gap_up and is_reasonable_gap and sufficient_volume)
            
            return {
                'is_gap_candidate': is_gap_candidate,
                'gap_percent': gap_percent,
                'gap_amount': gap_amount,
                'yesterday_close': yesterday_close,
                'today_open': today_open,
                'current_price': current_price,
                'pullback_percent': pullback_from_high,
                'volume_ratio': volume_analysis.get('volume_ratio', 0),
                'high_since_open': high_since_open
            }
            
        except Exception as e:
            logger.error(f"Error analyzing pre-market gap for {symbol}: {e}")
            return {'is_gap_candidate': False, 'error': str(e)}
    
    async def _create_gap_setup(self, symbol: str, gap_analysis: Dict[str, Any], 
                               df: pd.DataFrame) -> Optional[TradeSetup]:
        """Create a trade setup from gap analysis."""
        try:
            # Run full technical analysis
            analysis = self.signal_generator.analyze_stock(df, symbol)
            
            if analysis.get('signal_strength', 0) < self.min_signal_strength:
                return None
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(gap_analysis, analysis)
            
            setup = TradeSetup(
                symbol=symbol,
                signal_type=analysis.get('signal', 'none'),
                signal_strength=analysis.get('signal_strength', 0),
                entry_price=analysis.get('entry_price', 0),
                stop_loss=analysis.get('stop_loss', 0),
                target_price=analysis.get('target_price', 0),
                position_size=0,  # Will be calculated at execution
                risk_reward_ratio=analysis.get('risk_reward_ratio', 0),
                setup_reasons=analysis.get('signal_reasons', []),
                timestamp=datetime.now(),
                confidence_score=confidence_score
            )
            
            # Add to active setups
            self.active_setups[symbol] = setup
            
            return setup
            
        except Exception as e:
            logger.error(f"Error creating gap setup for {symbol}: {e}")
            return None
    
    async def _check_entry_conditions(self, setup: TradeSetup, 
                                     df: pd.DataFrame) -> Dict[str, Any]:
        """Check if entry conditions are met for a setup."""
        try:
            current_price = df['close'].iloc[-1]
            
            # Get fresh analysis
            analysis = self.signal_generator.analyze_stock(df, setup.symbol)
            
            # Check pullback to VWAP
            vwap = self.indicators.calculate_vwap(df)
            current_vwap = vwap.iloc[-1] if not vwap.empty else 0
            
            # Entry conditions
            near_vwap = abs(current_price - current_vwap) / current_vwap <= 0.005  # Within 0.5%
            bullish_reversal = any(analysis.get('reversal_patterns', {}).values())
            volume_confirmation = analysis.get('volume_analysis', {}).get('high_volume', False)
            
            # Check if we've pulled back enough from the gap
            pullback_analysis = analysis.get('pullback_analysis', {})
            sufficient_pullback = pullback_analysis.get('is_pullback', False)
            
            should_enter = (near_vwap and bullish_reversal and 
                          volume_confirmation and sufficient_pullback)
            
            return {
                'should_enter': should_enter,
                'current_price': current_price,
                'vwap_level': current_vwap,
                'near_vwap': near_vwap,
                'bullish_reversal': bullish_reversal,
                'volume_confirmation': volume_confirmation,
                'sufficient_pullback': sufficient_pullback,
                'updated_analysis': analysis
            }
            
        except Exception as e:
            logger.error(f"Error checking entry conditions for {setup.symbol}: {e}")
            return {'should_enter': False, 'error': str(e)}
    
    def _check_exit_conditions(self, position: Dict[str, Any], current_price: float,
                              df: pd.DataFrame) -> Dict[str, Any]:
        """Check if position should be exited."""
        try:
            entry_price = position['entry_price']
            stop_loss = position.get('stop_loss', 0)
            target_price = position.get('target_price', 0)
            
            # Stop loss hit
            if stop_loss and current_price <= stop_loss:
                return {'should_exit': True, 'reason': 'stop_loss', 'exit_type': 'stop'}
            
            # Target hit
            if target_price and current_price >= target_price:
                return {'should_exit': True, 'reason': 'target_reached', 'exit_type': 'profit'}
            
            # Time-based exit (end of day)
            if self._is_near_market_close():
                return {'should_exit': True, 'reason': 'end_of_day', 'exit_type': 'time'}
            
            # Trailing stop (if position is profitable)
            if current_price > entry_price:
                trailing_stop = self._calculate_trailing_stop(position, current_price, df)
                if trailing_stop and current_price <= trailing_stop:
                    return {'should_exit': True, 'reason': 'trailing_stop', 'exit_type': 'trailing'}
            
            return {'should_exit': False}
            
        except Exception as e:
            logger.error(f"Error checking exit conditions: {e}")
            return {'should_exit': False, 'error': str(e)}
    
    async def _execute_position_exit(self, position: Dict[str, Any], reason: str,
                                   current_price: float) -> Optional[Dict[str, Any]]:
        """Execute position exit."""
        try:
            symbol = position['symbol']
            quantity = abs(position['quantity'])
            
            # Place market sell order
            order_id = order_manager.place_market_order(
                symbol=symbol,
                side='sell',
                quantity=quantity
            )
            
            if order_id:
                logger.info(f"Exited position {symbol}: {quantity} shares at ${current_price} - Reason: {reason}")
                
                return {
                    'action': 'position_exit',
                    'symbol': symbol,
                    'quantity': quantity,
                    'exit_price': current_price,
                    'reason': reason,
                    'order_id': order_id,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                logger.error(f"Failed to exit position {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"Error executing position exit for {symbol}: {e}")
            return None
    
    async def _get_market_data(self, symbol: str, period: str = '1d', 
                              interval: str = '5m') -> Optional[pd.DataFrame]:
        """Get market data for analysis."""
        try:
            # Use market data service to get historical data
            data = market_data_service.get_historical_data(symbol, period, interval)
            return data
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return None
    
    def _calculate_confidence_score(self, gap_analysis: Dict[str, Any], 
                                   technical_analysis: Dict[str, Any]) -> float:
        """Calculate confidence score for a setup."""
        try:
            score = 0.0
            
            # Gap quality (0-30 points)
            gap_percent = gap_analysis.get('gap_percent', 0)
            if 1 <= gap_percent <= 3:
                score += 30
            elif 3 < gap_percent <= 5:
                score += 20
            elif gap_percent > 5:
                score += 10
            
            # Volume confirmation (0-25 points)
            volume_ratio = gap_analysis.get('volume_ratio', 0)
            if volume_ratio >= 2.0:
                score += 25
            elif volume_ratio >= 1.5:
                score += 15
            
            # Technical signal strength (0-25 points)
            signal_strength = technical_analysis.get('signal_strength', 0)
            score += min(signal_strength * 5, 25)
            
            # Risk-reward ratio (0-20 points)
            rr_ratio = technical_analysis.get('risk_reward_ratio', 0)
            if rr_ratio >= 3:
                score += 20
            elif rr_ratio >= 2:
                score += 15
            elif rr_ratio >= 1.5:
                score += 10
            
            return min(score, 100.0)  # Cap at 100
            
        except Exception as e:
            logger.error(f"Error calculating confidence score: {e}")
            return 0.0
    
    async def _create_trade_record(self, setup: TradeSetup, order_id: str, 
                                  shares: int) -> str:
        """Create a trade record in the database."""
        try:
            with get_db_session() as db:
                trade = Trade(
                    symbol=setup.symbol,
                    side='long',
                    quantity=shares,
                    entry_price=Decimal(str(setup.entry_price)),
                    stop_loss=Decimal(str(setup.stop_loss)),
                    target_price=Decimal(str(setup.target_price)),
                    strategy='velez_gap_pullback',
                    setup_type=setup.signal_type,
                    alpaca_order_id=order_id,
                    entry_time=datetime.now(),
                    status=TradeStatus.FILLED
                )
                
                db.add(trade)
                db.commit()
                db.refresh(trade)
                
                return str(trade.id)
                
        except Exception as e:
            logger.error(f"Error creating trade record: {e}")
            return ""
    
    async def _place_stop_loss_order(self, symbol: str, quantity: int, 
                                    stop_price: float) -> Optional[str]:
        """Place stop-loss order for position protection."""
        try:
            stop_order_id = order_manager.place_stop_loss_order(
                symbol=symbol,
                quantity=quantity,
                stop_price=stop_price
            )
            
            if stop_order_id:
                logger.info(f"Placed stop-loss order for {symbol}: {quantity} shares at ${stop_price}")
            
            return stop_order_id
            
        except Exception as e:
            logger.error(f"Error placing stop-loss order for {symbol}: {e}")
            return None
    
    def _get_market_session(self) -> MarketSession:
        """Determine current market session."""
        try:
            now = datetime.now().time()
            
            # Market hours (Eastern Time)
            pre_market_start = time(4, 0)
            market_open = time(9, 30)
            market_close = time(16, 0)
            after_hours_end = time(20, 0)
            
            if pre_market_start <= now < market_open:
                return MarketSession.PRE_MARKET
            elif market_open <= now < market_close:
                return MarketSession.REGULAR_HOURS
            elif market_close <= now < after_hours_end:
                return MarketSession.AFTER_HOURS
            else:
                return MarketSession.CLOSED
                
        except Exception as e:
            logger.error(f"Error determining market session: {e}")
            return MarketSession.CLOSED
    
    def _is_near_market_close(self, minutes_before_close: int = 30) -> bool:
        """Check if we're near market close."""
        try:
            now = datetime.now().time()
            market_close = time(16, 0)
            
            # Calculate time before close
            close_threshold = (datetime.combine(datetime.today(), market_close) - 
                             timedelta(minutes=minutes_before_close)).time()
            
            return close_threshold <= now < market_close
            
        except Exception as e:
            logger.error(f"Error checking market close time: {e}")
            return False
    
    def _calculate_trailing_stop(self, position: Dict[str, Any], current_price: float,
                               df: pd.DataFrame) -> Optional[float]:
        """Calculate trailing stop level."""
        try:
            entry_price = position['entry_price']
            atr = self.indicators.calculate_atr(df).iloc[-1] if len(df) > 14 else 0
            
            # Use ATR-based trailing stop
            if atr > 0:
                trailing_distance = atr * 1.5
                trailing_stop = current_price - trailing_distance
                
                # Ensure trailing stop is above entry
                if trailing_stop > entry_price:
                    return trailing_stop
            
            return None
            
        except Exception as e:
            logger.error(f"Error calculating trailing stop: {e}")
            return None
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """Get current strategy status."""
        try:
            return {
                'is_active': self.is_active,
                'active_setups_count': len(self.active_setups),
                'active_symbols': list(self.active_setups.keys()),
                'daily_trades_count': self.daily_trades_count,
                'max_daily_trades': self.max_daily_trades,
                'market_session': self._get_market_session().value,
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting strategy status: {e}")
            return {'is_active': False, 'error': str(e)}
    
    async def shutdown_strategy(self) -> bool:
        """Shutdown the strategy gracefully."""
        try:
            logger.info("Shutting down Velez trading strategy...")
            
            self.is_active = False
            self.active_setups = {}
            
            # Update cache
            redis_cache.set("velez_strategy_status", {
                "is_active": False,
                "shutdown_at": datetime.now().isoformat()
            })
            
            logger.info("Velez trading strategy shut down successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error shutting down strategy: {e}")
            return False


# Create global strategy instance
velez_strategy = VelezTradingStrategy()