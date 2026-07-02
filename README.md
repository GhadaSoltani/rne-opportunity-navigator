# RNE Opportunity Navigator

Automated pipeline for extracting company data from RNE PDF documents and classifying them into business sectors using multi-layer ML and LLM verification.

**Status:** Production-ready | **Language:** Python 3.11+ | **Last Updated:** 2026

---

## 🎯 Overview

This project provides an end-to-end solution for:

1. **Extraction** — Parse RNE PDF files and generate structured `rne_companies.csv` with company names and activities
2. **Segmentation** — Classify companies into 8 business sectors using a confidence-ranked pipeline (rules → embeddings → RAG → LLM)
3. **API** — FastAPI endpoints to run the pipeline programmatically with job status tracking
4. **Dashboard** — Streamlit interface for exploratory data analysis, batch processing, and result browsing

---

## 📊 Business Sectors

The classifier assigns one of 8 mutually exclusive categories to each company:

| Sector | Description | Examples |
|---|---|---|
| **retail** | Commerce, sales, distribution, import/export, restaurants, cafés | Supermarket, boutique, bakery, café, e-commerce |
| **manufacturing** | Industrial production, fabrication, transformation of goods | Textiles, chemicals, food processing, metal works |
| **transport** | Logistics, freight, delivery, warehousing, fleet management | Courier, trucking company, warehouse, taxi service |
| **tourism** | Hotels, travel agencies, accommodation, leisure, recreation | Hotel, resort, travel agency, sports facilities |
| **healthcare** | Clinics, hospitals, pharmacies, medical labs, veterinary | Pharmacy, dental clinic, medical lab, hospital |
| **education** | Schools, universities, training centers, childcare | School, university, coding bootcamp, daycare |
| **financial_services** | Banking, insurance, accounting, audit, investment | Bank, insurance, accounting firm, credit union |
| **others** | Services not covered above (consulting, IT, construction, real estate, government) | Consulting, law firm, software company, construction |

---

## 📁 Project Structure

```
rne-opportunity-navigator/
│
├── extraction/                 ← PDF extraction pipeline
│   ├── run_batch.py            Batch extraction orchestrator
│   ├── step1_extract_mixed.py   Parse PDFs → mixed format
│   ├── step3_to_csv.py          Mixed format → structured CSV
│   └── step5_mixed_to_company_csv.py  Denormalize to flat table
│
├── segmentation/               ← Classification pipeline (5 layers)
│   ├── config.py               Configuration & paths
│   ├── data_loader.py          Load and validate CSV inputs
│   ├── text_cleaner.py         Text preprocessing (normalize accents, case)
│   ├── taxonomy_classifier.py   Layer 1: Keyword-based rules
│   ├── validated_examples_classifier.py  Layer 0: Manual corrections (highest priority)
│   ├── embedding_classifier.py  Layer 3: Semantic similarity to validated examples
│   ├── rag_retriever.py        RAG knowledge base queries
│   ├── rag_knowledge_builder.py Build in-memory RAG index
│   ├── llm_validator.py        Layer 5: Mistral LLM verification
│   ├── llm_full_auditor.py     Batch LLM audit on uncertain rows
│   ├── export_results.py       Format & export results
│   └── main.py                 Segmentation orchestrator
│
├── pipeline/                   ← High-level orchestration
│   └── runner.py               Pipeline state machine & error handling
│
├── api/                        ← FastAPI server
│   └── routes.py               REST endpoints
│
├── app/                        ← Streamlit dashboard
│   └── dashboard.py            Interactive UI
│
├── data/
│   ├── input/
│   │   ├── pdfs/               Drop PDF files here for extraction
│   │   └── rne_companies.csv   Or drop pre-extracted CSV directly
│   ├── output/                 Classification results (segmented CSV, audit, review queue)
│   └── knowledge/
│       └── validated_examples.csv  Manual corrections (highest priority in pipeline)
│
├── knowledge/
│   ├── sector_taxonomy.yaml     Classification rules, keywords (French & Arabic)
│   ├── rag_knowledge_base.csv   Auto-generated RAG embeddings (do not edit)
│   └── validated_examples.csv   Your manual corrections (persist across runs)
│
├── run.py                      Single entry point for all modes
├── requirements.txt            Dependencies
└── README.md                   This file
```

---

## 🔄 Classification Pipeline (5 Layers)

Each company row passes through these layers sequentially. **The first layer that returns a confident result wins** — deeper layers are skipped.

```
┌─────────────────────────────────────────────────────────┐
│ 0. Validated Examples (confidence: 1.0)                 │
│    → Exact match against knowledge/validated_examples.csv│
│    → Your manual corrections take absolute priority      │
├─────────────────────────────────────────────────────────┤
│ 1. Taxonomy Rules (confidence: 0.9–1.0)                 │
│    → Keyword matching against sector_taxonomy.yaml      │
│    → Fast, interpretable, rule-based                    │
├─────────────────────────────────────────────────────────┤
│ 2. Embedding Similarity (confidence: 0.7–0.9)           │
│    → Semantic similarity vs. validated examples         │
│    → Catches paraphrases & synonyms                     │
├─────────────────────────────────────────────────────────┤
│ 3. RAG Retrieval (confidence: 0.6–0.8)                  │
│    → Semantic search in knowledge base                  │
│    → Best for ambiguous/niche activities                │
├─────────────────────────────────────────────────────────┤
│ 4. LLM Verification (confidence: 0.5–0.9)               │
│    → Mistral LLM re-examines uncertain rows             │
│    → Manual audit of previously unclassified rows       │
└─────────────────────────────────────────────────────────┘
```

