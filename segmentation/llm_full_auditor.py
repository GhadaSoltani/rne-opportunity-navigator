import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

from segmentation.config import (
    OUTPUT_CSV,
    OLLAMA_URL,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)


ALLOWED_CATEGORIES = [
    "retail",
    "manufacturing",
    "transport",
    "tourism",
    "healthcare",
    "education",
    "financial_services",
    "others",
]

LLM_AUDIT_OUTPUT = Path("data/output/rne_companies_segmented_llm_audit.csv")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_blind_prompt(activity_text: str) -> str:
    """
    Pass 1 — blind classification.
    The LLM does NOT see the system category to avoid anchoring bias.
    """

    return f"""
You are a B2B company classification expert working for Ooredoo Business (Tunisia).

Your task:
Classify the company activity below into exactly ONE of these 8 categories:

retail | manufacturing | transport | tourism | healthcare | education | financial_services | others

─────────────────────────────────────────────
CATEGORY DEFINITIONS AND BUSINESS RULES
─────────────────────────────────────────────

1. retail
Businesses that SELL or DISTRIBUTE goods or services to individuals or other businesses.
This is the broadest commercial category.

Includes:
commerce, vente, distribution, import/export, wholesale, boutiques, supermarkets,
cafés, restaurants, beauty salons, pharmacies that primarily sell, and distributors
of ANY product type: medical, food, electronics, construction, clothes, equipment.

Key rule:
If the core activity is selling, trading, commerce, import/export, or distribution,
classify as retail, regardless of what the product is.

Examples:
- commerce de matériel médical → retail
- vente de dispositifs médicaux → retail
- importation et distribution alimentaire → retail
- restaurant / café → retail unless part of hotel
- salon de beauté → retail
- commerce de matériaux de construction → retail

2. healthcare
Businesses that DELIVER medical care or health services directly to patients.

Includes:
clinics, hospitals, medical laboratories, dental offices, ambulance services,
medical analysis centers, healthcare centers.

Key rule:
Selling medical products does NOT make a company healthcare.
Only classify as healthcare if the core service is caring for patients.

Examples:
- clinique médicale → healthcare
- laboratoire d'analyses médicales → healthcare
- cabinet dentaire → healthcare
- vente de matériel médical → retail, NOT healthcare

3. manufacturing
Businesses that PRODUCE, FABRICATE, TRANSFORM, ASSEMBLE, or PROCESS physical goods.

Includes:
factories, workshops, industrial production, food processing, textile production,
printing, furniture manufacturing, metal production.

Key rule:
If they make or transform something, classify as manufacturing.

4. transport
Moving goods or people, and related logistics services.

Includes:
freight, delivery, logistics, warehousing, taxi, bus, transit, shipping,
courier services, transport support.

5. tourism
Accommodation and travel-related services.

Includes:
hotels, tourist residences, travel agencies, camping, tour operators.

Key rule:
Cafés and restaurants are retail unless clearly part of a hotel or tourism accommodation service.

6. education
Teaching and learning services.

Includes:
schools, universities, training centers, kindergartens, tutoring,
professional certification, e-learning platforms.

7. financial_services
Financial and advisory services.

Includes:
banks, insurance companies, leasing, credit, accounting firms, audit,
financial consulting, investment, payment services.

8. others
Use ONLY when the activity clearly does not fit any category above.

Includes:
associations, NGOs, religious organizations, public administration,
diplomatic missions, or genuinely unclassifiable descriptions.

Key rule:
When in doubt between "others" and a real category, prefer the real category.

─────────────────────────────────────────────
LANGUAGE NOTE
─────────────────────────────────────────────
The activity may be written in French, Arabic, English, or mixed language.
Classify based on meaning.

─────────────────────────────────────────────
CONFIDENCE SCALE
─────────────────────────────────────────────
0.90 – 1.00 : very certain
0.70 – 0.89 : likely correct
0.50 – 0.69 : uncertain
below 0.50  : very ambiguous

─────────────────────────────────────────────
ACTIVITY TO CLASSIFY
─────────────────────────────────────────────
{activity_text}

─────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────
Return ONLY valid JSON. No markdown. No text outside JSON.

{{
  "llm_category": "one_of_the_8_allowed_categories",
  "llm_confidence": 0.0,
  "llm_reason": "one sentence explaining the classification in English"
}}
"""


