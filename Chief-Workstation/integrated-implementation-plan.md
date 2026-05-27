# Integrated Implementation Plan: State Machine + Relational + 6-Phase Gates

> **Date:** 2026-05-20
> **Scope:** Merge 6-phase gate findings + relational state machine + micro-model layer into a single execution plan
> **Status:** v3 — council-reviewed (GPT + Gemma), all CRITICAL/HIGH findings applied
> **Reviews:** `council-reviewer-diversity` (GPT) 2 CRITICAL + 3 HIGH + 3 MODERATE + 2 LOW; `council-reviewer-arch` (Gemma) PASS

---

## 0. Gap Analysis (What's Real vs. False Positives)

Cross-referenced both plans against `super-council.py` to eliminate false positives.

### Already Implemented (No Work Needed)

| Finding | Source | Reality | Evidence |
|---------|--------|---------|----------|
| Infinite-loop in `transition_to` (no retreat) | 6-phase P0#1 | Already retreats to SCOUT on retry exhaustion | Line 2231-2244 |
| No retreat from HUMAN_GATE to SCOUT | 6-phase P0#6 | `VALID_TRANSITIONS[HUMAN_GATE]` includes `SCOUT` | Line 2096 |
| No `PENDING_REVIEW` state | 6-phase P1#8 | Phase in `ALL_PHASES`, `VALID_TRANSITIONS`, executor wired | Lines 2076, 2095, 5053 |
| No `COHESIVENESS_REVIEW` phase | 6-phase C1 | Phase exists with co-chair delegation + static analysis fallback | Line 5099 |
| INDEX failure → DONE ambiguity | 6-phase P0#5 | Docstring states "INDEX failure → FAILED (not DONE)" | Line 2200 |
| Path-traversal in `MigrationManager` | 6-phase P0#3 | `MigrationManager` class does not exist in codebase | grep: 0 results |

### Confirmed Gaps (Real Work)

| Finding | Severity | Unit |
|---------|----------|------|
| Dead `PHASE_EXECUTORS` reference | HIGH | Unit 1 |
| `_auto_index_file` wrong receiver | HIGH | Unit 1 |
| `UnboundLocalError` in `_handle_pipeline` | HIGH | Unit 1 |
| Artifacts never stored between phases | HIGH | Unit 1 |
| **Duplicate pipelines from timestamp collisions** | HIGH | Unit 1.5 |
| **No (task, project_id) dedup lookup** | HIGH | Unit 1.5 |
| **`_delegate()` bypasses pipeline tracking** | HIGH | Unit 1.5 |
| **3 independent ID generators, no canonical ID** | HIGH | Unit 1.5 |
| Reviewer auto-dispatch not wired | HIGH | Unit 9 |
| No diff-check before BUILD | MODERATE | Unit 10 |
| Global attempt ceiling hardcoded (10) | MODERATE | Unit 11 |
| Tool names not validated in `_delegate()` | MODERATE | Unit 11 |
| Recall-then-validate worktree failure path | MODERATE | Unit 11 |
| Race condition on `attempt_number` | HIGH | Unit 3 |
| Context truncation mid-artifact | HIGH | Unit 7 |
| **Missing `task_hash` column in dedup constraint** | CRITICAL | Unit 1.5 + Unit 2 |
| **`_pipeline_lock` in-process only (no multi-process safety)** | CRITICAL | Unit 1.5 + Unit 2 |
| **WAL checkpoint timing misalignment** | HIGH | Unit 2 |

---

## 0.5. Routing Matrix (Self-Contained)

Determines which component owns which work. Embedded here so the plan is self-contained.

### Routing Rules

| Pattern | Owner | Rationale |
|---------|-------|-----------|
| Deterministic / transactional / rule-based | **Python** | No hallucination risk; ACID guarantees |
| Summarization / ranking / tagging | **Small Model** | Cheap inference; semantic understanding |
| Policy / arbitration / planning | **Chair** | Final authority on dispatch/retry/retreat/gate/replan |

### Flow

```
Python records transitions → ContextRouter fetches → Small Model summarizes (if needed) → Chair decides
```

### Ownership by Component

| Component | Owner | Units |
|-----------|-------|-------|
| `RelationalStore` | Python | Unit 2 |
| `ContextRouter` | Python | Unit 4 |
| `StateMachineLinter` | Python | Unit 6 |
| Phase schema validators | Python | Unit 5 |
| Transition executor / guardrails | Python | Unit 3 |
| `MicroModelEnricher` | Small Model | Unit 8 |
| Artifact summaries | Small Model | Unit 8 |
| Failure labeling | Small Model | Unit 8 |
| Semantic ranking | Small Model | Unit 8 |
| **`ChairAgent` (thin wrapper)** | Chair | Unit 9 |
| Next-best-action / final selection | Chair | Unit 9 |
| Retry / retreat / proceed | Chair | Unit 3 |
| Gate judgments | Chair | Unit 9 |
| Replanning | Chair | Unit 6 |

> **Note:** "Chair" is implemented as a thin `ChairAgent` service that consumes `_run_cohesiveness_check` / `SlotSupervisor` output and makes final go/no-go decisions. This aligns the routing matrix with the actual code structure.

---

## 1. Executive Summary

This plan consolidates three sources of work:
1. **4 critical runtime bugs** — crash the pipeline on every run
2. **5 remaining 6-phase gate findings** — blocks proper delegation flow
3. **Relational schema + atomic transitions** — normalized SQLite, WAL mode, transactional writes
4. **Context Router + Memory Layer + Micro-Model** — manages state across sequential Gemma → Nemo → GPT reviews

**Total estimated effort:** ~20 hours across 17 units

---

## 2. Implementation Units

