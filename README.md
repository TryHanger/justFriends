# Metaphor Analyzer API

Python backend for the research project on automatic metaphor detection and cross-cultural comparison in Chinese and Kazakh poetry.

## What this starter provides

- FastAPI service with health, text-analysis, and document-upload endpoints.
- GPT-backed analysis with schema-validated JSON output.
- Text extraction from TXT, text-based PDF, and DOCX.
- SQLAlchemy persistence for submitted analyses.
- Pollable background job states, aggregate comparison, and JSON/CSV exports.
- A documented integration boundary for Arslan's NLP/embedding models and Nikita's frontend.

Scanned-PDF OCR and DOC/ODT/RTF conversion are intentionally left as the next document-processing integration. Text-based PDF extraction is already supported. Jobs currently use FastAPI's in-process background runner for the MVP; use a durable worker queue before deploying multiple API processes.

## Run locally

1. Create a virtual environment and install the project: `python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'`.
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
3. Start the API: `uvicorn app.main:app --reload`.
4. Open `/docs` for the interactive API reference.

The service starts without an API key so health checks and documentation remain available. Without `OPENAI_API_KEY`, submitted jobs move to `failed` with a configuration error.

For a shared local environment, copy `.env.example` to `.env`, set `OPENAI_API_KEY`, then run `docker compose up --build`.

## API contract

- `GET /api/v1/health` — service and database status.
- `POST /api/v1/analyze` — submit text and receive a job ID.
- `POST /api/v1/analyze/file` — upload `.txt`, text PDF, or `.docx` and receive a job ID.
- `GET /api/v1/analyses/{analysis_id}` — poll status and retrieve a finished result.
- `GET /api/v1/analyses` — list recent analyses.
- `POST /api/v1/compare` — compare descriptive counts for Chinese and Kazakh analyses.
- `GET /api/v1/analyses/{analysis_id}/export?format=json|csv` — download one finished result.

Analysis requests return HTTP 202 and an `analysis_id`. The client polls the supplied status URL; the completed result contains detected language, model version, and metaphor spans with character offsets, labels, source/target domains, confidence, and a short rationale. See [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) for examples.

## Module handoff

- Arslan can implement the NLP detector and cross-language matcher behind `app/services/analyzer.py`; keep the `AnalysisResult` contract stable.
- Nikita can build the UI against the OpenAPI schema at `/openapi.json` and the endpoints above.
- The API owner maintains document parsing, persistence, and integration tests.

## Configuration

All runtime settings come from environment variables. Do not commit `.env` or API keys. Set `DATABASE_URL` to a PostgreSQL URL for shared deployments; SQLite is the local default.
The default CORS allowlist supports Vite on localhost port 5173; set `CORS_ORIGINS` to a JSON array when the frontend uses another origin.
