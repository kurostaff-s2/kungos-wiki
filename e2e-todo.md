# E2E Test TODO — Pages Modified on 2026-05-04

---

## Rules

1. **Do not deviate from the UI design** — Tailwind + Radix + shadcn-ui is the approved stack. Every component must align with these primitives.
2. **Always commit when a bug is fixed** — Small, atomic commits. Never batch multiple unrelated fixes.
3. **Never roll back commits during E2E testing** — If a test fails, fix the code, don't revert the commit.
4. **Don't make things more complex** — Simple fixes over clever solutions. Follow existing patterns.
5. **Never deviate from the access level design** — `access-level-design.md` is the source of truth for RBAC.
6. **Never deviate from the KungOS v2 plan** — `KungOS_v2.md` and `kungos_v2_db.md` are the source of truth for tenant architecture.
7. **Always assume there is data in the DB** — If a page shows nothing, check the database first before assuming a code bug. When in doubt, query MongoDB/Postgres to confirm data exists.
8. **Stick to the standardized naming nomenclature** — Use `tenant`, `BG`, `Division`, `Branch`. Never use `entity` in new code. Variables: `divs`, `accessibleDivs`, `filterByDiv`, `division_accesslevel`. Backend fields: `bg_code`, `division`, `branch`. Show **labels** to users, use **codes** for filtering/API calls.
9. **E2E login credentials are in `.env.e2e` and `e2e/fixtures.js`** — Never hardcode credentials in test files. Use the fixtures for auth setup.

---

**Commits:** `62d6907` → `a3c1467` (10 commits)
**Scope:** Nomenclature cleanup, TDZ fixes, StatusBadge→Badge, select→Radix Select, Redux connect→useSelector, TanStack Table cell renderers

---

## Accounts

