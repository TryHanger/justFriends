import logging
import re

from sqlalchemy.orm import Session

from app.db.models import AnalysisRecord
from app.db.session import SessionLocal
from app.schemas.analysis import AnalysisResult
from app.services.analyzer import analyze_text

logger = logging.getLogger(__name__)


def process_analysis(analysis_id: int, model_profile: str = "default") -> None:
    """Run one persisted analysis job using an independent DB session."""
    db: Session = SessionLocal()
    try:
        record = db.get(AnalysisRecord, analysis_id)
        if record is None:
            return
        record.status = "processing"
        db.commit()

        try:
            language = record.language if record.language != "auto" else "auto"
            # Keep the default path compatible with integrations that provide
            # the original two-argument analyzer callable.
            if model_profile == "default":
                result = analyze_text(record.source_text, language)
            else:
                result = analyze_text(record.source_text, language, model_profile)
            record.language = result.language
            record.model_version = result.model_version
            record.result = result.model_dump(mode="json")
            record.status = "completed"
            record.error_message = None
        except Exception as exc:
            logger.exception("Analysis %s failed", analysis_id)
            reason = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-***", str(exc))[:300]
            record.status = "failed"
            record.error_message = (
                f"Analysis failed ({type(exc).__name__}: {reason}). "
                "Check API configuration and try again."
            )
        db.commit()
    finally:
        db.close()


def create_analysis_job(
    db: Session, source_text: str, language: str, source_name: str | None, model_profile: str = "default"
) -> AnalysisRecord:
    record = AnalysisRecord(
        language=language,
        model_version=model_profile if model_profile != "default" else "pending",
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
