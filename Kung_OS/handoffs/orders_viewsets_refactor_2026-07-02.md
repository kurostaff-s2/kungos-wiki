# Task Handoff: Orders Viewsets MongoDB → PostgreSQL Refactoring

**Date:** 2026-07-02  
**Phase:** Phase 12 — API Endpoint Verification & Bug Fixes  
**Status:** Ready for Implementation  
**Priority:** HIGH  

---

## Executive Summary

The orders domain viewsets currently use MongoDB (`get_collection` + `find()`) for data access, but the target architecture uses PostgreSQL. PostgreSQL services have been created in `domains/orders/services_pg.py` but the viewsets haven't been refactored to use them.

**Current State:** 39 MongoDB calls across 6 viewsets  
**Target State:** 100% PostgreSQL service calls, 0 MongoDB calls  

---

## Architecture Context

### Target Architecture
```
ViewSets (domains/orders/viewsets.py)
    ↓
PostgreSQL Services (domains/orders/services_pg.py)
    ↓
Django ORM (domains/orders/models.py)
    ↓
PostgreSQL (KungOS_PG_One)
```

### Current Architecture (MIXED)
```
ViewSets (domains/orders/viewsets.py)
    ↓
MongoDB (get_collection + find()) ← MIXED with PostgreSQL services
```

### PostgreSQL Services Available
All CRUD operations are implemented in `domains/orders/services_pg.py`:
- **Estimates:** `get_estimates_pg()`, `get_estimate_detail_pg()`, `create_estimate_pg()`, `update_estimate_pg()`, `delete_estimate_pg()`
- **TP Orders:** `get_tp_orders_pg()`, `get_tp_order_detail_pg()`, `create_tp_order_pg()`, `update_tp_order_pg()`, `delete_tp_order_pg()`
- **In-Store Orders:** `get_instore_orders_pg()`, `get_instore_order_detail_pg()`, `create_instore_order_pg()`, `update_instore_order_pg()`, `delete_instore_order_pg()`
- **Unified Orders:** `get_unified_orders_pg()`, `get_unified_order_detail_pg()`, `create_unified_order_pg()`, `update_unified_order_pg()`, `delete_unified_order_pg()`
- **Service Requests:** `get_service_requests_pg()`, `get_service_request_detail_pg()`, `create_service_request_pg()`, `update_service_request_pg()`, `delete_service_request_pg()`

---

## Viewsets Requiring Refactoring

### 1. EstimateViewSet (Lines 47-213)
**Current:** list() uses PostgreSQL, retrieve/create/update/destroy use MongoDB  
**Target:** All methods use PostgreSQL services

**Methods to refactor:**
- `retrieve()` — Replace `collection.find_one()` with `get_estimate_detail_pg()`
- `create()` — Replace MongoDB insert with `create_estimate_pg()`
- `update()` — Replace MongoDB update with `update_estimate_pg()`
- `destroy()` — Replace MongoDB delete with `delete_estimate_pg()`

**Pattern:**
```python
# BEFORE (MongoDB)
collection, tenant_filter = self.get_collection(request)
doc = collection.find_one({**tenant_filter, '_id': ObjectId(pk)}, {'_id': 0})

# AFTER (PostgreSQL)
result = get_estimate_detail_pg(pk)
```

---

### 2. TPOrderViewSet (Lines 214-418)
**Current:** All methods use MongoDB  
**Target:** All methods use PostgreSQL services

**Methods to refactor:**
- `list()` — Replace with `get_tp_orders_pg()`
- `retrieve()` — Replace with `get_tp_order_detail_pg()`
- `create()` — Replace with `create_tp_order_pg()`
- `update()` — Replace with `update_tp_order_pg()`
- `destroy()` — Replace with `delete_tp_order_pg()`

---

### 3. InStoreViewSet (Lines 419-599)
**Current:** All methods use MongoDB  
**Target:** All methods use PostgreSQL services

**Methods to refactor:**
- `list()` — Replace with `get_instore_orders_pg()`
- `retrieve()` — Replace with `get_instore_order_detail_pg()`
- `create()` — Replace with `create_instore_order_pg()`
- `update()` — Replace with `update_instore_order_pg()`
- `destroy()` — Replace with `delete_instore_order_pg()`

---

### 4. OrdersViewSet (Lines 600-664)
**Current:** All methods use MongoDB  
**Target:** All methods use PostgreSQL services

**Methods to refactor:**
- `list()` — Replace with `get_unified_orders_pg()`
- `retrieve()` — Replace with `get_unified_order_detail_pg()`
- `create()` — Replace with `create_unified_order_pg()`
- `update()` — Replace with `update_unified_order_pg()`
- `destroy()` — Replace with `delete_unified_order_pg()`

---

### 5. PurchaseOrderViewSet (Lines 665-793)
**Current:** All methods use MongoDB  
**Target:** Move to inventory domain (already partially done in `domains/inventory/views.py`)

**Action:**
- Remove from `domains/orders/viewsets.py`
- Use existing implementation in `domains/inventory/views.py`

---

### 6. ServiceRequestViewSet (Lines 795-844)
**Current:** All methods use MongoDB  
**Target:** All methods use PostgreSQL services

**Methods to refactor:**
- `list()` — Replace with `get_service_requests_pg()`
- `retrieve()` — Replace with `get_service_request_detail_pg()`
- `create()` — Replace with `create_service_request_pg()`
- `update()` — Replace with `update_service_request_pg()`
- `destroy()` — Replace with `delete_service_request_pg()`

---

## Implementation Pattern

