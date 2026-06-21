# Super Go Manager — Slot Persistence Coordinator for Super Council

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `bc8cb5` |
| Entity type | `handoff` |
| Short description | Thin Go service that coordinates KV cache slot persistence across super-router model swaps |
| Status | `draft` |
| Source references | `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py`, `/home/chief/llama-swap/config.yaml` |
| Generated | `21-06-2026` |
| Next action / owner | Execute Phase 1 (super-router setup), then proceed sequentially |

## Summary

Replace the unreliable `llama-swap` proxy with two new super-council components:

1. **super-router** — llama.cpp router mode using `/home/chief/main-llama/llama.cpp/build/bin/llama-server`. Handles model loading/unloading and request routing. Independent of arc-router.
2. **super-go-manager** — Thin Go service that coordinates slot persistence: saving KV cache before unload, restoring after load. Subscribes to super-router's SSE stream.

The arc-router (SYCL fork, port 18093) is exclusive and independent — it is NOT part of this implementation and is not referenced here.

## Architecture

```
Client → [super-router:main-llama] → [child-server:dynamic_port:llama-server]
                  ↑                        ↑
           SSE stream (real-time)      /slots/0?action=save/restore
                  │                        │
           [super-go-manager:Go] ──────────┘
                  │
           /home/chief/tmp/llama-slots/<alias>/<config_hash>/slot-0.bin
```

