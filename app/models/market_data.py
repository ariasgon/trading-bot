"""
Market data models for caching price and volume information.
"""
import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, BigInteger, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime

from app.core.database import Base


class MarketData(Base):
    """
    Market data model for storing OHLCV bars and indicators.
    
    Caches intraday price data for technical analysis and
    reduces API calls to market data providers.
    """
    __tablename__ = "market_data"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Identification
    symbol = Column(String(10), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)  # "1T", "5T", "15T", "60T", "1D"
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # OHLCV data
    open_price = Column(Numeric(10, 4), nullable=False)
    high_price = Column(Numeric(10, 4), nullable=False)
    low_price = Column(Numeric(10, 4), nullable=False)
    close_price = Column(Numeric(10, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)
    
    # Additional market data
    vwap = Column(Numeric(10, 4), nullable=True)
    trade_count = Column(Integer, nullable=True)
    
    # Technical indicators (cached for performance)
    ema_20 = Column(Numeric(10, 4), nullable=True)
    ema_200 = Column(Numeric(10, 4), nullable=True)
    atr_14 = Column(Numeric(10, 4), nullable=True)
    rsi_14 = Column(Numeric(8, 2), nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Composite index for fast lookups
    __table_args__ = (
        Index('ix_market_data_symbol_timeframe_timestamp', 'symbol', 'timeframe', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<MarketData(symbol={self.symbol}, timeframe={self.timeframe}, timestamp={self.timestamp}, close={self.close_price})>"
    
    @property
    def typical_price(self) -> float:
        """Calculate typical price (HLC/3)."""
        return (float(self.high_price) + float(self.low_price) + float(self.close_price)) / 3
    
    @property
    def true_range(self) -> float:
        """Calculate true range (for ATR calculation)."""
        # This would need previous close, which would require additional logic
        # For now, return high - low
        return float(self.high_price) - float(self.low_price)
    
    @property
    def price_change(self) -> float:
        """Calculate price change from open to close."""
        return float(self.close_price) - float(self.open_price)
    
    @property
    def price_change_percent(self) -> float:
        """Calculate percentage price change."""
        if float(self.open_price) > 0:
            return (self.price_change / float(self.open_price)) * 100
        return 0.0
    
    def is_green_candle(self) -> bool:
        """Check if candle is bullish (close > open)."""
        return float(self.close_price) > float(self.open_price)
    
    def is_red_candle(self) -> bool:
        """Check if candle is bearish (close < open)."""
        return float(self.close_price) < float(self.open_price)
    
    def body_size(self) -> float:
        """Calculate candle body size."""
        return abs(float(self.close_price) - float(self.open_price))
    
    def upper_wick_size(self) -> float:
        """Calculate upper wick size."""
        return float(self.high_price) - max(float(self.open_price), float(self.close_price))
    
    def lower_wick_size(self) -> float:
        """Calculate lower wick size."""
        return min(float(self.open_price), float(self.close_price)) - float(self.low_price)


class PreMarketData(Base):
    """
    Pre-market data for gap analysis and stock selection.
    
    Stores pre-market price action and gap information
    for the daily stock scanning process.
    """
    __tablename__ = "premarket_data"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Identification
    symbol = Column(String(10), nullable=False, index=True)
    trade_date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Previous day close
    previous_close = Column(Numeric(10, 4), nullable=False)
    
    # Pre-market data
    premarket_high = Column(Numeric(10, 4), nullable=True)
    premarket_low = Column(Numeric(10, 4), nullable=True)
    premarket_last = Column(Numeric(10, 4), nullable=True)
    premarket_volume = Column(BigInteger, default=0)
    
    # Gap analysis
    gap_percent = Column(Numeric(8, 4), nullable=True)
    gap_direction = Column(String(10), nullable=True)  # "up", "down", "flat"
    gap_size = Column(Numeric(10, 4), nullable=True)   # Absolute gap size in dollars
    
    # Volume analysis
    avg_volume_10d = Column(BigInteger, nullable=True)  # 10-day average volume
    volume_ratio = Column(Numeric(8, 2), nullable=True) # Current vs average volume
    
    # News and catalysts
    has_news = Column(String(1), default='N')           # Y/N for news presence
    catalyst_type = Column(String(50), nullable=True)   # "earnings", "upgrade", etc.
    
    # Selection criteria
    is_gapper = Column(String(1), default='N')          # Y/N for gap criteria met
    selection_score = Column(Numeric(5, 2), nullable=True) # 0-100 scoring
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<PreMarketData(symbol={self.symbol}, date={self.trade_date}, gap={self.gap_percent}%)>"
    
    def calculate_gap_metrics(self, current_price: float):
        """Calculate gap metrics based on current price vs previous close."""
        if not self.previous_close:
            return
        
        prev_close = float(self.previous_close)
        gap_dollars = current_price - prev_close
        
        self.gap_size = abs(gap_dollars)
        self.gap_percent = (gap_dollars / prev_close) * 100
        
        if gap_dollars > 0.5:  # Significant gap up
            self.gap_direction = "up"
        elif gap_dollars < -0.5:  # Significant gap down
            self.gap_direction = "down"
        else:
            self.gap_direction = "flat"
        
        # Determine if it qualifies as a gapper (>2% gap)
        if abs(float(self.gap_percent)) >= 2.0:
            self.is_gapper = 'Y'