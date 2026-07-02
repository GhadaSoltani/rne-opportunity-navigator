"""
STEP 3 — Extract structured fields from the French and Arabic txt files
          using the same table-aware checkbox/KV logic as the camelot-based code.

Output: extracted_data.csv  +  extracted_data.db (SQLite)

Each output row has:
  - All French fields  (from _french.txt)
  - All Arabic fields  (from _arabic.txt)

Usage:
    # single pair
    python step3_to_csv.py output/708307Y_french.txt output/708307Y_arabic.txt

    # whole folder
    python step3_to_csv.py --folder output/
"""

import os
import re
import csv
import glob
import sqlite3
import argparse
import logging

logger = logging.getLogger(__name__)

# ── character patterns ────────────────────────────────────────────────────────

ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\u0660-\u0669\u06F0-\u06F9]+"
)
LATIN_NOISE = re.compile(r"[A-Za-z0-9\s@.:+/\-|]+")
MULTI_WS    = re.compile(r"\s{2,}")
CELL_SEP    = " | "

# ── checkbox / checked-cell detection (same logic as camelot code) ────────────

CHECKED_GLYPHS = {
    "☒", "☑", "✓", "✔", "✅", "■", "●", "◼", "✔︎",
    "[x]", "(x)", "x", "X", "\uf0fe", "\uf0fd", "\uf052", "\uf0fc", "\uf0b7",
}


def looks_like_checked(cell: str) -> int:
    """
    Score how much a cell looks like a ticked checkbox.
    Returns 0 (not checked) → 10 (definitely checked).
    Mirrors the camelot-based looks_like_checked_cell logic exactly.
    """
    c = cell.strip()
    if not c:
        return 0
    if c in CHECKED_GLYPHS:
        return 10
    if len(c) <= 2 and not re.fullmatch(r"[A-Za-zÀ-ÿ]{1,2}", c):
        return 6
    if re.fullmatch(r"[^\w\s]+", c):
        return 5
    if re.fullmatch(r"\d", c):
        return 2
    return 0


# ── low-level helpers ─────────────────────────────────────────────────────────

def clean_cell(s) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\xa0", " ")
    s = ARABIC_RE.sub(" ", s)           # strip Arabic from French cells
    return MULTI_WS.sub(" ", s).strip()


def clean_arabic_cell(s) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[A-Za-z0-9@.:+/\-]+", " ", s)   # strip Latin from Arabic cells
    return MULTI_WS.sub(" ", s).strip()


def read_table_rows(path: str, arabic: bool = False) -> list[list[str]]:
    """
    Read a language-split txt file and return a list of rows.
    Each row is a list of cell strings (split on CELL_SEP).
    Structural markers (PAGE / TABLE / ===) are skipped.
    """
    rows: list[list[str]] = []
    cleaner = clean_arabic_cell if arabic else clean_cell
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.rstrip("\n")
                if (not line or line.startswith("===")
                        or line.startswith("PAGE ")
                        or line.startswith("--- TABLE")):
                    continue
                cells = [cleaner(c) for c in line.split(CELL_SEP)]
                if any(c for c in cells):
                    rows.append(cells)
    except FileNotFoundError:
        logger.warning(f"File not found: {path}")
    return rows


# ── KV extraction with checkbox block handling ────────────────────────────────

def after_label(rows: list[list[str]], label_re, n_rows: int = 4) -> str:
    """
    Find the first row whose first cell matches label_re,
    then return the joined non-empty cells of the NEXT row.
    """
    for i, row in enumerate(rows):
        if row and re.search(label_re, row[0], re.I):
            for j in range(i + 1, min(i + 1 + n_rows, len(rows))):
                value = " ".join(c for c in rows[j] if c).strip(" |-")
                if value and not re.search(label_re, value, re.I):
                    return value
    return ""


