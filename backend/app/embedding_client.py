from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from app.services.fireworks_client import load_fireworks_api_key

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5")
EMBEDDING_DIMENSIONS = 768
EMBEDDING_ENDPOINT = "https://api.fireworks.ai/inference/v1/embeddings"


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    api_key = load_fireworks_api_key()
    if not api_key:
        return []

    payload = {
        "model": EMBEDDING_MODEL,
        "input": texts,
        "dimensions": EMBEDDING_DIMENSIONS,
        "normalize": True,
    }
    req = request.Request(
        EMBEDDING_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return []

    rows = data.get("data") or []
    embeddings: list[list[float]] = []
    for row in sorted(rows, key=lambda item: int(item.get("index", 0))):
        vector = row.get("embedding") if isinstance(row, dict) else None
        if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
            return []
        embeddings.append([float(value) for value in vector])
    return embeddings if len(embeddings) == len(texts) else []


def to_pgvector(values: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in values) + "]"
