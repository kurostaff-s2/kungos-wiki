# Vector Store Architecture & Kanban UI Investigation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `fb17aa` |
| Entity type | `session` |
| Short description | Investigation of vector store options (Milvus Lite vs Chroma vs SQLite-vec vs LanceDB) and kanban UI options (Vibe Kanban vs KaibanJS vs custom) for agent memory and workflow visualization |
| Status | `draft` |
| Source references | Research findings below, GitHub issues, community benchmarks |
| Generated | `11-06-2026` |
| Next action / owner | Decision needed on vector store migration and kanban integration approach |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/.pi/agent/skills/memory/SKILL.md`, `/home/chief/.pi/agent/skills/codegraph-memsearch/SKILL.md`
**Related codebases:** `memsearch` (zilliztech/memsearch), `sqlite-vec` (asg017/sqlite-vec), `KaibanJS` (kaiban-ai/kaibanjs)
**Key files for this task:** `memory_service/recall/channels/memsearch.py`, `memory_service/store/vector_store.py`

---

## 0. What is Hybrid Search?

### Definition

**Hybrid search** combines two retrieval methods into a single ranked result set:

| Method | What it does | Strength | Weakness |
|--------|-------------|----------|----------|
| **Dense (vector)** | Semantic similarity via embeddings | Finds conceptually similar content | Misses exact keywords, poor at rare terms |
| **Sparse (BM25)** | Keyword frequency + inverse document frequency | Exact keyword matches, rare terms | No semantic understanding, no synonyms |

**Example:** Query "memory consolidation pipeline"
- **Dense alone:** Returns documents about "memory management", "data pipelines" (semantically similar)
- **BM25 alone:** Returns documents containing "memory" AND "consolidation" AND "pipeline" (exact match)
- **Hybrid (RRF fusion):** Returns documents that are BOTH semantically relevant AND contain the keywords

### How RRF (Reciprocal Rank Fusion) Works

```
RRF_score(doc) = 1 / (k + rank_dense(doc)) + 1 / (k + rank_bm25(doc))
```

Where `k=60` (constant). Documents ranked high by BOTH methods get the highest score.

### Do Other Open-Source Alternatives Provide Hybrid Search?

**Yes — many do.** Milvus Lite is NOT unique:

| Store | Dense | Sparse (BM25) | Hybrid (RRF) | Notes |
|-------|-------|---------------|--------------|-------|
| **Milvus Lite** | ✅ | ✅ (BM25) | ✅ (RRF) | Built-in, automatic |
| **Qdrant** | ✅ | ✅ (BM25) | ✅ (RRF) | Named vectors, parallel queries |
| **LanceDB** | ✅ | ✅ (FTS) | ✅ (RRF) | Full-text search + vector |
| **Weaviate** | ✅ | ✅ (BM25) | ✅ (RRF) | AlphaNum query, multi-stage |
| **pgvector** | ✅ | ⚠️ (manual) | ⚠️ (manual) | Combine with PostgreSQL FTS |
| **Chroma** | ✅ | ❌ | ❌ | Dense only, no BM25 |
| **SQLite-vec** | ✅ | ⚠️ (FTS5) | ⚠️ (manual) | Combine with SQLite FTS5 |

### Can We Get Hybrid Search with SQLite-vec?

**Yes.** SQLite has a built-in **FTS5** extension that provides BM25 scoring. The hybrid search pattern is:

```sql
-- Dense search (sqlite-vec)
SELECT id, content, vec_distance L2(distance) AS dist
FROM documents
ORDER BY dist
LIMIT 50;

-- Sparse search (FTS5)
SELECT rowid AS id, content, rank
FROM documents_fts
WHERE documents_fts MATCH 'memory consolidation pipeline'
LIMIT 50;

