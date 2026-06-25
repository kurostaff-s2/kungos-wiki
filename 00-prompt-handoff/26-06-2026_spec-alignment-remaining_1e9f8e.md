# Spec Alignment — Remaining Gaps

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `1e9f8e` |
| Entity type | `handoff` |
| Short description | Close remaining LIVE-vs-TARGET gaps: error envelope, pagination, legacy endpoint deprecation |
| Status | `draft` |
| Source references | `Kung_OS/specs/endpoint_contract_spec.md`, `Kung_OS/specs/database_schemas/postgresql_schema.md` |
| Generated | 26-06-2026 |
| Next action / owner | Execute Phase 1 (error envelope), then Phase 2 (pagination), then Phase 3 (legacy endpoints) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` (§3.1 Response Envelope, §3.2 Pagination)
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` (§2.4 User Tables — `users_accesslevel` DEPRECATED)
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend may depend on legacy endpoints)
**Key files for this task:**
- `backend/utils.py` (error helper, access levels)
- `users/api/viewsets.py` (legacy endpoints)
- `users/urls.py` (routing)
- `users/api/rbac_views.py` (RBAC views)

## Background

Phases 0-5 completed column renames, M1 Identity models, migration 0013, and frontend adaptation. Three remaining gaps prevent full spec alignment:

1. **Error envelope** — `api_error()` returns `{"error": msg}` instead of spec format
2. **Pagination** — uses DRF default instead of spec format
3. **Legacy endpoints** — `bgswitch_get`, `bgswitch`, `AccessLevelViewSet` still reference `users_accesslevel` (DEPRECATED, 55-col table)

**Excluded from scope:**
- KuroUser→Identity data migration (separate handoff: `26-06-2026_m1-identity-migration_1a1902.md`)
- Cafe identity FK migration (excluded per user request)
- Orders schema (Phase 8, planned)
- MongoDB collections (Phase 8, planned)

---

## Phase 1: Error Envelope Helper

**What:** Replace `api_error()` in `backend/utils.py` to return the spec-compliant error envelope.

**Files:**
- Modify `backend/utils.py`

**Steps:**

1. Read current `api_error()` function in `backend/utils.py` (line 38).
2. Replace with spec-compliant format:

```python
import uuid
from datetime import datetime
import pytz

def api_error(message="Internal server error", code="INTERNAL_ERROR", details=None, status=400):
    """Return spec-compliant error envelope.

    Args:
        message: Human-readable error message.
        code: Machine-readable error code (e.g., "VALIDATION_ERROR", "NOT_FOUND").
        details: Optional list of {field, issue} dicts for validation errors.
        status: HTTP status code (default 400).

    Returns:
        dict matching spec §3.1 error envelope.
    """
    body = {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
        },
        "meta": {
            "request_id": str(uuid.uuid4())[:12],
            "timestamp": datetime.now(pytz.timezone('UTC')).isoformat(),
        },
    }
    if details:
        body["error"]["details"] = details
    return body, status
```

3. Update all callers of `api_error()` to unpack the tuple: `body, status = api_error(...)`. Search for `api_error(` across the codebase.
4. For callers that use `Response(api_error(...))`, update to `Response(body, status=status)`.
5. Verify Python syntax for `backend/utils.py` and all modified callers.

**Tests:**
1. **Test error envelope shape:** Call `api_error("Phone required", "VALIDATION_ERROR", [{"field": "phone", "issue": "required"}])` and assert keys: `status`, `error.code`, `error.message`, `error.details`, `meta.request_id`, `meta.timestamp`.
2. **Test default error:** Call `api_error()` and assert `code == "INTERNAL_ERROR"`, `status == 400`.
3. **Test no details:** Call `api_error("Not found", "NOT_FOUND")` and assert `details` key absent.

**Dependencies:** None.

---

## Phase 2: Pagination Helper

**What:** Create a custom DRF paginator returning the spec-compliant pagination object.

**Files:**
- Create `users/pagination.py`
- Modify `users/api/viewsets.py` (or `backend/settings.py` for global)

**Steps:**

1. Create `users/pagination.py`:

```python
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class SpecPagination(PageNumberPagination):
    """Pagination matching spec §3.2.

    Returns:
        {
            "status": "success",
            "data": [...],
            "pagination": {
                "page": 1,
                "page_size": 20,
                "total_items": 150,
                "total_pages": 8,
                "has_next": true,
                "has_prev": false
            },
            "meta": { ... }
        }
    """
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        import uuid
        from datetime import datetime
        import pytz

        return Response({
            "status": "success",
            "data": data,
            "pagination": {
                "page": self.page.number,
                "page_size": self.page.size,
                "total_items": self.paginator.count,
                "total_pages": self.paginator.num_pages,
                "has_next": self.page.has_next(),
                "has_prev": self.page.has_previous(),
            },
            "meta": {
                "request_id": str(uuid.uuid4())[:12],
                "timestamp": datetime.now(pytz.timezone('UTC')).isoformat(),
            },
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "data": {"type": "array", "items": schema},
                "pagination": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "page_size": {"type": "integer"},
                        "total_items": {"type": "integer"},
                        "total_pages": {"type": "integer"},
                        "has_next": {"type": "boolean"},
                        "has_prev": {"type": "boolean"},
                    },
                },
                "meta": {"type": "object"},
            },
        }
```

2. Apply globally in `backend/settings.py`:

```python
REST_FRAMEWORK = {
    ...
    "DEFAULT_PAGINATION_CLASS": "users.pagination.SpecPagination",
    "PAGE_SIZE": 20,
    ...
}
```

