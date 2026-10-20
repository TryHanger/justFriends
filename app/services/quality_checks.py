"""Allowlisted, local-only quality checks with persistent results."""

import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.models import CheckRunRecord
from app.db.session import SessionLocal
from app.services.quality import ROOT, _run_lock

CHECKS = {
    "backend-tests": ("Backend Tests", "pytest и результаты отдельных тестов", "tests", 120),
    "python-static": ("Python Static Analysis", "Ruff: исходный код и тесты", "static", 90),
    "frontend-tests": ("Frontend Tests", "Vitest: проверки интерфейса", "tests", 120),
    "typescript": ("TypeScript Check", "Проверка типов интерфейса", "static", 120),
    "frontend-build": ("Frontend Build", "Проверка производственной сборки", "build", 180),
}
EVIDENCE = {
    "backend-tests": ("Контракты API, валидация входных данных и сохранение результатов",
                      ["ISO/IEC 25010:2023", "ISO/IEC/IEEE 29148:2018", "ISO/IEC/IEEE 29119-3:2021"]),
    "python-static": ("Правила качества Python-кода из pyproject.toml",
                      ["ISO/IEC 25010:2023"]),
    "frontend-tests": ("Сценарии интерфейса и обмен с API",
                       ["ISO/IEC 25010:2023", "ISO/IEC/IEEE 29119-3:2021"]),
    "typescript": ("Типовые контракты интерфейса",
                   ["ISO/IEC 25010:2023"]),
    "frontend-build": ("Сборка веб-интерфейса для развёртывания",
                       ["ISO/IEC 25010:2023"]),
}
TERMINAL = {"passed", "failed", "skipped", "unavailable", "timeout", "error", "interrupted"}
_lock = _run_lock
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quality-check")


def _availability(check_id: str) -> tuple[bool, str | None]:
    settings = get_settings()
    if (settings.environment != "local" or not settings.quality_runner_enabled or
            make_url(settings.database_url).host not in {None, "localhost", "127.0.0.1", "db"}):
        return False, "Runner выключен. Нужны local и QUALITY_RUNNER_ENABLED."
    if check_id == "backend-tests" and (not (ROOT / "tests").is_dir() or
                                         not shutil.which("pytest")):
        return False, "pytest или тесты отсутствуют в окружении."
    if check_id == "python-static" and not shutil.which("ruff"):
        return False, "Ruff не установлен."
    if check_id.startswith("frontend") or check_id == "typescript":
        if not _frontend_local_available() and not _worker_available():
            return False, "Node.js/npm и зависимости frontend недоступны; контейнер проверок не запущен."
    return True, None


def _frontend_local_available() -> bool:
    return bool(shutil.which("npm") and (ROOT / "frontend" / "node_modules").is_dir())


def _worker_request(method: str, path: str, timeout: int) -> dict:
    connection = http.client.HTTPConnection("frontend-checks", 9090, timeout=timeout)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        payload = response.read(2_000_001)
        if response.status != 200 or len(payload) > 2_000_000:
            raise OSError("Контейнер проверок интерфейса недоступен")
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("Некорректный ответ контейнера проверок")
        return result
    finally:
        connection.close()


def _worker_available() -> bool:
    if not get_settings().quality_frontend_worker_enabled:
        return False
    try:
        return _worker_request("GET", "/health", 2).get("status") == "ok"
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def list_checks() -> list[dict]:
    settings = get_settings()
    if settings.environment != "local":
        return [_check_view(check_id, None) for check_id in CHECKS]
    with SessionLocal() as db:
        result = []
        for check_id in CHECKS:
            last = db.scalar(select(CheckRunRecord).where(CheckRunRecord.check_id == check_id)
                             .order_by(CheckRunRecord.created_at.desc()).limit(1))
            result.append(_check_view(check_id, last))
        return result


