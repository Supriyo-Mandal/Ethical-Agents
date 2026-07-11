from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DATA_FILE = DATA_DIR / "documents.json"


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]", encoding="utf-8")


def load_documents() -> List[Dict[str, Any]]:
    ensure_storage()
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_documents(records: List[Dict[str, Any]]) -> None:
    ensure_storage()
    with DATA_FILE.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)


def add_document_record(record: Dict[str, Any]) -> Dict[str, Any]:
    records = load_documents()
    record.setdefault("id", str(uuid4()))
    records.append(record)
    save_documents(records)
    return record


def get_document_summaries() -> List[Dict[str, Any]]:
    return load_documents()