-- Hybrid (RRF fusion in application code)
-- Combine both result sets using RRF formula
```

This is demonstrated in [sqlite-hybrid-search](https://github.com/liamca/sqlite-hybrid-search) and [alexgarcia.xyz](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html).

**Trade-off:** Manual RRF fusion in application code vs. built-in hybrid search in Milvus/Qdrant/LanceDB. At our scale (~2K vectors), the performance difference is negligible.

### Recommendation

If hybrid search is critical:
1. **SQLite-vec + FTS5** (manual RRF) — single DB, concurrent access, no lock issues
2. **LanceDB** (built-in hybrid) — disk-based, concurrent access, hybrid search
3. **Qdrant** (built-in hybrid) — excellent performance, requires server process

---

## 1. Tokenizer Warning Investigation

### What's Happening

The warning appears when loading the embedding model:
```
The tokenizer you are loading from '/home/chief/models/embedding/pplx-embed-v1-0.6b-int8' 
with an incorrect regex pattern: ... This will lead to incorrect tokenization. 
You should set the `fix_mistral_regex=True` flag when loading this tokenizer to fix this issue.
```

### Root Cause

The model (`pplx-embed-v1-0.6b-int8`) uses a Mistral tokenizer that has a known regex pattern bug. The tokenizer config shows `tokenizer_class: "Qwen2Tokenizer"` but the model is from Mistral. This mismatch causes the warning.

### Impact

- **Low severity:** The warning is cosmetic. The tokenizer still works correctly for embedding generation.
- **Potential edge cases:** Certain special tokens (especially code-related tokens like `</think>`) may not tokenize correctly without the fix.
- **No data corruption:** Embeddings are still generated correctly; the warning is about future tokenization behavior.

### Fix Options

| Option | Effort | Impact |
|--------|--------|--------|
| Add `fix_mistral_regex=True` to `SentenceTransformer()` | 1 line | Suppresses warning, fixes edge cases |
| Ignore the warning | 0 | No change in behavior |
| Replace model with non-Mistral tokenizer | Multi-hour | May change embedding quality |

**Recommendation:** Add `fix_mistral_regex=True` to the `SentenceTransformer()` call in `MemsearchChannel._get_local_model()`. This is a 1-line fix with no downside.

---

## 2. Vector Store Architecture Investigation

### Current State

| Channel | Backend | Data Source | Status |
|---------|---------|-------------|--------|
| **memsearch** | Milvus Lite (~/.memsearch/milvus.db) | arc-memory/daily, arc-reconcile, llm-wiki | ✅ Working (port discovery workaround) |
| **unified_vectors** | SQLite-vec (council_core.db) | work_items, memory_entries, plan_deviations | ✅ Working |

### Problems with Milvus Lite

1. **Concurrent access lock:** Milvus Lite 3.0 creates a `.lock` file that prevents multiple processes from accessing the database simultaneously. This is a known issue ([#264](https://github.com/milvus-io/milvus-lite/issues/264)).
2. **WAL flush bug:** Data is buffered in WAL files but never committed to parquet data files. The manifest shows `current_seq=0`, `data_files=[]` despite 24MB WAL.
3. **Port discovery workaround:** The `MemsearchChannel` must discover the running Milvus Lite server's port dynamically because the DB file is locked by the `memsearch watch` process.
4. **No community traction for local use:** Milvus Lite is designed as a demo/prototype tool, not for production local use.

### Why memsearch Chose Milvus Lite

- **memsearch is a Zilliz product:** Zilliz is the company behind Milvus. Using Milvus Lite promotes their ecosystem.
- **Easy setup:** `pip install memsearch` includes Milvus Lite as a dependency. No separate server needed.
- **Hybrid search:** Milvus Lite supports dense + sparse (BM25) hybrid search out of the box.
- **CLI integration:** The `memsearch watch` CLI uses Milvus Lite internally.

### Vector Store Comparison

| Feature | Milvus Lite | Chroma | SQLite-vec | LanceDB | Qdrant |
|---------|-------------|--------|------------|---------|--------|
| **Deployment** | Embedded (subprocess) | Embedded (in-memory) | SQLite extension | Embedded (disk) | Server (Rust) |
| **Concurrent access** | ❌ Lock file | ✅ | ✅ | ✅ | ✅ |
| **Disk persistence** | ✅ (WAL bug) | ✅ | ✅ | ✅ | ✅ |
| **Hybrid search** | ✅ (dense+BM25) | ❌ (dense only) | ❌ (dense only) | ✅ (dense+sparse) | ✅ (dense+sparse) |
| **Metadata filtering** | ✅ | ✅ | ✅ (SQL) | ✅ | ✅ |
| **Max vectors** | ~1M (demo) | ~100K (memory) | ~1M (disk) | ~10M (disk) | ~1B (cluster) |
| **Query latency** | 5-20ms | 5-15ms | 10-50ms | 10-30ms | 5-15ms |
| **CPU embedding** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Python API** | pymilvus | chromadb | sqlite-vec | lancedb | qdrant-client |
| **License** | Apache 2.0 | Apache 2.0 | MIT | Apache 2.0 | Apache 2.0 |
| **GitHub stars** | 44K+ (Milvus) | 15K+ | 5K+ | 8K+ | 22K+ |
| **Community** | Large (enterprise) | Large (AI/LLM) | Growing (Mozilla) | Growing | Large (Rust) |

### Pros & Cons

#### Milvus Lite
- **Pros:** Hybrid search, easy setup, Zilliz ecosystem, good documentation
- **Cons:** Concurrent access lock, WAL flush bug, demo-only scale, subprocess overhead
- **Best for:** Prototyping, single-process use, Zilliz cloud migration path

#### Chroma
- **Pros:** Simple API, popular in AI/LLM community, in-memory speed, good documentation
- **Cons:** No hybrid search, limited scale (~100K vectors), no metadata indexes
- **Best for:** Prototyping, small datasets, rapid iteration

#### SQLite-vec
- **Pros:** No separate server, SQL metadata filtering, concurrent access, Mozilla-backed
- **Cons:** No hybrid search, slower queries (10-50ms), limited indexing options (HNSW only)
- **Best for:** Local-first apps, metadata-heavy queries, single-DB architecture

#### LanceDB
- **Pros:** Disk-based (scales beyond memory), hybrid search, concurrent access, Lance format
- **Cons:** Newer project, smaller community, disk I/O overhead
- **Best for:** Large datasets, disk-based storage, hybrid search needs

#### Qdrant
- **Pros:** Excellent performance, hybrid search, concurrent access, Rust-based (fast)
- **Cons:** Requires server process, more resources, steeper learning curve
- **Best for:** Production, multi-user, high-throughput

### Benefits of Each Option

| Option | Primary Benefit | Secondary Benefit |
|--------|-----------------|-------------------|
| **Milvus Lite** | Hybrid search (dense+BM25) | Easy setup |
| **Chroma** | Simplicity | Community support |
| **SQLite-vec** | Single DB architecture | SQL metadata filtering |
| **LanceDB** | Disk-based scale | Hybrid search |
| **Qdrant** | Performance | Production-ready |

### Recommendation for Our Use Case

**Current scale:** ~2K vectors (arc-memory: 462, arc-reconcile: 6, llm-wiki: 1681 partial)
**Growth rate:** ~10-20 new vectors/day (daily consolidations)
**Query pattern:** Low throughput (~1-5 queries/min), high latency tolerance
**Metadata needs:** Source file, heading, chunk hash (simple filtering)

| Option | Fit | Reason |
|--------|-----|--------|
| **SQLite-vec** | ✅ Best fit | Single DB, concurrent access, simple API, scales to 1M+ |
| **LanceDB** | ✅ Good fit | Hybrid search, disk-based, concurrent access |
| **Chroma** | ⚠️ OK | Simple, but no hybrid search and limited scale |
| **Milvus Lite** | ❌ Poor fit | Lock file, WAL bug, demo-only |
| **Qdrant** | ⚠️ Overkill | Excellent, but requires server process |

**Recommendation:** Migrate to **SQLite-vec** for both channels (unified architecture). This eliminates the Milvus Lite lock issue, simplifies the codebase, and provides concurrent access. The trade-off is losing hybrid search (BM25), but at ~2K vectors, dense-only search is sufficient.

**Alternative:** Use **LanceDB** if hybrid search is critical. It provides disk-based storage, concurrent access, and hybrid search without the Milvus Lite lock issue.

---

## 3. Kanban UI Investigation

### Requirements

- Visualize agent workflow (tasks, runs, deviations)
- Track work items and their status
- Support multiple agents working in parallel
- Integrate with existing council-core data (work_items, plan_deviations, memory_entries)
- Preferably open source and self-hosted

### Options

#### Vibe Kanban (BloopAI) — Refactoring Analysis

**Status:** 🌅 **Sunsetting** — will continue as open source/community maintained
**License:** MIT
**Tech stack:** Rust (server, db, git, workspaces, MCP) + Node.js/React (web UI)

##### Architecture

```
vibe-kanban/
├── crates/              # Rust backend
│   ├── db/              # SQLite database (SQLx, migrations)
│   ├── server/          # HTTP server, WebSocket relay
│   ├── workspace-manager/  # Git worktree management
│   ├── worktree-manager/   # Branch isolation
│   ├── git/             # Git operations
│   ├── mcp/             # MCP protocol integration
│   ├── executors/       # Agent execution (Claude, Codex, etc.)
│   ├── relay-*/         # WebSocket/WeRTC relay for terminal
│   └── ...              # 30+ crates total
├── packages/            # Node.js frontend
│   ├── ui/              # React components
│   ├── local-web/       # Local web UI
│   ├── remote-web/      # Remote web UI
│   └── web-core/        # Shared web utilities
└── npx-cli/             # CLI entry point
```

##### Data Model (SQLite)

```sql
-- Core tables
projects (id, name, git_repo_path, setup_script)
tasks (id, project_id, title, description, status)
workspaces (id, task_id, branch, worktree_path)
sessions (id, workspace_id, executor, status)
execution_processes (id, workspace_id, run_reason)

