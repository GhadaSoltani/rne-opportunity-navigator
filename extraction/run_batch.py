"""
BATCH PIPELINE — Process a folder of RNE PDFs into one clean CSV + SQLite.

Flow per PDF:
    1. extraction/step1_extract_mixed.py:
        PDF -> output/<name>_mixed.txt

    2. extraction/step5_mixed_to_company_csv.py:
        output/<name>_mixed.txt -> append one row to output/rne_companies.csv

    3. If successful:
        delete output/<name>_mixed.txt

Outputs:
    output/rne_companies.csv
    output/rne_audit.csv
    output/rne_companies.sqlite
    output/progress.json
    output/failed_pdfs.log

Usage:
    python -m extraction.run_batch --input-dir pdfs --output-dir output

Test only first 5 PDFs:
    python -m extraction.run_batch --input-dir pdfs --output-dir output --limit 5 --reset

Keep mixed txt files for debugging:
    python -m extraction.run_batch --input-dir pdfs --output-dir output --keep-mixed

Reprocess everything from scratch:
    python -m extraction.run_batch --input-dir pdfs --output-dir output --reset --reprocess
"""

import argparse
import json
import logging
import traceback
from pathlib import Path
from typing import Dict, List

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


from extraction.step1_extract_mixed import extract_mixed_text
from extraction.step5_mixed_to_company_csv import (
    parse_mixed_txt,
    enrich_missing_arabic_from_long_csv,
    append_row_csv,
    append_audit_csv,
    upsert_company_sqlite,
    insert_audit_sqlite,
    reset_outputs,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


PROGRESS_FILE = "progress.json"
FAILED_LOG = "failed_pdfs.log"


def find_pdfs(input_dir: Path) -> List[Path]:
    return sorted(input_dir.rglob("*.pdf"))


def load_progress(output_dir: Path) -> set:
    progress_path = output_dir / PROGRESS_FILE

    if not progress_path.exists():
        return set()

    try:
        with open(progress_path, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_progress(output_dir: Path, done: set) -> None:
    progress_path = output_dir / PROGRESS_FILE

    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f, ensure_ascii=False, indent=2)


def log_failure(output_dir: Path, pdf_path: Path, error: str, tb: str) -> None:
    failed_path = output_dir / FAILED_LOG

    with open(failed_path, "a", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"PDF: {pdf_path}\n")
        f.write(f"ERROR: {error}\n")
        f.write(tb)
        f.write("\n")


def delete_file_safely(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning(f"Could not delete {path}: {exc}")


def process_one_pdf(
    pdf_path: Path,
    output_dir: Path,
    keep_mixed: bool = False,
    fallback_debug: bool = False,
    no_sqlite: bool = False,
) -> Dict[str, str]:
    """
    Process one PDF.

    Returns:
        {
            "status": "ok" or "error",
            "pdf": "...",
            "id": "...",
            "mixed_path": "...",
            "error": "..."
        }
    """
    mixed_path = None

    try:
        logger.info(f"Processing: {pdf_path.name}")

        # Step 1: PDF -> mixed txt.
        mixed_path_str = extract_mixed_text(
            pdf_path=str(pdf_path),
            output_dir=str(output_dir),
            fallback_debug=fallback_debug,
        )

        mixed_path = Path(mixed_path_str)

        # Step 4: mixed txt -> final CSV/SQLite.
        row, audit_rows = parse_mixed_txt(str(mixed_path))

        row = enrich_missing_arabic_from_long_csv(
            row=row,
            mixed_path=str(mixed_path),
            output_dir=str(output_dir),
        )

        companies_csv = output_dir / "rne_companies.csv"
        audit_csv = output_dir / "rne_audit.csv"
        sqlite_db = output_dir / "rne_companies.sqlite"

        append_row_csv(str(companies_csv), row, reset=False)
        append_audit_csv(str(audit_csv), audit_rows, reset=False)

        if not no_sqlite:
            upsert_company_sqlite(str(sqlite_db), row)
            insert_audit_sqlite(str(sqlite_db), audit_rows)

        company_id = row.get("identifiant_unique", "")

        logger.info(f"OK: {pdf_path.name} -> ID={company_id}")

        # Delete mixed txt only after successful parse/write.
        if not keep_mixed and mixed_path:
            delete_file_safely(mixed_path)

        return {
            "status": "ok",
            "pdf": str(pdf_path),
            "id": company_id,
            "mixed_path": str(mixed_path),
        }

    except Exception as exc:
        tb = traceback.format_exc()

        logger.error(f"FAILED: {pdf_path.name} — {exc}")

        # Keep mixed file on failure for debugging.
        return {
            "status": "error",
            "pdf": str(pdf_path),
            "mixed_path": str(mixed_path) if mixed_path else "",
            "error": str(exc),
            "tb": tb,
        }


def run_batch(
    input_dir: Path,
    output_dir: Path,
    reset: bool = False,
    reprocess: bool = False,
    keep_mixed: bool = False,
    fallback_debug: bool = False,
    no_sqlite: bool = False,
    limit: int = 0,
) -> None:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if reset:
        logger.warning("Reset enabled: deleting final output files.")
        reset_outputs(str(output_dir))

        progress_path = output_dir / PROGRESS_FILE
        failed_path = output_dir / FAILED_LOG

        delete_file_safely(progress_path)
        delete_file_safely(failed_path)

    pdfs = find_pdfs(input_dir)

    if limit and limit > 0:
        pdfs = pdfs[:limit]

    if not pdfs:
        logger.error(f"No PDFs found in: {input_dir}")
        return

    done = set() if reprocess else load_progress(output_dir)

    todo = []

    for pdf in pdfs:
        pdf_key = str(pdf.resolve())

        if pdf_key in done and not reprocess:
            continue

        todo.append(pdf)

    logger.info(f"Found PDFs: {len(pdfs)}")
    logger.info(f"Already done: {len(done)}")
    logger.info(f"To process: {len(todo)}")
    logger.info(f"Output folder: {output_dir}")

    if not todo:
        logger.info("Nothing to do. Use --reprocess to process again.")
        return

    ok_count = 0
    fail_count = 0

    iterator = tqdm(todo, unit="pdf") if HAS_TQDM else todo

    for pdf_path in iterator:
        result = process_one_pdf(
            pdf_path=pdf_path,
            output_dir=output_dir,
            keep_mixed=keep_mixed,
            fallback_debug=fallback_debug,
            no_sqlite=no_sqlite,
        )

        pdf_key = str(pdf_path.resolve())

        if result["status"] == "ok":
            ok_count += 1
            done.add(pdf_key)
            save_progress(output_dir, done)

        else:
            fail_count += 1
            log_failure(
                output_dir=output_dir,
                pdf_path=pdf_path,
                error=result.get("error", ""),
                tb=result.get("tb", ""),
            )

    logger.info("=" * 80)
    logger.info(f"DONE")
    logger.info(f"OK: {ok_count}")
    logger.info(f"FAILED: {fail_count}")
    logger.info(f"CSV: {output_dir / 'rne_companies.csv'}")
    logger.info(f"AUDIT: {output_dir / 'rne_audit.csv'}")

    if not no_sqlite:
        logger.info(f"SQLITE: {output_dir / 'rne_companies.sqlite'}")

    if fail_count:
        logger.info(f"Failed PDFs log: {output_dir / FAILED_LOG}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch process a folder of RNE PDFs into rne_companies.csv"
    )

    parser.add_argument(
        "--input-dir",
        required=True,
        help="Folder containing PDFs",
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output folder",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete final CSV/SQLite/progress before running",
    )

    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Ignore progress.json and process PDFs again",
    )

    parser.add_argument(
        "--keep-mixed",
        action="store_true",
        help="Keep per-PDF _mixed.txt files instead of deleting them after success",
    )

    parser.add_argument(
        "--fallback-debug",
        action="store_true",
        help="Show PyMuPDF fallback debug lines from Step 1",
    )

    parser.add_argument(
        "--no-sqlite",
        action="store_true",
        help="Do not write SQLite database",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N PDFs. Useful for testing.",
    )

    args = parser.parse_args()

    run_batch(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        reset=args.reset,
        reprocess=args.reprocess,
        keep_mixed=args.keep_mixed,
        fallback_debug=args.fallback_debug,
        no_sqlite=args.no_sqlite,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()