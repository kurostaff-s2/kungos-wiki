# Legacy Code Removal — Auth & Identity Alignment

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `f4101b` |
| Entity type | `handoff` |
| Short description | Remove dead serializers, function-based views, and non-spec-compliant response patterns from `users/` and `backend/` |
| Status | `draft` |
| Source references | `Kung_OS/specs/endpoint_contract_spec.md` (§3.1 Response Envelope, §4.1 Auth Endpoints, §4.3 Auth Migration Notes), `25-06-2026_auth-api-target-alignment_9152b4.md`, `26-06-2026_m1-identity-migration_1a1902.md` |
| Generated | 26-06-2026 |
| Next action / owner | Execute Phase 1 (dead serializers), Phase 2 (dead views), Phase 3 (error envelope compliance), Phase 4 (legacy response fields) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` (§3.1 Error Envelope, §4.3 Auth Migration Notes)
- `/home/chief/llm-wiki/00-prompt-handoff/25-06-2026_auth-api-target-alignment_9152b4.md`
- `/home/chief/llm-wiki/00-prompt-handoff/26-06-2026_m1-identity-migration_1a1902.md`
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend depends on login/me response shapes)
**Key files for this task:**
- `users/serializers.py` (dead login serializers)
- `users/views.py` (dead function-based views)
- `users/api/viewsets.py` (non-spec error responses, legacy response fields)
- `backend/utils.py` (shared utilities)
- `backend/auth_utils.py` (legacy resolve_access)

## Background

Phases 1-3 of the spec alignment handoff (`26-06-2026_spec-alignment-remaining_1e9f8e.md`) completed:
- **Phase 1:** `api_error()` helper created in `backend/utils.py`, 17 callers updated
- **Phase 2:** `SpecPagination` created in `users/pagination.py`, registered globally
- **Phase 3:** `TenantContextViewSet` created, `bgswitch`/`AccessLevelViewSet` rewritten to RBAC

Three categories of legacy code remain that do not conform to the target spec:

1. **Dead serializers** — `AdminLoginSerializer`, `StaffLoginSerializer`, `RebLoginSerializer` have zero callers across the codebase
2. **Dead function-based views** — 10 `@api_view` decorated functions in `users/views.py` are not routed by any URL config and have been superseded by ViewSets
3. **Non-spec-compliant response patterns** — `AuthViewSet` methods return flat error dicts instead of `**api_error()` envelopes; `_build_user_data` includes legacy `accesslevel[]` fields

**Excluded from scope:**
- `Accesslevel` model/table (55-col DEPRECATED table) — kept for frontend backward compat per alignment doc
- `Switchgroupmodel` — kept until `resolve_access()` frontend migration completes (120+ call sites)
- `KuroUser` model — migrated via separate handoff (`26-06-2026_m1-identity-migration_1a1902.md`)
- `resolve_access()` rewrite — deferred until frontend fully migrates to RBAC

---

## Phase 1: Remove Dead Login Serializers

**What:** Delete three login serializers with zero callers from `users/serializers.py`.

**Evidence of zero callers:**
```
grep -rn "AdminLoginSerializer\|StaffLoginSerializer\|RebLoginSerializer" --include="*.py"
# Only self-references in users/serializers.py (class definitions)
# No imports, no instantiations, no URL routing references
```

**Files:**
- Modify `users/serializers.py`

**Steps:**

1. Read `users/serializers.py` and locate the three dead serializers:
   - `AdminLoginSerializer` (line ~XX)
   - `StaffLoginSerializer` (line ~XX)
   - `RebLoginSerializer` (line ~XX)

2. Verify zero callers one more time (safety check):
   ```bash
   grep -rn "AdminLoginSerializer\|StaffLoginSerializer\|RebLoginSerializer" --include="*.py" | grep -v "class AdminLoginSerializer\|class StaffLoginSerializer\|class RebLoginSerializer"
   ```

3. Delete all three class definitions and their associated methods.

4. Verify Python syntax: `python -m py_compile users/serializers.py`

**Tests:**
1. **Syntax check:** `python -m py_compile users/serializers.py` exits 0.
2. **Import check:** `python -c "from users.serializers import *"` does not raise ImportError for remaining serializers.
3. **Regression check:** Confirm no import errors in `users/api/viewsets.py` (which imports from `users/serializers.py`).

**Dependencies:** None.

---

## Phase 2: Remove Dead Function-Based Views

**What:** Delete 10 `@api_view` decorated functions and their dead helpers from `users/views.py`. These functions are not routed by any URL config and have been superseded by ViewSets in `users/api/viewsets.py`.

**Evidence of dead views:**
```
grep -rn "users.views" --include="urls.py"
# No output — zero URL routing references to users/views.py function-based views
```

**Dead functions (10 @api_view + 6 helpers):**

| Function | Superseded By | Lines |
|---|---|---|
| `kuroloaduser` (GET) | `UserViewSet.me` | ~186-196 |
| `rebloaduser` (GET) | `UserViewSet.me` | ~199-210 |
| `empprofile` (GET/POST) | `UserViewSet.profile` | ~215-237 |
| `accesslevel` (GET/POST) | `AccessLevelViewSet` (RBAC) | ~365-457 |
| `verifyUserid` (POST) | `AuthViewSet.verify` | ~462-552 |
| `employees_data` (GET) | `UserViewSet.employees` | ~557-570 |
| `emp_acc` (POST) | `UserViewSet.emp_acc` | ~588-622 |
| `bgSwitch` (GET/POST) | `TenantContextViewSet.bgswitch` | ~627+ |
| `handle_get_request` | Dead (only called by `empprofile`) | ~239-253 |
| `handle_post_request` | Dead (only called by `empprofile`) | ~255-273 |
| `validate_otp` | Dead (only called by dead views; `UserViewSet._validate_otp` is separate) | ~275-282 |
| `update_user` | Dead (only called by dead views) | ~284-288 |
| `update_kuro_user` | Dead (only called by dead views; `UserViewSet._update_kuro_user` is separate) | ~332-345 |
| `fetch_user_profile` | Dead (only called by dead views) | ~347-360 |

**Dead utility (1):**

| Function | Evidence | Lines |
|---|---|---|
| `getCounters` | Zero external callers; all code uses `teams.kurostaff.views.getCounters` | ~30-53 |

**Shared utility (1):**

| Function | Status | Lines |
|---|---|---|
| `_build_user_response` | Dead — only called by `kuroloaduser`/`rebloaduser` | ~84-183 |

**Functions to KEEP (actively imported):**

| Function | Importers | Lines |
|---|---|---|
| `numcode` | `users/api/viewsets.py`, `teams/kurostaff/views.py` | ~56-60 |
| `generateKey` | Internal (called by `generateOTP`) | ~62-63 |
| `generateOTP` | `users/api/viewsets.py` | ~65-68 |
| `sendSMS` | 14 files in `teams/` + `domains/shared/viewsets.py` | ~70-82 |
| `business_accesslevel` | `users/api/viewsets.py` | ~290-330 |
| `division_accesslevel` | `users/api/viewsets.py` | ~572-585 |

**Files:**
- Modify `users/views.py`

**Steps:**

1. Read full `users/views.py` to confirm line numbers for each dead function.
2. Verify `_build_user_response` callers: `grep -n "_build_user_response" users/views.py` — should only appear in `kuroloaduser` and `rebloaduser`.
3. Verify `getCounters` callers: `grep -rn "from users.views import.*getCounters\|users.views.getCounters" --include="*.py"` — should return zero.
4. Delete dead functions in this order (bottom-up to preserve line numbers):
   a. `bgSwitch` (last @api_view, ~627+)
   b. `emp_acc` (~588-622)
   c. `employees_data` (~557-570)
   d. `verifyUserid` (~462-552)
   e. `accesslevel` (~365-457)
   f. `fetch_user_profile` (~347-360)
   g. `update_kuro_user` (~332-345)
   h. `empprofile` + `handle_get_request` + `handle_post_request` (~215-273)
   i. `validate_otp` (~275-282)
   j. `update_user` (~284-288)
   k. `rebloaduser` (~199-210)
   l. `kuroloaduser` (~186-196)
   m. `_build_user_response` (~84-183)
   n. `getCounters` (~30-53)
5. After deletion, verify remaining imports are still needed. Remove unused imports:
   - `from users.models import ... Accesslevel, Switchgroupmodel` — check if still needed by `business_accesslevel`/`division_accesslevel`
   - `from tenant.models import BusinessGroup` — check if still needed
   - `from users.serializers import ...` — check if still needed
   - `from bson import ObjectId` — check if still needed
   - `from django.db.models import Q` — check if still needed
   - `from datetime import datetime, timedelta` — check if still needed
   - `from pytz import timezone` — check if still needed
   - `from django.utils.timezone import now` — check if still needed
   - `from rest_framework import status` — check if still needed
   - `import pyotp` — needed by `generateOTP`
   - `import base64` — needed by `generateKey`
   - `import urllib.request, urllib.parse` — needed by `sendSMS`
   - `import environ` — needed by `sendSMS`
   - `from collections import defaultdict` — check if still needed
   - `from backend.exceptions import InputException` — check if still needed
6. Verify Python syntax: `python -m py_compile users/views.py`
7. Verify imports still work: `python -c "from users.views import numcode, generateOTP, sendSMS, business_accesslevel, division_accesslevel"`

**Tests:**
1. **Syntax check:** `python -m py_compile users/views.py` exits 0.
2. **Import check:** All kept functions importable: `python -c "from users.views import numcode, generateOTP, sendSMS, business_accesslevel, division_accesslevel"` exits 0.
3. **Regression check:** `users/api/viewsets.py` still imports correctly: `python -c "from users.api.viewsets import *"` exits 0.
4. **Regression check:** `teams/financial.py` still imports correctly: `python -c "from users.views import sendSMS"` exits 0.

**Dependencies:** None (independent of Phase 1).

---

## Phase 3: Error Envelope Compliance in AuthViewSet

**What:** Replace flat error dicts in `AuthViewSet` methods with `**api_error()` envelopes to comply with spec §3.1.

**Current (non-compliant) patterns in `users/api/viewsets.py`:**

| Method | Current Pattern | Line (approx) |
|---|---|---|
| `login` | `{'status': 'FAILURE', 'msg': '...'}` | ~500-600 |
| `logout` | `{'status': 'FAILURE', 'msg': '...'}` | ~600+ |
| `verify` | `{'status': 'FAILURE', 'msg': '...'}` | ~650+ |
| `pwdreset` | `{'status': 'FAILURE', 'msg': '...'}` | ~700+ |

**Target pattern (spec §3.1):**
```python
from backend.utils import api_error

