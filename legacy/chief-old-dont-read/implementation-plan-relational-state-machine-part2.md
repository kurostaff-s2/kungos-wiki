### Unit 10: Phase Registry Auto-Upsert + Multi-Tenant Enforcement (P1)
- **Files:** `relational_store.py`, `super-council.py`
- **Scope:** Add auto-upsert in orchestrator init: scan `workflow_definitions.phases` JSON and INSERT missing names into `phase_names`. Add CHECK constraint on `workflow_runs.project_id`.
- **RED:** Test that adding a new phase to `workflow_definitions` auto-upserts into `phase_names`. Test that missing `project_id` is rejected.
- **GREEN:** Implement `_sync_phase_registry()` in `RelationalStore`: parse `workflow_definitions.phases` JSON, INSERT OR IGNORE into `phase_names`. Add CHECK constraint on `workflow_runs.project_id` (non-empty).
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_phase_registry.py -v` — new phases auto-upserted. Missing `project_id` rejected.
- **Dependencies:** Unit 2
- **Notes:** Fixes M2 (phase registry friction), L6 (multi-tenant isolation).

### Unit 11: Timestamp Precision Fix (P3)
- **Files:** `relational_store.py`
- **Scope:** Change timestamps from `REAL` epoch to `TEXT` ISO-8601 for microsecond precision.
- **RED:** Test that timestamps preserve milliseconds. Test that ordering is correct.
- **GREEN:** Change DDL: `created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`. Update all INSERT statements.
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_timestamps.py -v` — timestamps include milliseconds. Ordering correct.
- **Dependencies:** Unit 2
- **Notes:** Fixes L4 (timestamp precision).

### Unit 12: Full Integration Test (P4)
- **Files:** `tests/test_full_pipeline.py` (new)
- **Scope:** End-to-end test of full pipeline: SCOUT→PLAN→BUILD→COHESIVENESS_REVIEW→AGENT_VALIDATE→PENDING_REVIEW→HUMAN_GATE→INDEX→DONE. Verify all tables populated, enrichment runs, context router returns correct data.
- **RED:** Test fails because pipeline not fully integrated.
- **GREEN:** Run full pipeline with mock agents. Verify:
  - `workflow_runs` has correct phase/status
  - `state_executions` has correct outcomes/durations
  - `event_log` has all transitions
  - `artifacts` has all phase outputs
  - `artifact_summaries` has enrichment data
  - Context Router returns correct snapshot
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_full_pipeline.py -v` — all assertions pass. No crashes. All tables populated.
- **Dependencies:** Units 1-11
- **Notes:** Final integration test. Confirms all units work together.

---

## Execution Order

| Phase | Units | Effort | Dependencies |
|-------|-------|--------|-------------|
| **P0** | Unit 1 | 30 min | none |
| **P1** | Units 2, 3, 10 | 4 hours | Unit 2 → Unit 3 |
| **P2** | Units 4, 5 | 3 hours | Units 2, 3 |
| **P3** | Units 6, 7, 9, 11 | 6 hours | Units 2, 4 |
| **P4** | Units 8, 12 | 4 hours | Units 3, 4, 7 |

**Total estimated effort:** ~17 hours

---

## TDD Dispatch Pattern

For each unit:
1. Dispatch **worker** for RED phase → write failing test
2. Chair Gate → verify test FAILS
3. Dispatch **worker** for GREEN phase → minimal implementation
4. Chair Gate → verify test PASSES, diff scoped
5. Dispatch **worker** for REFACTOR phase → cleanup (if needed)
6. Chair Gate → verify no regressions
7. Dispatch **reviewer** (read-only) → quality check
8. Chair Gate → validate review output
9. Index artifacts → memsearch

**Sequential only** (VRAM thrashing with parallel).

---

## Self-Review Checklist

| Check | Status |
|-------|--------|
| Spec coverage | ✅ All 12 units cover report sections + triple review findings + Integrated State Architecture Spec |
| Placeholder scan | ✅ No TBDs, TODOs, or "figure out later" |
| Type consistency | ✅ Interfaces match across units (RelationalStore → ContextRouter → MicroModel) |
| Task boundaries | ✅ Each unit is 1-4 hours of focused work |
| Buildability | ✅ Each unit has specific file paths, RED/GREEN steps, verification criteria |
| i18n/locale | ✅ Timestamps use ISO-8601 UTC (Unit 11). No hard-coded locale assumptions. |

---

## Research-First Gate

| Unit | Research Needed | Status |
|------|----------------|--------|
| Unit 2 (SQLite schema) | SQLite WAL mode, PRAGMA foreign_keys | ✅ Verified: standard SQLite features |
| Unit 3 (Atomic writes) | SQLite BEGIN IMMEDIATE, COALESCE(MAX()) | ✅ Verified: standard SQLite patterns |
| Unit 4 (Context Router) | sqlite3.Row, parameterized queries | ✅ Verified: stdlib, no external deps |
| Unit 6 (State Linter) | DFS cycle detection algorithm | ✅ Verified: standard graph algorithm |
| Unit 8 (Micro-Model) | Async threading, post-commit triggers | ✅ Verified: `threading.Thread` or `queue.Queue` |

All units use stdlib or existing project dependencies. No external research needed.

---

## Operational Rules

1. **Sequential subagent dispatch only.** Parallel = VRAM thrashing = 503s.
2. **Chair Gate after every RED/GREEN/REFACTOR phase.** No exceptions.
3. **Bounded repair:** Max 3 repairs per unit. Escalate to human on failure.
4. **No silent changes.** Every edit must be in the plan.
5. **Fail fast.** If a unit blocks, stop and report. Don't continue unrelated work.

---

*Plan compiled 2026-05-20. Aligned with Integrated State Architecture Specification.*
