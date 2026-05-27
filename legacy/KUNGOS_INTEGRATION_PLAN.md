# KungOS Integration Plan — Single Working Document

**Date:** 2026-05-12
**Council Review:** 2026-05-13 (Gemma `reviewer-arch` + Nemo `reviewer-logic` + GPT-OSS `reviewer-diversity`)
**Last Updated:** 2026-05-13 (Phase 2A/2B complete: session_end fix, cafe-fnb domain created)
**Sources:** Specialist-coder audit, Builder attempts (2x), Nemo deep-audit, Nemo integration-audit, Nemo rename+split review, Gemma council review, GPT-OSS council review, manual verification, filesystem verification
**Status:** Council-reviewed — Phase 1 corrected, Phase 2A/2B complete, platform primitives verified

> **This is the single working document for the KungOS integration program.** `KungOS_v2.md` is the master plan but its progress log is stale (2-3 weeks behind). When the two documents conflict, this integration plan reflects the verified state of the codebase.

---

## Verified Ground Truth

### Two Separate Django Projects

| | **KungOS (kteam-dj-chief)** | **Kuro Gaming (kuro-gaming-dj-backend)** |
|---|---|---|
| **Path** | `~/Coding-Projects/kteam-dj-chief/` | `~/Coding-Projects/kuro-gaming-dj-backend/` |
| **manage.py** | Yes (root) | Yes (root) |
| **Django** | 5.x | 4.1.13 (EOL) |
| **Auth** | `rest_framework_simplejwt` + `CookieJWTAuthentication` | `knox` (legacy token) + custom `ModelBackend` |
| **User model** | `users.models.CustomUser` (AbstractBaseUser) | `users.models.CustomUser` (AbstractBaseUser) |
| **Structure** | Domain-first (`domains/*`) + platform primitives (`plat/*`) | Flat apps (`accounts`, `orders`, `products`, `games`, `payment`, `kuroadmin`, `users`) |
| **Multi-tenant** | `tenant/`, `tenant_api/`, `plat/tenant/` (RLS, config, verify) | None |
| **Observability** | `plat/observability/` (CorrelationID, TenantContext middleware) | None |
| **Outbox/Events** | `plat/outbox/` (models, service, worker), `plat/events/` (bus, types) | None |
| **API Schema** | `drf_spectacular` (OpenAPI/Swagger/ReDoc) | None |
| **Search** | `meilisearch` configured | None |
| **Channels** | `channels` (ASGI/WebSockets) | None |
| **DB** | PostgreSQL + MongoDB (PyMongo direct) | PostgreSQL + MongoDB (djongo deprecated bridge) |
| **Deployment** | `docker-compose.yml` (Mongo + MeiliSearch), systemd services | `docker-compose.yml` absent, manual |

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

### KungOS URL Routing (verified — backend/urls.py)

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

Root-level legacy endpoints (still active):
  /api/v1/bgSwitch, /api/v1/accesslevel, /api/v1/pwdreset, /api/v1/verify
  /api/v1/empprofile, /api/v1/employeesdata, /api/v1/kuro/user, /api/v1/reb/user
  /api/v1/auth/login, /api/v1/auth/kuroregister, /api/v1/auth/rebregister
  /api/v1/auth/refresh, /api/v1/auth/logout
```

### Kuro Gaming URL Routing (verified — backend/urls.py)

```
/             → users.urls
/api/products/ → products.urls
/api/accounts/ → accounts.urls
/api/orders/   → orders.urls
/api/games/    → games.urls
/api/payment/  → payment.urls
/api/kuroadmin/ → kuroadmin.urls
```

### Domain Implementation Status (verified)

| Domain | models.py | viewsets.py | urls.py | notes |
|--------|-----------|-------------|---------|-------|
| accounts | ❌ | ✅ | ✅ | MongoDB collections (inward/outward invoices) |
| orders | ❌ | ✅ | ✅ | Deduplicates kuroadmin+ kurostaff estimates |
| products | ❌ | ✅ | ✅ | + depreciation.py |
| vendors | ❌ | ✅ | ✅ | |
| teams | ❌ | ✅ | ✅ | |
| search | ❌ | ✅ | ✅ | MeiliSearch operations |
| shared | ❌ | ✅ | ✅ | Cross-cutting utilities |
| eshop | ❌ | ❌ | ❌ | Empty shell |
| cafe_arcade | ✅ | ✅ | ✅ | 14 models + views + gamers_views + legacy_views (moved from rebellion/cafe/) |
| cafe_fnb    | ❌ | ❌ | ✅ | Gateway domain: OrderGateway (retry/circuit-breaker/idempotency) + views + serializers. No PG models — MongoDB only. |
| tournaments | ❌ | ✅ | ✅ | views.py + urls.py (moved from rebellion/esports/) |

**Key finding:** No `models.py` in any domain. Models live in `users/models.py`, `tenant/models.py`, and MongoDB collections accessed directly via PyMongo.

### Platform Primitives (verified — plat/)

**Verified 2026-05-13 against live codebase.** All modules exist with real implementation. `plat/` is in `INSTALLED_APPS`. Observability middleware is in `MIDDLEWARE`.

| Module | Files | Lines | Status |
|--------|-------|-------|--------|
| `plat/outbox/` | models.py, service.py, worker.py | 95 + 73 | ✅ Real implementation — outbox pattern for cross-store consistency |
| `plat/events/` | bus.py, types.py | 100 + | ✅ Real implementation — domain event bus (emit/on pattern) |
| `plat/observability/` | context.py, logging.py, middleware.py | 69 + | ✅ In MIDDLEWARE — CorrelationIDMiddleware, TenantContextMiddleware |
| `plat/tenant/` | collection.py, config.py, exceptions.py, rls.py, verify.py | 77 + 45 + | ✅ Real implementation — Tenant RLS, config, verification |
| `plat/health/` | urls.py, views.py | — | ✅ Real implementation — health check endpoints |
| `plat/shared/` | encoding.py, helpers.py, validation.py | — | ✅ Real implementation — shared utilities |
| `plat/management/` | commands/seed_tenant_config.py | — | ✅ Tenant config seeding |

**Note:** `KungOS_v2.md` references `platform/` — the actual directory is `plat/`. `KungOS_v2.md` §"Phase 2 Progress Log" incorrectly marks these as "🟡 Not yet created" — they are implemented and wired.

### Users/Tenant Models (verified — users/models.py)

```
CustomUser (AbstractBaseUser) — primary user model
KuroUser — legacy user profile
Switchgroupmodel — tenant switching context
Accesslevel — legacy 40+ column permission table
PhoneModel — phone number storage
UserTenantContext — tenant context per user
Common_counters — counters
Permission — normalized permission model (new)
Role — role model (new)
RolePermission — role-permission mapping (new)
UserRole — user-role assignment (new)
UserRoleBranch — user-role-branch assignment (new)
UserPermission — user-permission assignment (new)
```

### Tenant Models (verified — tenant/models.py)

```
BusinessGroup — primary tenant unit (legal entity)
Division — operational divisions within a BG
Branch — physical outlets/locations within a Division
BankAccount — bank accounts under a BG
```

### Rebellion/Cafe (verified — rebellion/ → domains/ on 2026-05-13)

```
rebellion/                    # Thin shim for backward compat
  views.py                   # Imports from domains.tournaments, domains.cafe_arcade
  urls.py                    # Routes to domains.tournaments, domains.cafe_arcade
  admin.py

