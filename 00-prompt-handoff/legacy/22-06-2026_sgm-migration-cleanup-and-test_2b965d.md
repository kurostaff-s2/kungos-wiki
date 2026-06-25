# SGM Migration: Dead Code Cleanup & Integration Testing

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `sgm-migration-2b965d` |
| Entity type | `handoff` |
| Short description | Wire SGM to council for delegation, fix slot save/restore race, verify slot persistence end-to-end |
| Status | `in_progress` |
| Source references | `super_council/council_main.py`, `super_council/api/super_go_manager_client.py`, `super-go-manager/main.go`, `super-go-manager/config.yaml`, `models/super-router/models.ini` |
| Generated | `22-06-2026` |
| Updated | `22-06-2026 16:00` |
| Next action / owner | Execute Phase 2 (slot persistence test cycle), then Phase 1 (dead code removal) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super-go-manager/`
**Key files for this task:**
- `super_council/council_main.py` — main proxy (8K lines, SGM wiring complete)
- `super_council/api/llama_swap_client.py` — dead, to delete (Phase 1)
- `super_council/api/super_go_manager_client.py` — active, replaces llama_swap_client
- `super-go-manager/main.go` — SGM server (new endpoints added)
- `super-go-manager/config.yaml` — slot models + restore timeout
- `models/super-router/models.ini` — per-model `slot-save-path` config

## Background

Super Go Manager (SGM, :9293) replaces llama-swap (:9292) as the single swap backend. Full wiring is complete:
- `SuperGoManagerClient` created as drop-in replacement for `LlamaSwapClient`
- `council_main.py` import + instantiation updated, all "llama-swap" docstrings → "SGM"
- SGM `/save` and `/restore` endpoints added (were noop stubs)
- Pre-proxy slot save added to `handleChatCompletions` (fixes eviction race)
- Restore timeout made configurable (was hardcoded 30s, now 300s default)
- Empty-slot guard added (prevents 0-token restore from locking swap)

## Changes Applied

### SGM (`super-go-manager/main.go`)

| Change | What | Why |
|--------|------|-----|
| `POST /save` endpoint | New HTTP handler → calls `m.SaveSlot(alias)` | Council needs standalone save (not just during swap) |
| `POST /restore` endpoint | New HTTP handler → calls `m.RestoreSlot(alias)` | Council needs standalone restore |
| Pre-proxy save in `handleChatCompletions` | When `requested_model != current_model`, save current slot BEFORE proxying | Router auto-unloads current model on proxy; by the time pollLoop detects `loaded → unloaded`, child is already dead |
| `RestoreTimeoutS` config | Replace hardcoded 30s with configurable timeout (default 300s) | 2.8GB slot (80K tokens) needs ~90s to restore on NVMe |
| Empty-slot guard in `RestoreSlot` | If `meta.SlotTokens == 0`, return nil (cold start) instead of attempting restore | Prevents 0-token restore from stale backup locking swap forever |

### SGM Config (`super-go-manager/config.yaml`)

```yaml
restore_timeout_s: 300  # was: hardcoded 30s in code
```

### Router Config (`models/super-router/models.ini`)

Added `slot-save-path` for models that were missing it:
- `gemma-4-26b`: `slot-save-path = /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/gemma-4-26b`
- `nemotron-cascade`: `slot-save-path = /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/nemotron-cascade`

`qwen-160k-UD-fast` and `qwen3.6-35b-a3b` already had `slot-save-path` configured.

### Council Client (`super_go_manager_client.py`)

| Change | What |
|--------|------|
| `save_slot(model_id)` | Calls `POST /save` instead of returning `{"status": "noop"}` |
| `restore_slot(model_id)` | Calls `POST /restore` instead of returning `{"status": "noop"}` |

### Council Main (`council_main.py`)

- All "llama-swap" → "SGM" in docstrings, comments, log messages (20+ references)
- 2 remaining references in commented-out deprecated code (historical, safe to leave)

## Bugs Found & Fixed

### Bug 1: Auto-save on eviction fires too late (FIXED)
- **Symptom:** `WARN: auto-save on eviction failed for qwen-160k-UD-fast: model not loaded (no child port)`
- **Root cause:** Poll loop detects `loaded → unloaded` after child process has already exited. `SaveSlot` needs child port to call `POST /slots/0?action=save`.
- **Fix:** Pre-proxy save in `handleChatCompletions` — save current slot when `requested_model != current_model`, BEFORE proxying (which triggers router's auto-unload).

### Bug 2: Restore timeout too short for large slots (FIXED)
- **Symptom:** `SLOT RESTORE FAILED [qwen-160k-UD-fast]: context deadline exceeded` — 2.8GB slot couldn't restore in 30s.
- **Fix:** Configurable `restore_timeout_s` (300s default). `NewSlotClient` accepts timeout parameter.

### Bug 3: 0-token restore locks swap forever (FIXED)
- **Symptom:** `⚠ RESTORE RETURNED 0 TOKENS [gemma-4-26b]: slot empty/corrupted, keeping swap lock` — `swapping=true` stuck, all requests blocked with 503.
- **Root cause:** Stale `slot-0.bin.swapbak` from previous failed swap was restored, returned 0 tokens, and SwapModel kept the lock indefinitely.
- **Fix:** If `meta.SlotTokens == 0`, treat as cold start (return nil) instead of attempting restore.

### Bug 4: Missing `slot-save-path` for gemma/nemotron (FIXED)
- **Symptom:** gemma and nemotron in SGM's `slot_models` but child couldn't write `slot-0.bin` — no `slot-save-path` in `models.ini`.
- **Fix:** Added `slot-save-path` entries to `models.ini` for both models.

## Remaining Work

### Phase 1: Dead Code Audit & Removal

1. **Delete `api/llama_swap_client.py`** — verify zero non-test imports:
   ```bash
   grep -rn "llama_swap_client\|LlamaSwapClient\|LlamaSwapError" super_council/ --include="*.py" | grep -v __pycache__ | grep -v test
   ```
2. **Delete `api/test_llama_swap_client.py`** — tests for dead code (4 pre-existing failures)
3. **Completion gate:**
   - [ ] `grep -rn "llama_swap\|LlamaSwap\|LLAMA_SWAP" super_council/ --include="*.py"` returns zero non-test results
   - [ ] `python3 -c "import py_compile; py_compile.compile('council_main.py', doraise=True)"` passes
   - [ ] Council starts without import errors

### Phase 2: Slot Persistence Test Cycle (CURRENT)

**Preconditions:**
- [x] SGM running with new binary (pre-proxy save, restore timeout, empty-slot guard)
- [x] Router running with updated `models.ini` (slot-save-path for all 4 models)
- [x] Council running with SGM client wired (save/restore call real endpoints)
- [x] Qwen slot exists: 3.0GB, 87,889 tokens

**Test 1: Slot Restore After Swap (CRITICAL)**
```bash
# Current state: qwen loaded with 87K token slot saved
# Step 1: Swap to gemma (triggers pre-proxy save of qwen)
curl -s -X POST http://127.0.0.1:9293/swap -H "Content-Type: application/json" -d '{"alias":"gemma-4-26b"}'

