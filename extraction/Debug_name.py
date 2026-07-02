"""
DEBUG — Print every cell from the mixed txt,
focusing on the Nom et Prénom / الإسم و اللقب row.

Usage:
    python src/debug_name.py output/1658358N_mixed.txt
    python src/debug_name.py output/1658358N_mixed.txt > debug_name_output.txt
"""

import sys
import os
import re
import unicodedata

ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)


def clean_text(s) -> str:
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def repr_cell(s: str) -> str:
    visible = repr(s)
    codepoints = " ".join(f"U+{ord(c):04X}({c})" for c in s if c.strip())
    return f"{visible}\n       codepoints: {codepoints}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "output/1658358N_mixed.txt"

    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        raw_lines = [line.rstrip("\n") for line in f]

    print("=" * 70)
    print(f"File: {path}  ({len(raw_lines)} lines total)")
    print("=" * 70)

    print("\n>>> ALL LINES CONTAINING ARABIC:\n")

    for i, line in enumerate(raw_lines, 1):
        if ARABIC_RE.search(line):
            cells = [clean_text(c) for c in line.split("|")]

            print(f"  Line {i:4d}: {repr(line)}")

            for j, cell in enumerate(cells):
                if cell:
                    print(f"    cell[{j}]: {repr_cell(cell)}")

            print()

    print("\n>>> LINES MATCHING 'Nom' OR 'اللقب' OR 'الإسم':\n")

    keywords = ["nom", "اللقب", "الإسم", "اإلسم", "لقب", "اسم"]

    for i, line in enumerate(raw_lines, 1):
        line_lower = line.lower()

        if any(k.lower() in line_lower for k in keywords):
            cells = [clean_text(c) for c in line.split("|")]

            print(f"  Line {i:4d}: {repr(line)}")

            for j, cell in enumerate(cells):
                print(f"    cell[{j}]: {repr_cell(cell)}")

            print()

    print("\n>>> NORMALIZED ARABIC CELLS:\n")

    def normalize_arabic(s):
        s = clean_text(s)
        s = unicodedata.normalize("NFKC", s)
        s = re.sub(r"[إأآٱاٲٳ]", "ا", s)
        s = s.replace("ى", "ي")
        s = s.replace("ؤ", "و")
        s = s.replace("ئ", "ي")
        s = re.sub(r"[\u064B-\u065F]", "", s)
        s = s.replace("\u0640", "")
        return s.strip(" :")

    seen = set()

    for line in raw_lines:
        if not ARABIC_RE.search(line):
            continue

        cells = [clean_text(c) for c in line.split("|")]

        for cell in cells:
            if cell and ARABIC_RE.search(cell) and cell not in seen:
                seen.add(cell)
                norm = normalize_arabic(cell)

                print(f"  raw   : {repr(cell)}")
                print(f"  norm  : {repr(norm)}")
                print()


if __name__ == "__main__":
    main()