domains/cafe_arcade/          # Moved from rebellion/cafe/ (2026-05-13)
  models.py                  # 14 models: Session, Station, Cafe, Game, CafeWallet, etc.
  views.py                   # Gaming views (sessions, stations, wallet, etc.) — session_end() fixed 2026-05-13
  gamers_views.py            # Gamer session tracking (split from tournaments)
  legacy_views.py            # Legacy MongoDB-based views
  serializers.py             # Gaming serializers — last_order_id added to SessionSerializer + SessionEndResponse
  urls.py                    # Cafe-Arcade URLs (included via backend/urls.py as /api/v1/cafe/)
  tasks.py
  channels/consumers.py      # WebSocket consumers
  channels/routing.py
  management/commands/seed_games.py, seed_member_plans.py, seed_pricing.py, seed_stations.py
  migrations/0001_initial.py, 0002_tenant_framework.py, 0003_session_order_ref.py
  tests/                     # Empty — needs tests (T1 council finding)

domains/cafe_fnb/             # Created 2026-05-13 — Phase 2B complete
  __init__.py                # Domain docstring
  apps.py                    # CafeFnbConfig
  gateways.py                # OrderGateway: get(), get_amount_paid(), create(), list_orders()
                             # Resilience: circuit-breaker (5 failures → 30s reset), retry (3x exponential backoff), idempotency (_operation_id)
  views.py                   # menu, create_order, get_order, list_orders
  serializers.py             # OrderCreateRequest, OrderResponse, OrderListResponse, MenuItemSerializer
  urls.py                    # /api/v1/cafe-fnb/ (menu, orders, orders/create, orders/<id>)
  migrations/__init__.py     # No PG models — gateway only

domains/tournaments/          # Moved from rebellion/esports/ (2026-05-13)
  views.py                   # tournaments, players, teams, tourneyregister
  urls.py                    # Tournament URL routing (registered via rebellion/urls.py)
  apps.py