def _check_view(check_id: str, last: CheckRunRecord | None) -> dict:
    name, description, category, _ = CHECKS[check_id]
    available, reason = _availability(check_id)
    return {"id": check_id, "name": name, "description": description,
            "category": category, "available": available, "reason": reason,
            "last_run_id": last.id if last else None,
            "last_status": last.status if last else None,
            "last_duration_seconds": last.duration_seconds if last else None,
            "project_requirement": EVIDENCE[check_id][0],
            "standard_refs": EVIDENCE[check_id][1],
            "characteristics": ["Functional suitability"] if check_id.endswith("tests")
            else ["Maintainability"] if check_id in {"python-static", "typescript"}
            else ["Functional suitability"]}


def _view(row: CheckRunRecord) -> dict:
    return {"id": row.id, "check_id": row.check_id, "status": row.status,
            "created_at": row.created_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "duration_seconds": row.duration_seconds, "exit_code": row.exit_code,
            "summary": row.summary, "diagnostics": row.diagnostics,
            "cases": row.cases or [], "counts": row.counts or {},
            "project_version": row.project_version, "environment": row.environment}


def get_run(run_id: str) -> dict:
    with SessionLocal() as db:
        row = db.get(CheckRunRecord, run_id)
        if row is None:
            raise HTTPException(404, "Запуск не найден")
        return _view(row)


