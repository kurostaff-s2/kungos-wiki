# Task Handoff: Odysseus → Council Core Schema Unification

**Source spec:** `13-council-core-architecture-analysis.md`, `13-council-core-unified-db-draft.md`, `12-odysseus-integration-map.md`
**Generated:** 04-06-2026
**Goal:** Merge Odysseus app.db columns into Council Core schema — include governance columns, media/gallery, extensibility, AI classification, token budgeting, and UI chrome. Produce unified migration SQL + updated CouncilCoreStore.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Reference docs:**
- `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
- `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md`
- `/home/chief/llm-wiki/super-council-docs/12-odysseus-integration-map.md`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/` (source of truth for Odysseus column definitions)
**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/migrations_council_core/01_core_tables.sql` — modify
- `/home/chief/Coding-Projects/7-council/migrations_council_core/02_fts5_indexes.sql` — modify
- `/home/chief/Coding-Projects/7-council/super_council/memory_service/council_core_store.py` — modify
- `~/.council-memory/council_core.db` — target database (apply migrations)

---

## Background & Corrections

**Key correction from previous analysis:** Odysseus is a **single-user system**, not multi-user. This changes the inclusion criteria:

| Previously Recommended | Correction | New Recommendation |
|---|---|---|
| EXCLUDE: Media/gallery | User uploads images/documents for AI analysis | **INCLUDE** |
| EXCLUDE: Extensibility (webhooks, integrations, mcp_servers, user_tools) | Used for upload→analyze pipeline | **INCLUDE** |
| EXCLUDE: UI chrome (color, label, sort_order, image_url, repeat) | Single-user workspace needs visual organization | **INCLUDE** |
| EXCLUDE: AI classification | Already built, useful for auto-categorization | **INCLUDE** (unified) |
| EXCLUDE: Token budgeting | Already built, useful for cost tracking | **INCLUDE** (unified) |
| DEFER: Email traceability | Not needed now | **DEFER** (unchanged) |
| DEFER: Calendar | Not wired yet | **DEFER** (unchanged) |

---

## Execution Order (DAG)

```
Phase 1 (Schema Design) ──┐
                           ├──> Phase 2 (Migration SQL) ──> Phase 3 (CouncilCoreStore) ──> Phase 4 (Apply + Verify)
Phase 1B (Column Audit) ──┘
```

- **Phase 1 + 1B:** Can run in parallel (design + audit)
- **Phase 2:** Depends on Phase 1 completion
- **Phase 3:** Depends on Phase 2 (needs final schema)
- **Phase 4:** Depends on Phase 3 (needs updated store)

---

## Phase 1: Schema Design — Unified Column Specification

**What:** Define the final column specification for every table, merging Odysseus columns with Council governance columns.

**Output:** A complete column specification document (embedded in the migration SQL as comments).

### Unified Column Convention

Every table gets these governance columns (Council adds these):

```sql
revision INTEGER NOT NULL DEFAULT 1,
created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
updated_by TEXT NOT NULL DEFAULT 'system',
updated_source TEXT NOT NULL DEFAULT 'council',
origin_source TEXT NOT NULL DEFAULT 'council',
status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
is_deleted INTEGER NOT NULL DEFAULT 0
```

### Unified AI Classification + Token Budgeting

Instead of separate columns scattered across tables, create **one unified tracking pattern**:

```sql
-- Unified AI metadata column (replaces ai_classification, ai_content_hash separately)
ai_metadata TEXT DEFAULT '{}',  -- JSON: {classification: "...", content_hash: "...", confidence: 0.0, model: "..."}

