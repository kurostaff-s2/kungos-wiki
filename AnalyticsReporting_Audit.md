# Analytics & Reporting Endpoints — Audit Report

## 1. Endpoint Inventory

### 1.1 `GET /shared/analytics` — Dashboard Analytics
**Frontend:** `Accounts/Analytics.jsx` (primary), `Home.jsx` (partial)
**Backend:** `teams/analytics.py:analytics()` → 212-line FBV

**Frontend expects:**
```js
{
  totalOrders, totalRevenue, totalExpenses, profitMargin,
  avgInvoiceValue, daysToPay, overdueAmount,
  totalEstimates, totalTPOrders,
  statusBreakdown: { Paid: N, Pending: N, ... },
  chartData: [{ period, revenue, expenses, orders }],
  paymentTrend: [{ period, paid, pending }],
  vendors: [{ name, amount, percentage }],
  monthlyData: [...],
  period
}
```

**Backend returns:** ✅ Matches frontend contract exactly.

**Data sources (5 collections):**
- `inwardpayments` — primary revenue data
- `paymentVouchers` — expenses
- `estimates` — estimate counts
- `tporders` — TP order counts
- `purchaseorders` — vendor spend analysis

**Query params:** `period` (daily/weekly/monthly/quarterly/yearly), `division`, `branch`

---

### 1.2 `GET /accounts/financials` — Financial Reports
**Frontend:** `Accounts/Financials.jsx`
**Backend:** `teams/financial.py:financials()` → 116-line FBV

**Frontend expects:** Array of `{ date, description, category, type: "income"|"expense", amount, reference }`

**Backend returns:** Array of `{ "2024-Jan": { invoice_type: total, ...total }, "CurrentFin-year": {...}, "LastFin-year": {...} }`

**⚠️ CRITICAL MISMATCH:** Frontend expects flat transaction list with `type: "income"|"expense"`. Backend returns monthly aggregated dict with invoice types as keys. The frontend's `summary` useMemo will produce all zeros because no record has `type === 'income'` or `type === 'expense'`.

**Data sources:**
- `inwardInvoices` — via `financial_totals()` aggregation pipeline (last 6 months)
- `inwardInvoices` — via `payment_financials()` aggregation pipeline (payment vouchers, last 6 months)
- `inwardInvoices` — via `past_present_fin_totals()` (FY totals)

**Query params:** `period` (frontend sends but backend ignores)

---

### 1.3 `GET /accounts/itc-gst` — GST Compliance
**Frontend:** `Accounts/ITCGST.jsx`
**Backend:** `teams/financial.py:itc_gst()` → 60-line FBV

**Frontend expects:** Array of `{ invoice_no, gstin, invoice_date, igst, cgst, sgst, itc_amount, gst_amount, utilized, status }`

**Backend returns:** ✅ Matches frontend contract.

**Data sources:**
- `inwardInvoices` — invoices from current period

**Query params:** `period` (monthly/quarterly/yearly)

---

### 1.4 `GET /accounts/revenue` — Revenue (Sales)
**Frontend:** Not directly called. Used via export: `accounts/outwardinvoices`

**Backend:** `teams/financial.py:sales()` → calls `sales_func()` → 100-line aggregation

**Backend returns:** Dict of 21 keys: `invoice_curmonth`, `credit_curmonth`, `debit_curmonth`, `invoice_lastmonth`, etc. (3 data types × 7 time periods)

**⚠️ DATA SOURCE BUG:** `sales_func()` queries `outwardDebitNotes` collection, not `outwardInvoices`. This is likely a legacy naming issue — the collection may contain all outward documents.

**Query params:** None (hardcoded time periods)

---

### 1.5 `GET /accounts/expenditure` — Expenditure (Purchases)
**Frontend:** Not directly called. Used via export: `accounts/inwardinvoices`

**Backend:** `teams/financial.py:purchases()` → calls `purchases_func()` → 100-line aggregation

**Backend returns:** Dict of 21 keys (same structure as sales): invoice/credit/debit × current/last month/year/quarter

**Data sources:**
- `inwardInvoices` collection

**Query params:** None (hardcoded time periods)

---

### 1.6 `GET /accounts/bulk-payments` — Bulk Payments
**Frontend:** `BulkPayments.jsx` — calls `accounts/inward-invoices?foradmin=true` (NOT bulk-payments)

