# ⚡ Quick Start - Stock Screener

Get your screener running in **15 minutes**!

## 🎯 Goal

Receive daily emails with stocks down 30%+ from their 5-year highs, including fundamental data.

---

## 📝 Step-by-Step

### 1. Get Financial Modeling Prep API Key (2 min)

1. Go to: https://financialmodelingprep.com/developer/docs/
2. Click "Get Free API Key"
3. Sign up (email + password)
4. Copy your API key
5. ✅ You get **250 free API calls per day**

---

### 2. Get Gmail App Password (3 min)

**IMPORTANT: This is NOT your Gmail password!**

1. Go to: https://myaccount.google.com/security
2. Scroll to "2-Step Verification" → Turn it ON if not enabled
3. Go to: https://myaccount.google.com/apppasswords
4. Select:
   - App: **Mail**
   - Device: **Other** (name it "Stock Screener")
5. Click "Generate"
6. **Copy the 16-character password** (example: `abcd efgh ijkl mnop`)
7. ✅ Save it - you'll only see it once!

---

### 3. Configure Your Screener (2 min)

```bash
cd OneDrive/Desktop/trading-bot/stock_screener
cp .env.example .env
```

Edit `.env` file with your info:

```bash
# Alpaca (you already have these!)
ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU

# FMP API (from step 1)
FMP_API_KEY=paste_your_fmp_key_here

# Gmail (from step 2)
EMAIL_FROM=youremail@gmail.com
EMAIL_TO=youremail@gmail.com
EMAIL_PASSWORD=abcd efgh ijkl mnop
```

---

### 4. Test Everything (5 min)

```bash
# Install dependencies
pip install -r requirements.txt

# Run setup test
python test_setup.py
```

You should see:
```
✅ PASS - Environment Variables
✅ PASS - Alpaca API
✅ PASS - FMP API
✅ PASS - Gmail SMTP
🎉 ALL TESTS PASSED!
```

And receive a test email!

---

### 5. Run Your First Scan (3 min)

```bash
python screener.py
```

Output:
```
Screening 63 stocks for 30%+ drops from 5-year ATH...
✓ TSLA: -45.2% from ATH
✓ ABBV: -32.1% from ATH
✅ Found 12 stocks down 30%+ from 5-year ATH
✅ Email sent successfully
```

**Check your email!** You should have a beautiful HTML report with all the data.

---

## 🚀 Deploy to Cloud (Optional - for automatic daily emails)

### Railway.app (Recommended - 5 min setup)

**Free: $5/month credit (plenty for daily job)**

1. **Sign up**: https://railway.app
   - Use GitHub to sign in

2. **Create Project**
   - Click "New Project"
   - Select "Empty Project"

3. **Add Service**
   - Click "+ New"
   - Select "GitHub Repo"
   - Connect your stock_screener folder

4. **Add Environment Variables**
   - Click on your service
   - Go to "Variables" tab
   - Click "Raw Editor"
   - Paste all variables from your `.env` file

5. **Add Cron Job**
   - In service settings → "Cron"
   - Schedule: `0 21 * * 1-5`
   - Command: `python screener.py`

6. **Deploy**
   - Railway auto-deploys
   - Done! 🎉

**Cron explained**: `0 21 * * 1-5` = 9 PM UTC (4 PM ET), Monday-Friday

---

## 📧 What You'll Get

Daily email with:
- Stocks down 30%+ from ATH
- Current price vs 5-year high
- Drop percentage
- PE ratio
- Price CAGR (5 years)
- Sales CAGR (5 years)
- Profit CAGR (5 years)
- PE ratio CAGR (5 years)

Formatted as nice HTML table with color coding!

---

## 💡 Tips

### Customize the threshold
Want 40% drops instead of 30%?

Edit `screener.py` line 163:
```python
# Change from:
if drop_pct <= -30:

# To:
if drop_pct <= -40:
```

### Add more stocks
Edit `get_sp500_symbols()` method in `screener.py` to add more tickers.

### Change schedule
Adjust cron in Railway:
- `0 21 * * 1-5` = Weekdays 4 PM ET
- `0 22 * * *` = Daily 5 PM ET
- `0 14 * * 1` = Mondays 9 AM ET

---

## 🐛 Troubleshooting

### "Email not sending"
- Use App Password, not Gmail password
- Enable 2-Step Verification first
- Copy the 16-char password exactly

### "No fundamentals data"
- Check FMP API key is correct
- Verify at: https://financialmodelingprep.com/developer/docs/dashboard

### "Not finding stocks"
- This is normal! If market is up, fewer stocks will be down 30%
- Lower threshold to -20% if you want more results

---

## ✅ Checklist

- [ ] Got FMP API key
- [ ] Got Gmail App Password
- [ ] Created .env file
- [ ] Ran test_setup.py successfully
- [ ] Ran screener.py successfully
- [ ] Received test email
- [ ] (Optional) Deployed to Railway

---

## 🎉 You're Done!

You now have:
- ✅ Automated stock screening
- ✅ Daily email alerts
- ✅ Fundamental analysis
- ✅ Runs in the cloud (no computer needed!)
- ✅ 100% FREE

---

## 📚 Next Steps

- Read `SETUP_GUIDE.md` for advanced config
- Customize screening criteria
- Add more metrics
- Set up Slack notifications
- Backtest the signals

Enjoy your automated deep value screener! 📊🚀
