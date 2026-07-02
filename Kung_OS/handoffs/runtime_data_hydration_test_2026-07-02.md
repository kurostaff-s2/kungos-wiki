# Runtime Data Hydration Test Handoff

**Date:** 2026-07-02  
**Status:** 📋 **READY FOR EXECUTION**  
**Effort:** 2-3 hours  

---

## 🎯 **Objective**

Verify all migrated API endpoints return **real data** from PostgreSQL/MongoDB by running both servers and testing against live database.

---

## 📊 **Data Summary**

| Database | Collection/Table | Type | Volume |
|----------|-----------------|------|--------|
| **MongoDB** | `financial_documents` | Unified Finance | 13,014 docs |
| **PostgreSQL** | `orders_core` | Unified Orders | 13,603 records |
| **PostgreSQL** | `inv_purchase_orders` | Purchase Orders | 7,148 records |
| **PostgreSQL** | `users_customuser` | Users | 3,532 records |
| **PostgreSQL** | `inv_vendors` | Vendors | 424 records |
| **PostgreSQL** | `users_employee` | Employees | 68 records |
| **PostgreSQL** | `tenant_business_groups` | Business Groups | 2 |
| **PostgreSQL** | `tenant_divisions` | Divisions | 4 |
| **PostgreSQL** | `tenant_branches` | Branches | 4 |
| **PostgreSQL** | `users_user_tenant_context` | User-Tenant Mapping | 3,531 |

**Total Data Points:** ~41,320 records across both databases

---

## 🖥️ **Server Setup**

### Backend Server (KungOS-dj)

```bash
cd /home/chief/Coding-Projects/KungOS-dj
# Check if running
ps aux | grep uvicorn | grep -v grep
# If not running:
nohup uvicorn app:app --host 0.0.0.0 --port 7000 > /tmp/backend.log 2>&1 &
# Verify
curl -s http://localhost:7000/api/v1/shared/home | head -5
```

**Status:** ✅ Already running on port 7000

---

### Frontend Server (KungOS-FE-Team)

```bash
cd /home/chief/Coding-Projects/KungOS-FE-Team
# Check if running
ps aux | grep vite | grep -v grep
# If not running:
nohup npm run dev > /tmp/frontend.log 2>&1 &
# Verify
curl -s http://localhost:3001 | head -10
```

**Status:** ✅ Already running on port 3001

---

## 🧪 **Testing Procedure**

### Step 1: Authenticate

**Option A: Use existing JWT token**
```bash
# Get token from browser DevTools → Application → Cookies
# Or from backend logs after login
TOKEN="your_jwt_token_here"
```

**Option B: Create test user via Django shell**
```bash
cd /home/chief/Coding-Projects/KungOS-dj
python3 manage.py shell
```
```python
from users.models import CustomUser
user = CustomUser.objects.create_user(username='runtime_test', password='test123', is_staff=True, is_superuser=True)
print(f"User created: {user.username}")
# Login via frontend and copy JWT token
```

---

### Step 2: Test Each Endpoint