def build_reconciliation_prompt(
    activity_text: str,
    blind_category: str,
    blind_confidence: float,
    system_category: str,
    system_confidence: float,
    system_method: str,
    matched_keywords: str,
) -> str:
    """
    Pass 2 — reconciliation.
    Only called when blind LLM category != system category.
    """

    kw_line = f"- matched_keywords: {matched_keywords}" if matched_keywords else "- matched_keywords: none"

    return f"""
You are auditing a disagreement between two classification systems for Ooredoo Business (Tunisia).

Both systems classified the same company activity but reached DIFFERENT conclusions.
Your job is to decide the correct final category using the business rules below.

─────────────────────────────────────────────
ACTIVITY
─────────────────────────────────────────────
{activity_text}

─────────────────────────────────────────────
CLASSIFICATION RESULTS
─────────────────────────────────────────────
Blind LLM classification:
- category: {blind_category}
- confidence: {blind_confidence}

Rule-based / segmentation system:
- category: {system_category}
- confidence: {system_confidence}
- method: {system_method}
{kw_line}

─────────────────────────────────────────────
KEY BUSINESS RULES
─────────────────────────────────────────────
- Selling ANY product, including medical products, means retail.
- Healthcare means delivering care to patients: clinics, labs, hospitals, doctors, dental care.
- Cafés and restaurants are retail unless clearly part of a hotel.
- Manufacturing means producing, fabricating, transforming, or assembling physical goods.
- Transport means moving people/goods or logistics services.
- Tourism means hotels, accommodation, travel agencies, tourist residences, camping.
- Education means teaching/training/schools/universities.
- Financial services means banks, insurance, credit, accounting, audit, finance.
- Others is last resort only. Prefer a specific category when possible.
- Activities may be in French, Arabic, English, or mixed language.

─────────────────────────────────────────────
CONFIDENCE SCALE
─────────────────────────────────────────────
0.90 – 1.00 : very certain
0.70 – 0.89 : likely correct
0.50 – 0.69 : uncertain
below 0.50  : very ambiguous

─────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────
Return ONLY valid JSON. No markdown. No text outside JSON.

{{
  "llm_category": "final_category",
  "llm_confidence": 0.0,
  "llm_reason": "one sentence explaining your final decision",
  "llm_agrees_with_system": true
}}
"""


# ---------------------------------------------------------------------------
# Ollama caller
# ---------------------------------------------------------------------------

def call_ollama(prompt: str) -> dict:
    """
    Call local Ollama and return parsed JSON response.
    """

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        timeout=120,
    )

    response.raise_for_status()

    raw = response.json()["response"]

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------

def _empty_activity_result(system_category: str) -> dict:
    return {
        "llm_category": "others",
        "llm_confidence": 0.0,
        "llm_reason": "Empty activity text — cannot classify.",
        "llm_agrees_with_system": system_category == "others",
        "llm_pass": "skipped_empty_activity",
    }


def _error_result(error: Exception) -> dict:
    return {
        "llm_category": "",
        "llm_confidence": 0.0,
        "llm_reason": f"LLM error: {error}",
        "llm_agrees_with_system": False,
        "llm_pass": "error",
    }


def _validate_category(raw: str) -> str:
    """
    Return category if valid, otherwise 'others'.
    """

    cleaned = str(raw).strip().lower()

    if cleaned in ALLOWED_CATEGORIES:
        return cleaned

    return "others"


def is_empty_activity(row: pd.Series) -> bool:
    """
    Detect rows with no usable activity text.
    """

    activity_text = str(row.get("activity_raw_combined", "")).strip()
    method = str(row.get("method", "")).strip()

    return activity_text == "" or method == "empty_activity"


