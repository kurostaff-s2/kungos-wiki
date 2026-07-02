# AnalyticsViewSet Refactoring — Handoff Document

**Date:** 2026-07-02  
**Phase:** Phase 17 (Shared Viewsets Cleanup)  
**Priority:** Medium  
**Estimated Effort:** 4-6 hours  

---

## 📋 **Overview**

**File:** `domains/shared/viewsets.py`  
**Class:** `AnalyticsViewSet` (lines 285-560)  
**Endpoint:** `GET /shared/analytics`  

**Current State:** Uses MongoDB for estimates, tporders, purchaseorders  
**Target State:** Use PostgreSQL `OrderCore` model for estimates, tporders, purchaseorders  

---

## 🎯 **Objective**

Migrate `AnalyticsViewSet` to use PostgreSQL for order data while keeping MongoDB for finance data:

| Collection | Current | Target | Reason |
|------------|---------|--------|--------|
| `inwardpayments` | MongoDB | **MongoDB** | Finance data (keep) |
| `paymentvouchers` | MongoDB | **MongoDB** | Finance data (keep) |
| `estimates` | MongoDB | **PostgreSQL** | Migrated to `OrderCore` (order_type='estimate') |
| `tporders` | MongoDB | **PostgreSQL** | Migrated to `OrderCore` (order_type='tp') |
| `purchaseorders` | MongoDB | **PostgreSQL** | Migrated to `OrderCore` (order_type='purchase') |

---

## 📊 **Current Architecture**

```
AnalyticsViewSet.list()
    ↓
┌─────────────────────────────────────────────────┐
│ MongoDB Collections (Finance)                    │
│ - inwardpayments (revenue)                       │
│ - paymentvouchers (expenses)                     │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│ MongoDB Collections (Orders) ← MIGRATE TO PG    │
│ - estimates (count)                              │
│ - tporders (count)                               │
│ - purchaseorders (vendor spend)                  │
└─────────────────────────────────────────────────┘
```

---

## 🏗️ **Target Architecture**

```
AnalyticsViewSet.list()
    ↓
┌─────────────────────────────────────────────────┐
│ MongoDB Collections (Finance)                    │
│ - inwardpayments (revenue)                       │
│ - paymentvouchers (expenses)                     │
└─────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────┐
│ PostgreSQL OrderCore (Orders) ← NEW             │
│ - order_type='estimate' (count)                  │
│ - order_type='tp' (count)                        │
│ - order_type='purchase' (vendor spend)           │
└─────────────────────────────────────────────────┘
```

---

## 🔧 **Implementation Plan**

### Step 1: Update Imports (✅ DONE)
```python
from domains.orders.models import OrderCore
from django.db.models import Sum, Count
```

### Step 2: Replace Estimates Count (MongoDB → PostgreSQL)

**Before (MongoDB):**
```python
est_col, est_tf = self.get_collection('estimates')
est_filter = {**est_tf}
est_filter.update(build_division_filter())
est_filter.update(build_branch_filter())
estimates_count = est_col.count_documents(est_filter)
```

**After (PostgreSQL):**
```python
est_filter = {
    'bg_code': bg.bg_code,
    'order_type': 'estimate',
    'delete_flag': False,
    'active': True,
}
est_filter.update(build_division_filter())
if branch_param and branch_param != '__all__':
    est_filter['branch_code'] = branch_param
estimates_count = OrderCore.objects.filter(**est_filter).count()
```

### Step 3: Replace TP Orders Count (MongoDB → PostgreSQL)

**Before (MongoDB):**
```python
tp_col, tp_tf = self.get_collection('tporders')
tp_filter = {**tp_tf}
tp_filter.update(build_division_filter())
tp_filter.update(build_branch_filter())
tp_orders_count = tp_col.count_documents(tp_filter)
```

**After (PostgreSQL):**
```python
tp_filter = {
    'bg_code': bg.bg_code,
    'order_type': 'tp',
    'delete_flag': False,
    'active': True,
}
tp_filter.update(build_division_filter())
if branch_param and branch_param != '__all__':
    tp_filter['branch_code'] = branch_param
tp_orders_count = OrderCore.objects.filter(**tp_filter).count()
```