```

**Key finding:** `domains.cafe_arcade` has real implementation (14 models, views, serializers, channels, seed commands, gamers_views, legacy_views) — moved from `rebellion/cafe/` on 2026-05-13. `domains.tournaments` has `views.py` (tournaments, players, teams, tourneyregister) — moved from `rebellion/esports/` on 2026-05-13. Empty shells `domains/cafe/` and `domains/esports/` deleted. All imports updated to `domains.cafe_arcade` and `domains.tournaments`.

### Kuro Gaming Models (verified)

| App | models.py | serializers.py | Content |
|-----|-----------|----------------|---------|
| accounts | ✅ | ❌ | Cart, Wishlist, Addresslist (59 lines) |
| orders | ✅ | ✅ | Orders (30+ fields), OrderItems |
| products | ❌ (3 lines) | ❌ | Empty stub |
| games | ❌ (3 lines) | ❌ | Empty stub |
| payment | ❌ (3 lines) | ❌ | Empty stub |
| users | ✅ | ✅ | CustomUser (AbstractBaseUser) |
| kuroadmin | ✅ | ❌ | Admin models |

**Key finding:** `products`, `games`, `payment` are all empty stubs in Kuro Gaming. The real product/game data lives in MongoDB collections, not Django ORM models.

---

## Security Issues (CRITICAL — fix before anything else)

### 1. Hardcoded AWS Credentials in Kuro Gaming
**File:** `~/Coding-Projects/kuro-gaming-dj-backend/backend/settings.py`
```python
DBBACKUP_STORAGE_OPTIONS = {
    "access_key": "[REDACTED]",
    "secret_key": "uASP3ZGsQPOmHPOPEmW7V6+E8/CQFohb2urbijK2",
    "bucket_name": "kuro-db-backup",
}
```
**Impact:** Anyone with repo access can read/write production backups.
**Fix:** Replace with `env('AWS_ACCESS_KEY_ID')`, `env('AWS_SECRET_ACCESS_KEY')`, `env('AWS_BUCKET')`. Rotate keys immediately.

### 2. Hardcoded MeiliSearch Key in KungOS docker-compose.yml
**File:** `~/Coding-Projects/kteam-dj-chief/docker-compose.yml`
```yaml
MEILI_MASTER_KEY=aSampleMasterKey
```
**Impact:** Search index accessible without authentication.
**Fix:** Use env var `MEILI_MASTER_KEY`.

### 3. Default SECRET_KEY Fallback in Kuro Gaming
**File:** `~/Coding-Projects/kuro-gaming-dj-backend/backend/settings.py`
```python
SECRET_KEY = env('DJANGO_SECRET_KEY', default='change-me-in-production')
```
**Impact:** Predictable key → session forgery.
**Fix:** Remove default, require env var.

### 4. Knox Token Auth (no rotation/refresh)
**File:** `~/Coding-Projects/kuro-gaming-dj-backend/backend/settings.py`
**Impact:** Tokens never expire, no rotation, no blacklist.
**Fix:** Migrate to SimpleJWT (already in KungOS).

---

## Architecture Gap Analysis

### What KungOS Has That Kuro Gaming Needs

| Feature | KungOS | Kuro Gaming | Gap |
|---------|--------|-------------|-----|
| Multi-tenant | ✅ tenant/, tenant_api/, plat/tenant/ | ❌ | Full tenant system needed |
| JWT auth | ✅ SimpleJWT + CookieJWT | ❌ Knox | Auth migration |
| Domain structure | ✅ domains/ | ❌ flat apps | Restructure |
| Observability | ✅ CorrelationID, TenantContext middleware | ❌ | Add middleware |
| Outbox pattern | ✅ plat/outbox/ | ❌ | Add to Kuro |
| Event bus | ✅ plat/events/ | ❌ | Add to Kuro |
| OpenAPI docs | ✅ drf_spectacular | ❌ | Add to Kuro |
| Pagination | ✅ PageNumberPagination (20/page) | ❌ | Add to Kuro |
| Throttling | ✅ Per-endpoint rate limits | ❌ | Add to Kuro |
| RBAC (normalized) | ✅ Permission, Role, UserRole models | ❌ Accesslevel (40 columns) | Migrate |
| Management commands | ✅ seed_rbac_roles, migrate_mongodb_to_unified, etc. | ❌ | Port commands |

### What Kuro Gaming Has That KungOS Needs

| Feature | Kuro Gaming | KungOS | Gap |
|---------|-------------|--------|-----|
| Cart model | ✅ accounts.models.Cart | ❌ domains/eshop/ is empty shell | Port Cart to `domains/eshop/` |
| Wishlist model | ✅ accounts.models.Wishlist | ❌ | Port Wishlist to `domains/eshop/` |
| Address model | ✅ accounts.models.Addresslist | ❌ | Port Address to `domains/eshop/` |
| Order model (ORM) | ✅ orders.models.Orders | ❌ domains/eshop/ is empty shell | Port Orders to `domains/eshop/` |
| OrderItems model | ✅ orders.models.OrderItems | ❌ | Port OrderItems to `domains/eshop/` |
| Order serializers | ✅ orders/serializers.py | ❌ | Port serializers to `domains/eshop/` |
| E-commerce flow | ✅ (cart → order → payment) | ❌ | Integrate into `domains/eshop/` |

**Council verdict (2026-05-13):** All e-commerce models go to `domains/eshop/` — NOT `domains/accounts/`, `domains/orders/`, or `domains/products/`. See architecture conflict resolution below.

### Overlap / Conflict Areas

| Area | KungOS | Kuro Gaming | Conflict | Resolution |
|------|--------|-------------|----------|------------|
| `accounts/` | `domains.accounts/` (viewsets for inward/outward invoices — **FINANCE**) | `accounts/` (Cart, Wishlist, Addresslist — **E-COMMERCE**) | Different business domains — KungOS=finance, Kuro=e-commerce | ✅ **Resolved:** Cart, Wishlist, Addresslist → `domains/eshop/`. `domains/accounts/` stays finance-only. |
| `orders/` | `domains.orders/` (Estimates, TP orders, **In-store orders**, Purchase orders — **BACK-OFFICE**) | `orders/` (e-commerce orders with 30+ fields — **E-COMMERCE**) | Different order types — need to distinguish | ✅ **Resolved:** E-commerce Orders + OrderItems → `domains/eshop/`. `domains/orders/` stays back-office (Estimates, TP, In-store, PO). |
| `products/` | `domains.products/` (viewsets for asset catalog — **INVENTORY**) | `products/` (empty stub, data in MongoDB) | KungOS has viewsets, Kuro has MongoDB data | ✅ **Resolved:** E-commerce product catalog stays in MongoDB; `domains/eshop/` provides ORM models for relational data. `domains/products/` stays inventory. |
| `users/` | `users/` (CustomUser + RBAC models) | `users/` (CustomUser, authenticate.py) | Same model name, different schemas | Reconcile schemas (Phase 4) |
| `kuroadmin/` | `kungos_admin/` | `kuroadmin/` | Both are admin panels | Merge during legacy cleanup (Phase 7) |

### Architecture Conflict Resolution (Council Verdict, 2026-05-13)

**Conflict:** `KungOS_v2.md` places e-commerce models in `domains/eshop/`. `KUNGOS_INTEGRATION_PLAN.md` Phase 1 originally merged them into `domains/accounts/`, `domains/orders/`, `domains/products/`.

**Verdict:** `domains/eshop/` is the correct home. Both Gemma (`reviewer-arch`) and Nemo (`reviewer-logic`) agreed:

- **Namespace integrity:** `domains/accounts/` is Finance/Invoices. `domains/orders/` is Back-office/In-store. Mixing e-commerce into these creates "God Domains".
- **Security:** Merging e-commerce into `domains/accounts/` creates cross-domain permission leakage (a FinancePermission user could access Cart endpoints).
- **Brand ownership:** `domains/eshop/` preserves brand boundaries per KungOS principle #9 (Domain-as-Django-app, Brand-as-sub-package).
- **URL clarity:** `/api/v1/eshop/cart/` vs ambiguous `/api/v1/accounts/cart/`.
- **Zero-cost entry:** `domains/eshop/` is already in `INSTALLED_APPS` — empty shell waiting.

**Phase 1 corrected to target `domains/eshop/` exclusively.** All steps below reflect this.

---

## Atomic Implementation Plan

### Phase 0 — Security Hardening (Week 1)

**Goal:** Eliminate all hardcoded secrets, fix auth, prepare for merge.

| # | File | Action | Why | Validation |
|---|------|--------|-----|-----------|
| 0.1 | `kuro/backend/settings.py` | Replace hardcoded AWS keys with `env('AWS_ACCESS_KEY_ID')`, `env('AWS_SECRET_ACCESS_KEY')`, `env('AWS_BUCKET')` | Prevent data leak | `grep -r "[REDACTED]"` → no matches |
| 0.2 | `kuro/backend/settings.py` | Remove `default='change-me-in-production'` from SECRET_KEY | Prevent session forgery | App fails to start without env var |
| 0.3 | `kuro/backend/settings.py` | Replace `knox` with `rest_framework_simplejwt` in `INSTALLED_APPS` and `DEFAULT_AUTHENTICATION_CLASSES` | Unified auth stack | `pip show djangorestframework-simplejwt` |
| 0.4 | `kuro/backend/settings.py` | Add `drf_spectacular`, `corsheaders` to `INSTALLED_APPS` | API docs + CORS | OpenAPI schema accessible |
| 0.5 | `kuro/requirements.txt` | Add `djangorestframework-simplejwt`, `drf-spectacular`, `django-cors-headers`. Remove `knox`, `djongo`. | Dependency alignment | `pip install -r requirements.txt` succeeds |
| 0.6 | `kuro/backend/settings.py` | Add `MIDDLEWARE` entries for `CorrelationIDMiddleware` and `TenantContextMiddleware` (copy from KungOS) | Observability parity | Response header `X-Correlation-ID` present |
| 0.7 | `kuro/backend/settings.py` | Add `REST_FRAMEWORK` config matching KungOS (pagination, throttling, auth) | API consistency | `GET /api/products/` returns paginated response |
| 0.8 | `kuro/backend/settings.py` | Add `MONGO_DB_URI = env('MONGO_DB_URI', default='mongodb://127.0.0.1:27017')` | Config consistency | MongoDB connection uses env var |

**Completion criteria:**
- No hardcoded secrets in either repo
- Both projects use SimpleJWT
- Both projects have correlation ID middleware
- Both projects have pagination + throttling

---

### Phase 1 — E-Commerce Models: Kuro → `domains/eshop/` (Weeks 2-3)

**Goal:** Populate the empty `domains/eshop/` shell with Kuro Gaming's e-commerce ORM models, adding tenant fields.

**Council-locked target:** All e-commerce models go to `domains/eshop/`. NOT `domains/accounts/` (finance), NOT `domains/orders/` (back-office), NOT `domains/products/` (inventory).

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 1.1 | `domains/eshop/models.py` *(create)* | Define `Cart`, `Wishlist`, `Addresslist` models from Kuro Gaming's `accounts/models.py`, adding `bg_code` FK to `tenant.BusinessGroup` | Populates empty eshop shell with e-commerce models | `python manage.py makemigrations domains.eshop` creates migration |
| 1.2 | `domains/eshop/models.py` | Define `Order`, `OrderItem` models from Kuro Gaming's `orders/models.py`, adding `bg_code` FK | E-commerce order models (distinct from back-office orders in `domains/orders/`) | `makemigrations domains.eshop` creates migration |
| 1.3 | `domains/eshop/serializers.py` *(create)* | Create `CartSerializer`, `WishlistSerializer`, `AddresslistSerializer`, `OrderSerializer`, `OrderItemSerializer` with tenant validation | API serialization for all e-commerce models | `python manage.py test domains.eshop` passes |
| 1.4 | `domains/eshop/viewsets.py` *(create)* | Create `CartViewSet`, `WishlistViewSet`, `AddresslistViewSet`, `OrderViewSet`, `OrderItemViewSet` | E-commerce endpoints under `/api/v1/eshop/` | `GET /api/v1/eshop/cart/` returns 200 |
| 1.5 | `domains/eshop/urls.py` *(create)* | Register all e-commerce viewsets on router under `eshop/` prefix | URL wiring — keeps `/api/v1/eshop/` namespace separate from `/api/v1/accounts/` (finance) and `/api/v1/orders/` (back-office) | All eshop endpoints accessible |
| 1.6 | `backend/urls.py` | Add `path('eshop/', include('domains.eshop.urls'))` to `/api/v1/` routing | Wire eshop into main URL tree | `/api/v1/eshop/` routes active |

**What stays untouched:**
- `domains/accounts/` — Finance/invoices only (inward/outward invoices). No e-commerce models added.
- `domains/orders/` — Back-office/in-store only (Estimates, TP orders, In-store orders, Purchase orders). No e-commerce models added.
- `domains/products/` — Inventory/asset catalog only. No e-commerce product models added.

**Data migration strategy:**
- PostgreSQL models (Cart, Wishlist, Addresslist, Orders, OrderItems): Django migration with `RunPython` to copy from Kuro Gaming DB
- MongoDB collections: Use existing `users/management/commands/migrate_mongodb_to_unified.py` command

**Completion criteria:**
- All 5 Kuro Gaming e-commerce models exist in `domains/eshop/models.py` with `bg_code` FK
- All 5 serializers exist in `domains/eshop/serializers.py`
- All 5 viewsets exist in `domains/eshop/viewsets.py`
- `domains/eshop/urls.py` registers all viewsets under `/api/v1/eshop/`
- Data migration scripts tested on staging DB
- All eshop endpoints return correct tenant-scoped data
- `domains/accounts/`, `domains/orders/`, `domains/products/` remain unchanged (no e-commerce models added)

---

### Phase 2 — Gaming Domain Integration (Weeks 4-5)

**Goal:** Integrate gaming-specific functionality into KungOS domain structure.

#### 2A — Session Model Fix (Week 4, Day 1) ✅ **DONE 2026-05-13**

| # | File | Action | Why | Validation |
|---|------|--------|-----|-----------|
| 2.1 | `domains/cafe_arcade/models.py` | ✅ `last_order_id` added (migration 0003). `food_charges` kept as deprecated fallback (NOT dropped yet) | Council decision: session references F&B, doesn't embed it | Migration 0003 applied |
| 2.2 | `domains/cafe_arcade/views.py` | ✅ `session_end()` fixed: (a) indentation bug fixed — `started_at`/`billed_minutes` inside `transaction.atomic()`, (b) two `transaction.atomic()` blocks merged into one — eliminates race condition, (c) `food_total` logic: `last_order_id` → 0 (no double-count), else `food_charges` fallback | Single source of truth for food charges; eliminates race condition window | 1 `transaction.atomic()` block, all code inside scope |
| 2.3 | `domains/cafe_arcade/serializers.py` | ✅ `last_order_id` added to `SessionSerializer` fields + `SessionEndResponse`. `food_charges` marked with `help_text='Deprecated — use last_order_id'` | API surfaces new field during transition | Serializers include `last_order_id` |
| 2.4 | `domains/cafe_arcade/models.py` | ⏳ `food_charges` column NOT dropped yet — kept as deprecated fallback until transition complete. Drop in Phase 9 after all sessions migrated. | Safe transition — existing sessions with `food_charges > 0` still bill correctly | Column present, marked `# DEPRECATED` |

