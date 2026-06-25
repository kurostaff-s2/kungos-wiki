# Council Main Fallback Removal — Option A: Thin Proxy

**Date**: 2026-06-19
**Task**: Remove all direct upstream fallback paths from council_main.py; make llama-swap the single source of truth for model lifecycle.
**Status**: Planned — ready for execution
**Parent**: Slot persistence investigation (15-llama-swap-slot-persistence-fix.md)

---

## Problem Statement

council_main.py maintains **dual-mode** operation:
- **Primary path**: llama-swap (port 9292) — manages model lifecycle, slot save/restore, request routing
- **Fallback path**: Direct llama-server (port 8081) — SlotClient + UpstreamProcess for direct subprocess management

The fallback is **broken**: nothing runs on port 8081, `self.upstream.running()` always returns False, `self.client` connections are refused. This creates silent failures in health checks, status APIs, and restart logic.

**Evidence**:
```
curl http://127.0.0.1:8090/api/status
→ {"error": "Upstream unavailable: Connection refused"}
```

---

## Architecture After Change

```
BEFORE (dual-mode):
  pi → council_main:8090 → self.client → llama-server:8081  (BROKEN)
  pi → council_main:8090 → self.llama_client → llama-swap:9292 → llama-server:10007  (WORKS)

AFTER (single-mode):
  pi → council_main:8090 → self.llama_client → llama-swap:9292 → llama-server:10007
```

council_main becomes a thin proxy: auth, logging, delegation logic, memory integration. All model lifecycle routes through llama-swap.

---

## Changes Required

### 1. Remove Classes (1,086 lines)

| Class | Lines | Purpose | Why Remove |
|-------|-------|---------|------------|
| `UpstreamProcess` | 1079–1726 (648) | Direct llama-server subprocess management | Replaced by llama-swap's Go process manager |
| `SlotClient` | 1727–2164 (438) | Direct HTTP client for llama-server | Replaced by LlamaSwapClient |

### 2. Remove Init Fields

**File**: `council_main.py` ~line 2883

```python
# REMOVE from __init__ params:
    upstream_host: str,          # → no longer needed
    upstream_port: int,          # → no longer needed
    upstream_config_path: Optional[str] = None,  # → keep for ModelRegistry only
    upstream_bin: str,           # → no longer needed

# REMOVE field assignments:
    self.upstream_host = upstream_host
    self.upstream_port = upstream_port
    self.upstream_config_path = upstream_config_path
    self.upstream_bin = upstream_bin
    self.client = SlotClient(f"http://{upstream_host}:{upstream_port}")
    self.upstream = UpstreamProcess(...)
```

**Keep**: `upstream_config_path` is still needed by `ModelRegistry` for model definitions.

### 3. Update `_post_chat_completion` (line 3543)

```python
# BEFORE:
def _post_chat_completion(self, payload: dict, timeout: float = 120.0) -> tuple:
    if self.llama_client and self.llama_client.is_available():
        return self.llama_client.chat_completion(payload, timeout=timeout)
    return self.client.post_json("/v1/chat/completions", payload, timeout=timeout)  # ← REMOVE

# AFTER:
def _post_chat_completion(self, payload: dict, timeout: float = 120.0) -> tuple:
    if self.llama_client and self.llama_client.is_available():
        return self.llama_client.chat_completion(payload, timeout=timeout)
    raise RuntimeError("llama-swap unavailable — no fallback (direct upstream removed)")
```

### 4. Update `_swap_to_via_llama` (lines 3496, 3513)

```python
# BEFORE:
if self.current_alias == alias and self.upstream.running():
    return

# AFTER:
if self.current_alias == alias and self._model_is_ready(alias):
    return

# NEW helper:
def _model_is_ready(self, alias: str) -> bool:
    """Check if model is ready via llama-swap."""
    if not self.llama_client or not self.llama_client.is_available():
        return False
    try:
        running = self.llama_client.get_running_models()
        return any(m.get("model") == alias and m.get("state") == "ready" for m in running)
    except Exception:
        return False
```

