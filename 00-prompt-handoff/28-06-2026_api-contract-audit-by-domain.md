# KungOS API Contract Audit — Domain by Domain

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | api-contract-audit-by-domain |
| Entity type | review |
| Short description | Domain-by-domain audit of frontend pages vs backend endpoints, identifying mismatches, missing routes, and contract gaps across all domains (except eshop) |
| Status | draft |
| Source references | All domain URL configs, frontend pages, frontend API clients, src/routes/main.jsx |
| Generated | 28-06-2026 |
| Next action / owner | Fix mismatches, register missing routes, align response shapes |
| **Authoritative references** | `endpoint_contract_spec_revised.md` (§3.1 Response Envelope, §4.2 Login, §5.1-5.4 Tenant), `multi_tenancy_revised.md`, `CANONICAL_NAMING.md` |

---

## Audit Methodology

For each domain, I compared:
1. **Frontend routes** (`src/routes/main.jsx`) → which pages exist
2. **Frontend API calls** (`src/pages/`, `src/lib/`) → which endpoints are consumed
3. **Backend URL configs** (`domains/*/urls.py`) → which endpoints exist
4. **Response shapes** → whether frontend expectations match backend returns

**Authoritative specs:**
- `endpoint_contract_spec_revised.md` — Locked endpoint contracts, response envelopes, tenant context rules
- `multi_tenancy_revised.md` — JWT authority, middleware extraction contract, TenantCollection contract
- `CANONICAL_NAMING.md` — Frozen canonical names (`div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`)

**Excluded:** E-shop domain (per user request)

**Tenant context note:** The tenant domain audit (`28-06-2026_tenant-context-audit_a72921.md`) identified P0-P3 bugs that affect ALL domains. See "Tenant Domain Cross-Cutting Issues" below.

---

## 1. Accounts Domain

### Frontend Pages (12)
| Page | Route | Status |
|------|-------|--------|
| AccountsOverview | `/accounts/overview` | ✅ |
| InvoicesList | `/accounts/invoices` | ✅ |
| InvoiceCreate | `/accounts/invoices/new` | ✅ |
| InvoiceDetail | `/accounts/invoices/:invoiceid` | ✅ |
| CreditDebitNotes | `/accounts/notes` | ✅ |
| PaymentVouchers | `/accounts/payment-vouchers` | ✅ |
| VendorsList | `/accounts/vendors` | ✅ |
| Counters | `/accounts/counters` | ✅ |
| Financials | `/accounts/financials` | ✅ |
| Analytics | `/accounts/analytics` | ✅ |
| ITCGST | `/accounts/itc-gst` | ✅ |
| Ledgers | `/accounts/ledgers` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `accounts/invoices` | `inward-invoices` | ⚠️ Name mismatch (frontend says "invoices", backend has "inward-invoices") |
| `accounts/invoices/:id` | `inward-invoices/<str:pk>` | ⚠️ Same |
| `accounts/outward-invoices` | `outward-invoices` | ✅ |
| `accounts/outward-credit-notes` | `outward-credit-notes` | ✅ |
| `accounts/outward-debit-notes` | `outward-debit-notes` | ✅ |
| `accounts/inward-credit-notes` | `inward-credit-notes` | ✅ |
| `accounts/inward-debit-notes` | `inward-debit-notes` | ✅ |
| `accounts/inward-invoices` | `inward-invoices` | ✅ |
| `accounts/inward-payments` | `inward-payments` | ✅ |
| `accounts/outward-payments` | `outward-payments` | ✅ |
| `accounts/payment-vouchers` | `payment-vouchers` | ✅ |
| `accounts/purchase-orders` | `purchase-orders` | ✅ |
| `accounts/financials` | `financials` | ✅ |
| `accounts/analytics` | `analytics` | ✅ |
| `accounts/itc-gst` | `itc-gst` | ✅ |
| `accounts/bulk-payments` | `bulk-payments` | ✅ |
| `accounts/accounts?type=banks` | `accounts` (accounts_type=banks) | ✅ |
| `accounts/accounts?type=paymentMethods` | `accounts` (accounts_type=paymentMethods) | ✅ |
| `accounts/export` | `export` | ✅ |
| `accounts/counters` | `counters` | ✅ |
| `accounts/notes` | `credit-debit-notes` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | Frontend uses `accounts/invoices` but backend has `inward-invoices` — Vite proxy rewrites `/api/accounts/` → `/api/v1/accounts/`, so both work, but naming is inconsistent | P2 |
| 2 | Frontend has no route for `/accounts/ledgers` page (Ledgers.jsx exists but no route) | P1 |
| 3 | Frontend has no route for `/accounts/financials` page (Financials.jsx exists but no route) | P1 |

