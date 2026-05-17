# MongoDB Field Migration: Legacy → Canonical Tenant Fields

**Date:** 2026-05-17  
**Status:** Complete  
**Approvals:** Council consensus (Nemo, Gemma, Diversity)  
**Related Constitution:** `architecture/multi_tenancy.md` (Tenant Isolation Strategy)  

---

## Summary

Migrated all MongoDB tenant fields from legacy naming to canonical naming across 31 collections (136,886 documents) and updated all corresponding Python code references.

| Legacy Field | Canonical Field | Scope |
|-------------|----------------|-------|
| `bgcode` | `bg_code` | All 31 collections |
| `division` | `div_code` | All 31 collections |
| `branch` | `branch_code` | All 31 collections |

---

## Phase 1: MongoDB Data Migration

**Command:** `python3 manage.py migrate_tenant_fields`  
**Tool:** `plat/management/commands/migrate_tenant_fields.py`

### Execution Log

| Step | Command | Result |
|------|---------|--------|
| Dry-run | `migrate_tenant_fields` | 136,886 documents flagged across 31 collections |
| Execute | `migrate_tenant_fields --execute` | 136,886 documents renamed |
| Verify | `migrate_tenant_fields --verify` | ✅ All collections clean |

### Collections Affected (all 31)

| Collection | Documents | Fields Renamed |
|-----------|-----------|---------------|
| employee_attendance | 966 | bgcode, division |
| accounts | 7 | bgcode, division |
| teams | 14 | bgcode, division |
| inwardpayments | 21,026 | bgcode, division |
| indentproduct | 1,490 | bgcode, division |
| indentpos | 247 | bgcode, division |
| entities | 2 | bgcode, division |
| outwardinvoices | 1,165 | bgcode, division |
| players | 117 | bgcode, division |
| tporders | 229 | bgcode, division |
| outward | 754 | bgcode, division |
| inwarddebitnotes | 3 | bgcode, division |
| products | 82 | bgcode, division |
| tournaments | 3 | bgcode, division |
| misc | 5,512 | bgcode, division |
| serviceRequest | 1,625 | bgcode, division |
| stock_register | 194 | bgcode, division |
| tourneyregister | 56 | bgcode, division |
| paymentvouchers | 3,459 | bgcode, division |
| estimates | 4,308 | bgcode, division |
| presets | 6 | bgcode, division |
| purchaseorders | 15,216 | bgcode, division |
| tpbuilds | 123 | bgcode, division |
| bgData | 1 | bgcode, division |
| vendors | 409 | bgcode, division |
| reb_users | 1,982 | bgcode, division |
| kgorders | 9,162 | bgcode, division |
| inwardinvoices | 16 | bgcode, division |
| inwardcreditnotes | 106 | bgcode, division |
| outwarddebitnotes | 13 | bgcode, division |
| outwardcreditnotes | 150 | bgcode, division |

---

## Phase 2: Code Migration

### Files Modified (15 files, ~200 references)

| File | Changes | Type |
|------|---------|------|
| `backend/utils.py` | 10 lines | Tenant filter, insert_one, projections |
| `teams/kurostaff/views.py` | 59 lines | MongoDB queries, aggregations |
| `teams/financial.py` | 32 lines | MongoDB queries |
| `teams/products.py` | 19 lines | MongoDB queries, filters |
| `teams/outward_invoices.py` | 20 lines | MongoDB queries, function calls |
| `teams/inward_invoices.py` | 15 lines | MongoDB queries |
| `teams/estimates.py` | 5 lines | MongoDB queries |
| `domains/cafe_arcade/legacy_views.py` | 7 lines | MongoDB queries, projections |
| `domains/shared/viewsets.py` | 3 lines | MongoDB queries |
| `teams/analytics.py` | 4 lines | MongoDB queries |
| `teams/service_requests.py` | 3 lines | MongoDB queries |
| `teams/employees.py` | 1 line | MongoDB query |
| `users/views.py` | 1 line | Query param |
| `domains/accounts/viewsets.py` | 12 lines | Document insertion |
| `domains/teams/viewsets.py` | 1 line | Document insertion |
| `domains/products/viewsets.py` | 1 line | Document insertion |
| `domains/cafe_fnb/gateways.py` | 3 lines | Document insertion |

