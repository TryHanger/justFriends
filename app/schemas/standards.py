from pydantic import BaseModel
from typing import List, Optional

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
    dependencies: List[str]

class LifecycleState(BaseModel):
    processes: List[LifecycleProcess]
    readiness: str
    issues: List[str]

class QualityMetric(BaseModel):
    characteristic: str
    score: float
    passed: bool
    details: str

class QualityReport(BaseModel):
    metrics: List[QualityMetric]
    overall_status: str
    total_tests: int
    passed_tests: int
