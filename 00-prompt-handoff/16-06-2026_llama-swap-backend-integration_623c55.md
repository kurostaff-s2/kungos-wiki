# Phase 1A: Llama-Swap Backend Integration

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `75a031-p1a` |
| Entity type | `work_item` |
| Short description | Wire `LlamaSwapClient` into `SlotSupervisor` as optional model management layer with graceful fallback to direct process management |
| Status | `done` |
| Source references | `/home/chief/llm-wiki/00-prompt-handoff/16-06-2026_llama-swap-integration_75a031.md`, `/home/chief/llama-swap/`, `/home/chief/Coding-Projects/7-council/super_council/council_main.py` |
| Generated | `16-06-2026` |
| Next action / owner | Phase 1A complete. Ready for end-to-end testing with llama-swap running on :9292 |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/llm-wiki/00-prompt-handoff/16-06-2026_llama-swap-integration_75a031.md` (master plan)
**Related codebases:** `/home/chief/llama-swap/` (Go backend, branch `council-swaphook` at `kurostaff-s2/llama-swap`)
**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/super_council/council_main.py` — SlotSupervisor class, _swap_to, _save_current_slot, _restore_current_slot, _get_free_vram, _wait_for_vram
- `/home/chief/Coding-Projects/7-council/super_council/api/llama_swap_client.py` — LlamaSwapClient (already created)
- `/home/chief/Coding-Projects/7-council/super_council/api/test_llama_swap_client.py` — LlamaSwapClient tests (already created)

---

## What This Phase Delivers

Replace `SlotSupervisor`'s direct llama-server process management with `LlamaSwapClient` delegation to the llama-swap Go service. When llama-swap is running on `:9292`, all model swap operations route through its REST API (which handles process lifecycle, VRAM management, and KV cache persistence via SwapHook). When llama-swap is unavailable, fall back to existing direct process management (nvidia-smi, subprocess).

**Net effect:** ~970 lines of model management code (`UpstreamProcess`, `SlotStore`, `SlotClient`, `ModelRegistry`, `BinaryHashTracker`, swap orchestration) replaced by ~300 lines of `LlamaSwapClient` + delegation logic.

---

## Pre-Flight Checklist

- [ ] Phase 0 (Go Build Verification) is complete — llama-swap compiles in both modes
- [ ] `LlamaSwapClient` exists at `super_council/api/llama_swap_client.py`
- [ ] `LlamaSwapClient` tests pass: `pytest super_council/api/test_llama_swap_client.py -v`
- [ ] llama-swap branch `council-swaphook` pushed to `kurostaff-s2/llama-swap`

---

## Architecture Decision: Optional Delegation

**Pattern:** `LlamaSwapClient` is an optional component. `SlotSupervisor` checks if llama-swap is available at startup and routes accordingly.

**Why optional:** Graceful degradation. If llama-swap crashes or isn't running, the system continues with direct process management. No single point of failure.

**Dispatch logic:**
```python
# In SlotSupervisor.__init__:
self.llama_client: Optional[LlamaSwapClient] = None
try:
    self.llama_client = LlamaSwapClient(base_url=os.environ.get("LLAMA_SWAP_URL", "http://localhost:9292"))
    if self.llama_client.is_available():
        log.info("llama-swap available at %s — delegating model management", self.llama_client.base_url)
    else:
        self.llama_client = None  # not reachable, fall back
except Exception as e:
    log.warning("llama-swap unavailable (%s) — using direct process management", e)
    self.llama_client = None

# In _swap_to:
if self.llama_client and self.llama_client.is_available():
    return self._swap_to_via_llama(alias)
else:
    return self._swap_to_direct(alias)  # existing logic, renamed
```

---

## Implementation Steps

### Step 1: Add LlamaSwapClient import and initialization

**File:** `super_council/council_main.py`

1. Add import near top of file (with other imports):
```python
from super_council.api.llama_swap_client import LlamaSwapClient, LlamaSwapError
```

2. In `SlotSupervisor.__init__` (line ~2744), after `self.memory_service = MemoryService.load(...)`, add:
```python
# Llama-swap integration: optional delegation layer
self.llama_client: Optional[LlamaSwapClient] = None
try:
    llama_swap_url = os.environ.get("LLAMA_SWAP_URL", "http://localhost:9292")
    self.llama_client = LlamaSwapClient(base_url=llama_swap_url)
    if self.llama_client.is_available():
        log.info("llama-swap available at %s — delegating model management", llama_swap_url)
    else:
        self.llama_client = None
except Exception as e:
    log.warning("llama-swap unavailable (%s) — using direct process management", e)
    self.llama_client = None
```

