from __future__ import annotations

from typing import Any


class BaseAgent:
    def __init__(self, name: str, threshold: float = 0.7) -> None:
        self.name = name
        self.threshold = threshold

    def evaluate(self, document_text: str, filename: str) -> dict[str, Any]:
        return {
            "agent": self.name,
            "overall_score": 0.0,
            "evaluated_fields": [],
            "new_fields": [],
        }
