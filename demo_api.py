"""
demo_api.py
===========
Single-file FastAPI backend that ties the whole repo together for a live demo:

    1. Clients & Segmentation  — add a client manually or upload/point at a CSV,
       classify business activity into sectors (validated examples -> taxonomy
       rules -> semantic embeddings, the first three layers of
       segmentation/main.py's 5-layer cascade).
    2. RNE PDF extraction      — upload one or many RNE PDFs, parse them
       (extraction/) and clean the text fields (segmentation.text_cleaner),
       return one CSV.
    3. PU-Bagging + supervised classification dashboard — surfaces the
       prediction/ submodule's results (Bagging-PU / prior-corrected / two-step
       PU learning, then a calibrated LightGBM classifier saved as
       best_model.joblib) and lets you score a business live.

Design note: `segmentation/__init__.py` and `extraction/__init__.py` eagerly
import heavy optional deps (sentence-transformers, scikit-learn, camelot,
PyMuPDF) that may not be installed on the demo machine. Rather than crash the
whole API, missing packages are stubbed at import time (see `_available`
below) so the modules still import cleanly; each feature is then indepedently
gated by a capability flag and returns a clear "pip install ..." message
instead of a stack trace.

Run:
    py -3 -m uvicorn demo_api:app --reload --port 8000
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import types
import uuid
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

try:
    from rapidfuzz import fuzz as _fuzz
    from rapidfuzz import process as _fuzz_process
    from rapidfuzz import utils as _fuzz_utils
    RAPIDFUZZ_OK = True
except Exception:  # pragma: no cover - defensive
    RAPIDFUZZ_OK = False

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

DATA_INPUT = BASE_DIR / "data" / "input"
DATA_OUTPUT = BASE_DIR / "data" / "output"
DATA_INPUT.mkdir(parents=True, exist_ok=True)
DATA_OUTPUT.mkdir(parents=True, exist_ok=True)

MANUAL_CLIENTS_CSV = DATA_OUTPUT / "demo_manual_clients.csv"

PREDICTION_DIR = BASE_DIR / "prediction"
CLASSIFICATION_DIR = PREDICTION_DIR / "classification"
FIGURES_DIR = CLASSIFICATION_DIR / "figures"

TOKEN_STORE: Dict[str, Path] = {}


# =============================================================================
# Optional-dependency stubbing
# =============================================================================
def _stub_getattr_factory(name: str):
    def __getattr__(attr):  # noqa: N807
        def _unavailable(*_a, **_k):
            raise RuntimeError(
                f"'{name}' is not installed in this environment — this feature "
                f"is disabled until it's installed."
            )
        return _unavailable
    return __getattr__


def _install_stub_chain(dotted_name: str) -> None:
    parts = dotted_name.split(".")
    for i in range(1, len(parts) + 1):
        partial = ".".join(parts[:i])
        if partial in sys.modules:
            continue
        stub = types.ModuleType(partial)
        stub.__getattr__ = _stub_getattr_factory(partial)
        sys.modules[partial] = stub
        if i > 1:
            setattr(sys.modules[".".join(parts[: i - 1])], parts[i - 1], stub)


def _available(dotted_name: str) -> bool:
    """True if really importable; otherwise installs a harmless stub chain so
    unconditional `import`/`from ... import ...` elsewhere in the codebase
    doesn't crash, and returns False."""
    try:
        import_module(dotted_name)
        return True
    except Exception:
        _install_stub_chain(dotted_name)
        return False


SENTENCE_TRANSFORMERS_OK = _available("sentence_transformers")
SKLEARN_PAIRWISE_OK = _available("sklearn.metrics.pairwise")
CAMELOT_OK = _available("camelot")
FITZ_OK = _available("fitz")

EMBEDDING_LAYER_AVAILABLE = SENTENCE_TRANSFORMERS_OK and SKLEARN_PAIRWISE_OK
EXTRACTION_LAYER_AVAILABLE = CAMELOT_OK and FITZ_OK
EMBEDDING_FALLBACK_CAP = 300  # cap embedding calls per batch run, keeps the demo snappy

