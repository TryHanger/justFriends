"""Behavioral checks for the standards dashboard, not copies of its implementation."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import standards as routes
from app.services.quality import run_quality_suite
from app.services.standards import STANDARDS, lifecycle_state, search_standards


@pytest.mark.parametrize("query,expected", [
    ("25010", "ISO/IEC 25010:2023"),
    ("АРХИТЕКТУРА", "ISO/IEC/IEEE 42010:2022"),
    ("сопровождения ПО", "ISO/IEC/IEEE 12207:2017"),
])
def test_search_finds_designation_domain_and_purpose_case_insensitively(query, expected):
    assert expected in [item.designation for item in search_standards(query)]


def test_search_no_match_and_domain_filter():
    assert search_standards("невероятный стандарт") == []
    assert all(item.domain == "Безопасность" for item in search_standards("", "безопасность"))


def test_catalog_has_required_organizations_and_unique_identifiers():
    assert len(STANDARDS) >= 10
    assert {"ISO", "IEC", "IEEE", "ISO/IEC/IEEE", "Национальный"} <= {
        organization for item in STANDARDS for organization in item.organization.split("/")
    } | {item.organization for item in STANDARDS}
    assert len({item.designation for item in STANDARDS}) == len(STANDARDS)
    assert all(item.source_url.startswith("https://") for item in STANDARDS)


def test_lifecycle_does_not_claim_user_validation_from_source_files(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("architecture")
    state = lifecycle_state(tmp_path)
    by_id = {item.id: item for item in state.processes}
    assert by_id["architecture"].status == "evidenced"
    assert by_id["validation"].status == "missing"
    assert state.readiness == "not_ready"
    assert any("пользовательских" in issue for issue in state.issues)


def test_lifecycle_tracks_real_artifacts_and_gaps(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "API_CONTRACT.md").write_text("contract")
    state = lifecycle_state(tmp_path)
    requirements = next(p for p in state.processes if p.id == "requirements")
    assert requirements.evidence == ["docs/API_CONTRACT.md"]
    assert requirements.gaps == []
    assert next(p for p in state.processes if p.id == "implementation").status == "missing"


def test_quality_runner_counts_junit_cases_without_guesses(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        path = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml=")))
        path.write_text('''<testsuite><testcase classname="api" name="ok"/>
          <testcase classname="api" name="bad"><failure message="wrong result"/></testcase>
          <testcase classname="api" name="later"><skipped message="dependency"/></testcase>
          </testsuite>''', encoding="utf-8")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr("app.services.quality.subprocess.run", fake_run)
    report = run_quality_suite(tmp_path)
    assert (report.total_tests, report.passed_tests, report.failed_tests, report.skipped_tests) == (3, 1, 1, 1)
    assert report.overall_status == "FAIL"
    assert report.cases[1].message == "wrong result"
    assert next(m for m in report.metrics if m.characteristic == "Security").status == "not_evaluated"


def test_quality_runner_reports_missing_junit_as_incomplete(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.quality.subprocess.run", lambda *a, **k: SimpleNamespace(
        returncode=2, stdout="collection failed", stderr=""))
    report = run_quality_suite(tmp_path)
    assert report.overall_status == "INCOMPLETE"
    assert report.total_tests == 0
    assert "collection failed" in report.limitations[-1]


def test_quality_endpoint_is_disabled_outside_local(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(environment="production"))
    app = FastAPI()
    app.include_router(routes.router, prefix="/standards")
    with TestClient(app) as client:
        assert client.post("/standards/quality/run").status_code == 403
        assert client.get("/standards/reference?query=25010").json()[0]["designation"] == "ISO/IEC 25010:2023"
        assert client.get("/standards/reference?query=none").json() == []


def test_lifecycle_route_returns_project_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "lifecycle_state", lambda: lifecycle_state(tmp_path))
    app = FastAPI()
    app.include_router(routes.router, prefix="/standards")
    with TestClient(app) as client:
        response = client.get("/standards/lifecycle")
    assert response.status_code == 200
    assert response.json()["readiness"] == "not_ready"
    assert len(response.json()["processes"]) >= 8
