from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi import HTTPException, UploadFile, status
from pypdf import PdfReader

SUPPORTED_SUFFIXES = {".txt", ".pdf", ".docx"}


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
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not text.strip():
                raise HTTPException(
                    status_code=422,
                    detail="No selectable text found. Scanned PDF OCR is planned for a later integration.",
                )
        else:
            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="TXT must use UTF-8 encoding") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not read this document") from exc

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No text found in document")
    return text, filename

