# Frontend-Backend Coverage Audit (Final)

**Date:** 2026-07-02  
**Status:** ⚠️ **GAPS IDENTIFIED**  

---

## 🎯 **Audit Objective**

Verify that all frontend pages have corresponding backend endpoints and are covered in the runtime data hydration test handoff.

**Domain Mapping:**
- HR → **Teams** domain
- Products → Related to **Eshop** and **Inventory** domains
- Cafe-FNB & Cafe-Arcade → Separate domains
- Docs, SMS, Counters → **Shared** domain (implemented, NOT in handoff)
- Platform utilities → **plat** domain (middleware, filters, outbox, PDF)

---

## 📊 **Coverage Summary**

| Domain | Frontend Pages | Backend Endpoints | Handoff Coverage | Status |
|--------|---------------|-------------------|------------------|--------|
| **Orders** | 6 pages | 7 endpoints | 4/7 | ⚠️  Missing 3 |
| **Accounts** | 12 pages | 19 endpoints | 9/19 | ⚠️  Missing 10 |
| **Teams** (incl. HR) | 7 pages | 7 endpoints | 2/7 | ⚠️  Missing 5 |
| **Vendors** | 1 page | 2 endpoints | 1/2 | ✅ Complete |
| **Shared** | 1 page | 11 endpoints | 1/11 | ⚠️  Missing 10 |
| **Inventory** | 6 pages | 18 endpoints | 0/18 | ❌ Not covered |
| **Eshop** | 3 pages | 9 endpoints | 0/9 | ❌ Not covered |
| **Cafe Arcade** | 13 pages | 31 endpoints | 0/31 | ❌ Not covered |
| **Cafe FNB** | 1 page | 9 endpoints | 0/9 | ❌ Not covered |
| **Products** | 5 pages | 6 endpoints | 0/6 | ❌ Not covered |
| **Tenant/Settings** | 6 pages | 23 endpoints | 0/23 | ❌ Not covered |

**Total:** 61 frontend pages, 135 backend endpoints, 17/135 covered (13%)

---

## ✅ **Covered in Handoff**

### Orders Domain (4/7 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| EstimatesList | `/api/v1/orders/estimates` | ✅ Covered |
| EstimatesDetail | `/api/v1/orders/estimates/:estimate_no` | ✅ Covered |
| OrdersList | `/api/v1/orders/orders` | ✅ Covered (unified) |
| ServiceRequestsList | `/api/v1/orders/service-requests` | ✅ Covered |
| ServiceRequestsDetail | `/api/v1/orders/service-request/:srid` | ❌ Not in handoff |
| OrderCreate | `/api/v1/orders/in-store` (POST) | ❌ Not in handoff |
| OrderDetail | `/api/v1/orders/in-store/:orderId` | ❌ Not in handoff |

### Accounts Domain (9/19 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| AnalyticsNew | `/api/v1/accounts/analytics` | ✅ Covered |
| FinancialsNew | `/api/v1/accounts/financials` | ✅ Covered |
| InvoicesList | `/api/v1/accounts/inward-invoices` | ✅ Covered |
| InvoiceCreate | `/api/v1/accounts/inward-invoices` (POST) | ❌ Not in handoff |
| InvoiceDetail | `/api/v1/accounts/inward-invoices/:invoiceid` | ❌ Not in handoff |
| PaymentVouchersNew | `/api/v1/accounts/payment-vouchers` | ✅ Covered |
| VendorsListNew | `/api/v1/accounts/vendors` | ✅ Covered |
| CreditDebitNotes | `/api/v1/accounts/notes` | ⚠️  Partially covered |
| ITCGSTNew | `/api/v1/accounts/itc-gst` | ❌ Not in handoff |
| Ledgers | `/api/v1/accounts/sundry-ledger` | ❌ Not in handoff |
| PurchaseOrdersNew | `/api/v1/accounts/purchase-orders` | ❌ Not in handoff |
| BulkPayments | `/api/v1/accounts/bulk-payments` | ❌ Not in handoff |
| Overview (Accounts) | `/api/v1/accounts/overview` | ❌ Not in handoff |
| Revenue | `/api/v1/accounts/revenue` | ❌ Not in handoff |
| Expenditure | `/api/v1/accounts/expenditure` | ❌ Not in handoff |
| ProfitLoss | `/api/v1/accounts/profit-loss` | ✅ Covered |
| BalanceSheet | `/api/v1/accounts/balance-sheet` | ✅ Covered |
| Settlements | `/api/v1/accounts/settlements` | ❌ Not in handoff |
| Export | `/api/v1/accounts/export/*` | ❌ Not in handoff |

