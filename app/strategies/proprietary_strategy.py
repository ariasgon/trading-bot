"""
Proprietary Trading Strategy - Gap + Ichimoku + RSI + ATR
========================================================

This strategy combines:
1. Gap Analysis (from Oliver Velez methodology)
2. Ichimoku Cloud for trend and signal confirmation
3. RSI for oversold/overbought confirmation
4. ATR-based stop losses
5. Support/Resistance levels (for stop loss calculation only)
6. Works for both LONG and SHORT positions

Entry Rules (SIMPLIFIED - No Volume/Pullback Requirements):
-----------
LONG:
- Gap up detected (0.75% - 8%)
- Ichimoku: Price above cloud + TK bullish cross (or Tenkan > Kijun)
- RSI < 70 (not overbought, bonus for RSI < 35)

SHORT:
- Gap down detected (0.75% - 8%)
- Ichimoku: Price below cloud + TK bearish cross (or Tenkan < Kijun)
- RSI > 30 (not oversold, bonus for RSI > 65)

REMOVED REQUIREMENTS (per user request):
- Volume confirmation (no longer required)
- Price pullback to Support/VWAP (no longer required)
- Price rally to Resistance (no longer required)

Exit Rules:
----------
LONG:
- Stop Loss: Entry - (2 × ATR) or below nearest support (whichever is tighter)
- Target 1 (50%): Kijun-sen (base line)
- Target 2 (50%): Cloud top edge or RSI > 70

SHORT:
- Stop Loss: Entry + (2 × ATR) or above nearest resistance (whichever is tighter)
- Target 1 (50%): Kijun-sen (base line)
- Target 2 (50%): Cloud bottom edge or RSI < 30

Logging:
--------
All entry analysis includes detailed logging of:
- RSI values
- Ichimoku Cloud levels (Tenkan, Kijun, Cloud Top/Bottom)
- Price position relative to cloud
- TK cross signals
- Reason for entry/rejection
"""

import asyncio
import logging
import pandas as pd
from decimal import Decimal
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from app.strategies.indicators import TechnicalIndicators
from app.strategies.ichimoku_indicator import ichimoku_calculator
from app.services.analysis_logger import analysis_logger
from app.services.market_data import market_data_service
from app.services.order_manager import order_manager
from app.services.risk_manager import risk_manager
from app.services.portfolio import portfolio_service
from app.services.ml_model_manager import ml_model_manager
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
    target_1: float  # 50% exit - Kijun-sen
    target_2: float  # 50% exit - Cloud edge or RSI extreme
    position_size: int

    # Signal details
    gap_percent: float
    ichimoku_signal: str
    rsi_value: float
    atr_value: float

    # Support/Resistance
    support_level: float
    resistance_level: float

    # Metadata
    signal_strength: int
    setup_reasons: List[str]
    confidence_score: float
    timestamp: datetime