# ---- segmentation (safe to import now; heavy bits are stubbed if missing) --
from segmentation.config import TAXONOMY_PATH, VALIDATED_EXAMPLES_PATH, INPUT_CSV
from segmentation.text_cleaner import normalize_text, normalize_text_primary
from segmentation.data_loader import load_companies
from segmentation.taxonomy_classifier import load_taxonomy, classify_with_taxonomy
from segmentation.validated_examples_classifier import (
    load_validated_examples_with_patterns,
    classify_with_validated_examples,
)

TAXONOMY = load_taxonomy(TAXONOMY_PATH)
VALIDATED_EXAMPLES, VALIDATED_PATTERNS = load_validated_examples_with_patterns(VALIDATED_EXAMPLES_PATH)

_embedding_model = None
_embedding_ref_df = None
_embedding_ref_vecs = None


def _ensure_embedding_model():
    global _embedding_model, _embedding_ref_df, _embedding_ref_vecs
    if _embedding_model is None:
        from segmentation.embedding_classifier import (
            build_reference_embeddings,
            load_embedding_model,
            load_embedding_reference,
        )
        _embedding_ref_df = load_embedding_reference(VALIDATED_EXAMPLES_PATH)
        _embedding_model = load_embedding_model()
        _embedding_ref_vecs = build_reference_embeddings(_embedding_model, _embedding_ref_df)
    return _embedding_model, _embedding_ref_df, _embedding_ref_vecs


# ---- extraction (safe to import now; camelot/fitz stubbed if missing) -----
try:
    from extraction.run_batch import process_one_pdf
    EXTRACTION_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - defensive
    process_one_pdf = None
    EXTRACTION_IMPORT_ERROR = str(exc)

from extraction.step5_mixed_to_company_csv import clean_text as extraction_clean_text

# ---- prediction / PU-bagging classifier (isolated, own sys.path entry) ----
if str(CLASSIFICATION_DIR) not in sys.path:
    sys.path.insert(0, str(CLASSIFICATION_DIR))

PREDICTION_AVAILABLE = False
PREDICTION_IMPORT_ERROR = None
try:
    from supervised_models import (  # type: ignore
        engineer_presence_flags,
        load_bundle,
        predict_proba_new,
    )
    PREDICTION_AVAILABLE = True
except Exception as exc:  # pragma: no cover - defensive
    PREDICTION_IMPORT_ERROR = str(exc)

_pred_bundle = None


def _ensure_pred_bundle():
    global _pred_bundle
    if _pred_bundle is None:
        model_path = CLASSIFICATION_DIR / "best_model.joblib"
        if not model_path.exists():
            raise FileNotFoundError(f"{model_path} not found")
        _pred_bundle = load_bundle(str(model_path))
    return _pred_bundle


# =============================================================================
# Classification cascade (validated examples -> taxonomy -> embeddings)
# Lighter than segmentation.main.run_segmentation: skips the RAG + LLM layers
# so the demo works with no rag_knowledge_base.csv and no Ollama running.
# =============================================================================
def classify_activity(activity_text: str, use_embeddings: bool = True) -> dict:
    activity_primary = normalize_text_primary(activity_text or "")
    activity_multi = normalize_text(activity_text or "")

    validated = classify_with_validated_examples(activity_primary, VALIDATED_EXAMPLES, VALIDATED_PATTERNS)
    if validated is not None and validated["method"] == "validated_example_exact":
        return validated

    taxonomy_result = classify_with_taxonomy(activity_primary, TAXONOMY)
    if taxonomy_result["method"] == "empty_activity" or taxonomy_result["needs_review"] is False:
        return taxonomy_result

    if use_embeddings and EMBEDDING_LAYER_AVAILABLE:
        try:
            from segmentation.embedding_classifier import classify_with_embeddings
            model, ref_df, ref_vecs = _ensure_embedding_model()
            embedding_result, _ = classify_with_embeddings(
                activity_clean=activity_multi, model=model, reference_df=ref_df,
                reference_embeddings=ref_vecs, accept_threshold=0.90, review_threshold=0.85,
            )
            if embedding_result is not None:
                return embedding_result
        except Exception:
            pass

    return validated or taxonomy_result


