import pandas as pd
import numpy as np

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from segmentation.text_cleaner import normalize_text
from segmentation.config import EMBEDDING_MODEL_NAME


def load_embedding_reference(validated_examples_path):
    try:
        df = pd.read_csv(validated_examples_path, encoding="utf-8-sig")
    except FileNotFoundError:
        return pd.DataFrame(columns=["activity", "activity_clean", "category"])

    if df.empty:
        return pd.DataFrame(columns=["activity", "activity_clean", "category"])

    df = df.dropna(subset=["activity", "category"]).copy()
    df["activity_clean"] = df["activity"].apply(normalize_text)
    df["category"] = df["category"].astype(str).str.strip()
    df = df[df["activity_clean"] != ""]

    return df[["activity", "activity_clean", "category"]].drop_duplicates()


def load_embedding_model():
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return model


def build_reference_embeddings(model, reference_df):
    if reference_df.empty:
        return None

    texts = reference_df["activity_clean"].tolist()
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings


def get_embedding_best_match(activity_clean, model, reference_df, reference_embeddings):
    if not activity_clean:
        return None
    if reference_df.empty or reference_embeddings is None:
        return None

    query_embedding = model.encode(
        [activity_clean],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    similarities = cosine_similarity(query_embedding, reference_embeddings)[0]
    best_index = int(np.argmax(similarities))
    best_similarity = float(similarities[best_index])
    best_row = reference_df.iloc[best_index]

    return {
        "best_similarity": round(best_similarity, 3),
        "best_match_activity": best_row["activity"],
        "best_match_category": best_row["category"],
    }


def classify_with_embeddings(
    activity_clean,
    model,
    reference_df,
    reference_embeddings,
    accept_threshold=0.90,
    review_threshold=0.85,
):
    best_match = get_embedding_best_match(
        activity_clean=activity_clean,
        model=model,
        reference_df=reference_df,
        reference_embeddings=reference_embeddings,
    )

    if best_match is None:
        return None, None

    best_similarity = best_match["best_similarity"]
    predicted_category = best_match["best_match_category"]
    best_match_activity = best_match["best_match_activity"]

    low_score_info = {
        "embedding_score": best_similarity,
        "embedding_best_match": best_match_activity,
        "embedding_best_category": predicted_category,
    }

    if best_similarity < review_threshold:
        return None, low_score_info

    needs_review = best_similarity < accept_threshold
    method = (
        "embedding_similarity"
        if not needs_review
        else "embedding_similarity_low_confidence"
    )

    result = {
        "category": predicted_category,
        "confidence": best_similarity,
        "method": method,
        "matched_keywords": [
            f"closest_match: {best_match_activity}",
            f"similarity_score: {best_similarity}",
        ],
        "blocked_keywords": [],
        "needs_review": needs_review,
    }

    return result, low_score_info