"""
analysis/config.py
==================
All thresholds, keyword lists, and offer mappings used by the analysis layer.

Tune everything from here without touching the logic modules.
"""

from pathlib import Path

# Inherit the project base directory from segmentation config so paths stay consistent
from segmentation.config import BASE_DIR


# ─────────────────────────────────────────────────────────────────────────────
# Input / output paths
# ─────────────────────────────────────────────────────────────────────────────

ANALYSIS_INPUT_CSV    = BASE_DIR / "data" / "output" / "rne_companies_segmented.csv"
PROSPECTS_CSV         = BASE_DIR / "data" / "output" / "commercial_prospects.csv"
COHORT_SUMMARY_CSV    = BASE_DIR / "data" / "output" / "cohort_summary.csv"
SECTOR_KPIS_CSV       = BASE_DIR / "data" / "output" / "sector_kpis.csv"
VAGUE_ACTIVITIES_CSV  = BASE_DIR / "data" / "output" / "vague_activities_report.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Capital tiers (in TND)
# ─────────────────────────────────────────────────────────────────────────────

CAPITAL_TIERS = [
    # (max_value_exclusive, label)
    (5_000,   "micro"),
    (20_000,  "small"),
    (100_000, "medium"),
    (float("inf"), "large"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Maturity buckets (in years since immatriculation)
# ─────────────────────────────────────────────────────────────────────────────

MATURITY_BUCKETS = [
    # (max_age_exclusive_in_years, label)
    (1,  "startup"),
    (3,  "growing"),
    (10, "established"),
    (float("inf"), "mature"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Digital signal keywords
# Matched (case-insensitive, accent-insensitive) against the activity text.
# ─────────────────────────────────────────────────────────────────────────────

DIGITAL_HIGH_KEYWORDS = [
    "logiciel", "software", "saas", "developpement informatique",
    "developpement de logiciels", "realisation de logiciels",
    "edition de logiciels", "programmation",
    "cloud", "data center", "datacenter", "hebergement",
    "telecommunications", "telecom",
    "informatique", "activites informatiques",
    "cybersecurite", "cyber securite",
]

DIGITAL_MEDIUM_KEYWORDS = [
    "technologie", "tech", "systeme",
    "numerique", "digital",
    "conception de site web", "site internet", "site web",
    "marketing digital", "e-commerce", "ecommerce",
    "intelligence artificielle", "ia",
]


# ─────────────────────────────────────────────────────────────────────────────
# Mobility signal keywords
# ─────────────────────────────────────────────────────────────────────────────

MOBILITY_KEYWORDS = [
    "transport", "transports", "routier", "routes",
    "marchandises", "fret",
    "livraison", "livreur", "logistique",
    "taxi", "vtc",
    "messagerie", "coursier",
    "demenagement",
    "flotte", "ambulance",
]


# ─────────────────────────────────────────────────────────────────────────────
# Multi-site signal keywords (used in combination with capital threshold)
# ─────────────────────────────────────────────────────────────────────────────

MULTISITE_KEYWORDS = [
    "agence", "agences",
    "commerce de gros", "gros",
    "distribution", "distributeur",
    "reseau", "franchise",
    "succursale", "filiale",
    "chaine", "groupe",
]

MULTISITE_CAPITAL_FLOOR = 100_000  # capital >= this also triggers multisite signal


# ─────────────────────────────────────────────────────────────────────────────
# Geography — Tunisian cities to detect inside fr_adresse
# Order matters: more specific names first so "Sousse Ville" matches before "Sousse"
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_CITIES = [
    "Tunis", "Sfax", "Sousse", "Kairouan",
    "Bizerte", "Gabes", "Ariana", "Gafsa",
    "Monastir", "Ben Arous", "Kasserine", "Medenine",
    "Nabeul", "Tataouine", "Beja", "Jendouba",
    "Mahdia", "Siliana", "Kef", "Tozeur",
    "Manouba", "Zaghouan", "Kebili",
    "Hammam Sousse", "Hammam-Sousse",
    "Hergla", "Akouda", "Enfidha", "Msaken", "M'saken",
    "Hammam Lif", "La Marsa", "Carthage", "El Kram",
    "Korba", "Kelibia", "Hammamet",
    # Added after inspecting real RNE data — common satellite towns
    "Kalaa El Kebira", "Kalaa Essghira",
    "Sakiet Eddaier", "Sakiet Ezzit",
    "Bou Ficha", "El Jem", "El Hencha",
    "Bir Ali Ben Khelifa", "Mahras", "Esskhira",
    "Jebeniana", "Agareb", "Sidi Bou Ali",
    "Ouerdanine", "Sahline", "Bou Merdes",
    "Zeramdine", "Kondar",
    "Sidi Hassine", "Ezzouhour", "El Kabbaria",
]


# ─────────────────────────────────────────────────────────────────────────────
# Offer recommendation cascade
# Rules are evaluated TOP TO BOTTOM. The first matching rule wins.
#
# Each rule is a dict with:
#   - "condition" : a callable taking a row dict, returning True/False
#   - "offer"     : the recommended_offer label
#   - "reason"    : short human-readable trace for the audit column
#
# To add a new offer, insert a new rule at the appropriate priority level.
# ─────────────────────────────────────────────────────────────────────────────

OFFER_RULES = [
    # ─── High-signal combinations ───────────────────────────────────────────
    {
        "name":      "fleet_pro",
        "condition": lambda r: r["mobility_signal"] and r["category"] == "transport",
        "offer":     "Fleet Pro — GPS + mobiles illimites",
        "reason":    "transport + mobility signal",
    },
    {
        "name":      "fibre_cloud",
        "condition": lambda r: r["digital_signal"] == "high" and r["multisite_signal"],
        "offer":     "Business Fibre + Cloud Connect",
        "reason":    "digital_high + multisite",
    },
    {
        "name":      "fibre_fixe",
        "condition": lambda r: r["digital_signal"] == "high",
        "offer":     "Business Fibre + Fixe Pro",
        "reason":    "digital_high",
    },

    # ─── Size-driven enterprise offer ───────────────────────────────────────
    {
        "name":      "enterprise",
        "condition": lambda r: r["capital_tier"] == "large",
        "offer":     "Enterprise — devis personnalise",
        "reason":    "capital > 100k TND",
    },

    # ─── Startups (regardless of sector) ────────────────────────────────────
    {
        "name":      "starter_pack",
        "condition": lambda r: r["maturity"] == "startup",
        "offer":     "Starter Pack — engagement 6 mois",
        "reason":    "startup < 1 year",
    },

    # ─── Sector-default offers ──────────────────────────────────────────────
    {
        "name":      "retail_default",
        "condition": lambda r: r["category"] == "retail",
        "offer":     "Business Connect + TPE Mobile",
        "reason":    "sector default: retail",
    },
    {
        "name":      "manufacturing_default",
        "condition": lambda r: r["category"] == "manufacturing",
        "offer":     "IoT Connect + Lignes Fixes",
        "reason":    "sector default: manufacturing",
    },
    {
        "name":      "transport_default",
        "condition": lambda r: r["category"] == "transport",
        "offer":     "Fleet Starter + GPS",
        "reason":    "sector default: transport",
    },
    {
        "name":      "tourism_default",
        "condition": lambda r: r["category"] == "tourism",
        "offer":     "Hospitality WiFi + Lignes Fixes",
        "reason":    "sector default: tourism",
    },
    {
        "name":      "healthcare_default",
        "condition": lambda r: r["category"] == "healthcare",
        "offer":     "Clinic Connect + PABX Cloud",
        "reason":    "sector default: healthcare",
    },
    {
        "name":      "education_default",
        "condition": lambda r: r["category"] == "education",
        "offer":     "Campus Connect + Internet HD",
        "reason":    "sector default: education",
    },
    {
        "name":      "financial_default",
        "condition": lambda r: r["category"] == "financial_services",
        "offer":     "Secure Business + VPN",
        "reason":    "sector default: financial_services",
    },

    # ─── Last resort ────────────────────────────────────────────────────────
    {
        "name":      "to_qualify",
        "condition": lambda r: True,
        "offer":     "Starter — a qualifier en appel",
        "reason":    "no clear signal — needs phone qualification",
    },
]


