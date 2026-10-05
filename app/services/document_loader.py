from io import BytesIO
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import HTTPException, UploadFile, status

from app.core.limits import MAX_ANALYSIS_CHARS

SUPPORTED_SUFFIXES = {".txt", ".pdf", ".docx"}


def _table_text(table: Table):
    seen_cells: set[object] = set()
    for row in table.rows:
        for cell in row.cells:
            cell_xml = cell._tc
            if cell_xml in seen_cells:
                continue
            seen_cells.add(cell_xml)
            yield from _docx_blocks(cell)


def _docx_blocks(container, *, keep_empty_paragraphs: bool = False):
    for block in container.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text or keep_empty_paragraphs:
                yield block.text
        elif isinstance(block, Table):
            yield from _table_text(block)


async def extract_text(upload: UploadFile, max_upload_mb: int) -> tuple[str, str]:
    filename = upload.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported formats in this version: TXT, text-based PDF, DOCX",
        )

    content = await upload.read(max_upload_mb * 1024 * 1024 + 1)
    if len(content) > max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {max_upload_mb} MB")
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    try:
        if suffix == ".txt":
            text = content.decode("utf-8-sig")
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise HTTPException(
                    status_code=503, detail="PDF support is unavailable: install project dependencies"
                ) from exc
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not text.strip():
                raise HTTPException(
                    status_code=422,
                    detail="No selectable text found. Scanned PDF OCR is planned for a later integration.",
                )
        else:
            document = Document(BytesIO(content))
            text = "\n".join(_docx_blocks(document, keep_empty_paragraphs=True))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="TXT must use UTF-8 encoding") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read this document") from exc

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No text found in document")
    if len(text) > MAX_ANALYSIS_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Extracted text exceeds {MAX_ANALYSIS_CHARS} characters",
        )
    return text, filename

