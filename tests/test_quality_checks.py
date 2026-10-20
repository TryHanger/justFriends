"""Persistent runner behavior without executing external commands."""

import asyncio
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.routes import standards as routes
from app.db.base import Base
from app.db.models import CheckRunRecord
from app.services import quality_checks as checks


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(checks, "SessionLocal", factory)
    monkeypatch.setattr(checks, "_availability", lambda _id: (True, None))
    monkeypatch.setattr(checks, "_project_version", lambda: "test")
    yield factory
    engine.dispose()


def record(factory, id, check_id="backend-tests", status="passed", cases=None, counts=None):
    with factory.begin() as db:
        db.add(CheckRunRecord(id=id, check_id=check_id, status=status,
                              created_at=datetime.now(UTC),
                              finished_at=datetime.now(UTC) if status not in {"queued", "running"} else None,
                              environment="local",
                              summary="done", diagnostics="", cases=cases or [], counts=counts or {}))


def test_real_junit_result_is_saved_and_survives_new_session(monkeypatch, isolated):
    class Pool:
        def submit(self, fn, *args):
            fn(*args)

    class Process:
        returncode = 0
        def wait(self, **_kwargs):
            return 0

    def command(_id, temporary):
        xml = temporary / "junit.xml"
        xml.write_text('<testsuite><testcase classname="api" name="valid" time="0.2"/>'
                       '<testcase classname="api" name="invalid" time="0.1">'
                       '<skipped message="optional"/></testcase></testsuite>', encoding="utf-8")
        return ["fixed-tool"], Path.cwd(), xml

    monkeypatch.setattr(checks, "_pool", Pool())
    monkeypatch.setattr(checks, "_command", command)
    monkeypatch.setattr(checks.subprocess, "Popen", lambda *a, **k: Process())
    run = checks.start("backend-tests")
    assert run["status"] == "skipped"
    assert run["counts"] == {"passed": 1, "failed": 0, "skipped": 1}
    assert checks.get_run(run["id"])["cases"][1]["name"] == "api::invalid"
    assert checks.history()[0]["id"] == run["id"]


def test_junit_error_counts_as_failed_test(monkeypatch, isolated):
    class Pool:
        def submit(self, fn, *args):
            fn(*args)

    class Process:
        returncode = 1
        def wait(self, **_kwargs):
            return 1

    def command(_id, temporary):
        xml = temporary / "junit.xml"
        xml.write_text('<testsuite><testcase classname="api" name="broken" time="0.1">'
                       '<error message="setup failed"/></testcase></testsuite>', encoding="utf-8")
        return ["fixed-tool"], Path.cwd(), xml

    monkeypatch.setattr(checks, "_pool", Pool())
    monkeypatch.setattr(checks, "_command", command)
    monkeypatch.setattr(checks.subprocess, "Popen", lambda *a, **k: Process())
    run = checks.start("backend-tests")
    assert run["status"] == "failed"
    assert run["counts"] == {"passed": 0, "failed": 1, "skipped": 0}
    assert run["cases"][0]["status"] == "error"


def test_recovery_marks_only_unfinished_runs(isolated):
    record(isolated, "queued", status="queued")
    record(isolated, "running", status="running")
    record(isolated, "finished")
    checks.recover_interrupted()
    assert checks.get_run("queued")["status"] == "interrupted"
    assert checks.get_run("running")["status"] == "interrupted"
    assert checks.get_run("finished")["status"] == "passed"


def test_comparison_uses_case_identifiers_and_rejects_other_tools(isolated):
    record(isolated, "a", cases=[{"name": "valid", "status": "failed"},
                                 {"name": "removed", "status": "passed"}],
           counts={"passed": 1, "failed": 1, "skipped": 0})
    record(isolated, "b", cases=[{"name": "valid", "status": "passed"},
                                 {"name": "added", "status": "failed"}],
           counts={"passed": 1, "failed": 1, "skipped": 0})
    record(isolated, "c", check_id="python-static")
    result = checks.compare("a", "b")
    assert result["became_passed"] == ["valid"]
    assert result["appeared"] == ["added"]
    assert result["disappeared"] == ["removed"]
    assert result["count_delta"]["passed"] == 0
    assert not checks.compare("a", "c")["comparable"]


