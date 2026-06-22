# SGM Migration: Dead Code Cleanup & Integration Testing

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `sgm-migration-2b965d` |
| Entity type | `handoff` |
| Short description | Remove llama-swap dead code from council, verify SGM-based swap flow end-to-end |
| Status | `draft` |
| Source references | `super_council/council_main.py`, `super_council/api/super_go_manager_client.py`, `super-go-manager/config.yaml` |
| Generated | `22-06-2026` |
| Next action / owner | Execute Phase 1 (dead code audit), then Phase 2 (SGM integration test) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super-go-manager/`
**Key files for this task:**
- `super_council/council_main.py` — main proxy (8K lines, partial SGM wiring done)
- `super_council/api/llama_swap_client.py` — dead, to delete
- `super_council/api/super_go_manager_client.py` — new, replaces llama_swap_client
- `super-go-manager/config.yaml` — updated with 4 slot-persistent models

## Background

Super Go Manager (SGM, :9293) replaces llama-swap (:9292) as the single swap backend. Initial wiring is complete:
- `SuperGoManagerClient` created as drop-in replacement for `LlamaSwapClient`
- `council_main.py` import + instantiation updated
- SGM config updated with `gemma-4-26b` and `nemotron-cascade`

**Remaining work:** Dead code removal (llama-swap remnants), docstring cleanup, integration testing.

## Phase 1: Dead Code Audit & Removal

**What:** Remove all llama-swap artifacts that are no longer needed.
**Files:** `super_council/api/llama_swap_client.py`, `council_main.py`
**Dependencies:** None

### Steps

1. **Delete `api/llama_swap_client.py`** — entire file is dead. Verify zero imports remain:
   ```bash
   grep -rn "llama_swap_client\|LlamaSwapClient\|LlamaSwapError" super_council/ --include="*.py" | grep -v __pycache__ | grep -v test
   ```
   If any non-test references exist, either update them or confirm they're unreachable code paths.

2. **Delete `api/super_go_manager_client.py` backup** — if created as `.bak` or similar.

3. **Clean remaining llama-swap docstrings** in `council_main.py`:
   - File docstring (lines 2-8): Update to reference SGM
   - `_model_is_ready()` docstring (line 2368): "via llama-swap" → "via SGM"
   - `_swap_to_via_sgm()` body comments (line 2490): "llama-swap" → "SGM"
   - `_post_chat_completion()` docstring (line 2517): "through llama-swap" → "through SGM"
   - `_save_current_slot()` docstring (line 2527): "llama-swap" → "SGM"
   - `_restore_current_slot()` docstring (line 2548): "llama-swap" → "SGM"
   - `_get_free_vram()` docstring (line 2567): "llama-swap" → "SGM nvidia-smi fallback"
   - `_wait_for_vram()` docstring (line 2577): "llama-swap" → "SGM nvidia-smi fallback"

4. **Remove unused env var references:**
   - `LLAMA_SWAP_URL` → verify only `SGM_URL` is referenced
   - Default port `:9292` → `:9293`

5. **Check for llama-swap systemd services:**
   ```bash
   systemctl --user list-units | grep llama-swap
   ```
   If active, document for separate deprecation (not this handoff).

### Tests

- [ ] `grep -rn "llama_swap\|LlamaSwap\|LLAMA_SWAP" super_council/ --include="*.py"` returns zero non-test results
- [ ] `python3 -c "import py_compile; py_compile.compile('council_main.py', doraise=True)"` passes
- [ ] Council starts without import errors: `python3 -c "from super_council.council_main import CouncilApp; print('import ok')"`

### Completion Gate

- [ ] All llama-swap imports removed
- [ ] All docstrings updated
- [ ] Syntax check passes
- [ ] Import test passes

---

## Phase 2: SGM Integration Testing

**What:** Verify SGM-based swap flow works end-to-end through council.
**Files:** `super_council/council_main.py`, `super-go-manager/config.yaml`
**Dependencies:** Phase 1 complete

### Pre-Flight Checklist

- [ ] SGM is running: `curl -s http://127.0.0.1:9293/health` returns `{"status":"ok"}`
- [ ] Super-router is running: `curl -s http://127.0.0.1:18094/v1/models` returns model list
- [ ] Council is stopped (will restart for testing)

### Test 1: Health Check

```bash
# SGM health
curl -s http://127.0.0.1:9293/health | python3 -m json.tool

# Expected: {"status": "ok", "current": "<model>", "swapping": false, "router_url": "http://127.0.0.1:18094"}
```

### Test 2: Model List

```bash
curl -s http://127.0.0.1:9293/models | python3 -m json.tool

# Expected: list of models including qwen-160k-UD-fast, qwen3.6-35b-a3b, gemma-4-26b, nemotron-cascade
```

### Test 3: Swap Flow (Manual)

