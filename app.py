"""
app.py — BTC Forecast Dashboard (v2 — 10 Upgrades)
GBM + Student-t with GARCH-inspired adaptive volatility.
Run: streamlit run app.py
"""

import json, os, time, math
from datetime import datetime, timezone, timedelta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from scipy import stats
from streamlit_autorefresh import st_autorefresh
import pandas as pd

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BTC Forecaster | AlphaI × Polaris",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st_autorefresh(interval=10_000, limit=10000, key="btc_live_refresh")

# ─── Constants ───────────────────────────────────────────────────────────────
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
BINANCE_PARAMS = {"symbol": "BTCUSDT", "interval": "1h", "limit": 500}
HISTORY_FILE = "prediction_history.jsonl"
BACKTEST_FILE = "backtest_results.jsonl"
ALPHA = 0.05

# ─── Sidebar Controls (Upgrade 10) ──────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Model Parameters")
    sb_short = st.slider("Short vol window", 3, 12, 6, key="sb_short")
    sb_medium = st.slider("Medium vol window", 12, 48, 24, key="sb_med")
    sb_long = st.slider("Long vol window", 48, 336, 168, key="sb_long")
    sb_nsim = st.slider("Monte Carlo sims", 1000, 50000, 10000, step=1000, key="sb_nsim")
    if st.button("Reset to defaults"):
        st.session_state.sb_short = 6
        st.session_state.sb_med = 24
        st.session_state.sb_long = 168
        st.session_state.sb_nsim = 10000
        st.rerun()

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
.block-container {padding-top: 1rem; padding-bottom: 0rem;}
div[data-testid="stMetricValue"] {font-size: 1.8rem;}
.metric-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    border: 1px solid rgba(255,165,0,0.25); border-radius: 16px;
    padding: 20px 24px; text-align: center; box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}
