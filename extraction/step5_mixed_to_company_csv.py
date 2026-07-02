"""
STEP 4 — Convert clean Camelot mixed txt into a compact horizontal company CSV.

Input:
    output/<name>_mixed.txt

Outputs:
    output/rne_companies.csv
    output/rne_audit.csv
    output/rne_companies.sqlite

Each row = one company.
Primary key = identifiant_unique.

Usage:
    python src/step4_mixed_to_company_csv.py output/1658358N_mixed.txt

Reset output for testing:
    python src/step4_mixed_to_company_csv.py output/1658358N_mixed.txt --reset

Disable SQLite:
    python src/step4_mixed_to_company_csv.py output/1658358N_mixed.txt --no-sqlite
"""

import argparse
import csv
import os
import re
import sqlite3
import unicodedata
from typing import Dict, List, Optional, Tuple


# =============================================================================
# Final horizontal CSV schema
# =============================================================================

OUTPUT_COLUMNS = [
    "identifiant_unique",
    "fr_type_registre",
    "fr_etat_registre",
    "date_debut_activite",
    "fr_denomination",
    "ar_denomination",
    "fr_nom_commercial",
    "ar_nom_commercial",
    "fr_forme_juridique",
    "ar_forme_juridique",
    "fr_adresse",
    "ar_adresse",
    "capital",
    "duree",
    "date_immatriculation",
    "fr_activite",
    "ar_activite",
    "fr_activite_principale",
    "ar_activite_principale",
    "code_activite_principale",
    "ar_nom_prenom",
    "fr_nationalite",
    "ar_nationalite",
    "fr_nantissement",
    "fr_leasing",
    "fr_situation_fiscale",
    "extraction_status",
]

AUDIT_COLUMNS = [
    "source_file",
    "identifiant_unique",
    "field_key",
    "issue_type",
    "message",
    "page",
    "line_number",
    "raw_line",
]


# =============================================================================
# Regex / constants
# =============================================================================

ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)

MULTI_WS = re.compile(r"\s+")

FR_STATUS_OPTIONS = [
    "Actif",
    "Suspension provisoire",
    "Registre radié",
]

FR_YES_NO = ["Oui", "Non"]

FR_FISCAL_OPTIONS = [
    "Régularisée",
    "Regularisee",
    "En défaut de plus 12 mois et moins de 24 mois",
    "En défaut de plus de 24 mois",
]


# =============================================================================
# Field definitions
# =============================================================================

