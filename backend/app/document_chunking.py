from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path


def extract_pages(raw: bytes, filename: str) -> list[dict[str, object]]:
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(raw))
            return [
                {"page_number": page_number, "text": page.extract_text() or ""}
                for page_number, page in enumerate(reader.pages, start=1)
            ]
        except ImportError:
            pass

    if suffix == ".docx":
        try:
            import docx

            document = docx.Document(io.BytesIO(raw))
            text = "\n\n".join(paragraph.text for paragraph in document.paragraphs).strip()
            return [{"page_number": 1, "text": text}]
        except ImportError:
            pass

    text = raw.decode("utf-8", errors="replace")
    return [{"page_number": 1, "text": text}]


def chunk_pages(
    pages: list[dict[str, object]],
    target_tokens: int = 700,
    overlap_tokens: int = 80,
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    chunk_index = 0
    max_words = target_tokens
    overlap_words = min(overlap_tokens, max_words // 2)

    for page in pages:
        page_number = int(page.get("page_number", 1))
        text = str(page.get("text", "")).strip()
        if not text:
            continue

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        words: list[str] = []
        for paragraph in paragraphs:
            paragraph_words = paragraph.split()
            if not paragraph_words:
                continue
            if words and len(words) + len(paragraph_words) > max_words:
                chunks.append(_make_chunk(chunk_index, page_number, words))
                chunk_index += 1
                words = words[-overlap_words:]
            words.extend(paragraph_words)

            while len(words) > max_words:
                chunks.append(_make_chunk(chunk_index, page_number, words[:max_words]))
                chunk_index += 1
                words = words[max_words - overlap_words:]

        if words:
            chunks.append(_make_chunk(chunk_index, page_number, words))
            chunk_index += 1

    return chunks


def build_document_chunks(raw: bytes, filename: str) -> list[dict[str, object]]:
    return chunk_pages(extract_pages(raw, filename))


def _make_chunk(chunk_index: int, page_number: int, words: list[str]) -> dict[str, object]:
    content = " ".join(words).strip()
    return {
        "page_number": page_number,
        "chunk_index": chunk_index,
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "metadata": {"token_estimate": len(words)},
    }