def test_product_measurements_use_cases_and_keep_missing_evidence_visible(isolated):
    record(isolated, "backend", cases=[
        {"name": "good", "status": "passed"},
        {"name": "bad", "status": "failed"},
        {"name": "optional", "status": "skipped"},
    ])
    record(isolated, "ruff", check_id="python-static", status="failed", cases=[
        {"name": "F401", "status": "failed"},
    ])
    report = checks.product_measurements()
    by_id = {item["id"]: item for item in report["measurements"]}
    assert by_id["backend-pass-share"]["value"] == 50.0
    assert by_id["backend-pass-share"]["denominator"] == 2
    assert by_id["backend-pass-share"]["skipped"] == 1
    assert by_id["backend-pass-share"]["source_run_id"] == "backend"
    assert by_id["ruff-findings"]["value"] == 1.0
    assert by_id["frontend-pass-share"]["state"] == "not_measured"
    assert by_id["typescript-errors"]["value"] is None


def test_product_measurements_compare_two_real_runs(isolated):
    record(isolated, "older", cases=[
        {"name": "one", "status": "passed"}, {"name": "two", "status": "failed"},
    ])
    record(isolated, "newer", status="skipped", cases=[
        {"name": "one", "status": "passed"}, {"name": "two", "status": "passed"},
        {"name": "optional", "status": "skipped"},
    ])
    item = next(item for item in checks.product_measurements()["measurements"]
                if item["id"] == "backend-pass-share")
    assert item["value"] == 100.0
    assert item["previous_value"] == 50.0
    assert item["source_run_id"] == "newer"
    assert item["previous_run_id"] == "older"
    assert item["skipped"] == 1


def test_failed_tool_without_structured_result_is_not_zero_findings(isolated):
    record(isolated, "ruff-error", check_id="python-static", status="failed")
    report = checks.product_measurements()
    ruff = next(item for item in report["measurements"] if item["id"] == "ruff-findings")
    assert ruff["state"] == "not_measured"
    assert ruff["value"] is None


def test_runner_rejects_unknown_id_and_concurrency(isolated):
    with pytest.raises(Exception) as unknown:
        checks.start("user-command")
    assert unknown.value.status_code == 404
    assert checks._lock.acquire(blocking=False)
    try:
        with pytest.raises(Exception) as busy:
            checks.start("backend-tests")
        assert busy.value.status_code == 409
    finally:
        checks._lock.release()