### Standard Refactoring Pattern

```python
# BEFORE (MongoDB pattern)
def list(self, request):
    try:
        result = resolve_access(request)
        collection, tenant_filter = self.get_collection(request)
        filters = self.apply_filter_params(request)
        
        output_list = decode_result(
            collection.find({**tenant_filter, **filters}, {'_id': 0})
            .sort([('created_date', -1)])
        )
        return success_response(output_list)
    except InputException as e:
        return error_response(str(e), code='VALIDATION_ERROR')

# AFTER (PostgreSQL pattern)
def list(self, request):
    try:
        result = resolve_access(request)
        user = result['user']
        accessible_divs = self.get_accessible_divisions(request)
        bg = result['bg']
        
        if not check_permission(result['permissions'], 'orders.tp'):
            return error_response('Access denied', code='AUTH_REQUIRED', 
                                 status_code=status.HTTP_401_UNAUTHORIZED)
        
        from domains.orders.services_pg import get_tp_orders_pg
        
        filters = self.apply_filter_params(request)
        limit = request.query_params.get('limit')
        
        tpData = get_tp_orders_pg(
            filters=filters,
            limit=int(limit) if limit else 0,
            bg_code=bg.bg_code,
        )
        
        return success_response(tpData or [])
    except InputException as e:
        return error_response(str(e), code='VALIDATION_ERROR')
```

### Key Changes Required

1. **Remove MongoDB imports:**
   ```python
   # REMOVE
   from backend.utils import get_collection
   from bson import ObjectId
   ```

2. **Replace `self.get_collection(request)` with service calls:**
   ```python
   # BEFORE
   collection, tenant_filter = self.get_collection(request)
   
   # AFTER
   from domains.orders.services_pg import get_tp_orders_pg
   result = get_tp_orders_pg(filters=filters, limit=limit, bg_code=bg_code)
   ```

3. **Update filter handling:**
   ```python
   # BEFORE (MongoDB filter format)
   filters = self.apply_filter_params(request)
   
   # AFTER (PostgreSQL filter format)
   filters = self.apply_filter_params(request)
   # Service functions handle filter conversion internally
   ```

4. **Update response format:**
   ```python
   # BEFORE (MongoDB document format)
   return success_response(doc)
   
   # AFTER (PostgreSQL service response format)
   return success_response(result)
   ```

---

## Testing Requirements

### Unit Tests
- [ ] Each viewset method returns correct HTTP status codes (200, 201, 404, 401)
- [ ] Permission checks work correctly
- [ ] Filter parameters are applied correctly
- [ ] Pagination works correctly

### Integration Tests
- [ ] List endpoints return data from PostgreSQL
- [ ] Detail endpoints return single record
- [ ] Create endpoints insert into PostgreSQL
- [ ] Update endpoints modify PostgreSQL records
- [ ] Delete endpoints soft-delete PostgreSQL records

### API Tests
```bash
# Test estimates
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/estimates
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/estimates/<id>

# Test TP orders
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/tp-orders
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/tp-orders/<id>

# Test in-store orders
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/in-store
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/in-store/<id>

# Test service requests
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/service-requests
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/orders/service-requests/<id>
```

---

## Files to Modify

1. **`/home/chief/Coding-Projects/KungOS-dj/domains/orders/viewsets.py`**
   - Refactor all 6 viewsets to use PostgreSQL services
   - Remove MongoDB imports and calls
   - Remove `get_collection` method from ServiceRequestViewSet

2. **`/home/chief/Coding-Projects/KungOS-dj/domains/orders/services_pg.py`**
   - Already complete (no changes needed)

3. **`/home/chief/Coding-Projects/KungOS-dj/domains/orders/urls.py`**
   - No changes needed (URL patterns remain the same)

4. **`/home/chief/Coding-Projects/KungOS-dj/domains/inventory/views.py`**
   - PurchaseOrderViewSet already implemented here (no changes needed)

---

## Acceptance Criteria

- [ ] All 39 MongoDB calls removed from `domains/orders/viewsets.py`
- [ ] All viewset methods use PostgreSQL services
- [ ] All endpoints return 200 OK with valid JSON
- [ ] All permission checks work correctly
- [ ] All CRUD operations work (list, retrieve, create, update, delete)
- [ ] No MongoDB dependencies in orders domain
- [ ] All API tests pass

---

## Estimated Effort

- **Time:** 2-3 hours
- **Risk:** MEDIUM (ensure filter format compatibility)
- **Rollback:** Simple (revert viewsets.py changes, keep PostgreSQL services)

---

## Notes

1. **PurchaseOrderViewSet** has been moved to inventory domain and should be removed from orders domain
2. **ServiceRequestViewSet** currently has a recursive call bug (`self.get_collection()` calling itself) — this will be fixed during refactoring
3. **Filter format** may need adjustment — PostgreSQL services expect different filter format than MongoDB
4. **Response format** may differ — PostgreSQL services return dicts, MongoDB returns documents

---

## References

- PostgreSQL Services: `/home/chief/Coding-Projects/KungOS-dj/domains/orders/services_pg.py`
- Orders Viewsets: `/home/chief/Coding-Projects/KungOS-dj/domains/orders/viewsets.py`
- Orders Models: `/home/chief/Coding-Projects/KungOS-dj/domains/orders/models.py`
- Inventory Views (Purchase Orders): `/home/chief/Coding-Projects/KungOS-dj/domains/inventory/views.py`

---

**Handoff Time:** 2026-07-02  
**Next Action:** Begin refactoring EstimateViewSet (highest priority — partially migrated)
