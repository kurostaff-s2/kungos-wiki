# MemSearch — Vector Indexing & Semantic Recall

> MemSearch (by Zilliz/Milvus creators) is cross-platform semantic memory for AI coding agents. We use it as a vector recall layer via `MemIndex` — zero direct MemSearch dependency in `super_council.py`.

**Upstream:** [github.com/zilliztech/memsearch](https://github.com/zilliztech/memsearch) — plugins for Claude Code, Codex CLI, OpenClaw, OpenCode + Python API for custom agents.

## Design Philosophy (Upstream)

**Markdown is the source of truth.** Milvus is a "shadow index" — derived, rebuildable, always in sync with `.md` files.

```
Markdown files (source of truth)
  │
  ▼
memsearch watch (live file watcher)
  │ detects file change
  ▼
re-chunk → SHA-256 hash each chunk
  │
  ├─ hash unchanged? → skip (no embed, no upsert)
  └─ hash new/changed? → embed → upsert to Milvus
```

**Intended recall is 3-layer progressive:**
1. **L1 search** — `memsearch search "query"` → ranked chunks
2. **L2 expand** — `memsearch expand <chunk_hash>` → full `.md` section
3. **L3 transcript** — `parse-transcript <session.jsonl>` → raw dialogue

**Intended maintenance:** `memsearch compact` — LLM-powered chunk summarization, compresses old chunks into daily summaries.

### What MemSearch Is Good At

| Feature | How It Works |
|---------|-------------|
| **Hybrid search** | Dense vector (COSINE) + BM25 sparse + RRF reranking |
| **Smart dedup** | SHA-256 content hashing — unchanged chunks skip embedding entirely |
| **Live sync** | `memsearch watch` — file watcher auto-indexes on change |
| **Progressive recall** | 3 layers: search → expand (full section) → transcript (raw dialogue) |
| **Cross-agent memory** | Same Milvus index shared across Claude Code, Codex, OpenClaw, OpenCode |
| **Compact** | LLM-powered chunk summarization — compresses old chunks into daily summaries |

### What We Use vs. What We Don't

| Feature | Intended (Upstream) | Our Usage |
|---------|---|---|
| **Source** | Persistent `.md` files in `.memsearch/memory/` | `/tmp/trace-*` (deleted after index) + real files |
| **Sync** | `memsearch watch` — live file watcher | Manual `index_file()` calls, no watcher |
| **Dedup** | SHA-256 hash — skips unchanged chunks | No dedup — re-embeds every time |
| **Recall** | 3-layer progressive (search → expand → transcript) | Single-layer search only (`top_k=5`) |
| **Compact** | `memsearch compact` — LLM summarization | Not used |
| **Expand** | `memsearch expand <hash>` — full section | Not used |

## Architecture

```
super_council.py
  └── memory_service.indexer.*    (Python API)
        └── MemIndex              (owns lifecycle, config, locking)
              └── MemSearch       (external package, owned by memory service only)
                    └── MilvusStore (Milvus-lite, local *.db file)
```

**Location:** `memory_service/index.py` (MemIndex), `memory_service/memsearch_wrapper.py` (ProjectAwareMemSearch)

### Components

| Component | File | Role |
|-----------|------|------|
| `MemIndex` | `memory_service/index.py` | Vector indexing service, lifecycle, locking |
| `ProjectAwareMemSearch` | `memory_service/memsearch_wrapper.py` | project_id tagging + type filtering |
| `MemSearch` | `memsearch` package (external) | Chunking, embedding, Milvus client |
| `MilvusStore` | `memsearch/store.py` (external) | Milvus-lite collection, upsert, search |

### Dependency Isolation

**`super_council.py` has zero direct MemSearch dependency.** All vector indexing and search route through `memory_service.indexer` (single source of truth).

Removed in 2026-05-28 refactor:
- `CouncilMemory._auto_index_file()` → replaced by `MemIndex.index_file()`
- `_active_recall()` MemSearch boilerplate → `memory_service.indexer.search()`
- Raw `from memsearch import MemSearch` import → eliminated

### Graceful Degradation

MemSearch is optional. If the `memsearch` package is not installed or `memsearch.enabled = false` in config:
- `MemIndex.available` → `False`
- `index_file()` → returns `False` immediately, no error
- `search()` → returns `[]` immediately, no error
- `stats()` → returns `{"available": False}`

All callers handle this transparently. Vector recall is a quality-of-life feature, not a hard dependency.

## Indexing Pipeline

### File Indexing (Current — `MemIndex.index_file()`)

```
File path → MemIndex.index_file(path)
  → fcntl.flock() (non-blocking, released on death)
  → MemSearch(path) → ProjectAwareMemSearch
  → ms.index_file(path) → chunk_markdown() → embed → upsert
  → Tag project_id + type (code/spec/doc/review)
```

- **Locking:** `fcntl.flock()` on `~/.council-memory/.memsearch.lock` — non-blocking, auto-released on process death
- **Type inference:** `ProjectAwareMemSearch.infer_type(path)` — `code`, `spec`, `doc`, `review`
- **Project tagging:** Client-side upsert of `project_id` dynamic field on chunk hashes
- **Fire-and-forget:** Failures logged at debug level, never block the calling pipeline

### Raw Session Memory Indexing (Current — Temp File)

```
raw_text → upsert_raw_session_memory() → DB (raw_session_memories)
  → _try_index_raw_memory() → tempfile.mkstemp(prefix="trace-{id[:16]}-")
  → MemIndex.index_file(tmp_path) → chunk → embed → upsert
  → os.unlink(tmp_path)  (delete temp file)
```

**Problem:** The temp file is created in `/tmp/`, indexed, then deleted. MemSearch stores the file path as `source` metadata, so recall results reference deleted files (`/tmp/trace-*`).

### Direct Text Upsert (Proposed — No Temp File)

```
raw_text → upsert_raw_session_memory() → DB (raw_session_memories)
  → _try_index_raw_memory() → chunk_markdown(raw_text, source="raw_session_memories:{trace_id}")
  → embed_and_store(chunks) → store.upsert(records)
```

**Eliminates temp file entirely.** Uses Milvus `store.upsert(chunks)` directly:

```python
# Current: file-based (temp file churn)
fd, path = tempfile.mkstemp(prefix="trace-{id[:16]}-", suffix=".md")
os.write(fd, raw_text.encode())
ms.index_file(path)  # reads file → chunks → embeds → upserts
os.unlink(path)       # deletes temp file

# Proposed: direct text upsert
from memsearch.chunker import chunk_markdown
chunks = chunk_markdown(raw_text, source=f"raw_session_memories:{trace_id}")
embeddings = await embedder.embed([c.content for c in chunks])
records = [
    {
        "chunk_hash": compute_chunk_id(...),
        "content": chunk.content,
        "embedding": embeddings[i],
        "source": f"raw_session_memories:{trace_id}",
        "project_id": "council-memory",
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }
    for i, chunk in enumerate(chunks)
]
ms.store._client.upsert(collection_name=collection, data=records)
```

**Benefits:**
- No `/tmp/` churn or stale source paths
- `source` field points to actual DB row (`raw_session_memories:trace-{id}`)
- Same vector quality, same semantic search
- Eliminates file I/O overhead

**Trade-off:** `chunk_markdown()` and `_embed_and_store()` are internal APIs (underscored). Could break on memsearch upgrade. Mitigation: pin memsearch version or wrap in try/except.

### Persistent Source Files (Proper Fix — Per Upstream Design)

The direct text upsert above is a workaround. The **proper fix** (per memsearch architecture) is:

1. Write raw session memories to persistent `.md` files (`~/.council-memory/traces/trace-{id}.md`)
2. Use `memsearch watch` on that directory
3. Milvus becomes a true shadow index — always rebuildable from the `.md` files

```
raw_text → upsert_raw_session_memory() → DB (raw_session_memories)
  → Write ~/.council-memory/traces/trace-{id}.md (persistent, 14-day TTL)
  → memsearch watch detects file → chunks → SHA-256 hash → embed → upsert
  → Source field: ~/.council-memory/traces/trace-{id}.md (valid, rebuildable)
```

**Benefits over direct upsert:**
- True shadow index — `memsearch reset --yes` rebuilds from `.md` files
- Live sync — `memsearch watch` auto-indexes on file change
- SHA-256 dedup — unchanged files skip embedding
- Progressive recall — L2 `expand` and L3 `transcript` work on real files
- Compact — `memsearch compact` summarizes old chunks

**Trade-off:** Disk space for `.md` files (same content already in DB, but gives memsearch its intended source-of-truth contract).

## What We're Missing

| Gap | Impact | Fix |
|-----|--------|-----|
| **Live watcher** | Manual `index_file()` calls needed everywhere | `memsearch watch ~/.council-memory/traces/` |
| **SHA-256 dedup** | Re-embeds identical content every session | Use persistent `.md` files + watch |
| **Progressive recall** | Only get chunk snippets, not full context | L2 `expand` + L3 `transcript` |
| **Compact** | Old chunks accumulate forever | `memsearch compact` on schedule |
| **Source of truth** | `/tmp/trace-*` deleted after index | Persistent `.md` files in `~/.council-memory/traces/` |

## Milvus Schema

Milvus-lite collection schema (created by `MilvusStore._ensure_collection()`):

| Field | Type | Notes |
|-------|------|-------|
| `chunk_hash` | VARCHAR(64) | Primary key |
| `embedding` | FLOAT_VECTOR | Dense vector (1536-dim, COSINE) |
| `content` | VARCHAR(65535) | Chunk text, enables analyzer |
| `sparse_vector` | SPARSE_FLOAT_VECTOR | Auto-generated by BM25 function from `content` |
| `source` | VARCHAR(1024) | File path or DB reference |
| `heading` | VARCHAR(1024) | Markdown heading |
| `heading_level` | INT64 | Heading depth (1-6) |
| `start_line` | INT64 | First line of chunk |
| `end_line` | INT64 | Last line of chunk |
| `project_id` | Dynamic | Client-side tag (not in schema) |
| `type` | Dynamic | Client-side tag: code/spec/doc/review |

**BM25 function:** `sparse_vector` is auto-generated from `content` via `FunctionType.BM25` — do not include it in upsert dicts.

## Search

### Hybrid Search (Dense + BM25 with RRF)

```python
ms.search(query, top_k=10)
```

Returns hybrid results: dense vector (COSINE) + BM25 full-text, reranked with RRF (Reciprocal Rank Fusion).

### Project-Aware Search

```python
pms = ProjectAwareMemSearch(ms)
results = pms.search(query, project_id="council-memory", type_filter="code")
```

Client-side filtering (memsearch v0.4.x lacks server-side `filter_expr`). Filters `project_id` and `type` from metadata after retrieval.

### MemIndex Search (Public API)

```python
memory_service.indexer.search(
    query="how does X work",
    project_id="council-memory",
    limit=10,
)
# Returns: list of dicts with content, source, score, metadata
```

## Configuration

**Location:** `memory_service/memory-config.json`

```json
{
  "memsearch": {
    "enabled": true,
    "milvus_uri": "~/.memsearch/milvus.db",
    "collection": "memsearch_chunks"
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Toggle vector indexing on/off |
| `milvus_uri` | `~/.memsearch/milvus.db` | Local Milvus-lite DB path |
| `collection` | `memsearch_chunks` | Milvus collection name |

### Embedding Provider

Hard-coded in `MemIndex` (not configurable via JSON):

```python
MemSearch(
    embedding_provider="onnx",
    embedding_model="gpahal/bge-m3-onnx-int8",
    milvus_uri=...,
    collection=...,
)
```

- **Provider:** ONNX (CPU, no GPU required)
- **Model:** `gpahal/bge-m3-onnx-int8` (int8 quantized, ~600MB)
- **Dimension:** 1024 (bge-m3)

### Embedding Stack — Two Models, Same Dimension

| Component | Model | Dimension | Format | Location |
|-----------|-------|-----------|--------|----------|
| **memsearch** (vector search) | `gpahal/bge-m3-onnx-int8` | 1024 | ONNX INT8, HuggingFace Hub | `~/.cache/huggingface/` |
| **MicroModelEnricher** (failure classification) | `pplx-embed-v1-0.6b-int8` | 1024 | ONNX INT8, local | `~/models/embedding/` |

Both are **INT8 quantized** — not fine-tunable as-is (quantization destroys gradient paths).

## Fine-Tuning Options

### A: Fine-Tune bge-m3 (memsearch) — Feasible, High Effort

```
bge-m3 (FP16, ~2GB) → fine-tune on our corpus → export ONNX INT8 → replace model
```

- **Training data:** Our own corpus (raw_session_memories, session_diary, review_findings, artifacts, docs)
- **Approach:** Contrastive learning (`MultipleNegativesRankingLoss`) — positive pairs: same-domain text; negative pairs: random
- **Tool:** `sentence-transformers` library
- **Cost:** ~4-8 hours on GPU

**Hardware caveat:** Arc A380 (SYCL) won't run standard PyTorch fine-tuning. Options:
1. CPU fine-tuning (slow, ~24-48 hours)
2. Cloud GPU (Colab/Kaggle free tier, ~2 hours)
3. Cross-encode approach (lighter, ~1 hour on CPU)

**Benefit:** Embeddings tuned to our domain (council workflows, code reviews, memory patterns).

### B: Cross-Encoder Reranker — Low Effort, High Impact

```
memsearch search (bge-m3, fast) → cross-encoder rerank (fine-tuned, slow but accurate)
```

- **How it works:** bge-m3 retrieves top-20 candidates → cross-encoder scores them → return top-5
- **Fine-tuning:** Cross-encoders are smaller (~300M params), easier to fine-tune on relevance judgments
- **Tool:** `sentence-transformers` cross-encoder
- **Benefit:** Dramatically better ranking without re-embedding the entire corpus

### C: Swap to pplx-embed-v1 (Unified Model)

```
Use pplx-embed-v1-0.6b-int8 for BOTH memsearch AND MicroModelEnricher
```

- **How:** Change memsearch config to use local model instead of HuggingFace Hub
- **Benefit:** One model, consistent embeddings, already on disk
- **Trade-off:** pplx-embed-v1 is 700MB vs bge-m3 600MB, marginal quality difference

### D: Metadata-Enhanced Retrieval — Zero Fine-Tuning, Immediate Impact

```
Instead of fine-tuning the model, enrich the metadata:
- source: "raw_session_memories:trace-{id}" (already proposed)
- type: "workflow" vs "documentation"
- phase: "RED" / "GREEN" / "REFACTOR"
- project_id: "council-memory"
- recency: created_at timestamp
```

- **How:** Add metadata fields to Milvus chunks, use them for post-retrieval filtering
- **Benefit:** Better recall without any model changes
- **Effort:** ~30 lines (metadata enrichment in upsert path)

### Recommendation: D → B → A (if needed)

1. **D (metadata enrichment)** — Free, immediate quality gains. Enabled by dual-channel design (DB poller + file watcher).
2. **B (cross-encoder reranker)** — If metadata filtering isn't enough, add a fine-tuned reranker for the top-K results.
3. **A (full fine-tune)** — Only if B doesn't close the gap. Expensive, hardware-constrained, but highest ceiling.

Measure recall quality after D is in place, then decide if B or A is warranted.

## Data Flow — Raw Session Memories

```
Assistant message (auto-detected, scored >= 4)
  → upsert_summary MCP tool
  → RelationalStore.upsert_raw_session_memory(raw_text, source_file)
    → INSERT INTO raw_session_memories (trace_id, raw_text, expires_at=now+14d)
    → Background thread: _try_index_raw_memory(trace_id, raw_text)
      → chunk_markdown(raw_text, source="raw_session_memories:{trace_id}")
      → embed → upsert to Milvus
  → 14-day TTL (expires_at), queryable via query_raw_session_memories()
```

**DB table:** `raw_session_memories` (pipelines.db)
- `trace_id` TEXT PRIMARY KEY
- `date` TEXT — entry date
- `source_file` TEXT — origin (e.g. "auto-detected-assistant-message")
- `raw_text` TEXT — full message content
- `created_at` TEXT — ISO timestamp
- `expires_at` INTEGER — epoch (14-day TTL)
- `is_indexed` INTEGER — vector index flag

**Vector store:** `~/.memsearch/milvus.db`
- Chunks of raw_text with embeddings
- Source field: `raw_session_memories:trace-{id}` (proposed) or `/tmp/trace-*` (current)
- No automatic TTL — chunks persist until explicitly deleted

## File Locations

| Resource | Path |
|----------|------|
| MemIndex source | `super_council/memory_service/index.py` |
| ProjectAwareMemSearch | `super_council/memory_service/memsearch_wrapper.py` |
| Milvus-lite DB | `~/.memsearch/milvus.db` |
| Lock file | `~/.council-memory/.memsearch.lock` |
| MemSearch package | `~/.local/lib/python3.12/site-packages/memsearch/` |

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `memsearch` | v0.4.x | Vector indexing, chunking, embedding |
| `milvus-lite` | (via memsearch) | Local vector DB (*.db file) |
| `onnxruntime` | (via memsearch) | ONNX embedding inference |
| `pymilvus` | (via memsearch) | Milvus client library |

## Health & Diagnostics

```bash
# Check memsearch availability
python3 -c "from super_council.memory_service import load; svc = load(); print(svc.indexer.stats())"

# Check Milvus DB exists
ls -la ~/.memsearch/milvus.db

# Check lock file
ls -la ~/.council-memory/.memsearch.lock
```

**Health endpoint:** `GET /health` → `"memsearch": {"status": "available"}` (via `memory_service.indexer.stats()`)

## Upstream CLI Reference

```bash
# Setup
memsearch config init                              # interactive setup wizard
memsearch config set embedding.provider onnx       # switch embedding provider
memsearch config set milvus.uri http://localhost:19530  # switch Milvus backend

# Index & Search
memsearch index ./memory/                          # index markdown files
memsearch index ./memory/ --force                  # re-embed everything
memsearch search "Redis caching"                   # hybrid search (BM25 + vector)
memsearch search "auth flow" --top-k 10 --json     # JSON for scripting
memsearch expand <chunk_hash>                      # show full section around a chunk

# Live Sync & Maintenance
memsearch watch ./memory/                          # live file watcher (auto-index on change)
memsearch compact                                  # LLM-powered chunk summarization
memsearch stats                                    # show indexed chunk count
memsearch reset --yes                              # drop all indexed data and rebuild
```

**We use none of these directly** — all indexing goes through `MemIndex.index_file()` (Python API). The CLI is available for manual maintenance and debugging.

## Usage Call Sites

| Caller | What It Does | Frequency |
|--------|-------------|-----------|
| `_active_recall()` in `super_council.py:3828` | Pre-dispatch: "what past solutions exist for this phase?" → injects into subagent prompt | Every delegation |
| `_active_recall_structured()` in `super_council.py:3888` | Same but returns JSON for programmatic consumers | Every delegation |
| `recall.unified()` in `layer.py:1087` | Channel 1a: vector search across all indexed content | Every recall query |
| `_run_startup_consolidation()` in `super_council.py:8430` | Indexes consolidation output file for future recall | Arc summarizer runs |
| `upsert_raw_session_memory()` → `_try_index_raw_memory()` in `store.py:1057` | Indexes raw assistant messages (via temp file) | Every auto-detected message |
