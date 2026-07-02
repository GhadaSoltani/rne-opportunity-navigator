"""
analysis/feature_engineering.py
================================
Builds the analytical features used by the recommendation engine:

    capital_tier      — size proxy from `capital`
    maturity          — age bucket from `date_immatriculation`
    digital_signal    — keyword-based signal (high / medium / standard)
    mobility_signal   — boolean from activity keywords
    multisite_signal  — boolean from activity keywords OR large capital
    city              — extracted from `fr_adresse` (bonus)
    data_quality      — 0..1 completeness score per row (bonus)

Every function takes a DataFrame and returns a new DataFrame with the column added.
None mutate the input in place — they return a copy. This keeps the pipeline easy
to compose and easy to unit-test.
"""

import logging
import re
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd

from analysis.config import (
    CAPITAL_TIERS,
    MATURITY_BUCKETS,
    DIGITAL_HIGH_KEYWORDS,
    DIGITAL_MEDIUM_KEYWORDS,
    MOBILITY_KEYWORDS,
    MULTISITE_KEYWORDS,
    MULTISITE_CAPITAL_FLOOR,
    KNOWN_CITIES,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Text normalization helper — strip accents and lowercase for keyword matching
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text) -> str:
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    s = str(text)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _combined_activity(row) -> str:
    """Concatenate FR + AR activity into a single normalized blob for keyword search."""
    fr = _normalize(row.get("fr_activite_principale", ""))
    ar = _normalize(row.get("ar_activite_principale", ""))
    return f"{fr} {ar}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 — capital_tier
# ─────────────────────────────────────────────────────────────────────────────

