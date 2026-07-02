"""
app/pages/market_intelligence.py
================================
Market Intelligence — the sales-team dashboard.

Organized by decision-value, not by feature inventory:

  Tier 1 (always visible, top of page) — the views a sales leader looks at first:
    - 6 hero KPIs (incl. new companies, B2B, high-connectivity)
    - Opportunity matrix heatmap (size × connectivity), the "where to deploy" view
    - New-companies pipeline (monthly registrations, last 24 months)
    - Governorate scorecard

  Tier 2 (still on first scroll, supporting):
    - Sector composition + digital demand by sector
    - Company size + maturity breakdowns
    - Top cities

  Tier 3 (behind "Show more analysis" expander):
    - Business model distribution (B2B / B2C / mixed / unknown)
    - International signal
    - Dynamism distribution
    - Fleet size
    - Full opportunity matrix table
    - Sector scorecard table

Reads the analytical CSVs produced by analysis/main.py. Falls back to live
feature computation from the segmented CSV if analysis has not been run yet.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.theme import (
    inject_global_css, section_divider,
    WHITE, RED, RED_SOFT, MUTED, OFF_WHITE, SUCCESS,
    NAVY, NAVY_LIGHT, NAVY_LIGHTER, NAVY_HAIRLINE, CATEGORY_COLORS,
)
from app.components.branding import (
    show_fixed_logo, page_title, sidebar_context, eyebrow,
)
from segmentation.config import OUTPUT_CSV
from analysis.config import SECTOR_KPIS_CSV


# Derived analytical CSV paths
FEATURES_CSV     = OUTPUT_CSV.parent / "company_features.csv"
GEOGRAPHY_CSV    = OUTPUT_CSV.parent / "geography_summary.csv"
GOVERNORATE_CSV  = OUTPUT_CSV.parent / "governorate_breakdown.csv"
OPPORTUNITY_CSV  = OUTPUT_CSV.parent / "opportunity_matrix.csv"
TIMING_CSV       = OUTPUT_CSV.parent / "timing_summary.csv"


inject_global_css()
sidebar_context()


# ── Label mappings ────────────────────────────────────────────────────────────
CATEGORY_LABELS = {
    "retail": "Retail", "manufacturing": "Manufacturing", "transport": "Transport",
    "tourism": "Tourism", "healthcare": "Healthcare", "education": "Education",
    "financial_services": "Financial services", "others": "Others",
}
CAPITAL_TIER_ORDER  = ["micro", "small", "medium", "large", "unknown"]
CAPITAL_TIER_LABELS = {
    "micro": "Micro (<5k)", "small": "Small (5–20k)", "medium": "Medium (20–100k)",
    "large": "Large (>100k)", "unknown": "Unknown",
}
MATURITY_ORDER  = ["startup", "growing", "established", "mature", "unknown"]
MATURITY_LABELS = {
    "startup": "Startup (<1y)", "growing": "Growing (1–3y)",
    "established": "Established (3–10y)", "mature": "Mature (>10y)", "unknown": "Unknown",
}
COMPANY_SIZE_ORDER = ["Solo", "Small", "Mid", "Large", "Unknown"]
CONNECTIVITY_ORDER = ["high", "medium", "low"]
CONNECTIVITY_LABELS = {"high": "High need", "medium": "Medium need", "low": "Low need"}
BUSINESS_MODEL_LABELS = {"B2B": "B2B", "B2C": "B2C", "mixed": "Mixed", "unknown": "Unspecified"}
DYNAMISM_ORDER = ["high", "medium", "low", "unknown"]
DYNAMISM_LABELS = {"high": "Growing fast", "medium": "Stable", "low": "Slow", "unknown": "Unknown"}
FLEET_ORDER = ["large", "medium", "small", "none"]
FLEET_LABELS = {"large": "Large fleet", "medium": "Medium fleet", "small": "Small fleet", "none": "No fleet"}


# Plotly base layout — calm, transparent, blends with navy
BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=OFF_WHITE, family="sans-serif", size=13),
    margin=dict(t=10, b=10, l=10, r=10),
    hoverlabel=dict(bgcolor=NAVY_LIGHT, bordercolor=NAVY_LIGHTER, font_size=13),
)


# ──────────────────────────────────────────────────────────────────────────────
# Data loaders
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=20)
def load_features():
    """Prefer company_features.csv; else compute features from segmented CSV."""
    feats = Path(FEATURES_CSV)
    if feats.exists():
        return pd.read_csv(feats, encoding="utf-8-sig"), "features"
    seg = Path(OUTPUT_CSV)
    if seg.exists():
        from analysis.feature_engineering import build_all_features
        df = pd.read_csv(seg, encoding="utf-8-sig")
        return build_all_features(df), "computed"
    return None, "none"


@st.cache_data(ttl=20)
def load_csv(path_str: str):
    p = Path(path_str)
    return pd.read_csv(p, encoding="utf-8-sig") if p.exists() else None


# ──────────────────────────────────────────────────────────────────────────────
# Reusable chart builders
# ──────────────────────────────────────────────────────────────────────────────

def kpi_card(label: str, value: str, sub: str, accent: str = RED) -> str:
    return f"""
    <div class="on-card on-reveal" style="padding:1.05rem 1.15rem; height:120px;
         border-left:3px solid {accent};">
        <div style="color:{MUTED}; font-size:0.74rem; text-transform:uppercase;
             letter-spacing:0.07em;">{label}</div>
        <div style="color:{WHITE}; font-size:1.9rem; font-weight:800; line-height:1.2;
             margin-top:0.25rem;">{value}</div>
        <div style="color:{OFF_WHITE}; font-size:0.82rem; margin-top:0.15rem;">{sub}</div>
    </div>
    """


def vertical_bar(df: pd.DataFrame, x_col: str, y_col: str, color: str, height: int = 320):
    """Generic vertical bar chart with the dashboard's standard styling."""
    fig = go.Figure(go.Bar(
        x=df[x_col], y=df[y_col], marker=dict(color=color),
        text=df[y_col], textposition="outside", textfont=dict(color=OFF_WHITE),
        hovertemplate="%{x}<br>%{y} companies<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_layout(**BASE_LAYOUT, height=height, showlegend=False)
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)", title="", tickfont=dict(color=OFF_WHITE))
    fig.update_yaxes(gridcolor=NAVY_HAIRLINE, title="", zeroline=False, tickfont=dict(color=MUTED))
    return fig


def horizontal_bar(labels, values, color: str, height: int = 320, text_format=None):
    """Generic horizontal bar chart."""
    text = [text_format(v) if text_format else v for v in values] if text_format else values
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=color),
        text=text, textposition="outside", textfont=dict(color=OFF_WHITE),
        cliponaxis=False,
    ))
    fig.update_layout(**BASE_LAYOUT, height=height, showlegend=False)
    fig.update_xaxes(gridcolor=NAVY_HAIRLINE, title="", zeroline=False, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)", title="", tickfont=dict(color=OFF_WHITE))
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Page header
# ──────────────────────────────────────────────────────────────────────────────

