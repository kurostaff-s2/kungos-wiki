# Embedding Consolidation — pplx-embed-v1 (Master Plan)

**Source spec:** `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md` (§3.4, §7.3, §7.8, §15)
**Generated:** 04-06-2026
**Goal:** Consolidate 3 embedding models (bge-m3, all-MiniLM, pplx) into 1 (pplx-embed-v1-0.6b), 1 HTTP server (:18099), 1 vector store (Milvus-lite).

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md`
**Related codebases:**
- `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/` (Odysseus embedding client)
- `/home/chief/models/embedding/pplx-embed-v1-0.6b-int8/` (pplx model + server.py)
**Key files for this task:** Listed per phase below.

---

## Execution Order (DAG)

```
Phase 1 (start server)
    ├── Phase 2 (Memsearch → pplx HTTP)
    ├── Phase 3 (MicroModelEnricher → memory-service)
    └── Phase 4 (Odysseus → pplx HTTP)
            │
Phase 5 (cleanup — after 2, 3, 4 all pass)
            │
Phase 6 (production wiring + verification)
```

**Phases 2, 3, 4 can run in parallel after Phase 1.**
**Phase 5 blocks on all of 2, 3, 4.**

---

## Phase 1: Start pplx Embedding Server on :18099

**What:** Get the existing `server.py` running on port 18099 with HTTP→ONNX fallback for resilience.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py` | Change port to 18099, add fallback pattern |
| Create | `~/.config/systemd/user/pplx-embed.service` | Systemd user service |

**Steps:**
1. Read existing `server.py` — it already has `/v1/embeddings` and `/v1/models` endpoints
2. Change default port from `18097` → `18099` (avoids conflict with memory-service SSE)
3. Add HTTP→ONNX fallback pattern from Odysseus's `get_embedding_client()`:
   - If ONNX session fails to load, log warning and return 503
   - Add `/health` endpoint returning model status, dims, uptime
4. Test manually: `python3 server.py --port 18099` → `curl http://127.0.0.1:18099/health`
5. Create systemd user service file
6. Enable and start: `systemctl --user enable --now pplx-embed.service`

**Tests:**
- [ ] `curl http://127.0.0.1:18099/health` returns `{"status": "ok", "model": "pplx-embed-v1-0.6b", "dims": 1024}`
- [ ] `curl -X POST http://127.0.0.1:18099/v1/embeddings -d '{"input": ["hello world"]}'` returns 1024-dim embedding
- [ ] Service survives restart: `systemctl --user restart pplx-embed.service`

**Dependencies:** None

---

## Phase 2: Point Memsearch at pplx HTTP

**What:** Change Memsearch from direct bge-m3 ONNX load to HTTP client pointing at pplx server.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/layer.py` | Change embedding_provider from "onnx" to HTTP URL |
| Modify | `super_council/memory_service/memsearch_wrapper.py` | Add HTTP client support |
| Modify | `super_council/memory_service/config.py` | Add embedding_url config field |

**Steps:**
1. Add `embedding_url: str = "http://127.0.0.1:18099/v1/embeddings"` to `MemoryConfig`
2. In `layer.py`, change Memsearch initialization:
   ```python
   # OLD:
   ms = MemSearch(embedding_provider="onnx", embedding_model="gpahal/bge-m3-onnx-int8", ...)
   # NEW:
   ms = MemSearch(embedding_provider="http", embedding_url=config.embedding_url, ...)
   ```
3. If `memsearch` package doesn't support HTTP provider, add a thin wrapper in `memsearch_wrapper.py` that:
   - Accepts `embedding_url` parameter
   - Calls `httpx.post(url, json={"input": texts})` for encoding
   - Returns normalized embeddings
4. Restart memory-service: `systemctl --user restart memory-service.service`
5. Verify Memsearch still works: `curl http://127.0.0.1:18098/v1/memory/tool/memsearch_status`

**Tests:**
- [ ] Memsearch returns results after restart
- [ ] Existing 351 entities still searchable (no re-index needed yet)
- [ ] New file indexing works (touch a file in watched dir, wait 30s, search)

**Dependencies:** Phase 1

---

## Phase 3: Wire MicroModelEnricher into memory-service

