"""
analysis/config_v2.py
=====================
Constants for the second wave of feature engineering.

Kept in a separate file from config.py so the original config (offer rules,
capital tiers, etc.) stays untouched. Everything here is tunable from one place:
mappings, keyword lists, and thresholds.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Feature: legal_form_type
# Maps the verbose RNE legal-form strings to a clean business-tier label.
# Real data shows values like "Société à Responsabilité Limitée (SARL)" — long
# French names — so the mapping is keyword-based on the lower-cased text.
# ─────────────────────────────────────────────────────────────────────────────

LEGAL_FORM_PATTERNS = [
    # (substring to look for in lower-cased fr_forme_juridique, business tier)
    ("suarl",                         "solo"),
    ("personne physique",             "solo"),
    ("entreprise individuelle",       "solo"),
    ("auto-entrepreneur",             "solo"),
    ("societe anonyme",               "corporate"),   # "Société Anonyme (SA)"
    ("sa)",                           "corporate"),   # safety net for "(SA)"
    ("sas",                           "corporate"),
    ("responsabilite limitee",        "sme"),         # "(SARL)"
    ("sarl",                          "sme"),
    ("en nom collectif",              "partnership"),
    ("commandite",                    "partnership"),
    ("civile",                        "partnership"), # SCI, SCP, etc.
    ("mutuelle",                      "other"),
    ("cooperative",                   "other"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Feature: company_size
# Cross of legal_form_type x capital_tier x sector, returning Solo/Small/Mid/Large.
# This is the "how big is this deal?" feature for the sales team.
#
# Rules are evaluated TOP TO BOTTOM. The first match wins. Each rule is a
# (predicate_function, label) pair.
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_SIZE_RULES = [
    # (predicate(row_dict) -> bool, size_label)

    # Solo: legal form is solo, OR micro capital with no other size signal
    (lambda r: r.get("legal_form_type") == "solo",                                          "Solo"),

    # Large: corporate legal form OR very large capital
    (lambda r: r.get("legal_form_type") == "corporate",                                     "Large"),
    (lambda r: r.get("capital_tier") == "large",                                            "Large"),

    # Mid: SME legal form WITH medium capital, or manufacturing with medium+ capital
    (lambda r: r.get("legal_form_type") == "sme" and r.get("capital_tier") == "medium",     "Mid"),
    (lambda r: r.get("category") == "manufacturing" and r.get("capital_tier") in ("medium", "large"), "Mid"),

    # Small: SME with small capital (most common case)
    (lambda r: r.get("legal_form_type") == "sme" and r.get("capital_tier") in ("small", "micro"),     "Small"),

    # Partnership-style firms (SCP, SCI) without other signal → Small
    (lambda r: r.get("legal_form_type") == "partnership",                                   "Small"),

    # ── Capital-only fallbacks (when legal_form_type is unknown/other) ──
    # Many RNE rows have empty fr_forme_juridique; capital still gives signal.
    (lambda r: r.get("capital_tier") == "medium",                                           "Mid"),
    (lambda r: r.get("capital_tier") == "small",                                            "Small"),
    (lambda r: r.get("capital_tier") == "micro",                                            "Solo"),
]
COMPANY_SIZE_DEFAULT = "Unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Feature: dynamism_score
# capital_per_year = capital / age_years
# Anything above HIGH_THRESHOLD is "high dynamism" (growing fast, hiring).
# ─────────────────────────────────────────────────────────────────────────────

DYNAMISM_HIGH_THRESHOLD_TND   = 50_000   # >= this capital_per_year = "high"
DYNAMISM_MEDIUM_THRESHOLD_TND = 10_000   # >= this = "medium", below = "low"


# ─────────────────────────────────────────────────────────────────────────────
# Feature: business_model (B2B / B2C / mixed / unknown)
# Keywords matched against activity text (lower-cased, accent-stripped).
# Verified against real data — these all have meaningful hit counts.
# ─────────────────────────────────────────────────────────────────────────────

B2B_KEYWORDS = [
    "gros", "commerce de gros",              # wholesale
    "industriel", "industrielle",
    "conseil", "consulting",                 # consulting
    "services aux entreprises",
    "sous-traitance", "sous traitance",
    "fourniture",
    "btob", "b to b", "b2b",
    "professionnel", "professionnels",
    "ingenierie",
    "bureau d'etudes", "bureau detudes",
    "entreprises",                           # "services aux entreprises" partial
]

B2C_KEYWORDS = [
    "detail", "commerce de detail",          # retail
    "vente au detail",
    "magasin", "boutique",
    "salon",
    "restaurant", "restauration",
    "cafe", "cafeteria",
    "boulangerie", "patisserie",
    "particulier", "particuliers",
    "alimentation generale",
    "coiffure", "esthetique",
    "supermarche", "epicerie",
]


# ─────────────────────────────────────────────────────────────────────────────
# Feature: international_signal
# Search across activity + denomination + commercial name.
# ─────────────────────────────────────────────────────────────────────────────

INTERNATIONAL_KEYWORDS = [
    "international",
    "import", "export",
    "trading",
    "offshore",
    "commerce exterieur",
    "global", "worldwide",
    "multinational",
    "overseas",
    "tunisie ", " tunisie",          # "X Tunisie" often = foreign brand subsidiary
]


# ─────────────────────────────────────────────────────────────────────────────
# Feature: connectivity_need
# Sector × company_size → connectivity demand level.
# This is what tells the salesperson "open the fiber page vs the mobile page".
# ─────────────────────────────────────────────────────────────────────────────

# Sectors with inherently high connectivity needs (always at least "medium")
HIGH_CONNECTIVITY_SECTORS = {
    "financial_services",   # banks, insurance — high uptime + secure
    "healthcare",           # clinics, telemedicine
}

# Sectors with inherently low connectivity needs
LOW_CONNECTIVITY_SECTORS = {
    "agriculture",
}

# Activity keywords that ALWAYS push connectivity to "high" regardless of size
HIGH_CONNECTIVITY_ACTIVITY_KEYWORDS = [
    "telecommunications", "telecom",
    "informatique",
    "logiciel", "software",
    "cloud", "hebergement", "data center", "datacenter",
    "centre d'appel", "centre dappel", "call center",
    "cybersecurite",
    "internet",
]


# ─────────────────────────────────────────────────────────────────────────────
# Feature: fleet_size (refines mobility_signal into deal value buckets)
# ─────────────────────────────────────────────────────────────────────────────

# Activity keywords suggesting larger fleets
LARGE_FLEET_KEYWORDS = [
    "transport routier de marchandises",
    "transport de marchandises",
    "logistique",
    "messagerie",
    "fret",
    "demenagement",
]
SMALL_FLEET_KEYWORDS = [
    "taxi",
    "vtc",
    "ambulance",
    "livraison",
    "coursier",
]


# ─────────────────────────────────────────────────────────────────────────────
# Feature: governorate
# Tunisia has 24 governorates. We map known cities (from analysis.config.KNOWN_CITIES)
# to their governorate. This is built from city → governorate, NOT postal codes,
# because real data only has postal codes in ~10% of rows.
#
# Source: Tunisian government administrative divisions.
# ─────────────────────────────────────────────────────────────────────────────

CITY_TO_GOVERNORATE = {
    # Tunis governorate
    "Tunis": "Tunis", "El Kram": "Tunis", "Carthage": "Tunis",
    "Hammam Lif": "Ben Arous", "La Marsa": "Tunis",
    "Sidi Hassine": "Tunis", "Ezzouhour": "Tunis", "El Kabbaria": "Tunis",

    # Ariana governorate
    "Ariana": "Ariana", "Manouba": "Manouba",

    # Ben Arous governorate
    "Ben Arous": "Ben Arous",

    # Nabeul governorate (Cap Bon)
    "Nabeul": "Nabeul", "Hammamet": "Nabeul",
    "Korba": "Nabeul", "Kelibia": "Nabeul",

    # Sousse
    "Sousse": "Sousse", "Hammam Sousse": "Sousse", "Hammam-Sousse": "Sousse",
    "Akouda": "Sousse", "Hergla": "Sousse",
    "Msaken": "Sousse", "M'saken": "Sousse",
    "Enfidha": "Sousse",
    "Kalaa El Kebira": "Sousse", "Kalaa Essghira": "Sousse",
    "Bou Ficha": "Sousse", "Sidi Bou Ali": "Sousse",
    "Kondar": "Sousse",

    # Monastir
    "Monastir": "Monastir",
    "Ouerdanine": "Monastir", "Sahline": "Monastir",
    "Bou Merdes": "Monastir", "Zeramdine": "Monastir",

    # Mahdia
    "Mahdia": "Mahdia", "El Jem": "Mahdia",

    # Sfax
    "Sfax": "Sfax",
    "Sakiet Eddaier": "Sfax", "Sakiet Ezzit": "Sfax",
    "El Hencha": "Sfax", "Bir Ali Ben Khelifa": "Sfax",
    "Mahras": "Sfax", "Esskhira": "Sfax",
    "Jebeniana": "Sfax", "Agareb": "Sfax",

    # Kairouan
    "Kairouan": "Kairouan",

    # Kasserine, Sidi Bouzid, Gafsa, Tozeur, Kebili, Tataouine, Medenine
    "Kasserine": "Kasserine",
    "Gafsa": "Gafsa", "Tozeur": "Tozeur",
    "Kebili": "Kebili",
    "Medenine": "Medenine", "Tataouine": "Tataouine",

    # North
    "Bizerte": "Bizerte",
    "Beja": "Beja", "Jendouba": "Jendouba",
    "Kef": "Kef", "Siliana": "Siliana", "Zaghouan": "Zaghouan",

    # South coast
    "Gabes": "Gabes",
}


# ─────────────────────────────────────────────────────────────────────────────
# Feature: is_new_company
# A company is "new" if registered within the last N months.
# Based on real data (388 of 958 = 40% in 2025), 12 months is the natural window.
# ─────────────────────────────────────────────────────────────────────────────

NEW_COMPANY_WINDOW_MONTHS = 12
