# Task Handoff: PostgreSQL Migration + Memory Wiring + AppFlowy Extension

**Source specs:** `12-appflowy-integration.md`, `03-relational-layer.md`, `09-memory-service.md`
**Generated:** 03-06-2026
**Goal:** Migrate all Council data from pipelines.db (SQLite) to council_test (PostgreSQL), wire the memory layer to PostgreSQL, extend AppFlowy integration to include memory layer data, and verify end-to-end bidirectional sync.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council`
**Reference docs:** `/home/chief/llm-wiki/super-council-docs/12-appflowy-integration.md`, `/home/chief/llm-wiki/super-council-docs/03-relational-layer.md`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super_council/vendor/appflowy-cloud`
**Key files for this task:** Listed per phase below.

---

## Current State (Baseline)

| Data Store | Tables | Rows | Sync Target |
|---|---|---|---|
| **pipelines.db** (SQLite) | raw_session_memories, session_diary, consolidation_cache, review_findings, event_log, artifacts, session_summaries | 55, 16, 2, 11, 11, 9, 0 | NOT synced |
| **council_test** (PostgreSQL) | council_core.*, council_sync.*, council_ops.* | **0 everywhere** | AppFlowy sync source (empty) |
| **AppFlowy** | work_items (2 rows), reviews/findings/knowledge_base/prompt_library (0) | 2 | Visual workspace |

**Problem:** council_test PostgreSQL is empty. AppFlowy sync reads from council_core.* which has 0 rows. Memory layer data (raw_session_memories, consolidation_cache, session_diary) exists only in pipelines.db and is not part of the AppFlowy sync design.

---

## Execution Order (DAG)

```
Phase 1: PG Migration Scripts (foundational)
    ↓
Phase 2: Data Migration (depends on 1)
    ↓
Phase 3: Memory Layer PostgreSQL Tables (parallel with 4)
Phase 4: AppFlowy Memory Databases (parallel with 3)
    ↓
Phase 5: Memory → AppFlowy Sync Workers (depends on 3,4)
    ↓
Phase 6: Production Wiring + E2E Verification (depends on all)
```

---

### Phase 1: PostgreSQL Migration Scripts

**What:** Create migration scripts to populate council_test PostgreSQL from pipelines.db SQLite data. Establish council_core tables with data.
**Files:**
- Create `super_council/migrations_pg/001_seed_from_pipelines.py` — migration script
- Modify `super_council/memory_layer.py` — add PostgreSQL write path
**Steps:**
1. Create migration script that reads from pipelines.db (SQLite) and writes to council_test (PostgreSQL)
2. Map pipelines.db tables → council_core tables:
   - `review_findings` → `council_core.review_findings`
   - `artifacts` → `council_core.knowledge_cards` (transform: extract key fields)
   - `session_summaries` → `council_core.memory_entries` (if data exists)
3. Generate UUIDs for migrated rows, preserve original IDs as `external_key`
4. Set `origin_source = 'pipelines_migration'`, `updated_source = 'system'`
5. Create `work_items` from `event_log` entries that represent tasks (filter by event_type)
6. Create `prompt_templates` from `artifact_summaries` if applicable
7. Run migration, verify row counts match
**Tests:**
- [ ] All 11 review_findings migrated with correct fields
- [ ] All 9 artifacts migrated as knowledge_cards
- [ ] Row counts verified: SELECT COUNT(*) from each council_core table
- [ ] No duplicate IDs, all UUIDs valid
**Dependencies:** None

---

### Phase 2: AppFlowy Database Setup for Memory Layer

**What:** Create new AppFlowy databases for memory layer data (session_diary, consolidation_cache, raw_session_memories). Extend the ownership matrix.
**Files:**
- Modify `super_council/setup_appflowy_production.py` — add memory database definitions
- Modify `llm-wiki/super-council-docs/12-appflowy-integration.md` — update ownership matrix §4
**Steps:**
1. Define AppFlowy database schemas for memory layer:
   - **Session Diary:** Title, Provenance, Decisions, Open Items, Work Completed, Session Context, Created At
   - **Consolidation Cache:** Title, Continuity Notes, Preferences, Decisions, Unresolved, Tier, Created At
   - **Raw Session Memories:** Raw Text, Provenance, Source, Created At
2. Add to `DATABASE_DEFINITIONS` in `setup_appflowy_production.py`
3. Update `ENTITY_TO_DATABASE` mapping
4. Run setup script to create databases in AppFlowy
5. Save new database IDs to `appflowy_setup_mapping.json`
**Tests:**
- [ ] 3 new databases created in AppFlowy (session_diary, consolidation_cache, raw_memories)
- [ ] Database IDs saved to mapping file
- [ ] Fields match the schema definitions
**Dependencies:** None (parallel with Phase 3)

---

### Phase 3: Memory Layer PostgreSQL Tables

