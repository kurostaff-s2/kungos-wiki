# KungOS Integration Wiring Gap Fixes

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | 82b873-wiring |
| Entity type | work_item |
| Short description | Fix critical integration wiring gaps: userid→identity_id migration, response envelope compliance, filter propagation, and API contract alignment |
| Status | draft |
| Source references | `30-06-2026_kungos_wiring_audit.md` (this review), `29-06-2026_kungos_full_scope_testing_d075f8.md` |
| Generated | 30-06-2026 |
| Next action / owner | Implementation agent — execute Phases 1-4 |
| Excluded | E-shop domain, Careers, Tournaments (no frontend), KungOS Admin (backend-only) |

## Primary Goal

**Resolve all critical wiring gaps identified in the integration audit to ensure correct data flow from KungOS_Mongo_One through backend to frontend.**

## Execution Order

```
Phase 1: Schema Alignment (userid → identity_id) — 14 files, 81 refs
    ↓
Phase 2: Response Envelope Compliance — 3 files, 6 INPUT_ERROR refs
    ↓
Phase 3: CANCELLED (no-op — Home.jsx has no legacy division= API calls)
    ↓
Phase 4: API Contract — 1 verified fix (Cafe FNB route mismatch)
    ↓
Phase 5: Audit Unverified P1 Issues — 7 items need live verification
```

---

## Project Context

**Backend project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Frontend project root:** `/home/chief/Coding-Projects/kteam-fe-chief`
**Authoritative specs:**
- `endpoint_contract_spec_revised.md` — Wire contract authority
- `multi_tenancy.md` — Multi-tenancy constitution
- `CANONICAL_NAMING.md` — Naming gate

---

## Phase 1: Schema Alignment (userid → identity_id)

**What:** Replace `request.user.userid` with `identity_id` for all cross-domain person references. Preserve `userid` for auth context only (CustomUser.auth).

**Files to Modify (15 files, 100+ references):**

| File | Lines | Action |
|------|-------|--------|
| `domains/tournaments/views.py` | 87, 114, 134, 151, 161, 212 | Replace `request.user.userid` → `identity_id` |
| `domains/orders/viewsets.py` | 179, 222, 332, 337, 340, 387, 427, 544, 564, 608, 754, 766, 803, 863, 875, 905 | Replace `request.user.userid` → `identity_id` |
| `domains/orders/services.py` | 217, 219, 221, 249, 251, 267, 483, 692, 710, 738 | Replace `request.user.userid` → `identity_id` |
| `domains/orders/estimates/viewsets.py` | 148, 150, 155, 174, 176 | Replace `request.user.userid` → `identity_id` |
| `domains/accounts/expenditure/inward_debit_notes.py` | 100, 139, 143 | Replace `request.user.userid` → `identity_id` |
| `domains/accounts/sales/viewsets.py` | 174, 224, 244, 246, 455, 494, 498 | Replace `request.user.userid` → `identity_id` |
| `domains/accounts/services.py` | 140, 142 | Replace `request.user.userid` → `identity_id` |
| `domains/cafe_arcade/views.py` | 126, 160, 161, 168, 180, 208, 229, 387, 409, 414, 598 | Replace `request.user.userid` → `identity_id` |
| `domains/cafe_arcade/views_tracker.py` | 106, 338 | Replace `request.user.userid` → `identity_id` |
| `domains/products/viewsets.py` | 153, 201, 284, 299, 301, 336, 472, 484, 533, 680, 695, 697, 770, 1023, 1033, 1376, 1460, 1603 | Replace `request.user.userid` → `identity_id` |
| `domains/products/services.py` | 94, 100 | Replace `request.user.userid` → `identity_id` |
| `domains/vendors/viewsets.py` | 129, 194, 253 | Replace `request.user.userid` → `identity_id` |
| `domains/teams/viewsets.py` | 110, 119, 152, **221** | Replace `request.user.userid` → `identity_id` (line 221 has `'identity_id': str(user.userid)` — **wiring gap!**) |
| `domains/shared/viewsets.py` | 221 | Replace `request.user.userid` → `identity_id` |