### 5. Update `_delegate` (line 4981)

```python
# BEFORE:
original_running = self.upstream.running()

# AFTER:
original_running = self._model_is_ready(self.current_alias) if self.current_alias else False
```

### 6. Rewrite `_restart_upstream` (lines 5708–5840)

Current implementation directly stops/starts llama-server subprocess. Replace with llama-swap operations:

```python
def _restart_upstream(self, payload: dict) -> dict:
    """Restart current model via llama-swap.

    Flow: save slot → swap away → swap back → verify healthy.
    """
    if not self.llama_client or not self.llama_client.is_available():
        return {"error": "llama-swap unavailable", "status": 503}

    if not self.current_alias:
        return {"error": "no current model to restart", "status": 400}

    # Save current slot
    try:
        self._save_current_slot()
    except Exception as e:
        log.warning("Failed to save slot before restart: %s", e)

    # Force restart by swapping away and back
    # Find a different model to swap to temporarily
    running = self.llama_client.get_running_models()
    # ... swap logic via llama_client.swap_to() ...
```

**Alternative**: If `_restart_upstream` is only called for crash recovery, consider delegating to llama-swap's built-in health check + auto-restart. May not need Python-side implementation at all.

### 7. Update Health/Metrics Endpoints

| Line | Current | Replace With |
|------|---------|--------------|
| 5797 | `self.client.get("/v1/health")` | `self.llama_client.get_health()` or `GET /running` |
| 5800 | `self.client.get("/v1/models")` | `self.llama_client.get_models()` |
| 7379 | `self.client.metrics()` | `self.llama_client.get_performance()` |
| 7847 | `self.client.post_json(...)` | `self.llama_client.chat_completion(...)` |
| 7863 | `self.client._parse_upstream_json(...)` | Parse response from llama_client directly |

### 8. Update CLI Args (lines 8998–9012)

```python
# REMOVE:
p.add_argument("--upstream-host", ...)
p.add_argument("--upstream-port", ...)
p.add_argument("--upstream-config", ...)
p.add_argument("--upstream-bin", ...)

# KEEP:
p.add_argument("--listen-host", ...)
p.add_argument("--listen-port", ...)
```

### 9. Update ModelRegistry (minimal)

ModelRegistry still needs `upstream_config_path` for model definitions. The `self.upstream` field in `ModelInfo` (line 613) is a string ID, not the UpstreamProcess — keep it.

