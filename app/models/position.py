"""
Position model for tracking open positions.
"""
import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from app.core.database import Base


class PositionStatus(PyEnum):
    """Position status enumeration."""
    OPEN = "open"
    CLOSED = "closed"


class Position(Base):
    """
    Position model for tracking current open positions.
    
    This tracks real-time position data including current P&L,
    stop-loss levels, and position management information.
    """
    __tablename__ = "positions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Position identification
    symbol = Column(String(10), nullable=False, index=True)
    
    # Position details
    quantity = Column(Integer, nullable=False)  # Positive for long, negative for short
    entry_price = Column(Numeric(10, 4), nullable=False)
    current_price = Column(Numeric(10, 4), nullable=True)
    
    # Risk management
    stop_loss = Column(Numeric(10, 4), nullable=True)
    target_price = Column(Numeric(10, 4), nullable=True)
    trail_stop_amount = Column(Numeric(10, 4), nullable=True)  # Trailing stop distance
    
    # P&L tracking
    unrealized_pnl = Column(Numeric(15, 2), default=0.0)
    unrealized_pnl_percent = Column(Numeric(8, 4), default=0.0)
    
    # Position management
    status = Column(Enum(PositionStatus), nullable=False, default=PositionStatus.OPEN, index=True)
    partial_fills = Column(Integer, default=0)  # Number of partial fills
    
    # References
    trade_id = Column(UUID(as_uuid=True), ForeignKey("trades.id"), nullable=True)
    alpaca_position_id = Column(String(50), nullable=True)  # Alpaca's position ID
    
    # Strategy information
    strategy = Column(String(50), default="velez")
    setup_type = Column(String(50), nullable=True)
    confidence_level = Column(String(20), nullable=True)  # high, medium, low
    
    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship to trade
    trade = relationship("Trade", backref="position")
    
    def __repr__(self):
        return f"<Position(id={self.id}, symbol={self.symbol}, quantity={self.quantity}, status={self.status})>"
    
    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    @property
    def market_value(self) -> float:
        """Calculate current market value of position."""
        if self.current_price:
            return abs(self.quantity) * float(self.current_price)
        return 0.0
    
    @property
    def cost_basis(self) -> float:
        """Calculate cost basis of position."""
        return abs(self.quantity) * float(self.entry_price)
    
    def update_current_price(self, new_price: float):
        """Update current price and recalculate P&L."""
        self.current_price = new_price
        self.calculate_unrealized_pnl()
    
    def calculate_unrealized_pnl(self):
        """Calculate and update unrealized P&L."""
        if not self.current_price:
            return
        
        current_price = float(self.current_price)
        entry_price = float(self.entry_price)
        
        if self.is_long:
            pnl = (current_price - entry_price) * self.quantity
        else:  # short position
            pnl = (entry_price - current_price) * abs(self.quantity)
        
        self.unrealized_pnl = pnl
        
        # Calculate percentage
        if self.cost_basis > 0:
            self.unrealized_pnl_percent = (pnl / self.cost_basis) * 100
    
    def update_trailing_stop(self, atr_value: float = None, fixed_amount: float = None):
        """Update trailing stop based on current price."""
        if not self.current_price:
            return
        
        current_price = float(self.current_price)
        
        if atr_value:
            # Use ATR-based trailing stop
            trail_amount = atr_value
        elif fixed_amount:
            # Use fixed amount
            trail_amount = fixed_amount
        elif self.trail_stop_amount:
            # Use existing trail amount
            trail_amount = float(self.trail_stop_amount)
        else:
            return
        
        if self.is_long:
            # For longs, stop goes below current price
            new_stop = current_price - trail_amount
            # Only raise the stop, never lower it
            if not self.stop_loss or new_stop > float(self.stop_loss):
                self.stop_loss = new_stop
        else:
            # For shorts, stop goes above current price
            new_stop = current_price + trail_amount
            # Only lower the stop for shorts, never raise it
            if not self.stop_loss or new_stop < float(self.stop_loss):
                self.stop_loss = new_stop
    
    def check_stop_loss_hit(self) -> bool:
        """Check if stop loss has been hit."""
        if not self.stop_loss or not self.current_price:
            return False
        
        stop_loss = float(self.stop_loss)
        current_price = float(self.current_price)
        
        if self.is_long:
            return current_price <= stop_loss
        else:  # short position
            return current_price >= stop_loss
    
    def check_target_hit(self) -> bool:
        """Check if price target has been hit."""
        if not self.target_price or not self.current_price:
            return False
        
        target = float(self.target_price)
        current_price = float(self.current_price)
        
        if self.is_long:
            return current_price >= target
        else:  # short position
            return current_price <= target
    
    def close_position(self, exit_price: float, exit_time: datetime = None):
        """Mark position as closed."""
        self.status = PositionStatus.CLOSED
        self.current_price = exit_price
        self.calculate_unrealized_pnl()
        
        # Update associated trade if exists
        if self.trade:
            self.trade.update_exit(exit_price, exit_time)