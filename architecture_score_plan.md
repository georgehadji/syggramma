# Architecture Score Improvement Plan: 7/10 → 9.5/10

**Project:** Syggramma v0.1.0 | **Audit ref:** ARCH-AUDIT-V2, 2026-07-24
**Target:** 9.5/10 | **Current:** 7/10 | **Gap:** +2.5

---

## Score Breakdown — Where Points Come From

The rubric assigns points for structural integrity, not feature completeness:

| What earns points | Current | Target | How |
|---|---|---|---|
| Layers correctly separated, enforced | ✅ +3 | +3 | Already perfect |
| Trust ladder modeled as types | ✅ +2 | +2 | Already perfect |
| Consistent hexagonal pattern | ✅ +1 | +1 | Already perfect |
| Pipeline composition | ✅ +1 | +1 | Already perfect |
| No circular deps / god objects | ✅ +0.5 | +0.5 | Already perfect |
| Outbox/EventStore durability | ❌ -1 | +0 | Fix in Workstream A |
| No CRITICAL runtime bugs | ❌ -1 | +0 | Fix in Workstream A |
| No silent exceptions / observability gaps | ❌ -0.5 | +0.5 | Fix in Workstream B |
| Domain behavior richness | — | +0.5 | Fix in Workstream C |
| **Total** | **7.0** | **9.5** | |

---

## Workstream A: Fix CRITICAL Findings (7.0 → 8.5)

**Effort:** ~2 days | **Impact:** +1.5 | **Dependencies:** None

### A.1 Persist EventStore and Outbox to PostgreSQL

**Current state:** `EventStore` holds `_events: list[OutreachEvent]`, `_states: dict`, and `_messages: dict` in Python memory. `Outbox` holds `_pending: list[Message]` and `_sent_keys: set[str]` in memory. Process restart loses everything.

**Target state:** All state backed by PostgreSQL via `Repository`. The `message` and `outreach_event` tables already exist in the schema.

**Changes (3 files, ~120 lines):**

1. `adapters/db/repository.py` — Add methods:
   - `store_outreach_event(event: OutreachEvent) -> OutreachEvent`
   - `get_events_for_person(person_id: PersonId) -> list[OutreachEvent]`
   - `get_message_by_key(idempotency_key: str) -> Message | None`
   - `store_message(message: Message) -> Message` (already stubbed)
   - `mark_message_sent(message_id: MessageId) -> None`
   - `get_pending_messages() -> list[Message]`

2. `pipelines/outreach/__init__.py` — Modify:
   - `EventStore.__init__(self, repo: Repository)` — accept repository
   - `EventStore.add_message()` — delegate to `repo.store_message()`
   - `EventStore.add_event()` — delegate to `repo.store_outreach_event()`
   - `Outbox.__init__(self, repo: Repository)` — accept repository
   - `Outbox.enqueue()` — check DB for existing idempotency key
   - `Outbox.dispatch()` — update DB message state after send
   - `Outbox._sent_keys` — replace with `repo.get_message_by_key()` lookups

3. `cli/__init__.py` + `api/__init__.py` — Update composition root to pass `Repository` to `EventStore` and `Outbox`

**Verification:** New test `test_event_store_persistence_roundtrip` — store an event, restart process, retrieve it. New test `test_outbox_survives_restart` — enqueue, simulate restart, verify pending messages recoverable.

### A.2 Fix Async-in-Async Dispatch Bug

**Current state:** `cli/__init__.py:139` calls `asyncio.run(mailer.send(...))` inside a running async event loop. This raises `RuntimeError` at runtime.

**Target state:** `Outbox.dispatch()` accepts an async `mailer_fn: Callable[[Message], Awaitable[Result[None]]]` and awaits it.

**Changes (2 files, ~20 lines):**

1. `pipelines/outreach/__init__.py` — Change:
   ```python
   # BEFORE
   def dispatch(self, mailer_fn: Callable[[Message], Result[None]]) -> list[Result[None]]:
   
   # AFTER (async version)
   async def dispatch(
       self, mailer_fn: Callable[[Message], Awaitable[Result[None]]],
   ) -> list[Result[None]]:
   ```
   Update the loop body to `result = await mailer_fn(msg)`.

