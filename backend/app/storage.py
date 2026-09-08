from __future__ import annotations

from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .embedding_client import embed_texts, to_pgvector
from .config import DATABASE_URL


def _connect() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)


def save_analysis(document_name: str, result: dict[str, Any]) -> dict[str, Any]:
    analysis_id = str(uuid4())
    stored_result = dict(result)
    chunks = stored_result.pop("_document_chunks", [])
    embeddings = embed_texts([str(chunk["content"]) for chunk in chunks])
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO analyses (id, document_name, result)
            VALUES (%s, %s, %s)
            """,
            (analysis_id, document_name, Jsonb(stored_result)),
        )
        for chunk in chunks:
            chunk_position = int(chunk["chunk_index"])
            embedding = (
                to_pgvector(embeddings[chunk_position])
                if chunk_position < len(embeddings)
                else None
            )
            connection.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, page_number, chunk_index, content, content_hash, metadata, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    str(uuid4()),
                    analysis_id,
                    chunk["page_number"],
                    chunk["chunk_index"],
                    chunk["content"],
                    chunk["content_hash"],
                    Jsonb(chunk["metadata"]),
                    embedding,
                ),
            )
    return {"id": analysis_id, "document_name": document_name, **stored_result}


def load_analysis(analysis_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, document_name, result FROM analyses WHERE id = %s",
            (analysis_id,),
        ).fetchone()
    if row is None:
        return None
    stored_id, document_name, result = row
    return {"id": str(stored_id), "document_name": document_name, **result}


def get_history() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, document_name, result
            FROM analyses
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [
        {"id": str(analysis_id), "document_name": document_name, **result}
        for analysis_id, document_name, result in rows
    ]


def delete_analysis(analysis_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM analyses WHERE id = %s",
            (analysis_id,),
        )
    return cursor.rowcount > 0
