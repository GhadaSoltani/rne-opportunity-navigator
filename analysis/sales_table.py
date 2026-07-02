"""
analysis/sales_table.py
=======================
Builds the clean, sales-facing company table requested for the internal tool.

Exactly six columns, in this order, with these display labels:

    Identifiant unique
    Dénomination          (French name; falls back to Arabic per-row if FR empty)
    Catégorie             (the segmented category)
    Activité              (the cleaned / combined activity text)
    Adresse               (French address; falls back to Arabic per-row if FR empty)
    Date début d'activité
    Nom du dirigeant

Nothing is guessed: every column is resolved from the real headers via
analysis.column_resolver, and any field that cannot be found is rendered as an
empty column (never crashes) and reported.
"""

import logging

import numpy as np
import pandas as pd

from analysis.column_resolver import resolve_columns

logger = logging.getLogger(__name__)


# Display order + the exact French labels for the UI
DISPLAY_LABELS = {
    "identifiant_unique":  "Identifiant unique",
    "denomination":        "Dénomination",
    "categorie":           "Catégorie",
    "activite":            "Activité",
    "adresse":             "Adresse",
    "date_debut_activite": "Date début d'activité",
    "dirigeant":           "Nom du dirigeant",
}
DISPLAY_ORDER = list(DISPLAY_LABELS.keys())


def _clean_value(v) -> str:
    """Render a single cell as a clean string; empty-ish values become ''."""
    if v is None:
        return ""
    if isinstance(v, float) and np.isnan(v):
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null", "nat"):
        return ""
    return s


def _is_empty(v) -> bool:
    return _clean_value(v) == ""


def _fr_with_ar_fallback(df: pd.DataFrame, fr_col: str | None, ar_col: str | None) -> list[str]:
    """
    Per-row: use the French value if it's non-empty, otherwise fall back to
    the Arabic value for that same row. If a company has both, French wins.
    If it has only one of the two, that one is used. If it has neither, the
    cell is empty.
    """
    n = len(df)
    fr_series = df[fr_col] if fr_col and fr_col in df.columns else pd.Series([""] * n, index=df.index)
    ar_series = df[ar_col] if ar_col and ar_col in df.columns else pd.Series([""] * n, index=df.index)

    values = []
    for fr_v, ar_v in zip(fr_series, ar_series):
        fr_clean = _clean_value(fr_v)
        values.append(fr_clean if fr_clean else _clean_value(ar_v))
    return values


def build_sales_table(df: pd.DataFrame):
    """
    Build the six-/seven-column sales table.

    Returns:
        table_df : DataFrame with the French display-label columns, in order
        report   : the column-resolution report (what mapped to what)
    """
    mapping, report, ar_address_col, ar_denomination_col = resolve_columns(df)

    out = pd.DataFrame(index=df.index)

    # Fields that need a per-row French-with-Arabic-fallback merge, and the
    # Arabic column to fall back to for each.
    FALLBACK_FIELDS = {
        "denomination": ar_denomination_col,
        "adresse":      ar_address_col,
    }

    for field in DISPLAY_ORDER:
        real_col = mapping.get(field)
        label = DISPLAY_LABELS[field]

        if field in FALLBACK_FIELDS:
            out[label] = _fr_with_ar_fallback(df, real_col, FALLBACK_FIELDS[field])
        else:
            if real_col and real_col in df.columns:
                out[label] = df[real_col].map(_clean_value)
            else:
                # Field not found — empty column, already reported as MISSING
                out[label] = ""

    # Log coverage so the user can see how complete each column is
    for label in out.columns:
        non_empty = (out[label].astype(str).str.len() > 0).sum()
        pct = (100 * non_empty / len(out)) if len(out) else 0
        logger.info("Column %-24s filled: %d/%d (%.0f%%)", label, non_empty, len(out), pct)

    return out, report