# Step 2: Wait for swap, verify health
sleep 10
curl -s http://127.0.0.1:9293/health | python3 -m json.tool
# Expected: "current": "gemma-4-26b", "swapping": false

# Step 3: Swap back to qwen (should restore 87K token slot)
curl -s -X POST http://127.0.0.1:9293/swap -H "Content-Type: application/json" -d '{"alias":"qwen-160k-UD-fast"}'

# Step 4: Wait for swap + restore (may take 60-120s for 2.8GB restore)
sleep 30
curl -s http://127.0.0.1:9293/health | python3 -m json.tool
# Expected: "current": "qwen-160k-UD-fast", "swapping": false

# Step 5: Check logs for restore
journalctl --user -u super-go-manager --since "now-2min" --no-pager | grep -i "restore\|RESTORE"
# Expected: "RESTORE qwen-160k-UD-fast: 87889 tokens"
```

**Test 2: Pre-proxy Save (Router Auto-Route)**
```bash
# Don't use /swap endpoint — use chat completion to trigger router auto-route
# This tests the pre-proxy save path (not SwapModel)

# Current: gemma loaded
# Send request for qwen — SGM should save gemma slot BEFORE proxying
curl -s -X POST http://127.0.0.1:9293/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-160k-UD-fast","messages":[{"role":"user","content":"hello"}],"max_tokens":5}'

# Check logs for pre-proxy save
journalctl --user -u super-go-manager --since "now-1min" --no-pager | grep -i "PRE-PROXY\|SAVE"
# Expected: "PRE-PROXY SAVE: gemma-4-26b (before routing to qwen-160k-UD-fast)"
```

**Test 3: Full Council Delegation Flow**
```bash
# Trigger delegation through council (tests full council → SGM → router pipeline)
curl -s -X POST http://127.0.0.1:8090/api/swap \
  -H "Content-Type: application/json" \
  -d '{"alias":"nemotron-cascade"}'

