"""
ingest.py
=========
Idempotent PDF ingestion: hash the file, upload to MinIO, record in MongoDB.

If the same file (by content, not name) is ingested twice, the second call
is a no-op that returns the existing document ID with status "duplicate".

Changes from original:
    - _with_retries:   retries network calls (MinIO upload, Mongo insert)
                       so a 1-second blip doesn't lose a file
    - _looks_like_pdf: rejects corrupt/empty/renamed files before hashing
"""

import os
import time
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from storage.object_store import compute_sha256, upload_pdf
from db.documents import documents


# ── Helpers ──────────────────────────────────────────────────────────────────

def _with_retries(fn, *args, retries: int = 3, delay: float = 1.0, **kwargs):
    """
    Call fn(*args, **kwargs) up to `retries` times.
    If it fails every time, re-raise the last exception.
    Waits 1s, 2s, 3s between attempts (linear backoff).
    """
    last_err = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            time.sleep(delay * (attempt + 1))
    raise last_err


def _looks_like_pdf(path: str) -> bool:
    """
    Quick sanity check: file is non-empty and starts with %PDF-.
    Catches renamed .txt files, corrupt downloads, zero-byte placeholders.
    """
    try:
        if os.path.getsize(path) == 0:
            return False
        with open(path, "rb") as f:
            header = f.read(5)
        return header == b"%PDF-"
    except OSError:
        return False


# ── Main entry point ─────────────────────────────────────────────────────────

def ingest_pdf(
    path: str,
    company: str = "UNKNOWN",
    document_type: str = "unclassified",
):
    """
    Idempotent ingest: hash → upload → record.

    Returns:
        (doc_id, status)  where status is "ingested" or "duplicate".

    Raises:
        FileNotFoundError if the file doesn't exist.
        ValueError if the file isn't a valid PDF.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PDF not found: {path}")

    if not _looks_like_pdf(path):
        raise ValueError(f"Not a valid PDF (bad header or empty): {path}")

    sha = compute_sha256(path)

    # Check for duplicate (same content, possibly different filename)
    existing = documents.find_one({"sha256": sha})
    if existing:
        return existing["_id"], "duplicate"

    # Upload to MinIO (with retries)
    key = _with_retries(upload_pdf, path, sha)

    # Record in MongoDB (with retries)
    doc = {
        "filename":         os.path.basename(path),
        "company":          company,
        "document_type":    document_type,
        "sha256":           sha,
        "object_key":       key,
        "size_bytes":       os.path.getsize(path),
        "upload_date":      datetime.now(timezone.utc),
        "status":           "uploaded",
        "pipeline_version": 1,
        "stages": {
            "extracted": None,
            "chunked":   None,
            "embedded":  None,
            "indexed":   None,
        },
        "error": None,
    }

    try:
        result = _with_retries(documents.insert_one, doc)
        return result.inserted_id, "ingested"
    except DuplicateKeyError:
        # Race condition: another process ingested the same file between
        # our find_one and insert_one — treat as duplicate.
        return documents.find_one({"sha256": sha})["_id"], "duplicate"
