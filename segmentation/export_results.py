import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def save_outputs(df, output_csv, review_csv, audit_csv, empty_activity_csv, activity_column):
    output_csv         = Path(output_csv)
    review_csv         = Path(review_csv)
    audit_csv          = Path(audit_csv)
    empty_activity_csv = Path(empty_activity_csv)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    review_csv.parent.mkdir(parents=True, exist_ok=True)
    audit_csv.parent.mkdir(parents=True, exist_ok=True)
    empty_activity_csv.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    empty_df = df[df["method"] == "empty_activity"].copy()
    empty_df.to_csv(empty_activity_csv, index=False, encoding="utf-8-sig")

    review_df = df[
        (df["needs_review"] == True) &
        (df["method"] != "empty_activity")
    ].copy()
    review_df.to_csv(review_csv, index=False, encoding="utf-8-sig")

    audit_columns = [
        activity_column, "activity_clean", "category", "confidence",
        "method", "matched_keywords", "blocked_keywords", "needs_review",
    ]
    existing_columns = [col for col in audit_columns if col in df.columns]
    df[existing_columns].to_csv(audit_csv, index=False, encoding="utf-8-sig")

    logger.info("Empty activities saved: %d", len(empty_df))
    logger.info("Review-needed rows without empty activities: %d", len(review_df))