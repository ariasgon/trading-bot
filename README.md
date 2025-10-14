# Trading Bot - Automated Stock Trading System

A sophisticated, fully-automated trading bot built with Python and FastAPI that implements gap trading strategies with Ichimoku Cloud indicators, RSI confirmation, and machine learning enhancements.

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## =€ Features

### Core Trading Features
- **Automated Gap Trading** - Detects and trades stocks with significant overnight gaps (0.75% - 8%)
- **Ichimoku Cloud Analysis** - Uses full Ichimoku indicator suite for trend confirmation
- **RSI Filtering** - Prevents entries in overbought/oversold conditions
- **Bracket Orders** - Automatic stop loss and take profit orders
- **Real-time Market Scanning** - Continuous monitoring of 15+ symbols
- **Risk Management** - Position sizing based on account equity and ATR

### Strategy Implementations
- **Proprietary Gap Strategy** - Gap + Ichimoku + RSI combination
- **Velez Strategy** - Based on Oliver Velez methodology
- **Ichimoku Strategy** - Pure Ichimoku cloud trading
- **ML-Enhanced Entries** - Machine learning model for trade quality scoring

### Analytics & Monitoring
- **Trade History Dashboard** - View all historical trades with P/L
- **Real-time P/L Analytics** - Win rate, R-multiples, profit factor
- **Backtesting Engine** - Test strategies on historical data
- **Order History** - Track all orders (filled, pending, cancelled)
- **Live Position Monitoring** - Real-time position tracking with unrealized P/L

### Technical Features
- **RESTful API** - Complete API for all bot operations
- **Docker Support** - Containerized deployment with PostgreSQL and Redis
- **Database Persistence** - Trades, positions, and analytics stored in PostgreSQL
- **Redis Caching** - Fast data access and session management
- **Beautiful Dashboards** - Multiple web-based UIs for monitoring

## =Ê Dashboards

### Main Dashboard
Access at: `http://localhost:8000/dashboard`
- Active positions with live P/L
- Today's trades
- Account summary
- Bot status and controls
- Backtesting interface

### Trade History Dashboard
Access at: `http://localhost:8000/dashboard/history`
- Complete trade history with filters
- P/L analytics (total, win rate, R-multiples)
- Best/worst trades
- Daily P/L breakdown
- Order history viewer

## =à Technology Stack

**Backend:**
- Python 3.12+
- FastAPI - Modern web framework
- SQLAlchemy - Database ORM
- Alpaca Trade API - Broker integration
- Pandas & NumPy - Data analysis
- Scikit-learn - Machine learning

**Database & Cache:**
- PostgreSQL - Primary database
- Redis - Caching and sessions

**Frontend:**
- HTML/CSS/JavaScript
- Responsive design
- Real-time updates

**Deployment:**
- Docker & Docker Compose
- Uvicorn ASGI server

## =æ Installation

### Prerequisites
- Python 3.12 or higher
- Docker Desktop (for PostgreSQL and Redis)
- Alpaca Trading Account (paper or live)

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/ariasgon/trading-bot.git
cd trading-bot
```

2. **Set up environment variables**
```bash
cp .env.example .env
```

Edit `.env` and add your Alpaca credentials:
```env
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Use paper trading
```

3. **Start Docker containers**
```bash
docker-compose up -d
```

4. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

5. **Run the bot**

**Option A - Using the launcher (Windows):**
```bash
start_trading_bot.bat
```

**Option B - Manual start:**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

6. **Access the dashboard**
```
http://localhost:8000/dashboard
```

## <¯ Usage

### Starting the Bot

1. **Access the dashboard** at `http://localhost:8000/dashboard`
2. **Click "Start Bot"** to begin automated trading
3. **Monitor positions** in real-time

### API Endpoints

**Bot Control:**
- `POST /api/v1/bot/start` - Start the trading bot
- `POST /api/v1/bot/stop` - Stop the trading bot
- `GET /api/v1/bot/status` - Get bot status
- `GET /api/v1/bot/watchlist` - View current watchlist

**Trading:**
- `GET /api/v1/bot/active-positions` - Get active positions
- `POST /api/v1/bot/close-position/{symbol}` - Close a specific position
- `POST /api/v1/bot/close-all-positions` - Close all positions

**Trade History:**
- `GET /api/v1/history/trades` - Get historical trades (with filters)
- `GET /api/v1/history/analytics/summary` - P/L analytics
- `GET /api/v1/history/analytics/daily` - Daily P/L breakdown
- `GET /api/v1/history/orders/recent` - Recent orders

**Backtesting:**
- `POST /api/v1/backtest/run` - Run a backtest
- `GET /api/v1/backtest/results/{id}` - Get backtest results

### Configuration

Key configuration options in `.env`:

```env
# Trading Parameters
MAX_POSITION_SIZE=10000      # Maximum $ per position
RISK_PER_TRADE=100          # $ to risk per trade
MAX_DAILY_LOSS=500          # Stop trading after this loss
MAX_POSITIONS=5             # Maximum concurrent positions

# Strategy Settings
MIN_GAP_PERCENT=0.75        # Minimum gap size
MAX_GAP_PERCENT=8.0         # Maximum gap size
USE_ML_SCORING=true         # Enable ML trade scoring
ML_MINIMUM_SCORE=0.40       # Minimum ML confidence

# Logging
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
```

## =È Trading Strategies

