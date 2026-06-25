# Llama-Swap: Native Build + Default Model Slot Persistence

| Field | Value |
|-------|-------|
| Project ID | `llama-swap` |
| Primary entity ID | `070b47` |
| Entity type | `handoff` |
| Short description | Wire Qwen3.6-35B-A3B as default model with slot persistence on native llama.cpp; verify swap cycle with subagent delegation |
| Status | `draft` |
| Source references | `/home/chief/llama-swap/config.yaml`, `/home/chief/llama-swap/docs/handoff-slot-verification.md` |
| Generated | `20-06-2026` |
| Next action / owner | Execute Phase 1 (config verification), then Phase 2 (live swap test) |

---

## Project Context

**Project root:** `/home/chief/llama-swap/`
**Related codebases:**
- Native llama.cpp (untouched): `/home/chief/main-llama/llama.cpp/`
- Patched llama.cpp (fork, no longer used): `/home/chief/llama-cpp-latest/`
- Slot store: `/home/chief/Coding-Projects/7-council/council-config/slots/`
**Key files for this task:**
- `/home/chief/llama-swap/config.yaml` — modified (see Changes Applied)
- `/home/chief/llama-swap/internal/slotstore/hook.go` — reads per-model `slotStore.enabled`
- `/home/chief/llama-swap/internal/router/base.go` — `doSwap` flow: drain → BeforeStop(save) → stop → start → AfterReady(restore)

---

## Background

### What Changed

Three configuration changes were applied to `/home/chief/llama-swap/config.yaml`:

1. **Binary switched to native build:** `macros.llama-server` changed from `/home/chief/llama-cpp-latest/build/bin/llama-server` (forked with ~600 lines of MTP/recurrent patches) to `/home/chief/main-llama/llama.cpp/build/bin/llama-server` (untouched upstream).

2. **Default model set:** `hooks.on_startup.preload: [qwen3.6-35b-a3b]` — Qwen3.6-35B-A3B loads on boot. Priority bumped to 10 (highest) so it's the last evicted.

3. **Slot persistence scoped to default model only:** `slotStore.enabled` set to `true` for `qwen3.6-35b-a3b` and `false` for all 8 other models. Non-default models start fresh on every swap.

### Why This Works

The Qwen3.6-35B-A3B model (`qwen35moe` architecture) is a **standard MoE transformer** — no recurrent layers, no MTP speculative decoding, no context checkpoints. The ~600 lines of modifications in the forked build were exclusively for:

- MTP draft cache persistence (save/restore draft KV alongside trunk KV)
- Context checkpoint binary companion files (`.checkpoints` sidecars)
- Recurrent state shrink/expand during cache operations
- Hybrid memory stale-state clearing

None of that applies to a standard transformer. The native `/slots` API (`llama_state_seq_save_file` / `llama_state_seq_load_file`) handles KV cache persistence for this model without any fork patches.

The slotstore hook (`internal/slotstore/hook.go`) already checks `mc.SlotStore.Enabled` per model — it's configurable, not hardcoded. Models with `enabled: false` are skipped entirely during `BeforeStop`/`AfterReady`.

### Caveats

- **Reasoning budget:** All models in this config are reasoning models (`--reasoning auto --reasoning-budget 8192`). Test payloads must use `max_tokens >= 512` for simple prompts and `max_tokens >= 1024` for context-heavy prompts. The model needs headroom for thinking tags (`<thinking>...</thinking>`) plus actual response tokens. Low budgets will produce truncated or incomplete reasoning.
- **KV cache contamination fix:** The forked build included a 3-line fix in `server_prompt_cache::load` (return `false` on cache miss so `prompt_clear()` runs). This prevents stale KV state on low-overlap slot reuse (`f_keep < 0.5`). Verify whether this is already upstream in the native build. If NOT present, it's a single patch worth backporting — it benefits ALL models, not just MTP/recurrent.
- **Binary hash purging:** Slot directories will be purged on first run because the binary hash changed (forked → native). This is expected behavior to prevent format corruption. Slots will be recreated on first save.
- **Multimodal:** The 35B-A3B has `--mmproj` (vision projector). Slot save captures full KV cache including vision tokens. No special handling needed.

---

## Phase 1: Configuration Verification

**What:** Confirm all config changes are correct and the native binary is functional.
**Dependencies:** None.
**Estimated effort:** ~10 min.

### Steps

1. **Verify binary path:**
   ```bash
   ls -lh /home/chief/main-llama/llama.cpp/build/bin/llama-server
   # Should exist, ~18K
   ```

2. **Verify config state:**
   ```bash
   cd /home/chief/llama-swap
   grep "llama-server" config.yaml
   # Should point to /home/chief/main-llama/llama.cpp/build/bin/llama-server

   grep -A2 "preload" config.yaml
   # Should list qwen3.6-35b-a3b

   grep "enabled:" config.yaml
   # Should show: false x8, true x1 (only qwen3.6-35b-a3b)
   ```

3. **Verify model architecture:**
   ```bash
   # Confirm qwen3.6-35b-a3b is standard transformer (no MTP/recurrent)
   grep "Architecture" /home/chief/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.meta.txt
   # Should show: qwen35moe
   ```

