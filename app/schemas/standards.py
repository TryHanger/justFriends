from typing import Literal

from pydantic import BaseModel

class StandardInfo(BaseModel):
    designation: str
    organization: str
    title: str
    domain: str
    purpose: str
    example_use: str
    source_url: str
    project_evidence: list[str]

class LifecycleProcess(BaseModel):
    id: str
    name: str
    responsible: str
    inputs: list[str]
    outputs: list[str]
    dependencies: list[str]
    status: Literal["evidenced", "partial", "missing"]
    evidence: list[str]
    gaps: list[str]

class LifecycleState(BaseModel):
    processes: list[LifecycleProcess]
    readiness: Literal["not_ready", "conditional", "ready"]
    issues: list[str]


class QualityCase(BaseModel):
    name: str
    status: Literal["passed", "failed", "error", "skipped"]
    message: str = ""

class QualityMetric(BaseModel):
    characteristic: str
    criterion: str
    method: str
    status: Literal["passed", "failed", "not_evaluated"]
    observed: str

class QualityReport(BaseModel):
    overall_status: Literal["PASS", "FAIL", "INCOMPLETE"]
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    duration_seconds: float
    metrics: list[QualityMetric]
    cases: list[QualityCase]
    limitations: list[str]
