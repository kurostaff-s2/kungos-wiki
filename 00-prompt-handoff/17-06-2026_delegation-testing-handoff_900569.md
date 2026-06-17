# Delegation Testing Handoff — Llama Swap + Pipeline Tracking

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `handoff-900569` |
| Entity type | `handoff` |
| Short description | Execute end-to-end tests for delegation flow with llama-swap model management and pipeline state tracking |
| Status | `draft` |
| Source references | `council_main.py` (_delegate, _delegate_chain, PipelineState), `api/model_registry.py`, `api/council_delegations.py` |
| Generated | 17-06-2026 |
| Next action / owner | Test delegation flow: trigger swap → verify chain → check provenance → validate dashboard |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Frontend root:** `/home/chief/Coding-Projects/7-council/super_council/frontend/packages/local-web/`
**Shared pages:** `/home/chief/Coding-Projects/7-council/super_council/frontend/packages/web-core/src/pages/delegation/`
**Key files for this task:**
- `council_main.py` — `_delegate()`, `_delegate_chain()`, `_swap_to()`, `PipelineState`
- `api/council_delegations.py` — Delegation API endpoints
- `memory_service/store/delegation.py` — `DelegationStoreMixin`
- `frontend/packages/web-core/src/pages/delegation/DelegationDashboard.tsx` — Frontend dashboard
- `frontend/packages/local-web/src/routes/_app.delegation.tsx` — Route registration
- `scripts/backfill_delegations.py` — Backfill script (reference for MD parsing)

**Related codebases:**
- `llama-forks/ik_llama.cpp/` — Llama.cpp fork with slot save/restore
- `super_council/frontend/packages/local-web/` — Council frontend (runs on :3000)

---

## What Is Done

### Backend (complete)
- **Schema:** `delegation_runs` table with `run_id UNIQUE`, `chain_id`, `source_id`, `trace_id` provenance columns
- **Store:** `DelegationStoreMixin` composed into `RelationalStore` (23 tests passing)
- **API:** 4 endpoints live on `:8000`:
  - `GET /v1/council/delegations` — paginated list with search/filters
  - `GET /v1/council/delegations/run/{run_id}` — detail with full task/response
  - `GET /v1/council/delegations/chain/{chain_id}` — group by chain
  - `GET /v1/council/delegations/chain/{chain_id}/raw` — raw MD file
- **Backfill:** 8 delegation records populated (6 with provenance, 2 legacy)
- **Pipeline tracking:** `PipelineState` machine (SCOUT → PLAN → BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE → PENDING_REVIEW → HUMAN_GATE → INDEX → DONE/FAILED)

### Llama Swap Integration (complete)
- **`_swap_to()`** routes through `LlamaSwapClient` (Go service on `:9292`)
- **Slot save/restore** via `llama-swap` SwapHook (preserves KV cache across swaps)
- **VRAM management** via `get_free_vram()`, `wait_for_vram()`
- **Model registry** with external server health checks

### Frontend (complete)
- **Delegation dashboard** at `/delegation` with table, search, model filters, chain filter, pagination
- **Detail panel** (slide-over) with full task/response, provenance, raw MD link
- **Sidebar entry** — "Delegations" button (8th item, after MemSearch)
- **Model badges, chain badges, role badges, relative timestamps**

---

## What Needs Testing

### Test 1: Single Delegation with Model Swap

**Goal:** Verify that a delegation triggers a proper model swap (via llama-swap), saves the response, and records it in `delegation_runs`.

**Steps:**
1. Confirm current model slot: `curl http://localhost:8000/v1/models/current`
2. Trigger a delegation via the council tool interface (Pi chat):
   ```
   delegate_to(nemotron-cascade, "Review this code: print('hello')")
   ```
3. Verify swap occurred:
   - Check `council_main` logs for `=== DELEGATION START: <from> -> <to> ===`
   - Check llama-swap logs for `swap_to` event
   - Verify `curl http://localhost:8000/v1/models/current` shows the target model during execution
4. Wait for completion (~30-120s depending on model)
5. Verify swap-back: `curl http://localhost:8000/v1/models/current` should show original model
6. Verify DB record:
   ```sql
   SELECT * FROM delegation_runs ORDER BY created_at DESC LIMIT 1;
   ```
   - `run_id` should match delegation ID
   - `from_model` = original model alias
   - `to_model` = target model alias
   - `role` = "coder" or "reviewer"
   - `source_id` / `trace_id` should be populated (provenance)
7. Verify API returns the record:
   ```
   curl http://localhost:8000/v1/council/delegations?page=1&per_page=1
   ```
