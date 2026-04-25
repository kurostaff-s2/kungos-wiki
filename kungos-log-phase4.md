## [2026-04-23] Navigation & Order Restructure — Phase 4: Navigation Restructure & Route Redirects

**Plan item:** `docs/plans/2026-04-23-navigation-structure-restructure.md` — Phase 4: Navigation restructure (no behavior changes)

**Context:** Phase 4 restructures the global navigation hierarchy and route structure without changing any component behavior. Users will see the new navigation, but all existing bookmarks and links redirect to new paths.

### Changes made

#### 1. Updated navigation.jsx
- **Modified:** `src/data/navigation.jsx`
- **Changes:**
  - **Orders section:** Restructured with entry points (Estimates, Service Requests) at top, followed by Fulfillment Pipeline (status-driven tabs), Channels (filtered views), and Management actions
  - **Products & Procurement section:** New combined section replacing Products + Inventory + POs
    - Catalog: Products, Presets, Pre-Builts, Peripherals, Portal Editor
    - Inventory: Stock, Stock Register, TP Builds
    - Procurement: Purchase Orders, Indents/Batches
    - Audit
  - **Accounts section:** Streamlined with Documents, Payments, Master Data, Financials subsections
    - Moved Purchase Orders out (now in Products & Procurement)
  - **HR section:** Streamlined with Overview, Employees, Attendance, Salaries, Job Apps, Access Levels, Business Groups
  - **Users section:** New dedicated section with Users, User Detail, User Orders
  - **Updated sectionIcons:** Added "Products & Procurement" and "Users" mappings

#### 2. Updated main.jsx
- **Modified:** `src/routes/main.jsx`
- **Changes:**
  - Consolidated duplicate routes (removed 4 duplicates)
  - Total routes: 141 (down from 145)
  - Added new unified routes under `/orders/` and `/inventory/`
  - Added route redirects for all legacy paths
  - Removed legacy component imports that are no longer needed as direct routes

### Route Redirects Added

#### TP Orders → Unified Orders
| Old Path | New Path |
|----------|----------|
| `/tporders` | `/orders/overview` |
| `/tporders/:orderId` | `/orders/:orderId` |
| `/tporders/add-products/:orderId` | `/orders/:orderId` |
| `/tporders/add-inventory/:orderId` | `/orders/:orderId` |
| `/tporder-invoice/:orderid` | `/orders/:orderId` |

#### Offline Orders → Unified Orders
| Old Path | New Path |
|----------|----------|
| `/offlineorders` | `/orders/overview` |
| `/offlineorders/:orderId` | `/orders/:orderId` |
| `/offlineorder-invoice/:orderid` | `/orders/:orderId` |
| `/offlineorder-status/:orderid` | `/orders/:orderId` |

#### Estimates → Orders/Estimates
| Old Path | New Path |
|----------|----------|
| `/estimates` | `/orders/estimates` |
| `/estimates/:estimate_no` | `/orders/estimates/:estimate_no` |
| `/estimates/:estimate_no/:version` | `/orders/estimates/:estimate_no` |
| `/nps/estimates/:estimate_no` | `/orders/estimates/:estimate_no` |
| `/nps/estimates/:estimate_no/:version` | `/orders/estimates/:estimate_no` |
| `/create-estimate` | `/orders/estimates/new` |
| `/estimate-order/:estimate_no/:version` | `/orders/estimates/:estimate_no` |

#### Service Requests → Orders/Service-Request
| Old Path | New Path |
|----------|----------|
| `/service-request` | `/orders/service-request` |
| `/servicerequest/:srid` | `/orders/service-request/:srid` |
| `/kuroservices` | `/orders/service-request` |

#### Products & Inventory → New Structure
| Old Path | New Path |
|----------|----------|
| `/stock/inventory` | `/inventory/stock` |
| `/stock/inventory/details` | `/inventory/stock` |
| `/stock/outward` | `/inventory/stock` |
| `/stock-register` | `/inventory/stock-register` |
| `/stock-register/prod/:prodId` | `/inventory/stock-register` |
| `/stock-register/:prodColl` | `/inventory/stock-register` |
| `/stock-register/:prodColl/:prodType` | `/inventory/stock-register` |
| `/tpbuilds` | `/inventory/tp-builds` |
| `/tpbuilds/:buildId` | `/inventory/tp-builds/:buildId` |
| `/portaleditor` | `/products/portal-editor` |
| `/productfinder` | `/products` |
| `/prebuiltsfinder` | `/products/pre-builts` |
| `/replace-preset-values` | `/products/presets` |

#### Accounts → Streamlined
| Old Path | New Path |
|----------|----------|
| `/inward-invoices` | `/accounts/invoices` |
| `/inward-invoices/:invoiceid` | `/accounts/invoices/:invoiceid` |
| `/create-inward-invoice` | `/accounts/invoices/new` |
| `/inward-creditnotes` | `/accounts/notes` |
| `/inward-creditnotes/:creditnoteid` | `/accounts/notes/:creditnoteid` |
| `/create-inward-creditnote` | `/accounts/notes` |
| `/create-inward-debitnote` | `/accounts/notes` |
| `/payment-vouchers` | `/accounts/payment-vouchers` |
| `/payment-vouchers/:pv_no` | `/accounts/payment-vouchers` |
| `/vendors` | `/accounts/vendors` |
| `/financials` | `/accounts/financials` |
| `/analytics` | `/accounts/analytics` |
| `/itc-gst` | `/accounts/itc-gst` |

#### Purchase Orders → Accounts/Purchase-Orders
| Old Path | New Path |
|----------|----------|
| `/purchase-orders` | `/accounts/purchase-orders` |
| `/purchase-orders/:po_no` | `/accounts/purchase-orders` |
| `/create-po` | `CreatePO` (accessible) |
| `/create-po/:batchid` | `/accounts/purchase-orders/new` |

#### HR → Streamlined
| Old Path | New Path |
|----------|----------|
| `/employee-accesslevel` | `/hr/access-levels` |
| `/employee-accesslevel/:empid` | `/hr/access-levels` |
| `/bggroup` | `/hr/business-groups` |

#### Users → Streamlined
| Old Path | New Path |
|----------|----------|
| `/user/profile/:userid` | `/users/:userid` |

### Files modified
- `src/data/navigation.jsx` — New hierarchy with 6 sections (Orders, Products & Procurement, Accounts, HR, Users)
- `src/routes/main.jsx` — Consolidated routes, added legacy redirects, removed duplicates

### Route counts
- **Before:** 145 routes (4 duplicates)
- **After:** 141 routes (0 duplicates)

### Next
- **Phase 5:** Order consolidation — merge OfflineOrders into unified OrdersList with channel filter
- **Phase 6:** Products & Procurement reorganization (frontend pages)
- **Phase 7:** Legacy cleanup — remove old page files
