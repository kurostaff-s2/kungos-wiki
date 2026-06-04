---
name: council-unified-architecture
description: "First-principles analysis of the Council unified database architecture. Defines what must be built, bridged, or refactored. Use when planning, implementing, or reviewing changes to memory, search, or Odysseus-Council integration."
---

# Council Unified Architecture — First Principles

> **Purpose:** Ensure every change serves core architectural goals. Prevents drift, fragmentation, feature creep.
> **Based on:** 13-council-core-unified-db-draft.md (v3), live feature audit (2026-06-04)
> **Date:** 2026-06-04

---

## Five First Principles

| Principle | Problem | What It Means |
|---|---|---|
| **Persistence** | Knowledge vanishes between sessions | Every fact, decision, artifact survives restarts |
| **Recall** | Agents can't find what they need | Knowledge retrievable by meaning, keyword, structure, execution history |
| **Consolidation** | Raw traces accumulate without structure | Traces → facts → themes → strategy over time |
| **Governance** | No quality control on stored knowledge | Provenance, reviewability, expiry on every piece |
| **Context** | Knowledge floats without belonging | Every piece scoped to a project/domain |

**If a feature doesn't serve at least one principle, it doesn't belong.**

---

## Real Usage Flows (Five Outcomes)

Everything traces to one of these. If it doesn't, defer it.

| # | Flow | Who | What Search/Recall Must Deliver |
|---|---|---|---|
| **1** | "What did we decide about X?" | Human → Odysseus | **Vector search** across memories + session diary + consolidation |
| **2** | "Show my notes/tasks for project Y" | Human → Odysseus | **FTS5 keyword** on notes, documents, work_items, filtered by project_id |
| **3** | "Research Z for me" | Human → Odysseus → web | **Web search** (SearXNG) + **structured storage** (research_reports → knowledge_cards) |
| **4** | "Do X" | Human → Odysseus → agent | **Project-scoped CRUD** on work_items with phase tracking |
| **5** | Agent needs context | Agent (pi/Council) | **Unified recall** — vector + keyword + execution history, token-budgeted |

---

## Minimal Viable Set

### Tables (10, not 31)

| Table | Serves | Status |
|---|---|---|
| `projects` | Flows 2,4,5 (scoping) | ❌ Create |
| `sessions` | All flows (context anchor) | ✅ Exists (Odysseus app.db) |
| `chat_messages` | Flow 1 (conversation history) | ✅ Exists (Odysseus app.db) |
| `memories` | Flow 1 (semantic recall) | ✅ Exists (Odysseus app.db, 0 rows) |
| `notes` | Flow 2 (user content) | ✅ Exists (Odysseus app.db, 0 rows) |
| `documents` | Flow 2 (user content) | ✅ Exists (Odysseus app.db, 0 rows) |
| `work_items` | Flow 4 (task tracking) | ❌ Create |
| `research_reports` | Flow 3 (research storage) | ❌ Create |
| `knowledge_cards` | Flow 3 → 1 bridge | ❌ Create |
| `session_diary` | Flows 1,5 (consolidation) | ✅ Exists (pipelines.db, 22 rows) |

### Search Infrastructure

| Component | Purpose | Status |
|---|---|---|
| Milvus-lite (`unified_vectors`) | Vector search (Flows 1,5) | ✅ Running (351 entities, wrong data) |
| FTS5 indexes (4) | Keyword search (Flow 2) | ❌ Create: notes_fts, documents_fts, work_items_fts, knowledge_cards_fts |
| SearXNG (`:8080`) | Web search (Flow 3) | ✅ Running |
| pplx-embed-v1 (`:18099`) | Embedding server | ✅ Running (systemd, 1024d) |

### What's Deferred (Not Now)

| Component | Why Defer |
|---|---|
| `audit_trail` | No consumer reads it |
| `calendars` / `calendar_events` | Real but not wired yet |
| `crew_members` / `model_endpoints` | Odysseus manages its own config |
| `scheduled_tasks` / `task_runs` | Automation not built yet |
| RRF hybrid search | No evidence of missed retrievals |
| 4-channel project resolution | One writer, explicit project_id works |

