"""Port definitions (Protocols) for the hexagonal architecture.

Ports define the interfaces that adapters implement.  The domain and
pipeline modules depend only on these Protocols, never on concrete
adapter implementations.

All port methods use only domain types and kernel trust wrappers.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from syggramma.domain import (
    Book,
    Campaign,
    Contact,
    Course,
    Department,
    Distribution,
    Fact,
    Institution,
    Match,
    Message,
    Person,
    Review,
)
from syggramma.kernel import (
    CampaignId,
    Inferred,
    MessageId,
    Parsed,
    PersonId,
    Raw,
    Result,
    Tainted,
)

# ── Pipeline-level exceptions ──────────────────────────────────────────────


class HarvestError(Exception):
    """Base for errors that cross the adapter→pipeline boundary."""


class SuspiciousEmptyResult(HarvestError):
    """A department known to have data returned empty."""


class RateLimitedError(HarvestError):
    """The upstream service returned a 429 or rate-limit response."""


class RecaptchaChallengeError(HarvestError):
    """The upstream service presented a reCAPTCHA challenge."""

# ── Ingestion ports ─────────────────────────────────────────────────────────


@runtime_checkable
class CourseCatalogPort(Protocol):
    """Abstraction over the Eudoxus REST API (or any other course catalogue)."""

    async def fetch_institutions(self) -> Parsed[list[dict[str, object]]]:
        """Return the full institution/department tree."""
        ...

    async def fetch_institution_academics(self) -> Parsed[dict[str, object]]:
        """Return the full response including institutionAcademics and academicSecretariats."""
        ...

    async def fetch_courses(
        self, secretariat_id: int, year: int,
    ) -> Parsed[dict[str, list[dict[str, object]]]]:
        """Return all courses for a department-year, keyed by semester."""
        ...

    async def fetch_course_books(self, course_id: int) -> Parsed[dict[str, object]]:
        """Return book assignments for a single course."""
        ...

    async def fetch_book_by_isbn(self, isbn: str) -> Parsed[list[dict[str, object]]]:
        """Look up a book by ISBN."""
        ...

    async def fetch_book_by_id(self, book_id: int) -> Parsed[list[dict[str, object]]]:
        """Look up a book by its Eudoxus id."""
        ...

    async def fetch_book_courses(
        self, book_id: int, year: int,
    ) -> Parsed[dict[str, object]]:
        """Reverse index: which courses distribute a given book."""
        ...

    def mark_prior_year_data(self, secretariat_id: int, has_data: bool) -> None:
        """Record that a secretariat had data in a previously harvested year."""
        ...


# ── Snapshot storage port ───────────────────────────────────────────────────


@runtime_checkable
class SnapshotStorePort(Protocol):
    """Content-addressed storage for raw HTTP responses (L0)."""

    def store(self, url: str, body: bytes, headers: dict[str, str] | None = None) -> Raw:
        """Store a response and return its Raw wrapper with snapshot_id."""
        ...

    def exists(self, sha256: str) -> bool:
        """Check if a snapshot with the given hash already exists."""
        ...


# ── Normalizer port ─────────────────────────────────────────────────────────


@runtime_checkable
class PersonNameNormalizerPort(Protocol):
    """Greek person-name normalisation.

    The normaliser is a pure function with versioned transforms.
    """

    VERSION: str  # e.g. "normalize.person_name:v2"

    def normalize(self, raw: str) -> str:
        """Normalise a single person-name string to its canonical form."""
        ...

    def tokenize(self, raw: str) -> list[str]:
        """Split a name field into individual name tokens."""
        ...

    def split_surname_given(self, tokens: list[str]) -> tuple[str | None, str | None]:
        """Best-effort split into (surname, given).

        Returns (None, None) when the split is ambiguous.
        """
        ...


# ── Matcher port ────────────────────────────────────────────────────────────


@runtime_checkable
class MatcherPort(Protocol):
    """Entity resolution for person names.

    The matcher produces Inferred verdicts that require human
    verification before reaching the outreach module.
    """

    RULES_VERSION: str  # e.g. "resolve.ensemble:v4"

    async def match_course_professor(
        self, course: Course, book: Book,
    ) -> Inferred[Match]:
        """Produce a match verdict for a professor ↔ course ↔ book triple."""
        ...

    async def find_candidates(
        self, name: str, block_key: str,
    ) -> Sequence[Person]:
        """Find candidate persons for a name within a blocking key."""
        ...

    async def merge_persons(
        self, person_a: Person, person_b: Person, evidence: str,
    ) -> Inferred[Person]:
        """Merge two person records into one."""
        ...


# ── Enrichment ports (sync, for synchronous pipelines) ─────────────────────


@runtime_checkable
class SyncOpenAlexPort(Protocol):
    """Synchronous OpenAlex API for author profiles."""

    def search_author(self, display_name: str) -> Parsed[list[dict[str, object]]]:
        """Search for an author by name."""
        ...

    def fetch_author_by_id(self, openalex_id: str) -> Parsed[dict[str, object]]:
        """Fetch an author by their OpenAlex id."""
        ...

    def fetch_works(self, author_id: str, per_page: int = 25) -> Parsed[list[dict[str, object]]]:
        """Fetch works for an author."""
        ...

    def extract_profile(self, author_data: dict[str, object]) -> dict[str, object]:
        """Extract a standardised profile."""
        ...

    def close(self) -> None: ...


@runtime_checkable
class SyncOrcidPort(Protocol):
    """Synchronous ORCID API."""

    def fetch_record(self, orcid: str) -> Parsed[dict[str, object]]: ...
    def extract_name(self, record: dict[str, object]) -> dict[str, str]: ...
    def extract_external_ids(self, record: dict[str, object]) -> list[dict[str, str]]: ...
    def close(self) -> None: ...


@runtime_checkable
class SyncCrossrefPort(Protocol):
    """Synchronous Crossref API."""

    def fetch_works_by_doi(self, doi: str) -> Parsed[dict[str, object]]: ...
    def search_by_author(
        self, author_name: str, rows: int = 10,
    ) -> Parsed[list[dict[str, object]]]: ...
    def extract_publication(self, work: dict[str, object]) -> dict[str, object]: ...
    def close(self) -> None: ...


# ── Enrichment ports (async) ────────────────────────────────────────────────


@runtime_checkable
class OpenAlexPort(Protocol):
    """Async OpenAlex API for author profiles."""

    async def fetch_author(self, name: str) -> Parsed[list[dict[str, object]]]:
        """Search for an author by name."""
        ...

    async def fetch_author_by_id(self, openalex_id: str) -> Parsed[dict[str, object]]:
        """Fetch an author by their OpenAlex id."""
        ...


@runtime_checkable
class OrcidPort(Protocol):
    """ORCID API for researcher identity."""

    async def fetch_record(self, orcid: str) -> Parsed[dict[str, object]]:
        """Fetch a public ORCID record."""
        ...


@runtime_checkable
class CrossrefPort(Protocol):
    """Crossref API for publication metadata."""

    async def fetch_works(self, doi: str) -> Parsed[dict[str, object]]:
        """Fetch metadata for a DOI."""
        ...


@runtime_checkable
class UniversityScraperPort(Protocol):
    """Scraper for a university's faculty directory."""

    async def fetch_contact(
        self, person: Person,
    ) -> Tainted[str]:
        """Scrape a faculty page for contact details.

        Returns Tainted content that must pass through
        ``llm.extract(schema, tainted)`` before use.
        """
        ...