def extract_checkbox_block(
    rows: list[list[str]],
    start_idx: int,
    options: list[str],
    lookahead: int = 8,
) -> tuple[str, float, int]:
    """
    Starting from start_idx+1, scan up to `lookahead` rows for option labels
    and their associated checkbox cells. Return (selected_value, confidence, next_row_idx).

    This is the exact same scoring logic as the camelot code's Etat/Leasing blocks.
    """
    best_value = ""
    best_score = -1
    last_idx   = start_idx

    for j in range(start_idx + 1, min(len(rows), start_idx + 1 + lookahead)):
        row       = rows[j]
        first_col = row[0] if row else ""

        # Stop if we've left the block (new unrelated label appears)
        if first_col and not any(
            first_col.lower() == opt.lower() for opt in options
        ) and first_col.lower() not in ("oui", "non", ""):
            # also stop on date-like or major section labels
            if re.search(r"^(date|type|capital|durée|adresse|activit)", first_col, re.I):
                break

        # detect which option this row names
        matched_opt = next(
            (opt for opt in options if first_col.lower() == opt.lower()), None
        )
        if matched_opt is None and first_col.lower() in ("oui", "non"):
            matched_opt = first_col.capitalize()

        if matched_opt is None:
            continue

        # score all non-label cells for checkbox appearance
        score = max(
            (looks_like_checked(c) for c in row[1:] if c),
            default=0,
        )
        last_idx = j

        if score > best_score:
            best_score = score
            best_value = matched_opt

    conf = 1.0 if best_score >= 5 else (0.6 if best_score > 0 else 0.0)
    return best_value, conf, last_idx + 1


# ── French field extraction ───────────────────────────────────────────────────

def extract_french_fields(french_path: str) -> dict:
    rows = read_table_rows(french_path, arabic=False)
    g    = lambda pattern, n=4: after_label(rows, pattern, n)

    rec: dict = {}
    rec["identifiant_unique"]       = g(r"N°\s*Identifiant\s*unique")
    rec["denomination"]             = g(r"^Dénomination$")
    rec["nom_commercial"]           = g(r"^Nom\s*commercial$")
    rec["forme_juridique"]          = g(r"^Forme\s*[Jj]uridique$")
    rec["capital"]                  = g(r"^Capital$")
    rec["duree"]                    = g(r"^Durée$")
    rec["date_debut_activite"]      = g(r"Date\s*début\s*d.activité")
    rec["date_immatriculation"]     = g(r"Date\s*d.immatriculation")
    rec["activite_principale"]      = g(r"Activité\s*principale\s*[:\-]?$")
    rec["code_activite_principale"] = g(r"Code\s*activité\s*principale\s*[:\-]?$")
    rec["activite_secondaire"]      = g(r"Activité\s*secondaire\s*[:\-]?$")
    rec["activite_secondaire"]      = rec["activite_secondaire"].replace("null", "").strip(" -")

    # Adresse: may span two rows
    rec["adresse"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"^Adresse$", row[0], re.I):
            parts = []
            for j in range(i + 1, min(i + 3, len(rows))):
                v = " ".join(c for c in rows[j] if c).strip(" |-")
                if v and not re.search(r"^(Capital|Durée|Date)", v, re.I):
                    parts.append(v)
            rec["adresse"] = ", ".join(parts)
            break

    # ── Etat du registre — checkbox block ─────────────────────────────────────
    rec["etat_registre"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"[ée]tat\s*du\s*registre", row[0], re.I):
            opts  = ["Actif", "Suspension provisoire", "Registre radié"]
            val, conf, _ = extract_checkbox_block(rows, i, opts, lookahead=8)
            rec["etat_registre"] = val
            break
    # fallback: plain text scan
    if not rec["etat_registre"]:
        full_text = " ".join(" ".join(r) for r in rows)
        if re.search(r"\bActif\b", full_text):
            rec["etat_registre"] = "Actif"
        elif re.search(r"Suspension\s*provisoire", full_text):
            rec["etat_registre"] = "Suspension provisoire"
        elif re.search(r"Registre\s*radi[ée]", full_text, re.I):
            rec["etat_registre"] = "Radié"

    # ── Nantissement — checkbox block ─────────────────────────────────────────
    rec["nantissement"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"^Nantissement$", row[0], re.I):
            val, conf, _ = extract_checkbox_block(rows, i, ["Oui", "Non"], lookahead=6)
            rec["nantissement"] = val
            break

    # ── Leasing — checkbox block ──────────────────────────────────────────────
    rec["leasing"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"^Leasing$", row[0], re.I):
            val, conf, _ = extract_checkbox_block(rows, i, ["Oui", "Non"], lookahead=6)
            rec["leasing"] = val
            break

    # ── Situation fiscale — checkbox block ────────────────────────────────────
    rec["situation_fiscale"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"situation\s*fiscale", row[0], re.I):
            opts = [
                "Régularisée",
                "En défaut de plus 12 mois",
                "En défaut de plus de 24 mois",
            ]
            val, conf, _ = extract_checkbox_block(rows, i, opts, lookahead=8)
            rec["situation_fiscale"] = val
            break
    if not rec["situation_fiscale"]:
        full_text = " ".join(" ".join(r) for r in rows)
        if re.search(r"En\s*défaut\s*de\s*plus\s*de\s*24\s*mois", full_text, re.I):
            rec["situation_fiscale"] = "En défaut > 24 mois"
        elif re.search(r"En\s*défaut\s*de\s*plus\s*12\s*mois", full_text, re.I):
            rec["situation_fiscale"] = "En défaut 12-24 mois"
        else:
            rec["situation_fiscale"] = "Régularisée"

    # ── Dirigeants table — Nom et Prénom (French side) ────────────────────────
    rec["nom_prenom_dirigeant_fr"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"nom\s*et\s*pr[ée]nom", row[0], re.I):
            # value may be in the same row (col 1+) or next row
            inline = " ".join(c for c in row[1:] if c).strip()
            if inline:
                rec["nom_prenom_dirigeant_fr"] = inline
            else:
                val = after_label(rows, r"nom\s*et\s*pr[ée]nom", 2)
                rec["nom_prenom_dirigeant_fr"] = val
            break

    return rec


