"""
app/components/branding.py
==========================
Reusable branding components: logo display, page headers, hero, SVG accents,
and the contextual sidebar companion.

Used across all pages so branding stays consistent.
"""

import base64
from pathlib import Path

import streamlit as st

from app.theme import (
    LOGO_PATH, RED, RED_SOFT, WHITE, OFF_WHITE, MUTED,
    NAVY, NAVY_LIGHT, NAVY_LIGHTER, NAVY_HAIRLINE, SUCCESS,
)


# ──────────────────────────────────────────────────────────────────────────────
# Logo loading
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data
def _load_logo_base64() -> str | None:
    """Read the logo file and return it as a base64 string for inline HTML."""
    path = Path(LOGO_PATH)
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


def show_fixed_logo(width: int = 138):
    """Display the Ooredoo Business logo fixed at the bottom-right of the screen."""
    logo_b64 = _load_logo_base64()
    if logo_b64 is None:
        return
    st.markdown(
        f"""
        <div class="ooredoo-logo-fixed">
            <img src="data:image/png;base64,{logo_b64}" width="{width}" alt="Ooredoo Business" />
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_logo_centered(width: int = 230):
    """Display the logo centered (used on the home page)."""
    logo_b64 = _load_logo_base64()
    if logo_b64 is None:
        st.warning(f"Logo not found at {LOGO_PATH}")
        return
    st.markdown(
        f"""
        <div style="text-align:center; margin: 1.2rem 0 0.4rem 0;">
            <img src="data:image/png;base64,{logo_b64}" width="{width}" alt="Ooredoo Business" />
        </div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# SVG decorative accents
# ──────────────────────────────────────────────────────────────────────────────

def _signal_mark_svg(size: int = 46) -> str:
    """
    A small bespoke 'signal / navigator' mark in Ooredoo red — three rising
    connectivity arcs over a base node. Used as a page eyebrow accent.
    Returns raw SVG markup (no Streamlit call).
    """
    return f"""
    <svg width="{size}" height="{size}" viewBox="0 0 48 48" fill="none"
         xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Opportunity Navigator">
        <circle cx="24" cy="36" r="4" fill="{RED}"/>
        <path d="M14 30 A14 14 0 0 1 34 30" stroke="{RED}" stroke-width="3"
              stroke-linecap="round" fill="none" opacity="0.9"/>
        <path d="M9 25 A21 21 0 0 1 39 25" stroke="{RED_SOFT}" stroke-width="2.6"
              stroke-linecap="round" fill="none" opacity="0.6"/>
        <path d="M4 20 A28 28 0 0 1 44 20" stroke="{RED_SOFT}" stroke-width="2.2"
              stroke-linecap="round" fill="none" opacity="0.32"/>
    </svg>
    """


def hero(title_lead: str, title_accent: str, subtitle: str):
    """
    Page hero: bespoke signal mark + two-tone title + subtitle.
    The accent word is rendered in Ooredoo red.
    """
    st.markdown(
        f"""
        <div class="on-reveal" style="display:flex; align-items:center; gap:1rem; margin-bottom:0.4rem;">
            <div style="flex-shrink:0;">{_signal_mark_svg(52)}</div>
            <div>
                <h1 style="color:{WHITE}; font-size:2.7rem; font-weight:800;
                           line-height:1.05; margin:0;">
                    {title_lead} <span style="color:{RED};">{title_accent}</span>
                </h1>
            </div>
        </div>
        <p class="on-reveal" style="color:{OFF_WHITE}; font-size:1.15rem; line-height:1.6;
                  max-width:680px; margin:0 0 0.4rem 0;">
            {subtitle}
        </p>
        """,
        unsafe_allow_html=True,
    )


def page_title(title: str, subtitle: str | None = None):
    """Render a consistent page title with optional subtitle and accent mark."""
    st.markdown(
        f"""
        <div class="on-reveal" style="display:flex; align-items:center; gap:0.8rem; margin-bottom:0.15rem;">
            <div style="flex-shrink:0;">{_signal_mark_svg(40)}</div>
            <h1 style="color:{WHITE}; font-weight:800; font-size:2.1rem; margin:0;">{title}</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f"""<p class="on-reveal" style="color:{MUTED}; font-size:1.05rem;
                   margin:0 0 0.6rem 3.6rem;">{subtitle}</p>""",
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Contextual sidebar companion
# ──────────────────────────────────────────────────────────────────────────────

def _chip(active: bool, label: str) -> str:
    dot = "on-dot-on" if active else "on-dot-off"
    color = SUCCESS if active else MUTED
    return (
        f'<div class="on-context-chip">'
        f'<span class="on-dot {dot}"></span>'
        f'<span style="color:{OFF_WHITE};">{label}</span>'
        f'</div>'
    )


def brand_header():
    """
    The sticky brand block — 'Opportunity Navigator' + 'Ooredoo Business'.

    Call this ONCE from the router (app/dashboard.py), BEFORE st.navigation(...)
    is created and run. Streamlit renders sidebar content in the order it is
    called: anything written to st.sidebar before st.navigation(...).run()
    appears ABOVE the nav menu; anything written by a page afterward appears
    BELOW it. That ordering is how this block stays above the menu while the
    workspace chips (rendered per-page via sidebar_context) stay below it.

    The block itself uses `position: sticky` so it stays pinned to the top of
    the sidebar even as the menu/workspace content below it scrolls.
    """
    with st.sidebar:
        st.markdown(
            f"""
            <div class="on-brand-sticky">
                <div style="color:{WHITE}; font-size:1.02rem; font-weight:800;
                            letter-spacing:0.01em; line-height:1.15;">
                    Opportunity <span style="color:{RED};">Navigator</span>
                </div>
                <div style="color:{MUTED}; font-size:0.72rem; letter-spacing:0.14em;
                            text-transform:uppercase; margin-top:0.15rem;">
                    Ooredoo Business
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def sidebar_context():
    """
    Render the workspace status chips below the nav menu.

    Call this from each page (after the router has already placed the brand
    header and the nav menu). Reads:
        - data/output/rne_companies_segmented.csv existence + row count
        - data/output/commercial_prospects.csv existence + row count
    """
    seg_path  = Path("data/output/rne_companies_segmented.csv")
    pros_path = Path("data/output/commercial_prospects.csv")

    seg_rows = None
    pros_rows = None
    try:
        if seg_path.exists():
            seg_rows = sum(1 for _ in open(seg_path, encoding="utf-8-sig")) - 1
    except OSError:
        seg_rows = None
    try:
        if pros_path.exists():
            pros_rows = sum(1 for _ in open(pros_path, encoding="utf-8-sig")) - 1
    except OSError:
        pros_rows = None

    with st.sidebar:
        st.markdown(
            f'<div class="on-eyebrow" style="margin-top:0.9rem;">Workspace</div>',
            unsafe_allow_html=True,
        )

        seg_label = (
            f"{seg_rows:,} companies classified"
            if seg_rows is not None else "No data imported yet"
        )
        pros_label = (
            f"{pros_rows:,} prospects ready"
            if pros_rows is not None else "Prospects not built yet"
        )

        st.markdown(
            _chip(seg_rows is not None, seg_label) + _chip(pros_rows is not None, pros_label),
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Small building blocks reused across pages
# ──────────────────────────────────────────────────────────────────────────────

def eyebrow(text: str):
    """A small uppercase red eyebrow label above a section."""
    st.markdown(f'<div class="on-eyebrow">{text}</div>', unsafe_allow_html=True)


def step_marker(index: int, total: int, label: str, done: bool = False):
    """
    A subtle progress marker for progressive-disclosure flows.
    Reads as 'where am I' context, not a rigid Step 1/2/3 form.
    """
    dot_color = SUCCESS if done else RED
    pips = ""
    for i in range(total):
        c = dot_color if (i <= index - 1) else NAVY_LIGHTER
        pips += f'<span style="width:22px;height:3px;border-radius:2px;background:{c};display:inline-block;margin-right:4px;"></span>'
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.7rem;margin:0.2rem 0 0.5rem 0;">
            <div>{pips}</div>
            <span style="color:{MUTED};font-size:0.85rem;">{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
