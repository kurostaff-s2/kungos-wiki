# Council Core Data Topology Fix — Master Plan

**Source spec:** First-principles analysis of council_core.db schema (2026-06-06)
**Generated:** 06-06-2026
**Goal:** Eliminate orphaned entries, zombie tables, and unscoped data in council_core.db; establish a foolproof project→work→execution traceability chain.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Database:** `/home/chief/.council-memory/council_core.db` (primary), `/home/chief/.council-memory/memory.db` (deprecated)
**Migration SQL:** `/home/chief/Coding-Projects/7-council/super_council/migrations_council_core/`
**Key files for this task:**
- `memory_service/store.py` — RelationalStore (all DB writes)
- `memory_service/mcp_server.py` — MCP tool handlers (upsert_summary, recall)
- `memory_service/router.py` — ContextRouter (all DB reads)
- `memory_service/db_poller.py` — FTS/vector indexing poller
- `arc_summarizer/pipeline.py` — Arc A380 consolidation pipeline
- `migrations_council_core/` — SQL migration scripts

**Related codebases:** None (self-contained within super_council)

---

## Problem Summary

| Issue | Severity | Evidence |
|---|---|---|
| 167 memory_entries have NULL source_run_id | Critical — orphaned | 100% of entries unlinked to any execution |
| 14 zombie tables across both DBs | High — confusion | Empty copies of deprecated tables |
| `entry_type='diary'` is a catch-all | Moderate — semantic debt | No distinction between agent summaries and Arc output |
| 8 tables lack project_id entirely | High — unscoped data | sessions, notes, documents, rollups, memory_entries |
| Arc pipeline writes to dead memory.db | Critical — data loss | session_diary and consolidation_cache both empty |
| Inconsistent ID naming | Low — confusion | run_id vs source_run_id vs workflow_runs.id |
| No ON DELETE CASCADE | Moderate — orphan risk | Hard deletes create orphans |

---

## Options and Recommendations

### Option A: Minimal Fix (Stop the bleeding)

**Scope:** Drop zombie tables, fix entry_type naming, enforce source_run_id at write time.

**Pros:**
- Fast (~2 hours)
- Low risk — no schema additions
- Fixes immediate orphaning problem
- No migration of existing data

**Cons:**
- project_id scoping remains incomplete
- Arc pipeline still broken
- Legacy tables in memory.db remain (just ignored)

**Recommendation:** ✅ **Do this first** — it's the foundation everything else builds on.

---

### Option B: Full Topology Fix (Complete re-scope)

**Scope:** Option A + add project_id to all unscoped tables + redirect Arc pipeline + retroactive scoping.

**Pros:**
- Every row traceable to a project
- Arc pipeline produces usable data
- Clean architecture going forward
- Full audit trail

**Cons:**
- ~6–8 hours
- Requires migration of 167 existing memory_entries
- Arc pipeline needs testing
- Breaking change for any code assuming global memories

**Recommendation:** ✅ **Do this after Option A validates** — split into two handoff sessions.

---

### Option C: Nuclear Option (Rebuild council_core from scratch)

**Scope:** Drop both DBs, re-run migrations with corrected schema, re-migrate all data with proper FKs.

**Pros:**
- Clean slate, no legacy debt
- Perfect FK enforcement from day one
- Consistent naming throughout

**Cons:**
- ~12+ hours
- Risk of data loss during re-migration
- Downtime during rebuild
- Overkill for current scale (167 entries)

**Recommendation:** ❌ **Skip** — cost outweighs benefit at current data volume. Revisit if table count exceeds 50 or row count exceeds 100K.

---

## Execution Order (DAG)

```
Phase A1: Drop zombie tables         Phase A2: Fix entry_type semantics
  ↓                                      ↓
Phase A3: Enforce source_run_id       Phase A4: Tests + verification
  ↓
Phase A5: Production wiring (memory service restart, poller check)
```

Phases A1 and A2 are independent — can run in parallel.

---

## Phase A1: Drop Zombie Tables

**What:** Remove 14 empty/deprecated tables from both council_core.db and memory.db.

**Files:**
- Create: `migrations_council_core/04_drop_zombie_tables.sql`
- Modify: `memory_service/store.py` (remove any dead code referencing dropped tables)

**Steps:**
1. Verify all 14 tables are empty (0 rows) — document proof
2. Write SQL migration: `04_drop_zombie_tables.sql`
   - council_core.db: DROP `session_summaries`, `session_diary`, `raw_session_memories`, `consolidation_cache`, `memories`, `notes`, `documents`
   - memory.db: DROP `session_summaries`, `session_diary`, `raw_session_memories`, `consolidation_cache`, `pipelines`, `artifacts`, `event_log`
3. Check for code references to dropped tables (grep in `memory_service/`)
4. Remove dead code paths (e.g., `query_session_summaries()`, `query_consolidation_cache()`)
5. Run migration against both DBs
6. Verify: `PRAGMA table_info` on both DBs shows only active tables

