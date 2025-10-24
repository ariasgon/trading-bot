"""
Trade History API endpoints for viewing historical trades and P&L analysis.
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.database import get_db_session
from app.models.trade import Trade, TradeStatus, TradeSide
from app.services.order_manager import order_manager
from sqlalchemy import func, and_

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/trades")
async def get_trade_history(
    limit: int = Query(100, le=500, description="Maximum number of trades to return"),
    offset: int = Query(0, ge=0, description="Number of trades to skip"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    strategy: Optional[str] = Query(None, description="Filter by strategy"),
    status: Optional[str] = Query(None, description="Filter by status"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
):
    """
    Get historical trades with optional filters.

    Returns detailed information about each trade including P&L, duration, and win/loss status.
    """
    try:
        with get_db_session() as db:
            # Build query
            query = db.query(Trade)

            # Apply filters
            if symbol:
                query = query.filter(Trade.symbol == symbol.upper())

            if strategy:
                query = query.filter(Trade.strategy == strategy)

            if status:
                # Status filter uses lowercase enum values
                query = query.filter(Trade.status == status.lower())

            # Date filtering: Use entry_time for all trades (open and closed)
            # This ensures we see recent trades even if they haven't exited yet
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Trade.entry_time >= start_dt)
            else:
                # Default: show trades from last 90 days if no filter specified
                default_start = datetime.now() - timedelta(days=90)
                query = query.filter(Trade.entry_time >= default_start)

            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(Trade.entry_time < end_dt)

            # Order by most recent first
            query = query.order_by(Trade.entry_time.desc())

            # Get total count before pagination
            total_count = query.count()

            # Apply pagination
            trades = query.offset(offset).limit(limit).all()

            # Format trades for response
            trades_data = []
            for trade in trades:
                trade_dict = {
                    'id': str(trade.id),
                    'symbol': trade.symbol,
                    'side': trade.side if trade.side else None,  # Changed from enum to string
                    'quantity': trade.quantity,
                    'entry_price': float(trade.entry_price) if trade.entry_price else None,
                    'exit_price': float(trade.exit_price) if trade.exit_price else None,
                    'stop_loss': float(trade.stop_loss) if trade.stop_loss else None,
                    'target_price': float(trade.target_price) if trade.target_price else None,
                    'status': trade.status if trade.status else None,  # Changed from enum to string
                    'realized_pnl': float(trade.realized_pnl) if trade.realized_pnl else 0.0,
                    'unrealized_pnl': float(trade.unrealized_pnl) if trade.unrealized_pnl else 0.0,
                    'r_multiple': float(trade.r_multiple) if trade.r_multiple else None,
                    'entry_time': trade.entry_time.isoformat() if trade.entry_time else None,
                    'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
                    'duration_minutes': trade.duration_minutes,
                    'is_winner': trade.is_winner,
                    'strategy': trade.strategy,
                    'setup_type': trade.setup_type,
                    'alpaca_order_id': trade.alpaca_order_id
                }
                trades_data.append(trade_dict)

            return {
                'trades': trades_data,
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'timestamp': datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"Error fetching trade history: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch trade history: {str(e)}")


@router.get("/analytics/summary")
async def get_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    strategy: Optional[str] = Query(None, description="Filter by strategy")
):
    """
    Get comprehensive P&L analytics and trading statistics.

    Includes:
    - Total P&L, win rate, average R-multiple
    - Best and worst trades
    - Strategy breakdown
    - Daily/weekly performance
    """
    try:
        with get_db_session() as db:
            # Calculate start date
            start_date = datetime.now() - timedelta(days=days)

            # Build base query for closed trades
            # Note: TradeStatus enum values are lowercase ('filled', not 'FILLED')
            query = db.query(Trade).filter(
                and_(
                    Trade.status == 'filled',
                    Trade.exit_time >= start_date,
                    Trade.exit_time.isnot(None)
                )
            )

            if strategy:
                query = query.filter(Trade.strategy == strategy)

            trades = query.all()

            if not trades:
                return {
                    'summary': {
                        'total_trades': 0,
                        'total_pnl': 0.0,
                        'win_rate': 0.0,
                        'message': 'No completed trades found in this period'
                    },
                    'period_days': days,
                    'timestamp': datetime.now().isoformat()
                }

            # Calculate statistics
            total_trades = len(trades)
            winners = [t for t in trades if t.is_winner]
            losers = [t for t in trades if t.is_winner is False]

            total_pnl = sum(float(t.realized_pnl) for t in trades if t.realized_pnl)
            win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0

            avg_winner = sum(float(t.realized_pnl) for t in winners) / len(winners) if winners else 0
            avg_loser = sum(float(t.realized_pnl) for t in losers) / len(losers) if losers else 0

            # Best and worst trades
            best_trade = max(trades, key=lambda t: float(t.realized_pnl) if t.realized_pnl else 0)
            worst_trade = min(trades, key=lambda t: float(t.realized_pnl) if t.realized_pnl else 0)

            # R-multiple statistics
            r_multiples = [float(t.r_multiple) for t in trades if t.r_multiple]
            avg_r_multiple = sum(r_multiples) / len(r_multiples) if r_multiples else 0

            # Strategy breakdown
            strategy_stats = {}
            for trade in trades:
                strat = trade.strategy or 'unknown'
                if strat not in strategy_stats:
                    strategy_stats[strat] = {
                        'count': 0,
                        'total_pnl': 0.0,
                        'winners': 0,
                        'losers': 0
                    }

                strategy_stats[strat]['count'] += 1
                strategy_stats[strat]['total_pnl'] += float(trade.realized_pnl) if trade.realized_pnl else 0
                if trade.is_winner:
                    strategy_stats[strat]['winners'] += 1
                else:
                    strategy_stats[strat]['losers'] += 1

            # Add win rates to strategy stats
            for strat, stats in strategy_stats.items():
                stats['win_rate'] = (stats['winners'] / stats['count'] * 100) if stats['count'] > 0 else 0

            # Top traded symbols
            symbol_stats = {}
            for trade in trades:
                sym = trade.symbol
                if sym not in symbol_stats:
                    symbol_stats[sym] = {
                        'count': 0,
                        'total_pnl': 0.0,
                        'winners': 0
                    }

                symbol_stats[sym]['count'] += 1
                symbol_stats[sym]['total_pnl'] += float(trade.realized_pnl) if trade.realized_pnl else 0
                if trade.is_winner:
                    symbol_stats[sym]['winners'] += 1

            # Sort symbols by trade count
            top_symbols = sorted(
                [{'symbol': sym, **stats} for sym, stats in symbol_stats.items()],
                key=lambda x: x['count'],
                reverse=True
            )[:10]

            return {
                'summary': {
                    'total_trades': total_trades,
                    'winning_trades': len(winners),
                    'losing_trades': len(losers),
                    'total_pnl': round(total_pnl, 2),
                    'win_rate': round(win_rate, 2),
                    'average_winner': round(avg_winner, 2),
                    'average_loser': round(avg_loser, 2),
                    'profit_factor': round(abs(avg_winner / avg_loser), 2) if avg_loser != 0 else 0,
                    'average_r_multiple': round(avg_r_multiple, 2)
                },
                'best_trade': {
                    'symbol': best_trade.symbol,
                    'pnl': float(best_trade.realized_pnl),
                    'entry_time': best_trade.entry_time.isoformat() if best_trade.entry_time else None,
                    'r_multiple': float(best_trade.r_multiple) if best_trade.r_multiple else None
                },
                'worst_trade': {
                    'symbol': worst_trade.symbol,
                    'pnl': float(worst_trade.realized_pnl),
                    'entry_time': worst_trade.entry_time.isoformat() if worst_trade.entry_time else None,
                    'r_multiple': float(worst_trade.r_multiple) if worst_trade.r_multiple else None
                },
                'by_strategy': strategy_stats,
                'top_symbols': top_symbols,
                'period_days': days,
                'timestamp': datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"Error calculating analytics: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to calculate analytics: {str(e)}")


@router.get("/analytics/daily")
async def get_daily_pnl(
    days: int = Query(30, ge=1, le=90, description="Number of days to retrieve")
):
    """
    Get daily P&L breakdown for charting and analysis.

    Returns P&L aggregated by day.
    """
    try:
        with get_db_session() as db:
            start_date = datetime.now() - timedelta(days=days)

            # Query trades grouped by day
            trades = db.query(Trade).filter(
                and_(
                    Trade.status == 'filled',
                    Trade.exit_time >= start_date,
                    Trade.exit_time.isnot(None)
                )
            ).order_by(Trade.exit_time).all()

            # Group by date
            daily_pnl = {}
            for trade in trades:
                if trade.exit_time:
                    date_key = trade.exit_time.date().isoformat()
                    if date_key not in daily_pnl:
                        daily_pnl[date_key] = {
                            'date': date_key,
                            'pnl': 0.0,
                            'trades': 0,
                            'winners': 0,
                            'losers': 0
                        }

                    daily_pnl[date_key]['pnl'] += float(trade.realized_pnl) if trade.realized_pnl else 0
                    daily_pnl[date_key]['trades'] += 1
                    if trade.is_winner:
                        daily_pnl[date_key]['winners'] += 1
                    else:
                        daily_pnl[date_key]['losers'] += 1

            # Calculate cumulative P&L
            cumulative = 0.0
            daily_data = []
            for date_key in sorted(daily_pnl.keys()):
                data = daily_pnl[date_key]
                cumulative += data['pnl']
                data['cumulative_pnl'] = round(cumulative, 2)
                data['pnl'] = round(data['pnl'], 2)
                daily_data.append(data)

            return {
                'daily_pnl': daily_data,
                'total_days': len(daily_data),
                'period_days': days,
                'timestamp': datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"Error fetching daily P&L: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily P&L: {str(e)}")


@router.get("/orders/recent")
async def get_recent_orders(
    limit: int = Query(50, le=200, description="Maximum number of orders to return")
):
    """
    Get recent orders from Alpaca API (real-time order data).

    This shows ALL orders including pending, filled, and cancelled.
    """
    try:
        # Get orders from Alpaca
        orders = order_manager.get_recent_orders(limit=limit)

        if not orders:
            return {
                'orders': [],
                'count': 0,
                'message': 'No orders found',
                'timestamp': datetime.now().isoformat()
            }

        # Format orders
        orders_data = []
        for order in orders:
            orders_data.append({
                'id': order.get('id'),
                'symbol': order.get('symbol'),
                'side': order.get('side'),
                'type': order.get('type'),
                'qty': order.get('qty'),
                'filled_qty': order.get('filled_qty', 0),
                'limit_price': order.get('limit_price'),
                'stop_price': order.get('stop_price'),
                'status': order.get('status'),
                'filled_avg_price': order.get('filled_avg_price'),
                'submitted_at': order.get('submitted_at'),
                'filled_at': order.get('filled_at'),
                'cancelled_at': order.get('cancelled_at'),
                'time_in_force': order.get('time_in_force')
            })

        return {
            'orders': orders_data,
            'count': len(orders_data),
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching recent orders: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent orders: {str(e)}")
