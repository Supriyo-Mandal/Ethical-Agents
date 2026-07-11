from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.config import ALLOWED_EXTENSIONS
from app.core.knowledge_loader import load_repository
from app.core.report_builder import build_report
from app.services.json_storage import append_report
from backend.app.analysis import analyze_document, extract_text


async def process_uploaded_document(file: UploadFile) -> dict[str, Any]:
    if not file.filename:
        raise ValueError("A filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type")

    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        temp_path = Path(tmp.name)

    try:
        text = extract_text(temp_path, file.filename)
        result = analyze_document(text, file.filename)
    finally:
        temp_path.unlink(missing_ok=True)

    repository = load_repository("bias")
    report = build_report(file.filename, result, repository)
    append_report(report)
    return report