def test_timeout_is_persisted_without_false_success(monkeypatch, isolated):
    record(isolated, "timeout", status="queued")
    monkeypatch.setattr(checks, "_command", lambda _id, temporary:
                        (["fixed-tool"], Path.cwd(), temporary / "junit.xml"))
    class Process:
        def wait(self, **_kwargs):
            raise subprocess.TimeoutExpired(["fixed-tool"], 1)
    monkeypatch.setattr(checks.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(checks, "_stop_tree", lambda _process: None)
    assert checks._lock.acquire(blocking=False)
    checks._execute("timeout", "backend-tests")
    assert checks.get_run("timeout")["status"] == "timeout"


def test_process_launch_error_is_saved_without_exposing_command(monkeypatch, isolated):
    record(isolated, "launch-error", status="queued")
    monkeypatch.setattr(checks, "_command", lambda _id, temporary:
                        (["fixed-tool"], Path.cwd(), temporary / "junit.xml"))
    def fail(*_args, **_kwargs):
        raise OSError("runner unavailable")
    monkeypatch.setattr(checks.subprocess, "Popen", fail)
    assert checks._lock.acquire(blocking=False)
    checks._execute("launch-error", "backend-tests")
    result = checks.get_run("launch-error")
    assert result["status"] == "error"
    assert "fixed-tool" not in result["diagnostics"]


def test_frontend_worker_report_is_saved_as_real_cases(monkeypatch, isolated):
    record(isolated, "frontend-worker", check_id="frontend-tests", status="queued")
    monkeypatch.setattr(checks, "_frontend_local_available", lambda: False)
    called = []
    def worker(method, path, timeout):
        called.append((method, path, timeout))
        return {"exit_code": 0, "output": "tests passed", "timeout": False,
                "report": {"testResults": [{"assertionResults": [
                    {"fullName": "renders checks", "status": "passed", "duration": 4},
                ]}]}}
    monkeypatch.setattr(checks, "_worker_request", worker)
    assert checks._lock.acquire(blocking=False)
    checks._execute("frontend-worker", "frontend-tests")
    run = checks.get_run("frontend-worker")
    assert called[0][:2] == ("POST", "/run/frontend-tests")
    assert run["status"] == "passed"
    assert run["counts"] == {"passed": 1, "failed": 0, "skipped": 0}
    assert run["cases"][0]["name"] == "renders checks"


def test_frontend_worker_timeout_is_not_reported_as_success(monkeypatch, isolated):
    record(isolated, "frontend-timeout", check_id="typescript", status="queued")
    monkeypatch.setattr(checks, "_frontend_local_available", lambda: False)
    monkeypatch.setattr(checks, "_worker_request", lambda *_args:
                        {"exit_code": None, "output": "timed out", "timeout": True})
    assert checks._lock.acquire(blocking=False)
    checks._execute("frontend-timeout", "typescript")
    assert checks.get_run("frontend-timeout")["status"] == "timeout"


def test_production_startup_does_not_create_runner_table(monkeypatch):
    import app.main as main

    created = []
    monkeypatch.setattr(main, "settings", SimpleNamespace(environment="production",
                                                           quality_runner_enabled=False))
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda bind, tables: created.extend(tables))
    async def startup():
        async with main.lifespan(None):
            pass
    asyncio.run(startup())
    assert "quality_check_runs" not in {table.name for table in created}


def test_secret_redaction_and_diagnostic_parser(monkeypatch):
    monkeypatch.setenv("TEST_SECRET", "very-private-token")
    assert "very-private-token" not in checks._sanitize("token=very-private-token")
    findings = checks._parse_cases("python-static", None, '[{"filename":"app/a.py",'
        '"location":{"row":4},"code":"F401","message":"unused"}]')
    assert findings[0]["name"] == "a.py:4:F401"
    assert checks._parse_cases("typescript", None, "src/App.tsx(2,3): error TS1001: bad")[0]["status"] == "failed"


def test_api_requires_local_page_and_known_check(monkeypatch, isolated):
    settings = SimpleNamespace(environment="local", quality_runner_enabled=True,
                               cors_origins=["http://localhost:5173"],
                               database_url="sqlite:///test.db")
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(routes.router, prefix="/standards")
    with TestClient(app) as client:
        assert client.post("/standards/checks/backend-tests/runs").status_code == 403
        local_headers = {"X-Quality-Local": "1", "Origin": "http://localhost:8080"}
        assert client.post("/standards/checks/backend-tests/runs",
                           headers={"X-Quality-Local": "1", "Origin": "https://evil.example"}).status_code == 403
        assert client.post("/standards/checks/backend-tests/runs",
                           headers={**local_headers, "Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.post("/standards/checks/not-a-tool/runs",
                           headers=local_headers).status_code == 404
        assert client.get("/standards/checks/runs/missing",
                          headers=local_headers).status_code == 404
        assert len(client.get("/standards/checks").json()) == 5
        assert client.get("/standards/quality/measurements").status_code == 403
        measurement = client.get("/standards/quality/measurements",
                                 headers=local_headers)
        assert measurement.status_code == 200
        assert measurement.json()["standard"] == "ISO/IEC 25023:2016"
    settings.environment = "production"
    with TestClient(app) as client:
        assert client.get("/standards/checks/runs/history",
                          headers=local_headers).status_code == 403
