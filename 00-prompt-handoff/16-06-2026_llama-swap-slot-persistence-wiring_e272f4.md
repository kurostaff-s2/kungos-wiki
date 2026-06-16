# llama-swap Slot Persistence Wiring — Investigation & Completion

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `e272f4` |
| Entity type | `handoff` |
| Short description | Finish llama-swap slot save/restore wiring: SlotHook works, target model startup fails during swap |
| Status | `in-progress` |
| Source references | `llama-swap/internal/slotstore/`, `super_council/api/llama_swap_client.py`, `super_council/council_main.py` |
| Generated | 16-06-2026 |
| Next action / owner | Investigate why target models fail to start during swap (OOM despite VRAM being freed) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Related codebases:**
- llama-swap: `/home/chief/llama-swap/` (Go, binary at `/home/chief/bin/llama-swap`)
- super_council: `/home/chief/Coding-Projects/7-council/super_council/` (Python)
**Reference docs:** `/home/chief/llm-wiki/super-council-docs/04-delegation.md`
**Key files for this task:** Listed in "Files to Modify" below.

---

## What Is Done

### 1. `--slot-save-path` Flag Injection (`process_command.go`)

- **Status:** Working. Flag is injected into llama-server command when `SlotStore.Enabled` and `SlotSavePath` are set.
- **Evidence:** Process command line shows `--slot-save-path /home/chief/Coding-Projects/7-council/council-config/slots/qwen-160k-UD-fast`
- **Fix applied:** Added debug logging to diagnose condition failures.

**File:** `/home/chief/llama-swap/internal/process/process_command.go` (line 369)

### 2. SlotSavePath Bug Fix (`hook.go`)

- **Status:** Fixed. Was passing `SlotDir` (base dir) instead of `SlotSavePath` (per-model dir) to Store config.
- **Bug:** Store.Save() looked for `.bin` file in base `/slots/` instead of `/slots/qwen-160k-UD-fast/`.
- **Fix:** Changed `SlotDir: mc.SlotStore.SlotDir` → `SlotDir: mc.SlotStore.SlotSavePath` in `NewHook()`.

**File:** `/home/chief/llama-swap/internal/slotstore/hook.go` (line 30)

### 3. Build Errors Fixed (`store.go`)

- **Status:** Fixed.
  - `sha256.Sum256()` returns `[32]byte`, not `[]byte` — assigned to variable first, then sliced.
  - Missing `context` import added.

**File:** `/home/chief/llama-swap/internal/slotstore/store.go` (lines 199, 12)

### 4. Slot Save/Restore Verified

- **Status:** Working. Save fires on swap-out (BeforeStop), restore fires on swap-back (AfterReady).
- **Evidence from logs:**
  ```
  INFO slotstore: save complete model=qwen-160k-UD-fast slot=0 tokens=77259 bin_mb=2716.6 checksum=5b69bbd6d5...
  INFO slotstore: restore complete model=qwen-160k-UD-fast slot=0 tokens=77259 saved_at=... restored_at=...
  ```
- **Slot files:** `slot-0.bin` (2.7GB) + `slot-0.json` (metadata with checksum, tokens, timestamps) in per-model directory.

### 5. SwapHook Wiring

- **Status:** Working. `hook_council.go` compiled with `-tags council`, returns real slotstore hook (not no-op stub).
- **Flow:** `newBaseRouter` → `getSwapHook(cfg)` → `slotstore.NewHook(cfg)` → `hook{store: New(...)}`
- **BeforeStop/AfterReady** called from `base.go` lines 249, 277.

### 6. Council Delegate Wiring

- **Status:** Wired. `LlamaSwapClient.swap_to()` calls `GET /upstream/{model_id}` which triggers full swap lifecycle.
- **Flow:** `_delegate()` → `_swap_to_via_llama()` → `llama_client.swap_to(alias)` → llama-swap swap lifecycle.

---

## What Is Broken

### Target Model Startup Fails During Swap

**Symptom:** When swapping FROM qwen TO any other model, the target model exits with "upstream command exited prematurely". The swap aborts, qwen reloads, and slot restore fires successfully.

**Evidence:**
```
23:39:31 INFO slotstore: save complete model=qwen-160k-UD-fast slot=0 tokens=77259
23:39:32 WARN group: running mellum2-12b exited: upstream command exited prematurely
23:40:30 INFO slotstore: restore complete model=qwen-160k-UD-fast slot=0 tokens=77259
```

**Timeline:** Save completes → 1 second later target fails → qwen reloads → restore works.

**Hypothesis:** The target model OOMs because VRAM isn't fully released when the new model starts. The swap flow should be:
1. BeforeStop(save) → writes to disk while model still running
2. Stop old model → frees VRAM
3. Start new model → should have VRAM available

