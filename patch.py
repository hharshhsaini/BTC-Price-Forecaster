import re

with open("app.py", "r") as f:
    code = f.read()

# 1. CSS changes
code = code.replace(
    ".glass {\n    background: rgba(255,255,255,0.03);",
    ".glass {\n    min-height: 110px;\n    background: rgba(255,255,255,0.03);"
)

code = code.replace(
    ".value-xl {\n    font-size: 2.2rem; font-weight: 700; color: #ffffff;\n    letter-spacing: -0.02em; line-height: 1.1;\n}",
    ".value-xl {\n    font-size: 2rem !important;\n    font-weight: 700 !important;\n    color: #ffffff !important;\n    font-family: 'SF Mono', monospace !important;\n    line-height: 1.2 !important;\n}"
)

# 2. Add compute_live_coverage
code = code.replace(
    "def compute_adaptive_volatility",
    "def compute_live_coverage(history):\n    resolved = [r for r in history if r.get('in_range') is not None]\n    if not resolved: return None\n    hits = sum(1 for r in resolved if r.get('in_range'))\n    return hits / len(resolved)\n\n\ndef compute_adaptive_volatility"
)

# 3. Replace render_header
old_header = code[code.find("def render_header(live_price, change_pct, generated_at):"):code.find("def render_kpi_cards(live_price")]
new_header = """def render_header(live_price, change_pct, generated_at):
    st.markdown(clean_html(f'''
    <div style="
        padding: 20px 32px 16px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
    ">
        <!-- Logo + Title -->
        <div style="display:flex; align-items:center; gap:14px;">
            <div style="
                width:42px; height:42px; border-radius:12px;
                background: linear-gradient(135deg, #F7931A, #e8750a);
                display:flex; align-items:center; justify-content:center;
                font-size:22px; font-weight:900; color:white;
                box-shadow: 0 4px 20px rgba(247,147,26,0.35);
                flex-shrink:0;
            ">&#x20BF;</div>
            <div>
                <div style="font-size:22px; font-weight:700; color:#fff; 
                            letter-spacing:-0.02em; line-height:1.2;">
                    BTC Price Forecaster
                </div>
                <div style="font-size:11px; color:rgba(255,255,255,0.35); 
                            letter-spacing:0.06em;">
                    AlphaI &times; Polaris &nbsp;·&nbsp; GBM + Student-t 
                    &nbsp;·&nbsp; 95% Confidence Interval
                </div>
            </div>
        </div>

        <!-- Center: Live price -->
        <div style="text-align:center;">
            <div style="font-size:32px; font-weight:700; color:#F7931A; 
                        letter-spacing:-0.02em; font-family:monospace;">
                ${live_price:,.2f}
            </div>
            <div style="font-size:12px; font-weight:600;
                        color:{'#10b981' if change_pct >= 0 else '#ef4444'};">
                {'&#9650;' if change_pct >= 0 else '&#9660;'} 
                {abs(change_pct):.2f}% 24h
            </div>
        </div>

        <!-- Right: Status -->
        <div style="text-align:right;">
            <div style="display:inline-flex; align-items:center; gap:6px;
                        background:rgba(16,185,129,0.08);
                        border:1px solid rgba(16,185,129,0.2);
                        border-radius:100px; padding:5px 12px;
                        margin-bottom:6px;">
                <div style="width:7px; height:7px; border-radius:50%;
                            background:#10b981;
                            box-shadow:0 0 8px #10b981;"></div>
                <span style="font-size:11px; color:#10b981; 
                             font-weight:600; letter-spacing:0.05em;">
                    LIVE · 10s
                </span>
            </div>
            <div style="font-size:10px; color:rgba(255,255,255,0.2); 
                        font-family:monospace; display:block;">
                {generated_at}
            </div>
        </div>
    </div>
    '''), unsafe_allow_html=True)


"""
code = code.replace(old_header, new_header)

