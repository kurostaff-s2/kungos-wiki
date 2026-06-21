# KV Cache Full Reprocessing Investigation — 83K+ Tokens on Swap Back

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `91eded` |
| Entity type | `handoff` |
| Short description | Investigate why swap-back to qwen-160k-UD-fast causes 83K+ token prompt reprocessing despite slot restore |
| Status | `draft` |
| Source references | `21-06-2026_super-go-manager-handoff_bc8cb5.md`, `19-06-2026_llama-swap-slot-persistence-investigation_99070a.md` |
| Generated | 21-06-2026 |
| Next action / owner | Agent: trace slot restore → first request flow; identify why KV cache isn't reused |

---

## Problem Statement

After swapping back to `qwen-160k-UD-fast`, the **first real request** causes **83K+ token prompt reprocessing** (~99 seconds at ~1057 t/s), despite the manager successfully restoring the slot file (`slot-0.bin`) which contains the full conversation context.

**Expected:** Slot restore loads KV cache → first request reuses cached prefix → only new tokens processed.

**Actual:** Slot restore reports success (e.g., `RESTORE: 221 tokens (8.5ms)`) → first request reprocesses full 83K+ tokens from scratch.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/super-go-manager/main.go` — Manager swap logic (SwapModel, SaveSlot, RestoreSlot, TriggerModelLoad)
- `/home/chief/Coding-Projects/7-council/super-go-manager/config.yaml` — Manager config (slot_dir, slot_models)
- `/home/chief/models/super-router/models.ini` — Router model config (slot-save-path, ctx-checkpoints, cache settings)

**Related codebases:**
- `/home/chief/main-llama/llama.cpp/` — llama-server source (slot save/restore implementation, prompt cache, ctx-checkpoints)

**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/21-06-2026_super-go-manager-handoff_bc8cb5.md` — Previous handoff (swap cycle fixes)
- `/home/chief/llm-wiki/00-prompt-handoff/19-06-2026_llama-swap-slot-persistence-investigation_99070a.md` — Slot persistence investigation

---

## Evidence

### Swap Cycle Logs (Working Parts)

```
=== SWAP START: qwen-160k-UD-fast -> qwen3.6-35b-a3b ===
SAVE qwen-160k-UD-fast: 221 tokens, 157.0 MiB (1466.5ms)   ← slot saved
STATE CHANGE: qwen-160k-UD-fast loaded -> unloaded
STATE CHANGE: qwen3.6-35b-a3b unloaded -> loading
STATE CHANGE: qwen3.6-35b-a3b loading -> loaded
RESTORE qwen3.6-35b-a3b: 217 tokens (8.5ms)                ← slot restored
=== SWAP DONE: qwen3.6-35b-a3b -> qwen3.6-35b-a3b (7.1s) ===
```

### Full Reprocessing Evidence

After swap back to `qwen-160k-UD-fast`, first request causes:

```
[33193] 0.03.192.742 I srv  get_availabl: updating prompt cache
[33193] 0.03.192.747 I srv          load:  - looking for better prompt, base f_keep = -1.000, sim = 0.000
[33193] 0.03.192.750 I srv        update:  - cache state: 0 prompts, 0.000 MiB (limits: 16192.000 MiB, 110592 tokens, 16978542592 est)
[33193] 0.03.193.441 I slot launch_slot_: id  0 | task 0 | processing task, is_child = 0
[33193] 0.06.581.592 I slot print_timing: id  0 | task 0 | prompt processing, n_tokens =   3584, progress = 0.04, t =   3.39 s / 1057.81 tokens per second
[33193] 0.07.065.607 I slot print_timing: id  0 | task 0 | prompt processing, n_tokens =   4096, progress = 0.04, t =   3.87 s
[33193] 0.07.554.565 I slot print_timing: id  0 | task 0 | prompt processing, n_tokens =   4608, progress = 0.05, t =   4.36 s
... continues to 83K+ tokens, ~99 seconds total
```

**Key indicators:**
- `f_keep = -1.000, sim = 0.000` — **No cache match found** (f_keep should be 0.99+ for cached prefix)
- `cache state: 0 prompts, 0.000 MiB` — **Prompt cache is empty**
- `prompt processing, n_tokens = 3584, 4096, 4608...` — Incremental progress through full context

### Contrast: Subsequent Requests (Working)

After the first request completes, subsequent requests DO use cache:

```
[41665] 1.30.164.897 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, sim_best = 0.987 (> 0.100 thold), f_keep = 0.999
[41665] 1.33.603.827 I slot print_timing: id  0 | task 490 | prompt eval time =    1530.29 ms /   819 tokens
[41665] 1.33.603.830 I slot print_timing: id  0 | task 490 |    graphs reused =        460
```

- `f_keep = 0.999` — 99.9% of context reused from cache
- `prompt eval = 1530ms / 819 tokens` — Only new tokens processed
- `graphs reused = 460` — KV cache hits confirmed

### Slot File Evidence

```
# Slot files on tmpfs (RAM):
-rw-rw-r-- 1.8G qwen-160k-UD-fast/slot-0.bin   ← 92K tokens saved
-rw-rw-r--  66M qwen3.6-35b-a3b/slot-0.bin     ← 229 tokens saved

# Metadata:
qwen-160k-UD-fast: slot_tokens = 92350
qwen3.6-35b-a3b:   slot_tokens = 229
```

### Router Init Evidence

Each child server spawn shows fresh slot initialization:

```
[54073] 0.02.976.955 I slot   load_model: id  0 | task -1 | new slot, n_ctx = 110592
[54073] 0.02.976.998 I srv          init: idle slots will be saved to prompt cache upon starting a new task
```

---

## Current Architecture

### Swap Flow (5 steps)

```
1. SAVE current model's slot  → POST /slots/0?action=save (child writes slot-0.bin)
2. TRIGGER load target model  → POST /v1/chat/completions (minimal 1-token request)
3. WAIT for model loaded      → Poll router /v1/models until status="loaded"
4. RESTORE target slot        → POST /slots/0?action=restore (child reads slot-0.bin)
5. SET m.current = target     → Manager state update
```

### Key Components

| Component | Role | Path |
|-----------|------|------|
| **Manager** (`super-go-manager`) | Orchestrates swap cycle, save/restore | `:9293` |
| **Router** (`super-router`) | Routes requests to child servers, manages models-max=1 | `:18094` |
| **Child servers** (`llama-server`) | Actual inference, slot save/restore, KV cache | Dynamic ports |
| **Slot files** (`slot-0.bin`) | KV cache snapshots on tmpfs | `council-config/slots/kv-slots/` |

### llama-server Slot Mechanism

The child server has **two separate caching mechanisms**:

1. **Slot KV Cache** (`--slot-save-path`, `--slot-restore-path`)
   - Per-slot conversation context (slot 0, 1, etc.)
   - Saved via `POST /slots/0?action=save` → writes `slot-0.bin`
   - Restored via `POST /slots/0?action=restore` → reads `slot-0.bin`
   - Contains the actual KV cache entries for the conversation

2. **Prompt Cache** (model-level, `cache-ram`, `cache-reuse`)
   - Shared across all slots for prefix matching
   - `cache state: 0 prompts, 0.000 MiB` when empty
   - Used for `f_keep` and `sim` calculations
   - Populated automatically when slots become idle

3. **Context Checkpoints** (`ctx-checkpoints = 16`)
   - Internal llama.cpp mechanism for long context management
   - Creates checkpoints at positions within the context
   - `restored context checkpoint (pos_min = 57336, n_tokens = 57337)`
   - Separate from slot save/restore

### Critical Configuration

```ini
# models.ini (router child spawn args)
slot-save-path = /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/qwen-160k-UD-fast
cache-type-k = q8_0
cache-type-v = q8_0
cache-ram = 16192          # 16GB prompt cache
cache-reuse = 8192         # 8GB reuse threshold
ctx-checkpoints = 16       # 16 context checkpoints
```

---

## Hypotheses (Ordered by Likelihood)

### H1: Trigger Request Processes with Empty Slot, Then Restore Doesn't Match

**Theory:** The trigger request (Step 2) arrives at the child server with an empty slot. The child processes the minimal prompt (`\n`, 1 token). Then Step 4 restores the slot file, loading 92K tokens into the slot's KV cache. However, when the **real request** arrives, it sends the full conversation history. The child compares the incoming prompt against the slot's KV cache, but:

- The trigger request created a **different token sequence** (just `\n`) than the saved slot (full conversation)
- The slot restore loads the saved KV cache, but the **slot position/offset** might not match
- The child falls back to full prompt processing because prefix matching fails

