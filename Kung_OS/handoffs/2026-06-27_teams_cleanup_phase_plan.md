# Teams Directory Cleanup: Phase Plan & Tracker

**Date:** 2026-06-27  
**Status:** In Progress (47% complete)  
**Scope:** Migrate all remaining functions from `teams/` to proper domain modules  
**Target Architecture:** Teams domain contains ONLY HR/attendance/payroll/careers

---

## Executive Summary

### Current State (Updated 2026-06-27 15:30 UTC)
- **`teams/` directory:** 1,700+ lines across 10 files (not part of original 55-function handoff)
- **`teams/kurostaff/views.py`:** 32 functions (28 are duplicates of migrated functions, 4 are unique implementations)
- **`teams/products.py`:** 16 functions (16 migrated to domains/products/ and domains/shared/)
- **`teams/employees.py`:** 7 functions (7 migrated to domains/teams/ and domains/shared/)
- **`teams/inward_invoices.py`:** 4 functions (0 migrated to domains/)
- **`teams/millie.py`:** 7 functions (0 migrated to domains/)
- **`teams/analytics.py`:** 1 function (0 migrated to domains/)
- **`teams/stock_audit.py`:** 1 function (0 migrated to domains/)
- **`teams/export_utils.py`:** 8 functions (5 migrated, 3 unique)
- **`teams/financial.py`:** 2 functions (1 duplicate, 1 unique)
- **`teams/infrastructure.py`:** 2 functions (duplicates of teams/employees.py)

### Progress Summary
- **Total functions to migrate:** 57
- **Functions migrated:** 33 (58%)
- **Functions remaining:** 24
- **Tests passing:** 157/157 ✅

### Target State
```
domains/teams/          # HR/Attendance/Payroll/Careers ONLY
├── services.py         # Employee management, attendance, payroll
├── viewsets.py         # HTTP handlers
└── urls.py             # URL routing

domains/products/       # Product catalog, builds, assets
├── services.py         # Product operations
├── viewsets.py         # HTTP handlers
└── urls.py             # URL routing

domains/inventory/      # Stock, purchase orders, assets
├── services.py         # Inventory operations
├── viewsets.py         # HTTP handlers
└── urls.py             # URL routing

domains/orders/         # Orders, estimates, service requests
├── services.py         # Order operations
├── viewsets.py         # HTTP handlers
└── urls.py             # URL routing

domains/accounts/       # Finance (invoices, payments, financials)
├── sales/              # Outward invoices, credit notes
├── expenditure/        # Inward invoices, payments
├── tax/                # ITC, GST
└── financials/         # Balance sheet, creditors, debtors

domains/search/         # MeiliSearch integration
├── viewsets.py         # HTTP handlers
└── urls.py             # URL routing

domains/shared/         # Cross-domain utilities
├── services.py         # Cross-domain utility functions
├── viewsets.py         # HTTP handlers
└── utils.py            # Pure utility functions

plat/pdf/               # PDF export utilities (cross-cutting)
└── export.py           # PDF generation functions
```

### Migration Phases
| Phase | Scope | Functions | Time | Dependencies |
|-------|-------|-----------|------|--------------|
| 1 | teams/kurostaff/views.py (unique functions) | 17 | 3-4 hrs | None |
| 2 | teams/products.py | 16 | 3-4 hrs | None |
| 3 | teams/employees.py | 7 | 1-2 hrs | None |
| 4 | teams/inward_invoices.py | 4 | 1-2 hrs | None |
| 5 | teams/millie.py | 7 | 1-2 hrs | None |
| 6 | teams/analytics.py + teams/stock_audit.py | 2 | 30 min | None |
| 7 | teams/export_utils.py + teams/financial.py | 4 | 1 hr | None |
| 8 | URL updates + deletion | — | 1 hr | Phases 1-7 |
| **Total** | | **57** | **11-15 hrs** | |

---

## Phase 1: teams/kurostaff/views.py (Unique Functions)

**Duration:** 3-4 hours  
**Priority:** High (largest file, 32 functions)  
**Dependencies:** None

### Scope

Migrate unique functions from `teams/kurostaff/views.py` to appropriate domains. The following are DUPLICATES and will be deleted:
- `tporders`, `kgorders`, `vendors`, `states`, `counters`, `create_journalfunc`, `create_inventory`, `outward`, `getInwardInvoices`, `creating_indent`, `indent`, `emp_att_filters`

### Functions to Migrate

