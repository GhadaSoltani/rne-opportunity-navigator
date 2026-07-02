"""
db/documents.py
===============
MongoDB document collection — stores metadata for every ingested PDF.

Original: ensure_indexes, ping.
Added:    get_pending_extraction, mark_extracted, mark_extraction_failed,
          count_by_status — used by the new DB-based extraction flow.
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError

load_dotenv()

_client = MongoClient(
    os.getenv("MONGO_URI"),
    serverSelectionTimeoutMS=5000,
)
db = _client["rne_database"]
documents = db["documents"]


def ensure_indexes():
    documents.create_index([("sha256", ASCENDING)], unique=True)
    documents.create_index([("status", ASCENDING)])
    documents.create_index([("company", ASCENDING)])


def ping() -> bool:
    """Quick connectivity check."""
    try:
        _client.admin.command("ping")
        return True
    except ServerSelectionTimeoutError as e:
        print(f"MongoDB unreachable: {e}")
        return False


# ── Extraction workflow helpers ──────────────────────────────────────────────

def get_pending_extraction(limit: int = 0) -> list:
    """
    Return documents that have been uploaded to MinIO but not yet extracted.
    Sorted oldest-first so we process in upload order.
    """
    query = {
        "status": "uploaded",
        "stages.extracted": None,
    }
    cursor = documents.find(query).sort("upload_date", 1)
    if limit > 0:
        cursor = cursor.limit(limit)
    return list(cursor)


def mark_extracted(doc_id, company_id: str = ""):
    """
    Called after a PDF is successfully extracted.
    Sets the extraction timestamp and stores the company ID we found inside.
    """
    documents.update_one(
        {"_id": doc_id},
        {"$set": {
            "stages.extracted": datetime.now(timezone.utc),
            "status": "extracted",
            "company": company_id,
            "error": None,
        }},
    )


def mark_extraction_failed(doc_id, error_msg: str):
    """
    Called when extraction fails for a PDF.
    Keeps the document in the DB but flags it so we can investigate.
    """
    documents.update_one(
        {"_id": doc_id},
        {"$set": {
            "status": "extraction_failed",
            "error": error_msg,
        }},
    )


def count_by_status() -> dict:
    """
    Quick summary: {"uploaded": 12, "extracted": 340, "extraction_failed": 2}
    Used by the dashboard to show storage health.
    """
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    result = list(documents.aggregate(pipeline))
    return {r["_id"]: r["count"] for r in result}