### Output Fields

Each row gets:
- `category` — Predicted sector (or `null` if unclassified)
- `confidence` — Score 0–1 indicating certainty
- `method` — Which layer made the prediction (e.g., "taxonomy", "embedding")
- `needs_review` — `True` if confidence is below threshold (default: 0.65)

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** (3.12 recommended for better performance)
- **Ollama** (optional, only for LLM audit step)
- **Git** (for cloning the repository)

### Installation (5 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/GhadaSoltani/rne-opportunity-navigator.git
cd rne-opportunity-navigator

# 2. Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Build RAG knowledge base (required once per installation)
python run.py --skip-extraction --rebuild-rag
```

---

## 📖 Usage

### Option A: You have a CSV file ready

```bash
# Place your CSV at data/input/rne_companies.csv, then:
python run.py --skip-extraction
```

**Expected output:**
```
data/output/
├── rne_companies_segmented.csv      # All rows with predictions
├── classification_audit.csv         # Summary: activity, category, method
├── review_needed.csv                # Rows flagged for manual review
└── empty_activities.csv             # Rows with no activity text
```

### Option B: Extract from PDFs first

```bash
# Drop PDF files in data/input/pdfs/, then:
python run.py --pdf-folder data/input/pdfs
```

This runs extraction → segmentation automatically.

### Option C: Full pipeline with LLM audit

```bash
# Requires Ollama running locally (see LLM Setup below)
python run.py --pdf-folder data/input/pdfs --llm-audit
```

This runs extraction → segmentation → LLM re-examination of uncertain rows.

### All run.py Options

```
--pdf-folder PATH       Folder containing PDFs to extract
--input PATH            Path to rne_companies.csv (default: data/input/rne_companies.csv)
--skip-extraction       Skip PDF extraction; run segmentation only
--rebuild-rag           Force rebuild of RAG knowledge base
--llm-audit             Run LLM audit after segmentation (requires Ollama)
--llm-limit N           Limit LLM audit to N rows (useful for testing)
--keep-mixed            Keep intermediate extraction files (for debugging)
--from-db               Extract from database instead of local folder (MinIO/MongoDB)
--dashboard             Launch Streamlit dashboard
--api                   Launch FastAPI server
--host ADDR             API host (default: 0.0.0.0)
--port PORT             API port (default: 8000)
--reload                Enable uvicorn auto-reload (development)
```

---

## 🤖 LLM Audit (Optional)

The LLM audit uses **Mistral** to re-examine rows with low confidence or stuck in `others` category. This step is optional but significantly improves accuracy.

### Setup Ollama

1. **Install Ollama:**
   - Download from [https://ollama.com](https://ollama.com)
   - Follow platform-specific installation steps

2. **Start Ollama in a separate terminal:**
   ```bash
   ollama serve
   ```
   (Server listens on `http://localhost:11434`)

3. **Pull Mistral model:**
   ```bash
   ollama pull mistral
   ```
   (First run takes ~5 minutes; ~4GB disk space)

### Run LLM Audit

**Test mode (first 20 rows):**
```bash
python -m segmentation.llm_full_auditor
```

**Production mode (all uncertain rows):**
```bash
# Edit the bottom of segmentation/llm_full_auditor.py and set limit=None
python -m segmentation.llm_full_auditor
```

**Resume interrupted audit:**
The audit automatically skips already-audited rows, so you can safely interrupt and resume.

---

## 📊 Output Files

All files are saved to `data/output/`:

| File | Purpose | Rows | Columns |
|---|---|---|---|
| `rne_companies_segmented.csv` | **Full results** — every company with predictions | 958 | activity, category, confidence, method, needs_review |
| `classification_audit.csv` | **Compact audit** — for spreadsheet review | N/A | activity, category, method, keywords |
| `review_needed.csv` | **Manual review queue** — rows with confidence < 0.65 | Varies | activity, category, confidence, reason |
| `empty_activities.csv` | **Data quality** — rows with missing/blank activity text | Varies | company_name (for data cleaning) |
| `embedding_low_confidence.csv` | **Embedding issues** — rows where embedding score < threshold | Varies | activity, raw_score |

### Interpreting Results

- **confidence ≥ 0.9:** High confidence; results production-ready
- **0.65 ≤ confidence < 0.9:** Medium confidence; worth spot-checking
- **confidence < 0.65:** Flagged for `needs_review = True`; manual review recommended
- **method = "others":** No rule/embedding match found; suggest LLM audit

---

## 🔧 Improving Accuracy

The fastest way to improve classification is to grow `knowledge/validated_examples.csv` with manual corrections.

