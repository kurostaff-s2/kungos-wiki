# Audit: Move Memory Consolidation to Arc A380

**Date:** 2026-05-28
**Status:** Implemented — arc_summarizer module built, wired into super-council

---

## Implementation Summary

### Model Selection (benchmarked on Arc A380 SYCL)

| Model | Prompt t/s | Gen t/s | Total Time | YAML Quality | VRAM |
|-------|-----------|---------|------------|-------------|------|
| **Granite-4.1-3B** Q4_K_M | 20 | **21.4** | **5.2s** | Clean, no fences | 2.6 GB |
| Ministral-3-3B-Reasoning Q5_K_M | 24.5 | 11.9 | 14.1s | Wraps in ```yaml | 3.2 GB |
| Qwen3.5-4B Q5_K_M | 15.6 | 9.4 | 96.1s | SSM bottleneck | 3.5 GB |

**Winner: Granite-4.1-3B** — fastest generation, clean YAML output, stops naturally on EOS.

### Module: `arc_summarizer/`

```
arc_summarizer/
├── __init__.py      (153 lines) — ArcSummarizer unified interface
├── config.py        (103 lines) — ArcConfig from config-subsystem.json
├── client.py        (317 lines) — HTTP client: consolidation, summarization, extraction
├── prompts.py       (149 lines) — Prompt templates + YAML rendering
└── pipeline.py      (327 lines) — Startup pipeline + Tier 1 injection
```

**Total: 1049 lines** (vs 9K+ in super_council.py)

### Usage

```python
from super_council.arc_summarizer import ArcSummarizer

arc = ArcSummarizer.load(fallback_url="http://127.0.0.1:8091")

# Consolidation (startup)
arc.consolidate()  # blocking
arc.start_consolidation_thread()  # background

# Session summarization
summary = arc.summarize_session(turns)

# Knowledge extraction
knowledge = arc.extract_knowledge(text, schema)

# Tier 1 injection
card = arc.inject_tier1()
```

---

## Current State

### Hardware

| GPU | VRAM | Current Load | llama.cpp Build |
|-----|------|-------------|-----------------|
| **RTX 3090** (NVIDIA) | 24 GB (~21.5 GB used) | Qwen3.6-27B-UD on :8091 — main chat + consolidation | CUDA (`build/`) |
| **Arc A380** (Intel DG2) | 6 GB | **Idle** | SYCL (`build-sycl/`, v9031, IntelLLVM 2026.0.0) |

SYCL build verified working: Bonsai-1.7B-Q1_0 → 224.83 t/s (pp512), 19.77 t/s (tg128).

### Consolidation Today

All memory consolidation runs on the **RTX 3090** via `_call_consolidation_model()` → POST to `http://127.0.0.1:8091` (Qwen3.6-27B upstream). Same GPU handles main chat, so consolidation competes for VRAM and compute.

### Arc A380 — Code Exists, Server Not Running

| Component | Status |
|-----------|--------|
| `summarizer/` module (config.py, server.py, prompts.py) | ✅ Written |
| `config-subsystem.json` summarizer section | ✅ Written |
| `ZayaSummarizer` class (HTTP client to :8095) | ✅ Implemented |
| Model: `ZAYA1-8B-Q4_K_M.gguf` (5.2 GB) | ✅ Exists |
| SYCL llama-server binary | ✅ Built, tested |
| **llama-server process on Arc (:8095)** | ❌ **Not running** |
| **Consolidation routed to Arc** | ❌ **Still points to :8091** |
| Health check / auto-start | ❌ Not implemented |

---

## Consolidation Audit Findings (from super_council.py)

### CRITICAL: Model mismatch

`_call_consolidation_model()` sends `"model": "default"` to upstream. Comments say "Granite-8b" but the default alias is `qwen-160k-UD-fast` (Qwen3.6-27B-UD). Consolidation prompt is optimized for Granite ("strict instruction following, no reasoning traces") but runs against a reasoning model.

### HIGH: No fallback on failure

When upstream crashes, `_call_consolidation_model()` returns `None` → early return from `_do_startup_consolidation()`. This skips `_activate_latest_consolidation()` and `_inject_tier1_startup_context()`. No Tier 1 injection on failure.

### HIGH: 150K char input to reasoning model = wasted GPU

Consolidation feeds ~150K chars (~37K tokens) to Qwen3.6-27B. Reasoning traces consume output budget. For Granite this is efficient (no reasoning, strict YAML). For Qwen it's GPU-wasteful.

### HIGH: Race condition — HTTP server starts before consolidation

`consolidation_thread.start()` → `httpd.serve_forever()`. First user requests arrive before `_tier1_knowledge_card` is populated. First N requests get zero Tier 1 injection.

### MEDIUM: Probation + activation only on success

`_activate_latest_consolidation()` and `_inject_tier1_startup_context()` only run if `_do_startup_consolidation()` completes. On timeout, system relies on stale `is_active=1` entries from previous startup.

