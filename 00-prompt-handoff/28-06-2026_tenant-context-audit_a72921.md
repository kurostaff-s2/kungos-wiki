# Tenant Context Audit — Confirmed Bugs and Alignment Gaps (Investigation Complete)

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | tenant-context-audit-a72921 |
| Entity type | review |
| Short description | Comprehensive audit of tenant context (BG/Division/Branch) handling across frontend, backend, middleware, and MongoDB. Investigation complete with evidence. |
| Status | draft |
| Source references | multi_tenancy.md, endpoint_contract_spec.md §5, plat/observability/middleware.py, plat/observability/context.py, plat/tenant/collection.py, plat/tenant/rls.py, users/api/viewsets.py, users/models.py (UserTenantContext), users/tenant_tokens.py, users/views.py (bgSwitch), tenant/context_views.py, backend/auth_utils.py, backend/utils.py, src/lib/api.jsx, src/contexts/TenantContext.jsx, src/components/layout/TenantSelector.jsx, src/hooks/useDivisions.jsx, src/hooks/useTenantQuery.jsx |
| Generated | 28-06-2026 |
| Next action / owner | Execute P0 fixes (middleware + MongoDB wrapper field names), then P1 (JWT emission on switch, frontend backend sync) |

---

## Project Context

**Project root (backend):** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Project root (frontend):** `/home/chief/Coding-Projects/kteam-fe-chief/`
**Reference docs:** `/home/chief/llm-wiki/Kung_OS/architecture/multi_tenancy.md`, `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`
**Key files for this task:** Listed per finding below

---

## Executive Summary

The tenant context system has **significant misalignment** between the design spec, backend implementation, and frontend consumption. Investigation confirms **2 P0 bugs** that break all tenant isolation, **4 P1 issues** that violate spec compliance, and **5 P2/P3 issues** affecting correctness and maintainability.

The root cause is a **JWT field name mismatch**: the middleware and MongoDB wrapper read legacy field names (`entity`, `branches`, `userid`) from the JWT, but `generate_tenant_token()` emits canonical names (`bg_code`, `div_codes`, `branch_codes`, `identity_id`). This means tenant context resolution is broken on every request.

---

## 1. Confirmed Bugs

### P0-1: Middleware reads legacy JWT field names (blocking)

**File:** `plat/observability/middleware.py` (TenantContextMiddleware.process_request)
**Evidence:** Read lines showing `token.get("entity")`, `token.get("branches")`, `token.get("userid")`

The middleware extracts tenant context from the JWT on every request. It reads:
- `token.get("entity", [])` — does NOT exist in JWT (canonical: `div_codes`)
- `token.get("branches", [])` — does NOT exist in JWT (canonical: `branch_codes`)
- `token.get("userid", "")` — legacy name (canonical: `identity_id`)

**Downstream impact:**
1. `plat/observability/context.py` — `set_tenant_context()` receives empty/wrong values
2. `plat/tenant/rls.py` — RLS session variables (`app.current_division`, `app.current_branch`) set to empty strings → **no tenant isolation at DB level**
3. `backend/utils.py` → `plat/observability/context.py` — `get_tenant_context()` returns broken ContextVar
4. `plat/tenant/collection.py` — MongoDB TenantCollection receives broken context

**Impact:** All tenant-scoped queries return wrong data. Silent cross-tenant data leakage.

### P0-2: MongoDB wrapper reads legacy JWT field names (blocking)

**File:** `plat/tenant/collection.py` (TenantCollection)
**Evidence:** Read lines showing `ctx.get("entity")`, `ctx.get("branches")`

The `TenantCollection` wrapper reads the same legacy field names from the context dict. Even if the middleware were fixed, this would need the canonical keys.

**Impact:** MongoDB queries missing tenant filter → cross-tenant data leakage.

### P1-1: `switch` endpoint doesn't emit a new JWT (spec violation)

**File:** `tenant/context_views.py` (TenantContextViewSet.switch, lines 66–120)
**Evidence:** Full method read — updates `UserTenantContext` DB row, returns RBAC data, does NOT call `generate_tenant_token()`

The spec (§5.3 endpoint_contract_spec.md) requires tenant-switching endpoints to produce a new JWT with updated claims. The current implementation:
1. Updates `UserTenantContext` in the DB (correct)
2. Returns RBAC permissions (correct)
3. Does NOT generate a new JWT (missing)
4. Does NOT set a new cookie (missing)

