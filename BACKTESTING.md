# Backtesting Module

A comprehensive backtesting engine for testing the Velez gap trading strategy using historical Alpaca data.

## 🎯 Features

### Core Functionality
- **Historical Data Simulation**: Uses real Alpaca 1-minute bars for accurate simulation
- **Realistic Position Management**: Implements proper entry/exit logic with stop-losses and targets
- **Commission & Slippage**: Models real trading costs (configurable commission + slippage)
- **Risk Management**: 1% risk per trade with position sizing based on stop-loss distance
- **Performance Metrics**: 20+ comprehensive metrics including Sharpe ratio, max drawdown, profit factor

### Strategy Implementation
- **Gap Detection**: Identifies significant gaps (≥1.5%) from previous day close
- **VWAP Pullback**: Waits for pullback to VWAP before entry
- **Reversal Patterns**: Detects bottom tail (BT) patterns for entry confirmation
- **Position Management**: Automatic stop-loss and target management
- **End-of-Day Exits**: Closes all positions at 3:55 PM ET

## 🚀 Quick Start

### 1. API Endpoints

#### Run Full Backtest
```bash
POST /api/backtesting/run
```

Request body:
```json
{
  "symbols": ["AAPL", "MSFT", "TSLA"],
  "start_date": "2024-01-01",
  "end_date": "2024-01-31", 
  "initial_capital": 100000.0,
  "commission_per_share": 0.005
}
```

#### Quick Backtest
```bash
POST /api/backtesting/quick-run?symbols=AAPL&symbols=MSFT&days=30
```

#### Get Results
```bash
GET /api/backtesting/results/summary     # Summary metrics
GET /api/backtesting/results/detailed    # Full trade log + equity curve
```

### 2. Python Usage

```python
from app.services.backtesting import backtesting_engine
from datetime import datetime, timedelta

# Run backtest
results = await backtesting_engine.run_backtest(
    symbols=['AAPL', 'MSFT'],
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 1, 31),
    initial_capital=100000.0
)

if results['success']:
    metrics = results['metrics']
    print(f"Total trades: {metrics.total_trades}")
    print(f"Win rate: {metrics.win_rate:.1f}%")
    print(f"Total return: {metrics.total_pnl:.2f}")
```

## 📊 Performance Metrics

### Trading Statistics
- **Total Trades**: Number of completed trades
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profit ÷ gross loss
- **Average Win/Loss**: Average profit and loss per trade
- **Consecutive Wins/Losses**: Maximum consecutive streaks

### Risk Metrics
- **Max Drawdown**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted return (annualized)
- **Sortino Ratio**: Downside deviation-adjusted return
- **Calmar Ratio**: Return ÷ max drawdown

### Financial Metrics
- **Total P&L**: Net profit/loss after commissions
- **Total Return %**: Percentage return on capital
- **Total Commission**: All trading costs
- **Gross Profit/Loss**: Before commission totals

## 🔧 Configuration

### Default Settings
```python
initial_capital = 100000.0        # Starting capital
commission_per_share = 0.005      # $0.005 per share
min_commission = 1.0              # Minimum $1 per trade
slippage_pct = 0.001              # 0.1% slippage
max_positions = 5                 # Maximum concurrent positions
risk_per_trade = 0.01             # Risk 1% of equity per trade
```

### Strategy Parameters
```python
min_gap_percent = 1.5             # Minimum gap to consider
vwap_proximity_pct = 0.02         # Within 2% of VWAP
tail_threshold = 0.3              # 30% minimum tail for entry
```

## 📈 Sample Results

```
📊 BACKTEST RESULTS (AAPL, MSFT - 30 days)
================================================
Initial Capital: $100,000.00
Final Equity: $102,450.00
Total Return: +2.45%

Trading Performance:
- Total Trades: 23
- Winning Trades: 15 (65.2%)
- Losing Trades: 8 (34.8%)
- Profit Factor: 1.85
- Average Win: $425.50
- Average Loss: -$285.20

Risk Metrics:
- Max Drawdown: -3.2%
- Sharpe Ratio: 1.42
- Sortino Ratio: 2.18

Costs:
- Total Commission: $184.50
```

