"""
extraction/db_extract.py
========================
Bridge between the storage layer (MinIO + MongoDB) and the existing
extraction pipeline.

This module does NOT contain any extraction logic. It only handles:
    - "Where does the PDF come from?"   → MinIO
    - "Where do we record the result?"  → MongoDB

The actual extraction is done by process_one_pdf() from run_batch.py,
which is called exactly as before, with a normal file path.

Flow per document:
    1. Query MongoDB for documents with status="uploaded", not yet extracted
    2. Download the PDF from MinIO to a temporary folder
    3. Call process_one_pdf(temp_pdf_path, output_dir)  ← unchanged logic
    4. If OK:   mark_extracted(doc_id) in MongoDB
       If FAIL: mark_extraction_failed(doc_id, error) in MongoDB
    5. Clean up temp folder (best-effort — never crashes if Windows locks the file)
"""

import gc
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from db.documents import (
    get_pending_extraction,
    mark_extracted,
    mark_extraction_failed,
)
from storage.object_store import download_pdf
from extraction.run_batch import process_one_pdf

logger = logging.getLogger(__name__)


def _safe_cleanup(tmp_dir: str, retries: int = 3, delay: float = 1.0):
    """
    Try to delete a temp folder. On Windows, PDF libraries (Camelot, PyMuPDF)
    sometimes hold file handles for a moment after returning. If deletion
    fails, wait and retry. If it still fails, log a warning and move on —
    the OS will clean it up later. Never crash.
    """
    for attempt in range(retries):
        try:
            # Force Python to release any lingering file handles
            gc.collect()
            shutil.rmtree(tmp_dir)
            return
        except PermissionError:
            time.sleep(delay * (attempt + 1))
        except Exception:
            break
    # Not critical — Windows cleans up %TEMP% periodically
    logger.warning("Could not delete temp folder %s (file still locked). "
                   "It will be cleaned up by the OS.", tmp_dir)


def extract_from_db(
    output_dir: str = "data/input",
    limit: int = 0,
    keep_mixed: bool = False,
    no_sqlite: bool = False,
) -> dict:
    """
    Pull unprocessed PDFs from MinIO, extract each one, update MongoDB.

    Args:
        output_dir:  Where rne_companies.csv and rne_audit.csv are written.
                     Same folder that run_batch uses — the rest of the
                     pipeline reads from here.
        limit:       Max documents to process. 0 = all pending.
        keep_mixed:  Keep the intermediate _mixed.txt files (debugging).
        no_sqlite:   Skip the per-PDF SQLite output.

    Returns:
        {"total": N, "ok": N, "failed": N}
    """
    pending = get_pending_extraction(limit=limit)

    if not pending:
        logger.info("No pending documents to extract.")
        return {"total": 0, "ok": 0, "failed": 0}

    logger.info("Found %d document(s) pending extraction.", len(pending))

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    fail_count = 0

    for i, doc in enumerate(pending, start=1):
        doc_id = doc["_id"]
        filename = doc.get("filename", "unknown.pdf")
        obj_key = doc.get("object_key", "")

        if not obj_key:
            logger.warning(
                "[%d/%d] %s — no object_key in MongoDB, skipping.",
                i, len(pending), filename,
            )
            mark_extraction_failed(doc_id, "missing object_key in document record")
            fail_count += 1
            continue

        logger.info("[%d/%d] Extracting: %s", i, len(pending), filename)

        # Create the temp dir manually (NOT as a context manager) so we
        # control cleanup ourselves and never crash on Windows file locks.
        tmp_dir = tempfile.mkdtemp(prefix="rne_extract_")
        local_pdf = os.path.join(tmp_dir, filename)

        try:
            # ── Step A: Download from MinIO to temp file ─────────────
            download_pdf(obj_key, local_pdf)
            logger.info("  Downloaded -> %s (%d bytes)",
                        local_pdf, os.path.getsize(local_pdf))

            # ── Step B: Run the EXISTING extraction logic ────────────
            # process_one_pdf sees a normal file path — it has no idea
            # the file was just pulled from MinIO.
            result = process_one_pdf(
                pdf_path=Path(local_pdf),
                output_dir=output_path,
                keep_mixed=keep_mixed,
                no_sqlite=no_sqlite,
            )

            # ── Step C: Update MongoDB with the outcome ──────────────
            if result["status"] == "ok":
                company_id = result.get("id", "")
                mark_extracted(doc_id, company_id=company_id)
                ok_count += 1
                logger.info("  OK: %s -> company ID=%s", filename, company_id)
            else:
                error_msg = result.get("error", "unknown extraction error")
                mark_extraction_failed(doc_id, error_msg)
                fail_count += 1
                logger.error("  FAILED: %s — %s", filename, error_msg)

        except Exception as e:
            mark_extraction_failed(doc_id, str(e))
            fail_count += 1
            logger.error("  FAILED: %s — %s", filename, e)

        finally:
            # ── Step D: Clean up temp folder (best-effort) ───────────
            # This NEVER crashes, even if Windows still has the file locked.
            _safe_cleanup(tmp_dir)

    summary = {
        "total": len(pending),
        "ok": ok_count,
        "failed": fail_count,
    }

    logger.info("=" * 50)
    logger.info("DB extraction complete: %s", summary)
    logger.info("=" * 50)
    return summary
