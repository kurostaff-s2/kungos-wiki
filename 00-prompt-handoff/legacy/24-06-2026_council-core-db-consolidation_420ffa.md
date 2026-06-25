# Council Core DB Consolidation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `consolidation-420ffa` |
| Entity type | `handoff` |
| Short description | Delete dead tables, fix `recall.review_findings()` bug, consolidate schema, checkpoint WAL |
| Status | `draft` |
| Source references | Audit findings from 2026-06-24 session |
| Generated | `24-06-2026` |
| Next action / owner | Execute Phase 1 (review_findings fix) immediately; remaining phases sequential |

## Project Context

**Project root:** `/home/chief/.council-worktrees/pipe-4bf58d2f7ba0430db2d62b3e4ad94eb1/super_council/`
**Database:** `/home/chief/.council-memory/council_core.db`
**Key files for this task:** Listed per phase below
**Related codebases:** None — all changes within `super_council/`

---

## Background

`council_core.db` has 46 real tables (91 counting FTS internals). 16 tables (35%) are empty with no active writer. The `review_findings` table is empty because `review.log()` writes to `event_log` only — the `recall.review_findings()` reader queries the empty table and returns `[]` before reaching the dead `event_log` fallback code.

**Data reality:** 3.8 MB actual data in a 12 MB file + 33 MB WAL. `memory_rollups` (333 rows) consumes 3 MB alone.

---

## Execution Order

```
Phase 1 (review_findings fix) ──┐
                                 ├── Phase 2 (delete dead tables)
Phase 3 (WAL checkpoint) ───────┤
                                 └── Phase 4 (audit trail cleanup)
```

Phase 1 and 3 are independent. Phase 2 depends on 1. Phase 4 depends on 2.

---

## Phase 1: Fix `recall.review_findings()` — Make event_log the primary path

**What:** `review.log()` writes to `event_log` + `artifacts`. The `review_findings` table is never written to by active code. Make `recall.review_findings()` query `event_log` directly as the primary path, with `review_findings` table as optional fallback. This fixes the bug where `recall.review_findings()` returns `[]`.

**Files:**
- Modify: `super_council/memory_service/recall/router.py` (lines 288-348)

**Steps:**

1. Read `super_council/memory_service/recall/router.py` lines 288-350 (the `get_review_findings` method).

2. Replace the method body. Current flow:
   - Line 307: `findings = self._store.get_review_findings(limit=limit)` → always returns `[]`
   - Line 309: `return [...]` → returns empty list, short-circuits
   - Lines 327-348: `event_log` query → **unreachable dead code**

3. New flow:
   ```python
   def get_review_findings(self, project_id=None, limit=10):
       # Primary: event_log (where review.log() actually writes)
       if project_id:
           rows = self._db.execute(
               "SELECT el.event_id, el.run_id, el.event_type, el.severity, "
               "el.message, el.occurred_at, wr.project_id "
               "FROM event_log el "
               "JOIN workflow_runs wr ON el.run_id = wr.id "
               "WHERE el.event_type IN ('review-finding', 'review-verdict') "
               "AND wr.project_id = ? "
               "ORDER BY el.occurred_at DESC LIMIT ?",
               (project_id, limit),
           ).fetchall()
       else:
           rows = self._db.execute(
               "SELECT el.event_id, el.run_id, el.event_type, el.severity, "
               "el.message, el.occurred_at, wr.project_id "
               "FROM event_log el "
               "JOIN workflow_runs wr ON el.run_id = wr.id "
               "WHERE el.event_type IN ('review-finding', 'review-verdict') "
               "ORDER BY el.occurred_at DESC LIMIT ?",
               (limit,),
           ).fetchall()

       # Fallback: review_findings table (populated only by direct RelationalStore calls)
       if not rows:
           findings = self._store.get_review_findings(limit=limit)
           # ... format findings rows ...
       
       # Format event_log rows
       return [
           {
               "event_id": r[0],
               "run_id": r[1],
               "event_type": r[2],
               "severity": r[3],
               "message": r[4],
               "occurred_at": r[5],
               "project_id": r[6] or "",
           }
           for r in rows
       ]
   ```

4. The key change: move the `event_log` query BEFORE the `review_findings` table query. The `review_findings` table becomes a fallback, not the primary path.