def add_capital_tier(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def to_tier(value):
        try:
            capital = float(value)
        except (TypeError, ValueError):
            return "unknown"
        if pd.isna(capital) or capital <= 0:
            return "unknown"
        for threshold, label in CAPITAL_TIERS:
            if capital < threshold:
                return label
        return CAPITAL_TIERS[-1][1]

    df["capital_tier"] = df.get("capital", pd.Series([None] * len(df))).apply(to_tier)
    logger.info("Capital tier distribution:\n%s", df["capital_tier"].value_counts().to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2 — maturity
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(value):
    """Parse common French date formats. Returns datetime or None."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue

    # last resort: pandas, but suppress chatty warnings
    try:
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)
        return parsed.to_pydatetime() if not pd.isna(parsed) else None
    except Exception:
        return None


def add_maturity(df: pd.DataFrame, reference_date: datetime | None = None) -> pd.DataFrame:
    df = df.copy()
    ref = reference_date or datetime.now()

    def to_maturity(value):
        d = _parse_date(value)
        if d is None:
            return "unknown"
        age_years = (ref - d).days / 365.25
        if age_years < 0:
            return "unknown"
        for threshold, label in MATURITY_BUCKETS:
            if age_years < threshold:
                return label
        return MATURITY_BUCKETS[-1][1]

    def to_age_years(value):
        d = _parse_date(value)
        if d is None:
            return np.nan
        age = (ref - d).days / 365.25
        return round(age, 2) if age >= 0 else np.nan

    date_col = df.get("date_immatriculation", pd.Series([None] * len(df)))
    df["maturity"] = date_col.apply(to_maturity)
    df["age_years"] = date_col.apply(to_age_years)
    logger.info("Maturity distribution:\n%s", df["maturity"].value_counts().to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3 — digital_signal
# ─────────────────────────────────────────────────────────────────────────────

# Pre-normalize keyword lists once at import for speed
_DIGITAL_HIGH   = [_normalize(k) for k in DIGITAL_HIGH_KEYWORDS]
_DIGITAL_MEDIUM = [_normalize(k) for k in DIGITAL_MEDIUM_KEYWORDS]
_MOBILITY       = [_normalize(k) for k in MOBILITY_KEYWORDS]
_MULTISITE      = [_normalize(k) for k in MULTISITE_KEYWORDS]


def _matches_any(text: str, keywords: list[str]) -> list[str]:
    """Return the list of keywords that appear inside text (whole-word match)."""
    if not text:
        return []
    found = []
    for kw in keywords:
        # whole-word match using word boundaries
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, text):
            found.append(kw)
    return found


def add_digital_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def classify(row):
        text = _combined_activity(row)
        if _matches_any(text, _DIGITAL_HIGH):
            return "high"
        if _matches_any(text, _DIGITAL_MEDIUM):
            return "medium"
        return "standard"

    df["digital_signal"] = df.apply(classify, axis=1)
    logger.info("Digital signal distribution:\n%s", df["digital_signal"].value_counts().to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Feature 4 — mobility_signal
# ─────────────────────────────────────────────────────────────────────────────

def add_mobility_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def has_mobility(row):
        text = _combined_activity(row)
        return bool(_matches_any(text, _MOBILITY))

    df["mobility_signal"] = df.apply(has_mobility, axis=1)
    logger.info("Mobility signal: %d / %d (%.1f%%)",
                df["mobility_signal"].sum(), len(df),
                100 * df["mobility_signal"].mean() if len(df) else 0)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Feature 5 — multisite_signal
# ─────────────────────────────────────────────────────────────────────────────

def add_multisite_signal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def has_multisite(row):
        text = _combined_activity(row)
        if _matches_any(text, _MULTISITE):
            return True
        try:
            return float(row.get("capital", 0) or 0) >= MULTISITE_CAPITAL_FLOOR
        except (TypeError, ValueError):
            return False

    df["multisite_signal"] = df.apply(has_multisite, axis=1)
    logger.info("Multisite signal: %d / %d (%.1f%%)",
                df["multisite_signal"].sum(), len(df),
                100 * df["multisite_signal"].mean() if len(df) else 0)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Bonus 1 — city (extracted from fr_adresse)
# ─────────────────────────────────────────────────────────────────────────────

_CITY_PATTERNS = [
    (city, re.compile(r"\b" + re.escape(_normalize(city)) + r"\b"))
    for city in KNOWN_CITIES
]


def add_city(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def extract_city(address):
        if not address or pd.isna(address):
            return "unknown"
        text = _normalize(address)
        for city, pattern in _CITY_PATTERNS:
            if pattern.search(text):
                return city
        return "other"

    df["city"] = df.get("fr_adresse", pd.Series([None] * len(df))).apply(extract_city)
    top_cities = df["city"].value_counts().head(8)
    logger.info("Top cities:\n%s", top_cities.to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Bonus 2 — data_quality_score (0..1)
# ─────────────────────────────────────────────────────────────────────────────

QUALITY_CRITICAL_COLUMNS = [
    "fr_denomination",
    "fr_adresse",
    "fr_activite_principale",
    "capital",
    "date_immatriculation",
]


def _is_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    s = str(value).strip()
    return bool(s) and s.lower() not in ("nan", "none", "null", "0", "")


def add_data_quality(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    available_cols = [c for c in QUALITY_CRITICAL_COLUMNS if c in df.columns]
    if not available_cols:
        df["data_quality_score"] = 0.0
        df["callable_prospect"]  = False
        return df

    def score_row(row):
        present = sum(_is_present(row.get(c)) for c in available_cols)
        return round(present / len(available_cols), 2)

    df["data_quality_score"] = df.apply(score_row, axis=1)

    # A prospect is "callable" if we at least have a denomination AND (address OR activity)
    def is_callable(row):
        has_name     = _is_present(row.get("fr_denomination"))
        has_address  = _is_present(row.get("fr_adresse"))
        has_activity = _is_present(row.get("fr_activite_principale")) or _is_present(row.get("ar_activite_principale"))
        return has_name and (has_address or has_activity)

    df["callable_prospect"] = df.apply(is_callable, axis=1)
    logger.info("Callable prospects: %d / %d (%.1f%%)",
                df["callable_prospect"].sum(), len(df),
                100 * df["callable_prospect"].mean() if len(df) else 0)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# One-call orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def build_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """Run every feature builder in the right order and return the enriched dataframe.

    Runs v1 features (size proxy, maturity, signals, geography, quality) and then
    chains the v2 features (legal form, company size, dynamism, business model,
    international, connectivity need, fleet size, governorate, new-company flag,
    eligibility placeholders). Calling this once gives you the full feature set.
    """
    df = add_capital_tier(df)
    df = add_maturity(df)
    df = add_digital_signal(df)
    df = add_mobility_signal(df)
    df = add_multisite_signal(df)
    df = add_city(df)
    df = add_data_quality(df)

    # v2 features — must run AFTER the v1 ones above because some depend on
    # columns built here (capital_tier, age_years, city, multisite_signal).
    from analysis.feature_engineering_v2 import build_all_features_v2
    df = build_all_features_v2(df)
    return df
