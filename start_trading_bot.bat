@echo off
echo Starting Trading Bot...
echo.

REM Change to the trading bot directory
cd /d "C:\Users\arias\OneDrive\Desktop\trading-bot"

REM Check if we're in the correct directory
if not exist "docker-compose.yml" (
    echo ERROR: docker-compose.yml not found in current directory
    echo Make sure you're in the correct trading-bot folder
    pause
    exit /b 1
)

REM Start Docker containers
echo Starting Docker containers...
docker-compose up -d

REM Check if containers started successfully
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Trading Bot started successfully!
    echo.
    echo Dashboard: http://localhost:8000/static/dashboard.html
    echo API Docs: http://localhost:8000/docs
    echo.
    echo Press any key to exit...
    pause >nul
) else (
    echo.
    echo ❌ Failed to start Trading Bot
    echo Make sure Docker Desktop is running
    echo.
    pause
    exit /b 1
)