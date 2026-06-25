# Verification Handoff: Memory Service Decoupling

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `14c364` |
| Entity type | `handoff` |
| Short description | Verify memory service decoupling from council_main/server.py, consolidation monitoring migration, and council-tools cleanup |
| Status | `draft` |
| Source references | Session changes (see Changed Files below) |
| Generated | 24-06-2026 |
| Next action / owner | Agent: execute verification checklist, confirm all services functional |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files changed:**

| File | Change |
|------|--------|
| `memory_service/__init__.py` | Added `consolidation` parameter to `__init__()` and `load()`. Skips ArcPipeline, IdleWindowScheduler, SessionWatcher when `False` |
| `memory_service/http_endpoints.py` | Added 3 consolidation monitoring handlers (moved from `api/consolidation_status.py`) |
| `council_main.py` | `MemoryService.load(consolidation=False)`, removed scheduler push code, removed `_wake_scheduler()` calls |
| `api/council_delegations.py` | `MemoryService.load(consolidation=False)` |
| `mcp_server.py` | Both `MemoryService.load(consolidation=False)` |
| `voice_pipeline/http_server.py` | `MemoryService.load(consolidation=False)` |
| `server.py` | Removed `register_consolidation_routes` import and registration |
| `api/consolidation_status.py` | **Deleted** |
| `.pi/agent/extensions/council-tools/index.ts` | Removed `callSummarize`, `callSummarizeChat`, `callFanout`, `callSupervisor`, `/summarize`, `/summarize-session`, `/council-fanout` commands, quit hook, dead comment |

## What Changed

### 1. Memory Service Decoupling
- `MemoryService.load(consolidation=False)` in all non-memory-service processes
- Only `memory_service/__main__.py` loads with `consolidation=True` (default)
- council_main.py, server.py, mcp_server.py, voice_pipeline get: store, router, layer, review, vector_store, cg_store, enricher
- They do NOT get: pipeline, scheduler, session_watcher

### 2. Consolidation Monitoring Migration
- Moved from `api/consolidation_status.py` (server.py) to `memory_service/http_endpoints.py`
- 3 handlers: `consolidation_status`, `consolidation_pipeline`, `consolidation_active_requests`
- Accessible via memory service HTTP: `POST /v1/memory/tool/{handler}` (port 18098)
- Accessible via MCP tools

### 3. Council-Tools Cleanup
- Removed: `callSummarize()`, `callSummarizeChat()`, `callFanout()`, `callSupervisor()` (dead)
- Removed commands: `/summarize`, `/summarize-session`, `/council-fanout`
- Removed: quit hook (`session_shutdown` → `callSummarizeChat`)
- Remaining supervisor calls: `delegate`, `chain`, `chair-gate` (all active)
- All memory tools route through `memoryClient` (MCP SSE, port 18097)

## Verification Checklist

### Phase 1: Service Health

- [ ] `systemctl --user status arc-router` → active, no crash loop
- [ ] `systemctl --user status memory-service` → active, no errors
- [ ] `systemctl --user status memsearch-watch` → active
- [ ] `journalctl --user -u memory-service -n 50 --no-pager` → zero consolidation failures, zero gRPC errors
- [ ] `curl -s http://127.0.0.1:18093/v1/models` → models loaded
- [ ] `curl -s http://127.0.0.1:18098/v1/memory/health` → all components available

### Phase 2: Memory Service Decoupling

- [ ] `grep -n 'consolidation=False' council_main.py` → present
- [ ] `journalctl --user -u memory-service -n 100 --no-pager | grep 'ArcPipeline initialized'` → present (only in memory-service)
- [ ] `journalctl --user -u memory-service -n 100 --no-pager | grep 'SessionWatcher started'` → present (only in memory-service)
- [ ] council_main.py does NOT log "ArcPipeline initialized" or "SessionWatcher started"
- [ ] `curl -s http://127.0.0.1:8000/v1/council/health` → supervisor healthy

