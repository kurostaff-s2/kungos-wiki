# Domain Migration: Phase-Wise Task Handoff

**Date:** 2026-06-27  
**Status:** Ready for Execution  
**Scope:** Migrate 55 functions from `teams/` to proper domain modules  
**Total Estimated Time:** 16-22 hours

---

## Executive Summary

### Current State
- **4,215 lines** scattered across `teams/financial.py`, `teams/inward_invoices.py`, `teams/outward_invoices.py`, `teams/estimates.py`
- **56 functions** with mixed business logic (sales, expenditure, tax, financials, inventory)
- No clear domain boundaries

### Target State
```
domains/accounts/
├── sales/              # Outward invoices, credit notes, sales reports
├── expenditure/        # Inward invoices, payments, purchase reports
├── tax/                # ITC, GST management
├── financials/         # Balance sheet, creditors, debtors
└── shared/             # Common utilities

domains/inventory/      # NEW: Stock, purchase orders, assets
├── stock_register.py
├── stock_audit.py
├── purchase_orders.py
└── assets.py

domains/orders/         # Estimates (already partially migrated)
└── estimates/
```

### Migration Phases
| Phase | Scope | Functions | Time | Dependencies |
|-------|-------|-----------|------|--------------|
| 1 | Accounts: Sales | 10 | 2-3 hrs | None (start here) |
| 2 | Accounts: Expenditure | 18 | 4-5 hrs | Phase 1 |
| 3 | Accounts: Tax | 5 | 1-2 hrs | Phase 2 |
| 4 | Accounts: Financials | 9 | 2-3 hrs | Phase 2 |
| 5 | Orders: Estimates | 1 | 30 min | None |
| 6 | Inventory: Foundation | 5 | 2-3 hrs | Phase 2 |
| 7 | Inventory: Purchase Orders | 3 | 1-2 hrs | Phase 6 |
| 8 | Inventory: Assets & Indents | 4 | 1-2 hrs | Phase 6 |
| 9 | Cleanup | — | 2 hrs | Phases 1-8 |
| **Total** | | **55** | **16-22 hrs** | |

---

## Phase 1: Accounts — Sales Module

**Duration:** 2-3 hours  
**Priority:** High (cleanest boundaries, highest business value)  
**Dependencies:** None

### Scope

Create `domains/accounts/sales/` with outward invoice operations, credit notes, and sales reports.

### Module Structure

```
domains/accounts/sales/
├── __init__.py
├── services.py           # Outward invoice operations
├── credit_notes.py       # Credit note operations
├── reports.py            # Sales reports
└── viewsets.py           # HTTP handlers
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `getOutwardInvoices()` | `teams/outward_invoices.py:58` | `services.py` | Query outward invoices |
| `outwardinvoices()` | `teams/outward_invoices.py:78` | `viewsets.py` | API endpoint |
| `getOutwardCreditNotes()` | `teams/outward_invoices.py:335` | `credit_notes.py` | Query credit notes |
| `outwardcreditnotes()` | `teams/outward_invoices.py:353` | `viewsets.py` | API endpoint |
| `format_outwardinvoice()` | `teams/inward_invoices.py:1126` | `services.py` | Format for PDF export |
| `format_creditnote()` | `teams/inward_invoices.py:1177` | `credit_notes.py` | Format for PDF export |
| `sales_func()` | `teams/financial.py:740` | `reports.py` | Sales data aggregation |
| `sales()` | `teams/financial.py:817` | `viewsets.py` | API endpoint |
| `outwardentry()` | `domains/accounts/services.py:159` | `services.py` | Outward entry processing |
| `outward()` | `domains/accounts/services.py:234` | `viewsets.py` | API endpoint |

### Tests to Write

```python
# tests/test_accounts_sales.py

class TestOutwardInvoices:
    def test_get_outward_invoices_query(self):
        """Test outward invoice query with filters"""
        
    def test_outwardinvoices_api_endpoint(self):
        """Test outward invoices API endpoint"""
        
    def test_format_outwardinvoice(self):
        """Test outward invoice formatting for PDF"""

class TestCreditNotes:
    def test_get_outward_credit_notes_query(self):
        """Test credit note query"""
        
    def test_outwardcreditnotes_api_endpoint(self):
        """Test credit notes API endpoint"""
        
    def test_format_creditnote(self):
        """Test credit note formatting"""

