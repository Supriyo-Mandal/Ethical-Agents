from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import KNOWLEDGE_DIR


def _knowledge_path(agent_name: str) -> Path:
    return KNOWLEDGE_DIR / agent_name / "repository.json"


def _prompt_path(agent_name: str) -> Path:
    return KNOWLEDGE_DIR / agent_name / "prompt.txt"


def load_repository(agent_name: str) -> list[dict[str, Any]]:
    repository_path = _knowledge_path(agent_name)
    if not repository_path.exists():
        return []
    return json.loads(repository_path.read_text(encoding="utf-8"))


def load_prompt(agent_name: str) -> str:
    prompt_path = _prompt_path(agent_name)
    if not prompt_path.exists():
        return (
            f"You are a {agent_name} risk specialist. Review the document for reusable {agent_name} concerns."
        )
    return prompt_path.read_text(encoding="utf-8").strip()


def append_new_fields(agent_name: str, new_fields: list[dict[str, Any]]) -> None:
    """Persist only high-confidence, reusable proposed fields into the repository."""
    repository_path = _knowledge_path(agent_name)
    if not repository_path.exists():
        return None

    repository = json.loads(repository_path.read_text(encoding="utf-8"))
    existing_names = {
        str(entry.get("field_name", "")).strip().lower()
        for entry in repository
        if str(entry.get("field_name", "")).strip()
    }

    accepted = []
    for field in new_fields:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("field_name", "")).strip()
        description = str(field.get("description") or "").strip()
        reason = str(field.get("reason") or "").strip()
        if not field_name or field_name.lower() in existing_names:
            continue
        if len(field_name.split()) > 6:
            continue
        if not description or not reason:
            continue
        accepted.append(
            {
                "field_id": _next_field_id(repository, agent_name),
                "field_name": field_name,
                "description": description,
                "reason": reason,
                "examples": field.get("examples") or [],
                "version": 1,
            }
        )
        existing_names.add(field_name.lower())

    if not accepted:
        return None

    repository.extend(accepted)
    repository_path.write_text(json.dumps(repository, indent=2), encoding="utf-8")
    return None


def _next_field_id(repository: list[dict[str, Any]], agent_name: str) -> str:
    prefix = agent_name.upper()[:3]
    numbers = []
    for entry in repository:
        field_id = str(entry.get("field_id", ""))
        match = re.search(r"(\d+)$", field_id)
        if match:
            numbers.append(int(match.group(1)))
    next_number = max(numbers, default=0) + 1
    return f"{prefix}_{next_number:03d}"
