# KungOS Codebase Audit — Gap Report (Supplement to 2026-06-27 Audit)

**Date:** 2026-06-27
**Purpose:** Identify findings missed by the original audit report
**Scope:** Full-stack audit of live codebase

---

## Critical Gaps (Missed by Original Audit)

### 1. EShop Domain is Completely Empty — MAJOR GAP

**Original Audit Claim:**
> "E-commerce: GET /api/v1/eshop/products/ — ✅ Implemented (MongoDB-backed)"

**Actual State:**
- `domains/eshop/` contains ONLY: `__init__.py`, `apps.py`, `urls.py`
- `urls.py` has ALL viewsets commented out:
  ```python
  # router.register('cart', CartViewSet, basename='cart')
  # router.register('wishlist', WishlistViewSet, basename='wishlist')
  # router.register('addresses', AddresslistViewSet, basename='addresses')
  # router.register('orders', OrderViewSet, basename='orders')
  ```
- **NO models.py, serializers.py, or viewsets.py exist**
- URL path `eshop/` is registered in `backend/urls.py` but resolves to empty router

**Impact:**
- `GET /api/v1/eshop/products/` returns 404 or empty response
- Frontend cannot consume e-commerce APIs
- Phase 4B (E-Commerce Products) is NOT implemented

**Status:** ❌ NOT IMPLEMENTED

---

### 2. kurostaff/views.py Has 34 Dead Functions

**Finding:**
- `teams/kurostaff/views.py` defines 54 functions
- `teams/kurostaff/urls.py` wires only 20 functions to URLs
- **34 functions are dead code** (not accessible via any endpoint)

**Dead functions include:**
- `getCounters()` — referenced in URLs but also defined locally
- Multiple helper functions not exposed as endpoints
- Legacy functions that may have been replaced by domain ViewSets

**Impact:**
- Code maintenance burden
- Potential security risk (functions accessible if URL routing changes)
- Confusion about which functions are active

**Status:** ⚠️ NEEDS REVIEW

---

### 3. "40+ Viewsets Missing Serializers" Claim is Misleading

**Original Audit Claim:**
> "Orphaned ViewSets (No Serializer) — These views fail at runtime when DRF tries to serialize responses"

**Actual State:**
- `domains/accounts/viewsets.py` viewsets use custom serialization via:
  - `BaseAccountsViewSet.success_response()` — wraps data in `{data, meta}` envelope
  - `BaseAccountsViewSet.error_response()` — wraps errors in standard format
  - Direct MongoDB document conversion in `list()`, `retrieve()`, etc.
- These viewsets **do not use DRF ModelSerializers** because they're doing custom MongoDB-to-JSON conversion
- This is **by design**, not orphaned code

**Why the audit was wrong:**
- The viewsets manually transform MongoDB documents to JSON responses
- They don't need DRF serializers because they're not using `ModelSerializer` or `Serializer` classes
- The `reporting_response()` and `success_response()` methods provide the response envelope

**Impact:**
- No runtime errors
- Custom serialization is working as intended
- However, this pattern makes it harder to add OpenAPI schema documentation

**Status:** ✅ WORKING AS DESIGNED (but limits OpenAPI generation)

---

### 4. Multiple Domains Have No Django Models

**Finding:**
The following domains use MongoDB directly without Django models:
- `domains/products/` — No `models.py`
- `domains/search/` — No `models.py`
- `domains/shared/` — No `models.py`
- `domains/tournaments/` — No `models.py`
- `domains/teams/` — No `models.py`
- `domains/vendors/` — No `models.py`

**Impact:**
- These domains cannot use Django ORM features (migrations, admin, signals)
- They rely entirely on MongoDB `TenantCollection` for data access
- This may be intentional (legacy MongoDB data), but should be documented

**Status:** ⚠️ BY DESIGN? NEEDS DOCUMENTATION

---

### 5. Cafe Domain Architecture Conflict

**Finding:**
Three cafe-related domains exist with overlapping responsibilities:
- `domains/cafe_arcade/` — Active, 24+ endpoints (sessions, stations, wallets)
- `domains/cafe_fnb/` — New domain (orders, menu, packages)
- `CAFE_COUNCIL_TODO.md` — Mentions `domains/cafe/` as empty shell (Phase 9)

**Original Audit Gap:**
- Did not investigate the conflict between these three domains
- Did not verify if `cafe_arcade` and `cafe_fnb` should be consolidated
- Did not check if `domains/cafe/` shell should be deleted or used

**Impact:**
- Confusion about which domain handles which cafe functionality
- Potential duplicate endpoints or conflicting logic
- Migration path unclear

**Status:** ⚠️ NEEDS ARCHITECTURAL CLARITY

---

### 6. `misc` Collection Still Actively Used

**Original Audit Claim:**
> "Spec claimed 100% duplicate, but has 1,299 unique phones"

**Actual State:**
- `misc` collection is referenced in 10+ code locations:
  - `users/views.py` — `getCounters()`
  - `teams/kurostaff/views.py` — Multiple endpoints
  - `teams/millie.py` — Cleanup scripts
  - `users/management/commands/migrate_mongodb_to_unified.py` — Excluded from migration
- The collection is **not a duplicate** — it stores counter data, inventory types, and other metadata

**Impact:**
- Cannot drop `misc` collection without breaking multiple endpoints
- Original audit's "100% duplicate" claim is incorrect
- Migration strategy needs revision