**Council review findings applied (2026-05-13):**
- Gemma R1: Dual-write inconsistency flagged — `transaction.atomic()` only covers PG. OrderGateway Mongo writes outside PG transaction. Mitigation: `food_total = 0` when `last_order_id` is set (no double-count) until OrderGateway lookup is implemented.
- Gemma R3: Data backfill for `last_order_id` deferred — no existing sessions have `food_charges > 0` per audit.
- GPT-OSS D1: Zero test coverage confirmed — `tests/` is empty. First tests needed for `session_end()` concurrency.
- GPT-OSS indentation bug: Confirmed real — lines 512-513 were outside `transaction.atomic()`. Fixed.

#### 2B — Create cafe-fnb/ Domain (Week 4, Days 2-3) ✅ **DONE 2026-05-13**

| # | File | Action | Why | Validation |
|---|------|--------|-----|-----------|
| 2.4 | `domains/cafe_fnb/` | ✅ Created: `__init__.py`, `apps.py`, `gateways.py`, `views.py`, `serializers.py`, `urls.py`, `migrations/__init__.py` | Lightweight F&B domain (council-locked) | Domain registered in INSTALLED_APPS, imports OK |
| 2.5 | `domains/cafe_fnb/gateways.py` | ✅ `OrderGateway` with 4 methods: `get()`, `get_amount_paid()`, `create()`, `list_orders()`. Resilience: circuit-breaker (5 failures → 30s reset), retry (3x exponential backoff 0.1→0.4→0.8s), idempotency (`_operation_id` dedup) | Adapter pattern: new domain, legacy data | All methods import, circuit-breaker starts `closed` |
| 2.6 | `domains/cafe_fnb/views.py` | ✅ `POST /cafe-fnb/orders/create` (create), `GET /cafe-fnb/orders/<id>` (lookup), `GET /cafe-fnb/orders` (list with pagination/date filters) | F&B order endpoints | 5 URL patterns registered |
| 2.7 | `domains/cafe_fnb/views.py` | ✅ `GET /cafe-fnb/menu` — stub (returns empty menu). Needs stock_register schema to populate. | Menu lookup | Endpoint returns 200 with empty items |
| 2.8 | `domains/cafe_fnb/serializers.py` | ✅ `OrderCreateRequest`, `OrderResponse`, `OrderListResponse`, `MenuItemSerializer`, `MenuResponse` | API serialization | All serializers import |
| 2.9 | `domains/cafe_fnb/urls.py` | ✅ 5 patterns: `menu`, `orders-list`, `orders-list-slash`, `orders-create`, `orders-detail` | URL wiring | All resolve under `/api/v1/cafe-fnb/` |
| 2.10 | `backend/urls.py` | ✅ `path('cafe-fnb/', include('domains.cafe_fnb.urls'))` | URL wiring | `/api/v1/cafe-fnb/orders/` accessible |
| 2.11 | `backend/settings.py` | ✅ `'domains.cafe_fnb'` added to INSTALLED_APPS | App registration | `apps.get_app_config('cafe_fnb')` returns CafeFnbConfig |

**No models.py** — F&B data stays in MongoDB `kgorders` + `stock_register`. The domain is a gateway, not a new data store.

**Resilience features (beyond original plan — per GPT-OSS D2):**
- **Circuit-breaker:** Opens after 5 consecutive failures, resets after 30s. Returns 503 to caller.
- **Retry:** Exponential backoff (3 retries, base 0.1s, max 2.0s) for transient errors.
- **Idempotency:** `create()` uses `_operation_id` (auto-generated UUID) to prevent duplicate orders on retry.
- **Tenant filtering:** All queries use `get_collection()` with `bg_code`/`div_code`/`branch_code`.
- **Graceful degradation:** `get()` and `get_amount_paid()` return `None`/`0` on failure (no exception propagation for read paths).

#### 2C — Gaming Domain Audit (Week 4-5)

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 2.11 | `domains/cafe_arcade/models.py` | Audit existing models (Game, Station, MemberPlan, Pricing, Session, etc.) | domains.cafe_arcade has real gaming logic (14 models) | Models document all gaming entities |
| 2.12 | `domains/cafe_arcade/serializers.py` | Audit existing serializers | Serializers exist — verify completeness | All models have serializers |
| 2.13 | `domains/cafe_arcade/management/commands/seed_games.py` | Audit seed data | Gaming catalog seeding | Seed command runs |
| 2.14 | `domains/cafe_arcade/management/commands/seed_stations.py` | Audit seed data | Station seeding | Seed command runs |
| 2.15 | `domains/cafe_arcade/management/commands/seed_member_plans.py` | Audit seed data | Member plan seeding | Seed command runs |
| 2.16 | `domains/cafe_arcade/management/commands/seed_pricing.py` | Audit seed data | Pricing seeding | Seed command runs |
| 2.17 | `domains/cafe_arcade/channels/consumers.py` | Audit WebSocket consumers | Real-time gaming features | Consumers handle events |
| 2.18 | `domains/tournaments/` | ✅ **DONE** — tournaments, players, teams, tourneyregister views moved from `rebellion/esports/` on 2026-05-13 | Architecture decision implemented |
| 2.19 | `domains/cafe_arcade/gamers_views.py` | ✅ **DONE** — gamers endpoints (session tracking: time, food, billing) split from tournaments into cafe_arcade on 2026-05-13 | Gamers belong in cafe-arcade, not tournaments |
| 2.20 | `domains/eshop/` | ✅ **DECIDED:** Keep separate for e-commerce. All Kuro Gaming e-commerce models (Cart, Wishlist, Addresslist, Orders, OrderItems) live here. See Phase 1 + council verdict above. | Populated in Phase 1 | Phase 1 exit criteria met |