FIELDS = [
    {
        "key": "identifiant_unique",
        "fr_labels": ["N° Identifiant unique"],
        "ar_labels": ["المعرف الوحيد", "اﻟﻤﻌﺮف اﻟﻮﺣﻴﺪ"],
        "column": "identifiant_unique",
        "same_value": True,
        "required": True,
    },
    {
        "key": "type_registre",
        "fr_labels": ["Type du registre"],
        "ar_labels": ["نوع السجل", "ﻧﻮع اﻟﺴﺠﻞ"],
        "column": "fr_type_registre",
    },
    {
        "key": "etat_registre",
        "fr_labels": ["Etat du registre", "État du registre"],
        "ar_labels": ["حالة السجل", "ﺣﺎﻟﺔ اﻟﺴﺠﻞ"],
        "column": "fr_etat_registre",
        "special": "etat_registre",
    },
    {
        "key": "date_debut_activite",
        "fr_labels": ["Date début d'activité", "Date debut d'activité"],
        "ar_labels": ["تاريخ بداية النشاط", "ﺗﺎﺭﻳﺦ ﺑﺪﺍﻳﺔ اﻟﻨﺸﺎﻁ"],
        "column": "date_debut_activite",
        "same_value": True,
    },
    {
        "key": "denomination",
        "fr_labels": ["Dénomination", "Denomination"],
        "ar_labels": ["التسمية", "اﻟﺘﺴﻤﻴﺔ"],
        "fr_column": "fr_denomination",
        "ar_column": "ar_denomination",
    },
    {
        "key": "nom_commercial",
        "fr_labels": ["Nom commercial"],
        "ar_labels": [
            "الإسم التجاري",
            "اإلسم التجاري",
            "الاسم التجاري",
            "اﻹﺳﻢ اﻟﺘﺠﺎري",
        ],
        "fr_column": "fr_nom_commercial",
        "ar_column": "ar_nom_commercial",
    },
    {
        "key": "forme_juridique",
        "fr_labels": ["Forme Juridique", "Forme juridique"],
        "ar_labels": [
            "النظام القانوني",
            "الشكل القانوني",
            "اﻟﻨﻈﺎﻡ اﻟﻘﺎﻧﻮﻧﻲ",
            "اﻟﺸﻜﻞ اﻟﻘﺎﻧﻮﻧﻲ",
        ],
        "fr_column": "fr_forme_juridique",
        "ar_column": "ar_forme_juridique",
    },
    {
        "key": "adresse",
        "fr_labels": ["Adresse"],
        "ar_labels": ["عنوان المقر", "المقر", "ﻋﻨﻮاﻥ اﻟﻤﻘﺮ"],
        "fr_column": "fr_adresse",
        "ar_column": "ar_adresse",
    },
    {
        "key": "capital",
        "fr_labels": ["Capital"],
        "ar_labels": ["رأس المال", "ﺭﺃﺱ اﻟﻤﺎﻝ"],
        "column": "capital",
        "same_value": True,
    },
    {
        "key": "duree",
        "fr_labels": ["Durée", "Duree"],
        "ar_labels": ["مدة الشركة", "ﻣﺪﺓ اﻟﺸﺮﻛﺔ"],
        "column": "duree",
        "same_value": True,
    },
    {
        "key": "date_immatriculation",
        "fr_labels": ["Date d'immatriculation"],
        "ar_labels": [
            "تاريخ التسجيل",
            "تاريخ الترسيم",
            "ﺗﺎﺭﻳﺦ اﻟﺘﺴﺠﻴﻞ",
            "ﺗﺎﺭﻳﺦ اﻟﺘﺮﺳﻴﻢ",
        ],
        "column": "date_immatriculation",
        "same_value": True,
    },
    {
        "key": "activite",
        "fr_labels": ["Activité", "Activite"],
        "ar_labels": ["نوع النشاط", "ﻧﻮع اﻟﻨﺸﺎﻁ"],
        "fr_column": "fr_activite",
        "ar_column": "ar_activite",
    },
    {
        "key": "activite_principale",
        "fr_labels": [
            "Activité principale:",
            "Activité principale",
            "Activite principale:",
            "Activite principale",
        ],
        "ar_labels": [
            "النشاط الرئيسي:",
            "النشاط الرئيسي",
            "اﻟﻨﺸﺎﻁ اﻟﺮﺋﻴﺴﻲ",
            "اﻟﻨﺸﺎﻁ اﻟﺮﺋﻴﺴﻲ:",
        ],
        "fr_column": "fr_activite_principale",
        "ar_column": "ar_activite_principale",
        "allow_next_line_value": True,
    },
    {
        "key": "code_activite_principale",
        "fr_labels": [
            "Code activité principale:",
            "Code activité principale",
            "Code activite principale:",
            "Code activite principale",
        ],
        "ar_labels": [
            "رمز النشاط الرئيسي:",
            "رمز النشاط الرئيسي",
            "ﺭﻣﺰ اﻟﻨﺸﺎﻁ اﻟﺮﺋﻴﺴﻲ",
            "ﺭﻣﺰ اﻟﻨﺸﺎﻁ اﻟﺮﺋﻴﺴﻲ:",
        ],
        "column": "code_activite_principale",
        "same_value": True,
    },
    {
        "key": "nom_prenom",
        "fr_labels": ["Nom et Prénom", "Nom et Prenom"],
        "ar_labels": [
            "الإسم و اللقب",
            "اإلسم و اللقب",
            "الاسم و اللقب",
            "اﻹﺳﻢ و اﻟﻠﻘﺐ",
        ],
        "ar_column": "ar_nom_prenom",
        "special": "arabic_name",
    },
    {
        "key": "nationalite",
        "fr_labels": ["Nationalité", "Nationalite"],
        "ar_labels": ["الجنسية", "اﻟﺠﻨﺴﻴﺔ"],
        "fr_column": "fr_nationalite",
        "ar_column": "ar_nationalite",
    },
    {
        "key": "nantissement",
        "fr_labels": ["Nantissement"],
        "ar_labels": ["الرهون", "اﻟﺮﻫﻮﻥ"],
        "fr_column": "fr_nantissement",
        "special": "oui_non",
    },
    {
        "key": "leasing",
        "fr_labels": ["Leasing"],
        "ar_labels": ["الإيجار", "الايجار", "اﻹﻳﺠﺎﺭ"],
        "fr_column": "fr_leasing",
        "special": "oui_non",
    },
    {
        "key": "situation_fiscale",
        "fr_labels": ["Situation fiscale"],
        "ar_labels": ["الوضعية الجبائية", "اﻟﻮﺿﻌﻴﺔ اﻟﺠﺒﺎﺋﻴﺔ"],
        "fr_column": "fr_situation_fiscale",
        "special": "situation_fiscale",
    },
]


