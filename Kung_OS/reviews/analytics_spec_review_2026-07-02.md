# Analytics Spec Review — Gap Analysis

**Date:** 2026-07-02  
**Review Type:** Spec vs Reality  
**Scope:** Spec vs Audit, Schema, Frontend, Live Code  

---

## 🔴 **CRITICAL GAPS IDENTIFIED**

### Gap 1: `inwardpayments` Schema Mismatch

**Spec Claim:**
> `totalRevenue` from `inwardpayments` → uses `totalprice` field

**Reality (Live Schema):**
```javascript
{
  _id: ObjectId('6a02dda695d2f755ff65d0fc'),
  orderid: 'KG23000431',
  payments: [...],
  amount_paid: 2600,           // ← ACTUAL FIELD
  created_by: 'KCTM032',
  active: true,
  delete_flag: false,
  created_date: '02-01-2025, 09:45:53',
  status: 'Paid',
  branch: 'Madhapur'
  // NO totalprice field!
  // NO div_code field!
  // NO bg_code field!
}
```

**Impact:** 
- Current analytics code references `p.get('totalprice')` which **returns undefined**
- All revenue calculations return **0**
- **Spec must be updated** to use `amount_paid` instead of `totalprice`

**Fix Required:**
```python
# Before (broken)
total_revenue = round(sum(
    (p.get('totalprice') or 0) for p in all_payments
), 2)

# After (correct)
total_revenue = round(sum(
    (p.get('amount_paid') or 0) for p in all_payments
), 2)
```

---

### Gap 2: `inwardpayments` Missing Tenant Fields

**Spec Claim:**
> Use `bg_code`, `div_code`, `branch_code` for tenant scoping

**Reality (Live Schema):**
```javascript
{
  // NO bg_code field
  // NO div_code field
  // branch: 'Madhapur'  // ← Single field, not branch_code
  // entity: 'kurogaming'  // ← Entity field, not bg_code
}
```

**Impact:**
- Tenant scoping via `bg_code`/`div_code` **won't work**
- Must use `entity` field for BG scoping
- Must use `branch` field for branch scoping (not `branch_code`)

**Fix Required:**
```python
# Before (broken)
payment_filter = {
    'bg_code': bg.bg_code,
    'div_code': division,
    'branch_code': branch,
}

# After (correct)
payment_filter = {
    'entity': bg.entity,  # or bg_code if available
    'branch': branch,  # not branch_code
}
```

---

### Gap 3: Financials Response Format

**Spec Claim:**
> Return flat transaction list: `[{date, description, type, amount, reference}]`

**Reality (Live Code):**
```python
# domains/accounts/financials/viewsets.py
final_output = []
for obj in result_list:
    formatted_date = f"{int(obj['year'])}-{months[int(obj['month']) - 1]}"
    if final_output.get(formatted_date):
        final_output[formatted_date].update({obj['type']: obj['total']})
    else:
        final_output[formatted_date] = {obj['type']: obj['total']}

# Returns:
[
  {"2024-Jan": {"Invoice": 50000, "Credit": 10000, "Debit": 5000, "total": 55000}},
  {"2024-Feb": {"Invoice": 60000, "Credit": 12000, "Debit": 6000, "total": 66000}},
  {"CurrentFin-year": {...}},
  {"LastFin-year": {...}}
]
```

**Frontend Expectation (from audit):**
```javascript
[
  {
    date: "2024-01-15",
    description: "Invoice #INV-001",
    category: "Sales",
    type: "income",  // "income" | "expense"
    amount: 50000,
    reference: "INV-001"
  }
]
```

**Impact:**
- Frontend `useMemo` produces **all zeros** (no `type === 'income'` or `type === 'expense'`)
- **Spec must be updated** — either fix backend or fix frontend

**Recommendation:**
- ✅ **Fix backend** to return flat transaction list
- ✅ **Add `type` field**: `"income"` for invoices, `"expense"` for payment vouchers

---

### Gap 4: `paymentvouchers` Collection Empty

**Spec Claim:**
> Use `paymentvouchers` for expense data

**Reality:**
```javascript
> db.paymentvouchers.countDocuments()
0
```

**Impact:**
- Expense calculations will return **0**
- Must use `inwardInvoices` with `pay_status` filter instead

**Fix Required:**
```python
# Before (broken - empty collection)
pv_col, pv_tf = self.get_collection('paymentvouchers')
all_expenses = decode_result(pv_col.find(pv_filter, {...}))

# After (correct - use inwardInvoices)
inv_col, inv_tf = self.get_collection('inwardInvoices')
expense_filter = {
    **inv_tf,
    'pay_status': {'$in': ['Paid', 'Pending']},
}
all_expenses = decode_result(inv_col.find(expense_filter, {...}))
```

---

### Gap 5: `inwardInvoices` Schema Differences

**Spec Claim:**
> Use `inwardinvoices` for financial data