### Step 2: Rename existing methods (preserve fallback logic)

**File:** `super_council/council_main.py`

Rename existing methods to make them explicit fallback paths:

| Current Name | New Name | Line |
|--------------|----------|------|
| `_swap_to` | `_swap_to_direct` | ~3039 |
| `_save_current_slot` | `_save_current_slot_direct` | ~3259 |
| `_restore_current_slot` | `_restore_current_slot_direct` | ~3300 |
| `_get_free_vram` | `_get_free_vram_direct` | ~2976 |
| `_wait_for_vram` | `_wait_for_vram_direct` | ~2991 |

**Search/replace pattern:** Use exact text replacement for each method definition. Update all internal call sites within the renamed methods (e.g., `_swap_to_direct` calls `_save_current_slot_direct`, not `_save_current_slot`).

### Step 3: Implement delegation wrapper methods

**File:** `super_council/council_main.py`

Add new public methods that dispatch to llama-swap or direct based on availability:

```python
def _swap_to(self, alias: str) -> None:
    """Swap to target model alias.

    Delegates to llama-swap if available; falls back to direct process management.
    """
    if self.llama_client and self.llama_client.is_available():
        return self._swap_to_via_llama(alias)
    return self._swap_to_direct(alias)

def _swap_to_via_llama(self, alias: str) -> None:
    """Swap via llama-swap REST API.

    Delegates full swap lifecycle to llama-swap:
    1. SwapHook.BeforeStop() — save KV cache of current model
    2. Stop current model
    3. Start target model
    4. SwapHook.AfterReady() — restore KV cache into new model

    Falls back to direct swap on error.
    """
    model = self.registry.get(alias)
    config = self.registry.get_config(alias)
    if not model or not config:
        raise KeyError(f"Unknown model alias: {alias}")

    if self.current_alias == alias and self.upstream.running():
        return

    # Swap guard: wait for prior swap
    if not self._swap_event.wait(timeout=30):
        raise TimeoutError(f"Swap to '{alias}' timed out waiting for prior swap")

    if not self._swap_lock.acquire(timeout=1):
        raise RuntimeError(f"Swap to '{alias}' blocked: could not acquire swap lock")
    self._swapping = True
    self._swap_event.clear()

    try:
        with self.lock:
            if self.fanout_in_progress:
                raise RuntimeError(f"Swap to '{alias}' blocked: fanout in progress")

            if self.current_alias == alias and self.upstream.running():
                self._clear_failure(alias)
                return

        # Delegate to llama-swap — handles save, stop, start, restore
        log.info("SWAP via llama-swap: %s -> %s", self.current_alias, alias)
        try:
            self.llama_client.swap_to(alias)
        except LlamaSwapError as e:
            log.warning("llama-swap swap failed (%s) — falling back to direct swap", e)
            self.lock.acquire()
            try:
                self._swap_to_direct(alias)
                return
            finally:
                self.lock.release()
            raise

        self.current_alias = alias
        self.current_signature = model.signature
        self._clear_failure(alias)
        self._inc_stat("swaps")

        # Log swap via memory service
        try:
            self.memory.log_swap(alias=alias, tokens_restored=0, restore_ms=0, cold_start=False)
        except Exception:
            pass

    except Exception:
        if self.current_alias == alias:
            self.current_alias = None
            self.current_signature = None
        raise
    finally:
        self._swapping = False
        self._swap_lock.release()
        self._swap_event.set()

def _save_current_slot(self) -> bool:
    """Save current slot. Delegates to llama-swap if available."""
    if self.llama_client and self.llama_client.is_available() and self.current_alias:
        try:
            self.llama_client.save_slot(self.current_alias)
            self._inc_stat("saves")
            return True
        except LlamaSwapError as e:
            log.warning("llama-swap save failed (%s) — falling back", e)
    return self._save_current_slot_direct()

def _restore_current_slot(self, prefer_signature: Optional[str] = None) -> bool:
    """Restore current slot. Delegates to llama-swap if available."""
    if self.llama_client and self.llama_client.is_available() and self.current_alias:
        try:
            self.llama_client.restore_slot(self.current_alias)
            return True
        except LlamaSwapError as e:
            log.warning("llama-swap restore failed (%s) — falling back", e)
    return self._restore_current_slot_direct(prefer_signature)

def _get_free_vram(self) -> Optional[int]:
    """Get free VRAM. Delegates to llama-swap if available."""
    if self.llama_client and self.llama_client.is_available():
        try:
            vram = self.llama_client.get_free_vram()
            return int(vram.free_vram_mb) if vram.free_vram_mb > 0 else None
        except LlamaSwapError:
            pass
    return self._get_free_vram_direct()

def _wait_for_vram(self) -> bool:
    """Wait for VRAM. Delegates to llama-swap if available."""
    if self.llama_client and self.llama_client.is_available():
        # Estimate required VRAM from current model config
        required_mb = CUDA_VRAM_HEADROOM  # use existing constant
        return self.llama_client.wait_for_vram(
            required_mb=required_mb,
            timeout=CUDA_VRAM_POLL_TIMEOUT,
            poll_interval=CUDA_VRAM_POLL_INTERVAL,
        )
    return self._wait_for_vram_direct()
```