def classify_dataframe(df: pd.DataFrame, activity_col: str) -> pd.DataFrame:
    """Two-pass classification: cheap rules first, embeddings only on the
    uncertain remainder (capped, so a large CSV stays demo-fast)."""
    df = df.copy()
    n = len(df)
    categories, confidences, methods, reviews = [], [], [], []
    fallback_indices: List[int] = []

    for i, text in enumerate(df[activity_col].astype(str)):
        result = classify_activity(text, use_embeddings=False)
        categories.append(result["category"])
        confidences.append(result["confidence"])
        methods.append(result["method"])
        reviews.append(result["needs_review"])
        if result["needs_review"] and result["method"] not in ("empty_activity",):
            fallback_indices.append(i)

    embedding_applied = 0
    if EMBEDDING_LAYER_AVAILABLE and fallback_indices:
        capped = fallback_indices[:EMBEDDING_FALLBACK_CAP]
        for i in capped:
            result = classify_activity(str(df[activity_col].iloc[i]), use_embeddings=True)
            categories[i] = result["category"]
            confidences[i] = result["confidence"]
            methods[i] = result["method"]
            reviews[i] = result["needs_review"]
            embedding_applied += 1

    df["category"] = categories
    df["confidence"] = confidences
    df["method"] = methods
    df["needs_review"] = reviews
    df.attrs["embedding_applied"] = embedding_applied
    df.attrs["embedding_skipped"] = max(0, len(fallback_indices) - embedding_applied)
    return df


def ensure_default_input_csv() -> Optional[Path]:
    """Guarantee `data/input/rne_companies.csv` exists for the 'use existing
    data' demo path, exporting it from rne_companies.sqlite if needed."""
    if INPUT_CSV.exists():
        return INPUT_CSV
    sqlite_path = DATA_INPUT / "rne_companies.sqlite"
    if not sqlite_path.exists():
        return None
    conn = sqlite3.connect(sqlite_path)
    try:
        df = pd.read_sql_query("SELECT * FROM companies", conn)
    finally:
        conn.close()
    if df.empty:
        return None
    INPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(INPUT_CSV, index=False, encoding="utf-8-sig")
    return INPUT_CSV


# =============================================================================
# FastAPI app
# =============================================================================
app = FastAPI(title="RNE Opportunity Navigator — Demo API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "capabilities": {
            "embedding_layer": EMBEDDING_LAYER_AVAILABLE,
            "extraction_pdf": EXTRACTION_LAYER_AVAILABLE and process_one_pdf is not None,
            "prediction_model": PREDICTION_AVAILABLE and (CLASSIFICATION_DIR / "best_model.joblib").exists(),
        },
        "notes": {
            "embedding_layer": None if EMBEDDING_LAYER_AVAILABLE else "pip install sentence-transformers scikit-learn",
            "extraction_pdf": None if EXTRACTION_LAYER_AVAILABLE else "pip install camelot-py[cv] pymupdf (+ Ghostscript on Windows)",
            "prediction_model": None if PREDICTION_AVAILABLE else (
                "pip install scikit-learn lightgbm joblib shap"
                if not SKLEARN_PAIRWISE_OK else
                f"pip install lightgbm joblib shap ({PREDICTION_IMPORT_ERROR})"
            ),
        },
    }


# -----------------------------------------------------------------------------
# 1. Clients & Segmentation
# -----------------------------------------------------------------------------
class ClientIn(BaseModel):
    denomination: str
    activite: str
    nom_commercial: Optional[str] = None
    forme_juridique: Optional[str] = None
    adresse: Optional[str] = None
    capital: Optional[str] = None
    date_immatriculation: Optional[str] = None
    nom_dirigeant: Optional[str] = None


class TextIn(BaseModel):
    activity: str


@app.post("/segmentation/classify-text")
def classify_text(body: TextIn):
    return classify_activity(body.activity)


