"""create analyses table and enable pgvector

Revision ID: 001_create_analyses
Revises:
Create Date: 2026-09-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_create_analyses"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_name", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analyses_created_at",
        "analyses",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_created_at", table_name="analyses")
    op.drop_table("analyses")
    op.execute("DROP EXTENSION IF EXISTS vector")