**Backend:** `teams/financial.py:bulk_payments()` → 15-line FBV

**⚠️ UNUSED:** The `accounts/bulk-payments` endpoint is never called by the frontend. The BulkPayments page uses `accounts/inward-invoices` directly.

---

### 1.7 Export Endpoints
**Frontend:** `Financials.jsx` export dialog → `accounts/${exportType}?duration=${exportDuration}`

| exportType | Frontend path | Backend route | Status |
|-----------|---------------|---------------|--------|
| `financials` | `accounts/financials?duration=...` | `accounts/financials` (FinancialsViewSet) | ⚠️ Duration param ignored |
| `inwardinvoices` | `accounts/inwardinvoices?duration=...` | `accounts/inward-invoices` (hyphen mismatch) | ❌ Path mismatch |
| `outwardinvoices` | `accounts/outwardinvoices?duration=...` | `accounts/outward-invoices` (hyphen mismatch) | ❌ Path mismatch |
| `inwardpayments` | `accounts/inwardpayments?duration=...` | `accounts/inward-payments` (hyphen mismatch) | ❌ Path mismatch |

**⚠️ The export paths don't match:** Frontend sends `accounts/inwardinvoices` (no hyphen), backend expects `accounts/inward-invoices` (hyphen). Export will 404.

**Backend also has:** `accounts/export/inward-invoices`, `accounts/export/outward-invoices`, `accounts/export/inward-payments` — these are never called by the frontend.

---

### 1.8 `GET /cafe/dashboard/revenue` — Cafe Revenue
**Frontend:** `cafe/CafeDashboard.jsx` → `cafeApi.dashboardRevenue`
**Backend:** `domains/cafe/viewsets.py` — needs implementation

**⚠️ MISSING:** No backend implementation exists yet. Cafe domain is not fully wired.

---

## 2. Issues Summary

### Critical (breaks frontend)
| # | Issue | Impact |
|---|-------|--------|
| C1 | `financials` returns monthly dict, frontend expects transaction list | Financials page shows ₹0 for all stats |
| C2 | Export paths: frontend sends `inwardinvoices`, backend expects `inward-invoices` | Export button 404s |
| C3 | `sales_func()` queries `outwardDebitNotes` not `outwardInvoices` | Revenue data may be wrong |

### High (wrong data or missing)
| # | Issue | Impact |
|---|-------|--------|
| H1 | `financials` ignores `period` param | Period selector does nothing |
| H2 | `bulk-payments` endpoint never called | Dead code |
| H3 | `accounts/analytics` duplicates `shared/analytics` | Confusion, potential inconsistency |
| H4 | Cafe `dashboard/revenue` not implemented | Cafe dashboard breaks |

### Medium (quality)
| # | Issue | Impact |
|---|-------|--------|
| M1 | `analytics` has `sys.stderr.write` debug logs | Production noise |
| M2 | `analytics` has hardcoded `days_to_pay = 15` | Misleading metric |
| M3 | `itc_gst` tax extraction is naive (assumes 28%=IGST, 18%/2=CGST/SGST) | Wrong for non-standard rates |
| M4 | `getfilters()` uses `$substr` on date strings — fragile | Breaks on non-ISO dates |
| M5 | `sales_func` / `purchases_func` make 21 separate aggregation queries each | Slow, could be 1 query |
| M6 | No pagination on analytics/reporting endpoints | Memory issues with large datasets |
| M7 | `Inventory/Overview.jsx` has hardcoded static data | Doesn't reflect real inventory |

### Low (cleanup)
| # | Issue | Impact |
|---|-------|--------|
| L1 | `analytics` fallback data in frontend uses `Math.random()` | Inconsistent charts |
| L2 | `financials` has broad `except Exception` → returns `[]` silently | Hard to debug |
| L3 | `itc_gst` `utilized` always 0 | No utilization tracking |

---

## 3. Missing Critical Functions

### 3.1 Profit & Loss Statement
No dedicated P&L endpoint. `financials` comes closest but returns wrong format. A proper P&L needs:
- Revenue by category (sales, services, other)
- COGS
- Gross profit
- Operating expenses (by department)
- Net profit
- Year-over-year comparison

### 3.2 Balance Sheet
No balance sheet endpoint. Needs:
- Assets (current + fixed)
- Liabilities (current + long-term)
- Equity
- Asset register integration (depreciation)