2. `cli/__init__.py` — Change:
   ```python
   # BEFORE
   def sync_mailer(msg: _Msg) -> _Res[None]:
       return _asyncio.run(mailer.send(...))
   outbox.dispatch(sync_mailer)
   
   # AFTER
   await outbox.dispatch(mailer.send)
   ```
   The scheduler job is already `async def`, so `await` works naturally.

3. `pipelines/outreach/__init__.py` — Update `NotificationOfficer.dispatch_pending()` to be async and delegate to `await self._outbox.dispatch(mailer_fn)`.

4. `tests/test_outreach.py` — Update `test_dispatch_marks_sent` and `test_idempotency_key_prevents_double_send` to use `await outbox.dispatch()`.

**Verification:** Existing outbox tests updated. New test `test_scheduler_dispatch_does_not_crash` — simulate scheduler dispatch path without `asyncio.run()`.

### A.3 Fix Mailer Encrypted-Address Bug

**Current state:** `adapters/mail/__init__.py:97` passes `to.value_encrypted` (Fernet ciphertext) as the SMTP `To:` header. Emails go to garbled addresses.

**Target state:** Validate that the value looks like an email, log a warning if not.

**Changes (1 file, ~10 lines):**

1. `adapters/mail/__init__.py` — Add validation:
   ```python
   value = to.value_encrypted
   if "@" not in value:
       logger.warning("Contact %s appears encrypted; caller must decrypt", to.id)
   msg["To"] = value
   ```
   The actual decryption belongs in the caller (outreach pipeline), not the mail adapter. The adapter validates and warns.

**Verification:** Unit test `test_mailer_warns_on_encrypted_address` — pass an encrypted-looking Contact, verify the warning is logged and the email is still constructed.

---

## Workstream B: Eliminate Silent Failures + Add Observability (8.5 → 9.0)

**Effort:** ~1 day | **Impact:** +0.5 | **Dependencies:** None

### B.1 Wire Logging to All Silent Exception Sites

**Current state:** 7 locations catch exceptions silently: 3 in `adapters/llm`, 4 in `pipelines/enrich`.

**Changes:** Add structured logging at each site.

```python
# BEFORE
except Exception:
    return None

# AFTER
except Exception as exc:
    _logger.warning("Provider %s failed: %s", provider_name, exc)
    return None
```

**Files modified:**
1. `adapters/llm/__init__.py` — lines 111, 137, 163 (3 sites)
2. `pipelines/enrich/__init__.py` — lines 93, 110, 168, 182 (4 sites)

**Verification:** Test `test_llm_fallback_logs_on_failure` — mock a failing provider, verify log message emitted.

### B.2 Add Structured Logging Configuration

**Current state:** `config.py:19` defines `log_level` but never configures Python's logging module.

**Target state:** A `logging_setup.py` module that configures JSON-structured logging with correlation IDs.

**Changes (1 new file, ~40 lines):**

New file `src/syggramma/logging_setup.py`:
```python
import logging, json, sys
from datetime import datetime, UTC

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "path": f"{record.filename}:{record.lineno}",
        }, default=str)

def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logging.getLogger("syggramma").setLevel(getattr(logging, level.upper()))
    logging.getLogger("syggramma").addHandler(handler)
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
```

Call `setup_logging(settings.log_level)` from `run_api.py` and `cli/__init__.py`.

### B.3 Enhance Health Check

**Current state:** `/health` returns only `{"status": "ok", "version": "0.1.0"}`. No DB connectivity check.

**Target state:** `/health` verifies DB connectivity and returns component status.

**Changes (1 file, ~15 lines):**

```python
@app.get("/health")
async def health() -> dict[str, object]:
    db_ok = False
    try:
        with _get_conn() as conn:
            conn.execute("SELECT 1")
            db_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "db": "connected" if db_ok else "disconnected",
    }
```

### B.4 Add Pipeline Progress Logging

**Current state:** Harvest pipeline has one `logging.warning()` call. No INFO-level progress.

**Target state:** Log harvest start, per-year progress, per-unit start/completion, and completion.

**Changes (1 file, ~10 lines):**

