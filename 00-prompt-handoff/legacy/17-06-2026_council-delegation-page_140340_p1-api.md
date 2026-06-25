# Unit 1: Backend API — Delegation Endpoints

**Parent plan:** `17-06-2026_council-delegation-page_140340.md`
**Phase:** 1 of 6
**Dependencies:** Unit 0 (schema + RelationalStore methods must exist)
**Estimated effort:** ~20 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `api/council_delegations.py` — new API module (create)
- `server.py` — mount routes (modify)
- `api/core.py` — reference for route registration pattern

## What This Phase Delivers

Three API endpoints that read from `delegation_runs` table via RelationalStore methods. Returns JSON with pagination, search, and filters.

## Pre-Flight Checklist

- [ ] Unit 0 is complete (delegation_runs table exists, RelationalStore methods work)
- [ ] Read `api/core.py` for route registration pattern
- [ ] Read `server.py` for how routes are mounted

## Implementation Steps

### Step 1: Create API module

Create `api/council_delegations.py`:

```python
"""Council delegation runs API endpoints."""
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from super_council.memory_service import MemoryService

# Endpoints:
# GET /v1/council/delegations — list with pagination/search
# GET /v1/council/delegations/{chain_id} — single delegation detail
# GET /v1/council/delegations/{chain_id}/raw — raw MD file content
```

**`GET /v1/council/delegations`** query params:
- `page` (int, default 1)
- `per_page` (int, default 20, max 100)
- `search` (str, optional — searches task text)
- `from_model` (str, optional)
- `to_model` (str, optional)

Response:
```json
{
  "delegations": [{"chain_id", "from_model", "to_model", "role", "batch", "retry", "created_at", "task_preview", "response_length", "md_file_path"}, ...],
  "total": 236,
  "page": 1,
  "per_page": 20
}
```

**`GET /v1/council/delegations/{chain_id}`** returns full delegation with task + response text.

**`GET /v1/council/delegations/{chain_id}/raw`** reads MD file from filesystem and returns as text/plain. Returns 404 if file not found.

### Step 2: Mount routes in server.py

In `server.py`, find where other council routes are registered (e.g., `register_council_mgmt_routes`). Add:

```python
from super_council.api.council_delegations import register_delegation_routes
# ... in app setup ...
register_delegation_routes(app)
```

Follow the existing pattern for route registration.

### Step 3: Test endpoints

```bash
# After starting server
curl http://localhost:8000/api/v1/council/delegations | python -m json.tool
curl http://localhost:8000/api/v1/council/delegations?page=1\&per_page=5
curl http://localhost:8000/api/v1/council/delegations?to_model=reviewer-arch
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `api/council_delegations.py` | Three endpoints: list, detail, raw |
| Modify | `server.py` | Mount delegation routes |

## Phase-Specific Tests

1. GET `/v1/council/delegations` returns 200 with empty array (if no data)
2. GET `/v1/council/delegations` returns paginated results after backfill
3. GET `/v1/council/delegations?to_model=X` filters correctly
4. GET `/v1/council/delegations/{chain_id}` returns full delegation
5. GET `/v1/council/delegations/{chain_id}/raw` returns MD file content
6. GET `/v1/council/delegations/nonexistent` returns 404

## Completion Gate

- [ ] All three endpoints respond correctly
- [ ] Pagination works (page 1, page 2, etc.)
- [ ] Search/filter params work
- [ ] Raw endpoint serves MD file
- [ ] No regression in existing API endpoints

## Notes for Next Phase

- Frontend (Unit 3) will call `/api/v1/council/delegations` (proxied to localhost:8000)
- `task_preview` in list response should be first 120 chars of task text
- `created_at` is ISO format string
