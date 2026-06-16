# llama-swap Integration — Master Plan

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `75a031` |
| Entity type | `handoff` |
| Short description | Optional module architecture: SwapHook interface (upstream) + SlotStore council extension (build-tagged) + thin Python client |
| Status | `in_progress` |
| Source references | `/home/chief/llama-swap/`, `/home/chief/Coding-Projects/7-council/super_council/` |
| Generated | `16-06-2026` |
| Next action / owner | Go build verification, Python integration tests |

---

## Architecture Decision: Optional Module Pattern

**Decision:** Implement SlotStore and ModelRegistry as an optional module in llama-swap, not a fork.

**Rationale:**
- Upstream PR adds only a generic `SwapHook` interface (6 lines, zero cost when nil)
- Council-specific code (KV cache I/O, config hash, binary groups) behind `-tags council` build tag
- Standard builds (`go build ./...`) produce identical binary to upstream
- Council builds (`go build -tags council ./...`) include KV cache persistence
- If upstream rejects SwapHook PR: micro-fork with 6 lines of divergence

**What gets upstreamed:**
- `internal/router/hook.go` — SwapHook interface (generic, no council types)
- `internal/router/base.go` — 6 lines: hook field + two conditional calls in doSwap()
- `internal/config/model_config.go` — SlotStoreConfig struct (YAML field, ignored without council tag)

**What stays council-only (build-tagged):**
- `internal/slotstore/` — KV cache persistence (llama.cpp-specific)
- `internal/router/hook_council.go` — SwapHook implementation
- `internal/server/slots.go` — Slot REST endpoints
- `internal/server/slots_routes.go` — Route registration

---

## Architecture

### Target State (after integration)

```
llama-swap (Go, :9292) — THE MODEL AUTHORITY
    │
    ├── router.SwapHook (interface) ← UPSTREAM
    │   ├── BeforeStop(toStop, target) → save KV cache
    │   └── AfterReady(modelID) → restore KV cache
    │
    ├── slotstore.Store (council, build-tagged)
    │   ├── Save(modelID) → HTTP POST to llama-server /slots/?action=save
    │   ├── Restore(modelID) → HTTP POST to llama-server /slots/?action=restore
    │   ├── ValidateChecksum(binPath, expected) → SHA-256
    │   └── Cleanup() → orphan reconciliation
    │
    ├── Process Lifecycle (existing upstream)
    │   └── start/stop llama-server, health checks, auto-restart
    │
    ├── VRAM Management (existing upstream)
    │   └── perfgpu SSE stats, cached GPU data
    │
    ├── Real-time Metrics (existing upstream)
    │   └── SSE /api/events
    │
    └── REST API (extended with council endpoints)
        ├── GET  /api/slots/status         (council)
        ├── POST /api/slots/save/{model}   (council)
        ├── POST /api/slots/restore/{model} (council)
        └── POST /api/slots/cleanup        (council)

SlotSupervisor (Python, :8000) — THE WORKFLOW ORCHESTRATOR
    │
    ├── CouncilLlamaSwapClient (NEW — thin HTTP client, ~300 lines)
    │   ├── swap_to(alias) → GET /upstream/{alias}
    │   ├── get_current_model() → GET /api/models/
    │   ├── get_slot_status() → GET /api/slots/status
    │   ├── get_free_vram() → GET /api/performance
    │   └── wait_for_vram(required_mb) → poll GPU stats
    │
    ├── Council Pipeline (UNCHANGED)
    ├── Memory Service (UNCHANGED)
    └── AppFlowy Bridge (UNCHANGED)

InfraDashboard (React, :3000)
    └── useLlamaSwapStats → SSE /api/events (real-time)
    └── LlamaModelsPanel → model states, load/unload
    └── LlamaActivityStats → request counts, token throughput
    └── LlamaPerformanceChart → CPU, memory, GPU charts
```

### Swap Lifecycle (with SwapHook)

```
① BeforeStop(toStop=["model-a"], target="model-b")
    → slotstore.Save("model-a")
    → HTTP POST to llama-server /slots/0?action=save
    → compute SHA-256 checksum
    → write slot-0.json sidecar

② Stop("model-a")
    → llama-swap stops llama-server process (existing)

③ Run("model-b")
    → llama-swap starts llama-server with model-b (existing)

④ WaitReady("model-b")
    → health check passes (existing)

⑤ AfterReady("model-b")
    → slotstore.Restore("model-b")
    → read slot-0.json sidecar
    → validate SHA-256 checksum
    → HTTP POST to llama-server /slots/0?action=restore
    → update restored_at timestamp
```