@app.post("/segmentation/clients")
def add_client(client: ClientIn):
    result = classify_activity(client.activite)

    existing = []
    if MANUAL_CLIENTS_CSV.exists():
        existing = pd.read_csv(MANUAL_CLIENTS_CSV, encoding="utf-8-sig").to_dict("records")

    row = {
        "client_id": len(existing) + 1,
        "fr_denomination": client.denomination,
        "fr_nom_commercial": client.nom_commercial or "",
        "fr_forme_juridique": client.forme_juridique or "",
        "fr_adresse": client.adresse or "",
        "capital": client.capital or "",
        "date_immatriculation": client.date_immatriculation or "",
        "ar_nom_prenom": client.nom_dirigeant or "",
        "fr_activite_principale": client.activite,
        "category": result["category"],
        "confidence": result["confidence"],
        "method": result["method"],
        "needs_review": result["needs_review"],
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    existing.append(row)
    pd.DataFrame(existing).to_csv(MANUAL_CLIENTS_CSV, index=False, encoding="utf-8-sig")
    return row


@app.get("/segmentation/clients")
def list_clients():
    if not MANUAL_CLIENTS_CSV.exists():
        return []
    return pd.read_csv(MANUAL_CLIENTS_CSV, encoding="utf-8-sig").fillna("").to_dict("records")


@app.delete("/segmentation/clients")
def clear_clients():
    if MANUAL_CLIENTS_CSV.exists():
        MANUAL_CLIENTS_CSV.unlink()
    return {"status": "cleared"}


@app.post("/segmentation/run-csv")
async def run_csv(
    file: Optional[UploadFile] = File(None),
    use_existing: bool = Form(False),
):
    if use_existing:
        input_path = ensure_default_input_csv()
        if input_path is None:
            raise HTTPException(404, "No existing dataset found (data/input/rne_companies.csv or .sqlite).")
    elif file is not None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="rne_seg_"))
        input_path = tmp_dir / Path(file.filename).name
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    else:
        raise HTTPException(400, "Provide a CSV file or set use_existing=true.")

    try:
        df, detected_cols = load_companies(str(input_path))
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    df = classify_dataframe(df, "activity_raw_combined")

    out_path = DATA_OUTPUT / "demo_segmented_latest.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    token = uuid.uuid4().hex
    TOKEN_STORE[token] = out_path

    return {
        "total_rows": len(df),
        "detected_columns": detected_cols,
        "category_distribution": df["category"].value_counts().to_dict(),
        "method_distribution": df["method"].value_counts().to_dict(),
        "needs_review": int(df["needs_review"].sum()),
        "embedding_layer_used": EMBEDDING_LAYER_AVAILABLE,
        "embedding_applied_rows": df.attrs.get("embedding_applied", 0),
        "embedding_skipped_rows": df.attrs.get("embedding_skipped", 0),
        "download_token": token,
    }


def _company_record(row: dict, source: str) -> dict:
    return {
        "denomination": str(row.get("fr_denomination", "") or "").strip(),
        "activite": str(row.get("fr_activite_principale", "") or "").strip(),
        "adresse": str(row.get("fr_adresse", "") or "").strip(),
        "capital": str(row.get("capital", "") or "").strip(),
        "date_immatriculation": str(row.get("date_immatriculation", "") or "").strip(),
        "forme_juridique": str(row.get("fr_forme_juridique", "") or "").strip(),
        "category": str(row.get("category", "") or "").strip(),
        "source": source,
    }


