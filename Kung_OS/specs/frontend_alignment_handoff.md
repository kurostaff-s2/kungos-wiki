# Frontend-Backend Alignment Handoff

**Date:** 2026-06-29
**Project:** `kteam-fe-chief` (Frontend) → `kteam-dj-chief` (Backend)
**Branch:** `develop`
**Status:** Active — Review findings require attention (see §Review Findings)
**Last Reviewed:** 2026-06-29

---

## Executive Summary

The frontend (`kteam-fe-chief`) has been migrated to align with the KungOS target state backend (`kteam-dj-chief`). Core alignment work is verified complete, but a review against the spec and live codebases uncovered **3 P0 issues, 2 P1 issues, and several open questions** that need resolution before the migration can be considered fully aligned.

**Verified Complete:**

- ✅ **RBAC Migration:** 33 files migrated from legacy `accesslevels` to `_permissions`
- ✅ **Response Envelope:** Standardized to `{status, data, meta}` format
- ✅ **Error Handling:** 45/129 mutations have onError handlers (35%) — counts verified
- ✅ **Data Loading:** 21/41 components check division in `enabled` flags — counts verified
- ✅ **Error Format:** Updated to match spec §8.2 format
- ✅ **Legacy `accesslevels` references:** 0 in frontend code
- ✅ **Legacy `accessUtils` references:** 0 in frontend code

**Active Issues Requiring Resolution:**

- 🔴 **P0:** `bg.entities` field does not exist in backend response — TenantSelector BG→division mapping is broken
- 🔴 **P0:** All permissions assigned level 2 (Edit) in frontend — security gap, over-privileged UI (FQ-4)
- 🔴 **P0:** Legacy `POST /api/v1/cafe/sessions/start` still registered in backend URLs
- 🔴 **P0:** Cafe Arcade domain reads `div_code` (singular) from user model — field doesn't exist, tenant isolation broken
- 🔴 **P0:** No React Query cache invalidation after tenant switch — stale data persists across BG/Division changes
- 🔴 **P0:** Three navigation configs (`navigation.jsx`, `sidebar-nav.js`, `nav-data.js`) with inconsistent keys and dead code (FQ-1)
- 🟠 **P1:** Refresh token cookie named `jwt_refresh` (spec says `refresh_token`), and refresh token exposed in JSON body (spec says cookie-only)
- 🟠 **P1:** Auth interceptor in `api.jsx` is a no-op — `getToken()` reads HttpOnly cookies (impossible)
- 🟠 **P1:** MongoDB queries without `bg_code` filter leak data across business groups
- ⚪ **Open:** Migration phase numbering ambiguous between handoff (P0–P4) and migration_spec.md (Phase 1–4)
- ⚪ **Open:** Accounts domain spec missing (backend has ~47/55 endpoints implemented)

**Remaining routine work:** ~84 mutations need onError, ~20 components need division checks, pagination/filter params alignment.

---

## Review Findings (2026-06-29)

A thorough review against `endpoint_contract_spec_revised.md`, `CANONICAL_NAMING.md`, the RBAC architecture, and the live codebases revealed the following issues. Each finding includes: what the handoff claims, what the code actually does, and the required action.

---

### RF-1: `bg.entities` Legacy Field — TenantSelector Broken 🔴 P0

**Handoff claim:** §3.1 lists `entity` as FORBIDDEN; canonical name is `div_codes`.

**Reality:** The frontend accesses a non-existent field:

```jsx
// src/components/layout/TenantSelector.jsx:318
const bgDivs = bg.entities || []
```

The backend `BusinessGroupSerializer` returns **only** `divisions_count` (integer), not an `entities` array. The field simply does not exist in the API response. Similarly, `AppLayout.jsx:230` accesses `d.branches` on division objects, but `DivisionSerializer` returns only `branches_count`.

**Impact:** `bgDivs` is always `[]`. The TenantSelector's BG-level expansion shows 0 divisions under each BG. The tenant selector UI is effectively non-functional for showing division/branch hierarchies.

**Root cause:** The frontend expects a nested hierarchy (BG → divisions[] → branches[]) in the BG detail response, but the backend returns flat count fields. The `useDivisions()` hook already fetches a flat list of all divisions — the frontend should derive the hierarchy from that.

**Action:** Fix `TenantSelector.jsx` and `AppLayout.jsx` to derive BG→division→branch hierarchy from the `useDivisions()` flat list (already fetched), not from `bg.entities`.

---

### RF-2: Permission Levels All Set to 2 (Edit) — Security Gap 🔴 P0

**Handoff claim:** §2.6 shows `buildPermissionsObject()` converting flat array → object with levels.

**Reality:** The function assigns **level 2 (Edit) to ALL permissions**:

```js
// src/actions/user.jsx:14
result[perm] = { level: 2, bg_code: bgCode || null }
```

The backend login response (`_build_login_response`, `users/api/viewsets.py:185`) sends `permissions` as a **flat list of strings** — level information is stripped:

```python
permissions = list(rbac_data.get('_permissions', {}).keys())  # keys only, levels dropped
```

The backend's `build_permissions_object()` correctly computes levels, and the `/tenant/current/` endpoint DOES return `_permissions` with levels. But the login response drops them.

**Impact:** Every user gets Edit (level 2) on everything they have permission for. A View-only user sees edit buttons and can attempt edits. This is a security issue — over-privileged UI.

**Action (choose one):**
- **Option A (Backend fix):** Change login response to include levels: `permissions: [{"code": "accounts.inward-invoices", "level": 1}, ...]`
- **Option B (Frontend fix):** After login, fetch `/tenant/current/` to get `_permissions` with levels, and use that instead of `buildPermissionsObject()`
- **Option C (Hybrid):** Backend includes levels in login; frontend `buildPermissionsObject()` reads them

---

### RF-3: Legacy `POST /api/v1/cafe/sessions/start` Still Active 🔴 P0

**Handoff claim:** §4.3 says this endpoint should be removed, replaced by `POST /api/v1/cafe/sessions`.

**Reality:** The legacy endpoint is **still registered**:

```
# domains/cafe_arcade/urls.py:45
path('sessions/start', views.session_start, name='session_start'),
```

The `session_start` view function exists at `domains/cafe_arcade/views.py:361`. The spec says the target is `POST /api/v1/cafe/sessions` (collection POST per REST convention), but the backend only has the legacy `sessions/start` action pattern.

**Risk:** If the frontend calls `POST /api/v1/cafe/sessions` (new spec), it will get a 404. If it calls `POST /api/v1/cafe/sessions/start` (legacy), it works but against a deprecated endpoint. **The frontend's actual call target needs to be verified.**

**Action:** Verify which endpoint the frontend uses for session creation. If it uses the legacy endpoint, document the gap. If it uses the new endpoint, it's broken (404). Then remove the legacy endpoint from URLs.

---

### RF-4: Refresh Token Cookie Name Mismatch + JSON Body Exposure 🟠 P1

**Spec §4.1.1:** Refresh token cookie name = `refresh_token`
**Spec §4.2:** Refresh token should be **only** in HttpOnly cookie, NOT in JSON response body.

**Backend reality:**
- Cookie named `jwt_refresh` (not `refresh_token`)
- `refresh_token` included in JSON body:
  ```python
  'data': {
      'access_token': str(jwt_token),
      'refresh_token': str(refresh),  # ← in JSON body (XSS risk)
      ...
  }
  ```

**Action:** Align backend with spec: rename cookie to `refresh_token`, remove from JSON body. Update frontend cookie reads if any exist.

---

### RF-5: Auth Interceptor is Dead Code 🟠 P1

