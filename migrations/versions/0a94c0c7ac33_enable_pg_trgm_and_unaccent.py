"""enable_pg_trgm_and_unaccent

Revision ID: 0a94c0c7ac33
Revises: 27ec4cd1b014
Create Date: 2026-07-22 22:50:00.066934
"""
from typing import Collection, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0a94c0c7ac33'
down_revision: str | None = '27ec4cd1b014'
branch_labels: str | Collection[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable extensions (idempotent — IF NOT EXISTS is implicit)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # Note: trigram indexes on person, course, and book tables
    # are deferred to later migrations when those tables exist.


def downgrade() -> None:
    # Extensions are not dropped in downgrade — other tables may depend on them
    pass