page_title("Market Intelligence", "Where the opportunity is, and who to focus on.")

df, source = load_features()

if df is None:
    st.markdown(
        f"""
        <div class="on-card on-reveal" style="text-align:center; margin-top:1.4rem;">
            <p style="color:{OFF_WHITE}; font-size:1.05rem; margin:0;">
                No data yet. Open <b>Import data</b> in the sidebar to bring in your first companies.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_fixed_logo()
    st.stop()

if source == "computed":
    st.markdown(
        f"<p style='color:{MUTED}; font-size:0.86rem;'>Live view — computed from the latest classified data.</p>",
        unsafe_allow_html=True,
    )


# ── Optional sector filter that drives the whole dashboard ────────────────────
all_sectors = sorted([c for c in df["category"].dropna().unique().tolist() if str(c).strip()]) if "category" in df.columns else []
fcol1, fcol2 = st.columns([3, 1])
with fcol2:
    sector_filter = st.selectbox(
        "Focus sector",
        ["All sectors"] + [CATEGORY_LABELS.get(s, s) for s in all_sectors],
    )
label_to_key = {CATEGORY_LABELS.get(s, s): s for s in all_sectors}
active_key = label_to_key.get(sector_filter) if sector_filter != "All sectors" else None

view = df if active_key is None else df[df["category"] == active_key]


# ──────────────────────────────────────────────────────────────────────────────
# TIER 1 — Hero KPIs (6 cards)
# ──────────────────────────────────────────────────────────────────────────────

total = len(view)

def col_sum(col_name):
    return int(view[col_name].sum()) if col_name in view.columns else 0

def col_count_where(col_name, value):
    return int((view[col_name] == value).sum()) if col_name in view.columns else 0


callable_n        = col_sum("callable_prospect")
callable_pct      = (100 * callable_n / total) if total else 0
new_companies     = col_sum("is_new_company")
new_pct           = (100 * new_companies / total) if total else 0
b2b_n             = col_count_where("business_model", "B2B")
b2b_pct           = (100 * b2b_n / total) if total else 0
high_conn         = col_count_where("connectivity_need", "high")
high_conn_pct     = (100 * high_conn / total) if total else 0
multisite         = col_sum("multisite_signal")

# Two rows of 3 KPI cards. Top row = the most actionable; bottom = supporting.
k1, k2, k3 = st.columns(3)
with k1: st.markdown(kpi_card("Companies", f"{total:,}", "in this view", RED), unsafe_allow_html=True)
with k2: st.markdown(kpi_card("New (last 12 months)", f"{new_companies:,}", f"{new_pct:.0f}% — no current provider", SUCCESS), unsafe_allow_html=True)
with k3: st.markdown(kpi_card("High connectivity need", f"{high_conn:,}", f"{high_conn_pct:.0f}% — fibre / cloud fit", "#5B8FE0"), unsafe_allow_html=True)

st.markdown("<div style='height:0.8vh;'></div>", unsafe_allow_html=True)

k4, k5, k6 = st.columns(3)
with k4: st.markdown(kpi_card("B2B prospects", f"{b2b_n:,}", f"{b2b_pct:.0f}% — VPN / pro lines", "#E0A24C"), unsafe_allow_html=True)
with k5: st.markdown(kpi_card("Reachable", f"{callable_n:,}", f"{callable_pct:.0f}% callable", "#37C2A0"), unsafe_allow_html=True)
with k6: st.markdown(kpi_card("Multi-site", f"{multisite:,}", "likely bigger contracts", "#E07CB0"), unsafe_allow_html=True)

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 1 — Opportunity matrix heatmap (the flagship visualization)
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("The opportunity map")
st.markdown(
    f"<h4 style='color:{WHITE}; margin-bottom:0.2rem;'>Where to deploy the team</h4>"
    f"<p style='color:{MUTED}; font-size:0.92rem; margin-top:0;'>"
    f"Company size × connectivity need. Each cell shows how many companies fit that profile — "
    f"the darker the cell, the bigger the opportunity to deploy that product family there.</p>",
    unsafe_allow_html=True,
)

if {"company_size", "connectivity_need"}.issubset(view.columns) and total:
    # Build matrix
    pivot = view.pivot_table(
        index="company_size", columns="connectivity_need",
        values="identifiant_unique", aggfunc="count", fill_value=0,
    )
    # Reorder rows & columns
    row_order = [r for r in COMPANY_SIZE_ORDER if r in pivot.index]
    col_order = [c for c in CONNECTIVITY_ORDER if c in pivot.columns]
    pivot = pivot.reindex(index=row_order, columns=col_order)

    z = pivot.values
    text = [[f"<b>{int(v):,}</b>" if v else "0" for v in row] for row in z]
    fig = go.Figure(go.Heatmap(
        z=z,
        x=[CONNECTIVITY_LABELS.get(c, c) for c in pivot.columns],
        y=pivot.index,
        text=text,
        texttemplate="%{text}",
        textfont=dict(color=WHITE, size=15),
        colorscale=[
            [0.0, "rgba(237,28,36,0.05)"],
            [0.4, "rgba(237,28,36,0.40)"],
            [0.8, "rgba(237,28,36,0.75)"],
            [1.0, "rgba(237,28,36,0.95)"],
        ],
        showscale=False,
        hovertemplate="<b>%{y}</b> × %{x}<br>%{z} companies<extra></extra>",
        xgap=4, ygap=4,
    ))
    fig.update_layout(**BASE_LAYOUT, height=340)
    fig.update_xaxes(side="top", tickfont=dict(color=OFF_WHITE, size=12))
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=OFF_WHITE, size=12))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Opportunity matrix needs `company_size` and `connectivity_need`. Run `python -m analysis.main`.")

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 1 — New-companies pipeline (monthly registrations)
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("The fresh pipeline")
st.markdown(
    f"<h4 style='color:{WHITE}; margin-bottom:0.2rem;'>New companies registered, by month</h4>"
    f"<p style='color:{MUTED}; font-size:0.92rem; margin-top:0;'>"
    f"Fresh registrations have no telecom provider yet — they're the easiest wins.</p>",
    unsafe_allow_html=True,
)

timing = load_csv(str(TIMING_CSV))
if timing is not None and len(timing) > 0:
    timing = timing.copy()
    timing["month"] = timing["month"].astype(str)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timing["month"], y=timing["registrations"],
        mode="lines+markers",
        line=dict(color=RED, width=2.5),
        marker=dict(size=7, color=RED, line=dict(color=NAVY, width=1.5)),
        fill="tozeroy", fillcolor="rgba(237,28,36,0.15)",
        hovertemplate="%{x}<br><b>%{y}</b> new companies<extra></extra>",
    ))
    fig.update_layout(**BASE_LAYOUT, height=300, showlegend=False)
    fig.update_xaxes(gridcolor=NAVY_HAIRLINE, title="", tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=NAVY_HAIRLINE, title="", zeroline=False, tickfont=dict(color=MUTED))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Timing summary not found. Run `python -m analysis.main` to build it.")

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 1 — Governorate scorecard (territory view)
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("Territory scorecard")
st.markdown(
    f"<h4 style='color:{WHITE}; margin-bottom:0.2rem;'>By governorate</h4>"
    f"<p style='color:{MUTED}; font-size:0.92rem; margin-top:0;'>"
    f"Where the team is winning and where opportunity hides. Higher % new = warmer territory.</p>",
    unsafe_allow_html=True,
)

gov = load_csv(str(GOVERNORATE_CSV))
if gov is not None and len(gov) > 0:
    show = gov.copy()
    show = show[show["governorate"].astype(str) != "Unknown"]   # hide Unknown row from the scorecard
    if len(show):
        show = show.rename(columns={
            "governorate": "Governorate", "companies": "Companies",
            "pct_new": "New %", "pct_digital_high": "Digital %",
            "pct_b2b": "B2B %", "pct_high_connectivity": "High connectivity %",
            "avg_capital": "Avg capital (TND)",
        })
        st.dataframe(
            show, use_container_width=True, height=min(360, 56 + 36 * len(show)),
            hide_index=True,
        )
    else:
        st.info("No governorate identified yet.")
else:
    st.info("Governorate breakdown not found. Run `python -m analysis.main`.")

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 2 — Sector composition + digital demand
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("Composition of the market")
r2c1, r2c2 = st.columns([1, 1], gap="large")

with r2c1:
    st.markdown(f"<h4 style='color:{WHITE};'>Companies by sector</h4>", unsafe_allow_html=True)
    if "category" in view.columns and total:
        counts = view["category"].value_counts().reset_index()
        counts.columns = ["category", "count"]
        counts["label"] = counts["category"].map(lambda c: CATEGORY_LABELS.get(c, c))
        colors = [CATEGORY_COLORS.get(c, "#7286A6") for c in counts["category"]]
        fig = go.Figure(go.Pie(
            labels=counts["label"], values=counts["count"], hole=0.62,
            marker=dict(colors=colors, line=dict(color=NAVY, width=2)),
            textinfo="percent", textfont=dict(color=WHITE, size=12),
            hovertemplate="%{label}<br>%{value} companies<br>%{percent}<extra></extra>",
        ))
        fig.update_layout(**BASE_LAYOUT, height=330, showlegend=True,
                          legend=dict(font=dict(color=OFF_WHITE, size=11), orientation="v", x=1.0, y=0.5))
        fig.add_annotation(text=f"<b>{total:,}</b><br>companies", showarrow=False,
                           font=dict(color=WHITE, size=16), x=0.5, y=0.5)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with r2c2:
    st.markdown(f"<h4 style='color:{WHITE};'>Digital demand by sector</h4>", unsafe_allow_html=True)
    if {"category", "digital_signal"}.issubset(view.columns) and total:
        g = view.groupby("category")["digital_signal"].apply(lambda s: 100 * (s == "high").mean()).reset_index()
        g.columns = ["category", "pct"]
        g["label"] = g["category"].map(lambda c: CATEGORY_LABELS.get(c, c))
        g = g.sort_values("pct")
        fig = horizontal_bar(g["label"], g["pct"], "#5B8FE0", height=330,
                              text_format=lambda v: f"{v:.0f}%")
        fig.update_xaxes(ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 2 — Company size + maturity
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("Who they are")
r3c1, r3c2 = st.columns([1, 1], gap="large")

with r3c1:
    st.markdown(f"<h4 style='color:{WHITE};'>By company size</h4>", unsafe_allow_html=True)
    # Prefer the v2 company_size feature; fall back to capital_tier
    if "company_size" in view.columns and total:
        vc = view["company_size"].value_counts()
        ordered = [(t, int(vc.get(t, 0))) for t in COMPANY_SIZE_ORDER if vc.get(t, 0) > 0]
        labels = [t for t, _ in ordered]
        values = [v for _, v in ordered]
        df_bar = pd.DataFrame({"x": labels, "y": values})
        st.plotly_chart(vertical_bar(df_bar, "x", "y", "#E0A24C"),
                        use_container_width=True, config={"displayModeBar": False})
    elif "capital_tier" in view.columns and total:
        vc = view["capital_tier"].value_counts()
        ordered = [(t, int(vc.get(t, 0))) for t in CAPITAL_TIER_ORDER if vc.get(t, 0) > 0]
        labels = [CAPITAL_TIER_LABELS[t] for t, _ in ordered]
        values = [v for _, v in ordered]
        df_bar = pd.DataFrame({"x": labels, "y": values})
        st.plotly_chart(vertical_bar(df_bar, "x", "y", "#E0A24C"),
                        use_container_width=True, config={"displayModeBar": False})

with r3c2:
    st.markdown(f"<h4 style='color:{WHITE};'>By maturity</h4>", unsafe_allow_html=True)
    if "maturity" in view.columns and total:
        vc = view["maturity"].value_counts()
        ordered = [(t, int(vc.get(t, 0))) for t in MATURITY_ORDER if vc.get(t, 0) > 0]
        labels = [MATURITY_LABELS[t] for t, _ in ordered]
        values = [v for _, v in ordered]
        df_bar = pd.DataFrame({"x": labels, "y": values})
        st.plotly_chart(vertical_bar(df_bar, "x", "y", "#37C2A0"),
                        use_container_width=True, config={"displayModeBar": False})

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 2 — Top cities
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("Local footprint")
st.markdown(f"<h4 style='color:{WHITE};'>Top cities</h4>", unsafe_allow_html=True)

if "city" in view.columns and total:
    geo = view["city"].value_counts().reset_index()
    geo.columns = ["city", "count"]
    geo = geo[~geo["city"].astype(str).str.lower().isin({"unknown", "other"})]
    geo = geo.head(12).sort_values("count")
    if len(geo):
        st.plotly_chart(
            horizontal_bar(geo["city"], geo["count"], RED, height=max(280, 30 * len(geo))),
            use_container_width=True, config={"displayModeBar": False},
        )
    else:
        st.info("No recognizable city found in the addresses for this view.")

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# TIER 3 — "Show more analysis" expander
# ──────────────────────────────────────────────────────────────────────────────

with st.expander("Show more analysis", expanded=False):

    # ── Business model breakdown ─────────────────────────────────────────────
    eyebrow("Customer focus")
    st.markdown(f"<h4 style='color:{WHITE};'>Business model (B2B / B2C)</h4>", unsafe_allow_html=True)
    if "business_model" in view.columns and total:
        vc = view["business_model"].value_counts()
        order = ["B2B", "B2C", "mixed", "unknown"]
        labels = [BUSINESS_MODEL_LABELS.get(t, t) for t in order if vc.get(t, 0) > 0]
        values = [int(vc.get(t, 0)) for t in order if vc.get(t, 0) > 0]
        df_bar = pd.DataFrame({"x": labels, "y": values})
        st.plotly_chart(vertical_bar(df_bar, "x", "y", "#E07CB0", height=300),
                        use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:1vh;'></div>", unsafe_allow_html=True)

    # ── International + Dynamism + Fleet side by side ────────────────────────
    eyebrow("Deeper signals")
    e1, e2, e3 = st.columns(3, gap="large")

    with e1:
        st.markdown(f"<h4 style='color:{WHITE};'>International signal</h4>", unsafe_allow_html=True)
        intl = col_sum("international_signal")
        intl_pct = (100 * intl / total) if total else 0
        st.markdown(
            f"""
            <div class="on-card" style="text-align:center; padding:1.4rem 1rem;">
                <div style="color:{WHITE}; font-size:2.4rem; font-weight:800;">{intl:,}</div>
                <div style="color:{MUTED}; font-size:0.9rem; margin-top:0.3rem;">
                    companies with international scope ({intl_pct:.1f}%)
                </div>
                <div style="color:{OFF_WHITE}; font-size:0.85rem; margin-top:0.6rem; line-height:1.5;">
                    Likely candidates for international call plans, roaming, multi-country VPN.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with e2:
        st.markdown(f"<h4 style='color:{WHITE};'>Dynamism</h4>", unsafe_allow_html=True)
        if "dynamism_score" in view.columns and total:
            vc = view["dynamism_score"].value_counts()
            labels = [DYNAMISM_LABELS[t] for t in DYNAMISM_ORDER if vc.get(t, 0) > 0]
            values = [int(vc.get(t, 0)) for t in DYNAMISM_ORDER if vc.get(t, 0) > 0]
            df_bar = pd.DataFrame({"x": labels, "y": values})
            st.plotly_chart(vertical_bar(df_bar, "x", "y", "#9B89E6", height=280),
                            use_container_width=True, config={"displayModeBar": False})

    with e3:
        st.markdown(f"<h4 style='color:{WHITE};'>Fleet size</h4>", unsafe_allow_html=True)
        if "fleet_size" in view.columns and total:
            vc = view["fleet_size"].value_counts()
            ordered = [(t, int(vc.get(t, 0))) for t in FLEET_ORDER if vc.get(t, 0) > 0]
            labels = [FLEET_LABELS[t] for t, _ in ordered]
            values = [v for _, v in ordered]
            df_bar = pd.DataFrame({"x": labels, "y": values})
            st.plotly_chart(vertical_bar(df_bar, "x", "y", "#3FB8B0", height=280),
                            use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:1vh;'></div>", unsafe_allow_html=True)

    # ── Full opportunity matrix table ─────────────────────────────────────────
    eyebrow("All segments")
    st.markdown(
        f"<h4 style='color:{WHITE};'>Full opportunity matrix</h4>"
        f"<p style='color:{MUTED}; font-size:0.9rem; margin-top:0;'>"
        f"Every combination of size × connectivity need × business model. "
        f"This is the table the future recommendation engine will consume.</p>",
        unsafe_allow_html=True,
    )
    opp = load_csv(str(OPPORTUNITY_CSV))
    if opp is not None and len(opp):
        show = opp.rename(columns={
            "company_size": "Size", "connectivity_need": "Connectivity",
            "business_model": "Business model", "companies": "Companies",
            "avg_capital": "Avg capital (TND)", "pct_new": "% new",
        })
        # Map labels
        if "Connectivity" in show.columns:
            show["Connectivity"] = show["Connectivity"].map(lambda c: CONNECTIVITY_LABELS.get(c, c))
        if "Business model" in show.columns:
            show["Business model"] = show["Business model"].map(lambda c: BUSINESS_MODEL_LABELS.get(c, c))
        st.dataframe(show, use_container_width=True,
                     height=min(420, 56 + 36 * len(show)), hide_index=True)
    else:
        st.info("Opportunity matrix not found.")

    st.markdown("<div style='height:1vh;'></div>", unsafe_allow_html=True)

    # ── Sector scorecard table ────────────────────────────────────────────────
    eyebrow("Sector scorecard")
    st.markdown(f"<h4 style='color:{WHITE};'>The numbers behind each sector</h4>", unsafe_allow_html=True)
    kpis = load_csv(str(SECTOR_KPIS_CSV))
    if kpis is not None and len(kpis):
        show = kpis.copy()
        if "category" in show.columns:
            show["category"] = show["category"].map(lambda c: CATEGORY_LABELS.get(c, c))
        rename = {
            "category": "Sector", "companies": "Companies",
            "avg_capital": "Avg capital", "median_capital": "Median capital",
            "avg_age_years": "Avg age (y)", "pct_digital_high": "Digital %",
            "pct_mobility": "Mobility %", "pct_multisite": "Multi-site %",
            "pct_callable": "Callable %", "avg_confidence": "Avg confidence",
        }
        show = show.rename(columns={k: v for k, v in rename.items() if k in show.columns})
        st.dataframe(show, use_container_width=True, height=330, hide_index=True)
    else:
        st.info("Sector scorecard not found.")


# ── Download the data behind this view ────────────────────────────────────────
section_divider()
csv_bytes = view.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "Download the data behind this view (CSV)",
    data=csv_bytes,
    file_name="market_intelligence_view.csv",
    mime="text/csv",
)

show_fixed_logo()
