"""Analysis SQL views for market intelligence reports.

These views implement the eight deliverables listed in ARCHITECTURE.md §6.5.
They are designed to work against the L1 schema after a harvest run.
"""

# ── 1. Own-catalogue coverage ──────────────────────────────────────────────
#
# All Kyriakidis titles (publisher_id = '149848') with distribution counts
# per year.  Surfaces titles with zero distributions.

OWN_COVERAGE_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_own_catalogue_coverage AS
SELECT
    b.id AS book_id,
    b.title,
    b.isbn,
    b.authors_raw,
    b.publication_year,
    b.edition,
    COALESCE(d.year, y.year) AS year,
    COALESCE(d.distributions, 0) AS distributions,
    COALESCE(d.institutions, 0) AS institutions,
    COALESCE(d.departments, 0) AS departments
FROM book b
CROSS JOIN generate_series(
    (SELECT MIN(year) FROM distribution),
    (SELECT MAX(year) FROM distribution)
) AS y(year)
LEFT JOIN (
    SELECT
        dist.book_id,
        dist.year,
        COUNT(DISTINCT dist.course_id) AS distributions,
        COUNT(DISTINCT inst.id) AS institutions,
        COUNT(DISTINCT dept.id) AS departments
    FROM distribution dist
    JOIN course c ON c.id = dist.course_id
    JOIN department dept ON dept.id = c.department_id
    JOIN institution inst ON inst.id = dept.institution_id
    GROUP BY dist.book_id, dist.year
) d ON d.book_id = b.id AND d.year = y.year
WHERE b.publisher_id = '149848'
ORDER BY b.title, y.year DESC;
"""

# ── 2. Orphan titles → candidate courses ────────────────────────────────────
#
# Kyriakidis titles with zero distributions, matched to courses in cognate
# departments by title keyword overlap.  This is the highest-value lead type.

ORPHAN_TITLES_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_orphan_titles AS
SELECT
    b.id AS book_id,
    b.title AS book_title,
    b.isbn,
    b.authors_raw,
    c.id AS candidate_course_id,
    c.title AS course_title,
    c.year AS course_year,
    dept.name AS department_name,
    inst.name AS institution_name,
    -- Simple keyword overlap score: fraction of book words found in course title
    (
        SELECT COUNT(*)
        FROM unnest(string_to_array(
            lower(regexp_replace(b.title, '[^\\w\\s]', '', 'g')), ' '
        )) AS bw
        WHERE bw IN (
            SELECT unnest(string_to_array(
                lower(regexp_replace(c.title, '[^\\w\\s]', '', 'g')), ' '
            ))
        )
        AND length(bw) > 2
    )::float / GREATEST(
        (SELECT COUNT(*) FROM unnest(string_to_array(
            lower(regexp_replace(b.title, '[^\\w\\s]', '', 'g')), ' '
        )) AS bw2 WHERE length(bw2) > 2),
        1
    ) AS title_similarity
FROM book b
CROSS JOIN course c
JOIN department dept ON dept.id = c.department_id
JOIN institution inst ON inst.id = dept.institution_id
WHERE b.publisher_id = '149848'
  AND NOT EXISTS (
      SELECT 1 FROM distribution d
      WHERE d.book_id = b.id
  )
  AND c.year >= COALESCE(b.publication_year, 2000)
  AND (
      SELECT COUNT(*)
      FROM unnest(string_to_array(lower(regexp_replace(b.title, '[^\\w\\s]', '', 'g')), ' ')) AS bw
      WHERE bw IN (
          SELECT unnest(string_to_array(lower(regexp_replace(c.title, '[^\\w\\s]', '', 'g')), ' '))
      )
      AND length(bw) > 2
  ) >= 1
ORDER BY title_similarity DESC, b.title;
"""

# ── 3. Friendly non-authors ─────────────────────────────────────────────────
#
# Professors distributing a Kyriakidis title of which they are NOT the author.
# This is the warmest outreach list: the professor already chose a Kyriakidis
# book for their course; they are not the author → no conflict of interest.

FRIENDLY_NON_AUTHORS_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_friendly_non_authors AS
SELECT
    c.id AS course_id,
    c.title AS course_title,
    c.professor_raw,
    c.year,
    b.id AS book_id,
    b.title AS book_title,
    b.authors_raw,
    dept.name AS department_name,
    inst.name AS institution_name
FROM course c
JOIN distribution dist ON dist.course_id = c.id
JOIN book b ON b.id = dist.book_id
JOIN department dept ON dept.id = c.department_id
JOIN institution inst ON inst.id = dept.institution_id
WHERE b.publisher_id = '149848'
  AND c.professor_raw != ''
  AND NOT (
      -- Simple author containment check: professor name appears in authors_raw
      -- (case-insensitive, diacritic-aware via unaccent)
      EXISTS (
          SELECT 1
          FROM unnest(string_to_array(lower(b.authors_raw), ',')) AS author
          WHERE strpos(
              lower(unaccent(b.authors_raw)),
              lower(unaccent(c.professor_raw))
          ) > 0
      )
  )