# =============================================================================
# Text helpers
# =============================================================================

def clean_text(s) -> str:
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ")
    s = s.replace("\u200e", "")
    s = s.replace("\u200f", "")
    s = MULTI_WS.sub(" ", s).strip()
    return s


def normalize_arabic_text(s: str) -> str:
    s = clean_text(s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[إأآٱاٲٳ]", "ا", s)
    s = s.replace("ى", "ي")
    s = s.replace("ؤ", "و")
    s = s.replace("ئ", "ي")
    s = re.sub(r"[\u064B-\u065F]", "", s)
    s = s.replace("\u0640", "")
    s = s.strip(" :")
    return s


def has_arabic(s: str) -> bool:
    return bool(ARABIC_RE.search(clean_text(s) or ""))


def normalize_label(s: str) -> str:
    s = clean_text(s)
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    s = s.strip(" :")
    return s


def split_pipe_line(line: str) -> List[str]:
    cells = [clean_text(c) for c in line.split("|")]
    return [c for c in cells if c]


def get_page_from_line(line: str) -> Optional[int]:
    m = re.match(r"PAGE\s+(\d+)", clean_text(line))
    return int(m.group(1)) if m else None


def is_noise_line(line: str) -> bool:
    line = clean_text(line)

    if not line:
        return True

    if line.startswith("="):
        return True

    if line.startswith("--- TABLE"):
        return True

    return False


def label_matches(cell: str, labels: List[str]) -> bool:
    cell_norm = normalize_label(cell)
    cell_ar_norm = normalize_arabic_text(cell)

    for label in labels:
        if normalize_label(label) == cell_norm:
            return True

        if normalize_arabic_text(label) == cell_ar_norm:
            return True

    return False


def label_contains(cell: str, labels: List[str]) -> bool:
    cell_norm = normalize_label(cell)
    cell_ar_norm = normalize_arabic_text(cell)

    for label in labels:
        label_norm = normalize_label(label)
        label_ar_norm = normalize_arabic_text(label)

        if label_norm and label_norm in cell_norm:
            return True

        if label_ar_norm and label_ar_norm in cell_ar_norm:
            return True

    return False


def find_spec_by_fr_label(cell: str) -> Optional[dict]:
    for spec in FIELDS:
        if label_matches(cell, spec["fr_labels"]):
            return spec

    return None


def find_spec_by_ar_label(cell: str) -> Optional[dict]:
    for spec in FIELDS:
        if label_matches(cell, spec["ar_labels"]) or label_contains(cell, spec["ar_labels"]):
            return spec

    return None


def looks_like_new_field(cells: List[str]) -> bool:
    return any(find_spec_by_fr_label(c) or find_spec_by_ar_label(c) for c in cells)


def contains_any(text: str, options: List[str]) -> Optional[str]:
    text = clean_text(text)

    for option in options:
        if option and option in text:
            return option

    return None


# =============================================================================
# Arabic name helpers
# =============================================================================

_NOM_PRENOM_AR_LABELS_NORM = {
    normalize_arabic_text(v)
    for v in [
        "الإسم و اللقب",
        "اإلسم و اللقب",
        "الاسم و اللقب",
        "اﻹﺳﻢ و اﻟﻠﻘﺐ",
    ]
}

_AR_NON_NAME_WORDS_NORM = {
    normalize_arabic_text(v)
    for v in [
        "المسيرون",
        "الصفة",
        "الجنسية",
        "وكيل",
        "مسير",
        "مدير",
        "تونسي",
        "تونسية",
        "رئيس",
        "مديرة",
        "وكيلة",
    ]
}


def _is_ar_nom_label(cell: str) -> bool:
    return normalize_arabic_text(cell) in _NOM_PRENOM_AR_LABELS_NORM


def _is_ar_non_name(cell: str) -> bool:
    norm = normalize_arabic_text(cell)

    if norm in _NOM_PRENOM_AR_LABELS_NORM:
        return True

    if norm in _AR_NON_NAME_WORDS_NORM:
        return True

    return False


def _looks_like_arabic_name(cell: str) -> bool:
    cell = clean_text(cell)

    if not cell or not has_arabic(cell):
        return False

    if _is_ar_non_name(cell):
        return False

    if re.search(r"\d", cell):
        return False

    words = cell.split()

    if not (1 <= len(words) <= 5):
        return False

    return True


def extract_arabic_name_from_row(cells: List[str]) -> str:
    arabic_name_candidates = []
    seen = set()

    for cell in cells:
        cell = clean_text(cell)

        if not has_arabic(cell):
            continue

        if _is_ar_nom_label(cell):
            continue

        if _looks_like_arabic_name(cell):
            norm = normalize_arabic_text(cell)

            if norm not in seen:
                arabic_name_candidates.append(cell)
                seen.add(norm)

    if arabic_name_candidates:
        return arabic_name_candidates[0]

    return ""


# =============================================================================
# Load mixed txt
# =============================================================================

def load_lines_cells(mixed_path: str) -> List[dict]:
    rows = []
    current_page = None

    with open(mixed_path, encoding="utf-8") as f:
        raw_lines = [line.rstrip("\n") for line in f]

    for line_number, raw_line in enumerate(raw_lines, start=1):
        page = get_page_from_line(raw_line)

        if page is not None:
            current_page = page
            continue

        if is_noise_line(raw_line):
            continue

        cells = split_pipe_line(raw_line)

        if not cells:
            continue

        rows.append(
            {
                "page": current_page,
                "line_number": line_number,
                "raw_line": raw_line,
                "cells": cells,
            }
        )

    return rows


# =============================================================================
# Extraction helpers
# =============================================================================

def extract_arabic_value_from_cells(arabic_cells: List[str], spec: dict) -> str:
    normalized_cells = [clean_text(c) for c in arabic_cells if clean_text(c)]

    if not normalized_cells:
        return ""

    label_indexes = [
        i for i, cell in enumerate(normalized_cells)
        if label_matches(cell, spec.get("ar_labels", []))
        or label_contains(cell, spec.get("ar_labels", []))
    ]

    values = [
        cell for i, cell in enumerate(normalized_cells)
        if i not in label_indexes
    ]

    return clean_text(" ".join(values))


def extract_regular_field(
    lines: List[dict],
    index: int,
    spec: dict,
) -> Tuple[str, str, float]:
    cells = lines[index]["cells"]

    fr_idx = next(
        (i for i, c in enumerate(cells) if label_matches(c, spec["fr_labels"])),
        None,
    )

    if fr_idx is None:
        return "", "", 0.0

    after = cells[fr_idx + 1:]

    french_cells = [clean_text(c) for c in after if c and not has_arabic(c)]
    arabic_cells = [clean_text(c) for c in after if c and has_arabic(c)]

    fr_value = clean_text(" ".join(french_cells))
    ar_value = extract_arabic_value_from_cells(arabic_cells, spec)

    if spec.get("same_value") and fr_value and not ar_value:
        ar_value = fr_value

    if spec.get("allow_next_line_value") and index + 1 < len(lines):
        next_cells = lines[index + 1]["cells"]

        if not looks_like_new_field(next_cells):
            next_fr = [clean_text(c) for c in next_cells if c and not has_arabic(c)]
            next_ar = [clean_text(c) for c in next_cells if c and has_arabic(c)]

            if next_fr:
                fr_value = clean_text(fr_value + " " + " ".join(next_fr))

            if next_ar:
                ar_value = clean_text(
                    ar_value + " " + extract_arabic_value_from_cells(next_ar, spec)
                )

    if not fr_value and not ar_value:
        return "", "", 0.0

    return fr_value, ar_value, 1.0


def extract_arabic_name_field(
    lines: List[dict],
    index: int,
    spec: dict,
) -> Tuple[str, float]:
    name = extract_arabic_name_from_row(lines[index]["cells"])

    if name:
        confidence = 1.0 if len(name.split()) >= 2 else 0.8
        return name, confidence

    for i in range(index + 1, min(len(lines), index + 4)):
        first_cell = lines[i]["cells"][0] if lines[i]["cells"] else ""

        if find_spec_by_fr_label(first_cell):
            break

        name = extract_arabic_name_from_row(lines[i]["cells"])

        if name:
            confidence = 1.0 if len(name.split()) >= 2 else 0.8
            return name, confidence

    return "", 0.0


def fallback_extract_ar_nom_prenom(lines: List[dict]) -> Tuple[str, float, dict]:
    for item in lines:
        cells = item["cells"]

        has_fr_label = any(
            label_matches(c, ["Nom et Prénom", "Nom et Prenom"])
            for c in cells
        )

        has_ar_label = any(_is_ar_nom_label(c) for c in cells)

        if not has_fr_label and not has_ar_label:
            continue

        name = extract_arabic_name_from_row(cells)

        if name:
            confidence = 1.0 if len(name.split()) >= 2 else 0.8
            return name, confidence, item

    return "", 0.0, {}


def extract_status_field(lines: List[dict], index: int) -> Tuple[str, float]:
    candidates = []

    for i in range(max(0, index - 1), min(len(lines), index + 3)):
        joined = " ".join(lines[i]["cells"])
        option = contains_any(joined, FR_STATUS_OPTIONS)

        if option:
            candidates.append({"line_index": i, "value": option})

    if not candidates:
        return "", 0.0

    previous = [c for c in candidates if c["line_index"] < index]

    if previous:
        return previous[0]["value"], 1.0

    return candidates[0]["value"], 0.8


def extract_oui_non_field(lines: List[dict], index: int) -> Tuple[str, float]:
    for i in range(index + 1, min(len(lines), index + 5)):
        if looks_like_new_field(lines[i]["cells"]):
            break

        option = contains_any(" ".join(lines[i]["cells"]), FR_YES_NO)

        if option:
            return option, 1.0

    return "", 0.0


def extract_situation_fiscale(lines: List[dict], index: int) -> Tuple[str, float]:
    candidates = []

    for i in range(max(0, index - 2), min(len(lines), index + 3)):
        option = contains_any(" ".join(lines[i]["cells"]), FR_FISCAL_OPTIONS)

        if option:
            candidates.append({"line_index": i, "value": option})

    if not candidates:
        return "", 0.0

    previous = [c for c in candidates if c["line_index"] < index]

    if previous:
        return previous[-1]["value"], 1.0

    return candidates[0]["value"], 0.8


# =============================================================================
# Fallback from rne_records_long.csv
# =============================================================================

LONG_TO_COMPANY_ARABIC_MAP = {
    "denomination": "ar_denomination",
    "nom_commercial": "ar_nom_commercial",
    "activite": "ar_activite",
    "activite_principale": "ar_activite_principale",
    "nom_prenom": "ar_nom_prenom",
    "nom_prenom_dirigeant": "ar_nom_prenom",
}


def clean_arabic_extracted_value(value: str, label: str = "") -> str:
    value = clean_text(value)
    label = clean_text(label)

    if not value:
        return ""

    value_norm = normalize_arabic_text(value)
    label_norm = normalize_arabic_text(label)

    if label_norm and value_norm == label_norm:
        return ""

    if label_norm and label_norm in value_norm:
        value = value.replace(label, "")
        value = clean_text(value)

    return value


def enrich_missing_arabic_from_long_csv(
    row: Dict[str, str],
    mixed_path: str,
    output_dir: str,
) -> Dict[str, str]:
    long_csv_path = os.path.join(output_dir, "rne_records_long.csv")

    if not os.path.exists(long_csv_path):
        return row

    current_id = row.get("identifiant_unique", "")
    source_file = os.path.basename(mixed_path).replace("_mixed.txt", "")

    try:
        with open(long_csv_path, encoding="utf-8-sig", newline="") as f:
            long_rows = list(csv.DictReader(f))
    except Exception:
        return row

    for long_row in long_rows:
        long_id = clean_text(long_row.get("identifiant_unique", ""))
        long_source = clean_text(long_row.get("source_file", ""))
        field_key = clean_text(long_row.get("field_key", ""))

        if current_id and long_id and long_id != current_id:
            continue

        if not current_id and long_source and long_source != source_file:
            continue

        target_col = LONG_TO_COMPANY_ARABIC_MAP.get(field_key)

        if not target_col or row.get(target_col):
            continue

        ar_value = clean_arabic_extracted_value(
            long_row.get("ar_value", ""),
            long_row.get("ar_label", ""),
        )

        if ar_value:
            row[target_col] = ar_value

    return row


# =============================================================================
# Apply extraction to final row
# =============================================================================

def make_empty_company_row() -> Dict[str, str]:
    row = {col: "" for col in OUTPUT_COLUMNS}
    row["extraction_status"] = "ok"
    return row


def set_row_values(
    row: Dict[str, str],
    spec: dict,
    fr_value: str,
    ar_value: str,
) -> None:
    if spec.get("column"):
        value = fr_value or ar_value

        if value:
            row[spec["column"]] = value

    if spec.get("fr_column") and fr_value:
        row[spec["fr_column"]] = fr_value

    if spec.get("ar_column") and ar_value:
        row[spec["ar_column"]] = ar_value


def parse_mixed_txt(mixed_path: str) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    if not os.path.isfile(mixed_path):
        raise FileNotFoundError(f"Mixed file not found: {mixed_path}")

    source_file = os.path.basename(mixed_path).replace("_mixed.txt", "")
    lines = load_lines_cells(mixed_path)

    row = make_empty_company_row()
    audit_rows = []
    seen_fields = set()

    for index, item in enumerate(lines):
        for cell in item["cells"]:
            spec = find_spec_by_fr_label(cell)

            if not spec:
                continue

            key = spec["key"]

            if key in seen_fields:
                continue

            special = spec.get("special")

            if special == "etat_registre":
                fr_value, confidence = extract_status_field(lines, index)
                ar_value = ""

            elif special == "oui_non":
                fr_value, confidence = extract_oui_non_field(lines, index)
                ar_value = ""

            elif special == "situation_fiscale":
                fr_value, confidence = extract_situation_fiscale(lines, index)
                ar_value = ""

            elif special == "arabic_name":
                fr_value = ""
                ar_value, confidence = extract_arabic_name_field(lines, index, spec)

            else:
                fr_value, ar_value, confidence = extract_regular_field(lines, index, spec)

            set_row_values(row, spec, fr_value, ar_value)

            if confidence < 1.0 or (not fr_value and not ar_value):
                audit_rows.append(
                    {
                        "source_file": source_file,
                        "identifiant_unique": row.get("identifiant_unique", ""),
                        "field_key": key,
                        "issue_type": "low_confidence" if confidence > 0 else "missing_value",
                        "message": f"confidence={confidence}",
                        "page": item.get("page", ""),
                        "line_number": item.get("line_number", ""),
                        "raw_line": item.get("raw_line", ""),
                    }
                )

            seen_fields.add(key)

    if not row.get("ar_nom_prenom"):
        fallback_name, fallback_confidence, fallback_item = fallback_extract_ar_nom_prenom(lines)

        if fallback_name:
            row["ar_nom_prenom"] = fallback_name

            if fallback_confidence < 1.0:
                audit_rows.append(
                    {
                        "source_file": source_file,
                        "identifiant_unique": row.get("identifiant_unique", ""),
                        "field_key": "nom_prenom",
                        "issue_type": "low_confidence",
                        "message": f"fallback extraction confidence={fallback_confidence}",
                        "page": fallback_item.get("page", ""),
                        "line_number": fallback_item.get("line_number", ""),
                        "raw_line": fallback_item.get("raw_line", ""),
                    }
                )

        else:
            audit_rows.append(
                {
                    "source_file": source_file,
                    "identifiant_unique": row.get("identifiant_unique", ""),
                    "field_key": "nom_prenom",
                    "issue_type": "missing_value",
                    "message": "Could not extract Arabic Nom et Prénom",
                    "page": "",
                    "line_number": "",
                    "raw_line": "",
                }
            )

    if not row.get("identifiant_unique"):
        if re.search(r"\d+[A-Z]?$", source_file, re.I):
            row["identifiant_unique"] = source_file
            row["extraction_status"] = "warning_id_from_filename"
        else:
            row["extraction_status"] = "warning_missing_id"

        audit_rows.append(
            {
                "source_file": source_file,
                "identifiant_unique": row.get("identifiant_unique", ""),
                "field_key": "identifiant_unique",
                "issue_type": "missing_required_field",
                "message": "N° Identifiant unique not found; used filename if possible",
                "page": "",
                "line_number": "",
                "raw_line": "",
            }
        )

    for audit in audit_rows:
        audit["identifiant_unique"] = row.get("identifiant_unique", "")

    return row, audit_rows


# =============================================================================
# CSV writing
# =============================================================================

def read_existing_ids(csv_path: str) -> set:
    ids = set()

    if not os.path.exists(csv_path):
        return ids

    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                value = r.get("identifiant_unique", "")

                if value:
                    ids.add(value)
    except Exception:
        pass

    return ids


def append_row_csv(csv_path: str, row: Dict[str, str], reset: bool = False) -> None:
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    if reset and os.path.exists(csv_path):
        os.remove(csv_path)

    existing_ids = read_existing_ids(csv_path)
    row_id = row.get("identifiant_unique", "")

    if row_id and row_id in existing_ids:
        print(f"[SKIP] ID already exists in CSV: {row_id}")
        return

    needs_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0

    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)

        if needs_header:
            writer.writeheader()

        writer.writerow({col: row.get(col, "") for col in OUTPUT_COLUMNS})