### Proprietary Gap Strategy

**Entry Rules (LONG):**
1. Gap up detected (0.75% - 8%)
2. Price above or inside Ichimoku cloud
3. Tenkan-sen > Kijun-sen (or bullish TK cross)
4. RSI < 70 (not overbought)

**Entry Rules (SHORT):**
1. Gap down detected (0.75% - 8%)
2. Price below or inside Ichimoku cloud
3. Tenkan-sen < Kijun-sen (or bearish TK cross)
4. RSI > 30 (not oversold)

**Exit Rules:**
- Stop Loss: Entry ± (2 × ATR)
- Target 1: Kijun-sen (50% position)
- Target 2: Cloud edge or RSI extreme (50% position)

**Risk Management:**
- Position sizing based on ATR
- Maximum 5 concurrent positions
- Daily loss limit protection
- Automatic end-of-day position closure

## >ê Backtesting

Run backtests via the dashboard or API:

```bash
curl -X POST http://localhost:8000/api/v1/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "proprietary",
    "symbols": ["AAPL", "MSFT", "GOOGL"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 10000
  }'
```

**Backtest Results Include:**
- Total return and Sharpe ratio
- Win rate and profit factor
- Maximum drawdown
- Trade-by-trade breakdown
- Equity curve chart

## =Ê Performance Metrics

The bot tracks comprehensive performance metrics:

- **Total P/L** - Overall profit/loss
- **Win Rate** - Percentage of winning trades
- **Average R-Multiple** - Risk-adjusted returns
- **Profit Factor** - Avg winner / Avg loser ratio
- **Sharpe Ratio** - Risk-adjusted performance
- **Maximum Drawdown** - Largest peak-to-trough decline
- **Trade Duration** - Average holding period

## = Security Best Practices

1. **Never commit `.env` files** - Contains sensitive API keys
2. **Use paper trading first** - Test with simulated money
3. **Enable 2FA on Alpaca** - Protect your account
4. **Monitor positions regularly** - Don't rely solely on automation
5. **Set conservative risk limits** - Start with small position sizes
6. **Keep API keys secure** - Use environment variables only

## = Troubleshooting

### Bot won't start
- Check Docker containers are running: `docker-compose ps`
- Verify Alpaca API keys in `.env`
- Check logs: `docker-compose logs`

### No trades being placed
- Verify market is open (9:30 AM - 4:00 PM ET)
- Check watchlist has stocks with gaps
- Review bot logs for entry conditions
- Ensure account has sufficient buying power

### Database connection failed
- Restart Docker containers: `docker-compose restart`
- Check PostgreSQL is running: `docker-compose ps db`
- Verify database credentials in `.env`

### API errors
- Check Alpaca account status
- Verify API key permissions
- Ensure using correct base URL (paper vs live)

## =Ý Development

### Project Structure
```
trading-bot/
   app/
      api/              # API endpoints
         bot_control.py
         trade_history.py
         backtesting.py
      core/             # Core functionality
         config.py
         database.py
         cache.py
      models/           # Database models
         trade.py
         position.py
      services/         # Business logic
         trading_bot.py
         order_manager.py
         risk_manager.py
         market_data.py
      strategies/       # Trading strategies
         proprietary_strategy.py
         velez_strategy.py
         ichimoku_strategy.py
      static/           # Frontend files
         dashboard.html
         trade_history.html
      main.py           # Application entry point
   docker-compose.yml    # Docker configuration
   requirements.txt      # Python dependencies
   .env.example          # Environment template
   README.md            # This file
```

### Adding New Strategies

1. Create a new file in `app/strategies/`
2. Implement `scan_for_opportunities()` method
3. Define entry/exit logic
4. Register in `trading_bot.py`

Example:
```python
class MyStrategy:
    async def scan_for_opportunities(self, symbols: List[str]) -> List[TradeSetup]:
        # Your logic here
        pass
```

### Running Tests
```bash
pytest tests/
```

## > Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## =Ä License

This project is licensed under the MIT License - see the LICENSE file for details.

##   Disclaimer

**This trading bot is for educational and research purposes only.**

- Trading stocks involves substantial risk of loss
- Past performance does not guarantee future results
- Never trade with money you cannot afford to lose
- This software is provided "as is" without warranty
- The authors are not responsible for any financial losses

**Always:**
- Start with paper trading
- Understand the strategies before using
- Monitor the bot regularly
- Set appropriate risk limits
- Consult a financial advisor

## =Þ Support

- **Documentation**: See `/docs` folder
- **Issues**: https://github.com/ariasgon/trading-bot/issues
- **Discussions**: https://github.com/ariasgon/trading-bot/discussions

## =O Acknowledgments

- [Alpaca Markets](https://alpaca.markets/) - Trading API
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Oliver Velez](https://www.velez-capital.com/) - Trading methodology inspiration
- Ichimoku Kinko Hyo - Technical analysis system

## =Ú Additional Resources

- [Alpaca API Documentation](https://alpaca.markets/docs/)
- [Ichimoku Cloud Tutorial](https://www.investopedia.com/terms/i/ichimoku-cloud.asp)
- [Oliver Velez Trading Strategies](https://www.youtube.com/user/OliverVelezTrades)
- [Risk Management Best Practices](https://www.investopedia.com/articles/trading/09/risk-management.asp)

---

**Built with d by the Trading Bot Team**

*Last updated: October 2025*
