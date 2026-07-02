# Analytics & Reporting System — Unified Specification

**Date:** 2026-07-02  
**Version:** 1.0  
**Status:** Draft  
**Priority:** High  

---

## 🎯 **Objective**

Design a unified analytics & reporting system that:
1. **Resolves all audit issues** (Financials format, export paths, sales_func)
2. **Eliminates inherent conflicts** (MongoDB vs PostgreSQL, hybrid queries)
3. **Provides optimal performance** (single query pipelines, caching)
4. **Maintains backward compatibility** (frontend contracts unchanged)
5. **Enables future extensibility** (P&L, Balance Sheet, Customer Analytics)

---

## 📊 **Current State Analysis**

### Audit Issues Summary

| # | Issue | Severity | Root Cause |
|---|-------|----------|------------|
| C1 | `financials` returns monthly dict, frontend expects flat list | 🔴 Critical | Backend-frontend contract mismatch |
| C2 | Export paths: `inwardinvoices` vs `inward-invoices` | 🔴 Critical | URL routing inconsistency |
| C3 | `sales_func` queries wrong doc_type | 🟡 High | Verify `outward_invoice` doc_type |
| H1 | `financials` ignores `period` param | 🟡 High | Missing parameter handling |
| H2 | `bulk-payments` endpoint never called | 🟡 High | Dead code |
| H3 | `accounts/analytics` duplicates `shared/analytics` | 🟡 Medium | Duplication |
| H4 | Cafe `dashboard/revenue` not implemented | 🟡 High | Missing feature |
| M1 | `analytics` has `sys.stderr.write` debug logs | 🟢 Medium | Code quality |
| M2 | `analytics` has hardcoded `days_to_pay = 15` | 🟢 Medium | Incorrect metric |
| M3 | `itc_gst` tax extraction is naive | 🟢 Medium | Business logic |
| M5 | `sales_func`/`purchases_func` make 21 separate queries | 🟢 Medium | Performance |
| M6 | No pagination on analytics/reporting | 🟢 Medium | Scalability |

### Architectural Issues

1. **Hybrid Data Access Pattern**
   - Some endpoints use MongoDB (`financial_documents`)
   - Some use PostgreSQL (`orders_core`)
   - No consistent abstraction layer

2. **Duplicated Code**
   - `resolve_access()` called in every FBV
   - `get_collection()` called manually
   - Period parsing duplicated across endpoints

3. **Inconsistent Response Formats**
   - `financials` returns monthly dict
   - `analytics` returns flat object
   - `sales`/`purchases` return 21-key dict

4. **Missing Infrastructure**
   - No `ReportingViewSet` mixin
   - No `PeriodParser` utility
   - No standardized response envelope
   - No correlation IDs for debugging

---

## 🏗️ **Proposed Architecture**

### Core Principles

1. **Single Source of Truth** — One data access pattern per domain
2. **Consistent Abstraction** — `ReportingViewSet` mixin for all reporting
3. **Unified Finance Collection** — All financial docs in `financial_documents` (KungOS_Mongo_One)
4. **Frontend-First Design** — All endpoints match frontend contracts exactly
5. **Performance by Default** — Single query pipelines, caching, pagination

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (KungOS-FE-Team)                 │
│  Analytics.jsx | Financials.jsx | ITCGST.jsx | CafeDashboard.jsx │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   ReportingViewSet (Mixin)                   │
│  - resolve_access() | get_collection() | parse_period()     │
│  - reporting_response() | correlation_id | structured log   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Data Access Layer (Unified)                     │
│  ┌──────────────────────────────────────────────────┐       │
│  │  KungOS_Mongo_One.financial_documents            │       │
│  │  (Unified collection with doc_type field)        │       │
│  │                                                  │       │
│  │  doc_types:                                      │       │
│  │  - inward_payment (3,188)                        │       │
│  │  - inward_invoice (4,750)                        │       │
│  │  - payment_voucher (3,715)                       │       │
│  │  - outward_invoice (1,192)                       │       │
│  │  - inward_credit_note (109)                      │       │
│  │  - inward_debit_note (3)                         │       │
│  │  - outward_credit_note (44)                      │       │
│  │  - outward_debit_note (13)                       │       │
│  └──────────────────────────────────────────────────┘       │
│  ┌──────────────────────────────────────────────────┐       │
│  │  KungOS_PG_One (PostgreSQL)                      │       │
│  │  - orders_core (estimates, tp, purchase)         │       │
│  │  - inv_purchase_orders (vendor data)             │       │
│  │  - inventory_inventorystock                      │       │
│  │  - users_customer                                │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📐 **Data Access Strategy**

