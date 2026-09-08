from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any
import re

from app.orchestrator import analyze_document
from .config import MAX_UPLOAD_BYTES
from .parsers import parse_upload


def _extract_text(file: Any) -> str:
    """
    Read bytes from an UploadFile (or any file-like object) and return
    plain text.  Supports .txt, .md, .pdf, and .docx.
    Falls back to a best-effort UTF-8 decode for everything else.
    """
    document = _parse_document(file)
    return document["plain_text"]


def _read_bytes(file: Any) -> bytes:
    raw: bytes = b""
    if hasattr(file, "file"):
        file.file.seek(0)
        raw = file.file.read()
        file.file.seek(0)
    elif hasattr(file, "read"):
        raw = file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file exceeds the 20 MB limit")
    return raw


def _parse_document(file: Any) -> dict[str, Any]:
    filename = getattr(file, "filename", "document") or "document"
    content_type = getattr(file, "content_type", "application/octet-stream") or "application/octet-stream"
    return parse_upload(_read_bytes(file), filename, content_type)


def analyze(file: Any) -> dict[str, Any]:
    """
    Extract text from the uploaded file, then pass it as a plain string
    to the agent orchestrator.  The orchestrator and all agents expect
    the payload to carry 'document_text' so normalize_document_payload
    can route it into the messages array correctly.
    """
    document = _parse_document(file)

    payload = {
        "document_name": getattr(file, "filename", "document") or "document",
        "document_type": getattr(file, "content_type", "text/plain") or "text/plain",
        "document_text": document["plain_text"],
        "document_content": document,
    }

    result = analyze_document(payload)

    if not isinstance(result, dict):
        raise TypeError("The agent orchestrator must return a dictionary")

    return result


def cross_document_analysis(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare completed document analyses without sending documents to another model."""
    if len(results) < 2:
        return {"document_count": len(results), "shared_high_risk_fields": [], "similarity": []}

    field_documents: dict[str, set[str]] = {}
    domain_scores: dict[str, list[float]] = {}
    texts: dict[str, set[str]] = {}
    for result in results:
        name = str(result.get("document_name", "document"))
        metadata = result.get("metadata") or {}
        for item in metadata.get("high_risk_fields", []):
            field_name = str(item.get("field_name", item.get("field", ""))).strip()
            if field_name:
                field_documents.setdefault(field_name, set()).add(name)
        for domain, score in (metadata.get("domain_scores") or {}).items():
            domain_scores.setdefault(domain, []).append(float(score))
        content = metadata.get("document_content") or {}
        texts[name] = set(re.findall(r"[a-z0-9]{3,}", str(content.get("plain_text", "")).lower()))

    shared = [
        {"field": field, "documents": sorted(names), "document_count": len(names)}
        for field, names in field_documents.items()
        if len(names) > 1
    ]
    ranges = {
        domain: {
            "minimum": min(scores),
            "maximum": max(scores),
            "delta": max(scores) - min(scores),
        }
        for domain, scores in domain_scores.items()
    }
    names = list(texts)
    similarity = []
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            union = texts[first] | texts[second]
            score = len(texts[first] & texts[second]) / len(union) if union else 1.0
            similarity.append({"documents": [first, second], "jaccard": round(score, 4)})

    return {
        "document_count": len(results),
        "shared_high_risk_fields": shared,
        "domain_score_ranges": ranges,
        "text_similarity": similarity,
    }


def detect_duplicate_documents(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find likely duplicate documents using title and extracted-text similarity."""
    candidates = [(item, False) for item in current] + [(item, True) for item in previous]
    matches: list[dict[str, Any]] = []
    for index, (first, first_previous) in enumerate(candidates):
        first_name = str(first.get("document_name", first.get("name", "document")))
        first_title = _document_title(first_name)
        first_tokens = _document_tokens(first)
        if not first_tokens:
            continue
        for second, second_previous in candidates[index + 1:]:
            if first_previous and second_previous:
                continue
            second_name = str(second.get("document_name", second.get("name", "document")))
            if first_name == second_name and first_previous == second_previous:
                continue
            second_tokens = _document_tokens(second)
            if not second_tokens:
                continue
            title_score = SequenceMatcher(None, first_title, _document_title(second_name)).ratio()
            semantic_score = len(first_tokens & second_tokens) / len(first_tokens | second_tokens)
            if (title_score >= 0.9 and semantic_score >= 0.65) or (title_score >= 0.45 and semantic_score >= 0.9):
                matches.append({
                    "documents": [first_name, second_name],
                    "title_similarity": round(title_score, 4),
                    "semantic_similarity": round(semantic_score, 4),
                    "confidence": round((title_score + semantic_score) / 2, 4),
                    "reason": "Matching title and highly similar extracted content",
                })
    return matches


def _document_title(name: str) -> str:
    title = re.sub(r"\.[^.]+$", "", name).lower()
    title = re.sub(r"\b(copy|final|draft|version|v\d+)\b", " ", title)
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def _document_tokens(document: dict[str, Any]) -> set[str]:
    metadata = document.get("metadata") or {}
    content = metadata.get("document_content") or document.get("document_content") or {}
    text = content.get("plain_text", "") if isinstance(content, dict) else ""
    return set(re.findall(r"[a-z0-9]{3,}", str(text).lower()))
