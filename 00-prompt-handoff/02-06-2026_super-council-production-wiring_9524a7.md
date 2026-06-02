# Execution Prompt: Super Council Production Wiring

**Source spec:** Analysis of `/home/chief/Coding-Projects/7-council/super_council/` codebase
**Review findings:** Run `review-a191cae610fa` (FAIL verdict — 6 findings, 1 critical, 1 high, 3 moderate, 1 low)
**Previous plan:** `02-06-2026_appflowy-v2.1-phase-1-outbound-engine_24d138.md` (stale — see Constraints)
**Generated:** 02-06-2026 by pi
**Goal:** Wire the fully-implemented Council ↔ AppFlowy sync components into a running production system with HTTP API, background workers, and end-to-end verification.

---

## Context: What Exists vs. What's Missing

### Already Complete (Do NOT Re-implement)

| Component | File | Status |
|---|---|---|
| CouncilCoreAPI (Starlette Router) | `api/core.py` | ✅ All CRUD + command handlers, outbox integration on POST/PATCH |
| OutboxWriter | `api/outbox_writer.py` | ✅ Writes to `council_sync.outbox_events` |
| OutboxDispatcher | `workers/outbox.py` | ✅ Polling, retry/backoff (2s/4s/8s), dead letter |
| AppFlowyInboundSync | `workers/inbound.py` | ✅ Polling, snapshot hash, allowlist, PATCH back |
| BindingManager | `workers/binding_manager.py` | ✅ Create, lookup, orphan detection, repair |
| SnapshotHash | `workers/snapshot_hash.py` | ✅ SHA-256 cell canonicalization |
| AppFlowySync (REST client) | `workers/appflowy_sync.py` | ✅ Full AppFlowy REST API wrapper |
| SQL Migrations | `migrations_pg/001_core.sql` through `004_sync_tables.sql` | ✅ All schemas + tables |
| Test Suite | `tests/api/`, `tests/workers/`, `tests/e2e/`, `tests/ui/` | ✅ 100% passing |
| Setup Script | `setup_appflowy_production.py` | ✅ Full bootstrap flow |

### Missing (This Prompt)

| Gap | Severity | Phase |
|---|---|---|
| No production HTTP server mounting `CouncilCoreAPI` | Critical | Phase 1 |
| No worker launcher (OutboxDispatcher + InboundSync) | Critical | Phase 2 |
| `_handle_command` missing outbox event write | High | Phase 3 |
| `mutation_type` CHECK constraint lacks `'command'` | Moderate | Phase 4 |
| No binding seed on production startup | Moderate | Phase 5 |
| No health check endpoint | Low | Phase 6 |
| No `README.md` with startup instructions | Low | Phase 7 |

---

## Architecture (As-Built)

```
┌─────────────────────────────────────────────────────────────┐
│                     PRODUCTION WIRE                         │
│                                                             │
│  User/Tool ──▶  [uvicorn:8000]  ◀── CouncilCoreAPI         │
│                     │                                       │
│                     │  (psycopg2 raw SQL)                   │
│                     ▼                                       │
│              PostgreSQL (council_test)                      │
│              ┌──────────────────────────┐                   │
│              │ council_core.*           │  entities         │
│              │ council_ops.*            │  workflows        │
│              │ council_sync.*           │  outbox/bindings  │
│              └──────────────────────────┘                   │
│                     │                                       │
│      ┌──────────────┼──────────────┐                        │
│      ▼              ▼              ▼                        │
│  [Worker 1]     [Worker 2]     [Worker 3]                  │
│  OutboxDisp.    InboundSync    BindingMgr                  │
│  (poll outbox)  (poll AppFlowy)(orphan check)              │
│      │              │              │                        │
│      ▼              ▼              │                        │
│  AppFlowy REST ◀─▶ AppFlowy REST  │                        │
│  (localhost:8080)                 │                        │
│                                  │                        │
│  Memory Service (separate)       │                        │
│  [uvicorn:18096] MCP server      │                        │
│                                  │                        │
└─────────────────────────────────────────────────────────────┘
```

### Database Note

The system uses **PostgreSQL exclusively** (`council_test` database). There is no SQLite for the Council system. SQLite is only used by the Memory Service (`~/.council-memory/pipelines.db`) and codegraph index — separate subsystems.

---

## Phase 1: Production HTTP Server