### MongoDB (Unified Finance Collection)

**Collection:** `financial_documents` in `KungOS_Mongo_One`

**Rationale:**
- **Unified collection** — All financial docs in one place
- **Normalized schema** — `doc_type` field distinguishes document types
- **Proper tenant scoping** — `bg_code`, `div_code`, `branch_code` fields
- **MongoDB aggregation** — Optimal for financial reports

**Document Types (8 total, 14,264 documents):**
| doc_type | Count | Description |
|----------|-------|-------------|
| `inward_payment` | 3,188 | Inward payments (revenue) |
| `inward_invoice` | 4,750 | Inward invoices (purchases/expenses) |
| `payment_voucher` | 3,715 | Payment vouchers (expenses) |
| `outward_invoice` | 1,192 | Outward invoices (sales/revenue) |
| `inward_credit_note` | 109 | Inward credit notes |
| `inward_debit_note` | 3 | Inward debit notes |
| `outward_credit_note` | 44 | Outward credit notes |
| `outward_debit_note` | 13 | Outward debit notes |

**Unified Schema:**
```javascript
{
  _id: ObjectId,
  doc_type: 'inward_payment',           // NORMALIZED TYPE
  
  // Tenant scoping (PROPER FIELDS)
  bg_code: 'KURO0001',
  div_code: 'KURO0001_001',
  branch_code: 'KURO0001_001_001',
  
  // Metadata
  active: true,
  delete_flag: false,
  created_date: '02-01-2025, 09:45:53',
  
  // Document-specific fields (varies by doc_type)
  // inward_payment: amount_paid, status, payments[], orderid
  // inward_invoice: totalprice, pay_status, invoice_no, vendor, gstin
  // payment_voucher: amount, pay_date, vendor, pv_no
  // outward_invoice: totalprice, invoice_date, user, products[]
}
```

**Access Pattern:**
```python
class FinanceDataAccess:
    """MongoDB data access for unified financial_documents collection.
    
    Uses single collection with doc_type filter.
    Uses bg_code/div_code/branch_code for tenant scoping.
    """
    
    def __init__(self, bg_code, div_code=None, branch_code=None):
        self.bg_code = bg_code
        self.div_code = div_code
        self.branch_code = branch_code
    
    def get_collection(self):
        """Get financial_documents collection."""
        return get_collection('financial_documents', bg_code=self.bg_code)
    
    def build_filter(self, doc_type=None):
        """Build tenant + doc_type filter."""
        filter_dict = {
            'bg_code': self.bg_code,
            'active': True,
            'delete_flag': False,
        }
        if self.div_code:
            filter_dict['div_code'] = self.div_code
        if self.branch_code:
            filter_dict['branch_code'] = self.branch_code
        if doc_type:
            filter_dict['doc_type'] = doc_type
        return filter_dict
    
    def aggregate(self, pipeline):
        """Run aggregation pipeline on collection."""
        collection = self.get_collection()
        return decode_result(collection.aggregate(pipeline))
```

### PostgreSQL (Transaction Data)

**Tables:**
- `orders_core` — All orders (in_store, tp, estimate, service, purchase)
- `indent` / `indent_item` — Indent records
- `inventory_inventorystock` — Stock register
- `users_customer` — Customer profiles
- `inv_vendors` — Vendor profiles

**Rationale:**
- Transactional data benefits from relational integrity
- PostgreSQL JOINs optimize complex queries
- Existing Django ORM models

**Access Pattern:**
```python
class TransactionDataAccess:
    """PostgreSQL data access for transaction tables."""
    
    def __init__(self, bg_code, division=None, branch=None):
        self.bg_code = bg_code
        self.division = division
        self.branch = branch
    
    def get_orders(self, order_type=None):
        """Query OrderCore with tenant scoping."""
        qs = OrderCore.objects.filter(
            bg_code=self.bg_code,
            delete_flag=False,
            active=True
        )
        if order_type:
            qs = qs.filter(order_type=order_type)
        if self.division:
            qs = qs.filter(div_code=self.division)
        if self.branch:
            qs = qs.filter(branch_code=self.branch)
        return qs
```

---

## 🔌 **ReportingViewSet Mixin**

### Base Class

