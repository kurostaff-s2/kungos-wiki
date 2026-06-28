# Cafe Tracker Endpoint Testing & API Contract Alignment

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | b86ea6 |
| Entity type | handoff |
| Short description | Test Cafe Tracker backend endpoints, fix API contract mismatches, align with target state PostgreSQL ORM |
| Status | draft |
| Source references | unified_cafe_dashboard_spec.md, views_tracker.py, cafe_fnb/models.py, orders/models.py |
| Generated | 28-06-2026 |
| Next action / owner | Execute Phase 1 (fix backend), Phase 2 (test endpoints), Phase 3 (align contracts) |

---

## Source Spec

**Source spec:** `/home/chief/llm-wiki/Kung_OS/architecture/unified_cafe_dashboard_spec.md`  
**Generated:** 28-06-2026 by agent  
**Goal:** Fix backend API contract mismatches, test all 5 Cafe Tracker endpoints, align with target state PostgreSQL ORM.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`  
**Reference docs:** 
- `/home/chief/llm-wiki/Kung_OS/architecture/unified_cafe_dashboard_spec.md`
- `/home/chief/llm-wiki/Kung_OS/architecture/cafe_tracker_test_checklist.md`

**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend)  
**Key files for this task:**
- `/home/chief/Coding-Projects/kteam-dj-chief/domains/cafe_arcade/views_tracker.py` (520 lines, 5 endpoints)
- `/home/chief/Coding-Projects/kteam-dj-chief/domains/cafe_arcade/models.py` (Session, Station, Game, PricePlan)
- `/home/chief/Coding-Projects/kteam-dj-chief/domains/cafe_fnb/models.py` (CafeFnbDetail, CafeMenuItems)
- `/home/chief/Coding-Projects/kteam-dj-chief/domains/orders/models.py` (OrderCore)
- `/home/chief/Coding-Projects/kteam-dj-chief/domains/cafe_arcade/urls.py` (tracker URL patterns)
- `/home/chief/Coding-Projects/kteam-dj-chief/users/permissions.py` (permission resolution)

---

## Current State Summary

### ✅ Implemented
- **5 backend endpoints** in `domains/cafe_arcade/views_tracker.py`:
  - `GET /api/v1/cafe/tracker/active` — List active sessions with F&B
  - `GET /api/v1/cafe/tracker/sessions/:id/fnb/orders` — Get F&B orders for session
  - `POST /api/v1/cafe/tracker/sessions/:id/fnb/orders` — Add F&B order to session
  - `POST /api/v1/cafe/tracker/sessions/:id/wallet/topup` — Top up wallet
  - `POST /api/v1/cafe/tracker/sessions/:id/close` — Close session with unified checkout
- **6 frontend files** in `kteam-fe-chief/src/pages/cafe/`:
  - `CustomerTracker.jsx` — Unified supervisor dashboard
  - `SessionCard.jsx` — Session card component
  - `AddFnbOrderModal.jsx` — Add F&B order modal
  - `WalletTopupModal.jsx` — Wallet top-up modal
  - `CloseSessionModal.jsx` — Close session modal
  - `cafeTrackerApi.js` — API client methods
- **URL patterns** registered in `domains/cafe_arcade/urls.py`
- **Test data seeded**: 7 stations, 6 games, 5 pricing rules

### ❌ Issues Found

#### 1. Backend 500 Error on POST /tracker/sessions/:id/fnb/orders
**Root cause:** `OrderCore` model field mismatch
- View tries to set `payment_method` field, but `OrderCore` model doesn't have this field
- `OrderCore` has: `order_id`, `order_type`, `status`, `customer`, `bg_code`, `total_amount`, etc.
- **Fix needed:** Remove `payment_method` from `OrderCore.objects.create()`, use available fields

#### 2. Permission System Not Configured
**Issue:** `cafe_manager` role assigned to admin user, but `resolve_permission()` returns level 0
**Root cause:** JWT token has empty `bg_code`, but user role is scoped to `bg_code='KURO0001'`
**Fix needed:**
- Create `UserTenantContext` for admin user with `bg_code='KURO0001'`
- Ensure JWT token carries correct `bg_code` from tenant context
- Permission check in `require_cafe_permission()` must pass `bg_code` to `resolve_permission()`

#### 3. Frontend API Client Mismatch
**Issue:** `cafeApi.js` calls `/api/v1/cafe/` (Arcade domain) but tracker endpoints are at `/api/v1/cafe/`
**Status:** Actually aligned — tracker endpoints are under `/cafe/` path, not `/cafe-fnb/`

#### 4. Tenant Context Extraction
**Issue:** `get_tenant_context()` extracts `bg_code` from JWT token claims
**Status:** Working correctly after fix — JWT now carries `bg_code: 'KURO0001'`

---

## Execution Order

```
Phase 1: Fix Backend API Contracts (30 min)
  ↓