def history(check_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    with SessionLocal() as db:
        statement = select(CheckRunRecord)
        if check_id:
            statement = statement.where(CheckRunRecord.check_id == check_id)
        if status:
            statement = statement.where(CheckRunRecord.status == status)
        rows = db.scalars(statement.order_by(CheckRunRecord.created_at.desc()).limit(limit)).all()
        return [_view(row) for row in rows]


def product_measurements() -> dict:
    """Project-defined indicators from real runs, not claimed ISO formulas."""
    with SessionLocal() as db:
        recent = {
            check_id: db.scalars(select(CheckRunRecord).where(CheckRunRecord.check_id == check_id)
                                   .order_by(CheckRunRecord.created_at.desc(), CheckRunRecord.id.desc())
                                   .limit(2)).all()
            for check_id in ("backend-tests", "frontend-tests", "python-static", "typescript")
        }

    definitions = [
        ("backend-tests", "backend-pass-share", "Доля успешных выполненных серверных тестов",
         "Функциональная пригодность", "%", "passed / (passed + failed + error) × 100; skipped отдельно",
         "Отражает только сценарии набора pytest; не измеряет полноту требований или качество NLP-модели."),
        ("frontend-tests", "frontend-pass-share", "Доля успешных выполненных тестов интерфейса",
         "Функциональная пригодность", "%", "passed / (passed + failed + error) × 100; skipped отдельно",
         "Отражает только сценарии Vitest; не заменяет испытания с пользователями и браузерами."),
        ("python-static", "ruff-findings", "Замечания статической проверки Python",
         "Сопровождаемость", "замечаний", "Количество диагностик Ruff из последнего завершённого запуска",
         "Ноль замечаний означает прохождение выбранных правил Ruff, а не отсутствие дефектов."),
        ("typescript", "typescript-errors", "Ошибки проверки типов TypeScript",
         "Сопровождаемость", "ошибок", "Количество диагностик TypeScript из последнего завершённого запуска",
         "Ноль ошибок типов не доказывает правильность поведения интерфейса."),
    ]
    def measured_value(check_id: str, row: CheckRunRecord | None) -> tuple[float | None, int | None, int | None, int | None]:
        cases = row.cases or [] if row else []
        valid = bool(row and row.status in {"passed", "failed", "skipped"})
        if check_id.endswith("tests") and valid:
            numerator = sum(case.get("status") == "passed" for case in cases)
            denominator = sum(case.get("status") in {"passed", "failed", "error"} for case in cases)
            skipped = sum(case.get("status") == "skipped" for case in cases)
            return (round(numerator / denominator * 100, 2) if denominator else None,
                    numerator, denominator, skipped)
        if valid and (row.status == "passed" or cases):
            return float(sum(case.get("status") == "failed" for case in cases)), None, None, None
        return None, None, None, None

    measurements = []
    for check_id, ident, title, characteristic, unit, method, limitation in definitions:
        row = recent[check_id][0] if recent[check_id] else None
        previous = recent[check_id][1] if len(recent[check_id]) > 1 else None
        value, numerator, denominator, skipped = measured_value(check_id, row)
        previous_value, _, _, _ = measured_value(check_id, previous)
        measurements.append({
            "id": ident, "title": title, "characteristic": characteristic,
            "state": "measured" if value is not None else "not_measured",
            "value": value, "unit": unit, "numerator": numerator if value is not None else None,
            "denominator": denominator if value is not None else None,
            "skipped": skipped if value is not None else None,
            "source_run_id": row.id if row else None,
            "observed_at": row.finished_at.isoformat() if row and row.finished_at else None,
            "previous_value": previous_value,
            "previous_run_id": previous.id if previous else None,
            "previous_observed_at": previous.finished_at.isoformat() if previous and previous.finished_at else None,
            "method": method, "limitation": limitation,
        })
    return {
        "standard": "ISO/IEC 25023:2016",
        "source_url": "https://www.iso.org/standard/35747.html",
        "measurements": measurements,
        "limitations": [
            "Это проектные индикаторы по подходу к измерению; формулы не объявлены дословными мерами ISO/IEC 25023.",
            "ISO/IEC 25023 не задаёт универсальных порогов оценки; целевые значения для проекта не утверждены.",
            "Покрытие кода, производительность, безопасность, удобство использования и качество NLP здесь не измерены.",
            "Модель характеристик на странице относится к ISO/IEC 25010:2023; применимость мер редакции 2016 года требует отдельного сопоставления.",
        ],
    }


def compare(first_id: str, second_id: str) -> dict:
    first, second = get_run(first_id), get_run(second_id)
    if first["check_id"] != second["check_id"]:
        return {"comparable": False, "reason": "Разные виды проверок нельзя сравнить.",
                "first": first, "second": second}
    old = {item["name"]: item["status"] for item in first["cases"]}
    new = {item["name"]: item["status"] for item in second["cases"]}
    return {"comparable": True, "reason": None, "first": first, "second": second,
            "became_passed": sorted(name for name in old.keys() & new.keys()
                                    if old[name] != "passed" and new[name] == "passed"),
            "became_failed": sorted(name for name in old.keys() & new.keys()
                                    if old[name] == "passed" and new[name] in {"failed", "error"}),
            "appeared": sorted(new.keys() - old.keys()), "disappeared": sorted(old.keys() - new.keys()),
            "duration_delta_seconds": round((second["duration_seconds"] or 0) -
                                            (first["duration_seconds"] or 0), 3),
            "count_delta": {key: second["counts"].get(key, 0) - first["counts"].get(key, 0)
                            for key in ("passed", "failed", "skipped")}}


def recover_interrupted() -> None:
    with SessionLocal.begin() as db:
        for row in db.scalars(select(CheckRunRecord).where(
                CheckRunRecord.status.in_(["queued", "running"]))):
            row.status = "interrupted"
            row.finished_at = datetime.now(UTC)
            row.summary = "Процесс сервера завершился до получения результата."


def start(check_id: str) -> dict:
    if check_id not in CHECKS:
        raise HTTPException(404, "Неизвестный вид проверки")
    available, reason = _availability(check_id)
    if not available:
        raise HTTPException(503, reason)
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "Другая проверка уже выполняется")
    try:
        row = CheckRunRecord(id=str(uuid4()), check_id=check_id, status="queued",
                             created_at=datetime.now(UTC), environment="local",
                             project_version=_project_version(),
                             summary="Ожидает запуска", diagnostics="", cases=[], counts={})
        with SessionLocal.begin() as db:
            db.add(row)
        _pool.submit(_execute, row.id, check_id)
        return get_run(row.id)
    except Exception:
        _lock.release()
        raise


