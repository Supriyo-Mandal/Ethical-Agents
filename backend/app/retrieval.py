from __future__ import annotations

from typing import Any

from .embedding_client import embed_texts, to_pgvector
from .storage import _connect


def retrieve_chunks(
    document_id: str,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 50))
    query_embeddings = embed_texts([query])
    query_vector = to_pgvector(query_embeddings[0]) if query_embeddings else None

    with _connect() as connection:
        if query_vector:
            rows = connection.execute(
                """
                SELECT id, page_number, chunk_index, content, metadata,
                       0.70 * (1 - (embedding <=> %s::vector))
                       + 0.30 * ts_rank_cd(
                           to_tsvector('simple', content),
                           plainto_tsquery('simple', %s)
                       ) AS relevance_score
                FROM document_chunks
                WHERE document_id = %s
                  AND embedding IS NOT NULL
                ORDER BY relevance_score DESC
                LIMIT %s
                """,
                (query_vector, query, document_id, bounded_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, page_number, chunk_index, content, metadata,
                       ts_rank_cd(
                           to_tsvector('simple', content),
                           plainto_tsquery('simple', %s)
                       ) AS relevance_score
                FROM document_chunks
                WHERE document_id = %s
                ORDER BY relevance_score DESC, chunk_index ASC
                LIMIT %s
                """,
                (query, document_id, bounded_limit),
            ).fetchall()

    return [
        {
            "id": str(chunk_id),
            "page_number": page_number,
            "chunk_index": chunk_index,
            "content": content,
            "metadata": metadata,
            "relevance_score": float(relevance_score or 0.0),
        }
        for chunk_id, page_number, chunk_index, content, metadata, relevance_score in rows
    ]