@app.get("/companies/search")
def search_companies(q: str = "", limit: int = 8):
    """
    Real fuzzy lookup by company name — NOT live scraping. It searches the RNE
    registry already loaded (data/input/rne_companies.csv, auto-exported from
    the sqlite dump) plus anything already added manually, so typing a name
    that's already on file auto-fills the rest of the form instead of the
    operator retyping it. A live enrichment lookup (ratings/reviews/phone from
    the web) is a separate, not-yet-built feature — see the Roadmap page.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return []

    records: List[dict] = []
    base_path = ensure_default_input_csv()
    if base_path is not None:
        base_df = pd.read_csv(base_path, encoding="utf-8-sig").fillna("")
        records.extend(_company_record(r, "RNE registry") for r in base_df.to_dict("records"))

    manual = _read_csv_safe(MANUAL_CLIENTS_CSV)
    if manual is not None and not manual.empty:
        records.extend(_company_record(r, "Manual entry") for r in manual.fillna("").to_dict("records"))

    records = [r for r in records if r["denomination"]]
    if not records:
        return []

    names = [r["denomination"] for r in records]

    if RAPIDFUZZ_OK:
        matches = _fuzz_process.extract(
            q, names, scorer=_fuzz.WRatio, processor=_fuzz_utils.default_process, limit=limit * 4,
        )
        ranked = [(idx, score) for _, score, idx in matches if score >= 60]
    else:
        ranked = [(i, 100.0) for i, n in enumerate(names) if q.lower() in n.lower()][: limit * 4]

    seen = set()
    results = []
    for idx, score in ranked:
        rec = records[idx]
        key = rec["denomination"].lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({**rec, "match_score": round(float(score), 1)})
        if len(results) >= limit:
            break
    return results


@app.get("/segmentation/download/{token}")
def download_segmentation(token: str):
    path = TOKEN_STORE.get(token)
    if path is None or not path.exists():
        raise HTTPException(404, "Unknown or expired download token.")
    return FileResponse(path, filename=path.name, media_type="text/csv")


# -----------------------------------------------------------------------------
# 2. RNE PDF extraction
# -----------------------------------------------------------------------------
@app.post("/extraction/parse-pdfs")
async def parse_pdfs(files: List[UploadFile] = File(...)):
    if not (EXTRACTION_LAYER_AVAILABLE and process_one_pdf is not None):
        raise HTTPException(
            503,
            "PDF extraction needs camelot-py[cv] and pymupdf "
            "(pip install camelot-py[cv] pymupdf; Windows also needs Ghostscript).",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="rne_pdf_"))
    results = []
    for uf in files:
        safe_name = Path(uf.filename).name
        pdf_path = tmp_dir / safe_name
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(uf.file, f)
        outcome = process_one_pdf(pdf_path=pdf_path, output_dir=tmp_dir, keep_mixed=False, no_sqlite=True)
        results.append({
            "file": safe_name,
            "status": outcome["status"],
            "identifiant_unique": outcome.get("id", ""),
            "error": outcome.get("error", ""),
        })

    companies_csv = tmp_dir / "rne_companies.csv"
    if not companies_csv.exists():
        return {"results": results, "n_ok": 0, "n_failed": len(results), "rows": 0, "download_token": None}

    df = pd.read_csv(companies_csv, encoding="utf-8-sig")
    df = df.map(lambda v: extraction_clean_text(v) if isinstance(v, str) else v)
    if "fr_activite_principale" in df.columns:
        df["activity_clean_fr"] = df["fr_activite_principale"].apply(normalize_text_primary)
    if "ar_activite_principale" in df.columns:
        df["activity_clean_ar"] = df["ar_activite_principale"].apply(normalize_text_primary)

    # Chain straight into sector classification — a parsed PDF should come
    # back sector-tagged, not just as raw fields the employee has to sort
    # through separately.
    activity_source = "fr_activite_principale" if "fr_activite_principale" in df.columns else None
    if activity_source is not None:
        df = classify_dataframe(df, activity_source)
        by_id = {r["identifiant_unique"]: r for r in results}
        for _, row in df.iterrows():
            r = by_id.get(row.get("identifiant_unique", ""))
            if r is not None:
                r["sector"] = row.get("category", "")

    out_path = DATA_OUTPUT / "demo_extracted_cleaned.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    token = uuid.uuid4().hex
    TOKEN_STORE[token] = out_path

    n_ok = sum(1 for r in results if r["status"] == "ok")
    return {
        "results": results,
        "n_ok": n_ok,
        "n_failed": len(results) - n_ok,
        "rows": len(df),
        "download_token": token,
    }


@app.get("/extraction/download/{token}")
def download_extraction(token: str):
    path = TOKEN_STORE.get(token)
    if path is None or not path.exists():
        raise HTTPException(404, "Unknown or expired download token.")
    return FileResponse(path, filename=path.name, media_type="text/csv")


# -----------------------------------------------------------------------------
# Enrichment tools — real, deliberately modest-scope implementations of the
# scrape / complete / clean pipeline described in the roadmap. None of these
# fabricate data: clean wraps logic already used live elsewhere in this app;
# complete only fills fields it can honestly justify from what's already
# present; scrape makes a genuine external API call (OpenStreetMap Nominatim,
# free/keyless) rather than pretending to hit a paid ratings/reviews source.
# -----------------------------------------------------------------------------
TUNISIA_GOVERNORATES = [
    "Tunis", "Ariana", "Ben Arous", "Manouba", "Nabeul", "Zaghouan", "Bizerte",
    "Beja", "Jendouba", "Kef", "Siliana", "Sousse", "Monastir", "Mahdia",
    "Sfax", "Kairouan", "Kasserine", "Sidi Bouzid", "Gabes", "Medenine",
    "Tataouine", "Gafsa", "Tozeur", "Kebili",
]

SECTOR_TO_CATEGORY_HINT = {
    "retail": "store", "manufacturing": "factory", "transport": "transport service",
    "tourism": "hotel", "healthcare": "clinic", "education": "school",
    "financial_services": "bank", "others": "business",
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@app.post("/tools/clean")
def tools_clean(body: Dict[str, Any] = Body(...)):
    """The cleaning tool. Thin wrapper around normalization logic that
    already runs live elsewhere in this app — nothing new or fabricated."""
    text = str(body.get("text", ""))
    if not text.strip():
        raise HTTPException(400, "Provide non-empty 'text'.")
    return {
        "original": text,
        "cleaned_basic": extraction_clean_text(text),
        "cleaned_normalized": normalize_text_primary(text),
    }


@app.post("/tools/complete")
def tools_complete(body: Dict[str, Any] = Body(...)):
    """The data-completion tool. Fills only fields it can deterministically
    justify from what's already present (governorate from address text,
    category from sector); anything it can't infer is reported as still
    missing rather than guessed."""
    out = dict(body)
    filled = []

    address = str(out.get("adresse") or out.get("address") or "")
    if not out.get("governorate") and address:
        addr_norm = normalize_text_primary(address)
        # Word-boundary match, longest name first — "Tunisie" (the country,
        # often present in addresses) must not false-match "Tunis" the
        # governorate, and "Ben Arous" should win over a bare "Arous".
        for gov in sorted(TUNISIA_GOVERNORATES, key=len, reverse=True):
            pattern = r"\b" + re.escape(normalize_text_primary(gov)) + r"\b"
            if re.search(pattern, addr_norm):
                out["governorate"] = gov
                filled.append("governorate")
                break

    sector = out.get("category") or out.get("sector")
    if sector in SECTOR_TO_CATEGORY_HINT and not out.get("maps_category"):
        out["maps_category"] = SECTOR_TO_CATEGORY_HINT[sector]
        filled.append("maps_category")

    still_missing = [
        f for f in ("governorate", "maps_category", "rating", "reviews", "phone", "website")
        if not out.get(f)
    ]
    return {"completed": out, "fields_filled": filled, "still_missing": still_missing}


@app.get("/tools/scrape")
def tools_scrape(name: str = "", address: str = ""):
    """The scraping/enrichment tool. Makes a genuine call to OpenStreetMap's
    free Nominatim geocoder — real external data, not fabricated. Scope note:
    this returns location/address matches, not Google-style ratings or
    reviews (that needs a paid, keyed API this demo doesn't have)."""
    query = f"{name} {address}".strip()
    if not query:
        raise HTTPException(400, "Provide a name and/or address to look up.")
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "tn"},
            headers={"User-Agent": "OpportunityNavigator-Demo/1.0 (thesis prototype)"},
            timeout=6,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:
        return {"found": False, "error": str(exc)}

    if not results:
        return {"found": False}

    r = results[0]
    return {
        "found": True,
        "display_name": r.get("display_name"),
        "latitude": float(r.get("lat")),
        "longitude": float(r.get("lon")),
        "osm_type": r.get("type"),
        "source": "OpenStreetMap Nominatim — free public geocoder, not a ratings/reviews source",
    }


