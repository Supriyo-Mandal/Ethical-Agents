from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .analysis import analyze_document, extract_text
from .storage import add_document_record, get_document_summaries


class UploadResponse(dict):
    pass

app = FastAPI(title="Ethical Agents Risk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".txt", ".md", ".pdf", ".docx"}:
            return JSONResponse(status_code=400, content={"detail": "Unsupported file type"})

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = Path(tmp.name)

        try:
            text = extract_text(temp_path, file.filename or "uploaded-document")
            result = analyze_document(text, file.filename or "uploaded-document")
        finally:
            temp_path.unlink(missing_ok=True)

        record = {
            "id": None,
            "name": file.filename or "uploaded-document",
            "description": result["metadata"]["description"],
            "decision": result["decision"],
            "summary": result["metadata"]["summary"],
            "paragraph": result["metadata"]["paragraph"],
            "fields_used": result["metadata"]["fields_used"],
            "overall_score": result["overall_score"],
        }
        saved = add_document_record(record)
        return {
            "document_id": saved["id"],
            "document_name": saved["name"],
            "publish": result["publish"],
            "decision": result["decision"],
            "overall_score": result["overall_score"],
            "metadata": result["metadata"],
        }
    except Exception as exc:  # pragma: no cover - defensive path for runtime errors
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    return await analyze(file)


@app.get("/documents")
def documents() -> Dict[str, Any]:
    records = get_document_summaries()
    return {"documents": records}


@app.get("/output")
def output() -> Dict[str, Any]:
    records = get_document_summaries()
    latest = records[-1] if records else None
    return {
        "latest_result": {
            "document_id": latest.get("id") if latest else None,
            "document_name": latest.get("name") if latest else None,
            "publish": latest.get("decision") == "Publish" if latest else None,
            "decision": latest.get("decision") if latest else None,
            "overall_score": latest.get("overall_score") if latest else None,
            "metadata": {
                "paragraph": latest.get("paragraph") if latest else None,
                "summary": latest.get("summary") if latest else None,
                "fields_used": latest.get("fields_used", []) if latest else [],
                "description": latest.get("description") if latest else None,
            },
        }
        if latest
        else None,
        "documents": [
            {
                "name": item.get("name"),
                "description": item.get("description"),
                "decision": item.get("decision"),
            }
            for item in records
        ],
    }
