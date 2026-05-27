# Plan: Relational State Machine + Micro-Model Layer

## Summary
Replace JSON-blob persistence in `super-council.py` with a normalized SQLite schema (6 core tables + 4 enum tables), add a Context Router service, an automated State Machine Linter, a Memory Layer with artifact-boundary truncation, and an Embedded Micro-Model enrichment service. Fixes 4 critical runtime bugs and all 8 triple-review findings. Aligns with Integrated State Architecture Specification.

**Scope:** `super-council.py` + new modules (`relational_store.py`, `context_router.py`, `micro_model.py`, `state_linter.py`)  
**Constraints:** Sequential subagent dispatch only (VRAM thrashing). SQLite single-writer (WAL mode). No migration risk (project in development).

---

## Implementation Units

### Unit 1: Fix Critical Runtime Bugs (P0)
- **Files:** `super-council.py`
- **Scope:** Remove dead `PHASE_EXECUTORS` reference, fix `_auto_index_file` receiver, fix UnboundLocalError in `_handle_pipeline`, wire artifacts between phases.
- **RED:** Add unit tests that trigger each crash path (phase execution, INDEX phase, retry path, COHESIVENESS_REVIEW artifact lookup).
- **GREEN:** Apply 4 targeted fixes:
  1. Remove line `executor_name = PipelineState.PHASE_EXECUTORS.get(phase)` (dead reference)
  2. Change `self._auto_index_file` → `self.memory._auto_index_file` in `_run_index`
  3. Fix `ps` UnboundLocalError in `_handle_pipeline` explicit-failure block (line ~5296)
  4. Wire `ps.artifacts[phase] = result` in `_execute_phase` so COHESIVENESS_REVIEW gets PLAN/BUILD outputs
- **REFACTOR:** None needed.
- **Verification:** `pytest tests/test_super_council_bugs.py -v` — all 4 crash tests pass. Manual pipeline run completes SCOUT→PLAN→BUILD→COHESIVENESS_REVIEW without crashes.
- **Dependencies:** none
- **Notes:** These are surgical fixes. No new code, just removing dead references and fixing receivers.

### Unit 2: SQLite Schema + WAL Mode (P1)
- **Files:** `relational_store.py` (new), `super-council.py`
- **Scope:** Create 4 enum lookup tables + 6 core tables + indexes. Enable WAL mode. Seed `workflow_definitions` with current `VALID_TRANSITIONS`.
- **RED:** Test that schema creation succeeds and seed data is present.
- **GREEN:** Implement `RelationalStore` class:
  ```python
  class RelationalStore:
      def __init__(self, db_path: str):
          self.db = sqlite3.connect(db_path)
          self.db.execute("PRAGMA journal_mode=WAL")
          self.db.execute("PRAGMA foreign_keys=ON")
          self._create_tables()
          self._seed_definitions()
  ```
  - `_create_tables()`: DDL from §4.2 (enum tables, core tables, indexes)
  - `_seed_definitions()`: INSERT current `VALID_TRANSITIONS` into `workflow_definitions`
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_relational_store.py -v` — schema creates, seed data present, WAL mode enabled, FK enforcement active. `sqlite3 pipelines.db ".tables"` shows all 10 tables.
- **Dependencies:** none
- **Notes:** No migration needed (project in development). Schema is created on first run.

### Unit 3: Atomic `transition_to()` with Transactional Writes (P1)
- **Files:** `relational_store.py`, `super-council.py`
- **Scope:** Refactor `PipelineState.transition_to()` to write to normalized tables atomically. Fix race condition on `attempt_number` (H1). Wrap in `BEGIN IMMEDIATE ... COMMIT`.
- **RED:** Test that concurrent transitions don't produce duplicate `attempt_number` values.
- **GREEN:** Implement `_next_attempt(run_id, phase)` using `SELECT COALESCE(MAX(attempt_number),0)+1`. Wrap `transition_to()` in `BEGIN IMMEDIATE ... COMMIT` with `try/except ROLLBACK`. Write to `state_executions`, `event_log`, `artifacts`, update `workflow_runs`.
- **REFACTOR:** Remove in-memory `phase_attempts` dict (replaced by DB-side calculation).
- **Verification:** `pytest tests/test_atomic_transition.py -v` — concurrent transitions produce unique `attempt_number`. Partial failure rolls back cleanly.
- **Dependencies:** Unit 2
- **Notes:** Fixes H1 (race condition), M5 (transactional guarantees).

### Unit 4: Context Router Service (P2)
- **Files:** `context_router.py` (new), `super-council.py`
- **Scope:** Implement `ContextRouter` with `get_run_snapshot()`, `get_recent_events()`, `get_artifacts()`, `summarize_run_issues()`, `find_similar_runs()`. Wire into `SlotSupervisor`.
- **RED:** Test that all 5 methods return correct data for a sample run.
- **GREEN:** Implement `ContextRouter` class (from §8.3). Wire into `SlotSupervisor.__init__()` as `self.context_router`.
- **REFACTOR:** Replace `_active_recall()` with `self.context_router.find_similar_runs()` + memsearch fallback.
- **Verification:** `pytest tests/test_context_router.py -v` — all 5 methods return correct data. `get_run_snapshot()` includes executions + artifacts. `summarize_run_issues()` correlates errors with state_executions.
- **Dependencies:** Unit 2, Unit 3
- **Notes:** Fixes M4 (migration backfill risk) by using fallback defaults for missing fields.

### Unit 5: Phase Schema Validation (P2)
- **Files:** `super-council.py`, `relational_store.py`
- **Scope:** Add `PHASE_SCHEMAS` dict (from §10) with input/output contracts for all 10 phases. Validate at phase boundaries.
- **RED:** Test that invalid input/output is caught and logged.
- **GREEN:** Implement `validate_phase_input(phase, data)` and `validate_phase_output(phase, data)`. Call in `_execute_phase()` before/after phase execution.
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_phase_validation.py -v` — invalid input rejected, valid input passes. Missing required fields logged as warnings.
- **Dependencies:** Unit 4
- **Notes:** Fixes L3 (artifact schema `content_path` conditional on `kind`).