# Instead of:
return Response({'status': 'FAILURE', 'msg': 'Invalid credentials'}, status=401)

# Use:
body, status_code = api_error("Invalid credentials", code="AUTH_FAILED", status=401)
return Response(body, status=status_code)
```

**Files:**
- Modify `users/api/viewsets.py`

**Steps:**

1. Read `AuthViewSet` in `users/api/viewsets.py` and locate all `Response({'status': 'FAILURE'` patterns.
2. For each flat error response:
   a. Determine appropriate error code (`AUTH_FAILED`, `VALIDATION_ERROR`, `NOT_FOUND`, `SESSION_EXPIRED`).
   b. Determine appropriate HTTP status (400, 401, 403, 404).
   c. Replace with `body, status_code = api_error(...)` pattern.
3. Verify `api_error` is imported at top of file (should already be from Phase 1 of spec alignment).
4. Verify Python syntax: `python -m py_compile users/api/viewsets.py`

**Error code mapping:**

| Scenario | Code | Status |
|---|---|---|
| Invalid credentials | `AUTH_FAILED` | 401 |
| User not found | `USER_NOT_FOUND` | 404 |
| Invalid OTP | `OTP_INVALID` | 400 |
| OTP expired | `OTP_EXPIRED` | 400 |
| Missing phone/password | `VALIDATION_ERROR` | 400 |
| Session expired/invalid | `SESSION_EXPIRED` | 401 |
| Account suspended | `ACCOUNT_SUSPENDED` | 403 |

**Tests:**
1. **Syntax check:** `python -m py_compile users/api/viewsets.py` exits 0.
2. **Pattern check:** `grep -n "'status': 'FAILURE'" users/api/viewsets.py` returns zero matches in `AuthViewSet`.
3. **Envelope shape check:** Login with invalid credentials returns `{status: "error", error: {code, message}, meta: {request_id, timestamp}}`.

**Dependencies:** Phase 1 of spec alignment (api_error already created).

---

## Phase 4: Remove Legacy Response Fields

**What:** Remove `accesslevel[]` and legacy field names from `_build_user_data` and login response builders to comply with spec §4.3.

**Current (non-compliant) fields:**

| Field | Location | Issue |
|---|---|---|
| `accesslevel[]` | `_build_user_data` | Legacy permission format (raw permission strings, not RBAC perm_codes) |
| `roles[]` (from AccesslevelSerializer) | `_build_user_data` | Derived from `users_accesslevel` table (DEPRECATED) |
| `userid` | login response | Should be `identity_id` per spec §4.3 |

**Target fields (spec §4.3):**

| Legacy | Target | Source |
|---|---|---|
| `userid` | `identity_id` | M1 Identity model |
| `accesslevel[]` | `permissions[]` | RBAC perm_codes |
| `roles[]` (Accesslevel) | `roles[]` | Derived from Identity extensions |
| `division[]` | `active_div_code` | UserTenantContext |
| `branches[]` | `active_branch_code` | UserTenantContext |

**Files:**
- Modify `users/api/viewsets.py`

**Steps:**

1. Read `_build_user_data` method and identify legacy field assignments.
2. Replace `accesslevel[]` serialization with RBAC-based permission resolution:
   - Remove `AccesslevelSerializer` instantiation from `_build_user_data`.
   - Add `permissions` field from `resolve_permission()` or RBAC tables.
3. Replace `roles[]` derivation from `Accesslevel` with role derivation from Identity extensions.
4. Update login response to use `identity_id` instead of `userid` (if M1 migration is complete; otherwise keep `userid` with `identity_id` alongside during transition).
5. **Transition safety:** If frontend still expects `accesslevel[]` in login response, add field alongside `permissions[]` with a `ponytail:` comment marking it as transitional:
   ```python
   # ponytail: accesslevel[] kept for frontend compat until migration complete. Remove when kteam-fe-chief stops referencing it.
   "accesslevel": accesslevel_data,  # transitional
   "permissions": permissions,       # spec-compliant
   ```
6. Verify Python syntax: `python -m py_compile users/api/viewsets.py`

**Tests:**
1. **Syntax check:** `python -m py_compile users/api/viewsets.py` exits 0.
2. **Login response shape:** Login returns both `permissions[]` (spec-compliant) and `accesslevel[]` (transitional) during migration period.
3. **`/me` response shape:** Returns `identity_id`, `active_div_code`, `active_branch_code` per spec.

**Dependencies:** Phase 3 (error envelope compliance). M1 migration (`26-06-2026_m1-identity-migration_1a1902.md`) for `identity_id` field.

---

## Phase 5: Clean Up Dead Imports

**What:** Remove unused imports from files modified in Phases 1-4.

**Files:**
- Modify `users/serializers.py`
- Modify `users/views.py`
- Modify `users/api/viewsets.py`

**Steps:**

1. After Phases 1-4 are complete, run:
   ```bash
   python -c "
   import ast, sys
   with open('users/serializers.py') as f:
       tree = ast.parse(f.read())
   # Check for unused imports
   "
   ```
2. Manually review each file for imports that are no longer referenced after deletions.
3. Remove dead imports.
4. Verify Python syntax for all three files.

**Tests:**
1. **Syntax check:** All three files pass `python -m py_compile`.
2. **Import chain check:** `python -c "from users.api.viewsets import *"` exits 0.

**Dependencies:** Phases 1-4.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/serializers.py` | Delete 3 dead login serializers |
| Modify | `users/views.py` | Delete 10 dead @api_view functions, 6 dead helpers, 1 dead utility |
| Modify | `users/api/viewsets.py` | Replace flat error dicts with api_error(), remove legacy response fields |
| Modify | `users/serializers.py` | Clean up dead imports (Phase 5) |
| Modify | `users/views.py` | Clean up dead imports (Phase 5) |

## Constraints

- **No data loss:** `Accesslevel` model/table must NOT be dropped. It is DEPRECATED per spec but still referenced by frontend (120+ call sites via `resolve_access()`).
- **No routing changes:** Do not modify `users/urls.py` or `backend/urls.py` in this handoff. The dead views are already un-routed.
- **Backward compat on login/me:** During transition, keep `accesslevel[]` alongside `permissions[]` in login response. Mark with `ponytail:` comment.
- **Frontend coordination:** Before removing `accesslevel[]` entirely, verify `kteam-fe-chief` no longer references it.
- **Django 6.0.4 compatibility:** All changes must work with Django 6.0.4.
- **`sendSMS` must survive:** 14 importers across `teams/` depend on `users.views.sendSMS`. Do not delete.

## Success Criteria

- [ ] `AdminLoginSerializer`, `StaffLoginSerializer`, `RebLoginSerializer` deleted from `users/serializers.py`
- [ ] 10 dead `@api_view` functions deleted from `users/views.py`
- [ ] 6 dead helper functions deleted from `users/views.py`
- [ ] `getCounters` deleted from `users/views.py` (zero callers)
- [ ] `_build_user_response` deleted from `users/views.py` (only called by dead views)
- [ ] `users/views.py` still exports `numcode`, `generateOTP`, `sendSMS`, `business_accesslevel`, `division_accesslevel`
- [ ] All `AuthViewSet` error responses use `**api_error()` envelope (spec §3.1)
- [ ] Login response includes `permissions[]` (spec-compliant) alongside `accesslevel[]` (transitional)
- [ ] Dead imports removed from all modified files
- [ ] Python syntax verification passes for all modified files
- [ ] All existing tests still pass (no regression)
- [ ] `users/api/viewsets.py` imports successfully with no errors

## Execution Order

```
Phase 1 (dead serializers) ──┐
Phase 2 (dead views) ────────┤ (parallel, independent)
                              ├──→ Phase 3 (error envelope) ──→ Phase 4 (legacy fields) ──→ Phase 5 (dead imports)
```

- **Phase 1 & 2:** Parallel (independent files, no shared dependencies).
- **Phase 3:** Depends on `api_error()` existing (already created in spec alignment Phase 1).
- **Phase 4:** Depends on Phase 3 (error envelope compliance first, then response shape).
- **Phase 5:** Depends on Phases 1-4 (clean up after all deletions).

## Caveats & Uncertainty

1. **`AccesslevelSerializer` usage** — Actively imported by `users/views.py`, `users/api/viewsets.py`, `careers/views.py`, `teams/` (10+ files). Cannot be deleted. Only legacy field usage within `_build_user_data` is scoped for removal.
2. **`business_accesslevel` / `division_accesslevel`** — Still imported by `users/api/viewsets.py` and actively used. These functions reference `Accesslevel` model. Must survive.
3. **`sendSMS`** — 14 importers across `teams/` + `domains/shared/viewsets.py`. Critical shared utility. Must survive.
4. **Frontend transition period** — The `accesslevel[]` field in login responses cannot be removed until `kteam-fe-chief` is verified to use `permissions[]` instead. Estimated timeline: unknown, requires frontend audit.
5. **`resolve_access()` in `backend/auth_utils.py`** — Still imports `Accesslevel` and `BusinessGroup`. 120+ call sites per docstring. Not in scope for this handoff; deferred to frontend migration.
6. **Line numbers are approximate** — The line numbers cited in this handoff are estimates from the code analysis. The executing agent must verify exact line numbers before deletion.

---

## Serialized Phase Handoffs

This handoff has 5 phases. Phases 1-2 are parallel. Phases 3-5 are sequential. No separate phase docs needed (each phase is a single-file modification completable in one agent session).

## Anti-Patterns to Avoid

- ❌ Deleting `AccesslevelSerializer` (10+ active importers) → ✅ Only remove legacy field usage in `_build_user_data`
- ❌ Deleting `sendSMS` (14 active importers) → ✅ Keep unconditionally
- ❌ Deleting `business_accesslevel`/`division_accesslevel` (active in viewsets) → ✅ Keep unconditionally
- ❌ Removing `accesslevel[]` from login response without frontend verification → ✅ Keep alongside `permissions[]` with `ponytail:` comment
- ❌ Modifying URL routing → ✅ Dead views are already un-routed; only delete function definitions
- ❌ Changing `resolve_access()` → ✅ Deferred to frontend migration handoff
