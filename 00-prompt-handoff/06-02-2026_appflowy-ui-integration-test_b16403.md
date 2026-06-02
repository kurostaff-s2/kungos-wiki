# AppFlowy UI Integration Test — Remaining Items Handoff

**Source spec:** `super_council/tests/ui/fixtures/appflowy_ui_driver.py` (cell editing rewrite)
**Reference doc:** `llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md`
**Previous handoff:** `02-06-2026_appflowy-ui-integration-test_906f47.md` (superseded)
**Generated:** 06-02-2026
**Goal:** Complete the AppFlowy UI integration test verification — resolve workspace setup, seed databases, and validate cell editing across all 5 entity types.

---

## Completed Items

### Phase 0: Login Blocker — RESOLVED
- **Root cause:** `admin@example.com` existed in Gotrue but was missing from `af_user` table and had no `af_workspace` entry. `/api/user/profile` returned `code: 1024, "User not found"`.
- **Fix applied:** Direct SQL inserts into `appflowy-cloud-postgres-1`:
  - `af_user` record: uid=`597820294459035649`, uuid=`dcf20331-093d-49bb-9f44-6e2a3a1c0e0e`, email=`admin@example.com`
  - `af_workspace` entry: linked to owner_uid, role=Owner
- **Verified:** Playwright navigates to `/app/{workspace_id}`, DOM renders "My Workspace", "Search", "New page" with expected test IDs.

### Environment State
- AppFlowy docker-compose stack running (postgres, gotrue, appflowy_cloud, nginx)
- API signin works: `admin@example.com` / `password` → access_token
- UI login works: Two-step flow (email → password) completes successfully
- Database: `appflowy-cloud-postgres-1` (DB: `postgres`, User: `postgres`, Pass: `password`)

---

## Current Blocker: Workspace Has No Folder Structure

### Problem
The workspace for `admin@example.com` (workspace_id: `abb0ba52-f401-49b1-a67f-cd341652381c`) was created via direct SQL inserts, bypassing the normal user verification flow. The `GettingStartedTemplate` was never applied, so:

- **No Folder collab** (partition_key=3) exists in `af_collab`
- **No root space** exists in `af_folder_view`
- **No workspace database collab** (partition_key=2) exists
- API calls to `POST /api/workspace/{ws}/page-view` fail with `code: -2, "Record not found"`

### Two Workspaces Exist

| Workspace ID | Owner | Email | Template Applied | Folder Collab |
|---|---|---|---|---|
| `0cd1391c-80cb-4b4a-9095-8a62375a9b23` | uid: 597820294459035648 | `ui-test@appflowy.io` | YES | YES |
| `abb0ba52-f401-49b1-a67f-cd341652381c` | uid: 597820294459035649 | `admin@example.com` | NO | NO |

The `ui-test@appflowy.io` workspace has the full template: Folder collab, "General" space, "Getting started" document, "To-dos" board, workspace database collab, and 76 total collabs.

### Resolution Options

**Option A (Recommended): Use the `ui-test@appflowy.io` workspace**
- Update the password for `ui-test@appflowy.io` in Gotrue (auth.users table)
- Point tests to this workspace (it already has folder structure)
- Requires: Generate bcrypt hash for "password" and update `auth.users.encrypted_password`

**Option B: Fix the admin workspace**
- Copy the Folder collab from the `ui-test@appflowy.io` workspace
- Or manually create a Folder collab + workspace database collab
- Requires: Understanding the protobuf-encoded Folder structure

**Option C: Create a new user via normal flow**
- Sign up a new user via `POST /gotrue/signup` (triggers template)
- Use that user's workspace
- Requires: New credentials, but clean state

---

## Remaining Phases

### Phase 1: Resolve Workspace Setup

**What:** Get a workspace with folder structure so databases can be created.

**Recommended approach (Option A):**
1. Generate bcrypt hash for "password":
   ```bash
   pip install bcrypt
   python3 -c "import bcrypt; print(bcrypt.hashpw(b'password', bcrypt.gensalt(rounds=10)).decode())"
   ```
2. Update the `ui-test@appflowy.io` user password:
   ```sql
   UPDATE auth.users SET encrypted_password = '$2a$10$NEW_HASH' WHERE email = 'ui-test@appflowy.io';
   ```
3. Verify API signin:
   ```bash
   curl -X POST http://localhost/gotrue/token?grant_type=password \
     -H "Content-Type: application/json" \
     -H "apikey: hello456" \
     -d '{"email":"ui-test@appflowy.io","password":"password"}'
   ```
4. Verify workspace access:
   ```bash
   WS_ID=$(curl -s -H "Authorization: Bearer $TOKEN" http://localhost/api/workspace | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['workspace_id'])")
   # Should return: 0cd1391c-80cb-4b4a-9095-8a62375a9b23
   ```