**Tests:**
- [ ] `SELECT COUNT(*) FROM sqlite_master WHERE type='table'` — count reduced by 14
- [ ] No code references to dropped table names
- [ ] `python3 -m memory_service` starts without import errors

**Dependencies:** None.

---

## Phase A2: Fix entry_type Semantics

**What:** Rename `diary` → `summary` for agent-produced entries; reserve `diary` for Arc output; add `consolidation` type.

**Files:**
- Create: `migrations_council_core/05_fix_entry_types.sql`
- Modify: `memory_service/store.py` — `upsert_memory_entry()` CHECK constraint
- Modify: `memory_service/mcp_server.py` — `upsert_summary()` routing logic

**Steps:**
1. Migrate existing data:
   ```sql
   UPDATE memory_entries SET entry_type='summary'
   WHERE entry_type='diary' AND origin_source='inline-summary';
   UPDATE memory_entries SET entry_type='summary'
   WHERE entry_type='diary' AND origin_source='auto-detected-assistant-message';
   -- Note: auto-detected should already be 'raw', but fix any mis-tagged
   ```
2. Update CHECK constraint in `store.py`:
   ```python
   entry_type IN ('raw', 'summary', 'diary', 'consolidation', 'incident', 'decision')
   ```
3. Update `upsert_summary()` routing:
   - `source == "auto-detected-assistant-message"` → `entry_type="raw"` (keep)
   - `source == "inline-summary"` → `entry_type="summary"` (NEW)
   - `source contains "consolidation"` → `entry_type="consolidation"` (NEW)
   - `source contains "arc"` → `entry_type="diary"` (reserved for Arc)
   - Everything else → `entry_type="summary"` (default)
4. Verify distribution:
   - `raw`: auto-detected messages
   - `summary`: agent-produced summaries (was `diary`)
   - `diary`: 0 rows (reserved for Arc)
   - `consolidation`: 0 rows (reserved for Arc full consolidation)

**Tests:**
- [ ] All 167 entries have valid entry_type (no raw `diary` from inline-summary)
- [ ] New CHECK constraint enforced (INSERT with invalid type fails)
- [ ] `upsert_summary` with `source="inline-summary"` produces `entry_type="summary"`

**Dependencies:** None (parallel with A1).

---

## Phase A3: Enforce source_run_id at Write Time

**What:** Make `upsert_summary` accept `project_id` and `run_id`; validate and store them; backfill existing entries.

**Files:**
- Modify: `memory_service/mcp_server.py` — add `project_id`, `run_id` params to `upsert_summary()`
- Modify: `memory_service/store.py` — add validation in `upsert_memory_entry()`
- Create: `migrations_council_core/06_enforce_source_run_id.sql` (ALTER TABLE + backfill)

**Steps:**
1. Add `project_id` column to `memory_entries`:
   ```sql
   ALTER TABLE memory_entries ADD COLUMN project_id TEXT REFERENCES projects(id);
   ```
2. Backfill existing entries:
   ```sql
   -- All existing entries are from the council project
   UPDATE memory_entries SET project_id = 'afee346a-0de1-4683-afcf-914a417c553c'
   WHERE project_id IS NULL;
   ```
3. For `source_run_id`: since none are set, backfill based on `created_at` matching nearest `workflow_runs.started_at`:
   ```sql
   -- Best-effort: link to most recent active run at time of creation
   UPDATE memory_entries SET source_run_id = (
       SELECT id FROM workflow_runs
       WHERE started_at <= memory_entries.created_at
       ORDER BY started_at DESC LIMIT 1
   ) WHERE source_run_id IS NULL;
   ```
4. Update `upsert_summary()` MCP tool:
   ```python
   def upsert_summary(
       summary_text: str,
       source: str = "inline-summary",
       project_id: str = None,
       run_id: str = None,
   ) -> str:
   ```
5. Add validation:
   - If `run_id` provided → `SELECT 1 FROM workflow_runs WHERE id=?` (fail if not found)
   - If `project_id` provided → `SELECT 1 FROM projects WHERE id=?` (fail if not found)
   - If neither → log warning, allow (for global system notes)
6. Update `upsert_memory_entry()` to accept and store `project_id` and `source_run_id`

**Tests:**
- [ ] All 167 entries now have `project_id` set
- [ ] `upsert_summary(run_id="nonexistent")` fails with FK error
- [ ] `upsert_summary(project_id="nonexistent")` fails with FK error
- [ ] `upsert_summary()` without params still works (global entry)

**Dependencies:** A1 (tables must be clean first).

---

## Phase A4: Tests + Verification

**What:** Comprehensive test suite for new schema and write paths.

**Files:**
- Create: `tests/test_data_topology.py`

**Steps:**
1. **Orphan detection test:**
   ```python
   def test_no_orphaned_memory_entries():
       """Every memory_entry must have project_id."""
       orphans = store.db.execute(
           "SELECT COUNT(*) FROM memory_entries WHERE project_id IS NULL"
       ).fetchone()[0]
       assert orphans == 0, f"{orphans} orphaned entries"
   ```
