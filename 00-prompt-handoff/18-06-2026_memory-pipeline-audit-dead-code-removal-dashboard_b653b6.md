# Memory Pipeline Audit — Dead Code Removal + Lifecycle Dashboard

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `b653b6` |
| Entity type | `handoff` |
| Short description | Audit memory service codebase post-`session_lifecycle` migration, remove dead code, tighten pipeline alignment, and update the frontend pipeline dashboard to reflect the unified tracking architecture |
| Status | `draft` |
| Source references | `18-06-2026_delegation-fix-test-rollup-outlier-investigation_6d5fc5.md`, `18-06-2026_final-findings-validation-corrected.md` |
| Generated | `18-06-2026` |
| Next action / owner | Execute Phase 1 (dead code audit) then proceed sequentially through Phases 2–4 |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/18-06-2026_delegation-fix-test-rollup-outlier-investigation_6d5fc5.md` (active 3-phase plan, corrected findings)
- `/home/chief/llm-wiki/00-prompt-handoff/18-06-2026_final-findings-validation-corrected.md` (validation report)
**Key files for this task:**
- `memory_service/store/session_store.py` — `session_lifecycle` table, upsert/query methods
- `memory_service/ingest/session_watcher.py` — JSONL watcher, lifecycle-aware processing gate
- `memory_service/consolidate/pipeline.py` — sequential consolidation, lifecycle dedup guard
- `memory_service/consolidate/tier_writer.py` — rollup DB upsert + lifecycle update
- `memory_service/recall/router.py` — recall router, lifecycle query method
- `api/consolidation_status.py` — pipeline status API endpoint
- `frontend/packages/web-core/src/pages/memory/PipelineView.tsx` — pipeline dashboard
- `frontend/packages/web-core/src/shared/hooks/council/usePipelineDetails.ts` — pipeline data hook
- `frontend/packages/web-core/src/pages/memory/MemoryRollupsPage.tsx` — memory rollups page container

## Background

The `session_lifecycle` table was created as a single source of truth for the JSONL → MD → Rollup pipeline, replacing three fragmented tracking mechanisms:

1. **`raw_session_memories` table** — dropped (77 rows migrated to `session_lifecycle`)
2. **`watcher-outliers.json` file** — removed (replaced by DB query: `md_written=1 AND rollup_id IS NULL`)
3. **In-memory `_processed` dict** — already eliminated in prior sessions

The migration completed: `session_lifecycle` has 77 rows, 55 linked to rollups, 22 awaiting consolidation. The pipeline is running with the new architecture.

**What remains:**
- Dead code references to `raw_session_memories` that need cleanup
- API response structure still uses legacy naming (`raw_sessions`, `watcher_outliers`)
- Frontend types/components still reference old schema (e.g., `RawSessionEntry` with `md_file_count`, `WatcherOutlier`)
- PipelineView needs a "Lifecycle" tab showing the unified tracking view
- Function/method names that reference `raw_session_memories` should be renamed to `session_lifecycle` equivalents
- The `query_existing_rollup` path in the pipeline was replaced by direct `session_lifecycle` queries — verify no orphaned callers

## Phase 1: Dead Code Audit & Removal

**What:** Systematic audit of all dead references, unused imports, and legacy patterns introduced by the `session_lifecycle` migration. Remove or rename everything that references the old architecture.

**Files:** All files listed in Project Context above.

**Steps:**

1. **Rename `query_raw_session_memories` → `query_session_lifecycle`** across all three files:
   - `memory_service/store/session_store.py` (line ~821)
   - `memory_service/recall/router.py` (line ~572)
   - `api/consolidation_status.py` (line ~347) — also rename `_query_raw_session_memories` → `_query_session_lifecycle`

2. **Update callers of `query_raw_session_memories`:**
   - Search for `query_raw_session_memories` across the entire codebase
   - Update any MCP tool definitions, API routes, or router registrations that reference the old name
   - If the method is exposed as an MCP tool, update the tool name accordingly

3. **Rename `_get_watcher_outliers` → `_get_unconsolidated_sessions`** in `api/consolidation_status.py`:
   - Update the function name and docstring
   - Update the response key from `watcher_outliers` to `unconsolidated_sessions`
   - Update the response structure to match the new schema (source_file, trace_id, md_file_path, ingested_at, reason)

4. **Remove unused imports from `session_watcher.py`:**
   - `import json` — no longer needed (outlier file removed)
   - `import os` — check if still used (likely not, since `_log_outlier` removed)
   - Verify `threading` is still needed (only `_lock` for reprocess counts)

5. **Clean up `consolidation_store.py`:**
   - Check if `query_existing_rollup` is still called anywhere after the pipeline switched to direct `session_lifecycle` queries
   - If only called by the old pipeline path, consider deprecating or keeping as fallback
   - Remove any references to `raw_session_memories` in docstrings

6. **Remove `_RAW_SESSION_DATA_DIR` constant if unused:**
   - Check if `_RAW_SESSION_DATA_DIR` in `consolidation_status.py` is still referenced after the lifecycle migration
   - If only used for filesystem globbing (pending/processed MD files), keep it — it's still valid
   - If completely unused, remove it

7. **Update test file references:**
   - `tests/test_migration_seed.py` references `raw_session_memories` in the expected tables list
   - Update to `session_lifecycle` (or remove if the test is for PostgreSQL migration that doesn't apply)

**Tests:**
- Run `python3 -m py_compile` on all modified files
- Run `python3 -m pytest tests/ -v -x` (full suite, no regression)
- Verify memory service starts cleanly: `systemctl --user restart memory-service` then check logs

**Dependencies:** None (Phase 1 is standalone).

## Phase 2: Pipeline Alignment & Tightening

**What:** Tighten the consolidation pipeline to fully leverage `session_lifecycle` as the single source of truth. Remove redundant checks, add missing lifecycle state transitions, and ensure all code paths update the lifecycle table.

**Files:**
- `memory_service/consolidate/pipeline.py`
- `memory_service/consolidate/tier_writer.py`
- `memory_service/ingest/session_watcher.py`
- `memory_service/store/session_store.py`

**Steps:**

1. **Verify all MD write paths update `session_lifecycle.md_written`:**
   - Trace `upsert_raw_session_memory()` → `write_canonical_raw_md()` in `session_store.py`
   - Confirm `md_written=1` is set when MD files are written
   - If not, add the lifecycle update in the MD write path

2. **Add lifecycle error tracking:**
   - When pipeline processing fails for a session, update `session_lifecycle.error` with the failure message
   - When processing succeeds, clear `session_lifecycle.error` (set to NULL)
   - This enables the dashboard to show "failed" state alongside "pending" and "consolidated"

3. **Remove redundant filesystem + DB dual-checks:**
   - The pipeline currently does filesystem glob (`*.md`) AND lifecycle DB query
   - Consider: can the lifecycle query alone drive the pipeline? (i.e., `SELECT source_file FROM session_lifecycle WHERE md_written=1 AND rollup_id IS NULL`)
   - If yes, replace the filesystem glob with the DB query entirely — this eliminates race conditions and is faster
   - If no (filesystem is still needed for edge cases), add a comment explaining why

4. **Add consolidated_at backfill for existing rollups:**
   - The 55 sessions with existing rollups may have NULL `consolidated_at`
   - Run a backfill: `UPDATE session_lifecycle SET consolidated_at = (SELECT created_at FROM memory_rollups WHERE memory_rollups.id = session_lifecycle.rollup_id) WHERE consolidated_at IS NULL AND rollup_id IS NOT NULL`

5. **Add `session_ended` flag update:**
   - When SessionWatcher detects idle timeout (MD written), set `session_ended=1`
   - This distinguishes "session still active" from "session complete, awaiting consolidation"
   - Currently inferred from filesystem (.tmp extension) — move to explicit DB state

6. **Audit `consolidation_store.query_existing_rollup`:**
   - If still used, verify it returns correct results with the new schema
   - If replaced by `session_lifecycle` queries everywhere, mark as deprecated with a TODO comment

**Tests:**
- Verify pipeline processes remaining 22 sessions successfully
- Check `session_lifecycle` has all 77 sessions with correct rollup_id, consolidated_at, and error fields
- Verify no "name not defined" or missing import errors in logs

**Dependencies:** Phase 1 complete (clean codebase first).

## Phase 3: Frontend — Lifecycle Dashboard

**What:** Update the PipelineView component to reflect the unified `session_lifecycle` architecture. Replace legacy tabs with lifecycle-aware views and add a new "Lifecycle" tab showing the complete tracking pipeline.

**Files:**
- `frontend/packages/web-core/src/shared/hooks/council/usePipelineDetails.ts`
- `frontend/packages/web-core/src/pages/memory/PipelineView.tsx`
- `frontend/packages/web-core/src/pages/memory/ConsolidationMonitor.tsx` (optional: add lifecycle stats)

**Steps:**

1. **Update TypeScript types in `usePipelineDetails.ts`:**
   - Replace `RawSessionEntry` with `SessionLifecycleEntry`:
     ```typescript
     export interface SessionLifecycleEntry {
       source_file: string;
       source_uuid: string | null;
       trace_id: string;
       md_written: number;
       md_file_path: string | null;
       md_part_count: number;
       rollup_id: string | null;
       rollup_tier: string | null;
       ingested_at: string;
       md_finalized_at: string | null;
       consolidated_at: string | null;
       error: string | null;
     }
     ```
   - Replace `WatcherOutlier` with `UnconsolidatedSession`:
     ```typescript
     export interface UnconsolidatedSession {
       source_file: string;
       trace_id: string | null;
       md_file_path: string | null;
       ingested_at: string;
       reason: string;
     }
     ```
   - Update `PipelineDetails` interface:
     - Rename `raw_sessions` → `session_lifecycle`
     - Rename `watcher_outliers` → `unconsolidated_sessions`
     - Add lifecycle summary stats: `total_ingested`, `total_md_written`, `total_consolidated`, `total_awaiting`, `total_error`

2. **Update PipelineView tabs:**
   - Replace "Sessions" tab → "Lifecycle" tab (shows unified tracking view)
   - Replace "Outliers" tab → "Awaiting" tab (shows sessions awaiting consolidation)
   - Keep "Pending", "Skipped", "Processed" tabs (filesystem views still useful)

3. **Build the Lifecycle tab view:**
   - Show each session as a row with lifecycle state indicators:
     - Green dot: fully consolidated (rollup_id set)
     - Yellow dot: MD written, awaiting consolidation
     - Gray dot: ingested, MD not yet written
     - Red dot: error state
   - Display key fields: trace_id, ingested_at, md_finalized_at, consolidated_at, error
   - Add a "pipeline stage" column: JSONL → MD → Rollup (with checkmarks for completed stages)

4. **Update summary stats cards:**
   - Replace "Raw Sessions" → "Sessions Ingested" (from lifecycle table)
   - Add "Awaiting Consolidation" stat (md_written=1, rollup_id IS NULL)
   - Add "Has Errors" stat (error IS NOT NULL)
   - Keep existing stats: Pending, Already Consolidated, Processed, Rollups Created

5. **Update the "Awaiting" tab (formerly Outliers):**
   - Show sessions with md_written=1 and rollup_id IS NULL
   - Display: trace_id, md_file_path, ingested_at, reason
   - Add visual indicator if session has been awaiting > 24 hours (stale warning)

6. **Update ConsolidationMonitor (optional):**
   - Add lifecycle summary bar at the top: `77 total → 55 consolidated → 22 awaiting`
   - Color-coded progress bar showing pipeline completion percentage

7. **Sync with API response changes:**
   - Ensure frontend types match the updated API response from Phase 1
   - Update `usePipelineDetails` query key if endpoint path changes
   - Handle backward compatibility if API still returns old keys during transition

**Tests:**
- Frontend compiles without TypeScript errors: `cd frontend && pnpm typecheck` (or equivalent)
- PipelineView renders all tabs without console errors
- Lifecycle tab shows correct counts matching DB
- Awaiting tab displays sessions with md_written=1 and rollup_id IS NULL

**Dependencies:** Phase 1 complete (API response structure updated first).

## Phase 4: Production Wiring & Verification

**What:** Restart memory service, verify full pipeline end-to-end with new architecture, and confirm no regressions.

**Files:** Service configuration, test files.

**Steps:**

1. **Restart memory service:**
   ```bash
   systemctl --user restart memory-service
   journalctl --user -u memory-service --since "now" --no-pager | grep -iE "error|warn|lifecycle"
   ```

2. **Verify startup:**
   - Service starts without errors
   - SessionWatcher starts with lifecycle-aware mode
   - IdleWindowScheduler starts with lifecycle queries
   - No "name not defined" or import errors

3. **Verify pipeline processing:**
   - Check that remaining 22 sessions are picked up and processed
   - Monitor LLM queue: 4/4 slots busy processing
   - Verify `session_lifecycle` updates: rollup_id, consolidated_at set after each completion

4. **Verify API endpoint:**
   - `curl http://localhost:<port>/v1/consolidation/pipeline?days=15`
   - Response contains `session_lifecycle` and `unconsolidated_sessions` keys
   - No `raw_sessions` or `watcher_outliers` keys (or deprecated with warning)

