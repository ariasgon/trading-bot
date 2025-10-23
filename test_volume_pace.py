"""
Test Volume Pace Calculation Fix

This script tests the new time-aware volume pace calculation
to ensure it correctly identifies high-volume stocks.
"""
import sys
from datetime import datetime, time
import pytz

# Simulated test scenarios
def calculate_volume_pace(current_volume: float, avg_daily_volume: float, test_time: time = None) -> float:
    """
    Calculate volume PACE (rate) accounting for time of day.
    This is a copy of the logic from proprietary_strategy.py for testing.
    """
    try:
        est = pytz.timezone('US/Eastern')

        if test_time:
            # Use provided test time
            current_time = test_time
        else:
            # Use current time
            now_est = datetime.now(est)
            current_time = now_est.time()

        # Market hours: 9:30 AM - 4:00 PM EST (6.5 hours = 390 minutes)
        market_open = time(9, 30)
        market_close = time(16, 0)

        # Convert times to minutes since midnight for calculation
        current_minutes = current_time.hour * 60 + current_time.minute
        open_minutes = market_open.hour * 60 + market_open.minute
        close_minutes = market_close.hour * 60 + market_close.minute

        # If before market open, assume we're at market open time
        if current_minutes < open_minutes:
            current_minutes = open_minutes

        # If after market close, assume we're at market close
        if current_minutes > close_minutes:
            current_minutes = close_minutes

        # Calculate percentage of trading day elapsed
        minutes_elapsed = current_minutes - open_minutes
        total_trading_minutes = close_minutes - open_minutes  # 390 minutes

        if total_trading_minutes <= 0:
            return (0.0, 0.0, 0.0, 0)

        pct_day_elapsed = minutes_elapsed / total_trading_minutes

        # Expected volume at this point in the day
        expected_volume = avg_daily_volume * pct_day_elapsed

        if expected_volume <= 0:
            return (0.0, 0.0, 0.0, 0)

        # Calculate pace: actual / expected
        volume_pace = current_volume / expected_volume

        return volume_pace, pct_day_elapsed, expected_volume, minutes_elapsed

    except Exception as e:
        print(f"Error calculating volume pace: {e}")
        return (0.0, 0.0, 0.0, 0)


def test_volume_pace():
    """Test volume pace calculation with various scenarios."""

    print("=" * 80)
    print("VOLUME PACE CALCULATION TEST")
    print("=" * 80)
    print()

    # Test scenario: Stock with 10M average daily volume
    avg_daily_volume = 10_000_000

    test_cases = [
        # (time, current_volume, description)
        (time(9, 30), 1_000_000, "Market open - 1M volume (10% of avg)"),
        (time(10, 0), 1_000_000, "30 mins in - 1M volume (10% of avg)"),
        (time(10, 0), 2_000_000, "30 mins in - 2M volume (20% of avg) - HIGH VOLUME"),
        (time(11, 0), 2_000_000, "1.5 hours in - 2M volume (20% of avg)"),
        (time(11, 0), 5_000_000, "1.5 hours in - 5M volume (50% of avg) - HIGH VOLUME"),
        (time(13, 0), 5_000_000, "Mid-day - 5M volume (50% of avg)"),
        (time(15, 0), 8_000_000, "Near close - 8M volume (80% of avg)"),
        (time(16, 0), 12_000_000, "Market close - 12M volume (120% of avg)"),
    ]

    print(f"Average Daily Volume: {avg_daily_volume:,} shares")
    print(f"Volume Threshold: 2.0x pace")
    print()
    print("-" * 80)

    for test_time, current_volume, description in test_cases:
        pace, pct_elapsed, expected_vol, mins_elapsed = calculate_volume_pace(
            current_volume, avg_daily_volume, test_time
        )

        meets_threshold = "[PASS]" if pace >= 2.0 else "[FAIL]"

        print(f"\n{description}")
        print(f"  Time: {test_time.strftime('%I:%M %p')} EST ({mins_elapsed} mins into trading day)")
        print(f"  Trading day elapsed: {pct_elapsed*100:.1f}%")
        print(f"  Current volume: {current_volume:,} shares")
        print(f"  Expected volume by now: {expected_vol:,.0f} shares")
        print(f"  Volume pace: {pace:.2f}x {meets_threshold}")

    print()
    print("=" * 80)
    print("OLD METHOD (BROKEN) vs NEW METHOD (FIXED) COMPARISON")
    print("=" * 80)
    print()

    # Compare old vs new method
    test_time = time(10, 0)  # 30 mins after open
    current_volume = 2_000_000  # 2M shares traded

    # OLD METHOD (broken)
    old_ratio = current_volume / avg_daily_volume

    # NEW METHOD (fixed)
    new_pace, pct_elapsed, expected_vol, mins = calculate_volume_pace(
        current_volume, avg_daily_volume, test_time
    )

    print(f"Scenario: 30 minutes after market open")
    print(f"Current volume: {current_volume:,} shares")
    print(f"Average daily volume: {avg_daily_volume:,} shares")
    print()
    print(f"OLD METHOD (BROKEN):")
    print(f"  Calculation: {current_volume:,} / {avg_daily_volume:,}")
    print(f"  Result: {old_ratio:.2f}x [FAIL] (fails 2.0x threshold)")
    print(f"  Problem: Compares partial day to full day")
    print()
    print(f"NEW METHOD (FIXED):")
    print(f"  Trading day elapsed: {pct_elapsed*100:.1f}%")
    print(f"  Expected volume by now: {expected_vol:,.0f} shares")
    print(f"  Calculation: {current_volume:,} / {expected_vol:,.0f}")
    print(f"  Result: {new_pace:.2f}x [PASS] (passes 2.0x threshold)")
    print(f"  Insight: Trading at {new_pace:.1f}x normal pace!")
    print()
    print("=" * 80)


if __name__ == "__main__":
    test_volume_pace()
