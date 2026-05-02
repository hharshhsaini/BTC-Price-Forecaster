"""
app.py — Part B + C: Live BTC Forecast Dashboard
Streamlit app: fetches live data, runs GBM+Student-t, shows prediction.
Bonus (Part C): persists predictions to prediction_history.jsonl.
Run: streamlit run app.py
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import plotly.graph_objects as go
import requests
import streamlit as st
from scipy import stats
from streamlit_autorefresh import st_autorefresh

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BTC Price Forecaster | AlphaI × Polaris",
    page_icon="₿",
    layout="wide",
)

# Refresh UI every 10 seconds to show latest live price
st_autorefresh(interval=10_000, limit=10000, key="btc_live_refresh")

# ─── Constants ────────────────────────────────────────────────────────────────
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
BINANCE_PARAMS = {"symbol": "BTCUSDT", "interval": "1h", "limit": 500}
N_SIMS = 10_000
ALPHA = 0.05
LONG_WINDOW = 168
SHORT_WINDOW = 24
HISTORY_FILE = "prediction_history.jsonl"
BACKTEST_FILE = "backtest_results.jsonl"

# ─── CSS Styling ──────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border: 1px solid rgba(255,165,0,0.25);
        border-radius: 16px;
        padding: 20px 24px;
        text-align: center;
        box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    }
    .metric-label {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #f0a500;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 900;
        color: #ffffff;
        line-height: 1;
    }
    .metric-sub {
        font-size: 0.72rem;
        color: rgba(255,255,255,0.45);
        margin-top: 4px;
    }
    .price-hero {
        background: linear-gradient(135deg, #f0a500, #ff6b35);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3.2rem;
        font-weight: 900;
        line-height: 1;
    }
    .range-card {
        background: linear-gradient(135deg, #0d2137, #0a1628);
        border: 1px solid rgba(34,197,94,0.3);
        border-radius: 16px;
        padding: 24px 32px;
        text-align: center;
    }
    .range-lower { color: #ef4444; font-size: 1.6rem; font-weight: 800; }
    .range-upper { color: #22c55e; font-size: 1.6rem; font-weight: 800; }
    .range-sep { color: rgba(255,255,255,0.4); font-size: 1.4rem; margin: 0 16px; }
    .section-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #f0a500;
        border-left: 4px solid #f0a500;
        padding-left: 12px;
        margin: 32px 0 16px 0;
    }
    .timestamp-badge {
        display: inline-block;
        background: rgba(240,165,0,0.12);
        border: 1px solid rgba(240,165,0,0.3);
        border-radius: 24px;
        padding: 4px 16px;
        font-size: 0.78rem;
        color: #f0a500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─── BUG 1: Load backtest metrics dynamically — never hardcoded ───────────────
def load_backtest_metrics(path=BACKTEST_FILE):
    if not os.path.exists(path):
        return None
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    if not records:
        return None
    alpha = 0.05
    coverage_flags, widths, winklers = [], [], []
    for r in records:
        lo, hi, actual = float(r["lower"]), float(r["upper"]), float(r["actual"])
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
        "coverage": round(np.mean(coverage_flags) * 100, 2),
        "mean_width": round(np.mean(widths), 2),
        "mean_winkler": round(np.mean(winklers), 2),
        "n": len(records),
    }


# ─── BUG 2A: Clean malformed/duplicate rows at startup ────────────────────────
def clean_history(path=HISTORY_FILE):
    """Remove rows with missing/null candle_open, then deduplicate by candle_open."""
    if not os.path.exists(path):
        return
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            co = r.get("candle_open")
            if not co or co in ("—", "null", None):
                continue
            rows.append(r)
    # Deduplicate: keep last entry per candle_open
    seen = {}
    for r in rows:
        seen[r["candle_open"]] = r
    clean = list(seen.values())
    with open(path, "w") as f:
        for r in clean:
            f.write(json.dumps(r) + "\n")


clean_history()  # run once at module load before anything reads the file


# ─── Live ticker via REST polling (replaces WebSocket) ──────────────────────────
@st.cache_data(ttl=10)  # re-fetches every 10 seconds automatically
def fetch_live_ticker():
    """
    Fetch current BTC price and 24h change from Binance REST.
    Uses the geo-safe mirror. Returns (price, change_pct).
    """
    try:
        resp = requests.get(
            "https://data-api.binance.vision/api/v3/ticker/24hr",
            params={"symbol": "BTCUSDT"},
            timeout=5,
        )
        data = resp.json()
        return float(data["lastPrice"]), float(data["priceChangePercent"])
    except Exception:
        return None, None


# ─── Klines (historical candles) ────────────────────────────────────────────
@st.cache_data(ttl=300)  # refresh every 5 minutes
def fetch_klines() -> tuple:
    resp = requests.get(BINANCE_URL, params=BINANCE_PARAMS, timeout=30)
    resp.raise_for_status()
    raw_bars = resp.json()
    closes = np.array([float(k[4]) for k in raw_bars])
    timestamps_ms = [int(k[0]) for k in raw_bars]
    return closes, timestamps_ms, raw_bars


# ─── GBM + Student-t Model ────────────────────────────────────────────────────
def fit_student_t(returns: np.ndarray) -> tuple:
    if len(returns) < 3:
        return 3.0, 0.0, 1e-4
    df, loc, scale = stats.t.fit(returns)
    return max(df, 2.01), loc, scale


def recent_vol_scale(returns: np.ndarray, short_window: int = SHORT_WINDOW) -> float:
    if len(returns) < short_window + 1:
        return 1.0
    long_std = returns.std()
    short_std = returns[-short_window:].std()
    if long_std < 1e-12:
        return 1.0
    return short_std / long_std


def predict_next(closes: np.ndarray) -> tuple:
    """Run GBM+Student-t on closes; return (lower, upper) for next bar."""
    log_returns = np.diff(np.log(closes))
    fit_returns = log_returns[-LONG_WINDOW:] if len(log_returns) >= LONG_WINDOW else log_returns

    df, loc, scale = fit_student_t(fit_returns)
    vol_ratio = recent_vol_scale(fit_returns, SHORT_WINDOW)
    scaled_scale = scale * vol_ratio

    rng = np.random.default_rng(int(time.time()))
    sampled = stats.t.rvs(df=df, loc=loc, scale=scaled_scale, size=N_SIMS, random_state=rng)
    next_prices = closes[-1] * np.exp(sampled)

    return float(np.percentile(next_prices, 2.5)), float(np.percentile(next_prices, 97.5))


# ─── Save prediction — always overwrites latest for same candle_open ────────────
def save_prediction(record: dict, path: str = HISTORY_FILE):
    # Validate
    co = record.get("candle_open")
    if not co or co in ("—", None, "null"):
        return

    existing = []
    try:
        with open(path) as f:
            existing = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        pass

    # Remove old entry for same candle_open (replace with latest)
    existing = [r for r in existing if r.get("candle_open") != co]
    existing.append(record)

    # Keep sorted by candle_open descending (newest first)
    existing.sort(key=lambda r: r.get("candle_open", ""), reverse=True)

    with open(path, "w") as f:
        for r in existing:
            f.write(json.dumps(r) + "\n")


# ─── FIX 3: Backfill actuals from live Binance data ───────────────────────────
def backfill_actuals(history_path: str = HISTORY_FILE):
    """Fetch latest bars and fill in actual prices for past predictions."""
    try:
        with open(history_path) as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []

    if not rows:
        return rows

    # Fetch enough bars to cover history window
    resp = requests.get(
        BINANCE_URL,
        params={"symbol": "BTCUSDT", "interval": "1h", "limit": 500},
    )
    bars = resp.json()
    # Build map: candle_open_time_ms -> close_price
    bar_map = {int(b[0]): float(b[4]) for b in bars}

    updated = False
    for row in rows:
        if row.get("actual_at_close") is None:
            try:
                dt = datetime.fromisoformat(row["candle_open"])
                ts_ms = int(dt.timestamp() * 1000)
                if ts_ms in bar_map:
                    row["actual_at_close"] = round(bar_map[ts_ms], 2)
                    in_range = row["lower"] <= row["actual_at_close"] <= row["upper"]
                    row["in_range"] = in_range
                    updated = True
            except Exception:
                pass

    if updated:
        with open(history_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    return rows


# ─── Chart Builder ─────────────────────────────────────────────────────────────
def build_chart(closes: np.ndarray, ts_ms_list: list, lower: float, upper: float) -> go.Figure:
    last_50_closes = closes[-50:]
    last_50_ts = ts_ms_list[-50:]
    datetimes = [datetime.fromtimestamp(t / 1000, tz=timezone.utc) for t in last_50_ts]

    # Next candle's open timestamp (last close time + 3600s)
    next_ts = datetime.fromtimestamp(last_50_ts[-1] / 1000 + 3600, tz=timezone.utc)

    fig = go.Figure()

    # Close price line
    fig.add_trace(
        go.Scatter(
            x=datetimes,
            y=last_50_closes,
            mode="lines",
            name="BTC Close",
            line=dict(color="#f0a500", width=2),
            hovertemplate="<b>%{x|%Y-%m-%d %H:%M} UTC</b><br>Close: $%{y:,.2f}<extra></extra>",
        )
    )

    # Shaded ribbon for predicted range (upcoming bar)
    fig.add_trace(
        go.Scatter(
            x=[datetimes[-1], next_ts, next_ts, datetimes[-1]],
            y=[upper, upper, lower, lower],
            fill="toself",
            fillcolor="rgba(34,197,94,0.15)",
            line=dict(color="rgba(34,197,94,0)", width=0),
            name="95% Forecast",
            hoverinfo="skip",
        )
    )

    # Upper bound line
    fig.add_trace(
        go.Scatter(
            x=[datetimes[-1], next_ts],
            y=[upper, upper],
            mode="lines",
            line=dict(color="#22c55e", width=1.5, dash="dot"),
            name=f"Upper ${upper:,.0f}",
            hovertemplate=f"Upper: ${upper:,.2f}<extra></extra>",
        )
    )

    # Lower bound line
    fig.add_trace(
        go.Scatter(
            x=[datetimes[-1], next_ts],
            y=[lower, lower],
            mode="lines",
            line=dict(color="#ef4444", width=1.5, dash="dot"),
            name=f"Lower ${lower:,.0f}",
            hovertemplate=f"Lower: ${lower:,.2f}<extra></extra>",
        )
    )

    # Vertical divider at "now"
    fig.add_vline(
        x=datetimes[-1].timestamp() * 1000,
        line_width=1,
        line_dash="dash",
        line_color="rgba(255,255,255,0.25)",
        annotation_text="Now",
        annotation_font_color="rgba(255,255,255,0.4)",
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="white"),
        margin=dict(l=8, r=8, t=16, b=8),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=11),
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            tickfont=dict(size=10),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            tickformat="$,.0f",
            tickfont=dict(size=10),
        ),
        hovermode="x unified",
        height=380,
    )
    return fig


# ─── Gap detector — display-only placeholder rows for unvisited candles ─────────
def add_display_gaps(rows):
    """
    Add placeholder rows for candles that closed but were never predicted.
    These are display-only — NOT saved to the jsonl file.
    """
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

    parsed.sort(key=lambda x: x[0])
    now_utc = datetime.now(timezone.utc)

    result = []
    prev_dt = parsed[0][0]

    for dt, row in parsed:
        gap_dt = prev_dt + timedelta(hours=1)
        while gap_dt < dt:
            if gap_dt < now_utc:  # only show gaps for past candles
                result.append({
                    "candle_open": gap_dt.isoformat(),
                    "lower": None,
                    "upper": None,
                    "actual_at_close": None,
                    "in_range": None,
                    "_is_gap": True,
                })
            gap_dt += timedelta(hours=1)
        result.append(row)
        prev_dt = dt

    return result


# ─── Main App ─────────────────────────────────────────────────────────────────
def main():
    # Header
    st.markdown(
        """
        <div style="text-align:center; padding: 32px 0 8px 0;">
            <span style="font-size:2.8rem; font-weight:900; background:linear-gradient(90deg,#f0a500,#ff6b35);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                ₿ BTC Price Forecaster
            </span>
            <div style="font-size:0.88rem; color:rgba(255,255,255,0.45); margin-top:6px;">
                AlphaI × Polaris Hiring Challenge &nbsp;·&nbsp; GBM + Student-t Model &nbsp;·&nbsp; 95% Confidence Interval
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 1. Headline Backtest Metrics (FIX 1: dynamic from file) ───────────────
    bt = load_backtest_metrics()



    st.markdown('<div class="section-title">📊 Backtest Performance (720 bars)</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)

    if bt is None:
        st.warning("Backtest metrics unavailable — run `python backtest.py` first to generate backtest_results.jsonl.")
    else:
        with c1:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Coverage 95%</div>
                    <div class="metric-value">{bt['coverage']:.2f}%</div>
                    <div class="metric-sub">Target ≈ 95% &nbsp;·&nbsp; n={bt['n']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Mean Width</div>
                    <div class="metric-value">${bt['mean_width']:,.0f}</div>
                    <div class="metric-sub">Avg forecast range</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Mean Winkler Score</div>
                    <div class="metric-value">${bt['mean_winkler']:,.0f}</div>
                    <div class="metric-sub">Lower = better</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Fetch live data ───────────────────────────────────────────────────────
    with st.spinner("Fetching latest BTC data from Binance..."):
        try:
            closes, ts_ms_list, raw_bars = fetch_klines()
        except Exception as e:
            st.error(f"Failed to fetch data: {e}")
            return

    # ── Fetch live ticker (REST poll, cached 10s) ─────────────────────────────
    live_price_ticker, live_change_pct_ticker = fetch_live_ticker()
    rest_close = float(closes[-1])
    live_price = live_price_ticker if live_price_ticker is not None else rest_close
    live_change_pct = live_change_pct_ticker if live_change_pct_ticker is not None else 0.0

    col_price, col_ts = st.columns([2, 1])
    with col_price:
        arrow = "▲" if live_change_pct >= 0 else "▼"
        change_color = "#00c896" if live_change_pct >= 0 else "#ff4b4b"
        badge_label = "● LIVE (10s)"
        badge_color = "#00c896"
        st.markdown(
            f"""
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
                    <span style="font-size:0.75rem; color:{badge_color};
                        border:1px solid {badge_color}33;
                        border-radius:4px; padding:2px 8px;">
                        {badge_label}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        st.caption(f"⚡ REST ticker · Refreshes every 10s · Last: {now_str}")

    # ── Run Model with live price as intra-candle tick ────────────────────────
    # Replace last REST close with live tick so forecast reflects current moment
    closes_for_model = np.append(closes[:-1], live_price)
    with st.spinner("Running GBM + Student-t simulation (10,000 paths)..."):
        lower, upper = predict_next(closes_for_model)

    prediction_time = datetime.now(tz=timezone.utc)

    with col_ts:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="text-align:right; padding-top:16px;">
                <div class="timestamp-badge">🕐 Generated {prediction_time.strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── 3. Predicted Range ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🎯 Next 1-Hour Candle — 95% Confidence Range</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
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
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 4. Chart ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📈 Price Chart — Last 50 Bars + Forecast</div>', unsafe_allow_html=True)
    fig = build_chart(closes, ts_ms_list, lower, upper)
    st.plotly_chart(fig, use_container_width=True)

    # ── 5. Timestamp badge ────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="text-align:center; margin-top:8px; margin-bottom:32px;">
            <span class="timestamp-badge">
                ⏱ Prediction generated at {prediction_time.strftime('%Y-%m-%d %H:%M:%S')} UTC
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── Part C: Prediction Persistence ──────────────────────────────────────

    # FIX 4: Compute next candle's open time correctly from raw bar data
    last_bar_open_ms = int(raw_bars[-1][0])  # open time of last fetched bar
    next_candle_open = (
        datetime.fromtimestamp(last_bar_open_ms / 1000, tz=timezone.utc) + timedelta(hours=1)
    )
    next_candle_open_iso = next_candle_open.isoformat()

    new_record = {
        "candle_open": next_candle_open_iso,
        "lower": round(lower, 2),
        "upper": round(upper, 2),
        "actual_at_close": None,
        "in_range": None,
        "generated_at": prediction_time.isoformat(),
    }

    # ── Step 1: Backfill actuals FIRST (before saving new record) ───────────
    history = backfill_actuals(HISTORY_FILE)

    # ── Step 2: Check if this candle already has an actual backfilled ────────
    # If so, carry it forward so we don't lose it on overwrite
    existing_for_candle = next(
        (r for r in history if r.get("candle_open") == next_candle_open_iso), None
    )
    if existing_for_candle and existing_for_candle.get("actual_at_close") is not None:
        new_record["actual_at_close"] = existing_for_candle["actual_at_close"]
        new_record["in_range"] = existing_for_candle["in_range"]

    # ── Step 3: Save (overwrites previous entry for same candle_open) ────────
    save_prediction(new_record)

    # ── Step 4: Reload history for display ───────────────────────────────
    history = backfill_actuals(HISTORY_FILE)

    st.markdown('<div class="section-title">📋 Prediction History</div>', unsafe_allow_html=True)

    if not history:
        st.info("No prediction history yet. Check back after the next candle closes.")
    else:
        import pandas as pd

        # ─── Readable timestamp formatter ─────────────────────────────────────
        def fmt_dt(iso_str):
            """Convert ISO string to readable UTC display: '2026-05-02 04:00 UTC'"""
            if not iso_str or iso_str == "—":
                return "—"
            try:
                dt = datetime.fromisoformat(iso_str)
                dt = dt.astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                return iso_str

        # Add gap rows for unvisited candles (display-only, not saved to file)
        rows_with_gaps = add_display_gaps(history[-50:])

        # Sort descending by candle_open (newest first)
        rows_with_gaps.sort(
            key=lambda r: r.get("candle_open", ""),
            reverse=True,
        )

        display_rows = []
        for r in rows_with_gaps:
            if r.get("_is_gap"):
                display_rows.append({
                    "Candle Open (UTC)": fmt_dt(r["candle_open"]),
                    "Lower ($)": "not visited",
                    "Upper ($)": "not visited",
                    "Actual ($)": "—",
                    "In Range": "—",
                    "Generated At": "—",
                })
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
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

    # Footer
    st.markdown(
        """
        <div style="text-align:center; margin-top:48px; padding-top:16px;
                    border-top:1px solid rgba(255,255,255,0.08);
                    font-size:0.75rem; color:rgba(255,255,255,0.25);">
            Built for AlphaI × Polaris · GBM + Student-t fat-tail model ·
            Data: Binance public mirror · No API key required
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
