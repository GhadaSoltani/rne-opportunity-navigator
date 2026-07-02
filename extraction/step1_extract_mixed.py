"""
STEP 1 — Extract all table cells from a mixed Arabic/French PDF using Camelot,
with PyMuPDF fallback for missing dirigeants / Nom et Prénom rows.

Output:
    output/<name>_mixed.txt

Usage:
    python src/step1_extract_mixed.py pdfs/1658358N.pdf --output-dir output
    python src/step1_extract_mixed.py pdfs/1658358N.pdf --output-dir output --fallback-debug
    python src/step1_extract_mixed.py pdfs/1658358N.pdf --output-dir output --no-fix-arabic

Why this version:
    Camelot extracts the main table well, but sometimes misses the dirigeants
    table on page 2. If Camelot misses "Nom et Prénom / الإسم و اللقب",
    this script uses PyMuPDF to scan the page text and appends a synthetic row:

        Nom et Prénom | | <arabic_name> | الإسم و اللقب
"""

import argparse
import logging
import os
import re
import unicodedata
from typing import List, Optional

import camelot
import fitz  # PyMuPDF
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


# =============================================================================
# Regex
# =============================================================================

ARABIC_CHAR_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)

ARABIC_RUN_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\u0660-\u0669\u06F0-\u06F9\s]+"
)

ARABIC_TEXT_RUN_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s]+"
)

MULTI_WS_RE = re.compile(r"\s+")


# =============================================================================
# Basic cleaning
# =============================================================================

def clean_text(s) -> str:
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ")
    s = s.replace("\u200e", "")
    s = s.replace("\u200f", "")
    s = MULTI_WS_RE.sub(" ", s).strip()
    return s


def normalize_spaces(s) -> str:
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ")
    s = s.replace("\u200e", " ")
    s = s.replace("\u200f", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_arabic_for_match(s: str) -> str:
    s = clean_text(s)

    s = s.replace("إ", "ا")
    s = s.replace("أ", "ا")
    s = s.replace("آ", "ا")
    s = s.replace("ٱ", "ا")
    s = s.replace("ى", "ي")
    s = s.replace("ؤ", "و")
    s = s.replace("ئ", "ي")

    s = re.sub(r"[\u064B-\u065F]", "", s)
    s = s.replace("\u0640", "")

    return s.strip(" :|-،؛")


def has_arabic(s: str) -> bool:
    return bool(ARABIC_CHAR_RE.search(clean_text(s)))


# =============================================================================
# Optional Camelot Arabic reversal fix
# =============================================================================

def reverse_arabic_run(match: re.Match) -> str:
    text = match.group(0)

    if not text.strip():
        return text

    return text[::-1]


def fix_reversed_arabic(s: str) -> str:
    """
    Fix Arabic when Camelot returns it in visual reversed order.

    Example:
        تايطعم -> معطيات
        فيرعتلا -> التعريف
    """
    if not ARABIC_CHAR_RE.search(s):
        return s

    fixed = ARABIC_RUN_RE.sub(reverse_arabic_run, s)
    return normalize_spaces(fixed)


def clean_cell(s, fix_arabic: bool = True) -> str:
    s = normalize_spaces(s)

    if fix_arabic:
        s = fix_reversed_arabic(s)

    return s


# =============================================================================
# Camelot extraction
# =============================================================================

def read_tables_best(pdf_path: str, page: str):
    """
    Try stream first, then lattice.
    """
    try:
        tables = camelot.read_pdf(pdf_path, pages=page, flavor="stream")
        if tables.n > 0:
            return tables, "stream"
    except Exception:
        pass

    tables = camelot.read_pdf(pdf_path, pages=page, flavor="lattice")
    return tables, "lattice"


# =============================================================================
# PyMuPDF fallback for missing Nom et Prénom
# =============================================================================

NAME_LABEL_VARIANTS = [
    "الإسم و اللقب",
    "اإلسم و اللقب",
    "الاسم و اللقب",
    "اﻹﺳﻢ و اﻟﻠﻘﺐ",
]

BLOCKED_ARABIC_VALUES = [
    "الإسم و اللقب",
    "اإلسم و اللقب",
    "الاسم و اللقب",
    "اﻹﺳﻢ و اﻟﻠﻘﺐ",
    "المسيرون",
    "الصفة",
    "الجنسية",
    "وكيل",
    "مسير",
    "مدير",
    "مديرة",
    "وكيلة",
    "تونسي",
    "تونسية",
    "رئيس",
]


def is_name_label(text: str) -> bool:
    text_norm = normalize_arabic_for_match(text)

    for label in NAME_LABEL_VARIANTS:
        label_norm = normalize_arabic_for_match(label)
        if label_norm and label_norm in text_norm:
            return True

    return False


def is_blocked_arabic_value(text: str) -> bool:
    text_norm = normalize_arabic_for_match(text)

    if not text_norm:
        return True

    if is_name_label(text):
        return True

    for blocked in BLOCKED_ARABIC_VALUES:
        blocked_norm = normalize_arabic_for_match(blocked)
        if text_norm == blocked_norm:
            return True

    return False


def dedupe_repeated_name_words(text: str) -> str:
    """
    Turns:
        رضا علي رضا علي
    into:
        رضا علي
    """
    text = clean_text(text)
    words = text.split()

    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])

    return text