5. **Verify frontend:**
   - Navigate to Memory → Pipeline page
   - All tabs render correctly
   - Lifecycle tab shows 77 sessions with correct states
   - Awaiting tab shows correct count

6. **Full test suite:**
   ```bash
   cd ~/Coding-Projects/7-council/super_council
   python3 -m pytest tests/ -v --tb=short
   ```

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] Memory service starts without errors
- [ ] SessionWatcher processes new JSONL files and updates `session_lifecycle`
- [ ] Pipeline picks up sessions from `session_lifecycle` (not filesystem glob alone)
- [ ] Completed consolidations update `session_lifecycle.rollup_id` and `consolidated_at`
- [ ] API returns updated response structure
- [ ] Frontend PipelineView renders all tabs without errors
- [ ] Lifecycle tab shows correct pipeline stages
- [ ] All existing tests pass (no regression)
- [ ] No dead references to `raw_session_memories` or `watcher-outliers.json` in codebase

**Marking Complete:** The task is NOT complete until all post-wiring tests pass.

## Execution Order

```
Phase 1 (Dead Code Audit) → Phase 2 (Pipeline Alignment) → Phase 3 (Frontend) → Phase 4 (Wiring)
```

All phases are sequential. Phase 3 depends on Phase 1's API response changes. Phase 4 depends on all prior phases.

