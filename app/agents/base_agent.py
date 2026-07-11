from __future__ import annotations

import json
import re
from typing import Any

from app.config import THRESHOLD
from app.services.fireworks_client import call_fireworks
from app.services.knowledge_repository import append_new_fields, load_prompt, load_repository


class BaseAgent:
    def __init__(self, name: str, threshold: float = THRESHOLD) -> None:
        self.name = name
        self.threshold = threshold
        self.agent_key = name.lower()

    def evaluate(self, document_text: str | dict[str, Any], filename: str | None = None) -> dict[str, Any]:
        payload = document_text if isinstance(document_text, dict) else None
        text = self._extract_document_text(document_text, filename or "document")
        repository = load_repository(self.agent_key)
        prompt = load_prompt(self.agent_key)
        normalized = " ".join(re.findall(r"\w+", text.lower()))

        evaluated_fields: list[dict[str, Any]] = []
        for entry in repository:
            field_name = str(entry.get("field_name", "")).strip()
            description = str(entry.get("description", "")).strip()
            reason = str(entry.get("reason", "")).strip()
            examples = entry.get("examples") or []
            if not field_name:
                continue

            match_score = self._match_score(field_name, description, reason, examples, normalized)
            if match_score <= 0.0:
                continue

            evaluated_fields.append(
                {
                    "field_id": entry.get("field_id"),
                    "field_name": field_name,
                    "score": round(match_score, 2),
                    "reason": reason,
                }
            )

        if not evaluated_fields:
            overall_score = 0.0
        else:
            overall_score = round(sum(item["score"] for item in evaluated_fields) / len(evaluated_fields), 2)

        field_scores = {item["field_name"]: item["score"] for item in evaluated_fields}
        field_reasons = {item["field_name"]: item["reason"] for item in evaluated_fields}

        new_fields = []
        if isinstance(document_text, dict):
            new_fields = self._infer_new_fields(text, repository)

        fireworks_result = None
        proposed_fields = []
        if isinstance(document_text, dict):
            fireworks_result = call_fireworks(prompt, self._render_payload(document_text, text))
            proposed_fields = self._extract_proposed_fields(fireworks_result, text, repository)
            if proposed_fields:
                append_new_fields(self.agent_key, proposed_fields)

        return {
            "agent": self.name,
            "agent_name": self.name,
            "overall_score": overall_score,
            "threshold": self.threshold,
            "evaluated_fields": evaluated_fields,
            "field_scores": field_scores,
            "field_reasons": field_reasons,
            "new_fields": new_fields,
            "proposed_fields": proposed_fields,
            "system_prompt": prompt,
            "filename": filename or "document",
            "input_format": "fireworks_payload" if payload else "plain_text",
            "fireworks_result": fireworks_result,
        }

    def _extract_document_text(self, document_text: str | dict[str, Any], filename: str) -> str:
        if isinstance(document_text, dict):
            payload = document_text
            messages = payload.get("messages") or []
            if isinstance(messages, list):
                for item in messages:
                    if isinstance(item, dict):
                        content = item.get("content")
                        if isinstance(content, str):
                            return content
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and isinstance(block.get("text"), str):
                                    return block["text"]
            if isinstance(payload.get("document_text"), str):
                return payload["document_text"]
            if isinstance(payload.get("text"), str):
                return payload["text"]
            return ""
        return str(document_text or "")

    def _render_payload(self, document_text: str | dict[str, Any], text: str) -> str:
        if isinstance(document_text, dict):
            return json.dumps(document_text, indent=2)
        return text

    def _match_score(self, field_name: str, description: str, reason: str, examples: list[Any], normalized_text: str) -> float:
        tokens = [field_name.lower(), description.lower(), reason.lower()]
        if examples:
            tokens.extend(str(example).lower() for example in examples)
        haystack = " ".join(tokens)
        if not haystack:
            return 0.0

        score = 0.0
        for token in re.findall(r"\w+", haystack):
            if token in normalized_text:
                score += 0.08
        if any(term in normalized_text for term in re.findall(r"\w+", field_name.lower())):
            score += 0.2
        if any(term in normalized_text for term in re.findall(r"\w+", description.lower())):
            score += 0.2
        if any(term in normalized_text for term in re.findall(r"\w+", reason.lower())):
            score += 0.2
        return min(1.0, round(score, 2))

    def _infer_new_fields(self, document_text: str, repository: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return the seed-only repository entries as the current knowledge base state."""
        return []

    def _extract_proposed_fields(self, fireworks_result: Any, document_text: str, repository: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(fireworks_result, dict):
            return []

        candidate_fields = fireworks_result.get("candidate_fields") or []
        if not isinstance(candidate_fields, list):
            return []

        existing_names = {
            str(entry.get("field_name", "")).strip().lower()
            for entry in repository
            if str(entry.get("field_name", "")).strip()
        }
        proposed_fields = []
        for field in candidate_fields:
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("field_name", "")).strip()
            if not field_name:
                continue
            if field_name.lower() in existing_names:
                continue
            if len(field_name.split()) > 6:
                continue
            proposed_fields.append(
                {
                    "field_name": field_name,
                    "description": str(field.get("description") or f"Reusable {self.name.lower()} concept related to {field_name}."),
                    "reason": str(field.get("reason") or f"{field_name} is a reusable {self.name.lower()} domain concept."),
                    "examples": field.get("examples") or [],
                    "document_excerpt": document_text[:240],
                }
            )
        return proposed_fields
