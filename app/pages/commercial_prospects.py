"""
app/pages/commercial_prospects.py
==================================
Commercial Prospects — recommendation-powered prospect view.

Sections:
    1  KPI strip
    2  What to lead with — rank-1 offer chart + family donut
    3  Recommendation explorer — styled HTML table (paginated)
    4  Company deep-dive — enter an RNE ID, see the recommendation card
    5  Downloads

IMPORTANT — HTML rendering:
    Streamlit's markdown renderer treats any line that begins with leading
    whitespace as an indented code block, which dumps raw HTML to screen.
    Every HTML helper here therefore returns a SINGLE-LINE string with no
    leading indentation. Hover effects live in a CSS class (injected once),
    never as inline on* handlers (Streamlit's sanitizer strips those).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from app.theme import (
    inject_global_css, section_divider,
    WHITE, RED, RED_SOFT, MUTED, OFF_WHITE, SUCCESS,
    NAVY, NAVY_LIGHT, NAVY_LIGHTER, NAVY_HAIRLINE,
    CATEGORY_COLORS,
)
from app.components.branding import (
    show_fixed_logo, page_title, sidebar_context, eyebrow,
)
from app.components.charts import (
    recommendation_top_offers_chart,
    family_donut_chart,
    strongest_by_sector_chart,
    FAMILY_COLORS,
    FAMILY_LABELS,
)

inject_global_css()
sidebar_context()


# ─────────────────────────────────────────────────────────────────────────────
# Page-scoped CSS — injected once. Hover states live here, NOT inline.
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <style>
    .rec-table-wrap {{
        border: 1px solid {NAVY_HAIRLINE};
        border-radius: 14px;
        overflow: auto;
        max-height: 640px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.18);
    }}
    .rec-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9rem;
    }}
    .rec-table thead th {{
        position: sticky;
        top: 0;
        background: {NAVY_LIGHTER};
        color: {WHITE};
        text-align: left;
        padding: 12px 14px;
        font-size: 0.72rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        font-weight: 600;
        white-space: nowrap;
        border-bottom: 2px solid {NAVY_HAIRLINE};
        z-index: 2;
    }}
    .rec-table tbody td {{
        padding: 11px 14px;
        border-bottom: 1px solid {NAVY};
        vertical-align: middle;
    }}
    .rec-table tbody tr:nth-child(odd)  td {{ background: {NAVY_LIGHT}; }}
    .rec-table tbody tr:nth-child(even) td {{ background: rgba(27,53,89,0.35); }}
    .rec-table tbody tr {{ transition: background 0.15s ease; }}
    .rec-table tbody tr:hover td {{ background: rgba(237,28,36,0.10) !important; }}

    .rec-id      {{ color: {MUTED}; font-size: 0.82rem; font-family: monospace; white-space: nowrap; }}
    .rec-name    {{ color: {WHITE}; font-weight: 600; font-size: 0.9rem; max-width: 230px;
                    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .rec-offer   {{ color: {OFF_WHITE}; font-weight: 500; font-size: 0.88rem; white-space: nowrap; }}
    .rec-city    {{ color: {OFF_WHITE}; font-size: 0.85rem; white-space: nowrap; }}
    .rec-score-n {{ color: {WHITE}; font-size: 0.82rem; font-weight: 700; min-width: 30px; text-align: right; }}
    .rec-badge   {{ display: inline-flex; align-items: center; gap: 0.35rem; border-radius: 999px;
                    padding: 0.15rem 0.6rem; font-size: 0.78rem; white-space: nowrap; color: {WHITE}; }}
    .rec-fam     {{ display: inline-flex; align-items: center; border-radius: 6px; padding: 0.12rem 0.5rem;
                    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
                    letter-spacing: 0.04em; white-space: nowrap; }}
    .rec-track   {{ flex: 1; background: {NAVY}; border-radius: 3px; height: 5px;
                    overflow: hidden; min-width: 50px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Paths
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


def _generate_recommendations_only() -> str | None:
    """Run recommendation Layers 1-4 only. Needs company_features.csv to already exist.
    Returns an error message on failure, or None on success."""
    from recommendation.main import run_recommendation
    try:
        run_recommendation()
        return None
    except Exception as e:
        return str(e)


def _generate_full_pipeline() -> str | None:
    """Run the full --from-db pipeline (extraction + segmentation + analysis), then
    recommendations. Needs DB credentials (MONGO_URI, MinIO) configured in the environment.
    Returns an error message on failure, or None on success."""
    from pipeline.runner import run_pipeline
    from recommendation.main import run_recommendation
    try:
        run_pipeline(from_db=True)
        run_recommendation()
        return None
    except Exception as e:
        return str(e)


def enrich_recommendations(recs: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Join recommendations with company features for display."""
    join_cols = [
        "identifiant_unique", "fr_denomination", "ar_denomination",
        "fr_nom_commercial", "fr_activite_principale",
        "category", "company_size", "capital_tier", "maturity", "city",
        "callable_prospect", "digital_signal", "mobility_signal",
        "multisite_signal", "governorate",
    ]
    available = [c for c in join_cols if c in feats.columns]
    return recs.merge(
        feats[available].drop_duplicates(subset=["identifiant_unique"]),
        on="identifiant_unique",
        how="left",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _esc(text) -> str:
    s = str(text) if text is not None else ""
    if s.lower() in ("nan", "none", ""):
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_rtl(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in str(text))


def _display_name(row) -> str:
    """Resolve best name: FR denomination → Arabic → commercial name → '—'."""
    for col in ("fr_denomination", "ar_denomination", "fr_nom_commercial"):
        val = str(row.get(col, "")).strip()
        if val and val.lower() not in ("nan", "none", ""):
            return val
    return "—"


def _score_color(score: float) -> str:
    if score >= 0.60:
        return RED
    if score >= 0.40:
        return "#E0A24C"
    return MUTED


def _category_badge(cat: str) -> str:
    key = str(cat).strip()
    if not key or key.lower() in ("nan", "none"):
        return f'<span style="color:{MUTED};">—</span>'
    color = CATEGORY_COLORS.get(key, "#7286A6")
    label = CATEGORY_LABELS.get(key, key)
    return (f'<span class="rec-badge" style="background:{color}1a;border:1px solid {color}44;">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{color};"></span>'
            f'{_esc(label)}</span>')


def _family_badge(family: str) -> str:
    key = str(family).strip()
    if not key or key.lower() in ("nan", "none"):
        return ""
    color = FAMILY_COLORS.get(key, "#7286A6")
    label = FAMILY_LABELS.get(key, key)
    return (f'<span class="rec-fam" style="background:{color}1a;border:1px solid {color}44;'
            f'color:{color};">{_esc(label)}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Table renderer — returns ONE single-line HTML string (no leading whitespace)
# ─────────────────────────────────────────────────────────────────────────────

def render_recommendation_table(rows: pd.DataFrame) -> str:
    headers = ["RNE ID", "Company", "Sector", "Top offer", "Family", "Score", "City"]
    header_html = "".join(f"<th>{h}</th>" for h in headers)

    body_parts = []
    for _, r in rows.iterrows():
        rne_id     = _esc(r.get("identifiant_unique", ""))
        name       = _display_name(r)
        name_esc   = _esc(name)
        category   = str(r.get("category", "")).strip()
        offer_name = _esc(r.get("offer_name", ""))
        family     = str(r.get("family", "")).strip()
        score      = float(r.get("final_score", 0))
        city       = _esc(r.get("city", ""))

        name_dir = "rtl" if _is_rtl(name) else "ltr"
        bar_color = _score_color(score)
        score_pct = min(100, max(0, score * 100))
        city_disp = city if city and city.lower() not in ("unknown", "other", "nan") else "—"

        score_cell = (
            f'<div style="display:flex;align-items:center;gap:0.4rem;min-width:120px;">'
            f'<div class="rec-track"><div style="width:{score_pct:.0f}%;height:100%;'
            f'border-radius:3px;background:{bar_color};"></div></div>'
            f'<span class="rec-score-n">{score:.2f}</span></div>'
        )

        row_html = (
            "<tr>"
            f'<td><span class="rec-id">{rne_id}</span></td>'
            f'<td><span class="rec-name" dir="{name_dir}" title="{name_esc}">{name_esc}</span></td>'
            f"<td>{_category_badge(category)}</td>"
            f'<td><span class="rec-offer">{offer_name}</span></td>'
            f"<td>{_family_badge(family)}</td>"
            f"<td>{score_cell}</td>"
            f'<td><span class="rec-city">{city_disp}</span></td>'
            "</tr>"
        )
        body_parts.append(row_html)

    body_html = "".join(body_parts)
    return (
        '<div class="rec-table-wrap on-reveal">'
        '<table class="rec-table">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Company deep-dive card — returns ONE single-line HTML string
# ─────────────────────────────────────────────────────────────────────────────

def _score_bar(score: float, color: str) -> str:
    pct = min(100, max(0, score * 100))
    return (
        f'<div style="display:flex;align-items:center;gap:0.5rem;">'
        f'<div style="flex:1;background:{NAVY};border-radius:4px;height:7px;'
        f'overflow:hidden;min-width:60px;">'
        f'<div style="width:{pct:.0f}%;height:100%;border-radius:4px;background:{color};"></div>'
        f'</div>'
        f'<span style="color:{WHITE};font-size:0.9rem;font-weight:700;'
        f'min-width:34px;text-align:right;">{score:.2f}</span></div>'
    )


def _mini_bar(score: float, color: str, label: str) -> str:
    pct = min(100, max(0, score * 100))
    return (
        f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:4px;">'
        f'<span style="color:{color};font-size:0.72rem;width:54px;text-align:right;">{label}</span>'
        f'<div style="flex:1;background:{NAVY};border-radius:3px;height:4px;overflow:hidden;">'
        f'<div style="width:{pct:.0f}%;height:100%;border-radius:3px;background:{color};"></div></div>'
        f'<span style="color:{MUTED};font-size:0.72rem;width:28px;">{score:.2f}</span></div>'
    )


def _confidence_label(score: float) -> tuple[str, str]:
    """Return (label, color) describing the strength of the top match."""
    if score >= 0.60:
        return "Strong match", SUCCESS
    if score >= 0.45:
        return "Good match", "#E0A24C"
    if score >= 0.30:
        return "Possible fit", "#5B8FE0"
    return "Weak signal", MUTED


def render_company_header(company_id: str, feats_row: dict, top_score: float) -> str:
    name     = _display_name(feats_row)
    name_esc = _esc(name)
    activity = _esc(feats_row.get("fr_activite_principale", ""))
    category = str(feats_row.get("category", "")).strip()
    size     = _esc(feats_row.get("company_size", ""))
    city     = _esc(feats_row.get("city", ""))
    maturity = _esc(feats_row.get("maturity", ""))
    rne_id   = _esc(company_id)
    name_dir = "rtl" if _is_rtl(name) else "ltr"

    conf_label, conf_color = _confidence_label(top_score)

    meta = []
    if size and size.lower() not in ("nan", "unknown"):
        meta.append(size)
    if city and city.lower() not in ("nan", "unknown", "other"):
        meta.append(city)
    if maturity and maturity.lower() not in ("nan", "unknown"):
        meta.append(maturity)
    meta_line = " · ".join(meta) if meta else ""

    conf_pill = (
        f'<span style="display:inline-flex;align-items:center;gap:0.35rem;'
        f'background:{conf_color}1a;border:1px solid {conf_color}55;color:{conf_color};'
        f'border-radius:999px;padding:0.2rem 0.7rem;font-size:0.78rem;font-weight:600;">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{conf_color};"></span>'
        f'{conf_label}</span>'
    )

    return (
        f'<div style="margin-bottom:1.2rem;padding-bottom:1rem;'
        f'border-bottom:1px solid {NAVY_HAIRLINE};">'
        f'<div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;margin-bottom:0.4rem;">'
        f'{_category_badge(category)}'
        f'<span style="font-size:1.2rem;font-weight:700;color:{WHITE};" dir="{name_dir}">{name_esc}</span>'
        f'{conf_pill}</div>'
        f'<div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">'
        f'<span style="color:{MUTED};font-size:0.82rem;font-family:monospace;">{rne_id}</span>'
        f'<span style="color:{MUTED};">·</span>'
        f'<span style="color:{MUTED};font-size:0.82rem;">{meta_line}</span></div>'
        f'<div style="color:{OFF_WHITE};font-size:0.86rem;margin-top:0.4rem;max-width:640px;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{activity}">'
        f'{activity if activity else "—"}</div></div>'
    )


def render_offer_card(rec: dict) -> str:
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

    rank_colors = {1: RED, 2: "#5B8FE0", 3: MUTED}
    rank_color = rank_colors.get(rank, MUTED)

    reasons = []
    if rule_reasons:
        first = rule_reasons.split(" | ")[0]
        reasons.append(
            f'<div style="color:{OFF_WHITE};font-size:0.8rem;line-height:1.5;">'
            f'<span style="color:#5B8FE0;font-weight:600;">Why:</span> {first}</div>'
        )
    if why_matched and why_matched.lower() not in ("", "nan", "semantic match"):
        reasons.append(
            f'<div style="color:{OFF_WHITE};font-size:0.8rem;line-height:1.5;">'
            f'<span style="color:#37C2A0;font-weight:600;">Match:</span> {why_matched}</div>'
        )
    if collab_src and collab_src.lower() not in ("none", "nan", ""):
        clean = collab_src.replace("category:", "").replace("segment:", "")
        reasons.append(
            f'<div style="color:{OFF_WHITE};font-size:0.8rem;line-height:1.5;">'
            f'<span style="color:#E0A24C;font-weight:600;">Similar to:</span> {clean}</div>'
        )
    reasons_html = "".join(reasons) if reasons else (
        f'<span style="color:{MUTED};font-size:0.8rem;">Semantic match</span>'
    )

    accent = f"border-left:3px solid {rank_color};" if rank == 1 else ""

    return (
        f'<div style="background:rgba(10,27,56,0.5);border:1px solid {NAVY_HAIRLINE};'
        f'border-radius:12px;padding:1.1rem;flex:1;min-width:215px;{accent}">'
        f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.7rem;flex-wrap:wrap;">'
        f'<span style="color:{rank_color};font-weight:800;font-size:1rem;">#{rank}</span>'
        f'{_family_badge(family)}'
        f'<span style="color:{WHITE};font-weight:600;font-size:0.95rem;">{offer_name}</span></div>'
        f'{_score_bar(final_score, rank_color)}'
        f'<div style="margin-top:0.7rem;">'
        f'{_mini_bar(rule_score, "#5B8FE0", "Rules")}'
        f'{_mini_bar(content_score, "#37C2A0", "Content")}'
        f'{_mini_bar(collab_score, "#E0A24C", "Peers")}</div>'
        f'<div style="margin-top:0.7rem;border-top:1px solid {NAVY_HAIRLINE};padding-top:0.6rem;">'
        f'{reasons_html}</div></div>'
    )


def render_company_card(company_id: str, comp_recs: pd.DataFrame, feats_row: dict) -> str:
    ordered = comp_recs.sort_values("rank")
    top_score = float(ordered.iloc[0]["final_score"]) if len(ordered) else 0.0

    header = render_company_header(company_id, feats_row, top_score)
    cards = "".join(render_offer_card(rec) for rec in ordered.to_dict("records"))

    return (
        f'<div class="on-card on-reveal" style="margin-bottom:1rem;">'
        f'{header}'
        f'<div style="display:flex;gap:0.8rem;flex-wrap:wrap;">{cards}</div></div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

page_title("Commercial Prospects", "AI-powered recommendations for every company.")

recs_df  = load_recommendations()
feats_df = load_features()

st.session_state.setdefault("auto_generate_attempted", False)
st.session_state.setdefault("auto_generate_error", None)

if (recs_df is None or feats_df is None) and not st.session_state.auto_generate_attempted:
    st.session_state.auto_generate_attempted = True

    if feats_df is None:
        with st.status(
            "No data found yet — running the full pipeline "
            "(extraction + segmentation + recommendations). This can take a while…",
            expanded=True,
        ) as status:
            error = _generate_full_pipeline()
            if error is None:
                status.update(label="Pipeline complete.", state="complete")
            else:
                status.update(label=f"Pipeline failed: {error}", state="error")
    else:
        with st.status("Generating recommendations…", expanded=True) as status:
            error = _generate_recommendations_only()
            if error is None:
                status.update(label="Recommendations generated.", state="complete")
            else:
                status.update(label=f"Recommendation generation failed: {error}", state="error")

    st.session_state.auto_generate_error = error
    if error is None:
        load_recommendations.clear()
        load_features.clear()
        st.rerun()

recs_df  = load_recommendations()
feats_df = load_features()

if recs_df is None or feats_df is None:
    st.markdown(
        f'<div class="on-card on-reveal" style="text-align:center;margin-top:1.4rem;">'
        f'<p style="color:{OFF_WHITE};font-size:1.05rem;margin:0 0 0.6rem 0;">'
        f'{"Recommendations have not been generated yet." if recs_df is None else "Company features file not found."}'
        f'</p>'
        + (
            f'<p style="color:{RED};font-size:0.88rem;margin:0.4rem 0;">'
            f'Automatic generation failed: {_esc(st.session_state.auto_generate_error)}</p>'
            if st.session_state.auto_generate_error else ""
        )
        + f'<p style="color:{MUTED};font-size:0.92rem;margin:0.4rem 0 0.2rem 0;">'
        f'Or run the pipeline manually:</p>'
        f'<code style="color:{RED_SOFT};font-size:0.88rem;">python run.py --from-db --recommend</code>'
        f'<p style="color:{MUTED};font-size:0.85rem;margin:0.6rem 0 0 0;">'
        f'or separately: <code style="color:{RED_SOFT};">python -m recommendation.main</code></p></div>',
        unsafe_allow_html=True,
    )
    if st.button("Retry now"):
        st.session_state.auto_generate_attempted = False
        st.session_state.auto_generate_error = None
        st.rerun()
    show_fixed_logo()
    st.stop()

recs = enrich_recommendations(recs_df, feats_df)


# ── SECTION 1 — KPIs ─────────────────────────────────────────────────────────
top1 = recs[recs["rank"] == 1].copy()
n_companies      = top1["identifiant_unique"].nunique()
n_offers_in_play = top1["offer_id"].nunique()
avg_score        = top1["final_score"].mean()
strong_matches   = int((top1["final_score"] >= 0.50).sum())
hot_leads        = int((top1["final_score"] >= 0.70).sum())

# Toggle state for the "Strongest leads" drill-down
st.session_state.setdefault("show_hot_leads", False)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Companies analyzed", f"{n_companies:,}")
c2.metric("Offers in play",     f"{n_offers_in_play}")
c3.metric("Avg match score",    f"{avg_score:.2f}")
c4.metric("Strong matches (≥0.5)", f"{strong_matches:,}")

# Clickable "Strongest leads" KPI — styled to match st.metric visually,
# but rendered as a real button so it can toggle the drill-down.
with c5:
    is_open = st.session_state.show_hot_leads
    accent = SUCCESS if is_open else RED
    chevron = "▾" if is_open else "▸"
    st.markdown(
        f'<div style="background:linear-gradient(160deg,{NAVY_LIGHT} 0%,rgba(16,37,68,0.55) 100%);'
        f'border:1px solid {NAVY_HAIRLINE};border-left:3px solid {accent};border-radius:14px;'
        f'padding:1.05rem 1.15rem;box-shadow:0 4px 14px rgba(0,0,0,0.18);'
        f'height:100%;position:relative;">'
        f'<div style="color:{MUTED};font-size:0.82rem;text-transform:uppercase;'
        f'letter-spacing:0.06em;">Strongest leads (≥0.7)</div>'
        f'<div style="color:{WHITE};font-weight:700;font-size:1.75rem;line-height:1.25;'
        f'margin-top:0.15rem;">{hot_leads:,}</div>'
        f'<div style="color:{accent};font-size:0.78rem;font-weight:600;margin-top:0.2rem;">'
        f'{chevron} {"Hide list" if is_open else "View list"}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button(
        "Hide strongest leads" if is_open else "View strongest leads",
        key="toggle_hot_leads",
        use_container_width=True,
    ):
        st.session_state.show_hot_leads = not st.session_state.show_hot_leads
        st.rerun()

# ── Drill-down: strongest leads (sector breakdown + table) ───────────────────
if st.session_state.show_hot_leads:
    hot_df = top1[top1["final_score"] >= 0.70].sort_values(
        "final_score", ascending=False,
    )
    st.markdown("<div style='height:1.2vh;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.6rem;'
        f'margin-bottom:0.5rem;">'
        f'<span style="color:{SUCCESS};font-size:0.78rem;font-weight:700;'
        f'letter-spacing:0.14em;text-transform:uppercase;">Strongest leads</span>'
        f'<span style="color:{MUTED};font-size:0.85rem;">'
        f'{len(hot_df):,} companies with a match score ≥ 0.70, '
        f'ranked highest first.</span></div>',
        unsafe_allow_html=True,
    )
    if len(hot_df) == 0:
        st.markdown(
            f"<div class='on-card' style='text-align:center;'>"
            f"<p style='color:{MUTED};margin:0;'>No companies reached the 0.70 threshold. "
            f"The strongest opportunities are in the table below.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        # ── Sector breakdown: where are the strongest leads concentrated? ──
        st.markdown(
            f"<h4 style='color:{WHITE};margin:0.8rem 0 0.2rem 0;'>By sector</h4>"
            f"<p style='color:{MUTED};font-size:0.86rem;margin-top:0;'>"
            f"Where the strongest leads sit. Hover a bar to see the "
            f"concentration rate (share of the sector that scored ≥ 0.70).</p>",
            unsafe_allow_html=True,
        )
        strongest_by_sector_chart(recs, threshold=0.70)

        # ── The ranked list of strongest leads ─────────────────────────────
        st.markdown(
            f"<h4 style='color:{WHITE};margin:1rem 0 0.2rem 0;'>"
            f"Ranked list</h4>",
            unsafe_allow_html=True,
        )

        # Cap at 100 rows so a huge cohort doesn't blow up the page.
        HOT_LIMIT = 100
        display_rows = hot_df.head(HOT_LIMIT)
        st.markdown(
            render_recommendation_table(display_rows),
            unsafe_allow_html=True,
        )
        if len(hot_df) > HOT_LIMIT:
            st.markdown(
                f"<p style='color:{MUTED};font-size:0.85rem;margin-top:0.4rem;'>"
                f"Showing the top {HOT_LIMIT} of {len(hot_df):,}. "
                f"Use the explorer below to browse the rest.</p>",
                unsafe_allow_html=True,
            )
        # Download button for the sales team
        csv_hot = hot_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            f"Download strongest leads ({len(hot_df):,} companies)",
            data=csv_hot,
            file_name="strongest_leads.csv",
            mime="text/csv",
        )

section_divider()


# ── SECTION 2 — What to lead with ────────────────────────────────────────────
eyebrow("What to lead with")

cc1, cc2 = st.columns([3, 2], gap="large")
with cc1:
    st.markdown(
        f"<h4 style='color:{WHITE};margin-top:0;'>Top recommended offers</h4>"
        f"<p style='color:{MUTED};font-size:0.88rem;margin-top:0;'>"
        f"Which offers appear most as the #1 recommendation.</p>",
        unsafe_allow_html=True,
    )
    recommendation_top_offers_chart(recs)
with cc2:
    st.markdown(
        f"<h4 style='color:{WHITE};margin-top:0;'>By offer family</h4>"
        f"<p style='color:{MUTED};font-size:0.88rem;margin-top:0;'>"
        f"Product families across all top picks.</p>",
        unsafe_allow_html=True,
    )
    family_donut_chart(recs)

section_divider()


# ── SECTION 3 — Recommendation explorer ──────────────────────────────────────
eyebrow("Recommendation explorer")
st.markdown(
    f"<h4 style='color:{WHITE};margin-top:0;'>Browse all recommendations</h4>",
    unsafe_allow_html=True,
)

f1, f2, f3 = st.columns(3)
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
    search_q = st.text_input(
        "Search by name or RNE ID", "", key="rec_search",
        placeholder="Company name or RNE ID…",
    )

label_to_cat = {CATEGORY_LABELS.get(c, c): c for c in
                (recs["category"].dropna().unique() if "category" in recs.columns else [])}
label_to_fam = {FAMILY_LABELS.get(f, f): f for f in
                (recs["family"].dropna().unique() if "family" in recs.columns else [])}

filtered_top1 = top1.copy()
if selected_sector != "All sectors":
    filtered_top1 = filtered_top1[filtered_top1["category"] == label_to_cat.get(selected_sector, selected_sector)]
if selected_family != "All families":
    filtered_top1 = filtered_top1[filtered_top1["family"] == label_to_fam.get(selected_family, selected_family)]
if search_q.strip():
    q = search_q.strip().lower()
    scols = ["fr_denomination", "ar_denomination", "fr_nom_commercial", "identifiant_unique"]
    mask = pd.Series(False, index=filtered_top1.index)
    for col in scols:
        if col in filtered_top1.columns:
            mask = mask | filtered_top1[col].astype(str).str.lower().str.contains(q, na=False, regex=False)
    filtered_top1 = filtered_top1[mask]

n_filtered = len(filtered_top1)
PAGE_SIZE_DEFAULT = 25

pcol1, pcol2 = st.columns([3, 1])
with pcol1:
    st.markdown(
        f"<p style='color:{OFF_WHITE};margin-bottom:0.3rem;'>"
        f"<b>{n_filtered:,}</b> companies matched.</p>",
        unsafe_allow_html=True,
    )
with pcol2:
    page_size = st.selectbox("Per page", [10, 25, 50, 100],
                             index=[10, 25, 50, 100].index(PAGE_SIZE_DEFAULT),
                             key="rec_page_size")

total_pages = max(1, (n_filtered + page_size - 1) // page_size)
st.session_state.setdefault("rec_page", 1)
if st.session_state.rec_page > total_pages:
    st.session_state.rec_page = 1

page = st.session_state.rec_page
start = (page - 1) * page_size
page_rows = filtered_top1.iloc[start:start + page_size]

if n_filtered == 0:
    st.markdown(
        f"<div class='on-card' style='text-align:center;'>"
        f"<p style='color:{MUTED};margin:0;'>No companies match your search.</p></div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(render_recommendation_table(page_rows), unsafe_allow_html=True)

def _go_first(): st.session_state.rec_page = 1
def _go_prev():  st.session_state.rec_page = max(1, st.session_state.rec_page - 1)
def _go_next():  st.session_state.rec_page = min(total_pages, st.session_state.rec_page + 1)
def _go_last():  st.session_state.rec_page = total_pages

st.markdown("<div style='height:0.4vh;'></div>", unsafe_allow_html=True)
p1, p2, p3, p4, p5 = st.columns([1, 1, 2, 1, 1])
with p1: st.button("« First", on_click=_go_first, disabled=(page <= 1), use_container_width=True, key="rec_first")
with p2: st.button("‹ Prev",  on_click=_go_prev,  disabled=(page <= 1), use_container_width=True, key="rec_prev")
with p3:
    st.markdown(
        f"<p style='text-align:center;color:{MUTED};margin-top:0.5rem;'>"
        f"Page <b>{page}</b> of <b>{total_pages}</b></p>",
        unsafe_allow_html=True,
    )
with p4: st.button("Next ›",  on_click=_go_next,  disabled=(page >= total_pages), use_container_width=True, key="rec_next")
with p5: st.button("Last »",  on_click=_go_last,  disabled=(page >= total_pages), use_container_width=True, key="rec_last")

section_divider()


# ── SECTION 4 — Company deep-dive ────────────────────────────────────────────
eyebrow("Company deep-dive")
st.markdown(
    f"<h4 style='color:{WHITE};margin-top:0;'>Recommendation card</h4>"
    f"<p style='color:{MUTED};font-size:0.88rem;margin-top:0;'>"
    f"Enter a company RNE ID to see its three recommended offers with "
    f"score breakdowns and plain-language reasons.</p>",
    unsafe_allow_html=True,
)

rne_input = st.text_input(
    "RNE ID", "", key="rec_rne_input",
    placeholder="e.g. 1592574J, A183321996…",
    label_visibility="collapsed",
)

if rne_input.strip():
    lookup_id = rne_input.strip()
    comp_recs = recs[recs["identifiant_unique"].astype(str) == lookup_id]

    if comp_recs.empty:
        mask = recs["identifiant_unique"].astype(str).str.contains(
            lookup_id, case=False, na=False, regex=False
        )
        matches = recs[mask]["identifiant_unique"].unique()

        if len(matches) == 0:
            st.markdown(
                f"<div class='on-card' style='text-align:center;'>"
                f"<p style='color:{MUTED};margin:0;'>No company found for "
                f"<b>{_esc(lookup_id)}</b>. Check the ID and try again.</p></div>",
                unsafe_allow_html=True,
            )
        elif len(matches) <= 6:
            sugg = [f"<p style='color:{OFF_WHITE};font-size:0.9rem;'>Did you mean one of these?</p>"]
            for mid in matches:
                fm = feats_df[feats_df["identifiant_unique"] == mid]
                dn = _display_name(fm.iloc[0].to_dict()) if len(fm) else "—"
                sugg.append(
                    f"<p style='color:{OFF_WHITE};font-size:0.9rem;margin:0.2rem 0;'>"
                    f"<code style='color:{RED_SOFT};'>{_esc(mid)}</code> — {_esc(dn)}</p>"
                )
            st.markdown("".join(sugg), unsafe_allow_html=True)
        else:
            st.markdown(
                f"<p style='color:{MUTED};'>{len(matches)} partial matches. "
                f"Try a more specific ID.</p>",
                unsafe_allow_html=True,
            )
    else:
        actual_id = comp_recs.iloc[0]["identifiant_unique"]
        fm = feats_df[feats_df["identifiant_unique"] == actual_id]
        feat_row = fm.iloc[0].to_dict() if len(fm) else {}
        st.markdown(
            render_company_card(actual_id, comp_recs, feat_row),
            unsafe_allow_html=True,
        )

section_divider()


# ── SECTION 5 — Downloads ────────────────────────────────────────────────────
eyebrow("Export")

d1, d2 = st.columns(2)
with d1:
    csv_full = recs_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "Download all recommendations (CSV)",
        data=csv_full, file_name="recommendations_raw.csv",
        mime="text/csv", use_container_width=True,
    )
with d2:
    if n_filtered > 0:
        csv_filtered = filtered_top1.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            f"Download filtered view ({n_filtered:,} companies)",
            data=csv_filtered, file_name="recommendations_filtered.csv",
            mime="text/csv", use_container_width=True,
        )

show_fixed_logo()