**Evidence for:**
- `f_keep = -1.000, sim = 0.000` on first request after swap back
- `cache state: 0 prompts, 0.000 MiB` — prompt cache empty

**Evidence against:**
- Slot restore reports success with correct token count
- Subsequent requests DO use cache (`f_keep = 0.999`)

**Test:** Remove the trigger request (Step 2) and use router's `/v1/models` API to load model without processing any request. Then restore slot and send real request. Check if cache is used.

---

### H2: Slot Restore Loads KV Cache, But Child's Internal Slot State is Stale

**Theory:** The slot restore (`POST /slots/0?action=restore`) loads the KV cache data into memory, but the child server's **slot metadata** (n_past, n_tokens, position) is not updated correctly. When the next request arrives, the child thinks the slot is empty and reprocesses everything.

**Evidence for:**
- Slot restore is fast (8-15ms) — might be loading data without updating slot state
- Child logs show `new slot, n_ctx = 110592` on each spawn — fresh initialization

**Evidence against:**
- Slot restore reports `NRestored` tokens matching saved count
- llama.cpp's restore should update slot state

**Test:** Add logging to check slot state (n_past, n_tokens) before and after restore. Compare with saved metadata.

---

### H3: Prompt Cache is Separate from Slot KV Cache

**Theory:** The slot KV cache (per-slot conversation context) and the prompt cache (model-level prefix sharing) are **two separate mechanisms**. The slot restore loads the conversation into the slot's KV cache, but the **prompt cache is empty**. When the first request arrives:

- The child checks the prompt cache first → empty → falls back to full processing
- The slot's KV cache IS loaded, but the child doesn't use it for prefix matching
- After the first request completes, the prompt cache is populated → subsequent requests use cache

**Evidence for:**
- `cache state: 0 prompts, 0.000 MiB` — prompt cache explicitly empty
- `idle slots will be saved to prompt cache upon starting a new task` — prompt cache populated from idle slots
- Subsequent requests work (`f_keep = 0.999`)

**Evidence against:**
- Slot KV cache should be used directly for prefix matching within the same slot
- Prompt cache is for cross-slot sharing, not same-slot reuse

**Test:** Check if the child's slot 0 has n_past > 0 after restore but before first request. If yes, the slot KV cache is loaded but not being used for prefix matching.

---

### H4: Tokenization Mismatch Between Save and Restore

**Theory:** The slot was saved with one tokenization (e.g., including system prompt with specific format), but the restore request uses different tokenization (e.g., different system prompt or jinja template). The tokens don't match, so prefix matching fails.

**Evidence for:**
- Child uses `jinja = true` for template processing
- System prompt might differ between save time and request time

**Evidence against:**
- Same model, same config, same child server binary
- Slot restore reports correct token count

**Test:** Compare token sequences from saved slot vs incoming request. Check if system prompt format is consistent.

---

## Investigation Plan

### Phase 1: Baseline — Verify Slot Restore Actually Populates KV Cache

**Goal:** Confirm whether slot restore loads KV cache into the child server's slot 0.

**Steps:**
1. Swap to qwen3.6-35b (establish clean state)
2. Swap back to qwen-160k-UD-fast
3. Immediately after RESTORE log, query the child server's slot status:
   ```
   curl http://127.0.0.1:<child_port>/slots/0
   ```
4. Check response for `n_past`, `n_tokens`, `cache_size` fields
5. Expected: `n_past = 92350` (matching saved slot_tokens)
6. If `n_past = 0`, slot restore is NOT loading KV cache correctly

**Files to modify:** `main.go` — add debug logging after RestoreSlot to query child slot status.

---

### Phase 2: Trigger Request Impact — Test Without Trigger

**Goal:** Determine if the trigger request (minimal `\n`) interferes with slot restore.

**Steps:**
1. Modify `TriggerModelLoad` to use a different mechanism:
   - Option A: Use router's `/v1/models` endpoint to trigger load (if available)
   - Option B: Send trigger with the same system prompt format as real requests
   - Option C: Skip trigger entirely — router loads on first real request
2. Test swap cycle without trigger request
3. Check if first real request uses cache (`f_keep > 0.9`)

**Files to modify:** `main.go` — `TriggerModelLoad()` method.

**Caveat:** Without trigger, router won't load the model until first real request arrives. This adds latency to the first real request (model load + prompt processing).

---

### Phase 3: Prompt Cache vs Slot Cache — Isolate Mechanisms