### Step 4: Replace Purchase Orders Vendor Data (MongoDB → PostgreSQL)

**Before (MongoDB):**
```python
po_col, po_tf = self.get_collection('purchaseorders')
po_filter = {**po_tf, "delete_flag": {"$ne": True}}
po_filter.update(build_division_filter())
po_filter.update(build_branch_filter())
po_data = decode_result(po_col.find(po_filter, {"_id": 0, "vendor": 1, "total_amount": 1}))
vendor_totals = {}
for po in po_data:
    v = po.get('vendor', 'Unknown')
    amt = float(po.get('total_amount', 0) or 0)
    vendor_totals[v] = vendor_totals.get(v, 0) + amt
```

**After (PostgreSQL):**
```python
po_filter = {
    'bg_code': bg.bg_code,
    'order_type': 'purchase',
    'delete_flag': False,
    'active': True,
}
po_filter.update(build_division_filter())
if branch_param and branch_param != '__all__':
    po_filter['branch_code'] = branch_param

# Note: PurchaseOrders in PostgreSQL don't have direct vendor linkage
# Need to query PurchaseOrder model from inventory domain
from domains.inventory.models import PurchaseOrder as InventoryPurchaseOrder
# Aggregate by vendor if available, otherwise use total_amount
vendor_totals = {}
po_qs = OrderCore.objects.filter(**po_filter).values('products').annotate(
    total=Sum('total_amount')
)
total_vendor_spend = sum(float(po['total'] or 0) for po in po_qs)
```

**⚠️ IMPORTANT:** The `products` field in `OrderCore` is a JSON field. Vendor extraction requires additional logic. Consider:
1. Querying `InventoryPurchaseOrder` model directly (has `vendor` field)
2. Or keeping MongoDB for purchase orders vendor analysis

### Step 5: Update Filter Helpers

**Change `build_division_filter()` to return Django ORM filter format:**
```python
def build_division_filter():
    if division_param and division_param != '__all__':
        return {"div_code": division_param}
    elif access_divisions:
        return {"div_code__in": access_divisions}  # Changed from $in to __in
    return {}
```

**Change `build_branch_filter()` to return Django ORM filter format:**
```python
def build_branch_filter():
    if branch_param and branch_param != '__all__':
        return {"branch_code": branch_param}
    return {}
```

---

## 🧪 **Testing Requirements**

### Unit Tests
- [ ] Verify `estimates_count` matches MongoDB baseline
- [ ] Verify `tp_orders_count` matches MongoDB baseline
- [ ] Verify `vendor_data` aggregation works correctly
- [ ] Verify all period types (daily, weekly, monthly, quarterly, yearly)

### Integration Tests
- [ ] Test with empty database (zero counts)
- [ ] Test with single division
- [ ] Test with multiple divisions
- [ ] Test with branch filters
- [ ] Test with date range filters

### Performance Tests
- [ ] Compare query times (MongoDB vs PostgreSQL)
- [ ] Verify no N+1 queries
- [ ] Check for missing indexes

---

## ⚠️ **Known Issues & Caveats**

### 1. Vendor Field Mapping
**Issue:** `OrderCore.products` is a JSON field, not a direct vendor reference  
**Solution:** 
- Option A: Query `InventoryPurchaseOrder` model directly (has `vendor` field)
- Option B: Keep MongoDB for purchase orders vendor analysis
- Option C: Add vendor field to `OrderCore` (requires schema migration)

**Recommendation:** Option A — use `InventoryPurchaseOrder` for vendor data

### 2. Filter Format Divergence
**Issue:** MongoDB uses `$in`, Django ORM uses `__in`  
**Solution:** Update `build_division_filter()` to return Django ORM format

### 3. Date Parsing
**Issue:** MongoDB returns datetime objects + strings; PostgreSQL returns only datetime  
**Solution:** Remove `_parse_date()` helper for PostgreSQL queries (not needed)

### 4. Backward Compatibility
**Issue:** API response format must remain unchanged  
**Solution:** Ensure all response fields are present with same structure

---

## 📝 **Files to Modify**

| File | Lines | Changes |
|------|-------|---------|
| `domains/shared/viewsets.py` | 285-560 | Refactor `AnalyticsViewSet.list()` |
| `domains/shared/services.py` | - | May need helper functions |