**Steps:**

1. **Identify auth vs. cross-domain usage:**
   - **Auth context (preserve `userid`):** `CustomUser.auth`, JWT token generation, session management
   - **Cross-domain (replace with `identity_id`):** Document creation, order tracking, invoice references, player/gamer records

2. **Apply replacements:**
   ```python
   # Before (incorrect):
   data['created_by'] = request.user.userid
   
   # After (correct):
   result = resolve_access(request)
   data['created_by'] = result['identity_id']
   ```

3. **Verify no `userid` remains in cross-domain context:**
   ```bash
   rg -n "\.userid" /home/chief/Coding-Projects/kteam-dj-chief/domains/ | grep -v "CustomUser" | grep -v "request.user.userid"
   ```

**Tests:**
- [ ] 0 `request.user.userid` references in domains (except auth context)
- [ ] All cross-domain person references use `identity_id`
- [ ] CustomUser.auth still uses `userid` for session management
- [ ] No regression in existing tests

**Dependencies:** None (Phase 1 is independent)

---

## Phase 2: Response Envelope Compliance

**What:** Replace `INPUT_ERROR` with `VALIDATION_ERROR` and `api_error()` with `error_response()` from `backend.response_utils`.

**Files to Modify (6 files):**

| File | Issue | Action |
|------|-------|--------|
| `users/api/viewsets.py` | `INPUT_ERROR` | Replace with `VALIDATION_ERROR` |
| `users/views.py` | `INPUT_ERROR` | Replace with `VALIDATION_ERROR` |
| `users/api/identity_views.py` | `INPUT_ERROR` | Replace with `VALIDATION_ERROR` |
| `tenant/context_views.py` | `api_error()` | Replace with `error_response()` |
| `careers/views.py` | `api_error()` | Replace with `error_response()` |
| `domains/shared/millie.py` | `api_error()` | Replace with `error_response()` |

**Steps:**

1. **Replace `INPUT_ERROR` → `VALIDATION_ERROR`:**
   ```python
   # Before:
   return error_response("Validation failed", code='INPUT_ERROR')
   
   # After:
   return error_response("Validation failed", code='VALIDATION_ERROR')
   ```

2. **Replace `api_error()` → `error_response()`:**
   ```python
   # Before:
   body, status = api_error("Not found", code='NOT_FOUND')
   return Response(body, status=status)
   
   # After:
   return error_response("Not found", code='NOT_FOUND')
   ```

3. **Verify no `INPUT_ERROR` or `api_error()` remains:**
   ```bash
   rg -l "INPUT_ERROR" /home/chief/Coding-Projects/kteam-dj-chief/ | grep -v ".bak"
   rg -l "api_error(" /home/chief/Coding-Projects/kteam-dj-chief/ | grep -v ".bak"
   ```

**Tests:**
- [ ] 0 `INPUT_ERROR` references (except .bak files)
- [ ] 0 `api_error()` tuple unpacking in domains
- [ ] All error responses use `error_response()` from `backend.response_utils`
- [ ] All files compile without syntax errors

**Dependencies:** None (Phase 2 is independent)

---

## Phase 3: CANCELLED (No-Op)

**Status:** ❌ **CANCELLED** — No action needed

**Reason:** Live codebase verification shows Home.jsx has NO legacy `division=` API calls. Only match is a `console.log` statement:
```javascript
// src/pages/Home.jsx:66
console.log(`[DASHBOARD] filterByDiv: ${items.length} → ${filtered.length} (division=${activeDivision})`)
```

**Verification:**
```bash
$ rg -n "division=" /home/chief/Coding-Projects/kteam-fe-chief/src/
src/pages/Home.jsx:66:    console.log(...)
```

**Conclusion:** Filter propagation is already correct. No changes needed.

**Dependencies:** None (skipped)

---

## Phase 4: API Contract Alignment

**What:** Fix verified route/endpoint mismatches between frontend and backend.

### Phase 4a: Verified P0 Issue (Must Fix)