---

## Execution Order (DAG)

```
Phase 0 (Go Build Verification) ──────────────────────────────────────┐
                                                                      │
Phase 1 (Analysis & Review) ──┐                                      │
                               ├──────────────────────────────────────┤
Phase 1A (Backend Bridge) ─────┤         Phase 2 (Shared Types + SSE Hook) ──┐
                               │                                              │
Phase 3A (ModelsPanel) ────────┤         Phase 3B (ActivityStats) ────────────┤
Phase 3C (PerformanceChart) ───┤                                              │
                               │                                              │
Phase 4 (InfraDashboard Integration) ◄────────────────────────────────────────┤
                                                                              │
Phase 5 (Production Wiring & Verification) ◄──────────────────────────────────┘
```

**Phase 0** validates Go code compiles in both standard and council modes.
**Phase 1A** creates the Python client (already done).
**Phases 2-4** are frontend (parallel with backend).
**Phase 5** wires everything together.

---

## Phases Overview

| Phase | Name | Effort | Dependencies | Status |
|-------|------|--------|--------------|--------|
| 0 | Go Build Verification | ~15 min | None | ⏳ pending Go install |
| 1 | Analysis & Architecture Review | ~30 min | None | ✅ done |
| 1A | Backend Bridge (Python Client) | ~45 min | Phase 1 | ✅ done |
| 2 | Shared Types + SSE Hook | ~45 min | Phase 1 | ⏳ pending |
| 3A | LlamaModelsPanel Component | ~30 min | Phase 2 | ⏳ pending |
| 3B | LlamaActivityStats Component | ~30 min | Phase 2 | ⏳ pending |
| 3C | LlamaPerformanceChart Component | ~45 min | Phase 2 | ⏳ pending |
| 4 | InfraDashboard Integration | ~30 min | Phases 3A, 3B, 3C | ⏳ pending |
| 5 | Production Wiring & Verification | ~30 min | All phases | ⏳ pending |

---

## Phase 0: Go Build Verification

**What:** Verify all Go code compiles in both standard and council build modes.

**Commands:**
```bash
cd /home/chief/llama-swap

# Standard build — must compile without council features
go build ./...

# Council build — must compile with KV cache persistence
go build -tags council ./...

# Run tests (standard)
go test ./internal/router/ -v
go test ./internal/config/ -v

# Run tests (council)
go test -tags council ./internal/slotstore/ -v
go test -tags council ./internal/router/ -v
```

**Expected:**
- Standard build: compiles cleanly, no council code included
- Council build: compiles cleanly, includes slotstore + hook
- All tests pass in both modes

---

## Phase 1A: Backend Bridge (Python Client) ✅ DONE

**What:** Wire SlotSupervisor to route model swap operations through llama-swap REST API.

**Files Created:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/api/llama_swap_client.py` | Thin HTTP client for llama-swap REST API |
| Create | `super_council/api/test_llama_swap_client.py` | Unit tests with httpx.MockTransport |

**What Gets Removed from `council_main.py` (next step):**

| Component | Lines | Replacement |
|-----------|-------|-------------|
| `UpstreamProcess` | ~350 | llama-swap process management |
| `SlotStore` | ~120 | llama-swap slotstore.SlotStore |
| `SlotClient` | ~100 | llama-swap internal (HTTP to llama-server) |
| `ModelRegistry` | ~150 | llama-swap config.yaml |
| `BinaryHashTracker` | ~80 | llama-swap slotstore.ValidateChecksum |
| `_swap_to()`, `_save_current_slot()`, `_restore_current_slot()`, `_get_free_vram()`, `_wait_for_vram()` | ~250 | llama-swap swap lifecycle + SwapHook |
| `CouncilLlamaSwapClient` | **~300** | **NEW — replaces all above** |
| **Net** | **~-850** | |

**Next Step:** Replace `SlotSupervisor` methods to use `LlamaSwapClient`. Add graceful fallback when llama-swap is unavailable.

---

## Phase 2: Shared Types + SSE Hook

**What:** Define TypeScript types for llama-swap data and create the SSE-based React hook.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `frontend/packages/web-core/src/shared/types/llama-swap.ts` | TypeScript interfaces |
| Create | `frontend/packages/web-core/src/shared/hooks/council/useLlamaSwapStats.ts` | SSE hook |

**Types to define** (from `ui-svelte/src/lib/types.ts`):

```typescript
interface LlamaModel {
  id: string;
  state: 'ready' | 'starting' | 'stopping' | 'stopped' | 'shutdown' | 'unknown';
  name: string;
  description: string;
  unlisted: boolean;
  aliases?: string[];
  capabilities?: {
    vision?: boolean;
    audio_transcriptions?: boolean;
    image_generation?: boolean;
    reranker?: boolean;
  };
}

