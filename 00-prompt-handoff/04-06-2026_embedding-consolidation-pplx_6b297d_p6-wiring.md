# Phase 6: Production Wiring + Verification

**Parent plan:** `04-06-2026_embedding-consolidation-pplx_6b297d.md`
**Phase:** 6 of 6 (final)
**Dependencies:** All phases 1-5 complete
**Estimated effort:** ~30 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** Verification only — no new files.

---

## What This Phase Delivers

Full end-to-end verification of the unified embedding architecture. One model, one server, one vector store. All regression tests pass.

---

## Pre-Flight Checklist

- [ ] Phase 1: pplx server running on :18099
- [ ] Phase 2: Memsearch uses pplx HTTP
- [ ] Phase 3: MicroModelEnricher wired into memory-service
- [ ] Phase 4: Odysseus code points at pplx
- [ ] Phase 5: Old models deleted, ChromaDB removed

---

## Verification Steps

### 1. Service Health

```bash
# pplx server
curl -s http://127.0.0.1:18099/health | python3 -m json.tool

# memory-service
curl -s http://127.0.0.1:18098/v1/memory/health | python3 -m json.tool

# systemd status
systemctl --user status pplx-embed.service memory-service.service --no-pager
```

### 2. Embedding Flow (End-to-End)

```bash
# Write a test file
echo "# Test Embedding Consolidation\nThis is a test of the unified embedding architecture." \
  > ~/.council-memory/daily/test-embedding-consolidation.md

# Wait for indexing (30s poll interval)
sleep 35

# Search for it
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/council-recall \
  -H "Content-Type: application/json" \
  -d '{"query": "embedding consolidation", "max_tokens": 512}' | python3 -m json.tool

# Clean up
rm ~/.council-memory/daily/test-embedding-consolidation.md
```

### 3. Enrichment Flow

```bash
# classify_failure via MCP
curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/classify_failure \
  -H "Content-Type: application/json" \
  -d '{"run_id": "test-123", "error": "ConnectionRefusedError: Connection refused"}' \
  | python3 -m json.tool

# Expected: {"failure_type": "connection_error", "confidence": 0.9}
```

### 4. Model Inventory

```bash
# Only one model should exist
echo "Embedding models on disk:"
du -sh ~/models/embedding/*/
# Expected: ~688 MB for pplx-embed-v1-0.6b-int8/

# No bge-m3
find ~/.fastembed -name "*bge*" 2>/dev/null
# Expected: empty

# No all-MiniLM
find ~/.fastembed -name "*MiniLM*" 2>/dev/null
# Expected: empty

# No ChromaDB
find vendor/odysseus/data -name "chroma*" 2>/dev/null
# Expected: empty (or just the empty directory)
```

### 5. Vector Store

```bash
python3 -c "
from pymilvus import connections, Collection
import os
connections.connect('default', uri=os.path.expanduser('~/.memsearch/milvus.db'))
coll = Collection('memsearch_chunks')
print(f'Entities: {coll.num_entities}')
print(f'Schema: {[f.name for f in coll.schema.fields]}')
"
# Expected: 351+ entities, 1024-dim embeddings
```

### 6. MCP Tools Regression

```bash
# List all available tools
curl -s http://127.0.0.1:18098/v1/memory/tools | python3 -c "
import sys, json
tools = json.load(sys.stdin)
print(f'Total tools: {len(tools)}')
for t in tools:
    print(f'  - {t[\"name\"]}')
"
```

---

## Post-Wiring Tests (GATE — must pass before marking complete)

- [ ] pplx server: `/health` returns `{"status": "ok", "dims": 1024}`
- [ ] pplx server: `/v1/embeddings` returns 1024-dim vectors
- [ ] memory-service: starts cleanly, no errors in logs
- [ ] Memsearch: returns results for "embedding consolidation" query
- [ ] MicroModelEnricher: `classify_failure` returns correct classification
- [ ] MicroModelEnricher: `model_available=True` in logs
- [ ] Milvus: 351+ entities in memsearch_chunks
- [ ] Only pplx model on disk (~688 MB)
- [ ] No bge-m3 or all-MiniLM on disk
- [ ] No ChromaDB service in docker-compose
- [ ] All MCP tools available (no regression)
- [ ] Full embedding flow: write → index → search works

---

## Completion Gate

- [ ] All post-wiring tests pass
- [ ] No errors in service logs
- [ ] All existing functionality preserved
- [ ] ~530 MB disk freed
- [ ] Plan doc updated (v3 → mark embedding consolidation as COMPLETE)

---

## If Anything Fails

1. **pplx server down:** Check `systemctl --user status pplx-embed.service`. Check logs for ONNX load errors.
2. **Memsearch broken:** Check if memsearch package supports HTTP provider. May need wrapper in `memsearch_wrapper.py`.
3. **Enricher not loading:** Check if `model_quantized.onnx` exists at expected path. Check `onnxruntime` version.
4. **Dimension mismatch:** Verify pplx outputs 1024d (same as bge-m3). If different, re-index existing Milvus entities.
5. **Port conflict:** Verify :18099 is free. `ss -tlnp | grep 18099`.
