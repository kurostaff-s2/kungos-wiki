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
| 08 | [Arc Summarizer](08-arc-summarizer.md) | Memory consolidation on Arc A380, Granite-4.1-3B, Tier 1 injection, pipeline API |
| 09 | [Memory Service](09-memory-service.md) | MemoryService architecture, FastMCP server, 22 tools, 7 resources, unified_log_recall, tool matrix |
| 10 | [Code Graph](10-codegraph.md) | CodeGraphStore API, 12 MCP tools, FTS5 search, call graph traversal, cross-DB JOINs with memory layer |
| 11 | [MemSearch](11-memsearch.md) | MemIndex vector indexing, Milvus-lite schema, hybrid search, raw session memory pipeline, direct text upsert |
| 14 | [Recall Search Fine-Tuning](14-recall-search-fine-tuning.md) | FTS5 indexes, analytics logging, UnifiedVectorStore, project filtering, verification |

## Plans & Analysis

| Document | Purpose |
|----------|--------|
| [AppFlowy Self-Host Plan](appflowy-selfhost-plan.md) | Same-machine deployment, CouncilDatabase (PostgreSQL), full refactor, no backward compat, AppFlowy synthesis |
| [AppFlowy Integration Analysis](appflowy-integration-analysis.md) | Feature inventory (35 council + 30 AppFlowy + 15 cross-system), gap analysis, options |
| [Arc Summarizer TODO](todo-arc-summarizer.md) | Arc Summarizer implementation checklist |

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
              Arc LLM (:18095 Granite-4.1-3B)
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
| `qwen-uhn-q5-fast` | Qwen3.6-27B UHN | Q5_K_M | 98K | Higher quality builder |
| `gemma-4-26b` | Gemma-4-26B | IQ4_XS | 98K | Google's voice |
| `gemma-4-26b-q4` | Gemma-4-26B | Q4_K_M | 98K | Alternative quant |
| `nemotron-cascade` | Nemotron-Cascade-2-30B | IQ4_XS | 98K | NVIDIA's reasoning |
| `nemotron-nano` | Nemotron-3-Nano-4B | Q6_K | 98K | Priority 5, fast |
| `gpt-oss-20b` | GPT-oss-20B | Q6_K_XL | 98K | OpenAI's voice |
| `gpt-oss-20b-q4` | GPT-oss-20B | Q4_K_M | 98K | Alternative quant |
| `mellum2-12b` | Mellum2-12B | Q5_K_L | 98K | Scout, fast |
| `nex-n2-mini` | Nex-N2-mini | Q4_K_L | 98K | Code specialist |

### Slot Persistence
- **Config:** `~/llama-swap/config.yaml` (all models have `slotStore.enabled: true`)
- **Slot dir:** `~/Coding-Projects/7-council/council-config/slots/` (48GB tmpfs)
- **Max slots:** 48 per model
- **Binary group:** `llama-flash` (all share same llama.cpp binary)
- **Checksum:** SHA-256 validation before restore
- **Orphan cleanup:** Stale slots removed on startup

### Key Endpoints
- `POST /v1/chat/completions` — Chat with auto-swap (via llama-swap :9292)
- `GET /running` — Running models
- `GET /api/slots/status` — Slot persistence status
- `POST /api/slots/save/{model}` — Manual slot save
- `POST /api/slots/restore/{model}` — Manual slot restore
- `POST /api/slots/cleanup` — Orphan cleanup

### Arc Summarizer (Memory Consolidation)
- Server: `127.0.0.1:18095` (llama-server on Arc A380)
- Model: `granite-4.1-3b-Q4_K_M` (Granite-4.1-3B)
- Roles: memory consolidation, session summarization, knowledge extraction
- Health: `GET http://127.0.0.1:18095/v1/models`

### File Locations
- llama-swap source: `~/llama-swap/`
- llama-swap config: `~/llama-swap/config.yaml`
- llama-swap binary: `~/bin/llama-swap` (council build tag)
- llama-server binary: `~/llama-cpp-latest/build/bin/llama-server`
- Slots (tmpfs): `~/Coding-Projects/7-council/council-config/slots/` (48GB)
- Models: `~/models/`
- Council memory: `~/.council-memory/`
- Memsearch DB: `~/.memsearch/milvus.db/`
- Pipeline state: `~/.council-memory/pipelines/`
- Phase state: `~/.council-memory/phase-state/`
- Bench results: `~/Coding-Projects/7-council/bench-results/`
- Arc summarizer module: `~/Coding-Projects/7-council/super_council/arc_summarizer/`
- Semantic memory: `~/.council-memory/semantic-memory/`
