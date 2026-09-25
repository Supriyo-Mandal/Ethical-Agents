from __future__ import annotations

import io
import zipfile
from pathlib import Path


SUPPORTED = {"txt", "md", "pdf", "docx", "png", "jpg", "jpeg", "tif", "tiff", "webp"}


def detect_format(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if raw.startswith(b"%PDF"):
        actual = "pdf"
    elif raw.startswith(b"\x89PNG"):
        actual = "png"
    elif raw.startswith(b"\xff\xd8\xff"):
        actual = "jpg"
    elif raw.startswith((b"II*\x00", b"MM\x00*")):
        actual = "tiff"
    elif raw.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = set(archive.namelist())
            actual = "docx" if "[Content_Types].xml" in names and any(name.startswith("word/") for name in names) else suffix
        except zipfile.BadZipFile:
            actual = suffix
    else:
        actual = suffix if suffix in {"txt", "md"} else ""

    if actual not in SUPPORTED:
        raise ValueError("Unsupported or unrecognized file type")
    if suffix and suffix in SUPPORTED and actual not in {suffix, "jpg" if suffix == "jpeg" else suffix}:
        raise ValueError("File extension does not match its contents")
    return actual
