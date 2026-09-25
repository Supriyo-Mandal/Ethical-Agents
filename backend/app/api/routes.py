from __future__ import annotations
import logging

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.llm_config import load_config
from app.services.llm_gateway import _get_provider_candidates

from ..analysis import analyze, cross_document_analysis, detect_duplicate_documents
from ..config import MAX_BATCH_FILES
from ..schemas import AnalysisResponse, BatchAnalysisResponse, HistoryResponse
from ..storage import get_history, load_analysis, save_analysis

router = APIRouter()

logger = logging.getLogger(__name__)

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/llm")
def llm_health() -> dict[str, Any]:
    try:
        providers = load_config()
        if not providers:
            return {"status": "degraded", "ready": False, "error": "No providers configured"}

        candidates = _get_provider_candidates()
        if not candidates:
            return {"status": "degraded", "ready": False, "error": "No enabled provider/model available"}

        return {
            "status": "ok",
            "ready": True,
            "providers": [p.id for p in providers],
            "candidate_count": len(candidates),
        }
    except Exception as exc:
        return {"status": "degraded", "ready": False, "error": str(exc)}


@router.post("/upload", response_model=AnalysisResponse | BatchAnalysisResponse)
@router.post("/analyze", response_model=AnalysisResponse | BatchAnalysisResponse)
async def upload(
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    files = files or ([file] if file else [])
    if not files or len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Upload between 1 and {MAX_BATCH_FILES} files")
    if any(not file.filename for file in files):
        raise HTTPException(status_code=400, detail="Every uploaded file needs a filename")

    logger.info("upload route reached")
    logger.info("UPLOAD: request received with %s file(s)", len(files))
    previous_reports = get_history()
    results: list[dict[str, Any]] = []
    for file in files:
        logger.info("UPLOAD: analyzing file=%s", file.filename)
        try:
            result = analyze(file)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}") from exc
        logger.info("UPLOAD: analysis complete for file=%s", file.filename)
        result["document_name"] = file.filename or "document"
        results.append(result)

    duplicates = detect_duplicate_documents(results, previous_reports)
    duplicates_by_document: dict[str, list[dict[str, Any]]] = {}
    for match in duplicates:
        for name in match["documents"]:
            duplicates_by_document.setdefault(name, []).append(match)

    for result in results:
        result.setdefault("metadata", {})["duplicate_documents"] = duplicates_by_document.get(
            result["document_name"], []
        )
        saved = save_analysis(result["document_name"], result)
        result["analysis_id"] = saved["id"]

    previous_documents = [
        {
            "id": report.get("id", ""),
            "name": report.get("document_name", ""),
            "publish": bool(report.get("publish", False)),
        }
        for report in get_history()
    ]

    if len(results) == 1:
        result = results[0]
        return {
            "publish": bool(result.get("publish", False)),
            "overall_score": float(result.get("overall_score", 0.0)),
            "summary": result.get("summary", ""),
            "metadata": result.get("metadata", {"fields": []}),
            "previous_documents": previous_documents,
        }

    return {
        "analyses": [
            {
                "analysis_id": item.get("analysis_id"),
                "document_name": item.get("document_name"),
                **item,
            }
            for item in results
        ],
        "cross_document_analysis": cross_document_analysis(results),
        "duplicate_documents": duplicates,
        "previous_documents": previous_documents,
    }


@router.get("/history", response_model=HistoryResponse)
def history() -> dict[str, object]:
    return {"analyses": get_history()}


@router.get("/report/{analysis_id}")
def report(analysis_id: str) -> dict[str, object]:
    result = load_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Report not found")
    return result
