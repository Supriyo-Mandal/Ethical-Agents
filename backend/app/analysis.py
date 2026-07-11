from __future__ import annotations

from typing import Any

try:
    from app.orchestrator import analyze_document as framework_analyze
except Exception:  # pragma: no cover - defensive fallback
    framework_analyze = None


def analyze(document: Any) -> dict[str, Any]:
    if framework_analyze is None:
        return {
            "publish": False,
            "summary": "Framework unavailable",
            "metadata": {"fields": []},
        }

    result = framework_analyze(document)
    if not isinstance(result, dict):
        raise TypeError("The AI framework must return a dictionary")
    return result
