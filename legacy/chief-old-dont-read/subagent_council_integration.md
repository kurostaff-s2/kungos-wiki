---
tags: [architecture, agents, local-llm, hardware, planning]
created: 2026-05-18
updated: 2026-05-18
sources: [local-hardware, council-architecture, SuperMemory]
related: [[ADR-001-local-llm]], [[ADR-002-dual-model]], [[ADR-003-llama-cpp]], [[council-architecture]], [[SuperMemory]]
status: stable
---

# ADR-007: Subagent LLM Council & MemSearch Integration

## Summary

This ADR establishes the official architecture for integrating a multi-model **LLM Council** and **MemSearch** (hybrid keyword-vector search) using an isolated **Subagent-based** framework. It leverages a single **RTX 3090 GPU (Ryzen 7 7700, 96GB RAM)** system by combining **sequential slot persistence** (which reduces model swap overhead by 98%) with **lightweight isolated subprocesses**. This prevents token bloat, resolves context pollution, and ensures high-quality, robust code iteration via TDD-gated loops. It adopts proven patterns from existing packages like `super-pi` (TDD-gated development, checkpoint resuming) and `@narumitw/pi-subagents` (isolated worker subprocesses, natural delegation).

## Details

### 1. The Core Problem: Monolithic Token & Latency Bloat

Standard coding agent interactions operate in a single monolithic context. As the session progresses, reading files and generating code, the context size rapidly grows past 50K–80K tokens. On a single RTX 3090 GPU, this causes two severe failure modes:
1. **Exponential Prefill Latency**: Reprocessing the growing context on every turn triggers huge prompt-processing (PP) delays (~80 seconds at 80K context).
2. **Context Pollution / Drift**: High context volume dilutes instruction compliance, causing models to hallucinate, ignore architectural rules, or generate sub-par code.

### 2. The Solution: Isolated Subagents & Sequential Swapping

By delegating tasks to specialized subagents running in isolated subprocesses (the `@narumitw/pi-subagents` pattern), we encapsulate their contexts. A subagent only receives the exact inputs (e.g., class signature, specific file content, specific test output) it needs. This keeps the active context under 5K–10K tokens, ensuring near-instant prefill and highly focused generation.

To run multiple models on a single 24GB GPU without massive startup overhead, we use a tiered VRAM/RAM sequential swap system:

```
                  ┌───────────────────────────────────────────────┐
                  │                 96GB DDR5 RAM                 │
                  │   (Chair, Builder, and Reviewers cached on    │
                  │        disk/RAM for rapid GGUF reloading)     │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼  llama-swap (2s swap)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           RTX 3090 GPU (24GB VRAM)                              │
│                                                                                 │
│  ┌────────────────────────────────────────┐ ┌────────────────────────────────┐  │
│  │             Tiny Council               │ │        Active Solo Worker      │  │
│  │            (Co-resident)               │ │      (Sequentially Loaded)     │  │
│  │                                        │ │                                │  │
│  │  Ministral-8B + Nemotron-Nano-4B       │ │  e.g., Qwen3-Coder-30B (12.5GB)│  │
│  │  + Qwen3-4B                            │ │  or Gemma-4-31B (17.3GB)       │  │
│  │  Quantization: Q6_K                    │ │  Uses `--fit on` to spill KV   │  │
│  │  VRAM: ~11 GB (Never evicted)          │ │  VRAM: ~13 GB remaining        │  │
│  └────────────────────────────────────────┘ └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

* **The Tiny Council (Co-resident)**: Three fast, lightweight models (Ministral-8B + Nemotron-Nano-4B + Qwen3-4B at Q6_K quant) remain loaded in ~11GB of VRAM. They provide instant, zero-swap 3-way parallel speculative critique and initial checks.
* **The Solo Workers (Sequential Swapping)**: The orchestrator sequentially loads large specialist models (Chair, Builder, specialized Reviewers) into the remaining 13GB VRAM. 
* **Slot Persistence**: PRs #20819 + #20822 (by @European-tech) are cherry-picked into the turboquant build and live in production. They persist context checkpoints (`<file>.checkpoints` companion files) alongside raw KV cache, enabling slot save/restore across model swaps. Swapping a model and restoring its 96K KV context takes **under 2.5 seconds** (compared to ~165 seconds of cold prefill waste). Upstream status: open, not merged.

---

### 3. Subagent Integration & Role Mapping

We map our **7-Step LLM Council** roles to dedicated subagents defined in `.pi/agents/*.md`:

| Subagent Role | Model | quant | Context | Purpose / Specialization |
|---|---|---|---|---|
| **`scout`** | Ministral-8B | Q6_K | 10K | Uses `memsearch` and `grep` tools to query codebase and wiki. |
| **`planner`** | Qwen3.6-27B | Q4_K_M | 64K | Standardizes specifications, synthesizes findings, designs architecture. |
| **`builder`** | Qwen3-Coder-30B | IQ4_XS | 50K | Writes actual code, manages files, runs tests (MoE coding specialist). |
| **`reviewer-arch`** | Gemma-4-31B | Q4_K_M | 20K | Audits code structure, validates architectural constitution compliance. |
| **`reviewer-logic`** | Nemotron-Cascade-2-30B | IQ4_XS | 20K | Flags logic errors, checks edge cases, verifies boundaries. |
| **`reviewer-security`** | Qwen3.6-35B | Q4_K_M | 20K | Audits tenant isolation, authorization, and data injection risks. |
| **`chair`** (Orchestrator) | Qwen3.6-27B | Q4_K_M | 130K | Coordinates the pipeline, aggregates subagent outputs, runs UAT. |

---

### 4. MemSearch Integration & Context Tiering

To maximize token efficiency, we integrate **MemSearch** (hybrid keyword-vector search) into our subagent workflows following a tiered recall architecture:

```
┌────────────────────────────────────────────────────────┐
│                        USER INPUT                      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                        TIER 0                          │
│ Curated memory check (context/MEMORY.md - zero cost)   │
└───────────────────────────┬────────────────────────────┘
                            │ (not found)
                            ▼
┌────────────────────────────────────────────────────────┐
│                        LEVEL 1                         │
│ Spawn scout subagent -> Hybrid Vector Search           │
│ memsearch search "query" --top-k 5 (under 2k tokens)    │
└───────────────────────────┬────────────────────────────┘
                            │ (needs full content)
                            ▼
┌────────────────────────────────────────────────────────┐
│                        LEVEL 2                         │
│ Expand targeted match block -> memsearch expand        │
└────────────────────────────────────────────────────────┘
```

* **Scout Tooling**: The `scout` subagent performs high-speed semantic index retrieval, reading only the necessary file slices and ADRs.
* **Context Capping**: The main coordinator (`chair`) holds a high-level representation of state using `context/MEMORY.md` (capped at 2,500 characters), which is reloaded at the start of a new session. It never directly holds raw source code in its context.

---

### 5. High-Quality Iteration: TDD-Gated & Evidence-First Loops

To prevent sub-par or broken code output, the subagent pipeline incorporates core principles from `super-pi` and `pi-subagents`:

```
┌─────────────────┐
│ 1. Spec & Plan  ├────────┐
└─────────────────┘        │
                           ▼
                 ┌───────────────────┐
                 │ 2. TDD-Gate:      │
                 │ Write Unit Test   │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ 3. Build & Run    │◄───────┐ (Failed)
                 │ Local Test Command│        │
                 └─────────┬─────────┘        │
                           │                  │
                           ├─► [Test Passes?]─┘
                           │   (Remediation)
                           ▼ (Success)
                 ┌───────────────────┐
                 │ 4. Fan-out Review │
                 │ Arch & Logic flags│
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ 5. Security & UAT │
                 └───────────────────┘
```

1. **TDD-Gated Implementation**: The `builder` subagent does not return code immediately. It must first write a unit test demonstrating the change, run it against the codebase, and iteratively modify its code until the test passes.
2. **Evidence-First Critiques**: Reviewer subagents are constrained by structured, simple prompts (as proven by arXiv R2). They do not write long explanations; they respond with simple `[ISSUE] <one-line description> + <evidence code line>` or `[PASS]`. This reduces false-positive reviews by 30% and keeps tokens extremely low.
3. **Checkpoint Resuming**: The orchestrator writes the pipeline state at every phase (e.g., `Discovery`, `Planning`, `TDD-Write`, `Local-Compile`, `Review-Phase`) to `context/memory/`. If a subagent times out or errors, the pipeline resumes immediately from the exact phase checkpoint.

---

### 6. Hardware Optimization & Run Tunings

We apply the following low-level system tunings to maximize single RTX 3090 throughput:
* **Asymmetric KV Cache on Chair**: Configured at `--ctx-size 98304` (96K) with `-ctk q8_0 -ctv turbo4` and `--fit on` to spill KV cache to system memory when VRAM is full. The `q8_0/turbo4` combination at 130K would require ~26.4GB (doesn't fit on 24GB). At 96K with `--fit on`, the KV cache spills gracefully to DDR5. Run with `TURBO_AUTO_ASYMMETRIC=0` to prevent silent K→q8_0 upgrade at long context (would OOM).
* **Speed Mode Compilations**: Rebuild both the core `llama-server` and `turboquant` with `-DGGML_CUDA_COMPRESSION_MODE=speed` to maximize kernel execution speeds.
* **CPU Tuning**: Configure the Ryzen 7 7700 CPU scaling governor to `performance` via `sudo cpupower frequency-set -g performance`.
* **Prompt Caching Fixes**: Cherry-pick the `server: fix prompt caching for hybrid models` commit into our server to ensure the MoE architectures (Builder Qwen3-Coder and Reviewer Qwen3.6-35B) cache prefill states properly.

## References

* [[local-ai-stack]] — Local LLM inference, models, and RAG configuration.
* [[Local-Hardware]] — Hardware benchmarks and detailed llama.cpp optimization recommendations.
* [[SuperMemory]] — Structured memory system combining MEMORY.md and MemSearch.
* [[council-architecture]] — LLM Council composition and architectural principles.
* `@narumitw/pi-subagents` — NPM package for isolated subprocess subagent delegation.
* `leing2021/super-pi` — GitHub repository for TDD-gated coding agents and iterative loops.
