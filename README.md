# ₿ BTC Price Forecaster

> AlphaI × Polaris Hiring Challenge — GBM + Student-t Model · 95% Confidence Interval

A real-time Bitcoin price range forecasting dashboard that predicts where
BTC/USDT will land **one hour from now** with 95% confidence, updating
every 10 seconds using live Binance data.

---

## 🔗 Live Demo

**[https://btc-price-forecaster.streamlit.app/](https://btc-price-forecaster.streamlit.app/)**

---

## What It Does

Every hour, a new 1-hour candle closes on Bitcoin's chart.
This system predicts the **95% confidence price range** for the next candle using:

- **Geometric Brownian Motion (GBM)** simulation with 10,000 Monte Carlo paths
- **Student-t distribution** (not normal) to correctly handle Bitcoin's fat tails
- **Volatility clustering** — recent volatility window (24 bars) scales the prediction width
- **Live price feed** — Binance REST ticker refreshes every 10 seconds
- **Intra-candle updates** — model re-runs with live price as provisional input

---

## Project Structure

```
btc_forecaster/
├── app.py                    # Streamlit live dashboard
├── backtest.py               # 30-day rolling backtest (720 bars)
├── backtest_results.jsonl    # Backtest output (one prediction per line)
├── prediction_history.jsonl  # Live prediction log (grows over time)
└── requirements.txt          # Dependencies
```

---

## Backtest Results (720 bars, 30 days)

| Metric | Value | Target |
|--------|-------|--------|
| Coverage 95% | 93.56% | ~95% |
| Mean Width | $1,202 | lower = better |
| Mean Winkler Score | $1,754 | lower = better |

Backtest uses a **strict no-peek rolling window** — when predicting bar N,
only bars 0..N-1 are used. Zero data leakage.

---

## Dashboard Features

- **Live BTC price** — REST ticker, refreshes every 10 seconds (`● LIVE (10s)`)
- **Predicted 95% range** — lower/upper bounds for the next 1-hour candle
- **Price chart** — last 50 bars with forecast ribbon shaded
- **Backtest metrics** — coverage, mean width, Winkler score (read from file, not hardcoded)
- **Prediction history** — full log of past predictions with actuals backfilled automatically
- **Gap detection** — unvisited candles shown as "not visited" rows
- **Auto-refresh** — Streamlit autorefresh every 10 seconds, no manual reload needed

---

## Key Concepts

### 1. No Peeking
When predicting bar N, only bars 0..N-1 are used. This is enforced
strictly in the rolling backtest loop. No data leakage possible.

### 2. Volatility Clustering
Uses a short recent window (last 24 bars) to estimate current volatility.
Calm hours → narrow range. Volatile hours → wider range.

### 3. Fat Tails
Bitcoin has more extreme moves than a normal distribution predicts.
`scipy.stats.t` (Student-t) is used throughout — never `scipy.stats.norm`.

---

## How to Run Locally

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the backtest (generates backtest_results.jsonl)
```bash
python backtest.py
```
Fetches 720 BTCUSDT 1-hour bars, runs rolling predictions,
saves results to `backtest_results.jsonl`, prints metrics.

### 3. Launch the dashboard
```bash
streamlit run app.py
```

---

## Data Source

All data comes from Binance's public mirror — **no API key required**:

```
https://data-api.binance.vision/api/v3/klines
https://data-api.binance.vision/api/v3/ticker/24hr
```

This endpoint is geo-safe and works from all regions including India.

---

## Deployment

Hosted on **Streamlit Community Cloud** (free tier).
The app sleeps after inactivity and wakes in ~30 seconds on next visit.

---

## Built For

**AlphaI × Polaris Hiring Challenge**
GBM + Student-t fat-tail model · Data: Binance public mirror · No API key required