### Teams Domain - HR (2/7 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| Employees | `/api/v1/teams/employees` | ✅ Covered |
| Users | `/api/v1/teams/users` | ✅ Covered |
| Attendance | `/api/v1/teams/emp-attendance` | ❌ Not in handoff |
| Dashboard (HR) | `/api/v1/teams/attendance-dashboard` | ❌ Not in handoff |
| EditAttendance | `/api/v1/teams/edit-attendance/:userid` | ❌ Not in handoff |
| EmployeesSalary | `/api/v1/teams/employees/salary` | ❌ Not in handoff |
| JobApps | `/api/v1/careers/job-apps` | ❌ Not in handoff |
| CreateEmp | `/api/v1/teams/employees` (POST) | ❌ Not in handoff |
| EmployeeAccessLevel | `/api/v1/rbac/access-levels` | ❌ Not in handoff |

### Vendors Domain (1/2 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| VendorsListNew | `/api/v1/vendors/vendors` | ✅ Covered |
| VendorDetail | `/api/v1/vendors/vendors/:pk` | ❌ Not in handoff |

### Shared Domain (1/11 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| Home | `/api/v1/shared/home` | ✅ Covered |
| DocGenerator | `/api/v1/shared/doc-generator` | ❌ Not in handoff (implemented in `domains/shared/viewsets.py`) |
| SMS | `/api/v1/shared/sms` | ❌ Not in handoff (implemented in `domains/shared/viewsets.py`) |
| Misc | `/api/v1/shared/misc` | ❌ Not in handoff (implemented in `domains/shared/viewsets.py`) |
| CreateCollection | `/api/v1/shared/create-collection` | ❌ Not in handoff |
| GetCollection | `/api/v1/shared/get-collection` | ❌ Not in handoff |
| AdminPortal | `/api/v1/shared/adminportal` | ❌ Not in handoff (implemented in `domains/shared/viewsets.py`) |
| Counters | `/api/v1/shared/counters` | ❌ Not in handoff (implemented in `domains/shared/viewsets.py`) |
| SMSHeaders | `/api/v1/shared/sms-headers` | ❌ Not in handoff (implemented in `domains/shared/viewsets.py`) |
| Analytics | `/api/v1/shared/analytics` | ⚠️  Alias for accounts/analytics |
| Checklist | `/api/v1/shared/checklist` | ❌ Not in handoff |

**Note:** Shared domain methods (doc_generator, sms, misc, adminportal, counters, sms_headers) are **implemented** in `domains/shared/viewsets.py` but NOT documented in handoff.

---

## ❌ **NOT Covered in Handoff**

### Inventory Domain (18 endpoints, 0 covered)

**Frontend Pages:**
- StockList (`/inventory`)
- StockDetail (`/inventory/:productid`)
- StockRegisterPage (`/inventory/stock-register`)
- AuditList (`/inventory/audit`)
- AuditDetail (`/inventory/audit/:auditId`)
- TPBuildsList (`/products/tp-builds`)
- TPBuildsDetail (`/products/tp-builds/:buildId`)
- TPBuildsNew (`/products/tp-builds/new`)

**Backend Endpoints:**
```
/api/v1/inventory/items
/api/v1/inventory/items/:item_id
/api/v1/inventory/stock
/api/v1/inventory/stock/:stock_id
/api/v1/inventory/movements
/api/v1/inventory/movements/create
/api/v1/inventory/assets
/api/v1/inventory/assets/create
/api/v1/inventory/assets/:asset_id
/api/v1/inventory/assets/:asset_id/status
/api/v1/inventory/assets/:asset_id/movements
/api/v1/inventory/assets/movements/create
/api/v1/inventory/stock-audit
/api/v1/inventory/stock-audit/:audit_id
/api/v1/inventory/stock-audit/create
/api/v1/inventory/indents
/api/v1/inventory/indents/create
/api/v1/inventory/indents/:indent_id
/api/v1/inventory/indents/:indent_id/approve
/api/v1/inventory/purchase-orders
/api/v1/inventory/purchase-orders/:po_no
/api/v1/inventory/purchase-orders/create
/api/v1/inventory/reports/assets/:asset_id/maintenance
/api/v1/inventory/reports/assets/:asset_id/lifecycle
/api/v1/inventory/reports/branch/assets
/api/v1/inventory/reports/depreciation
```