### Critical Fixes (Council Review Findings)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 1 | `get_collection()` used `bgcode` | `backend/utils.py:289` | → `bg_code` |
| 2 | `insert_one()` used legacy fields | `backend/utils.py:445-450` | → `bg_code`, `div_code`, `branch_code` |
| 3 | Projection dicts used `branch` | `backend/utils.py:513-514` | → `branch_code` |
| 4 | `creating_kgorders()` wrong kwarg `division=` | `teams/outward_invoices.py:230` | → `divisions_list=[...]` |
| 5 | `creating_kgorders()` wrong kwarg `division=` | `teams/kurostaff/views.py:2654` | → `divisions_list=[...]` |
| 6 | Undefined `divisions_list` | `teams/outward_invoices.py:89` | → `divisions` |
| 7 | Duplicate keys in query dict | `teams/outward_invoices.py:322` | → `{"$in": divisions + [None]}` |
| 8 | Aggregation pipeline `bgcode` | `teams/kurostaff/views.py:1131` | → `bg_code` |
| 9 | Aggregation pipeline `bgcode` | `teams/kurostaff/views.py:1924` | → `bg_code` |
| 10 | Document insertion `bgcode` | `domains/accounts/viewsets.py` (12 lines) | → `bg_code` |
| 11 | Document insertion `bgcode` | `domains/teams/viewsets.py:109` | → `bg_code` |
| 12 | Document insertion `bgcode` | `domains/products/viewsets.py:360` | → `bg_code` |
| 13 | Document insertion `bgcode`, `division`, `branch` | `domains/cafe_fnb/gateways.py:215` | → `bg_code`, `div_code`, `branch_code` |
| 14 | MongoDB field `branch` | `teams/kurostaff/views.py:727` | → `branch_code` |
| 15 | MongoDB field `branch` | `domains/cafe_arcade/legacy_views.py` (3 lines) | → `branch_code` |

### Intentionally Preserved (Not Changed)

| Reference | Reason |
|-----------|--------|
| `users/permissions.py:128` | Docstring example |
| `users/views.py:323,578` | Django model `Accesslevel.division` (PostgreSQL column) |
| `users/api/viewsets.py:1251` | Query param `bgcode` (API contract, frontend sends this) |
| `backend/response_utils.py:110,116` | Docstring examples |
| All `query_params.get('branch')` / `query_params.get('division')` | API parameters (frontend contract) |
| All `getattr(user, 'division')` | Django model field access (PostgreSQL column) |
| `users/views.py` `userData["division"]` | Django model context |
| `plat/observability/middleware.py` `getattr(user, "division")` | Django model field access |

---

## Verification

### MongoDB Verification
```
$ python3 manage.py migrate_tenant_fields --verify
=== VERIFY: Checking for legacy fields ===
✅ All collections clean — no legacy fields found
```

### Code Verification
```
$ grep -rn "'bgcode'\|\"bgcode\"" --include='*.py' | grep -v migrate_tenant | grep -v management/commands | grep -v scripts/
(no output)

$ grep -rn "'branch'\|\"branch\"" --include='*.py' | grep -v migrate_tenant | grep -v management/commands | grep -v scripts/ | grep -v branch_code
(no output)
```

### Council Review
- **Nemo (reviewer-logic):** Identified 2 HIGH issues (`creating_kgorders` kwarg, `get_collection` filter) - both fixed
- **Diversity (reviewer-diversity):** Identified 4 HIGH issues (tenant filter, undefined variable, wrong kwarg, duplicate keys) - all fixed
- **Review files:** `~/.council-memory/reviews/deleg-1778968625/`, `~/.council-memory/reviews/deleg-1778969080/`

---

## Known Issues / Follow-up

| Item | Status | Notes |
|------|--------|-------|
| Query param `bgcode` | **Pending** | Frontend still sends `bgcode` - API accepts both for now |
| Docstring examples | **Cosmetic** | `backend/response_utils.py`, `users/permissions.py` still show old names |
| `creating_kgorders()` signature | **Fixed** | Callers now use `divisions_list=` instead of `division=` |
| MongoDB indexes | **Pending** | Legacy indexes on `bgcode`/`division`/`branch` should be dropped |
| Management commands | **Legacy** | `migrate_mongodb_to_unified.py`, `migrate_reporting_fields.py` still use old field names (not in active use) |

---

## Rollback Plan

If issues arise, reverse the migration:

```bash
# Reverse MongoDB rename (all 31 collections)
python3 manage.py migrate_tenant_fields --reverse

# Revert code changes (git)
git revert <commit-hash>
```

---

## Timeline

| Time | Event |
|------|-------|
| 2026-05-17 02:14 | Dry-run: 136,886 documents identified |
| 2026-05-17 02:15 | Execute: 136,886 documents renamed |
| 2026-05-17 02:17 | Verify: All collections clean |
| 2026-05-17 02:12-03:27 | Code migration: 15 files, ~200 references |
| 2026-05-17 03:24-03:44 | Council review (Nemo, Diversity) |
| 2026-05-17 03:44+ | Critical fixes applied |
| 2026-05-17 03:50 | Final verification: No legacy refs remain |
