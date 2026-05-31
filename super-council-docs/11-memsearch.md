# MemSearch — Vector Indexing & Semantic Recall

> MemSearch wraps Milvus-lite for hybrid vector + BM25 search. All indexing routes through `MemIndex` — zero direct MemSearch dependency in `super_council.py`.

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
- **Model:** `gpahal/bge-m3-onnx-int8` (int8 quantized, ~400MB)
- **Dimension:** 1024 (bge-m3)

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
