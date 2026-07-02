import logging
from collections import defaultdict

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from segmentation.config import EMBEDDING_MODEL_NAME
from segmentation.text_cleaner import normalize_text

logger = logging.getLogger(__name__)


class RAGRetriever:
    def __init__(self, knowledge_path, top_k=5):
        self.knowledge_path = knowledge_path
        self.top_k = top_k

        self.df = pd.read_csv(knowledge_path, encoding="utf-8-sig")

        if "text" not in self.df.columns:
            raise ValueError("RAG knowledge base must contain a 'text' column.")
        if "category" not in self.df.columns:
            raise ValueError("RAG knowledge base must contain a 'category' column.")

        self.df["text_clean"] = self.df["text"].apply(normalize_text)

        logger.info("Loading embedding model for RAG...")
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        logger.info("Building RAG embeddings...")
        self.embeddings = self.model.encode(
            self.df["text_clean"].tolist(),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def retrieve(self, query_text):
        query_clean = normalize_text(query_text)
        if not query_clean:
            return []

        query_embedding = self.model.encode(
            [query_clean],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        similarities = cosine_similarity(query_embedding, self.embeddings)[0]
        top_indices = np.argsort(similarities)[::-1][:self.top_k]

        results = []
        for idx in top_indices:
            row = self.df.iloc[idx]
            results.append({
                "text":       row["text"],
                "category":   row["category"],
                "source":     row.get("source", ""),
                "similarity": round(float(similarities[idx]), 3),
            })

        return results


def classify_with_rag(retrieved_items, high_threshold=0.82, medium_threshold=0.65):
    if not retrieved_items:
        return None

    top_score = retrieved_items[0]["similarity"]

    if top_score < medium_threshold:
        return None

    relevant_items = [i for i in retrieved_items if i["similarity"] >= medium_threshold]

    votes = defaultdict(float)
    for item in relevant_items:
        votes[item["category"]] += item["similarity"]

    winning_category = max(votes, key=votes.get)

    context_summary = " | ".join(
        f"{i['category']}:{i['similarity']}:{i['source']}"
        for i in retrieved_items[:3]
    )
    vote_breakdown = ", ".join(
        f"{cat}={round(score, 3)}"
        for cat, score in sorted(votes.items(), key=lambda x: -x[1])
    )

    matched_keywords = [
        f"rag_match: {retrieved_items[0]['text']}",
        f"rag_context: {context_summary}",
        f"rag_votes: {vote_breakdown}",
    ]

    if top_score >= high_threshold:
        return {
            "category":         winning_category,
            "confidence":       top_score,
            "method":           "rag_similarity",
            "matched_keywords": matched_keywords,
            "blocked_keywords": [],
            "needs_review":     False,
        }

    return {
        "category":         winning_category,
        "confidence":       top_score,
        "method":           "rag_similarity_low_confidence",
        "matched_keywords": matched_keywords,
        "blocked_keywords": [],
        "needs_review":     True,
    }


def format_rag_context(retrieved_items):
    if not retrieved_items:
        return "No relevant RAG context found."
    lines = []
    for i, item in enumerate(retrieved_items, start=1):
        lines.append(
            f"{i}. source={item['source']} | category={item['category']} | "
            f"similarity={item['similarity']} | {item['text']}"
        )
    return "\n".join(lines)