-- Unified token budgeting (replaces total_input_tokens, total_output_tokens per-session)
-- Stored at the session level, not per-message
-- Also tracks per-operation tokens for research/task runs
```

### Table-by-Table Specification

#### `sessions` (merged Odysseus + Council)

| Column | Source | Type | Notes |
|---|---|---|---|
| `id` | Both | TEXT PK | |
| `name` | Both | TEXT NOT NULL | |
| `endpoint_url` | Odysseus | TEXT NOT NULL | |
| `model` | Both | TEXT NOT NULL | |
| `owner` | Odysseus | TEXT | Single-user, no FK |
| `has_rag` | Odysseus (`rag`) | INTEGER DEFAULT 0 | Renamed from `rag` |
| `is_archived` | Odysseus (`archived`) | INTEGER DEFAULT 0 | Renamed from `archived` |
| `folder` | Odysseus | TEXT | |
| `headers` | Odysseus | TEXT (JSON) | |
| `last_accessed` | Odysseus | TEXT | |
| `last_message_at` | Odysseus | TEXT | |
| `is_important` | Odysseus | INTEGER DEFAULT 0 | |
| `message_count` | Odysseus | INTEGER | |
| `total_input_tokens` | Odysseus | INTEGER DEFAULT 0 | **KEPT** — token budgeting |
| `total_output_tokens` | Odysseus | INTEGER DEFAULT 0 | **KEPT** — token budgeting |
| `mode` | Odysseus | TEXT | 'chat', 'agent', 'research' |
| `crew_member_id` | Odysseus | TEXT | Agent persona reference |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** — project scoping |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** — unified AI classification |
| Governance columns | Council | — | revision, created_at, updated_at, updated_by, updated_source, origin_source, status, is_deleted |

#### `chat_messages` (merged)

| Column | Source | Notes |
|---|---|---|
| `id` | Both | TEXT PK |
| `session_id` | Both | FK → sessions(id) |
| `role` | Both | TEXT NOT NULL |
| `content` | Both | TEXT NOT NULL |
| `metadata` | Both | TEXT (JSON) |
| `timestamp` | Both | TEXT |
| Governance columns | Council | **ADDED** |

#### `notes` (merged — keep ALL Odysseus columns)

| Column | Source | Notes |
|---|---|---|
| `id` | Both | TEXT PK |
| `owner` | Odysseus | TEXT |
| `title` | Both | TEXT |
| `content` | Both | TEXT |
| `items` | Odysseus | TEXT (JSON array) |
| `note_type` | Odysseus | TEXT |
| `color` | Odysseus | TEXT | **KEPT** — UI chrome |
| `label` | Odysseus | TEXT | **KEPT** — UI chrome |
| `is_pinned` | Odysseus (`pinned`) | INTEGER DEFAULT 0 | **KEPT** — renamed |
| `is_archived` | Odysseus (`archived`) | INTEGER DEFAULT 0 | **KEPT** — renamed |
| `due_date` | Odysseus | TEXT | |
| `source` | Odysseus | TEXT | |
| `session_id` | Odysseus | FK → sessions(id) | |
| `sort_order` | Odysseus | INTEGER | **KEPT** — UI chrome |
| `image_url` | Odysseus | TEXT | **KEPT** — UI chrome |
| `repeat` | Odysseus | TEXT | **KEPT** — UI chrome |
| `ai_classification` | Odysseus | TEXT | **KEPT** — will be merged into ai_metadata |
| `ai_content_hash` | Odysseus | TEXT | **KEPT** — will be merged into ai_metadata |
| `agent_session_id` | Odysseus | TEXT | |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** — supersedes ai_classification + ai_content_hash |
| Governance columns | Council | **ADDED** |

#### `documents` (merged)

| Column | Source | Notes |
|---|---|---|
| `id` | Both | TEXT PK |
| `session_id` | Both | FK → sessions(id) |
| `title` | Both | TEXT NOT NULL |
| `language` | Both | TEXT |
| `current_content` | Both | TEXT NOT NULL |
| `version_count` | Both | INTEGER |
| `is_active` | Both | INTEGER DEFAULT 1 |
| `is_archived` | Odysseus (`archived`) | INTEGER DEFAULT 0 | Renamed |
| `owner` | Odysseus | TEXT |
| `tidy_verdict` | Odysseus | TEXT | **KEPT** — AI analysis result |
| `source_email_uid` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `source_email_folder` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `source_email_account_id` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `source_email_message_id` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** |
| Governance columns | Council | **ADDED** |

#### `memories` (merged)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `text` | Odysseus | TEXT NOT NULL |
| `category` | Odysseus | TEXT |
| `source` | Odysseus | TEXT |
| `owner` | Odysseus | TEXT |
| `session_id` | Odysseus | FK → sessions(id) |
| `timestamp` | Odysseus | INTEGER |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `confidence` | Council draft | REAL | **ADDED** — from unified draft §4.2 |
| `tags` | Council draft | TEXT DEFAULT '[]' | **ADDED** |
| `tier` | Council draft | TEXT | **ADDED** — consolidation tier |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** |
| Governance columns | Council | **ADDED** |

#### `gallery_images` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `filename` | Odysseus | TEXT NOT NULL UNIQUE |
| `prompt` | Odysseus | TEXT NOT NULL |
| `model` | Odysseus | TEXT |
| `size` | Odysseus | TEXT |
| `quality` | Odysseus | TEXT |
| `tags` | Odysseus | TEXT |
| `ai_tags` | Odysseus | TEXT (JSON) | **KEPT** — AI analysis |
| `session_id` | Odysseus | FK → sessions(id) |
| `album_id` | Odysseus | FK → gallery_albums(id) |
| `owner` | Odysseus | TEXT |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `favorite` | Odysseus | INTEGER DEFAULT 0 | **KEPT** — UI chrome |
| `file_hash` | Odysseus | TEXT(64) |
| `taken_at` | Odysseus | TEXT |
| `camera_make` | Odysseus | TEXT |
| `camera_model` | Odysseus | TEXT |
| `gps_lat` | Odysseus | TEXT |
| `gps_lng` | Odysseus | TEXT |
| `width` | Odysseus | INTEGER |
| `height` | Odysseus | INTEGER |
| `file_size` | Odysseus | INTEGER |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** — unified analysis results |
| Governance columns | Council | **ADDED** |

#### `gallery_albums` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `description` | Odysseus | TEXT |
| `cover_id` | Odysseus | TEXT FK → gallery_images(id) |
| `owner` | Odysseus | TEXT |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| Governance columns | Council | **ADDED** |

#### `editor_drafts` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `owner` | Odysseus | TEXT |
| `name` | Odysseus | TEXT NOT NULL |
| `source_image_id` | Odysseus | TEXT FK → gallery_images(id) |
| `width` | Odysseus | INTEGER |
| `height` | Odysseus | INTEGER |
| `payload` | Odysseus | TEXT NOT NULL (JSON) |
| `thumbnail` | Odysseus | TEXT |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| Governance columns | Council | **ADDED** |

#### `signatures` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `owner` | Odysseus | TEXT |
| `name` | Odysseus | TEXT NOT NULL |
| `data_png` | Odysseus | TEXT NOT NULL (base64) |
| `width` | Odysseus | INTEGER |
| `height` | Odysseus | INTEGER |
| `svg` | Odysseus | TEXT |
| Governance columns | Council | **ADDED** |

#### `integrations` (NEW — from Odysseus, for upload→analyze pipeline)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `owner` | Odysseus | TEXT |
| `name` | Odysseus | TEXT NOT NULL |
| `type` | Odysseus | TEXT NOT NULL |
| `config` | Odysseus | TEXT (JSON) |
| `is_enabled` | Odysseus | INTEGER DEFAULT 1 |
| Governance columns | Council | **ADDED** |

#### `mcp_servers` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `transport` | Odysseus | TEXT NOT NULL |
| `command` | Odysseus | TEXT |
| `args` | Odysseus | TEXT |
| `env` | Odysseus | TEXT (JSON) |
| `url` | Odysseus | TEXT |
| `is_enabled` | Odysseus | INTEGER DEFAULT 1 |
| `oauth_config` | Odysseus | TEXT (JSON) |
| `disabled_tools` | Odysseus | TEXT (JSON) |
| Governance columns | Council | **ADDED** |

#### `webhooks` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `url` | Odysseus | TEXT NOT NULL |
| `secret` | Odysseus | TEXT |
| `events` | Odysseus | TEXT NOT NULL |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `last_triggered_at` | Odysseus | TEXT |
| `last_status_code` | Odysseus | INTEGER |
| `last_error` | Odysseus | TEXT |
| Governance columns | Council | **ADDED** |

#### `user_tools` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `description` | Odysseus | TEXT |
| `icon` | Odysseus | TEXT |
| `html_content` | Odysseus | TEXT NOT NULL |
| `scope` | Odysseus | TEXT NOT NULL |
| `session_id` | Odysseus | FK → sessions(id) |
| `owner` | Odysseus | TEXT |
| `is_pinned` | Odysseus | INTEGER DEFAULT 0 |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `version` | Odysseus | INTEGER |
| `author` | Odysseus | TEXT |
| Governance columns | Council | **ADDED** |

#### `user_tool_data` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | INTEGER PK (autoincrement) |
| `tool_id` | Odysseus | FK → user_tools(id) |
| `key` | Odysseus | TEXT NOT NULL |
| `value` | Odysseus | TEXT |
| Governance columns (lite) | Council | created_at, updated_at only |

---

## Phase 1B: Column Audit — Odysseus app.db Inventory

**What:** Dump the full schema from Odysseus app.db and verify every column is accounted for in the unified spec.

**Steps:**
1. Run `sqlite3 vendor/odysseus/data/app.db ".schema"` and capture output
2. Cross-reference every column against the Phase 1 spec
3. Flag any Odysseus column not in the spec
4. Flag any spec column not in Odysseus (these are Council additions — verify they're intentional)

**Output:** Audit report as comments in the migration SQL.

---

## Phase 2: Migration SQL — Unified Schema

**What:** Rewrite `migrations_council_core/01_core_tables.sql` with the unified schema.

**Files:**
- `migrations_council_core/01_core_tables.sql` — complete rewrite
- `migrations_council_core/02_fts5_indexes.sql` — add FTS5 for new tables

**Steps:**
1. Keep existing tables (projects, work_items, workflow_runs, reviews, review_findings, prompt_templates, knowledge_cards, memory_entries, memory_rollups, research_reports) — they're correct
2. Rewrite `sessions` with unified columns (has_rag, is_archived, project_id, ai_metadata, governance)
3. Rewrite `chat_messages` with governance columns
4. Rewrite `notes` with ALL Odysseus columns + project_id + ai_metadata + governance
5. Rewrite `documents` with unified columns + governance (email columns as nullable DEFERRED)
6. Rewrite `memories` with project_id, confidence, tags, tier, ai_metadata, governance
7. Add `gallery_images` table
8. Add `gallery_albums` table
9. Add `editor_drafts` table
10. Add `signatures` table
11. Add `integrations` table
12. Add `mcp_servers` table
13. Add `webhooks` table
14. Add `user_tools` table
15. Add `user_tool_data` table
16. Add indexes for all new FK columns and hot-read paths
17. Update `02_fts5_indexes.sql` to add FTS5 for: gallery_images (prompt, ai_tags), editor_drafts (name, payload), integrations (name, type), user_tools (name, description)

**Constraints:**
- **Idempotent:** Every CREATE TABLE uses `IF NOT EXISTS`
- **FK-safe:** All foreign keys reference existing tables (create in dependency order)
- **SQLite types only:** TEXT, INTEGER, REAL — no BOOLEAN, no TIMESTAMPTZ, no JSONB
- **Governance columns on EVERY table:** No exceptions
- **ai_metadata on content-bearing tables:** sessions, notes, documents, memories, gallery_images
- **project_id on all user-data tables:** For project scoping (Gap 4)

---

## Phase 3: CouncilCoreStore — Updated Access Layer

**What:** Update `memory_service/council_core_store.py` to support new tables and unified columns.

**Steps:**
1. Add CRUD for `gallery_images` — create, list, search by tags/ai_tags, get by filename
2. Add CRUD for `gallery_albums` — create, list, get by id
3. Add CRUD for `editor_drafts` — create, list, get by id, update payload
4. Add CRUD for `signatures` — create, list, get by name
5. Add CRUD for `integrations` — create, list, enable/disable
6. Add CRUD for `mcp_servers` — create, list, enable/disable, update config
7. Add CRUD for `webhooks` — create, list, trigger, get last status
8. Add CRUD for `user_tools` — create, list, pin/unpin, enable/disable
9. Add CRUD for `user_tool_data` — get/set by (tool_id, key)
10. Update `get_sessions()` to include `total_input_tokens`, `total_output_tokens`, `ai_metadata`
11. Update `get_notes()` to include all UI chrome columns + `ai_metadata`
12. Update `get_documents()` to include `project_id`, `ai_metadata`
13. Add `get_memories()` method with project_id filter
14. Update `health_check()` to report row counts for all new tables

**Constraints:**
- **No raw SQL in MCP layer:** All queries go through CouncilCoreStore methods
- **Parameterized queries only:** No string concatenation for SQL
- **WAL mode:** All connections use `PRAGMA journal_mode=WAL`

---

## Phase 4: Apply Migrations + Data Migration + Verification

**What:** Apply the unified migration to council_core.db, migrate data from Odysseus app.db, verify end-to-end.

**Steps:**

### 4A. Apply Migration
1. Backup council_core.db: `cp ~/.council-memory/council_core.db ~/.council-memory/council_core.db.backup.pre-unification`
2. Run migration SQL against council_core.db (use ALTER TABLE for existing tables, CREATE TABLE for new ones)
3. Verify all tables exist: `SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`

### 4B. Migrate Odysseus Data
1. Copy `sessions` from app.db → council_core.db (map `rag→has_rag`, `archived→is_archived`)
2. Copy `chat_messages` from app.db → council_core.db
3. Copy `notes` from app.db → council_core.db (map `pinned→is_pinned`, `archived→is_archived`)
4. Copy `documents` from app.db → council_core.db (map `archived→is_archived`)
5. Copy `memories` from app.db → council_core.db (0 rows expected, but migrate schema)
6. Copy `gallery_images` from app.db → council_core.db (if data exists)
7. Copy `gallery_albums` from app.db → council_core.db (if data exists)
8. Copy `editor_drafts` from app.db → council_core.db (if data exists)
9. Copy `integrations` from app.db → council_core.db (if data exists)
10. Copy `mcp_servers` from app.db → council_core.db (if data exists)
11. Copy `webhooks` from app.db → council_core.db (if data exists)
12. Copy `user_tools` from app.db → council_core.db (if data exists)
13. For all migrated rows: set `origin_source='odysseus'`, `updated_source='migration'`

### 4C. Backfill Missing Columns
1. `ALTER TABLE memory_entries ADD COLUMN project_id TEXT REFERENCES projects(id)` (if not present)
2. `ALTER TABLE memory_rollups ADD COLUMN project_id TEXT REFERENCES projects(id)` (if not present)
3. `ALTER TABLE knowledge_cards ADD COLUMN project_id TEXT REFERENCES projects(id)` (if not present)
4. Backfill `ai_metadata` = '{}' for all existing rows in sessions, notes, documents, memories, gallery_images

### 4D. Verification
1. Run `health_check()` — all tables present, row counts match expectations
2. Verify FK integrity: `PRAGMA foreign_key_check`
3. Verify FTS5 indexes: `SELECT COUNT(*) FROM <table>_fts`
4. Verify data migration: compare row counts between app.db and council_core.db
5. Test CouncilCoreStore CRUD for each new table

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `migrations_council_core/01_core_tables.sql` | Unified schema with all Odysseus + Council columns |
| Modify | `migrations_council_core/02_fts5_indexes.sql` | FTS5 for new tables |
| Modify | `memory_service/council_core_store.py` | CRUD for all new tables + updated column access |
| Create | `migrations_council_core/03_unify_odysseus_columns.sql` | ALTER TABLE + data migration from app.db |
| Modify | `memory_service/config.py` | Add new table config if needed |

---

## Constraints

- **SQLite only:** No PostgreSQL types. TEXT for PKs, TEXT for timestamps, TEXT for JSON.
- **Idempotent migrations:** Safe to re-run. Use `IF NOT EXISTS`, `ALTER TABLE IF NOT EXISTS` (or check-first pattern).
- **FK enforcement:** `PRAGMA foreign_keys=ON` on all connections.
- **WAL mode:** `PRAGMA journal_mode=WAL` on all connections.
- **Governance columns mandatory:** Every table gets revision, created_at, updated_at, updated_by, updated_source, origin_source, status, is_deleted.
- **ai_metadata unified:** Single JSON column replaces scattered ai_classification, ai_content_hash columns. Both old columns KEPT for backward compatibility but deprecated.
- **Token budgeting unified:** total_input_tokens + total_output_tokens on sessions. Per-operation token tracking via metadata JSON on workflow_runs/task_runs.
- **project_id on all user-data tables:** No exceptions. NULL allowed (late binding via 4-channel resolution).
- **No data loss:** Source DBs (app.db, pipelines.db) preserved as backups.
- **Single-user model:** No users table. `owner` is TEXT username, not FK.

---

## Success Criteria

- [ ] `01_core_tables.sql` contains unified schema for all 20+ tables
- [ ] Every table has governance columns (revision, updated_by, origin_source, is_deleted, etc.)
- [ ] `ai_metadata` column on sessions, notes, documents, memories, gallery_images
- [ ] `total_input_tokens` + `total_output_tokens` on sessions (token budgeting)
- [ ] All UI chrome columns kept (color, label, sort_order, image_url, repeat, pinned, favorite)
- [ ] Media/gallery tables present (gallery_images, gallery_albums, editor_drafts, signatures)
- [ ] Extensibility tables present (integrations, mcp_servers, webhooks, user_tools, user_tool_data)
- [ ] `project_id` FK on all user-data tables
- [ ] FTS5 indexes on all content-bearing tables
- [ ] Migration applied to council_core.db without errors
- [ ] Data migrated from app.db (sessions, chat_messages, notes, documents, memories)
- [ ] `PRAGMA foreign_key_check` passes (no FK violations)
- [ ] CouncilCoreStore CRUD works for all new tables
- [ ] `health_check()` reports all tables with correct row counts
- [ ] Source DBs (app.db, pipelines.db) untouched
- [ ] All existing tests pass (no regression)

---

## Caveats & Uncertainty

1. **Email columns are DEFERRED but present as nullable:** `source_email_*` columns exist in documents but are NULL. If email integration is built later, they're ready. If not, they're dead weight (5 nullable TEXT columns).
2. **ai_classification + ai_content_hash kept alongside ai_metadata:** For backward compatibility during transition. Plan to deprecate and remove after 2-4 weeks once all code uses ai_metadata.
3. **crew_member_id on sessions:** Kept because Odysseus agent personas may be useful. But Council's model dispatch is skills-based, not DB-based. May become orphaned if crew_members table is not wired.
4. **Gallery tables may have 0 rows:** Odysseus app.db likely has no gallery data. Tables exist but are empty. Verify before spending time on migration.
5. **mcp_servers overlap:** Council already has MCP via Pi extension. Odysseus mcp_servers table may duplicate this. Consider whether to merge or keep separate.

---

## Stress Test

1. **If Odysseus schema changes upstream:** Migration SQL is idempotent. New columns can be added via ALTER TABLE. Governance columns are stable.
2. **If multi-user is needed later:** `owner` TEXT → FK to users table. Breaking change but contained (one column per table).
3. **If email integration is built:** `source_email_*` columns already exist. Just populate them.
4. **If gallery/media grows large:** `gallery_images` has `file_hash` UNIQUE index for dedup. Consider blob storage migration if >10K images.

---

## Notes for Executor

- Read `vendor/odysseus/data/app.db` schema FIRST to verify column names match the spec
- The `migrate_data.py` in `migrations_council_core/` has existing migration logic — extend it, don't rewrite
- CouncilCoreStore uses `sqlite3.Row` as row_factory — all queries return dicts
- The unified DB draft (`13-council-core-unified-db-draft.md`) has the original design decisions — reference it for rationale