3. For ViewSets that should NOT paginate (e.g., `login`, `me`), add `pagination_class = None`.

**Tests:**
1. **Test pagination shape:** Hit any paginated endpoint (e.g., `GET /api/v1/users/`) and assert `pagination` keys match spec.
2. **Test page_size param:** Hit `GET /api/v1/users/?page_size=5` and assert `page_size == 5`.
3. **Test max_page_size:** Hit `GET /api/v1/users/?page_size=200` and assert capped at 100.

**Dependencies:** Phase 1 (error envelope may affect error responses from paginated views).

---

## Phase 3: Legacy Endpoint Deprecation

**What:** Deprecate three legacy endpoints that reference `users_accesslevel` (DEPRECATED per spec §2.4).

**Files:**
- Modify `users/api/viewsets.py` (lines 1121-1195: `bgswitch`, `bgswitch_get`; lines 1200+: `AccessLevelViewSet`)
- Modify `users/urls.py` (remove legacy routes)

**Steps:**

1. **Audit frontend dependency:** Search `kteam-fe-chief` for `bgswitch`, `access-levels`, `bgswitch_get` calls. If frontend still calls these, coordinate with frontend team before removal.

2. **Deprecate `bgswitch_get` (GET /users/bgswitch_get/):**
   - Replace `Accesslevel` query with RBAC-based resolution.
   - Return canonical shape: `{status, data: [{bg_code, div_codes, branch_codes, permissions}], meta}`.
   - Use `resolve_permission()` from `users/permissions.py` instead of `Accesslevel.objects`.

3. **Deprecate `bgswitch` (POST /users/bgswitch/):**
   - Replace `Switchgroupmodel` update with `UserTenantContext` update.
   - Use `div_codes`/`branch_codes` instead of `division`/`branches`.

4. **Deprecate `AccessLevelViewSet` (CRUD on `users_accesslevel`):**
   - Option A: Replace with RBAC views that proxy to `rbac_user_roles` / `rbac_user_permissions`.
   - Option B: Add deprecation warning header and keep as passthrough until frontend migrates.
   - **Recommendation:** Option A if RBAC views exist; Option B if frontend still depends on it.

5. **Update URL routing:** Remove `bgswitch_get` and `bgswitch` from `users/urls.py` if fully replaced. Keep `access-levels` route if Option B chosen.

6. **Verify no regressions:** Ensure `resolve_access()` in `backend/auth_utils.py` still works (it imports `Accesslevel` — if table is kept, this is fine; if dropped, rewrite).

**Tests:**
1. **Test bgswitch_get returns RBAC data:** Hit endpoint and assert response uses `div_codes`/`branch_codes` (not `division`/`branches`).
2. **Test bgswitch updates UserTenantContext:** POST new BG and verify `UserTenantContext` updated (not `Switchgroupmodel`).
3. **Test access-levels still works (if Option B):** Hit endpoint and assert deprecation warning header present.

**Dependencies:** Phase 1 (error envelope used in error responses). Frontend audit must complete before execution.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/utils.py` | Replace `api_error()` with spec-compliant envelope |
| Create | `users/pagination.py` | Custom DRF paginator matching spec §3.2 |
| Modify | `backend/settings.py` | Register `SpecPagination` globally |
| Modify | `users/api/viewsets.py` | Update legacy endpoints to use RBAC |
| Modify | `users/urls.py` | Remove or update legacy routes |
| Modify | `backend/auth_utils.py` | Rewrite `resolve_access()` if `Accesslevel` dropped |

## Constraints

- **No data loss:** `users_accesslevel` table must not be dropped until frontend is migrated. Use deprecation warnings first.
- **Backward compat on login/me:** Do not change `login` or `/users/me` response shapes in this handoff (already aligned in P1/P5).
- **Django 6.0.4 compatibility:** Use `condition=` for `CheckConstraint`, not `check=`.
- **Frontend coordination:** Before removing legacy endpoints, verify `kteam-fe-chief` no longer calls them.

## Success Criteria

- [ ] `api_error()` returns spec-compliant `{status, error, meta}` envelope
- [ ] All callers of `api_error()` updated to unpack tuple
- [ ] `SpecPagination` registered globally, returns spec-compliant `pagination` object
- [ ] `bgswitch_get` returns RBAC-based data with canonical field names
- [ ] `bgswitch` updates `UserTenantContext` (not `Switchgroupmodel`)
- [ ] `AccessLevelViewSet` either replaced with RBAC proxy or marked deprecated
- [ ] Python syntax verification passes for all modified files
- [ ] All existing tests still pass (no regression)
- [ ] Frontend still loads without hydration errors

## Caveats & Uncertainty

1. **`resolve_access()` in `backend/auth_utils.py`** — Still imports `Accesslevel` and `BusinessGroup`. If `Accesslevel` table is kept (Option B), this is fine. If dropped, the function must be rewritten to use RBAC. This affects 120+ call sites (per docstring).
2. **Frontend dependency on legacy endpoints** — Must audit `kteam-fe-chief` before removing `bgswitch_get`/`bgswitch`/`access-levels`. If frontend still calls them, use Option B (deprecation warning) and schedule frontend migration.
3. **`Switchgroupmodel`** — Still used by `bgswitch` and `resolve_access()`. If `UserTenantContext` replaces it, all callers must be updated. This is a wider change than the three endpoints alone.

---

## Execution Order

```
Phase 1 (error envelope) → Phase 2 (pagination) → Phase 3 (legacy endpoints)
     (independent)              (depends on P1)          (depends on P1, frontend audit)
```

All phases sequential. Phase 3 requires frontend audit before execution.
