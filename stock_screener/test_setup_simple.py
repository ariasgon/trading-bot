"""
Simple test script for Windows - no emojis
"""
import os
from dotenv import load_dotenv
import requests
import smtplib
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()

print("="*60)
print("STOCK SCREENER SETUP TEST")
print("="*60)
print()

# Test 1: Environment Variables
print("1. Checking environment variables...")
required_vars = [
    'ALPACA_API_KEY',
    'ALPACA_SECRET_KEY',
    'FMP_API_KEY',
    'EMAIL_FROM',
    'EMAIL_TO',
    'EMAIL_PASSWORD'
]

all_set = True
for var in required_vars:
    value = os.getenv(var)
    if not value:
        print(f"   MISSING: {var}")
        all_set = False
    else:
        masked = value[:4] + '...' if len(value) > 4 else value
        print(f"   OK: {var}: {masked}")

if not all_set:
    print("\nPlease add missing variables to .env file")
    exit(1)

print("   SUCCESS: All environment variables set!\n")

# Test 2: Alpaca API
print("2. Testing Alpaca API...")
try:
    headers = {
        "APCA-API-KEY-ID": os.getenv('ALPACA_API_KEY'),
        "APCA-API-SECRET-KEY": os.getenv('ALPACA_SECRET_KEY')
    }

    response = requests.get(
        "https://paper-api.alpaca.markets/v2/account",
        headers=headers
    )
    response.raise_for_status()

    account = response.json()
    print(f"   SUCCESS: Connected!")
    print(f"   Account: {account.get('account_number')}")
    print(f"   Equity: ${float(account.get('equity', 0)):,.2f}\n")
except Exception as e:
    print(f"   ERROR: {e}\n")
    exit(1)

# Test 3: FMP API
print("3. Testing Financial Modeling Prep API...")
try:
    api_key = os.getenv('FMP_API_KEY')

    response = requests.get(
        f"https://financialmodelingprep.com/api/v3/quote/AAPL",
        params={'apikey': api_key}
    )
    response.raise_for_status()

    data = response.json()
    if data and len(data) > 0:
        print(f"   SUCCESS: Connected!")
        print(f"   Test quote for AAPL: ${data[0].get('price')}\n")
    else:
        print(f"   ERROR: No data returned. Check your API key.\n")
        exit(1)
except Exception as e:
    print(f"   ERROR: {e}")
    print("   Get your free API key at: https://financialmodelingprep.com/developer/docs/\n")
    exit(1)

# Test 4: Gmail SMTP
print("4. Testing Gmail SMTP...")
try:
    email_from = os.getenv('EMAIL_FROM')
    email_to = os.getenv('EMAIL_TO')
    password = os.getenv('EMAIL_PASSWORD')

    msg = MIMEText("This is a test email from your Stock Screener setup!")
    msg['Subject'] = 'Stock Screener - Test Email SUCCESS'
    msg['From'] = email_from
    msg['To'] = email_to

    print(f"   Sending test email to {email_to}...")
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(email_from, password)
        server.send_message(msg)

    print(f"   SUCCESS: Test email sent!")
    print(f"   Check your inbox at {email_to}\n")
except Exception as e:
    print(f"   ERROR: {e}")
    print("\n   Troubleshooting:")
    print("   1. Make sure you're using an App Password (not your Gmail password)")
    print("   2. Enable 2-Step Verification in Gmail")
    print("   3. Create App Password at: https://myaccount.google.com/apppasswords")
    print("   4. The App Password should be 16 characters\n")
    exit(1)

# Summary
print("="*60)
print("TEST SUMMARY")
print("="*60)
print("PASS - Environment Variables")
print("PASS - Alpaca API")
print("PASS - FMP API")
print("PASS - Gmail SMTP")
print("\n" + "="*60)
print("ALL TESTS PASSED!")
print("="*60)
print("\nYou're ready to run the screener:")
print("  python screener.py")
print("\nOr deploy to Railway (see RAILWAY_DEPLOYMENT.md)")
print()