| Page | File | Changes | Risk |
|---|---|---|---|
| Credit/Debit Notes | `Accounts/CreditDebitNotes.jsx` | TDZ fix, entity→division, StatusBadge→Badge, select→Radix | 🔴 High (TDZ + nomenclature) |
| Financials | `Accounts/Financials.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| Invoice Detail | `Accounts/InvoiceDetail.jsx` | entity→division, StatusBadge→Badge, unused import removed | 🟢 Low |
| Invoices List | `Accounts/InvoicesList.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| ITC/GST | `Accounts/ITCGST.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| Overview | `Accounts/Overview.jsx` | TDZ fix, entity→division, StatusBadge→Badge, StatCard label→title | 🔴 High (TDZ) |
| Payment Vouchers | `Accounts/PaymentVouchers.jsx` | TDZ fix, entity→division, StatusBadge→Badge, select→Radix | 🔴 High (TDZ) |
| Purchase Orders | `Accounts/PurchaseOrders.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| Vendors List | `Accounts/VendorsList.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |

---

## Cafe

| Page | File | Changes | Risk |
|---|---|---|---|
| Pricing Config | `cafe/PricingConfig.jsx` | select→Radix Select | 🟡 Medium |
| Stations List | `cafe/StationsList.jsx` | select→Radix Select (2 filters) | 🟡 Medium |

---

## Core Pages

| Page | File | Changes | Risk |
|---|---|---|---|
| Counters | `Counters.jsx` | Redux connect→useSelector | 🟡 Medium |
| Employees Salary | `EmployeesSalary.jsx` | entity→division, select→Radix Select | 🟡 Medium |
| Home | `Home.jsx` | entity→division, TDZ fix | 🟡 Medium |
| Invoice/Credit | `InvoiceCredit.jsx` | Redux connect→useSelector | 🟡 Medium |
| Inward Debit Note | `InwardDebitNote.jsx` | entity→division, select→Radix Select (4) | 🔴 High (form-heavy) |
| Inward Payment | `InwardPayment.jsx` | select→Radix Select (4) | 🟡 Medium |
| Search Results | `SearchResults.jsx` | Redux connect→useSelector, select→Radix Select | 🟡 Medium |
| Users | `Users.jsx` | entity→division | 🟢 Low |

---

## Estimates

| Page | File | Changes | Risk |
|---|---|---|---|
| Estimates List | `Estimates/EstimatesList.jsx` | TDZ fix, TanStack Table cell renderers, StatusBadge→Badge, select→Radix, accessor→accessorKey | 🔴 Critical (verified ✅) |
| Estimates Detail | `Estimates/EstimatesDetail.jsx` | Redux connect→useSelector, StatusBadge→Badge | 🟡 Medium |
| Create Estimate | `CreateEstimate.jsx` | select→Radix Select | 🟡 Medium |

---

## Generate Invoice

| Page | File | Changes | Risk |
|---|---|---|---|
| Generate Invoice | `GenerateInvoice.jsx` | select→Radix Select (12 elements: search type, comp collection/type/maker, prod collection/type/category/maker, tax_rate, division, billadd state, shpadd state) | 🔴 Critical (form-heavy) |

---

## HR

| Page | File | Changes | Risk |
|---|---|---|---|
| Attendance | `Hr/Attendence.jsx` | Redux connect→useSelector | 🟡 Medium |
| Create Employee | `Hr/CreateEmp.jsx` | Redux connect→useSelector | 🟡 Medium |
| Dashboard | `Hr/Dashboard.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| Employee Access Level | `Hr/EmployeeAccessLevel.jsx` | entity→division, select→Radix Select (dynamic color classes) | 🔴 High (dynamic styling) |
| Employees | `Hr/Employees.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| Job Applications | `Hr/JobApps.jsx` | Redux connect→useSelector, entity→division, StatusBadge→Badge | 🟡 Medium |

---

## Inventory

| Page | File | Changes | Risk |
|---|---|---|---|
| Audit | `Inventory/Audit.jsx` | entity→division, StatusBadge→Badge, StatCard label→title | 🟢 Low |
| Audit Detail | `Inventory/AuditDetail.jsx` | entity→division, StatusBadge→Badge, StatCard label→title | 🟢 Low |
| Stock | `Inventory/Stock.jsx` | entity→division, select→Radix Select, unused import removed | 🟡 Medium |
| Stock Detail | `Inventory/StockDetail.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| Stock Register | `Inventory/StockRegister.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| TP Builds | `Inventory/TPBuilds.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| TP Builds Detail | `Inventory/TPBuildsDetail.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |
| TP Builds New | `Inventory/TPBuildsNew.jsx` | entity→division, unused import removed | 🟢 Low |
| Create TP Build | `CreateTPBuild.jsx` | select→Radix Select (5: division, channel, preset type, 2× margin) | 🔴 High (form-heavy) |

---

## Orders

| Page | File | Changes | Risk |
|---|---|---|---|
| Create Order | `Orders/OrderCreate.jsx` | unused import removed | 🟢 Low |
| Order Detail | `Orders/OrderDetail.jsx` | unused import removed | 🟢 Low |
| Orders List | `Orders/OrdersList.jsx` | StatusBadge→Badge | 🟢 Low |
| Overview | `Orders/Overview.jsx` | entity→division, StatCard label→title | 🟢 Low |
| Create PO | `CreatePO.jsx` | select→Radix Select | 🟡 Medium |
| Indent List | `IndentList.jsx` | select→Radix Select (2) | 🟡 Medium |

---

## Outward

| Page | File | Changes | Risk |
|---|---|---|---|
| Outward Invoices | `OutwardInvoices.jsx` | TDZ fix, entity→division, download URL bug fix | 🔴 High (TDZ + URL) |
| Outward Invoice | `OutwardInvoice.jsx` | entity→division, select→Radix Select (6: division, collection, type, category, maker, tax_rate) | 🔴 Critical (form-heavy) |
| Outward Debit Notes | `OutwardDebitNotes.jsx` | TDZ fix, entity→division | 🔴 High (TDZ) |
| Outward Credit Notes | `OutwardCreditNotes.jsx` | TDZ fix, entity→division | 🔴 High (TDZ) |
| Create Outward DNote | `CreateOutwardDNote.jsx` | entity→division, select→Radix Select (3) | 🔴 High (form-heavy) |
| Create Payment Link | `CreatePaymentLink.jsx` | select→Radix Select | 🟡 Medium |

---

## Products

| Page | File | Changes | Risk |
|---|---|---|---|
| Overview | `Products/Overview.jsx` | TDZ fix, entity→division, StatusBadge→Badge | 🔴 High (TDZ) |
| Presets | `Products/Presets.jsx` | StatusBadge→Badge | 🟢 Low |
| Product Detail | `Products/ProductDetail.jsx` | StatusBadge→Badge, duplicate import fix | 🟢 Low |
| Products List | `Products/ProductsList.jsx` | entity→division, StatusBadge→Badge | 🟢 Low |

---

## Service Requests

| Page | File | Changes | Risk |
|---|---|---|---|
| Service Requests List | `ServiceRequests/ServiceRequestsList.jsx` | TanStack Table cell renderers, StatusBadge→Badge, Filter import fix | 🔴 High (table) |
| Service Requests Detail | `ServiceRequests/ServiceRequestsDetail.jsx` | Redux connect→useSelector, StatusBadge→Badge | 🟡 Medium |

---

## Components

| Component | File | Changes | Risk |
|---|---|---|---|
| TenantSelector | `layout/TenantSelector.jsx` | Full rewrite — entities→divs, labels-only display | 🔴 Critical (global) |
| DivisionSelector | `common/DivisionSelector.jsx` | Renamed from EntitySelector | 🟡 Medium |
| ListFilters | `common/ListFilters.jsx` | Renamed from EntityFilters | 🟡 Medium |
| OrderTableComponents | `common/OrderTableComponents.jsx` | TanStack Table cell renderers (10 columns) | 🔴 Critical (shared) |
| AuthenticatedRoute | `common/AuthenticatedRoute.jsx` | entity→division | 🟡 Medium |
| ConvertToOrderDialog | `common/ConvertToOrderDialog.jsx` | entity→division | 🟢 Low |
| NewOrder | `NewOrder.jsx` | entity→division | 🟢 Low |
| ProductBasicInfo | `ProductForm/ProductBasicInfo.jsx` | entity→division | 🟢 Low |
| AppLayout | `layout/AppLayout.jsx` | entity→division | 🟢 Low |
| index (common) | `common/index.jsx` | Export rename EntitySelector→DivisionSelector | 🟢 Low |

---

## Actions / Lib

| File | Changes | Risk |
|---|---|---|
| `actions/admin.jsx` | entity→division | 🟡 Medium |
| `actions/user.jsx` | entity→division | 🟡 Medium |
| `lib/queryKeys.js` | entity→division | 🟢 Low |
| `App.jsx` | entity→division | 🟢 Low |

---

## E2E Test Priority

### 🔴 Critical (test first)
1. **Estimates List** — TDZ + table renderers + form (already verified ✅)
2. **Generate Invoice** — 12 select elements in complex form
3. **Outward Invoice** — 6 select elements in complex form
4. **Create TP Build** — 5 select elements in complex form
5. **Inward Debit Note** — 4 select elements in complex form
6. **Create Outward DNote** — 3 select elements in complex form
7. **Service Requests List** — Table cell renderers
8. **Accounts/Overview** — TDZ fix
9. **Accounts/PaymentVouchers** — TDZ fix
10. **OutwardInvoices** — TDZ + download URL fix
11. **OutwardDebitNotes** — TDZ fix
12. **OutwardCreditNotes** — TDZ fix
13. **Products/Overview** — TDZ fix
14. **TenantSelector** — Global component, affects all pages

### 🟡 Medium (test second)
15. **Hr/EmployeeAccessLevel** — Dynamic color classes on SelectTrigger
16. **EmployeesSalary** — Division assignment select
17. **IndentList** — 2 select elements
18. **Inventory/Stock** — Collection filter select
19. **CreatePO** — Division select
20. **SearchResults** — Filter dropdown
21. **CreatePaymentLink** — Expiry select
22. **cafe/PricingConfig** — Tier select
23. **cafe/StationsList** — 2 filter selects
24. **Counters** — Redux useSelector
25. **InvoiceCredit** — Redux useSelector
26. **Hr/JobApps** — Redux useSelector + StatusBadge
27. **Hr/Attendence** — Redux useSelector
28. **Hr/CreateEmp** — Redux useSelector
29. **EstimatesDetail** — Redux useSelector + StatusBadge
30. **ServiceRequestsDetail** — Redux useSelector + StatusBadge

### 🟢 Low (test last)
31-56. All StatusBadge-only and entity→division-only pages

---

## Regression Checklist

- [ ] Login flow → TenantSelector shows labels, not codes
- [ ] Division switch → all pages filter correctly by code
- [ ] Branch switch → all pages filter correctly by code
- [ ] Estimates list → data loads, no TDZ, table renders
- [ ] Generate Invoice → all 12 dropdowns open/selected correctly
- [ ] Outward Invoice → all 6 dropdowns open/selected correctly
- [ ] Create TP Build → all 5 dropdowns open/selected correctly
- [ ] Inward Debit Note → all 4 dropdowns open/selected correctly
- [ ] Service Requests list → table renders data correctly
- [ ] Accounts/PaymentVouchers → no TDZ crash
- [ ] OutwardInvoices → no TDZ crash, download works
- [ ] Products/Overview → no TDZ crash
- [ ] HR/EmployeeAccessLevel → color-coded select renders correctly
- [ ] All StatusBadge pages → badges render with correct colors
- [ ] All pages with useSelector → no "user is undefined" crash
