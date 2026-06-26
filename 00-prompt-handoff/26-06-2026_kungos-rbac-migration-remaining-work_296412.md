# Kung_OS RBAC Migration — Remaining Work Execution Plan

**Source spec:** `/home/chief/llm-wiki/Kung_OS/` (authoritative)
**Parent handoff:** `26-06-2026_accesslevel-to-rbac-migration_e1ae60.md`
**Generated:** 26-06-2026
**Goal:** Execute all remaining migration phases to bring `kteam-dj-chief` from RBAC-complete to full Kung_OS spec compliance, with a final verification phase confirming legacy code removal and endpoint spec alignment.

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `296412` |
| Entity type | `handoff` |
| Short description | Complete Kung_OS migration: M1 identity consolidation, M2 cafe alignment, M3 Mongo field rename, missing endpoints, M4 orders, e-commerce, legacy cleanup, and final verification |
| Status | `draft` |
| Source references | `/home/chief/llm-wiki/Kung_OS/architecture/`, `/home/chief/llm-wiki/Kung_OS/specs/` |
| Generated | 26-06-2026 |
| Next action / owner | Execute Phase 1 (M1 Identity Consolidation) — blocks all downstream phases |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:** `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`, `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/mongodb_schema.md`, `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/migration_spec.md`, `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`, `/home/chief/llm-wiki/Kung_OS/architecture/identity_layer.md`, `/home/chief/llm-wiki/Kung_OS/architecture/rbac_system.md`
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief/` (frontend), `/home/chief/Coding-Projects/kuro-gaming-dj-backend/` (legacy source)
**Key files for this task:** See per-phase file maps below

---

## Execution Order (DAG)

```
Phase 1 (M1 Identity) ──┬──→ Phase 2 (M2 Cafe) ──┐
                         │                         │
Phase 3 (M3 Mongo) ──────┤                         ├──→ Phase 8 (Legacy Cleanup)
                         │                         │
Phase 4 (Identity API) ──┘                         │
                                                   ├──→ Phase 9 (Final Verification)
Phase 5 (M4 Orders) ───────────────────────────────┤
                                                   │
Phase 6 (E-Commerce) ──────────────────────────────┤
                                                   │
Phase 7 (Response Envelope) ───────────────────────┘
```

**Critical path:** Phase 1 → Phase 2 → Phase 4 → Phase 8 → Phase 9
**Parallelizable:** Phase 3 (with M1/M2), Phase 5 (independent), Phase 6 (with M5), Phase 7 (independent)

---

## Constraints

- **Hard cutover:** No dual-mode or legacy fallbacks in target spec. Adapter layer (`rbac_mapping.py`) is temporary only.
- **Tenant isolation:** All queries must respect `bg_code`/`div_code`/`branch_code` scoping. No exceptions.
- **Data integrity:** M1 migration must pass `--validate` gate (row count reconciliation, phone normalization, FK integrity) before proceeding.
- **Frontend parity:** Login response shape must be stable before frontend (`kteam-fe-chief`) is updated. Coordinate with frontend team.
- **No data loss:** M3 MongoDB field rename uses dual-read middleware during transition. Zero downtime requirement.
- **Financial safety:** M4 orders migration requires financial sum reconciliation (total amounts match before/after).
- **Test discipline:** TDD for all new endpoints. Existing endpoints verified against spec before marking complete.

---

## Phase 1: M1 Identity Consolidation

**What:** Generate Django migrations for 9 M1 identity tables, execute data migration from 7 MongoDB sources, validate data integrity.

**Dependencies:** None (Phase 0 — RBAC migration is complete)

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `users/migrations/0002_identity_consolidation.py` | M1 identity tables migration |
| Modify | `users/management/commands/migrate_identity.py` | Populate from MongoDB sources |
| Modify | `users/models.py` | Wire Identity FK into CustomUser (if not already) |
| Create | `users/management/commands/validate_identity.py` | Post-migration validation gate |

**Steps:**

1. **Generate migration 0002** for the 9 M1 tables:
   - `users_identity` (identity_id PK, phone E.164, bg_code, div_code, branch_code, name, email, metadata JSON, created_at, updated_at)
   - `users_employee` (identity FK, employee_id, designation, department, joining_date, status)
   - `users_customer` (identity FK, membership_tier, total_spent, loyalty_points, status)
   - `users_player` (identity FK, player_id, skill_rating, tournament_count, status)
   - `users_organization` (org_id PK, name, type, bg_code, div_code, contact_info JSON)
   - `users_vendor_profile` (identity FK, vendor_id, gstin, pan, payment_terms, status)
   - `users_team_profile` (identity FK, team_name, sport, division, status)
   - `team_memberships` (team_profile FK, identity FK, role, joined_at, is_active)
   - `identity_phone_aliases` (identity FK, phone E.164 UNIQUE, is_primary, source)

2. **Execute `python manage.py migrate users 0002`**

3. **Execute `python manage.py migrate_identity`** with sources:
   - `reb_users` (Mongo, 1,979 records) → `users_identity` + `users_customer`
   - `players` (Mongo, 117 docs, 59 unique) → `users_identity` + `users_player`
   - `employee_attendance` (Mongo, 966 docs, 31 unique) → `users_identity` + `users_employee`
   - `serviceRequest` (Mongo, 1,328) → `users_identity` + `users_customer`
   - `orders.user.phone` (Mongo, 727) → `users_identity` + `users_customer`
   - `teams` (Mongo, 14) → `users_organization` + `users_team_profile`
   - `vendors` (Mongo, 409) → `users_organization` + `users_vendor_profile`

4. **Execute `python manage.py validate_identity`** — validation gate:
   - Row count reconciliation (source vs. target)
   - Phone normalization (all E.164, no duplicates)
   - FK integrity (all extension rows reference valid identities)
   - Phone alias uniqueness (no collisions)

5. **Update `AuthViewSet.login()`** to emit real `identity_id` from `users_identity` (not `userid`)

**Tests:**

1. **Test migration creates tables:** `python manage.py dbshell -c "\dt users_*"` — all 9 tables exist
2. **Test data migration counts:** Assert `users_identity.count()` ≥ expected unique count from sources
3. **Test phone normalization:** Assert all `phone` fields match `^\+91\d{10}$` or `^\+\d{1,3}\d{4,14}$`
4. **Test FK integrity:** Assert zero orphaned extension rows (`SELECT COUNT(*) FROM users_employee e LEFT JOIN users_identity i ON e.identity_id = i.identity_id WHERE i.identity_id IS NULL`)
5. **Test login response:** Assert `POST /auth/login` returns `identity_id` in `ID000001` format

**Completion Gate:**
- [ ] Migration 0002 applied successfully
- [ ] All 7 MongoDB sources migrated
- [ ] Validation gate passes (zero errors)
- [ ] Login response emits correct `identity_id` format
- [ ] Files committed

---

## Phase 2: M2 Cafe Schema Alignment

**What:** Update cafe domain models to reference `Identity` instead of `CustomUser`. Drop `CafeUser` projection table.

**Dependencies:** Phase 1 (M1 Identity Consolidation complete)

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/cafe_arcade/models.py` | Change FKs from CustomUser to Identity |
| Create | `domains/cafe_arcade/migrations/0005_m2_identity_fk.py` | Schema migration for FK changes |
| Modify | `domains/cafe_arcade/api/viewsets.py` | Update queries to use identity_id |
| Delete | `domains/cafe_arcade/models.py::CafeUser` | Drop thin projection table |