**Use curl with authentication:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:7000/api/v1/shared/analytics?period=monthly | python3 -m json.tool
```

**Or use browser DevTools:**
1. Open http://localhost:3001
2. Login with test user
3. Open DevTools → Network tab
4. Navigate to each page
5. Check response data

---

## 📊 **Database Data Volumes**

### MongoDB (KungOS_Mongo_One)

| Collection | Type | Volume |
|------------|------|--------|
| `financial_documents` | Unified Finance | **13,014 documents** |
| └─ `inward_invoice` | Income | 4,750 |
| └─ `payment_voucher` | Expense | 3,715 |
| └─ `inward_payment` | Revenue | 3,188 |
| └─ `outward_invoice` | Sales | 1,192 |
| └─ `inward_credit_note` | Credit | 109 |
| └─ `outward_credit_note` | Credit | 44 |
| └─ `inward_debit_note` | Debit | 3 |
| └─ `outward_debit_note` | Debit | 13 |
| `products` | Catalog | Active products |
| `custom_catalog` | Catalog | Custom items |

**Key Fields:** `_id`, `source_db`, `source_collection`, `doc_type`, `bg_code`, `div_code`, `branch_code`, `migrated_at`, `invoice_no`, `invoice_date`, `totalprice`, `vendor`, `pay_status`

---

### PostgreSQL (KungOS_PG_One)

| Table | Domain | Volume |
|-------|--------|--------|
| `orders_core` | Unified Orders | **13,603 records** |
| └─ `in_store` | In-Store | 12,174 |
| └─ `eshop` | E-Shop | 1,200 |
| └─ `tp` | Third-Party | 229 |
| `users_employee` | Employees | 68 |
| `inv_vendors` | Vendors | 424 |
| `inv_purchase_orders` | Purchase Orders | 7,148 |
| `users_customuser` | Users | 3,532 |
| `eshop_detail` | E-Shop Detail | 0 (placeholder) |
| `caf_platform_sessions` | Cafe | 0 (placeholder) |
| `kungos_tenant_profile` | Tenants | 0 (placeholder) |

**Key Fields (orders_core):** `id`, `order_type`, `order_status`, `customer_name`, `total_amount`, `created_date`, `updated_date`, `delete_flag`, `active`

---

### Tenant Data (PostgreSQL)

| Table | Type | Volume |
|-------|------|--------|
| `tenant_business_groups` | Business Groups | **2** |
| └─ `KURO0001` | Kuro Cadence | Active |
| └─ `DUNE0003` | Dune Labs | Active |
| `tenant_divisions` | Divisions | **4** |
| └─ `KURO0001_001` | Kuro Gaming | Active |
| └─ `KURO0001_002` | Rebellion | Active |
| └─ `KURO0001_003` | RenderEdge | Active |
| └─ `DUNE0003_001` | Rebellion (Dune) | Active |
| `tenant_branches` | Branches | **4** |
| └─ `KURO0001_001_001` | KG Madhapur | Active |
| └─ `KURO0001_002_001` | RB Madhapur | Active |
| └─ `KURO0001_002_002` | RB LB Nagar | Active |
| └─ `KURO0001_003_001` | RE Madhapur | Active |
| `users_user_tenant_context` | User-Tenant Mapping | **3,531** |
| `kungos_tenant_profile` | Tenant Profile | 0 (placeholder) |

**Key Fields (tenant_business_groups):** `bg_code`, `bg_label`, `legal_name`, `registered_address`, `is_active`, `created_at`

**Key Fields (tenant_divisions):** `div_code`, `div_label`, `brand_name`, `bg_code`, `is_active`, `created_at`

**Key Fields (tenant_branches):** `branch_code`, `branch_label`, `branch_name`, `div_code`, `is_active`, `created_at`

**Key Fields (users_user_tenant_context):** `userid`, `bg_code`, `div_codes`, `branch_codes`, `scope`, `created_at`

**Sample Data:**
```sql
-- Business Groups
SELECT bg_code, bg_label, legal_name, is_active FROM tenant_business_groups;
-- Result: KURO0001 (Kuro Cadence), DUNE0003 (Dune Labs)

-- Divisions
SELECT div_code, div_label, bg_code, is_active FROM tenant_divisions;
-- Result: KURO0001_001 (Kuro Gaming), KURO0001_002 (Rebellion), etc.

-- Branches
SELECT branch_code, branch_label, div_code, is_active FROM tenant_branches;
-- Result: KURO0001_001_001 (KG Madhapur), KURO0001_002_001 (RB Madhapur), etc.

