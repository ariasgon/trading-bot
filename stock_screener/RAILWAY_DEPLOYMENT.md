# 🚂 Railway Deployment Guide

## Your Project: `fortunate-charm`

Your stock screener is ready to deploy to Railway!

---

## 🚀 Quick Deploy Steps

### 1. Push to GitHub (if not already done)

```bash
cd OneDrive/Desktop/trading-bot/stock_screener

# Initialize git if needed
git init
git add .
git commit -m "Initial stock screener setup"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/stock-screener.git
git push -u origin main
```

**OR** just upload the folder to a new GitHub repo via the web interface.

---

### 2. Deploy to Railway

1. **Go to Railway**: https://railway.app/dashboard
2. **Find your project**: `fortunate-charm`
3. **Add New Service**:
   - Click "+ New"
   - Select "GitHub Repo"
   - Choose your stock-screener repo (or select "Empty Service" to deploy manually)

4. **Add Environment Variables**:
   - Click on your service
   - Go to "Variables" tab
   - Click "RAW Editor"
   - Paste this:

```
ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU
FMP_API_KEY=7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI
EMAIL_FROM=sales@forjaanalytics.com
EMAIL_TO=ariasgon@msn.com
EMAIL_PASSWORD=qkiuqgoblfkngegl
```

5. **Set up Cron Schedule**:
   - In your service, go to "Settings"
   - Scroll to "Cron Schedule"
   - **Schedule**: `0 21 * * 1-5`
   - **Command**: `python screener.py`
   - Click "Add"

6. **Deploy**:
   - Railway will auto-deploy
   - Check "Deployments" tab for status

---

## ⏰ Schedule Details

**Cron**: `0 21 * * 1-5`
- Runs at **9:00 PM UTC**
- Which is **4:00 PM EST** (market close!)
- **Monday-Friday only**

**To adjust timezone**:
- 5 PM EST = `0 22 * * 1-5` (10 PM UTC)
- 3 PM EST = `0 20 * * 1-5` (8 PM UTC)

---

## 📧 What Happens

Every weekday at 4 PM EST:
1. Railway runs your screener
2. Scans S&P 500 for 30%+ drops
3. Gets fundamental data
4. Emails report to: **ariasgon@msn.com**

---

## 🧪 Test Deployment

After deploying, you can trigger a manual run:

1. Go to Railway dashboard
2. Click on your service
3. Go to "Deployments" tab
4. Click the latest deployment
5. Click "View Logs"
6. You should see the screener running

**OR** click "Trigger Deploy" to run it immediately!

---

## 🔍 Monitoring

Check logs in Railway:
- Click your service → "Deployments" → Latest deployment → "View Logs"

You'll see:
```
Screening 63 stocks for 30%+ drops from 5-year ATH...
✓ TSLA: -45.2% from ATH
✓ ABBV: -32.1% from ATH
✅ Found 12 stocks down 30%+ from 5-year ATH
✅ Email sent successfully to ariasgon@msn.com
```

---

## 🐛 Troubleshooting

### Deployment fails
- Check "Deployments" → "View Logs" for errors
- Verify all environment variables are set
- Make sure `requirements.txt` is in the root folder

### Email not sending
- Verify app password is correct (no spaces)
- Check Railway logs for error messages
- Test locally first with `python test_setup.py`

### Not finding stocks
- Normal if market is strong
- Lower threshold to -20% if you want more results
- Check logs to see if it's running

### Wrong timezone
- UTC to EST is -5 hours (or -4 during DST)
- Adjust cron schedule accordingly

---

## 💡 Pro Tips

1. **Test Locally First**
   ```bash
   python test_setup.py  # Verify everything works
   python screener.py     # Run full scan
   ```

2. **Monitor First Week**
   - Check Railway logs daily
   - Verify emails are arriving
   - Adjust threshold if needed

3. **Set Up Notifications**
   - Railway can notify you if deployment fails
   - Settings → Notifications

4. **Cost Management**
   - Free tier: $5/month credit
   - This job uses ~$0.10/month
   - You're well within free limits!

---

## 📊 API Usage

With default settings:
- **Alpaca**: 63 stocks × 1 call = 63 calls/day
- **FMP**: 63 stocks × 2 calls = ~126 calls/day
- **Gmail**: 1 email/day
- **Total**: Well within all free tiers ✅

---

## ✅ Deployment Checklist

- [ ] Code pushed to GitHub (optional)
- [ ] Railway project `fortunate-charm` ready
- [ ] Environment variables added to Railway
- [ ] Cron schedule set: `0 21 * * 1-5`
- [ ] Command set: `python screener.py`
- [ ] First deployment successful
- [ ] Logs show screener running
- [ ] Test email received at ariasgon@msn.com

---

## 🎉 You're Live!

Your screener will now run automatically every weekday at 4 PM EST!

**Next email**: Tomorrow at market close 📬

Check your inbox at **ariasgon@msn.com** for the report!

---

## 🔧 Future Enhancements

Want to add more features?
- Add more stock universes (Russell 2000, NASDAQ 100)
- Include technical indicators (RSI, MACD)
- Export to Google Sheets
- Add Slack/Discord notifications
- Create backtesting module

Just update the code and push to GitHub - Railway will auto-deploy!