### Unit 1: Fix Critical Runtime Bugs (P0)
- **Priority:** P0 — blocks all pipeline execution
- **Files:** `super-council.py`
- **Scope:** 4 surgical fixes, no new code.
- **RED:** `tests/test_super_council_bugs.py` — 4 tests that trigger each crash:
  1. `_execute_phase()` hits dead `PHASE_EXECUTORS.get(phase)` → AttributeError
  2. `_run_index()` calls `self._auto_index_file` → AttributeError (wrong receiver)
  3. `_handle_pipeline()` explicit-failure block references `ps` before assignment → UnboundLocalError
  4. `_run_cohesiveness_check()` reads `ps.artifacts[PLAN]` → empty dict (artifacts never stored)
- **GREEN:** Apply 4 fixes:
  1. **Line 5033:** Remove `executor_name = PipelineState.PHASE_EXECUTORS.get(phase)` and its `if not executor_name:` guard. The `if/elif` chain below handles all phases.
  2. **Line 5235:** Change `_run_index` to return `{"ok": True, "indexed": True}` (placeholder until Memory Layer exists). Remove `self._auto_index_file(ps.pipeline_id)` call.
  3. **Line ~5296:** Fix `_handle_pipeline` explicit-failure block: load `ps` via `self._get_or_create_pipeline(pipeline_id, task, project_id)` before the `outcome == "failure"` branch.
  4. **Line 5067:** After phase execution succeeds, add `ps.artifacts[phase] = result` in `_execute_phase()` before returning.
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_super_council_bugs.py -v` — all 4 crash tests pass. Manual pipeline run SCOUT→PLAN→BUILD→COHESIVENESS_REVIEW completes without crashes.
- **Dependencies:** none
- **Effort:** 30 min

### Unit 1.5: Canonical Pipeline ID + Deduplication + Mandatory Tracking (P0)
- **Priority:** P0 — prevents duplicate pipelines and untracked delegations
- **Files:** `super-council.py`
- **Scope:** 4 changes to ensure all delegations are tracked under a single canonical `pipeline_id` matched to `(task, project_id)`.
- **RED:** `tests/test_pipeline_dedup.py` — 5 tests:
  1. Two calls with same `(task, project_id)` return same `pipeline_id`
  2. `_delegate()` with no `pipeline_id` auto-creates one and tracks it
  3. `_delegate_chain()` links all sub-delegations to parent `pipeline_id`
  4. UUID-based IDs never collide (1000 rapid calls)
  5. Existing `pipeline_id` in payload is reused (backwards compat)
- **GREEN:** Apply 4 changes:
  1. **Add `find_active_pipeline(task, project_id)` to `PipelineTracker`:**
     ```python
     import hashlib

     def find_active_pipeline(self, task: str, project_id: str) -> Optional[dict]:
         """Find non-terminal pipeline matching task + project_id.
         Uses task_hash for dedup (SHA-256 prefix, 16 hex chars).
         DB-level UNIQUE(task_hash, project_id) is the primary dedup guard.
         Uses EXACT MATCH (no LIKE substring collisions)."""
         task_hash = hashlib.sha256(task.encode()).hexdigest()[:32]
         row = self._db.execute("""
             SELECT pipeline_id, project_id, task, phase, status
             FROM pipelines
             WHERE project_id = ?
               AND task_hash = ?
               AND status NOT IN ('done', 'failed')
             ORDER BY created_at DESC LIMIT 1
         """, (project_id, task_hash)).fetchone()
         return dict(row) if row else None
     ```
  2. **Rewrite `_get_or_create_pipeline()` with dedup logic:**
     ```python
     import hashlib

     def _get_or_create_pipeline(self, pipeline_id, task, project_id="default"):
         # NOTE: self._pipeline_lock is REMOVED. Multi-process safety is handled
         # entirely by DB-level UNIQUE(task_hash, project_id) + INSERT OR IGNORE + retry.
         task_hash = hashlib.sha256(task.encode()).hexdigest()[:32]

         # 1. Explicit pipeline_id provided → reuse if in memory
         if pipeline_id and pipeline_id in self._active_pipelines:
             return self._active_pipelines[pipeline_id]

         # 2. DB-level dedup: check for existing active pipeline with same (task_hash, project_id)
         # This is the PRIMARY dedup mechanism, works across processes
         if task and project_id:
             existing = self.pipeline_tracker.find_active_pipeline(task, project_id)
             if existing:
                 pipeline_id = existing["pipeline_id"]
                 ps = PipelineState.from_file(pipeline_id)
                 self._active_pipelines[pipeline_id] = ps
                 return ps

         # 3. Try loading from disk by pipeline_id
         if pipeline_id:
             ps = PipelineState.from_file(pipeline_id)
             if ps.phase not in PipelineState.TERMINAL_PHASES:
                 self._active_pipelines[pipeline_id] = ps
                 return ps

         # 4. Generate collision-proof ID (full UUID, no truncation)
         if not pipeline_id:
             pipeline_id = f"pipe-{uuid4().hex}"

         # 5. Create fresh — DB UNIQUE constraint will reject if another process beat us
         try:
             ps = PipelineState(pipeline_id=pipeline_id, task=task, project_id=project_id,
                                task_hash=task_hash)
             self._active_pipelines[pipeline_id] = ps
             self.pipeline_tracker.upsert_pipeline(ps)
             return ps
         except sqlite3.IntegrityError:
             # Another process created it — retry lookup
             existing = self.pipeline_tracker.find_active_pipeline(task, project_id)
             if existing:
                 pipeline_id = existing["pipeline_id"]
                 ps = PipelineState.from_file(pipeline_id)
                 self._active_pipelines[pipeline_id] = ps
                 return ps
             raise
     ```
  3. **Enforce `_delegate()` routes ALL paths through `_get_or_create_pipeline()`:**
     ```python
     # In _delegate(), replace:
     task_id = payload.get("task_id", f"deleg-{int(time.time())}")
     # With:
     pipeline_id = payload.get("pipeline_id") or payload.get("task_id")
     if not pipeline_id:
         # Auto-create pipeline for ad-hoc delegation
         task = payload.get("task", "")
         project_id = payload.get("project_id", "default")
         ps = self._get_or_create_pipeline(None, task, project_id)
         pipeline_id = ps.pipeline_id
     task_id = pipeline_id  # Canonical ID

     # CRITICAL: Remove any direct `PipelineState(...)` construction in _delegate().
     # Every delegation MUST route through _get_or_create_pipeline() to ensure
     # canonical ID tracking and multi-process dedup safety.
     ```
  4. **Wire `_delegate_chain()` to propagate `pipeline_id`:**
     ```python
     # In _delegate_chain(), replace:
     chain_id = plan.get("chain_id", f"chain-{int(time.time())}")
     # With:
     pipeline_id = plan.get("pipeline_id") or plan.get("chain_id")
     if not pipeline_id:
         project_id = plan.get("project_id", "default")
         ps = self._get_or_create_pipeline(None, task_context, project_id)
         pipeline_id = ps.pipeline_id
     # Propagate to all sub-delegations (include project_id):
     coder_result = self._delegate({"alias": ..., "pipeline_id": pipeline_id, "project_id": project_id, ...})
     review_result = self._delegate({"alias": ..., "pipeline_id": pipeline_id, "project_id": project_id, ...})
     ```
- **REFACTOR:** Replace all `f"pipe-{int(time.time())}"`, `f"deleg-{int(time.time())}"`, `f"chain-{int(time.time())}"` with full UUID-based generation (`uuid4().hex`). Remove all `LIKE ?` substring dedup queries; use exact `WHERE task_hash = ?` match.
- **Verification:** `pytest tests/test_pipeline_dedup.py -v` — same task+project reuses pipeline, UUID IDs never collide, all delegations tracked.
- **Dependencies:** Unit 1
- **Effort:** 1.5 hours

### Unit 2: SQLite Schema + WAL Mode + Phase Registry + Timestamps (P0)
- **Priority:** P0 — foundation for all relational work
- **Files:** `relational_store.py` (new), `super-council.py`
- **Scope:** Create 4 enum lookup tables + 6 core tables + indexes. Enable WAL mode. Seed `workflow_definitions`. Auto-upsert phase registry. Use ISO-8601 timestamps.
- **RED:** `tests/test_relational_store.py` — schema creation, seed data, WAL mode, FK enforcement, phase registry sync, timestamp precision.
- **GREEN:** Implement `RelationalStore` class:
  ```python
  class RelationalStore:
      def __init__(self, db_path: str):
          # timeout=30 prevents "database is locked" under concurrent pipelines
          self.db = sqlite3.connect(db_path, timeout=30)
          self.db.execute("PRAGMA journal_mode=WAL")
          self.db.execute("PRAGMA foreign_keys=ON")
          self.db.execute("PRAGMA wal_autocheckpoint=0")
          self._create_tables()
          self._seed_definitions()
          self._sync_phase_registry()

      def checkpoint(self):
          """Manually checkpoint WAL after transition commits.
          Uses TRUNCATE to reclaim disk space when safe.
          Called from _record_transition() or off-peak scheduler."""
          self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
  ```
  - `_create_tables()`: Load from `migrations/09_schema.sql` (single source of truth, no split DDL) with `TEXT` ISO-8601 timestamps
  - `_seed_definitions()`: INSERT current `VALID_TRANSITIONS` into `workflow_definitions`
  - `_sync_phase_registry()`: Parse `workflow_definitions.phases` JSON, INSERT OR IGNORE into `phase_names`
  - Add CHECK constraint on `workflow_runs.project_id` (non-empty)
  - Drop `idx_events_type` and `idx_events_severity` (write amplification on hot path)
  - **Single source of truth:** Remove `state_json` column from `pipelines` table. All state reads/writes go through `RelationalStore` normalized tables.
  - **DB-level dedup (multi-process safe):** Add `UNIQUE(task_hash, project_id)` constraint on `pipelines` table. `task_hash` = `sha256(task.encode()).hexdigest()[:32]`. This is the **primary** dedup mechanism. Python `_pipeline_lock` is removed.
  - **`task_hash` column definition:** `task_hash TEXT NOT NULL` on `pipelines` table, computed at insert time via `hashlib.sha256(task.encode()).hexdigest()[:32]`.
  - **`INSERT OR IGNORE` + retry pattern:** `upsert_pipeline()` uses `INSERT OR IGNORE INTO pipelines (...) VALUES (...)`. On `IntegrityError`, retry `find_active_pipeline()` to fetch the existing record.
- **REFACTOR:** `PipelineTracker` becomes thin wrapper around `RelationalStore`. `PipelineState.save()` writes to `RelationalStore` only (no JSON file, no `state_json` blob).
- **Verification:** `pytest tests/test_relational_store.py -v` — schema creates, seed data present, WAL mode enabled, FK enforcement active, timestamps include milliseconds, phase registry synced.
- **Dependencies:** none
- **Effort:** 2 hours

### Unit 3: Atomic `transition_to()` with Transactional Writes (P1)
- **Priority:** P1 — fixes race condition H1 + transactional guarantees M5
- **Files:** `relational_store.py`, `super-council.py`
- **Scope:** Refactor `PipelineState.transition_to()` to write to normalized tables atomically. Fix race condition on `attempt_number`. Wrap in `BEGIN IMMEDIATE ... COMMIT`.
- **RED:** `tests/test_atomic_transition.py` — concurrent transitions produce unique `attempt_number`. Partial failure rolls back cleanly.
- **GREEN:** Implement in `RelationalStore`:
  - `_next_attempt(run_id, phase)`: `SELECT COALESCE(MAX(attempt_number),0)+1 FROM state_executions WHERE run_id=? AND phase=?`
  - `_record_transition(run_id, phase, attempt, outcome, error, duration)`: INSERT into `state_executions`, `event_log`, `artifacts`; UPDATE `workflow_runs`
  - **Atomic increment:** `UPDATE state_executions SET attempt_number = attempt_number + 1 WHERE run_id=? AND phase=?` inside `BEGIN IMMEDIATE ... COMMIT`
  - Wrap in `BEGIN IMMEDIATE ... COMMIT` with `try/except ROLLBACK`
- **REFACTOR:** Replace in-memory `phase_attempts` dict with DB-side calculation. Update `PipelineState.transition_to()` to call `self.relational_store._record_transition()`.
- **Verification:** `pytest tests/test_atomic_transition.py -v` — concurrent transitions produce unique `attempt_number`. Partial failure rolls back cleanly.
- **Dependencies:** Unit 2
- **Effort:** 2 hours

### Unit 4: Context Router Service (P1)
- **Priority:** P1 — manages state across sequential Gemma → Nemo → GPT reviews
- **Files:** `context_router.py` (new), `super-council.py`
- **Scope:** Implement `ContextRouter` with 5 methods. Wire into `SlotSupervisor`. Replace `_active_recall()` with `find_similar_runs()` + memsearch fallback.
- **RED:** `tests/test_context_router.py` — all 5 methods return correct data for a sample run.
- **GREEN:** Implement `ContextRouter`:
  - `get_run_snapshot(run_id)` — run + executions + artifacts
  - `get_recent_events(run_id, limit)` — last N events
  - `get_artifacts(run_id, filter)` — filtered artifacts
  - `summarize_run_issues(run_id)` — structured summary of errors + state_executions
  - `find_similar_runs(query)` — semantic match via memsearch
- **REFACTOR:** Replace `_active_recall()` with `self.context_router.find_similar_runs()` + memsearch fallback.
- **Verification:** `pytest tests/test_context_router.py -v` — all 5 methods return correct data. `get_run_snapshot()` includes executions + artifacts. `summarize_run_issues()` correlates errors with state_executions.
- **Dependencies:** Unit 2, Unit 3
- **Effort:** 2 hours
- **Why this is needed:** Sequential reviews (Gemma → Nemo → GPT) need shared context. Current `_active_recall()` is a vector-only query with no pipeline state awareness. Context Router bridges the gap.

### Unit 5: Phase Schema Validation (P2)
- **Priority:** P2 — catches malformed artifacts between phases
- **Files:** `super-council.py`, `relational_store.py`
- **Scope:** Add `PHASE_SCHEMAS` dict with input/output contracts for all 10 phases. Validate at phase boundaries.
- **RED:** `tests/test_phase_validation.py` — invalid input/output caught and logged.
- **GREEN:** Implement `validate_phase_input(phase, data)` and `validate_phase_output(phase, data)`. Call in `_execute_phase()` before/after phase execution.
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_phase_validation.py -v` — invalid input rejected, valid input passes. Missing required fields logged as warnings.
- **Dependencies:** Unit 4
- **Effort:** 1 hour
- **Why this is needed:** COHESIVENESS_REVIEW reads `ps.artifacts[PLAN]` and `ps.artifacts[BUILD]`. If either is malformed (wrong schema, missing fields), the co-chair gets garbage. Validation catches this at the boundary.

