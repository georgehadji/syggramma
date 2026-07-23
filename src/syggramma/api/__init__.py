"""FastAPI application — review queues and API routes.

ARCHITECTURE.md §6.5: Review UI via HTMX + Jinja2, server-rendered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from syggramma import __version__

app = FastAPI(
    title="Syggramma",
    description="Market-intelligence and author-outreach system",
    version=__version__,
)

# Templates and static files
HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

if (HERE / "static").exists():
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


def _render(name: str, request: Request, **context: Any) -> Response:
    """Render a Jinja2 template to an HTML response."""
    tmpl = templates.get_template(name)
    body = tmpl.render(request=request, **context)
    return HTMLResponse(body)


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/")
async def dashboard(request: Request) -> Response:
    """Main dashboard — shows queue counts and quick stats."""
    return _render("dashboard.html", request, queues={
        "match_review": 0,
        "person_merge": 0,
    })


# ── Match review queue ─────────────────────────────────────────────────────

@app.get("/review/matches")
async def match_review_queue(request: Request) -> Response:
    """Queue of unresolved matches needing human review."""
    matches: list[dict[str, Any]] = []
    return _render("match_review.html", request, matches=matches)


@app.get("/review/matches/{match_id}")
async def match_detail(request: Request, match_id: int) -> Response:
    """Detail view for a single match with feature vector."""
    match: dict[str, Any] = {}
    return _render("match_detail.html", request, match=match)


@app.post("/review/matches/{match_id}/approve")
async def approve_match(match_id: int, reviewer_id: str) -> dict[str, str]:
    """Approve a match, promoting it to Verified (L4)."""
    return {"status": "ok", "match_id": str(match_id)}


@app.post("/review/matches/{match_id}/reject")
async def reject_match(match_id: int, reviewer_id: str) -> dict[str, str]:
    """Reject a match."""
    return {"status": "ok", "match_id": str(match_id)}


# ── Person merge queue ─────────────────────────────────────────────────────

@app.get("/review/merges")
async def person_merge_queue(request: Request) -> Response:
    """Queue of candidate person merges needing review."""
    merges: list[dict[str, Any]] = []
    return _render("person_merge.html", request, merges=merges)


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
