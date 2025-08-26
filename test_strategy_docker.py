#!/usr/bin/env python3
"""Test strategy implementation inside Docker container."""

import pandas as pd
import numpy as np
from datetime import datetime

def main():
    print('🚀 Testing strategy implementation...')
    
    # Test technical indicators
    try:
        from app.strategies.indicators import TechnicalIndicators, VelezSignalGenerator
        print('✅ Strategy modules imported successfully')
        
        # Create test data
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        close_prices = 100 + np.cumsum(np.random.randn(100) * 0.02)
        high_prices = close_prices + np.random.uniform(0.1, 2.0, 100)  
        low_prices = close_prices - np.random.uniform(0.1, 2.0, 100)
        open_prices = close_prices + np.random.uniform(-1.0, 1.0, 100)
        volume = np.random.randint(1000000, 5000000, 100)
        
        df = pd.DataFrame({
            'open': open_prices,
            'high': high_prices, 
            'low': low_prices,
            'close': close_prices,
            'volume': volume
        }, index=dates)
        
        print('✅ Test data created')
        
        # Test VWAP calculation
        vwap = TechnicalIndicators.calculate_vwap(df)
        print(f'✅ VWAP calculation: Last value = {vwap.iloc[-1]:.2f}')
        
        # Test EMA calculation
        ema_20 = TechnicalIndicators.calculate_ema(df["close"], 20)
        print(f'✅ EMA-20 calculation: Last value = {ema_20.iloc[-1]:.2f}')
        
        # Test ATR calculation
        atr = TechnicalIndicators.calculate_atr(df)
        print(f'✅ ATR calculation: Last value = {atr.iloc[-1]:.2f}')
        
        # Test RSI calculation
        rsi = TechnicalIndicators.calculate_rsi(df["close"])
        print(f'✅ RSI calculation: Last value = {rsi.iloc[-1]:.2f}')
        
        # Test signal generator
        signal_gen = VelezSignalGenerator()
        analysis = signal_gen.analyze_stock(df, 'TEST')
        
        print(f'✅ Stock analysis completed:')
        print(f'  - Symbol: {analysis.get("symbol", "N/A")}')
        print(f'  - Signal: {analysis.get("signal", "none")}')
        print(f'  - Signal strength: {analysis.get("signal_strength", 0)}')
        print(f'  - Current price: ${analysis.get("current_price", 0):.2f}')
        print(f'  - Entry price: ${analysis.get("entry_price", 0):.2f}')
        print(f'  - Stop loss: ${analysis.get("stop_loss", 0):.2f}')
        print(f'  - Target price: ${analysis.get("target_price", 0):.2f}')
        print(f'  - Risk/Reward ratio: {analysis.get("risk_reward_ratio", 0):.2f}')
        print(f'  - VWAP level: ${analysis.get("vwap", 0):.2f}')
        print(f'  - RSI: {analysis.get("rsi", 0):.2f}')
        
        # Test volume analysis
        volume_analysis = analysis.get('volume_analysis', {})
        print(f'  - Volume ratio: {volume_analysis.get("volume_ratio", 0):.2f}')
        print(f'  - High volume: {volume_analysis.get("high_volume", False)}')
        
        # Test reversal patterns
        patterns = analysis.get('reversal_patterns', {})
        active_patterns = [k for k, v in patterns.items() if v]
        if active_patterns:
            print(f'  - Active patterns: {", ".join(active_patterns)}')
        
        print('🎉 All strategy tests passed!')
        return True
        
    except Exception as e:
        print(f'❌ Strategy test failed: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)