ORDER BY inst.name, dept.name, c.title;
"""

# ── 4. Competitive share ────────────────────────────────────────────────────
#
# Distribution counts by publisher × year.  Shows market share trends.

COMPETITIVE_SHARE_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_competitive_share AS
SELECT
    b.publisher_id,
    b.publisher_name,
    dist.year,
    COUNT(DISTINCT dist.book_id) AS books_distributed,
    COUNT(DISTINCT dist.course_id) AS courses,
    COUNT(DISTINCT dept.id) AS departments,
    COUNT(DISTINCT inst.id) AS institutions
FROM distribution dist
JOIN book b ON b.id = dist.book_id
JOIN course c ON c.id = dist.course_id
JOIN department dept ON dept.id = c.department_id
JOIN institution inst ON inst.id = dept.institution_id
WHERE b.publisher_id IS NOT NULL
GROUP BY b.publisher_id, b.publisher_name, dist.year
ORDER BY b.publisher_name, dist.year DESC;
"""

# ── 5. Decay detection ──────────────────────────────────────────────────────
#
# Titles losing course adoptions year over year.  The author may be
# dissatisfied with their current publisher.

DECAY_DETECTION_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_decay_detection AS
WITH yearly_counts AS (
    SELECT
        b.id AS book_id,
        b.title,
        b.publisher_name,
        dist.year,
        COUNT(DISTINCT dist.course_id) AS adoptions
    FROM distribution dist
    JOIN book b ON b.id = dist.book_id
    GROUP BY b.id, b.title, b.publisher_name, dist.year
),
yearly_change AS (
    SELECT
        book_id,
        title,
        publisher_name,
        year,
        adoptions,
        LAG(adoptions) OVER (PARTITION BY book_id ORDER BY year) AS prev_year_adoptions
    FROM yearly_counts
)
SELECT
    book_id,
    title,
    publisher_name,
    year,
    adoptions,
    prev_year_adoptions,
    (adoptions - prev_year_adoptions) AS change,
    CASE
        WHEN prev_year_adoptions > 0
        THEN ROUND(
            (adoptions - prev_year_adoptions)::numeric / prev_year_adoptions * 100, 1
        )
        ELSE 0
    END AS change_pct
FROM yearly_change
WHERE prev_year_adoptions IS NOT NULL
  AND adoptions < prev_year_adoptions
ORDER BY change ASC, year DESC;
"""

# ── 6. Whitespace ───────────────────────────────────────────────────────────
#
# Subject areas with many courses and no Kyriakidis title.
# Uses a simple department/school → subject mapping since Eudoxus subjects
# are unreliable (the API returns empty arrays for most books).

WHITESPACE_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_whitespace AS
SELECT
    dept.school,
    COUNT(DISTINCT c.id) AS total_courses,
    COUNT(DISTINCT c.id) FILTER (
        WHERE EXISTS (
            SELECT 1 FROM distribution dist
            JOIN book b ON b.id = dist.book_id
            WHERE dist.course_id = c.id
              AND b.publisher_id = '149848'
        )
    ) AS kyriakidis_courses,
    COUNT(DISTINCT dept.id) AS departments,
    COUNT(DISTINCT inst.id) AS institutions
FROM course c
JOIN department dept ON dept.id = c.department_id
JOIN institution inst ON inst.id = dept.institution_id
WHERE dept.school IS NOT NULL
GROUP BY dept.school
HAVING COUNT(DISTINCT c.id) FILTER (
    WHERE EXISTS (
        SELECT 1 FROM distribution dist
        JOIN book b ON b.id = dist.book_id
        WHERE dist.course_id = c.id
          AND b.publisher_id = '149848'
    )
) = 0
ORDER BY total_courses DESC;
"""

# ── 7. Stale editions ───────────────────────────────────────────────────────
#
# Distributed titles with publicationYear older than ~10 years and no later
# edition detected.

STALE_EDITIONS_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_stale_editions AS
SELECT
    b.id AS book_id,
    b.title,
    b.isbn,
    b.authors_raw,
    b.publication_year,
    b.edition,
    b.publisher_name,
    COUNT(DISTINCT dist.course_id) AS current_adoptions,
    COUNT(DISTINCT dept.id) AS departments,
    COUNT(DISTINCT inst.id) AS institutions,
    EXTRACT(YEAR FROM NOW()) - b.publication_year AS years_since_publication