**Steps:**

1. **Modify `CafeWalkin` model:**
   - Remove `phone = models.CharField(max_length=15, unique=True)`
   - Add `identity = models.OneToOneField('users.Identity', on_delete=models.CASCADE, related_name='cafe_walkin')`
   - Add `phone` as non-unique field (denormalized from Identity for read performance)

2. **Modify `CafeWallet` model:**
   - Change `customer = models.OneToOneField('users.CustomUser', ...)` to `models.OneToOneField('users.Identity', ...)`
   - Update related_name if needed

3. **Modify `CafeWalletTransaction` model:**
   - Change `created_by = models.ForeignKey('users.CustomUser', ...)` to `models.ForeignKey('users.Identity', ...)`

4. **Modify `AuthToken` model:**
   - Change `user = models.ForeignKey('users.CustomUser', ...)` to `models.ForeignKey('users.Identity', ...)`

5. **Drop `CafeUser` model** — replaced by `users_identity`. Remove model, serializer, and viewset references.

6. **Generate migration:** `python manage.py makemigrations cafe_arcade`

7. **Execute migration:** `python manage.py migrate cafe_arcade`

8. **Update viewsets** to query by `identity_id` instead of `user_id`/`userid`

**Tests:**

1. **Test FK integrity:** Assert all cafe tables reference valid `identity_id` values
2. **Test wallet operations:** Create wallet → topup → spend → assert balance correct
3. **Test session creation:** Create session with identity → assert no FK errors
4. **Test CafeUser removal:** Assert `caf_platform_users` table is dropped (no regression)

**Completion Gate:**
- [ ] All FK changes applied
- [ ] Migration executed successfully
- [ ] Cafe operations functional with identity FKs
- [ ] `CafeUser` table dropped
- [ ] Files committed

---

## Phase 3: M3 MongoDB Field Rename

**What:** Rename `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` across 31 MongoDB collections with zero downtime.

**Dependencies:** None (can run parallel to Phase 1/2)

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `plat/tenant/dual_read.py` | Dual-read middleware for legacy/canonical field names |
| Create | `plat/tenant/management/commands/rename_fields.py` | Batch field rename command |
| Modify | `plat/tenant/collection.py` | Use canonical field names |
| Modify | `plat/observability/middleware.py` | Read canonical JWT claim names |

**Steps:**

1. **Implement dual-read middleware** (`plat/tenant/dual_read.py`):
   - `DualReadField` class that reads both `bgcode` and `bg_code` (returns first non-null)
   - Index lookup fallback: if `{field}_idx` doesn't exist, try `{legacy_field}_idx`
   - Transparent to callers — no code changes needed in viewsets

2. **Create batch rename command** (`rename_fields.py`):
   - Accept `--collections` (comma-separated) or `--all`
   - For each collection: update documents in batches of 1000, rebuild indexes
   - Idempotent: safe to re-run (checks for canonical fields before renaming)
   - `--dry-run` mode: report changes without executing
   - `--validate` mode: verify all documents have canonical fields

