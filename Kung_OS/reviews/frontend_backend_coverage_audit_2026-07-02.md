# Frontend-Backend Coverage Audit

**Date:** 2026-07-02  
**Status:** ⚠️ **GAPS IDENTIFIED**  

---

## 🎯 **Audit Objective**

Verify that all frontend pages have corresponding backend endpoints and are covered in the runtime data hydration test handoff.

---

## 📊 **Coverage Summary**

| Domain | Frontend Pages | Backend Endpoints | Handoff Coverage | Status |
|--------|---------------|-------------------|------------------|--------|
| **Orders** | 6 pages | 7 endpoints | 4/7 | ⚠️  Missing 3 |
| **Accounts** | 12 pages | 19 endpoints | 9/19 | ⚠️  Missing 10 |
| **Teams** | 4 pages | 4 endpoints | 2/4 | ⚠️  Missing 2 |
| **Vendors** | 1 page | 2 endpoints | 1/2 | ✅ Complete |
| **Shared** | 1 page | 11 endpoints | 1/11 | ⚠️  Missing 10 |
| **Inventory** | 6 pages | 8 endpoints | 0/8 | ❌ Not covered |
| **Cafe** | 14 pages | 12 endpoints | 0/12 | ❌ Not covered |
| **Tenant/Settings** | 6 pages | 5 endpoints | 0/5 | ❌ Not covered |
| **Products** | 5 pages | 6 endpoints | 0/6 | ❌ Not covered |
| **HR** | 5 pages | 3 endpoints | 0/3 | ❌ Not covered |

**Total:** 60 frontend pages, 77 backend endpoints, 17/77 covered (22%)

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
| VendorsListNew | `/api/v1/accounts/vendors` | ✅ Covered (redirects to /vendors/vendors) |
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

### Teams Domain (2/4 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| Employees | `/api/v1/teams/employees` | ✅ Covered |
| Users | `/api/v1/teams/users` | ✅ Covered |
| Attendance | `/api/v1/teams/emp-attendance` | ❌ Not in handoff |
| EditAttendance | `/api/v1/teams/emp-attendancedate` | ❌ Not in handoff |

### Vendors Domain (1/2 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| VendorsListNew | `/api/v1/vendors/vendors` | ✅ Covered |
| VendorDetail | `/api/v1/vendors/vendors/:pk` | ❌ Not in handoff |

### Shared Domain (1/11 endpoints)

| Frontend Page | Backend Endpoint | Handoff Coverage |
|--------------|------------------|------------------|
| Home | `/api/v1/shared/home` | ✅ Covered |
| DocGenerator | `/api/v1/shared/doc-generator` | ❌ Not in handoff |
| SMS | `/api/v1/shared/sms` | ❌ Not in handoff |
| Misc | `/api/v1/shared/misc` | ❌ Not in handoff |
| CreateCollection | `/api/v1/shared/create-collection` | ❌ Not in handoff |
| GetCollection | `/api/v1/shared/get-collection` | ❌ Not in handoff |
| AdminPortal | `/api/v1/shared/adminportal` | ❌ Not in handoff |
| Counters | `/api/v1/shared/counters` | ❌ Not in handoff |
| SMSHeaders | `/api/v1/shared/sms-headers` | ❌ Not in handoff |
| Analytics | `/api/v1/shared/analytics` | ✅ Covered (but this is accounts/analytics alias) |
| Checklist | `/api/v1/shared/checklist` | ❌ Not in handoff |

---

## ❌ **NOT Covered in Handoff**

### Inventory Domain (8 endpoints, 0 covered)

| Frontend Page | Backend Endpoint |
|--------------|------------------|
| StockList | `/api/v1/inventory/stock` |
| StockDetail | `/api/v1/inventory/:productid` |
| StockRegisterPage | `/api/v1/inventory/stock-register` |
| AuditList | `/api/v1/inventory/audit` |
| AuditDetail | `/api/v1/inventory/audit/:auditId` |
| TPBuildsList | `/api/v1/products/tp-builds` |
| TPBuildsDetail | `/api/v1/products/tp-builds/:buildId` |
| TPBuildsNew | `/api/v1/products/tp-builds/new` |

### Cafe Domain (12 endpoints, 0 covered)

| Frontend Page | Backend Endpoint |
|--------------|------------------|
| CafeDashboard | `/api/v1/cafe/dashboard` |
| StationsList | `/api/v1/cafe/stations` |
| StationDetail | `/api/v1/cafe/stations/:id` |
| SessionStart | `/api/v1/cafe/sessions/start` |
| SessionActive | `/api/v1/cafe/sessions` |
| SessionEnd | `/api/v1/cafe/sessions/end/:id` |
| WalletBalance | `/api/v1/cafe/wallets` |
| WalletRecharge | `/api/v1/cafe/wallets/recharge` |
| GameLibrary | `/api/v1/cafe/games` |
| PricingConfig | `/api/v1/cafe/pricing` |
| CafePayments | `/api/v1/cafe/payments` |
| MemberPlans | `/api/v1/cafe/members` |
| CustomerTracker | `/api/v1/cafe/tracker` |
| FnbMenuManagement | `/api/v1/cafe-fnb/menu` |

