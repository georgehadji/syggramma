"""Fast batch import of courses from snapshots."""
import json, psycopg
from pathlib import Path

SNAP_DIR = Path("data/snapshots")
DB = "postgresql://syggramma:syggramma@localhost:5432/syggramma"

def main():
    conn = psycopg.connect(DB)
    
    # Collect all course rows first
    body_files = [
        f for f in SNAP_DIR.rglob("*")
        if f.suffix == '' and f.is_file() and len(f.name) == 64 and len(f.parent.name) == 2
    ]
    print(f"Reading {len(body_files)} snapshots...")
    
    courses: list[tuple] = []
    departments_seen: set[int] = set()
    
    for bf in body_files:
        try:
            data = json.loads(bf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key, items in data.items():
            if not key.isdigit() or not isinstance(items, list):
                continue
            for c in items:
                if not isinstance(c, dict):
                    continue
                eid = c.get("courseId") or c.get("id")
                if not eid:
                    continue
                sid = c.get("secretariatID", 0)
                departments_seen.add(sid)
                courses.append((
                    eid, c.get("title", ""), c.get("code", ""),
                    c.get("year", 2024), c.get("semester", 0),
                    c.get("period", ""), c.get("professor", "") or "",
                    sid,
                ))
    
    print(f"Found {len(courses)} courses across {len(departments_seen)} departments")
    
    # Insert departments
    for sid in departments_seen:
        conn.execute("""
            INSERT INTO department (id, institution_id, eudoxus_academic_id, name, is_live, secretariat_id)
            VALUES (%s, 1, %s, %s, true, %s)
            ON CONFLICT (secretariat_id) DO NOTHING
        """, [sid, sid, f"Secretariat {sid}", sid])
    conn.commit()
    print(f"Departments: {conn.execute('SELECT COUNT(*) FROM department').fetchone()[0]}")
    
    # Batch insert courses
    batch_size = 500
    for i in range(0, len(courses), batch_size):
        batch = courses[i:i+batch_size]
        with conn.cursor() as cur:
            for c in batch:
                cur.execute("""
                    INSERT INTO course (eudoxus_id, title, code, year, semester, period, professor_raw, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (eudoxus_id, year, department_id) DO UPDATE SET
                        title = EXCLUDED.title, professor_raw = EXCLUDED.professor_raw
                """, c)
        conn.commit()
        print(f"  {min(i+batch_size, len(courses))}/{len(courses)} courses")
    
    total = conn.execute("SELECT COUNT(*) FROM course").fetchone()[0]
    print(f"Done! {total} courses in DB")
    conn.close()

if __name__ == "__main__":
    main()
