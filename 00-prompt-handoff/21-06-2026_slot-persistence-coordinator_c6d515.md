# Slot Persistence Coordinator — Super Council Implementation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `c6d515` |
| Entity type | `handoff` |
| Short description | Thin Go service that coordinates KV cache slot persistence across llama.cpp router model swaps |
| Status | `draft` |
| Source references | `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py`, `/home/chief/llama-swap/config.yaml` |
| Generated | `21-06-2026` |
| Next action / owner | Execute Phase 1 (skeleton), then proceed sequentially |

## Summary

Replace the unreliable `llama-swap` proxy with a thin Go coordinator that plugs into the native `llama.cpp` router mode. The router (`/home/chief/main-llama/llama.cpp`) handles model loading/unloading and request routing. The coordinator handles **only** slot persistence: saving KV cache before unload, restoring after load.

The arc-router (SYCL fork, port 18093) is exclusive and independent — it is NOT part of this implementation. This coordinator is a separate super-council service that works with the main llama.cpp router.

## Architecture

```
Client → [router:main-llama] → [child-server:dynamic_port:llama-server]
              ↑                    ↑
       SSE stream (real-time)   /slots/0?action=save/restore
              │                    │
       [slot-persistor:Go] ────────┘
              │
       /home/chief/tmp/llama-slots/<alias>/<config_hash>/slot-0.bin
```

**Roles:**
- **router** (main-llama build): Manages model loading/unloading, request routing. Exposes SSE stream for state changes. Independent of super-council.
- **child-server** (dynamic port): Runs llama-server with `--slot-save-path`. Exposes `/slots/{id}?action=save/restore`.
- **slot-persistor** (Go, super-council): Subscribes to router SSE stream, coordinates save→unload→load→restore cycle.

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py` — legacy Python supervisor (reference for slot logic, config hash, metadata sidecar)
- `/home/chief/llama-swap/config.yaml` — current llama-swap config (model definitions, slot settings)
- `/home/chief/main-llama/llama.cpp/tools/server/` — main build server source (router API, slot endpoints)
- `/home/chief/main-llama/llama.cpp/build/bin/llama-server` — router binary

**Related codebases:**
- `/home/chief/main-llama/llama.cpp/` — main llama.cpp build (router binary)

## Constraints

- **Single slot only:** All models serialize through one GPU; `id_slot=0` always.
- **Per-model, per-config namespace:** Slot bins stored in `<alias>/<config_hash>/` to prevent cross-model KV corruption.
- **Binary hash tracking:** Purge all slots on llama-server binary change (prevents incompatible restores).
- **Metadata sidecar:** `.json` file validates model signature before restore.
- **No proxy:** The Go service does NOT proxy HTTP requests. It only coordinates slot persistence.
- **SSE primary:** Use `GET /v1/router/models/sse` for real-time model state changes.
- **Slot save before unload:** Must save slot state BEFORE calling `POST /v1/router/models/unload`.
- **Slot restore after load:** Must restore slot state AFTER SSE `model_status` event with `loaded` state.
- **arc-router is independent:** The SYCL fork (port 18093) is NOT part of this implementation. Use main-llama router.

## Caveats & Uncertainty

1. **SSE event format:** Verify the exact SSE event format (event name, data structure) from the main build's router. The `notify_sse` function in `server-models.cpp` sends `model_status` events.

2. **Swap interception:** The coordinator wraps the router's load/unload commands. It receives swap requests, saves slot, then calls `POST /v1/router/models/unload`, then `POST /v1/router/models/load`, then restores slot.

3. **Slot save timing:** The `/slots/{id}?action=save` endpoint must be called while the model is still loaded. If called after unload, it returns an error.

4. **MTP model compatibility:** Multi-token prediction models may have draft cache incompatibilities during slot restore. Consider disabling slot restore for MTP models (check `--spec-type` in model config).

5. **VRAM management:** The router handles LRU eviction and `models_max`. The coordinator doesn't manage VRAM — it trusts the router's model lifecycle.

## Implementation Units

### Phase 1: Go Service — Core Skeleton

**What:** Create the Go service skeleton with HTTP client, SSE subscriber, and slot directory management.

**Files:**
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/main.go`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/go.mod`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/config.yaml`

