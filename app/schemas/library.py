from datetime import datetime

from pydantic import BaseModel

from app.schemas.analysis import AnalysisResult


class LibraryBookResponse(BaseModel):
    id: int
    title: str
    author: str | None
    language: str
    source_name: str
    source_url: str | None
    analysis_id: int
    status: str
    created_at: datetime
    result: AnalysisResult | None = None


class LibraryResponse(BaseModel):
    items: list[LibraryBookResponse]
    total: int
