from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from app.orchestrator import analyze_document
from .document_chunking import build_document_chunks


def _extract_text(file: Any) -> str:
    """
    Read bytes from an UploadFile (or any file-like object) and return
    plain text. Supports .txt, .md, .pdf, and .docx.
    Falls back to a best-effort UTF-8 decode for everything else.
    """
    filename: str = getattr(file, "filename", "") or ""
    suffix = Path(filename).suffix.lower()

    raw: bytes = b""
    if hasattr(file, "file"):
        file.file.seek(0)
        raw = file.file.read()
        file.file.seek(0)
    elif hasattr(file, "read"):
        raw = file.read()
    else:
        return ""

    if not raw:
        return ""

    if suffix in (".txt", ".md", ""):
        return raw.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except ImportError:
            pass

        try:
            import pdfminer.high_level as pdfminer  # type: ignore
            return pdfminer.extract_text(io.BytesIO(raw)).strip()
        except ImportError:
            pass

        return raw.decode("utf-8", errors="replace")

    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except ImportError:
            pass
        return raw.decode("utf-8", errors="replace")

    return raw.decode("utf-8", errors="replace")


def analyze(file: Any) -> dict[str, Any]:
    """
    Extract text from the uploaded file, then pass it as a plain string
    to the agent orchestrator. The orchestrator and all agents expect
    the payload to carry 'document_text' so normalize_document_payload
    can route it into the messages array correctly.
    """
    raw = b""
    if hasattr(file, "file"):
        file.file.seek(0)
        raw = file.file.read()
        file.file.seek(0)
    elif hasattr(file, "read"):
        raw = file.read()

    filename = getattr(file, "filename", "document") or "document"
    document_chunks = build_document_chunks(raw, filename) if raw else []
    text = _extract_text(file)

    payload = {
        "document_name": getattr(file, "filename", "document") or "document",
        "document_type": getattr(file, "content_type", "text/plain") or "text/plain",
        "document_text": text,
    }

    result = analyze_document(payload)

    if not isinstance(result, dict):
        raise TypeError("The agent orchestrator must return a dictionary")

    result["_document_chunks"] = document_chunks
    return result
