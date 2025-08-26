"""
Performance tracking models for daily and overall statistics.
"""
import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, Date, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional, List

from app.core.database import Base


class DailyPerformance(Base):
    """
    Daily performance tracking model.
    
    Stores comprehensive daily trading statistics for
    performance analysis and risk management.
    """
    __tablename__ = "daily_performance"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Date (unique constraint)
    trade_date = Column(Date, nullable=False, unique=True, index=True)
    
    # Trade counts
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    # P&L metrics
    total_pnl = Column(Numeric(15, 2), default=0.0)
    
    # Performance ratios
    win_rate = Column(Numeric(5, 2), default=0.0)         # Percentage
    
    # Best/worst trades
    largest_win = Column(Numeric(15, 2), default=0.0)
    largest_loss = Column(Numeric(15, 2), default=0.0)
    
    # Account metrics
    account_equity = Column(Numeric(15, 2), nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<DailyPerformance(date={self.trade_date}, pnl={self.total_pnl}, trades={self.total_trades})>"
    
    def calculate_metrics(self, trades: List['Trade']):
        """Calculate all performance metrics from a list of trades."""
        if not trades:
            return
        
        # Reset counters
        self.total_trades = len(trades)
        self.winning_trades = 0
        self.losing_trades = 0
        
        total_pnl = 0
        largest_win = 0
        largest_loss = 0
        
        # Process each trade
        for trade in trades:
            if trade.realized_pnl is None:
                continue
            
            pnl = float(trade.realized_pnl)
            total_pnl += pnl
            
            if pnl > 0:
                self.winning_trades += 1
                largest_win = max(largest_win, pnl)
            elif pnl < 0:
                self.losing_trades += 1
                largest_loss = min(largest_loss, pnl)
        
        # Set calculated values
        self.total_pnl = total_pnl
        self.largest_win = largest_win
        self.largest_loss = largest_loss
        
        # Calculate win rate
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
    
    def update_account_equity(self, new_equity: float):
        """Update account equity."""
        self.account_equity = new_equity


class TradingSession(Base):
    """
    Trading session model for intraday performance tracking.
    
    Tracks performance within specific time windows during the day.
    """
    __tablename__ = "trading_sessions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Session identification
    trade_date = Column(Date, nullable=False, index=True)
    session_name = Column(String(50), nullable=False)  # "opening", "midday", "power_hour", etc.
    
    # Time window
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Performance metrics
    trades_count = Column(Integer, default=0)
    session_pnl = Column(Numeric(15, 2), default=0.0)
    win_rate = Column(Numeric(5, 2), default=0.0)
    
    # Best performing symbols
    best_symbol = Column(String(10), nullable=True)
    best_symbol_pnl = Column(Numeric(15, 2), default=0.0)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<TradingSession(date={self.trade_date}, session={self.session_name}, pnl={self.session_pnl})>"