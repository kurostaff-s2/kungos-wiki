# Super-Council Overview

> The super-council is the evolved slot-supervisor with integrated state machine, relational layer, and semantic enrichment. Replaces the legacy `slot-supervisor.py`.

## Architecture

```
+------------------------------------------------------------------+
|                     Pi Coding Agent                              |
|                     (Client/Chair)                               |
+--------------------------------+---------------------------------+
                                 |
                                 v
+------------------------------------------------------------------+
|              Memory Service (MCP SSE)                            |
|              [port:18097 (SSE), 18098 (stream)]                  |
|                                                                  |
|  +--------------+  +--------------+  +----------------+        |
|  |RelationalStore|  |ContextRouter |  |  MemoryLayer   |        |
|  |(SQLite+WAL)   |  |(queries)     |  |(budget slices) |        |
|  +--------------+  +--------------+  +----------------+        |
|                                                                  |
|  +------------------------------------------------------------+  |
|  |              MicroModelEnricher                             |  |
|  |  artifact summaries | failure classification | events       |  |
|  +------------------------------------------------------------+  |
|                                                                  |
|  +------------------------------------------------------------+  |
|  |              Arc Summarizer                                 |  |
|  |  consolidation | session summary | knowledge extraction     |  |
|  |  → Granite-4.1-3B on Arc A380 (:18095)                     |  |
|  +------------------------------------------------------------+  |
+--------------------------------+---------------------------------+
                                 |
                                 v
+------------------------------------------------------------------+
|              llama-swap (model proxy)                            |
|              [port:9292]                                         |
|                                                                  |
|  +------------------------------------------------------------+  |
|  |  Slot Persistence (council build tag)                      |  |
|  |  KV cache save/restore via tmpfs (48GB)                    |  |
|  |  /home/chief/Coding-Projects/7-council/council-config/slots |
|  +------------------------------------------------------------+  |
|                                                                  |
|  +----------+  +----------+  +----------+  +----------+        |
|  |  qwen    |  |  gemma   |  | nemotron |  | gpt-oss  |        |
|  |  27B MTP |  |  26B     |  | cascade  |  | 20B      |        |
|  +----------+  +----------+  +----------+  +----------+        |
+--------------------------------+---------------------------------+
                                 | proxy
                                 v
+------------------------------------------------------------------+
|              llama-server (per-model, dynamic ports)             |
|              [ports: 10001+]                                     |
|                                                                  |
|  Single active model at a time (exclusive swap)                  |
|  VRAM: RTX 3090 24GB, MTP speculative decoding                   |
+------------------------------------------------------------------+
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| llama-swap | 9292 | Model proxy, slot persistence, routing |
| memory-service | 18097/18098 | MCP SSE server (RelationalStore, ContextRouter, MemoryLayer) |
| memsearch-watch | 19530 | Vector index (Milvus Lite) |
| arc-llm | 18095 | Arc A380 consolidation model (Granite-4.1-3B) |
| frontend | 232821 | Web dashboard (Vite dev server) |

## Slot Persistence

llama-swap is built with `-tags council` to enable KV cache slot persistence:

- **Slot directory:** `/home/chief/Coding-Projects/7-council/council-config/slots/` (48GB tmpfs)
- **Max slots per model:** 48
- **Binary group:** `llama-flash` (all models share same llama.cpp binary)
- **Checksum validation:** SHA-256 before restore
- **Orphan cleanup:** Stale slots removed on startup

On model swap: `BeforeStop` saves outgoing model's KV cache → `AfterReady` restores into target.
On OOM kill: slots are **not** saved (SIGKILL bypasses hooks). `MemoryMax=8G` prevents this.

## Usage Rules

### Pipeline is the Primary Path

**All reviews, builds, and multi-phase work flows through `/v1/council/pipeline`.**

The pipeline provides:
- State machine context management (SCOUT → PLAN → BUILD → REVIEW → ...)
- RelationalStore persistence (SQLite, WAL mode, FK enforced)
- Automatic retry/retreat logic (per-phase + global ceiling)
- Artifact indexing into memsearch (via `memory_service.indexer` only)
- Structured event logging

### Single Source of Truth Rule

**All memory operations route through `memory_service/`** — the memory layer is
architecturally independent and can run standalone via `--mcp-sse`.

`super_council.py` has **zero direct MemSearch dependency**. All vector indexing
and search go through `memory_service.indexer` (MemIndex). This enforces:
- One config source (`config-subsystem.json`)
- One Milvus connection owner (MCP server or in-process indexer)
- Graceful degradation in one place (MemIndex)

**Full MemSearch documentation:** [11-memsearch.md](11-memsearch.md)

**Do NOT use direct delegation for reviews.** Use the pipeline's `AGENT_VALIDATE` phase which auto-dispatches to the appropriate reviewer alias.

### Fanout is for Small Models Only

**Fanout (`/v1/council/fanout`) is ONLY for `tiny_council` models:**
- `nemotron-nano` (Nemotron-3-Nano-4B)
- `qwen3-4b` (Qwen3-4B)
- `granite-tiny` (Granite-4.1-8B)

**Do NOT use fanout for reviewer models:**
- `reviewer-logic` (Nemotron-Cascade-2-30B) — requires full context, swap-through
- `reviewer-arch` (Gemma-4-26B-A4B) — requires full context, swap-through
- `reviewer-diversity` (GPT-OSS-20B) — requires full context, swap-through
- `goal-checker-co-chair` (Qwen3.6-35B-A3B) — requires full context, swap-through

**Reason:** Our 24GB VRAM (RTX 3090) cannot parallel-load reviewer models. Fanout on reviewer models will block with `"Swap blocked: fanout operation in progress"`.

## Core Modules

| Module | File | Purpose |
|--------|------|---------|
| `MemoryService` | `memory_service/__init__.py` | Unified memory entry point (load → .store, .router, .layer, .review) |
| `RelationalStore` | `memory_service/store.py` | SQLite-backed store with WAL, FK enforcement, schema seeding |
| `ContextRouter` | `memory_service/router.py` | Structured queries: snapshots, events, similar runs, issues |
| `MemoryLayer` | `memory_service/layer.py` | Token-budgeted context slices with artifact boundaries |
| `ReviewService` | `memory_service/review.py` | Review lifecycle (start → log → verdict) via RelationalStore |
| `MemIndex` | `memory_service/index.py` | Memsearch vector indexing (graceful degradation) — [11-memsearch.md](11-memsearch.md) |
| `ProjectAwareMemSearch` | `memory_service/memsearch_wrapper.py` | MemSearch wrapper with project_id tagging + type filtering |
| `FastMCP Server` | `memory_service/mcp_server.py` | MCP server: 18 tools + 7 resources (stdio + SSE transport) |
| `MCPClient` | `mcp_client.py` | Sync MCP client for Pi agent (background event-loop thread) |
| `MicroModelEnricher` | `micro_model.py` | Async semantic enrichment (ONNX embeddings, TF-IDF keywords) |
| `ArcSummarizer` | `arc_summarizer/__init__.py` | Unified facade for consolidation, summarization, extraction |
| `ArcClient` | `arc_summarizer/client.py` | HTTP client with retry + fallback to main upstream |
| `ArcPipeline` | `arc_summarizer/pipeline.py` | Full consolidation pipeline (gather→call→write→cache→inject) |
| `ArcConfig` | `arc_summarizer/config.py` | Loads from `config-subsystem.json["consolidation"]` |

**Backward compat shims** (re-export from `memory_service/`): `relational_store.py`, `context_router.py`, `memory_layer.py`, `review_service.py`

## Key Design Decisions

1. **Proxy architecture:** llama-swap (port 9292) is the stable frontend. Clients never see upstream restarts.
2. **Per-model slot namespace:** `<alias>/<config_hash>/` prevents cross-model KV corruption.
3. **Binary hash tracker:** Purges all slots on llama-server binary change.
4. **SQLite + WAL:** Atomic transitions, FK enforcement, zero auto-checkpoint (manual only).
5. **Single-slot GPU:** All models serialize through one GPU. Wall-clock = sum of tasks.
6. **Artifact boundaries:** MemoryLayer never cuts mid-artifact. Uses `ARTIFACT_BOUNDARY` markers.
7. **DESC ordering:** Newest artifacts preserved when budget is tight (MODERATE-2 fix).
8. **MemoryService single source of truth:** Supervisor uses direct Python API (`MemoryService.load()`). No MCP subprocess spawning, no JSON-RPC serialization for in-process calls. External consumers use `memory_service --mcp-stdio` (FastMCP).
9. **FastMCP for external MCP:** Full protocol compliance (tools with auto-schema, resources, stdio + SSE transport, proper error codes). `mcp>=1.0.0` declared dependency.
10. **Heuristic fallback:** MicroModelEnricher works without ONNX model (TF-IDF keywords, pattern matching).
11. **Arc A380 consolidation:** Memory consolidation routes to Granite-4.1-3B on Arc A380 (separate from main GPU). Health-gated startup with fallback to main upstream.
12. **Session memory separation:** `memory_rollups` (Arc A380 pipeline, `consol-*` prefix, replaces zombie `consolidation_cache`) is strictly separate from `session_diary` (mechanical upsert, `sess-*` prefix). Pi extension `message_end` hook uses a multi-signal scorer (high/medium headers, structural signals, anti-noise vetoes, threshold=4) to auto-detect summaries and upsert mechanically — no model involvement. All recall routes through ContextRouter (canonical recall path). Provenance traceability: `consol-*` = Arc, `sess-*` = mechanical, `test-*` = tests.

## Configuration

### llama-swap Config

**Primary config:** `~/llama-swap/config.yaml`

Defines all models, routing groups, scheduler, and slot persistence. Built with `-tags council` for KV cache persistence.

```yaml
models:
  "qwen-160k-UD-fast":
    cmd: |        # llama-server CLI with ${PORT} macro
    capabilities: # text in/out, context size
    slotStore:    # KV cache persistence
      enabled: true
      slot_dir: /home/chief/Coding-Projects/7-council/council-config/slots
      validate_checksum: true
      cleanup_orphans: true
      max_slots: 48
      binary_group: llama-flash

