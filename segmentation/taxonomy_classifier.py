import yaml

from segmentation.text_cleaner import normalize_text_primary


def load_taxonomy(taxonomy_path):
    with open(taxonomy_path, "r", encoding="utf-8") as file:
        taxonomy = yaml.safe_load(file)
    validate_taxonomy(taxonomy)
    return taxonomy


def validate_taxonomy(taxonomy):
    required_top_level_keys = ["categories", "priority_order", "sectors"]
    for key in required_top_level_keys:
        if key not in taxonomy:
            raise ValueError(f"Missing required key in taxonomy YAML: {key}")

    categories = taxonomy["categories"]
    priority_order = taxonomy["priority_order"]
    sectors = taxonomy["sectors"]

    for category in categories:
        if category not in sectors:
            raise ValueError(f"Category '{category}' exists in categories but not in sectors.")

    for category in priority_order:
        if category not in categories:
            raise ValueError(f"Category '{category}' exists in priority_order but not in categories.")

    for sector_name, sector_data in sectors.items():
        if "include_keywords" not in sector_data:
            raise ValueError(f"Sector '{sector_name}' is missing include_keywords.")
        if "exclude_keywords" not in sector_data:
            raise ValueError(f"Sector '{sector_name}' is missing exclude_keywords.")


def find_keyword_matches(activity_clean, keywords):
    matches = []
    for keyword in keywords:
        keyword_clean = normalize_text_primary(keyword)
        if keyword_clean and keyword_clean in activity_clean:
            matches.append(keyword)
    return matches


def classify_with_taxonomy(activity_clean, taxonomy):
    if not activity_clean:
        return {
            "category": "others",
            "confidence": 0.0,
            "method": "empty_activity",
            "matched_keywords": [],
            "blocked_keywords": [],
            "needs_review": True,
        }

    sectors = taxonomy["sectors"]
    priority_order = taxonomy["priority_order"]
    conflict_results = []

    for sector_name in priority_order:
        sector_rules = sectors[sector_name]
        include_keywords = sector_rules.get("include_keywords", [])
        exclude_keywords = sector_rules.get("exclude_keywords", [])

        matched_keywords = find_keyword_matches(activity_clean, include_keywords)
        blocked_keywords = find_keyword_matches(activity_clean, exclude_keywords)

        if matched_keywords and not blocked_keywords:
            confidence = calculate_rule_confidence(matched_keywords)
            return {
                "category": sector_name,
                "confidence": confidence,
                "method": "taxonomy_rule",
                "matched_keywords": matched_keywords,
                "blocked_keywords": blocked_keywords,
                "needs_review": False,
            }

        if matched_keywords and blocked_keywords:
            conflict_results.append({
                "category": sector_name,
                "confidence": 0.60,
                "method": "taxonomy_conflict",
                "matched_keywords": matched_keywords,
                "blocked_keywords": blocked_keywords,
                "needs_review": True,
            })

    if conflict_results:
        return conflict_results[0]

    return {
        "category": "others",
        "confidence": 0.50,
        "method": "no_rule_match",
        "matched_keywords": [],
        "blocked_keywords": [],
        "needs_review": True,
    }


def calculate_rule_confidence(matched_keywords):
    confidence = 0.90 + (0.02 * len(matched_keywords))
    confidence = min(confidence, 0.98)
    return round(confidence, 3)