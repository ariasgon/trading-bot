"""
Proprietary Trading Strategy - Gap Screening + MACD + Volume + RSI
===================================================================

Research-backed strategy combining the most effective indicators:
1. Gap Analysis (0.75% - 20%) - FOR SCREENING VOLATILE STOCKS ONLY
2. Volume Confirmation (>1.5x average - CRITICAL for quality setups)
3. MACD Histogram (momentum direction - DETERMINES LONG/SHORT)
4. RSI for overbought/oversold confirmation

KEY PRINCIPLE: Gap is for SCREENING, not direction! MACD determines trade direction.

Based on research showing 73-74% win rate for this combination.

Entry Rules:
-----------
LONG (MACD Histogram > threshold):
- Gap detected (ANY direction - confirms volatility)
- Volume > 1.5x average (cumulative: today's total volume vs 30-day average daily volume)
- RSI < 70 (not overbought)
- MACD histogram > threshold (bullish momentum - TIME-AWARE: 0.012 before 10:30 AM, 0.02 after)
- Time: Before 2 PM EST

SHORT (MACD Histogram < -threshold):
- Gap detected (ANY direction - confirms volatility)
- Volume > 1.5x average (cumulative: today's total volume vs 30-day average daily volume)
- RSI > 30 (not oversold)
- MACD histogram < -threshold (bearish momentum - TIME-AWARE: -0.012 before 10:30 AM, -0.02 after)
- Time: Before 2 PM EST

Exit Rules:
----------
- ALPACA AUTOMATIC TRAILING STOP: Active immediately after entry via OTO orders
  - Trail Type: trail_price (dollar amount - ATR distance)
  - Trail Distance: Same as initial stop distance (typically $2-5)
  - High Water Mark (HWM): Alpaca tracks highest price since entry
  - Stop Formula: stop_price = hwm - trail_price
  - Behavior: Stop follows price up continuously, never moves down
  - Example: Entry $100, trail $3 → Price $110 → Stop $107 (auto-adjusted)
  - Zero manual intervention - Alpaca handles everything
- Target: ATR-based (2.5x initial risk)
- Let orders run to target or trailing stop (fully automated)

Risk Management:
---------------
- Max daily potential loss: $540 (reduced for tighter risk control)
- Dynamic adjustment based on realized P/L
- If win $100 → can risk $440 more
- If lose $100 → can risk $440 more
- No trading after 2 PM EST
- Position close time: 3:50 PM EST
"""