FROM book b
JOIN distribution dist ON dist.book_id = b.id
JOIN course c ON c.id = dist.course_id
JOIN department dept ON dept.id = c.department_id
JOIN institution inst ON inst.id = dept.institution_id
WHERE b.publication_year IS NOT NULL
  AND EXTRACT(YEAR FROM NOW()) - b.publication_year >= 8
  AND NOT EXISTS (
      -- No later edition of the same title detected
      SELECT 1 FROM book b2
      WHERE b2.publisher_id = b.publisher_id
        AND b2.publication_year > b.publication_year
        AND b2.title = b.title
  )
GROUP BY b.id, b.title, b.isbn, b.authors_raw, b.publication_year,
         b.edition, b.publisher_name
ORDER BY years_since_publication DESC;
"""

# ── 8. Lead score ───────────────────────────────────────────────────────────
#
# Weighted, explainable combination of the above.  Each contributing factor
# is stored separately so a salesperson can see *why* a lead is scored high.

LEAD_SCORE_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_lead_score AS
WITH leads AS (
    -- Friendly non-authors: professors using Kyriakidis books they didn't write
    SELECT
        c.id AS course_id,
        c.professor_raw AS lead_name,
        'friendly_non_author' AS lead_type,
        b.id AS book_id,
        b.title AS book_title,
        dept.name AS department_name,
        inst.name AS institution_name,
        100 AS base_score,  -- warmest lead
        1 AS weight_friendly_non_author,
        0 AS weight_orphan,
        0 AS weight_decay,
        0 AS weight_stale
    FROM course c
    JOIN distribution dist ON dist.course_id = c.id
    JOIN book b ON b.id = dist.book_id
    JOIN department dept ON dept.id = c.department_id
    JOIN institution inst ON inst.id = dept.institution_id
    WHERE b.publisher_id = '149848'
      AND c.professor_raw != ''

    UNION ALL

    -- Orphan titles: course with no Kyriakidis distribution but keyword overlap
    SELECT
        c.id AS course_id,
        c.professor_raw AS lead_name,
        'orphan_title' AS lead_type,
        NULL AS book_id,
        NULL AS book_title,
        dept.name AS department_name,
        inst.name AS institution_name,
        60 AS base_score,
        0 AS weight_friendly_non_author,
        1 AS weight_orphan,
        0 AS weight_decay,
        0 AS weight_stale
    FROM course c
    JOIN department dept ON dept.id = c.department_id
    JOIN institution inst ON inst.id = dept.institution_id
    WHERE NOT EXISTS (
        SELECT 1 FROM distribution dist
        JOIN book b ON b.id = dist.book_id AND b.publisher_id = '149848'
        WHERE dist.course_id = c.id
    )

    UNION ALL

    -- Decaying titles: courses where a non-Kyriakidis book lost adoptions
    SELECT
        NULL AS course_id,
        b.publisher_name AS lead_name,
        'decaying_title' AS lead_type,
        b.id AS book_id,
        b.title AS book_title,
        NULL AS department_name,
        NULL AS institution_name,
        40 AS base_score,
        0 AS weight_friendly_non_author,
        0 AS weight_orphan,
        1 AS weight_decay,
        0 AS weight_stale
    FROM mv_decay_detection d
    JOIN book b ON b.id = d.book_id
    WHERE d.year = (SELECT MAX(year) FROM mv_decay_detection)

    UNION ALL

    -- Stale editions: old books still being adopted
    SELECT
        NULL AS course_id,
        NULL AS lead_name,
        'stale_edition' AS lead_type,
        book_id,
        title AS book_title,
        NULL AS department_name,
        NULL AS institution_name,
        20 AS base_score,
        0 AS weight_friendly_non_author,
        0 AS weight_orphan,
        0 AS weight_decay,
        1 AS weight_stale
    FROM mv_stale_editions
)
SELECT
    *,
    base_score
    + weight_friendly_non_author * 40
    + weight_orphan * 30
    + weight_decay * 20
    + weight_stale * 10
    AS total_score
FROM leads
ORDER BY total_score DESC, lead_type;
"""

# ── All views in a list for easy iteration ──────────────────────────────────

ALL_ANALYSIS_VIEWS = [
    ("mv_own_catalogue_coverage", OWN_COVERAGE_VIEW),
    ("mv_orphan_titles", ORPHAN_TITLES_VIEW),
    ("mv_friendly_non_authors", FRIENDLY_NON_AUTHORS_VIEW),
    ("mv_competitive_share", COMPETITIVE_SHARE_VIEW),
    ("mv_decay_detection", DECAY_DETECTION_VIEW),
    ("mv_whitespace", WHITESPACE_VIEW),
    ("mv_stale_editions", STALE_EDITIONS_VIEW),
    ("mv_lead_score", LEAD_SCORE_VIEW),
]
