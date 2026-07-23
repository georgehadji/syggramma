"""ORCID API adapter for researcher identity verification."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from syggramma.config import settings
from syggramma.kernel import Parsed, SnapshotId


class OrcidClient:
    """HTTP client for the ORCID public API."""

    BASE_URL = "https://pub.orcid.org/v3.0/"

    def __init__(
        self,
        base_url: str = settings.orcid_base_url,
        max_rps: float = settings.orcid_max_rps,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Accept": "application/json",
                "User-Agent": "Syggramma/0.1",
            },
        )

    def fetch_record(self, orcid: str) -> Parsed[dict[str, Any]]:
        """Fetch a public ORCID record (requires valid ORCID iD).

        Args:
            orcid: The ORCID iD in format '0000-0001-2345-6789'.

        """
        response = self._client.get(orcid, params={"version": "public"})
        response.raise_for_status()
        return Parsed(
            value=response.json(),
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    def extract_name(self, record: dict[str, Any]) -> dict[str, str]:
        """Extract name components from an ORCID record."""
        name_data = record.get("person", {}).get("name", {})
        return {
            "given_names": name_data.get("given-names", {}).get("value", ""),
            "family_name": name_data.get("family-name", {}).get("value", ""),
            "credit_name": name_data.get("credit-name", {}).get("value", ""),
        }

    def extract_external_ids(self, record: dict[str, Any]) -> list[dict[str, str]]:
        """Extract external identifiers (Scopus ID, ResearcherID, etc.)."""
        ids: list[dict[str, str]] = []
        ext_ids = (
            record.get("person", {})
            .get("external-identifiers", {})
            .get("external-identifier", [])
        )
        for ext in ext_ids:
            ids.append({
                "type": ext.get("external-id-type", ""),
                "value": ext.get("external-id-value", ""),
                "url": ext.get("external-id-url", {}).get("value", ""),
            })
        return ids

    def close(self) -> None:
        self._client.close()
