"""Resolve pipeline — normalize professors from courses and create Person records."""
import psycopg

from syggramma.pipelines.normalize import normalize, VERSION


def main():
    conn = psycopg.connect("postgresql://syggramma:syggramma@localhost:5432/syggramma")
    
    rows = conn.execute(
        "SELECT DISTINCT professor_raw FROM course WHERE professor_raw != ''"
    ).fetchall()
    raw_names = [row[0] for row in rows]
    print(f"Unique raw professor strings: {len(raw_names)}")

    persons_created = 0
    aliases_created = 0

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

            existing = conn.execute(
                "SELECT id FROM person WHERE canonical_surname = %s",
                [surname],
            ).fetchone()

            if existing is None:
                pid = conn.execute(
                    """INSERT INTO person (display_name, canonical_surname, canonical_given)
                       VALUES (%s, %s, %s) RETURNING id""",
                    [part, surname, norm],
                ).fetchone()[0]
                persons_created += 1
            else:
                pid = existing[0]
                conn.execute(
                    """INSERT INTO person_alias (person_id, raw_text, normalized, source_kind, normalizer_version)
                       VALUES (%s, %s, %s, 'eudoxus_course', %s) ON CONFLICT DO NOTHING""",
                    [pid, part, norm, VERSION],
                )
                aliases_created += 1

    conn.commit()
    print(f"Persons created: {persons_created}")
    print(f"Aliases created: {aliases_created}")
    print(f"Person rows: {conn.execute('SELECT COUNT(*) FROM person').fetchone()[0]}")
    print(f"Alias rows: {conn.execute('SELECT COUNT(*) FROM person_alias').fetchone()[0]}")

    print("\nSample persons:")
    for r in conn.execute(
        "SELECT display_name, canonical_surname, canonical_given FROM person ORDER BY canonical_surname LIMIT 15"
    ).fetchall():
        print(f"  {r[1]:>25} | {r[0]:.40} | {r[2]}")

    conn.close()


if __name__ == "__main__":
    main()
