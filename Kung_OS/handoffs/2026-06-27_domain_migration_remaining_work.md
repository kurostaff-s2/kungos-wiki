# Domain Migration — Remaining Work Handoff

**Date:** 2026-06-27  
**Status:** 85% Complete (47/55 functions migrated)  
**Target:** 100% Migration + Zero Duplicates  
**Estimated Time:** 2-3 hours

---

## Executive Summary

The domain migration has successfully moved 47/55 functions from `teams/` to `domains/`. The remaining work involves:

1. **Remove 3 duplicate functions** (already exist in domains/)
2. **Migrate 5-6 remaining functions** (not yet migrated)
3. **Fix 6 stale imports** (placeholder imports until migration completes)
4. **Run full test suite** (verify 157+ tests passing)

**Current Test Count:** 157/157 passing ✅

---

## Phase 1: Remove Remaining Duplicates (30 minutes)

### 1.1 Remove `itc_gst` from `teams/financial.py`

**Location:** `teams/financial.py`  
**Status:** Already migrated to `domains/accounts/tax/gst.py:19`

**Action:**
```bash
# Remove lines containing itc_gst definition (check line numbers)
grep -n "^def itc_gst" teams/financial.py
```

**Verify:**
```bash
# Should return only domains/ location
grep -rn "^def itc_gst" --include="*.py" | grep -v __pycache__ | grep -v venv
```

---

### 1.2 Remove `getestimates` from `teams/estimates.py`

**Location:** `teams/estimates.py:9`  
**Status:** Already migrated to `domains/orders/estimates/services.py:55`

**Action:**
```bash
# Read the file and remove the getestimates function
cat teams/estimates.py
```

**Verify:**
```bash
# Should return only domains/ location
grep -rn "^def getestimates" --include="*.py" | grep -v __pycache__ | grep -v venv
```

---

### 1.3 Remove `bulk_payments` from `teams/financial.py` (if duplicate)

**Location:** `teams/financial.py`  
**Status:** Check if already in `domains/accounts/expenditure/payments.py`

**Action:**
```bash
# Check if bulk_payments exists in domains
grep -n "^def bulk_payments" domains/accounts/expenditure/payments.py

# If exists, remove from teams/financial.py
grep -n "^def bulk_payments" teams/financial.py
```

**Verify:**
```bash
# Should return only domains/ location
grep -rn "^def bulk_payments" --include="*.py" | grep -v __pycache__ | grep -v venv
```

---

## Phase 2: Migrate Remaining Functions (1-2 hours)

### 2.1 Migrate Payment Functions

**Source:** `teams/financial.py`  
**Target:** `domains/accounts/payments/` (create new module)

**Functions to migrate:**
1. `getpaymentvouchers(filters, limit, db_name, bg_code)` → `domains/accounts/payments/services.py`
2. `paymentvouchers(request)` → `domains/accounts/payments/viewsets.py`

**Steps:**
1. Create `domains/accounts/payments/` directory
2. Create `domains/accounts/payments/__init__.py`
3. Create `domains/accounts/payments/services.py` with `getpaymentvouchers`
4. Create `domains/accounts/payments/viewsets.py` with `paymentvouchers`
5. Add authentication, tenant isolation, event emissions
6. Update `teams/financial.py` to import from domains (or remove if no longer used)

**Verification:**
```bash
# Check imports
grep -rn "from teams.financial import.*payment" --include="*.py" | grep -v __pycache__

# Run tests
python3 manage.py test tests/ --no-input
```

---

### 2.2 Migrate Service Request Functions

**Source:** `teams/financial.py`  
**Target:** `domains/service_requests/` (create new module)

**Functions to migrate:**
1. `CreateServiceRequest(serviceData, database, userid)` → `domains/service_requests/services.py`
2. `kuroServiceRequest(request)` → `domains/service_requests/viewsets.py`
3. `serviceRequest(request)` → `domains/service_requests/viewsets.py`

