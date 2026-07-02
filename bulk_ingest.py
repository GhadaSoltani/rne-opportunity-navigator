"""
Bulk-import a folder of PDFs, several at a time.
Usage: python bulk_ingest.py /path/to/folder
"""
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from ingest import ingest_pdf
from db.documents import ensure_indexes, ping as mongo_ping
from storage.object_store import ping as minio_ping


def bulk_ingest(folder: str, workers: int = 12):
    paths = [
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
    ]
    print(f"Found {len(paths)} PDFs. Ingesting with {workers} workers...")

    counts = {"ingested": 0, "duplicate": 0, "failed": 0}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ingest_pdf, p): p for p in paths}
        for i, fut in enumerate(as_completed(futures), start=1):
            path = futures[fut]
            try:
                _, status = fut.result()
                counts[status] += 1
                print(f"[{i}/{len(paths)}] [{status}] {os.path.basename(path)}")
            except Exception as e:
                counts["failed"] += 1
                print(f"[{i}/{len(paths)}] [FAILED] {os.path.basename(path)} ({e})")

    print("\nDone:", counts)


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "./incoming"

    if not mongo_ping():
        print("Mongo unreachable — aborting.")
        sys.exit(1)
    if not minio_ping():
        print("MinIO unreachable — aborting.")
        sys.exit(1)

    ensure_indexes()
    bulk_ingest(folder)