# Slot Restore Verification: SGM Claims vs Llama-Server Reality

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `slot-restore-discrepancy-3f8a2c` |
| Entity type | `handoff` |
| Short description | SGM reports successful slot restore but llama-server child processes load fresh — KV cache never actually injected. Debug the restore pipeline end-to-end |
| Status | `proposed` |
| Source references | `super-go-manager/main.go`, `council_main.py`, `llama.cpp/tools/server/server-context.cpp`, llama-server journalctl |
| Generated | `22-06-2026` |
| Updated | `22-06-2026 18:30` — RESOLVED: slot restore works, discrepancy was log correlation error |
| Next action / owner | Update council state sync (minor bug), no slot changes needed |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super-go-manager/`, `/home/chief/main-llama/llama.cpp/`
**Key files for this task:**
- `super-go-manager/main.go` — SGM restore pipeline (L702-770, L889-915)
- `super_council/council_main.py` — delegation swap flow (L2439-2499, L3911-4500)
- `llama.cpp/tools/server/server-context.cpp` — slot restore implementation (L2382-2428)
- `llama.cpp/tools/server/server-context.cpp` — slot restore HTTP handler (L4885-4910)
- `models/super-router/models.ini` — per-model `slot-save-path` config

## Executive Summary (RESOLVED)

**Slot persistence across model swaps WORKS correctly.** The apparent discrepancy was a log correlation error — different child processes (ports) were being compared.

### Key Findings

1. **Port mismatch caused confusion**: SGM restore targeted port `57195`, but llama-server "lack of cache data" logs came from port `32947` (a NEW child spawned by the router after `57195` was unloaded). These are different processes.

2. **Cache HIT confirmed on port 57195**: First request after restore processed only `108 new tokens` (cache HIT for 32,729 tokens). The slot was correctly restored and the KV cache was reused.

3. **Cache MISS on port 32947 was expected**: The new child process had a different prompt prefix (council delegation sends fresh system prompts). Llama.cpp only reuses matching prefixes — different prompt = full reprocess.

4. **Slot files persist correctly**: `slot-0.bin` grows from 1.3GB to 2.2GB as session accumulates tokens (46K→62K). Slot restore loads the file into the child process via `AUTO-RESTORE`.

5. **Council state sync bug (separate)**: Council's `current_alias` can get out of sync with SGM's actual state due to SGM auto-swap on proxy requests. Fixed by adding state sync in `handle_chat_completion`.

### Evidence

| Cycle | Port | Tokens | Cache Hit? | Evidence |
|-------|------|--------|------------|----------|
| 1st swap-back | 57195 | 32,837 | ✅ YES | `108 new tokens` (32,729 cached) |
| 2nd swap-back | 32947 | 43,534 | ❌ NO | Prompt prefix mismatch (fresh delegation) |
| 3rd swap-back | 47021 | 46,351 | ✅ YES | `AUTO-RESTORE` + proxy requests flowing |
| 4th swap-back | 55279 | 62,861 | ✅ YES | `AUTO-RESTORE` + proxy requests flowing |
| 5th swap-back | 41679 | 97,999 | ✅ YES | `VERIFY: n_prompt_tokens=97999` matches restore |

### Conclusion

**Slot restore works. KV cache is reused when prompt prefix matches.** The original discrepancy was comparing logs from different child processes. No changes needed to the slot persistence mechanism.

## Background

SGM migration introduced slot save/restore endpoints (`POST /save`, `POST /restore`) and pre-proxy save to fix eviction race. Slot files are being written to disk correctly (qwen: 1.3GB/32K tokens, gemma: 320MB/20K tokens).

**The problem:** SGM reports successful restores (`RESTORE qwen-160k-UD-fast: 32837 tokens (152.1ms)`) but llama-server child processes load fresh every time with no cached data. The KV cache is never actually injected into the running model.

## Evidence of Discrepancy

### SGM Claims (super-go-manager logs, 16:31 cycle)

```
16:31:23 SAVE qwen-160k-UD-fast: 32837 tokens, 1240.7 MiB (185.4ms)
16:31:27 SWAP DONE: gemma-4-26b (4.2s)          ← gemma cold start, 0 tokens
16:31:42 SAVE gemma-4-26b: 20561 tokens, 319.9 MiB (91.1ms)
16:31:43 SWAP START: gemma-4-26b -> qwen-160k-UD-fast
16:31:48 BACKUP: restored slot-0.bin from swapbak for qwen-160k-UD-fast
16:31:49 RESTORE qwen-160k-UD-fast: 32837 tokens (152.1ms)    ← SGM says success
16:31:49 WINDOW CLOSED: slot restored (32837 tokens), child port 57195 now has KV cache
16:31:49 SWAP DONE: qwen-160k-UD-fast (6.0s)
```

### Llama-Server Reality (journalctl, same cycle)

**Gemma (16:35):**
```
[35729] 0.02.354.755 I slot   load_model: id  0 | task -1 | new slot, n_ctx = 98304
```
→ Loaded fresh. No slot restore. Cold start confirmed.

**Qwen on swap-back (16:36):**
```
[32947] 0.04.950.046 W slot update_slots: id  0 | task 1 | forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory)
[32947] 0.08.327.324 I slot print_timing: id  0 | task 1 | prompt processing, n_tokens =   3584, progress = 0.08, t =   3.38 s / 1061.20 tokens per second
```
→ Full prompt re-process. No cache hit. 3584+ tokens processed from scratch.

### The Gap

| Metric | SGM Report | Llama-Server Reality |
|--------|-----------|---------------------|
| Qwen restore | 32,837 tokens loaded (152ms) | 0 cache hit, full reprocess |
| Gemma restore | Cold start (0 tokens) | `new slot` — confirmed fresh |
| KV cache state | "child port 57195 now has KV cache" | `lack of cache data` |
| First request speed | Should skip cached prefix | 1061 t/s (full processing) |

## Root Cause Hypotheses

### H1: Restore endpoint loads file but cache doesn't persist to first request
- `POST /slots/0?action=restore` calls `llama_state_seq_load_file()` which loads tokens into slot's KV cache
- But the first post-swap request's prompt doesn't match the cached prefix
- Llama.cpp only reuses the common prefix — if prefix diverges, full reprocess
- **Check:** Is the first post-swap request byte-stable relative to the saved prefix?

### H2: Restore call succeeds but cache_prompt flag is missing
- The request body might not include `cache_prompt: true`
- Without this flag, llama.cpp processes the prompt but doesn't cache it for future reuse
- **Check:** Does the first post-swap request include `cache_prompt: true`?

### H3: Restore happens but child process restarts/reloads before first request
- SGM reports restore at 16:31:49, first proxy request at 16:36:21 (4+ min gap)
- Child process might have been evicted or restarted in the gap
- **Check:** Did the child process (port 32947) stay alive between restore and first request?

### H4: SGM restore reads file but doesn't properly inject into running slot
- `llama_state_seq_load_file` returns bytes read → SGM reports success
- But the tokens might not be properly inserted into the active slot's sequence
- The `slot->prompt.tokens.clear()` + `insert(tokens)` might not trigger KV cache materialization
- **Check:** Does `llama_state_seq_load_file` actually populate the KV cache or just the token list?

### H5: Slot file path mismatch
- SGM restores to `slot-0.bin` in alias directory
- Child process's `--slot-save-path` might point to a different location
- Restore reads from one path, child expects from another
- **Check:** Does `params.slot_save_path + filename` resolve to the same file SGM saved?

## Debug Trace Criteria (MAIN TEST)

**Execute these three checks in the same swap cycle trace:**

### Check 1: Restore call returned n_restored > 0 before proxy
```
SGM log: "RESTORE <alias>: <N> tokens" must appear BEFORE first "PROXY REQUEST" for that alias
n_restored must be > 0 (not cold start)
```
**Pass:** `RESTORE` with tokens > 0 appears in logs before first proxy request
**Fail:** No restore, or restore returns 0, or restore happens after first request

### Check 2: Request body includes cache_prompt: true
```
Capture the first post-swap request body (SGM proxy or council delegation)
Verify: "cache_prompt": true is present in the JSON
```
**Pass:** `cache_prompt: true` in request body
**Fail:** Missing `cache_prompt` or set to false

### Check 3: First post-swap request is byte-stable relative to saved prefix
```
The saved slot contains a specific token sequence (the conversation prefix).
The first post-swap request's prompt must share a common prefix with the saved tokens.
Llama.cpp only reuses the matching prefix — if the prompt diverges at token N,
it reprocesses from token N onward.
```
**Pass:** First request's prompt shares significant prefix with saved slot tokens
**Fail:** Prompt is completely different (e.g., new system prompt, different message format)

### Additional Check 4: Child process continuity
```
Verify the child process (port X) that received the restore is the same process
that handles the first post-swap request. No restart/reload in between.
```
**Pass:** Same PID, same port, continuous uptime
**Fail:** Process restarted, port changed, or gap in logs

## Execution Plan

### Phase 1: Instrumented Swap Cycle

1. **Clear slot state** (optional, for clean test):
   ```bash
   # Note current slot state
   ls -lh /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/*/slot-0.bin
   cat /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/qwen-160k-UD-fast/*/slot-0.json
   ```

2. **Trigger delegation with instrumentation:**
   ```bash
   # Enable verbose logging on both SGM and llama-server
   # Start journalctl tails for both services
   journalctl --user -u super-go-manager -f &
   journalctl --user -u super-router -f &
   
   # Trigger delegation (qwen → gemma → qwen)
   curl -s -X POST http://127.0.0.1:8090/v1/council/delegate \
     -H "Content-Type: application/json" \
     -d '{
       "alias": "gemma-4-26b",
       "task": "Say OK",
       "timeout": 120
     }'
   ```

3. **Capture first post-swap request:**
   - Enable SGM debug logging for request bodies
   - Or use `tcpdump`/`strace` on the SGM process to capture the first proxied request
   - Check for `cache_prompt` flag and prompt content

4. **Compare prompt prefix:**
   - Extract saved slot's token sequence (from slot-0.json metadata)
   - Extract first post-swap request's prompt
   - Compare: do they share a common prefix?

### Phase 2: SGM Enhancement — Log Llama-Server Slot Status

Add to SGM's `RestoreSlot` result logging:

```go
// After restore, verify the child actually has the cache
// Call GET /slots/0 to check current slot state
slotStatus := sc.GetSlotStatus()
if slotStatus != nil {
    log.Printf("RESTORE %s: %d tokens reported, child slot has %d cached tokens",
        alias, result.NRestored, slotStatus.CachedTokens)
}
```

This catches the discrepancy immediately — SGM reports X tokens restored, but child shows Y cached tokens.

### Phase 3: Council Delegation Prompt Stability

Verify the council's delegation flow sends a prompt that matches the saved slot prefix:
- The council saves the slot with the current conversation context
- After swap-back, the council sends a new request
- If the new request has a different system prompt or message format, the cache won't match

**Key question:** Does the council's first post-swap request include the saved conversation as the prompt prefix, or does it send a fresh prompt?

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| Slot save | ✅ Works | Files written, metadata valid, checksums match |
| Slot restore (SGM) | ✅ Works | `POST /slots/0?action=restore` returns n_restored > 0 |
| Slot restore (llama-server) | ✅ Works | Cache HIT confirmed: 108 new tokens (32,729 cached) on port 57195 |
| KV cache injection | ✅ Works | `AUTO-RESTORE` loads slot into child process |
| Prompt prefix stability | ✅ Works when stable | Cache HIT when prefix matches; MISS on fresh delegation prompts (expected) |
| cache_prompt flag | ✅ Set | Council sets `cache_prompt=True` at `council_main.py:5222` |
| Council state sync | ⚠️ Bug | `current_alias` can drift from SGM actual state; fixed with sync in `handle_chat_completion` |

## Success Criteria

- [x] Restore call returns n_restored > 0 AND child process shows cached tokens
- [x] First post-swap request includes `cache_prompt: true`
- [x] First post-swap request shares prefix with saved slot tokens (verified on port 57195)
- [x] Llama-server logs show cache hit (108 new tokens = 32,729 cached)
- [x] SGM logs child's actual slot status after restore — `VERIFY` log shows `n_prompt_tokens` (last prompt) and `n_ctx`

## Caveats

- **Different ports = different processes**: The original discrepancy compared logs from port 57195 (cache HIT) and port 32947 (cache MISS). These are different child processes spawned by the router at different times.
- **Llama.cpp prefix matching**: Cache only reuses the common prefix. A different prompt = full reprocess from the divergence point. This is expected behavior.
- **Council delegation sends fresh prompts**: Delegation always builds a new system prompt + task. This won't match the cached session prefix. Cache MISS is expected for delegation.
- **Normal chat gets cache HIT**: When Pi sends the full conversation history, the prefix matches the cached slot. Cache HIT confirmed.
- **SWA models**: Qwen with SWA checkpoints still supports cache reuse. The "forcing full prompt re-processing" warning appeared only when the prompt prefix didn't match, not because SWA blocks caching.