**Roles:**
- **super-router** (main-llama build): Manages model loading/unloading, request routing. Exposes SSE stream for state changes. Independent super-council service.
- **child-server** (dynamic port): Runs llama-server with `--slot-save-path`. Exposes `/slots/{id}?action=save/restore`.
- **super-go-manager** (Go, super-council): Subscribes to super-router SSE stream, coordinates save→unload→load→restore cycle.

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py` — legacy Python supervisor (reference for slot logic, config hash, metadata sidecar)
- `/home/chief/llama-swap/config.yaml` — current llama-swap config (model definitions, slot settings)
- `/home/chief/main-llama/llama.cpp/tools/server/` — main build server source (router API, slot endpoints)
- `/home/chief/main-llama/llama.cpp/build/bin/llama-server` — super-router binary

**Related codebases:**
- `/home/chief/main-llama/llama.cpp/` — main llama.cpp build (super-router binary)

## Constraints

- **Single slot only:** All models serialize through one GPU; `id_slot=0` always.
- **Per-model, per-config namespace:** Slot bins stored in `<alias>/<config_hash>/` to prevent cross-model KV corruption.
- **Binary hash tracking:** Purge all slots on llama-server binary change (prevents incompatible restores).
- **Metadata sidecar:** `.json` file validates model signature before restore.
- **No proxy:** super-go-manager does NOT proxy HTTP requests. It only coordinates slot persistence.
- **SSE primary:** Use `GET /v1/router/models/sse` for real-time model state changes.
- **Slot save before unload:** Must save slot state BEFORE calling `POST /v1/router/models/unload`.
- **Slot restore after load:** Must restore slot state AFTER SSE `model_status` event with `loaded` state.
- **super-router is new:** Fresh router instance using main-llama build. Independent of arc-router.

## Caveats & Uncertainty

1. **SSE event format:** Verify the exact SSE event format (event name, data structure) from the main build's router. The `notify_sse` function in `server-models.cpp` sends `model_status` events.

2. **Swap interception:** super-go-manager wraps super-router's load/unload commands. It receives swap requests, saves slot, then calls `POST /v1/router/models/unload`, then `POST /v1/router/models/load`, then restores slot.

3. **Slot save timing:** The `/slots/{id}?action=save` endpoint must be called while the model is still loaded. If called after unload, it returns an error.

4. **MTP model compatibility:** Multi-token prediction models may have draft cache incompatibilities during slot restore. Consider disabling slot restore for MTP models (check `--spec-type` in model config).

5. **VRAM management:** super-router handles LRU eviction and `models_max`. super-go-manager doesn't manage VRAM — it trusts the router's model lifecycle.

6. **Port selection:** super-router needs a port that doesn't conflict with arc-router (18093) or llama-swap (9292). Consider 18094 or similar.

## Implementation Units

### Phase 1: Super-Router Setup

**What:** Configure and launch super-router using main-llama build.

**Files:**
- Create: `/home/chief/models/super-router/models.ini`
- Create: `/etc/systemd/system/super-router.service`

**Steps:**
1. Create models.ini from current model definitions (adapt from llama-swap config.yaml):
   ```ini
   [LFM2-2.6B-Transcript-Q8_0]
   model = /home/chief/models/LFM2-2.6B-Transcript-Q8_0.gguf
   ctx-size = 32768
   ngl = 99
   flash-attn = true
   parallel = 1
   slot-save-path = /home/chief/tmp/llama-slots/LFM2-2.6B-Transcript-Q8_0

   [LFM2.5-1.2B-Instruct-Q8_0]
   model = /home/chief/models/LFM2.5-1.2B-Instruct-Q8_0.gguf
   ctx-size = 32768
   ngl = 99
   flash-attn = true
   slot-save-path = /home/chief/tmp/llama-slots/LFM2.5-1.2B-Instruct-Q8_0
   ```
2. Create systemd service:
   ```ini
   [Unit]
   Description=Super Council LLM Router
   After=network-online.target

   [Service]
   ExecStart=/home/chief/main-llama/llama.cpp/build/bin/llama-server \
       --host 127.0.0.1 \
       --port 18094 \
       --models-dir /home/chief/models/super-router \
       --models-preset /home/chief/models/super-router/models.ini \
       --models-max 2 \
       --slot-save-path /home/chief/tmp/llama-slots
   Restart=on-failure
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```
3. Create slot directories: `mkdir -p /home/chief/tmp/llama-slots/{LFM2-2.6B-Transcript-Q8_0,LFM2.5-1.2B-Instruct-Q8_0}`.
4. Start super-router, verify it's running on port 18094.
5. Verify API endpoints:
   - `GET /v1/models` — model list with child server ports
   - `POST /v1/router/models/load` — load a model
   - `POST /v1/router/models/unload` — unload a model
   - `GET /v1/router/models/sse` — SSE stream for state changes
6. Verify slot endpoints on child server:
   - `POST /slots/0?action=save` — save KV cache
   - `POST /slots/0?action=restore` — restore KV cache

**Tests:**
- [ ] super-router starts and listens on port 18094
- [ ] `/v1/models` returns model list with child server ports
- [ ] `POST /v1/router/models/load` loads a model successfully
- [ ] `POST /v1/router/models/unload` unloads a model successfully
- [ ] `GET /v1/router/models/sse` connects and sends `model_status` events
- [ ] Slot save/restore works on child server

**Dependencies:** None.

---

### Phase 2: Super Go Manager — Core Skeleton

**What:** Create the Go service skeleton with HTTP client, SSE subscriber, and slot directory management.

**Files:**
- Create: `/home/chief/Coding-Projects/7-council/super-go-manager/main.go`
- Create: `/home/chief/Coding-Projects/7-council/super-go-manager/go.mod`
- Create: `/home/chief/Coding-Projects/7-council/super-go-manager/config.yaml`

**Steps:**
1. Initialize Go module: `go mod init super-go-manager`.
2. Create `config.yaml` with super-router URL, slot directory, llama binary path, and model list.
3. Implement HTTP client for super-router (`GET /v1/models`, `POST /v1/router/models/load`, `POST /v1/router/models/unload`) and child servers (`POST /slots/{id}?action=save/restore`).
4. Implement SSE subscriber for `GET /v1/router/models/sse` — parse `model_status` events, extract model name, status, and child server port.
5. Implement slot directory management: `<alias>/<config_hash>/slot-0.bin` + `.json` metadata sidecar.
6. Implement binary hash tracking: compute SHA-256 of llama-server binary, purge slots on change.
7. Implement config hash computation: SHA-256 of model path, ctx_size, ngl, cache types, flash attention.

**Config structure:**
```yaml
router:
  url: "http://127.0.0.1:18094"

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
- [ ] Service starts and connects to super-router SSE stream
- [ ] SSE events parsed correctly (model name, status, child port)
- [ ] Model state detection works (loaded/unloaded transitions)
- [ ] Config hash computation matches expected values
- [ ] Binary hash tracking detects binary changes