### Unit 6: State Machine Linter (P3)
- **Files:** `state_linter.py` (new), `super-council.py`
- **Scope:** Implement `StateMachineLinter` with 8 checks (unreachable, invalid targets, missing handlers, dead-ends, infinite loops, orphaned transitions, missing retreat paths, asymmetric). Fix DFS cycle detection (M3).
- **RED:** Test linter against current `VALID_TRANSITIONS` (should pass all checks). Test against intentionally broken graph (should detect cycles, unreachable states).
- **GREEN:** Implement `StateMachineLinter` (from §7). Fix `_check_infinite_loops` to use per-DFS recursion stack instead of global `visited` set. Fix `_check_retreat_paths` to also check `retreat_target` attribute.
- **REFACTOR:** Expose as Chair/Co-Chair tools: `lint_current_workflow()`, `inspect_workflow_graph()`, `propose_safe_transition()`.
- **Verification:** `pytest tests/test_state_linter.py -v` — current graph passes all checks. Broken graph detected. DFS finds all cycles including shared-node cycles.
- **Dependencies:** none
- **Notes:** Fixes M3 (linter DFS false negatives), L2 (retreat-path false positives).

### Unit 7: Memory Layer with Artifact-Boundary Truncation (P3)
- **Files:** `context_router.py`, `memory_layer.py` (new)
- **Scope:** Implement `MemoryLayer` with memsearch integration. Fix context truncation to use artifact-boundary splitting (H2). Add summarization, chunking, eviction strategies.
- **RED:** Test that context truncation never cuts mid-artifact. Test that token budget is respected.
- **GREEN:** Implement `MemoryLayer` (from §13). Refactor `get_context_slice()` to split context into artifact blocks, drop whole blocks until under budget, replace oversized block with pre-computed summary.
- **REFACTOR:** Replace raw character truncation (`context[:max_chars]`) with block-based truncation.
- **Verification:** `pytest tests/test_memory_layer.py -v` — truncation never produces malformed JSON. Token budget respected. Summaries used when blocks don't fit.
- **Dependencies:** Unit 4
- **Notes:** Fixes H2 (mid-artifact truncation).

### Unit 8: Embedded Micro-Model Layer (P4)
- **Files:** `micro_model.py` (new), `relational_store.py`, `context_router.py`
- **Scope:** Implement `MicroModelEnricher` with `enrich_artifact()`, `enrich_event_window()`, `enrich_failure()`, `should_index_full_text()`. Create 3 enrichment side tables. Wire as async post-commit worker.
- **RED:** Test that enrichment runs asynchronously without blocking phase transitions. Test that enrichment failures are non-blocking. Test that Context Router falls back to raw SQL when enrichment unavailable.
- **GREEN:** Implement `MicroModelEnricher` (from §17). Create `artifact_summaries`, `event_window_summaries`, `failure_classifications` tables. Wire as background thread triggered on `transition_to()` commit.
- **REFACTOR:** Update `ContextRouter.get_run_snapshot()` to include enrichment data. Update `MemoryLayer.ingest_artifact()` to prefer enriched summaries.
- **Verification:** `pytest tests/test_micro_model.py -v` — enrichment runs async, doesn't block transitions. Fallback works when micro-model unavailable. Summaries improve recall quality.
- **Dependencies:** Unit 3, Unit 4, Unit 7
- **Notes:** Operational rules: canonical writes never wait on micro-model. Enrichment failures logged as warnings. Re-enrichment allowed.

### Unit 9: Index Optimization + Retention Automation (P3)
- **Files:** `relational_store.py`
- **Scope:** Drop `idx_events_type` and `idx_events_severity` (only used for manual debugging). Add automated retention/archival job.
- **RED:** Test that dropping indexes doesn't break hot-path queries. Test that archival moves old runs correctly.
- **GREEN:** Remove 2 indexes from DDL. Implement `_archive_old_runs(retention_days=90)` method: INSERT into archive tables, DELETE from main, VACUUM. Schedule via `threading.Timer` or cron.
- **REFACTOR:** None.
- **Verification:** `pytest tests/test_retention.py -v` — archival moves data correctly. VACUUM reclaims space. Hot-path queries still fast.
- **Dependencies:** Unit 2
- **Notes:** Fixes M1 (write amplification), L5 (retention automation).

### Unit 10: Phase Registry Auto-