"""
app/pages/import_data.py
========================
Import data — bring in company records and run the pipeline.

PDF upload flow (updated):
    1. User uploads PDFs via Streamlit
    2. Each PDF is ingested into MinIO + MongoDB (via ingest.py)
    3. Pipeline runs extraction FROM DATABASE (not from local folder)
    4. Segmentation + analysis run as before

CSV upload flow (unchanged):
    1. User uploads a CSV
    2. Saved to data/input/rne_companies.csv
    3. Pipeline runs segmentation + analysis (no extraction)
"""

import shutil
import tempfile
from pathlib import Path

import streamlit as st

from app.theme import (
    inject_global_css, section_divider,
    WHITE, RED, MUTED, OFF_WHITE, SUCCESS, NAVY_LIGHT, NAVY_HAIRLINE,
)
from app.components.branding import (
    show_fixed_logo, hero, sidebar_context, eyebrow, step_marker,
)

inject_global_css()
sidebar_context()

# ── Paths ─────────────────────────────────────────────────────────────────────
INPUT_CSV = Path("data/input/rne_companies.csv")

# Columns the extraction produces — shown to the user so a CSV import matches.
EXPECTED_CSV_COLUMNS = [
    "identifiant_unique", "fr_denomination", "fr_activite_principale",
    "ar_activite_principale", "fr_adresse", "ar_adresse", "capital",
    "date_immatriculation", "date_debut_activite", "fr_dirigeant",
]

# ── Session state init ──────────────────────────────────────────────────────────
st.session_state.setdefault("uploaded_ok", False)
st.session_state.setdefault("run_complete", False)


hero(
    "Import",
    "your data",
    "Add official RNE documents or a ready company file. We read each business, "
    "classify its sector, and prepare it for your team.",
)

section_divider()


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — choose and provide input
# ──────────────────────────────────────────────────────────────────────────────

eyebrow("Your data")
step_marker(index=1, total=3, label="Choose what to import")

mode = st.radio(
    "What would you like to import?",
    ["RNE documents (PDF)", "A ready company file (CSV)"],
    horizontal=True,
)

uploaded_files = None
uploaded_csv   = None

if mode.startswith("RNE documents"):
    uploaded_files = st.file_uploader(
        "Drop your RNE PDF files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Add one file or a whole batch — we'll read them all.",
    )
    if uploaded_files:
        st.markdown(
            f"<div class='on-reveal' style='color:{SUCCESS}; font-weight:600;'>"
            f"✓ {len(uploaded_files)} document(s) ready.</div>",
            unsafe_allow_html=True,
        )
        st.session_state.uploaded_ok = True
    else:
        st.session_state.uploaded_ok = False
