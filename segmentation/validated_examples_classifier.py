import re
import pandas as pd

from segmentation.text_cleaner import normalize_text_primary


def load_validated_examples(path):
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except FileNotFoundError:
        return {}

    if df.empty:
        return {}

    if "activity" not in df.columns or "category" not in df.columns:
        return {}

    df = df.dropna(subset=["activity", "category"])

    validated_examples = {}

    for _, row in df.iterrows():
        activity_clean = normalize_text_primary(row["activity"])
        category = str(row["category"]).strip()
        if activity_clean and category:
            validated_examples[activity_clean] = category

    return validated_examples


def _build_partial_match_patterns(validated_examples: dict) -> list:
    patterns = []
    for example_activity, category in validated_examples.items():
        if len(example_activity) < 5:
            continue
        pattern = re.compile(r"\b" + re.escape(example_activity) + r"\b")
        patterns.append((pattern, example_activity, category))
    return patterns


def load_validated_examples_with_patterns(path):
    validated_examples = load_validated_examples(path)
    partial_patterns   = _build_partial_match_patterns(validated_examples)
    return validated_examples, partial_patterns


def classify_with_validated_examples(activity_clean, validated_examples, partial_patterns=None):
    if not activity_clean:
        return None

    if activity_clean in validated_examples:
        return {
            "category":         validated_examples[activity_clean],
            "confidence":       1.0,
            "method":           "validated_example_exact",
            "matched_keywords": ["manual_correction"],
            "blocked_keywords": [],
            "needs_review":     False,
        }

    if partial_patterns is not None:
        for pattern, example_activity, category in partial_patterns:
            if pattern.search(activity_clean):
                return {
                    "category":         category,
                    "confidence":       0.90,
                    "method":           "validated_example_partial",
                    "matched_keywords": [f"partial_match: {example_activity}"],
                    "blocked_keywords": [],
                    "needs_review":     True,
                }
    else:
        for example_activity, category in validated_examples.items():
            if len(example_activity) < 5:
                continue
            pattern = r"\b" + re.escape(example_activity) + r"\b"
            if re.search(pattern, activity_clean):
                return {
                    "category":         category,
                    "confidence":       0.90,
                    "method":           "validated_example_partial",
                    "matched_keywords": [f"partial_match: {example_activity}"],
                    "blocked_keywords": [],
                    "needs_review":     True,
                }

    return None