**Reality (Live Schema):**
```javascript
{
  _id: ObjectId('682316801532dd9d6765d1d1'),
  invoiceid: 'SHWE20001J',
  vendor: 'SHWE360001',
  gstin: '36AAUFS5784P1ZV',
  invoice_no: '026762',
  invoice_date: '2020-09-16T00:00:00.000000+0530',
  fin_year: 'FY20-21',
  cgst: 3943.22,
  sgst: 3943.22,
  igst: 0,
  pay_status: 'Paid',
  settled: 'Yes',
  itc_received: 'Yes',
  delete_flag: false,
  active: true,
  totalprice: 51700,           // ← Has totalprice
  desc: '',
  tags: [],
  entity: 'kurogaming'         // ← Has entity field
}
```

**Impact:**
- Collection name is `inwardInvoices` (camelCase), not `inwardinvoices`
- Has `totalprice` field (unlike `inwardpayments`)
- Has `entity` field for tenant scoping
- Has `pay_status` field for payment tracking

**Fix Required:**
```python
# Before (wrong collection name)
collection, tf = get_collection('inwardinvoices', ...)

# After (correct collection name)
collection, tf = get_collection('inwardInvoices', ...)
```

---

### Gap 6: `purchaseorders` Schema for Vendor Data

**Spec Claim:**
> Use `InventoryPurchaseOrder` model for vendor data

**Reality (MongoDB Schema):**
```javascript
{
  _id: ObjectId('668a5814d499d93213d19813'),
  po_no: 'KUROACRO23002Q',
  vendor: 'ACRO33000D',        // ← Direct vendor field
  total_amount: 26577,
  created_by: 'KCAD002',
  created_date: '10-06-2022, 11:21:32',
  delete_flag: false,
  active: true,
  entity: 'kurogaming'
}
```

**Reality (PostgreSQL Schema):**
```sql
CREATE TABLE inv_purchase_orders (
    po_no VARCHAR(100) PRIMARY KEY,
    vendor_code VARCHAR(50),     -- FK to inv_vendors
    total_amount NUMERIC(12,2),
    branch_code VARCHAR(50),
    bg_code VARCHAR(50),
    div_code VARCHAR(50),
    created_by VARCHAR(50),
    created_date VARCHAR(50),
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Impact:**
- MongoDB has direct `vendor` field
- PostgreSQL has `vendor_code` (FK to `inv_vendors`)
- Need to JOIN with `inv_vendors` to get vendor name

**Fix Required:**
```python
# PostgreSQL query with JOIN
from django.db.models import F

po_qs = InventoryPurchaseOrder.objects.filter(
    bg_code=bg_code,
    delete_flag=False,
    active=True
).select_related('vendor_code')  # JOIN with inv_vendors

vendor_totals = {}
for po in po_qs:
    vendor_name = po.vendor_code.name if po.vendor_code else 'Unknown'
    vendor_totals[vendor_name] = vendor_totals.get(vendor_name, 0) + float(po.total_amount or 0)
```

---

## 🟡 **HIGH PRIORITY GAPS**

### Gap 7: Date Format Inconsistency

**Issue:**
- `inwardpayments.created_date`: `'02-01-2025, 09:45:53'` (DD-MM-YYYY)
- `inwardInvoices.invoice_date`: `'2020-09-16T00:00:00.000000+0530'` (ISO 8601)
- `purchaseorders.created_date`: `'10-06-2022, 11:21:32'` (DD-MM-YYYY)

**Impact:**
- Date parsing must handle multiple formats
- `_parse_date()` helper must be robust

**Fix Required:**
```python
def parse_date(date_str):
    """Parse multiple date formats."""
    if not date_str:
        return None
    try:
        # ISO format
        return datetime.fromisoformat(str(date_str).replace('+0530', '+05:30'))
    except ValueError:
        pass
    try:
        # DD-MM-YYYY, HH:MM:SS format
        return datetime.strptime(str(date_str).split(',')[0], '%d-%m-%Y, %H:%M:%S')
    except ValueError:
        pass
    return None