2. **FK integrity test:** Every `source_run_id` points to existing `workflow_runs.id`
3. **entry_type distribution test:** No `diary` entries from non-Arc sources
4. **Write path test:** `upsert_summary()` with valid/invalid params
5. **Zombie table test:** Dropped tables don't exist
6. **FTS consistency test:** `memory_entries_fts` count matches `memory_entries` count

**Tests:**
- [ ] All 6 new tests pass
- [ ] All existing tests still pass (no regression)
- [ ] `python3 -m pytest tests/ -v` — full suite green

**Dependencies:** A1, A2, A3 complete.

---

## Phase A5: Production Wiring

**What:** Restart memory service, verify poller, run end-to-end upsert→recall flow.

**Files:**
- Modify: `memory_service/__main__.py` (if needed for new params)

**Steps:**
1. Run all migrations in order: 01 → 02 → 03 → 04 → 05 → 06
2. Restart memory service: `systemctl --user restart memory-service.service`
3. Verify health: `curl http://127.0.0.1:18096/health`
4. Trigger poller cycle: verify FTS indexes are consistent
5. End-to-end test:
   - Call `upsert_summary("test entry", source="inline-summary", project_id="afee346a...")`
   - Verify entry in `memory_entries` with correct `entry_type`, `project_id`, `source_run_id`
   - Call `recall.unified("test entry")` — verify it's found
   - Verify FTS search works: `memory_entries_fts MATCH 'test entry'`
6. Verify no regressions in existing recall paths

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] Memory service starts and responds to health check
- [ ] Poller runs without errors (check logs)
- [ ] FTS search returns results for new entries
- [ ] `recall.unified()` returns results from council_core.db
- [ ] All 167 existing entries have project_id set
- [ ] All existing tests still pass (no regression)
- [ ] No orphaned entries (project_id IS NOT NULL for all)

**Dependencies:** A1–A4 complete.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations_council_core/04_drop_zombie_tables.sql` | DROP 14 deprecated tables |
| Create | `migrations_council_core/05_fix_entry_types.sql` | Rename diary→summary, add consolidation |
| Create | `migrations_council_core/06_enforce_source_run_id.sql` | Add project_id, backfill, enforce FKs |
| Create | `tests/test_data_topology.py` | Orphan detection, FK integrity, write path tests |
| Modify | `memory_service/store.py` | CHECK constraint, new columns, validation |
| Modify | `memory_service/mcp_server.py` | New params on upsert_summary() |
| Modify | `memory_service/__main__.py` | If CLI needs new params |

---

## Constraints

- **No data loss:** All 167 existing memory_entries must survive migration
- **FK enforcement:** No INSERT with invalid project_id or source_run_id
- **Backward compatibility:** `upsert_summary()` without new params must still work (global entries)
- **FTS consistency:** FTS indexes must match table counts after migration
- **memory.db deprecation:** No new writes to memory.db; reads from it return empty
- **Migration idempotency:** All SQL migrations must be safe to re-run

---

## Success Criteria

- [ ] 14 zombie tables dropped from both DBs
- [ ] `entry_type` correctly categorized (raw/summary/diary/consolidation)
- [ ] All 167 memory_entries have project_id set
- [ ] `upsert_summary()` accepts and validates project_id + run_id
- [ ] Zero orphaned entries (every row traceable to a project)
- [ ] FTS indexes consistent with table data
- [ ] Memory service starts, poller runs, health check passes
- [ ] End-to-end upsert→recall flow verified
- [ ] All existing tests pass (no regression)
- [ ] New test suite (6 tests) passes

---

## Caveats & Uncertainty

1. **source_run_id backfill is best-effort** — temporal matching (nearest workflow_run by created_at) may produce incorrect links. These should be flagged as `origin_source='temporal-backfill'` for manual review.
2. **Arc pipeline not fixed in this handoff** — Option B covers Arc redirection. This handoff only fixes the foundation.
3. **memory.db not deleted** — deprecated but retained until Arc pipeline is fully migrated to council_core.
4. **sessions/notes/documents still unscoped** — Option B adds project_id to these tables. They remain global for now.
5. **No ON DELETE CASCADE added** — soft-delete (`is_deleted=1`) is the current policy. Adding CASCADE would be a separate decision.

---

## Options for Next Phase (Option B — Full Topology)

If Option A validates successfully, the next handoff would cover:

1. **Add project_id to sessions, notes, documents, memory_rollups, cg_*** tables
2. **Redirect Arc pipeline** to write to `council_core.memory_rollups` and `council_core.consolidation_cache`
3. **Add ON DELETE CASCADE** or formalize soft-delete policy
4. **Unify ID naming** (document `run_id` vs `source_run_id` convention)
5. **Full integration test** across project→work→run→entry chain

**Estimated effort:** ~6 hours across 4 phases.

---

## Revisit When

- Table count in council_core exceeds 30
- Row count exceeds 100K (reconsider Option C — nuclear rebuild)
- Multi-user/multi-tenant requirements emerge
- Arc pipeline is reactivated (triggers Option B)
