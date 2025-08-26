"""
Mock Enhanced Market Data Service for testing watchlist functionality.
"""
import logging
import random
from datetime import datetime, time
from typing import Dict, List, Optional, Any
import pytz

logger = logging.getLogger(__name__)


class MockEnhancedMarketDataService:
    """Mock enhanced market data service for testing purposes."""
    
    def __init__(self):
        # Mock market hours (Eastern Time)
        self.pre_market_start = time(4, 0)
        self.market_open = time(9, 30)
        self.market_close = time(16, 0)
        self.after_hours_end = time(20, 0)
        
        # Mock stock data
        self.mock_stocks = {
            "AAPL": {"base_price": 175.50, "sector": "tech"},
            "GOOGL": {"base_price": 142.30, "sector": "tech"},
            "TSLA": {"base_price": 244.90, "sector": "auto"},
            "NVDA": {"base_price": 463.20, "sector": "tech"},
            "SPY": {"base_price": 453.80, "sector": "etf"},
            "QQQ": {"base_price": 385.60, "sector": "etf"},
            "AMZN": {"base_price": 145.70, "sector": "tech"},
            "META": {"base_price": 319.40, "sector": "tech"},
            "MSFT": {"base_price": 378.90, "sector": "tech"},
            "AMD": {"base_price": 115.80, "sector": "tech"}
        }
    
    def _get_market_session(self) -> str:
        """Determine current market session."""
        try:
            est = pytz.timezone('US/Eastern')
            now_est = datetime.now(est).time()
            
            if self.pre_market_start <= now_est < self.market_open:
                return "pre_market"
            elif self.market_open <= now_est < self.market_close:
                return "regular_hours"
            elif self.market_close <= now_est < self.after_hours_end:
                return "after_hours"
            else:
                return "closed"
        except Exception:
            return "regular_hours"  # Default for testing
    
    async def get_enhanced_watchlist_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get enhanced market data for all watchlist symbols."""
        try:
            results = {}
            
            for symbol in symbols:
                if symbol not in self.mock_stocks:
                    continue
                    
                symbol_data = self._generate_mock_data(symbol)
                if symbol_data:
                    results[symbol] = symbol_data
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting enhanced watchlist data: {e}")
            return {}
    
    def _generate_mock_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Generate realistic mock data for a symbol."""
        try:
            if symbol not in self.mock_stocks:
                return None
            
            base_info = self.mock_stocks[symbol]
            base_price = base_info["base_price"]
            
            # Generate realistic price movements
            random.seed(hash(symbol + datetime.now().strftime("%Y%m%d")))  # Consistent per day
            
            # Previous close (base price with small variation)
            previous_close = base_price * (1 + (random.random() - 0.5) * 0.02)  # ±1%
            
            # Pre-market movement (-2% to +3%)
            pre_market_change = (random.random() - 0.3) * 0.05  # Bias toward gaps up
            pre_market_price = previous_close * (1 + pre_market_change)
            
            # Opening gap
            open_change = pre_market_change * 0.8 + (random.random() - 0.5) * 0.01  # Opening usually follows pre-market
            opening_price = previous_close * (1 + open_change)
            
            # Current price (intraday movement)
            intraday_change = (random.random() - 0.5) * 0.03  # ±1.5% intraday
            current_price = opening_price * (1 + intraday_change)
            
            # Volume data
            base_volume = random.randint(500000, 5000000)  # Base volume
            volume_multiplier = 0.5 + random.random() * 2.5  # 0.5x to 3x average
            current_volume = int(base_volume * volume_multiplier)
            
            # Calculate gaps
            gap_pre_market = pre_market_price - previous_close if pre_market_price else 0
            gap_pre_market_percent = (gap_pre_market / previous_close * 100) if previous_close > 0 else 0
            
            gap_open = opening_price - previous_close if opening_price else 0
            gap_open_percent = (gap_open / previous_close * 100) if previous_close > 0 else 0
            
            # Price changes
            price_change = current_price - previous_close
            price_change_percent = (price_change / previous_close * 100) if previous_close > 0 else 0
            
            # Volume ratio
            volume_ratio = volume_multiplier
            
            return {
                "symbol": symbol,
                "previous_close": round(previous_close, 2),
                "current_price": round(current_price, 2),
                "pre_market_price": round(pre_market_price, 2) if pre_market_price else None,
                "opening_price": round(opening_price, 2),
                "price_change": round(price_change, 2),
                "price_change_percent": round(price_change_percent, 2),
                "gap_pre_market": round(gap_pre_market, 2),
                "gap_pre_market_percent": round(gap_pre_market_percent, 2),
                "gap_open": round(gap_open, 2),
                "gap_open_percent": round(gap_open_percent, 2),
                "volume": current_volume,
                "avg_volume": base_volume,
                "volume_ratio": round(volume_ratio, 1),
                "market_session": self._get_market_session(),
                "last_updated": datetime.now().isoformat(),
                "display_formatting": self._get_display_formatting(
                    price_change_percent, gap_pre_market_percent, gap_open_percent, volume_ratio
                )
            }
            
        except Exception as e:
            logger.error(f"Error generating mock data for {symbol}: {e}")
            return None
    
    def _get_display_formatting(self, price_change_percent: float, gap_pre_market_percent: float,
                               gap_open_percent: float, volume_ratio: float) -> Dict[str, str]:
        """Get color coding and formatting for display."""
        formatting = {}
        
        # Price change color
        if price_change_percent > 2:
            formatting["price_color"] = "#27ae60"  # Strong green
        elif price_change_percent > 0:
            formatting["price_color"] = "#2ecc71"  # Light green
        elif price_change_percent < -2:
            formatting["price_color"] = "#e74c3c"  # Strong red
        elif price_change_percent < 0:
            formatting["price_color"] = "#ec7063"  # Light red
        else:
            formatting["price_color"] = "#95a5a6"  # Gray
        
        # Gap color (pre-market)
        if abs(gap_pre_market_percent) > 3:
            formatting["gap_color"] = "#f39c12"  # Strong orange
        elif abs(gap_pre_market_percent) > 1:
            formatting["gap_color"] = "#f7dc6f"  # Light orange
        else:
            formatting["gap_color"] = "#bdc3c7"  # Light gray
        
        # Volume color
        if volume_ratio > 2:
            formatting["volume_color"] = "#9b59b6"  # Purple (high volume)
        elif volume_ratio > 1.5:
            formatting["volume_color"] = "#8e44ad"  # Light purple
        else:
            formatting["volume_color"] = "#95a5a6"  # Gray
        
        # Background intensity based on overall activity
        activity_score = abs(price_change_percent) + abs(gap_pre_market_percent) + (volume_ratio - 1)
        if activity_score > 5:
            formatting["bg_intensity"] = "high"
        elif activity_score > 2:
            formatting["bg_intensity"] = "medium"
        else:
            formatting["bg_intensity"] = "low"
        
        return formatting
    
    async def get_watchlist_summary(self, symbols: List[str]) -> Dict[str, Any]:
        """Get summary statistics for the watchlist."""
        try:
            data = await self.get_enhanced_watchlist_data(symbols)
            
            if not data:
                return {"error": "No data available"}
            
            # Calculate summary stats
            total_symbols = len(data)
            gappers = len([s for s in data.values() if abs(s.get("gap_pre_market_percent", 0)) > 1])
            movers = len([s for s in data.values() if abs(s.get("price_change_percent", 0)) > 2])
            high_volume = len([s for s in data.values() if s.get("volume_ratio", 0) > 1.5])
            
            # Top movers
            sorted_by_change = sorted(data.values(), key=lambda x: abs(x.get("price_change_percent", 0)), reverse=True)
            top_movers = [s["symbol"] for s in sorted_by_change[:3]]
            
            # Top gappers
            sorted_by_gap = sorted(data.values(), key=lambda x: abs(x.get("gap_pre_market_percent", 0)), reverse=True)
            top_gappers = [s["symbol"] for s in sorted_by_gap[:3]]
            
            return {
                "total_symbols": total_symbols,
                "gappers": gappers,
                "movers": movers,
                "high_volume": high_volume,
                "top_movers": top_movers,
                "top_gappers": top_gappers,
                "market_session": self._get_market_session(),
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting watchlist summary: {e}")
            return {"error": str(e)}


# Create global mock enhanced market data service instance
mock_enhanced_market_data = MockEnhancedMarketDataService()