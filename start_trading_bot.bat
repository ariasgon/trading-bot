@echo off
title Trading Bot Launcher
color 0A

echo.
echo ========================================
echo       TRADING BOT LAUNCHER
echo ========================================
echo.
echo Starting Trading Bot Application...
echo.

REM Change to the trading bot directory
cd /d "%~dp0"

REM Check if we're in the correct directory
if not exist "docker-compose.yml" (
    echo ERROR: docker-compose.yml not found in current directory
    echo Make sure you're in the correct trading-bot folder
    pause
    exit /b 1
)

echo [1/5] Checking Docker containers...
docker-compose ps | findstr trading_postgres >nul 2>&1
if %errorlevel% neq 0 (
    echo     Starting PostgreSQL and Redis containers...
    docker-compose up -d db redis
    echo     Waiting for databases to initialize...
    timeout /t 10 >nul
) else (
    echo     Docker containers already running
)

echo.
echo [2/5] Checking Python dependencies...
"C:\Users\arias\AppData\Local\Programs\Python\Python312\python.exe" -c "import fastapi, uvicorn" 2>nul
if %errorlevel% neq 0 (
    echo     Installing missing Python packages...
    "C:\Users\arias\AppData\Local\Programs\Python\Python312\python.exe" -m pip install fastapi uvicorn pydantic sqlalchemy redis alpaca-trade-api pandas psycopg2-binary schedule
) else (
    echo     Python dependencies are ready
)

echo.
echo [3/5] Starting Trading Bot API Server...
start "Trading Bot API" /min "C:\Users\arias\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

echo     Waiting for server to start...
timeout /t 8 >nul

echo.
echo [4/5] Auto-starting the trading bot...
curl -s -X POST http://localhost:8000/api/v1/bot/start > nul 2>&1
if %errorlevel% equ 0 (
    echo     Trading bot activated successfully!
) else (
    echo     Note: Bot will need to be started manually from dashboard
)

echo.
echo [5/5] Opening Trading Bot Dashboard...
echo     Starting browser...
timeout /t 2 >nul
start http://localhost:8000/dashboard

echo.
echo ========================================
echo         TRADING BOT READY!
echo ========================================
echo.
echo API Server: http://localhost:8000
echo Dashboard: http://localhost:8000/dashboard
echo API Docs: http://localhost:8000/docs
echo.
echo Trading Hours: 10:00 AM - 2:00 PM EST (new entries)
echo                Positions close at 3:50 PM EST
echo.
echo Press any key to exit this window...
pause >nul