**Goal:** Determine whether the prompt cache or slot KV cache is responsible for the reprocessing.

**Steps:**
1. Enable verbose logging on child server (or add debug endpoint)
2. After swap back and restore, check:
   - Slot 0's `n_past` (slot KV cache state)
   - Model's prompt cache size (should be 0 initially)
3. Send first real request
4. Check if prompt processing uses slot KV cache or prompt cache
5. Look for `f_keep` value in child logs:
   - `f_keep > 0.9` → slot KV cache was used (prefix matched)
   - `f_keep = -1.000` → no cache match, full processing

**Files to read:** llama.cpp source (`llama.cpp/server/llama_server.cpp` — slot restore and prefix matching logic).

---

### Phase 4: Root Cause Fix

**Goal:** Implement fix based on findings from Phases 1-3.

**Possible fixes (depends on root cause):**

| Root Cause | Fix |
|------------|-----|
| Trigger request pollutes slot | Send trigger with matching system prompt, or skip trigger |
| Slot restore doesn't update n_past | Patch llama.cpp restore logic, or add manual slot state update |
| Prompt cache empty on first request | Force prompt cache update after restore, or use `--no-prompt-cache-overhead` |
| Tokenization mismatch | Ensure consistent system prompt format across save/restore/request |

---

## Constraints

- **models-max=1** is intentional (VRAM limits) — only one model loaded at a time
- **Slot files on tmpfs** — confirmed working (5.3x faster saves, 2x faster restores)
- **Synchronous trigger** — required for router stability (fire-and-forget caused races)
- **No implicit swaps** — only `/swap` endpoint changes models (handleChatCompletions is proxy-only)
- **parallel=1** — single slot per child server

---

## Success Criteria

- [ ] Root cause identified with evidence (not speculation)
- [ ] First request after swap back uses KV cache (`f_keep > 0.9`, prompt eval < 5s for new tokens only)
- [ ] No full 83K+ token reprocessing on swap back
- [ ] Swap cycle time remains ~5-7 seconds (not degraded by fix)
- [ ] Context preservation verified: conversation continues seamlessly after swap back
- [ ] No regression in existing swap functionality (save/restore/checksums)

---

## Caveats & Uncertainty

1. **llama.cpp internals:** Slot save/restore implementation in llama.cpp may have quirks not documented. May need to read source code (`server/llama_server.cpp`, `common/slot-management.cpp`).

2. **Router vs Child behavior:** The router (super-router on :18094) and child servers (dynamic ports) have separate caching mechanisms. Confusion between them can lead to incorrect hypotheses.

3. **Prompt cache auto-population:** The log message `idle slots will be saved to prompt cache upon starting a new task` suggests prompt cache is populated lazily. This might be the intended behavior, not a bug.

4. **Context checkpoints:** The `ctx-checkpoints = 16` feature creates internal checkpoints. These might interact with slot save/restore in unexpected ways.

5. **System prompt format:** The child server applies jinja templates which might add/remove tokens compared to what was saved. This could cause prefix mismatch.

---

## Debug Commands

```bash
# Check manager logs
journalctl --user -u super-go-manager.service --since "5 min ago" --no-pager | grep -E "SWAP|SAVE|RESTORE|PROXY|AUTO-SAVE"

# Check router logs (child server output)
journalctl --user -u super-router.service --since "5 min ago" --no-pager | grep -E "print_timing|prompt processing|f_keep|sim|n_past|slot.*save|slot.*restore|cache state"

# Query child slot status (replace <port> with actual child port)
curl -s http://127.0.0.1:<port>/slots/0 | python3 -m json.tool

# Check tmpfs slot files
ls -lh /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/*/slot-0.bin

# Full swap cycle test
curl -s -w " (%{time_total}s)" -X POST "http://127.0.0.1:9293/swap?alias=qwen3.6-35b-a3b"
curl -s -w " (%{time_total}s)" -X POST "http://127.0.0.1:9293/swap?alias=qwen-160k-UD-fast"
```

---

## Related Handoffs

- `21-06-2026_super-go-manager-handoff_bc8cb5.md` — Swap cycle stability fixes (completed)
- `19-06-2026_llama-swap-slot-persistence-investigation_99070a.md` — Slot persistence investigation
- `16-06-2026_llama-swap-slot-persistence-wiring_e272f4.md` — Slot persistence wiring plan
