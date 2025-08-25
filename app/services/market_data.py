"""
Market data service for Alpaca integration.
Handles real-time and historical market data.
"""
import asyncio
import logging
import json
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Any
from decimal import Decimal
import pandas as pd

import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
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
    
    def get_historical_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Get historical bar data."""
        try:
            # Map timeframe string to Alpaca TimeFrame
            timeframe_map = {
                "1T": TimeFrame.Minute,
                "5T": TimeFrame(5, TimeFrame.Unit.Minute),
                "15T": TimeFrame(15, TimeFrame.Unit.Minute),
                "1H": TimeFrame.Hour,
                "1D": TimeFrame.Day
            }
            
            tf = timeframe_map.get(timeframe, TimeFrame.Minute)
            
            bars = self.api.get_bars(
                symbol,
                tf,
                start=start,
                end=end,
                adjustment='raw'
            ).df
            
            return bars
            
        except Exception as e:
            logger.error(f"Error getting historical bars for {symbol}: {e}")
            return pd.DataFrame()
    
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