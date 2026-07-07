"""
recommendation/main.py
======================
Orchestrator for the recommendation system.

Runs all 4 layers in order:
    Layer 1 — Rule engine              (rules_engine.py + rules_config.py)
    Layer 2 — Content-based similarity (content_similarity.py)
    Layer 3 — Collaborative filtering  (collaborative.py)
    Layer 4 — Hybrid ranker            (ranker.py)

Run directly:
    python -m recommendation.main

Produces in data/output/:
    rule_scores.csv            Layer 1 scores
    content_scores.csv         Layer 2 scores
    collab_scores.csv          Layer 3 scores
    recommendations_raw.csv    Layer 4 final ranked top-N per company
"""

import logging
from pathlib import Path

import pandas as pd

from recommendation.config import (
    COMPANY_FEATURES_CSV,
    OFFER_CATALOG_CSV,
    PURCHASES_PATH,
    RULE_SCORES_CSV,
    CONTENT_SCORES_CSV,
    COLLAB_SCORES_CSV,
    RECOMMENDATIONS_RAW_CSV,
    CONTENT_TOP_N,
    COLLAB_TOP_N,
    RANKER_TOP_N,
)
from recommendation.rules_engine       import build_rule_scores
from recommendation.content_similarity import build_content_scores
from recommendation.collaborative      import build_collab_scores
from recommendation.ranker             import build_ranked_recommendations

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# File loading helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_csv(path: Path, label: str) -> pd.DataFrame:
    """Load a UTF-8-BOM CSV."""
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    logger.info("  Loaded %s: %d rows from %s", label, len(df), path)
    return df


def _load_purchases(path: Path) -> pd.DataFrame:
    """
    Load the purchases file.  The file has a .xls extension but may
    actually be CSV (UTF-8-BOM).  We try CSV first, then Excel.
    """
    if not path.exists():
        logger.warning("Purchase history not found at %s — "
                       "Layer 3 will use global popularity only.", path)
        return pd.DataFrame()

    # Try CSV first (the file is CSV despite the .xls extension)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        logger.info("  Loaded purchases (CSV): %d rows from %s",
                    len(df), path)
        return df
    except Exception:
        pass

    # Fall back to Excel
    try:
        df = pd.read_excel(path)
        logger.info("  Loaded purchases (Excel): %d rows from %s",
                    len(df), path)
        return df
    except Exception as e:
        logger.warning("Could not load purchases from %s: %s — "
                       "Layer 3 will use global popularity only.", path, e)
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def run_recommendation(
    company_features_csv: str | Path | None = None,
    offer_catalog_csv:    str | Path | None = None,
    purchases_path:       str | Path | None = None,
    top_n:                int = RANKER_TOP_N,
) -> dict:
    """
    Run the full recommendation pipeline (Layers 1–4).

    Returns:
        Summary dict with counts and output paths.
    """
    features_path  = Path(company_features_csv) if company_features_csv else COMPANY_FEATURES_CSV
    catalog_path   = Path(offer_catalog_csv)    if offer_catalog_csv    else OFFER_CATALOG_CSV
    purchases_file = Path(purchases_path)       if purchases_path       else PURCHASES_PATH

    # ── Load inputs ───────────────────────────────────────────────────────
    logger.info("Loading inputs...")
    companies_df  = _load_csv(features_path, "company features")
    catalog_df    = _load_csv(catalog_path,  "offer catalog")
    purchases_df  = _load_purchases(purchases_file)

    RULE_SCORES_CSV.parent.mkdir(parents=True, exist_ok=True)

    # ── Layer 1: Rule engine ──────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("LAYER 1 — Rule engine")
    logger.info("=" * 60)

    rule_scores = build_rule_scores(
        companies_df=companies_df,
        catalog_df=catalog_df,
    )
    rule_scores.to_csv(RULE_SCORES_CSV, index=False, encoding="utf-8-sig")
    logger.info("  Wrote %s (%d rows)", RULE_SCORES_CSV, len(rule_scores))

    # ── Layer 2: Content-based similarity ─────────────────────────────────
    logger.info("=" * 60)
    logger.info("LAYER 2 — Content-based similarity")
    logger.info("=" * 60)

    content_scores = build_content_scores(
        companies_df=companies_df,
        catalog_df=catalog_df,
        top_n=CONTENT_TOP_N,
    )
    content_scores.to_csv(CONTENT_SCORES_CSV, index=False, encoding="utf-8-sig")
    logger.info("  Wrote %s (%d rows)", CONTENT_SCORES_CSV, len(content_scores))

    # ── Layer 3: Collaborative filtering ──────────────────────────────────
    logger.info("=" * 60)
    logger.info("LAYER 3 — Collaborative filtering")
    logger.info("=" * 60)

    collab_scores = build_collab_scores(
        companies_df=companies_df,
        purchases_df=purchases_df,
        top_n=COLLAB_TOP_N,
    )
    collab_scores.to_csv(COLLAB_SCORES_CSV, index=False, encoding="utf-8-sig")
    logger.info("  Wrote %s (%d rows)", COLLAB_SCORES_CSV, len(collab_scores))

    # ── Layer 4: Hybrid ranker ────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("LAYER 4 — Hybrid ranker")
    logger.info("=" * 60)

    recommendations = build_ranked_recommendations(
        companies_df=companies_df,
        catalog_df=catalog_df,
        rule_scores=rule_scores,
        content_scores=content_scores,
        collab_scores=collab_scores,
        top_n=top_n,
    )
    recommendations.to_csv(
        RECOMMENDATIONS_RAW_CSV, index=False, encoding="utf-8-sig",
    )
    logger.info("  Wrote %s (%d rows)",
                RECOMMENDATIONS_RAW_CSV, len(recommendations))

    # ── Summary ───────────────────────────────────────────────────────────
    summary = {
        "companies_processed":     len(companies_df),
        "offers_in_catalog":       len(catalog_df),
        "purchase_rows_loaded":    len(purchases_df),
        "top_n":                   top_n,
        "rule_score_rows":         len(rule_scores),
        "content_score_rows":      len(content_scores),
        "collab_score_rows":       len(collab_scores),
        "recommendations_total":   len(recommendations),
        "rule_scores_csv":         str(RULE_SCORES_CSV),
        "content_scores_csv":      str(CONTENT_SCORES_CSV),
        "collab_scores_csv":       str(COLLAB_SCORES_CSV),
        "recommendations_raw_csv": str(RECOMMENDATIONS_RAW_CSV),
    }

    logger.info("=" * 60)
    logger.info("RECOMMENDATION SYSTEM — COMPLETE (Layers 1-4)")
    logger.info("  Companies      : %d", summary["companies_processed"])
    logger.info("  Offers         : %d", summary["offers_in_catalog"])
    logger.info("  Purchases      : %d", summary["purchase_rows_loaded"])
    logger.info("  Recommendations: %d  (top-%d per company)",
                summary["recommendations_total"], top_n)
    logger.info("  Output         : %s", summary["recommendations_raw_csv"])
    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    run_recommendation()
