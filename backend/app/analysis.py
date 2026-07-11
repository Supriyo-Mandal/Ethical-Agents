from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from docx import Document as DocxDocument
from PyPDF2 import PdfReader


RISK_FIELDS = {
    "Bias": ["fair", "bias", "discrimination", "ranking", "recommend", "automated", "decision"],
    "Security": ["security", "password", "token", "encryption", "attack", "vulnerability", "auth"],
    "Privacy": ["privacy", "personal", "data", "consent", "profile", "location", "email"],
    "Compliance": ["policy", "compliance", "regulation", "gdpr", "hipaa", "legal", "audit"],
    "Transparency": ["explain", "transparency", "audit", "trace", "review", "human", "report"],
}


def extract_text(file_path: Path, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        document = DocxDocument(str(file_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text)
    raise ValueError(f"Unsupported file type: {filename}")


def summarize_description(text: str, filename: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return f"Document {filename} was uploaded for review."
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    first_sentence = next((s for s in sentences if s), cleaned[:140])
    summary = first_sentence[:140].rstrip()
    if len(summary) == 140:
        summary += "..."
    return summary


def analyze_document(text: str, filename: str) -> Dict[str, object]:
    normalized = text.lower()
    fields_used: List[str] = []
    for field, keywords in RISK_FIELDS.items():
        if any(keyword in normalized for keyword in keywords):
            fields_used.append(field)

    strong_risk_terms = [
        "sensitive",
        "personal data",
        "without human",
        "automated decision",
        "profiling",
        "consent",
        "password",
        "token",
        "attack",
        "breach",
        "gdpr",
        "hipaa",
    ]
    strong_risk_hits = sum(1 for term in strong_risk_terms if term in normalized)

    risk_score = min(0.98, 0.2 + 0.12 * len(fields_used) + 0.06 * strong_risk_hits)
    publish = risk_score < 0.7

    if publish:
        decision_text = "Publish"
        reason_paragraph = (
            "The document presents a manageable risk profile because the identified concerns are limited "
            "and the content can be published with standard safeguards."
        )
        summary = "The review found moderate or low risk and recommends publication."
    else:
        decision_text = "Do Not Publish"
        reason_paragraph = (
            "The document contains material risk indicators such as sensitive data handling, automated "
            "decision-making, or weak transparency controls that justify withholding publication."
        )
        summary = "The review found significant risk and recommends withholding publication."

    if fields_used:
        fields_text = ", ".join(fields_used)
        if publish:
            reason_paragraph += f" The review focused on the following domains: {fields_text}."
        else:
            reason_paragraph += f" The review focused on the following domains: {fields_text}."

    return {
        "decision": decision_text,
        "publish": publish,
        "overall_score": round(risk_score, 2),
        "metadata": {
            "paragraph": reason_paragraph,
            "summary": summary,
            "fields_used": fields_used,
            "description": summarize_description(text, filename),
        },
    }
