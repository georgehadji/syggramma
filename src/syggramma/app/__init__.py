"""Use cases / application services.

This is the composition root: the only module that wires pipelines
with adapters via ports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubmitMatchesForReview:
    """Use case: gather unresolved matches for human review."""

    limit: int = 50


@dataclass
class ReviewMatch:
    """Use case: a human reviews an inferred match."""

    match_id: int
    verdict: str  # "accepted" | "rejected"
    reviewer_id: str
    note: str = ""


@dataclass
class ApproveMessage:
    """Use case: a human approves a drafted message."""

    message_id: int
    reviewer_id: str


@dataclass
class SendApprovedMessages:
    """Use case: send all approved messages (transactional outbox dispatch)."""

    batch_size: int = 20


@dataclass
class RunHarvest:
    """Use case: run a harvest cycle for given years."""

    start_year: int = 2024
    end_year: int = 2025
    pilot_departments: list[int] | None = None
