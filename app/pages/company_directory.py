"""
app/pages/4_Company_Directory.py
================================
The sales-facing company directory.

A clean, scannable view of every classified company with exactly the fields a
salesperson needs to make a call: who they are, what they do, where they are,
since when, and who runs it. Built as a styled, searchable, paginated table —
not a raw dataset dump.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from app.theme import (
    inject_global_css, section_divider,
    WHITE, RED, RED_SOFT, MUTED, OFF_WHITE, NAVY, NAVY_LIGHT,
    NAVY_LIGHTER, NAVY_HAIRLINE, CATEGORY_COLORS,
)
from app.components.branding import (
    show_fixed_logo, page_title, sidebar_context, eyebrow,
)
from analysis.sales_table import build_sales_table
from segmentation.config import OUTPUT_CSV


inject_global_css()
sidebar_context()

PAGE_SIZE_DEFAULT = 25

# Friendly labels for the category badge
CATEGORY_LABELS = {
    "retail": "Retail", "manufacturing": "Manufacturing", "transport": "Transport",
    "tourism": "Tourism", "healthcare": "Healthcare", "education": "Education",
    "financial_services": "Financial services", "others": "Others",
}


@st.cache_data(ttl=20)
def load_segmented(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    table, report = build_sales_table(df)
    return table, report


page_title("Company Directory", "Every classified company, ready to call.")

data = load_segmented(str(OUTPUT_CSV))

if data is None:
    st.markdown(
        f"""
        <div class="on-card on-reveal" style="text-align:center; margin-top:1.4rem;">
            <p style="color:{OFF_WHITE}; font-size:1.05rem; margin:0;">
                No companies yet. Open <b>Upload &amp; Run</b> in the sidebar to bring in your first documents.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    show_fixed_logo()
    st.stop()

table, report = data