**Steps:**
1. Initialize Go module: `go mod init slot-persistor`.
2. Create `config.yaml` with router URL, slot directory, llama binary path, and model list.
3. Implement HTTP client for router (`GET /v1/models`, `POST /v1/router/models/load`, `POST /v1/router/models/unload`) and child servers (`POST /slots/{id}?action=save/restore`).
4. Implement SSE subscriber for `GET /v1/router/models/sse` — parse `model_status` events, extract model name, status, and child server port.
5. Implement slot directory management: `<alias>/<config_hash>/slot-0.bin` + `.json` metadata sidecar.
6. Implement binary hash tracking: compute SHA-256 of llama-server binary, purge slots on change.
7. Implement config hash computation: SHA-256 of model path, ctx_size, ngl, cache types, flash attention.

**Config structure:**
```yaml
router:
  url: "http://127.0.0.1:18093"

slot_dir: "/home/chief/tmp/llama-slots"

llama_bin: "/home/chief/main-llama/llama.cpp/build/bin/llama-server"

models:
  - alias: "LFM2-2.6B-Transcript-Q8_0"
    model_path: "/home/chief/models/LFM2-2.6B-Transcript-Q8_0.gguf"
    ctx_size: 32768
    ngl: 99
    cache_type_k: "q8_0"
    cache_type_v: "q8_0"
    flash_attention: true
```

**Tests:**
- [ ] Service starts and connects to router SSE stream
- [ ] SSE events parsed correctly (model name, status, child port)
- [ ] Model state detection works (loaded/unloaded transitions)
- [ ] Config hash computation matches expected values
- [ ] Binary hash tracking detects binary changes

**Dependencies:** None.

---

### Phase 2: Slot Persistence Logic

**What:** Implement the save→unload→load→restore cycle.

**Files:**
- Modify: `/home/chief/Coding-Projects/7-council/slot-persistor/main.go`

**Steps:**
1. Implement `saveSlot(alias, childPort)` — call `POST /slots/0?action=save` on child server, write metadata sidecar.
2. Implement `restoreSlot(alias, childPort)` — read metadata sidecar, validate signature, call `POST /slots/0?action=restore`.
3. Implement `swapModel(fromAlias, toAlias)` — the core swap logic:
   a. Get current model's child port from router (`GET /v1/models`).
   b. Save slot on current child server.
   c. Call `POST /v1/router/models/unload` to unload current model.
   d. Call `POST /v1/router/models/load` to load new model.
   e. Wait for SSE `model_status` event with `loaded` state for new model.
   f. Get new model's child port from `/v1/models`.
   g. Restore slot on new child server.
4. Implement metadata sidecar: `{alias, config_hash, model_signature, timestamp, n_saved}`.
5. Implement restore validation: check metadata exists, config hash matches, model signature matches.
6. Implement error handling: retry restore with backoff, log failures, continue on error.

**Swap flow:**
```
1. Client requests swap to "model-B" (via HTTP endpoint or CLI)
2. Coordinator: GET /v1/models → find current model (model-A) and its port
3. Coordinator: POST /slots/0?action=save on model-A's port
4. Coordinator: write metadata sidecar
5. Coordinator: POST /v1/router/models/unload for model-A
6. Coordinator: POST /v1/router/models/load for model-B
7. Coordinator: wait for SSE event: model-B status=loaded
8. Coordinator: GET /v1/models → find model-B's port
9. Coordinator: POST /slots/0?action=restore on model-B's port
10. Coordinator: validate restore (n_restored matches n_saved)
```

**Tests:**
- [ ] Slot save returns valid response with `n_saved` count
- [ ] Metadata sidecar written correctly
- [ ] Slot restore validates metadata before restoring
- [ ] Full swap cycle works (save→unload→load→restore)
- [ ] Error handling: restore fails gracefully on missing metadata

**Dependencies:** Phase 1 (Go service skeleton).

---

### Phase 3: Swap Command Interface

**What:** Provide an interface for triggering model swaps with slot persistence.

