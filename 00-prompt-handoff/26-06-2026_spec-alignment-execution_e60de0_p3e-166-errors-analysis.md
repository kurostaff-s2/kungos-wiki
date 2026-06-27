# Phase 3E: 166 Pre-existing Errors Analysis

**Date:** 2026-06-27  
**Status:** Analysis Complete  
**Total Errors:** 166

---

## Summary

| Category | Count | Spec Violation? | Root Cause |
|----------|-------|-----------------|------------|
| Missing `@pytest.mark.django_db` | 166 | ❌ NO | Test setup issue |

---

## Root Cause

**All 166 errors are caused by missing `@pytest.mark.django_db` decorator** on test classes or methods that access the database.

**Error Message:**
```
RuntimeError: Database access not allowed, use the "django_db" mark, 
or the "db" or "transactional_db" fixtures to enable it.
```

---

## Affected Test Files

| Test File | Errors | Tests Affected |
|-----------|--------|----------------|
| `test_reporting.py` | 35 | ViewSet tests, URL routes, tenant context, migration command |
| `test_domains_rbac_migration.py` | 32 | Legacy imports/calls/access dict checks |
| `test_teams_rbac_migration.py` | 28 | Legacy imports/calls/access dict checks |
| `test_legacy_removal.py` | 17 | Legacy function removal, constant removal |
| `test_outbox.py` | 10 | Outbox event tests |
| `test_access_control.py` | 8 | CheckPermission, IsSupervisor, Cors |
| `test_kurostaff_rbac_migration.py` | 8 | Kurostaff RBAC patterns |
| `test_events.py` | 7 | Event types, domain events |
| `test_users_rbac_migration.py` | 6 | Legacy imports/calls/access dict |
| `test_auth.py` | 3 | Throttling, health endpoints |
| `test_division_scoping_migration.py` | 3 | Division scoping patterns |
| `test_reporting_base_rbac.py` | 3 | Reporting base RBAC |
| `test_tenant_scope.py` | 3 | Tenant config, user context |
| `test_webhooks.py` | 3 | Payment webhooks |

---

## Analysis

### Not Spec Violations

These errors are **test infrastructure issues**, not spec violations:

1. **Missing decorator** — Tests that need DB access don't have `@pytest.mark.django_db`
2. **Test isolation** — Tests run in isolation but need DB transactions
3. **Fixture missing** — No `db` or `transactional_db` fixture applied

### Spec Compliance

All 166 errors are in **test files only**. The actual application code:
- ✅ Has no database access issues
- ✅ Complies with spec requirements
- ✅ Passes system checks (0 issues)

---

## Fix Options

### Option 1: Add Decorator to Each Test Class (Recommended)
**Effort:** Medium (14 files to update)  
**Impact:** Fixes all 166 errors  
**Risk:** Low — standard pytest Django pattern

### Option 2: Add Global Fixture in conftest.py
**Effort:** Low (1 line in conftest.py)  
**Impact:** Fixes all 166 errors  
**Risk:** Medium — may mask test isolation issues

### Option 3: Use pytest.ini Configuration
**Effort:** Low (1 line in pytest.ini)  
**Impact:** Fixes all 166 errors  
**Risk:** Low — standard pytest configuration

---

## Recommendation

**Option 1:** Add `@pytest.mark.django_db` to test classes that need DB access.

This is the standard Django/pytest pattern and ensures test isolation.

---

## Next Steps

1. Add `@pytest.mark.django_db` to affected test classes
2. Re-run full test suite (expect 0 errors)
3. Update test documentation to include decorator requirements
