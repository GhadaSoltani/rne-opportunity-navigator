"""
recommendation/rules_config.py
==============================
The declarative rule table for Layer 1 (business logic).

Each rule is a dict with:
    - name           : short unique ID for the rule (used in logs and explanations)
    - when           : a callable(company_row) -> bool (the trigger condition)
    - target_family  : optional str — apply score to every offer in this family
    - target_offer   : optional str — apply score to this specific offer_id
                       (if both are set, both must match)
    - score          : the rule's confidence in [0, 1]
    - reason_fr      : short French sentence for the explanation

Design principles:
    - No substring matching. Family or exact offer_id only — no false positives.
    - Multiple rules can target the same offer; they COMBINE via soft-max,
      not "best wins". Three medium rules > one weak rule.
    - Every category has at least one rule. No blind spots.
    - Rules are editable from THIS FILE only. Logic modules stay untouched.

Adding a new rule:
    RULES.append({
        "name":          "my_new_rule",
        "when":          lambda r: r.get("category") == "agriculture",
        "target_family": "iot",
        "score":         0.70,
        "reason_fr":     "IoT pour l'agriculture connectee",
    })
"""

# ─────────────────────────────────────────────────────────────────────────────
# Small helpers so rules read cleanly
# ─────────────────────────────────────────────────────────────────────────────

def _truthy(v):
    """Accept True, 'True', 'true', 1 as True — dataframe values are messy."""
    return v in (True, "True", "true", 1, "1")

def _cat(r, *values):
    """Row category matches any of the given labels."""
    return str(r.get("category", "")).strip() in values

def _digital(r, *values):
    return str(r.get("digital_signal", "")).strip() in values

def _size(r, *values):
    return str(r.get("company_size", "")).strip() in values

def _capital(r, *values):
    return str(r.get("capital_tier", "")).strip() in values

def _maturity(r, *values):
    return str(r.get("maturity", "")).strip() in values

def _mobility(r):     return _truthy(r.get("mobility_signal"))
def _multisite(r):    return _truthy(r.get("multisite_signal"))
def _international(r):return _truthy(r.get("international_signal"))
def _new_company(r):  return _truthy(r.get("is_new_company"))


# ─────────────────────────────────────────────────────────────────────────────
# The rule table
# Grouped by intent so it's easy to read and audit.
# ─────────────────────────────────────────────────────────────────────────────

