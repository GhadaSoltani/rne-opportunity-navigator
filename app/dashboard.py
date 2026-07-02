"""
app/dashboard.py
================
Opportunity Navigator — application router (entry point).

Launch:
    python run.py --dashboard
    or
    streamlit run app/dashboard.py

This file owns navigation via st.navigation, so it controls the exact sidebar
labels and order. Each page module under app/pages/ is a plain body script
(it must NOT call st.set_page_config — the router owns the page config).
"""

import streamlit as st

from app.theme import inject_global_css
from app.components.branding import brand_header

st.set_page_config(
    page_title="Opportunity Navigator",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject the theme CSS here too (each page also calls this — it's idempotent)
# so the sticky brand block below is styled immediately, with no flash.
inject_global_css()

# Render the sticky brand block FIRST, before the nav menu is created.
# Streamlit renders sidebar content in call order: anything written here
# appears above the nav menu; anything a page writes afterward (e.g. the
# workspace chips via sidebar_context()) appears below it.
brand_header()

# ── Define the navigation (custom titles, in order) ───────────────────────────
home        = st.Page("pages/home.py",                  title="Home",                 icon=":material/home:", default=True)
import_data = st.Page("pages/import_data.py",           title="Import data",          icon=":material/upload:")
overview    = st.Page("pages/overview.py",              title="Overview",             icon=":material/insights:")
prospects   = st.Page("pages/commercial_prospects.py",  title="Commercial Prospects", icon=":material/target:")
directory   = st.Page("pages/company_directory.py",     title="Company Directory",    icon=":material/contacts:")
market      = st.Page("pages/market_intelligence.py",   title="Market Intelligence",  icon=":material/monitoring:")

nav = st.navigation([home, import_data, overview, prospects, directory, market])
nav.run()
