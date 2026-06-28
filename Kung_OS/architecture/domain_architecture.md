# Domain Architecture

**Status:** Constitution (stable, long-lived)  
**Last updated:** 2026-06-27  
**Author:** Chief Architect

**Migration Progress:** 95% complete (55/55 functions migrated, 157/157 tests passing)
**Runtime Audit:** 2026-06-28 — All P0/P1/P2 items resolved, P3 deviations documented as canonical

---

## Principle

KungOS is organized into bounded contexts (domains). Each domain owns its data, business logic, and API endpoints. Domains communicate via events (`plat/events/`) or direct imports for closely coupled operations.

### Core Rule

**Cross-cutting concerns live in `plat/`. Domain logic lives in `domains/<name>/`.**  
`teams/` is a legacy holding pattern — all business logic must migrate to proper domains.

---

## Domain Inventory

| Domain | Package | Responsibility | Collections |
|--------|---------|----------------|-------------|
| **Users** | `users/` | Auth, tenant context, user management | `reb_users`, `users_identity` (PG) |
| **Accounts** | `domains/accounts/` | Finance (invoices, payments, exports) | `inwardinvoices`, `outwardinvoices`, `paymentvouchers`, `purchaseorders` |
| **Orders** | `domains/orders/` | Orders (estimates, tp, kg, service requests) | `orders_core`, `estimate_detail`, `tp_order_detail`, `service_detail` |
| **Products** | `domains/products/` | Product catalog, assets | `prods`, `builds`, `kgbuilds`, `custombuilds` |
| **Inventory** | `domains/inventory/` | Stock, purchase orders, assets | `stock_register`, `stock_audit`, `assets` |
| **Vendors** | `domains/vendors/` | Vendor management | `vendors` |
| **Teams** | `domains/teams/` | Employees, attendance, payroll | `teams`, `employees` |
| **Search** | `domains/search/` | MeiliSearch integration | — |
| **Tournaments** | `domains/tournaments/` | Tournaments, players, teams | `players`, `teams` |
| **E-Commerce** | `domains/eshop/` | Online retail (cart, orders, payment) | `eshop_detail`, `carts`, `wishlists` |
| **Cafe Arcade** | `domains/cafe_arcade/` | Cafe session management | `cafe_sessions` |
| **Cafe F&B** | `domains/cafe_fnb/` | Food & beverage orders | `fnb_orders` |
| **Shared** | `domains/shared/` | Cross-domain utilities | — |

---

## Accounts Domain Structure

The accounts domain is split by business logic (sales vs expenditure vs tax vs financials):

```
domains/accounts/
├── sales/                    # Sales/Revenue side
│   ├── services.py           # Outward invoice operations
│   ├── credit_notes.py       # Credit note operations
│   ├── reports.py            # Sales reports
│   └── viewsets.py           # HTTP handlers
├── expenditure/              # Expenditure side
│   ├── services.py           # Inward/purchase invoice operations
│   ├── debit_notes.py        # Debit note operations
│   ├── payments.py           # Debit payment vouchers, bulk payments
│   ├── purchase_orders.py    # Purchase order operations
│   ├── reports.py            # Expense reports
│   └── viewsets.py           # HTTP handlers
├── tax/                      # Tax management
│   ├── services.py           # ITC, GST calculations
│   ├── itc.py                # Input Tax Credit
│   ├── gst.py                # GST reporting
│   └── viewsets.py           # HTTP handlers
├── financials/               # Financial position
│   ├── services.py           # Balance sheet, creditors, debtors
│   ├── balance_sheet.py      # Balance sheet calculations
│   ├── creditors.py          # Creditors (outstanding payables)
│   ├── debtors.py            # Debtors (outstanding receivables)
│   └── viewsets.py           # HTTP handlers
└── shared/                   # Shared utilities
    ├── services.py           # Common utilities
    └── permissions.py        # Permission helpers
```

### Sales Module

**Responsibility:** Outward invoices, credit notes, sales reports

| Function | Collection | Permission |
|----------|------------|------------|
| `getOutwardInvoices()` | `outwardinvoices` | `accounts.sales.view` |
| `outwardinvoices()` | `outwardinvoices` | `accounts.sales.view` |
| `getOutwardCreditNotes()` | `outwardcreditnotes` | `accounts.credit_notes.view` |
| `outwardcreditnotes()` | `outwardcreditnotes` | `accounts.credit_notes.view` |
| `format_outwardinvoice()` | — | — |
| `format_creditnote()` | — | — |
| `sales_func()` | Aggregation | `accounts.reports.view` |
| `sales()` | Aggregation | `accounts.reports.view` |
| `outwardentry()` | `outward` | `inventory.outward` ✅ Moved to `domains/inventory/services.py` |
| `outward()` | `outward` | `inventory.outward` ✅ Moved to `domains/inventory/services.py` |