**Note:** `rebellion/cafe/` was renamed to `domains/cafe_arcade/` on 2026-05-13. `rebellion/esports/` was renamed to `domains/tournaments/` on 2026-05-13. Empty shells `domains/cafe/` and `domains/esports/` were deleted.

**Completion criteria:**
- ✅ `Session.last_order_id` added (migration 0003). `food_charges` kept as deprecated fallback.
- ✅ `domains/cafe_fnb/` created with `OrderGateway` adapter (retry + circuit-breaker + idempotency)
- ✅ F&B order endpoints functional (`POST /cafe-fnb/orders/create`, `GET /cafe-fnb/orders/<id>`, `GET /cafe-fnb/orders`)
- ✅ `GET /cafe-fnb/menu` returns 200 (stub — needs stock_register schema)
- ⏳ Session end calculates food charges via `OrderGateway` lookup — `food_total = 0` when `last_order_id` set (prevents double-count). Full lookup pending TODO in `session_end()`.
- ✅ `domains.cafe_arcade` verified (renamed from `rebellion.cafe` on 2026-05-13)
- ✅ `domains.tournaments` verified (renamed from `rebellion.esports` on 2026-05-13)
- ✅ `domains.cafe_arcade.gamers_views` verified (gamers split from tournaments on 2026-05-13)
- ⏳ Tests for `session_end()` concurrency + double-end protection — `tests/` is empty (GPT-OSS D1)
- ⏳ `food_charges` column drop — deferred to Phase 9 after transition complete

---

### Phase 3 — Payment Integration (Week 6)

**Goal:** Create payment domain from Kuro Gaming's payment logic.

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 3.1 | `domains/payment/` *(create)* | Create new domain: `models.py`, `serializers.py`, `viewsets.py`, `urls.py`, `apps.py` | Payment processing needs domain | Domain registered in INSTALLED_APPS |
| 3.2 | `domains/payment/models.py` | Define `PaymentTransaction`, `PaymentMethod`, `Refund` models with `bg_code` FK | Payment models | `makemigrations domains.payment` creates migration |
| 3.3 | `domains/payment/serializers.py` | Create serializers for payment models | API serialization | Serializers validate |
| 3.4 | `domains/payment/viewsets.py` | Create viewsets for payment operations | Payment API | Endpoints accessible |
| 3.5 | `domains/payment/services.py` *(create)* | Implement payment provider integration (Cashfree, UPI) from Kuro Gaming logic | Payment processing | Provider integration works |
| 3.6 | `domains/orders/models.py` | Add `payment_transaction` FK to `Order` model | Order-payment linkage | FK constraint enforced |
| 3.7 | `backend/urls.py` | Add `path('payment/', include('domains.payment.urls'))` | URL wiring | Payment endpoints accessible |

**Completion criteria:**
- Payment domain fully implemented
- Orders linked to payment transactions
- Payment provider integration tested

---

### Phase 4 — Auth Unification (Week 7)

**Goal:** Merge Kuro Gaming's auth into KungOS's SimpleJWT + tenant context.

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 4.1 | `users/models.py` | Compare Kuro Gaming's `CustomUser` fields with KungOS's `CustomUser` | Schema alignment | Field diff documented |
| 4.2 | `users/models.py` | Add any missing fields from Kuro Gaming (e.g., `name`, `emailVerified`) | Schema parity | Both user models compatible |
| 4.3 | `users/management/commands/` | Create `migrate_kuro_users.py` command | User data migration | Command migrates users |
| 4.4 | `users/api/viewsets.py` | Add Kuro Gaming registration endpoints (`kuroregister`, `kurologin`) | Auth endpoint parity | Endpoints work with SimpleJWT |
| 4.5 | `users/cookie_auth.py` | Verify tenant context is extracted from JWT | Tenant-aware auth | JWT contains `bg_code` |
| 4.6 | `backend/settings.py` | Verify `AUTH_USER_MODEL = 'users.CustomUser'` | Auth model config | Django uses correct model |

**Completion criteria:**
- Kuro Gaming users migrated to KungOS user model
- All auth endpoints use SimpleJWT
- JWT contains tenant context (`bg_code`, `div_code`)
- Both Kuro and KungOS login flows work

---

### Phase 5 — MongoDB Consolidation (Week 8)

**Goal:** Consolidate MongoDB collections, add tenant filtering.

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 5.1 | `plat/tenant/collection.py` | Audit `TenantCollection` wrapper | Tenant filtering for MongoDB | Wrapper adds `bg_code` filter |
| 5.2 | `backend/utils.py` | ✅ **FIXED (2026-05-13):** `get_collection()` uses singleton `get_mongo_client()` — confirmed working. Two leak points patched: `users/api/viewsets.py:552` (health check) and `backend/views_diagnostic.py:33` (diagnostic view) now use `get_mongo_client()` instead of creating per-request clients. | Main code path was fixed 2026-04-23; remaining leak points patched 2026-05-13 | All `MongoClient()` calls outside `management/commands/` route through singleton |
| 5.3 | `backend/utils.py` | Refactor `get_collection()` to use `TenantCollection` wrapper | Tenant isolation | All queries filtered by `bg_code` |
| 5.4 | `backend/utils.py` | Rename fields: `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` | **Canonical naming locked (2026-05-13).** All MongoDB documents must use underscored `_code` suffix. DB migration required for existing collections. | All queries use `_code` suffix |
| 5.5 | `users/management/commands/migrate_mongodb_to_unified.py` | Audit migration command | Existing migration tool | Command runs |
| 5.6 | `users/management/commands/reconcile_user_models.py` | Audit reconciliation command | User model reconciliation | Command runs |
| 5.7 | MongoDB collections (all) | DB migration: rename `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code` across all documents | Enforce canonical naming convention | Field names consistent across all collections |

**Completion criteria:**
- All MongoDB access goes through `TenantCollection` wrapper
- All `MongoClient()` calls in request path use singleton `get_mongo_client()` ✅ (done)
- Field naming consistent (`bg_code`, `div_code`, `branch_code`) — DB migration applied
- Migration commands tested

---

### Phase 6 — RBAC Migration (Week 9)

**Goal:** Complete migration from legacy `Accesslevel` (40 columns) to normalized RBAC.

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 6.1 | `seed_permissions.py` | Audit current seed script | Maps 40 columns → normalized permissions | Script runs idempotently |
| 6.2 | `users/management/commands/seed_rbac_roles.py` | Audit seed command | RBAC role seeding | Command runs |
| 6.3 | `users/models.py` | Verify `Permission`, `Role`, `RolePermission`, `UserRole`, `UserRoleBranch`, `UserPermission` models | RBAC models exist | Models documented |
| 6.4 | `users/api/rbac_views.py` | Audit RBAC API views | RBAC management API | Views work |
| 6.5 | `users/api/rbac_serializers.py` | Audit RBAC serializers | RBAC serialization | Serializers validate |
| 6.6 | `users/api/permissions.py` | Audit permission classes | Permission enforcement | Classes enforce |
| 6.7 | `backend/auth_utils.py` | Verify `resolve_access()`, `has_read_access()`, `has_write_access()`, `has_division_read_access()`, `has_division_write_access()` | Auth utilities complete | Functions work |
| 6.8 | `users/migrations/` | Create migration to deprecate `Accesslevel` model | Legacy model removal | Migration runs |

