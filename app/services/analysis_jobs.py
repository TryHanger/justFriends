from sqlalchemy.orm import Session

from app.db.models import AnalysisRecord
from app.db.session import SessionLocal
from app.schemas.analysis import AnalysisResult
from app.services.analyzer import analyze_text


def process_analysis(analysis_id: int) -> None:
    """Run one persisted analysis job using an independent DB session."""
    db: Session = SessionLocal()
    try:
        record = db.get(AnalysisRecord, analysis_id)
        if record is None:
            return
        record.status = "processing"
        db.commit()

        try:
            result = analyze_text(
                record.source_text,
                record.language if record.language != "auto" else "auto",
            )
            record.language = result.language
            record.model_version = result.model_version
            record.result = result.model_dump(mode="json")
            record.status = "completed"
            record.error_message = None
        except Exception:
            record.status = "failed"
            record.error_message = "Analysis failed. Check API configuration and try again."
        db.commit()
    finally:
        db.close()


def create_analysis_job(
    db: Session, source_text: str, language: str, source_name: str | None
) -> AnalysisRecord:
    record = AnalysisRecord(
        language=language,
        model_version="pending",
        status="queued",
        source_name=source_name,
        source_text=source_text,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def read_result(record: AnalysisRecord) -> AnalysisResult | None:
    if record.result is None:
        return None
    return AnalysisResult.model_validate(record.result)