**What:** Move MicroModelEnricher from super_council.py-only to memory-service MCP server.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/mcp_server.py` | Add MicroModelEnricher init + tools |
| Modify | `super_council/memory_service/__main__.py` | Pass store to enricher |

**Steps:**
1. In `mcp_server.py`, add `enricher: Optional[Any] = None` parameter to MemoryServiceMCP
2. In `__main__.py`, initialize MicroModelEnricher during startup:
   ```python
   from super_council.micro_model import MicroModelEnricher
   enricher = MicroModelEnricher(store, bonsai_url=config.get('bonsai_url'))
   ```
3. Add MCP tools: `summarize_artifact`, `classify_failure` (already defined in mcp_server.py, just wire the enricher)
4. Restart memory-service

**Tests:**
- [ ] `classify_failure` tool works via MCP: send error message → get classification
- [ ] `summarize_artifact` tool works via MCP: send artifact_id → get summary
- [ ] Model loaded: check logs for `MicroModelEnricher initialized (model_available=True)`

**Dependencies:** Phase 1

---

## Phase 4: Point Odysseus at pplx HTTP

**What:** Change Odysseus's EmbeddingClient default from all-MiniLM to pplx HTTP server.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `vendor/odysseus/src/embeddings.py` | Change default model + add pplx URL |
| Modify | `vendor/odysseus/src/memory_vector.py` | Use pplx HTTP instead of ChromaDB |
| Modify | `vendor/odysseus/src/rag_vector.py` | Use pplx HTTP instead of ChromaDB |

**Steps:**
1. In `embeddings.py`, change `_DEFAULT_MODEL` from `"all-minilm:l6-v2"` → `"pplx-embed-v1-0.6b"`
2. Set `EMBEDDING_URL=http://127.0.0.1:18099/v1/embeddings` in Odysseus env/config
3. In `memory_vector.py`, replace ChromaDB collection with Milvus-lite `unified_vectors`:
   - Use `UnifiedVectorStore` from memory-service (import or HTTP)
   - `find_similar()` → `UnifiedVectorStore.dedup_check()`
4. In `rag_vector.py`, replace ChromaDB with Milvus-lite:
   - `VectorRAG.search()` → `UnifiedVectorStore.search(source='document')`
5. Test Odysseus embedding pipeline (can run standalone without full Odysseus)

**Tests:**
- [ ] `get_embedding_client()` returns pplx HTTP client (not all-MiniLM)
- [ ] `EmbeddingClient().encode(["test"])` returns 1024-dim vector
- [ ] `MemoryVectorStore.find_similar("test text")` works without ChromaDB

**Dependencies:** Phase 1

---

## Phase 5: Cleanup — Delete Old Models + ChromaDB

**What:** Remove bge-m3, all-MiniLM model files, ChromaDB from docker-compose and code.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Delete | `~/.fastembed/models--qdrant--bge-m3*/` | Free ~450 MB |
| Delete | `vendor/odysseus/data/fastembed_cache/models--qdrant--all-MiniLM-L6-v2-onnx/` | Free ~80 MB |
| Modify | `vendor/odysseus/docker-compose.yml` | Remove chromadb service |
| Modify | `vendor/odysseus/src/chroma_client.py` | Add deprecation warning |

**Steps:**
1. Verify all phases 2-4 pass (Memsearch, MicroModelEnricher, Odysseus all work without old models)
2. Delete bge-m3 model files: `rm -rf ~/.fastembed/models--qdrant--BAAI--bge-m3*/`
3. Delete all-MiniLM cache: `rm -rf vendor/odysseus/data/fastembed_cache/models--qdrant--all-MiniLM-L6-v2-onnx/`
4. Remove chromadb from docker-compose.yml
5. Add deprecation warning to chroma_client.py: `logger.warning("ChromaDB is deprecated. Use pplx-embed-v1 on :18099")`
6. Verify disk savings: `du -sh ~/models/embedding/ ~/.fastembed/`

**Tests:**
- [ ] pplx server still responds: `curl http://127.0.0.1:18099/health`
- [ ] Memsearch still works without bge-m3 on disk
- [ ] Odysseus embedding still works without all-MiniLM on disk
- [ ] ~530 MB disk freed

**Dependencies:** Phases 2, 3, 4 (all must pass)

---

## Phase 6: Production Wiring + Verification

**What:** Full end-to-end verification of the unified embedding architecture.

**Files:** No new files. Verification only.

**Steps:**
1. Start all services: `systemctl --user start pplx-embed.service memory-service.service`
2. Verify health endpoints:
   - pplx: `curl http://127.0.0.1:18099/health`
   - memory-service: `curl http://127.0.0.1:18098/v1/memory/health`
