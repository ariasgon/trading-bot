"""Test Pabbly webhook integration"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

webhook_url = os.getenv('PABBLY_WEBHOOK_URL')

if not webhook_url:
    print("ERROR: PABBLY_WEBHOOK_URL not set in .env")
    exit(1)

# Test payload
test_data = {
    "date": "2025-10-07 12:00:00",
    "alert_count": 2,
    "subject": "Test: Stock Alert System",
    "alerts": [
        {
            "ticker": "AAPL",
            "current_price": 150.50,
            "ath_5y": 200.00,
            "drop_pct": -24.8,
            "ath_date": "2024-01-15"
        },
        {
            "ticker": "TSLA",
            "current_price": 180.25,
            "ath_5y": 300.00,
            "drop_pct": -39.9,
            "ath_date": "2023-11-10"
        }
    ]
}

print("Testing Pabbly webhook...")
print(f"URL: {webhook_url[:50]}...")
print(f"Sending test data with {len(test_data['alerts'])} alerts...")

try:
    response = requests.post(webhook_url, json=test_data, timeout=30)
    response.raise_for_status()
    print(f"SUCCESS! Status code: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"FAILED: {e}")
