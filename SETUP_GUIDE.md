# 🚀 BTC Forecaster - Complete Setup Guide

## Problem Solved: Automatic Data Updates

### What Was Wrong?
1. ❌ Dashboard showing old/stale data
2. ❌ Manual refresh required to see new predictions
3. ❌ No automatic backfilling of missing data
4. ❌ GitHub Actions not keeping database current

### What's Fixed Now?
1. ✅ **Auto-refresh every 10 seconds** - Dashboard automatically reloads
2. ✅ **Fast cache (5 seconds)** - Data updates quickly from database
3. ✅ **Manual backfill script** - Quick recovery if database falls behind
4. ✅ **GitHub Actions** - Automatically runs every hour
5. ✅ **Monitoring tools** - Easy to check database status

---

## 📦 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Create `.env` file:
```bash
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here
```

### 3. Initialize Database (First Time Only)
```bash
# Run the manual backfill to populate database
python manual_backfill.py
```

### 4. Run the Dashboard
```bash
streamlit run app.py
```
Open: **http://localhost:8501**

---

## 🔄 How Auto-Update Works

### Frontend (Browser)
- Dashboard automatically refreshes **every 10 seconds**
- JavaScript timer reloads the page
- No manual refresh needed!

### Backend (Database)
- Streamlit cache: **5 seconds TTL**
- Fresh data fetched from Supabase every 5 seconds
- History table updates automatically

### Automation (GitHub Actions)
- Runs **every hour at :02 minutes** (cron: `'2 * * * *'`)
- Backfills missing predictions
- Evaluates pending predictions
- Keeps database current

---

## 🛠️ Maintenance Tools

### Check Database Status
```bash
python db_debug.py
```
**Output:**
- Latest 10 predictions with status
- Gap from current time
- ⚠️ Warning if database > 2 hours behind

### Manual Backfill (If Needed)
```bash
python manual_backfill.py
```
**When to use:**
- Database is > 2 hours behind
- GitHub Actions failed/stopped
- After extended downtime
- First-time setup

### Run Tracker Manually (Testing)
```bash
# Single execution (like GitHub Actions)
GITHUB_ACTIONS=true python tracker.py

# Continuous mode (daemon)
python tracker.py
```

---

## 🎯 How It Works

### Data Flow
```
1. Binance API (every hour)
   ↓
2. tracker.py calculates prediction
   ↓  
3. Saves to Supabase database
   ↓
4. app.py loads from database (cache: 5s)
   ↓
5. Dashboard auto-refreshes (10s)
   ↓
6. User sees latest data!
```

### Prediction Generation
1. Fetch last 500 hourly candles from Binance
2. Calculate volatility (EWM: 6h, 24h, 168h weighted)
3. Generate prediction using Student-t distribution
4. Store lower/upper bounds in database
5. Mark as PENDING until hour closes

### Evaluation (Hourly)
1. Check for closed candles
2. Fetch actual close price from Binance
3. Determine if actual is within [lower, upper]
4. Update `actual_close` and `is_hit` fields
5. Status changes from PENDING → HIT/MISS

---

## 🔍 Troubleshooting

### Problem: "Dashboard not updating"
**Symptoms:** Old values, history shows old dates

**Solutions:**
1. **Check database:**
   ```bash
   python db_debug.py
   ```
   If gap > 2 hours, run backfill:
   ```bash
   python manual_backfill.py
   ```

2. **Hard refresh browser:**
   - Mac: `Cmd + Shift + R`
   - Windows: `Ctrl + Shift + R`
   - Or clear browser cache

3. **Check app is running:**
   ```bash
   # Restart Streamlit
   streamlit run app.py
   ```

### Problem: "All predictions showing PENDING"
**Symptoms:** No HIT/MISS status, everything gray

**Solution:**
```bash
# Run manual backfill to evaluate pending predictions
python manual_backfill.py
```

This will:
- Fetch actual close prices from Binance
- Calculate HIT/MISS for each prediction
- Update database with results

### Problem: "GitHub Actions not running"
**Symptoms:** Database falls behind by days

**Solutions:**
1. **Check GitHub Actions tab**
   - Go to: `https://github.com/YOUR_USERNAME/btc_forecaster/actions`
   - Look for "BTC Forecaster Tracker" workflow
   - Check if it's enabled and running

2. **Verify secrets are set:**
   - Repo Settings → Secrets → Actions
   - Check `SUPABASE_URL` and `SUPABASE_KEY` exist

3. **Manually trigger:**
   - Actions tab → "BTC Forecaster Tracker"
   - Click "Run workflow" button

4. **Local alternative:**
   ```bash
   # Run tracker once per hour
   while true; do
     GITHUB_ACTIONS=true python tracker.py
     sleep 3600  # 1 hour
   done
   ```

### Problem: "Connection error to Supabase"
**Symptoms:** Empty history, connection failed logs

