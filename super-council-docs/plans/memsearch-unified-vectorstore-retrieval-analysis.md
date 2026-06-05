# First Principles Analysis: MemSearch & UnifiedVectorStore Data Retrieval

> **Generated:** 2026-06-05
> **Scope:** Real-data retrieval via MemSearch, UnifiedVectorStore, FTS5, and the unified recall fusion layer
> **Reference proposal:** `00-prompt-handoff/05-06-2026_mcp-tools-unified-vector-analytics_2b3bff.md`
> **Reference docs:** `14-recall-search-fine-tuning.md`, `11-memsearch.md`, `09-memory-service.md`

---

## 1. Problem Essence

**Core problem:** An AI coding agent needs to retrieve relevant past knowledge across sessions — decisions, code patterns, review findings, session summaries — fast enough to inject into prompts without exhausting token budgets.

**So what? chain:**

```
"We need memsearch + UnifiedVectorStore"
  → so semantic search works across all memory types
  → so the agent can recall relevant context without scanning everything
  → so each session starts with informed context, not a blank slate
  → so the agent doesn't repeat mistakes or reinvent solutions
  ← GROUND TRUTH: Knowledge must survive across sessions and be retrievable by meaning, not just keywords.
```

**Success criteria (measurable):**

- Recall latency < 500ms for vector search, < 5ms for FTS5
- Results are project-scoped (no cross-project contamination)
- Graceful degradation when components are unavailable
- Token-budgeted output (doesn't overflow context windows)

---

## 2. How Data Is Actually Retrieved — The Real Pipeline

The system has **three distinct retrieval channels**, not one. Understanding which channel serves which outcome is critical.

### Channel 1: MemSearch (File-Based Vector Index)

**What it indexes:** Markdown files on disk — docs, specs, reviews, chat summaries, code files.

**How retrieval works:**

```
Query → MemIndex.search()
  → MemSearch(query, top_k=N)
  → Milvus hybrid search (COSINE dense + BM25 sparse + RRF reranking)
  → ProjectAwareMemSearch client-side filters (project_id, type)
  → Returns ranked chunks with content, source, score
```

**Key implementation detail:** `ProjectAwareMemSearch` applies **client-side filtering** because memsearch v0.4.x lacks server-side `filter_expr`. This means it fetches top-K results from Milvus, then filters in Python. If the top-K doesn't include the project's results, you get zero hits.

**Source:** `memory_service/index.py` (MemIndex), `memory_service/memsearch_wrapper.py` (ProjectAwareMemSearch)

**Serves:** `unified_recall()` Channel 1a (text memory), direct file indexing via `memsearch_index_file` MCP tool.

### Channel 2: UnifiedVectorStore (Database-Content Vector Index)

**What it indexes:** SQLite rows — `session_diary`, `consolidation_cache` entries (structured workflow data that doesn't exist as files).

**How retrieval works:**

```
Query → UnifiedVectorStore.search()
  → httpx POST to pplx-embed-v1 on :18099
  → Milvus search with SERVER-SIDE filter_expr (project_id, source)
  → Returns ranked results with source, source_id, score
```

**Key advantage over MemSearch:** Server-side filtering via Milvus `filter_expr` — no client-side filtering needed. This is architecturally cleaner but uses a different embedding endpoint (HTTP API vs. local ONNX).

**Source:** `memory_service/vector_store.py`

**Serves:** Currently only auto-reindex on startup. Not yet wired into MCP tools (that's what the proposal handoff is for).

### Channel 3: FTS5 + Relational Queries (Keyword/Structural)

**What it queries:** SQLite tables directly — `session_diary`, `event_log`, `artifacts`, `raw_session_memories`, `consolidation_cache`.

**How retrieval works:**

```
Query → ContextRouter methods
  → FTS5 MATCH (stemming, ranking, multi-term)
  → OR LIKE '%query%' (legacy fallback)
  → Returns structured rows
```

**Source:** `memory_service/router.py` (ContextRouter)

**Serves:** `query_session_diary()`, `find_similar_runs()`, `get_review_findings()`, `get_recent_events()`, `query_raw_session_memories()`.

### The Fusion Layer — `unified_recall()`

The `MemoryLayer.unified_recall()` method orchestrates all three channels:

```
Channel 1a: MemSearch vector search (top_k=5)        → text memory
Channel 1b: ContextRouter artifacts                   → structured artifacts
Channel 1c: ContextRouter review findings             → review events
Channel 2:  (Structural graph — workflow definitions)  → only if query matches workflow keywords
Channel 3:  ContextRouter find_similar_runs           → execution history
Channel 4:  ContextRouter query_session_diary          → auto-upserted summaries
Channel 5:  ContextRouter query_raw_session_memories   → recent context (min 3KB budget)
Channel 6:  ContextRouter query_raw_session_memories   → raw traces (14-day lookback)

→ Fused with token budget (max_tokens * 4 chars)
→ Ordered: Recent Context → Text → Structural → Execution → Diary → Raw Traces
```

**Source:** `memory_service/layer.py` (lines 1042–1400)

---

## 3. Assumptions Challenged

| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| "Two vector stores (MemSearch + UnifiedVectorStore) are needed" | Technical | Both use Milvus-lite, both use pplx-embed-v1. Different embedding paths (ONNX local vs HTTP :18099). Different filtering (client-side vs server-side). | **Investigate** — Could be unified, but current split has rationale (files vs DB rows) |
| "Client-side filtering is acceptable for MemSearch" | Technical | If project has <K results in top-K, returns nothing. No server-side filter_expr in v0.4.x. | **Keep with caveat** — Works for small collections; becomes unreliable at scale |
| "Auto-reindex on startup is sufficient" | Technical | UnifiedVectorStore re-indexes ALL data on every startup. O(N) cost every launch. No incremental indexing. | **Investigate** — Should use triggers or change-data-capture for incremental updates |
| "Analytics logging to flat JSON files is sufficient" | Technical | File-based analytics means no concurrent-write safety, no aggregation queries. `get_analytics_summary()` re-parses entire file every call. | **Keep for now** — Low write volume, but will need DB-backed analytics at scale |
| "Token-budgeted fusion is the right approach" | Architectural | Char budget (max_tokens * 4) is a rough approximation. Different channels have different information density. | **Keep** — Good enough for current scale; could improve with semantic scoring |
| "DbIndexPoller 30s interval is optimal" | Technical | 30s means up to 30s of staleness. Polls 4 tables, 50 rows each. | **Keep** — Acceptable trade-off between freshness and CPU |

---

## 4. Ground Truths

1. **Embedding dimension is fixed at 1024** — Both bge-m3 (MemSearch) and pplx-embed-v1 (UnifiedVectorStore) produce 1024-dim vectors. This is a hardware/model constraint, not a design choice.

2. **Milvus-lite is local-file SQLite-backed** — No network latency for Milvus itself. All latency comes from embedding generation (HTTP to :18099 for UnifiedVectorStore, ONNX for MemSearch).

3. **Graceful degradation is mandatory** — MemSearch, UnifiedVectorStore, linter, enricher all fail silently. The system must work with zero vector search capability. This is a hard requirement, not optional.

4. **Token budgets are the hard constraint** — LLM context windows are finite. Every retrieval channel competes for the same budget. The fusion layer must prioritize.

5. **Data arrives in two forms** — Files (markdown, code) and database rows (structured workflow data). These have fundamentally different indexing requirements.

---

## 5. Outcome Analysis — What Each Module Gets, From Which Channel

### Module → Channel → Outcome Map

| Module / Consumer | What It Needs | Which Channel Serves It | Outcome Type |
|-------------------|---------------|------------------------|--------------|
| **SlotSupervisor** (`_active_recall()`) | "What past solutions exist for this phase?" | MemIndex.search() → MemSearch | **Semantic recall** — finds similar patterns across files |
| **Pi Extension** (`recall.unified`) | Fused context for agent prompt injection | All 6 channels via unified_recall() | **Token-budgeted context** — multi-source fusion |
| **Pi Extension** (`recall.context_slice`) | Context for a specific run | MemoryLayer.get_context_slice() | **Run-scoped artifacts** — narrow, deep |
| **Pi Extension** (`recall.recent_events`) | Recent execution events | ContextRouter.get_recent_events() | **Temporal recall** — what happened recently |
| **Pi Extension** (`recall.run_snapshot`) | Full run state | ContextRouter.get_run_snapshot() | **State reconstruction** — complete picture |
| **Pi Extension** (`recall.summarize_issues`) | Categorized failures | ContextRouter.summarize_run_issues() | **Failure diagnosis** — structured issues |
| **Pi Extension** (`recall.review_findings`) | Recent review findings | ContextRouter.get_review_findings() | **Quality signals** — review outcomes |
| **ArcPipeline** (consolidation) | Active context for summarization | consolidation_cache direct query | **Continuity context** — what's current |
| **DbIndexPoller** | Unindexed rows → Milvus | SQLite poll → chunk → embed → upsert | **Index maintenance** — keeps vectors fresh |
| **DocFileWatcher** | File changes → Milvus | File watcher → MemSearch watch | **Index maintenance** — keeps files indexed |

### Outcome Types (Categorized)

1. **Semantic Recall** — "Find things similar to this query" (MemSearch vector search)
2. **Keyword Recall** — "Find things containing these terms" (FTS5 MATCH)
3. **Temporal Recall** — "What happened in the last N days" (ContextRouter time-range queries)
4. **State Reconstruction** — "What is the current state of run X" (snapshots, artifacts)
5. **Failure Diagnosis** — "What went wrong and why" (issue summaries, review findings)
6. **Index Maintenance** — "Keep the vector index in sync" (poller, watcher)

---

## 6. Proposal vs. Reality Gap

The handoff proposal (`05-06-2026_mcp-tools-unified-vector-analytics`) plans to wire two new MCP tools:

### Current State

| Planned Tool | What It Does | Current State | Gap |
|-------------|--------------|---------------|-----|
| `vector_search` | Expose UnifiedVectorStore.search() via MCP | UnifiedVectorStore exists but is NOT passed to MemoryMCPHandler | **Phase 1 needed** — wire vector_store to handler |
| `analytics_summary` | Expose get_analytics_summary() via MCP | analytics.py exists with get_analytics_summary() | **Phase 2 needed** — register as MCP tool |

### What This Means

The vector store works, but agents inside pi sessions cannot query it directly. They get the *fused* output from `unified_recall()`, but cannot target UnifiedVectorStore specifically. The proposal fills this gap.

### What the Proposal Misses

1. **UnifiedVectorStore is not yet called from `unified_recall()`** — The fusion layer uses MemSearch (Channel 1a) but NOT UnifiedVectorStore. The reindex happens on startup, but search results aren't part of the 6-channel fusion.

2. **No incremental indexing for UnifiedVectorStore** — Every startup re-indexes everything. Should use DB triggers or `is_indexed` flag (like DbIndexPoller has for MemSearch).

3. **Analytics tools are read-only diagnostics** — They inform decisions but don't change behavior. The proposal's P2 (caching based on analytics) is deferred until 48-72h of data exists.

---

## 7. Module Relevance Map

```
super_council.py (SlotSupervisor)
├── _active_recall() → MemIndex.search() → MemSearch → Milvus (bge-m3)
└── _active_recall_structured() → same path, JSON output

memory_service/layer.py (MemoryLayer)
├── unified_recall() → ALL channels (fusion orchestrator)
│   ├── 1a: MemSearch (vector, files)
│   ├── 1b: ContextRouter.artifacts (FTS5/DB)
│   ├── 1c: ContextRouter.review_findings (FTS5/DB)
│   ├── 2:  Store.workflow_definitions (DB)
│   ├── 3:  ContextRouter.find_similar_runs (DB)
│   ├── 4:  ContextRouter.session_diary (DB)
│   ├── 5:  ContextRouter.raw_session_memories (DB)
│   └── 6:  ContextRouter.raw_session_memories (DB, wider)
└── get_context_slice() → ContextRouter.artifacts

memory_service/router.py (ContextRouter)
├── find_similar_runs() → FTS5 + LIKE queries
├── get_recent_events() → event_log time-range query
├── get_run_snapshot() → pipeline + event_log + artifacts JOIN
├── summarize_run_issues() → event_log categorization
├── get_review_findings() → event_log review-filter
├── query_session_diary() → session_diary FTS5
├── query_raw_session_memories() → raw_session_memories time-range
└── get_startup_context() → consolidation_cache active entry

memory_service/vector_store.py (UnifiedVectorStore)
├── search() → pplx-embed-v1 HTTP → Milvus server-side filter
├── index() → pplx-embed-v1 HTTP → Milvus insert
└── reindex_existing_data() → DB poll → embed → upsert
    [NOT YET EXPOSED AS MCP TOOL]

memory_service/analytics.py
├── log_embedding_request() → JSON line to file
├── log_search_request() → JSON line to file
└── get_analytics_summary() → parse files → aggregate stats
    [NOT YET EXPOSED AS MCP TOOL]

memory_service/db_poller.py (DbIndexPoller — Channel A)
├── _poll_loop() → 30s interval background thread
├── _poll_table() → WHERE is_indexed = 0 LIMIT 50
├── _upsert_records() → chunk → embed → Milvus upsert
└── _mark_indexed() → SET is_indexed = 1

memory_service/file_watcher.py (DocFileWatcher — Channel B)
├── start() → MemSearch(paths=watch_dirs).watch()
└── Monitors: ~/llm-wiki/super-council-docs/, ~/.council-memory/daily/, ~/.council-memory/specs/
```

---

## 8. Stress Test — Where The System Breaks

### Scenario 1: Milvus directory fills up

Both MemSearch and UnifiedVectorStore share `~/.memsearch/milvus.db`. No size limits, no eviction policy. Chunks accumulate forever.

**Impact:** Disk exhaustion, slower searches.
**Mitigation:** Add `memsearch compact` schedule or TTL-based eviction.

### Scenario 2: pplx-embed-v1 server (:18099) goes down

UnifiedVectorStore._get_embedding() fails with httpx timeout. All search() calls return `[]`. MemSearch uses local ONNX (bge-m3), so it continues working.

**Impact:** Half the vector search capability lost.
**Mitigation:** Graceful degradation already in place (`_available` flag). Could add fallback to ONNX path.

### Scenario 3: Client-side filtering misses results

MemSearch returns top-K=5, but project-specific results are at position 6-10. Client-side filter removes all 5.

**Impact:** Zero results for project-scoped queries when collection is large.
**Mitigation:** Increase top_K for filtered queries, or migrate to server-side filtering.

### Scenario 4: Analytics log grows large

`get_analytics_summary()` reads entire file into memory, parses every line. O(N) per call.

**Impact:** Slow analytics at high query volume.
**Mitigation:** Rotate log files, or migrate to SQLite-backed analytics.

### Scenario 5: DbIndexPoller races with writes

Poller reads `is_indexed = 0` rows, application writes new rows simultaneously. New rows might be missed until next cycle.

**Impact:** Up to 30s staleness window.
**Mitigation:** Acceptable for current scale. Could reduce interval or add trigger-based indexing.

---

## 9. Conclusion

### Current State

The retrieval architecture is **functionally complete but partially exposed**. The data flows correctly through three channels (MemSearch files, UnifiedVectorStore DB-rows, FTS5 keyword), and `unified_recall()` fuses them well. However, UnifiedVectorStore and analytics are internal-only — not accessible as MCP tools.

### Key Insight

The two-vector-store split (MemSearch for files, UnifiedVectorStore for DB rows) is justified by the ground truth that data arrives in two fundamentally different forms. But they share Milvus storage, use the same embedding dimension (1024), and could theoretically share the embedding endpoint if MemSearch were configured to use the HTTP endpoint instead of local ONNX.

### What the Proposal Correctly Addresses

Exposing `vector_search` and `analytics_summary` as MCP tools closes the gap between internal capability and agent-accessible tools. The proposal's phased approach (wire → register → test) is sound.

### Confidence & Revisit Triggers

**Confidence:** High — based on direct code reading of all relevant modules (vector_store.py, index.py, layer.py, router.py, analytics.py, mcp_server.py, db_poller.py, file_watcher.py, memsearch_wrapper.py, config.py, __init__.py).

**Revisit when:**
- Collection size exceeds 10K chunks (client-side filtering becomes unreliable)
- Embedding latency consistently > 500ms (need caching or model swap)
- Analytics shows >50% repeated queries within 5min (need embedding cache, P2)
- UnifiedVectorStore startup re-index takes > 10s (need incremental indexing)
- Milvus DB exceeds 2GB (need eviction or compaction policy)

---

## Appendix: File Locations

| Component | File Path |
|-----------|-----------|
| MemIndex | `super_council/memory_service/index.py` |
| ProjectAwareMemSearch | `super_council/memory_service/memsearch_wrapper.py` |
| UnifiedVectorStore | `super_council/memory_service/vector_store.py` |
| Analytics | `super_council/memory_service/analytics.py` |
| MemoryLayer (unified_recall) | `super_council/memory_service/layer.py` |
| ContextRouter | `super_council/memory_service/router.py` |
| MemoryMCPHandler | `super_council/memory_service/mcp_server.py` |
| DbIndexPoller | `super_council/memory_service/db_poller.py` |
| DocFileWatcher | `super_council/memory_service/file_watcher.py` |
| MemoryConfig | `super_council/memory_service/config.py` |
| MemoryService | `super_council/memory_service/__init__.py` |
| Milvus DB | `~/.memsearch/milvus.db` |
| Analytics logs | `~/.council-memory/analytics/` |
| Pipelines DB | `~/.council-memory/pipelines.db` |
