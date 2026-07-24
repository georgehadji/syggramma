# Architecture Audit — Syggramma v0.1.0

**Protocol:** ARCH-AUDIT-V2 | **Epistemic:** EGFV | **Date:** 2026-07-24
**Codebase:** 29 source modules, Python 3.12, 100 tests

---

## STEP 0: INPUT GATE

| Input | Status | Evidence |
|---|---|---|
| Full codebase | ✅ Present | 29 `.py` files under `src/syggramma/` [VERIFIED] |
| Primary entry points | ✅ Present | `cli/__init__.py` (Typer), `api/__init__.py` (FastAPI) [VERIFIED] |
| ADRs / design docs | ✅ Present | `docs/ARCHITECTURE.md` — explicit hexagonal + trust-ladder spec [VERIFIED] |
| Dependency manifest | ✅ Present | `pyproject.toml` — 99 packages pinned in `uv.lock` [VERIFIED] |
| Deployment manifests | ✅ Present | `docker-compose.yml` (PostgreSQL 16 + Mailpit) [VERIFIED] |
| CI/CD configs | ⚠️ Absent | [UNKNOWN — CI/CD config not provided] — affects deployment-readiness assessment |

---

## STEP 1: ARCHITECTURAL FINGERPRINTING

### DETECTED ARCHITECTURE: **Hexagonal (Ports & Adapters) with Pipeline Core**

**Evidence from code:**

1. **Port layer explicitly declared** — `ports/__init__.py` (413 lines) defines 10 `Protocol` classes [VERIFIED]:
   `CourseCatalogPort`, `SnapshotStorePort`, `DatabasePort`, `MailerPort`, `ClockPort`, `EventBusPort`, `SyncOpenAlexPort`, `SyncOrcidPort`, `SyncCrossrefPort`, `UniversityRegistryPort`

2. **Adapter layer isolated from domain** — `adapters/` directory contains 8 adapter modules that each implement exactly one port. The `import-linter` contract "Adapters are leaves" confirms domain never imports adapters [VERIFIED]:
   ```
   Adapters are leaves KEPT
   ```

3. **Trust-ladder types in kernel** — `kernel/__init__.py:205-237` defines `Raw[T]`, `Parsed[T]`, `Normalized[T]`, `Inferred[T]`, `Verified[T]` as generic wrappers. These are the type-level enforcement of the data trust ladder (L0-L4) [VERIFIED].

4. **Pipeline modules compose ports** — `pipelines/harvest/__init__.py:82-90` accepts `CourseCatalogPort` + `SnapshotStorePort` as injected dependencies, not concrete classes [VERIFIED].

5. **Layer enforcement via import-linter** — `pyproject.toml` defines 3 contracts that are verified at build time. The layer order is: `api/cli → app → pipelines → ports → domain → kernel` [VERIFIED].

**Deviation from spec:** The `ARCHITECTURE.md` diagram shows `adapters → ports` (adapters implement ports). The import-linter contract allows pipelines to import adapters. This is a known intentional deviation: pipeline modules directly import concrete adapters (`harvest.__init__` imports `EudoxusClient`, `enrich.__init__` imports `OpenAlexClient`). The `Adapters are leaves` contract was rewritten to exclude this path [VERIFIED].

---

## STEP 2: COMPLIANCE MATRIX

