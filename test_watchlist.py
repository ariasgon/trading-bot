#!/usr/bin/env python3
"""
Test script for enhanced watchlist functionality.
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.mock_enhanced_market_data import mock_enhanced_market_data

async def test_enhanced_watchlist():
    """Test the enhanced watchlist functionality."""
    print("Testing Enhanced Watchlist Functionality")
    print("=" * 50)
    
    # Test symbols
    test_symbols = ["AAPL", "GOOGL", "TSLA", "NVDA", "SPY"]
    
    try:
        print(f"\n1. Testing enhanced watchlist data for symbols: {test_symbols}")
        enhanced_data = await mock_enhanced_market_data.get_enhanced_watchlist_data(test_symbols)
        
        if enhanced_data:
            print(f"✓ Successfully retrieved data for {len(enhanced_data)} symbols")
            
            # Display sample data for first symbol
            if enhanced_data:
                first_symbol = list(enhanced_data.keys())[0]
                sample_data = enhanced_data[first_symbol]
                
                print(f"\nSample data for {first_symbol}:")
                print(f"  Previous Close: ${sample_data.get('previous_close', 'N/A')}")
                print(f"  Current Price: ${sample_data.get('current_price', 'N/A')}")
                print(f"  Pre-Market: ${sample_data.get('pre_market_price', 'N/A')}")
                print(f"  Opening Price: ${sample_data.get('opening_price', 'N/A')}")
                print(f"  Gap Pre-Market: {sample_data.get('gap_pre_market_percent', 'N/A')}%")
                print(f"  Gap Open: {sample_data.get('gap_open_percent', 'N/A')}%")
                print(f"  Volume Ratio: {sample_data.get('volume_ratio', 'N/A')}")
                print(f"  Market Session: {sample_data.get('market_session', 'N/A')}")
                
                # Display formatting info
                formatting = sample_data.get('display_formatting', {})
                print(f"  Color Coding:")
                print(f"    Price Color: {formatting.get('price_color', 'N/A')}")
                print(f"    Gap Color: {formatting.get('gap_color', 'N/A')}")
                print(f"    Volume Color: {formatting.get('volume_color', 'N/A')}")
                print(f"    Background Intensity: {formatting.get('bg_intensity', 'N/A')}")
        else:
            print("✗ No data retrieved")
            
        print(f"\n2. Testing watchlist summary")
        summary_data = await mock_enhanced_market_data.get_watchlist_summary(test_symbols)
        
        if summary_data:
            print("✓ Successfully retrieved summary data")
            print(f"  Total Symbols: {summary_data.get('total_symbols', 'N/A')}")
            print(f"  Gappers: {summary_data.get('gappers', 'N/A')}")
            print(f"  Movers: {summary_data.get('movers', 'N/A')}")
            print(f"  High Volume: {summary_data.get('high_volume', 'N/A')}")
            print(f"  Top Movers: {summary_data.get('top_movers', [])}")
            print(f"  Top Gappers: {summary_data.get('top_gappers', [])}")
            print(f"  Market Session: {summary_data.get('market_session', 'N/A')}")
        else:
            print("✗ No summary data retrieved")
            
        print(f"\n3. Testing all watchlist symbols individually")
        for symbol in test_symbols:
            symbol_data = await mock_enhanced_market_data.get_enhanced_watchlist_data([symbol])
            if symbol in symbol_data:
                data = symbol_data[symbol]
                price_change = data.get('price_change_percent', 0)
                gap_pm = data.get('gap_pre_market_percent', 0)
                volume_ratio = data.get('volume_ratio', 0)
                
                status = "📈" if price_change > 0 else "📉" if price_change < 0 else "➡️"
                print(f"  {status} {symbol}: {price_change:+.2f}% | Gap: {gap_pm:+.2f}% | Vol: {volume_ratio:.1f}x")
            else:
                print(f"  ✗ {symbol}: No data")
        
        print(f"\n✓ Enhanced watchlist functionality test completed successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_enhanced_watchlist())
    sys.exit(0 if result else 1)