def append_audit_csv(csv_path: str, rows: List[Dict[str, str]], reset: bool = False) -> None:
    if not rows:
        return

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    if reset and os.path.exists(csv_path):
        os.remove(csv_path)

    needs_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0

    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_COLUMNS)

        if needs_header:
            writer.writeheader()

        for row in rows:
            writer.writerow({col: row.get(col, "") for col in AUDIT_COLUMNS})


# =============================================================================
# SQLite writing
# =============================================================================

def init_sqlite(db_path: str) -> None:
    company_cols = ", ".join(
        f"{c} TEXT PRIMARY KEY" if c == "identifiant_unique" else f"{c} TEXT"
        for c in OUTPUT_COLUMNS
    )

    audit_cols = ", ".join(f"{c} TEXT" for c in AUDIT_COLUMNS)

    with sqlite3.connect(db_path) as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS companies ({company_cols})")
        conn.execute(f"CREATE TABLE IF NOT EXISTS audit ({audit_cols})")
        conn.commit()


def upsert_company_sqlite(db_path: str, row: Dict[str, str]) -> None:
    init_sqlite(db_path)

    cols = OUTPUT_COLUMNS
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)

    update_sql = ", ".join(
        f"{c}=excluded.{c}" for c in cols if c != "identifiant_unique"
    )

    sql = (
        f"INSERT INTO companies ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT(identifiant_unique) DO UPDATE SET {update_sql}"
    )

    values = [row.get(c, "") for c in cols]

    with sqlite3.connect(db_path) as conn:
        conn.execute(sql, values)
        conn.commit()


