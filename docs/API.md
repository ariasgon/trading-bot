# Trading Bot API Documentation

Complete API reference for the Trading Bot application.

**Base URL:** `http://localhost:8000`

## Authentication

Currently, the API does not require authentication for local development. For production deployments, implement proper authentication mechanisms.

---

## Bot Control Endpoints

### Start Trading Bot

Start the automated trading bot.

**Endpoint:** `POST /api/v1/bot/start`

**Response:**
```json
{
  "status": "starting",
  "message": "Trading bot is starting...",
  "timestamp": "2025-10-14T10:00:00"
}
```

### Stop Trading Bot

Stop the trading bot and halt all automated trading.

**Endpoint:** `POST /api/v1/bot/stop`

**Response:**
```json
{
  "status": "stopped",
  "message": "Trading bot stopped successfully",
  "timestamp": "2025-10-14T10:00:00"
}
```

### Get Bot Status

Retrieve current bot status and statistics.

**Endpoint:** `GET /api/v1/bot/status`

**Response:**
```json
{
  "bot_status": {
    "is_running": true,
    "is_trading_active": true,
    "watchlist_size": 15,
    "active_positions": 2,
    "trades_today": 5,
    "error_count": 0,
    "session_start": "2025-10-14T09:30:00",
    "last_scan": "2025-10-14T10:00:00",
    "last_analysis": "2025-10-14T10:00:00"
  },
  "timestamp": "2025-10-14T10:00:00"
}
```

### Get Watchlist

Retrieve current watchlist with gap data.

**Endpoint:** `GET /api/v1/bot/watchlist`

**Response:**
```json
{
  "watchlist": {
    "AAPL": {
      "symbol": "AAPL",
      "current_price": 150.50,
      "previous_close": 148.00,
      "gap_percent": 1.69,
      "gap_amount": 2.50
    }
  },
  "count": 15,
  "timestamp": "2025-10-14T10:00:00"
}
```

---

## Trading Endpoints

### Get Active Positions

Retrieve all currently active positions.

**Endpoint:** `GET /api/v1/bot/active-positions`

**Response:**
```json
{
  "active_positions": {
    "AAPL": {
      "symbol": "AAPL",
      "quantity": 100,
      "side": "long",
      "entry_price": 150.00,
      "current_price": 151.50,
      "market_value": 15150.00,
      "unrealized_pl": 150.00,
      "unrealized_plpc": 1.00,
      "cost_basis": 15000.00,
      "stop_loss": 148.00,
      "target_1": 152.00,
      "entry_time": "2025-10-14T09:35:00"
    }
  },
  "position_count": 1,
  "timestamp": "2025-10-14T10:00:00"
}
```

### Close Position

Close a specific position by symbol.

**Endpoint:** `POST /api/v1/bot/close-position/{symbol}`

**Parameters:**
- `symbol` (path): Stock symbol to close (e.g., "AAPL")

**Response:**
```json
{
  "status": "success",
  "message": "Position closed successfully",
  "symbol": "AAPL",
  "quantity_closed": 100,
  "exit_price": 151.50
}
```

### Close All Positions

Close all active positions.

**Endpoint:** `POST /api/v1/bot/close-all-positions`

**Response:**
```json
{
  "status": "success",
  "message": "All positions closed",
  "positions_closed": 3,
  "symbols": ["AAPL", "MSFT", "GOOGL"]
}
```

---

## Trade History Endpoints

### Get Trade History

Retrieve historical trades with optional filters.

**Endpoint:** `GET /api/v1/history/trades`

**Query Parameters:**
- `limit` (int, optional): Maximum trades to return (default: 100, max: 500)
- `offset` (int, optional): Number of trades to skip (default: 0)
- `symbol` (string, optional): Filter by symbol
- `strategy` (string, optional): Filter by strategy name
- `status` (string, optional): Filter by status (filled, pending, cancelled)
- `start_date` (string, optional): Start date (YYYY-MM-DD)
- `end_date` (string, optional): End date (YYYY-MM-DD)

**Example:**
```
GET /api/v1/history/trades?symbol=AAPL&limit=50&status=filled
```

**Response:**
```json
{
  "trades": [
    {
      "id": "uuid-here",
      "symbol": "AAPL",
      "side": "buy",
      "quantity": 100,
      "entry_price": 150.00,
      "exit_price": 152.00,
      "stop_loss": 148.00,
      "target_price": 153.00,
      "status": "filled",
      "realized_pnl": 200.00,
      "r_multiple": 2.0,
      "entry_time": "2025-10-14T09:35:00",
      "exit_time": "2025-10-14T14:20:00",
      "duration_minutes": 285,
      "is_winner": true,
      "strategy": "proprietary",
      "setup_type": "gap_long"
    }
  ],
  "total_count": 150,
  "limit": 50,
  "offset": 0,
  "timestamp": "2025-10-14T10:00:00"
}
```

### Get Analytics Summary

Get comprehensive P/L analytics and statistics.

**Endpoint:** `GET /api/v1/history/analytics/summary`

**Query Parameters:**
- `days` (int, optional): Number of days to analyze (default: 30, max: 365)
- `strategy` (string, optional): Filter by strategy

**Example:**
```
GET /api/v1/history/analytics/summary?days=30
```