### Workflow

**Step 1 — Review results:**
```bash
# Open data/output/rne_companies_segmented.csv
# Focus on rows where:
#   - category = 'others' (unclassified)
#   - needs_review = True (low confidence)
#   - confidence < 0.7 (uncertain)
```

**Step 2 — Add corrections:**
```bash
# Edit knowledge/validated_examples.csv and add correct classifications:
activity,category
Commerce de matériel informatique,retail
Clinique pédiatrique,healthcare
Conseil en ingénierie logicielle,others
```

**Step 3 — Rebuild & re-run:**
```bash
python run.py --skip-extraction --rebuild-rag
```

Your corrections apply immediately and are permanent (stored in `validated_examples.csv`).

---

## 🎨 Streamlit Dashboard

Interactive UI for exploring results, running pipelines, and managing corrections.

```bash
python run.py --dashboard
```

Opens `http://localhost:8501` in your browser.

**Features:**
- Upload CSV and run segmentation with one click
- View category distribution charts and statistics
- Browse and filter classified companies
- Download output files
- Manage the manual review queue
- Add corrections directly from the UI

---

## 🌐 FastAPI Server

RESTful API for programmatic access to the pipeline.

```bash
python run.py --api
```

Server starts at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/pipeline/run` | POST | Run full pipeline (extraction + segmentation) |
| `/pipeline/segment` | POST | Upload CSV and run segmentation |
| `/pipeline/status` | GET | Check if pipeline is running |
| `/results/summary` | GET | Get classification summary (counts by category) |
| `/results/download` | GET | Download segmented CSV |
| `/results/download/audit` | GET | Download audit CSV |
| `/results/download/review` | GET | Download review CSV |
| `/pipeline/llm-audit` | POST | Trigger LLM audit on risky rows |

**Example:**
```bash
# Run segmentation via API
curl -X POST http://localhost:8000/pipeline/segment \
  -F "file=@data/input/rne_companies.csv"

# Get summary
curl http://localhost:8000/results/summary
```

---

## 📚 Advanced Features

### Extending the Pipeline

The pipeline is modular and designed for extension. To add a new layer:

1. Create your module in a new folder (e.g., `scoring/`)
2. Implement a function that takes a DataFrame and returns predictions with confidence scores
3. Open `pipeline/runner.py` and add a `_run_scoring(ctx)` function
4. Register it in the `PIPELINE_STEPS` list

The API, dashboard, and CLI (`run.py`) automatically pick up the new layer.

### Database Integration

To extract from MinIO or MongoDB instead of local PDFs:

```bash
# Set environment variables
export MINIO_ENDPOINT=minio.example.com
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin

# Run pipeline from database
python run.py --from-db
```

---

## 🐛 Troubleshooting

### "No module named 'segmentation'"
- Ensure you're running from the repository root: `pwd` should show `rne-opportunity-navigator`

### "Ollama connection refused" (LLM audit fails)
- Start Ollama: `ollama serve` (in a separate terminal)
- Verify connectivity: `curl http://localhost:11434/api/tags`

### "Mistral not found"
- Pull the model: `ollama pull mistral`
- Verify: `ollama list` (should show `mistral`)

### PDF extraction produces empty CSV
- Check PDF format: some PDFs are image-based (OCR not yet implemented)
- Check folder path: `ls data/input/pdfs/`

### Results all classified as "others"
- Rebuild RAG: `python run.py --skip-extraction --rebuild-rag`
- Check taxonomy: verify `knowledge/sector_taxonomy.yaml` is valid YAML
- Run LLM audit to re-examine: `python run.py --llm-audit`

---

## 📋 Requirements

See `requirements.txt` for full list:

**Core:**
- `pandas`, `numpy` — Data processing
- `scikit-learn` — ML utilities
- `pyyaml` — Configuration files
- `sentence-transformers` — Embeddings for semantic similarity
- `requests`, `tqdm` — HTTP, progress bars

**Extraction:**
- `camelot-py[cv]`, `pymupdf`, `PyPDF2` — PDF parsing
- `opencv-python` — Image processing

**API & Dashboard:**
- `fastapi`, `uvicorn[standard]` — REST API
- `streamlit`, `plotly` — Dashboard & charts

---

## 📄 License

[Add your license here, e.g., MIT]

## 👥 Contributing

Contributions are welcome! Please open an issue or pull request for bugs, features, or improvements.

## 📞 Support

For questions or issues, please open a GitHub issue with:
- Description of the problem
- Relevant error messages
- Steps to reproduce
- Platform (Windows/Mac/Linux)

---

## 🗺️ Roadmap

- [ ] OCR support for image-based PDFs
- [ ] GraphQL API alternative
- [ ] Real-time classification WebSocket endpoint
- [ ] Batch job scheduling (Celery/RQ)
- [ ] Multi-language support beyond French/Arabic
- [ ] Export to database (PostgreSQL, MongoDB)
- [ ] Web UI for taxonomy editing
- [ ] Automated accuracy metrics & A/B testing

---

**Last Updated:** 2026 | **Maintained by:** GhadaSoltani
