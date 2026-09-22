"""Existing HTTP contract with in-memory SQLite; no model or paid provider calls."""

import json
from pathlib import Path

import pytest

from app.nlp.contracts import output_schema, validate_result
from app.nlp.corpus import Poem
from app.schemas.analysis import AnalysisJobResponse, AnalysisStatusResponse
from app.schemas.comparison import ComparisonMatch, ComparisonResult


def test_generated_contracts_and_examples():
    root = Path(__file__).resolve().parents[1]
    assert json.loads((root / "contracts/llm-output.schema.json").read_text()) == output_schema()
    assert (
        json.loads((root / "contracts/corpus.schema.json").read_text()) == Poem.model_json_schema()
    )
    for language in ("zh", "kk"):
        path = root / "contracts/examples" / f"analyze-{language}"
        request = json.loads(Path(str(path) + ".request.json").read_text(encoding="utf-8"))
        AnalysisJobResponse.model_validate_json(
            Path(str(path) + ".response.json").read_text(encoding="utf-8")
        )
        response = AnalysisStatusResponse.model_validate_json(
            Path(str(path) + ".completed.json").read_text(encoding="utf-8")
        )
        validate_result(request["text"], language, response.result)


def test_api_persist_retrieve_and_errors(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.core.config import get_settings
    from app.services.analyzer import get_pipeline
    from app.api.v1.routes import analyses as analysis_routes
    from app.api.v1.routes.analyses import router
    from app.db.base import Base
    from app.db.session import get_db
    from app.services import analysis_jobs

    monkeypatch.setenv("NLP_BACKEND", "baseline")
    get_settings.cache_clear()
    get_pipeline.cache_clear()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(analysis_jobs, "SessionLocal", sessions)

    def db():
        with sessions() as session:
            yield session

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_db] = db
    try:
        with TestClient(application) as client:
            text = "🌙\r\nӨмір өзені тоқтамай ағады."
            response = client.post("/api/v1/analyze", json={"text": text, "language": "kk"})
            assert response.status_code == 202, response.text
            job = response.json()
            assert job["status"] == "queued"
            completed = client.get(job["status_url"]).json()
            assert completed["status"] == "completed", completed
            data = completed["result"]
            assert data["model_version"] == "lexical-demo-v1"
            assert text[data["metaphors"][0]["start"] : data["metaphors"][0]["end"]] == "Өмір өзені"
            assert client.get(job["status_url"]).json() == completed
            uploaded = client.post(
                "/api/v1/analyze/file",
                data={"language": "kk"},
                files={"file": ("poem.txt", text.encode("utf-8"), "text/plain")},
            )
            assert uploaded.status_code == 202, uploaded.text
            uploaded_result = client.get(uploaded.json()["status_url"]).json()
            assert uploaded_result["status"] == "completed", uploaded_result
            assert uploaded_result["result"]["metaphors"] == data["metaphors"]
            history = client.get("/api/v1/analyses").json()
            assert isinstance(history["items"], list) and history["limit"] == 20

            zh_job = client.post(
                "/api/v1/analyze", json={"text": "心海泛起波浪。", "language": "zh"}
            ).json()
            zh_done = client.get(zh_job["status_url"]).json()
            assert zh_done["status"] == "completed", zh_done

            class FakeMatcher:
                def compare(self, queries, candidates, k):
                    assert k == 2
                    assert queries and candidates
                    assert queries[0].language != candidates[0].language
                    return ComparisonResult(
                        model_version="fake-e5",
                        matches=[
                            ComparisonMatch(
                                query_id=queries[0].id,
                                candidate_id=candidates[0].id,
                                similarity=0.81,
                                rank=1,
                            )
                        ],
                        warnings=["Similarity is not cultural equivalence."],
                    )

            monkeypatch.setattr(analysis_routes, "get_semantic_matcher", lambda: FakeMatcher())
            semantic = client.post(
                "/api/v1/compare/semantic?k=2",
                json={"analysis_ids": [job["analysis_id"], zh_job["analysis_id"]]},
            )
            assert semantic.status_code == 200, semantic.text
            assert semantic.json()["model_version"] == "fake-e5"
            assert len(semantic.json()["matches"]) == 2  # zh→kk and kk→zh

            assert client.post("/api/v1/analyze", json={"text": "   "}).status_code == 422
            assert (
                client.post("/api/v1/analyze", json={"text": "x", "language": "en"}).status_code
                == 422
            )
            assert client.get("/api/v1/analyses/9999").status_code == 404
            ambiguous = client.post("/api/v1/analyze", json={"text": "hello"})
            assert ambiguous.status_code == 202
            assert client.get(ambiguous.json()["status_url"]).json()["status"] == "failed"
            monkeypatch.setenv("NLP_BACKEND", "openai")
            monkeypatch.setenv("OPENAI_API_KEY", "")
            get_settings.cache_clear()
            get_pipeline.cache_clear()
            missing_key = client.post("/api/v1/analyze", json={"text": "心海", "language": "zh"})
            assert missing_key.status_code == 202
            failed = client.get(missing_key.json()["status_url"]).json()
            assert failed["status"] == "failed" and failed["result"] is None
            assert failed["error"]
    finally:
        get_pipeline.cache_clear()
        get_settings.cache_clear()
        engine.dispose()
