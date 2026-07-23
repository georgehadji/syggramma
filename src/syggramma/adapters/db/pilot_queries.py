"""Pilot-corpus queries for Milestone 2.

These are the SQL queries that answer "every course, book, publisher, professor"
for the pilot dataset — exactly what Milestone 2 requires.
"""

# ── Pilot corpus queries ────────────────────────────────────────────────────

# All institutions in the pilot
ALL_INSTITUTIONS = """
SELECT id, eudoxus_id, name, ror_id
FROM institution
ORDER BY name;
"""

# All departments in the pilot
ALL_DEPARTMENTS = """
SELECT d.id, d.name, d.school, d.secretariat_id, d.is_live,
       i.name AS institution_name
FROM department d
JOIN institution i ON i.id = d.institution_id
ORDER BY i.name, d.name;
"""

# All courses in the pilot dataset (one row per course-year)
ALL_COURSES = """
SELECT c.id AS course_id, c.eudoxus_id, c.title, c.code, c.year,
       c.semester, c.period, c.professor_raw,
       d.name AS department_name,
       i.name AS institution_name
FROM course c
JOIN department d ON d.id = c.department_id
JOIN institution i ON i.id = d.institution_id
ORDER BY i.name, d.name, c.year, c.code;
"""

# All books referenced in the pilot
ALL_BOOKS = """
SELECT b.id, b.eudoxus_id, b.isbn, b.title, b.subtitle,
       b.authors_raw, b.edition, b.publication_year,
       b.publisher_id, b.publisher_name
FROM book b
ORDER BY b.publisher_name, b.title;
"""

# All publishers found in the pilot
ALL_PUBLISHERS = """
SELECT b.publisher_id, b.publisher_name,
       COUNT(DISTINCT b.id) AS books,
       COUNT(DISTINCT dist.course_id) AS distributions
FROM book b
LEFT JOIN distribution dist ON dist.book_id = b.id
WHERE b.publisher_id IS NOT NULL
GROUP BY b.publisher_id, b.publisher_name
ORDER BY distributions DESC;
"""

# All professors mentioned in the pilot (raw, not yet resolved)
ALL_PROFESSORS = """
SELECT DISTINCT c.professor_raw
FROM course c
WHERE c.professor_raw != ''
ORDER BY c.professor_raw;
"""

# Courses with their distributed books (the core join)
COURSES_WITH_BOOKS = """
SELECT
    c.id AS course_id,
    c.title AS course_title,
    c.year,
    c.professor_raw,
    b.id AS book_id,
    b.title AS book_title,
    b.isbn,
    b.authors_raw AS book_authors,
    b.publisher_name,
    b.publisher_id,
    d.name AS department_name,
    i.name AS institution_name
FROM course c
JOIN distribution dist ON dist.course_id = c.id
JOIN book b ON b.id = dist.book_id
JOIN department d ON d.id = c.department_id
JOIN institution i ON i.id = d.institution_id
ORDER BY i.name, d.name, c.year, c.code;
"""

# Kyriakidis-specific: courses using Kyriakidis books
KYRIAKIDIS_COURSES = """
SELECT
    c.id AS course_id,
    c.title AS course_title,
    c.year,
    c.professor_raw,
    b.id AS book_id,
    b.title AS book_title,
    b.isbn,
    b.authors_raw AS book_authors,
    d.name AS department_name,
    i.name AS institution_name
FROM course c
JOIN distribution dist ON dist.course_id = c.id
JOIN book b ON b.id = dist.book_id
JOIN department d ON d.id = c.department_id
JOIN institution i ON i.id = d.institution_id
WHERE b.publisher_id = '149848'
ORDER BY i.name, d.name, c.year, c.code;
"""

# Summary statistics for the pilot
PILOT_SUMMARY = """
SELECT
    COUNT(DISTINCT i.id) AS institutions,
    COUNT(DISTINCT d.id) AS departments,
    COUNT(DISTINCT c.id) AS courses,
    COUNT(DISTINCT b.id) AS books,
    COUNT(DISTINCT b.publisher_id) AS publishers,
    COUNT(DISTINCT c.professor_raw) FILTER (WHERE c.professor_raw != '') AS professors_mentioned,
    COUNT(DISTINCT dist.id) AS distributions,
    COUNT(DISTINCT dist.book_id) FILTER (WHERE bk.publisher_id = '149848') AS kyriakidis_books_distributed,
    COUNT(DISTINCT dist.course_id) FILTER (WHERE bk.publisher_id = '149848') AS kyriakidis_course_adoptions
FROM institution i
JOIN department d ON d.institution_id = i.id
JOIN course c ON c.department_id = d.id
JOIN distribution dist ON dist.course_id = c.id
JOIN book b ON b.id = dist.book_id
LEFT JOIN book bk ON bk.id = dist.book_id;
"""

# ── All pilot queries in a dict for easy iteration ─────────────────────────

PILOT_QUERIES = {
    "all_institutions": ALL_INSTITUTIONS,
    "all_departments": ALL_DEPARTMENTS,
    "all_courses": ALL_COURSES,
    "all_books": ALL_BOOKS,
    "all_publishers": ALL_PUBLISHERS,
    "all_professors": ALL_PROFESSORS,
    "courses_with_books": COURSES_WITH_BOOKS,
    "kyriakidis_courses": KYRIAKIDIS_COURSES,
    "pilot_summary": PILOT_SUMMARY,
}
