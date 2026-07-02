"""
run.py — unified entry point for Opportunity Navigator.

Usage:
    python run.py --dashboard
    python run.py --api
    python run.py --pdf-folder data/input/pdfs
    python run.py --skip-extraction
    python run.py --skip-extraction --rebuild-rag
    python run.py --pdf-folder data/input/pdfs --llm-audit

    NEW — extract from database instead of local folder:
    python run.py --from-db
    python run.py --from-db --rebuild-rag
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _run_dashboard():
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app/dashboard.py"],
        check=True,
    )


def _run_api(host: str, port: int, reload: bool):
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api.routes:app",
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")
    subprocess.run(cmd, check=True)


def _run_pipeline(args):
    from pipeline.runner import run_pipeline

    # from_db mode: no pdf_folder needed
    # local mode: pdf_folder needed unless skipping extraction
    if args.from_db:
        pdf_folder = None
    elif args.skip_extraction:
        pdf_folder = None
    else:
        pdf_folder = args.pdf_folder

    result = run_pipeline(
        pdf_folder=pdf_folder,
        extraction_output_csv=args.input,
        skip_extraction=args.skip_extraction,
        skip_rag_rebuild=not args.rebuild_rag,
        run_llm_audit=args.llm_audit,
        llm_audit_limit=args.llm_limit,
        keep_mixed=args.keep_mixed,
        from_db=args.from_db,
    )

    if result.get("errors"):
        logger.warning("Pipeline completed with errors: %s", result["errors"])
    else:
        logger.info("Pipeline completed successfully.")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Opportunity Navigator — unified entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--dashboard",        action="store_true", help="Launch Streamlit dashboard")
    parser.add_argument("--api",              action="store_true", help="Launch FastAPI server")
    parser.add_argument("--pdf-folder",       default=None,        help="Folder containing PDFs to extract")
    parser.add_argument("--input",            default="data/input/rne_companies.csv",
                                                                   help="Path to rne_companies.csv")
    parser.add_argument("--skip-extraction",  action="store_true", help="Skip PDF extraction, run segmentation only")
    parser.add_argument("--rebuild-rag",      action="store_true", help="Force rebuild of RAG knowledge base")
    parser.add_argument("--llm-audit",        action="store_true", help="Run LLM audit after segmentation (requires Ollama)")
    parser.add_argument("--llm-limit",        type=int, default=None, help="Limit LLM audit to N rows")
    parser.add_argument("--keep-mixed",       action="store_true", help="Keep intermediate extraction files (for debugging)")
    parser.add_argument("--from-db",          action="store_true", help="Extract from database (MinIO/MongoDB) instead of local folder")
    parser.add_argument("--host",             default="0.0.0.0",   help="API host (default: 0.0.0.0)")
    parser.add_argument("--port",             type=int, default=8000, help="API port (default: 8000)")
    parser.add_argument("--reload",           action="store_true", help="Enable uvicorn auto-reload")

    args = parser.parse_args()

    if args.dashboard:
        _run_dashboard()
    elif args.api:
        _run_api(host=args.host, port=args.port, reload=args.reload)
    elif args.skip_extraction or args.pdf_folder or args.rebuild_rag or args.llm_audit or args.from_db:
        _run_pipeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