**What:** Create a server entry point that mounts `CouncilCoreAPI` on uvicorn, making the API accessible at `http://localhost:8000/v1/`.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `server.py` | Main entry point: mount API, start uvicorn |

**Steps:**

1. Create `server.py` in project root (`/home/chief/Coding-Projects/7-council/super_council/`)
2. Import `CouncilCoreAPI` from `api.core`
3. Create a Starlette `Application` with middleware:
   - `CORSMiddleware` (allow origins from env `ALLOWED_ORIGINS`, default `http://localhost:8080`)
   - `TrustedHostMiddleware` (optional, default `*`)
4. Register `CouncilCoreAPI` routes on the application
5. Add a `/health` endpoint returning `{"status": "ok", "timestamp": ..., "components": {"db": ..., "appflowy": ...}}`
6. Start uvicorn on host `0.0.0.0`, port from env `COUNCIL_API_PORT` (default `8000`)
7. Add `--workers` flag for gunicorn/uvicorn worker count (default 1)

**Implementation Details:**

```python
# server.py structure
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from super_council.api.core import CouncilCoreAPI
import uvicorn
import os

app = Starlette()
app.add_middleware(CORSMiddleware, allow_origins=[...])

api = CouncilCoreAPI()
api.register(app.router)
api.register_sync_routes(app.router)

@app.route("/health")
async def health(request):
    # Check DB connectivity, return status dict
    ...

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=os.getenv("COUNCIL_API_HOST", "0.0.0.0"),
        port=int(os.getenv("COUNCIL_API_PORT", "8000")),
        log_level="info",
    )
```

**Constraints:**
- Do NOT use SQLAlchemy ORM — the API uses psycopg2 raw SQL
- The `CouncilCoreAPI` constructor takes no arguments (verified in tests)
- The API's `register(router)` method mounts all CRUD routes
- The API's `register_sync_routes(router)` method mounts sync management routes

**Tests:**
- Start server, `curl http://localhost:8000/health` → 200 OK
- `curl http://localhost:8000/v1/projects` → 200 OK (empty list or existing data)

**Dependencies:** None (Phase 1 is independent)

---

## Phase 2: Worker Launcher

**What:** Create a process launcher that starts OutboxDispatcher, AppFlowyInboundSync, and BindingManager orphan-check as background workers.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `workers/launcher.py` | Start all workers as daemon threads |
| Modify | `setup_appflowy_production.py` | Add `--start-workers` flag (optional) |

**Steps:**

1. Create `workers/launcher.py` with:
   - `WorkerLauncher` class that configures and starts all workers
   - Each worker runs in a separate `threading.Thread` (daemon=True)
   - Graceful shutdown via `threading.Event`
   - Logging with worker name prefix

2. Worker configuration from environment:
   - `OUTBOX_POLL_INTERVAL` (default `5.0` seconds)
   - `INBOUND_POLL_INTERVAL` (default `5.0` seconds)
   - `ORPHAN_CHECK_INTERVAL` (default `300.0` seconds — 5 minutes)
   - `DB_CONFIG` from existing env vars (`COUNCIL_DB_HOST`, `COUNCIL_DB_NAME`, `COUNCIL_DB_USER`)

3. Worker startup sequence:
   - Load DB config from environment
   - Initialize `AppFlowySync` (REST client)
   - Initialize `BindingManager(db_config, appflowy_sync)`
   - Initialize `OutboxDispatcher(db_config, appflowy_sync, binding_manager)`
   - Initialize `AppFlowyInboundSync(db_config, appflowy_sync, council_api_base_url)`
   - Start threads in order: OutboxDispatcher → InboundSync → OrphanCheck

4. Add SIGINT/SIGTERM handler for graceful shutdown:
   - Set shutdown event
   - Wait for each thread to finish current cycle (max 30s timeout)
   - Log shutdown status

5. Add `--daemon` flag for background mode (write PID file to `~/.council-memory/worker.pid`)

**Implementation Details:**

