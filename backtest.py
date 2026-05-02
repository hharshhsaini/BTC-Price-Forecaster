"""
backtest.py — Rolling Backtest (no data leakage)
BTC/USDT 1-hour candles, GBM + Student-t model.
Run: python backtest.py
"""

import requests
import json
import numpy as np
from scipy import stats
from datetime import datetime, timezone

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


def fetch_bars(symbol="BTCUSDT", interval="1h", limit=720):
    resp = requests.get(BINANCE_URL, params={"symbol": symbol, "interval": interval, "limit": limit})
    resp.raise_for_status()
    data = resp.json()
    closes = [float(bar[4]) for bar in data]
    timestamps = [int(bar[0]) for bar in data]
    return closes, timestamps


def predict_range(closes, n_sim=10000, vol_window=24, fit_window=168):
    """Predict 95% CI for next bar using GBM + Student-t. Uses ONLY closes passed in."""
    log_returns = np.diff(np.log(closes))
    fit_data = log_returns[-fit_window:] if len(log_returns) >= fit_window else log_returns
    df_t, loc_t, scale_t = stats.t.fit(fit_data)
    recent_vol = np.std(log_returns[-vol_window:]) if len(log_returns) >= vol_window else np.std(log_returns)
    global_vol = np.std(fit_data)
    vol_ratio = recent_vol / global_vol if global_vol > 0 else 1.0
    adjusted_scale = scale_t * vol_ratio
    last_price = closes[-1]
    sim_returns = stats.t.rvs(df=df_t, loc=loc_t, scale=adjusted_scale, size=n_sim)
    sim_prices = last_price * np.exp(sim_returns)
    lower = float(np.percentile(sim_prices, 2.5))
    upper = float(np.percentile(sim_prices, 97.5))
    return lower, upper


def evaluate(records):
    alpha = 0.05
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
            winklers.append(width + (2 / alpha) * miss)
    return {
        "coverage_95": round(np.mean(coverage_flags), 4),
        "mean_width": round(np.mean(widths), 2),
        "mean_winkler_95": round(np.mean(winklers), 2),
    }


def run_backtest():
    print("Fetching 720 bars from Binance mirror...")
    closes, timestamps = fetch_bars(limit=720)
    print(f"Got {len(closes)} bars. Running rolling backtest...")

    records = []
    MIN_HISTORY = 50  # need at least 50 bars to fit

    for i in range(MIN_HISTORY, len(closes)):
        # STRICT no-peek: only use closes[0..i-1] to predict closes[i]
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
    print(f"  Coverage 95%   : {metrics['coverage_95']*100:.2f}%  (target ~95%)")
    print(f"  Mean width     : ${metrics['mean_width']:,.2f}")
    print(f"  Mean Winkler   : ${metrics['mean_winkler_95']:,.2f}  (lower = better)")
    print("========================")
    print("Saved to backtest_results.jsonl")
    return metrics


if __name__ == "__main__":
    run_backtest()