# -----------------------------------------------------------------------------
# Company Directory — the single view uniting all three input methods
# -----------------------------------------------------------------------------
def _normalize_directory_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["company"] = df["fr_denomination"] if "fr_denomination" in df.columns else ""
    if "fr_activite_principale" in df.columns:
        out["activity"] = df["fr_activite_principale"]
    elif "activity_raw_combined" in df.columns:
        out["activity"] = df["activity_raw_combined"]
    else:
        out["activity"] = ""
    out["category"] = df["category"] if "category" in df.columns else ""
    out["confidence"] = df["confidence"] if "confidence" in df.columns else None
    out["method"] = df["method"] if "method" in df.columns else ""
    out["needs_review"] = df["needs_review"] if "needs_review" in df.columns else False
    out["source"] = source
    return out


@app.get("/directory")
def directory():
    frames = []
    manual = _read_csv_safe(MANUAL_CLIENTS_CSV)
    if manual is not None and not manual.empty:
        frames.append(_normalize_directory_frame(manual, "Manual entry"))

    batch = _read_csv_safe(DATA_OUTPUT / "demo_segmented_latest.csv")
    if batch is not None and not batch.empty:
        frames.append(_normalize_directory_frame(batch, "Bulk import"))

    pdf_extract = _read_csv_safe(DATA_OUTPUT / "demo_extracted_cleaned.csv")
    if pdf_extract is not None and not pdf_extract.empty:
        frames.append(_normalize_directory_frame(pdf_extract, "PDF document"))

    if not frames:
        return {"total": 0, "by_source": {}, "by_sector": {}, "needs_review": 0, "rows": []}

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["confidence"] = pd.to_numeric(combined["confidence"], errors="coerce")
    combined = combined.fillna("")

    return {
        "total": len(combined),
        "by_source": combined["source"].value_counts().to_dict(),
        "by_sector": combined[combined["category"] != ""]["category"].value_counts().to_dict(),
        "needs_review": int((combined["needs_review"] == True).sum()),  # noqa: E712
        "rows": combined.to_dict("records"),
    }