| # | Domain | Issue | Status | Fix |
|---|--------|-------|--------|-----|
| 1 | Cafe Tracker | Route not registered | ❌ FALSE | Already registered in `src/routes/main.jsx:262` |
| 2 | Cafe FNB | URL mismatch: `cafe/fnb/menu` vs `cafe-fnb/menu` | ⚠️ PARTIAL | Fix frontend route path |
| 3 | Cafe Tracker | `cafeTrackerApi.js` doesn't unwrap envelopes | ❌ FALSE | Already uses `fetcher` from `api.jsx` |

**Issue #2: Cafe FNB Route Mismatch (Verified)**

**Problem:** Frontend route uses `/cafe/fnb/menu` (no hyphen), but backend uses `/cafe-fnb/menu` (with hyphen).

**Live state:**
- **Backend:** `/api/v1/cafe-fnb/menu` ✅
- **Frontend API:** `src/lib/cafeApi.js` uses `/api/v1/cafe-fnb/` ✅
- **Frontend Route:** `src/routes/main.jsx:263` uses `/cafe/fnb/menu` ⚠️

**Fix:**
```javascript
// src/routes/main.jsx:263
// Before:
<Route path="/cafe/fnb/menu" element={<FnbMenuManagement />} />

// After:
<Route path="/cafe-fnb/menu" element={<FnbMenuManagement />} />
```

Also update `src/data/sidebar-nav.js:229`:
```javascript
// Before:
{ label: 'F&B Menu', to: '/cafe/fnb/menu', ... }

// After:
{ label: 'F&B Menu', to: '/cafe-fnb/menu', ... }
```

### Phase 4b: Unverified P1 Issues (Need Audit)

| # | Domain | Issue | Status | Action |
|---|--------|-------|--------|--------|
| 5 | Accounts | No route for Ledgers page | ❓ UNVERIFIED | Audit |
| 6 | Accounts | No route for Financials page | ❓ UNVERIFIED | Audit |
| 7 | Products | `products/kurodata` not in urls.py | ❌ FALSE | Already in `shared/kurodata` |
| 8 | Products | No route for PreBuilts page | ❓ UNVERIFIED | Audit |
| 9 | Products | No route for Peripherals page | ❓ UNVERIFIED | Audit |
| 10 | Inventory | `/api/products/stock-audit` vs `/api/v1/inventory/stock-audit` | ❓ UNVERIFIED | Audit |
| 11 | Teams | `teams/employeesdata` not in urls.py | ❌ FALSE | Already in `teams/urls.py:32` |
| 12 | Teams | `teams/emp-attendance` not in urls.py | ❌ FALSE | Already in `teams/urls.py:33` |
| 13 | Teams | `teams/emp-attendancedate` not in urls.py | ❌ FALSE | Already in `teams/urls.py:34` |
| 14 | Shared | `/api/v1/shared/checklist` not in urls.py | ❌ FALSE | Already in `shared/urls.py:57` |
| 15 | Auth | `/pwdreset` not in urls.py | ❌ FALSE | Already in `users/api/auth_urls.py:49` |
| 16 | Cafe Tracker | Close receipt field mismatches | ❓ UNVERIFIED | Audit |
| 17 | Cafe FNB | Menu response shape mismatch | ❓ UNVERIFIED | Audit |

**False Claims (Already Implemented):**
- Issue #7: `kurodata` is in `domains/shared/urls.py:62`, not `products/`
- Issue #11-13: Teams endpoints are in `domains/teams/urls.py:32-34`
- Issue #14: Checklist is in `domains/shared/urls.py:57`
- Issue #15: pwdreset is in `users/api/auth_urls.py:49`

**Steps:**

1. **Fix verified Issue #2:**
   - Update `src/routes/main.jsx:263` from `/cafe/fnb/menu` → `/cafe-fnb/menu`
   - Update `src/data/sidebar-nav.js:229` from `/cafe/fnb/menu` → `/cafe-fnb/menu`

