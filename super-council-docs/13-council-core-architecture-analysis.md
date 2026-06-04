---
name: council-unified-architecture
description: "First-principles analysis of the Council unified database architecture. Defines what must be built, bridged, or refactored to fulfill the target system's purpose. Use when planning, implementing, or reviewing changes to the memory layer, search architecture, or Odysseus-Council integration."
---

# Council Unified Architecture — First Principles Skill

> **Purpose:** Ensure every change to the Council memory system serves the core architectural goals. Prevents drift, fragmentation, and feature creep.
> **Based on:** 13-council-core-unified-db-draft.md (v3), actual codebase analysis (pipelines.db, Odysseus app.db, memory_service source)
> **Date:** 2026-06-04

---

## First Principles

The Council system exists to solve **five fundamental problems** for AI agent workflows:

| Principle | Problem | What It Means |
|---|---|---|
| **Persistence** | Knowledge vanishes between sessions | Every fact, decision, and artifact must survive restarts |
| **Recall** | Agents can't find what they need | Knowledge must be retrievable by meaning, keyword, structure, AND execution history |
| **Consolidation** | Raw traces accumulate without structure | Knowledge must be distilled from traces → facts → themes → strategy over time |
| **Governance** | No quality control on stored knowledge | Every piece of knowledge needs provenance, reviewability, and expiry |
| **Context** | Knowledge floats without belonging | Every piece of knowledge must be scoped to a project/domain |

**If a feature doesn't serve at least one of these five principles, it doesn't belong in the system.**

---

## Core Capabilities — What Must Exist

The target architecture requires **eight capabilities**. Each is non-negotiable.

### Capability 1: Canonical Persistence (RelationalStore)

**Purpose:** Single write path. Every fact lands in one place.

**Must provide:**
- WAL mode + FK enforcement + manual checkpointing
- Schema loaded from migrations (single source of truth)
- Atomic transactions for state transitions
- TTL-based retention on all memory tables
- **Project scoping** — every writable table that holds knowledge MUST have `project_id TEXT REFERENCES projects(id)`

**Current state:** ✅ Implemented for workflow tables. ❌ Missing `project_id` on memory tables (`session_diary`, `raw_session_memories`, `consolidation_cache`, `artifacts`).

**Action required:** ADD `project_id` to all knowledge-bearing tables. Without this, Context Principle is violated.

### Capability 2: Three-Channel Recall (ContextRouter + MemoryLayer)

**Purpose:** Agents retrieve knowledge by meaning, structure, or execution history — not just keyword grep.

**Must provide:**
- **Channel A (Text):** Vector search + session diary + consolidation cache
- **Channel B (Structure):** Workflow definitions, phase transitions, code graph
- **Channel C (Execution):** Recent events, run snapshots, failure summaries
- **Fusion:** Token-budgeted context slice that never cuts mid-artifact

**Current state:** ✅ Implemented. All three channels exist. Fusion works.

**Action required:** NONE — this is the strongest part of the current architecture.

### Capability 3: Code Intelligence (CodeGraphStore)

**Purpose:** Structural understanding of the codebase — callers, callees, impact, traces.

**Must provide:**
- FTS5 full-text search over symbols
- Call graph traversal (callers/callees)
- Impact analysis (blast radius)
- Path tracing (call paths through dynamic dispatch)
- **Separate database file** — never embedded in council_core.db

**Current state:** ✅ Functionality exists. ❌ Still embedded in `pipelines.db` (cg_* tables = 257K edges).

**Action required:** EXTRACT to `codegraph.db`. This is a pure data move — no code changes, just `ATTACH DATABASE` + `INSERT INTO dst SELECT FROM src`.

### Capability 4: Consolidation Pipeline (ArcPipeline + IdleWindowScheduler)

**Purpose:** Raw traces → structured knowledge over time. Prevents memory bloat.

**Must provide:**
- 4-tier pyramid: daily → short → weekly → bimonthly
- Each tier reads from lower tier output
- Idle-window scheduling (CPU-aware, Arc-health-gated)
- Startup catch-up for missed tiers
- Output written to `session_diary` (lower tiers) or `consolidation_cache` (higher tiers)

**Current state:** ✅ Implemented. Pipeline, scheduler, and tier definitions all exist.

**Action required:** NONE — but ensure `session_diary` rows from tiered consolidation get `project_id` when Capability 1 is fixed.

### Capability 5: Review Lifecycle (ReviewService)

**Purpose:** Quality gates for knowledge and code changes.

