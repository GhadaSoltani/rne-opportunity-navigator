"""
analysis/column_resolver.py
===========================
Maps the six business-facing fields the sales team needs to whatever the real
column headers happen to be in the segmented / cleaned CSV.

Why this exists:
    The RNE extraction has gone through several iterations and the exact header
    names are not guaranteed (e.g. director name might be `fr_dirigeant`,
    `dirigeant`, or `gerant`; the activity-start date might be `date_debut_activite`
    or `date_immatriculation`). Guessing a name and silently producing an empty
    column is the worst outcome for a sales tool. So instead of hard-coding, we
    resolve each field against a ranked list of candidate names and report which
    one we used.

Public API:
    resolve_columns(df)  ->  (mapping, report)
        mapping : {business_field: real_column_name_or_None}
        report  : list of dicts describing what was found / missing
"""

import logging
import unicodedata

logger = logging.getLogger(__name__)


# ── The six fields the sales table needs, each with ranked candidate headers ──
# Order matters: the first candidate found in the dataframe wins.
FIELD_CANDIDATES = {
    "identifiant_unique": [
        "identifiant_unique", "identifiant", "id_unique", "matricule",
        "id", "rne_id", "numero_rne",
    ],
    "denomination": [
        # French / latin-script denomination only — Arabic is resolved
        # separately as a per-row fallback (see ARABIC_DENOMINATION_CANDIDATES)
        "fr_denomination", "denomination", "denomination_fr",
        "raison_sociale", "nom_entreprise",
    ],
    "categorie": [
        "category", "categorie", "secteur", "sector",
    ],
    "activite": [
        # cleaned / combined activity first, then raw FR, then AR
        "activity_clean", "activite_clean", "activity_raw_combined",
        "activite_combinee", "fr_activite_principale", "activite_principale",
        "fr_activite", "ar_activite_principale", "ar_activite",
    ],
    "adresse": [
        # French address preferred, Arabic as fallback (handled specially below)
        "fr_adresse", "adresse", "adresse_fr",
    ],
    "date_debut_activite": [
        "date_debut_activite", "date_debut", "date_activite",
        "date_immatriculation", "date_creation",
    ],
    "dirigeant": [
        "fr_dirigeant", "dirigeant", "fr_gerant", "gerant",
        "fr_representant", "representant", "nom_dirigeant", "responsable",
    ],
}

# Arabic-address fallbacks (used only when no French address column is found,
# or, per-row, when the French address value is empty)
ARABIC_ADDRESS_CANDIDATES = ["ar_adresse", "adresse_ar", "adresse_arabe"]

# Arabic-denomination fallbacks — same idea: used per-row when the French
# denomination is empty for that company.
ARABIC_DENOMINATION_CANDIDATES = ["ar_denomination", "denomination_ar", "denomination_arabe"]


def _norm(name: str) -> str:
    """Normalize a header for tolerant matching: lowercase, strip accents/spaces."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip().replace(" ", "_").replace("-", "_")


def _find_first(df_cols_norm: dict, candidates: list[str]):
    """Return the real column name for the first candidate present, else None."""
    for cand in candidates:
        key = _norm(cand)
        if key in df_cols_norm:
            return df_cols_norm[key]
    return None


def resolve_columns(df):
    """
    Resolve the six business fields against the dataframe's real headers.

    Returns:
        mapping        : dict {business_field -> real_column_name or None}
        report         : list of dicts [{field, resolved_to, status}]
        ar_address_col : the Arabic address column name if present, else None
        ar_denomination_col : the Arabic denomination column name if present, else None
    """
    # Map normalized header -> original header so we can match tolerantly
    df_cols_norm = {_norm(c): c for c in df.columns}

    mapping = {}
    report = []

    for field, candidates in FIELD_CANDIDATES.items():
        real = _find_first(df_cols_norm, candidates)
        mapping[field] = real
        report.append({
            "field": field,
            "resolved_to": real if real else "(not found)",
            "status": "ok" if real else "MISSING",
        })

    # Arabic fallback columns (used to fill empty French values, per row)
    ar_address_col      = _find_first(df_cols_norm, ARABIC_ADDRESS_CANDIDATES)
    ar_denomination_col = _find_first(df_cols_norm, ARABIC_DENOMINATION_CANDIDATES)

    # Log a clear summary
    for r in report:
        if r["status"] == "ok":
            logger.info("Resolved %-22s -> %s", r["field"], r["resolved_to"])
        else:
            logger.warning("Could NOT resolve %-22s (looked for: %s)",
                           r["field"], ", ".join(FIELD_CANDIDATES[r["field"]][:4]))
    if ar_address_col:
        logger.info("Arabic address fallback     -> %s", ar_address_col)
    if ar_denomination_col:
        logger.info("Arabic denomination fallback -> %s", ar_denomination_col)

    return mapping, report, ar_address_col, ar_denomination_col
