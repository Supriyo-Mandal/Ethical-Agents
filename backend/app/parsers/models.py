from __future__ import annotations

from typing import Any


def block(block_id: str, block_type: str, text: str = "", **extra: Any) -> dict[str, Any]:
    return {"id": block_id, "type": block_type, "text": text, **extra}


def document_model(name: str, content_type: str, format_name: str) -> dict[str, Any]:
    return {
        "document_name": name,
        "document_type": content_type,
        "format": format_name,
        "pages": [],
        "plain_text": "",
        "metadata": {"ocr_used": False, "page_count": 0},
        "warnings": [],
    }


def finalize(document: dict[str, Any]) -> dict[str, Any]:
    lines: list[str] = []
    for page in document["pages"]:
        lines.append(f"[Page {page['page_number']}]")
        for item in page["blocks"]:
            text = item.get("text", "").strip()
            if text:
                label = item["type"].capitalize()
                lines.append(f"{label}: {text}")
    document["plain_text"] = "\n".join(lines).strip()
    document["metadata"]["page_count"] = len(document["pages"])
    return document
