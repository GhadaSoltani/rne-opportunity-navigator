# RNE Platform

Automated pipeline for extracting company data from RNE PDF documents and classifying them into business sectors.

---

## What this project does

1. **Extraction** — reads RNE PDF files and produces a structured `rne_companies.csv`
2. **Segmentation** — classifies each company into one of 8 business sectors using a multi-layer pipeline
3. **API** — exposes the pipeline via FastAPI endpoints
4. **Dashboard** — Streamlit interface to run the pipeline and browse results

---

## Business sectors

| Category | Description |
|---|---|
| `retail` | Commerce, vente, distribution, import/export, restaurants, cafés |
| `manufacturing` | Fabrication, industrie, transformation de produits physiques |
| `transport` | Transport, logistique, livraison, entreposage |
| `tourism` | Hôtels, agences de voyage, hébergement touristique |
| `healthcare` | Cliniques, hôpitaux, laboratoires, soins médicaux |
| `education` | Écoles, formation, universités, jardins d'enfants |
| `financial_services` | Banques, assurances, comptabilité, audit |
| `others` | Tout ce qui ne correspond pas aux catégories ci-dessus |

---

## Project structure

```
rne_platform/
│
├── extraction/                 ← PDF extraction pipeline
│   ├── __init__.py
│   ├── run_batch.py
│   ├── step1_extract_mixed.py
│   ├── step3_to_csv.py
│   └── step5_mixed_to_company_csv.py
│
├── segmentation/               ← Company classification pipeline
│   ├── __init__.py
│   ├── config.py
│   ├── data_loader.py
│   ├── text_cleaner.py
│   ├── taxonomy_classifier.py
│   ├── validated_examples_classifier.py
│   ├── embedding_classifier.py
│   ├── rag_retriever.py
│   ├── rag_knowledge_builder.py
│   ├── llm_validator.py
│   ├── llm_full_auditor.py
│   ├── export_results.py
│   └── main.py
│
├── pipeline/                   ← Orchestration layer
│   ├── __init__.py
│   └── runner.py
│
├── api/                        ← FastAPI server
│   ├── __init__.py
│   └── routes.py
│
├── app/                        ← Streamlit dashboard
│   └── dashboard.py
│
├── data/
│   ├── input/
│   │   ├── pdfs/               ← drop PDF files here
│   │   └── rne_companies.csv   ← or drop CSV directly here
│   ├── output/                 ← all classification outputs land here
│   └── knowledge/
│       └── validated_examples.csv
│
├── knowledge/
│   ├── sector_taxonomy.yaml    ← classification rules and keywords
│   ├── rag_knowledge_base.csv  ← auto-generated, do not edit
│   └── validated_examples.csv  ← manual corrections go here
│
├── run.py                      ← single entry point for everything
├── requirements.txt
└── README.md
```

---

## Segmentation pipeline layers

Each company row passes through these layers in order. The first layer that returns a confident result wins — the row does not continue to deeper layers.

```
1. Validated examples     → exact match against your manual corrections (confidence 1.0)
2. Taxonomy rules         → keyword matching against sector_taxonomy.yaml
3. Embedding similarity   → semantic similarity against validated examples
4. RAG similarity         → semantic search in the knowledge base
5. LLM verification       → Mistral via Ollama for uncertain rows
```

---

## Requirements

