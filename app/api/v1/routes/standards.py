from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.schemas.standards import (
    CheckComparison,
    CheckRun,
    LifecycleState,
    ProductMeasurementsReport,
    ProjectCheck,
    QualityReport,
    StandardInfo,
)
from app.services import quality_checks
from app.services.quality import run_quality_suite
from app.services.security_lab import SecurityReview, SecurityReviewRequest, review_code
from app.services.standards import lifecycle_state, search_standards

router = APIRouter()


@router.post("/security/review", response_model=SecurityReview)
def review_security(request: SecurityReviewRequest):
    return review_code(request)


def require_runner(request: Request, x_quality_local: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.environment != "local" or not settings.quality_runner_enabled:
        raise HTTPException(403, "Runner выключен или подключена недоверенная БД")
    host = make_url(settings.database_url).host
    if host not in {None, "localhost", "127.0.0.1", "db"}:
        raise HTTPException(403, "Runner выключен или подключена недоверенная БД")
    allowed_origins = {*settings.cors_origins, "http://localhost:8080", "http://127.0.0.1:8080"}
    origin = request.headers.get("origin")
    if (x_quality_local != "1" or (origin and origin not in allowed_origins) or
            request.headers.get("sec-fetch-site") == "cross-site"):
        raise HTTPException(403, "Проверки доступны только с локального сайта")


@router.get("/reference", response_model=list[StandardInfo])
def get_standards_reference(query: str = Query(default="", max_length=100), domain: str | None = None):
    return search_standards(query, domain)


@router.get("/lifecycle", response_model=LifecycleState)
def get_lifecycle_state():
    return lifecycle_state()


@router.post("/quality/run", response_model=QualityReport, dependencies=[Depends(require_runner)])
def run_quality_checks():
    return run_quality_suite()


@router.get("/quality/measurements", response_model=ProductMeasurementsReport,
            dependencies=[Depends(require_runner)])
def get_quality_measurements():
    return quality_checks.product_measurements()


@router.get("/checks", response_model=list[ProjectCheck])
def get_checks():
    return quality_checks.list_checks()


@router.post("/checks/{check_id}/runs", response_model=CheckRun, status_code=202,
             dependencies=[Depends(require_runner)])
def start_check(check_id: str):
    return quality_checks.start(check_id)


@router.get("/checks/runs/history", response_model=list[CheckRun],
            dependencies=[Depends(require_runner)])
def check_history(check_id: str | None = None, status: str | None = None,
                  limit: int = Query(50, ge=1, le=100)):
    return quality_checks.history(check_id, status, limit)


@router.get("/checks/runs/{run_id}", response_model=CheckRun,
            dependencies=[Depends(require_runner)])
def get_check_run(run_id: str):
    return quality_checks.get_run(run_id)


@router.get("/checks/runs/{first_id}/compare/{second_id}",
            response_model=CheckComparison, dependencies=[Depends(require_runner)])
def compare_check_runs(first_id: str, second_id: str):
    return quality_checks.compare(first_id, second_id)
