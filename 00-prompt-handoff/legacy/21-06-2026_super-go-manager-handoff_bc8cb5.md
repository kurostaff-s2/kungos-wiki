# Super Go Manager — Slot Persistence Coordinator for Super Council

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `bc8cb5` |
| Entity type | `handoff` |
| Short description | Go service that coordinates KV cache slot persistence across super-router model swaps |
| Status | `implemented` |
| Source references | `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py` (legacy Python, logic reference) |
| Generated | `21-06-2026` |
| Next action / owner | Verify full swap cycle (save→load→restore) after GPU frees |

## Summary

Replaced the `llama-swap` proxy with two new super-council components:

1. **super-router** — llama.cpp router mode using `/home/chief/main-llama/llama.cpp/build/bin/llama-server`. Handles model loading/unloading and request routing. Runs on RTX 3090 (port 18094). Independent of arc-router.
2. **super-go-manager** — Go service that proxies chat completions with automatic slot persistence: saving KV cache before model change, restoring after load. Polls router state (no SSE).

The arc-router (SYCL fork, port 18093) is exclusive and independent — it runs on Intel ARC GPU and is NOT part of this implementation.

## Architecture

```
Client → [super-go-manager:9293] → [super-router:18094] → [child-server:dynamic_port]
              │                              │
              │                       /v1/models (poll)
              │                              │
              └── /slots/0?action=save/restore (direct to child)
              │
              /home/chief/tmp/llama-slots/<alias>/<config_hash>/slot-0.bin
```

**Roles:**
- **super-router** (main-llama build, port 18094): Manages model loading/unloading via LRU eviction. Models load on-demand via chat requests. No explicit load/unload/SSE endpoints.
- **child-server** (dynamic port): Runs llama-server with `--slot-save-path`. Exposes `/slots/{id}?action=save/restore`.
- **super-go-manager** (Go, port 9293): Proxies `/v1/chat/completions`, auto-detects model changes, coordinates save→load→restore cycle. Polls `/v1/models` for state.

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py` — legacy Python supervisor (reference for slot logic, config hash, metadata sidecar, binary hash tracking)
- `/home/chief/Coding-Projects/7-council/super-go-manager/main.go` — **actual implementation** (Go service, ~800 lines)
- `/home/chief/Coding-Projects/7-council/super-go-manager/config.yaml` — service configuration
- `/home/chief/models/super-router/models.ini` — super-router model presets (9 models)

**Related codebases:**
- `/home/chief/main-llama/llama.cpp/` — main llama.cpp build (super-router binary)

## Constraints

- **Single slot only:** All models serialize through one GPU; `id_slot=0` always.
- **Per-model, per-config namespace:** Slot bins stored in `<alias>/<config_hash>/` to prevent cross-model KV corruption.
- **Binary hash tracking:** Purge all slots on llama-server binary change (prevents incompatible restores). See `BinaryHashTracker` in main.go.
- **Metadata sidecar:** `.json` file validates model signature before restore. See `SlotMeta` in main.go.
- **Chat proxy with auto-swap:** super-go-manager proxies `/v1/chat/completions` and auto-saves slot on model change. No explicit swap command needed for normal operation.
- **Poll-based state:** Router has NO SSE endpoint (`/v1/router/models/sse` does not exist). State discovered via `GET /v1/models` polling.
- **No explicit load/unload:** Router loads models on-demand via chat requests. LRU eviction handles unloading (models-max=2).
- **Slot save before swap:** Must save slot state BEFORE forwarding request to new model.
- **Slot restore after response:** Restore happens after non-streaming response completes (streaming restores are deferred).
- **super-router is new:** Fresh router instance using main-llama build. Independent of arc-router.
- **GPU separation:** super-router uses RTX 3090; arc-router uses Intel ARC. No VRAM conflict.

## Implementation Details

### Router API (actual, not speculative)

The main-llama build's router mode exposes:
- `GET /v1/models` — model list with status and child server ports (in `status.args`)
- `GET /v1/health` — health check
- `POST /v1/chat/completions` — chat completions (triggers model load on-demand)

**No explicit endpoints exist for:**
- `POST /v1/router/models/load` — does NOT exist
- `POST /v1/router/models/unload` — does NOT exist
- `GET /v1/router/models/sse` — does NOT exist

### Slot Save/Restore Flow

```
1. Client sends POST /v1/chat/completions to super-go-manager (:9293)
2. super-go-manager detects model change (alias != current)
3. If current model has slot persistence: POST /slots/0?action=save on current child
4. Write metadata sidecar (SlotMeta) with checksum
5. Forward request to super-router (:18094)
6. Super-router loads new model on-demand (LRU evicts if needed)
7. For non-streaming: read full response, write to client, then restore slot
8. For streaming: copy response directly (restore deferred)
```

### Key Go Types (main.go)

| Type | Purpose |
|------|---------|
| `RouterClient` | HTTP client for super-router (`GET /v1/models`, `POST /v1/chat/completions`) |
| `SlotClient` | HTTP client for child servers (`POST /slots/0?action=save/restore`) |
| `SlotStore` | Slot directory management, metadata sidecars, checksum validation |
| `BinaryHashTracker` | SHA-256 of llama-server binary, purges slots on change |
| `Manager` | Orchestrator: swap logic, HTTP handlers, poll loop |
| `SlotMeta` | Metadata sidecar: `{model_alias, model_signature, config_hash, saved_at, slot_tokens, slot_checksum}` |

### Config Hash Computation

From `ComputeConfigHash()` in main.go:
```go
configStr := fmt.Sprintf("%s\nctx_size=%d\nngl=%d\nctk=%s\nctv=%s\nfa=%d\n",
    modelPath, ctxSize, ngl, cacheTypeK, cacheTypeV, flashAttention)