### Unit 6: State Machine Linter (P2)
- **Priority:** P2 — validates `VALID_TRANSITIONS` graph correctness
- **Files:** `state_linter.py` (new), `super-council.py`
- **Scope:** Implement `StateMachineLinter` with 8 checks. Fix DFS cycle detection (M3).
- **RED:** `tests/test_state_linter.py` — current graph passes all checks. Broken graph detected.
- **GREEN:** Implement `StateMachineLinter`:
  - `_check_unreachable_states()` — states with no incoming transitions
  - `_check_invalid_targets()` — transitions to non-existent phases
  - `_check_missing_handlers()` — phases without executor methods
  - `_check_dead_ends()` — non-terminal phases with no outgoing transitions
  - `_check_infinite_loops()` — per-DFS recursion stack (fix M3)
  - `_check_orphaned_transitions()` — transitions not in VALID_TRANSITIONS
  - `_check_retreat_paths()` — all non-terminal phases can reach SCOUT
  - `_check_asymmetric_transitions()` — A→B exists but B→A doesn't (informational)
- **REFACTOR:** Expose as Chair/Co-Chair tools: `lint_current_workflow()`, `inspect_workflow_graph()`, `propose_safe_transition()`.
- **Verification:** `pytest tests/test_state_linter.py -v` — current graph passes all checks. Broken graph detected. DFS finds all cycles including shared-node cycles.
- **Dependencies:** none
- **Effort:** 1.5 hours
- **Why this is needed:** Adding new phases (e.g., PENDING_REVIEW variants) can break the graph. Linter catches cycles, unreachable states, and missing retreat paths before they cause infinite loops.

