# Autonomous Defect-Hunt Report #2 — Syggramma

Protocol: V7 Proactive | Epistemic: EGFV | Iteration 2 | 98 tests | 29 modules audited

══════════════════════════════════════════
EXECUTIVE SUMMARY
══════════════════════════════════════════

Full surface (29 modules) triaged across 8 defect taxonomy classes.
FINDINGS: 1 VERIFIED + FIXED, 1 CONFIRMED SUSPECTED, 5 CLEARED (innocent), 1 UNKNOWN (needs runtime).
PRIOR REPORT FALSE ALARMS: 2 (pilot_queries.py and analysis_views.py — flagged for SQL injection in prior audit, found innocent).
NEW SURFACE: 6 M5-M7 modules are stubs (empty or TODO-returning) — zero runtime surface to hunt.
REGRESSION: D1 fix applied; all 98 tests, mypy, and import-linter pass.

══════════════════════════════════════════
INVENTORY
══════════════════════════════════════════

| ID | Region | Finding | Trigger | Innocence | Status | Severity |
|----|--------|---------|---------|-----------|--------|----------|
| D1 | pipelines/outreach | Outbox.dispatch silently drops messages when mailer_fn returns Error | FIRED | NO-DEFENSE | VERIFIED + FIXED | HIGH |
| D2 | pipelines/outreach | FrequencyCapPolicy uses global counter despite per-person parameter | FIRED | PARTIAL-DEFENSE | CONFIRMED SUSPECTED | MEDIUM |
| D3 | adapters/storage | SnapshotStore TOCTOU between exists() and write() | — | — | UNKNOWN | LOW |
| D4 | pipelines/harvest | Blind Exception catch — should catch EudoxusError subclasses | DID-NOT-FIRE | CODE-INNOCENT | CLEARED | — |
| D5 | adapters/db/pilot_queries | SQL injection via f-strings (prior audit flag) | DID-NOT-FIRE | CODE-INNOCENT | CLEARED (innocent) | — |
| D6 | adapters/db/analysis_views | SQL injection in materialized views | DID-NOT-FIRE | CODE-INNOCENT | CLEARED (innocent) | — |
| D7 | adapters/eudoxus | httpx.AsyncClient connection leak on error | DID-NOT-FIRE | CODE-INNOCENT | CLEARED (innocent) | — |

D1 FIX APPLIED: pipelines/outreach/__init__.py:286 — added `else: remaining.append(msg)` for Error-returning mailerFn results.

══════════════════════════════════════════
PRIOR REPORT FALSE ALARMS (CORRECTED)
══════════════════════════════════════════

The previous audit asserted:
  A1 [VF]: "R10 pilot_queries.py contains f-string SQL injection at get_courses_with_books() line 92"

STATUS: FALSE (innocent). The file contains 9 module-level SQL string constants and one dict. Zero f-strings. Zero runtime interpolation. Verified by AST analysis — `ast.walk(ast.parse(source))` found zero `ast.JoinedStr` nodes. The code flagged in the prior audit no longer exists (was likely a different version, or the audit hallucinated function names that don't exist).

analysis_views.py: Same — 8 CREATE MATERIALIZED VIEW string constants, no injection surface.

══════════════════════════════════════════
M5-M7 SURFACE: ALL STUBS
══════════════════════════════════════════

Six new modules added for milestones M5-M7 contain zero runtime surface:
- adapters/mail/__init__.py — empty file
- adapters/llm/__init__.py — empty file
- adapters/universities/__init__.py — empty file
- pipelines/analyze/__init__.py — 4 methods returning empty lists with TODO comments
- api/__init__.py — 7 endpoints returning hardcoded empty responses
- cli/__init__.py — CLI entry point (previously existing, unchanged)

These will be re-hunted when implementation begins.

══════════════════════════════════════════
COVERAGE STATEMENT
══════════════════════════════════════════
Surface audited:        All 29 source modules
Defect classes covered: All 8 taxonomy classes
Confirmed defects:      1 HIGH (D1 — FIXED)
Confirmed suspected:    1 MEDIUM (D2)
Cleared (innocent):     5
Unknown (needs runtime):1 LOW
Stub (no surface):      6

Clean-claim scope: "All 29 modules were audited across all 8 taxonomy classes.
  One VERIFIED DEFECT found and fixed (D1: message loss in Outbox.dispatch).
  Five candidates cleared as innocent. One LOW-severity concurrency finding (D3)
  remains UNKNOWN pending stress testing. Six M5-M7 modules are stubs with no
  runtime surface to hunt."

Highest-value next action: Implement mail/LLM adapters, then re-hunt those surfaces.
  Also: concurrency stress test for SnapshotStore to resolve D3.

Encoded: 2026-07-23 | 98 tests | 29 modules | 7 candidates | 2 iterations
