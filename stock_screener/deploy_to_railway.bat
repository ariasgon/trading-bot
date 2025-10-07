@echo off
echo ============================================================
echo Railway Deployment Script
echo ============================================================
echo.

echo Checking Railway CLI...
railway --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Railway CLI not found. Installing...
    npm install -g @railway/cli
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Failed to install Railway CLI
        echo Please install manually: npm install -g @railway/cli
        pause
        exit /b 1
    )
)

echo.
echo Logging in to Railway...
railway login

echo.
echo Linking to project 'fortunate-charm'...
railway link

echo.
echo Setting environment variables...
railway variables set ALPACA_API_KEY=PKWL2CDN7XQY9YCM78TU
railway variables set ALPACA_SECRET_KEY=zh3KYYWL4867PhRIZWlClPBRBeMu39iIQtKtQIhU
railway variables set FMP_API_KEY=7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI
railway variables set EMAIL_FROM=sales@forjaanalytics.com
railway variables set EMAIL_TO=ariasgon@msn.com
railway variables set EMAIL_PASSWORD=qkiuqgoblfkngegl

echo.
echo Deploying to Railway...
railway up

echo.
echo ============================================================
echo Deployment Complete!
echo ============================================================
echo.
echo Next: Set up the cron schedule in Railway dashboard
echo 1. Go to: https://railway.app/dashboard
echo 2. Click on your service
echo 3. Go to Settings ^> Cron Schedule
echo 4. Schedule: 0 21 * * 1-5
echo 5. Command: python screener.py
echo.
pause
