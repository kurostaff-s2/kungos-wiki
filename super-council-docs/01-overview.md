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
|              Super-Council Supervisor                            |
|              [listen_port:8090]                                  |
|                                                                  |
|  +----------+  +----------+  +----------+  +----------------+  |
|  |Delegation |  |  Fanout  |  |  Chain   |  |   Pipeline    |  |
|  |(reviews)  |  |(small    |  |(refactor)|  |  PRIMARY PATH |  |
|  |           |  | models)  |  |          |  | for ALL WORK  |  |
|  +----------+  +----------+  +----------+  +----------------+  |
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
+--------------------------------+---------------------------------+
                                 | proxy
                                 v
+------------------------------------------------------------------+
|              llama-server                                        |
|              [upstream_port:8091]                                |
|                                                                  |
|  +----------+  +----------+  +----------+  +----------+        |
|  |  chair   |  | co-chair |  | reviewer |  |  vice-   |        |
|  |(default) |  |          |  |    x3    |  | granite  |        |
|  +----------+  +----------+  +----------+  +----------+        |
+------------------------------------------------------------------+
```

## Usage Rules

### Pipeline is the Primary Path

**All reviews, builds, and multi-phase work flows through `/v1/council/pipeline`.**

The pipeline provides:
- State machine context management (SCOUT → PLAN → BUILD → REVIEW → ...)
- RelationalStore persistence (SQLite, WAL mode, FK enforced)
- Automatic retry/retreat logic (per-phase + global ceiling)
- Artifact indexing into memsearch
- Structured event logging

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
| `SlotSupervisor` | `super_council.py` | Proxy frontend, slot management, model swapping, delegation |
| `PipelineState` | `super_council.py` | 6-phase state machine with retry/retreat/ceiling |
| `ChairGateState` | `super_council.py` | 5-step TDD gate validation (RED→GREEN→REFACTOR) |
| `RelationalStore` | `relational_store.py` | SQLite-backed store with WAL, FK enforcement, schema seeding |
| `ContextRouter` | `context_router.py` | Structured queries: snapshots, events, similar runs, issues |
| `MemoryLayer` | `memory_layer.py` | Token-budgeted context slices with artifact boundaries |
| `MicroModelEnricher` | `micro_model.py` | Async semantic enrichment (ONNX embeddings, TF-IDF keywords) |
| `StateMachineLinter` | `state_linter.py` | 8-check linter for transition graph validation |
| `TinyCouncilManager` | `super_council.py` | Fanout coordinator (parallel/sequential mode selection) |

## Key Design Decisions

1. **Proxy architecture:** Stable frontend port survives swap churn. Clients never see upstream restarts.
2. **Per-model slot namespace:** `<alias>/<config_hash>/` prevents cross-model KV corruption.
3. **Binary hash tracker:** Purges all slots on llama-server binary change.
4. **SQLite + WAL:** Atomic transitions, FK enforcement, zero auto-checkpoint (manual only).
5. **Single-slot GPU:** All models serialize through one GPU. Wall-clock = sum of tasks.
6. **Artifact boundaries:** MemoryLayer never cuts mid-artifact. Uses `ARTIFACT_BOUNDARY` markers.
7. **DESC ordering:** Newest artifacts preserved when budget is tight (MODERATE-2 fix).
8. **Heuristic fallback:** MicroModelEnricher works without ONNX model (TF-IDF keywords, pattern matching).

## Configuration

### Dual-Config Architecture

The supervisor uses **two config files** for clean separation of concerns:

| File | Purpose | Loaded By |
|------|---------|-----------|
| `config-subsystem.json` | Subsystem settings: `default_alias`, `voice_pipeline`, `summarizer` | `ModelRegistry` (subsystem settings) |
| `upstream-config.json` | Inference-upstream: model definitions, server flags, KV cache types | `ModelRegistry` (inference-upstream section) |

**Server flags flow:** `upstream-config.json` → `ModelInfo.extra` → `ModelConfig.server_flags` → `build_args()` → llama-server CLI.

Every flag in `upstream-config.json` is passed to the upstream llama-server. Missing flags (e.g., `--flash-attn`, `--mlock`, `--cont-batching`, `--spec-type`, `--reasoning`) cause the upstream to run with defaults, resulting in degraded performance.

### Startup

```bash
# Default (auto-discovers sibling configs)
python3 -m super_council \
    --listen-port 8090 \
    --upstream-port 8091

# Explicit paths
python3 -m super_council \
    --listen-port 8090 \
    --upstream-port 8091 \
    --config /home/chief/Coding-Projects/7-council/super_council/config-subsystem.json \
    --upstream-config /home/chief/Coding-Projects/7-council/super_council/upstream-config.json \
    --slot-dir /home/chief/Coding-Projects/7-council/council-config/slots
```

### llama-server Binaries

| Binary | Purpose | Models |
|--------|---------|--------|
| `llama-cpp-turboquant/build/bin/llama-server` | Default upstream (turboquant fork) | qwen3.6-27b, gemma-4-26b, nemotron-cascade, gpt-oss-20b, qwen3.6-35b-a3b, granite-8b |
| `indras-mirror-fork/build/bin/llama-server` | MTP speculative decoding (fused TBQ4 FA) | qwen3.6-27b-flash, qwen3.6-27b-uhn, qwen3.6-uhn-q5-builder |

**Indras-Mirror fork features:**
- Fused TBQ4 flash attention kernels (`GGML_CUDA_FA_ALL_QUANTS=ON`)
- Native MTP speculative decoding (`--spec-type mtp --spec-draft-n-max 3`)
- Slot persistence (upstream native, no cherry-picks)
- KV cache format: `tbq4_0` (first swap rebuilds from `turbo4`)
- Compiled for RTX 3090 (compute 8.6)

### MTP Performance (Q4_K_M Heretic-v2, tbq4_0 KV)

| Generated Tokens | PP (t/s) | TG (t/s) | Draft Acceptance |
|-----------------|----------|----------|------------------|
| 100 | 291 | 66.8 | 93.6% |
| 200 | 291 | 56.9 | 76.2% |
| 500 | 210 | 49.5 | 62.0% |
| 1000 | 245 | 47.3 | 58.6% |

*vs. vanilla decode (llama-bench): ~37 t/s TG at 64 tokens. MTP adds ~30 t/s boost at short lengths.*

## File Locations

| Resource | Path |
|----------|------|
| Supervisor source | `~/Coding-Projects/7-council/super_council/` |
| Subsystem config | `~/Coding-Projects/7-council/super_council/config-subsystem.json` |
| Upstream config | `~/Coding-Projects/7-council/super_council/upstream-config.json` |
| Slots | `~/Coding-Projects/7-council/council-config/slots/` |
| Models | `~/models/` |
| Council memory | `~/.council-memory/` |
| Phase state | `~/.council-memory/phase-state/` |
| Pipeline state | `~/.council-memory/pipelines/` |
| Supervisor log | `/tmp/super-council.log` |
| Embedding model | `~/models/embedding/pplx-embed-v1-0.6b-int8/` |
| MTP binary (indras-mirror-fork) | `~/Coding-Projects/7-council/indras-mirror-fork/build/bin/llama-server` |
| Bench results | `~/Coding-Projects/7-council/bench-results/` |
