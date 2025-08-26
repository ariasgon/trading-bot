"""
Portfolio service for tracking positions and performance.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from app.core.database import get_db_session
from app.core.cache import redis_cache
from app.models.trade import Trade, TradeStatus
from app.models.position import Position, PositionStatus
from app.models.performance import DailyPerformance
from app.services.order_manager import order_manager
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class PortfolioService:
    """Service for portfolio management and tracking."""
    
    def __init__(self):
        self.account_equity = 100000.0  # Starting equity
        self.daily_pnl = 0.0
        
    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary including equity, positions, and P&L."""
        try:
            # Get account info from Alpaca
            account_info = order_manager.get_account_info()
            
            # Get current positions
            positions = self.get_open_positions()
            
            # Calculate total unrealized P&L
            total_unrealized_pnl = sum(pos.get('unrealized_pnl', 0) for pos in positions)
            
            # Get today's performance
            today_performance = self.get_daily_performance(date.today())
            
            summary = {
                "account_equity": account_info.get('equity', 0),
                "cash": account_info.get('cash', 0),
                "buying_power": account_info.get('buying_power', 0),
                "portfolio_value": account_info.get('portfolio_value', 0),
                "positions_count": len(positions),
                "total_unrealized_pnl": total_unrealized_pnl,
                "daily_pnl": today_performance.get('total_pnl', 0) if today_performance else 0,
                "daily_trades": today_performance.get('total_trades', 0) if today_performance else 0,
                "win_rate": today_performance.get('win_rate', 0) if today_performance else 0,
                "last_updated": datetime.now().isoformat()
            }
            
            # Cache the summary
            redis_cache.set("account_summary", summary, expiration=60)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting account summary: {e}")
            return {}
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions from both database and Alpaca."""
        try:
            position_list = []
            
            # First get positions from database
            with get_db_session() as db:
                # Use raw string to avoid enum issue temporarily
                positions = db.query(Position).filter(Position.status == 'open').all()
                
                for pos in positions:
                    # Update current price
                    current_price = market_data_service.get_current_price(pos.symbol)
                    if current_price:
                        pos.update_current_price(current_price)
                        db.commit()
                    
                    position_data = {
                        "id": str(pos.id),
                        "symbol": pos.symbol,
                        "quantity": pos.quantity,
                        "side": "long" if pos.is_long else "short",
                        "entry_price": float(pos.entry_price),
                        "current_price": float(pos.current_price) if pos.current_price else None,
                        "stop_loss": float(pos.stop_loss) if pos.stop_loss else None,
                        "target_price": float(pos.target_price) if pos.target_price else None,
                        "unrealized_pnl": float(pos.unrealized_pnl),
                        "unrealized_pnl_percent": float(pos.unrealized_pnl_percent),
                        "market_value": pos.market_value,
                        "cost_basis": pos.cost_basis,
                        "strategy": pos.strategy,
                        "setup_type": pos.setup_type,
                        "created_at": pos.created_at.isoformat(),
                        "source": "database"
                    }
                    
                    position_list.append(position_data)
            
            # Also get positions directly from Alpaca (for positions not tracked in database)
            alpaca_positions = order_manager.get_positions()
            
            # Get symbols already in database to avoid duplicates
            db_symbols = {pos['symbol'] for pos in position_list}
            
            # Add Alpaca positions that aren't in database
            for alpaca_pos in alpaca_positions:
                symbol = alpaca_pos['symbol']
                if symbol not in db_symbols:
                    position_data = {
                        "id": f"alpaca_{symbol}",
                        "symbol": symbol,
                        "quantity": alpaca_pos['quantity'],
                        "side": alpaca_pos['side'],
                        "entry_price": alpaca_pos['avg_entry_price'],
                        "current_price": alpaca_pos['current_price'],
                        "stop_loss": None,
                        "target_price": None,
                        "unrealized_pnl": alpaca_pos['unrealized_pnl'],
                        "unrealized_pnl_percent": alpaca_pos['unrealized_pnl_percent'],
                        "market_value": alpaca_pos['market_value'],
                        "cost_basis": alpaca_pos['cost_basis'],
                        "strategy": "manual",
                        "setup_type": "manual",
                        "created_at": datetime.now().isoformat(),
                        "source": "alpaca"
                    }
                    
                    position_list.append(position_data)
            
            return position_list
                
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []
    
    def get_position_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol."""
        try:
            positions = self.get_open_positions()
            return next((pos for pos in positions if pos['symbol'] == symbol), None)
            
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {e}")
            return None
    
    def get_daily_performance(self, trade_date: date) -> Optional[Dict[str, Any]]:
        """Get performance metrics for a specific date."""
        try:
            with get_db_session() as db:
                perf = db.query(DailyPerformance).filter(
                    DailyPerformance.trade_date == trade_date
                ).first()
                
                if not perf:
                    return None
                
                return {
                    "trade_date": perf.trade_date.isoformat(),
                    "total_trades": perf.total_trades,
                    "winning_trades": perf.winning_trades,
                    "losing_trades": perf.losing_trades,
                    "total_pnl": float(perf.total_pnl),
                    "win_rate": float(perf.win_rate),
                    "profit_factor": float(perf.profit_factor),
                    "largest_win": float(perf.largest_win),
                    "largest_loss": float(perf.largest_loss),
                    "avg_win": float(perf.avg_win),
                    "avg_loss": float(perf.avg_loss),
                    "avg_trade": float(perf.avg_trade),
                    "account_equity": float(perf.account_equity) if perf.account_equity else None,
                    "daily_return_percent": float(perf.daily_return_percent)
                }
                
        except Exception as e:
            logger.error(f"Error getting daily performance for {trade_date}: {e}")
            return None
    
    def update_daily_performance(self, trade_date: date = None) -> bool:
        """Update daily performance metrics."""
        try:
            if not trade_date:
                trade_date = date.today()
            
            with get_db_session() as db:
                # Get all completed trades for the day
                trades = db.query(Trade).filter(
                    Trade.entry_time >= datetime.combine(trade_date, datetime.min.time()),
                    Trade.entry_time < datetime.combine(trade_date, datetime.min.time()) + timedelta(days=1),
                    Trade.status == TradeStatus.FILLED,
                    Trade.realized_pnl.is_not(None)
                ).all()
                
                # Get or create daily performance record
                perf = db.query(DailyPerformance).filter(
                    DailyPerformance.trade_date == trade_date
                ).first()
                
                if not perf:
                    perf = DailyPerformance(trade_date=trade_date)
                    db.add(perf)
                
                # Calculate metrics
                perf.calculate_metrics(trades)
                
                # Update account equity
                account_info = order_manager.get_account_info()
                if account_info.get('equity'):
                    perf.update_account_equity(float(account_info['equity']))
                
                logger.info(f"Updated daily performance for {trade_date}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating daily performance: {e}")
            return False
    
    def get_performance_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get performance summary for the last N days."""
        try:
            with get_db_session() as db:
                end_date = date.today()
                start_date = end_date - timedelta(days=days)
                
                # Get all completed trades in the period
                trades = db.query(Trade).filter(
                    Trade.entry_time >= datetime.combine(start_date, datetime.min.time()),
                    Trade.entry_time <= datetime.combine(end_date, datetime.max.time()),
                    Trade.status == TradeStatus.FILLED,
                    Trade.realized_pnl.is_not(None)
                ).all()
                
                if not trades:
                    return {
                        "period_days": days,
                        "total_trades": 0,
                        "total_pnl": 0.0,
                        "win_rate": 0.0,
                        "profit_factor": 0.0,
                        "avg_trade": 0.0
                    }
                
                # Calculate summary metrics
                total_trades = len(trades)
                winners = [t for t in trades if float(t.realized_pnl) > 0]
                losers = [t for t in trades if float(t.realized_pnl) < 0]
                
                total_pnl = sum(float(t.realized_pnl) for t in trades)
                gross_profit = sum(float(t.realized_pnl) for t in winners)
                gross_loss = sum(abs(float(t.realized_pnl)) for t in losers)
                
                win_rate = (len(winners) / total_trades) * 100 if total_trades > 0 else 0
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
                avg_trade = total_pnl / total_trades if total_trades > 0 else 0
                
                largest_win = max((float(t.realized_pnl) for t in winners), default=0)
                largest_loss = min((float(t.realized_pnl) for t in losers), default=0)
                
                # R-multiple stats
                r_multiples = [float(t.r_multiple) for t in trades if t.r_multiple is not None]
                avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0
                
                return {
                    "period_days": days,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "total_trades": total_trades,
                    "winning_trades": len(winners),
                    "losing_trades": len(losers),
                    "total_pnl": total_pnl,
                    "win_rate": win_rate,
                    "profit_factor": profit_factor,
                    "avg_trade": avg_trade,
                    "largest_win": largest_win,
                    "largest_loss": largest_loss,
                    "avg_r_multiple": avg_r,
                    "gross_profit": gross_profit,
                    "gross_loss": gross_loss
                }
                
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}
    
    def calculate_risk_metrics(self) -> Dict[str, Any]:
        """Calculate current risk metrics."""
        try:
            positions = self.get_open_positions()
            account_info = order_manager.get_account_info()
            
            total_exposure = sum(pos['market_value'] for pos in positions)
            account_equity = account_info.get('equity', 0)
            
            exposure_percent = (total_exposure / account_equity * 100) if account_equity > 0 else 0
            
            # Calculate total risk (distance to stops)
            total_risk = 0
            for pos in positions:
                if pos['stop_loss']:
                    risk_per_share = abs(pos['current_price'] - pos['stop_loss'])
                    position_risk = risk_per_share * abs(pos['quantity'])
                    total_risk += position_risk
            
            risk_percent = (total_risk / account_equity * 100) if account_equity > 0 else 0
            
            # Get today's P&L
            today_perf = self.get_daily_performance(date.today())
            daily_pnl = today_perf.get('total_pnl', 0) if today_perf else 0
            daily_pnl_percent = (daily_pnl / account_equity * 100) if account_equity > 0 else 0
            
            # Check position count limits
            max_positions = settings.max_concurrent_positions
            position_count = len(positions)
            
            risk_metrics = {
                "total_exposure": total_exposure,
                "exposure_percent": exposure_percent,
                "total_risk": total_risk,
                "risk_percent": risk_percent,
                "positions_count": position_count,
                "max_positions": max_positions,
                "positions_utilization": (position_count / max_positions * 100) if max_positions > 0 else 0,
                "daily_pnl": daily_pnl,
                "daily_pnl_percent": daily_pnl_percent,
                "daily_limit_percent": settings.daily_loss_limit * 100,
                "account_equity": account_equity,
                "cash": account_info.get('cash', 0),
                "buying_power": account_info.get('buying_power', 0),
                "last_updated": datetime.now().isoformat()
            }
            
            # Cache risk metrics
            redis_cache.set("risk_metrics", risk_metrics, expiration=60)
            
            return risk_metrics
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics: {e}")
            return {}
    
    def check_risk_limits(self) -> Dict[str, Any]:
        """Check if any risk limits are violated."""
        try:
            risk_metrics = self.calculate_risk_metrics()
            violations = []
            
            # Check daily loss limit
            daily_pnl_percent = risk_metrics.get('daily_pnl_percent', 0)
            if daily_pnl_percent < -(settings.daily_loss_limit * 100):
                violations.append({
                    "type": "daily_loss_limit",
                    "current": daily_pnl_percent,
                    "limit": -(settings.daily_loss_limit * 100),
                    "action": "stop_trading"
                })
            
            # Check position count limit
            position_count = risk_metrics.get('positions_count', 0)
            if position_count >= settings.max_concurrent_positions:
                violations.append({
                    "type": "max_positions",
                    "current": position_count,
                    "limit": settings.max_concurrent_positions,
                    "action": "no_new_positions"
                })
            
            # Check exposure limits (example: 95% of equity)
            exposure_percent = risk_metrics.get('exposure_percent', 0)
            if exposure_percent > 95:
                violations.append({
                    "type": "max_exposure",
                    "current": exposure_percent,
                    "limit": 95,
                    "action": "reduce_positions"
                })
            
            return {
                "violations_count": len(violations),
                "violations": violations,
                "risk_status": "violated" if violations else "within_limits",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return {"violations_count": 0, "violations": [], "risk_status": "error"}
    
    def get_watchlist(self) -> List[str]:
        """Get current trading watchlist."""
        try:
            # Check cache first
            cached_watchlist = redis_cache.get("watchlist")
            if cached_watchlist:
                return cached_watchlist
            
            # Default watchlist for Oliver Velez strategy
            default_watchlist = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
                "META", "NVDA", "NFLX", "AMD", "CRM",
                "SHOP", "SQ", "ROKU", "ZOOM", "DOCU"
            ]
            
            # Cache for 1 hour
            redis_cache.set("watchlist", default_watchlist, expiration=3600)
            
            return default_watchlist
            
        except Exception as e:
            logger.error(f"Error getting watchlist: {e}")
            return []
    
    def update_watchlist(self, symbols: List[str]) -> bool:
        """Update the trading watchlist."""
        try:
            # Validate symbols (basic check)
            valid_symbols = [s.upper().strip() for s in symbols if s.strip()]
            
            # Cache the new watchlist
            redis_cache.set("watchlist", valid_symbols, expiration=3600)
            
            logger.info(f"Updated watchlist with {len(valid_symbols)} symbols")
            return True
            
        except Exception as e:
            logger.error(f"Error updating watchlist: {e}")
            return False
    
    def health_check(self) -> bool:
        """Check if portfolio service is healthy."""
        try:
            # Simple database connection test
            with get_db_session() as db:
                # Just test that we can connect and count positions
                count = db.query(Position).count()
                return True
            
        except Exception as e:
            logger.error(f"Portfolio service health check failed: {e}")
            return False


# Create global portfolio service instance
portfolio_service = PortfolioService()