**Must provide:**
- `review.start()` → create pipeline + workflow_run + seed event
- `review.log()` → record findings with severity
- `review.verdict()` → PASS/FAIL/PARTIAL with reason
- Findings queryable by ContextRouter

**Current state:** ✅ Implemented. `review_findings` table exists with 11 rows.

**Action required:** NONE.

### Capability 6: Unified Search (UnifiedSearchRouter) — **MISSING**

**Purpose:** Single query interface for ALL search capabilities. Agents should never need to know which backend to hit.

**Must provide:**
- **Vector search** — Milvus-lite (semantic similarity)
- **Keyword search** — FTS5 on SQLite (precision matching)
- **Hybrid search** — RRF fusion of vector + keyword results
- **Code search** — CodeGraphStore FTS5 (structural)
- **Web search** — SearXNG pass-through (external knowledge)
- **Single interface:** `router.search(query, mode='hybrid', project_id=...)`

**Current state:** ❌ Does not exist. Five separate search paths:
- `MemIndex` (Milvus-lite, memory_service)
- `ProjectAwareMemSearch` (wrapper, memory_service)
- `MemoryVectorStore` (ChromaDB, Odysseus)
- `CodeGraphStore` (FTS5, code_graph)
- `web_search` tool (SearXNG, Odysseus)

**Action required:** BUILD `UnifiedSearchRouter`. This is the single largest capability gap. Without it, agents must know which tool to call for which query type — defeating the purpose of unified memory.

### Capability 7: Unified Vector Store (UnifiedVectorStore) — **MISSING**

**Purpose:** Single vector backend replacing ChromaDB + Milvus fragmentation.

**Must provide:**
- Single Milvus-lite collection (`unified_vectors`)
- Source tagging: `memory`, `knowledge_card`, `document`, `note`, `artifact`, `session_diary`
- `index(source, source_id, text, metadata)` — fire-and-forget indexing
- `search(query, top_k, filters)` — filtered vector search
- `dedup_check(text, threshold)` — near-duplicate detection

**Current state:** ❌ Does not exist. Two vector backends:
- Milvus-lite (`~/.memsearch/milvus.db`) — Council memsearch, 351 entities
- ChromaDB (`:8100`) — Odysseus memory vector + RAG, NOT RUNNING

**Action required:** BUILD `UnifiedVectorStore`. ChromaDB is not running, so zero migration cost — just stop importing it and use Milvus-lite everywhere.

### Capability 8: Embedding Infrastructure (pplx-embed-v1) — **PARTIAL**

**Purpose:** Single embedding model for all vector operations.

**Must provide:**
- Single model: `pplx-embed-v1-0.6b-int8` (ONNX INT8, 1024d, 32K context)
- HTTP server on `:18099` (OpenAI-compatible `/v1/embeddings`)
- Direct ONNX load path for MicroModelEnricher (async, low-latency)
- All clients (Memsearch, Odysseus, MicroModelEnricher) use same model

**Current state:** ⚠️ Model exists on disk (688MB). `server.py` exists. Server is NOT running. Odysseus defaults to `all-MiniLM-L6-v2`.

**Action required:** START server on `:18099`. Point Memsearch and Odysseus at it. Remove bge-m3 and all-MiniLM defaults.

---

## The Five Gaps — What Needs To Happen

### Gap 1: Project Identity (BUILD — Foundational)

**Problem:** The system has no concept of "project" beyond a free-text `project_id` string on `pipelines` and `workflow_runs`. No `projects` table, no slug-based dedup, no FTS5 index, no resolution cascade.

**Why it matters:** Without projects, you cannot:
- Scope queries to a domain ("show me everything about mcp-review")
- Deduplicate work across agents ("did someone already create the mcp-review project?")
- Resolve orphaned memories ("which project does this summary belong to?")
- Filter consolidation output ("give me the weekly review for super-council only")

**What to build:**

```
projects table:
  id TEXT PK (UUID, system-stable)
  slug TEXT UNIQUE (human-stable dedup key)
  name TEXT NOT NULL
  description TEXT (indexed by FTS5)
  status TEXT DEFAULT 'active'
  priority TEXT
  tags TEXT (JSON array)
  created_at, updated_at

projects_fts: FTS5 virtual table on (name, description)

get_or_create_project(slug, name, **metadata) → id
  - Lookup by slug
  - INSERT OR IGNORE (race-condition safe)
  - Return winner UUID

4-channel resolution cascade:
  Channel 1: Explicit project_id (if provided)
  Channel 2: Active session → project_id
  Channel 3: File paths in text → codegraph → project slug
  Channel 4: FTS5 keyword match on projects (name + description)
  Fallback: INSERT with project_id=NULL + fire late-resolution event
```

