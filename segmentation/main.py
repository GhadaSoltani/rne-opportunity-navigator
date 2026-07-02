"""
segmentation/main.py
====================
Can be run directly:
    python -m segmentation.main

Or called from pipeline/runner.py:
    from segmentation.main import run_segmentation
    run_segmentation(input_csv="data/input/rne_companies.csv")
"""

import logging
from pathlib import Path

import pandas as pd
from tqdm import tqdm

logger = logging.getLogger(__name__)

from segmentation.config import (
    INPUT_CSV,
    OUTPUT_CSV,
    REVIEW_CSV,
    AUDIT_CSV,
    EMPTY_ACTIVITY_CSV,
    LOW_EMBEDDING_CSV,
    TAXONOMY_PATH,
    VALIDATED_EXAMPLES_PATH,
    RAG_KNOWLEDGE_PATH,
    ACTIVITY_COLUMN,
    AR_ACTIVITY_COLUMN,
)

from segmentation.data_loader import load_companies
from segmentation.taxonomy_classifier import load_taxonomy, classify_with_taxonomy

from segmentation.validated_examples_classifier import (
    load_validated_examples_with_patterns,
    classify_with_validated_examples,
)

from segmentation.embedding_classifier import (
    load_embedding_reference,
    load_embedding_model,
    build_reference_embeddings,
    classify_with_embeddings,
)

from segmentation.rag_retriever import (
    RAGRetriever,
    classify_with_rag,
)

from segmentation.llm_validator import (
    should_use_llm,
    validate_with_llm,
)

from segmentation.export_results import save_outputs