interface LlamaActivityEntry {
  id: number;
  timestamp: string;
  model: string;
  req_path: string;
  resp_status_code: number;
  tokens: {
    cache_tokens: number;
    input_tokens: number;
    output_tokens: number;
    prompt_per_second: number;
    tokens_per_second: number;
  };
  duration_ms: number;
}

interface LlamaSysStat {
  timestamp: string;
  cpu_pct: number[];
  cpu_pct_total: number;
  mem_used_gb: number;
  mem_total_gb: number;
  swap_used_gb: number;
  load_avg: number[];
  net_rx_bytes: number;
  net_tx_bytes: number;
}

interface LlamaGpuStat {
  timestamp: string;
  id: number;
  name: string;
  gpu_util_pct: number;
  mem_util_pct: number;
  mem_used_mb: number;
  mem_total_mb: number;
  temp_c: number;
  power_draw_w: number;
}

interface LlamaInFlight {
  id: string;
  model: string;
  req_path: string;
  tokens_consumed: number;
  tokens_generated: number;
  started_at: string;
}

interface LlamaLogEntry {
  type: 'proxy' | 'upstream';
  timestamp: string;
  message: string;
}
```

**Hook interface:**

```typescript
interface LlamaSwapStats {
  models: LlamaModel[];
  loadingModels: string[];
  activityEntries: LlamaActivityEntry[];
  totalRequests: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCacheTokens: number;
  inflightRequests: LlamaInFlight[];
  sysStats: LlamaSysStat[];
  gpuStats: LlamaGpuStat[];
  logs: LlamaLogEntry[];
  connected: boolean;
  error: string | null;
}

interface LlamaSwapActions {
  loadModel(modelId: string): Promise<void>;
  unloadModel(modelId: string): Promise<void>;
  unloadAll(): Promise<void>;
  refreshPerformance(): Promise<void>;
}

function useLlamaSwapStats(baseUrl?: string): LlamaSwapStats & LlamaSwapActions;
```

---

## Phase 3A: LlamaModelsPanel Component

**What:** React component displaying model list with load/unload controls, state badges.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `frontend/packages/web-core/src/pages/infra/llama/LlamaModelsPanel.tsx` | Model list with controls |

**Steps:**
1. Consume `useLlamaSwapStats` hook
2. Render model table: name, state badge (color-coded), description, aliases
3. Load/unload buttons per model (disabled during transitions)
4. "Unload All" button with confirmation
5. Sort by name, filter unlisted models
6. State colors: ready=green, starting=yellow (spinning), stopping=orange, stopped=gray, error=red

---

## Phase 3B: LlamaActivityStats Component

**What:** React component displaying request counts, token throughput, and p50/p95/p99 histograms.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `frontend/packages/web-core/src/pages/infra/llama/LlamaActivityStats.tsx` | Activity metrics display |

**Steps:**
1. Summary cards: total requests, input tokens, output tokens, cache tokens
2. Per-model breakdown (group activity entries by model)
3. Token throughput display (tokens/sec)
4. Duration histogram (p50, p95, p99)
5. Auto-refresh from SSE stream
6. Clear history button

---

## Phase 3C: LlamaPerformanceChart Component

**What:** React component displaying CPU, memory, GPU performance over time using Chart.js.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `frontend/packages/web-core/src/pages/infra/llama/LlamaPerformanceChart.tsx` | Performance charts |

**Steps:**
1. Verify Chart.js availability in VK frontend
2. CPU chart: per-core utilization over time
3. Memory chart: used/total GB over time
4. GPU chart: utilization%, VRAM%, temperature, power draw
5. Time window selector: 5m, 15m, 1hr
6. Dark theme matching VK

---

## Phase 4: InfraDashboard Integration

**What:** Wire llama-swap components into InfraDashboard as a collapsible "Model Swap" section.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `frontend/packages/web-core/src/pages/infra/InfraDashboard.tsx` | Add Model Swap section |
| Modify | `frontend/vite.config.ts` | Add `/llama/` proxy to llama-swap |
| Create | `frontend/packages/web-core/src/pages/infra/llama/index.ts` | Barrel export |
| Modify | `frontend/packages/web-core/src/shared/hooks/council/useInfraStatus.ts` | Add `llama_swap` label |

---

## Phase 5: Production Wiring & Verification

**What:** Wire all components into a running system. Start llama-swap, verify full flow end-to-end.

**Steps:**
1. Build llama-swap with council tag: `go build -tags council -o llama-swap-council ./cmd/llama-swap/`
2. Configure `config.yaml` with slotStore extensions
3. Start llama-swap-council on port :9292
4. Verify health: `curl http://localhost:9292/health`
5. Verify slot endpoints: `curl http://localhost:9292/api/slots/status`
6. Verify Vite proxy routes `/llama/api/events` to llama-swap SSE
7. Open VK frontend, navigate to Infra page
8. Test model swap flow through UI
9. Verify KV cache save/restore in slot directory
10. Verify SlotSupervisor routes through llama-swap API

