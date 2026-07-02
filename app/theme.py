"""
app/theme.py
============
Single source of truth for the Opportunity Navigator visual identity.

Change a color here and it updates everywhere. Nothing else hardcodes colors.

This module also provides:
    - inject_global_css()      global dark-navy theme + animations + component styling
    - style_dataframe(df)      pandas Styler with alternating rows / formatting
    - section_divider()        soft SVG divider between sections
    - aurora_background()      ambient SVG glow injected once per page
"""

# ── Brand colors — refined, harmonized navy + Ooredoo red ─────────────────────
# The original palette is preserved in spirit but tuned so accents sit calmly
# on the navy instead of vibrating against it.
NAVY          = "#0A1B38"   # primary background (deep, slightly warmer navy)
NAVY_LIGHT    = "#102544"   # cards / panels
NAVY_LIGHTER  = "#1B3559"   # hover / borders
NAVY_HAIRLINE = "#24406B"   # subtle 1px separators
RED           = "#ED1C24"   # Ooredoo action accent (unchanged — brand-critical)
RED_SOFT      = "#F2484F"   # lighter red for hover / glows
WHITE         = "#FFFFFF"   # primary text
OFF_WHITE     = "#DCE5F2"   # secondary text (slightly cooler, less glare)
MUTED         = "#8499B8"   # captions / hints (warmer muted blue-grey)
SUCCESS       = "#2DD4A7"   # confirmations (teal, harmonized)
SUCCESS_DIM   = "#1A9B79"

# ── Category palette for charts — harmonized, lower-saturation nuances ─────────
# Re-tuned so all eight sit in the same tonal family against navy: nothing
# fluorescent, nothing muddy. Reds stay closest to the brand.
CATEGORY_COLORS = {
    "retail":             "#EF4B52",   # brand-adjacent coral-red
    "manufacturing":      "#E0A24C",   # warm amber, softened
    "transport":          "#5B8FE0",   # calm blue
    "tourism":            "#37C2A0",   # harmonized teal-green
    "healthcare":         "#E07CB0",   # softened pink
    "education":          "#9B89E6",   # softened violet
    "financial_services": "#3FB8B0",   # teal
    "others":             "#7286A6",   # muted slate-blue (matches MUTED family)
}

# ── Asset paths ───────────────────────────────────────────────────────────────
LOGO_PATH = "app/assets/ooredoo_business.png"


