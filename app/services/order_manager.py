"""
Order management service for trade execution.
Handles order placement, tracking, and fills.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
from enum import Enum
import base64
import requests

import alpaca_trade_api as tradeapi
from alpaca_trade_api.entity import Order

from app.core.config import settings
from app.core.cache import redis_cache
from app.core.database import get_db_session
from app.models.trade import Trade, TradeSide, TradeStatus
from app.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types for Alpaca."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(Enum):
    """Time in force options."""
    DAY = "day"
    GTC = "gtc"     # Good Till Canceled
    IOC = "ioc"     # Immediate Or Cancel
    FOK = "fok"     # Fill Or Kill


class OrderManagerService:
    """Service for managing trade orders through Alpaca."""
    
    def __init__(self):
        self.api = tradeapi.REST(
            key_id=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            base_url=settings.alpaca_base_url
        )
        
        # Track pending orders
        self.pending_orders = {}
        
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        try:
            account = self.api.get_account()
            
            return {
                "account_id": account.id,
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "day_trade_count": account.daytrade_count,
                "pattern_day_trader": account.pattern_day_trader
            }
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}
    
    def calculate_position_size(self, symbol: str, entry_price: float, stop_loss: float, risk_amount: float) -> int:
        """Calculate position size based on risk management."""
        try:
            if stop_loss <= 0 or entry_price <= 0 or risk_amount <= 0:
                return 0
            
            # Calculate risk per share
            risk_per_share = abs(entry_price - stop_loss)
            
            if risk_per_share <= 0:
                return 0
            
            # Calculate number of shares
            shares = int(risk_amount / risk_per_share)
            
            # Verify we have enough buying power
            account_info = self.get_account_info()
            buying_power = account_info.get('buying_power', 0)
            
            position_cost = shares * entry_price
            
            if position_cost > buying_power:
                # Reduce position size to fit buying power
                shares = int(buying_power / entry_price)
                logger.warning(f"Reduced position size for {symbol} due to buying power limit: {shares} shares")
            
            return max(shares, 0)
            
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0
    
    def place_market_order(self, symbol: str, side: str, quantity: int, trade_id: str = None) -> Optional[str]:
        """Place a market order."""
        try:
            if quantity <= 0:
                logger.error(f"Invalid quantity for {symbol}: {quantity}")
                return None
            
            # Validate side
            if side.lower() not in ['buy', 'sell']:
                logger.error(f"Invalid side for {symbol}: {side}")
                return None
            
            logger.info(f"Placing market order: {side} {quantity} shares of {symbol}")
            
            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side=side.lower(),
                type=OrderType.MARKET.value,
                time_in_force=TimeInForce.DAY.value
            )
            
            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": side.lower(),
                "quantity": quantity,
                "type": OrderType.MARKET.value,
                "status": order.status,
                "submitted_at": datetime.now().isoformat(),
                "trade_id": trade_id
            }
            
            self.pending_orders[order.id] = order_data
            
            # Cache order info
            redis_cache.set(f"order:{order.id}", order_data, expiration=86400)  # 24 hours
            
            logger.info(f"Market order placed: {order.id}")
            return order.id
            
        except Exception as e:
            logger.error(f"Error placing market order for {symbol}: {e}")
            return None

    def place_bracket_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        stop_loss: float,
        take_profit: float,
        trade_id: str = None
    ) -> Optional[str]:
        """
        Place a bracket order with entry, stop loss, and take profit using Trading API.

        Uses OCO (One-Cancels-Other) order class which creates:
        - Main market order (entry)
        - Stop loss order (triggered if price goes against you)
        - Take profit order (triggered if price goes in your favor)

        When one is filled, the other is automatically cancelled.
        """
        try:
            if quantity <= 0:
                logger.error(f"Invalid quantity for {symbol}: {quantity}")
                return None

            if side.lower() not in ['buy', 'sell']:
                logger.error(f"Invalid side for {symbol}: {side}")
                return None

            # Round prices to 2 decimal places (cents) - Alpaca requirement
            stop_loss = round(stop_loss, 2)
            take_profit = round(take_profit, 2)

            logger.info(f"🎯 Placing BRACKET ORDER (OCO): {side} {quantity} {symbol}")
            logger.info(f"   Stop Loss: ${stop_loss:.2f}, Take Profit: ${take_profit:.2f}")

            # Place bracket order using Trading API
            # order_class='bracket' creates entry + stop loss + take profit in one call
            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side=side.lower(),
                type=OrderType.MARKET.value,
                time_in_force=TimeInForce.DAY.value,
                order_class='bracket',  # This is the KEY parameter!
                stop_loss={
                    'stop_price': str(stop_loss)
                },
                take_profit={
                    'limit_price': str(take_profit)
                }
            )

            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": side.lower(),
                "quantity": quantity,
                "type": "bracket",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "status": order.status,
                "submitted_at": datetime.now().isoformat(),
                "trade_id": trade_id
            }

            self.pending_orders[order.id] = order_data
            redis_cache.set(f"order:{order.id}", order_data, expiration=86400)

            logger.info(f"✅ BRACKET ORDER PLACED: {order.id}")
            logger.info(f"   Entry Order ID: {order.id}")
            logger.info(f"   Stop Loss: ${stop_loss:.2f}, Take Profit: ${take_profit:.2f}")

            return order.id

        except Exception as e:
            logger.error(f"Error placing bracket order for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def place_stop_loss_order(self, symbol: str, quantity: int, stop_price: float, trade_id: str = None) -> Optional[str]:
        """Place a stop-loss order."""
        try:
            if quantity <= 0 or stop_price <= 0:
                logger.error(f"Invalid parameters for stop loss {symbol}: qty={quantity}, stop=${stop_price}")
                return None

            # Round price to 2 decimal places
            stop_price = round(stop_price, 2)

            logger.info(f"Placing stop-loss order: sell {quantity} shares of {symbol} at ${stop_price}")

            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side='sell',
                type=OrderType.STOP.value,
                stop_price=stop_price,
                time_in_force=TimeInForce.DAY.value
            )
            
            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": "sell",
                "quantity": quantity,
                "type": OrderType.STOP.value,
                "stop_price": stop_price,
                "status": order.status,
                "submitted_at": datetime.now().isoformat(),
                "trade_id": trade_id
            }
            
            self.pending_orders[order.id] = order_data
            redis_cache.set(f"order:{order.id}", order_data, expiration=86400)
            
            logger.info(f"Stop-loss order placed: {order.id}")
            return order.id
            
        except Exception as e:
            logger.error(f"Error placing stop-loss order for {symbol}: {e}")
            return None
    
    def place_limit_order(self, symbol: str, side: str, quantity: int, limit_price: float, trade_id: str = None) -> Optional[str]:
        """Place a limit order."""
        try:
            if quantity <= 0 or limit_price <= 0:
                logger.error(f"Invalid parameters for limit order {symbol}: qty={quantity}, price=${limit_price}")
                return None

            # Round price to 2 decimal places
            limit_price = round(limit_price, 2)

            logger.info(f"Placing limit order: {side} {quantity} shares of {symbol} at ${limit_price}")

            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side=side.lower(),
                type=OrderType.LIMIT.value,
                limit_price=limit_price,
                time_in_force=TimeInForce.DAY.value
            )
            
            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": side.lower(),
                "quantity": quantity,
                "type": OrderType.LIMIT.value,
                "limit_price": limit_price,
                "status": order.status,
                "submitted_at": datetime.now().isoformat(),
                "trade_id": trade_id
            }
            
            self.pending_orders[order.id] = order_data
            redis_cache.set(f"order:{order.id}", order_data, expiration=86400)
            
            logger.info(f"Limit order placed: {order.id}")
            return order.id
            
        except Exception as e:
            logger.error(f"Error placing limit order for {symbol}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        try:
            logger.info(f"Cancelling order: {order_id}")
            
            self.api.cancel_order(order_id)
            
            # Remove from tracking
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]
            
            # Update cache
            cached_order = redis_cache.get(f"order:{order_id}")
            if cached_order:
                cached_order['status'] = 'cancelled'
                cached_order['cancelled_at'] = datetime.now().isoformat()
                redis_cache.set(f"order:{order_id}", cached_order, expiration=86400)
            
            logger.info(f"Order cancelled successfully: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get current status of an order."""
        try:
            # First check cache
            cached_order = redis_cache.get(f"order:{order_id}")
            if cached_order:
                return cached_order
            
            # Query API
            order = self.api.get_order(order_id)
            
            order_data = {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": int(order.qty),
                "filled_qty": int(order.filled_qty) if order.filled_qty else 0,
                "type": order.order_type,
                "status": order.status,
                "limit_price": float(order.limit_price) if order.limit_price else None,
                "stop_price": float(order.stop_price) if order.stop_price else None,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None
            }
            
            # Update cache
            redis_cache.set(f"order:{order_id}", order_data, expiration=86400)
            
            return order_data
            
        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}")
            return {}
    
    def check_order_fills(self) -> List[Dict[str, Any]]:
        """Check for filled orders and process them."""
        filled_orders = []
        
        try:
            # Check all pending orders
            orders_to_remove = []
            
            for order_id in list(self.pending_orders.keys()):
                order_status = self.get_order_status(order_id)
                
                if order_status.get('status') == 'filled':
                    filled_orders.append(order_status)
                    orders_to_remove.append(order_id)
                    
                    # Process the fill
                    asyncio.create_task(self._process_order_fill(order_status))
                    
                elif order_status.get('status') in ['cancelled', 'rejected', 'expired']:
                    orders_to_remove.append(order_id)
            
            # Remove processed orders
            for order_id in orders_to_remove:
                if order_id in self.pending_orders:
                    del self.pending_orders[order_id]
            
            return filled_orders
            
        except Exception as e:
            logger.error(f"Error checking order fills: {e}")
            return []
    
    async def _process_order_fill(self, order_data: Dict[str, Any]):
        """Process a filled order and update trade/position records."""
        try:
            with get_db_session() as db:
                symbol = order_data['symbol']
                side = order_data['side']
                quantity = order_data['filled_qty']
                fill_price = order_data['filled_avg_price']
                
                logger.info(f"Processing fill: {side} {quantity} {symbol} at ${fill_price}")
                
                # If this is an entry order, create/update position
                if order_data.get('trade_id'):
                    trade = db.query(Trade).filter(Trade.id == order_data['trade_id']).first()
                    if trade:
                        if side == 'buy':
                            # Long position entry
                            trade.entry_price = Decimal(str(fill_price))
                            trade.entry_time = datetime.now()
                            trade.status = TradeStatus.FILLED
                        else:
                            # Short position entry or position exit
                            if not trade.entry_price:  # Short entry
                                trade.entry_price = Decimal(str(fill_price))
                                trade.entry_time = datetime.now()
                                trade.status = TradeStatus.FILLED
                            else:  # Position exit
                                trade.exit_price = Decimal(str(fill_price))
                                trade.exit_time = datetime.now()
                                trade.update_exit(fill_price, datetime.now())
                
                # Update or create position record
                position = db.query(Position).filter(Position.symbol == symbol, Position.status == 'open').first()
                
                if side == 'buy':
                    if position:
                        # Adding to existing position or covering short
                        if position.quantity < 0:  # Covering short
                            position.quantity += quantity
                            if position.quantity == 0:
                                position.close_position(fill_price)
                        else:  # Adding to long
                            # Calculate new average price
                            total_cost = (float(position.entry_price) * position.quantity) + (fill_price * quantity)
                            total_quantity = position.quantity + quantity
                            position.entry_price = Decimal(str(total_cost / total_quantity))
                            position.quantity = total_quantity
                    else:
                        # New long position
                        new_position = Position(
                            symbol=symbol,
                            quantity=quantity,
                            entry_price=Decimal(str(fill_price)),
                            current_price=Decimal(str(fill_price)),
                            strategy="velez"
                        )
                        db.add(new_position)
                
                else:  # sell
                    if position:
                        if position.quantity > 0:  # Closing long
                            position.quantity -= quantity
                            if position.quantity <= 0:
                                position.close_position(fill_price)
                        else:  # Adding to short
                            position.quantity -= quantity
                    else:
                        # New short position
                        new_position = Position(
                            symbol=symbol,
                            quantity=-quantity,
                            entry_price=Decimal(str(fill_price)),
                            current_price=Decimal(str(fill_price)),
                            strategy="velez"
                        )
                        db.add(new_position)
                
                logger.info(f"Successfully processed fill for {symbol}")
                
        except Exception as e:
            logger.error(f"Error processing order fill: {e}")
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions from Alpaca with stop loss and take profit orders."""
        try:
            positions = self.api.list_positions()

            # Get all open orders to find stop/limit orders for positions
            open_orders = {}
            try:
                orders = self.api.list_orders(status='open')
                for order in orders:
                    symbol = order.symbol
                    if symbol not in open_orders:
                        open_orders[symbol] = {'stop_loss': None, 'take_profit': None}

                    # Identify stop loss orders
                    if order.type == 'stop':
                        open_orders[symbol]['stop_loss'] = float(order.stop_price) if hasattr(order, 'stop_price') and order.stop_price else None

                    # Identify take profit orders (limit orders in opposite direction)
                    elif order.type == 'limit':
                        open_orders[symbol]['take_profit'] = float(order.limit_price) if hasattr(order, 'limit_price') and order.limit_price else None
            except Exception as e:
                logger.warning(f"Could not fetch open orders: {e}")

            position_list = []
            for pos in positions:
                # Safely get attributes with defaults
                qty = int(pos.qty) if hasattr(pos, 'qty') else 0
                market_value = float(pos.market_value) if hasattr(pos, 'market_value') else 0.0
                cost_basis = float(pos.cost_basis) if hasattr(pos, 'cost_basis') else 0.0
                current_price = float(pos.current_price) if hasattr(pos, 'current_price') else 0.0
                avg_entry_price = float(pos.avg_entry_price) if hasattr(pos, 'avg_entry_price') else 0.0

                # Calculate unrealized P&L if not available
                unrealized_pnl = 0.0
                unrealized_pnl_percent = 0.0

                if hasattr(pos, 'unrealized_pnl'):
                    unrealized_pnl = float(pos.unrealized_pnl)
                elif hasattr(pos, 'unrealized_pl'):  # Alternative attribute name
                    unrealized_pnl = float(pos.unrealized_pl)
                else:
                    # Calculate manually
                    if qty != 0 and avg_entry_price > 0:
                        unrealized_pnl = qty * (current_price - avg_entry_price)

                if hasattr(pos, 'unrealized_plpc'):
                    unrealized_pnl_percent = float(pos.unrealized_plpc) * 100
                elif avg_entry_price > 0:
                    unrealized_pnl_percent = ((current_price - avg_entry_price) / avg_entry_price) * 100

                # Get stop loss and take profit from open orders
                symbol_orders = open_orders.get(pos.symbol, {})

                position_data = {
                    "symbol": pos.symbol,
                    "quantity": qty,
                    "side": "long" if qty > 0 else "short",
                    "market_value": market_value,
                    "cost_basis": cost_basis,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_percent": unrealized_pnl_percent,
                    "current_price": current_price,
                    "avg_entry_price": avg_entry_price,
                    "stop_loss": symbol_orders.get('stop_loss'),
                    "take_profit": symbol_orders.get('take_profit')
                }
                position_list.append(position_data)

            return position_list

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions (alias for get_positions for consistency)."""
        return self.get_positions()

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific position by symbol."""
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos['symbol'] == symbol:
                    return pos
            return None
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {e}")
            return None

    def close_position(self, symbol: str) -> bool:
        """
        Close a specific position by symbol.

        Uses Trading API to close the position by placing an offsetting order.
        """
        try:
            # Get the position
            position = self.get_position(symbol)

            if not position:
                logger.warning(f"No position found for {symbol}")
                return False

            quantity = abs(position['quantity'])
            side = 'sell' if position['quantity'] > 0 else 'buy'

            logger.info(f"🔒 Closing position for {symbol}")
            logger.info(f"   Current Qty: {position['quantity']}")
            logger.info(f"   Current Value: ${position['market_value']:.2f}")
            logger.info(f"   Unrealized P/L: ${position['unrealized_pnl']:.2f}")

            # Place offsetting market order
            order_id = self.place_market_order(symbol, side, quantity)

            if order_id:
                logger.info(f"✅ Position closed successfully for {symbol}")
                return True
            else:
                logger.error(f"❌ Failed to close position for {symbol}")
                return False

        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def close_all_positions(self) -> bool:
        """Close all open positions (end of day)."""
        try:
            logger.info("Closing all positions for end of day")
            
            positions = self.get_positions()
            
            for position in positions:
                symbol = position['symbol']
                quantity = abs(position['quantity'])
                side = 'sell' if position['quantity'] > 0 else 'buy'
                
                order_id = self.place_market_order(symbol, side, quantity)
                if order_id:
                    logger.info(f"Placed closing order for {symbol}: {order_id}")
                else:
                    logger.error(f"Failed to place closing order for {symbol}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return False
    
    def get_recent_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent orders from Alpaca."""
        try:
            # Get recent orders (all statuses)
            orders = self.api.list_orders(status='all', limit=limit)

            orders_list = []
            for order in orders:
                order_data = {
                    'id': order.id,
                    'symbol': order.symbol,
                    'side': order.side,
                    'type': order.order_type,
                    'qty': int(order.qty) if order.qty else 0,
                    'filled_qty': int(order.filled_qty) if order.filled_qty else 0,
                    'limit_price': float(order.limit_price) if order.limit_price else None,
                    'stop_price': float(order.stop_price) if order.stop_price else None,
                    'status': order.status,
                    'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                    'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                    'filled_at': order.filled_at.isoformat() if order.filled_at else None,
                    'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
                    'time_in_force': order.time_in_force
                }
                orders_list.append(order_data)

            return orders_list

        except Exception as e:
            logger.error(f"Error getting recent orders: {e}")
            return []

    def health_check(self) -> bool:
        """Check if order management service is healthy."""
        try:
            # Test API connection
            account = self.api.get_account()
            return account is not None

        except Exception as e:
            logger.error(f"Order manager health check failed: {e}")
            return False