3. Full embedding flow test:
   - Write a test file to `~/.council-memory/daily/`
   - Wait 30s for indexing
   - Search via Memsearch: `curl http://127.0.0.1:18098/v1/memory/tool/memsearch_status`
   - Verify results include the test file
4. Enrichment flow test:
   - Call `classify_failure` via MCP with a test error
   - Verify classification result
5. Odysseus flow test:
   - Call `get_embedding_client()` → verify pplx HTTP
   - Call `encode(["test"])` → verify 1024-dim output
6. Disk verification: `du -sh ~/models/embedding/` → should be ~688 MB (one model)

**Post-Wiring Tests (GATE):**
- [ ] pplx server starts and responds to `/health`
- [ ] pplx server returns 1024-dim embeddings for `/v1/embeddings`
- [ ] Memsearch uses pplx HTTP (no bge-m3 on disk)
- [ ] MicroModelEnricher loads pplx ONNX directly (model_available=True)
- [ ] Odysseus EmbeddingClient points at pplx HTTP (not all-MiniLM)
- [ ] Milvus-lite vector store accessible (351+ entities)
- [ ] No ChromaDB service running on :8100
- [ ] Disk usage: ~688 MB for embedding models (was ~1.2 GB)
- [ ] All existing memory-service MCP tools still work (no regression)

**Dependencies:** All phases 1-5

---

## Constraints

- **Port 18097 is owned by memory-service SSE** — pplx server must use 18099
- **IST timestamps** — all logs/timestamps use IST (+05:30), not UTC
- **No data loss** — existing 351 Milvus entities must survive the transition
- **Graceful degradation** — if pplx server is down, Memsearch must fall back (not crash)
- **ONNX direct for enrichment** — MicroModelEnricher uses direct ONNX load (not HTTP) for low-latency async path
- **No new dependencies** — use existing `httpx`, `onnxruntime`, `transformers` packages

---

## Success Criteria

- [ ] One embedding model on disk: `pplx-embed-v1-0.6b-int8` (688 MB)
- [ ] One HTTP server running: `:18099` with `/v1/embeddings` + `/health`
- [ ] One vector store: Milvus-lite `unified_vectors` collection
- [ ] Memsearch uses pplx HTTP (no bge-m3 dependency)
- [ ] MicroModelEnricher wired into memory-service (model_available=True)
- [ ] Odysseus EmbeddingClient points at pplx HTTP (no all-MiniLM)
- [ ] ChromaDB removed from docker-compose
- [ ] ~530 MB disk freed (bge-m3 + all-MiniLM deleted)
- [ ] All existing MCP tools work (no regression)
- [ ] Full embedding flow verified (write → index → search)

---

## Caveats & Uncertainty

1. **memsearch package HTTP support:** The `memsearch` package (v0.4.4) may not support HTTP embedding provider. If not, a thin wrapper in `memsearch_wrapper.py` is needed. Check `MemSearch.__init__()` signature.
2. **Model loading time:** pplx ONNX model takes ~5-10s to load. MicroModelEnricher loads it directly at startup — this delays memory-service startup. Consider lazy loading.
3. **Concurrent embedding requests:** pplx server.py is single-threaded (HTTPServer). Under load, requests queue. Consider `ThreadingHTTPServer` if concurrency is needed.
4. **Odysseus not running:** Odysseus is vendored but not active. Phase 4 changes are preparatory — they won't be tested until Odysseus is wired. Mark as "code correct, untested" if needed.
5. **Milvus re-embedding:** If embedding dimensions change (they shouldn't — both pplx and bge-m3 are 1024d), existing 351 entities need re-embedding. Verify dimension match before deleting bge-m3.

---

## Serialized Phase Handoffs

This plan has 6 phases. Individual phase handoffs are saved as:

| Phase | File |
|-------|------|
| P1 | `04-06-2026_embedding-consolidation-pplx_6b297d_p1-server.md` |
| P2 | `04-06-2026_embedding-consolidation-pplx_6b297d_p2-memsearch.md` |
| P3 | `04-06-2026_embedding-consolidation-pplx_6b297d_p3-enricher.md` |
| P4 | `04-06-2026_embedding-consolidation-pplx_6b297d_p4-odysseus.md` |
| P5 | `04-06-2026_embedding-consolidation-pplx_6b297d_p5-cleanup.md` |
| P6 | `04-06-2026_embedding-consolidation-pplx_6b297d_p6-wiring.md` |

Each phase doc is self-contained and can be handed to a separate subagent.
