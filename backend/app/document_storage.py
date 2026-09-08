from __future__ import annotations

import hashlib
from pathlib import Path

import boto3

from .config import (
    OBJECT_STORAGE_ACCESS_KEY,
    OBJECT_STORAGE_BUCKET,
    OBJECT_STORAGE_ENDPOINT,
    OBJECT_STORAGE_REGION,
    OBJECT_STORAGE_SECRET_KEY,
)


def store_document(content: bytes, filename: str, content_type: str = "application/octet-stream") -> str | None:
    if not OBJECT_STORAGE_BUCKET:
        return None

    suffix = Path(filename).suffix.lower()
    digest = hashlib.sha256(content).hexdigest()
    key = f"documents/{digest}{suffix}"
    client = boto3.client(
        "s3",
        endpoint_url=OBJECT_STORAGE_ENDPOINT or None,
        region_name=OBJECT_STORAGE_REGION,
        aws_access_key_id=OBJECT_STORAGE_ACCESS_KEY or None,
        aws_secret_access_key=OBJECT_STORAGE_SECRET_KEY or None,
    )
    client.put_object(
        Bucket=OBJECT_STORAGE_BUCKET,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return key