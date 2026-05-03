# Phase 10: Nomenclature Cleanup & Bug Fixes (2026-05-04)

**Goal:** Eliminate "entity" terminology across codebase. Use correct tenant nomenclature: BG, Division, Branch. Show labels to users, use codes for filtering.

---

## TDZ (Temporal Dead Zone) Fixes

**Root cause:** `useBranchQuery({ division: activeDivision })` declared before `activeDivision` was defined.

### Files fixed (8 total)

| File | Fix |
|---|---|
| `Estimates/EstimatesList.jsx` | Reordered state + replaced `useTenantQuery` with inline `buildQueryString()` |
| `Products/Overview.jsx` | Moved `activeDivision` before `branchQuery` |
| `Accounts/Overview.jsx` | Moved `activeDivision` before `branchQuery` |
| `Accounts/PaymentVouchers.jsx` | Moved `activeDivision` before `branchQuery` |
| `Accounts/CreditDebitNotes.jsx` | Moved `activeDivision` before `branchQuery` |
| `OutwardInvoices.jsx` | Moved `activeDivision` before `branchQuery` |
| `OutwardDebitNotes.jsx` | Moved `activeDivision` before `branchQuery` |
| `OutwardCreditNotes.jsx` | Moved `activeDivision` before `branchQuery` |

### Pattern (correct order)
```jsx
const { division } = useTenant()
const [divisionFilter, setDivisionFilter] = useState(division)
const activeDivision = divisionFilter || division        // ← derive first
const branchQuery = useBranchQuery({ division: activeDivision })  // ← then use
```

---

## TenantSelector Rewrite

**File:** `src/components/layout/TenantSelector.jsx`

### Changes
- **Full rewrite** with correct nomenclature
- `entities` → `divs`, `bgEntities` → `bgDivs`
- `getEntityLabel` → `getDivLabel`
- `handleDivisionSelect` → `handleDivSelect`
- `divItem.div_code` → `divItem.code`, `divItem.title` → `divItem.label`
- Trigger button: shows division label (primary) + branch if set (was showing all 3 levels crammed)
- All display text uses **labels**; all filtering uses **codes**

### Before/After trigger
- Before: `BG_CODE / Division_Label / Branch` (crowded, codes visible)
- After: `Division Label · Branch` (clean, labels only)

---

## Nomenclature Cleanup — Frontend

### Component renames
| Old | New |
|---|---|
| `EntityFilters.jsx` | `ListFilters.jsx` |
| `EntitySelector.jsx` | `DivisionSelector.jsx` |

### Variable renames (24 pages)
- `accessibleEntities` → `accessibleDivs`
- `filterByEntity` → `filterByDiv`

### UI label fixes (12 files)
- `<td>Entity</td>` → `<td>Division</td>`
- `"Select Entity"` → `"Select Division"`
- `"Entity is required"` → `"Division is required"`

### Files touched
```
src/components/layout/TenantSelector.jsx
src/components/common/ListFilters.jsx (renamed from EntityFilters)
src/components/common/DivisionSelector.jsx (renamed from EntitySelector)
src/components/common/index.jsx
src/pages/OutwardInvoices.jsx
src/pages/OutwardDebitNotes.jsx
src/pages/OutwardCreditNotes.jsx
src/pages/Products/ProductsList.jsx
src/pages/Products/Overview.jsx
src/pages/Home.jsx
src/pages/Estimates/EstimatesList.jsx
src/pages/EmployeesSalary.jsx
src/pages/Accounts/InvoicesList.jsx
src/pages/Accounts/PaymentVouchers.jsx
src/pages/Accounts/VendorsList.jsx
src/pages/Accounts/Overview.jsx
src/pages/Accounts/CreditDebitNotes.jsx
src/pages/Accounts/PurchaseOrders.jsx
src/pages/Hr/Dashboard.jsx
src/pages/Hr/Employees.jsx
src/pages/Hr/EmployeeAccessLevel.jsx
src/pages/Hr/JobApps.jsx
src/pages/Hr/Attendence.jsx
src/pages/ServiceRequests/ServiceRequestsList.jsx
src/pages/Inventory/Audit.jsx
src/pages/Inventory/TPBuilds.jsx
src/pages/Inventory/Stock.jsx
src/pages/Inventory/StockRegister.jsx
src/pages/CreateTPBuild.jsx
src/pages/OutwardInvoice.jsx
src/pages/InwardDebitNote.jsx
src/pages/CreateOutwardDNote.jsx
src/pages/IndentList.jsx
src/pages/CreatePO.jsx
src/pages/Users.jsx
src/components/NewOrder.jsx
src/components/ProductForm/ProductBasicInfo.jsx
src/components/common/ConvertToOrderDialog.jsx
src/components/common/AuthenticatedRoute.jsx
src/components/layout/AppLayout.jsx
src/actions/admin.jsx
src/actions/user.jsx
src/App.jsx
src/lib/queryKeys.js
```