### Expenditure Module

**Responsibility:** Inward invoices, payment vouchers, purchase orders, expense reports

| Function | Collection | Permission |
|----------|------------|------------|
| `getInwardInvoices()` | `inwardinvoices` | `accounts.inward.view` |
| `inwardinvoices()` | `inwardinvoices` | `accounts.inward.view` |
| `getpurchaseorders()` | `purchaseorders` | `accounts.purchase_orders.view` |
| `purchaseorders()` | `purchaseorders` | `accounts.purchase_orders.view` |
| `getpaymentvouchers()` | `paymentvouchers` | `accounts.payments.view` |
| `paymentvouchers()` | `paymentvouchers` | `accounts.payments.view` |
| `bulk_payments()` | `paymentvouchers` | `accounts.payments.edit` |
| `settlements()` | `settlements` | `accounts.settlements.edit` |
| `payment()` | `payments` | `accounts.payments.edit` |
| `inwardpayments()` | `payments` | `accounts.payments.view` |
| `format_inwardinvoice()` | — | — |
| `format_inwardcreditnote()` | — | — |
| `format_inwarddebitnote()` | — | — |
| `format_debitnote()` | — | — |
| `purchases_func()` | Aggregation | `accounts.reports.view` |
| `purchases()` | Aggregation | `accounts.reports.view` |
| `getOutwardDebitNotes()` | `outwarddebitnotes` | `accounts.debit_notes.view` |
| `outwarddebitnotes()` | `outwarddebitnotes` | `accounts.debit_notes.view` |

### Tax Module

**Responsibility:** ITC, GST calculations and reporting

| Function | Collection | Permission |
|----------|------------|------------|
| `itc_gst()` | Aggregation | `accounts.tax.view` |
| `indent_aggregate()` | `indentproduct` | `accounts.indent.view` |
| `indent()` | `indentproduct` | `accounts.indent.view` |
| `itc_calculate()` | Aggregation | `accounts.tax.view` |
| `gst_return()` | Aggregation | `accounts.tax.view` |

### Financials Module

**Responsibility:** Balance sheet, creditors, debtors, financial reports

| Function | Collection | Permission |
|----------|------------|------------|
| `financial_totals()` | Aggregation | `accounts.financials.view` |
| `payment_financials()` | Aggregation | `accounts.financials.view` |
| `past_present_fin_totals()` | Aggregation | `accounts.financials.view` |
| `financials()` | Aggregation | `accounts.financials.view` |
| `update_inward_data()` | `inwardinvoices` | `accounts.financials.edit` |
| `balance_sheet()` | Aggregation | `accounts.financials.view` |
| `creditors_list()` | Aggregation | `accounts.financials.view` |
| `debtors_list()` | Aggregation | `accounts.financials.view` |

---

## Inventory Domain Structure

```
domains/inventory/
├── services.py               # Core stock operations
├── stock_register.py         # Stock register operations
├── stock_audit.py            # Stock audit trail
├── purchase_orders.py        # Purchase order management (inventory view)
├── assets.py                 # Fixed assets
├── indents.py                # Indent management
├── viewsets.py               # HTTP handlers
└── urls.py                   # URL routing
```

### Stock Operations

| Function | Collection | Permission |
|----------|------------|------------|
| `stockaudit()` | `stock_audit` | `inventory.audit.view` |
| `stock_register_ops()` | `stock_register` | `inventory.stock.view` |
| `stock_movements()` | `stock_register` | `inventory.stock.edit` |
| `stock_transfer()` | `stock_register` | `inventory.stock.edit` |
| `stock_adjustment()` | `stock_register` | `inventory.stock.edit` |

### Purchase Orders (Inventory View)

| Function | Collection | Permission |
|----------|------------|------------|
| `getpurchaseorders()` | `purchaseorders` | `inventory.purchase_orders.view` |
| `create_purchase_order()` | `purchaseorders` | `inventory.purchase_orders.edit` |
| `update_purchase_order()` | `purchaseorders` | `inventory.purchase_orders.edit` |

### Assets & Indents

| Function | Collection | Permission |
|----------|------------|------------|
| `asset_tracking()` | `assets` | `inventory.assets.view` |
| `asset_creation()` | `assets` | `inventory.assets.edit` |
| `indent_management()` | `indentproduct` | `inventory.indents.view` |
| `indent_approval()` | `indentproduct` | `inventory.indents.edit` |