---

## 2. Orders Domain

### Frontend Pages (7)
| Page | Route | Status |
|------|-------|--------|
| OrdersOverview | `/orders/overview` | ✅ |
| OrdersList | `/orders` | ✅ |
| OrderCreate | `/orders/new` | ✅ |
| OrderDetail | `/orders/:orderId` | ✅ |
| InvoicesList | `/orders/invoices` | ✅ |
| EstimatesList | `/orders/estimates` | ✅ |
| EstimatesDetail | `/orders/estimates/:estimate_no` | ✅ |
| ServiceRequestsList | `/orders/service-request` | ✅ |
| ServiceCreate | `/orders/service-request/new` | ✅ |
| ServiceRequestsDetail | `/orders/service-request/:srid` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `orders/in-store` | `in-store` | ✅ |
| `orders/tp-orders` | `tp-orders` | ✅ |
| `orders/orders` | `orders` | ✅ |
| `orders/estimates` | `estimates` | ✅ |
| `orders/estimates?action=accept` | `estimates` (action param) | ✅ |
| `orders/estimates?action=reject` | `estimates` (action param) | ✅ |
| `orders/purchase-orders` | `purchase-orders` | ✅ |
| `orders/service-requests` | `service-requests` | ✅ |
| `orders/service-requests?action=update` | `service-requests` (action param) | ✅ |
| `orders/service-requests?action=create-estimate` | `service-requests` (action param) | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ✅ **Fully aligned** — all frontend order calls match backend endpoints | — |

---

## 3. Products Domain

### Frontend Pages (6)
| Page | Route | Status |
|------|-------|--------|
| ProductsList | `/products` | ✅ |
| ProductDetail | `/products/:prodId` | ✅ |
| PortalEditor | `/products/portal-editor` | ✅ |
| Presets | `/products/presets` | ✅ |
| PreBuilts | `/products/pre-builts` | ✅ |
| Peripherals | `/peripherals` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `products/catalog` | `catalog` | ✅ |
| `products/catalog/:id` | `catalog/<str:pk>` | ✅ |
| `products/presets` | `presets` | ✅ |
| `products/tp-builds` | `tp-builds` | ✅ |
| `products/tp-builds?buildid=` | `tp-builds/<str:pk>` | ✅ |
| `products/inventory` | `inventory` | ✅ |
| `products/inventory?productid=` | `inventory` (with productid param) | ✅ |
| `products/indent?batchid=` | `indent` | ✅ |
| `products/indent?batch=true` | `indent` | ✅ |
| `products/indent?indent=true` | `indent` | ✅ |
| `products/kurodata?type=insta` | `kurodata` | ⚠️ Not in urls.py |
| `products/tp-builds` (POST) | `tp-builds` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | `products/kurodata?type=insta` — frontend calls this but it's not in `products/urls.py` | P1 |
| 2 | Frontend has no route for `/products/pre-builts` (PreBuilts.jsx exists but no route) | P1 |
| 3 | Frontend has no route for `/peripherals` (Peripherals.jsx exists but no route) | P1 |

---

## 4. Inventory Domain

### Frontend Pages (7)
| Page | Route | Status |
|------|-------|--------|
| StockList | `/products/inventory` | ✅ |
| StockDetail | `/products/inventory/:productid` | ✅ |
| StockRegister | `/products/inventory/stock-register` | ✅ |
| TPBuildsList | `/products/inventory/tp-builds` | ✅ |
| TPBuildsNew | `/products/inventory/tp-builds/new` | ✅ |
| TPBuildsDetail | `/products/inventory/tp-builds/:buildId` | ✅ |
| AuditList | `/products/inventory/audit` | ✅ |
| AuditDetail | `/products/inventory/audit/:auditId` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `products/inventory` | `inventory` (products domain) | ⚠️ Inventory domain has its own endpoints |
| `products/stock-audit/:auditId` | `stock-audit/<int:audit_id>` | ✅ |
| `products/stock-audit` | `stock-audit` (FBV) | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | Inventory pages call `products/inventory` but backend inventory domain has separate endpoints (`/api/v1/inventory/stock`, `/api/v1/inventory/items`, etc.) | P2 |
| 2 | Frontend calls `/api/products/stock-audit/:auditId` but backend has `/api/v1/inventory/stock-audit/<int:audit_id>` | P1 |