**Completion criteria:**
- All permissions use normalized RBAC models
- `Accesslevel` model deprecated
- Auth utilities work with new RBAC
- Migration tested on staging DB

---

### Phase 7 — Legacy Cleanup (Week 10)

**Goal:** Remove legacy code, consolidate routing.

| # | File (in kteam-dj-chief) | Action | Why | Validation |
|---|--------------------------|--------|-----|-----------|
| 7.1 | `backend/urls.py` | Remove root-level legacy endpoints (`/api/v1/bgSwitch`, `/api/v1/accesslevel`, etc.) | Single source of truth | Endpoints 404 |
| 7.2 | `backend/urls.py` | Move all endpoints under `/api/v1/` domain routing | Domain-first routing | All endpoints under `/api/v1/` |
| 7.3 | `kungos_admin/` | Audit for overlap with new domain admin | Admin consolidation | Overlap documented |
| 7.4 | `rebellion/` | Thin shim for backward compat — imports from `domains.tournaments` and `domains.cafe_arcade`. Deprecate after all external consumers migrate. | Legacy cleanup | `rebellion/` shim removed |
| 7.5 | `teams/` (flat app) | Audit for overlap with `domains.teams/` | Domain consolidation | Overlap documented |
| 7.6 | `careers/` | Audit — keep as-is or move to domain | Structure decision | Decision documented |

**Completion criteria:**
- All endpoints under `/api/v1/` domain routing
- Legacy endpoints removed or aliased
- No duplicate admin panels

---

### Phase 8 — Kuro Gaming Decommission (Week 11)

**Goal:** Fully decommission Kuro Gaming backend.

| # | Action | Why | Validation |
|---|--------|-----|-----------|
| 8.1 | Verify all Kuro Gaming endpoints have KungOS equivalents | No functionality lost | Endpoint mapping complete |
| 8.2 | Verify all Kuro Gaming data migrated to KungOS | No data loss | Data counts match |
| 8.3 | Update DNS/API gateway to route to KungOS | Traffic switch | All traffic goes to KungOS |
| 8.4 | Stop Kuro Gaming services | Resource cleanup | Services stopped |
| 8.5 | Archive Kuro Gaming repo | Historical record | Repo archived |

**Completion criteria:**
- All Kuro Gaming functionality available in KungOS
- All data migrated
- Kuro Gaming services stopped
- No traffic to Kuro Gaming

---

### Phase 9 — Testing & CI/CD (Week 12)

**Goal:** Full test coverage, CI/CD pipeline.

| # | Action | Why | Validation |
|---|--------|-----|-----------|
| 9.1 | `pytest.ini` — verify config | Test framework setup | `pytest` runs |
| 9.2 | `tests/` — audit existing tests | Test coverage | Tests pass |
| 9.3 | `test_viewsets.py` — audit | ViewSet tests | Tests pass |
| 9.4 | Add integration tests for tenant isolation | Tenant security | Cross-tenant access blocked |
| 9.5 | Add integration tests for RBAC | Permission enforcement | Permissions enforced |
| 9.6 | Add integration tests for outbox pattern | Cross-store consistency | Events delivered |
| 9.7 | Add integration tests for event bus | Event processing | Events processed |
| 9.8 | Add API contract tests for all domain endpoints | API stability | Contracts enforced |
| 9.9 | Set up GitHub Actions CI pipeline | Automated testing | Pipeline runs on PR |
| 9.10 | Set up deployment pipeline (Helm/K8s or docker-compose) | Automated deployment | Pipeline deploys |

**Completion criteria:**
- ≥80% test coverage
- CI pipeline runs on every PR
- Deployment pipeline tested
- All integration tests pass

---

## Cafe Platform Architecture Decision (LOCKED — 2026-05-13)

**Council Review:** Gemma-arch (DO NOT LOCK), Nemo-logic (DO NOT LOCK), GPT-OSS-diversity (PARTIALLY AGREE)
**Reports:** `~/llm-wiki/cafe-audit-report.md`, `~/llm-wiki/cafe-council-review.md`

### Decision: Lightweight F&B Domain, No Event Layer

| Topic | Decision | Rationale |
|-------|----------|----------|
| **F&B approach** | Separate `cafe-fnb/` domain | Lifecycle mismatch with sessions, inventory integrity, God object risk |
| **Event/orchestration layer** | ❌ Deferred | Over-engineering for 3 cafes (~30 orders/day). Add when >5 locations or franchise model |
| **Session ↔ F&B bridge** | `Session.last_order_id` (nullable FK) | Thin reference, no embedded food_charges |
| **Legacy MongoDB** | `kgorders` stays in MongoDB, `OrderGateway` adapter | No migration of 68K documents. Adapter reads/writes legacy kgorders |
| **Protocol chain** | Enforce: domains → services → repositories | Critical — prevents direct DB bypass, enables caching, audit, swapping |
| **rebellion/cafe/ rename** | ✅ **DONE (2026-05-13)** — renamed to `domains/cafe_arcade/` | Rename complete, all imports updated |

### Session Model Change (2026-05-13)

```python
# CURRENT STATE (domains/cafe_arcade/models.py)
class Session(models.Model):
    food_charges = models.DecimalField(max_digits=8, decimal_places=2, default=0)  # DEPRECATED: use last_order_id
    last_order_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)  # FK to kgorders.orderid
```

**Migration:** `0003_session_order_ref.py` — added `last_order_id`. `food_charges` NOT dropped yet (kept as deprecated fallback for transition period). Drop in Phase 9.

**`session_end()` fix (2026-05-13):**
- Indentation bug fixed — `started_at`/`billed_minutes` moved inside `transaction.atomic()`
- Two `transaction.atomic()` blocks merged into one — eliminates race condition window
- `food_total` logic: `last_order_id` → 0 (no double-count), else `food_charges` fallback
- Serializers updated: `last_order_id` in `SessionSerializer` + `SessionEndResponse`

### cafe-fnb/ Domain Structure (Lightweight) ✅ Created 2026-05-13

```
domains/
  cafe_fnb/
    __init__.py
    apps.py
    gateways.py       # OrderGateway: get(), get_amount_paid(), create(), list_orders()
                      # Resilience: circuit-breaker, retry (3x backoff), idempotency (_operation_id)
    views.py          # menu, create_order, get_order, list_orders
    serializers.py    # OrderCreateRequest, OrderResponse, OrderListResponse, MenuItemSerializer
    urls.py           # /api/v1/cafe-fnb/menu, /api/v1/cafe-fnb/orders, /api/v1/cafe-fnb/orders/create, /api/v1/cafe-fnb/orders/<id>
    migrations/       # __init__.py only — no PG models
```

**No models.py** — F&B data stays in MongoDB `kgorders` + `stock_register`. The domain is a gateway, not a new data store.

### Endpoint Changes

