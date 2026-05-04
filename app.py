import streamlit as st
import streamlit.components.v1 as components
import json
import numpy as np
from scipy import stats
from datetime import datetime, timezone, timedelta
import requests
import os
import math

st.set_page_config(
    page_title="BTC Price Forecaster",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Hide ALL streamlit chrome
st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.block-container { 
    padding: 0 !important; 
    max-width: 100% !important;
}
[data-testid="stAppViewContainer"] {
    background: #050508;
}
</style>
""", unsafe_allow_html=True)

# ── Load backtest metrics (Python side, runs once) ─────────────────
def load_backtest_metrics(path="backtest_results.jsonl"):
    if not os.path.exists(path):
        return {"coverage": 0.0, "mean_width": 0, 
                "mean_winkler": 0, "n": 0}
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try: records.append(json.loads(line))
                except: pass
    if not records:
        return {"coverage": 0.0, "mean_width": 0,
                "mean_winkler": 0, "n": 0}
    alpha = 0.05
    cov, widths, winks = [], [], []
    for r in records:
        lo, hi, actual = float(r["lower"]), float(r["upper"]), float(r["actual"])
        w = hi - lo
        inside = lo <= actual <= hi
        cov.append(int(inside))
        widths.append(w)
        winks.append(w if inside else w + (2/alpha)*min(
            abs(actual-lo), abs(actual-hi)))
    return {
        "coverage": round(np.mean(cov)*100, 2),
        "mean_width": round(np.mean(widths), 2),
        "mean_winkler": round(np.mean(winks), 2),
        "n": len(records)
    }

# ── Load prediction history (Python side, runs once) ───────────────
def load_history(path="prediction_history.jsonl"):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try: rows.append(json.loads(line))
                except: pass
    # Sort newest first
    rows.sort(key=lambda r: r.get("candle_open",""), reverse=True)
    return rows[:50]  # last 50 only

# ── Load rolling backtest data ─────────────────────────────────────
def load_rolling_data(path="backtest_results.jsonl", window=60):
    if not os.path.exists(path):
        return [], [], []
    records = []
    with open(path) as f:
        for line in f:
            try: records.append(json.loads(line.strip()))
            except: pass
    if len(records) < window:
        return [], [], []
    alpha = 0.05
    ts, covs, winks = [], [], []
    for i in range(window, len(records)):
        w = records[i-window:i]
        cf, ws = [], []
        for r in w:
            lo,hi,ac = float(r["lower"]),float(r["upper"]),float(r["actual"])
            wd = hi-lo
            inside = lo<=ac<=hi
            cf.append(int(inside))
            ws.append(wd if inside else wd+(2/alpha)*min(
                abs(ac-lo),abs(ac-hi)))
        ts.append(records[i]["timestamp"])
        covs.append(round(float(np.mean(cf))*100, 2))
        winks.append(round(float(np.mean(ws)), 2))
    return ts, covs, winks

metrics = load_backtest_metrics()
history = load_history()
roll_ts, roll_cov, roll_wink = load_rolling_data()

# Build history rows for table
def fmt_history_rows(rows):
    out = []
    for r in rows:
        co = r.get("candle_open","")
        try:
            dt = datetime.fromisoformat(co)
            co_fmt = dt.strftime("%Y-%m-%d %H:%M UTC")
        except:
            co_fmt = co
        
        ga = r.get("generated_at","")
        try:
            dt2 = datetime.fromisoformat(ga)
            ga_fmt = dt2.strftime("%Y-%m-%d %H:%M UTC")
        except:
            ga_fmt = ga
            
        actual = r.get("actual_at_close")
        in_range = r.get("in_range")
        out.append({
            "candle": co_fmt,
            "lower": f"${r['lower']:,.2f}" if r.get("lower") else "—",
            "upper": f"${r['upper']:,.2f}" if r.get("upper") else "—",
            "actual": f"${actual:,.2f}" if actual else "—",
            "result": ("HIT" if in_range is True else 
                      "MISS" if in_range is False else "PENDING"),
            "generated": ga_fmt,
            "is_gap": r.get("_is_gap", False),
            "is_summary": r.get("_is_summary", False),
            "count": r.get("_count", 0)
        })
    return out

history_rows = fmt_history_rows(history)

# Pass data to JS as JSON
metrics_json = json.dumps(metrics)
history_json = json.dumps(history_rows)
roll_json = json.dumps({
    "ts": roll_ts[-200:],
    "cov": roll_cov[-200:],
    "wink": roll_wink[-200:]
})

# ── Gauge math (Python) ────────────────────────────────────────────
def gauge_needle(coverage_pct):
    display_min, display_max = 80.0, 100.0
    clamped = max(display_min, min(display_max, float(coverage_pct)))
    fraction = (clamped - display_min) / (display_max - display_min)
    needle_deg = 180.0 - (fraction * 180.0)
    needle_rad = math.radians(needle_deg)
    cx, cy, r = 120, 95, 75
    nx = round(cx + r * math.cos(needle_rad), 2)
    ny = round(cy - r * math.sin(needle_rad), 2)
    tail_r = 10
    tx = round(cx - tail_r * math.cos(needle_rad), 2)
    ty = round(cy + tail_r * math.sin(needle_rad), 2)
    return cx, cy, r, nx, ny, tx, ty

def arc_path(cx, cy, r, a1, a2, color, width=10):
    def pt(deg):
        rad = math.radians(deg)
        return (cx + r*math.cos(rad), cy - r*math.sin(rad))
    x1,y1 = pt(a1); x2,y2 = pt(a2)
    large = 1 if abs(a1-a2) > 180 else 0
    return (f'<path d="M{x1:.1f},{y1:.1f} A{r},{r} 0 {large},1 '
            f'{x2:.1f},{y2:.1f}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round"/>')

cx,cy,r,nx,ny,tx,ty = gauge_needle(metrics["coverage"])
cov = metrics["coverage"]
ncol = ("#10b981" if abs(cov-95)<1.5 else 
        "#6366f1" if cov>=97 else 
        "#f59e0b" if cov>=93 else "#ef4444")

def pt(deg):
    rad = math.radians(deg)
    return (cx + r*math.cos(rad), cy - r*math.sin(rad))

arcs_svg = (
    arc_path(cx,cy,r, 180, 90, 'rgba(239,68,68,0.4)') +
    arc_path(cx,cy,r, 90,  54, 'rgba(245,158,11,0.4)') +
    arc_path(cx,cy,r, 54,  18, 'rgba(16,185,129,0.5)') +
    arc_path(cx,cy,r, 18,   0, 'rgba(99,102,241,0.4)')
)
lx,ly = pt(180); rx,ry = pt(0)
mx_out,my_out = pt(45)
mx_in = cx+(r-14)*math.cos(math.radians(45))
my_in = cy-(r-14)*math.sin(math.radians(45))
bg_arc = arc_path(cx,cy,r,180,0,'rgba(255,255,255,0.06)')

# Build history table rows HTML
def build_table_rows(rows):
    html = ""
    for r in rows:
        if r.get("is_summary"):
            html += f"""<tr>
                <td colspan="6" style="text-align:center;
                    color:rgba(255,255,255,0.2);font-style:italic;
                    font-size:11px;padding:6px;">
                    ··· {r['count']} unvisited hours collapsed ···
                </td></tr>"""
            continue
        if r.get("is_gap"):
            html += f"""<tr style="opacity:0.35;">
                <td style="color:rgba(255,255,255,0.4);">{r['candle']}</td>
                <td colspan="4" style="color:rgba(255,255,255,0.25);
                    font-style:italic;">not visited</td>
                <td>—</td></tr>"""
            continue
        result = r.get("result","PENDING")
        result_html = {
            "HIT":  '<span style="color:#10b981;font-weight:700;">&#10003; HIT</span>',
            "MISS": '<span style="color:#ef4444;font-weight:700;">&#10007; MISS</span>',
        }.get(result, '<span style="color:rgba(255,255,255,0.3);">PENDING</span>')
        
        html += f"""<tr>
            <td>{r['candle']}</td>
            <td style="color:#ef4444;">{r['lower']}</td>
            <td style="color:#10b981;">{r['upper']}</td>
            <td style="color:rgba(255,255,255,0.8);">{r['actual']}</td>
            <td>{result_html}</td>
            <td style="color:rgba(255,255,255,0.3);">{r['generated']}</td>
        </tr>"""
    return html

table_rows_html = build_table_rows(history_rows)

# ── Render the entire dashboard as one component ───────────────────
dashboard_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}

body {{
    background: #050508;
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
    overflow-x: hidden;
}}

/* ── Scrollbar ── */
::-webkit-scrollbar {{ width:4px; height:4px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ 
    background:rgba(255,255,255,0.15); border-radius:2px; 
}}
.audit-scroll::-webkit-scrollbar {{ width: 6px; }}
.audit-scroll::-webkit-scrollbar-track {{ background: rgba(0,0,0,0.1); border-radius: 4px; }}
.audit-scroll::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.25); border-radius: 4px; }}
.audit-scroll::-webkit-scrollbar-thumb:hover {{ background: rgba(255,255,255,0.4); }}

/* ── Glass cards ── */
.glass {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 16px;
    backdrop-filter: blur(20px);
    transition: border-color 0.2s;
}}
.glass:hover {{ border-color: rgba(255,255,255,0.12); }}
.glass-btc {{
    background: rgba(247,147,26,0.05);
    border: 1px solid rgba(247,147,26,0.15);
    border-radius: 16px;
}}

/* ── Typography ── */
.label {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
    font-family: 'SF Mono', monospace;
}}
.val-xl {{
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    font-family: 'SF Mono', monospace;
    line-height: 1.1;
}}
.val-lg {{
    font-size: 1.5rem;
    font-weight: 700;
    font-family: 'SF Mono', monospace;
}}
.divider {{
    height: 1px;
    background: linear-gradient(90deg, transparent, 
                rgba(255,255,255,0.06), transparent);
    margin: 10px 0;
}}

/* ── Progress bar ── */
.track {{
    height: 3px;
    background: rgba(255,255,255,0.06);
    border-radius:100px;
    margin-top: 6px;
    overflow: hidden;
}}
.fill {{ height:100%; border-radius:100px; }}

/* ── Ticker ── */
@keyframes ticker {{
    0%   {{ transform: translateX(0); }}
    100% {{ transform: translateX(-33.33%); }}
}}
.ticker-wrap {{
    overflow: hidden;
    background: rgba(255,255,255,0.02);
    border-top: 1px solid rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding: 7px 0;
    white-space: nowrap;
}}
.ticker-inner {{
    display: inline-block;
    animation: ticker 35s linear infinite;
    font-size: 11px;
    font-family: 'SF Mono', monospace;
    white-space: nowrap;
}}

/* ── Table ── */
.btc-table {{ width:100%; border-collapse:collapse; }}
.btc-table th {{
    font-size: 9px; font-weight:600; letter-spacing:0.1em;
    color: rgba(255,255,255,0.25); text-transform:uppercase;
    padding: 8px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    text-align: left;
    position: sticky; top:0;
    background: rgba(10,10,15,0.98);
    backdrop-filter: blur(10px);
    z-index: 2;
}}
.btc-table td {{
    padding: 9px 12px; font-size:12px;
    color: rgba(255,255,255,0.7);
    border-bottom: 1px solid rgba(255,255,255,0.03);
    font-family: 'SF Mono', monospace;
}}
.btc-table tr:hover td {{
    background: rgba(255,255,255,0.02);
}}

/* ── Pulse ── */
@keyframes pulse {{
    0%,100% {{ opacity:1; box-shadow:0 0 6px #10b981; }}
    50% {{ opacity:0.5; box-shadow:0 0 12px #10b981; }}
}}
.pulse-dot {{
    width:7px; height:7px; border-radius:50%;
    background:#10b981;
    animation: pulse 2s infinite;
    display:inline-block;
}}

/* ── Layout ── */
.header {{
    padding: 14px 28px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky; top:0; z-index:100;
    background: rgba(5,5,8,0.97);
    backdrop-filter: blur(20px);
}}
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    padding: 14px 20px;
}}
.kpi-card {{
    padding: 16px 18px;
}}
.chart-row {{
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 12px;
    padding: 0 20px 14px;
}}
.metrics-row {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    padding: 0 20px 14px;
}}
.section-label {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.1em;
    color: rgba(255,255,255,0.25);
    text-transform: uppercase;
    padding: 0 20px;
    margin-bottom: 6px;
}}
</style>
</head>
<body>

<!-- ── HEADER ─────────────────────────────────────────────── -->
<div class="header">
    <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:38px;height:38px;border-radius:10px;
                    background:linear-gradient(135deg,#F7931A,#e8750a);
                    display:flex;align-items:center;justify-content:center;
                    font-size:20px;font-weight:900;color:white;
                    box-shadow:0 4px 15px rgba(247,147,26,0.3);">
            &#x20BF;
        </div>
        <div>
            <div style="font-size:17px;font-weight:700;
                        color:#fff;letter-spacing:-0.01em;">
                BTC Price Forecaster
            </div>
            <div style="font-size:10px;color:rgba(255,255,255,0.3);
                        letter-spacing:0.06em;">
                AlphaI &times; Polaris &nbsp;·&nbsp; GBM + Student-t 
                &nbsp;·&nbsp; 99% Confidence Interval
            </div>
        </div>
    </div>
    
    <div style="text-align:center;">
        <div id="hdr-price" class="val-xl" 
             style="color:#F7931A;font-size:2.2rem;">
            Loading...
        </div>
        <div id="hdr-change" style="font-size:12px;font-weight:600;">
            —
        </div>
    </div>
    
    <div style="text-align:right;">
        <div style="display:inline-flex;align-items:center;gap:6px;
                    background:rgba(16,185,129,0.08);
                    border:1px solid rgba(16,185,129,0.2);
                    border-radius:100px;padding:5px 12px;margin-bottom:5px;">
            <span class="pulse-dot"></span>
            <span style="font-size:11px;color:#10b981;
                         font-weight:600;letter-spacing:0.05em;">
                LIVE · 10s
            </span>
        </div>
        <div id="hdr-time" style="font-size:10px;
                                   color:rgba(255,255,255,0.2);
                                   font-family:monospace;display:block;">
        </div>
    </div>
</div>

<!-- ── TICKER ─────────────────────────────────────────────── -->
<div class="ticker-wrap">
    <div class="ticker-inner" id="ticker-inner">
        Loading predictions...
    </div>
</div>

<!-- ── KPI CARDS ──────────────────────────────────────────── -->
<div class="kpi-grid">
    <!-- Current Price -->
    <div class="glass kpi-card">
        <div class="label" style="margin-bottom:8px;">
            <span style="color:#10b981;">&#9679;</span> Current Price
        </div>
        <div id="kpi-price" class="val-xl" style="color:#F7931A;">—</div>
        <div class="divider"></div>
        <div style="font-size:10px;color:rgba(255,255,255,0.35);">
            BTCUSDT · Binance
        </div>
    </div>
    
    <!-- Support -->
    <div class="glass kpi-card">
        <div class="label" style="margin-bottom:8px;">
            <span style="color:#10b981;">&#9660;</span> Support (Low)
        </div>
        <div id="kpi-lower" class="val-xl" style="color:#10b981;">—</div>
        <div class="divider"></div>
        <div style="font-size:10px;color:rgba(255,255,255,0.35);">
            99% lower bound
        </div>
    </div>
    
    <!-- Resistance -->
    <div class="glass kpi-card">
        <div class="label" style="margin-bottom:8px;">
            <span style="color:#ef4444;">&#9650;</span> Resistance (High)
        </div>
        <div id="kpi-upper" class="val-xl" style="color:#ef4444;">—</div>
        <div class="divider"></div>
        <div style="font-size:10px;color:rgba(255,255,255,0.35);">
            99% upper bound
        </div>
    </div>
    
    <!-- Range Width -->
    <div class="glass kpi-card">
        <div class="label" style="margin-bottom:8px;">Range Width</div>
        <div id="kpi-width" class="val-xl" style="color:#fff;">—</div>
        <div class="divider"></div>
        <div style="display:flex;justify-content:space-between;
                    font-size:10px;color:rgba(255,255,255,0.35);">
            <span id="kpi-mid">Mid —</span>
            <span id="kpi-conf">— conf</span>
        </div>
        <div class="track">
            <div id="kpi-conf-bar" class="fill" 
                 style="width:0%;background:#f59e0b;"></div>
        </div>
    </div>
    
    <!-- Resolves In -->
    <div class="glass-btc kpi-card">
        <div class="label" style="margin-bottom:8px;">Resolves In</div>
        <div id="kpi-countdown" class="val-xl" 
             style="color:#F7931A;font-family:monospace;">
            --:--
        </div>
        <div class="divider"></div>
        <div style="font-size:10px;color:rgba(247,147,26,0.6);">
            Next 1H candle close
        </div>
        <div class="track">
            <div id="kpi-time-bar" class="fill" 
                 style="width:0%;
                        background:linear-gradient(90deg,#F7931A,#e8750a);">
            </div>
        </div>
    </div>
</div>

<!-- ── CHART + INSIGHTS ───────────────────────────────────── -->
<div class="chart-row">
    <!-- Chart -->
    <div class="glass" style="padding:12px;overflow:hidden;">
        <div id="ohlc-bar" style="font-size:11px;color:rgba(255,255,255,0.5);
                                   font-family:monospace;margin-bottom:6px;
                                   display:flex;align-items:center;flex-wrap:wrap;gap:12px;">
            <span style="font-weight:600;color:rgba(255,255,255,0.7);">
                BTCUSDT · BINANCE
            </span>
            <span id="c-t" style="color:rgba(255,255,255,0.9);">—</span>
            <span>O <span id="c-o" style="color:rgba(255,255,255,0.7);">—</span></span>
            <span>H <span id="c-h" style="color:#10b981;">—</span></span>
            <span>L <span id="c-l" style="color:#ef4444;">—</span></span>
            <span>C <span id="c-c" style="color:#F7931A;">—</span></span>
            <span>Vol <span id="c-v" style="color:rgba(255,255,255,0.7);">—</span></span>
        </div>
        <div id="chart" style="height:400px;"></div>
    </div>
    
    <!-- Insights panel -->
    <div style="display:flex;flex-direction:column;gap:10px;">
        
        <!-- Price position -->
        <div class="glass" style="padding:16px;">
            <div class="label" style="margin-bottom:10px;">
                Price Position in Range
            </div>
            <div style="position:relative;height:44px;
                        background:rgba(255,255,255,0.03);
                        border-radius:8px;overflow:hidden;
                        border:1px solid rgba(255,255,255,0.06);">
                <div id="range-fill" style="position:absolute;
                     left:0;top:0;bottom:0;width:50%;
                     background:linear-gradient(90deg,
                         rgba(16,185,129,0.2),rgba(247,147,26,0.3));
                     border-radius:8px;transition:width 0.5s ease;"></div>
                <div id="range-needle" style="position:absolute;
                     top:6px;bottom:6px;left:50%;width:3px;
                     background:#F7931A;border-radius:2px;
                     box-shadow:0 0 8px rgba(247,147,26,0.6);
                     transition:left 0.5s ease;"></div>
                <div id="range-lo-label" style="position:absolute;
                     left:8px;top:50%;transform:translateY(-50%);
                     font-size:10px;color:rgba(16,185,129,0.8);
                     font-family:monospace;">—</div>
                <div id="range-hi-label" style="position:absolute;
                     right:8px;top:50%;transform:translateY(-50%);
                     font-size:10px;color:rgba(239,68,68,0.8);
                     font-family:monospace;">—</div>
            </div>
            <div id="range-sub" style="text-align:center;font-size:10px;
                 color:rgba(255,255,255,0.3);margin-top:5px;">—</div>
        </div>
        
        <!-- Model internals -->
        <div class="glass" style="padding:16px;">
            <div class="label" style="margin-bottom:10px;">
                Model Internals
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div style="background:rgba(255,255,255,0.02);
                            border-radius:8px;padding:10px;">
                    <div style="font-size:9px;color:rgba(255,255,255,0.3);
                                margin-bottom:4px;letter-spacing:0.08em;">
                        STUDENT-T DF
                    </div>
                    <div id="m-df" style="font-size:16px;font-weight:600;
                                          color:#818cf8;font-family:monospace;">
                        —
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.02);
                            border-radius:8px;padding:10px;">
                    <div style="font-size:9px;color:rgba(255,255,255,0.3);
                                margin-bottom:4px;letter-spacing:0.08em;">
                        SCALE
                    </div>
                    <div id="m-scale" style="font-size:16px;font-weight:600;
                                              color:#818cf8;font-family:monospace;">
                        —
                    </div>
                </div>
            </div>
            <div style="margin-top:10px;">
                <div style="font-size:9px;color:rgba(255,255,255,0.3);
                            letter-spacing:0.08em;margin-bottom:6px;">
                    VOLATILITY REGIME
                </div>
                <div id="vol-bars"></div>
            </div>
        </div>
        
        <!-- Backtest summary -->
        <div class="glass" style="padding:16px;">
            <div class="label" style="margin-bottom:10px;">
                Backtest · 30D · {metrics['n']} Bars
            </div>
            <div style="display:flex;justify-content:space-between;
                        align-items:baseline;margin-bottom:4px;">
                <span style="font-size:11px;color:rgba(255,255,255,0.4);">
                    Coverage
                </span>
                <span style="font-size:15px;font-weight:700;
                             color:{'#10b981' if abs(metrics['coverage']-95)<2 else '#f59e0b'};
                             font-family:monospace;">
                    {metrics['coverage']:.2f}%
                </span>
            </div>
            <div class="track">
                <div class="fill" 
                     style="width:{metrics['coverage']}%;
                            background:{'#10b981' if abs(metrics['coverage']-95)<2 else '#f59e0b'};">
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;
                        gap:8px;margin-top:10px;">
                <div>
                    <div style="font-size:9px;color:rgba(255,255,255,0.3);">
                        AVG WIDTH
                    </div>
                    <div style="font-size:14px;font-weight:600;
                                color:rgba(255,255,255,0.8);
                                font-family:monospace;">
                        ${metrics['mean_width']:,.0f}
                    </div>
                </div>
                <div>
                    <div style="font-size:9px;color:rgba(255,255,255,0.3);">
                        WINKLER
                    </div>
                    <div style="font-size:14px;font-weight:600;
                                color:rgba(255,255,255,0.8);
                                font-family:monospace;">
                        {metrics['mean_winkler']:,.0f}
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- ── BACKTEST METRICS ROW ────────────────────────────────── -->
<div class="metrics-row">
    <!-- Coverage Gauge -->
    <div class="glass" style="padding:20px;text-align:center;">
        <div class="label" style="margin-bottom:10px;">Coverage Gauge</div>
        <svg viewBox="30 20 180 90" 
             style="width:100%;max-width:240px;display:block;margin:0 auto;">
            {bg_arc}
            {arcs_svg}
            <line x1="{mx_in:.1f}" y1="{my_in:.1f}" 
                  x2="{mx_out:.1f}" y2="{my_out:.1f}"
                  stroke="rgba(255,255,255,0.5)" stroke-width="1.5"/>
            <text x="{mx_out+6:.1f}" y="{my_out-3:.1f}"
                  fill="rgba(255,255,255,0.4)" font-size="7"
                  font-family="monospace">99%</text>
            <line x1="{tx}" y1="{ty}" x2="{nx}" y2="{ny}"
                  stroke="{ncol}" stroke-width="2.5" 
                  stroke-linecap="round"/>
            <circle cx="{cx}" cy="{cy}" r="6" fill="{ncol}"/>
            <circle cx="{cx}" cy="{cy}" r="3" fill="#050508"/>
            <text x="{cx}" y="{cy-18}" text-anchor="middle"
                  fill="{ncol}" font-size="19" font-weight="700"
                  font-family="monospace">{cov:.1f}%</text>
            <text x="{lx-2:.1f}" y="{ly+12:.1f}"
                  fill="rgba(255,255,255,0.25)" font-size="7"
                  text-anchor="middle" font-family="monospace">80%</text>
            <text x="{rx+2:.1f}" y="{ry+12:.1f}"
                  fill="rgba(255,255,255,0.25)" font-size="7"
                  text-anchor="middle" font-family="monospace">100%</text>
        </svg>
        <div style="font-size:11px;color:rgba(255,255,255,0.3);
                    font-family:monospace;margin-top:4px;">
            Backtest: {metrics['coverage']:.2f}% (n={metrics['n']})
        </div>
        <div id="live-cov-label" style="font-size:11px;
                                         color:#10b981;font-family:monospace;
                                         margin-top:2px;"></div>
    </div>
    
    <!-- Mean Width -->
    <div class="glass" style="padding:28px 20px;text-align:center;">
        <div class="label" style="margin-bottom:12px;">Mean Width</div>
        <div class="val-xl" style="font-size:2.2rem;">
            ${metrics['mean_width']:,.0f}
        </div>
        <div class="divider"></div>
        <div style="font-size:11px;color:rgba(255,255,255,0.35);">
            Avg forecast range · lower = better
        </div>
    </div>
    
    <!-- Winkler -->
    <div class="glass" style="padding:28px 20px;text-align:center;">
        <div class="label" style="margin-bottom:12px;">
            Mean Winkler Score
        </div>
        <div class="val-xl" style="font-size:2.2rem;">
            {metrics['mean_winkler']:,.0f}
        </div>
        <div class="divider"></div>
        <div style="font-size:11px;color:rgba(255,255,255,0.35);">
            Efficiency metric · lower = better
        </div>
    </div>
</div>

<!-- ── ROLLING STABILITY CHART ────────────────────────────── -->
<div style="padding:0 20px 14px;">
    <div class="section-label" style="padding:0;margin-bottom:8px;">
        Rolling Model Stability · 60-Bar Window
    </div>
    <div class="glass" style="padding:12px;position:relative;">
        <canvas id="rolling-chart" height="300" style="width: 100%; display: block;"></canvas>
        <div id="rolling-tooltip" style="display:none; position:absolute; pointer-events:none; 
                                       background:rgba(15,15,20,0.95); border:1px solid rgba(255,255,255,0.1); 
                                       padding:8px 12px; border-radius:6px; font-family:monospace; font-size:11px;
                                       z-index:10; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
            <div style="color:#10b981; margin-bottom:4px;" id="tt-cov"></div>
            <div style="color:#f59e0b;" id="tt-wink"></div>
        </div>
    </div>
</div>

<!-- ── PREDICTION HISTORY TABLE ──────────────────────────── -->
<div style="padding:0 20px 28px;">
    <div class="glass" style="padding:0;overflow:hidden;">
        <div style="padding:14px 16px 10px;
                    border-bottom:1px solid rgba(255,255,255,0.05);">
            <div class="label">Prediction Audit Log · Part C</div>
        </div>
        <div class="audit-scroll" style="overflow-y:scroll;max-height:250px;
                    scrollbar-width:thin;
                    scrollbar-color:rgba(255,255,255,0.15) transparent;
                    padding-right:4px;">
            <table class="btc-table">
                <thead>
                    <tr>
                        <th>Candle (UTC)</th>
                        <th>Lower</th>
                        <th>Upper</th>
                        <th>Actual</th>
                        <th>Result</th>
                        <th>Generated</th>
                    </tr>
                </thead>
                <tbody id="history-tbody">
                    {table_rows_html}
                </tbody>
            </table>
        </div>
    </div>
</div>

<div style="text-align:center;padding:16px;
            font-size:10px;color:rgba(255,255,255,0.15);
            font-family:monospace;letter-spacing:0.05em;">
    Built for AlphaI &times; Polaris &nbsp;·&nbsp; 
    GBM + Student-t fat-tail model &nbsp;·&nbsp; 
    Data: Binance public mirror &nbsp;·&nbsp; No API key required
</div>

<!-- ════════════════════════════════════════════════════════ -->
<!-- JAVASCRIPT — ALL LIVE UPDATES HAPPEN HERE               -->
<!-- ════════════════════════════════════════════════════════ -->
<script>
const BINANCE = 'https://api.binance.com/api/v3';
const METRICS = {metrics_json};
const ROLL    = {roll_json};

// ── Lightweight Charts setup ──────────────────────────────
const chartEl = document.getElementById('chart');
const chart = LightweightCharts.createChart(chartEl, {{
    width: chartEl.clientWidth,
    height: 400,
    layout: {{
        background: {{ type:'solid', color:'transparent' }},
        textColor: 'rgba(255,255,255,0.35)',
        fontSize: 11,
        fontFamily: "'SF Mono', monospace",
    }},
    grid: {{
        vertLines: {{ color:'rgba(255,255,255,0.04)' }},
        horzLines: {{ color:'rgba(255,255,255,0.04)' }},
    }},
    crosshair: {{
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: {{ color:'rgba(255,255,255,0.15)', width:1 }},
        horzLine: {{ color:'rgba(255,255,255,0.15)', width:1 }},
    }},
    rightPriceScale: {{
        borderColor: 'rgba(255,255,255,0.06)',
        textColor: 'rgba(255,255,255,0.3)',
        scaleMargins: {{ top:0.08, bottom:0.22 }},
    }},
    timeScale: {{
        borderColor: 'rgba(255,255,255,0.06)',
        textColor: 'rgba(255,255,255,0.3)',
        timeVisible: true,
        secondsVisible: false,
    }},
    handleScroll: {{ 
        mouseWheel: true, 
        pressedMouseMove: true, 
        pinch: true,
        horzTouchDrag: true,
    }},
    handleScale: {{ 
        axisPressedMouseMove: true, 
        mouseWheel: true, 
        pinch: true,
    }},
}});

const candleSeries = chart.addCandlestickSeries({{
    upColor:        '#10b981',
    downColor:      '#ef4444',
    borderUpColor:  '#10b981',
    borderDownColor:'#ef4444',
    wickUpColor:    '#10b981',
    wickDownColor:  '#ef4444',
}});

const volumeSeries = chart.addHistogramSeries({{
    priceFormat: {{ type:'volume' }},
    priceScaleId: 'vol',
}});
chart.priceScale('vol').applyOptions({{
    scaleMargins: {{ top:0.82, bottom:0 }},
}});

const upperLine = chart.addLineSeries({{
    color: 'rgba(239,68,68,0.7)',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    lastValueVisible: true,
    priceLineVisible: false,
    title: 'Upper',
}});
const lowerLine = chart.addLineSeries({{
    color: 'rgba(16,185,129,0.7)',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    lastValueVisible: true,
    priceLineVisible: false,
    title: 'Lower',
}});

// OHLC crosshair display
chart.subscribeCrosshairMove(p => {{
    if (!p.time) return;
    const d = p.seriesData && p.seriesData.get(candleSeries);
    const v = p.seriesData && p.seriesData.get(volumeSeries);
    if (!d) return;
    
    const date = new Date(p.time * 1000);
    const timeStr = date.getUTCFullYear() + '-' +
                    String(date.getUTCMonth()+1).padStart(2,'0') + '-' +
                    String(date.getUTCDate()).padStart(2,'0') + ' ' +
                    String(date.getUTCHours()).padStart(2,'0') + ':' +
                    String(date.getUTCMinutes()).padStart(2,'0') + ' UTC';
                    
    const volStr = v ? (v.value >= 1000 ? (v.value/1000).toFixed(2)+'K' : v.value.toFixed(2)) : '—';
    const fmt = val => val.toLocaleString('en-US', {{minimumFractionDigits:2, maximumFractionDigits:2}});
    
    document.getElementById('c-t').textContent = timeStr;
    document.getElementById('c-o').textContent = fmt(d.open);
    document.getElementById('c-h').textContent = fmt(d.high);
    document.getElementById('c-l').textContent = fmt(d.low);
    document.getElementById('c-c').textContent = fmt(d.close);
    document.getElementById('c-v').textContent = volStr;
}});

// Responsive
const ro = new ResizeObserver(e => {{
    chart.applyOptions({{ width: e[0].contentRect.width }});
}});
ro.observe(chartEl);

// ── Rolling stability chart (Canvas) ─────────────────────
function drawRollingChart() {{
    const canvas = document.getElementById('rolling-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth * window.devicePixelRatio;
    canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    const W = canvas.offsetWidth, H = canvas.offsetHeight;
    
    ctx.clearRect(0,0,W,H);
    
    const covs  = ROLL.cov;
    const winks = ROLL.wink;
    if (!covs || covs.length < 2) return;
    
    const pad = {{ l:40, r:50, t:8, b:20 }};
    const w = W - pad.l - pad.r;
    const h = H - pad.t - pad.b;
    
    // Dynamic scaling so it's not pinched (tight bounds with 10% margin)
    const minC = Math.min(...covs);
    const maxC = Math.max(...covs);
    const cDiff = Math.max(maxC - minC, 0.5); // minimum 0.5% spread
    const covMin = minC - cDiff * 0.1;
    const covMax = maxC + cDiff * 0.1;
    
    // Winkler dynamic scaling
    const wRawMin = Math.min(...winks);
    const wRawMax = Math.max(...winks);
    const wDiff = Math.max(wRawMax - wRawMin, 50); // minimum $50 spread
    const wMin = wRawMin - wDiff * 0.1;
    const wMax = wRawMax + wDiff * 0.1;
    
    const cx = (i) => pad.l + (i/(covs.length-1))*w;
    const cy_cov = (v) => pad.t + h - ((v-covMin)/(covMax-covMin))*h;
    const cy_w   = (v) => pad.t + h - ((v-wMin)/(wMax-wMin))*h;
    
    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.lineWidth = 1;
    [90,95,100].forEach(v => {{
        const y = cy_cov(v);
        ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y);
        ctx.stroke();
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        ctx.font = '9px monospace';
        ctx.textAlign = 'right';
        ctx.fillText(v+'%', pad.l-4, y+3);
    }});
    
    // 95% target line
    ctx.strokeStyle = 'rgba(99,102,241,0.35)';
    ctx.setLineDash([4,4]);
    ctx.lineWidth = 1;
    const y95 = cy_cov(95);
    ctx.beginPath(); ctx.moveTo(pad.l,y95); ctx.lineTo(W-pad.r,y95);
    ctx.stroke();
    ctx.setLineDash([]);
    
    // Winkler line (amber)
    ctx.strokeStyle = 'rgba(245,158,11,0.6)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    winks.forEach((v,i) => {{
        i===0 ? ctx.moveTo(cx(i),cy_w(v)) : ctx.lineTo(cx(i),cy_w(v));
    }});
    ctx.stroke();
    
    // Coverage area fill
    ctx.fillStyle = 'rgba(16,185,129,0.06)';
    ctx.beginPath();
    covs.forEach((v,i) => {{
        i===0 ? ctx.moveTo(cx(i),cy_cov(v)) : ctx.lineTo(cx(i),cy_cov(v));
    }});
    ctx.lineTo(cx(covs.length-1), pad.t+h);
    ctx.lineTo(pad.l, pad.t+h);
    ctx.closePath();
    ctx.fill();
    
    // Coverage line (green)
    ctx.strokeStyle = '#10b981';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    covs.forEach((v,i) => {{
        i===0 ? ctx.moveTo(cx(i),cy_cov(v)) : ctx.lineTo(cx(i),cy_cov(v));
    }});
    ctx.stroke();
    
    // Right axis labels for Winkler
    ctx.fillStyle = 'rgba(245,158,11,0.5)';
    ctx.textAlign = 'left';
    [wMin, (wMin+wMax)/2, wMax].forEach(v => {{
        ctx.fillText('$'+Math.round(v), W-pad.r+4, cy_w(v)+3);
    }});
    
    // Legend
    ctx.fillStyle = '#10b981';
    ctx.fillRect(pad.l, 4, 14, 2);
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.textAlign = 'left';
    ctx.fillText('Coverage', pad.l+18, 10);
    
    ctx.fillStyle = 'rgba(245,158,11,0.7)';
    ctx.fillRect(pad.l+90, 4, 14, 2);
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.fillText('Winkler $', pad.l+108, 10);
    
    // Add hover tooltip listeners once
    if (!canvas.dataset.hoverAttached) {{
        canvas.dataset.hoverAttached = "true";
        const tooltip = document.getElementById('rolling-tooltip');
        const ttCov = document.getElementById('tt-cov');
        const ttWink = document.getElementById('tt-wink');
        
        canvas.addEventListener('mousemove', (e) => {{
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const curCovs = ROLL.cov;
            const curWinks = ROLL.wink;
            if(!curCovs || curCovs.length === 0) return;
            
            const wCanvas = canvas.offsetWidth - pad.l - pad.r;
            
            let idx = Math.round(((x - pad.l) / wCanvas) * (curCovs.length - 1));
            idx = Math.max(0, Math.min(curCovs.length - 1, idx));
            
            ttCov.innerHTML = 'Coverage: ' + curCovs[idx].toFixed(2) + '%';
            ttWink.innerHTML = 'Winkler: $' + curWinks[idx].toLocaleString('en-US', {{maximumFractionDigits:0}});
            
            tooltip.style.display = 'block';
            
            // Keep tooltip inside canvas
            let tLeft = x + 15;
            let tTop = y + 15;
            if (tLeft + 150 > canvas.offsetWidth) tLeft = x - 160;
            
            tooltip.style.left = tLeft + 'px';
            tooltip.style.top = tTop + 'px';
        }});
        
        canvas.addEventListener('mouseleave', () => {{
            tooltip.style.display = 'none';
        }});
    }}
}}

// ── Countdown ────────────────────────────────────────────
function updateCountdown() {{
    const now = new Date();
    const secsLeft = 3600 - (now.getMinutes()*60 + now.getSeconds());
    const m = String(Math.floor(secsLeft/60)).padStart(2,'0');
    const s = String(secsLeft%60).padStart(2,'0');
    const el = document.getElementById('kpi-countdown');
    if (el) el.textContent = m+':'+s;
    const pct = ((3600-secsLeft)/3600*100).toFixed(1);
    const bar = document.getElementById('kpi-time-bar');
    if (bar) bar.style.width = pct+'%';
}}
setInterval(updateCountdown, 1000);
updateCountdown();

// ── Vol bars helper ───────────────────────────────────────
function renderVolBars(vols) {{
    const container = document.getElementById('vol-bars');
    if (!container) return;
    const labels = [['6H','#ef4444'],['24H','#f59e0b'],['7D','#10b981']];
    container.innerHTML = vols.map((v,i) => {{
        const pct = Math.min(v/0.003*100,100).toFixed(0);
        const [label,color] = labels[i];
        return `<div style="display:flex;align-items:center;
                            gap:8px;margin-bottom:5px;">
            <div style="font-size:9px;color:rgba(255,255,255,0.3);
                        width:28px;font-family:monospace;">${{label}}</div>
            <div style="flex:1;height:3px;background:rgba(255,255,255,0.06);
                        border-radius:2px;overflow:hidden;">
                <div style="height:100%;width:${{pct}}%;
                            background:${{color}};border-radius:2px;"></div>
            </div>
            <div style="font-size:9px;color:${{color}};
                        font-family:monospace;width:55px;text-align:right;">
                ${{(v*100).toFixed(4)}}%
            </div>
        </div>`;
    }}).join('');
}}

// ── Main data fetch + DOM update ──────────────────────────
let forecastLower = null;
let forecastUpper = null;
let chartInitialized = false;

async function fetchAndUpdate() {{
    try {{
        // Fetch bars + ticker in parallel
        const [barsRes, tickerRes, forecastRes] = await Promise.all([
            fetch(BINANCE+'/klines?symbol=BTCUSDT&interval=1h&limit=72'),
            fetch(BINANCE+'/ticker/24hr?symbol=BTCUSDT'),
            fetch(BINANCE+'/klines?symbol=BTCUSDT&interval=1h&limit=500')
        ]);
        
        const bars   = await barsRes.json();
        const ticker = await tickerRes.json();
        const bars500 = await forecastRes.json();
        
        // ── Price update ──────────────────────────────────
        const price  = parseFloat(ticker.lastPrice);
        const change = parseFloat(ticker.priceChangePercent);
        const arrow  = change >= 0 ? '▲' : '▼';
        const col    = change >= 0 ? '#10b981' : '#ef4444';
        const priceStr = '$' + price.toLocaleString('en-US',
            {{minimumFractionDigits:2,maximumFractionDigits:2}});
        
        // Update all price displays
        ['hdr-price','kpi-price'].forEach(id => {{
            const el = document.getElementById(id);
            if(el) el.textContent = priceStr;
        }});
        const chg = document.getElementById('hdr-change');
        if(chg) {{
            chg.textContent = arrow+' '+Math.abs(change).toFixed(2)+'% 24h';
            chg.style.color = col;
        }}
        const now = new Date();
        const timeEl = document.getElementById('hdr-time');
        if(timeEl) timeEl.textContent = 
            now.toUTCString().slice(5,25)+' UTC';
        
        // ── Candlestick chart update ──────────────────────
        const candles = bars.map(b => ({{
            time:  Math.floor(parseInt(b[0])/1000),
            open:  parseFloat(b[1]),
            high:  parseFloat(b[2]),
            low:   parseFloat(b[3]),
            close: parseFloat(b[4]),
        }}));
        const volumes = bars.map(b => {{
            const o=parseFloat(b[1]), c=parseFloat(b[4]);
            return {{
                time:  Math.floor(parseInt(b[0])/1000),
                value: parseFloat(b[5]),
                color: c>=o ? 'rgba(16,185,129,0.3)' 
                             : 'rgba(239,68,68,0.3)',
            }};
        }});
        
        candleSeries.setData(candles);
        volumeSeries.setData(volumes);
        
        // Update OHLC bar with last candle
        const last = candles[candles.length-1];
        const lastVol = volumes[volumes.length-1];
        const fmtOHLC = val => val.toLocaleString('en-US', {{minimumFractionDigits:2, maximumFractionDigits:2}});
        ['o','h','l','c'].forEach((k,i) => {{
            const val = [last.open,last.high,last.low,last.close][i];
            const el = document.getElementById('c-'+k);
            if(el) el.textContent = fmtOHLC(val);
        }});
        
        const date = new Date(last.time * 1000);
        const timeStr = date.getUTCFullYear() + '-' +
                        String(date.getUTCMonth()+1).padStart(2,'0') + '-' +
                        String(date.getUTCDate()).padStart(2,'0') + ' ' +
                        String(date.getUTCHours()).padStart(2,'0') + ':' +
                        String(date.getUTCMinutes()).padStart(2,'0') + ' UTC';
        
        const vEl = document.getElementById('c-v');
        if (vEl && lastVol) {{
            vEl.textContent = lastVol.value >= 1000 ? (lastVol.value/1000).toFixed(2)+'K' : lastVol.value.toFixed(2);
        }}
        const tEl = document.getElementById('c-t');
        if (tEl) tEl.textContent = timeStr;
        
        if (!chartInitialized) {{
            chart.timeScale().scrollToRealTime();
            chartInitialized = true;
        }}
        
        // ── Compute forecast via simple GBM in JS ────────
        // (Uses last 500 bars closes for vol estimation)
        const closes500 = bars500.map(b => parseFloat(b[4]));
        closes500[closes500.length-1] = price; // inject live price
        
        const logRets = [];
        for(let i=1; i<closes500.length; i++) {{
            logRets.push(Math.log(closes500[i]/closes500[i-1]));
        }}
        
        // Adaptive volatility: blend 6H, 24H, 168H windows
        function ewmVol(rets, span) {{
            if(rets.length===0) return 0.001;
            const weights = rets.map((_,i) => 
                Math.exp(-i/span)).reverse();
            const wSum = weights.reduce((a,b)=>a+b,0);
            const wRets = rets.map((r,i)=>r*weights[i]);
            const mean = wRets.reduce((a,b)=>a+b,0)/wSum;
            const variance = rets.map((r,i)=>
                weights[i]*Math.pow(r-mean,2)
            ).reduce((a,b)=>a+b,0)/wSum;
            return Math.sqrt(variance);
        }}
        
        const recent = logRets.slice(-168);
        const v6  = ewmVol(recent.slice(-6),   6);
        const v24 = ewmVol(recent.slice(-24),  24);
        const v168= ewmVol(recent,            168);
        const vol = Math.max(
            0.5*v6 + 0.3*v24 + 0.2*v168,
            v168 * 0.5  // floor
        );
        
        // Student-t approximation: use df=2.5 (BTC typical)
        // 99% CI = 0.5th to 99.5th percentile
        // t-multiplier for df=2.5, p=0.005: ~7.16
        // (precomputed: scipy.stats.t.ppf(0.995, 2.5) ≈ 7.16)
        const df = 2.5;
        const tMult = 7.16; // 99% CI multiplier for df=2.5
        
        const lower = price * Math.exp(-tMult * vol);
        const upper = price * Math.exp( tMult * vol);
        forecastLower = lower;
        forecastUpper = upper;
        
        // Update forecast lines on chart
        const lastTime = last.time;
        const nextTime = lastTime + 3600;
        upperLine.setData([
            {{time:lastTime, value:upper}},
            {{time:nextTime, value:upper}},
        ]);
        lowerLine.setData([
            {{time:lastTime, value:lower}},
            {{time:nextTime, value:lower}},
        ]);
        
        // ── KPI cards update ──────────────────────────────
        const fmt = v => '$'+v.toLocaleString('en-US',
            {{minimumFractionDigits:2,maximumFractionDigits:2}});
        const fmtK = v => '$'+Math.round(v).toLocaleString('en-US');
        
        const setEl = (id, val) => {{
            const el = document.getElementById(id);
            if(el) el.textContent = val;
        }};
        
        setEl('kpi-lower', fmt(lower));
        setEl('kpi-upper', fmt(upper));
        
        const width = upper - lower;
        const mid   = (upper + lower) / 2;
        setEl('kpi-width', fmtK(width));
        setEl('kpi-mid', 'Mid '+fmtK(mid));
        
        // Confidence: how narrow relative to recent vol
        const conf = Math.max(0, Math.min(100,
            Math.round((1 - vol/0.005) * 100)
        ));
        setEl('kpi-conf', conf+'/100 conf');
        const confBar = document.getElementById('kpi-conf-bar');
        if(confBar) {{
            confBar.style.width = conf+'%';
            confBar.style.background = 
                conf>70 ? '#10b981' : conf>40 ? '#f59e0b' : '#ef4444';
        }}
        
        // ── Price position indicator ───────────────────────
        const pos = Math.max(0,Math.min(1,(price-lower)/width));
        const posPct = (pos*100).toFixed(1);
        const fill = document.getElementById('range-fill');
        const needle = document.getElementById('range-needle');
        if(fill) fill.style.width = posPct+'%';
        if(needle) needle.style.left = 'calc('+posPct+'% - 2px)';
        setEl('range-lo-label', fmtK(lower));
        setEl('range-hi-label', fmtK(upper));
        setEl('range-sub', 
            'Price at '+posPct+'% of range · Width '+fmtK(width));
        
        // ── Model internals ───────────────────────────────
        // Approximate Student-t fit
        const recentVol = vol;
        const scale = recentVol;
        setEl('m-df',    df.toFixed(2));
        setEl('m-scale', scale.toFixed(6));
        renderVolBars([v6, v24, v168]);
        
    }} catch(e) {{
        console.warn('Update error:', e);
    }}
}}

// ── Ticker update (from Python-rendered history) ──────────
function buildTicker() {{
    const historyRows = {history_json};
    const items = historyRows
        .filter(r => r.result === 'HIT' || r.result === 'MISS')
        .slice(0, 15)
        .map(r => {{
            const col = r.result==='HIT' ? '#10b981' : '#ef4444';
            const icon = r.result==='HIT' ? '&#10003;' : '&#10007;';
            return `<span style="color:${{col}};margin:0 20px;">
                ${{icon}} ${{r.candle.slice(11,16)}}&#8594;${{r.actual}} (${{r.result.toLowerCase()}})
            </span>`;
        }}).join('<span style="color:rgba(255,255,255,0.15);">&nbsp;·&nbsp;</span>');
    
    const ticker = document.getElementById('ticker-inner');
    if(ticker && items) {{
        ticker.innerHTML = items + items + items;
    }}
}}

// ── Init ─────────────────────────────────────────────────
drawRollingChart();
buildTicker();
fetchAndUpdate();

// Update every 10 seconds — ONLY DOM nodes change, no page reload
setInterval(fetchAndUpdate, 2000);

// Redraw canvas chart on resize
window.addEventListener('resize', drawRollingChart);
</script>
</body>
</html>
"""

# Render everything as a single component
components.html(dashboard_html, height=1700, scrolling=True)