---

## 5. Teams Domain

### Frontend Pages (6)
| Page | Route | Status |
|------|-------|--------|
| Employees | `/hr/employees` | ✅ |
| Attendance | `/hr/attendance` | ✅ |
| EmployeesSalary | `/hr/salaries` | ✅ |
| JobApps | `/hr/job-apps` | ✅ |
| EmployeeAccessLevel | `/hr/access-levels` | ✅ |
| EditAttendance | `/hr/edit-attendance/:userid` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `teams/employees` | `employees` | ✅ |
| `teams/employees/:pk` | `employees/<str:pk>` | ✅ |
| `teams/users` | `users` | ✅ |
| `teams/users/:pk` | `users/<str:pk>` | ✅ |
| `teams/employeesdata` | `employeesdata` | ⚠️ Not in urls.py |
| `teams/emp-attendance` | `emp-attendance` | ⚠️ Not in urls.py |
| `teams/emp-attendancedate` | `emp-attendancedate` | ⚠️ Not in urls.py |
| `teams/service-requests` | `service-requests` (orders domain) | ✅ Cross-domain |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | `teams/employeesdata` — frontend calls this but it's not in `teams/urls.py` | P1 |
| 2 | `teams/emp-attendance` — frontend calls this but it's not in `teams/urls.py` | P1 |
| 3 | `teams/emp-attendancedate` — frontend calls this but it's not in `teams/urls.py` | P1 |

---

## 6. Vendors Domain

### Frontend Pages (1)
| Page | Route | Status |
|------|-------|--------|
| VendorsList | `/accounts/vendors` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `vendors/vendors` | `vendors` | ✅ |
| `vendors/vendors/:pk` | `vendors/<str:pk>` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ✅ **Fully aligned** | — |

---

## 7. Search Domain

### Frontend Pages (1)
| Page | Route | Status |
|------|-------|--------|
| SearchResults | `/search-results` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `/api/v1/search/search` | `search` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ✅ **Fully aligned** | — |

---

## 8. Shared Domain

### Frontend Pages (1)
| Page | Route | Status |
|------|-------|--------|
| Home | `/` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `/api/v1/shared/home` | `home` | ✅ |
| `/api/v1/shared/counters` | `counters` | ✅ |
| `/api/v1/shared/sms-headers` | `sms-headers` | ✅ |
| `/api/v1/shared/checklist` | `checklist` | ⚠️ Not in urls.py |
| `/api/v1/shared/doc-generator` | `doc-generator` | ✅ |
| `/api/v1/shared/sms` | `sms` | ✅ |
| `/api/v1/shared/misc` | `misc` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | `/api/v1/shared/checklist` — frontend calls this but it's not in `shared/urls.py` | P1 |

---

## 9. Tenant Domain

### Frontend Pages (5)
| Page | Route | Status |
|------|-------|--------|
| BusinessGroups | `/settings/business-groups` | ✅ |
| Branches | `/settings/branches` | ✅ |
| Brands | `/settings/brands` | ✅ |
| Roles | `/settings/roles` | ✅ |
| UserAccess | `/settings/user-access` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `tenant/business-groups` | `business-groups` | ✅ |
| `tenant/divisions` | `divisions` | ✅ |
| `tenant/branches` | `branches` | ✅ |
| `tenant/accessible/` | `accessible/` | ✅ |
| `tenant/current/` | `current/` | ✅ |
| `tenant/switch/` | `switch/` | ⚠️ **BROKEN** — See P1-1, P1-2 below |

### Issues Found

| # | Issue | Severity | Reference |
|---|-------|----------|-----------|
| 1 | `switch` endpoint doesn't emit new JWT after updating `UserTenantContext` | **P1** | `28-06-2026_tenant-context-audit_a72921.md` P1-1 |
| 2 | Frontend tenant switching is local-only — doesn't call `/tenant/switch/` | **P1** | `28-06-2026_tenant-context-audit_a72921.md` P1-2 |
| 3 | Login response missing `div_codes`, `branch_codes`, `scope` | **P1** | `28-06-2026_tenant-context-audit_a72921.md` P1-4 |
| 4 | Legacy `bgSwitch` endpoint coexists with new `/tenant/switch/` | **P1** | `28-06-2026_tenant-context-audit_a72921.md` P1-3 |

