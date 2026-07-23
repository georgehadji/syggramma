"""Tests for the FastAPI API endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from syggramma.api import app, _get_conn


@pytest.fixture(autouse=True)
def mock_db() -> Any:
    """Mock psycopg connections so tests don't need a real DB."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=None)
    mock_conn.execute.return_value.fetchall.return_value = []
    mock_conn.execute.return_value.fetchone.return_value = {"n": 138}

    with patch("syggramma.api._get_conn", return_value=mock_conn):
        yield


@pytest.fixture
def client() -> httpx.AsyncClient:
    """Create an async test client that talks directly to the ASGI app."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
class TestAPI:
    async def test_health_endpoint(self, client: httpx.AsyncClient) -> None:
        """Health check returns ok status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_dashboard_returns_html(self, client: httpx.AsyncClient) -> None:
        """Dashboard returns HTML."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_match_review_queue(self, client: httpx.AsyncClient) -> None:
        """Match review queue returns HTML."""
        response = await client.get("/review/matches")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_person_merge_queue(self, client: httpx.AsyncClient) -> None:
        """Person merge queue returns HTML."""
        response = await client.get("/review/merges")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_match_detail(self, client: httpx.AsyncClient) -> None:
        """Match detail page returns HTML."""
        response = await client.get("/review/matches/1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_approve_match(self, client: httpx.AsyncClient) -> None:
        """Approve match returns ok."""
        response = await client.post("/review/matches/1/approve", params={"reviewer_id": "test"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_reject_match(self, client: httpx.AsyncClient) -> None:
        """Reject match returns ok."""
        response = await client.post("/review/matches/1/reject", params={"reviewer_id": "test"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
