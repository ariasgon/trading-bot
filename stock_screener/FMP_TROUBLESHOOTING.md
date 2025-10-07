# FMP API Troubleshooting

## Issue: 403 Forbidden Error

Your FMP API key `7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI` is returning a 403 error.

---

## Possible Causes & Solutions

### 1. Email Verification Required

**Most Common Issue!**

1. Check your email inbox for message from Financial Modeling Prep
2. Click the verification link
3. Wait 5-10 minutes for activation
4. Try again

### 2. API Key Not Activated

1. Log in to: https://financialmodelingprep.com/developer/docs/dashboard
2. Check your API key status
3. Make sure it shows "Active"

### 3. Free Tier Limits

The free tier allows:
- 250 API calls per day
- Basic endpoints only

Check if you've exceeded today's limit in your dashboard.

### 4. Wrong API Key Format

1. Go to: https://financialmodelingprep.com/developer/docs/dashboard
2. Copy your API key again
3. Make sure there are no extra spaces
4. Update `.env` file

---

## Temporary Workaround

**Use the simplified screener** that works without FMP:

```bash
python screener_simple.py
```

This version:
- ✅ Works with Alpaca only
- ✅ Finds stocks down 30%+ from ATH
- ✅ Calculates price CAGR
- ❌ No PE ratio or financial CAGRs

---

## Testing FMP API

Test your API key manually:

```bash
curl "https://financialmodelingprep.com/api/v3/quote/AAPL?apikey=7V1pVkJkyTcGsyjizspwY8JPqbZsJLgI"
```

**Should return**:
```json
[{"symbol":"AAPL","name":"Apple Inc.","price":175.23,...}]
```

**If 403 error**: API key needs activation

---

## Alternative Data Sources

If FMP doesn't work, consider:

1. **Alpha Vantage** (free)
   - 25 calls/day
   - https://www.alphavantage.co/

2. **Yahoo Finance** (via yfinance library)
   - Free, unlimited
   - `pip install yfinance`

3. **Polygon.io** (free tier)
   - 5 calls/minute
   - https://polygon.io/

---

## Next Steps

1. **Check your email** for FMP verification
2. **Log in to FMP dashboard** to verify status
3. **Use `screener_simple.py`** in the meantime
4. **Once FMP works**, switch back to `screener.py`

---

## Contact FMP Support

If still not working:
- Email: support@financialmodelingprep.com
- Dashboard: https://financialmodelingprep.com/developer/docs/dashboard