**Alternative (Option C):**
1. Sign up new user:
   ```bash
   curl -X POST http://localhost/gotrue/signup \
     -H "Content-Type: application/json" \
     -H "apikey: hello456" \
     -d '{"email":"ui-test2@appflowy.io","password":"password"}'
   ```
2. Verify user exists in `af_user` table (if not, insert manually)
3. Use the new workspace (template applied automatically)

**Files:** None (database operations only)

**Success:** API signin works, workspace has folder structure, `POST /api/workspace/{ws}/page-view` succeeds.

---

### Phase 2: Fix Database Creation API

**What:** Update `seed_data.py` to use correct AppFlowy API endpoints.

**Current issue:** `seed_data.py` uses `POST /api/workspace/{ws}/database` which returns 405 (Method Not Allowed).

**Correct flow:**
1. Create page view (creates database):
   ```
   POST /api/workspace/{workspace_id}/page-view
   Body: {"parent_view_id": "{space_view_id}", "layout": 1, "name": "Work Items"}
   ```
   - `layout: 1` = Grid (database)
   - `parent_view_id` = a space view ID (e.g., "General" space)
   - Response includes `view_id` and creates database collab

2. Add fields:
   ```
   POST /api/workspace/{workspace_id}/database/{database_id}/fields
   Body: {"name": "Title", "type": "rich_text"}
   ```
   - Note: endpoint is `/fields` (plural), not `/field`

3. Create rows:
   ```
   POST /api/workspace/{workspace_id}/database/{database_id}/row
   Body: {"rows": [{"cells": {"Title": "value"}}]}
   ```

**API Route Reference (from `src/api/workspace.rs`):**
```
POST /api/workspace/{workspace_id}/space              → create space
POST /api/workspace/{workspace_id}/page-view           → create page/database view
GET  /api/workspace/{workspace_id}/page-view/{view_id} → get page view
GET  /api/workspace/{workspace_id}/database            → list databases
POST /api/workspace/{workspace_id}/database/{db_id}/fields  → add fields
POST /api/workspace/{workspace_id}/database/{db_id}/row     → create row
PUT  /api/workspace/{workspace_id}/database/{db_id}/row     → update row
GET  /api/workspace/{workspace_id}/database/{db_id}/fields  → get fields
```

**Files:** `super_council/tests/ui/fixtures/seed_data.py`

**Steps:**
1. Update `_ensure_database()` to use `POST /api/workspace/{ws}/page-view` with `layout: 1`
2. Update column creation to use `/fields` endpoint (plural)
3. Get the space view ID from the folder metadata (or create a space first)
4. Test database creation manually

**Success:** `seed_data.py` creates all 5 databases with correct columns.

---

### Phase 3: Seed Test Databases

**What:** Run seed_data.py to create all 5 databases with seed rows.

**Steps:**
1. Ensure workspace is resolved (Phase 1)
2. Ensure seed_data.py uses correct API (Phase 2)
3. Run seed:
   ```python
   from super_council.tests.ui.fixtures.seed_data import SeedDataGenerator
   gen = SeedDataGenerator(
       appflowy_base_url="http://localhost",
       appflowy_email="<resolved_email>",
       appflowy_password="<resolved_password>",
   )
   result = gen.seed_all()
   ```
4. Verify databases exist:
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" "http://localhost/api/workspace/$WS_ID/database" | python3 -m json.tool
   ```

**Files:** `super_council/tests/ui/fixtures/seed_data.py`

**Success:** All 5 databases exist with correct columns and seed rows.

---

### Phase 4: Update UI Driver for Two-Step Login

**What:** Ensure `appflowy_ui_driver.py` handles the two-step login flow correctly.

**Current state:** The driver has `_try_appflowy_two_step_login()` which handles email → password flow. Login works for `admin@example.com`.

**Changes needed:**
1. Update default credentials to use resolved workspace user
2. Verify base URL is `http://localhost` (not `:8080`)
3. Ensure `navigate_to_database()` works with seeded databases

**Files:** `super_council/tests/ui/fixtures/appflowy_ui_driver.py`

**Success:** Driver logs in and navigates to seeded databases.

---

### Phase 5: Verify Cell Resolution Layer

**What:** Confirm `_get_column_id()` and `_resolve_cell()` target correct cells.

**Steps:**
1. Run column verification tests:
   ```bash
   APPFLOWY_BASE_URL=http://localhost \
   APPFLOWY_EMAIL="<resolved>" \
   APPFLOWY_PASSWORD="<resolved>" \
   python3 -m pytest tests/ui/test_appflowy_databases.py -v -k "columns"
   ```
2. Verify column IDs are extracted correctly
3. Check that all expected columns are found

**Success:** All 5 databases report correct column counts (9, 5, 7, 5, 6).

---

### Phase 6: Test Cell Editing

