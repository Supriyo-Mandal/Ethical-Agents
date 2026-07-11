from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from app.orchestrator import analyze_document


def _extract_text(file: Any) -> str:
    """
    Read bytes from an UploadFile (or any file-like object) and return
    plain text.  Supports .txt, .md, .pdf, and .docx.
    Falls back to a best-effort UTF-8 decode for everything else.
    """
    filename: str = getattr(file, "filename", "") or ""
    suffix = Path(filename).suffix.lower()

    # Read raw bytes — works for both SpooledTemporaryFile and BytesIO
    raw: bytes = b""
    if hasattr(file, "file"):
        # FastAPI UploadFile wraps a SpooledTemporaryFile in .file
        file.file.seek(0)
        raw = file.file.read()
        file.file.seek(0)  # rewind so FastAPI can still close it cleanly
    elif hasattr(file, "read"):
        raw = file.read()
    else:
        return ""

    if not raw:
        return ""

    # ── Plain text / Markdown ──────────────────────────────────────────
    if suffix in (".txt", ".md", ""):
        return raw.decode("utf-8", errors="replace")

    # ── PDF ───────────────────────────────────────────────────────────
    if suffix == ".pdf":
        try:
            import pypdf  # preferred
            reader = pypdf.PdfReader(io.BytesIO(raw))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
        except ImportError:
            pass
        try:
            import pdfminer.high_level as pdfminer  # type: ignore
            return pdfminer.extract_text(io.BytesIO(raw)).strip()
        except ImportError:
            pass
        # Last-resort: decode bytes and hope for the best
        return raw.decode("utf-8", errors="replace")

    # ── DOCX ──────────────────────────────────────────────────────────
    if suffix == ".docx":
        try:
            import docx  # python-docx
            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except ImportError:
            pass
        return raw.decode("utf-8", errors="replace")

    # ── Fallback ──────────────────────────────────────────────────────
    return raw.decode("utf-8", errors="replace")


def analyze(file: Any) -> dict[str, Any]:
    """
    Extract text from the uploaded file, then pass it as a plain string
    to the agent orchestrator.  The orchestrator and all agents expect
    the payload to carry 'document_text' so normalize_document_payload
    can route it into the messages array correctly.
    """
    text = _extract_text(file)

    payload = {
        "document_name": getattr(file, "filename", "document") or "document",
        "document_type": getattr(file, "content_type", "text/plain") or "text/plain",
        "document_text": text,   # <-- agents receive actual text, not a file object
    }

    result = analyze_document(payload)

    if not isinstance(result, dict):
        raise TypeError("The agent orchestrator must return a dictionary")

    return result
