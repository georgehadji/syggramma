"""baseline

Revision ID: 74a35b1aa45f
Revises: 
Create Date: 2026-07-22 21:36:54.895736
"""
from typing import Collection, Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74a35b1aa45f'
down_revision: str | None = None
branch_labels: str | Collection[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    pass


def downgrade() -> None:
    """Revert the migration."""
    pass