### Phase 3: Consolidation Monitoring

- [ ] `curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/consolidation_status -H 'Content-Type: application/json' -d '{}'` → returns tier/rollup/llm data
- [ ] `curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/consolidation_pipeline -H 'Content-Type: application/json' -d '{"days":7}'` → returns lifecycle/pending data
- [ ] `curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/consolidation_active_requests -H 'Content-Type: application/json' -d '{}'` → returns active/failed lists
- [ ] `curl -s http://127.0.0.1:8000/v1/consolidation/status` → **404 or not found** (route removed from server.py)

### Phase 4: Council-Tools Cleanup

- [ ] Pi extension loads without errors (`~/.pi/agent/extensions/council-tools/`)
- [ ] `/council-delegate` command works
- [ ] `/council-chain` command works
- [ ] `/council-recall` command works (memory tool)
- [ ] `/summarize` → **not found** (removed)
- [ ] `/summarize-session` → **not found** (removed)
- [ ] `/council-fanout` → **not found** (removed)
- [ ] No `callSummarize`, `callSummarizeChat`, `callFanout`, `callSupervisor` in index.ts

### Phase 5: Consolidation Pipeline Functionality

- [ ] Trigger a consolidation run (e.g., `curl -s -X POST http://127.0.0.1:18098/v1/memory/tool/consolidation_status -H 'Content-Type: application/json' -d '{}'`)
- [ ] Check `journalctl --user -u memory-service -f` for consolidation activity
- [ ] Verify consolidation completes without timeout (should be < 300s)
- [ ] Verify slot polling works (`_get_slots()` resolves child port via `/v1/models`)
- [ ] Verify `n_keep=0` and `cache_prompt=false` are sent in requests

### Phase 6: No Regression

- [ ] `grep -rn 'consolidation_status\|register_consolidation_routes' super_council/` → only in http_endpoints.py
- [ ] `grep -rn 'callSummarize\|callFanout\|callSupervisor' .pi/agent/extensions/council-tools/` → none
- [ ] `grep -rn 'MemoryService.load' super_council/` → all non-__main__ calls use `consolidation=False`
- [ ] TypeScript compiles: `cd ~/.pi/agent/extensions/council-tools && npx tsc --noEmit` → no errors

## Expected Architecture After Changes

```
council_main.py (supervisor)        server.py (API)
     │                                    │
     ├─ MemoryService(consolidation=False)│
     │   ├─ store, router, layer, review  │
     │   └─ NO pipeline/scheduler/watcher │
     │                                    │
     ├─ delegate, chain, chair-gate ──→ supervisor endpoints
     └─ memory tools ──→ memory-service (MCP SSE :18097)
                                    │
memory-service.service              │
     ├─ MemoryService(consolidation=True)
     │   ├─ ArcPipeline → arc-router (:18093)
     │   ├─ IdleWindowScheduler
     │   └─ SessionWatcher
     └─ HTTP endpoints (:18098)
         ├─ /v1/memory/tool/consolidation_status
         ├─ /v1/memory/tool/consolidation_pipeline
         └─ /v1/memory/tool/consolidation_active_requests
```

## Caveats

- **consolidation_status.py deleted** — any external scripts calling `/v1/consolidation/status` on server.py port will break. Use memory service port 18098 instead.
- **Summarization commands removed** — `/summarize`, `/summarize-session`, `/council-fanout` are gone. If needed, restore from git.
- **quit hook removed** — sessions no longer auto-summarize on `/quit`.
- **callSupervisor removed** — was dead code (never called). If a future feature needs generic supervisor calls, re-add it.

## Completion Gate

- [ ] All Phase 1-6 checks pass
- [ ] No errors in memory-service journal for 10+ minutes
- [ ] Consolidation monitoring accessible via memory service HTTP
- [ ] Council-tools extension loads without errors
- [ ] No regression in existing functionality
