"""
One-shot test. Usage:
    python test_one.py path\to\some.pdf

If you don't pass a path, it uses the first .pdf in the ./samples/ folder.
"""

import sys
import os
import glob

from db.documents import ensure_indexes, documents
from db.documents import ping as mongo_ping
from storage.object_store import presigned_url
from storage.object_store import ping as minio_ping
from ingest import ingest_pdf


def find_test_pdf() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1]
    matches = glob.glob("samples/*.pdf")
    return matches[0] if matches else None


def main():
    print("checking MongoDB...")
    if not mongo_ping():
        print("FAILED: cannot reach MongoDB. Check Phase 1 sanity checks.")
        sys.exit(1)
    print("  OK")

    print("checking MinIO...")
    if not minio_ping():
        print("FAILED: cannot reach MinIO. Is the container up? Is .env correct?")
        sys.exit(1)
    print("  OK")

    print("ensuring indexes...")
    ensure_indexes()
    print("  OK")

    pdf = find_test_pdf()
    if not pdf:
        print("\nNo PDF to test with.")
        print("Either:")
        print("  - put any PDF into the .\\samples\\ folder and rerun, OR")
        print("  - run:  python test_one.py C:\\path\\to\\some.pdf")
        sys.exit(1)

    if not os.path.isfile(pdf):
        print(f"FAILED: '{pdf}' is not a file.")
        sys.exit(1)

    print(f"\ningesting: {pdf}")
    doc_id, status = ingest_pdf(pdf, company="ABC", document_type="annual_report")
    print(f"  result: {status}  doc_id={doc_id}")

    print("re-ingesting same file (should say duplicate)...")
    doc_id2, status2 = ingest_pdf(pdf, company="ABC", document_type="annual_report")
    print(f"  result: {status2}  doc_id={doc_id2}")

    doc = documents.find_one({"_id": doc_id})
    print(f"\nMetadata stored:")
    print(f"  filename:   {doc['filename']}")
    print(f"  sha256:     {doc['sha256']}")
    print(f"  object_key: {doc['object_key']}")
    print(f"  size:       {doc['size_bytes']} bytes")
    print(f"  status:     {doc['status']}")

    url = presigned_url(doc["object_key"])
    print(f"\nDownload URL (paste into a browser):\n{url}\n")
    print("SUCCESS.")


if __name__ == "__main__":
    main()