4. **Check native build for contamination fix:**
   ```bash
   cd /home/chief/main-llama/llama.cpp
   grep -A5 "it_best == states.end()" tools/server/server-task.cpp
   # If it returns FALSE on miss → fix is upstream (good)
   # If it returns TRUE always → fix is NOT upstream (needs backport)
   ```

### Completion Gate

- [ ] Binary exists and is executable
- [ ] Config points to native binary
- [ ] Preload lists qwen3.6-35b-a3b only
- [ ] slotStore enabled for exactly 1 model (qwen3.6-35b-a3b)
- [ ] Contamination fix status determined (upstream or needs backport)

---

## Phase 2: Restart and Boot Test

**What:** Restart llama-swap with new config, verify default model loads.
**Dependencies:** Phase 1 complete.
**Estimated effort:** ~10 min.

### Steps

1. **Restart llama-swap:**
   ```bash
   curl -X POST http://localhost:9292/v1/council/restart
   # Or restart via systemctl/service manager
   ```

2. **Verify preload fired:**
   ```bash
   # Check logs for preload event
   grep -i "preload\|qwen3.6-35b-a3b" /path/to/llama-swap/logs/
   # Should see: "preloading model: qwen3.6-35b-a3b"
   # Should see: "slotstore hook configured" with models=1
   ```

3. **Verify model is ready:**
   ```bash
   curl -s http://localhost:9292/running | python3 -m json.tool
   # Should show qwen3.6-35b-a3b in running state
   ```

4. **Verify binary hash purge (expected):**
   ```bash
   # Logs should show slot purge due to binary change
   grep -i "purged\|binary" /path/to/llama-swap/logs/
   # Expected: "slotstore: purged slots for changed binaries"
   ```

### Completion Gate

- [ ] llama-swap restarted successfully
- [ ] qwen3.6-35b-a3b preloaded and ready
- [ ] Slot hook configured for 1 model (not 9)
- [ ] Binary hash purge logged (expected first-run behavior)

---

## Phase 3: Slot Persistence Test (Default Model)

**What:** Build context with default model, swap away, swap back — verify context survives.
**Dependencies:** Phase 2 complete.
**Estimated effort:** ~20 min.

### Steps

1. **Build context with default model:**
   ```bash
   # Send a multi-turn conversation to build KV cache
   curl -s http://localhost:9292/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen3.6-35b-a3b",
       "messages": [
         {"role": "user", "content": "Remember this fact: the answer to testing is 42. Do not forget this number."},
         {"role": "assistant", "content": "I will remember that the answer to testing is 42."},
         {"role": "user", "content": "What is the answer to testing?"}
       ],
       "max_tokens": 1024
     }' | python3 -m json.tool
   # Should respond with "42" or similar (reasoning models need budget for thinking tags)
   ```

2. **Verify slot was saved (check logs):**
   ```bash
   grep -i "slotstore.*save" /path/to/llama-swap/logs/
   # Should show: "slotstore: save succeeded" for qwen3.6-35b-a3b
   ```

3. **Swap to another model (triggers eviction):**
   ```bash
   # Trigger a swap by requesting a different model
   curl -s http://localhost:9292/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "mellum2-12b",
       "messages": [
         {"role": "user", "content": "Say hello briefly."}
       ],
       "max_tokens": 512
     }' | python3 -m json.tool
   # Should get a response from mellum2-12b
   ```

4. **Verify slot save during swap:**
   ```bash
   grep -i "slotstore.*BeforeStop\|slotstore.*save" /path/to/llama-swap/logs/
   # Should show save for qwen3.6-35b-a3b (NOT for mellum2-12b)
   ```

5. **Swap back to default model:**
   ```bash
   curl -s http://localhost:9292/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen3.6-35b-a3b",
       "messages": [
         {"role": "user", "content": "What is the answer to testing?"}
       ],
       "max_tokens": 1024
     }' | python3 -m json.tool
   ```

6. **Verify context recall:**
   - **PASS:** Model answers "42" based on restored KV cache
   - **FAIL:** Model hallucinates, denies previous context, or asks for clarification

7. **Verify slot restore (check logs):**
   ```bash
   grep -i "slotstore.*AfterReady\|slotstore.*restore" /path/to/llama-swap/logs/
   # Should show: "slotstore: restore succeeded" for qwen3.6-35b-a3b
   ```

### Completion Gate

- [ ] Context built with qwen3.6-35b-a3b
- [ ] Slot saved before eviction (logged)
- [ ] Swap to mellum2-12b succeeded (no slot save for mellum)
- [ ] Swap back to qwen3.6-35b-a3b restored context
- [ ] Model correctly recalls "42" from before the swap
- [ ] Slot restore logged

---

## Phase 4: Non-Default Model Fresh Slate Test

**What:** Confirm non-default models do NOT persist slots — every swap is fresh.
**Dependencies:** Phase 3 complete.
**Estimated effort:** ~15 min.

### Steps