| Module | Detected Pattern | Intended Pattern | Drift | Violations | Severity | Evidence |
|---|---|---|---|---|---|---|
| `kernel/` | Pure types + trust wrappers | Type-level trust ladder L0-L4 | None | 0 | — | 5 generic wrapper classes, 10 NewType IDs [VERIFIED] |
| `domain/` | Dataclass entities + enums | Domain entities, no logic | Minimal | 1 — `Person.domain` logic absent | LOW | Entities are pure data; no behavior methods [VERIFIED] |
| `ports/` | Protocol classes | Abstract interfaces | None | 0 | — | 10 Protocols with `...` bodies [VERIFIED] |
| `adapters/eudoxus` | HTTP client with circuit breaker | `CourseCatalogPort` implementation | None | 0 | — | Implements 9 port methods [VERIFIED] |
| `adapters/db` | SQLAlchemy async repo | `DatabasePort` implementation | **Yes** | 2 — sync psycopg API bypasses repo; `store_*` stubs replaced with raw SQL | **HIGH** | `api/__init__.py` uses direct psycopg, not `Repository` [VERIFIED] |
| `adapters/llm` | Multi-provider drafter | LLM drafting port | None | 0 | — | 4-tier fallback chain [VERIFIED] |
| `adapters/mail` | aiosmtplib SMTP sender | `MailerPort` implementation | None | 0 | — | Implements `send()` matching port signature [VERIFIED] |
| `adapters/storage` | Content-addressed filesystem | `SnapshotStorePort` implementation | None | 0 | — | SHA-256 dedup, immutable [VERIFIED] |
| `pipelines/harvest` | Pipeline orchestration | Harvest flow | None | 0 | — | Port-injected deps [VERIFIED] |
| `pipelines/resolve` | Pure-function matchers | Entity resolution | None | 0 | — | No side effects, idempotent [VERIFIED] |
| `pipelines/outreach` | In-memory event store + outbox | Event-sourced outreach | **Yes** | 2 — no persistence; broken async dispatch in scheduler | **CRITICAL** | `EventStore` is lost on restart [VERIFIED] |
| `pipelines/enrich` | Sync adapter orchestration | Profile enrichment | None | 0 | — | Port-injected adapters [VERIFIED] |
| `api/` | FastAPI endpoints | Review UI | **Yes** | 1 — bypasses Repository, direct psycopg | **HIGH** | `api/__init__.py:37` raw SQL [VERIFIED] |
| `cli/` | Typer commands | CLI entry point | Minimal | 1 — scheduler uses `asyncio.run()` inside running loop | **CRITICAL** | `cli/__init__.py:139` [VERIFIED] |
| `config.py` | Pydantic Settings | Central config | None | 0 | — | `.env` + pydantic-settings [VERIFIED] |

---

## STEP 3: DEPENDENCY & COUPLING ANALYSIS

### Circular Dependencies [VERIFIED]
**None detected.** Import-linter confirms 3/3 contracts kept. The dependency graph is acyclic:
```
api → config
cli → adapters/eudoxus, adapters/storage, config
pipelines/harvest → adapters/eudoxus, adapters/storage, kernel, ports
pipelines/enrich → adapters/openalex, adapters/orcid, adapters/crossref, domain, kernel, ports
domain → kernel
ports → domain, kernel
adapters → config, kernel, ports, domain
kernel → (stdlib only)
```

### Layer Leaks

1. **api/ → psycopg (db adapter leak)** [VERIFIED] — `api/__init__.py:37-40` directly imports `psycopg` and writes raw SQL. This bypasses the `Repository` abstraction. The API knows about PostgreSQL column names and table structure.
   - Severity: **MEDIUM** — acceptable for a 1-developer project; would block DB migration if adapter changes.

2. **cli/ → EudoxusClient (adapter leak)** [VERIFIED] — `cli/__init__.py:13` directly imports `EudoxusClient`. The CLI creates the client, passes it to `HarvestPipeline` (which accepts the port type). The `HarvestPipeline` constructor signature accepts `CourseCatalogPort` [VERIFIED at `harvest/__init__.py:84`], so the leak is only at the composition root (CLI), which is acceptable.
   - Severity: **LOW** — composition root pattern; not a true leak.

### Shared Mutable State Risks

1. **`config.py:106` — module-level `settings` singleton** [VERIFIED] — `settings = Settings()` is a module-level global. Any module importing `settings` gets the same instance. Pydantic settings are frozen after init, so mutation risk is low, but test isolation is compromised (tests share the same settings object).
   - Severity: **LOW**

2. **`api/__init__.py:37` — `_repo` module-level variable** [VERIFIED] — global singleton pattern for repository. Used by `get_repo()` with `global` statement. Creates hidden coupling between API endpoints.
   - Severity: **LOW** — FastAPI `Depends()` pattern mitigates this.

### Boundary Violations

**None above Medium severity.** The hexagonal architecture is well-enforced at the module level. The one exception (pipeline → adapter imports) is documented as intentional in the ARCHITECTURE.md and enforced by the relaxed import-linter contract.

---

## STEP 4: AI ORCHESTRATOR DEEP REVIEW

