"""Eudoxus REST API client.

Implements ``ports.CourseCatalogPort`` against the live Eudoxus API.
Handles rate limiting, circuit-breaking, and the known API quirks
documented in ``docs/EUDOXUS-API.md``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

import httpx

from syggramma.kernel import Parsed, SnapshotId
from syggramma.ports import (
    HarvestError,
    RateLimitedError,
    RecaptchaChallengeError,
    SuspiciousEmptyResult,
)

# ── Custom errors ──────────────────────────────────────────────────────────

class EudoxusError(HarvestError):
    """Base for Eudoxus API errors."""


# ── Rate limiter ───────────────────────────────────────────────────────────

class TokenBucket:
    """Simple in-memory token bucket rate limiter."""

    def __init__(self, rate: float, burst: int | None = None) -> None:
        self._rate = rate  # tokens per second
        self._burst = burst or max(1, int(rate * 2))
        self._tokens = float(self._burst)
        self._last_refill = datetime.now(UTC)
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens < 1:
                sleep_time = (1 - self._tokens) / self._rate
                await asyncio.sleep(sleep_time)
                self._refill()
            self._tokens -= 1

    def _refill(self) -> None:
        now = datetime.now(UTC)
        elapsed = (now - self._last_refill).total_seconds()
        self._tokens = min(float(self._burst), self._tokens + elapsed * self._rate)
        self._last_refill = now


# ── Circuit breaker ────────────────────────────────────────────────────────

class CircuitBreaker:
    """Simple circuit breaker for external API calls."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._failures = 0
        self._last_failure_time: datetime | None = None
        self._open = False

    async def call[T](self, coro: Awaitable[T]) -> T:
        if self._open:
            if self._last_failure_time and (
                datetime.now(UTC) - self._last_failure_time
            ).total_seconds() > self._reset_timeout:
                self._open = False
                self._failures = 0
            else:
                raise EudoxusError("Circuit breaker is open")
        try:
            result = await coro
            self._failures = 0
        except Exception:
            self._failures += 1
            self._last_failure_time = datetime.now(UTC)
            if self._failures >= self._failure_threshold:
                self._open = True
            raise
        else:
            return result


# ── Eudoxus client ─────────────────────────────────────────────────────────

class EudoxusClient:
    """HTTP client for the Eudoxus REST API.

    Implements the 5 endpoints documented in ``docs/EUDOXUS-API.md``.
    Handles rate limiting, circuit breaking, reCAPTCHA detection,
    and the empty-result trap.
    """

    BASE_URL = "https://service.eudoxus.gr/coursebooks/rest/"

    def __init__(
        self,
        base_url: str = BASE_URL,
        max_rps: float = 2.0,
        max_concurrent: int = 4,
        user_agent: str | None = None,
        timeout: float = 30.0,
        recaptcha_stop: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._rate_limiter = TokenBucket(rate=max_rps, burst=max_concurrent)
        self._circuit_breaker = CircuitBreaker()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._recaptcha_stop = recaptcha_stop
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "User-Agent": user_agent or "Syggramma/0.1",
                "Accept": "application/json",
            },
        )
        self._prior_year_data: dict[int, bool] = {}
        """Cache of which secretariat ids had data in a prior year,
        used by the SuspiciousEmptyResult guard."""

    # ── Port implementation (CourseCatalogPort) ─────────────────────────

    async def fetch_institutions(self) -> Parsed[list[dict[str, Any]]]:
        """GET secretariat-academics — full institution/department tree.

        Returns the raw ``institutions`` list from the response.
        """
        data = await self._get("courses-books/secretariat-academics")
        return Parsed(
            value=data["institutions"],
            source_snapshot_id=SnapshotId(0),  # filled by pipeline
            parsed_at=datetime.now(UTC),
        )

    async def fetch_institution_academics(self) -> Parsed[dict[str, Any]]:
        """GET secretariat-academics — full response including academics."""
        data = await self._get("courses-books/secretariat-academics")
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_courses(
        self, secretariat_id: int, year: int,
    ) -> Parsed[dict[str, list[dict[str, Any]]]]:
        """GET get-semesters-courses for a department-year."""
        data = await self._get(
            "courses-books/get-semesters-courses",
            params={"secretariatId": secretariat_id, "year": year},
        )
        self._check_empty_result(secretariat_id, year, data)
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_course_books(self, course_id: int) -> Parsed[dict[str, Any]]:
        """GET course/{courseId}/books — book assignments for a course."""
        data = await self._get(f"courses-books/course/{course_id}/books")
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_book_by_isbn(self, isbn: str) -> Parsed[list[dict[str, Any]]]:
        """GET book/eudoxus/info?isbn={isbn}."""
        data = await self._get(
            "courses-books/book/eudoxus/info",
            params={"isbn": isbn},
        )
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_book_by_id(self, book_id: int) -> Parsed[list[dict[str, Any]]]:
        """GET book/eudoxus/info?bookId={id}."""
        data = await self._get(
            "courses-books/book/eudoxus/info",
            params={"bookId": book_id},
        )
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_book_courses(
        self, book_id: int, year: int,
    ) -> Parsed[dict[str, Any]]:
        """GET book/eudoxus/courses — reverse index for a book."""
        data = await self._get(
            "courses-books/book/eudoxus/courses",
            params={"bookId": book_id, "year": year},
        )
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_departments(self) -> Parsed[dict[str, Any]]:
        """Return the full academic secretariats dict for department resolution."""
        data = await self._get("courses-books/secretariat-academics")
        return Parsed(
            value=data["academicSecretariats"],
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    async def fetch_academic_years(self) -> Parsed[dict[str, Any]]:
        """GET academic-years endpoint."""
        data = await self._get("courses-books/academic-years")
        return Parsed(
            value=data,
            source_snapshot_id=SnapshotId(0),
            parsed_at=datetime.now(UTC),
        )

    # ── Internal HTTP helpers ───────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Rate-limited, circuit-broken GET request."""
        await self._rate_limiter.acquire()

        async def do_get() -> Any:
            async with self._semaphore:
                response = await self._client.get(path, params=params)
                self._check_response(response)
                return response.json()

        return await self._circuit_breaker.call(do_get())

    def _check_response(self, response: httpx.Response) -> None:
        """Validate the HTTP response before parsing JSON."""
        if response.status_code == 200:
            body = response.text.strip()
            # reCAPTCHA challenge: body is HTML, not JSON
            if body.startswith("<") and "recaptcha" in body.lower():
                if self._recaptcha_stop:
                    raise RecaptchaChallengeError(
                        "Eudoxus presented a reCAPTCHA challenge. "
                        "Harvest must stop and alert a human.",
                    )
            return

        if response.status_code == 429:
            raise RateLimitedError(f"Rate limited: {response.headers.get('Retry-After', 'unknown')}")

        response.raise_for_status()

    def _check_empty_result(
        self, secretariat_id: int, year: int, data: dict[str, object],
    ) -> None:
        """Guard: an empty result for a known-live department is suspicious.

        If we have prior-year data for this secretariat and the current
        year returns empty, raise SuspiciousEmptyResult.
        """
        if not data:  # empty dict
            if self._prior_year_data.get(secretariat_id):
                raise SuspiciousEmptyResult(
                    f"Secretariat {secretariat_id} had data in a prior year "
                    f"but returned empty for year {year}. "
                    f"This may indicate a silent API failure.",
                )

    def mark_prior_year_data(self, secretariat_id: int, has_data: bool) -> None:
        """Record that a secretariat had data in a previously harvested year."""
        self._prior_year_data[secretariat_id] = has_data

    async def close(self) -> None:
        await self._client.aclose()
