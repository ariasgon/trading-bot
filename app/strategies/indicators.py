"""
Technical Indicators Engine for Oliver Velez Trading Strategy.

This module provides all technical analysis functions required for implementing
the Oliver Velez pullback and reversal strategy.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Technical analysis indicators for trading strategies."""
    
    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """
        Calculate Volume Weighted Average Price (VWAP).
        
        Args:
            df: DataFrame with columns ['high', 'low', 'close', 'volume']
            
        Returns:
            Series containing VWAP values
        """
        try:
            # Calculate typical price
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            
            # Calculate cumulative volume * typical price
            cumulative_pv = (typical_price * df['volume']).cumsum()
            
            # Calculate cumulative volume
            cumulative_volume = df['volume'].cumsum()
            
            # Calculate VWAP
            vwap = cumulative_pv / cumulative_volume
            
            return vwap
            
        except Exception as e:
            logger.error(f"Error calculating VWAP: {e}")
            return pd.Series(index=df.index)
    
    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
        """
        Calculate Exponential Moving Average (EMA).
        
        Args:
            prices: Series of price values
            period: EMA period
            
        Returns:
            Series containing EMA values
        """
        try:
            return prices.ewm(span=period, adjust=False).mean()
        except Exception as e:
            logger.error(f"Error calculating EMA: {e}")
            return pd.Series(index=prices.index)
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range (ATR).
        
        Args:
            df: DataFrame with columns ['high', 'low', 'close']
            period: ATR period (default 14)
            
        Returns:
            Series containing ATR values
        """
        try:
            # Calculate True Range components
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())
            
            # True Range is the maximum of the three components
            true_range = pd.DataFrame({'hl': high_low, 'hc': high_close, 'lc': low_close}).max(axis=1)
            
            # Calculate ATR as EMA of True Range
            atr = true_range.ewm(span=period, adjust=False).mean()
            
            return atr
            
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return pd.Series(index=df.index)
    
    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI).
        
        Args:
            prices: Series of price values
            period: RSI period (default 14)
            
        Returns:
            Series containing RSI values
        """
        try:
            # Calculate price changes
            delta = prices.diff()
            
            # Separate gains and losses
            gains = delta.where(delta > 0, 0)
            losses = -delta.where(delta < 0, 0)
            
            # Calculate average gains and losses
            avg_gains = gains.ewm(span=period, adjust=False).mean()
            avg_losses = losses.ewm(span=period, adjust=False).mean()
            
            # Calculate RSI
            rs = avg_gains / avg_losses
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return pd.Series(index=prices.index)
    
    @staticmethod
    def detect_gap(df: pd.DataFrame, min_gap_percent: float = 0.5) -> pd.Series:
        """
        Detect price gaps between sessions.
        
        Args:
            df: DataFrame with columns ['open', 'close']
            min_gap_percent: Minimum gap percentage to consider significant
            
        Returns:
            Series with gap information (positive for gap up, negative for gap down)
        """
        try:
            # Calculate gap as difference between current open and previous close
            prev_close = df['close'].shift(1)
            current_open = df['open']
            
            gap_amount = current_open - prev_close
            gap_percent = (gap_amount / prev_close) * 100
            
            # Only consider significant gaps
            significant_gaps = gap_percent.where(abs(gap_percent) >= min_gap_percent, 0)
            
            return significant_gaps
            
        except Exception as e:
            logger.error(f"Error detecting gaps: {e}")
            return pd.Series(index=df.index)
    
    @staticmethod
    def identify_pullback(df: pd.DataFrame, vwap: pd.Series, ema_period: int = 20) -> Dict[str, Any]:
        """
        Identify pullback conditions for Oliver Velez strategy.
        
        Args:
            df: DataFrame with OHLCV data
            vwap: VWAP series
            ema_period: EMA period for trend identification
            
        Returns:
            Dictionary with pullback analysis
        """
        try:
            ema = TechnicalIndicators.calculate_ema(df['close'], ema_period)
            current_price = df['close'].iloc[-1]
            current_vwap = vwap.iloc[-1] if not vwap.empty else None
            current_ema = ema.iloc[-1] if not ema.empty else None
            
            # Determine trend bias
            above_vwap = current_price > current_vwap if current_vwap else False
            above_ema = current_price > current_ema if current_ema else False
            
            # Calculate recent price action
            recent_high = df['high'].tail(5).max()
            recent_low = df['low'].tail(5).min()
            
            # Pullback conditions
            pullback_from_high = (current_price < recent_high * 0.98)  # 2% pullback
            pullback_to_support = above_vwap and (current_price <= current_vwap * 1.005)  # Near VWAP
            
            pullback_analysis = {
                'is_pullback': pullback_from_high and pullback_to_support,
                'trend_bias': 'bullish' if above_vwap and above_ema else 'bearish',
                'above_vwap': above_vwap,
                'above_ema': above_ema,
                'current_price': current_price,
                'vwap_level': current_vwap,
                'ema_level': current_ema,
                'recent_high': recent_high,
                'recent_low': recent_low,
                'pullback_percent': ((recent_high - current_price) / recent_high * 100) if recent_high > 0 else 0,
                'distance_to_vwap_percent': ((current_price - current_vwap) / current_vwap * 100) if current_vwap else 0
            }
            
            return pullback_analysis
            
        except Exception as e:
            logger.error(f"Error identifying pullback: {e}")
            return {'is_pullback': False, 'error': str(e)}
    
    @staticmethod
    def detect_bullish_reversal_patterns(df: pd.DataFrame) -> Dict[str, bool]:
        """
        Detect bullish reversal candlestick patterns.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Dictionary with pattern detection results
        """
        try:
            if len(df) < 3:
                return {'hammer': False, 'doji': False, 'engulfing': False}
            
            # Get last 3 candles for pattern analysis
            recent = df.tail(3).copy()
            recent['body'] = abs(recent['close'] - recent['open'])
            recent['upper_shadow'] = recent['high'] - recent[['open', 'close']].max(axis=1)
            recent['lower_shadow'] = recent[['open', 'close']].min(axis=1) - recent['low']
            recent['range'] = recent['high'] - recent['low']
            
            current = recent.iloc[-1]
            prev = recent.iloc[-2]
            
            patterns = {}
            
            # Hammer pattern
            small_body = current['body'] < (current['range'] * 0.3)
            long_lower_shadow = current['lower_shadow'] > (current['body'] * 2)
            short_upper_shadow = current['upper_shadow'] < (current['body'] * 0.5)
            patterns['hammer'] = small_body and long_lower_shadow and short_upper_shadow
            
            # Doji pattern
            very_small_body = current['body'] < (current['range'] * 0.1)
            patterns['doji'] = very_small_body
            
            # Bullish engulfing pattern
            prev_bearish = prev['close'] < prev['open']
            current_bullish = current['close'] > current['open']
            engulfs_body = (current['open'] < prev['close'] and 
                           current['close'] > prev['open'])
            patterns['engulfing'] = prev_bearish and current_bullish and engulfs_body
            
            # Morning star pattern (3-candle)
            if len(recent) >= 3:
                first = recent.iloc[-3]
                second = recent.iloc[-2] 
                third = recent.iloc[-1]
                
                first_bearish = first['close'] < first['open']
                second_small = second['body'] < (first['body'] * 0.5)
                third_bullish = third['close'] > third['open']
                gap_down = second['high'] < first['close']
                gap_up = third['close'] > first['close']
                
                patterns['morning_star'] = (first_bearish and second_small and 
                                          third_bullish and gap_down and gap_up)
            else:
                patterns['morning_star'] = False
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error detecting reversal patterns: {e}")
            return {'hammer': False, 'doji': False, 'engulfing': False, 'morning_star': False}
    
    @staticmethod
    def calculate_support_resistance(df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
        """
        Calculate dynamic support and resistance levels.
        
        Args:
            df: DataFrame with OHLCV data
            window: Lookback window for calculation
            
        Returns:
            Dictionary with support/resistance levels
        """
        try:
            recent_data = df.tail(window)
            
            # Calculate pivot points
            highs = recent_data['high']
            lows = recent_data['low']
            closes = recent_data['close']
            
            # Find local peaks and troughs
            resistance_candidates = []
            support_candidates = []
            
            for i in range(2, len(recent_data) - 2):
                current_high = highs.iloc[i]
                current_low = lows.iloc[i]
                
                # Check if current high is a local maximum
                if (current_high > highs.iloc[i-1] and current_high > highs.iloc[i-2] and
                    current_high > highs.iloc[i+1] and current_high > highs.iloc[i+2]):
                    resistance_candidates.append(current_high)
                
                # Check if current low is a local minimum
                if (current_low < lows.iloc[i-1] and current_low < lows.iloc[i-2] and
                    current_low < lows.iloc[i+1] and current_low < lows.iloc[i+2]):
                    support_candidates.append(current_low)
            
            # Calculate levels
            current_price = closes.iloc[-1]
            
            # Resistance: lowest high above current price
            resistance_levels = [r for r in resistance_candidates if r > current_price]
            resistance = min(resistance_levels) if resistance_levels else highs.max()
            
            # Support: highest low below current price  
            support_levels = [s for s in support_candidates if s < current_price]
            support = max(support_levels) if support_levels else lows.min()
            
            # Alternative calculations if no clear levels found
            if not resistance_levels:
                resistance = recent_data['high'].quantile(0.9)
            if not support_levels:
                support = recent_data['low'].quantile(0.1)
            
            return {
                'resistance': resistance,
                'support': support,
                'current_price': current_price,
                'resistance_distance': ((resistance - current_price) / current_price * 100),
                'support_distance': ((current_price - support) / current_price * 100)
            }
            
        except Exception as e:
            logger.error(f"Error calculating support/resistance: {e}")
            return {'resistance': 0, 'support': 0, 'current_price': 0}
    
    @staticmethod
    def analyze_volume_profile(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
        """
        Analyze volume profile for the given period.
        
        Args:
            df: DataFrame with OHLCV data
            period: Analysis period
            
        Returns:
            Dictionary with volume analysis
        """
        try:
            recent_data = df.tail(period)
            
            # Calculate volume metrics
            avg_volume = recent_data['volume'].mean()
            current_volume = recent_data['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            # Volume trend
            volume_ema = TechnicalIndicators.calculate_ema(recent_data['volume'], 10)
            volume_trend = 'increasing' if volume_ema.iloc[-1] > volume_ema.iloc[-2] else 'decreasing'
            
            # High volume threshold (above 1.5x average)
            high_volume = current_volume > (avg_volume * 1.5)
            
            # Price-volume relationship
            price_change = (recent_data['close'].iloc[-1] - recent_data['close'].iloc[-2]) / recent_data['close'].iloc[-2]
            volume_change = (current_volume - recent_data['volume'].iloc[-2]) / recent_data['volume'].iloc[-2]
            
            # Volume confirmation
            volume_confirms_move = (price_change > 0 and volume_change > 0) or (price_change < 0 and volume_change > 0)
            
            return {
                'current_volume': int(current_volume),
                'average_volume': int(avg_volume),
                'volume_ratio': volume_ratio,
                'volume_trend': volume_trend,
                'high_volume': high_volume,
                'volume_confirms_move': volume_confirms_move,
                'relative_volume_strength': min(volume_ratio, 5.0)  # Cap at 5x for display
            }
            
        except Exception as e:
            logger.error(f"Error analyzing volume profile: {e}")
            return {'current_volume': 0, 'average_volume': 0, 'volume_ratio': 0}
    
    @staticmethod
    def calculate_momentum_indicators(df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate momentum indicators for trend strength analysis.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Dictionary with momentum indicators
        """
        try:
            closes = df['close']
            
            # Rate of Change (ROC) - 10 period
            roc_10 = ((closes - closes.shift(10)) / closes.shift(10) * 100).iloc[-1]
            
            # Price momentum - 5 period
            momentum_5 = (closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6] * 100 if len(closes) > 5 else 0
            
            # Acceleration (change in momentum)
            if len(closes) > 10:
                prev_momentum = (closes.iloc[-6] - closes.iloc[-11]) / closes.iloc[-11] * 100
                acceleration = momentum_5 - prev_momentum
            else:
                acceleration = 0
            
            return {
                'roc_10_period': roc_10 if not pd.isna(roc_10) else 0,
                'momentum_5_period': momentum_5,
                'price_acceleration': acceleration,
                'momentum_strength': abs(momentum_5)  # Absolute momentum strength
            }
            
        except Exception as e:
            logger.error(f"Error calculating momentum indicators: {e}")
            return {'roc_10_period': 0, 'momentum_5_period': 0, 'price_acceleration': 0}


class VelezSignalGenerator:
    """Generate trading signals based on Oliver Velez methodology."""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
    
    def analyze_stock(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        Comprehensive analysis of a stock for Velez strategy signals.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Stock symbol
            
        Returns:
            Dictionary with complete analysis
        """
        try:
            if df.empty or len(df) < 50:
                return {'symbol': symbol, 'error': 'Insufficient data'}
            
            # Calculate core indicators
            vwap = self.indicators.calculate_vwap(df)
            ema_20 = self.indicators.calculate_ema(df['close'], 20)
            ema_50 = self.indicators.calculate_ema(df['close'], 50)
            atr = self.indicators.calculate_atr(df)
            rsi = self.indicators.calculate_rsi(df['close'])
            
            # Detect patterns and conditions
            gaps = self.indicators.detect_gap(df)
            pullback = self.indicators.identify_pullback(df, vwap)
            reversal_patterns = self.indicators.detect_bullish_reversal_patterns(df)
            support_resistance = self.indicators.calculate_support_resistance(df)
            volume_analysis = self.indicators.analyze_volume_profile(df)
            momentum = self.indicators.calculate_momentum_indicators(df)
            
            # Current values
            current_price = df['close'].iloc[-1]
            current_vwap = vwap.iloc[-1] if not vwap.empty else 0
            current_atr = atr.iloc[-1] if not atr.empty else 0
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50
            current_gap = gaps.iloc[-1] if not gaps.empty else 0
            
            # Trading signal generation
            signal_strength = 0
            signal_reasons = []
            
            # Check for gap and pullback entry
            if current_gap > 0.5:  # Gap up
                signal_strength += 2
                signal_reasons.append('Gap up detected')
                
                if pullback.get('is_pullback'):
                    signal_strength += 3
                    signal_reasons.append('Pullback to VWAP/support')
            
            # Check for reversal patterns
            if any(reversal_patterns.values()):
                signal_strength += 2
                active_patterns = [k for k, v in reversal_patterns.items() if v]
                signal_reasons.append(f'Bullish pattern: {", ".join(active_patterns)}')
            
            # Check volume confirmation
            if volume_analysis.get('volume_confirms_move') and volume_analysis.get('high_volume'):
                signal_strength += 2
                signal_reasons.append('High volume confirmation')
            
            # RSI oversold bounce
            if 25 <= current_rsi <= 35:
                signal_strength += 1
                signal_reasons.append('RSI oversold bounce setup')
            
            # Trend alignment
            if pullback.get('trend_bias') == 'bullish':
                signal_strength += 1
                signal_reasons.append('Bullish trend bias')
            
            # Generate entry signal
            signal_type = 'none'
            if signal_strength >= 5:
                signal_type = 'strong_buy'
            elif signal_strength >= 3:
                signal_type = 'buy'
            elif signal_strength >= 1:
                signal_type = 'weak_buy'
            
            # Calculate entry levels
            entry_price = current_price
            stop_loss = max(
                support_resistance.get('support', current_price * 0.98),
                current_price - (current_atr * 2),
                current_price * 0.97  # Maximum 3% stop
            )
            
            # Target based on risk-reward (minimum 2:1)
            risk_amount = entry_price - stop_loss
            target_price = entry_price + (risk_amount * 2)
            
            # Compile final analysis
            analysis = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'current_price': current_price,
                'signal': signal_type,
                'signal_strength': signal_strength,
                'signal_reasons': signal_reasons,
                
                # Entry levels
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'target_price': target_price,
                'risk_reward_ratio': (target_price - entry_price) / (entry_price - stop_loss) if entry_price > stop_loss else 0,
                
                # Technical levels
                'vwap': current_vwap,
                'support': support_resistance.get('support'),
                'resistance': support_resistance.get('resistance'),
                'atr': current_atr,
                'rsi': current_rsi,
                
                # Pattern analysis
                'gap_percent': current_gap,
                'pullback_analysis': pullback,
                'reversal_patterns': reversal_patterns,
                'volume_analysis': volume_analysis,
                'momentum_indicators': momentum,
                
                # Trend information
                'ema_20': ema_20.iloc[-1] if not ema_20.empty else 0,
                'ema_50': ema_50.iloc[-1] if not ema_50.empty else 0,
                'trend_alignment': pullback.get('trend_bias', 'neutral')
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing stock {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'signal': 'none',
                'timestamp': datetime.now().isoformat()
            }
    
    def scan_watchlist(self, watchlist: List[str], market_data_func) -> List[Dict[str, Any]]:
        """
        Scan watchlist for trading opportunities.
        
        Args:
            watchlist: List of stock symbols
            market_data_func: Function to retrieve market data for symbols
            
        Returns:
            List of analysis results sorted by signal strength
        """
        results = []
        
        for symbol in watchlist:
            try:
                # Get market data
                df = market_data_func(symbol)
                if df is not None and not df.empty:
                    analysis = self.analyze_stock(df, symbol)
                    results.append(analysis)
                else:
                    logger.warning(f"No data available for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
                continue
        
        # Sort by signal strength
        results.sort(key=lambda x: x.get('signal_strength', 0), reverse=True)
        
        return results