3. **Execute rename in maintenance window:**
   - `python manage.py rename_fields --all --validate`
   - Monitor for index rebuild completion

4. **Update `TenantContextMiddleware`** to read canonical JWT claim names (`bg_code`, `div_codes`, `branch_codes`)

5. **Remove dual-read middleware** after all collections are renamed

**Tests:**

1. **Test dual-read:** Query with legacy field name → returns correct result
2. **Test rename idempotency:** Run rename twice → no errors, no duplicate fields
3. **Test index rebuild:** Assert canonical indexes exist, legacy indexes removed
4. **Test middleware:** JWT with canonical claims → tenant context extracted correctly

**Completion Gate:**
- [ ] Dual-read middleware implemented and tested
- [ ] All 31 collections renamed
- [ ] Indexes rebuilt
- [ ] Middleware reads canonical claims
- [ ] Dual-read middleware removed
- [ ] Files committed

---

## Phase 4: Missing Identity Endpoints

**What:** Implement the 6 missing identity-related API endpoints from the spec.

**Dependencies:** Phase 1 (M1 Identity Consolidation complete)

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/api/viewsets.py` | Add lookup, identity CRUD, extension endpoints |
| Modify | `users/api/serializers.py` | Add IdentityLookupSerializer, ExtensionSerializers |
| Modify | `users/urls.py` | Route new endpoints |
| Modify | `backend/urls.py` | Route `/tenant/accessible` |

**Steps:**

1. **Implement `GET /users/lookup?phone=+91...`:**
   - Normalize phone to E.164
   - Search `identity_phone_aliases` for match
   - Return identity + active extensions (employee, customer, player)
   - 404 if not found

2. **Implement `POST /users/identity`:**
   - Accept: `phone` (required), `name` (optional), `bg_code` (from JWT)
   - Create `Identity` record + `PhoneAlias`
   - Return created identity with `identity_id`

3. **Implement `PATCH /users/identity/{id}`:**
   - Accept: `name`, `email`, `metadata` (partial update)
   - Verify caller owns identity or has `manage_users` permission
   - Return updated identity

4. **Implement `GET /users/{id}`:**
   - Return identity + all active extensions
   - Include `roles[]` and `permissions[]` from RBAC

5. **Implement extension endpoints:**
   - `GET /users/{id}/employee` — return `users_employee` row (404 if not employee)
   - `GET /users/{id}/customer` — return `users_customer` row (404 if not customer)
   - `GET /users/{id}/player` — return `users_player` row (404 if not player)

6. **Implement `GET /tenant/accessible`:**
   - Return list of BGs/divisions/branches the authenticated user can access
   - Derived from `rbac_user_roles` + `rbac_user_role_branches`

7. **Update `GET /auth/me`** (if separate from `/users/me`) — or verify `/users/me` is sufficient per spec

**Tests:**

1. **Test phone lookup:** Create identity → lookup by phone → returns correct identity
2. **Test identity creation:** POST with phone → returns identity with `ID000001` format ID
3. **Test extension retrieval:** Create employee → GET `/users/{id}/employee` → returns employee data
4. **Test tenant accessible:** Assign roles across 2 BGs → GET `/tenant/accessible` → returns both
5. **Test permission gating:** Unauthenticated request → 401; insufficient permissions → 403

**Completion Gate:**
- [ ] All 6 endpoints implemented
- [ ] Endpoints match spec response shape
- [ ] Permission gating enforced
- [ ] Tests pass
- [ ] Files committed

---

## Phase 5: M4 Orders to PostgreSQL

**What:** Create PostgreSQL models for orders domain, migrate data from 4 MongoDB collections, update views.

**Dependencies:** None (can run parallel to Phase 1-4)

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `domains/orders/models.py` | 7 PostgreSQL models |
| Create | `domains/orders/migrations/0001_initial.py` | Orders schema migration |
| Create | `domains/orders/management/commands/migrate_orders.py` | Data migration from MongoDB |
| Modify | `domains/orders/api/viewsets.py` | Query PostgreSQL models |
| Modify | `domains/orders/api/serializers.py` | Serialize PostgreSQL models |

**Steps:**

1. **Create 7 Django models:**
   - `Order` (order_id PK, identity FK, type, status, total_amount, bg_code, div_code, branch_code, created_at, updated_at)
   - `EstimateDetail` (order FK, item_name, quantity, unit_price, tax, total, metadata JSON)
   - `InStoreDetail` (order FK, item_name, quantity, unit_price, tax, total, station FK)
   - `TPOrderDetail` (order FK, item_name, quantity, unit_price, tax, total, tp_id)
   - `ServiceDetail` (order FK, service_type, description, duration, cost, status)
   - `EshopDetail` (order FK, product_id, quantity, unit_price, tax, total, shipping_address JSON)
   - `OrderPayment` (order FK, payment_method, amount, status, transaction_id, gateway_response JSON)

2. **Generate and apply migration:** `python manage.py makemigrations orders && python manage.py migrate orders`

3. **Create migration command** (`migrate_orders.py`):
   - Source: `estimates`, `kgorders`, `tporders`, `serviceRequest` (MongoDB)
   - Map each document to appropriate PostgreSQL model
   - Resolve `user.phone` → `identity_id` via `identity_phone_aliases`
   - Batch insert with `bulk_create` (1000 per batch)
   - `--validate` mode: row count + financial sum reconciliation

4. **Execute migration:** `python manage.py migrate_orders --validate`

5. **Update viewsets** to use PostgreSQL models instead of MongoDB queries

6. **Wire outbox pattern** for cross-store consistency (order creation → MongoDB write via outbox)

**Tests:**

1. **Test data migration counts:** Source collection count == target table count
2. **Test financial reconciliation:** Sum of all `total_amount` in Mongo == sum in PostgreSQL
3. **Test FK resolution:** All `identity_id` FKs resolve to valid identities
4. **Test viewset queries:** List orders → returns correct data from PostgreSQL
5. **Test outbox pattern:** Create order → verify outbox entry → verify MongoDB write

**Completion Gate:**
- [ ] 7 models created and migrated
- [ ] Data migration complete with validation
- [ ] Financial sums match (zero discrepancy)
- [ ] Viewsets use PostgreSQL models
- [ ] Outbox wired for cross-store consistency
- [ ] Files committed

---

## Phase 6: E-Commerce Implementation

**What:** Implement e-commerce domain: product consolidation (M5), eshop models, 17 endpoints, Cashfree integration.

**Dependencies:** Phase 5 (M4 Orders — for order/payment models), M5 product consolidation

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `domains/eshop/models.py` | Cart, Wishlist, Address, Order, Payment models |
| Create | `domains/eshop/api/viewsets.py` | 17 endpoint viewsets |
| Create | `domains/eshop/api/serializers.py` | Eshop serializers |
| Modify | `domains/eshop/urls.py` | Wire 17 endpoints |
| Create | `domains/eshop/services/payment.py` | Cashfree payment gateway integration |
| Create | `domains/eshop/management/commands/migrate_products.py` | M5 product consolidation |

**Steps:**

1. **Execute M5 product consolidation:**
   - Migrate 12 collections from `kuro-gaming-dj-backend` to `KungOS_Mongo_One`
   - Collections: `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets`
   - Standardize field names (camelCase → snake_case)

2. **Create eshop Django models:**
   - `Cart` (identity FK, status, created_at, updated_at)
   - `CartItem` (cart FK, product_id, quantity, unit_price, subtotal)
   - `Wishlist` (identity FK, product_id, added_at)
   - `Address` (identity FK, label, full_address JSON, is_default, bg_code)
   - `EshopOrder` (order_id PK, identity FK, status, total_amount, shipping_address JSON, payment_status, bg_code)
   - `EshopOrderItem` (eshop_order FK, product_id, quantity, unit_price, subtotal)

3. **Implement 17 endpoints** (see spec for full list):
   - Products: GET `/eshop/products`, GET `/eshop/products/{id}`
   - Cart: GET/POST/PATCH/DELETE `/eshop/cart`
   - Wishlist: GET/POST `/eshop/wishlist`
   - Addresses: GET/POST/PATCH `/eshop/addresses`
   - Checkout: POST `/eshop/checkout`
   - Orders: GET `/eshop/orders`, GET `/eshop/orders/{id}`
   - Payments: POST `/eshop/payment/initiate`, POST `/eshop/payment/webhook`, GET `/eshop/payment/upi-qr`

4. **Integrate Cashfree payment gateway:**
   - `initiate_payment()` → create Cashfree order → return payment URL
   - `handle_webhook()` → verify signature → update order status
   - `generate_upi_qr()` → generate UPI QR code for offline payment

5. **Wire outbox** for order → inventory sync

**Tests:**

1. **Test product listing:** GET `/eshop/products` → returns products from consolidated collections
2. **Test cart flow:** Add item → update quantity → remove item → assert correct state
3. **Test checkout flow:** Create cart → checkout → assert order created with correct totals
4. **Test payment initiation:** POST `/eshop/payment/initiate` → returns Cashfree payment URL
5. **Test webhook handling:** Simulate Cashfree webhook → assert order status updated

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

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `backend/api_helpers.py` | Standardized error, pagination, filter helpers |
| Modify | All `domains/*/api/viewsets.py` | Use standardized helpers |
| Modify | `users/api/viewsets.py` | Use standardized helpers |

**Steps:**

1. **Standardize error responses:**
   - All errors use `api_error(code, message, details)` helper
   - Return envelope: `{status: "error", code: "...", message: "...", details: {...}}`
   - Consistent HTTP status codes (400, 401, 403, 404, 422, 500)

2. **Implement spec pagination:**
   - Replace DRF default pagination with spec format
   - Response includes: `{data: [...], pagination: {page, per_page, total_items, total_pages, has_next, has_prev}}`
   - Query params: `page`, `per_page` (default 20, max 100)

3. **Standardize filter params:**
   - Format: `filter[field]=value` (e.g., `?filter[status]=active&filter[bg_code]=KCTM`)
   - Replace ad-hoc filter params with standardized format
   - Support range filters: `filter[amount][gte]=100&filter[amount][lte]=1000`

**Tests:**

1. **Test error response shape:** Trigger 400/401/403/404 → assert envelope format
2. **Test pagination:** List with 25 items, per_page=10 → assert `total_items=25, total_pages=3`
3. **Test filter params:** `?filter[status]=active` → returns only active items

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

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Delete | `users/rbac_mapping.py` | Remove adapter layer |
| Modify | `backend/utils.py` | Remove `resolve_access_levels()` wrapper |
| Modify | All viewsets with `has_*_access()` calls | Replace with RBAC permission checks |
| Delete | Legacy `kuro/` endpoint routes | Remove from URL configs |
| Modify | `users/models.py` | Remove `KuroUser.roles`, `KuroUser.businessgroups` JSON fields |
| Create | `users/migrations/000X_drop_legacy_fields.py` | Drop legacy fields from DB |
| Create | `users/migrations/000X_drop_legacy_tables.py` | Drop `users_accesslevel`, `users_switchgroupmodel` |

**Steps:**

1. **Remove adapter layer:**
   - Delete `users/rbac_mapping.py`
   - Remove `resolve_access_levels()` from `backend/utils.py`
   - Update ~520 `has_*_access()` call sites to use `resolve_permission()` directly

2. **Remove legacy endpoints:**
   - `GET /kuro/user` → replaced by `GET /users/me`
   - `GET /kuro/user/{userid}` → replaced by `GET /users/{identity_id}`
   - `POST /cafe/sessions/start` → replaced by `POST /cafe/sessions`
   - `POST /cafe/sessions/{id}/food` → replaced by `POST /cafe-fnb/orders`
   - `GET /tournaments/tourneyregister` → replaced by `POST /tournaments/{id}/register`
   - `GET /kuro/accesslevel/{userid}` → replaced by `GET /rbac/user/{identity_id}`
   - `POST /kuro/switchgroup` → replaced by `POST /tenant/switch`
   - `GET /kuro/businessgroups` → replaced by `GET /tenant/accessible`

3. **Remove legacy model fields:**
   - `KuroUser.roles` (JSON) → replaced by `rbac_user_roles`
   - `KuroUser.businessgroups` (JSON) → replaced by `rbac_user_roles.bg_code`
   - `Session.food_charges` (DEPRECATED) → use `last_order_id`

4. **Drop legacy tables:**
   - `users_accesslevel` (55-col flat table)
   - `users_switchgroupmodel`

5. **Update frontend** (`kteam-fe-chief`) to consume new response shapes

**Tests:**

1. **Test adapter removal:** Assert `rbac_mapping.py` is deleted, no imports remain
2. **Test legacy endpoint removal:** Assert all `/kuro/*` endpoints return 404
3. **Test field removal:** Assert `KuroUser.roles` and `KuroUser.businessgroups` fields are gone
4. **Test table drop:** Assert `users_accesslevel` and `users_switchgroupmodel` tables are dropped
5. **Test RBAC still works:** Permission checks pass without adapter layer

**Completion Gate:**
- [ ] Adapter layer removed
- [ ] Legacy endpoints removed (all return 404)
- [ ] Legacy fields dropped from models
- [ ] Legacy tables dropped from DB
- [ ] Frontend updated to new response shapes
- [ ] No regression in RBAC functionality
- [ ] Files committed

---

## Phase 9: Final Verification — Legacy Removal and Endpoint Compliance

**What:** Automated test suite confirming (a) all legacy code elements are removed, (b) all existing endpoints match target spec contracts. This is the final gate before the migration is considered complete.

**Dependencies:** Phase 8 (Legacy Cleanup complete)

**Files to Create/Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_legacy_removal.py` | Verify all legacy elements are gone |
| Create | `tests/test_endpoint_compliance.py` | Verify all endpoints match spec |
| Create | `tests/test_rbac_integrity.py` | Verify RBAC cascading without adapter |
| Create | `tests/conftest.py` | Shared fixtures for verification tests |
| Create | `tests/fixtures/spec_endpoints.json` | Target spec endpoint definitions |

**Steps:**

### Step 1: Legacy Removal Tests (`test_legacy_removal.py`)

```python
# Test 1: Adapter layer files are deleted
def test_rbac_mapping_file_removed():
    assert not os.path.exists('users/rbac_mapping.py'), "Adapter layer still exists"

# Test 2: No imports of adapter layer remain in codebase
def test_no_adapter_imports():
    result = subprocess.run(['grep', '-r', 'rbac_mapping', 'users/', 'backend/', 'domains/'], capture_output=True, text=True)
    assert result.stdout.strip() == '', f"Adapter imports still present: {result.stdout}"

# Test 3: Legacy resolve_access_levels() wrapper is removed
def test_resolve_access_levels_removed():
    with open('backend/utils.py') as f:
        content = f.read()
    assert 'resolve_access_levels' not in content, "Legacy wrapper still present"

# Test 4: Legacy endpoints return 404
@pytest.mark.parametrize("path", [
    "/kuro/user",
    "/kuro/user/testuser",
    "/kuro/accesslevel/testuser",
    "/kuro/switchgroup",
    "/kuro/businessgroups",
    "/cafe/sessions/start",
    "/tournaments/tourneyregister",
])
def test_legacy_endpoints_removed(path):
    response = client.get(f"/api/v1{path}")
    assert response.status_code == 404, f"Legacy endpoint {path} still active"

# Test 5: Legacy model fields are removed
def test_kurouser_legacy_fields_removed():
    from users.models import CustomUser
    assert not hasattr(CustomUser, 'roles'), "KuroUser.roles field still exists"
    assert not hasattr(CustomUser, 'businessgroups'), "KuroUser.businessgroups field still exists"

# Test 6: Legacy DB tables are dropped
def test_legacy_tables_dropped():
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('users_accesslevel', 'users_switchgroupmodel')
        """)
        rows = cursor.fetchall()
        assert len(rows) == 0, f"Legacy tables still exist: {[r[0] for r in rows]}"

# Test 7: CafeUser projection table is dropped
def test_cafe_user_table_dropped():
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'caf_platform_users'
        """)
        rows = cursor.fetchall()
        assert len(rows) == 0, "CafeUser projection table still exists"

# Test 8: No references to Accesslevel model remain
def test_no_accesslevel_references():
    result = subprocess.run(['grep', '-r', 'Accesslevel', 'users/', 'backend/', 'domains/'], capture_output=True, text=True)
    # Allow references in migrations (historical) and test files
    lines = [l for l in result.stdout.split('\n') if l and '/migrations/' not in l and '/tests/' not in l and '.pyc' not in l]
    assert len(lines) == 0, f"Accesslevel references remain: {lines}"

# Test 9: No references to Switchgroupmodel remain
def test_no_switchgroupmodel_references():
    result = subprocess.run(['grep', '-r', 'Switchgroupmodel', 'users/', 'backend/', 'domains/'], capture_output=True, text=True)
    lines = [l for l in result.stdout.split('\n') if l and '/migrations/' not in l and '/tests/' not in l and '.pyc' not in l]
    assert len(lines) == 0, f"Switchgroupmodel references remain: {lines}"

# Test 10: has_*_access() calls replaced with resolve_permission()
def test_legacy_access_helpers_replaced():
    result = subprocess.run(['grep', '-r', 'has_.*_access', 'backend/', 'domains/'], capture_output=True, text=True)
    lines = [l for l in result.stdout.split('\n') if l and '/migrations/' not in l and '/tests/' not in l and '.pyc' not in l]
    assert len(lines) == 0, f"Legacy has_*_access() calls remain: {lines}"
```

### Step 2: Endpoint Compliance Tests (`test_endpoint_compliance.py`)

```python
# Load target spec endpoint definitions from fixtures
SPEC_ENDPOINTS = json.load(open('tests/fixtures/spec_endpoints.json'))

# Test 1: All spec endpoints exist and respond
@pytest.mark.parametrize("method,path,expected_status", [
    ("POST", "/auth/login", 200),
    ("POST", "/auth/otp/send", 200),
    ("POST", "/auth/refresh", 200),
    ("POST", "/auth/logout", 200),
    ("GET", "/users/me", 200),
    ("GET", "/users/lookup", 200),  # with ?phone= param
    ("POST", "/users/identity", 201),
    ("GET", "/tenant/accessible", 200),
    ("POST", "/tenant/switch", 200),
    ("GET", "/tenant/current", 200),
    ("GET", "/rbac/roles", 200),
    ("POST", "/rbac/roles", 201),
    ("GET", "/rbac/user-roles", 200),
    ("POST", "/rbac/user-roles", 201),
    ("GET", "/rbac/user-permissions", 200),
    ("GET", "/cafe/sessions", 200),
    ("POST", "/cafe/sessions", 201),
    ("GET", "/cafe/stations", 200),
    ("GET", "/cafe/wallet", 200),
    ("POST", "/cafe/wallet/topup", 201),
    ("GET", "/cafe-fnb/menu", 200),
    ("POST", "/cafe-fnb/orders", 201),
])
def test_spec_endpoint_exists(method, path, expected_status, authenticated_client):
    """Every endpoint in the target spec must exist and respond with expected status."""
    if method == "GET":
        response = authenticated_client.get(f"/api/v1{path}")
    elif method == "POST":
        response = authenticated_client.post(f"/api/v1{path}", {}, format='json')
    assert response.status_code == expected_status, \
        f"{method} {path} returned {response.status_code}, expected {expected_status}"

# Test 2: Login response matches target envelope
def test_login_response_shape(authenticated_client):
    response = authenticated_client.post("/api/v1/auth/login", {
        "phone": "+919876543210",
        "password": "test_password"
    })
    data = response.json()
    assert "status" in data, "Missing 'status' field"
    assert "data" in data, "Missing 'data' field"
    user_data = data["data"]
    assert "identity_id" in user_data, "Missing 'identity_id' in login response"
    assert user_data["identity_id"].startswith("ID"), f"identity_id format wrong: {user_data['identity_id']}"
    assert "roles" in user_data, "Missing 'roles' in login response"
    assert "permissions" in user_data, "Missing 'permissions' in login response"
    assert "phone" in user_data, "Missing 'phone' in login response"
    assert user_data["phone"].startswith("+"), "Phone not E.164 normalized"

# Test 3: /users/me response matches target envelope
def test_users_me_response_shape(authenticated_client):
    response = authenticated_client.get("/api/v1/users/me")
    data = response.json()
    user_data = data.get("data", data)  # handle both envelope and direct
    assert "identity_id" in user_data, "Missing 'identity_id'"
    assert "roles" in user_data, "Missing 'roles'"
    assert "permissions" in user_data, "Missing 'permissions'"

# Test 4: Error responses use standardized envelope
def test_error_response_shape(client):
    response = client.get("/api/v1/users/me")  # unauthenticated
    data = response.json()
    # Should be either DRF error or standardized envelope
    assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

# Test 5: Pagination matches spec format
def test_pagination_format(authenticated_client):
    response = authenticated_client.get("/api/v1/cafe/sessions?page=1&per_page=10")
    data = response.json()
    if "pagination" in data:
        pagination = data["pagination"]
        assert "page" in pagination, "Missing 'page' in pagination"
        assert "per_page" in pagination, "Missing 'per_page' in pagination"
        assert "total_items" in pagination, "Missing 'total_items' in pagination"
        assert "total_pages" in pagination, "Missing 'total_pages' in pagination"
    # If pagination not yet implemented (Phase 7), skip with warning
    else:
        pytest.warn(UserWarning("Pagination not yet standardized — Phase 7 pending"))

# Test 6: All cafe sessions use identity FK (not CustomUser)
def test_cafe_sessions_use_identity_fk():
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM caf_platform_sessions s
            LEFT JOIN users_identity i ON s.started_by = i.identity_id
            WHERE s.started_by != '' AND i.identity_id IS NULL
        """)
        orphaned = cursor.fetchone()[0]
        assert orphaned == 0, f"{orphaned} sessions reference non-existent identities"

# Test 7: All wallets use identity FK (not CustomUser)
def test_wallets_use_identity_fk():
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM caf_platform_wallets w
            LEFT JOIN users_identity i ON w.identity_id = i.identity_id
            WHERE i.identity_id IS NULL
        """)
        orphaned = cursor.fetchone()[0]
        assert orphaned == 0, f"{orphaned} wallets reference non-existent identities"

# Test 8: RBAC cascading works without adapter layer
def test_rbac_cascading_without_adapter():
    """Verify resolve_permission() works independently of adapter layer."""
    from users.permissions import resolve_permission
    # This should not import rbac_mapping
    import users.permissions as perms_module
    source = inspect.getsource(perms_module)
    assert 'rbac_mapping' not in source, "RBAC module still imports adapter layer"
```

### Step 3: RBAC Integrity Tests (`test_rbac_integrity.py`)

```python
# Test 1: Permission resolution cascades correctly
def test_permission_cascade():
    from users.permissions import resolve_permission, build_permissions_object
    # Create a user with division-level role
    # Assert: division perm > BG-wide perm > global perm
    # Assert: max-level wins

# Test 2: Role assignment works end-to-end
def test_role_assignment_flow():
    # Create role → assign to user → verify user has role permissions
    # Assert: permissions derived from role are correct

# Test 3: Branch-level permissions are respected
def test_branch_level_permissions():
    # Assign role with branch restriction
    # Assert: user can only access resources in assigned branches

# Test 4: Permission revocation is immediate
def test_permission_revocation():
    # Assign permission → revoke → assert immediately denied
    # No caching that delays revocation
```

### Step 4: Spec Endpoint Fixture (`spec_endpoints.json`)

```json
{
  "auth": {
    "endpoints": [
      {"method": "POST", "path": "/auth/login", "auth": false, "expected_status": 200},
      {"method": "POST", "path": "/auth/otp/send", "auth": false, "expected_status": 200},
      {"method": "POST", "path": "/auth/otp/verify", "auth": false, "expected_status": 200},
      {"method": "POST", "path": "/auth/refresh", "auth": false, "expected_status": 200},
      {"method": "POST", "path": "/auth/logout", "auth": true, "expected_status": 200}
    ]
  },
  "users": {
    "endpoints": [
      {"method": "GET", "path": "/users/me", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/users/lookup", "auth": true, "params": {"phone": "+91..."}, "expected_status": 200},
      {"method": "POST", "path": "/users/identity", "auth": true, "expected_status": 201},
      {"method": "PATCH", "path": "/users/identity/{id}", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/users/{id}", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/users/{id}/employee", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/users/{id}/customer", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/users/{id}/player", "auth": true, "expected_status": 200}
    ]
  },
  "tenant": {
    "endpoints": [
      {"method": "GET", "path": "/tenant/accessible", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/tenant/switch", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/tenant/current", "auth": true, "expected_status": 200}
    ]
  },
  "rbac": {
    "endpoints": [
      {"method": "GET", "path": "/rbac/roles", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/rbac/roles", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/rbac/user-roles", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/rbac/user-roles", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/rbac/user-permissions", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/rbac/user-permissions", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/rbac/user-access", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/rbac/permissions", "auth": true, "expected_status": 200}
    ]
  },
  "cafe": {
    "endpoints": [
      {"method": "GET", "path": "/cafe/sessions", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/cafe/sessions", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/cafe/sessions/{id}", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/cafe/sessions/{id}/end", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/cafe/stations", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/cafe/stations/{id}/command", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/cafe/wallet", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/cafe/wallet/topup", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/cafe/wallet/transactions", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/cafe/games", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/cafe/price-plans", "auth": true, "expected_status": 200},
      {"method": "GET", "path": "/cafe/member-plans", "auth": true, "expected_status": 200}
    ]
  },
  "cafe_fnb": {
    "endpoints": [
      {"method": "GET", "path": "/cafe-fnb/menu", "auth": true, "expected_status": 200},
      {"method": "POST", "path": "/cafe-fnb/orders", "auth": true, "expected_status": 201},
      {"method": "GET", "path": "/cafe-fnb/orders/{id}", "auth": true, "expected_status": 200}
    ]
  },
  "legacy_removed": {
    "endpoints": [
      {"method": "GET", "path": "/kuro/user", "expected_status": 404},
      {"method": "GET", "path": "/kuro/user/{userid}", "expected_status": 404},
      {"method": "GET", "path": "/kuro/accesslevel/{userid}", "expected_status": 404},
      {"method": "POST", "path": "/kuro/switchgroup", "expected_status": 404},
      {"method": "GET", "path": "/kuro/businessgroups", "expected_status": 404},
      {"method": "POST", "path": "/cafe/sessions/start", "expected_status": 404},
      {"method": "GET", "path": "/tournaments/tourneyregister", "expected_status": 404}
    ]
  }
}
```

**Tests:**

1. **Legacy file removal:** Assert `rbac_mapping.py` deleted, no imports remain
2. **Legacy endpoint removal:** Assert all `/kuro/*` endpoints return 404
3. **Legacy field removal:** Assert `KuroUser.roles`/`businessgroups` fields gone
4. **Legacy table removal:** Assert `users_accesslevel`/`users_switchgroupmodel` dropped
5. **Spec endpoint existence:** All spec endpoints respond with expected status
6. **Login response shape:** Correct envelope with `identity_id`, `roles[]`, `permissions[]`
7. **Pagination format:** Matches spec (`total_items`, `total_pages`)
8. **RBAC without adapter:** `resolve_permission()` works independently
9. **Cafe FK integrity:** All cafe tables reference valid `identity_id`
10. **Wallet FK integrity:** All wallets reference valid `identity_id`

**Completion Gate (FINAL — migration complete only if all pass):**

- [ ] All 10 legacy removal tests pass
- [ ] All spec endpoint compliance tests pass
- [ ] Login response matches target envelope exactly
- [ ] RBAC cascading works without adapter layer
- [ ] No orphaned FK references in cafe/orders tables
- [ ] Full test suite passes (no regression)
- [ ] Files committed
- [ ] Migration declared complete

---

## Success Criteria (Overall)

- [ ] Phase 1: M1 identity tables created, populated, validated
- [ ] Phase 2: Cafe schema aligned with identity FKs
- [ ] Phase 3: MongoDB field rename complete (31 collections)
- [ ] Phase 4: All 6 missing identity endpoints implemented
- [ ] Phase 5: Orders migrated to PostgreSQL (7 tables, financial reconciliation)
- [ ] Phase 6: E-commerce domain functional (17 endpoints, Cashfree integration)
- [ ] Phase 7: Response envelope standardized (errors, pagination, filters)
- [ ] Phase 8: All legacy code removed (adapter, endpoints, fields, tables)
- [ ] Phase 9: Final verification suite passes (legacy removal + endpoint compliance)
- [ ] Frontend (`kteam-fe-chief`) updated to new response shapes
- [ ] Zero regression in existing functionality
- [ ] All migrations applied cleanly on fresh database

---

## Caveats & Uncertainty

1. **M1 phone dedup collisions:** Multiple MongoDB sources may have the same phone number with different data. The migration command must handle collisions (merge strategy: take most recent, flag for manual review). **Risk:** Data loss if merge strategy is incorrect.

2. **M3 zero-downtime requirement:** Dual-read middleware adds latency during transition period. Monitor query performance during rename. **Risk:** Performance degradation if dual-read is not optimized.

3. **Frontend coordination:** Login response shape change requires frontend update. Coordinate with frontend team before deploying. **Risk:** Frontend breakage if deployed without frontend update.

4. **M4 financial data integrity:** Orders contain financial data. Any discrepancy in migration is unacceptable. **Risk:** Financial data loss or corruption.

5. **Adapter layer call sites (~520):** Replacing `has_*_access()` calls requires careful review. Some may have custom logic not captured by RBAC. **Risk:** Permission regression if custom logic is lost.

6. **MongoDB collection count (31):** Exact list of collections to rename not yet enumerated. May be more or fewer. **Risk:** Incomplete rename if collection list is inaccurate.

---

## Notes for Executing Agent

- **Read the full Kung_OS spec directory** before starting any phase. The spec is the single source of truth.
- **Each phase is independently executable** by a subagent. Use the serialized phase docs for delegation.
- **Phase 9 is the final gate.** Do not declare the migration complete until Phase 9 passes.
- **Commit after each phase** with a descriptive message (e.g., `feat: M1 identity consolidation — 9 tables, 7 sources migrated`).
- **Run the full test suite after each phase** to catch regressions early.
- **Coordinate with frontend team** before Phase 8 (legacy cleanup) to ensure frontend is updated.
