from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request
from typing import Any


@dataclass
class ProviderError(Exception):
    kind: str
    status_code: int | None = None
    retry_after: float | None = None


DEFAULT_BASE_URL = "https://api.openai.com/v1"


def call_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any] | None:
    if not api_key:
        raise ProviderError("authentication", 401)

    payload: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        retry_after = None
        header = exc.headers.get("Retry-After") if exc.headers else None
        if header:
            try:
                retry_after = max(0.0, float(header))
            except ValueError:
                pass
        kind = "quota" if exc.code in {402, 409} else "http"
        raise ProviderError(kind, exc.code, retry_after) from exc
    except TimeoutError as exc:
        raise ProviderError("timeout") from exc
    except (error.URLError, ValueError, json.JSONDecodeError) as exc:
        raise ProviderError("unavailable") from exc

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
