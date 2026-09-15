import csv
import json
from collections import Counter, defaultdict
from io import StringIO
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisRecord
from app.db.session import get_db
from app.schemas.analysis import (
    AnalysisJobResponse,
    AnalysisListResponse,
    AnalyzeRequest,
    AnalysisStatusResponse,
    CompareRequest,
    CompareResponse,
    ComparisonGroup,
)
from app.services.analysis_jobs import create_analysis_job, process_analysis, read_result
from app.services.document_loader import extract_text

router = APIRouter()
settings = get_settings()


def _csv_safe(value: object) -> str | object:
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value


def _enqueue_analysis(
    background_tasks: BackgroundTasks,
    db: Session,
    text: str,
    language: str,
    source_name: str | None = None,
) -> AnalysisJobResponse:
    record = create_analysis_job(db, text, language, source_name)
    background_tasks.add_task(process_analysis, record.id)
    return AnalysisJobResponse(
        analysis_id=record.id,
        status="queued",
        status_url=f"{settings.api_prefix}/analyses/{record.id}",
    )


@router.post("/analyze", response_model=AnalysisJobResponse, status_code=202)
def analyze(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    return _enqueue_analysis(background_tasks, db, request.text, request.language)


@router.post("/analyze/file", response_model=AnalysisJobResponse, status_code=202)
async def analyze_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form("auto"),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    if language not in {"auto", "zh", "kk"}:
        raise HTTPException(status_code=422, detail="language must be auto, zh, or kk")
    text, filename = await extract_text(file, settings.max_upload_mb)
    return _enqueue_analysis(background_tasks, db, text, language, filename)


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatusResponse)
def get_analysis_status(
    analysis_id: int, db: Session = Depends(get_db)
) -> AnalysisStatusResponse:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = read_result(record)
    return AnalysisStatusResponse(
        analysis_id=record.id,
        status=record.status,
        source_name=record.source_name,
        created_at=record.created_at.isoformat(),
        result=result,
        error=record.error_message,
    )


@router.get("/analyses", response_model=AnalysisListResponse)
def list_analyses(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> AnalysisListResponse:
    records = list(
        db.scalars(
            select(AnalysisRecord)
            .order_by(AnalysisRecord.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    items = [
        AnalysisStatusResponse(
            analysis_id=record.id,
            status=record.status,
            source_name=record.source_name,
            created_at=record.created_at.isoformat(),
            result=read_result(record),
            error=record.error_message,
        )
        for record in records
    ]
    return AnalysisListResponse(items=items, limit=limit, offset=offset)


@router.get("/analyses/{analysis_id}/export")
def export_analysis(
    analysis_id: int,
    format: Literal["json", "csv"] = "json",
    db: Session = Depends(get_db),
) -> Response:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    result = read_result(record)
    if record.status != "completed" or result is None:
        raise HTTPException(status_code=409, detail="Analysis is not completed")

    if format == "json":
        content = json.dumps(
            {
                "analysis_id": record.id,
                "source_name": record.source_name,
                "created_at": record.created_at.isoformat(),
                "result": result.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="analysis-{record.id}.json"'},
        )

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "analysis_id", "language", "text", "start", "end", "label",
            "source_domain", "target_domain", "confidence", "rationale",
        ]
    )
    for span in result.metaphors:
        values = [
            record.id,
            result.language,
            span.text,
            span.start,
            span.end,
            span.label,
            span.source_domain,
            span.target_domain,
            span.confidence,
            span.rationale,
        ]
        writer.writerow([_csv_safe(value) for value in values])
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="analysis-{record.id}.csv"'},
    )


@router.post("/compare", response_model=CompareResponse)
def compare_analyses(
    request: CompareRequest, db: Session = Depends(get_db)
) -> CompareResponse:
    unique_ids = list(dict.fromkeys(request.analysis_ids))
    records = list(
        db.scalars(select(AnalysisRecord).where(AnalysisRecord.id.in_(unique_ids))).all()
    )
    by_id = {record.id: record for record in records}
    missing_ids = [analysis_id for analysis_id in unique_ids if analysis_id not in by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail={"missing_analysis_ids": missing_ids})

    pending_ids = [
        record.id for record in records if record.status != "completed" or record.result is None
    ]
    if pending_ids:
        raise HTTPException(
            status_code=409,
            detail={"message": "All analyses must be completed", "pending_analysis_ids": pending_ids},
        )

    grouped: dict[str, list[AnalysisRecord]] = defaultdict(list)
    for record in records:
        grouped[record.language].append(record)
    if not {"zh", "kk"}.issubset(grouped):
        raise HTTPException(
            status_code=422,
            detail="Comparison requires at least one completed Chinese (zh) and one Kazakh (kk) analysis",
        )

    output: dict[str, ComparisonGroup] = {}
    for language, language_records in grouped.items():
        labels: Counter[str] = Counter()
        source_domains: Counter[str] = Counter()
        target_domains: Counter[str] = Counter()
        metaphor_count = 0
        for record in language_records:
            result = read_result(record)
            if result is None:
                continue
            metaphor_count += len(result.metaphors)
            labels.update(span.label for span in result.metaphors)
            source_domains.update(span.source_domain for span in result.metaphors)
            target_domains.update(span.target_domain for span in result.metaphors)
        output[language] = ComparisonGroup(
            analysis_count=len(language_records),
            metaphor_count=metaphor_count,
            by_label=dict(labels),
            by_source_domain=dict(source_domains),
            by_target_domain=dict(target_domains),
        )

    return CompareResponse(
        languages=output,
        analysis_ids=unique_ids,
        note="Counts are descriptive and depend on the selected analyses; semantic cross-language matching is a separate NLP integration.",
    )