8. Verify frontend: Navigate to `http://localhost:3000/delegation` — new record should appear in table

### Test 2: Delegation Chain (multi-step)

**Goal:** Verify that a multi-step delegation chain executes correctly with proper pipeline tracking.

**Steps:**
1. Trigger a delegation chain via council tool:
   ```
   delegate_chain({
     "chain_id": "test-chain-002",
     "steps": [
       {"id": "s1", "description": "Add logging to main.py"},
       {"id": "s2", "description": "Add error handling"},
     ],
     "batch_size": 1,
     "coder_alias": "qwen-160k-UD-fast",
     "reviewer_alias": "nemotron-cascade",
     "max_retries": 1
   })
   ```
2. Monitor execution:
   - Each step should trigger: swap to coder → execute → swap to reviewer → validate → swap back
   - Check `council_main` logs for `CHAIN:` prefixed entries
3. Verify DB records:
   ```sql
   SELECT run_id, chain_id, from_model, to_model, role, batch, retry FROM delegation_runs WHERE chain_id = 'test-chain-002' ORDER BY created_at;
   ```
   - Should see 2 rows (1 coder + 1 reviewer per step × 1 batch)
4. Verify pipeline state:
   - Check `~/.council-memory/pipelines/pipe-*.json` for chain pipeline
   - Verify phase transitions match expected flow
5. Verify frontend: Both records should appear under same chain_id in delegation dashboard

### Test 3: Pipeline State Machine

**Goal:** Verify that the 6-phase pipeline state machine tracks correctly and delegates at each phase.

**Steps:**
1. Trigger a pipeline task:
   ```
   POST /v1/council/pipeline {
     "task": "Implement a simple REST API with FastAPI",
     "project_id": "to_be_reconciled"
   }
   ```
2. Monitor pipeline progression:
   - SCOUT → PLAN → BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE → PENDING_REVIEW → HUMAN_GATE → INDEX → DONE
   - Each phase may trigger delegation (swap to specialist model)
   - Check `council_main` logs for `PIPELINE:` prefixed entries
3. Verify pipeline JSON state:
   ```bash
   cat ~/.council-memory/pipelines/pipe-*.json
   ```
   - `phase` should advance correctly
   - `history` should record each transition
   - `phase_attempts` should track retries
4. Verify delegation records correlate with pipeline phases:
   ```sql
   SELECT dr.chain_id, dr.role, dr.from_model, dr.to_model, dr.created_at
   FROM delegation_runs dr
   WHERE dr.chain_id = '<pipeline_id>'
   ORDER BY dr.created_at;
   ```

### Test 4: Provenance Tracking

**Goal:** Verify that `source_id` and `trace_id` are correctly populated from `memory_rollups`.

**Steps:**
1. After any delegation completes, check the DB:
   ```sql
   SELECT run_id, chain_id, source_id, trace_id FROM delegation_runs ORDER BY created_at DESC LIMIT 5;
   ```
2. Cross-reference with `memory_rollups`:
   ```sql
   SELECT source_id, trace_id, created_at FROM memory_rollups ORDER BY created_at DESC LIMIT 5;
   ```
3. Verify the `get_latest_rollup_provenance()` function returns matching data
4. Verify frontend displays provenance in detail panel

### Test 5: Frontend Dashboard

**Goal:** Verify the delegation dashboard loads, filters, and displays data correctly.

**Steps:**
1. Navigate to `http://localhost:3000/delegation`
2. Verify table loads with all records
3. Test search: Enter "review" in search box — should filter to reviewer roles
4. Test model filter: Select "nemotron-cascade" in "To Model" dropdown
5. Test chain filter: Enter "test-chain-001" — should show only that chain's records
6. Test detail panel: Click any row — slide-over should open with full task/response
7. Test raw MD link: Click "Open Raw MD File" — should download/open the MD file
8. Test pagination: If >20 records, verify page navigation works

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Verify | `council_main.py` | `_delegate()`, `_delegate_chain()`, `_swap_to()` |
| Verify | `api/council_delegations.py` | API endpoints |
| Verify | `memory_service/store/delegation.py` | Store mixin |
| Verify | `frontend/packages/web-core/src/pages/delegation/DelegationDashboard.tsx` | Dashboard |
| Verify | `frontend/packages/local-web/src/routes/_app.delegation.tsx` | Route |

---

## Constraints

