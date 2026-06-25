# Super-Council Documentation Index

> Complete documentation for the super-council: memory service, llama-swap model proxy, relational layer, and semantic enrichment.

## Documents

| # | Document | Purpose |
|---|----------|---------|
| 01 | [Overview](01-overview.md) | Architecture, services, usage rules, core modules, configuration, file locations |
| 02 | [State Machine](02-state-machine.md) | PipelineState (6-phase), ChairGateState (TDD gate), StateMachineLinter, reviewer auto-dispatch |
| 03 | [Relational Layer](03-relational-layer.md) | RelationalStore (SQLite+WAL), ContextRouter (queries), MemoryLayer (budget slices) |
| 04 | [Delegation & Active Recall](04-delegation.md) | Delegation flow, active recall, worktree isolation, recall-then-validate |
| 05 | [Pipeline API](05-pipeline-api.md) | REST endpoints, payloads, response formats, error codes |
| 06 | [MicroModel Enricher](06-micro-model.md) | ONNX embeddings, failure classification, artifact enrichment, MCP methods |
| 07 | [Diagnostics](07-diagnostics.md) | Troubleshooting, common issues, recovery procedures, log analysis |
| 08 | [Arc Summarizer](08-arc-summarizer.md) | Memory consolidation on Arc A380, LFM2-2.6B/1.2B router mode, tiered rollups, pipeline API, parser fallback chain |
| 09 | [Memory Service](09-memory-service.md) | MemoryService architecture, FastMCP server, 21 tools, 7 resources, unified_log_recall, tool matrix |
| 10 | [Code Graph](10-codegraph.md) | CodeGraphStore API, 12 MCP tools, FTS5 search, call graph traversal, cross-DB JOINs with memory layer |
| 11 | [MemSearch](11-memsearch.md) | MemIndex vector indexing, Milvus-lite schema, hybrid search, raw session memory pipeline, direct text upsert |
| 14 | [Recall Search Fine-Tuning](14-recall-search-fine-tuning.md) | FTS5 indexes, analytics logging, UnifiedVectorStore, project filtering, verification |
| 15 | [Llama-Swap Slot Persistence Fix](15-llama-swap-slot-persistence-fix.md) | MTP draft cache persistence, --cache-reuse, _last_n_saved tracking, slot API endpoints |

## Plans & Analysis

| Document | Purpose |
|----------|--------|
| [Arc Summarizer TODO](todo-arc-summarizer.md) | Arc consolidation pipeline — remaining work |

## Usage Rules

### Pipeline is Primary Path
**All reviews and multi-phase work flows through `/v1/council/pipeline`.** The state machine manages context, retry logic, and artifact persistence.

### Fanout is for Small Models Only
**Fanout (`/v1/council/fanout`) is ONLY for `tiny_council` models:** nemotron-nano, qwen3-4b, granite-tiny.
**Do NOT use fanout for reviewer models** (Nemotron, Gemma, GPT-OSS, co-chair) — 24GB VRAM cannot parallel-load them.

## Quick Reference

### Architecture
```
Pi (Client) → llama-swap (:9292) → llama-server (dynamic ports 10001+)
              Memory Service (:18097/18098 MCP SSE)
              Memsearch (:19530 Milvus Lite)
              Arc Summarizer (:18093 LFM2-2.6B/1.2B router)
```

### Pipeline Flow
```
SCOUT → PLAN → BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE
     → PENDING_REVIEW → HUMAN_GATE → INDEX → DONE | FAILED
```

### Model Roster (llama-swap)
| Model ID | Model | Quant | Context | Notes |
|----------|-------|-------|---------|-------|
| `qwen-160k-UD-fast` | Qwen3.6-27B-UD | Q4_K_XL | 110K | MTP speculative decoding (default) |
| `qwen-uhn-fast` | Qwen3.6-27B UHN | Q4_K_M | 98K | Uncensored Heretic v2, MTP |
| `mellum2-12b` | Mellum2-12B | Q5_K_L | 98K | Scout, fast |
| `nex-n2-mini` | Nex-N2-mini | Q4_K_L | 98K | Code specialist |

**Note:** Model roster may vary based on available models and llama-swap configuration. Check `GET /running` via llama-swap for currently loaded models.

### Slot Persistence
- **Config:** `~/llama-swap/config.yaml` (all models have `slotStore.enabled: true`)
- **Cache reuse:** `--cache-reuse 8192` (partial prefix matching)
- **Slot dir:** `~/Coding-Projects/7-council/council-config/slots/` (48GB tmpfs)
- **Max slots:** 48 per model
- **Binary group:** `llama-flash` (all share same llama.cpp binary)
- **Checksum:** SHA-256 validation before restore
- **Orphan cleanup:** Stale slots removed on startup
- **MTP draft cache:** Persisted alongside trunk KV (see [15](15-llama-swap-slot-persistence-fix.md))
- **Token tracking:** `_last_n_saved` updated from `/slots` endpoint after each request

### Key Endpoints
- `POST /v1/chat/completions` — Chat with auto-swap (via llama-swap :9292)
- `GET /running` — Running models
- `GET /api/slots/status` — Slot persistence status
- `POST /api/slots/save/{model}` — Manual slot save (saves trunk + MTP draft cache)
- `POST /api/slots/restore/{model}` — Manual slot restore (restores trunk + MTP draft cache)
- `POST /api/slots/cleanup` — Orphan cleanup

### Arc Summarizer (Memory Consolidation)
- Server: `127.0.0.1:18093` (llama.cpp router mode on Arc A380)
- Models: `LFM2-2.6B-Transcript-Q8_0` (daily), `LFM2.5-1.2B-Instruct-Q8_0` (short/weekly/bimonthly)
- Pipeline: Scheduler → ArcPipeline → ArcClient → LLMRequestQueue → router
- Router mode: `--models-max 2` (both models loaded, per-model slot)
- Queue: single pipeline — all LLM requests route through LLMRequestQueue
- Health: `GET http://127.0.0.1:18093/v1/models`

### File Locations
- llama-swap source: `~/llama-swap/`
- llama-swap config: `~/llama-swap/config.yaml`
- llama-swap binary: `~/bin/llama-swap` (council build tag)
- llama-server binary (A380/SYCL): `~/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/build-sycl-prod/bin/llama-server`
- Slots (tmpfs): `~/Coding-Projects/7-council/council-config/slots/` (48GB)
- Models: `~/models/`
- Council memory: `~/.council-memory/`
- Memsearch DB: `~/.memsearch/milvus.db/`
- Pipeline state: `~/.council-memory/pipelines/`
- Phase state: `~/.council-memory/phase-state/`
- Bench results: `~/Coding-Projects/7-council/bench-results/`
- Arc summarizer config: `~/Coding-Projects/7-council/super_council/arc_summarizer/start.sh`
- Consolidation pipeline: `~/Coding-Projects/7-council/super_council/memory_service/consolidate/`
- Semantic memory: `~/.council-memory/semantic-memory/`
