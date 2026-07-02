"""
storage/object_store.py
=======================
MinIO object store — stores the actual PDF files.

Original: compute_sha256, object_key, upload_pdf, presigned_url, ping.
Added:    download_pdf — used by db_extract.py to pull a PDF back to disk
          so the existing extraction code can read it like a normal file.
"""

import hashlib
import os
from datetime import timedelta

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

load_dotenv()

_client = Minio(
    os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False,
)
BUCKET = os.getenv("MINIO_BUCKET", "rne-docs")


def compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def object_key(sha256: str) -> str:
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}.pdf"


def upload_pdf(path: str, sha256: str) -> str:
    key = object_key(sha256)
    _client.fput_object(BUCKET, key, path, content_type="application/pdf")
    return key


def download_pdf(key: str, dest_path: str) -> str:
    """
    Download a PDF from MinIO to a local file.

    Used by extraction/db_extract.py: it downloads the PDF to a temp folder,
    then hands that file path to the existing extraction functions (which
    expect a normal local file — they don't know about MinIO).

    Args:
        key:       The object key in MinIO (e.g. "ab/cd/abcd...pdf").
        dest_path: Where to write the file locally.

    Returns:
        dest_path (same as input, for convenience).
    """
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    _client.fget_object(BUCKET, key, dest_path)
    return dest_path


def presigned_url(key: str, expires_seconds: int = 3600) -> str:
    return _client.presigned_get_object(
        BUCKET, key, expires=timedelta(seconds=expires_seconds)
    )


def ping() -> bool:
    """Quick connectivity check."""
    try:
        _client.bucket_exists(BUCKET)
        return True
    except S3Error as e:
        print(f"MinIO error: {e}")
        return False
    except Exception as e:
        print(f"MinIO unreachable: {e}")
        return False
