from __future__ import annotations

from typing import Any

from app.orchestrator import analyze_document


def analyze(file: Any) -> dict[str, Any]:
    payload = {
        "document_name": file.filename,
        "document_type": file.content_type,
        "document": file,
    }

    result = analyze_document(payload)

    if not isinstance(result, dict):
        raise TypeError("The AI framework must return a dictionary")

    return result
