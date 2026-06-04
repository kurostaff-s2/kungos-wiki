# Phase 2: Point Memsearch at pplx HTTP

**Parent plan:** `04-06-2026_embedding-consolidation-pplx_6b297d.md`
**Phase:** 2 of 6
**Dependencies:** Phase 1 (pplx server running on :18099)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/memory_service/layer.py` — Memsearch initialization (line ~1090)
- `super_council/memory_service/memsearch_wrapper.py` — ProjectAwareMemSearch wrapper
- `super_council/memory_service/config.py` — MemoryConfig dataclass

---

## What This Phase Delivers

Memsearch uses pplx-embed-v1 HTTP endpoint instead of direct bge-m3 ONNX load. Existing 351 entities remain searchable (same 1024-dim, no re-index needed). New file indexing uses pplx embeddings.

---

## Pre-Flight Checklist

- [ ] Phase 1 complete: `curl http://127.0.0.1:18099/health` returns ok
- [ ] memory-service is running: `systemctl --user status memory-service.service`
- [ ] Current Memsearch works: check logs for `MemIndex wired to RelationalStore`

---

## Implementation Steps

### Step 1: Check memsearch package capabilities

```python
python3 -c "
from memsearch import MemSearch
import inspect
sig = inspect.signature(MemSearch.__init__)
print('MemSearch.__init__ params:', list(sig.parameters.keys()))
"
```

Check if `MemSearch` accepts `embedding_provider="http"` or `embedding_url` parameter.

### Step 2A: If memsearch supports HTTP natively

In `layer.py` (~line 1095), change:

```python
# OLD:
ms = MemSearch(
    embedding_provider="onnx",
    embedding_model="gpahal/bge-m3-onnx-int8",
    milvus_uri=os.path.expanduser("~/.memsearch/milvus.db"),
    collection="memsearch_chunks",
)

# NEW:
ms = MemSearch(
    embedding_provider="http",
    embedding_url="http://127.0.0.1:18099/v1/embeddings",
    milvus_uri=os.path.expanduser("~/.memsearch/milvus.db"),
    collection="memsearch_chunks",
)
```

### Step 2B: If memsearch doesn't support HTTP

Add HTTP embedding client to `memsearch_wrapper.py`:

```python
import httpx

class HTTPEmbeddingClient:
    """Thin HTTP client for pplx embedding server."""
    def __init__(self, url: str = "http://127.0.0.1:18099/v1/embeddings"):
        self.url = url
        self._client = httpx.Client(timeout=30.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.post(self.url, json={"input": texts})
        resp.raise_for_status()
        data = resp.json()
        return [d["embedding"] for d in data["data"]]

    @property
    def dimension(self) -> int:
        return 1024
```

Then in `layer.py`, pass the HTTP client to Memsearch (or use it directly if MemSearch doesn't accept custom clients).

### Step 3: Add config field

In `config.py`, add to `MemoryConfig`:

```python
embedding_url: str = "http://127.0.0.1:18099/v1/embeddings"
```

Load from config-subsystem.json:

```python
embedding_url = raw.get("embedding_url", "http://127.0.0.1:18099/v1/embeddings")
```

### Step 4: Restart and verify

```bash
systemctl --user restart memory-service.service
sleep 10
# Check logs
journalctl --user -u memory-service.service --since "1 minute ago"
# Check Memsearch status
curl http://127.0.0.1:18098/v1/memory/tool/memsearch_status
```

### Step 5: Test search

```bash
# Search for something in the indexed docs
curl -X POST http://127.0.0.1:18098/v1/memory/tool/council-recall \
  -H "Content-Type: application/json" \
  -d '{"query": "memory service", "max_tokens": 1024}'
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/layer.py` | Change embedding_provider to HTTP |
| Modify | `super_council/memory_service/config.py` | Add embedding_url field |
| Modify (maybe) | `super_council/memory_service/memsearch_wrapper.py` | Add HTTP client if needed |

---

## Phase-Specific Tests

1. **Memsearch status:** Returns ok, shows pplx as embedding source
2. **Existing entities searchable:** Search for "memory service" → returns results from existing 351 entities
3. **New indexing works:** Touch a file in `~/.council-memory/daily/`, wait 30s, search for its content
4. **No bge-m3 dependency:** `rm -rf ~/.fastembed/models--qdrant--BAAI--bge-m3*/` (don't actually delete yet, just verify it's not needed)

---

## Completion Gate

- [ ] Memsearch uses pplx HTTP endpoint
- [ ] Existing 351 entities still searchable
- [ ] New file indexing works
- [ ] memory-service starts without bge-m3 model on disk
- [ ] All phase-specific tests pass

---

## Notes for Next Phase

Phase 3 (MicroModelEnricher) is independent — it uses direct ONNX load, not HTTP. No coordination needed with this phase.
