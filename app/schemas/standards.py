from pydantic import BaseModel, Field


class StandardInfo(BaseModel):
    designation: str
    organization: str
    title: str
    domain: str
    purpose: str
    example_use: str

class LifecycleProcess(BaseModel):
    name: str
    status: str
    responsible: str
    dependencies: list[str]
    evidence: list[str] = Field(default_factory=list)
    details: str = ""

class LifecycleState(BaseModel):
    processes: list[LifecycleProcess]
    readiness: str
    issues: list[str]
    last_checked_at: str | None = None

class QualityMetric(BaseModel):
    characteristic: str
    score: float
    passed: bool
    details: str

class QualityReport(BaseModel):
    metrics: list[QualityMetric]
    overall_status: str
    total_tests: int
    passed_tests: int