else:
    uploaded_csv = st.file_uploader(
        "Drop your company CSV here",
        type=["csv"],
        accept_multiple_files=False,
        help="A CSV with the same columns the extraction produces (listed below).",
    )

    # Show the expected schema so the user knows what a valid CSV looks like.
    cols_html = "".join(
        f'<span style="display:inline-block; background:rgba(255,255,255,0.04); '
        f'border:1px solid {NAVY_HAIRLINE}; border-radius:7px; padding:0.2rem 0.6rem; '
        f'margin:0.2rem; font-size:0.82rem; color:{OFF_WHITE}; font-family:monospace;">{c}</span>'
        for c in EXPECTED_CSV_COLUMNS
    )
    st.markdown(
        f"""
        <div class="on-card" style="margin-top:0.6rem; padding:1rem 1.1rem;">
            <div style="color:{MUTED}; font-size:0.82rem; text-transform:uppercase;
                 letter-spacing:0.06em; margin-bottom:0.5rem;">Expected columns</div>
            <div style="line-height:2;">{cols_html}</div>
            <div style="color:{MUTED}; font-size:0.86rem; margin-top:0.6rem;">
                Identifiers and the French/Arabic activity and address are the most useful.
                Missing columns are handled gracefully — they simply stay empty.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if uploaded_csv:
        st.markdown(
            f"<div class='on-reveal' style='color:{SUCCESS}; font-weight:600; margin-top:0.5rem;'>"
            f"✓ File ready.</div>",
            unsafe_allow_html=True,
        )
        st.session_state.uploaded_ok = True
    else:
        st.session_state.uploaded_ok = False


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — options (revealed once input is provided)
# ──────────────────────────────────────────────────────────────────────────────

rebuild_rag   = False
run_llm_audit = False

if st.session_state.uploaded_ok:
    section_divider()
    st.markdown('<div class="on-reveal">', unsafe_allow_html=True)
    eyebrow("Options")
    step_marker(index=2, total=3, label="Fine-tune the run (optional)")

    with st.expander("Advanced options", expanded=False):
        rebuild_rag = st.checkbox(
            "Refresh the knowledge base before classifying",
            value=False,
            help="Turn on after editing the sector rules or validated examples.",
        )
        run_llm_audit = st.checkbox(
            "Double-check uncertain businesses with the language model",
            value=False,
            help="More accurate on ambiguous activities. Requires the local model service.",
        )
    st.markdown("</div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# Stage 3 — run (revealed once input is provided)
# ──────────────────────────────────────────────────────────────────────────────

if st.session_state.uploaded_ok:
    section_divider()
    st.markdown('<div class="on-reveal">', unsafe_allow_html=True)
    eyebrow("Run")
    step_marker(index=3, total=3, label="Read, classify, and prepare your data")

    run_clicked = st.button("Start  →", type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

    if run_clicked:
        from pipeline.runner import run_pipeline

        # ── PDF upload: ingest into database first, then extract from DB ─
        if mode.startswith("RNE documents"):
            progress = st.progress(0, text="Storing documents…")
            status   = st.empty()

            # Step A: Ingest each PDF into MinIO + MongoDB
            try:
                from ingest import ingest_pdf
                from db.documents import ping as mongo_ping
                from storage.object_store import ping as minio_ping

                # Check that storage services are running
                if not mongo_ping():
                    st.error(
                        "Cannot connect to the document database (MongoDB). "
                        "Make sure Docker is running: `docker compose up -d`"
                    )
                    st.stop()
                if not minio_ping():
                    st.error(
                        "Cannot connect to the file store (MinIO). "
                        "Make sure Docker is running: `docker compose up -d`"
                    )
                    st.stop()

                ingested_count = 0
                duplicate_count = 0
                failed_names = []

                for i, f in enumerate(uploaded_files, start=1):
                    progress.progress(
                        int((i / len(uploaded_files)) * 30),
                        text=f"Storing document {i}/{len(uploaded_files)}…",
                    )

                    # Save to a temp file so ingest_pdf can read it
                    with tempfile.NamedTemporaryFile(
                        suffix=".pdf", delete=False, prefix="rne_upload_"
                    ) as tmp:
                        tmp.write(f.read())
                        tmp_path = tmp.name

                    try:
                        _, ingest_status = ingest_pdf(tmp_path)
                        if ingest_status == "ingested":
                            ingested_count += 1
                        else:
                            duplicate_count += 1
                    except Exception as e:
                        failed_names.append(f"{f.name}: {e}")
                    finally:
                        # Clean up the temp file
                        Path(tmp_path).unlink(missing_ok=True)

                # Report ingestion results
                parts = [f"Stored **{ingested_count}** new document(s)"]
                if duplicate_count:
                    parts.append(f"**{duplicate_count}** already in the database")
                if failed_names:
                    parts.append(f"**{len(failed_names)}** failed")
                status.markdown(
                    f"<p style='color:{OFF_WHITE};'>{' · '.join(parts)}.</p>",
                    unsafe_allow_html=True,
                )

                if failed_names:
                    st.warning("Some files could not be stored: " + "; ".join(failed_names))

            except ImportError:
                st.error(
                    "Storage modules not found. Make sure `ingest.py`, "
                    "`db/documents.py`, and `storage/object_store.py` are in the project."
                )
                st.stop()

            # Step B: Run the pipeline with from_db=True
            from_db          = True
            skip_extraction  = False

        # ── CSV upload: save locally, skip extraction (unchanged) ────────
        else:
            INPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
            with open(INPUT_CSV, "wb") as out:
                shutil.copyfileobj(uploaded_csv, out)
            from_db          = False
            skip_extraction  = True
            progress = st.progress(0, text="Getting ready…")
            status   = st.empty()

        # ── Run the pipeline ─────────────────────────────────────────────
        STEP_MESSAGES = {
            "extraction":   "Reading your documents…",
            "rag_build":    "Refreshing the knowledge base…",
            "segmentation": "Classifying companies into sectors…",
            "analysis":     "Preparing your view…",
            "llm_audit":    "Double-checking uncertain businesses…",
        }
        STEP_ORDER = ["extraction", "rag_build", "segmentation", "analysis", "llm_audit"]

        def on_step_start(step_name, ctx):
            idx = STEP_ORDER.index(step_name) if step_name in STEP_ORDER else 0
            msg = STEP_MESSAGES.get(step_name, step_name)
            # Start progress at 30% (ingestion took 0–30%), pipeline is 30–100%
            pct = 30 + int((idx / len(STEP_ORDER)) * 70)
            progress.progress(pct, text=msg)
            status.markdown(
                f"<p style='color:{MUTED}; margin-top:0.4rem;'>{msg}</p>",
                unsafe_allow_html=True,
            )

        def on_step_end(step_name, ctx):
            idx = STEP_ORDER.index(step_name) if step_name in STEP_ORDER else 0
            pct = 30 + int(((idx + 1) / len(STEP_ORDER)) * 70)
            progress.progress(pct,
                              text=f"Done — {STEP_MESSAGES.get(step_name, step_name)}")

        try:
            result = run_pipeline(
                extraction_output_csv=str(INPUT_CSV),
                skip_extraction=skip_extraction,
                skip_rag_rebuild=not rebuild_rag,
                run_llm_audit=run_llm_audit,
                from_db=from_db,
                on_step_start=on_step_start,
                on_step_end=on_step_end,
            )

            progress.progress(100, text="Complete")
            status.empty()

            summary = result.get("segmentation_results")
            if summary:
                st.session_state["last_summary"] = summary
                st.session_state.run_complete = True

            section_divider()
            st.markdown(
                f"""
                <div class="on-card on-card-accent on-reveal" style="margin-bottom:1rem;">
                    <div style="display:flex; align-items:center; gap:0.6rem;">
                        <span style="font-size:1.4rem;">✓</span>
                        <span style="color:{WHITE}; font-size:1.2rem; font-weight:700;">
                            Done. Your data is ready.
                        </span>
                    </div>
                    <p style="color:{OFF_WHITE}; margin:0.4rem 0 0 0;">
                        Explore the full breakdown in <b>Overview</b>, or jump to your
                        call-ready list in <b>Company Directory</b>.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if summary:
                c1, c2, c3, c4 = st.columns(4)
                total = summary.get("total_rows", 0)
                empty = summary.get("empty_activities", 0)
                c1.metric("Companies read", f"{total:,}")
                c2.metric("Classified", f"{total - empty:,}")
                c3.metric("Needs review", f"{summary.get('needs_review', 0):,}")
                c4.metric("No activity", f"{empty:,}")

            # Clickable route to the Overview page
            if st.button("Open Overview  →", type="primary", key="to_overview"):
                st.switch_page("pages/overview.py")

            if result.get("errors"):
                st.warning(
                    "The run finished, but some steps reported issues: "
                    + "; ".join(result["errors"])
                )

        except Exception as e:
            progress.empty()
            status.empty()
            st.error(
                f"We couldn't finish the run. {e}  \n"
                "Check that your file matches the expected format and try again."
            )

else:
    # Invitation, with a clear hint of what happens next.
    st.markdown(
        f"""
        <div class="on-card" style="margin-top:1.2rem; text-align:center; opacity:0.92;">
            <p style="color:{MUTED}; margin:0; font-size:1.02rem;">
                Choose your data above to begin — the next steps appear here automatically.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

show_fixed_logo()
