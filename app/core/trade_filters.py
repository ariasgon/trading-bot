"""
Trade Filters and Risk Controls Module
======================================

Centralized module for all trading filters, blacklists, and risk controls:
- Ticker blacklist (volatile crypto miners)
- One-strike rule (max 1 loss per ticker per day)
- Priority tickers (leveraged ETFs, liquid tech)
- Market direction bias filter
- Circuit breaker (consecutive loss pause)
- Position and trade limits
- Enhanced trade logging
"""

import logging
import pytz
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.core.cache import redis_cache

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Ticker Blacklist - volatile crypto miners to avoid
BLACKLIST = [
    "MARA", "CLSK", "HUT", "RIOT", "BITF", "HIVE",
]

# One-Strike Rule - max losses per ticker before blocking
MAX_LOSSES_PER_TICKER_PER_DAY = 1

# Priority Tickers - categorized by liquidity and reliability
PRIORITY_TICKERS = {
    "tier_1": [
        "SQQQ", "TQQQ", "SOXL", "SOXS", "SPXU", "SPXL",
        "UVXY", "QLD", "QID", "TNA", "TZA"
    ],  # Leveraged ETFs - highest priority
    "tier_2": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA",
        "AMD", "MU", "WDC", "STX", "ORCL", "ADBE"
    ],  # Liquid tech
    "tier_3": [
        "PWR", "CAT", "DE", "GE", "HON"
    ],  # Industrials
}