**Data Sources:**
- PostgreSQL: `inventory_inventoryitem`, `inventory_inventorymovement`, `inventory_inventorystock`, `inventory_asset`, `inventory_stockaudit`, `inventory_indent`, `inv_purchase_orders`

---

### Eshop Domain (9 endpoints, 0 covered)

**Frontend Pages:**
- (No dedicated frontend pages — uses Products pages)

**Backend Endpoints:**
```
/api/v1/eshop/cart
/api/v1/eshop/cart/:id
/api/v1/eshop/wishlist
/api/v1/eshop/wishlist/:id
/api/v1/eshop/orders
/api/v1/eshop/orders/create
/api/v1/eshop/orders/:order_id
/api/v1/eshop/orders/:order_id/confirm
/api/v1/eshop/orders/:order_id/advance
```

**Data Sources:**
- PostgreSQL: `eshop_cart`, `eshop_wishlist`, `eshop_detail`
- MongoDB: `products`, `custom_catalog`

---

### Cafe Arcade Domain (31 endpoints, 0 covered)

**Frontend Pages:**
- CafeDashboard (`/cafe/dashboard`)
- StationsList (`/cafe/stations`)
- StationDetail (`/cafe/stations/:id`)
- SessionStart (`/cafe/sessions/start`)
- SessionActive (`/cafe/sessions`)
- SessionEnd (`/cafe/sessions/end/:id`)
- WalletBalance (`/cafe/wallets`)
- WalletRecharge (`/cafe/wallets/recharge`)
- GameLibrary (`/cafe/games`)
- PricingConfig (`/cafe/pricing`)
- CafePayments (`/cafe/payments`)
- MemberPlans (`/cafe/members`)
- CustomerTracker (`/cafe/tracker`)

**Backend Endpoints:**
```
/api/v1/cafe/customer/register
/api/v1/cafe/customer/lookup
/api/v1/cafe/customer/profile
/api/v1/cafe/wallet/balance
/api/v1/cafe/wallet/recharge
/api/v1/cafe/wallet/transactions
/api/v1/cafe/stations
/api/v1/cafe/stations/:id
/api/v1/cafe/stations/:id/status
/api/v1/cafe/sessions/
/api/v1/cafe/sessions/pause
/api/v1/cafe/sessions/resume
/api/v1/cafe/sessions/end
/api/v1/cafe/sessions/extend
/api/v1/cafe/sessions/active
/api/v1/cafe/pricing/rules
/api/v1/cafe/pricing/calculate
/api/v1/cafe/games
/api/v1/cafe/members/plans
/api/v1/cafe/members/upgrade
/api/v1/cafe/dashboard/overview
/api/v1/cafe/dashboard/revenue
/api/v1/cafe/dashboard/utilization
/api/v1/cafe/payments
/api/v1/cafe/payments/record
/api/v1/cafe/tracker/active
/api/v1/cafe/tracker/sessions/:id/fnb/orders
/api/v1/cafe/tracker/sessions/:id/wallet/topup
/api/v1/cafe/tracker/sessions/:id/close
/api/v1/cafe/gamers
```

**Data Sources:**
- PostgreSQL: `caf_platform_sessions`, `caf_platform_stations`, `caf_platform_wallets`, `caf_platform_wallet_transactions`, `caf_platform_games`, `caf_platform_member_plans`, `caf_platform_price_plans`, `caf_platform_session_leases`, `users_customer`

---

### Cafe FNB Domain (9 endpoints, 0 covered)

**Frontend Pages:**
- FnbMenuManagement (`/cafe-fnb/menu`)

**Backend Endpoints:**
```
/api/v1/cafe-fnb/menu
/api/v1/cafe-fnb/menu/items/
/api/v1/cafe-fnb/menu/items/:item_id
/api/v1/cafe-fnb/menu/items/:item_id/full
/api/v1/cafe-fnb/orders
/api/v1/cafe-fnb/orders/create
/api/v1/cafe-fnb/orders/:order_id
/api/v1/cafe-fnb/refunds
/api/v1/cafe-fnb/refunds/create
```

**Data Sources:**
- PostgreSQL: `cafe_fnb_detail`, `cafe_fnb_refunds`

---

### Products Domain (6 endpoints, 0 covered)