def insert_audit_sqlite(db_path: str, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return

    init_sqlite(db_path)

    cols = AUDIT_COLUMNS
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)

    sql = f"INSERT INTO audit ({col_list}) VALUES ({placeholders})"
    values = [[row.get(c, "") for c in cols] for row in rows]

    with sqlite3.connect(db_path) as conn:
        conn.executemany(sql, values)
        conn.commit()


# =============================================================================
# CLI
# =============================================================================

def reset_outputs(output_dir: str) -> None:
    for filename in ["rne_companies.csv", "rne_audit.csv", "rne_companies.sqlite"]:
        path = os.path.join(output_dir, filename)

        if os.path.exists(path):
            os.remove(path)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("mixed", help="Path to output/<name>_mixed.txt")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--no-sqlite", action="store_true")

    args = parser.parse_args()

    mixed_path = args.mixed
    output_dir = args.output_dir or os.path.dirname(mixed_path) or "."

    os.makedirs(output_dir, exist_ok=True)

    if args.reset:
        reset_outputs(output_dir)

    companies_csv = os.path.join(output_dir, "rne_companies.csv")
    audit_csv = os.path.join(output_dir, "rne_audit.csv")
    sqlite_db = os.path.join(output_dir, "rne_companies.sqlite")

    row, audit_rows = parse_mixed_txt(mixed_path)
    row = enrich_missing_arabic_from_long_csv(row, mixed_path, output_dir)

    append_row_csv(companies_csv, row, reset=False)
    append_audit_csv(audit_csv, audit_rows, reset=False)

    if not args.no_sqlite:
        upsert_company_sqlite(sqlite_db, row)
        insert_audit_sqlite(sqlite_db, audit_rows)

    print("[OK] Parsed:", mixed_path)
    print("[OK] ID:", row.get("identifiant_unique", ""))
    print("[OK] ar_nom_prenom:", row.get("ar_nom_prenom", "(empty)"))
    print("[OK] CSV:", companies_csv)
    print("[OK] Audit:", audit_csv)

    if not args.no_sqlite:
        print("[OK] SQLite:", sqlite_db)


if __name__ == "__main__":
    main()