# Market Direction Bias
class MarketBias(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    CHOPPY = "choppy"

# Market bias confidence multipliers
BIAS_CONFIDENCE = {
    MarketBias.BULLISH: {"long": 1.0, "short": 0.5},
    MarketBias.BEARISH: {"long": 0.5, "short": 1.0},
    MarketBias.CHOPPY: {"long": 0.7, "short": 0.7},
}

# Position Sizing
MAX_RISK_PER_TRADE_DOLLARS = 100  # Maximum $100 risk per trade
POSITION_SIZE_PERCENT = 0.02  # 2% of account per position (backup calculation)

# Time Restrictions (EST)
TRADING_START_TIME = time(9, 35)   # 9:35 AM EST (5 minutes after open)
TRADING_END_TIME = time(15, 45)    # 3:45 PM EST (15 minutes before close)

# Circuit Breaker
CONSECUTIVE_LOSSES_THRESHOLD = 3  # After 3 consecutive losses
CIRCUIT_BREAKER_PAUSE_MINUTES = 30  # Pause trading for 30 minutes

# Daily Limits
MAX_OPEN_POSITIONS = 10
MAX_TRADES_PER_DAY = 25
DAILY_MAX_LOSS_DOLLARS = 500  # $500 max loss
DAILY_MAX_LOSS_PERCENT = 0.02  # 2% of account


@dataclass
class TradeFilterState:
    """Tracks state for trade filtering decisions."""
    # One-strike rule tracking
    ticker_losses_today: Dict[str, int] = field(default_factory=dict)

    # Circuit breaker tracking
    consecutive_losses: int = 0
    circuit_breaker_until: Optional[datetime] = None

    # Daily tracking
    trades_today: int = 0
    daily_realized_pnl: float = 0.0
    trade_log: List[Dict[str, Any]] = field(default_factory=list)

    # Market bias
    current_market_bias: MarketBias = MarketBias.CHOPPY
    last_bias_check: Optional[datetime] = None


class TradeFilters:
    """
    Centralized trade filtering and risk control system.
    """

    def __init__(self):
        self.state = TradeFilterState()
        self.est = pytz.timezone('US/Eastern')

    def reset_daily_state(self):
        """Reset all daily tracking at start of new trading day."""
        self.state = TradeFilterState()
        logger.info("Trade filters reset for new trading day")

    # =========================================================================
    # BLACKLIST CHECK
    # =========================================================================

    def is_blacklisted(self, symbol: str) -> bool:
        """
        Check if ticker is on the blacklist.

        Returns:
            True if blacklisted (should NOT trade), False otherwise
        """
        is_blocked = symbol.upper() in BLACKLIST
        if is_blocked:
            logger.warning(f"BLOCKED: {symbol} is on the blacklist (volatile crypto miner)")
        return is_blocked

    # =========================================================================
    # ONE-STRIKE RULE
    # =========================================================================

    def record_loss(self, symbol: str):
        """Record a loss for a ticker (for one-strike rule)."""
        symbol = symbol.upper()
        current_losses = self.state.ticker_losses_today.get(symbol, 0)
        self.state.ticker_losses_today[symbol] = current_losses + 1

        logger.info(f"ONE-STRIKE: {symbol} now has {self.state.ticker_losses_today[symbol]} loss(es) today")

        # Also update consecutive losses for circuit breaker
        self.state.consecutive_losses += 1
        logger.info(f"CIRCUIT BREAKER: Consecutive losses now at {self.state.consecutive_losses}")

    def record_win(self, symbol: str):
        """Record a win (resets consecutive loss counter)."""
        self.state.consecutive_losses = 0
        logger.info(f"WIN recorded for {symbol} - consecutive loss counter reset")

    def is_ticker_blocked_by_losses(self, symbol: str) -> bool:
        """
        Check if ticker is blocked due to one-strike rule.

        Returns:
            True if blocked (already hit max losses today), False otherwise
        """
        symbol = symbol.upper()
        losses_today = self.state.ticker_losses_today.get(symbol, 0)

        if losses_today >= MAX_LOSSES_PER_TICKER_PER_DAY:
            logger.warning(f"ONE-STRIKE BLOCKED: {symbol} already has {losses_today} loss(es) today (max: {MAX_LOSSES_PER_TICKER_PER_DAY})")
            return True
        return False

    # =========================================================================
    # PRIORITY TICKERS
    # =========================================================================

    def get_ticker_priority(self, symbol: str) -> int:
        """
        Get priority tier for a ticker.

        Returns:
            1 = highest priority (tier_1)
            2 = medium priority (tier_2)
            3 = lower priority (tier_3)
            4 = no priority (other tickers)
        """
        symbol = symbol.upper()

        if symbol in PRIORITY_TICKERS["tier_1"]:
            return 1
        elif symbol in PRIORITY_TICKERS["tier_2"]:
            return 2
        elif symbol in PRIORITY_TICKERS["tier_3"]:
            return 3
        else:
            return 4

    def is_priority_ticker(self, symbol: str) -> bool:
        """Check if ticker is in any priority tier."""
        return self.get_ticker_priority(symbol) <= 3

    def sort_by_priority(self, symbols: List[str]) -> List[str]:
        """Sort symbols by priority (highest priority first)."""
        return sorted(symbols, key=lambda s: self.get_ticker_priority(s))

    # =========================================================================
    # MARKET DIRECTION BIAS
    # =========================================================================

    def check_market_bias(self) -> MarketBias:
        """
        Check market direction using SPY.

        Returns:
            MarketBias enum indicating current market direction
        """
        try:
            # Only check every 5 minutes to avoid excessive API calls
            now = datetime.now(self.est)
            if (self.state.last_bias_check and
                (now - self.state.last_bias_check).total_seconds() < 300):
                return self.state.current_market_bias

            # Lazy import to avoid circular dependency
            from app.services.market_data import market_data_service

            # Get SPY data
            spy_bars = market_data_service.get_bars("SPY", timeframe="5Min", limit=20)

            if spy_bars is None or len(spy_bars) < 10:
                logger.warning("Could not get SPY data for market bias check")
                return MarketBias.CHOPPY

            # Calculate short-term trend using EMA
            close_prices = spy_bars['close'].values

            # Simple trend detection
            # Compare current price to 10-period moving average
            ma_10 = close_prices[-10:].mean()
            current_price = close_prices[-1]

            # Also check price change over last 5 bars
            price_change_5 = (close_prices[-1] - close_prices[-6]) / close_prices[-6] * 100

            # Determine bias
            if current_price > ma_10 * 1.001 and price_change_5 > 0.1:
                bias = MarketBias.BULLISH
            elif current_price < ma_10 * 0.999 and price_change_5 < -0.1:
                bias = MarketBias.BEARISH
            else:
                bias = MarketBias.CHOPPY

            self.state.current_market_bias = bias
            self.state.last_bias_check = now

            logger.info(f"MARKET BIAS: {bias.value.upper()} (SPY: ${current_price:.2f}, MA10: ${ma_10:.2f}, 5-bar change: {price_change_5:+.2f}%)")

            return bias

        except Exception as e:
            logger.error(f"Error checking market bias: {e}")
            return MarketBias.CHOPPY

    def get_bias_confidence_multiplier(self, trade_direction: str) -> float:
        """
        Get confidence multiplier based on market bias and trade direction.

        Args:
            trade_direction: "long" or "short"

        Returns:
            Multiplier between 0.5 and 1.0
        """
        bias = self.check_market_bias()
        multiplier = BIAS_CONFIDENCE[bias].get(trade_direction.lower(), 0.7)

        if multiplier < 1.0:
            logger.info(f"BIAS FILTER: {trade_direction.upper()} signal in {bias.value.upper()} market - confidence reduced to {multiplier*100:.0f}%")

        return multiplier

    def should_take_trade_with_bias(self, trade_direction: str, min_confidence: float = 0.6) -> bool:
        """
        Check if trade should be taken given market bias.

        Args:
            trade_direction: "long" or "short"
            min_confidence: Minimum confidence required (default 0.6)

        Returns:
            True if trade should be taken, False if bias is too unfavorable
        """
        multiplier = self.get_bias_confidence_multiplier(trade_direction)

        if multiplier < min_confidence:
            logger.warning(f"BIAS REJECTION: {trade_direction.upper()} trade rejected due to unfavorable market bias (confidence: {multiplier*100:.0f}% < {min_confidence*100:.0f}%)")
            return False

        return True

    # =========================================================================
    # CIRCUIT BREAKER
    # =========================================================================

    def check_circuit_breaker(self) -> bool:
        """
        Check if circuit breaker is active.

        Returns:
            True if trading is PAUSED (circuit breaker active), False if OK to trade
        """
        now = datetime.now(self.est)

        # Check if we're in a pause period
        if self.state.circuit_breaker_until:
            if now < self.state.circuit_breaker_until:
                remaining = (self.state.circuit_breaker_until - now).total_seconds() / 60
                logger.warning(f"CIRCUIT BREAKER ACTIVE: Trading paused for {remaining:.1f} more minutes")
                return True
            else:
                # Pause period ended
                self.state.circuit_breaker_until = None
                self.state.consecutive_losses = 0
                logger.info("CIRCUIT BREAKER: Pause period ended, trading resumed")

        # Check if we need to trigger circuit breaker
        if self.state.consecutive_losses >= CONSECUTIVE_LOSSES_THRESHOLD:
            self.state.circuit_breaker_until = now + timedelta(minutes=CIRCUIT_BREAKER_PAUSE_MINUTES)
            logger.warning(f"CIRCUIT BREAKER TRIGGERED: {self.state.consecutive_losses} consecutive losses - pausing trading for {CIRCUIT_BREAKER_PAUSE_MINUTES} minutes")
            return True

        return False

    # =========================================================================
    # DAILY LIMITS
    # =========================================================================

    def check_daily_trade_limit(self) -> bool:
        """
        Check if daily trade limit is reached.

        Returns:
            True if BLOCKED (limit reached), False if OK to trade
        """
        if self.state.trades_today >= MAX_TRADES_PER_DAY:
            logger.warning(f"DAILY LIMIT: Max trades reached ({self.state.trades_today}/{MAX_TRADES_PER_DAY})")
            return True
        return False

    def check_daily_loss_limit(self, account_equity: float) -> bool:
        """
        Check if daily loss limit is reached.

        Args:
            account_equity: Current account equity

        Returns:
            True if BLOCKED (limit reached), False if OK to trade
        """
        # Check absolute dollar limit
        if self.state.daily_realized_pnl <= -DAILY_MAX_LOSS_DOLLARS:
            logger.warning(f"DAILY LOSS LIMIT: Net P/L ${self.state.daily_realized_pnl:.2f} exceeds max loss ${DAILY_MAX_LOSS_DOLLARS}")
            return True

        # Check percentage limit
        pnl_percent = self.state.daily_realized_pnl / account_equity if account_equity > 0 else 0
        if pnl_percent <= -DAILY_MAX_LOSS_PERCENT:
            logger.warning(f"DAILY LOSS LIMIT: Net P/L {pnl_percent*100:.2f}% exceeds max loss {DAILY_MAX_LOSS_PERCENT*100:.1f}%")
            return True

        return False

    def update_daily_pnl(self, pnl: float, is_win: bool, symbol: str):
        """
        Update daily P/L tracking.

        Args:
            pnl: Realized P/L from trade
            is_win: Whether the trade was a win
            symbol: Stock symbol
        """
        self.state.daily_realized_pnl += pnl

        if is_win:
            self.record_win(symbol)
        else:
            self.record_loss(symbol)

        logger.info(f"DAILY P/L: ${self.state.daily_realized_pnl:.2f} (trade: ${pnl:+.2f})")

    def increment_trade_count(self):
        """Increment daily trade counter."""
        self.state.trades_today += 1
        logger.info(f"TRADE COUNT: {self.state.trades_today}/{MAX_TRADES_PER_DAY}")

    # =========================================================================
    # POSITION SIZING
    # =========================================================================

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        account_equity: float,
        max_risk: float = MAX_RISK_PER_TRADE_DOLLARS
    ) -> Tuple[int, float]:
        """
        Calculate position size based on risk.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            account_equity: Account equity
            max_risk: Maximum risk in dollars (default $100)

        Returns:
            Tuple of (shares, actual_risk)
        """
        risk_per_share = abs(entry_price - stop_loss)

        if risk_per_share <= 0:
            logger.error(f"Invalid risk per share: {risk_per_share}")
            return 0, 0.0

        # Calculate shares based on max risk
        shares = int(max_risk / risk_per_share)

        # Also check against percentage-based limit
        max_position_value = account_equity * POSITION_SIZE_PERCENT
        max_shares_by_value = int(max_position_value / entry_price)

        # Use the smaller of the two
        shares = min(shares, max_shares_by_value)

        # Ensure at least 1 share
        shares = max(shares, 1)

        actual_risk = shares * risk_per_share

        logger.info(f"POSITION SIZE: {shares} shares @ ${entry_price:.2f}, risk ${actual_risk:.2f} (max: ${max_risk})")

        return shares, actual_risk

    # =========================================================================
    # TIME RESTRICTIONS
    # =========================================================================

    def is_within_trading_hours(self) -> bool:
        """
        Check if current time is within allowed trading hours.

        Returns:
            True if within hours, False otherwise
        """
        current_time = datetime.now(self.est).time()

        if current_time < TRADING_START_TIME:
            minutes_until = (
                TRADING_START_TIME.hour * 60 + TRADING_START_TIME.minute -
                current_time.hour * 60 - current_time.minute
            )
            logger.info(f"TIME RESTRICTION: Waiting for trading hours ({minutes_until} min until {TRADING_START_TIME})")
            return False

        if current_time > TRADING_END_TIME:
            logger.info(f"TIME RESTRICTION: Trading hours ended ({TRADING_END_TIME})")
            return False

        return True

    # =========================================================================
    # COMPREHENSIVE TRADE VALIDATION
    # =========================================================================

    def can_take_trade(
        self,
        symbol: str,
        trade_direction: str,
        account_equity: float,
        current_positions: int = 0
    ) -> Tuple[bool, List[str]]:
        """
        Comprehensive check if a trade can be taken.

        Args:
            symbol: Stock symbol
            trade_direction: "long" or "short"
            account_equity: Current account equity
            current_positions: Number of currently open positions

        Returns:
            Tuple of (can_trade, list_of_rejection_reasons)
        """
        reasons = []

        # 1. Blacklist check
        if self.is_blacklisted(symbol):
            reasons.append(f"Blacklisted ticker ({symbol})")

        # 2. One-strike rule
        if self.is_ticker_blocked_by_losses(symbol):
            reasons.append(f"One-strike rule: {symbol} already has max losses today")

        # 3. Circuit breaker
        if self.check_circuit_breaker():
            reasons.append("Circuit breaker active - consecutive losses")

        # 4. Daily trade limit
        if self.check_daily_trade_limit():
            reasons.append(f"Daily trade limit reached ({MAX_TRADES_PER_DAY})")

        # 5. Daily loss limit
        if self.check_daily_loss_limit(account_equity):
            reasons.append(f"Daily loss limit reached (${DAILY_MAX_LOSS_DOLLARS})")

        # 6. Position limit
        if current_positions >= MAX_OPEN_POSITIONS:
            reasons.append(f"Max positions reached ({MAX_OPEN_POSITIONS})")

        # 7. Time restriction
        if not self.is_within_trading_hours():
            reasons.append("Outside trading hours")

        # 8. Market bias (this is a soft filter - only block if very unfavorable)
        if not self.should_take_trade_with_bias(trade_direction, min_confidence=0.5):
            reasons.append(f"Unfavorable market bias for {trade_direction}")

        can_trade = len(reasons) == 0

        if not can_trade:
            logger.warning(f"TRADE BLOCKED for {symbol}: {', '.join(reasons)}")

        return can_trade, reasons

    # =========================================================================
    # ENHANCED LOGGING
    # =========================================================================

    def log_trade(self, trade_data: Dict[str, Any]):
        """
        Log trade with enhanced detail for analysis.

        Args:
            trade_data: Dictionary with trade details
        """
        required_fields = [
            'symbol', 'direction', 'entry_price', 'exit_price',
            'stop_loss', 'take_profit', 'quantity', 'pnl',
            'entry_time', 'exit_time', 'exit_reason'
        ]

        log_entry = {
            'timestamp': datetime.now(self.est).isoformat(),
            **{k: trade_data.get(k) for k in required_fields},
            # Additional computed fields
            'r_multiple': self._calculate_r_multiple(trade_data),
            'hold_duration_minutes': self._calculate_hold_duration(trade_data),
            'market_bias_at_entry': self.state.current_market_bias.value,
            'ticker_priority': self.get_ticker_priority(trade_data.get('symbol', '')),
            'daily_trade_number': self.state.trades_today,
            'consecutive_losses_at_entry': self.state.consecutive_losses,
        }

        self.state.trade_log.append(log_entry)

        # Log to console
        symbol = trade_data.get('symbol', 'UNKNOWN')
        pnl = trade_data.get('pnl', 0)
        direction = trade_data.get('direction', 'unknown')
        exit_reason = trade_data.get('exit_reason', 'unknown')

        logger.info(f"TRADE LOG: {symbol} {direction.upper()} | P/L: ${pnl:+.2f} | Exit: {exit_reason} | R: {log_entry['r_multiple']:.2f}")

        # Cache the trade log
        redis_cache.set(
            f"trade_log_{datetime.now(self.est).strftime('%Y%m%d')}",
            self.state.trade_log,
            expiration=86400 * 7  # Keep for 7 days
        )

    def _calculate_r_multiple(self, trade_data: Dict[str, Any]) -> float:
        """Calculate R-multiple (reward/risk ratio achieved)."""
        try:
            entry = trade_data.get('entry_price', 0)
            stop = trade_data.get('stop_loss', 0)
            exit_price = trade_data.get('exit_price', 0)
            direction = trade_data.get('direction', 'long')

            if entry == 0 or stop == 0:
                return 0.0

            risk = abs(entry - stop)

            if direction.lower() == 'long':
                reward = exit_price - entry
            else:
                reward = entry - exit_price

            return reward / risk if risk > 0 else 0.0

        except Exception:
            return 0.0

    def _calculate_hold_duration(self, trade_data: Dict[str, Any]) -> float:
        """Calculate hold duration in minutes."""
        try:
            entry_time = trade_data.get('entry_time')
            exit_time = trade_data.get('exit_time')

            if entry_time and exit_time:
                if isinstance(entry_time, str):
                    entry_time = datetime.fromisoformat(entry_time)
                if isinstance(exit_time, str):
                    exit_time = datetime.fromisoformat(exit_time)

                duration = (exit_time - entry_time).total_seconds() / 60
                return round(duration, 1)
        except Exception:
            pass
        return 0.0

    def get_trade_log(self) -> List[Dict[str, Any]]:
        """Get today's trade log."""
        return self.state.trade_log


# Global instance
trade_filters = TradeFilters()