# ── Arabic field extraction ───────────────────────────────────────────────────

AR_SKIP_VALUES = {
    "المسيرون", "اإلسم و اللقب", "الصفة", "الجنسية", "الرهون", "اإليجار",
}


def extract_arabic_fields(arabic_path: str) -> dict:
    rows = read_table_rows(arabic_path, arabic=True)

    rec: dict = {}

    # helper: find value on next non-empty row after a label
    def ar_after(label_re, n=4):
        for i, row in enumerate(rows):
            if row and re.search(label_re, row[0]):
                for j in range(i + 1, min(i + 1 + n, len(rows))):
                    v = " ".join(c for c in rows[j] if c).strip()
                    if v and v not in AR_SKIP_VALUES and not re.search(label_re, v):
                        return v
        return ""

    # Standard Arabic fields (mirror the French fields)
    rec["ar_denomination"]        = ar_after(r"التسمية|الإسم التجاري")
    rec["ar_nom_commercial"]      = ar_after(r"الاسم\s*التجاري")
    rec["ar_forme_juridique"]     = ar_after(r"الشكل\s*القانوني")
    rec["ar_adresse"]             = ar_after(r"العنوان")
    rec["ar_activite_principale"] = ar_after(r"النشاط\s*الرئيسي")
    rec["ar_activite_secondaire"] = ar_after(r"النشاط\s*الثانوي")

    # Dirigeant name — most reliable field in the Arabic side
    rec["ar_nom_prenom_dirigeant"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"اإلسم\s*و\s*اللقب|الاسم\s*و\s*اللقب", row[0]):
            # try inline first (same row, other columns)
            inline_parts = [c for c in row[1:] if c and c not in AR_SKIP_VALUES]
            inline = " ".join(inline_parts).strip()
            if inline and ARABIC_RE.search(inline) and 2 <= len(inline.split()) <= 6:
                rec["ar_nom_prenom_dirigeant"] = inline
                break
            # fallback: next rows
            for j in range(i + 1, min(i + 4, len(rows))):
                candidate = " ".join(c for c in rows[j] if c).strip()
                if (candidate
                        and ARABIC_RE.search(candidate)
                        and 2 <= len(candidate.split()) <= 6
                        and candidate not in AR_SKIP_VALUES
                        and not re.search(r"\d", candidate)):
                    rec["ar_nom_prenom_dirigeant"] = candidate
                    break
            break

    # Etat du registre — Arabic checkbox block
    rec["ar_etat_registre"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"حالة\s*السجل", row[0]):
            opts = ["مباشر", "إيقاف مؤقت", "سجل ملغى"]
            val, conf, _ = extract_checkbox_block(rows, i, opts, lookahead=8)
            rec["ar_etat_registre"] = val
            break

    # Nantissement / Leasing — Arabic checkbox blocks
    rec["ar_nantissement"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"الرهون", row[0]):
            val, conf, _ = extract_checkbox_block(rows, i, ["نعم", "لا"], lookahead=6)
            rec["ar_nantissement"] = val
            break

    rec["ar_leasing"] = ""
    for i, row in enumerate(rows):
        if row and re.search(r"اإليجار\s*التمويلي|الإيجار\s*التمويلي", row[0]):
            val, conf, _ = extract_checkbox_block(rows, i, ["نعم", "لا"], lookahead=6)
            rec["ar_leasing"] = val
            break

    return rec