```python
# domains/reporting/base.py

class ReportingViewSet(viewsets.GenericViewSet):
    """Thin mixin for reporting endpoints.
    
    Plugs into existing KungOS v2 primitives:
      - resolve_access() for tenant context
      - get_collection() for MongoDB access
      - TransactionDataAccess for PostgreSQL access
      - CookieJWTAuthentication for auth
      - check_access() for permissions
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    # Override per-endpoint
    ALLOWED_PERIODS = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']
    DEFAULT_PERIOD = 'monthly'
    
    def initial(self, request, *args, **kwargs):
        """Resolve tenant context once."""
        super().initial(request, *args, **kwargs)
        self.tenant_context = resolve_access(request)
        self.correlation_id = request.META.get('HTTP_X_CORRELATION_ID') or uuid4().hex
        self.bg = self.tenant_context['bg']
        self.division = self.tenant_context.get('division')
        self.branch = self.tenant_context.get('branch')
    
    def get_collection(self, name):
        """MongoDB collection with tenant scoping."""
        return get_collection(
            name,
            bg_code=self.bg.bg_code,
            division=self.division,
            branch=self.branch,
        )
    
    def get_transaction_access(self):
        """PostgreSQL transaction data access."""
        return TransactionDataAccess(
            bg_code=self.bg.bg_code,
            division=self.division,
            branch=self.branch,
        )
    
    def parse_period(self, request):
        """Parse period/duration → Period object."""
        period = request.query_params.get('period',
                    request.query_params.get('duration', self.DEFAULT_PERIOD))
        return PeriodParser.parse(period, self.ALLOWED_PERIODS)
    
    def reporting_response(self, data, meta=None):
        """Standardized {data, meta} envelope."""
        return reporting_response(data, meta={
            'period': meta.get('period', self.DEFAULT_PERIOD),
            'correlation_id': self.correlation_id,
            'generated_at': datetime.now(timezone('Asia/Kolkata')).isoformat(),
            **(meta or {}),
        })
    
    def log(self, level, event, **kwargs):
        """Structured logging with correlation ID."""
        logger = structlog.get_logger()
        log_data = {'correlation_id': self.correlation_id, **kwargs}
        getattr(logger, level)(event, **log_data)
```

---

## 📋 **Endpoint Specifications**

### 1. `GET /shared/analytics` — Dashboard Analytics

**Frontend:** `Analytics.jsx`  
**ViewSet:** `SharedViewSet` (extends `ReportingViewSet`)

**Query Params:**
- `period` (daily/weekly/monthly/quarterly/yearly)
- `div_code` (division code, optional)
- `branch_code` (branch code, optional)

**Response Contract:**
```javascript
{
  totalRevenue: number,
  totalExpenses: number,
  profitMargin: number,
  avgInvoiceValue: number,
  daysToPay: number,
  overdueAmount: number,
  totalOrders: number,
  totalEstimates: number,
  totalTPOrders: number,
  statusBreakdown: {Paid: N, Pending: N, ...},
  chartData: [{period, revenue, expenses, orders}],
  paymentTrend: [{period, paid, pending}],
  vendors: [{name, amount, percentage}],
  monthlyData: [...],
  period: string
}
```

**Data Sources:**
| Field | Source | Access |
|-------|--------|--------|
| `totalRevenue` | `financial_documents` (`doc_type='inward_payment'`) | MongoDB |
| `totalExpenses` | `financial_documents` (`doc_type='payment_voucher'`) | MongoDB |
| `totalOrders` | `financial_documents` (`doc_type='inward_payment'`) | MongoDB |
| `totalEstimates` | `orders_core` (order_type='estimate') | PostgreSQL |
| `totalTPOrders` | `orders_core` (order_type='tp') | PostgreSQL |
| `statusBreakdown` | `financial_documents` (`doc_type='inward_payment'`) | MongoDB |
| `chartData` | `financial_documents` (`inward_payment` + `payment_voucher`) | MongoDB |
| `paymentTrend` | `financial_documents` (`doc_type='inward_payment'`) | MongoDB |
| `vendors` | `orders_core` (order_type='purchase') or `inv_purchase_orders` | PostgreSQL |

**Implementation Notes:**
- ✅ **USE unified collection** — `financial_documents` with `doc_type` filter
- ✅ **USE proper tenant fields** — `bg_code`, `div_code`, `branch_code`
- ✅ **USE `amount_paid`** for revenue (from `inward_payment` docs)
- ✅ **USE `amount`** for expenses (from `payment_voucher` docs)
- ✅ **USE `inv_purchase_orders`** with JOIN for vendor data
- ✅ **FIX:** Remove hardcoded `days_to_pay = 15` (calculate from payment dates)
- ✅ **FIX:** Remove `sys.stderr.write` debug logs
- ✅ **OPTIMIZE:** Add database indexes for `orders_core(order_type, active, delete_flag)`

