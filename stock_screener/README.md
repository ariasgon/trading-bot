# 📊 Stock Screener - Deep Value Alerts

Automated daily screener that finds stocks down 30%+ from their 5-year all-time high and emails you a detailed report with fundamental data.

## 🎯 What It Does

- Scans S&P 500 stocks daily at market close
- Finds stocks down ≥30% from 5-year ATH
- Collects fundamental data:
  - PE Ratio
  - 5-year CAGR: Price, Sales, Profits, PE
- Emails formatted HTML report
- Runs automatically in the cloud (no computer needed!)

## 🚀 Quick Start

See **SETUP_GUIDE.md** for detailed instructions

### 1. Get API Keys
- ✅ Alpaca (you have it)
- Financial Modeling Prep (free)
- Gmail App Password (free)

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your keys
```

### 3. Test Locally
```bash
pip install -r requirements.txt
python screener.py
```

### 4. Deploy to Cloud
Choose one:
- **Railway.app** (easiest)
- AWS Lambda
- Google Cloud Functions

## 📧 Email Example

You'll receive:
- Ticker symbols
- Current vs ATH prices
- Drop percentage
- Fundamental metrics
- Color-coded gains/losses

## 🔧 Files

- `screener.py` - Main screening logic
- `requirements.txt` - Python dependencies
- `.env.example` - Environment template
- `SETUP_GUIDE.md` - Complete setup instructions
- `lambda_handler.py` - AWS Lambda wrapper
- `Procfile` - Railway deployment config

## 📅 Schedule

Runs Monday-Friday at 4:00 PM ET (market close)

Customize in cloud platform cron settings.

## 💰 Cost

**100% FREE** using free tiers:
- Alpaca: Free
- Financial Modeling Prep: 250 calls/day free
- Gmail SMTP: 500 emails/day free
- Railway: $5/month credit (plenty for daily job)

## 🎓 How It Works

1. Fetches 5 years of price data from Alpaca
2. Calculates all-time high for each stock
3. Filters stocks down ≥30% from ATH
4. Fetches fundamentals from FMP API
5. Calculates CAGRs (only needs 2 data points!)
6. Generates HTML email
7. Sends via Gmail SMTP

## 🔐 Security

- Never commit `.env` file
- Use App Passwords (not Gmail password)
- Store secrets in cloud platform
- All API keys are read-only

## 📈 Extending

Want to add more features?
- Add more screening criteria
- Include technical indicators
- Export to CSV/Google Sheets
- Add Slack/SMS alerts
- Backtest historical signals

## 🐛 Need Help?

Check `SETUP_GUIDE.md` troubleshooting section
