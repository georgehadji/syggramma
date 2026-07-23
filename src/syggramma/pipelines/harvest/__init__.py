"""Harvest pipeline — Eudoxus ingestion orchestration.

Orchestrates fetching the Eudoxus catalogue for a set of years and
departments, storing L0 snapshots, and loading L1 data into the
database via the ledger.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from syggramma.kernel import SnapshotId
from syggramma.ports import CourseCatalogPort, SnapshotStorePort, SuspiciousEmptyResult

# ── Domain types for pipeline state ─────────────────────────────────────────

@dataclass
class InstitutionInfo:
    eudoxus_id: int
    name: str


@dataclass
class DepartmentInfo:
    academic_id: int
    secretariat_id: int | None
    institution_id: int
    school: str | None
    name: str
    is_live: bool


@dataclass
class HarvestUnitResult:
    secretariat_id: int
    year: int
    status: str  # completed | failed | suspicious_skip
    course_count: int = 0
    book_count: int = 0
    error: str | None = None
    snapshot_ids: list[SnapshotId] = field(default_factory=list)


@dataclass
class HarvestRunResult:
    year: int
    status: str  # completed | failed
    units: list[HarvestUnitResult] = field(default_factory=list)
    total_courses: int = 0
    total_books: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ── Pipeline ────────────────────────────────────────────────────────────────

def _secretariat_id_from_academics(
    academic_id: int,
    academic_secretariats: dict[str, Any],
) -> int | None:
    """Resolve the secretariatId trap documented in EUDOXUS-API.md.

    ``secretariatId`` is NOT ``institutionAcademics[].id`` — it is
    ``academicSecretariats[<academicId>].id``.
    """
    key = str(academic_id)
    entry = academic_secretariats.get(key)
    if entry is None:
        return None
    id_val: object = entry.get("id")
    return id_val if isinstance(id_val, int) else None


class HarvestPipeline:
    """Orchestrates a full harvest for one or more years."""

    def __init__(
        self,
        eudoxus: CourseCatalogPort,
        snapshot_store: SnapshotStorePort,
        max_concurrent_units: int = 4,
    ) -> None:
        self._eudoxus = eudoxus
        self._snapshot_store = snapshot_store
        self._semaphore = asyncio.Semaphore(max_concurrent_units)

    async def run(
        self,
        years: list[int],
        pilot_secretariat_ids: list[int] | None = None,
    ) -> list[HarvestRunResult]:
        """Run a full harvest for the given years.

        If ``pilot_secretariat_ids`` is set, only harvest those departments.
        """
        # Fetch institution tree once
        academics_data = await self._eudoxus.fetch_institution_academics()
        raw: Any = academics_data.value
        institutions_raw: list[dict[str, object]] = raw["institutions"]
        institution_academics: dict[str, list[dict[str, object]]] = raw["institutionAcademics"]
        academic_secretariats: dict[str, dict[str, object]] = raw["academicSecretariats"]

        # Build department info from the tree
        all_institutions = self._parse_institutions(institutions_raw)
        all_departments = self._parse_departments(
            all_institutions, institution_academics, academic_secretariats,
        )

        # Filter to pilot if needed
        if pilot_secretariat_ids is not None:
            pilot_set = set(pilot_secretariat_ids)
            all_departments = [d for d in all_departments if d.secretariat_id in pilot_set]
            if not all_departments:
                logging.warning("No departments matched pilot ids %s", pilot_secretariat_ids)

        results: list[HarvestRunResult] = []
        for year in sorted(years):
            result = await self._harvest_year(year, all_departments)
            results.append(result)

        return results

    async def _harvest_year(
        self,
        year: int,
        departments: list[DepartmentInfo],
    ) -> HarvestRunResult:
        """Harvest all departments for a single year."""
        run_result = HarvestRunResult(
            year=year,
            status="running",
            started_at=datetime.now(UTC),
        )

        # Mark which departments had data in a prior year (for empty-result guard)
        # In a full run, this would query the DB.  For now, assume all live
        # departments had data.
        for d in departments:
            if d.secretariat_id and d.is_live:
                self._eudoxus.mark_prior_year_data(d.secretariat_id, True)

        # Harvest all units concurrently
        tasks = [
            self._harvest_unit(d, year)
            for d in departments
            if d.secretariat_id is not None and d.is_live
        ]

        unit_results = await asyncio.gather(*tasks, return_exceptions=True)

        for unit_result in unit_results:
            if isinstance(unit_result, BaseException):
                run_result.units.append(
                    HarvestUnitResult(
                        secretariat_id=0,
                        year=year,
                        status="failed",
                        error=str(unit_result),
                    ),
                )
            else:
                run_result.units.append(unit_result)
                run_result.total_courses += unit_result.course_count
                run_result.total_books += unit_result.book_count

        run_result.finished_at = datetime.now(UTC)
        run_result.status = "completed"
        return run_result

    async def _harvest_unit(
        self,
        dept: DepartmentInfo,
        year: int,
    ) -> HarvestUnitResult:
        """Harvest a single department-year unit of work."""
        sid = dept.secretariat_id
        assert sid is not None

        async with self._semaphore:
            unit = HarvestUnitResult(secretariat_id=sid, year=year, status="running")

            try:
                # Fetch courses for this department-year
                courses_data = await self._eudoxus.fetch_courses(sid, year)

                # Store snapshot
                body = json.dumps(courses_data.value, ensure_ascii=False, default=str).encode("utf-8")
                raw = self._snapshot_store.store(
                    url=f"get-semesters-courses?sId={sid}&y={year}",
                    body=body,
                )
                unit.snapshot_ids.append(raw.snapshot_id)

                # Count courses
                courses_seen: set[int] = set()
                for semester_courses in courses_data.value.values():
                    for course in semester_courses:
                        cid: object = course.get("id")
                        if isinstance(cid, int):
                            courses_seen.add(cid)

                unit.course_count = len(courses_seen)
                unit.status = "completed"

            except SuspiciousEmptyResult:
                unit.status = "suspicious_skip"
                unit.error = "Empty result for department with prior-year data"
            except Exception as e:
                unit.status = "failed"
                unit.error = str(e)

            return unit

    # ── Parser helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_institutions(raw: list[dict[str, object]]) -> dict[int, InstitutionInfo]:
        """Parse deduplicated institutions from the raw API response."""
        seen: dict[int, InstitutionInfo] = {}
        for entry in raw:
            eid_obj: object = entry["id"]
            name_obj: object = entry["name"]
            if isinstance(eid_obj, int) and isinstance(name_obj, str):
                if eid_obj not in seen:
                    seen[eid_obj] = InstitutionInfo(eudoxus_id=eid_obj, name=name_obj)
        return seen

    @staticmethod
    def _parse_departments(
        institutions: dict[int, InstitutionInfo],
        institution_academics: dict[str, list[dict[str, object]]],
        academic_secretariats: dict[str, dict[str, object]],
    ) -> list[DepartmentInfo]:
        """Parse department records from the institution-academics tree."""
        departments: list[DepartmentInfo] = []

        for inst_id_str, academics in institution_academics.items():
            inst_id = int(inst_id_str)
            if inst_id not in institutions:
                continue

            for ac in academics:
                academic_id: object = ac["id"]
                if not isinstance(academic_id, int):
                    continue
                secretariat_id = _secretariat_id_from_academics(
                    academic_id, academic_secretariats,
                )
                name_obj: object = ac.get("department", "") or ""
                d_name: str = name_obj if isinstance(name_obj, str) else ""
                school_obj: object = ac.get("school")
                d_school: str | None = school_obj if isinstance(school_obj, str) else None
                is_live = not any(
                    marker in d_name
                    for marker in ["(ΚΑΤΑΡΓΗΘΗΚΕ", "(ΜΕΤΑΦΕΡΘΗΚΕ", "(Συγχωνεύτηκε"]
                )

                departments.append(
                    DepartmentInfo(
                        academic_id=academic_id,
                        secretariat_id=secretariat_id,
                        institution_id=inst_id,
                        school=d_school,
                        name=d_name,
                        is_live=is_live,
                    ),
                )

        return departments