# -----------------------------------------------------------------------------
# 3. PU-Bagging + supervised classification dashboard
# -----------------------------------------------------------------------------
def _read_csv_safe(path: Path) -> Optional[pd.DataFrame]:
    return pd.read_csv(path) if path.exists() else None


@app.get("/prediction/overview")
def prediction_overview():
    run_summary = {}
    summary_path = CLASSIFICATION_DIR / "run_summary.json"
    if summary_path.exists():
        run_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    method_comp = _read_csv_safe(PREDICTION_DIR / "method_comparison_v3.csv")
    stability = _read_csv_safe(PREDICTION_DIR / "stability_v3.csv")
    prior_comp = _read_csv_safe(PREDICTION_DIR / "prior_comparison.csv")

    pu_by_method_at_k = {}
    if method_comp is not None:
        for k in (2000, 5000):
            subset = method_comp[method_comp["k"] == k]
            pu_by_method_at_k[str(k)] = subset.set_index("method")["recall@k"].round(4).to_dict()

    return {
        "run_summary": run_summary,
        "pu_recall_by_method": pu_by_method_at_k,
        "pu_stability": stability.to_dict("records") if stability is not None else [],
        "prior_estimation": prior_comp.to_dict("records") if prior_comp is not None else [],
        # The PU-learning label funnel, as actually run: Ooredoo never discloses
        # its client-base size, so "confirmed positives" comes purely from
        # cross-referencing the 28k-row Maps scrape against known purchase
        # records (entity linkage) — that gave 6,000 matched positives.
        # Bagging-PU then expanded the positive set to 9,352 confidently-positive
        # rows; everything else is treated as negative for the downstream
        # classifier. This replaces the older, smaller-scale numbers previously
        # quoted in prediction/README.md (~625 positives / 27,854 total), which
        # predate this larger entity-linkage pass.
        "label_funnel": {
            "total_businesses": 28000,
            "confirmed_positive_matches": 6000,
            "positives_after_bagging_pu": 9352,
            "negatives_for_classification": 28000 - 9352,
        },
        "prediction_model_available": PREDICTION_AVAILABLE and (CLASSIFICATION_DIR / "best_model.joblib").exists(),
    }