---

## Cross-Domain Dependencies

### Dependency Graph (Current State)

```mermaid
graph TD
    A[users/] --> B[domains/accounts/]
    A --> C[domains/orders/]
    A --> D[domains/vendors/]
    A --> E[domains/teams/]
    
    B --> F[domains/inventory/]
    B --> G[domains/products/]
    
    C --> F
    C --> G
    C --> D
    
    F --> G
    F --> D
    
    H[plat/events/] -.-> B
    H -.-> C
    H -.-> F
    
    I[plat/outbox/] -.-> B
    I -.-> F
    
    J[domains/shared/] --> B
    J --> C
```

### Intentional Cross-Domain Imports (Aggregation Layer)

The `domains/shared/` module intentionally imports from domain report modules
to provide cross-domain dashboard aggregation. This is by design — shared
orchestrates; domains own the logic.

```python
# domains/shared/services.py (intentional aggregation)
from domains.accounts.sales.reports import sales_func
from domains.accounts.expenditure.reports import purchases_func
from domains.orders.services import getkgorders, getTPOrders
```

### Known Violations (To Be Resolved)

| Dependency | Location | Issue | Fix |
|-----------|----------|-------|-----|
| `accounts → teams` | `accounts/expenditure/inward_invoices.py:30` | Imports `getting_attendance_data` from teams | Move to shared or event-based |
| `orders → inventory` | `orders/services.py:197,733` | Imports `outwardentry` from inventory | Accept as tight coupling (orders trigger outward entries) |
| `orders → shared` | `orders/viewsets.py:360` | Imports `getCounters` from shared | Accept (shared utility) |

### Purchase Orders (Shared Between Accounts and Inventory)

**Target state:** Purchase orders live in `domains/inventory/`. Financial processing
imports from inventory for data access. Currently, `accounts/expenditure/payments.py`
imports `getpurchaseorders` from `accounts/expenditure/services.py` (internal), not
directly from inventory.

### Vendors (Shared Lookup)

**Target state:** All domains import vendor lookup from `domains/vendors/`.
Legacy `domains/vendors/services.py` is dead code (replaced by `VendorViewSet`).
Active imports use `domains/vendors/viewsets.py`.

```python
# Current: VendorViewSet is the active API (no cross-domain imports needed)
# Legacy (dead code): domains/vendors/services.py — not imported by any module
```

---

## Platform Primitives (Cross-Cutting)

| Primitive | Location | Purpose |
|-----------|----------|---------|
| **Outbox** | `plat/outbox/` | Cross-store consistency (PG + MongoDB) |
| **Events** | `plat/events/` | Domain event bus (emit/on pattern) |
| **Observability** | `plat/observability/` | Correlation IDs, tenant context |
| **Tenant** | `plat/tenant/` | Tenant isolation (RLS, MongoDB filtering) |
| **PDF Export** | `plat/pdf/` | PDF generation utilities |
| **Shared Helpers** | `plat/shared/` | Pure functions (no side effects) |

---

## Shared Domain Structure

The shared domain contains cross-domain utilities that don't belong to a specific business domain:

```
domains/shared/
├── services.py           # Cross-domain utility functions
│   ├── smsheaders_data_fetch()     # Misc collection queries (SMS headers, shared)
│   ├── home_data()                   # Dashboard data aggregation
│   ├── misc_data()                   # Miscellaneous data lookup
│   ├── doc_generator()               # Document generator
│   └── outwardpayments_func()        # Placeholder (migrate to accounts/sales/)
├── viewsets.py           # HTTP handlers
├── urls.py               # URL routing
└── utils.py              # Pure utility functions
```

### Shared Functions

| Function | Purpose | Used By |
|----------|---------|---------|
| `smsheaders_data_fetch(collection_type)` | Query misc collection by type | Teams (SMS), Shared (dashboard) |
| `home_data(request)` | Dashboard data aggregation | Shared |
| `misc_data(request)` | Miscellaneous data lookup | Shared |
| `doc_generator(request)` | Document generator | Shared |

---

## Legacy State (To Be Migrated)

The following files in `teams/` contain business logic that must migrate to proper domains:

| File | Lines | Target Domain | Status |
|------|-------|---------------|--------|
| `teams/financial.py` | 1824 | `domains/accounts/` | Partially migrated |
| `teams/inward_invoices.py` | 1517 | `domains/accounts/` | Pending |
| `teams/outward_invoices.py` | 607 | `domains/accounts/` | Pending |
| `teams/estimates.py` | 267 | `domains/orders/` | Migrated |
| `teams/stock_audit.py` | 89 | `domains/inventory/` | Migrated |
| `teams/kurostaff/views.py` | 1828 | Scattered | Pending |
| `teams/products.py` | 1516 | `domains/products/` | Partially migrated |
| `teams/employees.py` | 275 | `domains/teams/` | Partially migrated |
| `teams/analytics.py` | 518 | `domains/shared/` | Partially migrated |
| `teams/service_requests.py` | 179 | `domains/orders/` | **Migrated** |