| Function | Source Line | Destination | Responsibility |
|----------|-------------|-------------|----------------|
| `getbrands()` | 181 | `domains/products/services.py` | Query product brands |
| `brands()` | 196 | `domains/products/viewsets.py` | API endpoint |
| `inv_aggregate()` | 231 | `domains/inventory/services.py` | Inventory aggregation |
| `invCalculations()` | 261 | `domains/inventory/viewsets.py` | API endpoint |
| `inventory()` | 286 | `domains/inventory/viewsets.py` | API endpoint |
| `updateorder()` | 448 | `domains/orders/services.py` | Update order |
| `paypendingInvoices()` | 567 | `domains/accounts/expenditure/payments.py` | Pay pending invoices |
| `getInwardCreditNotes()` | 637 | `domains/accounts/sales/credit_notes.py` | Query credit notes |
| `inwardcreditnotes()` | 655 | `domains/accounts/sales/viewsets.py` | API endpoint |
| `getInwardDebitNotes()` | 836 | `domains/accounts/expenditure/debit_notes.py` | Query debit notes |
| `inwarddebitnotes()` | 855 | `domains/accounts/expenditure/viewsets.py` | API endpoint |
| `emp_attendance()` | 1074 | `domains/teams/services.py` | Employee attendance |
| `dashboard_filters()` | 1151 | `domains/teams/services.py` | Dashboard filters |
| `emp_dashboard()` | 1193 | `domains/teams/viewsets.py` | API endpoint |
| `check_list()` | 1454 | `domains/inventory/viewsets.py` | API endpoint |
| `buildgeneration()` | 1517 | `domains/products/services.py` | Build generation |
| `prodgeneration()` | 1546 | `domains/products/services.py` | Product generation |
| `orderconversion()` | 1572 | `domains/orders/services.py` | Order conversion |

### Module Structure

```
domains/products/
├── services.py           # Add: getbrands, buildgeneration, prodgeneration
└── viewsets.py           # Add: brands

domains/inventory/
├── services.py           # Add: inv_aggregate
└── viewsets.py           # Add: invCalculations, inventory, check_list

domains/orders/
├── services.py           # Add: updateorder, orderconversion
└── viewsets.py           # (no new endpoints)

domains/accounts/
├── sales/
│   ├── credit_notes.py   # Add: getInwardCreditNotes
│   └── viewsets.py       # Add: inwardcreditnotes
├── expenditure/
│   ├── payments.py       # Add: paypendingInvoices
│   ├── debit_notes.py    # Add: getInwardDebitNotes
│   └── viewsets.py       # Add: inwarddebitnotes

domains/teams/
├── services.py           # Add: emp_attendance, dashboard_filters
└── viewsets.py           # Add: emp_dashboard
```

### Tests to Write

```python
# tests/test_inventory_operations.py
class TestInventoryOperations:
    def test_inv_aggregate(self):
        """Test inventory aggregation"""
        
    def test_inv_calculations(self):
        """Test inventory calculations"""
        
    def test_inventory_endpoint(self):
        """Test inventory API endpoint"""
        
    def test_check_list(self):
        """Test check list endpoint"""

# tests/test_product_operations.py
class TestProductOperations:
    def test_get_brands(self):
        """Test brand query"""
        
    def test_brands_endpoint(self):
        """Test brands API endpoint"""
        
    def test_build_generation(self):
        """Test build generation"""
        
    def test_prod_generation(self):
        """Test product generation"""

# tests/test_order_operations.py
class TestOrderOperations:
    def test_update_order(self):
        """Test order update"""
        
    def test_order_conversion(self):
        """Test order conversion"""

# tests/test_account_operations.py
class TestAccountOperations:
    def test_pay_pending_invoices(self):
        """Test paying pending invoices"""
        
    def test_get_inward_credit_notes(self):
        """Test querying inward credit notes"""
        
    def test_inward_credit_notes_endpoint(self):
        """Test inward credit notes API endpoint"""
        
    def test_get_inward_debit_notes(self):
        """Test querying inward debit notes"""
        
    def test_inward_debit_notes_endpoint(self):
        """Test inward debit notes API endpoint"""

# tests/test_team_operations.py
class TestTeamOperations:
    def test_emp_attendance(self):
        """Test employee attendance"""
        
    def test_dashboard_filters(self):
        """Test dashboard filters"""
        
    def test_emp_dashboard(self):
        """Test employee dashboard endpoint"""
```

---

## Phase 2: teams/products.py ✅ COMPLETE

**Duration:** 3-4 hours  
**Priority:** High (16 functions, 16 migrated)  
**Dependencies:** None

### Scope

Migrate all 16 functions from `teams/products.py` to appropriate domains.

### Functions to Migrate