**What:** Verify cell editing works for all field types.

**Target columns:**
- **Text:** Title, Description, Notes, Body, Name, Template Body
- **Select:** Priority, State, Status, Severity, Verdict
- **Multi-select:** Tags
- **Date:** Due Date
- **Number:** Confidence

**Steps:**
1. Run editability tests:
   ```bash
   APPFLOWY_BASE_URL=http://localhost \
   APPFLOWY_EMAIL="<resolved>" \
   APPFLOWY_PASSWORD="<resolved>" \
   python3 -m pytest tests/ui/test_appflowy_editability.py -v
   ```
2. Verify each field type edits correctly
3. Document any field types that need special handling

**Success:** All editable fields accept edits and verify correctly.

---

### Phase 7: Full Test Suite Run

**What:** Run all 61 UI tests and verify results.

**Steps:**
1. Run full suite:
   ```bash
   APPFLOWY_BASE_URL=http://localhost \
   APPFLOWY_EMAIL="<resolved>" \
   APPFLOWY_PASSWORD="<resolved>" \
   APPFLOWY_TIMEOUT=30 \
   python3 -m pytest tests/ui/ -v --tb=short
   ```
2. Count passing/failing tests
3. Document remaining failures

**Success:** All editability tests pass. Remaining failures documented.

---

## Key Technical Findings

### AppFlowy Cloud API Structure
- **No direct "create database" endpoint** — databases are created via `POST /api/workspace/{ws}/page-view` with `layout: 1` (Grid)
- **Fields endpoint is plural** — `/fields` not `/field`
- **Folder collab required** — All page/database operations require a Folder collab (partition_key=3) in the workspace
- **Workspace template creates folder** — `GettingStartedTemplate` creates Folder collab, "General" space, "Getting started" doc, "To-dos" board

### Database Collab Types (partition_key)
| Key | Type | Description |
|-----|------|-------------|
| 0 | Document | Page content |
| 1 | Database | Grid/Board/Calendar data |
| 2 | WorkspaceDatabase | Workspace-level database metadata |
| 3 | Folder | Folder hierarchy |
| 4 | DatabaseRow | Individual row data |
| 5 | UserAwareness | Presence/cursor data |

### Gotrue Authentication
- **API key:** `hello456` (header: `apikey`)
- **Signup:** `POST /gotrue/signup` with apikey header
- **Signin:** `POST /gotrue/token?grant_type=password` with apikey header
- **User storage:** `auth.users` table in PostgreSQL (search_path=auth)
- **Password hashing:** bcrypt ($2a$10$)

### Two Users / Two Workspaces
| Email | UID | Workspace ID | Template | Status |
|-------|-----|--------------|----------|--------|
| `admin@example.com` | 597820294459035649 | `abb0ba52-f401-49b1-a67f-cd341652381c` | NO | Login works, no databases |
| `ui-test@appflowy.io` | 597820294459035648 | `0cd1391c-80cb-4b4a-9095-8a62375a9b23` | YES | Password unknown, full template |

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `tests/ui/fixtures/seed_data.py` | Fix database creation API endpoints |
| Modify | `tests/ui/fixtures/appflowy_ui_driver.py` | Update credentials, verify login flow |
| DB Update | `auth.users` | Set password for `ui-test@appflowy.io` OR create new user |

---

## Constraints

- **No hardcoded credentials** — Use environment variables only
- **Idempotent seeding** — Seed data can run multiple times without errors
- **Clean skip** — Tests skip gracefully when AppFlowy unavailable
- **No silent failures** — All errors logged with context
- **API-only database creation** — Use REST API, not direct SQL (except for auth fixes)

---

## Success Criteria

- [ ] Phase 1: Workspace with folder structure accessible via API
- [ ] Phase 2: `seed_data.py` creates databases via correct API endpoints
- [ ] Phase 3: All 5 databases seeded with correct columns and rows
- [ ] Phase 4: UI driver logs in and navigates to databases
- [ ] Phase 5: Column resolution returns correct IDs for all columns
- [ ] Phase 6: Cell editing works for all field types
- [ ] Phase 7: Full test suite passes or failures documented

---

## Environment Setup

```bash
# AppFlowy stack should already be running
docker ps --filter "name=appflowy-cloud"

# Database connection
# Host: localhost (via nginx)
# API: http://localhost/api/...
# Gotrue: http://localhost/gotrue/...
# PostgreSQL: appflowy-cloud-postgres-1 (DB: postgres, User: postgres, Pass: password)

# Run tests
cd /home/chief/Coding-Projects/7-council/super_council
APPFLOWY_BASE_URL=http://localhost \
APPFLOWY_EMAIL="<resolved>" \
APPFLOWY_PASSWORD="<resolved>" \
APPFLOWY_TIMEOUT=30 \
python3 -m pytest tests/ui/ -v
```