class ProprietaryStrategy:
    """
    Proprietary trading strategy combining Gap + Ichimoku + RSI + ATR.
    """

    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.is_active = False
        self.active_setups: Dict[str, TradeSetup] = {}
        self.active_positions: Dict[str, Dict] = {}
        self.daily_trades_count = 0
        self.max_daily_trades = 50

        # Strategy parameters
        self.min_gap_percent = 0.75
        self.max_gap_percent = 8.0
        self.min_volume_ratio = 1.5
        self.atr_stop_multiplier = 2.0

        # RSI thresholds
        self.rsi_oversold = 35
        self.rsi_overbought = 65
        self.rsi_extreme_high = 70
        self.rsi_extreme_low = 30

        # ML Enhancement Parameters
        self.use_ml_scoring = True
        self.ml_minimum_score = 0.40  # 40% win probability minimum
        self.ml_model_loaded = False

    async def initialize_strategy(self) -> bool:
        """Initialize the strategy for the trading day."""
        try:
            logger.info("Initializing Proprietary Trading Strategy...")

            # Reset daily counters
            self.daily_trades_count = 0
            self.active_setups = {}
            self.active_positions = {}

            # Load ML model if enabled
            if self.use_ml_scoring:
                logger.info("Loading ML entry scoring model...")
                self.ml_model_loaded = ml_model_manager.load_model()
                if self.ml_model_loaded:
                    logger.info("ML model loaded - enhanced scoring enabled")
                else:
                    logger.warning("ML model not found - using base strategy")
                    self.use_ml_scoring = False

            # Check pre-trade conditions
            conditions = risk_manager.check_pre_trade_conditions()
            if not conditions.get('can_trade', False):
                logger.warning(f"Cannot trade: {conditions.get('reasons', [])}")
                return False

            # Cache strategy status
            redis_cache.set("proprietary_strategy_status", {
                "is_active": True,
                "initialized_at": datetime.now().isoformat(),
                "daily_trades_count": 0
            })

            self.is_active = True
            logger.info("✅ Proprietary Trading Strategy initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing strategy: {e}")
            return False

    async def scan_for_opportunities(self, symbols: List[str]) -> List[TradeSetup]:
        """
        Scan watchlist for trading opportunities.

        Args:
            symbols: List of stock symbols to scan

        Returns:
            List of valid trade setups
        """
        setups = []

        for symbol in symbols:
            try:
                # Get market data (1-day bars for gap analysis, 5-min for entry)
                df_daily = market_data_service.get_bars(symbol, timeframe='1Day', limit=100)
                df_5min = market_data_service.get_bars(symbol, timeframe='5Min', limit=100)

                if df_daily is None or df_5min is None or len(df_daily) < 60 or len(df_5min) < 60:
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
            is_gap_down = gap_percent < 0
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

    def _get_ml_score(self, symbol: str, setup_data: dict, df: pd.DataFrame) -> tuple:
        '''Get ML score for trade quality.'''
        if not self.use_ml_scoring or not self.ml_model_loaded:
            return 0.60, 'ENTER', {}  # Neutral if ML disabled

        try:
            # Extract features
            current_price = df['close'].iloc[-1]
            rsi = self.indicators.calculate_rsi(df['close'], period=14).iloc[-1]

            # Build feature dict
            features = {
                'gap_percent': abs(setup_data.get('gap_percent', 0)),
                'rsi': rsi if not pd.isna(rsi) else 50,
                'stoch_rsi': 0.5,  # Placeholder
                'mfi': 50,  # Placeholder
                'atr_percent': (setup_data.get('atr', 0) / current_price * 100) if current_price > 0 else 3,
                'volume_ratio': setup_data.get('volume_ratio', 1.5),
                'entry_hour': datetime.now().hour,
                'price': current_price,
                'ichimoku_strength': setup_data.get('ichimoku_strength', 50)
            }

            # Get ML prediction
            win_prob, recommendation, details = ml_model_manager.predict_trade_quality(features)

            logger.info(f"ML Score for {symbol}: {win_prob:.1%} ({recommendation})")
            return win_prob, recommendation, details

        except Exception as e:
            logger.error(f"ML scoring error: {e}")
            return 0.60, 'ENTER', {}

    async def _analyze_entry_conditions(self, symbol: str, df: pd.DataFrame,
                                       gap_data: Dict[str, Any]) -> Optional[TradeSetup]:
        """
        Analyze if entry conditions are met for a trade setup.
        """
        try:
            # Calculate indicators
            df_with_ichimoku = ichimoku_calculator.calculate(df)
            ichimoku_signals = ichimoku_calculator.get_signals(df_with_ichimoku)

            rsi = self.indicators.calculate_rsi(df['close'], period=14)
            atr = self.indicators.calculate_atr(df, period=14)
            vwap = self.indicators.calculate_vwap(df)

            # Volume analysis - DISABLED per user request
            # avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
            # current_volume = df['volume'].iloc[-1]
            # volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            # Support/Resistance
            support_resistance = self.indicators.calculate_support_resistance(df)
            support = support_resistance.get('support', 0)
            resistance = support_resistance.get('resistance', 0)

            # Current values
            current_price = df['close'].iloc[-1]
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50
            current_atr = atr.iloc[-1] if not atr.empty else 0
            current_vwap = vwap.iloc[-1] if not vwap.empty else current_price

            # Get Ichimoku levels
            tenkan_sen = df_with_ichimoku['tenkan_sen'].iloc[-1]
            kijun_sen = df_with_ichimoku['kijun_sen'].iloc[-1]
            senkou_span_a = df_with_ichimoku['senkou_span_a'].iloc[-1]
            senkou_span_b = df_with_ichimoku['senkou_span_b'].iloc[-1]
            cloud_top = max(senkou_span_a, senkou_span_b)
            cloud_bottom = min(senkou_span_a, senkou_span_b)

            # DETAILED LOGGING FOR DEBUGGING
            logger.info(f"📊 {symbol} Analysis @ ${current_price:.2f}")
            logger.info(f"   RSI: {current_rsi:.1f}")
            logger.info(f"   Ichimoku Cloud: Top=${cloud_top:.2f}, Bottom=${cloud_bottom:.2f}")
            logger.info(f"   Tenkan-sen: ${tenkan_sen:.2f}, Kijun-sen: ${kijun_sen:.2f}")
            logger.info(f"   Price vs Cloud: {ichimoku_signals['price_vs_cloud']}")
            logger.info(f"   TK Cross: {ichimoku_signals.get('tk_cross', 'none')}")
            logger.info(f"   Tenkan above Kijun: {ichimoku_signals['tenkan_above_kijun']}")

            # Also log to analysis logger for API visibility
            analysis_logger._add_log(
                'info',
                f"RSI={current_rsi:.1f}, Price=${current_price:.2f}, Cloud={ichimoku_signals['price_vs_cloud']}, "
                f"Tenkan=${tenkan_sen:.2f}, Kijun=${kijun_sen:.2f}, TK_Cross={ichimoku_signals.get('tk_cross', 'none')}",
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

                # 2. Ichimoku bullish (RELAXED: price above or inside cloud + TK bullish alignment)
                # For gap trades, allow price inside cloud as it may be breaking out
                price_position_ok = ichimoku_signals['price_vs_cloud'] in ['above', 'inside']
                tk_bullish = (ichimoku_signals['tk_cross'] == 'bullish' or
                             ichimoku_signals['tenkan_above_kijun'])

                ichimoku_bullish = price_position_ok and tk_bullish

                if ichimoku_bullish:
                    if ichimoku_signals['price_vs_cloud'] == 'above':
                        setup_reasons.append(f"Ichimoku bullish (above cloud): {ichimoku_signals['signal']}")
                        signal_strength += 3
                    else:
                        setup_reasons.append(f"Ichimoku bullish (inside cloud, breaking out): {ichimoku_signals['signal']}")
                        signal_strength += 2  # Slightly lower confidence for inside cloud
                    logger.info(f"✅ {symbol} LONG: Ichimoku bullish confirmed (price_vs_cloud={ichimoku_signals['price_vs_cloud']})")
                else:
                    # Check if at least TK is bullish even if price below cloud
                    if tk_bullish and ichimoku_signals['price_vs_cloud'] != 'below':
                        setup_reasons.append(f"Ichimoku TK bullish: {ichimoku_signals['signal']}")
                        signal_strength += 1
                        logger.info(f"⚠️ {symbol} LONG: Weak Ichimoku (TK bullish but price {ichimoku_signals['price_vs_cloud']} cloud)")
                    else:
                        is_long_valid = False
                        logger.info(f"❌ {symbol} LONG: Ichimoku not bullish (price_vs_cloud={ichimoku_signals['price_vs_cloud']}, tk_cross={ichimoku_signals.get('tk_cross', 'none')}, tenkan_above_kijun={ichimoku_signals['tenkan_above_kijun']})")

                # 3. RSI confirmation (relaxed: just not overbought)
                if current_rsi < self.rsi_oversold:
                    setup_reasons.append(f"RSI oversold: {current_rsi:.1f}")
                    signal_strength += 2
                    logger.info(f"✅ {symbol} LONG: RSI oversold at {current_rsi:.1f}")
                elif current_rsi < 70:  # Not overbought
                    setup_reasons.append(f"RSI acceptable: {current_rsi:.1f}")
                    signal_strength += 1
                    logger.info(f"✅ {symbol} LONG: RSI acceptable at {current_rsi:.1f}")
                else:
                    is_long_valid = False
                    logger.info(f"❌ {symbol} LONG: RSI too high (overbought) at {current_rsi:.1f}")

                # Signal strength threshold: LOWERED to 4 (was 5) for gap trades
                # 2 from gap + 2 from ichimoku + 1 from RSI = 5 typical
                # Minimum: 2 from gap + 1 from weak ichimoku + 1 from RSI = 4
                if is_long_valid and signal_strength >= 4:
                    signal_type = SignalType.LONG
                    logger.info(f"🎯 {symbol} LONG SIGNAL GENERATED! Strength: {signal_strength}/7+")
                else:
                    logger.info(f"⚠️ {symbol} LONG: Signal strength insufficient ({signal_strength} < 4) or conditions not met")

            # SHORT SETUP ANALYSIS
            elif gap_data['gap_direction'] == 'down':
                is_short_valid = True

                # 1. Gap down detected
                setup_reasons.append(f"Gap down: {gap_data['gap_percent']:.2f}%")
                signal_strength += 2

                # 2. Ichimoku bearish (RELAXED: price below or inside cloud + TK bearish alignment)
                # For gap trades, allow price inside cloud as it may be breaking down
                price_position_ok = ichimoku_signals['price_vs_cloud'] in ['below', 'inside']
                tk_bearish = (ichimoku_signals['tk_cross'] == 'bearish' or
                             not ichimoku_signals['tenkan_above_kijun'])

                ichimoku_bearish = price_position_ok and tk_bearish

                if ichimoku_bearish:
                    if ichimoku_signals['price_vs_cloud'] == 'below':
                        setup_reasons.append(f"Ichimoku bearish (below cloud): {ichimoku_signals['signal']}")
                        signal_strength += 3
                    else:
                        setup_reasons.append(f"Ichimoku bearish (inside cloud, breaking down): {ichimoku_signals['signal']}")
                        signal_strength += 2  # Slightly lower confidence for inside cloud
                    logger.info(f"✅ {symbol} SHORT: Ichimoku bearish confirmed (price_vs_cloud={ichimoku_signals['price_vs_cloud']})")
                else:
                    # Check if at least TK is bearish even if price above cloud
                    if tk_bearish and ichimoku_signals['price_vs_cloud'] != 'above':
                        setup_reasons.append(f"Ichimoku TK bearish: {ichimoku_signals['signal']}")
                        signal_strength += 1
                        logger.info(f"⚠️ {symbol} SHORT: Weak Ichimoku (TK bearish but price {ichimoku_signals['price_vs_cloud']} cloud)")
                    else:
                        is_short_valid = False
                        logger.info(f"❌ {symbol} SHORT: Ichimoku not bearish (price_vs_cloud={ichimoku_signals['price_vs_cloud']}, tk_cross={ichimoku_signals.get('tk_cross', 'none')}, tenkan_above_kijun={ichimoku_signals['tenkan_above_kijun']})")

                # 3. RSI confirmation (relaxed: just not oversold)
                if current_rsi > self.rsi_overbought:
                    setup_reasons.append(f"RSI overbought: {current_rsi:.1f}")
                    signal_strength += 2
                    logger.info(f"✅ {symbol} SHORT: RSI overbought at {current_rsi:.1f}")
                elif current_rsi > 30:  # Not oversold
                    setup_reasons.append(f"RSI acceptable: {current_rsi:.1f}")
                    signal_strength += 1
                    logger.info(f"✅ {symbol} SHORT: RSI acceptable at {current_rsi:.1f}")
                else:
                    is_short_valid = False
                    logger.info(f"❌ {symbol} SHORT: RSI too low (oversold) at {current_rsi:.1f}")

                # Signal strength threshold: LOWERED to 4 (was 5) for gap trades
                # 2 from gap + 2 from ichimoku + 1 from RSI = 5 typical
                # Minimum: 2 from gap + 1 from weak ichimoku + 1 from RSI = 4
                if is_short_valid and signal_strength >= 4:
                    signal_type = SignalType.SHORT
                    logger.info(f"🎯 {symbol} SHORT SIGNAL GENERATED! Strength: {signal_strength}/7+")
                else:
                    logger.info(f"⚠️ {symbol} SHORT: Signal strength insufficient ({signal_strength} < 4) or conditions not met")

            # If no valid signal, return None
            if signal_type == SignalType.NONE:
                return None

            # Calculate entry levels
            entry_price = current_price

            # Calculate stop loss (ATR-based or support/resistance)
            if signal_type == SignalType.LONG:
                atr_stop = entry_price - (current_atr * self.atr_stop_multiplier)
                support_stop = support * 0.995  # 0.5% below support
                stop_loss = max(atr_stop, support_stop)  # Use tighter stop

                # Targets - must be ABOVE entry for LONG
                # Use Kijun if it's above entry, otherwise use ATR-based target
                if kijun_sen > entry_price:
                    target_1 = kijun_sen
                else:
                    target_1 = entry_price + (current_atr * 1.5)  # ATR-based target

                # Target 2 should be higher than target 1
                if cloud_top > target_1:
                    target_2 = cloud_top
                else:
                    target_2 = entry_price + (current_atr * 3.0)  # Larger ATR-based target

            else:  # SHORT
                atr_stop = entry_price + (current_atr * self.atr_stop_multiplier)
                resistance_stop = resistance * 1.005  # 0.5% above resistance
                stop_loss = min(atr_stop, resistance_stop)  # Use tighter stop

                # Targets - must be BELOW entry for SHORT
                # Use Kijun if it's below entry, otherwise use ATR-based target
                if kijun_sen < entry_price:
                    target_1 = kijun_sen
                else:
                    target_1 = entry_price - (current_atr * 1.5)  # ATR-based target

                # Target 2 should be lower than target 1
                if cloud_bottom < target_1:
                    target_2 = cloud_bottom
                else:
                    target_2 = entry_price - (current_atr * 3.0)  # Larger ATR-based target

            # Validate target direction
            if signal_type == SignalType.LONG:
                if target_1 <= entry_price or target_2 <= target_1:
                    logger.warning(f"⚠️ {symbol} LONG: Invalid targets - T1=${target_1:.2f}, T2=${target_2:.2f}, Entry=${entry_price:.2f}")
                    return None
                logger.info(f"✅ {symbol} LONG: Entry=${entry_price:.2f}, Stop=${stop_loss:.2f}, T1=${target_1:.2f}, T2=${target_2:.2f}")
            else:
                if target_1 >= entry_price or target_2 >= target_1:
                    logger.warning(f"⚠️ {symbol} SHORT: Invalid targets - T1=${target_1:.2f}, T2=${target_2:.2f}, Entry=${entry_price:.2f}")
                    return None
                logger.info(f"✅ {symbol} SHORT: Entry=${entry_price:.2f}, Stop=${stop_loss:.2f}, T1=${target_1:.2f}, T2=${target_2:.2f}")

            # Calculate position size
            shares = risk_manager.calculate_position_size(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss
            )[0]

            if shares <= 0:
                return None

            # ML Enhancement: Score trade quality
            if self.use_ml_scoring and self.ml_model_loaded:
                win_prob, recommendation, ml_details = self._get_ml_score(symbol, gap_data, df)

                # Reject if ML score too low
                if win_prob < self.ml_minimum_score:
                    logger.info(f"ML REJECT {symbol}: {win_prob:.1%} < {self.ml_minimum_score:.1%}")
                    return None

                # Adjust position size based on ML confidence
                if recommendation == 'STRONG_ENTER':
                    shares = int(shares * 1.3)  # Increase by 30%
                elif recommendation == 'REDUCE_SIZE':
                    shares = int(shares * 0.7)  # Reduce by 30%

                logger.info(f"ML APPROVED {symbol}: {win_prob:.1%} - {recommendation}")

            # Create trade setup
            setup = TradeSetup(
                symbol=symbol,
                signal_type=signal_type,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=target_2,
                position_size=shares,
                gap_percent=gap_data['gap_percent'],
                ichimoku_signal=ichimoku_signals['signal'],
                rsi_value=current_rsi,
                atr_value=current_atr,
                support_level=support,
                resistance_level=resistance,
                signal_strength=signal_strength,
                setup_reasons=setup_reasons,
                confidence_score=min(signal_strength * 10, 95),
                timestamp=datetime.now()
            )

            return setup

        except Exception as e:
            logger.error(f"Error analyzing entry conditions for {symbol}: {e}")
            return None

    async def monitor_active_setups(self) -> List[Dict[str, Any]]:
        """Monitor active setups for entry signals."""
        if not self.is_active:
            return []

        entry_signals = []

        for symbol, setup in list(self.active_setups.items()):
            try:
                # Get current market data
                df = market_data_service.get_bars(symbol, timeframe='1Min', limit=10)

                if df is None or len(df) < 2:
                    continue

                current_price = df['close'].iloc[-1]

                # Check if entry conditions are still valid
                should_enter = self._check_immediate_entry(setup, current_price, df)

                if should_enter:
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

    def _check_immediate_entry(self, setup: TradeSetup, current_price: float,
                               df: pd.DataFrame) -> bool:
        """Check if immediate entry is warranted."""
        try:
            # For LONG: price is reasonable and above stop loss
            if setup.signal_type == SignalType.LONG:
                # Entry if price is within 3% of entry price and above stop loss
                price_deviation = abs(current_price - setup.entry_price) / setup.entry_price
                above_stop = current_price > setup.stop_loss
                price_reasonable = price_deviation <= 0.03  # 3% tolerance

                # Also check that we haven't already exceeded target 1
                below_target = current_price < setup.target_1

                return above_stop and price_reasonable and below_target

            # For SHORT: price is reasonable and below stop loss
            elif setup.signal_type == SignalType.SHORT:
                # Entry if price is within 3% of entry price and below stop loss
                price_deviation = abs(current_price - setup.entry_price) / setup.entry_price
                below_stop = current_price < setup.stop_loss
                price_reasonable = price_deviation <= 0.03  # 3% tolerance

                # Also check that we haven't already exceeded target 1 (for SHORT, target is BELOW entry)
                above_target = current_price > setup.target_1  # Price should still be above target (not yet reached)

                return below_stop and price_reasonable and above_target

            return False

        except Exception as e:
            logger.error(f"Error checking entry for {setup.symbol}: {e}")
            return False

    async def execute_trade_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """
        Execute a trade based on the signal.
        """
        try:
            setup: TradeSetup = signal['setup']

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
                target_price=setup.target_1
            )

            if not validation.get('is_valid', False):
                logger.warning(f"Trade validation failed for {setup.symbol}: {validation.get('errors', [])}")
                self.active_setups.pop(setup.symbol, None)
                return None

            # Place BRACKET ORDER with stop loss and take profit
            side = 'buy' if setup.signal_type == SignalType.LONG else 'sell'

            logger.info(f"🎯 EXECUTING BRACKET ORDER for {setup.symbol}:")
            logger.info(f"   Side: {side}, Qty: {setup.position_size}")
            logger.info(f"   Entry: ${setup.entry_price:.2f}")
            logger.info(f"   Stop Loss: ${setup.stop_loss:.2f}")
            logger.info(f"   Take Profit (Target 1): ${setup.target_1:.2f}")

            order_id = order_manager.place_bracket_order(
                symbol=setup.symbol,
                side=side,
                quantity=setup.position_size,
                stop_loss=setup.stop_loss,
                take_profit=setup.target_1  # Using target_1 for take profit
            )

            if order_id:
                # Remove from active setups
                self.active_setups.pop(setup.symbol, None)

                # Update trade count
                self.daily_trades_count += 1

                logger.info(f"✅ BRACKET ORDER PLACED: {setup.symbol} {side} {setup.position_size} shares @ ${setup.entry_price}")
                logger.info(f"   Order ID: {order_id}")

                # Try to create database records, but don't fail if DB is unavailable
                trade_id = order_id  # Use order_id as fallback trade_id
                try:
                    # Create trade record
                    db_trade_id = await self._create_trade_record(setup, order_id)
                    if db_trade_id:
                        trade_id = db_trade_id

                    # Create position record
                    await self._create_position_record(setup, trade_id)

                    logger.info(f"✅ Database records created for {setup.symbol}")

                except Exception as e:
                    logger.warning(f"Could not create database records for {setup.symbol} (DB may be offline): {e}")
                    logger.info(f"Trade will continue with order_id {order_id} as trade_id")

                # Add to active positions for monitoring (even if DB failed)
                self.active_positions[setup.symbol] = {
                    'setup': setup,
                    'trade_id': trade_id,
                    'order_id': order_id,
                    'entry_time': datetime.now(),
                    'scaled_out_50': False
                }

                logger.info(f"✅ Trade executed: {setup.symbol} {side} {setup.position_size} shares")
                return trade_id

            else:
                logger.error(f"❌ Order placement failed for {setup.symbol}")
                return None

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
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
                    target_price=Decimal(str(setup.target_1)),
                    strategy='proprietary_gap_ichimoku',
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
                    target_price=Decimal(str(setup.target_1)),
                    status=PositionStatus.OPEN,
                    strategy='proprietary_gap_ichimoku',
                    setup_type=setup.signal_type.value,
                    trade_id=trade_id
                )

                position.calculate_unrealized_pnl()

                db.add(position)
                db.commit()
                db.refresh(position)

                logger.info(f"✅ Position record created for {setup.symbol}")

                return str(position.id)

        except Exception as e:
            logger.error(f"Error creating position record: {e}")
            return ""

    async def _place_protective_orders(self, setup: TradeSetup) -> Dict[str, Any]:
        """Place stop loss and take profit orders."""
        try:
            protective_orders = {}

            # Place stop loss
            stop_order_id = order_manager.place_stop_loss_order(
                symbol=setup.symbol,
                quantity=setup.position_size,
                stop_price=setup.stop_loss
            )

            if stop_order_id:
                protective_orders['stop_loss'] = stop_order_id
                logger.info(f"Stop loss placed for {setup.symbol} @ ${setup.stop_loss}")

            # Place take profit at Target 1 (50% of position)
            half_position = setup.position_size // 2
            if half_position > 0:
                tp1_order_id = order_manager.place_limit_order(
                    symbol=setup.symbol,
                    side='sell' if setup.signal_type == SignalType.LONG else 'buy',
                    quantity=half_position,
                    limit_price=setup.target_1
                )

                if tp1_order_id:
                    protective_orders['take_profit_1'] = tp1_order_id
                    logger.info(f"Take profit 1 placed for {setup.symbol} @ ${setup.target_1}")

            return protective_orders

        except Exception as e:
            logger.error(f"Error placing protective orders: {e}")
            return {}

    async def monitor_positions(self) -> List[Dict[str, Any]]:
        """Monitor active positions for exit signals."""
        exit_signals = []

        for symbol, pos_data in list(self.active_positions.items()):
            try:
                setup: TradeSetup = pos_data['setup']

                # Get current market data
                df = market_data_service.get_bars(symbol, timeframe='1Min', limit=50)

                if df is None or len(df) < 2:
                    continue

                # Calculate current indicators
                df_with_ichimoku = ichimoku_calculator.calculate(df)
                rsi = self.indicators.calculate_rsi(df['close'], period=14)

                current_price = df['close'].iloc[-1]
                current_rsi = rsi.iloc[-1] if not rsi.empty else 50

                # Check exit conditions
                should_exit, reason = self._check_exit_conditions(
                    setup, current_price, current_rsi, df_with_ichimoku, pos_data
                )

                if should_exit:
                    exit_signals.append({
                        'symbol': symbol,
                        'reason': reason,
                        'exit_price': current_price
                    })

            except Exception as e:
                logger.error(f"Error monitoring position {symbol}: {e}")
                continue

        return exit_signals

    def _check_exit_conditions(self, setup: TradeSetup, current_price: float,
                               current_rsi: float, df_ichimoku: pd.DataFrame,
                               pos_data: Dict) -> Tuple[bool, str]:
        """Check if position should be exited."""
        try:
            # Stop loss hit
            if setup.signal_type == SignalType.LONG:
                if current_price <= setup.stop_loss:
                    return True, "stop_loss"

                # Target 2 hit with RSI extreme
                if current_price >= setup.target_2 or current_rsi >= self.rsi_extreme_high:
                    return True, "target_2_or_rsi_extreme"

                # Ichimoku reversal signal
                ichimoku_signals = ichimoku_calculator.get_signals(df_ichimoku)
                if ichimoku_signals['tk_cross'] == 'bearish':
                    return True, "ichimoku_reversal"

            else:  # SHORT
                if current_price >= setup.stop_loss:
                    return True, "stop_loss"

                # Target 2 hit with RSI extreme
                if current_price <= setup.target_2 or current_rsi <= self.rsi_extreme_low:
                    return True, "target_2_or_rsi_extreme"

                # Ichimoku reversal signal
                ichimoku_signals = ichimoku_calculator.get_signals(df_ichimoku)
                if ichimoku_signals['tk_cross'] == 'bullish':
                    return True, "ichimoku_reversal"

            return False, ""

        except Exception as e:
            logger.error(f"Error checking exit conditions: {e}")
            return False, ""

    async def add_gap_setup(self, setup_data: Dict[str, Any]) -> bool:
        """Add a gap setup to active monitoring."""
        try:
            symbol = setup_data.get('symbol')
            if not symbol or symbol in self.active_setups:
                return False

            # Run full analysis
            df = market_data_service.get_bars(symbol, timeframe='5Min', limit=100)
            if df is None or len(df) < 60:
                return False

            gap_data = {
                'has_gap': True,
                'gap_percent': setup_data.get('gap_percent', 0),
                'gap_direction': 'up' if setup_data.get('gap_percent', 0) > 0 else 'down',
                'current_price': setup_data.get('current_price', 0),
                'previous_close': setup_data.get('previous_close', 0)
            }

            setup = await self._analyze_entry_conditions(symbol, df, gap_data)

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
