"""
Dynamic Market Scanner for Gap and Volume Analysis

Scans S&P 500 and NASDAQ for:
- Biggest gappers (>2% premarket gaps)
- Highest volume stocks
- Best Velez trading setups
"""
import asyncio
import logging
from datetime import datetime, time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import pandas as pd

from app.core.cache import redis_cache
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


@dataclass
class GapStock:
    """Represents a stock with significant gap."""
    symbol: str
    previous_close: float
    premarket_price: float
    current_price: float
    gap_percent: float
    premarket_gap_percent: float
    volume: int
    volume_ratio: float
    score: float  # Combined gap + volume score


class MarketScanner:
    """Dynamic market scanner for gap and volume analysis."""
    
    def __init__(self):
        self.sp500_symbols = self._get_sp500_symbols()
        self.nasdaq100_symbols = self._get_nasdaq100_symbols()
        self.scan_universe = list(set(self.sp500_symbols + self.nasdaq100_symbols))
        
        # Scanner parameters
        self.min_gap_threshold = 1.0  # 1.0% minimum gap (reduced from 1.5%)
        self.min_volume_ratio = 1.2   # 1.2x average volume
        self.min_price = 5.0          # $5 minimum price
        self.max_price = 1000.0       # $1000 maximum price
        self.top_stocks_count = 30    # Return top 30 gappers (expanded from 20)
        
        logger.info(f"Market scanner initialized with {len(self.scan_universe)} symbols")

    def calculate_and_cache_volume_baselines(self, symbols: List[str]) -> None:
        """
        Calculate BOTH 5-day and 30-day average volume baselines for symbols.
        This is called once per day during scanner initialization.

        Uses daily bars we already fetch for gap analysis - zero extra API overhead!

        Research shows gap trading uses 2x the 5-day average as the standard,
        while 30-day provides more stable comparison. We use BOTH for best results.
        """
        try:
            logger.info(f"📊 Calculating 5-day and 30-day volume baselines for {len(symbols)} symbols...")
            cached_count = 0
            calculated_count = 0

            for symbol in symbols:
                try:
                    # Check if already cached (expires at end of day)
                    cache_key_30d = f"avg_daily_volume_30d:{symbol}"
                    cache_key_5d = f"avg_daily_volume_5d:{symbol}"

                    cached_30d = redis_cache.get(cache_key_30d)
                    cached_5d = redis_cache.get(cache_key_5d)

                    if cached_30d and cached_5d:
                        cached_count += 1
                        continue

                    # Get 30-day daily bars to calculate both averages
                    daily_bars = market_data_service.get_bars(symbol, timeframe='1Day', limit=30)

                    if daily_bars is None or len(daily_bars) < 5:
                        continue

                    # Calculate 30-day average (more stable)
                    avg_daily_volume_30d = daily_bars['volume'].mean()

                    # Calculate 5-day average (gap trading standard - more responsive)
                    avg_daily_volume_5d = daily_bars['volume'].tail(5).mean()

                    if avg_daily_volume_30d > 0 and avg_daily_volume_5d > 0:
                        # Cache both until end of trading day (expires at 4 PM ET)
                        redis_cache.set(cache_key_30d, float(avg_daily_volume_30d), expiration=28800)  # 8 hours
                        redis_cache.set(cache_key_5d, float(avg_daily_volume_5d), expiration=28800)  # 8 hours
                        calculated_count += 1

                except Exception as e:
                    logger.debug(f"Error calculating volume baseline for {symbol}: {e}")
                    continue

            logger.info(f"✅ Volume baselines ready: {calculated_count} calculated (both 5d & 30d), {cached_count} cached")

        except Exception as e:
            logger.error(f"Error calculating volume baselines: {e}")

    def _get_sp500_symbols(self) -> List[str]:
        """Get full S&P 500 symbols for comprehensive market scanning."""
        # Complete S&P 500 list (as of late 2024) - 503 symbols (includes share classes)
        return [
            # Technology
            "AAPL", "MSFT", "GOOGL", "GOOG", "META", "NVDA", "AVGO", "ORCL", "CSCO", "CRM",
            "ACN", "ADBE", "AMD", "TXN", "INTC", "QCOM", "IBM", "AMAT", "NOW", "INTU",
            "ADI", "LRCX", "MU", "KLAC", "SNPS", "CDNS", "MCHP", "APH", "MSI", "TEL",
            "FTNT", "HPQ", "HPE", "KEYS", "GLW", "ANSS", "MPWR", "NXPI", "ON", "SWKS",
            "ENPH", "FSLR", "TER", "AKAM", "CTSH", "IT", "WDC", "STX", "NTAP", "JNPR",
            "ZBRA", "CDW", "EPAM", "PAYC", "FFIV", "JKHY", "TYL", "PTC", "VRSN", "GEN",

            # Healthcare
            "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "AMGN",
            "BMY", "ISRG", "MDT", "GILD", "CVS", "ELV", "VRTX", "SYK", "CI", "REGN",
            "BSX", "ZTS", "BDX", "HCA", "MCK", "EW", "HUM", "IDXX", "IQV", "DXCM",
            "MRNA", "ILMN", "A", "MTD", "ALGN", "RMD", "PODD", "HOLX", "WST", "BAX",
            "BIIB", "ZBH", "CAH", "TECH", "RVTY", "VTRS", "LH", "MOH", "CNC", "DGX",
            "TFX", "STE", "PKI", "HSIC", "XRAY", "OGN", "DVA", "INCY", "CRL", "BIO",

            # Financials
            "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "C",
            "BLK", "AXP", "SCHW", "CB", "PGR", "MMC", "ICE", "CME", "AON", "USB",
            "PNC", "TFC", "MET", "AIG", "MCO", "AFL", "TRV", "PRU", "AMP", "ALL",
            "MSCI", "HIG", "CINF", "RJF", "TROW", "NDAQ", "STT", "BK", "MTB", "DFS",
            "FITB", "CFG", "HBAN", "NTRS", "KEY", "RF", "FRC", "SIVB", "CMA", "ZION",
            "CBOE", "FDS", "MKTX", "IVZ", "BEN", "WLTW", "L", "GL", "AIZ", "LNC",

            # Consumer Discretionary
            "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG",
            "TGT", "ORLY", "ROST", "MAR", "AZO", "DHI", "YUM", "HLT", "GM", "F",
            "LULU", "EBAY", "GRMN", "DRI", "ULTA", "POOL", "LVS", "WYNN", "MGM", "CZR",
            "LEN", "PHM", "NVR", "TOL", "KMX", "BBY", "TSCO", "DPZ", "DECK", "GPC",
            "APTV", "BWA", "LEG", "EXPE", "CCL", "RCL", "NCLH", "HAS", "ETSY", "W",

            # Consumer Staples
            "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "MDLZ", "CL", "EL",
            "GIS", "KMB", "SYY", "KHC", "STZ", "HSY", "ADM", "MKC", "KR", "WBA",
            "TSN", "HRL", "CAG", "K", "CLX", "SJM", "CHD", "BF.B", "TAP", "CPB",

            # Industrials
            "UPS", "HON", "UNP", "BA", "CAT", "RTX", "DE", "LMT", "GE", "MMM",
            "NOC", "GD", "CSX", "ITW", "NSC", "EMR", "ETN", "PH", "PCAR", "TT",
            "WM", "RSG", "FAST", "CMI", "AME", "ROK", "ODFL", "URI", "DOV", "VRSK",
            "CPRT", "IR", "GWW", "XYL", "SNA", "PWR", "J", "WAB", "FTV", "NDSN",
            "ROP", "IEX", "CHRW", "EXPD", "JBHT", "LSTR", "GNRC", "TDG", "HWM", "LHX",

            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "PXD",
            "WMB", "HES", "DVN", "KMI", "HAL", "BKR", "FANG", "CTRA", "MRO", "OKE",
            "APA", "TRGP", "EQT", "MTDR",

            # Utilities
            "NEE", "DUK", "SO", "D", "SRE", "AEP", "EXC", "XEL", "ED", "WEC",
            "PCG", "ES", "AWK", "EIX", "DTE", "PEG", "PPL", "FE", "AEE", "CMS",
            "EVRG", "ETR", "ATO", "NI", "CNP", "LNT", "NRG", "PNW", "AES", "CEG",

            # Real Estate
            "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "WELL", "SPG", "DLR", "VICI",
            "AVB", "CBRE", "EQR", "MAA", "ARE", "WY", "VTR", "ESS", "SBAC", "INVH",
            "EXR", "UDR", "HST", "KIM", "REG", "CPT", "BXP", "PEAK", "FRT", "IRM",

            # Materials
            "LIN", "APD", "SHW", "ECL", "FCX", "NUE", "NEM", "DOW", "DD", "PPG",
            "VMC", "MLM", "CTVA", "ALB", "CE", "EMN", "FMC", "LYB", "PKG", "IFF",
            "BALL", "AVY", "AMCR", "SEE", "WRK", "CF", "MOS", "IP",

            # Communication Services
            "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS", "CHTR", "WBD", "PARA", "FOX",
            "FOXA", "OMC", "IPG", "MTCH", "LYV", "EA", "TTWO", "ATVI", "NWSA", "NWS",

            # Popular ETFs and Leveraged Products
            "SPY", "QQQ", "IWM", "VTI", "DIA", "ARKK", "ARKF", "ARKG", "ARKQ", "ARKW",
            "SOXL", "TQQQ", "SPXL", "SOXS", "SQQQ", "SPXS", "UVXY", "VXX", "LABU", "LABD",
            "TLT", "GLD", "SLV", "USO", "XLE", "XLF", "XLK", "XLV", "XLI", "XLC",

            # Popular Non-S&P 500 Growth Stocks (commonly traded)
            "COIN", "RBLX", "HOOD", "SOFI", "RIVN", "LCID", "PLTR", "SNOW", "DDOG", "NET",
            "CRWD", "ZS", "MDB", "OKTA", "ESTC", "DOCU", "ZM", "U", "DASH", "ABNB",
            "SHOP", "SQ", "ROKU", "SNAP", "PINS", "TWLO", "BILL", "HUBS", "VEEV", "TEAM",
            "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "BNTX", "SE", "GRAB",
            "MARA", "RIOT", "CLSK", "HUT", "BITF", "UPWK", "FVRR",
        ]
    
    def _get_nasdaq100_symbols(self) -> List[str]:
        """Get NASDAQ 100 symbols (top growth stocks)."""
        return [
            "GOOGL", "GOOG", "AMZN", "TSLA", "META", "NVDA", "NFLX", "AMD", "PYPL", "INTC",
            "CMCSA", "ADBE", "CSCO", "PEP", "COST", "TMUS", "AVGO", "TXN", "QCOM", "CHTR",
            "SBUX", "INTU", "ISRG", "GILD", "BKNG", "REGN", "MDLZ", "VRTX", "ADP", "FISV",
            "CSX", "ATVI", "ILMN", "MU", "AMAT", "BIIB", "KHC", "LRCX", "EA", "WBA",
            "ADI", "MELI", "KLAC", "JD", "NTES", "LULU", "DXCM", "CTAS", "SNPS", "CDNS",
            "MAR", "ORLY", "PCAR", "MNST", "WDAY", "IDXX", "NXPI", "PAYX", "FAST", "VRSK",
            "CTSH", "ANSS", "CHKP", "CERN", "MCHP", "SWKS", "BMRN", "INCY", "ALGN", "TTWO",
            "SGEN", "DOCU", "ZM", "PTON", "MRNA", "BNTX", "ZS", "CRWD", "DDOG", "NET",
            "OKTA", "MDB", "ESTC", "SPLK", "TEAM", "PD", "WORK", "FVRR", "UPWK", "SHOP"
        ]
    
    async def scan_for_gappers(self) -> List[GapStock]:
        """
        Scan the market for biggest gappers with high volume.

        Returns:
            List of GapStock objects sorted by combined gap+volume score
        """
        logger.info(f"🔍 Starting market scan of {len(self.scan_universe)} symbols...")

        # Calculate volume baselines for all symbols (uses cached data after first run)
        self.calculate_and_cache_volume_baselines(self.scan_universe)

        # Check cache first
        cached_results = redis_cache.get("market_scan_results")
        if cached_results and len(cached_results) > 0:
            logger.info(f"📊 Using cached scan results: {len(cached_results)} gappers")
            return [GapStock(**stock) for stock in cached_results]
        
        gappers = []
        scan_count = 0
        error_count = 0
        
        # Scan in batches to avoid API rate limits
        batch_size = 10
        for i in range(0, len(self.scan_universe), batch_size):
            batch = self.scan_universe[i:i+batch_size]
            batch_results = await self._scan_batch(batch)
            gappers.extend(batch_results)
            scan_count += len(batch)
            
            # Brief pause between batches
            await asyncio.sleep(0.1)
            
            if scan_count % 50 == 0:
                logger.info(f"📊 Scanned {scan_count}/{len(self.scan_universe)} symbols, found {len(gappers)} gappers")
        
        # Sort by combined score (gap percentage + volume ratio)
        gappers.sort(key=lambda x: x.score, reverse=True)
        
        # Take top stocks
        top_gappers = gappers[:self.top_stocks_count]
        
        # Cache results for 5 minutes - BUT ONLY IF WE FOUND GAPPERS
        # This prevents caching empty results that would block future scans
        if top_gappers and len(top_gappers) > 0:
            cache_data = [
                {
                    'symbol': g.symbol,
                    'previous_close': g.previous_close,
                    'premarket_price': g.premarket_price,
                    'current_price': g.current_price,
                    'gap_percent': g.gap_percent,
                    'premarket_gap_percent': g.premarket_gap_percent,
                    'volume': g.volume,
                    'volume_ratio': g.volume_ratio,
                    'score': g.score
                }
                for g in top_gappers
            ]
            redis_cache.set("market_scan_results", cache_data, expiration=300)  # 5 minutes
            logger.info(f"✅ Market scan complete: Found {len(top_gappers)} top gappers from {scan_count} symbols (cached)")
        else:
            # Don't cache empty results - just log and return empty list
            logger.warning(f"⚠️ Market scan found 0 gappers from {scan_count} symbols (not caching empty result)")

        return top_gappers
    
    async def _scan_batch(self, symbols: List[str]) -> List[GapStock]:
        """Scan a batch of symbols for gaps and volume."""
        batch_gappers = []
        
        for symbol in symbols:
            try:
                quote_data = market_data_service.get_quote(symbol)
                if not quote_data:
                    continue
                
                # Extract data
                current_price = quote_data.get('price', 0)
                previous_close = quote_data.get('previous_close', 0)
                premarket_price = quote_data.get('premarket_price', 0)
                volume = quote_data.get('volume', 0)
                gap_percent = quote_data.get('gap_percent', 0)
                premarket_gap_percent = quote_data.get('premarket_gap_percent', 0)
                
                # Filter criteria
                if not self._meets_criteria(current_price, gap_percent, premarket_gap_percent, volume):
                    continue

                # Calculate cumulative volume ratio using BOTH baselines (hybrid approach)
                # Research shows: gap trading uses 2x the 5-day average standard
                avg_daily_volume_30d = redis_cache.get(f"avg_daily_volume_30d:{symbol}")
                avg_daily_volume_5d = redis_cache.get(f"avg_daily_volume_5d:{symbol}")

                if avg_daily_volume_30d and avg_daily_volume_30d > 0:
                    volume_ratio_30d = volume / avg_daily_volume_30d
                else:
                    volume_ratio_30d = 0

                if avg_daily_volume_5d and avg_daily_volume_5d > 0:
                    volume_ratio_5d = volume / avg_daily_volume_5d
                else:
                    volume_ratio_5d = 0

                # Use MORE PERMISSIVE of the two (honors both standards)
                volume_ratio = max(volume_ratio_30d, volume_ratio_5d, 1.0)
                
                # Calculate combined score
                score = self._calculate_score(gap_percent, premarket_gap_percent, volume_ratio)
                
                gapper = GapStock(
                    symbol=symbol,
                    previous_close=previous_close,
                    premarket_price=premarket_price,
                    current_price=current_price,
                    gap_percent=gap_percent,
                    premarket_gap_percent=premarket_gap_percent,
                    volume=volume,
                    volume_ratio=volume_ratio,
                    score=score
                )
                
                batch_gappers.append(gapper)
                
            except Exception as e:
                logger.warning(f"Error scanning {symbol}: {e}")
                continue
        
        return batch_gappers
    
    def _meets_criteria(self, price: float, gap_percent: float, 
                       premarket_gap_percent: float, volume: int) -> bool:
        """Check if stock meets gap and volume criteria."""
        # Price range check
        if not (self.min_price <= price <= self.max_price):
            return False
        
        # Gap threshold check (either regular gap or premarket gap)
        has_significant_gap = (
            abs(gap_percent) >= self.min_gap_threshold or 
            abs(premarket_gap_percent) >= self.min_gap_threshold
        )
        
        if not has_significant_gap:
            return False
        
        # Volume check (basic - would be more sophisticated with historical averages)
        if volume < 100000:  # Minimum 100k volume
            return False
        
        return True
    
    def _calculate_score(self, gap_percent: float, premarket_gap_percent: float, 
                        volume_ratio: float) -> float:
        """Calculate combined score for ranking stocks."""
        # Use the highest gap (either regular or premarket)
        max_gap = max(abs(gap_percent), abs(premarket_gap_percent))
        
        # Weighted score: 70% gap, 30% volume
        gap_score = max_gap * 0.7
        volume_score = (volume_ratio - 1.0) * 30 * 0.3  # Scale volume ratio contribution
        
        return gap_score + volume_score
    
    def get_scan_universe_size(self) -> int:
        """Get the total number of symbols being scanned."""
        return len(self.scan_universe)
    
    async def force_refresh_scan(self) -> List[GapStock]:
        """Force refresh the market scan (ignore cache)."""
        redis_cache.delete("market_scan_results")
        return await self.scan_for_gappers()

    def scan_for_daily_candidates_backtest(
        self,
        historical_data: Dict[str, pd.DataFrame],
        scan_date: datetime
    ) -> List[str]:
        """
        Scan for trading candidates on a specific historical date (for backtesting).

        This simulates the daily market scan that would have happened on that date.

        Args:
            historical_data: Dict of symbol -> DataFrame with historical data
            scan_date: The date to perform the scan

        Returns:
            List of stock symbols that meet criteria for that day
        """
        candidates = []
        debug_count = 0
        no_data_count = 0
        filtered_count = 0

        logger.info(f"📊 Backtest scan for {scan_date.date()}: analyzing {len(self.scan_universe)} stocks")

        for symbol in self.scan_universe:
            # Get historical data for this symbol
            symbol_data = historical_data.get(symbol)
            if symbol_data is None or symbol_data.empty:
                no_data_count += 1
                continue

            # Analyze if this stock had a gap on scan_date
            gap_info = self._analyze_historical_gap(symbol, symbol_data, scan_date)

            if gap_info:
                candidates.append(gap_info)
            else:
                filtered_count += 1

            # Show detailed debug for first 3 stocks
            debug_count += 1
            if debug_count <= 3:
                logger.info(f"   DEBUG {symbol}: data_len={len(symbol_data)}, gap_info={'FOUND' if gap_info else 'NONE'}")

        # Log summary
        logger.info(f"   SUMMARY: {no_data_count} no data, {filtered_count} filtered, {len(candidates)} passed")

        # Sort by gap score
        candidates.sort(key=lambda x: x['gap_score'], reverse=True)

        # Return top 10 symbols
        top_symbols = [c['symbol'] for c in candidates[:10]]

        if top_symbols:
            logger.info(f"✅ Backtest scan found {len(candidates)} gappers, selected top {len(top_symbols)}")
            for i, c in enumerate(candidates[:10], 1):
                logger.info(f"   {i}. {c['symbol']}: Gap {c['gap_percent']:.2f}%, Vol {c['volume_ratio']:.2f}x, Score {c['gap_score']:.1f}")
        else:
            logger.info(f"⚠️ Backtest scan found 0 candidates with gap ≥{self.min_gap_threshold}%")

        return top_symbols

    def _analyze_historical_gap(
        self,
        symbol: str,
        data: pd.DataFrame,
        scan_date: datetime
    ) -> Optional[Dict[str, any]]:
        """Analyze if a stock had a significant gap on a specific date."""
        try:
            # Only log for first 3 symbols to avoid spam
            if symbol in ['CHTR', 'C', 'MDT']:
                logger.info(f"{symbol}: ANALYZING - data shape: {data.shape}, scan_date: {scan_date}")

            # Find data around market open on scan_date
            # Market opens at 9:30 AM Eastern = 13:30 UTC (or 14:30 UTC during DST)
            scan_time = scan_date.replace(hour=9, minute=30, second=0, microsecond=0)

            # Make scan_time timezone-aware if data index is timezone-aware
            if hasattr(data.index, 'tz') and data.index.tz is not None:
                import pytz
                eastern = pytz.timezone('US/Eastern')
                # First localize to Eastern time, then convert to UTC to match data
                scan_time = eastern.localize(scan_time).astimezone(pytz.UTC)

            # Get data up to scan time
            data_up_to_scan = data[data.index <= scan_time]

            if data_up_to_scan.empty or len(data_up_to_scan) < 2:
                logger.info(f"{symbol}: SKIP - Not enough data (len={len(data_up_to_scan)})")
                return None

            # Get current price (at market open)
            current_bar = data_up_to_scan.iloc[-1]
            current_price = current_bar['close']

            # Price filter
            if current_price < self.min_price or current_price > self.max_price:
                logger.info(f"{symbol}: SKIP - Price ${current_price:.2f} outside range (${self.min_price}-${self.max_price})")
                return None

            # Get previous day close - find the last bar from the previous trading day
            scan_date_only = scan_date.date()

            # Convert index to date and filter for bars before scan_date
            data_with_dates = data_up_to_scan.copy()
            data_with_dates['date'] = pd.to_datetime(data_with_dates.index).date

            # Get data from previous trading day (before scan_date)
            previous_day_data = data_with_dates[data_with_dates['date'] < scan_date_only]

            if previous_day_data.empty:
                logger.info(f"{symbol}: SKIP - No previous day data for {scan_date_only}")
                return None

            # Get the last close from the previous trading day
            prev_close = previous_day_data.iloc[-1]['close']

            # Calculate gap
            gap_percent = ((current_price - prev_close) / prev_close) * 100

            logger.info(f"{symbol}: Prev=${prev_close:.2f}, Curr=${current_price:.2f}, Gap={gap_percent:.2f}%")

            # Filter by gap threshold
            if abs(gap_percent) < self.min_gap_threshold:
                logger.info(f"{symbol}: SKIP - Gap {gap_percent:.2f}% < threshold {self.min_gap_threshold}%")
                return None

            # LONG ONLY: Skip gap-down stocks
            if gap_percent < 0:
                logger.info(f"{symbol}: SKIP - Gap-down {gap_percent:.2f}% (long-only strategy)")
                return None

            # Volume analysis
            current_volume = current_bar.get('volume', 0)
            avg_volume = data_up_to_scan['volume'].tail(20).mean() if 'volume' in data.columns else 0
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # Calculate score
            gap_score = self._calculate_score(gap_percent, 0, volume_ratio)

            return {
                'symbol': symbol,
                'gap_percent': gap_percent,
                'current_price': current_price,
                'prev_close': prev_close,
                'volume': current_volume,
                'volume_ratio': volume_ratio,
                'gap_score': gap_score
            }

        except Exception as e:
            logger.info(f"{symbol}: ERROR - {e}")
            import traceback
            logger.info(f"{symbol}: TRACEBACK - {traceback.format_exc()}")
            return None


# Global scanner instance
market_scanner = MarketScanner()