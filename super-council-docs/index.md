# Super-Council Documentation Index

> Complete documentation for the super-council: evolved slot-supervisor with integrated state machine, relational layer, and semantic enrichment.

## Documents

| # | Document | Purpose |
|---|----------|---------|
| 01 | [Overview](01-overview.md) | Architecture, usage rules, core modules, key design decisions, file locations |
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

## Usage Rules

### Pipeline is Primary Path
**All reviews and multi-phase work flows through `/v1/council/pipeline`.** The state machine manages context, retry logic, and artifact persistence.

### Fanout is for Small Models Only
**Fanout (`/v1/council/fanout`) is ONLY for `tiny_council` models:** nemotron-nano, qwen3-4b, granite-tiny.
**Do NOT use fanout for reviewer models** (Nemotron, Gemma, GPT-OSS, co-chair) — 24GB VRAM cannot parallel-load them.

## Quick Reference

### Architecture
```
Client (Pi) → [listen_port:8090] ←proxy→ [upstream_port:8091:llama-server]
```

### Pipeline Flow
```
SCOUT → PLAN → BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE
     → PENDING_REVIEW → HUMAN_GATE → INDEX → DONE | FAILED
```

### Model Aliases (gpu_chat)
| Alias | Model | Role |
|-------|-------|------|
| `qwen3.6-27b` | Qwen3.6-27B-UD-Q4_K_XL | Chair (default) |
| `qwen3.6-27b-flash` | Qwen3.6-27B-Heretic-v2 Q4_K_M (MTP) | Flash MTP decode (indras-mirror-fork) |
| `qwen3.6-27b-uhn` | Qwen3.6-27B-Heretic-v2 Q4_K_M (MTP) | UHN MTP builder (161K ctx) |
| `qwen3.6-uhn-q5-builder` | Qwen3.6-27B-Heretic-v2 Q5_K_M (MTP) | UHN Q5 MTP builder (90K ctx) |
| `goal-checker-co-chair` | Qwen3.6-35B-A3B | Co-chair/Builder |
| `reviewer-logic` | Nemotron-Cascade-2-30B | Logic/security review |
| `reviewer-arch` | Gemma-4-26B-A4B | Architecture review |
| `reviewer-diversity` | GPT-OSS-20B | Diversity review |
| `vice-granite` | Granite-4.1-8B | Summarizer |
| `vice-ministral` | Ministral-3-8B | Vice-chair |

### MTP Models (indras-mirror-fork)
Uses the **Indras-Mirror fork** of llama.cpp with fused TBQ4 flash attention kernels and native MTP speculative decoding. Binary: `llama-forks/indras-mirror-fork/build/bin/llama-server`.

| Model | Quant | MTP Config | TG Speed |
|-------|-------|-----------|----------|
| `qwen3.6-27b-flash` | Q4_K_M | spec_type=mtp, draft_max=3 | ~67 t/s (100 tok) |
| `qwen3.6-27b-uhn` | Q4_K_M | spec_type=mtp, draft_max=3 | ~67 t/s (100 tok) |
| `qwen3.6-uhn-q5-builder` | Q5_K_M | spec_type=mtp, draft_max=3 | ~64 t/s (100 tok) |

*TG drops to ~47 t/s at 1000 tokens with 58.6% draft acceptance.*

### Fanout Pool (tiny_council)
| Alias | Model |
|-------|-------|
| `nemotron-nano` | Nemotron-3-Nano-4B |
| `qwen3-4b` | Qwen3-4B |
| `granite-tiny` | Granite-4.1-8B |

### Key Endpoints
- `POST /v1/chat/completions` — Chat with auto-swap
- `POST /v1/council/delegate` — One-shot delegation (use pipeline for reviews)
- `POST /v1/council/fanout` — Multi-model fanout (tiny_council only)
- `POST /v1/council/chain` — Multi-step delegation chain
- `POST /v1/council/pipeline` — **PRIMARY PATH** for all work
- `POST /v1/council/recall` — Active recall (memsearch)
- `POST /v1/council/summarize` — Session summarization

### Arc Summarizer (Memory Consolidation)
- Server: `127.0.0.1:18095` (llama-server SYCL on Arc A380)
- Model: `granite-4.1-3b-Q4_K_M` (Granite-4.1-3B)
- Roles: memory consolidation, session summarization, knowledge extraction
- Health: `GET http://127.0.0.1:18095/v1/models`
- systemd: `arc-summarizer.service` (user-level)

### File Locations
- Supervisor: `~/Coding-Projects/7-council/super_council/`
- Subsystem config: `~/Coding-Projects/7-council/super_council/config-subsystem.json` (default_alias, voice_pipeline, summarizer)
- Upstream config: `~/Coding-Projects/7-council/super_council/upstream-config.json` (model definitions, server flags)
- Slots: `~/Coding-Projects/7-council/council-config/slots/`
- Council memory: `~/.council-memory/`
- Pipeline state: `~/.council-memory/pipelines/`
- Phase state: `~/.council-memory/phase-state/`
- Supervisor log: `/tmp/super-council.log`
- MTP binary: `~/Coding-Projects/7-council/llama-forks/indras-mirror-fork/build/bin/llama-server`
- Turboquant binary: `~/Coding-Projects/7-council/llama-forks/llama-cpp-turboquant/build/bin/llama-server`
- Bench results: `~/Coding-Projects/7-council/bench-results/`
- Arc summarizer module: `~/Coding-Projects/7-council/super_council/arc_summarizer/`
- Arc summarizer service: `~/.config/systemd/user/arc-summarizer.service`
- Semantic memory: `~/.council-memory/semantic-memory/`
