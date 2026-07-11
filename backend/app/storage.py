from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from .config import REPORT_DIRECTORY


REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)


def save_analysis(document_payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    analysis_id = str(uuid4())
    report_path = REPORT_DIRECTORY / f"{analysis_id}.json"
    document = document_payload.get("document", {})
    payload = {
        "id": analysis_id,
        "document_name": document.get("name", "document"),
        "document_type": document.get("type", "txt"),
        "document": document,
        **result,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_analysis(analysis_id: str) -> dict[str, Any] | None:
    report_path = REPORT_DIRECTORY / f"{analysis_id}.json"
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))


def get_history() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(REPORT_DIRECTORY.glob("*.json"))]


def delete_analysis(analysis_id: str) -> bool:
    report_path = REPORT_DIRECTORY / f"{analysis_id}.json"
    if report_path.exists():
        report_path.unlink()
        return True
    return False