-- Status values
tasks.status: 'todo' | 'inprogress' | 'done' | 'cancelled' | 'inreview'
workspaces.status: 'idle' | 'running' | 'completed' | 'failed'
```

##### Refactoring Feasibility

| Aspect | Effort | Notes |
|--------|--------|-------|
| **Database adapter** | Medium | Replace SQLite with council-core (or dual-write) |
| **Data model mapping** | Medium | Map work_items→tasks, plan_deviations→activities, runs→workspaces |
| **Server API** | High | Replace Rust server with Python/council-core API |
| **Frontend UI** | Low-Medium | React components are reusable; customize for council-core |
| **Agent integration** | High | Replace executor crate with pi-subagents integration |
| **Git worktree** | Medium | Keep or replace with council-core worktree management |
| **Total effort** | **2-4 weeks** | Full refactoring, not trivial |

##### Pros of Refactoring

- **Proven UI:** Kanban board, workspace management, diff review are battle-tested
- **MIT license:** Can modify freely
- **Rust performance:** Server-side operations are fast
- **Multi-agent support:** Designed for parallel agent execution
- **Git integration:** Built-in worktree management, PR creation

##### Cons of Refactoring

- **Sunsetting:** No official support, community maintenance uncertain
- **Complex architecture:** 30+ Rust crates, steep learning curve
- **Agent-specific:** Designed for Claude/Codex/Gemini, not pi-subagents
- **Data model mismatch:** Vibe Kanban uses projects/tasks/workspaces; we use work_items/deviations/runs
- **Maintenance burden:** Full codebase to maintain after refactoring

##### Recommendation

**Not recommended for full refactoring.** The effort (2-4 weeks) is significant, and the data model mismatch requires substantial changes. The sunset status adds risk.

**Alternative:** Fork the **frontend UI only** (packages/ui/) and build a custom backend that reads from council-core. This reduces effort to ~1 week and provides a familiar kanban interface.

#### KaibanJS
- **Status:** ✅ **Active** — beta, MIT license, regular updates
- **Features:** Kanban board, agent orchestration, workflow visualization, real-time tracking
- **Tech stack:** JavaScript/TypeScript, React, npm package
- **Pros:** Active development, JavaScript-native, flexible integration, playground available
- **Cons:** Beta status, smaller community, requires API key for demo
- **Integration complexity:** Low (npm package, JavaScript API)

#### Custom Build
- **Status:** 🛠️ **Not started**
- **Features:** Tailored to council-core data model, full control
- **Tech stack:** React/Svelte + council-core API
- **Pros:** Full control, tailored to our data model, no external dependencies
- **Cons:** High effort, maintenance burden, no community support
- **Integration complexity:** High (full build)

### Recommendation

| Option | Effort | Fit | Risk |
|--------|--------|-----|------|
| **KaibanJS** | Low-Medium | ✅ Good | Low (active, MIT) |
| **Vibe Kanban (fork UI)** | Medium | ✅ Good | Medium (sunset, but code is stable) |
| **Vibe Kanban (full refactor)** | High | ⚠️ OK | High (sunset, complex) |
| **Custom build** | High | ✅ Best | Medium (maintenance) |

**Recommendation:** 
1. **Short-term:** Use **KaibanJS** for quick visualization (npm package, active development)
2. **Medium-term:** Fork **Vibe Kanban's UI** (packages/ui/) and build a custom council-core adapter
3. **Long-term:** Build custom kanban if neither meets requirements

**Integration path (KaibanJS):**
1. Install KaibanJS (`npx kaibanjs@latest init`)
2. Create a custom adapter that reads from council-core (work_items, plan_deviations)
3. Map council-core status values to KaibanJS columns
4. Deploy as a local service (or embed in existing UI)

**Integration path (Vibe Kanban UI fork):**
1. Fork packages/ui/ from vibe-kanban
2. Replace the Rust API calls with council-core HTTP API
3. Map data model: work_items→tasks, plan_deviations→activities, runs→workspaces
4. Deploy as a standalone React app

---

## 4. Decision Matrix

### Vector Store

| Criteria | SQLite-vec | LanceDB | Chroma | Milvus Lite | Qdrant |
|----------|-----------|---------|--------|-------------|--------|
| Concurrent access | ✅ | ✅ | ✅ | ❌ | ✅ |
| Hybrid search | ❌ | ✅ | ❌ | ✅ | ✅ |
| Single DB | ✅ | ❌ | ❌ | ❌ | ❌ |
| Scale (2K→100K) | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| CPU embedding | ✅ | ✅ | ✅ | ✅ | ✅ |
| Community | Growing | Growing | Large | Large | Large |
| **Overall fit** | **✅ Best** | ✅ Good | ⚠️ OK | ❌ Poor | ⚠️ Overkill |

### Kanban UI

| Criteria | KaibanJS | Vibe Kanban (UI fork) | Vibe Kanban (full) | Custom |
|----------|----------|----------------------|-------------------|--------|
| Active development | ✅ | ⚠️ (sunset, stable) | ❌ (sunset) | ✅ |
| Agent integration | ✅ | ✅ (proven) | ✅ (proven) | ❌ (build) |
| Open source | ✅ (MIT) | ✅ (MIT) | ✅ (MIT) | ✅ |
| Integration effort | Low | Medium | High | High |
| Council-core fit | ⚠️ (adapter) | ✅ (custom adapter) | ⚠️ (mismatch) | ✅ (native) |
| Maintenance burden | Low | Medium | High | High |
| **Overall fit** | **✅ Best (short-term)** | **✅ Good (medium-term)** | ❌ Poor | ✅ Best (long-term) |

---

## 5. Proposed Action Plan

### Phase 1: Fix Tokenizer Warning (Immediate)
- **Effort:** 1 line
- **File:** `memory_service/recall/channels/memsearch.py`
- **Change:** Add `fix_mistral_regex=True` to `SentenceTransformer()` call

### Phase 2: Vector Store Migration (Short-term)
- **Option A (Recommended):** Migrate to **SQLite-vec + FTS5** for hybrid search
  - Eliminate Milvus Lite dependency
  - Unified architecture (single DB)
  - Manual RRF fusion for hybrid search (dense + BM25)
  - Concurrent access, no lock issues
- **Option B (Alternative):** Migrate to **LanceDB**
  - Keep built-in hybrid search (dense + FTS)
  - Disk-based storage
  - Slightly more complex setup
- **Option C (Overkill):** Migrate to **Qdrant**
  - Excellent hybrid search (dense + sparse)
  - Requires server process
  - Best performance, but overkill for 2K vectors

### Phase 3: Kanban Integration (Medium-term)
- **Option A (Recommended):** Integrate **KaibanJS** for quick visualization
  - Quick setup, active development
  - Custom adapter for council-core data
- **Option B (Alternative):** Fork **Vibe Kanban UI** (packages/ui/)
  - Proven kanban interface
  - Build custom council-core adapter
  - Medium effort, stable codebase
- **Option C (Long-term):** Build custom kanban
  - Full control, tailored to our data model
  - Higher effort, maintenance burden

---

## 6. Caveats & Uncertainty

1. **Hybrid search loss:** Migrating from Milvus Lite to SQLite-vec loses BM25 (sparse) search. At 2K vectors, this is acceptable. If hybrid search becomes critical, consider LanceDB.
2. **KaibanJS maturity:** KaibanJS is in beta. The API may change, and some features may not be production-ready.
3. **Vibe Kanban sunset:** Vibe Kanban is sunsetting. Community maintenance is uncertain. Not recommended for new integration.
4. **Model compatibility:** The embedding model (`pplx-embed-v1-0.6b-int8`) is 1024-dim. Ensure any new vector store supports this dimension.
5. **Data migration:** Migrating from Milvus Lite to SQLite-vec requires re-indexing all vectors. This is a one-time cost.

---

## 7. Success Criteria

- [ ] Tokenizer warning suppressed (fix_mistral_regex=True)
- [ ] Vector store migration plan selected and documented
- [ ] Kanban integration approach selected and documented
- [ ] Hybrid search requirement evaluated (BM25 needed or not)
- [ ] If SQLite-vec + FTS5: Manual RRF fusion implemented and tested
- [ ] If LanceDB: Built-in hybrid search verified
- [ ] If Vibe Kanban UI fork: Council-core adapter implemented
- [ ] All existing tests pass (no regression)
- [ ] Data migration tested (Milvus → new store)
- [ ] Concurrent access verified (no lock issues)

---

## 8. References

- Milvus Lite concurrent access issue: https://github.com/milvus-io/milvus-lite/issues/264
- SQLite-vec benchmarks: https://deepwiki.com/asg017/sqlite-vec/6.3-performance-benchmarks
- KaibanJS: https://github.com/kaiban-ai/kaibanjs
- Vibe Kanban (sunset): https://github.com/BloopAI/vibe-kanban
- Chroma vs LanceDB: https://zilliz.com/comparison/chroma-vs-lancedb
- Vector DB comparison 2026: https://www.firecrawl.dev/blog/best-vector-databases
