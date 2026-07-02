"""
pipeline/runner.py
==================
Orchestrates the full pipeline:
    Step 1  — Extraction:     PDF files → rne_companies.csv
              TWO MODES:
                (a) from local folder  (original — unchanged)
                (b) from database      (new — pulls PDFs from MinIO)
    Step 1b — RAG build:      taxonomy + validated_examples → rag_knowledge_base.csv
    Step 2  — Segmentation:   rne_companies.csv → rne_companies_segmented.csv
    Step 3  — Analysis:       rne_companies_segmented.csv → analytical CSVs
    Step 4  — LLM audit:      optional — re-examines risky rows via Ollama

Each step is independently importable and callable.
Adding a new step means adding one function call here — nothing else changes.
"""

import logging
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

def _run_extraction(ctx: dict) -> dict:
    """
    Step 1: Extract PDFs → rne_companies.csv

    Two modes, selected by the `from_db` flag in the context:

        from_db=True  (new):
            Pull PDFs from MinIO (already ingested via ingest.py),
            run extraction, update MongoDB status.
            Does NOT need a pdf_folder.

        from_db=False (original):
            Read PDFs from a local folder on disk.
            Needs pdf_folder set in the context.
    """
    output_csv = Path(ctx["extraction_output_csv"])

    if ctx.get("from_db"):
        # ── NEW: extract from MinIO + MongoDB ────────────────────────
        from extraction.db_extract import extract_from_db

        logger.info("Step 1 — Extraction (from database)")
        logger.info("  Output dir : %s", output_csv.parent)

        result = extract_from_db(
            output_dir=str(output_csv.parent),
            limit=ctx.get("extraction_limit", 0),
            keep_mixed=ctx.get("keep_mixed", False),
        )

        ctx["extraction_done"] = True
        ctx["extraction_results"] = result
        return ctx

    # ── ORIGINAL: extract from local folder (unchanged) ──────────────
    from extraction.run_batch import run_batch

    pdf_folder = ctx["pdf_folder"]
    keep_mixed = ctx.get("keep_mixed", False)

    logger.info("Step 1 — Extraction (from local folder)")
    logger.info("  PDF folder : %s", pdf_folder)
    logger.info("  Output CSV : %s", output_csv)

    run_batch(
        input_dir=Path(pdf_folder),
        output_dir=output_csv.parent,
        keep_mixed=keep_mixed,
    )

    ctx["extraction_done"] = True
    return ctx


def _run_rag_build(ctx: dict) -> dict:
    """
    Step 1b: Rebuild RAG knowledge base.
    Run this whenever taxonomy or validated_examples change.
    Skipped if rag_knowledge_base.csv already exists and skip_rag_rebuild=True.
    """
    from segmentation.rag_knowledge_builder import build_rag_knowledge_base

    rag_path = ctx.get("rag_knowledge_path", Path("knowledge/rag_knowledge_base.csv"))
    skip     = ctx.get("skip_rag_rebuild", False)

    if skip and Path(rag_path).exists():
        logger.info("Step 1b — RAG build skipped (already exists)")
        return ctx

    logger.info("Step 1b — Building RAG knowledge base")
    build_rag_knowledge_base()
    return ctx


def _run_segmentation(ctx: dict) -> dict:
    """Step 2: Classify companies from rne_companies.csv."""
    from segmentation.main import run_segmentation

    input_csv = ctx.get("extraction_output_csv") or ctx.get("segmentation_input_csv")

    logger.info("Step 2 — Segmentation")
    logger.info("  Input CSV : %s", input_csv)

    results = run_segmentation(input_csv=str(input_csv))

    ctx["segmentation_done"] = True
    ctx["segmentation_results"] = results
    return ctx


def _run_analysis(ctx: dict) -> dict:
    """
    Step 3: Run the analysis layer.
    Reads rne_companies_segmented.csv and builds the analytical CSVs.
    """
    if not ctx.get("run_analysis", True):
        logger.info("Step 3 — Analysis skipped (set run_analysis=True to enable)")
        return ctx

    from analysis.main import run_analysis
    from segmentation.config import OUTPUT_CSV

    logger.info("Step 3 — Analysis")
    logger.info("  Input CSV : %s", OUTPUT_CSV)

    results = run_analysis(input_csv=str(OUTPUT_CSV))

    ctx["analysis_done"] = True
    ctx["analysis_results"] = results
    return ctx


