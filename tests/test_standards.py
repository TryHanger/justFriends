"""Behavioral checks for the standards dashboard, not copies of its implementation."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import standards as routes
from app.services.quality import quality_snapshot, run_quality_suite
from app.services.standards import STANDARDS, lifecycle_state, search_standards, soa_architecture


@pytest.mark.parametrize("query,expected", [
    ("25010", "ISO/IEC 25010:2023"),
    ("АРХИТЕКТУРА", "ISO/IEC/IEEE 42010:2022"),
    ("сопровождения ПО", "ISO/IEC/IEEE 12207:2017"),
    ("18384", "ISO/IEC 18384-2:2016"),
    ("сервис-ориентированной", "ISO/IEC 18384-1:2016"),
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
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_example.py").write_text("def test_example(): pass")
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


def test_quality_runner_rejects_missing_junit(monkeypatch, tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_example.py").write_text("def test_example(): pass")
    monkeypatch.setattr("app.services.quality.subprocess.run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=b"", stderr=b""))
    with pytest.raises(Exception) as exc:
        run_quality_suite(tmp_path)
    assert getattr(exc.value, "status_code", None) == 503
    assert quality_snapshot()[0] == "unavailable"


def test_quality_runner_times_out_without_disclosing_paths(monkeypatch, tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_example.py").write_text("def test_example(): pass")

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("app.services.quality.subprocess.run", timeout)
    with pytest.raises(Exception) as exc:
        run_quality_suite(tmp_path)
    assert getattr(exc.value, "status_code", None) == 504
    assert "test_example.py" not in str(exc.value)


def test_quality_runner_rejects_concurrent_run():
    from app.services import quality

    assert quality._run_lock.acquire(blocking=False)
    try:
        with pytest.raises(Exception) as exc:
            run_quality_suite()
        assert getattr(exc.value, "status_code", None) == 409
    finally:
        quality._run_lock.release()


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


def test_soa_mapping_has_the_nine_layers_of_iso_18384_2():
    layers = soa_architecture().layers
    assert [layer.kind for layer in layers].count("horizontal") == 5
    assert [layer.kind for layer in layers].count("cross_cutting") == 4
    assert {layer.standard_name for layer in layers} >= {
        "Operational Systems Layer", "Consumer Layer", "Integration Layer", "Governance Layer"}


def test_soa_mapping_tracks_real_artifacts_and_does_not_claim_missing_layers(tmp_path):
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "App.tsx").write_text("app")
    state = soa_architecture(tmp_path)
    by_id = {layer.id: layer for layer in state.layers}
    assert by_id["consumer"].status == "partial"
    assert by_id["consumer"].evidence == ["frontend/src/App.tsx"]
    assert "Отсутствует frontend/src/api.ts" in by_id["consumer"].gaps
    assert by_id["operational"].status == "missing"
    assert state.alignment == "not_aligned"


def test_soa_gaps_that_files_cannot_close_keep_alignment_partial():
    state = soa_architecture()
    integration = next(layer for layer in state.layers if layer.id == "integration")
    assert integration.status == "partial"
    assert any("посредника" in gap for gap in integration.gaps)
    assert state.alignment == "partial"


def test_soa_route_returns_layers(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "soa_architecture", lambda: soa_architecture(tmp_path))
    app = FastAPI()
    app.include_router(routes.router, prefix="/standards")
    with TestClient(app) as client:
        response = client.get("/standards/soa")
    assert response.status_code == 200
    assert len(response.json()["layers"]) == 9
    assert response.json()["alignment"] == "not_aligned"