**Response:**
```json
{
  "summary": {
    "total_trades": 50,
    "winning_trades": 32,
    "losing_trades": 18,
    "total_pnl": 2500.00,
    "win_rate": 64.00,
    "average_winner": 120.00,
    "average_loser": -60.00,
    "profit_factor": 2.00,
    "average_r_multiple": 1.5
  },
  "best_trade": {
    "symbol": "AAPL",
    "pnl": 500.00,
    "entry_time": "2025-10-01T10:00:00",
    "r_multiple": 5.0
  },
  "worst_trade": {
    "symbol": "TSLA",
    "pnl": -200.00,
    "entry_time": "2025-10-05T11:00:00",
    "r_multiple": -2.0
  },
  "by_strategy": {
    "proprietary": {
      "count": 35,
      "total_pnl": 1800.00,
      "winners": 24,
      "losers": 11,
      "win_rate": 68.57
    }
  },
  "top_symbols": [
    {
      "symbol": "AAPL",
      "count": 10,
      "total_pnl": 800.00,
      "winners": 7
    }
  ],
  "period_days": 30,
  "timestamp": "2025-10-14T10:00:00"
}
```

### Get Daily P/L

Get daily P/L breakdown for charting.

**Endpoint:** `GET /api/v1/history/analytics/daily`

**Query Parameters:**
- `days` (int, optional): Number of days to retrieve (default: 30, max: 90)

**Response:**
```json
{
  "daily_pnl": [
    {
      "date": "2025-10-14",
      "pnl": 250.00,
      "trades": 5,
      "winners": 3,
      "losers": 2,
      "cumulative_pnl": 2500.00
    }
  ],
  "total_days": 30,
  "period_days": 30,
  "timestamp": "2025-10-14T10:00:00"
}
```

### Get Recent Orders

Get recent orders from Alpaca.

**Endpoint:** `GET /api/v1/history/orders/recent`

**Query Parameters:**
- `limit` (int, optional): Maximum orders to return (default: 50, max: 200)

**Response:**
```json
{
  "orders": [
    {
      "id": "order-id",
      "symbol": "AAPL",
      "side": "buy",
      "type": "market",
      "qty": 100,
      "filled_qty": 100,
      "limit_price": null,
      "stop_price": null,
      "status": "filled",
      "filled_avg_price": 150.25,
      "submitted_at": "2025-10-14T09:35:00",
      "filled_at": "2025-10-14T09:35:02",
      "time_in_force": "day"
    }
  ],
  "count": 20,
  "timestamp": "2025-10-14T10:00:00"
}
```

---

## Backtesting Endpoints

### Run Backtest

Run a backtest on historical data.

**Endpoint:** `POST /api/v1/backtest/run`

**Request Body:**
```json
{
  "strategy": "proprietary",
  "symbols": ["AAPL", "MSFT", "GOOGL"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 10000,
  "timeframe": "5Min"
}
```

**Response:**
```json
{
  "backtest_id": "uuid-here",
  "status": "running",
  "message": "Backtest started",
  "timestamp": "2025-10-14T10:00:00"
}
```

### Get Backtest Results

Retrieve results from a completed backtest.

**Endpoint:** `GET /api/v1/backtest/results/{backtest_id}`

**Response:**
```json
{
  "backtest_id": "uuid-here",
  "status": "completed",
  "results": {
    "total_return": 25.50,
    "total_pnl": 2550.00,
    "total_trades": 150,
    "win_rate": 62.00,
    "profit_factor": 1.85,
    "sharpe_ratio": 1.45,
    "max_drawdown": -8.50,
    "avg_trade_duration": 180
  },
  "trades": [
    {
      "symbol": "AAPL",
      "entry_date": "2024-01-15",
      "exit_date": "2024-01-15",
      "entry_price": 150.00,
      "exit_price": 152.00,
      "pnl": 200.00,
      "return_pct": 1.33
    }
  ],
  "equity_curve": [
    {
      "date": "2024-01-01",
      "equity": 10000.00
    }
  ]
}
```

---

## Error Responses

All endpoints may return error responses in the following format:

**4xx Client Errors:**
```json
{
  "detail": "Error message describing what went wrong",
  "status_code": 400
}
```

**5xx Server Errors:**
```json
{
  "detail": "Internal server error message",
  "status_code": 500
}
```

**Common Error Codes:**
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (resource doesn't exist)
- `422` - Unprocessable Entity (validation error)
- `500` - Internal Server Error

---

## Rate Limiting

Currently, there are no rate limits on the API. For production use, implement appropriate rate limiting based on your infrastructure.

---

## WebSocket Support

Real-time updates are not currently available via WebSocket. Use polling with the status and position endpoints for near real-time updates.

**Recommended polling intervals:**
- Bot status: Every 5 seconds
- Active positions: Every 2 seconds
- Trade history: Every 30 seconds

---

## API Versioning

The API is currently at version 1 (`/api/v1/`). Future versions will maintain backward compatibility where possible.

---

## Examples

### Python Example

```python
import requests

BASE_URL = "http://localhost:8000"

# Start the bot
response = requests.post(f"{BASE_URL}/api/v1/bot/start")
print(response.json())

# Get active positions
response = requests.get(f"{BASE_URL}/api/v1/bot/active-positions")
positions = response.json()
print(f"Active positions: {positions['position_count']}")

# Get trade history
response = requests.get(
    f"{BASE_URL}/api/v1/history/trades",
    params={"limit": 10, "status": "filled"}
)
trades = response.json()
print(f"Recent trades: {len(trades['trades'])}")
```

### cURL Example

```bash
# Start bot
curl -X POST http://localhost:8000/api/v1/bot/start

# Get bot status
curl http://localhost:8000/api/v1/bot/status

# Get trade analytics
curl "http://localhost:8000/api/v1/history/analytics/summary?days=7"

# Close a position
curl -X POST http://localhost:8000/api/v1/bot/close-position/AAPL
```

---

## Interactive API Documentation

FastAPI provides interactive API documentation:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

These interfaces allow you to:
- View all available endpoints
- Test endpoints directly from the browser
- See request/response schemas
- Download OpenAPI specification

---

**Last updated:** October 2025