hash := sha256.Sum256([]byte(configStr))[:16]
```

### Binary Hash Tracking

From `BinaryHashTracker` in main.go:
- Computes SHA-256 of `/home/chief/main-llama/llama.cpp/build/bin/llama-server`
- Stores hash in `<slot_dir>/.llama_server_binary_hash`
- On mismatch: purges all slot directories, writes new hash
- Reference: `slot-supervisor.py` lines 1-100 (same logic in Python)

### Metadata Sidecar

From `SlotStore.WriteMeta()` in main.go:
- Atomic write: `.json.tmp` → rename to `.json`
- Contains: model alias, config hash, model signature, timestamp, token count, bin checksum
- Validated before restore: config hash match, checksum match

### Swap Serialization

From `Manager.SwapModel()` in main.go:
- `sync.Mutex` prevents concurrent swaps
- `swapping` bool tracks in-progress state
- Returns error if swap already in progress

## Services

| Service | Port | Status | Systemd |
|---------|------|--------|---------|
| super-router | 18094 | ✅ running | `systemctl --user super-router.service` |
| super-go-manager | 9293 | ✅ running | `systemctl --user super-go-manager.service` |
| arc-router | 18093 | ✅ running (independent) | `systemctl --user arc-router.service` |

## Wiring (Completed)

### Pi Configuration

- **`/home/chief/.pi/agent/models.json`** — `llama-swap` provider updated:
  - `baseUrl: "http://127.0.0.1:9293/v1"` (was `:9292`)
  - Provider name kept as `llama-swap` for backward compatibility

### Super Council Configuration

- **`/home/chief/Coding-Projects/7-council/super_council/upstream-config.json`** — `_note` fields updated:
  - `mellum2-12b`: "served by super-router via super-go-manager (:9293), not direct spawn"
  - `nex-n2-mini`: "served by super-router via super-go-manager (:9293), not direct spawn"

### Decommissioned

- **`llama-swap.service`** — disabled and removed via `systemctl --user disable`

## Bug Fix: Body Consumption in Chat Proxy (2026-06-21)

### Problem

All proxied chat requests returned **502 Bad Gateway** with no body. Journal logs showed:

```
http: proxy error: net/http: HTTP/1.x transport connection broken: http: ContentLength=338928 with Body length 0
```

### Root Cause

In `handleChatCompletions` (main.go ~line 548), the request body was read with `io.ReadAll(r.Body)` to extract the `model` field for slot persistence logic. This **consumed the body**. When `reverseProxy.ServeHTTP()` was called afterward, it forwarded the request with the original `Content-Length` header (e.g., 338928 bytes) but an **empty body** (0 bytes). The upstream super-router rejected the mismatch, breaking the connection.

### Fix

Two-line change in `main.go`:

1. Added `"bytes"` to imports
2. Added body restoration after reading:
   ```go
   r.Body = io.NopCloser(bytes.NewReader(body))
   ```

This restores the consumed body as a `bytes.Reader` wrapped in `io.NopCloser`, so the reverse proxy can forward the full request with matching `Content-Length`.

### Verification

- Health check: ✅ 200
- Non-streaming chat: ✅ 200, response returned correctly
- Streaming chat: ✅ SSE chunks flowing through `FlushInterval: 1ms`
- No proxy errors in journal since restart

### Impact

The low-latency streaming architecture (`FlushInterval: 1ms`, `MaxIdleConns: 5`, `MaxIdleConnsPerHost: 2`) was already correctly configured — it just couldn't fire because every request failed at the body level. This fix unblocks the entire proxy path.

## Remaining Work

### GPU-Blocked Verification

The RTX 3090 is occupied by the current council session (~22GB VRAM). The following tests require GPU availability:

1. **Full swap cycle:** Trigger swap via `POST /swap?alias=qwen3.6-35b-a3b`, verify slot save→load→restore
2. **Slot persistence:** Verify conversation context preserved across model swaps (token count match)
3. **Streaming restore:** Verify streaming responses work correctly with deferred restore
4. **Super-council integration:** Verify super-council can reach models via super-go-manager after full switch

### Post-GPU-Free Steps

1. Kill current llama-server on RTX 3090
2. Test model load on super-router (should succeed with free VRAM)
3. Test full swap cycle: `curl -X POST "http://127.0.0.1:9293/swap?alias=qwen3.6-35b-a3b"`
4. Verify slot save/restore preserves conversation context
5. Update any remaining configs that reference old ports

## Success Criteria

- [x] super-router runs on port 18094 with 9 models registered
- [x] super-go-manager runs as systemd service, polls super-router
- [x] Chat proxy forwards requests to super-router
- [x] Body consumption bug fixed (502 → 200) — `r.Body = io.NopCloser(bytes.NewReader(body))`
- [x] Non-streaming and streaming paths verified end-to-end
- [x] Slot save works on child server (verified via API)
- [x] Metadata sidecars written with checksum validation
- [x] Binary hash tracking detects binary changes
- [x] Swap endpoint serializes concurrent requests
- [x] `llama-swap.service` decommissioned (stopped, disabled)
- [x] Pi models.json updated to point to super-go-manager (:9293)
- [x] super_council upstream-config.json updated
- [ ] End-to-end swap tested: save→load→restore with token count verification (GPU blocked)
- [ ] No regression in existing services (pending full switch)

## References

- **Legacy slot logic:** `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py` — Python reference for slot directory structure, config hash, metadata sidecar, binary hash tracking
- **Legacy slot logic (backup):** `/home/chief/Coding-Projects/7-council/docs/slot-supervisor-legacy.py` — older version, less relevant
- **Go implementation:** `/home/chief/Coding-Projects/7-council/super-go-manager/main.go` — actual implementation
- **Go config:** `/home/chief/Coding-Projects/7-council/super-go-manager/config.yaml` — service configuration
- **Router models:** `/home/chief/models/super-router/models.ini` — 9 model presets
- **Pi models:** `/home/chief/.pi/agent/models.json` — provider configuration (updated to :9293)
- **Super council config:** `/home/chief/Coding-Projects/7-council/super_council/upstream-config.json` — model serving notes (updated)