---

## Live Feature Audit (2026-06-04)

### Verified Working

| Feature | Transport | Outcome |
|---|---|---|
| `council-recall` | MCP SSE `:18097` | ✅ 3-channel recall (vector + structural + execution) |
| `query_session_diary` | MCP SSE + HTTP `:18098` | ⚠️ LIKE search works but weak |
| `reconcile_open_items` | MCP SSE + HTTP | ✅ Dedup across diary entries |
| `memsearch_index_file` | MCP SSE + HTTP | ✅ Works, pplx HTTP `:18099` |
| `memsearch_status` | MCP SSE + HTTP | ✅ 351 entities in Milvus |
| Codegraph tools (12) | MCP SSE only | ✅ FTS5 on 94K nodes |
| `review.start/log/verdict` | MCP SSE + HTTP | ✅ Review lifecycle |
| `upsert_summary` | MCP SSE + HTTP | ✅ Persists to consolidation_cache |

### What's Broken

| Feature | Problem | Fix |
|---|---|---|
| council-recall Ch.1 | bge-m3 ONNX → pplx HTTP | ✅ Switched 2026-06-04 |
| council-recall Ch.3 | `LIKE ?` on artifacts/event_log | FTS5 on content/message |
| query_session_diary | `LIKE ?` on 3 columns | FTS5 on (decisions, open_items, work_completed) |
| memsearch | bge-m3 direct ONNX | ✅ pplx HTTP `:18099` (2026-06-04) |
| unified_log_recall | Sync socket checks, >5s timeout | Async, per-channel 2s timeout |
| Vector store | Indexes chat summaries, not canonical knowledge | Index memories, session_diary, consolidation_cache, knowledge_cards |
| Project scoping | Client-side filter after full retrieval | Milvus dynamic field for server-side filter |

---

## Five Gaps — What Needs To Happen

### Gap 1: Embedding Server (START — P0) ✅ CLOSED 2026-06-04

**Problem:** pplx-embed-v1 model (688MB, 1024d, 32K ctx) exists on disk. `server.py` exists. Server is NOT running. System uses bge-m3 (450MB, 8K ctx) which is inferior for code/web content.

**Fix:** Start `server.py` on `:18099`. Point Memsearch and council-recall at it.

**Done:**
- `server.py` port changed 18097 → 18099, `/health` endpoint added, error handling added
- `~/.config/systemd/user/pplx-embed.service` created, enabled, running
- All MemSearch call sites (index.py, db_poller.py, layer.py, file_watcher.py) → `openai` provider at `:18099/v1`
- Odysseus `embeddings.py` default model → `pplx-embed-v1-0.6b`, default URL → `:18099`
- all-MiniLM fastembed cache deleted (~87MB freed)
- ChromaDB deprecation warning added to `chroma_client.py`

**Verification:**
- `curl http://127.0.0.1:18099/health` → `{"status": "ok", "model": "pplx-embed-v1-0.6b", "dims": 1024}`
- Memsearch search returns results via pplx HTTP
- Odysseus `get_embedding_client()` → pplx HTTP, 1024-dim

---

### Gap 2: FTS5 Indexes (BUILD — P0)

**Problem:** All keyword search uses `LIKE ?` — no stemming, no ranking, full table scan. `query_session_diary("decisions")` returns 0 results because content doesn't contain the word "decisions".

**Fix:** Create FTS5 virtual tables on content-bearing tables.

**Tables to index:**
- `session_diary` → `session_diary_fts(decisions, open_items, work_completed)`
- `artifacts` → `artifacts_fts(content)`
- `event_log` → `event_log_fts(message)`
- Future: `notes_fts`, `documents_fts`, `work_items_fts`, `knowledge_cards_fts`

**Files:**
- `migrations/10_fts5_indexes.sql` — CREATE VIRTUAL TABLE statements
- `memory_service/router.py` — replace LIKE with FTS5 MATCH
- `memory_service/layer.py` — replace LIKE with FTS5 MATCH in council-recall Ch.3