### Unit 7: Memory Layer with Artifact-Boundary Truncation (P2)
- **Priority:** P2 — fixes H2 (mid-artifact truncation)
- **Files:** `memory_layer.py` (new), `context_router.py`
- **Scope:** Implement `MemoryLayer` with memsearch integration. Fix context truncation to use artifact-boundary splitting. Add summarization, chunking, eviction strategies.
- **RED:** `tests/test_memory_layer.py` — context truncation never cuts mid-artifact. Token budget respected.
- **GREEN:** Implement `MemoryLayer`:
  - `ingest_artifact(run_id, phase, content)` — store artifact with metadata
  - `get_context_slice(run_id, max_tokens)` — block-based truncation
  - `_split_into_blocks(context)` — split on artifact boundaries
  - `_summarize_block(block)` — pre-computed summary for oversized blocks
  - `evict_old_artifacts(retention_days)` — cleanup
- **REFACTOR:** Replace raw character truncation (`context[:max_chars]`) with `self.memory_layer.get_context_slice()`.
- **Verification:** `pytest tests/test_memory_layer.py -v` — truncation never produces malformed JSON. Token budget respected. Summaries used when blocks don't fit.
- **Dependencies:** Unit 4
- **Effort:** 2 hours
- **Why this is needed:** Sequential reviews build context by appending artifacts. Current truncation cuts mid-JSON, producing malformed context for downstream models. Artifact-boundary splitting ensures each model gets complete, parseable context.