1. **Build context with non-default model:**
   ```bash
   curl -s http://localhost:9292/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gemma-4-26b",
       "messages": [
         {"role": "user", "content": "Remember: the secret code is ALPHA-7-Bravo. I will ask you later."}
       ],
       "max_tokens": 1024
     }' | python3 -m json.tool
   ```

2. **Swap away and back:**
   ```bash
   # Swap to another model
   curl -s http://localhost:9292/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "nex-n2-mini",
       "messages": [{"role": "user", "content": "Hi."}],
       "max_tokens": 512
     }' | python3 -m json.tool

   # Swap back to gemma
   curl -s http://localhost:9292/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gemma-4-26b",
       "messages": [
         {"role": "user", "content": "What is the secret code?"}
       ],
       "max_tokens": 1024
     }' | python3 -m json.tool
   ```

3. **Verify NO context recall:**
   - **PASS:** Model does NOT know "ALPHA-7-Bravo" (fresh slate, as expected)
   - **FAIL:** Model recalls the code (slot persisted when it shouldn't have)

4. **Verify no slot operations in logs:**
   ```bash
   grep -i "slotstore.*gemma-4-26b" /path/to/llama-swap/logs/
   # Should show NO save/restore for gemma-4-26b
   ```

### Completion Gate

- [ ] Non-default model (gemma-4-26b) served requests
- [ ] No slot save/restore logged for gemma-4-26b
- [ ] Model started fresh after swap (no context recall)

---

## Phase 5: Subagent Delegation Swap Cycle

**What:** Full end-to-end test through the actual subagent delegation flow — the production path.
**Dependencies:** Phases 1-4 complete.
**Estimated effort:** ~30 min.

### Steps

1. **Start a subagent delegation with default model:**
   - Invoke a subagent that uses `qwen3.6-35b-a3b` as its model
   - Have it produce a substantive response (100+ tokens)
   - Record the response for comparison

2. **Trigger model swap during active work:**
   - While subagent is running, trigger a swap to another model (e.g., via council model selection)
   - Verify the swap completes without errors

3. **Resume with default model:**
   - Switch back to `qwen3.6-35b-a3b`
   - Ask the model to reference context from before the swap
   - **PASS:** Context is preserved and model continues coherently
   - **FAIL:** Model loses context or hallucinates

4. **Verify slot file integrity:**
   ```bash
   # Check slot files exist and have reasonable sizes
   ls -lh /home/chief/Coding-Projects/7-council/council-config/slots/qwen3.6-35b-a3b/
   # Should show .bin files with .json metadata sidecars
   # Verify checksums match
   ```

5. **Multi-swap stress test:**
   - Perform 3-5 rapid swaps: default → model-A → default → model-B → default
   - After each return to default, verify context recall
   - **PASS:** Context survives all swap cycles
   - **FAIL:** Context degrades or corrupts after N swaps

### Completion Gate

- [ ] Subagent delegation works with default model
- [ ] Swap during active delegation completes cleanly
- [ ] Context survives swap and resume
- [ ] Slot files have valid checksums
- [ ] Multi-swap stress test passes (3-5 cycles)

---

## Files Modified

| Action | File | Change |
|--------|------|--------|
| Modified | `/home/chief/llama-swap/config.yaml` | Binary → native, default model preload, slot persistence scoped to 1 model |

## Files Read (Reference)

| File | Purpose |
|------|---------|
| `/home/chief/llama-swap/internal/slotstore/hook.go` | Per-model slotStore.enabled check |
| `/home/chief/llama-swap/internal/router/base.go` | doSwap flow: drain → save → stop → start → restore |
| `/home/chief/llama-swap/docs/handoff-slot-verification.md` | Previous investigation context |
| `/home/chief/models/qwen3.6-35b/Qwen3.6-35B-A3B-UD-Q4_K_XL.meta.txt` | Model architecture verification |

---

## Constraints

- **No code changes:** All configuration is handled through `config.yaml` only. The slotstore hook is already per-model configurable.
- **Native binary only:** Must use `/home/chief/main-llama/llama.cpp/build/bin/llama-server` (untouched upstream). No forked patches.
- **Single persistence target:** Only `qwen3.6-35b-a3b` persists slots. All other models start fresh.
- **Configurable, not hardcoded:** If the default model changes, only `hooks.on_startup.preload` and the target model's `slotStore.enabled` need updating.

---

## Success Criteria

- [ ] Native binary loads and serves Qwen3.6-35B-A3B correctly
- [ ] Default model preloads on startup
- [ ] Slot save/restore works for default model (context survives swap)
- [ ] Non-default models start fresh (no slot persistence)
- [ ] Subagent delegation swap cycle completes without context loss
- [ ] Multi-swap stress test passes (3-5 cycles)
- [ ] Slot file checksums validate correctly
- [ ] Contamination fix status determined (upstream or backported)

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| KV cache contamination on low overlap | Medium | High | Verify contamination fix is upstream; backport 3-line patch if not |
| Binary hash purge deletes valid slots | Certain (first run only) | Low | Expected behavior; slots recreate on first save |
| Multimodal tokens in KV cache | Low | Low | Standard transformer handles this natively |
| VRAM OOM during swap | Low | High | llama-swap already waits for VRAM release (30s timeout) |
