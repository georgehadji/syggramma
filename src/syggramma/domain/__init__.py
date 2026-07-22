"""Domain entities, value objects, and invariants.

This module is *pure*: it imports nothing outside the standard library and
kernel.  No I/O, no database, no external dependencies — every function
here is deterministic and testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from syggramma.kernel import (
    BookId,
    CampaignId,
    ContactId,
    CourseId,
    DepartmentId,
    FeatureVector,
    InstitutionId,
    MatchId,
    MessageId,
    PersonId,
    ReviewerId,
    SnapshotId,
)

# ── Value Objects ───────────────────────────────────────────────────────────


class Semester(Enum):
    WINTER = 0
    SPRING = 1
    SUMMER = 2


class Period(Enum):
    WINTER = "Ximerino"
    SPRING = "Earino"
    SUMMER = "Kalokairino"


@dataclass(frozen=True)
class NormalizedName:
    """A normalised person name.

    Carries the canonical form and a flag indicating whether the
    (surname, given) split is reliable.
    """

    canonical: str
    surname: str | None = None
    given: str | None = None
    split_ambiguous: bool = False


@dataclass(frozen=True)
class Address:
    """Postal address for a secretariat or institution."""

    street: str | None = None
    city: str | None = None
    prefecture: str | None = None
    postal_code: str | None = None


@dataclass(frozen=True)
class Provenance:
    """Every factual claim about a person or book carries provenance.

    This satisfies the GDPR right of access: you can trace every field
    back to a source URL and a point in time.
    """

    source_url: str
    snapshot_id: SnapshotId
    fetched_at: datetime
    method: str  # e.g. "eudoxus.harvest:v1", "openalex.enrich:v1"


@dataclass(frozen=True)
class Fact:
    """A single atomic fact with provenance.

    Facts are the building blocks of outreach messages.  The LLM receives
    a closed list of Facts; it may rephrase but not introduce new ones.
    """

    claim: str
    provenance: Provenance



# ── Verdicts ────────────────────────────────────────────────────────────────


class Verdict(Enum):
    """Four-valued outcome of person-to-course matching.

    These are the *only* possible verdicts for a match between a person
    and a course distribution.  The matching system never returns a simple
    boolean — each verdict drives a different action.
    """

    AUTHOR_SELF = "author_self"
    """Confirmed: the professor teaching this course IS the book's author."""

    PROBABLE = "probable"
    """Strong evidence but not certain — goes to human review queue."""

    UNCERTAIN = "uncertain"
    """Weak signal — low-priority human review."""

    NOT_AUTHOR = "not_author"
    """Confirmed: the professor is NOT the author (a commercial lead)."""


# ── Entity states (for outreach state machine) ──────────────────────────────


class OutreachState(Enum):
    """States of the outreach state machine.

    See ARCHITECTURE.md §6.6 for the full diagram.
    """

    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    SCORED = "scored"
    DRAFTED = "drafted"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    APPROVED = "approved"
    QUEUED = "queued"
    SENT = "sent"
    REPLIED = "replied"
    BOUNCED = "bounced"
    OPTED_OUT = "opted_out"
    SUPPRESSED = "suppressed"  # terminal


class EventType(Enum):
    """Types of outreach events in the event log."""

    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    SCORED = "scored"
    DRAFTED = "drafted"
    REJECTED = "rejected"
    APPROVED = "approved"
    QUEUED = "queued"
    SENT = "sent"
    REPLY_RECEIVED = "reply_received"
    BOUNCE_RECEIVED = "bounce_received"
    OPT_OUT_RECEIVED = "opt_out_received"
    SUPPRESSED = "suppressed"


# ── Entities ────────────────────────────────────────────────────────────────


@dataclass
class Institution:
    id: InstitutionId | None = None
    eudoxus_id: int | None = None
    name: str = ""
    ror_id: str | None = None


@dataclass
class Department:
    id: DepartmentId | None = None
    institution_id: InstitutionId | None = None
    eudoxus_academic_id: int | None = None
    secretariat_id: int | None = None
    school: str | None = None
    name: str = ""
    is_live: bool = True


@dataclass
class Course:
    id: CourseId | None = None
    eudoxus_id: int | None = None
    department_id: DepartmentId | None = None
    year: int | None = None
    semester: Semester | None = None
    period: Period | None = None
    code: str | None = None
    title: str = ""
    professor_raw: str = ""
    snapshot_id: SnapshotId | None = None


