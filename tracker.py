import os
import time
import requests
import numpy as np
import scipy.stats as stats
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Constants
BINANCE = "https://api.binance.com/api/v3"
ALPHA = 0.01  # 99% CI
DF = 2.5
T_MULT = 7.16 # scipy.stats.t.ppf(1 - ALPHA/2, df=DF)

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_url or not supabase_key:
    print("Missing Supabase credentials in .env")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

def ewm_vol(rets, span):
    if len(rets) == 0: return 0.001
    weights = np.exp(-np.arange(len(rets))[::-1]/span)
    w_sum = np.sum(weights)
    mean = np.sum(rets * weights) / w_sum
    var = np.sum(weights * (rets - mean)**2) / w_sum
    return np.sqrt(var)

def get_binance_klines(limit=500):
    url = f"{BINANCE}/klines?symbol=BTCUSDT&interval=1h&limit={limit}"
    res = requests.get(url)
    res.raise_for_status()
    return res.json()

def process_tracker():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for updates...")
    try:
        # Fetch 500 klines to have history for vol of older candles
        klines = get_binance_klines(limit=500)
    except Exception as e:
        print(f"Failed to fetch Binance data: {e}")
        return

    # Map for easy lookup: candle_open_iso -> close_price
    kline_map = {}
    for k in klines:
        dt = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat()
        kline_map[dt] = float(k[4])

    # 1. EVALUATION (Update PENDING records)
    try:
        res = supabase.table("predictions").select("*").is_("actual_close", "null").execute()
        pending = res.data
        if pending:
            for p in pending:
                p_dt = p["candle_time"]
                # Normalize time format for matching
                p_dt_norm = datetime.fromisoformat(p_dt.replace('Z', '+00:00')).isoformat()
                
                # Check if this candle has finished (it's older than the current open candle)
                current_candle_dt = datetime.fromtimestamp(klines[-1][0] / 1000, tz=timezone.utc).isoformat()
                
                if p_dt_norm < current_candle_dt and p_dt_norm in kline_map:
                    actual = kline_map[p_dt_norm]
                    is_hit = bool(p["lower_bound"] <= actual <= p["upper_bound"])
                    print(f"Resolving {p_dt_norm}: Close={actual}, Hit={is_hit}")
                    supabase.table("predictions").update({
                        "actual_close": actual,
                        "is_hit": is_hit
                    }).eq("id", p["id"]).execute()
    except Exception as e:
        print(f"Error during evaluation: {e}")

    # 2. BACKFILLING & PREDICTION
    # We check the last 168 candles (1 week) to ensure no gaps
    for i in range(len(klines) - 168, len(klines)):
        k = klines[i]
        candle_dt = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat()
        
        # Check if we already have this prediction
        try:
            existing = supabase.table("predictions").select("id").eq("candle_time", candle_dt).execute()
            if not existing.data:
                # Need to generate prediction for this candle!
                # Volatility is calculated using candles *before* this one
                prev_klines = klines[:i]
                if len(prev_klines) < 168: continue
                
                prev_closes = [float(pk[4]) for pk in prev_klines]
                current_price = prev_closes[-1]
                log_rets = np.diff(np.log(prev_closes))
                
                recent = log_rets[-168:]
                v6 = ewm_vol(recent[-6:], 6)
                v24 = ewm_vol(recent[-24:], 24)
                v168 = ewm_vol(recent, 168)
                vol = max(0.5*v6 + 0.3*v24 + 0.2*v168, v168*0.5)
                
                lower = current_price * np.exp(-T_MULT * vol)
                upper = current_price * np.exp(T_MULT * vol)
                
                print(f"Gap found! Backfilling prediction for {candle_dt}")
                supabase.table("predictions").insert({
                    "candle_time": candle_dt,
                    "lower_bound": float(lower),
                    "upper_bound": float(upper)
                }).execute()
        except Exception as e:
            print(f"Error backfilling {candle_dt}: {e}")

if __name__ == "__main__":
    print("Starting robust tracker daemon (Gap-filling mode)...")
    while True:
        process_tracker()
        # Sleep until the start of the next minute
        time.sleep(60 - datetime.now().second)