**Depends on:** Nothing. This is the foundation. Build first.

**Files to create/modify:**
- `migrations/10_projects.sql` — CREATE TABLE + FTS5
- `memory_service/store.py` — `get_or_create_project()`, `_resolve_project()`
- `memory_service/layer.py` — `upsert_summary(project_id=...)` with cascade

### Gap 2: Unified Search (BUILD — High Value)

**Problem:** Five separate search interfaces. Agents must know which backend serves which data. No hybrid search. No unified ranking.

**Why it matters:** The whole point of "unified memory" is that agents get ONE query interface. Right now they get five tools and must guess which one to use.

**What to build:**

```
UnifiedSearchRouter:
  __init__(vector_store, db, codegraph_store)
  search(query, mode='hybrid', **filters) → Dict[backends, fused]
  _search_vector(query, filters) → [hits]
  _search_fts5(query, filters) → [hits]
  _search_web(query) → [hits]
  _rrf_fuse(backend_results) → [fused_hits]

RRF fusion:
  score = 1 / (k + rank) where k=61
  Combine vector + keyword ranks
  Deduplicate by source_id
  Return top-10
```

**FTS5 indexes to create:**
- `projects_fts` (on name, description)
- `knowledge_cards_fts` (on topic, summary)
- `documents_fts` (on title, content)
- `notes_fts` (on title, body)

**Depends on:** Gap 3 (UnifiedVectorStore) — the router needs a single vector backend.

**Files to create:**
- `memory_service/search_router.py` — UnifiedSearchRouter class
- `migrations/12_fts5_indexes.sql` — FTS5 virtual tables

### Gap 3: Unified Vector Store (BUILD — Prerequisite for Gap 2)

**Problem:** Two vector backends (Milvus-lite + ChromaDB). Two embedding models. No dedup. No source tagging.

**Why it matters:** Without a unified vector store, you can't do hybrid search, can't deduplicate across sources, and can't filter by source type.

**What to build:**

```
UnifiedVectorStore:
  COLLECTION_NAME = "unified_vectors"
  SOURCES = ("memory", "knowledge_card", "document", "note", "artifact", "session_diary")

  __init__(embedding_url="http://127.0.0.1:18099")
  index(source, source_id, text, metadata) → None
  search(query, top_k, filters) → [hits]
  dedup_check(text, threshold=0.92) → source_id | None

Embedding client:
  HTTP to :18099 (pplx-embed-v1)
  Falls back to direct ONNX load if HTTP fails
```

**Migration:**
- ChromaDB is NOT running → zero data to migrate
- Milvus-lite has 351 entities → re-embed with pplx model
- Odysseus `MemoryVectorStore` → replaced by `UnifiedVectorStore.dedup_check()`

**Depends on:** Gap 8 (Embedding server must be running).

**Files to create:**
- `memory_service/vector_store.py` — UnifiedVectorStore class
- Modify `memory_service/index.py` — replace MemIndex with UnifiedVectorStore

### Gap 4: Odysseus Table Merge (BRIDGE — Data Integration)

**Problem:** Odysseus tables (sessions, memories, notes, documents, crew_members, model_endpoints, scheduled_tasks, calendars) live in `vendor/odysseus/data/app.db`. They need to be harmonized into `council_core.db`.

**Why it matters:** Without this merge, Odysseus writes to its own database and Council has no visibility. The "single write path" principle is violated.

**What to bridge:**

| Odysseus Table | Council Table | Mapping |
|---|---|---|
| `sessions` | `sessions` | Rename `owner` → `owner_id`, `rag` → `has_rag`, `archived` → `is_archived`. Add `project_id`, `expires_at`, `metadata`. |
| `memories` | `memories` (NEW) | Add `project_id`, `confidence`, `tags`, `related_memory_ids`, `tier`, `is_indexed`, `expires_at`. |
| `notes` | `notes` | Add `project_id`, `metadata`, `created_by`, `updated_by`, `revision`. |
| `documents` | `documents` (NEW) | Add `project_id`, `tags`, `metadata`, `created_by`, `updated_by`, `revision`. |
| `crew_members` | `crew_members` | Rename `owner` → `owner_id`. Add `metadata`. |
| `model_endpoints` | `model_endpoints` | Add `metadata`. Preserve `EncryptedText` for `api_key`. |
| `scheduled_tasks` | `scheduled_tasks` (NEW) | Rename `owner` → `owner_id`. Add `metadata`, `is_enabled`, `is_builtin`. |
| `calendars` | `calendars` (NEW) | Rename `owner` → `owner_id`. |
| `calendar_events` | `calendar_events` (NEW) | New table. |
| `task_runs` | `task_runs` (NEW) | New table. |

