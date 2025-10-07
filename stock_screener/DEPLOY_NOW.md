# 🚀 Deploy to Railway NOW - Ready to Go!

Your screener is configured and tested. Follow these simple steps:

---

## ✅ What's Working

- ✅ Alpaca API: Connected
- ✅ Email: Tested successfully (check ariasgon@msn.com!)
- ⚠️ FMP API: Needs activation (see FMP_TROUBLESHOOTING.md)

**Solution**: Using `screener_simple.py` (works without FMP)

---

## 🚂 Railway Deployment (5 Minutes)

### Step 1: Go to Railway

1. Open: https://railway.app/dashboard
2. Find your project: **`fortunate-charm`**
3. Click on it

### Step 2: Create New Service

1. Click **"+ New"**
2. Select **"Empty Service"**
3. Name it: `stock-screener`

### Step 3: Add Environment Variables

1. Click on your new service
2. Go to **"Variables"** tab
3. Click **"RAW Editor"**
4. Paste this EXACTLY:

```
ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU
EMAIL_FROM=sales@forjaanalytics.com
EMAIL_TO=ariasgon@msn.com
EMAIL_PASSWORD=qkiuqgoblfkngegl
```

5. Click **"Save"**

### Step 4: Upload Code

**Option A: Via GitHub** (Recommended)

1. Create GitHub repo for your screener folder
2. In Railway, click "Settings" → "Connect to GitHub Repo"
3. Select your repo

**Option B: Manual Deploy**

1. In Railway service, go to "Deployments"
2. Click "Deploy"
3. Upload these files from `stock_screener/`:
   - `screener_simple.py`
   - `requirements.txt`
   - `.env` (or use variables from step 3)

### Step 5: Set Start Command

1. Go to **"Settings"**
2. Scroll to **"Start Command"**
3. Enter: `python screener_simple.py`
4. Click **"Save"**

### Step 6: Add Cron Schedule

1. Still in Settings, scroll to **"Cron Schedule"**
2. Click **"Add Cron Schedule"**
3. **Schedule**: `0 21 * * 1-5`
4. **Command**: `python screener_simple.py`
5. Click **"Add"**

### Step 7: Test It!

1. Go to "Deployments" tab
2. Click **"Trigger Deploy"**
3. Click the deployment → **"View Logs"**

You should see:
```
Screening 63 stocks for 30%+ drops from 5-year ATH...
Found: TSLA: -45.2% from ATH
...
Email sent successfully to ariasgon@msn.com
```

---

## 📅 Schedule Explained

**`0 21 * * 1-5`**
- Runs at 9 PM UTC
- = 4 PM EST (market close!)
- Monday-Friday only

**Need different time?**
- 5 PM EST: `0 22 * * 1-5`
- 3 PM EST: `0 20 * * 1-5`
- Daily: `0 21 * * *`

---

## 📧 What You'll Get

Every weekday at 4 PM EST, you'll receive an email at **ariasgon@msn.com** with:

| Ticker | Current Price | 5Y ATH | Drop % | 5Y CAGR |
|--------|--------------|---------|---------|----------|
| TSLA   | $443.78      | $891.00 | -50.2%  | 15.3%    |
| ABBV   | $238.24      | $340.00 | -32.0%  | 8.2%     |

---

## 🔧 After FMP API is Fixed

Once your FMP API key is activated:

1. Add to Railway variables:
   ```
   FMP_API_KEY=7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI
   ```

2. Change start command to:
   ```
   python screener.py
   ```

3. You'll get extra data:
   - PE Ratio
   - Sales CAGR
   - Profit CAGR
   - PE CAGR

---

## ✅ Deployment Checklist

- [ ] Go to railway.app/dashboard
- [ ] Find project `fortunate-charm`
- [ ] Create new service
- [ ] Add environment variables
- [ ] Set start command: `python screener_simple.py`
- [ ] Set cron: `0 21 * * 1-5`
- [ ] Test deployment
- [ ] Verify email arrives

---

## 🎉 You're Live!

Once deployed:
- ✅ Runs automatically every weekday
- ✅ No computer needed
- ✅ 100% free (Railway free tier)
- ✅ Emails arrive at market close

**First email**: Tomorrow at 4 PM EST! 📬

---

## 💡 Quick Tips

1. **Check logs** if no email:
   - Railway → Deployments → View Logs

2. **Manual run** anytime:
   - Deployments → Trigger Deploy

3. **Pause temporarily**:
   - Settings → Disable Cron

4. **Change email**:
   - Variables → Edit `EMAIL_TO`

---

## 📞 Need Help?

- Check Railway logs first
- See FMP_TROUBLESHOOTING.md for API issues
- Test locally with `python screener_simple.py`

Enjoy your automated stock screener! 🚀
