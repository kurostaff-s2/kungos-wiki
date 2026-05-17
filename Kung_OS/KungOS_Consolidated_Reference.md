# KungOS — Consolidated Reference

**Date:** 2026-05-16
**Sources merged:** `KUNGOS_INTEGRATION_PLAN.md` (2026-05-13), `KungOS_Identity_Design.md` (2026-05-14), `kungos_v2_db.md` (2026-04-29)
**Resolution rule:** When sources conflict, priority is: (1) verified ground truth from live DB/code, (2) latest council-locked decisions, (3) latest document date
**Status:** Single source of truth for the KungOS program

> Replaces `KUNGOS_INTEGRATION_PLAN.md`, `KungOS_Identity_Design.md`, and `kungos_v2_db.md` as the working reference. `KungOS_v2.md` remains the master plan (architecture, phases, cutover) but its progress log is stale.

---

## Table of Contents

1. [Verified Ground Truth](#1-verified-ground-truth)
2. [Tenant Hierarchy & Multi-Tenancy](#2-tenant-hierarchy--multi-tenancy)
3. [RBAC System](#3-rbac-system)
4. [Identity Layer](#4-identity-layer)
5. [Cafe Platform](#5-cafe-platform)
6. [Orders System](#6-orders-system)
7. [MongoDB State](#7-mongodb-state)
8. [Platform Primitives](#8-platform-primitives)
9. [API Routing](#9-api-routing)
10. [Security Issues](#10-security-issues)
11. [Atomic Implementation Plan](#11-atomic-implementation-plan)
12. [Risk Register](#12-risk-register)
13. [Open Questions](#13-open-questions)

---

## 1. Verified Ground Truth

### Two Separate Django Projects

| | **KungOS (kteam-dj-chief)** | **Kuro Gaming (kuro-gaming-dj-backend)** |
|---|---|---|
| **Path** | `~/Coding-Projects/kteam-dj-chief/` | `~/Coding-Projects/kuro-gaming-dj-backend/` |
| **Django** | 5.x | 4.1.13 (EOL) |
| **Auth** | `rest_framework_simplejwt` + `CookieJWTAuthentication` | `knox` (legacy token) + custom `ModelBackend` |
| **Structure** | Domain-first (`domains/*`) + platform primitives (`plat/*`) | Flat apps (`accounts`, `orders`, `products`, `games`, `payment`, `kuroadmin`, `users`) |
| **Multi-tenant** | `tenant/`, `tenant_api/`, `plat/tenant/` | None |
| **Observability** | `plat/observability/` (CorrelationID, TenantContext middleware) | None |
| **Outbox/Events** | `plat/outbox/`, `plat/events/` | None |
| **API Schema** | `drf_spectacular` | None |
| **Search** | `meilisearch` configured | None |
| **Channels** | `channels` (ASGI/WebSockets) | None |
| **DB** | PostgreSQL + MongoDB (PyMongo direct) | PostgreSQL + MongoDB (djongo deprecated bridge) |
| **Deployment** | `docker-compose.yml` (Mongo + MeiliSearch), systemd services | Manual, no docker-compose |

### KungOS INSTALLED_APPS (verified)

```python
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    # Third party
    'rest_framework', 'rest_framework_simplejwt', 'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular', 'corsheaders', 'dbbackup', 'storages',
    # User-developed (legacy)
    'teams', 'kungos_admin', 'plat', 'careers', 'users', 'tenant', 'tenant_api',
    'rebellion',
    # Domain modules (ViewSet-based API)
    'domains.accounts', 'domains.orders', 'domains.products', 'domains.vendors',
    'domains.eshop', 'domains.teams', 'domains.cafe_arcade', 'domains.cafe_fnb', 'domains.tournaments',
    'domains.search', 'domains.shared',
    # Channels
    'channels',
]
```

### KungOS MIDDLEWARE (verified)

```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Platform observability
    'plat.observability.middleware.CorrelationIDMiddleware',
    'plat.observability.middleware.TenantContextMiddleware',
]
```

### KungOS REST_FRAMEWORK (verified)

```python
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'users.cookie_auth.CookieJWTAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
    'DEFAULT_THROTTLE_CLASSES': ['AnonRateThrottle', 'UserRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute', 'user': '1000/minute', 'login': '10000/minute',
        'otp': '5/minute', 'sms': '5/minute', 'register': '10/minute',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

### Domain Implementation Status (verified)

| Domain | models.py | viewsets.py | urls.py | Notes |
|--------|-----------|-------------|---------|-------|
| accounts | ❌ | ✅ | ✅ | MongoDB collections (inward/outward invoices) — **FINANCE** |
| orders | ❌ | ✅ | ✅ | Estimates, TP orders, In-store orders, PO — **BACK-OFFICE** |
| products | ❌ | ✅ | ✅ | Asset catalog — **INVENTORY** + depreciation.py |
| vendors | ❌ | ✅ | ✅ | |
| teams | ❌ | ✅ | ✅ | |
| search | ❌ | ✅ | ✅ | MeiliSearch operations |
| shared | ❌ | ✅ | ✅ | Cross-cutting utilities |
| eshop | ❌ | ❌ | ❌ | Empty shell — target for e-commerce models (Phase 1) |
| cafe_arcade | ✅ | ✅ | ✅ | 14 models + views + gamers_views + legacy_views |
| cafe_fnb | ❌ | ❌ | ✅ | Gateway domain: OrderGateway + views + serializers. No PG models. |
| tournaments | ❌ | ✅ | ✅ | Tournaments, players, teams, tourneyregister |

**Key finding:** No `models.py` in any domain except `cafe_arcade`. Models live in `users/models.py`, `tenant/models.py`, and MongoDB collections accessed directly via PyMongo.

### Kuro Gaming Models (verified)

| App | models.py | Content |
|-----|-----------|---------|
| accounts | ✅ | Cart, Wishlist, Addresslist (59 lines) |
| orders | ✅ | Orders (30+ fields), OrderItems |
| products | ❌ | Empty stub — data in MongoDB |
| games | ❌ | Empty stub |
| payment | ❌ | Empty stub |
| users | ✅ | CustomUser (AbstractBaseUser) |
| kuroadmin | ✅ | Admin models |

---

## 2. Tenant Hierarchy & Multi-Tenancy

### 2.1 Tenant Schema (PostgreSQL) — Verified 2026-04-29

**Replaces legacy Brand/Entity/EntityBranch/BgEntityBranch** (all deleted in migration 0007).

| Table | PK | FKs | Notes |
|---|---|---|---|
| `tenant_business_groups` | `bg_code` (VARCHAR(10)) | — | Legal entity. Code = first 4 letters + seq (e.g. `KURO0001`). Fields: `bg_label`, `legal_name`, `tax_gst`, `tax_pan`, `db_name`, `licence_type`, `licence_cert` |
| `tenant_divisions` | `div_code` (VARCHAR(20)) | `bg` → tenant_business_groups.bg_code | Operational division. Code = `bg_code_XXX` (e.g. `KURO0001_001`). Fields: `div_label`, `brand_code`, `brand_name`, `type`, `dj_apps`, `ent_status_code`, `ent_op_code`, `logo_url` |
| `tenant_branches` | `branch_code` (VARCHAR(30)) | `division` → tenant_divisions.div_code | Physical outlet. Code = `div_code_XXX` (e.g. `KURO0001_001_001`). Fields: `branch_label`, `branch_name`, `incharge_userid`, `pincode`, `inv_series_code`, `primary_bk` → tenant_bank_accounts |
| `tenant_bank_accounts` | `bank_code` (VARCHAR(20)) | `bg` → tenant_business_groups.bg_code | Bank account per BG. Code = `bg_code_BK_XXX`. Fields: `bk_label`, `bank_name`, `account_holder_name`, `account_type` |
| `tenant_division_addresses` | `address_code` (VARCHAR(30)) | `division` → tenant_divisions.div_code | Bill/shipping addresses per division. Code = `div_code_TYPE_XXX`. Fields: `address_type`, `label`, `address_line1/2`, `city`, `state`, `country`, `pincode`, `phone_no`, `is_default` |

**Current data:**
- 2 BusinessGroups: `KURO0001` (KURO CADENCE LLP), `DUNE0003` (DUNE LABS LLP)
- 4 Divisions: `KURO0001_001` (Kuro Gaming), `_002` (Rebellion), `_003` (RenderEdge), `DUNE0003_001` (Rebellion)
- 6 Branches across all divisions

### 2.2 Tenant Schema (MongoDB)

All 31 MongoDB collections have `(bgcode, division, branch_code)` fields on 100% of documents. All 31 have `(bgcode, division)` compound indexes.

**Naming conflict (Phase 5.7):** MongoDB uses `bgcode`, `division`, `branch_code`. Canonical naming locked to `bg_code`, `div_code`, `branch_code`. DB migration required.

### 2.3 Platform Tenant Module (`plat/tenant/`)

| File | Purpose |
|------|---------|
| `collection.py` | `TenantCollection` wrapper — adds `bg_code` filter to MongoDB queries |
| `config.py` | Tenant config loading |
| `exceptions.py` | Tenant-related exceptions |
| `rls.py` | Row-level security utilities (NOT yet enabled on PostgreSQL tables) |
| `verify.py` | Tenant verification |

### 2.4 PostgreSQL RLS Status

**❌ NOT IMPLEMENTED.** Zero tables have RLS enabled. Tenant isolation relies entirely on application-level filtering. Deferred to Phase 4.

---

## 3. RBAC System

### 3.1 Normalized RBAC Tables (PostgreSQL) — Verified 2026-04-29

Replaces legacy `users_accesslevel` (55 columns, 40+ varchar permission fields).

| Table | PK | Notes |
|---|---|---|
| `rbac_permissions` | `perm_code` (VARCHAR(50)) | Permission registry. 35 perms across modules: invoices, orders, products, inventory, sales, payments, financials, analytics, data, hr, admin |
| `rbac_roles` | `role_code` (VARCHAR(30)) | User-created roles. `parent_role` → self (nullable). `is_system` flag reserved. Single-level inheritance. |
| `rbac_role_permissions` | `(role_code, perm_code)` composite | Permission level: 0=Revoked, 1=View, 2=Edit, 3=Supervisor |
| `rbac_user_roles` | `id` (BIGSERIAL) | Role assignment scoped by `bg_code` + `division` (nullable = BG-wide). UNIQUE(userid, role, bg_code, division) |
| `rbac_user_role_branches` | `(user_role_id, branch_code)` composite | Branch-level scoping |
| `rbac_user_permissions` | `(userid, perm_code, bg_code, division)` composite | Direct permission overrides. Fields: `level`, `reason`, `expires_at`, `granted_by` |

**Resolution engine:** `users/permissions.py` — `resolve_permission()` cascades: exact division → BG-wide → global. Max-level wins. Roles are always additive.

### 3.2 Legacy `users_accesslevel` — Current State

55 columns, all 50+ permission fields are `varchar` (strings, NOT integers). Still in use. Planned additions (NOT YET IMPLEMENTED): `kungosadmin`, `cafedashboard`, `station_management`, `wallet_management`, `wallet_recharge`, `pricing_management`, `cafe_dashboard`, `cafe_sessions`, `cafe_payments`.

**Migration target:** Phase 6 — deprecate `Accesslevel`, all permissions use normalized RBAC.

---

## 4. Identity Layer

### 4.1 Current State (Anti-Patterns)

KungOS manages identity across **7 user types in 8 storage locations**:

| Type | Count | Storage | Anti-Pattern |
|---|---|---|---|
| Employees | 31 | `employee_attendance` (Mongo) + `KuroUser` (PG) | Split across Mongo + PG |
| Players | 59 unique (117 docs) | `players` (Mongo) | 50% duplication |
| Customers (registered) | 1,979 | `reb_users` (Mongo) + `misc` (Mongo, 100% dup) | 100% duplicate |
| Customers (unregistered) | 727 | Embedded in `orders.user.phone` (Mongo) | No canonical record |
| Service Requestors | 1,328 | `serviceRequest` (Mongo) | 2.3% overlap with customers |
| Teams | 14 | `teams` (Mongo) | Mixed with players |
| Vendors | 409 | `vendors` (Mongo) | No relationship to orders |
| Auth Users | ~200 | `users_customuser` + `users_kurouser` (PG) | Two-table split, 42 fields in KuroUser |

**Critical overlaps:**
- `reb_users` ↔ `misc`: 100% duplicate
- `orders.user.phone` ↔ `reb_users`: 73% match
- `serviceRequest.phone` ↔ `reb_users`: 2.3% match
- `players.mobile` ↔ `reb_users.phone`: 20% match

### 4.2 Current PostgreSQL User Tables (verified)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `users_customuser` | 16 | `userid` | CustomUser model, `USERNAME_FIELD='phone'` |
| `users_kurouser` | 42 | `id` | Extended user profile — 6 new fields added |
| `users_user_tenant_context` | 9 | `id` | Field is `scope` (NOT `scope_type`) |
| `users_phonemodel` | 4 | `id` | OTP verification |
| `users_switchgroupmodel` | 4 | `id` | BG switching tokens |
| `users_common_counters` | 3 | `id` | Legacy counter tracking |

**Anti-pattern:** `CustomUser` (auth, 16 cols) + `KuroUser` (profile, 42 cols) = split identity. `KuroUser.businessgroups` is JSON (no FK integrity). `KuroUser.roles` is JSON (bypasses RBAC).

### 4.3 Target Architecture (Pre-Phase 4 — Identity Design)

**Design:** One core identity table + type-specific extension tables. PostgreSQL as identity store, MongoDB for operational data.

```
users_identity (core — 1 row per person)
├── identity_id (PK, sequential: ID000001)
├── phone (UNIQUE, normalized E.164: +91XXXXXXXXXX)
├── name, email
├── bg_code, div_code, branch_code (tenant context)
├── status (active/suspended/inactive)
├── phone_verified, idproof_type, idproof_number
├── user → CustomUser (OneToOne, nullable)
│
├── users_employee (extension — employees only)
├── users_customer (extension — customers, merges reb_users + serviceRequest)
├── users_player (extension — players, replaces Mongo players collection)
│
└── users_organization (separate — teams, vendors)
    ├── users_vendor_profile (extension)
    └── users_team_profile (extension)
```

**Key design decisions:**
- `identity_id` is the PK — not `phone` (phones change), not `CustomUser.userid` (format varies)
- `phone` is tenant-scoped unique (`bg_code` + `phone`)
- No `identity_type` column — roles derived from which extension tables have rows
- `CustomUser` preserved as Django auth model — linked via nullable OneToOne
- Phone-only identities (unregistered customers, walk-ins) don't have a `CustomUser` record
- Organizations (teams, vendors) are separate from people — different query patterns, growth rates, schemas

### 4.4 Migration Strategy (Identity)

```
python manage.py migrate_identity --source=<mongo_uri> --validate

Step 1: Read & normalize all sources (phone → E.164)
Step 2: Dedup by normalized phone (fuzzy name match >85% = auto-merge)
Step 3: Flag conflicts for manual review (dedup_review table)
Step 4: Write to new tables (single transaction per batch)
Step 5: Backfill CafeWalkin.identity FK, drop phone uniqueness
Step 6: Validate (row counts, phone normalization, FK integrity, zero orphans)
```

**Legacy collection disposition:**
- `reb_users` → `users_identity` + `users_customer` (DEPRECATED)
- `misc` → SKIP (100% duplicate of reb_users)
- `players` → `users_identity` + `users_player` (DEPRECATED)
- `vendors` → `users_organization` + `users_vendor_profile` (DEPRECATED)
- `teams` → `users_organization` + `users_team_profile` (DEPRECATED)
- `employee_attendance` → stays in Mongo (operational data), references `identity_id`
- `serviceRequest` → stays in Mongo (operational data), references `identity_id`

### 4.5 Cafe Platform Identity Alignment

**Current problems:**
- `CafeWalkin.phone` is `unique=True` — conflicts with `CustomUser.phone` uniqueness
- `CafeUser` is a thin projection of `CustomUser` — redundant data
- `CafeWallet.customer` FK → `CustomUser` — but walk-ins have wallets too

**Resolution (Phase 4):**
- `CafeWalkin` links to `users_identity` via FK (phone uniqueness dropped)
- `CafeUser` replaced by `users_identity`
- Wallet stays on `CustomUser` (auth-bound, not identity-bound)

---

## 5. Cafe Platform

### 5.1 PostgreSQL Tables — 14 Tables (verified)

All cafe data in PostgreSQL (NOT MongoDB). ACID billing, relational integrity.

| Table | Cols | PK | Notes |
|---|---|---|---|
| `caf_platform_cafes` | 12 | `id` | Cafe registry. FKs: bg_code, div_code, branch_code |
| `caf_platform_stations` | 14 | `id` | UNIQUE `(cafe_id, code)`. Denormalized tenant fields from Cafe |
| `caf_platform_sessions` | 17 | `id` | 4 FKs: cafe_id, game_id, price_plan_id, station_id |
| `caf_platform_session_leases` | 8 | `id` | Lease versioning |
| `caf_platform_station_commands` | 9 | `id` | Station remote control |
| `caf_platform_station_events` | 8 | `id` | Station event log |
| `caf_platform_wallets` | 11 | `id` | **CONFLICT SEE §5.2** |
| `caf_platform_wallet_transactions` | 9 | `id` | FK wallet_id, FK created_by_id→CustomUser |
| `caf_platform_price_plans` | 15 | `id` | FK cafe_id; jsonb config |
| `caf_platform_member_plans` | 9 | `id` | UNIQUE plan_id, tier; seeded: edge/titan/s |
| `caf_platform_games` | 13 | `id` | Game catalog; FK cafe_id |
| `caf_platform_users` | 8-10 | `id` | **CONFLICT SEE §5.3** |
| `caf_platform_walkins` | 5-10 | `id` | **CONFLICT SEE §5.4** |
| `caf_platform_auth_tokens` | 7 | `id` | Auth token storage |

### 5.2 Wallet Schema Conflict Resolution

**`kungos_v2_db.md` documents TWO conflicting wallet definitions:**

**Definition A (first occurrence, §1.2):**
```python
# caf_platform_wallets (11 cols)
customer_id → users_customuser.userid (FK, UNIQUE)
balance (no default of 0)
membership_tier, points_earned, total_spent, total_recharged, status
```

**Definition B (second occurrence, §1.2 later):**
```python
# caf_platform_wallets (8 cols)
walkin_id → caf_platform_walkins.walkin_id (nullable FK)
user_id → caf_platform_users.user_id (nullable FK)
CHECK: exactly one of walkin_id or user_id IS NOT NULL
Partial UNIQUE: (walkin_id, bg_code) WHERE walkin_id IS NOT NULL
Partial UNIQUE: (user_id, bg_code) WHERE user_id IS NOT NULL
```

**Resolution:** Definition B is the **current live schema** (polymorphic owner via walkin/user). Definition A was the earlier design. The CHECK constraint enforces single ownership. Tenant resolution: `wallet → walkin.bg_code` OR `wallet → user.bg_code`.

**Identity Design alignment (Phase 4):** Wallet should link to `users_identity` instead of polymorphic walkin/user. But this is deferred — current polymorphic design works.

### 5.3 Cafe Users Schema Conflict Resolution

**`kungos_v2_db.md` documents TWO conflicting users definitions:**

**Definition A (first occurrence):**
```python
# caf_platform_users (8 cols)
id, user_id (UNIQUE FK→CustomUser.userid), user_type, display_name,
bg_code, div_code, branch_code, status, created_at, updated_at
UNIQUE (user_id, bg_code, div_code, branch_code)
```

**Definition B (second occurrence):**
Same 10 columns, same constraints. No real conflict — Definition B is just the expanded listing of Definition A.

**Identity Design says:** `CafeUser` is a "thin projection" of `CustomUser` — redundant data, update anomalies. Should be replaced by `users_identity` in Phase 4.

### 5.4 Cafe Walkins Schema Conflict Resolution

**`kungos_v2_db.md` documents TWO conflicting walkins definitions:**

**Definition A (first occurrence, §1.2):**
```python
# caf_platform_walkins (5 cols)
id, walkin_id (UNIQUE), primary_phone (NOT UNIQUE), secondary_phones (jsonb),
name, bg_code, div_code, branch_code, created_at, last_visit
UNIQUE (primary_phone, bg_code, div_code, branch_code)
```

**Definition B (implied by identity design):**
```python
# caf_platform_walkins (modified)
identity_id → users_identity.identity_id (FK, NOT NULL)
phone uniqueness DROPPED — phone lives in users_identity only
```

**Resolution:** Definition A is the **current live schema**. Definition B is the **target** after Phase 4 identity migration. Current schema works — phone uniqueness is tenant-scoped (composite with bg/div/branch).

### 5.5 Session Model (verified)

```python
class Session(models.Model):
    food_charges = models.DecimalField(...)  # DEPRECATED: use last_order_id
    last_order_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)  # FK to kgorders.orderid
```

**Migration:** `0003_session_order_ref.py` — added `last_order_id`. `food_charges` NOT dropped yet.

**`session_end()` fix (2026-05-13):**
- Indentation bug fixed — `started_at`/`billed_minutes` inside `transaction.atomic()`
- Two `transaction.atomic()` blocks merged into one
- `food_total` logic: `last_order_id` → 0 (no double-count), else `food_charges` fallback

### 5.6 Cafe-FNB Domain (created 2026-05-13)

```
domains/cafe_fnb/
  gateways.py    # OrderGateway: get(), get_amount_paid(), create(), list_orders()
                 # Resilience: circuit-breaker (5 failures → 30s reset), retry (3x backoff), idempotency
  views.py       # menu, create_order, get_order, list_orders
  serializers.py # OrderCreateRequest, OrderResponse, OrderListResponse, MenuItemSerializer
  urls.py        # /api/v1/cafe-fnb/
  migrations/    # __init__.py only — no PG models
```

**No models.py** — F&B data stays in MongoDB `kgorders` + `stock_register`.

### 5.7 Endpoint Changes

| Before (Planned) | After (Locked) | Status |
|-----------------|----------------|--------|
| `POST /cafe/sessions/<id>/food` | `POST /cafe-fnb/orders/create` | ✅ Implemented |
| `GET /cafe-fnb/orders/<id>` | Lookup by orderid | ✅ Implemented |
| `GET /cafe-fnb/orders` | List with pagination + date filters | ✅ Implemented |
| `GET /cafe-fnb/menu` | Product catalog from stock_register | ✅ Stub |
| `Session.food_charges` accumulation | `Session.last_order_id` reference | ✅ Implemented |
| Food charges in session end | `food_total = 0` when `last_order_id` set | ✅ Implemented |
| Full OrderGateway lookup in session_end | TODO | ⏳ Pending |

---

## 6. Orders System

### 6.1 Planned PostgreSQL Tables (Phase 8)

Replaces 4 MongoDB collections: `estimates` (4,308), `kgorders` (9,162), `tporders` (229), `serviceRequest` (1,625). Total: 15,925 docs.

| Table | Cols | PK | Notes |
|---|---|---|---|
| `orders_core` | 13 | `id` | Shared by all order types. `orderid` (UNIQUE), `order_type` (ENUM), `status` (ENUM), `total_amount`, `customer_id`, `division`, `bg_code`, `billadd` (JSONB), `products` (JSONB), `channel`, `created_at`, `updated_at` |
| `estimate_detail` | 5 | `order_id` | FK → orders_core |
| `in_store_detail` | 9 | `order_id` | FK → orders_core |
| `tp_order_detail` | 7 | `order_id` | FK → orders_core |
| `service_detail` | 5 | `order_id` | FK → orders_core |
| `eshop_detail` | 22 | `order_id` | FK → orders_core |

**Note:** `indentpos` and `indentproduct` stay in MongoDB — procurement documents, no customer/shipping/payment, flexible schema needed.

### 6.2 Identity Design Alignment

`orders_core.customer_id` will reference `users_identity.identity_id` (after Phase 4 identity migration). Currently references `userid` (CustomUser format).

### 6.3 Domain Separation (Council-locked)

- `domains/orders/` — Back-office only (Estimates, TP orders, In-store orders, Purchase orders)
- `domains/eshop/` — E-commerce orders (Cart → Order → Payment flow)
- `domains/cafe_fnb/` — F&B orders (MongoDB `kgorders`, gateway pattern)

---

## 7. MongoDB State

### 7.1 Database

**Name:** `KungOS_Mongo_One` (underscores)  
**MongoDB version:** 8  
**Total:** 31 collections, 68,443 documents, 100% tenant-scoped

### 7.2 Collection Inventory

| Collection | Docs | Notes |
|---|---|---|
| `purchaseorders` | 15,216 | ~99.96% kurogaming |
| `inwardpayments` | 21,026 | ~81% rebellion |
| `estimates` | 4,308 | 100% kurogaming — **→ orders_core + estimate_detail (PG)** |
| `misc` | 5,512 | Mixed division — **100% duplicate of reb_users** |
| `products` | 82 | Retail products |
| `accounts` | 7 | 100% kurogaming |
| `players` | 117 | Esports players — **→ users_player (PG, Phase 4)** |
| `tournaments` | 3 | Esports tournaments |
| `reb_users` | 1,982 | Rebellion users — **→ users_customer (PG, Phase 4)** |
| `kgorders` | 9,162 | In-store orders — **→ orders_core + in_store_detail (PG)** |
| `tporders` | 229 | TP orders — **→ orders_core + tp_order_detail (PG)** |
| `tpbuilds` | 123 | TP builds |
| `serviceRequest` | 1,625 | Service requests — **→ orders_core + service_detail (PG)** |
| `outward` | 754 | Outward documents |
| `outwardInvoices` | 1,165 | Outward invoices |
| `outwardCreditNotes` | 150 | Outward credit notes |
| `paymentVouchers` | 3,459 | Payment vouchers |
| `stock_register` | 194 | Stock register |
| `indentpos` | 247 | Indent positions |
| `indentproduct` | 1,490 | Indent products |
| `employee_attendance` | 966 | Employee attendance — **stays in Mongo (operational), references identity_id** |
| `vendors` | 409 | Vendor records — **→ users_organization + vendor_profile (PG, Phase 4)** |
| `teams` | 14 | Teams — **→ users_organization + team_profile (PG, Phase 4)** |
| `presets` | 6 | Gaming presets |
| `tourneyregister` | 56 | Tournament registrations |
| `bgData` | 1 | BG metadata |
| `inwardCreditNotes` | 106 | Inward credit notes |
| `inwardDebitNotes` | 3 | Inward debit notes |
| `inwardInvoices` | 16 | Inward invoices |
| `outwardDebitNotes` | 13 | Outward debit notes |

### 7.3 Division Distribution

| Division (div_code) | Brand Code | Docs | % |
|---|---|---|---|
| `KURO0001_001` | kurogaming | 15,216 | 22.2% |
| `KURO0001_002` | rebellion | 17,127 | 25.0% |
| `KURO0001_003` | renderedge | 0 | 0% |
| `DUNE0003_001` | rebellion | 36,099 | 52.8% |
| **Total** | — | **68,443** | **100%** |

### 7.4 Gaming Integration Gap

**12/13 gaming collections MISSING from MongoDB** (92%). Only `presets` exists (6 docs). Deferred to Phase 3b.

| # | Collection | Gaming Code Reference | Status |
|---|---|---|---|
| 1 | `prods` | `db['prods']` | ❌ MISSING |
| 2 | `builds` | `db['builds']` | ❌ MISSING |
| 3 | `kgbuilds` | `db['kgbuilds']` | ❌ MISSING |
| 4 | `custombuilds` | `db['custombuilds']` | ❌ MISSING |
| 5 | `components` | `db['components']` | ❌ MISSING |
| 6 | `accessories` | `db['accessories']` | ❌ MISSING |
| 7 | `monitors` | `db['monitors']` | ❌ MISSING |
| 8 | `networking` | `db['networking']` | ❌ MISSING |
| 9 | `external` | `db['external']` | ❌ MISSING |
| 10 | `games` | games app | ❌ MISSING |
| 11 | `kurodata` | `db['kurodata']` | ❌ MISSING |
| 12 | `lists` | `db['lists']` | ❌ MISSING |
| 13 | `presets` | `db['presets']` | ✅ EXISTS |

**Root cause:** Gaming apps not yet merged into `kungos_dj/domains/eshop/`. Separate `products` MongoDB database no longer exists.

### 7.5 MongoDB Field Naming (Phase 5.7)

**Canonical naming locked (2026-05-13):** `bg_code`, `div_code`, `branch_code` (underscored `_code` suffix).

**Current state:** MongoDB uses `bgcode`, `division`, `branch_code`. DB migration required to rename `bgcode` → `bg_code`, `division` → `div_code`.

---

## 8. Platform Primitives

### 8.1 `plat/` Module Inventory (verified 2026-05-13)

All modules exist with real implementation. `plat/` is in `INSTALLED_APPS`. Observability middleware is in `MIDDLEWARE`.

| Module | Files | Status |
|--------|-------|--------|
| `plat/outbox/` | models.py, service.py, worker.py | ✅ Outbox pattern for cross-store consistency |
| `plat/events/` | bus.py, types.py | ✅ Domain event bus (emit/on pattern) |
| `plat/observability/` | context.py, logging.py, middleware.py | ✅ In MIDDLEWARE — CorrelationIDMiddleware, TenantContextMiddleware |
| `plat/tenant/` | collection.py, config.py, exceptions.py, rls.py, verify.py | ✅ Tenant RLS, config, verification |
| `plat/health/` | urls.py, views.py | ✅ Health check endpoints |
| `plat/shared/` | encoding.py, helpers.py, validation.py | ✅ Shared utilities |
| `plat/management/` | commands/seed_tenant_config.py | ✅ Tenant config seeding |

**Note:** `KungOS_v2.md` references `platform/` — the actual directory is `plat/`. `KungOS_v2.md` §"Phase 2 Progress Log" incorrectly marks these as "🟡 Not yet created" — they are implemented and wired.

### 8.2 MongoDB Connection Management

**Singleton pattern:** `get_collection()` uses singleton `get_mongo_client()`. Two leak points patched (2026-05-13): `users/api/viewsets.py:552` (health check) and `backend/views_diagnostic.py:33` (diagnostic view).

**All `MongoClient()` calls outside `management/commands/` route through singleton.**

---

## 9. API Routing

### 9.1 KungOS URL Routing (verified — backend/urls.py)

```
/api/v1/
  accounts/     → domains.accounts.urls
  vendors/      → domains.vendors.urls
  orders/       → domains.orders.urls
  products/     → domains.products.urls
  teams/        → domains.teams.urls
  search/       → domains.search.urls
  shared/       → domains.shared.urls
  users/        → users.urls
  careers/      → careers.urls
  rebellion/    → rebellion.urls
  cafe/         → domains.cafe_arcade.urls
  cafe-fnb/     → domains.cafe_fnb.urls  # Phase 2B — F&B gateway
  admin/        → kungos_admin.urls
  tenant/       → tenant_api.urls

Root-level legacy endpoints (still active, Phase 7 removal):
  /api/v1/bgSwitch, /api/v1/accesslevel, /api/v1/pwdreset, /api/v1/verify
  /api/v1/empprofile, /api/v1/employeesdata, /api/v1/kuro/user, /api/v1/reb/user
  /api/v1/auth/login, /api/v1/auth/kuroregister, /api/v1/auth/rebregister
  /api/v1/auth/refresh, /api/v1/auth/logout
```

### 9.2 Kuro Gaming URL Routing (verified)

```
/             → users.urls
/api/products/ → products.urls
/api/accounts/ → accounts.urls
/api/orders/   → orders.urls
/api/games/    → games.urls
/api/payment/  → payment.urls
/api/kuroadmin/ → kuroadmin.urls
```

---

## 10. Security Issues

### 10.1 Hardcoded AWS Credentials (CRITICAL)

**File:** `kuro/backend/settings.py`
```python
DBBACKUP_STORAGE_OPTIONS = {
    "access_key": "[REDACTED]",
    "secret_key": "uASP3ZGsQPOmHPOPEmW7V6+E8/CQFohb2urbijK2",
    "bucket_name": "kuro-db-backup",
}
```
**Fix:** Replace with env vars. Rotate keys immediately.

### 10.2 Hardcoded MeiliSearch Key

**File:** `kteam-dj-chief/docker-compose.yml`
```yaml
MEILI_MASTER_KEY=aSampleMasterKey
```
**Fix:** Use env var.

### 10.3 Default SECRET_KEY Fallback

**File:** `kuro/backend/settings.py`
```python
SECRET_KEY = env('DJANGO_SECRET_KEY', default='change-me-in-production')
```
**Fix:** Remove default, require env var.

### 10.4 Knox Token Auth (no rotation/refresh)

**File:** `kuro/backend/settings.py` — Tokens never expire, no rotation, no blacklist.
**Fix:** Migrate to SimpleJWT.

### 10.5 PostgreSQL RLS Not Implemented

Zero tables have RLS. Tenant isolation via app-level filtering only. Deferred to Phase 4.

---

## 11. Atomic Implementation Plan

### Phase 0 — Security Hardening (Week 1)

| # | Action | Validation |
|---|--------|-----------|
| 0.1 | Replace hardcoded AWS keys with env vars | `grep -r "[REDACTED]"` → no matches |
| 0.2 | Remove SECRET_KEY default | App fails without env var |
| 0.3 | Replace `knox` with SimpleJWT in Kuro | `pip show djangorestframework-simplejwt` |
| 0.4 | Add `drf_spectacular`, `corsheaders` to Kuro | OpenAPI schema accessible |
| 0.5 | Align Kuro dependencies | `pip install -r requirements.txt` succeeds |
| 0.6 | Add CorrelationID + TenantContext middleware to Kuro | `X-Correlation-ID` header present |
| 0.7 | Add REST_FRAMEWORK config to Kuro | Paginated responses |
| 0.8 | Add MONGO_DB_URI env var to Kuro | MongoDB uses env var |

### Phase 1 — E-Commerce Models: Kuro → `domains/eshop/` (Weeks 2-3)

**Council-locked:** All e-commerce models go to `domains/eshop/`. NOT accounts, orders, or products.

| # | Action | Validation |
|---|--------|-----------|
| 1.1 | Create `Cart`, `Wishlist`, `Addresslist` models with `bg_code` FK | `makemigrations domains.eshop` |
| 1.2 | Create `Order`, `OrderItem` models with `bg_code` FK | `makemigrations domains.eshop` |
| 1.3 | Create serializers for all 5 models | Serializers validate |
| 1.4 | Create viewsets for all 5 models | `GET /api/v1/eshop/cart/` returns 200 |
| 1.5 | Register viewsets on router under `eshop/` prefix | All eshop endpoints accessible |
| 1.6 | Wire `eshop/` into main URL tree | `/api/v1/eshop/` routes active |

**What stays untouched:** `domains/accounts/` (finance), `domains/orders/` (back-office), `domains/products/` (inventory).

### Phase 2 — Gaming Domain Integration (Weeks 4-5)

**2A — Session Model Fix** ✅ DONE 2026-05-13
- `last_order_id` added (migration 0003)
- `session_end()` fixed (indentation bug, merged atomic blocks, food_total logic)
- `food_charges` kept as deprecated fallback (drop in Phase 9)

**2B — Create cafe-fnb/ Domain** ✅ DONE 2026-05-13
- OrderGateway with circuit-breaker, retry, idempotency
- F&B order endpoints functional
- Menu endpoint stub (needs stock_register schema)

**2C — Gaming Domain Audit** (Week 4-5)
- Audit existing models, serializers, seed data, WebSocket consumers
- ⏳ Tests for `session_end()` concurrency — `tests/` is empty
- ⏳ Full OrderGateway lookup in `session_end()` — TODO
- ⏳ WebSocket consumers are stubs — 10 handlers return `ack: True` only

### Phase 3 — Payment Integration (Week 6)

Create `domains/payment/` from Kuro Gaming's payment logic. Models: `PaymentTransaction`, `PaymentMethod`, `Refund`. Link to orders via FK.

### Phase 4 — Auth Unification (Week 7)

| # | Action | Notes |
|---|--------|-------|
| 4.1 | Compare Kuro Gaming's `CustomUser` with KungOS's | Schema alignment |
| 4.2 | Deploy `users_identity` + extension tables | Identity Design target |
| 4.3 | Run `migrate_identity` management command | Import + dedup |
| 4.4 | Backfill CafeWalkin.identity FK, drop phone uniqueness | Cafe alignment |
| 4.5 | Migrate `reb_users`, `players`, `vendors`, `teams` to PG | Legacy Mongo collections deprecated |
| 4.6 | Add Kuro registration endpoints | SimpleJWT auth |
| 4.7 | Verify JWT contains tenant context | `bg_code`, `div_code` in token |

### Phase 5 — MongoDB Consolidation (Week 8)

| # | Action | Notes |
|---|--------|-------|
| 5.1 | Audit `TenantCollection` wrapper | Tenant filtering for MongoDB |
| 5.2 | ✅ DONE — `get_collection()` uses singleton | Two leak points patched |
| 5.3 | Refactor `get_collection()` to use `TenantCollection` | Tenant isolation |
| 5.4 | Rename fields: `bgcode` → `bg_code`, `division` → `div_code` | Canonical naming |
| 5.5 | Audit migration commands | `migrate_mongodb_to_unified`, `reconcile_user_models` |

### Phase 6 — RBAC Migration (Week 9)

Complete migration from legacy `Accesslevel` (40 columns) to normalized RBAC. Audit seed scripts, API views, permission classes, auth utilities.

### Phase 7 — Legacy Cleanup (Week 10)

Remove root-level legacy endpoints. Move all endpoints under `/api/v1/` domain routing. Consolidate admin panels. Deprecate `rebellion/` shim.

### Phase 8 — Kuro Gaming Decommission (Week 11)

Verify all Kuro Gaming endpoints have KungOS equivalents. Migrate all data. Update DNS/API gateway. Stop Kuro Gaming services. Archive repo.

### Phase 9 — Testing & CI/CD (Week 12)

Full test coverage (≥80%), CI pipeline, deployment pipeline. Integration tests for tenant isolation, RBAC, outbox pattern, event bus, API contracts.

---

## 12. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| MongoDB tenant filtering missed in some queries | High | Critical (data leak) | `TenantCollection` wrapper + code review |
| RBAC migration breaks existing permissions | Medium | High | Staging test with all user roles |
| Gaming WebSocket consumers break on domain move | Medium | Medium | Integration tests for WebSocket |
| Data migration loses rows | Low | Critical | Row count verification + rollback backup |
| Kuro Gaming users can't log in after auth merge | Medium | Critical | Auth testing with all user types |
| Outbox pattern not transactional | Medium | High | `transaction.on_commit` pattern |
| MeiliSearch index stale after migration | Low | Medium | Reindex command + event trigger |
| cafe-fnb OrderGateway bypasses tenant filter | Low | Critical (data leak) | ✅ Mitigated: all queries use `get_collection()` |
| Session end fails if OrderGateway unavailable | Low | Medium | ✅ Mitigated: returns `None` → `food_total = 0` |
| Legacy kgorders schema drift | Medium | Medium | ✅ Mitigated: graceful degradation |
| Dual-write inconsistency (PG vs Mongo) | Medium | Medium | ⏳ Open: `transaction.atomic()` only covers PG |
| Zero test coverage for cafe_arcade | High | High | ⏳ Open: `tests/` is empty |
| Mongo bloat — no TTL/cleanup for kgorders | Medium | Medium | ⏳ Open: no data lifecycle policy |
| WebSocket consumers are stubs | Medium | Medium | ⚠️ 10 handlers return `ack: True` only |
| Identity dedup merges wrong records | Medium | High | ⏳ Fuzzy match >85% auto-merge, manual review for conflicts |
| Phone normalization fails for edge cases | Low | Medium | ⏳ phonenumbers library handles most cases |
| CafeWallet polymorphic owner breaks on identity migration | Medium | Medium | ⏳ Phase 4 alignment required |

---

## 13. Open Questions

1. **MongoDB strategy:** Keep PyMongo direct access or migrate to Django ORM for all models?
2. **Frontend:** What is the current frontend state? Is there a `kurogg-nextjs` or `kteam-fe-chief`?
3. **Deployment target:** Kubernetes (Helm) or docker-compose + systemd?
4. **Timeline:** 12 weeks assumed — is this realistic?
5. **Team size:** How many developers? Parallel workstreams?
6. **Data migration testing:** Do we have a staging DB with production-like data?
7. **kgorders schema:** What fields exist in production `kgorders`? `OrderGateway.create()` assumes specific fields. Need to verify against actual documents.
8. **Gaming collections:** When will gaming apps be merged into `kungos_dj/domains/eshop/`? (Phase 3b blocker)
9. **RLS timeline:** PostgreSQL RLS deferred — when is production cutover? Risk window for app-level filtering only.
10. **`food_charges` column drop:** Deferred to Phase 9 — what's the transition criteria?

---

## Appendix A: Architecture Conflict Resolution Log

| Conflict | Sources | Resolution | Authority |
|----------|---------|------------|-----------|
| E-commerce model location | Integration Plan originally `domains/accounts/` | `domains/eshop/` exclusively | Council verdict 2026-05-13 (Gemma + Nemo) |
| Wallet schema (2 definitions) | kungos_v2_db.md §1.2 (Definition A vs B) | Definition B (polymorphic walkin/user) is live | Verified against live DB |
| Cafe walkins phone uniqueness | kungos_v2_db.md (unique) vs Identity Design (drop) | Current: unique tenant-scoped. Target: drop after Phase 4 | Identity Design §2.3 |
| Cafe users redundancy | kungos_v2_db.md (current) vs Identity Design (replace) | Current: thin projection works. Target: replace with `users_identity` | Identity Design §2.3 |
| `platform/` vs `plat/` naming | KungOS_v2.md (`platform/`) vs filesystem (`plat/`) | `plat/` is actual directory | Verified on disk |
| Orders domain separation | Integration Plan vs Identity Design | `domains/orders/` = back-office, `domains/eshop/` = e-commerce, `domains/cafe_fnb/` = F&B | Council verdict |
| MongoDB field naming | `bgcode` vs `bg_code` | Canonical: `bg_code`, `div_code`, `branch_code` | Locked 2026-05-13 |
| Session food charges | `food_charges` vs `last_order_id` | `last_order_id` added, `food_charges` deprecated fallback | Council decision 2026-05-13 |

---

## Appendix B: Document Cross-Reference

| Topic | Primary Reference | Secondary |
|-------|-------------------|-----------|
| PostgreSQL schema (detailed columns) | `kungos_v2_db.md` §1.2 | This doc §2, §4.2, §5 |
| API endpoint design | `KungOS_Endpoint_Design.md` | This doc §9 |
| Orders migration plan | `orders-migration-plan.md` | This doc §6 |
| Cafe platform design | `CAFE_PLATFORM.md` | This doc §5 |
| DB test plan | `kungos_db_test_plan.md` | — |
| Master modernization plan | `KungOS_v2.md` | This doc §11 |
| Cafe audit report | `~/llm-wiki/cafe-audit-report.md` | This doc §5 |
| Cafe council review | `~/llm-wiki/cafe-council-review.md` | This doc §5 |

---

**Last updated:** 2026-05-16
**Next update:** After Phase 1 completion (e-commerce models in `domains/eshop/`)
**Superseded documents:** `KUNGOS_INTEGRATION_PLAN.md`, `KungOS_Identity_Design.md`, `kungos_v2_db.md` (retain as historical reference)
