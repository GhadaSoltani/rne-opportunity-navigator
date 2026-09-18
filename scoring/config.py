"""
scoring/config.py
=================
Every tunable number for the prospect-intelligence layer.

Two prospect populations, one framework:
  - Google Maps universe  → conversion axis = your trained PU propensity model
                            value axis      = sector + prominence + digital
  - RNE registered set    → conversion axis = heuristic readiness (no PU score)
                            value axis      = firmographics (capital, size, need…)

Scores are 0–100 and explainable (each model returns a driver breakdown).
"""

from pathlib import Path
from core.paths import BASE_DIR

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
MAPS_SCORED_CSV     = BASE_DIR / "data" / "input"  / "scored_businesses.csv"   # PU-scored Maps
RNE_FEATURES_CSV    = BASE_DIR / "data" / "output" / "company_features.csv"    # RNE firmographics
PROSPECT_SCORES_CSV = BASE_DIR / "data" / "output" / "prospect_scores.csv"     # unified output
RNE_SCORES_CSV      = BASE_DIR / "data" / "output" / "rne_prospect_scores.csv" # secondary output

# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION PROPENSITY (Maps) — from the PU model
# ─────────────────────────────────────────────────────────────────────────────
# Which model column to treat as the conversion probability. prob_client is less
# skewed than prob_calibrated and ranks well; both are kept for display.
PU_PRIMARY_COLUMN   = "prob_client"
PU_DISPLAY_COLUMN   = "prob_client"     # shown to users as "modeled probability"
# The conversion axis used for tiering is the percentile RANK of the PU score,
# so tiers are balanced and rankable rather than crushed against 0 by the low base rate.
PROPENSITY_AS_PERCENTILE = True

# ─────────────────────────────────────────────────────────────────────────────
# VALUE POTENTIAL — firmographic model (RNE rows)
# ─────────────────────────────────────────────────────────────────────────────
VALUE_WEIGHTS = {
    "sector_propensity": 0.22,
    "capital_tier":      0.20,
    "company_size":      0.16,
    "connectivity_need": 0.16,
    "multisite":         0.10,
    "b2b":               0.08,
    "international":      0.08,
}

# Value model for Maps rows (no capital/size/need available → lighter blend).
VALUE_WEIGHTS_MAPS = {
    "sector_propensity": 0.55,
    "prominence":        0.25,   # rating × review volume = size/activity proxy
    "digital":           0.20,   # has_website → higher complexity/value
}

# Telecom-spend propensity by sector (0..1).
SECTOR_PROPENSITY = {
    "tourism":            0.90,
    "financial_services": 0.85,
    "healthcare":         0.80,
    "transport":          0.80,
    "manufacturing":      0.75,
    "education":          0.65,
    "retail":             0.60,
    "others":             0.50,
}
SECTOR_PROPENSITY_DEFAULT = 0.50

# capital_tier (RNE) → 0..1  (real labels: micro/small/medium/large/unknown)
CAPITAL_TIER_FACTOR = {
    "large": 1.00, "medium": 0.70, "small": 0.40, "micro": 0.20, "unknown": 0.30,
}
# company_size (RNE, real labels: Solo/Small/Mid/Large/Unknown) → 0..1
COMPANY_SIZE_FACTOR = {
    "large": 1.00, "mid": 0.70, "small": 0.45, "solo": 0.25, "unknown": 0.35,
}
# connectivity_need (RNE, real labels: low/medium/high) → 0..1
CONNECTIVITY_NEED_FACTOR = {
    "high": 1.00, "medium": 0.60, "low": 0.25, "unknown": 0.40,
}
# digital_signal (RNE, real labels: standard/high) → 0..1
DIGITAL_SIGNAL_FACTOR = {
    "high": 1.00, "medium": 0.60, "standard": 0.30, "low": 0.15, "unknown": 0.30,
}

# Prominence proxy (Maps): reviews are log-saturated, blended with rating.
MAPS_REVIEWS_SATURATION = 50
MAPS_RATING_MAX         = 5.0
MAPS_ACTIVITY_BLEND     = 0.5    # 0.5 rating + 0.5 review-volume