**What:** Create council_core tables for memory layer data that don't exist yet. Wire memory_layer.py to write to PostgreSQL.
**Files:**
- Create `super_council/migrations_pg/002_memory_layer_tables.py` — DDL for new tables
- Modify `super_council/memory_layer.py` — add PostgreSQL upsert path
- Modify `super_council/relational_store.py` — add memory table queries
**Steps:**
1. Create DDL for memory layer tables in council_core schema:
   ```sql
   CREATE TABLE IF NOT EXISTS council_core.session_diary_entries (
       id UUID PRIMARY KEY,
       provenance TEXT NOT NULL,  -- sess-* or consol-*
       decisions TEXT,
       open_items TEXT,
       work_completed TEXT,
       session_context TEXT,
       consolidation_tier TEXT,
       revision BIGINT NOT NULL DEFAULT 1,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
   );

   CREATE TABLE IF NOT EXISTS council_core.consolidation_cache_entries (
       id UUID PRIMARY KEY,
       provenance TEXT NOT NULL,  -- consol-*
       continuity_notes TEXT,
       preferences TEXT,
       decisions TEXT,
       unresolved TEXT,
       tier TEXT,
       revision BIGINT NOT NULL DEFAULT 1,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
   );

   CREATE TABLE IF NOT EXISTS council_core.raw_session_memories (
       id UUID PRIMARY KEY,
       provenance TEXT NOT NULL,  -- trace-*
       raw_text TEXT NOT NULL,
       source TEXT,
       revision BIGINT NOT NULL DEFAULT 1,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
   );
   ```
2. Migrate data from pipelines.db → new PostgreSQL tables
3. Update memory_layer.py to write to PostgreSQL (dual-write: SQLite + PG)
4. Update relational_store.py queries to use PostgreSQL
**Tests:**
- [ ] All 3 tables created in council_core schema
- [ ] 16 session_diary entries migrated
- [ ] 2 consolidation_cache entries migrated
- [ ] 55 raw_session_memories migrated
- [ ] memory_layer.py writes to both SQLite and PostgreSQL
**Dependencies:** Phase 1 (migration pattern)

---

### Phase 4: Bindings + Outbox for Memory Layer

**What:** Create appflowy_bindings for all memory layer entities. Seed outbox_events for initial sync.
**Files:**
- Modify `super_council/workers/binding_manager.py` — add memory entity types
- Modify `super_council/workers/outbox.py` — add memory entity types
- Modify `super_council/appflowy_sync.py` — add memory database IDs
**Steps:**
1. Add memory entity types to ENTITY_TO_DATABASE mapping:
   - `session_diary` → new AppFlowy database ID
   - `consolidation_cache` → new AppFlowy database ID
   - `raw_session_memory` → new AppFlowy database ID
2. Create bindings for all migrated memory entities in council_sync.appflowy_bindings
3. Seed outbox_events for initial full sync
4. Update FIELD_ALLOWLIST for memory entities (which fields are editable from AppFlowy)
5. Update COLUMN_TO_FIELD mappings in inbound.py for memory entities
**Tests:**
- [ ] Bindings exist for all memory entities (COUNT from appflowy_bindings)
- [ ] Outbox events seeded (COUNT from outbox_events WHERE delivery_state='pending')
- [ ] FIELD_ALLOWLIST includes memory entity types
**Dependencies:** Phase 2, Phase 3

---

### Phase 5: Memory → AppFlowy Sync Workers

**What:** Extend outbound dispatcher and inbound sync to handle memory layer entities. Implement cell transformations for memory data types.
**Files:**
- Modify `super_council/workers/outbox.py` — add memory entity delivery
- Modify `super_council/workers/inbound.py` — add memory entity inbound processing
- Modify `super_council/appflowy_sync.py` — add memory cell transformations
- Create `super_council/tests/test_memory_appflowy_sync.py` — tests
**Steps:**
1. Extend OutboxDispatcher to handle session_diary, consolidation_cache, raw_session_memory entity types
2. Implement cell transformations for memory data:
   - session_diary: decisions → rich_text, open_items → long_text, work_completed → long_text
   - consolidation_cache: continuity_notes → long_text, preferences → long_text, decisions → long_text
   - raw_session_memory: raw_text → long_text
3. Extend inbound sync to handle memory entity types
4. Implement hash comparison for memory entities
5. Add FIELD_ALLOWLIST for memory entities:
   - session_diary: decisions, open_items, work_completed (editable), provenance, session_context (read-only)
   - consolidation_cache: continuity_notes, preferences (editable), provenance, tier (read-only)
   - raw_session_memory: raw_text (read-only — Council owns)
**Tests:**
- [ ] Outbound: session_diary entry created in PG → appears in AppFlowy
- [ ] Outbound: consolidation_cache entry → appears in AppFlowy
- [ ] Inbound: Edit session_diary in AppFlowy → patch applied to PG
- [ ] Hash comparison skips unchanged memory entities
- [ ] Field allowlist enforces read-only fields
**Dependencies:** Phase 4

---

### Phase 6: Production Wiring + E2E Verification