**Steps:**
1. Create `domains/service_requests/` directory
2. Create `domains/service_requests/__init__.py`
3. Create `domains/service_requests/services.py` with `CreateServiceRequest`
4. Create `domains/service_requests/viewsets.py` with `kuroServiceRequest`, `serviceRequest`
5. Add authentication, tenant isolation, event emissions
6. Update `teams/financial.py` to import from domains (or remove if no longer used)

**Verification:**
```bash
# Check imports
grep -rn "from teams.financial import.*ServiceRequest" --include="*.py" | grep -v __pycache__

# Run tests
python3 manage.py test tests/ --no-input
```

---

### 2.3 Migrate `indent_aggregate`

**Source:** `teams/financial.py`  
**Target:** `domains/inventory/indents.py` (or `domains/inventory/services.py`)

**Function:** `indent_aggregate()`

**Steps:**
1. Check if already in `domains/inventory/indents.py`
2. If not, add to `domains/inventory/services.py`
3. Update `teams/financial.py` to import from domains (or remove if no longer used)

**Verification:**
```bash
# Check imports
grep -rn "from teams.financial import.*indent_aggregate" --include="*.py" | grep -v __pycache__

# Run tests
python3 manage.py test tests/ --no-input
```

---

### 2.4 Migrate `outwardpayments_func`

**Source:** `teams/inward_invoices.py:402`  
**Target:** `domains/accounts/sales/reports.py` (or `domains/accounts/sales/services.py`)

**Function:** `outwardpayments_func(db_name, bg_code)`

**Steps:**
1. Add to `domains/accounts/sales/reports.py` or `domains/accounts/sales/services.py`
2. Update `teams/products.py` to import from domains (already done?)
3. Remove from `teams/inward_invoices.py`

**Verification:**
```bash
# Check imports
grep -rn "from teams.inward_invoices import.*outwardpayments" --include="*.py" | grep -v __pycache__

# Run tests
python3 manage.py test tests/ --no-input
```

---

## Phase 3: Fix Stale Imports (30 minutes)

### 3.1 Migrate `home_data`, `doc_generator`, `misc_data`

**Source:** `teams/products.py`  
**Target:** `domains/products/services.py` or `domains/shared/services.py`

**Functions:**
1. `home_data(request)` → `domains/shared/services.py`
2. `doc_generator(request)` → `domains/shared/services.py`
3. `misc_data(request)` → `domains/shared/services.py`

**Steps:**
1. Read functions from `teams/products.py`
2. Add to `domains/shared/services.py`
3. Update `domains/shared/viewsets.py` to import from domains
4. Remove from `teams/products.py` (if no longer used)

**Verification:**
```bash
# Check imports in domains/shared/viewsets.py
grep -n "from teams.products import" domains/shared/viewsets.py

# Run tests
python3 manage.py test tests/ --no-input
```

---

### 3.2 Migrate `smsheaders_data_fetch`

**Source:** `teams/employees.py`  
**Target:** `domains/employees/services.py`

**Function:** `smsheaders_data_fetch()`

**Steps:**
1. Read function from `teams/employees.py`
2. Add to `domains/employees/services.py`
3. Update `domains/shared/viewsets.py` to import from domains
4. Remove from `teams/employees.py` (if no longer used)

**Verification:**
```bash
# Check imports in domains/shared/viewsets.py
grep -n "from teams.employees import" domains/shared/viewsets.py

# Run tests
python3 manage.py test tests/ --no-input
```

---

### 3.3 Migrate `gettpbuilds`

**Source:** `teams/products.py:56`  
**Target:** `domains/products/services.py`

**Function:** `gettpbuilds(filters, specific_fields, limit, bg_code)`

**Steps:**
1. Read function from `teams/products.py`
2. Add to `domains/products/services.py`
3. Update `domains/products/viewsets.py` to import from domains
4. Remove from `teams/products.py` (if no longer used)

**Verification:**
```bash
# Check imports in domains/products/viewsets.py
grep -n "from teams.products import" domains/products/viewsets.py

# Run tests
python3 manage.py test tests/ --no-input
```

---

## Phase 4: Final Cleanup & Verification (30 minutes)

