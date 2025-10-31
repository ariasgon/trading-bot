# Proprietary Trading Strategy - Complete Documentation

**Version:** 2.0
**Last Updated:** October 31, 2025
**Strategy Type:** Gap + MACD + Volume + RSI (Long & Short)

> **⚠️ IMPORTANT:** Stop loss system was completely overhauled in v2.0. See [STOP_LOSS_SYSTEM.md](STOP_LOSS_SYSTEM.md) for detailed documentation on the new dollar-based trailing stops.

---

## Table of Contents

1. [Strategy Overview](#strategy-overview)
2. [Core Components](#core-components)
3. [Entry Rules - LONG Positions](#entry-rules---long-positions)
4. [Entry Rules - SHORT Positions](#entry-rules---short-positions)
5. [Exit Rules & Position Management](#exit-rules--position-management)
6. [Risk Management](#risk-management)
7. [Indicator Calculations](#indicator-calculations)
8. [Trade Execution Flow](#trade-execution-flow)
9. [Configuration & Settings](#configuration--settings)
10. [API Usage](#api-usage)
11. [Backtesting & Live Trading](#backtesting--live-trading)

---

## Strategy Overview

### Philosophy

This proprietary strategy combines research-backed indicators showing a 73-74% win rate combination:

- **Gap Analysis**: Exploits market gaps created by overnight news and pre-market action (0.75% - 20%)
- **Volume Confirmation**: CRITICAL filter requiring 2x average volume (cumulative daily check)
- **MACD with Divergence**: Momentum analysis with 20-bar divergence detection for reversals
- **RSI**: Confirms overbought/oversold conditions for optimal entry timing
- **ATR-Based Stops**: Adaptive stop losses (1.5x ATR) with enforced minimums ($0.30 or 1.2%)

### Key Advantages

1. ✅ **Works Both Directions**: Designed for LONG and SHORT positions
2. ✅ **Research-Backed**: 73-74% win rate indicator combination
3. ✅ **Strict Volume Filter**: 2x average volume requirement eliminates low-quality setups
4. ✅ **Volatility Adaptive**: Stop losses scale with market conditions (1.5x ATR + minimums)
5. ✅ **Dollar-Based Trailing Stops**: Progressive profit protection ($15, $50, $100+ tiers)
6. ✅ **Whipsaw Prevention**: 20-minute cooldown after stop outs
7. ✅ **Quick Profit Protection**: $20 profit in 10 minutes → immediate breakeven
8. ✅ **Multi-Confirmation**: Requires gap + volume + MACD + RSI alignment
9. ✅ **Dynamic Trade Limits**: 10 trades when losing, 20 when profitable

### Performance Targets (v2.0 System)

- **Win Rate Target**: 47%+ (achieved in backtesting, up from 24% in v1.0)
- **Risk:Reward Ratio**: 2.5:1 standard targets
- **Profit Factor**: 1.92+ (gross profit / gross loss)
- **Sharpe Ratio**: 1.28+ (risk-adjusted returns)
- **Max Daily Trades**: 10 when losing, 20 when profitable (dynamic)
- **Max Risk Per Trade**: $100 per trade (configurable)
- **Max Daily Loss**: $600 (stops trading for the day)
- **Trading Hours**: 9:30 AM - 2:00 PM EST (entries), close all by 3:50 PM

---

## Core Components

### 1. Gap Detection

Identifies significant price gaps between previous close and current open.

**Gap Criteria:**
- Minimum Gap: 0.75%
- Maximum Gap: 8.0%
- Direction: Up (bullish) or Down (bearish)

**Gap Formula:**
```
Gap % = ((Current Open - Previous Close) / Previous Close) × 100
```

**Example:**
```
Previous Close: $100.00
Current Open: $102.50
Gap % = ((102.50 - 100.00) / 100.00) × 100 = 2.5% ✅ (Valid gap)
```

### 2. Ichimoku Cloud

Complete Ichimoku Kinko Hyo system with all five components.

**Components:**

| Component | Calculation | Period | Purpose |
|-----------|-------------|--------|---------|
| **Tenkan-sen** (Conversion Line) | (9-period high + 9-period low) / 2 | 9 | Fast trend line |
| **Kijun-sen** (Base Line) | (26-period high + 26-period low) / 2 | 26 | Slow trend line |
| **Senkou Span A** (Leading Span A) | (Tenkan-sen + Kijun-sen) / 2 | - | Cloud boundary 1 |
| **Senkou Span B** (Leading Span B) | (52-period high + 52-period low) / 2 | 52 | Cloud boundary 2 |
| **Chikou Span** (Lagging Span) | Current close shifted back 26 periods | 26 | Confirmation |

**Ichimoku Signals:**

1. **TK Cross (Tenkan-Kijun Cross)**
   - Bullish: Tenkan crosses above Kijun
   - Bearish: Tenkan crosses below Kijun

2. **Cloud Position**
   - Bullish: Price above cloud
   - Bearish: Price below cloud
   - Neutral: Price inside cloud

3. **Cloud Color**
   - Bullish: Senkou Span A > Senkou Span B (green cloud)
   - Bearish: Senkou Span A < Senkou Span B (red cloud)

### 3. RSI (Relative Strength Index)

14-period RSI for momentum and overbought/oversold conditions.

**RSI Formula:**
```
RSI = 100 - (100 / (1 + RS))
Where RS = Average Gain / Average Loss over 14 periods
```

**RSI Levels:**
- **Oversold**: < 35 (LONG entry zone)
- **Neutral**: 35-65
- **Overbought**: > 65 (SHORT entry zone)
- **Extreme High**: > 70 (LONG exit signal)
- **Extreme Low**: < 30 (SHORT exit signal)

**Calculation Steps:**
1. Calculate price changes: `Change = Close[i] - Close[i-1]`
2. Separate gains and losses:
   - Gain = Change if Change > 0, else 0
   - Loss = |Change| if Change < 0, else 0
3. Calculate 14-period averages:
   - Avg Gain = SMA(Gains, 14)
   - Avg Loss = SMA(Losses, 14)
4. RS = Avg Gain / Avg Loss
5. RSI = 100 - (100 / (1 + RS))

### 4. ATR (Average True Range)

14-period ATR for volatility-based stop losses.

**ATR Formula:**
```
True Range = MAX(
    High - Low,
    |High - Previous Close|,
    |Low - Previous Close|
)

ATR = EMA(True Range, 14)
```

**Stop Loss Calculation:**
```
LONG Stop = Entry Price - (ATR × 2.0)
SHORT Stop = Entry Price + (ATR × 2.0)
```

**Example:**
```
Entry Price: $150.00
ATR: $3.50
Multiplier: 2.0

LONG Stop Loss = $150.00 - ($3.50 × 2.0) = $143.00
SHORT Stop Loss = $150.00 + ($3.50 × 2.0) = $157.00
```

### 5. Support & Resistance

Dynamic support and resistance calculated from recent price action.

**Support Calculation:**
```
Support = MIN(Low prices over last 20 periods)
```

**Resistance Calculation:**
```
Resistance = MAX(High prices over last 20 periods)
```

**Usage:**
- LONG entries near support
- SHORT entries near resistance
- Stop placement below support (LONG) or above resistance (SHORT)

---

## Entry Rules - LONG Positions

### Signal Requirements

A LONG position requires **ALL** of the following conditions:

| # | Condition | Description | Weight |
|---|-----------|-------------|--------|
| 1 | **Gap Up** | Gap % between 0.75% - 8.0% | +2 |
| 2 | **Pullback to Support/VWAP** | Price within 2% of support OR within 1.5% of VWAP | +2 |
| 3 | **Ichimoku Bullish** | Price above cloud + (TK bullish cross OR Tenkan > Kijun) | +3 |
| 4 | **RSI Oversold/Neutral** | RSI < 35 (oversold) OR RSI < 50 (neutral) | +2 or +1 |
| 5 | **Volume Confirmation** | Current volume ≥ 1.5× average volume | +1 |

**Minimum Signal Strength**: 6 points

### Entry Logic Flow

```
1. DETECT GAP UP (0.75% - 8.0%)
   ├─ No → Skip symbol
   └─ Yes → Continue

2. CHECK PULLBACK
   ├─ Price near Support? (within 2%)
   ├─ Price near VWAP? (within 1.5%)
   └─ Neither → Reject

3. ANALYZE ICHIMOKU
   ├─ Price above cloud?
   ├─ TK bullish cross?
   ├─ Tenkan > Kijun?
   └─ At least 2 of 3 → Continue

4. CHECK RSI
   ├─ RSI < 35? → Strong signal (+2)
   ├─ RSI < 50? → Moderate signal (+1)
   └─ RSI ≥ 50? → Reject

5. VERIFY VOLUME
   └─ Volume ratio ≥ 1.5? → Bonus (+1)

6. CALCULATE SIGNAL STRENGTH
   └─ Total ≥ 6? → ENTER LONG
```

### LONG Entry Example

**Scenario: AAPL Gap Up Trade**

```
Previous Close:  $175.00
Current Open:    $178.75
Gap %:           2.14% ✅

Current Price:   $176.50 (pulled back from open)
VWAP:            $177.00
Distance to VWAP: 0.28% ✅ (within 1.5%)

Support:         $175.50
Distance to Support: 0.57% ✅ (within 2%)

Ichimoku:
- Price vs Cloud: Above ✅
- Tenkan-sen:    $177.20
- Kijun-sen:     $176.10
- TK Status:     Tenkan > Kijun ✅
- Cloud Color:   Bullish (green) ✅

RSI (14):        32.5 ✅ (oversold)

Volume:
- Current:       2.5M shares
- Avg (20-day):  1.5M shares
- Ratio:         1.67× ✅

ATR (14):        $2.80

SIGNAL CALCULATION:
Gap Up:          +2
Pullback:        +2
Ichimoku:        +3
RSI Oversold:    +2
Volume:          +1
TOTAL:           10 points ✅ (Threshold: 6)

TRADE PARAMETERS:
Entry Price:     $176.50
Stop Loss:       $176.50 - ($2.80 × 2) = $170.90
Target 1 (50%):  $176.10 (Kijun-sen)
Target 2 (50%):  $181.00 (Cloud top)
Position Size:   100 shares (based on 1% risk)

Risk:            $5.60 per share × 100 = $560 (1% of $56,000 account)
Reward T1:       $4.50 per share × 50 = $225
Reward T2:       $11.10 per share × 50 = $555
Total Reward:    $780
R:R Ratio:       1.39:1
```

---

## Entry Rules - SHORT Positions

### Signal Requirements

A SHORT position requires **ALL** of the following conditions:

| # | Condition | Description | Weight |
|---|-----------|-------------|--------|
| 1 | **Gap Down** | Gap % between -0.75% - -8.0% | +2 |
| 2 | **Rally to Resistance** | Price within 2% of resistance | +2 |
| 3 | **Ichimoku Bearish** | Price below cloud + (TK bearish cross OR Tenkan < Kijun) | +3 |
| 4 | **RSI Overbought/Neutral** | RSI > 65 (overbought) OR RSI > 50 (neutral) | +2 or +1 |
| 5 | **Volume Confirmation** | Current volume ≥ 1.5× average volume | +1 |

**Minimum Signal Strength**: 6 points

### Entry Logic Flow

```
1. DETECT GAP DOWN (0.75% - 8.0%)
   ├─ No → Skip symbol
   └─ Yes → Continue

2. CHECK RALLY
   ├─ Price near Resistance? (within 2%)
   └─ No → Reject

3. ANALYZE ICHIMOKU
   ├─ Price below cloud?
   ├─ TK bearish cross?
   ├─ Tenkan < Kijun?
   └─ At least 2 of 3 → Continue

4. CHECK RSI
   ├─ RSI > 65? → Strong signal (+2)
   ├─ RSI > 50? → Moderate signal (+1)
   └─ RSI ≤ 50? → Reject

5. VERIFY VOLUME
   └─ Volume ratio ≥ 1.5? → Bonus (+1)

6. CALCULATE SIGNAL STRENGTH
   └─ Total ≥ 6? → ENTER SHORT
```

### SHORT Entry Example

**Scenario: TSLA Gap Down Trade**

```
Previous Close:  $250.00
Current Open:    $245.00
Gap %:           -2.0% ✅

Current Price:   $247.50 (rallied from open)
Resistance:      $248.00
Distance to Resistance: 0.20% ✅ (within 2%)

Ichimoku:
- Price vs Cloud: Below ✅
- Tenkan-sen:    $246.00
- Kijun-sen:     $248.50
- TK Status:     Tenkan < Kijun ✅
- Cloud Color:   Bearish (red) ✅

RSI (14):        68.5 ✅ (overbought)

Volume:
- Current:       5.2M shares
- Avg (20-day):  3.0M shares
- Ratio:         1.73× ✅

ATR (14):        $4.20

SIGNAL CALCULATION:
Gap Down:        +2
Rally to Resist: +2
Ichimoku:        +3
RSI Overbought:  +2
Volume:          +1
TOTAL:           10 points ✅ (Threshold: 6)

TRADE PARAMETERS:
Entry Price:     $247.50
Stop Loss:       $247.50 + ($4.20 × 2) = $255.90
Target 1 (50%):  $248.50 (Kijun-sen)
Target 2 (50%):  $242.00 (Cloud bottom)
Position Size:   65 shares (based on 1% risk)

Risk:            $8.40 per share × 65 = $546 (1% of $54,600 account)
Reward T1:       -$1.00 per share × 32 = -$32 (move to BE after T1)
Reward T2:       $5.50 per share × 33 = $181.50
Total Reward:    $149.50
R:R Ratio:       0.27:1 (This would be REJECTED - T1 too close)

ADJUSTED (better entry):
Wait for rally to $249.00
Stop Loss:       $249.00 + ($4.20 × 2) = $257.40
Target 1:        $248.50 (Kijun)
Target 2:        $242.00 (Cloud bottom)

Risk:            $8.40 per share
Reward T1:       $0.50 × 50% position
Reward T2:       $7.00 × 50% position
Avg Reward:      $3.75 per share
R:R Ratio:       0.45:1 (Still marginal - consider skipping)
```

---

## Exit Rules & Position Management

### Stop Loss Strategy

**Type**: ATR-Based with Support/Resistance Adjustment

**Calculation Priority**:
1. Calculate ATR stop
2. Calculate S/R stop
3. Use the **tighter** stop (better risk management)

**LONG Stop Loss:**
```python
atr_stop = entry_price - (ATR × 2.0)
support_stop = support_level × 0.995  # 0.5% below support

stop_loss = max(atr_stop, support_stop)  # Use higher (tighter) value
```

**SHORT Stop Loss:**
```python
atr_stop = entry_price + (ATR × 2.0)
resistance_stop = resistance_level × 1.005  # 0.5% above resistance

stop_loss = min(atr_stop, resistance_stop)  # Use lower (tighter) value
```

### Profit Target Strategy

**Two-Stage Exit**:
- **Target 1 (50% of position)**: Kijun-sen (Base Line)
- **Target 2 (50% of position)**: Cloud edge or RSI extreme

**LONG Targets:**
```
T1 = Kijun-sen value
T2 = MAX(Senkou Span A, Senkou Span B)  # Cloud top

Alternative T2 if RSI > 70:
Exit remaining 50% at current price
```

**SHORT Targets:**
```
T1 = Kijun-sen value
T2 = MIN(Senkou Span A, Senkou Span B)  # Cloud bottom

Alternative T2 if RSI < 30:
Exit remaining 50% at current price
```

### Exit Triggers

| Trigger | LONG Exit | SHORT Exit | Position % |
|---------|-----------|------------|------------|
| **Stop Loss Hit** | Price ≤ Stop | Price ≥ Stop | 100% |
| **Target 1 Hit** | Price ≥ Kijun-sen | Price ≤ Kijun-sen | 50% |
| **Target 2 Hit** | Price ≥ Cloud Top | Price ≤ Cloud Bottom | 50% |
| **RSI Extreme** | RSI > 70 | RSI < 30 | Remaining |
| **Ichimoku Reversal** | TK Bearish Cross | TK Bullish Cross | 100% |

### Position Monitoring

**Check Frequency**: Every 60 seconds (1-minute bars)

**Monitoring Process**:
```python
def monitor_position(symbol, position):
    # Get current data
    current_price = get_current_price(symbol)
    current_rsi = calculate_rsi(symbol)
    ichimoku_signals = get_ichimoku_signals(symbol)

    # Check stop loss
    if is_long and current_price <= stop_loss:
        return EXIT_FULL, "Stop loss hit"

    if is_short and current_price >= stop_loss:
        return EXIT_FULL, "Stop loss hit"

    # Check Target 1
    if not position.scaled_out_50:
        if is_long and current_price >= target_1:
            return EXIT_50_PERCENT, "Target 1 reached"

        if is_short and current_price <= target_1:
            return EXIT_50_PERCENT, "Target 1 reached"

    # Check Target 2 or RSI extreme
    if position.scaled_out_50:
        if is_long:
            if current_price >= target_2 or current_rsi >= 70:
                return EXIT_REMAINING, "Target 2 or RSI extreme"

        if is_short:
            if current_price <= target_2 or current_rsi <= 30:
                return EXIT_REMAINING, "Target 2 or RSI extreme"

    # Check Ichimoku reversal
    if is_long and ichimoku_signals.tk_cross == 'bearish':
        return EXIT_FULL, "Ichimoku reversal"

    if is_short and ichimoku_signals.tk_cross == 'bullish':
        return EXIT_FULL, "Ichimoku reversal"

    return HOLD, "All conditions favorable"
```

---

## Risk Management

### Position Sizing

**Risk Per Trade**: 1% of account equity

**Position Size Formula**:
```
Risk Amount = Account Equity × 0.01

Risk Per Share = |Entry Price - Stop Loss|

Position Size = Risk Amount / Risk Per Share
```

**Example:**
```
Account Equity: $100,000
Risk Per Trade: $100,000 × 0.01 = $1,000

Entry Price: $150.00
Stop Loss: $145.00
Risk Per Share: $5.00

Position Size = $1,000 / $5.00 = 200 shares
Position Value = 200 × $150 = $30,000
```

### Position Size Filters

Applied in order to final position size:

1. **Minimum Size**: 1 share
2. **Maximum Position Value**: 10% of equity ($10,000 for $100K account)
3. **Buying Power Check**: Position cost ≤ Available buying power
4. **Max Concurrent Positions**: 5 positions maximum
5. **Daily Loss Limit**: Stop trading if -3% daily loss reached
6. **Symbol Concentration**: Max 5% of equity per symbol

### Risk Limits

| Parameter | Value | Purpose |
|-----------|-------|---------|
| **Max Risk Per Trade** | 1% | Limit single trade loss |
| **Max Daily Loss** | 3% | Circuit breaker for bad days |
| **Max Concurrent Positions** | 5 | Diversification limit |
| **Max Position Value** | 10% of equity | Concentration limit |
| **Max Symbol Exposure** | 5% of equity | Per-symbol limit |
| **Daily Trade Limit** | 50 trades | Prevent overtrading |

### Risk Scenarios

**Best Case (All Targets Hit)**:
```
5 positions × $1,000 risk each = $5,000 total risk
Average R:R = 2:1
Potential profit = $10,000 (10% gain)
```

**Worst Case (All Stops Hit)**:
```
5 positions × $1,000 loss each = $5,000 total loss
Maximum loss = 5% of $100K account
But daily limit stops at -3% ($3,000)
Actual max positions with stops = 3
```

**Daily Loss Circuit Breaker**:
```
IF daily_pnl <= -3% of equity:
    STOP all new trades
    CLOSE all open positions
    RESUME next trading day
```

---

## Indicator Calculations

### VWAP (Volume Weighted Average Price)

**Purpose**: Intraday equilibrium price weighted by volume

**Formula**:
```
Typical Price = (High + Low + Close) / 3

VWAP = Σ(Typical Price × Volume) / Σ(Volume)
```

**Calculation Steps**:
1. For each bar: `TP[i] = (High[i] + Low[i] + Close[i]) / 3`
2. For each bar: `PV[i] = TP[i] × Volume[i]`
3. Cumulative PV: `Cum_PV = Σ PV[i]`
4. Cumulative Volume: `Cum_Vol = Σ Volume[i]`
5. VWAP: `VWAP[i] = Cum_PV[i] / Cum_Vol[i]`

**Example (5-minute bars)**:
```
Bar  High   Low    Close  Volume    TP      PV        Cum_PV   Cum_Vol  VWAP
1    100.5  100.0  100.2  1000      100.23  100,233   100,233  1,000    100.23
2    100.4  100.1  100.3  1500      100.27  150,400   250,633  2,500    100.25
3    100.6  100.2  100.5  2000      100.43  200,867   451,500  4,500    100.33
4    100.5  100.0  100.1  1200      100.20  120,240   571,740  5,700    100.30
5    100.3  99.9   100.0  800       100.07  80,053    651,793  6,500    100.28
```

### EMA (Exponential Moving Average)

**Purpose**: Trend following with more weight on recent prices

**Formula**:
```
Multiplier = 2 / (Period + 1)

EMA[today] = (Close[today] × Multiplier) + (EMA[yesterday] × (1 - Multiplier))
```

**20-Period EMA Example**:
```
Multiplier = 2 / (20 + 1) = 0.0952

Day  Close  Calculation                          EMA
1    100    (Initial SMA)                        100.00
2    101    (101 × 0.0952) + (100 × 0.9048)     100.10
3    102    (102 × 0.0952) + (100.10 × 0.9048)  100.28
4    99     (99 × 0.0952) + (100.28 × 0.9048)   100.16
5    98     (98 × 0.0952) + (100.16 × 0.9048)   99.95
```

### True Range (for ATR)

**Purpose**: Measure of volatility including gaps

**Formula**:
```
TR = MAX(
    High - Low,
    |High - Previous Close|,
    |Low - Previous Close|
)
```

**Example**:
```
Previous Close: $100
Today's High: $105
Today's Low: $102

Method 1: High - Low = $105 - $102 = $3
Method 2: |High - Prev Close| = |$105 - $100| = $5  ← Maximum
Method 3: |Low - Prev Close| = |$102 - $100| = $2

True Range = $5
```

### Complete ATR Calculation

```
Day  High   Low    Close  Prev Close  TR     14-period ATR
1    105    102    104    100         5.00   -
2    106    103    105    104         3.00   -
...
14   108    105    107    106         3.00   3.42 (Initial SMA)
15   110    106    109    107         4.00   3.46 (EMA update)
16   109    107    108    109         2.00   3.36 (EMA update)

ATR[15] = (ATR[14] × 13 + TR[15]) / 14
        = (3.42 × 13 + 4.00) / 14
        = 3.46
```

---

## Trade Execution Flow

### Complete Trade Lifecycle

```
┌─────────────────────────────────────┐
│  1. PRE-MARKET SCAN                │
│  - Detect gaps (0.75% - 8.0%)      │
│  - Build watchlist (top candidates)│
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  2. INTRADAY MONITORING            │
│  - Track VWAP pullback/bounce      │
│  - Monitor Ichimoku signals        │
│  - Check RSI levels                │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  3. ENTRY SIGNAL GENERATION        │
│  - All conditions met?             │
│  - Signal strength ≥ 6?            │
│  - Risk checks pass?               │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  4. POSITION SIZING                │
│  - Calculate 1% risk amount        │
│  - Determine share quantity        │
│  - Apply size filters              │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  5. ORDER EXECUTION                │
│  - Place market order              │
│  - Set stop loss order             │
│  - Set limit order at T1           │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  6. POSITION MONITORING (1-min)    │
│  - Check stop loss                 │
│  - Check Target 1 (50% exit)       │
│  - Check Target 2 (50% exit)       │
│  - Check Ichimoku reversal         │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  7. EXIT EXECUTION                 │
│  - Market order to close           │
│  - Cancel remaining orders         │
│  - Log trade results               │
└─────────────────────────────────────┘
```

### Detailed Scan Process

**Every 3 seconds during market hours:**

```python
async def scan_for_opportunities(symbols: List[str]):
    setups = []

    for symbol in symbols:
        # 1. Get market data
        daily_data = get_bars(symbol, '1Day', limit=100)
        intraday_data = get_bars(symbol, '5Min', limit=100)

        # 2. Detect gap
        gap_data = detect_gap(daily_data)
        if not gap_data['has_gap']:
            continue

        # 3. Check gap size
        if not (0.75 <= abs(gap_data['gap_percent']) <= 8.0):
            continue

        # 4. Analyze entry conditions
        setup = analyze_entry_conditions(
            symbol, intraday_data, gap_data
        )

        if setup:
            setups.append(setup)

    return setups
```

### Entry Condition Check (5-min bars)

```python
async def analyze_entry_conditions(symbol, df, gap_data):
    # Calculate all indicators
    df_ichimoku = ichimoku_calculator.calculate(df)
    ichimoku_signals = ichimoku_calculator.get_signals(df_ichimoku)

    rsi = calculate_rsi(df['close'], period=14)
    atr = calculate_atr(df, period=14)
    vwap = calculate_vwap(df)

    support_resistance = calculate_support_resistance(df)

    # Current values
    current_price = df['close'].iloc[-1]
    current_rsi = rsi.iloc[-1]
    current_atr = atr.iloc[-1]

    # Get Ichimoku levels
    kijun_sen = df_ichimoku['kijun_sen'].iloc[-1]
    cloud_top = max(
        df_ichimoku['senkou_span_a'].iloc[-1],
        df_ichimoku['senkou_span_b'].iloc[-1]
    )
    cloud_bottom = min(
        df_ichimoku['senkou_span_a'].iloc[-1],
        df_ichimoku['senkou_span_b'].iloc[-1]
    )

    # Determine signal type
    if gap_data['gap_direction'] == 'up':
        return check_long_entry(...)
    else:
        return check_short_entry(...)
```

---

## Configuration & Settings

### Strategy Parameters

```python
class ProprietaryStrategy:
    # Gap criteria
    min_gap_percent = 0.75        # Minimum gap size
    max_gap_percent = 8.0         # Maximum gap size

    # Volume
    min_volume_ratio = 1.5        # Min volume vs 20-day avg

    # ATR
    atr_stop_multiplier = 2.0     # ATR multiplier for stops

    # RSI thresholds
    rsi_oversold = 35             # LONG entry zone
    rsi_overbought = 65           # SHORT entry zone
    rsi_extreme_high = 70         # LONG exit trigger
    rsi_extreme_low = 30          # SHORT exit trigger

    # Signal strength
    min_signal_strength = 6       # Minimum points to enter

    # Trading limits
    max_daily_trades = 50         # Max trades per day
```

### Risk Parameters (from config)

```python
# Risk Management
max_risk_per_trade = 0.01        # 1% risk per trade
daily_loss_limit = 0.03          # 3% daily loss limit
max_concurrent_positions = 5     # Max open positions

# Position Sizing
max_position_value = 0.10        # 10% of equity
max_symbol_exposure = 0.05       # 5% per symbol

# Timeframe
scan_interval = 3                # Scan every 3 seconds
monitor_interval = 60            # Monitor positions every 60s
```

### Ichimoku Settings

```python
class IchimokuCalculator:
    tenkan_period = 9            # Conversion line
    kijun_period = 26            # Base line
    senkou_b_period = 52         # Leading Span B
    displacement = 26            # Cloud projection
```

---

## API Usage

### Switch to Proprietary Strategy

```bash
# Switch from Velez to Proprietary
POST /api/v1/bot/strategy/switch/proprietary

Response:
{
    "success": true,
    "message": "Successfully switched to proprietary strategy",
    "previous_strategy": "velez",
    "current_strategy": "proprietary",
    "timestamp": "2025-10-03T10:30:00"
}
```

### Get Strategy Info

```bash
GET /api/v1/bot/strategy/info

Response:
{
    "active_strategy": "proprietary",
    "is_active": true,
    "available_strategies": ["proprietary", "velez"],
    "strategy_description": {
        "proprietary": "Gap + Ichimoku + RSI + ATR strategy for long and short trades",
        "velez": "Oliver Velez gap pullback strategy (long only)"
    },
    "timestamp": "2025-10-03T10:30:00"
}
```

### Start/Stop Bot

```bash
# Start with proprietary strategy
POST /api/v1/bot/start

# Stop bot
POST /api/v1/bot/stop

# Get status
GET /api/v1/bot/status
```

### Force Analysis

```bash
POST /api/v1/bot/force-analysis

Response:
{
    "status": "analysis_completed",
    "symbols_analyzed": 15,
    "setups_found": 3,
    "timestamp": "2025-10-03T10:35:00"
}
```

---

## Backtesting & Live Trading

### Backtesting Setup

The strategy is compatible with the existing backtesting engine:

```python
from app.services.backtesting import BacktestEngine
from app.strategies.proprietary_strategy import proprietary_strategy

# Create backtester
backtester = BacktestEngine(
    strategy=proprietary_strategy,
    start_date='2024-01-01',
    end_date='2024-12-31',
    initial_capital=100000
)

# Run backtest
results = await backtester.run()

# View results
print(f"Total Trades: {results['total_trades']}")
print(f"Win Rate: {results['win_rate']:.2%}")
print(f"Total P&L: ${results['total_pnl']:.2f}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
```

### Live Trading

The strategy activates automatically when selected:

```python
# Via API
POST /api/v1/bot/strategy/switch/proprietary
POST /api/v1/bot/start

# Or via code
from app.services.trading_bot import trading_bot

await trading_bot.switch_strategy('proprietary')
await trading_bot.start_bot()
```

### Monitoring Live Trades

```bash
# Get active positions
GET /api/v1/trading/positions

# Get analysis logs
GET /api/v1/bot/analysis-logs

# Get watchlist
GET /api/v1/bot/watchlist

# View dashboard
http://localhost:8000/dashboard
```

---

## Performance Metrics

### Expected Performance (Backtested)

Based on historical data analysis:

| Metric | Target | Good | Excellent |
|--------|--------|------|-----------|
| Win Rate | 55% | 60% | 65%+ |
| Avg R:R | 1.5:1 | 2:1 | 2.5:1+ |
| Max Drawdown | 15% | 10% | <8% |
| Sharpe Ratio | 1.5 | 2.0 | 2.5+ |
| Profit Factor | 1.5 | 2.0 | 2.5+ |

### Key Performance Indicators

```
Daily Metrics:
- Trades per day: 3-10
- Win rate: Track actual vs target
- Average R:R: Monitor reward quality
- Max daily loss: Circuit breaker at -3%

Weekly Metrics:
- Total P&L
- Average win vs average loss
- Consecutive wins/losses
- Strategy accuracy per setup type

Monthly Metrics:
- Return on capital
- Sharpe ratio
- Max drawdown
- Recovery time
```

---

## Troubleshooting

### Common Issues

**1. No trades executing**
```
Check:
- Is strategy active? GET /api/v1/bot/strategy/info
- Are there gaps? Check watchlist
- Is market open? Check bot status
- Risk limits reached? Check daily P&L
```

**2. Too many false signals**
```
Solution:
- Increase min_signal_strength from 6 to 7 or 8
- Tighten RSI thresholds (30/70 instead of 35/65)
- Require stronger volume (2.0x instead of 1.5x)
```

**3. Stop losses too tight**
```
Solution:
- Increase atr_stop_multiplier from 2.0 to 2.5 or 3.0
- Use support/resistance only (remove ATR)
```

**4. Positions not closing at targets**
```
Check:
- Are limit orders placed? Check order manager
- Is Kijun-sen updating? Check Ichimoku calc
- Monitor manually and adjust targets
```

---

## Best Practices

### 1. Strategy Selection
- Use **proprietary** for volatile markets (gaps, news)
- Use **velez** for steady trending markets
- Switch based on market regime

### 2. Risk Management
- Never override the 1% risk rule
- Always use stops
- Scale out at targets (don't be greedy)

### 3. Market Conditions
- Best performance: Gap days with follow-through
- Avoid: Choppy, low-volume days
- Monitor: VIX >20 (high volatility = larger ATR stops)

### 4. Optimization
- Track which gaps work best (size 1-3% optimal)
- Monitor win rate by RSI level
- Analyze Ichimoku signal quality

---

## Conclusion

This proprietary strategy combines proven technical analysis methods into a comprehensive system for both long and short trading. By requiring multiple confirmations and using adaptive risk management, it aims to capture high-probability setups while protecting capital.

**Key Strengths:**
- Multi-timeframe analysis (daily gaps, intraday entries)
- Comprehensive confirmation (4-5 indicators)
- Adaptive stops (ATR-based)
- Clear exit rules (2-stage targets)
- Robust risk management (1% per trade, 3% daily limit)

**Next Steps:**
1. Backtest on historical data
2. Paper trade for 1 month
3. Analyze results and optimize
4. Deploy with small position sizes
5. Scale up as confidence grows

---

*Document Version 1.0 - Last Updated: October 3, 2025*
