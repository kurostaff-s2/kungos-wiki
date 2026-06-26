# Kung_OS RBAC Migration — Data Migration Execution & Remaining Phases

**Source spec:** `/home/chief/llm-wiki/Kung_OS/` (authoritative)
**Parent handoff:** `26-06-2026_kungos-rbac-migration-remaining-work_296412.md`
**Generated:** 26-06-2026
**Goal:** Execute the M1 data migration script against live MongoDB sources, then complete Phases 5–9 (Orders, E-Commerce, Response Envelope, Legacy Cleanup, Final Verification) to achieve full spec compliance.

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `2059e2` |
| Entity type | `handoff` |
| Short description | Execute M1 data migration from MongoDB to PostgreSQL, then complete remaining phases (M4 Orders, E-Commerce, Response Envelope, Legacy Cleanup, Final Verification) |
| Status | `draft` |
| Source references | `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`, `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/identity_spec.md`, `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/cafe_spec.md` |
| Generated | 26-06-2026 |
| Next action / owner | Execute Phase 1 Data Migration (dry-run → live → validate), then proceed through Phases 5–9 sequentially |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:** `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`, `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/identity_spec.md`, `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`, `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/mongodb_schema.md`
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief/` (frontend), `/home/chief/Coding-Projects/kuro-gaming-dj-backend/` (legacy source for M5 product consolidation)
**Key files for this task:** See per-phase file maps below

---

## Current State (Completed Work)

### Schema Alignment (Complete)

All M1/M2/M3 schema changes are applied. The PostgreSQL tables exist and are spec-compliant.

| Phase | Status | Evidence |
|-------|--------|----------|
| **Phase 1 (M1 Schema)** | ✅ Complete | `users_identity`, `users_employee`, `users_customer`, `users_player`, `users_organization`, `users_vendor_profile`, `users_team_profile` tables exist |
| **Phase 2 (M2 Cafe)** | ✅ Complete | `Session.started_by/ended_by` → Identity FK, `AuthToken.identity` → Identity FK, `CafeWallet.identity` → Identity FK, `CafeWalletTransaction.created_by` → Identity FK, `CafeWalkin.identity` → Identity FK, `CafeUser` deprecated |
| **Phase 3 (M3 Mongo Rename)** | ✅ Complete | Commit `d37fbe2` — `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` across 31 collections |
| **Phase 4 (Identity Endpoints)** | ✅ Complete | `GET /api/v1/users/me`, `GET /api/v1/users/lookup`, `POST /api/v1/users/identity`, `PATCH /api/v1/users/identity/{id}` implemented in `users/api/identity_views.py` |

### Database State (Pre-Migration)

| Table | Count | Notes |
|-------|-------|-------|
| `users_identity` | 2 | Dev data only (seed records) |
| `users_employee` | 0 | Awaiting migration |
| `users_customer` | 2 | Dev data only |
| `users_player` | 0 | Awaiting migration |
| `users_organization` | 423 | Vendors migrated (409) + teams (14) — this was done in prior session |
| `users_vendor_profile` | 409 | Migrated |
| `users_team_profile` | 14 | Migrated |

### MongoDB Source Collections

| Collection | Count | Target | Notes |
|------------|-------|--------|-------|
| `reb_users` | 1,982 | `users_identity` + `users_customer` | Primary customer source |
| `players` | 117 (59 unique) | `users_identity` + `users_player` | Dedup by phone |
| `employee_attendance` | 966 (31 unique) | `users_identity` + `users_employee` | userid format (KCTM006) doesn't match reb_users — requires special handling |
| `serviceRequest` | 1,625 | `users_identity` + `users_customer` | Requestor source |
| `orders` | ~727 unique phones | `users_identity` + `users_customer` | Unregistered customers |
| `teams` | 14 | `users_organization` + `users_team_profile` | ✅ Already migrated |
| `vendors` | 409 | `users_organization` + `users_vendor_profile` | ✅ Already migrated |

### Uncommitted Changes (Must Be Committed First)

| File | Change |
|------|--------|
| `users/models.py` | `Identity.div_code` NOT NULL, `roles`/`primary_role` properties, `VendorProfile.gstin` relaxed |
| `domains/cafe_arcade/models.py` | All FK changes to Identity, `CafeUser` deprecated |
| `users/api/identity_views.py` | **NEW** — IdentityViewSet with lookup/create/update |
| `users/urls.py` | Identity endpoint URL registration |
| `users/management/commands/migrate_identity.py` | Canonical field names (`bg_code` instead of `bgcode`) |

**Pre-flight:** Commit these changes before executing data migration.

---

## Execution Order (DAG — Remaining Work)

```
Phase 1 (Data Migration) ──→ Phase 5 (M4 Orders) ──┐
                                                    │