# Expected: swap succeeds, SGM handles save/restore
# Check council logs for SGM connection
journalctl --user -u council-supervisor -n 20 --no-pager
```

**Test 4: Non-Slot Model Swap**
```bash
# Swap to mellum2-12b (no slot persistence)
curl -s -X POST http://127.0.0.1:9293/swap -H "Content-Type: application/json" -d '{"alias":"mellum2-12b"}'

# Expected: swap succeeds but no slot save/restore (router handles routing only)
```

**Test 5: Slot Persistence Verification**
```bash
# Check slot files exist for all 4 slot-persistent models
ls -lh /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/*/slot-0.bin
ls -lh /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/*/*/slot-0.json

# Expected: slot-0.bin in each alias dir, slot-0.json in config_hash subdir
# qwen-160k-UD-fast: 3.0GB, 87889 tokens ✓
# gemma-4-26b: should exist after Test 2 pre-proxy save
# nemotron-cascade: should exist after Test 3
# qwen3.6-35b-a3b: should exist if ever used
```

### Phase 3: Llama-Swap Deprecation (Optional)

**Dependencies:** Phase 2 complete, all tests passing

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

## Current State (as of 22-06-2026 16:00)

| Component | Status | Notes |
|-----------|--------|-------|
| SGM binary | ✅ Built, running | Pre-proxy save, restore timeout, empty-slot guard |
| SGM config | ✅ Updated | `restore_timeout_s: 300` |
| Router config | ✅ Updated | `slot-save-path` for all 4 slot models |
| Council client | ✅ Updated | `save_slot`/`restore_slot` call real endpoints |
| Council main | ✅ Updated | All "llama-swap" → "SGM" docstrings |
| Qwen slot | ✅ Exists | 3.0GB, 87,889 tokens, checksum valid |
| Gemma slot | ✅ Cleaned | Stale 0-token metadata removed |
| Nemotron slot | ❌ Empty | No `slot-0.bin` or metadata yet |
| qwen3.6-35b-a3b slot | ❌ Empty | No `slot-0.bin` or metadata yet |

## Known Issues

### Concurrency (Gemma Review — Critical)
- **`m.restoring` map data race:** Written in `pollLoop`, read in `handleChatCompletions` without mutex. Can cause Go panic under load.
- **`/save` and `/restore` bypass `swapLock`:** Can run concurrently with `SwapModel`, risking file corruption.
- **Fix needed:** Add `sync.RWMutex` to `Manager`; acquire `swapLock` in `handleSave`/`handleRestore`.

### Backup Failure is Non-Fatal
- If `BackupSlot` fails during swap, swap proceeds. Idle save can then corrupt `slot-0.bin`.
- **Recommendation:** Abort swap on backup failure for slot-persistent models.

### Config Hash Directory Bloat
- Old `config_hash` subdirectories never purged.
- **Recommendation:** `CleanupOrphans` should remove obsolete config_hash dirs.

## Constraints

- **SGM must be running** before council restart
- **Slot persistence is critical** — verify slot files are created for the 4 configured models
- **Don't delete llama-swap binaries** until Phase 3 is explicitly approved — keep as rollback option
- **Env var is `SGM_URL`** — don't mix with old `LLAMA_SWAP_URL`

## Success Criteria

- [x] SGM `/save` and `/restore` endpoints functional
- [x] Council client calls real SGM endpoints (not noop)
- [x] Pre-proxy save prevents eviction race
- [x] Restore timeout handles 2.8GB+ slots
- [x] Empty-slot guard prevents swap lock hang
- [x] `slot-save-path` configured for all 4 slot models
- [x] All "llama-swap" docstrings → "SGM"
- [ ] Slot restore verified end-to-end (swap away → swap back → tokens restored)
- [ ] Pre-proxy save verified (router auto-route saves slot before unload)
- [ ] Full council delegation flow verified
- [ ] Non-slot model swap verified
- [ ] Dead code removed (llama_swap_client.py)
- [ ] All council tests pass (no regression)

## Caveats

- **SGM blocks requests during swap** — `POST /v1/chat/completions` returns 503 while `swapping=true`. Council retry logic must handle this.
- **VRAM management is council-side** — SGM doesn't report VRAM. Council uses direct `nvidia-smi` calls.
- **Slot paths must match** — SGM's `slot_dir` must point to the same directory council expects.
- **Model paths in SGM config** must match actual `.gguf` file locations.
- **Restore is slow for large slots** — 2.8GB takes ~60-120s on NVMe. `restore_timeout_s: 300` provides headroom.
- **Router controls model lifecycle** — SGM can't intercept unload events. Pre-proxy save is the workaround.