# ── Surface any column that could not be resolved (honest, not silent) ────────
missing = [r["field"] for r in report if r["status"] == "MISSING"]
if missing:
    pretty = ", ".join(missing)
    st.markdown(
        f"""
        <div class="on-card on-reveal" style="border-left:3px solid {RED};
             background:rgba(237,28,36,0.06); margin-bottom:0.8rem;">
            <span style="color:{OFF_WHITE};">
            Some fields were not found in the data and appear empty: <b>{pretty}</b>.
            Everything else is shown normally.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

LABEL_CATEGORY = "Catégorie"
LABEL_DENOM    = "Dénomination"
LABEL_ACTIVITY = "Activité"
LABEL_ADDRESS  = "Adresse"
LABEL_ID       = "Identifiant unique"
LABEL_DATE     = "Date début d'activité"
LABEL_DIRIGEANT = "Nom du dirigeant"


# ── Top metrics ───────────────────────────────────────────────────────────────
total = len(table)
n_categories = table[LABEL_CATEGORY].replace("", pd.NA).nunique(dropna=True) if LABEL_CATEGORY in table.columns else 0
with_director = int((table[LABEL_DIRIGEANT].astype(str).str.len() > 0).sum()) if LABEL_DIRIGEANT in table.columns else 0

c1, c2, c3 = st.columns(3)
c1.metric("Companies", f"{total:,}")
c2.metric("Sectors covered", f"{n_categories}")
c3.metric("With a named director", f"{with_director:,}")

section_divider()


# ── Filters / search ──────────────────────────────────────────────────────────
eyebrow("Find a company")

fcol1, fcol2, fcol3 = st.columns([2, 1, 1])
with fcol1:
    query = st.text_input("Search by name, activity, address, ID or director", "")
with fcol2:
    if LABEL_CATEGORY in table.columns:
        cats_present = sorted([c for c in table[LABEL_CATEGORY].unique().tolist() if str(c).strip()])
        cat_options = ["All sectors"] + cats_present
        selected_cat = st.selectbox("Sector", cat_options)
    else:
        selected_cat = "All sectors"
with fcol3:
    page_size = st.selectbox("Per page", [10, 25, 50, 100], index=[10, 25, 50, 100].index(PAGE_SIZE_DEFAULT))


# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = table.copy()

if selected_cat != "All sectors" and LABEL_CATEGORY in filtered.columns:
    filtered = filtered[filtered[LABEL_CATEGORY] == selected_cat]

if query.strip():
    q = query.strip().lower()
    searchable_cols = [c for c in [LABEL_DENOM, LABEL_ACTIVITY, LABEL_ADDRESS, LABEL_ID, LABEL_DIRIGEANT] if c in filtered.columns]
    mask = pd.Series(False, index=filtered.index)
    for col in searchable_cols:
        mask = mask | filtered[col].astype(str).str.lower().str.contains(q, na=False, regex=False)
    filtered = filtered[mask]


# ── Pagination state ──────────────────────────────────────────────────────────
total_filtered = len(filtered)
total_pages = max(1, (total_filtered + page_size - 1) // page_size)

st.session_state.setdefault("dir_page", 1)
# clamp current page when filters shrink the result set
if st.session_state.dir_page > total_pages:
    st.session_state.dir_page = 1

page = st.session_state.dir_page
start = (page - 1) * page_size
end = start + page_size
page_rows = filtered.iloc[start:end]

st.markdown(
    f"<p style='color:{OFF_WHITE}; margin-bottom:0.4rem;'>"
    f"<b>{total_filtered:,}</b> companies found · page <b>{page}</b> of <b>{total_pages}</b></p>",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Render the directory as styled HTML cards-in-a-table (not a raw dataframe)
# ──────────────────────────────────────────────────────────────────────────────

def _is_rtl(text: str) -> bool:
    """True if the string contains Arabic characters — used to set text direction."""
    return any("\u0600" <= ch <= "\u06FF" for ch in str(text))


def _esc(text: str) -> str:
    """Minimal HTML escaping for safety inside our markup."""
    return (
        str(text)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _category_badge(cat: str) -> str:
    key = str(cat).strip()
    if not key:
        return f'<span style="color:{MUTED};">—</span>'
    color = CATEGORY_COLORS.get(key, "#7286A6")
    label = CATEGORY_LABELS.get(key, key)
    return (
        f'<span style="display:inline-flex; align-items:center; gap:0.4rem;'
        f' background:{color}1f; border:1px solid {color}55; color:{WHITE};'
        f' border-radius:999px; padding:0.18rem 0.7rem; font-size:0.82rem; white-space:nowrap;">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{color};"></span>{_esc(label)}</span>'
    )


def _cell(text: str, *, strong=False, muted=False, max_width=None) -> str:
    val = _clean = str(text).strip()
    if not val:
        return f'<td style="padding:12px 14px;"><span style="color:{MUTED};">—</span></td>'
    rtl = _is_rtl(val)
    dir_attr = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    color = MUTED if muted else (WHITE if strong else OFF_WHITE)
    weight = "600" if strong else "400"
    mw = f"max-width:{max_width}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" if max_width else ""
    return (
        f'<td style="padding:12px 14px; color:{color}; font-weight:{weight};'
        f' direction:{dir_attr}; text-align:{align}; {mw}" title="{_esc(val)}">{_esc(val)}</td>'
    )


def render_directory(rows: pd.DataFrame) -> str:
    header_cells = "".join(
        f'<th style="position:sticky; top:0; background:{NAVY_LIGHTER}; color:{WHITE};'
        f' text-align:left; padding:12px 14px; font-size:0.74rem; letter-spacing:0.05em;'
        f' text-transform:uppercase; font-weight:600; white-space:nowrap;">{_esc(col)}</th>'
        for col in rows.columns
    )

    body = ""
    for _, r in rows.iterrows():
        cells = (
            _cell(r.get(LABEL_ID, ""), muted=True)
            + _cell(r.get(LABEL_DENOM, ""), strong=True, max_width="220px")
            + f'<td style="padding:12px 14px;">{_category_badge(r.get(LABEL_CATEGORY, ""))}</td>'
            + _cell(r.get(LABEL_ACTIVITY, ""), max_width="280px")
            + _cell(r.get(LABEL_ADDRESS, ""), max_width="240px")
            + _cell(r.get(LABEL_DATE, ""))
            + _cell(r.get(LABEL_DIRIGEANT, ""))
        )
        body += f'<tr style="border-bottom:1px solid {NAVY};">{cells}</tr>'

    return f"""
    <div class="on-reveal" style="border:1px solid {NAVY_HAIRLINE}; border-radius:14px;
         overflow:auto; max-height:640px; box-shadow:0 6px 20px rgba(0,0,0,0.18);">
        <table style="width:100%; border-collapse:collapse; font-size:0.92rem;">
            <thead><tr>{header_cells}</tr></thead>
            <tbody>{body}</tbody>
        </table>
    </div>
    """


# We re-order the columns to: ID, Dénomination, Catégorie, Activité, Adresse, Date, Dirigeant
ORDERED = [LABEL_ID, LABEL_DENOM, LABEL_CATEGORY, LABEL_ACTIVITY, LABEL_ADDRESS, LABEL_DATE, LABEL_DIRIGEANT]
ordered_present = [c for c in ORDERED if c in page_rows.columns]

if total_filtered == 0:
    st.markdown(
        f"<div class='on-card' style='text-align:center;'>"
        f"<p style='color:{MUTED}; margin:0;'>No companies match your search. Try a different term or sector.</p></div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(render_directory(page_rows[ordered_present]), unsafe_allow_html=True)


# ── Pager controls ────────────────────────────────────────────────────────────
def _go_first(): st.session_state.dir_page = 1
def _go_prev():  st.session_state.dir_page = max(1, st.session_state.dir_page - 1)
def _go_next():  st.session_state.dir_page = min(total_pages, st.session_state.dir_page + 1)
def _go_last():  st.session_state.dir_page = total_pages

st.markdown("<div style='height:0.6vh;'></div>", unsafe_allow_html=True)
p1, p2, p3, p4, p5 = st.columns([1, 1, 2, 1, 1])
with p1:
    st.button("« First", on_click=_go_first, disabled=(page <= 1), use_container_width=True)
with p2:
    st.button("‹ Prev", on_click=_go_prev, disabled=(page <= 1), use_container_width=True)
with p3:
    st.markdown(
        f"<p style='text-align:center; color:{MUTED}; margin-top:0.5rem;'>"
        f"Showing {min(start + 1, total_filtered):,}–{min(end, total_filtered):,} of {total_filtered:,}</p>",
        unsafe_allow_html=True,
    )
with p4:
    st.button("Next ›", on_click=_go_next, disabled=(page >= total_pages), use_container_width=True)
with p5:
    st.button("Last »", on_click=_go_last, disabled=(page >= total_pages), use_container_width=True)


# ── Download (the clean six/seven-column view) ────────────────────────────────
section_divider()
csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "Download this directory (CSV)",
    data=csv_bytes,
    file_name="company_directory.csv",
    mime="text/csv",
)

show_fixed_logo()
