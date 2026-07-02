import re
import pandas as pd

from segmentation.text_cleaner import normalize_text, normalize_text_primary


def find_column(df, expected_column):
    normalized_columns = {
        normalize_text_primary(column): column
        for column in df.columns
    }
    expected_clean = normalize_text_primary(expected_column)
    if expected_clean in normalized_columns:
        return normalized_columns[expected_clean]
    return None


def is_fragmented_activity(text) -> bool:
    if pd.isna(text):
        return False
    t = str(text).strip()
    if not t:
        return False
    if re.match(r"^[a-z]", t):
        return True
    if t.endswith(")"):
        return True
    return False


def load_companies(
    csv_path,
    activity_column="fr_activite_principale",
    arabic_activity_column="ar_activite_principale"
):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    fr_col = find_column(df, activity_column)
    ar_col = find_column(df, arabic_activity_column)

    if fr_col is None and ar_col is None:
        raise ValueError(
            f"No activity column found. Expected '{activity_column}' or '{arabic_activity_column}'. "
            f"Available columns are: {list(df.columns)}"
        )

    def combine_activity(row):
        parts = []
        if fr_col is not None and pd.notna(row[fr_col]) and str(row[fr_col]).strip():
            parts.append(str(row[fr_col]).strip())
        if ar_col is not None and pd.notna(row[ar_col]) and str(row[ar_col]).strip():
            parts.append(str(row[ar_col]).strip())
        return " | ".join(parts)

    df["activity_raw_combined"] = df.apply(combine_activity, axis=1)
    df["activity_clean"] = df["activity_raw_combined"].apply(normalize_text)
    df["activity_clean_primary"] = df["activity_raw_combined"].apply(normalize_text_primary)

    if fr_col is not None:
        df["activity_is_fragmented"] = df[fr_col].apply(is_fragmented_activity)
    else:
        df["activity_is_fragmented"] = False

    detected_cols = {
        "fr_activity_column": fr_col,
        "ar_activity_column": ar_col
    }

    return df, detected_cols