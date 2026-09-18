"""
ingestion/build_master.py
=========================
Merge RNE records and Google-Maps listings into a single master prospect table
(companies_master.csv) with a clear field-precedence policy:

    RNE  wins for official / legal fields  (capital, dates, legal form, official name)
    Maps wins for contact / engagement     (phone, website, rating, reviews, coords)

Every master row is tagged with:
    match_source     ∈ {matched, rne_only, maps_only}
    match_confidence  the entity-resolution pair score (1.0 for single-source rows)

Unmatched records from *both* sides are kept — a Maps-only business with no RNE
record is still a real prospect, and vice-versa.

Run directly:
    python -m ingestion.build_master --maps data/input/google_maps.csv \
                                      --rne  data/output/rne_companies_segmented.csv
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

from segmentation.config import BASE_DIR
from ingestion.column_resolver import resolve_maps_columns
from ingestion.entity_resolution import resolve_entities

logger = logging.getLogger(__name__)

MASTER_CSV = BASE_DIR / "data" / "output" / "companies_master.csv"
REVIEW_CSV = BASE_DIR / "data" / "output" / "merge_review_needed.csv"

# Maps enrichment columns that flow into the master table.
MAPS_ENRICHMENT = [
    "maps_name", "maps_address", "maps_phone", "maps_website", "maps_email",
    "maps_rating", "maps_reviews_count", "maps_category", "maps_lat", "maps_lng",
    "maps_status", "maps_city", "maps_governorate",
]


def build_master(
    rne_csv: str | Path,
    maps_csv: str | Path,
    rne_name_col: str = "fr_denomination",
    rne_phone_col: str | None = None,
) -> dict:
    """Build companies_master.csv. Returns a summary dict."""
    rne_csv, maps_csv = Path(rne_csv), Path(maps_csv)
    if not rne_csv.exists():
        raise FileNotFoundError(f"RNE CSV not found: {rne_csv}")
    if not maps_csv.exists():
        raise FileNotFoundError(f"Maps CSV not found: {maps_csv}")

    logger.info("Loading RNE  : %s", rne_csv)
    rne = pd.read_csv(rne_csv, encoding="utf-8-sig").reset_index(drop=True)
    logger.info("Loading Maps : %s", maps_csv)
    maps_raw = pd.read_csv(maps_csv, encoding="utf-8-sig")
    maps = resolve_maps_columns(maps_raw).reset_index(drop=True)

    # ── resolve ──────────────────────────────────────────────────────────────
    res = resolve_entities(rne, maps, rne_name_col=rne_name_col, rne_phone_col=rne_phone_col)
    matches   = res["matches"]
    review    = res["review"]
    rne_matched = res["rne_matched_index"]
    maps_unmatched = res["maps_unmatched_index"]

    enrichment_cols = [c for c in MAPS_ENRICHMENT if c in maps.columns]
    master_rows = []

    # ── matched rows: RNE base + Maps enrichment ──────────────────────────────
    matched_maps_idx = set()
    for _, m in matches.iterrows():
        base = rne.iloc[int(m["rne_index"])].to_dict()
        mp   = maps.iloc[int(m["maps_index"])]
        matched_maps_idx.add(int(m["maps_index"]))
        for c in enrichment_cols:
            base[c] = mp.get(c)
        base["match_source"] = "matched"
        base["match_confidence"] = float(m["score"])
        master_rows.append(base)

    # ── rne-only rows ─────────────────────────────────────────────────────────
    for i in range(len(rne)):
        if i in rne_matched:
            continue
        base = rne.iloc[i].to_dict()
        for c in enrichment_cols:
            base.setdefault(c, None)
        base["match_source"] = "rne_only"
        base["match_confidence"] = 1.0
        master_rows.append(base)

    # ── maps-only rows (real prospects with no official record yet) ────────────
    for j in maps_unmatched:
        mp = maps.iloc[j]
        base = {c: mp.get(c) for c in enrichment_cols}
        # promote Maps fields into the canonical identity slots so the rest of the
        # pipeline (analysis, scoring) can treat them uniformly
        base["fr_denomination"] = mp.get("maps_name")
        base["fr_adresse"]      = mp.get("maps_address")
        base["city"]            = mp.get("maps_city")
        base["governorate"]     = mp.get("maps_governorate")
        base["match_source"]    = "maps_only"
        base["match_confidence"] = 1.0
        master_rows.append(base)

    master = pd.DataFrame(master_rows)

    MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    logger.info("Wrote %s (%d rows)", MASTER_CSV, len(master))

    # ── review queue for borderline pairs ──────────────────────────────────────
    if len(review):
        rev_rows = []
        for _, r in review.iterrows():
            rev_rows.append({
                "rne_name":  rne.iloc[int(r["rne_index"])].get(rne_name_col),
                "maps_name": maps.iloc[int(r["maps_index"])].get("maps_name"),
                "score":     r["score"],
            })
        pd.DataFrame(rev_rows).to_csv(REVIEW_CSV, index=False, encoding="utf-8-sig")
        logger.info("Wrote %s (%d borderline pairs to review)", REVIEW_CSV, len(review))

    summary = {
        "rne_rows":        len(rne),
        "maps_rows":       len(maps),
        "matched":         len(matches),
        "rne_only":        len(rne) - len(rne_matched),
        "maps_only":       len(maps_unmatched),
        "review_pairs":    len(review),
        "master_rows":     len(master),
        "master_csv":      str(MASTER_CSV),
    }
    logger.info("=" * 60)
    logger.info("MERGE COMPLETE — master prospect table built")
    logger.info("  RNE rows   : %d", summary["rne_rows"])
    logger.info("  Maps rows  : %d", summary["maps_rows"])
    logger.info("  Matched    : %d", summary["matched"])
    logger.info("  RNE-only   : %d", summary["rne_only"])
    logger.info("  Maps-only  : %d", summary["maps_only"])
    logger.info("  For review : %d", summary["review_pairs"])
    logger.info("  Master rows: %d", summary["master_rows"])
    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Build the merged master prospect table.")
    parser.add_argument("--rne",  required=True, help="Path to RNE / segmented CSV")
    parser.add_argument("--maps", required=True, help="Path to Google Maps export CSV")
    parser.add_argument("--rne-name-col", default="fr_denomination")
    parser.add_argument("--rne-phone-col", default=None)
    args = parser.parse_args()

    build_master(
        rne_csv=args.rne,
        maps_csv=args.maps,
        rne_name_col=args.rne_name_col,
        rne_phone_col=args.rne_phone_col,
    )