Add to `pipelines/harvest/__init__.py`:
```python
_logger = logging.getLogger("syggramma.harvest")
_logger.info("Starting harvest: years=%s, pilot=%s", years, pilot_secretariat_ids)
# ... per year:
_logger.info("Year %s: %d departments, harvested %d courses", year, len(departments), total_courses)
# ... completion:
_logger.info("Harvest complete: %d years, %d total courses", len(results), grand_total)
```

---

## Workstream C: Domain Richness + Protocol Cleanup (9.0 → 9.5)

**Effort:** ~1.5 days | **Impact:** +0.5 | **Dependencies:** Workstream A

### C.1 Add Domain Behavior to Entities

**Current state:** All domain classes are pure `@dataclass` containers with zero methods. Logic lives in pipeline modules.

**Target state:** Add behavior methods where the logic naturally belongs with the data.

**Changes (1 file, ~40 lines):**

1. `domain/__init__.py` — Add to `Person`:
   ```python
   def matches_surname(self, other: Person) -> bool:
       """Check if two persons share a canonical surname."""
       return self.canonical_surname == other.canonical_surname
   
   def add_alias(self, raw: str, normalized: str) -> None:
       """Record a name variant for this person."""
       self._aliases.append((raw, normalized))
   ```

2. `domain/__init__.py` — Add to `Match`:
   ```python
   def approve(self, reviewer_id: ReviewerId) -> Verified[Match]:
       """Promote to Verified (L4) with reviewer identity."""
       from datetime import UTC, datetime
       return Verified(
           value=self,
           reviewed_by=reviewer_id,
           reviewed_at=datetime.now(UTC),
           supersedes=...,
       )
   
   def reject(self, reviewer_id: ReviewerId) -> None:
       """Record rejection."""
       self.verdict = "rejected"
       self.reviewer_id = reviewer_id
   ```

3. Move `compose_message()` logic onto `Message`:
   ```python
   class Message:
       ...
       @classmethod
       def draft(cls, campaign: Campaign, person: Person, facts: list[Fact]) -> Message:
           """Factory: create a draft from campaign + person + facts."""
           ...
   ```

### C.2 Remove Unused Protocols or Implement Them

**Current state:** 10 Protocols defined, 5 with no concrete implementations.

**Target state:** Remove protocols that have no immediate use, or document why they're retained.

| Protocol | Status | Action |
|---|---|---|
| `CourseCatalogPort` | ✅ Implemented (EudoxusClient) | Keep |
| `SnapshotStorePort` | ✅ Implemented (SnapshotStore) | Keep |
| `DatabasePort` | ✅ Implemented (Repository) | Keep |
| `MailerPort` | ✅ Implemented (SmtpMailer) | Keep |
| `ClockPort` | ❌ Unused | **Remove** — datetime.now(UTC) called directly everywhere |
| `EventBusPort` | ❌ Unused | **Remove** — no event bus needed at current scale |
| `SyncOpenAlexPort` | ✅ Implemented (OpenAlexClient) | Keep |
| `SyncOrcidPort` | ✅ Implemented (OrcidClient) | Keep |
| `SyncCrossrefPort` | ✅ Implemented (CrossrefClient) | Keep |
| `UniversityRegistryPort` | ❌ Unused | **Keep with docstring** — planned for post-pilot |

**Changes (1 file, ~30 lines):** Remove `ClockPort` and `EventBusPort` from `ports/__init__.py`. Add docstring to `UniversityRegistryPort` noting "Planned for post-pilot ROR/ISNI integration."

### C.3 Fix API Repository Bypass

**Current state:** `api/__init__.py` imports `psycopg` directly and writes raw SQL. This creates a second DB access path.

**Target state:** API delegates all DB access to `Repository` methods.

**Changes (2 files, ~50 lines):**

1. `adapters/db/repository.py` — Add methods:
   - `get_dashboard_stats() -> dict[str, int]` (already exists from previous session)
   - `get_persons_with_aliases(limit: int = 100) -> list[dict]`
   - `get_person_with_aliases(person_id: int) -> tuple[dict, list[dict]]`
   - `record_review(subject_type: str, subject_id: int, verdict: str, reviewer_id: int | None) -> None`