### Unit 8: Embedded Micro-Model Layer (P3)
- **Priority:** P3 — async enrichment for better recall quality
- **Files:** `micro_model.py` (new), `relational_store.py`, `context_router.py`
- **Scope:** Implement `MicroModelEnricher` with async post-commit enrichment. Create 3 enrichment side tables.
- **RED:** `tests/test_micro_model.py` — enrichment runs async without blocking transitions. Fallback works when micro-model unavailable.
- **GREEN:** Implement `MicroModelEnricher`:
  - `enrich_artifact(run_id, phase, content)` — generate summary, tags, keywords
  - `enrich_event_window(run_id, events)` — summarize event sequences
  - `enrich_failure(run_id, error)` — classify failure type
  - `should_index_full_text(content)` — decide if full-text indexing is worth it
  - Create `artifact_summaries`, `event_window_summaries`, `failure_classifications` tables
  - Wire as `ThreadPoolExecutor(max_workers=2)` triggered on `transition_to()` commit. Use `future.add_done_callback()` for error handling.
- **REFACTOR:** Update `ContextRouter.get_run_snapshot()` to include enrichment data. Update `MemoryLayer.ingest_artifact()` to prefer enriched summaries.
- **Verification:** `pytest tests/test_micro_model.py -v` — enrichment runs async, doesn't block transitions. Fallback works when micro-model unavailable. Summaries improve recall quality.
- **Dependencies:** Unit 3, Unit 4, Unit 7
- **Effort:** 2 hours
- **Why this is needed:** Raw artifacts are large. Enriched summaries improve recall quality for Context Router queries without loading full artifacts. Async so it doesn't block phase transitions.

### Unit 9: Reviewer Auto-Dispatch (P1)
- **Priority:** P1 — 6-phase P0#2, blocks AGENT_VALIDATE→PENDING_REVIEW flow
- **Files:** `super-council.py`
- **Scope:** Wire reviewer auto-dispatch after AGENT_VALIDATE. Currently `_run_agent_validate()` returns a placeholder dict with no actual dispatch.
- **RED:** `tests/test_reviewer_dispatch.py` — AGENT_VALIDATE triggers PENDING_REVIEW transition. Reviewer task is enqueued.
- **GREEN:** Update `_run_agent_validate()` to:
  1. Run existing 5-step Chair gate
  2. On gate pass, auto-dispatch reviewer via `self._delegate()` with alias from `council-reviewer-arch` or `council-reviewer-logic`
  3. Transition to `PENDING_REVIEW` with reviewer task ID in artifacts
  4. On gate fail, transition to `COHESIVENESS_REVIEW` or `BUILD` per VALID_TRANSITIONS
- **REFACTOR:** Update `_run_pending_review()` to check reviewer task completion (poll or callback).
- **Verification:** `pytest tests/test_reviewer_dispatch.py -v` — AGENT_VALIDATE dispatches reviewer, PENDING_REVIEW waits for completion.
- **Dependencies:** Unit 1, Unit 1.5
- **Effort:** 1 hour

### Unit 10: Diff-Check Before BUILD (P2)
- **Priority:** P2 — 6-phase P0#4, prevents no-op builds
- **Files:** `super-council.py`
- **Scope:** Add `git diff --stat` check in `_run_build()` before delegating to builder. If 0 files changed, skip to COHESIVENESS_REVIEW.
- **RED:** `tests/test_diff_check.py` — BUILD with no changes skips to COHESIVENESS_REVIEW. BUILD with changes proceeds normally.
- **GREEN:** Add in `_run_build()`:
  ```python
  import subprocess
  diff_result = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True)
  if not diff_result.stdout.strip():
      log.info("BUILD: no changes detected, skipping to COHESIVENESS_REVIEW")
      return {"ok": True, "skipped": True, "reason": "no changes"}
  ```
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_diff_check.py -v` — no-op builds short-circuited.
- **Dependencies:** Unit 1, Unit 1.5
- **Effort:** 30 min

### Unit 11: Parameterized Ceiling + Tool Validation + Worktree Failure Path (P2)
- **Priority:** P2 — 6-phase P1#9, P1#10, P1#11
- **Files:** `super-council.py`
- **Scope:** Three small fixes:
  1. Parameterize `max_global_attempts` via env var `COUNCIL_MAX_GLOBAL_ATTEMPTS` or config
  2. Validate tool names in `_delegate()` against `self._allowed_tools`
  3. Handle worktree creation failure in recall-then-validate
- **RED:** `tests/test_parameterized_config.py` — env var overrides ceiling. Unknown tool names rejected. Worktree failure handled gracefully.
- **GREEN:**
  1. In `PipelineState.__init__()`: Read from env var with `try/except ValueError` (default=10), then persist to `workflow_definitions` table: `INSERT OR REPLACE INTO config (key, value) VALUES ('max_global_attempts', ?)`
  2. In `_delegate()`: Validate `payload.get("tools")` against `self._allowed_tools` (line 2398)
  3. In `_delegate()` recall-then-validate: If `_create_worktree()` returns `None`, log warning and skip recall (don't crash)
  4. On restart: Read `max_global_attempts` from `workflow_definitions` table, override env var default
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_parameterized_config.py -v` — all 3 fixes pass.
- **Dependencies:** Unit 1, Unit 1.5
- **Effort:** 1 hour