@dataclass
class Book:
    id: BookId | None = None
    eudoxus_id: int | None = None
    isbn: str | None = None
    title: str = ""
    subtitle: str | None = None
    authors_raw: str = ""
    edition: str | None = None
    publication_year: int | None = None
    publisher_id: str | None = None
    publisher_name: str | None = None
    pages: int | None = None
    link_to_publisher: str | None = None
    snapshot_id: SnapshotId | None = None


@dataclass
class Distribution:
    """A book distributed through a course in a given year."""

    course_id: CourseId
    book_id: BookId
    bookgroup_id: int | None = None
    year: int | None = None


@dataclass
class Person:
    """Canonical person record after entity resolution.

    Every raw name string maps to a Person via PersonAlias.
    """

    id: PersonId | None = None
    canonical_surname: str | None = None
    canonical_given: str | None = None
    display_name: str | None = None
    created_at: datetime | None = None


@dataclass
class PersonAlias:
    """One raw name string observed for a person, with the evidence."""

    id: int | None = None
    person_id: PersonId | None = None
    raw_text: str = ""
    normalized: str = ""
    source_kind: str = ""  # "professor" | "author" | "enrichment"
    evidence: dict[str, object] | None = None
    normalizer_version: str = ""


@dataclass
class Authorship:
    """A person authored a book."""

    person_id: PersonId
    book_id: BookId
    position: int = 0


@dataclass
class Teaching:
    """A person taught a course (with confidence from the resolver)."""

    person_id: PersonId
    course_id: CourseId
    confidence: float = 0.0
    method: str = ""


@dataclass
class Match:
    """A verdict linking a person, a book, and a course.

    This is the core output of the resolve pipeline.
    """

    id: MatchId | None = None
    person_id: PersonId | None = None
    book_id: BookId | None = None
    course_id: CourseId | None = None
    verdict: Verdict = Verdict.UNCERTAIN
    score: float = 0.0
    features: FeatureVector | None = None
    rules_version: str = ""
    created_at: datetime | None = None
    superseded_by: MatchId | None = None


@dataclass
class Profile:
    """Enriched external profile for a person."""

    person_id: PersonId
    openalex_id: str | None = None
    orcid: str | None = None
    scopus_id: str | None = None
    homepage: str | None = None
    bio: str | None = None
    topics: list[str] = field(default_factory=list)
    field_sources: dict[str, Provenance] = field(default_factory=dict)


@dataclass
class Contact:
    """A contact method (email, phone) for a person.

    Contact values are encrypted at rest.  value_hash enables
    deduplication and suppression lookups without decryption.
    """

    id: ContactId | None = None
    person_id: PersonId | None = None
    kind: str = ""  # "email" | "phone"
    value_encrypted: str = ""
    value_hash: str = ""
    source_url: str = ""
    fetched_at: datetime | None = None
    verified_at: datetime | None = None
    status: str = "unverified"


@dataclass
class Review:
    """A human review of an inferred fact."""

    id: int | None = None
    subject_type: str = ""  # "match" | "person_merge" | "enrichment"
    subject_id: int | None = None
    verdict: str = ""  # "accepted" | "rejected" | "needs_changes"
    reviewer_id: ReviewerId | None = None
    reviewed_at: datetime | None = None
    note: str = ""


@dataclass
class Campaign:
    """An outreach campaign with recorded legal basis."""

    id: CampaignId | None = None
    name: str = ""
    legal_basis: str = ""
    lia_document_ref: str = ""
    created_at: datetime | None = None


@dataclass
class OutreachEvent:
    """An immutable event in the outreach event log."""

    id: int | None = None
    person_id: PersonId | None = None
    campaign_id: CampaignId | None = None
    event_type: EventType | None = None
    payload: dict[str, object] | None = None
    occurred_at: datetime | None = None
    actor: str = ""  # "system" | reviewer_id


@dataclass
class Message:
    """An email message sent or pending.

    The idempotency_key guarantees no double-send even on retry.
    """

    id: MessageId | None = None
    person_id: PersonId | None = None
    campaign_id: CampaignId | None = None
    subject: str = ""
    body: str = ""
    facts: list[Fact] = field(default_factory=list)
    state: OutreachState = OutreachState.DRAFTED
    approved_by: ReviewerId | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    idempotency_key: str = ""


@dataclass
class Suppression:
    """A suppressed address (survives erasure — only the salted hash remains)."""

    address_hash: str
    reason: str = ""
    created_at: datetime | None = None