def is_risky_row(row: pd.Series) -> bool:
    """
    Decide if a row should be audited when risky-only mode is enabled.
    """

    if is_empty_activity(row):
        return False

    category = str(row.get("category", "")).strip()
    method = str(row.get("method", "")).strip()

    try:
        confidence = float(row.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    needs_review = row.get("needs_review", False)

    if isinstance(needs_review, str):
        needs_review = needs_review.strip().lower() == "true"

    risky_methods = {
        "taxonomy_conflict",
        "no_rule_match",
        "embedding_similarity_low_confidence",
        "rag_similarity_low_confidence",
        "llm_verification",
    }

    return (
        category == "others"
        or confidence < 0.80
        or needs_review is True
        or method in risky_methods
    )


# ---------------------------------------------------------------------------
# Row-level audit
# ---------------------------------------------------------------------------

def audit_one_row(row: pd.Series) -> dict:
    """
    Two-pass audit for one row.

    Pass 1:
        Blind LLM classification without seeing the system category.

    Pass 2:
        Reconciliation only if blind category disagrees with system category.
    """

    activity_text = str(row.get("activity_raw_combined", "")).strip()
    system_category = str(row.get("category", "")).strip()
    system_conf = row.get("confidence", "")
    system_method = row.get("method", "")
    matched_kw = row.get("matched_keywords", "")

    matched_kw = "" if pd.isna(matched_kw) else str(matched_kw).strip()

    if not activity_text:
        return _empty_activity_result(system_category)

    # Pass 1: blind classification
    try:
        blind_result = call_ollama(build_blind_prompt(activity_text))

        blind_category = _validate_category(blind_result.get("llm_category", ""))
        blind_confidence = round(float(blind_result.get("llm_confidence", 0.0)), 3)
        blind_reason = str(blind_result.get("llm_reason", "")).strip()

    except Exception as error:
        return _error_result(error)

    agrees = blind_category == system_category

    # Pass 2: reconciliation only if disagreement
    if not agrees:
        try:
            recon_result = call_ollama(
                build_reconciliation_prompt(
                    activity_text=activity_text,
                    blind_category=blind_category,
                    blind_confidence=blind_confidence,
                    system_category=system_category,
                    system_confidence=system_conf,
                    system_method=system_method,
                    matched_keywords=matched_kw,
                )
            )

            final_category = _validate_category(recon_result.get("llm_category", ""))
            final_confidence = round(float(recon_result.get("llm_confidence", 0.0)), 3)
            final_reason = str(recon_result.get("llm_reason", "")).strip()
            final_agrees = final_category == system_category
            llm_pass = "reconciliation"

        except Exception as error:
            final_category = blind_category
            final_confidence = blind_confidence
            final_reason = f"{blind_reason} [reconciliation failed: {error}]"
            final_agrees = agrees
            llm_pass = "blind_fallback"

    else:
        final_category = blind_category
        final_confidence = blind_confidence
        final_reason = blind_reason
        final_agrees = True
        llm_pass = "blind"

    return {
        "llm_category": final_category,
        "llm_confidence": final_confidence,
        "llm_reason": final_reason,
        "llm_agrees_with_system": final_agrees,
        "llm_pass": llm_pass,
    }


# ---------------------------------------------------------------------------
# Checkpoint / resume helpers
# ---------------------------------------------------------------------------

def load_existing_audit() -> pd.DataFrame | None:
    """
    Load existing audit file if it exists.
    Used for resume mode.
    """

    if not LLM_AUDIT_OUTPUT.exists():
        return None

    try:
        existing = pd.read_csv(LLM_AUDIT_OUTPUT, encoding="utf-8-sig")
        return existing
    except Exception:
        return None


def get_already_audited_keys(existing_df: pd.DataFrame | None) -> set:
    """
    Build a set of rows already audited.
    We use activity_raw_combined + category as a simple key.
    """

    if existing_df is None or existing_df.empty:
        return set()

    required_cols = {"activity_raw_combined", "category", "llm_category"}

    if not required_cols.issubset(existing_df.columns):
        return set()

    audited_df = existing_df[
        existing_df["llm_category"].fillna("").astype(str).str.strip() != ""
    ].copy()

    keys = set(
        zip(
            audited_df["activity_raw_combined"].astype(str),
            audited_df["category"].astype(str),
        )
    )

    return keys


def row_key(row: pd.Series) -> tuple:
    """
    Unique-ish row key for resume mode.
    """

    return (
        str(row.get("activity_raw_combined", "")),
        str(row.get("category", "")),
    )


def save_checkpoint(df: pd.DataFrame) -> None:
    """
    Save current audit progress.
    """

    LLM_AUDIT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        LLM_AUDIT_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def audit_all_rows(
    limit: int | None = None,
    sleep_seconds: float = 0.1,
    only_risky: bool = True,
    checkpoint_every: int = 20,
    resume: bool = True,
) -> pd.DataFrame:

    logger.info("Loading segmented file...")
    df = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")

    logger.info("Original rows: %d", len(df))

    # Filter risky rows if enabled
    if only_risky:
        df_to_process = df[df.apply(is_risky_row, axis=1)].copy()
        logger.info("Risky rows selected: %d", len(df_to_process))
    else:
        df_to_process = df[~df.apply(is_empty_activity, axis=1)].copy()
        logger.info("Non-empty rows selected: %d", len(df_to_process))

    # Apply limit after filtering
    if limit is not None:
        df_to_process = df_to_process.head(limit).copy()
        logger.info("Limit applied. Rows to process: %d", len(df_to_process))

    # FIXED: initialize each LLM column with the correct dtype.
    # Was: all columns initialized with "" (str), which caused pandas to
    # reject float and bool values written later (e.g. llm_confidence=0.85,
    # llm_agrees_with_system=True) with TypeError: Invalid value for dtype str.
    if "llm_category" not in df_to_process.columns:
        df_to_process["llm_category"] = ""
    if "llm_confidence" not in df_to_process.columns:
        df_to_process["llm_confidence"] = 0.0
    if "llm_reason" not in df_to_process.columns:
        df_to_process["llm_reason"] = ""
    if "llm_agrees_with_system" not in df_to_process.columns:
        df_to_process["llm_agrees_with_system"] = False
    if "llm_pass" not in df_to_process.columns:
        df_to_process["llm_pass"] = ""

    llm_columns = [
        "llm_category",
        "llm_confidence",
        "llm_reason",
        "llm_agrees_with_system",
        "llm_pass",
    ]

    # Resume mode
    existing_df = load_existing_audit() if resume else None
    audited_keys = get_already_audited_keys(existing_df)

    if resume and audited_keys:
        logger.info("Resume enabled. Already audited rows found: %d", len(audited_keys))

    total = len(df_to_process)
    audited_now = 0
    skipped_resume = 0

    logger.info("Starting LLM audit on %d selected rows...", total)

    for i, (idx, row) in enumerate(df_to_process.iterrows(), start=1):
        key = row_key(row)

        if resume and key in audited_keys:
            skipped_resume += 1
            logger.debug("[%d/%d] skipped already audited row", i, total)
            continue

        logger.info("[%d/%d] auditing row...", i, total)

        result = audit_one_row(row)

        for col in llm_columns:
            df_to_process.loc[idx, col] = result.get(col, "")

        audited_now += 1

        if checkpoint_every > 0 and audited_now % checkpoint_every == 0:
            save_checkpoint(df_to_process)
            logger.info("Checkpoint saved after %d newly audited rows.", audited_now)

        time.sleep(sleep_seconds)

    # Final save
    save_checkpoint(df_to_process)

    logger.info("LLM audit saved to: %s", LLM_AUDIT_OUTPUT)
    logger.info("Audit summary — selected: %d  newly audited: %d  skipped: %d",
                total, audited_now, skipped_resume)

    if "llm_category" in df_to_process.columns:
        logger.info("LLM category distribution:\n%s",
                    df_to_process["llm_category"].value_counts().to_string())

    if "llm_agrees_with_system" in df_to_process.columns:
        logger.info("Agreement with system:\n%s",
                    df_to_process["llm_agrees_with_system"].value_counts().to_string())

    if "llm_pass" in df_to_process.columns:
        logger.info("Audit pass breakdown:\n%s",
                    df_to_process["llm_pass"].value_counts().to_string())

    disagreements = df_to_process[df_to_process["llm_agrees_with_system"] == False]

    if not disagreements.empty:
        cols = ["activity_raw_combined", "category", "llm_category", "llm_confidence", "llm_reason"]
        existing_cols = [c for c in cols if c in disagreements.columns]
        logger.info("Disagreements: %d rows\n%s",
                    len(disagreements),
                    disagreements[existing_cols].head(10).to_string(index=False))

    return df_to_process


if __name__ == "__main__":
    # First test with 20 risky rows.
    # Later, set limit=None to audit all risky rows.
    audit_all_rows(
        limit=20,
        sleep_seconds=0.1,
        only_risky=True,
        checkpoint_every=10,
        resume=True,
    )