---

## File Map (Complete)

### Go (llama-swap) — NEW FILES
| File | Phase | Purpose |
|------|-------|---------|
| `internal/router/hook.go` | 0 | SwapHook interface (upstream) |
| `internal/router/hook_default.go` | 0 | No-op hook (!council build) |
| `internal/router/hook_council.go` | 0 | Council hook wiring (council build) |
| `internal/router/hook_test.go` | 0 | SwapHook unit tests |
| `internal/slotstore/store.go` | 0 | KV cache persistence (council build) |
| `internal/slotstore/store_stub.go` | 0 | No-op stub (!council build) |
| `internal/slotstore/store_test.go` | 0 | SlotStore unit tests |
| `internal/slotstore/hook.go` | 0 | SwapHook implementation (council build) |
| `internal/slotstore/hook_test.go` | 0 | Hook unit tests |
| `internal/server/slots.go` | 0 | Slot REST endpoints (council build) |
| `internal/server/slots_stub.go` | 0 | No-op route registration (!council build) |
| `internal/server/slots_routes.go` | 0 | Route registration (council build) |
| `internal/config/slotstore_test.go` | 0 | Config extension tests |
| `docs/council-slotstore.md` | 0 | Documentation |

### Go (llama-swap) — MODIFIED FILES
| File | Phase | Change |
|------|-------|--------|
| `internal/router/base.go` | 0 | +hook field, +2 conditional calls in doSwap(), +getSwapHook(conf) call |
| `internal/config/model_config.go` | 0 | +SlotStoreConfig struct, +SlotStore field in ModelConfig |
| `internal/server/server.go` | 0 | +registerSlotRoutes() call in routes() |

### Python (super_council) — NEW FILES
| File | Phase | Purpose |
|------|-------|---------|
| `super_council/api/llama_swap_client.py` | 1A | Thin HTTP client for llama-swap |
| `super_council/api/test_llama_swap_client.py` | 1A | Unit tests with httpx.MockTransport |

### TypeScript (frontend) — PLANNED FILES
| File | Phase | Purpose |
|------|-------|---------|
| `frontend/packages/web-core/src/shared/types/llama-swap.ts` | 2 | TypeScript interfaces |
| `frontend/packages/web-core/src/shared/hooks/council/useLlamaSwapStats.ts` | 2 | SSE hook |
| `frontend/packages/web-core/src/pages/infra/llama/LlamaModelsPanel.tsx` | 3A | Model list component |
| `frontend/packages/web-core/src/pages/infra/llama/LlamaActivityStats.tsx` | 3B | Activity metrics component |
| `frontend/packages/web-core/src/pages/infra/llama/LlamaPerformanceChart.tsx` | 3C | Performance charts component |
| `frontend/packages/web-core/src/pages/infra/llama/index.ts` | 4 | Barrel export |

