from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import docx
import PyPDF2
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..analysis import analyze, build_document_payload
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

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Document content is required")

    if suffix == ".txt":
        text = contents.decode("utf-8", errors="ignore")
    elif suffix == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(contents)
            temp_path = handle.name
        try:
            text = "\n".join(page.extract_text() or "" for page in PyPDF2.PdfReader(temp_path).pages)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    else:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as handle:
            handle.write(contents)
            temp_path = handle.name
        try:
            text = "\n".join(paragraph.text for paragraph in docx.Document(temp_path).paragraphs if paragraph.text)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    document_payload = build_document_payload(file.filename, suffix.lstrip("."), text)
    analysis_result = analyze(document_payload)
    save_analysis(document_payload, analysis_result)

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
