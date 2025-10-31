# 🤖 Trading Bot - Quick Start Guide

## Easy Launch Options

You now have multiple ways to start your Trading Bot without using the command line:

### 🖱️ Desktop Shortcut (Recommended)
- **Double-click** the `Trading Bot` shortcut on your desktop
- This will automatically:
  1. Start PostgreSQL and Redis containers
  2. Check and install Python dependencies
  3. Start the FastAPI server
  4. Open the dashboard in your browser

### 📁 From Project Folder
Navigate to the trading-bot folder and double-click any of these:
- `start_trading_bot.bat` - Full startup with all checks
- `quick_start.bat` - Simplified launcher
- `stop_trading_bot.bat` - Stop all services

## 📋 What Each Script Does

### `start_trading_bot.bat`
- ✅ Checks if Docker containers are running
- ✅ Starts PostgreSQL and Redis if needed
- ✅ Verifies Python dependencies
- ✅ Launches FastAPI server in a separate window
- ✅ Opens dashboard in your default browser
- ✅ Shows project folder when done

### `stop_trading_bot.bat`
- 🛑 Terminates Python FastAPI server
- 🛑 Stops Docker containers
- 🛑 Clean shutdown of all services

### `quick_start.bat`
- 🚀 Simple wrapper that calls the main startup script

## 🌐 Access Points

Once started, you can access:

| Service | URL | Description |
|---------|-----|-------------|
| **Dashboard** | http://localhost:8000/dashboard | Main trading interface |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |
| **Health Check** | http://localhost:8000/health | System status |
| **Root API** | http://localhost:8000 | Basic API info |

## 🔧 Troubleshooting

### If the shortcut doesn't work:
1. Make sure Docker Desktop is running
2. Check that Python is installed at the expected path
3. Run `start_trading_bot.bat` directly to see error messages

### If containers fail to start:
1. Open Docker Desktop
2. Check if ports 5432 (PostgreSQL) and 6379 (Redis) are available
3. Try stopping and restarting Docker

### If Python server fails:
1. Check if port 8000 is already in use
2. Verify all dependencies are installed
3. Run the startup script from command line to see errors

## 🔄 Manual Commands (if needed)

If you prefer command line control:

```bash
# Start everything
docker-compose up -d db redis
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Stop everything
docker-compose down
# Kill Python processes manually
```

## 📊 Features Available

- **Live Trading**: Start/stop bot, monitor positions
- **Backtesting**: Test strategies with historical data
- **Analysis**: Market scanning and technical analysis
- **Portfolio**: Real-time position tracking
- **Settings**: Configure trading parameters

## 🎯 Quick Tips

1. **First Time Setup**: The desktop shortcut will handle everything automatically
2. **Daily Use**: Just double-click the desktop shortcut
3. **Clean Shutdown**: Use `stop_trading_bot.bat` when done
4. **Monitoring**: Keep an eye on the API server window for logs
5. **Updates**: If you update the code, the server will auto-reload

## 🆘 Getting Help

- Check the API documentation at http://localhost:8000/docs
- View server logs in the FastAPI window
- Monitor Docker containers with `docker-compose ps`
- Check application logs in the dashboard

---

**Happy Trading! 🚀📈**