**Remove from ModelInfo.__repr__** (line 613): The `"upstream": self.upstream` reference is fine (it's a string).

### 10. Remove Dead Code

| Lines | Content |
|-------|---------|
| 3200–3330 | `_swap_to_direct` (commented out but still present) |
| 3431, 3458 | Commented save/restore via self.client |
| 3214–3323 | Commented swap fallback logic |

---

## Files Modified

| File | Changes |
|------|---------|
| `super_council/council_main.py` | Remove ~1,100 lines, update ~15 methods |
| `super_council/api/llama_swap_client.py` | May need `get_running_models()`, `get_health()`, `get_models()` methods if not present |

---

## LlamaSwapClient — Missing Methods

Check if these exist in `llama_swap_client.py`. If not, add them:

| Method | Purpose | llama-swap Endpoint |
|--------|---------|---------------------|
| `get_running_models()` | Check model state | `GET /running` |
| `get_health()` | Health check | `GET /api/health` or `GET /running` |
| `get_models()` | List available models | `GET /api/models` |
| `chat_completion()` | ✅ Already exists | `POST /v1/chat/completions` |
| `swap_to()` | ✅ Already exists | `GET /upstream/{model}/` |
| `save_slot()` | ✅ Already exists | `POST /api/slots/save/{model}` |
| `restore_slot()` | ✅ Already exists | `POST /api/slots/restore/{model}` |
| `get_performance()` | ✅ Already exists | `GET /api/performance` |
| `get_slot_token_count()` | ✅ Already exists | `GET /slots` |

---

## Testing Strategy

### Pre-change baseline
```bash
# Verify current state
curl http://127.0.0.1:8090/api/status  # → should fail (upstream unavailable)
curl http://127.0.0.1:9292/running     # → should show qwen ready
# Send chat completion through council (should work via llama-swap path)
curl -X POST http://127.0.0.1:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-160k-UD-fast","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

### Post-change verification
1. **Startup**: council_main starts without errors, no "upstream unavailable" warnings
2. **Chat completion**: Routes through llama-swap (check logs)
3. **Swap**: `_swap_to(mellum2-12b)` works via llama-swap
4. **Delegation**: Full delegation cycle (swap → task → swap back) works
5. **Health check**: `/api/status` reports correct state via llama-swap
6. **Metrics**: `/api/metrics` returns data via llama-swap
7. **Restart**: `_restart_upstream` works via llama-swap (or is removed)

### Rollback
If anything breaks: `git revert` the council_main.py change. The fallback code is being removed, so rollback restores it.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| llama-swap goes down, no fallback | Low (systemd restart) | High (no model access) | Accept — single source of truth means single point of failure |
| Missing LlamaSwapClient methods | Medium | Medium | Audit before removal; add missing methods |
| `_restart_upstream` rewrite incomplete | Medium | High | Test thoroughly; consider removing if llama-swap handles restarts |
| ModelRegistry still needs upstream_config | Low | Low | Keep the param; only remove process management |
| Delegation broken during transition | Medium | High | Test full delegation cycle before declaring done |

---

## Execution Order

1. **Audit LlamaSwapClient** — verify all needed methods exist
2. **Add missing methods** — `get_running_models()`, `get_health()`, `get_models()`
3. **Add `_model_is_ready()` helper** — replacement for `self.upstream.running()`
4. **Update hot paths first** — `_post_chat_completion`, `_swap_to_via_llama`, `_delegate`
5. **Update health/metrics** — lines 5797, 5800, 7379, 7847, 7863
6. **Rewrite `_restart_upstream`** — or remove if not needed
7. **Remove classes** — UpstreamProcess, SlotClient
8. **Remove init fields** — upstream_host, upstream_port, upstream_bin, self.client, self.upstream
9. **Remove CLI args** — --upstream-host, --upstream-port, --upstream-config, --upstream-bin
10. **Clean dead code** — commented fallback sections
11. **Test** — full delegation cycle, swap, health check, metrics

---

## Decision Points

1. **Keep `upstream_config_path`?** YES — ModelRegistry needs it for model definitions. Only remove the process management aspect.

2. **Keep `_restart_upstream`?** MAYBE — if llama-swap has built-in restart/health recovery, this can be removed. Otherwise rewrite to use llama-swap API.

3. **Hard fail or graceful degradation?** Hard fail — if llama-swap is unavailable, council_main should error clearly rather than silently falling back to broken direct mode.

4. **Remove `--upstream-port` CLI arg or deprecate?** Remove — it's confusing to have a CLI arg that does nothing. If needed later, add it back with a clear error message.

---

## Next Steps

1. Execute the changes in the order above
2. Test thoroughly (especially delegation cycle)
3. If delegations are clean → done
4. If delegations still have issues → pivot to Option B (move delegation hook to llama-swap Go code)

---

## Critical Context

- **council_main**: `/home/chief/Coding-Projects/7-council/super_council/council_main.py`
- **LlamaSwapClient**: `/home/chief/Coding-Projects/7-council/super_council/api/llama_swap_client.py`
- **llama-swap**: `/home/chief/llama-swap/` (Go, port 9292)
- **llama-server**: port 10007 (Qwen), port 10004 (mellum2)
- **council_main**: port 8090
- **Running processes**: council_main PID 2027, llama-swap PID 108025, llama-server PID 99719
- **Slot dir**: `/home/chief/Coding-Projects/7-council/council-config/slots/qwen-160k-UD-fast/`
- **Config**: `/home/chief/llama-swap/config.yaml`