**Solutions:**
1. **Verify `.env` file:**
   ```bash
   cat .env
   ```
   Should show valid `SUPABASE_URL` and `SUPABASE_KEY`

2. **Test connection:**
   ```bash
   python db_debug.py
   ```
   Should connect and show records

3. **Check Supabase project:**
   - Login to supabase.com
   - Verify project is active (not paused)
   - Check database is accessible

---

## 📊 Understanding the Dashboard

### Top Section (Live Data)
- **Current Price:** Real-time BTC price from Binance
- **Support/Resistance:** 99% confidence bounds for next hour
- **Range Width:** How wide the prediction interval is
- **Countdown:** Time until next candle close

### Chart Section
- **Price Chart:** Last 50 candles with live updates
- **Timeframe Selector:** 1M, 5M, 15M, 1H, 4H, 1D views
- **Price Position:** Where current price sits in predicted range
- **Model Internals:** Student-t DF, Scale, Volatility metrics

### History Table
- **Candle Time:** When the prediction was for
- **Lower/Upper:** Predicted price range
- **Actual:** Actual close price (filled after hour ends)
- **Result:** 
  - ✅ **HIT** (green) - Actual within range
  - ❌ **MISS** (red) - Actual outside range  
  - **PENDING** (gray) - Hour not closed yet

### Metrics
- **Coverage:** % of predictions that were correct (target: ~95-99%)
- **Mean Width:** Average prediction range width (lower = better)
- **Winkler Score:** Combined metric (coverage + width penalty)

---

## 🚦 Health Check Checklist

Run this daily to ensure everything is working:

```bash
# 1. Check database status
python db_debug.py

# Expected output:
# ✓ Gap < 2 hours
# ✓ Latest prediction is recent
# ✓ No warnings

# 2. If gap > 2 hours, run backfill
python manual_backfill.py

# 3. Open dashboard
streamlit run app.py
# Check history table shows recent HIT/MISS

# 4. Verify GitHub Actions (weekly)
# Go to Actions tab on GitHub
# Check last run was successful
```

---

## 🎓 Interview Talking Points

### System Architecture
> "Built a real-time Bitcoin forecasting system with automatic data pipelines. Frontend auto-refreshes every 10 seconds, backend uses 5-second cache, and GitHub Actions handles hourly prediction generation and evaluation."

### Problem-Solving Approach
> "When the dashboard stopped updating, I identified three root causes: stale database, missing automation, and long cache TTL. I created monitoring tools first (db_debug.py), then a recovery script (manual_backfill.py), and finally optimized the refresh cycle for better UX."

### Technical Implementation
> "Used Streamlit for the dashboard with JavaScript auto-refresh, Supabase for cloud PostgreSQL storage, and GitHub Actions for serverless cron jobs. Implemented statistical modeling (GBM + Student-t distribution) for price predictions with 99% confidence intervals."

### Production Readiness
> "Added comprehensive error handling, monitoring tools, manual recovery scripts, and documentation. Set up automated testing via GitHub Actions and implemented graceful degradation when database is unavailable."

---

## 📝 Files Overview

| File | Purpose | When to Use |
|------|---------|-------------|
| `app.py` | Main dashboard | Always running |
| `tracker.py` | Generates & evaluates predictions | Auto (GitHub Actions) or manual |
| `manual_backfill.py` | Quick database population | When database is behind |
| `db_debug.py` | Database status check | Daily health check |
| `backtest.py` | Historical validation | One-time or when updating model |
| `.github/workflows/tracker.yml` | Automation config | Runs automatically |

---

## 🔐 Security Notes

- **Never commit `.env` file** - Contains sensitive API keys
- **Use Streamlit Secrets** for production deployment
- **Keep Supabase keys private** - Service role key has full access
- **GitHub Secrets** - Store credentials in repo settings, not code

---

## 🚀 Deployment (Streamlit Cloud)

1. **Push to GitHub:**
   ```bash
   git push origin main
   ```

2. **Configure Streamlit Cloud:**
   - Go to share.streamlit.io
   - Connect GitHub repo
   - Add secrets: `SUPABASE_URL`, `SUPABASE_KEY`
   - Deploy!

3. **Verify:**
   - App auto-starts and loads data
   - History shows recent predictions
   - Auto-refresh works (check every 10s)

---

## ✅ Success Indicators

Your system is working perfectly when:
- ✅ Dashboard shows current hour's prediction
- ✅ History table has HIT/MISS statuses (not all PENDING)
- ✅ Gap in `db_debug.py` is < 1 hour
- ✅ New predictions appear every hour automatically
- ✅ GitHub Actions shows green checkmarks
- ✅ Page auto-refreshes without manual intervention

---

**Built with:** Python · Streamlit · Supabase · NumPy · SciPy · GitHub Actions
**For:** AlphaI × Polaris Hiring Challenge
