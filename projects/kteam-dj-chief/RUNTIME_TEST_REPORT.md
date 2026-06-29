# KungOS Runtime Testing Report — Critical Bugs Found

**Date:** 2026-06-29  
**Tester:** pi coding agent  
**Status:** 🔴 **BLOCKER — Multiple critical bugs preventing frontend-backend integration**

---

## Executive Summary

Runtime testing of kteam-dj-chief (backend) against kteam-fe-chief (frontend) revealed **5 critical bugs** that prevent the frontend from receiving intended data from the backend.

| # | Severity | Endpoint | Error | Root Cause |
|---|----------|----------|-------|------------|
| 1 | 🔴 P0 | `/teams/users` | 500 Internal Error | `NameError: name 'userid' is not defined` |
| 2 | 🔴 P0 | `/accounts/inward-invoices` | 500 Internal Error | `BusinessGroup.DoesNotExist` — JWT bg_code mismatch |
| 3 | 🟡 P1 | `/cafe/games` | 403 Forbidden | Spec says **public**, implementation requires auth |
| 4 | 🟡 P1 | `/cafe/price-plans` | 404 Not Found | Spec path `/price-plans` ≠ impl `/pricing/rules` |
| 5 | 🟡 P1 | `/users/me` | 301 Redirect | Missing trailing slash handling |

**Additionally:** JWT token contains `bg_code: "KURO0001"` but login response returns `"bg_code": "BG0001"` — mismatch between JWT claims and response envelope.

---

## Test Environment

- **Backend:** `http://localhost:8000` (Django 6.0.6, running)
- **Frontend:** `http://localhost:3000` (Vite dev server)
- **Test User:** `E2EADM01` (admin, full scope, bg_code: KURO0001)
- **Auth:** JWT Bearer token from `/api/v1/auth/login`

---

## Bug #1: `NameError: name 'userid' is not defined`

**Severity:** 🔴 P0 — Complete endpoint failure  
**Endpoint:** `GET /api/v1/teams/users`  
**HTTP Status:** 500 Internal Server Error  
**File:** `domains/teams/viewsets.py:161`

### Evidence

```
{"timestamp": "2026-06-29 01:57:14,474", "level": "ERROR", 
 "logger": "backend.response_utils", 
 "message": "Unhandled exception: name 'userid' is not defined", 
 "exception": "Traceback (most recent call last):
   File \".../domains/teams/viewsets.py\", line 161, in list
     if userid:
        ^^^^^^
 NameError: name 'userid' is not defined"}
```

### Root Cause

Variable `userid` is used on line 161 but the query param was captured as `identity_id` on line 158:

```python
# Line 158: captures as identity_id
identity_id = request.query_params.get('identity_id')

# Line 161: uses undefined 'userid'
if userid:
    user_obj = CustomUser.objects.get(userid=userid)
```

### Impact

- **`/teams/users` endpoint completely broken** — returns 500 for all requests
- Frontend HR pages (Employees, UserAccess, UserDetails) cannot load
- Affects: `src/pages/Hr/Employees.jsx`, `src/pages/Hr/UserAccess.jsx`, `src/pages/UserDetails.jsx`, `src/pages/Users.jsx`

### Fix

```python
# Option A: Use identity_id (spec-aligned)
identity_id = request.query_params.get('identity_id')
if identity_id:
    user_obj = Identity.objects.get(identity_id=identity_id)

# Option B: Fix variable name
userid = request.query_params.get('userid')
if userid:
    user_obj = CustomUser.objects.get(userid=userid)
```

**Recommendation:** Option A — aligns with canonical naming (identity_id, not userid).

---

## Bug #2: `BusinessGroup.DoesNotExist` — Tenant Context Mismatch

**Severity:** 🔴 P0 — Complete endpoint failure  
**Endpoint:** `GET /api/v1/accounts/inward-invoices` (and all accounts endpoints)  
**HTTP Status:** 500 Internal Server Error  
**File:** `backend/auth_utils.py:145`

### Evidence