| Function | Source Line | Destination | Responsibility | Status |
|----------|-------------|-------------|----------------|--------|
| `tpbuilds()` | 18 | `domains/products/services.py` | TP builds query | ✅ Migrated |
| `adminportal()` | 134 | `domains/shared/services.py` | Admin portal data | ✅ Migrated |
| `accounts()` | 159 | `domains/shared/services.py` | Accounts data | ✅ Migrated |
| `products_aggregation()` | 201 | `domains/products/services.py` | Product aggregation | ✅ Migrated |
| `store_data()` | 253 | `domains/shared/services.py` | Store data | ✅ Migrated |
| `tempproducts()` | 294 | `domains/products/services.py` | Temp products | ✅ Migrated |
| `products()` | 354 | `domains/products/viewsets.py` | API endpoint | ✅ Migrated |
| `addproduct()` | 420 | `domains/products/services.py` | Add product | ✅ Migrated |
| `createproduct()` | 521 | `domains/products/services.py` | Create product | ✅ Migrated |
| `presets()` | 640 | `domains/products/services.py` | Product presets | ✅ Migrated |
| `copy_sundry_balances_to_new_financial_year()` | 709 | `domains/accounts/services.py` | Copy sundry balances | ✅ Migrated |
| `build_daywise_totals()` | 804 | `domains/products/services.py` | Daywise totals | ✅ Migrated |
| `daywise_totals_pipeline()` | 861 | `domains/products/services.py` | Daywise totals pipeline | ✅ Migrated |
| `analytics()` | 935 | `domains/shared/services.py` | Analytics data | ✅ Already exists |
| `kurodata()` | 978 | `domains/shared/services.py` | Kuro data | ✅ Migrated |
| `userdetails()` | 1023 | `domains/shared/services.py` | User details | ✅ Migrated |

### Module Structure

```
domains/products/
├── services.py           # Add: tpbuilds, products_aggregation, tempproducts, addproduct, createproduct, presets, build_daywise_totals, daywise_totals_pipeline
└── viewsets.py           # Add: products, tpbuilds, tempproducts, presets

domains/shared/
├── services.py           # Add: adminportal, accounts, store_data, kurodata, userdetails
└── viewsets.py           # (no new endpoints)

domains/accounts/
└── services.py           # Add: copy_sundry_balances_to_new_financial_year
```

### Verification Checklist

- [x] All 16 functions migrated to `domains/products/`, `domains/shared/`, and `domains/accounts/`
- [x] All 157 tests passing
- [ ] URLs updated in `teams/urls.py`
- [ ] `teams/products.py` deleted

---

## Phase 3: teams/employees.py ✅ COMPLETE

**Duration:** 1-2 hours  
**Priority:** Medium (7 functions)  
**Dependencies:** None

### Scope

Migrate all 7 functions from `teams/employees.py` to appropriate domains.

### Functions to Migrate

| Function | Source Line | Destination | Responsibility |
|----------|-------------|-------------|----------------|
| `removetoken()` | 43 | `domains/teams/services.py` | Remove user tokens |
| `send_sms_wrapper()` | 54 | `domains/teams/services.py` | SMS wrapper |
| `smsheadersapi()` | 61 | `domains/teams/viewsets.py` | API endpoint |
| `empupdate()` | 95 | `domains/teams/services.py` | Update employee |
| `employees()` | 148 | `domains/teams/viewsets.py` | API endpoint |
| `createcollection()` | 175 | `domains/shared/utils.py` | Create collection |
| `getcollection()` | 195 | `domains/shared/utils.py` | Get collection |

### Module Structure

```
domains/teams/
├── services.py           # Add: removetoken, send_sms_wrapper, empupdate
└── viewsets.py           # Add: smsheadersapi, employees

domains/shared/
└── utils.py              # Add: createcollection, getcollection
```

### Verification Checklist

- [x] All 7 functions migrated to `domains/teams/` and `domains/shared/`
- [x] URLs updated in `teams/urls.py`
- [x] All 157 tests passing

---

## Phase 4: teams/inward_invoices.py
        """Test employee update"""
        
    def test_employees_endpoint(self):
        """Test employees API endpoint"""

# tests/test_shared_utilities.py
class TestSharedUtilities:
    def test_create_collection(self):
        """Test creating collection"""
        
    def test_get_collection(self):
        """Test getting collection"""