-- User-Tenant Context (sample)
SELECT userid, bg_code, div_codes, branch_codes FROM users_user_tenant_context LIMIT 3;
-- Result: userid=4927093804, bg_code=KURO0001, div_codes=[], branch_codes=[]
```

---

## 📋 **Endpoint Test Checklist**

### 1. Orders Domain (PostgreSQL)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| Estimates | `/api/v1/orders/estimates` | List of estimates from `orders_core` |
| TP Orders | `/api/v1/orders/tp-orders` | List of TP orders from `orders_core` |
| In-Store Orders | `/api/v1/orders/instore` | List of in-store orders from `orders_core` |
| Service Requests | `/api/v1/orders/service-requests` | List of service requests |

**Verification:**
- ✅ Returns JSON array
- ✅ Each item has required fields (id, status, amount, etc.)
- ✅ Data matches PostgreSQL `orders_core` table

---

### 2. Teams Domain (PostgreSQL)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| Employees | `/api/v1/teams/employees` | List of active employees from `users_employeeprofile` |
| Users | `/api/v1/teams/users` | List of users from `users_customuser` |

**Verification:**
- ✅ Returns JSON array
- ✅ EmployeeProfile items have `active=True` (soft delete)
- ✅ Data matches PostgreSQL tables

---

### 3. Vendors Domain (PostgreSQL)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| Vendors | `/api/v1/vendors/` | List of vendors from `inv_vendors` |

**Verification:**
- ✅ Returns JSON array
- ✅ Each vendor has code, name, PAN
- ✅ Data matches PostgreSQL `inv_vendors` table

---

### 4. Analytics (Hybrid: MongoDB + PostgreSQL)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| Analytics Dashboard | `/api/v1/shared/analytics?period=monthly` | Aggregated metrics |

**Expected Response Fields:**
```javascript
{
  totalRevenue: 1500000,      // From financial_documents (inward_payment)
  totalExpenses: 800000,      // From financial_documents (payment_voucher)
  profitMargin: 46.7,         // Calculated
  chartData: [...],           // Monthly breakdown
  paymentTrend: [...],        // Paid vs pending
  vendors: [...],             // Top 5 vendors
  totalOrders: 500,           // From financial_documents
  totalEstimates: 50,         // From orders_core (PostgreSQL)
  totalTPOrders: 30,          // From orders_core (PostgreSQL)
}
```

**Tenant Filtering Test:**
```bash
# With division
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7000/api/v1/shared/analytics?period=monthly&div_code=KURO0001_001"

# With branch
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7000/api/v1/shared/analytics?period=monthly&branch_code=BR001"

# With both
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7000/api/v1/shared/analytics?period=monthly&div_code=KURO0001_001&branch_code=BR001"
```

**Verification:**
- ✅ Returns all expected fields
- ✅ `div_code` and `branch_code` filter data correctly
- ✅ `totalRevenue` > 0 (has real data)
- ✅ `chartData` has monthly entries

---

### 5. Financials (MongoDB: financial_documents)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| Financial Transactions | `/api/v1/accounts/financials?period=monthly` | Flat transaction list |

**Expected Response:**
```javascript
[
  {
    date: "2026-07",
    description: "Invoice #INV-001",
    category: "Sales",
    type: "income",
    amount: 50000,
    reference: "INV-001"
  },
  // ... more transactions
]
```

**Tenant Filtering Test:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7000/api/v1/accounts/financials?period=monthly&div_code=KURO0001_001"
```

**Verification:**
- ✅ Returns array (not dict)
- ✅ Each item has `date`, `description`, `amount`
- ✅ Mix of income and expense transactions
- ✅ Data matches `financial_documents` collection

---

### 6. Profit & Loss (MongoDB: financial_documents)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| P&L Statement | `/api/v1/accounts/profit-loss?period=curr_fy` | P&L report |

**Expected Response:**
```javascript
{
  period: "FY 2026-2027",
  revenue: {
    sales: 1500000,
    credits: 50000,
    total: 1450000
  },
  cogs: 800000,
  gross_profit: {
    amount: 650000,
    margin: 44.8
  },
  expenses: {
    total: 400000
  },
  operating_profit: 250000,
  net_profit: 250000,
  net_margin: 17.2
}
```

**Verification:**
- ✅ Returns all required fields
- ✅ `net_profit` is calculated correctly
- ✅ `gross_margin` and `net_margin` are percentages

---

### 7. Balance Sheet (MongoDB: financial_documents)

| Endpoint | URL | Expected Data |
|----------|-----|---------------|
| Balance Sheet | `/api/v1/accounts/balance-sheet?period=curr_fy` | BS report |