def clean_arabic_name_candidate(text: str) -> str:
    """
    Clean Arabic name candidate from PyMuPDF fallback.

    Handles PyMuPDF visual-order output like:
        علي رضا علي رضا اللقب و اإلسم

    Converts it to:
        رضا علي
    """
    text = clean_text(text)

    # Normalize Arabic presentation forms but keep visible value.
    text = unicodedata.normalize("NFKC", text)

    # Remove normal label variants.
    for label in NAME_LABEL_VARIANTS:
        text = text.replace(clean_text(label), " ")

    # Remove reversed label forms often produced by PyMuPDF visual order.
    reversed_label_variants = [
        "اللقب و الإسم",
        "اللقب و اإلسم",
        "اللقب و الاسم",
        "اﻟﻠﻘﺐ و اﻹﺳﻢ",
    ]

    for label in reversed_label_variants:
        text = text.replace(clean_text(label), " ")

    # Remove individual label words if they remain.
    label_words = [
        "الإسم",
        "اإلسم",
        "الاسم",
        "اﻹﺳﻢ",
        "اللقب",
        "اﻟﻠﻘﺐ",
    ]

    words = [w for w in text.split() if w.strip()]
    cleaned_words = []

    for word in words:
        word_norm = normalize_arabic_for_match(word)

        if any(word_norm == normalize_arabic_for_match(label_word) for label_word in label_words):
            continue

        if word_norm == normalize_arabic_for_match("و"):
            continue

        if any(word_norm == normalize_arabic_for_match(blocked) for blocked in BLOCKED_ARABIC_VALUES):
            continue

        cleaned_words.append(word)

    text = " ".join(cleaned_words)
    text = MULTI_WS_RE.sub(" ", text).strip(" :|-،؛")

    # Deduplicate duplicated visual extraction:
    #   علي رضا علي رضا -> علي رضا
    text = dedupe_repeated_name_words(text)

    # PyMuPDF often gives Arabic words in visual left-to-right order.
    # So:
    #   علي رضا -> رضا علي
    words = text.split()
    if 2 <= len(words) <= 5:
        text = " ".join(reversed(words))

    return text


def looks_like_person_name(text: str) -> bool:
    text = clean_arabic_name_candidate(text)

    if not text or not has_arabic(text):
        return False

    if is_blocked_arabic_value(text):
        return False

    if re.search(r"\d", text):
        return False

    words = [w for w in text.split() if w.strip()]

    if not (1 <= len(words) <= 5):
        return False

    return True


def group_words_into_lines(words: list, y_tolerance: float = 4.0) -> List[List[tuple]]:
    if not words:
        return []

    words = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    lines = []

    for word in words:
        x0, y0, x1, y1, text = word[:5]

        if not clean_text(text):
            continue

        if not lines:
            lines.append([word])
            continue

        last_line = lines[-1]
        last_y = sum(w[1] for w in last_line) / len(last_line)

        if abs(y0 - last_y) <= y_tolerance:
            last_line.append(word)
        else:
            lines.append([word])

    for line in lines:
        line.sort(key=lambda w: w[0])

    return lines


def line_to_text(line_words: List[tuple]) -> str:
    parts = [clean_text(w[4]) for w in line_words if clean_text(w[4])]
    return clean_text(" ".join(parts))


def extract_arabic_name_from_line_text(line_text: str) -> str:
    """
    Given something like:
        Nom et Prénom علي رضا علي رضا اللقب و اإلسم

    return:
        رضا علي
    """
    line_text = clean_text(line_text)

    if not has_arabic(line_text):
        return ""

    arabic_runs = ARABIC_TEXT_RUN_RE.findall(line_text)
    candidates = []

    for run in arabic_runs:
        candidate = clean_arabic_name_candidate(run)

        if looks_like_person_name(candidate):
            candidates.append(candidate)

    if not candidates:
        return ""

    return candidates[0]