### 4.1 Verify Zero Duplicates

```bash
# Check for duplicate function definitions
for func in sales_func purchases_func financial_totals payment_financials past_present_fin_totals update_inward_data getpurchaseorders purchaseorders estimates indent itc_gst getestimates bulk_payments outwardpayments_func; do
    count=$(grep -rn "^def $func" --include="*.py" | grep -v __pycache__ | grep -v venv | wc -l)
    if [ "$count" -gt 1 ]; then
        echo "DUPLICATE: $func ($count locations)"
        grep -rn "^def $func" --include="*.py" | grep -v __pycache__ | grep -v venv
    fi
done
```

**Expected:** Zero duplicates (except `indent` which has multiple valid definitions in different modules)

---

### 4.2 Verify Zero Stale Imports

```bash
# Check for stale imports from teams/ into domains/
grep -rn "from teams\.\|import teams\." --include="*.py" | grep -v __pycache__ | grep -v "teams/" | grep -v test_
```

**Expected:** Zero stale imports

---

### 4.3 Run Full Test Suite

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
python3 manage.py test tests/ -v 1 --no-input
```

**Expected:** 157+ tests passing ✅

---

### 4.4 Verify Authentication Coverage

```bash
# Check for endpoints without authentication
grep -rn "@authentication_classes(\[\])" domains/ --include="*.py"
```

**Expected:** Zero matches

---

### 4.5 Verify Tenant Isolation

```bash
# Check for hardcoded bg_code
grep -rn "bg_code='BG0001'" domains/ --include="*.py"
```

**Expected:** Zero matches

---

## Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Migrated functions | 47/55 (85%) | 55/55 (100%) |
| Duplicate functions | 3 | 0 |
| Stale imports | 6 | 0 |
| Test count | 157 | 157+ |
| Teams/ functions | 40+ | <10 |

---

## Commit Strategy

1. **Commit 1:** Remove duplicates (itc_gst, getestimates, bulk_payments)
2. **Commit 2:** Migrate payment functions
3. **Commit 3:** Migrate service request functions
4. **Commit 4:** Migrate indent_aggregate, outwardpayments_func
5. **Commit 5:** Migrate home_data, doc_generator, misc_data
6. **Commit 6:** Migrate smsheaders_data_fetch, gettpbuilds
7. **Commit 7:** Final cleanup & verification

Each commit should:
- Include relevant tests
- Pass all tests before committing
- Have clear commit message
- Be pushed to `develop` branch

---

## Verification Checklist

- [ ] Zero duplicate function definitions
- [ ] Zero stale imports from teams/ into domains/
- [ ] 157+ tests passing
- [ ] All domain endpoints have authentication
- [ ] No hardcoded bg_code in domains/
- [ ] All functions follow snake_case naming
- [ ] Event emissions in all migrated viewsets
- [ ] Git history clean (no merge conflicts)

---

## References

- **Migration Plan:** `/home/chief/llm-wiki/Kung_OS/handoffs/2026-06-27_domain_migration_phase_plan.md`
- **Review Fixes:** `/home/chief/llm-wiki/Kung_OS/handoffs/2026-06-27_domain_migration_review_fixes.md`
- **Domain Architecture:** `/home/chief/llm-wiki/Kung_OS/architecture/domain_architecture.md`
- **Platform Primitives:** `/home/chief/llm-wiki/Kung_OS/architecture/platform_primitives.md`

---

## Questions & Clarifications

**Q: Should I create new domains for payments and service requests?**  
A: Yes. Create `domains/accounts/payments/` and `domains/service_requests/`.

**Q: What about functions that are still needed in teams/?**  
A: Keep them in teams/ if they're actively used and not migrated. Don't remove prematurely.

**Q: Should I add tests for migrated functions?**  
A: Yes. Add tests for all newly migrated functions (aim for 157+ total tests).

**Q: What if a function has complex dependencies?**  
A: Document the dependencies and migrate them first. Don't create circular imports.

---

**Ready to execute?** Start with Phase 1 (Remove Remaining Duplicates) and work through each phase sequentially.