```
{"timestamp": "2026-06-29 01:56:53,489", "level": "ERROR", 
 "logger": "backend.response_utils", 
 "message": "Unhandled exception: BusinessGroup matching query does not exist.",
 "exception": "Traceback (most recent call last):
   File \".../domains/accounts/viewsets.py\", line 69, in get_tenant_context
     sw, bg = resolve_minimal(request)
   File \".../backend/auth_utils.py\", line 145, in resolve_minimal
     bg = BusinessGroup.objects.get(bg_code=ctx.bg_code)
   tenant.models.BusinessGroup.DoesNotExist: BusinessGroup matching query does not exist."}
```

### Root Cause

Two issues:

1. **JWT bg_code = "KURO0001"** (correct, matches DB)
2. **Login response bg_code = "BG0001"** (incorrect fallback)

Login response shows:
```json
"user": {
    "bg_code": "BG0001",  // ← WRONG: fallback value
    ...
}
```

But JWT contains:
```json
{
    "bg_code": "KURO0001",  // ← correct
    ...
}
```

The `resolve_minimal()` function reads `ctx.bg_code` from the JWT (which is correct), but the error suggests the tenant context extraction is failing somewhere. Need to investigate `_get_switchgroup()`.

### Impact

- **All accounts endpoints broken** — inward/outward invoices, payments, purchase orders, etc.
- Frontend Accounts pages cannot load any data
- Affects: `src/pages/Accounts/InvoicesList.jsx`, `src/pages/OutwardInvoices.jsx`, `src/pages/PurchaseOrders.jsx`, etc.

### Fix

Investigate `_get_switchgroup()` to ensure it correctly extracts `bg_code` from JWT claims. Also fix the login response fallback (`'bg_code': identity.bg_code or 'BG0001'` on line 135 of `users/api/viewsets.py`).

---

## Bug #3: `/cafe/games` Auth Mismatch

**Severity:** 🟡 P1 — Spec vs implementation  
**Endpoint:** `GET /api/v1/cafe/games`  
**HTTP Status:** 403 Forbidden (with auth), 401 (without)  
**Spec (§6.3):** Public  
**Implementation:** Requires JWT authentication

### Evidence

**Spec says:**
```
| GET | `/cafe/games` | Game catalog | Public |
```

**Implementation (`domains/cafe_arcade/views.py`):**
```python
def game_library(request):
    ctx = get_tenant_context(request.user)  # Requires auth!
```

**Test result:**
```bash
$ curl http://localhost:8000/api/v1/cafe/games
{"status":"error","error":{"code":"not_authenticated",...}}

$ curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/cafe/games
{"status":"error","error":{"code":"permission_denied",...}}
```

### Impact

- Frontend `GameLibrary.jsx` cannot load game catalog
- Even with auth, returns `permission_denied` (missing cafe permission)

### Fix Options

- **Option A:** Remove auth requirement (true public endpoint per spec)
- **Option B:** Update spec to mark as JWT-authenticated + add `cafe.games` permission

---

## Bug #4: `/cafe/price-plans` Path Mismatch

**Severity:** 🟡 P1 — Spec vs implementation  
**Endpoint:** `GET /api/v1/cafe/price-plans`  
**HTTP Status:** 404 Not Found  
**Spec (§6.3):** `/cafe/price-plans`  
**Implementation:** `/cafe/pricing/rules`

### Evidence

**Spec says:** `GET /cafe/price-plans` — Price plans — Public

**Backend URLs (`domains/cafe_arcade/urls.py`):**
```python
path('pricing/rules', views.pricing_rules, name='pricing_rules'),
```

**Frontend (`src/lib/cafeApi.js`):**
```javascript
pricingRules: () => fetcher(`${BASE}pricing/rules`)(),  // Uses /pricing/rules ✅
```

### Impact

- Spec is outdated — frontend already uses `/pricing/rules`
- No actual breakage since frontend is aligned with implementation

### Fix

Update spec document: `/cafe/price-plans` → `/cafe/pricing/rules`

---

## Bug #5: `/users/me` 301 Redirect

