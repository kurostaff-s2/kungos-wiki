# Audit Report vs Project Structure — Gap Analysis

**Date:** 2026-06-27
**Purpose:** Compare audit report findings against official project structure document
**Scope:** Discrepancies, inaccuracies, and missed findings

---

## Critical Discrepancies

### 1. `kurostaff/` Package Location — WRONG

**Project Structure Document:**
```
├── kurostaff/                  # Staff Operations (2,935 lines) — TO BE REMOVED
│   ├── views.py                # Inventory, orders, stock management (2,875 lines)
│   ├── models.py               # Staff models (3 lines)
│   ├── urls.py                 # Kurostaff URL routes (25 lines) — TO BE REMOVED
│   └── templatetags/           # Custom template tags
```

**Actual State:**
- `kurostaff/` is at `teams/kurostaff/` (NOT at root level)
- `teams/kurostaff/views.py` is 155KB (NOT 2,875 lines — that's ~5,000 lines)
- `teams/kurostaff/urls.py` exists and is mounted at `teams/urls.py:5`
- **20+ files import from `teams.kurostaff.views`** (actively used, not dead)

**Impact:**
- Audit report didn't flag this as a critical issue
- The package is NOT "TO BE REMOVED" — it's actively imported
- Removing it would break 20+ files

---

### 2. `kuroadmin/` Package — DOES NOT EXIST

**Project Structure Document:**
```
├── kuroadmin/                  # Admin Operations (8,406 lines) — TO BE REMOVED
│   ├── views.py                # Split entry point (186 lines)
│   ├── financial.py            # Migrated to domains/accounts/
│   ├── products.py             # Migrated to domains/products/
│   └── ... (15+ files)
```

**Actual State:**
- `kuroadmin/` directory does NOT exist
- Functionality was migrated to `teams/` directory (which contains the legacy code)
- `teams/` contains: `financial.py`, `products.py`, `inward_invoices.py`, `outward_invoices.py`, etc.

**Impact:**
- Audit report didn't clarify this
- The "TO BE REMOVED" status is misleading — the code exists in `teams/`

---

### 3. EShop Domain — EMPTY (Not Implemented)

**Audit Report Claim:**
> "GET /api/v1/eshop/products/ — ✅ Implemented (MongoDB-backed)"

**Project Structure Document:**
```
├── domains/eshop/                  # E-Commerce domain (mounted at /api/v1/eshop/)
```

**Actual State:**
- `domains/eshop/` contains ONLY: `__init__.py`, `apps.py`, `urls.py`
- `urls.py` has ALL viewsets commented out
- **NO models.py, serializers.py, or viewsets.py**
- URL path `eshop/` is registered but resolves to empty router

**Impact:**
- Audit report is WRONG — EShop is NOT implemented
- This is a CRITICAL gap

---

### 4. `plat/` Directory — NOT MENTIONED in Audit

**Project Structure Document:**
- Shows `plat/` directory with management commands

**Audit Report:**
- Does NOT mention `plat/` directory
- Only mentions `plat/management/commands/mongo_migrate_eshop` in passing

**Impact:**
- Missing `plat/` directory structure from audit
- Important for understanding migration infrastructure

---

### 5. `teams/` Directory — NOT SHOWN in Project Structure

**Project Structure Document:**
- Does NOT show `teams/` directory at all

**Actual State:**
- `teams/` is a major directory with 20+ files
- Contains legacy kurostaff code
- Contains migrated functionality (financial.py, products.py, etc.)

**Impact:**
- Project structure document is INCOMPLETE
- Missing entire directory that's critical to understanding the codebase

---

### 6. Dead Functions in `teams/kurostaff/views.py` — NOT FLAGGED

**Finding:**
- `teams/kurostaff/views.py` has 54 functions
- `teams/kurostaff/urls.py` wires only 20 functions
- **34 functions are dead** (not accessible via URLs)

**Audit Report:**
- Does NOT mention this
- Claims "Legacy routes removed (Phase 3C)" but doesn't flag dead functions

**Impact:**
- 34 dead functions add maintenance burden
- Potential security risk if URL routing changes

---

### 7. `division` vs `div_code` Bug — CORRECTLY IDENTIFIED

**Audit Report:**
> "UserPermissionSerializer references `division` field but model has `div_code`"

**Project Structure Document:**
- Shows `users/api/rbac_serializers.py` exists

**Actual State:**
- Bug is correctly identified
- `users/api/rbac_serializers.py:20,32` reference `division` instead of `div_code`

**Impact:**
- ✅ Audit report is CORRECT on this finding

---

### 8. Missing Serializers — MISLEADING

**Audit Report:**
> "40+ viewsets missing serializers — Will fail at runtime"

**Actual State:**
- Viewsets use custom serialization via `reporting_response()` and `success_response()`
- This is by design for MongoDB-to-JSON conversion
- Not orphaned code — working as intended

**Impact:**
- Audit report is MISLEADING
- No runtime errors
- However, limits OpenAPI schema generation

---

## Summary Table

| # | Finding | Audit Report | Project Structure | Actual State | Status |
|---|---------|--------------|-------------------|--------------|--------|
| 1 | `kurostaff/` location | Not mentioned | Root level | `teams/kurostaff/` | ❌ WRONG |
| 2 | `kuroadmin/` exists | Not mentioned | Root level | Does NOT exist | ❌ WRONG |
| 3 | EShop implemented | ✅ Claimed | Shown as empty | EMPTY | ❌ WRONG |
| 4 | `plat/` directory | Not mentioned | Shown | Exists | ⚠️ MISSING |
| 5 | `teams/` directory | Not mentioned | Not shown | Exists (20+ files) | ⚠️ MISSING |
| 6 | Dead functions | Not mentioned | Not mentioned | 34 dead functions | ❌ MISSED |
| 7 | `division` bug | ✅ Correct | Shown | Correct | ✅ CORRECT |
| 8 | Missing serializers | ❌ Misleading | Shown | Working as designed | ❌ MISLEADING |

---

## Recommendations

### Immediate

1. **Fix project structure document:**
   - Show `teams/` directory with all files
   - Show `kurostaff/` at `teams/kurostaff/` (not root)
   - Remove `kuroadmin/` (doesn't exist)
   - Clarify EShop is empty

2. **Fix audit report:**
   - Remove "EShop implemented" claim
   - Add `teams/` directory to scope
   - Clarify `kurostaff/` location
   - Remove "40+ viewsets missing serializers" (misleading)

3. **Verify `teams/kurostaff/` status:**
   - 20+ files import from it — is it really "TO BE REMOVED"?
   - If yes, need migration plan for all importers
   - If no, update spec to reflect actual state

### Short-term

4. **Update spec documents:**
   - `CAFE_COUNCIL_TODO.md` — Update with actual project structure
   - `KUNGOS_INTEGRATION_PLAN.md` — Update with actual domain layout
   - Any other spec docs that reference `kuroadmin/` or `kurostaff/`

5. **Document `teams/` directory:**
   - Create README for `teams/` explaining legacy vs migrated code
   - Document which files are active vs dead
   - Clarify ownership and maintenance responsibility

---

**Analysis completed:** 2026-06-27
**Next review:** Post-documentation update
