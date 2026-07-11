from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from app.orchestrator import analyze_document as framework_analyze
except Exception:  # pragma: no cover - defensive fallback
    framework_analyze = None


def build_document_payload(file_name: str, file_type: str, content: str) -> dict[str, Any]:
    return {
        "document": {
            "name": file_name,
            "type": file_type,
            "content": content,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
    }


def analyze(document: dict[str, Any]) -> dict[str, Any]:
    if framework_analyze is None:
        return {
            "publish": False,
            "overall_score": 0.0,
            "summary": "Framework unavailable",
            "metadata": {"fields": []},
        }

    result = framework_analyze(document)
    if not isinstance(result, dict):
        raise TypeError("The AI framework must return a dictionary")
    return result
