import json
import re
import requests

from segmentation.config import OLLAMA_URL, OLLAMA_MODEL


ALLOWED_CATEGORIES = [
    "retail", "manufacturing", "transport", "tourism",
    "healthcare", "education", "financial_services", "others",
]


def should_use_llm(result):
    method     = result.get("method", "")
    confidence = float(result.get("confidence", 0))
    category   = result.get("category", "")

    if method == "empty_activity":
        return False
    if method == "rag_similarity_low_confidence":
        return True
    if method == "embedding_similarity_low_confidence":
        return True
    if method in ["no_rule_match", "taxonomy_conflict"]:
        return True
    if confidence < 0.70:
        return True
    if category == "others" and confidence < 0.85:
        return True

    return False


def build_llm_prompt(activity_text, current_result):
    current_category = current_result.get("category", "")
    confidence       = current_result.get("confidence", "")
    method           = current_result.get("method", "")
    matched_keywords = current_result.get("matched_keywords", [])
    blocked_keywords = current_result.get("blocked_keywords", [])

    prompt = f"""
You are a B2B company activity segmentation assistant for Ooredoo Business.

Your task:
Verify the category of a company activity using ONLY the project-specific business rules below.

Allowed categories:
- retail
- manufacturing
- transport
- tourism
- healthcare
- education
- financial_services
- others

Project-specific business rules:

1. retail:
Businesses that sell goods or services directly to customers or to other businesses.
Retail includes commerce, vente, distribution, import/export, wholesale, retail, shops,
supermarkets, cafés, restaurants, beauty salons, salons, stores, distributors, and commercial intermediaries.
If the activity is about selling/trading/distribution of products, classify it as retail,
even if the products are medical, food, electronics, construction materials, clothes, or equipment.

2. healthcare:
Use healthcare only for medical care or health services:
clinics, doctors, hospitals, medical laboratories, dental care, ambulance, medical analysis,
healthcare centers, and pharmacies if the activity is clearly a pharmacy/healthcare establishment.
Do NOT classify as healthcare only because the sold product is medical.

3. manufacturing:
Use manufacturing when the company produces, fabricates, transforms, assembles,
or manufactures physical goods.

4. transport:
Use transport for moving people or goods, logistics, delivery, warehousing, freight,
taxi, transit, shipping, and transport support services.

5. tourism:
Use tourism for hotels, accommodation, tourism services, travel agencies,
tourist residences, camping, and tourist activities.
In this project, cafés and restaurants are retail unless clearly part of a hotel/tourism activity.

6. education:
Use education for schools, training centers, teaching, universities, kindergartens,
professional training, and learning services.

7. financial_services:
Use financial_services for banks, insurance, credit, leasing, accounting, audit,
financial advice, investment, and payment services.

8. others:
Use others only if the activity does not clearly fit the previous categories.

Current automatic classification:
- activity: {activity_text}
- current_category: {current_category}
- current_confidence: {confidence}
- method: {method}
- matched_keywords: {matched_keywords}
- blocked_keywords: {blocked_keywords}

Instructions:
- Choose exactly ONE category from the allowed categories.
- Do not invent new categories.
- Follow the project-specific rules even if general knowledge suggests another category.
- Return JSON only.
- If uncertain, set needs_review to true.
- Keep the explanation short.

Return exactly this JSON format:
{{
  "category": "one_allowed_category",
  "confidence": 0.0,
  "needs_review": true,
  "reason": "short explanation"
}}
"""
    return prompt


def call_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
        timeout=90,
    )
    response.raise_for_status()
    raw = response.json()["response"]

    clean = raw.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        clean = match.group(0)

    return json.loads(clean)


def validate_with_llm(activity_text, current_result):
    try:
        prompt     = build_llm_prompt(activity_text, current_result)
        llm_output = call_ollama(prompt)

        category     = str(llm_output.get("category", "")).strip()
        confidence   = float(llm_output.get("confidence", 0.0))
        needs_review = bool(llm_output.get("needs_review", True))
        reason       = str(llm_output.get("reason", "")).strip()

        if category not in ALLOWED_CATEGORIES:
            return current_result

        return {
            "category":         category,
            "confidence":       round(confidence, 3),
            "method":           "llm_verification",
            "matched_keywords": [f"llm_reason: {reason}"],
            "blocked_keywords": [],
            "needs_review":     needs_review or confidence < 0.70,
        }

    except Exception as error:
        fallback = current_result.copy()
        fallback["matched_keywords"] = current_result.get("matched_keywords", []) + [
            f"llm_error: {error}"
        ]
        return fallback