Phase 2: Test All 5 Endpoints (45 min)
  ↓
Phase 3: Align Frontend API Client (15 min)
  ↓
Phase 4: End-to-End Integration Test (30 min)
```

---

## Phase 1: Fix Backend API Contracts

**What:** Fix `OrderCore` model field mismatch in `tracker_add_fnb_order()` view

**Files to Modify:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/cafe_arcade/views_tracker.py` | Remove `payment_method` from OrderCore.create(), use available fields |

**Steps:**
1. Read `domains/orders/models.py` to confirm available `OrderCore` fields
2. Update `tracker_add_fnb_order()` to use correct `OrderCore` fields:
   - `order_id` — required
   - `order_type` — required (use 'in_store')
   - `total_amount` — required
   - `status` — required (use 'completed')
   - `bg_code` — required
   - `created_by` — required (use `request.user.userid`)
   - **Remove:** `payment_method` (not a field on OrderCore)
3. Add `payment_method` to `CafeFnbDetail` only (which has the field)

**Tests:**
1. Run Django system check: `python3 manage.py check`
2. Verify no syntax errors: `python3 -m py_compile domains/cafe_arcade/views_tracker.py`

**Success Criteria:**
- [ ] `OrderCore.objects.create()` uses only valid fields
- [ ] `CafeFnbDetail.objects.create()` includes `payment_method`
- [ ] No 500 error on POST /tracker/sessions/:id/fnb/orders

---

## Phase 2: Test All 5 Endpoints

**What:** Manual testing of all 5 Cafe Tracker endpoints with real data

**Files to Test:**
- `domains/cafe_arcade/views_tracker.py`

**Test Script:**
```bash
# Login and get token
curl -s -X POST http://localhost:9001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin001","password":"admin123"}'

# Test each endpoint
# 1. GET /tracker/active
curl -s -X GET http://localhost:9001/api/v1/cafe/tracker/active \
  -H "Authorization: Bearer $TOKEN"

# 2. GET /tracker/sessions/:id/fnb/orders
curl -s -X GET http://localhost:9001/api/v1/cafe/tracker/sessions/1/fnb/orders \
  -H "Authorization: Bearer $TOKEN"

# 3. POST /tracker/sessions/:id/fnb/orders
curl -s -X POST http://localhost:9001/api/v1/cafe/tracker/sessions/1/fnb/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"menu_item_id":1,"quantity":2}]}'

# 4. POST /tracker/sessions/:id/wallet/topup
curl -s -X POST http://localhost:9001/api/v1/cafe/tracker/sessions/1/wallet/topup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount":500,"payment_method":"cash"}'

# 5. POST /tracker/sessions/:id/close
curl -s -X POST http://localhost:9001/api/v1/cafe/tracker/sessions/1/close \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"payment_method":"wallet"}'
```

**Expected Results:**
| Endpoint | Method | Expected Status | Expected Response |
|----------|--------|-----------------|-------------------|
| `/tracker/active` | GET | 200 | List of active sessions with F&B orders |
| `/tracker/sessions/:id/fnb/orders` | GET | 200 | List of F&B orders for session |
| `/tracker/sessions/:id/fnb/orders` | POST | 201 | Created order with total amount |
| `/tracker/sessions/:id/wallet/topup` | POST | 200 | Updated wallet balance |
| `/tracker/sessions/:id/close` | POST | 200 | Session closed with receipt |

**Success Criteria:**
- [ ] All 5 endpoints return correct HTTP status codes
- [ ] Response data matches expected schema
- [ ] No 500 errors in server logs
- [ ] Database records created correctly

---

## Phase 3: Align Frontend API Client

**What:** Verify frontend `cafeTrackerApi.js` calls correct backend endpoints

**Files to Verify:**
| Action | File | Purpose |
|--------|------|---------|
| Verify | `kteam-fe-chief/src/lib/cafeTrackerApi.js` | API client methods |
| Verify | `kteam-fe-chief/src/pages/cafe/CustomerTracker.jsx` | Page component |

**Steps:**
1. Read `cafeTrackerApi.js` to confirm endpoint paths
2. Verify paths match backend URL patterns:
   - `GET /api/v1/cafe/tracker/active`
   - `GET /api/v1/cafe/tracker/sessions/:id/fnb/orders`
   - `POST /api/v1/cafe/tracker/sessions/:id/fnb/orders`
   - `POST /api/v1/cafe/tracker/sessions/:id/wallet/topup`
   - `POST /api/v1/cafe/tracker/sessions/:id/close`