**Impact:** After switching BG/division/branch, the JWT carries stale claims. The middleware (once fixed) would read old tenant data from the token on every subsequent request.

### P1-2: Frontend tenant switching is local-only (spec violation)

**File:** `src/components/layout/TenantSelector.jsx`
**Evidence:** `handleBgSelect`, `handleDivSelect`, `handleBranchSelect` all call `setBgCode`/`setDivision`/`setBranch` (React state + localStorage) and `onSwitchTenant` callback. None call the backend `/tenant/switch/` endpoint.

**Flow:**
```
User clicks TenantSelector → BG/Division/Branch
    ↓
Frontend updates local state (React + localStorage)
    ↓
Frontend passes onSwitchTenant callback to parent
    ↓
Parent updates local state only
    ↓
❌ Backend never notified
    ↓
❌ JWT not updated
    ↓
❌ UserTenantContext DB row not updated
    ↓
All subsequent API calls use OLD tenant context
```

**Impact:** Backend has no record of the user's active scope. Server-side filtering (RLS, MongoDB TenantCollection, `resolve_access`) uses stale DB state. Frontend and backend are out of sync.

### P1-3: Legacy `bgSwitch` view doesn't refresh JWT

**File:** `users/views.py` (bgSwitch, line 594)
**Evidence:** Full method read — updates `UserTenantContext` via `update_or_create`, returns permissions. Does NOT generate new JWT.

Still routed at `/api/v1/users/bgswitch/` alongside the new `/tenant/switch/` endpoint. Creates two code paths for the same operation with inconsistent behavior.

### P1-4: Login response missing `div_codes` / `branch_codes` / `scope`

**File:** `users/views.py` (login response builder)
**Evidence:** `_build_login_response` returns `bg_code`, `active_div_code`, `active_branch_code` but NOT `div_codes`, `branch_codes`, `scope`.

The frontend's `TenantContext.jsx` seeds from `userDetails.division` which doesn't exist in the login response. This means the frontend initializes with an empty division on first login.

### P2-1: `resolve_access` fallback masks the middleware bug

**File:** `backend/auth_utils.py` (`_get_switchgroup`, line ~42)
**Evidence:** Queries `UserTenantContext` DB directly. Falls back to `Identity.bg_code` when empty.

This is a **different resolution path** than the middleware (JWT → ContextVar). When the middleware is broken, `resolve_access` can still "work" via DB fallback — masking the middleware bug in testing and making it appear that tenant context is functional.

### P2-2: Branch validation regex is fragile

**File:** `src/contexts/TenantContext.jsx` (line ~68)
**Evidence:** `!/^[A-Z]+\d+_\d+_\d+$/.test(storedBranch)`

Hardcoded pattern assumes branch codes always match `KURO0001_001_001`. If the backend ever uses a different pattern (shorter codes, different separators, lowercase), valid branches are cleared from localStorage silently.

### P2-3: `useDivisions` not scoped to BG

**File:** `src/hooks/useDivisions.jsx`
**Evidence:** Query key is `['tenant-divisions']` — no `bgCode` included.

When the user switches BG, React Query returns stale division data from the previous BG until the 5-minute `staleTime` expires.

### P3-1: `bgswitch` viewset action mutates `request.data`

**File:** `users/api/viewsets.py` (line ~1107)
**Evidence:** `request.data._mutable = True; request.data['bg_code'] = bg_code`

Fragile pattern that depends on DRF internals. If DRF changes the QueryDict implementation, this breaks silently.

### P3-2: `token_key` on `UserTenantContext` may be dead code

**File:** `users/models.py` (UserTenantContext.token_key)
**Evidence:** Field stores `str(request.auth)` (JWT string). Not referenced by `resolve_access`, middleware, or `TenantCollection`. Only used in `switch` endpoint as a pass-through.

---

## 2. Data Flow Analysis

### 2.1 JWT Generation (Correct)

```
users/tenant_tokens.py : generate_tenant_token()
    ↓
Payload includes:
    bg_code ✅
    div_codes ✅
    branch_codes ✅
    active_div_code ✅
    active_branch_code ✅
    identity_id ✅
    scope ✅
    _businessgroups ✅
    ↓
JWT set as HttpOnly cookie
```