import asyncio
import logging
import pandas as pd
import pytz
import time as time_module
from decimal import Decimal
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from app.strategies.indicators import TechnicalIndicators
from app.services.analysis_logger import analysis_logger
from app.services.market_data import market_data_service
from app.services.order_manager import order_manager
from app.services.risk_manager import risk_manager
from app.services.portfolio import portfolio_service
from app.core.cache import redis_cache
from app.core.database import get_db_session
from app.models.trade import Trade, TradeStatus
from app.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Trade signal types."""
    LONG = "long"
    SHORT = "short"
    NONE = "none"


@dataclass
class TradeSetup:
    """Represents a complete trade setup."""
    symbol: str
    signal_type: SignalType
    entry_price: float
    stop_loss: float
    target_price: float
    position_size: int

    # Signal details
    gap_percent: float
    volume_ratio: float
    rsi_value: float
    macd_value: float
    macd_signal: float
    macd_histogram: float
    atr_value: float
    has_macd_divergence: bool
    divergence_type: str

    # Metadata
    signal_strength: int
    setup_reasons: List[str]
    confidence_score: float
    timestamp: datetime


class ProprietaryStrategy:
    """
    Proprietary trading strategy: Gap + Volume + MACD + RSI
    Research-backed combination with 73-74% win rate.
    """

    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.is_active = False
        self.active_setups: Dict[str, TradeSetup] = {}
        self.active_positions: Dict[str, Dict] = {}

        # Strategy parameters
        self.min_gap_percent = 0.75
        self.max_gap_percent = 20.0
        self.min_volume_ratio = 1.5  # Volume must be 1.5x average - RESTORED to original strict requirement
        self.atr_stop_multiplier = 1.5  # 1.5x ATR for breathing room (was 0.9 - too tight!)
        self.min_stop_distance_dollars = 0.30  # Minimum $0.30 stop distance
        self.min_stop_distance_percent = 1.2  # OR 1.2% of price, whichever is larger

        # RSI thresholds
        self.rsi_overbought = 70
        self.rsi_oversold = 30

        # MACD parameters
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.divergence_lookback = 20  # Look back 20 bars for divergence

        # Risk Management
        self.max_daily_loss = 540.0  # Max $540 potential loss per day (reduced by 10% from $600)
        self.daily_realized_pnl = 0.0  # Track today's realized P/L

        # Time restriction - Extended to capture afternoon moves
        self.trading_cutoff_hour = 14  # No new trades after 2 PM EST
        self.position_close_hour = 15  # Close all positions by 3:50 PM EST
        self.position_close_minute = 50  # Close at exactly 3:50 PM

        # ALPACA NATIVE TRAILING STOPS
        # Uses OTO orders with trail_price (dollar amount trailing)
        # Alpaca automatically adjusts stop as price moves favorably
        # Stop distance = ATR-based (same as initial stop loss distance)
        self.enable_trailing_stops = True       # Use Alpaca's automatic trailing stops

        # Whipsaw prevention
        self.stop_out_cooldown = 3600            # 60 minutes (1 hour) cooldown after stop out to prevent whipsaws (seconds)
        self.recent_stop_outs: Dict[str, float] = {}  # Track stop out timestamps by symbol

        # Profit target multipliers (adjusted for tighter stops)
        self.profit_target_multiplier = 2.5      # Target = 2.5x initial risk
        self.aggressive_target_multiplier = 3.5  # Aggressive target for strong setups

    async def initialize_strategy(self) -> bool:
        """Initialize the strategy for the trading day."""
        try:
            logger.info("Initializing Proprietary Trading Strategy (Gap + Volume + MACD + RSI)...")

            # Reset daily counters
            self.active_setups = {}
            self.active_positions = {}
            self.daily_realized_pnl = 0.0

            # Get today's realized P/L from database
            self.daily_realized_pnl = self._get_todays_realized_pnl()

            # Check pre-trade conditions
            conditions = risk_manager.check_pre_trade_conditions()
            if not conditions.get('can_trade', False):
                logger.warning(f"Cannot trade: {conditions.get('reasons', [])}")
                return False

            # Cache strategy status
            redis_cache.set("proprietary_strategy_status", {
                "is_active": True,
                "initialized_at": datetime.now().isoformat(),
                "daily_realized_pnl": self.daily_realized_pnl
            })

            self.is_active = True
            logger.info(f"✅ Strategy initialized - Today's realized P/L: ${self.daily_realized_pnl:.2f}")

            # Log time restrictions
            logger.info(f"⏰ Time restrictions:")
            logger.info(f"   New trades cutoff: {self.trading_cutoff_hour}:00 PM EST")
            logger.info(f"   Position close time: {self.position_close_hour}:{self.position_close_minute:02d} PM EST")

            # Log Alpaca trailing stop configuration
            logger.info(f"🔄 ALPACA AUTOMATIC TRAILING STOPS: ENABLED")
            logger.info(f"   Method: OTO (One-Triggers-Other) orders with trail_price")
            logger.info(f"   Trail Distance: ATR-based dollar amount (~$2-5 typical)")
            logger.info(f"   Behavior: Stop follows price continuously, never moves back")
            logger.info(f"   Activation: Immediately after entry fills (no delay)")
            logger.info(f"   Alpaca auto-adjusts stop every tick as HWM increases")
            logger.info(f"   💰 Max daily risk: ${self.max_daily_loss:.0f}")

            return True

        except Exception as e:
            logger.error(f"Error initializing strategy: {e}")
            return False

    def _get_todays_realized_pnl(self) -> float:
        """Get today's realized P/L from closed trades."""
        try:
            with get_db_session() as db:
                # Use EST timezone for trading day calculation
                est = pytz.timezone('US/Eastern')
                today_start = datetime.now(est).replace(hour=0, minute=0, second=0, microsecond=0)

                trades = db.query(Trade).filter(
                    Trade.exit_time >= today_start,
                    Trade.exit_time.isnot(None),
                    Trade.realized_pnl.isnot(None)
                ).all()

                total_pnl = sum(float(trade.realized_pnl) for trade in trades)
                logger.info(f"Today's realized P/L from {len(trades)} trades: ${total_pnl:.2f}")
                return total_pnl

        except Exception as e:
            logger.error(f"Error getting today's realized P/L: {e}")
            return 0.0

    def _check_time_restriction(self) -> bool:
        """Check if current time is within trading hours."""
        try:
            est = pytz.timezone('US/Eastern')
            current_time_est = datetime.now(est).time()
            cutoff_time = time(self.trading_cutoff_hour, 0)

            if current_time_est >= cutoff_time:
                logger.info(f"⏰ Trading cutoff reached ({self.trading_cutoff_hour} PM EST) - no new trades")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking time restriction: {e}")
            return False

    def _should_close_all_positions(self) -> bool:
        """Check if we should force close all positions due to time cutoff."""
        try:
            est = pytz.timezone('US/Eastern')
            current_time_est = datetime.now(est).time()
            close_time = time(self.position_close_hour, self.position_close_minute)

            if current_time_est >= close_time:
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking position close time: {e}")
            return False

    def _calculate_volume_pace(self, current_volume: float, avg_daily_volume: float) -> float:
        """
        Calculate volume PACE (rate) accounting for time of day.

        This fixes the volume comparison by comparing:
        - Actual volume traded so far today
        - vs. EXPECTED volume at this time of day (based on historical average)

        Example:
        - Market open: 9:30 AM EST
        - Current time: 10:00 AM EST (30 minutes elapsed = 7.7% of trading day)
        - Expected volume by now: 7.7% of avg_daily_volume
        - If actual volume is 15% of avg_daily_volume, pace = 15% / 7.7% = 1.95x

        Args:
            current_volume: Today's cumulative volume so far
            avg_daily_volume: Historical average FULL DAY volume

        Returns:
            Volume pace multiplier (e.g., 2.0 = trading at 2x normal pace)
        """
        try:
            est = pytz.timezone('US/Eastern')
            now_est = datetime.now(est)
            current_time = now_est.time()

            # Market hours: 9:30 AM - 4:00 PM EST (6.5 hours = 390 minutes)
            market_open = time(9, 30)
            market_close = time(16, 0)

            # Convert times to minutes since midnight for calculation
            current_minutes = current_time.hour * 60 + current_time.minute
            open_minutes = market_open.hour * 60 + market_open.minute
            close_minutes = market_close.hour * 60 + market_close.minute

            # If before market open, assume we're at market open time
            if current_minutes < open_minutes:
                current_minutes = open_minutes

            # If after market close, assume we're at market close
            if current_minutes > close_minutes:
                current_minutes = close_minutes

            # Calculate percentage of trading day elapsed
            minutes_elapsed = current_minutes - open_minutes
            total_trading_minutes = close_minutes - open_minutes  # 390 minutes

            if total_trading_minutes <= 0:
                return 0.0

            pct_day_elapsed = minutes_elapsed / total_trading_minutes

            # Expected volume at this point in the day
            # Using a simple linear model (in reality, volume is higher at open/close)
            expected_volume = avg_daily_volume * pct_day_elapsed

            if expected_volume <= 0:
                return 0.0

            # Calculate pace: actual / expected
            volume_pace = current_volume / expected_volume

            # Log detailed calculation for debugging
            logger.info(f"   Volume Pace Calculation:")
            logger.info(f"      Current time: {current_time}")
            logger.info(f"      Trading day elapsed: {pct_day_elapsed*100:.1f}% ({minutes_elapsed} of {total_trading_minutes} mins)")
            logger.info(f"      Today's volume: {current_volume:,.0f}")
            logger.info(f"      Avg daily volume: {avg_daily_volume:,.0f}")
            logger.info(f"      Expected by now: {expected_volume:,.0f} ({pct_day_elapsed*100:.1f}% of avg)")
            logger.info(f"      Volume pace: {volume_pace:.2f}x")

            return volume_pace

        except Exception as e:
            logger.error(f"Error calculating volume pace: {e}")
            # Fallback to simple ratio if calculation fails
            return current_volume / avg_daily_volume if avg_daily_volume > 0 else 0.0

    def _check_daily_loss_limit(self, potential_loss: float) -> bool:
        """
        Check if adding this trade would exceed daily loss limit.

        Formula: Available risk = $600 - (current_potential_loss) + realized_pnl
        """
        try:
            # Get potential loss from all open positions
            open_positions_risk = self._calculate_open_positions_risk()

            # Calculate available risk
            available_risk = self.max_daily_loss - open_positions_risk + self.daily_realized_pnl

            logger.info(f"💰 Risk Check:")
            logger.info(f"   Max daily loss: ${self.max_daily_loss:.2f}")
            logger.info(f"   Open positions risk: ${open_positions_risk:.2f}")
            logger.info(f"   Today's realized P/L: ${self.daily_realized_pnl:.2f}")
            logger.info(f"   Available risk: ${available_risk:.2f}")
            logger.info(f"   This trade risk: ${potential_loss:.2f}")

            if potential_loss > available_risk:
                logger.warning(f"❌ Trade rejected: Risk ${potential_loss:.2f} exceeds available ${available_risk:.2f}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            return False

    def _is_stock_shortable(self, symbol: str) -> bool:
        """
        Check if a stock is shortable via Alpaca API.

        Returns:
            True if the stock can be shorted, False otherwise
        """
        try:
            # Get asset information from Alpaca
            asset = order_manager.api.get_asset(symbol)

            # Check if the stock is shortable
            is_shortable = asset.shortable if hasattr(asset, 'shortable') else False
            easy_to_borrow = asset.easy_to_borrow if hasattr(asset, 'easy_to_borrow') else False

            if is_shortable:
                logger.info(f"✅ {symbol}: Shortable={is_shortable}, Easy to borrow={easy_to_borrow}")
            else:
                logger.info(f"❌ {symbol}: Not shortable")

            return is_shortable

        except Exception as e:
            logger.error(f"Error checking if {symbol} is shortable: {e}")
            # On error, assume not shortable (safer default)
            return False

    def _calculate_open_positions_risk(self) -> float:
        """Calculate total potential loss from all open positions."""
        try:
            total_risk = 0.0

            open_positions = portfolio_service.get_open_positions()

            for position in open_positions:
                entry_price = abs(float(position.get('entry_price', 0)))
                stop_loss = abs(float(position.get('stop_loss', 0)))
                quantity = abs(int(position.get('quantity', 0)))

                potential_loss = abs(entry_price - stop_loss) * quantity
                total_risk += potential_loss

            return total_risk

        except Exception as e:
            logger.error(f"Error calculating open positions risk: {e}")
            return 0.0

    async def scan_for_opportunities(self, symbols: List[str]) -> List[TradeSetup]:
        """
        Scan watchlist for trading opportunities.
        """
        setups = []

        # Check time restriction
        if not self._check_time_restriction():
            return setups

        for symbol in symbols:
            try:
                # WHIPSAW PREVENTION: Check cooldown after stop out
                if symbol in self.recent_stop_outs:
                    time_since_stop = time_module.time() - self.recent_stop_outs[symbol]
                    if time_since_stop < self.stop_out_cooldown:
                        remaining = int(self.stop_out_cooldown - time_since_stop)
                        logger.debug(f"⏸️ {symbol} in cooldown after stop out ({remaining}s remaining)")
                        continue
                    else:
                        # Cooldown expired, remove from tracking
                        del self.recent_stop_outs[symbol]

                # Get market data
                df_daily = market_data_service.get_bars(symbol, timeframe='1Day', limit=100)
                df_5min = market_data_service.get_bars(symbol, timeframe='5Min', limit=300)  # Increased for better MACD calculation

                if df_daily is None or df_5min is None or len(df_daily) < 30 or len(df_5min) < 50:
                    continue

                # Analyze for gap
                gap_data = self._detect_gap(df_daily, symbol)

                if not gap_data['has_gap']:
                    continue

                # Check if gap is within acceptable range
                gap_pct = abs(gap_data['gap_percent'])
                if gap_pct < self.min_gap_percent or gap_pct > self.max_gap_percent:
                    continue

                # Analyze entry conditions on 5-min chart
                setup = await self._analyze_entry_conditions(
                    symbol=symbol,
                    df=df_5min,
                    df_daily=df_daily,
                    gap_data=gap_data
                )

                if setup:
                    setups.append(setup)
                    logger.info(f"✅ Setup found: {symbol} - {setup.signal_type.value} - {setup.gap_percent:.2f}% gap")

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue

        return setups

    def _detect_gap(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Detect price gaps."""
        try:
            if len(df) < 2:
                return {'has_gap': False}

            current = df.iloc[-1]
            previous = df.iloc[-2]

            gap_percent = ((current['open'] - previous['close']) / previous['close']) * 100

            # Determine gap direction and size
            is_gap_up = gap_percent > 0
            gap_size = abs(gap_percent)

            has_significant_gap = gap_size >= self.min_gap_percent

            return {
                'has_gap': has_significant_gap,
                'gap_percent': gap_percent,
                'gap_direction': 'up' if is_gap_up else 'down',
                'gap_size': gap_size,
                'previous_close': float(previous['close']),
                'current_open': float(current['open']),
                'current_price': float(current['close'])
            }

        except Exception as e:
            logger.error(f"Error detecting gap for {symbol}: {e}")
            return {'has_gap': False}

    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate MACD indicator."""
        try:
            close = df['close']

            # Calculate EMAs
            ema_fast = close.ewm(span=self.macd_fast, adjust=False).mean()
            ema_slow = close.ewm(span=self.macd_slow, adjust=False).mean()

            # MACD line
            macd = ema_fast - ema_slow

            # Signal line
            signal = macd.ewm(span=self.macd_signal, adjust=False).mean()

            # Histogram
            histogram = macd - signal

            df_copy = df.copy()
            df_copy['macd'] = macd
            df_copy['macd_signal'] = signal
            df_copy['macd_histogram'] = histogram

            return df_copy

        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            return df

    def _detect_macd_divergence(self, df: pd.DataFrame, lookback: int = 20) -> Tuple[bool, str]:
        """
        Detect MACD divergence over the last N bars.

        Returns: (has_divergence, divergence_type)
        divergence_type: 'bullish', 'bearish', or 'none'
        """
        try:
            if len(df) < lookback + 5:
                return False, 'none'

            # Get last N bars
            recent_df = df.iloc[-lookback:]

            prices = recent_df['close'].values
            macd_values = recent_df['macd'].values

            # Find price lows and highs
            price_min_idx = prices.argmin()
            price_max_idx = prices.argmax()

            # Find MACD lows and highs
            macd_min_idx = macd_values.argmin()
            macd_max_idx = macd_values.argmax()

            # Bullish divergence: Price makes lower low, MACD makes higher low
            if price_min_idx < len(prices) - 5:  # Low not at the very end
                subsequent_prices = prices[price_min_idx+1:]
                subsequent_macd = macd_values[price_min_idx+1:]

                if len(subsequent_prices) > 0:
                    second_price_low = subsequent_prices.min()
                    second_macd_low = subsequent_macd.min()

                    if second_price_low < prices[price_min_idx] and second_macd_low > macd_values[price_min_idx]:
                        logger.info(f"🔍 Bullish MACD divergence detected")
                        return True, 'bullish'

            # Bearish divergence: Price makes higher high, MACD makes lower high
            if price_max_idx < len(prices) - 5:  # High not at the very end
                subsequent_prices = prices[price_max_idx+1:]
                subsequent_macd = macd_values[price_max_idx+1:]

                if len(subsequent_prices) > 0:
                    second_price_high = subsequent_prices.max()
                    second_macd_high = subsequent_macd.max()

                    if second_price_high > prices[price_max_idx] and second_macd_high < macd_values[price_max_idx]:
                        logger.info(f"🔍 Bearish MACD divergence detected")
                        return True, 'bearish'

            return False, 'none'

        except Exception as e:
            logger.error(f"Error detecting MACD divergence: {e}")
            return False, 'none'

    async def _analyze_entry_conditions(self, symbol: str, df: pd.DataFrame,
                                       df_daily: pd.DataFrame, gap_data: Dict[str, Any]) -> Optional[TradeSetup]:
        """
        Analyze if entry conditions are met using Gap + Volume + MACD + RSI.
        """
        try:
            # Calculate indicators
            df_with_macd = self._calculate_macd(df)
            rsi = self.indicators.calculate_rsi(df['close'], period=14)
            atr = self.indicators.calculate_atr(df, period=14)

            # Volume analysis using TIME-AWARE volume pace comparison
            # FIXED: Compare volume PACE (rate) vs expected pace at this time of day
            # This solves the issue where early-day cumulative volume was being compared to full-day average
            quote_data = market_data_service.get_quote(symbol)
            today_volume = quote_data.get('volume', 0) if quote_data else 0

            # Get both cached baselines (average FULL DAY volume)
            avg_daily_volume_30d = redis_cache.get(f"avg_daily_volume_30d:{symbol}")
            avg_daily_volume_5d = redis_cache.get(f"avg_daily_volume_5d:{symbol}")

            volume_ratio_30d = 0.0
            volume_ratio_5d = 0.0

            if avg_daily_volume_30d and avg_daily_volume_30d > 0 and today_volume > 0:
                # Calculate volume PACE (accounts for time of day)
                volume_ratio_30d = self._calculate_volume_pace(today_volume, avg_daily_volume_30d)

            if avg_daily_volume_5d and avg_daily_volume_5d > 0 and today_volume > 0:
                # Calculate volume PACE (accounts for time of day)
                volume_ratio_5d = self._calculate_volume_pace(today_volume, avg_daily_volume_5d)

            # Use MORE PERMISSIVE of the two (max ratio honors both standards)
            volume_ratio = max(volume_ratio_30d, volume_ratio_5d)

            # Current values
            current_price = df['close'].iloc[-1]
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50
            current_atr = atr.iloc[-1] if not atr.empty else 0

            current_macd = df_with_macd['macd'].iloc[-1]
            current_signal = df_with_macd['macd_signal'].iloc[-1]
            current_histogram = df_with_macd['macd_histogram'].iloc[-1]

            # MACD crossover detection
            prev_macd = df_with_macd['macd'].iloc[-2]
            prev_signal = df_with_macd['macd_signal'].iloc[-2]

            macd_bullish_cross = (prev_macd <= prev_signal) and (current_macd > current_signal)
            macd_bearish_cross = (prev_macd >= prev_signal) and (current_macd < current_signal)

            # MACD histogram threshold for valid signals (research-based)
            # Histogram between -0.20 and +0.20 is considered aggressive entry zone
            # RESTORED: 0.02 - strict threshold to filter out weak momentum and reduce false signals
            # TIME-AWARE: Relaxed threshold during market open (first 60 min) when MACD is still building
            est = pytz.timezone('US/Eastern')
            current_time_est = datetime.now(est).time()
            market_open_time = time(9, 30)
            early_trading_cutoff = time(10, 30)  # First hour after open

            # Relax threshold during first hour of trading (9:30-10:30 AM EST)
            if market_open_time <= current_time_est < early_trading_cutoff:
                macd_histogram_threshold = 0.012  # More lenient during market open
                logger.info(f"   ⏰ Early trading period - using relaxed MACD threshold: {macd_histogram_threshold}")
            else:
                macd_histogram_threshold = 0.02  # Strict threshold after 10:30 AM
                logger.debug(f"   MACD threshold: {macd_histogram_threshold} (normal hours)")

            # MACD divergence detection
            has_divergence, divergence_type = self._detect_macd_divergence(df_with_macd, self.divergence_lookback)

            # DETAILED LOGGING
            logger.info(f"📊 {symbol} Analysis @ ${current_price:.2f}")
            logger.info(f"   Gap: {gap_data['gap_percent']:.2f}% ({gap_data['gap_direction']})")
            logger.info(f"   Volume: {volume_ratio:.2f}x (5d: {volume_ratio_5d:.2f}x, 30d: {volume_ratio_30d:.2f}x) - threshold: {self.min_volume_ratio}x")
            logger.info(f"   RSI: {current_rsi:.1f}")
            logger.info(f"   MACD: {current_macd:.4f}, Signal: {current_signal:.4f}, Histogram: {current_histogram:.4f}")
            logger.info(f"   MACD Bullish Cross: {macd_bullish_cross}, Bearish Cross: {macd_bearish_cross}")
            logger.info(f"   MACD Divergence: {has_divergence} ({divergence_type})")

            # Log to analysis logger for API visibility
            analysis_logger._add_log(
                'info',
                f"Gap={gap_data['gap_percent']:.1f}%, Vol={volume_ratio:.1f}x, RSI={current_rsi:.1f}, "
                f"MACD={current_macd:.3f}, Signal={current_signal:.3f}, Div={divergence_type}",
                symbol,
                analysis_logger._get_trading_time()
            )

            # Determine signal type
            signal_type = SignalType.NONE
            setup_reasons = []
            signal_strength = 0

            # DETERMINE TRADE DIRECTION FROM MACD (NOT GAP!)
            # Gap is for screening only - MACD histogram determines bullish/bearish momentum
            # Positive histogram = bullish momentum → LONG
            # Negative histogram = bearish momentum → SHORT

            # LONG SETUP ANALYSIS - MACD showing bullish momentum
            if current_histogram > macd_histogram_threshold:
                is_long_valid = True

                # 1. Gap detected (any direction - just confirms volatility)
                gap_pct = abs(gap_data['gap_percent'])
                setup_reasons.append(f"Gap: {gap_data['gap_percent']:.2f}%")
                signal_strength += 2

                # 2. Volume confirmation (CRITICAL!)
                if volume_ratio >= self.min_volume_ratio:
                    setup_reasons.append(f"High volume: {volume_ratio:.1f}x average")
                    signal_strength += 3
                    logger.info(f"✅ {symbol} LONG: High volume confirmed at {volume_ratio:.1f}x")
                else:
                    is_long_valid = False
                    logger.info(f"❌ {symbol} LONG: Volume too low ({volume_ratio:.1f}x < {self.min_volume_ratio}x)")

                # 3. RSI confirmation
                if current_rsi < self.rsi_overbought:
                    setup_reasons.append(f"RSI not overbought: {current_rsi:.1f}")
                    signal_strength += 2
                    logger.info(f"✅ {symbol} LONG: RSI acceptable at {current_rsi:.1f}")
                else:
                    is_long_valid = False
                    logger.info(f"❌ {symbol} LONG: RSI overbought at {current_rsi:.1f}")

                # 4. MACD confirmation - bullish histogram with minimum threshold
                macd_confirmed = False
                if macd_bullish_cross:
                    setup_reasons.append("MACD bullish crossover")
                    signal_strength += 3
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} LONG: MACD bullish crossover")
                elif has_divergence and divergence_type == 'bullish':
                    setup_reasons.append("MACD bullish divergence")
                    signal_strength += 3
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} LONG: MACD bullish divergence detected")
                elif current_histogram > macd_histogram_threshold:
                    setup_reasons.append(f"MACD bullish (hist={current_histogram:.3f})")
                    signal_strength += 3  # INCREASED from +1 to +3
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} LONG: MACD histogram bullish ({current_histogram:.3f})")

                if not macd_confirmed:
                    is_long_valid = False
                    logger.info(f"❌ {symbol} LONG: No MACD confirmation")

                # Signal strength threshold: 7+ for strong signal
                # 2 (gap) + 3 (volume) + 2 (RSI) + 3 (MACD) = 10 max
                if is_long_valid and signal_strength >= 7:
                    signal_type = SignalType.LONG
                    logger.info(f"🎯 {symbol} LONG SIGNAL GENERATED! Strength: {signal_strength}/10")
                else:
                    logger.info(f"⚠️ {symbol} LONG: Signal strength insufficient ({signal_strength} < 7)")

            # SHORT SETUP ANALYSIS - MACD showing bearish momentum
            elif current_histogram < -macd_histogram_threshold:
                is_short_valid = True

                # 1. Gap detected (any direction - just confirms volatility)
                gap_pct = abs(gap_data['gap_percent'])
                setup_reasons.append(f"Gap: {gap_data['gap_percent']:.2f}%")
                signal_strength += 2

                # 2. Volume confirmation (CRITICAL!)
                if volume_ratio >= self.min_volume_ratio:
                    setup_reasons.append(f"High volume: {volume_ratio:.1f}x average")
                    signal_strength += 3
                    logger.info(f"✅ {symbol} SHORT: High volume confirmed at {volume_ratio:.1f}x")
                else:
                    is_short_valid = False
                    logger.info(f"❌ {symbol} SHORT: Volume too low ({volume_ratio:.1f}x < {self.min_volume_ratio}x)")

                # 3. RSI confirmation
                if current_rsi > self.rsi_oversold:
                    setup_reasons.append(f"RSI not oversold: {current_rsi:.1f}")
                    signal_strength += 2
                    logger.info(f"✅ {symbol} SHORT: RSI acceptable at {current_rsi:.1f}")
                else:
                    is_short_valid = False
                    logger.info(f"❌ {symbol} SHORT: RSI oversold at {current_rsi:.1f}")

                # 4. MACD confirmation - bearish histogram with minimum threshold
                macd_confirmed = False
                if macd_bearish_cross:
                    setup_reasons.append("MACD bearish crossover")
                    signal_strength += 3
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} SHORT: MACD bearish crossover")
                elif has_divergence and divergence_type == 'bearish':
                    setup_reasons.append("MACD bearish divergence")
                    signal_strength += 3
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} SHORT: MACD bearish divergence detected")
                elif current_histogram < -macd_histogram_threshold:
                    setup_reasons.append(f"MACD bearish (hist={current_histogram:.3f})")
                    signal_strength += 3  # INCREASED from +1 to +3
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} SHORT: MACD histogram bearish ({current_histogram:.3f})")

                if not macd_confirmed:
                    is_short_valid = False
                    logger.info(f"❌ {symbol} SHORT: No MACD confirmation")

                # Signal strength threshold: 7+ for strong signal
                # 2 (gap) + 3 (volume) + 2 (RSI) + 3 (MACD) = 10 max
                if is_short_valid and signal_strength >= 7:
                    signal_type = SignalType.SHORT
                    logger.info(f"🎯 {symbol} SHORT SIGNAL GENERATED! Strength: {signal_strength}/10")
                else:
                    logger.info(f"⚠️ {symbol} SHORT: Signal strength insufficient ({signal_strength} < 7)")

            # If no valid signal, return None with detailed rejection reasons
            if signal_type == SignalType.NONE:
                # Build detailed rejection reasons
                rejection_reasons = []

                # Determine what signal type was attempted based on MACD
                attempted_signal = "UNKNOWN"
                if current_histogram > macd_histogram_threshold:
                    attempted_signal = "LONG"
                elif current_histogram < -macd_histogram_threshold:
                    attempted_signal = "SHORT"
                else:
                    # MACD didn't meet threshold - this is the primary rejection
                    if abs(current_histogram) > 0:
                        if current_histogram > 0:
                            attempted_signal = "LONG"
                            rejection_reasons.append(f"MACD hist too weak ({current_histogram:.3f} < {macd_histogram_threshold})")
                        else:
                            attempted_signal = "SHORT"
                            rejection_reasons.append(f"MACD hist too weak ({current_histogram:.3f} > -{macd_histogram_threshold})")
                    else:
                        rejection_reasons.append(f"MACD hist neutral ({current_histogram:.3f})")

                # Check volume
                if volume_ratio < self.min_volume_ratio:
                    rejection_reasons.append(f"Vol too low ({volume_ratio:.1f}x < {self.min_volume_ratio}x)")

                # Check RSI based on signal type
                if attempted_signal == "LONG":
                    if current_rsi >= self.rsi_overbought:
                        rejection_reasons.append(f"RSI overbought ({current_rsi:.1f} >= {self.rsi_overbought})")
                elif attempted_signal == "SHORT":
                    if current_rsi <= self.rsi_oversold:
                        rejection_reasons.append(f"RSI oversold ({current_rsi:.1f} <= {self.rsi_oversold})")

                # Check signal strength
                if signal_strength < 7:
                    rejection_reasons.append(f"Signal strength insufficient ({signal_strength}/10 < 7)")

                # Build rejection message
                if not rejection_reasons:
                    rejection_reasons.append("No clear signal direction")

                rejection_msg = f"REJECTED [{attempted_signal}] - " + " | ".join(rejection_reasons)
                rejection_msg += f" | Gap={gap_data['gap_percent']:.1f}%, Vol={volume_ratio:.1f}x, RSI={current_rsi:.1f}, MACD={current_histogram:.3f}"

                logger.warning(f"❌ {symbol}: {rejection_msg}")
                analysis_logger._add_log(
                    'warning',
                    rejection_msg,
                    symbol,
                    analysis_logger._get_trading_time()
                )
                return None

            # Calculate entry levels
            entry_price = current_price

            # Calculate stop loss and target (ATR-based with MINIMUM DISTANCE enforcement)
            if signal_type == SignalType.LONG:
                # Calculate ATR-based stop
                atr_stop_distance = current_atr * self.atr_stop_multiplier

                # Calculate minimum stop distance (greater of $0.30 or 1.2% of price)
                min_stop_dollar = self.min_stop_distance_dollars
                min_stop_percent = entry_price * (self.min_stop_distance_percent / 100.0)
                min_stop_distance = max(min_stop_dollar, min_stop_percent)

                # Use the LARGER of ATR-based or minimum stop distance
                final_stop_distance = max(atr_stop_distance, min_stop_distance)
                stop_loss = entry_price - final_stop_distance
                target_price = entry_price + (final_stop_distance * 2.5)  # 2.5x risk for reward

            else:  # SHORT
                # Calculate ATR-based stop
                atr_stop_distance = current_atr * self.atr_stop_multiplier

                # Calculate minimum stop distance (greater of $0.30 or 1.2% of price)
                min_stop_dollar = self.min_stop_distance_dollars
                min_stop_percent = entry_price * (self.min_stop_distance_percent / 100.0)
                min_stop_distance = max(min_stop_dollar, min_stop_percent)

                # Use the LARGER of ATR-based or minimum stop distance
                final_stop_distance = max(atr_stop_distance, min_stop_distance)
                stop_loss = entry_price + final_stop_distance
                target_price = entry_price - (final_stop_distance * 2.5)

            # Validate levels
            if signal_type == SignalType.LONG:
                if target_price <= entry_price or stop_loss >= entry_price:
                    rejection_msg = f"REJECTED [LONG] - Invalid levels: Entry=${entry_price:.2f}, Stop=${stop_loss:.2f}, Target=${target_price:.2f}"
                    logger.warning(f"⚠️ {symbol}: {rejection_msg}")
                    analysis_logger._add_log('warning', rejection_msg, symbol, analysis_logger._get_trading_time())
                    return None
            else:
                if target_price >= entry_price or stop_loss <= entry_price:
                    rejection_msg = f"REJECTED [SHORT] - Invalid levels: Entry=${entry_price:.2f}, Stop=${stop_loss:.2f}, Target=${target_price:.2f}"
                    logger.warning(f"⚠️ {symbol}: {rejection_msg}")
                    analysis_logger._add_log('warning', rejection_msg, symbol, analysis_logger._get_trading_time())
                    return None

            # Calculate position size
            risk_per_share = abs(entry_price - stop_loss)
            potential_loss = risk_per_share * 1  # Placeholder for initial size calculation

            shares = risk_manager.calculate_position_size(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss
            )[0]

            if shares <= 0:
                signal_dir = "LONG" if signal_type == SignalType.LONG else "SHORT"
                rejection_msg = f"REJECTED [{signal_dir}] - Position size too small (shares={shares}): Entry=${entry_price:.2f}, Risk=${risk_per_share:.2f}/share"
                logger.warning(f"❌ {symbol}: {rejection_msg}")
                analysis_logger._add_log('warning', rejection_msg, symbol, analysis_logger._get_trading_time())
                return None

            # Calculate actual potential loss with real position size
            potential_loss = risk_per_share * shares

            # Check daily loss limit
            if not self._check_daily_loss_limit(potential_loss):
                signal_dir = "LONG" if signal_type == SignalType.LONG else "SHORT"
                rejection_msg = f"REJECTED [{signal_dir}] - Daily loss limit: Potential loss ${potential_loss:.2f} would exceed limit"
                logger.warning(f"❌ {symbol}: {rejection_msg}")
                analysis_logger._add_log('warning', rejection_msg, symbol, analysis_logger._get_trading_time())
                return None

            logger.info(f"✅ {symbol}: Entry=${entry_price:.2f}, Stop=${stop_loss:.2f}, Target=${target_price:.2f}, Size={shares}")

            # Create trade setup
            est = pytz.timezone('US/Eastern')
            setup = TradeSetup(
                symbol=symbol,
                signal_type=signal_type,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_price=target_price,
                position_size=shares,
                gap_percent=gap_data['gap_percent'],
                volume_ratio=volume_ratio,
                rsi_value=current_rsi,
                macd_value=current_macd,
                macd_signal=current_signal,
                macd_histogram=current_histogram,
                atr_value=current_atr,
                has_macd_divergence=has_divergence,
                divergence_type=divergence_type,
                signal_strength=signal_strength,
                setup_reasons=setup_reasons,
                confidence_score=min(signal_strength * 10, 95),
                timestamp=datetime.now(est)
            )

            return setup

        except Exception as e:
            logger.error(f"Error analyzing entry conditions for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def monitor_active_setups(self) -> List[Dict[str, Any]]:
        """Monitor active setups for entry signals."""
        if not self.is_active:
            return []

        # Check time restriction
        if not self._check_time_restriction():
            return []

        # Log how many setups we're monitoring
        if len(self.active_setups) > 0:
            logger.info(f"📋 Monitoring {len(self.active_setups)} active setups: {list(self.active_setups.keys())}")
        else:
            logger.debug("📋 No active setups to monitor")

        entry_signals = []

        for symbol, setup in list(self.active_setups.items()):
            try:
                # Get current market data
                df = market_data_service.get_bars(symbol, timeframe='1Min', limit=10)

                if df is None or len(df) < 2:
                    logger.debug(f"⚠️ {symbol}: Insufficient market data for entry signal")
                    continue

                current_price = df['close'].iloc[-1]

                # For this simplified strategy, enter immediately if setup is valid
                logger.info(f"🎯 {symbol}: Generating entry signal at ${current_price:.2f}")
                entry_signals.append({
                    'action': 'enter_trade',
                    'setup': setup,
                    'entry_signal': 'immediate',
                    'current_price': current_price
                })

            except Exception as e:
                logger.error(f"Error monitoring setup for {symbol}: {e}")
                continue

        return entry_signals

    async def execute_trade_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """Execute a trade based on the signal using LIMIT ORDERS."""
        try:
            setup: TradeSetup = signal['setup']

            # Final time check
            if not self._check_time_restriction():
                signal_dir = "LONG" if setup.signal_type == SignalType.LONG else "SHORT"
                rejection_msg = f"REJECTED [{signal_dir}] - Trading cutoff time reached"
                logger.warning(f"❌ {setup.symbol}: {rejection_msg}")
                analysis_logger._add_log('warning', rejection_msg, setup.symbol, analysis_logger._get_trading_time())
                self.active_setups.pop(setup.symbol, None)
                return None

            # Check if we already have a position
            existing_position = portfolio_service.get_position_by_symbol(setup.symbol)
            if existing_position:
                signal_dir = "LONG" if setup.signal_type == SignalType.LONG else "SHORT"
                rejection_msg = f"REJECTED [{signal_dir}] - Already have position in this symbol"
                logger.warning(f"❌ {setup.symbol}: {rejection_msg}")
                analysis_logger._add_log('warning', rejection_msg, setup.symbol, analysis_logger._get_trading_time())
                self.active_setups.pop(setup.symbol, None)
                return None

            # Check if we already traded this symbol today (prevent re-entry on same day)
            try:
                with get_db_session() as db:
                    # Use EST timezone for trading day calculation
                    est = pytz.timezone('US/Eastern')
                    today_start = datetime.now(est).replace(hour=0, minute=0, second=0, microsecond=0)

                    existing_trade_today = db.query(Trade).filter(
                        Trade.symbol == setup.symbol,
                        Trade.entry_time >= today_start
                    ).first()

                    if existing_trade_today:
                        signal_dir = "LONG" if setup.signal_type == SignalType.LONG else "SHORT"
                        rejection_msg = f"REJECTED [{signal_dir}] - Already traded this symbol today (prevent re-entry)"
                        logger.warning(f"❌ {setup.symbol}: {rejection_msg}")
                        logger.info(f"   Previous trade today: Entry @ {existing_trade_today.entry_time.strftime('%H:%M:%S')}")
                        analysis_logger._add_log('warning', rejection_msg, setup.symbol, analysis_logger._get_trading_time())
                        self.active_setups.pop(setup.symbol, None)
                        return None
            except Exception as e:
                logger.error(f"Error checking for existing trades today for {setup.symbol}: {e}")
                # Continue with trade if check fails (don't block on error)

            # Validate trade setup
            validation = risk_manager.validate_trade_setup(
                symbol=setup.symbol,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                target_price=setup.target_price
            )

            if not validation.get('is_valid', False):
                signal_dir = "LONG" if setup.signal_type == SignalType.LONG else "SHORT"
                errors = ", ".join(validation.get('errors', ['Unknown validation error']))
                rejection_msg = f"REJECTED [{signal_dir}] - Validation failed: {errors}"
                logger.warning(f"❌ {setup.symbol}: {rejection_msg}")
                analysis_logger._add_log('warning', rejection_msg, setup.symbol, analysis_logger._get_trading_time())
                self.active_setups.pop(setup.symbol, None)
                return None

            # Check if stock is shortable (only for SHORT signals)
            if setup.signal_type == SignalType.SHORT:
                if not self._is_stock_shortable(setup.symbol):
                    rejection_msg = f"REJECTED [SHORT] - Stock is not shortable"
                    logger.warning(f"❌ {setup.symbol}: {rejection_msg}")
                    analysis_logger._add_log('warning', rejection_msg, setup.symbol, analysis_logger._get_trading_time())
                    self.active_setups.pop(setup.symbol, None)
                    return None
                logger.info(f"✅ {setup.symbol}: Confirmed shortable - proceeding with SHORT trade")

            # Place ENTRY ORDER with TRAILING STOP + TAKE PROFIT
            side = 'buy' if setup.signal_type == SignalType.LONG else 'sell'

            logger.info(f"🎯 EXECUTING TRADE for {setup.symbol}:")
            logger.info(f"   Side: {side}, Qty: {setup.position_size}")
            logger.info(f"   Entry Limit: ${setup.entry_price:.2f}")
            logger.info(f"   Trailing Stop: 1.5x ATR (placed after fill)")
            logger.info(f"   Take Profit: ${setup.target_price:.2f}")

            # Place entry order (trailing stop + take profit placed automatically after fill)
            order_id = order_manager.place_bracket_order(
                symbol=setup.symbol,
                side=side,
                quantity=setup.position_size,
                stop_loss=setup.stop_loss,
                take_profit=setup.target_price,
                limit_price=setup.entry_price  # Use limit price for entry
            )

            if order_id:
                # Remove from active setups
                self.active_setups.pop(setup.symbol, None)

                logger.info(f"✅ TRADE PLACED: {setup.symbol} {side} {setup.position_size} shares")
                logger.info(f"   Entry Order ID: {order_id}")
                logger.info(f"   Trailing stop + take profit will be placed after entry fills")

                # Create database records
                trade_id = order_id
                try:
                    db_trade_id = await self._create_trade_record(setup, order_id)
                    if db_trade_id:
                        trade_id = db_trade_id

                    await self._create_position_record(setup, trade_id)
                    logger.info(f"✅ Database records created for {setup.symbol}")

                except Exception as e:
                    logger.warning(f"Could not create database records: {e}")

                # Add to active positions
                est = pytz.timezone('US/Eastern')
                self.active_positions[setup.symbol] = {
                    'setup': setup,
                    'trade_id': trade_id,
                    'order_id': order_id,
                    'entry_time': datetime.now(est),
                    'has_trailing_stop': True,  # Trailing stop placed automatically after entry fills
                    'tier': '🔄 Native Trailing Stop'
                }

                logger.info(f"✅ {setup.symbol}: Added to active position tracking")
                return trade_id

            else:
                logger.error(f"❌ Order placement failed for {setup.symbol}")
                return None

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _create_trade_record(self, setup: TradeSetup, order_id: str) -> str:
        """Create trade record in database."""
        try:
            with get_db_session() as db:
                # Use EST timezone for consistency with re-entry filter
                est = pytz.timezone('US/Eastern')

                trade = Trade(
                    symbol=setup.symbol,
                    side='long' if setup.signal_type == SignalType.LONG else 'short',
                    quantity=setup.position_size,
                    entry_price=Decimal(str(setup.entry_price)),
                    stop_loss=Decimal(str(setup.stop_loss)),
                    target_price=Decimal(str(setup.target_price)),
                    strategy='proprietary_gap_macd_rsi',
                    setup_type=setup.setup_type,  # Use the string directly
                    alpaca_order_id=order_id,
                    entry_time=datetime.now(est),
                    status='pending'  # Use string value, will update to 'filled' when order fills
                )

                db.add(trade)
                db.commit()
                db.refresh(trade)

                logger.info(f"✅ Trade record created in database: {trade.id}")
                return str(trade.id)

        except Exception as e:
            logger.error(f"❌ Error creating trade record for {setup.symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""

    async def _create_position_record(self, setup: TradeSetup, trade_id: str) -> str:
        """Create position record in database."""
        try:
            with get_db_session() as db:
                current_price = market_data_service.get_current_price(setup.symbol)

                position = Position(
                    symbol=setup.symbol,
                    quantity=setup.position_size if setup.signal_type == SignalType.LONG else -setup.position_size,
                    entry_price=Decimal(str(setup.entry_price)),
                    current_price=Decimal(str(current_price)) if current_price else Decimal(str(setup.entry_price)),
                    stop_loss=Decimal(str(setup.stop_loss)),
                    target_price=Decimal(str(setup.target_price)),
                    status=PositionStatus.OPEN,
                    strategy='proprietary_gap_macd_rsi',
                    setup_type=setup.setup_type,  # Use string directly
                    trade_id=trade_id
                )

                position.calculate_unrealized_pnl()

                db.add(position)
                db.commit()
                db.refresh(position)

                logger.info(f"✅ Position record created in database: {position.id}")
                return str(position.id)

        except Exception as e:
            logger.error(f"❌ Error creating position record for {setup.symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""

    def _track_stop_out(self, symbol: str) -> None:
        """
        Track when a position is stopped out to prevent immediate re-entry (whipsaw prevention).

        Args:
            symbol: Stock symbol that was stopped out
        """
        self.recent_stop_outs[symbol] = time_module.time()
        logger.info(f"🛑 {symbol}: Stopped out - cooldown activated for {int(self.stop_out_cooldown/60)} minutes")

    async def force_close_position(self, symbol: str, position_data: Dict, reason: str = "Time cutoff") -> bool:
        """
        Force close a position immediately with a market order.

        This cancels all associated orders (trailing stops, take profit limits) and
        exits the position at market price.

        Args:
            symbol: Stock symbol
            position_data: Position information
            reason: Reason for force close (for logging)

        Returns:
            True if successfully closed, False otherwise
        """
        try:
            # Track stop out if this is a stop loss trigger (not time cutoff)
            if "stop" in reason.lower():
                self._track_stop_out(symbol)
            setup: TradeSetup = position_data['setup']

            logger.info(f"⏰ {symbol}: FORCE CLOSING POSITION - {reason}")
            logger.info(f"   Position size: {setup.position_size} shares")
            logger.info(f"   Entry: ${setup.entry_price:.2f}")

            # Step 1: Cancel ALL open orders for this symbol (including orphaned take-profits)
            try:
                logger.info(f"{symbol}: Cancelling ALL open orders for this symbol...")

                # Get all open orders for this symbol
                open_orders = order_manager.api.list_orders(status='open', symbols=symbol)

                if open_orders:
                    logger.info(f"{symbol}: Found {len(open_orders)} open orders to cancel")
                    for order in open_orders:
                        logger.info(f"  Cancelling {order.type} order {order.id} ({order.side} @ ${order.limit_price if order.limit_price else order.stop_price})")
                        order_manager.cancel_order(order.id)
                    logger.info(f"✅ {symbol}: All open orders cancelled")
                else:
                    logger.info(f"{symbol}: No open orders to cancel")

            except Exception as e:
                logger.warning(f"{symbol}: Error cancelling orders: {e} (continuing with position close)")

            # Step 2: Close position with market order
            side = 'sell' if setup.signal_type == SignalType.LONG else 'buy'

            logger.info(f"{symbol}: Placing market order to close position...")
            close_order_id = order_manager.place_market_order(
                symbol=symbol,
                side=side,
                quantity=setup.position_size,
                trade_id=position_data.get('trade_id')
            )

            if close_order_id:
                logger.info(f"✅ {symbol}: Position closed via market order {close_order_id}")

                # Remove from active positions
                if symbol in self.active_positions:
                    del self.active_positions[symbol]

                # Update database position status
                try:
                    with get_db_session() as db:
                        position = db.query(Position).filter(
                            Position.symbol == symbol,
                            Position.status == PositionStatus.OPEN
                        ).first()

                        if position:
                            position.status = PositionStatus.CLOSED
                            db.commit()
                            logger.info(f"{symbol}: Database position updated to CLOSED")

                except Exception as e:
                    logger.warning(f"{symbol}: Error updating database position: {e}")

                return True
            else:
                logger.error(f"❌ {symbol}: Failed to place market close order")
                return False

        except Exception as e:
            logger.error(f"Error force closing {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def monitor_positions(self) -> List[Dict[str, Any]]:
        """
        Monitor active positions and their trailing stops.

        Functions:
        1. Syncs existing Alpaca positions into tracking system
        2. Monitors positions for current P/L
        3. Logs position status with trailing stop indicators
        4. Force closes all positions after cutoff time (3:50 PM EST)

        Note: Trailing stops are placed automatically after entry fills.
        """
        logger.info(f"🔍 monitor_positions() called - checking for positions to monitor")
        exit_signals = []

        # SYNC EXISTING ALPACA POSITIONS INTO self.active_positions
        # This handles positions that existed before bot restart
        try:
            logger.info(f"🔄 Checking for Alpaca positions to sync... (tracking {len(self.active_positions)} internally)")
            alpaca_positions = order_manager.get_open_positions()
            logger.info(f"🔄 Found {len(alpaca_positions) if alpaca_positions else 0} Alpaca positions")

            if alpaca_positions:
                for alpaca_pos in alpaca_positions:
                    symbol = alpaca_pos.get('symbol')

                    # If position exists in Alpaca but not in our tracking dict, add it
                    if symbol and symbol not in self.active_positions:
                        logger.info(f"🔄 {symbol}: Syncing existing Alpaca position into tracking system...")

                        # Create minimal TradeSetup from Alpaca position data
                        qty = abs(alpaca_pos.get('qty', 0))
                        entry_price = float(alpaca_pos.get('avg_entry_price', 0))
                        current_price = float(alpaca_pos.get('current_price', entry_price))
                        unrealized_pl = float(alpaca_pos.get('unrealized_pl', 0))
                        side = alpaca_pos.get('side', 'long')

                        # Calculate ATR-based stops (fallback if we don't have original)
                        df = market_data_service.get_bars(symbol, timeframe='5Min', limit=100)
                        if df is not None and len(df) > 0:
                            atr = self.indicators.calculate_atr(df, period=14)
                            current_atr = atr.iloc[-1] if not atr.empty else (entry_price * 0.02)
                        else:
                            current_atr = entry_price * 0.02  # 2% fallback

                        stop_distance = max(current_atr * self.atr_stop_multiplier, 0.30, entry_price * 0.012)

                        if side == 'long':
                            stop_loss = entry_price - stop_distance
                            target_price = entry_price + (stop_distance * 2.5)
                            signal_type = SignalType.LONG
                        else:
                            stop_loss = entry_price + stop_distance
                            target_price = entry_price - (stop_distance * 2.5)
                            signal_type = SignalType.SHORT

                        # Create minimal TradeSetup
                        est = pytz.timezone('US/Eastern')
                        synced_setup = TradeSetup(
                            symbol=symbol,
                            signal_type=signal_type,
                            entry_price=entry_price,
                            stop_loss=stop_loss,
                            target_price=target_price,
                            position_size=int(qty),
                            gap_percent=0.0,  # Unknown for synced positions
                            volume_ratio=0.0,  # Unknown
                            rsi_value=50.0,  # Unknown
                            macd_value=0.0,  # Unknown
                            macd_signal=0.0,  # Unknown
                            macd_histogram=0.0,  # Unknown
                            atr_value=current_atr,
                            has_macd_divergence=False,
                            divergence_type='none',
                            signal_strength=7,  # Assume valid
                            setup_reasons=['Synced from existing position'],
                            confidence_score=0.7,
                            timestamp=datetime.now(est)  # Add required timestamp field
                        )

                        # Check if position already has a trailing stop
                        has_existing_trailing = False
                        try:
                            orders = order_manager.api.list_orders(status='open', symbols=symbol)
                            for order in orders:
                                if order.type == 'trailing_stop':
                                    has_existing_trailing = True
                                    logger.info(f"✅ {symbol}: Already has trailing stop - will not upgrade again")
                                    break
                        except Exception as e:
                            logger.warning(f"{symbol}: Could not check for existing trailing stops: {e}")

                        # Add to tracking (est already declared above)
                        self.active_positions[symbol] = {
                            'setup': synced_setup,
                            'trade_id': None,  # Unknown for synced positions
                            'order_id': None,  # Unknown
                            'entry_time': datetime.now(est) - timedelta(minutes=30),  # Assume entered 30 min ago
                            'synced_from_alpaca': True,  # Flag to identify synced positions
                            'has_trailing_stop': has_existing_trailing,  # Check if already has trailing stop
                            'trailing_stop_id': None,
                            'tier': '🔄 Native Trailing Stop' if has_existing_trailing else '📍 Fixed Stop'
                        }

                        logger.info(f"✅ {symbol}: Synced into tracking - Entry: ${entry_price:.2f}, Stop: ${stop_loss:.2f}, Profit: ${unrealized_pl:.2f}")
                        logger.info(f"   Current: ${current_price:.2f}, Has trailing stop: {has_existing_trailing}")
        except Exception as e:
            logger.warning(f"Error syncing Alpaca positions: {e}")

        # Check if we should force close all positions due to time cutoff
        if self._should_close_all_positions():
            if len(self.active_positions) > 0:
                logger.warning(f"⏰ POSITION CLOSING TIME REACHED ({self.position_close_hour}:00 PM EST)")
                logger.warning(f"   Force closing {len(self.active_positions)} open position(s)...")

                # Close all positions
                for symbol, pos_data in list(self.active_positions.items()):
                    await self.force_close_position(
                        symbol=symbol,
                        position_data=pos_data,
                        reason=f"Time cutoff ({self.position_close_hour}:00 PM EST)"
                    )

                logger.warning(f"✅ All positions closed due to time cutoff")
                return exit_signals

        # Log active position monitoring
        if len(self.active_positions) > 0:
            logger.info(f"💼 Monitoring {len(self.active_positions)} active position(s): {list(self.active_positions.keys())}")
            if self.enable_trailing_stops:
                logger.info(f"   🔄 Trailing stops ENABLED - checking for upgrade opportunities")
            else:
                logger.info(f"   ❌ Trailing stops DISABLED")

        for symbol, pos_data in list(self.active_positions.items()):
            try:
                setup: TradeSetup = pos_data['setup']

                # NOTE: Trailing stops are placed automatically via OTO orders - no upgrade needed!
                # Positions already have trailing stops from entry via OTO order class

                # Get current price for logging
                df = market_data_service.get_bars(symbol, timeframe='1Min', limit=5)
                if df is not None and len(df) > 0:
                    current_price = df['close'].iloc[-1]

                    # Calculate P/L
                    pnl = (current_price - setup.entry_price) * setup.position_size
                    if setup.signal_type == SignalType.SHORT:
                        pnl = -pnl

                    profit_pct = (pnl / (setup.entry_price * setup.position_size)) * 100

                    # Log position status with trailing stop indicator
                    stop_status = pos_data.get('tier', '📍 Fixed Stop')

                    logger.info(f"💼 {symbol}: ${current_price:.2f} | P/L: ${pnl:.2f} ({profit_pct:+.2f}%) | {stop_status}")

            except Exception as e:
                logger.error(f"Error monitoring position {symbol}: {e}")
                continue

        return exit_signals

    async def add_gap_setup(self, setup_data: Dict[str, Any]) -> bool:
        """Add a gap setup to active monitoring."""
        try:
            symbol = setup_data.get('symbol')
            if not symbol:
                logger.debug(f"add_gap_setup: No symbol provided")
                return False

            if symbol in self.active_setups:
                logger.debug(f"add_gap_setup: {symbol} already in active setups, skipping")
                return False

            # Check time restriction
            if not self._check_time_restriction():
                logger.info(f"add_gap_setup: {symbol} blocked by time restriction")
                return False

            logger.info(f"🔍 Analyzing {symbol} for gap setup (Gap: {setup_data.get('gap_percent', 0):.1f}%)")

            # Run full analysis
            df = market_data_service.get_bars(symbol, timeframe='5Min', limit=300)  # Increased for better MACD calculation
            df_daily = market_data_service.get_bars(symbol, timeframe='1Day', limit=100)

            if df is None or df_daily is None or len(df) < 50:
                logger.warning(f"⚠️ {symbol}: Insufficient historical data for analysis")
                return False

            gap_data = {
                'has_gap': True,
                'gap_percent': setup_data.get('gap_percent', 0),
                'gap_direction': 'up' if setup_data.get('gap_percent', 0) > 0 else 'down',
                'current_price': setup_data.get('current_price', 0),
                'previous_close': setup_data.get('previous_close', 0)
            }

            setup = await self._analyze_entry_conditions(symbol, df, df_daily, gap_data)

            if setup:
                self.active_setups[symbol] = setup
                logger.info(f"✅ Gap setup added: {symbol} - {setup.signal_type.value} (strength: {setup.signal_strength}/10)")
                analysis_logger._add_log(
                    'success',
                    f"Setup added: {setup.signal_type.value} entry at ${setup.entry_price:.2f}",
                    symbol,
                    analysis_logger._get_trading_time()
                )
                return True
            else:
                logger.info(f"❌ {symbol}: Setup analysis failed - no valid signal generated")

            return False

        except Exception as e:
            logger.error(f"Error adding gap setup for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


# Global strategy instance
proprietary_strategy = ProprietaryStrategy()