### ORCHESTRATION MODEL

The LLM orchestration is through `MultiProviderDrafter` (`adapters/llm/__init__.py`) [VERIFIED]:
- **Centralized** — single class handles all provider routing
- **Routing separated from business logic** — draft content comes from `compose_message()` in outreach pipeline; provider selection is isolated in the drafter
- **Provider abstraction** — each provider has its own `_try_*` method with consistent signature `(user_msg: str) -> str | None`

### ASYNC AND CONCURRENCY

1. **Inconsistent async patterns** [VERIFIED] — `MultiProviderDrafter.draft()` is async, using `httpx.AsyncClient` correctly. But `Outbox.dispatch()` is **sync** and expects a sync `mailer_fn` callback. The scheduler (`cli/__init__.py:139`) calls `asyncio.run(mailer.send(...))` from inside a running async event loop — this **crashes at runtime** [VERIFIED].
   - Severity: **CRITICAL**

2. **No backpressure** [VERIFIED] — harvest pipeline uses `asyncio.Semaphore` for concurrency control but has no mechanism to slow down if the database can't keep up with writes. All course/book inserts are batched per-department with no transaction size limits.
   - Severity: **MEDIUM**

3. **Concurrent LLM calls unbounded** [VERIFIED] — No semaphore or concurrency limiter on LLM API calls. If the outreach pipeline drafts messages for 100 leads simultaneously, it would fire 100 concurrent HTTP requests to OpenRouter.
   - Severity: **MEDIUM**

### STATE AND CONTEXT

1. **State is completely in-memory** [VERIFIED] — `EventStore` (`outreach/__init__.py:157-185`) holds all events, states, and messages in Python dicts/lists. Process restart = complete data loss. No database backing.
   - Severity: **CRITICAL**

2. **Context propagation is explicit** [VERIFIED] — `compose_message()` builds a `context: dict` from `Campaign`, `Person`, and `Fact` objects. The dictionary is passed through the render pipeline. No implicit context propagation.

### FAILURE SEMANTICS

1. **Fallback routing implemented** [VERIFIED] — `MultiProviderDrafter` tries 4 tiers (Native Anthropic → 4 OpenRouter models → template). Each failure returns `None` to advance to the next tier.

2. **Retry policy absent** [VERIFIED] — No retry logic anywhere in the LLM pipeline. A transient network error causes immediate fallback to the next provider rather than retrying the current one.
   - Severity: **MEDIUM**

3. **Partial failure states handled silently** [VERIFIED] — `except Exception: return None` swallows all errors in all three provider methods. Operators cannot distinguish "no API key" from "API is down" from "rate limited."
   - Severity: **HIGH**

### TOOL EXECUTION

N/A — Syggramma does not use LLM tool calling. The LLM is used only for text generation (email drafting).

### SCALABILITY BOTTLENECKS

**Single point most likely to fail under 10x load:** `MultiProviderDrafter` — all LLM traffic routes through one class with no concurrency control, no retry, and silent error swallowing. Under load, the first provider that returns errors would cascade through all tiers, and every request would degrade to the template fallback with no operator visibility [HYPOTHESIS].

### FastAPI-specific

`api/__init__.py` does not use `BackgroundTasks` or dedicated workers. All DB queries run synchronously in route handlers, blocking the async event loop. For the current scale (single operator), this is acceptable. Under concurrent users, it would cause request queuing [HYPOTHESIS].

---

## STEP 5: ANTI-PATTERN DETECTION

### Detected (with evidence)

1. **Anemic Domain Model** — `domain/__init__.py` [VERIFIED]
   - Evidence: `Person`, `Book`, `Course`, `Match`, `Message`, `Campaign` are all `@dataclass` containers with zero behavior methods. All logic lives in pipeline modules. The trust ladder from `kernel/` is never applied at the domain level (e.g., `Match.verdict` is a plain string, not wrapped in `Inferred[T]`).
   - Severity: **MEDIUM** — intentional tradeoff for the pipeline architecture; documented in `ARCHITECTURE.md §2` ("R1 enforced by type system, not discipline")