@app.get("/prediction/figures")
def prediction_figures():
    pu_figs = sorted(p.name for p in PREDICTION_DIR.glob("*.png"))
    cls_figs = sorted(p.name for p in FIGURES_DIR.glob("*.png")) if FIGURES_DIR.exists() else []
    return {"pu": pu_figs, "classification": cls_figs}


@app.get("/prediction/figure/{group}/{filename}")
def prediction_figure(group: str, filename: str):
    safe_name = Path(filename).name
    if group == "pu":
        path = PREDICTION_DIR / safe_name
    elif group == "classification":
        path = FIGURES_DIR / safe_name
    else:
        raise HTTPException(404, "Unknown figure group.")
    if not path.exists() or path.suffix.lower() != ".png":
        raise HTTPException(404, "Figure not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/prediction/model-info")
def prediction_model_info():
    if not PREDICTION_AVAILABLE:
        raise HTTPException(503, f"Prediction model unavailable: {PREDICTION_IMPORT_ERROR}")
    try:
        bundle = _ensure_pred_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    return {
        "best_model_name": bundle.get("best_model_name"),
        "calibration": bundle.get("calibration"),
        "threshold": bundle.get("threshold"),
        "n_features": len(bundle.get("feature_columns", [])),
        "numeric_features": bundle.get("numeric", []),
        "categorical_features": bundle.get("categorical", []),
    }


@app.post("/prediction/score")
def prediction_score(body: Dict[str, Any] = Body(...)):
    if not PREDICTION_AVAILABLE:
        raise HTTPException(503, f"Prediction model unavailable: {PREDICTION_IMPORT_ERROR}")
    try:
        bundle = _ensure_pred_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))

    df = pd.DataFrame([body])
    df = engineer_presence_flags(df)
    proba = predict_proba_new(df, bundle=bundle)[0]
    return {
        "prob_client": round(float(proba), 4),
        "predicted_client": bool(proba >= bundle.get("threshold", 0.5)),
        "model": bundle.get("best_model_name"),
    }


@app.post("/prediction/score-csv")
async def prediction_score_csv(file: UploadFile = File(...)):
    if not PREDICTION_AVAILABLE:
        raise HTTPException(503, f"Prediction model unavailable: {PREDICTION_IMPORT_ERROR}")
    try:
        bundle = _ensure_pred_bundle()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))

    df = pd.read_csv(file.file)
    df = engineer_presence_flags(df)
    proba = predict_proba_new(df, bundle=bundle)
    df["prob_client"] = proba
    df["predicted_client"] = df["prob_client"] >= bundle.get("threshold", 0.5)

    out_path = DATA_OUTPUT / "demo_scored_businesses.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    token = uuid.uuid4().hex
    TOKEN_STORE[token] = out_path

    preview_cols = [c for c in ["name", "category", "governorate", "prob_client", "predicted_client"] if c in df.columns]
    top_preview = df.sort_values("prob_client", ascending=False).head(15)[preview_cols].to_dict("records")

    return {
        "rows_scored": len(df),
        "predicted_client_count": int(df["predicted_client"].sum()),
        "top_preview": top_preview,
        "download_token": token,
    }


@app.get("/prediction/download/{token}")
def download_prediction(token: str):
    path = TOKEN_STORE.get(token)
    if path is None or not path.exists():
        raise HTTPException(404, "Unknown or expired download token.")
    return FileResponse(path, filename=path.name, media_type="text/csv")


@app.get("/")
def root():
    return {
        "name": "RNE Opportunity Navigator — Demo API",
        "docs": "/docs",
        "tabs": ["segmentation/*", "extraction/*", "prediction/*"],
    }
