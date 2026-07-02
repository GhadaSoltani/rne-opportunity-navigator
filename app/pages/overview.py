"""
app/pages/2_Results.py
======================
Explore how each company was classified.

Small result sets show in full automatically; larger ones get filters,
a column picker, and a styled, sortable table.
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
from app.components.charts import category_distribution_chart, method_distribution_chart
from segmentation.config import OUTPUT_CSV, REVIEW_CSV, AUDIT_CSV


inject_global_css()
sidebar_context()

AUTO_SHOW_THRESHOLD = 10


@st.cache_data(ttl=20)
def load_results(path_str: str) -> pd.DataFrame | None:
    path = Path(path_str)
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig")


page_title("Overview", "See how every company was classified.")

df = load_results(str(OUTPUT_CSV))

if df is None:
    st.markdown(
        f"""
        <div class="on-card on-reveal" style="text-align:center; margin-top:1.4rem;">
            <p style="color:{OFF_WHITE}; font-size:1.05rem; margin:0;">
                No data yet. Head to <b>Import data</b> in the sidebar to bring in your first companies.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_fixed_logo()
    st.stop()


# ── Summary metrics ───────────────────────────────────────────────────────────
total          = len(df)
needs_review   = int(((df["needs_review"] == True) & (df["method"] != "empty_activity")).sum())
empty_activity = int((df["method"] == "empty_activity").sum())
classified     = total - empty_activity

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total companies", f"{total:,}")
c2.metric("Classified",      f"{classified:,}")
c3.metric("Needs review",    f"{needs_review:,}")
c4.metric("No activity",     f"{empty_activity:,}")

section_divider()


# ── Charts ────────────────────────────────────────────────────────────────────
eyebrow("Distribution")
chart_col1, chart_col2 = st.columns([1, 1], gap="large")

with chart_col1:
    st.markdown(f"<h4 style='color:{WHITE};'>By sector</h4>", unsafe_allow_html=True)
    chart_type = st.radio(
        "Chart type", ["bar", "pie"], horizontal=True, label_visibility="collapsed"
    )
    category_distribution_chart(df, chart_type=chart_type)

with chart_col2:
    st.markdown(f"<h4 style='color:{WHITE};'>How they were classified</h4>", unsafe_allow_html=True)
    method_distribution_chart(df)

section_divider()


# ── Display columns available ─────────────────────────────────────────────────
display_cols_all = [
    c for c in [
        "identifiant_unique", "fr_denomination", "activity_raw_combined",
        "category", "confidence", "method", "matched_keywords", "needs_review",
    ]
    if c in df.columns
]

NUMERIC_FMT = {"confidence": "{:.2f}"}


def _render_table(frame: pd.DataFrame, cols: list[str], height: int = 440):
    """Styled, sortable table via pandas Styler."""
    st.dataframe(
        style_dataframe(frame[cols], numeric_format=NUMERIC_FMT),
        use_container_width=True,
        height=height,
    )


# =============================================================================
# CASE 1 — small result set: show everything automatically
# =============================================================================
if total <= AUTO_SHOW_THRESHOLD:
    eyebrow("All companies")
    st.markdown(
        f"<p style='color:{MUTED};'>Showing all {total} companies.</p>",
        unsafe_allow_html=True,
    )
    _render_table(df, display_cols_all, height=400)

# =============================================================================
# CASE 2 — large result set: give the user controls
# =============================================================================
else:
    eyebrow(f"Browse {total:,} companies")

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
        selected_cat = st.selectbox("Sector", categories)
    with fcol2:
        methods = ["All"] + sorted(df["method"].dropna().unique().tolist())
        selected_method = st.selectbox("Method", methods)
    with fcol3:
        review_filter = st.selectbox("Review status", ["All", "Needs review only", "Accepted only"])

    fcol4, fcol5 = st.columns([2, 1])
    with fcol4:
        search_col_options = [
            c for c in ["identifiant_unique", "fr_denomination", "activity_raw_combined"]
            if c in df.columns
        ]
        search_col  = st.selectbox("Search in", search_col_options) if search_col_options else None
        search_term = st.text_input("Find a company (leave empty to ignore)", "")
    with fcol5:
        row_limit = st.number_input("Rows to show", min_value=1, max_value=total, value=min(50, total))

    chosen_cols = st.multiselect(
        "Columns", options=display_cols_all, default=display_cols_all,
    )
    if not chosen_cols:
        chosen_cols = display_cols_all

    # ── Apply filters ────────────────────────────────────────────────────────
    filtered = df.copy()
    if selected_cat != "All":
        filtered = filtered[filtered["category"] == selected_cat]
    if selected_method != "All":
        filtered = filtered[filtered["method"] == selected_method]
    if review_filter == "Needs review only":
        filtered = filtered[(filtered["needs_review"] == True) & (filtered["method"] != "empty_activity")]
    elif review_filter == "Accepted only":
        filtered = filtered[filtered["needs_review"] == False]
    if search_col and search_term.strip():
        mask = filtered[search_col].astype(str).str.contains(search_term.strip(), case=False, na=False)
        filtered = filtered[mask]

    st.markdown(
        f"<p style='color:{OFF_WHITE};'>Matched <b>{len(filtered):,}</b> companies. "
        f"Showing first <b>{min(len(filtered), int(row_limit)):,}</b>.</p>",
        unsafe_allow_html=True,
    )

    _render_table(filtered.head(int(row_limit)), chosen_cols, height=460)

    csv_bytes = filtered[chosen_cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "Download this view (CSV)",
        data=csv_bytes,
        file_name="filtered_results.csv",
        mime="text/csv",
    )


# ── Full downloads ────────────────────────────────────────────────────────────
section_divider()
eyebrow("Download full outputs")

d1, d2, d3 = st.columns(3)
with d1:
    if OUTPUT_CSV.exists():
        st.download_button(
            "Full classified file",
            data=OUTPUT_CSV.read_bytes(),
            file_name="rne_companies_segmented.csv",
            mime="text/csv",
            use_container_width=True,
        )
with d2:
    if AUDIT_CSV.exists():
        st.download_button(
            "Classification audit",
            data=AUDIT_CSV.read_bytes(),
            file_name="classification_audit.csv",
            mime="text/csv",
            use_container_width=True,
        )
with d3:
    if REVIEW_CSV.exists():
        st.download_button(
            "Needs-review list",
            data=REVIEW_CSV.read_bytes(),
            file_name="review_needed.csv",
            mime="text/csv",
            use_container_width=True,
        )

show_fixed_logo()
