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

#### Vibe Kanban (BloopAI)
- **Status:** 🌅 **Sunsetting** — will continue as open source/community maintained
- **Features:** Kanban board, workspace management, agent orchestration, diff review, PR creation
- **Agents supported:** Claude Code, Codex, Gemini CLI, GitHub Copilot, Amp, Cursor, OpenCode, Droid, CCR, Qwen Code
- **Tech stack:** Rust backend, React frontend, npm package
- **Pros:** Designed for AI agents, multi-agent support, built-in diff review
- **Cons:** Sunsetting, community maintenance uncertain, may not be updated
- **Integration complexity:** Medium (requires npm, Rust, agent authentication)

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
| **Vibe Kanban** | Medium | ⚠️ OK | High (sunset) |
| **Custom build** | High | ✅ Best | Medium (maintenance) |

**Recommendation:** Start with **KaibanJS** for quick visualization. It's active, MIT-licensed, and designed for AI agent workflows. If it doesn't meet our needs, consider a custom build tailored to council-core.

**Integration path:**
1. Install KaibanJS (`npx kaibanjs@latest init`)
2. Create a custom adapter that reads from council-core (work_items, plan_deviations)
3. Map council-core status values to KaibanJS columns
4. Deploy as a local service (or embed in existing UI)

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

| Criteria | KaibanJS | Vibe Kanban | Custom |
|----------|----------|-------------|--------|
| Active development | ✅ | ❌ (sunset) | ✅ |
| Agent integration | ✅ | ✅ | ❌ (build) |
| Open source | ✅ (MIT) | ✅ (MIT) | ✅ |
| Integration effort | Low | Medium | High |
| Council-core fit | ⚠️ (adapter) | ⚠️ (adapter) | ✅ (native) |
| **Overall fit** | **✅ Best** | ⚠️ OK | ✅ Best (long-term) |

---

## 5. Proposed Action Plan

### Phase 1: Fix Tokenizer Warning (Immediate)
- **Effort:** 1 line
- **File:** `memory_service/recall/channels/memsearch.py`
- **Change:** Add `fix_mistral_regex=True` to `SentenceTransformer()` call

### Phase 2: Vector Store Migration (Short-term)
- **Option A (Recommended):** Migrate to SQLite-vec for both channels
  - Eliminate Milvus Lite dependency
  - Unified architecture (single DB)
  - Lose hybrid search (BM25) — acceptable at 2K vectors
- **Option B (Alternative):** Migrate to LanceDB
  - Keep hybrid search
  - Disk-based storage
  - Slightly more complex setup

### Phase 3: Kanban Integration (Medium-term)
- **Option A (Recommended):** Integrate KaibanJS
  - Quick setup, active development
  - Custom adapter for council-core data
- **Option B (Long-term):** Build custom kanban
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
- [ ] Migration implementation completed (if approved)
- [ ] All existing tests pass (no regression)
- [ ] Hybrid search evaluated (BM25 needed or not)
- [ ] Data migration tested (Milvus → new store)

---

## 8. References

- Milvus Lite concurrent access issue: https://github.com/milvus-io/milvus-lite/issues/264
- SQLite-vec benchmarks: https://deepwiki.com/asg017/sqlite-vec/6.3-performance-benchmarks
- KaibanJS: https://github.com/kaiban-ai/kaibanjs
- Vibe Kanban (sunset): https://github.com/BloopAI/vibe-kanban
- Chroma vs LanceDB: https://zilliz.com/comparison/chroma-vs-lancedb
- Vector DB comparison 2026: https://www.firecrawl.dev/blog/best-vector-databases
