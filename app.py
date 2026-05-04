import textwrap


import json, os, time, math
from datetime import datetime, timezone, timedelta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from scipy import stats
import streamlit.components.v1 as components

def clean_html(html_str):
    return '\n'.join(line.strip() for line in html_str.split('\n'))

# --- Page Config ---
st.set_page_config(
    page_title="BTC Price Forecaster",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Constants ---
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
BINANCE_PARAMS = {"symbol": "BTCUSDT", "interval": "1h", "limit": 500}
HISTORY_FILE = "prediction_history.jsonl"
BACKTEST_FILE = "backtest_results.jsonl"
ALPHA = 0.03

# --- Design System CSS ---
st.markdown(clean_html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

[data-testid="stAppViewContainer"] {
    background: #050508;
    background-image:
        radial-gradient(ellipse at 20% 50%, rgba(247,147,26,0.04) 0%, transparent 60%),
        radial-gradient(ellipse at 80% 20%, rgba(99,102,241,0.04) 0%, transparent 60%);
}
[data-testid="block-container"] { max-width: 100% !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; padding-bottom: 0 !important; }
section[data-testid="stSidebar"] { display: none; }
[data-testid="stExpander"] { border: 1px solid rgba(255,255,255,0.06) !important; border-radius: 12px !important; background: rgba(255,255,255,0.02) !important; }

.glass {
    min-height: 110px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 20px 24px;
    transition: border-color 0.2s ease;
}
.glass:hover { border-color: rgba(255,255,255,0.12); }

.glass-accent {
    background: rgba(247,147,26,0.05);
    border: 1px solid rgba(247,147,26,0.15);
    border-radius: 16px;
    backdrop-filter: blur(20px);
    padding: 20px 24px;
}

.label {
    font-size: 10px; font-weight: 600; letter-spacing: 0.12em;
    color: rgba(255,255,255,0.3); text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
}
.value-xl {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #ffffff !important;
    font-family: 'SF Mono', monospace !important;
    line-height: 1.2 !important;
}
.value-lg { font-size: 1.6rem; font-weight: 600; color: #ffffff; }
.value-md { font-size: 1.1rem; font-weight: 500; color: rgba(255,255,255,0.85); }

.up { color: #10b981; } .down { color: #ef4444; }
.warn { color: #f59e0b; } .info { color: #6366f1; }
.btc { color: #F7931A; }

.pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 100px;
    font-size: 11px; font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
}
.pill-up { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.2); }
.pill-down { background: rgba(239,68,68,0.12); color: #ef4444; border: 1px solid rgba(239,68,68,0.2); }
.pill-info { background: rgba(99,102,241,0.12); color: #818cf8; border: 1px solid rgba(99,102,241,0.2); }

.divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent);
    margin: 12px 0;
}

.progress-track {
    height: 4px; background: rgba(255,255,255,0.06);
    border-radius: 100px; overflow: hidden; margin-top: 8px;
}
.progress-fill {
    height: 100%; border-radius: 100px; transition: width 0.6s ease;
}

@keyframes scroll {
    0%   { transform: translateX(0); }
    100% { transform: translateX(-33.33%); }
}
.ticker-wrap {
    overflow: hidden;
    background: rgba(255,255,255,0.02);
    border-top: 1px solid rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding: 8px 0;
}
.ticker-content {
    display: inline-block; white-space: nowrap;
    animation: scroll 30s linear infinite;
    font-size: 11px; font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.02em;
}

.btc-table { width: 100%; border-collapse: collapse; }
.btc-table th {
    font-size: 9px; font-weight: 600; letter-spacing: 0.1em;
    color: rgba(255,255,255,0.25); text-transform: uppercase;
    padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.05);
    text-align: left; font-family: 'JetBrains Mono', monospace;
}
.btc-table td {
    padding: 10px 12px; font-size: 13px; color: rgba(255,255,255,0.75);
    border-bottom: 1px solid rgba(255,255,255,0.03);
    font-family: 'JetBrains Mono', monospace;
}
.btc-table tr:hover td { background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.95); }

.glow-orange { box-shadow: 0 0 30px rgba(247,147,26,0.08); }
.glow-green  { box-shadow: 0 0 30px rgba(16,185,129,0.08); }
.glow-red    { box-shadow: 0 0 30px rgba(239,68,68,0.08); }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
</style>
"""), unsafe_allow_html=True)


# ============================================================================
# DATA FUNCTIONS
# ============================================================================

@st.cache_data(ttl=3600)
def load_backtest_metrics(path=BACKTEST_FILE):
    if not os.path.exists(path):
        return None
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try: records.append(json.loads(line))
                except Exception: pass
    if not records: return None
    coverage_flags, widths, winklers = [], [], []
    for r in records:
        lo, hi, actual = float(r["lower"]), float(r["upper"]), float(r["actual"])
        width = hi - lo
        inside = lo <= actual <= hi
        coverage_flags.append(int(inside))
        widths.append(width)
        if inside: winklers.append(width)
        else:
            miss = min(abs(actual - lo), abs(actual - hi))
            winklers.append(width + (2 / ALPHA) * miss)
    return {
        "coverage": round(np.mean(coverage_flags) * 100, 2),
        "mean_width": round(np.mean(widths), 2),
        "mean_winkler": round(np.mean(winklers), 2),
        "n": len(records),
        "records": records,
    }


def clean_history(path=HISTORY_FILE):
    if not os.path.exists(path): return
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: r = json.loads(line)
            except Exception: continue
            co = r.get("candle_open")
            if not co or co in ("\u2014", "null", None): continue
            rows.append(r)
    seen = {}
    for r in rows: seen[r["candle_open"]] = r
    clean = list(seen.values())
    with open(path, "w") as f:
        for r in clean: f.write(json.dumps(r) + "\n")

clean_history()


@st.cache_data(ttl=10)
def fetch_live_ticker():
    try:
        resp = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr",
                            params={"symbol": "BTCUSDT"}, timeout=5)
        data = resp.json()
        return float(data["lastPrice"]), float(data["priceChangePercent"])
    except Exception:
        return None, None


@st.cache_data(ttl=300)
def fetch_klines():
    resp = requests.get(BINANCE_URL, params=BINANCE_PARAMS, timeout=30)
    resp.raise_for_status()
    raw_bars = resp.json()
    closes = np.array([float(k[4]) for k in raw_bars])
    timestamps_ms = [int(k[0]) for k in raw_bars]
    return closes, timestamps_ms, raw_bars


def save_prediction(record, path=HISTORY_FILE):
    co = record.get("candle_open")
    if not co or co in ("\u2014", None, "null"): return
    existing = []
    try:
        with open(path) as f: existing = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError: pass
    existing = [r for r in existing if r.get("candle_open") != co]
    existing.append(record)
    existing.sort(key=lambda r: r.get("candle_open", ""), reverse=True)
    with open(path, "w") as f:
        for r in existing: f.write(json.dumps(r) + "\n")


def backfill_actuals(history_path=HISTORY_FILE):
    try:
        with open(history_path) as f: rows = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError: return []
    if not rows: return rows
    resp = requests.get(BINANCE_URL, params={"symbol": "BTCUSDT", "interval": "1h", "limit": 500})
    bars = resp.json()
    bar_map = {int(b[0]): float(b[4]) for b in bars}
    updated = False
    for row in rows:
        if row.get("actual_at_close") is None:
            try:
                dt = datetime.fromisoformat(row["candle_open"])
                ts_ms = int(dt.timestamp() * 1000)
                if ts_ms in bar_map:
                    row["actual_at_close"] = round(bar_map[ts_ms], 2)
                    row["in_range"] = row["lower"] <= row["actual_at_close"] <= row["upper"]
                    updated = True
            except Exception: pass
    if updated:
        with open(history_path, "w") as f:
            for row in rows: f.write(json.dumps(row) + "\n")
    return rows


# ============================================================================
# MODEL FUNCTIONS
# ============================================================================

def compute_live_coverage(history):
    resolved = [r for r in history if r.get('in_range') is not None]
    if not resolved: return None
    hits = sum(1 for r in resolved if r.get('in_range'))
    return hits / len(resolved)


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


def predict_next(closes, n_sims=10000, short_w=6, med_w=24, long_w=168,
                 alpha=0.05):
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
    return {
        "lower": lower, "upper": upper,
        "df": df, "loc": loc, "scale": scale, "scaled_scale": scaled_scale,
        "blended_vol": blended_vol, "vol_breakdown": vol_breakdown,
        "n_sims": n_sims, "simulated_prices": next_prices,
        "log_returns": log_returns,
    }


def confidence_score(log_returns, lower, upper, current_price):
    width = upper - lower
    recent_vol_dollar = np.std(log_returns[-24:]) * current_price * np.sqrt(24)
    narrowness = max(0, 1 - (width / (recent_vol_dollar * 2)))
    mid = (upper + lower) / 2
    centering = 1 - abs(current_price - mid) / (width / 2 + 1e-9)
    centering = max(0, min(1, centering))
    return int((0.6 * narrowness + 0.4 * centering) * 100)


def time_to_next_candle():
    now = datetime.now(timezone.utc)
    total_seconds_past = now.minute * 60 + now.second
    seconds_remaining = 3600 - total_seconds_past
    m = seconds_remaining // 60
    s = seconds_remaining % 60
    progress = total_seconds_past / 3600
    return f"{m:02d}:{s:02d}", progress


# ============================================================================
# GAP DETECTOR
# ============================================================================

def add_display_gaps(rows):
    if not rows:
        return rows
    parsed = []
    for r in rows:
        try:
            dt = datetime.fromisoformat(r["candle_open"])
            parsed.append((dt, r))
        except Exception:
            pass
    if not parsed:
        return rows
    parsed.sort(key=lambda x: x[0], reverse=True)
    now_utc = datetime.now(timezone.utc)
    result = []
    i = 0
    while i < len(parsed):
        dt, row = parsed[i]
        result.append(row)
        if i + 1 < len(parsed):
            next_dt = parsed[i + 1][0]
            gap_hours = int((dt - next_dt).total_seconds() / 3600) - 1
            if gap_hours == 1:
                gap_dt = dt - timedelta(hours=1)
                if gap_dt < now_utc:
                    result.append({"candle_open": gap_dt.isoformat(), "lower": None, "upper": None,
                                   "actual_at_close": None, "in_range": None, "_is_gap": True})
            elif gap_hours > 1:
                gap_dt = dt - timedelta(hours=1)
                if gap_dt < now_utc:
                    result.append({"candle_open": gap_dt.isoformat(), "lower": None, "upper": None,
                                   "actual_at_close": None, "in_range": None, "_is_gap": True})
                    result.append({"_is_summary": True, "_count": gap_hours - 1})
        i += 1
    return result

# ============================================================================
# UI COMPONENTS
# ============================================================================

def render_header(live_price, change_pct, generated_at):
    st.markdown(clean_html("""
    <div style="text-align:center; margin-bottom: 2rem; margin-top: 1rem;">
        <h1 style="color:#F7931A; font-size:2.5rem; font-weight:700; margin-bottom:0;">
            ₿ BTC Price Forecaster
        </h1>
        <p style="color:rgba(255,255,255,0.6); font-size:0.85rem; margin-top:0.2rem;">
            AlphaI × Polaris Hiring Challenge &nbsp;·&nbsp; GBM + Student-t Model &nbsp;·&nbsp; 95% Confidence Interval
        </p>
    </div>
    """), unsafe_allow_html=True)


def render_kpi_cards(live_price, lower, upper, coverage, 
                      mean_width, winkler, confidence, countdown, time_elapsed_pct):
    
    width = upper - lower
    mid = (lower + upper) / 2
    
    # Coverage color
    if abs(coverage - 0.96) < 0.015:
        cov_color = "#10b981"
        cov_label = "ON TARGET"
    elif coverage > 0.965:
        cov_color = "#6366f1"
        cov_label = "WIDE"
    else:
        cov_color = "#f59e0b"
        cov_label = "TIGHT"
    
    cards_html = f"""
    <div style="display:grid; grid-template-columns:repeat(5,1fr); 
                gap:12px; padding:16px 24px;">
        
        <!-- Card 1: Current Price -->
        <div class="glass glow-orange">
            <div class="label" style="margin-bottom:8px;">
                <svg width="10" height="10" viewBox="0 0 10 10" style="margin-right:4px;">
                    <circle cx="5" cy="5" r="4" fill="#10b981"/>
                </svg>
                Current Price
            </div>
            <div class="value-xl btc" style="font-family:'JetBrains Mono', monospace;">${live_price:,.2f}</div>
            <div class="divider"></div>
            <div style="font-size:11px; color:rgba(255,255,255,0.4);">
                BTCUSDT \u00b7 Binance
            </div>
        </div>
        
        <!-- Card 2: Predicted Low -->
        <div class="glass glow-red">
            <div class="label" style="margin-bottom:8px;">
                <svg width="10" height="10" viewBox="0 0 10 10" style="margin-right:4px;">
                    <path d="M5 8L1 2h8z" fill="#ef4444"/>
                </svg>
                Support (Low)
            </div>
            <div class="value-xl" style="color:#ef4444; font-family:'JetBrains Mono', monospace;">${lower:,.2f}</div>
            <div class="divider"></div>
            <div style="font-size:11px; color:rgba(255,255,255,0.4);">
                Lower bound
            </div>
        </div>
        
        <!-- Card 3: Predicted High -->
        <div class="glass glow-green">
            <div class="label" style="margin-bottom:8px;">
                <svg width="10" height="10" viewBox="0 0 10 10" style="margin-right:4px;">
                    <path d="M5 2L9 8H1z" fill="#10b981"/>
                </svg>
                Resistance (High)
            </div>
            <div class="value-xl" style="color:#10b981; font-family:'JetBrains Mono', monospace;">${upper:,.2f}</div>
            <div class="divider"></div>
            <div style="font-size:11px; color:rgba(255,255,255,0.4);">
                Upper bound
            </div>
        </div>
        
        <!-- Card 4: Range Width -->
        <div class="glass">
            <div class="label" style="margin-bottom:8px;">Range Width</div>
            <div class="value-xl" style="font-family:'JetBrains Mono', monospace;">${width:,.0f}</div>
            <div class="divider"></div>
            <div style="display:flex; justify-content:space-between; 
                        font-size:10px; color:rgba(255,255,255,0.35); font-family:'JetBrains Mono', monospace;">
                <span>Mid ${mid:,.0f}</span>
                <span>{confidence}/100 conf</span>
            </div>
            <div class="progress-track" style="margin-top:6px;">
                <div class="progress-fill" style="
                    width:{confidence}%; 
                    background:{'#10b981' if confidence>70 else '#f59e0b' if confidence>40 else '#ef4444'};
                "></div>
            </div>
        </div>
        
        <!-- Card 5: Resolves In -->
        <div class="glass-accent">
            <div class="label" style="margin-bottom:8px;">Resolves In</div>
            <div class="value-xl btc" style="font-family:'JetBrains Mono', monospace;">
                {countdown}
            </div>
            <div class="divider"></div>
            <div style="font-size:11px; color:rgba(247,147,26,0.6);">
                Next 1H candle close
            </div>
            <div class="progress-track" style="margin-top:6px;">
                <div class="progress-fill" style="
                    width:{time_elapsed_pct*100}%;
                    background: linear-gradient(90deg, #F7931A, #e8750a);
                "></div>
            </div>
        </div>
        
    </div>
    """
    st.markdown(clean_html(cards_html), unsafe_allow_html=True)


def render_chart(raw_bars, lower, upper, live_price, history):
    bars_48 = raw_bars[-48:]
    opens  = [float(b[1]) for b in bars_48]
    highs  = [float(b[2]) for b in bars_48]
    lows   = [float(b[3]) for b in bars_48]
    closes = [float(b[4]) for b in bars_48]
    volumes= [float(b[5]) for b in bars_48]
    times  = [datetime.fromtimestamp(int(b[0])/1000, tz=timezone.utc) 
              for b in bars_48]
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.78, 0.22],
        vertical_spacing=0.02
    )
    
    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=times, open=opens, high=highs, low=lows, close=closes,
        increasing=dict(line=dict(color='#10b981', width=1), 
                       fillcolor='rgba(16,185,129,0.7)'),
        decreasing=dict(line=dict(color='#ef4444', width=1), 
                       fillcolor='rgba(239,68,68,0.7)'),
        name='OHLC', showlegend=False
    ), row=1, col=1)
    
    # Volume bars
    vol_colors = ['rgba(16,185,129,0.3)' if c >= o else 'rgba(239,68,68,0.3)' 
                  for o, c in zip(opens, closes)]
    fig.add_trace(go.Bar(
        x=times, y=volumes, marker_color=vol_colors,
        name='Volume', showlegend=False
    ), row=2, col=1)
    
    # Forecast ribbon
    next_time = times[-1] + timedelta(hours=1)
    fig.add_trace(go.Scatter(
        x=[times[-1], next_time, next_time, times[-1]],
        y=[upper, upper, lower, lower],
        fill='toself',
        fillcolor='rgba(99,102,241,0.08)',
        line=dict(width=0),
        name='Forecast Range', showlegend=True,
        hoverinfo='skip'
    ), row=1, col=1)
    
    # Upper/lower dashed lines
    fig.add_trace(go.Scatter(
        x=[times[-1], next_time], y=[upper, upper],
        line=dict(color='#10b981', width=1.5, dash='dash'),
        name=f'Upper ${upper:,.0f}', showlegend=True
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=[times[-1], next_time], y=[lower, lower],
        line=dict(color='#ef4444', width=1.5, dash='dash'),
        name=f'Lower ${lower:,.0f}', showlegend=True
    ), row=1, col=1)
    
    # Live price horizontal line
    fig.add_hline(
        y=live_price, row=1,
        line=dict(color='rgba(247,147,26,0.4)', width=1, dash='dot'),
        annotation_text=f'  ${live_price:,.2f}',
        annotation_font=dict(color='#F7931A', size=11)
    )
    
    # Scatter dots for past predictions
    for r in history:
        if r.get('actual_at_close') and r.get('lower') and r.get('upper'):
            mid_pred = (r['lower'] + r['upper']) / 2
            hit = r.get('in_range')
            color = '#10b981' if hit else '#ef4444'
            try:
                dt = datetime.fromisoformat(r['candle_open'])
                fig.add_trace(go.Scatter(
                    x=[dt], y=[mid_pred],
                    mode='markers',
                    marker=dict(color=color, size=7, 
                               symbol='circle',
                               line=dict(color='rgba(0,0,0,0.5)', width=1)),
                    name='Hit' if hit else 'Miss',
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{'HIT' if hit else 'MISS'}</b><br>"
                        f"Range: ${r['lower']:,.0f}\u2013${r['upper']:,.0f}<br>"
                        f"Actual: ${r['actual_at_close']:,.0f}"
                        "<extra></extra>"
                    )
                ), row=1, col=1)
            except:
                pass
    
    # "Now" vertical line
    fig.add_shape(
        type="line", x0=times[-1], x1=times[-1],
        y0=0, y1=1, yref="paper",
        line=dict(color='rgba(255,255,255,0.1)', width=1, dash='dot')
    )
    fig.add_annotation(
        x=times[-1], y=1.02, yref="paper",
        text='NOW', showarrow=False,
        font=dict(color='rgba(255,255,255,0.3)', size=9)
    )
    
    fig.update_layout(
        uirevision='constant',
        height=480,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=8, b=0),
        legend=dict(
            orientation='h', x=0, y=1.02,
            bgcolor='rgba(0,0,0,0)',
            font=dict(color='rgba(255,255,255,0.5)', size=10)
        ),
        xaxis=dict(
            showgrid=False, zeroline=False,
            color='rgba(255,255,255,0.2)',
            tickfont=dict(size=10),
            rangeslider=dict(visible=False),
            range=[times[-min(49, len(times))], times[-1] + timedelta(hours=2)],
            rangeselector=dict(visible=False),
            type='date'
        ),
        dragmode='pan',
        xaxis2=dict(showgrid=False, zeroline=False,
                    color='rgba(255,255,255,0.2)',
                    tickfont=dict(size=10)),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.04)',
            zeroline=False,
            color='rgba(255,255,255,0.25)',
            tickprefix='$', tickfont=dict(size=10),
            side='right'
        ),
        yaxis2=dict(
            showgrid=False, zeroline=False,
            color='rgba(255,255,255,0.15)',
            tickfont=dict(size=9), side='right'
        ),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='rgba(10,10,15,0.95)',
            bordercolor='rgba(255,255,255,0.1)',
            font=dict(color='white', size=12, family='JetBrains Mono, monospace')
        )
    )
    
    return fig


def render_insights(lower, upper, live_price, coverage, 
                     winkler, mean_width, df_t, scale_t, 
                     vol_short, vol_medium, vol_long):
    
    width = upper - lower
    mid = (lower + upper) / 2
    price_pos = (live_price - lower) / (width + 1e-9)
    price_pos_pct = round(min(max(price_pos * 100, 0), 100), 1)
    
    cov_vs_target = round((coverage - 0.96) * 100, 2)
    cov_sign = "+" if cov_vs_target >= 0 else ""
    
    st.markdown(clean_html(f"""
    <div style="padding: 0 24px 0 0; height:100%;">
        
        <!-- Range position indicator -->
        <div class="glass" style="margin-bottom:12px;">
            <div class="label" style="margin-bottom:12px;">Price Position in Range</div>
            <div style="position:relative; height:48px; 
                        background:rgba(255,255,255,0.03);
                        border-radius:8px; overflow:hidden;
                        border:1px solid rgba(255,255,255,0.06);">
                <!-- Fill -->
                <div style="position:absolute; left:0; top:0; bottom:0;
                            width:{price_pos_pct}%;
                            background:linear-gradient(90deg, 
                                rgba(16,185,129,0.2), rgba(247,147,26,0.3));
                            border-radius:8px;"></div>
                <!-- Marker -->
                <div style="position:absolute; top:8px; bottom:8px;
                            left:calc({price_pos_pct}% - 2px);
                            width:3px; border-radius:2px;
                            background:#F7931A;
                            box-shadow:0 0 8px rgba(247,147,26,0.6);"></div>
                <!-- Labels -->
                <div style="position:absolute; left:8px; top:50%; 
                            transform:translateY(-50%);
                            font-size:10px; color:rgba(16,185,129,0.7);
                            font-family:'JetBrains Mono', monospace;">
                    ${lower:,.0f}
                </div>
                <div style="position:absolute; right:8px; top:50%; 
                            transform:translateY(-50%);
                            font-size:10px; color:rgba(239,68,68,0.7);
                            font-family:'JetBrains Mono', monospace;">
                    ${upper:,.0f}
                </div>
            </div>
            <div style="text-align:center; font-size:10px; 
                        color:rgba(255,255,255,0.35); margin-top:6px;">
                Price at {price_pos_pct}% of range \u00b7 Width ${width:,.0f}
            </div>
        </div>
        
        <!-- Model stats -->
        <div class="glass" style="margin-bottom:12px;">
            <div class="label" style="margin-bottom:12px;">Model Internals</div>
            
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                <div style="background:rgba(255,255,255,0.02); 
                            border-radius:8px; padding:10px;">
                    <div style="font-size:9px; color:rgba(255,255,255,0.3); 
                                letter-spacing:0.08em; margin-bottom:4px;">
                        STUDENT-T DF
                    </div>
                    <div style="font-size:16px; font-weight:600; 
                                color:#818cf8; font-family:'JetBrains Mono', monospace;">
                        {df_t:.2f}
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02); 
                            border-radius:8px; padding:10px;">
                    <div style="font-size:9px; color:rgba(255,255,255,0.3); 
                                letter-spacing:0.08em; margin-bottom:4px;">
                        SCALE
                    </div>
                    <div style="font-size:16px; font-weight:600; 
                                color:#818cf8; font-family:'JetBrains Mono', monospace;">
                        {scale_t:.6f}
                    </div>
                </div>
            </div>
            
            <!-- Volatility bars -->
            <div style="margin-top:12px;">
                <div style="font-size:9px; color:rgba(255,255,255,0.3); 
                            letter-spacing:0.08em; margin-bottom:8px;">
                    VOLATILITY REGIME
                </div>
                {"".join([
                    f'''<div style="display:flex; align-items:center; 
                                   gap:8px; margin-bottom:6px;">
                        <div style="font-size:9px; color:rgba(255,255,255,0.3); 
                                    width:40px; font-family:'JetBrains Mono', monospace;">{label}</div>
                        <div style="flex:1; height:4px; 
                                    background:rgba(255,255,255,0.06); 
                                    border-radius:2px; overflow:hidden;">
                            <div style="height:100%; width:{min(vol/0.002*100,100):.0f}%; 
                                        background:{color}; border-radius:2px;"></div>
                        </div>
                        <div style="font-size:9px; color:{color}; 
                                    font-family:'JetBrains Mono', monospace; width:52px; text-align:right;">
                            {vol*100:.4f}%
                        </div>
                    </div>'''
                    for label, vol, color in [
                        ('6H', vol_short, '#ef4444'),
                        ('24H', vol_medium, '#f59e0b'),
                        ('7D', vol_long, '#10b981')
                    ]
                ])}
            </div>
        </div>
        

        
    </div>
    """), unsafe_allow_html=True)


def render_coverage_gauge_html(coverage_pct, live_coverage=None, live_n=0):
    """Returns complete HTML string for gauge — rendered via components.html"""
    import math
    # Needle math: 80%=left(180deg), 100%=right(0deg)
    display_min, display_max = 80.0, 100.0
    clamped = max(display_min, min(display_max, float(coverage_pct)))
    fraction = (clamped - display_min) / (display_max - display_min)
    needle_deg = 180.0 - (fraction * 180.0)
    needle_rad = math.radians(needle_deg)
    
    cx, cy, r = 120, 95, 75
    
    # Needle tip
    nx = cx + r * math.cos(needle_rad)
    ny = cy - r * math.sin(needle_rad)
    
    # Needle tail (opposite direction, shorter)
    tail_r = 10
    tx_tail = cx - tail_r * math.cos(needle_rad)
    ty_tail = cy + tail_r * math.sin(needle_rad)
    
    def pt(deg):
        rad = math.radians(deg)
        return (cx + r * math.cos(rad), cy - r * math.sin(rad))
    
    def arc_path(a1, a2, color, width=10):
        x1, y1 = pt(a1)
        x2, y2 = pt(a2)
        large = 1 if abs(a1 - a2) > 180 else 0
        sweep = 1  # always clockwise
        return (f'<path d="M{x1:.2f},{y1:.2f} '
                f'A{r},{r} 0 {large},{sweep} {x2:.2f},{y2:.2f}" '
                f'fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-linecap="round"/>')
    
    # Needle color
    diff = abs(coverage_pct - 95)
    if diff < 1.5:
        needle_color = "#10b981"
    elif coverage_pct >= 97:
        needle_color = "#6366f1"
    elif coverage_pct >= 93:
        needle_color = "#f59e0b"
    else:
        needle_color = "#ef4444"
    
    # 95% marker position: fraction=(95-80)/20=0.75 → deg=180-135=45
    m_deg = 45.0
    mx_out, my_out = pt(m_deg)
    m_inner_r = r - 14
    mx_in = cx + m_inner_r * math.cos(math.radians(m_deg))
    my_in = cy - m_inner_r * math.sin(math.radians(m_deg))
    
    # Left/right end labels
    left_x, left_y = pt(180)
    right_x, right_y = pt(0)
    
    live_html = ""
    if live_coverage is not None:
        lc = live_coverage * 100 if live_coverage <= 1.0 else float(live_coverage)
        lc_color = "#10b981" if lc >= 94 else "#f59e0b"
        live_html = f"""
        <div style="color:{lc_color};font-size:11px;
                    font-family:monospace;margin-top:2px;">
            Live: {lc:.1f}% ({live_n} resolved)
        </div>"""
    
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    font-family: -apple-system, 'SF Mono', monospace;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 16px;
    min-height: 100%;
  }}
  .label {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
    margin-bottom: 8px;
  }}
  .sub {{
    font-size: 11px;
    color: rgba(255,255,255,0.3);
    font-family: monospace;
    margin-top: 4px;
    text-align: center;
  }}
</style>
</head>
<body>
  <div class="label">Coverage Gauge</div>
  
  <svg viewBox="30 20 180 90"
       style="width:100%;max-width:260px;display:block;">
    
    <!-- Background track -->
    {arc_path(180, 0, 'rgba(255,255,255,0.06)', 10)}
    
    <!-- Red zone: 80-90% → 180 to 90deg -->
    {arc_path(180, 90, 'rgba(239,68,68,0.4)', 10)}
    
    <!-- Amber zone: 90-93% → 90 to 54deg -->
    {arc_path(90, 54, 'rgba(245,158,11,0.4)', 10)}
    
    <!-- Green zone: 93-97% → 54 to 18deg -->
    {arc_path(54, 18, 'rgba(16,185,129,0.5)', 10)}
    
    <!-- Indigo zone: 97-100% → 18 to 0deg -->
    {arc_path(18, 0, 'rgba(99,102,241,0.4)', 10)}
    
    <!-- 95% target marker -->
    <line x1="{mx_in:.2f}" y1="{my_in:.2f}"
          x2="{mx_out:.2f}" y2="{my_out:.2f}"
          stroke="rgba(255,255,255,0.6)" stroke-width="1.5"/>
    <text x="{mx_out+5:.1f}" y="{my_out-3:.1f}"
          fill="rgba(255,255,255,0.5)" font-size="7"
          font-family="monospace">95%</text>
    
    <!-- Needle -->
    <line x1="{tx_tail:.2f}" y1="{ty_tail:.2f}"
          x2="{nx:.2f}" y2="{ny:.2f}"
          stroke="{needle_color}" stroke-width="2.5"
          stroke-linecap="round"/>
    
    <!-- Pivot circle -->
    <circle cx="{cx}" cy="{cy}" r="6"
            fill="{needle_color}"/>
    <circle cx="{cx}" cy="{cy}" r="3"
            fill="#0a0a0f"/>
    
    <!-- Value text -->
    <text x="{cx}" y="{cy - 18}"
          text-anchor="middle"
          fill="{needle_color}"
          font-size="19"
          font-weight="700"
          font-family="monospace">{coverage_pct:.1f}%</text>
    
    <!-- Range labels -->
    <text x="{left_x - 2:.1f}" y="{left_y + 12:.1f}"
          fill="rgba(255,255,255,0.25)"
          font-size="7" font-family="monospace"
          text-anchor="middle">80%</text>
    <text x="{right_x + 2:.1f}" y="{right_y + 12:.1f}"
          fill="rgba(255,255,255,0.25)"
          font-size="7" font-family="monospace"
          text-anchor="middle">100%</text>
  </svg>
  
  <div class="sub">Backtest: {coverage_pct:.2f}% (n=714)</div>
  {live_html}
</body>
</html>"""

def render_width_card(mean_width):
    st.markdown(clean_html(f'''
    <div class="glass" style="text-align:center; padding:28px 20px; height:250px; display:flex; flex-direction:column; justify-content:center; align-items:center;">
        <div class="label" style="margin-bottom:12px;">Mean Width</div>
        <div style="font-size:2rem; font-weight:700; color:#fff; 
                    letter-spacing:-0.02em; font-family:monospace;">
            ${mean_width:,.0f}
        </div>
        <div class="divider" style="width:100%; margin:12px 0;"></div>
        <div style="font-size:11px; color:rgba(255,255,255,0.35);">
            Avg forecast range &middot; lower = better
        </div>
    </div>
    '''), unsafe_allow_html=True)

def render_winkler_card(winkler):
    st.markdown(clean_html(f'''
    <div class="glass" style="text-align:center; padding:28px 20px; height:250px; display:flex; flex-direction:column; justify-content:center; align-items:center;">
        <div class="label" style="margin-bottom:12px;">Mean Winkler Score</div>
        <div style="font-size:2rem; font-weight:700; color:#fff; 
                    letter-spacing:-0.02em; font-family:monospace;">
            {winkler:,.0f}
        </div>
        <div class="divider" style="width:100%; margin:12px 0;"></div>
        <div style="font-size:11px; color:rgba(255,255,255,0.35);">
            Efficiency metric &middot; lower = better
        </div>
    </div>
    '''), unsafe_allow_html=True)


def render_rolling_chart(timestamps, coverages, winklers):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Target line
    fig.add_hline(
        y=0.96,
        line=dict(color='rgba(99,102,241,0.4)', width=1, dash='dot'),
        annotation_text='96% target',
        annotation_font=dict(color='rgba(99,102,241,0.6)', size=9)
    )

    # Coverage area chart
    fig.add_trace(go.Scatter(
        x=timestamps, y=coverages,
        fill='tozeroy',
        fillcolor='rgba(16,185,129,0.05)',
        line=dict(color='#10b981', width=1.5),
        name='Coverage'
    ), secondary_y=False)
    
    # Winkler
    fig.add_trace(go.Scatter(
        x=timestamps, y=winklers,
        line=dict(color='rgba(245,158,11,0.6)', width=1),
        name='Winkler $'
    ), secondary_y=True)
    
    fig.update_layout(
        uirevision='constant',
        height=160,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            orientation='h', x=0, y=1.1,
            bgcolor='rgba(0,0,0,0)',
            font=dict(color='rgba(255,255,255,0.4)', size=9)
        ),
        xaxis=dict(showgrid=False, 
                   color='rgba(255,255,255,0.15)',
                   tickfont=dict(size=9)),
        yaxis=dict(showgrid=True, 
                   gridcolor='rgba(255,255,255,0.03)',
                   color='rgba(255,255,255,0.2)',
                   tickfont=dict(size=9),
                   tickformat='.0%'),
        yaxis2=dict(showgrid=False,
                    color='rgba(245,158,11,0.4)',
                    tickfont=dict(size=9),
                    tickprefix='$')
    )
    fig.update_yaxes(
        range=[0.82, 1.02],          # zoom into 82%–102%
        tickformat='.0%',
        secondary_y=False
    )
    fig.update_yaxes(
        range=[800, 3500],            # Winkler range
        tickprefix='$',
        secondary_y=True
    )
    return fig


def render_history_table(display_rows):
    rows_html = ""
    for r in display_rows:
        if r.get("_is_summary"):
            rows_html += f"""
            <tr>
                <td colspan="6" style="text-align:center; 
                    color:rgba(255,255,255,0.2); font-style:italic;
                    padding:6px 12px; font-size:11px;">
                    \u00b7\u00b7\u00b7 {r['_count']} unvisited hours collapsed \u00b7\u00b7\u00b7
                </td>
            </tr>"""
            continue
        
        if r.get("Lower ($)") == "not visited":
            rows_html += f'''
            <tr style="opacity:0.4;">
                <td style="color:rgba(255,255,255,0.4);">
                    {r.get('Candle Open (UTC)', '\u2014')}
                </td>
                <td colspan="4" style="color:rgba(255,255,255,0.25); 
                                        font-style:italic; letter-spacing:0.05em; text-align:center;">
                    not visited
                </td>
                <td style="color:rgba(255,255,255,0.2);">\u2014</td>
            </tr>'''
            continue
            
        in_range = r.get("In Range", "\u2014")
        hit_html = {
            "HIT": '<span style="color:#10b981; font-weight:700;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px; vertical-align:-1px;"><polyline points="20 6 9 17 4 12"></polyline></svg>HIT</span>',
            "MISS": '<span style="color:#ef4444; font-weight:700;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px; vertical-align:-1px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>MISS</span>',
        }.get(in_range, '<span style="color:rgba(255,255,255,0.2);">PENDING</span>')
        
        rows_html += f"""
        <tr>
            <td>{r.get('Candle Open (UTC)', '\u2014')}</td>
            <td style="color:#ef4444;">{r.get('Lower ($)', '\u2014')}</td>
            <td style="color:#10b981;">{r.get('Upper ($)', '\u2014')}</td>
            <td>{r.get('Actual ($)', '\u2014')}</td>
            <td>{hit_html}</td>
            <td style="color:rgba(255,255,255,0.35);">
                {r.get('Generated At', '\u2014')}
            </td>
        </tr>"""
    
    st.markdown(clean_html(f"""
    <div class="glass" style="margin:0 24px 24px; padding:0; overflow:hidden;">
        
        <!-- Header -->
        <div style="padding:16px 20px 12px; 
                    border-bottom:1px solid rgba(255,255,255,0.05);">
            <div class="label">Prediction Audit Log · Part C</div>
        </div>
        
        <!-- SCROLLABLE table container — KEY FIX -->
        <style>
        .audit-scroll::-webkit-scrollbar {{
            width: 4px;
        }}
        .audit-scroll::-webkit-scrollbar-track {{
            background: transparent;
        }}
        .audit-scroll::-webkit-scrollbar-thumb {{
            background: rgba(255,255,255,0.15);
            border-radius: 2px;
        }}
        .audit-scroll::-webkit-scrollbar-thumb:hover {{
            background: rgba(255,255,255,0.25);
        }}
        </style>
        
        <div class="audit-scroll" style="
            overflow-y: auto;
            max-height: 380px;
            scrollbar-width: thin;
            scrollbar-color: rgba(255,255,255,0.15) transparent;
        ">
                <table class="btc-table" style="width:100%;">
                    <thead style="
                        position: sticky;
                        top: 0;
                        background: rgba(10,10,15,0.95);
                        backdrop-filter: blur(10px);
                        z-index: 1;
                    ">
                        <tr>
                            <th>Candle (UTC)</th>
                            <th>Lower</th>
                            <th>Upper</th>
                            <th>Actual</th>
                            <th>Result</th>
                            <th>Generated</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    """), unsafe_allow_html=True)


def render_ticker(resolved_predictions, max_items=15):
    if not resolved_predictions:
        return
    
    items = []
    for r in resolved_predictions[:max_items]:
        hit = r.get("in_range")
        actual = r.get("actual_at_close")
        candle = r.get("candle_open", "")
        try:
            hour = datetime.fromisoformat(candle).astimezone(timezone.utc).strftime("%H:%M")
        except:
            hour = "??"
        
        if hit is True:
            icon = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><polyline points="20 6 9 17 4 12"></polyline></svg>'
            color = "#10b981"
        elif hit is False:
            icon = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
            color = "#ef4444"
        else:
            continue
        
        actual_str = f"${actual:,.0f}" if actual else "?"
        items.append(
            f'<span style="color:{color}; margin: 0 24px;">'
            f'{icon} {hour}\u2192{actual_str} ({"hit" if hit else "miss"})'
            f'</span>'
        )
    
    if not items:
        return
    
    content = " \u00b7 ".join(items) * 3  # repeat 3x for seamless loop
    
    st.markdown(clean_html(f"""
    <div class="ticker-wrap">
        <div class="ticker-content">
            {content}
        </div>
    </div>
    """), unsafe_allow_html=True)


# ============================================================================
# MAIN APP FLOW
# ============================================================================

# --- STATIC SECTION ---
render_header(None, None, None)
metrics = load_backtest_metrics()

# --- LIVE SECTION ---
@st.fragment(run_every=10)
def live_section():
    # 1. Fetch data
    raw_bars = fetch_klines()[2]
    closes = np.array([float(k[4]) for k in raw_bars])
    live_price_ticker, change_pct_ticker = fetch_live_ticker()
    
    live_price = live_price_ticker if live_price_ticker is not None else closes[-1]
    change_pct = change_pct_ticker if change_pct_ticker is not None else 0.0

    # 2. Run model
    closes_for_model = np.append(closes[:-1], live_price)
    
    # 97% confidence interval -> alpha=0.03
    pred = predict_next(closes_for_model, n_sims=10000, alpha=0.03)
    lower = pred["lower"]
    upper = pred["upper"]
    df_t = pred["df"]
    loc_t = pred["loc"]
    scale_t = pred["scale"]
    
    # 3. Compute display values
    # We can use the logic inside compute_adaptive_volatility to extract individual windows
    # since compute_adaptive_volatility returns a dict of short, medium, long
    vol_s = pred["vol_breakdown"]["short"] if pred["vol_breakdown"] else 0.001
    vol_m = pred["vol_breakdown"]["medium"] if pred["vol_breakdown"] else 0.001
    vol_l = pred["vol_breakdown"]["long"] if pred["vol_breakdown"] else 0.001
    
    confidence = confidence_score(np.diff(np.log(closes_for_model)), lower, upper, live_price)
    countdown, time_pct = time_to_next_candle()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 4. Load history
    if metrics:
        coverage = metrics["coverage"] / 100.0  # as fraction
        mean_width = metrics["mean_width"]
        winkler = metrics["mean_winkler"]
    else:
        coverage, mean_width, winkler = 0.96, 0.0, 0.0

    last_bar_open_ms = int(raw_bars[-1][0])
    next_candle_open = datetime.fromtimestamp(last_bar_open_ms / 1000, tz=timezone.utc) + timedelta(hours=1)
    next_candle_open_iso = next_candle_open.isoformat()
    
    prediction_time = datetime.now(tz=timezone.utc)
    new_record = {
        "candle_open": next_candle_open_iso,
        "lower": round(lower, 2),
        "upper": round(upper, 2),
        "actual_at_close": None,
        "in_range": None,
        "generated_at": prediction_time.isoformat(),
    }
    
    history = backfill_actuals(HISTORY_FILE)
    existing_for_candle = next((r for r in history if r.get("candle_open") == next_candle_open_iso), None)
    if existing_for_candle and existing_for_candle.get("actual_at_close") is not None:
        new_record["actual_at_close"] = existing_for_candle["actual_at_close"]
        new_record["in_range"] = existing_for_candle["in_range"]
        
    save_prediction(new_record)
    history = backfill_actuals(HISTORY_FILE)

    # 5. Render
    resolved = [r for r in history if r.get("in_range") is not None]
    resolved.sort(key=lambda r: r.get("candle_open", ""), reverse=True)
    render_ticker(resolved)
    
    render_kpi_cards(live_price, lower, upper, coverage, 
                      mean_width, winkler, confidence, countdown, time_pct)

    col_chart, col_insights = st.columns([0.65, 0.35])
    with col_chart:
        fig = render_chart(raw_bars, lower, upper, live_price, history)
        st.plotly_chart(fig, use_container_width=True, config={
            'displayModeBar': False,
            'scrollZoom': True,
            'doubleClick': 'reset'
        })
        
    with col_insights:
        render_insights(lower, upper, live_price, coverage, winkler, 
                         mean_width, df_t, scale_t, vol_s, vol_m, vol_l)

    live_cov = compute_live_coverage(history)
    live_n = len([r for r in history if r.get("in_range") is not None])
    
    col_g, col_w, col_wk = st.columns(3)
    with col_g:
        components.html(
            render_coverage_gauge_html(
                coverage * 100, live_cov, live_n
            ),
            height=250
        )
    with col_w:
        render_width_card(mean_width)
    with col_wk:
        render_winkler_card(winkler)

    # Rolling chart
    st.markdown('<div style="padding:0 24px;">', unsafe_allow_html=True)
    st.markdown('<div class="label" style="margin-bottom:8px;">Rolling Model Stability \u00b7 60-Bar Window</div>', unsafe_allow_html=True)
    
    bt_records = metrics.get("records", []) if metrics else []
    all_recs = []
    for r in bt_records:
        all_recs.append({"ts": r["timestamp"], "lower": r["lower"], "upper": r["upper"], "actual": r["actual"]})
    for r in resolved:
        all_recs.append({"ts": r.get("generated_at", r["candle_open"]),
                         "lower": r["lower"], "upper": r["upper"], "actual": r["actual_at_close"]})
    all_recs.sort(key=lambda x: str(x["ts"]))
    
    window = 60
    roll_ts, roll_cov, roll_wink = [], [], []
    for i in range(window, len(all_recs)):
        w_recs = all_recs[i - window:i]
        cov_flags, w_scores = [], []
        for rec in w_recs:
            lo, hi, actual = rec["lower"], rec["upper"], rec["actual"]
            wd = hi - lo
            inside = lo <= actual <= hi
            cov_flags.append(int(inside))
            if inside: w_scores.append(wd)
            else: w_scores.append(wd + (2 / ALPHA) * min(abs(actual - lo), abs(actual - hi)))
        roll_cov.append(np.mean(cov_flags))
        roll_wink.append(np.mean(w_scores))
        
        ts_val = all_recs[i]["ts"]
        try:
            if isinstance(ts_val, (int, float)):
                roll_ts.append(datetime.fromtimestamp(ts_val / 1000, tz=timezone.utc))
            else:
                roll_ts.append(datetime.fromisoformat(str(ts_val)))
        except Exception:
            roll_ts.append(datetime.now(timezone.utc) - timedelta(hours=len(all_recs) - i))

    if len(roll_ts) > 0:
        fig2 = render_rolling_chart(roll_ts, roll_cov, roll_wink)
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar':False})
    st.markdown('</div>', unsafe_allow_html=True)

    # History table
    rows_with_gaps = add_display_gaps(history[-50:])
    display_rows = []
    
    def fmt_dt(iso_str):
        if not iso_str or iso_str == "\u2014": return "\u2014"
        try:
            dt = datetime.fromisoformat(iso_str).astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception: return iso_str
        
    for r in rows_with_gaps:
        if r.get("_is_summary"):
            display_rows.append({"_is_summary": True, "_count": r["_count"]})
        elif r.get("_is_gap"):
            display_rows.append({
                "Candle Open (UTC)": fmt_dt(r["candle_open"]),
                "Lower ($)": "not visited", "Upper ($)": "not visited",
                "Actual ($)": "\u2014", "In Range": "\u2014", "Generated At": "\u2014"
            })
        else:
            actual = r.get("actual_at_close")
            in_range = r.get("in_range")
            display_rows.append({
                "Candle Open (UTC)": fmt_dt(r.get("candle_open")),
                "Lower ($)": f"${r['lower']:,.2f}" if r.get("lower") is not None else "\u2014",
                "Upper ($)": f"${r['upper']:,.2f}" if r.get("upper") is not None else "\u2014",
                "Actual ($)": f"${actual:,.2f}" if actual is not None else "\u2014",
                "In Range": "HIT" if in_range is True else ("MISS" if in_range is False else "\u2014"),
                "Generated At": fmt_dt(r.get("generated_at")),
            })
            
    render_history_table(display_rows)

if __name__ == "__main__":
    live_section()
