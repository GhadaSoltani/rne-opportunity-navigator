"""
Folder watcher. Drop PDFs into ./incoming/ and they get auto-ingested.
Run with:  python watch_ingest.py
Stop with Ctrl+C.
"""

import os
import time
import shutil
from pathlib import Path
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ingest import ingest_pdf
from db.documents import ensure_indexes, ping as mongo_ping
from storage.object_store import ping as minio_ping

load_dotenv()
WATCH_DIR = os.getenv("INCOMING_DIR", "./incoming")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "./incoming/processed")


def wait_until_stable(path: str, checks: int = 3, interval: float = 1.0, max_wait: int = 120) -> bool:
    """Wait until a file's size stops changing — avoids reading a half-copied PDF."""
    last_size, stable_count = -1, 0
    elapsed = 0.0
    while elapsed < max_wait:
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            return False
        if size == last_size and size > 0:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            stable_count = 0
            last_size = size
        time.sleep(interval)
        elapsed += interval
    return False


def process_one(path: str):
    if not path.lower().endswith(".pdf"):
        return
    print(f"[detected] {path}")
    if not wait_until_stable(path):
        print(f"[skipped]  {path} (never stabilized)")
        return
    try:
        doc_id, status = ingest_pdf(path)
        print(f"[{status}]  {path} -> {doc_id}")
        Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
        dest = os.path.join(PROCESSED_DIR, os.path.basename(path))
        # if a same-named file is already in processed (e.g. re-drop of a duplicate), don't clobber
        if os.path.exists(dest):
            stem, ext = os.path.splitext(os.path.basename(path))
            dest = os.path.join(PROCESSED_DIR, f"{stem}_{int(time.time())}{ext}")
        shutil.move(path, dest)
    except Exception as e:
        print(f"[FAILED]   {path} ({e})")


class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            process_one(event.src_path)

    def on_moved(self, event):
        if not event.is_directory and getattr(event, "dest_path", None):
            process_one(event.dest_path)


def scan_existing():
    """Catch any PDFs already sitting in incoming/ when the watcher starts.
    These files aren't 'in motion' — no need to wait for stability."""
    for name in os.listdir(WATCH_DIR):
        full = os.path.join(WATCH_DIR, name)
        if os.path.isfile(full) and name.lower().endswith(".pdf"):
            try:
                doc_id, status = ingest_pdf(full)
                print(f"[{status}]  {full} -> {doc_id}")
                Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
                dest = os.path.join(PROCESSED_DIR, name)
                if os.path.exists(dest):
                    stem, ext = os.path.splitext(name)
                    dest = os.path.join(PROCESSED_DIR, f"{stem}_{int(time.time())}{ext}")
                shutil.move(full, dest)
            except Exception as e:
                print(f"[FAILED]   {full} ({e})")


def main():
    print("checking MongoDB...")
    if not mongo_ping():
        print("FAILED: cannot reach MongoDB. Aborting.")
        return
    print("  OK")

    print("checking MinIO...")
    if not minio_ping():
        print("FAILED: cannot reach MinIO. Aborting.")
        return
    print("  OK")

    ensure_indexes()
    Path(WATCH_DIR).mkdir(parents=True, exist_ok=True)
    Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)

    print(f"\nsweeping existing files in {WATCH_DIR}...")
    scan_existing()

    observer = Observer()
    observer.schedule(PDFHandler(), WATCH_DIR, recursive=False)
    observer.start()
    print(f"\nWatching {WATCH_DIR}\\ for new PDFs. Drop files in to ingest. Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()