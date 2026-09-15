# API contract for frontend integration

Base URL: `http://localhost:8000/api/v1`. Interactive schema: `http://localhost:8000/docs`; machine-readable schema: `/openapi.json`.

The default CORS policy allows the Vite development origins `http://localhost:5173` and `http://127.0.0.1:5173`. Set `CORS_ORIGINS` to a JSON array to use another frontend origin.

## Submit text

`POST /analyze` with `Content-Type: application/json`:

```json
{
  "text": "Poem in Chinese or Kazakh",
  "language": "auto"
}
```

`language` accepts `auto`, `zh`, or `kk`. The API returns HTTP `202 Accepted`:

```json
{
  "analysis_id": 42,
  "status": "queued",
  "status_url": "/api/v1/analyses/42"
}
```

Poll `status_url` until `status` becomes `completed` or `failed`.

## Upload a document

`POST /analyze/file` as `multipart/form-data`:

- `file`: `.txt`, text-based `.pdf`, or `.docx`;
- `language`: optional `auto`, `zh`, or `kk`.

The response uses the same `202` job contract. The upload limit defaults to 20 MB and can be changed with `MAX_UPLOAD_MB`. Scanned PDFs return `422` until OCR is connected.

## Poll one analysis

`GET /analyses/42` returns the job status. When complete, `result` contains:

```json
{
  "analysis_id": 42,
  "status": "completed",
  "source_name": null,
  "created_at": "2026-09-15T12:00:00+00:00",
  "result": {
    "language": "kk",
    "model_version": "gpt-5.6-terra",
    "metaphors": [
      {
        "text": "source span",
        "start": 0,
        "end": 11,
        "label": "metaphor",
        "source_domain": "nature",
        "target_domain": "emotion",
        "confidence": 0.86,
        "rationale": "Short context-based explanation."
      }
    ]
  },
  "error": null
}
```

Offsets use zero-based Python Unicode character indexes; `end` is exclusive. The returned phrase equals the exact source slice `[start:end]`.

`GET /analyses?limit=20&offset=0` lists the newest jobs first. `limit` ranges from 1 to 100.

## Compare completed analyses

`POST /compare`:

```json
{
  "analysis_ids": [42, 43, 44]
}
```

At least one completed Chinese (`zh`) and one completed Kazakh (`kk`) analysis are required. The response groups descriptive counts by language, label, source domain, and target domain. These counts do not claim one-to-one semantic equivalence; the embeddings module can later add semantic matches.

## Export results

- `GET /analyses/42/export?format=json`
- `GET /analyses/42/export?format=csv`

Both return a downloadable file and require a completed analysis.

## Status and error handling

| Status | Meaning | Frontend action |
|---:|---|---|
| 202 | Job accepted | Store `analysis_id`; poll `status_url` |
| 200 | Read/list/compare/export succeeded | Render payload or download file |
| 404 | Analysis ID does not exist | Show not found |
| 409 | Job unfinished or export unavailable | Continue polling or show current state |
| 413 | Upload exceeds configured limit | Ask user for a smaller file |
| 415 | Unsupported file extension | Show supported formats |
| 422 | Invalid request or no extractable text | Show validation details |
| 200 with `status: degraded` | Database health check failed | Show temporary service issue |

GPT failures, including missing API configuration, are stored as job state `failed`; the API keeps details generic so it does not expose keys or provider internals.
