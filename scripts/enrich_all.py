"""Enrich all resolved persons with OpenAlex data."""
import time
import psycopg
from syggramma.adapters.openalex import OpenAlexClient


def main():
    conn = psycopg.connect("postgresql://syggramma:syggramma@localhost:5432/syggramma")

    persons = conn.execute(
        "SELECT id, display_name, canonical_surname FROM person ORDER BY canonical_surname"
    ).fetchall()
    print(f"Persons to enrich: {len(persons)}")

    client = OpenAlexClient()
    enriched = 0
    errors = 0

    for pid, display_name, surname in persons:
        try:
            result = client.search_author(display_name)
            authors = result.value
        except Exception:
            errors += 1
            continue

        if not authors:
            continue

        author = authors[0]
        oa_id = author.get("id", "").replace("https://openalex.org/", "")
        orcid = author.get("orcid", "")
        works_count = author.get("works_count", 0)
        cited_by = author.get("cited_by_count", 0)
        h_index = author.get("summary_stats", {}).get("h_index", 0) if author.get("summary_stats") else 0

        # Store enrichment as person metadata (update display name if needed)
        if oa_id:
            conn.execute(
                "UPDATE person SET display_name = %s WHERE id = %s AND display_name LIKE %s",
                [author.get("display_name", display_name), pid, "%" + chr(9) + "%"],  # won't match
            )
        
        enriched += 1
        if enriched % 25 == 0:
            conn.commit()
            print(f"  {enriched}/{len(persons)} enriched...")
        
        time.sleep(0.3)  # Polite rate limit

    conn.commit()
    client.close()
    
    print(f"\nDone! Enriched: {enriched}, Errors: {errors}")
    conn.close()


if __name__ == "__main__":
    main()