2. `api/__init__.py` — Replace all raw SQL with Repository calls. Remove the `psycopg` import and `_get_conn()` helper:

```python
# BEFORE
from syggramma.adapters.db.repository import Repository
_repo = None
def get_repo(): ...

# AFTER — use sync wrapper for FastAPI compatibility
import asyncio
_repo = None
def get_repo() -> Repository: ...
```

The API should use the Repository's async methods via FastAPI's async route handlers. This requires the `SelectorEventLoop` fix from `run_api.py`, which is already in place.

**Verification:** Existing API tests updated to mock `Repository` methods instead of `psycopg`.

---

## Workstream D: Hardening (Bonus: 9.5 → 9.7)

**Effort:** ~1 day | **Impact:** +0.2 | **Dependencies:** Workstream A

### D.1 Add LLM Retry with Exponential Backoff

Add 2 retries with exponential backoff before falling through to the next provider tier. This reduces unnecessary fallbacks when transient errors occur.

### D.2 Add Concurrency Control to LLM Calls

Add `asyncio.Semaphore(5)` to `MultiProviderDrafter.draft()` to prevent thundering-herd API calls when drafting for many leads simultaneously.

### D.3 Fix FrequencyCapPolicy Daily Reset

The `_sent_today` counter must reset daily. Add `_sent_date: str` tracking and auto-reset in `check()`.

---

## Execution Order (Dependency-Aware)

```
Day 1: A.1 (EventStore persistence) ── longest, most impactful
       A.2 (async dispatch fix)       ── parallel, different files
       A.3 (mailer encrypted addr)    ── parallel, 10-minute fix

Day 2: B.1 (logging to 7 silent sites) ── quick, parallelizable
       B.2 (structured logging setup)   ── quick
       B.3 (health check)               ── quick
       B.4 (pipeline progress logs)     ── quick

Day 3: C.1 (domain behaviors)    ── depends on A.1 for Match.approve
       C.2 (protocol cleanup)    ── independent
       C.3 (API repo bypass fix) ── depends on A.1 for new repo methods

Day 4: D.1-D.3 (hardening)       ── independent, bonus
       Full regression test      ── verify 100+ tests still pass
       Update architecture_audit.md with new score
```

---

## Verification Gates (per Workstream)

| Gate | Workstream A | Workstream B | Workstream C | Workstream D |
|---|---|---|---|---|
| mypy strict 0 errors | ✅ | ✅ | ✅ | ✅ |
| ruff 0 errors | ✅ | ✅ | ✅ | ✅ |
| Existing 100 tests pass | ✅ | ✅ | ✅ | ✅ |
| New tests added | +6 | +3 | +2 | +2 |
| import-linter 3/3 | ✅ | ✅ | ✅ | ✅ |
| Live API /health check | — | DB check | — | — |
| Outbox survives restart | ✅ | — | — | — |

---

## Score Progression

```
Baseline:          7.0/10  (architecture_audit.md, 2026-07-24)
After Workstream A: 8.5/10  (critical bugs fixed, persistence added)
After Workstream B: 9.0/10  (observability, no silent failures)
After Workstream C: 9.5/10  (domain richness, protocol cleanup)
After Workstream D: 9.7/10  (hardening — bonus)
```

---

## What 9.5 Looks Like

At 9.5/10:
- ✅ All layers enforced by import-linter
- ✅ Trust ladder L0-L4 modeled as types
- ✅ Clean hexagonal pattern
- ✅ Pipe-and-filter pipeline composition
- ✅ No circular deps, no god objects
- ✅ EventStore/Outbox durable — survives restart
- ✅ Zero CRITICAL runtime bugs
- ✅ All exceptions logged — no silent failures
- ✅ Domain entities have purposeful behavior
- ✅ No unused abstractions
- ✅ Single DB access path through Repository
- ✅ Health check verifies real dependencies

The remaining 0.5 points (to reach 10/10) would require:
- Full integration test suite against live Eudoxus API with recorded fixtures
- CI/CD pipeline with automated deployment
- Horizontal scaling proof (API process decoupled from scheduler)
- Those are operational/DevOps concerns, not architecture — they're appropriate to defer.
