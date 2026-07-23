"""SQLAlchemy repository implementing DatabasePort.

Uses SQLAlchemy Core for bulk operations (pipelines) and ORM for entity
operations (CRM).  All methods are async; sessions are managed via
context managers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from syggramma.adapters.db.models import Base
from syggramma.config import settings
from syggramma.domain import (
    Book,
    Campaign,
    Contact,
    Course,
    Department,
    Distribution,
    Institution,
    Match,
    Message,
    Person,
    Review,
)
from syggramma.kernel import (
    PersonId,
)


class Repository:
    """SQLAlchemy-based repository implementing DatabasePort.

    Creates its own async engine and session factory based on settings.
    """

    def __init__(self, db_url: str | None = None) -> None:
        url = db_url or settings.db_url
        # Convert psycopg to async + asyncpg for the async driver
        async_url = url.replace("psycopg://", "postgresql+asyncpg://")
        self._engine = create_async_engine(
            async_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

    async def create_all(self) -> None:
        """Create all tables (dev/test only — use Alembic in production)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # ── L1 / Catalogue persistence ──────────────────────────────────────

    async def store_institution(self, institution: Institution) -> Institution:
        async with self._session_factory() as session:
            stmt = text("""
                INSERT INTO institution (eudoxus_id, name, ror_id)
                VALUES (:eid, :name, :ror)
                ON CONFLICT (eudoxus_id) DO UPDATE
                    SET name = EXCLUDED.name, ror_id = EXCLUDED.ror_id
                RETURNING id
            """)
            result = await session.execute(stmt, {
                "eid": institution.eudoxus_id,
                "name": institution.name,
                "ror": institution.ror_id,
            })
            row = result.fetchone()
            if row:
                institution.id = row[0]
            await session.commit()
        return institution

    async def store_department(self, department: Department) -> Department:
        async with self._session_factory() as session:
            stmt = text("""
                INSERT INTO department (institution_id, eudoxus_academic_id,
                                        secretariat_id, school, name, is_live)
                VALUES (:inst_id, :acad_id, :sec_id, :school, :name, :live)
                ON CONFLICT (secretariat_id) DO UPDATE
                    SET school = EXCLUDED.school,
                        name = EXCLUDED.name,
                        is_live = EXCLUDED.is_live
                RETURNING id
            """)
            result = await session.execute(stmt, {
                "inst_id": department.institution_id,
                "acad_id": department.eudoxus_academic_id,
                "sec_id": department.secretariat_id,
                "school": department.school,
                "name": department.name,
                "live": department.is_live,
            })
            row = result.fetchone()
            if row:
                department.id = row[0]
            await session.commit()
        return department

    async def store_course(self, course: Course) -> Course:
        async with self._session_factory() as session:
            stmt = text("""
                INSERT INTO course (eudoxus_id, department_id, year, semester,
                                    period, code, title, professor_raw, snapshot_id)
                VALUES (:eid, :dept_id, :year, :sem, :period, :code, :title,
                        :prof_raw, :snap_id)
                ON CONFLICT (id) DO UPDATE
                    SET title = EXCLUDED.title,
                        professor_raw = EXCLUDED.professor_raw
                RETURNING id
            """)
            result = await session.execute(stmt, {
                "eid": course.eudoxus_id,
                "dept_id": course.department_id,
                "year": course.year,
                "sem": course.semester,
                "period": course.period,
                "code": course.code,
                "title": course.title,
                "prof_raw": course.professor_raw,
                "snap_id": course.snapshot_id,
            })
            row = result.fetchone()
            if row:
                course.id = row[0]
            await session.commit()
        return course

    async def store_book(self, book: Book) -> Book:
        async with self._session_factory() as session:
            stmt = text("""
                INSERT INTO book (eudoxus_id, isbn, title, subtitle, authors_raw,
                                  edition, publication_year, publisher_id,
                                  publisher_name, pages, link_to_publisher, snapshot_id)
                VALUES (:eid, :isbn, :title, :subtitle, :authors,
                        :edition, :pub_year, :pub_id,
                        :pub_name, :pages, :link, :snap_id)
                ON CONFLICT (eudoxus_id) DO UPDATE
                    SET title = EXCLUDED.title,
                        authors_raw = EXCLUDED.authors_raw
                RETURNING id
            """)
            result = await session.execute(stmt, {
                "eid": book.eudoxus_id,
                "isbn": book.isbn,
                "title": book.title,
                "subtitle": book.subtitle,
                "authors": book.authors_raw,
                "edition": book.edition,
                "pub_year": book.publication_year,
                "pub_id": book.publisher_id,
                "pub_name": book.publisher_name,
                "pages": book.pages,
                "link": book.link_to_publisher,
                "snap_id": book.snapshot_id,
            })
            row = result.fetchone()
            if row:
                book.id = row[0]
            await session.commit()
        return book

    async def store_distribution(self, distribution: Distribution) -> None:
        async with self._session_factory() as session:
            stmt = text("""
                INSERT INTO distribution (course_id, book_id, bookgroup_id, year)
                VALUES (:course_id, :book_id, :bg_id, :year)
                ON CONFLICT (course_id, book_id, year) DO NOTHING
            """)
            await session.execute(stmt, {
                "course_id": distribution.course_id,
                "book_id": distribution.book_id,
                "bg_id": distribution.bookgroup_id,
                "year": distribution.year,
            })
            await session.commit()

    # ── Bulk operations ─────────────────────────────────────────────────

    async def execute_many(self, stmt: str, params: list[dict[str, object]]) -> None:
        async with self._session_factory() as session:
            for param in params:
                await session.execute(text(stmt), param)
            await session.commit()

    # ── Queries ─────────────────────────────────────────────────────────

    async def get_institutions(self) -> list[Any]:
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM institution ORDER BY name"),
            )
            return list(result.mappings().all())

    async def get_departments(self, institution_id: int | None = None) -> list[Any]:
        async with self._session_factory() as session:
            if institution_id:
                result = await session.execute(
                    text("SELECT * FROM department WHERE institution_id = :inst_id ORDER BY name"),
                    {"inst_id": institution_id},
                )
            else:
                result = await session.execute(
                    text("SELECT * FROM department ORDER BY name"),
                )
            return list(result.mappings().all())

    async def get_courses(
        self, department_id: int, year: int,
    ) -> list[Any]:
        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT c.* FROM course c
                    WHERE c.department_id = :dept_id AND c.year = :year
                    ORDER BY c.code
                """),
                {"dept_id": department_id, "year": year},
            )
            return list(result.mappings().all())

    async def get_books_by_publisher(self, publisher_id: str) -> list[Any]:
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM book WHERE publisher_id = :pub_id ORDER BY title"),
                {"pub_id": publisher_id},
            )
            return list(result.mappings().all())

    async def get_distributions(
        self, course_id: int | None = None, book_id: int | None = None,
    ) -> list[Any]:
        async with self._session_factory() as session:
            clauses: list[str] = []
            params: dict[str, Any] = {}
            if course_id is not None:
                clauses.append("course_id = :course_id")
                params["course_id"] = course_id
            if book_id is not None:
                clauses.append("book_id = :book_id")
                params["book_id"] = book_id
            where = " AND ".join(clauses) if clauses else "TRUE"
            result = await session.execute(
                text(f"SELECT * FROM distribution WHERE {where} ORDER BY year"),
                params,
            )
            return list(result.mappings().all())

    # ── Entity stubs (Domain CRM entities — full impl in later milestones) ──

    async def store_person(self, person: Person) -> Person:
        return person  # stub

    async def store_match(self, match: Match) -> Match:
        return match  # stub

    async def store_contact(self, contact: Contact) -> Contact:
        return contact  # stub

    async def store_message(self, message: Message) -> Message:
        return message  # stub

    async def store_campaign(self, campaign: Campaign) -> Campaign:
        return campaign  # stub

    async def store_review(self, review: Review) -> Review:
        return review  # stub

    async def get_person_by_id(self, person_id: PersonId) -> Person | None:
        return None  # stub

    async def get_matches_for_review(self, limit: int = 50) -> Sequence[Match]:
        return []  # stub
