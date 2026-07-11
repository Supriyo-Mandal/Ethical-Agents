from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PreviousDocument(BaseModel):
    id: str
    name: str
    publish: bool


class AnalysisResponse(BaseModel):
    publish: bool
    overall_score: float
    summary: str
    metadata: dict[str, Any]
    previous_documents: list[PreviousDocument]


class HistoryResponse(BaseModel):
    analyses: list[dict[str, Any]]
