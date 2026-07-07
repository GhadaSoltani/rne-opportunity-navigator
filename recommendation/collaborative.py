"""
recommendation/collaborative.py
================================
Layer 3 — Collaborative filtering.

Learns from real purchase history: which offers did companies in each
(category × company_size) segment actually buy?

We work at SEGMENT level (not per-company) because we have ~211 labeled
rows — enough to see patterns per segment, not enough to do per-company
matrix factorisation without overfitting.

Logic:
    1. From purchases, keep rows that have both a category and an offer_id
    2. For each (category, company_size) pair, count purchases per offer
    3. Normalise to a 0-1 score = share of that segment's purchases
    4. For a target company, look up its segment and return those scores

Fallback chain (always returns something — no silent zeros):
    1. (category, company_size) segment — most specific
    2. category only                    — medium specificity
    3. global offer popularity          — always available

Public API:
    build_collab_scores(companies_df, purchases_df, top_n) -> DataFrame
"""

import logging

import pandas as pd

from recommendation.config import (
    COLLAB_TOP_N,
    COLLAB_MIN_SEGMENT_PURCHASES,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Affinity matrix builder
# ─────────────────────────────────────────────────────────────────────────────

def build_affinity_matrix(
    purchases_df: pd.DataFrame,
    companies_df: pd.DataFrame | None = None,
) -> dict:
    """
    Build the segment -> offer affinity lookup from purchase history.

    If `companies_df` is provided, we enrich purchases rows (matched by
    RNE identifier) with `company_size` so the segment-level lookup
    (category × company_size) has better coverage.

    Returns a nested dict:
        {
          "segment":   {(category, size):  {offer_id: score}},
          "category":  {category:          {offer_id: score}},
          "global":    {offer_id: score},
        }

    Scores within each group sum to 1.0 so they're directly comparable.
    """
    df = purchases_df.copy()

    # ── Enrich purchases with company_size from companies_df ─────────────
    if (companies_df is not None
            and "company_size" not in df.columns
            and "rne" in df.columns
            and "identifiant_unique" in companies_df.columns):
        size_map = (
            companies_df[["identifiant_unique", "company_size"]]
            .dropna(subset=["identifiant_unique", "company_size"])
            .set_index("identifiant_unique")["company_size"]
            .to_dict()
        )
        df["company_size"] = df["rne"].map(size_map)
        enriched = df["company_size"].notna().sum()
        logger.info("Enriched %d / %d purchase rows with company_size",
                    enriched, len(df))

    # ── Filter to rows with both category and valid offer_id ─────────────
    labeled = df[
        df["category"].notna()
        & (df["category"].astype(str).str.strip() != "")
        & df["offer_id"].notna()
        & (df["offer_id"].astype(str).str.strip() != "")
        & (df["offer_id"] != "unmapped")
    ].copy()

    logger.info("Labeled rows for collaborative layer: %d / %d",
                len(labeled), len(purchases_df))

    def normalise(counts: pd.Series) -> dict:
        total = counts.sum()
        if total == 0:
            return {}
        return (counts / total).round(4).to_dict()

    # ── Global popularity (ultimate fallback) ─────────────────────────────
    global_counts = labeled["offer_id"].value_counts()
    global_scores = normalise(global_counts)
    logger.info("Global fallback built from %d purchases, %d distinct offers",
                len(labeled), len(global_scores))

    # ── Category-level affinity ───────────────────────────────────────────
    cat_scores = {}
    for cat, grp in labeled.groupby("category"):
        counts = grp["offer_id"].value_counts()
        if counts.sum() >= COLLAB_MIN_SEGMENT_PURCHASES:
            cat_scores[cat] = normalise(counts)
    logger.info("Category-level affinity built for %d categories",
                len(cat_scores))

    # ── Segment-level affinity (category × company_size) ──────────────────
    seg_scores = {}
    if "company_size" in labeled.columns:
        for (cat, size), grp in labeled.groupby(["category", "company_size"]):
            counts = grp["offer_id"].value_counts()
            if counts.sum() >= COLLAB_MIN_SEGMENT_PURCHASES:
                seg_scores[(cat, size)] = normalise(counts)
        logger.info("Segment-level affinity built for %d segments",
                    len(seg_scores))
    else:
        logger.info("No company_size in purchases — segment level skipped, "
                    "using category level only")

    return {
        "segment":  seg_scores,
        "category": cat_scores,
        "global":   global_scores,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-company scorer
# ─────────────────────────────────────────────────────────────────────────────

def score_company(
    company_row: dict,
    affinity: dict,
) -> list[dict]:
    """
    Return collaborative scores for one company.

    Lookup priority:
        1. (category, company_size) segment — most specific
        2. category only                    — medium specificity
        3. global popularity                — always available

    Returns:
        List of dicts: [{offer_id, collab_score, collab_source}, ...]
        sorted descending by collab_score.
    """
    category = str(company_row.get("category", "")).strip()
    size     = str(company_row.get("company_size", "")).strip()

    # Try segment first
    seg_key = (category, size)
    if seg_key in affinity["segment"]:
        scores = affinity["segment"][seg_key]
        source = f"segment:{category}×{size}"
    elif category in affinity["category"]:
        scores = affinity["category"][category]
        source = f"category:{category}"
    else:
        scores = affinity["global"]
        source = "global_popularity"

    return sorted(
        [{"offer_id": oid, "collab_score": sc, "collab_source": source}
         for oid, sc in scores.items()],
        key=lambda x: -x["collab_score"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_collab_scores(
    companies_df:  pd.DataFrame,
    purchases_df:  pd.DataFrame,
    top_n:         int = COLLAB_TOP_N,
) -> pd.DataFrame:
    """
    Run the collaborative layer for all companies.

    Args:
        companies_df:  company_features.csv — needs 'identifiant_unique',
                       'category', 'company_size'.
        purchases_df:  purchase history — needs 'category', 'offer_id'.
        top_n:         max offers to return per company.

    Returns DataFrame with columns:
        identifiant_unique, offer_id, collab_score, collab_source
    """
    if purchases_df.empty:
        logger.warning("Empty purchases — returning empty collab scores")
        return pd.DataFrame(
            columns=["identifiant_unique", "offer_id",
                     "collab_score", "collab_source"]
        )

    affinity = build_affinity_matrix(purchases_df, companies_df)

    rows = []
    for _, comp in companies_df.iterrows():
        comp_id = str(comp["identifiant_unique"])
        results = score_company(comp.to_dict(), affinity)

        for r in results[:top_n]:
            rows.append({
                "identifiant_unique": comp_id,
                "offer_id":           r["offer_id"],
                "collab_score":       r["collab_score"],
                "collab_source":      r["collab_source"],
            })

    result = pd.DataFrame(rows)
    logger.info("Collaborative scores: %d (company, offer) pairs", len(result))
    return result
