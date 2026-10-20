from typing import Literal

from pydantic import BaseModel, Field


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
    last_checked_at: str | None = None


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


class ProductMeasurement(BaseModel):
    id: str
    title: str
    characteristic: str
    state: Literal["measured", "not_measured"]
    value: float | None
    unit: str
    numerator: int | None
    denominator: int | None
    skipped: int | None
    source_run_id: str | None
    observed_at: str | None
    previous_value: float | None = None
    previous_run_id: str | None = None
    previous_observed_at: str | None = None
    method: str
    limitation: str


class ProductMeasurementsReport(BaseModel):
    standard: str
    source_url: str
    measurements: list[ProductMeasurement]
    limitations: list[str]


class ProjectCheck(BaseModel):
    id: str
    name: str
    description: str
    category: str
    available: bool
    reason: str | None
    last_run_id: str | None
    last_status: str | None
    last_duration_seconds: float | None
    characteristics: list[str]
    project_requirement: str
    standard_refs: list[str]


class CheckCase(BaseModel):
    name: str
    status: str
    duration_seconds: float
    message: str


class CheckRun(BaseModel):
    id: str
    check_id: str
    status: str
    created_at: str
    finished_at: str | None
    duration_seconds: float | None
    exit_code: int | None
    summary: str
    diagnostics: str
    cases: list[CheckCase]
    counts: dict[str, int]
    project_version: str | None
    environment: str


class CheckComparison(BaseModel):
    comparable: bool
    reason: str | None
    first: CheckRun
    second: CheckRun
    became_passed: list[str] = Field(default_factory=list)
    became_failed: list[str] = Field(default_factory=list)
    appeared: list[str] = Field(default_factory=list)
    disappeared: list[str] = Field(default_factory=list)
    duration_delta_seconds: float | None = None
    count_delta: dict[str, int] = Field(default_factory=dict)