```

---

### Gap 8: Missing `outwardInvoices` Data

**Spec Claim:**
> Use `outwardInvoices` for revenue data

**Reality:**
```javascript
> db.outwardInvoices.countDocuments()
1192
```

**Impact:**
- Collection exists and has data
- Must verify `sales_func` uses correct collection

---

### Gap 9: `estimates` and `tporders` Migration Status

**Spec Claim:**
> Migrate `estimates` and `tporders` to PostgreSQL `orders_core`

**Reality:**
```javascript
> db.estimates.countDocuments()
5056
> db.tporders.countDocuments()
229
```

**Impact:**
- MongoDB still has data (not yet migrated to PostgreSQL)
- Must verify PostgreSQL `orders_core` has corresponding records

**Verification Required:**
```sql
SELECT order_type, COUNT(*) 
FROM orders_core 
WHERE order_type IN ('estimate', 'tp')
GROUP BY order_type;
```

---

## 🟢 **LOW PRIORITY GAPS**

### Gap 10: Analytics ViewSet Line Numbers

**Spec Claim:**
> `AnalyticsViewSet` at lines 285-560

**Reality:**
```bash
$ wc -l domains/shared/viewsets.py
600 lines
$ grep -n "class AnalyticsViewSet" domains/shared/viewsets.py
285:class AnalyticsViewSet(...)
```

**Impact:** Minimal — line numbers are approximate

---

### Gap 11: `accounts/analytics` Duplication

**Audit Issue:**
> `accounts/analytics` duplicates `shared/analytics`

**Reality:**
```bash
$ grep -rn "accounts/analytics\|shared/analytics" domains/ --include="*.py"
domains/accounts/urls.py: path('analytics', AnalyticsViewSet.as_view(...)),
domains/shared/urls.py: path('analytics', AnalyticsViewSet.as_view(...)),
```

**Impact:**
- Two endpoints for same data
- Must decide which to keep (recommend `shared/analytics`)

---

## 📊 **SPEC UPDATES REQUIRED**

### Update 1: `inwardpayments` Field Mapping

**Before (Spec):**
```
| `inwardpayments` | `totalprice` | Revenue |
```

**After (Spec):**
```
| `inwardpayments` | `amount_paid` | Revenue |
```

---

### Update 2: Tenant Scoping Fields

**Before (Spec):**
```
payment_filter = {
    'bg_code': bg.bg_code,
    'div_code': division,
    'branch_code': branch,
}
```

**After (Spec):**
```
payment_filter = {
    'entity': bg.entity,
    'branch': branch,  # not branch_code
}
```

---

### Update 3: Financials Response Format

**Before (Spec):**
```javascript
// Returns monthly dict
[
  {"2024-Jan": {"Invoice": 50000, "total": 55000}},
  {"2024-Feb": {"Invoice": 60000, "total": 66000}}
]
```

**After (Spec):**
```javascript
// Return flat transaction list
[
  {
    date: "2024-01-15",
    description: "Invoice #INV-001",
    category: "Sales",
    type: "income",
    amount: 50000,
    reference: "INV-001"
  }
]
```

---

### Update 4: Expense Data Source

**Before (Spec):**
```
| `paymentvouchers` | expenses | MongoDB |
```

**After (Spec):**
```
| `inwardInvoices` (pay_status filter) | expenses | MongoDB |
```

---

### Update 5: Collection Names

**Before (Spec):**
```
- `inwardinvoices`
- `outwardinvoices`
- `paymentvouchers`
```

**After (Spec):**
```
- `inwardInvoices` (camelCase)
- `outwardInvoices` (camelCase)
- `paymentVouchers` (camelCase)
```

---

## ✅ **SPEC RECOMMENDATIONS**

### Recommendation 1: Fix `inwardpayments` Revenue Calculation

**Action:** Update spec to use `amount_paid` field  
**Priority:** 🔴 Critical  
**Effort:** 1 hour  

### Recommendation 2: Fix Tenant Scoping

**Action:** Update spec to use `entity` and `branch` fields  
**Priority:** 🔴 Critical  
**Effort:** 1 hour  

### Recommendation 3: Fix Financials Response Format

**Action:** Implement flat transaction list format  
**Priority:** 🔴 Critical  
**Effort:** 4 hours  

### Recommendation 4: Fix Expense Data Source

**Action:** Use `inwardInvoices` with `pay_status` filter  
**Priority:** 🟡 High  
**Effort:** 2 hours  

### Recommendation 5: Fix Collection Names

**Action:** Update all collection name references to camelCase  
**Priority:** 🟡 High  
**Effort:** 1 hour  

### Recommendation 6: Verify Estimates/TP Migration

**Action:** Run SQL query to verify PostgreSQL has estimates/tp orders  
**Priority:** 🟡 High  
**Effort:** 30 minutes  

---

## 📝 **CONCLUSION**

### Critical Issues (Must Fix Before Implementation)
1. ✅ `inwardpayments` uses `amount_paid`, not `totalprice`
2. ✅ Tenant scoping uses `entity`/`branch`, not `bg_code`/`div_code`/`branch_code`
3. ✅ Financials must return flat transaction list (not monthly dict)
4. ✅ Expenses from `inwardInvoices`, not empty `paymentvouchers`
5. ✅ Collection names are camelCase (`inwardInvoices`, not `inwardinvoices`)

### High Priority Issues (Fix During Implementation)
6. ✅ Date format parsing (multiple formats)
7. ✅ Vendor data from `inv_purchase_orders` with JOIN
8. ✅ Verify estimates/tp migration to PostgreSQL

### Low Priority Issues (Document for Future)
9. ✅ Line number approximation
10. ✅ Endpoint duplication (`accounts/analytics` vs `shared/analytics`)

---

## 🎯 **NEXT STEPS**

1. **Update spec** with all gap fixes (2 hours)
2. **Verify PostgreSQL migration** for estimates/tp (30 minutes)
3. **Test `inwardpayments` schema** with actual queries (1 hour)
4. **Implement fixes** in Phase 1 (critical bugs)

---

**Review Date:** 2026-07-02  
**Status:** 🔴 **5 CRITICAL GAPS IDENTIFIED**  
**Action Required:** Update spec before implementation  
**Estimated Fix Time:** 8-10 hours
