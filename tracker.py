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
    if not rets: return 0.001
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running tracker...")
    klines = get_binance_klines(limit=500)
    
    closes = [float(k[4]) for k in klines]
    current_price = closes[-1]
    
    # Klines format: [open_time, open, high, low, close, volume, close_time, ...]
    current_candle_open_ts = klines[-1][0]
    current_candle_open_dt = datetime.fromtimestamp(current_candle_open_ts / 1000, tz=timezone.utc)
    next_candle_open_dt = current_candle_open_dt + timedelta(hours=1)
    
    # 1. Evaluate the *previous* candle (which just closed)
    previous_candle_open_ts = klines[-2][0]
    previous_candle_open_dt = datetime.fromtimestamp(previous_candle_open_ts / 1000, tz=timezone.utc)
    previous_close_price = float(klines[-2][4])
    
    # Check if we have a prediction for the previous candle in the DB
    try:
        prev_res = supabase.table("predictions").select("*").eq("candle_time", previous_candle_open_dt.isoformat()).execute()
        if prev_res.data:
            record = prev_res.data[0]
            if record.get("actual_close") is None:
                # We need to evaluate it
                lower = record["lower_bound"]
                upper = record["upper_bound"]
                is_hit = bool(lower <= previous_close_price <= upper)
                
                print(f"Evaluating previous candle ({previous_candle_open_dt}): Close={previous_close_price}, Bounds=[{lower}, {upper}], Hit={is_hit}")
                
                supabase.table("predictions").update({
                    "actual_close": previous_close_price,
                    "is_hit": is_hit
                }).eq("id", record["id"]).execute()
    except Exception as e:
        print(f"Error evaluating previous candle: {e}")
    
    # 2. Generate prediction for the *next* candle (the one we are predicting)
    # The current candle is still open, we are predicting where it will be at close / where the next one opens
    log_rets = np.diff(np.log(closes))
    recent = log_rets[-168:]
    v6 = ewm_vol(recent[-6:], 6)
    v24 = ewm_vol(recent[-24:], 24)
    v168 = ewm_vol(recent, 168)
    vol = max(0.5*v6 + 0.3*v24 + 0.2*v168, v168*0.5)
    
    lower_bound = current_price * np.exp(-T_MULT * vol)
    upper_bound = current_price * np.exp(T_MULT * vol)
    
    print(f"Prediction for candle {current_candle_open_dt}: Lower={lower_bound}, Upper={upper_bound}")
    
    # 3. Save prediction to DB (upsert based on candle_time)
    try:
        data = {
            "candle_time": current_candle_open_dt.isoformat(),
            "lower_bound": float(lower_bound),
            "upper_bound": float(upper_bound),
        }
        # Insert or update
        # Because we only want 1 prediction per candle, we can check if it exists
        existing = supabase.table("predictions").select("id").eq("candle_time", current_candle_open_dt.isoformat()).execute()
        if not existing.data:
            supabase.table("predictions").insert(data).execute()
            print("Successfully inserted prediction.")
        else:
            supabase.table("predictions").update(data).eq("id", existing.data[0]["id"]).execute()
            print("Successfully updated prediction.")
    except Exception as e:
        print(f"Error saving prediction: {e}")

if __name__ == "__main__":
    process_tracker()