---

## 🧪 **Test Commands**

```bash
# Run analytics endpoint
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/shared/analytics?period=monthly"

# Compare with MongoDB baseline
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/shared/analytics?period=monthly&use_mongo=true"

# Run tests
python3 manage.py test domains.shared.tests.AnalyticsViewSetTest
```

---

## 📊 **Expected Results**

| Metric | Before | After |
|--------|--------|-------|
| MongoDB queries | 5 | 2 (finance only) |
| PostgreSQL queries | 0 | 3 (orders only) |
| Response time | ~200ms | ~150ms (estimated) |
| Data accuracy | 100% | 100% |

---

## 🚀 **Deployment Checklist**

- [ ] Code review completed
- [ ] All tests passing
- [ ] Performance benchmarked
- [ ] API response format verified
- [ ] Documentation updated
- [ ] Monitoring alerts configured
- [ ] Rollback plan documented

---

## 📚 **Related Documentation**

- [Unified Migration Guide](/home/chief/llm-wiki/Kung_OS/unified_migration_guide.md)
- [Orders ViewSets Refactor Handoff](/home/chief/llm-wiki/Kung_OS/handoffs/orders_viewsets_refactor_2026-07-02.md)
- [Phase 2/7 Migration Summary](/home/chief/llm-wiki/Kung_OS/unified_migration_guide.md#phase-27)

---

## 🎯 **Acceptance Criteria**

- [ ] `estimates_count` uses `OrderCore.objects.filter(order_type='estimate')`
- [ ] `tp_orders_count` uses `OrderCore.objects.filter(order_type='tp')`
- [ ] `vendor_data` uses `InventoryPurchaseOrder` or `OrderCore` (no MongoDB)
- [ ] `inwardpayments` still uses MongoDB (finance)
- [ ] `paymentvouchers` still uses MongoDB (finance)
- [ ] All period types working (daily, weekly, monthly, quarterly, yearly)
- [ ] Response format unchanged
- [ ] No regression in existing functionality

---

**Handoff Date:** 2026-07-02  
**Status:** Ready for implementation  
**Priority:** Medium  
**Estimated Effort:** 4-6 hours

---

## 📝 **Review Notes (2026-07-02)**

### ✅ **Reviewed & Approved**

**Reviewer:** Chief Architect  
**Review Date:** 2026-07-02  

#### **Strengths:**
1. ✅ Clear hybrid approach (MongoDB for finance, PostgreSQL for orders)
2. ✅ Detailed before/after code examples
3. ✅ Comprehensive testing requirements
4. ✅ Known issues well-documented
5. ✅ Backward compatibility considerations included

#### **Recommendations:**

1. **Purchase Orders Vendor Field (Step 4)**
   - **Issue:** `OrderCore.products` is JSON, vendor extraction is complex
   - **Recommendation:** Use `InventoryPurchaseOrder` model directly
   - **Action:** Update Step 4 with actual `InventoryPurchaseOrder` query

2. **Filter Helper Refactoring**
   - **Issue:** Current `build_division_filter()` returns MongoDB format (`$in`)
   - **Recommendation:** Create separate helper for PostgreSQL filters
   - **Action:** Add `build_pg_division_filter()` function

3. **Performance Optimization**
   - **Issue:** Count queries on large tables may be slow
   - **Recommendation:** Add database indexes if needed
   - **Action:** Monitor query performance after migration

#### **Additional Considerations:**

1. **Database Indexes**
   ```sql
   -- Recommended indexes for OrderCore
   CREATE INDEX idx_ordercore_type_active ON orders_core(order_type, active, delete_flag);
   CREATE INDEX idx_ordercore_bg_div ON orders_core(bg_code, div_code);
   ```

2. **Migration Script**
   - Consider creating a management command to validate data consistency
   - Run parallel queries (MongoDB + PostgreSQL) during transition

3. **Monitoring**
   - Add logging for query execution times
   - Set up alerts for query failures

#### **Updated Estimated Effort:**
- **Original:** 4-6 hours
- **Revised:** 6-8 hours (includes testing & monitoring setup)

---

**Review Status:** ✅ APPROVED with recommendations