# ── LLM port ────────────────────────────────────────────────────────────────


@runtime_checkable
class LlmPort(Protocol):
    """Constrained LLM interface for structured extraction.

    **Safety rule:** The LLM must never receive free-form scraped content.
    All scraped text is ``Tainted[str]`` and must pass through ``extract``
    with a constrained schema.  The only entry point for scraped content
    is ``extract(schema, tainted)``.
    """

    async def extract[T](
        self, schema: type[T], tainted: Tainted[str],
    ) -> Parsed[T]:
        """Extract structured data from tainted text using a constrained schema.

        The LLM may only emit values matching the schema; anything else
        is discarded.  The result is ``Parsed[T]`` (L1), still requiring
        human review before use in outreach.
        """
        ...

    async def draft(
        self, template_name: str, facts: list[Fact], campaign: Campaign,
    ) -> tuple[str, str]:
        """Draft a subject + body from a fixed fact list.

        The LLM may rephrase facts but may **not** introduce new claims.
        The fact list is closed — enforced by the type signature.
        """
        ...


# ── Database port ───────────────────────────────────────────────────────────


@runtime_checkable
class DatabasePort(Protocol):
    """Abstract persistence layer.  Implemented by SQLAlchemy adapters."""

    async def store_institution(self, institution: Institution) -> Institution:
        ...

    async def store_department(self, department: Department) -> Department:
        ...

    async def store_course(self, course: Course) -> Course:
        ...

    async def store_book(self, book: Book) -> Book:
        ...

    async def store_distribution(self, distribution: Distribution) -> None:
        ...

    async def store_person(self, person: Person) -> Person:
        ...

    async def store_match(self, match: Match) -> Match:
        ...

    async def store_contact(self, contact: Contact) -> Contact:
        ...

    async def store_message(self, message: Message) -> Message:
        ...

    async def store_campaign(self, campaign: Campaign) -> Campaign:
        ...

    async def store_review(self, review: Review) -> Review:
        ...

    async def get_person_by_id(self, person_id: PersonId) -> Person | None:
        ...

    async def get_matches_for_review(
        self, limit: int = 50,
    ) -> Sequence[Match]:
        """Get unresolved matches needing human review."""
        ...

    async def execute_many(
        self, stmt: str, params: list[dict[str, object]],
    ) -> None:
        """Bulk execute a parameterised statement."""
        ...


# ── Mail port ───────────────────────────────────────────────────────────────


@runtime_checkable
class MailerPort(Protocol):
    """SMTP abstraction for sending emails."""

    async def send(
        self,
        to: Contact,
        subject: str,
        body: str,
        campaign_id: CampaignId,
        message_id: MessageId,
    ) -> Result[None]:
        """Send a single message.  Returns Ok or Error.

        The caller is responsible for transactional outbox logic;
        this port only performs the SMTP delivery.
        """
        ...


# ── Clock port ──────────────────────────────────────────────────────────────


@runtime_checkable
class ClockPort(Protocol):
    """Abstract clock for testability."""

    def now(self) -> datetime:
        ...

    def today(self) -> datetime:
        ...


# ── Events / Bus (for pipeline composition) ─────────────────────────────────


@runtime_checkable
class EventBusPort(Protocol):
    """Lightweight in-process event bus for pipeline orchestration."""

    async def publish(self, event_name: str, payload: dict[str, object]) -> None:
        ...

    async def subscribe(self, event_name: str, handler: Any) -> None:
        ...
