"""SQLAlchemy ORM models for the Syggramma L1 (ingestion) schema.

Mirrors the entity definitions in ``domain/__init__.py`` for persistence.
All tables use UUID primary keys for compatibility with distributed
snapshots and to avoid integer collision across data sources.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── L0 / Snapshot ───────────────────────────────────────────────────────────


class Snapshot(Base):
    __tablename__ = "snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    headers: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    body_path: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ── Harvest ledger ──────────────────────────────────────────────────────────


class HarvestRun(Base):
    __tablename__ = "harvest_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running | completed | failed
    code_version: Mapped[str] = mapped_column(String(64), nullable=False)


class HarvestUnit(Base):
    __tablename__ = "harvest_unit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("harvest_run.id"), nullable=False,
    )
    secretariat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending",
    )  # pending | running | completed | failed | suspicious
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("snapshot.id"), nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run: Mapped[HarvestRun] = relationship(backref="units")


# ── L1 / Catalogue ──────────────────────────────────────────────────────────


class Institution(Base):
    __tablename__ = "institution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eudoxus_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    ror_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    departments: Mapped[list[Department]] = relationship(back_populates="institution")


class Department(Base):
    __tablename__ = "department"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("institution.id"), nullable=False,
    )
    eudoxus_academic_id: Mapped[int] = mapped_column(Integer, nullable=False)
    secretariat_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    school: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    institution: Mapped[Institution] = relationship(back_populates="departments")
    courses: Mapped[list[Course]] = relationship(back_populates="department")


class Course(Base):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eudoxus_id: Mapped[int] = mapped_column(Integer, nullable=False)
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("department.id"), nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    professor_raw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("snapshot.id"), nullable=True,
    )

    department: Mapped[Department] = relationship(back_populates="courses")
    distributions: Mapped[list[Distribution]] = relationship(back_populates="course")


class Book(Base):
    __tablename__ = "book"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eudoxus_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    isbn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors_raw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    edition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publisher_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_to_publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("snapshot.id"), nullable=True,
    )

    distributions: Mapped[list[Distribution]] = relationship(back_populates="book")


class Distribution(Base):
    __tablename__ = "distribution"

    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("course.id"), primary_key=True,
    )
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("book.id"), primary_key=True,
    )
    bookgroup_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)

    course: Mapped[Course] = relationship(back_populates="distributions")
    book: Mapped[Book] = relationship(back_populates="distributions")


# ── Person registry (identity) ────────────────────────────────────────────


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_surname: Mapped[str | None] = mapped_column(String(256), nullable=True)
    canonical_given: Mapped[str | None] = mapped_column(String(256), nullable=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    aliases: Mapped[list[PersonAlias]] = relationship(back_populates="person")


class PersonAlias(Base):
    __tablename__ = "person_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("person.id"), nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    normalizer_version: Mapped[str] = mapped_column(String(64), nullable=False)

    person: Mapped[Person] = relationship(back_populates="aliases")
