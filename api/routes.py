"""
api/routes.py
=============
FastAPI interface for Opportunity Navigator.

Today: mostly used as a backend for the Streamlit dashboard.
Future: other Ooredoo systems call these endpoints programmatically.

Start:
    python run.py --api
    or
    uvicorn api.routes:app --host 0.0.0.0 --port 8000 --reload

Interactive docs: http://localhost:8000/docs
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pipeline.runner import run_pipeline
from segmentation.config import OUTPUT_CSV, AUDIT_CSV, REVIEW_CSV

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Opportunity Navigator API",
    description="PDF extraction + company sector segmentation pipeline.",
    version="1.0.0",
)

# CORS — open for internal use. Restrict allow_origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state. Replace with Redis/DB when scaling to many workers.
_state: dict = {
    "status": "idle",       # idle | running | done | error
    "last_summary": None,
    "last_error": None,
}

PDF_UPLOAD_DIR = Path("data/input")
INPUT_CSV      = Path("data/input/rne_companies.csv")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB per file


# ── Background wrapper ────────────────────────────────────────────────────────
def _run_bg(ctx: dict):
    _state["status"] = "running"
    _state["last_error"] = None
    try:
        result = run_pipeline(**ctx)
        _state["status"] = "done"
        _state["last_summary"] = result.get("segmentation_results")
    except Exception as e:
        _state["status"] = "error"
        _state["last_error"] = str(e)


# ── Meta ──────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"app": "Opportunity Navigator", "version": "1.0.0", "status": _state["status"]}


@app.get("/pipeline/status")
def pipeline_status():
    return {"status": _state["status"], "error": _state["last_error"]}


# ── Run full pipeline (extraction + segmentation) ─────────────────────────────
@app.post("/pipeline/run")
def run_full(
    background_tasks: BackgroundTasks,
    pdf_folder: str = "data/input/pdfs",
    run_llm_audit: bool = False,
    rebuild_rag: bool = False,
):
    if _state["status"] == "running":
        raise HTTPException(409, "Pipeline already running.")

    ctx = {
        "pdf_folder":       pdf_folder,
        "skip_extraction":  False,
        "skip_rag_rebuild": not rebuild_rag,
        "run_llm_audit":    run_llm_audit,
    }
    background_tasks.add_task(_run_bg, ctx)
    return {"message": "Pipeline started.", "status": "running"}


# ── Upload PDFs then run ──────────────────────────────────────────────────────
@app.post("/pipeline/upload-pdfs")
async def upload_pdfs(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    run_llm_audit: bool = False,
    rebuild_rag: bool = False,
):
    if _state["status"] == "running":
        raise HTTPException(409, "Pipeline already running.")

    PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"Only PDF files are accepted. Got: {f.filename!r}")
        dest = PDF_UPLOAD_DIR / Path(f.filename).name
        content = await f.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"File {f.filename!r} exceeds the 200 MB limit.")
        dest.write_bytes(content)
        saved.append(f.filename)

    ctx = {
        "pdf_folder":       str(PDF_UPLOAD_DIR),
        "skip_extraction":  False,
        "skip_rag_rebuild": not rebuild_rag,
        "run_llm_audit":    run_llm_audit,
    }
    background_tasks.add_task(_run_bg, ctx)
    return {"message": "PDFs uploaded, pipeline started.", "files": saved, "status": "running"}


# ── Upload a CSV and segment only ─────────────────────────────────────────────
@app.post("/pipeline/segment")
async def segment_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    run_llm_audit: bool = False,
    rebuild_rag: bool = False,
):
    if _state["status"] == "running":
        raise HTTPException(409, "Pipeline already running.")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, f"Only CSV files are accepted. Got: {file.filename!r}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File {file.filename!r} exceeds the 200 MB limit.")
    INPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    INPUT_CSV.write_bytes(content)

    ctx = {
        "pdf_folder":            None,
        "extraction_output_csv": str(INPUT_CSV),
        "skip_extraction":       True,
        "skip_rag_rebuild":      not rebuild_rag,
        "run_llm_audit":         run_llm_audit,
    }
    background_tasks.add_task(_run_bg, ctx)
    return {"message": "CSV uploaded, segmentation started.", "status": "running"}


# ── Results ───────────────────────────────────────────────────────────────────
@app.get("/results/summary")
def get_summary():
    if _state["status"] == "idle":
        raise HTTPException(404, "No pipeline run yet.")
    if _state["status"] == "running":
        raise HTTPException(202, "Pipeline still running.")
    if _state["status"] == "error":
        raise HTTPException(500, _state["last_error"])
    return _state["last_summary"] or {"message": "No summary available."}


@app.get("/results/download")
def download_segmented():
    if not Path(OUTPUT_CSV).exists():
        raise HTTPException(404, "No segmented CSV found.")
    return FileResponse(str(OUTPUT_CSV), media_type="text/csv", filename="rne_companies_segmented.csv")


@app.get("/results/download/audit")
def download_audit():
    if not Path(AUDIT_CSV).exists():
        raise HTTPException(404, "No audit CSV found.")
    return FileResponse(str(AUDIT_CSV), media_type="text/csv", filename="classification_audit.csv")


@app.get("/results/download/review")
def download_review():
    if not Path(REVIEW_CSV).exists():
        raise HTTPException(404, "No review CSV found.")
    return FileResponse(str(REVIEW_CSV), media_type="text/csv", filename="review_needed.csv")


# ── LLM audit ─────────────────────────────────────────────────────────────────
@app.post("/pipeline/llm-audit")
def trigger_llm_audit(background_tasks: BackgroundTasks, limit: Optional[int] = None):
    if _state["status"] == "running":
        raise HTTPException(409, "Pipeline already running.")

    ctx = {
        "pdf_folder":       None,
        "skip_extraction":  True,
        "skip_rag_rebuild": True,
        "run_llm_audit":    True,
        "llm_audit_limit":  limit,
    }
    background_tasks.add_task(_run_bg, ctx)
    return {"message": "LLM audit started.", "status": "running"}