class TestSalesReports:
    def test_sales_func_aggregation(self):
        """Test sales data aggregation"""
        
    def test_sales_api_endpoint(self):
        """Test sales API endpoint"""

class TestOutwardEntries:
    def test_outwardentry_processing(self):
        """Test outward entry processing"""
        
    def test_outward_api_endpoint(self):
        """Test outward API endpoint"""
```

### Acceptance Criteria

- [ ] All 10 functions migrated to `domains/accounts/sales/`
- [ ] Unit tests pass for each function
- [ ] API endpoints return correct responses
- [ ] No references to old `teams/outward_invoices.py` or `teams/financial.py` for sales functions
- [ ] PDF formatting functions use `plat.pdf.export.exporttopdf`

### Cross-Domain Dependencies

- **Reads:** `domains/vendors/` (vendor lookup for outward invoices)
- **Reads:** `domains/products/` (product lookup for outward invoices)
- **Writes:** `outwardinvoices` collection (MongoDB)
- **Writes:** `outwardcreditnotes` collection (MongoDB)
- **Writes:** `outward` collection (MongoDB)

### Implementation Steps

1. **RED:** Create test file `tests/test_accounts_sales.py` with failing tests
2. **GREEN:** Migrate functions to `domains/accounts/sales/`
   - Create module structure (`__init__.py`, `services.py`, `credit_notes.py`, `reports.py`, `viewsets.py`)
   - Migrate `getOutwardInvoices()`, `outwardinvoices()` to `services.py`/`viewsets.py`
   - Migrate `getOutwardCreditNotes()`, `outwardcreditnotes()` to `credit_notes.py`/`viewsets.py`
   - Migrate `format_outwardinvoice()` to `services.py`
   - Migrate `format_creditnote()` to `credit_notes.py`
   - Migrate `sales_func()`, `sales()` to `reports.py`/`viewsets.py`
   - Migrate `outwardentry()`, `outward()` from `domains/accounts/services.py`
3. **REFACTOR:** Update imports in callers
   - Update `teams/views.py` to import from `domains/accounts/sales/`
   - Remove duplicate functions from `teams/outward_invoices.py`
   - Remove duplicate functions from `teams/financial.py`
4. **VERIFY:** Run full test suite

---

## Phase 2: Accounts — Expenditure Module

**Duration:** 4-5 hours  
**Priority:** High (largest module, most functions)  
**Dependencies:** Phase 1 (for shared utilities)

### Scope

Create `domains/accounts/expenditure/` with inward invoice operations, payment processing, and purchase reports.

### Module Structure

```
domains/accounts/expenditure/
├── __init__.py
├── services.py           # Inward invoice operations
├── debit_notes.py        # Debit note operations
├── payments.py           # Payment vouchers, bulk payments
├── purchase_orders.py    # Purchase order operations
├── reports.py            # Purchase reports
└── viewsets.py           # HTTP handlers
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `getInwardInvoices()` | `teams/inward_invoices.py:135` | `services.py` | Query inward invoices |
| `inwardinvoices()` | `teams/inward_invoices.py:62` | `viewsets.py` | API endpoint |
| `getpurchaseorders()` | `teams/financial.py:51` | `purchase_orders.py` | Query purchase orders |
| `purchaseorders()` | `teams/financial.py:68` | `viewsets.py` | API endpoint |
| `getpaymentvouchers()` | `teams/financial.py:206` | `payments.py` | Query payment vouchers |
| `paymentvouchers()` | `teams/financial.py:223` | `viewsets.py` | API endpoint |
| `bulk_payments()` | `teams/financial.py:924` | `payments.py` | Bulk payment processing |
| `settlements()` | `teams/financial.py:1368` | `payments.py` | Settlements |
| `payment()` | `teams/financial.py:1437` | `payments.py` | Payment processing |
| `inwardpayments()` | `teams/inward_invoices.py:869` | `payments.py` | Inward payments |
| `exportinwardpayments()` | `teams/inward_invoices.py:447` | `payments.py` | Export inward payments |
| `format_inwardinvoice()` | `teams/inward_invoices.py:980` | `services.py` | Format for PDF export |
| `format_inwardcreditnote()` | `teams/inward_invoices.py:995` | `services.py` | Format for PDF export |
| `format_inwarddebitnote()` | `teams/inward_invoices.py:1008` | `debit_notes.py` | Format for PDF export |
| `format_debitnote()` | `teams/inward_invoices.py:1205` | `debit_notes.py` | Format for PDF export |
| `purchases_func()` | `teams/inward_invoices.py:314` | `reports.py` | Purchases data aggregation |
| `purchases()` | `teams/inward_invoices.py:392` | `viewsets.py` | API endpoint |
| `getOutwardDebitNotes()` | `teams/outward_invoices.py:494` | `debit_notes.py` | Query debit notes |
| `outwarddebitnotes()` | `teams/outward_invoices.py:515` | `viewsets.py` | API endpoint |