**Handoff claim:** §4.4 says frontend should read JWT from cookies.

**Reality:** The `authInterceptor` in `api.jsx` is a no-op:

```js
const authInterceptor = (config) => {
    // We can't read the HttpOnly cookie, so Authorization header
    // will be empty — but that's fine since cookie auth handles it.
    return config  // ← does nothing
}
```

The `getToken()` function reads `jwt_token` from `document.cookie`, but **HttpOnly cookies are not readable by JavaScript**. This function always returns `null`. `setToken()` is also a no-op.

**Impact:** Not currently broken (cookie auth works via `withCredentials: true`), but `getToken()`/`setToken()` are misleading dead code. If someone later tries the Bearer header fallback, it won't work.

**Action:** Remove `getToken()` and `setToken()` (or mark as deprecated with clear documentation). The Bearer header fallback is impossible with HttpOnly cookies — document this limitation.

---

### RF-6: Migration Phase Numbering Ambiguous ⚪ Open

**Handoff claim:** P0=Middleware, P1=Identity, P2=RBAC, P3=MongoDB, P4=Data backfill.

**Backend docs confirm completion of:** P0 (identity-auth linkage ✅), P1 (RBAC population ✅), P3 (legacy code cleanup ✅).

**However:** The handoff says P3 (MongoDB field names) is "in progress" and P4 (data backfill) is "pending." The backend's `P3_LEGACY_CODE_CLEANUP_COMPLETE.md` refers to a different P3 (view function cleanup), not MongoDB field migration. The `migration_spec.md` uses different phase numbering (Phase 1–4 for MongoDB migration specifically).

**Action:** Clarify which phase numbering scheme is authoritative. The handoff should reference the specific completion docs (`P0_MIGRATION_COMPLETE.md`, `P1_RBAC_POPULATION_COMPLETE.md`, `P3_LEGACY_CODE_CLEANUP_COMPLETE.md`) rather than ambiguous phase names.

---

### RF-7: Accounts Domain Spec Missing ⚪ Open

**Handoff claim:** §4.1 correctly identifies `accounts_spec.md` as missing.

**Backend reality:** The Accounts domain is **substantially implemented** — `domains/accounts/urls.py` registers ~40 endpoints across invoices, payments, credit/debit notes, financials, tax, exports, and settlements. The URL docstring says "47/55 functions migrated to ViewSets." But no domain spec exists to document the API contract.

**Action:** Create `specs/domain_specs/accounts_spec.md` documenting the actual implemented endpoints, request/response shapes, and permission requirements. The backend is ahead of the spec — spec should be written to match implementation.

---

### RF-8: Backend Supports Dual Filter Params (Legacy + Canonical) ✅ No Action Needed

**Handoff claim:** §1.3 defers filter param migration to Phase 2.

**Verification:** Backend Accounts viewsets support **both** `?division=` (legacy) and `?div_code=` (canonical). No frontend code uses `filter[]` format. The deferral is correct — nothing is broken.

---

## Second Pass: Alignment Tightening (2026-06-29)

A second pass reviewed the document for additional spec alignment gaps, open questions, and implementation details that need clarification.

---

### SP-1: `bg.entities` — Detailed Fix Guidance

**Current broken code in `TenantSelector.jsx`:**
```js
// Line 318: accesses non-existent field
const bgDivs = bg.entities || []

// Line 36: mapping drops bg_code
const divs = useMemo(() => {
    return divisionsData.map(d => ({
      code: d.div_code,
      label: d.div_label || d.brand_name || d.div_code,
      branches: [],
    }))
}, [divisionsData])
```

**Required fix:**
```js
// Include bg_code in mapping
const divs = useMemo(() => {
    return divisionsData.map(d => ({
      code: d.div_code,
      label: d.div_label || d.brand_name || d.div_code,
      bg_code: d.bg_code,  // ← ADD THIS
      branches: [],
    }))
}, [divisionsData])

// Replace bg.entities with filter
const bgDivs = divs.filter(d => d.bg_code === bg.bg_code)
```

**Also fix:** `div.name` → `div.label` (line 352), and `div.branches` references (line 364) — branches aren't available in DivisionSerializer response.

**AppLayout.jsx** already uses the correct approach:
```js
const bgDivs = divisions.filter(d => String(d.bg?.bg_code || d.bg) === String(bg.bg_code))
```
But it also accesses `d.branches?.length` (line 114) which doesn't exist.

---

### SP-2: Session Creation Endpoint — Replacement Doesn't Exist Yet

**Current state:** Frontend calls `POST /api/v1/cafe/sessions/start` (legacy action pattern).

**Spec target:** `POST /api/v1/cafe/sessions` (REST collection POST).

**Backend reality:** The collection POST endpoint does NOT exist. Only action-pattern endpoints exist (`sessions/start`, `sessions/end`, `sessions/pause`, `sessions/resume`, `sessions/extend`).

**Action:** Either:
- **A:** Backend implements `POST /api/v1/cafe/sessions` (ViewSet `create` method) — recommended
- **B:** Frontend keeps using `sessions/start` until backend is ready — document as temporary
- **C:** Update spec to accept action-pattern for cafe sessions — less ideal

---

### SP-3: DivisionSerializer Fields — Branches Not Available

**Backend `DivisionSerializer` returns:** `div_code`, `div_label`, `brand_code`, `brand_name`, `div_type`, `bg_code`, `bg_label`, `branches_count` (integer).

**Frontend expects:** `div.branches` (array of branch objects) and `div.name` (string).

**Reality:** Branches are NOT returned in the DivisionSerializer. `div.name` doesn't exist — should be `div.div_label` or `div.div_code`.

**Impact:** The TenantSelector and AppLayout show 0 branches under every division. The branch hierarchy is effectively broken.

**Action:** Either:
- **A:** Backend adds a `branches` nested serializer to DivisionSerializer
- **B:** Frontend fetches branches separately (separate API call)
- **C:** Frontend removes branch display until backend supports it

---

### SP-4: `useAccessible` Hook Does Not Exist

**Handoff claim:** §4.1 references `GET /api/v1/tenant/accessible`.

**Frontend reality:** No `useAccessible` hook exists. The frontend uses `useBusinessGroups()` (calls `/tenant/business-groups/`) for BG list and `useDivisions()` (calls `/tenant/divisions`) for divisions. Accessible divisions are derived from `user.div_codes` in login response.

**This is fine** — the frontend doesn't need `tenant/accessible`. The spec endpoint exists for future use.

---

### SP-5: Open Questions Needing Resolution

| # | Question | Impact | Owner |
|---|----------|--------|-------|
| Q1 | Should `POST /api/v1/cafe/sessions` be implemented (REST) or keep `sessions/start` (action pattern)? | Cafe Arcade functionality | Backend |
| Q2 | Should branches be nested in DivisionSerializer or fetched separately? | TenantSelector hierarchy display | Backend |
| Q3 | Should login response include permission levels, or should frontend fetch `/tenant/current/`? | RBAC security | Backend+Frontend |
| Q4 | Is the `bg.entities` bug intentional (placeholder) or accidental? | TenantSelector functionality | Frontend |
| Q5 | Which migration phase numbering is authoritative — handoff P0-P4 or backend completion docs? | Documentation clarity | All |
| Q6 | Should refresh token cookie be `refresh_token` (spec) or `jwt_refresh` (current)? | Auth security | Backend |

---

## Multi-Tenancy Gap Analysis (2026-06-29)

A deep-dive into the multi-tenancy architecture revealed **3 critical gaps** that block full tenant isolation and **5 high-priority gaps** that need resolution before production. This section covers issues not captured in the Review Findings above.