**Expected Response:**
```javascript
{
  as_of: "2026-07-02T00:00:00+05:30",
  assets: {
    current: {
      cash: 500000,
      accounts_receivable: 200000,
      inventory: 0,  // Placeholder
      total: 700000
    },
    fixed: {
      equipment: 300000,
      accumulated_depreciation: -50000,
      net: 250000
    },
    total_assets: 950000
  },
  liabilities: {
    current: {
      accounts_payable: 150000,
      total: 150000
    },
    long_term: {
      loans: 100000,
      total: 100000
    },
    total_liabilities: 250000
  },
  equity: {
    capital: 500000,
    retained_earnings: 200000,
    total: 700000
  },
  balance_check: true
}
```

**Verification:**
- ✅ Returns all required fields
- ✅ `balance_check` is `true` (Assets = Liabilities + Equity)
- ✅ Note: `inventory` is 0 (placeholder — needs PostgreSQL integration)

---

### 8. Accounts CRUD (MongoDB: financial_documents)

| Endpoint | URL | Method | Expected |
|----------|-----|--------|----------|
| Inward Invoices | `/api/v1/accounts/inward-invoices` | GET | List of invoices |
| Outward Invoices | `/api/v1/accounts/outward-invoices` | GET | List of invoices |
| Inward Payments | `/api/v1/accounts/inward-payments` | GET | List of payments |
| Payment Vouchers | `/api/v1/accounts/payment-vouchers` | GET | List of vouchers |
| Credit Notes | `/api/v1/accounts/credit-notes` | GET | List of notes |
| Debit Notes | `/api/v1/accounts/debit-notes` | GET | List of notes |

**DOC_TYPE Mapping:**
| ViewSet | DOC_TYPE |
|---------|----------|
| InwardInvoiceViewSet | `inward_invoice` |
| OutwardInvoiceViewSet | `outward_invoice` |
| InwardPaymentViewSet | `inward_payment` |
| OutwardPaymentViewSet | `payment_voucher` |
| PaymentVoucherViewSet | `payment_voucher` |
| OutwardCreditNoteViewSet | `outward_credit_note` |
| OutwardDebitNoteViewSet | `outward_debit_note` |
| InwardCreditNoteViewSet | `inward_credit_note` |
| InwardDebitNoteViewSet | `inward_debit_note` |

**Verification:**
- ✅ Each endpoint returns data filtered by correct `doc_type`
- ✅ Data matches `financial_documents` collection

---

## 🔍 **Data Verification Queries**

### MongoDB (financial_documents)

```javascript
// Count by doc_type
db.financial_documents.aggregate([
  {$group: {_id: "$doc_type", count: {$sum: 1}}},
  {$sort: {count: -1}}
])

// Sample inward_invoice
db.financial_documents.findOne({doc_type: "inward_invoice"})

// Filter by tenant
db.financial_documents.find({bg_code: "KURO0001", doc_type: "inward_invoice"}).count()

// Filter by tenant + division
db.financial_documents.find({bg_code: "KURO0001", div_code: "KURO0001_001", doc_type: "inward_invoice"}).count()
```

### PostgreSQL (orders_core)

```sql
SELECT order_type, COUNT(*) FROM orders_core GROUP BY order_type;
SELECT order_type, COUNT(*) FROM orders_core WHERE active = true AND delete_flag = false GROUP BY order_type;
```

### PostgreSQL (users_employeeprofile)

```sql
SELECT COUNT(*) FROM users_employeeprofile WHERE active = true;
SELECT * FROM users_employeeprofile LIMIT 1;
```

### PostgreSQL (inv_vendors)

```sql
SELECT COUNT(*) FROM inv_vendors;
SELECT * FROM inv_vendors LIMIT 1;
```

### PostgreSQL (Tenant Data)

```sql
-- Business Groups
SELECT COUNT(*) FROM tenant_business_groups;
SELECT bg_code, bg_label, legal_name, is_active FROM tenant_business_groups;

-- Divisions
SELECT COUNT(*) FROM tenant_divisions;
SELECT div_code, div_label, bg_code, is_active FROM tenant_divisions;

-- Branches
SELECT COUNT(*) FROM tenant_branches;
SELECT branch_code, branch_label, div_code, is_active FROM tenant_branches;

-- User-Tenant Context
SELECT COUNT(*) FROM users_user_tenant_context;
SELECT userid, bg_code, div_codes, branch_codes FROM users_user_tenant_context LIMIT 5;
```

