# Changelog

All notable changes to the Trading Bot project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-10-31

### 🚨 Major Breaking Changes

#### Stop Loss System Complete Overhaul
- **CRITICAL FIX**: Increased initial stop distance from 0.9x ATR to 1.5x ATR
  - Previous stops were too tight (e.g., PFE had $0.04 stops getting hit by noise)
  - Now enforces minimum $0.30 or 1.2% of price distance
  - Prevents micro-stops from normal bid/ask spread fluctuations

#### Strategy Consolidation
- **REMOVED**: Velez strategy (app/strategies/velez_strategy.py)
- **REMOVED**: Ichimoku strategy references
- **REMOVED**: Strategy API endpoints (app/api/strategy.py)
- **CONSOLIDATED**: Single proprietary strategy (Gap + MACD + Volume + RSI)

### ✨ Added

#### Dollar-Based Trailing Stops
- Complete replacement of percentage-based trailing stops
- Progressive profit protection tiers:
  - **$15 profit**: Move to breakeven (lowered from $30)
  - **$20 profit in 10 minutes**: Quick profit protection → immediate breakeven
  - **$80 profit**: Lock $50 (with $30 buffer for breathing room)
  - **$130 profit**: Lock $100 (with $30 buffer)
  - **Every +$50**: Continue locking profit with $30 buffer

#### Whipsaw Prevention System
- 20-minute cooldown after stop outs
- Prevents immediate re-entry into same symbols
- Tracks stop out timestamps per symbol
- Automatic cleanup when cooldown expires

#### Dynamic Trade Limits
- Adaptive position count based on daily P/L:
  - **10 trades** when daily PnL ≤ 0
  - **20 trades** when daily PnL > 0
- Encourages scaling up when winning
- Reduces exposure when losing

#### Enhanced Position Management
- Fixed position counting to only track bot-managed positions
- Manual positions (opened outside bot) no longer count against limits
- Resolves "Max position limit reached" false positives

### 🔄 Changed

#### Trading Hours
- **Extended entry cutoff**: 12 PM → 2 PM EST
- Allows capturing afternoon momentum moves
- Still closes all positions by 3:50 PM EST

#### Stop Loss Parameters
- `atr_stop_multiplier`: 0.9 → 1.5 (67% increase)
- Added `min_stop_distance_dollars`: $0.30
- Added `min_stop_distance_percent`: 1.2%
- Stop calculation now uses larger of ATR-based or minimum distance

#### Profit Targets
- Updated from `1.5x ATR` to `2.5x risk distance`
- Better risk/reward ratio
- Aggressive target increased to 3.5x for strong setups

#### Trailing Stop Thresholds
- `breakeven_profit_threshold`: $30 → $15 (50% reduction)
- Added `quick_profit_threshold`: $20 in 10 minutes
- Added `stop_out_cooldown`: 1200 seconds (20 minutes)

#### Position Monitoring
- Added position age tracking for quick profit protection
- Enhanced logging with tier names and locked profit amounts
- Better visibility into stop upgrade decisions

### 🐛 Fixed

#### Critical Stop Loss Issues
- **Fixed**: Stops too tight causing whipsaw losses
  - Example: PFE $0.04 stops → now minimum $0.30
  - Example: NET stopped in same minute → now has breathing room
- **Fixed**: Duplicate stop orders bug
  - Previously: Same stop executed 2-3 times simultaneously
  - Now: Proper order management prevents duplicates
- **Fixed**: Immediate re-entry after stop out
  - Previously: Bot would re-enter same stock within seconds
  - Now: 20-minute cooldown prevents whipsaws

#### Position Counting Bug
- **Fixed**: Manual positions counted against bot limits
  - Previously: Manual AMZN/CHTR/NET positions blocked bot entries
  - Now: Only bot-managed positions count toward 5-position limit
- Changed `get_open_positions_count()` to use database (bot positions only)
- Added fallback to Alpaca API if database unavailable

#### Strategy Imports
- **Fixed**: Removed all Velez strategy imports from main.py
- **Fixed**: Updated bot_control.py to remove Velez session checks
- **Fixed**: Cleaned up strategy.__init__.py exports

