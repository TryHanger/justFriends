"""Reproducible test evidence for the project quality dashboard."""

import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree

from app.schemas.standards import QualityCase, QualityMetric, QualityReport

ROOT = Path(__file__).resolve().parents[2]
TEST_FILES = ("tests/test_standards.py", "tests/test_nlp_api.py", "tests/test_nlp_contracts.py", "tests/test_nlp_models.py")


def _metric(name, criterion, method, status, observed):
    return QualityMetric(characteristic=name, criterion=criterion, method=method,
                         status=status, observed=observed)


def run_quality_suite(root: Path = ROOT, timeout: int = 90) -> QualityReport:
    """Run only repository-owned tests. JUnit XML is the sole source of counts."""
    start = time.monotonic()
    cases: list[QualityCase] = []
    limitation = "Автоматические тесты не доказывают соответствие ISO/IEC 25010 или готовность к эксплуатации."
    error = ""
    with tempfile.TemporaryDirectory(prefix="quality-check-") as tmp:
        report_file = Path(tmp) / "junit.xml"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", *TEST_FILES, "-q", f"--junitxml={report_file}"],
                cwd=root, capture_output=True, text=True, timeout=timeout, check=False,
            )
            if report_file.exists():
                tree = ElementTree.parse(report_file)
                for case in tree.iter("testcase"):
                    child = next((node for node in case if node.tag in {"failure", "error", "skipped"}), None)
                    status = child.tag if child is not None else "passed"
                    cases.append(QualityCase(
                        name=f"{case.get('classname', '')}::{case.get('name', '')}",
                        status="failed" if status == "failure" else status,
                        message=(child.get("message", "") if child is not None else "")[:500],
                    ))
            if result.returncode != 0 and not cases:
                error = (result.stderr or result.stdout or "pytest не сформировал отчёт")[-1200:]
        except (subprocess.TimeoutExpired, OSError, ElementTree.ParseError) as exc:
            error = f"Запуск тестов не завершён: {type(exc).__name__}: {exc}"
    passed = sum(c.status == "passed" for c in cases)
    failed = sum(c.status in {"failed", "error"} for c in cases)
    skipped = sum(c.status == "skipped" for c in cases)
    total = len(cases)
    if error:
        limitations = [limitation, error]
        overall = "INCOMPLETE"
    else:
        limitations = [limitation]
        overall = "FAIL" if failed or result.returncode else "INCOMPLETE" if skipped or not total else "PASS"
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
