"""
recommendation/ranker.py
========================
Layer 4 — Hybrid Ranker.

Fuses the three score layers into a single ranked list of offers per company:

    final_score = W_RULE    * rule_score
                + W_CONTENT * content_score
                + W_COLLAB  * collab_score

Missing scores are treated as 0.0 (correct behaviour):
    - Layer 1 only outputs non-zero rule scores
    - Layer 2 keeps top-8 above 0.35 similarity
    - Layer 3 keeps top-10 per company
    So a (company, offer) pair absent from a layer's output legitimately
    scored 0 or was below that layer's noise floor.

Public API:
    build_ranked_recommendations(
        companies_df, catalog_df,
        rule_scores, content_scores, collab_scores,
        top_n=3
    ) -> DataFrame
"""

import logging

import pandas as pd

from recommendation.config import W_RULE, W_CONTENT, W_COLLAB

logger = logging.getLogger(__name__)

assert abs((W_RULE + W_CONTENT + W_COLLAB) - 1.0) < 1e-9, \
    "Layer weights must sum to 1.0"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _index_layer_scores(
    df: pd.DataFrame,
    score_column: str,
    extra_columns: list[str] | None = None,
) -> dict:
    """
    Turn a long-format layer output into
        {(comp_id, offer_id): {...fields...}}
    for O(1) lookup.
    """
    if df is None or df.empty:
        return {}

    extras = extra_columns or []
    out = {}

    for row in df.itertuples(index=False):
        row_dict = row._asdict()
        comp_id  = str(row_dict["identifiant_unique"])
        offer_id = row_dict["offer_id"]
        key = (comp_id, offer_id)

        entry = {score_column: float(row_dict[score_column])}
        for col in extras:
            if col in row_dict and row_dict[col] is not None:
                val = row_dict[col]
                if isinstance(val, float) and pd.isna(val):
                    val = ""
                entry[col] = val
        out[key] = entry

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_ranked_recommendations(
    companies_df:   pd.DataFrame,
    catalog_df:     pd.DataFrame,
    rule_scores:    pd.DataFrame,
    content_scores: pd.DataFrame,
    collab_scores:  pd.DataFrame,
    top_n:          int = 3,
) -> pd.DataFrame:
    """
    Fuse the three layers and produce the final top-N ranked offers
    per company.

    Returns DataFrame with columns:
        identifiant_unique, rank, offer_id, offer_name, family,
        final_score, rule_score, content_score, collab_score,
        n_rules_fired, rule_reasons, rule_names,
        collab_source, content_why_matched
    """
    if "identifiant_unique" not in companies_df.columns:
        raise ValueError("companies_df must have 'identifiant_unique'")
    for col in ("offer_id", "offer_name", "family"):
        if col not in catalog_df.columns:
            raise ValueError(f"catalog_df must have '{col}'")

    n_companies = len(companies_df)
    n_offers    = len(catalog_df)
    logger.info("Layer 4: ranking %d offers across %d companies (top-%d each)",
                n_offers, n_companies, top_n)

    # ── Fast lookup indexes for each layer ───────────────────────────────
    rule_idx = _index_layer_scores(
        rule_scores, "rule_score",
        extra_columns=["n_rules_fired", "rule_reasons", "rule_names"],
    )
    content_idx = _index_layer_scores(
        content_scores, "content_score",
        extra_columns=["why_matched"],
    )
    collab_idx = _index_layer_scores(
        collab_scores, "collab_score",
        extra_columns=["collab_source"],
    )

    logger.info("  Layer 1 index: %d (company, offer) pairs", len(rule_idx))
    logger.info("  Layer 2 index: %d (company, offer) pairs", len(content_idx))
    logger.info("  Layer 3 index: %d (company, offer) pairs", len(collab_idx))

    catalog_records = catalog_df[["offer_id", "offer_name", "family"]]\
        .to_dict("records")

    all_recs = []
    company_ids = companies_df["identifiant_unique"].astype(str).tolist()

    for comp_id in company_ids:
        candidates = []

        for cat_row in catalog_records:
            offer_id   = cat_row["offer_id"]
            offer_name = cat_row["offer_name"]
            family     = cat_row["family"]
            key = (comp_id, offer_id)

            r_entry = rule_idx.get(key, {})
            c_entry = content_idx.get(key, {})
            k_entry = collab_idx.get(key, {})

            rule_score    = float(r_entry.get("rule_score", 0.0))
            content_score = float(c_entry.get("content_score", 0.0))
            collab_score  = float(k_entry.get("collab_score", 0.0))

            final_score = (
                W_RULE    * rule_score
                + W_CONTENT * content_score
                + W_COLLAB  * collab_score
            )

            candidates.append({
                "identifiant_unique":  comp_id,
                "offer_id":            offer_id,
                "offer_name":          offer_name,
                "family":              family,
                "final_score":         round(final_score, 4),
                "rule_score":          round(rule_score, 4),
                "content_score":       round(content_score, 4),
                "collab_score":        round(collab_score, 4),
                "n_rules_fired":       int(r_entry.get("n_rules_fired", 0) or 0),
                "rule_reasons":        r_entry.get("rule_reasons", ""),
                "rule_names":          r_entry.get("rule_names", ""),
                "collab_source":       k_entry.get("collab_source", "none"),
                "content_why_matched": c_entry.get("why_matched", ""),
            })

        # Sort: final_score desc, then rule_score, then content_score
        candidates.sort(
            key=lambda x: (
                -x["final_score"],
                -x["rule_score"],
                -x["content_score"],
            )
        )

        for rank, rec in enumerate(candidates[:top_n], start=1):
            rec["rank"] = rank
            all_recs.append(rec)

    result = pd.DataFrame(all_recs)

    # Reorder columns for readability
    column_order = [
        "identifiant_unique", "rank",
        "offer_id", "offer_name", "family",
        "final_score", "rule_score", "content_score", "collab_score",
        "n_rules_fired", "rule_reasons", "rule_names",
        "collab_source", "content_why_matched",
    ]
    result = result[[c for c in column_order if c in result.columns]]

    logger.info("Layer 4 produced %d recommendations (%d companies × top-%d)",
                len(result), n_companies, top_n)

    if len(result) > 0:
        avg_final = result["final_score"].mean()
        max_final = result["final_score"].max()
        top1 = result[result["rank"] == 1]
        share_zero = (top1["final_score"] < 0.05).sum() / max(len(top1), 1)
        logger.info("  Mean final_score: %.3f  Max: %.3f",
                    avg_final, max_final)
        logger.info("  Rank-1 recs with near-zero score: %.1f%%",
                    share_zero * 100)
        if share_zero > 0.30:
            logger.warning(
                "  >30%% of top-1 recs have near-zero scores. "
                "Check the segmentation output for empty/unknown categories."
            )

    return result
