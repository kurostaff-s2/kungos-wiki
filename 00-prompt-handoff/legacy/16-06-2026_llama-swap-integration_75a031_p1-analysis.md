# Phase 1: Analysis & Architecture Review

**Parent plan:** `16-06-2026_llama-swap-integration_75a031.md`
**Phase:** 1 of 5
**Dependencies:** None
**Estimated effort:** ~30 min

---

## Project Context

**Project root (llama-swap):** `/home/chief/llama-swap/`
**Project root (VK frontend):** `/home/chief/Coding-Projects/7-council/super_council/frontend/`
**Project root (Supercouncil backend):** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `/home/chief/llama-swap/config.yaml` — llama-swap model configuration
- `/home/chief/llama-swap/README.md` — port and startup instructions
- `/home/chief/llama-swap/ui-svelte/src/lib/types.ts` — data type definitions
- `/home/chief/llama-swap/ui-svelte/src/stores/api.ts` — SSE connection pattern
- `/home/chief/Coding-Projects/7-council/super_council/frontend/package.json` — frontend dependencies
- `/home/chief/Coding-Projects/7-council/super_council/frontend/vite.config.ts` — Vite proxy configuration

---

## What This Phase Delivers

A review and analysis report that validates the integration architecture before any code is written. This phase identifies potential blockers (port conflicts, missing dependencies, model config mismatches) and confirms the integration design is sound.

## Pre-Flight Checklist

- [ ] llama-swap repository exists at `/home/chief/llama-swap/`
- [ ] VK frontend exists at `/home/chief/Coding-Projects/7-council/super_council/frontend/`
- [ ] Supercouncil backend exists at `/home/chief/Coding-Projects/7-council/super_council/`

## Implementation Steps

### Step 1: Verify llama-swap configuration

1. Read `/home/chief/llama-swap/config.yaml` — identify:
   - Default listen port (`listen` or `port` field)
   - Model definitions (paths, names, aliases)
   - Any GPU-related configuration
2. Read `/home/chief/llama-swap/README.md` — identify:
   - Startup command and port configuration
   - Any environment variable requirements
   - Dependency requirements (nvidia-smi, etc.)
3. Check if llama-swap binary exists: `ls -la /home/chief/llama-swap/llama-swap` or equivalent

### Step 2: Confirm port allocation

1. List all currently used ports in the Supercouncil stack:
   - Council API: `:8000`
   - VK frontend (Vite): `:3000`
   - Qwen s2s: `:8091`
   - ARC LLM: `:18095`
   - Milvus: `:18099`
   - Embeddings: `:18099`
   - PostgreSQL: `:5432`
   - MongoDB: `:27017`
2. Check if llama-swap's default port (`:8080`) conflicts
3. Propose alternative port (`:9292`) if needed
4. Verify proposed port is available: `ss -tlnp | grep 9292`

### Step 3: Review model configuration alignment

1. Read llama-swap's `config.yaml` model definitions
2. Read SlotSupervisor's model registry (from `council_main.py` or `api/model_registry.py`)
3. Compare: do the model IDs/aliases match? Are there models in one but not the other?
4. Document any mismatches

### Step 4: Verify SSE event schema

1. Read `/home/chief/llama-swap/ui-svelte/src/lib/types.ts` — document all TypeScript interfaces
2. Read `/home/chief/llama-swap/ui-svelte/src/stores/api.ts` — document SSE event types and parsing logic
3. Confirm event types: `modelStatus`, `logData`, `metrics`, `inflight`, `perfsys`, `perfgpu`
4. Note any fields that may need adaptation for React context

### Step 5: Check frontend dependencies

1. Read `/home/chief/Coding-Projects/7-council/super_council/frontend/package.json`
2. Check for `chart.js` or `react-chartjs-2` (needed for Phase 3C)
3. Check for existing charting libraries
4. Document what needs to be installed

### Step 6: Review Vite proxy configuration

1. Read `/home/chief/Coding-Projects/7-council/super_council/frontend/vite.config.ts`
2. Document existing proxy rules (e.g., `/v1/` → `http://localhost:8000`)
3. Note SSE proxy requirements (Vite may buffer SSE; need `ws: true` or equivalent)

### Step 7: Review SlotSupervisor model swap methods

1. Read `council_main.py` — locate `_swap_to()`, `_get_free_vram()`, `_wait_for_vram()`
2. Document current implementation (direct subprocess management)
3. Map to llama-swap REST equivalents:
   - `_swap_to(alias)` → `POST /api/models/unload` + `GET /upstream/{alias}`
   - `_get_free_vram()` → `GET /api/performance` → parse GPU `mem_free_mb`
   - `_wait_for_vram()` → poll `GET /api/performance` for VRAM availability

### Step 8: Produce analysis report

Write findings to a report file at `/home/chief/llm-wiki/00-prompt-handoff/16-06-2026_llama-swap-integration_75a031_p1-report.md` with:

```markdown
# Phase 1 Analysis Report

## Port Allocation
- llama-swap default port: :XXXX
- Conflict: Yes/No
- Proposed port: :9292 (available: Yes/No)

## Model Configuration Alignment
- Models in llama-swap config.yaml: [list]
- Models in SlotSupervisor registry: [list]
- Mismatches: [list or "none"]

## SSE Event Schema
- Event types confirmed: [list]
- Fields requiring adaptation: [list or "none"]

## Frontend Dependencies
- chart.js: installed/missing
- react-chartjs-2: installed/missing
- Installation needed: Yes/No

## Vite Proxy
- Existing proxy rules: [list]
- SSE passthrough support: Yes/No
- Configuration needed: [details]

## SlotSupervisor Mapping
- _swap_to() → [llama-swap equivalent]
- _get_free_vram() → [llama-swap equivalent]
- _wait_for_vram() → [llama-swap equivalent]

## Blockers
- [list any blocking issues or "none"]

## Recommendations
- [actionable recommendations based on findings]
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `~/.llm-wiki/00-prompt-handoff/16-06-2026_llama-swap-integration_75a031_p1-report.md` | Analysis report |

## Phase-Specific Tests

N/A — this is a review/analysis phase. Verification is reading and confirming file contents.

## Completion Gate

- [ ] All 8 implementation steps completed
- [ ] Analysis report written with all sections populated
- [ ] No unresolved blockers identified (or blockers documented with proposed resolutions)
- [ ] Report saved to handoff directory

## Notes for Next Phase

- Phase 1A (Backend Bridge) uses the SlotSupervisor mapping from Step 7
- Phase 2 (Types + Hook) uses the SSE event schema from Step 4
- Phase 3C (PerformanceChart) uses the dependency check from Step 5
- Phase 4 (Integration) uses the Vite proxy config from Step 6
