from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV = BASE_DIR / "data" / "input" / "rne_companies.csv"

OUTPUT_CSV = BASE_DIR / "data" / "output" / "rne_companies_segmented.csv"
REVIEW_CSV = BASE_DIR / "data" / "output" / "review_needed.csv"
AUDIT_CSV = BASE_DIR / "data" / "output" / "classification_audit.csv"
EMPTY_ACTIVITY_CSV = BASE_DIR / "data" / "output" / "empty_activities.csv"
LOW_EMBEDDING_CSV = BASE_DIR / "data" / "output" / "embedding_low_confidence.csv"
TAXONOMY_PATH = BASE_DIR / "knowledge" / "sector_taxonomy.yaml"
VALIDATED_EXAMPLES_PATH = BASE_DIR / "knowledge" / "validated_examples.csv"
RAG_KNOWLEDGE_PATH = BASE_DIR / "knowledge" / "rag_knowledge_base.csv"

ACTIVITY_COLUMN = "fr_activite_principale"
AR_ACTIVITY_COLUMN = "ar_activite_principale"

CATEGORIES = [
    "retail",
    "manufacturing",
    "transport",
    "tourism",
    "healthcare",
    "education",
    "financial_services",
    "others",
]

HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.65

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"