**Unified Schema Notes:**
```javascript
// financial_documents collection (UNIFIED)
{
  doc_type: 'inward_payment',     // ← Filter by this
  bg_code: 'KURO0001',           // ← Proper tenant scoping
  div_code: 'KURO0001_001',
  branch_code: 'KURO0001_001_001',
  amount_paid: 2600,             // ← For revenue
  status: 'Paid',                // ← For statusBreakdown
  created_date: '02-01-2025, 09:45:53',
  active: true,
  delete_flag: false
}

// financial_documents with doc_type='payment_voucher' (EXPENSES)
{
  doc_type: 'payment_voucher',
  bg_code: 'KURO0001',
  amount: 211593,                // ← For expenses
  pay_date: '2021-12-16T...',
  vendor: 'ACRO33000D',
  active: true,
  delete_flag: false
}

// inv_purchase_orders schema (VENDORS - PostgreSQL)
{
  po_no: 'KUROACRO23002Q',
  vendor_code: 'ACRO33000D',    // ← FK to inv_vendors
  total_amount: 26577,
  bg_code: 'KURO0001',
  div_code: 'KURO0001_001',
  branch_code: 'KURO0001_001_001'
}
```

---

### 2. `GET /accounts/financials` — Financial Reports

**Frontend:** `Financials.jsx`  
**ViewSet:** `FinancialsViewSet` (extends `ReportingViewSet`)

**Query Params:**
- `period` (daily/weekly/monthly/quarterly/yearly) — **WILL BE SUPPORTED**
- `duration` (alias for period)

**Response Contract (FIXED):**
```javascript
[
  {
    date: "2024-01-15",
    description: "Invoice #INV-001",
    category: "Sales",
    type: "income",  // "income" | "expense"
    amount: 50000,
    reference: "INV-001"
  },
  // ... more transactions
]
```

**Current Issue (C1):** Backend returns monthly dict `[{ "2024-Jan": {...} }]`  
**Fix:** Return flat transaction list with `type` field

**Data Sources:**
| Type | Source | Access |
|------|--------|--------|
| Income | `financial_documents` (`doc_type='inward_invoice'`) | MongoDB |
| Expense | `financial_documents` (`doc_type='payment_voucher'`) | MongoDB |

**Implementation Notes:**
- ✅ **FIX:** Return flat transaction list (not monthly dict)
- ✅ **FIX:** Support `period` query parameter
- ✅ **FIX:** Add `type: "income" | "expense"` field
- ✅ **USE unified collection** — `financial_documents` with `doc_type` filter
- ✅ **OPTIMIZE:** Single aggregation pipeline (not 3 separate queries)

**Unified Schema Notes:**
```javascript
// financial_documents with doc_type='inward_invoice' (INCOME)
{
  doc_type: 'inward_invoice',
  bg_code: 'KURO0001',
  invoiceid: 'SHWE20001J',
  vendor: 'SHWE360001',
  invoice_no: '026762',
  invoice_date: '2020-09-16T00:00:00.000000+0530',
  totalprice: 51700,
  pay_status: 'Paid',
  itc_received: 'Yes',
  active: true,
  delete_flag: false
}

// financial_documents with doc_type='payment_voucher' (EXPENSE)
{
  doc_type: 'payment_voucher',
  bg_code: 'KURO0001',
  amount: 211593,
  pay_date: '2021-12-16T...',
  vendor: 'ACRO33000D',
  pv_no: 'KUROACRO220019',
  active: true,
  delete_flag: false
}
```

---

### 3. `GET /accounts/itc-gst` — GST Compliance

**Frontend:** `ITCGST.jsx`  
**ViewSet:** `ITCGSTViewSet` (extends `ReportingViewSet`)

**Query Params:**
- `period` (monthly/quarterly/yearly)

**Response Contract:**
```javascript
[
  {
    invoice_no: "INV-001",
    gstin: "27AAAACCP1234D1Z5",
    invoice_date: "2024-01-15",
    igst: 5000,
    cgst: 2500,
    sgst: 2500,
    itc_amount: 10000,
    gst_amount: 10000,
    utilized: 0,
    status: "Claimed"  // "Claimed" | "Pending" | "Rejected"
  }
]
```