RULES = [
    # ═══════════════════════════════════════════════════════════════════════
    # TRANSPORT — mobility & fleet
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "transport_fleet_iot",
        "when":          lambda r: _cat(r, "transport") and _mobility(r),
        "target_offer":  "iot_m2m",
        "score":         0.90,
        "reason_fr":     "Transport avec signal mobilite — IoT pour gestion de flotte",
    },
    {
        "name":          "transport_fleet_sim_data",
        "when":          lambda r: _cat(r, "transport") and _mobility(r),
        "target_offer":  "mobile_data_sim_gprs",
        "score":         0.85,
        "reason_fr":     "Transport avec mobilite — SIM Data pour vehicules connectes",
    },
    {
        "name":          "transport_fleet_dongle",
        "when":          lambda r: _cat(r, "transport") and _mobility(r),
        "target_offer":  "mobile_data_postpaid_dongle",
        "score":         0.70,
        "reason_fr":     "Transport avec mobilite — Cle 4G pour connexion mobile",
    },
    {
        "name":          "transport_multisite_sdwan",
        "when":          lambda r: _cat(r, "transport") and _multisite(r),
        "target_offer":  "security_secure_sdwan",
        "score":         0.75,
        "reason_fr":     "Transport multi-sites — SD-WAN pour interconnecter les agences",
    },
    {
        "name":          "transport_baseline_mobile",
        # Transport without mobility_signal — still gets a mobile baseline
        "when":          lambda r: _cat(r, "transport") and not _mobility(r),
        "target_family": "mobile",
        "score":         0.40,
        "reason_fr":     "Transport — offre mobile professionnelle",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # RETAIL — commerce & distribution
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "retail_progress_mobile",
        "when":          lambda r: _cat(r, "retail"),
        "target_offer":  "mobile_forfait_business_progress",
        "score":         0.70,
        "reason_fr":     "Commerce — forfait Business Progress pour equipes de vente",
    },

    {
        "name":          "retail_large_fibre",
        "when":          lambda r: _cat(r, "retail") and _capital(r, "large"),
        "target_family": "fixed",
        "score":         0.65,
        "reason_fr":     "Enseigne importante — connectivite fixe pour les magasins",
    },
    {
        "name":          "retail_sms_printer",
        "when":          lambda r: _cat(r, "retail"),
        "target_offer":  "mobile_sms_printer",
        "score":         0.45,
        "reason_fr":     "Commerce — SMS Printer pour communication client",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # MANUFACTURING — industrial
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "manufacturing_iot",
        "when":          lambda r: _cat(r, "manufacturing"),
        "target_offer":  "iot_m2m",
        "score":         0.75,
        "reason_fr":     "Industrie — IoT/M2M pour surveillance des equipements",
    },
    {
        "name":          "manufacturing_fibre",
        "when":          lambda r: _cat(r, "manufacturing") and _capital(r, "medium", "large"),
        "target_offer":  "fixed_fibre_pro",
        "score":         0.72,
        "reason_fr":     "Industrie capitalisee — Fibre Pro pour l'usine",
    },
    {
        "name":          "manufacturing_voip",
        "when":          lambda r: _cat(r, "manufacturing"),
        "target_offer":  "fixed_voix_business",
        "score":         0.60,
        "reason_fr":     "Industrie — telephonie fixe VoIP pour l'administratif",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # TOURISM — hotels, travel agencies
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "tourism_secure_wifi",
        "when":          lambda r: _cat(r, "tourism"),
        "target_offer":  "security_secure_wifi",
        "score":         0.85,
        "reason_fr":     "Tourisme — WiFi securise pour clients / hebergement",
    },

    {
        "name":          "tourism_fibre",
        "when":          lambda r: _cat(r, "tourism"),
        "target_family": "fixed",
        "score":         0.60,
        "reason_fr":     "Tourisme — connectivite fixe haut debit pour l'etablissement",
    },
    {
        "name":          "tourism_roaming",
        "when":          lambda r: _cat(r, "tourism") and _international(r),
        "target_offer":  "mobile_roaming_international",
        "score":         0.70,
        "reason_fr":     "Tourisme international — forfait roaming",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # HEALTHCARE — clinics, medical
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "healthcare_secure_internet",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "security_secure_internet",
        "score":         0.80,
        "reason_fr":     "Sante — acces internet securise pour donnees patients",
    },
    {
        "name":          "healthcare_ms365",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "collab_ms365",
        "score":         0.70,
        "reason_fr":     "Sante — MS365 pour dossier patient et collaboration equipe",
    },
    {
        "name":          "healthcare_fibre",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_family": "fixed",
        "score":         0.60,
        "reason_fr":     "Sante — connectivite fixe fiable pour la clinique",
    },
    {
        "name":          "healthcare_edr",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "security_edr",
        "score":         0.65,
        "reason_fr":     "Sante — EDR pour proteger les postes soignants",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # EDUCATION — schools, universities, training
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "education_ms365",
        "when":          lambda r: _cat(r, "education"),
        "target_offer":  "collab_ms365",
        "score":         0.85,
        "reason_fr":     "Education — MS365 pour enseignants et etudiants",
    },
    {
        "name":          "education_secure_wifi",
        "when":          lambda r: _cat(r, "education"),
        "target_offer":  "security_secure_wifi",
        "score":         0.75,
        "reason_fr":     "Education — WiFi securise pour le campus",
    },
    {
        "name":          "education_secure_internet",
        "when":          lambda r: _cat(r, "education"),
        "target_offer":  "security_secure_internet",
        "score":         0.70,
        "reason_fr":     "Education — acces internet securise pour eleves",
    },
    {
        "name":          "education_fibre",
        "when":          lambda r: _cat(r, "education"),
        "target_family": "fixed",
        "score":         0.65,
        "reason_fr":     "Education — connectivite fixe pour salles / laboratoires",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # FINANCIAL SERVICES — banks, insurance, accounting
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "finance_anti_ddos",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "security_anti_ddos",
        "score":         0.85,
        "reason_fr":     "Finance — Anti-DDoS pour la disponibilite des services",
    },
    {
        "name":          "finance_waf",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "security_waf",
        "score":         0.80,
        "reason_fr":     "Finance — WAF pour proteger les applications web",
    },
    {
        "name":          "finance_secure_internet",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "security_secure_internet",
        "score":         0.75,
        "reason_fr":     "Finance — acces internet securise obligatoire",
    },
    {
        "name":          "finance_thd_fibre",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "fixed_thd_fibre",
        "score":         0.75,
        "reason_fr":     "Finance — Fibre THD pour temps de reponse critique",
    },
    {
        "name":          "finance_multisite_sdwan",
        "when":          lambda r: _cat(r, "financial_services") and _multisite(r),
        "target_offer":  "security_secure_sdwan",
        "score":         0.85,
        "reason_fr":     "Banque / assurance multi-agences — SD-WAN securise",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # DIGITAL SIGNAL — IT / tech companies (works across categories)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "digital_high_fibre",
        "when":          lambda r: _digital(r, "high"),
        "target_offer":  "fixed_thd_fibre",
        "score":         0.85,
        "reason_fr":     "Forte activite numerique — Fibre THD",
    },
    {
        "name":          "digital_high_fibre_pro",
        "when":          lambda r: _digital(r, "high"),
        "target_offer":  "fixed_fibre_pro",
        "score":         0.75,
        "reason_fr":     "Forte activite numerique — Fibre Pro",
    },
    {
        "name":          "digital_high_cloud",
        "when":          lambda r: _digital(r, "high"),
        "target_family": "cloud",
        "score":         0.80,
        "reason_fr":     "Forte activite numerique — services Cloud",
    },
    {
        "name":          "digital_high_security",
        "when":          lambda r: _digital(r, "high"),
        "target_family": "security",
        "score":         0.60,
        "reason_fr":     "Forte activite numerique — offres securite",
    },
    {
        "name":          "digital_medium_cloud",
        "when":          lambda r: _digital(r, "medium"),
        "target_family": "cloud",
        "score":         0.55,
        "reason_fr":     "Activite technologique — services Cloud",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SIZE / CAPITAL signals — refine offers within a size tier
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "large_priv_pro",
        # Large companies lean toward the Pro tier, not Plus
        "when":          lambda r: _capital(r, "large") or _size(r, "Large"),
        "target_offer":  "mobile_forfait_business_priv_pro",
        "score":         0.70,
        "reason_fr":     "Grande entreprise — forfait Business Priv Pro",
    },
    {
        "name":          "mid_priv_plus",
        # Mid companies lean toward Plus, not Pro
        "when":          lambda r: _size(r, "Mid") or _capital(r, "medium"),
        "target_offer":  "mobile_forfait_business_priv_plus",
        "score":         0.65,
        "reason_fr":     "Entreprise moyenne — forfait Business Priv Plus",
    },
    {
        "name":          "small_progress",
        "when":          lambda r: _size(r, "Small") or _capital(r, "small"),
        "target_offer":  "mobile_forfait_business_progress",
        "score":         0.65,
        "reason_fr":     "Petite entreprise — forfait Business Progress",
    },
    {
        "name":          "solo_classic",
        "when":          lambda r: _size(r, "Solo") or _capital(r, "micro"),
        "target_offer":  "mobile_forfait_business_classic",
        "score":         0.60,
        "reason_fr":     "Auto-entrepreneur — forfait Business Classic",
    },
    {
        "name":          "solo_4g_box",
        "when":          lambda r: _size(r, "Solo"),
        "target_offer":  "mobile_4g_box_pro",
        "score":         0.55,
        "reason_fr":     "Auto-entrepreneur — 4G Box comme internet principal",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # MULTI-SITE — chain / franchise / branches
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "multisite_sdwan_general",
        "when":          lambda r: _multisite(r),
        "target_offer":  "security_secure_sdwan",
        "score":         0.70,
        "reason_fr":     "Multi-sites — SD-WAN pour interconnexion optimisee",
    },
    {
        "name":          "multisite_centrex",
        "when":          lambda r: _multisite(r),
        "target_offer":  "collab_business_centrex",
        "score":         0.60,
        "reason_fr":     "Multi-sites — Business Centrex telephonie unifiee",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # MATURITY — startup / new company
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "startup_progress",
        "when":          lambda r: _maturity(r, "startup"),
        "target_offer":  "mobile_forfait_business_progress",
        "score":         0.65,
        "reason_fr":     "Startup — engagement leger avec Business Progress",
    },
    {
        "name":          "startup_4g_box",
        "when":          lambda r: _maturity(r, "startup"),
        "target_offer":  "mobile_4g_box_pro",
        "score":         0.55,
        "reason_fr":     "Startup — 4G Box comme internet flexible",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # INTERNATIONAL activity
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "international_roaming",
        "when":          lambda r: _international(r),
        "target_offer":  "mobile_roaming_international",
        "score":         0.85,
        "reason_fr":     "Activite internationale — forfait Roaming",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # BASELINE — every company gets at least ONE mobile baseline
    # so no company is left with an empty rule score
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "baseline_business_progress",
        "when":          lambda r: True,  # always fires
        "target_offer":  "mobile_forfait_business_progress",
        "score":         0.30,
        "reason_fr":     "Ligne mobile professionnelle standard",
    },
  

    # ═══════════════════════════════════════════════════════════════════════
    # IoT / M2M — Ooredoo IoT deck: "Education, Gouvernement, Finance,
    # Fabrication, Transport, Médical, Pétrole et Gaz, Hospitalité, Vente
    # au détail." References: OneTech, GIAS, Vitalait, Med.tn, CNSS, Talan.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "iot_healthcare",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "iot_m2m",
        "score":         0.75,
        "reason_fr":     "Sante — IoT pour equipements medicaux connectes (ref: Med.tn)",
    },
    {
        "name":          "iot_finance_insurance",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "iot_m2m",
        "score":         0.65,
        "reason_fr":     "Finance/assurance — IoT pour telematique et risque (ref: Talan, At-Takafulia)",
    },
    {
        "name":          "iot_education",
        "when":          lambda r: _cat(r, "education"),
        "target_offer":  "iot_m2m",
        "score":         0.55,
        "reason_fr":     "Education — IoT pour gestion campus et laboratoires",
    },
    {
        "name":          "iot_retail_multisite",
        "when":          lambda r: _cat(r, "retail") and _multisite(r),
        "target_offer":  "iot_m2m",
        "score":         0.65,
        "reason_fr":     "Retail multi-sites — IoT pour tracking marchandises et TPE",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # Business Centrex — deck: convergence FMC, receptionniste, "nouveau
    # business sans PBX physique". Prix Premium 10 / Platinum 15 TND.
    # Strong for tourism (hotels/reception), retail (customer service),
    # healthcare (clinic phones), finance (agencies), education (admin).
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "centrex_startup_no_pbx",
        # Startups don't have an existing PBX — Centrex is the natural choice
        "when":          lambda r: _maturity(r, "startup"),
        "target_offer":  "collab_business_centrex",
        "score":         0.65,
        "reason_fr":     "Nouvelle entreprise sans PBX — Centrex hors investissement materiel",
    },
    {
        "name":          "centrex_tourism_reception",
        "when":          lambda r: _cat(r, "tourism"),
        "target_offer":  "collab_business_centrex",
        "score":         0.80,
        "reason_fr":     "Tourisme/hotellerie — Centrex pour la reception et convergence fixe-mobile",
    },
    {
        "name":          "centrex_healthcare_clinic",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "collab_business_centrex",
        "score":         0.70,
        "reason_fr":     "Sante — Centrex pour standard clinique et prise de RDV",
    },
    {
        "name":          "centrex_finance_agencies",
        "when":          lambda r: _cat(r, "financial_services") and _multisite(r),
        "target_offer":  "collab_business_centrex",
        "score":         0.75,
        "reason_fr":     "Banque/assurance multi-agences — Centrex telephonie unifiee",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # Endpoint Protection Platform (EPP) — Bitdefender first-line defense
    # for SMEs. Deck insight: "PME sans equipe securite dediee".
    # Broad applicability across sectors that handle client data / stock.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "epp_sme_baseline",
        # Any small/mid company gets EPP as endpoint baseline
        "when":          lambda r: _size(r, "Small", "Mid"),
        "target_offer":  "security_epp",
        "score":         0.55,
        "reason_fr":     "PME — protection endpoint Bitdefender EPP geree par Ooredoo SOC",
    },
    {
        "name":          "epp_manufacturing",
        "when":          lambda r: _cat(r, "manufacturing"),
        "target_offer":  "security_epp",
        "score":         0.70,
        "reason_fr":     "Industrie — EPP pour postes atelier et administration (ref: OneTech, GIAS)",
    },
    {
        "name":          "epp_retail",
        "when":          lambda r: _cat(r, "retail"),
        "target_offer":  "security_epp",
        "score":         0.65,
        "reason_fr":     "Commerce — EPP pour caisses, TPE et postes administratifs",
    },
    {
        "name":          "epp_education",
        "when":          lambda r: _cat(r, "education"),
        "target_offer":  "security_epp",
        "score":         0.65,
        "reason_fr":     "Education — EPP pour salles informatiques et admin",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # Endpoint Detection & Response (EDR) — Bitdefender advanced tier for
    # regulated / high-value sectors. Deck: "grandes entreprises, banques,
    # assurances, hopitaux, cibles prioritaires de ransomware".
    # Note: existing healthcare_edr rule (score 0.65) stays — this ADDS
    # finance and large-manufacturing coverage.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "edr_finance_regulated",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "security_edr",
        "score":         0.85,
        "reason_fr":     "Finance secteur regule — EDR Bitdefender avec threat hunting SOC 24/7",
    },
    {
        "name":          "edr_manufacturing_large",
        "when":          lambda r: _cat(r, "manufacturing") and _capital(r, "large"),
        "target_offer":  "security_edr",
        "score":         0.75,
        "reason_fr":     "Grande industrie — EDR pour proteger production contre ransomware",
    },
    {
        "name":          "edr_high_digital",
        # Tech-heavy companies are ransomware targets
        "when":          lambda r: _digital(r, "high") and _capital(r, "medium", "large"),
        "target_offer":  "security_edr",
        "score":         0.70,
        "reason_fr":     "Entreprise numerique — EDR pour detection avancee et forensic MITRE",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # Safe Email — deck: "email reste le premier vecteur de compromission
    # notamment ransomware". Broad applicability, higher priority for
    # sectors handling sensitive data / transactions.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "safe_email_finance",
        "when":          lambda r: _cat(r, "financial_services"),
        "target_offer":  "security_safe_email",
        "score":         0.75,
        "reason_fr":     "Finance — Safe Email contre phishing et fraude par email",
    },
    {
        "name":          "safe_email_healthcare",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "security_safe_email",
        "score":         0.65,
        "reason_fr":     "Sante — Safe Email pour proteger correspondance et donnees patients",
    },
    {
        "name":          "safe_email_baseline",
        # Every mid-to-large company should have email security
        "when":          lambda r: _size(r, "Mid", "Large") or _capital(r, "medium", "large"),
        "target_offer":  "security_safe_email",
        "score":         0.45,
        "reason_fr":     "Protection email — anti-phishing anti-malware essentiel",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # Secure WiFi — deck references: Mall of Sfax, Movenpick, Aviation
    # Civile, Atrium Yasmine. Retail and tourism are the strongest anchors.
    # (existing tourism_secure_wifi and education_secure_wifi rules stay)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "wifi_retail_captive_portal",
        # Retail deck angle: captive portals for marketing campaigns
        "when":          lambda r: _cat(r, "retail"),
        "target_offer":  "security_secure_wifi",
        "score":         0.75,
        "reason_fr":     "Commerce — WiFi securise avec portail captif pour marketing client (ref: Mall of Sfax)",
    },
    {
        "name":          "wifi_healthcare_public_areas",
        "when":          lambda r: _cat(r, "healthcare"),
        "target_offer":  "security_secure_wifi",
        "score":         0.65,
        "reason_fr":     "Sante — WiFi securise pour salles d'attente et patients",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # SD-WAN reinforcement — deck emphasizes "chaines de magasins, agences
    # bancaires, franchises". (existing multi-site rules stay — these ADD
    # specificity where the deck evidence is strongest.)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "name":          "sdwan_retail_chain",
        "when":          lambda r: _cat(r, "retail") and _multisite(r),
        "target_offer":  "security_secure_sdwan",
        "score":         0.85,
        "reason_fr":     "Chaine de magasins — SD-WAN Fortinet pour interconnecter les points de vente",
    },
    {
        "name":          "sdwan_finance_branches",
        "when":          lambda r: _cat(r, "financial_services") and _multisite(r),
        "target_offer":  "security_secure_sdwan",
        "score":         0.90,
        "reason_fr":     "Banque/assurance multi-agences — SD-WAN Fortinet securise et manage",
    },
    {
        "name":          "sdwan_manufacturing_multi_plant",
        "when":          lambda r: _cat(r, "manufacturing") and _multisite(r),
        "target_offer":  "security_secure_sdwan",
        "score":         0.80,
        "reason_fr":     "Groupe industriel multi-usines — SD-WAN pour interconnexion sites de production",
    },


]