**Effort:** ~30 min

---

### Gap 3: Vector Store Re-index (BUILD — P1)

**Problem:** Milvus has 351 entities from chat summaries + daily logs (ephemeral). Does NOT index memories, session_diary, consolidation_cache, or knowledge_cards (canonical).

**Fix:** Index canonical knowledge tables into Milvus. Source-tag each entry.

**Files:**
- `memory_service/vector_store.py` — UnifiedVectorStore class (rename from MemIndex)
- `memory_service/layer.py` — index memories, session_diary, consolidation_cache on write
- Drop ChromaDB imports from Odysseus code

**Effort:** ~30 min

---

### Gap 4: Project Scoping (BUILD — P1)

**Problem:** `project_id` param accepted by council-recall but not enforced in Milvus. Client-side filtering after full retrieval works at 351 entities, breaks at 35K.

**Fix:** Add `project_id` column to existing Council tables. Add project_id as Milvus dynamic field.

**Files:**
- `migrations/11_projects.sql` — projects table + ALTER TABLE for project_id columns
- `memory_service/store.py` — `get_or_create_project()`, `_resolve_project()`
- `memory_service/vector_store.py` — project_id in Milvus dynamic fields

**Effort:** ~20 min

---

### Gap 5: Log Recall Timeout (FIX — P2)

**Problem:** `unified_log_recall` does synchronous socket checks on multiple ports + queries 10 channels. Takes >5 seconds. Agent times out.

**Fix:** Async health checks with 2s per-channel timeout. Prune unused channels.

**Files:**
- `memory_service/layer.py` — `unified_log_recall()` async rewrite
- `memory_service/health.py` — async socket checks

**Effort:** ~30 min

---

## Anti-Patterns

| Anti-Pattern | Why | Instead |
|---|---|---|
| LIKE queries for search | No stemming, no ranking, slow | FTS5 indexes |
| Multiple embedding models | Inconsistent scores, wasted RAM | Single: pplx-embed-v1 |
| Direct ChromaDB access | Bypasses unified vector store | Route through UnifiedVectorStore |
| `project_id` as free text | No dedup, no FK enforcement | `REFERENCES projects(id)` with slug dedup |
| Client-side vector filtering | Full scan, breaks at scale | Milvus dynamic fields (server-side) |
| Sync socket checks in recall | Blocks agent, causes timeout | Async with per-channel timeout |
| Knowledge without project scope | Orphaned data, impossible to filter | Explicit project_id at insert |

---

## Decisions

| Decision | Rationale |
|---|---|
| SQLite, not PostgreSQL | All existing backends are SQLite. PG is empty. |
| Single embedding model | pplx-embed-v1: bidirectional, 32K ctx, code-aware, ONNX INT8 |
| Milvus-lite, not ChromaDB | Embedded, no external service, ChromaDB not running |
| CodeGraph in separate file | Different access patterns, retention, backup strategy |
| No users table | Single admin. Username-based ownership. |
| Explicit project_id at insert | One writer. 4-channel cascade over-engineered. |
| FTS5 before RRF fusion | Measure misses first, build fusion second. |
| Soft-delete, not archive table | Simpler. One table. `status` column. |

---

## Verification Checklist

- [x] pplx server responds on `:18099/v1/models` — ✅ systemd managed
- [x] council-recall uses pplx embeddings (not bge-m3) — ✅ all MemSearch sites switched
- [ ] FTS5 indexes exist on session_diary, artifacts, event_log
- [ ] query_session_diary uses FTS5 MATCH (not LIKE)
- [ ] council-recall Ch.3 uses FTS5 MATCH (not LIKE)
- [ ] Milvus indexes memories, session_diary, consolidation_cache, knowledge_cards
- [x] `projects` table exists with UNIQUE slug — ✅
- [ ] `project_id` column on session_diary, raw_session_memories, consolidation_cache, artifacts
- [ ] project_id filter works server-side in Milvus (not client-side)
- [ ] unified_log_recall completes in <2s (async, per-channel timeout)
- [x] ChromaDB imports removed from Odysseus code — ✅ deprecation warning added
- [x] CodeGraph tools accessible via MCP SSE — ✅
- [ ] All existing tests pass (no regression)