**Frontend Pages:**
- ProductsList (`/products`)
- ProductDetail (`/products/:prodId`)
- PortalEditor (`/products/portal-editor`)
- Presets (`/products/presets`)
- PreBuilts (`/products/pre-builts`)

**Backend Endpoints:**
```
/api/v1/products/catalog
/api/v1/products/catalog/:pk
/api/v1/products/tp-builds
/api/v1/products/tp-builds/:pk
/api/v1/products/presets
```

**Data Sources:**
- MongoDB: `products`, `custom_catalog`

---

### Tenant/Settings Domain (23 endpoints, 0 covered)

**Frontend Pages:**
- BusinessGroupsPage (`/settings/business-groups`)
- BrandsPage (`/settings/brands`)
- BranchesPage (`/settings/branches`)
- RolesPage (`/settings/roles`)
- UserAccessPage (`/settings/user-access`)
- EshopAdminManager (`/settings/eshop-admin`)

**Backend Endpoints:**
```
/api/v1/tenant/business-groups
/api/v1/tenant/business-groups/:id
/api/v1/tenant/divisions
/api/v1/tenant/divisions/:id
/api/v1/tenant/branches
/api/v1/tenant/branches/:id
/api/v1/tenant/bank-accounts
/api/v1/tenant/bank-accounts/:id
/api/v1/tenant/accessible/
/api/v1/tenant/current/
/api/v1/tenant/switch/
/api/v1/rbac/roles/
/api/v1/rbac/roles/:code/
/api/v1/rbac/roles/:code/perms/
/api/v1/rbac/roles/all_with_perms/
/api/v1/rbac/user-roles/
/api/v1/rbac/user-roles/:id/
/api/v1/rbac/user-permissions/
/api/v1/rbac/user-permissions/:id/
/api/v1/rbac/user-access/
/api/v1/rbac/user-access/:userid/
/api/v1/rbac/permissions/
```

**Data Sources:**
- PostgreSQL: `kungos_tenant_profile`, `tenant_business_groups`, `tenant_divisions`, `tenant_branches`, `tenant_division_addresses`, `tenant_bank_accounts`, `rbac_roles`, `rbac_permissions`, `rbac_role_permissions`, `rbac_user_roles`, `rbac_user_permissions`, `rbac_user_role_branches`, `users_user_tenant_context`

---

## 🏗️ **Platform Domain (plat)**

The `plat` domain provides platform-level utilities used across all domains:

| Module | Purpose | Used By |
|--------|---------|---------|
| `plat/django/filters.py` | FilterParserMixin for query param parsing | All viewsets |
| `plat/events/bus.py` | Event bus for domain events | Orders, Accounts |
| `plat/outbox/` | Outbox pattern for reliable messaging | All domains |
| `plat/pdf/export.py` | PDF/CSV export utilities | Accounts, Orders |
| `plat/shared/helpers.py` | Shared helper functions | All viewsets |
| `plat/shared/validation.py` | Input validation utilities | All viewsets |
| `plat/observability/` | Correlation ID, tenant context middleware | All requests |
| `plat/health/` | Health check endpoints | All domains |

**Note:** These are infrastructure components, not API endpoints. They support the domain endpoints but are not tested in the hydration test.

---

## 📋 **Handoff Document Gaps**

### Missing Sections

1. ❌ **Inventory Domain** — 18 endpoints, 8 frontend pages, 7 PostgreSQL tables
2. ❌ **Eshop Domain** — 9 endpoints, data from PostgreSQL + MongoDB
3. ❌ **Cafe Arcade Domain** — 31 endpoints, 13 frontend pages, 8 PostgreSQL tables
4. ❌ **Cafe FNB Domain** — 9 endpoints, 1 frontend page, 2 PostgreSQL tables
5. ❌ **Products Domain** — 6 endpoints, 5 frontend pages, MongoDB collections
6. ❌ **Tenant/Settings Domain** — 23 endpoints, 6 frontend pages, 13 PostgreSQL tables
7. ❌ **Missing Orders endpoints** — OrderCreate, OrderDetail, ServiceRequestsDetail
8. ❌ **Missing Accounts endpoints** — InvoiceCreate, InvoiceDetail, ITCGST, Ledgers, etc.
9. ❌ **Missing Shared endpoints** — DocGenerator, SMS, Counters, etc. (implemented but not documented)

### Missing Data Volumes