2. **Audit unverified P1 issues (#5-6, #8-9, #10, #16-17):**
   - Verify each claim against live codebase
   - Check if route/endpoint exists in `domains/*/urls.py`
   - Check if frontend route exists in `src/routes/main.jsx`
   - Check if response shape matches spec

3. **Fix verified issues:**
   - Add missing routes/endpoints if confirmed broken
   - Align response shapes if confirmed mismatched

**Tests:**
- [ ] Issue #2 fixed (Cafe FNB route uses `/cafe-fnb/menu`)
- [ ] All false claims documented (Issues #7, #11-15)
- [ ] All unverified issues audited (Issues #5-6, #8-9, #10, #16-17)
- [ ] No 404 errors in browser console (if backend running)

**Dependencies:** Phases 1-2 must be complete before Phase 4

---

## Phase 5: Audit Unverified P1 Issues

**What:** Verify the 7 unverified P1 issues against live codebase to determine if they're actually broken.

**Unverified Issues:**
| # | Domain | Issue |
|---|--------|-------|
| 5 | Accounts | No route for Ledgers page |
| 6 | Accounts | No route for Financials page |
| 8 | Products | No route for PreBuilts page |
| 9 | Products | No route for Peripherals page |
| 10 | Inventory | `/api/products/stock-audit` vs `/api/v1/inventory/stock-audit` |
| 16 | Cafe Tracker | Close receipt field mismatches |
| 17 | Cafe FNB | Menu response shape mismatch |

**Verification Steps:**

For each issue, run:
```bash
# Check if backend endpoint exists
rg -n "pattern" /home/chief/Coding-Projects/kteam-dj-chief/domains/

# Check if frontend route exists
rg -n "pattern" /home/chief/Coding-Projects/kteam-fe-chief/src/

# Check if response shape matches spec
rg -n "pattern" /home/chief/Coding-Projects/kteam-fe-chief/src/lib/
```

**Expected Outcomes:**
- If endpoint/route exists: Mark as **FALSE** (no action needed)
- If endpoint/route missing: Mark as **TRUE** and fix
- If response shape mismatch: Mark as **TRUE** and align

**Files to Audit:**
- `domains/accounts/urls.py` — Check for Ledgers/Financials routes
- `domains/products/urls.py` — Check for PreBuilts/Peripherals routes
- `domains/inventory/urls.py` — Check stock-audit URL
- `domains/cafe_arcade/views_tracker.py` — Check close receipt fields
- `domains/cafe_fnb/views.py` — Check menu response shape

**Tests:**
- [ ] All 7 issues audited
- [ ] False claims documented
- [ ] True claims fixed
- [ ] No unverified issues remain

**Dependencies:** Phase 4 must be complete before Phase 5

---

## Constraints

- **Do NOT modify** `src/pages/Accounts/Analytics.jsx`, `src/pages/Home.jsx` (except Phase 3), or `src/hooks/useTenantParams.jsx`
- **FilterParserMixin must NOT parse tenant fields** (`div_code`, `branch_code`, `bg_code`)
- **No legacy alias support** in the mixin — `division=` is ignored, not mapped
- **All `query_params.get('division')` → `query_params.get('div_code')`**
- **`userid` exists ONLY on `CustomUser`** — all cross-domain person references use `identity_id`
- **All tests must run against the migrated codebase** (commit `41b3756` or later)
- **E-shop domain excluded** — do not touch eshop files
- **KungOS Admin domain included** — verify tenant bootstrap, domain config, API keys, templates

---

## Success Criteria

### Phase 1: Schema Alignment
- [ ] 0 `request.user.userid` references in domains (except auth context)
- [ ] All cross-domain person references use `identity_id`
- [ ] CustomUser.auth still uses `userid` for session management
- [ ] No regression in existing tests

### Phase 2: Response Envelope Compliance
- [ ] 0 `INPUT_ERROR` references (except .bak files)
- [ ] 0 `api_error()` tuple unpacking in domains
- [ ] All error responses use `error_response()` from `backend.response_utils`
- [ ] All files compile without syntax errors

### Phase 3: Filter Propagation
- [x] CANCELLED — No-op (Home.jsx has no legacy division= API calls)

### Phase 4: API Contract Alignment
- [ ] Issue #2 fixed (Cafe FNB route uses `/cafe-fnb/menu`)
- [ ] All false claims documented (Issues #7, #11-15)
- [ ] All unverified issues audited (Issues #5-6, #8-9, #10, #16-17)

### Phase 5: Audit Unverified P1 Issues
- [ ] All 7 issues audited
- [ ] False claims documented
- [ ] True claims fixed
- [ ] No unverified issues remain

### Full Scope
- [ ] Backend starts and serves all endpoints
- [ ] Frontend builds and loads all pages
- [ ] No console errors in browser
- [ ] All existing tests still pass (no regression)

---

## Caveats & Uncertainty

1. **Auth context preservation:** `userid` must be preserved for `CustomUser.auth` (session management, JWT generation). Only replace in cross-domain person references.

2. **Test data:** If tests fail after migration, verify test data uses `identity_id` (not `userid`) for person references.

3. **Frontend components:** Some frontend components may reference `userid` in display logic. These are acceptable if they're showing auth context (not cross-domain references).

4. **Third-party integrations:** If any third-party APIs expect `userid`, document the mapping and preserve it.

5. **Migration script:** Consider generating a migration script to update existing MongoDB documents from `userid` to `identity_id` if needed.

---

## Next Steps

1. **Phase 1:** Execute schema alignment (userid → identity_id)
2. **Phase 2:** Execute response envelope compliance
3. **Phase 3:** Execute filter propagation
4. **Phase 4:** Execute API contract alignment
5. **Verification:** Run full test suite, verify backend/frontend start
6. **Commit:** Commit all changes to `origin/develop`
7. **Update:** Update this handoff with results

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `29-06-2026_kungos_full_scope_testing_d075f8.md` | Original testing handoff (Phases 0-7) |
| `endpoint_contract_spec_revised.md` | Authoritative wire contract |
| `multi_tenancy.md` | Multi-tenancy constitution |
| `CANONICAL_NAMING.md` | Naming gate |
| `backend/response_utils.py` | Canonical response envelope |
| `backend/exceptions.py` | Standard error classes |
| `plat/django/filters.py` | FilterParserMixin |
| `src/lib/api.jsx` | Frontend API client |
| `src/hooks/useTenantQuery.jsx` | Frontend tenant query builder |

---

## Execution Summary

| Phase | Status | Results |
|-------|--------|---------|
| Phase 1: Schema Alignment | ⏳ NEXT | 14 files, 81 refs (verified) |
| Phase 2: Response Envelope | ⏳ NEXT | 3 files, 6 INPUT_ERROR refs (verified) |
| Phase 3: Filter Propagation | ❌ CANCELLED | No-op (no legacy division= API calls) |
| Phase 4: API Contract | ⏳ NEXT | 1 verified fix (Cafe FNB route) |
| Phase 5: Audit P1 Issues | ⏳ NEXT | 7 items need live verification |

*Handoff generated: 30-06-2026*
*Handoff updated: 30-06-2026 (corrected after live codebase verification)*
*Excluded: E-shop domain, Careers, Tournaments (no frontend), KungOS Admin (backend-only)*
*Total estimated effort: 2-3 hours (Phases 1-2-4) + 30 min (Phase 5 audit)*

## Verification Notes

**Live codebase verification performed:**
- ✅ Phase 1: 81 `request.user.userid` refs confirmed in 14 files
- ✅ Phase 2: 6 `INPUT_ERROR` refs confirmed in 3 files
- ❌ Phase 3: No legacy `division=` API calls found (only console.log)
- ❌ Phase 4a #1: Cafe Tracker route already registered
- ⚠️ Phase 4a #2: Frontend route mismatch verified (1 line fix)
- ❌ Phase 4a #3: cafeTrackerApi.js already uses fetcher (unwraps envelopes)
- ❌ Phase 4b #7: kurodata in shared/urls.py (not products/)
- ❌ Phase 4b #11-13: Teams endpoints in teams/urls.py
- ❌ Phase 4b #14: Checklist in shared/urls.py
- ❌ Phase 4b #15: pwdreset in auth_urls.py

**Key insight:** Many "P0/P1 issues" in original handoff were already implemented. Live codebase verification prevents wasted effort on non-issues.