**Dependencies:** Phase 1 (super-router setup).

---

### Phase 3: Slot Persistence Logic

**What:** Implement the save→unload→load→restore cycle.

**Files:**
- Modify: `/home/chief/Coding-Projects/7-council/super-go-manager/main.go`

**Steps:**
1. Implement `saveSlot(alias, childPort)` — call `POST /slots/0?action=save` on child server, write metadata sidecar.
2. Implement `restoreSlot(alias, childPort)` — read metadata sidecar, validate signature, call `POST /slots/0?action=restore`.
3. Implement `swapModel(fromAlias, toAlias)` — the core swap logic:
   a. Get current model's child port from super-router (`GET /v1/models`).
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
2. super-go-manager: GET /v1/models → find current model (model-A) and its port
3. super-go-manager: POST /slots/0?action=save on model-A's port
4. super-go-manager: write metadata sidecar
5. super-go-manager: POST /v1/router/models/unload for model-A
6. super-go-manager: POST /v1/router/models/load for model-B
7. super-go-manager: wait for SSE event: model-B status=loaded
8. super-go-manager: GET /v1/models → find model-B's port
9. super-go-manager: POST /slots/0?action=restore on model-B's port
10. super-go-manager: validate restore (n_restored matches n_saved)
```

**Tests:**
- [ ] Slot save returns valid response with `n_saved` count
- [ ] Metadata sidecar written correctly
- [ ] Slot restore validates metadata before restoring
- [ ] Full swap cycle works (save→unload→load→restore)
- [ ] Error handling: restore fails gracefully on missing metadata

**Dependencies:** Phase 2 (Go service skeleton).

---

### Phase 4: Swap Command Interface

**What:** Provide an interface for triggering model swaps with slot persistence.

**Files:**
- Modify: `/home/chief/Coding-Projects/7-council/super-go-manager/main.go`
- Create: `/home/chief/Coding-Projects/7-council/super-go-manager/cmd/swap.go`

**Steps:**
1. Implement HTTP endpoint: `POST /swap?alias=<target>` — triggers swap with slot persistence.
2. Implement CLI command: `super-go-manager swap <alias>` — same logic, CLI interface.
3. Implement swap state tracking: prevent concurrent swaps, queue requests during active swap.
4. Implement swap logging: structured logs for save/restore timing, token counts, errors.
5. Implement health endpoint: `GET /health` — reports manager status, current model, last swap time.

**Tests:**
- [ ] HTTP endpoint accepts swap requests
- [ ] CLI command triggers swap
- [ ] Concurrent swaps are serialized (not parallel)
- [ ] Health endpoint reports accurate state
- [ ] Swap logging includes timing and token counts

**Dependencies:** Phase 3 (slot persistence logic).

---

### Phase 5: Production Wiring

**What:** Wire both components into production, decommission llama-swap.

**Files:**
- Create: `/etc/systemd/system/super-go-manager.service`
- Modify: `super_council` config (update model endpoint from llama-swap to super-router)

**Steps:**
1. Build Go binary: `go build -o super-go-manager ./...`
2. Create systemd service:
   ```ini
   [Unit]
   Description=Super Council Slot Persistence Manager
   After=super-router.service
   Requires=super-router.service

   [Service]
   ExecStart=/home/chief/Coding-Projects/7-council/super-go-manager/super-go-manager \
       --config /home/chief/Coding-Projects/7-council/super-go-manager/config.yaml
   Restart=on-failure
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```
3. Start both services: `super-router.service`, then `super-go-manager.service`.
4. Verify super-go-manager is healthy and connected to super-router.
5. Test swap: `curl -X POST http://127.0.0.1:9293/swap?alias=<target>`
6. Verify slot was saved and restored correctly (token count match).
7. Stop and disable `llama-swap.service`.
8. Update `super_council` config to point to super-router (port 18094) instead of llama-swap (port 9292).

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] `super-router.service` starts and listens on port 18094
- [ ] `super-go-manager.service` starts and reports healthy
- [ ] Swap via HTTP endpoint works end-to-end
- [ ] Slot save/restore preserves conversation context (verify token count)
- [ ] `llama-swap.service` stopped and disabled
- [ ] `super_council` can reach models via super-router
- [ ] No regression in existing services