def _run_llm_audit(ctx: dict) -> dict:
    """
    Step 4 (optional): LLM audit on risky rows.
    Only runs if run_llm_audit=True in context.
    Requires Ollama running locally.
    """
    from segmentation.llm_full_auditor import audit_all_rows

    if not ctx.get("run_llm_audit", False):
        logger.info("Step 4 — LLM audit skipped (set run_llm_audit=True to enable)")
        return ctx

    logger.info("Step 4 — LLM audit")

    audit_all_rows(
        limit=ctx.get("llm_audit_limit", None),
        sleep_seconds=ctx.get("llm_sleep_seconds", 0.1),
        only_risky=True,
        checkpoint_every=20,
        resume=True,
    )

    ctx["llm_audit_done"] = True
    return ctx


# ---------------------------------------------------------------------------
# Pipeline steps in order
# ---------------------------------------------------------------------------

PIPELINE_STEPS = [
    {"name": "extraction",   "fn": _run_extraction},
    {"name": "rag_build",    "fn": _run_rag_build},
    {"name": "segmentation", "fn": _run_segmentation},
    {"name": "analysis",     "fn": _run_analysis},
    {"name": "llm_audit",    "fn": _run_llm_audit},
]


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_pipeline(
    pdf_folder: str | Path | None = None,
    extraction_output_csv: str | Path = "data/input/rne_companies.csv",
    segmentation_input_csv: str | Path | None = None,
    skip_extraction: bool = False,
    skip_rag_rebuild: bool = True,
    run_analysis: bool = True,
    run_llm_audit: bool = False,
    llm_audit_limit: int | None = None,
    keep_mixed: bool = False,
    from_db: bool = False,
    on_step_start: Callable | None = None,
    on_step_end: Callable | None = None,
) -> dict:
    """
    Run the full pipeline end-to-end.

    Args:
        pdf_folder:
            Folder containing PDF files to extract.
            Required unless skip_extraction=True or from_db=True.

        extraction_output_csv:
            Where extraction writes rne_companies.csv.
            Also used as segmentation input unless segmentation_input_csv is set.

        segmentation_input_csv:
            Override segmentation input CSV.

        skip_extraction:
            Skip the extraction step entirely.

        skip_rag_rebuild:
            Skip rebuilding the RAG knowledge base if it already exists.

        run_analysis:
            Run the analysis layer after segmentation. Default True.

        run_llm_audit:
            Run LLM audit on risky rows after segmentation.

        llm_audit_limit:
            Max rows to audit. None = all risky rows.

        keep_mixed:
            Keep intermediate _mixed.txt files after extraction.

        from_db:
            NEW — If True, extraction pulls PDFs from MinIO/MongoDB
            instead of from a local folder. pdf_folder is ignored.

        on_step_start / on_step_end:
            Optional callbacks for progress updates.
    """

    ctx = {
        "pdf_folder":              Path(pdf_folder) if pdf_folder else None,
        "extraction_output_csv":   Path(extraction_output_csv),
        "segmentation_input_csv":  Path(segmentation_input_csv) if segmentation_input_csv else None,
        "skip_extraction":         skip_extraction,
        "skip_rag_rebuild":        skip_rag_rebuild,
        "run_analysis":            run_analysis,
        "run_llm_audit":           run_llm_audit,
        "llm_audit_limit":         llm_audit_limit,
        "keep_mixed":              keep_mixed,
        "from_db":                 from_db,
        "extraction_done":         False,
        "segmentation_done":       False,
        "analysis_done":           False,
        "llm_audit_done":          False,
        "errors":                  [],
    }

    logger.info("=" * 60)
    logger.info("RNE PLATFORM — PIPELINE START")
    logger.info("=" * 60)

    start_time = time.time()

    for step in PIPELINE_STEPS:
        step_name = step["name"]

        # Decide whether to skip extraction
        if step_name == "extraction":
            if skip_extraction:
                logger.info("Step — extraction SKIPPED")
                continue
            # Need either from_db or a pdf_folder to run extraction
            if not from_db and ctx["pdf_folder"] is None:
                logger.info("Step — extraction SKIPPED (no pdf_folder and not from_db)")
                continue

        try:
            if on_step_start:
                on_step_start(step_name, ctx)

            ctx = step["fn"](ctx)

            if on_step_end:
                on_step_end(step_name, ctx)

        except Exception as e:
            error_msg = f"Step '{step_name}' failed: {e}"
            logger.error(error_msg)
            ctx["errors"].append(error_msg)

            # Segmentation failure is fatal — stop the pipeline
            if step_name == "segmentation":
                raise

            # Other failures are logged but not fatal
            continue

    elapsed = round(time.time() - start_time, 1)

    logger.info("=" * 60)
    logger.info("RNE PLATFORM — PIPELINE DONE (%ss)", elapsed)
    if ctx["errors"]:
        logger.warning("Errors: %s", ctx["errors"])
    logger.info("=" * 60)

    return ctx
