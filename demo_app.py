"""
demo_app.py
===========
Ooredoo Business — Opportunity Navigator (employee-facing demo).

Single-file Streamlit front-end, built on the same visual identity as the
production app (app/theme.py, app/components/): navy + Ooredoo red, the real
logo, the same card/hero/chart components. It talks to demo_api.py over HTTP
and wraps the three headline capabilities of the repo in plain business
language so any Ooredoo employee — not just engineers — can use it:

    1. Add & classify clients   — one at a time, or a whole spreadsheet.
    2. Import RNE documents     — upload scanned PDFs, get a clean CSV back.
    3. Smart lead scoring       — the PU-learning + ML engine on 28k businesses.

Run (after starting demo_api.py):
    streamlit run demo_app.py
"""

import io
import os

import pandas as pd
import requests
import streamlit as st

from app.theme import (
    inject_global_css, style_dataframe, section_divider,
    WHITE, RED, RED_SOFT, MUTED, OFF_WHITE, NAVY_LIGHT, NAVY_HAIRLINE, NAVY_LIGHTER,
    SUCCESS, CATEGORY_COLORS, LOGO_PATH,
)
from app.components.branding import show_fixed_logo, brand_header, hero, eyebrow
from app.components.charts import category_distribution_chart, method_distribution_chart

API_BASE_DEFAULT = os.environ.get("DEMO_API_BASE", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Opportunity Navigator — Ooredoo Business",
    page_icon=LOGO_PATH,
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()

SECTOR_LABELS = {
    "retail": "Retail & Commerce", "manufacturing": "Manufacturing",
    "transport": "Transport & Logistics", "tourism": "Tourism & Hospitality",
    "healthcare": "Healthcare", "education": "Education",
    "financial_services": "Financial Services", "others": "Other Services",
}

METHOD_LABELS = {
    "validated_example_exact": "Verified match (100% sure)",
    "validated_example_partial": "Verified match (similar wording)",
    "taxonomy_rule": "Matched by business rules",
    "taxonomy_conflict": "Ambiguous — worth a quick check",
    "no_rule_match": "Unclear — worth a quick check",
    "empty_activity": "No description provided",
    "embedding_similarity": "Matched by AI (high confidence)",
    "embedding_similarity_low_confidence": "Matched by AI — worth a quick check",
}


def sector_label(cat: str) -> str:
    return SECTOR_LABELS.get(cat, str(cat).replace("_", " ").title())


def friendly_method(method: str) -> str:
    return METHOD_LABELS.get(method, str(method).replace("_", " ").title())


def category_badge(category: str, confidence: float | None = None):
    color = CATEGORY_COLORS.get(category, "#7286A6")
    label = sector_label(category)
    conf_txt = f" · {confidence:.0%} sure" if confidence is not None else ""
    st.markdown(
        f"<span style='display:inline-flex;align-items:center;gap:0.4rem;"
        f"background:rgba(255,255,255,0.04);border:1px solid {color};color:{WHITE};"
        f"padding:0.35rem 0.9rem;border-radius:999px;font-weight:600;font-size:0.92rem;'>"
        f"<span style='width:9px;height:9px;border-radius:50%;background:{color};'></span>"
        f"{label}{conf_txt}</span>",
        unsafe_allow_html=True,
    )


def on_card_open(height: str = "auto"):
    st.markdown(f"<div class='on-card on-reveal' style='height:{height};'>", unsafe_allow_html=True)


def on_card_close():
    st.markdown("</div>", unsafe_allow_html=True)


# Rough sector -> Google-Maps-style category hint, used only to pre-fill the
# lead-scoring form when jumping there from a directory company. The RNE
# registry (sector taxonomy) and the Maps scrape (PU-scoring features) are
# genuinely two different populations in this project — there's no built
# entity-resolution step joining them yet — so this is a helpful starting
# guess for the operator to refine, not a real cross-pipeline match.
SECTOR_TO_HINT = {
    "retail": "store", "manufacturing": "factory", "transport": "transport service",
    "tourism": "hotel", "healthcare": "clinic", "education": "school",
    "financial_services": "bank", "others": "business",
}


def _goto(page_label: str):
    st.session_state["nav_page"] = page_label


def _send_to_scoring(name: str, category_hint: str):
    st.session_state["score_prefill"] = {"name": name, "category": category_hint}
    st.session_state["nav_page"] = "🎯  Smart Lead Scoring"


def _use_client_match(record: dict):
    st.session_state["client_prefill"] = record
    st.session_state["client_search_results"] = []


def _use_search_match_for_scoring(record: dict):
    st.session_state["score_prefill"] = {
        "name": record.get("denomination", ""),
        "category": SECTOR_TO_HINT.get(record.get("category", ""), ""),
    }
    st.session_state["scoring_search_results"] = []


def company_search_box(state_key: str, on_pick, help_text: str):
    """
    Real fuzzy search over the RNE registry + manual entries (demo_api.py's
    /companies/search) — not live scraping. Renders a search box, and for any
    results, a one-click "Use →" that hands the matched record to `on_pick`.
    """
    st.caption(help_text)
    sc1, sc2 = st.columns([4, 1])
    query = sc1.text_input(
        "Search by company name", key=f"{state_key}_query",
        label_visibility="collapsed", placeholder="Start typing a company name...",
    )
    if sc2.button("🔍 Search", key=f"{state_key}_btn"):
        if query.strip():
            r = api_get(api_base, "/companies/search", params={"q": query.strip()})
            st.session_state[state_key] = r.json() if r.ok else []
        else:
            st.session_state[state_key] = []

    for i, rec in enumerate(st.session_state.get(state_key, [])):
        rc1, rc2 = st.columns([5, 1])
        subtitle = rec.get("activite") or rec.get("category") or ""
        rc1.markdown(
            f"**{rec['denomination']}**"
            + (f" — {subtitle}" if subtitle else "")
            + f"  \n<small style='color:{MUTED};'>{rec.get('source','')} · {rec.get('match_score','')}% match</small>",
            unsafe_allow_html=True,
        )
        rc2.button("Use →", key=f"{state_key}_use_{i}", on_click=on_pick, args=(rec,))


# =============================================================================
# API helpers
# =============================================================================
def api_get(base, path, **kwargs):
    return requests.get(f"{base}{path}", timeout=60, **kwargs)


def api_post(base, path, **kwargs):
    return requests.post(f"{base}{path}", timeout=300, **kwargs)


def api_delete(base, path, **kwargs):
    return requests.delete(f"{base}{path}", timeout=30, **kwargs)


@st.cache_data(ttl=10)
def get_health(base):
    try:
        r = api_get(base, "/health")
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}