3. Verify request/response data structures match

**Success Criteria:**
- [ ] Frontend API client paths match backend URL patterns
- [ ] Request data structures match backend serializers
- [ ] Response data structures match backend responses

---

## Phase 4: End-to-End Integration Test

**What:** Test complete supervisor workflow end-to-end

**Workflow:**
1. Start session (already exists in test data)
2. Add F&B order to session
3. Top up wallet
4. Close session with unified checkout
5. Verify station released

**Steps:**
1. Login as admin user
2. Get active sessions list
3. Add F&B order to session 1
4. Top up wallet for session 1
5. Close session 1
6. Verify session status changed to 'closed'
7. Verify wallet balance deducted
8. Verify station released

**Success Criteria:**
- [ ] Complete workflow executes without errors
- [ ] Session status updated correctly
- [ ] Wallet balance updated correctly
- [ ] Station released after close
- [ ] Receipt generated (if applicable)

---

## Constraints

- **Target state uses PostgreSQL ORM** — No MongoDB queries allowed
- **Permission system uses RBAC** — All endpoints require `require_cafe_permission()`
- **Tenant context from JWT** — `bg_code` must be extracted from JWT token claims
- **No legacy MongoDB endpoints** — All endpoints must use PostgreSQL ORM models
- **OrderCore model fields** — Must use only fields defined in `domains/orders/models.py`

---

## Success Criteria

- [ ] All 5 backend endpoints return correct HTTP status codes
- [ ] No 500 errors in server logs
- [ ] Database records created correctly (OrderCore, CafeFnbDetail, CafeWalletTransaction)
- [ ] Frontend API client paths match backend URL patterns
- [ ] Complete supervisor workflow executes without errors
- [ ] Session status updated correctly after close
- [ ] Wallet balance updated correctly after top-up and close
- [ ] Station released after session close
- [ ] All existing tests still pass (no regression)

---

## Post-Wiring Verification (GATE)

- [ ] Server starts and responds to HTTP requests
- [ ] All 5 tracker endpoints respond correctly
- [ ] POST /tracker/sessions/:id/fnb/orders returns 201 (not 500)
- [ ] GET /tracker/active returns active sessions with F&B orders
- [ ] POST /tracker/sessions/:id/wallet/topup updates wallet balance
- [ ] POST /tracker/sessions/:id/close closes session and releases station
- [ ] Frontend builds without errors
- [ ] All existing tests still pass (no regression)

**Marking Complete:** The task is NOT complete until all post-wiring tests pass. A component that exists as code but cannot be started and verified end-to-end is incomplete.

---

## Notes for Next Phase

1. **Server running on port 9001** — Not 8000
2. **Test user:** `admin001` / `admin123` (has `cafe_manager` role)
3. **Tenant context:** `bg_code='KURO0001'` (must be in JWT token)
4. **Test data:** Session 1 exists with station ST-001, game GTA V
5. **Menu items:** IDs 1-5 available for F&B orders

---

## Appendix: OrderCore Model Fields

From `domains/orders/models.py`:

```python
class OrderCore(models.Model):
    order_id = models.CharField(max_length=50, unique=True, db_index=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPES, db_index=True)
    status = models.CharField(max_length=20, default='created', choices=ORDER_STATUSES, db_index=True)
    customer = models.ForeignKey(Identity, on_delete=models.PROTECT, ...)
    customer_name = models.CharField(max_length=200, blank=True, default='')
    customer_phone = models.CharField(max_length=50, blank=True, default='')
    customer_email = models.EmailField(blank=True, default='', null=True)
    bg_code = models.CharField(max_length=10, db_index=True)
    div_code = models.CharField(max_length=20, blank=True, default='', db_index=True)
    branch_code = models.CharField(max_length=30, blank=True, default='')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    channel = models.CharField(max_length=50, blank=True, default='')
    bill_address = models.JSONField(default=dict, blank=True)
    products = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    delete_flag = models.BooleanField(default=False, db_index=True)
    created_by = models.CharField(max_length=50, blank=True, default='')
    created_date = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_by = models.CharField(max_length=50, blank=True, default='')
    updated_date = models.DateTimeField(auto_now=True)
```

**Note:** `payment_method` is NOT a field on `OrderCore`. It should only be on `CafeFnbDetail`.

---

*Handoff generated: 28-06-2026*  
*Priority: P0 — Core Supervisor Workflow*  
*Estimated effort: ~2 hours*