---

## Current State of Execution (2026-06-04)

> **Database topology:** `pipelines.db` = legacy backup (untouched). `council_core.db` = single canonical DB. `codegraph.db` = planned separate DB (not yet extracted).

### council_core.db — Live Schema

| Table | Rows | Serves | Status |
|---|---|---|---|
| `projects` | 2 | Flows 2,4,5 (scoping) | ✅ Created, seeded |
| `sessions` | 2 | All flows (context anchor) | ✅ Migrated from Odysseus app.db |
| `chat_messages` | 9 | Flow 1 (conversation history) | ✅ Migrated from Odysseus app.db |
| `memories` | 0 | Flow 1 (semantic recall) | ✅ Schema created |
| `notes` | 0 | Flow 2 (user content) | ✅ Schema created |
| `documents` | 0 | Flow 2 (user content) | ✅ Schema created |
| `work_items` | 3 | Flow 4 (task tracking) | ✅ Created, migrated from pipelines |
| `research_reports` | 0 | Flow 3 (research storage) | ✅ Schema created |
| `knowledge_cards` | 0 | Flow 3 → 1 bridge | ✅ Schema created |
| `memory_entries` | 124 | Flows 1,5 (replaces session_diary) | ✅ Unified table: entry_type (diary/raw/summary/incident/decision), tier, FTS5 indexed |
| `memory_rollups` | 2 | Flows 1,5 (replaces consolidation_cache) | ✅ Unified table: tier, window_start/end, summary |
| `reviews` | 2 | Review lifecycle | ✅ Created |
| `review_findings` | 11 | Review findings | ✅ Migrated from pipelines.db |
| `workflow_runs` | 3 | Execution tracking | ✅ Created with project_id FK |
| `prompt_templates` | 0 | Reusable prompts | ✅ Schema created |

### FTS5 Indexes — Live

| FTS5 Table | Source Table | Entries | Status |
|---|---|---|---|
| `memory_entries_fts` | memory_entries (title, body) | 124 | ✅ |
| `knowledge_cards_fts` | knowledge_cards (topic, title, body) | 0 | ✅ |
| `work_items_fts` | work_items (title, description) | 3 | ✅ |
| `chat_messages_fts` | chat_messages (content) | 9 | ✅ |
| `notes_fts` | notes (title, content) | 0 | ✅ |
| `documents_fts` | documents (title, current_content) | 0 | ✅ |
| `research_reports_fts` | research_reports (query, summary, findings) | 0 | ✅ |
| `review_findings_fts` | review_findings (title, summary, evidence) | 11 | ✅ |

### project_id Column Coverage

| Table | Has project_id | Status |
|---|---|---|
| `work_items` | ✅ | FK → projects(id) |
| `workflow_runs` | ✅ | FK → projects(id) |
| `reviews` | ✅ | FK → projects(id) |
| `research_reports` | ✅ | FK → projects(id) |
| `memory_entries` | ❌ | **Missing — needs ALTER TABLE** |
| `memory_rollups` | ❌ | **Missing — needs ALTER TABLE** |
| `knowledge_cards` | ❌ | **Missing — needs ALTER TABLE** |

### CouncilCoreStore — Wired Components

| Component | Status |
|---|---|
| `CouncilCoreStore` class | ✅ `memory_service/council_core_store.py` |
| `mem.council_core` property | ✅ Wired in `MemoryService.__init__` |
| `get_or_create_project()` | ✅ Slug dedup, FK-safe |
| `get_work_items()` | ✅ Filtered by project_id, kind, status |
| `create_knowledge_card()` | ✅ With tags, confidence, source_run_id |
| `search_knowledge_cards()` | ✅ Keyword search on title/body/topic |
| `get_memory_entries()` | ✅ Filtered by entry_type, tier |
| `get_memory_rollups()` | ✅ Filtered by tier |
| `get_sessions()` / `get_chat_messages()` | ✅ |
| `get_reviews()` / `get_review_findings()` | ✅ |
| `get_workflow_runs()` | ✅ |
| `health_check()` | ✅ Returns status + row counts |

