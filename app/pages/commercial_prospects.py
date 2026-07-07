"""
app/pages/commercial_prospects.py
==================================
Commercial Prospects — recommendation-powered prospect view.

When the recommendation system has been run (recommendations_raw.csv exists):
    Section 1  KPI strip — companies, recommendations, avg score, strong matches
    Section 2  What to lead with — rank-1 offer distribution
    Section 3  Score anatomy — where the signal comes from, by sector
    Section 4  Recommendation explorer — filterable table, one row per company
    Section 5  Company deep-dive — select a company, see full recommendation card
    Section 6  Downloads

Falls back to a helpful message when recommendations have not been generated yet.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from app.theme import (
    inject_global_css, section_divider, style_dataframe,
    WHITE, RED, RED_SOFT, MUTED, OFF_WHITE, SUCCESS,
    NAVY, NAVY_LIGHT, NAVY_LIGHTER, NAVY_HAIRLINE,
    CATEGORY_COLORS,
)
from app.components.branding import (
    show_fixed_logo, page_title, sidebar_context, eyebrow,
)
from app.components.charts import (
    recommendation_top_offers_chart,
    score_anatomy_chart,
    family_donut_chart,
    FAMILY_COLORS,
    FAMILY_LABELS,
)

inject_global_css()
sidebar_context()


# ─────────────────────────────────────────────────────────────────────────────
# Paths — constructed the same way as recommendation/config.py
# ─────────────────────────────────────────────────────────────────────────────
DATA_OUTPUT = Path("data/output")
RECOMMENDATIONS_CSV = DATA_OUTPUT / "recommendations_raw.csv"
FEATURES_CSV        = DATA_OUTPUT / "company_features.csv"

CATEGORY_LABELS = {
    "retail": "Retail", "manufacturing": "Manufacturing",
    "transport": "Transport", "tourism": "Tourism",
    "healthcare": "Healthcare", "education": "Education",
    "financial_services": "Financial services", "others": "Others",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=20)
def load_recommendations() -> pd.DataFrame | None:
    if not RECOMMENDATIONS_CSV.exists():
        return None
    return pd.read_csv(RECOMMENDATIONS_CSV, encoding="utf-8-sig")


@st.cache_data(ttl=20)
def load_features() -> pd.DataFrame | None:
    if not FEATURES_CSV.exists():
        return None
    return pd.read_csv(FEATURES_CSV, encoding="utf-8-sig")


def enrich_recommendations(recs: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Join recommendations with company features for display."""
    join_cols = [
        "identifiant_unique", "fr_denomination", "fr_activite_principale",
        "category", "company_size", "capital_tier", "maturity", "city",
        "callable_prospect", "digital_signal", "mobility_signal",
        "multisite_signal", "governorate",
    ]
    available = [c for c in join_cols if c in feats.columns]
    merged = recs.merge(
        feats[available].drop_duplicates(subset=["identifiant_unique"]),
        on="identifiant_unique",
        how="left",
    )
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _esc(text) -> str:
    s = str(text) if text is not None else ""
    if s.lower() in ("nan", "none", ""):
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _category_badge(cat: str) -> str:
    key = str(cat).strip()
    if not key or key.lower() in ("nan", "none"):
        return f'<span style="color:{MUTED};">—</span>'
    color = CATEGORY_COLORS.get(key, "#7286A6")
    label = CATEGORY_LABELS.get(key, key)
    return (
        f'<span style="display:inline-flex; align-items:center; gap:0.35rem;'
        f' background:{color}1a; border:1px solid {color}44; color:{WHITE};'
        f' border-radius:999px; padding:0.15rem 0.6rem; font-size:0.78rem;'
        f' white-space:nowrap;">'
        f'<span style="width:6px;height:6px;border-radius:50%;'
        f'background:{color};"></span>{_esc(label)}</span>'
    )


def _family_badge(family: str) -> str:
    key = str(family).strip()
    if not key or key.lower() in ("nan", "none"):
        return ""
    color = FAMILY_COLORS.get(key, "#7286A6")
    label = FAMILY_LABELS.get(key, key)
    return (
        f'<span style="display:inline-flex; align-items:center; gap:0.3rem;'
        f' background:{color}1a; border:1px solid {color}44; color:{color};'
        f' border-radius:6px; padding:0.12rem 0.5rem; font-size:0.72rem;'
        f' font-weight:600; text-transform:uppercase; letter-spacing:0.04em;'
        f' white-space:nowrap;">{_esc(label)}</span>'
    )


