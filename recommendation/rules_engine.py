"""
recommendation/rules_engine.py
==============================
Layer 1 — Rule engine (evaluates the declarative rules from rules_config.py).

For each (company, offer) pair:
    1. Find every rule that fires for this company AND targets this offer
    2. Combine the individual rule scores into a single score in [0, 1]
    3. Collect the reasons (French strings) from every rule that fired

Score combination — probabilistic OR:
    combined = 1 - product(1 - rule_score for each firing rule)

    This means:
      - one rule at 0.80              -> combined = 0.80
      - two rules at 0.60 and 0.50    -> combined = 1 - 0.4*0.5 = 0.80
      - three rules at 0.40           -> combined = 1 - 0.6^3   = 0.784

    Multiple pieces of evidence reinforce each other, but the score
    stays bounded in [0, 1].

Public API:
    build_rule_scores(companies_df, catalog_df) -> DataFrame
    score_company_offer(company_row, offer_id, offer_family) -> (score, reasons)
"""

import logging
from functools import reduce

import pandas as pd

from recommendation.rules_config import RULES

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rule_matches_offer(rule: dict, offer_id: str, offer_family: str) -> bool:
    """
    A rule targets an offer if:
      - target_offer matches offer_id  (specific offer), AND/OR
      - target_family matches offer_family  (family-wide)
    A rule with BOTH set requires both to match.
    A rule with neither set is invalid and skipped.
    """
    tgt_offer  = rule.get("target_offer")
    tgt_family = rule.get("target_family")

    if tgt_offer is None and tgt_family is None:
        return False
    if tgt_offer is not None and tgt_offer != offer_id:
        return False
    if tgt_family is not None and tgt_family != offer_family:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def score_company_offer(
    company_row: dict,
    offer_id: str,
    offer_family: str,
) -> tuple[float, list[dict]]:
    """
    Compute Layer 1 score for one (company, offer) pair.

    Returns:
        score:   float in [0, 1]
        reasons: list of {"rule": <name>, "reason_fr": <text>, "score": <float>}
                 — one entry per rule that fired, sorted by score descending.
    """
    firing = []

    for rule in RULES:
        if not _rule_matches_offer(rule, offer_id, offer_family):
            continue

        try:
            fires = bool(rule["when"](company_row))
        except Exception as e:
            logger.debug("Rule '%s' errored: %s", rule.get("name"), e)
            fires = False

        if not fires:
            continue

        firing.append({
            "rule":      rule.get("name", "unnamed"),
            "reason_fr": rule.get("reason_fr", ""),
            "score":     float(rule.get("score", 0)),
        })

    if not firing:
        return 0.0, []

    # Strongest reason first (for the explainer)
    firing.sort(key=lambda x: -x["score"])

    # Probabilistic OR:  combined = 1 - ∏(1 - s_i)
    complements = [max(0.0, min(1.0, 1.0 - r["score"])) for r in firing]
    combined = 1.0 - reduce(lambda a, b: a * b, complements, 1.0)

    return round(combined, 4), firing


def build_rule_scores(
    companies_df: pd.DataFrame,
    catalog_df:   pd.DataFrame,
) -> pd.DataFrame:
    """
    Run Layer 1 for every (company, offer) pair.

    Returns DataFrame with columns:
        identifiant_unique, offer_id, rule_score, n_rules_fired,
        rule_reasons, rule_names
    """
    if "identifiant_unique" not in companies_df.columns:
        raise ValueError("companies_df needs 'identifiant_unique'")
    if "offer_id" not in catalog_df.columns:
        raise ValueError("catalog_df needs 'offer_id'")

    logger.info("Layer 1: evaluating %d rules across %d companies × %d offers",
                len(RULES), len(companies_df), len(catalog_df))

    catalog_records = catalog_df[["offer_id", "family"]].to_dict(orient="records")

    rows = []
    for _, comp in companies_df.iterrows():
        comp_id  = str(comp["identifiant_unique"])
        comp_row = comp.to_dict()

        for offer_rec in catalog_records:
            offer_id = offer_rec["offer_id"]
            family   = str(offer_rec.get("family", "")).strip()

            score, reasons = score_company_offer(comp_row, offer_id, family)

            if score == 0.0:
                continue  # keep the output file lean

            rows.append({
                "identifiant_unique": comp_id,
                "offer_id":           offer_id,
                "rule_score":         score,
                "n_rules_fired":      len(reasons),
                "rule_reasons":       " | ".join(r["reason_fr"] for r in reasons),
                "rule_names":         ",".join(r["rule"] for r in reasons),
            })

    result = pd.DataFrame(rows)
    logger.info("Layer 1 produced %d non-zero (company, offer) rule scores",
                len(result))

    if len(result) > 0:
        avg_rules = result["n_rules_fired"].mean()
        max_rules = result["n_rules_fired"].max()
        logger.info("  Avg rules firing per pair: %.2f (max %d)",
                    avg_rules, max_rules)

    return result