### MEDIUM: No slot save/clear after consolidation

Consolidation bypasses `handle_chat_completion` — calls upstream HTTP API directly via `urllib`. Slot state after consolidation is unknown and potentially dirty for next user request.

### LOW: Hardcoded 120s timeout, no retry, no configurability

---

## Architecture Proposal

### Target: ZAYA1-8B on Arc A380 (port 8095)

```
┌───────────────────────────────────────────────────────────────────┐
│                     Memory Consolidation Flow                      │
│                                                                    │
│  super-council (:8090)                                             │
│    ↓  _call_consolidation_model()                                  │
│    ↓  POST → http://127.0.0.1:8095/v1/chat/completions            │
│                                                                    │
│  Arc A380 (:8095)                                                  │
│    llama-server (SYCL build)                                       │
│    ZAYA1-8B-Q4_K_M (5.2 GB / 6 GB VRAM)                           │
│    Roles: consolidation, summarizer, vice-chair, memory-enrich     │
│                                                                    │
│  RTX 3090 (:8091)                                                  │
│    Qwen3.6-27B-UD (17 GB / 24 GB VRAM)                            │
│    Roles: main chat ONLY (consolidation removed)                   │
└───────────────────────────────────────────────────────────────────┘
```

### VRAM Budget (Arc A380, 6 GB)

| Component | Estimated |
|-----------|-----------|
| ZAYA1-8B Q4_K_M weights | ~4.2 GB |
| KV cache (32K ctx, 80 layers) | ~150 MB |
| Mamba recurrent cache | ~120 MB |
| Compute buffers | ~80 MB |
| Driver overhead | ~200 MB |
| **Total** | **~4.7 GB** (22% headroom) |

### VRAM Savings (RTX 3090, 24 GB)

| | Before | After |
|--|--------|-------|
| Qwen3.6-27B-UD | ~17 GB | ~17 GB |
| Consolidation KV cache | ~2-3 GB | **0** |
| **Free headroom** | ~4 GB | **~7 GB** |

### Fallback Model Options (if ZAYA1-8B OOMs)

| Model | File Size | Est. VRAM | Notes |
|-------|-----------|-----------|-------|
| ZAYA1-8B Q3_K_M | ~4.0 GB | ~3.5 GB | Safer fit, slight quality loss |
| Qwen3.5-4B Q5_K_M | 3.0 GB | ~2.5 GB | Very safe, less capable |
| Bonsai-1.7B Q4_K_M | ~1.0 GB | ~1.2 GB | Trivial fit, too small for consolidation |

---

## Implementation Steps

### Step 1: Start llama-server on Arc A380 ✅

Running on port 18095 (Granite-4.1-3B), 18096 (Ministral-3-3B), 18097 (Qwen3.5-4B).
SYCL build verified working. Health check passes.

### Step 2: Build arc_summarizer module ✅

Module created with config, client, prompts, pipeline submodules.
Wired into super_council.py via `_init_arc_summarizer()` in `serve_forever()`.

### Step 3: Route consolidation to Arc ✅

Config in `config-subsystem.json`:
```json
"consolidation": {
    "model": "granite-4.1-3b",
    "server_url": "http://127.0.0.1:18095",
    "timeout_seconds": 120,
    "max_retries": 3,
    "fallback_to_main": true
}
```

### Step 4: systemd service + journalctl ✅

**Service:** `~/.config/systemd/user/arc-summarizer.service`
**Start script:** `arc_summarizer/start.sh`
**Journal retention:** 7 days (`~/.config/systemd/journald.conf.d/arc-summarizer.conf`)

```bash
# Manage service
systemctl --user start arc-summarizer     # start
systemctl --user status arc-summarizer    # check
systemctl --user restart arc-summarizer   # restart
systemctl --user enable arc-summarizer    # enabled on login

# Logs (7-day retention)
journalctl --user -u arc-summarizer.service -f           # follow
journalctl --user -u arc-summarizer.service -n 100       # last 100
journalctl --user -u arc-summarizer.service --since '1h' # since 1 hour
```

**Note:** Port 18095 must be free. Kill manual llama-server instances before starting systemd service.

### Step 5: Fix consolidation bugs (while routing)

TODO: Add fallback on model failure, save slot before consolidation, update stale comments.

```bash
/home/chief/llama.cpp/build-sycl/bin/llama-server \
  -m /home/chief/models/zaya1/ZAYA1-8B-Q4_K_M.gguf \
  --alias zaya1-8b \
  --ctx-size 32768 \
  -ngl 99 \
  --host 127.0.0.1 \
  --port 8095 \
  --mamba-cache-dtype float32 \
  --reasoning on \
  --reasoning-format qwen3 \
  --temp 0.3 \
  --top-p 0.9 \
  --top-k 40 \
  --repeat-penalty 1.1 \
  --threads 8 \
  --threads-batch 8 \
  -ub 16
```

