"""
scoring/main.py
===============
Unified prospect-intelligence scoring.

Primary population — the Google Maps universe (scored_businesses.csv):
    value       = Maps-based value model (sector + prominence + digital)
    conversion  = trained PU propensity (prob → percentile) from scoring/propensity
Secondary population — RNE registered companies (company_features.csv):
    value       = firmographic value model
    conversion  = heuristic readiness (no PU score available)

Both are scored on the same 0–100 axes, tiered A/B/C/D, and given a campaign plan.
Writes prospect_scores.csv (Maps, primary) and rne_prospect_scores.csv (RNE).

    python -m scoring.main
"""

import json
import logging
from pathlib import Path

import pandas as pd

from scoring.config import (
    MAPS_SCORED_CSV, RNE_FEATURES_CSV, PROSPECT_SCORES_CSV, RNE_SCORES_CSV,
)
from scoring.models import value_potential, conversion_readiness, maps_sector
from scoring.propensity import compute_propensity
from scoring.priority import priority_score, assign_tier
from scoring.campaign_planner import plan_campaign

logger = logging.getLogger(__name__)

MAPS_CARRY = ["name", "search_category", "category", "address", "governorate",
              "phone", "website", "email", "rating", "reviews", "place_url",
              "is_known_customer", "predicted_customer", "predicted_client"]
RNE_CARRY  = ["identifiant_unique", "fr_denomination", "category", "confidence",
              "governorate", "city", "capital", "capital_tier", "company_size",
              "maturity", "business_model", "connectivity_need", "digital_signal",
              "is_new_company", "multisite_signal", "international_signal",
              "callable_prospect"]


def _finalize(rec, value, conv, vb, cb, row):
    prio = priority_score(value, conv)
    tier_key, tier_label = assign_tier(value, conv)
    plan = plan_campaign(row, tier_key)
    rec.update({
        "value_score": value, "conversion_score": conv, "priority_score": prio,
        "tier": tier_key, "tier_label": tier_label,
        "campaign_channel": plan["channel"], "budget_band": plan["budget_band"],
        "budget_tnd": plan["budget_tnd"], "cadence": plan["cadence"],
        "campaign_rationale": plan["rationale"],
        "value_breakdown": json.dumps(vb, ensure_ascii=False),
        "conversion_breakdown": json.dumps(cb, ensure_ascii=False),
    })
    return rec, tier_key


def _tier_summary(rows):
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for _, k in rows:
        counts[k] += 1
    return counts


def score_maps(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    logger.info("Maps universe: %d businesses", len(df))
    if "is_known_customer" in df.columns:
        known = int((df["is_known_customer"] == 1).sum())
        df = df[df["is_known_customer"] != 1].copy()
        logger.info("Excluded %d existing customers → %d prospects", known, len(df))
    df = compute_propensity(df)          # adds propensity_score (0–100) + propensity_prob

    out, tiers = [], []
    for _, row in df.iterrows():
        value, vb = value_potential(row)
        conv = float(row["propensity_score"])
        cb = {"pu_propensity_percentile": conv,
              "modeled_probability": float(row["propensity_prob"])}
        rec = {c: row.get(c) for c in MAPS_CARRY if c in df.columns}
        rec["source"] = "maps"
        rec["sector"] = maps_sector(row)
        rec, k = _finalize(rec, value, conv, vb, cb, row)
        out.append(rec); tiers.append((None, k))

    result = pd.DataFrame(out).sort_values("priority_score", ascending=False)
    result.to_csv(PROSPECT_SCORES_CSV, index=False, encoding="utf-8-sig")
    return result, _tier_summary(tiers)


def score_rne(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    logger.info("RNE registered: %d companies", len(df))
    out, tiers = [], []
    for _, row in df.iterrows():
        value, vb = value_potential(row)
        conv, cb = conversion_readiness(row)
        rec = {c: row.get(c) for c in RNE_CARRY if c in df.columns}
        rec["source"] = "rne"; rec["sector"] = row.get("category")
        rec, k = _finalize(rec, value, conv, vb, cb, row)
        out.append(rec); tiers.append((None, k))
    result = pd.DataFrame(out).sort_values("priority_score", ascending=False)
    result.to_csv(RNE_SCORES_CSV, index=False, encoding="utf-8-sig")
    return result, _tier_summary(tiers)


def run_scoring(maps_csv=None, rne_csv=None) -> dict:
    maps_csv = Path(maps_csv or MAPS_SCORED_CSV)
    rne_csv  = Path(rne_csv or RNE_FEATURES_CSV)
    summary = {}

    if maps_csv.exists():
        m, mt = score_maps(maps_csv)
        summary["maps"] = {"prospects": len(m), "tiers": mt,
                           "avg_value": round(m["value_score"].mean(), 1),
                           "output": str(PROSPECT_SCORES_CSV)}
    if rne_csv.exists():
        r, rt = score_rne(rne_csv)
        summary["rne"] = {"prospects": len(r), "tiers": rt,
                          "avg_value": round(r["value_score"].mean(), 1),
                          "output": str(RNE_SCORES_CSV)}
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    s = run_scoring()
    print(json.dumps(s, indent=2, ensure_ascii=False))