---

## Nomenclature Cleanup — Backend

### Critical bug fix
**`users/tenant_tokens.py`** — JWT payload was reading `ctx.entity` but model field is `ctx.division`. Token always had empty division list.
- JWT field: `entity` → `division`
- `_resolve_tenant_context()`: `ctx.entity` → `ctx.division`
- `get_tenant_from_token()`: `entity` → `division`

### Files fixed
```
users/tenant_tokens.py         — JWT payload entity→division (BUG FIX)
users/permissions.py           — resolve_permission() param entity→division
users/views.py                 — entity var→divisions, entity_accesslevel→division_accesslevel
users/api/viewsets.py          — 15+ entity refs → division
teams/kurostaff/views.py       — allentities→alldivs, entity→divisions
backend/response_utils.py      — ENTITY_ACCESS_DENIED→DIVISION_ACCESS_DENIED
tenant/models.py               — SCOPE_ENTITY→SCOPE_DIVISION, help_text cleanup
```

### Remaining "entity" references (intentional)
- `tenant/models.py` — "legal entity" is valid business term (company)
- `migrations/` — historical database migrations (untouched)
- `restore_kuropurchase.py`, `populate_entity.py`, `deploy_restore.py` — legacy MongoDB migration tools

---

## TanStack Table Cell Renderer Bug (Critical)

**Root cause:** TanStack Table v8 passes a `CellContext` object to `cell` functions, not the raw row. Code was written as `cell: (row) => row.estimate_no` treating the context as the row → all field accesses returned `undefined` → fallback values (`N/A`, `₹0`).

**Fix pattern:** `cell: (row) => row.field` → `cell: ({ row }) => row.original.field`

### Files fixed (4 total, 19 column definitions)

| File | Columns | Extra fixes |
|---|---|---|
| `Estimates/EstimatesList.jsx` | 8 (Estimate No, Customer, Division, Total, Status, Date, Actions) | Radix Select, Badge, Copy icon |
| `ServiceRequests/ServiceRequestsList.jsx` | 9 (SR ID, Customer, Device, Issue, Type, Assigned, Status, Date, Actions) | Badge, e.stopPropagation() |
| `OrderTableComponents.jsx` | 10 (EstimateProductsTable: 6, EstimateBuildsTable: 4) | Used in estimate/order detail pages |
| `Estimates/EstimatesDetail.jsx` | 0 (no DataTable) | StatusBadge → Badge (2 instances) |

### Pages already correct (verified)

- `Stock.jsx`, `OrdersList.jsx` — use `cell: info => info.getValue()` pattern
- `Employees.jsx`, `Financials.jsx`, `CreditDebitNotes.jsx`, `InvoicesList.jsx`, `PaymentVouchers.jsx` — already use `cell: ({ row }) => row.original.xxx`

### Shadcn/Radix alignment across all 4 files

- `accessor` → `accessorKey` (TanStack Table v8 standard)
- `StatusBadge(label, color)` → `Badge(variant)` (shadcn)
- Raw `<select>` → Radix `<Select>` + `<SelectTrigger>` + `<SelectContent>`
- `Button size="sm"` → `Button size="icon"` for action buttons
- Added `e.stopPropagation()` on action buttons to prevent row click
- Removed unused imports (`Search`, `Filter`, `ArrowUpDown`, `StatusBadge`)

## Verification

- Playwright test: `check-estimates` — **1 passed**, 30 table rows, data correct
- Manual headless check: estimate numbers (KGE2305051, KGE2305050...), totals (₹208,499, ₹1,728,725...), statuses rendering
- Frontend: zero "entity" references in active code
- Backend: zero "entity" references in active code paths (legacy tools excluded)

---

## Next
- Phase 11: Sidebar quick-wins (A-F) from `side-nav-design.md`
- Phase 12: Audit other pages for `useTenantQuery` double-`?` URL pattern
- Phase 13: Broader e2e suite to confirm backend signature fixes
- Audit remaining list pages for `pageSize` vs `defaultPageSize` prop alignment
- Migrate any remaining raw `<select>` elements to Radix `<Select>` across codebase