**Data Sources:**
| Field | Source | Access |
|-------|--------|--------|
| All fields | `inwardinvoices` | MongoDB |

**Implementation Notes:**
- ✅ **FIX:** Improve tax extraction logic (handle non-28% rates)
- ✅ **FIX:** Track `utilized` field (currently always 0)

---

### 4. `GET /accounts/revenue` — Revenue (Sales)

**Frontend:** Not directly called (used via export)  
**ViewSet:** `RevenueViewSet` (extends `ReportingViewSet`)

**Response Contract:**
```javascript
{
  invoice_curmonth: number,
  credit_curmonth: number,
  debit_curmonth: number,
  invoice_lastmonth: number,
  // ... 21 keys total
}
```

**Current Issue (C3):** `sales_func` queries wrong `doc_type`  
**Fix:** Verify `outward_invoice` doc_type is correct

**Data Sources:**
| Field | Source | Access |
|-------|--------|--------|
| All fields | `financial_documents` (`doc_type='outward_invoice'`) | MongoDB |

**Implementation Notes:**
- ✅ **FIX:** Verify correct collection name
- ✅ **OPTIMIZE:** Reduce 21 queries to 1 aggregation pipeline

---

### 5. `GET /accounts/expenditure` — Expenditure (Purchases)

**Frontend:** Not directly called (used via export)  
**ViewSet:** `ExpenditureViewSet` (extends `ReportingViewSet`)

**Response Contract:**
```javascript
{
  invoice_curmonth: number,
  credit_curmonth: number,
  debit_curmonth: number,
  invoice_lastmonth: number,
  // ... 21 keys total
}
```

**Data Sources:**
| Field | Source | Access |
|-------|--------|--------|
| All fields | `inwardinvoices` | MongoDB |

**Implementation Notes:**
- ✅ **OPTIMIZE:** Reduce 21 queries to 1 aggregation pipeline

---

### 6. `GET /cafe/dashboard/revenue` — Cafe Revenue (NEW)

**Frontend:** `CafeDashboard.jsx`  
**ViewSet:** `CafeViewSet.dashboard_revenue()` (extends `ReportingViewSet`)

**Response Contract:**
```javascript
{
  totalRevenue: number,
  totalOrders: number,
  avgOrderValue: number,
  topProducts: [{name, revenue, orders}],
  hourlyTrend: [{hour, revenue, orders}],
  dailyTrend: [{date, revenue, orders}]
}
```

**Data Sources:**
| Field | Source | Access |
|-------|--------|--------|
| `totalRevenue` | `financial_documents` (`doc_type='inward_payment'`) | MongoDB |
| `topProducts` | `products` + `financial_documents` | MongoDB |

**Implementation Notes:**
- ✅ **NEW:** Implement cafe revenue endpoint
- ✅ **FIX:** Wire up `CafeDashboard.jsx` frontend

---

### 7. Export Endpoints

**Current Issue (C2):** Frontend sends `accounts/inwardinvoices`, backend expects `accounts/inward-invoices`  
**Fix:** Add alias routes

**Routes:**
```python
# accounts/urls.py
urlpatterns = [
    path('financials', FinancialsViewSet.as_view({'get': 'list'}), name='financials'),
    path('financials/<str:duration>', FinancialsViewSet.as_view({'get': 'export'}), name='financials-export'),
    
    # Alias routes (no hyphen)
    path('inwardinvoices', InwardInvoicesViewSet.as_view({'get': 'list'}), name='inward-invoices'),
    path('inwardinvoices/<str:duration>', InwardInvoicesViewSet.as_view({'get': 'export'}), name='inward-invoices-export'),
    
    # Hyphenated routes (canonical)
    path('inward-invoices', InwardInvoicesViewSet.as_view({'get': 'list'}), name='inward-invoices'),
    path('inward-invoices/<str:duration>', InwardInvoicesViewSet.as_view({'get': 'export'}), name='inward-invoices-export'),
    
    # ... similar for other doc_types
]
```

---

## 🗂️ **Database Indexes**

### PostgreSQL Indexes

