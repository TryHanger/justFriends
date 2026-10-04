"""Upload validation must happen before persistent jobs or model work."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.routes.analyses import router as analyses_router
from app.api.v1.routes.library import router as library_router
from app.db.base import Base
from app.db.models import AnalysisRecord, BookRecord
from app.db.session import get_db
from app.schemas.analysis import AnalysisResult
from app.services import analysis_jobs


@pytest.fixture
def upload_client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    calls = []

    def analyze_text(text, language):
        calls.append((text, language))
        return AnalysisResult(language="zh", model_version="test", metaphors=[])

    monkeypatch.setattr(analysis_jobs, "SessionLocal", sessions)
    monkeypatch.setattr(analysis_jobs, "analyze_text", analyze_text)

    def db():
        with sessions() as session:
            yield session

    app = FastAPI()
    app.include_router(analyses_router, prefix="/api/v1")
    app.include_router(library_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        yield client, sessions, calls
    engine.dispose()


@pytest.mark.parametrize("route", ["/api/v1/analyze/file", "/api/v1/library/books"])
def test_oversized_extracted_upload_creates_no_records_or_model_call(upload_client, route):
    client, sessions, calls = upload_client
    response = client.post(
        route,
        data={"language": "zh"},
        files={"file": ("poem.txt", ("x" * 100_001).encode(), "text/plain")},
    )

    assert response.status_code == 422, response.text
    assert "100000" in str(response.json()["detail"]).replace(",", "").replace("_", "")
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AnalysisRecord)) == 0
        assert db.scalar(select(func.count()).select_from(BookRecord)) == 0
    assert calls == []


@pytest.mark.parametrize("route", ["/api/v1/analyze/file", "/api/v1/library/books"])
def test_upload_at_extracted_limit_is_accepted(upload_client, route):
    client, sessions, calls = upload_client
    response = client.post(
        route,
        data={"language": "zh"},
        files={"file": ("poem.txt", ("  " + "x" * 100_000 + "  ").encode(), "text/plain")},
    )

    assert response.status_code == 202, response.text
    with sessions() as db:
        record = db.get(AnalysisRecord, response.json()["analysis_id"])
        assert len(record.source_text) == 100_000
        assert db.scalar(select(func.count()).select_from(BookRecord)) == int(route.endswith("books"))
    assert len(calls) == 1


@pytest.mark.parametrize("route", ["/api/v1/analyze/file", "/api/v1/library/books"])
def test_upload_rejects_invalid_language_before_persistence(upload_client, route):
    client, sessions, calls = upload_client
    response = client.post(
        route,
        data={"language": "en"},
        files={"file": ("poem.txt", b"text", "text/plain")},
    )

    assert response.status_code == 422, response.text
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AnalysisRecord)) == 0
        assert db.scalar(select(func.count()).select_from(BookRecord)) == 0
    assert calls == []
