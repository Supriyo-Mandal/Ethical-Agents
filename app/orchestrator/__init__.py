from __future__ import annotations

from typing import Any

from app.orchestrator.parent_agent import ParentAgent


def analyze_document(payload: Any) -> dict[str, Any]:
    """
    Entry point called by the backend.

    Accepts the raw document payload, routes it through the ParentAgent,
    and returns a schema the backend can serialize directly.
    """
    document_name = "document"
    if isinstance(payload, dict):
        document_name = str(payload.get("document_name", "document"))

    result = ParentAgent().evaluate_document(payload, document_name)
    return _to_backend_schema(result)


def _to_backend_schema(result: dict[str, Any]) -> dict[str, Any]:
    """
    Map the ParentAgent output to the shape the FastAPI backend (and
    the frontend) expect.

    ParentAgent returns:
        decision, publish, overall_score,
        agent_outputs[], high_risk_fields[], newly_learned_fields[],
        executive_summary, recommendations[]

    Backend AnalysisResponse expects:
        publish, overall_score, summary, metadata: { fields[], ... }
    """
    # Build a flat list of all evaluated fields for display
    all_fields: list[dict[str, Any]] = []
    for agent_output in result.get("agent_outputs", []):
        agent_name = agent_output.get("agent", "Unknown")
        field_scores = agent_output.get("field_scores") or {}
        field_reasons = agent_output.get("field_reasons") or {}

        for field_name, score in field_scores.items():
            all_fields.append(
                {
                    "agent": agent_name,
                    "field": field_name,
                    "score": score,
                    "reason": field_reasons.get(field_name, ""),
                    "high_risk": score >= ParentAgent.THRESHOLD,
                }
            )

    # Sort so high-risk fields appear first
    all_fields.sort(key=lambda x: x["score"], reverse=True)

    metadata: dict[str, Any] = {
        "fields": all_fields,
        "high_risk_fields": result.get("high_risk_fields", []),
        "newly_learned_fields": result.get("newly_learned_fields", []),
        "decision": result.get("decision", "Unknown"),
        "executive_summary": result.get("executive_summary", ""),
        "recommendations": result.get("recommendations", []),
        "domain_scores": {
            d["agent"]: d["overall_score"]
            for d in result.get("agent_outputs", [])
        },
    }

    return {
        "publish": result.get("publish", False),
        "overall_score": result.get("overall_score", 0.0),
        "summary": result.get("executive_summary", "Analysis complete."),
        "metadata": metadata,
    }
