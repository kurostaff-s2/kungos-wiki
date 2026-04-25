## [2026-04-23] Navigation & Order Restructure — Phase 6: Products & Procurement Reorganization

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Phase 6: Products & Procurement Reorganization

**Context:** Phase 6 consolidates Inventory, Stock, TP Builds, Purchase Orders, and Indents under a unified `products/` URL hierarchy. This aligns with the new navigation structure where Products & Procurement is a single section containing Catalog, Inventory, Procurement, and Audit subsections.

### Changes made

#### 1. Updated navigation.jsx paths
- **Modified:** `src/data/navigation.jsx`
- **Changes:**
  - Inventory: `inventory/stock` → `products/inventory`
  - Stock Register: `inventory/stock-register` → `products/inventory/stock-register`
  - TP Builds: `inventory/tp-builds` → `products/inventory/tp-builds`
  - Purchase Orders: `accounts/purchase-orders` → `products/procurement/po`
  - Indents: `accounts/indents` → `products/procurement/indents`
  - Audit: `inventory/audit` → `products/audit`

#### 2. Updated main.jsx — new routes + legacy redirects
- **Modified:** `src/routes/main.jsx` — 155 routes, 75 legacy redirects
- **New routes added:**
  - `/products/inventory` → StockList
  - `/products/inventory/:productid` → StockDetail
  - `/products/inventory/stock-register` → StockRegisterPage
  - `/products/inventory/tp-builds` → TPBuildsList
  - `/products/inventory/tp-builds/new` → TPBuildsNew
  - `/products/inventory/tp-builds/:buildId` → TPBuildsDetail
  - `/products/inventory/tp-builds/:buildId/edit` → TPBuildsNew
  - `/products/audit` → AuditList
  - `/products/audit/:auditId` → AuditDetail
  - `/products/procurement/po` → PurchaseOrdersNew
  - `/products/procurement/po/new` → CreatePO
  - `/products/procurement/indents` → IndentList
- **Legacy redirects added:**
  - `/inventory/stock` → `/products/inventory`
  - `/inventory/stock/:productid` → `/products/inventory/:productid`
  - `/inventory/stock-register` → `/products/inventory/stock-register`
  - `/inventory/audit` → `/products/audit`
  - `/inventory/audit/:auditId` → `/products/audit/:auditId`
  - `/inventory/tp-builds` → `/products/inventory/tp-builds`
  - `/inventory/tp-builds/new` → `/products/inventory/tp-builds/new`
  - `/inventory/tp-builds/:buildId` → `/products/inventory/tp-builds/:buildId`
  - `/accounts/purchase-orders` → `/products/procurement/po`
  - `/accounts/indents` → `/products/procurement/indents`
  - `/purchase-orders` → `/products/procurement/po`
  - `/purchase-orders/:po_no` → `/products/procurement/po`
  - `/create-po` → `/products/procurement/po/new`
  - `/create-po/:batchid` → `/products/procurement/po/new`
  - `/indent-list` → `/products/procurement/indents`

#### 3. Updated internal navigation links in Inventory pages
- **Modified:** `src/pages/Inventory/Overview.jsx` — 18 link replacements
- **Modified:** `src/pages/Inventory/StockDetail.jsx` — 3 link replacements
- **Modified:** `src/pages/Inventory/Stock.jsx` — 1 link replacement
- **Modified:** `src/pages/Inventory/TPBuilds.jsx` — 3 link replacements
- **Modified:** `src/pages/Inventory/TPBuildsDetail.jsx` — 3 link replacements
- **Modified:** `src/pages/Inventory/TPBuildsNew.jsx` — 3 link replacements
- **Modified:** `src/pages/Inventory/AuditDetail.jsx` — 3 link replacements
- **Modified:** `src/pages/Inventory/Audit.jsx` — 3 link replacements

#### 4. Updated internal navigation links in Accounts pages
- **Modified:** `src/pages/Accounts/Overview.jsx` — 1 link replacement (Purchase Orders → products/procurement/po)
- **Modified:** `src/pages/Accounts/PurchaseOrders.jsx` — API URL unchanged (backend endpoint)

#### 5. Updated shared components
- **Modified:** `src/components/layout/Breadcrumbs.jsx` — breadcrumb label updated
- **Modified:** `src/components/common/SearchBar.jsx` — search result mapping updated
- **Modified:** `src/components/common/Header.jsx` — header mapping updated
- **Modified:** `src/pages/SearchResults.jsx` — search result mapping updated
- **Modified:** `src/pages/CreatePO.jsx` — back navigation updated
- **Modified:** `src/pages/PurchaseOrder.jsx` — back navigation updated
- **Modified:** `src/pages/PurchaseOrders.jsx` — PO link updated

### Route mapping

| Old Path | New Path |
|----------|----------|
| `/inventory/stock` | `/products/inventory` |
| `/inventory/stock/:productid` | `/products/inventory/:productid` |
| `/inventory/stock-register` | `/products/inventory/stock-register` |
| `/inventory/tp-builds` | `/products/inventory/tp-builds` |
| `/inventory/tp-builds/new` | `/products/inventory/tp-builds/new` |
| `/inventory/tp-builds/:buildId` | `/products/inventory/tp-builds/:buildId` |
| `/inventory/audit` | `/products/audit` |
| `/inventory/audit/:auditId` | `/products/audit/:auditId` |
| `/accounts/purchase-orders` | `/products/procurement/po` |
| `/accounts/indents` | `/products/procurement/indents` |
| `/purchase-orders` | `/products/procurement/po` |
| `/create-po` | `/products/procurement/po/new` |
| `/create-po/:batchid` | `/products/procurement/po/new` |
| `/indent-list` | `/products/procurement/indents` |

### Files modified
- `src/data/navigation.jsx` — Updated paths to products/inventory and products/procurement
- `src/routes/main.jsx` — Added new routes, legacy redirects (155 total routes, 75 redirects)
- `src/pages/Inventory/Overview.jsx` — 18 link replacements
- `src/pages/Inventory/StockDetail.jsx` — 3 link replacements
- `src/pages/Inventory/Stock.jsx` — 1 link replacement
- `src/pages/Inventory/TPBuilds.jsx` — 3 link replacements
- `src/pages/Inventory/TPBuildsDetail.jsx` — 3 link replacements
- `src/pages/Inventory/TPBuildsNew.jsx` — 3 link replacements
- `src/pages/Inventory/AuditDetail.jsx` — 3 link replacements
- `src/pages/Inventory/Audit.jsx` — 3 link replacements
- `src/pages/Accounts/Overview.jsx` — 1 link replacement
- `src/components/layout/Breadcrumbs.jsx` — breadcrumb label
- `src/components/common/SearchBar.jsx` — search mapping
- `src/components/common/Header.jsx` — header mapping
- `src/pages/SearchResults.jsx` — search mapping
- `src/pages/CreatePO.jsx` — back navigation
- `src/pages/PurchaseOrder.jsx` — back navigation
- `src/pages/PurchaseOrders.jsx` — PO link

### Impact
- **Unified URL hierarchy:** All Products & Procurement under `/products/*`
- **Legacy preserved:** 14 legacy redirect paths maintained
- **Internal links updated:** All Inventory and Accounts pages reference new paths
- **Navigation sidebar:** Updated to reflect new structure
- **No component changes:** All components remain the same, only routes/paths changed

### Next
- **Phase 7:** Legacy cleanup — remove old page files and dead code