class BrokerOrderManagerService:
    """
    Broker API Order Manager - Supports bracket orders with stop loss + take profit.

    Uses Alpaca Broker API instead of Trading API for advanced order types.
    """

    def __init__(self):
        self.broker_api_url = settings.alpaca_broker_api_url
        self.email = settings.alpaca_broker_email
        self.password = settings.alpaca_broker_password
        self.account_id = settings.alpaca_broker_account_id

        # Create Basic Auth header
        credentials = f"{self.email}:{self.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        self.auth_header = f"Basic {encoded_credentials}"

        # Standard headers for all requests
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": self.auth_header
        }

        # Market data API (still uses Trading API for quotes)
        self.data_api = tradeapi.REST(
            key_id=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            base_url=settings.alpaca_base_url
        )

        # Fetch account ID if not set
        if not self.account_id:
            self._fetch_account_id()

        # Track pending orders
        self.pending_orders = {}

    def _fetch_account_id(self):
        """Fetch the account ID from Broker API."""
        try:
            url = f"{self.broker_api_url}/v1/accounts"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                accounts = response.json()
                if accounts and len(accounts) > 0:
                    self.account_id = accounts[0]['id']
                    logger.info(f"✅ Fetched Broker Account ID: {self.account_id}")
                else:
                    logger.error("No accounts found in Broker API")
            else:
                logger.error(f"Failed to fetch account ID: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Error fetching account ID: {e}")

    def get_account_info(self) -> Dict[str, Any]:
        """Get account information from Broker API."""
        try:
            if not self.account_id:
                logger.error("No account ID available")
                return {}

            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/account"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                account = response.json()
                return {
                    "account_id": account.get('id'),
                    "equity": float(account.get('equity', 0)),
                    "cash": float(account.get('cash', 0)),
                    "buying_power": float(account.get('buying_power', 0)),
                    "portfolio_value": float(account.get('portfolio_value', 0))
                }
            else:
                logger.error(f"Failed to get account info: {response.status_code} - {response.text}")
                return {}

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}

    def place_bracket_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        stop_loss: float,
        take_profit: float,
        trade_id: str = None
    ) -> Optional[str]:
        """
        Place a bracket order with entry, stop loss, and take profit.

        This is the KEY method that uses Broker API to place all three orders at once!
        """
        try:
            if not self.account_id:
                logger.error("No account ID available for bracket order")
                return None

            if quantity <= 0:
                logger.error(f"Invalid quantity for {symbol}: {quantity}")
                return None

            if side.lower() not in ['buy', 'sell']:
                logger.error(f"Invalid side for {symbol}: {side}")
                return None

            # Round prices to 2 decimal places (cents) - Alpaca requirement
            stop_loss = round(stop_loss, 2)
            take_profit = round(take_profit, 2)

            logger.info(f"🎯 Placing BRACKET ORDER: {side} {quantity} {symbol}")
            logger.info(f"   Stop Loss: ${stop_loss:.2f}, Take Profit: ${take_profit:.2f}")

            # Broker API endpoint
            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/orders"

            # Build bracket order payload
            payload = {
                "symbol": symbol,
                "qty": str(quantity),
                "side": side.lower(),
                "type": "market",
                "time_in_force": "day",
                "order_class": "bracket",
                "stop_loss": {
                    "stop_price": str(stop_loss)
                },
                "take_profit": {
                    "limit_price": str(take_profit)
                }
            }

            # Make the request
            response = requests.post(url, json=payload, headers=self.headers)

            if response.status_code in [200, 201]:
                order_data = response.json()
                order_id = order_data.get('id')

                # Track the order
                order_info = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": side.lower(),
                    "quantity": quantity,
                    "type": "bracket",
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "status": order_data.get('status'),
                    "submitted_at": datetime.now().isoformat(),
                    "trade_id": trade_id
                }

                self.pending_orders[order_id] = order_info
                redis_cache.set(f"order:{order_id}", order_info, expiration=86400)

                logger.info(f"✅ BRACKET ORDER PLACED: {order_id}")
                logger.info(f"   Entry Order ID: {order_id}")
                logger.info(f"   Stop Loss: ${stop_loss:.2f}, Take Profit: ${take_profit:.2f}")

                return order_id
            else:
                logger.error(f"❌ Bracket order failed: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error placing bracket order for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def place_market_order(self, symbol: str, side: str, quantity: int, trade_id: str = None) -> Optional[str]:
        """Place a simple market order (without stop/take profit)."""
        try:
            if not self.account_id:
                logger.error("No account ID available")
                return None

            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/orders"

            payload = {
                "symbol": symbol,
                "qty": str(quantity),
                "side": side.lower(),
                "type": "market",
                "time_in_force": "day"
            }

            response = requests.post(url, json=payload, headers=self.headers)

            if response.status_code in [200, 201]:
                order_data = response.json()
                order_id = order_data.get('id')
                logger.info(f"✅ Market order placed: {order_id}")
                return order_id
            else:
                logger.error(f"Market order failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return None

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions from Broker API."""
        try:
            if not self.account_id:
                logger.error("No account ID available")
                return []

            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/positions"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                positions = response.json()
                logger.info(f"Retrieved {len(positions)} open positions from Broker API")
                return positions
            else:
                logger.error(f"Failed to get positions: {response.status_code} - {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get a specific position by symbol."""
        try:
            if not self.account_id:
                logger.error("No account ID available")
                return None

            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/positions/{symbol}"
            response = requests.get(url, headers=self.headers)

            if response.status_code == 200:
                position = response.json()
                return position
            elif response.status_code == 404:
                logger.info(f"No position found for {symbol}")
                return None
            else:
                logger.error(f"Failed to get position for {symbol}: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {e}")
            return None

    def close_position(self, symbol: str) -> bool:
        """
        Close a position using Broker API.

        This uses the Broker API DELETE endpoint to close a position.
        URL: DELETE /v1/trading/accounts/{account_id}/positions/{symbol}
        """
        try:
            if not self.account_id:
                logger.error("No account ID available")
                return False

            # First check if position exists
            position = self.get_position(symbol)
            if not position:
                logger.warning(f"No position found for {symbol}")
                return False

            logger.info(f"🔒 Closing position for {symbol}")
            logger.info(f"   Current Qty: {position.get('qty')}")
            logger.info(f"   Current Value: ${float(position.get('market_value', 0)):.2f}")

            # Close the position using Broker API DELETE endpoint
            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/positions/{symbol}"
            response = requests.delete(url, headers=self.headers)

            if response.status_code in [200, 204]:
                logger.info(f"✅ Position closed successfully for {symbol}")
                return True
            else:
                logger.error(f"❌ Failed to close position for {symbol}: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def close_all_positions(self) -> bool:
        """Close all open positions."""
        try:
            if not self.account_id:
                logger.error("No account ID available")
                return False

            logger.info("🔒 Closing all positions...")

            # Close all positions using Broker API
            url = f"{self.broker_api_url}/v1/trading/accounts/{self.account_id}/positions"
            response = requests.delete(url, headers=self.headers)

            if response.status_code in [200, 204, 207]:  # 207 = Multi-Status (partial success)
                logger.info("✅ All positions closed")
                return True
            else:
                logger.error(f"Failed to close all positions: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return False

    def health_check(self) -> bool:
        """Check if Broker API is accessible."""
        try:
            account_info = self.get_account_info()
            return bool(account_info and account_info.get('account_id'))
        except Exception as e:
            logger.error(f"Broker API health check failed: {e}")
            return False


# Create global order manager service instance
# Using Trading API with OCO/Bracket orders for stop loss + take profit
order_manager = OrderManagerService()