### Tests to Write

```python
# tests/test_accounts_expenditure.py

class TestInwardInvoices:
    def test_get_inward_invoices_query(self):
        """Test inward invoice query"""
        
    def test_inwardinvoices_api_endpoint(self):
        """Test inward invoices API endpoint"""
        
    def test_format_inwardinvoice(self):
        """Test inward invoice formatting"""

class TestPurchaseOrders:
    def test_getpurchaseorders_query(self):
        """Test purchase order query"""
        
    def test_purchaseorders_api_endpoint(self):
        """Test purchase orders API endpoint"""

class TestPayments:
    def test_getpaymentvouchers_query(self):
        """Test payment voucher query"""
        
    def test_paymentvouchers_api_endpoint(self):
        """Test payment vouchers API endpoint"""
        
    def test_bulk_payments(self):
        """Test bulk payment processing"""
        
    def test_settlements(self):
        """Test settlements"""
        
    def test_payment(self):
        """Test payment processing"""
        
    def test_inwardpayments(self):
        """Test inward payments"""

class TestDebitNotes:
    def test_get_outward_debit_notes_query(self):
        """Test debit note query"""
        
    def test_outwarddebitnotes_api_endpoint(self):
        """Test debit notes API endpoint"""
        
    def test_format_debitnote(self):
        """Test debit note formatting"""

class TestPurchaseReports:
    def test_purchases_func_aggregation(self):
        """Test purchases data aggregation"""
        
    def test_purchases_api_endpoint(self):
        """Test purchases API endpoint"""
```

### Acceptance Criteria

- [ ] All 18 functions migrated to `domains/accounts/expenditure/`
- [ ] Unit tests pass for each function
- [ ] API endpoints return correct responses
- [ ] No references to old `teams/inward_invoices.py` or `teams/financial.py` for expenditure functions
- [ ] Payment functions coordinate with `domains/inventory/purchase_orders.py` (Phase 6)

### Cross-Domain Dependencies

- **Reads:** `domains/vendors/` (vendor lookup for inward invoices)
- **Reads:** `domains/inventory/purchase_orders.py` (purchase order details)
- **Writes:** `inwardinvoices` collection (MongoDB)
- **Writes:** `purchaseorders` collection (MongoDB)
- **Writes:** `paymentvouchers` collection (MongoDB)
- **Writes:** `settlements` collection (MongoDB)
- **Writes:** `payments` collection (MongoDB)

### Implementation Steps

1. **RED:** Create test file `tests/test_accounts_expenditure.py` with failing tests
2. **GREEN:** Migrate functions to `domains/accounts/expenditure/`
   - Create module structure
   - Migrate inward invoice functions
   - Migrate purchase order functions
   - Migrate payment functions
   - Migrate debit note functions
   - Migrate purchase report functions
3. **REFACTOR:** Update imports in callers
4. **VERIFY:** Run full test suite

---

## Phase 3: Accounts — Tax Module

**Duration:** 1-2 hours  
**Priority:** Medium  
**Dependencies:** Phase 2

### Scope

Create `domains/accounts/tax/` with ITC, GST calculations and reporting.

### Module Structure

```
domains/accounts/tax/
├── __init__.py
├── services.py           # Tax calculation utilities
├── itc.py                # Input Tax Credit
├── gst.py                # GST reporting
└── viewsets.py           # HTTP handlers
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `itc_gst()` | `teams/financial.py:1768` | `viewsets.py` | ITC/GST report |
| `indent_aggregate()` | `teams/financial.py:1048` | `itc.py` | Indent aggregation |
| `indent()` | `teams/financial.py:1119` | `viewsets.py` | Indent API endpoint |
| (New) `itc_calculate()` | — | `itc.py` | ITC calculation logic |
| (New) `gst_return()` | — | `gst.py` | GST return generation |

### Tests to Write

```python
# tests/test_accounts_tax.py

