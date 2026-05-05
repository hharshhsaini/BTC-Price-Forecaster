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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Waking up to process...")
    try:
        klines = get_binance_klines(limit=500)
    except Exception as e:
        print(f"Failed to fetch Binance data: {e}")
        return

    closes = [float(k[4]) for k in klines]
    current_price = closes[-1]
    
    # Klines format: [open_time, open, high, low, close, volume, close_time, ...]
    current_candle_open_ts = klines[-1][0]
    current_candle_open_dt = datetime.fromtimestamp(current_candle_open_ts / 1000, tz=timezone.utc)
    
    # 1. Catch-up Evaluation Logic
    # Find all PENDING predictions (actual_close is null) where candle_time < current_candle_open_dt
    try:
        res = supabase.table("predictions").select("*").is_("actual_close", "null").lt("candle_time", current_candle_open_dt.isoformat()).execute()
        pending = res.data
        if pending:
            print(f"Found {len(pending)} pending historical predictions to evaluate.")
            
            # Map klines to a dictionary of open_dt string -> actual_close
            kline_map = {}
            for k in klines:
                dt = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat()
                kline_map[dt] = float(k[4]) # close price
            
            for p in pending:
                p_dt = p["candle_time"]
                # some DBs return +00:00, python isoformat might differ, try to match
                if p_dt in kline_map:
                    actual = kline_map[p_dt]
                    lower = p["lower_bound"]
                    upper = p["upper_bound"]
                    is_hit = bool(lower <= actual <= upper)
                    
                    print(f"Updating PENDING candle {p_dt}: Close={actual}, Hit={is_hit}")
                    supabase.table("predictions").update({
                        "actual_close": actual,
                        "is_hit": is_hit
                    }).eq("id", p["id"]).execute()
                else:
                    # Sometimes time formats differ slightly (e.g. trailing Z vs +00:00). We normalize
                    try:
                        p_dt_obj = datetime.fromisoformat(p_dt.replace('Z', '+00:00'))
                        p_dt_norm = p_dt_obj.isoformat()
                        if p_dt_norm in kline_map:
                            actual = kline_map[p_dt_norm]
                            lower = p["lower_bound"]
                            upper = p["upper_bound"]
                            is_hit = bool(lower <= actual <= upper)
                            print(f"Updating PENDING candle {p_dt}: Close={actual}, Hit={is_hit}")
                            supabase.table("predictions").update({
                                "actual_close": actual,
                                "is_hit": is_hit
                            }).eq("id", p["id"]).execute()
                    except:
                        pass
    except Exception as e:
        print(f"Error during catch-up evaluation: {e}")

    # 2. Generate prediction for the *current* open candle
    log_rets = np.diff(np.log(closes))
    recent = log_rets[-168:]
    v6 = ewm_vol(recent[-6:], 6)
    v24 = ewm_vol(recent[-24:], 24)
    v168 = ewm_vol(recent, 168)
    vol = max(0.5*v6 + 0.3*v24 + 0.2*v168, v168*0.5)
    
    lower_bound = current_price * np.exp(-T_MULT * vol)
    upper_bound = current_price * np.exp(T_MULT * vol)
    
    # 3. Upsert prediction into DB for the current open candle
    try:
        data = {
            "candle_time": current_candle_open_dt.isoformat(),
            "lower_bound": float(lower_bound),
            "upper_bound": float(upper_bound),
        }
        existing = supabase.table("predictions").select("id").eq("candle_time", current_candle_open_dt.isoformat()).execute()
        if not existing.data:
            supabase.table("predictions").insert(data).execute()
            print(f"New prediction inserted for {current_candle_open_dt}.")
        else:
            # Optionally update the live bounds while the candle is open
            pass 
    except Exception as e:
        print(f"Error saving prediction: {e}")

if __name__ == "__main__":
    print("Starting continuous tracker daemon...")
    while True:
        process_tracker()
        
        # Calculate how many seconds until the next minute starts to keep it aligned
        now = datetime.now()
        sleep_secs = 60 - now.second
        
        # We only really need to run this every ~5 minutes or so, since we are dealing with 1h candles, 
        # but running every 1 minute ensures we catch the hour boundary precisely.
        time.sleep(sleep_secs)
