from __future__ import annotations

from pydantic import BaseModel, Field


class ReportResult(BaseModel):
    id: str
    name: str
    description: str
    decision: str
    publish: bool
    overall_score: float
    summary: str
    paragraph: str
    fields_used: list[str] = Field(default_factory=list)
    repository_size: int = 0
