# Council Review — Remaining Issues & Action Items

**Date:** 2026-05-09
**Reviewers:** Nemotron-Cascade-2-30B (logic), Gemma-4-26B (architecture)
**Files reviewed:** `slot-supervisor.py` (1821 lines), `config.json`

---

## Completed Fixes (on disk, needs restart)

| # | Fix | File |
|---|---|---|
| 1 | `fanout_in_progress` race — moved check inside `with self.lock:` | `slot-supervisor.py` |
| 2 | Thread-safe stats — `_stats_lock` + `_inc_stat()` helper, all 11 increments updated | `slot-supervisor.py` |
| 3 | Decouple TinyCouncilManager — explicit `council_aliases`/`council_configs` args, `_resolve_council_group()` | `slot-supervisor.py` |
| 4 | Socket leak in `_check_port()` — `finally: sock.close()` | `slot-supervisor.py` |
| 5 | Parallel fanout OOM risk — 2s stagger between `proc.start()` calls | `slot-supervisor.py` |
| 6 | Config `group_defaults` merge — `ModelRegistry.load()` merges group defaults into each model | `slot-supervisor.py` |
| 7 | Config deduplication — tiny_council and gpu_chat use `group_defaults` to eliminate repeated flags | `config.json` |

---

## Remaining Issues (flagged but not implemented)

### MEDIUM

| # | Issue | Reviewer | Details |
|---|---|---|---|
| **A** | **Signal handler deadlock during overlap join** | Gemma | SIGINT during `t_load.join()` could deadlock `httpd.shutdown()`. Fix: skip `httpd.shutdown()` when overlap threads are active, or use `stop_event` only. Low-probability edge case (only hits on Ctrl+C during swap). |
| **B** | **Async slot save** | Nemotron | `_save_current_slot()` blocks HTTP response thread. On tmpfs this is ~0.3s (not 500ms). Making it async risks slot loss on crash. Trade-off: faster responses vs. potentially stale slots. |

### LOW

| # | Issue | Reviewer | Details |
|---|---|---|---|
| **C** | **nvidia-smi result caching** | Nemotron | Subprocess spawn every 0.2s during VRAM wait = ~0.75s CPU overhead/swap (5% of 16s cycle). Fix: 1s TTL cache on `_get_free_vram()`. |
| **D** | **Job cleanup exception handling** | Nemotron | `_job_cleanup_loop()` doesn't catch exceptions during dict mutation. Runs every 5 min under lock — unlikely to trigger. |
| **E** | **`_failures` backoff growth on repeated failure** | Both | If same model repeatedly fails, backoff grows exponentially. This is intended behavior — prevents thrashing. No change needed unless you want a max-backoff decay mechanism. |
| **F** | **Exception masking** | Gemma | Generic `Exception` wrapped as `RuntimeError`. `raise ... from e` preserves full traceback chain. Not a real issue. |

---

## Model Disk Access — Current Limitations & Options

### Why models can't read files

The reviewer models (Nemotron-Cascade, Gemma-4, etc.) run inside **llama-server**, which is a pure inference engine exposing an OpenAI-compatible HTTP API. They receive text prompts and return text completions. No filesystem access because:

1. **llama-server has no file-reading tool** — It's a chat completion server, not an agent runtime
2. **Security isolation** — Giving LLMs filesystem access = arbitrary file read/write risk
3. **HTTP API is stateless** — Each request is independent; model sees only what's in the prompt

### Current approach: embed full files in prompts

Works because reviewer models have 20K context windows and our files fit:
- `slot-supervisor.py` — 75KB text ≈ ~15K tokens
- `config.json` — 7.8KB ≈ ~1.5K tokens

### Options for better file access

| Approach | How | Pros | Cons |
|---|---|---|---|
| **1. Embed in prompt** (current) | Read files in Python, paste into `messages` | Simple, works now | Context window limit. Large files get truncated. |
| **2. Tool-use loop** | Wire up `read_file(path, offset, limit)` tool. Both Nemotron-Cascade and Gemma-4 support tools in their templates. Model requests specific sections on demand. | Efficient context use. Focused review. | Requires building tool execution loop in supervisor. Non-trivial. |
| **3. External agent framework** | LangChain, CrewAI, or custom agent with `read`, `bash`, `grep` tools | Full filesystem access, chaining | Adds complexity, latency, dependencies. Overkill. |
| **4. Truncate + summarize** | Send only relevant sections (functions, configs) | Stays within context window | Models miss cross-file context. |

### Recommendation

**Option 2 (tool-use)** is the most practical upgrade. Both reviewer models have tool support in their chat templates. Would enable models to explore the codebase on demand without burning context budget. Requires building the tool loop — separate project.

---

## Reviewer Hallucinations to Note

| Claim | Reality |
|---|---|
| "Qwen3.6-27B ngl=64 will OOM" | TCQ (`ctk=q8_0, ctv=turbo4`) keeps it at 18.9GB. Fits in 24GB. |
| "Slot saves write to NVMe" | Slots are on tmpfs (RAM disk, 48GB). Saves are ~0.3s. |
| "Socket not closed on port check success" | Fixed in this round — was a real issue, now resolved with `finally: sock.close()`. |
| "VRAM wait timeout lets swap proceed unsafely" | Intentional: if VRAM wait times out but CUDA driver serialized the load, swap is valid. |
| Line numbers throughout | Both models hallucinated line numbers. Code has shifted since training data. |
