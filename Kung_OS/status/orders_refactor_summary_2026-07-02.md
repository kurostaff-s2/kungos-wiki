# Orders Viewsets Refactoring — Status Summary

**Date:** 2026-07-02  
**Phase:** Phase 12  
**Status:** PostgreSQL services complete, viewsets need refactoring  

---

## Current State

### PostgreSQL Services ✅ COMPLETE
All CRUD operations implemented in `domains/orders/services_pg.py`:
- ✅ Estimates (5 services)
- ✅ TP Orders (5 services)
- ✅ In-Store Orders (5 services)
- ✅ Unified Orders (5 services)
- ✅ Service Requests (5 services)

**Total:** 25 PostgreSQL services ready for use

### Viewsets Still Using MongoDB ⚠️ IN PROGRESS
- ❌ EstimateViewSet — list() uses PostgreSQL, retrieve/create/update/destroy use MongoDB
- ❌ TPOrderViewSet — All methods use MongoDB
- ❌ InStoreViewSet — All methods use MongoDB
- ❌ OrdersViewSet — All methods use MongoDB
- ❌ PurchaseOrderViewSet — All methods use MongoDB (should be moved to inventory)
- ❌ ServiceRequestViewSet — All methods use MongoDB

**Total MongoDB calls:** 39 across 6 viewsets

### API Endpoint Status
| Endpoint | Status | Notes |
|----------|--------|-------|
| `/orders/estimates` | ✅ 200 | Empty data (estimates not migrated) |
| `/orders/tp-orders` | ✅ 200 | Empty data (TP orders not migrated) |
| `/orders/in-store` | ✅ 200 | Empty data (in-store orders not migrated) |
| `/orders/service-requests` | ❌ 500 | Recursive call bug in get_collection |
| `/inventory/purchase-orders` | ❌ 500 | Permission denied (expected) |

---

## What's Been Done

1. ✅ Created PurchaseOrder Django model (maps to `inv_purchase_orders` table)
2. ✅ Created inventory domain services_pg.py with purchase order services
3. ✅ Added PurchaseOrderSerializer to inventory serializers.py
4. ✅ Added purchase order endpoints to inventory views.py
5. ✅ Added purchase order URLs to inventory urls.py
6. ✅ Created all PostgreSQL services for orders domain (25 services)
7. ✅ Fixed `apply_filter_params` and `get_collection` method references
8. ✅ Created comprehensive task handoff document

---

## What Needs to Be Done

### Priority 1: Fix ServiceRequestViewSet Bug
- **Issue:** Recursive call in `get_collection()` method
- **Fix:** Replace `self.get_collection()` with `get_collection()` (standalone function)
- **File:** `domains/orders/viewsets.py` line 804

### Priority 2: Refactor All Viewsets to PostgreSQL
- **Task:** Replace all MongoDB calls with PostgreSQL service calls
- **Files:** `domains/orders/viewsets.py`
- **Effort:** 2-3 hours
- **See:** Task handoff document for detailed pattern

### Priority 3: Move PurchaseOrderViewSet to Inventory
- **Task:** Remove from orders domain, use inventory domain implementation
- **Files:** Remove from `domains/orders/viewsets.py`
- **Already done:** Inventory domain has working implementation

---

## Next Steps

1. **Fix ServiceRequestViewSet bug** (10 minutes)
   - Replace recursive `self.get_collection()` with standalone `get_collection()`

2. **Refactor EstimateViewSet** (30 minutes)
   - Complete the migration started in list() method
   - Refactor retrieve, create, update, destroy methods

3. **Refactor TPOrderViewSet** (30 minutes)
   - Refactor all methods to use PostgreSQL services

4. **Refactor InStoreViewSet** (30 minutes)
   - Refactor all methods to use PostgreSQL services

5. **Refactor OrdersViewSet** (20 minutes)
   - Refactor all methods to use PostgreSQL services

6. **Remove PurchaseOrderViewSet from orders** (10 minutes)
   - Delete from orders domain (already in inventory)

7. **Test all endpoints** (30 minutes)
   - Verify all endpoints return 200 OK
   - Verify CRUD operations work correctly

**Total estimated time:** 2.5 hours

---

## Documentation

- **Task Handoff:** `/home/chief/llm-wiki/Kung_OS/handoffs/orders_viewsets_refactor_2026-07-02.md`
- **PostgreSQL Services:** `/home/chief/Coding-Projects/KungOS-dj/domains/orders/services_pg.py`
- **Orders Viewsets:** `/home/chief/Coding-Projects/KungOS-dj/domains/orders/viewsets.py`
- **Orders Models:** `/home/chief/Coding-Projects/KungOS-dj/domains/orders/models.py`
- **Inventory Views (Purchase Orders):** `/home/chief/Coding-Projects/KungOS-dj/domains/inventory/views.py`

---

## Key Decisions

1. **Purchase orders belong to inventory domain** — moved from orders to inventory
2. **PostgreSQL services are complete** — no need to create more services
3. **Viewsets need full refactoring** — cannot partially migrate
4. **ServiceRequestViewSet has a bug** — must fix before refactoring

---

**Status:** Ready for implementation  
**Next Action:** Begin refactoring EstimateViewSet (highest priority)