### 3.3 Cash Flow Statement
No cash flow endpoint. Needs:
- Operating activities
- Investing activities
- Financing activities
- Net cash position

### 3.4 Inventory Valuation
`Inventory/Overview.jsx` is hardcoded. Needs:
- Total stock value (by branch/division)
- Stock turnover ratio
- Slow-moving/obsolete items
- Stock adjustment history

### 3.5 Customer Analytics
No customer-facing analytics. Needs:
- Top customers by revenue
- Customer acquisition/retention
- Average order value by customer segment
- Customer lifetime value

### 3.6 Vendor Analytics
`analytics` has top vendors by spend but no dedicated endpoint. Needs:
- Vendor performance (on-time delivery, quality)
- Payment terms compliance
- Vendor concentration risk
- Spend by category

### 3.7 Order Fulfillment Metrics
No order analytics. Needs:
- Order processing time
- Fulfillment rate
- Return/cancellation rate
- Backorder tracking

### 3.8 Employee Analytics
No HR analytics beyond basic counts. Needs:
- Attendance trends
- Leave utilization
- Salary cost by department
- Turnover rate

---

## 4. Frontend Data Contracts (Recharts + DataTable + shadcn/ui)

All reporting endpoints must produce data shapes the frontend components consume directly.
No client-side transformation should be needed beyond basic formatting.

### 4.1 Recharts — Chart Data Contracts

Frontend uses **Recharts v3** with `dataKey` fields. Backend must produce arrays of objects with these exact keys.

| Component | Page | Required `dataKey` Fields | Source Endpoint |
|-----------|------|--------------------------|-----------------|
| `<BarChart>` (Revenue vs Expenses) | `Analytics.jsx` | `{ period, revenue, expenses, orders }` | `shared/analytics` → `chartData` |
| `<AreaChart>` (Payment Trends) | `Analytics.jsx` | `{ period, paid, pending }` | `shared/analytics` → `paymentTrend` |
| Vendor bars | `Analytics.jsx` | `{ name, amount, percentage }` | `shared/analytics` → `vendors` |

