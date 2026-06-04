# Phase 5: Cleanup — Delete Old Models + ChromaDB

**Parent plan:** `04-06-2026_embedding-consolidation-pplx_6b297d.md`
**Phase:** 5 of 6
**Dependencies:** Phases 2, 3, 4 (all must pass)
**Estimated effort:** ~15 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `vendor/odysseus/docker-compose.yml` — Remove chromadb service
- `vendor/odysseus/src/chroma_client.py` — Add deprecation warning

---

## What This Phase Delivers

bge-m3 and all-MiniLM model files deleted (~530 MB freed). ChromaDB removed from docker-compose. Deprecation warnings added to chroma_client.py.

---

## Pre-Flight Checklist

- [ ] Phase 2 complete: Memsearch works without bge-m3
- [ ] Phase 3 complete: MicroModelEnricher works
- [ ] Phase 4 complete: Odysseus code points at pplx
- [ ] pplx server healthy: `curl http://127.0.0.1:18099/health`

---

## Implementation Steps

### Step 1: Verify no bge-m3 dependency

```bash
# Check if anything imports bge-m3
grep -r "bge-m3\|bge_m3" super_council/ --include="*.py" -l
# Should only find references in comments/config, not imports
```

### Step 2: Delete bge-m3 model

```bash
# Find bge-m3 files
find ~/.fastembed -name "*bge*" -type d
# Delete
rm -rf ~/.fastembed/models--qdrant--BAAI--bge-m3*/
rm -rf ~/.fastembed/models--gpahal--bge-m3*/
```

### Step 3: Delete all-MiniLM cache

```bash
rm -rf vendor/odysseus/data/fastembed_cache/models--qdrant--all-MiniLM-L6-v2-onnx/
```

### Step 4: Remove ChromaDB from docker-compose

In `vendor/odysseus/docker-compose.yml`:
- Remove `chromadb:` service block
- Remove `chromadb-data:` volume
- Remove `chromadb` from `depends_on:` in odysseus service

### Step 5: Add deprecation warning

In `vendor/odysseus/src/chroma_client.py`, add at module level:

```python
import warnings
warnings.warn(
    "chroma_client.py is deprecated. Use pplx-embed-v1 on :18099 for embeddings. "
    "ChromaDB has been replaced by Milvus-lite.",
    DeprecationWarning,
    stacklevel=2,
)
```

### Step 6: Verify disk savings

```bash
echo "Before cleanup (expected ~1.2 GB):"
du -sh ~/models/embedding/ ~/.fastembed/ vendor/odysseus/data/fastembed_cache/ 2>/dev/null

echo "After cleanup (expected ~688 MB):"
du -sh ~/models/embedding/pplx-embed-v1-0.6b-int8/
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Delete | `~/.fastembed/models--*--bge-m3*/` | Free ~450 MB |
| Delete | `vendor/odysseus/data/fastembed_cache/*--all-MiniLM*/` | Free ~80 MB |
| Modify | `vendor/odysseus/docker-compose.yml` | Remove chromadb service |
| Modify | `vendor/odysseus/src/chroma_client.py` | Add deprecation warning |

---

## Phase-Specific Tests

1. **pplx server still works:** `curl http://127.0.0.1:18099/health` → 200
2. **Memsearch works without bge-m3:** Search returns results
3. **No all-MiniLM on disk:** `find ~/.fastembed -name "*MiniLM*" -type d` → empty
4. **Disk freed:** `du -sh ~/models/embedding/` → ~688 MB total

---

## Completion Gate

- [ ] bge-m3 model files deleted
- [ ] all-MiniLM cache deleted
- [ ] ChromaDB removed from docker-compose
- [ ] Deprecation warning in chroma_client.py
- [ ] ~530 MB disk freed
- [ ] All services still work

---

## Notes for Next Phase

Phase 6 (production wiring) does full end-to-end verification. All models should be cleaned up, all services pointing at pplx.