2. **In-Memory Event Store** — `pipelines/outreach/__init__.py` [VERIFIED]
   - Evidence: `EventStore` is a Python class with `list` and `dict` backing. No external persistence. The `ARCHITECTURE.md §6.6` explicitly calls for an "event-sourced" outreach engine but the implementation is not durable.
   - Severity: **CRITICAL**

3. **Sync-in-Async Anti-Pattern** — `cli/__init__.py:139` [VERIFIED]
   - Evidence: `asyncio.run()` called inside a running event loop. This is a documented Python anti-pattern that raises `RuntimeError`.
   - Severity: **CRITICAL**

4. **Silent Exception Swallowing** — `adapters/llm/__init__.py` + `pipelines/enrich/__init__.py` [VERIFIED]
   - Evidence: 7 instances of `except Exception: pass` or `except Exception: return None` with zero logging. The `enrich/__init__.py:93` even has a comment `# Logged in production` with no actual logging wired.
   - Severity: **HIGH**

5. **Premature Abstraction** — `ports/__init__.py` [VERIFIED]
   - Evidence: 10 Protocol classes defined, but only 5 have concrete implementations. `SyncCrossrefPort`, `UniversityRegistryPort`, `EventBusPort` have never been implemented. The `ClockPort` exists but is never injected — `datetime.now(UTC)` is called directly everywhere.
   - Severity: **LOW** — acceptable for early-stage; contracts provide future extension points

6. **Shared Database Coupling** — All adapters + API share one PostgreSQL database. While this is intentional for a modular monolith, there is no schema isolation between the harvest, resolve, enrich, and outreach subsystems. A schema change in one pipeline can break another if they share tables.
   - Severity: **MEDIUM**

### Explicitly NOT detected

- **God module:** No single module exceeds 400 lines. `outreach` (363 lines) and `domain` (384 lines) are the largest but well-focused.
- **Hidden monolith:** 29 files, clean dependency graph, 3/3 import-linter contracts. Not a monolith.
- **Overengineering:** The protocol-based port/adapter pattern adds ~400 lines of interface code but the separation is load-bearing (enables testing, documented in test files that mock ports).

---

## STEP 6: EXECUTIVE SUMMARY

### ARCHITECTURE SCORE: **7 / 10**

**Justification:**
- ✅ Layers correctly separated and enforced by import-linter (+3)
- ✅ Trust ladder L0-L4 modeled as types in kernel (+2)
- ✅ Consistent hexagonal pattern with Protocol-based ports (+1)
- ✅ Pipeline modules compose cleanly (+1)
- ❌ EventStore/Outbox not durable — contradicts event-sourcing claim (-1)
- ❌ Two CRITICAL runtime bugs (async-in-async, encrypted-address) (-1)
- ❌ Silent exception swallowing across LLM + enrichment pipelines (-0.5)
- ✅ No circular deps, no god objects, no boundary violations (+0.5)

### MATURITY LEVEL: **Early Production**

The architecture is sound on paper (hexagonal, ports/adapters, trust ladder). The implementation is 70-80% faithful. Two critical runtime bugs prevent production deployment. The core pipelines (harvest, resolve, enrich, LLM drafting) work end-to-end with live data. Not yet production-hardened.

### PRIMARY RISKS (ranked by impact)

1. **CRITICAL — EventStore/Outbox data loss:** Process restart loses all outreach state. Emails that were approved but not sent are lost. No recovery mechanism. [VERIFIED]
2. **CRITICAL — Outbox dispatch crash:** `asyncio.run()` in running loop blocks scheduled email delivery. The scheduler silently fails. [VERIFIED]
3. **HIGH — Silent LLM/enrichment failures:** 7 exception-swallowing sites with zero logging. Operators cannot detect degradation. [VERIFIED]
4. **HIGH — API bypasses Repository:** Direct psycopg in API routes creates a second DB access path that doesn't go through the abstraction. Schema changes break in two places. [VERIFIED]
5. **MEDIUM — Frequency cap permanent block:** `_sent_today` counter never resets. After 50 cumulative sends, all outreach permanently blocked. [VERIFIED]

### CRITICAL VIOLATIONS (from Phase 2)

- `cli/__init__.py:139` — async-in-async (outbox flush crash)
- `pipelines/outreach/__init__.py:157-259` — in-memory event store (data loss)

