"""
Risk management service for position sizing and risk controls.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from app.core.config import settings
from app.core.database import get_db_session
from app.models.trade import Trade, TradeStatus
from app.models.position import Position, PositionStatus
from app.services.order_manager import order_manager
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class RiskManagerService:
    """Service for managing trading risk and position sizing."""
    
    def __init__(self):
        self.max_risk_per_trade = settings.max_risk_per_trade
        self.daily_loss_limit = settings.daily_loss_limit
        self.max_concurrent_positions = settings.max_concurrent_positions
        
    def calculate_position_size(self, symbol: str, entry_price: float, stop_loss: float, 
                              risk_percentage: float = None) -> Tuple[int, Dict[str, Any]]:
        """Calculate optimal position size based on risk management rules."""
        try:
            # Use default risk percentage if not provided
            if risk_percentage is None:
                risk_percentage = self.max_risk_per_trade
            
            # Get account information
            account_info = order_manager.get_account_info()
            account_equity = account_info.get('equity', 0)
            
            if account_equity <= 0:
                return 0, {"error": "Invalid account equity"}
            
            # Calculate dollar risk amount
            risk_amount = account_equity * risk_percentage
            
            # Calculate risk per share
            risk_per_share = abs(entry_price - stop_loss)
            
            if risk_per_share <= 0:
                return 0, {"error": "Invalid risk per share calculation"}
            
            # Calculate base position size
            base_shares = int(risk_amount / risk_per_share)
            
            # Apply position sizing filters
            sizing_info = self._apply_sizing_filters(
                symbol=symbol,
                base_shares=base_shares,
                entry_price=entry_price,
                account_equity=account_equity
            )
            
            final_shares = sizing_info["final_shares"]
            
            # Calculate actual risk and position value
            actual_risk = final_shares * risk_per_share
            position_value = final_shares * entry_price
            
            return final_shares, {
                "base_shares": base_shares,
                "final_shares": final_shares,
                "risk_per_share": risk_per_share,
                "planned_risk_amount": risk_amount,
                "actual_risk_amount": actual_risk,
                "position_value": position_value,
                "risk_percentage": (actual_risk / account_equity) * 100,
                "filters_applied": sizing_info["filters_applied"],
                "account_equity": account_equity
            }
            
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0, {"error": str(e)}
    
    def _apply_sizing_filters(self, symbol: str, base_shares: int, entry_price: float, 
                            account_equity: float) -> Dict[str, Any]:
        """Apply various filters to position sizing."""
        filters_applied = []
        final_shares = base_shares
        
        # Filter 1: Minimum position size
        min_shares = 1
        if final_shares < min_shares:
            final_shares = 0
            filters_applied.append("below_minimum_size")
        
        # Filter 2: Maximum position size (e.g., 10% of equity)
        max_position_value = account_equity * 0.10
        max_shares_by_value = int(max_position_value / entry_price)
        
        if final_shares > max_shares_by_value:
            final_shares = max_shares_by_value
            filters_applied.append("max_position_value_limit")
        
        # Filter 3: Buying power check
        account_info = order_manager.get_account_info()
        buying_power = account_info.get('buying_power', 0)
        position_cost = final_shares * entry_price
        
        if position_cost > buying_power:
            affordable_shares = int(buying_power / entry_price)
            final_shares = affordable_shares
            filters_applied.append("buying_power_limit")
        
        # Filter 4: Maximum concurrent positions
        open_positions_count = self.get_open_positions_count()
        if open_positions_count >= self.max_concurrent_positions:
            final_shares = 0
            filters_applied.append("max_concurrent_positions")
        
        # Filter 5: Daily loss limit check
        if self.is_daily_loss_limit_reached():
            final_shares = 0
            filters_applied.append("daily_loss_limit_reached")
        
        # Filter 6: Symbol-specific position limit (avoid overconcentration)
        existing_position = self.get_existing_position(symbol)
        if existing_position:
            # Limit additional position size if already have exposure
            current_value = abs(existing_position.get('market_value', 0))
            max_total_value = account_equity * 0.05  # 5% per symbol
            
            if current_value >= max_total_value:
                final_shares = 0
                filters_applied.append("symbol_concentration_limit")
        
        return {
            "final_shares": max(final_shares, 0),
            "filters_applied": filters_applied
        }
    
    def validate_trade_setup(self, symbol: str, entry_price: float, stop_loss: float, 
                           target_price: float = None) -> Dict[str, Any]:
        """Validate a trade setup before execution."""
        try:
            validation = {
                "is_valid": True,
                "warnings": [],
                "errors": [],
                "risk_reward_ratio": None,
                "setup_quality": "unknown"
            }
            
            # Check basic price logic
            if entry_price <= 0 or stop_loss <= 0:
                validation["errors"].append("Invalid entry price or stop loss")
                validation["is_valid"] = False
            
            # Check risk-reward ratio if target is provided
            if target_price and target_price > 0:
                risk = abs(entry_price - stop_loss)
                reward = abs(target_price - entry_price)
                
                if risk > 0:
                    rr_ratio = reward / risk
                    validation["risk_reward_ratio"] = round(rr_ratio, 2)
                    
                    if rr_ratio < 1.5:  # Minimum 1.5:1 risk-reward
                        validation["warnings"].append("Risk-reward ratio below 1.5:1")
                    elif rr_ratio >= 2.0:
                        validation["setup_quality"] = "good"
                    else:
                        validation["setup_quality"] = "acceptable"
            
            # Check stop loss distance (shouldn't be too tight or too wide)
            stop_distance_pct = abs(entry_price - stop_loss) / entry_price * 100
            
            if stop_distance_pct < 0.5:
                validation["warnings"].append("Stop loss very tight (< 0.5%)")
            elif stop_distance_pct > 8.0:
                validation["warnings"].append("Stop loss very wide (> 8%)")
            
            # Check current market conditions
            market_status = market_data_service.get_market_status()
            if not market_status.get("is_open"):
                validation["warnings"].append("Market is currently closed")
            
            # Check if we already have a position in this symbol
            existing_position = self.get_existing_position(symbol)
            if existing_position:
                validation["warnings"].append("Already have position in this symbol")
            
            return validation
            
        except Exception as e:
            logger.error(f"Error validating trade setup for {symbol}: {e}")
            return {
                "is_valid": False,
                "errors": [str(e)],
                "warnings": [],
                "risk_reward_ratio": None
            }
    
    def check_pre_trade_conditions(self) -> Dict[str, Any]:
        """Check if conditions are suitable for new trades."""
        try:
            conditions = {
                "can_trade": True,
                "reasons": [],
                "market_status": "unknown",
                "account_status": "unknown",
                "risk_status": "unknown"
            }
            
            # Check market hours
            market_status = market_data_service.get_market_status()
            conditions["market_status"] = "open" if market_status.get("is_open") else "closed"
            
            if not market_status.get("is_open"):
                conditions["can_trade"] = False
                conditions["reasons"].append("Market is closed")
            
            # Check daily loss limit
            if self.is_daily_loss_limit_reached():
                conditions["can_trade"] = False
                conditions["reasons"].append("Daily loss limit reached")
                conditions["risk_status"] = "daily_limit_exceeded"
            else:
                conditions["risk_status"] = "within_limits"
            
            # Check maximum concurrent positions
            open_positions = self.get_open_positions_count()
            if open_positions >= self.max_concurrent_positions:
                conditions["can_trade"] = False
                conditions["reasons"].append("Maximum concurrent positions reached")
            
            # Check account status
            account_info = order_manager.get_account_info()
            buying_power = account_info.get('buying_power', 0)
            
            if buying_power < 1000:  # Minimum $1000 buying power
                conditions["can_trade"] = False
                conditions["reasons"].append("Insufficient buying power")
                conditions["account_status"] = "insufficient_capital"
            else:
                conditions["account_status"] = "sufficient_capital"
            
            return conditions
            
        except Exception as e:
            logger.error(f"Error checking pre-trade conditions: {e}")
            return {
                "can_trade": False,
                "reasons": [f"Error checking conditions: {e}"],
                "market_status": "error",
                "account_status": "error",
                "risk_status": "error"
            }
    
    def get_open_positions_count(self) -> int:
        """Get the number of currently open positions."""
        try:
            with get_db_session() as db:
                count = db.query(Position).filter(Position.status == 'open').count()
                return count
        except Exception as e:
            logger.error(f"Error getting open positions count: {e}")
            return 0
    
    def get_existing_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Check if we already have a position in this symbol."""
        try:
            with get_db_session() as db:
                position = db.query(Position).filter(
                    Position.symbol == symbol.upper(),
                    Position.status == 'open'
                ).first()
                
                if position:
                    return {
                        "id": str(position.id),
                        "quantity": position.quantity,
                        "entry_price": float(position.entry_price),
                        "current_price": float(position.current_price) if position.current_price else None,
                        "market_value": position.market_value,
                        "unrealized_pnl": float(position.unrealized_pnl)
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Error checking existing position for {symbol}: {e}")
            return None
    
    def is_daily_loss_limit_reached(self) -> bool:
        """Check if daily loss limit has been reached."""
        try:
            with get_db_session() as db:
                today = date.today()
                
                # Get today's completed trades
                trades = db.query(Trade).filter(
                    Trade.entry_time >= datetime.combine(today, datetime.min.time()),
                    Trade.entry_time < datetime.combine(today, datetime.min.time()) + timedelta(days=1),
                    Trade.status == TradeStatus.FILLED,
                    Trade.realized_pnl.is_not(None)
                ).all()
                
                daily_pnl = sum(float(trade.realized_pnl) for trade in trades if trade.realized_pnl)
                
                # Get account equity for percentage calculation
                account_info = order_manager.get_account_info()
                account_equity = account_info.get('equity', 100000)  # Default fallback
                
                daily_loss_percentage = daily_pnl / account_equity
                
                return daily_loss_percentage <= -self.daily_loss_limit
                
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            return False
    
    def calculate_stop_loss_price(self, symbol: str, entry_price: float, 
                                side: str, atr_multiplier: float = 2.0) -> Optional[float]:
        """Calculate appropriate stop-loss price based on ATR or fixed percentage."""
        try:
            # Try to get ATR-based stop first
            # For now, use a simple percentage-based approach
            # In a full implementation, you'd calculate ATR from historical data
            
            stop_percentage = 0.02  # 2% default stop
            
            if side.lower() == 'buy':
                # For long positions, stop below entry
                stop_price = entry_price * (1 - stop_percentage)
            else:
                # For short positions, stop above entry
                stop_price = entry_price * (1 + stop_percentage)
            
            return round(stop_price, 2)
            
        except Exception as e:
            logger.error(f"Error calculating stop loss for {symbol}: {e}")
            return None
    
    def calculate_target_price(self, entry_price: float, stop_loss: float, 
                             side: str, risk_reward_ratio: float = 2.0) -> float:
        """Calculate target price based on risk-reward ratio."""
        try:
            risk_amount = abs(entry_price - stop_loss)
            reward_amount = risk_amount * risk_reward_ratio
            
            if side.lower() == 'buy':
                # For long positions, target above entry
                target_price = entry_price + reward_amount
            else:
                # For short positions, target below entry
                target_price = entry_price - reward_amount
            
            return round(target_price, 2)
            
        except Exception as e:
            logger.error(f"Error calculating target price: {e}")
            return entry_price
    
    def monitor_positions_risk(self) -> Dict[str, Any]:
        """Monitor all open positions for risk management."""
        try:
            with get_db_session() as db:
                positions = db.query(Position).filter(Position.status == 'open').all()
                
                risk_alerts = []
                total_risk = 0
                
                for position in positions:
                    # Update current price
                    current_price = market_data_service.get_current_price(position.symbol)
                    if current_price:
                        position.update_current_price(current_price)
                        db.commit()
                    
                    # Check for stop-loss hits
                    if position.check_stop_loss_hit():
                        risk_alerts.append({
                            "type": "stop_loss_hit",
                            "symbol": position.symbol,
                            "current_price": float(position.current_price),
                            "stop_loss": float(position.stop_loss),
                            "action": "close_position"
                        })
                    
                    # Check for target hits
                    if position.check_target_hit():
                        risk_alerts.append({
                            "type": "target_hit",
                            "symbol": position.symbol,
                            "current_price": float(position.current_price),
                            "target_price": float(position.target_price),
                            "action": "close_position"
                        })
                    
                    # Calculate position risk
                    if position.stop_loss:
                        risk_per_share = abs(float(position.entry_price) - float(position.stop_loss))
                        position_risk = risk_per_share * abs(position.quantity)
                        total_risk += position_risk
                
                return {
                    "positions_monitored": len(positions),
                    "risk_alerts": risk_alerts,
                    "total_risk": total_risk,
                    "alerts_count": len(risk_alerts),
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error monitoring positions risk: {e}")
            return {"error": str(e)}
    
    def health_check(self) -> bool:
        """Check if risk manager service is healthy."""
        try:
            # Test database connection
            count = self.get_open_positions_count()
            return isinstance(count, int)
            
        except Exception as e:
            logger.error(f"Risk manager health check failed: {e}")
            return False


# Create global risk manager service instance
risk_manager = RiskManagerService()