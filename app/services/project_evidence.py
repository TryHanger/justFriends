"""Repository artifact inventory for an informational lifecycle view.

File presence is evidence to review, never proof that a standard is satisfied.
"""

from pathlib import Path

from app.schemas.standards import LifecycleProcess, LifecycleState
from app.services.quality_checks import get_quality_snapshot

_repository = Path(__file__).resolve().parents[2]


def _artifact_process(name: str, artifacts: list[str]) -> LifecycleProcess:
    found = [artifact for artifact in artifacts if (_repository / artifact).is_file()]
    missing = [artifact for artifact in artifacts if artifact not in found]
    details = f"Found: {', '.join(found) or 'none'}. Missing: {', '.join(missing) or 'none'}. Presence requires manual review."
    return LifecycleProcess(
        name=name,
        status="evidence_found" if not missing else "missing",
        responsible="Unassigned",
        dependencies=[],
        evidence=found,
        details=details,
    )


def build_lifecycle_state() -> LifecycleState:
    processes = [
        _artifact_process("Requirements evidence", ["docs/API_CONTRACT.md", "docs/NLP_CONTRACT.md"]),
        _artifact_process("Architecture evidence", ["ARCHITECTURE.md"]),
        _artifact_process("Implementation evidence", ["app/main.py"]),
        _artifact_process("Test suite evidence", ["tests/test_nlp_api.py", "tests/test_quality_checks.py"]),
        _artifact_process("CI evidence", [".github/workflows/quality.yml"]),
    ]
    report, run_status, checked_at, error = get_quality_snapshot()
    if report is None:
        runtime_status = run_status or "not_run"
        details = error or "Automated tests have not been run through this process."
    else:
        runtime_status = report.overall_status
        details = report.metrics[0].details if report.metrics else "Test report contained no metrics."
    processes.append(
        LifecycleProcess(
            name="Runtime tests",
            status=runtime_status,
            responsible="Unassigned",
            dependencies=["Test suite evidence"],
            evidence=[],
            details=details,
        )
    )
    issues = [f"{item.name}: {item.details}" for item in processes if item.status == "missing"]
    if runtime_status != "PASS":
        issues.append(f"Runtime tests: {details}")
    issues.append("A human must review artifact contents and project practices; this is not certification.")
    return LifecycleState(
        processes=processes,
        readiness="Manual review required",
        issues=issues,
        last_checked_at=checked_at,
    )
