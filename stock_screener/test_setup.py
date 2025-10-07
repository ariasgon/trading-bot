"""
Quick test script to verify your setup is correct
"""
import os
from dotenv import load_dotenv
import requests
import smtplib
from email.mime.text import MIMEText

# Load environment variables
load_dotenv()

def test_env_vars():
    """Check all required environment variables are set"""
    print("1️⃣ Checking environment variables...")

    required_vars = [
        'ALPACA_API_KEY',
        'ALPACA_SECRET_KEY',
        'FMP_API_KEY',
        'EMAIL_FROM',
        'EMAIL_TO',
        'EMAIL_PASSWORD'
    ]

    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing.append(var)
            print(f"   ❌ {var}: NOT SET")
        else:
            # Show first 4 chars only
            masked = value[:4] + '...' if len(value) > 4 else value
            print(f"   ✅ {var}: {masked}")

    if missing:
        print(f"\n⚠️  Missing variables: {', '.join(missing)}")
        print("Please add them to your .env file")
        return False

    print("✅ All environment variables set!\n")
    return True


def test_alpaca():
    """Test Alpaca API connection"""
    print("2️⃣ Testing Alpaca API...")

    try:
        headers = {
            "APCA-API-KEY-ID": os.getenv('ALPACA_API_KEY'),
            "APCA-API-SECRET-KEY": os.getenv('ALPACA_SECRET_KEY')
        }

        # Test account endpoint
        response = requests.get(
            "https://paper-api.alpaca.markets/v2/account",
            headers=headers
        )
        response.raise_for_status()

        account = response.json()
        print(f"   ✅ Connected! Account: {account.get('account_number')}")
        print(f"   💰 Equity: ${float(account.get('equity', 0)):,.2f}\n")
        return True

    except Exception as e:
        print(f"   ❌ Error: {e}\n")
        return False


def test_fmp():
    """Test Financial Modeling Prep API"""
    print("3️⃣ Testing Financial Modeling Prep API...")

    try:
        api_key = os.getenv('FMP_API_KEY')

        # Test with a simple quote
        response = requests.get(
            f"https://financialmodelingprep.com/api/v3/quote/AAPL",
            params={'apikey': api_key}
        )
        response.raise_for_status()

        data = response.json()
        if data and len(data) > 0:
            print(f"   ✅ Connected! Test quote for AAPL: ${data[0].get('price')}\n")
            return True
        else:
            print(f"   ❌ No data returned. Check your API key.\n")
            return False

    except Exception as e:
        print(f"   ❌ Error: {e}\n")
        print("   Get your free API key at: https://financialmodelingprep.com/developer/docs/\n")
        return False


def test_email():
    """Test Gmail SMTP connection"""
    print("4️⃣ Testing Gmail SMTP...")

    try:
        email_from = os.getenv('EMAIL_FROM')
        email_to = os.getenv('EMAIL_TO')
        password = os.getenv('EMAIL_PASSWORD')

        # Create test message
        msg = MIMEText("This is a test email from your Stock Screener setup! 🎉")
        msg['Subject'] = '✅ Stock Screener - Test Email'
        msg['From'] = email_from
        msg['To'] = email_to

        # Send test email
        print(f"   📧 Sending test email to {email_to}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(email_from, password)
            server.send_message(msg)

        print(f"   ✅ Test email sent successfully!")
        print(f"   📬 Check your inbox at {email_to}\n")
        return True

    except Exception as e:
        print(f"   ❌ Error: {e}")
        print("\n   Troubleshooting:")
        print("   1. Make sure you're using an App Password (not your Gmail password)")
        print("   2. Enable 2-Step Verification in Gmail")
        print("   3. Create App Password at: https://myaccount.google.com/apppasswords")
        print("   4. The App Password should be 16 characters (spaces don't matter)\n")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("🧪 STOCK SCREENER SETUP TEST")
    print("="*60 + "\n")

    results = []

    # Run tests
    results.append(("Environment Variables", test_env_vars()))

    if results[0][1]:  # Only continue if env vars are set
        results.append(("Alpaca API", test_alpaca()))
        results.append(("FMP API", test_fmp()))
        results.append(("Gmail SMTP", test_email()))

    # Summary
    print("="*60)
    print("📊 TEST SUMMARY")
    print("="*60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    all_passed = all(result[1] for result in results)

    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("="*60)
        print("\nYou're ready to run the screener:")
        print("  python screener.py")
        print("\nNext steps:")
        print("  1. Test locally first")
        print("  2. Then deploy to cloud (see SETUP_GUIDE.md)")
    else:
        print("⚠️  SOME TESTS FAILED")
        print("="*60)
        print("\nPlease fix the issues above and run this test again:")
        print("  python test_setup.py")
    print()


if __name__ == "__main__":
    main()