# 4. Add render_coverage_gauge
gauge_func = """def render_coverage_gauge(coverage, live_coverage=None, live_n=0):
    pct = coverage  # e.g. 0.9356
    
    # Gauge math: semicircle 0–180 degrees
    # 0.0 = leftmost, 1.0 = rightmost
    # Clamp to 0.5–1.0 visible range for BTC context
    angle_min, angle_max = 0.80, 1.0
    needle_pct = (pct - angle_min) / (angle_max - angle_min)
    needle_pct = max(0, min(1, needle_pct))
    needle_deg = 180 * needle_pct  # 0 = left, 180 = right
    
    import math
    rad = math.radians(needle_deg)
    # Needle endpoint (center=100,90, radius=65)
    nx = 100 - 65 * math.cos(rad)
    ny = 90 - 65 * math.sin(rad)
    
    # Color based on proximity to 0.95
    diff = abs(pct - 0.95)
    color = "#10b981" if diff < 0.02 else "#f59e0b" if diff < 0.04 else "#ef4444"
    
    live_html = ""
    if live_coverage is not None:
        live_color = "#10b981" if live_coverage >= 0.93 else "#f59e0b"
        live_html = f'''
        <div style="font-size:11px; color:{live_color}; 
                    font-family:monospace; margin-top:2px;">
            Live: {live_coverage*100:.1f}% ({live_n} resolved)
        </div>'''
    
    return f'''
    <div class="glass" style="padding:20px; text-align:center;">
        <div class="label" style="margin-bottom:12px;">Coverage Gauge</div>
        <svg viewBox="0 0 200 110" style="width:100%; max-width:200px;">
            <!-- Background arc (full semicircle) -->
            <path d="M 25 90 A 75 75 0 0 1 175 90" 
                  fill="none" stroke="rgba(255,255,255,0.06)" 
                  stroke-width="12" stroke-linecap="round"/>
            
            <!-- Red zone: 80–90% -->
            <path d="M 25 90 A 75 75 0 0 1 100 15" 
                  fill="none" stroke="rgba(239,68,68,0.25)" 
                  stroke-width="12" stroke-linecap="round"/>
            
            <!-- Amber zone: 90–93% -->
            <path d="M 100 15 A 75 75 0 0 1 143 28" 
                  fill="none" stroke="rgba(245,158,11,0.25)" 
                  stroke-width="12" stroke-linecap="round"/>
            
            <!-- Green zone: 93–97% -->
            <path d="M 143 28 A 75 75 0 0 1 163 55" 
                  fill="none" stroke="rgba(16,185,129,0.35)" 
                  stroke-width="12" stroke-linecap="round"/>
            
            <!-- Blue zone: 97–100% -->
            <path d="M 163 55 A 75 75 0 0 1 175 90" 
                  fill="none" stroke="rgba(99,102,241,0.25)" 
                  stroke-width="12" stroke-linecap="round"/>
            
            <!-- Target marker at 95% -->
            <line x1="153" y1="40" x2="145" y2="50" 
                  stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/>
            <text x="158" y="38" fill="rgba(255,255,255,0.3)" 
                  font-size="7" text-anchor="middle">95%</text>
            
            <!-- Needle -->
            <line x1="100" y1="90" x2="{nx:.1f}" y2="{ny:.1f}" 
                  stroke="{color}" stroke-width="2.5" 
                  stroke-linecap="round"/>
            <circle cx="100" cy="90" r="5" fill="{color}" 
                    opacity="0.9"/>
            <circle cx="100" cy="90" r="3" fill="#050508"/>
            
            <!-- Value text -->
            <text x="100" y="75" text-anchor="middle" 
                  fill="{color}" font-size="18" font-weight="700"
                  font-family="monospace">
                {pct*100:.1f}%
            </text>
        </svg>
        
        <div style="font-size:11px; color:rgba(255,255,255,0.35); 
                    font-family:monospace; margin-top:4px;">
            Backtest: {pct*100:.2f}% (n=714)
        </div>
        {live_html}
    </div>
    '''

"""
code = code.replace("def render_rolling_chart", gauge_func + "def render_rolling_chart")

# 5. Remove Backtest summary from render_insights
old_bt_summary = """        <!-- Backtest summary -->
        <div class="glass">
            <div class="label" style="margin-bottom:12px;">Backtest \\u00b7 30D \\u00b7 720 Bars</div>
            
            <div style="margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; 
                            align-items:baseline; margin-bottom:4px;">
                    <span style="font-size:11px; color:rgba(255,255,255,0.4);">
                        Coverage
                    </span>
                    <span style="font-size:15px; font-weight:700; 
                                 color:{'#10b981' if abs(coverage-0.95)<0.02 else '#f59e0b'}; 
                                 font-family:'JetBrains Mono', monospace;">
                        {coverage:.2f}%
                        <span style="font-size:10px; opacity:0.6;">
                            ({cov_sign}{cov_vs_target:.2f}% vs 95%)
                        </span>
                    </span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" style="
                        width:{coverage:.1f}%;
                        background:{'#10b981' if abs(coverage-0.95)<0.02 else '#f59e0b'};
                    "></div>
                </div>
            </div>
            
            <div style="display:grid; grid-template-columns:1fr 1fr; 
                        gap:8px; margin-top:8px;">
                <div>
                    <div style="font-size:9px; color:rgba(255,255,255,0.3);">
                        AVG WIDTH
                    </div>
                    <div style="font-size:14px; font-weight:600; 
                                color:rgba(255,255,255,0.8); font-family:'JetBrains Mono', monospace;">
                        ${mean_width:,.0f}
                    </div>
                </div>
                <div>
                    <div style="font-size:9px; color:rgba(255,255,255,0.3);">
                        WINKLER
                    </div>
                    <div style="font-size:14px; font-weight:600; 
                                color:rgba(255,255,255,0.8); font-family:'JetBrains Mono', monospace;">
                        {winkler:,.0f}
                    </div>
                </div>
            </div>
        </div>"""
