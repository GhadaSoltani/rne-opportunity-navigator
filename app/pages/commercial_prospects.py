"""
app/pages/3_Commercial_Prospects.py
====================================
Explore the prospect file produced by the analysis layer.

  1. Prospect table with filters and a styled, sortable view
  2. Recommended-offer distribution chart (harmonized palette)
  3. Sector KPIs, top cohorts, and activities to refine
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from app.theme import (
    inject_global_css, section_divider, style_dataframe,
    WHITE, RED, MUTED, OFF_WHITE, SUCCESS,
)
from app.components.branding import (
    show_fixed_logo, page_title, sidebar_context, eyebrow,
)
from app.components.charts import offer_distribution_chart
from analysis.config import (
    PROSPECTS_CSV,
    COHORT_SUMMARY_CSV,
    SECTOR_KPIS_CSV,
    VAGUE_ACTIVITIES_CSV,
)


inject_global_css()
sidebar_context()


@st.cache_data(ttl=20)
def load_csv(path_str: str) -> pd.DataFrame | None:
    path = Path(path_str)
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


page_title("Commercial Prospects", "Companies matched to the offer that fits them.")

prospects = load_csv(str(PROSPECTS_CSV))

if prospects is None:
    st.markdown(
        f"""
        <div class="on-card on-reveal" style="text-align:center; margin-top:1.4rem;">
            <p style="color:{OFF_WHITE}; font-size:1.05rem; margin:0 0 0.4rem 0;">
                No prospect file yet. Run the Navigator from <b>Upload &amp; Run</b> first.
            </p>
            <p style="color:{MUTED}; font-size:0.92rem; margin:0;">
                The prospect view is prepared automatically at the end of each run.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_fixed_logo()
    st.stop()


# ── Top KPIs ──────────────────────────────────────────────────────────────────
total = len(prospects)
callable_count = int(prospects["callable_prospect"].sum()) if "callable_prospect" in prospects.columns else None
digital_high = int((prospects["digital_signal"] == "high").sum()) if "digital_signal" in prospects.columns else 0
mobility = int(prospects["mobility_signal"].sum()) if "mobility_signal" in prospects.columns else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total prospects",        f"{total:,}")
c2.metric("Callable",               f"{callable_count:,}" if callable_count is not None else "—")
c3.metric("Digital signal = high",  f"{digital_high:,}")
c4.metric("Mobility signal",        f"{mobility:,}")

section_divider()


# ── Offer distribution chart ──────────────────────────────────────────────────
eyebrow("Recommended offers")
st.markdown(f"<h4 style='color:{WHITE}; margin-top:0;'>What to lead with</h4>", unsafe_allow_html=True)
offer_distribution_chart(prospects, offer_col="recommended_offer")

section_divider()


# ── Filters ───────────────────────────────────────────────────────────────────
eyebrow(f"Browse {total:,} prospects")

f1, f2, f3 = st.columns(3)
with f1:
    offers = ["All"] + sorted(prospects["recommended_offer"].dropna().unique().tolist())
    selected_offer = st.selectbox("Recommended offer", offers)
with f2:
    if "city" in prospects.columns:
        cities = ["All"] + sorted(prospects["city"].dropna().unique().tolist())
    else:
        cities = ["All"]
    selected_city = st.selectbox("City", cities)
with f3:
    callable_only = st.checkbox("Callable only", value=True)


filtered = prospects.copy()
if selected_offer != "All":
    filtered = filtered[filtered["recommended_offer"] == selected_offer]
if "city" in filtered.columns and selected_city != "All":
    filtered = filtered[filtered["city"] == selected_city]
if callable_only and "callable_prospect" in filtered.columns:
    filtered = filtered[filtered["callable_prospect"] == True]


# ── Limit and table ───────────────────────────────────────────────────────────
safe_max = max(10, len(filtered))
row_limit = st.number_input(
    "Rows to show", min_value=10, max_value=safe_max, value=min(100, safe_max)
)

display_cols = [c for c in [
    "recommended_offer", "fr_denomination", "city", "category",
    "capital_tier", "maturity", "digital_signal", "mobility_signal",
    "multisite_signal", "fr_activite_principale", "fr_adresse",
] if c in filtered.columns]

st.markdown(
    f"<p style='color:{OFF_WHITE};'>Matched <b>{len(filtered):,}</b> prospects. "
    f"Showing first <b>{min(len(filtered), int(row_limit)):,}</b>.</p>",
    unsafe_allow_html=True,
)

if display_cols and len(filtered) > 0:
    st.dataframe(
        style_dataframe(filtered[display_cols].head(int(row_limit))),
        use_container_width=True,
        height=460,
    )
else:
    st.info("No prospects match these filters. Try widening them.")


# ── Download ──────────────────────────────────────────────────────────────────
csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "Download this view (CSV)",
    data=csv_bytes,
    file_name="filtered_prospects.csv",
    mime="text/csv",
)

section_divider()


# ── Sector KPIs ───────────────────────────────────────────────────────────────
eyebrow("Sector KPIs")
sector_kpis = load_csv(str(SECTOR_KPIS_CSV))
if sector_kpis is not None:
    st.dataframe(style_dataframe(sector_kpis), use_container_width=True, height=320)
else:
    st.info("Sector KPI file not found. It is built during analysis.")


# ── Cohort summary ────────────────────────────────────────────────────────────
eyebrow("Top cohorts")
cohort = load_csv(str(COHORT_SUMMARY_CSV))
if cohort is not None:
    st.dataframe(style_dataframe(cohort.head(40)), use_container_width=True, height=360)
    st.markdown(
        f"<p style='color:{MUTED}; font-size:0.92rem;'>"
        f"Sorted by company count. Showing top 40 of {len(cohort):,} cohorts.</p>",
        unsafe_allow_html=True,
    )
else:
    st.info("Cohort summary file not found. It is built during analysis.")


# ── Vague activities ──────────────────────────────────────────────────────────
eyebrow("Activities to refine")
vague = load_csv(str(VAGUE_ACTIVITIES_CSV))
if vague is not None and len(vague) > 0:
    st.dataframe(style_dataframe(vague), use_container_width=True, height=320)
    st.markdown(
        f"<p style='color:{MUTED}; font-size:0.92rem;'>"
        f"These activities led to many uncertain classifications. Adding them to "
        f"<code>knowledge/validated_examples.csv</code> will sharpen future runs.</p>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<p style='color:{MUTED};'>Nothing flagged for refinement — classifications look clean.</p>",
        unsafe_allow_html=True,
    )

show_fixed_logo()