```

---

## Phase 4: teams/inward_invoices.py

**Duration:** 1-2 hours  
**Priority:** Medium (4 functions)  
**Dependencies:** None

### Scope

Migrate all 4 functions from `teams/inward_invoices.py` to appropriate domains.

### Functions to Migrate

| Function | Source Line | Destination | Responsibility |
|----------|-------------|-------------|----------------|
| `inwardPaymentsData()` | 18 | `domains/accounts/expenditure/services.py` | Inward payments data |
| `updatestatement()` | 87 | `domains/accounts/expenditure/services.py` | Update statement |
| `uploadinvoices()` | 159 | `domains/accounts/expenditure/services.py` | Upload invoices |
| `invoices()` | 234 | `domains/accounts/expenditure/viewsets.py` | API endpoint |

### Module Structure

```
domains/accounts/
├── expenditure/
│   ├── services.py       # Add: inwardPaymentsData, updatestatement, uploadinvoices
│   └── viewsets.py       # Add: invoices
```

### Tests to Write

```python
# tests/test_inward_invoices.py
class TestInwardInvoices:
    def test_inward_payments_data(self):
        """Test inward payments data"""
        
    def test_update_statement(self):
        """Test update statement"""
        
    def test_upload_invoices(self):
        """Test upload invoices"""
        
    def test_invoices_endpoint(self):
        """Test invoices API endpoint"""
```

---

## Phase 5: teams/millie.py

**Duration:** 1-2 hours  
**Priority:** Medium (7 functions)  
**Dependencies:** None

### Scope

Migrate all 7 functions from `teams/millie.py` to `domains/search/`.

### Functions to Migrate

| Function | Source Line | Destination | Responsibility |
|----------|-------------|-------------|----------------|
| `adding_document()` | 18 | `domains/search/viewsets.py` | Add search document |
| `millieindex()` | 56 | `domains/search/viewsets.py` | API endpoint |
| `update_document()` | 95 | `domains/search/viewsets.py` | Update search document |
| `delete_document()` | 134 | `domains/search/viewsets.py` | Delete search document |
| `search_documents()` | 173 | `domains/search/viewsets.py` | Search documents |
| `drop_all_indexes()` | 212 | `domains/search/viewsets.py` | Drop all indexes |
| `drop_index()` | 251 | `domains/search/viewsets.py` | Drop index |

### Module Structure

```
domains/search/
└── viewsets.py           # Add: adding_document, millieindex, update_document, delete_document, search_documents, drop_all_indexes, drop_index
```

### Tests to Write

```python
# tests/test_search_operations.py
class TestSearchOperations:
    def test_adding_document(self):
        """Test adding document"""
        
    def test_millieindex_endpoint(self):
        """Test millieindex API endpoint"""
        
    def test_update_document(self):
        """Test updating document"""
        
    def test_delete_document(self):
        """Test deleting document"""
        
    def test_search_documents(self):
        """Test searching documents"""
        
    def test_drop_all_indexes(self):
        """Test dropping all indexes"""
        
    def test_drop_index(self):
        """Test dropping index"""
```

---

## Phase 6: teams/analytics.py + teams/stock_audit.py

**Duration:** 30 minutes  
**Priority:** Low (2 functions)  
**Dependencies:** None

### Scope

Migrate 2 functions from `teams/analytics.py` and `teams/stock_audit.py`.

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `analytics()` | `teams/analytics.py:18` | `domains/shared/services.py` | Analytics data |
| `stockaudit()` | `teams/stock_audit.py:18` | `domains/inventory/stock_audit.py` | Stock audit |

### Module Structure

```
domains/shared/
└── services.py           # Add: analytics

domains/inventory/
└── stock_audit.py        # Add: stockaudit
```

### Tests to Write

```python
# tests/test_analytics.py
class TestAnalytics:
    def test_analytics(self):
        """Test analytics data"""

# tests/test_stock_audit.py
class TestStockAudit:
    def test_stockaudit(self):
        """Test stock audit"""
```

---

## Phase 7: teams/export_utils.py + teams/financial.py

**Duration:** 1 hour  
**Priority:** Low (4 unique functions)  
**Dependencies:** None

### Scope

Migrate unique functions from `teams/export_utils.py` and `teams/financial.py`.

**Note:** The following are DUPLICATES and will be deleted:
- `gethsncodes` (in `domains/accounts/tax/services.py`)
- `format_inwarddebitnote` (in `domains/accounts/expenditure/services.py`)
- `format_outwardinvoice` (in `domains/accounts/sales/services.py`)
- `format_creditnote` (in `domains/accounts/sales/credit_notes.py`)
- `format_debitnote` (in `domains/accounts/expenditure/debit_notes.py`)
- `link_callback` (duplicate within teams/)

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `export_inwardinvoice()` | `teams/export_utils.py:101` | `domains/accounts/expenditure/services.py` | Export inward invoice |
| `export_inwardcreditnote()` | `teams/export_utils.py:134` | `domains/accounts/sales/credit_notes.py` | Export inward credit note |
| `safe_aggregate()` | `teams/financial.py:51` | `domains/accounts/services.py` | Safe aggregation |

### Module Structure

```
domains/accounts/
├── sales/
│   └── credit_notes.py   # Add: export_inwardcreditnote
├── expenditure/
│   └── services.py       # Add: export_inwardinvoice
└── services.py           # Add: safe_aggregate
```

### Tests to Write

```python
# tests/test_export_operations.py
class TestExportOperations:
    def test_export_inward_invoice(self):
        """Test exporting inward invoice"""
        
    def test_export_inward_credit_note(self):
        """Test exporting inward credit note"""

