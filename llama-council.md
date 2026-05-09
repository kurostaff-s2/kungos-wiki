# Llama Council Setup Log

## Session: 2026-05-07 — Smoke Test Run

**Goal:** Run live smoke test against Qwen3-4B to validate H1-H7 assumptions and confirm slot naming convention.

### Results

| Assumption | Result |
|---|---|
| H1: Save API returns 2xx | ✅ Confirmed — `{id_slot, filename, n_saved, n_written, timings}` |
| H2: Restore API returns token count | ✅ Confirmed — `{id_slot, filename, n_restored, n_read, timings}` |
| H3: `/health` endpoint | ✅ `/v1/health` works (fixed in script) |
| H4: `/metrics` endpoint | ✅ 501 fallback to `{}` (guarded in script) |
| H5: `--auto-save-slots` flags | ✅ Not needed — explicit POST save/restore |
| H6: `--slot-save-path` nested dir | ✅ Server started with nested path |
| H7: Slot filenames | ✅ `filename` param respected — saved as `slot-0.bin`, `qsgg` magic |

### 🔴 Critical Finding: `n_saved: 0`

Both save operations returned `n_saved: 0`, `n_written: 20` (header only). Slot file is 20-byte `qsgg` header with **no actual KV cache data**. Restore gives zero benefit.

**Likely causes:** idle slot cleared, `--cache-reuse` interference, `-np 4` distribution
**Investigation needed:** `-np 1`, `--cache-ram 0`, active-slot save, larger context

**Full log:** `~/Coding-Projects/7-council/llama-council/scripts/slot-smoke-run.log` (⚠️ INACTIVE — from original build)

---

## Session: 2026-05-06

