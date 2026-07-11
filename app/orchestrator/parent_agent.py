from __future__ import annotations

from typing import Any


class ParentAgent:
    def __init__(self) -> None:
        self.threshold = 0.7

    def decide(self, agent_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        scores = [item.get("overall_score", 0.0) for item in agent_outputs]
        overall_score = max(scores) if scores else 0.0
        publish = overall_score < self.threshold
        return {
            "decision": "Publish" if publish else "Do Not Publish",
            "publish": publish,
            "overall_score": round(overall_score, 2),
            "agent_outputs": agent_outputs,
        }
