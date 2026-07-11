from __future__ import annotations

from app.services.json_storage import load_reports


def list_reports_route() -> dict[str, object]:
    reports = load_reports()
    latest = reports[-1] if reports else None
    return {
        "latest_result": latest,
        "documents": [
            {
                "name": item.get("name"),
                "description": item.get("description"),
                "decision": item.get("decision"),
            }
            for item in reports
        ],
    }
