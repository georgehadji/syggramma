"""FastAPI application — review queues and API routes.

ARCHITECTURE.md §6.5: Review UI via HTMX + Jinja2, server-rendered.
Uses sync psycopg for DB access — works on all platforms without event loop issues.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row

from syggramma import __version__
from syggramma.config import settings

app = FastAPI(
    title="Syggramma",
    description="Market-intelligence and author-outreach system",
    version=__version__,
)

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

if (HERE / "static").exists():
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


def _get_conn() -> psycopg.Connection[dict[str, Any]]:
    """Get a sync psycopg connection for the API layer."""
    return psycopg.connect(
        settings.db_url.replace("+psycopg", ""),
        row_factory=dict_row,
    )


def _render(name: str, request: Request, **context: Any) -> HTMLResponse:
    tmpl = templates.get_template(name)
    body = tmpl.render(request=request, **context)
    return HTMLResponse(body)


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/")
async def dashboard(request: Request) -> HTMLResponse:
    with _get_conn() as conn:
        # Match review count: persons with at least one alias
        row = conn.execute("""
            SELECT COUNT(*) AS n FROM (
                SELECT p.id FROM person p
                JOIN person_alias pa ON pa.person_id = p.id
                GROUP BY p.id HAVING COUNT(pa.id) > 0
            ) sub
        """).fetchone()
        match_count: int = row["n"] if row else 0

        row = conn.execute("""
            SELECT COUNT(*) AS n FROM (
                SELECT p.id FROM person p
                JOIN person_alias pa ON pa.person_id = p.id
                GROUP BY p.id HAVING COUNT(pa.id) > 1
            ) sub
        """).fetchone()
        merge_count: int = row["n"] if row else 0

        stats = {}
        for tbl in ["person", "course", "book"]:
            r = conn.execute(f"SELECT COUNT(*) AS n FROM {tbl}").fetchone()
            stats[tbl] = r["n"] if r else 0

    return _render("dashboard.html", request, queues={
        "match_review": match_count,
        "person_merge": merge_count,
        "stats": stats,
    })


# ── Match review queue ─────────────────────────────────────────────────────

@app.get("/review/matches")
async def match_review_queue(request: Request) -> HTMLResponse:
    with _get_conn() as conn:
        matches = conn.execute("""
            SELECT p.id, p.display_name, p.canonical_surname,
                   COUNT(pa.id) AS alias_count
            FROM person p
            LEFT JOIN person_alias pa ON pa.person_id = p.id
            GROUP BY p.id, p.display_name, p.canonical_surname
            HAVING COUNT(pa.id) > 0
            ORDER BY alias_count DESC
            LIMIT 100
        """).fetchall()
    return _render("match_review.html", request, matches=matches)


@app.get("/review/matches/{match_id}")
async def match_detail(request: Request, match_id: int) -> HTMLResponse:
    with _get_conn() as conn:
        person = conn.execute(
            "SELECT * FROM person WHERE id = %s", [match_id],
        ).fetchone()
        aliases = conn.execute(
            "SELECT * FROM person_alias WHERE person_id = %s", [match_id],
        ).fetchall()
    return _render("match_detail.html", request, match=person or {}, aliases=aliases)


@app.post("/review/matches/{match_id}/approve")
async def approve_match(match_id: int, reviewer_id: str = "") -> dict[str, str]:
    with _get_conn() as conn:
        rid = int(reviewer_id) if reviewer_id.isdigit() else None
        conn.execute(
            "INSERT INTO review (subject_type, subject_id, verdict, reviewer_id) "
            "VALUES ('match', %s, 'accepted', %s)",
            [match_id, rid],
        )
        conn.commit()
    return {"status": "ok", "match_id": str(match_id)}


@app.post("/review/matches/{match_id}/reject")
async def reject_match(match_id: int, reviewer_id: str = "") -> dict[str, str]:
    with _get_conn() as conn:
        rid = int(reviewer_id) if reviewer_id.isdigit() else None
        conn.execute(
            "INSERT INTO review (subject_type, subject_id, verdict, reviewer_id) "
            "VALUES ('match', %s, 'rejected', %s)",
            [match_id, rid],
        )
        conn.commit()
    return {"status": "ok", "match_id": str(match_id)}


# ── Person merge queue ─────────────────────────────────────────────────────

@app.get("/review/merges")
async def person_merge_queue(request: Request) -> HTMLResponse:
    with _get_conn() as conn:
        merges = conn.execute("""
            SELECT p.id, p.display_name, p.canonical_surname,
                   p.canonical_given, COUNT(pa.id) AS alias_count
            FROM person p
            LEFT JOIN person_alias pa ON pa.person_id = p.id
            GROUP BY p.id
            HAVING COUNT(pa.id) > 1
            ORDER BY alias_count DESC
            LIMIT 50
        """).fetchall()
    return _render("person_merge.html", request, merges=merges)


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
