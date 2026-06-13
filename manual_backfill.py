#!/usr/bin/env python3
"""
Manual Backfill Script
Fills ALL gaps in the database by fetching recent Binance data.
Run this once to populate the database with recent predictions.

Usage:
    python manual_backfill.py
"""

import os
import requests
import numpy as np
from datetime import datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Constants
BINANCE = "https://api.binance.com/api/v3"
ALPHA = 0.01  # 99% CI
DF = 2.5
T_MULT = 7.16  # scipy.stats.t.ppf(1 - ALPHA/2, df=DF)

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_url or not supabase_key:
    print("❌ Missing Supabase credentials in .env")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

def ewm_vol(rets, span):
    if len(rets) == 0:
        return 0.001
    weights = np.exp(-np.arange(len(rets))[::-1] / span)
    w_sum = np.sum(weights)
    mean = np.sum(rets * weights) / w_sum
    var = np.sum(weights * (rets - mean) ** 2) / w_sum
    return np.sqrt(var)

def get_binance_klines(limit=500):
    url = f"{BINANCE}/klines?symbol=BTCUSDT&interval=1h&limit={limit}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def backfill_all():
    print("=" * 60)
    print("   BTC FORECASTER - MANUAL BACKFILL")
    print("=" * 60)
    print("\nFetching latest 500 candles from Binance...")
    
    try:
        klines = get_binance_klines(limit=500)
    except Exception as e:
        print(f"❌ Failed to fetch Binance data: {e}")
        return

    print(f"✓ Fetched {len(klines)} candles")
    
    # Build kline_map for evaluation
    kline_map = {}
    for k in klines:
        dt = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat()
        kline_map[dt] = float(k[4])

    print("\n" + "=" * 60)
    print("STEP 1: Evaluating Pending Predictions")
    print("=" * 60)
    
    # Evaluate pending predictions
    try:
        res = supabase.table("predictions").select("*").is_("actual_close", "null").execute()
        pending = res.data
        evaluated = 0
        
        if pending:
            current_candle_dt = datetime.fromtimestamp(klines[-1][0] / 1000, tz=timezone.utc).isoformat()
            
            for p in pending:
                p_dt = p["candle_time"]
                p_dt_norm = datetime.fromisoformat(p_dt.replace('Z', '+00:00')).isoformat()
                
                if p_dt_norm < current_candle_dt and p_dt_norm in kline_map:
                    actual = kline_map[p_dt_norm]
                    is_hit = bool(p["lower_bound"] <= actual <= p["upper_bound"])
                    supabase.table("predictions").update({
                        "actual_close": actual,
                        "is_hit": is_hit
                    }).eq("id", p["id"]).execute()
                    evaluated += 1
        
        print(f"✓ Evaluated {evaluated} pending predictions")
    except Exception as e:
        print(f"⚠️  Error during evaluation: {e}")

    print("\n" + "=" * 60)
    print("STEP 2: Backfilling Missing Predictions")
    print("=" * 60)
    
    # Backfill gaps (last 168 candles)
    backfilled = 0
    start_idx = max(0, len(klines) - 168)
    
    for i in range(start_idx, len(klines)):
        k = klines[i]
        candle_dt = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat()
        
        try:
            # Check if prediction already exists
            existing = supabase.table("predictions").select("id").eq("candle_time", candle_dt).execute()
            
            if not existing.data:
                # Generate prediction
                prev_klines = klines[:i]
                if len(prev_klines) < 168:
                    continue
                
                prev_closes = [float(pk[4]) for pk in prev_klines]
                current_price = prev_closes[-1]
                log_rets = np.diff(np.log(prev_closes))
                
                recent = log_rets[-168:]
                v6 = ewm_vol(recent[-6:], 6)
                v24 = ewm_vol(recent[-24:], 24)
                v168 = ewm_vol(recent, 168)
                vol = max(0.5 * v6 + 0.3 * v24 + 0.2 * v168, v168 * 0.5)
                
                lower = current_price * np.exp(-T_MULT * vol)
                upper = current_price * np.exp(T_MULT * vol)
                
                supabase.table("predictions").insert({
                    "candle_time": candle_dt,
                    "lower_bound": float(lower),
                    "upper_bound": float(upper)
                }).execute()
                
                backfilled += 1
                print(f"  ✓ {candle_dt[:16]} | ${lower:,.0f} - ${upper:,.0f}")
        except Exception as e:
            print(f"  ⚠️  Error for {candle_dt}: {e}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✓ Backfilled: {backfilled} predictions")
    print(f"✓ Evaluated: {evaluated} pending predictions")
    print("\n✅ Backfill complete! Your database is now up to date.")
    print("\nNext steps:")
    print("  1. Run: streamlit run app.py")
    print("  2. Check prediction history in the dashboard")
    print("=" * 60)

if __name__ == "__main__":
    backfill_all()