**Severity:** 🟡 P1 — Minor  
**Endpoint:** `GET /api/v1/users/me`  
**HTTP Status:** 301 (redirects to `/api/v1/users/me/`)

### Evidence

```
"GET /api/v1/users/me HTTP/1.1" 301 0
```

### Impact

- Axios may not follow redirect with credentials
- Frontend may fail to load user data

### Fix

Either:
- Add trailing slash to URL pattern: `path('users/me/', ...)`
- Or ensure frontend uses `/users/me/`

---

## Additional Observations

### JWT vs Login Response Mismatch

**Login response:**
```json
{
    "data": {
        "user": {
            "bg_code": "BG0001",  // Fallback value
            "div_codes": [],
            "branch_codes": [],
            "active_div_code": "",
            "scope": "full"
        }
    }
}
```

**JWT payload:**
```json
{
    "bg_code": "KURO0001",  // Correct value
    "div_codes": [],
    "branch_codes": [],
    "active_div_code": "",
    "tenant_scope": "full"
}
```

**Issue:** Login response `bg_code` is `"BG0001"` (hardcoded fallback in `users/api/viewsets.py:135`), but JWT contains `"KURO0001"`. This violates spec §3.1 — response envelope must match JWT claims.

**Location:** `users/api/viewsets.py` line 135:
```python
'bg_code': identity.bg_code or 'BG0001',  // Hardcoded fallback
```

---

## Endpoints That WORK ✅

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /health/` | ✅ 200 | PostgreSQL + MongoDB connected |
| `POST /api/v1/auth/login` | ✅ 200 | Returns JWT + refresh token |
| `GET /api/v1/teams/employees` | ✅ 200 | Returns empty list (no data) |
| `GET /api/v1/cafe/pricing/rules` | ✅ Works | Frontend aligned |

---

## Endpoints That FAIL ❌

| Endpoint | Status | Error |
|----------|--------|-------|
| `GET /api/v1/teams/users` | ❌ 500 | `NameError: name 'userid'` |
| `GET /api/v1/accounts/*` | ❌ 500 | `BusinessGroup.DoesNotExist` |
| `GET /api/v1/cafe/games` | ❌ 403 | Auth mismatch + missing permission |
| `GET /api/v1/cafe/stations` | ❌ 403 | Missing `cafe.stations` permission |
| `GET /api/v1/cafe/dashboard/overview` | ❌ 403 | Missing permission |
| `GET /api/v1/inventory/stock` | ❌ 500 | `Unauthorized` error |
| `GET /api/v1/users/me` | ⚠️ 301 | Trailing slash redirect |

---

## Recommendations

### Immediate (P0 — Fix Before Any Frontend Testing)

1. **Fix `domains/teams/viewsets.py:161`** — Change `userid` → `identity_id` (or fix variable name)
2. **Fix `backend/auth_utils.py:145`** — Debug `resolve_minimal()` BusinessGroup lookup
3. **Fix login response bg_code** — Remove hardcoded `'BG0001'` fallback

### Short-term (P1)

4. **Decide `/cafe/games` auth** — Public (per spec) or JWT (per impl)?
5. **Update spec** — `/cafe/price-plans` → `/cafe/pricing/rules`
6. **Fix trailing slash** — `/users/me` → `/users/me/`
7. **Verify cafe permissions** — Ensure test user has `cafe.stations`, `cafe.sessions` permissions

### Long-term (P2)

8. **Add integration tests** — pytest + DRF test client for all endpoints
9. **Add response shape validation** — Ensure all responses match spec envelope
10. **Add tenant context tests** — Verify JWT → ContextVar propagation

---

## Appendix: Test Commands Used

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"E2EADM01","password":"E2Eadmin123!"}'

# Test endpoints (replace $TOKEN with access_token from login)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/teams/users
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/accounts/inward-invoices
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/cafe/games
curl http://localhost:8000/api/v1/cafe/price-plans

# Backend logs
tail -f /tmp/django_server.log
```

---

**Report generated:** 2026-06-29  
**Next steps:** Fix P0 bugs, then re-run integration tests
