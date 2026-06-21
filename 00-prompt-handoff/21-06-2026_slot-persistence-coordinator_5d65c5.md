# Slot Persistence Coordinator — Replace llama-swap with Router + Go Coordinator

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `5d65c5` |
| Entity type | `handoff` |
| Short description | Replace unreliable llama-swap proxy with native llama.cpp router mode + thin Go slot persistence coordinator |
| Status | `draft` |
| Source references | `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py`, `/home/chief/llama-swap/config.yaml`, `/home/chief/models/arc-router/models.ini` |
| Generated | `21-06-2026` |
| Next action / owner | Execute Phase 1 (research & API verification), then proceed through phases sequentially |

## Summary

The current `llama-swap` proxy (port 9292) is unreliable: binary hash collisions trigger slot purges, race conditions corrupt saves, metadata sidecars are missing, and MTP model slot compatibility is broken. All these issues stem from managing model lifecycle + routing + slot persistence in a single complex proxy.

The native `llama.cpp` router mode (`arc-router.service` on port 18093) already handles model loading/unloading natively. The gap is **slot persistence across model swaps** — saving KV cache before unload, restoring after load.

This handoff specifies a thin Go service (~200-300 lines) that watches the router for model state changes and coordinates slot save/restore via the child server's `/slots/{id}?action=save/restore` endpoints. No proxy, no model lifecycle management — just slot persistence coordination.

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/docs/slot-supervisor.py` — legacy Python supervisor (reference for slot logic)
- `/home/chief/llama-swap/config.yaml` — current llama-swap config (model definitions, slot settings)
- `/home/chief/models/arc-router/models.ini` — router model presets
- `/home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/tools/server/` — fork's server source (SYCL build)
- `/home/chief/main-llama/llama.cpp/tools/server/` — main build server source (reference for API)

**Related codebases:**
- `/home/chief/main-llama/llama.cpp/` — main llama.cpp build (CPU, reference for router API)
- `/home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/` — SYCL fork (arc-router binary)

## Architecture

```
Client → [arc-router:18093] → [child-server:dynamic_port:llama-server]
                ↑                    ↑
                │                    │
         /v1/models (poll)    /slots/0?action=save/restore
                │                    │
         [slot-persistor:Go] ────────┘
                │
         /home/chief/tmp/llama-slots/<alias>/<config_hash>/slot-0.bin
```

**Roles:**
- **arc-router** (port 18093): Manages model loading/unloading, request routing. No slot persistence.
- **child-server** (dynamic port): Runs llama-server with `--slot-save-path`. Exposes `/slots/{id}?action=save/restore`.
- **slot-persistor** (Go): Watches router for model changes, coordinates save→unload→load→restore cycle.

## Constraints

- **Single slot only:** All models serialize through one GPU; `id_slot=0` always.
- **Per-model, per-config namespace:** Slot bins stored in `<alias>/<config_hash>/` to prevent cross-model KV corruption.
- **Binary hash tracking:** Purge all slots on llama-server binary change (prevents incompatible restores).
- **Metadata sidecar:** `.json` file validates model signature before restore.
- **No proxy:** The Go service does NOT proxy HTTP requests. It only coordinates slot persistence.
- **Polling, not SSE:** The SYCL fork doesn't have SSE endpoints. Use `/v1/models` polling (1-2s interval).
- **Slot save before unload:** Must save slot state BEFORE the router unloads the model. This requires intercepting the swap command.
- **Slot restore after load:** Must restore slot state AFTER the new model is fully loaded and healthy.

## Caveats & Uncertainty

1. **Router API gap:** The SYCL fork (`llama-vulkan-a380`) has basic router mode but lacks `POST /v1/router/models/load`, `POST /v1/router/models/unload`, and `GET /v1/router/models/sse` endpoints present in the main build. The coordinator must use `/v1/models` polling to detect state changes.

2. **Swap interception:** The router doesn't provide hooks for "about to unload" or "just loaded" events. The coordinator must either:
   - **Option A (recommended):** Wrap the router's load/unload commands — the coordinator receives swap requests, saves slot, then calls router to unload/load, then restores slot.
   - **Option B:** Poll `/v1/models` and detect state changes reactively (racy — might miss the save window).

3. **Slot save timing:** The `/slots/{id}?action=save` endpoint must be called while the model is still loaded and processing. If called after unload, it returns an error.

4. **MTP model compatibility:** Multi-token prediction models may have draft cache incompatibilities during slot restore. Consider disabling slot restore for MTP models (check `--spec-type` in model config).

5. **VRAM management:** The router handles LRU eviction and `models_max`. The coordinator doesn't manage VRAM — it trusts the router's model lifecycle.

## Implementation Units

### Phase 1: Research & API Verification

**What:** Verify the router and child server APIs available to the coordinator. Confirm slot save/restore works end-to-end.

**Files:** None (investigation only).

**Steps:**
1. Query `GET http://127.0.0.1:18093/v1/models` — confirm model list, status, child server ports.
2. Identify the loaded model's child server port from the response.
3. Test `POST http://<child_port>/slots/0?action=save` with `{"filename":"slot-0.bin"}` — verify it works.
4. Test `POST http://<child_port>/slots/0?action=restore` with `{"filename":"slot-0.bin"}` — verify it works.
5. Check if `--slot-save-path` is currently set on the child server (likely not — needs to be added to models.ini).
6. Verify the fork's router supports `POST /v1/router/models/load` and `POST /v1/router/models/unload` (likely 404).
7. Document findings: which endpoints work, which don't, what's needed.

