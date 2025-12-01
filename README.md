# Trading Bot - Automated Stock Trading System

A sophisticated, fully-automated trading bot built with Python and FastAPI that implements a proprietary gap trading strategy with MACD, Volume, and RSI confirmation.

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## ✨ Features

### Core Trading Features
- **Automated Gap Trading** - Detects and trades stocks with significant overnight gaps (0.75% - 20%)
- **MACD with Divergence Detection** - Advanced momentum analysis with 20-bar divergence lookback
- **Volume Confirmation** - Requires 1.5x average volume for entry validation (CRITICAL)
- **RSI Filtering** - Prevents entries in extreme overbought/oversold conditions
- **Dollar-Based Trailing Stops** - Intelligent profit protection with $15/$50/$100 tiers
- **Real-time Market Scanning** - Continuous monitoring of 350+ S&P 500 and growth stocks
- **Adaptive Risk Management** - Position sizing based on ATR with minimum stop distances
- **Whipsaw Prevention** - 60-minute cooldown after stop outs, 30-minute after any exit
- **Market Open Delay** - Waits 30 minutes after open to avoid volatility spikes

### Advanced Stop Loss System
- **Minimum Stop Distance** - $0.30 or 1.2% of price (prevents noise stops)
- **1.5x ATR Initial Stop** - Proper breathing room for positions
- **Quick Profit Protection** - $20 profit in 10 minutes → immediate breakeven
- **Progressive Profit Lock** - $15, $50, $100+ tiers with $30 buffer
- **2.5x Risk/Reward Targets** - Optimized profit targets

### Strategy Features
- **Proprietary Gap + MACD Strategy** - Research-backed 73-74% win rate combination
- **Dynamic Trade Limits** - 10 trades when PnL ≤ 0, 20 trades when profitable
- **Extended Trading Hours** - Trades until 2 PM EST (closes all by 3:50 PM)
- **Smart Position Management** - Only counts bot-managed positions (ignores manual trades)

### Analytics & Monitoring
- **Professional Dashboard** - Modern dark-themed UI with real-time updates
- **Trade History Analytics** - Win rate, R-multiples, profit factor, Sharpe ratio
- **Backtesting Engine** - Test strategies on historical data with realistic daily scanning
- **Order History** - Track all orders (filled, pending, cancelled)
- **Live Position Monitoring** - Real-time P/L tracking with trailing stop visualization

### Technical Features
- **RESTful API** - Complete API for all bot operations
- **Docker Support** - Containerized deployment with PostgreSQL and Redis
- **Database Persistence** - Trades, positions, and analytics stored in PostgreSQL
- **Redis Caching** - Fast market data access and session management
- **Beautiful Dashboards** - Multiple web-based UIs for monitoring
- **Comprehensive Logging** - Detailed analysis logs for debugging

## 📊 Dashboards

### Main Dashboard
Access at: `http://localhost:8000/dashboard`
- Active positions with live P/L
- Today's trades
- Account summary and daily P/L
- Bot status and controls
- Quick position close buttons

### Trade History Dashboard
Access at: `http://localhost:8000/trade-history`
- Complete trade history with filters
- P/L analytics (total, win rate, R-multiples)
- Best/worst trades
- Daily P/L breakdown
- Order history viewer

### Backtesting Dashboard
Access at: `http://localhost:8000/dashboard/backtesting`
- Run historical backtests
- View equity curves
- Analyze trade-by-trade results
- Compare strategy performance

## 🛠 Technology Stack

**Backend:**
- Python 3.12+
- FastAPI - Modern async web framework
- SQLAlchemy - Database ORM
- Alpaca Trade API - Broker integration
- Pandas & NumPy - Data analysis
- TA-Lib - Technical indicators

**Database & Cache:**
- PostgreSQL - Primary database
- Redis - Market data caching

**Frontend:**
- HTML/CSS/JavaScript
- Responsive design
- Real-time updates via API polling

**Deployment:**
- Docker & Docker Compose
- Uvicorn ASGI server

## 📥 Installation

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

## 🚀 Usage

### Starting the Bot

1. **Access the dashboard** at `http://localhost:8000/dashboard`
2. **Click "Start Bot"** to begin automated trading
3. **Monitor positions** in real-time

### API Endpoints

