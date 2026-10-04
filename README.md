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

1. Create a virtual environment and install the project: `python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev,quality]'` (PowerShell activation: `.\.venv\Scripts\Activate.ps1`).
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
- `POST /api/v1/compare/semantic?k=5` — rank metaphor candidates in both language directions with multilingual-e5.
- `GET /api/v1/analyses/{analysis_id}/export?format=json|csv` — download one finished result.
- `POST /api/v1/standards/quality/run` — run the bundled Python tests and report measured pass, failure, error, and skip counts. Only one run per API process can execute at a time.

Analysis requests return HTTP 202 and an `analysis_id`. The client polls the supplied status URL; the completed result contains detected language, model version, and metaphor spans with character offsets, labels, source/target domains, confidence, and a short rationale. See [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) for examples.

## Module handoff

Arslan's NLP module is implemented in `app/nlp/`. See [the NLP guide](docs/NLP.md)
for setup, annotation, training, and evaluation, and [the NLP contract](docs/NLP_CONTRACT.md)
for labels, domains, offsets, and examples matching the asynchronous API.
Run `python -m app.nlp demo` for an offline synthetic demonstration.
Set `NLP_BACKEND=baseline` to analyze without API keys; other modes are
`openai` (default), `ollama`, `xlmr`, and `hybrid`. Neural models require `.[nlp]`.

- Arslan maintains `app/nlp/`, taxonomy, annotation, model training, and semantic comparison;
  `app/services/analyzer.py` connects the detector to the background analysis jobs.
- Nikita can build the UI against the OpenAPI schema at `/openapi.json` and the endpoints above.
- The API owner maintains document parsing, persistence, and integration tests.

## Configuration

All runtime settings come from environment variables. Do not commit `.env` or API keys. Set `DATABASE_URL` to a PostgreSQL URL for shared deployments; SQLite is the local default.
The default CORS allowlist supports Vite on localhost port 5173; set `CORS_ORIGINS` to a JSON array when the frontend uses another origin.

The automated test report is a test pass rate, not ISO certification or a measure of performance. Its `INCOMPLETE` status means at least one test was skipped, even if every executed test passed. The optional neural-model test is skipped in the default Docker image because torch and transformers are not installed there; install the `nlp` extra in a separate environment to run it. The image includes the lightweight `quality` extra and the test fixtures required for the report.

## Document limits

Uploads are limited to `MAX_UPLOAD_MB` MiB of file data (20 MiB by default) and 100,000 characters of extracted text. The text limit applies to both analysis and library uploads, including DOCX tables. A longer document returns HTTP 422 before a job or library record is created. Split a long book into smaller excerpts before submitting it; automatic chunking is not implemented. DOCX paragraphs and tables are read in document order, including nested tables, without duplicating merged cells. Scanned images, headers and footers are not extracted.

## Quality checks and standards

Run the same checks used by CI:

```shell
python -m pip install -e '.[dev,quality]'
python -X utf8 -m ruff check app tests scripts
python -X utf8 -m pytest -q -rs
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

CI runs on pushes and pull requests; frontend lint warnings fail the job. The Standards page shows available project evidence and the last test run in that API process. File presence does not mean a document has passed review, and a configured workflow does not mean GitHub has run it successfully. See [the quality policy](docs/QUALITY.md) for check coverage, standards mapping and remaining manual assessments.
