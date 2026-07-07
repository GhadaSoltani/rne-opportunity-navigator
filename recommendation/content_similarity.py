"""
recommendation/content_similarity.py
====================================
Layer 2 — Content-based similarity.

Builds a text profile for each company and each offer, embeds them with
a multilingual sentence-transformer, then ranks offers by cosine
similarity to each company.

The company profile describes what the company IS (sector, size, activity).
The offer profile describes what the offer DOES (family, features, targets).
Neither side mentions the other — the embedder finds the semantic match.

The offer profile also consumes the optional `strong_sectors` column from
the catalog, expanding sector codes into French labels so the embedder
picks up Ooredoo's authoritative sector alignment.

Public API:
    build_content_scores(companies_df, catalog_df, top_n, model) -> DataFrame
"""

import logging
import re
import unicodedata
from functools import lru_cache

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from recommendation.config import (
    EMBEDDING_MODEL_NAME,
    CONTENT_TOP_N,
    CONTENT_MIN_SIMILARITY,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _truthy(v) -> bool:
    return v in (True, "True", "true", 1, "1")


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null", ""):
        return ""
    return s


# Human-readable sector labels the embedder recognizes as business concepts.
_SECTOR_LABELS = {
    "retail":             "commerce et distribution, vente au detail, magasin",
    "manufacturing":      "industrie, fabrication, production, transformation",
    "transport":          "transport, logistique, livraison, fret",
    "tourism":            "tourisme, hotellerie, restauration, voyages",
    "healthcare":         "sante, medical, clinique, laboratoire",
    "education":          "education, formation, enseignement, ecole",
    "financial_services": "banque, assurance, services financiers, comptabilite",
    "others":             "entreprise de services",
}

_SIZE_LABELS = {
    "Solo":    "auto-entrepreneur, petite structure individuelle",
    "Small":   "petite entreprise",
    "Mid":     "entreprise de taille moyenne",
    "Large":   "grande entreprise",
    "Unknown": "",
}

_MATURITY_LABELS = {
    "startup":     "entreprise recente, jeune structure",
    "growing":     "entreprise en croissance",
    "established": "entreprise etablie",
    "mature":      "entreprise mature de longue date",
    "unknown":     "",
}


# ─────────────────────────────────────────────────────────────────────────────
# Company profile — describes what the company IS
# ─────────────────────────────────────────────────────────────────────────────

def build_company_profile(row: dict) -> str:
    """Build a French text profile for one company row."""
    parts = []

    activity = _clean(row.get("fr_activite_principale"))
    if not activity:
        activity = _clean(row.get("activity_raw_combined"))
        activity = re.sub(r"[\u0600-\u06FF]+", "", activity)
        activity = re.sub(r"\s*\|\s*", " ", activity).strip()
    if activity:
        parts.append(f"Activite: {activity[:400]}")

    category = _clean(row.get("category")).lower()
    if category:
        label = _SECTOR_LABELS.get(category, category)
        if label:
            parts.append(f"Secteur: {label}")

    size = _clean(row.get("company_size"))
    if size:
        label = _SIZE_LABELS.get(size, "")
        if label:
            parts.append(f"Taille: {label}")

    maturity = _clean(row.get("maturity")).lower()
    if maturity:
        label = _MATURITY_LABELS.get(maturity, "")
        if label:
            parts.append(label)

    biz = _clean(row.get("business_model"))
    if biz == "B2B":
        parts.append("Clientele professionnelle B2B")
    elif biz == "B2C":
        parts.append("Clientele grand public B2C")

    if _truthy(row.get("international_signal")):
        parts.append("Activite internationale, import export")
    if _truthy(row.get("multisite_signal")):
        parts.append("Plusieurs sites, agences ou succursales")
    if _truthy(row.get("mobility_signal")):
        parts.append("Equipes mobiles sur le terrain, vehicules")

    city = _clean(row.get("city"))
    if city and city.lower() not in ("unknown", "other"):
        parts.append(f"Situee a {city}")

    if not parts:
        return "Entreprise tunisienne."
    return ". ".join(parts) + "."


# ─────────────────────────────────────────────────────────────────────────────
# Offer profile — describes what the offer DOES
# ─────────────────────────────────────────────────────────────────────────────

def build_offer_profile(row: dict) -> str:
    """
    Build a French text profile for one catalog offer.

    If the catalog row has a `strong_sectors` column (comma-separated
    sector codes like "tourism,retail"), they are expanded into French
    labels so the embedder picks up Ooredoo's sector alignment.
    """
    name   = _clean(row.get("offer_name"))
    family = _clean(row.get("family"))
    description = _clean(row.get("description"))

    family_words = {
        "mobile":        "forfait mobile professionnel, telephonie",
        "mobile_data":   "internet mobile, SIM data, 4G",
        "fixed":         "connectivite fixe entreprise, ligne fixe",
        "security":      "cybersecurite, protection informatique",
        "cloud":         "services cloud, hebergement",
        "collaboration": "collaboration bureautique, communication unifiee",
        "iot":           "internet des objets, capteurs connectes",
        "managed":       "services manages, infogerance",
    }.get(family, family)

    parts = [f"Offre: {name}", f"Categorie: {family_words}"]
    if description:
        parts.append(description)

    # Expand strong_sectors into readable French sector labels
    strong_sectors_raw = _clean(row.get("strong_sectors"))
    if strong_sectors_raw:
        sector_codes = [s.strip().lower() for s in strong_sectors_raw.split(",")
                        if s.strip()]
        sector_phrases = [_SECTOR_LABELS.get(code, code)
                          for code in sector_codes
                          if _SECTOR_LABELS.get(code, code)]
        if sector_phrases:
            parts.append("Cible: " + "; ".join(sector_phrases))

    # Capability tags
    tags = []
    if _truthy(row.get("is_mobility")):
        tags.append("mobilite, flotte, vehicules")
    if _truthy(row.get("is_multisite")):
        tags.append("multi-sites, agences")
    if _truthy(row.get("is_security")):
        tags.append("securite, protection")
    if tags:
        parts.append("Adapte a: " + " ; ".join(tags))

    return ". ".join(parts) + "."


# ─────────────────────────────────────────────────────────────────────────────
# Model cache
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_model(model_name: str = EMBEDDING_MODEL_NAME) -> SentenceTransformer:
    logger.info("Loading embedding model: %s (first time only)", model_name)
    return SentenceTransformer(model_name)


def _why_matched(company_profile: str, offer_profile: str, top_k: int = 3) -> str:
    """Find the most meaningful overlapping terms between profiles."""
    stop = {
        "de", "du", "des", "la", "le", "les", "un", "une", "et", "en", "au",
        "aux", "a", "pour", "avec", "dans", "est", "sur", "par", "ou", "que",
        "qui", "ce", "cette", "d", "l", "s", "c", "offre", "entreprise",
        "secteur", "activite", "categorie", "adapte", "situee", "clientele",
        "plusieurs", "cible",
    }

    def tokens(text):
        text = unicodedata.normalize("NFKD", text.lower())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return {w for w in re.findall(r"[a-z]{4,}", text) if w not in stop}

    common = tokens(company_profile) & tokens(offer_profile)
    if not common:
        return "semantic match"
    return ", ".join(sorted(common, key=len, reverse=True)[:top_k])


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_content_scores(
    companies_df: pd.DataFrame,
    catalog_df:   pd.DataFrame,
    top_n:        int = CONTENT_TOP_N,
    model:        SentenceTransformer | None = None,
) -> pd.DataFrame:
    """
    Compute Layer 2 content-based similarity scores.

    Returns DataFrame with columns:
        identifiant_unique, offer_id, content_score, rank, why_matched
    """
    if "identifiant_unique" not in companies_df.columns:
        raise ValueError("companies_df must have 'identifiant_unique' column")
    if "offer_id" not in catalog_df.columns:
        raise ValueError("catalog_df must have 'offer_id' column")

    logger.info("Building company profiles for %d companies...",
                len(companies_df))
    company_profiles = [build_company_profile(r)
                        for r in companies_df.to_dict("records")]

    logger.info("Building offer profiles for %d offers...", len(catalog_df))
    offer_profiles = [build_offer_profile(r)
                      for r in catalog_df.to_dict("records")]

    if model is None:
        model = _get_model()

    logger.info("Encoding %d company profiles...", len(company_profiles))
    company_embeddings = model.encode(
        company_profiles,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=64,
    )

    logger.info("Encoding %d offer profiles...", len(offer_profiles))
    offer_embeddings = model.encode(
        offer_profiles,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )

    logger.info("Computing similarity matrix (%d x %d)...",
                len(company_embeddings), len(offer_embeddings))
    similarity = company_embeddings @ offer_embeddings.T

    offer_ids   = catalog_df["offer_id"].tolist()
    company_ids = companies_df["identifiant_unique"].astype(str).tolist()
    n_offers    = len(offer_ids)
    effective_top_n = min(top_n, n_offers)

    logger.info("Selecting top-%d offers per company (min sim = %.2f)...",
                effective_top_n, CONTENT_MIN_SIMILARITY)

    rows = []
    stats_kept = 0
    stats_dropped = 0

    for i, comp_id in enumerate(company_ids):
        sims  = similarity[i]
        order = np.argsort(-sims, kind="stable")

        rank = 1
        for j in order:
            if rank > effective_top_n:
                break
            score = float(sims[j])
            if score < CONTENT_MIN_SIMILARITY:
                stats_dropped += 1
                continue
            rows.append({
                "identifiant_unique": comp_id,
                "offer_id":          offer_ids[j],
                "content_score":     round(score, 4),
                "rank":              rank,
                "why_matched":       _why_matched(company_profiles[i],
                                                  offer_profiles[j]),
            })
            rank += 1
            stats_kept += 1

    result = pd.DataFrame(rows)
    logger.info("Content scoring: kept %d pairs, dropped %d below threshold",
                stats_kept, stats_dropped)
    if len(result):
        logger.info("Score distribution: min=%.3f, mean=%.3f, max=%.3f",
                    result["content_score"].min(),
                    result["content_score"].mean(),
                    result["content_score"].max())
    return result
