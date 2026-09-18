"""
ingestion/column_resolver.py
============================
Google-Maps exports come with all kinds of column names depending on the scraper.
Rather than hardcode them, we map *canonical* field names to a list of *candidate*
source headers. Point CANDIDATES at your real headers once and everything
downstream (entity resolution, master build, scoring) is stable.

Usage:
    from ingestion.column_resolver import resolve_maps_columns
    df = resolve_maps_columns(raw_maps_df)   # returns df with canonical column names
"""

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)


# canonical_name -> list of candidate source headers (case-insensitive, fuzzy)
# Calibrated to the real maps.csv export:
#   name, search_category, category, address, governorate, latitude, longitude,
#   phone, website, email, rating, reviews, hours, plus_code, place_url, scraped_at
CANDIDATES = {
    "maps_name":          ["name", "title", "business_name"],
    "maps_address":       ["address", "full_address", "adresse", "formatted_address"],
    "maps_phone":         ["phone", "phone_number", "telephone", "tel"],
    "maps_website":       ["website", "site", "url", "web"],
    "maps_email":         ["email", "e-mail", "mail"],
    "maps_rating":        ["rating", "stars", "note", "score"],
    "maps_reviews_count": ["reviews", "review_count", "reviews_count", "user_ratings_total"],
    "maps_category":      ["category", "search_category", "categories", "type", "types"],
    "maps_lat":           ["latitude", "lat", "y"],
    "maps_lng":           ["longitude", "lng", "lon", "long", "x"],
    "maps_status":        ["business_status", "status", "state"],
    "maps_hours":         ["hours", "opening_hours", "horaires"],
    "maps_place_url":     ["place_url", "url", "maps_url", "link"],
    "maps_governorate":   ["governorate", "gouvernorat", "region", "province"],
    # note: this export has no explicit 'city' column — city is inside 'address'.
}


def _normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h).strip().lower()).strip("_")


def resolve_maps_columns(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """
    Rename the columns of a raw Maps DataFrame to canonical names.

    Args:
        df:     raw DataFrame straight from the Maps export.
        strict: if True, raise when a canonical field cannot be resolved at all.
                if False (default), just log a warning and skip it.

    Returns:
        A copy of df with resolved columns renamed to their canonical names.
        Unresolved canonical fields simply won't be present (scoring treats
        missing enrichment gracefully).
    """
    df = df.copy()
    norm_to_original = {_normalize_header(c): c for c in df.columns}

    rename_map = {}
    resolved, missing = [], []

    for canonical, candidates in CANDIDATES.items():
        found = None
        for cand in candidates:
            key = _normalize_header(cand)
            if key in norm_to_original:
                found = norm_to_original[key]
                break
        if found is not None:
            rename_map[found] = canonical
            resolved.append(canonical)
        else:
            missing.append(canonical)

    df = df.rename(columns=rename_map)

    logger.info("Column resolver: resolved %d/%d canonical fields",
                len(resolved), len(CANDIDATES))
    if missing:
        msg = "Column resolver: unresolved fields: %s" % ", ".join(missing)
        if strict:
            raise KeyError(msg)
        logger.warning(msg)

    return df