- **No concurrent delegation:** `_delegating` flag prevents concurrent delegation (atomic lock)
- **Swap-back guarantee:** `try/finally` ensures swap-back even on error
- **Context limits:** Task truncated to fit target model's context (minus reserved tokens)
- **Pipeline transitions:** Must follow `VALID_TRANSITIONS` map (no invalid phase jumps)
- **Provenance:** `source_id`/`trace_id` are advisory — may be NULL for pre-rollup delegations
- **Llama-swap required:** All model swaps route through llama-swap Go service (`:9292`) — no direct process management fallback

---

## Success Criteria

- [ ] Single delegation completes with proper swap → execute → swap-back cycle
- [ ] Delegation record appears in `delegation_runs` with correct provenance
- [ ] API returns delegation data at all 4 endpoints
- [ ] Frontend dashboard loads and displays records
- [ ] Delegation chain executes multi-step correctly (coder → reviewer → swap-back)
- [ ] Pipeline state machine transitions follow `VALID_TRANSITIONS` map
- [ ] Pipeline JSON state persists to `~/.council-memory/pipelines/`
- [ ] Provenance (`source_id`/`trace_id`) populated from `memory_rollups`
- [ ] Frontend filters (search, model, chain) work correctly
- [ ] Detail panel displays full task/response with raw MD link
- [ ] All existing tests still pass (no regression)

---

## Caveats & Uncertainty

1. **Malformed timestamps:** `created_at` from SQLite may have format `2026-06-17T15:37.590Z` (missing seconds). Frontend handles this with regex fix.
2. **Slot save/restore:** Depends on llama-swap SwapHook (Go service). If llama-swap is down, delegation fails (no fallback).
3. **Context overflow:** If task exceeds target model's context, it's truncated with `[TRUNCATED]` marker. May affect delegation quality.
4. **Concurrent delegation:** Guarded by `_delegation_lock`. Returns 409 if delegation already in progress.
5. **Legacy records:** May 26 delegations have NULL provenance (pre-rollup system). Frontend handles gracefully.
6. **Submodule pushes:** Cannot push to `BloopAI/vibe-kanban.git` or `ikawrakow/ik_llama.cpp.git` (upstream repos without write access). Commits exist locally.

---

## Environment

| Component | Port | Status |
|-----------|------|--------|
| Backend (server.py) | `:8000` | Running (PID 176124) |
| Frontend (local-web) | `:3000` | Running (Vite dev) |
| Llama-swap (Go) | `:9292` | Check `systemctl status llama-swap.service` |
| Pi (chat interface) | CLI | Check `arc-llm.service` |

**Pre-flight checklist:**
- [ ] Backend running: `curl http://localhost:8000/v1/council/status`
- [ ] Frontend running: `curl http://localhost:3000`
- [ ] Llama-swap running: `curl http://localhost:9292/health`
- [ ] Current model loaded: `curl http://localhost:8000/v1/models/current`
- [ ] Delegation API live: `curl http://localhost:8000/v1/council/delegations`

---

## Quick Reference

### Available Models (from registry)
```
qwen-160k-UD-fast    — Coder (fast, large context)
nemotron-cascade      — Reviewer (high quality)
gemma-4-26b-mtp       — Alternative reviewer
```

### Key API Endpoints
```
GET  /v1/council/delegations?page=1&per_page=20&search=&from_model=&to_model=&chain_id=
GET  /v1/council/delegations/run/{run_id}
GET  /v1/council/delegations/chain/{chain_id}
GET  /v1/council/delegations/chain/{chain_id}/raw
GET  /v1/models/current
GET  /v1/models/available
POST /v1/council/pipeline  (advance pipeline state machine)
```

### Key DB Queries
```sql
-- Latest delegations
SELECT * FROM delegation_runs ORDER BY created_at DESC LIMIT 10;

-- Chain grouping
SELECT chain_id, COUNT(*) as calls, GROUP_CONCAT(DISTINCT to_model) as models
FROM delegation_runs GROUP BY chain_id;

-- Provenance check
SELECT run_id, source_id, trace_id FROM delegation_runs WHERE source_id IS NULL;

-- Pipeline state
SELECT pipeline_id, phase, status, created_at FROM pipelines ORDER BY created_at DESC;
```

### Log Patterns
```
=== DELEGATION START: <from> -> <to> ===
DELEGATION: task length=<N> chars, timeout=<N>
CHAIN: <chain_id>: <N> steps, batch=<N>, coder=<alias>, reviewer=<alias>
PIPELINE: <pipeline_id> phase=<PHASE> transition=<FROM>-><TO>
SWAP: <from> -> <to> (llama-swap)
```
