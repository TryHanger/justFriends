from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnalysisRecord, BookRecord
from app.db.session import get_db
from app.schemas.analysis import AnalysisJobResponse
from app.schemas.library import LibraryBookResponse, LibraryResponse
from app.services.analysis_jobs import create_analysis_job, process_analysis, read_result
from app.services.document_loader import extract_text

router = APIRouter(prefix="/library", tags=["library"])
settings = get_settings()


def _book_response(book: BookRecord, analysis: AnalysisRecord) -> LibraryBookResponse:
    return LibraryBookResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        language=analysis.language if analysis.language != "auto" else book.language,
        source_name=book.source_name,
        source_url=book.source_url,
        analysis_id=book.analysis_id,
        status=analysis.status,
        created_at=book.created_at,
        result=read_result(analysis),
    )


@router.get("/books", response_model=LibraryResponse)
def list_books(db: Session = Depends(get_db)) -> LibraryResponse:
    rows = db.execute(
        select(BookRecord, AnalysisRecord)
        .join(AnalysisRecord, AnalysisRecord.id == BookRecord.analysis_id)
        .order_by(BookRecord.id.desc())
    ).all()
    return LibraryResponse(items=[_book_response(book, analysis) for book, analysis in rows], total=len(rows))


@router.post("/books", response_model=AnalysisJobResponse, status_code=202)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    language: str = Form("auto"),
    source_url: str | None = Form(None),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    text, filename = await extract_text(file, settings.max_upload_mb)
    record = create_analysis_job(db, text, language, filename)
    book = BookRecord(
        title=(title or filename.rsplit(".", 1)[0]).strip()[:255],
        author=author.strip()[:255] if author else None,
        language=language,
        source_name=filename,
        source_url=source_url,
        analysis_id=record.id,
    )
    db.add(book)
    db.commit()
    background_tasks.add_task(process_analysis, record.id)
    return AnalysisJobResponse(
        analysis_id=record.id,
        status="queued",
        status_url=f"{settings.api_prefix}/analyses/{record.id}",
    )