**What:** Start all workers, seed bindings, verify full bidirectional sync for all entity types including memory layer.
**Files:**
- Modify `super_council/workers/launcher.py` — add memory entity types to polling
- Modify `super_council/server.py` — wire memory sync endpoints
**Steps:**
1. Update launcher to include memory entity types in outbound dispatcher and inbound sync
2. Start server with all workers
3. Verify outbound sync:
   - Create work_item in PG → check AppFlowy row appears
   - Create review_finding in PG → check AppFlowy row appears
   - Create session_diary in PG → check AppFlowy row appears
   - Create consolidation_cache in PG → check AppFlowy row appears
4. Verify inbound sync:
   - Edit work_item in AppFlowy → check PG updated
   - Edit review_finding in AppFlowy → check PG updated
   - Edit session_diary in AppFlowy → check PG updated (approved fields only)
5. Verify hash comparison (edit same value → skip)
6. Verify health endpoint reports all components OK
7. Run full test suite: `pytest tests/ -v`
**Post-Wiring Tests (GATE):**
- [ ] Server starts and responds to HTTP on :8000
- [ ] Outbound dispatcher runs and delivers events
- [ ] Inbound sync runs and applies changes
- [ ] All entity types synced: work_items, reviews, findings, prompt_templates, knowledge_cards, session_diary, consolidation_cache
- [ ] AppFlowy web UI at :8099 shows all data
- [ ] Health endpoint: all components OK
- [ ] All existing tests pass (no regression)
- [ ] fetch_row_detail returns correct shape (regression test for fix)
**Dependencies:** All phases

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/migrations_pg/001_seed_from_pipelines.py` | Migrate pipelines.db → PostgreSQL |
| Create | `super_council/migrations_pg/002_memory_layer_tables.py` | DDL for memory tables |
| Create | `super_council/tests/test_memory_appflowy_sync.py` | Memory sync tests |
| Modify | `super_council/setup_appflowy_production.py` | Add memory database definitions |
| Modify | `super_council/memory_layer.py` | Dual-write SQLite + PostgreSQL |
| Modify | `super_council/relational_store.py` | PostgreSQL queries for memory |
| Modify | `super_council/workers/binding_manager.py` | Add memory entity types |
| Modify | `super_council/workers/outbox.py` | Add memory entity delivery |
| Modify | `super_council/workers/inbound.py` | Add memory entity inbound |
| Modify | `super_council/workers/launcher.py` | Add memory to polling |
| Modify | `super_council/appflowy_sync.py` | Add memory cell transforms |
| Modify | `super_council/server.py` | Wire memory sync endpoints |
| Modify | `12-appflowy-integration.md` | Update ownership matrix, add memory section |

---

## Constraints

- **No data loss:** All existing pipelines.db data must be preserved during migration.
- **Revision tracking:** All council_core rows must have revision >= 1, incremented on every write.
- **Field allowlist:** Only explicitly approved fields may be edited from AppFlowy (per §7.6).
- **pre_hash mandatory:** All PUT requests to AppFlowy must include pre_hash (§7.5).
- **Hash-based dedup:** Inbound sync uses snapshot hash comparison, not `since` parameter (§7.5).
- **fetch_row_detail fix:** Must extract `data[0]` from API response (verified fix, 2026-06-03).
- **No backward SQLite sync:** AppFlowy sync reads from PostgreSQL only, not pipelines.db.

---

## Success Criteria

- [ ] All pipelines.db data migrated to council_test PostgreSQL (11 review_findings, 9 artifacts→knowledge_cards, 16 session_diary, 2 consolidation_cache, 55 raw_session_memories)
- [ ] council_core tables populated with data (not 0 rows)
- [ ] 3 new AppFlowy databases created for memory layer (session_diary, consolidation_cache, raw_memories)
- [ ] Bindings exist for all entities in council_sync.appflowy_bindings
- [ ] Outbound sync delivers all entity types to AppFlowy
- [ ] Inbound sync applies AppFlowy changes to PostgreSQL (approved fields only)
- [ ] Hash comparison correctly skips unchanged rows
- [ ] AppFlowy web UI (:8099) shows all synced data
- [ ] Health endpoint reports all components OK
- [ ] All existing tests pass (no regression)
- [ ] 12-appflowy-integration.md updated with memory layer ownership matrix

---

## Caveats & Uncertainty

- **PostgreSQL connection:** council_test uses Unix socket `/var/run/postgresql`, user `postgres`. AppFlowy PostgreSQL is in Docker (separate instance).
- **AppFlowy credentials:** `chief@appflowy.io` / `chief123`, GOTRUE_API_KEY=`hello456`, workspace=`78f5e673-a911-4b4d-9283-be3344c9a784`
- **Port conflicts:** AppFlowy web on :8099, Council API on :8000, AppFlowy cloud on :80
- **Data mapping:** pipelines.db schema differs from council_core schema — field mapping needed (especially artifacts → knowledge_cards)
- **Memory layer in AppFlowy:** Not part of original design spec (§4 ownership matrix). This is an extension. May need design review.
