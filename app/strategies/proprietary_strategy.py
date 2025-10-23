"""
Proprietary Trading Strategy - Gap + Volume + MACD + RSI
========================================================

Research-backed strategy combining the most effective indicators for gap trading:
1. Gap Analysis (0.75% - 20%)
2. Volume Confirmation (>2x average - CRITICAL for gap validation)
3. MACD with Divergence Detection (momentum + reversal signals)
4. RSI for overbought/oversold confirmation

Based on research showing 73-74% win rate for this combination.

Entry Rules:
-----------
LONG:
- Gap up detected (0.75% - 20%)
- Volume > 2x average (cumulative: today's total volume vs 30-day average daily volume)
- RSI < 70 (not overbought)
- MACD bullish crossover OR bullish divergence (20-bar lookback)
- Time: Before 12 PM EST

SHORT:
- Gap down detected (0.75% - 20%)
- Volume > 2x average (cumulative: today's total volume vs 30-day average daily volume)
- RSI > 30 (not oversold)
- MACD bearish crossover OR bearish divergence (20-bar lookback)
- Time: Before 12 PM EST

Exit Rules:
----------
- Stop Loss: Entry ± (2 × ATR)
- Target: ATR-based (1.5x ATR for partial, 3x ATR for full)
- Let bracket orders run to target (no early exits)

Risk Management:
---------------
- Max daily potential loss: $600
- Dynamic adjustment based on realized P/L
- If win $100 → can risk $500 more
- If lose $100 → can risk $500 more
- No trading after 11 AM EST
"""