**Bot Control:**
- `POST /api/v1/bot/start` - Start the trading bot
- `POST /api/v1/bot/stop` - Stop the trading bot
- `POST /api/v1/bot/pause` - Pause trading
- `POST /api/v1/bot/resume` - Resume trading
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

**Settings:**
- `GET /api/v1/settings/current` - Get current settings
- `PUT /api/v1/settings/update` - Update settings

### Configuration

Key configuration options in `.env`:

```env
# Trading Parameters
MAX_POSITION_SIZE=10000          # Maximum $ per position
RISK_PER_TRADE=100              # $ to risk per trade
MAX_DAILY_LOSS=600              # Stop trading after this loss
MAX_CONCURRENT_POSITIONS=5      # Maximum concurrent positions

# Strategy Settings (Proprietary Gap + MACD)
MIN_GAP_PERCENT=0.75            # Minimum gap size
MAX_GAP_PERCENT=20.0            # Maximum gap size
MIN_VOLUME_RATIO=1.5            # CRITICAL: Must be 1.5x average volume
ATR_STOP_MULTIPLIER=1.5         # Initial stop distance (1.5x ATR)

# Trailing Stop Settings (Dollar-Based)
BREAKEVEN_PROFIT_THRESHOLD=15   # Move to breakeven at $15 profit
QUICK_PROFIT_THRESHOLD=20       # Quick profit protection at $20 in 10min
TIER1_PROFIT_THRESHOLD=50       # Lock $50 at $80 profit
TIER2_PROFIT_THRESHOLD=100      # Lock $100 at $130 profit
STOP_OUT_COOLDOWN=1200          # 20-minute cooldown after stop out

# Trading Hours
TRADING_CUTOFF_HOUR=14          # No new trades after 2 PM EST
POSITION_CLOSE_HOUR=15          # Close all positions at 3:50 PM EST
POSITION_CLOSE_MINUTE=50

# Logging
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR
```

## 📈 Trading Strategy

### Proprietary Gap + MACD + Volume + RSI Strategy

Based on research showing 73-74% win rate for this indicator combination.

**Entry Rules (LONG):**
1. ✅ Gap up detected (0.75% - 20%)
2. ✅ Volume > 1.5x average (CRITICAL - cumulative daily volume check)
3. ✅ RSI < 70 (not overbought)
4. ✅ MACD bullish crossover OR bullish divergence (20-bar lookback)
5. ✅ Time: Before 2 PM EST

**Entry Rules (SHORT):**
1. ✅ Gap down detected (0.75% - 20%)
2. ✅ Volume > 1.5x average (CRITICAL - cumulative daily volume check)
3. ✅ RSI > 30 (not oversold)
4. ✅ MACD bearish crossover OR bearish divergence (20-bar lookback)
5. ✅ Time: Before 2 PM EST

**Exit Rules:**

**Initial Stop Loss:**
- Based on 1.5x ATR with enforced minimums
- Minimum $0.30 or 1.2% of price (whichever is larger)
- Prevents micro-stops from normal market noise

**Dollar-Based Trailing Stops:**
- **$15 profit** → Move stop to breakeven (protect entry)
- **$20 profit in 10 min** → Immediate breakeven (quick profit protection)
- **$80 profit** → Lock $50 (with $30 buffer)
- **$130 profit** → Lock $100 (with $30 buffer)
- **Every +$50** → Continue moving up with $30 buffer

**Profit Targets:**
- Target = Entry ± (2.5x initial stop distance)
- Aggressive target for strong setups: 3.5x

**Risk Management:**
- Position sizing based on 1.5x ATR
- Maximum 5 concurrent bot-managed positions
- Daily loss limit protection ($600 default)
- 20-minute cooldown after stop outs (whipsaw prevention)
- Automatic end-of-day position closure (3:50 PM EST)
- Dynamic trade limits: 10 when losing, 20 when profitable

## 🧪 Backtesting

Run backtests via the dashboard or API:

```bash
curl -X POST http://localhost:8000/api/v1/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "proprietary",
    "symbols": ["AAPL", "MSFT", "GOOGL"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "initial_capital": 100000,
    "use_daily_scanner": true
  }'
```