**Status:** ❌ CANNOT DROP — STILL ACTIVE

---

### 7. OpenAPI Schema Generation Broken (Confirmed)

**Original Audit Finding:**
> "OpenAPI/Swagger docs at `/api/v1/docs/swagger/` — BROKEN (due to serializer bug)"

**Root Cause:**
- `UserPermissionSerializer` references `division` field but model has `div_code`
- `UserRoleSerializer` references `division` field but model has `div_code`
- This causes `drf_spectacular` schema generation to fail

**Impact:**
- No API documentation available
- Frontend developers cannot discover endpoints
- Auto-generated client libraries fail

**Status:** ❌ BROKEN — NEEDS FIX

---

### 8. Observability Gaps (Confirmed)

**Original Audit Finding:**
> "No structured logging, request tracing, or error tracking"

**Current State:**
- Health check endpoints exist (`/health/`, `/ping/`)
- DRF exception handler is active
- Response envelope is active
- **NO:** Structured logging (JSON format)
- **NO:** Request tracing (OpenTelemetry)
- **NO:** Error tracking (Sentry)
- **NO:** Performance monitoring

**Impact:**
- Cannot debug production issues
- No visibility into request performance
- No error aggregation or alerting

**Status:** ❌ NOT IMPLEMENTED

---

### 9. Legacy `kurostaff/` Package Still Present — SPEC VIOLATION (CRITICAL)

**Original Audit Gap:**
The audit mentioned "Legacy routes removed (Phase 3C)" but did NOT flag that the `kurostaff/` package itself is still present.

**Spec Requirement (Brand Lock Removal, 25-06-2026):**
> **Phase 5: Legacy Package Removal (Pending)**
> - `kuroadmin/` (8,406 lines) — TO BE REMOVED
> - `kurostaff/` (2,935 lines) — TO BE REMOVED
> **Action:** Delete package + remove URLs from `backend/urls.py`

**Actual State:**
- `teams/kurostaff/` still exists with 54 functions (2,935 lines)
- `teams/kurostaff/urls.py` still mounted at `/api/v1/kurostaff/`
- 34 of 54 functions are dead (not wired to URLs)
- Functionality claimed migrated to domain modules, but legacy code remains

**Impact:**
- Violates target spec naming convention (brand-scoped names forbidden)
- Creates confusion about what's active vs legacy
- 34 dead functions add maintenance burden
- Potential security risk if URL routing changes

**Status:** ❌ SPEC VIOLATION — MUST BE REMOVED

---

## Summary of Missed Findings

| # | Finding | Severity | Original Audit Status |
|---|---------|----------|----------------------|
| 1 | EShop domain completely empty | **CRITICAL** | ❌ Claimed implemented |
| 2 | kurostaff/views.py has 34 dead functions | HIGH | ❌ Not mentioned |
| 3 | "40+ viewsets missing serializers" is misleading | MEDIUM | ❌ Incorrect assessment |
| 4 | Multiple domains have no Django models | MEDIUM | ❌ Not mentioned |
| 5 | Cafe domain architecture conflict | HIGH | ❌ Not investigated |
| 6 | `misc` collection still actively used | HIGH | ❌ Incorrect claim |
| 7 | OpenAPI schema generation broken | HIGH | ✅ Correctly identified |
| 8 | Observability gaps | MEDIUM | ✅ Correctly identified |
| 9 | Legacy `kurostaff/` package still present — SPEC VIOLATION | **CRITICAL** | ❌ Not mentioned |

---

## Recommendations

### Immediate (Before Production)

1. **Fix EShop domain:**
   - Create `models.py`, `serializers.py`, `viewsets.py` for eshop
   - Or remove `eshop/` URL route if not ready
   - Verify `GET /api/v1/eshop/products/` works

2. **Fix `division` → `div_code` in serializers:**
   - `users/api/rbac_serializers.py` lines 20, 32
   - Enables OpenAPI schema generation

3. **Remove legacy `kurostaff/` package — SPEC VIOLATION:**
   - Delete `teams/kurostaff/` package entirely
   - Remove URLs from `backend/urls.py`
   - Verify no active code paths reference it
   - This is a hard requirement from the Brand Lock Removal spec (25-06-2026)

4. **Audit remaining dead functions:**
   - Remove or document 34 dead functions in kurostaff (before deletion)
   - Verify no active code paths reference them

5. **Verify `misc` collection usage:**
   - Document what data it stores
   - Update migration strategy if needed

### Short-term (1-2 weeks)

5. **Document MongoDB vs PostgreSQL domains:**
   - Create clear documentation on which domains use which database
   - Update CAFE_COUNCIL_TODO.md with current state

6. **Resolve cafe domain architecture:**
   - Decide if `cafe_arcade` and `cafe_fnb` should be consolidated
   - Delete or use `domains/cafe/` shell

7. **Configure observability:**
   - Add structured logging
   - Add request tracing
   - Add error tracking (Sentry)

### Long-term (1-2 months)

8. **Increase test coverage:**
   - Target: 80%+ coverage
   - Add integration tests for all domains
   - Add E2E tests for critical paths

9. **Security hardening:**
   - Rate limiting
   - CORS configuration
   - CSRF protection
   - Input validation

---

**Audit completed:** 2026-06-27
**Next review:** Post-production deployment