Phase 6 (E-Commerce) ───────────────────────────────┼──→ Phase 8 (Legacy Cleanup)
                                                    │
Phase 7 (Response Envelope) ────────────────────────┤
                                                    │
                                                    ├──→ Phase 9 (Final Verification)
```

**Critical path:** Data Migration → M4 Orders → Legacy Cleanup → Final Verification
**Parallelizable:** Phase 6 (with Phase 5), Phase 7 (independent)

---

## Phase 1: Data Migration Execution

**What:** Execute `migrate_identity.py` to populate `users_identity` and extension tables from MongoDB sources.

**Dependencies:** Uncommitted changes committed, MongoDB connection verified

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Execute | `users/management/commands/migrate_identity.py` | Data migration command |

### Step 1: Pre-Flight Checks

```bash
# 1. Verify MongoDB connection
python manage.py shell -c "from pymongo import MongoClient; c = MongoClient('mongodb://127.0.0.1:27017', serverSelectionTimeoutMS=5000); c.admin.command('ping'); print('OK')"

# 2. Verify source collection counts
python manage.py shell -c "
from pymongo import MongoClient
db = MongoClient()['KungOS_Mongo_One']
for coll in ['reb_users', 'players', 'employee_attendance', 'serviceRequest', 'orders']:
    print(f'{coll}: {db[coll].count_documents({})}')
"

# 3. Verify PostgreSQL tables exist
python manage.py dbshell -c "\dt users_identity users_employee users_customer users_player users_organization"

# 4. Record pre-migration counts (for reconciliation)
python manage.py shell -c "
from users.models import Identity, EmployeeProfile, CustomerProfile, PlayerProfile, Organization
print(f'Identity: {Identity.objects.count()}')
print(f'Employee: {EmployeeProfile.objects.count()}')
print(f'Customer: {CustomerProfile.objects.count()}')
print(f'Player: {PlayerProfile.objects.count()}')
print(f'Organization: {Organization.objects.count()}')
"
```

### Step 2: Employee Bridge (One-Time, Pre-Migration)

**Before data migration, resolve employee userid→phone mapping via CustomUser.**

This is a **one-time migration step**, not a permanent bridge. After this, CustomUser is deprecated and employees route through Identity like all other user types.

```python
# users/management/commands/migrate_identity.py — employee bridge step
# Read CustomUser records that have employee_attendance entries
# Map: employee_attendance.userid → CustomUser.userid → CustomUser.phone → Identity

from users.models import CustomUser, Identity

for attendance_doc in db['employee_attendance'].distinct('userid'):
    try:
        custom_user = CustomUser.objects.get(userid=attendance_doc)
        phone = normalize_phone(custom_user.phone)
        # Create or link Identity for this employee
        identity, created = Identity.objects.get_or_create(
            phone=phone,
            defaults={'name': custom_user.name, 'bg_code': 'KURO0001'}
        )
        # Link CustomUser to Identity (one-time, for migration only)
        if not identity.user_id:
            identity.user = custom_user
            identity.save(update_fields=['user'])
    except CustomUser.DoesNotExist:
        # Flag for manual review — employee with no CustomUser record
        flagged.append(attendance_doc)
