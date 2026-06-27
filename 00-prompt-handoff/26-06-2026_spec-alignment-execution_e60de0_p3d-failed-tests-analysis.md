# Phase 3D: Failed Tests Analysis Against Spec

**Date:** 2026-06-27  
**Status:** Analysis Complete  
**Test Results:** 236 passed, 14 failed

---

## Summary

| Category | Count | Spec Violation? |
|----------|-------|-----------------|
| Auth endpoint 404s | 8 | ✅ YES |
| Cafe permissions missing | 6 | ❌ NO (test setup issue) |

---

## Auth Endpoint Failures (8 tests)

### Root Cause
**Spec says:** `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/logout`  
**Implementation has:** `/api/v1/users/auth/login`, `/api/v1/users/auth/refresh`, `/api/v1/users/auth/logout`

### Evidence

**Spec (§4.3 Auth Module):**
```
| POST | /api/v1/auth/login | Login (phone + password) | None |
| POST | /api/v1/auth/refresh | Refresh JWT | Refresh token |
| POST | /api/v1/auth/logout | Invalidate session | JWT |
```

**Implementation (users/urls.py:64-66):**
```python
path('auth/login', AuthViewSet.as_view({'post': 'login'}), name='unified_login'),
path('auth/refresh', CookieTokenRefreshView.as_view(), name='jwt_refresh'),
path('auth/logout', AuthViewSet.as_view({'post': 'logout'}), name='jwt_logout'),
```

**URL Resolution:**
- `users/urls.py` is included at `path('users/', include('users.urls'))`
- Result: `/api/v1/users/auth/login` (not `/api/v1/auth/login`)

### Failing Tests
1. `test_login_success` — POST `/api/v1/auth/login` → 404
2. `test_login_invalid_password` — POST `/api/v1/auth/login` → 404
3. `test_login_missing_fields` — POST `/api/v1/auth/login` → 404
4. `test_login_nonexistent_user` — POST `/api/v1/auth/login` → 404
5. `test_logout_blacklists_token` — POST `/api/v1/auth/logout` → 404
6. `test_logout_without_refresh` — POST `/api/v1/auth/logout` → 404
7. `test_refresh_success` — POST `/api/v1/auth/refresh` → 404
8. `test_refresh_invalid_token` — POST `/api/v1/auth/refresh` → 404

### Fix Required
Move auth routes from `users/urls.py` to a top-level `auth/urls.py` and include at `path('auth/', include('auth.urls'))` in `backend/urls.py`.

---

## Cafe Permissions Failures (6 tests)

### Root Cause
**Test expects:** Cafe permissions seeded in `rbac_permissions` table  
**Reality:** Permissions not seeded (test setup issue, not spec violation)

### Evidence

**Failing Tests:**
1. `test_all_cafe_permissions_exist` — Missing 11 cafe permissions
2. `test_specific_cafe_session_permissions` — `cafe.sessions.view`, `cafe.sessions.manage`
3. `test_specific_cafe_station_permissions` — `cafe.stations.view`, `cafe.stations.manage`
4. `test_specific_cafe_wallet_permissions` — `cafe.wallet.view`, `cafe.wallet.manage`
5. `test_specific_cafe_fnb_permissions` — `cafe.menu.view`, `cafe.orders.view`, `cafe.orders.manage`
6. `test_specific_cafe_pricing_membership_permissions` — `cafe.pricing.view`, `cafe.membership.view`

**Spec (cafe_spec.md):**
- Defines endpoints but does NOT specify permission codes
- Permission model is in `architecture/rbac_system.md` (generic, no cafe-specific perms)

### Verdict
**NOT a spec violation.** Tests expect permissions that aren't defined in any spec. This is a test setup issue — either:
1. Permissions should be seeded (add to test fixtures)
2. Tests should be removed (permissions not in spec)

---

## Recommendations

### Priority 1: Fix Auth Routes (8 tests)
**Action:** Move auth endpoints to `/api/v1/auth/` namespace  
**Effort:** Low (URL configuration change)  
**Impact:** Aligns with spec, fixes 8 tests

### Priority 2: Resolve Cafe Permission Tests (6 tests)
**Action:** Either seed permissions or remove tests  
**Effort:** Low  
**Impact:** Clarifies test expectations

---

## Next Steps

1. **Phase 4:** Fix auth URL routing (move from `/users/auth/` to `/auth/`)
2. **Phase 4:** Resolve cafe permission tests (seed or remove)
3. **Phase 5:** Re-run full test suite (expect 236 passed, 0 failed)