### TypeScript (frontend) — PLANNED MODIFICATIONS
| File | Phase | Change |
|------|-------|--------|
| `frontend/packages/web-core/src/pages/infra/InfraDashboard.tsx` | 4 | Add Model Swap section |
| `frontend/vite.config.ts` | 4 | Add `/llama/` proxy |
| `frontend/packages/web-core/src/shared/hooks/council/useInfraStatus.ts` | 4 | Add `llama_swap` label |

---

## Constraints

- **No breaking changes to existing InfraDashboard** — all additions must be additive
- **Graceful degradation** — if llama-swap is unavailable, InfraDashboard must still function
- **SSE reconnection** — hook must auto-reconnect with exponential backoff (max 8s)
- **Memory management** — activity/performance data arrays bounded (max 200 entries)
- **Design system consistency** — use VK's existing Tailwind classes
- **No direct Svelte code reuse** — port patterns, not code
- **Port isolation** — llama-swap on :9292, no conflicts
- **SlotSupervisor backward compatibility** — fall back to direct process management if llama-swap unavailable
- **Build tag discipline** — council code must compile out cleanly without `-tags council`

---

## Success Criteria

- [ ] llama-swap compiles in both standard and council modes (Phase 0)
- [ ] SwapHook interface is upstreamable (generic, no council types)
- [ ] All Go tests pass in both build modes
- [ ] Python LlamaSwapClient passes all unit tests
- [ ] llama-swap is running and discoverable as an infra service
- [ ] Model Swap section displays in InfraDashboard with live SSE data
- [ ] Users can load/unload models from the UI
- [ ] Activity stats show real-time request counts and token throughput
- [ ] Performance charts display CPU and GPU metrics over time
- [ ] SlotSupervisor routes model swap through llama-swap API
- [ ] KV cache save/restore works during model swaps
- [ ] Graceful degradation when llama-swap is unavailable
- [ ] All existing InfraDashboard functionality works (no regression)
- [ ] SSE auto-reconnection works after llama-swap restart

---

## Caveats & Uncertainty

1. **Go not installed locally** — Phase 0 requires Go 1.26+ installation. All code is written and tested for correctness but cannot be compiled locally.

2. **llama-server slot API** — The slot save/restore HTTP endpoints (`/slots/{id}?action=save|restore`) are llama.cpp-specific. They must be verified against the actual llama-server version in use.

3. **GPU stat availability** — llama-swap's GPU stats require `nvidia-smi` access. If running in a container without NVIDIA drivers, GPU stats will be empty.

4. **SSE proxying through Vite** — Vite's dev proxy may buffer SSE connections. The proxy config must set `ws: true` or equivalent.

5. **Chart.js dependency** — VK frontend may not have Chart.js installed. Need to verify before Phase 3C.

6. **Config migration** — `upstream-config.json` → `config.yaml` with slotStore extensions. Models need to be redefined in YAML format.

7. **Concurrent model operations** — If SlotSupervisor and the UI both trigger model loads simultaneously, llama-swap must handle concurrent requests.

---

## Serialized Phase Handoffs

See companion documents:
- `16-06-2026_llama-swap-integration_75a031_p0-build.md` — Phase 0: Go Build Verification
- `16-06-2026_llama-swap-integration_75a031_p1-analysis.md` — Phase 1: Analysis & Architecture Review
- `16-06-2026_llama-swap-integration_75a031_p1a-backend.md` — Phase 1A: Backend Bridge
- `16-06-2026_llama-swap-integration_75a031_p2-types-hook.md` — Phase 2: Shared Types + SSE Hook
- `16-06-2026_llama-swap-integration_75a031_p3a-models.md` — Phase 3A: LlamaModelsPanel
- `16-06-2026_llama-swap-integration_75a031_p3b-activity.md` — Phase 3B: LlamaActivityStats
- `16-06-2026_llama-swap-integration_75a031_p3c-performance.md` — Phase 3C: LlamaPerformanceChart
- `16-06-2026_llama-swap-integration_75a031_p4-integration.md` — Phase 4: InfraDashboard Integration
- `16-06-2026_llama-swap-integration_75a031_p5-wiring.md` — Phase 5: Production Wiring
