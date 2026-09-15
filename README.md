# Metaphor Analyzer API

Python backend for the research project on automatic metaphor detection and cross-cultural comparison in Chinese and Kazakh poetry.

## What this starter provides

- FastAPI service with health, text-analysis, and document-upload endpoints.
- Configurable NLP analysis: lexical baseline, OpenAI, Ollama, local XLM-R, or hybrid.
- Text extraction from TXT, text-based PDF, and DOCX.
- SQLAlchemy persistence for submitted analyses.
- Arslan's NLP module, corpus/annotation tools, model training, evaluation, and embedding comparison.
- Versioned JSON examples and an integration contract for Nikita's frontend.

Scanned-PDF OCR and DOC/ODT/RTF conversion are intentionally left as the next document-processing integration. Text-based PDF extraction is already supported.

## Run locally

1. Create a virtual environment and install the project: `python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'`.
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
3. Start the API: `uvicorn app.main:app --reload`.
4. Open `/docs` for the interactive API reference.

The service starts without an API key so health checks and documentation remain available.
In the default OpenAI mode, analysis endpoints return HTTP 503 until `OPENAI_API_KEY` is
configured. Set `NLP_BACKEND=baseline` for offline demonstration without a key.

For a shared local environment, copy `.env.example` to `.env`, set `OPENAI_API_KEY`, then run `docker compose up --build`.

## API contract

- `GET /api/v1/health` — service and database status.
- `POST /api/v1/analyze` — analyze text. JSON body: `{"text":"...","language":"auto"}`.
- `POST /api/v1/analyze/file` — upload `.txt`, text PDF, or `.docx`; optional `language` form field.
- `GET /api/v1/analyses/{analysis_id}` — retrieve a saved analysis.

The analysis response contains an `analysis_id`, detected language, model version, and metaphor spans with character offsets, labels, source/target domains, confidence, and a short rationale. Offsets refer to the extracted original text.

## Module handoff

Arslan's NLP implementation and Russian setup guide: [docs/NLP.md](docs/NLP.md).
The versioned labels, domains, offset rules and integration examples are in
[docs/NLP_CONTRACT.md](docs/NLP_CONTRACT.md) and `contracts/`.
Run `python -m app.nlp demo` for an offline synthetic demonstration.
Set `NLP_BACKEND=baseline` for the existing analysis API to work without an API key;
other choices are `openai` (default), `ollama`, `xlmr`, and `hybrid`.
Neural models require `pip install -e '.[nlp]'` and trained/downloaded weights.

- Arslan maintains `app/nlp/`, taxonomy, annotation, model experiments, and the comparison module;
  `app/services/analyzer.py` connects analysis to the existing backend.
- Nikita can build the UI against the OpenAPI schema at `/openapi.json` and the endpoints above.
- The API owner maintains document parsing, persistence, and integration tests.

## Configuration

All runtime settings come from environment variables. Do not commit `.env` or API keys. Set `DATABASE_URL` to a PostgreSQL URL for shared deployments; SQLite is the local default.
