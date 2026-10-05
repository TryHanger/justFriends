"""Reproducible test evidence for the project quality dashboard."""

import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from xml.etree import ElementTree

from fastapi import HTTPException

from app.schemas.standards import QualityCase, QualityMetric, QualityReport

ROOT = Path(__file__).resolve().parents[2]
_run_lock = Lock()
_snapshot_lock = Lock()
_last_status: str | None = None
_last_checked_at: str | None = None
_last_error: str | None = None


def quality_snapshot() -> tuple[str | None, str | None, str | None]:
    with _snapshot_lock:
        return _last_status, _last_checked_at, _last_error


def _set_snapshot(status: str, error: str | None = None) -> None:
    global _last_status, _last_checked_at, _last_error
    with _snapshot_lock:
        _last_status = status
        _last_checked_at = datetime.now(UTC).isoformat() if status != "running" else None
        _last_error = error


def _metric(name, criterion, method, status, observed):
    return QualityMetric(characteristic=name, criterion=criterion, method=method,
                         status=status, observed=observed)


def run_quality_suite(root: Path = ROOT, timeout: int = 90) -> QualityReport:
    """Run only repository-owned tests. JUnit XML is the sole source of counts."""
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A quality check is already running")
    _set_snapshot("running")
    try:
        report = _run_quality_suite(root, timeout)
        _set_snapshot(report.overall_status)
        return report
    except HTTPException as exc:
        _set_snapshot("unavailable", str(exc.detail))
        raise
    finally:
        _run_lock.release()


def _run_quality_suite(root: Path, timeout: int) -> QualityReport:
    start = time.monotonic()
    cases: list[QualityCase] = []
    limitation = "Автоматические тесты не доказывают соответствие ISO/IEC 25010 или готовность к эксплуатации."
    test_files = tuple(sorted(path.relative_to(root).as_posix()
                              for path in (root / "tests").glob("test_*.py")))
    if not test_files:
        raise HTTPException(status_code=503, detail="The test suite is unavailable")
    with tempfile.TemporaryDirectory(prefix="quality-check-") as tmp:
        report_file = Path(tmp) / "junit.xml"
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "pytest", *test_files, "-q",
                 "-p", "no:cacheprovider", f"--basetemp={Path(tmp) / 'pytest'}",
                 f"--junitxml={report_file}"],
                cwd=root, capture_output=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="The test suite timed out") from exc
        except OSError as exc:
            raise HTTPException(status_code=503, detail="The test runner is unavailable") from exc
        if result.returncode not in (0, 1):
            raise HTTPException(status_code=503, detail="The test runner could not complete")
        try:
            tree = ElementTree.parse(report_file)
        except (OSError, ElementTree.ParseError) as exc:
            raise HTTPException(status_code=503, detail="Test results are unavailable or invalid") from exc
        if tree.getroot().tag not in {"testsuite", "testsuites"}:
            raise HTTPException(status_code=503, detail="Test results are unavailable or invalid")
        for case in tree.iter("testcase"):
            child = next((node for node in case if node.tag in {"failure", "error", "skipped"}), None)
            status = child.tag if child is not None else "passed"
            cases.append(QualityCase(
                name=f"{case.get('classname', '')}::{case.get('name', '')}",
                status="failed" if status == "failure" else status,
                message=(child.get("message", "") if child is not None else "")[:500],
            ))
    passed = sum(c.status == "passed" for c in cases)
    failed = sum(c.status in {"failed", "error"} for c in cases)
    skipped = sum(c.status == "skipped" for c in cases)
    total = len(cases)
    if not total or (result.returncode == 0 and failed) or (result.returncode == 1 and not failed):
        raise HTTPException(status_code=503, detail="Test results are unavailable or inconsistent")
    limitations = [limitation]
    overall = "FAIL" if failed else "INCOMPLETE" if skipped else "PASS"
    observed = f"{passed}/{total} пройдено; {failed} ошибок; {skipped} пропущено"
    functional = "passed" if overall == "PASS" else "failed" if failed else "not_evaluated"
    api_case = next((case for case in cases if case.name.endswith(
        "::test_api_persist_retrieve_and_errors")), None)
    reliability = ("not_evaluated" if api_case is None or api_case.status == "skipped"
                   else "passed" if api_case.status == "passed" else "failed")
    metrics = [
        _metric("Functional suitability", "Все автоматические проверки API и контрактов проходят", "pytest; JUnit XML", functional, observed),
        _metric("Reliability", "Ошибочные входы дают контролируемый ответ", "API тесты негативных сценариев", reliability,
                api_case.name if api_case else "Целевой API тест не выполнялся"),
        _metric("Performance efficiency", "Порог времени для заданной нагрузки", "Повторный нагрузочный эксперимент", "not_evaluated", "Нагрузочный эксперимент не проводился"),
        _metric("Compatibility", "Работа в целевых браузерах и средах", "Кроссбраузерные и интеграционные проверки", "not_evaluated", "Не проверено"),
        _metric("Interaction capability", "Понятность сценариев для пользователей", "Пользовательская валидация", "not_evaluated", "Нет пользовательских испытаний"),
        _metric("Security", "Контроль доступа и защита данных", "Модель угроз и тесты безопасности", "not_evaluated", "Не проводилась оценка безопасности"),
        _metric("Maintainability", "Изменяемость без регрессий", "Ревью и регрессионные тесты", "not_evaluated", "Один запуск тестов не измеряет сопровождаемость"),
        _metric("Flexibility", "Перенос и адаптация к средам", "Тестирование развёртывания", "not_evaluated", "Не проверено"),
        _metric("Safety", "Отсутствие неприемлемого вреда", "Анализ рисков", "not_evaluated", "Анализ вреда не проводился"),
    ]
    return QualityReport(overall_status=overall, total_tests=total, passed_tests=passed,
                         failed_tests=failed, skipped_tests=skipped,
                         duration_seconds=round(time.monotonic() - start, 3),
                         metrics=metrics, cases=cases, limitations=limitations)