```bash
# Swap to gemma-4-26b
curl -s -X POST http://127.0.0.1:9293/swap -H "Content-Type: application/json" -d '{"alias":"gemma-4-26b"}' | python3 -m json.tool

# Expected: {"status": "ok", "model": "gemma-4-26b"}
# Wait 30-60s for model to load

# Verify swap completed
curl -s http://127.0.0.1:9293/health | python3 -m json.tool
# Expected: "current": "gemma-4-26b", "swapping": false
```

### Test 4: Chat Completion Proxy

```bash
# Send a test chat completion through SGM
curl -s -X POST http://127.0.0.1:9293/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4-26b","messages":[{"role":"user","content":"Say hello in 3 words"}],"max_tokens":20}' \
  | python3 -m json.tool

# Expected: 200 OK with choices[0].message.content
```

### Test 5: Council Integration (Full Restart)

```bash
# Start council with SGM
export SGM_URL=http://127.0.0.1:9293
systemctl --user restart super-council

# Check council logs for SGM connection
journalctl --user -u super-council -n 20 --no-pager

# Expected: "Super Go Manager available at http://127.0.0.1:9293"
```

### Test 6: Council Delegation Swap

```bash
# Trigger a swap through council's delegation endpoint
curl -s -X POST http://127.0.0.1:8090/api/swap \
  -H "Content-Type: application/json" \
  -d '{"alias":"nemotron-cascade"}' | python3 -m json.tool

# Expected: swap succeeds, SGM handles save/restore
```

### Test 7: Slot Persistence Verification

```bash
# Check slot files exist for slot-persistent models
ls -la /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/

# Expected: directories for qwen-160k-UD-fast, qwen3.6-35b-a3b, gemma-4-26b, nemotron-cascade
# Each with slot-0.bin and slot-0.json metadata
```

### Test 8: Non-Slot Model Swap

```bash
# Swap to mellum2-12b (no slot persistence)
curl -s -X POST http://127.0.0.1:9293/swap -H "Content-Type: application/json" -d '{"alias":"mellum2-12b"}' | python3 -m json.tool

# Expected: swap succeeds but no slot save/restore (router handles routing only)
```

### Completion Gate

- [ ] All 8 tests pass
- [ ] SGM health reports correct current model after each swap
- [ ] Slot files created/updated for slot-persistent models
- [ ] Council logs show no SGM-related errors
- [ ] Chat completions return valid responses through SGM proxy

---

## Phase 3: Llama-Swap Deprecation (Optional)

**What:** Safely decommission llama-swap service.
**Dependencies:** Phase 2 complete, all tests passing

### Steps

1. **Verify llama-swap is not referenced:**
   ```bash
   grep -rn "9292\|llama.swap\|LLAMA_SWAP" ~/.config/systemd/ --include="*.service" 2>/dev/null
   ```

2. **Stop llama-swap service:**
   ```bash
   systemctl --user stop llama-swap
   systemctl --user disable llama-swap
   ```

3. **Verify council still works:**
   ```bash
   curl -s http://127.0.0.1:8090/health | python3 -m json.tool
   ```

4. **Archive llama-swap config** (don't delete yet):
   ```bash
   mv /home/chief/Coding-Projects/7-council/llama-swap/ /home/chief/Coding-Projects/7-council/llama-swap-archived/
   ```

### Completion Gate

- [ ] llama-swap stopped and disabled
- [ ] Council health check passes without llama-swap
- [ ] Swap flow still works through SGM only

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Delete | `super_council/api/llama_swap_client.py` | Dead code, replaced by SGM client |
| Modify | `super_council/council_main.py` | Docstring cleanup (llama-swap → SGM) |
| Verify | `super-go-manager/config.yaml` | Already updated, confirm models load |

## Constraints

- **No functionality changes** — this is cleanup + verification only
- **SGM must be running** before council restart
- **Slot persistence is critical** — verify slot files are created for the 4 configured models
- **Don't delete llama-swap binaries** until Phase 3 is explicitly approved — keep as rollback option
- **Env var is `SGM_URL`** — don't mix with old `LLAMA_SWAP_URL`

## Success Criteria

- [ ] Zero llama-swap references in non-test Python code
- [ ] Council starts and connects to SGM on `:9293`
- [ ] Model swap works through SGM (save → trigger → restore)
- [ ] Slot persistence verified for 4 configured models
- [ ] Chat completions proxy through SGM returns valid responses
- [ ] Non-slot models (mellum2-12b, gpt-oss-20b) swap without slot operations
- [ ] All existing council tests still pass (no regression)
- [ ] Council logs show no SGM-related errors

## Caveats

- **SGM blocks requests during swap** — `POST /v1/chat/completions` returns 503 while `swapping=true`. Council retry logic must handle this.
- **VRAM management is council-side** — SGM doesn't report VRAM. Council uses direct `nvidia-smi` calls.
- **Slot paths must match** — SGM's `slot_dir` must point to the same directory council expects.
- **Model paths in SGM config** must match actual `.gguf` file locations. If paths differ from `upstream-config.json`, SGM will fail to trigger-load.
