"""Resolve pipeline — batch-optimized for 17K+ professors."""
import psycopg
from collections import defaultdict

from syggramma.pipelines.normalize import normalize, VERSION

DB = "postgresql://syggramma:syggramma@localhost:5432/syggramma"

def main():
    conn = psycopg.connect(DB)
    
    # Pull all unique professor_raw values
    rows = conn.execute(
        "SELECT DISTINCT professor_raw FROM course WHERE professor_raw != ''"
    ).fetchall()
    raw_names = [r[0] for r in rows]
    print(f"Unique raw professor strings: {len(raw_names)}")

    # Load all existing surnames into memory
    existing = set()
    for r in conn.execute("SELECT canonical_surname FROM person").fetchall():
        existing.add(r[0])
    print(f"Existing persons: {len(existing)}")

    # First pass: normalize and collect unique surnames
    surname_parts: dict[str, list[tuple[str, str]]] = defaultdict(list)  # surname -> [(raw, norm)]
    
    for raw in raw_names:
        parts = [p.strip() for p in raw.split(",")]
        for part in parts:
            if not part or len(part) < 2:
                continue
            norm = normalize(part)
            if not norm:
                continue
            tokens = norm.split()
            if not tokens:
                continue
            surname = tokens[-1]
            surname_parts[surname].append((part, norm))

    print(f"Unique surnames found: {len(surname_parts)}")

    # Batch insert new persons
    new_persons = 0
    new_aliases = 0
    
    with conn.cursor() as cur:
        for surname, variants in surname_parts.items():
            if surname in existing:
                # Add aliases for existing person
                pid = conn.execute(
                    "SELECT id FROM person WHERE canonical_surname = %s", [surname]
                ).fetchone()[0]
                for raw, norm in variants:
                    cur.execute("""
                        INSERT INTO person_alias (person_id, raw_text, normalized, source_kind, normalizer_version)
                        VALUES (%s, %s, %s, 'eudoxus_course', %s)
                        ON CONFLICT DO NOTHING
                    """, [pid, raw, norm, VERSION])
                    new_aliases += 1
            else:
                # Create new person (use first variant as display_name)
                raw, norm = variants[0]
                pid = cur.execute("""
                    INSERT INTO person (display_name, canonical_surname, canonical_given)
                    VALUES (%s, %s, %s) RETURNING id
                """, [raw, surname, norm]).fetchone()[0]
                existing.add(surname)
                new_persons += 1
                
                # Add remaining variants as aliases
                for raw2, norm2 in variants[1:]:
                    cur.execute("""
                        INSERT INTO person_alias (person_id, raw_text, normalized, source_kind, normalizer_version)
                        VALUES (%s, %s, %s, 'eudoxus_course', %s)
                        ON CONFLICT DO NOTHING
                    """, [pid, raw2, norm2, VERSION])
                    new_aliases += 1

        conn.commit()
    
    print(f"New persons: {new_persons}")
    print(f"New aliases: {new_aliases}")
    print(f"Total persons: {conn.execute('SELECT COUNT(*) FROM person').fetchone()[0]}")
    print(f"Total aliases: {conn.execute('SELECT COUNT(*) FROM person_alias').fetchone()[0]}")
    
    conn.close()

if __name__ == "__main__":
    main()
