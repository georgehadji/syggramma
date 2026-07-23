"""Analyze pipeline — market intelligence reporting helpers.

ARCHITECTURE.md §6.5: This module provides helper functions for running
the analysis materialized views and producing reports.  The heavy lifting
is in the SQL views (adapters/db/analysis_views.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Lead:
    """An explainable sales lead with contributing factors."""

    lead_type: str  # friendly_non_author | orphan_title | decaying_title | stale_edition
    name: str
    score: float
    factors: dict[str, float] = field(default_factory=dict)
    details: str = ""


class AnalysisService:
    """Service for running analysis queries against the database.

    In production, these methods execute the materialized views and return results.
    """

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    def get_own_catalogue_coverage(self, publisher_id: str = "149848") -> list[dict[str, Any]]:
        """Get distribution counts per year for own titles."""
        return []  # TODO: query mv_own_catalogue_coverage

    def get_orphan_titles(self) -> list[dict[str, Any]]:
        """Get Kyriakidis titles with zero distributions."""
        return []  # TODO: query mv_orphan_titles

    def get_friendly_non_authors(self) -> list[dict[str, Any]]:
        """Get professors using Kyriakidis books they didn't author."""
        return []  # TODO: query mv_friendly_non_authors

    def get_lead_scoreboard(self) -> list[Lead]:
        """Get the ranked lead scoreboard."""
        return []  # TODO: query mv_lead_score
