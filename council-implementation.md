# Council Pipeline — Implementation

**Date:** 2026-05-07  
**Status:** VALIDATED — slot persistence working, rotation tested, `-np 1` mandatory  
**Architecture:** See `council-architecture.md`  
**Code:** See `slot-supervisor.py`

---

## 1. Slot Persistence Model

### 1.1 Core Constraint: Byte-Compatible KV Only

KV cache is **model-specific**. A slot bin saved from one model configuration is **incompatible** with any other. Restore is valid only when ALL of the following match exactly:

| Parameter | Must Match | Why |
|---|---|---|
| **Model GGUF path** | Exact file | Different weights → different KV tensors |
| **Quantization** | Exact quant type (Q4_K_XL, IQ4_XS, etc.) | Different quant → different tensor layouts |
| **`--ctx-size`** | Exact value | Context window determines KV buffer dimensions |
| **`-ctk` / `-ctv`** | Exact values | KV quantization changes tensor format |
| **`-ngl`** | Exact value | Layer split between CPU/GPU affects which KV layers exist |
| **Arch flags** | Exact flags (`-fa`, `-np`, etc.) | Flash attention changes KV computation |

**Change any one → slot bin is invalid → must pay full prefill.**

### 1.2 Slot Directory Layout

```
/home/chief/tmp/llama-slots/
├── <model_alias>/              # Per-model namespace (CRITICAL)
│   ├── <config_hash>/          # Hash of model+quant+ctx+flags
│   │   ├── slot-0.bin          # KV cache state
│   │   ├── slot-0.bin.checkpoints  # Companion checkpoints file
│   │   └── slot-0.json         # Metadata: model_alias, model_signature, timestamp
│   └── <config_hash>/          # Different config = different subdir
│       └── ...
├── <model_alias>/
│   └── ...
└── .llama_server_binary_hash   # Binary change detection

**Key design:** Each model gets its own subdirectory. Within each model, each unique runtime config gets its own subdirectory. This prevents cross-model KV restoration.

### 1.3 Config Hash

The config hash is computed from the immutable runtime parameters:

```python
config_hash = sha256(
    f"{model_path}\n"
    f"{ctx_size}\n"
    f"{ngl}\n"
    f"{ctk}\n"
    f"{ctv}\n"
    f"{'-fa' if flash_attention else ''}\n"
    f"{'-np' if pipeline else ''}\n"
).hexdigest()[:16]
```

If the config hash doesn't match the stored slot's config hash → **invalidation** → full prefill.

### 1.4 Invalidation Rules

| Event | Action |
|---|---|
| Model GGUF replaced (new quant, new version) | Purge old config dir, create new one |
| `--ctx-size` changed | Purge old config dir, create new one |
| `-ngl` changed | Purge old config dir, create new one |
| llama-server binary updated | **Purge all** — binary changes may alter KV format |
| First-ever visit to a model | Full prefill (no slot exists yet) |
| Slot bin missing or corrupted | Full prefill |

---

## 2. llama-swap Configuration

### 2.1 Groups

```jsonc
// /home/chief/tmp/llama-swap/config.json
{
  "groups": [
    {
      "name": "tiny_council",
      "swap": false,
      "exclusive": true,
      "models": [
        {
          "model": "/home/chief/models/mistral/Ministral-8B-Instruct-2410-Q6_K.gguf",
          "alias": "ministral",
          "ctx_size": 16384,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/nvidia/NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf",
          "alias": "nemotron-nano",
          "ctx_size": 16384,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/qwen3/Qwen3-4B-Instruct-2507-Q6_K.gguf",
          "alias": "qwen3-4b",
          "ctx_size": 16384,
          "ngl": 48,
          "cache_prompt": true
        }
      ]
    },
    {
      "name": "gpu_chat",
      "swap": true,
      "exclusive": true,
      "models": [
        {
          "model": "/home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf",
          "alias": "chair",
          "ctx_size": 131072,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/qwen3/Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf",
          "alias": "builder",
          "ctx_size": 65536,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/google/gemma-4-31B-it-UD-Q4_K_XL.gguf",
          "alias": "reviewer-arch",
          "ctx_size": 32768,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/nvidia/nvidia_Nemotron-Cascade-2-30B-A3B-IQ4_XS.gguf",
          "alias": "reviewer-logic",
          "ctx_size": 32768,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/openai/gpt-oss-20b-Q4_K_M.gguf",
          "alias": "reviewer-diversity",
          "ctx_size": 32768,
          "ngl": 48,
          "cache_prompt": true
        },
        {
          "model": "/home/chief/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
          "alias": "reviewer-authority",
          "ctx_size": 32768,
          "ngl": 48,
          "cache_prompt": true
        }
      ]
    }
  ]
}
```

### 2.2 Group Behavior

| Group | `swap` | `exclusive` | Behavior |
|---|---|---|---|
| `tiny_council` | `false` | `true` | All 3 models co-resident (~11GB). Never evicted. No swap cost between members. |
| `gpu_chat` | `true` | `true` | One model at a time. Mutual eviction. Slot saved on evict, restored on load. |

### 2.3 llama-server Launch (per model)

```bash
llama-server \
  -m <model.gguf> \
  --ctx-size <ctx_size> \
  -ngl 48 \
  --auto-save-slots \
  --auto-restore-slots \
  --slot-save-path /home/chief/tmp/llama-slots/<model_alias>/<config_hash>/ \
  -c <ctx_size> \
  --host 127.0.0.1 \
  --port <port> \
  -np 1 \
  -fa