- Python 3.11 or higher
- [Ollama](https://ollama.com) installed locally (only needed for LLM audit step)
- Mistral model pulled in Ollama (only needed for LLM audit step)

---

## Installation

### Step 1 — Clone or create the project folder

```bash
mkdir rne_platform
cd rne_platform
```

### Step 2 — Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / Mac
python -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Build the RAG knowledge base

This must be run once before the first segmentation run, and again whenever you update `sector_taxonomy.yaml` or `knowledge/validated_examples.csv`.

```bash
python run.py --skip-extraction --rebuild-rag
```

---

## Running the pipeline

### Option A — You already have rne_companies.csv

Drop your CSV file into `data/input/rne_companies.csv` then run:

```bash
python run.py --skip-extraction
```

### Option B — You have PDF files to extract first

Drop your PDF files into `data/input/pdfs/` then run:

```bash
python run.py --pdf-folder data/input/pdfs
```

This runs extraction first, then segmentation automatically.

### Option C — Full pipeline with LLM audit

Runs extraction → segmentation → LLM audit on uncertain rows.
Requires Ollama running locally (see LLM audit section below).

```bash
python run.py --pdf-folder data/input/pdfs --llm-audit
```

---

## Output files

All outputs are saved to `data/output/`:

| File | Description |
|---|---|
| `rne_companies_segmented.csv` | Full results — all 958 rows with category, confidence, method |
| `classification_audit.csv` | Compact audit file — activity + category + method + keywords |
| `review_needed.csv` | Rows flagged for manual review (low confidence or partial match) |
| `empty_activities.csv` | Rows with no activity text at all |
| `embedding_low_confidence.csv` | Rows where embedding score was below threshold |

---

## LLM audit (optional)

The LLM audit re-examines uncertain rows using Mistral and can reclassify rows that were stuck in `others`.

### Step 1 — Install and start Ollama

Download from [https://ollama.com](https://ollama.com) then run:

```bash
ollama serve
```

### Step 2 — Pull the Mistral model

```bash
ollama pull mistral
```

### Step 3 — Run the audit

Test with 20 rows first:

```bash
python -m segmentation.llm_full_auditor
```

Run on all risky rows:

Edit the bottom of `segmentation/llm_full_auditor.py` and set `limit=None`, then run again. The audit resumes automatically if interrupted — already audited rows are skipped.

---

## Improving accuracy over time

The fastest way to improve classification accuracy is to grow `knowledge/validated_examples.csv`.

### Step 1 — Review the output

Open `data/output/rne_companies_segmented.csv` and look at rows where `category = others` or `needs_review = True`.

### Step 2 — Add corrections

Add correct classifications to `knowledge/validated_examples.csv`:

```
activity,category
Commerce de matériel informatique,retail
Clinique pédiatrique,healthcare
```

### Step 3 — Rebuild RAG and rerun

```bash
python run.py --skip-extraction --rebuild-rag
```

The validated examples layer runs first on every row, so your corrections are applied immediately and permanently.

---

## Streamlit dashboard

```bash
python run.py --dashboard
```

Opens a browser interface where you can:
- Upload a CSV and run segmentation with one click
- View category distribution charts
- Browse and filter results
- Download output files
- See the review queue

---

## FastAPI server

```bash
python run.py --api
```

Server starts at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

| Endpoint | Method | Description |
|---|---|---|
| `/pipeline/run` | POST | Run full pipeline (extraction + segmentation) |
| `/pipeline/segment` | POST | Upload CSV and run segmentation |
| `/pipeline/status` | GET | Check if pipeline is running |
| `/results/summary` | GET | Get classification summary |
| `/results/download` | GET | Download segmented CSV |
| `/results/download/audit` | GET | Download audit CSV |
| `/results/download/review` | GET | Download review CSV |
| `/pipeline/llm-audit` | POST | Trigger LLM audit on risky rows |

---

## Adding new pipeline layers

The pipeline is designed to be extended. To add a new layer:

1. Create your module in a new folder, e.g. `scoring/`
2. Open `pipeline/runner.py`
3. Write a `_run_scoring(ctx)` function
4. Add it to the `PIPELINE_STEPS` list

Nothing else needs to change. `run.py`, the API, and the dashboard all pick it up automatically.

---

## All available run.py options

```
--pdf-folder PATH       Folder containing PDFs to extract
--input PATH            Path to rne_companies.csv (default: data/input/rne_companies.csv)
--skip-extraction       Skip PDF extraction, run segmentation only
--rebuild-rag           Force rebuild of RAG knowledge base
--llm-audit             Run LLM audit after segmentation (requires Ollama)
--llm-limit N           Limit LLM audit to N rows
--keep-mixed            Keep intermediate extraction files (for debugging)
--dashboard             Launch Streamlit dashboard
--api                   Launch FastAPI server
```
