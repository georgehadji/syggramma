"""Fetch books for all courses from Eudoxus — async version."""
import asyncio, selectors, time
import psycopg
from syggramma.adapters.eudoxus import EudoxusClient


async def fetch_books_for_course(
    client: EudoxusClient,
    course_db_id: int,
    eudoxus_course_id: int,
    year: int,
    sem: asyncio.Semaphore,
) -> tuple[int, int]:
    """Fetch books for one course. Returns (books_added, dists_added)."""
    async with sem:
        try:
            result = await client.fetch_course_books(eudoxus_course_id)
            data = result.value
        except Exception:
            return 0, 0

    books_added = 0
    dists_added = 0
    conn = psycopg.connect("postgresql://syggramma:syggramma@localhost:5432/syggramma")

    # Response: {id, ..., bookgroups: [{books: [{book: {...}}]}]}
    for bg in data.get("bookgroups", []):
        for entry in bg.get("books", []):
            book = entry.get("book", {})
            eid = book.get("id")
            if not eid:
                continue
            r = conn.execute("""
                INSERT INTO book (eudoxus_id, isbn, title, subtitle, authors_raw, edition,
                                  publication_year, publisher_id, publisher_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (eudoxus_id) DO UPDATE SET
                    title = EXCLUDED.title, authors_raw = EXCLUDED.authors_raw,
                    publisher_id = EXCLUDED.publisher_id, publisher_name = EXCLUDED.publisher_name
                RETURNING id
            """, [
                eid, book.get("isbn", "")[:32], book.get("title", ""),
                book.get("subtitle") or None, book.get("authors", ""),
                (book.get("editionNumber") or "")[:64] or None,
                book.get("publicationYear"),
                str(book.get("publisherId", ""))[:64] if book.get("publisherId") else None,
                book.get("publisherName") or None,
            ])
            book_db_id = r.fetchone()[0]
            books_added += 1
            conn.execute("""
                INSERT INTO distribution (course_id, book_id, year)
                VALUES (%s, %s, %s)
                ON CONFLICT (course_id, book_id, year) DO NOTHING
            """, [course_db_id, book_db_id, year])
            dists_added += 1

    conn.commit()
    conn.close()
    return books_added, dists_added


async def main():
    conn = psycopg.connect("postgresql://syggramma:syggramma@localhost:5432/syggramma")
    courses = conn.execute(
        "SELECT id, eudoxus_id, year FROM course WHERE eudoxus_id IS NOT NULL ORDER BY id"
    ).fetchall()
    conn.close()
    print(f"Courses to fetch: {len(courses)}")

    client = EudoxusClient(max_rps=2.0, max_concurrent=2, recaptcha_stop=False)
    sem = asyncio.Semaphore(2)

    tasks = [
        fetch_books_for_course(client, db_id, int(eid), year, sem)
        for db_id, eid, year in courses
    ]

    total_books = 0
    total_dists = 0
    done = 0
    for coro in asyncio.as_completed(tasks):
        b, d = await coro
        total_books += b
        total_dists += d
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(courses)} done, {total_books} books, {total_dists} dists")

    await client.close()

    conn = psycopg.connect("postgresql://syggramma:syggramma@localhost:5432/syggramma")
    print(f"\nBook rows: {conn.execute('SELECT COUNT(*) FROM book').fetchone()[0]}")
    print(f"Distribution rows: {conn.execute('SELECT COUNT(*) FROM distribution').fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
