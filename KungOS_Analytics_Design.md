# KungOS Analytics & Reporting — Design Document

> **Version:** 1.0  
> **Status:** Design  
> **Date:** 2026-05-04  
> **Scope:** Reporting endpoints, dashboard analytics, financial reports, export pipelines  
> **Architecture:** Thin layer on KungOS v2 primitives — no greenfield infrastructure

---

## Table of Contents

1. [Overview](#1-overview)
2. [Frontend Data Contracts](#2-frontend-data-contracts)
   - [2.5 Response Envelope & Accessor Compatibility](#25-response-envelope--accessor-compatibility)
3. [Existing KungOS v2 Primitives](#3-existing-kungos-v2-primitives)
4. [New Thin-Layer Components](#4-new-thin-layer-components)
5. [Endpoint Specifications](#5-endpoint-specifications)
6. [Aggregation Patterns](#6-aggregation-patterns)
7. [Export Pipeline](#7-export-pipeline)
8. [Observability](#8-observability)
9. [Migration Plan](#9-migration-plan)
10. [Appendix: Period Formats](#10-appendix-period-formats)
11. [Appendix: Standardized Code Conventions](#11-appendix-standardized-code-conventions)

---

## 1. Overview

### 1.1 Purpose

Define the analytics and reporting layer for KungOS v2. All reporting endpoints plug into existing KungOS v2 primitives (tenant context, collection access, authentication) and add only thin utilities for period parsing, standardized responses, and observability.

### 1.2 Design Principles

| Principle | Rule |
|-----------|------|
| **No greenfield infrastructure** | Use `resolve_access()`, `get_collection()`, `BusinessGroup` — don't recreate |
| **Frontend-driven contracts** | Backend produces exact shapes Recharts/DataTable/StatCard consume |
| **Numeric amounts, ISO dates** | Frontend handles all formatting (`toLocaleString('en-IN')`, `toLocaleDateString('en-IN')`) |
| **Period-agnostic** | All reporting endpoints accept `period` param (daily/weekly/monthly/quarterly/yearly) |
| **Tenant-scoped** | Every query auto-scoped to `bg_code` → `div_code` → `branch_code` |
| **Code-first scoping** | Endpoint params use `bg_code`, `div_code`, `branch_code` — labels are display-only |
| **Observable** | Correlation IDs, structured logging, query timing |
| **Domain-routed** | `/api/v1/accounts/...`, `/api/v1/shared/...` — no legacy prefixes |
| **Canonical imports** | All utilities reference actual module paths per endpoint design (§2.3) |

### 1.3 Reporting Endpoints

| Domain | Endpoint | Purpose | Frontend Page |
|--------|----------|---------|---------------|
| shared | `GET /shared/analytics` | Dashboard analytics (revenue, expenses, trends) | `Accounts/Analytics.jsx` |
| accounts | `GET /accounts/financials` | Financial report (transaction list) | `Accounts/Financials.jsx` |
| accounts | `GET /accounts/itc-gst` | GST compliance (ITC tracking) | `Accounts/ITCGST.jsx` |
| accounts | `GET /accounts/revenue` | Revenue/sales metrics | Export, future page |
| accounts | `GET /accounts/expenditure` | Expenditure/purchase metrics | Export, future page |
| accounts | `GET /accounts/profit-loss` | P&L statement | Future page |
| accounts | `GET /accounts/balance-sheet` | Balance sheet | Future page |
| accounts | `GET /accounts/export/{type}` | Data export (CSV/Excel) | `Accounts/Financials.jsx` export dialog |
| products | `GET /products/inventory/valuation` | Inventory valuation report | `Inventory/Overview.jsx` |
| orders | `GET /orders/fulfillment-metrics` | Order fulfillment analytics | Future page |

---

## 2. Frontend Data Contracts

All reporting endpoints produce data shapes the frontend consumes directly. No client-side transformation beyond formatting.

### 2.1 Recharts — Chart Data

Frontend uses **Recharts v3** with `dataKey` fields.

| Chart | Page | Required Fields | Period Labels |
|-------|------|----------------|---------------|
| Revenue vs Expenses (BarChart) | Analytics | `{ period, revenue, expenses, orders }` | `daily`→`"14:00"`, `weekly`→`"Mon 15"`, `monthly`→`"Jan"`, `quarterly`→`"Q1 2024"`, `yearly`→`"2024"` |
| Payment Trends (AreaChart) | Analytics | `{ period, paid, pending }` | Same as above |
| Vendor Spend (bars) | Analytics | `{ name, amount, percentage }` | N/A |

### 2.2 DataTable — Table Data

Frontend uses **TanStack Table** via `@/components/common/DataTable` with `accessorKey` columns.

| Page | Required Fields | Type Values |
|------|----------------|-------------|
| Financials | `{ date, description, category, type, amount, reference }` | `type: "income" \| "expense"` |
| ITC-GST | `{ invoice_no, gstin, invoice_date, igst, cgst, sgst, itc_amount, status }` | `status: "Claimed" \| "Pending" \| "Rejected"` |

### 2.3 StatCard — KPI Data

Frontend uses `@/components/common/StatCard`. Values are computed from response data via `useMemo`.

| Page | KPI Keys | Source |
|------|----------|--------|
| Analytics | `totalRevenue`, `totalExpenses`, `profitMargin`, `avgInvoiceValue`, `daysToPay`, `overdueAmount` | Top-level keys in analytics response |
| Financials | `totalIncome`, `totalExpenses`, `netProfit`, `avgTransaction` | Computed from DataTable rows |
| ITC-GST | `totalITC`, `utilizedITC`, `availableITC`, `gstLiability`, `netPayable` | Computed from DataTable rows |

### 2.4 Badge Variants

| Page | Field | Mapping |
|------|-------|---------|
| Financials | `type` | `"income"` → `success`, `"expense"` → `destructive` |
| ITC-GST | `status` | `"Claimed"` → `success`, `"Pending"` → `warning`, `"Rejected"` → `destructive` |

### 2.5 Response Envelope & Accessor Compatibility

**Rule:** All reporting endpoints return `{data, meta}` envelope. Frontend must read from `response.data.*`, not `response.*`.

| Page | Current Accessor | New Accessor | Change |
|------|-----------------|--------------|--------|
| Analytics.jsx | `data.totalRevenue` | `data.data.totalRevenue` | Add `.data` accessor |
| Analytics.jsx | `data.chartData` | `data.data.chartData` | Add `.data` accessor |
| Analytics.jsx | `data.paymentTrend` | `data.data.paymentTrend` | Add `.data` accessor |
| Financials.jsx | `data[0].amount` | `data.data[0].amount` | Add `.data` accessor |
| ITCGST.jsx | `data[0].igst` | `data.data[0].igst` | Add `.data` accessor |

**Migration:** Update frontend `useQuery` selectors at the same time as backend cutover.

```js
// Before (current — flat response):
const { data } = useQuery({
  queryKey: queryKeys.analytics,
  queryFn: () => api.get('/shared/analytics'),
});
// data.totalRevenue, data.chartData, ...

// After (envelope):
const { data } = useQuery({
  queryKey: queryKeys.analytics,
  queryFn: () => api.get('/shared/analytics'),
  select: (response) => response.data, // unwrap envelope
});
// data.totalRevenue, data.chartData, ... (same as before)
```

**Alternative:** Add `select: (r) => r.data` in every `useQuery` call, or create a shared wrapper:

```js
// lib/api.jsx — shared envelope unwrapper
export const reportingApi = {
  get: (url, params) => api.get(url, params).then(r => r.data),
};
```

### 2.6 Formatting Rules

| Field Type | Backend Returns | Frontend Formats |
|-----------|----------------|-----------------|
| **Amounts** | Numeric (float) | `₹${value.toLocaleString('en-IN')}` |
| **Dates** | ISO string (`2024-03-15T10:30:00+05:30`) | `new Date(d).toLocaleDateString('en-IN')` |
| **Percentages** | Numeric (float, 0-100) | `${value}%` |
| **Period labels** | String (`"Jan"`, `"Q1 2024"`) | Rendered as-is |

---

## 3. Existing KungOS v2 Primitives

Reporting plugs into these. No recreation.

| Primitive | Canonical Module | Purpose |
|-----------|----------------|---------|
| `resolve_access(request)` | `backend/auth_utils.py` | Full tenant context: user, bg, switchgroup, access_dict |
| `resolve_minimal(request)` | `backend/auth_utils.py` | Lightweight: bg + switchgroup only |
| `has_read_access(access_dict, field)` | `backend/auth_utils.py` | Read permission check (replaces pandas patterns) |
| `has_write_access(access_dict, field)` | `backend/auth_utils.py` | Write permission check |
| `check_access(user_access, field, access_dict)` | `backend/auth_utils.py` | Permission check by codename |
| `check_write_access(user_access, field, access_dict, level)` | `backend/auth_utils.py` | Write permission check with level |
| `get_collection(name, bg_code, div_code, branch_code)` | `backend/utils.py` | MongoDB collection + tenant filter dict |
| `find_all(name, filters, bg_code, div_code, branch_code, sort, limit, skip)` | `backend/utils.py` | Query with tenant filtering + pagination |
| `decode_result(cursor)` | `backend/utils.py` | Decode MongoDB cursor → Python objects |
| `resolve_access_levels(access_query, bg_code)` | `backend/utils.py` | Resolve access levels from Accesslevel collection |
| `error_response(exc, raise_internal)` | `backend/response_utils.py` | Standardized error response envelope |
| `InputException` | `backend/exceptions.py` | Input validation exception |
| `CookieJWTAuthentication` | `users/cookie_auth.py` | Cookie-based JWT auth |
| `has_permission(user, codename)` | `users/permissions.py` | RBAC permission check |
| `BusinessGroup` model | `tenant/models.py` | BG config: db_name, brand, settings, bg_code |
| `Division` model | `tenant/models.py` | Division hierarchy: div_code, cascade codes |
| `Branch` model | `tenant/models.py` | Branch details: branch_code |
| Domain ViewSets | `kungos_dj/domains/{accounts,shared}/views.py` | Domain-based ViewSet routing |
| Domain URLs | `kungos_dj/domains/{accounts,shared}/urls.py` | Domain URL routing |
| `/api/v1/` routing | `backend/urls.py` | Root URL configuration (includes domain modules) |
| `/api/v1/` routing | `backend/urls.py` | Domain-based URL routing |

---

## 4. New Thin-Layer Components

Four new files in `backend/` — utilities that plug into existing canonical modules. All imports reference actual module paths per endpoint design (§2.3).

### 4.1 `backend/periods.py` — PeriodParser

```python
"""Period parsing utilities for reporting endpoints.

Converts period/duration strings → MongoDB date range filters.
Used by all reporting endpoints for consistent date handling.
"""

from datetime import datetime, timedelta
from pytz import timezone
from dateutil.relativedelta import relativedelta


class PeriodResult:
    """Parsed period result with date range and display label."""
    def __init__(self, start_date, end_date, label, period_type):
        self.start_date = start_date  # datetime
        self.end_date = end_date      # datetime
        self.label = label            # str (e.g., "Jan", "Q1 2024")
        self.period_type = period_type  # str (e.g., "monthly")

    def to_mongo_filter(self, date_field='created_date'):
        """Return MongoDB date range filter."""
        return {
            date_field: {
                "$gte": self.start_date.isoformat(),
                "$lt": self.end_date.isoformat(),
            }
        }


class PeriodParser:
    """Parse period/duration strings → PeriodResult.

    Supports:
      - Periods: daily, weekly, monthly, quarterly, yearly
      - Durations: curr_month, last_month, curr_fy, last_fy, curr_quarter, last_quarter
      - Custom: start_date/end_date query params
    """
    MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    @classmethod
    def parse(cls, period_str, allowed=None):
        """Parse a period string into a PeriodResult.

        Args:
            period_str: Period identifier (e.g., "monthly", "curr_fy")
            allowed: Optional list of allowed period types

        Returns:
            PeriodResult with start_date, end_date, label, period_type
        """
        now = datetime.now(timezone('Asia/Kolkata'))

        if period_str in ('daily',):
            return cls._parse_daily(now)
        elif period_str in ('weekly',):
            return cls._parse_weekly(now)
        elif period_str in ('monthly', 'curr_month'):
            return cls._parse_monthly(now)
        elif period_str in ('last_month',):
            return cls._parse_last_month(now)
        elif period_str in ('quarterly', 'curr_quarter'):
            return cls._parse_quarterly(now)
        elif period_str in ('last_quarter',):
            return cls._parse_last_quarter(now)
        elif period_str in ('yearly', 'curr_fy'):
            return cls._parse_yearly(now)
        elif period_str in ('last_fy',):
            return cls._parse_last_fy(now)
        else:
            # Default to monthly
            return cls._parse_monthly(now)

    @classmethod
    def _parse_daily(cls, now):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return PeriodResult(start, end, now.strftime("%a %d"), "daily")

    @classmethod
    def _parse_weekly(cls, now):
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return PeriodResult(start, end, cls.DAY_LABELS[start.weekday()], "weekly")

    @classmethod
    def _parse_monthly(cls, now):
        """Current month, 1st to last day."""
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=1)
        return PeriodResult(start, end, cls.MONTH_LABELS[now.month - 1], "monthly")

    @classmethod
    def _parse_last_month(cls, now):
        start = (now - relativedelta(months=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=1)
        return PeriodResult(start, end, cls.MONTH_LABELS[(now.month - 2) % 12], "monthly")

    @classmethod
    def _parse_quarterly(cls, now):
        quarter = (now.month - 1) // 3
        start = now.replace(month=quarter * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=3)
        return PeriodResult(start, end, f"Q{quarter + 1} {now.year}", "quarterly")

    @classmethod
    def _parse_last_quarter(cls, now):
        quarter = (now.month - 1) // 3
        if quarter == 0:
            quarter = 3
            year = now.year - 1
        else:
            quarter -= 1
            year = now.year
        start = now.replace(month=quarter * 3 + 1, day=1, year=year, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=3)
        return PeriodResult(start, end, f"Q{quarter} {year}", "quarterly")

    @classmethod
    def _parse_yearly(cls, now):
        """Current financial year (April–March for India)."""
        if now.month >= 4:
            start = now.replace(month=4, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = start + relativedelta(years=1)
            label = f"FY {now.year}-{now.year + 1}"
        else:
            start = now.replace(month=4, day=1, year=now.year - 1, hour=0, minute=0, second=0, microsecond=0)
            end = start + relativedelta(years=1)
            label = f"FY {now.year - 1}-{now.year}"
        return PeriodResult(start, end, label, "yearly")

    @classmethod
    def _parse_last_fy(cls, now):
        if now.month >= 4:
            start = now.replace(month=4, day=1, year=now.year - 1, hour=0, minute=0, second=0, microsecond=0)
            end = start + relativedelta(years=1)
            label = f"FY {now.year - 1}-{now.year}"
        else:
            start = now.replace(month=4, day=1, year=now.year - 2, hour=0, minute=0, second=0, microsecond=0)
            end = start + relativedelta(years=1)
            label = f"FY {now.year - 2}-{now.year - 1}"
        return PeriodResult(start, end, label, "yearly")

    @classmethod
    def parse_custom(cls, start_date_str, end_date_str):
        """Parse custom start_date/end_date query params."""
        start = datetime.fromisoformat(start_date_str).replace(tzinfo=timezone('Asia/Kolkata'))
        end = datetime.fromisoformat(end_date_str).replace(tzinfo=timezone('Asia/Kolkata'))
        label = f"{start.strftime('%d %b')} – {end.strftime('%d %b')}"
        return PeriodResult(start, end, label, "custom")
```

### 4.2 `backend/response_utils.py` — reporting_response

```python
"""Standardized response envelope for reporting endpoints."""

from rest_framework.response import Response
from datetime import datetime
from pytz import timezone


def reporting_response(data, meta=None):
    """Standardized {data, meta} response envelope for reporting endpoints.

    Args:
        data: The report data (list, dict, or primitive)
        meta: Optional metadata override

    Returns:
        DRF Response with {data, meta} envelope
    """
    base_meta = {
        'generated_at': datetime.now(timezone('Asia/Kolkata')).isoformat(),
    }
    if meta:
        base_meta.update(meta)

    return Response({
        'data': data,
        'meta': base_meta,
    })
```

### 4.3 Correlation ID + Structured Logging (already exists)

These are already implemented in `plat/observability/`:

| Component | Canonical Module | Purpose |
|-----------|----------------|---------|
| `CorrelationIDMiddleware` | `plat/observability/middleware.py` | Injects `X-Request-ID` on every request |
| `TenantContextMiddleware` | `plat/observability/middleware.py` | Extracts tenant from JWT → ContextVar |
| `StructuredFormatter` | `plat/observability/logging.py` | JSON log records with bg_code, request_id |
| `setup_structured_logging()` | `plat/observability/logging.py` | Configures root logger |

Already registered in `backend/settings.py` MIDDLEWARE:
```python
MIDDLEWARE = [
    ...
    'plat.observability.middleware.CorrelationIDMiddleware',
    'plat.observability.middleware.TenantContextMiddleware',
]
```

No new middleware needed. Reporting endpoints use `request.META.get('HTTP_X_REQUEST_ID')` for correlation ID.

```python
"""Correlation ID middleware for request tracing."""

import uuid
from django.utils.deprecation import MiddlewareMixin


class CorrelationIdMiddleware(MiddlewareMixin):
    """Inject X-Correlation-Id header on every request.

    If the client sends X-Correlation-Id, it is preserved.
    Otherwise, a new UUID is generated.

    The ID is available in request.META['CORRELATION_ID']
    and in response headers as X-Correlation-Id.
    """

    def process_request(self, request):
        correlation_id = request.META.get('HTTP_X_CORRELATION_ID') or uuid.uuid4().hex
        request.META['CORRELATION_ID'] = correlation_id
        return None

    def process_response(self, request, response):
        correlation_id = request.META.get('CORRELATION_ID')
        if correlation_id:
            response['X-Correlation-Id'] = correlation_id
        return response
```

### 4.4 `backend/reporting_base.py` — ReportingViewSet

```python
"""Reporting ViewSet base class.

Thin mixin that plugs into existing KungOS v2 primitives:
  - resolve_access() from backend/auth_utils.py for tenant context
  - get_collection() from backend/utils.py for data access
  - CookieJWTAuthentication from users/cookie_auth.py for auth
  - has_read_access()/has_write_access() from backend/auth_utils.py for permissions

Adds only:
  - PeriodParser (backend/periods.py) for date range filtering
  - reporting_response() (backend/response_utils.py) for {data, meta} envelope
  - Correlation ID injection
  - Structured logging stub
"""

from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from datetime import datetime
from pytz import timezone

# Canonical imports — per endpoint design §2.3
from users.cookie_auth import CookieJWTAuthentication
from users.permissions import has_permission
from backend.auth_utils import (
    resolve_access, resolve_minimal,
    has_read_access, has_write_access,
    check_access, check_write_access,
)
from backend.utils import get_collection, find_all, decode_result
from backend.exceptions import InputException
from backend.response_utils import error_response
from backend.periods import PeriodParser


class ReportingViewSet(viewsets.GenericViewSet):
    """Base ViewSet for all reporting endpoints.

    Tenant context: bg_code → div_code → branch_code (standardized codes, not labels).
    Labels are display-only — never used for scoping or filtering.

    Usage:
        class FinancialsViewSet(ReportingViewSet):
            COLLECTIONS = ['inwardinvoices', 'paymentvouchers']
            DEFAULT_PERIOD = 'monthly'

            def list(self, request):
                period = self.parse_period(request)
                collection, tf = self.get_collection('inwardinvoices')
                results = decode_result(collection.find({**tf, **period.to_mongo_filter()}))
                return self.reporting_response(results, {'period': period.label})
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    # Override per-endpoint
    COLLECTIONS = []  # list of collection names this report queries
    DEFAULT_PERIOD = 'monthly'
    ALLOWED_PERIODS = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']

    def initial(self, request, *args, **kwargs):
        """Resolve tenant context once, inject correlation ID.

        Sets self.tenant_context with:
          - bg_code: Business Group code (e.g., 'KURO0001')
          - div_code: Division code (e.g., 'KURO0001_001')
          - branch_code: Branch code (e.g., 'BR001')
          - access_dict: Permission map by division
        """
        super().initial(request, *args, **kwargs)
        self.tenant_context = resolve_access(request)
        self.correlation_id = request.META.get('CORRELATION_ID')

    def get_collection(self, name, div_code=None, branch_code=None):
        """Get collection with auto-scoped tenant filters.

        Uses get_collection() from backend/utils.py with resolved tenant context.
        Override div_code/branch_code for queries that need different scoping.

        Args:
            name: Collection name (e.g., 'inwardinvoices')
            div_code: Division code override (e.g., 'KURO0001_001')
            branch_code: Branch code override (e.g., 'BR001')

        Returns:
            tuple: (collection, filter_dict) from backend/utils.py
        """
        return get_collection(
            name,
            bg_code=self.tenant_context['bg'].bg_code,
            div_code=div_code,
            branch_code=branch_code,
        )

    def parse_period(self, request):
        """Parse period/duration params → PeriodResult.

        Checks: period → duration → start_date/end_date → DEFAULT_PERIOD
        """
        period = request.query_params.get('period',
                    request.query_params.get('duration', self.DEFAULT_PERIOD))

        # Custom date range
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date and end_date:
            return PeriodParser.parse_custom(start_date, end_date)

        return PeriodParser.parse(period, self.ALLOWED_PERIODS)

    def reporting_response(self, data, meta=None):
        """Return standardized {data, meta} envelope.

        Uses reporting_response() from backend/response_utils.py.
        """
        return Response({
            'data': data,
            'meta': {
                'period': meta.get('period', self.DEFAULT_PERIOD) if meta else self.DEFAULT_PERIOD,
                'correlation_id': self.correlation_id,
                'count': len(data) if isinstance(data, (list, dict)) else 1,
                'generated_at': datetime.now(timezone('Asia/Kolkata')).isoformat(),
                **(meta or {}),
            }
        })

    def error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        """Return standardized error response.

        Uses error_response() from backend/response_utils.py.
        """
        return error_response(message, status_code=status_code)

    def check_report_access(self, codename, level=1):
        """Check if user has access to this report.

        Uses has_read_access()/has_write_access() from backend/auth_utils.py.

        Args:
            codename: Permission codename (e.g., 'financials', 'analytics')
            level: 1 = read, 2 = write

        Returns:
            True if access granted, raises error_response if denied
        """
        access_dict = self.tenant_context['access_dict']

        if level == 1:
            if not has_read_access(access_dict, codename):
                return self.error_response("Access denied", status.HTTP_403_FORBIDDEN)
        else:
            if not has_write_access(access_dict, codename):
                return self.error_response("Access denied", status.HTTP_403_FORBIDDEN)
        return True
```

---

## 5. Endpoint Specifications

### 5.1 `GET /shared/analytics` — Dashboard Analytics

**Viewset:** `SharedViewSet.analytics()` → `kungos_dj/domains/shared/views.py`  
**URL:** `kungos_dj/domains/shared/urls.py` → `path('analytics', ...)`  
**Collections:** `inwardpayments`, `paymentvouchers`, `estimates`, `tporders`, `purchaseorders`  
**Permission:** `analytics` (read) → `has_read_access(access_dict, 'analytics')`

#### Query Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `period` | string | No | `monthly` | `daily`, `weekly`, `monthly`, `quarterly`, `yearly` |
| `div_code` | string | No | User's active division | Division code (e.g., `KURO0001_001`) — not display label |
| `branch_code` | string | No | All branches | Branch code (e.g., `BR001`) — not display label |

> **Note:** Endpoint params always use codes (`bg_code`, `div_code`, `branch_code`).
> Display labels are resolved by frontend via `tenant/divisions` and `tenant/branches` lookups.

#### Response

```json
{
  "data": {
    "totalOrders": 1542,
    "totalRevenue": 4523000.00,
    "totalExpenses": 2891000.00,
    "profitMargin": 36.1,
    "avgInvoiceValue": 2933.12,
    "daysToPay": 18,
    "overdueAmount": 156000.00,
    "totalEstimates": 234,
    "totalTPOrders": 189,
    "statusBreakdown": { "Paid": 1200, "Pending": 342 },
    "chartData": [
      { "period": "Nov", "revenue": 750000, "expenses": 480000, "orders": 256 },
      { "period": "Dec", "revenue": 820000, "expenses": 510000, "orders": 278 }
    ],
    "paymentTrend": [
      { "period": "Nov", "paid": 680000, "pending": 70000 },
      { "period": "Dec", "paid": 740000, "pending": 80000 }
    ],
    "vendors": [
      { "name": "TechCorp", "amount": 450000, "percentage": 35.2 },
      { "name": "SupplyHub", "amount": 320000, "percentage": 25.0 }
    ]
  },
  "meta": {
    "period": "monthly",
    "correlation_id": "abc123...",
    "count": 1,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

#### Implementation Notes

- Revenue from `inwardpayments` (primary revenue source)
- Expenses from `paymentvouchers` (internal expenses, where vendor is empty/missing)
- Chart data built by grouping payments by period bucket
- Vendor data from `purchaseorders` (top 5 by spend)
- All amounts are numeric floats, never formatted strings
- Tenant scoping: `bg_code` from `resolve_access()`, `div_code`/`branch_code` from query params
- Collection access: `get_collection(name, bg_code=..., div_code=..., branch_code=...)` from `backend/utils.py`

#### ⚠️ Envelope Compatibility

Current backend returns flat object: `{totalRevenue, chartData, ...}` → frontend reads `data.totalRevenue`.
New envelope wraps it: `{data: {totalRevenue, chartData, ...}, meta: {...}}` → frontend must read `data.data.totalRevenue`.

**Fix:** Update `Analytics.jsx` `useQuery` selector at cutover:
```js
select: (response) => response.data, // unwrap {data, meta} envelope
```
Or use shared wrapper from `lib/api.jsx`: `reportingApi.get('/shared/analytics')`.

---

### 5.2 `GET /accounts/financials` — Financial Report

**Viewset:** `FinancialsViewSet` → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('financials', ...)`  
**Collections:** `inwardinvoices`, `paymentvouchers`  
**Permission:** `financials` (read) → `has_read_access(access_dict, 'financials')`

#### Query Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `period` | string | No | `monthly` | Time period for report |
| `div_code` | string | No | User's active division | Division code (e.g., `KURO0001_001`) |
| `branch_code` | string | No | All branches | Branch code (e.g., `BR001`) |
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 50 | Results per page |

#### Response

```json
{
  "data": [
    {
      "date": "2024-12-15T10:30:00+05:30",
      "description": "Invoice #INV-2024-0456 from TechCorp",
      "category": "Equipment",
      "type": "income",
      "amount": 45000.00,
      "reference": "INV-2024-0456"
    },
    {
      "date": "2024-12-14T09:00:00+05:30",
      "description": "Payment voucher - Office supplies",
      "category": "Office Expenses",
      "type": "expense",
      "amount": 12500.00,
      "reference": "PV-2024-0123"
    }
  ],
  "meta": {
    "period": "monthly",
    "correlation_id": "abc123...",
    "count": 2,
    "page": 1,
    "page_size": 50,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

#### Implementation Notes

- Merges inward invoices (income) and payment vouchers (expenses) into single transaction list
- Each record has `type: "income" | "expense"` for Badge coloring
- `date` is ISO string for frontend `toLocaleDateString` formatting
- `amount` is numeric float for frontend `toLocaleString` formatting
- Paginated via DRF pagination
- Tenant scoping: `bg_code` from `resolve_access()`, `div_code`/`branch_code` from query params
- Collection access: `get_collection(name, bg_code=..., div_code=..., branch_code=...)` from `backend/utils.py`

---

### 5.3 `GET /accounts/itc-gst` — GST Compliance

**Viewset:** `ITCGSTViewSet` → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('itc-gst', ...)`  
**Collections:** `inwardinvoices`  
**Permission:** `itc_gst` (read) → `has_read_access(access_dict, 'itc_gst')`

#### Query Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `period` | string | No | `monthly` | `monthly`, `quarterly`, `yearly` |
| `div_code` | string | No | User's active division | Division code (e.g., `KURO0001_001`) |

#### Response

```json
{
  "data": [
    {
      "invoice_no": "INV-2024-0456",
      "gstin": "27AABCU9603R1ZM",
      "invoice_date": "2024-12-15T00:00:00+05:30",
      "igst": 8100.00,
      "cgst": 4050.00,
      "sgst": 4050.00,
      "itc_amount": 16200.00,
      "gst_amount": 16200.00,
      "utilized": 0,
      "status": "Pending"
    }
  ],
  "meta": {
    "period": "monthly",
    "correlation_id": "abc123...",
    "count": 1,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

#### Implementation Notes

- Tax extraction from `taxes` field in inward invoices
- `igst` from 28% rate, `cgst`/`sgst` from split rates
- `itc_amount` = igst + cgst + sgst
- `status` derived from invoice `active` field
- Tenant scoping: `bg_code` from `resolve_access()`, `div_code` from query params
- Collection access: `get_collection('inwardinvoices', bg_code=..., div_code=...)` from `backend/utils.py`

---

### 5.4 `GET /accounts/revenue` — Revenue Metrics

**Viewset:** `RevenueViewSet` → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('revenue', ...)`  
**Collections:** `outwardinvoices`  
**Permission:** `revenue` (read) → `has_read_access(access_dict, 'revenue')`

#### Query Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `period` | string | No | `monthly` | Time period |
| `div_code` | string | No | User's active division | Division code (e.g., `KURO0001_001`) |

#### Response

```json
{
  "data": {
    "current_month": { "invoices": 450000, "credits": 12000, "debits": 8000 },
    "last_month": { "invoices": 420000, "credits": 15000, "debits": 5000 },
    "current_quarter": { "invoices": 1350000, "credits": 38000, "debits": 22000 },
    "current_fy": { "invoices": 5200000, "credits": 145000, "debits": 89000 },
    "summary": {
      "total_invoices": 5200000,
      "total_credits": 145000,
      "total_debits": 89000,
      "net_revenue": 5256000
    }
  },
  "meta": {
    "period": "monthly",
    "correlation_id": "abc123...",
    "count": 1,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

---

### 5.5 `GET /accounts/expenditure` — Expenditure Metrics

**Viewset:** `ExpenditureViewSet` → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('expenditure', ...)`  
**Collections:** `inwardinvoices`  
**Permission:** `expenditure` (read) → `has_read_access(access_dict, 'expenditure')`

#### Response Shape

Same structure as `accounts/revenue` but sourced from inward invoices (purchases).

---

### 5.6 `GET /accounts/export/{type}` — Data Export

**Viewset:** `ExportViewSet` → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('export/<str:type>', ...)`  
**Types:** `financials`, `inward-invoices`, `outward-invoices`, `inward-payments`  
**Permission:** `export` (read) → `has_read_access(access_dict, 'export')`

#### Query Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `duration` | string | No | `curr_month` | `curr_month`, `last_month`, `curr_fy`, `last_fy` |
| `format` | string | No | `json` | `json`, `csv` |
| `div_code` | string | No | User's active division | Division code (e.g., `KURO0001_001`) |

#### Response

Same as the source endpoint's data shape, filtered by duration. For CSV format, returns `text/csv` content type with headers.

---

### 5.7 `GET /accounts/profit-loss` — P&L Statement

**Viewset:** `ProfitLossViewSet` (new) → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('profit-loss', ...)`  
**Collections:** `outwardinvoices`, `inwardinvoices`, `paymentvouchers`  
**Permission:** `profit_loss` (read) → `has_read_access(access_dict, 'profit_loss')`

#### Response

```json
{
  "data": {
    "period": "FY 2024-2025",
    "revenue": {
      "sales": 5200000,
      "services": 800000,
      "other": 50000,
      "total": 6050000
    },
    "cogs": 2800000,
    "gross_profit": 3250000,
    "gross_margin": 53.7,
    "operating_expenses": {
      "salaries": 1200000,
      "rent": 360000,
      "utilities": 120000,
      "marketing": 80000,
      "other": 40000,
      "total": 1800000
    },
    "operating_profit": 1450000,
    "interest": -25000,
    "tax": 290000,
    "net_profit": 1135000,
    "net_margin": 18.8,
    "prior_period": {
      "revenue": 5100000,
      "net_profit": 980000,
      "revenue_growth": 18.6,
      "profit_growth": 15.8
    }
  },
  "meta": {
    "period": "yearly",
    "correlation_id": "abc123...",
    "count": 1,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

---

### 5.8 `GET /accounts/balance-sheet` — Balance Sheet

**Viewset:** `BalanceSheetViewSet` (new) → `kungos_dj/domains/accounts/views.py`  
**URL:** `kungos_dj/domains/accounts/urls.py` → `path('balance-sheet', ...)`  
**Collections:** `asset_register`, `inwardinvoices`, `outwardinvoices`, `inwardpayments`, `outwardpayments`  
**Permission:** `balance_sheet` (read) → `has_read_access(access_dict, 'balance_sheet')`

#### Response

```json
{
  "data": {
    "as_of": "2024-12-31T00:00:00+05:30",
    "assets": {
      "current": {
        "cash": 250000,
        "accounts_receivable": 450000,
        "inventory": 1800000,
        "total": 2500000
      },
      "fixed": {
        "equipment": 3200000,
        "accumulated_depreciation": -800000,
        "net": 2400000
      },
      "total_assets": 4900000
    },
    "liabilities": {
      "current": {
        "accounts_payable": 380000,
        "short_term_loans": 150000,
        "total": 530000
      },
      "long_term": {
        "loans": 1200000,
        "total": 1200000
      },
      "total_liabilities": 1730000
    },
    "equity": {
      "capital": 2000000,
      "retained_earnings": 1170000,
      "total": 3170000
    },
    "balance_check": true
  },
  "meta": {
    "period": "yearly",
    "correlation_id": "abc123...",
    "count": 1,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

---

### 5.9 `GET /products/inventory/valuation` — Inventory Valuation

**Viewset:** `InventoryValuationViewSet` (new) → `kungos_dj/domains/products/views.py`  
**URL:** `kungos_dj/domains/products/urls.py` → `path('inventory/valuation', ...)`  
**Collections:** `stock_register`, `products`  
**Permission:** `inventory` (read) → `has_read_access(access_dict, 'inventory')`

#### Response

```json
{
  "data": {
    "total_skus": 1245,
    "total_quantity": 45600,
    "total_value": 18500000,
    "by_category": [
      { "category": "Laptops", "quantity": 250, "value": 4500000 },
      { "category": "Peripherals", "quantity": 1200, "value": 1800000 }
    ],
    "low_stock": [
      { "product_code": "LP-001", "name": "Dell Latitude 5420", "quantity": 3, "reorder_level": 10 }
    ],
    "out_of_stock": [
      { "product_code": "KB-042", "name": "Logitech K380", "quantity": 0 }
    ],
    "slow_moving": [
      { "product_code": "MN-015", "name": "HP LaserJet Pro", "days_since_sale": 180 }
    ]
  },
  "meta": {
    "correlation_id": "abc123...",
    "count": 1,
    "generated_at": "2025-01-04T10:30:00+05:30"
  }
}
```

---

## 6. Aggregation Patterns

### 6.1 Single-Pipeline Aggregation

Replace the legacy pattern of 21 separate aggregation queries with a single pipeline:

```python
# Instead of 21 calls to getfilters() + safe_aggregate():
# Uses decode_result() from backend/utils.py
from backend.utils import get_collection, decode_result

collection, tenant_filter = get_collection(
    'inwardinvoices',
    bg_code=tenant_context['bg'].bg_code,
    div_code=div_code,
    branch_code=branch_code,
)

pipeline = [
    {"$match": {**tenant_filter, "delete_flag": {"$ne": True}}},
    {"$project": {
        "parsed_date": {
            "$dateFromString": {
                "dateString": "$invoice_date",
                "format": "%Y-%m-%dT%H:%M:%S",
                "onError": null,
                "onNull": null,
            }
        },
        "total": "$totalprice",
        "type": "$invoice_type",
    }},
    {"$group": {
        "_id": {
            "month": {"$month": "$parsed_date"},
            "year": {"$year": "$parsed_date"},
            "type": "$type",
        },
        "total": {"$sum": "$total"},
        "count": {"$sum": 1},
    }},
]
results = decode_result(collection.aggregate(pipeline))
```

### 6.2 Date Parsing in Aggregations

Use MongoDB `$dateFromString` for robust date parsing instead of `$substr`:

```python
{"$project": {
    "parsed_date": {
        "$dateFromString": {
            "dateString": "$invoice_date",
            "format": "%Y-%m-%dT%H:%M:%S",
            "onError": null,
            "onNull": null,
        }
    },
    "month": {"$month": "$parsed_date"},
    "year": {"$year": "$parsed_date"},
}}
```

### 6.3 Period Bucketing

For chart data, use `$bucket` or `$bucketAuto` in aggregation:

```python
{"$bucket": {
    "groupBy": "$month",
    "boundaries": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "default": "Other",
    "output": {
        "revenue": {"$sum": "$totalprice"},
        "count": {"$sum": 1},
    }
}}
```

---

## 7. Export Pipeline

### 7.1 Export Types

| Type | Source Collection | Fields |
|------|------------------|--------|
| `financials` | Merged: inwardinvoices + paymentvouchers | date, description, type, amount, reference |
| `inward-invoices` | inwardinvoices | invoice_no, invoice_date, vendor, totalprice, taxes |
| `outward-invoices` | outwardinvoices | invoice_no, invoice_date, customer, totalprice, taxes |
| `inward-payments` | inwardpayments | payment_no, payment_date, invoice_no, amount, status |

### 7.2 Export Formats

| Format | Content-Type | Processing |
|--------|-------------|------------|
| `json` | `application/json` | Direct JSON serialization |
| `csv` | `text/csv` | CSV with headers, escaped values |

### 7.3 Export Limits

| Parameter | Default | Max | Configurable |
|-----------|---------|-----|-------------|
| `max_rows` | 10,000 | 100,000 | Via `BusinessGroup` settings |
| `timeout` | 30s | 120s | Via Django settings |

### 7.4 Large Export Handling

For exports exceeding `max_rows`:
1. Return error with `X-Export-Too-Large` header
2. Client can request background export via `POST /accounts/export/{type}/async`
3. Background task generates file, stores in temporary location
4. Webhook/notification when ready

---

## 8. Observability

### 8.1 Correlation IDs

Every request gets a `X-Correlation-Id` header:
- Client-provided ID preserved if sent
- Otherwise, UUID generated by `CorrelationIdMiddleware`
- Included in all response `meta.correlation_id`
- Logged on every query

### 8.2 Structured Logging

Replace `sys.stderr.write` with structlog:

```python
# Instead of:
sys.stderr.write(f"[Analytics] period={period}, total_orders={count}\n")

# Use:
self.logger.info(
    "analytics_query",
    correlation_id=self.correlation_id,
    period=period.label,
    total_orders=count,
    rows_scanned=scan_count,
    duration_ms=elapsed_ms,
)
```

### 8.3 Query Timing

All reporting endpoints log query timing:

```python
import time
start = time.monotonic()
results = decode_result(collection.find(filters))
elapsed_ms = (time.monotonic() - start) * 1000
```

### 8.4 Health Check

```
GET /shared/health/reports
→ {
    "status": "ok",
    "collections": {
      "inwardinvoices": {"status": "ok", "document_count": 45230},
      "inwardpayments": {"status": "ok", "document_count": 38901},
      ...
    },
    "checks": [
      {"name": "mongo_connection", "status": "ok"},
      {"name": "tenant_resolution", "status": "ok"},
    ]
  }
```

---

## 9. Migration Plan

### Phase 0: Thin Layer (prerequisite)

| Item | Canonical Module | Status |
|------|----------------|--------|
| PeriodParser | `backend/periods.py` | ✅ Created |
| reporting_response | `backend/response_utils.py` | ✅ Added |
| ReportingViewSet | `backend/reporting_base.py` | ✅ Created |
| CorrelationIDMiddleware | `plat/observability/middleware.py` | ✅ Exists (no new code) |
| StructuredFormatter | `plat/observability/logging.py` | ✅ Exists (no new code) |
| TenantConfig | `plat/tenant/config.py` | ✅ Exists (no new code) |
| TenantCollection | `plat/tenant/collection.py` | ✅ Exists (no new code) |
| **Imports from** | `backend/auth_utils.py` | `resolve_access()`, `has_read_access()`, `has_write_access()` |
| **Imports from** | `backend/utils.py` | `get_collection()`, `find_all()`, `decode_result()` |
| **Imports from** | `backend/response_utils.py` | `error_response()` |
| **Imports from** | `backend/exceptions.py` | `InputException` |
| **Imports from** | `users/cookie_auth.py` | `CookieJWTAuthentication` |
| **Imports from** | `users/permissions.py` | `has_permission()` |

### Phase 1: Fix Broken Contracts

| Item | Endpoint | Fix | Status |
|------|----------|-----|--------|
| Financials format | `accounts/financials` | Return `{date, description, type, amount, reference}` list | ✅ Fixed |
| Export path alias | `accounts/export` | Added dynamic `export_data` action with `type` param | ✅ Fixed |
| Sales collection | `accounts/revenue` | Fixed: queries `outwardInvoices` (was `outwardDebitNotes`) | ✅ Fixed |
| Envelope compatibility | All reporting | Added `reportingFetcher()` — unwraps `{data, meta}` | ✅ Fixed |
| Code param standardization | All reporting | `division`→`div_code`, `branch`→`branch_code` | ✅ Fixed |

### Phase 2: Migrate Endpoints

| Item | Endpoint | ViewSet | Canonical Module |
|------|----------|---------|----------------|
| Analytics | `shared/analytics` | `SharedViewSet.analytics()` | `kungos_dj/domains/shared/views.py` |
| Financials | `accounts/financials` | `FinancialsViewSet` | `kungos_dj/domains/accounts/views.py` |
| ITC-GST | `accounts/itc-gst` | `ITCGSTViewSet` | `kungos_dj/domains/accounts/views.py` |
| Revenue | `accounts/revenue` | `RevenueViewSet` | `kungos_dj/domains/accounts/views.py` |
| Expenditure | `accounts/expenditure` | `ExpenditureViewSet` | `kungos_dj/domains/accounts/views.py` |
| Export | `accounts/export/*` | `ExportViewSet` | `kungos_dj/domains/accounts/views.py` |

### Phase 3: Add Missing Reports

| Item | Endpoint | ViewSet | Canonical Module |
|------|----------|---------|----------------|
| P&L | `accounts/profit-loss` | `ProfitLossViewSet` | `kungos_dj/domains/accounts/views.py` |
| Balance Sheet | `accounts/balance-sheet` | `BalanceSheetViewSet` | `kungos_dj/domains/accounts/views.py` |
| Inventory Valuation | `products/inventory/valuation` | `InventoryValuationViewSet` | `kungos_dj/domains/products/views.py` |

### Phase 4: Cleanup

| Item | Description |
|------|-------------|
| Remove legacy FBVs | `teams/financial.py`, `teams/analytics.py` |
| Remove debug logs | `sys.stderr.write` calls |
| Consolidate aggregations | 21 queries → 1 pipeline |
| Add tests | Unit tests for PeriodParser, ReportingViewSet |

---

## 10. Appendix: Period Formats

### 10.1 Period String → Label Mapping

| Input | Period Type | Label Format | Example |
|-------|------------|-------------|---------|
| `daily` | daily | `HH:MM` (4-hour blocks) | `14:00` |
| `weekly` | weekly | `Day DD` | `Mon 15` |
| `monthly` / `curr_month` | monthly | `Mon` (3-letter) | `Jan` |
| `last_month` | monthly | `Mon` (3-letter) | `Dec` |
| `quarterly` / `curr_quarter` | quarterly | `Q# YYYY` | `Q1 2024` |
| `last_quarter` | quarterly | `Q# YYYY` | `Q4 2023` |
| `yearly` / `curr_fy` | yearly | `FY YYYY-YYYY` | `FY 2024-2025` |
| `last_fy` | yearly | `FY YYYY-YYYY` | `FY 2023-2024` |
| `start_date` + `end_date` | custom | `DD Mon – DD Mon` | `01 Jan – 31 Mar` |

### 10.2 Financial Year (India)

- April 1 → March 31
- `curr_fy`: If current month ≥ April → `FY {current_year}-{current_year+1}`, else `FY {current_year-1}-{current_year}`
- `last_fy`: Shift back one year

### 10.3 Recharts Period Labels

| Period Type | XAxis Label | Tooltip Format |
|------------|-------------|---------------|
| daily | `14:00` | `14:00 — ₹75,000` |
| weekly | `Mon 15` | `Mon 15 — ₹4,50,000` |
| monthly | `Jan` | `Jan — ₹12,50,000` |
| quarterly | `Q1 2024` | `Q1 2024 — ₹35,00,000` |
| yearly | `2024` | `2024 — ₹1,25,00,000` |

---

## 11. Appendix: Standardized Code Conventions

### 11.1 Use Codes — Never Labels

**Rule:** All endpoint communication uses codes (`bg_code`, `div_code`, `branch_code`). Labels are display-only, resolved by frontend.

| Context | Code (used in API) | Label (display only) |
|---------|-------------------|---------------------|
| Business Group | `bg_code: "KURO0001"` | `"Kuro Technologies"` |
| Division | `div_code: "KURO0001_001"` | `"Bangalore Division"` |
| Branch | `branch_code: "BR001"` | `"Main Branch"` |
| Vendor | `vendor_code: "AMAZ290010"` | `"Amazon Web Services"` |
| Product | `product_code: "LP-001"` | `"Dell Latitude 5420"` |
| Asset | `asset_no: "AST-2024-001"` | `"Office Laptop #1"` |

**Why:** Codes are stable, unique, and tenant-scoped. Labels change, duplicate, and are language-dependent.

### 11.2 Endpoint Parameter Naming

| ❌ Before | ✅ After | Rationale |
|-----------|----------|----------|
| `?division=Bangalore` | `?div_code=KURO0001_001` | Code, not label |
| `?branch=Main` | `?branch_code=BR001` | Code, not label |
| `?bgCode=KURO0001` | `?bg_code=KURO0001` | snake_case, not camelCase |
| `?vendorCode=AMAZ290010` | `?vendor_code=AMAZ290010` | snake_case, not camelCase |
| `?deleteFlag=true` | `?delete_flag=true` | snake_case, not camelCase |

### 11.3 Response Field Naming

All response fields use snake_case. Codes are always present; labels are optional display fields.

```json
{
  "bg_code": "KURO0001",
  "div_code": "KURO0001_001",
  "branch_code": "BR001",
  "vendor_code": "AMAZ290010",
  "vendor_name": "Amazon Web Services",
  "product_code": "LP-001",
  "product_name": "Dell Latitude 5420",
  "delete_flag": false
}
```

### 11.4 Frontend Label Resolution

Frontend resolves codes → labels via tenant endpoints:

```js
// Resolve div_code → display label
const divisions = useQuery({
  queryKey: queryKeys.tenant.divisions,
  queryFn: () => api.get('/tenant/divisions'),
});

const divisionLabel = divisions.data?.find(d => d.div_code === div_code)?.name;

// Resolve branch_code → display label
const branches = useQuery({
  queryKey: queryKeys.tenant.branches,
  queryFn: () => api.get('/tenant/branches'),
});

const branchLabel = branches.data?.find(b => b.branch_code === branch_code)?.name;
```

### 11.5 Canonical Import Map

All reporting endpoints import from these canonical modules:

| Import | From | Purpose |
|--------|------|---------|
| `resolve_access(request)` | `backend/auth_utils.py` | Full tenant context |
| `resolve_minimal(request)` | `backend/auth_utils.py` | Lightweight tenant context |
| `has_read_access(access_dict, field)` | `backend/auth_utils.py` | Read permission check |
| `has_write_access(access_dict, field)` | `backend/auth_utils.py` | Write permission check |
| `check_access(user_access, field, access_dict)` | `backend/auth_utils.py` | Permission check by codename |
| `check_write_access(user_access, field, access_dict, level)` | `backend/auth_utils.py` | Write permission with level |
| `get_collection(name, bg_code, div_code, branch_code)` | `backend/utils.py` | MongoDB collection + tenant filter |
| `find_all(name, filters, bg_code, div_code, branch_code, ...)` | `backend/utils.py` | Query with tenant filtering |
| `decode_result(cursor)` | `backend/utils.py` | Decode MongoDB cursor |
| `resolve_access_levels(access_query, bg_code)` | `backend/utils.py` | Resolve access levels |
| `error_response(exc, raise_internal)` | `backend/response_utils.py` | Standardized error response |
| `InputException` | `backend/exceptions.py` | Input validation exception |
| `CookieJWTAuthentication` | `users/cookie_auth.py` | Cookie-based JWT auth |
| `has_permission(user, codename)` | `users/permissions.py` | RBAC permission check |
| `BusinessGroup` | `tenant/models.py` | BG model (bg_code, db_name, brand) |
| `Division` | `tenant/models.py` | Division model (div_code, cascade) |
| `Branch` | `tenant/models.py` | Branch model (branch_code) |
| `PeriodParser` | `backend/periods.py` | Period/duration parsing (new) |
| `reporting_response(data, meta)` | `backend/response_utils.py` | Standardized report envelope (new) |
| `ReportingViewSet` | `backend/reporting_base.py` | Base mixin (new) |
| `CorrelationIdMiddleware` | `backend/middleware.py` | Request tracing (new) |