```python
# workers/launcher.py structure
import threading
import signal
import logging
from .outbox import OutboxDispatcher
from .inbound import AppFlowyInboundSync
from .binding_manager import BindingManager
from .appflowy_sync import AppFlowySync

class WorkerLauncher:
    def __init__(self, db_config, appflowy_config):
        self._shutdown = threading.Event()
        self._threads = []
        ...

    def start(self):
        # Initialize all workers
        # Start threads
        # Block on shutdown event
        ...

    def _run_outbox_dispatcher(self):
        # dispatcher = OutboxDispatcher(...)
        # while not self._shutdown.is_set():
        #     dispatcher.process_cycle()
        #     self._shutdown.wait(interval)
        ...

    def _run_inbound_sync(self):
        # sync = AppFlowyInboundSync(...)
        # while not self._shutdown.is_set():
        #     sync.process_cycle()
        #     self._shutdown.wait(interval)
        ...

    def _run_orphan_checker(self):
        # manager = BindingManager(...)
        # while not self._shutdown.is_set():
        #     manager.check_orphans()
        #     self._shutdown.wait(interval)
        ...
```

**Constraints:**
- Workers must NOT block the main thread
- Each worker must catch and log exceptions (not crash the process)
- Use existing worker classes — do NOT reimplement OutboxDispatcher or InboundSync
- The `OutboxDispatcher` and `AppFlowyInboundSync` already have `process_cycle()` methods that return stats dicts

**Tests:**
- Import `WorkerLauncher`, verify all 3 threads start
- Verify graceful shutdown within timeout
- Verify worker stats logging

**Dependencies:** Phase 1 (server must be running for InboundSync to PATCH back)

---

## Phase 3: Command Outbox Integration

**What:** Add outbox event writing to `_handle_command` in `api/core.py`. Currently only `_handle_create` and `_handle_patch` write outbox events. Commands (workflow transitions, state changes) are invisible to AppFlowy.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `api/core.py` | Add outbox write to `_handle_command` |

**Steps:**

1. Read the current `_handle_command` implementation (line ~370-430 in `api/core.py`)
2. After the `UPDATE ... SET updated_at = now(), revision = revision + 1` statement:
   - Fetch the updated row
   - Convert to dict via `_entity_to_dict(row)`
   - Call `outbox_writer.write_outbox_event(session, entity_type, entity_id, "command", new_revision, entity_dict)`
3. Ensure the outbox write is in the same transaction (same `session` object)
4. The existing `session.commit()` after idempotency store will commit both the entity update AND the outbox event

**Code Pattern (follow existing `_handle_patch`):**

```python
# After UPDATE in _handle_command:
cur.execute(f"SELECT * FROM council_core.{table} WHERE id = %s", (entity_id,))
row = cur.fetchone()
if row:
    entity_dict = _entity_to_dict(row)
    new_revision = res.revision  # from the UPDATE RETURNING
    outbox_writer.write_outbox_event(
        session, entity_type, entity_id, "command", new_revision, entity_dict
    )
```

**Constraints:**
- Use the existing `outbox_writer` module — do NOT create new outbox logic
- The mutation_type will be `"command"` — this requires the CHECK constraint update (Phase 4)
- Follow the exact same pattern as `_handle_patch` for consistency

**Tests:**
- Send a command via API
- Verify `council_sync.outbox_events` has a row with `mutation_type = 'command'`
- Verify `delivery_state = 'pending'`

**Dependencies:** Phase 4 (CHECK constraint must allow `'command'` first)

---

## Phase 4: Migration — mutation_type CHECK Constraint

**What:** Update `migrations_pg/004_sync_tables.sql` to allow `'command'` in the `mutation_type` CHECK constraint.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `migrations_pg/004_sync_tables.sql` | Add `'command'` to CHECK constraint |
| Create | `migrations_pg/005_add_command_mutation.sql` | Migration for running systems |

**Steps:**

1. In `migrations_pg/004_sync_tables.sql`, find the line:
   ```sql
   CHECK (mutation_type IN ('created', 'updated', 'deleted'))
   ```
   Replace with:
   ```sql
   CHECK (mutation_type IN ('created', 'updated', 'deleted', 'command'))
   ```

2. Create `migrations_pg/005_add_command_mutation.sql` for systems that already have the table:
   ```sql
   -- Migration 005: Add 'command' to mutation_type CHECK constraint
   -- Required for _handle_command outbox integration

   BEGIN;

   -- Drop existing CHECK constraint
   ALTER TABLE council_sync.outbox_events
       DROP CONSTRAINT IF EXISTS outbox_events_mutation_type_check;

   -- Add updated CHECK constraint
   ALTER TABLE council_sync.outbox_events
       ADD CONSTRAINT outbox_events_mutation_type_check
       CHECK (mutation_type IN ('created', 'updated', 'deleted', 'command'));

   COMMIT;
   ```