```sql
-- OrderCore indexes (critical for analytics)
CREATE INDEX idx_ordercore_type_active 
  ON orders_core(order_type, active, delete_flag);

CREATE INDEX idx_ordercore_bg_div 
  ON orders_core(bg_code, div_code);

CREATE INDEX idx_ordercore_bg_branch 
  ON orders_core(bg_code, branch_code);

CREATE INDEX idx_ordercore_created 
  ON orders_core(created_date);

CREATE INDEX idx_ordercore_type_created 
  ON orders_core(order_type, created_date);

-- Inventory indexes
CREATE INDEX idx_inventory_stock_bg 
  ON inventory_inventorystock(bg_code);

CREATE INDEX idx_inventory_stock_div 
  ON inventory_inventorystock(div_code);
```

### MongoDB Indexes

```javascript
// financial_documents (unified collection)
db.financial_documents.createIndex({ "doc_type": 1, "bg_code": 1, "created_date": -1 })
db.financial_documents.createIndex({ "status": 1 })
db.financial_documents.createIndex({ "pay_status": 1 })
db.financial_documents.createIndex({ "div_code": 1 })
db.financial_documents.createIndex({ "branch_code": 1 })
```

---

## ✅ **SCHEMA GAPS RESOLVED (Unified Collection)**

All schema gaps have been resolved by using the unified `financial_documents` collection in `KungOS_Mongo_One`.

### Resolution: Unified Collection Architecture

**Architecture:**
- **Single collection:** `financial_documents` in `KungOS_Mongo_One`
- **Normalized type:** `doc_type` field (`inward_payment`, `inward_invoice`, `payment_voucher`, etc.)
- **Proper tenant scoping:** `bg_code`, `div_code`, `branch_code`
- **All data migrated:** 14,264 documents across 8 doc_types

### Verified Document Counts

```javascript
> db.financial_documents.aggregate([
    { $group: { _id: '$doc_type', count: { $sum: 1 } } }
  ])

inward_invoice: 4750
inward_payment: 3188
payment_voucher: 3715
outward_invoice: 1192
inward_credit_note: 109
outward_credit_note: 44
outward_debit_note: 13
inward_debit_note: 3
Total: 14,264
```

### Unified Access Pattern

```python
class FinanceDataAccess:
    """Access unified financial_documents collection."""
    
    def __init__(self, bg_code, div_code=None, branch_code=None):
        self.bg_code = bg_code
        self.div_code = div_code
        self.branch_code = branch_code
    
    def get_revenue_docs(self):
        """Get inward_payment documents (revenue)."""
        return self.build_filter(doc_type='inward_payment')
    
    def get_expense_docs(self):
        """Get payment_voucher documents (expenses)."""
        return self.build_filter(doc_type='payment_voucher')
    
    def get_income_docs(self):
        """Get inward_invoice documents (income)."""
        return self.build_filter(doc_type='inward_invoice')
    
    def get_sales_docs(self):
        """Get outward_invoice documents (sales)."""
        return self.build_filter(doc_type='outward_invoice')
    
    def build_filter(self, doc_type=None):
        """Build unified filter."""
        filter_dict = {
            'bg_code': self.bg_code,
            'active': True,
            'delete_flag': False,
        }
        if self.div_code:
            filter_dict['div_code'] = self.div_code
        if self.branch_code:
            filter_dict['branch_code'] = self.branch_code
        if doc_type:
            filter_dict['doc_type'] = doc_type
        return filter_dict
```

---

## 📦 **Caching Strategy**

### Redis Cache (Read-Heavy Reporting)

**TTL Configuration:**
| Endpoint | TTL | Rationale |
|----------|-----|-----------|
| `shared/analytics` | 5 minutes | Dashboard, frequently refreshed |
| `accounts/financials` | 15 minutes | Financial reports, less frequent |
| `accounts/itc-gst` | 30 minutes | GST compliance, monthly updates |
| `accounts/revenue` | 15 minutes | Revenue reports |
| `accounts/expenditure` | 15 minutes | Expenditure reports |
| `cafe/dashboard/revenue` | 5 minutes | Cafe dashboard, real-time |

**Cache Key Pattern:**
```python
def cache_key(self, endpoint, params):
    """Generate cache key from endpoint + params."""
    key_parts = [
        'reporting',
        endpoint,
        self.bg.bg_code,
        self.division or 'all',
        self.branch or 'all',
        params.get('period', 'monthly'),
    ]
    return ':'.join(key_parts)
```

**Cache Invalidation:**
- Manual invalidation on data changes (POST/PUT/DELETE)
- Automatic TTL expiration
- Cache warming on system startup

---

## 📊 **Pagination Strategy**

### Large Dataset Endpoints

