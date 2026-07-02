import re
import unicodedata
import pandas as pd

# Arabic diacritics / tashkeel
ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652]")
TATWEEL = "\u0640"

# Arabic character range
ARABIC_RE = re.compile(r"[\u0600-\u06FF]+")


def normalize_arabic(text: str) -> str:
    text = re.sub(ARABIC_DIACRITICS, "", text)
    text = text.replace(TATWEEL, "")
    text = re.sub("[إأآا]", "ا", text)
    text = text.replace("ى", "ي")
    text = text.replace("ؤ", "و")
    text = text.replace("ئ", "ي")
    return text


def reverse_arabic_runs(text: str) -> str:
    def reverse_match(match):
        return match.group(0)[::-1]
    return ARABIC_RE.sub(reverse_match, text)


def reverse_full_text(text: str) -> str:
    return text[::-1]


def basic_clean(text: str) -> str:
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = normalize_arabic(text)
    text = re.sub(r"[^a-zA-Z0-9\u0600-\u06FF\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_text(text):
    if pd.isna(text):
        return ""
    original_clean = basic_clean(text)
    if not original_clean:
        return ""
    variants = [original_clean]
    full_reversed = basic_clean(reverse_full_text(original_clean))
    if full_reversed:
        variants.append(full_reversed)
    arabic_runs_reversed = basic_clean(reverse_arabic_runs(original_clean))
    if arabic_runs_reversed:
        variants.append(arabic_runs_reversed)
    unique_variants = []
    for variant in variants:
        if variant and variant not in unique_variants:
            unique_variants.append(variant)
    return " | ".join(unique_variants)


def normalize_text_primary(text):
    if pd.isna(text):
        return ""
    return basic_clean(text)