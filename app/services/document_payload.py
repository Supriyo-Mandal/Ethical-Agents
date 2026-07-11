from __future__ import annotations

from typing import Any


def normalize_document_payload(document_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document_payload, dict):
        return {"messages": [{"role": "user", "content": str(document_payload)}]}

    if "messages" in document_payload:
        return document_payload

    if "document" in document_payload:
        document_value = document_payload.get("document")
        if isinstance(document_value, str) and document_value.strip():
            return {
                "document_name": document_payload.get("document_name", "document"),
                "document_type": document_payload.get("document_type"),
                "messages": [{"role": "user", "content": document_value}],
            }

    if "document_text" in document_payload and isinstance(document_payload.get("document_text"), str):
        return {"messages": [{"role": "user", "content": document_payload["document_text"]}]}

    if "text" in document_payload and isinstance(document_payload.get("text"), str):
        return {"messages": [{"role": "user", "content": document_payload["text"]}]}

    if document_payload:
        text_candidates = []
        for key in ("content", "body", "data"):
            value = document_payload.get(key)
            if isinstance(value, str) and value.strip():
                text_candidates.append(value)
        if text_candidates:
            return {"messages": [{"role": "user", "content": text_candidates[0]}]}

    return {"messages": [{"role": "user", "content": ""}]}