1. ❌ **Inventory tables** — `inventory_inventoryitem`, `inventory_inventorymovement`, `inventory_inventorystock`, `inventory_asset`, `inventory_stockaudit`, `inventory_indent`
2. ❌ **Cafe tables** — `caf_platform_sessions`, `caf_platform_stations`, `caf_platform_wallets`, `caf_platform_games`, `caf_platform_member_plans`, `caf_platform_price_plans`
3. ❌ **Cafe FNB tables** — `cafe_fnb_detail`, `cafe_fnb_refunds`
4. ❌ **Products collections** — `products`, `custom_catalog` volumes (MongoDB)
5. ❌ **Eshop tables** — `eshop_cart`, `eshop_wishlist`, `eshop_detail`
6. ❌ **HR/MongoDB** — `employee_attendance` volume

---

## 🎯 **Recommendations**

### High Priority
1. **Expand handoff to cover ALL domains** — Add Inventory, Eshop, Cafe Arcade, Cafe FNB, Products, Tenant/Settings
2. **Add missing Orders endpoints** — OrderCreate, OrderDetail, ServiceRequestsDetail
3. **Add missing Accounts endpoints** — InvoiceCreate, InvoiceDetail, ITCGST, Ledgers, etc.
4. **Document Shared domain endpoints** — DocGenerator, SMS, Counters (implemented but not in handoff)

### Medium Priority
5. **Add data volumes for all databases** — Inventory, Cafe, Products, HR
6. **Add tenant/settings endpoints** — BusinessGroups, Brands, Branches, Roles, UserAccess
7. **Add RBAC endpoints** — Roles, UserRoles, UserPermissions, UserAccess

### Low Priority
8. **Add legacy endpoint documentation** — Document which endpoints are legacy vs modern
9. **Add deprecation timeline** — When will legacy endpoints be removed?

---

## ✅ **Conclusion**

**Current handoff covers only 13% of frontend-backend endpoints (17/135).**

**Top priority should be:**
1. Expand handoff to cover ALL domains (Inventory, Eshop, Cafe Arcade, Cafe FNB, Products, Tenant/Settings)
2. Add missing Orders/Accounts/Shared endpoints
3. Add data volumes for all databases
4. Verify tenant filtering and RBAC for all endpoints

**The handoff is currently focused on the migrated domains (Orders partial, Teams partial, Vendors, Accounts partial) but misses 87% of the application.**

---

## 📊 **Detailed Domain Breakdown**

### Orders Domain (7 endpoints)
- ✅ Covered: estimates, tp-orders, in-store (list), orders (unified), service-requests
- ❌ Missing: OrderCreate (in-store POST), OrderDetail (in-store/:id), ServiceRequestsDetail

### Accounts Domain (19 endpoints)
- ✅ Covered: analytics, financials, inward-invoices (list), payment-vouchers, vendors, profit-loss, balance-sheet
- ❌ Missing: InvoiceCreate, InvoiceDetail, ITCGST, Ledgers, PurchaseOrders, BulkPayments, Revenue, Expenditure, Settlements, Export

### Teams Domain - HR (7 endpoints)
- ✅ Covered: employees, users
- ❌ Missing: emp-attendance, attendance-dashboard, edit-attendance, employees/salary, job-apps, employees (POST), access-levels

### Vendors Domain (2 endpoints)
- ✅ Covered: vendors (list)
- ❌ Missing: vendors/:pk

### Shared Domain (11 endpoints)
- ✅ Covered: home
- ❌ Missing: doc-generator, sms, misc, adminportal, counters, sms-headers (implemented but not documented)
- ❌ Missing: create-collection, get-collection, checklist

### Inventory Domain (18 endpoints)
- ❌ NOT COVERED — All 18 endpoints missing

### Eshop Domain (9 endpoints)
- ❌ NOT COVERED — All 9 endpoints missing

### Cafe Arcade Domain (31 endpoints)
- ❌ NOT COVERED — All 31 endpoints missing

### Cafe FNB Domain (9 endpoints)
- ❌ NOT COVERED — All 9 endpoints missing

### Products Domain (6 endpoints)
- ❌ NOT COVERED — All 6 endpoints missing

### Tenant/Settings Domain (23 endpoints)
- ❌ NOT COVERED — All 23 endpoints missing

---

**Audit report:** `/home/chief/llm-wiki/Kung_OS/reviews/frontend_backend_coverage_audit_2026-07-02.md`

**Want me to expand the handoff to cover all domains?**
