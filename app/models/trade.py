"""
Trade model for storing completed trade data.
"""
import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from app.core.database import Base


class TradeSide(PyEnum):
    """Trade side enumeration."""
    BUY = "buy"
    SELL = "sell"


class TradeStatus(PyEnum):
    """Trade status enumeration."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Trade(Base):
    """
    Trade model representing a completed or pending trade.
    
    This stores all trade information including entry/exit prices,
    P&L, and timing data for performance analysis.
    """
    __tablename__ = "trades"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Trade identification
    symbol = Column(String(10), nullable=False, index=True)
    alpaca_order_id = Column(String(50), nullable=True)  # Alpaca's order ID
    
    # Trade details
    side = Column(Enum(TradeSide), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    # Prices
    entry_price = Column(Numeric(10, 4), nullable=True)
    exit_price = Column(Numeric(10, 4), nullable=True)
    stop_loss = Column(Numeric(10, 4), nullable=True)
    target_price = Column(Numeric(10, 4), nullable=True)
    
    # Status and P&L
    status = Column(Enum(TradeStatus), nullable=False, default=TradeStatus.PENDING)
    realized_pnl = Column(Numeric(15, 2), default=0.0)
    unrealized_pnl = Column(Numeric(15, 2), default=0.0)
    
    # Risk management
    risk_amount = Column(Numeric(10, 2), nullable=True)  # Amount risked (entry - stop) * quantity
    r_multiple = Column(Numeric(8, 2), nullable=True)    # Actual return / risk (R-multiple)
    
    # Timing
    entry_time = Column(DateTime(timezone=True), nullable=True)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    
    # Strategy information
    strategy = Column(String(50), default="velez")
    setup_type = Column(String(50), nullable=True)  # pullback_long, breakout_short, etc.
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Trade(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"
    
    @property
    def duration_minutes(self) -> Optional[int]:
        """Calculate trade duration in minutes."""
        if self.entry_time and self.exit_time:
            delta = self.exit_time - self.entry_time
            return int(delta.total_seconds() / 60)
        return None
    
    @property
    def is_winner(self) -> Optional[bool]:
        """Check if trade was profitable."""
        if self.realized_pnl is not None:
            return float(self.realized_pnl) > 0
        return None
    
    @property
    def gross_pnl(self) -> float:
        """Calculate gross P&L (before commissions)."""
        if self.entry_price and self.exit_price and self.quantity:
            if self.side == TradeSide.BUY:
                return (float(self.exit_price) - float(self.entry_price)) * self.quantity
            else:  # SHORT
                return (float(self.entry_price) - float(self.exit_price)) * self.quantity
        return 0.0
    
    def calculate_r_multiple(self):
        """Calculate and update R-multiple."""
        if self.realized_pnl and self.risk_amount and float(self.risk_amount) > 0:
            self.r_multiple = float(self.realized_pnl) / float(self.risk_amount)
        else:
            self.r_multiple = 0.0
    
    def update_exit(self, exit_price: float, exit_time: datetime = None):
        """Update trade with exit information."""
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.status = TradeStatus.FILLED
        
        # Calculate realized P&L
        self.realized_pnl = self.gross_pnl
        self.unrealized_pnl = 0.0
        
        # Calculate R-multiple
        self.calculate_r_multiple()