.metric-label {
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.12em;
    text-transform: uppercase; color: #f0a500; margin-bottom: 6px;
}
.metric-value { font-size: 2rem; font-weight: 900; color: #ffffff; line-height: 1; }
.metric-sub { font-size: 0.72rem; color: rgba(255,255,255,0.45); margin-top: 4px; }
.price-hero {
    background: linear-gradient(135deg, #f0a500, #ff6b35);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-size: 3.2rem; font-weight: 900; line-height: 1;
}
.range-card {
    background: linear-gradient(135deg, #0d2137, #0a1628);
    border: 1px solid rgba(34,197,94,0.3); border-radius: 16px;
    padding: 24px 32px; text-align: center;
}
.range-lower { color: #ef4444; font-size: 1.6rem; font-weight: 800; }
.range-upper { color: #22c55e; font-size: 1.6rem; font-weight: 800; }
.range-sep { color: rgba(255,255,255,0.4); font-size: 1.4rem; margin: 0 16px; }
.section-title {
    font-size: 1.15rem; font-weight: 700; color: #f0a500;
    border-left: 4px solid #f0a500; padding-left: 12px; margin: 32px 0 16px 0;
}
.timestamp-badge {
    display: inline-block; background: rgba(240,165,0,0.12);
    border: 1px solid rgba(240,165,0,0.3); border-radius: 24px;
    padding: 4px 16px; font-size: 0.78rem; color: #f0a500;
}


@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }
.gauge-pulse { animation: pulse 2s ease-in-out infinite; }
</style>
""", unsafe_allow_html=True)


# ─── Helper Functions ────────────────────────────────────────────────────────

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
            if not co or co in ("—", "null", None): continue
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


# ─── UPGRADE 1: Adaptive Volatility ─────────────────────────────────────────

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
    # Floor: never let vol drop below 50% of long-term average
    floor = v_long * 0.5
    blended = max(blended, floor)
    return blended, {"short": v_short, "medium": v_medium, "long": v_long}


def fit_student_t(returns):
    if len(returns) < 3: return 3.0, 0.0, 1e-4
    df, loc, scale = stats.t.fit(returns)
    return max(df, 2.01), loc, scale


def predict_next(closes, n_sims=10000, short_w=6, med_w=24, long_w=168):
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
    lower = float(np.percentile(next_prices, 2.5))
    upper = float(np.percentile(next_prices, 97.5))
    return {
        "lower": lower, "upper": upper,
        "df": df, "loc": loc, "scale": scale, "scaled_scale": scaled_scale,
        "blended_vol": blended_vol, "vol_breakdown": vol_breakdown,
        "n_sims": n_sims, "simulated_prices": next_prices,
        "log_returns": log_returns,
    }


# ─── UPGRADE 5: Confidence Score ────────────────────────────────────────────

def confidence_score(log_returns, lower, upper, current_price):
    width = upper - lower
    recent_vol_dollar = np.std(log_returns[-24:]) * current_price * np.sqrt(24)
    narrowness = max(0, 1 - (width / (recent_vol_dollar * 2)))
    mid = (upper + lower) / 2
    centering = 1 - abs(current_price - mid) / (width / 2 + 1e-9)
    centering = max(0, min(1, centering))
    return int((0.6 * narrowness + 0.4 * centering) * 100)





# ─── UPGRADE 8: Countdown Timer ─────────────────────────────────────────────

def time_to_next_candle():
    now = datetime.now(timezone.utc)
    total_seconds_past = now.minute * 60 + now.second
    seconds_remaining = 3600 - total_seconds_past
    m = seconds_remaining // 60
    s = seconds_remaining % 60
    progress = total_seconds_past / 3600
    return f"{m:02d}:{s:02d}", progress


# ─── Save / Backfill ────────────────────────────────────────────────────────

def save_prediction(record, path=HISTORY_FILE):
    co = record.get("candle_open")
    if not co or co in ("—", None, "null"): return
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


# ─── UPGRADE 2: Confidence Gauge SVG ────────────────────────────────────────

def render_gauge(coverage_pct):
    """Render SVG semicircle gauge for coverage. coverage_pct is 0-100."""
    cov = coverage_pct / 100.0
    angle = min(max(cov, 0), 1.05) * 180
    needle_rad = math.radians(180 - angle)
    nx = 150 + 100 * math.cos(needle_rad)
    ny = 140 - 100 * math.sin(needle_rad)
    if 93 <= coverage_pct <= 97: zone_color = "#00c896"
    elif coverage_pct < 90 or coverage_pct > 100: zone_color = "#ef5350"
    else: zone_color = "#f0b90b"
    svg = f'''<svg viewBox="0 0 300 170" xmlns="http://www.w3.org/2000/svg" style="max-width:280px;margin:auto;display:block;">
      <path d="M 30 140 A 120 120 0 0 1 270 140" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="18" stroke-linecap="round"/>
      <path d="M 68 140 A 82 82 0 0 1 88 72" fill="none" stroke="#ef5350" stroke-width="6" opacity="0.3" stroke-linecap="round"/>
      <path d="M 100 58 A 82 82 0 0 1 200 58" fill="none" stroke="#00c896" stroke-width="6" opacity="0.3" stroke-linecap="round"/>
      <path d="M 218 78 A 82 82 0 0 1 232 140" fill="none" stroke="#ef5350" stroke-width="6" opacity="0.3" stroke-linecap="round"/>
      <line x1="150" y1="140" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{zone_color}" stroke-width="3" stroke-linecap="round"/>
      <circle cx="150" cy="140" r="6" fill="{zone_color}" class="gauge-pulse"/>
      <text x="150" y="125" text-anchor="middle" fill="white" font-size="22" font-weight="900">{coverage_pct:.1f}%</text>
      <text x="30" y="160" text-anchor="middle" fill="rgba(255,255,255,0.3)" font-size="10">0</text>
      <text x="150" y="30" text-anchor="middle" fill="rgba(255,255,255,0.3)" font-size="10">0.50</text>
      <text x="270" y="160" text-anchor="middle" fill="rgba(255,255,255,0.3)" font-size="10">1.0</text>
    </svg>'''
    return svg


# ─── UPGRADE 3: Chart Overhaul ──────────────────────────────────────────────

def build_chart(raw_bars, lower, upper, history_rows):
    bars48 = raw_bars[-48:]
    dts = [datetime.fromtimestamp(int(b[0]) / 1000, tz=timezone.utc) for b in bars48]
    opens = [float(b[1]) for b in bars48]
    highs = [float(b[2]) for b in bars48]
    lows = [float(b[3]) for b in bars48]
    closes_arr = [float(b[4]) for b in bars48]
    last_ts = dts[-1]
    next_ts = last_ts + timedelta(hours=1)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=dts, open=opens, high=highs, low=lows, close=closes_arr,
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a", decreasing_fillcolor="#ef5350",
        name="OHLC", whiskerwidth=0.5,
    ))
    fig.add_trace(go.Scatter(
        x=[last_ts, next_ts, next_ts, last_ts],
        y=[upper, upper, lower, lower],
        fill="toself", fillcolor="rgba(100,200,100,0.15)",
        line=dict(color="rgba(100,200,100,0)", width=0),
        name="Forecast Range", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(x=[last_ts, next_ts], y=[upper, upper],
        mode="lines", line=dict(color="#22c55e", width=1.5, dash="dash"),
        name=f"Upper ${upper:,.0f}", hovertemplate=f"Upper: ${upper:,.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[last_ts, next_ts], y=[lower, lower],
        mode="lines", line=dict(color="#ef4444", width=1.5, dash="dash"),
        name=f"Lower ${lower:,.0f}", hovertemplate=f"Lower: ${lower:,.2f}<extra></extra>"))
    # Past prediction dots
    if history_rows:
        chart_start = dts[0]
        for row in history_rows:
            try:
                rdt = datetime.fromisoformat(row["candle_open"]).astimezone(timezone.utc)
            except Exception: continue
            if rdt < chart_start or rdt > last_ts: continue
            if row.get("lower") is None: continue
            mid = (row["lower"] + row["upper"]) / 2
            actual = row.get("actual_at_close")
            ir = row.get("in_range")
            if ir is True: color, label = "#26a69a", "HIT"
            elif ir is False: color, label = "#ef5350", "MISS"
            else: color, label = "#9c27b0", "PENDING"
            ht = f"Predicted: ${row['lower']:,.0f}–${row['upper']:,.0f}"
            if actual: ht += f" | Actual: ${actual:,.0f}"
            ht += f" | {label}<extra></extra>"
            fig.add_trace(go.Scatter(x=[rdt], y=[mid], mode="markers",
                marker=dict(color=color, size=8, line=dict(width=1, color="white")),
                name="", showlegend=False, hovertemplate=ht))
    fig.add_shape(type="line", x0=last_ts, x1=last_ts, y0=0, y1=1, yref="paper",
        line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"))
    fig.add_annotation(x=last_ts, y=1.02, yref="paper", text="Now", showarrow=False,
        font=dict(size=10, color="rgba(255,255,255,0.4)"))
    fig.add_annotation(x=next_ts, y=(upper+lower)/2,
        text=f"${lower:,.0f}<br>—<br>${upper:,.0f}", showarrow=False,
        font=dict(size=10, color="white"),
        bgcolor="rgba(15,20,35,0.85)", bordercolor="rgba(34,197,94,0.4)",
        borderwidth=1, borderpad=6)
    fig.update_layout(
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(family="Inter", color="white"),
        margin=dict(l=8, r=60, t=16, b=8), height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                   tickfont=dict(size=10), rangeslider=dict(visible=False)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                   tickformat="$,.0f", tickfont=dict(size=10)),
        hovermode="x unified",
    )
    return fig


# ─── Gap detector (max 3 consecutive gaps + summary) ────────────────────────

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
    parsed.sort(key=lambda x: x[0], reverse=True)  # newest first
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
                    result.append({
                        "candle_open": gap_dt.isoformat(),
                        "lower": None, "upper": None,
                        "actual_at_close": None, "in_range": None,
                        "_is_gap": True,
                    })
            elif gap_hours > 1:
                gap_dt = dt - timedelta(hours=1)
                if gap_dt < now_utc:
                    result.append({
                        "candle_open": gap_dt.isoformat(),
                        "lower": None, "upper": None,
                        "actual_at_close": None, "in_range": None,
                        "_is_gap": True,
                    })
                    result.append({"_is_summary": True, "_count": gap_hours - 1})
        i += 1
    return result


# ─── Main App ────────────────────────────────────────────────────────────────

def main():
    # ── Header ──────────────────────────────────────────────────────────────
    bt = load_backtest_metrics()

    st.markdown("""
    <div style="text-align:center; padding: 24px 0 4px 0;">
        <span style="font-size:2.8rem; font-weight:900; background:linear-gradient(90deg,#f0a500,#ff6b35);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
            ₿ BTC Price Forecaster
        </span>
        <div style="font-size:0.88rem; color:rgba(255,255,255,0.45); margin-top:6px;">
            AlphaI × Polaris Hiring Challenge &nbsp;·&nbsp; GBM + Student-t Model &nbsp;·&nbsp; 95% Confidence Interval
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Fetch live data ─────────────────────────────────────────────────────
    with st.spinner("Fetching latest BTC data from Binance..."):
        try:
            closes, ts_ms_list, raw_bars = fetch_klines()
        except Exception as e:
            st.error(f"Failed to fetch data: {e}")
            return
    live_price_ticker, live_change_pct_ticker = fetch_live_ticker()
    rest_close = float(closes[-1])
    live_price = live_price_ticker if live_price_ticker is not None else rest_close
    live_change_pct = live_change_pct_ticker if live_change_pct_ticker is not None else 0.0

    # ── Backfill and load history ───────────────────────────────────────────
    history = backfill_actuals(HISTORY_FILE)

    # ── UPGRADE 4: Live Accuracy Ticker ─────────────────────────────────────
    resolved = [r for r in history if r.get("in_range") is not None]
    resolved.sort(key=lambda r: r.get("candle_open", ""), reverse=True)
    if resolved:
        items = []
        for r in resolved[:15]:
            try:
                hour = datetime.fromisoformat(r["candle_open"]).astimezone(timezone.utc).strftime("%H:%M")
            except Exception: hour = "??"
            hit = r.get("in_range")
            actual = r.get("actual_at_close")
            if hit is True: icon, color = "✅", "#00c896"
            elif hit is False: icon, color = "❌", "#ef5350"
            else: continue
            actual_str = f"${actual:,.0f}" if actual else "?"
            items.append(f'<span style="color:{color}; margin: 0 24px;">{icon} {hour}→{actual_str} ({"hit" if hit else "miss"})</span>')
        if items:
            content = " · ".join(items) * 3
            st.markdown(f"""
            <div style="overflow:hidden; background:rgba(255,255,255,0.03);
                border:0.5px solid rgba(255,255,255,0.08); border-radius:8px;
                padding:10px 0; margin-bottom:1rem;">
                <div style="display:inline-block; white-space:nowrap;
                    animation:ticker 25s linear infinite; font-size:13px; font-family:monospace;">
                    {content}
                </div>
            </div>
            <style>
            @keyframes ticker {{
                0%   {{ transform: translateX(0); }}
                100% {{ transform: translateX(-33.33%); }}
            }}
            </style>
            """, unsafe_allow_html=True)

    # ── Run Model ───────────────────────────────────────────────────────────
    closes_for_model = np.append(closes[:-1], live_price)
    with st.spinner("Running GBM + Student-t simulation..."):
        result = predict_next(closes_for_model, n_sims=sb_nsim,
                              short_w=sb_short, med_w=sb_medium, long_w=sb_long)
    lower, upper = result["lower"], result["upper"]
    prediction_time = datetime.now(tz=timezone.utc)

    # ── Price + Timestamp Row ───────────────────────────────────────────────
    col_price, col_ts = st.columns([2, 1])
    with col_price:
        arrow = "▲" if live_change_pct >= 0 else "▼"
        change_color = "#00c896" if live_change_pct >= 0 else "#ff4b4b"
        st.markdown(f"""
        <div style="padding:8px 0;">
            <div style="font-size:0.75rem; font-weight:600; letter-spacing:.12em;
                        text-transform:uppercase; color:#f0a500; margin-bottom:4px;">
                Current BTC Price
            </div>
            <div style="display:flex; align-items:baseline; gap:16px; flex-wrap:wrap;">
                <span class="price-hero">${live_price:,.2f}</span>
                <span style="font-size:1rem; color:{change_color}; font-weight:700;">
                    {arrow} {abs(live_change_pct):.2f}% 24h
                </span>
                <span style="font-size:0.75rem; color:#00c896;
                    border:1px solid #00c89633; border-radius:4px; padding:2px 8px;">
                    ● LIVE (10s)
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_ts:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align:right; padding-top:16px;">
            <div class="timestamp-badge">🕐 Generated {prediction_time.strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Predicted Range + Confidence + Countdown (Upgrades 5, 8) ────────────
    st.markdown('<div class="section-title">🎯 Next 1-Hour Candle — 95% Confidence Range</div>', unsafe_allow_html=True)
    conf = confidence_score(result["log_returns"], lower, upper, live_price)
    countdown, progress = time_to_next_candle()
    if conf >= 70: conf_color = "#00c896"
    elif conf >= 40: conf_color = "#f0b90b"
    else: conf_color = "#ef5350"

    st.markdown(f"""
    <div class="range-card">
        <div style="font-size:0.78rem; color:rgba(255,255,255,0.4); margin-bottom:12px; letter-spacing:.1em; text-transform:uppercase;">
            Predicted range for the next 1-hour bar
        </div>
        <span class="range-lower">Lower: ${lower:,.2f}</span>
        <span class="range-sep">|</span>
        <span class="range-upper">Upper: ${upper:,.2f}</span>
        <div style="margin-top:12px; font-size:0.8rem; color:rgba(255,255,255,0.35);">
            Width: ${upper - lower:,.2f} &nbsp;·&nbsp; Midpoint: ${(upper+lower)/2:,.2f}
        </div>
        <div style="margin-top:16px; display:flex; justify-content:center; gap:40px; align-items:center; flex-wrap:wrap;">
            <div>
                <div style="font-size:0.7rem; color:rgba(255,255,255,0.4); text-transform:uppercase; letter-spacing:.1em; margin-bottom:4px;">Confidence</div>
                <div style="width:120px; height:8px; background:rgba(255,255,255,0.08); border-radius:4px; overflow:hidden;">
                    <div style="width:{conf}%; height:100%; background:{conf_color}; border-radius:4px;"></div>
                </div>
                <div style="font-size:0.85rem; color:{conf_color}; font-weight:700; margin-top:4px;">{conf}/100</div>
            </div>
            <div>
                <div style="font-size:0.7rem; color:rgba(255,255,255,0.4); text-transform:uppercase; letter-spacing:.1em; margin-bottom:4px;">Resolves in</div>
                <div style="font-size:1.3rem; font-weight:800; color:#f0a500;">⏱ {countdown}</div>
                <div style="width:120px; height:4px; background:rgba(255,255,255,0.08); border-radius:2px; overflow:hidden; margin-top:4px;">
                    <div style="width:{progress*100:.1f}%; height:100%; background:#f0a500; border-radius:2px;"></div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Chart (Upgrade 3) ──────────────────────────────────────────────────
    st.markdown('<div class="section-title">📈 Price Chart — Last 48 Bars + Forecast</div>', unsafe_allow_html=True)
    fig = build_chart(raw_bars, lower, upper, history)
    st.plotly_chart(fig, width="stretch")

    # ── Model Explanation Panel (Upgrade 6) ─────────────────────────────────
    with st.expander("🔬 How this prediction was made"):
        exc1, exc2 = st.columns(2)
        with exc1:
            st.markdown(f"""
            **Model Input:** Current BTC = **${live_price:,.2f}**

            **Fitted Student-t Parameters:**
            - Degrees of freedom (df): `{result['df']:.3f}`
            - Location (μ): `{result['loc']:.6f}`
            - Scale (σ): `{result['scale']:.6f}`
            - Adjusted scale: `{result['scaled_scale']:.6f}`

            **Monte Carlo:** `{result['n_sims']:,}` simulated paths
            **Percentiles:** 2.5th and 97.5th
            """)
        with exc2:
            vb = result["vol_breakdown"]
            if vb:
                st.markdown(f"""
                **Blended Volatility (GARCH-inspired):**
                - Short ({sb_short}h): `{vb['short']:.6f}` × 50%
                - Medium ({sb_medium}h): `{vb['medium']:.6f}` × 30%
                - Long ({sb_long}h): `{vb['long']:.6f}` × 20%
                - **Blended:** `{result['blended_vol']:.6f}`
                """)
            else:
                st.markdown(f"**Volatility:** Fallback std = `{result['blended_vol']:.6f}` (insufficient history)")

        # Mini histogram
        sim_prices = result["simulated_prices"]
        hist_fig = go.Figure()
        hist_fig.add_trace(go.Histogram(x=sim_prices, nbinsx=80,
            marker_color="rgba(100,150,255,0.5)", marker_line_color="rgba(100,150,255,0.8)", marker_line_width=0.5,
            name="Simulated Prices"))
        for val, color, label in [(lower, "#ef4444", "Lower"), (live_price, "#f0a500", "Current"), (upper, "#22c55e", "Upper")]:
            hist_fig.add_vline(x=val, line_dash="dash", line_color=color, line_width=2,
                annotation_text=label, annotation_font_color=color, annotation_font_size=10)
        hist_fig.update_layout(paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(family="Inter", color="white", size=11),
            margin=dict(l=8, r=8, t=24, b=8), height=220, showlegend=False,
            xaxis=dict(tickformat="$,.0f", gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
        st.plotly_chart(hist_fig, width="stretch")

    # ── Backtest Metrics Row + Gauge (Upgrades 2, 9) ────────────────────────
    st.markdown('<div class="section-title">📊 Backtest Performance</div>', unsafe_allow_html=True)
    if bt is None:
        st.warning("Backtest metrics unavailable — run `python backtest.py` first.")
    else:
        # Compute live coverage
        live_resolved = [r for r in history if r.get("in_range") is not None]
        live_cov = (sum(1 for r in live_resolved if r["in_range"]) / len(live_resolved) * 100) if live_resolved else None

        gc1, gc2, gc3 = st.columns([1.2, 1, 1])
        with gc1:
            gauge_svg = render_gauge(bt["coverage"])
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Coverage Gauge</div>
                {gauge_svg}
                <div class="metric-sub">Backtest: {bt['coverage']:.2f}% (n={bt['n']})</div>
                {"<div class='metric-sub gauge-pulse' style='color:#f0a500;'>Live: " + f"{live_cov:.1f}% ({len(live_resolved)} resolved)</div>" if live_cov is not None else ""}
            </div>
            """, unsafe_allow_html=True)
        with gc2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Mean Width</div>
                <div class="metric-value">${bt['mean_width']:,.0f}</div>
                <div class="metric-sub">Avg forecast range</div>
            </div>
            """, unsafe_allow_html=True)
        with gc3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Mean Winkler Score</div>
                <div class="metric-value">${bt['mean_winkler']:,.0f}</div>
                <div class="metric-sub">Lower = better</div>
            </div>
            """, unsafe_allow_html=True)

    # ── UPGRADE 7: Rolling Metrics Chart (full backtest + live) ──────────────
    bt_records = bt.get("records", []) if bt else []
    live_resolved = [r for r in history if r.get("actual_at_close") is not None]
    if len(bt_records) >= 30:
        st.markdown('<div class="section-title">📉 Rolling Model Stability (30-bar window)</div>', unsafe_allow_html=True)
        # Combine backtest + live into unified record list
        all_recs = []
        for r in bt_records:
            all_recs.append({"ts": r["timestamp"], "lower": r["lower"], "upper": r["upper"], "actual": r["actual"]})
        for r in live_resolved:
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

        rfig = make_subplots(specs=[[{"secondary_y": True}]])
        rfig.add_trace(go.Scatter(x=roll_ts, y=roll_cov, name="Coverage", line=dict(color="#00c896", width=2)), secondary_y=False)
        rfig.add_trace(go.Scatter(x=roll_ts, y=roll_wink, name="Winkler", line=dict(color="#f0b90b", width=2)), secondary_y=True)
        rfig.add_hline(y=0.95, line_dash="dot", line_color="rgba(0,200,150,0.3)", secondary_y=False)
        rfig.update_layout(paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(family="Inter", color="white"), margin=dict(l=8, r=8, t=16, b=8), height=280,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
        rfig.update_yaxes(title_text="Coverage", gridcolor="rgba(255,255,255,0.05)", secondary_y=False)
        rfig.update_yaxes(title_text="Winkler $", gridcolor="rgba(255,255,255,0.05)", secondary_y=True)
        st.plotly_chart(rfig, width="stretch")

    # ── Save prediction ────────────────────────────────────────────────────
    last_bar_open_ms = int(raw_bars[-1][0])
    next_candle_open = datetime.fromtimestamp(last_bar_open_ms / 1000, tz=timezone.utc) + timedelta(hours=1)
    next_candle_open_iso = next_candle_open.isoformat()
    new_record = {
        "candle_open": next_candle_open_iso, "lower": round(lower, 2),
        "upper": round(upper, 2), "actual_at_close": None,
        "in_range": None, "generated_at": prediction_time.isoformat(),
    }
    existing_for_candle = next((r for r in history if r.get("candle_open") == next_candle_open_iso), None)
    if existing_for_candle and existing_for_candle.get("actual_at_close") is not None:
        new_record["actual_at_close"] = existing_for_candle["actual_at_close"]
        new_record["in_range"] = existing_for_candle["in_range"]
    save_prediction(new_record)
    history = backfill_actuals(HISTORY_FILE)

    # ── Prediction History Table ────────────────────────────────────────────
    st.markdown('<div class="section-title">📋 Prediction History</div>', unsafe_allow_html=True)
    if not history:
        st.info("No prediction history yet. Check back after the next candle closes.")
    else:
        def fmt_dt(iso_str):
            if not iso_str or iso_str == "—": return "—"
            try:
                dt = datetime.fromisoformat(iso_str).astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception: return iso_str

        rows_with_gaps = add_display_gaps(history[-50:])
        display_rows = []
        for r in rows_with_gaps:
            if r.get("_is_summary"):
                display_rows.append({
                    "Candle Open (UTC)": f"... {r['_count']} more unvisited hours",
                    "Lower ($)": "—", "Upper ($)": "—",
                    "Actual ($)": "—", "In Range": "—", "Generated At": "—",
                })
            elif r.get("_is_gap"):
                display_rows.append({"Candle Open (UTC)": fmt_dt(r["candle_open"]),
                    "Lower ($)": "not visited", "Upper ($)": "not visited",
                    "Actual ($)": "—", "In Range": "—", "Generated At": "—"})
            else:
                actual = r.get("actual_at_close")
                in_range = r.get("in_range")
                display_rows.append({
                    "Candle Open (UTC)": fmt_dt(r.get("candle_open")),
                    "Lower ($)": f"{r['lower']:,.2f}" if r.get("lower") is not None else "—",
                    "Upper ($)": f"{r['upper']:,.2f}" if r.get("upper") is not None else "—",
                    "Actual ($)": f"{actual:,.2f}" if actual is not None else "—",
                    "In Range": "✅" if in_range is True else ("❌" if in_range is False else "—"),
                    "Generated At": fmt_dt(r.get("generated_at")),
                })
        df = pd.DataFrame(display_rows)
        st.dataframe(df, width="stretch", hide_index=True)

    # ── Footer ──────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center; margin-top:48px; padding-top:16px;
                border-top:1px solid rgba(255,255,255,0.08);
                font-size:0.75rem; color:rgba(255,255,255,0.25);">
        Built for AlphaI × Polaris · GBM + Student-t fat-tail model ·
        GARCH-inspired adaptive volatility · Data: Binance public mirror · No API key required
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