| Before (Planned) | After (Locked) | Status |
|-----------------|----------------|--------|
| `POST /cafe/sessions/<id>/food` | `POST /cafe-fnb/orders/create` (payload includes `session_id`) | ✅ Implemented |
| `GET /cafe-fnb/orders/<id>` | Lookup by orderid | ✅ Implemented |
| `GET /cafe-fnb/orders` | List with pagination + date filters | ✅ Implemented |
| `GET /cafe-fnb/menu` | Product catalog from stock_register | ✅ Stub (needs stock_register schema) |
| `Session.food_charges` accumulation | `Session.last_order_id` reference | ✅ Implemented (migration 0003) |
| Food charges in session end | `food_total = 0` when `last_order_id` set; `food_charges` fallback otherwise | ✅ Implemented (prevents double-count) |
| Full OrderGateway lookup in session_end | TODO: `OrderGateway.get(session.last_order_id).amount_paid` | ⏳ Pending (replaces `pass` in session_end) |

### Future Event Layer (Deferred)

**Trigger conditions for adding event/orchestration layer:**
- >5 cafe locations requiring real-time inventory sync
- Franchise model with centralized menu management
- Multiple payment providers requiring async webhook reconciliation
- Real-time analytics pipeline (revenue streaming, inventory forecasting)

**When triggered, add:**
- Event bus (reuse existing `plat/events/bus.py`)
- Domain events: `FnbOrderCompleted`, `InventoryUpdated`, `SessionCharged`
- Event handlers in each domain subscribing to events they care about
- Outbox pattern for durable event logging (reuse `plat/outbox/`)

**Note:** The lightweight path is fully refactorable into the event layer. Direct calls in `cafe-fnb/views.py` become event publishers. No data migration needed.

**Future Event Layer Implementation (when triggered):**
```
# Phase X — Event Layer (added when business demands)
1. Create domain events: FnbOrderCompleted, InventoryUpdated, SessionCharged
2. Replace direct calls in cafe-fnb/views.py with event_bus.publish()
3. Add event handlers in arcade-station/, wallet/, analytics/ domains
4. Wire plat/outbox/ for durable event logging
5. Add dead letter queue for failed event processing
6. Add event replay for debugging/reconciliation
```

---

## Open Questions / Decisions Needed

1. ~~**Eshop vs Products:**~~ ✅ **RESOLVED** — Keep separate. `domains/eshop/` = e-commerce (Cart, Wishlist, Addresslist, Orders, OrderItems). `domains/products/` = inventory/asset catalog. Council verdict 2026-05-13.
2. ~~**MongoClient per-request leak:**~~ ✅ **RESOLVED (2026-05-13)** — `get_collection()` uses singleton `get_mongo_client()`. Two remaining leak points patched: `users/api/viewsets.py:552` (health check) and `backend/views_diagnostic.py:33` (diagnostic view).
3. ~~**MongoDB field naming (`bgcode` vs `bg_code`):**~~ ✅ **RESOLVED (2026-05-13)** — Canonical: `bg_code`, `div_code`, `branch_code`. DB migration required for existing collections (Phase 5.7).
4. ~~**Session model: food_charges vs last_order_id**~~ ✅ **RESOLVED (2026-05-13)** — `last_order_id` added, `food_charges` kept as deprecated fallback. Drop in Phase 9.
5. ~~**cafe-fnb domain: create or defer**~~ ✅ **RESOLVED (2026-05-13)** — Created with OrderGateway (retry + circuit-breaker + idempotency).
6. **MongoDB strategy:** Keep PyMongo direct access or migrate to Django ORM for all models?
7. **Frontend:** What is the current frontend state? Is there a `kurogg-nextjs` or `kteam-fe-chief`?
8. **Deployment target:** Kubernetes (Helm) or docker-compose + systemd?
9. **Timeline:** 12 weeks assumed — is this realistic?
10. **Team size:** How many developers? Parallel workstreams?
11. **Data migration testing:** Do we have a staging DB with production-like data?
12. **kgorders schema:** What fields exist in production `kgorders`? `OrderGateway.create()` assumes `orderid`, `items`, `total`, `amount_paid`, `payment_status`, `session_id`, `started_by`, `created_at`, `updated_at`, `typeof`. Need to verify against actual documents.

**RESOLVED:**
- ~~Gaming domain location~~ → ✅ **DONE (2026-05-13)** — `rebellion/cafe/` → `domains/cafe_arcade/`, `rebellion/esports/` → `domains/tournaments/`, gamers split into `domains/cafe_arcade/gamers_views.py`, empty shells deleted
- ~~Cafe platform rename~~ → ✅ **DONE (2026-05-13)** — `domains/cafe/` + `domains/esports/` replaced with `domains/cafe_arcade/` + `domains/tournaments/`
- ~~Platform primitives exist?~~ → `plat/` verified on disk (2026-05-13) — all 7 modules implemented
- ~~`platform/` vs `plat/` naming~~ → `plat/` is the actual directory

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| MongoDB tenant filtering missed in some queries | High | Critical (data leak) | `TenantCollection` wrapper + code review |
| RBAC migration breaks existing permissions | Medium | High | Staging test with all user roles |
| Gaming WebSocket consumers break on domain move | Medium | Medium | Integration tests for WebSocket |
| Data migration loses rows | Low | Critical | Row count verification + rollback backup |
| Kuro Gaming users can't log in after auth merge | Medium | Critical | Auth testing with all user types |
| Outbox pattern not transactional | Medium | High | `transaction.on_commit` pattern |
| MeiliSearch index stale after migration | Low | Medium | Reindex command + event trigger |
| **cafe-fnb OrderGateway bypasses tenant filter** | Low | Critical (data leak) | ✅ Mitigated: all queries use `get_collection()` with `bg_code`/`div_code`/`branch_code` |
| **Session end fails if OrderGateway unavailable** | Low | Medium (incomplete billing) | ✅ Mitigated: `get()` returns `None` on failure → `food_total = 0`. Circuit-breaker prevents cascade. |
| **Legacy kgorders schema drift** | Medium | Medium (gateway breaks) | ✅ Mitigated: `get()` returns `None` for missing fields, logs error |
| **Dual-write inconsistency (PG vs Mongo)** | Medium | Medium (data drift) | ⏳ Open: `transaction.atomic()` only covers PG. OrderGateway Mongo writes outside PG transaction. Mitigation: `food_total = 0` when `last_order_id` set (no double-count). Full reconciliation job needed in Phase 2C. |
| **Zero test coverage for cafe_arcade** | High | High (silent breakage) | ⏳ Open: `tests/` is empty. First tests needed: `session_end()` concurrency, double-end protection, wallet deduction |
| **Mongo bloat — no TTL/cleanup for kgorders** | Medium | Medium (storage growth) | ⏳ Open: Council locked "no PG migration" but no data lifecycle policy. Add cleanup job in Phase 2C. |
| **WebSocket consumers are stubs** | Medium | Medium (features missing) | ⚠️ Noted: 10 handlers return `ack: True` only (session extend, stop, game launch/terminate). Implement in Phase 2C. |
| **rebellion/cafe/ rename breaks imports** | ✅ **DONE (2026-05-13)** — renamed to `domains/cafe_arcade/`, all imports updated | Verified: apps load, URLs resolve, models import |

---

## Appendix: File Inventory

### KungOS (kteam-dj-chief) — Key Files

