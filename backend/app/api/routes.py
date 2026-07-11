from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..analysis import analyze
from ..schemas import AnalysisResponse, HistoryResponse
from ..storage import get_history, load_analysis, save_analysis

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload", response_model=AnalysisResponse)
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    analysis_result = analyze(file)
    save_analysis(file.filename, analysis_result)

    return {
        "publish": bool(analysis_result.get("publish", False)),
        "summary": analysis_result.get("summary", ""),
        "metadata": analysis_result.get("metadata", {"fields": []}),
        "previous_documents": [
            {"id": report.get("id", ""), "name": report.get("document_name", ""), "publish": bool(report.get("publish", False))}
            for report in get_history()
        ],
    }


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_route(file: UploadFile = File(...)) -> dict[str, Any]:
    return await upload(file)


@router.get("/history", response_model=HistoryResponse)
def history() -> dict[str, object]:
    return {"analyses": get_history()}


@router.get("/report/{analysis_id}")
def report(analysis_id: str) -> dict[str, object]:
    result = load_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Report not found")
    return result
