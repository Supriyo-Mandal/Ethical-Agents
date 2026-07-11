from __future__ import annotations

from typing import Any

from app.services.document_payload import normalize_document_payload


class ParentAgent:
    """
    Orchestrator that coordinates all domain risk agents and produces a
    final publication decision.

    Responsibilities
    ----------------
    • Run every specialized agent against the document in sequence.
    • Collect and aggregate per-agent outputs — NO domain analysis here.
    • Identify the highest-risk domains and the individual high-risk fields.
    • Build an executive summary with the reasoning behind the decision.
    • Attach per-domain scores, high-risk field details, newly learned
      fields, and recommendations to the final report.

    Decision rule
    -------------
    The document is withheld from publication when the highest individual
    domain score meets or exceeds the threshold.  This is intentionally
    conservative: one severely problematic domain is enough to block
    publication even if all other domains score low.
    """

    THRESHOLD: float = 0.7

    def __init__(self) -> None:
        self.threshold = self.THRESHOLD

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    def evaluate_document(
        self,
        document_payload: dict[str, Any],
        filename: str = "document",
    ) -> dict[str, Any]:
        from app.agents.bias.agent import BiasAgent
        from app.agents.compliance.agent import ComplianceAgent
        from app.agents.privacy.agent import PrivacyAgent
        from app.agents.security.agent import SecurityAgent
        from app.agents.transparency.agent import TransparencyAgent

        normalized = normalize_document_payload(document_payload)
        agents = [BiasAgent, PrivacyAgent, SecurityAgent, ComplianceAgent, TransparencyAgent]
        agent_outputs = [cls().evaluate(normalized, filename) for cls in agents]

        return self._decide(agent_outputs)

    # ------------------------------------------------------------------ #
    #  Decision phase                                                      #
    # ------------------------------------------------------------------ #

    def _decide(self, agent_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not agent_outputs:
            return {
                "decision": "Publish",
                "publish": True,
                "overall_score": 0.0,
                "agent_outputs": [],
                "high_risk_fields": [],
                "newly_learned_fields": [],
                "executive_summary": "No domain agents produced results.",
                "recommendations": [],
            }

        # ── Collect per-agent summaries ────────────────────────────────
        domain_summaries: list[dict[str, Any]] = []
        all_high_risk_fields: list[dict[str, Any]] = []
        all_newly_learned: list[dict[str, Any]] = []

        for output in agent_outputs:
            agent_name = output.get("agent_name") or output.get("agent", "Unknown")
            agent_score = float(output.get("overall_score", 0.0) or 0.0)
            evaluated = output.get("evaluated_fields") or []
            field_scores = output.get("field_scores") or {}
            field_reasons = output.get("field_reasons") or {}

            # High-risk fields are those at or above the threshold
            high_risk = [
                {
                    "agent": agent_name,
                    "field_name": f["field_name"],
                    "score": f["score"],
                    "reason": field_reasons.get(f["field_name"], ""),
                }
                for f in evaluated
                if f.get("score", 0.0) >= self.threshold
            ]
            all_high_risk_fields.extend(high_risk)

            # Newly learned fields from this agent
            for nf in output.get("newly_learned_fields") or []:
                all_newly_learned.append({"agent": agent_name, **nf})

            domain_summaries.append(
                {
                    "agent": agent_name,
                    "overall_score": round(agent_score, 3),
                    "field_scores": field_scores,
                    "field_reasons": field_reasons,
                    "evaluated_fields": evaluated,
                    "high_risk_field_count": len(high_risk),
                }
            )

        # ── Aggregate scores ───────────────────────────────────────────
        scores = [d["overall_score"] for d in domain_summaries]
        overall_score = round(max(scores), 3) if scores else 0.0
        publish = overall_score < self.threshold

        # ── Identify highest-risk domains ──────────────────────────────
        high_risk_domains = sorted(
            [d for d in domain_summaries if d["overall_score"] >= self.threshold],
            key=lambda x: x["overall_score"],
            reverse=True,
        )
        high_risk_domain_names = [d["agent"] for d in high_risk_domains]

        # ── Build executive summary ────────────────────────────────────
        executive_summary = self._build_executive_summary(
            publish, overall_score, high_risk_domain_names, all_high_risk_fields
        )

        # ── Build recommendations ──────────────────────────────────────
        recommendations = self._build_recommendations(
            high_risk_domain_names, all_high_risk_fields
        )

        return {
            "decision": "Publish" if publish else "Do Not Publish",
            "publish": publish,
            "overall_score": overall_score,
            "agent_outputs": domain_summaries,
            "high_risk_fields": all_high_risk_fields,
            "newly_learned_fields": all_newly_learned,
            "executive_summary": executive_summary,
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------ #
    #  Summary and recommendation builders                                 #
    # ------------------------------------------------------------------ #

    def _build_executive_summary(
        self,
        publish: bool,
        overall_score: float,
        high_risk_domains: list[str],
        high_risk_fields: list[dict[str, Any]],
    ) -> str:
        score_pct = int(overall_score * 100)

        if publish:
            if overall_score == 0.0:
                return (
                    "No risk indicators were detected across any domain. "
                    "The document is clear for publication."
                )
            return (
                f"The document presents a manageable risk profile (overall score: "
                f"{score_pct}/100). All domain scores remain below the publication "
                f"threshold of {int(self.threshold * 100)}/100. No critical risk "
                f"indicators require withholding."
            )

        domain_list = ", ".join(high_risk_domains) if high_risk_domains else "multiple domains"
        field_count = len(high_risk_fields)
        return (
            f"Publication is withheld due to elevated risk in the following "
            f"domain(s): {domain_list}. Overall risk score: {score_pct}/100 "
            f"(threshold: {int(self.threshold * 100)}/100). "
            f"{field_count} high-risk field(s) require remediation before "
            f"this document can be approved."
        )

    def _build_recommendations(
        self,
        high_risk_domains: list[str],
        high_risk_fields: list[dict[str, Any]],
    ) -> list[str]:
        if not high_risk_domains:
            return ["Document meets publication standards. No action required."]

        recs: list[str] = []
        seen_domains: set[str] = set()

        for field in high_risk_fields:
            domain = field.get("agent", "")
            field_name = field.get("field_name", "")
            score = field.get("score", 0.0)
            reason = field.get("reason", "")

            if domain not in seen_domains:
                seen_domains.add(domain)
                recs.append(
                    f"[{domain}] Review and remediate '{field_name}' "
                    f"(score {score:.2f}): {reason}"
                )
            else:
                recs.append(
                    f"[{domain}] Also address '{field_name}' (score {score:.2f})."
                )

        return recs if recs else [
            "Review flagged domains and address all high-risk fields before publication."
        ]
