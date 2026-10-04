"""Measured pytest results for the on-demand quality endpoint."""

import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from fastapi import HTTPException

from app.schemas.standards import QualityMetric, QualityReport

_run_lock = Lock()
_snapshot_lock = Lock()
_repository = Path(__file__).resolve().parents[2]
_latest_report: QualityReport | None = None
_latest_status: str | None = None
_latest_checked_at: str | None = None
_latest_error: str | None = None


def _record_snapshot(report: QualityReport | None, status: str, error: str | None = None) -> None:
    global _latest_report, _latest_status, _latest_checked_at, _latest_error
    with _snapshot_lock:
        _latest_report = report
        _latest_status = status
        _latest_checked_at = None if status == "running" else datetime.now(UTC).isoformat()
        _latest_error = error


def get_quality_snapshot() -> tuple[QualityReport | None, str | None, str | None, str | None]:
    """Return one process's latest on-demand run; restarting a worker loses it."""
    with _snapshot_lock:
        return _latest_report, _latest_status, _latest_checked_at, _latest_error


def _counts_from_junit(path: Path) -> tuple[int, int, int, int]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise HTTPException(503, "Test results are unavailable or invalid.") from exc

    if root.tag not in {"testsuite", "testsuites"}:
        raise HTTPException(503, "Test results are unavailable or invalid.")

    passed = failed = errors = skipped = 0
    for case in root.iter("testcase"):
        outcomes = {child.tag for child in case}
        # A passing test body can still have a teardown error in JUnit XML.
        if "error" in outcomes:
            errors += 1
        elif "failure" in outcomes:
            failed += 1
        elif "skipped" in outcomes:
            skipped += 1
        else:
            passed += 1
    return passed, failed, errors, skipped


def run_quality_checks() -> QualityReport:
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "A quality check is already running.")

    _record_snapshot(None, "running", "Automated tests are running.")
    try:
        tests_path = _repository / "tests"
        if not tests_path.is_dir():
            raise HTTPException(503, "The test suite is unavailable.")

        with tempfile.TemporaryDirectory(prefix="quality-check-") as temp_dir:
            temp_path = Path(temp_dir)
            xml_path = temp_path / "results.xml"
            command = [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "pytest",
                str(tests_path),
                "-p",
                "no:cacheprovider",
                f"--basetemp={temp_path / 'pytest'}",
                f"--junitxml={xml_path}",
            ]
            start = time.monotonic()
            try:
                result = subprocess.run(
                    command,
                    cwd=_repository,
                    timeout=60,
                    capture_output=True,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(504, "The test suite timed out.") from exc
            except OSError as exc:
                raise HTTPException(503, "The test runner is unavailable.") from exc
            duration = time.monotonic() - start

            if result.returncode not in (0, 1):
                raise HTTPException(503, "The test runner could not complete.")

            passed, failed, errors, skipped = _counts_from_junit(xml_path)
            total = passed + failed + errors + skipped
            if total == 0 or (result.returncode == 0 and failed + errors) or (
                result.returncode == 1 and not failed + errors
            ):
                raise HTTPException(503, "Test results are unavailable or inconsistent.")

        status = "FAIL" if failed or errors else "INCOMPLETE" if skipped else "PASS"
        metric = QualityMetric(
            characteristic="Test pass rate",
            score=passed / total * 100,
            passed=status == "PASS",
            details=(
                f"passed={passed}, failed={failed}, errors={errors}, skipped={skipped}, "
                f"duration={duration:.2f}s"
            ),
        )
        report = QualityReport(
            metrics=[metric],
            overall_status=status,
            total_tests=total,
            passed_tests=passed,
        )
        _record_snapshot(report, status)
        return report
    except HTTPException as exc:
        _record_snapshot(None, "unavailable", str(exc.detail))
        raise
    except Exception:
        _record_snapshot(None, "unavailable", "The quality check could not complete.")
        raise
    finally:
        _run_lock.release()