**Period label format by period type:**
- `daily` → `"14:00"` (HH:MM blocks)
- `weekly` → `"Mon 15"` (Day DD)
- `monthly` → `"Jan"` (3-letter month)
- `quarterly` → `"Q1 2024"` (Q# YYYY)
- `yearly` → `"2024"` (YYYY)

### 4.2 DataTable — Table Data Contracts

Frontend uses **TanStack Table** via `@/components/common/DataTable` with `accessorKey` columns.

| Page | `accessorKey` Fields | Source Endpoint | Status |
|------|---------------------|-----------------|--------|
| `Financials.jsx` | `{ date, description, category, type: "income"\|"expense", amount, reference }` | `accounts/financials` | 🔴 MISMATCH — backend returns monthly dict |
| `ITCGST.jsx` | `{ invoice_no, gstin, invoice_date, igst, cgst, sgst, itc_amount, status }` | `accounts/itc-gst` | ✅ Matches |

### 4.3 StatCard — KPI Data Contracts

Frontend uses `@/components/common/StatCard` with `{ title, value, change, changeLabel, trend, icon }`.

| Page | KPI Fields | Source |
|------|-----------|--------|
| `Analytics.jsx` | `totalRevenue`, `totalExpenses`, `profitMargin`, `avgInvoiceValue`, `daysToPay`, `overdueAmount` | `shared/analytics` → top-level keys |
| `Financials.jsx` | `totalIncome`, `totalExpenses`, `netProfit`, `avgTransaction` | Computed from DataTable rows via `useMemo` |
| `ITCGST.jsx` | `totalITC`, `utilizedITC`, `availableITC`, `gstLiability`, `netPayable` | Computed from DataTable rows via `useMemo` |

### 4.4 PageSection — Collapsible Sections

Frontend uses `@/components/common/PageSection` with `{ title, description, defaultOpen }`.
All reporting pages use this for collapsible data sections.

### 4.5 Badge — Status Indicators

Frontend uses `@/components/ui/Badge` with variants: `success`, `warning`, `destructive`, `info`, `outline`, `secondary`.

| Page | Badge mapping |
|------|---------------|
| `Financials.jsx` | `type === 'income'` → `success`, `type === 'expense'` → `destructive` |
| `ITCGST.jsx` | `status === 'Claimed'` → `success`, `'Pending'` → `warning`, `'Rejected'` → `destructive` |

### 4.6 Currency Formatting

All monetary values use `toLocaleString('en-IN')` with `₹` prefix.
Backend should return **numeric values** (not formatted strings) so frontend can format consistently.

### 4.7 Date Formatting

- ISO dates (`2024-03-15T...`) → `new Date(row.original.date).toLocaleDateString('en-IN')`
- Backend should return **ISO strings** for all date fields
- Frontend handles locale-specific formatting

---

## 5. Reporting on Existing Foundations — Revised Plan

### 5.1 Existing KungOS v2 Primitives (already built)

KungOS v2 already provides the infrastructure. Reporting should **plug into** these, not recreate them.

| Primitive | Location | What it does | Reporting uses it for |
|-----------|----------|-------------|----------------------|
| `resolve_access(request)` | `backend/auth_utils.py:80` | Full tenant context: user, bg, switchgroup, access_dict | Single tenant resolution per request |
| `resolve_minimal(request)` | `backend/auth_utils.py:128` | Lightweight: bg + switchgroup only | Read-only reports without access checks |
| `get_collection(name, bg_code, division, branch)` | `backend/utils.py:261` | MongoDB collection + tenant filter dict | All data access, automatic bg/division/branch scoping |
| `find_all(name, filters, bg_code, division, branch, sort, limit, skip)` | `backend/utils.py:301` | Query helper with tenant filtering + pagination | Paginated report results |
| `BusinessGroup` model | `tenant/models.py:16` | BG config: db_name, brand, settings | TenantConfig-driven defaults |
| `Division` model | `tenant/models.py:100` | Division hierarchy, cascade codes | Division scoping |
| `Branch` model | `tenant/models.py:185` | Branch details | Branch scoping |
| `/api/v1/` routing | `backend/urls.py` | Domain-based URL routing | All reporting endpoints |
| `CookieJWTAuthentication` | `users/cookie_auth.py` | Cookie-based JWT auth | Auth on all endpoints |
| `check_access()` / `check_write_access()` | `backend/auth_utils.py` | Permission checks by codename | Report access control |

### 5.2 What's Missing (thin layer on top of existing)

| Gap | Solution | Plugs into |
|-----|----------|------------|
| Period/duration parsing | `backend/periods.py` — `PeriodParser` utility class | Standalone utility, no new infrastructure |
| Standardized response shape | `backend/response_utils.py` — `reporting_response(data, meta)` | Existing `error_response()` pattern |
| Correlation IDs | `backend/middleware.py` — `CorrelationIdMiddleware` | Existing Django middleware stack |
| Structured logging | `backend/logging.py` — `structlog` config | Existing `settings.py` LOGGING config |
| Reporting ViewSet mixin | `backend/reporting_base.py` — `ReportingViewSet` | Existing `GenericViewSet` pattern |
| TenantConfig for reporting | Extend `BusinessGroup` model or add `reporting_config` field | Existing tenant model |

### 5.3 Proposed: `ReportingViewSet` (thin mixin, not greenfield)

```python
# backend/reporting_base.py — plugs into existing primitives

class ReportingViewSet(viewsets.GenericViewSet):
    """Thin mixin for reporting endpoints.

    Plugs into existing KungOS v2 primitives:
      - resolve_access() for tenant context
      - get_collection() for data access
      - CookieJWTAuthentication for auth
      - check_access() for permissions

    Adds only:
      - PeriodParser for date range filtering
      - reporting_response() for {data, meta} envelope
      - Correlation ID injection
      - Structured logging
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    # Override per-endpoint
    COLLECTIONS = []  # list of collection names
    DEFAULT_PERIOD = 'monthly'
    ALLOWED_PERIODS = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']

    def initial(self, request, *args, **kwargs):
        """Resolve tenant context once (uses existing resolve_access)."""
        super().initial(request, *args, **kwargs)
        self.tenant_context = resolve_access(request)  # existing primitive
        self.correlation_id = request.META.get('HTTP_X_CORRELATION_ID') or uuid4().hex

    def get_collection(self, name):
        """Use existing get_collection() with resolved tenant context."""
        return get_collection(
            name,
            bg_code=self.tenant_context['bg'].bg_code,
            division=self.tenant_context.get('division'),
            branch=self.tenant_context.get('branch'),
        )

    def parse_period(self, request):
        """Parse period/duration → MongoDB date filter (new PeriodParser)."""
        period = request.query_params.get('period',
                    request.query_params.get('duration', self.DEFAULT_PERIOD))
        return PeriodParser.parse(period, self.ALLOWED_PERIODS)

    def reporting_response(self, data, meta=None):
        """Standardized {data, meta} envelope (new response_utils)."""
        return reporting_response(data, meta={
            'period': meta.get('period', self.DEFAULT_PERIOD),
            'correlation_id': self.correlation_id,
            'generated_at': datetime.now(timezone('Asia/Kolkata')).isoformat(),
            **(meta or {}),
        })
```

### 5.4 Migration Path (lean — no greenfield infrastructure)

| Step | Action | Uses Existing |
|------|--------|---------------|
| 1 | Add `PeriodParser` to `backend/periods.py` | Standalone utility |
| 2 | Add `reporting_response()` to `backend/response_utils.py` | Existing `error_response()` pattern |
| 3 | Add `CorrelationIdMiddleware` to `backend/middleware.py` | Existing Django middleware stack |
| 4 | Add `ReportingViewSet` to `backend/reporting_base.py` | Existing `GenericViewSet` pattern |
| 5 | Migrate `analytics()` → `SharedViewSet` using `ReportingViewSet` | `resolve_access()`, `get_collection()` |
| 6 | Migrate `financials()` → `FinancialsViewSet` using `ReportingViewSet` | `resolve_access()`, `get_collection()` |
| 7 | Migrate `itc_gst()` → `ITCGSTViewSet` using `ReportingViewSet` | `resolve_access()`, `get_collection()` |
| 8 | Migrate `sales()`/`purchases()` → `RevenueViewSet`/`ExpenditureViewSet` | `resolve_access()`, `get_collection()` |
| 9 | Decommission legacy FBVs (`teams/financial.py`, `teams/analytics.py`) | Cleanup |

### 5.5 Benefits

| Area | Before | After |
|------|--------|-------|
| **Tenant resolution** | Duplicated `resolve_access()` per FBV | Once in `initial()`, shared via `self.tenant_context` |
| **Period parsing** | Duplicated across 6 FBVs | Single `PeriodParser` utility |
| **Data access** | Manual `get_collection()` + filter building | `self.get_collection()` with auto-scoping |
| **Response shape** | Ad-hoc per endpoint | `reporting_response()` envelope |
| **Error handling** | `sys.stderr.write` + silent `except` | Structured logging + correlation IDs |
| **New infrastructure** | Would need separate reporting subsystem | **Zero new infrastructure** — plugs into existing primitives |
| **Testing** | Hard (FBV + request mocking) | Easy (mixin unit tests, collection mocks) |

---

## 6. Refactoring Recommendations (Updated)

### Phase 0: Shared Reporting Base Layer (prerequisite)
1. **Build `domains/reporting/`** — `ReportingViewSet` mixin, `PeriodParser`, `TenantScopeBuilder`, `ReportingResponse`
2. **Add correlation ID middleware** — `X-Correlation-Id` header injection
3. **Add structured logging** — `structlog` integration, replace `sys.stderr.write`
4. **Wire `TenantConfig`** — reporting defaults, feature flags, per-BG/brand config

### Phase 1: Fix Critical Bugs (immediate, parallel with Phase 0)
5. **Fix `financials` response format** — return `{date, description, type, amount}` to match frontend
6. **Fix export path mismatch** — add alias routes for `inwardinvoices` → `inward-invoices`
7. **Verify `sales_func` data source** — confirm `outwardDebitNotes` is correct or fix

### Phase 2: Migrate Endpoints onto Base Layer
8. **Migrate `analytics()`** → `SharedViewSet.analytics()` using `ReportingViewSet`
9. **Migrate `financials()`** → `FinancialsViewSet.list()` using `ReportingViewSet`
10. **Migrate `itc_gst()`** → `ITCGSTViewSet.list()` using `ReportingViewSet`
11. **Migrate `sales()`/`purchases()`** → `RevenueViewSet`/`ExpenditureViewSet` using `ReportingViewSet`
12. **Consolidate `sales_func`/`purchases_func`** — single aggregation pipeline (21 queries → 1)

### Phase 3: Add Missing Reports
13. **P&L endpoint** — `accounts/profit-loss` (using `ReportingViewSet`)
14. **Balance sheet endpoint** — `accounts/balance-sheet` (using `ReportingViewSet`)
15. **Inventory valuation** — `products/inventory/valuation` (using `ReportingViewSet`)
16. **Customer analytics** — `accounts/customer-analytics`
17. **Order fulfillment metrics** — `orders/fulfillment-metrics`

### Phase 4: Infrastructure
18. **Response caching** — Redis cache for reporting endpoints (configurable TTL via TenantConfig)
19. **Async export** — background tasks for large exports with webhook callback
20. **Health checks** — `/api/v1/shared/health/reports` endpoint for monitoring
21. **Decommission legacy FBVs** — remove `teams/financial.py`, `teams/analytics.py` after migration

---

## 7. Helper Functions Reference (Legacy — to be absorbed into base layer)

| Function | File | Purpose | Replaced By |
|----------|------|---------|-------------|
| `getfilters()` | `teams/inward_invoices.py:46` | Build MongoDB aggregation stages for time-based filtering | `PeriodParser` + `AggregationBuilder` |
| `safe_aggregate()` | `teams/financial.py:754` | Safe wrapper for `collection.aggregate()` | `ReportingViewSet.aggregate()` |
| `financial_totals()` | `teams/financial.py:1493` | Aggregation pipeline for inward invoices (last 6 months) | `FinancialsViewSet._build_pipeline()` |
| `payment_financials()` | `teams/financial.py:1550` | Aggregation pipeline for payment vouchers (last 6 months) | `FinancialsViewSet._build_pipeline()` |
| `past_present_fin_totals()` | `teams/financial.py:1608` | Aggregation for FY totals (current/last) | `PeriodParser` + `AggregationBuilder` |
| `update_inward_data()` | `teams/financial.py:1658` | Merge payment totals into invoice totals | `FinancialsViewSet._merge_totals()` |
| `getfinancialyear()` | `teams/kurostaff/views.py` | Compute financial year string from month/year | `PeriodParser.fiscal_year()` |

---

## 8. Frontend Data Contract Mismatches (summary — see §4 for full contracts)

| Endpoint | Frontend Expects | Backend Returns | Severity |
|----------|-----------------|-----------------|----------|
| `accounts/financials` | `[{date, description, type, amount, reference}]` | `[{ "2024-Jan": {invoice_type: total, total} }, ...]` | 🔴 Critical |
| `accounts/revenue` | Not called directly | `{invoice_curmonth, credit_curmonth, ...}` (21 keys) | 🟡 Unused |
| `accounts/expenditure` | Not called directly | `{invoice_curmonth, credit_curmonth, ...}` (21 keys) | 🟡 Unused |
| `shared/analytics` | Exact match | Exact match | ✅ OK |
| `accounts/itc-gst` | Exact match | Exact match | ✅ OK |
| `accounts/bulk-payments` | Not called | N/A | 🔴 Dead |

---

## 9. Decision Matrix

| Decision | Option A | Option B | Recommendation |
|----------|----------|----------|---------------|
| **Financials format** | Fix backend to match frontend | Fix frontend to match backend | Fix backend — frontend contract is cleaner |
| **Export paths** | Add alias routes (no hyphen) | Fix frontend to use hyphens | Add alias routes — less frontend risk |
| **sales_func collection** | Keep `outwardDebitNotes` | Switch to `outwardInvoices` | Verify with DB admin first |
| **Base layer approach** | Greenfield reporting subsystem | Thin mixin on existing primitives | **Thin mixin** — KungOS v2 already has resolve_access, get_collection, tenant models |
| **Missing reports** | Build all 8 missing reports | Build top 3 (P&L, balance sheet, inventory) | Top 3 first — MVP approach |
| **Caching** | Redis for all reporting | No cache, optimize queries | Redis — reporting is read-heavy, configurable via TenantConfig |
| **Error handling** | Keep `sys.stderr.write` + silent except | Structured logging + correlation IDs | **Structured logging** — observable, debuggable, no production noise |
| **Tenant scoping** | Per-endpoint `resolve_access()` | Centralized `TenantScopeBuilder` | **Centralized** — single source of truth, testable |
| **Period parsing** | Duplicated across endpoints | Centralized `PeriodParser` | **Centralized** — consistent date handling, testable |
| **Feature flags** | Hardcoded | `TenantConfig`-driven per BG/brand | **TenantConfig** — flexible per-tenant behavior |