**Files:**
- Modify: `/home/chief/Coding-Projects/7-council/slot-persistor/main.go`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/cmd/swap.go`

**Steps:**
1. Implement HTTP endpoint: `POST /swap?alias=<target>` — triggers swap with slot persistence.
2. Implement CLI command: `slot-persistor swap <alias>` — same logic, CLI interface.
3. Implement swap state tracking: prevent concurrent swaps, queue requests during active swap.
4. Implement swap logging: structured logs for save/restore timing, token counts, errors.
5. Implement health endpoint: `GET /health` — reports coordinator status, current model, last swap time.

**Tests:**
- [ ] HTTP endpoint accepts swap requests
- [ ] CLI command triggers swap
- [ ] Concurrent swaps are serialized (not parallel)
- [ ] Health endpoint reports accurate state
- [ ] Swap logging includes timing and token counts

**Dependencies:** Phase 2 (slot persistence logic).

---

### Phase 4: Production Wiring

**What:** Wire the coordinator into production, decommission llama-swap.

**Files:**
- Create: `/etc/systemd/system/slot-persistor.service`
- Modify: `super_council` config (update model endpoint from llama-swap to router)

**Steps:**
1. Build Go binary: `go build -o slot-persistor ./...`
2. Create systemd service unit:
   ```ini
   [Unit]
   Description=Slot Persistence Coordinator
   After=network-online.target

   [Service]
   ExecStart=/home/chief/Coding-Projects/7-council/slot-persistor/slot-persistor --config /home/chief/Coding-Projects/7-council/slot-persistor/config.yaml
   Restart=on-failure
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```
3. Start `slot-persistor.service`, verify it's running and healthy.
4. Test swap: `curl -X POST http://127.0.0.1:9293/swap?alias=<target>`
5. Verify slot was saved and restored correctly (token count match).
6. Stop and disable `llama-swap.service`.
7. Update `super_council` config to point to router instead of llama-swap.

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] `slot-persistor.service` starts and reports healthy
- [ ] Swap via HTTP endpoint works end-to-end
- [ ] Slot save/restore preserves conversation context (verify token count)
- [ ] `llama-swap.service` stopped and disabled
- [ ] `super_council` can reach models via router
- [ ] No regression in existing services

**Dependencies:** Phase 3 (swap command interface).

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/main.go` | Go service entry point |
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/go.mod` | Go module definition |
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/config.yaml` | Service configuration |
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/cmd/swap.go` | Swap command/endpoint |
| Create | `/etc/systemd/system/slot-persistor.service` | Systemd service unit |
| Modify | `super_council` config | Update model endpoint from llama-swap to router |

## Success Criteria

- [ ] Slot persistence coordinator runs as systemd service
- [ ] Model swaps preserve KV cache (slot save before unload, restore after load)
- [ ] Per-model, per-config slot namespaces prevent cross-model corruption
- [ ] Binary hash tracking purges slots on llama-server binary change
- [ ] Metadata sidecars validate model signature before restore
- [ ] Swap endpoint serializes concurrent requests
- [ ] `llama-swap.service` decommissioned (stopped, disabled)
- [ ] `super_council` points to router instead of llama-swap
- [ ] No regression in existing services
- [ ] End-to-end swap tested: save→unload→load→restore with token count verification

## Test Requirements

### Phase-Specific Tests

1. **SSE subscription:** Verify SSE stream connects and sends `model_status` events.
2. **Slot save/restore:** Verify KV cache is saved and restored correctly (token count match).
3. **Config hash:** Verify config hash computation matches expected values.
4. **Binary hash:** Verify slot purge on binary change.
5. **Swap cycle:** Full save→unload→load→restore cycle with timing and token count verification.
6. **Concurrency:** Verify concurrent swap requests are serialized.
7. **Error handling:** Verify graceful degradation on missing metadata, failed restores.

### Integration Tests

1. **End-to-end swap:** Trigger swap via HTTP endpoint, verify slot persistence.
2. **Super-council compatibility:** Verify super-council can reach models via router after llama-swap decommission.
3. **Service health:** Verify all services (router, slot-persistor, memory-service) are healthy.

## Notes for Execution

- **Keep it thin:** The Go service should be ~200-300 lines. No proxy, no model lifecycle management.
- **Reuse existing logic:** The Python slot-supervisor.py has the slot directory structure, config hash, and metadata sidecar logic. Port this to Go.
- **Test incrementally:** Verify each phase before proceeding. Don't skip verification.
- **SSE is primary:** Use SSE stream for model state changes. The main build has full SSE support.
- **arc-router is independent:** Do NOT touch the SYCL fork (port 18093). It's exclusive and independent.
- **Decommission llama-swap last:** Only after the coordinator is verified working.