```

### Step 3: Dry Run

```bash
# Execute dry run — preview without writing
python manage.py migrate_identity --dry-run
```

**Verify dry run output:**
- [ ] All 5 remaining sources processed (reb_users, players, employee_attendance, serviceRequest, orders)
- [ ] Expected identity count matches source data (~2,500+ unique identities after dedup)
- [ ] No errors or exceptions
- [ ] `employee_attendance` processed via CustomUser bridge (31 employees migrated)

### Step 4: Live Migration

```bash
# Execute live migration
python manage.py migrate_identity --source=all
```

**Monitor:**
- [ ] Each source shows `identities`, `extensions`, `skipped`, `errors` counts
- [ ] `errors` count is 0 for all sources
- [ ] `employee_attendance` processed (31 employees migrated via CustomUser bridge)

### Step 4: Validation Gate

```bash
# Run validation
python manage.py migrate_identity --validate
```

**Validation checks (must all pass):**

| Check | Expected | Evidence |
|-------|----------|----------|
| Identity count | ≥ 2,500 | `users_identity.count()` |
| Employee count | 31 | `users_employee.count()` — migrated via CustomUser bridge |
| Customer count | ≥ 2,500 | `users_customer.count()` |
| Player count | 59 | `users_player.count()` |
| Phone normalization | 100% E.164 | `Identity.objects.exclude(phone__regex=r'^\+\d{1,3}\d{4,14}$').count() == 0` |
| FK integrity | 0 orphans | All extension rows reference valid identities |
| Duplicate phones | 0 per tenant | `Identity.objects.values('bg_code', 'phone').annotate(cnt=Count('id')).filter(cnt__gt=1).count() == 0` |
| Auth linkage | 31 employees linked | `Identity.objects.filter(user__isnull=False).count()` — CustomUser linked for employees |

### Step 5: Validation Gate

```bash
# Run validation
python manage.py migrate_identity --validate
```

**Validation checks (must all pass):**

| Check | Expected | Evidence |
|-------|----------|----------|
| Identity count | ≥ 2,500 | `users_identity.count()` |
| Employee count | 31 | `users_employee.count()` — migrated via CustomUser bridge |
| Customer count | ≥ 2,500 | `users_customer.count()` |
| Player count | 59 | `users_player.count()` |
| Phone normalization | 100% E.164 | `Identity.objects.exclude(phone__regex=r'^\+\d{1,3}\d{4,14}$').count() == 0` |
| FK integrity | 0 orphans | All extension rows reference valid identities |
| Duplicate phones | 0 per tenant | `Identity.objects.values('bg_code', 'phone').annotate(cnt=Count('id')).filter(cnt__gt=1).count() == 0` |
| Auth linkage | 31 employees linked | `Identity.objects.filter(user__isnull=False).count()` — CustomUser linked for employees |

**Completion Gate:**
- [ ] Dry run passes (zero errors)
- [ ] Live migration completes (zero errors)
- [ ] Validation gate passes (all checks OK)
- [ ] Pre/post-migration counts reconciled
- [ ] All 31 employees migrated via CustomUser bridge

---

## Phase 5: M4 Orders to PostgreSQL

**What:** Create PostgreSQL models for orders domain, migrate data from 4 MongoDB collections, update views.

**Dependencies:** Phase 1 (Data Migration — identity lookup must work)

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `domains/orders/models.py` | 7 PostgreSQL models (Order, EstimateDetail, InStoreDetail, TPOrderDetail, ServiceDetail, EshopDetail, OrderPayment) |
| Create | `domains/orders/migrations/0001_initial.py` | Orders schema migration |
| Create | `domains/orders/management/commands/migrate_orders.py` | Data migration from MongoDB |
| Modify | `domains/orders/api/viewsets.py` | Query PostgreSQL models |
| Modify | `domains/orders/api/serializers.py` | Serialize PostgreSQL models |

### Step 1: Create 7 Django Models

```python
# domains/orders/models.py
from django.db import models
from decimal import Decimal

