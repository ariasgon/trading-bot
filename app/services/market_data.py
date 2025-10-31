"""
Market data service for Alpaca integration.
Handles real-time and historical market data.
"""
import asyncio
import logging
import json
from datetime import datetime, timedelta, date, time
from typing import List, Dict, Optional, Any, Tuple
from decimal import Decimal
import pandas as pd

import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame, TimeFrameUnit
from alpaca_trade_api.stream import Stream

from app.core.config import settings
from app.core.cache import redis_cache
from app.core.database import get_db_session
from app.models.market_data import MarketData, PreMarketData

logger = logging.getLogger(__name__)


class MarketDataService:
    """Service for handling market data from Alpaca."""
    
    def __init__(self):
        self.api = tradeapi.REST(
            key_id=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            base_url=settings.alpaca_base_url
        )
        self.stream = None
        self.is_streaming = False
        self.subscribed_symbols = set()
        
    async def initialize_stream(self):
        """Initialize WebSocket stream for real-time data."""
        try:
            self.stream = Stream(
                key_id=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
                base_url=settings.alpaca_base_url,
                data_feed='iex'  # Use IEX for paper trading
            )
            
            # Set up handlers
            self.stream.subscribe_trades(self._handle_trade)
            self.stream.subscribe_quotes(self._handle_quote)
            self.stream.subscribe_bars(self._handle_bar)
            
            logger.info("Market data stream initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize stream: {e}")
            return False
    
    async def _handle_trade(self, trade):
        """Handle incoming trade data."""
        try:
            # Cache the latest trade
            redis_cache.set(
                f"last_trade:{trade.symbol}",
                {
                    "symbol": trade.symbol,
                    "price": float(trade.price),
                    "size": trade.size,
                    "timestamp": trade.timestamp.isoformat()
                },
                expiration=300  # 5 minutes
            )
            
            # Update any open positions with current price
            await self._update_position_prices(trade.symbol, float(trade.price))
            
        except Exception as e:
            logger.error(f"Error handling trade for {trade.symbol}: {e}")
    
    async def _handle_quote(self, quote):
        """Handle incoming quote data."""
        try:
            # Cache current bid/ask
            redis_cache.set(
                f"quote:{quote.symbol}",
                {
                    "symbol": quote.symbol,
                    "bid": float(quote.bid_price),
                    "ask": float(quote.ask_price),
                    "bid_size": quote.bid_size,
                    "ask_size": quote.ask_size,
                    "timestamp": quote.timestamp.isoformat()
                },
                expiration=60  # 1 minute
            )
            
        except Exception as e:
            logger.error(f"Error handling quote for {quote.symbol}: {e}")
    
    async def _handle_bar(self, bar):
        """Handle incoming bar data."""
        try:
            # Store in database for technical analysis
            await self._store_bar_data(bar)
            
            # Cache latest bar
            redis_cache.set(
                f"latest_bar:{bar.symbol}:1T",
                {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume,
                    "vwap": float(bar.vwap) if bar.vwap else None
                },
                expiration=300
            )
            
        except Exception as e:
            logger.error(f"Error handling bar for {bar.symbol}: {e}")
    
    async def _store_bar_data(self, bar):
        """Store bar data in database."""
        try:
            with get_db_session() as db:
                market_data = MarketData(
                    symbol=bar.symbol,
                    timeframe="1T",
                    timestamp=bar.timestamp,
                    open_price=Decimal(str(bar.open)),
                    high_price=Decimal(str(bar.high)),
                    low_price=Decimal(str(bar.low)),
                    close_price=Decimal(str(bar.close)),
                    volume=bar.volume,
                    vwap=Decimal(str(bar.vwap)) if bar.vwap else None
                )
                
                db.add(market_data)
                
        except Exception as e:
            logger.error(f"Error storing bar data for {bar.symbol}: {e}")
    
    async def _update_position_prices(self, symbol: str, price: float):
        """Update position prices when new trade data arrives."""
        try:
            # This would update Position models in database
            # For now, we'll update the cached position data
            cached_position = redis_cache.get_position(symbol)
            if cached_position:
                cached_position['current_price'] = price
                cached_position['last_updated'] = datetime.now().isoformat()
                redis_cache.set_position(symbol, cached_position)
                
        except Exception as e:
            logger.error(f"Error updating position price for {symbol}: {e}")
    
    def subscribe_symbol(self, symbol: str):
        """Subscribe to real-time data for a symbol."""
        if self.stream and symbol not in self.subscribed_symbols:
            self.stream.subscribe_trades([symbol])
            self.stream.subscribe_quotes([symbol])
            self.stream.subscribe_bars([symbol])
            self.subscribed_symbols.add(symbol)
            logger.info(f"Subscribed to real-time data for {symbol}")
    
    def unsubscribe_symbol(self, symbol: str):
        """Unsubscribe from real-time data for a symbol."""
        if self.stream and symbol in self.subscribed_symbols:
            self.stream.unsubscribe_trades([symbol])
            self.stream.unsubscribe_quotes([symbol])
            self.stream.unsubscribe_bars([symbol])
            self.subscribed_symbols.remove(symbol)
            logger.info(f"Unsubscribed from real-time data for {symbol}")
    
    async def start_streaming(self, symbols: List[str]):
        """Start streaming data for given symbols."""
        if not self.stream:
            await self.initialize_stream()
        
        if not self.stream:
            raise Exception("Failed to initialize stream")
        
        # Subscribe to symbols
        for symbol in symbols:
            self.subscribe_symbol(symbol)
        
        # Start the stream
        if not self.is_streaming:
            self.is_streaming = True
            logger.info(f"Starting market data stream for {len(symbols)} symbols")
            await self.stream.run()
    
    def stop_streaming(self):
        """Stop the market data stream."""
        if self.stream and self.is_streaming:
            self.stream.stop()
            self.is_streaming = False
            self.subscribed_symbols.clear()
            logger.info("Market data stream stopped")
    
    def _parse_timeframe(self, timeframe: str) -> TimeFrame:
        """Parse timeframe string into Alpaca TimeFrame object."""
        try:
            timeframe = timeframe.upper()

            # Handle minute formats: 1T, 5T, 15T, 1Min, 5Min, etc.
            if 'T' in timeframe or 'MIN' in timeframe:
                # Extract number
                num_str = timeframe.replace('T', '').replace('MIN', '').replace('MINUTE', '').strip()
                minutes = int(num_str) if num_str else 1

                if minutes == 1:
                    return TimeFrame.Minute
                else:
                    return TimeFrame(minutes, TimeFrameUnit.Minute)

            # Handle hour formats: 1H, 2H, 1Hour, etc.
            elif 'H' in timeframe or 'HOUR' in timeframe:
                num_str = timeframe.replace('H', '').replace('HOUR', '').strip()
                hours = int(num_str) if num_str else 1

                if hours == 1:
                    return TimeFrame.Hour
                else:
                    return TimeFrame(hours, TimeFrameUnit.Hour)

            # Handle day formats: 1D, 1Day, etc.
            elif 'D' in timeframe or 'DAY' in timeframe:
                num_str = timeframe.replace('D', '').replace('DAY', '').strip()
                days = int(num_str) if num_str else 1

                if days == 1:
                    return TimeFrame.Day
                else:
                    return TimeFrame(days, TimeFrameUnit.Day)

            # Default to 1 minute
            else:
                logger.warning(f"Unknown timeframe format: {timeframe}, defaulting to 1 minute")
                return TimeFrame.Minute

        except Exception as e:
            logger.error(f"Error parsing timeframe {timeframe}: {e}")
            return TimeFrame.Minute

    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Get historical bar data with timeout protection."""
        try:
            # Don't cache DataFrames - Redis serialization causes type errors
            # Removed caching to prevent 'str' object has no attribute 'tail' error

            # Convert timeframe string to Alpaca TimeFrame object
            tf = self._parse_timeframe(timeframe)
            
            # Add timeout protection using threading
            import threading
            import queue
            
            result_queue = queue.Queue()
            error_queue = queue.Queue()
            
            def fetch_bars():
                try:
                    # Convert datetime objects to ISO format strings (YYYY-MM-DD)
                    start_str = start.strftime('%Y-%m-%d') if hasattr(start, 'strftime') else str(start)
                    end_str = end.strftime('%Y-%m-%d') if hasattr(end, 'strftime') else str(end)

                    bars = self.api.get_bars(
                        symbol,
                        tf,
                        start=start_str,
                        end=end_str,
                        adjustment='raw'
                    ).df
                    result_queue.put(bars)
                except Exception as e:
                    error_queue.put(e)
            
            # Run API call in thread with timeout
            fetch_thread = threading.Thread(target=fetch_bars)
            fetch_thread.start()
            fetch_thread.join(timeout=10)  # 10-second timeout
            
            if fetch_thread.is_alive():
                logger.warning(f"API timeout for {symbol} historical bars - using fallback")
                return pd.DataFrame()  # Return empty DataFrame on timeout
            
            # Check for results
            if not result_queue.empty():
                bars = result_queue.get()
                # Don't cache DataFrames - Redis serialization causes type errors
                # redis_cache.set(cache_key, bars, expiration=60)
                return bars
            elif not error_queue.empty():
                error = error_queue.get()
                logger.error(f"Error getting historical bars for {symbol}: {error}")
                return pd.DataFrame()
            else:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Critical error getting historical bars for {symbol}: {e}")
            return pd.DataFrame()

    def get_bars(self, symbol: str, timeframe: str = '1Min', limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Get recent bar data for a symbol with a limit on number of bars.
        This is a convenience wrapper around get_historical_bars().

        Args:
            symbol: Stock symbol
            timeframe: Timeframe string (1Min, 5Min, 15Min, 1Hour, 1Day, etc.)
            limit: Number of recent bars to fetch

        Returns:
            DataFrame with OHLCV data or None if error
        """
        try:
            # Calculate lookback period based on timeframe and limit
            now = datetime.now()

            # Map timeframe to timedelta and standard format
            timeframe_lower = timeframe.lower()
            if 'min' in timeframe_lower:
                minutes = int(timeframe_lower.replace('min', ''))
                lookback = timedelta(minutes=minutes * limit * 2)  # 2x buffer for market hours
                tf = f"{minutes}T"  # Convert to Alpaca format (1T, 5T, etc.)
            elif 'hour' in timeframe_lower:
                hours = int(timeframe_lower.replace('hour', ''))
                lookback = timedelta(hours=hours * limit * 2)
                tf = "1H" if hours == 1 else f"{hours}H"
            elif 'day' in timeframe_lower:
                days = int(timeframe_lower.replace('day', ''))
                lookback = timedelta(days=days * limit * 2)
                tf = "1D" if days == 1 else f"{days}D"
            else:
                # Assume it's already in Alpaca format (1T, 5T, 1D, etc.)
                tf = timeframe
                # Try to extract minutes for lookback calculation
                if 'T' in timeframe.upper():
                    try:
                        minutes = int(timeframe.replace('T', '').replace('t', ''))
                        lookback = timedelta(minutes=minutes * limit * 2)
                    except:
                        lookback = timedelta(minutes=limit * 2)
                elif 'D' in timeframe.upper():
                    lookback = timedelta(days=limit * 2)
                else:
                    lookback = timedelta(minutes=limit * 2)

            start = now - lookback

            # Get historical bars
            df = self.get_historical_bars(symbol, tf, start, now)

            # Validate that df is a DataFrame before proceeding
            if df is None or not isinstance(df, pd.DataFrame):
                return None

            if len(df) == 0:
                return None

            # Return only the most recent 'limit' bars
            return df.tail(limit)

        except Exception as e:
            logger.error(f"Error getting bars for {symbol}: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            # First try cache
            cached_trade = redis_cache.get(f"last_trade:{symbol}")
            if cached_trade:
                return cached_trade['price']
            
            # Fall back to API
            snapshot = self.api.get_snapshot(symbol)
            if snapshot and snapshot.latest_trade:
                price = float(snapshot.latest_trade.price)
                
                # Cache for future use
                redis_cache.set(
                    f"last_trade:{symbol}",
                    {
                        "symbol": symbol,
                        "price": price,
                        "timestamp": datetime.now().isoformat()
                    },
                    expiration=60
                )
                
                return price
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive quote data including daily OHLC for gap analysis."""
        try:
            # First try cached quote
            cached_quote = redis_cache.get(f"quote:{symbol}")
            if cached_quote:
                return cached_quote

            # Get current snapshot for live price
            snapshot = self.api.get_snapshot(symbol)
            if not snapshot:
                logger.error(f"No snapshot data for {symbol}")
                return None

            current_price = float(snapshot.latest_trade.price) if snapshot.latest_trade else 0

            # Get or set the FIXED opening reference prices (stored once per day, never changes)
            previous_close, today_open, opening_reference_price = self._get_opening_reference_prices(symbol)

            # Calculate gaps using the FIXED opening reference price
            gap_from_close = current_price - previous_close if previous_close > 0 else 0
            gap_close_percent = (gap_from_close / previous_close * 100) if previous_close > 0 else 0

            # Opening gap (gap from previous close to opening reference) - NEVER CHANGES during the day
            opening_gap = opening_reference_price - previous_close if previous_close > 0 and opening_reference_price > 0 else 0
            opening_gap_percent = (opening_gap / previous_close * 100) if previous_close > 0 and opening_reference_price > 0 else 0

            gap_from_open = current_price - today_open if today_open > 0 else 0
            gap_open_percent = (gap_from_open / today_open * 100) if today_open > 0 else 0

            quote_data = {
                'symbol': symbol,
                'price': current_price,
                'bid': float(snapshot.latest_quote.bid_price) if snapshot.latest_quote else 0,
                'ask': float(snapshot.latest_quote.ask_price) if snapshot.latest_quote else 0,
                'volume': snapshot.daily_bar.volume if snapshot.daily_bar else 0,
                'previous_close': previous_close,
                'today_open': today_open,
                'premarket_price': opening_reference_price,  # Using fixed opening reference price
                'gap_amount': gap_from_close,
                'gap_percent': gap_close_percent,
                'premarket_gap': opening_gap,  # Fixed gap amount - never changes
                'premarket_gap_percent': opening_gap_percent,  # Fixed gap percentage - never changes
                'gap_from_open': gap_from_open,
                'gap_open_percent': gap_open_percent,
                'timestamp': datetime.now().isoformat()
            }

            logger.info(f"📊 QUOTE: {symbol} - Current: ${current_price:.2f}, Prev Close: ${previous_close:.2f}, Opening Ref: ${opening_reference_price:.2f}, FIXED Gap: {opening_gap_percent:.2f}%")

            # Cache for 1 minute
            redis_cache.set(f"quote:{symbol}", quote_data, expiration=60)

            return quote_data

        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return None
    
    def _get_opening_reference_prices(self, symbol: str) -> Tuple[float, float, float]:
        """
        Get or set FIXED opening reference prices for the trading day.

        This method stores the opening reference price ONCE per day and NEVER updates it.
        The opening reference price is either:
        1. The last pre-market price (at 9:29 AM or last bar before 9:30 AM)
        2. The market opening price (first bar at 9:30 AM)

        Returns:
            Tuple of (previous_close, today_open, opening_reference_price)
        """
        try:
            import pytz

            # Get timezone-aware dates
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            today_date = now_eastern.date().isoformat()

            # Check if we have cached opening reference prices for today
            cache_key = f"opening_ref:{symbol}:{today_date}"
            cached_ref = redis_cache.get(cache_key)

            if cached_ref:
                # Use cached fixed reference prices (never recalculate during the day)
                logger.info(f"📌 USING CACHED OPENING REF: {symbol} - Prev Close: ${cached_ref['previous_close']:.2f}, Opening Ref: ${cached_ref['opening_reference']:.2f}")
                return (
                    cached_ref['previous_close'],
                    cached_ref['today_open'],
                    cached_ref['opening_reference']
                )

            # If not cached, calculate and store for the entire day
            logger.info(f"🔍 CALCULATING OPENING REF: {symbol} - First time today, storing fixed reference...")

            previous_close, today_open, premarket_price = self._get_daily_ohlc_data(symbol)

            # The opening reference is the premarket price if available, otherwise today's open
            opening_reference_price = premarket_price if premarket_price > 0 else today_open

            # Store this FIXED reference for the entire trading day (expires at midnight + 8 hours = 8 AM next day)
            reference_data = {
                'previous_close': previous_close,
                'today_open': today_open,
                'opening_reference': opening_reference_price,
                'cached_at': datetime.now().isoformat()
            }

            # Cache until end of trading day (expires in 8 hours)
            redis_cache.set(cache_key, reference_data, expiration=28800)

            logger.info(f"✅ STORED OPENING REF: {symbol} - Prev Close: ${previous_close:.2f}, Opening Ref: ${opening_reference_price:.2f}, Today Open: ${today_open:.2f}")

            return previous_close, today_open, opening_reference_price

        except Exception as e:
            logger.error(f"Error getting opening reference prices for {symbol}: {e}")
            # Fallback to current calculation
            return self._get_daily_ohlc_data(symbol)

    def _get_daily_ohlc_data(self, symbol: str) -> Tuple[float, float, float]:
        """Get previous close, today's open, and premarket price using proper Alpaca API."""
        try:
            from alpaca_trade_api.rest import TimeFrame
            import pytz
            
            # Get timezone-aware dates
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            
            # Get last 5 trading days to ensure we have data
            end_date = now_eastern.date()
            start_date = end_date - timedelta(days=7)  # Go back 7 days to account for weekends
            
            # Get daily bars for historical data
            daily_bars = self.api.get_bars(
                symbol,
                TimeFrame.Day,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                adjustment='raw'
            )
            
            previous_close = 0.0
            today_open = 0.0
            premarket_price = 0.0
            
            if daily_bars and len(daily_bars) >= 2:
                daily_df = daily_bars.df
                if len(daily_df) >= 2:
                    previous_close = float(daily_df['close'].iloc[-2])
                    today_open = float(daily_df['open'].iloc[-1])
            
            # Get premarket data using minute bars from 4:00 AM to 9:30 AM ET
            try:
                # Define premarket hours (4:00 AM - 9:30 AM ET)
                premarket_start = now_eastern.replace(hour=4, minute=0, second=0, microsecond=0)
                premarket_end = now_eastern.replace(hour=9, minute=30, second=0, microsecond=0)
                market_open_time = time(9, 30)

                # Only get premarket if we're in or past premarket hours
                if now_eastern.time() >= time(4, 0):
                    # Check if market has already opened
                    # If market is open, don't use 'asof' parameter (causes "invalid asof" error)
                    # If still in premarket, use current time as 'asof'
                    if now_eastern.time() >= market_open_time:
                        # Market has opened - fetch premarket without 'asof'
                        premarket_bars = self.api.get_bars(
                            symbol,
                            TimeFrame.Minute,
                            start=premarket_start.isoformat(),
                            end=premarket_end.isoformat(),
                            adjustment='raw'
                        )
                    else:
                        # Still in premarket - use 'asof' for real-time data
                        premarket_bars = self.api.get_bars(
                            symbol,
                            TimeFrame.Minute,
                            start=premarket_start.isoformat(),
                            end=premarket_end.isoformat(),
                            asof=now_eastern.isoformat(),
                            adjustment='raw'
                        )

                    if premarket_bars and len(premarket_bars) > 0:
                        premarket_df = premarket_bars.df
                        if not premarket_df.empty:
                            # Get the most recent premarket price
                            premarket_price = float(premarket_df['close'].iloc[-1])
                            logger.info(f"📊 PREMARKET: {symbol} - Last premarket price: ${premarket_price:.2f}")
                        else:
                            logger.info(f"📊 PREMARKET: {symbol} - No premarket activity yet")
                    else:
                        logger.info(f"📊 PREMARKET: {symbol} - No premarket data available")

            except Exception as premarket_error:
                logger.warning(f"Premarket data error for {symbol}: {premarket_error}")
                # Use today's open as fallback for premarket
                premarket_price = today_open
            
            logger.info(f"📈 OHLC DATA: {symbol} - Prev Close: ${previous_close:.2f}, Premarket: ${premarket_price:.2f}, Today Open: ${today_open:.2f}")
            
            return previous_close, today_open, premarket_price
            
        except Exception as e:
            logger.error(f"Error getting OHLC data for {symbol}: {e}")
            return 0.0, 0.0, 0.0
    
    def get_market_status(self) -> Dict[str, Any]:
        """Get current market status."""
        try:
            clock = self.api.get_clock()
            
            return {
                "is_open": clock.is_open,
                "next_open": clock.next_open.isoformat() if clock.next_open else None,
                "next_close": clock.next_close.isoformat() if clock.next_close else None,
                "current_time": clock.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting market status: {e}")
            return {"is_open": False, "error": str(e)}
    
    def scan_for_gappers(self, min_gap_percent: float = 2.0, min_volume: int = 100000) -> List[Dict[str, Any]]:
        """Scan for stocks with significant gaps."""
        try:
            # Get market movers (this is a simplified approach)
            # In production, you'd want a more sophisticated scanner
            
            # For now, return cached gappers or a sample list
            cached_gappers = redis_cache.get("daily_gappers")
            if cached_gappers:
                return cached_gappers
            
            # Sample gappers for testing
            sample_gappers = [
                {"symbol": "AAPL", "gap_percent": 3.2, "current_price": 150.50, "volume": 250000},
                {"symbol": "TSLA", "gap_percent": -2.8, "current_price": 234.20, "volume": 180000},
                {"symbol": "NVDA", "gap_percent": 4.1, "current_price": 98.75, "volume": 320000}
            ]
            
            # Cache for 1 hour
            redis_cache.set("daily_gappers", sample_gappers, expiration=3600)
            
            return sample_gappers
            
        except Exception as e:
            logger.error(f"Error scanning for gappers: {e}")
            return []
    
    def calculate_vwap(self, symbol: str, date_str: str = None) -> Optional[float]:
        """Calculate VWAP for a symbol."""
        try:
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            # Check cache first
            cache_key = f"vwap:{symbol}:{date_str}"
            cached_vwap = redis_cache.get(cache_key)
            if cached_vwap:
                return cached_vwap
            
            # Get intraday bars
            start = datetime.strptime(date_str, "%Y-%m-%d")
            end = start + timedelta(days=1)
            
            bars = self.get_historical_bars(symbol, "1T", start, end)
            
            if bars.empty:
                return None
            
            # Calculate VWAP
            bars['typical_price'] = (bars['high'] + bars['low'] + bars['close']) / 3
            bars['volume_price'] = bars['typical_price'] * bars['volume']
            
            cumulative_volume_price = bars['volume_price'].cumsum()
            cumulative_volume = bars['volume'].cumsum()
            
            current_vwap = float(cumulative_volume_price.iloc[-1] / cumulative_volume.iloc[-1])
            
            # Cache for 5 minutes
            redis_cache.set(cache_key, current_vwap, expiration=300)
            
            return current_vwap
            
        except Exception as e:
            logger.error(f"Error calculating VWAP for {symbol}: {e}")
            return None
    
    def get_intraday_volume_ratio(self, symbol: str, lookback_days: int = 20) -> float:
        """
        Calculate intraday volume ratio comparing today's volume-to-date with historical average.

        This compares apples-to-apples:
        - Today's volume from market open until now
        - vs Average volume from market open to this same time over past X days

        Args:
            symbol: Stock symbol
            lookback_days: Number of historical days to average (default 20)

        Returns:
            Volume ratio (e.g., 2.5 means today's volume is 2.5x the average for this time)
        """
        try:
            import pytz
            from alpaca_trade_api.rest import TimeFrame

            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            current_time = now_eastern.time()

            # Market opens at 9:30 AM ET
            market_open_time = time(9, 30)
            market_close_time = time(16, 0)

            # Check if we're during market hours
            if current_time < market_open_time:
                logger.warning(f"{symbol}: Market not open yet, returning 0")
                return 0.0

            # Calculate how many minutes have passed since market open
            market_open_today = now_eastern.replace(hour=9, minute=30, second=0, microsecond=0)
            minutes_since_open = int((now_eastern - market_open_today).total_seconds() / 60)

            if minutes_since_open <= 0:
                logger.warning(f"{symbol}: Market just opened, returning 0")
                return 0.0

            logger.info(f"📊 {symbol}: Calculating intraday volume ratio ({minutes_since_open} min since open)")

            # Get today's 1-minute bars from market open until now
            today_bars = self.api.get_bars(
                symbol,
                TimeFrame.Minute,
                start=market_open_today.isoformat(),
                end=now_eastern.isoformat(),
                adjustment='raw'
            )

            if not today_bars or len(today_bars) == 0:
                logger.warning(f"{symbol}: No intraday bars available")
                return 0.0

            # Calculate today's cumulative volume
            today_df = today_bars.df
            today_volume = today_df['volume'].sum()

            logger.info(f"📈 {symbol}: Today's volume so far: {today_volume:,}")

            # Get historical intraday volumes for comparison
            historical_volumes = []

            # Go back lookback_days trading days
            for i in range(1, lookback_days + 10):  # +10 buffer for weekends/holidays
                historical_date = now_eastern - timedelta(days=i)

                # Skip if it's a weekend
                if historical_date.weekday() >= 5:  # Saturday=5, Sunday=6
                    continue

                # Define the same time window on this historical day
                hist_market_open = historical_date.replace(hour=9, minute=30, second=0, microsecond=0)
                hist_cutoff_time = hist_market_open + timedelta(minutes=minutes_since_open)

                try:
                    # Get bars for this historical day from open to same time
                    hist_bars = self.api.get_bars(
                        symbol,
                        TimeFrame.Minute,
                        start=hist_market_open.isoformat(),
                        end=hist_cutoff_time.isoformat(),
                        adjustment='raw'
                    )

                    if hist_bars and len(hist_bars) > 0:
                        hist_df = hist_bars.df
                        hist_volume = hist_df['volume'].sum()

                        if hist_volume > 0:
                            historical_volumes.append(hist_volume)
                            logger.debug(f"   {historical_date.date()}: {hist_volume:,}")

                    # Stop once we have enough data points
                    if len(historical_volumes) >= lookback_days:
                        break

                except Exception as e:
                    logger.debug(f"Error getting historical data for {historical_date.date()}: {e}")
                    continue

            if len(historical_volumes) == 0:
                logger.warning(f"{symbol}: No historical volume data available")
                return 0.0

            # Calculate average historical volume at this time
            avg_historical_volume = sum(historical_volumes) / len(historical_volumes)

            # Calculate ratio
            volume_ratio = today_volume / avg_historical_volume if avg_historical_volume > 0 else 0.0

            logger.info(f"✅ {symbol} INTRADAY VOLUME RATIO:")
            logger.info(f"   Today's volume (so far): {today_volume:,}")
            logger.info(f"   Avg historical volume at this time ({len(historical_volumes)} days): {avg_historical_volume:,.0f}")
            logger.info(f"   Ratio: {volume_ratio:.2f}x")

            return volume_ratio

        except Exception as e:
            logger.error(f"Error calculating intraday volume ratio for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0.0

    def health_check(self) -> bool:
        """Check if market data service is healthy."""
        try:
            # Test API connection
            clock = self.api.get_clock()
            return clock is not None

        except Exception as e:
            logger.error(f"Market data service health check failed: {e}")
            return False


# Create global market data service instance
market_data_service = MarketDataService()