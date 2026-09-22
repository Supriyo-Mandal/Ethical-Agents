from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from .config import REPORT_DIRECTORY


REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)


def save_analysis(document_name: str, result: dict[str, Any], user_id: str) -> dict[str, Any]:
    analysis_id = str(uuid4())
    report_path = REPORT_DIRECTORY / f"{analysis_id}.json"
    payload = {
        "id": analysis_id,
        "document_name": document_name,
        "owner_id": user_id,
        **result,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_analysis(analysis_id: str, user_id: str) -> dict[str, Any] | None:
    report_path = REPORT_DIRECTORY / f"{analysis_id}.json"
    if not report_path.exists():
        return None

    data = json.loads(report_path.read_text(encoding="utf-8"))
    if data.get("owner_id") != user_id:
        return None
    
    return data


def get_history(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(REPORT_DIRECTORY.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("owner_id") == user_id:
            items.append(data)
    return items


def delete_analysis(analysis_id: str, user_id: str) -> bool:
    report_path = REPORT_DIRECTORY / f"{analysis_id}.json"
    if not report_path.exists():
        return False

    data = json.loads(report_path.read_text(encoding="utf-8"))
    if data.get("owner_id") != user_id:
        return False

    report_path.unlink()
    return True