---

### MG-1: Cafe Arcade Domain — Broken Tenant Context Extraction 🔴 P0

**Location:** `domains/cafe_arcade/views.py:46-55`

**Problem:** The cafe_arcade domain has its OWN `get_tenant_context` function that reads from `request.user` (Django User model), NOT from the JWT claims or middleware ContextVar:

```python
def get_tenant_context(user):
    return {
        "bg_code": getattr(user, "bg_code", DEFAULT_BG_CODE),  # ✓ exists
        "div_code": getattr(user, "div_code", ""),             # ✗ DOESN'T EXIST
        "branch_code": getattr(user, "branch_code", ""),       # ✗ DOESN'T EXIST
    }
```

**CustomUser model has:** `bg_code` (CharField), `div_codes` (JSONField list), `branch_codes` (JSONField list).

**Cafe Arcade reads:** `user.div_code` (singular — doesn't exist), `user.branch_code` (singular — doesn't exist).

**Impact:** Every cafe_arcade query filters by `div_code=""` (empty string). This either:
- Returns NO results (if MongoDB requires exact match)
- Returns ALL results across all BGs (if empty string matches everything)

**Evidence:** 10+ usages of `ctx['div_code']` in `domains/cafe_arcade/views.py` and `domains/cafe_arcade/views_tracker.py`:
```python
domains/cafe_arcade/views.py:318:  div_code=ctx['div_code'],
domains/cafe_arcade/views.py:710:  cafe__div_code=ctx['div_code'],
domains/cafe_arcade/views.py:728:  cafe__div_code=ctx['div_code'],
# ... and 7 more
```

**Root cause:** Two parallel tenant context systems exist:
1. `plat.observability.middleware.TenantContextMiddleware` — extracts from JWT, sets ContextVar (used by most domains)
2. `domains.cafe_arcade.views.get_tenant_context` — reads from `request.user` directly (used ONLY by cafe_arcade)

**Action:**
- **Option A:** Replace cafe_arcade's `get_tenant_context` with `from plat.observability.middleware import get_tenant_context`
- **Option B:** Fix cafe_arcade to read `div_codes[0]` instead of `div_code` from `request.user`
- **Option C:** Unify on one tenant context source across all domains (recommended)

---

### MG-2: Tenant Switch — No Query Cache Invalidation 🔴 P0

**Location:** `src/components/layout/TenantSelector.jsx` (BG/Division/Branch switch handlers)

**Problem:** After calling `/tenant/switch/` and updating local state, the frontend does NOT invalidate React Query caches. The `queryClient.invalidateQueries()` is never called.

**Evidence:**
```js
// src/components/layout/TenantSelector.jsx — handleBgSelect handler
const handleBgSelect = useCallback(async (code) => {
    const response = await api.post('/tenant/switch/', { bg_code: code, ... })
    const data = response.data?.data || response.data
    setBgCode(data.bg_code)
    setDivCodes(data.div_codes || [])
    // ... updates local state
    // ❌ NO queryClient.invalidateQueries() call
    if (onSwitchTenant) onSwitchTenant(data)
}, [...])
```

**Impact:** After switching BG/Division/Branch, the UI continues to show stale data from the previous tenant context until:
- User manually refreshes the page
- User navigates to a page that triggers a new fetch (old data persists in other tabs)

**Fix:** Add `queryClient.invalidateQueries()` after successful tenant switch in all three handlers:
```js
// After successful switch:
queryClient.invalidateQueries({ predicate: (query) => !query.state.dataUpdatedAt })
// Or more specifically:
queryClient.invalidateQueries({ queryKey: ['accounts'] })
queryClient.invalidateQueries({ queryKey: ['products'] })
// etc.
```

---

### MG-3: MongoDB Queries Without Tenant Filtering 🟠 P1

**Location:** Multiple domains call `get_collection()` without `bg_code`

**Problem:** The `get_collection()` function only filters by `bg_code` if provided. Calls without `bg_code` return ALL documents across all BGs.

**Evidence:**
```python
# domains/tournaments/views.py:187
reg_collection, _ = get_collection('tourneyregister')  # ← No bg_code

# domains/shared/services.py:35
misc_col, _ = get_collection("misc", db_name="KungOS_Mongo_One")  # ← No bg_code

# domains/shared/viewsets.py:375
est_col, est_tf = self.get_collection('estimates')  # ← No bg_code
```

**Impact:** Data leakage — users can see data from other BGs for tournaments, shared services, and other endpoints that don't enforce tenant filtering.

**Fix:**
1. Audit all `get_collection()` calls and ensure `bg_code` is always passed
2. Add a lint rule or test to catch missing tenant filters
3. Consider making `bg_code` a required parameter in `get_collection()` with a warning if omitted

---

### MG-4: Permission Levels Not in Login Response 🟠 P1

**Problem:** Login response sends `permissions` as a flat string array (levels dropped). All frontend permissions default to level 2 (Edit).

**Backend code:**
```python
# users/api/viewsets.py:197
rbac_data = build_permissions_object(user.userid, bg_code=tenant_context.get('bg_code'))
# ...
permissions = list(rbac_data.get('_permissions', {}).keys())  # ← keys only, levels dropped
```

**Impact:** Security gap — View-only users (level 1) see edit buttons and can attempt edits.

**Fix:** Either:
- Backend includes levels in login: `permissions: [{"code": "...", "level": 1}, ...]`
- Frontend fetches `/tenant/current/` after login to get `_permissions` with levels

---

### MG-5: Refresh Token in JSON Body (XSS Risk) 🟠 P1

**Problem:** Backend includes `refresh_token` in JSON response body AND sets it as HttpOnly cookie.

**Spec violation:** `endpoint_contract_spec_revised.md` §4.2 says refresh token must be cookie-only.

**Backend code:**
```python
# users/api/viewsets.py:239-241
'data': {
    'access_token': str(jwt_token),
    'refresh_token': str(refresh),  # ← IN JSON BODY (XSS risk)
    ...
}
```

**Impact:** XSS risk — if JS can read the response body, it can steal the refresh token.

**Fix:** Remove `refresh_token` from JSON body. Keep only in HttpOnly cookie.

---

### MG-6: Refresh Token Cookie Name Mismatch 🟠 P1

**Problem:** Backend sets cookie as `jwt_refresh`, spec says `refresh_token`.

**Backend code:**
```python
# users/api/viewsets.py:253
response.set_cookie(
    key='jwt_refresh',  # ← Should be 'refresh_token' per spec
    value=str(refresh),
    ...
)
```

**Impact:** If frontend or gateway reads `refresh_token` cookie, auth will fail.

**Fix:** Rename cookie to `refresh_token` in backend.

---

### MG-7: Dead Auth Code in Frontend 🟠 P1

**Problem:** `getToken()` and `setToken()` in `src/lib/api.jsx` are no-ops (cannot read HttpOnly cookies). The `authInterceptor` is also a no-op.

**Code:**
```js
// src/lib/api.jsx
const getToken = () => {
    const match = document.cookie.match(/jwt_token=([^;]+)/)
    return match ? match[1] : null  // ← Always null (HttpOnly)
}

const setToken = (token) => {
    document.cookie = `jwt_token=${token}; ...`  // ← No-op (HttpOnly)
}

const authInterceptor = (config) => {
    return config  // ← Does nothing
}
```

**Impact:** Misleading code — if someone tries to use Bearer header fallback, it won't work.

**Fix:** Remove `getToken()` and `setToken()`. Document that Bearer header is impossible with HttpOnly cookies.

---

