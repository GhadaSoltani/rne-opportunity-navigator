"""
scoring/models.py
=================
Value model + fallback readiness model, plus the Maps→sector mapper.

  value_potential(row)      → (VPS 0–100, breakdown)   auto-detects firmographic
                              (RNE) vs Maps-based value from the fields present.
  conversion_readiness(row) → (CRS 0–100, breakdown)   heuristic fallback used only
                              for rows with no PU propensity (RNE registered set).

Conversion propensity for Maps rows is computed from the PU model column in
scoring/propensity.py (needs the whole column for percentile ranking), not here.
"""

import math

from scoring.config import (
    VALUE_WEIGHTS, VALUE_WEIGHTS_MAPS,
    SECTOR_PROPENSITY, SECTOR_PROPENSITY_DEFAULT,
    CAPITAL_TIER_FACTOR, COMPANY_SIZE_FACTOR, CONNECTIVITY_NEED_FACTOR,
    DIGITAL_SIGNAL_FACTOR, MAPS_CATEGORY_RULES,
    MAPS_REVIEWS_SATURATION, MAPS_RATING_MAX, MAPS_ACTIVITY_BLEND,
    READINESS_WEIGHTS, REACHABILITY_POINTS,
)


# ── helpers ─────────────────────────────────────────────────────────────────
def _get(row, key, default=None):
    val = row.get(key, default) if hasattr(row, "get") else default
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    return val

def _truthy(val) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in {"true", "1", "yes", "y", "t"}
    return bool(val)

def _has_value(val) -> bool:
    if val is None:
        return False
    if isinstance(val, float) and math.isnan(val):
        return False
    return str(val).strip().lower() not in {"", "nan", "none", "null", "-", "0"}


# ── Maps category → sector ──────────────────────────────────────────────────
def maps_sector(row) -> str:
    text = " ".join(str(_get(row, c, "") or "") for c in
                    ("search_category", "category", "maps_category")).lower()
    for sector, keywords in MAPS_CATEGORY_RULES:
        if any(k in text for k in keywords):
            return sector
    return "others"


# ── prominence / activity proxy ─────────────────────────────────────────────
def _maps_activity_factor(row) -> float:
    rating  = _get(row, "rating",  _get(row, "maps_rating"))
    reviews = _get(row, "reviews", _get(row, "maps_reviews_count"))
    if rating is None and reviews is None:
        return 0.30
    rating_f = 0.0
    if rating is not None:
        try: rating_f = min(float(rating) / MAPS_RATING_MAX, 1.0)
        except (TypeError, ValueError): pass
    volume_f = 0.0
    if reviews is not None:
        try:
            r = max(float(reviews), 0.0)
            volume_f = min(math.log1p(r) / math.log1p(MAPS_REVIEWS_SATURATION), 1.0)
        except (TypeError, ValueError): pass
    b = MAPS_ACTIVITY_BLEND
    return b * rating_f + (1 - b) * volume_f


# ── VALUE POTENTIAL ─────────────────────────────────────────────────────────
def _value_firmographic(row):
    w = VALUE_WEIGHTS
    sector = str(_get(row, "category", "others") or "others").lower()
    factors = {
        "sector_propensity": SECTOR_PROPENSITY.get(sector, SECTOR_PROPENSITY_DEFAULT),
        "capital_tier":      CAPITAL_TIER_FACTOR.get(str(_get(row, "capital_tier", "unknown")).lower(), 0.30),
        "company_size":      COMPANY_SIZE_FACTOR.get(str(_get(row, "company_size", "unknown")).lower(), 0.35),
        "connectivity_need": CONNECTIVITY_NEED_FACTOR.get(str(_get(row, "connectivity_need", "unknown")).lower(), 0.40),
        "multisite":         1.0 if _truthy(_get(row, "multisite_signal", False)) else 0.0,
        "b2b":               1.0 if str(_get(row, "business_model", "")).upper() == "B2B" else 0.0,
        "international":      1.0 if _truthy(_get(row, "international_signal", False)) else 0.0,
    }
    breakdown = {k: round(100 * w[k] * factors[k], 2) for k in w}
    return min(round(sum(breakdown.values()), 2), 100.0), breakdown


def _value_maps(row):
    w = VALUE_WEIGHTS_MAPS
    sector = maps_sector(row)
    has_web = _truthy(_get(row, "has_website", False)) or _has_value(_get(row, "website"))
    factors = {
        "sector_propensity": SECTOR_PROPENSITY.get(sector, SECTOR_PROPENSITY_DEFAULT),
        "prominence":        _maps_activity_factor(row),
        "digital":           1.0 if has_web else 0.3,
    }
    breakdown = {k: round(100 * w[k] * factors[k], 2) for k in w}
    return min(round(sum(breakdown.values()), 2), 100.0), breakdown


def value_potential(row):
    """Auto-detect: firmographic value if RNE fields present, else Maps-based."""
    firmographic = _has_value(_get(row, "capital_tier")) or _has_value(_get(row, "company_size"))
    return _value_firmographic(row) if firmographic else _value_maps(row)


# ── CONVERSION READINESS (heuristic fallback for RNE rows) ──────────────────
def _reachability_factor(row) -> float:
    pts = 0.0
    if _has_value(_get(row, "phone")) or _has_value(_get(row, "maps_phone")) \
            or _truthy(_get(row, "callable_prospect", False)):
        pts += REACHABILITY_POINTS["phone"]
    if _has_value(_get(row, "website")) or _has_value(_get(row, "maps_website")):
        pts += REACHABILITY_POINTS["website"]
    if _has_value(_get(row, "email")) or _has_value(_get(row, "maps_email")):
        pts += REACHABILITY_POINTS["email"]
    return min(pts, 1.0)


def conversion_readiness(row):
    w = READINESS_WEIGHTS
    try: confidence = float(_get(row, "confidence", 0.5) or 0.5)
    except (TypeError, ValueError): confidence = 0.5
    factors = {
        "reachability":  _reachability_factor(row),
        "digital":       DIGITAL_SIGNAL_FACTOR.get(str(_get(row, "digital_signal", "unknown")).lower(), 0.30),
        "recency":       1.0 if _truthy(_get(row, "is_new_company", False)) else 0.35,
        "maps_activity": _maps_activity_factor(row),
        "confidence":    max(0.0, min(confidence, 1.0)),
    }
    breakdown = {k: round(100 * w[k] * factors[k], 2) for k in w}
    return min(round(sum(breakdown.values()), 2), 100.0), breakdown
