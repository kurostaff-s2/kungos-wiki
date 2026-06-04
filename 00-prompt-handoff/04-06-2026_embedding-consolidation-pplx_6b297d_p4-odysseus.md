# Phase 4: Point Odysseus at pplx HTTP

**Parent plan:** `04-06-2026_embedding-consolidation-pplx_6b297d.md`
**Phase:** 4 of 6
**Dependencies:** Phase 1 (pplx server running on :18099)
**Estimated effort:** ~30 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/`
**Key files for this phase:**
- `src/embeddings.py` — EmbeddingClient + FastEmbedClient (line 1-200)
- `src/memory_vector.py` — MemoryVectorStore (ChromaDB → needs pplx)
- `src/rag_vector.py` — VectorRAG (ChromaDB → needs pplx)

---

## What This Phase Delivers

Odysseus's embedding pipeline points at pplx-embed-v1 HTTP server. Default model changed from all-MiniLM to pplx. ChromaDB dependency removed from embedding path.

---

## Pre-Flight Checklist

- [ ] Phase 1 complete: pplx server on :18099
- [ ] Odysseus source exists: `ls vendor/odysseus/src/embeddings.py`

---

## Implementation Steps

### Step 1: Change default model in embeddings.py

```python
# OLD:
_DEFAULT_MODEL = "all-minilm:l6-v2"
_DEFAULT_FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# NEW:
_DEFAULT_MODEL = "pplx-embed-v1-0.6b"
# Keep fastembed fallback but change model
_DEFAULT_FASTEMBED_MODEL = "gpahal/bge-m3-onnx-int8"  # or remove entirely
```

### Step 2: Set EMBEDDING_URL

In Odysseus's `.env` or config, set:
```
EMBEDDING_URL=http://127.0.0.1:18099/v1/embeddings
```

### Step 3: Update memory_vector.py

Replace ChromaDB collection access with Milvus-lite. Since Odysseus isn't running yet, this is preparatory code:

```python
# In MemoryVectorStore.__init__:
# OLD: ChromaDB collection
# NEW: Use UnifiedVectorStore from memory-service (import or HTTP)
```

### Step 4: Update rag_vector.py

Same pattern — replace ChromaDB with Milvus-lite.

### Step 5: Test (standalone, without full Odysseus)

```python
python3 -c "
import sys
sys.path.insert(0, 'vendor/odysseus/src')
from embeddings import get_embedding_client
client = get_embedding_client()
print('URL:', client.url)
print('Model:', client.model)
vecs = client.encode(['test embedding'])
print('Dims:', vecs.shape[1])  # Should be 1024
"
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `vendor/odysseus/src/embeddings.py` | Default model → pplx |
| Modify | `vendor/odysseus/src/memory_vector.py` | ChromaDB → Milvus-lite |
| Modify | `vendor/odysseus/src/rag_vector.py` | ChromaDB → Milvus-lite |

---

## Phase-Specific Tests

1. **get_embedding_client() returns pplx HTTP client** (not all-MiniLM)
2. **encode() returns 1024-dim vectors**
3. **No ChromaDB dependency** (don't import chromadb)

---

## Completion Gate

- [ ] Default model changed to pplx
- [ ] EMBEDDING_URL set to :18099
- [ ] encode() returns 1024-dim vectors
- [ ] Code correct, may be untested (Odysseus not running)

---

## Notes for Next Phase

Phase 5 (cleanup) blocks on Phases 2, 3, 4 all passing. If Odysseus tests can't run (not wired), mark as "code correct, untested" — Phase 5 can proceed.
