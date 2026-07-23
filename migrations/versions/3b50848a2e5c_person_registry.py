"""person_registry

Creates person and person_alias tables for entity resolution.

Revision ID: 3b50848a2e5c
Revises: 4398b0abce94
Create Date: 2026-07-22 23:11:41.959427
"""
from typing import Collection, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3b50848a2e5c'
down_revision: str | None = '4398b0abce94'
branch_labels: str | Collection[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_surname", sa.String(256), nullable=True),
        sa.Column("canonical_given", sa.String(256), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "person_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("normalizer_version", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_person_alias_person_id", "person_alias", ["person_id"])

    # Trigram index on normalized for candidate generation
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_person_alias_normalized_trgm
        ON person_alias USING gin (normalized gin_trgm_ops)
    """)


def downgrade() -> None:
    op.drop_index("ix_person_alias_normalized_trgm", table_name="person_alias")
    op.drop_table("person_alias")
    op.drop_table("person")
