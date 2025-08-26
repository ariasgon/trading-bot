"""
Oliver Velez Core Signal Detection - Comprehensive Implementation.

This module implements the exact OV methodology from the blueprint:
- BT/TT detection with 66% thresholds
- Elephant (WRB) classification 
- NRB/NBB compression patterns
- 3-5 bar exhaustion reversals
- Lost control signals
- Context filters and scoring
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, time
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class OVCandle:
    """Represents a candle with OV-specific attributes."""
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    # Computed attributes
    range_val: float = 0.0
    body: float = 0.0
    upper_tail: float = 0.0
    lower_tail: float = 0.0
    tail_ratio_top: float = 0.0
    tail_ratio_bottom: float = 0.0
    body_ratio: float = 0.0


class OVCoreSignals:
    """Core Oliver Velez signal detection engine."""
    
    def __init__(self, config: Optional[Dict] = None):
        # OV Blueprint thresholds (configurable)
        self.tail_warning = config.get('tail_warning', 0.50) if config else 0.50
        self.tail_flip = config.get('tail_flip', 0.66) if config else 0.66
        self.nrb_multiplier = config.get('nrb_multiplier', 0.6) if config else 0.6
        self.nbb_multiplier = config.get('nbb_multiplier', 0.6) if config else 0.6
        self.elephant_multiplier_range = config.get('elephant_multiplier_range', 2.0) if config else 2.0
        
        # Time-of-day weighting periods (EST)
        self.high_probability_times = [
            time(10, 0), time(10, 30), time(11, 15), time(12, 0),
            time(13, 30), time(14, 15), time(14, 30), time(15, 0), time(15, 30)
        ]
    
    def prepare_candles(self, df: pd.DataFrame) -> List[OVCandle]:
        """Convert DataFrame to OV candles with computed attributes."""
        candles = []
        
        for _, row in df.iterrows():
            candle = OVCandle(
                open=row['open'],
                high=row['high'], 
                low=row['low'],
                close=row['close'],
                volume=int(row['volume'])
            )
            
            # Compute OV-specific attributes
            candle.range_val = candle.high - candle.low
            candle.body = abs(candle.close - candle.open)
            candle.upper_tail = candle.high - max(candle.open, candle.close)
            candle.lower_tail = min(candle.open, candle.close) - candle.low
            
            if candle.range_val > 0:
                candle.tail_ratio_top = candle.upper_tail / candle.range_val
                candle.tail_ratio_bottom = candle.lower_tail / candle.range_val
                candle.body_ratio = candle.body / candle.range_val
            
            candles.append(candle)
        
        return candles
    
    def calculate_rolling_medians(self, candles: List[OVCandle], period: int = 20) -> Dict[str, List[float]]:
        """Calculate rolling medians for NRB/NBB detection."""
        if len(candles) < period:
            return {'median_range': [], 'median_body': []}
        
        medians = {'median_range': [], 'median_body': []}
        
        for i in range(len(candles)):
            start_idx = max(0, i - period + 1)
            window_candles = candles[start_idx:i+1]
            
            ranges = [c.range_val for c in window_candles]
            bodies = [c.body for c in window_candles]
            
            medians['median_range'].append(np.median(ranges))
            medians['median_body'].append(np.median(bodies))
        
        return medians
    
    def detect_bt_tt(self, candle: OVCandle) -> Dict[str, Any]:
        """Detect Bottom Tail (BT) and Top Tail (TT) patterns."""
        is_bt = candle.tail_ratio_bottom >= self.tail_flip
        is_tt = candle.tail_ratio_top >= self.tail_flip
        
        # Additional confirmation criteria
        small_opposing_body = candle.body_ratio <= 0.3
        
        return {
            'is_bt': is_bt,
            'is_tt': is_tt,
            'bt_strength': candle.tail_ratio_bottom,
            'tt_strength': candle.tail_ratio_top,
            'small_body_confirmation': small_opposing_body,
            'pattern_quality': 'strong' if (is_bt or is_tt) and small_opposing_body else 'weak'
        }
    
    def detect_elephant(self, candles: List[OVCandle], index: int, medians: Dict[str, List[float]]) -> Dict[str, Any]:
        """Detect Elephant (Wide Range Bar) patterns."""
        if index >= len(medians['median_range']) or index < 0:
            return {'is_elephant': False}
        
        candle = candles[index]
        median_range = medians['median_range'][index]
        
        is_elephant = candle.range_val >= (self.elephant_multiplier_range * median_range)
        
        if not is_elephant:
            return {'is_elephant': False}
        
        # Classify elephant type based on position in run
        pos_in_run = self._count_consecutive_same_color(candles, index)
        
        # Direction of the elephant
        is_bullish = candle.close > candle.open
        
        # Classification logic
        if pos_in_run <= 2:
            elephant_type = 'ignition'
            interpretation = 'continuation_signal'
        else:
            elephant_type = 'exhaustion'  
            interpretation = 'reversal_warning'
        
        return {
            'is_elephant': True,
            'type': elephant_type,
            'interpretation': interpretation,
            'pos_in_run': pos_in_run,
            'is_bullish': is_bullish,
            'range_multiple': candle.range_val / median_range if median_range > 0 else 0,
            'volume_confirmation': candle.volume > 0  # Would need volume comparison
        }
    
    def detect_nrb_nbb(self, candles: List[OVCandle], index: int, medians: Dict[str, List[float]]) -> Dict[str, Any]:
        """Detect Narrow Range Bar (NRB) and Narrow Body Bar (NBB)."""
        if index >= len(medians['median_range']) or index < 0:
            return {'is_nrb': False, 'is_nbb': False}
        
        candle = candles[index]
        median_range = medians['median_range'][index] 
        median_body = medians['median_body'][index]
        
        is_nrb = candle.range_val <= (self.nrb_multiplier * median_range)
        is_nbb = candle.body <= (self.nbb_multiplier * median_body)
        
        # Context - compression after move increases breakout probability
        pos_in_run = self._count_consecutive_same_color(candles, index)
        after_move = pos_in_run >= 3
        
        return {
            'is_nrb': is_nrb,
            'is_nbb': is_nbb,
            'compression_quality': 'high' if (is_nrb and is_nbb) else 'medium' if (is_nrb or is_nbb) else 'low',
            'after_move': after_move,
            'range_compression': candle.range_val / median_range if median_range > 0 else 1,
            'body_compression': candle.body / median_body if median_body > 0 else 1,
            'breakout_probability': 'high' if (is_nrb or is_nbb) and after_move else 'medium'
        }
    
    def detect_3_5_exhaustion_reversal(self, candles: List[OVCandle], index: int) -> Dict[str, Any]:
        """Detect 3-5 bar exhaustion reversal patterns."""
        if index < 5:  # Need at least 5 bars for analysis
            return {'is_reversal': False}
        
        # Count consecutive same-color bars before current
        consecutive_count = self._count_consecutive_same_color(candles, index - 1)
        
        if consecutive_count not in [3, 4, 5]:
            return {'is_reversal': False}
        
        reversal_candle = candles[index]
        
        # Detect reversal signals on the current bar
        bt_tt = self.detect_bt_tt(reversal_candle)
        
        # Check for color flip
        prev_candle = candles[index - 1]
        color_flip = self._detect_color_flip(prev_candle, reversal_candle)
        
        # NRB after strong move
        medians = self.calculate_rolling_medians(candles[:index+1])
        nrb_nbb = self.detect_nrb_nbb(candles, index, medians)
        
        # Reversal signals
        reversal_signals = []
        if bt_tt['is_bt'] or bt_tt['is_tt']:
            reversal_signals.append('bt_tt_pattern')
        if color_flip['has_flip']:
            reversal_signals.append('color_flip')
        if nrb_nbb['is_nrb'] or nrb_nbb['is_nbb']:
            reversal_signals.append('compression')
        
        is_reversal = len(reversal_signals) > 0
        
        # Determine reversal direction
        if consecutive_count > 0 and is_reversal:
            # If we had bullish run, expect bearish reversal
            last_move_bullish = candles[index - 1].close > candles[index - 1].open
            reversal_direction = 'bearish' if last_move_bullish else 'bullish'
        else:
            reversal_direction = 'unknown'
        
        return {
            'is_reversal': is_reversal,
            'consecutive_count': consecutive_count,
            'reversal_direction': reversal_direction,
            'reversal_signals': reversal_signals,
            'signal_strength': len(reversal_signals),
            'bt_tt_data': bt_tt,
            'color_flip_data': color_flip,
            'compression_data': nrb_nbb
        }
    
    def detect_lost_control(self, candles: List[OVCandle], index: int) -> Dict[str, Any]:
        """Detect lost control / power flip signals."""
        if index < 1:
            return {'has_lost_control': False}
        
        current = candles[index]
        previous = candles[index - 1]
        
        # Calculate body erase ratio
        prev_body = previous.body
        if prev_body == 0:
            return {'has_lost_control': False}
        
        # Check if current opposite-color bar erases previous body
        prev_midpoint = (previous.open + previous.close) / 2
        
        body_erase_ratio = 0
        has_flip = False
        
        # Previous green, current red scenario
        if previous.close > previous.open and current.close < current.open:
            if current.close <= prev_midpoint:
                amount_erased = previous.close - current.close
                body_erase_ratio = amount_erased / prev_body
                has_flip = body_erase_ratio >= self.tail_warning
        
        # Previous red, current green scenario  
        elif previous.close < previous.open and current.close > current.open:
            if current.close >= prev_midpoint:
                amount_erased = current.close - previous.close
                body_erase_ratio = amount_erased / prev_body
                has_flip = body_erase_ratio >= self.tail_warning
        
        return {
            'has_lost_control': has_flip,
            'body_erase_ratio': body_erase_ratio,
            'threshold_used': self.tail_warning,
            'flip_strength': 'strong' if body_erase_ratio >= self.tail_flip else 'weak' if has_flip else 'none'
        }
    
    def _count_consecutive_same_color(self, candles: List[OVCandle], index: int) -> int:
        """Count consecutive same-colored candles before the given index."""
        if index <= 0:
            return 0
        
        reference_candle = candles[index - 1]
        reference_is_green = reference_candle.close > reference_candle.open
        
        count = 0
        for i in range(index - 1, -1, -1):
            candle = candles[i]
            candle_is_green = candle.close > candle.open
            
            if candle_is_green == reference_is_green:
                count += 1
            else:
                break
        
        return count
    
    def _detect_color_flip(self, prev_candle: OVCandle, current_candle: OVCandle) -> Dict[str, Any]:
        """Detect color flip pattern."""
        prev_is_green = prev_candle.close > prev_candle.open
        current_is_green = current_candle.close > current_candle.open
        
        has_flip = prev_is_green != current_is_green
        
        # Calculate how much of previous body was given back
        if has_flip and prev_candle.body > 0:
            if prev_is_green and not current_is_green:
                # Previous green, current red - measure giveback
                giveback = prev_candle.close - current_candle.close
                giveback_ratio = giveback / prev_candle.body
            elif not prev_is_green and current_is_green:
                # Previous red, current green - measure recovery
                giveback = current_candle.close - prev_candle.close  
                giveback_ratio = giveback / prev_candle.body
            else:
                giveback_ratio = 0
        else:
            giveback_ratio = 0
        
        return {
            'has_flip': has_flip,
            'giveback_ratio': giveback_ratio,
            'flip_strength': 'strong' if giveback_ratio >= self.tail_flip else 'medium' if giveback_ratio >= self.tail_warning else 'weak'
        }
    
    def calculate_session_weight(self, timestamp: datetime) -> float:
        """Calculate time-of-day weighting multiplier."""
        try:
            current_time = timestamp.time()
            
            # Find closest high-probability time
            min_distance = float('inf')
            for target_time in self.high_probability_times:
                # Calculate minutes difference
                current_minutes = current_time.hour * 60 + current_time.minute
                target_minutes = target_time.hour * 60 + target_time.minute
                
                distance = abs(current_minutes - target_minutes)
                min_distance = min(min_distance, distance)
            
            # Weight based on proximity (within 15 minutes gets full weight)
            if min_distance <= 15:
                return 1.5  # 50% boost
            elif min_distance <= 30:
                return 1.25  # 25% boost
            else:
                return 1.0  # No boost
                
        except Exception as e:
            logger.error(f"Error calculating session weight: {e}")
            return 1.0
    
    def analyze_comprehensive(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Comprehensive OV analysis of price data."""
        try:
            if len(df) < 50:
                return {'error': 'Insufficient data for analysis'}
            
            candles = self.prepare_candles(df)
            medians = self.calculate_rolling_medians(candles)
            
            # Analyze last few candles for signals
            results = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'total_candles': len(candles),
                'signals': []
            }
            
            # Analyze recent candles (last 10)
            for i in range(max(0, len(candles) - 10), len(candles)):
                candle_analysis = {
                    'index': i,
                    'candle': {
                        'open': candles[i].open,
                        'high': candles[i].high,
                        'low': candles[i].low,
                        'close': candles[i].close,
                        'range': candles[i].range_val,
                        'body': candles[i].body
                    }
                }
                
                # Run all signal detections
                candle_analysis['bt_tt'] = self.detect_bt_tt(candles[i])
                candle_analysis['elephant'] = self.detect_elephant(candles, i, medians)
                candle_analysis['nrb_nbb'] = self.detect_nrb_nbb(candles, i, medians)
                candle_analysis['reversal_3_5'] = self.detect_3_5_exhaustion_reversal(candles, i)
                candle_analysis['lost_control'] = self.detect_lost_control(candles, i)
                
                # Calculate composite score
                score = self._calculate_signal_score(candle_analysis)
                candle_analysis['composite_score'] = score
                
                results['signals'].append(candle_analysis)
            
            # Find strongest signals
            scored_signals = [s for s in results['signals'] if s['composite_score'] > 0]
            scored_signals.sort(key=lambda x: x['composite_score'], reverse=True)
            
            results['strongest_signals'] = scored_signals[:3]  # Top 3
            results['max_score'] = max([s['composite_score'] for s in results['signals']], default=0)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in comprehensive OV analysis: {e}")
            return {'error': str(e)}
    
    def _calculate_signal_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate composite signal strength score (0-10)."""
        score = 0
        
        # BT/TT patterns (0-3 points)
        bt_tt = analysis.get('bt_tt', {})
        if bt_tt.get('is_bt') or bt_tt.get('is_tt'):
            if bt_tt.get('pattern_quality') == 'strong':
                score += 3
            else:
                score += 1.5
        
        # Elephant patterns (0-2 points)
        elephant = analysis.get('elephant', {})
        if elephant.get('is_elephant'):
            if elephant.get('type') == 'ignition':
                score += 2  # Continuation signal
            else:
                score += 1  # Exhaustion warning
        
        # NRB/NBB compression (0-2 points)
        nrb_nbb = analysis.get('nrb_nbb', {})
        if nrb_nbb.get('breakout_probability') == 'high':
            score += 2
        elif nrb_nbb.get('is_nrb') or nrb_nbb.get('is_nbb'):
            score += 1
        
        # 3-5 reversal (0-2 points)  
        reversal = analysis.get('reversal_3_5', {})
        if reversal.get('is_reversal'):
            score += min(reversal.get('signal_strength', 0), 2)
        
        # Lost control (0-1 point)
        lost_control = analysis.get('lost_control', {})
        if lost_control.get('has_lost_control'):
            if lost_control.get('flip_strength') == 'strong':
                score += 1
            else:
                score += 0.5
        
        return min(score, 10.0)  # Cap at 10


# Example usage and testing
if __name__ == "__main__":
    # Test with sample data
    import pandas as pd
    
    # Sample OHLCV data
    data = {
        'open': [100, 101, 102, 103, 104, 105, 104, 103, 102, 101],
        'high': [101, 102, 103, 105, 106, 106, 105, 104, 103, 102],
        'low': [99, 100, 101, 102, 103, 104, 103, 102, 101, 100],
        'close': [100.5, 101.5, 102.5, 104, 105, 104.5, 103.5, 102.5, 101.5, 100.5],
        'volume': [10000, 12000, 15000, 20000, 25000, 18000, 16000, 14000, 12000, 10000]
    }
    
    df = pd.DataFrame(data)
    
    ov_signals = OVCoreSignals()
    results = ov_signals.analyze_comprehensive(df, "TEST")
    
    print(f"Analysis complete. Max score: {results.get('max_score', 0)}")
    print(f"Strongest signals: {len(results.get('strongest_signals', []))}")