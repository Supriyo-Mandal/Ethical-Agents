from __future__ import annotations

import json
from pathlib import Path

from app.config import KNOWLEDGE_DIR


def load_repository(agent_name: str) -> list[dict[str, object]]:
    repository_path = KNOWLEDGE_DIR / agent_name / "repository.json"
    if not repository_path.exists():
        return []
    return json.loads(repository_path.read_text(encoding="utf-8"))
