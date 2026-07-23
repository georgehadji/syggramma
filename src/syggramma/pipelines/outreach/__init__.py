"""Outreach pipeline — event-sourced campaign engine.

Implements the architecture described in ARCHITECTURE.md §6.6:
  - Event-sourced state machine
  - Transactional outbox
  - Idempotency key
  - Policy objects (legal gates, suppression, frequency cap)
  - Human-in-the-loop gate
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from syggramma.domain import (
    Campaign,
    EventType,
    Fact,
    Message,
    OutreachEvent,
    OutreachState,
    Person,
    Suppression,
)
from syggramma.kernel import (
    CampaignId,
    MessageId,
    PersonId,
    Result,
    Ok,
    err,
    ok,
)

# ── State machine ──────────────────────────────────────────────────────────

# Valid transitions: {from_state: {event: to_state}}
TRANSITIONS: dict[OutreachState, dict[EventType, OutreachState]] = {
    OutreachState.DISCOVERED: {
        EventType.ENRICHED: OutreachState.ENRICHED,
    },
    OutreachState.ENRICHED: {
        EventType.SCORED: OutreachState.SCORED,
    },
    OutreachState.SCORED: {
        EventType.DRAFTED: OutreachState.DRAFTED,
    },
    OutreachState.DRAFTED: {
        EventType.DRAFTED: OutreachState.DRAFTED,
        EventType.REJECTED: OutreachState.REJECTED,
        EventType.APPROVED: OutreachState.APPROVED,
    },
    OutreachState.PENDING_APPROVAL: {
        EventType.APPROVED: OutreachState.APPROVED,
        EventType.REJECTED: OutreachState.REJECTED,
    },
    OutreachState.REJECTED: {},  # terminal
    OutreachState.APPROVED: {
        EventType.QUEUED: OutreachState.QUEUED,
    },
    OutreachState.QUEUED: {
        EventType.SENT: OutreachState.SENT,
    },
    OutreachState.SENT: {
        EventType.REPLY_RECEIVED: OutreachState.REPLIED,
        EventType.BOUNCE_RECEIVED: OutreachState.BOUNCED,
        EventType.OPT_OUT_RECEIVED: OutreachState.OPTED_OUT,
    },
    OutreachState.REPLIED: {},  # terminal
    OutreachState.BOUNCED: {},  # terminal
    OutreachState.OPTED_OUT: {},  # terminal
    OutreachState.SUPPRESSED: {},  # terminal
}


def transition(state: OutreachState, event: EventType) -> Result[OutreachState]:
    """Apply an event to a state, returning the new state or an error.

    Returns Ok(new_state) on success, Error(message) on invalid transition.
    """
    valid = TRANSITIONS.get(state, {})
    new_state = valid.get(event)
    if new_state is None:
        return err(
            f"Cannot transition from {state.value} via {event.value}. "
            f"Valid events: {list(valid.keys())}"
        )
    return ok(new_state)


# ── Policy objects ─────────────────────────────────────────────────────────

@dataclass
class PolicyResult:
    allowed: bool
    reason: str = ""


class SuppressionPolicy:
    """Check if a contact is suppressed before sending."""

    def __init__(self, suppressions: dict[str, Suppression] | None = None) -> None:
        self._suppressions = suppressions or {}

    def check(self, address_hash: str) -> PolicyResult:
        if address_hash in self._suppressions:
            return PolicyResult(False, "Address is suppressed")
        return PolicyResult(True, "")

    def add_suppression(self, address_hash: str, reason: str = "") -> None:
        self._suppressions[address_hash] = Suppression(
            address_hash=address_hash, reason=reason,
        )


class FrequencyCapPolicy:
    """Enforce maximum messages per person per time period."""

    def __init__(self, max_per_day: int = 50, quiet_period_days: int = 90) -> None:
        self._max_per_day = max_per_day
        self._quiet_period_days = quiet_period_days
        self._sent_today: int = 0

    def check(self, person_id: PersonId, last_sent: datetime | None) -> PolicyResult:
        if self._sent_today >= self._max_per_day:
            return PolicyResult(False, f"Daily cap reached ({self._max_per_day})")
        if last_sent:
            days_since = (datetime.now(timezone.utc) - last_sent).days
            if days_since < self._quiet_period_days:
                return PolicyResult(
                    False,
                    f"Quiet period: {days_since}d < {self._quiet_period_days}d",
                )
        return PolicyResult(True, "")

    def record_send(self) -> None:
        self._sent_today += 1


class LegalBasisPolicy:
    """Verify that a campaign has a recorded legal basis before sending."""

    def check(self, campaign: Campaign) -> PolicyResult:
        if not campaign.legal_basis:
            return PolicyResult(False, "Campaign has no legal basis")
        if not campaign.lia_document_ref:
            return PolicyResult(False, "Campaign has no LIA document reference")
        return PolicyResult(True, "")


# ── Event sourcing ─────────────────────────────────────────────────────────

class EventStore:
    """In-memory event store for the outreach event log.

    In production this would be backed by the database ``outreach_event`` table.
    """

    def __init__(self) -> None:
        self._events: list[OutreachEvent] = []
        self._states: dict[PersonId, OutreachState] = {}
        self._messages: dict[MessageId, Message] = {}

    def append(self, event: OutreachEvent) -> None:
        self._events.append(event)

    def get_state(self, person_id: PersonId) -> OutreachState:
        return self._states.get(person_id, OutreachState.DISCOVERED)

    def set_state(self, person_id: PersonId, state: OutreachState) -> None:
        self._states[person_id] = state

    def get_events(self, person_id: PersonId) -> list[OutreachEvent]:
        return [e for e in self._events if e.person_id == person_id]

    def add_message(self, message: Message) -> None:
        if message.id is not None:
            self._messages[message.id] = message

    def get_message(self, message_id: MessageId) -> Message | None:
        return self._messages.get(message_id)


# ── Draft engine ───────────────────────────────────────────────────────────

DEFAULT_ARTICLE_14_NOTICE = (
    "This message is sent by Εκδόσεις Κυριακίδη as part of a legitimate-interest "
    "outreach campaign under GDPR Article 6(1)(f). We hold the following data about "
    "you, sourced from the Eudoxus public registry and publicly available academic "
    "profiles: your name, institutional affiliation, and published book information. "
    "You have the right to access, rectify, or erase your data at any time. "
    "To object to further processing, click the link below."
)


def compose_message(
    campaign: Campaign,
    person: Person,
    facts: list[Fact],
    subject_template: str,
    body_template: str,
) -> Message:
    """Compose a draft message from a campaign, person, and facts.

    The Article 14 notice and objection link are automatically appended.
    """
    # Build context for template rendering
    context = {
        "display_name": person.display_name or "",
        "facts": [f.claim for f in facts],
        "legal_basis": campaign.legal_basis,
        "lia_ref": campaign.lia_document_ref,
        # Placeholder — real objection link requires a routing setup
        "objection_link": f"{{{{OBJECTION_LINK}}}}",
    }

    # Simple template rendering (in production, use Jinja2)
    subject = _render_template(subject_template, context)
    body = _render_template(body_template, context)
    body += f"\n\n---\n{DEFAULT_ARTICLE_14_NOTICE}"
    body += f"\n\nTo object: {context['objection_link']}"

    return Message(
        subject=subject,
        body=body,
        facts=list(facts),
        state=OutreachState.DRAFTED,
    )


def _render_template(template: str, context: dict[str, Any]) -> str:
    """Simple template renderer with {{placeholders}}.

    Uses Jinja2 in production; uses str.replace for testing.
    """
    import re
    def replacer(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        return str(context.get(key, m.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


# ── Transactional outbox ───────────────────────────────────────────────────

class Outbox:
    """Transactional outbox for guaranteed send with idempotency.

    The send path: write message + send-intent in one transaction → then dispatch.
    Idempotency key prevents double-send on retry.
    """

    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store
        self._pending: list[Message] = []
        self._sent_keys: set[str] = set()

    def enqueue(self, message: Message) -> Result[MessageId]:
        """Enqueue a message for sending.

        Checks for duplicate idempotency key before enqueuing.
        """
        if message.idempotency_key in self._sent_keys:
            return err(f"Duplicate idempotency key: {message.idempotency_key}")

        import uuid
        msg_id = MessageId(uuid.uuid4().int & 0x7FFFFFFF)
        message.id = msg_id
        self._pending.append(message)
        self._event_store.add_message(message)
        return ok(msg_id)

    def dispatch(self, mailer_fn: Callable[[Message], Result[None]]) -> list[Result[None]]:
        """Dispatch all pending messages."""
        results: list[Result[None]] = []
        remaining: list[Message] = []

        for msg in self._pending:
            try:
                result = mailer_fn(msg)
                if isinstance(result, Ok):
                    self._sent_keys.add(msg.idempotency_key)
                    msg.state = OutreachState.SENT
                results.append(result)
            except Exception:
                remaining.append(msg)

        self._pending = remaining
        return results

    def has_pending(self) -> bool:
        return len(self._pending) > 0