class TestITC:
    def test_itc_calculate(self):
        """Test ITC calculation"""
        
    def test_indent_aggregate(self):
        """Test indent aggregation"""

class TestGST:
    def test_gst_return(self):
        """Test GST return generation"""
        
    def test_itc_gst_api_endpoint(self):
        """Test ITC/GST report API"""
```

### Acceptance Criteria

- [ ] All 5 functions migrated to `domains/accounts/tax/`
- [ ] Unit tests pass
- [ ] ITC calculations match existing behavior
- [ ] GST report API returns correct data

### Cross-Domain Dependencies

- **Reads:** `inwardinvoices` collection (for ITC)
- **Reads:** `outwardinvoices` collection (for GST)
- **Reads:** `purchaseorders` collection (for ITC)

---

## Phase 4: Accounts — Financials Module

**Duration:** 2-3 hours  
**Priority:** Medium  
**Dependencies:** Phase 2

### Scope

Create `domains/accounts/financials/` with balance sheet, creditors, debtors, and financial reports.

### Module Structure

```
domains/accounts/financials/
├── __init__.py
├── services.py           # Financial calculation utilities
├── balance_sheet.py      # Balance sheet calculations
├── creditors.py          # Creditors (outstanding payables)
├── debtors.py            # Debtors (outstanding receivables)
├── reports.py            # Financial reports
└── viewsets.py           # HTTP handlers
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `financial_totals()` | `teams/financial.py:1473` | `reports.py` | Financial totals |
| `payment_financials()` | `teams/financial.py:1530` | `reports.py` | Payment financials |
| `past_present_fin_totals()` | `teams/financial.py:1588` | `reports.py` | Historical totals |
| `financials()` | `teams/financial.py:1650` | `viewsets.py` | Financial summary |
| `update_inward_data()` | `teams/financial.py:1638` | `services.py` | Update inward data |
| (New) `balance_sheet()` | — | `balance_sheet.py` | Balance sheet calculation |
| (New) `creditors_list()` | — | `creditors.py` | Creditors list |
| (New) `debtors_list()` | — | `debtors.py` | Debtors list |

### Tests to Write

```python
# tests/test_accounts_financials.py

class TestFinancialTotals:
    def test_financial_totals(self):
        """Test financial totals calculation"""
        
    def test_payment_financials(self):
        """Test payment financials"""

class TestBalanceSheet:
    def test_balance_sheet(self):
        """Test balance sheet calculation"""
        
    def test_creditors_list(self):
        """Test creditors list"""
        
    def test_debtors_list(self):
        """Test debtors list"""

class TestFinancialReports:
    def test_financials_api_endpoint(self):
        """Test financial summary API"""
```

### Acceptance Criteria

- [ ] All 8 functions migrated to `domains/accounts/financials/`
- [ ] Unit tests pass
- [ ] Financial totals match existing behavior
- [ ] Balance sheet, creditors, debtors calculations are correct

### Cross-Domain Dependencies

- **Reads:** All financial collections (aggregation across collections)
- **Reads:** `inwardinvoices`, `outwardinvoices`, `purchaseorders`, `paymentvouchers`

---

## Phase 5: Orders — Estimates

**Duration:** 30 minutes  
**Priority:** Low (quick win)  
**Dependencies:** None

### Scope

Move estimates HTTP handler from `teams/estimates.py` to `domains/orders/`.

### Module Structure

```
domains/orders/estimates/
├── __init__.py
└── viewsets.py           # HTTP handlers (business logic already in domains/orders/services.py)
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `estimates()` | `teams/estimates.py:97` | `viewsets.py` | API endpoint |

**Note:** `getEstimates()` business logic already exists in `domains/orders/services.py:43`

### Tests to Write

```python
# tests/test_orders_estimates.py

class TestEstimates:
    def test_estimates_api_endpoint(self):
        """Test estimates API endpoint"""
