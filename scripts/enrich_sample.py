"""Enrichment pipeline — run on resolved persons to fetch ORCID/OpenAlex data."""
import psycopg
from pathlib import Path

from syggramma.adapters.openalex import OpenAlexClient
from syggramma.adapters.orcid import OrcidClient
from syggramma.adapters.crossref import CrossrefClient
from syggramma.pipelines.enrich import EnrichmentPipeline


def main():
    conn = psycopg.connect("postgresql://syggramma:syggramma@localhost:5432/syggramma")

    # Get persons that haven't been enriched yet
    rows = conn.execute(
        "SELECT id, display_name, canonical_surname FROM person ORDER BY canonical_surname"
    ).fetchall()
    print(f"Persons total: {len(rows)}")

    # Sample: first 5 with full names (skip single-initial ones)
    sample = [r for r in rows if len(r[1].split()) >= 2 and "." not in r[1]][:5]
    print(f"Sample to enrich (full names): {len(sample)}")

    openalex = OpenAlexClient()
    orcid = OrcidClient()
    crossref = CrossrefClient()

    pipeline = EnrichmentPipeline(
        openalex=openalex,
        orcid=orcid,
        crossref=crossref,
    )

    enriched = 0
    for pid, display_name, surname in sample:
        print(f"\nEnriching: {display_name} ({surname})")
        try:
            profile = pipeline.enrich_by_name(display_name)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        print(f"  ORCID: {profile.orcid or 'none'}")
        print(f"  OpenAlex ID: {profile.openalex_id or 'none'}")
        print(f"  Works count: {profile.works_count}")
        print(f"  Cited by: {profile.cited_by_count}")
        print(f"  Institutions: {[i.get('name', '') for i in profile.institutions[:2]]}")
        print(f"  Topics: {profile.topics[:3]}")

        # Store enrichment data as fact rows (if we had a fact table)
        # For now, just count
        if profile.orcid or profile.openalex_id:
            enriched += 1

        # Rate limit: OpenAlex is 10/sec, but be polite
        import time
        time.sleep(0.5)

    print(f"\nEnriched: {enriched}/{len(sample)}")

    openalex.close()
    orcid.close()
    crossref.close()
    conn.close()


if __name__ == "__main__":
    main()