### 📊 Performance Improvements

#### Risk/Reward Optimization
- **Before**: 0.9x ATR stop, 1.5x ATR target = 1.67:1 R/R
- **After**: 1.5x ATR stop, 2.5x target = 2.5:1 R/R (50% improvement)

#### Stop Out Frequency
- **Expected reduction**: 60-70% fewer stop outs
- Minimum stop distance prevents noise-based exits
- Quick profit protection captures fast movers

#### Trade Efficiency
- Dynamic limits allow 2x position count when profitable
- Whipsaw prevention improves win rate
- Extended hours capture more opportunities

### 🗑️ Removed

#### Deprecated Files
- `app/api/strategy.py` - No longer needed with single strategy
- `app/strategies/velez_strategy.py` - Removed in consolidation
- Strategy selection endpoints - Single strategy only

#### Deprecated Parameters
- Percentage-based trailing stop parameters
- Velez-specific configuration options
- Ichimoku strategy references

### 📝 Documentation

#### Updated
- README.md - Complete rewrite reflecting current state
- PROPRIETARY_STRATEGY_DOCUMENTATION.md - Updated stop loss details
- Added CHANGELOG.md - This file

#### Added Sections
- Advanced Stop Loss System documentation
- Whipsaw Prevention guide
- Dynamic Trade Limits explanation
- Recent Updates section in README

### 🔧 Technical Changes

#### Code Quality
- Added `time_module` import to avoid namespace conflicts
- Enhanced error handling in stop upgrade logic
- Improved logging messages with emoji indicators
- Added detailed docstrings to new methods

#### Database
- No schema changes required
- Backward compatible with existing data
- Position counting logic updated (no migration needed)

### ⚠️ Migration Notes

#### For Existing Users

**If upgrading from v1.x:**

1. **Stop all running bot instances**
2. **Pull latest code**: `git pull origin main`
3. **No database migration required**
4. **Update .env if using custom stop parameters**:
   ```env
   # Old parameters (remove these):
   # TRAILING_STOP_ACTIVATION=0.002
   # TRAILING_STOP_PERCENT=0.0065

   # New parameters (add these):
   BREAKEVEN_PROFIT_THRESHOLD=15
   QUICK_PROFIT_THRESHOLD=20
   STOP_OUT_COOLDOWN=1200
   ATR_STOP_MULTIPLIER=1.5
   ```
5. **Restart bot**: `start_trading_bot.bat`
6. **Monitor first day closely** to verify new stops are working

**Breaking Changes:**
- If you modified Velez strategy code, you'll need to port changes to proprietary strategy
- Custom trailing stop logic will need to be adapted to dollar-based system
- Strategy API endpoints have been removed

### 🎯 Known Issues

- None at this time

### 📈 Statistics

- **Lines of code changed**: 1,507 insertions, 1,668 deletions
- **Files modified**: 19
- **Files deleted**: 2
- **Commits**: 1 major release commit

---

## [1.9.0] - 2025-10-30

### Added
- Professional dashboard redesign with dark mode
- Trade history analytics dashboard
- Real-time P/L tracking
- Order history viewer

### Changed
- Updated UI to modern design language
- Enhanced mobile responsiveness

---

## [1.8.0] - 2025-10-29

### Added
- Backtesting dashboard
- Realistic daily market scanning in backtests
- ML model integration preparation

---

## [1.7.0] - 2025-10-28

### Added
- Comprehensive logging system
- Analysis logger for trade decisions
- Enhanced error tracking

---

## [1.0.0] - 2025-10-01

### Initial Release
- Basic gap trading strategy
- Alpaca integration
- PostgreSQL database
- Redis caching
- FastAPI backend
- Simple web dashboard

---

## Version Numbering

- **Major version (X.0.0)**: Breaking changes, major feature additions
- **Minor version (0.X.0)**: New features, non-breaking changes
- **Patch version (0.0.X)**: Bug fixes, minor improvements

## Support

For questions or issues:
- GitHub Issues: https://github.com/ariasgon/trading-bot/issues
- Discussions: https://github.com/ariasgon/trading-bot/discussions
