"""OpenAlex API adapter for author profile enrichment.

ARCHITECTURE.md §6.4: OpenAlex is the primary enrichment source (free, no key,
clean, has affiliations and topics).  Responses are cached by URL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from syggramma.config import settings
from syggramma.kernel import Parsed, SnapshotId


class OpenAlexClient:
    """HTTP client for the OpenAlex API."""

    BASE_URL = "https://api.openalex.org/"

    def __init__(
        self,
        base_url: str = settings.openalex_base_url,
        mailto: str = settings.openalex_mailto,
        max_rps: float = settings.openalex_max_rps,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._mailto = mailto
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            params={"mailto": mailto},
            headers={"User-Agent": f"Syggramma/0.1 (mailto:{mailto})"},
        )

    def search_author(self, display_name: str) -> Parsed[list[dict[str, Any]]]:
        """Search for an author by display name.

        Returns the ``results`` list from the OpenAlex /authors endpoint.
        """
        response = self._client.get(
            "authors",
            params={"search": display_name, "per_page": 5},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return Parsed(
            value=data.get("results", []),
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(timezone.utc),
        )

    def fetch_author_by_id(self, openalex_id: str) -> Parsed[dict[str, Any]]:
        """Fetch an author by their OpenAlex ID (e.g. 'A0000000001')."""
        response = self._client.get(f"authors/{openalex_id}")
        response.raise_for_status()
        return Parsed(
            value=response.json(),
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(timezone.utc),
        )

    def fetch_works(self, author_id: str, per_page: int = 25) -> Parsed[list[dict[str, Any]]]:
        """Fetch works for an author."""
        response = self._client.get(
            "works",
            params={"filter": f"authorships.author.id:{author_id}", "per_page": per_page},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return Parsed(
            value=data.get("results", []),
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(timezone.utc),
        )

    def extract_profile(self, author_data: dict[str, Any]) -> dict[str, Any]:
        """Extract a standardised profile from OpenAlex author data.

        Returns a dict with keys: openalex_id, display_name, orcid,
        homepage, topics, institutions, works_count, cited_by_count.
        """
        return {
            "openalex_id": author_data.get("id", "").replace("https://openalex.org/", ""),
            "display_name": author_data.get("display_name", ""),
            "orcid": author_data.get("orcid", ""),
            "homepage": (author_data.get("homepage_url") or [None])[0],
            "topics": [
                c["display_name"]
                for c in (author_data.get("concepts") or [])[:10]
            ],
            "institutions": [
                {
                    "name": i.get("display_name", ""),
                    "ror": i.get("ror", ""),
                }
                for i in (author_data.get("last_known_institutions") or [])
            ],
            "works_count": author_data.get("works_count", 0),
            "cited_by_count": author_data.get("cited_by_count", 0),
        }

    def close(self) -> None:
        self._client.close()