def friendly_alert(message: str):
    st.error(f"⚠️ {message}\n\nIf this keeps happening, contact IT support.")


# =============================================================================
# Sidebar — brand, plain navigation, plain-language status
# =============================================================================
if "api_base" not in st.session_state:
    st.session_state.api_base = API_BASE_DEFAULT

PAGES = [
    "🏠  Overview",
    "🏢  Company Directory",
    "➕  Add & Classify Clients",
    "📄  Import RNE Documents",
    "🎯  Smart Lead Scoring",
    "🗺️  Roadmap",
]

with st.sidebar:
    brand_header()
    st.markdown("<div style='height:0.3rem;'></div>", unsafe_allow_html=True)
    page = st.radio("Navigate", PAGES, label_visibility="collapsed", key="nav_page")
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)

api_base = st.session_state.api_base
health = get_health(api_base)
caps = health.get("capabilities", {})
API_DOWN = health.get("status") != "ok"

with st.sidebar:
    if API_DOWN:
        st.error("🔴 Can't reach the server.\n\nAsk IT to start it.")
    elif all(caps.values()):
        st.success("🟢 All features ready")
    else:
        missing = [k for k, v in caps.items() if not v]
        st.warning(f"🟡 Running in limited mode\n\n{len(missing)} advanced feature(s) still being set up by IT.")

    with st.expander("⚙️ Advanced (IT / Admin)"):
        new_base = st.text_input("Server address", value=api_base)
        if new_base != api_base:
            st.session_state.api_base = new_base
            st.cache_data.clear()
            st.rerun()
        st.caption("Technical status")
        st.json(health)
        if st.button("Refresh status"):
            st.cache_data.clear()
            st.rerun()