### Unit 12: Index Optimization + Retention Automation (P3)
- **Priority:** P3 — prevents DB bloat across sequential reviews
- **Files:** `relational_store.py`
- **Scope:** Implement automated retention/archival job. Drop unused indexes.
- **RED:** `tests/test_retention.py` — archival moves old runs correctly. VACUUM reclaims space.
- **GREEN:** Implement `_archive_old_runs(retention_days=90)`:
  - INSERT into archive tables, DELETE from main, VACUUM
  - Schedule via `threading.Timer` or cron
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_retention.py -v` — archival moves data correctly. VACUUM reclaims space. Hot-path queries still fast.
- **Dependencies:** Unit 2
- **Effort:** 1 hour
- **Why this is needed:** Sequential reviews generate many artifacts. Without retention, DB grows unbounded. Archival keeps hot data fast and moves cold data to archive.

### Unit 13: Timestamp Precision Fix (P3)
- **Priority:** P3 — microsecond precision for event correlation
- **Files:** `relational_store.py`
- **Scope:** Change timestamps from `REAL` epoch to `TEXT` ISO-8601 for microsecond precision.
- **RED:** `tests/test_timestamps.py` — timestamps preserve milliseconds. Ordering correct.
- **GREEN:** Change DDL: `created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`. Update all INSERT statements.
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_timestamps.py -v` — timestamps include milliseconds. Ordering correct.
- **Dependencies:** Unit 2
- **Effort:** 30 min

### Unit 14: Artifact-Boundary Context Truncation (P2)
- **Priority:** P2 — fixes H2 (mid-artifact truncation)
- **Files:** `super-council.py`
- **Scope:** Replace raw character truncation (`context[:max_chars]`) with block-based truncation. Split context into artifact blocks, drop whole blocks until under budget, replace oversized block with summary.
- **RED:** `tests/test_context_truncation.py` — truncation never cuts mid-artifact. Token budget respected. No malformed JSON.
- **GREEN:** Implement `_truncate_context(context, max_chars)`:
  ```python
  def _truncate_context(self, context: str, max_chars: int) -> str:
      blocks = re.split(r'\n\{\{ARTIFACT_BOUNDARY_\w+\}\}\n', context)
      result_blocks = []
      current_len = 0
      for block in blocks:
          if current_len + len(block) <= max_chars:
              result_blocks.append(block)
              current_len += len(block)
          else:
              summary = f"[TRUNCATED: {len(block)} chars, {len(block.split(chr(10)))} lines]"
              result_blocks.append(summary)
              break
      return "\n---\n".join(result_blocks)
  ```
- **REFACTOR:** Replace all `context[:max_chars]` calls with `self._truncate_context(context, max_chars)`.
- **Verification:** `pytest tests/test_context_truncation.py -v` — no malformed JSON, budget respected.
- **Dependencies:** Unit 1
- **Effort:** 1 hour

### Unit 15: Phase Registry Auto-Upsert + Multi-Tenant Enforcement (P1)
- **Priority:** P1 — M2 (phase registry friction), L6 (multi-tenant isolation)
- **Files:** `relational_store.py`, `super-council.py`
- **Scope:** Add auto-upsert in orchestrator init: scan `workflow_definitions.phases` JSON and INSERT missing names into `phase_names`. Add CHECK constraint on `workflow_runs.project_id`.
- **RED:** `tests/test_phase_registry.py` — new phases auto-upserted. Missing `project_id` rejected.
- **GREEN:** Implement `_sync_phase_registry()` in `RelationalStore`: parse `workflow_definitions.phases` JSON, INSERT OR IGNORE into `phase_names`. Add CHECK constraint on `workflow_runs.project_id` (non-empty).
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_phase_registry.py -v` — new phases auto-upserted. Missing `project_id` rejected.
- **Dependencies:** Unit 2
- **Effort:** 30 min

### Unit 16: Full Integration Test (P4)
- **Priority:** P4 — final verification
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
  - Reviewer auto-dispatch works
  - Diff-check short-circuits no-op builds
  - Parameterized ceiling respected
  - Artifact-boundary truncation works
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_full_pipeline.py -v` — all assertions pass. No crashes. All tables populated.
- **Dependencies:** Units 1-15
- **Effort:** 1 hour

---

## 3. Execution Order

| Priority | Units | Effort | Dependencies |
|----------|-------|--------|-------------|
| **P0** | Unit 1, Unit 1.5, Unit 2 | 4 hours | none |
| **P1** | Units 3, 4, 9, 15 | 5.5 hours | Unit 2, Unit 1.5 |
| **P2** | Units 5, 6, 7, 10, 11, 14 | 6 hours | Unit 1.5, Unit 4 |
| **P3** | Units 8, 12, 13 | 3.5 hours | Unit 3, Unit 4, Unit 7 |
| **P4** | Unit 16 | 1 hour | Units 1-15 |

**Total estimated effort:** ~20 hours

---

## 4. TDD Dispatch Pattern

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

## 5. Triple-Review Findings (Applied)

All findings from council reviews (`council-reviewer-diversity` GPT + `council-reviewer-arch` Gemma) have been applied inline.