def _sanitize(value: str) -> str:
    for key, secret in os.environ.items():
        if any(word in key.upper() for word in ("KEY", "TOKEN", "PASSWORD", "SECRET")) and len(secret) >= 4:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+", r"\1=[REDACTED]", value)
    return value[:12000]


def _stop_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, check=False, timeout=10)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _project_version() -> str | None:
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:40]
    try:
        command = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                 capture_output=True, text=True, check=False, timeout=3)
        return command.stdout.strip()[:40] if command.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _command(check_id: str, temporary: Path) -> tuple[list[str], Path, Path | None]:
    frontend = ROOT / "frontend"
    if check_id == "backend-tests":
        files = sorted((ROOT / "tests").glob("test_*.py"))
        if not files:
            raise FileNotFoundError("Нет файлов тестов")
        xml = temporary / "junit.xml"
        return ([sys.executable, "-X", "utf8", "-m", "pytest",
                 *[str(path.relative_to(ROOT)) for path in files], "-q", "-p", "no:cacheprovider",
                 f"--basetemp={temporary / 'pytest'}", f"--junitxml={xml}"], ROOT, xml)
    if check_id == "python-static":
        return [sys.executable, "-m", "ruff", "check", "app", "tests", "scripts",
                "--output-format=json"], ROOT, None
    npm = shutil.which("npm")
    if not npm:
        raise FileNotFoundError("npm отсутствует")
    if check_id == "frontend-tests":
        output = temporary / "vitest.json"
        return [npm, "run", "test", "--", "--reporter=json", f"--outputFile={output}"], frontend, output
    if check_id == "typescript":
        return [npm, "exec", "--", "tsc", "-b", "--pretty", "false"], frontend, None
    return [npm, "run", "build"], frontend, None


def _parse_cases(check_id: str, path: Path | None, diagnostics: str = "") -> list[dict]:
    if check_id == "python-static":
        findings = json.loads(diagnostics)
        return [{"name": f"{Path(item['filename']).name}:{item['location']['row']}:{item['code']}",
                 "status": "failed", "duration_seconds": 0,
                 "message": _sanitize(item["message"])[:2000]} for item in findings]
    if check_id == "typescript":
        return [{"name": line.split(": error ", 1)[0], "status": "failed",
                 "duration_seconds": 0, "message": line[:2000]}
                for line in diagnostics.splitlines() if ": error TS" in line]
    if path is None or not path.is_file():
        return []
    if check_id == "backend-tests":
        root = ElementTree.parse(path)
        if root.getroot().tag not in {"testsuite", "testsuites"}:
            raise ValueError("Некорректный JUnit XML")
        items = []
        for case in root.iter("testcase"):
            problem = next((child for child in case if child.tag in {"failure", "error", "skipped"}), None)
            items.append({"name": f"{case.get('classname', '')}::{case.get('name', '')}",
                          "status": "failed" if problem is not None and problem.tag == "failure"
                          else problem.tag if problem is not None else "passed",
                          "duration_seconds": float(case.get("time", "0")),
                          "message": _sanitize((problem.get("message", "") + "\n" + (problem.text or ""))
                                               if problem is not None else "")[:2000]})
        return items
    if check_id == "frontend-tests":
        report = json.loads(path.read_text(encoding="utf-8"))
        return [{"name": item.get("fullName") or item.get("title", ""),
                 "status": "passed" if item.get("status") == "passed" else
                 "skipped" if item.get("status") in {"pending", "skipped"} else "failed",
                 "duration_seconds": (item.get("duration") or 0) / 1000,
                 "message": _sanitize("\n".join(item.get("failureMessages") or []))[:2000]}
                for suite in report.get("testResults", []) for item in suite.get("assertionResults", [])]
    return []


