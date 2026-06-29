# KungOS P0 Bug Fixes — Applied

**Date:** 2026-06-29  
**Status:** ✅ **3/3 P0 bugs fixed**

---

## Fixes Applied

### Fix 1: `domains/teams/viewsets.py:161` — `userid` → `identity_id`

**Bug:** `NameError: name 'userid' is not defined`  
**Root Cause:** Variable captured as `identity_id` but used as `userid`

**Change:**
```python
# Before:
identity_id = request.query_params.get('identity_id')
if userid:  # NameError!
    user_obj = CustomUser.objects.get(userid=userid)

# After:
identity_id = request.query_params.get('identity_id')
if identity_id:
    user_obj = Identity.objects.get(identity_id=identity_id).user
```

**Status:** ✅ Fixed  
**Test Result:** `GET /api/v1/teams/users` → 200 OK

---

### Fix 2: `backend/auth_utils.py:145` — Handle missing BusinessGroup

**Bug:** `BusinessGroup.DoesNotExist` when `bg_code` is empty  
**Root Cause:** `resolve_minimal()` didn't handle empty `bg_code`

**Change:**
```python
# Before:
def resolve_minimal(request):
    ctx = _get_switchgroup(request)
    bg = BusinessGroup.objects.get(bg_code=ctx.bg_code)  # Crashes if bg_code=''
    return ctx, bg

# After:
def resolve_minimal(request):
    ctx = _get_switchgroup(request)
    if not ctx.bg_code:
        return ctx, None  # Graceful handling
    bg = BusinessGroup.objects.filter(bg_code=ctx.bg_code).first()
    if not bg:
        raise BusinessGroup.DoesNotExist(f"BusinessGroup '{ctx.bg_code}' not found")
    return ctx, bg
```

**Status:** ✅ Fixed  
**Test Result:** `GET /api/v1/accounts/inward-invoices` → 200 OK

---

### Fix 3: `users/api/viewsets.py` — Remove hardcoded `'BG0001'` fallback

**Bug:** Login response had `bg_code: 'BG0001'` but JWT had `'KURO0001'`  
**Root Cause:** Hardcoded fallback `'BG0001'` in tenant context resolution

**Changes:**
```python
# Before:
'bg_code': identity.bg_code or 'BG0001',
'bg_code': ctx.bg_code or 'BG0001',

# After:
'bg_code': identity.bg_code or '',
'bg_code': ctx.bg_code or '',
```

**Additional Fix:** Updated UserRole and UserTenantContext records in database:
- `UserRole.objects.filter(bg_code='BG0001').update(bg_code='KURO0001')` → 5 records updated
- `UserTenantContext.objects.filter(bg_code='BG0001').update(bg_code='KURO0001')` → 2 records updated

**Status:** ✅ Fixed  
**Test Result:** Login response `bg_code: 'KURO0001'` (matches JWT)

---

## Test Results Summary

### Before Fixes

| Endpoint | Status | Error |
|----------|--------|-------|
| `/teams/users` | ❌ 500 | `NameError: name 'userid'` |
| `/accounts/inward-invoices` | ❌ 500 | `BusinessGroup.DoesNotExist` |
| Login response `bg_code` | ❌ Mismatch | `'BG0001'` vs `'KURO0001'` |

### After Fixes

| Endpoint | Status | Notes |
|----------|--------|-------|
| `/teams/users` | ✅ 200 | Returns user list |
| `/accounts/inward-invoices` | ✅ 200 | Returns invoice data |
| Login response `bg_code` | ✅ `'KURO0001'` | Matches JWT |
| `/teams/employees` | ✅ 200 | Returns employee list |
| `/accounts/outward-invoices` | ✅ 200 | Returns invoice data |
| `/accounts/purchase-orders` | ✅ 200 | Returns PO data |
| `/cafe/stations` | ✅ 200 | Returns station list |
| `/cafe/sessions/active` | ✅ 200 | Returns active sessions |

---

## Remaining Issues (P1/P2)

### P1: Trailing Slash Redirects (301)

| Endpoint | Issue |
|----------|-------|
| `/users/me` | Redirects to `/users/me/` |
| `/eshop/cart` | Redirects to `/eshop/cart/` |
| `/tenant/current` | Redirects to `/tenant/current/` |

**Impact:** Minor — Axios may not follow redirects with credentials

**Fix:** Add trailing slashes to URL patterns or ensure frontend uses trailing slashes

### P1: Cafe Permission Denied (403)

| Endpoint | Issue |
|----------|--------|
| `/cafe/dashboard/overview` | Missing `cafe.dashboard` permission |
| `/cafe/pricing/rules` | Missing `cafe.pricing` permission |

**Impact:** Cafe dashboard pages cannot load

**Fix:** Add cafe permissions to test user's UserRole

### P2: Inventory Stock (500)

| Endpoint | Issue |
|----------|--------|
| `/inventory/stock` | `Unauthorized` error |

**Impact:** Inventory pages cannot load

**Fix:** Investigate inventory auth middleware

---

## Files Modified

1. `domains/teams/viewsets.py` — Fix `userid` → `identity_id`
2. `backend/auth_utils.py` — Handle missing BusinessGroup
3. `users/api/viewsets.py` — Remove `'BG0001'` fallback

## Database Changes

- `UserRole`: 5 records updated (`BG0001` → `KURO0001`)
- `UserTenantContext`: 2 records updated (`BG0001` → `KURO0001`)

---

**Verification:** Run comprehensive API test to confirm all P0 bugs are resolved.

**Next Steps:** Fix P1 issues (trailing slashes, cafe permissions, inventory auth)
