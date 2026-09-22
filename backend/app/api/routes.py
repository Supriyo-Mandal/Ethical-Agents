from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..analysis import analyze
from ..repository import save_document_to_postgres
from ..schemas import AnalysisResponse, HistoryResponse
from ..storage import get_history, load_analysis, save_analysis
from ..auth import get_current_user

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=AnalysisResponse)
@router.post("/analyze", response_model=AnalysisResponse)
async def upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required")

    result = analyze(file)
    saved = save_analysis(file.filename, result, user["sub"])

    # keep JSON file backup
    save_analysis(file.filename, result)

    # new PostgreSQL persistence
    save_document_to_postgres(file.filename, result)

    return {
        "publish": bool(result.get("publish", False)),
        "overall_score": float(result.get("overall_score", 0.0)),
        "summary": result.get("summary", ""),
        "metadata": result.get("metadata", {"fields": []}),
        "previous_documents": [
            {
                "id": report.get("id", ""),
                "name": report.get("document_name", ""),
                "publish": bool(report.get("publish", False)),
            }
            for report in get_history(user["sub"])
        ],
    }


@router.get("/history", response_model=HistoryResponse)
def history(user: dict = Depends(get_current_user)) -> dict[str, object]:
    return {"analyses": get_history(user["sub"])}


@router.get("/report/{analysis_id}")
def report(
    analysis_id: str,
    user: dict = Depends(get_current_user)
) -> dict[str, object]:
    result = load_analysis(analysis_id, user["sub"])
    if not result:
        raise HTTPException(status_code=404, detail="Report not found")
    return result