import asyncio
import logging
import pandas as pd
import pytz
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
        self.min_volume_ratio = 2.0  # CRITICAL: Volume must be 2x average
        self.atr_stop_multiplier = 2.0

        # RSI thresholds
        self.rsi_overbought = 70
        self.rsi_oversold = 30

        # MACD parameters
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.divergence_lookback = 20  # Look back 20 bars for divergence

        # Risk Management
        self.max_daily_loss = 600.0  # Max $600 potential loss per day
        self.daily_realized_pnl = 0.0  # Track today's realized P/L

        # Time restriction
        self.trading_cutoff_hour = 12  # No trades after 12 PM EST (noon)
        self.position_close_hour = 13  # Close all positions by 1 PM EST
        self.position_close_minute = 0  # Close at exactly 1:00 PM

        # Trailing Stop Configuration
        self.enable_trailing_stops = True  # Enable trailing stop upgrades
        self.trailing_stop_percent = 2.0  # 2% trailing stop (recommended for gap trading)
        self.trailing_upgrade_profit_threshold = 1.0  # Upgrade to trailing stop at +1% profit

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

            # Log trailing stop configuration
            if self.enable_trailing_stops:
                logger.info(f"🔄 Trailing stops: ENABLED")
                logger.info(f"   Trail percentage: {self.trailing_stop_percent}%")
                logger.info(f"   Upgrade at profit: +{self.trailing_upgrade_profit_threshold}%")
            else:
                logger.info(f"📍 Trailing stops: DISABLED (using fixed stops only)")

            return True

        except Exception as e:
            logger.error(f"Error initializing strategy: {e}")
            return False

    def _get_todays_realized_pnl(self) -> float:
        """Get today's realized P/L from closed trades."""
        try:
            with get_db_session() as db:
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

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
                # Get market data
                df_daily = market_data_service.get_bars(symbol, timeframe='1Day', limit=100)
                df_5min = market_data_service.get_bars(symbol, timeframe='5Min', limit=100)

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

            # LONG SETUP ANALYSIS
            if gap_data['gap_direction'] == 'up':
                is_long_valid = True

                # 1. Gap up detected
                setup_reasons.append(f"Gap up: {gap_data['gap_percent']:.2f}%")
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

                # 4. MACD confirmation (crossover OR divergence)
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
                elif current_macd > current_signal:
                    setup_reasons.append("MACD above signal")
                    signal_strength += 1
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} LONG: MACD above signal line")

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

            # SHORT SETUP ANALYSIS
            elif gap_data['gap_direction'] == 'down':
                is_short_valid = True

                # 1. Gap down detected
                setup_reasons.append(f"Gap down: {gap_data['gap_percent']:.2f}%")
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

                # 4. MACD confirmation (crossover OR divergence)
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
                elif current_macd < current_signal:
                    setup_reasons.append("MACD below signal")
                    signal_strength += 1
                    macd_confirmed = True
                    logger.info(f"✅ {symbol} SHORT: MACD below signal line")

                if not macd_confirmed:
                    is_short_valid = False
                    logger.info(f"❌ {symbol} SHORT: No MACD confirmation")

                # Signal strength threshold: 7+ for strong signal
                if is_short_valid and signal_strength >= 7:
                    signal_type = SignalType.SHORT
                    logger.info(f"🎯 {symbol} SHORT SIGNAL GENERATED! Strength: {signal_strength}/10")
                else:
                    logger.info(f"⚠️ {symbol} SHORT: Signal strength insufficient ({signal_strength} < 7)")

            # If no valid signal, return None
            if signal_type == SignalType.NONE:
                return None

            # Calculate entry levels
            entry_price = current_price

            # Calculate stop loss and target (ATR-based)
            if signal_type == SignalType.LONG:
                stop_loss = entry_price - (current_atr * self.atr_stop_multiplier)
                target_price = entry_price + (current_atr * 1.5)  # 1.5x ATR target
            else:  # SHORT
                stop_loss = entry_price + (current_atr * self.atr_stop_multiplier)
                target_price = entry_price - (current_atr * 1.5)

            # Validate levels
            if signal_type == SignalType.LONG:
                if target_price <= entry_price or stop_loss >= entry_price:
                    logger.warning(f"⚠️ {symbol} LONG: Invalid levels")
                    return None
            else:
                if target_price >= entry_price or stop_loss <= entry_price:
                    logger.warning(f"⚠️ {symbol} SHORT: Invalid levels")
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
                return None

            # Calculate actual potential loss with real position size
            potential_loss = risk_per_share * shares

            # Check daily loss limit
            if not self._check_daily_loss_limit(potential_loss):
                logger.warning(f"❌ {symbol}: Trade rejected due to daily loss limit")
                return None

            logger.info(f"✅ {symbol}: Entry=${entry_price:.2f}, Stop=${stop_loss:.2f}, Target=${target_price:.2f}, Size={shares}")

            # Create trade setup
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
                timestamp=datetime.now()
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

        entry_signals = []

        for symbol, setup in list(self.active_setups.items()):
            try:
                # Get current market data
                df = market_data_service.get_bars(symbol, timeframe='1Min', limit=10)

                if df is None or len(df) < 2:
                    continue

                current_price = df['close'].iloc[-1]

                # For this simplified strategy, enter immediately if setup is valid
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
                logger.warning(f"❌ {setup.symbol}: Trading cutoff reached")
                self.active_setups.pop(setup.symbol, None)
                return None

            # Check if we already have a position
            existing_position = portfolio_service.get_position_by_symbol(setup.symbol)
            if existing_position:
                logger.warning(f"Already have position for {setup.symbol}. Skipping.")
                self.active_setups.pop(setup.symbol, None)
                return None

            # Validate trade setup
            validation = risk_manager.validate_trade_setup(
                symbol=setup.symbol,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                target_price=setup.target_price
            )

            if not validation.get('is_valid', False):
                logger.warning(f"Trade validation failed for {setup.symbol}: {validation.get('errors', [])}")
                self.active_setups.pop(setup.symbol, None)
                return None

            # Check if stock is shortable (only for SHORT signals)
            if setup.signal_type == SignalType.SHORT:
                if not self._is_stock_shortable(setup.symbol):
                    logger.warning(f"❌ {setup.symbol}: Stock is not shortable - skipping SHORT trade")
                    self.active_setups.pop(setup.symbol, None)
                    return None
                logger.info(f"✅ {setup.symbol}: Confirmed shortable - proceeding with SHORT trade")

            # Place BRACKET ORDER with LIMIT entry
            side = 'buy' if setup.signal_type == SignalType.LONG else 'sell'

            logger.info(f"🎯 EXECUTING BRACKET ORDER (LIMIT) for {setup.symbol}:")
            logger.info(f"   Side: {side}, Qty: {setup.position_size}")
            logger.info(f"   Entry Limit: ${setup.entry_price:.2f}")
            logger.info(f"   Stop Loss: ${setup.stop_loss:.2f}")
            logger.info(f"   Take Profit: ${setup.target_price:.2f}")

            # Place bracket order with limit entry
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

                logger.info(f"✅ BRACKET ORDER PLACED: {setup.symbol} {side} {setup.position_size} shares")
                logger.info(f"   Order ID: {order_id}")

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
                self.active_positions[setup.symbol] = {
                    'setup': setup,
                    'trade_id': trade_id,
                    'order_id': order_id,
                    'entry_time': datetime.now()
                }

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
                trade = Trade(
                    symbol=setup.symbol,
                    side='long' if setup.signal_type == SignalType.LONG else 'short',
                    quantity=setup.position_size,
                    entry_price=Decimal(str(setup.entry_price)),
                    stop_loss=Decimal(str(setup.stop_loss)),
                    target_price=Decimal(str(setup.target_price)),
                    strategy='proprietary_gap_macd_rsi',
                    setup_type=setup.signal_type.value,
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
                    setup_type=setup.signal_type.value,
                    trade_id=trade_id
                )

                position.calculate_unrealized_pnl()

                db.add(position)
                db.commit()
                db.refresh(position)

                return str(position.id)

        except Exception as e:
            logger.error(f"Error creating position record: {e}")
            return ""

    async def upgrade_to_trailing_stop(self, symbol: str, position_data: Dict) -> bool:
        """
        Upgrade a position from fixed stop to trailing stop once profitable.

        This implements the hybrid approach:
        1. Position enters with bracket order (fixed stop + take profit)
        2. Once position reaches profit threshold, cancel fixed stop
        3. Replace with trailing stop to lock in profits
        4. Keep take-profit in place for upside capture

        Args:
            symbol: Stock symbol
            position_data: Position information including setup and order IDs

        Returns:
            True if successfully upgraded, False otherwise
        """
        try:
            setup: TradeSetup = position_data['setup']
            entry_price = setup.entry_price

            # Get current price
            current_price = market_data_service.get_current_price(symbol)
            if not current_price:
                logger.warning(f"Could not get current price for {symbol}")
                return False

            # Calculate profit percentage
            if setup.signal_type == SignalType.LONG:
                profit_pct = ((current_price - entry_price) / entry_price) * 100
            else:  # SHORT
                profit_pct = ((entry_price - current_price) / entry_price) * 100

            # Check if we've reached the upgrade threshold
            if profit_pct >= self.trailing_upgrade_profit_threshold:
                logger.info(f"🔄 {symbol}: Position profitable ({profit_pct:.2f}%), upgrading to trailing stop...")

                # Get parent order ID
                parent_order_id = position_data.get('order_id')
                if not parent_order_id:
                    logger.warning(f"{symbol}: No parent order ID found, cannot upgrade")
                    return False

                # Cancel the fixed stop loss from bracket order
                logger.info(f"{symbol}: Cancelling fixed stop loss leg...")
                if order_manager.cancel_stop_loss_leg(parent_order_id):

                    # Place trailing stop order
                    side = 'sell' if setup.signal_type == SignalType.LONG else 'buy'
                    logger.info(f"{symbol}: Placing {self.trailing_stop_percent}% trailing stop...")

                    trailing_stop_id = order_manager.place_trailing_stop(
                        symbol=symbol,
                        side=side,
                        quantity=setup.position_size,
                        trail_percent=self.trailing_stop_percent,
                        trade_id=position_data.get('trade_id')
                    )

                    if trailing_stop_id:
                        # Mark position as upgraded
                        position_data['has_trailing_stop'] = True
                        position_data['trailing_stop_id'] = trailing_stop_id
                        position_data['upgraded_at_profit'] = profit_pct
                        position_data['upgraded_at_price'] = current_price

                        logger.info(f"✅ {symbol}: TRAILING STOP ACTIVE!")
                        logger.info(f"   Profit at upgrade: {profit_pct:.2f}%")
                        logger.info(f"   Entry: ${entry_price:.2f}, Current: ${current_price:.2f}")
                        logger.info(f"   Trail: {self.trailing_stop_percent}%")
                        logger.info(f"   Initial stop: ${current_price * (1 - self.trailing_stop_percent/100):.2f}")
                        logger.info(f"   Take profit still active at: ${setup.target_price:.2f}")
                        return True
                    else:
                        logger.error(f"❌ {symbol}: Failed to place trailing stop")
                        return False
                else:
                    logger.error(f"❌ {symbol}: Failed to cancel fixed stop loss")
                    return False

            return False

        except Exception as e:
            logger.error(f"Error upgrading {symbol} to trailing stop: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def force_close_position(self, symbol: str, position_data: Dict, reason: str = "Time cutoff") -> bool:
        """
        Force close a position immediately with a market order.

        This cancels all associated orders (bracket legs, trailing stops) and
        exits the position at market price.

        Args:
            symbol: Stock symbol
            position_data: Position information
            reason: Reason for force close (for logging)

        Returns:
            True if successfully closed, False otherwise
        """
        try:
            setup: TradeSetup = position_data['setup']

            logger.info(f"⏰ {symbol}: FORCE CLOSING POSITION - {reason}")
            logger.info(f"   Position size: {setup.position_size} shares")
            logger.info(f"   Entry: ${setup.entry_price:.2f}")

            # Step 1: Cancel all open orders for this symbol
            try:
                # Cancel parent order and all legs
                parent_order_id = position_data.get('order_id')
                if parent_order_id:
                    logger.info(f"{symbol}: Cancelling parent order {parent_order_id} and all legs...")
                    order_manager.cancel_order(parent_order_id)

                # Cancel trailing stop if present
                trailing_stop_id = position_data.get('trailing_stop_id')
                if trailing_stop_id:
                    logger.info(f"{symbol}: Cancelling trailing stop {trailing_stop_id}...")
                    order_manager.cancel_order(trailing_stop_id)

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
        Monitor active positions and upgrade to trailing stops when profitable.

        With trailing stops enabled:
        1. Monitors positions for profitability
        2. Upgrades to trailing stop once profit threshold reached
        3. Logs position status with trailing stop indicators
        4. Force closes all positions after 1 PM EST cutoff
        """
        exit_signals = []

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

        for symbol, pos_data in list(self.active_positions.items()):
            try:
                setup: TradeSetup = pos_data['setup']

                # Check if position needs trailing stop upgrade
                if self.enable_trailing_stops and not pos_data.get('has_trailing_stop', False):
                    await self.upgrade_to_trailing_stop(symbol, pos_data)

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
                    trailing_status = "🔄 Trailing" if pos_data.get('has_trailing_stop') else "📍 Fixed Stop"
                    logger.info(f"{trailing_status} {symbol}: Price=${current_price:.2f}, P/L=${pnl:.2f} ({profit_pct:+.2f}%)")

                    # Log additional info for trailing stops
                    if pos_data.get('has_trailing_stop'):
                        logger.info(f"   Upgraded at: {pos_data.get('upgraded_at_profit', 0):.2f}% profit")

            except Exception as e:
                logger.error(f"Error monitoring position {symbol}: {e}")
                continue

        return exit_signals

    async def add_gap_setup(self, setup_data: Dict[str, Any]) -> bool:
        """Add a gap setup to active monitoring."""
        try:
            symbol = setup_data.get('symbol')
            if not symbol or symbol in self.active_setups:
                return False

            # Check time restriction
            if not self._check_time_restriction():
                return False

            # Run full analysis
            df = market_data_service.get_bars(symbol, timeframe='5Min', limit=100)
            df_daily = market_data_service.get_bars(symbol, timeframe='1Day', limit=100)

            if df is None or df_daily is None or len(df) < 50:
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
                logger.info(f"✅ Gap setup added: {symbol} - {setup.signal_type.value}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error adding gap setup: {e}")
            return False


# Global strategy instance
proprietary_strategy = ProprietaryStrategy()