```

### Acceptance Criteria

- [ ] `estimates()` function migrated to `domains/orders/estimates/viewsets.py`
- [ ] Unit test passes
- [ ] API endpoint returns correct responses
- [ ] Old `teams/estimates.py` no longer used

---

## Phase 6: Inventory — Stock Operations (Foundation)

**Duration:** 2-3 hours  
**Priority:** High (foundation for inventory domain)  
**Dependencies:** Phase 2

### Scope

Create `domains/inventory/` with stock register and stock audit operations.

### Module Structure

```
domains/inventory/
├── __init__.py
├── services.py           # Core stock operations
├── stock_register.py     # Stock register operations
├── stock_audit.py        # Stock audit trail
├── viewsets.py           # HTTP handlers
└── urls.py               # URL routing
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `stockaudit()` | `teams/stock_audit.py:50` | `stock_audit.py` | Stock audit API |
| (New) `stock_register_ops()` | `teams/kurostaff/views.py` | `stock_register.py` | Stock register operations |
| (New) `stock_movements()` | `teams/kurostaff/views.py` | `stock_register.py` | Inward/outward stock movements |
| (New) `stock_transfer()` | — | `stock_register.py` | Stock transfers between locations |
| (New) `stock_adjustment()` | — | `stock_register.py` | Stock adjustments |

### Tests to Write

```python
# tests/test_inventory_stock.py

class TestStockRegister:
    def test_stock_register_ops(self):
        """Test stock register operations"""
        
    def test_stock_movements(self):
        """Test stock movements (inward/outward)"""
        
    def test_stock_transfer(self):
        """Test stock transfers"""
        
    def test_stock_adjustment(self):
        """Test stock adjustments"""

class TestStockAudit:
    def test_stockaudit_api_endpoint(self):
        """Test stock audit API endpoint"""
```

### Acceptance Criteria

- [ ] All 5 functions migrated to `domains/inventory/`
- [ ] Unit tests pass
- [ ] Stock register operations work correctly
- [ ] Stock audit trail is maintained
- [ ] `stock_audit.py` created in `domains/inventory/`

### Cross-Domain Dependencies

- **Writes:** `stock_register` collection (MongoDB)
- **Writes:** `stock_audit` collection (MongoDB)
- **Emits:** `plat/events/` (stock_updated event for orders domain)

---

## Phase 7: Inventory — Purchase Orders

**Duration:** 1-2 hours  
**Priority:** Medium  
**Dependencies:** Phase 6

### Scope

Move purchase order management from `teams/financial.py` to `domains/inventory/`.

### Module Structure

```
domains/inventory/purchase_orders.py
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| `getpurchaseorders()` | `teams/financial.py:51` | `purchase_orders.py` | Query purchase orders (inventory view) |
| (New) `create_purchase_order()` | — | `purchase_orders.py` | Create purchase order |
| (New) `update_purchase_order()` | — | `purchase_orders.py` | Update purchase order |

### Tests to Write

```python
# tests/test_inventory_purchase_orders.py

class TestPurchaseOrders:
    def test_get_purchase_orders_query(self):
        """Test purchase order query"""
        
    def test_create_purchase_order(self):
        """Test purchase order creation"""
        
    def test_update_purchase_order(self):
        """Test purchase order update"""
```

### Acceptance Criteria

- [ ] Purchase order functions migrated to `domains/inventory/purchase_orders.py`
- [ ] Unit tests pass
- [ ] Purchase orders can be created and updated
- [ ] `accounts/expenditure/payments.py` imports from `inventory/purchase_orders.py`

### Cross-Domain Dependencies

- **Reads:** `vendors/` (vendor lookup)
- **Reads:** `products/` (product lookup)
- **Writes:** `purchaseorders` collection (MongoDB)
- **Used by:** `accounts/expenditure/payments.py` (financial processing)

---

## Phase 8: Inventory — Assets & Indents

**Duration:** 1-2 hours  
**Priority:** Low  
**Dependencies:** Phase 6

### Scope

Create asset tracking and indent management in `domains/inventory/`.

### Module Structure

```
domains/inventory/
├── assets.py             # Fixed assets
└── indents.py            # Indent management
```

### Functions to Migrate

| Function | Source | Destination | Responsibility |
|----------|--------|-------------|----------------|
| (New) `asset_tracking()` | — | `assets.py` | Fixed assets |
| (New) `asset_creation()` | — | `assets.py` | Create asset |
| (New) `indent_management()` | — | `indents.py` | Indent requests |
| (New) `indent_approval()` | — | `indents.py` | Approve/reject indents |

### Tests to Write

```python
# tests/test_inventory_assets_indents.py