---

## ⚠️ **Known Issues & Workarounds**

### 1. Django Test Client 400 Error

**Issue:** `DisallowedHost` error when using Django test client

**Workaround:** Test against running server with valid JWT

**Fix:** Add to `backend/settings.py`:
```python
if env.bool('TESTING', default=False):
    ALLOWED_HOSTS = ['*']
```

---

### 2. Inventory Valuation Placeholder

**Issue:** Balance Sheet `inventory` field is 0 (placeholder)

**Status:** ⚠️ Known — needs PostgreSQL `inventory_inventorystock` integration

**Impact:** Balance Sheet won't balance if inventory > 0

**Fix:** Implement inventory valuation from PostgreSQL (Phase 7+)

---

### 3. AccountsViewSet Legacy

**Issue:** `AccountsViewSet` still uses `accounts` MongoDB collection

**Status:** ⚠️ Known — needs PostgreSQL migration

**Impact:** Sundry creditors/debtors, banks, partners, loans not in unified collection

**Fix:** Migrate to PostgreSQL (Phase 7+)

---

### 4. PurchaseOrderViewSet Legacy

**Issue:** `PurchaseOrderViewSet` still uses `purchaseorders` MongoDB collection

**Status:** ⚠️ Known — purchase orders in PostgreSQL (inventory domain)

**Impact:** Accounts domain purchase orders not in unified collection

**Fix:** Remove from accounts domain or redirect to inventory domain

---

## 📝 **Test Report Template**

```markdown
## Endpoint Test Results

**Date:** 2026-07-02  
**Tester:** [Name]  
**Environment:** [Local/Production]

### Summary
- ✅ Passed: X/Y
- ❌ Failed: X/Y
- ⚠️  Known Issues: X

### Detailed Results

| # | Endpoint | Status | Response Time | Notes |
|---|----------|--------|---------------|-------|
| 1 | /shared/analytics | ✅/❌ | Xms | |
| 2 | /accounts/financials | ✅/❌ | Xms | |
| 3 | /accounts/profit-loss | ✅/❌ | Xms | |
| 4 | /accounts/balance-sheet | ✅/❌ | Xms | |
| ... | ... | ... | ... | ... |

### Issues Found
1. [Issue description]
2. [Issue description]

### Recommendations
1. [Recommendation]
```

---

## ✅ **Success Criteria**

- [ ] All 8 endpoint groups return data (not errors)
- [ ] Analytics endpoint returns `totalRevenue > 0`
- [ ] Financials endpoint returns transaction list
- [ ] P&L endpoint returns all required fields
- [ ] Balance Sheet endpoint returns `balance_check: true`
- [ ] Tenant filtering works (div_code, branch_code)
- [ ] Accounts CRUD endpoints filter by DOC_TYPE
- [ ] Response times < 2 seconds for all endpoints

---

## 📚 **Related Documentation**

- [Unified Migration Guide](/home/chief/llm-wiki/Kung_OS/unified_migration_guide.md)
- [Analytics & Reporting Spec](/home/chief/llm-wiki/Kung_OS/specs/analytics_reporting_spec_2026-07-02.md)
- [Phase 0-3 Status](/home/chief/llm-wiki/Kung_OS/status/phase0_foundation_2026-07-02.md)
- [Phase 6 Integration Tests](/home/chief/llm-wiki/Kung_OS/status/phase6_integration_testing_2026-07-02.md)

---

## 🎯 **Next Steps**

1. **Run servers** (already running)
2. **Authenticate** (create test user or use existing JWT)
3. **Test each endpoint** (use checklist above)
4. **Verify data hydration** (check MongoDB/PostgreSQL directly)
5. **Document issues** (use test report template)
6. **Fix critical issues** (prioritize by impact)

---

**Handoff Ready:** ✅ All servers running, all code committed, all tests pass.

**Estimated Time:** 2-3 hours for complete validation
