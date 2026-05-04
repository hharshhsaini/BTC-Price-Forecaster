"""
backtest.py — Rolling Backtest (no data leakage)
BTC/USDT 1-hour candles, GBM + Student-t model.
Run: python backtest.py
"""

import json
import numpy as np
from scipy import stats
from datetime import datetime, timezone
import requests
import time

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
ALPHA = 0.01

def fetch_bars(symbol="BTCUSDT", interval="1h", limit=720):
    resp = requests.get(BINANCE_URL, params={"symbol": symbol, "interval": interval, "limit": limit})
    resp.raise_for_status()
    data = resp.json()
    closes = [float(bar[4]) for bar in data]
    timestamps = [int(bar[0]) for bar in data]
    return closes, timestamps

def compute_adaptive_volatility(log_returns, short=6, medium=24, long=168):
    def ewm_vol(returns, span):
        weights = np.exp(-np.arange(len(returns))[::-1] / span)
        weights /= weights.sum()
        mean = np.sum(weights * returns)
        variance = np.sum(weights * (returns - mean) ** 2)
        return np.sqrt(variance)
    if len(log_returns) < long:
        return np.std(log_returns), None
    v_short = ewm_vol(log_returns[-short:], short)
    v_medium = ewm_vol(log_returns[-medium:], medium)
    v_long = ewm_vol(log_returns[-long:], long)
    blended = 0.5 * v_short + 0.3 * v_medium + 0.2 * v_long
    floor = v_long * 0.5
    blended = max(blended, floor)
    return blended, {"short": v_short, "medium": v_medium, "long": v_long}

def fit_student_t(returns):
    if len(returns) < 3: return 3.0, 0.0, 1e-4
    df, loc, scale = stats.t.fit(returns)
    return max(df, 2.01), loc, scale

def predict_range(closes, n_sims=10000, short_w=6, med_w=24, long_w=168, alpha=ALPHA):
    log_returns = np.diff(np.log(closes))
    fit_returns = log_returns[-long_w:] if len(log_returns) >= long_w else log_returns
    df, loc, scale = fit_student_t(fit_returns)
    blended_vol, vol_breakdown = compute_adaptive_volatility(log_returns, short_w, med_w, long_w)
    if vol_breakdown:
        global_vol = np.std(fit_returns)
        vol_ratio = blended_vol / global_vol if global_vol > 1e-12 else 1.0
    else:
        vol_ratio = 1.0
    scaled_scale = scale * vol_ratio
    rng = np.random.default_rng(int(time.time()))
    sampled = stats.t.rvs(df=df, loc=loc, scale=scaled_scale, size=n_sims, random_state=rng)
    next_prices = closes[-1] * np.exp(sampled)
    lower_pct = (alpha / 2) * 100
    upper_pct = (1 - alpha / 2) * 100
    lower = float(np.percentile(next_prices, lower_pct))
    upper = float(np.percentile(next_prices, upper_pct))
    return lower, upper

def evaluate(records):
    coverage_flags, widths, winklers = [], [], []
    for r in records:
        lo, hi, actual = r["lower"], r["upper"], r["actual"]
        width = hi - lo
        inside = lo <= actual <= hi
        coverage_flags.append(int(inside))
        widths.append(width)
        if inside:
            winklers.append(width)
        else:
            miss = min(abs(actual - lo), abs(actual - hi))
            winklers.append(width + (2 / ALPHA) * miss)
    return {
        "coverage": round(np.mean(coverage_flags), 4),
        "mean_width": round(np.mean(widths), 2),
        "mean_winkler": round(np.mean(winklers), 2),
    }

def run_backtest():
    print("Fetching 720 bars from Binance mirror...")
    closes, timestamps = fetch_bars(limit=720)
    print(f"Got {len(closes)} bars. Running rolling backtest...")

    records = []
    MIN_HISTORY = 168

    for i in range(MIN_HISTORY, len(closes)):
        history = closes[:i]
        actual = closes[i]
        ts_ms = timestamps[i]
        ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

        lower, upper = predict_range(history)
        record = {
            "timestamp": ts_iso,
            "lower": round(lower, 2),
            "upper": round(upper, 2),
            "actual": round(actual, 2),
        }
        records.append(record)

        if i % 50 == 0:
            print(f"  Bar {i}/{len(closes)-1} — actual={actual:.2f}, range=[{lower:.2f}, {upper:.2f}]")

    with open("backtest_results.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    metrics = evaluate(records)
    print("\n=== BACKTEST RESULTS ===")
    print(f"  Bars predicted : {len(records)}")
    print(f"  Coverage       : {metrics['coverage']*100:.2f}%  (target ~{(1-ALPHA)*100:.0f}%)")
    print(f"  Mean width     : ${metrics['mean_width']:,.2f}")
    print(f"  Mean Winkler   : ${metrics['mean_winkler']:,.2f}  (lower = better)")
    print("========================")
    print("Saved to backtest_results.jsonl")
    return metrics

if __name__ == "__main__":
    run_backtest()