## Constraints

- **No data loss:** All 77 sessions in `session_lifecycle` must remain intact. No DROP TABLE on `session_lifecycle`.
- **Backward compatibility during transition:** If API response keys change, ensure frontend handles both old and new keys during the transition period.
- **No silent failures:** All DB queries must have try/except with structured logging. If `session_lifecycle` query fails, log and degrade gracefully (fall back to filesystem).
- **Function rename is mechanical:** When renaming `query_raw_session_memories` → `query_session_lifecycle`, update ALL callers. Do not leave orphaned references.
- **Preserve MCP tool compatibility:** If `query_raw_session_memories` is exposed as an MCP tool, maintain backward compatibility by aliasing the old name to the new one (or update MCP tool definitions).

## Success Criteria

- [ ] Zero references to `raw_session_memories` in Python code (excluding test_migration_seed.py which may reference PostgreSQL schema)
- [ ] Zero references to `watcher-outliers.json` in Python code
- [ ] All `query_raw_session_memories` renamed to `query_session_lifecycle` (or equivalent)
- [ ] All `_get_watcher_outliers` renamed to `_get_unconsolidated_sessions`
- [ ] API response uses `session_lifecycle` and `unconsolidated_sessions` keys
- [ ] Frontend PipelineView has Lifecycle tab with pipeline stage visualization
- [ ] Frontend PipelineView has Awaiting tab (replaces Outliers)
- [ ] Frontend types match API response structure
- [ ] Memory service starts and runs without errors
- [ ] Pipeline processes sessions using `session_lifecycle` queries
- [ ] All existing tests pass
- [ ] No console errors in frontend

## Caveats & Uncertainty

1. **MCP tool exposure:** `query_raw_session_memories` may be exposed as an MCP tool in `router.py`. If so, renaming it could break external consumers. Check `router.py` for tool registration and update accordingly.
2. **PostgreSQL migration test:** `tests/test_migration_seed.py` references `raw_session_memories` — this may be for a PostgreSQL migration target that hasn't been updated yet. Verify if this needs updating or if it's a separate concern.
3. **Frontend build system:** The frontend uses pnpm/pnpm-workspace. Verify the correct build command before running typecheck.
4. **API endpoint path:** The pipeline endpoint is `/v1/consolidation/pipeline`. Verify this is the correct path and that no other endpoints need updating.
5. **Legacy rollups:** 180 rollups marked `parse_status='legacy'` still exist. They're not part of this handoff but should be noted as a future cleanup item.
6. **`_RAW_SESSION_PART_MAX_CHARS` constant:** This is still actively used (100K char cap for session parts). Do NOT remove — it's unrelated to the table rename.