**Backtest Features:**
- Realistic daily market scanning (simulates real-world discovery)
- Proper commission modeling ($0.005/share, $1 minimum)
- Slippage simulation (0.1%)
- Full trailing stop logic testing
- Trade-by-trade breakdown
- Equity curve visualization

**Backtest Results Include:**
- Total return and CAGR
- Sharpe ratio
- Win rate and profit factor
- Maximum drawdown
- Average R-multiple
- Trade duration statistics
- Best/worst trades

## 📊 Performance Metrics

The bot tracks comprehensive performance metrics:

- **Total P/L** - Overall profit/loss
- **Daily P/L** - Today's realized profit/loss
- **Win Rate** - Percentage of winning trades
- **Average R-Multiple** - Risk-adjusted returns
- **Profit Factor** - Gross profit / Gross loss
- **Sharpe Ratio** - Risk-adjusted performance
- **Maximum Drawdown** - Largest peak-to-trough decline
- **Trade Duration** - Average holding period
- **Best/Worst Trades** - Highest winners and losers

## 🔒 Security Best Practices

1. **Never commit `.env` files** - Contains sensitive API keys
2. **Use paper trading first** - Test with simulated money (https://paper-api.alpaca.markets)
3. **Enable 2FA on Alpaca** - Protect your account
4. **Monitor positions regularly** - Don't rely solely on automation
5. **Set conservative risk limits** - Start with small position sizes ($100/trade)
6. **Keep API keys secure** - Use environment variables only, never hardcode
7. **Review logs daily** - Check for errors or unusual behavior

## 🔧 Troubleshooting

### Bot won't start
- Check Docker containers are running: `docker-compose ps`
- Verify Alpaca API keys in `.env`
- Check logs: `docker-compose logs`
- Ensure Python 3.12+ is installed

### No trades being placed
- Verify market is open (9:30 AM - 4:00 PM ET)
- Check that it's before 2 PM EST (trading cutoff)
- Review bot logs for entry conditions not met
- Most common: Volume < 1.5x average (strict quality filter)
- Ensure account has sufficient buying power
- Check watchlist has active stocks

### Positions being stopped out too quickly
- This has been fixed! Previous version had 0.9x ATR stops (too tight)
- Current version uses 1.5x ATR with minimum $0.30 or 1.2% distance
- Check logs for stop upgrade messages
- Verify trailing stops are working: look for "💰 Upgrading stop" messages

### Database connection failed
- Restart Docker containers: `docker-compose restart`
- Check PostgreSQL is running: `docker-compose ps db`
- Verify database credentials in `.env`
- Check port 5432 is not in use by another service

### API errors
- Check Alpaca account status at https://app.alpaca.markets
- Verify API key permissions (trading, data, account)
- Ensure using correct base URL (paper vs live)
- Check rate limits (200 requests/minute for market data)

## 🏗 Development

### Project Structure
```
trading-bot/
├── app/
│   ├── api/                    # API endpoints
│   │   ├── bot_control.py     # Bot start/stop/status
│   │   ├── trade_history.py   # Trade history & analytics
│   │   ├── backtesting.py     # Backtesting API
│   │   ├── settings.py        # Configuration API
│   │   └── monitoring.py      # Health checks
│   ├── core/                   # Core functionality
│   │   ├── config.py          # Settings management
│   │   ├── database.py        # Database connection
│   │   └── cache.py           # Redis caching
│   ├── models/                 # Database models
│   │   ├── trade.py           # Trade model
│   │   └── position.py        # Position model
│   ├── services/               # Business logic
│   │   ├── trading_bot.py     # Main bot engine
│   │   ├── order_manager.py   # Order execution
│   │   ├── risk_manager.py    # Risk management
│   │   ├── market_data.py     # Market data fetching
│   │   ├── portfolio.py       # Portfolio tracking
│   │   ├── market_scanner.py  # Stock scanning
│   │   └── backtesting.py     # Backtesting engine
│   ├── strategies/             # Trading strategies
│   │   ├── proprietary_strategy.py  # Gap + MACD strategy
│   │   └── indicators.py      # Technical indicators
│   ├── static/                 # Frontend files
│   │   ├── dashboard.html     # Main dashboard
│   │   └── trade_history.html # Trade history UI
│   └── main.py                 # Application entry point
├── docker-compose.yml          # Docker configuration
├── requirements.txt            # Python dependencies
├── .env.example                # Environment template
├── README.md                   # This file
└── start_trading_bot.bat       # Windows launcher
```

### Adding New Features

**To add a new indicator:**
1. Add calculation method to `app/strategies/indicators.py`
2. Update strategy logic in `proprietary_strategy.py`
3. Test with backtesting

**To modify stop loss logic:**
1. Edit `upgrade_to_trailing_stop()` in `proprietary_strategy.py`
2. Adjust thresholds in `__init__()` method
3. Test with small position sizes first

**To change entry rules:**
1. Modify `_analyze_entry_conditions()` in `proprietary_strategy.py`
2. Update gap detection in `_detect_gap()`
3. Adjust RSI/MACD thresholds

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_proprietary_strategy.py

# Run with coverage
pytest --cov=app tests/
```

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

**Guidelines:**
- Follow PEP 8 style guide
- Add docstrings to all functions
- Include unit tests for new features
- Update documentation

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

**This trading bot is for educational and research purposes only.**

- Trading stocks involves substantial risk of loss
- Past performance does not guarantee future results
- Never trade with money you cannot afford to lose
- This software is provided "as is" without warranty of any kind
- The authors are not responsible for any financial losses incurred
- Automated trading can result in significant losses if not properly monitored

**Always:**
- Start with paper trading for at least 2-4 weeks
- Understand the strategy completely before using real money
- Monitor the bot regularly during trading hours
- Set appropriate risk limits for your account size
- Consult a financial advisor before live trading
- Keep sufficient buying power in your account
- Review all trades at end of day

## 🆘 Support

- **Documentation**: See markdown files in repository root
- **Issues**: https://github.com/ariasgon/trading-bot/issues
- **Discussions**: https://github.com/ariasgon/trading-bot/discussions

## 🙏 Acknowledgments

- [Alpaca Markets](https://alpaca.markets/) - Commission-free trading API
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- Technical analysis research papers on gap trading effectiveness
- Trading community for strategy feedback and testing

## 📚 Additional Resources

### Documentation
- [PROPRIETARY_STRATEGY_DOCUMENTATION.md](PROPRIETARY_STRATEGY_DOCUMENTATION.md) - Complete strategy guide
- [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) - Get started quickly
- [BACKTESTING.md](BACKTESTING.md) - Backtesting guide
- [REALISTIC_BACKTESTING.md](REALISTIC_BACKTESTING.md) - Advanced backtesting features

### External Resources
- [Alpaca API Documentation](https://alpaca.markets/docs/)
- [MACD Indicator Guide](https://www.investopedia.com/terms/m/macd.asp)
- [Volume Analysis](https://www.investopedia.com/articles/technical/02/010702.asp)
- [Risk Management Best Practices](https://www.investopedia.com/articles/trading/09/risk-management.asp)

## 📝 Recent Updates

### December 2025 - Anti-Churning & Stop Loss Improvements
- ✅ Widened trailing stop distance to 100% of initial stop (was 75% - too tight)
- ✅ Added minimum trail distance: $1.50 or 2.5% of price
- ✅ Implemented 30-minute cooldown after ANY trade exit (prevents churning)
- ✅ Added 30-minute market open delay (avoids opening volatility)
- ✅ Added duplicate order prevention (5-minute pending order lockout)
- ✅ Expanded stock universe to full S&P 500 (~350 symbols + growth stocks)
- ✅ Fixed issue causing multiple entries on same symbol within minutes

### October 2025 - Major Stop Loss Overhaul
- ✅ Fixed critical stop loss issues (increased from 0.9x to 1.5x ATR)
- ✅ Implemented minimum stop distances ($0.30 or 1.2% of price)
- ✅ Added dollar-based trailing stops with progressive tiers
- ✅ Lowered breakeven threshold from $30 to $15
- ✅ Added quick profit protection ($20 in 10 min → breakeven)
- ✅ Implemented 20-minute whipsaw prevention cooldown
- ✅ Fixed position counting to ignore manual positions
- ✅ Added dynamic trade limits (10 vs 20 based on daily P/L)
- ✅ Extended trading hours to 2 PM EST
- ✅ Removed old Velez strategy, consolidated to proprietary only

---

**Built with ❤️ by the Trading Bot Team**

*Last updated: December 1, 2025*
