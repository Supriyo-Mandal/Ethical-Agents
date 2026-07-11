from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request


def _find_config_path() -> Path | None:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[3] / "config.json",
        current.parents[2] / "config.json",
        current.parents[1] / "config.json",
        current.parents[0] / "config.json",
        current.parents[0].parent / "config.json",
        current.parents[0].parent.parent / "config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_fireworks_api_key() -> str:
    env_key = os.getenv("FIREWORKS_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    if env_key:
        return env_key

    config_path = _find_config_path()
    if not config_path:
        return ""

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    for key in ("api_key", "FIREWORKS_API_KEY", "fireworks_api_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def build_fireworks_payload(system_prompt: str, user_content: str) -> dict[str, Any]:
    return {
        "model": "accounts/fireworks/models/gpt-oss-120b",
        "max_tokens": 16384,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }


def call_fireworks(system_prompt: str, user_content: str) -> dict[str, Any] | None:
    api_key = load_fireworks_api_key()
    if not api_key:
        return None

    payload = build_fireworks_payload(system_prompt, user_content)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = request.Request(
        "https://api.fireworks.ai/inference/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    choices = data.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw_text": content}