| File | Purpose |
|------|---------|
| `backend/settings.py` | Django config (INSTALLED_APPS, MIDDLEWARE, REST_FRAMEWORK, DATABASES, MONGO_DB_URI) |
| `backend/urls.py` | URL routing (domain-first under /api/v1/, legacy root endpoints) |
| `backend/auth_utils.py` | Auth utilities (resolve_access, has_read_access, has_write_access) |
| `users/models.py` | CustomUser, KuroUser, Switchgroupmodel, Accesslevel, Permission, Role, UserRole, etc. |
| `users/cookie_auth.py` | CookieJWTAuthentication |
| `users/api/viewsets.py` | Auth, Register, User, AccessLevel viewsets |
| `users/api/rbac_views.py` | RBAC management views |
| `users/api/rbac_serializers.py` | RBAC serializers |
| `users/api/permissions.py` | Permission classes |
| `users/management/commands/migrate_mongodb_to_unified.py` | MongoDB migration command |
| `users/management/commands/reconcile_user_models.py` | User model reconciliation |
| `users/management/commands/seed_rbac_roles.py` | RBAC role seeding |
| `tenant/models.py` | BusinessGroup, Division, Branch, BankAccount |
| `tenant_api/urls.py` | Tenant API routing (business-groups, divisions, branches, bank-accounts) |
| `plat/outbox/models.py` | Outbox event model |
| `plat/outbox/service.py` | Outbox publishing service |
| `plat/outbox/worker.py` | Outbox background worker |
| `plat/events/bus.py` | Event bus (emit/on pattern) |
| `plat/events/types.py` | Event type definitions |
| `plat/observability/middleware.py` | CorrelationIDMiddleware, TenantContextMiddleware |
| `plat/observability/context.py` | Request context |
| `plat/observability/logging.py` | Structured logging |
| `plat/tenant/rls.py` | Row-level security utilities |
| `plat/tenant/verify.py` | Tenant verification |
| `plat/tenant/config.py` | Tenant configuration |
| `plat/tenant/collection.py` | TenantCollection MongoDB wrapper |
| `plat/health/views.py` | Health check views |
| `domains/*/viewsets.py` | Domain ViewSets (accounts, orders, products, vendors, teams, search, shared) |
| `domains/*/urls.py` | Domain URL routing |
| `domains/cafe_arcade/models.py` | Gaming models (14 models: Game, Station, MemberPlan, Pricing, Session, etc.) |
| `domains/cafe_arcade/serializers.py` | Gaming serializers |
| `domains/cafe_arcade/views.py` | Gaming views (sessions, stations, wallet, etc.) |
| `domains/cafe_arcade/gamers_views.py` | Gamer session tracking (gamers, getgamerfilters, getrebplayers, getpackages) |
| `domains/cafe_arcade/legacy_views.py` | Legacy MongoDB-based views (reborders, rbpackages, reb_users) |
| `domains/cafe_arcade/channels/consumers.py` | WebSocket consumers |
| `domains/cafe_arcade/management/commands/seed_*.py` | Gaming seed commands (4 commands) |
| `domains/cafe_fnb/gateways.py` | OrderGateway: get(), get_amount_paid(), create(), list_orders() + circuit-breaker + retry + idempotency |
| `domains/cafe_fnb/views.py` | F&B views: menu, create_order, get_order, list_orders |
| `domains/cafe_fnb/serializers.py` | F&B serializers: OrderCreateRequest, OrderResponse, OrderListResponse, MenuItemSerializer |
| `domains/cafe_fnb/urls.py` | F&B URL routing: /api/v1/cafe-fnb/ |
| `domains/tournaments/views.py` | Tournament views (tournaments, players, teams, tourneyregister) |
| `domains/tournaments/urls.py` | Tournament URL routing (registered via rebellion/urls.py) |
| `seed_permissions.py` | Permission seeding script |
| `docker-compose.yml` | Docker services (MongoDB, MeiliSearch) |
| `PRODUCTION_DEPLOYMENT.md` | Deployment guide |

### Kuro Gaming (kuro-gaming-dj-backend) — Key Files

| File | Purpose |
|------|---------|
| `backend/settings.py` | Django config (hardcoded AWS keys, Knox auth, djongo) |
| `backend/urls.py` | URL routing (flat apps under /api/) |
| `users/models.py` | CustomUser (AbstractBaseUser) |
| `users/authenticate.py` | CustomAuthenticationBackend (ModelBackend) |
| `users/serializers.py` | User serializers |
| `users/api.py` | User API |
| `accounts/models.py` | Cart, Wishlist, Addresslist |
| `orders/models.py` | Orders (30+ fields), OrderItems |
| `orders/serializers.py` | Order serializers |
| `products/models.py` | Empty stub (3 lines) |
| `games/models.py` | Empty stub (3 lines) |
| `payment/models.py` | Empty stub (3 lines) |
| `kuroadmin/models.py` | Admin models |
| `requirements.txt` | Dependencies (knox, djongo, Django 4.1.13) |
| `Pipfile` | Pipenv dependencies |
| `default-ip-*.psql` | PostgreSQL backup |
| `mongo-ip-*.dump` | MongoDB backup |

### Design Docs

| File | Purpose |
|------|---------|
| `~/llm-wiki/KungOS_v2.md` | Master modernization plan (Phase 0-4, platform primitives, outbox, event bus) |
| `~/llm-wiki/KungOS_Endpoint_Design.md` | API consolidation spec (domain-first routing, response contracts, RBAC, 11 domains) |
| `~/llm-wiki/access-level-design.md` | RBAC + Permission Matrix (40-col → normalized, Redis caching, tenant field rename) |
| `~/llm-wiki/kungos_v2_db.md` | Database reference (39 PostgreSQL tables, 30 MongoDB collections) |
| `~/llm-wiki/KungOS_v2.md` (in kteam-dj-chief) | Copy of master plan |

---

## Report Sources

| Report | Model | Path | Content |
|--------|-------|------|---------|
| Specialist-coder initial | Qwen3-Coder-30B | `~/.council-memory/reviews/deleg-1778603002/` | Shallow sweep (missed plat/ subdirs) |
| Builder attempt 1 | Qwen3.6-35B-A3B | `~/.council-memory/reviews/deleg-1778603642/` | Crashed (90 tokens, context budget) |
| Builder attempt 2 | Qwen3.6-35B-A3B | `~/.council-memory/reviews/deleg-1778603841/` | Crashed (38 tokens, context budget) |
| Nemo deep-audit | Nemotron-Cascade-2-30B | `~/.council-memory/reviews/deleg-1778604212/` | 8,028 tokens (single codebase) |
| Nemo integration | Nemotron-Cascade-2-30B | `~/.council-memory/reviews/deleg-1778604917/` | 5,544 tokens (two codebases, some hallucinations) |
| Nemo full-audit | Nemotron-Cascade-2-30B | `~/.council-memory/reviews/deleg-1778605508/` | 7,360 tokens (atomic plan, some hallucinations) |
| Nemo rename+split review | Nemotron-Cascade-2-30B | `~/.council-memory/reviews/deleg-1778667916/` | 3,374 tokens (hallucinated ViewSets, but structural assessment correct) |
| Gemma council review | Gemma-4-26B-A4B | `~/.council-memory/reviews/deleg-1778697234/` | 3,358 tokens (cafe-council TODO review, 5 findings: R1-R5) |
| GPT-OSS council review | GPT-OSS-20B | `~/.council-memory/reviews/deleg-1778697979/` | 60,214 tokens (cafe-council TODO review, 22 tool rounds, 8 findings: D1-D6 + alternatives) |
| Manual verification | Human | This document | Verified file paths, corrected hallucinations, applied rename+split, implemented Phase 2A/2B |

---

*Draft synthesized from 4 AI reports + manual verification. Needs review before execution.*