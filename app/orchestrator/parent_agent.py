from __future__ import annotations

from typing import Any

from app.services.document_payload import normalize_document_payload


class ParentAgent:
    def __init__(self) -> None:
        self.threshold = 0.7

    def evaluate_document(self, document_payload: dict[str, Any], filename: str = "document") -> dict[str, Any]:
        from app.agents.bias.agent import BiasAgent
        from app.agents.compliance.agent import ComplianceAgent
        from app.agents.privacy.agent import PrivacyAgent
        from app.agents.security.agent import SecurityAgent
        from app.agents.transparency.agent import TransparencyAgent

        normalized_payload = normalize_document_payload(document_payload)
        agent_classes = [BiasAgent, PrivacyAgent, SecurityAgent, ComplianceAgent, TransparencyAgent]
        agent_outputs = [agent_cls().evaluate(normalized_payload, filename) for agent_cls in agent_classes]
        return self.decide(agent_outputs)

    def decide(self, agent_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not agent_outputs:
            return {
                "decision": "Publish",
                "publish": True,
                "overall_score": 0.0,
                "agent_outputs": [],
                "summary": "No domain agents produced results.",
            }

        aggregated_scores = []
        field_summaries: list[dict[str, Any]] = []
        for item in agent_outputs:
            score = float(item.get("overall_score", 0.0) or 0.0)
            aggregated_scores.append(score)
            field_summaries.append(
                {
                    "agent": item.get("agent_name") or item.get("agent"),
                    "overall_score": round(score, 2),
                    "field_scores": item.get("field_scores") or {},
                    "field_reasons": item.get("field_reasons") or {},
                    "evaluated_fields": item.get("evaluated_fields") or [],
                }
            )

        overall_score = max(aggregated_scores) if aggregated_scores else 0.0
        publish = overall_score < self.threshold

        return {
            "decision": "Publish" if publish else "Do Not Publish",
            "publish": publish,
            "overall_score": round(overall_score, 2),
            "agent_outputs": field_summaries,
            "summary": (
                "The document presents a manageable risk profile because the highest domain score remains below the review threshold."
                if publish
                else "The document contains material risk indicators that justify withholding publication."
            ),
        }
