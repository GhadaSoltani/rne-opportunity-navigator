"""
recommendation/config.py
========================
All file paths, model settings, and tunable thresholds for the
recommendation system.  Tune everything from here — the logic modules
never hardcode paths or numbers.

Layers:
    Layer 1 — Rule engine              (rules_engine.py + rules_config.py)
    Layer 2 — Content-based similarity (content_similarity.py)
    Layer 3 — Collaborative filtering  (collaborative.py)
    Layer 4 — Hybrid ranker            (ranker.py)
"""

from pathlib import Path
from segmentation.config import BASE_DIR


# ─────────────────────────────────────────────────────────────────────────────
# Inputs
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_FEATURES_CSV = BASE_DIR / "data" / "output" / "company_features.csv"
OFFER_CATALOG_CSV    = BASE_DIR / "data" / "knowledge" / "offer_catalog.csv"

# The purchases file has a .xls extension but is actually CSV (UTF-8-BOM).
# We handle this transparently in main.py's loader.
PURCHASES_PATH       = BASE_DIR / "data" / "knowledge" / "purchases.xls"


# ─────────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────────

RECOMMENDATION_DIR      = BASE_DIR / "data" / "output"
RULE_SCORES_CSV         = RECOMMENDATION_DIR / "rule_scores.csv"
CONTENT_SCORES_CSV      = RECOMMENDATION_DIR / "content_scores.csv"
COLLAB_SCORES_CSV       = RECOMMENDATION_DIR / "collab_scores.csv"
RECOMMENDATIONS_RAW_CSV = RECOMMENDATION_DIR / "recommendations_raw.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────

from segmentation.config import EMBEDDING_MODEL_NAME   # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 tunables  (content_similarity.py)
# ─────────────────────────────────────────────────────────────────────────────

CONTENT_TOP_N          = 8      # Top-N similar offers per company
CONTENT_MIN_SIMILARITY = 0.35   # Floor — pairs below this are dropped


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 tunables  (collaborative.py)
# ─────────────────────────────────────────────────────────────────────────────

COLLAB_TOP_N              = 10  # Top-N offers per company from collab layer
COLLAB_MIN_SEGMENT_PURCHASES = 3   # Minimum purchases in a segment to trust it


# ─────────────────────────────────────────────────────────────────────────────
# Layer 4 tunables  (ranker.py)
# ─────────────────────────────────────────────────────────────────────────────

RANKER_TOP_N = 3                # Final top-N offers per company

# Fusion weights — must sum to 1.0
W_RULE    = 0.40   # business logic, high trust, always available
W_CONTENT = 0.40   # semantic match, works for every company
W_COLLAB  = 0.20   # real signal but sparse; grows with purchase history