# ─────────────────────────────────────────────────────────────────────────────
# Map Google-Maps search_category / category → the 8 RNE sectors
# Matched by keyword (case-insensitive substring). First hit wins; else "others".
# ─────────────────────────────────────────────────────────────────────────────
MAPS_CATEGORY_RULES = [
    ("healthcare",        ["doctor", "dentist", "pharma", "clinic", "hospital", "medical",
                           "veterinar", "physiothe", "optic", "laborator", "medecin", "sante"]),
    ("tourism",           ["restaurant", "cafe", "coffee", "bakery", "pastry", "hotel",
                           "travel", "tourism", "gym", "beauty", "hair salon", "spa",
                           "resort", "guest house", "patisserie", "boulangerie", "agence de voyage"]),
    ("education",         ["school", "universit", "training", "driving school", "kindergarten",
                           "institut", "academy", "formation", "ecole", "creche"]),
    ("financial_services",["bank", "insurance", "assurance", "finance", "credit",
                           "comptable", "accounting", "banque"]),
    ("manufacturing",     ["manufacturer", "usine", "factory", "construction", "industri",
                           "atelier", "fabric"]),
    ("transport",         ["transport", "logistic", "shipping", "freight", "taxi",
                           "car rental", "delivery", "livraison", "location de voiture"]),
    ("retail",            ["store", "shop", "supermarket", "wholesal", "car dealer", "market",
                           "boutique", "magasin", "distribut", "grossiste", "hardware",
                           "furniture", "electronics", "clothing", "quincaillerie"]),
]

# ─────────────────────────────────────────────────────────────────────────────
# HEURISTIC READINESS (fallback conversion axis for RNE rows with no PU score)
# ─────────────────────────────────────────────────────────────────────────────
READINESS_WEIGHTS = {
    "reachability": 0.30, "digital": 0.20, "recency": 0.18,
    "maps_activity": 0.17, "confidence": 0.15,
}
REACHABILITY_POINTS = {"phone": 0.55, "website": 0.30, "email": 0.15}

# ─────────────────────────────────────────────────────────────────────────────
# PRIORITY & TIERS
# ─────────────────────────────────────────────────────────────────────────────
PRIORITY_VALUE_WEIGHT = 0.50     # priority = w*value + (1-w)*conversion

# Tier thresholds. Value is absolute 0–100; propensity is a percentile 0–100.
TIER_VALUE_THRESHOLD      = 65.0   # VPS >= this → "high value"
TIER_PROPENSITY_THRESHOLD = 70.0   # propensity percentile >= this → "high propensity"

TIER_LABELS = {
    "A": "Strategic",          # high value, high propensity → invest most
    "B": "High-value nurture", # high value, low  propensity → warm up
    "C": "Efficient",          # low  value, high propensity → cheap automation
    "D": "Monitor",            # low  value, low  propensity → minimal spend
}

# ─────────────────────────────────────────────────────────────────────────────
# CAMPAIGN PLANNER
# ─────────────────────────────────────────────────────────────────────────────
CAMPAIGN_PLAN = {
    "A": {"budget_band": "High",   "cadence": "Weekly, personalized",
          "channel_options": ["field_sales", "tele_sales", "email", "social"],
          "note": "Dedicated account executive; tailored offer bundle."},
    "B": {"budget_band": "Medium", "cadence": "Bi-weekly nurture",
          "channel_options": ["tele_sales", "email", "social", "field_sales"],
          "note": "Inside sales + paid nurture to earn a direct contact."},
    "C": {"budget_band": "Low",    "cadence": "Automated drip",
          "channel_options": ["email", "sms", "social"],
          "note": "High-volume automated digital; near-zero human cost."},
    "D": {"budget_band": "None",   "cadence": "Monitor / re-score",
          "channel_options": ["none"],
          "note": "No active spend; keep in DB and re-score as signals change."},
}
BUDGET_BAND_TND = {"High": "150–400", "Medium": "40–150", "Low": "5–40", "None": "0"}