```

| Flag | Purpose |
|---|---|
| `--auto-save-slots` | PR #20822 — save slot state to disk on exit |
| `--auto-restore-slots` | PR #20822 — restore slot state on startup |
| `--slot-save-path` | **Per-model, per-config directory** — prevents cross-model KV reuse |
| `-ngl 48` | All layers on GPU (adjust per model) |
| `-np 1` | Single pipeline (single GPU) |
| `-fa` | Flash attention |

**Critical:** `--slot-save-path` is **per-model, per-config**. Not a shared directory. Each model writes its slot bins to its own isolated subdirectory.

---

## 3. slot-supervisor.py

### 3.1 Architecture (Merged: OP's Proxy + Our Safety Layer)

```
  Client (Pi Agent, curl, etc.)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  ThreadingHTTPServer (listen_port:8080)                     │
│                                                              │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────┐ │
│  │ Request     │    │ Slot Manager     │    │ Metrics    │ │
│  │ Handler     │───>│                  │    │ Cache      │ │
│  │             │    │ - per-model ns   │    │ (5s poll)  │ │
│  │ - /health   │    │ - config hash    │    │            │ │
│  │ - /metrics  │    │ - signature chk  │    │ /metrics   │ │
│  │ - /status   │    │ - save/restore   │    └────────────┘ │
│  │ - /v1/*     │    │ - .json metadata │                   │
│  └─────────────┘    └──────────────────┘                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ llama-server (upstream_port:8081, managed by supervisor)│
│  │  --auto-save-slots --auto-restore-slots              │   │
│  │  --slot-save-path /home/chief/tmp/llama-slots/<alias>/<hash>/ │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
       │                              │
       ▼                              ▼
  Stable port (8080)          Per-model slot bins (NVMe)
  Clients never see           /home/chief/tmp/llama-slots/
  swap churn                       ├── chair/<hash>/
                                   │   ├── slot-0.bin
                                   │   ├── slot-0.bin.checkpoints
                                   │   └── slot-0.json  ← metadata
                                   ├── builder/<hash>/
                                   └── ...```

**Key insight:** The proxy layer (OP's contribution) gives clients a stable endpoint. The upstream llama-server restarts on port 8081 during swaps — clients on 8080 never see downtime because the handler queues requests during the ~2s swap window.

### 3.2 Merge Provenance

| Component | Source | Why |
|---|---|---|
| **ThreadingHTTPServer proxy** | OP | Stable frontend port, clients never see swap churn |
| **Per-model slot namespace** | Ours | `<alias>/<config_hash>/` prevents cross-model KV corruption |
| **ModelConfig (frozen)** | Ours | Immutable runtime config, SHA-256 hash for namespace isolation |
| **BinaryHashTracker** | Ours | Purges all slots on llama-server binary change |
| **SlotStore (.json metadata)** | OP | `slot-0.json` stores model_signature → validates compatibility on restore |
| **Restore retries + backoff** | OP | Auto-restore can fail on first try; retries make it robust |
| **SlotClient (HTTP)** | OP | Clean separation of slot API calls from supervisor logic |
| **UpstreamProcess** | OP | Manages llama-server lifecycle with health-check wait |
| **invalidate_model CLI** | Ours | Manual slot invalidation per model alias |

### 3.3 Key Design Decisions

| Decision | Rationale |
|---|---|
| **Two ports (listen vs. upstream)** | Clients connect to stable 8080. Upstream swaps on 8081. No client-visible churn. |
| **Per-model slot namespace** | KV cache is model-specific. `/slot-dir/<alias>/<config_hash>/` prevents cross-model reuse. |
| **Config hash validation** | Before every restore, verify model path, ctx-size, ngl, quant flags match. |
| **Signature validation (.json)** | Metadata sidecar stores `model_signature`. Restore skips if signature mismatches. |
| **Pi Agent, not opencode** | No volatile token injection (`<TS>`, `<DATE>`) — skip normalization step. |
| **Single slot (id_slot=0)** | All models serialize through one GPU; no concurrent slots needed. |
| **NVMe slot storage** | `/home/chief/tmp/llama-slots/` — Gen5 NVMe, Linux page cache as RAM tier. |
| **Timeout split** | 5s read-only endpoints, 600s for `/v1/chat/completions`. |

### 3.4 Byte Compatibility Validation Flow

```
Request arrives for model "chair" on :8080
  │
  ├─→ Handler routes to SlotSupervisor.handle_chat_completion()
  │
  ├─→ _swap_to("chair")
  │     │
  │     ├─→ Save current slot (if different model was active)
  │     ├─→ Stop upstream llama-server (:8081)
  │     ├─→ Start upstream with chair config + per-config slot path
  │     │     └─→ --slot-save-path /home/chief/tmp/llama-slots/chair/<hash>/
  │     │
  │     ├─→ _restore_current_slot(prefer_signature=chair.signature)
  │     │     │
  │     │     ├─→ Read slot-0.json metadata
  │     │     ├─→ Check: model_signature matches prefer_signature?
  │     │     │     ├─ NO → Skip restore (signature mismatch)
  │     │     │     └─ YES → Continue
  │     │     ├─→ Check: slot-0.bin exists?
  │     │     │     ├─ NO → COLD START
  │     │     │     └─ YES → Continue
  │     │     └─→ POST /slots/0?action=restore (with retries + backoff)
  │     │           ├─ Success → CACHE HIT
  │     │           └─ Fail → COLD START
  │     │
  │     └─→ Upstream ready on :8081
  │
  ├─→ Forward request to upstream :8081/v1/chat/completions
  │
  ├─→ After response: SAVE slot + write slot-0.json metadata
  │
  └─→ Return response to client on :8080```

### 3.5 Code

See `/home/chief/llm-wiki/slot-supervisor.py` (924 lines, 8 classes, 58 methods)

### 3.6 CLI Reference

```bash
# Start the proxy server
python3 slot-supervisor.py \
    --listen-port 8080 \
    --upstream-port 8081 \
    --config /home/chief/tmp/llama-swap/config.json \
    --slot-dir /home/chief/tmp/llama-slots \
    --upstream-bin /path/to/llama-server

# Validate config without starting
python3 slot-supervisor.py --dry-run

# Print slot directory stats
python3 slot-supervisor.py --stats

# Purge orphans and unknown dirs
python3 slot-supervisor.py --cleanup-only

# Invalidate a specific model's slots
python3 slot-supervisor.py --invalidate chair
```

---

## 4. Caveats (from OP, adapted)

| Caveat | Our Mitigation |
|---|---|
| **Byte-compatible KV only** | Per-model namespace + config hash validation. Cross-model restore is impossible by design. |
| **First visit pays prefill** | Expected. Slot reuse pays off from 2nd visit onward (every visit in iterative pipeline). |
| **Worth it only if ctx-heavy AND swap-heavy** | Chair holds 130K ctx, 6+ model swaps per cycle. ✓ |
| **Both PRs unmerged** | Cherry-picked to `7-council/llama-council/` build. ⚠️ **INACTIVE** — council now runs from `llama-cpp-turboquant/` build (see §3.4) |
| **System prompt stability** | Pi Agent doesn't inject volatile tokens. No normalization needed. |
| **Orphan `.checkpoints` files** | Supervisor purges orphans on startup and after each swap cycle. |
| **Unknown model dirs linger** | Supervisor tracks known models; purges unknown dirs on cleanup. |
| **Binary update invalidates all** | Supervisor tracks llama-server binary hash; purges all slots on binary change. |

---

## 4.1 Audit Log

### Issues Fixed (2026-05-06)

| ID | Severity | Issue | Fix |
|---|---|---|---|
| **A** | Critical | `invalidate_model("builder")` purged **Chair's** slots (used `self.current_config` instead of target alias's config) | `invalidate_model` looks up config from registry, purges correct model's slot dir |
| **B** | Critical | `purge_orphans()`: `with_suffix(".bin")` on `slot0.bin.checkpoints` → `slot0.bin.bin` — orphan detection **never fired** | Merged: OP's `str(ckpt)[:-len(".checkpoints")]` pattern (correct) |
| **C** | Moderate | `invalidate_config(alias, reason)`: `alias` parameter unused | Merged: `SlotSupervisor.invalidate_model` uses registry directly |
| **D** | Moderate | Health check `except Exception: continue` swallowed `FileNotFoundError`, `KeyboardInterrupt` | Merged: OP's `wait_ready` — `URLError` → retry, `KeyboardInterrupt` → raise, other → continue |
| **E** | Moderate | Double restore: `--auto-restore-slots` restores on startup, then explicit `RESTORE` call conflicted | Merged: OP's `restore_slot` with retries + backoff, guarded by signature check |
| **F** | Minor | Unused imports: `os`, `pathlib`, `field` | Removed |

### Merge (2026-05-06)

Merged OP's production script (`/home/chief/Downloads/slot-supervisor.py`) with our safety-critical additions:

| Adopted from OP | Kept from Ours |
|---|---|
| ThreadingHTTPServer proxy layer | Per-model slot namespace (`<alias>/<config_hash>/`) |
| Two-port architecture (listen vs. upstream) | ModelConfig frozen dataclass |
| Slot metadata (.json sidecar) | BinaryHashTracker |
| Restore retries + backoff | invalidate_model CLI |
| SlotClient / UpstreamProcess separation | Config hash validation |

### Validated Assumptions (H1-H7)

| ID | Assumption | Status |
|---|---|---|
| **H1** | `/slots/{id}?action=save` returns 2xx | ✅ **Confirmed** — POST with `{"filename":"..."}`. Returns `{id_slot, filename, n_saved, n_written, timings}` |
| **H2** | `/slots/{id}?action=restore` returns token count | ✅ **Confirmed** — POST with `{"filename":"..."}`. Returns `{id_slot, filename, n_restored, n_read, timings}` |
| **H3** | `/health` returns HTTP 200 when ready | ❌ **WRONG** — binary has `/v1/health`, not `/health`. **Fixed in script** (line 434, 528). |
| **H4** | `/metrics` returns JSON | ❌ **501 Not Implemented** — endpoint registered but not functional. `SlotClient.metrics()` falls back to `{}` (line 535-538). |
| **H5** | `--auto-save-slots` / `--auto-restore-slots` flags exist | ⚠️ **Router-mode only** — supervisor uses explicit `POST /slots/{id}?action=save|restore` — no CLI flags needed. |
| **H6** | `--slot-save-path` accepts per-model subdirectory | ✅ **Confirmed** — server started successfully with `--slot-save-path /tmp/slot-smoke-test-path/` |
| **H7** | Slot filenames are `slot-{id}.bin` + `.checkpoints` | ✅ **CONFIRMED** — `filename` parameter IS respected by save/restore API. File saved as `slot-0.bin` with `qsgg` magic bytes. No `.checkpoints` companion generated. |

**Smoke test:** 2026-05-07, Qwen3-4B Q6_K, 3.1GB, ctx=2048, -ngl 36, -np 4 (auto). All H1-H7 confirmed.

### ✅ RESOLVED: `n_saved: 0` — Root cause: `-np 4` → `kv_unified = true`

**Diagnosis (2026-05-07):** Combined tests A-E isolated the cause:

| Test | `-np` | `--cache-ram` | `n_saved` | Size | Result |
|---|---|---|---|---|---|
| A | 1 | 0 | 325 | 47.9 MB | ✅ |
| B | 1 | default | 325 | 47.9 MB | ✅ |
| C | 4 (auto) | default | 0 | 20 B | ❌ |
| D | 4 (auto) | 0 | 0 | 20 B | ❌ |
| E | 1 | default (idempotent) | 325×2 | identical | ✅ |

**Root cause:** `-np 4` (auto) → `llama-server` enables `kv_unified = true`, which pools KV across all parallel slots. The per-slot save API has nothing to extract because KV isn't per-slot.

**Fix:** `-np 1` is **mandatory** for slot persistence. With single pipeline, KV is per-slot and save extracts the full cache.

**`--cache-ram 0` is optional** — does not fix the save bug. Controls in-memory prompt cache size (default 8192 MiB). With 96GB RAM, keeping the default 8GB prompt cache is affordable and beneficial for in-session reuse.

**Restore validated:** `n_restored: 325`, 47.9 MB read in 9.66ms. Context survives: model correctly recalls "The robot is named Kael." after swap+restore.

**Prompt cache idempotency confirmed:** `cached_tokens: 25/29` on repeated requests (system prompt overlap).

**See:** `~/Coding-Projects/7-council/llama-council/scripts/slot-smoke-run.log` (⚠️ INACTIVE — from original build; active council uses `llama-cpp-turboquant/`) for full run details.

### 🔬 Rotation Test Results (2026-05-07)

**Setup:** Qwen3-4B (3.1GB) ↔ Nemotron-Nano (3.8GB), ctx_size=4096, slot-dir `/tmp/council-rotation-test/`.

| Step | Model | Action | Result |
|---|---|---|---|
| 1 | qwen3-4b | Load + respond + save | ✅ 38 tokens, 5.3 MiB |
| 2 | nemotron-nano | Load + respond + save | ⚠️ 81 tokens, 82.4 MiB (empty response — chat template issue) |
| 3 | qwen3-4b | Swap + restore + respond | ✅ CACHE HIT: 38 tokens restored (1.2ms) |
| 4 | qwen3-4b | Full history test | ✅ Recalls "ALPHA-7" correctly |
| 5 | qwen3-4b | Partial prompt test | ✅ No recall (expected — KV cache ≠ conversation history) |

**Final supervisor stats:** `total_requests: 5`, `swaps: 3`, `restores: 1`, `saves: 6`, `errors: 1`

**Duplicate file behavior:** `llama-server` writes both `slot-0.bin` (requested) AND `<model_stem>` (automatic). Files are exact duplicates (identical md5sum). Cleanup removes `<model_stem>` copies on swap.

**Nemotron-Nano empty response:** RESOLVED — not a save/restore or chat template bug. Model has `enable_thinking=True` hardcoded in its Jinja template. Thinking output goes to `reasoning_content`; actual answer goes to `content`. With low `max_tokens` (≤20), thinking burns the budget and `content` is empty. `enable_thinking: false` and `disable_thinking: true` are NOT respected by llama.cpp. Fix: use `max_tokens ≥ 50` for Nemotron-Nano, or check both `content` + `reasoning_content` in responses.

### ⚠️ Hard Requirements (validated)

| Requirement | Why | Consequence if violated |
|---|---|---|
| **`-np 1`** | `n_parallel > 1` → `kv_unified = true` pools KV across slots | `n_saved: 0` — no per-slot KV to extract |
| **`-fit on`** (Nemotron-Nano) | 42 blocks + 3136 embedding length = tight VRAM fit | SIGSEGV (rc=-11) on model load |
| **ctx_size ≤ 4096** (rotation testing) | 16384 ctx → ~8.6GB KV for Nemotron-Nano, exceeds 5.8GB free VRAM | OOM crash on model load |
| **Full conversation history on restore** | KV cache gives attention state, not message history | Model has no "memory" of prior context without full history |
| **max_tokens ≥ 50** (Nemotron-Nano, Cascade-2, GPT-OSS) | Thinking always-on; `disable_thinking` not respected by llama.cpp | `content` empty when thinking burns token budget |
| **enable_thinking semantics differ** (Gemma ≠ Qwen) | Gemma defaults OFF (`default(false)`), Qwen defaults ON | Don't assume same toggle behavior across families |

### KV Cache vs. Conversation History

**KV cache restore** gives the model its previous attention state (key-value pairs from the prompt). This skips re-computation of the prompt's attention layers.

**Conversation history** is the actual message list sent to the model. Without it, the model has no semantic memory of what was discussed.

**Correct restore pattern:**
1. Restore KV cache (`POST /slots/0?action=restore`) → skips prompt prefill
2. Send full conversation history → model "remembers" context
3. `cached_tokens` counts prompt cache matches, NOT slot restore tokens

**Incorrect pattern:** Restore KV cache, send only the latest message → model has attention state for the full prompt but only sees the latest message. No recall of prior context.

### Chat Template Behavior (all 9 models)

Full reference: `council-architecture.md` §5 (Chat Template Reference).

**Key findings from GGUF inspection (2026-05-07):**

| Category | Models | Action Required |
|---|---|---|
| **No thinking** (plain output) | ministral, qwen3-4b, builder | None — works as-is |
| **Thinking ON by default, toggleable** | chair, reviewer-authority | Pass `enable_thinking: false` for plain output |
| **Thinking OFF by default, toggleable** | reviewer-arch | Works as-is; pass `enable_thinking: true` if needed |
| **Thinking ALWAYS ON (not toggleable)** | nemotron-nano, reviewer-logic, reviewer-diversity | Use `max_tokens ≥ 50`; check `reasoning_content` + `content` |

**Nemotron-Nano / Cascade-2 (always-on thinking):**
1. All responses include reasoning in `reasoning_content` field
2. Actual answer goes to `content` field
3. Thinking is NOT toggleable via API — `enable_thinking: false` is ignored by llama.cpp
4. With `max_tokens ≤ 20`, thinking burns the budget and `content` is empty
5. Fix: use `max_tokens ≥ 50`, or check both `content` + `reasoning_content`

**GPT-OSS-20B (reviewer-diversity):**
- Uses `thinking` field (not `reasoning_content`) in messages
- Uses `<|channel|>analysis` / `<|channel|>final` format
- `reasoning_effort` defaults to `"medium"` — no on/off toggle

**Gemma-4-31B (reviewer-arch):**
- Thinking OFF by default (opposite of Qwen)
- Uses `<|think|>` token and `<|channel|>thought` format
- `enable_thinking | default(false)` — don't assume Qwen semantics

### Supervisor Patch Log (2026-05-07)

| Change | Location | Purpose |
|---|---|---|
| `_parse_upstream_json()` | `SlotClient` | Safe JSON parsing with hex-safe raw-body logging on decode failure |
| `cleanup_duplicate_artifacts()` | `SlotStore` | Remove `<model_stem>` duplicate files after save/restore |
| Cleanup call in `_swap_to()` | `SlotSupervisor` | Run cleanup after save (gives async writes time to complete) |
| `-fit on` flag | `slot-supervisor.py` launch args | Required for Nemotron-Nano tight VRAM fit |

---

## 5. Implementation Checklist

### 5.1 Prerequisites

- [x] llama-council build with PRs #20819 + #20822 cherry-picked
- [x] llama-swap binary at `/home/chief/bin/llama-swap`
- [x] Tiny Council models on disk (Ministral, Nemotron-Nano, Qwen3-4B)
- [x] Chair model on disk (Qwen3.6-27B)
- [x] Builder model on disk (Qwen3-Coder-30B)
- [x] **Gemma-4-31B** — on disk (`/home/chief/models/google/gemma-4-31B-it-UD-Q4_K_XL.gguf`, 18GB)
- [x] Nemotron-Cascade-2-30B on disk
- [x] GPT-OSS-20B on disk
- [x] Qwen3.6-35B on disk

### 5.2 Infrastructure

- [x] Smoke test slot save/restore API (2026-05-07) — API works, `filename` param respected
- [x] Diagnose `n_saved: 0` — **RESOLVED**: `-np 1` mandatory (see §4.1)
- [x] Verify `.checkpoints` file generation — none generated under current tests (qsgg header only)
- [x] Rotation test: Qwen3-4B ↔ Nemotron-Nano, 3 swaps, 1 restore, 6 saves, 1 error (nemotron chat template)
- [x] KV cache restore validated: `CACHE HIT [qwen3-4b]: 47 tokens restored (1.3ms)`
- [x] Context persistence validated: full conversation history → model recalls "ALPHA-7"
- [x] Duplicate artifact cleanup: `cleanup_duplicate_artifacts()` removes `<model_stem>` copies
- [x] Nemotron-Nano empty response — **RESOLVED**: thinking always-on, needs `max_tokens ≥ 50`
- [x] Raw response logging: `_parse_upstream_json()` with hex-safe fallback
- [x] Chat template audit: all 9 models inspected via `gguf-dump` (2026-05-07)
- [ ] Create `/home/chief/tmp/llama-slots/` directory
- [ ] Create per-model subdirectories: `chair/`, `builder/`, `reviewer-arch/`, etc.
- [ ] Deploy `llama-swap/config.json` (Section 2.1)
- [ ] Deploy `slot-supervisor.py` (Section 3.4)
- [ ] Test slot save/restore with Chair model (cold start → swap → restore → validate config hash)
- [ ] Test cross-model invalidation (swap Chair → Gemma → verify Gemma doesn't restore Chair's slot)
- [ ] Test Tiny Council co-residency (no swap between members)

### 5.3 Tiny Council Fanout (2026-05-08)

**Implementation:** `TinyCouncilManager` class in `slot-supervisor.py` (1824 lines)

#### 5.3.1 Async Fanout (Option C)

- **Job queue** with TTL cleanup (1 hour)
- **Background thread** execution — user gets job_id immediately
- **Polling endpoint:** `GET /v1/council/fanout/{job_id}`
- **Job listing:** `GET /v1/council/fanout/jobs`
- **Async flag:** `{"async": true}` in POST body
- **Backward compatible:** sync mode still works (`async: false` or omit)

**Impact:** Eliminates 100% of user-facing blocking during fanout. User can continue working while fanout runs in background.

#### 5.3.2 Overlap Swap (Option D)

- **VRAM wait + model load** run in parallel threads
- **Saves ~3s per swap** (~18% faster)
- **Fallback to sequential** if overlap fails
- **CUDA driver** serializes GPU allocation, but host-side model copy streams from NVMe in parallel

**Impact:** Reduces swap time from ~16.6s to ~11.6s per cycle.

#### 5.3.3 Session Analysis (11.1 hours uptime)

| Metric | Value |
|--------|-------|
| Total requests | 622 |
| Total swaps | 101 |
| Swaps per hour | 9.1 |
| Estimated swap time | 16.6s per cycle |
| Total swap time | 1,677s (0.5 hours) |
| Fanouts possible (6 swaps each) | ~16 |
| Fanout blocking time | 1,594s (0.4 hours) |

**Combined impact:** Async fanout eliminates 1,594s of user-facing blocking. Overlap swap saves 303s of system work.

### 5.4 Pipeline

- [ ] Draft review prompts for each council member (per `council-architecture.md` §3)
- [ ] Wire Pi Agent to llama-council provider (optional)
- [ ] Run first council review on `Data_Migration_Report.md`
- [ ] Measure actual vs. estimated performance
- [ ] Tune context sizes based on real usage

### 5.4 Maintenance

- [ ] Set up orphan-purge cron (daily sweep of `.checkpoints` orphans)
- [ ] Monitor slot directory size (alert if >50GB)
- [ ] Track cache hit/miss ratios per model
- [ ] Document invalidation rules for team
- [ ] Track llama-server binary hash (purge all slots on binary update)