### Goal
Set up slot persistence (PRs #20819 + #20822) and prepare the 7-step Council-Build-Council pipeline for Kungos.

---

## PR Cherry-Pick

**Repo:** `/home/chief/Coding-Projects/7-council/llama-council/` (⚠️ **INACTIVE** — council now runs from `llama-cpp-turboquant/`)
**Base:** llama.cpp master `bf76ac77b` (ggml-org/llama.cpp)

### Cherry-Picked Commits

| PR | Commit | Description | Status |
|---|---|---|---|
| #20819 | `d5c325051` | server: persist context checkpoints across slot save/restore | ✅ Cherry-picked as `362bbba5a` |
| #20822 | `6d7dc316f` | server: auto-save/restore slot state on child exit/start in router mode | ✅ Cherry-picked as `76a4a57f7` |

### Files Changed (198 lines added)
- `tools/server/server-context.cpp` — checkpoint persistence logic
- `tools/server/server-context.h` — header updates
- `tools/server/server.cpp` — auto-save/restore in router mode

### Build
- **Location:** `/home/chief/Coding-Projects/7-council/llama-council/build/` (⚠️ **INACTIVE** — active build: `llama-cpp-turboquant/build/`)
- **Config:** GGML_CUDA=ON, GGML_CUDA_FA=ON, GGML_CUDA_FA_ALL_QUANTS=ON, GGML_CUDA_GRAPHS=ON, GGML_NATIVE=ON, compression=speed
- **Binary:** `build/bin/llama-server` ✅ Built successfully
- **ggml commit:** `76a4a57f7`

---

## Model Inventory

### Currently Available

| Role | Model | File | Size | Quant | Fits 24GB? |
|---|---|---|---|---|---|
| Chair | Qwen3.6-27B | `Qwen3.6-27B-UD-Q4_K_XL.gguf` | 17GB | Q4_K_XL | ✅ |
| Chair alt | Qwen3.6-27B | `Qwen3.6-27B-UD-Q5_K_XL.gguf` | 19GB | Q5_K_XL | ✅ (tight) |
| Builder | Qwen3-Coder-30B-A3B | `Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf` | 16GB | IQ4_XS | ✅ |
| Builder 1M | Qwen3-Coder-30B-A3B | `Qwen3-Coder-30B-A3B-Instruct-1M-IQ4_XS.gguf` | 16GB | IQ4_XS | ✅ |
| Reviewer | Nemotron-Cascade-2-30B | `nvidia_Nemotron-Cascade-2-30B-A3B-IQ4_XS.gguf` | 17GB | IQ4_XS | ✅ |
| Reviewer | Gemma-4-26B-A4B | `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` | 16GB | Q4_K_M | ✅ |
| Reviewer | Qwen3.6-35B-A3B | `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | 21GB | Q4_K_XL | ✅ (tight) |
| Reviewer | Qwen3.6-35B-A3B | `Qwen3.6-35B-A3B-UD-Q6_K_XL.gguf` | 30GB | Q6_K_XL | ❌ too big |
| Vision | mmproj | `mmproj-F16.gguf` | 858MB | F16 | ✅ |

### Tiny Council (on disk)

| Role | Model | File | Size | Quant |
|---|---|---|---|---|
| Tiny Chair | Ministral-8B | `Ministral-8B-Instruct-2410-Q6_K.gguf` | 6.2G | Q6_K |
| Tiny Builder | Nemotron-Nano-4B | `NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf` | 3.8G | Q6_K |
| Tiny Reviewer | Qwen3-4B | `Qwen3-4B-Instruct-2507-Q6_K.gguf` | 3.1G | Q6_K |

**Trio co-resident budget:** 13.1G total — zero swap cost, all fit together in 24GB.

### Bonus Models

| Model | File | Size | Fits 24GB? |
|---|---|---|---|
| GPT-OSS-20B | `gpt-oss-20b-Q4_K_M.gguf` | 11G | ✅ |
| Qwen3-Coder-Next | `Qwen3-Coder-Next-Q4_K_M.gguf` | 46G | ❌ |

---

## Slot Persistence with Pi Agent

### Why Pi Agent > opencode for Slot Persistence

| Factor | opencode | Pi Agent |
|---|---|---|
| **Volatile tokens** | Injects `<TS>`, `<DATE>`, `<EPOCH>`, `<CLOCK>` into system prompts | **No volatile injection** |
| **Cache stabilization** | Requires `OPENCODE_EXPERIMENTAL_CACHE_STABILIZATION=1` (PR #14743) | **Not needed** |
| **KV cache matching** | Breaks without the flag — every request = new cache entry | **Works out of the box** |
| **Config location** | `~/.config/opencode/` | `~/.pi/agent/models.json` |

Pi agent is already configured to talk to llama.cpp via OpenAI-compatible API (`models.json` → `llama-cpp` + `llama-cpp-turboquant` providers). Pointing it at the llama-council binary requires only a provider entry change.

### The Compaction Conflict

Pi auto-compacts when context exceeds `contextWindow - reserveTokens` (default 16384 reserve). It replaces old messages with a structured summary.

**The problem:** Saved slot has full original context. After compaction, pi sends:
```
[system prompt] + [compaction summary] + [recent messages]
```
But the slot was saved with:
```
[system prompt] + [all original messages]
```
**KV cache mismatch → slot restore fails → full re-prefill anyway.**

### Resolution Strategies

| Strategy | How | Trade-off |
|---|---|---|
| **1. Disable compaction** | `"compaction": {"enabled": false}` in `.pi/settings.json` | Context must fit in window — fine for 128K-192K windows on short sessions |
| **2. Accept re-prefill after compaction** | Slot-supervisor hashes prefixes; compaction = slot miss → pays prefill once → new slot saves → subsequent hits cache | One extra prefill per compaction event; still saves on all requests between compactions |
| **3. Separate pi sessions per role** | Each model role (Chair, Builder, Reviewer) gets its own pi session + llama-server instance | Cleanest — short conversations per role, compaction rarely triggers, slot persistence works perfectly |
| **4. Defer compaction** | Increase `keepRecentTokens` (e.g. 50000) and `reserveTokens` (e.g. 32768) | Pushes compaction further out; works if tasks don't exceed ~100K tokens |

### Recommended Architecture (Strategy 3)

```
Chair server   → port 8001 → pi session A (orchestrator, long context)
Builder server → port 8003 → pi session B (one task, short context)
Reviewer server→ port 8004 → pi session C (one review, short context)
```

- Each role conversation is short (one spec → one build → one review)
- No compaction needed within a single role's turn
- Slot persistence works perfectly on short, stable contexts
- Compaction only matters for the Chair session — can use strategy 1 or 2 there

### Wiring Pi to llama-council

Add a provider entry in `~/.pi/agent/models.json`:

```json
"llama-council": {
  "baseUrl": "http://127.0.0.1:8005",
  "api": "openai-completions",
  "apiKey": "local",
  "authHeader": true,
  "models": [
    { "id": "chair", "name": "Qwen3.6-27B", "contextWindow": 131072, "maxTokens": 16384 }
  ]
}
```

Start llama-council binary with:
```
./llama-server -m <model> --port 8005 --auto-save-slots --auto-restore-slots --slot-save-path /path/to/slots
```

---

## Existing Tooling

| Tool | Status | Notes |
|---|---|---|
| llama.cpp main | ✅ | Has `--slot-save-path` (manual save/restore) |
| llama-cpp-turboquant | ✅ | Same as main, no auto-save/restore |
| **llama-council** (7-council repo) | ✅ | Has `--auto-save-slots` + `--auto-restore-slots` |
| llama-swap | ✅ Installed at `/home/chief/bin/llama-swap` | Ready |
| opencode | ✅ Installed | Alternative to Pi, needs `OPENCODE_EXPERIMENTAL_CACHE_STABILIZATION=1` |
| **Pi Agent** | ✅ Default orchestrator | No volatile tokens, no cache stabilization needed |

---

## Hardware Context

- **GPU:** RTX 3090 Ti (24GB VRAM)
- **RAM:** 96GB DDR5
- **Storage:** Gen5 NVMe (budget tier, ~1000 MB/s read)
- **Disk Free:** ~515GB

---

## Research: Council Design Findings (2026-05-06)

### R1. Diversity > Size (NEO LLM Council)

> **Source:** [heyneo.com/blog/llm-council](https://heyneo.com/blog/llm-council/)

NEO built a multi-model consensus engine in ~200 lines of Python. Key finding:

- **"Council size matters less than council diversity."**
- Three models with different architectures and training regimes **outperform** five models from the same provider family.
- Hallucination reduction comes from **diversity, not bigger models**.

**Implication:** Adding Qwen3-Coder as a reviewer adds no diversity — it's same Alibaba lineage as Qwen3.6-27B/35B already in the council. Same-family models yield diminishing returns.

---

### R2. Systematic Overcorrection in Code Review (arXiv 2603.00539)

> **Source:** [arxiv.org/abs/2603.00539](https://arxiv.org/abs/2603.00539v1) — Jin & Chen, University of Sydney, Feb 2026

> **"LLMs frequently misclassify correct code implementation as non-compliant or defective."**

Key findings:
- LLMs have **systematic overcorrection** in code review — they flag correct code as buggy
- **More detailed prompts make it worse** — asking for explanations and proposed corrections **increases** misjudgment rates
- Code-specialized models are **prone to over-flagging** in review tasks
- Authors propose a "Fix-guided Verification Filter" to treat proposed fixes as executable counterfactual evidence

**Implication for council:**
- Code-trained models (Qwen3-Coder) should **not** be primary reviewers — they over-flag
- Keep review prompts **simple and specific**: "flag or pass", not "explain and propose fixes"
- The 7-step pipeline's review stage needs **prompt discipline** to avoid false positives

---

### R3. LLMs as Code Review Agents (Springer, 2026)

> **Source:** [link.springer.com/chapter/10.1007/978-3-032-09318-9_24](https://link.springer.com/chapter/10.1007/978-3-032-09318-9_24)

23 articles reviewed, 12 quantifiable metrics, 75 source code files tested:

- **Claude Sonnet** showed strongest agreement with human expert review
- **GPT-4o-mini** offered best balance of performance and cost
- LLMs assign **higher scores than humans** for complex architectural dimensions (Liskov substitution, dependency inversion) — i.e., **too lenient on architecture, too strict on syntax**

**Implication:** Need at least one reviewer that's **strict on structure** (Nemotron-Cascade for logic, Gemma for architecture) to counterbalance leniency.

---

### R4. Qwen3-Coder Positioning (Fireworks AI, Aug 2025)

> **Source:** [fireworks.ai/blog/qwen-3-decoded](https://fireworks.ai/blog/qwen-3-decoded)

- Qwen3-Coder: **"purpose-built for agentic coding workflows, repository-scale development, and tool-driven software engineering"**
- Fine-tuned on coding tasks via RL — not just pretrained on code corpora
- Qwen3-Coder-480B-A35B Instruct: "quality near GPT-4.1" for coding
- **Positioning: code generation and agentic workflows, not code review**

**Implication:** Qwen3-Coder belongs in the **Builder** role, not the Reviewer role. OP's separation was correct.

---

### R5. Synthesis: Council Composition Guidance

| Principle | Source | Application |
|---|---|---|
| **Diversity > size** | NEO (R1) | 4 lineages (Qwen, Gemma, GPT-OSS, Nemotron) > 5 same-family models |
| **Code-trained ≠ good reviewer** | arXiv (R2) | Qwen3-Coder as Builder only, not Reviewer |
| **Simple prompts for review** | arXiv (R2) | "Flag or pass" — don't ask for explanations/fixes |
| **Need architecture-strict reviewer** | Springer (R3) | Nemotron-Cascade + Gemma cover logic and structure |
| **Builder/Reviewer separation** | Fireworks (R4) | Code generation and code review are different tasks |

**Recommended reviewer roster (validated by research):**

| Reviewer | Lineage | Arch | What It Catches |
|---|---|---|---|
| Nemotron-Cascade-2-30B | NVIDIA | MoE | Logic errors, edge cases, security gaps |
| Gemma-4-26B | Google | Dense | Architecture consistency, structural issues |
| GPT-OSS-20B | OpenAI | Dense | Different tokenizer, different failure modes |
| Qwen3.6-35B | Alibaba | Dense | Final authority, subtle bugs smaller models skip |

**Tiny Council (concurrent, 13.1G, ~20s):**

| Model | Lineage | Role |
|---|---|---|
| Ministral-8B | Mistral | Structured checks, tool-use |
| Nemotron-Nano-4B | NVIDIA | Quick logic/sanity checks |
| Qwen3-4B | Alibaba | Third perspective, broad coverage |

---

## Next Steps

1. [ ] Test llama-council binary with `--auto-save-slots --auto-restore-slots`
2. [ ] Write slot-supervisor.py for Kungos workflow
3. [ ] Configure llama-swap groups for council rotation
4. [ ] Wire Pi Agent to llama-council provider (optional, if replacing current providers)
5. [ ] Decide: disable compaction for Chair session or accept re-prefill after compaction
6. [ ] Draft review prompts (simple "flag or pass" per R2)
7. [ ] Build council composition decision tree (Tiny trio → escalate to which larger reviewer?)