**Endpoints Requiring Pagination:**
- `accounts/financials` — Transaction list
- `accounts/itc-gst` — Invoice list
- `accounts/revenue` — Export data
- `accounts/expenditure` — Export data

**Pagination Contract:**
```javascript
{
  data: [...],
  pagination: {
    page: 1,
    per_page: 100,
    total: 1500,
    total_pages: 15,
    has_next: true,
    has_prev: false
  }
}
```

**Implementation:**
```python
def paginate(self, queryset, request, per_page=100):
    """Apply pagination to queryset."""
    page = int(request.query_params.get('page', 1))
    per_page = min(int(request.query_params.get('per_page', per_page)), 1000)
    
    total = queryset.count()
    total_pages = (total + per_page - 1) // per_page
    
    start = (page - 1) * per_page
    end = start + per_page
    data = queryset[start:end]
    
    return {
        'data': data,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        }
    }
```

---

## 🧪 **Testing Strategy**

### Unit Tests

| Test | Coverage |
|------|----------|
| `ReportingViewSet.initial()` | Tenant context resolution |
| `ReportingViewSet.parse_period()` | Period parsing |
| `FinanceDataAccess.get_collection()` | MongoDB access |
| `TransactionDataAccess.get_orders()` | PostgreSQL access |
| `PeriodParser.parse()` | Period validation |

### Integration Tests

| Test | Coverage |
|------|----------|
| `AnalyticsViewSet.list()` | All fields, all periods |
| `FinancialsViewSet.list()` | Flat list format, period support |
| `ITCGSTViewSet.list()` | Tax calculation, status tracking |
| `RevenueViewSet.list()` | 21-key response |
| `ExpenditureViewSet.list()` | 21-key response |
| `CafeViewSet.dashboard_revenue()` | New endpoint |

### Performance Tests

| Test | Metric |
|------|--------|
| `shared/analytics` | < 200ms response time |
| `accounts/financials` | < 500ms response time (1000 transactions) |
| `accounts/itc-gst` | < 300ms response time |
| Cache hit ratio | > 80% |
| Query count | < 5 queries per endpoint |

---

## 🚀 **Implementation Plan**

### Phase 0: Foundation (2 days)

**Tasks:**
1. ✅ Create `domains/reporting/base.py` — `ReportingViewSet` mixin
2. ✅ Create `backend/periods.py` — `PeriodParser` utility
3. ✅ Create `backend/response_utils.py` — `reporting_response()`
4. ✅ Add `CorrelationIdMiddleware` to `backend/middleware.py`
5. ✅ Configure `structlog` in `settings.py`
6. ✅ Add database indexes (PostgreSQL + MongoDB)

**Deliverables:**
- `ReportingViewSet` mixin
- `PeriodParser` utility
- `reporting_response()` function
- Structured logging configured
- Database indexes created

---

### Phase 1: Fix Critical Bugs (1 day)

**Tasks:**
1. ✅ Fix `FinancialsViewSet` — Return flat transaction list
2. ✅ Fix export paths — Add alias routes
3. ✅ Verify `sales_func` collection — Confirm correct name
4. ✅ Remove `sys.stderr.write` debug logs
5. ✅ Fix hardcoded `days_to_pay` in analytics

**Deliverables:**
- `FinancialsViewSet` returns correct format
- Export paths work (no 404s)
- `sales_func` queries correct collection
- No debug logs in production

---

### Phase 2: Migrate Endpoints (3 days)

**Tasks:**
1. ✅ Migrate `analytics()` → `SharedViewSet.analytics()`
2. ✅ Migrate `financials()` → `FinancialsViewSet.list()`
3. ✅ Migrate `itc_gst()` → `ITCGSTViewSet.list()`
4. ✅ Migrate `sales()` → `RevenueViewSet.list()`
5. ✅ Migrate `purchases()` → `ExpenditureViewSet.list()`
6. ✅ Implement `CafeViewSet.dashboard_revenue()`

**Deliverables:**
- All endpoints use `ReportingViewSet`
- Consistent response format
- Structured logging enabled
- Correlation IDs working

---

### Phase 3: Performance Optimization (1 day)

**Tasks:**
1. ✅ Add Redis caching for reporting endpoints
2. ✅ Optimize aggregation pipelines (21 queries → 1)
3. ✅ Add pagination for large datasets
4. ✅ Implement cache warming on startup

**Deliverables:**
- Redis caching enabled
- Query count reduced by 80%
- Pagination working
- Cache hit ratio > 80%