**Tests:**
- [ ] `/v1/models` returns model list with child server ports
- [ ] Slot save/restore works on child server (after adding `--slot-save-path`)
- [ ] Router load/unload endpoints tested (document 404 if unavailable)

**Dependencies:** None.

---

### Phase 2: Update models.ini with slot-save-path

**What:** Add `--slot-save-path` to each model's preset in `models.ini` so child servers support slot endpoints.

**Files:**
- Modify: `/home/chief/models/arc-router/models.ini`

**Steps:**
1. Add `slot-save-path = /home/chief/tmp/llama-slots/<alias>` to each model section in `models.ini`.
2. Create the slot directories: `mkdir -p /home/chief/tmp/llama-slots/<alias>`.
3. Restart `arc-router.service` to apply changes.
4. Verify child servers start with `--slot-save-path` flag.
5. Test slot save/restore on the running child server.

**Example models.ini:**
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

**Tests:**
- [ ] `arc-router.service` restarts cleanly
- [ ] Child server logs show `--slot-save-path` flag
- [ ] `POST /slots/0?action=save` returns 200 with `n_saved` count

**Dependencies:** Phase 1 (API verification).

---

### Phase 3: Go Service — Core Skeleton

**What:** Create the Go service skeleton with HTTP client, router polling, and slot directory management.

**Files:**
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/main.go`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/go.mod`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/config.yaml`

**Steps:**
1. Initialize Go module: `go mod init slot-persistor`.
2. Create `config.yaml` with router URL, slot directory, and model list.
3. Implement HTTP client for router (`GET /v1/models`) and child servers (`POST /slots/{id}?action=save/restore`).
4. Implement router polling loop (1-2s interval) to detect model state changes.
5. Implement slot directory management: `<alias>/<config_hash>/slot-0.bin` + `.json` metadata sidecar.
6. Implement binary hash tracking: compute SHA-256 of llama-server binary, purge slots on change.
7. Implement config hash computation: SHA-256 of model path, ctx_size, ngl, cache types, flash attention.

**Config structure:**
```yaml
router:
  url: "http://127.0.0.1:18093"
  poll_interval: "2s"

slot_dir: "/home/chief/tmp/llama-slots"

llama_bin: "/home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/build-sycl-prod/bin/llama-server"

models:
  - alias: "LFM2-2.6B-Transcript-Q8_0"
    model_path: "/home/chief/models/LFM2-2.6B-Transcript-Q8_0.gguf"
    ctx_size: 32768
    ngl: 99
    cache_type_k: "q8_0"
    cache_type_v: "q8_0"
    flash_attention: true
  - alias: "LFM2.5-1.2B-Instruct-Q8_0"
    ...
```

**Tests:**
- [ ] Service starts and polls router successfully
- [ ] Model state detection works (loaded/unloaded transitions)
- [ ] Config hash computation matches expected values
- [ ] Binary hash tracking detects binary changes

**Dependencies:** Phase 2 (slot-save-path configured).

---

### Phase 4: Slot Persistence Logic

**What:** Implement the save→unload→load→restore cycle.

**Files:**
- Modify: `/home/chief/Coding-Projects/7-council/slot-persistor/main.go`

**Steps:**
1. Implement `saveSlot(alias, childPort)` — call `POST /slots/0?action=save` on child server, write metadata sidecar.
2. Implement `restoreSlot(alias, childPort)` — read metadata sidecar, validate signature, call `POST /slots/0?action=restore`.
3. Implement `swapModel(fromAlias, toAlias)` — the core swap logic:
   a. Get current model's child port from router.
   b. Save slot on current child server.
   c. Trigger router to unload current model (via API or models.ini reload).
   d. Wait for new model to load (poll `/v1/models` for `loaded` status).
   e. Get new model's child port.
   f. Restore slot on new child server.
4. Implement metadata sidecar: `{alias, config_hash, model_signature, timestamp, n_saved}`.
5. Implement restore validation: check metadata exists, config hash matches, model signature matches.
6. Implement error handling: retry restore with backoff, log failures, continue on error.

**Swap flow:**
```
1. Client requests swap to "model-B"
2. Coordinator: GET /v1/models → find current model (model-A) and its port
3. Coordinator: POST /slots/0?action=save on model-A's port
4. Coordinator: write metadata sidecar
5. Coordinator: trigger router to unload model-A, load model-B
6. Coordinator: poll /v1/models until model-B is "loaded"
7. Coordinator: GET /v1/models → find model-B's port
8. Coordinator: POST /slots/0?action=restore on model-B's port
9. Coordinator: validate restore (n_restored matches n_saved)
```

**Tests:**
- [ ] Slot save returns valid response with `n_saved` count
- [ ] Metadata sidecar written correctly
- [ ] Slot restore validates metadata before restoring
- [ ] Full swap cycle works (save→unload→load→restore)
- [ ] Error handling: restore fails gracefully on missing metadata

**Dependencies:** Phase 3 (Go service skeleton).

---

### Phase 5: Swap Command Interface

**What:** Provide an interface for triggering model swaps with slot persistence.

**Files:**
- Modify: `/home/chief/Coding-Projects/7-council/slot-persistor/main.go`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/cmd/swap.go` (or HTTP endpoint)

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