3. Update `tests/db/fixtures.py` `run_migrations()` to include migration 005.

**Constraints:**
- Use `DROP CONSTRAINT IF EXISTS` to make the migration idempotent
- The constraint name must match the existing one (verify in `004_sync_tables.sql`)

**Tests:**
- Run migrations, verify constraint exists with `'command'`
- Insert a row with `mutation_type = 'command'` — must succeed
- Insert a row with `mutation_type = 'invalid'` — must fail

**Dependencies:** None (can run before Phase 3)

---

## Phase 5: Binding Seed + End-to-End Verification

**What:** Ensure bindings exist between Council entities and AppFlowy rows, then verify the full bidirectional flow.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `setup_appflowy_production.py` | Add `--seed-bindings` flag |
| Create | `tests/e2e/test_production_flow.py` | Full integration test |

**Steps:**

1. In `setup_appflowy_production.py`, add `--seed-bindings` flag that:
   - Creates sample entities via the API (or directly in DB if API not running)
   - Creates corresponding rows in AppFlowy
   - Creates bindings via `BindingManager.create_binding()`
   - Logs all binding IDs for verification

2. Create `tests/e2e/test_production_flow.py` with:
   - **Test outbound:** Create entity via API → verify outbox event → run dispatcher → verify AppFlowy row exists
   - **Test inbound:** Edit AppFlowy row → run inbound sync → verify Council entity updated
   - **Test command:** Send command → verify outbox event with `mutation_type='command'` → verify AppFlowy updated
   - **Test idempotency:** Re-run dispatcher on already-sent event → verify no duplicate

3. The test should use the real AppFlowy mock server from `tests/e2e/conftest.py` (already exists)

**Constraints:**
- Tests must use the real worker classes, not mocks
- Tests must verify database state, not just HTTP responses

**Tests:**
- All 4 test cases pass
- Outbound flow: Council → AppFlowy verified
- Inbound flow: AppFlowy → Council verified
- Command flow: Council command → AppFlowy verified

**Dependencies:** Phase 1 (server), Phase 2 (workers), Phase 3 (command outbox), Phase 4 (migration)

---

## Phase 6: Health Check Endpoint

**What:** Add a `/health` endpoint that reports the status of all components.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `server.py` | Add `/health` route |

**Steps:**

1. Add `/health` endpoint to `server.py`
2. Health check verifies:
   - PostgreSQL connectivity (simple `SELECT 1`)
   - AppFlowy REST API reachability (HEAD to base URL)
   - Outbox pending count (SELECT COUNT from `council_sync.outbox_events WHERE delivery_state = 'pending'`)
3. Return JSON:
   ```json
   {
     "status": "ok|degraded",
     "timestamp": "2026-06-02T...",
     "components": {
       "database": {"status": "ok", "latency_ms": 2},
       "appflowy": {"status": "ok", "latency_ms": 45},
       "outbox": {"status": "ok", "pending_count": 0}
     },
     "version": "0.1.0"
   }
   ```

**Constraints:**
- Health check must NOT block (timeout each component at 5s)
- Return 503 if database is down, 200 with `"degraded"` if AppFlowy is unreachable

**Tests:**
- Health endpoint returns 200 with all components ok
- Health endpoint returns 503 when DB is unreachable

**Dependencies:** Phase 1 (server)

---

## Phase 7: Documentation

**What:** Create README with startup instructions, environment variables, and architecture overview.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `docs/production-setup.md` | Full production deployment guide |

**Content:**

1. **Prerequisites:** PostgreSQL, AppFlowy Cloud, environment variables
2. **Quick Start:** One-command startup (`python server.py & python -m workers.launcher`)
3. **Environment Variables:** Full table of all config options
4. **Architecture:** Diagram of the sync flow
5. **Troubleshooting:** Common issues (DB connection, AppFlowy auth, binding errors)
6. **Monitoring:** Health check endpoint, log locations

**Constraints:**
- Include actual environment variable names (not placeholders)
- Include actual port numbers (8000 for API, 8080 for AppFlowy)

**Tests:**
- N/A (documentation)

**Dependencies:** All phases complete

---

## Constraints (Global)