class TestAssets:
    def test_asset_tracking(self):
        """Test asset tracking"""
        
    def test_asset_creation(self):
        """Test asset creation"""

class TestIndents:
    def test_indent_management(self):
        """Test indent management"""
        
    def test_indent_approval(self):
        """Test indent approval"""
```

### Acceptance Criteria

- [ ] All 4 functions created and tested
- [ ] Asset tracking works correctly
- [ ] Indent management works correctly

---

## Phase 9: Cleanup

**Duration:** 2 hours  
**Priority:** High  
**Dependencies:** Phases 1-8

### Scope

Remove stale code from `teams/` and update URL routing.

### Tasks

1. **Remove duplicate functions from `teams/` files:**
   - `teams/financial.py` — Remove all migrated functions
   - `teams/inward_invoices.py` — Remove all migrated functions
   - `teams/outward_invoices.py` — Remove all migrated functions
   - `teams/estimates.py` — Remove `estimates()` function
   - `teams/stock_audit.py` — Remove `stockaudit()` function
   - `teams/kurostaff/views.py` — Remove stock-related functions

2. **Update URL routing:**
   - Create URL patterns in each domain module
   - Update root URL conf to include domain URLs
   - Remove old URL patterns from `teams/urls.py`

3. **Update import statements:**
   - Verify all imports point to new domain modules
   - Remove imports from `teams/` for migrated functions

4. **Run full test suite:**
   - `python3 manage.py test tests/`
   - Verify all 70+ tests pass

### Acceptance Criteria

- [ ] No duplicate functions in `teams/`
- [ ] All imports point to domain modules
- [ ] URL routing works correctly
- [ ] Full test suite passes

---

## Execution Guidelines

### TDD Discipline

Each phase follows RED→GREEN→REFACTOR:

1. **RED:** Write failing tests for the functions to be migrated
2. **GREEN:** Migrate functions to new domain modules, make tests pass
3. **REFACTOR:** Update imports, remove duplicates, optimize

### Chair Gate Validation

After each phase, run chair gate:

```bash
chair_gate \
  --task_id "domain-migration-phase-X" \
  --phase "GREEN" \
  --subagent_log "<log>" \
  --worktree_path "/home/chief/Coding-Projects/kteam-dj-chief" \
  --test_command "python3 manage.py test tests/ -v 2" \
  --expected_outcome "PASS"
```

### Parallel Execution

Phases with no dependencies can run in parallel:
- Phase 1 (Sales) and Phase 5 (Estimates) can run in parallel
- Phase 6 (Inventory Foundation) can start after Phase 2

### Rollback Plan

If a phase fails:
1. Revert git changes: `git revert HEAD`
2. Restore old `teams/` files from git
3. Investigate failure and retry

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Functions migrated | 55 |
| Lines of code organized | ~5,000 |
| Test coverage | >80% for migrated functions |
| Test suite pass rate | 100% |
| Zero breaking changes | Yes |

---

## Quick Reference

### Domain Module Paths

```
domains/accounts/sales/
domains/accounts/expenditure/
domains/accounts/tax/
domains/accounts/financials/
domains/accounts/shared/
domains/inventory/
domains/orders/estimates/
```

### Key Imports

```python
# From domains
from domains.accounts.sales.services import getOutwardInvoices
from domains.accounts.expenditure.payments import bulk_payments
from domains.accounts.tax.itc import itc_calculate
from domains.accounts.financials.balance_sheet import balance_sheet
from domains.inventory.stock_register import stock_movements
from domains.inventory.purchase_orders import getpurchaseorders
from domains.orders.services import getEstimates

# From platform
from plat.pdf.export import exporttopdf, fetch_resources
from plat.shared.helpers import num2words
from plat.events.bus import emit
```

### Collections Used

| Domain | Collections |
|--------|-------------|
| Sales | `outwardinvoices`, `outwardcreditnotes`, `outward` |
| Expenditure | `inwardinvoices`, `purchaseorders`, `paymentvouchers`, `settlements`, `payments` |
| Tax | `inwardinvoices`, `outwardinvoices`, `purchaseorders` |
| Financials | All financial collections |
| Inventory | `stock_register`, `stock_audit`, `purchaseorders`, `assets`, `indentproduct` |
| Orders | `estimates`, `orders_core` |

---

**Next Step:** Begin Phase 1, Unit 1 (Sales Module) with chair gate validation.