def _score_bar(score: float, max_val: float = 1.0, color: str = RED) -> str:
    pct = min(100, max(0, (score / max_val) * 100))
    return (
        f'<div style="display:flex; align-items:center; gap:0.5rem;">'
        f'<div style="flex:1; background:{NAVY}; border-radius:4px; height:6px;'
        f' overflow:hidden; min-width:60px;">'
        f'<div style="width:{pct:.0f}%; height:100%; border-radius:4px;'
        f' background:linear-gradient(90deg, {color}, {color}cc);"></div>'
        f'</div>'
        f'<span style="color:{WHITE}; font-size:0.82rem; font-weight:600;'
        f' min-width:32px; text-align:right;">{score:.2f}</span>'
        f'</div>'
    )


def _mini_score_bar(score: float, color: str, label: str) -> str:
    pct = min(100, max(0, score * 100))
    return (
        f'<div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:3px;">'
        f'<span style="color:{color}; font-size:0.72rem; width:52px;'
        f' text-align:right;">{label}</span>'
        f'<div style="flex:1; background:{NAVY}; border-radius:3px; height:4px;'
        f' overflow:hidden;">'
        f'<div style="width:{pct:.0f}%; height:100%; border-radius:3px;'
        f' background:{color};"></div></div>'
        f'<span style="color:{MUTED}; font-size:0.72rem; width:28px;">'
        f'{score:.2f}</span></div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Company deep-dive card renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_company_card(company_id: str, recs: pd.DataFrame, feats_row: dict) -> str:
    """Render a full recommendation card for one company as HTML."""
    name     = _esc(feats_row.get("fr_denomination", ""))
    activity = _esc(feats_row.get("fr_activite_principale", ""))
    category = str(feats_row.get("category", "")).strip()
    size     = _esc(feats_row.get("company_size", ""))
    city     = _esc(feats_row.get("city", ""))
    maturity = _esc(feats_row.get("maturity", ""))
    comp_id  = _esc(company_id)

    if not name or name.lower() in ("nan", "none"):
        name = comp_id

    # Company header
    meta_parts = []
    if size and size.lower() not in ("nan", "unknown"):
        meta_parts.append(size)
    if city and city.lower() not in ("nan", "unknown", "other"):
        meta_parts.append(city)
    if maturity and maturity.lower() not in ("nan", "unknown"):
        meta_parts.append(maturity)
    meta_line = " · ".join(meta_parts) if meta_parts else ""

    header = f"""
    <div style="margin-bottom:1rem;">
        <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap;">
            {_category_badge(category)}
            <span style="font-size:1.1rem; font-weight:700; color:{WHITE};">{name}</span>
            <span style="color:{MUTED}; font-size:0.82rem;">{comp_id}</span>
        </div>
        <div style="color:{OFF_WHITE}; font-size:0.88rem; margin-top:0.3rem;
             max-width:600px; overflow:hidden; text-overflow:ellipsis;
             white-space:nowrap;" title="{activity}">{activity}</div>
        <div style="color:{MUTED}; font-size:0.82rem; margin-top:0.2rem;">{meta_line}</div>
    </div>
    """

    # Offer cards (up to 3)
    company_recs = recs[recs["identifiant_unique"] == company_id].sort_values("rank")
    offer_cards = ""

    for _, rec in company_recs.iterrows():
        rank         = int(rec.get("rank", 0))
        offer_name   = _esc(rec.get("offer_name", ""))
        family       = str(rec.get("family", "")).strip()
        final_score  = float(rec.get("final_score", 0))
        rule_score   = float(rec.get("rule_score", 0))
        content_score = float(rec.get("content_score", 0))
        collab_score = float(rec.get("collab_score", 0))
        rule_reasons = _esc(rec.get("rule_reasons", ""))
        why_matched  = _esc(rec.get("content_why_matched", ""))
        collab_src   = _esc(rec.get("collab_source", ""))

        # Rank accent color: #1 gets red, #2 gets softer, #3 gets muted
        rank_colors = {1: RED, 2: "#5B8FE0", 3: MUTED}
        rank_color = rank_colors.get(rank, MUTED)

        # Build explanation snippets
        explain_parts = []
        if rule_reasons:
            # Take first reason only for brevity
            first_reason = rule_reasons.split(" | ")[0]
            explain_parts.append(
                f'<div style="color:{OFF_WHITE}; font-size:0.8rem; line-height:1.4;">'
                f'<span style="color:#5B8FE0;">Rules:</span> {first_reason}</div>'
            )
        if why_matched and why_matched.lower() not in ("", "nan"):
            explain_parts.append(
                f'<div style="color:{OFF_WHITE}; font-size:0.8rem; line-height:1.4;">'
                f'<span style="color:#37C2A0;">Match:</span> {why_matched}</div>'
            )
        if collab_src and collab_src.lower() not in ("none", "nan", ""):
            explain_parts.append(
                f'<div style="color:{OFF_WHITE}; font-size:0.8rem; line-height:1.4;">'
                f'<span style="color:#E0A24C;">Peers:</span> {collab_src}</div>'
            )
        explain_html = "".join(explain_parts)

        offer_cards += f"""
        <div style="background:rgba(10,27,56,0.5); border:1px solid {NAVY_HAIRLINE};
             border-radius:12px; padding:1rem; flex:1; min-width:220px;">
            <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.7rem;
                 flex-wrap:wrap;">
                <span style="color:{rank_color}; font-weight:800; font-size:0.9rem;">#{rank}</span>
                {_family_badge(family)}
                <span style="color:{WHITE}; font-weight:600; font-size:0.92rem;">{offer_name}</span>
            </div>
            {_score_bar(final_score, color=rank_color)}
            <div style="margin-top:0.6rem;">
                {_mini_score_bar(rule_score, "#5B8FE0", "Rules")}
                {_mini_score_bar(content_score, "#37C2A0", "Content")}
                {_mini_score_bar(collab_score, "#E0A24C", "Peers")}
            </div>
            <div style="margin-top:0.6rem; border-top:1px solid {NAVY_HAIRLINE};
                 padding-top:0.5rem;">
                {explain_html if explain_html else f'<span style="color:{MUTED}; font-size:0.8rem;">Semantic match</span>'}
            </div>
        </div>
        """

    return f"""
    <div class="on-card on-reveal" style="margin-bottom:1rem;">
        {header}
        <div style="display:flex; gap:0.8rem; flex-wrap:wrap;">
            {offer_cards}
        </div>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

page_title("Commercial Prospects", "AI-powered recommendations for every company.")

recs_df  = load_recommendations()
feats_df = load_features()

# ── Guard: no data yet ────────────────────────────────────────────────────────
if recs_df is None or feats_df is None:
    missing_recs  = recs_df is None
    missing_feats = feats_df is None

    st.markdown(
        f"""
        <div class="on-card on-reveal" style="text-align:center; margin-top:1.4rem;">
            <p style="color:{OFF_WHITE}; font-size:1.05rem; margin:0 0 0.6rem 0;">
                {"Recommendations have not been generated yet." if missing_recs else
                 "Company features file not found."}
            </p>
            <p style="color:{MUTED}; font-size:0.92rem; margin:0 0 0.2rem 0;">
                Run the full pipeline with recommendations enabled:
            </p>
            <code style="color:{RED_SOFT}; font-size:0.88rem;">
                python run.py --from-db --recommend
            </code>
            <p style="color:{MUTED}; font-size:0.85rem; margin:0.6rem 0 0 0;">
                or separately: <code style="color:{RED_SOFT};">python -m recommendation.main</code>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_fixed_logo()
    st.stop()


# ── Enrich recommendations with company features ─────────────────────────────
recs = enrich_recommendations(recs_df, feats_df)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — KPIs
# ══════════════════════════════════════════════════════════════════════════════

top1 = recs[recs["rank"] == 1]
n_companies     = top1["identifiant_unique"].nunique()
n_offers_in_play = top1["offer_id"].nunique()
avg_score       = top1["final_score"].mean()
strong_matches  = int((top1["final_score"] >= 0.50).sum())
strong_pct      = (100 * strong_matches / n_companies) if n_companies else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies analyzed", f"{n_companies:,}")
c2.metric("Offers in play",     f"{n_offers_in_play}")
c3.metric("Avg match score",    f"{avg_score:.2f}")
c4.metric("Strong matches (≥0.5)", f"{strong_matches:,}")

section_divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — What to lead with
# ══════════════════════════════════════════════════════════════════════════════

eyebrow("What to lead with")

chart_col1, chart_col2 = st.columns([3, 2], gap="large")
with chart_col1:
    st.markdown(
        f"<h4 style='color:{WHITE}; margin-top:0;'>Top recommended offers</h4>"
        f"<p style='color:{MUTED}; font-size:0.88rem; margin-top:0;'>"
        f"Which offers appear most as the #1 recommendation.</p>",
        unsafe_allow_html=True,
    )
    recommendation_top_offers_chart(recs)

with chart_col2:
    st.markdown(
        f"<h4 style='color:{WHITE}; margin-top:0;'>By offer family</h4>"
        f"<p style='color:{MUTED}; font-size:0.88rem; margin-top:0;'>"
        f"Product families across all top picks.</p>",
        unsafe_allow_html=True,
    )
    family_donut_chart(recs)

section_divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Score anatomy
# ══════════════════════════════════════════════════════════════════════════════

eyebrow("Score anatomy")
st.markdown(
    f"<h4 style='color:{WHITE}; margin-top:0;'>Where the signal comes from</h4>"
    f"<p style='color:{MUTED}; font-size:0.88rem; margin-top:0;'>"
    f"Average contribution of each scoring layer to the top recommendation, by sector. "
    f"<span style='color:#5B8FE0;'>Rules</span> = business logic · "
    f"<span style='color:#37C2A0;'>Content</span> = semantic match · "
    f"<span style='color:#E0A24C;'>Peers</span> = purchase history.</p>",
    unsafe_allow_html=True,
)
score_anatomy_chart(recs)

section_divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Recommendation explorer
# ══════════════════════════════════════════════════════════════════════════════

eyebrow("Recommendation explorer")
st.markdown(
    f"<h4 style='color:{WHITE}; margin-top:0;'>Browse all recommendations</h4>",
    unsafe_allow_html=True,
)

# ── Filters ───────────────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns(4)

with f1:
    cat_opts = ["All sectors"]
    if "category" in recs.columns:
        cats = sorted(recs["category"].dropna().unique().tolist())
        cat_opts += [CATEGORY_LABELS.get(c, c) for c in cats if str(c).strip()]
    selected_sector = st.selectbox("Sector", cat_opts, key="rec_sector")

with f2:
    family_opts = ["All families"]
    if "family" in recs.columns:
        fams = sorted(recs["family"].dropna().unique().tolist())
        family_opts += [FAMILY_LABELS.get(f, f) for f in fams if str(f).strip()]
    selected_family = st.selectbox("Offer family", family_opts, key="rec_family")

with f3:
    score_floor = st.slider("Min score", 0.0, 1.0, 0.0, 0.05, key="rec_score")

with f4:
    search_q = st.text_input("Search company", "", key="rec_search",
                             placeholder="Name or ID…")

# ── Apply filters (on rank-1 rows, then bring in rank 2+3) ───────────────────
label_to_cat = {CATEGORY_LABELS.get(c, c): c for c in
                (recs["category"].dropna().unique() if "category" in recs.columns else [])}
label_to_fam = {FAMILY_LABELS.get(f, f): f for f in
                (recs["family"].dropna().unique() if "family" in recs.columns else [])}

filtered_top1 = top1.copy()

if selected_sector != "All sectors":
    cat_key = label_to_cat.get(selected_sector, selected_sector)
    filtered_top1 = filtered_top1[filtered_top1["category"] == cat_key]

if selected_family != "All families":
    fam_key = label_to_fam.get(selected_family, selected_family)
    # Filter companies whose rank-1 offer is in this family
    filtered_top1 = filtered_top1[filtered_top1["family"] == fam_key]

if score_floor > 0:
    filtered_top1 = filtered_top1[filtered_top1["final_score"] >= score_floor]

if search_q.strip():
    q = search_q.strip().lower()
    search_cols = ["fr_denomination", "identifiant_unique", "fr_activite_principale"]
    mask = pd.Series(False, index=filtered_top1.index)
    for col in search_cols:
        if col in filtered_top1.columns:
            mask = mask | filtered_top1[col].astype(str).str.lower().str.contains(
                q, na=False, regex=False
            )
    filtered_top1 = filtered_top1[mask]

# ── Table ─────────────────────────────────────────────────────────────────────
n_filtered = len(filtered_top1)
row_limit = st.number_input(
    "Rows", min_value=10, max_value=max(10, n_filtered),
    value=min(50, max(10, n_filtered)), key="rec_rows",
)

st.markdown(
    f"<p style='color:{OFF_WHITE};'>Matched <b>{n_filtered:,}</b> companies. "
    f"Showing first <b>{min(n_filtered, int(row_limit)):,}</b>.</p>",
    unsafe_allow_html=True,
)

# Build a display table: one row per company with rank-1 info
display = filtered_top1.head(int(row_limit)).copy()
display_cols = []

col_rename = {}
if "fr_denomination" in display.columns:
    col_rename["fr_denomination"] = "Company"
    display_cols.append("Company")
if "category" in display.columns:
    col_rename["category"] = "Sector"
    display_cols.append("Sector")

col_rename["offer_name"] = "Top offer"
display_cols.append("Top offer")

col_rename["family"] = "Family"
display_cols.append("Family")

col_rename["final_score"] = "Score"
display_cols.append("Score")

col_rename["rule_score"] = "Rules"
display_cols.append("Rules")

col_rename["content_score"] = "Content"
display_cols.append("Content")

col_rename["collab_score"] = "Peers"
display_cols.append("Peers")

if "city" in display.columns:
    col_rename["city"] = "City"
    display_cols.append("City")

display = display.rename(columns=col_rename)

# Apply sector labels for readability
if "Sector" in display.columns:
    display["Sector"] = display["Sector"].map(
        lambda c: CATEGORY_LABELS.get(c, c) if pd.notna(c) else "—"
    )
if "Family" in display.columns:
    display["Family"] = display["Family"].map(
        lambda f: FAMILY_LABELS.get(f, f) if pd.notna(f) else "—"
    )

# Keep only display columns that exist
display_cols = [c for c in display_cols if c in display.columns]

if display_cols and len(display) > 0:
    st.dataframe(
        style_dataframe(
            display[display_cols],
            numeric_format={"Score": "{:.2f}", "Rules": "{:.2f}",
                           "Content": "{:.2f}", "Peers": "{:.2f}"},
        ),
        use_container_width=True,
        height=min(520, 56 + 36 * len(display)),
    )
else:
    st.info("No companies match these filters. Try widening them.")


section_divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Company deep-dive
# ══════════════════════════════════════════════════════════════════════════════

eyebrow("Company deep-dive")
st.markdown(
    f"<h4 style='color:{WHITE}; margin-top:0;'>Full recommendation card</h4>"
    f"<p style='color:{MUTED}; font-size:0.88rem; margin-top:0;'>"
    f"Select a company to see all three recommended offers with score breakdowns "
    f"and explanations.</p>",
    unsafe_allow_html=True,
)

# Build a searchable dropdown of companies
company_options = []
for _, row in filtered_top1.head(500).iterrows():
    cid   = str(row["identifiant_unique"])
    cname = str(row.get("fr_denomination", ""))
    ccat  = str(row.get("category", ""))
    if cname and cname.lower() not in ("nan", "none"):
        label = f"{cname}  —  {cid}"
    else:
        label = cid
    if ccat and ccat.lower() not in ("nan", "none"):
        label += f"  [{CATEGORY_LABELS.get(ccat, ccat)}]"
    company_options.append((label, cid))

if company_options:
    selected_label = st.selectbox(
        "Choose a company",
        [opt[0] for opt in company_options],
        key="rec_company_select",
    )
    selected_id = dict(company_options).get(selected_label, "")

    if selected_id:
        # Get all recs for this company (all 3 ranks)
        comp_recs = recs[recs["identifiant_unique"] == selected_id]

        # Get features row
        feat_match = feats_df[feats_df["identifiant_unique"] == selected_id]
        feat_row = feat_match.iloc[0].to_dict() if len(feat_match) > 0 else {}

        st.markdown(
            render_company_card(selected_id, comp_recs, feat_row),
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        f"<p style='color:{MUTED};'>No companies match the current filters.</p>",
        unsafe_allow_html=True,
    )


section_divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Downloads
# ══════════════════════════════════════════════════════════════════════════════

eyebrow("Export")

d1, d2 = st.columns(2)
with d1:
    csv_full = recs_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "Download all recommendations (CSV)",
        data=csv_full,
        file_name="recommendations_raw.csv",
        mime="text/csv",
        use_container_width=True,
    )
with d2:
    if n_filtered > 0:
        csv_filtered = filtered_top1.to_csv(
            index=False, encoding="utf-8-sig"
        ).encode("utf-8-sig")
        st.download_button(
            f"Download filtered view ({n_filtered:,} companies)",
            data=csv_filtered,
            file_name="recommendations_filtered.csv",
            mime="text/csv",
            use_container_width=True,
        )

show_fixed_logo()