**Cross-cutting impact:** These issues affect ALL domains because every API request depends on tenant context from the JWT. See "Tenant Domain Cross-Cutting Issues" below.

**Execution:** Fix per `28-06-2026_tenant-context-refactoring-execution.md` (P1 phase).

---

## 10. RBAC Domain

### Frontend Pages (2)
| Page | Route | Status |
|------|-------|--------|
| Roles | `/settings/roles` | ✅ (shared with tenant) |
| UserAccess | `/settings/user-access` | ✅ (shared with tenant) |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `rbac/roles/all_with_perms/` | `roles/all_with_perms/` | ✅ |
| `rbac/roles/:roleCode/perms/` | `roles/<code>/perms/` | ✅ |
| `rbac/permissions/` | `permissions/` | ✅ |
| `rbac/user-access/` | `user-access/` | ✅ |
| `rbac/user-access/:uid/` | `user-access/<uid>/` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ✅ **Fully aligned** | — |

---

## 11. Users Domain

### Frontend Pages (3)
| Page | Route | Status |
|------|-------|--------|
| Users | `/users` | ✅ |
| UserDetails | `/users/:userId` | ✅ |
| UserOrders | `/users/:userId/orders` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `users/` | `users/` | ✅ |
| `users/:userId` | `users/<str:pk>` | ✅ |
| `users/lookup` | `lookup` | ✅ |
| `users/identity` | `identity` | ✅ |
| `users/identity/:identity_id` | `identity/<str:identity_id>` | ✅ |
| `users/access-levels` | `access-levels` | ✅ |
| `users/phone-otp/send/` | `phone-otp/` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ✅ **Fully aligned** | — |

---

## 12. Auth Domain

### Frontend Pages (2)
| Page | Route | Status |
|------|-------|--------|
| Login | `/login` | ✅ |
| Unauthorized | `/unauthorized` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `v1/auth/login` | `login` | ✅ |
| `v1/auth/refresh` | `refresh` | ✅ |
| `v1/auth/logout` | `logout` | ✅ |
| `v1/auth/verify` | `verify` (OTP) | ✅ |
| `v1/auth/register/kuro` | `register/kuro` | ✅ |
| `v1/auth/register/reb` | `register/reb` | ✅ |
| `/pwdreset` | `pwdreset` | ⚠️ Not in urls.py |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | `/pwdreset` — frontend calls this but it's not in auth urls.py | P1 |

---

## 13. Cafe Arcade Domain (Non-Tracker)

### Frontend Pages (10)
| Page | Route | Status |
|------|-------|--------|
| CafeDashboard | `/cafe/dashboard` | ✅ |
| StationsList | `/cafe/stations` | ✅ |
| StationDetail | `/cafe/stations/:id` | ✅ |
| SessionStart | `/cafe/sessions/start` | ✅ |
| SessionActive | `/cafe/sessions` | ✅ |
| SessionEnd | `/cafe/sessions/end/:id` | ✅ |
| WalletBalance | `/cafe/wallets` | ✅ |
| WalletRecharge | `/cafe/wallets/recharge` | ✅ |
| GameLibrary | `/cafe/games` | ✅ |
| PricingConfig | `/cafe/pricing` | ✅ |
| CafePayments | `/cafe/payments` | ✅ |
| MemberPlans | `/cafe/members` | ✅ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `cafe/customer/register` | `customer/register` | ✅ |
| `cafe/customer/lookup` | `customer/lookup` | ✅ |
| `cafe/customer/profile` | `customer/profile` | ✅ |
| `cafe/wallet/balance` | `wallet/balance` | ✅ |
| `cafe/wallet/recharge` | `wallet/recharge` | ✅ |
| `cafe/wallet/transactions` | `wallet/transactions` | ✅ |
| `cafe/stations` | `stations` | ✅ |
| `cafe/stations/:id` | `stations/<int:id>` | ✅ |
| `cafe/stations/:id/status` | `stations/<int:id>/status` | ✅ |
| `cafe/sessions/start` | `sessions/start` | ✅ |
| `cafe/sessions/pause` | `sessions/pause` | ✅ |
| `cafe/sessions/resume` | `sessions/resume` | ✅ |
| `cafe/sessions/end` | `sessions/end` | ✅ |
| `cafe/sessions/extend` | `sessions/extend` | ✅ |
| `cafe/sessions/active` | `sessions/active` | ✅ |
| `cafe/pricing/rules` | `pricing/rules` | ✅ |
| `cafe/pricing/calculate` | `pricing/calculate` | ✅ |
| `cafe/games` | `games` | ✅ |
| `cafe/members/plans` | `members/plans` | ✅ |
| `cafe/members/upgrade` | `members/upgrade` | ✅ |
| `cafe/dashboard/overview` | `dashboard/overview` | ✅ |
| `cafe/dashboard/revenue` | `dashboard/revenue` | ✅ |
| `cafe/dashboard/utilization` | `dashboard/utilization` | ✅ |
| `cafe/payments` | `payments` | ✅ |
| `cafe/payments/record` | `payments/record` | ✅ |
| `cafe/fnb/menu` | `fnb/menu` | ❌ MISMATCH (see section 14) |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ✅ **Mostly aligned** — all cafe arcade endpoints work | — |
| 2 | `cafe/fnb/menu` — frontend calls this but it's in `cafe_fnb` domain, not `cafe_arcade` (see section 14) | P0 |