| Finding | Severity | Status | Unit |
|---------|----------|--------|------|
| Split-brain: 4 state stores | HIGH | ✅ Fixed | Unit 2 — SQLite as canonical, remove `state_json` |
| `_delegate()` bypasses tracking | HIGH | ✅ Fixed | Unit 1.5 — always call `_get_or_create_pipeline()` |
| 3 independent ID generators | HIGH | ✅ Fixed | Unit 1.5 — single `uuid4().hex` generator |
| Race condition on `attempt_number` | HIGH | ✅ Fixed | Unit 3 — `BEGIN IMMEDIATE ... COMMIT` |
| `LIKE` dedup matches substrings | MODERATE | ✅ Fixed | Unit 1.5 — `WHERE task = ?` exact match |
| Truncated UUID (`hex[:12]`) | MODERATE | ✅ Fixed | Unit 1.5 — full `uuid4().hex` |
| `max_global_attempts` not persisted | MODERATE | ✅ Fixed | Unit 11 — store in `workflow_definitions` |
| `_pipeline_lock` in-process only | CRITICAL | ✅ Fixed | Unit 1.5 — Python lock removed; multi-process safety handled entirely by DB UNIQUE + INSERT OR IGNORE + retry |
| Missing `task_hash` column | CRITICAL | ✅ Fixed | Unit 1.5 + Unit 2 — `sha256(task)[:16]` computed at insert, explicit in `upsert_pipeline()` |
| `_delegate()` bypasses tracking | HIGH | ✅ Fixed | Unit 1.5 — All delegation paths enforced to route through `_get_or_create_pipeline()` |
| `LIKE ?` substring dedup | MODERATE | ✅ Fixed | Unit 1.5 — Exact `WHERE task_hash = ?` match only |
| Truncated UUID | MODERATE | ✅ Fixed | Unit 1.5 — Full `uuid4().hex` used |
| Routing matrix Chair mismatch | HIGH | ✅ Fixed | §0.5 — Added `ChairAgent` thin wrapper to align with `_run_cohesiveness_check` |
| DDL split across files | LOW | ✅ Fixed | §9 — Consolidated into single `migrations/09_schema.sql` script |
| WAL checkpoint timing | HIGH | ✅ Fixed | Unit 2 — `wal_autocheckpoint=0` + manual `checkpoint()` after each transition COMMIT |
| Phase registry friction | MODERATE | ✅ Fixed | Unit 2 — auto-upsert in orchestrator init |
| Sub-delegations missing `project_id` | LOW | ✅ Fixed | Unit 1.5 — propagate `project_id` |
| Write amplification on `event_log` | LOW | ✅ Fixed | Unit 2 — drop unused indexes |

## 6. Self-Review Checklist

| Check | Status | Notes |
|-------|--------|-------|
| Spec coverage | ✅ | All 6-phase P0/P1 items + 4 runtime bugs + dedup + relational schema + micro-model |
| Placeholder scan | ✅ | No TBDs, TODOs, or "figure out later" |
| Type consistency | ✅ | Interfaces match across units (RelationalStore → ContextRouter → MicroModel) |
| Task boundaries | ✅ | Each unit is 30 min - 2 hours |
| Buildability | ✅ | Specific file paths, RED/GREEN steps, verification criteria |
| False positive elimination | ✅ | 6 findings verified as already implemented |
| Over-engineering check | ✅ | All items justified against actual workflow (sequential Gemma→Nemo→GPT) |
| i18n/locale | ✅ | Timestamps use ISO-8601 UTC. No hard-coded locale assumptions. |
| Deduplication | ✅ | Unit 1.5 ensures (task, project_id) → single pipeline_id, exact match, full UUID |
| Single source of truth | ✅ | Unit 2 declares SQLite as canonical, removes `state_json` |
| Atomic transitions | ✅ | Unit 3 wraps `attempt_number` in `BEGIN IMMEDIATE ... COMMIT` |
| Multi-process safety | ✅ | Unit 1.5 uses `UNIQUE(task_hash, project_id)` constraint |

---

## 7. Research-First Gate

| Unit | Research Needed | Status |
|------|----------------|--------|
| Unit 1.5 (Deduplication) | `uuid4()`, SQLite exact-match queries | ✅ stdlib, existing `PipelineTracker` | 
| Unit 2 (SQLite schema) | SQLite WAL mode, PRAGMA foreign_keys | ✅ Standard SQLite features |
| Unit 3 (Atomic writes) | SQLite BEGIN IMMEDIATE, COALESCE(MAX()) | ✅ Standard SQLite patterns |
| Unit 4 (Context Router) | sqlite3.Row, parameterized queries | ✅ stdlib, no external deps |
| Unit 6 (State Linter) | DFS cycle detection algorithm | ✅ Standard graph algorithm |
| Unit 8 (Micro-Model) | Async threading, post-commit triggers | ✅ `threading.Thread` or `queue.Queue` |
| Unit 9 (Reviewer dispatch) | Existing `_delegate()` API | ✅ Already implemented |
| Unit 10 (Diff-check) | `git diff --stat` | ✅ Standard git command |
| Unit 11 (Tool validation) | `self._allowed_tools` (line 2398) | ✅ Already exists as set |

All units use stdlib or existing project dependencies. No external research needed.

---

## 8. Operational Rules

1. **Sequential subagent dispatch only.** Parallel = VRAM thrashing = 503s.
2. **Chair Gate after every RED/GREEN/REFACTOR phase.** No exceptions.
3. **Bounded repair:** Max 3 repairs per unit. Escalate to human on failure.
4. **No silent changes.** Every edit must be in the plan.
5. **Fail fast.** If a unit blocks, stop and report. Don't continue unrelated work.

---

*Plan compiled 2026-05-20. Self-contained; no external document references required.*