**Critical:** All `session_id` columns must have `REFERENCES sessions(id) ON DELETE SET NULL` (or CASCADE for chat_messages).

**Depends on:** Gap 1 (projects table must exist for FK references).

**Files to create:**
- `migrations/11_odysseus_tables.sql` — CREATE TABLE statements in dependency order
- `memory_service/store.py` — Migration helper for column renames

### Gap 5: Knowledge Bridge Tables (BUILD — New Capabilities)

**Problem:** No tables for knowledge cards, research reports, work items, or audit trail. These are the bridge between Odysseus's extraction/research and Council's governance.

**Why it matters:** Without these tables:
- Research findings have no structured home (lost in chat messages)
- No way to track work items through phase states
- No audit trail for data changes
- No knowledge cards for materialized research

**What to build:**

```
knowledge_cards:
  id, topic, summary, confidence, tags, sources,
  related_memory_ids, related_research_ids, project_id,
  tier, is_active, is_indexed, created_by, source_system,
  metadata, created_at, updated_at, expires_at

research_reports:
  id, query, summary, sections, sources, tokens_used,
  duration_seconds, knowledge_card_id, session_id,
  status, created_by, metadata, created_at, updated_at

work_items:
  id, project_id, kind, title, description, status,
  priority, phase, phase_history, tags, assigned_to,
  due_date, related_pipeline_id, related_run_id,
  related_research_id, related_review_id, metadata,
  created_by, updated_by, revision, created_at, updated_at

audit_trail:
  id, table_name, record_id, action, old_value, new_value,
  actor, source_system, metadata, created_at, expires_at
```

**Depends on:** Gap 1 (projects), Gap 4 (sessions for FK references).

**Files to create:**
- `migrations/13_knowledge_bridge.sql` — CREATE TABLE statements

---

## Refactoring Requirements

### Refactor 1: CodeGraph Extraction (Data Move)

**What:** Move `cg_*` tables from `pipelines.db` to `codegraph.db`.

**Why:** CodeGraph is 94K nodes + 257K edges = ~150MB of the 193MB `pipelines.db`. It should be a separate file because:
- Different access patterns (read-heavy search vs write-heavy workflow)
- Different retention policy (code graph grows monotonically; workflow data has TTL)
- Different backup strategy (code graph can be rebuilt; workflow data cannot)

**How:**
```sql
ATTACH DATABASE 'codegraph.db' AS dst;
CREATE TABLE dst.cg_nodes AS SELECT * FROM cg_nodes;
CREATE TABLE dst.cg_edges AS SELECT * FROM cg_edges;
-- ... repeat for cg_files, cg_nodes_fts, etc.
DETACH DATABASE dst;
DROP TABLE cg_nodes; -- ... repeat
```

**Risk:** LOW — pure data move. `CodeGraphStore.__init__()` needs path parameterization.

### Refactor 2: Remove `pipelines_archive` (Schema Cleanup)

**What:** Drop `pipelines_archive` table. Replace with soft-delete pattern on `pipelines`.

**Why:** `pipelines_archive` is a duplicate schema with 0 rows. The soft-delete pattern (`status='archived'`) is simpler and doesn't require a second table.

**How:**
```sql
ALTER TABLE pipelines ADD COLUMN is_archived INTEGER DEFAULT 0;
-- Migrate: INSERT INTO pipelines SELECT * FROM pipelines_archive;
DROP TABLE pipelines_archive;
```

**Risk:** LOW — table is empty.

### Refactor 3: Remove `translations` Table (Schema Cleanup)

**What:** The `translations` table (task_id → pipeline_id mapping) serves delegation tracking. Consider whether this belongs in `work_items.related_pipeline_id` instead.

**Why:** If `work_items` table exists (Gap 5), the `translations` table is redundant.

**Risk:** LOW — table is empty.

---

## What Stays Simple

The following design constraints are **hard rules** — they prevent complexity creep:

1. **One SQLite file** for business data (`council_core.db`)
2. **One SQLite file** for code graph (`codegraph.db`)
3. **One vector store** (Milvus-lite, `~/.memsearch/milvus.db`)
4. **One embedding model** (`pplx-embed-v1-0.6b-int8`)
5. **One embedding server** (`:18099`)
6. **One web search service** (SearXNG, `:8080`)
7. **No PostgreSQL** — all databases are empty. Retired.
8. **No ChromaDB** — not running. Remove immediately.
9. **No connection pooling** — SQLite WAL handles concurrency
10. **No migration tooling** — raw SQL in `migrations/*.sql`
11. **No users table** — ownership is username-based (TEXT, not FK)

---

## Implementation Priority Order

Based on dependency analysis and value delivery:

| Priority | Gap | Effort | Blocks |
|---|---|---|---|
| **P0** | Refactor 1: CodeGraph extraction | Low (data move) | Nothing. Unblocks DB size reduction. |
| **P0** | Refactor 2: Remove `pipelines_archive` | Trivial | Nothing. |
| **P1** | Gap 1: Project Identity | Medium | Everything else (FK anchor) |
| **P1** | Gap 8: Start embedding server | Low (start process) | Gap 3, Gap 2 |
| **P2** | Gap 3: UnifiedVectorStore | Medium | Gap 2 |
| **P2** | Gap 4: Odysseus table merge | Medium | Gap 5 |
| **P3** | Gap 2: UnifiedSearchRouter | Medium | Nothing (depends on P2) |
| **P3** | Gap 5: Knowledge bridge tables | Low (schema only) | Gap 4 |
| **P4** | Refactor 3: Remove `translations` | Trivial | Gap 5 |

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Wrong | What To Do Instead |
|---|---|---|
| Adding tables to `pipelines.db` without migration file | Schema drift. No audit trail. | Always use `migrations/NN_name.sql` |
| Direct ChromaDB access from agents | Bypasses unified vector store | Route through `UnifiedVectorStore` |
| Multiple embedding models | Inconsistent scores, wasted RAM | Single model: `pplx-embed-v1` |
| `project_id` as free text | No dedup, no FK enforcement, no scoping | `REFERENCES projects(id)` with slug dedup |
| Storing full row snapshots in audit_trail | Bloat. 90% of fields don't change. | Store only CHANGED fields |
| LIKE queries for search | No stemming, no ranking, slow | FTS5 indexes |
| Vector search without keyword fallback | Misses exact matches | Hybrid search with RRF fusion |
| Knowledge without project scope | Orphaned data, impossible to filter | 4-channel resolution cascade |

---

## Verification Checklist

Before declaring any gap "done":

- [ ] Migration SQL is idempotent (`CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE`)
- [ ] Migration SQL is in dependency order (FK-referenced tables created first)
- [ ] All `project_id` columns have `REFERENCES projects(id)`
- [ ] All `session_id` columns have `REFERENCES sessions(id) ON DELETE SET NULL`
- [ ] FTS5 virtual tables are created after content tables
- [ ] TTL columns (`expires_at`) have corresponding cleanup mechanism
- [ ] Embedding server health check passes (`curl :18099/v1/models`)
- [ ] Vector store dedup works (`dedup_check` returns existing ID for duplicate text)
- [ ] Search router returns results in all modes (vector, keyword, hybrid, web)
- [ ] CodeGraph is in separate file (`codegraph.db`, not `pipelines.db`)
- [ ] `pipelines_archive` table is dropped
- [ ] ChromaDB is removed from code and docker-compose

---

## Decision Log

| Decision | Rationale | Status |
|---|---|---|
| SQLite, not PostgreSQL | All existing backends are SQLite. PG is empty. | ✅ Decided |
| Single embedding model | pplx-embed-v1: bidirectional, 32K ctx, code-aware, ONNX INT8 | ✅ Decided |
| Milvus-lite, not ChromaDB | Embedded, no external service, ChromaDB not running | ✅ Decided |
| CodeGraph in separate file | Different access patterns, retention, backup strategy | ✅ Decided |
| No users table | Single admin. Username-based ownership. | ✅ Decided |
| FTS5 + vector hybrid search | FTS5 for precision, vector for semantics, RRF for fusion | ✅ Decided |
| 4-channel project resolution | Explicit → session → file-paths → FTS5 → fallback | ✅ Decided |
| Soft-delete, not archive table | Simpler. One table. `status` column handles it. | ✅ Decided |
| Polling for Arc→Odysseus triggers | No pub/sub needed. Single DB, single process. | ✅ Decided |
| EncryptedText for API keys | Fernet encryption at rest. ORM-transparent. | ✅ Decided |
