"""
test_layer2.py
==============
Quick standalone test for Layer 2 (content-based similarity).

Runs on a small sample of 10 companies and prints the top-3 recommended
offers for each — the point is to visually verify that the matches look
sensible before running on the full dataset.

Usage:
    python test_layer2.py
"""

import logging
import pandas as pd

from recommendation.config import COMPANY_FEATURES_CSV, OFFER_CATALOG_CSV
from recommendation.content_similarity import (
    build_content_scores,
    build_company_profile,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

# Load
print(f"Loading {COMPANY_FEATURES_CSV}...")
companies = pd.read_csv(COMPANY_FEATURES_CSV, encoding="utf-8-sig")

print(f"Loading {OFFER_CATALOG_CSV}...")
catalog = pd.read_csv(OFFER_CATALOG_CSV, encoding="utf-8-sig")

# Pick a diverse sample: 2 companies from each category if available
sample_frames = []
if "category" in companies.columns:
    for cat in companies["category"].dropna().unique():
        sub = companies[companies["category"] == cat].head(2)
        sample_frames.append(sub)
sample = pd.concat(sample_frames).head(10) if sample_frames else companies.head(10)
print(f"\nRunning Layer 2 on {len(sample)} sample companies...\n")

# Compute
scores = build_content_scores(sample, catalog, top_n=3)

# Print human-readable results
print("=" * 80)
print("RESULTS — top 3 recommendations per company")
print("=" * 80)

for _, comp in sample.iterrows():
    comp_id = str(comp["identifiant_unique"])
    name = str(comp.get("fr_denomination", "")).strip() or "(no name)"
    cat = str(comp.get("category", "")).strip()

    print(f"\n▸ {comp_id}  {name[:50]:<50}  [{cat}]")
    print(f"  Profile: {build_company_profile(comp.to_dict())[:120]}...")

    recs = scores[scores["identifiant_unique"] == comp_id].sort_values("rank")
    if len(recs) == 0:
        print("  (no offers passed the minimum similarity threshold)")
        continue
    for _, r in recs.iterrows():
        offer_row = catalog[catalog["offer_id"] == r["offer_id"]].iloc[0]
        offer_name = offer_row["offer_name"]
        family = offer_row["family"]
        print(f"     {r['rank']}. [{r['content_score']:.3f}] {offer_name}  ({family})")

print(f"\n{'=' * 80}")
print(f"Total (company, offer) pairs scored: {len(scores)}")
print("=" * 80)