**Dependencies:** Phase 4 (slot persistence logic).

---

### Phase 6: Production Wiring

**What:** Wire the coordinator into production, decommission llama-swap.

**Files:**
- Create: `/etc/systemd/system/slot-persistor.service`
- Create: `/home/chief/Coding-Projects/7-council/slot-persistor/config.yaml` (production)
- Modify: `/home/chief/models/arc-router/models.ini` (if needed)

**Steps:**
1. Build Go binary: `go build -o slot-persistor ./...`
2. Create systemd service unit:
   ```ini
   [Unit]
   Description=Slot Persistence Coordinator
   After=arc-router.service
   Requires=arc-router.service

   [Service]
   ExecStart=/home/chief/Coding-Projects/7-council/slot-persistor/slot-persistor --config /home/chief/Coding-Projects/7-council/slot-persistor/config.yaml
   Restart=on-failure
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```
3. Start `slot-persistor.service`, verify it's running.
4. Test swap: `curl -X POST http://127.0.0.1:9293/swap?alias=LFM2.5-1.2B-Instruct-Q8_0`
5. Verify slot was saved and restored correctly.
6. Stop and disable `llama-swap.service`.
7. Update any clients that point to llama-swap (port 9292) to use arc-router (port 18093) directly.
8. Update `super_council` config to point to arc-router instead of llama-swap.

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] `slot-persistor.service` starts and reports healthy
- [ ] Swap via HTTP endpoint works end-to-end
- [ ] Slot save/restore preserves conversation context (verify token count)
- [ ] `llama-swap.service` stopped and disabled
- [ ] Clients can reach models via arc-router (port 18093)
- [ ] No regression in existing services (arc-router, memory-service)

**Dependencies:** Phase 5 (swap command interface).

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/main.go` | Go service entry point |
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/go.mod` | Go module definition |
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/config.yaml` | Service configuration |
| Create | `/home/chief/Coding-Projects/7-council/slot-persistor/cmd/swap.go` | Swap command/endpoint |
| Create | `/etc/systemd/system/slot-persistor.service` | Systemd service unit |
| Modify | `/home/chief/models/arc-router/models.ini` | Add `slot-save-path` to presets |
| Modify | `super_council` config | Update model endpoint from llama-swap to arc-router |

## Success Criteria

- [ ] Slot persistence coordinator runs as systemd service
- [ ] Model swaps preserve KV cache (slot save before unload, restore after load)
- [ ] Per-model, per-config slot namespaces prevent cross-model corruption
- [ ] Binary hash tracking purges slots on llama-server binary change
- [ ] Metadata sidecars validate model signature before restore
- [ ] Swap endpoint serializes concurrent requests
- [ ] `llama-swap.service` decommissioned (stopped, disabled)
- [ ] All clients point to arc-router (port 18093) instead of llama-swap (port 9292)
- [ ] No regression in existing services
- [ ] End-to-end swap tested: save→unload→load→restore with token count verification

## Test Requirements

### Phase-Specific Tests

1. **API verification:** Confirm router and child server endpoints work as expected.
2. **Slot save/restore:** Verify KV cache is saved and restored correctly (token count match).
3. **Config hash:** Verify config hash computation matches expected values.
4. **Binary hash:** Verify slot purge on binary change.
5. **Swap cycle:** Full save→unload→load→restore cycle with timing and token count verification.
6. **Concurrency:** Verify concurrent swap requests are serialized.
7. **Error handling:** Verify graceful degradation on missing metadata, failed restores.

### Integration Tests

1. **End-to-end swap:** Trigger swap via HTTP endpoint, verify slot persistence.
2. **Client compatibility:** Verify clients can reach models via arc-router after llama-swap decommission.
3. **Service health:** Verify all services (arc-router, slot-persistor, memory-service) are healthy.

## Notes for Execution

- **Start with Phase 1 (research):** Don't assume API endpoints exist. Verify everything.
- **Keep it thin:** The Go service should be ~200-300 lines. No proxy, no model lifecycle management.
- **Reuse existing logic:** The Python slot-supervisor.py has the slot directory structure, config hash, and metadata sidecar logic. Port this to Go.
- **Test incrementally:** Verify each phase before proceeding. Don't skip verification.
- **Decommission llama-swap last:** Only after the coordinator is verified working.