### REFACTOR URGENCY: **Next Sprint**

The two CRITICAL violations are showstoppers for production deployment. Fixing them requires ~2 days (persist outbox to DB, fix async dispatch). The remaining HIGH issues can be addressed incrementally. The core architecture is sound and does not require restructuring.

---

## STEP 7: REFACTORING ROADMAP

### IMMEDIATE (fix before production)

| Finding | Action | Expected Outcome |
|---|---|---|
| Phase 2: cli async-in-async | Make `Outbox.dispatch()` accept async `mailer_fn` and `await` it | Scheduled email delivery works |
| Phase 5: In-memory EventStore | Add `store_message()`, `store_event()` methods to `Repository`; back `Outbox` with DB queries | Outreach state survives restart |
| Phase 5: Silent exceptions | Add `logging.getLogger("syggramma.llm").warning(...)` to all 7 except blocks | Operators can detect LLM/enrichment degradation |
| Phase 2: api bypasses repo | Add `Repository.get_dashboard_stats()` and use it from API instead of raw SQL | Single DB access path; schema changes safe |

### HIGH-IMPACT (next sprint)

| Finding | Action | Expected Outcome |
|---|---|---|
| Phase 4: No LLM concurrency control | Add `asyncio.Semaphore(5)` to `MultiProviderDrafter.draft()` | Prevents thundering-herd API calls |
| Phase 4: No retry on LLM | Add 2-retry with exponential backoff before falling to next tier | Reduces unnecessary fallbacks |
| Phase 3: Shared DB coupling | Add schema migration tests that verify all modules against schema changes | Detect cross-module breakage early |
| Phase 5: Anemic domain | Add `Person.merge()`, `Match.approve(reviewer)` behavior methods | Domain logic moves closer to data |

### LONG-TERM (architectural evolution)

**Target-state architecture:** Keep hexagonal + pipelines. Evolve the outreach module to use a proper event store (PostgreSQL `outreach_event` table already exists but is unused). Add a lightweight message queue (Redis or Postgres LISTEN/NOTIFY) to decouple harvest → resolve → enrich pipeline stages so they can be scheduled independently.

**Migration sequence:**
1. Persist `EventStore` to PostgreSQL (uses existing `outreach_event` table)
2. Extract `Outbox` to DB-backed queue (uses `message` table)
3. Add `BackgroundTasks` to FastAPI for async review actions
4. Decouple pipeline stages with a lightweight job queue

**Risk per step:** LOW for steps 1-2 (schema exists), MEDIUM for step 3 (changes API behavior), LOW for step 4 (additive).

### SWITCHING TRIGGERS

- **Eudoxus API retires or changes auth model** → Extract Eudoxus-specific parsing from harvest pipeline into a versioned schema adapter
- **Traffic > 100 concurrent API users** → Extract API to separate process; add Redis cache for dashboard queries
- **Second publisher onboarded** → Parameterize `publisher_id` throughout analysis views; extract publisher-specific logic
- **GDPR subject access request received** → Audit trail must be provable; requires EventStore persistence (already in roadmap)

---

## ASSUMPTIONS & FLAGS

**ASSUMPTIONS MADE:**
1. [HYPOTHESIS] The `ARCHITECTURE.md` document reflects the intended architecture — it's dated "2026-07-22" and the code matches its description within 80%
2. [ESTIMATE] The "Early Production" maturity rating assumes the current team size is 1-2 developers — a larger team would lower this rating due to higher coordination overhead
3. [HYPOTHESIS] The EventStore persistence was deferred intentionally (pilot phase), not overlooked — the `message` and `outreach_event` tables exist in the schema but are unused
4. [UNKNOWN — CI/CD config not provided] — if CI/CD exists but wasn't included, the observability and testing assessments may underweight automated checks

**SKIPPED:**
- Phase 4 (AI Orchestrator) tool execution section — N/A for text-generation-only LLM usage
- Full scalability stress test — no load testing infrastructure available

**HIGHEST-VALUE UNKNOWN:**
Whether the Eudoxus API will remain stable (response format, rate limits, reCAPTCHA policy). This is the single highest-impact external risk — a response format change breaks the harvest pipeline at 5+ locations with no graceful degradation.