## 🎛️ API Presets

### Symbol Presets
- **Gap Favorites**: Popular gap trading stocks
- **S&P 500 Sample**: Representative large-cap stocks
- **Tech Stocks**: Technology sector focus
- **Volatile Stocks**: Higher volatility names
- **Blue Chips**: Large, stable companies

### Date Presets
- **Last 30 Days**: Recent performance
- **Last Quarter**: 3-month analysis
- **Year to Date**: Current year performance
- **Last 12 Months**: Full year analysis
- **2023/2022**: Historical years

## 🔍 Advanced Usage

### Custom Strategy Testing
```python
# Test with different parameters
results = await backtesting_engine.run_backtest(
    symbols=['TSLA', 'AMD', 'NVDA'],  # High volatility
    start_date=datetime(2024, 6, 1),
    end_date=datetime(2024, 8, 31),   # Summer period
    initial_capital=50000.0,          # Smaller account
    commission_per_share=0.003        # Lower commission
)
```

### Batch Testing
```python
# Test multiple periods
periods = [
    ('Q1 2024', datetime(2024, 1, 1), datetime(2024, 3, 31)),
    ('Q2 2024', datetime(2024, 4, 1), datetime(2024, 6, 30)),
    ('Q3 2024', datetime(2024, 7, 1), datetime(2024, 9, 30))
]

for name, start, end in periods:
    results = await backtesting_engine.run_backtest(['AAPL'], start, end)
    if results['success']:
        metrics = results['metrics']
        print(f"{name}: {metrics.win_rate:.1f}% win rate, {metrics.total_pnl:.2f} P&L")
```

## ⚠️ Limitations

### Data Limitations
- **Market Hours Only**: 9:30 AM - 4:00 PM ET simulation
- **1-minute Bars**: Limited to 1-minute resolution
- **No Pre/After Hours**: Regular session only
- **Historical Data**: Subject to Alpaca data availability

### Strategy Limitations
- **Gap Strategy Only**: Focused on gap pullback setups
- **Long Only**: No short selling implemented
- **Single Timeframe**: 1-minute entry/exit logic
- **Simplified Execution**: Perfect fills assumed at specified prices

### Technical Limitations
- **Memory Usage**: Large datasets may require optimization
- **Processing Time**: Detailed simulation can be slow
- **API Rate Limits**: Subject to Alpaca API throttling

## 🛠️ Development

### Testing
```bash
# Run test suite
python test_backtesting.py

# Test specific scenarios
python -c "
import asyncio
from app.services.backtesting import backtesting_engine
from datetime import datetime, timedelta

async def test():
    results = await backtesting_engine.run_backtest(['AAPL'], 
        datetime.now() - timedelta(days=30), datetime.now())
    print(f'Success: {results[\"success\"]}')

asyncio.run(test())
"
```

### Extending the Engine
```python
# Add custom exit conditions
async def custom_exit_check(position, current_bar, df):
    # Custom logic here
    return should_exit, exit_reason

# Modify strategy parameters
backtesting_engine.min_gap_percent = 2.0  # Higher gap requirement
backtesting_engine.max_positions = 3      # Fewer concurrent positions
```

## 📚 Resources

### API Documentation
- Swagger UI: `http://localhost:8000/docs`
- Backtesting endpoints: `/api/backtesting/*`

### Log Analysis
```bash
# Monitor backtesting logs
tail -f logs/backtesting.log

# Check for specific patterns
grep "Gap setup" logs/backtesting.log
```

### Performance Analysis
```python
# Analyze equity curve
import matplotlib.pyplot as plt

equity_curve = backtesting_engine.equity_curve
times = [t for t, e in equity_curve]
values = [e for t, e in equity_curve]

plt.plot(times, values)
plt.title('Equity Curve')
plt.show()
```

## 🤝 Contributing

1. Test new features with `test_backtesting.py`
2. Add comprehensive metrics for new strategies
3. Maintain backward compatibility with API
4. Document performance characteristics
5. Include realistic cost modeling

---

*Built with real Alpaca data for accurate backtesting of the Oliver Velez gap trading methodology.*