---

### Phase 4: Missing Reports (2 days)

**Tasks:**
1. ✅ Implement P&L endpoint — `accounts/profit-loss`
2. ✅ Implement Balance Sheet endpoint — `accounts/balance-sheet`
3. ✅ Implement Inventory Valuation endpoint — `products/inventory/valuation`
4. ✅ Implement Customer Analytics endpoint — `accounts/customer-analytics`

**Deliverables:**
- 4 new reporting endpoints
- Frontend integration (if required)
- Documentation updated

---

### Phase 5: Cleanup & Deployment (1 day)

**Tasks:**
1. ✅ Decommission legacy FBVs (`teams/financial.py`, `teams/analytics.py`)
2. ✅ Update API documentation
3. ✅ Run full test suite
4. ✅ Performance benchmarking
5. ✅ Deploy to production

**Deliverables:**
- Legacy code removed
- Documentation updated
- All tests passing
- Production deployment

---

## 📈 **Success Metrics**

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Audit Issues Resolved** | 14/14 | Issue tracker |
| **Frontend Contract Match** | 100% | Manual verification |
| **Response Time (analytics)** | < 200ms | Load testing |
| **Response Time (financials)** | < 500ms | Load testing |
| **Query Count** | < 5 per endpoint | Query logging |
| **Cache Hit Ratio** | > 80% | Redis monitoring |
| **Test Coverage** | > 90% | Coverage report |
| **Production Incidents** | 0 | Incident tracking |

---

## 📚 **Related Documentation**

- [Unified Migration Guide](/home/chief/llm-wiki/Kung_OS/unified_migration_guide.md)
- [Analytics & Reporting Audit](/home/chief/llm-wiki/AnalyticsReporting_Audit.md)
- [AnalyticsViewSet Refactor Handoff](/home/chief/llm-wiki/Kung_OS/handoffs/analytics_viewset_refactor_2026-07-02.md)
- [Analytics Refactor Coverage Review](/home/chief/llm-wiki/Kung_OS/reviews/analytics_refactor_coverage_2026-07-02.md)

---

## 🎯 **Decision Matrix**

| Decision | Option A | Option B | Recommendation |
|----------|----------|----------|----------------|
| **Financials format** | Fix backend to match frontend | Fix frontend to match backend | ✅ **Fix backend** — frontend contract is cleaner |
| **Export paths** | Add alias routes (no hyphen) | Fix frontend to use hyphens | ✅ **Add alias routes** — less frontend risk |
| **sales_func doc_type** | Keep `outward_debit_note` | Switch to `outward_invoice` | ✅ **Verify with DB admin first** |
| **Base layer approach** | Greenfield reporting subsystem | Thin mixin on existing primitives | ✅ **Thin mixin** — KungOS v2 already has primitives |
| **Missing reports** | Build all 8 missing reports | Build top 3 (P&L, balance sheet, inventory) | ✅ **Top 3 first** — MVP approach |
| **Caching** | Redis for all reporting | No cache, optimize queries | ✅ **Redis** — reporting is read-heavy |
| **Error handling** | Keep `sys.stderr.write` + silent except | Structured logging + correlation IDs | ✅ **Structured logging** — observable, debuggable |
| **Tenant scoping** | Per-endpoint `resolve_access()` | Centralized `TenantScopeBuilder` | ✅ **Centralized** — single source of truth |
| **Period parsing** | Duplicated across endpoints | Centralized `PeriodParser` | ✅ **Centralized** — consistent date handling |
| **Feature flags** | Hardcoded | `TenantConfig`-driven per BG/brand | ✅ **TenantConfig** — flexible per-tenant behavior |

---

## ✅ **Acceptance Criteria**

- [ ] All 14 audit issues resolved
- [ ] 100% frontend contract match
- [ ] `ReportingViewSet` mixin working
- [ ] `PeriodParser` utility working
- [ ] Structured logging enabled
- [ ] Correlation IDs working
- [ ] Database indexes created
- [ ] Redis caching enabled
- [ ] Pagination working for large datasets
- [ ] All tests passing (>90% coverage)
- [ ] Performance benchmarks met
- [ ] Legacy FBVs decommissioned
- [ ] Documentation updated
- [ ] Production deployment successful

---

**Specification Date:** 2026-07-02  
**Status:** Draft — Ready for Review  
**Next Step:** Architecture review with team  
**Estimated Timeline:** 10 days (5 phases)  
**Estimated Effort:** 40-50 hours