code = code.replace(old_bt_summary, "")

# 6. Render 3 columns in main
main_add = """    with col_insights:
        render_insights(lower, upper, live_price, coverage, winkler, 
                         mean_width, df_t, scale_t, vol_s, vol_m, vol_l)

    # Render it inside a column:
    col_gauge, col_width, col_winkler = st.columns(3)
    with col_gauge:
        live_cov = compute_live_coverage(history)
        live_n = len([r for r in history if r.get("in_range") is not None])
        st.markdown(
            clean_html(render_coverage_gauge(coverage, live_cov, live_n)),
            unsafe_allow_html=True
        )
    with col_width:
        st.markdown(clean_html(f'''
        <div class="glass" style="text-align:center; padding:28px 20px;">
            <div class="label" style="margin-bottom:12px;">Mean Width</div>
            <div style="font-size:2rem; font-weight:700; color:#fff; 
                        letter-spacing:-0.02em; font-family:monospace;">
                ${mean_width:,.0f}
            </div>
            <div class="divider"></div>
            <div style="font-size:11px; color:rgba(255,255,255,0.35);">
                Avg forecast range · lower = better
            </div>
        </div>
        '''), unsafe_allow_html=True)
    with col_winkler:
        st.markdown(clean_html(f'''
        <div class="glass" style="text-align:center; padding:28px 20px;">
            <div class="label" style="margin-bottom:12px;">Mean Winkler Score</div>
            <div style="font-size:2rem; font-weight:700; color:#fff; 
                        letter-spacing:-0.02em; font-family:monospace;">
                {winkler:,.0f}
            </div>
            <div class="divider"></div>
            <div style="font-size:11px; color:rgba(255,255,255,0.35);">
                Efficiency metric · lower = better
            </div>
        </div>
        '''), unsafe_allow_html=True)"""
code = code.replace("""    with col_insights:
        render_insights(lower, upper, live_price, coverage, winkler, 
                         mean_width, df_t, scale_t, vol_s, vol_m, vol_l)""", main_add)

# 7. Rolling chart update
roll_yaxes = """    fig.update_yaxes(
        range=[0.82, 1.02],          # zoom into 82%–102%
        tickformat='.0%',
        secondary_y=False
    )
    fig.update_yaxes(
        range=[800, 3500],            # Winkler range
        tickprefix='$',
        secondary_y=True
    )"""
code = code.replace(
"""        yaxis2=dict(showgrid=False,
                    color='rgba(245,158,11,0.4)',
                    tickfont=dict(size=9),
                    tickprefix='$')
    )""", 
"""        yaxis2=dict(showgrid=False,
                    color='rgba(245,158,11,0.4)',
                    tickfont=dict(size=9),
                    tickprefix='$')
    )
""" + roll_yaxes)

# 8. Not visited fix
not_visited_fix = """        if r.get("Lower ($)") == "not visited":
            rows_html += f'''
            <tr style="opacity:0.4;">
                <td style="color:rgba(255,255,255,0.4);">
                    {r.get('Candle Open (UTC)', '\\u2014')}
                </td>
                <td colspan="4" style="color:rgba(255,255,255,0.25); 
                                        font-style:italic; letter-spacing:0.05em; text-align:center;">
                    not visited
                </td>
                <td style="color:rgba(255,255,255,0.2);">\\u2014</td>
            </tr>'''
            continue
            
        in_range = r.get("In Range", "\\u2014")"""
code = code.replace('        in_range = r.get("In Range", "\\u2014")', not_visited_fix)


with open("app.py", "w") as f:
    f.write(code)