- **Raw SQL Only:** The codebase uses psycopg2 + `sqlalchemy.text()` for raw SQL. Do NOT introduce SQLAlchemy ORM models. The previous plan (`02-06-2026_appflowy-v2.1-phase-1-outbound-engine_24d138.md`) prescribed `council_sync/models.py` with SQLAlchemy — this is architecturally wrong and must be avoided.
- **Existing Schemas Only:** The schemas are `council_core`, `council_ops`, `council_sync`. There are no `appflowy_*` schemas.
- **No Double Commits:** The `_handle_patch` double-commit pattern (session.commit() after outbox, then again after idempotency) should be consolidated into a single commit at the end of the transaction. Fix in Phase 3.
- **PostgreSQL Only:** The Council system uses PostgreSQL exclusively. Do not introduce SQLite.
- **Preserve Test Coverage:** All existing tests must continue to pass. No regression.
- **Worker Isolation:** Workers must not crash the main process. Each worker catches and logs its own exceptions.

---

## Success Criteria

- [ ] `server.py` starts and serves API at `http://localhost:8000/v1/`
- [ ] `workers/launcher.py` starts all 3 workers (OutboxDispatcher, InboundSync, OrphanCheck)
- [ ] `_handle_command` writes outbox events with `mutation_type = 'command'`
- [ ] `mutation_type` CHECK constraint includes `'command'`
- [ ] Full outbound flow works: POST entity → outbox event → AppFlowy row created
- [ ] Full inbound flow works: AppFlowy edit → inbound sync → Council entity updated
- [ ] Full command flow works: API command → outbox event → AppFlowy row updated
- [ ] `/health` endpoint reports component status
- [ ] All existing tests pass (no regression)
- [ ] `docs/production-setup.md` exists with startup instructions
- [ ] `setup_appflowy_production.py --seed-bindings` creates full binding chain

---

## File Map (Summary)

| Action | File | Phase |
|--------|------|-------|
| Create | `server.py` | 1 |
| Create | `workers/launcher.py` | 2 |
| Modify | `api/core.py` | 3 |
| Modify | `migrations_pg/004_sync_tables.sql` | 4 |
| Create | `migrations_pg/005_add_command_mutation.sql` | 4 |
| Modify | `tests/db/fixtures.py` | 4 |
| Modify | `setup_appflowy_production.py` | 5 |
| Create | `tests/e2e/test_production_flow.py` | 5 |
| Modify | `server.py` | 6 |
| Create | `docs/production-setup.md` | 7 |

**Total:** 4 new files, 5 modified files, 7 phases

---

## Execution Order

```
Phase 4 (migration)  ──┐
                        ├──▶ Phase 3 (command outbox) ──▶ Phase 5 (E2E tests)
Phase 1 (server)       ──┘                                ▲
                                                          │
Phase 2 (workers) ────────────────────────────────────────┘
                                                          │
Phase 6 (health) ──▶ (depends on Phase 1)                 │
                                                          │
Phase 7 (docs) ──▶ (after all phases complete)            │
```

**Recommended execution:** Phase 4 → Phase 1 → Phase 2 → Phase 3 → Phase 6 → Phase 5 → Phase 7

---

## Caveats & Uncertainty

1. **AppFlowy credentials:** The setup script requires `APPFLOWY_EMAIL` and `APPFLOWY_PASSWORD` environment variables. These must be configured before running.
2. **AppFlowy workspace:** The script assumes a specific workspace structure (workspace → folder → databases). If the workspace differs, the script will fail at database discovery.
3. **Port conflicts:** Default ports (8000 for API, 8080 for AppFlowy, 18096 for Memory Service) may conflict with other services.
4. **Double-commit in `_handle_patch`:** The existing code has two `session.commit()` calls. The second is a no-op but should be cleaned up in Phase 3.
5. **Worker thread safety:** Using `threading.Thread` for workers is simple but doesn't provide process isolation. For production, consider `multiprocessing` or a proper process manager (supervisord).
6. **InboundSync API base URL:** The `AppFlowyInboundSync` defaults to `http://localhost:8000` — this must match the actual API port.

---

## Anti-Patterns to Avoid

- ❌ Creating `council_sync/models.py` with SQLAlchemy ORM — use raw SQL
- ❌ Creating `appflowy_*` schemas — use existing `council_sync`
- ❌ Re-implementing OutboxDispatcher or InboundSync — they already exist
- ❌ Running workers in the main thread — use daemon threads
- ❌ Blocking health check on slow components — timeout each at 5s
- ❌ Making tests depend on real AppFlowy Cloud — use mock server for tests