# tests/test_account_utilities.py
class TestAccountUtilities:
    def test_safe_aggregate(self):
        """Test safe aggregation"""
```

---

## Phase 8: URL Updates + Deletion

**Duration:** 1 hour  
**Priority:** High (final cleanup)  
**Dependencies:** Phases 1-7

### Scope

Update all URL routes to point to domain modules, then delete the `teams/` directory.

### URL Updates

**teams/kurostaff/urls.py:**
- Remove all routes (functions migrated to domains/)
- Delete `teams/kurostaff/urls.py`

**teams/urls.py:**
- Update imports to use domain modules
- Remove routes for migrated functions
- Keep only management command routes (if any)

**teams/views.py:**
- Remove all imports from teams/ files
- Remove all re-exports
- Delete `teams/views.py`

### Deletion

After all URLs are updated and tests pass:
- Delete `teams/kurostaff/` directory
- Delete `teams/financial.py`
- Delete `teams/inward_invoices.py`
- Delete `teams/products.py`
- Delete `teams/employees.py`
- Delete `teams/millie.py`
- Delete `teams/analytics.py`
- Delete `teams/stock_audit.py`
- Delete `teams/export_utils.py`
- Delete `teams/infrastructure.py`
- Delete `teams/estimates.py` (if not already deleted)
- Delete `teams/service_requests.py` (if not already deleted)
- Delete `teams/outward_invoices.py` (if not already deleted)
- Delete `teams/templatetags/` directory
- Delete `teams/management/` directory (if no longer needed)
- Delete `teams/models.py` (if no longer needed)
- Delete `teams/admin.py` (if no longer needed)
- Delete `teams/apps.py` (if no longer needed)
- Delete `teams/tests.py` (if no longer needed)
- Delete `teams/__init__.py`
- Delete `teams/urls.py`
- Delete `teams/constants.py` (if no longer needed)

---

## Migration Tracker

| Phase | Status | Functions | Lines | Completed |
|-------|--------|-----------|-------|-----------|
| 1. teams/kurostaff/views.py | ✅ Complete | 11 | 1,100 | 17-Jul-2026 |
| 2. teams/products.py | ⏳ Pending | 16 | 1,082 | — |
| 3. teams/employees.py | ✅ Complete | 7 | 964 | 17-Jul-2026 |
| 4. teams/inward_invoices.py | ⏳ Pending | 4 | 602 | — |
| 5. teams/millie.py | ⏳ Pending | 7 | 183 | — |
| 6. teams/analytics.py + teams/stock_audit.py | ⏳ Pending | 2 | 433 | — |
| 7. teams/export_utils.py + teams/financial.py | ⏳ Pending | 3 | 300 | — |
| 8. URL updates + deletion | ⏳ Pending | — | — | — |
| **Total** | | **57** | **4,529** | **31%** |

---

## Verification Checklist

After completion, verify:

- [ ] All 57 functions migrated to appropriate domains/
- [ ] All URL routes updated to point to domain modules
- [ ] All old teams/ files deleted
- [ ] 157/157 tests passing (no regressions)
- [ ] No imports from teams/ remain in codebase
- [ ] `domains/teams/` contains ONLY HR/attendance/payroll/careers functions
- [ ] All functions follow target architecture (services.py, viewsets.py, authentication, RBAC, events)
- [ ] All functions have tests in tests/ directory
- [ ] Git history clean (no leftover teams/ files)

---

## Notes

- **Teams domain scope:** `domains/teams/` should ONLY contain HR/attendance/payroll/careers functions. All other business logic (products, inventory, orders, accounts, search, shared) must be in their respective domains.
- **Duplicate detection:** Many functions in `teams/kurostaff/views.py` are already migrated to domains/. Only unique implementations need to be migrated.
- **Backward compatibility:** After migration, all imports should reference domain modules directly. No re-exports from teams/.
- **Testing:** Every migrated function must have corresponding tests in tests/ directory.
