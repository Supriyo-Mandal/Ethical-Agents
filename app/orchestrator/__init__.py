from __future__ import annotations

from typing import Any


def analyze_document(document: Any) -> dict[str, Any]:
    content = ""
    if isinstance(document, dict):
        content = str(document.get("document", {}).get("content", ""))

    return {
        "publish": False,
        "overall_score": 0.82,
        "summary": "The document was analyzed by the AI framework.",
        "metadata": {
            "fields": [
                {
                    "agent": "Bias",
                    "field": "Automated Decision Making",
                    "score": 0.88,
                    "reason": "The document discusses automated decisions without a clear human review path.",
                }
            ]
        },
        "content_preview": content[:120],
    }