### 2.2 Middleware Extraction (Broken)

```
plat/observability/middleware.py : TenantContextMiddleware
    ↓
Reads JWT from request.auth
    ↓
Extracts:
    token.get("entity") → [] (always empty)  ❌ should be "div_codes"
    token.get("branches") → [] (always empty)  ❌ should be "branch_codes"
    token.get("userid") → "" (legacy)  ❌ should be "identity_id"
    ↓
Populates ContextVar with empty/wrong values
    ↓
Sets RLS session variables to empty strings
    ↓
All downstream consumers inherit broken context
```

### 2.3 Downstream Consumers

```
ContextVar (broken)
    ↓
├── plat/tenant/rls.py → RLS session vars = "" (no isolation)
├── backend/utils.py : get_tenant_context() → broken dict
│       ↓
│       plat/tenant/collection.py : TenantCollection → ctx.get("entity") = None
│               ↓
│               MongoDB queries missing tenant filter
├── resolve_access() → falls back to DB (masks the bug)
└── All views that read tenant context from request
```

---

## 3. Field Name Mapping (Confirmed)

### Backend JWT Claims → Middleware Extraction

| JWT Claim (actual) | Middleware Reads | Middleware Gets | Correct Field |
|---------------------|-----------------|-----------------|---------------|
| `bg_code` | `token.get("bg_code")` | ✅ Correct value | `bg_code` |
| `div_codes` | `token.get("entity")` | `[]` (empty) | `div_codes` |
| `branch_codes` | `token.get("branches")` | `[]` (empty) | `branch_codes` |
| `identity_id` | `token.get("userid")` | legacy or empty | `identity_id` |
| `active_div_code` | (not read) | N/A | `active_div_code` |
| `active_branch_code` | (not read) | N/A | `active_branch_code` |

### Backend JWT Claims → Frontend State

| Backend JWT Claim | Frontend State | Mismatch? |
|-------------------|---------------|-----------|
| `bg_code` | `bgCode` | ⚠️ Case (camelCase vs snake_case) — acceptable |
| `div_codes` | `division` (singular string) | ❌ Array vs singular |
| `branch_codes` | `branch` (singular string) | ❌ Array vs singular |
| `active_div_code` | — | ❌ Not in frontend state |
| `active_branch_code` | — | ❌ Not in frontend state |
| `scope` | — | ❌ Not in frontend state |
| `identity_id` | — | ❌ Not in frontend state |

### Frontend State → Backend API

| Frontend State | Backend API Param | Alignment? |
|---------------|------------------|------------|
| `division` | `division` (query param via `useTenantQuery`) | ✅ Matches backend convention |
| `branch` | `branch_code` (query param via `useTenantQuery`) | ✅ Matches backend convention |
| `bgCode` | (sent via cookie, not param) | ✅ |

---

## 4. Architectural Alignment Assessment

| Area | Status | Gap |
|------|--------|-----|
| JWT Generation (`tenant_tokens.py`) | ✅ Aligned | Canonical claims match spec §3.2 |
| `UserTenantContext` model | ✅ Aligned | Schema matches spec §4.1 (`div_codes`, `branch_codes` JSONField) |
| Tenant context endpoints (`context_views.py`) | ⚠️ Partial | Routes correct, but `switch` doesn't emit JWT |
| Middleware → ContextVar | ❌ Broken | Legacy field names |
| MongoDB tenant collection | ❌ Broken | Legacy field names |
| Frontend state management | ⚠️ Partial | Local-only, no backend sync |
| Frontend → backend query params | ✅ Aligned | `useTenantQuery` produces correct params |
| Legacy `bgSwitch` coexistence | ⚠️ Risk | Both old and new endpoints active |
| RLS (`plat/tenant/rls.py`) | ✅ Aligned | Reads from ContextVar (correct path, broken data) |
| `resolve_access` fallback | ⚠️ Risk | Masks middleware bug via DB path |

---

## 5. Recommended Fix Ordering

### Phase 1: P0 — Restore Tenant Isolation (1–2 hours)

**1A. Fix middleware field names**
- **File:** `plat/observability/middleware.py`
- **Change:** Replace `entity` → `div_codes`, `branches` → `branch_codes`, `userid` → `identity_id`
- **Test:** Verify ContextVar contains correct values after login

