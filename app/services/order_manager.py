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
        trade_id: str = None,
        limit_price: Optional[float] = None,
        use_trailing_stop: bool = True,
        trail_percent: Optional[float] = None
    ) -> Optional[str]:
        """
        Place a TRUE BRACKET ORDER using Alpaca's native order_class="bracket".

        This ATOMICALLY places:
        1. Entry order (limit or market)
        2. Take profit order (limit) - FIXED, does not trail
        3. Stop loss order (stop) - FIXED, does not trail

        The stop and take profit are OCO (One-Cancels-Other) - when one fills, the other cancels.

        Args:
            symbol: Stock symbol
            side: 'buy' or 'sell'
            quantity: Number of shares
            stop_loss: Stop loss price (FIXED)
            take_profit: Take profit price (FIXED)
            trade_id: Optional trade ID for tracking
            limit_price: If provided, uses limit order for entry. Otherwise uses market order.
            use_trailing_stop: If True, uses trailing stop instead of fixed stop (default: True)
            trail_percent: Deprecated - trail calculated from stop distance
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

            # Determine order type
            order_type = OrderType.LIMIT.value if limit_price is not None else OrderType.MARKET.value
            if limit_price is not None:
                limit_price = round(limit_price, 2)
                entry_price = limit_price
            else:
                # For market orders, estimate entry price from current quote
                try:
                    quote = self.api.get_latest_trade(symbol)
                    entry_price = float(quote.price)
                except:
                    # Fallback: use stop_loss to estimate entry
                    entry_price = stop_loss * 1.02 if side.lower() == 'buy' else stop_loss * 0.98

            # Log what we're placing
            logger.info(f"🎯 Placing BRACKET ORDER: {side.upper()} {quantity} {symbol}")
            if limit_price:
                logger.info(f"   Entry: LIMIT @ ${limit_price:.2f}")
            else:
                logger.info(f"   Entry: MARKET (est. ${entry_price:.2f})")
            logger.info(f"   Stop Loss: ${stop_loss:.2f} (FIXED)")
            logger.info(f"   Take Profit: ${take_profit:.2f} (FIXED)")

            # Use Alpaca's NATIVE BRACKET ORDER - this guarantees stop + TP are placed atomically
            # order_class="bracket" creates OCO (One-Cancels-Other) legs for stop and take profit
            order_params = {
                'symbol': symbol,
                'qty': quantity,
                'side': side.lower(),
                'type': order_type,
                'time_in_force': TimeInForce.GTC.value,
                'order_class': 'bracket',  # THIS IS THE KEY - native bracket order
                'stop_loss': {'stop_price': str(stop_loss)},  # Fixed stop loss
                'take_profit': {'limit_price': str(take_profit)}  # Fixed take profit
            }

            # Add limit price if using limit order for entry
            if limit_price is not None:
                order_params['limit_price'] = str(limit_price)

            # Place the bracket order - Alpaca handles everything atomically
            order = self.api.submit_order(**order_params)

            logger.info(f"✅ BRACKET ORDER PLACED SUCCESSFULLY: {order.id}")
            logger.info(f"   Entry Order ID: {order.id}")
            logger.info(f"   Stop Loss: ${stop_loss:.2f} (auto-placed by Alpaca)")
            logger.info(f"   Take Profit: ${take_profit:.2f} (auto-placed by Alpaca)")
            logger.info(f"   Both exit orders are OCO (One-Cancels-Other)")

            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": side.lower(),
                "quantity": quantity,
                "type": "bracket",  # Native bracket order
                "order_type": order_type,
                "limit_price": limit_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "status": order.status,
                "submitted_at": datetime.now().isoformat(),
                "trade_id": trade_id,
                "needs_stops": False,  # Bracket order handles this automatically
                "stops_placed": True,  # Already placed by Alpaca
                "order_class": "bracket"
            }

            self.pending_orders[order.id] = order_data
            redis_cache.set(f"order:{order.id}", order_data, expiration=86400)

            return order.id

        except Exception as e:
            logger.error(f"❌ ERROR placing bracket order for {symbol}: {e}")
            logger.error(f"   Parameters: side={side}, qty={quantity}, entry={limit_price if limit_price else 'MARKET'}")
            logger.error(f"   Stop loss: ${stop_loss}, Take profit: ${take_profit}")
            import traceback
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return None

    def _sync_place_stops_after_fill(
        self,
        order_id: str,
        symbol: str,
        quantity: int,
        side: str,
        trail_price: float,
        take_profit: float,
        trade_id: str = None
    ):
        """
        SYNCHRONOUS version: Monitor entry order for fill, then place trailing stop + FIXED take profit.

        This runs in a background thread and uses time.sleep() for reliable operation.

        Args:
            order_id: Entry order ID to monitor
            symbol: Stock symbol
            quantity: Number of shares
            side: Entry order side ('buy' or 'sell')
            trail_price: Dollar amount for trailing stop
            take_profit: Take profit price (FIXED - does not trail)
            trade_id: Associated trade ID
        """
        import time

        try:
            logger.info(f"🔍 {symbol}: [Thread] Monitoring order {order_id[:8]} for fill...")

            # Poll order status until filled (max 10 minutes for limit orders)
            max_checks = 600  # 10 minutes = 600 seconds
            check_interval = 1  # Check every 1 second

            for i in range(max_checks):
                try:
                    order = self.api.get_order(order_id)

                    if order.status == 'filled':
                        filled_qty = int(order.filled_qty) if order.filled_qty else quantity
                        filled_price = float(order.filled_avg_price) if order.filled_avg_price else None

                        logger.info(f"✅ {symbol}: Entry order FILLED!")
                        logger.info(f"   Filled: {filled_qty} shares @ ${filled_price:.2f}" if filled_price else f"   Filled: {filled_qty} shares")
                        logger.info(f"   Placing trailing stop + FIXED take profit...")

                        # Determine exit side (opposite of entry)
                        exit_side = 'sell' if side == 'buy' else 'buy'

                        # Place TRAILING STOP
                        trailing_stop_id = self.place_trailing_stop(
                            symbol=symbol,
                            side=exit_side,
                            quantity=filled_qty,
                            trail_price=trail_price,
                            trade_id=trade_id
                        )

                        if trailing_stop_id:
                            logger.info(f"✅ {symbol}: Trailing stop placed: {trailing_stop_id} (trail: ${trail_price})")
                        else:
                            logger.error(f"❌ {symbol}: Failed to place trailing stop!")

                        # Place FIXED TAKE PROFIT (limit order - does NOT move)
                        tp_id = self.place_limit_order(
                            symbol=symbol,
                            side=exit_side,
                            quantity=filled_qty,
                            limit_price=take_profit,
                            trade_id=trade_id,
                            time_in_force=TimeInForce.GTC.value  # GTC so it doesn't expire
                        )

                        if tp_id:
                            logger.info(f"✅ {symbol}: FIXED Take profit placed: {tp_id} @ ${take_profit:.2f}")
                        else:
                            logger.error(f"❌ {symbol}: Failed to place take profit!")

                        # Mark stops as placed in cache
                        cached_order = redis_cache.get(f"order:{order_id}")
                        if cached_order:
                            cached_order['stops_placed'] = True
                            cached_order['trailing_stop_id'] = trailing_stop_id
                            cached_order['take_profit_id'] = tp_id
                            redis_cache.set(f"order:{order_id}", cached_order, expiration=86400)

                        if trailing_stop_id and tp_id:
                            logger.info(f"🎯 {symbol}: Position FULLY PROTECTED - Trailing Stop + Fixed TP")
                        else:
                            logger.warning(f"⚠️ {symbol}: Position partially protected - check orders manually")

                        return

                    elif order.status in ['cancelled', 'expired', 'rejected']:
                        logger.warning(f"⚠️ {symbol}: Entry order {order.status}, not placing stops")
                        # Mark as processed so periodic checker doesn't retry
                        cached_order = redis_cache.get(f"order:{order_id}")
                        if cached_order:
                            cached_order['stops_placed'] = True  # Mark as done (no stops needed)
                            cached_order['entry_failed'] = True
                            redis_cache.set(f"order:{order_id}", cached_order, expiration=86400)
                        return

                    elif order.status == 'partially_filled':
                        # Log partial fill progress
                        if i % 30 == 0:  # Log every 30 seconds
                            filled = order.filled_qty if order.filled_qty else 0
                            logger.info(f"⏳ {symbol}: Partially filled {filled}/{quantity} shares...")

                except Exception as e:
                    if i % 60 == 0:  # Only log errors every minute to reduce spam
                        logger.error(f"Error checking order {order_id[:8]} status: {e}")

                # Wait before next check
                time.sleep(check_interval)

            # Timeout - let periodic checker handle it
            logger.warning(f"⏰ {symbol}: Entry order not filled after {max_checks} seconds")
            logger.warning(f"   Will be handled by periodic fill checker")

        except Exception as e:
            logger.error(f"Error in _sync_place_stops_after_fill for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _place_trailing_stop_after_fill(
        self,
        order_id: str,
        symbol: str,
        quantity: int,
        side: str,
        trail_price: float,
        take_profit: float,
        trade_id: str = None
    ):
        """
        ASYNC version (legacy): Monitor entry order for fill, then place trailing stop + take profit.
        NOTE: Prefer using _sync_place_stops_after_fill in a thread for reliability.
        """
        import asyncio

        try:
            logger.info(f"🔍 {symbol}: [Async] Monitoring order {order_id} for fill...")

            max_checks = 300
            for i in range(max_checks):
                try:
                    order = self.api.get_order(order_id)

                    if order.status == 'filled':
                        logger.info(f"✅ {symbol}: Entry order FILLED! Placing trailing stop + take profit...")
                        exit_side = 'sell' if side == 'buy' else 'buy'

                        trailing_stop_id = self.place_trailing_stop(
                            symbol=symbol,
                            side=exit_side,
                            quantity=quantity,
                            trail_price=trail_price,
                            trade_id=trade_id
                        )

                        if trailing_stop_id:
                            logger.info(f"✅ {symbol}: Trailing stop placed: {trailing_stop_id}")
                        else:
                            logger.error(f"❌ {symbol}: Failed to place trailing stop!")

                        tp_id = self.place_limit_order(
                            symbol=symbol,
                            side=exit_side,
                            quantity=quantity,
                            limit_price=take_profit,
                            trade_id=trade_id
                        )

                        if tp_id:
                            logger.info(f"✅ {symbol}: Take profit placed: {tp_id}")
                        else:
                            logger.error(f"❌ {symbol}: Failed to place take profit!")

                        cached_order = redis_cache.get(f"order:{order_id}")
                        if cached_order:
                            cached_order['stops_placed'] = True
                            redis_cache.set(f"order:{order_id}", cached_order, expiration=86400)

                        logger.info(f"🎯 {symbol}: Position fully protected with trailing stop + TP")
                        return

                    elif order.status in ['cancelled', 'expired', 'rejected']:
                        logger.warning(f"⚠️ {symbol}: Entry order {order.status}, not placing stops")
                        return

                except Exception as e:
                    logger.error(f"Error checking order status: {e}")

                await asyncio.sleep(1)

            logger.warning(f"⏰ {symbol}: Entry order not filled after {max_checks} seconds")

        except Exception as e:
            logger.error(f"Error in _place_trailing_stop_after_fill for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def place_stop_loss_order(self, symbol: str, quantity: int, stop_price: float, side: str = 'sell', trade_id: str = None) -> Optional[str]:
        """Place a stop-loss order."""
        try:
            if quantity <= 0 or stop_price <= 0:
                logger.error(f"Invalid parameters for stop loss {symbol}: qty={quantity}, stop=${stop_price}")
                return None

            # Round price to 2 decimal places
            stop_price = round(stop_price, 2)

            logger.info(f"Placing stop-loss order: {side} {quantity} shares of {symbol} at ${stop_price}")

            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side=side,
                type=OrderType.STOP.value,
                stop_price=stop_price,
                time_in_force=TimeInForce.GTC.value  # GTC so it doesn't expire
            )
            
            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": side,
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
    
    def place_limit_order(self, symbol: str, side: str, quantity: int, limit_price: float, trade_id: str = None, time_in_force: str = None) -> Optional[str]:
        """
        Place a limit order.

        Args:
            symbol: Stock symbol
            side: 'buy' or 'sell'
            quantity: Number of shares
            limit_price: Limit price
            trade_id: Optional trade ID for tracking
            time_in_force: 'day' or 'gtc' (defaults to 'gtc' for take profit orders)
        """
        try:
            if quantity <= 0 or limit_price <= 0:
                logger.error(f"Invalid parameters for limit order {symbol}: qty={quantity}, price=${limit_price}")
                return None

            # Round price to 2 decimal places
            limit_price = round(limit_price, 2)

            # Default to GTC for take profit orders (so they don't expire at end of day)
            tif = time_in_force if time_in_force else TimeInForce.GTC.value

            logger.info(f"Placing limit order: {side} {quantity} shares of {symbol} at ${limit_price} (TIF: {tif})")

            order = self.api.submit_order(
                symbol=symbol,
                qty=quantity,
                side=side.lower(),
                type=OrderType.LIMIT.value,
                limit_price=limit_price,
                time_in_force=tif
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
    
    def place_trailing_stop(
        self,
        symbol: str,
        side: str,
        quantity: int,
        trail_percent: Optional[float] = None,
        trail_price: Optional[float] = None,
        trade_id: str = None
    ) -> Optional[str]:
        """
        Place a trailing stop order.

        Args:
            symbol: Stock symbol
            side: 'sell' for long positions, 'buy' for short positions
            quantity: Number of shares
            trail_percent: Percentage trail (e.g., 2.0 for 2%)
            trail_price: Dollar trail (e.g., 2.00 for $2 trail)
            trade_id: Optional trade ID for tracking

        Returns:
            Order ID if successful, None otherwise

        Note: Must provide either trail_percent OR trail_price (not both)
        """
        try:
            if quantity <= 0:
                logger.error(f"Invalid quantity for {symbol}: {quantity}")
                return None

            if side.lower() not in ['buy', 'sell']:
                logger.error(f"Invalid side for {symbol}: {side}")
                return None

            if trail_percent is None and trail_price is None:
                logger.error(f"Must provide trail_percent or trail_price for {symbol}")
                return None

            if trail_percent is not None and trail_price is not None:
                logger.error(f"Cannot provide both trail_percent and trail_price for {symbol}")
                return None

            # Build order parameters
            order_params = {
                'symbol': symbol,
                'qty': quantity,
                'side': side.lower(),
                'type': OrderType.TRAILING_STOP.value,
                'time_in_force': TimeInForce.GTC.value  # Good till canceled
            }

            if trail_percent is not None:
                order_params['trail_percent'] = str(trail_percent)
                logger.info(f"🔄 Placing trailing stop: {side} {quantity} {symbol} with {trail_percent}% trail")
            else:
                trail_price = round(trail_price, 2)
                order_params['trail_price'] = str(trail_price)
                logger.info(f"🔄 Placing trailing stop: {side} {quantity} {symbol} with ${trail_price} trail")

            # Submit order
            order = self.api.submit_order(**order_params)

            # Track the order
            order_data = {
                "id": order.id,
                "symbol": symbol,
                "side": side.lower(),
                "quantity": quantity,
                "type": OrderType.TRAILING_STOP.value,
                "trail_percent": trail_percent,
                "trail_price": trail_price,
                "status": order.status,
                "submitted_at": datetime.now().isoformat(),
                "trade_id": trade_id
            }

            self.pending_orders[order.id] = order_data
            redis_cache.set(f"order:{order.id}", order_data, expiration=86400)

            logger.info(f"✅ Trailing stop placed: {order.id}")
            return order.id

        except Exception as e:
            logger.error(f"Error placing trailing stop for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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

    async def check_and_place_missing_stops(self) -> Dict[str, Any]:
        """
        Periodic checker to ensure all filled entry orders have stops placed.

        This is the safety net that catches any orders missed by the async monitor.
        Should be called periodically (every 1-2 minutes) by the trading bot.

        Returns:
            Dict with stats about stops placed
        """
        try:
            stats = {
                "checked": 0,
                "stops_placed": 0,
                "errors": 0,
                "orders_processed": []
            }

            # Get all recent orders (last 100)
            try:
                orders = self.api.list_orders(status='all', limit=100)
            except Exception as e:
                logger.error(f"Error fetching orders for stop check: {e}")
                return stats

            for order in orders:
                try:
                    # Get cached order data
                    cached_order = redis_cache.get(f"order:{order.id}")

                    if not cached_order:
                        continue

                    # Only process orders that need stops but don't have them yet
                    if not cached_order.get('needs_stops', False):
                        continue

                    if cached_order.get('stops_placed', False):
                        continue

                    stats["checked"] += 1

                    # Check if order is filled
                    if order.status != 'filled':
                        continue

                    # Order is filled but missing stops - place them now!
                    symbol = order.symbol
                    quantity = int(order.filled_qty) if order.filled_qty else int(order.qty)
                    entry_side = cached_order.get('side', order.side)
                    exit_side = 'sell' if entry_side == 'buy' else 'buy'

                    trail_price = cached_order.get('trail_price')
                    take_profit = cached_order.get('take_profit')
                    trade_id = cached_order.get('trade_id')

                    if not trail_price or not take_profit:
                        logger.warning(f"⚠️ {symbol}: Order {order.id} missing stop/TP data in cache")
                        continue

                    logger.warning(f"🔧 {symbol}: PLACING MISSING STOPS for order {order.id[:8]} (filled but no stops)")

                    # Place trailing stop
                    trailing_stop_id = self.place_trailing_stop(
                        symbol=symbol,
                        side=exit_side,
                        quantity=quantity,
                        trail_price=trail_price,
                        trade_id=trade_id
                    )

                    if trailing_stop_id:
                        logger.info(f"✅ {symbol}: Missing trailing stop placed: {trailing_stop_id}")
                    else:
                        logger.error(f"❌ {symbol}: Failed to place missing trailing stop")
                        stats["errors"] += 1
                        continue

                    # Place take profit
                    tp_id = self.place_limit_order(
                        symbol=symbol,
                        side=exit_side,
                        quantity=quantity,
                        limit_price=take_profit,
                        trade_id=trade_id
                    )

                    if tp_id:
                        logger.info(f"✅ {symbol}: Missing take profit placed: {tp_id}")
                    else:
                        logger.error(f"❌ {symbol}: Failed to place missing take profit")
                        stats["errors"] += 1
                        continue

                    # Mark stops as placed
                    cached_order['stops_placed'] = True
                    redis_cache.set(f"order:{order.id}", cached_order, expiration=86400)

                    stats["stops_placed"] += 1
                    stats["orders_processed"].append({
                        "symbol": symbol,
                        "order_id": order.id,
                        "trailing_stop_id": trailing_stop_id,
                        "take_profit_id": tp_id
                    })

                    logger.info(f"🎯 {symbol}: Missing stops successfully placed via periodic checker")

                except Exception as e:
                    logger.error(f"Error processing order {order.id} in periodic checker: {e}")
                    stats["errors"] += 1
                    continue

            if stats["stops_placed"] > 0:
                logger.warning(f"🔧 Periodic checker placed stops for {stats['stops_placed']} orders that were missed")

            return stats

        except Exception as e:
            logger.error(f"Error in periodic fill checker: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}

    def health_check(self) -> bool:
        """Check if order management service is healthy."""
        try:
            # Test API connection
            account = self.api.get_account()
            return account is not None

        except Exception as e:
            logger.error(f"Order manager health check failed: {e}")
            return False


# Create global order manager service instance
order_manager = OrderManagerService()