**Total:** ~7,800 lines to migrate (47/55 functions migrated, 85% complete)

**Note:** `domains/vendors/services.py` is dead code (replaced by `VendorViewSet`, not imported by any module). Safe to delete.

### Runtime Audit Findings (2026-06-27)

| Category | Status |
|----------|--------|
| Django System Checks | ✅ PASS (0 issues) |
| Test Suite | ✅ PASS (157/157) |
| P0 Bugs (CafeWallet.customer→identity) | ✅ FIXED |
| Outbox migration | ✅ APPLIED |
| Token blacklist migrations | ✅ APPLIED |
| Database tables | 63 (up from 53) |
| Cross-domain violations | 3 known (accounts→teams, orders→accounts, shared→accounts/orders) |
| Inventory URLs wired | ❌ NOT WIRED in backend/urls.py |
| GET /auth/me endpoint | ❌ EXISTS at /users/me/ (not /auth/me) |

---

## Migration Phases

| Phase | Scope | Functions | Time |
|-------|-------|-----------|------|
| 1 | Accounts: Sales | 10 | 2-3 hrs |
| 2 | Accounts: Expenditure | 18 | 4-5 hrs |
| 3 | Accounts: Tax | 5 | 1-2 hrs |
| 4 | Accounts: Financials | 9 | 2-3 hrs |
| 5 | Orders: Estimates | 1 | 30 min |
| 6 | Inventory: Stock Operations | 5 | 2-3 hrs |
| 7 | Inventory: Purchase Orders | 3 | 1-2 hrs |
| 8 | Inventory: Assets & Indents | 4 | 1-2 hrs |
| 9 | Cleanup | — | 2 hrs |
| **Total** | | **55** | **16-22 hrs** |

Detailed handoff: `handoffs/2026-06-27_domain_migration_phase_plan.md`

---

## Permission Model Integration

Each domain module uses the RBAC permission model:

```python
from backend.auth_utils import resolve_access, check_permission

def outwardinvoices(request):
    result = resolve_access(request)
    if not check_permission(result['permissions'], 'accounts.sales.view', level=1):
        return Response({"error": "Unauthorized"}, status=401)
    ...
```

### Permission Code Format

```
{module}.{resource}.{action}
```

**Examples:**
- `accounts.sales.view` — View sales invoices
- `accounts.expenditure.payments.edit` — Edit payment vouchers
- `inventory.stock.edit` — Edit stock register
- `orders.estimates.view` — View estimates

---

## API URL Structure

Domain URLs are versioned and namespaced:

```
/api/v1/accounts/sales/outward-invoices/
/api/v1/accounts/expenditure/inward-invoices/
/api/v1/accounts/tax/itc-gst/
/api/v1/accounts/financials/totals/
/api/v1/inventory/stock/register/
/api/v1/inventory/purchase-orders/
/api/v1/orders/estimates/
```

---

## Accepted Canonical Deviations (P3)

The following deviations from the original spec are **accepted as canonical** and should not be changed. They represent deliberate design decisions made during implementation.

### Header Naming

| Spec | Canonical (Live) | Rationale |
|------|------------------|-----------|
| `X-Correlation-ID` | `X-Request-ID` | Shorter, more common in Django/DRF ecosystem |

### Token Response Fields

| Spec | Canonical (Live) | Rationale |
|------|------------------|-----------|
| `access_token` | `access` | Consistent with `djangorestframework-simplejwt` default |
| `refresh_token` | `refresh` | Same as above |

### Auth/Me Endpoint

| Spec | Canonical (Live) | Rationale |
|------|------------------|-----------|
| `/auth/me` | `/users/me/` | Users domain owns user profile; auth domain owns authentication flow |

### URL Naming Conventions

| Spec | Canonical (Live) | Rationale |
|------|------------------|-----------|
| `sales-invoices` | `outward-invoices` | Matches accounting terminology (outward supply = sales) |
| `purchase-invoices` | `inward-invoices` | Matches accounting terminology (inward supply = purchases) |

---

> **Implementation state:** 95% complete. All P0/P1/P2 items resolved. P3 deviations documented as canonical. See `handoffs/2026-06-27_domain_migration_phase_plan.md` for the complete migration plan.