### MG-8: Legacy `sessions/start` Endpoint Still Active 🟠 P1

**Problem:** `POST /api/v1/cafe/sessions/start` is still registered in `domains/cafe_arcade/urls.py:45`. The spec target `POST /api/v1/cafe/sessions` does NOT exist.

**Evidence:**
```
# domains/cafe_arcade/urls.py:45
path('sessions/start', views.session_start, name='session_start'),
```

**Impact:** Frontend works with legacy endpoint, but migration is blocked. If someone removes the legacy endpoint, cafe session creation breaks.

**Fix:** Implement `POST /api/v1/cafe/sessions` (ViewSet `create`), then remove legacy endpoint.

---

### Verified Working Multi-Tenancy Components ✅

The following components are **correctly implemented** and working:

| Component | Status | Evidence |
|-----------|--------|----------|
| JWT token embedding of tenant context | ✅ | `TenantAwareRefreshToken.for_user()` includes bg_code, div_codes, branch_codes, active_div_code, etc. |
| `CookieJWTAuthentication` | ✅ | Reads JWT from `jwt_token` HttpOnly cookie |
| `TenantContextMiddleware` | ✅ | Extracts claims, sets ContextVar, sets PostgreSQL RLS session variables |
| CORS credential configuration | ✅ | `CORS_ALLOW_CREDENTIALS = True` |
| Frontend `withCredentials: true` | ✅ | All axios instances set `withCredentials: true` |
| `/tenant/switch/` endpoint | ✅ | Issues new JWT with updated context |
| Frontend tenant switching flow | ✅ | Calls `/tenant/switch/`, updates local state |
| Accounts domain tenant filtering | ✅ | 124 usages of `get_collection()` with `bg_code` |
| Division checks on components | ✅ | 21/41 components (51%) |
| Error handling on mutations | ✅ | 45/129 mutations (35%) |
| Zero legacy `accesslevels` references | ✅ | Confirmed via grep |

---

## Frontend Code Quality Review (2026-06-29)

A thorough review of the frontend codebase (`kteam-fe-chief`) for duplicate implementations, faulty logic, and naming inconsistencies.

---

### FQ-1: THREE Navigation Configs with Inconsistent Keys 🔴 P0

**Locations:**
- `src/data/navigation.jsx` → exports `navSections` (used by `CommandPalette.jsx`)
- `src/data/sidebar-nav.js` → exports `sidebarSections`, `settingsItems`, `sidebarConfig` (used by `AppSidebar.jsx`, `useNavAccess.jsx`)
- `src/data/nav-data.js` → exports `navSections` (DEAD CODE — not imported anywhere)

**Problem:** Three different nav configs with different structures and keys:

| File | Root Export | Item Structure | Item Count |
|------|-------------|----------------|------------|
| `navigation.jsx` | `navSections` | `{ section, items: [{ label, path, key, id }] }` | 7 sections, ~80 items |
| `sidebar-nav.js` | `sidebarSections` | `{ label, items: [{ label, icon, to, key, id }] }` | 7 sections, ~90 items |
| `nav-data.js` | `navSections` | `{ name, children: [{ name, path, key }] }` | 5 sections, ~40 items |

**Key Inconsistencies:**
- `navigation.jsx` uses `path` (relative), `sidebar-nav.js` uses `to` (absolute with `/`)
- Same feature has different keys: e.g., "Order Analytics" is `key: 'analytics'` in sidebar but `key: 'order-analytics'` in navigation
- `PERM_MAP` in `useNavAccess.jsx` maps sidebar keys to RBAC permissions, but the keys don't match the actual sidebar keys in many cases

**Impact:**
- Command Palette shows different routes than Sidebar
- Access control (`useNavAccess`) may grant/deny access incorrectly due to key mismatches
- `nav-data.js` is dead code that confuses developers

**Action:**
1. Delete `src/data/nav-data.js` (dead code)
2. Unify `navigation.jsx` and `sidebar-nav.js` into a single source of truth
3. Standardize on either `path` or `to` (recommend `to` for consistency with React Router)
4. Audit `PERM_MAP` in `useNavAccess.jsx` against actual sidebar keys

---

### FQ-2: TenantContext Setter Naming Collision 🟠 P1

**Location:** `src/contexts/TenantContext.jsx`

**Problem:** Two sets of `setBgCode`, `setDivCodes`, etc. with the same names:

1. **Context setters** (inside `TenantProvider`): Update React state AND localStorage
   ```js
   const setBgCode = useCallback((code) => {
       setBgCodeState(code)
       code ? localStorage.setItem(STORAGE_KEYS.bgCode, code) : localStorage.removeItem(STORAGE_KEYS.bgCode)
   }, [])
   ```

2. **Standalone exports** (outside `TenantProvider`): Update ONLY localStorage
   ```js
   export function setBgCode(code) {
       code ? LS.setItem(STORAGE_KEYS.bgCode, code) : LS.removeItem(STORAGE_KEYS.bgCode)
   }
   ```

**Impact:**
- Redux actions (`user.jsx`, `admin.jsx`) import the **localStorage-only** setters
- React components use `useTenant()` which gives the **React context** setters
- When Redux actions call `setBgCode(user.bg_code)`, only localStorage is updated
- React state is NOT updated until the next render cycle
- This creates a race condition where the UI may show stale data

**Action:**
- Rename the standalone exports to `setBgCodeStorage`, `setDivCodesStorage`, etc.
- Or better: Have Redux actions dispatch Redux actions that trigger the `TenantProvider` `useEffect` to sync from Redux

---

### FQ-3: Duplicate Tenant Context Setup Code 🟠 P1

**Location:** `src/actions/user.jsx`

**Problem:** The same 6-line tenant context setup pattern is repeated 3 times:

```js
// In loadUser (line 50-55)
// In pwdLogin (line 109-114)
// In otpLogin (line 171-176)
setBgCode(user.bg_code)
if (user.div_codes?.length) setDivCodes(user.div_codes)
if (user.branch_codes?.length) setBranchCodes(user.branch_codes)
if (user.active_div_code) setActiveDivCode(user.active_div_code)
if (user.active_branch_code) setActiveBranchCode(user.active_branch_code)
if (user.scope) setScope(user.scope)
```

**Action:** Extract to a helper function:
```js
function syncTenantContextFromUser(user) {
    setBgCode(user.bg_code)
    if (user.div_codes?.length) setDivCodes(user.div_codes)
    if (user.branch_codes?.length) setBranchCodes(user.branch_codes)
    if (user.active_div_code) setActiveDivCode(user.active_div_code)
    if (user.active_branch_code) setActiveBranchCode(user.active_branch_code)
    if (user.scope) setScope(user.scope)
}
```

---

### FQ-4: `buildPermissionsObject` Hardcodes Level 2 🔴 P0

**Location:** `src/actions/user.jsx:9-15`

**Problem:** All permissions are assigned level 2 (Edit) regardless of actual RBAC level:

```js
function buildPermissionsObject(permissions, bgCode) {
    if (!Array.isArray(permissions)) return {}
    const result = {}
    permissions.forEach(perm => {
        result[perm] = { level: 2, bg_code: bgCode || null }  // ← HARDCODED
    })
    return result
}
```

**Impact:** View-only users (level 1) get Edit capability. Security gap.

**Action:**
- Backend must include `level` in permission objects (currently sends flat string array)
- OR frontend must fetch permission levels from `/tenant/current/` after login

---

### FQ-5: `getToken` is Private and Non-Functional 🟡 P2

**Location:** `src/lib/api.jsx:51`

**Problem:** `getToken` is private (not exported) and tries to read HttpOnly cookie:

```js
const getToken = () => parseCookie('jwt_token')
```

**Impact:** Can't be used by external code. HttpOnly cookies can't be read by JS anyway.

**Action:** Remove or make it a no-op with documentation.

---

### FQ-6: `setToken` Imported but Unused in `user.jsx` 🟡 P2

**Location:** `src/actions/user.jsx:4`

**Problem:**
```js
import { setToken, clearToken } from '@/lib/api'
```

`setToken` is imported but never called in this file. `clearToken` is called in logout but is also a no-op.

**Action:** Remove `setToken` from import.

---

### FQ-7: `mappings.jsx` Has Typo in `extensions` 🟡 P2

**Location:** `src/data/mappings.jsx:237`

**Problem:**
```js
{
    "name": "extension",  // ← Should be "extensions"
    "title": "Extension Boxes"
}
```

**Action:** Fix to `"extensions"`.

---

### FQ-8: Mixed camelCase/snake_case in Local Variables 🟡 P2

**Problem:** Inconsistent casing in local variables:
- `divCode` (camelCase) for `div_code` (snake_case) backend field
- `bgCode` (camelCase) for `bg_code` (snake_case) backend field
- `activeDivCode` (camelCase) for `active_div_code` (snake_case) backend field

**Impact:** Cognitive load when switching between backend and frontend code.

**Action:** Consider using `getDivisionLabel(divisions, div_code)` instead of `getDivisionLabel(divisions, divCode)` for clarity.

---

### FQ-9: `errorHandler.js` vs `errorLogger.js` Naming 🟡 P2

**Locations:**
- `src/lib/errorHandler.js` — Extracts user-friendly error messages from API responses
- `src/lib/errorLogger.js` — Captures uncaught errors and logs them to a file

**Problem:** Similar names but different purposes. Developers may confuse them.

**Action:** Rename `errorLogger.js` to `errorCapture.js` or `errorSink.js` for clarity.

---

### FQ-10: No `onError` in `loadUser`, `pwdLogin`, `otpLogin` 🟠 P1

**Locations:**
- `src/actions/user.jsx:60-80` (loadUser)
- `src/actions/user.jsx:120-140` (pwdLogin)
- `src/actions/user.jsx:180-200` (otpLogin)

**Problem:** These critical auth actions don't have user-friendly error handling. They only dispatch `AUTH_FAIL` or `LOGIN_FAIL`.

**Impact:** Users see generic "An unexpected error occurred" messages.

**Action:** Add `getErrorMessage()` calls and toast notifications.

---

## 1. Remaining Work

### 1.1 Error Handling (P2-6)

**Current State:** 45/129 mutations have onError handlers (35%)
**Target State:** 100% coverage

**Components Needing onError (15 remaining):**

| Component | Mutations | Priority |
|-----------|-----------|----------|
| `cafe/CustomerTracker.jsx` | 1 | Medium |
| `cafe/FnbMenuManagement.jsx` | 1 | Medium |
| `cafe/MemberPlans.jsx` | 1 | Low |
| `cafe/SessionActive.jsx` | 2 | Medium |
| `cafe/SessionEnd.jsx` | 1 | Medium |
| `cafe/StationDetail.jsx` | 1 | Medium |
| `cafe/StationsList.jsx` | 1 | Low |
| `cafe/WalletBalance.jsx` | 1 | Medium |
| `Counters.jsx` | 1 | Low |
| `EmployeesSalary.jsx` | 1 | Low |
| `Hr/EditAttendance.jsx` | 1 | Low |
| `Hr/EmployeeAccessLevel.jsx` | 1 | Low |
| `Hr/JobApps.jsx` | 1 | Low |
| `IndentList.jsx` | 1 | Low |
| `Inventory/TPBuildsNew.jsx` | 1 | Low |
| `Orders/OrderDetail.jsx` | 1 | Medium |
| `Orders/OrdersList.jsx` | 1 | Low |
| `ServiceRequests/ServiceRequestsDetail.jsx` | 1 | Low |
| `ServiceRequests/ServiceRequestsList.jsx` | 1 | Low |
| `Tenant/Brands.jsx` | 1 | Low |

**Pattern to Apply:**
```js
onError: (err) => {
    console.error('[ComponentName] Operation failed:', err)
    alert(err?.response?.data?.error?.message || 
          err?.response?.data?.detail || 
          err?.response?.data?.msg || 
          'Operation failed. Please try again.')
}
```

**Note:** Many remaining mutations are GET requests for downloads/searches. These can use a simpler pattern:
```js
onError: () => {
    console.error('[ComponentName] Download/search failed')
    // No user-facing alert for GET mutations
}
```

### 1.2 Data Loading (P2-7)

**Current State:** 21/41 components check division in `enabled` flags
**Target State:** 100% coverage

**Components Needing Division Check (20 remaining):**

| Component | Current `enabled` | Fix |
|-----------|-------------------|-----|
| `cafe/CustomerTracker.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/FnbMenuManagement.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/MemberPlans.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/SessionActive.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/SessionEnd.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/StationDetail.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/StationsList.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `cafe/WalletBalance.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Counters.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `EmployeesSalary.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Hr/EditAttendance.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Hr/EmployeeAccessLevel.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Hr/JobApps.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `IndentList.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Inventory/TPBuildsNew.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Orders/OrderDetail.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Orders/OrdersList.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `ServiceRequests/ServiceRequestsDetail.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `ServiceRequests/ServiceRequestsList.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |
| `Tenant/Brands.jsx` | `!!isAuthenticated` | `!!isAuthenticated && !!activeDivision` |

**Pattern to Apply:**
```js
enabled: !!isAuthenticated && !!activeDivision
```

### 1.3 Pagination/Filter Params (Phase 2)

**Current State:** Frontend uses legacy query params (`?division=`, `?bg_code=`)
**Target State:** Spec §9.2 defines `?filter[field]=value` format

**Decision:** Defer to Phase 2 when backend updates are ready. Current implementation works with legacy backend endpoints.

**Components Using Legacy Filter Format:**
- `src/pages/Accounts/InvoicesList.jsx` — `?division=`
- `src/pages/Accounts/PaymentVouchers.jsx` — `?division=`
- `src/pages/Accounts/Ledgers.jsx` — `?type=`
- `src/pages/Products/ProductsList.jsx` — `?division=`
- `src/pages/Inventory/Stock.jsx` — `?division=`

**Spec §9.2 Format:**
```
GET /api/v1/cafe/sessions?filter[status]=active&filter[cafe_id]=5&sort=-start_time
```

---

## 2. Backend-Frontend API Alignment

### 2.1 Response Envelope (✅ Aligned)