# =============================================================================
# PAGE: Overview
# =============================================================================
def page_overview():
    st.markdown("<div style='height:1vh;'></div>", unsafe_allow_html=True)
    hero(
        "Opportunity",
        "Navigator",
        "Turn company records, scanned RNE documents, and business listings into "
        "ready-to-call sales opportunities — built for every Ooredoo Business team, "
        "technical or not.",
    )
    section_divider()

    eyebrow("What you can do here")
    cards = [
        ("M12 5 L12 19 M5 12 L19 12", "Add & classify clients",
         "Type in a new client, or import a whole spreadsheet — every company is "
         "instantly sorted into its business sector."),
        ("M4 18 L10 18 L10 10 L16 10 L16 4 L20 4", "Import RNE documents",
         "Upload scanned RNE certificates and get a clean, ready-to-use "
         "spreadsheet back in seconds — no manual typing."),
        ("M5 12 L11 12 M11 12 L9 9 M11 12 L9 15 M13 6 L19 6 M13 18 L19 18", "Smart lead scoring",
         "See which of the ~28,000 businesses we track are most likely to become "
         "Ooredoo Business customers, powered by machine learning."),
    ]
    targets = ["➕  Add & Classify Clients", "📄  Import RNE Documents", "🎯  Smart Lead Scoring"]
    cols = st.columns(3, gap="medium")
    for i, (col, (mark, title, body), target) in enumerate(zip(cols, cards, targets)):
        with col:
            st.markdown(
                f"""<div class="on-card on-reveal" style="height:206px;">
                    <svg width="38" height="38" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <path d="{mark}" stroke="{RED}" stroke-width="2"
                              stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <h3 style="color:{WHITE}; margin:0.7rem 0 0.4rem 0; font-size:1.15rem;">{title}</h3>
                    <p style="color:{MUTED}; font-size:0.94rem; line-height:1.55; margin:0;">{body}</p>
                </div>""",
                unsafe_allow_html=True,
            )
            st.button("Open →", key=f"cta_card_{i}", on_click=_goto, args=(target,), use_container_width=True)

    st.markdown("<div style='height:1.2vh;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"""<div class="on-card on-card-accent on-reveal" style="display:flex; align-items:center;
             justify-content:space-between; gap:1rem; flex-wrap:wrap;">
            <div>
                <div style="color:{WHITE}; font-size:1.15rem; font-weight:700;">Already added some companies?</div>
                <div style="color:{OFF_WHITE}; font-size:0.96rem;">
                    See everything in one place — search, filter, and score any of them.
                </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.button("📂 Open Company Directory →", type="primary", on_click=_goto, args=("🏢  Company Directory",))

    st.markdown("<div style='height:2vh;'></div>", unsafe_allow_html=True)
    eyebrow("Live snapshot")

    if API_DOWN:
        st.info("Connect to the server (see sidebar) to see live numbers here.")
    else:
        clients_r = api_get(api_base, "/segmentation/clients")
        manual_n = len(clients_r.json()) if clients_r.ok else 0
        ov_r = api_get(api_base, "/prediction/overview")
        overview = ov_r.json() if ov_r.ok else {}
        funnel = overview.get("label_funnel", {})

        c1, c2, c3 = st.columns(3)
        c1.metric("Clients added manually", manual_n)
        c2.metric("Businesses tracked for scoring", f"{funnel.get('total_businesses', 0):,}")
        c3.metric("Confirmed customer matches found", f"{funnel.get('confirmed_positive_matches', 0):,}")

    section_divider()
    eyebrow("Business sectors we detect")
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


# =============================================================================
# PAGE: Company Directory — the hub every other page feeds into
# =============================================================================
def page_directory():
    st.markdown(
        f"<h1 style='color:{WHITE};font-weight:800;font-size:2rem;margin-bottom:0;'>Company Directory</h1>"
        f"<p style='color:{MUTED};font-size:1.02rem;margin-top:0.3rem;max-width:720px;'>"
        f"Every company you've added — one at a time, from a spreadsheet, or from a scanned "
        f"document — lives here. Search it, filter it, and jump straight into lead scoring.</p>",
        unsafe_allow_html=True,
    )

    if API_DOWN:
        friendly_alert("The server isn't reachable right now.")
        return

    r = api_get(api_base, "/directory")
    if not r.ok:
        friendly_alert("Couldn't load the directory.")
        return
    data = r.json()

    if data["total"] == 0:
        st.info(
            "Your directory is empty. Add a client, import a spreadsheet, or upload an RNE "
            "document — everything you add shows up here automatically."
        )
        return

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Companies in directory", f"{data['total']:,}")
    k2.metric("Added manually", data["by_source"].get("Manual entry", 0))
    k3.metric("From spreadsheets", data["by_source"].get("Bulk import", 0))
    k4.metric("From scanned documents", data["by_source"].get("PDF document", 0))

    df = pd.DataFrame(data["rows"])
    df["category"] = df["category"].replace("", "unclassified")

    section_divider()
    eyebrow("Search & filter")
    fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
    search = fc1.text_input("Search by company or activity", placeholder="e.g. hotel, informatique...", label_visibility="collapsed")
    sector_filter = fc2.multiselect("Sector", sorted(df["category"].unique()), label_visibility="collapsed", placeholder="Sector")
    source_filter = fc3.multiselect("Source", sorted(df["source"].unique()), label_visibility="collapsed", placeholder="Source")
    review_only = fc4.checkbox("Needs review only")

    filtered = df.copy()
    if search:
        mask = (
            filtered["company"].astype(str).str.contains(search, case=False, na=False)
            | filtered["activity"].astype(str).str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]
    if sector_filter:
        filtered = filtered[filtered["category"].isin(sector_filter)]
    if source_filter:
        filtered = filtered[filtered["source"].isin(source_filter)]
    if review_only:
        filtered = filtered[filtered["needs_review"] == True]  # noqa: E712

    st.caption(f"Showing {len(filtered):,} of {len(df):,} companies")
    display = filtered.rename(columns={
        "company": "Company", "activity": "Activity", "category": "Sector",
        "confidence": "Confidence", "method": "How classified", "source": "Source",
    })
    show_cols = [c for c in ["Company", "Activity", "Sector", "Confidence", "How classified", "Source"] if c in display.columns]
    fmt = {"Confidence": "{:.0%}"} if pd.api.types.is_numeric_dtype(display.get("Confidence", pd.Series(dtype=float))) else {}
    st.dataframe(style_dataframe(display[show_cols], fmt), use_container_width=True, height=380)

    st.download_button(
        "⬇️ Download this view", filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name="company_directory.csv", mime="text/csv",
    )

    section_divider()
    ccol1, ccol2 = st.columns(2)
    with ccol1:
        eyebrow("By sector")
        category_distribution_chart(df, chart_type="bar")
    with ccol2:
        eyebrow("Where it came from")
        source_counts = df["source"].value_counts().reset_index()
        source_counts.columns = ["Source", "Companies"]
        st.dataframe(style_dataframe(source_counts), use_container_width=True, height=200)

    section_divider()
    eyebrow("Check a company's lead potential")
    st.caption(
        "Pick any company from your directory and jump straight into Smart Lead Scoring "
        "with its name and sector pre-filled."
    )
    company_names = sorted(n for n in df["company"].unique().tolist() if n)
    if company_names:
        pc1, pc2 = st.columns([3, 1])
        picked = pc1.selectbox("Company", company_names, label_visibility="collapsed")
        picked_row = df[df["company"] == picked].iloc[0]
        pc2.button(
            "🎯 Estimate lead potential →", type="primary",
            on_click=_send_to_scoring, args=(picked, SECTOR_TO_HINT.get(picked_row["category"], "")),
        )


# =============================================================================
# PAGE: Add & Classify Clients
# =============================================================================
def page_clients():
    hero_col, _ = st.columns([3, 1])
    with hero_col:
        st.markdown(
            f"<h1 style='color:{WHITE};font-weight:800;font-size:2rem;margin-bottom:0;'>"
            f"Add &amp; Classify Clients</h1>"
            f"<p style='color:{MUTED};font-size:1.02rem;margin-top:0.3rem;'>"
            f"Add clients one at a time, or bring in a whole list at once. "
            f"The app reads what the business does and sorts it into a sector automatically.</p>",
            unsafe_allow_html=True,
        )

    if API_DOWN:
        friendly_alert("The server isn't reachable right now.")
        return

    left, right = st.columns([1, 1.25], gap="large")

    with left:
        eyebrow("Already on file? Look it up first")
        on_card_open()
        company_search_box(
            "client_search_results", _use_client_match,
            "Search your RNE registry and previously-added clients — if it's already on file, "
            "we auto-fill the form below instead of you retyping it.",
        )
        on_card_close()

        client_prefill = st.session_state.pop("client_prefill", {})
        if client_prefill:
            st.info(f"Pre-filled from **{client_prefill.get('source', 'existing records')}**: **{client_prefill.get('denomination')}**. Review and add anything missing below.")

        st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
        eyebrow("Add one client")
        on_card_open()
        with st.form("add_client_form", clear_on_submit=True):
            denomination = st.text_input("Company name *", value=client_prefill.get("denomination", ""), placeholder="e.g. STE EXEMPLE SARL")
            activite = st.text_area(
                "What does this company do? *",
                value=client_prefill.get("activite", ""),
                placeholder="e.g. Vente de matériel informatique",
                help="Describe the business activity in a sentence — French or Arabic both work.",
            )
            c1, c2 = st.columns(2)
            nom_commercial = c1.text_input("Trade name (optional)")
            forme_juridique = c2.text_input("Legal form (optional)", value=client_prefill.get("forme_juridique", ""), placeholder="SARL")
            adresse = st.text_input("Address (optional)", value=client_prefill.get("adresse", ""))
            c3, c4 = st.columns(2)
            capital = c3.text_input("Capital (optional)", value=client_prefill.get("capital", ""))
            date_immat = c4.text_input("Registration date (optional)", value=client_prefill.get("date_immatriculation", ""), placeholder="DD/MM/YYYY")
            nom_dirigeant = st.text_input("Manager's name (optional)")
            submitted = st.form_submit_button("Add & classify this client", type="primary")
        on_card_close()

        if submitted:
            if not denomination or not activite:
                st.warning("Please fill in the company name and what it does.")
            else:
                payload = {
                    "denomination": denomination, "activite": activite,
                    "nom_commercial": nom_commercial, "forme_juridique": forme_juridique,
                    "adresse": adresse, "capital": capital,
                    "date_immatriculation": date_immat, "nom_dirigeant": nom_dirigeant,
                }
                r = api_post(api_base, "/segmentation/clients", json=payload)
                if r.ok:
                    row = r.json()
                    st.success(f"**{denomination}** was added.")
                    category_badge(row["category"], row["confidence"])
                    st.caption(friendly_method(row["method"]))
                else:
                    friendly_alert("Couldn't add this client.")

        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        eyebrow("Just curious? Try it without saving")
        quick_text = st.text_input("Describe any business activity", placeholder="e.g. Clinique dentaire pédiatrique")
        if st.button("Classify (no save)"):
            if quick_text:
                r = api_post(api_base, "/segmentation/classify-text", json={"activity": quick_text})
                if r.ok:
                    res = r.json()
                    category_badge(res["category"], res["confidence"])
                    st.caption(friendly_method(res["method"]))
                else:
                    friendly_alert("Couldn't classify this text.")

    with right:
        eyebrow("Clients added so far")
        r = api_get(api_base, "/segmentation/clients")
        clients = r.json() if r.ok else []
        if clients:
            df_clients = pd.DataFrame(clients)
            display_df = df_clients.rename(columns={
                "fr_denomination": "Company", "fr_activite_principale": "Activity",
                "category": "Sector", "confidence": "Confidence", "added_at": "Added",
            })
            show_cols = [c for c in ["Company", "Activity", "Sector", "Confidence", "Added"] if c in display_df.columns]
            st.dataframe(
                style_dataframe(display_df[show_cols], {"Confidence": "{:.0%}"}),
                use_container_width=True, height=250,
            )
            cc1, cc2 = st.columns(2)
            cc1.download_button(
                "⬇️ Download list", df_clients.to_csv(index=False).encode("utf-8-sig"),
                file_name="my_clients.csv", mime="text/csv",
            )
            if cc2.button("🗑️ Clear list"):
                api_delete(api_base, "/segmentation/clients")
                st.rerun()

            st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
            category_distribution_chart(df_clients, chart_type="pie")
        else:
            st.info("No clients added yet — use the form on the left to add your first one.")

    section_divider()
    eyebrow("Or classify a whole list at once")
    on_card_open()
    st.caption(
        "Use the companies already on file, or upload your own spreadsheet "
        "(must include a column describing each company's activity)."
    )
    source = st.radio("Where's the data?", ["Use companies already on file", "Upload my own spreadsheet"], horizontal=True)
    uploaded_csv = None
    if source == "Upload my own spreadsheet":
        uploaded_csv = st.file_uploader("Spreadsheet (CSV)", type=["csv"])

    if st.button("▶️  Classify this list", type="primary"):
        with st.spinner("Reading and classifying every row — this only takes a moment..."):
            if source == "Use companies already on file":
                r = api_post(api_base, "/segmentation/run-csv", data={"use_existing": "true"})
            elif uploaded_csv is not None:
                files = {"file": (uploaded_csv.name, uploaded_csv.getvalue(), "text/csv")}
                r = api_post(api_base, "/segmentation/run-csv", files=files, data={"use_existing": "false"})
            else:
                r = None
                st.warning("Please choose a spreadsheet first.")
        if r is not None:
            if r.ok:
                st.session_state["seg_summary"] = r.json()
            else:
                friendly_alert("Couldn't process this file. Make sure it has an activity column.")
    on_card_close()

    summary = st.session_state.get("seg_summary")
    if summary:
        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Companies classified", f"{summary['total_rows']:,}")
        m2.metric("Worth a quick human check", summary["needs_review"])
        m3.metric("Used AI matching", "Yes" if summary["embedding_layer_used"] else "Rules only")

        dl = api_get(api_base, f"/segmentation/download/{summary['download_token']}")
        if dl.ok:
            try:
                result_df = pd.read_csv(io.BytesIO(dl.content), encoding="utf-8-sig")
                cchart, mchart = st.columns(2)
                with cchart:
                    st.caption("By sector")
                    category_distribution_chart(result_df, chart_type="bar")
                with mchart:
                    st.caption("How each company was classified")
                    method_distribution_chart(result_df)
            except Exception:
                pass
            st.download_button(
                "⬇️ Download the full results", dl.content,
                file_name="clients_classified.csv", mime="text/csv", type="primary",
            )


# =============================================================================
# PAGE: Import RNE Documents
# =============================================================================
def page_extraction():
    st.markdown(
        f"<h1 style='color:{WHITE};font-weight:800;font-size:2rem;margin-bottom:0;'>Import RNE Documents</h1>"
        f"<p style='color:{MUTED};font-size:1.02rem;margin-top:0.3rem;max-width:700px;'>"
        f"Drop in one or several scanned RNE certificates. The app reads every field, "
        f"cleans up the text, and hands you back one ready-to-use spreadsheet — no retyping.</p>",
        unsafe_allow_html=True,
    )

    if API_DOWN:
        friendly_alert("The server isn't reachable right now.")
        return

    if not caps.get("extraction_pdf", False):
        st.warning(
            "📄 This feature is still being set up by IT (it needs a PDF-reading library). "
            "Everything else in the app works normally."
        )

    on_card_open()
    pdfs = st.file_uploader(
        "RNE PDF file(s)", type=["pdf"], accept_multiple_files=True,
        help="You can select more than one file at a time.",
    )
    run_disabled = not caps.get("extraction_pdf", False) or not pdfs
    if st.button("⚙️  Parse & clean these documents", type="primary", disabled=run_disabled):
        with st.spinner(f"Reading {len(pdfs)} document(s)... this can take a moment per file."):
            files = [("files", (p.name, p.getvalue(), "application/pdf")) for p in pdfs]
            r = api_post(api_base, "/extraction/parse-pdfs", files=files)
        if r.ok:
            st.session_state["extract_result"] = r.json()
        else:
            friendly_alert("Something went wrong while reading these documents.")
    on_card_close()

    result = st.session_state.get("extract_result")
    if result:
        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Read successfully", result["n_ok"])
        m2.metric("Needs a second look", result["n_failed"])
        m3.metric("Rows in the spreadsheet", result["rows"])

        status_df = pd.DataFrame(result["results"]).rename(columns={
            "file": "Document", "status": "Result", "identifiant_unique": "Company ID",
            "sector": "Sector", "error": "Note",
        })
        status_df["Result"] = status_df["Result"].map({"ok": "✅ Success", "error": "⚠️ Needs a look"}).fillna(status_df["Result"])
        if "Sector" in status_df.columns:
            status_df["Sector"] = status_df["Sector"].apply(
                lambda c: sector_label(c) if isinstance(c, str) and c else ""
            )
        show_cols = [c for c in ["Document", "Result", "Company ID", "Sector", "Note"] if c in status_df.columns]
        st.dataframe(style_dataframe(status_df[show_cols]), use_container_width=True)

        if result["n_failed"]:
            st.caption(
                "Documents marked ⚠️ couldn't be read automatically — usually a low-quality "
                "scan. Try a clearer copy, or add that client manually from the "
                "**Add & Classify Clients** page."
            )

        if result.get("download_token"):
            dl = api_get(api_base, f"/extraction/download/{result['download_token']}")
            if dl.ok:
                st.download_button(
                    "⬇️ Download the cleaned spreadsheet", dl.content,
                    file_name="rne_companies_parsed_cleaned.csv", mime="text/csv", type="primary",
                )
            st.success("These companies were also sector-classified and added to your **Company Directory**.")
            st.button("📂 Open Company Directory →", on_click=_goto, args=("🏢  Company Directory",))


# =============================================================================
# PAGE: Smart Lead Scoring (the flagship — PU-Bagging + classifier)
# =============================================================================
def page_scoring():
    hero(
        "Smart Lead",
        "Scoring",
        "Which of the businesses we track are most likely to become Ooredoo Business "
        "customers? Ooredoo doesn't disclose the size of its client base, so we found out "
        "by cross-referencing 28,000 scraped Tunisian businesses against known purchase "
        "records, then used Positive-Unlabeled machine learning to go further.",
    )

    if API_DOWN:
        friendly_alert("The server isn't reachable right now.")
        return

    ov_r = api_get(api_base, "/prediction/overview")
    overview = ov_r.json() if ov_r.ok else {}
    funnel = overview.get("label_funnel", {})
    run_summary = overview.get("run_summary", {})

    eyebrow("How the labels were built")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Businesses analyzed", f"{funnel.get('total_businesses', 0):,}")
    k2.metric("Confirmed customer matches", f"{funnel.get('confirmed_positive_matches', 0):,}")
    k3.metric("Positive after Bagging-PU", f"{funnel.get('positives_after_bagging_pu', 0):,}")
    k4.metric("Treated as negative", f"{funnel.get('negatives_for_classification', 0):,}")
    st.caption(
        "In plain terms: cross-referencing the scrape against known purchases found "
        f"{funnel.get('confirmed_positive_matches', 0):,} confirmed customers. Bagging-PU "
        f"(a machine learning technique built for exactly this situation — a few confirmed "
        f"positives and no confirmed negatives) then identified "
        f"{funnel.get('positives_after_bagging_pu', 0):,} businesses confidently enough to "
        f"treat as positive; the rest were treated as negative examples to train the classifier below."
    )

    section_divider()

    if run_summary:
        eyebrow("The scoring model, in numbers")
        best = run_summary.get("best_model", "—")
        test_metrics = run_summary.get("test_metrics", {}).get(best, {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Model in production", best)
        c2.metric("Overall accuracy", f"{test_metrics.get('accuracy', 0):.0%}")
        c3.metric("Catches real customers", f"{test_metrics.get('recall', 0):.0%}")
        c4.metric("Reliability score (ROC-AUC)", f"{test_metrics.get('roc_auc', 0):.2f}")

        known_checks = run_summary.get("known_customer_check", [])
        best_known = next((r for r in known_checks if r["model"] == best), None)
        if best_known:
            st.caption(
                f"Sanity check on a held-out validation slice of {best_known['n_known']} confirmed "
                f"customers: the model correctly flagged **{best_known['known_recall']:.0%}** of "
                f"them as good prospects."
            )

    section_divider()
    eyebrow("Score a business right now")
    st.caption("Type in what you know about a business and the model tells you how promising it is.")

    if not overview.get("prediction_model_available", False):
        st.warning("🎯 Live scoring is still being set up by IT. The results above are already available, though.")
    else:
        on_card_open()
        company_search_box(
            "scoring_search_results", _use_search_match_for_scoring,
            "Already have this business on file? Search your RNE registry or manually-added "
            "clients to pre-fill the name and a suggested category below — Ooredoo's client "
            "database has no ratings/reviews/phone fields, so you'll still want to fill those "
            "in for an accurate score. A live web lookup isn't built yet (see the Roadmap page).",
        )
        on_card_close()

        prefill = st.session_state.pop("score_prefill", {})
        if prefill:
            st.info(
                f"Pre-filled: **{prefill.get('name')}**. "
                f"Add a few more details below (rating, reviews, website...) for a sharper score."
            )
        on_card_open()
        with st.form("score_form"):
            sc1, sc2, sc3 = st.columns(3)
            name = sc1.text_input("Business name", value=prefill.get("name", ""))
            category = sc2.text_input("Category", value=prefill.get("category", ""), placeholder="e.g. hotel")
            governorate = sc3.text_input("Region (Governorate)", placeholder="e.g. Tunis")
            sc4, sc5, sc6 = st.columns(3)
            rating = sc4.number_input("Google rating", 0.0, 5.0, 4.0, step=0.1)
            reviews = sc5.number_input("Number of reviews", 0, 100000, 20)
            search_category = sc6.text_input("Search category (optional)")
            sc7, sc8, sc9 = st.columns(3)
            website = sc7.text_input("Website (optional)")
            email = sc8.text_input("Email (optional)")
            phone = sc9.text_input("Phone (optional)")
            address = st.text_input("Address (optional)")
            score_submit = st.form_submit_button("🎯 Check this business", type="primary")
        on_card_close()

        if score_submit:
            payload = {
                "name": name, "category": category, "governorate": governorate,
                "rating": rating, "reviews": reviews, "search_category": search_category,
                "website": website or None, "email": email or None, "phone": phone or None,
                "address": address,
            }
            r = api_post(api_base, "/prediction/score", json=payload)
            if r.ok:
                res = r.json()
                prob = res["prob_client"]
                if prob >= 0.66:
                    tag, color = "🔥 High potential", SUCCESS
                elif prob >= 0.33:
                    tag, color = "🟡 Worth a look", "#E0A24C"
                else:
                    tag, color = "❄️ Low potential", MUTED
                st.markdown(
                    f"<div class='on-card on-card-accent' style='display:flex;align-items:center;"
                    f"justify-content:space-between;'>"
                    f"<div><div style='color:{MUTED};font-size:0.85rem;text-transform:uppercase;"
                    f"letter-spacing:0.06em;'>Likelihood to become a customer</div>"
                    f"<div style='color:{WHITE};font-size:2.2rem;font-weight:800;'>{prob:.0%}</div></div>"
                    f"<div style='color:{color};font-size:1.3rem;font-weight:700;'>{tag}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                friendly_alert("Couldn't score this business.")

        with st.expander("Score many businesses at once from a spreadsheet"):
            biz_csv = st.file_uploader("Businesses spreadsheet (CSV)", type=["csv"], key="score_csv")
            if st.button("Score this spreadsheet") and biz_csv is not None:
                files = {"file": (biz_csv.name, biz_csv.getvalue(), "text/csv")}
                with st.spinner("Scoring every row..."):
                    r = api_post(api_base, "/prediction/score-csv", files=files)
                if r.ok:
                    res = r.json()
                    st.success(f"Scored {res['rows_scored']:,} businesses — {res['predicted_client_count']:,} look like good prospects.")
                    preview = pd.DataFrame(res["top_preview"]).rename(columns={
                        "name": "Business", "category": "Category", "governorate": "Region",
                        "prob_client": "Likelihood", "predicted_client": "Good prospect?",
                    })
                    if "Likelihood" in preview.columns:
                        st.dataframe(style_dataframe(preview, {"Likelihood": "{:.0%}"}), use_container_width=True)
                    else:
                        st.dataframe(preview, use_container_width=True)
                    dl = api_get(api_base, f"/prediction/download/{res['download_token']}")
                    if dl.ok:
                        st.download_button(
                            "⬇️ Download all scored businesses", dl.content,
                            file_name="scored_businesses.csv", mime="text/csv",
                        )
                else:
                    friendly_alert("Couldn't score this spreadsheet.")

    section_divider()
    with st.expander("🔬 How this works — technical notes (for reviewers / thesis defense)"):
        funnel = overview.get("label_funnel", {})
        st.markdown(
            "**Problem type: Positive-Unlabeled (PU) learning.** Ooredoo does not disclose the "
            "size or list of its client base, so labels can't come from a simple export — instead, "
            f"the {funnel.get('total_businesses', 0):,}-row Google Maps scrape was cross-referenced "
            f"against known purchase records via entity linkage (fuzzy name/phone/website matching), "
            f"giving {funnel.get('confirmed_positive_matches', 0):,} confirmed positive matches. "
            "Everything else is *unlabeled*, not confirmed-negative — a business we haven't matched "
            "might be a great prospect nobody has called yet. Treating the rest as negative outright "
            "would teach the model that customer-like patterns are bad, so three PU methods were "
            "built and compared instead:\n\n"
            "- **Bagging-PU** (Mordelet & Vert, 2014) — repeated sampling of pseudo-negatives, "
            "out-of-bag scoring.\n"
            "- **Prior-corrected Bagging-PU** — same, with pseudo-negatives down-weighted by the "
            "estimated class prior (nnPU spirit, Kiryo et al. 2017).\n"
            "- **Two-step PU** — extract reliable negatives, then train a standard classifier.\n\n"
            "The class prior itself was estimated three ways (spy technique, Elkan-Noto holdout, "
            "TIcE) — the spy heuristic gave an implausible π̂=0.77, so the final pipeline uses the "
            "more robust holdout/TIcE estimate. Bagging-PU's confident output expanded the positive "
            f"set from {funnel.get('confirmed_positive_matches', 0):,} confirmed matches to "
            f"{funnel.get('positives_after_bagging_pu', 0):,} positively-labeled businesses; the "
            f"remaining {funnel.get('negatives_for_classification', 0):,} were used as negatives. "
            "A calibrated LightGBM classifier is then trained on this final split, with careful "
            "leakage controls (PU scores and ranks are excluded as features)."
        )
        recall_by_k = overview.get("pu_recall_by_method", {})
        if recall_by_k:
            st.caption(
                "Recall@k by PU method, from an earlier validation pass on a smaller matched "
                "sample (before entity linkage was scaled up to the current "
                f"{funnel.get('confirmed_positive_matches', 0):,}-positive set) — kept here to show "
                "the relative ranking between methods, which is what motivated using Bagging-PU."
            )
            comp_df = pd.DataFrame(recall_by_k).rename(columns={"2000": "recall@2000", "5000": "recall@5000"})
            st.dataframe(comp_df.style.format("{:.1%}"), use_container_width=True)

        figs_r = api_get(api_base, "/prediction/figures")
        figs = figs_r.json() if figs_r.ok else {"pu": [], "classification": []}
        fcol1, fcol2 = st.columns(2)
        with fcol1:
            st.markdown("**Positive-Unlabeled learning**")
            for fname in figs.get("pu", []):
                img = api_get(api_base, f"/prediction/figure/pu/{fname}")
                if img.ok:
                    st.image(img.content, caption=fname, use_container_width=True)
        with fcol2:
            st.markdown("**Supervised classifier on PU labels**")
            for fname in figs.get("classification", []):
                img = api_get(api_base, f"/prediction/figure/classification/{fname}")
                if img.ok:
                    st.image(img.content, caption=fname, use_container_width=True)


# =============================================================================
# PAGE: Roadmap — honestly labeled, nothing here is wired up yet
# =============================================================================
def _planned_badge() -> str:
    return (
        "<span style='background:rgba(224,162,76,0.15);color:#E0A24C;border:1px solid #E0A24C;"
        "padding:2px 10px;border-radius:999px;font-size:0.75rem;font-weight:700;"
        "text-transform:uppercase;letter-spacing:0.04em;'>🚧 Planned — not yet built</span>"
    )


def _built_badge() -> str:
    return (
        "<span style='background:rgba(45,212,167,0.15);color:#2DD4A7;border:1px solid #2DD4A7;"
        "padding:2px 10px;border-radius:999px;font-size:0.75rem;font-weight:700;"
        "text-transform:uppercase;letter-spacing:0.04em;'>✅ Built — try it below</span>"
    )


def page_roadmap():
    st.markdown(
        f"<h1 style='color:{WHITE};font-weight:800;font-size:2rem;margin-bottom:0;'>"
        f"Data Pipeline — Scrape, Complete, Clean</h1>"
        f"<p style='color:{MUTED};font-size:1.02rem;margin-top:0.3rem;max-width:760px;'>"
        f"Three small, real tools behind the enrichment pipeline. Each does one honest, "
        f"narrowly-scoped job today; the remaining work is packaging them behind the MCP "
        f"(Model Context Protocol) so other systems can call them directly instead of hitting "
        f"these endpoints. Try each one below with your own input.</p>",
        unsafe_allow_html=True,
    )

    if API_DOWN:
        friendly_alert("The server isn't reachable right now.")
        return

    section_divider()

    # ---- Cleaning tool ----
    eyebrow("🧹 Cleaning tool")
    st.markdown(_built_badge(), unsafe_allow_html=True)
    st.caption(
        "Normalizes messy text — accents, casing, stray punctuation, Arabic diacritics. This is "
        "the exact logic already running live in Add & Classify Clients and Import RNE Documents; "
        "here it's just exposed directly so you can try it on anything."
    )
    clean_input = st.text_input("Try it: type messy text", placeholder="  Vente  de   matériel-INFORMATIQUE!!  ", key="tool_clean_in")
    if st.button("Clean this text"):
        if clean_input.strip():
            r = api_post(api_base, "/tools/clean", json={"text": clean_input})
            if r.ok:
                res = r.json()
                st.code(res["cleaned_normalized"], language=None)
            else:
                friendly_alert("Couldn't clean this text.")
        else:
            st.warning("Type something first.")

    section_divider()

    # ---- Completion tool ----
    eyebrow("🧩 Data-completion tool")
    st.markdown(_built_badge(), unsafe_allow_html=True)
    st.caption(
        "Fills only what it can honestly justify: the region (governorate) from an address, and a "
        "suggested Maps-style category from a detected sector. It does **not** guess ratings, "
        "reviews, phone, or website — those stay reported as missing rather than invented."
    )
    cc1, cc2 = st.columns(2)
    complete_addr = cc1.text_input("Address", placeholder="Rue de Marseille, Sfax, Tunisie", key="tool_complete_addr")
    complete_sector = cc2.selectbox("Detected sector", [""] + list(SECTOR_LABELS.keys()), format_func=lambda s: sector_label(s) if s else "—", key="tool_complete_sector")
    if st.button("Complete this record"):
        r = api_post(api_base, "/tools/complete", json={"adresse": complete_addr, "category": complete_sector})
        if r.ok:
            res = r.json()
            if res["fields_filled"]:
                st.success(f"Filled: {', '.join(res['fields_filled'])}")
            else:
                st.info("Nothing could be confidently filled from this input.")
            st.json(res["completed"])
            st.caption(f"Still missing (left blank, not guessed): {', '.join(res['still_missing']) or 'nothing'}")
        else:
            friendly_alert("Couldn't complete this record.")

    section_divider()

    # ---- Scraping tool ----
    eyebrow("🔍 Scraping / enrichment tool")
    st.markdown(_built_badge(), unsafe_allow_html=True)
    st.caption(
        "Makes a real call to OpenStreetMap's free Nominatim geocoder — genuine external data, "
        "not fabricated. Scope note: this finds locations/addresses, not Google-style ratings or "
        "reviews — that needs a paid, keyed API this prototype doesn't have."
    )
    sc1, sc2 = st.columns(2)
    scrape_name = sc1.text_input("Business name", placeholder="Hotel Africa", key="tool_scrape_name")
    scrape_addr = sc2.text_input("City / address", placeholder="Tunis", key="tool_scrape_addr")
    if st.button("Look this up"):
        if scrape_name or scrape_addr:
            r = api_get(api_base, "/tools/scrape", params={"name": scrape_name, "address": scrape_addr})
            if r.ok:
                res = r.json()
                if res.get("found"):
                    st.success(res["display_name"])
                    st.caption(f"Lat/Lon: {res['latitude']:.4f}, {res['longitude']:.4f} · {res['source']}")
                    st.map(pd.DataFrame([{"lat": res["latitude"], "lon": res["longitude"]}]))
                else:
                    st.warning("No match found for this name/address on OpenStreetMap.")
            else:
                friendly_alert("Couldn't reach the lookup service.")
        else:
            st.warning("Type a business name or address first.")

    section_divider()
    st.info(
        "**What's left, honestly:** these three run as regular endpoints today. Wrapping them "
        "behind an actual MCP server — so any MCP-compatible agent can call `scrape`, `complete`, "
        "and `clean` as tools rather than hitting these HTTP routes directly — is the remaining "
        "integration work, not the underlying logic."
    )


# =============================================================================
# Router
# =============================================================================
PAGE_FUNCS = {
    "🏠  Overview": page_overview,
    "🏢  Company Directory": page_directory,
    "➕  Add & Classify Clients": page_clients,
    "📄  Import RNE Documents": page_extraction,
    "🎯  Smart Lead Scoring": page_scoring,
    "🗺️  Roadmap": page_roadmap,
}
PAGE_FUNCS[page]()

show_fixed_logo()
