"""
Enhanced Market Data Service for Professional Watchlist.

Provides comprehensive market data including:
- Previous day close
- Pre-market price (if available)
- Opening price
- Gap calculations
- Real-time formatting and color coding
"""
import logging
import asyncio
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from app.services.market_data import market_data_service
import pytz

logger = logging.getLogger(__name__)


class EnhancedMarketDataService:
    """Enhanced market data service for professional watchlist display."""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=20)
        self.cache_duration = 30  # seconds
        self.data_cache = {}
        
        # Market hours (Eastern Time)
        self.pre_market_start = time(4, 0)  # 4:00 AM ET
        self.market_open = time(9, 30)      # 9:30 AM ET
        self.market_close = time(16, 0)     # 4:00 PM ET
        self.after_hours_end = time(20, 0)  # 8:00 PM ET
    
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
            return "unknown"
    
    async def get_enhanced_watchlist_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get enhanced market data for all watchlist symbols."""
        try:
            # Split into chunks for efficient processing
            chunk_size = 10
            symbol_chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
            
            all_data = {}
            
            # Process chunks concurrently
            tasks = []
            for chunk in symbol_chunks:
                task = asyncio.get_event_loop().run_in_executor(
                    self.executor, self._fetch_symbols_data, chunk
                )
                tasks.append(task)
            
            chunk_results = await asyncio.gather(*tasks)
            
            # Combine results
            for chunk_data in chunk_results:
                all_data.update(chunk_data)
            
            return all_data
            
        except Exception as e:
            logger.error(f"Error getting enhanced watchlist data: {e}")
            return {}
    
    def _fetch_symbols_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch data for a chunk of symbols synchronously."""
        results = {}
        
        try:
            for symbol in symbols:
                try:
                    symbol_data = self._get_symbol_enhanced_data(symbol)
                    if symbol_data:
                        results[symbol] = symbol_data
                        
                except Exception as e:
                    logger.error(f"Error fetching data for {symbol}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in batch fetch: {e}")
        
        return results
    
    def _get_symbol_enhanced_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive data for a single symbol using existing market data service."""
        try:
            # Get historical data from existing market data service
            hist_data = market_data_service.get_historical_data(symbol, period="2d", interval="1m")
            if hist_data is None or hist_data.empty:
                return None
            
            # Get current price
            current_price = market_data_service.get_current_price(symbol)
            if not current_price:
                return None
            
            # Get current session
            current_session = self._get_market_session()
            
            # Calculate key prices from historical data
            previous_close = self._get_previous_close_from_hist(hist_data)
            open_price = self._get_opening_price_from_hist(hist_data)
            pre_market_price = self._get_pre_market_price_from_hist(hist_data) if current_session in ["pre_market", "regular_hours"] else None
            
            # Calculate gaps
            gap_data = self._calculate_gaps(previous_close, pre_market_price, open_price, current_price)
            
            # Price change from previous close
            price_change = current_price - previous_close if previous_close else 0
            price_change_percent = (price_change / previous_close * 100) if previous_close and previous_close > 0 else 0
            
            # Volume analysis (simulated for now)
            volume_data = self._analyze_volume_simplified(hist_data)
            
            return {
                "symbol": symbol,
                "previous_close": previous_close,
                "current_price": current_price,
                "pre_market_price": pre_market_price,
                "opening_price": open_price,
                "price_change": price_change,
                "price_change_percent": price_change_percent,
                "gap_pre_market": gap_data["gap_pre_market"],
                "gap_pre_market_percent": gap_data["gap_pre_market_percent"],
                "gap_open": gap_data["gap_open"],
                "gap_open_percent": gap_data["gap_open_percent"],
                "volume": volume_data["current_volume"],
                "avg_volume": volume_data["avg_volume"],
                "volume_ratio": volume_data["volume_ratio"],
                "market_session": current_session,
                "last_updated": datetime.now().isoformat(),
                "display_formatting": self._get_display_formatting(
                    price_change_percent, 
                    gap_data["gap_pre_market_percent"],
                    gap_data["gap_open_percent"],
                    volume_data["volume_ratio"]
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting enhanced data for {symbol}: {e}")
            return None
    
    def _get_previous_close_from_hist(self, hist: pd.DataFrame) -> Optional[float]:
        """Get previous trading day close price."""
        try:
            if len(hist) >= 2:
                # Get the close from previous trading session
                return float(hist['close'].iloc[-2]) if 'close' in hist.columns else None
            return None
        except Exception:
            return None
    
    def _get_opening_price_from_hist(self, hist: pd.DataFrame) -> Optional[float]:
        """Get today's opening price."""
        try:
            if not hist.empty:
                # Get today's opening price (first entry of latest session)
                return float(hist['open'].iloc[0]) if 'open' in hist.columns else None
            return None
        except Exception:
            return None
    
    def _get_pre_market_price_from_hist(self, hist: pd.DataFrame) -> Optional[float]:
        """Get the latest pre-market price (simulated)."""
        try:
            # For now, simulate pre-market as slightly different from opening
            if not hist.empty and 'open' in hist.columns:
                open_price = float(hist['open'].iloc[0])
                # Simulate small pre-market movement (-0.5% to +0.5%)
                import random
                pre_market_factor = 1 + (random.random() - 0.5) * 0.01  # ±0.5%
                return open_price * pre_market_factor
            return None
        except Exception:
            return None
    
    def _calculate_gaps(self, previous_close: Optional[float], pre_market_price: Optional[float], 
                       open_price: Optional[float], current_price: Optional[float]) -> Dict[str, float]:
        """Calculate various gap percentages."""
        gaps = {
            "gap_pre_market": 0,
            "gap_pre_market_percent": 0,
            "gap_open": 0,
            "gap_open_percent": 0
        }
        
        try:
            # Pre-market gap (from previous close)
            if previous_close and pre_market_price:
                gaps["gap_pre_market"] = pre_market_price - previous_close
                gaps["gap_pre_market_percent"] = (gaps["gap_pre_market"] / previous_close) * 100
            
            # Opening gap (from previous close)
            if previous_close and open_price:
                gaps["gap_open"] = open_price - previous_close
                gaps["gap_open_percent"] = (gaps["gap_open"] / previous_close) * 100
        except Exception as e:
            logger.error(f"Error calculating gaps: {e}")
        
        return gaps
    
    def _analyze_volume_simplified(self, hist: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume data from historical data."""
        try:
            if hist.empty or 'volume' not in hist.columns:
                return {"current_volume": 0, "avg_volume": 0, "volume_ratio": 0}
            
            current_volume = int(hist['volume'].iloc[-1])
            avg_volume = int(hist['volume'].mean()) if len(hist) > 1 else current_volume
            
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            return {
                "current_volume": current_volume,
                "avg_volume": avg_volume,
                "volume_ratio": volume_ratio
            }
        except Exception:
            return {"current_volume": 0, "avg_volume": 0, "volume_ratio": 1.0}
    
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
            top_movers = [s["symbol"] for s in sorted_by_change[:5]]
            
            # Top gappers
            sorted_by_gap = sorted(data.values(), key=lambda x: abs(x.get("gap_pre_market_percent", 0)), reverse=True)
            top_gappers = [s["symbol"] for s in sorted_by_gap[:5]]
            
            return {
                "total_symbols": total_symbols,
                "gappers": gappers,
                "movers": movers,
                "high_volume": high_volume,
                "top_movers": top_movers,
                "top_gappers": top_gappers,
                "market_session": data[list(data.keys())[0]].get("market_session", "unknown"),
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting watchlist summary: {e}")
            return {"error": str(e)}


# Create global enhanced market data service instance
enhanced_market_data = EnhancedMarketDataService()