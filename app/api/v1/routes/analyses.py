from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisRecord
from app.db.session import get_db
from app.schemas.analysis import AnalysisResponse, AnalyzeRequest, AnalysisResult
from app.services.analyzer import (
    AnalyzerNotConfigured,
    AnalyzerOutputInvalid,
    analyze_text,
)
from app.services.document_loader import extract_text

router = APIRouter()
settings = get_settings()


def _analyze_and_save(
    text: str, language: str, source_name: str | None, db: Session
) -> AnalysisResponse:
    try:
        result = analyze_text(text, language)
    except AnalyzerNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GPT analysis is not configured. Set OPENAI_API_KEY.",
        ) from exc
    except AnalyzerOutputInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The analysis provider returned an invalid result.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The analysis provider could not process the request.",
        ) from exc

    record = AnalysisRecord(
        language=result.language,
        model_version=result.model_version,
        source_name=source_name,
        source_text=text,
        result=result.model_dump(mode="json"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return AnalysisResponse(analysis_id=record.id, **result.model_dump())


@router.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    return _analyze_and_save(request.text, request.language, None, db)


@router.post("/analyze/file", response_model=AnalysisResponse)
async def analyze_file(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    if language not in {"auto", "zh", "kk"}:
        raise HTTPException(status_code=422, detail="language must be auto, zh, or kk")
    text, filename = await extract_text(file, settings.max_upload_mb)
    return _analyze_and_save(text, language, filename, db)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> AnalysisResponse:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = AnalysisResult.model_validate(record.result)
    return AnalysisResponse(analysis_id=record.id, **result.model_dump())

