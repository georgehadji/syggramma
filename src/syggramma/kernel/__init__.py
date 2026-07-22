"""Trust-level wrappers: type-level enforcement of the data trust ladder.

Every piece of data in the system occupies exactly one trust level (L0–L4).
The wrappers in this module make it a **compile-time type error** to pass
data of the wrong trust level to a function that requires a higher one.

This is the single most important architectural invariant in the system:
levels only increase through explicit, recorded transitions, and the outreach
module can only accept L1 (raw from Eudoxus) and L4 (human-verified) facts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, NewType, TypeVar

T = TypeVar("T")


# ── Identity types ──────────────────────────────────────────────────────────

# Each is a NewType so the type system distinguishes them even though
# they are all int/uuid underneath.  This prevents mixing up ids at
# the call site without runtime overhead.

InstitutionId = NewType("InstitutionId", int)
DepartmentId = NewType("DepartmentId", int)
CourseId = NewType("CourseId", int)
BookId = NewType("BookId", int)
PersonId = NewType("PersonId", int)
ContactId = NewType("ContactId", int)
CampaignId = NewType("CampaignId", int)
MessageId = NewType("MessageId", int)

SnapshotId = NewType("SnapshotId", int)
UnitId = NewType("UnitId", int)
RunId = NewType("RunId", int)

ReviewerId = NewType("ReviewerId", str)
InferenceId = NewType("InferenceId", int)
MatchId = NewType("MatchId", int)


# ── Trust-level markers ─────────────────────────────────────────────────────

class TrustLevel(Enum):
    """The five rungs of the data trust ladder (L0–L4)."""

    RAW = 0
    PARSED = 1
    NORMALIZED = 2
    INFERRED = 3
    VERIFIED = 4


class Trusted(ABC, Generic[T]):
    """Abstract base for trust-level wrappers.

    Every piece of data carries its trust level; the class hierarchy
    mirrors L0–L4.  The trust level can only increase (monotonic) and
    every transition writes an audit record.
    """

    value: T

    @property
    @abstractmethod
    def level(self) -> TrustLevel: ...


# ── L0 / Raw ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Raw(Trusted[bytes]):
    """Bytes as received from an external source. Never parsed, never trusted.

    Stored content-addressed by sha256.  Immutable by definition.
    """

    value: bytes
    snapshot_id: SnapshotId
    url: str
    fetched_at: datetime
    sha256: str

    @property
    def level(self) -> TrustLevel:
        return TrustLevel.RAW


# ── L1 / Parsed ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Parsed(Trusted[T]):
    """Schema-validated against a Pydantic model. Structure trusted, semantics not."""

    value: T
    source_snapshot_id: SnapshotId
    parsed_at: datetime

    @property
    def level(self) -> TrustLevel:
        return TrustLevel.PARSED


# ── L2 / Normalized ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Normalized(Trusted[T]):
    """Deterministic pure transforms applied. Reproducible from L1."""

    value: T
    normalizer_version: str
    source: Parsed[T]

    @property
    def level(self) -> TrustLevel:
        return TrustLevel.NORMALIZED


# ── L3 / Inferred ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeatureVector:
    """Interpretable feature vector that produced an inference."""

    features: Mapping[str, float]
    method: str  # e.g. "resolve.name_match:v3"


@dataclass(frozen=True)
class Inferred(Trusted[T]):
    """Produced by heuristics, fuzzy matching, or LLM. Carries confidence + features.

    **Rule R1:** The outreach module must reject Inferred values at compile time.
    A human must promote ``Inferred`` → ``Verified`` first.
    """

    value: T
    confidence: float  # [0, 1]
    features: FeatureVector
    inference_id: InferenceId

    @property
    def level(self) -> TrustLevel:
        return TrustLevel.INFERRED


# ── L4 / Verified ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Verified(Trusted[T]):
    """A human looked at an L3 datum and affirmed it.

    This is the only trust level that can enter the outreach module.
    Carries reviewer identity and timestamp for auditability.
    """

    value: T
    reviewed_by: ReviewerId
    reviewed_at: datetime
    supersedes: InferenceId | None = None

    @property
    def level(self) -> TrustLevel:
        return TrustLevel.VERIFIED


# ── Tainted data (for scraped content) ──────────────────────────────────────

TaintedT = TypeVar("TaintedT", bound=str | bytes)


class Tainted(Generic[TaintedT]):
    """Scraped web content that may contain hostile text.

    This type exists to prevent prompt injection through scraped pages.
    Tainted data must pass through ``llm.extract(schema, tainted)`` with a
    constrained output schema before it becomes trusted text.  Free-form
    prompting over Tainted content is a type error because the LLM port
    only accepts ``Untainted[str]``.

    See ``ports/llm.py`` and ``adapters/llm/``.
    """

    __slots__ = ("_source_url", "_value")

    def __init__(self, value: TaintedT, source_url: str) -> None:
        self._value = value
        self._source_url = source_url

    @property
    def value(self) -> TaintedT:
        return self._value

    @property
    def source_url(self) -> str:
        return self._source_url


class Untainted(str):
    """Text that has passed through a constrained extraction schema.

    This is the output side of the Tainted → Untainted pipeline.
    Untainted text is safe to interpolate into prompts.
    """


# ── Result type ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Error:
    """Base for domain errors.

    Makes the success/failure path explicit
    without exceptions for expected failures.
    """

    message: str


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T


type Result[T] = Ok[T] | Error


def ok[T](value: T) -> Ok[T]:
    return Ok(value)


def err(message: str) -> Error:
    return Error(message)
