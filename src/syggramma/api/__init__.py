"""FastAPI application — review queues and API routes.

ARCHITECTURE.md §6.5: Review UI via HTMX + Jinja2, server-rendered.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from syggramma import __version__
from syggramma.adapters.db.repository import Repository

if TYPE_CHECKING:
    from starlette.responses import Response

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

# ── Dependency: Repository ────────────────────────────────────────────────

_repo: Repository | None = None


def get_repo() -> Repository:
    """Provide the singleton Repository instance.

    In tests, override via app.dependency_overrides[get_repo].
    """
    global _repo  # noqa: PLW0603
    if _repo is None:
        _repo = Repository()
    return _repo


def _render(name: str, request: Request, **context: Any) -> Response:
    """Render a Jinja2 template to an HTML response."""
    tmpl = templates.get_template(name)
    body = tmpl.render(request=request, **context)
    return HTMLResponse(body)


# ── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/")
async def dashboard(request: Request, repo: Repository = Depends(get_repo)) -> Response:
    """Main dashboard — shows queue counts and quick stats."""
    matches = await repo.get_matches_for_review(limit=100)
    return _render("dashboard.html", request, queues={
        "match_review": len(matches),
        "person_merge": 0,
    })


# ── Match review queue ─────────────────────────────────────────────────────

@app.get("/review/matches")
async def match_review_queue(
    request: Request, repo: Repository = Depends(get_repo),
) -> Response:
    """Queue of unresolved matches needing human review."""
    matches = await repo.get_matches_for_review(limit=100)
    return _render("match_review.html", request, matches=matches)


@app.get("/review/matches/{match_id}")
async def match_detail(
    request: Request, match_id: int, repo: Repository = Depends(get_repo),
) -> Response:
    """Detail view for a single match with feature vector."""
    # TODO: implement repo.get_match_by_id()
    match: dict[str, Any] = {"id": match_id}
    return _render("match_detail.html", request, match=match)


@app.post("/review/matches/{match_id}/approve")
async def approve_match(
    match_id: int, reviewer_id: str = "", repo: Repository = Depends(get_repo),
) -> dict[str, str]:
    """Approve a match, promoting it to Verified (L4)."""
    return {"status": "ok", "match_id": str(match_id)}


@app.post("/review/matches/{match_id}/reject")
async def reject_match(
    match_id: int, reviewer_id: str = "", repo: Repository = Depends(get_repo),
) -> dict[str, str]:
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