routing:
  router:
    use: group
    settings:
      groups:
        main:
          swap: true
          exclusive: true
          members: [qwen-160k-UD-fast, qwen-uhn-fast, ...]

  scheduler:
    use: fifo
    settings:
      fifo:
        priority:
          mellum2-12b: 10
          nemotron-nano: 5
```

### Memory Service Config

**Subsystem config:** `~/Coding-Projects/7-council/super_council/config-subsystem.json`

Defines subsystem settings: `default_alias`, `voice_pipeline`, `summarizer`.

### Startup

```bash
# llama-swap (systemd user service)
systemctl --user start llama-swap.service

# memory-service (systemd user service)
systemctl --user start memory-service.service

# memsearch-watch (systemd user service)
systemctl --user start memsearch-watch.service
```

### llama-server Binary

| Binary | Purpose |
|--------|---------|
| `~/llama-cpp-latest/build/bin/llama-server` | Default upstream (main llama.cpp with MTP) |

**Current model config:**
- MTP speculative decoding (`--spec-type draft-mtp --spec-draft-n-max 3`)
- Flash attention (`--flash-attn on`)
- KV cache: `q8_0` (K and V)
- Context: 110K tokens (qwen-160k-UD-fast)
- Threads: 16 / batch: 16
- Cache RAM: 16GB
- `--no-mmap --mlock` (weights in RAM, mlocked)

### MTP Performance (Q4_K_XL UD, q8_0 KV)

| Generated Tokens | PP (t/s) | TG (t/s) | Draft Acceptance |
|-----------------|----------|----------|------------------|
| 100 | ~290 | ~67 | ~94% |
| 200 | ~290 | ~57 | ~76% |
| 500 | ~210 | ~50 | ~62% |
| 1000 | ~245 | ~47 | ~59% |

*vs. vanilla decode: ~37 t/s TG at 64 tokens. MTP adds ~30 t/s boost at short lengths.*

## File Locations

| Resource | Path |
|----------|------|
| llama-swap source | `~/llama-swap/` |
| llama-swap config | `~/llama-swap/config.yaml` |
| llama-swap binary | `~/bin/llama-swap` (council build tag) |
| llama-server binary | `~/llama-cpp-latest/build/bin/llama-server` |
| Slots (tmpfs) | `~/Coding-Projects/7-council/council-config/slots/` (48GB) |
| Models | `~/models/` |
| Council memory | `~/.council-memory/` |
| Memsearch DB | `~/.memsearch/milvus.db/` |
| Phase state | `~/.council-memory/phase-state/` |
| Pipeline state | `~/.council-memory/pipelines/` |
| Embedding model | `~/models/embedding/pplx-embed-v1-0.6b-int8/` |
| Bench results | `~/Coding-Projects/7-council/bench-results/` |