### Step 4: Update call sites

**File:** `super_council/council_main.py`

Search for any remaining calls to the old method names (outside the renamed methods) and update:
- `_swap_to` → no change (this is the public delegation wrapper)
- `_save_current_slot` → no change (delegation wrapper)
- `_restore_current_slot` → no change (delegation wrapper)
- `_get_free_vram` → no change (delegation wrapper)
- `_wait_for_vram` → no change (delegation wrapper)

**Note:** The public method names stay the same. Only the internal implementation was renamed to `*_direct`. The delegation wrappers use the original names.

### Step 5: Add environment variable documentation

**File:** `super_council/council_main.py` (docstring or comment block)

Add to module docstring or `SlotSupervisor` class docstring:

```
Environment Variables:
  LLAMA_SWAP_URL — llama-swap REST API base URL (default: http://localhost:9292)
                   Set to empty string to disable llama-swap delegation.
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/council_main.py` | Add LlamaSwapClient import, initialization, delegation methods, rename fallback methods |

---

## Phase-Specific Tests

1. **Test delegation when llama-swap is available:** Mock `LlamaSwapClient.is_available()` → True, verify `_swap_to` calls `llama_client.swap_to(alias)`
2. **Test fallback when llama-swap is unavailable:** Mock `LlamaSwapClient.is_available()` → False, verify `_swap_to` calls `_swap_to_direct(alias)`
3. **Test fallback on LlamaSwapError:** Mock `llama_client.swap_to()` → raises `LlamaSwapError`, verify fallback to `_swap_to_direct`
4. **Test VRAM delegation:** Mock `llama_client.get_free_vram()` → returns `GPUStats`, verify `_get_free_vram` returns correct value
5. **Test slot save/restore delegation:** Mock `llama_client.save_slot()` and `llama_client.restore_slot()`, verify delegation
6. **Test environment variable:** Set `LLAMA_SWAP_URL` to custom value, verify client connects to correct URL
7. **Test disabled delegation:** Set `LLAMA_SWAP_URL=""`, verify `self.llama_client` is None

**Test file:** `super_council/test_llama_swap_integration.py` (new)

---

## Completion Gate

- [ ] `LlamaSwapClient` imported and initialized in `SlotSupervisor.__init__`
- [ ] Existing methods renamed to `*_direct` variants
- [ ] Delegation wrapper methods implemented (`_swap_to`, `_save_current_slot`, `_restore_current_slot`, `_get_free_vram`, `_wait_for_vram`)
- [ ] Fallback logic tested (llama-swap unavailable → direct management)
- [ ] Error handling tested (LlamaSwapError → fallback to direct)
- [ ] All existing tests still pass (no regression)
- [ ] New integration tests pass
- [ ] Files committed

---

## Notes for Next Phase

- Phase 2 (frontend types + SSE hook) is independent of this phase — can proceed in parallel
- After this phase completes, verify llama-swap is running and test end-to-end swap flow
- The `UpstreamProcess`, `SlotStore`, `SlotClient`, `ModelRegistry`, `BinaryHashTracker` classes are **preserved** as fallback — removal is a future refactoring phase (not this one)

---

## Caveats & Uncertainty

1. **Swap lifecycle difference:** llama-swap's SwapHook handles KV cache save/restore automatically. The direct fallback still uses Python-side SlotStore. This means slot behavior differs between the two paths — acceptable for now, but should be reconciled in future.

2. **Concurrent swap guard:** The existing `_swap_lock` and `_swap_event` mechanism is preserved. llama-swap has its own internal locking, so there's double-locking when both are active — harmless but worth noting.

3. **Model registry:** `SlotSupervisor` still uses `ModelRegistry` (Python) for model lookup. llama-swap has its own config.yaml. For full delegation, model config would need to be unified — not in this phase.

4. **Error recovery:** If llama-swap crashes mid-swap, the fallback may not have clean state. The existing `_swap_to_direct` error handling should cover this, but needs testing.

5. **Port conflicts:** llama-swap runs on `:9292` by default. Ensure no other service uses this port.
