"""Quality endpoint contracts; pytest subprocess is the only mocked boundary."""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import standards


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(standards.router, prefix="/standards")
    with TestClient(app) as test_client:
        yield test_client


def stub_pytest(monkeypatch, xml, exit_code=0):
    def run(command, **kwargs):
        assert command[0] == sys.executable
        assert command[1:5] == ["-X", "utf8", "-m", "pytest"]
        assert "-p" in command and "no:cacheprovider" in command
        assert kwargs["timeout"] == 60
        assert Path(kwargs["cwd"]).is_absolute()
        assert Path(command[5]).is_absolute()
        assert Path(command[5]) == Path(kwargs["cwd"]) / "tests"
        xml_arg = next(arg for arg in command if arg.startswith("--junitxml="))
        base_arg = next(arg for arg in command if arg.startswith("--basetemp="))
        assert Path(base_arg.split("=", 1)[1]).parent == Path(xml_arg.split("=", 1)[1]).parent
        Path(xml_arg.split("=", 1)[1]).write_text(xml, encoding="utf-8")
        return subprocess.CompletedProcess(command, exit_code, "", "")

    monkeypatch.setattr(subprocess, "run", run)


@pytest.mark.parametrize(
    ("xml", "exit_code", "expected"),
    [
        (
            ('<testsuites><testsuite><testcase name="a" time="0.1"/>'
             '<testcase name="b" time="0.2"/></testsuite></testsuites>'),
            0,
            ("PASS", 2, 2, "passed=2", "failed=0", "errors=0", "skipped=0"),
        ),
        (
            ('<testsuites><testsuite><testcase name="a"/>'
             '<testcase name="b"><skipped/></testcase></testsuite></testsuites>'),
            0,
            ("INCOMPLETE", 2, 1, "passed=1", "failed=0", "errors=0", "skipped=1"),
        ),
        (
            ('<testsuites><testsuite><testcase name="a"/>'
             '<testcase name="b"><failure/></testcase>'
             '<testcase name="c"><error/></testcase>'
             '<testcase name="d"><skipped/></testcase></testsuite></testsuites>'),
            1,
            ("FAIL", 4, 1, "passed=1", "failed=1", "errors=1", "skipped=1"),
        ),
    ],
)
def test_quality_report_counts_testcases_once(client, monkeypatch, xml, exit_code, expected):
    stub_pytest(monkeypatch, xml, exit_code)
    response = client.post("/standards/quality/run")
    assert response.status_code == 200, response.text
    report = response.json()
    status, total, passed, *details = expected
    assert report["overall_status"] == status
    assert report["total_tests"] == total
    assert report["passed_tests"] == passed
    assert len(report["metrics"]) == 1
    metric = report["metrics"][0]
    assert metric["characteristic"] == "Test pass rate"
    assert metric["score"] == pytest.approx(100 * passed / total)
    assert metric["passed"] is (status == "PASS")
    assert all(detail in metric["details"] for detail in details)
    assert "duration=" in metric["details"]


@pytest.mark.parametrize("xml", ["", "<not xml", "<testsuite/>"])
def test_quality_report_rejects_missing_or_bad_results(client, monkeypatch, xml):
    def run(command, **kwargs):
        if xml:
            path = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
            Path(path).write_text(xml, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    response = client.post("/standards/quality/run")
    assert response.status_code == 503
    assert "10" not in response.json()["detail"]


def test_quality_report_rejects_missing_runner(client, monkeypatch):
    def missing_runner(*args, **kwargs):
        raise FileNotFoundError("private/path/pytest")

    monkeypatch.setattr(subprocess, "run", missing_runner)
    response = client.post("/standards/quality/run")
    assert response.status_code == 503
    assert "private/path" not in response.json()["detail"]


def test_quality_report_rejects_missing_pytest_module(client, monkeypatch):
    def missing_module(command, **kwargs):
        return subprocess.CompletedProcess(command, 4, b"", b"No module named pytest")

    monkeypatch.setattr(subprocess, "run", missing_module)
    response = client.post("/standards/quality/run")
    assert response.status_code == 503
    assert "No module" not in response.json()["detail"]


def test_quality_report_times_out_safely(client, monkeypatch):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    response = client.post("/standards/quality/run")
    assert response.status_code == 504


def test_quality_report_rejects_invalid_runner_exit(client, monkeypatch):
    stub_pytest(monkeypatch, '<testsuite><testcase name="a"/></testsuite>', 3)
    response = client.post("/standards/quality/run")
    assert response.status_code == 503


def test_quality_report_rejects_missing_tests(client, monkeypatch, tmp_path):
    from app.services import quality_checks

    monkeypatch.setattr(quality_checks, "_repository", tmp_path)
    assert client.post("/standards/quality/run").status_code == 503


def test_quality_report_counts_teardown_error_once(client, monkeypatch):
    xml = (
        '<testsuites><testsuite tests="5" errors="2" failures="1" skipped="1">'
        '<testcase name="pass"/>'
        '<testcase name="fail"><failure/></testcase>'
        '<testcase name="skip"><skipped/></testcase>'
        '<testcase name="setup"><error/></testcase>'
        '<testcase name="body-passed-teardown-error"><error/></testcase>'
        '</testsuite></testsuites>'
    )
    stub_pytest(monkeypatch, xml, 1)
    response = client.post("/standards/quality/run")
    assert response.status_code == 200
    report = response.json()
    assert (report["total_tests"], report["passed_tests"], report["overall_status"]) == (
        5, 1, "FAIL"
    )
    assert "errors=2" in report["metrics"][0]["details"]


def test_quality_report_busy_lock_and_releases_after_error(client, monkeypatch):
    calls = 0

    def run(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            busy = client.post("/standards/quality/run")
            assert busy.status_code == 409
            raise FileNotFoundError("pytest")
        path = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
        Path(path).write_text('<testsuite><testcase name="a"/></testsuite>', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    assert client.post("/standards/quality/run").status_code == 503
    assert client.post("/standards/quality/run").status_code == 200


def test_failed_rerun_clears_prior_passing_lifecycle_evidence(client, monkeypatch):
    from app.services import quality_checks

    stub_pytest(monkeypatch, '<testsuite><testcase name="a"/></testsuite>')
    assert client.post("/standards/quality/run").status_code == 200
    previous = client.get("/standards/lifecycle").json()
    before = next(p for p in previous["processes"] if p["name"] == "Runtime tests")
    assert before["status"] == "PASS"
    assert previous["last_checked_at"]

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("private/path/pytest")

    monkeypatch.setattr(quality_checks.subprocess, "run", unavailable)
    assert client.post("/standards/quality/run").status_code == 503
    after = client.get("/standards/lifecycle").json()
    runtime = next(p for p in after["processes"] if p["name"] == "Runtime tests")
    assert runtime["status"] == "unavailable"
    assert "unavailable" in runtime["details"].lower()
    assert "passed=" not in runtime["details"]
    assert after["last_checked_at"]