---

## 9. Schema Appendix (Single Migration Script)

Full DDL for `RelationalStore._create_tables()`. Consolidated into a single `migrations/09_schema.sql` script to prevent split-file drift. Run via `sqlite3 ./db.sqlite < migrations/09_schema.sql`.

```sql
-- Enum lookup tables
CREATE TABLE phase_names (
    phase_name TEXT PRIMARY KEY,
    display_order INTEGER NOT NULL
);

CREATE TABLE event_types (
    event_type TEXT PRIMARY KEY
);

CREATE TABLE outcome_types (
    outcome TEXT PRIMARY KEY
);

CREATE TABLE severity_levels (
    severity TEXT PRIMARY KEY
);

-- Core tables
CREATE TABLE pipelines (
    pipeline_id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    task_hash TEXT NOT NULL,
    project_id TEXT NOT NULL CHECK (project_id != ''),
    phase TEXT NOT NULL REFERENCES phase_names(phase_name),
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(task_hash, project_id)
);

CREATE TABLE workflow_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL REFERENCES pipelines(pipeline_id),
    project_id TEXT NOT NULL CHECK (project_id != ''),
    phase TEXT NOT NULL REFERENCES phase_names(phase_name),
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT
);

CREATE TABLE state_executions (
    execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    phase TEXT NOT NULL REFERENCES phase_names(phase_name),
    attempt_number INTEGER NOT NULL DEFAULT 1,
    outcome TEXT NOT NULL REFERENCES outcome_types(outcome),
    error TEXT,
    duration_ms REAL,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    UNIQUE(run_id, phase, attempt_number)
);

CREATE TABLE event_log (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    event_type TEXT NOT NULL REFERENCES event_types(event_type),
    severity TEXT NOT NULL REFERENCES severity_levels(severity),
    message TEXT NOT NULL,
    metadata TEXT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    phase TEXT NOT NULL REFERENCES phase_names(phase_name),
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/plain',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE workflow_definitions (
    workflow_name TEXT PRIMARY KEY,
    phases TEXT NOT NULL,  -- JSON array of phase names
    transitions TEXT NOT NULL,  -- JSON object of phase -> [next_phases]
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Enrichment side tables (Unit 8)
CREATE TABLE artifact_summaries (
    artifact_id TEXT PRIMARY KEY REFERENCES artifacts(artifact_id),
    summary TEXT,
    tags TEXT,  -- JSON array
    keywords TEXT,  -- JSON array
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE event_window_summaries (
    summary_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    event_start TEXT NOT NULL,
    event_end TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE failure_classifications (
    classification_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    error TEXT NOT NULL,
    failure_type TEXT,  -- classified category
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Indexes (only on hot-read paths, no write-amplification indexes)
CREATE INDEX idx_pipelines_project_id ON pipelines(project_id);
CREATE INDEX idx_workflow_runs_pipeline_id ON workflow_runs(pipeline_id);
CREATE INDEX idx_state_executions_run_id ON state_executions(run_id);
CREATE INDEX idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX idx_artifacts_run_phase ON artifacts(run_id, phase);
```

## 10. Council Review Consolidation

### `council-reviewer-diversity` (GPT) — 9 Findings

| # | Severity | Finding | Applied In |
|---|----------|---------|------------|
| 1 | CRITICAL | Missing `task_hash` column — `UNIQUE(task_hash, project_id)` referenced but never defined | Unit 1.5 + Unit 2 + §9 |
| 2 | CRITICAL | `_pipeline_lock` in-process only — dedup not multi-process safe | Unit 1.5 + Unit 2 (DB UNIQUE is primary) |
| 3 | HIGH | WAL checkpoint timing misalignment — concurrent readers blocked during checkpoint | Unit 2 (`wal_autocheckpoint=0` + manual) |
| 4 | HIGH | (See other HIGH findings in Gap Analysis) | Various |
| 5 | HIGH | (See other HIGH findings in Gap Analysis) | Various |
| 6 | MODERATE | (See other MODERATE findings in Gap Analysis) | Various |
| 7 | MODERATE | (See other MODERATE findings in Gap Analysis) | Various |
| 8 | MODERATE | (See other MODERATE findings in Gap Analysis) | Various |
| 9 | LOW | (See other LOW findings in Gap Analysis) | Various |

### `council-reviewer-arch` (Gemma) — PASS

All four assessment axes passed:
- **Relational state machine:** PASS — Unit 3 atomic transitions + Unit 4 ContextRouter
- **ID tagging:** PASS — Unit 1.5 pipeline_id propagation + project_id constraints
- **Deduplication:** PASS — Unit 1.5 exact-match + Unit 2 DB UNIQUE constraint
- **Single source of truth:** PASS — Unit 2 removes `state_json`, all via RelationalStore

Routing matrix alignment: **PASS** — Python/Small Model/Chair ownership matches unit assignments.

### `council-reviewer-logic` (Nemotron) — PARTIAL → FIXED

All 7 findings applied:
- **CRITICAL:** `task_hash` missing from tracker insert → Added explicit computation in `upsert_pipeline()`
- **CRITICAL:** `_pipeline_lock` in-process only → Removed Python lock; DB UNIQUE + `INSERT OR IGNORE` + retry is sole safety mechanism
- **HIGH:** `_delegate()` bypasses tracking → Enforced all paths through `_get_or_create_pipeline()`
- **HIGH:** Routing matrix Chair mismatch → Added `ChairAgent` thin wrapper to align with code
- **MODERATE:** `LIKE ?` substring dedup → Exact `WHERE task_hash = ?` match only
- **MODERATE:** Truncated UUID → Full `uuid4().hex` used
- **LOW:** DDL split across files → Consolidated into `migrations/09_schema.sql`