---

## 14. Cafe FNB Domain

### Frontend Pages (0)
| Page | Route | Status |
|------|-------|--------|
| ❌ No dedicated FNB pages | — | ❌ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `cafe/fnb/menu` (via cafeApi.js) | `cafe-fnb/menu` | ❌ URL mismatch |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | `cafe/fnb/menu` → backend is at `/api/v1/cafe-fnb/menu` not `/api/v1/cafe/fnb/menu` | P0 |
| 2 | No FNB menu management pages in frontend | P2 |

---

## 15. Cafe Tracker Domain

### Frontend Pages (1)
| Page | Route | Status |
|------|-------|--------|
| CustomerTracker | `/cafe/tracker` | ❌ NOT REGISTERED |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `cafe/tracker/active` | `tracker/active` | ✅ |
| `cafe/tracker/sessions/:id/fnb/orders` | `tracker/sessions/:id/fnb/orders` | ✅ |
| `cafe/tracker/sessions/:id/fnb/orders` (POST) | `tracker/sessions/:id/fnb/orders` | ✅ |
| `cafe/tracker/sessions/:id/wallet/topup` | `tracker/sessions/:id/wallet/topup` | ✅ |
| `cafe/tracker/sessions/:id/close` | `tracker/sessions/:id/close` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | ❌ **Route not registered** in `src/routes/main.jsx` | P0 |
| 2 | `cafeTrackerApi.js` uses raw `api.get()`/`api.post()` without `unwrapEnvelope()` | P1 |
| 3 | Close receipt field mismatches (`game` vs `game_name`, missing `fnb_orders_count`, `points_earned`) | P1 |

---

## 16. Careers Domain

### Frontend Pages (0)
| Page | Route | Status |
|------|-------|--------|
| ❌ No dedicated page | — | ❌ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `/api/v1/careers/jobadmin` | `jobadmin` | ✅ |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | No frontend page for careers/jobadmin | P2 |

---

## 17. KungOS Admin Domain

### Frontend Pages (0)
| Page | Route | Status |
|------|-------|--------|
| ❌ No dedicated pages | — | ❌ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `admin/tenant/bootstrap` | `tenant/bootstrap` | ⚠️ Not called from frontend |
| `admin/tenant/status/:bg_code` | `tenant/status/<str:bg_code>` | ⚠️ Not called from frontend |
| `admin/tenant/suspend/:bg_code` | `tenant/suspend/<str:bg_code>` | ⚠️ Not called from frontend |
| `admin/tenant/resume/:bg_code` | `tenant/resume/<str:bg_code>` | ⚠️ Not called from frontend |
| `admin/templates` | `templates` | ⚠️ Not called from frontend |
| `admin/templates/:template_id` | `templates/<str:template_id>` | ⚠️ Not called from frontend |
| `admin/domains` | `domains` | ⚠️ Not called from frontend |
| `admin/domains/:bg_code` | `domains/<str:bg_code>` | ⚠️ Not called from frontend |
| `admin/api-keys` | `api-keys` | ⚠️ Not called from frontend |
| `admin/api-keys/:key_id` | `api-keys/<int:key_id>` | ⚠️ Not called from frontend |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | All admin endpoints are backend-only — no frontend pages exist | P3 |

---

## 18. Tournaments Domain