### Tenant/Settings Domain (5 endpoints, 0 covered)

| Frontend Page | Backend Endpoint |
|--------------|------------------|
| BusinessGroupsPage | `/api/v1/tenant/business-groups` |
| BrandsPage | `/api/v1/tenant/brands` |
| BranchesPage | `/api/v1/tenant/branches` |
| RolesPage | `/api/v1/rbac/roles` |
| UserAccessPage | `/api/v1/rbac/user-access` |
| EshopAdminManager | `/api/v1/tenant/eshop-admin` |

### Products Domain (6 endpoints, 0 covered)

| Frontend Page | Backend Endpoint |
|--------------|------------------|
| ProductsList | `/api/v1/products` |
| ProductDetail | `/api/v1/products/:prodId` |
| PortalEditor | `/api/v1/products/portal-editor` |
| Presets | `/api/v1/products/presets` |
| PreBuilts | `/api/v1/products/pre-builts` |
| PurchaseOrdersNew | `/api/v1/products/procurement/po` |
| CreatePO | `/api/v1/products/procurement/po/new` |
| IndentList | `/api/v1/products/procurement/indents` |

### HR Domain (3 endpoints, 0 covered)

| Frontend Page | Backend Endpoint |
|--------------|------------------|
| Attendance | `/api/v1/teams/emp-attendance` |
| Dashboard (HR) | `/api/v1/teams/attendance-dashboard` |
| EditAttendance | `/api/v1/teams/edit-attendance/:userid` |
| EmployeesSalary | `/api/v1/teams/employees/salary` |
| JobApps | `/api/v1/careers/job-apps` |
| CreateEmp | `/api/v1/teams/employees` (POST) |
| EmployeeAccessLevel | `/api/v1/rbac/access-levels` |

---

## 📋 **Handoff Document Gaps**

### Missing Sections

1. ❌ **Inventory Domain** — No endpoints or pages documented
2. ❌ **Cafe Domain** — No endpoints or pages documented
3. ❌ **Tenant/Settings Domain** — No endpoints or pages documented
4. ❌ **Products Domain** — No endpoints or pages documented
5. ❌ **HR Domain** — No endpoints or pages documented
6. ❌ **Orders Create/Detail** — Missing OrderCreate and OrderDetail pages
7. ❌ **Accounts Create/Detail** — Missing InvoiceCreate, InvoiceDetail, etc.
8. ❌ **Shared Utilities** — Missing doc-generator, sms, counters, etc.

### Missing Data Volumes

1. ❌ **Inventory tables** — `inventory_inventoryitem`, `inventory_inventorymovement`, etc.
2. ❌ **Cafe tables** — `caf_platform_sessions`, `caf_platform_stations`, etc.
3. ❌ **Products collections** — `products`, `custom_catalog` volumes
4. ❌ **HR tables** — `employee_attendance` (MongoDB) volume

---

## 🎯 **Recommendations**

### High Priority
1. **Expand handoff to cover all domains** — Add Inventory, Cafe, Tenant, Products, HR
2. **Add missing Orders endpoints** — OrderCreate, OrderDetail, ServiceRequestsDetail
3. **Add missing Accounts endpoints** — InvoiceCreate, InvoiceDetail, ITCGST, Ledgers, etc.
4. **Add missing Shared endpoints** — DocGenerator, SMS, Counters, etc.

### Medium Priority
5. **Add data volumes for all databases** — Inventory, Cafe, Products, HR
6. **Add tenant/settings endpoints** — BusinessGroups, Brands, Branches, Roles, UserAccess
7. **Add HR endpoints** — Attendance, Salaries, JobApps

### Low Priority
8. **Add legacy endpoint documentation** — Document which endpoints are legacy vs modern
9. **Add deprecation timeline** — When will legacy endpoints be removed?

---

## ✅ **Conclusion**

**Current handoff covers only 22% of frontend-backend endpoints.**

**Top priority should be:**
1. Expand handoff to cover ALL domains (Inventory, Cafe, Tenant, Products, HR)
2. Add missing Orders/Accounts/Shared endpoints
3. Add data volumes for all databases
4. Verify tenant filtering and RBAC for all endpoints

**The handoff is currently focused on the migrated domains (Orders, Teams, Vendors, Accounts partial) but misses 78% of the application.**