**Backend Target Format:**
```json
{
    "status": "success",
    "data": { ... },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

**Frontend Handler:** `src/lib/api.jsx` → `unwrapEnvelope()`
```js
const unwrapEnvelope = (response) => {
    if (!response || typeof response !== 'object') return response
    // Target envelope: {data, meta}
    if ('data' in response && 'meta' in response) return response.data
    // Legacy envelope: {status, data}
    if ('status' in response && 'data' in response) return response.data
    return response
}
```

### 2.2 Error Format (✅ Aligned)

**Backend Target Format (spec §8.2):**
```json
{
    "status": "error",
    "error": {
        "code": "PERMISSION_DENIED",
        "message": "You do not have permission...",
        "details": {...}
    }
}
```

**Frontend Handler:** `src/lib/errorHandler.js` → `getErrorMessage()`
```js
// Priority order:
// 1. error.error.message (spec format)
// 2. data.detail (DRF format)
// 3. data.msg (custom format)
// 4. data.message (generic)
// 5. data.error (generic)
// 6. data.non_field_errors[0] (DRF serializer)
// 7. Field-specific errors (DRF)
// 8. HTTP status-based fallback
```

### 2.3 Login Response (⚠️ Partially Aligned — See RF-2, RF-4)

**Backend Target Format:**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",    ← ⚠️ SPEC VIOLATION: should NOT be in JSON body
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "identity_id": "ID000001",
            "phone": "+919876543210",
            "name": "John Doe",
            "email": "john@example.com",
            "bg_code": "KURO0001",
            "div_codes": ["KURO0001_001"],
            "branch_codes": ["KURO0001_001_001"],
            "active_div_code": "KURO0001_001",
            "active_branch_code": "KURO0001_001_001",
            "scope": "division",
            "roles": ["employee"],
            "permissions": ["accounts.inward-invoices", ...],  ← ⚠️ LEVELS DROPPED
            "is_admin": false
        }
    },
    "meta": {...}
}
```

**Two spec violations:**
1. **Refresh token in JSON body** — Spec §4.2 says refresh token must be cookie-only (XSS prevention). Backend includes it in `data.refresh_token` AND sets `jwt_refresh` cookie.
2. **Permission levels dropped** — Backend sends `permissions` as flat string array. Level info from `build_permissions_object()` is lost. See RF-2.

**Backend cookie names:** `jwt_token` (access, 8h), `jwt_refresh` (refresh, 14d). Spec says refresh cookie should be named `refresh_token`. See RF-4.

**Frontend Handler:** `src/actions/user.jsx` → `pwdLogin()`
```js
const user = res.data?.data?.user
// Sets: bg_code, div_codes, branch_codes, active_div_code, active_branch_code, scope
// Converts: permissions[] → _permissions object via buildPermissionsObject()
// ⚠️ buildPermissionsObject assigns level 2 to ALL permissions (see RF-2)
```

### 2.4 User Me Endpoint (✅ Aligned)

**Backend Target Format:** Same as login response user object
**Frontend Handler:** `src/actions/user.jsx` → `loadUser()`
```js
const userData = res.data?.data || res.data
// Sets: bg_code, div_codes, branch_codes, active_div_code, active_branch_code, scope
```

### 2.5 Tenant Switching (✅ Aligned)

**Backend Endpoint:** `POST /api/v1/tenant/switch/`
**Frontend Handler:** `src/components/layout/AppLayout.jsx` → `switchTenant()`
```js
// Calls backend, updates local state, refreshes JWT
```

### 2.6 RBAC Permissions (⚠️ Partially Aligned — See RF-2)

**Backend Login Response Format:** Flat array of perm_codes (levels dropped)
```json
"permissions": ["accounts.inward-invoices", "orders.estimates.view", ...]
```

**Backend `/tenant/current/` Response Format:** Full `_permissions` with levels
```json
"permissions": {
    "accounts.inward-invoices": { "level": 2, "source": "store_manager" },
    "orders.estimates": { "level": 1, "source": "role" }
}
```

**Frontend Conversion:** `src/actions/user.jsx` → `buildPermissionsObject()`
```js
function buildPermissionsObject(permissions, bgCode) {
    if (!Array.isArray(permissions)) return {}
    const result = {}
    permissions.forEach(perm => {
        result[perm] = { level: 2, bg_code: bgCode || null }  // ⚠️ HARDCODED level 2
    })
    return result
}
```

**Problem:** All permissions get level 2 (Edit) regardless of actual RBAC level. A View-only user (level 1) gets Edit capability in the UI.

**Fix options:**
- **A:** Backend includes levels in login response: `permissions: [{"code": "...", "level": 1}, ...]`
- **B:** Frontend fetches `/tenant/current/` after login to get `_permissions` with levels
- **C:** Backend includes levels in login; frontend reads them in `buildPermissionsObject()`

### 2.7 Permission Checking (✅ Aligned)

**Helper Functions:** `src/lib/permissions.js`
```js
hasPermission(permissions, permCode, minLevel=1)
canView(permissions, permCode)        // level >= 1
canEdit(permissions, permCode)        // level >= 2
canAdmin(permissions, permCode)       // level >= 3
```

**Usage Pattern:**
```js
const permissions = useSelector(state => state.admin?._permissions || {})
if (canView(permissions, 'accounts.inward-invoices')) {
    // Show view button
}
if (canEdit(permissions, 'accounts.inward-invoices')) {
    // Show edit button
}
```

---

## 3. Canonical Naming Scheme

### 3.1 Frozen Canonical Names (Source of Truth)

**Reference:** `/home/chief/llm-wiki/Kung_OS/CANONICAL_NAMING.md`

| Concept | Canonical Name | FORBIDDEN |
|---------|---------------|-----------|
| Identity PK | `identity_id` | `userid`, `identityId`, `user_id` |
| Business group | `bg_code` | `bgcode`, `bg`, `business_group` |
| Division (singular) | `div_code` | `division`, `div`, `div_code_legacy` |
| Division (array) | `div_codes` | `division[]`, `entity`, `divisions` |
| Branch (singular) | `branch_code` | `branch`, `branch_code_legacy` |
| Branch (array) | `branch_codes` | `branches[]`, `branchs` |
| Active division | `active_div_code` | `entity[0]`, `active_division` |
| Active branch | `active_branch_code` | `branches[0]`, `active_branch` |
| Request ID | `request_id` | `requestId`, `req_id`, `reqId` |
| Refresh token | `refresh_token` | `refreshToken`, `refresh` |
| Token type | `token_type` | `tokenType`, `type` |

### 3.2 Permission Code Format

**Format:** `{domain}.{module}.{resource}.{action}`

**Examples:**
- `accounts.inward-invoices` — View inward invoices
- `accounts.outward-invoices` — View outward invoices
- `orders.estimates` — View estimates
- `products.tp-builds` — View TP builds
- `inventory.stock` — View stock
- `vendors.manage` — Manage vendors
- `admin.counters` — Manage counters
- `hr.employees` — Manage employees

**Permission Levels:**
- `0` = None (revoked)
- `1` = View
- `2` = Edit
- `3` = Admin/Supervisor

### 3.3 Field Mapping: Legacy → Canonical

| Legacy Field | Canonical Field | Context |
|--------------|-----------------|---------|
| `user.userid` | `user.identity_id` | Login response |
| `user.businessgroups[]` | `user.bg_code` | Login response (singular) |
| `user.accesslevel[]` | `user.permissions[]` | Login response (flat array) |
| `user.division[]` | `user.div_codes[]` | Login response |
| `user.branches[]` | `user.branch_codes[]` | Login response |
| `user.entity[0]` | `user.active_div_code` | Login response |
| `user.branches[0]` | `user.active_branch_code` | Login response |
| N/A | `user.scope` | Login response (`'full'`/`'division'`/`'branch'`) |
| N/A | `user.roles[]` | Login response (derived from extensions) |

### 3.4 Permission Object Format

**Login Response:** Flat array of perm_codes
```json
"permissions": ["accounts.inward-invoices", "orders.estimates", ...]
```

**Frontend State (`_permissions`):** Object with levels
```json
{
    "accounts.inward-invoices": { "level": 2, "bg_code": "KURO0001" },
    "orders.estimates": { "level": 1, "bg_code": "KURO0001" }
}
```

**Conversion:** `src/actions/user.jsx` → `buildPermissionsObject()`

---

## 4. Open Works Requiring Review

### 4.1 Missing Domain Specs

The following domains are **not** covered by foundational docs and need review:

| Domain | Spec Status | Backend Implementation | Notes |
|--------|-------------|----------------------|-------|
| **Accounts/Finance** | ❌ Missing | 🔵 ~47/55 endpoints implemented | Backend has invoices, payments, credit/debit notes, financials, tax, exports, settlements. Spec should be written to match implementation. See RF-7. |
| **RBAC System** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/architecture/rbac_system.md` |
| **Inventory** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/inventory_spec.md` |
| **E-Commerce** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/ecommerce_spec.md` |
| **Cafe Arcade** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/cafe_spec.md` |
| **Cafe F&B** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/cafe_fnb_orders_spec.md` |
| **Tournaments** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/tournaments_spec.md` |
| **Identity** | ✅ Documented | N/A | `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/identity_spec.md` |

**Action:** Create `specs/domain_specs/accounts_spec.md` covering:
- Invoice lifecycle (create, approve, credit, debit) — inward + outward
- Payment processing (inward, outward, bulk)
- Credit/debit notes (outward issued, inward received)
- Financial reports (P&L, balance sheet, ITC/GST, revenue, expenditure)
- Analytics endpoints
- Export endpoints (CSV/PDF)
- Settlements

**Priority:** Medium — backend is implemented, frontend Accounts pages exist but use legacy filter params. Spec enables Phase 2 filter param migration.

### 4.2 Migration Spec (⚠️ Phase Numbering Ambiguous — See RF-6)

**Reference:** `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/migration_spec.md`

**Verified Completion Docs:**

| Phase | Description | Status | Evidence |
|-------|-------------|--------|----------|
| P0 | Identity-Auth linkage + Tenant Context coverage | ✅ Complete | `P0_MIGRATION_COMPLETE.md` — 100% tenant context coverage, 9 linked identities |
| P1 | RBAC population (all users assigned roles) | ✅ Complete | `P1_RBAC_POPULATION_COMPLETE.md` — 100% user role coverage, 15 user roles |
| P2 | Middleware field names (entity→div_codes, branches→branch_codes) | ✅ Complete | Per `endpoint_contract_spec_revised.md` §11.1 (Phase 0 MUST) |
| P3 | Legacy view function cleanup | ✅ Complete | `P3_LEGACY_CODE_CLEANUP_COMPLETE.md` — 5 dead functions removed, 186 lines cleaned |
| P3 (MongoDB) | MongoDB field rename (bgcode→bg_code, division→div_code) | ⏳ Pending | `migration_spec.md` M3 — not started |
| P4 | Data backfill (M1 identity consolidation) | ⏳ Pending | `migration_spec.md` M1 — not started |

**Ambiguity:** The handoff uses P0–P4 for the overall migration, while `migration_spec.md` uses Phase 1–4 for MongoDB-specific migration. The backend completion docs use P0, P1, P3 for different things than the handoff. **Clarify which numbering scheme is authoritative.**

**Action:** Update this section to reference the specific completion docs and clearly distinguish between the overall migration phases (P0–P4) and the MongoDB migration phases (Phase 1–4).

### 4.3 Legacy Endpoint Removal

**Reference:** `endpoint_contract_spec_revised.md` §Appendix B

**Status: INCOMPLETE — One legacy endpoint still active (see RF-3)**

| Legacy Endpoint | Status | Replacement | Notes |
|----------------|--------|-------------|-------|
| `GET /api/v1/kuro/user` | ✅ Removed | `GET /api/v1/users/me` | Not in URL config |
| `GET /api/v1/kuro/user/{userid}` | ✅ Removed | `GET /api/v1/users/{identity_id}` | Not in URL config |
| `POST /api/v1/cafe/sessions/start` | 🔴 **STILL ACTIVE** | `POST /api/v1/cafe/sessions` | Registered in `domains/cafe_arcade/urls.py:45`. See RF-3. |
| `POST /api/v1/cafe/sessions/{id}/food` | ✅ Removed | `POST /api/v1/cafe-fnb/orders` | Not in URL config |
| `GET /api/v1/tournaments/tourneyregister` | ✅ Removed | `POST /api/v1/tournaments/{id}/register` | Not in URL config |
| `GET /api/v1/kuro/accesslevel/{userid}` | ✅ Removed | `GET /api/v1/rbac/user/{identity_id}` | Not in URL config |
| `POST /api/v1/kuro/switchgroup` | ✅ Removed | `POST /api/v1/tenant/switch` | Not in URL config (see `P3_LEGACY_CODE_CLEANUP_COMPLETE.md`) |
| `GET /api/v1/kuro/businessgroups` | ✅ Removed | `GET /api/v1/tenant/accessible` | Not in URL config |

**Action:**
1. Verify which endpoint the frontend uses for session creation (`cafe/sessions` vs `cafe/sessions/start`)
2. If frontend uses legacy endpoint, document the gap and plan migration
3. If frontend uses new endpoint, it's broken (404) — fix immediately
4. Remove `sessions/start` from `domains/cafe_arcade/urls.py`

### 4.4 JWT Cookie Handling (⚠️ Spec Violations — See RF-4, RF-5)

**Reference:** `endpoint_contract_spec_revised.md` §4.1.1, §4.2

**Current State:**
- Backend sets `jwt_token` (access, 8h, HttpOnly) and `jwt_refresh` (refresh, 14d, HttpOnly) as cookies
- Backend **also** includes `refresh_token` in JSON response body (spec violation)
- Frontend uses `withCredentials: true` in axios config ✅
- `authInterceptor` in `api.jsx` is a no-op (cannot read HttpOnly cookies)
- `getToken()` in `api.jsx` reads `jwt_token` from `document.cookie` — always returns `null` (HttpOnly)

**Spec vs Reality:**

| Aspect | Spec | Backend | Frontend |
|--------|------|---------|----------|
| Access token cookie name | `jwt_token` | `jwt_token` ✅ | N/A (cookie-only auth) |
| Refresh token cookie name | `refresh_token` | `jwt_refresh` ❌ | N/A |
| Refresh token in JSON body | NOT allowed | Included ❌ | N/A |
| Auth header fallback | N/A | N/A | No-op (dead code) ❌ |

**Action:**
1. Rename backend refresh cookie from `jwt_refresh` → `refresh_token`
2. Remove `refresh_token` from JSON response body
3. Remove dead `getToken()` and `setToken()` from `api.jsx`
4. Document that Bearer header fallback is impossible with HttpOnly cookies

### 4.5 Pagination Format

**Reference:** `endpoint_contract_spec_revised.md` §9.1

**Current State:** Frontend uses legacy query params (`?page=`, `?page_size=`)
**Target State:** Spec defines offset-based and cursor-based pagination

**Action:** Update pagination params when backend is ready:
- Offset: `?page=1&page_size=20`
- Cursor: `?cursor=abc123&limit=20`

### 4.6 Filter Format

**Reference:** `endpoint_contract_spec_revised.md` §9.2

**Current State:** Frontend uses legacy query params (`?division=`, `?bg_code=`)
**Target State:** Spec defines `?filter[field]=value` format

**Action:** Update filter params when backend is ready:
- `?filter[status]=active&filter[cafe_id]=5&sort=-start_time`

---

## 5. Verification Checklist

### 5.1 Build Verification

```bash
cd /home/chief/Coding-Projects/kteam-fe-chief
npx vite build  # Should pass with no errors
```

### 5.2 Zero Legacy References

```bash
# Should return 0 results
grep -rn "accesslevels\|_accesslevels\|userDetails\.accesslevel" src/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v ".test."

# Should return 0 results
grep -rn "LEGACY_ACCESS_LEVEL_MAP\|legacyFieldToPermCode\|checkLegacyAccess\|accessUtils" src/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v ".test."
```

