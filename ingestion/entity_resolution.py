"""
ingestion/entity_resolution.py
==============================
Match Google-Maps listings to RNE records for the same real-world business, when
there is no shared key.

Strategy (blocking + scoring, so we never do a full O(n*m) cross-join):
    1. Block   — only compare records that share a governorate/city block and a
                 name-prefix token, shrinking the candidate set massively.
    2. Score   — for each candidate pair, combine:
                    name similarity (token-set ratio)
                    locality overlap (city/governorate)
                    phone exact match (near-decisive)
    3. Decide  — accept >= ACCEPT_THRESHOLD, queue borderline pairs for review,
                 drop the rest.

Pure-Python (difflib) similarity so there is no hard dependency on rapidfuzz;
swap in rapidfuzz later for speed if the datasets get large.
"""

import logging
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

logger = logging.getLogger(__name__)

ACCEPT_THRESHOLD = 0.82     # pair score >= this → accepted match
REVIEW_THRESHOLD = 0.68     # between review and accept → human review queue

# Weights for the pair score (sum = 1.0).
W_NAME   = 0.55
W_LOCAL  = 0.20
W_PHONE  = 0.25


# ─────────────────────────────────────────────────────────────────────────────
# normalization
# ─────────────────────────────────────────────────────────────────────────────

_LEGAL_NOISE = {
    "sarl", "suarl", "sa", "societe", "société", "ste", "ets", "etablissement",
    "co", "company", "cie", "group", "groupe", "sas", "eurl", "llc", "ltd",
}


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def normalize_name(name) -> str:
    if not isinstance(name, str):
        return ""
    s = _strip_accents(name).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if t and t not in _LEGAL_NOISE]
    return " ".join(tokens)


def normalize_phone(phone) -> str:
    if phone is None:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    # keep the last 8 digits (Tunisian national number) to ignore +216 / 00216 prefixes
    return digits[-8:] if len(digits) >= 8 else digits


def _name_prefix_token(norm_name: str) -> str:
    return norm_name.split()[0] if norm_name else ""


# ─────────────────────────────────────────────────────────────────────────────
# pair scoring
# ─────────────────────────────────────────────────────────────────────────────

def _token_set_ratio(a: str, b: str) -> float:
    """Order-independent string similarity in [0,1]."""
    if not a or not b:
        return 0.0
    sa, sb = set(a.split()), set(b.split())
    inter = sa & sb
    if not inter:
        return SequenceMatcher(None, a, b).ratio()
    # sorted intersection vs each full set, take the best — robust to word order
    inter_str = " ".join(sorted(inter))
    r1 = SequenceMatcher(None, inter_str, " ".join(sorted(sa))).ratio()
    r2 = SequenceMatcher(None, inter_str, " ".join(sorted(sb))).ratio()
    r3 = SequenceMatcher(None, a, b).ratio()
    return max(r1, r2, r3)


def _locality_overlap(rne_row, maps_row) -> float:
    score = 0.0
    for col_r, col_m in [("governorate", "maps_governorate"), ("city", "maps_city")]:
        rv = str(rne_row.get(col_r, "") or "").lower()
        mv = str(maps_row.get(col_m, "") or "").lower()
        if rv and mv and (rv in mv or mv in rv):
            score += 0.5
    return min(score, 1.0)


def _pair_score(rne_row, maps_row) -> float:
    name = _token_set_ratio(rne_row["_norm_name"], maps_row["_norm_name"])
    local = _locality_overlap(rne_row, maps_row)
    phone = 1.0 if (rne_row.get("_norm_phone") and
                    rne_row.get("_norm_phone") == maps_row.get("_norm_phone")) else 0.0
    return W_NAME * name + W_LOCAL * local + W_PHONE * phone


# ─────────────────────────────────────────────────────────────────────────────
# public API
# ─────────────────────────────────────────────────────────────────────────────

def resolve_entities(
    rne_df: pd.DataFrame,
    maps_df: pd.DataFrame,
    rne_name_col: str = "fr_denomination",
    rne_phone_col: str | None = None,
) -> dict:
    """
    Match Maps rows to RNE rows.

    Returns a dict:
        {
          "matches":  DataFrame[rne_index, maps_index, score],
          "review":   DataFrame[rne_index, maps_index, score],  # borderline
          "maps_unmatched_index": list[int],
          "rne_matched_index":    set[int],
        }

    Indices refer to the positional index of each input DataFrame.
    """
    rne = rne_df.reset_index(drop=True).copy()
    maps = maps_df.reset_index(drop=True).copy()

    rne["_norm_name"] = rne.get(rne_name_col, "").map(normalize_name)
    maps["_norm_name"] = maps.get("maps_name", "").map(normalize_name)
    rne["_norm_phone"] = rne.get(rne_phone_col, "").map(normalize_phone) if rne_phone_col else ""
    maps["_norm_phone"] = maps.get("maps_phone", "").map(normalize_phone)
    rne["_block"] = rne["_norm_name"].map(_name_prefix_token)
    maps["_block"] = maps["_norm_name"].map(_name_prefix_token)

    # Build a blocking index on RNE by name-prefix token.
    rne_by_block: dict[str, list[int]] = {}
    for i, tok in enumerate(rne["_block"]):
        if tok:
            rne_by_block.setdefault(tok, []).append(i)

    matches, review = [], []
    maps_unmatched, rne_matched = [], set()

    for j, maps_row in maps.iterrows():
        tok = maps_row["_block"]
        candidates = rne_by_block.get(tok, [])
        best_i, best_score = None, 0.0
        for i in candidates:
            s = _pair_score(rne.iloc[i], maps_row)
            if s > best_score:
                best_i, best_score = i, s

        if best_i is not None and best_score >= ACCEPT_THRESHOLD:
            matches.append({"rne_index": best_i, "maps_index": j, "score": round(best_score, 3)})
            rne_matched.add(best_i)
        elif best_i is not None and best_score >= REVIEW_THRESHOLD:
            review.append({"rne_index": best_i, "maps_index": j, "score": round(best_score, 3)})
        else:
            maps_unmatched.append(j)

    logger.info("Entity resolution: %d matched, %d for review, %d Maps-only",
                len(matches), len(review), len(maps_unmatched))

    return {
        "matches": pd.DataFrame(matches),
        "review":  pd.DataFrame(review),
        "maps_unmatched_index": maps_unmatched,
        "rne_matched_index": rne_matched,
    }
