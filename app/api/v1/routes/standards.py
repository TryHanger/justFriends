from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.schemas.standards import LifecycleState, QualityReport, StandardInfo
from app.services.quality import run_quality_suite
from app.services.standards import lifecycle_state, search_standards

router = APIRouter()


@router.get("/reference", response_model=list[StandardInfo])
def get_standards_reference(query: str = Query(default="", max_length=100), domain: str | None = None):
    return search_standards(query, domain)


@router.get("/lifecycle", response_model=LifecycleState)
def get_lifecycle_state():
    return lifecycle_state()


@router.post("/quality/run", response_model=QualityReport)
def run_quality_checks():
    if get_settings().environment != "local":
        raise HTTPException(status_code=403, detail="Test execution is available in local mode only")
    return run_quality_suite()
