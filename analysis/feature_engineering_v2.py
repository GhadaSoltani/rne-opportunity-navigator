"""
analysis/feature_engineering_v2.py
==================================
The second wave of feature engineering — features designed to support a
recommendation engine for telecom offers (Ooredoo Business catalogue).

Organized by the sales question each feature answers:

  Section A — Company size & potential
    - add_legal_form_type()      legal form → solo / sme / corporate / partnership / other
    - add_company_size()         single label: Solo / Small / Mid / Large / Unknown
    - add_dynamism_score()       capital_per_year bucket: high / medium / low / unknown

  Section B — Product fit
    - add_business_model()       B2B / B2C / mixed / unknown
    - add_international_signal() True if international/import/export indicators
    - add_connectivity_need()    high / medium / low
    - add_fleet_size()           none / small / medium / large

  Section C — Geography
    - add_governorate()          24 Tunisian governorates

  Section D — Timing
    - add_is_new_company()       True if registered in the last 12 months

  [Eligibility hooks — placeholder for future GPS-based fibre/fixe eligibility]

All builders take a DataFrame, return a copy with the new column(s) added.
None mutates the input. Builders are idempotent and order-independent EXCEPT:
  - add_company_size() requires legal_form_type and capital_tier (from v1) to exist.
  - add_dynamism_score() requires age_years (from v1) to exist.

The orchestrator build_all_features_v2() runs them in a safe order.
"""

import logging
import re
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd

