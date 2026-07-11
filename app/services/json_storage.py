from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

REPORTS_FILE = BASE_DIR / "reports.json"


def load_reports() -> list[dict[str, Any]]:
    if not REPORTS_FILE.exists():
        return []
    return json.loads(REPORTS_FILE.read_text(encoding="utf-8"))


def append_report(report: dict[str, Any]) -> None:
    reports = load_reports()
    reports.append(report)
    REPORTS_FILE.write_text(json.dumps(reports, indent=2), encoding="utf-8")
