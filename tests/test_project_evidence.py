from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import standards
from app.services import project_evidence, quality_checks


def client():
    app = FastAPI()
    app.include_router(standards.router, prefix="/standards")
    return TestClient(app)


def process(state, name):
    return next(item for item in state["processes"] if item["name"] == name)


def test_lifecycle_reports_missing_repository_artifacts_without_claiming_completion(monkeypatch, tmp_path):
    monkeypatch.setattr(project_evidence, "_repository", tmp_path)
    state = client().get("/standards/lifecycle").json()
    assert state["readiness"] == "Manual review required"
    assert process(state, "Requirements evidence")["status"] == "missing"
    assert "docs/API_CONTRACT.md" in process(state, "Requirements evidence")["details"]
    assert state["issues"]
    assert all(p["responsible"] == "Unassigned" for p in state["processes"])


def test_lifecycle_identifies_present_artifacts_as_evidence_only(monkeypatch, tmp_path):
    monkeypatch.setattr(project_evidence, "_repository", tmp_path)
    for name in ("docs/API_CONTRACT.md", "docs/NLP_CONTRACT.md", "app/main.py", "tests/test_nlp_api.py", ".github/workflows/quality.yml"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("artifact", encoding="utf-8")
    state = client().get("/standards/lifecycle").json()
    assert process(state, "Requirements evidence")["status"] == "evidence_found"
    assert process(state, "Implementation evidence")["status"] == "evidence_found"
    assert process(state, "CI evidence")["status"] == "evidence_found"
    assert state["readiness"] == "Manual review required"
    assert all(item["status"] != "completed" for item in state["processes"])


def test_lifecycle_never_runs_tests_on_get(monkeypatch, tmp_path):
    monkeypatch.setattr(project_evidence, "_repository", tmp_path)
    monkeypatch.setattr(quality_checks, "_latest_report", None)
    monkeypatch.setattr(quality_checks, "_latest_status", None)
    monkeypatch.setattr(quality_checks, "_latest_checked_at", None)
    monkeypatch.setattr(quality_checks, "_latest_error", None)
    monkeypatch.setattr(quality_checks.subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("runner called")))
    state = client().get("/standards/lifecycle").json()
    assert process(state, "Runtime tests")["status"] == "not_run"
    assert state["last_checked_at"] is None
