from __future__ import annotations

from typing import Any


def build_report(filename: str, result: dict[str, Any], repository: list[dict[str, object]]) -> dict[str, Any]:
    return {
        "id": filename,
        "name": filename,
        "description": result["metadata"]["description"],
        "decision": result["decision"],
        "publish": result["publish"],
        "overall_score": result["overall_score"],
        "summary": result["metadata"]["summary"],
        "paragraph": result["metadata"]["paragraph"],
        "fields_used": result["metadata"]["fields_used"],
        "repository_size": len(repository),
    }