### 5.3 Canonical Naming Audit

```bash
# Should return 0 results (except in migration docs)
grep -rn "bgcode\|userid\|requestId\|refreshToken\|tokenType\|entity\|branches" src/pages/ src/components/ src/lib/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v ".test."
```

### 5.4 Error Handler Coverage

```bash
# Count mutations with onError
grep -rn "onError" src/pages/ src/components/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v ".test." | wc -l

# Total mutations
grep -rn "useMutation" src/pages/ src/components/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v ".test." | wc -l
```

### 5.5 Division Check Coverage

```bash
# Count components with division check
grep -rn "enabled:.*activeDivision\|enabled:.*division" src/pages/ --include="*.jsx" | grep -v node_modules | grep -v ".test." | wc -l

# Count components without division check
grep -rn "enabled: !!isAuthenticated" src/pages/ --include="*.jsx" | grep -v node_modules | grep -v ".test." | wc -l
```

### 5.6 Legacy Endpoint Audit (Backend)

```bash
# Should return 0 results — legacy kuro/ routes
grep -rn "kuro/" backend/urls.py users/urls.py --include="*.py" | grep -v "venv" | grep -v "__pycache__" | grep -v "#"

# Check if sessions/start is still registered (RF-3)
grep -n "sessions/start" domains/cafe_arcade/urls.py
# Expected: line 45 — MUST be removed
```

### 5.7 Frontend Legacy Field Audit

```bash
# Check for bg.entities usage (RF-1)
grep -rn "bg\.entities\|\.entities" src/components/layout/ --include="*.jsx" | grep -v node_modules
# Expected: TenantSelector.jsx:318 — MUST be fixed

# Check for d.branches on division objects (RF-1)
grep -rn "d\.branches\|div\.branches" src/components/layout/ --include="*.jsx" | grep -v node_modules
# Expected: AppLayout.jsx:230 — MUST be fixed

# Check for dead getToken/setToken usage (RF-5)
grep -rn "getToken\|setToken" src/ --include="*.jsx" --include="*.js" | grep -v node_modules | grep -v ".test."
# Expected: api.jsx definitions only — should be removed
```

### 5.8 Backend Cookie Name Audit

```bash
# Verify cookie names in backend (RF-4)
grep -rn "set_cookie.*jwt_refresh\|set_cookie.*refresh_token" users/api/viewsets.py tenant/context_views.py
# Expected: jwt_refresh — MUST change to refresh_token
```

### 5.9 Permission Level Audit

```bash
# Verify buildPermissionsObject assigns levels correctly (RF-2)
grep -A 5 "buildPermissionsObject" src/actions/user.jsx
# Expected: level: 2 hardcoded — MUST read from backend

# Verify login response includes levels
grep -A 3 "'permissions'" users/api/viewsets.py | head -10
# Expected: list of keys (no levels) — MUST include levels
```

---

## 6. Commit History

**Latest Commit:** `34f6ac6` on `develop`
**Message:** "chore: RBAC migration, error handling, data loading fixes"
**Files Changed:** 66 files (+569, -357)

**Key Changes:**
- P1-5: Full `accesslevels` → `_permissions` migration (33 files)
- P0-1: Standardized response envelope handling
- P0-2: Fixed API path mismatches
- P0-3: Handled field name mismatches in Home.jsx
- P2-6: Added onError handlers to 31 mutations (5 components)
- P2-7: Added division checks to 21 components
- Added `src/lib/permissions.js` with 4 helper functions
- Added `src/lib/errorHandler.js` with spec §8.2 error format support
- Deleted `src/lib/accessUtils.js` (unused legacy utility)
- Removed all legacy backward compatibility code

---

## 7. Next Steps (Priority Order)

### P0 — Multi-Tenancy Blockers (must fix before migration is complete)

1. **Fix cafe arcade tenant context extraction** — Replace local `get_tenant_context` with middleware's `get_tenant_context`; fix `div_code` → `div_codes[0]` (MG-1)
2. **Add query cache invalidation after tenant switch** — Call `queryClient.invalidateQueries()` in all three switch handlers (MG-2)
3. **Fix `bg.entities` broken hierarchy** — Derive BG→division→branch from `useDivisions()` flat list in `TenantSelector.jsx` and `AppLayout.jsx` (RF-1)
4. **Fix permission levels** — Backend must include levels in login response OR frontend must fetch from `/tenant/current/` (RF-2, FQ-4)
5. **Verify session creation endpoint** — Confirm frontend calls correct endpoint; remove legacy `sessions/start` from URLs (RF-3)
6. **Unify navigation configs** — 3 nav configs with inconsistent keys; delete dead `nav-data.js` (FQ-1)

### P1 — Security & Spec Alignment

7. **Audit MongoDB queries for missing `bg_code`** — Ensure all `get_collection()` calls filter by tenant (MG-3)
8. **Rename refresh cookie** — `jwt_refresh` → `refresh_token`, remove from JSON body (MG-5, MG-6)
9. **Remove dead auth code** — Clean up `getToken()`/`setToken()` no-ops in `api.jsx` (MG-7)
10. **Fix TenantContext setter naming** — Rename localStorage-only setters to avoid collision (FQ-2)
11. **Deduplicate tenant context setup** — Extract helper function from `user.jsx` (FQ-3)
12. **Add `onError` to auth actions** — `loadUser`, `pwdLogin`, `otpLogin` need user-friendly errors (FQ-10)

### P2 — Documentation & Cleanup

13. **Create accounts domain spec** — Document implemented endpoints (RF-7)
14. **Clarify migration phase numbering** — Reference specific completion docs, distinguish overall vs MongoDB phases (RF-6)
15. **Complete error handling** — Add onError to remaining ~84 mutations
16. **Complete division checks** — Add division checks to remaining ~20 components
17. **Update pagination/filter params** — When backend is ready (Phase 2)
18. **Fix `extensions` typo in `mappings.jsx`** — `extension` → `extensions` (FQ-7)
19. **Rename `errorLogger.js`** — To `errorCapture.js` for clarity (FQ-9)
20. **Standardize camelCase/snake_case** — Review local variable naming conventions (FQ-8)

---

## 8. References

### Foundational Docs
- `/home/chief/llm-wiki/Kung_OS/README.md` — Project overview
- `/home/chief/llm-wiki/Kung_OS/CANONICAL_NAMING.md` — Frozen canonical names
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md` — API contract (sole authority)
- `/home/chief/llm-wiki/Kung_OS/architecture/rbac_system.md` — RBAC system
- `/home/chief/llm-wiki/Kung_OS/architecture/identity_layer.md` — Identity architecture
- `/home/chief/llm-wiki/Kung_OS/architecture/multi_tenancy.md` — Multi-tenancy

### Domain Specs
- `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/identity_spec.md`
- `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/ecommerce_spec.md`
- `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/tournaments_spec.md`
- `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/cafe_spec.md`
- `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/cafe_fnb_orders_spec.md`
- `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/inventory_spec.md`

### Database Schemas
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/mongodb_schema.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/migration_spec.md`

### Codebase
- **Frontend:** `/home/chief/Coding-Projects/kteam-fe-chief` (branch: `develop`)
- **Backend:** `/home/chief/Coding-Projects/kteam-dj-chief`

---

**Document Status:** Active — 6 P0 blockers (5 multi-tenancy + 1 code quality) require immediate resolution
**Last Updated:** 2026-06-29
**Next Review:** After P0 blockers (MG-1, MG-2, RF-1, RF-2, RF-3, FQ-1, FQ-4) are resolved
