## [2026-04-23] Navigation & Order Restructure — Phase 9: Extend Shared Components

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Component Consolidation Plan

### Changes made

#### New shared components (5 files)

**1. `EntityStatCards.jsx`** — Generic configurable stat cards
- `EntityStatCards` — Takes array of card configs, renders grid
- `generateEntityStatCards(data, statusCounts, total)` — For any entity with status breakdown
- `generateFinancialStatCards(stats)` — Financial metrics (total, outstanding, overdue, paid)
- `generateInventoryStatCards(data)` — Inventory metrics (SKUs, out of stock, low stock, total qty)
- `generateEmployeeStatCards(data)` — Employee metrics (total, active, inactive, pending)

**2. `EntityFilters.jsx`** — Reusable search + filter + view toggle bar
- Search input with icon
- Status filter dropdown (optional)
- View toggle buttons (table/kanban or grid/list)
- Custom children slot for additional filters
- Reset button

**3. `SkeletonLoader.jsx`** — Loading skeletons
- `SkeletonLoader` — List page skeleton (stat cards + table)
- `GridSkeletonLoader` — Grid/list view skeleton
- `DetailSkeletonLoader` — Detail page skeleton

**4. `EntityDetailPage.jsx`** — Detail page wrapper
- Breadcrumb, header with icon/title/subtitle
- Status badge display
- Back button + custom action slot
- `InfoGrid` — Configurable info grid (2-5 cols)
- `DetailSection` — Section wrapper with title/action
- `EmptyDetailState` — Empty state for detail pages

**5. `EntityFormPage.jsx`** — Form page wrapper
- Breadcrumb, header with title/description
- Back + Cancel buttons
- Success/error message display
- `FormSection` — Section wrapper
- `FormFieldGroup` — Field with label + required indicator
- `FormGrid` — Configurable field grid (1-3 cols)

#### Updated query keys
- `stock(params)` — Stock/inventory data
- `tpBuilds(params)` — TP build data
- `invoices` — Invoices list
- `purchaseOrders(params)` — Purchase orders
- `indents(params)` — Indents

#### Refactored pages (8 files)

**Inventory:**
- `Stock.jsx` — React Query migration, EntityFilters, SkeletonLoader
- `StockDetail.jsx` — EntityDetailPage, InfoGrid, DetailSection
- `TPBuilds.jsx` — React Query migration, EntityFilters
- `TPBuildsDetail.jsx` — EntityDetailPage, DetailSection

**Accounts:**
- `InvoicesList.jsx` — React Query migration, EntityFilters
- `PurchaseOrders.jsx` — React Query migration, EntityFilters

**Products:**
- `ProductsList.jsx` — React Query migration, EntityFilters, GridSkeletonLoader

**HR:**
- `Employees.jsx` — React Query migration, EntityFilters

### Impact

| Metric | Before | After |
|---|---|---|
| Shared components | 8 (Phase 8) | 13 (Phase 9) |
| Pages using shared patterns | 6 (Phases 2-8) | 14 (Phases 2-9) |
| Entity pages refactored | 0 | 8 |
| React Query migrations | 6 | 8 |
| Files changed | — | 15 |
| Lines added | — | +1,567 |
| Lines removed | — | -1,607 |

### Patterns established

**List page pattern:**
```
PageBreadcrumb → PageHeader → EntityStatCards → EntityFilters → DataTable → EmptyState
```

**Detail page pattern:**
```
EntityDetailPage → DetailSection (info) → DetailSection (details) → DetailSection (actions)
```

**Form page pattern:**
```
EntityFormPage → FormSection (fields) → FormGrid → Submit bar
```

### Build verification
- All 15 files pass basic syntax checks (braces, parens balanced)
- Pre-existing build errors unchanged (OutwardInvoice.jsx, Profile, Switchgroup)
- 2,439 modules transformed successfully

### Next
- Phase 9 complete
- Remaining pages that could benefit: TPBuildsNew, Audit, AuditDetail, CreatePO, InvoiceCreate, CreateEmp, CreditDebitNotes, PaymentVouchers, Attendence, JobApps, ProductDetail, Presets
- Phase 10 (optional): Backend collection merge (tporders + kgorders → orders)
- Phase 11 (optional): React Query migration for remaining legacy pages