class Order(models.Model):
    """Core order record — shared by all order types."""
    order_id = models.CharField(max_length=50, unique=True, db_index=True)
    order_type = models.CharField(max_length=20, choices=[
        ('estimate', 'Estimate'), ('in_store', 'In-Store'),
        ('tp_order', 'TP Order'), ('service', 'Service'), ('eshop', 'E-Shop'),
    ], db_index=True)
    status = models.CharField(max_length=20, default='pending', db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customer = models.ForeignKey(
        'users.Identity', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders',
    )
    bg_code = models.CharField(max_length=10, db_index=True)
    div_code = models.CharField(max_length=20, db_index=True)
    branch_code = models.CharField(max_length=30, blank=True, default='', null=True)
    bill_address = models.JSONField(null=True, blank=True)
    products = models.JSONField(null=True, blank=True)
    channel = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders_core'
        indexes = [
            models.Index(fields=['bg_code', 'div_code']),
            models.Index(fields=['order_type', 'status']),
            models.Index(fields=['-created_at']),
        ]

class EstimateDetail(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, primary_key=True, related_name='estimate_detail')
    item_name = models.CharField(max_length=200)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'estimate_detail'

# ... (InStoreDetail, TPOrderDetail, ServiceDetail, EshopDetail, OrderPayment follow same pattern)
```

### Step 2: Generate and Apply Migration

```bash
python manage.py makemigrations orders
python manage.py migrate orders
```

### Step 3: Create Migration Command

```python
# domains/orders/management/commands/migrate_orders.py
# Source: estimates, kgorders, tporders, serviceRequest (MongoDB)
# Map each document to appropriate PostgreSQL model
# Resolve user.phone → identity_id via Identity.objects.get(phone=normalized_phone)
# Batch insert with bulk_create (1000 per batch)
# --validate mode: row count + financial sum reconciliation
```

### Step 4: Execute Migration

```bash
python manage.py migrate_orders --validate
```

**Validation:**
- [ ] Source collection count == target table count
- [ ] Sum of all `total_amount` in Mongo == sum in PostgreSQL (zero discrepancy)
- [ ] All `identity_id` FKs resolve to valid identities

### Step 5: Update Viewsets

Replace MongoDB queries in `domains/orders/api/viewsets.py` with PostgreSQL model queries.

**Completion Gate:**
- [ ] 7 models created and migrated
- [ ] Data migration complete with validation
- [ ] Financial sums match (zero discrepancy)
- [ ] Viewsets use PostgreSQL models
- [ ] Files committed

---

## Phase 6: E-Commerce Implementation

**What:** Implement e-commerce domain: product consolidation (M5), eshop models, 17 endpoints, Cashfree integration.

**Dependencies:** Phase 5 (M4 Orders — for order/payment models), M5 product consolidation

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `domains/eshop/models.py` | Cart, CartItem, Wishlist, Address, EshopOrder, EshopOrderItem |
| Create | `domains/eshop/api/viewsets.py` | 17 endpoint viewsets |
| Create | `domains/eshop/api/serializers.py` | Eshop serializers |
| Modify | `domains/eshop/urls.py` | Wire 17 endpoints |
| Create | `domains/eshop/services/payment.py` | Cashfree payment gateway integration |
| Create | `domains/eshop/management/commands/migrate_products.py` | M5 product consolidation |

### Step 1: M5 Product Consolidation

Migrate 12 collections from `kuro-gaming-dj-backend` to `KungOS_Mongo_One`:
- Collections: `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets`
- Standardize field names (camelCase → snake_case)

### Step 2: Create Eshop Models

```python
# domains/eshop/models.py
class Cart(models.Model):
    identity = models.ForeignKey('users.Identity', on_delete=models.CASCADE, related_name='carts')
    status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_id = models.CharField(max_length=50)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

# ... (Wishlist, Address, EshopOrder, EshopOrderItem)
```

### Step 3: Implement 17 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/eshop/products` | Product listing |
| GET | `/eshop/products/{id}` | Product detail |
| GET/POST/PATCH/DELETE | `/eshop/cart` | Cart CRUD |
| GET/POST | `/eshop/wishlist` | Wishlist |
| GET/POST/PATCH | `/eshop/addresses` | Address management |
| POST | `/eshop/checkout` | Checkout |
| GET | `/eshop/orders` | Order listing |
| GET | `/eshop/orders/{id}` | Order detail |
| POST | `/eshop/payment/initiate` | Payment initiation |
| POST | `/eshop/payment/webhook` | Payment webhook |
| GET | `/eshop/payment/upi-qr` | UPI QR generation |

### Step 4: Cashfree Integration

```python
# domains/eshop/services/payment.py
class CashfreeService:
    def initiate_payment(self, order_id, amount, currency='INR') -> dict:
        """Create Cashfree order → return payment URL."""
        ...

    def handle_webhook(self, payload, signature) -> bool:
        """Verify signature → update order status."""
        ...

    def generate_upi_qr(self, amount, upi_id) -> str:
        """Generate UPI QR code for offline payment."""
        ...
```

**Completion Gate:**
- [ ] M5 product consolidation complete
- [ ] Eshop models created and migrated
- [ ] All 17 endpoints implemented
- [ ] Cashfree integration functional
- [ ] Tests pass
- [ ] Files committed

---

## Phase 7: Response Envelope Alignment

**What:** Standardize error responses, pagination, and filter params across all viewsets.

**Dependencies:** None (can run parallel to all phases)

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `backend/api_helpers.py` | Standardized error, pagination, filter helpers |
| Modify | All `domains/*/api/viewsets.py` | Use standardized helpers |
| Modify | `users/api/viewsets.py` | Use standardized helpers |

### Step 1: Standardize Error Responses

```python
# backend/api_helpers.py
from rest_framework.response import Response

def api_error(code, message, details=None, status=400):
    """Standardized error response envelope."""
    body = {
        'status': 'error',
        'error': {
            'code': code,
            'message': message,
        }
    }
    if details:
        body['error']['details'] = details
    return Response(body, status=status)
```

### Step 2: Implement Spec Pagination

```python
# Standard pagination response
{
    'data': [...],
    'pagination': {
        'page': 1,
        'per_page': 20,
        'total_items': 25,
        'total_pages': 2,
        'has_next': True,
        'has_prev': False,
    }
}
```

### Step 3: Standardize Filter Params

```
# Format: filter[field]=value
?filter[status]=active&filter[bg_code]=KCTM
?filter[amount][gte]=100&filter[amount][lte]=1000
```

**Completion Gate:**
- [ ] Error responses standardized across all viewsets
- [ ] Pagination matches spec format
- [ ] Filter params use `filter[field]=value` format
- [ ] Tests pass
- [ ] Files committed

---

## Phase 8: Legacy Cleanup

**What:** Remove all legacy code elements: adapter layer, deprecated endpoints, obsolete models, legacy field references.

**Dependencies:** Phase 1-7 complete (all new code paths functional)

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Delete | `users/rbac_mapping.py` | Remove adapter layer (if exists) |
| Modify | `backend/utils.py` | Remove `resolve_access_levels()` wrapper |
| Modify | All viewsets with `has_*_access()` calls | Replace with RBAC permission checks |
| Delete | Legacy `kuro/` endpoint routes | Remove from URL configs |
| Modify | `users/models.py` | Remove `KuroUser.roles`, `KuroUser.businessgroups` JSON fields |
| Create | `users/migrations/000X_drop_legacy_fields.py` | Drop legacy fields from DB |
| Create | `users/migrations/000X_drop_legacy_tables.py` | Drop `users_accesslevel`, `users_switchgroupmodel` |

### Step 1: Remove Adapter Layer

- Delete `users/rbac_mapping.py`
- Remove `resolve_access_levels()` from `backend/utils.py`
- Update ~520 `has_*_access()` call sites to use `resolve_permission()` directly

### Step 2: Remove Legacy Endpoints

| Legacy Endpoint | Replacement |
|----------------|-------------|
| `GET /kuro/user` | `GET /users/me` |
| `GET /kuro/user/{userid}` | `GET /users/{identity_id}` |
| `POST /cafe/sessions/start` | `POST /cafe/sessions` |
| `POST /cafe/sessions/{id}/food` | `POST /cafe-fnb/orders` |
| `GET /tournaments/tourneyregister` | `POST /tournaments/{id}/register` |
| `GET /kuro/accesslevel/{userid}` | `GET /rbac/user/{identity_id}` |
| `POST /kuro/switchgroup` | `POST /tenant/switch` |
| `GET /kuro/businessgroups` | `GET /tenant/accessible` |

### Step 3: Deprecate CustomUser

- Update `AUTH_USER_MODEL` from `'users.CustomUser'` to `'users.Identity'`
- Update `SIMPLE_JWT.USER_ID_FIELD` from `'userid'` to `'identity_id'`
- Update `CookieJWTAuthentication.get_user()` to resolve `identity_id` instead of `userid`
- Update all auth-related views to use `Identity` instead of `CustomUser`
- Retain `CustomUser` model as read-only (audit trail, historical data)
- Retain `KuroUser` model as read-only (audit trail, historical data)

### Step 4: Remove Legacy Model Fields

- `KuroUser.roles` (JSON) → replaced by `rbac_user_roles`
- `KuroUser.businessgroups` (JSON) → replaced by `rbac_user_roles.bg_code`
- `Session.food_charges` (DEPRECATED) → use `last_order_id`

### Step 5: Drop Legacy Tables

- `users_accesslevel` (55-col flat table)
- `users_switchgroupmodel`
- `users_customuser` (deprecated — data migrated to `users_identity`)
- `users_kurouser` (deprecated — data migrated to `users_employee`)

**Completion Gate:**
- [ ] Adapter layer removed
- [ ] Legacy endpoints removed (all return 404)
- [ ] Legacy fields dropped from models
- [ ] Legacy tables dropped from DB
- [ ] No regression in RBAC functionality
- [ ] Files committed

---

## Phase 9: Final Verification

**What:** Automated test suite confirming (a) all legacy code elements are removed, (b) all existing endpoints match target spec contracts.

**Dependencies:** Phase 8 (Legacy Cleanup complete)

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_legacy_removal.py` | Verify all legacy elements are gone |
| Create | `tests/test_auth_model.py` | Verify Identity as AUTH_USER_MODEL, JWT with identity_id |
| Create | `tests/test_endpoint_compliance.py` | Verify all endpoints match spec |
| Create | `tests/test_rbac_integrity.py` | Verify RBAC cascading without adapter |
| Create | `tests/fixtures/spec_endpoints.json` | Target spec endpoint definitions |

### Test Categories

#### Legacy Removal Tests (`test_legacy_removal.py`)

1. Adapter layer files are deleted
2. No imports of adapter layer remain in codebase
3. Legacy `resolve_access_levels()` wrapper is removed
4. Legacy endpoints return 404 (`/kuro/*`, `/cafe/sessions/start`, etc.)
5. Legacy model fields are removed (`KuroUser.roles`, `KuroUser.businessgroups`)
6. Legacy DB tables are dropped (`users_accesslevel`, `users_switchgroupmodel`)
7. CafeUser projection table is dropped (`caf_platform_users`)
8. No references to `Accesslevel` model remain (excluding migrations/tests)
9. No references to `Switchgroupmodel` remain (excluding migrations/tests)
10. `has_*_access()` calls replaced with `resolve_permission()`

#### AUTH_USER_MODEL Tests (`test_auth_model.py`)

1. `AUTH_USER_MODEL` is `'users.Identity'`
2. `SIMPLE_JWT.USER_ID_FIELD` is `'identity_id'`
3. Login response carries `identity_id` (not `userid`)
4. JWT token resolves to `Identity` object (not `CustomUser`)
5. `CookieJWTAuthentication.get_user()` returns `Identity`
6. No `CustomUser` references in auth flow (excluding migrations/tests)
7. No `KuroUser` references in auth flow (excluding migrations/tests)
8. Django admin works with `Identity` as auth model

#### Endpoint Compliance Tests (`test_endpoint_compliance.py`)

1. All spec endpoints exist and respond with expected status
2. Login response matches target envelope (`identity_id`, `roles[]`, `permissions[]`)
3. `/users/me` response matches target envelope
4. Error responses use standardized envelope
5. Pagination matches spec format (if Phase 7 complete)
6. All cafe sessions use identity FK (not CustomUser)
7. All wallets use identity FK (not CustomUser)
8. RBAC cascading works without adapter layer

#### RBAC Integrity Tests (`test_rbac_integrity.py`)

1. Permission resolution cascades correctly (division > BG > global)
2. Role assignment works end-to-end
3. Branch-level permissions are respected
4. Permission revocation is immediate

**Completion Gate (FINAL — migration complete only if all pass):**

- [ ] All 10 legacy removal tests pass
- [ ] All 8 auth model tests pass (Identity as AUTH_USER_MODEL, JWT with identity_id)
- [ ] All spec endpoint compliance tests pass
- [ ] Login response matches target envelope exactly
- [ ] RBAC cascading works without adapter layer
- [ ] No orphaned FK references in cafe/orders tables
- [ ] Full test suite passes (no regression)
- [ ] Files committed
- [ ] Migration declared complete

---

## Constraints

- **Hard cutover:** No dual-mode or legacy fallbacks in target spec. Adapter layer is temporary only.
- **Tenant isolation:** All queries must respect `bg_code`/`div_code`/`branch_code` scoping. No exceptions.
- **Data integrity:** M1 migration must pass `--validate` gate (row count reconciliation, phone normalization, FK integrity) before proceeding.
- **Financial safety:** M4 orders migration requires financial sum reconciliation (total amounts match before/after). Zero discrepancy.
- **No data loss:** M3 MongoDB field rename uses dual-read middleware during transition. Zero downtime requirement.
- **Test discipline:** TDD for all new endpoints. Existing endpoints verified against spec before marking complete.
- **Identity as AUTH_USER_MODEL:** `users.Identity` replaces `users.CustomUser` as Django's auth model. JWT carries `identity_id`. CustomUser is deprecated (data migrated, table retained for audit only).
- **Employee attendance:** `employee_attendance.userid` resolved via one-time CustomUser bridge (userid → CustomUser.phone → Identity). Not skipped.

---

## Success Criteria

- [ ] Phase 1: Data migration executed, validated, reconciled
- [ ] Phase 5: Orders migrated to PostgreSQL (7 tables, financial reconciliation)
- [ ] Phase 6: E-commerce domain functional (17 endpoints, Cashfree integration)
- [ ] Phase 7: Response envelope standardized (errors, pagination, filters)
- [ ] Phase 8: All legacy code removed (adapter, endpoints, fields, tables)
- [ ] Phase 9: Final verification suite passes (legacy removal + endpoint compliance)
- [ ] Zero regression in existing functionality
- [ ] All migrations applied cleanly

---

## Caveats & Uncertainty

1. **M1 phone dedup collisions:** Multiple MongoDB sources may have the same phone with different data. Migration command handles dedup (merge: take most recent). **Risk:** Data loss if merge strategy is incorrect. Verify with `--dry-run` first.

2. **Employee bridge dependency:** Employee migration requires CustomUser records to exist for all 31 employee userids. **Risk:** Missing CustomUser records → employees flagged for manual review. Verify with `--dry-run` before live migration.

3. **AUTH_USER_MODEL change:** Switching from `CustomUser` to `Identity` as `AUTH_USER_MODEL` requires updating all auth-related code (login, JWT issuance, permission checks, admin integration). **Risk:** Auth regression if any path still references CustomUser. Audit all `AUTH_USER_MODEL` references before deployment.

4. **JWT identity_id migration:** JWT `USER_ID_FIELD` changes from `userid` to `identity_id`. All existing tokens become invalid on deploy. **Risk:** Users forced to re-login. Coordinate with frontend for graceful token refresh.

5. **M4 financial data integrity:** Orders contain financial data. Any discrepancy in migration is unacceptable. **Mitigation:** `--validate` mode with financial sum reconciliation.

6. **Adapter layer call sites (~520):** Replacing `has_*_access()` calls requires careful review. Some may have custom logic not captured by RBAC. **Risk:** Permission regression if custom logic is lost. Audit before deletion.

7. **Frontend coordination:** Login response shape change requires frontend update (`kteam-fe-chief`). Coordinate before Phase 8 (legacy cleanup). **Risk:** Frontend breakage if deployed without frontend update.

8. **MongoDB connection:** Migration requires MongoDB running at `mongodb://127.0.0.1:27017`. Verify connection before execution.

9. **E-Commerce Cashfree credentials:** Phase 6 requires Cashfree API keys. Obtain from finance team before implementation.

---

## Notes for Executing Agent

- **Read the full Kung_OS spec directory** before starting any phase. The spec is the single source of truth.
- **Commit uncommitted changes first** before executing data migration (see "Uncommitted Changes" section above).
- **Each phase is independently executable** by a subagent. Use the phase structure for delegation.
- **Phase 9 is the final gate.** Do not declare the migration complete until Phase 9 passes.
- **Commit after each phase** with a descriptive message (e.g., `feat: M4 orders migration — 7 tables, financial reconciliation`).
- **Run the full test suite after each phase** to catch regressions early.
- **Coordinate with frontend team** before Phase 8 (legacy cleanup) to ensure frontend is updated.
- **MongoDB is local:** `KungOS_Mongo_One` database at `mongodb://127.0.0.1:27017`. Verify connection with `ping` command.
- **Dev data caveat:** The database has minimal dev data (2 identities, 423 organizations). Migration will populate ~2,500+ identities. Expect significant count changes.