def find_arabic_nom_prenom_on_page(
    pdf_path: str,
    page_index_zero_based: int,
    fallback_debug: bool = False,
) -> str:
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_index_zero_based]
        words = page.get_text("words")
        doc.close()
    except Exception as exc:
        logger.warning(f"PyMuPDF fallback failed on page {page_index_zero_based + 1}: {exc}")
        return ""

    lines = group_words_into_lines(words)
    candidate_lines = []

    for line_words in lines:
        text = line_to_text(line_words)
        text_norm = normalize_arabic_for_match(text)
        text_lower = text.lower()

        has_french_label = "nom et prénom" in text_lower or "nom et prenom" in text_lower
        has_ar_label = any(
            normalize_arabic_for_match(label) in text_norm
            for label in NAME_LABEL_VARIANTS
        )

        if has_french_label or has_ar_label:
            candidate_lines.append(text)

    if fallback_debug:
        print("\n[DEBUG] PyMuPDF candidate lines for Nom et Prénom:")
        for line in candidate_lines:
            print("  ", repr(line))

    for text in candidate_lines:
        name = extract_arabic_name_from_line_text(text)

        if name:
            if fallback_debug:
                print(f"[DEBUG] Extracted Arabic name: {name}")
            return name

    return ""


def page_already_has_nom_prenom(page_lines: List[str]) -> bool:
    joined = "\n".join(clean_text(x) for x in page_lines)

    if "Nom et Prénom" in joined or "Nom et Prenom" in joined:
        return True

    joined_norm = normalize_arabic_for_match(joined)

    for label in NAME_LABEL_VARIANTS:
        if normalize_arabic_for_match(label) in joined_norm:
            return True

    return False


def maybe_append_dirigeants_fallback(
    pdf_path: str,
    page_num: int,
    page_lines: List[str],
    fallback_debug: bool = False,
) -> None:
    """
    Add synthetic Nom et Prénom row when Camelot misses the dirigeants table.
    """
    if page_already_has_nom_prenom(page_lines):
        return

    name = find_arabic_nom_prenom_on_page(
        pdf_path=pdf_path,
        page_index_zero_based=page_num - 1,
        fallback_debug=fallback_debug,
    )

    if not name:
        return

    page_lines.append("--- TEXT FALLBACK DIRIGEANTS ---")
    page_lines.append(f"Nom et Prénom | | {name} | الإسم و اللقب")

    logger.info(f"Page {page_num}: fallback Nom et Prénom extracted → {name}")


# =============================================================================
# Main extraction
# =============================================================================

def extract_mixed_text(
    pdf_path: str,
    output_dir: str = "output",
    fix_arabic: bool = True,
    fallback_debug: bool = False,
) -> str:
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    os.makedirs(output_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out_path = os.path.join(output_dir, f"{base}_mixed.txt")

    try:
        n_pages = len(PdfReader(pdf_path).pages)
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF '{pdf_path}': {exc}") from exc

    all_lines = []

    for page_num in range(1, n_pages + 1):
        page_str = str(page_num)

        page_lines = []
        page_lines.append("")
        page_lines.append("=" * 60)
        page_lines.append(f"PAGE {page_str}")
        page_lines.append("=" * 60)
        page_lines.append("")

        try:
            tables, flavor = read_tables_best(pdf_path, page_str)
        except Exception as exc:
            logger.warning(f"Page {page_str}: Camelot extraction failed — {exc}")
            tables = []
            flavor = "none"

        if hasattr(tables, "n"):
            logger.info(f"Page {page_str}: {tables.n} table(s) [{flavor}]")

            for t_idx, table in enumerate(tables, start=1):
                page_lines.append(f"--- TABLE {t_idx} ---")

                for row in table.df.itertuples(index=False):
                    cells = [clean_cell(c, fix_arabic=fix_arabic) for c in row]
                    page_lines.append(" | ".join(cells))
        else:
            logger.info(f"Page {page_str}: 0 table(s) [none]")

        maybe_append_dirigeants_fallback(
            pdf_path=pdf_path,
            page_num=page_num,
            page_lines=page_lines,
            fallback_debug=fallback_debug,
        )

        all_lines.extend(page_lines)

    content = "\n".join(all_lines)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Mixed text saved → {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--output-dir", default="output", help="Output folder")

    parser.add_argument(
        "--no-fix-arabic",
        action="store_true",
        help="Disable Arabic RTL reversal fix for Camelot cells",
    )

    parser.add_argument(
        "--fallback-debug",
        action="store_true",
        help="Print PyMuPDF candidate lines used for Nom et Prénom fallback",
    )

    args = parser.parse_args()

    extract_mixed_text(
        pdf_path=args.pdf,
        output_dir=args.output_dir,
        fix_arabic=not args.no_fix_arabic,
        fallback_debug=args.fallback_debug,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()