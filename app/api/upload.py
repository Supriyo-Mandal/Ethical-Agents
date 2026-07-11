from __future__ import annotations

from fastapi import UploadFile
from fastapi.responses import JSONResponse

from app.core.document_processor import process_uploaded_document


async def upload_document_route(file: UploadFile) -> object:
    try:
        return await process_uploaded_document(file)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
