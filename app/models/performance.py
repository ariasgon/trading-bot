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
    breakeven_trades = Column(Integer, default=0)
    
    # P&L metrics
    total_pnl = Column(Numeric(15, 2), default=0.0)
    gross_profit = Column(Numeric(15, 2), default=0.0)    # Total winning trades
    gross_loss = Column(Numeric(15, 2), default=0.0)      # Total losing trades
    commissions = Column(Numeric(10, 2), default=0.0)
    
    # Performance ratios
    win_rate = Column(Numeric(5, 2), default=0.0)         # Percentage
    profit_factor = Column(Numeric(8, 2), default=0.0)    # Gross profit / Gross loss
    
    # Best/worst trades
    largest_win = Column(Numeric(15, 2), default=0.0)
    largest_loss = Column(Numeric(15, 2), default=0.0)
    
    # Average metrics
    avg_win = Column(Numeric(15, 2), default=0.0)
    avg_loss = Column(Numeric(15, 2), default=0.0)
    avg_trade = Column(Numeric(15, 2), default=0.0)
    
    # R-multiple metrics
    avg_r_multiple = Column(Numeric(8, 2), default=0.0)
    best_r_multiple = Column(Numeric(8, 2), default=0.0)
    worst_r_multiple = Column(Numeric(8, 2), default=0.0)
    
    # Account metrics
    account_equity = Column(Numeric(15, 2), nullable=True)
    daily_return_percent = Column(Numeric(8, 4), default=0.0)
    
    # Risk metrics
    max_drawdown = Column(Numeric(15, 2), default=0.0)
    consecutive_wins = Column(Integer, default=0)
    consecutive_losses = Column(Integer, default=0)
    
    # Trading activity
    total_volume = Column(Integer, default=0)              # Total shares traded
    unique_symbols = Column(Integer, default=0)            # Number of different symbols
    
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
        self.breakeven_trades = 0
        
        total_pnl = 0
        gross_profit = 0
        gross_loss = 0
        r_multiples = []
        
        largest_win = 0
        largest_loss = 0
        total_volume = 0
        symbols = set()
        
        # Process each trade
        for trade in trades:
            if trade.realized_pnl is None:
                continue
            
            pnl = float(trade.realized_pnl)
            total_pnl += pnl
            total_volume += trade.quantity
            symbols.add(trade.symbol)
            
            if pnl > 0:
                self.winning_trades += 1
                gross_profit += pnl
                largest_win = max(largest_win, pnl)
            elif pnl < 0:
                self.losing_trades += 1
                gross_loss += abs(pnl)
                largest_loss = min(largest_loss, pnl)
            else:
                self.breakeven_trades += 1
            
            # R-multiple tracking
            if trade.r_multiple is not None:
                r_multiples.append(float(trade.r_multiple))
        
        # Set calculated values
        self.total_pnl = total_pnl
        self.gross_profit = gross_profit
        self.gross_loss = gross_loss
        self.largest_win = largest_win
        self.largest_loss = largest_loss
        self.total_volume = total_volume
        self.unique_symbols = len(symbols)
        
        # Calculate ratios
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
        
        if gross_loss > 0:
            self.profit_factor = gross_profit / gross_loss
        
        # Calculate averages
        if self.winning_trades > 0:
            self.avg_win = gross_profit / self.winning_trades
        
        if self.losing_trades > 0:
            self.avg_loss = gross_loss / self.losing_trades
        
        if self.total_trades > 0:
            self.avg_trade = total_pnl / self.total_trades
        
        # R-multiple statistics
        if r_multiples:
            self.avg_r_multiple = sum(r_multiples) / len(r_multiples)
            self.best_r_multiple = max(r_multiples)
            self.worst_r_multiple = min(r_multiples)
    
    def update_account_equity(self, new_equity: float):
        """Update account equity and calculate daily return."""
        if self.account_equity:
            old_equity = float(self.account_equity)
            if old_equity > 0:
                daily_change = new_equity - old_equity
                self.daily_return_percent = (daily_change / old_equity) * 100
        
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