**Key flags:** `-ngl 99` (all layers to GPU), `--mamba-cache-dtype float32` (ZAYA1 MoE SSM), `--reasoning on` (structured output).

**Verify:** `curl http://127.0.0.1:8095/v1/models`

### Step 2: Route consolidation to Arc

**Approach A — Configurable endpoint (minimal change):**

Add to `config-subsystem.json`:
```json
"consolidation": {
    "server_url": "http://127.0.0.1:8095",
    "model": "zaya1-8b",
    "timeout_seconds": 120,
    "max_retries": 3,
    "fallback_to_main": true
}
```

Update `_call_consolidation_model()`:
```python
url = f"{self._consolidation_config['server_url']}/v1/chat/completions"
payload = {"model": self._consolidation_config.get("model", "default"), ...}
```

**Approach B — ZayaSummarizer integration (cleaner, bigger change):**
```python
from super_council.summarizer import ZayaSummarizer, SummarizerConfig
config = SummarizerConfig.load()
self._summarizer = ZayaSummarizer(config)
# In _do_startup_consolidation():
result = self._summarizer.summarize(prompt, max_tokens=8192)
```

### Step 3: Health check + auto-start

**systemd service (recommended):**
```ini
# /etc/systemd/system/arc-summarizer.service
[Unit]
Description=ZAYA1-8B Summarizer on Intel Arc A380
After=network.target

[Service]
Type=simple
User=chief
Environment=ONEAPI_DEVICE_SELECTOR=level_zero:gpu.2
ExecStart=/home/chief/llama.cpp/build-sycl/bin/llama-server \
  -m /home/chief/models/zaya1/ZAYA1-8B-Q4_K_M.gguf \
  --alias zaya1-8b --ctx-size 32768 -ngl 99 \
  --host 127.0.0.1 --port 8095 \
  --mamba-cache-dtype float32 --reasoning on --reasoning-format qwen3 \
  --temp 0.3 --top-p 0.9 --top-k 40 --repeat-penalty 1.1 \
  --threads 8 --threads-batch 8 -ub 16
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Step 4: Fix consolidation bugs (while routing)

1. **Add fallback on model failure:** If `_call_consolidation_model()` returns None, activate latest cache entry + inject Tier 1 from cache (graceful degradation).
2. **Save slot before consolidation, reset after:** Prevent dirty slot state for next user request.
3. **Add retry with backoff:** 3 attempts, 5s/10s/15s delays.
4. **Update stale "Granite-8b" comments** to reflect actual model.
5. **Make timeout configurable** via `memory-config.json`.

### Step 5: Voice pipeline LLM (optional)

Currently points to `:8091` (NVIDIA). Can redirect to Arc if VRAM-constrained, but Qwen3.6-27B is more capable for open-ended voice conversation.

---

## Wear-In Sequence

1. **Test ZAYA1-8B on Arc** — Start SYCL server manually, verify no OOM, benchmark consolidation-sized prompt
2. **Verify output quality** — Run test consolidation through ZAYA1-8B, compare YAML quality vs Qwen3.6-27B
3. **Update config** — Add `consolidation` section to `config-subsystem.json`
4. **Update `_call_consolidation_model`** — Route to Arc with NVIDIA fallback
5. **Add health check** — Super-council checks :8095 before consolidation
6. **Start systemd service** — Persistent Arc server
7. **Monitor** — `intel_gpu_top` for VRAM, consolidation success rate, output quality

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| ZAYA1-8B OOMs on 6 GB Arc | HIGH | Test with `--ctx-size 16384` first. Fall back to Q3_K_M. |
| SYCL performance worse than expected | MEDIUM | Benchmark before committing. Bonsai-1.7B: 19.77 t/s gen. |
| Arc server crashes, consolidation breaks | MEDIUM | Fallback to :8091. Health check before each call. |
| Display VRAM usage reduces available memory | LOW | Check `intel_gpu_top`. Desktop Arc A380 typically reserves 1-2 GB. |
| Level Zero driver instability | LOW | Package `intel-level-zero-gpu 1.3.29735.27` installed. Test extended runtime. |

---

## Caveats

- **ZAYA1-8B not yet tested on Arc** — SYCL build works (Bonsai benchmark passed) but ZAYA1 is MoE with Mamba SSM layers. 4.7 GB estimate needs verification.
- **`--mamba-cache-dtype float32`** — May be no-op if ZAYA1 doesn't actually use Mamba/SSM. Verify model architecture.
- **Arc A380's 6 GB is shared with display** — If GPU drives a monitor, actual available VRAM could be 4–5 GB.
- **ZAYA1 reasoning mode adds overhead** — For pure YAML extraction, `--reasoning off` might be faster.
- **Port 8095 is hardcoded** in `summarizer/config.py` — Update both config and systemd service if changed.