**Dependencies:** Phase 4 (swap command interface).

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/models/super-router/models.ini` | Super-router model presets |
| Create | `/etc/systemd/system/super-router.service` | Super-router systemd service |
| Create | `/home/chief/Coding-Projects/7-council/super-go-manager/main.go` | Go service entry point |
| Create | `/home/chief/Coding-Projects/7-council/super-go-manager/go.mod` | Go module definition |
| Create | `/home/chief/Coding-Projects/7-council/super-go-manager/config.yaml` | Service configuration |
| Create | `/home/chief/Coding-Projects/7-council/super-go-manager/cmd/swap.go` | Swap command/endpoint |
| Create | `/etc/systemd/system/super-go-manager.service` | Systemd service unit |
| Modify | `super_council` config | Update model endpoint from llama-swap to super-router |

## Success Criteria

- [ ] super-router runs on port 18094 with slot-save-path enabled
- [ ] super-go-manager runs as systemd service, connected to super-router via SSE
- [ ] Model swaps preserve KV cache (slot save before unload, restore after load)
- [ ] Per-model, per-config slot namespaces prevent cross-model corruption
- [ ] Binary hash tracking purges slots on llama-server binary change
- [ ] Metadata sidecars validate model signature before restore
- [ ] Swap endpoint serializes concurrent requests
- [ ] `llama-swap.service` decommissioned (stopped, disabled)
- [ ] `super_council` points to super-router instead of llama-swap
- [ ] No regression in existing services
- [ ] End-to-end swap tested: save→unload→load→restore with token count verification

## Test Requirements

### Phase-Specific Tests

1. **Super-router API:** Verify all endpoints work (models, load, unload, SSE).
2. **SSE subscription:** Verify SSE stream connects and sends `model_status` events.
3. **Slot save/restore:** Verify KV cache is saved and restored correctly (token count match).
4. **Config hash:** Verify config hash computation matches expected values.
5. **Binary hash:** Verify slot purge on binary change.
6. **Swap cycle:** Full save→unload→load→restore cycle with timing and token count verification.
7. **Concurrency:** Verify concurrent swap requests are serialized.
8. **Error handling:** Verify graceful degradation on missing metadata, failed restores.

### Integration Tests

1. **End-to-end swap:** Trigger swap via HTTP endpoint, verify slot persistence.
2. **Super-council compatibility:** Verify super-council can reach models via super-router after llama-swap decommission.
3. **Service health:** Verify all services (super-router, super-go-manager, memory-service) are healthy.

## Notes for Execution

- **Keep it thin:** super-go-manager should be ~200-300 lines. No proxy, no model lifecycle management.
- **Reuse existing logic:** The Python slot-supervisor.py has the slot directory structure, config hash, and metadata sidecar logic. Port this to Go.
- **Test incrementally:** Verify each phase before proceeding. Don't skip verification.
- **SSE is primary:** Use SSE stream for model state changes. The main build has full SSE support.
- **arc-router is untouched:** The SYCL fork (port 18093) is independent and exclusive. Do not reference or modify it.
- **Decommission llama-swap last:** Only after super-go-manager is verified working.
