"""l1_ingestion_schema

Revision ID: 27ec4cd1b014
Revises: 74a35b1aa45f
Create Date: 2026-07-22 22:28:47.461977
"""
from typing import Collection, Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '27ec4cd1b014'
down_revision: str | None = '74a35b1aa45f'
branch_labels: str | Collection[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── L0 / Snapshot ────────────────────────────────────────────────────
    op.create_table(
        "snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=True),
        sa.Column("body_path", sa.Text(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("encoding", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_snapshot_sha256", "snapshot", ["sha256"])

    # ── Harvest ledger ───────────────────────────────────────────────────
    op.create_table(
        "harvest_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("code_version", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "harvest_unit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("harvest_run.id"), nullable=False),
        sa.Column("secretariat_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshot.id"), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── L1 / Catalogue ───────────────────────────────────────────────────
    op.create_table(
        "institution",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eudoxus_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ror_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eudoxus_id"),
    )

    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institution.id"), nullable=False),
        sa.Column("eudoxus_academic_id", sa.Integer(), nullable=False),
        sa.Column("secretariat_id", sa.Integer(), nullable=True),
        sa.Column("school", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secretariat_id"),
    )

    op.create_table(
        "course",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eudoxus_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("period", sa.String(32), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("professor_raw", sa.Text(), nullable=False, server_default=""),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshot.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_course_department_year", "course", ["department_id", "year"])

    op.create_table(
        "book",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eudoxus_id", sa.Integer(), nullable=True),
        sa.Column("isbn", sa.String(32), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("authors_raw", sa.Text(), nullable=False, server_default=""),
        sa.Column("edition", sa.String(64), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("publisher_id", sa.String(64), nullable=True),
        sa.Column("publisher_name", sa.Text(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("link_to_publisher", sa.Text(), nullable=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("snapshot.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eudoxus_id"),
    )
    op.create_index("ix_book_isbn", "book", ["isbn"])

    op.create_table(
        "distribution",
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("book_id", sa.Integer(), sa.ForeignKey("book.id"), nullable=False),
        sa.Column("bookgroup_id", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("course_id", "book_id", "year"),
    )


def downgrade() -> None:
    op.drop_table("distribution")
    op.drop_table("book")
    op.drop_table("course")
    op.drop_table("department")
    op.drop_table("institution")
    op.drop_table("harvest_unit")
    op.drop_table("harvest_run")
    op.drop_table("snapshot")