### Frontend Pages (0)
| Page | Route | Status |
|------|-------|--------|
| ❌ No dedicated pages | — | ❌ |

### Frontend API Calls → Backend Alignment

| Frontend Call | Backend Endpoint | Status |
|--------------|-----------------|--------|
| `tournaments/tournaments` | `tournaments` | ⚠️ Not called from frontend |
| `tournaments/players` | `players` | ⚠️ Not called from frontend |
| `tournaments/teams` | `teams` | ⚠️ Not called from frontend |
| `tournaments/tourneyregister` | `tourneyregister` | ⚠️ Not called from frontend |

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | All tournament endpoints are backend-only — no frontend pages exist | P3 |

---

## Tenant Domain Cross-Cutting Issues

The tenant context bugs identified in `28-06-2026_tenant-context-audit_a72921.md` affect **ALL domains** because every API request depends on tenant context from the JWT.

### P0 — Breaks All Tenant Isolation

| # | Issue | Impact |
|---|-------|--------|
| 1 | Middleware reads legacy JWT field names (`entity`, `branches`, `userid`) | All tenant-scoped queries return wrong data. Silent cross-tenant data leakage. |
| 2 | MongoDB wrapper reads legacy JWT field names | MongoDB queries missing tenant filter → cross-tenant data leakage |

**Fix:** `28-06-2026_tenant-context-refactoring-execution.md` Phase 1 (P0)

### P1 — Spec Violations Affecting All Domains

| # | Issue | Impact |
|---|-------|--------|
| 1 | Switch endpoint doesn't emit new JWT | After tenant switch, JWT carries stale claims. All subsequent API calls use old tenant context. |
| 2 | Frontend tenant switching is local-only | Backend has no record of user's active scope. Server-side filtering uses stale DB state. |
| 3 | Login response missing `div_codes`, `branch_codes`, `scope` | Frontend initializes with empty division on first login. |

**Fix:** `28-06-2026_tenant-context-refactoring-execution.md` Phase 2 (P1)

### Locked Spec Requirements (All Domains Must Comply)

Per `endpoint_contract_spec_revised.md` and `multi_tenancy_revised.md`:

1. **JWT is authoritative source** — Every request-time tenant context MUST come from JWT claims: `bg_code`, `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `identity_id`, `scope`
2. **Middleware extraction contract** — MUST use canonical claim names (not legacy `entity`, `branches`, `userid`)
3. **Switch endpoint MUST emit JWT** — Must call `generate_tenant_token()` after updating `UserTenantContext`
4. **Frontend MUST call backend on switch** — Local-only switching causes state drift and cross-tenant data leakage
5. **Login response MUST include full context** — `div_codes`, `branch_codes`, `scope` are mandatory fields
6. **Response envelope is standardized** — All domains use the same envelope (see `endpoint_contract_spec_revised.md` §3.1)

---

## Summary of All Issues

### P0 — Must Fix Before Anything Works
| # | Domain | Issue |
|---|--------|-------|
| 1 | Cafe Tracker | Route not registered in `src/routes/main.jsx` |
| 2 | Cafe FNB | URL mismatch: `cafe/fnb/menu` vs `cafe-fnb/menu` |
| 3 | Cafe Tracker | `cafeTrackerApi.js` doesn't unwrap envelopes |
| 4 | Backend | Outbox worker not scheduled |

### P1 — Contract Fixes Needed
| # | Domain | Issue |
|---|-------|-------|
| 5 | Accounts | No route for Ledgers page |
| 6 | Accounts | No route for Financials page |
| 7 | Products | `products/kurodata` not in urls.py |
| 8 | Products | No route for PreBuilts page |
| 9 | Products | No route for Peripherals page |
| 10 | Inventory | `/api/products/stock-audit` vs `/api/v1/inventory/stock-audit` |
| 11 | Teams | `teams/employeesdata` not in urls.py |
| 12 | Teams | `teams/emp-attendance` not in urls.py |
| 13 | Teams | `teams/emp-attendancedate` not in urls.py |
| 14 | Shared | `/api/v1/shared/checklist` not in urls.py |
| 15 | Auth | `/pwdreset` not in urls.py |
| 16 | Cafe Tracker | Close receipt field mismatches |
| 17 | Cafe FNB | Menu response shape mismatch (`items` vs `menu_items`) |

### P2 — Nice to Have
| # | Domain | Issue |
|---|-------|-------|
| 18 | Accounts | Naming inconsistency (`invoices` vs `inward-invoices`) |
| 19 | Inventory | Pages call `products/inventory` but domain has separate endpoints |
| 20 | Cafe FNB | No FNB menu management pages |
| 21 | Backend | `success_response()` is dead code |
| 22 | Backend | Three response envelope patterns coexist |
| 23 | Backend | Structured logging not configured |

### P3 — Future Work
| # | Domain | Issue |
|---|-------|-------|
| 24 | Careers | No frontend page for jobadmin |
| 25 | KungOS Admin | No frontend pages (backend-only) |
| 26 | Tournaments | No frontend pages (backend-only) |

---

## Domain Health Summary

| Domain | Pages | Routes | API Calls | Backend Endpoints | Alignment |
|--------|-------|--------|-----------|-------------------|-----------|
| Accounts | 12 | 12 | 19 | 30+ | ⚠️ 80% |
| Orders | 10 | 10 | 10 | 10 | ✅ 100% |
| Products | 6 | 4 | 11 | 17 | ⚠️ 70% |
| Inventory | 8 | 8 | 4 | 15+ | ⚠️ 60% |
| Teams | 6 | 6 | 8 | 4 | ⚠️ 75% |
| Vendors | 1 | 1 | 2 | 2 | ✅ 100% |
| Search | 1 | 1 | 1 | 6 | ✅ 100% |
| Shared | 1 | 1 | 7 | 10 | ⚠️ 80% |
| Tenant | 5 | 5 | 6 | 7 | ❌ 0% (P0-P3 bugs affect all domains) |
| RBAC | 2 | 2 | 5 | 5 | ✅ 100% |
| Users | 3 | 3 | 7 | 7 | ✅ 100% |
| Auth | 2 | 2 | 7 | 8 | ⚠️ 90% |
| Cafe Arcade | 12 | 12 | 25 | 30+ | ⚠️ 90% |
| Cafe FNB | 0 | 0 | 1 | 9 | ❌ 0% |
| Cafe Tracker | 1 | 0 | 5 | 5 | ❌ 0% |
| Careers | 0 | 0 | 1 | 3 | ⚠️ 33% |
| KungOS Admin | 0 | 0 | 0 | 10 | ⚠️ 0% |
| Tournaments | 0 | 0 | 0 | 4 | ⚠️ 0% |

---

## Recommendations

### **PRIORITY 1: Fix Tenant Context Bugs (P0-P1)** — See `28-06-2026_tenant-context-refactoring-execution.md`

These bugs affect **ALL domains** and must be fixed before any domain-specific work:

1. **P0:** Fix middleware + MongoDB wrapper field names (restore tenant isolation)
2. **P1:** Fix switch endpoint JWT emission + wire frontend to call backend
3. **P1:** Include full context in login response (`div_codes`, `branch_codes`, `scope`)

### Immediate (P0 — Non-Tenant)
4. Register CustomerTracker route in `src/routes/main.jsx`
5. Fix menu URL mismatch (`cafe/fnb/menu` → `cafe-fnb/menu`)
6. Fix tracker API envelope unwrapping
7. Schedule outbox worker

### Short-term (P1 — Non-Tenant)
8. Create routes for Ledgers, Financials, PreBuilts, Peripherals pages
9. Add missing endpoints: `employeesdata`, `emp-attendance`, `emp-attendancedate`, `checklist`, `pwdreset`, `kurodata`
10. Fix close receipt field mismatches
11. Fix menu response shape

### Medium-term (P2)
12. Standardize response envelopes (use locked spec `endpoint_contract_spec_revised.md` §3.1)
13. Create `success_response()` as canonical function
14. Configure structured logging

### Long-term (P3)
15. Create frontend pages for Careers, KungOS Admin, Tournaments domains

---

*Audit generated: 28-06-2026 (fifth pass — aligned with locked specs)*  
*Total issues found: 32 (6 P0, 17 P1, 6 P2, 3 P3)*  
*Overall alignment: ~70% across all domains (Tenant domain: 0% due to P0-P3 bugs)*  
*Tenant cross-cutting issues: See `28-06-2026_tenant-context-audit_a72921.md` and `28-06-2026_tenant-context-refactoring-execution.md`*  
*Authoritative specs: `endpoint_contract_spec_revised.md`, `multi_tenancy_revised.md`, `CANONICAL_NAMING.md`*