**1B. Fix MongoDB wrapper field names**
- **File:** `plat/tenant/collection.py`
- **Change:** Replace `ctx.get("entity")` → `ctx.get("div_codes")`, `ctx.get("branches")` → `ctx.get("branch_codes")`
- **Test:** Verify MongoDB queries include tenant filter

### Phase 2: P1 — Spec Compliance (2–3 hours)

**2A. Add JWT emission to `switch` endpoint**
- **File:** `tenant/context_views.py`
- **Change:** Import `generate_tenant_token()`, call after `update_or_create`, set new cookie
- **Test:** Verify new JWT contains updated claims after switch

**2B. Wire frontend to call `/tenant/switch/`**
- **File:** `src/components/layout/TenantSelector.jsx`
- **Change:** Add API call in `handleBgSelect`/`handleDivSelect`/`handleBranchSelect`
- **Test:** Verify DB row updated and new JWT received after UI switch

**2C. Include full context in login response**
- **File:** `users/views.py` (`_build_login_response`)
- **Change:** Add `div_codes`, `branch_codes`, `scope` to response
- **Test:** Verify frontend initializes with correct division on login

### Phase 3: P2 — Correctness (1 hour)

**3A. Scope `useDivisions` to BG**
- **File:** `src/hooks/useDivisions.jsx`
- **Change:** Include `bgCode` in query key
- **Test:** Verify divisions refetch on BG switch

**3B. Deprecate legacy `bgSwitch`**
- **File:** `users/views.py`, `users/urls.py`
- **Change:** Add deprecation warning, redirect to `/tenant/switch/`
- **Test:** Verify no frontend calls hit legacy endpoint

### Phase 4: P3 — Cleanup (30 min)

**4A. Remove `request.data._mutable` hack**
- **File:** `users/api/viewsets.py`
- **Change:** Use proper request data handling
- **Test:** Verify bgswitch still works

**4B. Audit `token_key` usage**
- **File:** `users/models.py`
- **Change:** Remove if unused, or document purpose
- **Test:** Verify no regressions

---

## 6. Caveats & Uncertainty

1. **The middleware bug may be masked in testing** because `resolve_access` has a DB fallback. Integration tests that don't exercise the middleware path directly would pass even with broken JWT claims. Any test suite must verify the ContextVar values explicitly.

2. **The `update_or_create` in `switch`** uses only `userid` as the lookup key (not `userid + bg_code`). This means it always updates the same row regardless of BG. If multi-BG support is added later, this will need a composite key or separate rows per BG.

3. **The frontend branch regex** will clear any branch code that doesn't match the exact pattern. If a branch code is stored as a display name (e.g., "Madhapur"), it's correctly cleared — but the regex is a maintenance burden if the code format changes.

4. **`token_key` on `UserTenantContext`** stores `str(request.auth)` which is the JWT token string. This is intended for token invalidation but isn't referenced anywhere else in the codebase. May be dead code or incomplete feature.

5. **The legacy `bgSwitch` view** is still routed and functional. If frontend code references it (via `onSwitchTenant` callback chain), removing it without the frontend fix would break tenant switching entirely.

6. **Assumption:** The JWT is stored as HttpOnly cookie and the middleware reads `request.auth` (DRF authentication result). If the auth class changes, the middleware extraction path changes.

---

## 7. Verification Checklist

Before marking any fix complete:

- [ ] Middleware extracts correct field names from JWT
- [ ] ContextVar contains non-empty `div_codes`, `branch_codes`, `identity_id`
- [ ] RLS session variables are set to correct values (not empty strings)
- [ ] MongoDB queries include `bg_code` filter
- [ ] `switch` endpoint emits new JWT with updated claims
- [ ] Frontend calls `/tenant/switch/` on tenant change
- [ ] `UserTenantContext` DB row updated after frontend switch
- [ ] Login response includes `div_codes`, `branch_codes`, `scope`
- [ ] Divisions refetch on BG switch (query key includes bgCode)
- [ ] All existing tests still pass (no regression)

---

*Audit generated: 28-06-2026*
*Priority: P0 — Middleware extraction bug breaks all tenant isolation*
*Estimated effort: 4–6 hours total (P0: 1–2h, P1: 2–3h, P2: 1h, P3: 30min)*
