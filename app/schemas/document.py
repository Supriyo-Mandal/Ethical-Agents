from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentUpload(BaseModel):
    filename: str = Field(..., min_length=1)
    content_type: str | None = None