# ── CSV + SQLite output ───────────────────────────────────────────────────────

FRENCH_FIELDS = [
    "identifiant_unique",
    "denomination",
    "nom_commercial",
    "forme_juridique",
    "adresse",
    "capital",
    "duree",
    "date_debut_activite",
    "date_immatriculation",
    "activite_principale",
    "code_activite_principale",
    "activite_secondaire",
    "etat_registre",
    "nantissement",
    "leasing",
    "situation_fiscale",
    "nom_prenom_dirigeant_fr",
]

ARABIC_FIELDS = [
    "ar_denomination",
    "ar_nom_commercial",
    "ar_forme_juridique",
    "ar_adresse",
    "ar_activite_principale",
    "ar_activite_secondaire",
    "ar_etat_registre",
    "ar_nantissement",
    "ar_leasing",
    "ar_nom_prenom_dirigeant",
]

FIELDNAMES = ["source_file"] + FRENCH_FIELDS + ARABIC_FIELDS


def write_sqlite(rows: list[dict], db_path: str) -> None:
    cols_def = ", ".join(
        f'"{f}" TEXT' for f in FIELDNAMES
    )
    placeholders = ", ".join("?" for _ in FIELDNAMES)
    col_names    = ", ".join(f'"{f}"' for f in FIELDNAMES)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute(f"CREATE TABLE IF NOT EXISTS records ({cols_def})")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_source "
        "ON records(source_file)"
    )
    for row in rows:
        values = [row.get(f, "") for f in FIELDNAMES]
        cur.execute(
            f"INSERT OR REPLACE INTO records ({col_names}) VALUES ({placeholders})",
            values,
        )
    con.commit()
    con.close()


def process_pair(
    french_path: str,
    arabic_path: str,
    csv_path: str,
    db_path: str,
    append: bool = False,
) -> dict:
    source = os.path.basename(french_path).replace("_french.txt", "")

    fr_fields = extract_french_fields(french_path)
    ar_fields = extract_arabic_fields(arabic_path)

    row = {"source_file": source}
    row.update(fr_fields)
    row.update(ar_fields)

    # ── CSV ──────────────────────────────────────────────────────────────────
    mode        = "a" if append else "w"
    needs_hdr   = (not append) or (not os.path.exists(csv_path))
    with open(csv_path, mode, encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if needs_hdr:
            w.writeheader()
        w.writerow(row)

    # ── SQLite ────────────────────────────────────────────────────────────────
    write_sqlite([row], db_path)

    logger.info(f"[✓] {source}")
    return row


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Step 3: extract fields from French+Arabic txt → CSV + SQLite"
    )
    p.add_argument("french", nargs="?", help="Path to _french.txt")
    p.add_argument("arabic", nargs="?", help="Path to _arabic.txt")
    p.add_argument("--folder", help="Process all *_french.txt files in a folder")
    a = p.parse_args()

    if a.folder:
        french_files = sorted(glob.glob(os.path.join(a.folder, "*_french.txt")))
        if not french_files:
            logger.error(f"No *_french.txt files found in: {a.folder}")
            return
        csv_path = os.path.join(a.folder, "extracted_data.csv")
        db_path  = os.path.join(a.folder, "extracted_data.db")
        for i, fr in enumerate(french_files):
            ar = fr.replace("_french.txt", "_arabic.txt")
            if not os.path.exists(ar):
                logger.warning(f"Missing arabic file for: {fr}")
                continue
            process_pair(fr, ar, csv_path, db_path, append=(i > 0))
        logger.info(f"\nCSV  → {csv_path}")
        logger.info(f"DB   → {db_path}")

    else:
        fr = a.french or "output/708307Y_french.txt"
        ar = a.arabic or "output/708307Y_arabic.txt"
        out_dir  = os.path.dirname(fr) or "."
        csv_path = os.path.join(out_dir, "extracted_data.csv")
        db_path  = os.path.join(out_dir, "extracted_data.db")
        row = process_pair(fr, ar, csv_path, db_path)
        print("\n--- Extracted fields ---")
        for k, v in row.items():
            print(f"  {k:40s}: {v}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()