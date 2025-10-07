# 🚀 Deploy to Railway - 3 Simple Options

Your FMP API is working! ✅ Let's deploy.

---

## Option 1: Automatic Deployment Script (EASIEST) ⭐

**Windows users - Just run this:**

```bash
cd OneDrive/Desktop/trading-bot/stock_screener
deploy_to_railway.bat
```

This script will:
1. Install Railway CLI (if needed)
2. Log you in
3. Link to your `fortunate-charm` project
4. Set all environment variables
5. Deploy your code

**Then manually set cron schedule** (see step below)

---

## Option 2: Railway CLI (Manual Commands)

### Step 1: Install Railway CLI

```bash
npm install -g @railway/cli
```

### Step 2: Navigate to folder

```bash
cd OneDrive/Desktop/trading-bot/stock_screener
```

### Step 3: Login to Railway

```bash
railway login
```

Browser will open - confirm login

### Step 4: Link to your project

```bash
railway link
```

Select: **`fortunate-charm`**

### Step 5: Set environment variables

```bash
railway variables set ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
railway variables set ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU
railway variables set FMP_API_KEY=7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI
railway variables set EMAIL_FROM=sales@forjaanalytics.com
railway variables set EMAIL_TO=ariasgon@msn.com
railway variables set EMAIL_PASSWORD=qkiuqgoblfkngegl
```

### Step 6: Deploy!

```bash
railway up
```

---

## Option 3: Railway Web UI (No CLI needed)

### Step 1: Create GitHub Repo

1. Go to https://github.com/new
2. Name it: `stock-screener`
3. Make it **Private**
4. Don't initialize with README
5. Create repository

### Step 2: Push code to GitHub

```bash
cd OneDrive/Desktop/trading-bot/stock_screener

git init
git add .
git commit -m "Stock screener initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/stock-screener.git
git push -u origin main
```

### Step 3: Deploy to Railway

1. Go to https://railway.app/dashboard
2. Find your project: **`fortunate-charm`**
3. Click **"+ New"** → **"GitHub Repo"**
4. Select your `stock-screener` repo
5. Wait for deployment to complete

### Step 4: Add Environment Variables

1. Click on your service
2. Go to **"Variables"** tab
3. Click **"RAW Editor"**
4. Paste this:

```
ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU
FMP_API_KEY=7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI
EMAIL_FROM=sales@forjaanalytics.com
EMAIL_TO=ariasgon@msn.com
EMAIL_PASSWORD=qkiuqgoblfkngegl
```

5. Click **"Update Variables"**

---

## 📅 Final Step: Set Up Cron Schedule (ALL OPTIONS)

**After deployment, set the schedule:**

1. Go to https://railway.app/dashboard
2. Click on your service in `fortunate-charm`
3. Go to **"Settings"**
4. Scroll to **"Cron Schedule"**
5. Click **"Add Cron Schedule"**

**Enter:**
- **Schedule**: `0 21 * * 1-5`
- **Command**: `python screener.py`

6. Click **"Add"**

---

## ✅ Verify It's Working

### Check Deployment

1. Go to **"Deployments"** tab
2. Click latest deployment
3. Click **"View Logs"**

Should see:
```
Screening 63 stocks for 30%+ drops from 5-year ATH...
✓ Found: TSLA: -45.2% from ATH
...
✅ Email sent successfully to ariasgon@msn.com
```

### Test Manual Run

1. Click **"Trigger Deploy"**
2. Watch the logs
3. Check your email!

---

## 🎉 You're Live!

Once cron is set:
- ✅ Runs Monday-Friday at 4 PM EST
- ✅ Scans all stocks automatically
- ✅ Emails you the results
- ✅ No computer needed!

**First scheduled email**: Tomorrow at 4 PM EST 📬

---

## 💡 Which Option Should I Use?

| Option | Best For | Time |
|--------|----------|------|
| **Option 1** (Script) | ⭐ Beginners | 2 min |
| **Option 2** (CLI) | Terminal users | 5 min |
| **Option 3** (Web UI) | GitHub users | 8 min |

**Recommendation**: Try **Option 1** first!

---

## 🐛 Troubleshooting

**Railway CLI not installing?**
- Install Node.js first: https://nodejs.org/

**"railway login" not working?**
- Close terminal, open new one
- Try: `railway whoami`

**Deployment fails?**
- Check logs in Railway dashboard
- Verify all variables are set
- Test locally first: `python screener.py`

---

## 📞 Need Help?

Run this command to check status:
```bash
railway status
```

View logs:
```bash
railway logs
```

Redeploy:
```bash
railway up
```

---

Ready? **Run `deploy_to_railway.bat`** and you're done! 🚀
