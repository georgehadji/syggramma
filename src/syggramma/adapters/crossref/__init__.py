"""Crossref API adapter for publication metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from syggramma.config import settings
from syggramma.kernel import Parsed, SnapshotId


class CrossrefClient:
    """HTTP client for the Crossref REST API."""

    BASE_URL = "https://api.crossref.org/"

    def __init__(
        self,
        base_url: str = settings.crossref_base_url,
        max_rps: float = settings.crossref_max_rps,
        user_agent: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": user_agent or "Syggramma/0.1 (mailto:vivlosbooks@gmail.com)",
                "Accept": "application/json",
            },
        )

    def fetch_works_by_doi(self, doi: str) -> Parsed[dict[str, Any]]:
        """Fetch metadata for a specific DOI."""
        response = self._client.get(f"works/{doi}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return Parsed(
            value=data.get("message", {}),
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(timezone.utc),
        )

    def search_by_author(self, author_name: str, rows: int = 10) -> Parsed[list[dict[str, Any]]]:
        """Search for works by author name."""
        response = self._client.get(
            "works",
            params={"query.author": author_name, "rows": rows},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return Parsed(
            value=data.get("message", {}).get("items", []),
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(timezone.utc),
        )

    def extract_publication(self, work: dict[str, Any]) -> dict[str, Any]:
        """Extract a standardised publication record."""
        return {
            "doi": work.get("DOI", ""),
            "title": (work.get("title") or [""])[0],
            "container": (work.get("container-title") or [""])[0],
            "publisher": work.get("publisher", ""),
            "type": work.get("type", ""),
            "published_year": (
                work.get("published-print", {})
                .get("date-parts", [[None]])[0][0]
            ),
            "authors": [
                {
                    "given": a.get("given", ""),
                    "family": a.get("family", ""),
                    "orcid": a.get("ORCID", "").replace("http://orcid.org/", ""),
                }
                for a in (work.get("author") or [])
            ],
        }

    def close(self) -> None:
        self._client.close()