### Five Gaps — Current Status

| Gap | Plan | Current | Delta |
|---|---|---|---|
| **1: Embedding Server** (P0) | Start pplx on `:18099` | ✅ Running (systemd, 1024d, all consumers switched). | **Closed 2026-06-04** |
| **2: FTS5 Indexes** (P0) | FTS5 on session_diary, artifacts, event_log | ✅ 8 FTS5 tables on council_core.db. Covers new schema (memory_entries replaces session_diary). Old pipelines.db tables (artifacts, event_log) NOT indexed — they stay in legacy DB. | **Closed for new schema** |
| **3: Vector Re-index** (P1) | Index canonical knowledge into Milvus | ❌ Milvus still indexes chat summaries (351 entities). Not re-indexed for council_core.db. | **Open** |
| **4: Project Scoping** (P1) | project_id on all knowledge tables | ⚠️ `projects` table exists. `project_id` on work_items, workflow_runs, reviews, research_reports. **Missing** on memory_entries, memory_rollups, knowledge_cards. | **Partial** |
| **5: Log Recall Timeout** (P2) | Async rewrite of unified_log_recall | ❌ Still synchronous, >5s timeout. | **Open** |

### What Was NOT Done (Intentionally Deferred)

| Item | Reason |
|---|---|
| CodeGraph extraction to `codegraph.db` | Phase 0 not executed. cg_* tables still in pipelines.db. |
| `project_id` on memory_entries, memory_rollups, knowledge_cards | Schema created without it. Needs ALTER TABLE migration. |
| pplx embedding server | ✅ Running on `:18099` (systemd). All consumers switched 2026-06-04. |
| ChromaDB removal from Odysseus vendor | ✅ Deprecation warning added. `chroma_client.py` logs warning on import. ChromaDB not running. |
| Odysseus wired to council_core.db | `.env.council` + `start-council.sh` created. But Odysseus SQLAlchemy models expect different column names (`rag` vs `has_rag`, `archived` vs `is_archived`). Direct swap blocked until column mapping resolved. |
| UnifiedVectorStore (Phase 4) | Not implemented. MemIndex uses pplx HTTP `:18099` (was bge-m3 ONNX). |
| UnifiedSearchRouter (Phase 6) | Not implemented. No RRF fusion. |

### Source DBs — Untouched

| Database | Path | Tables | Status |
|---|---|---|---|
| `pipelines.db` | `~/.council-memory/pipelines.db` | 32 | ✅ Legacy backup, untouched |
| `app.db` | `vendor/odysseus/data/app.db` | 24 | ✅ Legacy backup, untouched |

### Verification Checklist — Updated

| Check | Status |
|---|---|
| pplx server responds on `:18099/v1/models` | ✅ Running, systemd managed |
| council-recall uses pplx embeddings (not bge-m3) | ✅ All MemSearch call sites use pplx HTTP |
| FTS5 indexes exist on canonical tables | ✅ 8 FTS5 tables on council_core.db |
| `projects` table exists with UNIQUE slug | ✅ |
| `project_id` column on work_items, workflow_runs, reviews | ✅ |
| `project_id` column on memory_entries, memory_rollups, knowledge_cards | ❌ Missing |
| project_id filter works server-side in Milvus | ❌ Client-side only |
| unified_log_recall completes in <2s | ❌ Sync, >5s timeout |
| ChromaDB imports removed from Odysseus code | ✅ Deprecation warning added, service not running |
| CodeGraph tools accessible via MCP SSE | ✅ |
| All existing tests pass (no regression) | ✅ |
| **Score** | **8/12** |
