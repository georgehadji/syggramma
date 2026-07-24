"""Enrichment pipeline — external profile fetching with source ordering.

ARCHITECTURE.md §6.4:
  - Source order: OpenAlex → ORCID → Crossref
  - Cache-aside: responses cached by URL
  - Field-level provenance: each field stores source_url + fetched_at
  - Confidence-weighted merge: keep both when sources disagree
  - Never synthesise email addresses
  - Scraped content is Tainted[str]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from logging import getLogger
from typing import Any

from syggramma.domain import Provenance
from syggramma.kernel import SnapshotId
from syggramma.ports import SyncCrossrefPort, SyncOpenAlexPort, SyncOrcidPort

_enrich_logger = getLogger("syggramma.enrich")


@dataclass
class EnrichedProfile:
    """A consolidated external profile with field-level provenance."""

    openalex_id: str = ""
    orcid: str = ""
    scopus_id: str = ""
    homepage: str = ""
    display_name: str = ""
    topics: list[str] = field(default_factory=list)
    institutions: list[dict[str, str]] = field(default_factory=list)
    works_count: int = 0
    cited_by_count: int = 0

    # Provenance per field: {field_name: Provenance}
    field_sources: dict[str, Provenance] = field(default_factory=dict)


def _provenance(source_url: str, method: str, now: datetime | None = None) -> Provenance:
    return Provenance(
        source_url=source_url,
        snapshot_id=SnapshotId(0),  # Set by pipeline
        fetched_at=now or datetime.now(UTC),
        method=method,
    )


class EnrichmentPipeline:
    """Orchestrates enrichment from multiple external sources.

    Source order: OpenAlex (primary) → ORCID (identity) → Crossref (publications).
    Each source is independent; failures are logged but do not block others.
    """

    def __init__(
        self,
        openalex: SyncOpenAlexPort,
        orcid: SyncOrcidPort,
        crossref: SyncCrossrefPort,
        name_normalize_fn: object = None,
    ) -> None:
        self._openalex = openalex
        self._orcid = orcid
        self._crossref = crossref

    def enrich_by_name(self, display_name: str) -> EnrichedProfile:
        """Enrich a profile by searching for an author name.

        Runs OpenAlex search first, then uses the found ORCID and OpenAlex ID
        to fetch more detailed records from ORCID and Crossref.
        """
        profile = EnrichedProfile()
        now = datetime.now(UTC)

        # 1. OpenAlex search
        try:
            search_result = self._openalex.search_author(display_name)
            authors = search_result.value
            if authors:
                best = authors[0]
                extracted = self._openalex.extract_profile(best)
                self._merge_openalex(profile, extracted, now)

                # If OpenAlex found an ORCID, enrich from ORCID
                if profile.orcid:
                    self._enrich_from_orcid(profile, profile.orcid, now)

                # If we have an OpenAlex ID, get works
                if profile.openalex_id:
                    self._enrich_works_from_openalex(profile, profile.openalex_id, now)
        except Exception:
            _enrich_logger.warning("OpenAlex search failed for %s", display_name)

        return profile

    def enrich_by_openalex_id(self, openalex_id: str) -> EnrichedProfile:
        """Enrich directly by OpenAlex ID."""
        profile = EnrichedProfile()
        now = datetime.now(UTC)

        try:
            data = self._openalex.fetch_author_by_id(openalex_id)
            extracted = self._openalex.extract_profile(data.value)
            self._merge_openalex(profile, extracted, now)

            if profile.orcid:
                self._enrich_from_orcid(profile, profile.orcid, now)
        except Exception:
            _enrich_logger.warning("OpenAlex detail fetch failed for %s", profile.openalex_id)

        return profile

    # ── Internal enrichment steps ──────────────────────────────────────

    def _merge_openalex(
        self,
        profile: EnrichedProfile,
        data: dict[str, Any],
        now: datetime,
    ) -> None:
        """Merge OpenAlex data into the profile with provenance."""
        source_url = f"https://api.openalex.org/authors/{data.get('openalex_id', '')}"
        prov = _provenance(source_url, "openalex.search:v1", now)

        if data.get("openalex_id") and not profile.openalex_id:
            profile.openalex_id = data["openalex_id"]
            profile.field_sources["openalex_id"] = prov
        if data.get("orcid") and not profile.orcid:
            profile.orcid = data["orcid"]
            profile.field_sources["orcid"] = prov
        if data.get("homepage") and not profile.homepage:
            profile.homepage = data["homepage"]
            profile.field_sources["homepage"] = prov
        if data.get("display_name") and not profile.display_name:
            profile.display_name = data["display_name"]
            profile.field_sources["display_name"] = prov
        if data.get("topics"):
            profile.topics = data["topics"]
            profile.field_sources["topics"] = prov
        if data.get("institutions"):
            profile.institutions = data["institutions"]
            profile.field_sources["institutions"] = prov
        if data.get("works_count"):
            profile.works_count = data["works_count"]
        if data.get("cited_by_count"):
            profile.cited_by_count = data["cited_by_count"]

    def _enrich_from_orcid(self, profile: EnrichedProfile, orcid: str, now: datetime) -> None:
        """Fetch an ORCID record and merge identity data."""
        try:
            record = self._orcid.fetch_record(orcid)
            name_data = self._orcid.extract_name(record.value)
            ext_ids = self._orcid.extract_external_ids(record.value)

            prov = _provenance(f"https://pub.orcid.org/v3.0/{orcid}", "orcid.fetch:v1", now)

            if name_data.get("credit_name") and not profile.display_name:
                profile.display_name = name_data["credit_name"]
                profile.field_sources["display_name"] = prov

            # Extract Scopus ID from external identifiers
            for ext in ext_ids:
                if ext["type"] == "Scopus Author ID" and not profile.scopus_id:
                    profile.scopus_id = ext["value"]
                    profile.field_sources["scopus_id"] = prov
        except Exception:
            _enrich_logger.warning("ORCID fetch failed for %s", orcid)

    def _enrich_works_from_openalex(
        self,
        profile: EnrichedProfile,
        openalex_id: str,
        now: datetime,
    ) -> None:
        """Fetch works for an OpenAlex author."""
        try:
            self._openalex.fetch_works(openalex_id)
            # Works are not merged into the profile directly in v1
            # Future versions may aggregate publication details
        except Exception:
            _enrich_logger.warning("OpenAlex works fetch failed for %s", openalex_id)