But the 1-second gap between save-complete and target-failed suggests either:
- CUDA memory release is delayed (driver-level issue)
- The swap logic doesn't wait for process exit before starting new model
- The target model config has incompatible settings (e.g., `-ngl 99` forces all layers on GPU)

**Models tested (all failed):**
- `nemotron-nano` (4B, 3.8GB file, `-ngl 40`)
- `mellum2-12b` (12B, 8.8GB file, `-ngl 99`)

**Manual test:** Running mellum2-12b WITHOUT `-ngl 99` (let auto-fit work) loaded successfully when VRAM was free.

---

## Investigation Required

### Priority 1: Why does target model startup fail?

**Steps:**

1. **Check swap timing in `base.go`:** Does the swap wait for old model process to fully exit (and VRAM released) before starting new model? Look for:
   - `Stop()` → `Wait()` → then `Start()`
   - Or `Stop()` → immediate `Start()` (race condition)

2. **Check CUDA memory release:** After stopping qwen, does `nvidia-smi` show VRAM freed immediately? There might be a delay where CUDA context is torn down asynchronously.

3. **Test with `-fit on`:** If `-ngl 99` forces all layers on GPU and VRAM isn't fully released, the model OOMs. Removing `-ngl` (or adding `-fit on`) lets llama.cpp auto-fit layers. But this is a workaround, not a root cause fix.

4. **Check if swap uses same port:** If the old model's port isn't released, the new model might fail to bind. Check port allocation in llama-swap.

5. **Check upstream process stdout/stderr:** The "exited prematurely" error is generic. The actual llama-server error (OOM, port conflict, file not found) is in the process stdout/stderr which isn't captured in journalctl. Add logging or check `/proc/PID/fd/`.

### Priority 2: Council Delegate End-to-End Test

Once swap works, test the full council delegate flow:

1. Start council_main (already running, PID 384703)
2. Call `/delegate` with target model alias
3. Verify: slot saved → swap → task executes → swap back → slot restored
4. Verify: conversation context preserved after swap-back

### Priority 3: Manual Slot Endpoints

The REST endpoints `POST /api/slots/save/{model}` and `POST /api/slots/restore/{model}` are TODO stubs (return 202 but don't call slotstore). Decide if they need to be wired or if the SwapHook is sufficient.

---

## Files to Modify

| Action | File | Purpose |
|--------|------|---------|
| Investigate | `/home/chief/llama-swap/internal/router/base.go` | Swap timing — does it wait for VRAM release? |
| Investigate | `/home/chief/llama-swap/internal/process/process_command.go` | Add upstream stdout/stderr capture for error diagnosis |
| Modify | `/home/chief/llama-swap/config.yaml` | May need `-fit on` or reduced `-ngl` for target models |
| Modify | `/home/chief/llama-swap/internal/slotstore/hook.go` | SlotSavePath fix already applied |
| Modify | `/home/chief/llama-swap/internal/process/process_command.go` | Debug logging already applied |
| Modify | `/home/chief/llama-swap/internal/slotstore/store.go` | Build fixes already applied |

## Constraints

- **Build tag:** Must build with `-tags council` or slotstore is a no-op stub.
- **Binary path:** `/home/chief/bin/llama-swap` (systemd service `llama-swap.service`).
- **Slot directory:** `/home/chief/Coding-Projects/7-council/council-config/slots/` (per-model subdirs required).
- **VRAM:** Single RTX 3090 (24GB). Only one model can run at a time. Swap MUST stop old model before starting new one.
- **Kill blocked:** `kill` command is blocked by council gate. Use `/api/models/unload/{model}` or council restart endpoints.

## Success Criteria

- [ ] Swap to ANY configured model succeeds (not just qwen)
- [ ] Slot save fires on swap-out (BeforeStop) with checksum validation
- [ ] Slot restore fires on swap-in (AfterReady) with token count matching saved state
- [ ] Council delegate flow works: save → swap → execute → swap-back → restore
- [ ] Slot files persist across llama-swap restarts
- [ ] No regression: qwen model still loads and serves correctly
- [ ] Upstream process errors are captured in logs (not just "exited prematurely")

## Caveats & Uncertainty

- **CUDA VRAM release timing:** May be asynchronous. If llama-swap starts new model before CUDA context is fully torn down, OOM occurs. May need explicit `cudaDeviceSynchronize()` or delay.
- **`-ngl 99` behavior:** Forces all layers on GPU. If VRAM isn't enough, model fails. Auto-fit (`-fit on`) may be needed for smaller VRAM scenarios.
- **Slot file ownership:** llama-swap runs as `chief` user. Slot files are owned by `chief`. If systemd service runs as different user, permissions may break.
- **Manual endpoints:** `POST /api/slots/save/{model}` is a stub. If council needs manual save/restore (not just swap-triggered), these need implementation.