5. **Do NOT delete the `review_findings` table yet** — it gets deleted in Phase 2. This phase only fixes the reader.

**Tests:**
- `recall.review_findings(limit=10)` returns non-empty list (should return ~10 of the 120 existing review events)
- `recall.review_findings(project_id='some-project')` filters correctly
- Verify the returned dict keys match the existing docstring: `event_id`, `run_id`, `event_type`, `severity`, `message`, `occurred_at`, `project_id`

**Dependencies:** None.

**Completion Gate:**
- [ ] `recall.review_findings()` returns findings from `event_log`
- [ ] Existing callers (MCP tool, recall.unified) still work
- [ ] No regression in other recall methods

---

## Phase 2: Delete Dead Tables

**What:** Drop 8 tables that have 0 rows and no active writer. This is irreversible — back up the DB first.

**Files:**
- Create: `super_council/migrations/00X_drop_dead_tables.py` (migration script)
- Modify: `super_council/memory_service/store/vector_store.py` (remove dead table configs)

**Tables to drop (ranked by confidence):**

| Table | Rows | Active Writer? | Risk |
|-------|------|----------------|------|
| `review_findings` | 0 | No (Phase 1 removes last reader) | None — Phase 1 already bypasses it |
| `reviews` | 0 | No | None — `review.start/` `log/` `verdict` write to `event_log` |
| `pipelines_archive` | 0 | No | None — identical to `pipelines`, no writes |
| `consolidation_requests` | 0 | No | Low — 0 refs in `memory_service/` |
| `memory_entries_new` | 0 | No | Low — 0 refs, superseded by `memory_rollups` |
| `raw_session_memories_new` | 0 | No | Low — 0 refs |
| `prompt_templates` | 0 | No | Low — 0 refs in `memory_service/` |
| `research_reports` | 0 | No | Low — 0 refs in `memory_service/` |

**Steps:**

1. **Backup:** `cp ~/.council-memory/council_core.db ~/.council-memory/council_core.db.backup.preconsolidation`

2. **Remove vector_store configs for dead tables.** In `vector_store.py`, remove entries from the source config for: `review_findings`, `notes` (if empty), `sessions` (if empty). Check lines ~43-66.

3. **Create migration script** that executes:
   ```sql
   DROP TABLE IF EXISTS review_findings;
   DROP TABLE IF EXISTS review_findings_fts;
   DROP TABLE IF EXISTS reviews;
   DROP TABLE IF EXISTS pipelines_archive;
   DROP TABLE IF EXISTS consolidation_requests;
   DROP TABLE IF EXISTS memory_entries_new;
   DROP TABLE IF EXISTS raw_session_memories_new;
   DROP TABLE IF EXISTS prompt_templates;
   DROP TABLE IF EXISTS research_reports;
   DROP TABLE IF EXISTS research_reports_fts;
   ```

4. **Run migration** against `council_core.db`.

5. **Verify:** `SELECT name FROM sqlite_master WHERE type='table'` — confirm tables are gone.

**Tests:**
- `recall.review_findings()` still works (reads from `event_log` now, not dropped table)
- No ImportError or AttributeError from removed vector_store configs
- DB file size reduced (should be ~11.5 MB after drops, before WAL checkpoint)

**Dependencies:** Phase 1 complete (review_findings reader must be fixed first).

**Completion Gate:**
- [ ] All 8 tables dropped + associated FTS tables
- [ ] vector_store.py cleaned of dead configs
- [ ] `recall.review_findings()` still returns data
- [ ] No errors in memory_service startup

---

## Phase 3: WAL Checkpoint + Vacuum

**What:** The WAL file is 33 MB on a 12 MB DB. Checkpoint and vacuum to reclaim space.

**Files:** None — direct DB operations.

**Steps:**

1. ```python
   import sqlite3
   db = sqlite3.connect('/home/chief/.council-memory/council_core.db')
   db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
   db.execute('VACUUM')
   db.close()
   ```

2. Verify WAL file is gone or < 1 MB.
3. Verify DB file size is reasonable.

**Tests:**
- WAL file size < 1 MB
- DB accessible after vacuum
- All queries still work

**Dependencies:** None (can run in parallel with Phase 1).

**Completion Gate:**
- [ ] WAL truncated
- [ ] DB vacuumed
- [ ] File sizes verified

