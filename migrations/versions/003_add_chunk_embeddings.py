"""add embeddings to document chunks

Revision ID: 003_add_chunk_embeddings
Revises: 002_create_document_chunks
Create Date: 2026-09-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003_add_chunk_embeddings"
down_revision: Union[str, Sequence[str], None] = "002_create_document_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(768)")
    op.execute(
        """
        CREATE INDEX ix_document_chunks_embedding_hnsw
        ON document_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_document_chunks_embedding_hnsw")
    op.execute("ALTER TABLE document_chunks DROP COLUMN embedding")