def run_segmentation(input_csv: str | Path | None = None) -> dict:
    """
    Run the full segmentation pipeline.

    Args:
        input_csv:
            Path to rne_companies.csv.
            Defaults to INPUT_CSV from config if not provided.

    Returns:
        A summary dict with counts and output paths.
    """

    csv_path = Path(input_csv) if input_csv else INPUT_CSV

    logger.info("Loading company CSV...")
    df, detected_columns = load_companies(
        csv_path,
        ACTIVITY_COLUMN,
        AR_ACTIVITY_COLUMN,
    )

    logger.info("Detected French activity column : %s", detected_columns["fr_activity_column"])
    logger.info("Detected Arabic activity column : %s", detected_columns["ar_activity_column"])

    fragmented_count = df["activity_is_fragmented"].sum()
    logger.info("Fragmented French activity entries detected: %d", fragmented_count)

    logger.info("Loading validated examples...")
    validated_examples, partial_patterns = load_validated_examples_with_patterns(
        VALIDATED_EXAMPLES_PATH
    )
    logger.info("Loaded validated examples        : %d", len(validated_examples))
    logger.info("Pre-compiled partial patterns    : %d", len(partial_patterns))

    logger.info("Loading embedding reference examples...")
    embedding_reference_df = load_embedding_reference(VALIDATED_EXAMPLES_PATH)
    logger.info("Loaded embedding reference rows  : %d", len(embedding_reference_df))

    logger.info("Loading embedding model...")
    embedding_model = load_embedding_model()

    logger.info("Building reference embeddings...")
    reference_embeddings = build_reference_embeddings(
        embedding_model,
        embedding_reference_df,
    )

    logger.info("Loading sector taxonomy...")
    taxonomy = load_taxonomy(TAXONOMY_PATH)

    logger.info("Loading RAG retriever...")
    if not RAG_KNOWLEDGE_PATH.exists():
        raise FileNotFoundError(
            "RAG knowledge base not found. Run this first:\n"
            "python run.py --skip-extraction --rebuild-rag"
        )

    rag_retriever = RAGRetriever(
        knowledge_path=RAG_KNOWLEDGE_PATH,
        top_k=5,
    )

    results = []
    low_embedding_rows = []

    validated_exact_count    = 0
    validated_partial_count  = 0
    taxonomy_count           = 0
    embedding_count          = 0
    embedding_low_count      = 0
    rag_count                = 0
    llm_count                = 0
    empty_count              = 0
    fallback_count           = 0
    fragmented_routed_count  = 0

    logger.info("Classifying companies...")

    for row_index, (
        activity_clean_primary,
        activity_clean,
        activity_raw,
        is_fragmented,
    ) in tqdm(
        enumerate(zip(
            df["activity_clean_primary"],
            df["activity_clean"],
            df["activity_raw_combined"],
            df["activity_is_fragmented"],
        )),
        total=len(df),
    ):
        # ── 1. Validated examples ────────────────────────────────────────────
        validated_result  = classify_with_validated_examples(
            activity_clean_primary,
            validated_examples,
            partial_patterns,
        )

        validated_candidate = None

        if validated_result is not None:
            if validated_result["method"] == "validated_example_exact":
                results.append(validated_result)
                validated_exact_count += 1
                continue
            else:
                validated_candidate = validated_result
                validated_partial_count += 1

        # ── 2. Taxonomy rule ─────────────────────────────────────────────────
        taxonomy_result = classify_with_taxonomy(
            activity_clean_primary,
            taxonomy,
        )

        if taxonomy_result["method"] == "empty_activity":
            results.append(taxonomy_result)
            empty_count += 1
            continue

        if is_fragmented and taxonomy_result["needs_review"]:
            taxonomy_result["confidence"] = min(taxonomy_result["confidence"], 0.55)
            taxonomy_result["matched_keywords"] = taxonomy_result["matched_keywords"] + [
                "warning: fragmented_french_activity"
            ]
            fragmented_routed_count += 1

        if taxonomy_result["needs_review"] is False:
            results.append(taxonomy_result)
            taxonomy_count += 1
            continue

        # ── 3. Embedding similarity ──────────────────────────────────────────
        embedding_result, low_score_info = classify_with_embeddings(
            activity_clean=activity_clean,
            model=embedding_model,
            reference_df=embedding_reference_df,
            reference_embeddings=reference_embeddings,
            accept_threshold=0.90,
            review_threshold=0.85,
        )

        if low_score_info is not None and low_score_info["embedding_score"] < 0.85:
            original_row = df.iloc[row_index].to_dict()
            original_row["embedding_score"]         = low_score_info["embedding_score"]
            original_row["embedding_best_match"]    = low_score_info["embedding_best_match"]
            original_row["embedding_best_category"] = low_score_info["embedding_best_category"]
            original_row["taxonomy_category"]       = taxonomy_result["category"]
            original_row["taxonomy_confidence"]     = taxonomy_result["confidence"]
            original_row["taxonomy_method"]         = taxonomy_result["method"]
            low_embedding_rows.append(original_row)
            embedding_low_count += 1

        if embedding_result is not None and embedding_result["needs_review"] is False:
            results.append(embedding_result)
            embedding_count += 1
            continue

        # ── 4. RAG similarity ────────────────────────────────────────────────
        retrieved_items = rag_retriever.retrieve(activity_raw)

        rag_result = classify_with_rag(
            retrieved_items,
            high_threshold=0.82,
            medium_threshold=0.65,
        )

        if rag_result is not None and rag_result["needs_review"] is False:
            results.append(rag_result)
            rag_count += 1
            continue

        # ── 5. Best uncertain candidate ──────────────────────────────────────
        if rag_result is not None:
            candidate_result = rag_result
        elif embedding_result is not None:
            candidate_result = embedding_result
        elif taxonomy_result["method"] not in ("empty_activity", "no_rule_match"):
            candidate_result = taxonomy_result
        elif validated_candidate is not None:
            candidate_result = validated_candidate
        else:
            candidate_result = taxonomy_result

        # ── 6. LLM verification ──────────────────────────────────────────────
        if should_use_llm(candidate_result):
            llm_result = validate_with_llm(
                activity_text=activity_raw,
                current_result=candidate_result,
            )
            results.append(llm_result)
            llm_count += 1
            continue

        # ── 7. Fallback ──────────────────────────────────────────────────────
        results.append(candidate_result)
        fallback_count += 1

    # ── Write results to dataframe ───────────────────────────────────────────
    df["category"]         = [r["category"]   for r in results]
    df["confidence"]       = [r["confidence"] for r in results]
    df["method"]           = [r["method"]     for r in results]
    df["matched_keywords"] = [", ".join(r["matched_keywords"]) for r in results]
    df["blocked_keywords"] = [", ".join(r["blocked_keywords"]) for r in results]
    df["needs_review"]     = [r["needs_review"] for r in results]

    logger.info("Saving output files...")

    save_outputs(
        df=df,
        output_csv=OUTPUT_CSV,
        review_csv=REVIEW_CSV,
        audit_csv=AUDIT_CSV,
        empty_activity_csv=EMPTY_ACTIVITY_CSV,
        activity_column="activity_raw_combined",
    )

    # ── Save low embedding score rows ────────────────────────────────────────
    LOW_EMBEDDING_CSV.parent.mkdir(parents=True, exist_ok=True)

    if low_embedding_rows:
        low_df = pd.DataFrame(low_embedding_rows)
        useful_cols = [
            "activity_raw_combined", "activity_clean",
            "embedding_score", "embedding_best_match", "embedding_best_category",
            "taxonomy_category", "taxonomy_confidence", "taxonomy_method",
        ]
        low_df[[c for c in useful_cols if c in low_df.columns]].to_csv(
            LOW_EMBEDDING_CSV, index=False, encoding="utf-8-sig"
        )
    else:
        pd.DataFrame(columns=[
            "activity_raw_combined", "activity_clean",
            "embedding_score", "embedding_best_match", "embedding_best_category",
            "taxonomy_category", "taxonomy_confidence", "taxonomy_method",
        ]).to_csv(LOW_EMBEDDING_CSV, index=False, encoding="utf-8-sig")

    # ── Summary ──────────────────────────────────────────────────────────────
    real_review_count   = ((df["needs_review"] == True) & (df["method"] != "empty_activity")).sum()
    empty_activity_count = (df["method"] == "empty_activity").sum()

    summary = {
        "total_rows":              len(df),
        "validated_exact":         validated_exact_count,
        "validated_partial":       validated_partial_count,
        "taxonomy_rules":          taxonomy_count,
        "embedding_accepted":      embedding_count,
        "embedding_low":           embedding_low_count,
        "rag_similarity":          rag_count,
        "llm_verification":        llm_count,
        "empty_activities":        empty_count,
        "fallback":                fallback_count,
        "fragmented_routed":       fragmented_routed_count,
        "needs_review":            int(real_review_count),
        "empty_activity_rows":     int(empty_activity_count),
        "category_distribution":   df["category"].value_counts().to_dict(),
        "method_distribution":     df["method"].value_counts().to_dict(),
        "output_csv":              str(OUTPUT_CSV),
        "review_csv":              str(REVIEW_CSV),
        "audit_csv":               str(AUDIT_CSV),
    }

    logger.info("Pipeline step counts:")
    logger.info("  Validated examples (exact)  : %d", validated_exact_count)
    logger.info("  Validated examples (partial): %d", validated_partial_count)
    logger.info("  Taxonomy rules              : %d", taxonomy_count)
    logger.info("  Embedding accepted          : %d", embedding_count)
    logger.info("  Embedding low score         : %d", embedding_low_count)
    logger.info("  RAG similarity              : %d", rag_count)
    logger.info("  LLM verification            : %d", llm_count)
    logger.info("  Empty activities            : %d", empty_count)
    logger.info("  Fallback                    : %d", fallback_count)
    logger.info("  Fragmented routed           : %d", fragmented_routed_count)
    logger.info("Rows needing review          : %d", real_review_count)
    logger.info("Empty activity rows          : %d", empty_activity_count)
    logger.info("Category distribution:\n%s", df["category"].value_counts().to_string())
    logger.info("Classification methods:\n%s", df["method"].value_counts().to_string())

    return summary


if __name__ == "__main__":
    run_segmentation()