---

## Phase 4: Audit Trail Column Cleanup (Optional, Low Priority)

**What:** 8 tables share a 7-column audit trail pattern (`external_key`, `revision`, `updated_by`, `updated_at`, `updated_source`, `origin_source`, `status`, `is_deleted`) that no surviving table actively uses for revision tracking.

**Tables affected (after Phase 2 drops):** `projects`, `work_items`, `workflow_runs`

**Files:**
- Create: `super_council/migrations/00X_strip_audit_trail.py`

**Steps:**

1. For each surviving table, check if the audit columns are actually queried or written:
   ```bash
   grep -rn "external_key\|is_deleted\|revision" super_council/memory_service/ --include="*.py"
   ```

2. If a column is never referenced in active code, drop it:
   ```sql
   ALTER TABLE projects DROP COLUMN external_key;
   ALTER TABLE projects DROP COLUMN revision;
   -- etc.
   ```

3. **Caveat:** SQLite `ALTER TABLE DROP COLUMN` requires SQLite 3.35+. Verify version first.

**Tests:**
- All existing queries still work after column drops
- No KeyError from missing columns in code

**Dependencies:** Phase 2 complete.

**Completion Gate:**
- [ ] Unused columns dropped
- [ ] No regressions
- [ ] Schema simplified

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/recall/router.py` | Fix `get_review_findings()` to query `event_log` first |
| Create | `super_council/migrations/00X_drop_dead_tables.py` | Migration: drop 8 dead tables + FTS internals |
| Modify | `super_council/memory_service/store/vector_store.py` | Remove dead table configs |
| Create | `super_council/migrations/00X_strip_audit_trail.py` | Migration: drop unused audit columns (Phase 4) |
| Backup | `~/.council-memory/council_core.db.backup.preconsolidation` | Pre-consolidation backup |

---

## Constraints

- **Backup before Phase 2.** No exceptions. `cp council_core.db council_core.db.backup.preconsolidation`.
- **Phase ordering:** Phase 1 (fix reader) MUST complete before Phase 2 (drop table). Dropping `review_findings` before fixing the reader breaks `recall.review_findings()`.
- **No data loss:** `event_log` has 120 review events that must remain accessible after `review_findings` is dropped.
- **Migration scripts must be idempotent:** Use `DROP TABLE IF EXISTS` and `IF EXISTS` for columns.
- **FTS tables cascade:** Dropping a real table should also drop its `_fts`, `_fts_config`, `_fts_data`, `_fts_docsize`, `_fts_idx` variants.
- **Do not touch `memory_rollups`** — it has 333 rows of actual data and is the active memory store.

---

## Success Criteria

- [ ] `recall.review_findings(limit=10)` returns 10 findings from `event_log`
- [ ] 8 dead tables dropped + associated FTS tables
- [ ] `vector_store.py` has no configs for dropped tables
- [ ] WAL file < 1 MB after checkpoint
- [ ] DB vacuumed, file size < 10 MB
- [ ] No errors in memory_service startup
- [ ] All existing recall tools still work: `recall.unified()`, `recall.recent_knowledge()`, `system_health()`
- [ ] Pre-consolidation backup exists at `~/.council-memory/council_core.db.backup.preconsolidation`

---

## Caveats & Uncertainty

1. **`pipelines_archive` might be intentional.** If archival logic was planned but never implemented, consider keeping the schema. Check git history for TODOs.
2. **`consolidation_requests` might be used by the consolidation worker outside `memory_service/`.** Verify no external process writes to it before dropping.
3. **`notes` table (0 rows, 5 refs) was NOT included in drop list.** It has vector_store config and consolidation client references. Keep for now.
4. **`sessions` table (0 rows, 69 refs) was NOT included in drop list.** Heavily referenced in router. Keep for now — it may be populated by a future feature.
5. **SQLite version:** `ALTER TABLE DROP COLUMN` requires 3.35+. Phase 4 may not be feasible on older SQLite.
6. **FTS reindex:** After dropping tables, FTS indices on remaining tables may need rebuild. Monitor for FTS errors.

---

## Rollback Plan

If anything breaks:
1. Restore: `cp ~/.council-memory/council_core.db.backup.preconsolidation ~/.council-memory/council_core.db`
2. Revert router.py changes via git
3. Restart memory_service
