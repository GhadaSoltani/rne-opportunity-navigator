"""
core/paths.py
=============
Single, dependency-free source of the project base directory and key data paths.
Lightweight modules (scoring, ingestion, auth) import BASE_DIR from here instead
of from segmentation.config, so they don't drag in the ML stack (torch,
sentence-transformers, tqdm…) just to resolve a path.
"""
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data"
INPUT_DIR  = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
