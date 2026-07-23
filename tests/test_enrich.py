"""Tests for the enrichment adapters and pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from syggramma.pipelines.enrich import EnrichedProfile, _provenance, EnrichmentPipeline
from syggramma.domain import Provenance


class TestProvenance:
    def test_provenance_created(self) -> None:
        now = datetime.now(timezone.utc)
        p = _provenance("https://example.com", "test.method:v1", now)
        assert p.source_url == "https://example.com"
        assert p.method == "test.method:v1"
        assert p.fetched_at == now


class TestEnrichedProfile:
    def test_empty_profile(self) -> None:
        p = EnrichedProfile()
        assert p.openalex_id == ""
        assert p.field_sources == {}

    def test_profile_with_data(self) -> None:
        p = EnrichedProfile(
            openalex_id="A000000001",
            orcid="0000-0001-2345-6789",
            topics=["Machine Learning", "NLP"],
        )
        assert p.openalex_id == "A000000001"
        assert len(p.topics) == 2


class TestOpenAlexClient:
    """Tests that verify extract_profile works on known data shapes."""

    def test_extract_profile_with_full_data(self) -> None:
        from syggramma.adapters.openalex import OpenAlexClient
        client = OpenAlexClient()
        sample = {
            "id": "https://openalex.org/A000000001",
            "display_name": "Test Author",
            "orcid": "0000-0001-2345-6789",
            "homepage_url": ["https://example.com"],
            "concepts": [
                {"display_name": "Computer Science", "score": 0.9},
                {"display_name": "Machine Learning", "score": 0.8},
            ],
            "last_known_institutions": [
                {"display_name": "University of Test", "ror": "https://ror.org/01234567"},
            ],
            "works_count": 42,
            "cited_by_count": 100,
        }
        extracted = client.extract_profile(sample)
        assert extracted["openalex_id"] == "A000000001"
        assert extracted["display_name"] == "Test Author"
        assert extracted["orcid"] == "0000-0001-2345-6789"
        assert extracted["homepage"] == "https://example.com"
        assert "Computer Science" in extracted["topics"]
        assert extracted["works_count"] == 42
        client.close()

    def test_extract_profile_empty(self) -> None:
        from syggramma.adapters.openalex import OpenAlexClient
        client = OpenAlexClient()
        extracted = client.extract_profile({})
        assert extracted["openalex_id"] == ""
        assert extracted["display_name"] == ""
        client.close()


class TestOrcidClient:
    def test_extract_name(self) -> None:
        from syggramma.adapters.orcid import OrcidClient
        client = OrcidClient()
        record = {
            "person": {
                "name": {
                    "given-names": {"value": "John"},
                    "family-name": {"value": "Doe"},
                    "credit-name": {"value": "John Doe"},
                },
            },
        }
        name = client.extract_name(record)
        assert name["given_names"] == "John"
        assert name["family_name"] == "Doe"
        assert name["credit_name"] == "John Doe"
        client.close()

    def test_extract_external_ids(self) -> None:
        from syggramma.adapters.orcid import OrcidClient
        client = OrcidClient()
        record = {
            "person": {
                "external-identifiers": {
                    "external-identifier": [
                        {
                            "external-id-type": "Scopus Author ID",
                            "external-id-value": "12345678",
                            "external-id-url": {"value": "https://scopus.com/12345678"},
                        },
                    ],
                },
            },
        }
        ids = client.extract_external_ids(record)
        assert len(ids) == 1
        assert ids[0]["type"] == "Scopus Author ID"
        assert ids[0]["value"] == "12345678"
        client.close()


class TestCrossrefClient:
    def test_extract_publication(self) -> None:
        from syggramma.adapters.crossref import CrossrefClient
        client = CrossrefClient()
        work = {
            "DOI": "10.1000/test",
            "title": ["Test Publication"],
            "container-title": ["Test Journal"],
            "publisher": "Test Publisher",
            "type": "journal-article",
            "published-print": {"date-parts": [[2024]]},
            "author": [
                {"given": "John", "family": "Doe", "ORCID": "http://orcid.org/0000-0001-2345-6789"},
            ],
        }
        pub = client.extract_publication(work)
        assert pub["doi"] == "10.1000/test"
        assert pub["title"] == "Test Publication"
        assert pub["authors"][0]["given"] == "John"
        assert pub["authors"][0]["orcid"] == "0000-0001-2345-6789"
        client.close()