def inject_global_css():
    """
    Inject the global theme: dark navy surface, harmonized accents, component
    styling, animation keyframes, and progressive-disclosure helpers.
    Call this once at the top of each page.
    """
    import streamlit as st

    st.markdown(
        f"""
        <style>
        /* ============================================================
           Base surface
           ============================================================ */
        .stApp {{
            background-color: {NAVY};
            background-image:
                radial-gradient(1100px 520px at 12% -8%, rgba(237,28,36,0.10), transparent 60%),
                radial-gradient(900px 600px at 95% 8%, rgba(59,130,224,0.10), transparent 55%),
                radial-gradient(700px 700px at 50% 120%, rgba(45,212,167,0.06), transparent 60%);
            background-attachment: fixed;
            color: {WHITE};
        }}

        .stApp p, .stApp span, .stApp label,
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp li {{
            color: {WHITE};
        }}

        /* Constrain content width for readability on wide screens */
        .block-container {{
            max-width: 1180px;
            padding-top: 2.2rem;
            animation: on-fade-in 0.55s ease both;
        }}

        /* ============================================================
           Sidebar — "contextual companion" rather than a panel
           ============================================================ */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {NAVY_LIGHT} 0%, {NAVY} 100%);
            border-right: 1px solid {NAVY_HAIRLINE};
        }}
        section[data-testid="stSidebar"] * {{
            color: {OFF_WHITE};
        }}
        section[data-testid="stSidebar"] .block-container {{
            padding-top: 1.2rem;
        }}

        /* Sticky brand title — pinned to the top of the sidebar on scroll */
        .on-brand-sticky {{
            position: sticky;
            top: 0;
            z-index: 100;
            padding: 0.4rem 0 0.7rem 0;
            margin-bottom: 0.2rem;
            background: linear-gradient(180deg, {NAVY_LIGHT} 70%, rgba(16,37,68,0) 100%);
            border-bottom: 1px solid {NAVY_HAIRLINE};
        }}

        /* Sidebar nav links — quieter, pill on hover/active */
        section[data-testid="stSidebar"] a {{
            border-radius: 8px;
            transition: background-color 0.18s ease, color 0.18s ease;
        }}
        section[data-testid="stSidebar"] a:hover {{
            background-color: rgba(255,255,255,0.05);
        }}

        /* ============================================================
           Buttons
           ============================================================ */
        .stButton > button {{
            background: linear-gradient(135deg, {RED} 0%, #C7141B 100%);
            color: {WHITE};
            border: none;
            border-radius: 10px;
            padding: 0.62rem 1.5rem;
            font-weight: 600;
            font-size: 1rem;
            letter-spacing: 0.01em;
            box-shadow: 0 6px 18px rgba(237,28,36,0.22);
            transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
        }}
        .stButton > button:hover {{
            filter: brightness(1.06);
            transform: translateY(-2px);
            box-shadow: 0 10px 26px rgba(237,28,36,0.32);
            color: {WHITE};
        }}
        .stButton > button:active {{
            transform: translateY(0);
        }}
        .stButton > button:focus-visible {{
            outline: 2px solid {RED_SOFT};
            outline-offset: 2px;
        }}

        /* Download buttons — secondary, outlined */
        .stDownloadButton > button {{
            background-color: rgba(255,255,255,0.03);
            color: {OFF_WHITE};
            border: 1px solid {NAVY_LIGHTER};
            border-radius: 10px;
            font-weight: 500;
            transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.18s ease;
        }}
        .stDownloadButton > button:hover {{
            border-color: {RED};
            background-color: rgba(237,28,36,0.08);
            color: {WHITE};
            transform: translateY(-1px);
        }}

        /* ============================================================
           Metrics — soft cards
           ============================================================ */
        div[data-testid="stMetric"] {{
            background: linear-gradient(160deg, {NAVY_LIGHT} 0%, rgba(16,37,68,0.55) 100%);
            border: 1px solid {NAVY_HAIRLINE};
            border-radius: 14px;
            padding: 1.05rem 1.15rem;
            box-shadow: 0 4px 14px rgba(0,0,0,0.18);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        div[data-testid="stMetric"]:hover {{
            transform: translateY(-2px);
            border-color: {NAVY_LIGHTER};
        }}
        div[data-testid="stMetric"] label {{
            color: {MUTED} !important;
            font-size: 0.82rem !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        div[data-testid="stMetricValue"] {{
            color: {WHITE} !important;
            font-weight: 700;
        }}

        /* ============================================================
           Inputs — radio, selectbox, text, file uploader
           ============================================================ */
        section[data-testid="stFileUploaderDropzone"] {{
            background-color: {NAVY_LIGHT};
            border: 2px dashed {NAVY_LIGHTER};
            border-radius: 14px;
            transition: border-color 0.2s ease, background-color 0.2s ease;
        }}
        section[data-testid="stFileUploaderDropzone"]:hover {{
            border-color: {RED};
            background-color: rgba(237,28,36,0.05);
        }}

        div[data-baseweb="select"] > div {{
            background-color: {NAVY_LIGHT};
            border-color: {NAVY_LIGHTER};
            border-radius: 10px;
        }}
        .stTextInput input, .stNumberInput input {{
            background-color: {NAVY_LIGHT};
            color: {WHITE};
            border-radius: 10px;
            border: 1px solid {NAVY_LIGHTER};
        }}
        .stTextInput input:focus, .stNumberInput input:focus {{
            border-color: {RED};
            box-shadow: 0 0 0 2px rgba(237,28,36,0.20);
        }}

        /* Radio group as soft segmented control */
        div[role="radiogroup"] label {{
            background-color: {NAVY_LIGHT};
            border: 1px solid {NAVY_LIGHTER};
            border-radius: 10px;
            padding: 0.45rem 0.9rem;
            margin-right: 0.5rem;
            transition: border-color 0.18s ease, background-color 0.18s ease;
        }}
        div[role="radiogroup"] label:hover {{
            border-color: {RED};
        }}

        /* Expander */
        div[data-testid="stExpander"] {{
            border: 1px solid {NAVY_HAIRLINE};
            border-radius: 12px;
            background-color: rgba(16,37,68,0.45);
            overflow: hidden;
        }}

        /* ============================================================
           Tables / dataframes
           ============================================================ */
        .stDataFrame {{
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid {NAVY_HAIRLINE};
        }}

        /* ============================================================
           Alerts
           ============================================================ */
        div[data-testid="stAlert"] {{
            border-radius: 12px;
            border: 1px solid {NAVY_LIGHTER};
            background-color: {NAVY_LIGHT};
        }}

        /* ============================================================
           Progress bar — Ooredoo red fill
           ============================================================ */
        .stProgress > div > div > div > div {{
            background: linear-gradient(90deg, {RED} 0%, {RED_SOFT} 100%);
        }}

        /* ============================================================
           Hide Streamlit chrome
           ============================================================ */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header[data-testid="stHeader"] {{background: transparent;}}

        /* ============================================================
           Reusable layout helpers
           ============================================================ */
        .on-card {{
            background: linear-gradient(160deg, {NAVY_LIGHT} 0%, rgba(16,37,68,0.55) 100%);
            border: 1px solid {NAVY_HAIRLINE};
            border-radius: 16px;
            padding: 1.5rem 1.6rem;
            box-shadow: 0 6px 20px rgba(0,0,0,0.18);
        }}
        .on-card-accent {{
            border-left: 3px solid {RED};
        }}
        .on-eyebrow {{
            color: {RED_SOFT};
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }}
        .on-context-chip {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
            background-color: rgba(255,255,255,0.04);
            border: 1px solid {NAVY_HAIRLINE};
            border-radius: 10px;
            padding: 0.6rem 0.8rem;
            margin-bottom: 0.55rem;
            font-size: 0.9rem;
        }}
        .on-dot {{
            width: 8px; height: 8px; border-radius: 50%;
            flex-shrink: 0;
        }}
        .on-dot-on  {{ background-color: {SUCCESS}; box-shadow: 0 0 8px {SUCCESS}; }}
        .on-dot-off {{ background-color: {MUTED}; }}

        /* Fixed bottom-right logo */
        .ooredoo-logo-fixed {{
            position: fixed;
            bottom: 18px;
            right: 22px;
            z-index: 999;
            opacity: 0.9;
            animation: on-fade-in 1s ease both;
        }}

        /* ============================================================
           Animations
           ============================================================ */
        @keyframes on-fade-in {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes on-slide-in {{
            from {{ opacity: 0; transform: translateY(16px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        .on-reveal {{
            animation: on-slide-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
        }}

        @media (prefers-reduced-motion: reduce) {{
            .block-container, .on-reveal, .ooredoo-logo-fixed,
            .stButton > button, div[data-testid="stMetric"] {{
                animation: none !important;
                transition: none !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Table styling — pandas Styler for big sortable dataframes
# ──────────────────────────────────────────────────────────────────────────────

def style_dataframe(df, numeric_format: dict | None = None):
    """
    Return a pandas Styler with the navy theme: alternating rows, styled header,
    readable typography. Keeps st.dataframe sorting/scrolling intact.

    Args:
        df: the DataFrame to style
        numeric_format: optional {column: format_string} for number formatting,
                        e.g. {"capital": "{:,.0f}", "confidence": "{:.2f}"}
    """
    styler = df.style

    if numeric_format:
        valid = {c: f for c, f in numeric_format.items() if c in df.columns}
        if valid:
            styler = styler.format(valid)

    styler = styler.set_table_styles([
        {"selector": "thead th",
         "props": [
             ("background-color", NAVY_LIGHTER),
             ("color", WHITE),
             ("font-weight", "600"),
             ("text-transform", "uppercase"),
             ("font-size", "0.74rem"),
             ("letter-spacing", "0.05em"),
             ("padding", "10px 12px"),
             ("border", "none"),
         ]},
        {"selector": "tbody td",
         "props": [
             ("background-color", NAVY_LIGHT),
             ("color", OFF_WHITE),
             ("padding", "9px 12px"),
             ("border", "none"),
             ("border-bottom", f"1px solid {NAVY}"),
         ]},
        {"selector": "tbody tr:nth-child(even) td",
         "props": [("background-color", "rgba(27,53,89,0.35)")]},
        {"selector": "tbody tr:hover td",
         "props": [("background-color", "rgba(237,28,36,0.10)")]},
        {"selector": "",
         "props": [("border-collapse", "collapse"), ("border-radius", "12px"), ("overflow", "hidden")]},
    ])
    styler = styler.hide(axis="index")
    return styler


# ──────────────────────────────────────────────────────────────────────────────
# Decorative SVG helpers
# ──────────────────────────────────────────────────────────────────────────────

def section_divider():
    """A soft, centered SVG divider with an Ooredoo-red node in the middle."""
    import streamlit as st
    st.markdown(
        f"""
        <svg width="100%" height="22" viewBox="0 0 1000 22" preserveAspectRatio="none"
             style="display:block; margin:0.6rem 0 1.1rem 0;">
            <line x1="0" y1="11" x2="470" y2="11" stroke="{NAVY_HAIRLINE}" stroke-width="1"/>
            <circle cx="500" cy="11" r="4" fill="{RED}"/>
            <circle cx="500" cy="11" r="8" fill="none" stroke="{RED}" stroke-opacity="0.35" stroke-width="1"/>
            <line x1="530" y1="11" x2="1000" y2="11" stroke="{NAVY_HAIRLINE}" stroke-width="1"/>
        </svg>
        """,
        unsafe_allow_html=True,
    )