def _execute(run_id: str, check_id: str) -> None:
    started = time.monotonic()
    result = {"status": "error", "summary": "Проверка завершилась с ошибкой", "diagnostics": "",
              "cases": [], "counts": {}, "exit_code": None}
    try:
        with SessionLocal.begin() as db:
            db.get(CheckRunRecord, run_id).status = "running"
        with tempfile.TemporaryDirectory(prefix="project-check-") as directory:
            temporary = Path(directory)
            remote = (check_id in {"frontend-tests", "typescript", "frontend-build"}
                      and not _frontend_local_available())
            if remote:
                response = _worker_request("POST", f"/run/{check_id}", CHECKS[check_id][3] * 2 + 10)
                timed_out = response.get("timeout") is True
                returncode = response.get("exit_code")
                diagnostics = _sanitize(str(response.get("output") or ""))
                output = temporary / "vitest.json" if check_id == "frontend-tests" else None
                if output and response.get("report") is not None:
                    output.write_text(json.dumps(response["report"]), encoding="utf-8")
            else:
                command, cwd, output = _command(check_id, temporary)
                env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "HOME", "TMP", "TEMP", "LANG")
                       if key in os.environ}
                env.update({"DATABASE_URL": f"sqlite:///{(temporary / 'checks.db').as_posix()}",
                            "OPENAI_API_KEY": "", "NLP_BACKEND": "baseline", "ENVIRONMENT": "local",
                            "PYTHONDONTWRITEBYTECODE": "1"})
                flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                with (temporary / "tool.log").open("wb") as log:
                    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                                               stderr=subprocess.STDOUT, creationflags=flags,
                                               start_new_session=os.name != "nt")
                    try:
                        process.wait(timeout=CHECKS[check_id][3])
                        timed_out = False
                    except subprocess.TimeoutExpired:
                        _stop_tree(process)
                        timed_out = True
                returncode = None if timed_out else process.returncode
                with (temporary / "tool.log").open("rb") as saved:
                    diagnostics = _sanitize(saved.read(12000).decode("utf-8", errors="replace"))
            if timed_out:
                result.update(status="timeout", summary="Превышено время выполнения",
                              diagnostics=diagnostics)
            else:
                cases = _parse_cases(check_id, output, diagnostics)
                counts = ({"passed": sum(case["status"] == "passed" for case in cases),
                           "failed": sum(case["status"] in {"failed", "error"} for case in cases),
                           "skipped": sum(case["status"] == "skipped" for case in cases)}
                          if check_id.endswith("tests") else {})
                status = "passed" if returncode == 0 else "failed" if returncode == 1 else "error"
                if check_id.endswith("tests") and not cases:
                    status = "error"
                    diagnostics = (diagnostics + "\nНет структурированных результатов тестов.")[:12000]
                elif status == "passed" and counts.get("skipped"):
                    status = "skipped"
                result.update(status=status, summary="Проверка завершена: " + status,
                              diagnostics=diagnostics, cases=cases, counts=counts,
                              exit_code=returncode)
    except (OSError, ValueError, ElementTree.ParseError, json.JSONDecodeError) as exc:
        result.update(status="unavailable" if isinstance(exc, FileNotFoundError) else "error",
                      summary="Инструмент или отчёт недоступен", diagnostics=_sanitize(str(exc)))
    except Exception:
        result.update(status="error", summary="Непредвиденная ошибка выполнения")
    finally:
        try:
            with SessionLocal.begin() as db:
                row = db.get(CheckRunRecord, run_id)
                row.status = result["status"]
                row.finished_at = datetime.now(UTC)
                row.duration_seconds = round(time.monotonic() - started, 3)
                row.summary = result["summary"]
                row.diagnostics = result["diagnostics"]
                row.cases = result["cases"]
                row.counts = result["counts"]
                row.exit_code = result["exit_code"]
        finally:
            _lock.release()
