"""
app/pages/home.py
=================
Home — the landing page of Opportunity Navigator.

Body script only (the router in app/dashboard.py owns page config and nav).
No centered logo; the Ooredoo logo lives in the footer and stays visible on scroll.
"""

import streamlit as st

from app.theme import (
    inject_global_css, section_divider,
    WHITE, RED, RED_SOFT, MUTED, OFF_WHITE, NAVY_LIGHT, NAVY_HAIRLINE, SUCCESS,
    CATEGORY_COLORS,
)
from app.components.branding import (
    show_fixed_logo, sidebar_context, hero, eyebrow,
)

inject_global_css()
sidebar_context()


# ── Hero (no centered logo — footer only) ─────────────────────────────────────
st.markdown("<div style='height:2vh;'></div>", unsafe_allow_html=True)

hero(
    "Opportunity",
    "Navigator",
    "Turn official company records into ready-to-call opportunities. "
    "Import, classify, and explore your market in minutes.",
)

section_divider()


# ── What it does — three quiet capability cards ───────────────────────────────
eyebrow("What it does")

CARDS = [
    {
        "mark": "M3 16 L9 9 L13 13 L21 5",
        "title": "Import & classify",
        "body": "Bring in RNE documents. Every company is read and sorted into its "
                "business sector automatically.",
    },
    {
        "mark": "M4 18 L10 18 L10 10 L16 10 L16 4 L20 4",
        "title": "Explore your market",
        "body": "See the full picture with clear charts and filters, and spot the "
                "companies worth a closer look.",
    },
    {
        "mark": "M5 12 L11 12 M11 12 L9 9 M11 12 L9 15 M13 6 L19 6 M13 18 L19 18",
        "title": "Reach the right prospects",
        "body": "Get a clean, call-ready directory of companies with the details your "
                "team needs to act.",
    },
]


def _card(mark: str, title: str, body: str) -> str:
    return f"""
    <div class="on-card on-reveal" style="height:208px;">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
             xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="{mark}" stroke="{RED}" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <h3 style="color:{WHITE}; margin:0.7rem 0 0.4rem 0; font-size:1.22rem;">{title}</h3>
        <p style="color:{MUTED}; font-size:0.96rem; line-height:1.55; margin:0;">{body}</p>
    </div>
    """


col1, col2, col3 = st.columns(3, gap="medium")
with col1:
    st.markdown(_card(**CARDS[0]), unsafe_allow_html=True)
with col2:
    st.markdown(_card(**CARDS[1]), unsafe_allow_html=True)
with col3:
    st.markdown(_card(**CARDS[2]), unsafe_allow_html=True)


# ── Sectors strip ─────────────────────────────────────────────────────────────
st.markdown("<div style='height:2.4vh;'></div>", unsafe_allow_html=True)
eyebrow("Eight sectors, one clear view")

SECTOR_LABELS = {
    "retail": "Retail", "manufacturing": "Manufacturing", "transport": "Transport",
    "tourism": "Tourism", "healthcare": "Healthcare", "education": "Education",
    "financial_services": "Financial services", "others": "Others",
}

pills = ""
for key, label in SECTOR_LABELS.items():
    color = CATEGORY_COLORS.get(key, "#7286A6")
    pills += (
        f'<span style="display:inline-flex; align-items:center; gap:0.5rem; '
        f'background:rgba(255,255,255,0.03); border:1px solid {NAVY_HAIRLINE}; '
        f'border-radius:999px; padding:0.4rem 0.9rem; margin:0.25rem; font-size:0.92rem; color:{OFF_WHITE};">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{color};"></span>{label}</span>'
    )

st.markdown(f'<div class="on-reveal" style="line-height:2.4;">{pills}</div>', unsafe_allow_html=True)


# ── Call to action — clickable, routes to Import data ─────────────────────────
st.markdown("<div style='height:2.6vh;'></div>", unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="on-card on-card-accent on-reveal" style="display:flex; align-items:center;
         justify-content:space-between; gap:1rem; flex-wrap:wrap; margin-bottom:0.8rem;">
        <div>
            <div style="color:{WHITE}; font-size:1.25rem; font-weight:700;">Start here</div>
            <div style="color:{OFF_WHITE}; font-size:0.98rem;">
                Upload your data and explore your commercial prospects.
            </div>
        </div>
        <div style="font-size:1.6rem;">→</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Native clickable button that routes to the Import data page
if st.button("Import your data  →", type="primary", key="home_cta"):
    st.switch_page("pages/import_data.py")

show_fixed_logo()