from analysis.config_v2 import (
    LEGAL_FORM_PATTERNS,
    COMPANY_SIZE_RULES, COMPANY_SIZE_DEFAULT,
    DYNAMISM_HIGH_THRESHOLD_TND, DYNAMISM_MEDIUM_THRESHOLD_TND,
    B2B_KEYWORDS, B2C_KEYWORDS,
    INTERNATIONAL_KEYWORDS,
    HIGH_CONNECTIVITY_SECTORS, LOW_CONNECTIVITY_SECTORS,
    HIGH_CONNECTIVITY_ACTIVITY_KEYWORDS,
    LARGE_FLEET_KEYWORDS, SMALL_FLEET_KEYWORDS,
    CITY_TO_GOVERNORATE,
    NEW_COMPANY_WINDOW_MONTHS,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared text helpers (mirror the conventions of feature_engineering.py)
# ─────────────────────────────────────────────────────────────────────────────

def _norm(text) -> str:
    """Lowercase + strip accents. Empty/NaN → ''."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _combined_text(row, columns) -> str:
    """Concatenate several columns of a row into one normalized blob."""
    parts = [_norm(row.get(c, "")) for c in columns]
    return " ".join(p for p in parts if p)


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Whole-word match: any of the keywords found in text?"""
    if not text:
        return False
    for kw in keywords:
        kw_n = _norm(kw)
        if not kw_n:
            continue
        # Use word boundaries when keyword is a single word; substring otherwise
        if " " in kw_n:
            if kw_n in text:
                return True
        else:
            if re.search(r"\b" + re.escape(kw_n) + r"\b", text):
                return True
    return False


# Pre-normalize keyword lists once at import for speed
_B2B            = [_norm(k) for k in B2B_KEYWORDS]
_B2C            = [_norm(k) for k in B2C_KEYWORDS]
_INTERNATIONAL  = [_norm(k) for k in INTERNATIONAL_KEYWORDS]
_HIGH_CONN_ACT  = [_norm(k) for k in HIGH_CONNECTIVITY_ACTIVITY_KEYWORDS]
_LARGE_FLEET    = [_norm(k) for k in LARGE_FLEET_KEYWORDS]
_SMALL_FLEET    = [_norm(k) for k in SMALL_FLEET_KEYWORDS]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION A — Company size & potential
# ─────────────────────────────────────────────────────────────────────────────

def add_legal_form_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse fr_forme_juridique into a clean business-tier label.

    Output column: legal_form_type ∈ {solo, sme, corporate, partnership, other, unknown}
    """
    df = df.copy()

    def classify(value):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return "unknown"
        text = _norm(value)
        if not text:
            return "unknown"
        for pattern, label in LEGAL_FORM_PATTERNS:
            if _norm(pattern) in text:
                return label
        return "other"

    src = df.get("fr_forme_juridique", pd.Series([None] * len(df)))
    df["legal_form_type"] = src.apply(classify)
    logger.info("legal_form_type distribution:\n%s",
                df["legal_form_type"].value_counts().to_string())
    return df


def add_company_size(df: pd.DataFrame) -> pd.DataFrame:
    """
    Single business-size label combining legal form, capital, and sector.

    Output column: company_size ∈ {Solo, Small, Mid, Large, Unknown}

    Depends on: legal_form_type, capital_tier, category
    """
    df = df.copy()

    def size_for(row):
        rd = row.to_dict()
        for predicate, label in COMPANY_SIZE_RULES:
            try:
                if predicate(rd):
                    return label
            except Exception:
                continue
        return COMPANY_SIZE_DEFAULT

    df["company_size"] = df.apply(size_for, axis=1)
    logger.info("company_size distribution:\n%s",
                df["company_size"].value_counts().to_string())
    return df


def add_dynamism_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bucket capital_per_year into high/medium/low/unknown.

    A 2-year-old company with 200k TND capital → 100k/year → 'high'.
    A 20-year-old company with 200k TND → 10k/year → 'medium'.
    A 10-year-old company with 10k TND → 1k/year → 'low'.

    Output columns:
      - capital_per_year (float)
      - dynamism_score   ∈ {high, medium, low, unknown}

    Depends on: capital, age_years (from feature_engineering v1)
    """
    df = df.copy()

    def per_year(row):
        try:
            cap = float(row.get("capital", 0) or 0)
            age = float(row.get("age_years", 0) or 0)
        except (TypeError, ValueError):
            return np.nan
        if cap <= 0 or pd.isna(cap):
            return np.nan
        if age < 0.5:        # too young to compute a meaningful rate
            return np.nan
        if pd.isna(age):
            return np.nan
        return cap / age

    def bucket(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "unknown"
        if v >= DYNAMISM_HIGH_THRESHOLD_TND:
            return "high"
        if v >= DYNAMISM_MEDIUM_THRESHOLD_TND:
            return "medium"
        return "low"

    df["capital_per_year"] = df.apply(per_year, axis=1).round(0)
    df["dynamism_score"]   = df["capital_per_year"].apply(bucket)
    logger.info("dynamism_score distribution:\n%s",
                df["dynamism_score"].value_counts().to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SECTION B — Product fit
# ─────────────────────────────────────────────────────────────────────────────

ACTIVITY_COLS = ["fr_activite_principale", "ar_activite_principale", "activity_clean"]


def add_business_model(df: pd.DataFrame) -> pd.DataFrame:
    """
    B2B / B2C / mixed / unknown — detected from activity text.

    Output column: business_model
    """
    df = df.copy()

    def classify(row):
        text = _combined_text(row, ACTIVITY_COLS)
        has_b2b = _contains_any(text, _B2B)
        has_b2c = _contains_any(text, _B2C)
        if has_b2b and has_b2c:
            return "mixed"
        if has_b2b:
            return "B2B"
        if has_b2c:
            return "B2C"
        return "unknown"

    df["business_model"] = df.apply(classify, axis=1)
    logger.info("business_model distribution:\n%s",
                df["business_model"].value_counts().to_string())
    return df


def add_international_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    True if activity, denomination, or commercial name suggests international scope.

    Output column: international_signal (bool)
    """
    df = df.copy()
    SEARCH_COLS = ACTIVITY_COLS + ["fr_denomination", "fr_nom_commercial"]

    def detect(row):
        text = _combined_text(row, SEARCH_COLS)
        return _contains_any(text, _INTERNATIONAL)

    df["international_signal"] = df.apply(detect, axis=1)
    pct = 100 * df["international_signal"].mean() if len(df) else 0
    logger.info("international_signal: %d / %d (%.1f%%)",
                df["international_signal"].sum(), len(df), pct)
    return df


def add_connectivity_need(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate connectivity need (high/medium/low) from sector × size × activity.

    Used to tell the salesperson which product page to open before the call.

    Output column: connectivity_need ∈ {high, medium, low}

    Depends on: category, company_size
    """
    df = df.copy()

    def level(row):
        cat  = row.get("category", "")
        size = row.get("company_size", "Unknown")
        text = _combined_text(row, ACTIVITY_COLS)

        # Override: tech / telecom / cloud activity always = high
        if _contains_any(text, _HIGH_CONN_ACT):
            return "high"

        # Inherently high-connectivity sectors
        if cat in HIGH_CONNECTIVITY_SECTORS:
            return "high" if size in ("Mid", "Large") else "medium"

        # Inherently low
        if cat in LOW_CONNECTIVITY_SECTORS:
            return "low"

        # Size-driven default
        if size == "Large":
            return "high"
        if size == "Mid":
            return "medium"
        if size in ("Small", "Solo"):
            # Multi-site small companies still need medium (multiple connections)
            if row.get("multisite_signal"):
                return "medium"
            return "low"
        return "low"

    df["connectivity_need"] = df.apply(level, axis=1)
    logger.info("connectivity_need distribution:\n%s",
                df["connectivity_need"].value_counts().to_string())
    return df


def add_fleet_size(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate fleet size when mobility signal is present.

    Output column: fleet_size ∈ {none, small, medium, large}
    """
    df = df.copy()

    def estimate(row):
        if not row.get("mobility_signal"):
            return "none"
        text = _combined_text(row, ACTIVITY_COLS)
        cat   = row.get("category", "")
        size  = row.get("company_size", "Unknown")

        # Activity keywords first
        if _contains_any(text, _LARGE_FLEET):
            return "large" if size in ("Mid", "Large") else "medium"
        if _contains_any(text, _SMALL_FLEET):
            return "small"

        # Fallback: transport sector + size
        if cat == "transport":
            if size == "Large":
                return "large"
            if size == "Mid":
                return "medium"
            return "small"

        # Non-transport with mobility signal (e.g. multisite chain)
        return "small"

    df["fleet_size"] = df.apply(estimate, axis=1)
    logger.info("fleet_size distribution:\n%s",
                df["fleet_size"].value_counts().to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SECTION C — Geography
# ─────────────────────────────────────────────────────────────────────────────

def add_governorate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map the detected city to its Tunisian governorate.

    Output column: governorate (string, or "Unknown")

    Depends on: city (from feature_engineering v1)
    """
    df = df.copy()

    def to_gov(city):
        if city is None or (isinstance(city, float) and np.isnan(city)):
            return "Unknown"
        c = str(city).strip()
        if not c or c.lower() in ("unknown", "other"):
            return "Unknown"
        return CITY_TO_GOVERNORATE.get(c, "Unknown")

    src = df.get("city", pd.Series(["Unknown"] * len(df)))
    df["governorate"] = src.apply(to_gov)
    logger.info("governorate distribution (top 8):\n%s",
                df["governorate"].value_counts().head(8).to_string())
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SECTION D — Timing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(value):
    """Reuse the same lenient date parser as feature_engineering v1."""
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
    try:
        parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)
        return parsed.to_pydatetime() if not pd.isna(parsed) else None
    except Exception:
        return None


def add_is_new_company(df: pd.DataFrame, reference_date: datetime | None = None) -> pd.DataFrame:
    """
    True if the company was registered within the last NEW_COMPANY_WINDOW_MONTHS.

    On the real RNE dataset, ~40% of companies were registered in 2025 — these
    are prime targets: no existing provider yet, no contract to break.

    Output column: is_new_company (bool)

    Uses: date_immatriculation
    """
    df = df.copy()
    ref = reference_date or datetime.now()

    def is_new(value):
        d = _parse_date(value)
        if d is None:
            return False
        # months between d and ref
        months = (ref.year - d.year) * 12 + (ref.month - d.month)
        return 0 <= months <= NEW_COMPANY_WINDOW_MONTHS

    src = df.get("date_immatriculation", pd.Series([None] * len(df)))
    df["is_new_company"] = src.apply(is_new)
    n_new = int(df["is_new_company"].sum())
    pct = 100 * n_new / len(df) if len(df) else 0
    logger.info("is_new_company (registered within last %d months): %d / %d (%.1f%%)",
                NEW_COMPANY_WINDOW_MONTHS, n_new, len(df), pct)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility hooks — placeholder for the future GPS-based features
# ─────────────────────────────────────────────────────────────────────────────

def add_eligibility_placeholders(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reserves the columns 'eligibility_fibre' and 'eligibility_fixe' for the
    upcoming GPS-coordinate-based eligibility check. Until that is wired in,
    both columns default to None (unknown).

    The recommendation engine and any downstream UI can already reference
    these columns; they will start producing real values once the GPS layer
    is plugged in here.
    """
    df = df.copy()
    if "eligibility_fibre" not in df.columns:
        df["eligibility_fibre"] = None
    if "eligibility_fixe" not in df.columns:
        df["eligibility_fixe"] = None
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator — runs v2 features in the right order
# ─────────────────────────────────────────────────────────────────────────────

def build_all_features_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run every v2 builder. Order matters because some features depend on
    columns produced by earlier ones (and on v1 features that must already
    be present: capital_tier, age_years, city, multisite_signal).
    """
    # Section A — must run BEFORE B (connectivity_need depends on company_size)
    df = add_legal_form_type(df)
    df = add_company_size(df)        # uses legal_form_type + capital_tier + category
    df = add_dynamism_score(df)      # uses capital + age_years

    # Section B
    df = add_business_model(df)
    df = add_international_signal(df)
    df = add_connectivity_need(df)   # uses company_size + category + multisite_signal
    df = add_fleet_size(df)          # uses mobility_signal + company_size + category

    # Section C
    df = add_governorate(df)         # uses city

    # Section D
    df = add_is_new_company(df)

    # Eligibility placeholders (GPS-based work coming later)
    df = add_eligibility_placeholders(df)
    return df
