# Stock Screener Setup Guide

## 📋 Prerequisites

1. **Alpaca API** (you already have this!)
2. **Financial Modeling Prep API** (free tier: 250 calls/day)
3. **Gmail Account** with App Password

---

## 🔑 Step 1: Get API Keys

### Financial Modeling Prep (Fundamentals Data)

1. Go to https://financialmodelingprep.com/developer/docs/
2. Sign up for free account
3. Get your API key (250 calls/day free)
4. Copy the API key

### Gmail App Password (Email Alerts)

**IMPORTANT: You MUST use an App Password, not your regular Gmail password**

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** (required for app passwords)
3. Go to https://myaccount.google.com/apppasswords
4. Create a new App Password:
   - Select "Mail" as the app
   - Select "Other" as device
   - Name it "Stock Screener"
5. **Copy the 16-character password** (no spaces)

---

## ⚙️ Step 2: Configure Environment

1. Copy `.env.example` to `.env`
2. Fill in your values:

```bash
# Alpaca (copy from your trading bot .env)
ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU

# Financial Modeling Prep (get from step 1)
FMP_API_KEY=your_fmp_key_here

# Gmail
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=your_email@gmail.com  # Can be different
EMAIL_PASSWORD=abcd efgh ijkl mnop  # 16-char app password
```

---

## 🧪 Step 3: Test Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the screener
python screener.py
```

You should receive an email within a few minutes!

---

## ☁️ Step 4: Deploy to Cloud (Choose One)

### **Option A: Railway.app** (Recommended - Easiest)

**Cost: FREE ($5/month credit)**

1. **Create Railway Account**
   - Go to https://railway.app
   - Sign up with GitHub

2. **Create New Project**
   - Click "New Project" → "Deploy from GitHub repo"
   - Or click "Empty Project" if you prefer manual setup

3. **Add Environment Variables**
   - Click on your service
   - Go to "Variables" tab
   - Add all variables from your `.env` file

4. **Add Cron Job**
   - In Railway, go to Settings → Cron
   - Schedule: `0 21 * * 1-5` (9 PM UTC = 4 PM ET, Mon-Fri)
   - Command: `python screener.py`

5. **Deploy**
   - Railway auto-deploys on git push

**Cron Schedule Explained:**
- `0 21 * * 1-5` = Run at 9 PM UTC (4 PM EST) Mon-Fri
- Adjust for your timezone!

---

### **Option B: AWS Lambda + EventBridge**

**Cost: FREE (1M requests/month)**

1. **Package the application**
```bash
cd stock_screener
pip install -r requirements.txt -t .
zip -r lambda_function.zip .
```

2. **Create Lambda Function**
   - Go to AWS Console → Lambda
   - Create function
   - Runtime: Python 3.11
   - Upload `lambda_function.zip`

3. **Add Environment Variables**
   - Configuration → Environment variables
   - Add all from `.env`

4. **Create EventBridge Rule**
   - Go to Amazon EventBridge
   - Create rule with cron: `cron(0 21 ? * MON-FRI *)`
   - Target: Your Lambda function

5. **Increase Timeout**
   - Lambda Configuration → General
   - Set timeout to 5 minutes

---

### **Option C: Google Cloud Functions**

**Cost: FREE (2M invocations/month)**

1. **Install gcloud CLI**
```bash
# Follow: https://cloud.google.com/sdk/docs/install
```

2. **Deploy Function**
```bash
cd stock_screener

gcloud functions deploy stock-screener \
  --runtime python311 \
  --trigger-http \
  --entry-point run \
  --set-env-vars ALPACA_API_KEY=xxx,...
```

3. **Create Cloud Scheduler Job**
```bash
gcloud scheduler jobs create http stock-screener-daily \
  --schedule="0 21 * * 1-5" \
  --uri="https://YOUR-FUNCTION-URL" \
  --http-method=GET
```

---

## 📧 Email Preview

Your email will look like this:

| Ticker | Current Price | 5Y ATH | Drop % | PE | Price CAGR | Sales CAGR | Profit CAGR |
|--------|--------------|---------|--------|-----|-----------|-----------|-------------|
| TSLA   | $443.78      | $891.00 | -50.2% | 65  | 15.3%     | 28.5%     | 42.1%       |
| ABBV   | $238.24      | $175.00 | -36.0% | 12  | 8.2%      | 12.3%     | 15.6%       |

---

## 🔧 Customization

### Change Screening Criteria

Edit `screener.py`:

```python
# Current: 30% drop threshold
if drop_pct <= -30:

# Change to 40%:
if drop_pct <= -40:
```

### Add More Stocks

Edit the `get_sp500_symbols()` method to add more tickers.

### Change Email Schedule

Update the cron expression:
- Daily at 4 PM ET: `0 21 * * *`
- Weekdays at 5 PM ET: `0 22 * * 1-5`
- Every Monday at 9 AM ET: `0 14 * * 1`

---

## 🐛 Troubleshooting

### "Email not sending"
- Verify App Password (16 characters, no spaces)
- Check 2-Step Verification is enabled
- Try the password in Gmail SMTP settings

### "No fundamentals data"
- Verify FMP API key is correct
- Check you haven't exceeded 250 calls/day
- Some stocks may not have all data

### "Cloud function timing out"
- Increase timeout to 5-10 minutes
- Reduce number of stocks in screening list

---

## 📊 API Limits

| Service | Free Tier | Limit |
|---------|-----------|-------|
| Alpaca | Yes | Unlimited historical data |
| Financial Modeling Prep | Yes | 250 API calls/day |
| Gmail SMTP | Yes | 500 emails/day |
| Railway | $5 credit/month | ~750 hours |
| AWS Lambda | Yes | 1M requests/month |

---

## 🚀 Next Steps

1. Test locally first
2. Deploy to cloud
3. Verify first email arrives
4. Monitor for 1 week
5. Customize as needed

---

## 📞 Support

If you encounter issues:
1. Check logs in your cloud platform
2. Test locally with `python screener.py`
3. Verify all environment variables are set
