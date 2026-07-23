"""analysis_materialized_views

Creates the 8 materialized views for market-intelligence reports
defined in ARCHITECTURE.md §6.5.

Revision ID: 4398b0abce94
Revises: 0a94c0c7ac33
Create Date: 2026-07-22 22:56:14.119851
"""
from typing import Collection, Sequence

from alembic import op
from syggramma.adapters.db.analysis_views import ALL_ANALYSIS_VIEWS


# revision identifiers, used by Alembic.
revision: str = '4398b0abce94'
down_revision: str | None = '0a94c0c7ac33'
branch_labels: str | Collection[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, sql in ALL_ANALYSIS_VIEWS:
        op.execute(sql)


def downgrade() -> None:
    for name, _sql in reversed(ALL_ANALYSIS_VIEWS):
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {name} CASCADE")
