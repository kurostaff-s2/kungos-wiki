# KungOS Endpoint Contract Specification — Revised

**Status:** Spec — TARGET (locked)
**Date:** 2026-06-28
**Predecessor:** `endpoint_contract_spec.md` (2026-06-25)
**Authoritative references:** `multi_tenancy.md` (§JWT Claims, §Middleware Stack), `CANONICAL_NAMING.md`, `identity_layer.md`, `rbac_system.md`

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [URL Routing Rules](#2-url-routing-rules)
3. [Request/Response Contracts](#3-requestresponse-contracts)
4. [Authentication & Authorization](#4-authentication--authorization)
5. [Tenant Context Rules](#5-tenant-context-rules)
6. [Domain Specifications](#6-domain-specifications)
7. [Migration Mapping](#7-migration-mapping)
8. [Error Handling](#8-error-handling)
9. [Pagination & Filtering](#9-pagination--filtering)
10. [Versioning Strategy](#10-versioning-strategy)
11. [Compatibility Matrix](#11-compatibility-matrix)
12. [OpenAPI Contract](#12-openapi-contract)

---

## 1. Design Principles

### 1.1 Core Rules (from Legacy + Target Alignment)

| Rule | Description | Enforcement |
|---|---|---|
| **Domain-first routing** | URLs begin with domain namespace (`/users/`, `/cafe/`, `/eshop/`, `/tournaments/`) | URL conf structure |
| **Versioned prefix** | All API routes under `/api/v1/` | Root URL conf |
| **Noun-based resources** | `/api/v1/users/me`, not `/api/v1/getMyUser` | Naming convention |
| **Action sub-paths** | `/api/v1/cafe/sessions/{id}/end`, not `POST /sessions?action=end` | REST convention |
| **Tenant-scoped data** | All queries filter by `bg_code`/`div_code` from tenant context | Middleware + DB constraints |
| **Unified identity** | All person references via `identity_id`, not `userid`/`phone` | FK constraints |
| **RBAC over Accesslevel** | Permissions via `rbac_*` tables, not `users_accesslevel` | Middleware |
| **Outbox for cross-store** | PostgreSQL → MongoDB writes via outbox events | `transaction.on_commit` |

### 1.2 Shared Domain Namespaces

| Namespace | Domain | Package | Description |
|---|---|---|---|
| `/auth/` | Authentication | `users/` | Login, OTP, session management |
| `/users/` | Identity | `users/` | Identity CRUD, lookup, extensions |
| `/tenant/` | Multi-tenancy | `tenant/` | BG, division, branch management |
| `/rbac/` | RBAC | `users/` | Roles, permissions, assignments |
| `/cafe/` | Cafe (arcade) | `domains.cafe_arcade.urls` | Sessions, stations, wallet, pricing |
| `/cafe-fnb/` | Cafe (F&B) | `domains.cafe_fnb.urls` | F&B orders, menu |
| `/eshop/` | E-Commerce | `domains.eshop.urls` | Products, cart, orders, payments |
| `/tournaments/` | Tournaments | `domains/tournaments/` | Tournaments, players, teams |
| `/admin/` | Cross-cutting | `admin/` | Admin-only operations |

---

## 2. URL Routing Rules

### 2.1 Root URL Structure

```python
# urls.py (root)
urlpatterns = [
    path('api/v1/', include([
        # Auth
        path('auth/', include('users.api.auth_urls')),

        # Identity
        path('users/', include('users.urls')),

        # Multi-tenancy
        path('tenant/', include('tenant_api.urls')),

        # RBAC
        path('rbac/', include('users.rbac_urls')),

        # Accounts — finance (invoices, payments, financials)
        path('accounts/', include('domains.accounts.urls')),

        # Orders (estimates, TP, KG, service)
        path('orders/', include('domains.orders.urls')),

        # Products (catalog, assets)
        path('products/', include('domains.products.urls')),

        # Inventory (stock, audit, assets, indents)
        path('inventory/', include('domains.inventory.urls')),

        # E-Commerce
        path('eshop/', include('domains.eshop.urls')),

        # Vendors
        path('vendors/', include('domains.vendors.urls')),

        # Teams (employees, attendance, payroll)
        path('teams/', include('domains.teams.urls')),

        # Search (MeiliSearch)
        path('search/', include('domains.search.urls')),

        # Shared (cross-domain utilities)
        path('shared/', include('domains.shared.urls')),

        # Cafe — arcade (sessions, stations, wallet, pricing)
        path('cafe/', include('domains.cafe_arcade.urls')),

        # Cafe — F&B (orders, menu)
        path('cafe-fnb/', include('domains.cafe_fnb.urls')),

        # Tournaments
        path('tournaments/', include('domains/tournaments/urls')),

        # Careers
        path('careers/', include('careers.urls')),

        # Admin (cross-domain)
        path('admin/', include('kungos_admin.urls'))
    ])),
]
```

### 2.2 Route Naming Convention

```
/api/v1/{domain}/{resource}[/{id}][/{action}]
```

- **domain**: namespace (`users`, `cafe`, `eshop`, `tournaments`)
- **resource**: plural noun (`sessions`, `stations`, `orders`)
- **id**: resource identifier (path parameter)
- **action**: noun-like action (`end`, `topup`, `register`) — only when not covered by HTTP method

### 2.3 HTTP Method Mapping

| Method | Use | Example |
|---|---|---|
| `GET` | List or retrieve | `GET /api/v1/cafe/sessions` |
| `POST` | Create or trigger action | `POST /api/v1/cafe/sessions/{id}/end` |
| `PATCH` | Partial update | `PATCH /api/v1/users/identity/{id}` |
| `PUT` | Full replace (rare) | — |
| `DELETE` | Remove (soft delete preferred) | `DELETE /api/v1/eshop/cart/{id}` |

---

## 3. Request/Response Contracts

### 3.1 Standard Response Envelope

```json
{
    "status": "success",
    "data": { ... },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

**Error envelope:**
```json
{
    "status": "error",
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Phone number is required",
        "details": [
            {"field": "phone", "issue": "required"}
        ]
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

### 3.2 Pagination Response

```json
{
    "status": "success",
    "data": [ ... ],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total_items": 150,
        "total_pages": 8,
        "has_next": true,
        "has_prev": false
    },
    "meta": { ... }
}
```

### 3.3 List Query Parameters

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | `1` | Page number (1-indexed) |
| `page_size` | int | `20` | Items per page (max 100) |
| `sort` | string | `created_at` | Sort field (prefix `-` for desc) |
| `filter[field]` | string | — | Exact match filter |
| `search` | string | — | Full-text search on name/phone |

---

## 4. Authentication & Authorization

### 4.1 Auth Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Login (phone + password) | None |
| `POST` | `/api/v1/auth/otp/send` | Send OTP | None |
| `POST` | `/api/v1/auth/otp/verify` | Verify OTP | None |
| `POST` | `/api/v1/auth/refresh` | Refresh JWT | Refresh token |
| `POST` | `/api/v1/auth/logout` | Invalidate session | JWT |
| `GET` | `/api/v1/auth/me` | Current session info (alias for `/users/me/`) | JWT |

### 4.1.1 Header Naming Convention

| Header | Purpose | Canonical Name |
|---|---|---|
| Request/Response ID | Correlation ID for tracing | `X-Request-ID` |
| Token | JWT access token | `Authorization: Bearer <access_token>` |
| Refresh Token | Sliding refresh token (cookie) | `refresh_token` (cookie) |

**Note:** Spec previously referenced `X-Correlation-ID` but canonical name is `X-Request-ID` (matches implementation).

### 4.2 Login Response Contract

**Target:**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "identity_id": "ID000001",
            "phone": "+919876543210",
            "name": "John Doe",
            "email": "john@example.com",
            "bg_code": "KURO0001",
            "div_codes": ["KURO0001_001", "KURO0001_002"],
            "branch_codes": ["KURO0001_001_001"],
            "active_div_code": "KURO0001_001",
            "active_branch_code": "KURO0001_001_001",
            "scope": "division",
            "roles": ["employee", "customer"],
            "permissions": ["users.view", "orders.create"],
            "is_admin": false
        }
    }
}
```

**Mandatory fields:** The login response MUST include ALL of the following fields:
- `identity_id` (string) — stable person PK
- `bg_code` (string) — active business group
- `div_codes` (array[string]) — all accessible division codes
- `branch_codes` (array[string]) — all accessible branch codes
- `active_div_code` (string) — current active division
- `active_branch_code` (string \| null) — current active branch
- `scope` (string) — scope level: `'full'` \| `'division'` \| `'branch'`
- `roles` (array[string]) — derived from extensions
- `permissions` (object) — RBAC permissions keyed by code with levels: `{ "code": { level: N, bg_code: "..." }, ... }`

**Refresh token delivery:** The refresh token is delivered ONLY as an HttpOnly cookie (`refresh_token`). It is NOT included in the JSON response body to prevent XSS exposure. The frontend MUST use the cookie for token refresh requests.

**JWT alignment:** The fields in the login response MUST match the JWT claims defined in `multi_tenancy.md` §JWT Claims. The JWT is generated from the same data — the login response is the human-readable representation of the JWT payload.

**Active-context convention:** `div_codes[0]` is always the active division. `branch_codes[0]` is always the active branch. The JWT claims `active_div_code` and `active_branch_code` are explicit aliases for `div_codes[0]` and `branch_codes[0]` — they MUST always be equal.

**Invariant:** `active_div_code == div_codes[0]` and `active_branch_code == branch_codes[0]` MUST hold at all times. If they diverge, the JWT is stale and must be regenerated.

### 4.3 Auth Migration Notes

| Legacy Field | Target Field | Change |
|---|---|---|
| `user.userid` | `user.identity_id` | New PK format |
| `user.phone` (raw) | `user.phone` (E.164) | Normalized |
| `user.bg_code` | `user.bg_code` | Unchanged |
| `user.division[]` | `user.div_codes[]` | Renamed (canonical) |
| `user.branches[]` | `user.branch_codes[]` | Renamed (canonical) |
| — | `user.active_div_code` | Added (was `entity[0]`) |
| — | `user.active_branch_code` | Added (was `branches[0]`) |
| — | `user.scope` | Added |
| `user.accesslevel[]` | `user.permissions{}` | RBAC perm_codes with levels |
| — | `user.roles[]` | Derived from extensions |
| — | `refresh_token` | Added (sliding refresh) |

### 4.4 RBAC Authorization Flow

```
Request arrives
       │
       ▼
JWT decoded → identity_id + tenant context (bg_code, div_code)
       │
       ▼
resolve_permission(identity_id, perm_code, bg_code, div_code)
       │
       ├── Exact division match (level N)
       ├── BG-wide match (level N-1)
       ├── Global match (level N-2)
       └── DENY (default)
       │
       ▼
Level >= required? → ALLOW / DENY
```

---

## 5. Tenant Context Rules

### 5.1 Context Injection — Extraction Contract

**Authority:** The JWT is the authoritative source of tenant context for every request. All request-time tenant context resolution MUST read from the JWT.

### Exception: Public and HMAC-Authenticated Endpoints

| Endpoint Type | Auth Method | Tenant Resolution |
|---------------|-------------|-------------------|
| **Public catalog endpoints** (e.g., `/cafe/games`, `/cafe/price-plans`, `/eshop/products`, `/tournaments/`) | None (no auth) | Tenant context is **not required** — these endpoints return BG-scoped data filtered by query params or are genuinely public |
| **HMAC-authenticated webhooks** (e.g., `/eshop/payment/webhook`) | HMAC signature verification | Tenant context is resolved from the **payment/order record**, NOT from `request.auth` |

**Webhook tenant-resolution contract:**
1. Verify HMAC signature using shared secret
2. Extract tenant context from the payment/order record in the payload (e.g., `bg_code`, `div_code` from the order)
3. Set ContextVar from the extracted tenant context
4. Process the webhook with the resolved tenant context
5. If tenant context cannot be resolved from the payload: return HTTP 400 with `TENANT_CONTEXT_MISSING`

**FORBIDDEN:** Webhook handlers MUST NOT read tenant context from `request.auth` or JWT claims — webhooks are not JWT-authenticated.

**Middleware extraction contract (MUST use these exact claim names):**

```python
# TenantContextMiddleware.process_request
bg_code = token.get("bg_code")
div_codes = token.get("div_codes", [])
branch_codes = token.get("branch_codes", [])
active_div_code = token.get("active_div_code", "")
active_branch_code = token.get("active_branch_code", "")
identity_id = token.get("identity_id", "")
scope = token.get("scope", "full")
```

**ContextVar population (MUST use these exact keys):**

```python
set_tenant_context({
    "bg_code": bg_code,
    "div_codes": div_codes,
    "branch_codes": branch_codes,
    "active_div_code": active_div_code,
    "active_branch_code": active_branch_code,
    "identity_id": identity_id,
    "scope": scope,
})
```

**Session variables (MUST set on every request):**

| Variable | Source | Purpose |
|----------|--------|---------|
| `app.current_bg_code` | `bg_code` | Tenant scope (required) |
| `app.current_division` | `active_div_code` | Active division (singular) |
| `app.current_branch` | `active_branch_code` | Active branch (singular) |
| `app.current_userid` | `identity_id` | User identity |

**Error behavior:**
- If `bg_code` is missing or empty: raise `TenantContextMissing`, return HTTP 401
- If `identity_id` is missing or empty: raise `TenantContextMissing`, return HTTP 401
- If `div_codes` or `branch_codes` is missing: set to empty list (non-blocking)

**FORBIDDEN:** The middleware MUST NOT read legacy field names from the JWT:
- `entity` (legacy middleware field — JWT has `div_codes`)
- `branches` (legacy middleware field — JWT has `branch_codes`)
- `userid` (legacy middleware field — JWT has `identity_id`)

**TenantCollection extraction contract (MUST use these exact keys):**

```python
# plat/tenant/collection.py
bg_code = ctx.get("bg_code")
div_codes = ctx.get("div_codes", [])
branch_codes = ctx.get("branch_codes", [])
```

**FORBIDDEN:** TenantCollection MUST NOT read legacy keys from the ContextVar:
- `entity` (legacy ContextVar key — should use `div_codes`)
- `branches` (legacy ContextVar key — should use `branch_codes`)

### 5.2 Query Scoping Rules

| Scope | Query Filter | Example |
|---|---|---|
| `full` | `bg_code = X` | BG admin sees all divisions |
| `division` | `bg_code = X AND div_code IN (div_codes)` | Division manager |
| `branch` | `bg_code = X AND div_code = Y AND branch_code IN (branch_codes)` | Branch staff |

**Note:** The `div_codes` and `branch_codes` arrays come from the JWT (via ContextVar). The active division/branch come from `active_div_code` and `active_branch_code`.

### 5.3 Tenant Switching — JWT Emission Requirement

**POST /api/v1/tenant/switch/** MUST:

1. Validate the requested `bg_code` against the user's `Identity`
2. Update `UserTenantContext` with new `bg_code`, `div_codes`, `branch_codes`, `scope`, `active_div_code`, `active_branch_code`
3. Generate a **new JWT** with updated canonical claims (per `multi_tenancy.md` §JWT Claims)
4. Set the new JWT as an HttpOnly cookie
5. Return the response envelope with updated context data

**Response schema (MUST include all fields):**

```json
{
    "status": "success",
    "data": {
        "bg_code": "KURO0002",
        "div_codes": ["KURO0002_001", "KURO0002_002"],
        "branch_codes": ["KURO0002_001_001"],
        "active_div_code": "KURO0002_001",
        "active_branch_code": "KURO0002_001_001",
        "scope": "division",
        "identity_id": "ID000001"
    }
}
```

**JWT generation:** The switch endpoint MUST call `generate_tenant_token()` (from `users/tenant_tokens.py`) after updating `UserTenantContext`. The new JWT MUST contain all canonical claims: `bg_code`, `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `identity_id`, `scope`.

**Cookie handling:** The new JWT MUST be set as an HttpOnly cookie with the same cookie name as the original JWT. The cookie MUST have the same security attributes (same domain, path, secure flag, same-origin policy).

**Legacy endpoint:** The legacy `/api/v1/users/bgswitch/` endpoint (in `users/views.py`) has the same requirement — it MUST generate a new JWT. However, this endpoint is deprecated and will be removed. See §11.1.

### 5.4 Frontend Tenant Switching Contract

**The frontend MUST:**

1. Call `POST /api/v1/tenant/switch/` when the user changes BG/division/branch
2. Include the new context in the request body (see schema below)
3. Process the new JWT cookie set by the response
4. Update local state (React context + localStorage) with the response data
5. **NOT** switch tenant context via local state alone (backend MUST be notified)

**Request body schema:**
```json
{
    "bg_code": "KURO0002",
    "active_div_code": "KURO0002_001",
    "active_branch_code": "KURO0002_001_001"
}
```

**Rationale:** If the frontend switches tenant context locally without calling the backend, the backend has no record of the change. Subsequent API calls use the stale JWT, which carries the old tenant context. This causes:
- Server-side filtering (RLS, MongoDB TenantCollection, `resolve_access`) uses stale DB state
- Cross-tenant data leakage (user sees data from old tenant)
- Inconsistency between frontend and backend state

**Implementation note:** The `TenantSelector` component passes an `onSwitchTenant` callback to its parent. The parent (e.g., `AppLayout.jsx`) MUST call the backend switch endpoint within this callback. Updating local state alone is insufficient.

### 5.5 UserTenantContext Model

The `UserTenantContext` model (`users/models.py`) tracks the active tenant scope for each user session:

```
UserTenantContext
├── userid          — the user (FK → CustomUser.userid)
├── bg_code         — current business group
├── div_codes       — JSON list of accessible division codes
├── branch_codes    — JSON list of accessible branch codes
├── token_key       — JWT token for the session (deprecated — see P3-2 in audit)
└── scope           — 'full' | 'division' | 'branch'
```

**Derived properties (not model fields):**
- `active_div_code` — derived from `div_codes[0]`
- `active_branch_code` — derived from `branch_codes[0]`

**Field names:** The Django model uses `div_codes` and `branch_codes` (canonical). Legacy field names (`division`, `branches`) are NOT used in the model.

**Update semantics:** `UserTenantContext` is created on login and updated by tenant switch endpoints. The JWT is the authoritative source — `UserTenantContext` is the persistence layer.

**Relationship to JWT:**
- The JWT is regenerated on every switch endpoint call
- The JWT claims are derived from `UserTenantContext` at generation time
- The JWT is the request-time source of truth
- `UserTenantContext` is the persistence layer — read by `resolve_access` as fallback when JWT is unavailable

---

## 6. Domain Specifications

### 6.1 Identity Domain (`/api/v1/users/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/users/me` | Current user identity + extensions | JWT |
| `GET` | `/users/lookup?phone=+91...` | Lookup identity by phone | JWT |
| `POST` | `/users/identity` | Create identity (walk-in) | JWT |
| `PATCH` | `/users/identity/{id}` | Update identity | JWT |
| `GET` | `/users/{id}` | Get identity by ID | JWT |
| `GET` | `/users/{id}/employee` | Employee extension | JWT |
| `GET` | `/users/{id}/customer` | Customer extension | JWT |
| `GET` | `/users/{id}/player` | Player extension | JWT |

**`GET /users/me` response:**
```json
{
    "status": "success",
    "data": {
        "identity_id": "ID000001",
        "phone": "+919876543210",
        "name": "John Doe",
        "email": "john@example.com",
        "bg_code": "KURO0001",
        "active_div_code": "KURO0001_001",
        "active_branch_code": null,
        "status": "active",
        "roles": ["employee", "customer"],
        "primary_role": "employee",
        "employee_profile": {
            "userid": "KCTM006",
            "role": "tech",
            "department": "Engineering"
        },
        "customer_profile": {
            "registered": true,
            "order_count": 15,
            "total_spent": 25000.00
        }
    }
}
```

**Maturity rule:** `employee_profile`, `customer_profile`, `player_profile` are **nullable/absent until M1 data backfill completes**. Return `null` or omit — do not fabricate empty objects. Data availability follows migration timing (`migration_spec.md` Phase 4).

### 6.2 Accounts — Finance (`/api/v1/accounts/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/accounts/inward-invoices` | List inward (purchase) invoices | JWT |
| `POST` | `/accounts/inward-invoices` | Create inward invoice | JWT |
| `GET` | `/accounts/inward-invoices/{id}` | Invoice detail | JWT |
| `PATCH` | `/accounts/inward-invoices/{id}` | Update invoice | JWT |
| `DELETE` | `/accounts/inward-invoices/{id}` | Delete invoice | JWT |
| `GET` | `/accounts/outward-invoices` | List outward (sales) invoices | JWT |
| `POST` | `/accounts/outward-invoices` | Create outward invoice | JWT |
| `GET` | `/accounts/outward-credit-notes` | List credit notes issued | JWT |
| `GET` | `/accounts/outward-invoices/{id}` | Invoice detail | JWT |
| `PATCH` | `/accounts/outward-invoices/{id}` | Update invoice | JWT |
| `DELETE` | `/accounts/outward-invoices/{id}` | Delete invoice | JWT |
| `GET` | `/accounts/inward-payments` | List inward payments | JWT |
| `POST` | `/accounts/inward-payments` | Create inward payment | JWT |
| `GET` | `/accounts/outward-payments` | List outward payments | JWT |
| `POST` | `/accounts/outward-payments` | Create outward payment | JWT |
| `GET` | `/accounts/payment-vouchers` | List payment vouchers | JWT |
| `POST` | `/accounts/payment-vouchers` | Create payment voucher | JWT |
| `GET` | `/accounts/purchase-orders` | List purchase orders | JWT |
| `POST` | `/accounts/purchase-orders` | Create purchase order | JWT |
| `GET` | `/accounts/outward-debit-notes` | List debit notes issued | JWT |
| `POST` | `/accounts/outward-debit-notes` | Create debit note | JWT |
| `GET` | `/accounts/inward-credit-notes` | List credit notes received | JWT |
| `POST` | `/accounts/inward-credit-notes` | Create credit note | JWT |
| `GET` | `/accounts/inward-debit-notes` | List debit notes received | JWT |
| `POST` | `/accounts/inward-debit-notes` | Create debit note | JWT |
| `GET` | `/accounts/accounts` | List sundry accounts | JWT |
| `POST` | `/accounts/accounts` | Create account | JWT |
| `GET` | `/accounts/partners` | List partners | JWT |
| `POST` | `/accounts/partners` | Create partner | JWT |
| `GET` | `/accounts/banks` | List bank accounts | JWT |
| `POST` | `/accounts/banks` | Create bank account | JWT |
| `GET` | `/accounts/loans` | List loans | JWT |
| `POST` | `/accounts/loans` | Create loan | JWT |
| `GET` | `/accounts/financials` | Financial position summary | JWT |
| `GET` | `/accounts/balance-sheet` | Balance sheet report | JWT |
| `GET` | `/accounts/profit-loss` | Profit & loss statement | JWT |
| `GET` | `/accounts/revenue` | Revenue/sales report | JWT |
| `GET` | `/accounts/expenditure` | Expenditure/purchase report | JWT |
| `GET` | `/accounts/itc-gst` | ITC & GST reporting | JWT |
| `POST` | `/accounts/bulk-payments` | Process bulk payments | JWT |
| `GET` | `/accounts/analytics` | Financial analytics | JWT |
| `GET` | `/accounts/settlements` | Settlements | JWT |
| `GET` | `/accounts/export/inward-invoices` | Export inward invoices (CSV/PDF) | JWT |
| `GET` | `/accounts/export/outward-invoices` | Export outward invoices (CSV/PDF) | JWT |
| `GET` | `/accounts/export/inward-payments` | Export inward payments (CSV/PDF) | JWT |

**Canonical naming convention:**
- `inward-invoices` (not `purchase-invoices`) — accounting terminology
- `outward-invoices` (not `sales-invoices`) — accounting terminology
- `inward-payments` / `outward-payments` — consistent with invoice naming
- `outward-credit-notes` / `inward-credit-notes` — direction-based
- `outward-debit-notes` / `inward-debit-notes` — direction-based

### 6.3 Cafe — Arcade (`/api/v1/cafe/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/cafe/sessions` | List sessions | JWT |
| `POST` | `/cafe/sessions` | Create session | JWT |
| `GET` | `/cafe/sessions/{id}` | Session detail | JWT |
| `POST` | `/cafe/sessions/{id}/end` | End session | JWT |
| `GET` | `/cafe/stations` | List stations | JWT |
| `GET` | `/cafe/stations/{id}` | Station detail | JWT |
| `POST` | `/cafe/stations/{id}/command` | Station command | JWT |
| `GET` | `/cafe/wallet` | Wallet balance | JWT |
| `POST` | `/cafe/wallet/topup` | Wallet top-up | JWT |
| `GET` | `/cafe/wallet/transactions` | Transaction history | JWT |
| `GET` | `/cafe/games` | Game catalog | Public |
| `GET` | `/cafe/price-plans` | Price plans | Public |
| `GET` | `/cafe/member-plans` | Member plans | Public |

### 6.4 Cafe — F&B (`/api/v1/cafe-fnb/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/cafe-fnb/menu` | Menu items | Public |
| `POST` | `/cafe-fnb/orders` | Create order | JWT |
| `GET` | `/cafe-fnb/orders/{id}` | Order detail | JWT |

### 6.5 E-Commerce (`/api/v1/eshop/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/eshop/products` | Product catalog | Public |
| `GET` | `/eshop/products/{id}` | Product detail | Public |
| `GET` | `/eshop/cart` | Current user cart | JWT |
| `POST` | `/eshop/cart` | Add to cart | JWT |
| `PATCH` | `/eshop/cart/{id}` | Update cart item | JWT |
| `DELETE` | `/eshop/cart/{id}` | Remove cart item | JWT |
| `GET` | `/eshop/wishlist` | Current user wishlist | JWT |
| `POST` | `/eshop/wishlist` | Add to wishlist | JWT |
| `GET` | `/eshop/addresses` | User addresses | JWT |
| `POST` | `/eshop/addresses` | Create address | JWT |
| `PATCH` | `/eshop/addresses/{id}` | Update address (clone if used) | JWT |
| `POST` | `/eshop/checkout` | Create order | JWT |
| `GET` | `/eshop/orders` | User orders | JWT |
| `GET` | `/eshop/orders/{id}` | Order detail | JWT |
| `POST` | `/eshop/payment/initiate` | Initiate payment | JWT |
| `POST` | `/eshop/payment/webhook` | Cashfree webhook | HMAC |
| `GET` | `/eshop/payment/upi-qr` | Generate UPI QR | JWT |

### 6.6 Tournaments (`/api/v1/tournaments/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/tournaments/` | List tournaments | Public |
| `GET` | `/tournaments/{id}` | Tournament detail | Public |
| `POST` | `/tournaments/{id}/register` | Team registration | JWT |
| `GET` | `/tournaments/players/{id}` | Player detail | JWT |
| `GET` | `/tournaments/teams/{id}` | Team detail | Public |
| `GET` | `/tournaments/games` | Game catalog | Public |
| `GET` | `/tournaments/products` | Product catalog | Public |
| `GET` | `/tournaments/builds` | PC builds | Public |

### 6.7 Inventory (`/api/v1/inventory/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/inventory/stock` | Stock register | JWT |
| `POST` | `/inventory/stock` | Create stock entry | JWT |
| `PATCH` | `/inventory/stock/{id}` | Update stock entry | JWT |
| `GET` | `/inventory/stock-audit` | Stock audit trail | JWT |
| `POST` | `/inventory/stock-audit` | Create audit entry | JWT |
| `GET` | `/inventory/assets` | Asset tracking | JWT |
| `POST` | `/inventory/assets` | Create asset | JWT |
| `PATCH` | `/inventory/assets/{id}` | Update asset | JWT |
| `GET` | `/inventory/indents` | Indent management | JWT |
| `POST` | `/inventory/indents` | Create indent | JWT |
| `PATCH` | `/inventory/indents/{id}` | Update indent | JWT |
| `POST` | `/inventory/indents/{id}/approve` | Approve indent | JWT |
| `GET` | `/inventory/purchase-orders` | Purchase orders (inventory view) | JWT |
| `POST` | `/inventory/purchase-orders` | Create purchase order | JWT |
| `GET` | `/inventory/outward` | List outward entries (stock dispatch) | JWT |
| `POST` | `/inventory/outward` | Create outward entry (stock dispatch) | JWT |

**Note:** `outward` = inventory stock outflow (serials marked as sold/dispatched). Distinct from `outward-invoices` in accounts (sales invoices). Permission: `inventory.outward`.

---

## 7. Migration Mapping

### 7.1 Legacy → Target Endpoint Mapping

| Legacy Endpoint | Target Endpoint | Change |
|---|---|---|
| `POST /api/v1/auth/login` | `POST /api/v1/auth/login` | Response shape changed (see §4.3) |
| `GET /api/v1/kuro/user` | `GET /api/v1/users/me` | Path renamed, identity-based |
| `GET /api/v1/kuro/user/{userid}` | `GET /api/v1/users/{identity_id}` | ID format changed |
| `GET /api/v1/kuro/lookup?phone=X` | `GET /api/v1/users/lookup?phone=+91X` | Phone normalized |
| `POST /api/v1/cafe/sessions/start` | `POST /api/v1/cafe/sessions` | Action → POST on collection |
| `POST /api/v1/cafe/sessions/{id}/end` | `POST /api/v1/cafe/sessions/{id}/end` | Unchanged |
| `GET /api/v1/cafe/sessions?cafe_id=X` | `GET /api/v1/cafe/sessions?filter[cafe_id]=X` | Filter param format |
| `POST /api/v1/cafe/sessions/{id}/food` | `POST /api/v1/cafe-fnb/orders` | Moved to F&B domain |
| `GET /api/v1/eshop/cart` | `GET /api/v1/eshop/cart` | Unchanged (user → identity FK) |
| `POST /api/v1/eshop/checkout` | `POST /api/v1/eshop/checkout` | Unchanged (user → identity FK) |
| `GET /api/v1/tournaments/tournaments` | `GET /api/v1/tournaments/` | Path cleaned |
| `GET /api/v1/tournaments/players` | `GET /api/v1/tournaments/players/` | Path normalized |
| `POST /api/v1/tournaments/tourneyregister` | `POST /api/v1/tournaments/{id}/register` | RESTful path |
| `GET /api/v1/accounts/sales-invoices` | `GET /api/v1/accounts/outward-invoices` | Canonical accounting terminology |
| `GET /api/v1/accounts/purchase-invoices` | `GET /api/v1/accounts/inward-invoices` | Canonical accounting terminology |
| `GET /api/v1/products/inventory/stock` | `GET /api/v1/inventory/stock` | Inventory is separate domain |
| `GET /api/v1/accounts/outward` (legacy) | `GET /api/v1/inventory/outward` | Outward entries are inventory ops, not accounts |

### 7.2 Legacy → Target Field Mapping (Frontend Contract)

| Legacy Response Path | Target Response Path | Change |
|---|---|---|
| `res.data.user.userid` | `res.data.user.identity_id` | New PK |
| `res.data.user.phone` (raw) | `res.data.user.phone` (E.164) | Normalized |
| `res.data.user.businessgroups[]` | `res.data.user.bg_code` | Single BG from tenant context |
| `res.data.user.accesslevel[]` | `res.data.user.permissions{}` | RBAC perm_codes with levels |
| `res.data.user.roles` (JSON) | `res.data.user.roles[]` | Derived from extensions |
| `res.data.user.primary_bg` | `res.data.user.bg_code` | From tenant context |
| — | `res.data.user.div_codes[]` | Added (was `division[]`) |
| — | `res.data.user.branch_codes[]` | Added (was `branches[]`) |
| — | `res.data.user.active_div_code` | Added (was `entity[0]`) |
| — | `res.data.user.active_branch_code` | Added (was `branches[0]`) |
| — | `res.data.user.scope` | Added |
| `res.data.user.employee.*` | `res.data.user.employee_profile.*` | Nested extension |
| `res.data.user.customer.*` | `res.data.user.customer_profile.*` | Nested extension |
| `session.food_charges` | `session.last_order_id` | Reference, not amount |
| `wallet.customer_id` | `wallet.identity_id` | FK target changed |
| `address.user_id` | `address.identity_id` | FK target changed |
| `cart.user_id` | `cart.user_id` | Same name, FK → `users_identity` |
| `order.user_id` | `order.customer_id` | Renamed, FK → `users_identity` |

### 7.3 Frontend Transition Strategy

**Target state:** The locked target contract uses canonical names exclusively. No legacy field names in the target response.

**Migration guidance:** Dual-mode response (returning both legacy and target fields) is a migration-phase tactic, not a target-state feature. See `migration_spec.md` for transition strategy. Do not implement dual-mode in target-state code.

---

## 8. Error Handling

### 8.1 Standard Error Codes

| Code | HTTP Status | Description |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Request body/validation failed |
| `AUTH_REQUIRED` | 401 | No valid authentication |
| `AUTH_EXPIRED` | 401 | JWT token expired |
| `PERMISSION_DENIED` | 403 | Insufficient RBAC permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `TENANT_ISOLATION` | 403 | Cross-tenant data access attempt |
| `TENANT_CONTEXT_MISSING` | 401 | Middleware failed to extract tenant context from JWT |
| `CONFLICT` | 409 | Resource conflict (e.g., duplicate phone) |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unhandled server error |
| `SERVICE_UNAVAILABLE` | 503 | Downstream service unavailable |

### 8.2 Error Response Format

```json
{
    "status": "error",
    "error": {
        "code": "PERMISSION_DENIED",
        "message": "You do not have permission to view this resource",
        "details": {
            "required_permission": "users.view",
            "tenant_scope": "division"
        }
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

### 8.3 Tenant Isolation Errors

When a query attempts cross-tenant access:
```json
{
    "status": "error",
    "error": {
        "code": "TENANT_ISOLATION",
        "message": "Resource belongs to a different tenant",
        "details": {
            "requested_bg_code": "KURO0002",
            "current_bg_code": "KURO0001"
        }
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

### 8.4 Tenant Context Missing Error

When the middleware cannot extract tenant context from the JWT:
```json
{
    "status": "error",
    "error": {
        "code": "TENANT_CONTEXT_MISSING",
        "message": "Tenant context could not be resolved from JWT",
        "details": {
            "missing_claims": ["bg_code", "identity_id"]
        }
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

---

## 9. Pagination & Filtering

### 9.1 Pagination Convention

- **Cursor-based** for large/unbounded lists (sessions, transactions, orders)
- **Offset-based** for bounded/admin lists (users, roles, stations)

| Type | Params | Response |
|---|---|---|
| Offset | `page`, `page_size` | `pagination.total_items`, `total_pages` |
| Cursor | `cursor`, `limit` | `pagination.next_cursor`, `has_more` |

### 9.2 Filtering Convention

```
GET /api/v1/cafe/sessions?filter[status]=active&filter[cafe_id]=5&sort=-start_time
```

| Pattern | Meaning |
|---|---|---|
| `filter[field]=value` | Exact match |
| `filter[field__gte]=value` | Greater than or equal |
| `filter[field__lte]=value` | Less than or equal |
| `filter[field__in]=a,b,c` | In list |
| `search=query` | Full-text on name/phone fields |
| `sort=field` | Ascending sort |
| `sort=-field` | Descending sort |

---

## 10. Versioning Strategy

### 10.1 URL Versioning

- Current: `/api/v1/`
- All new endpoints under v1
- Breaking changes → v2 (not v1 patch)

### 10.2 Backward Compatibility Rules

| Change Type | Compatible? | Action |
|---|---|---|
| Add new endpoint | ✅ | Add to v1 |
| Add new response field | ✅ | Add to v1 |
| Remove response field | ❌ | Bump to v2 |
| Rename response field | ❌ | Return both (adapter) → v2 removes old |
| Change field type | ❌ | Bump to v2 |
| Add optional request param | ✅ | Add to v1 |
| Make optional param required | ❌ | Bump to v2 |

### 10.3 Deprecation Header

When a v1 endpoint will change in v2:
```
Deprecation: true
Sunset: Sat, 01 Jan 2027 00:00:00 GMT
Link: </api/v2/users/me>; rel="successor-version"
```

---

## 11. Compatibility Matrix

### 11.1 Legacy → Canonical Field Mapping

| Legacy Field/Claim | Canonical Field | Context | Removal |
|-------------------|----------------|---------|---------|
| `entity` (legacy middleware field) | `div_codes` | Middleware extraction | **Phase 0 (MUST)** |
| `branches` (legacy middleware field) | `branch_codes` | Middleware extraction | **Phase 0 (MUST)** |
| `userid` (legacy middleware field) | `identity_id` | Middleware extraction | **Phase 0 (MUST)** |
| `entity[0]` | `active_div_code` | JWT (stale) | Phase 0 |
| `branches[0]` | `active_branch_code` | JWT (stale) | Phase 0 |
| `division` (JSON array) | `div_codes[]` (scope) + `active_div_code` (active) | JWT + UserTenantContext | Phase 0 |
| `branches` (JSON array) | `branch_codes[]` (scope) + `active_branch_code` (active) | JWT + UserTenantContext | Phase 0 |
| `bgcode` | `bg_code` | MongoDB documents | M3 (Phase 5.7) |
| `division` | `div_code` | MongoDB documents | M3 (Phase 5.7) |
| `branch` | `branch_code` | MongoDB documents | M3 (Phase 5.7) |
| `userid` (PK) | `identity_id` | All person references | M1 (Phase 4) |
| `accesslevel[]` | `permissions{}` | Login response (with levels) | Phase 2 — FIXED |

**Phase 0 is the highest priority:** The middleware and MongoDB wrapper MUST be fixed to use canonical field names before any other work. This is a P0 bug that breaks all tenant isolation.

### 11.2 Response Envelope Authority

**`endpoint_contract_spec.md` is the sole authority for wire contracts.** All other specs reference this document for response shapes, route definitions, and error formats. Do not redefine login response shapes in handoff notes or domain specs.

### 11.3 Extension Payload Maturity

`employee_profile`, `customer_profile`, `player_profile`, and other extension-derived subobjects are **nullable/absent until M1 data backfill completes**. The contract defines the shape; data availability follows migration timing. Return `null` or omit — do not fabricate empty objects.

---

## 12. OpenAPI Contract

### 12.1 Generation Strategy

**ponytail:** Use `drf-spectacular` auto-generation from DRF viewsets + serializers. One manual `openapi.yaml` only if a consumer (mobile, partner) demands a static spec. Otherwise, live `/api/v1/schema/` endpoint is sufficient.

### 12.2 Required OpenAPI Extensions

```yaml
x-tenant-scoped: true        # Indicates endpoint requires tenant context
x-rbac-permission: "users.view"  # Required RBAC permission
x-outbox-event: "order.placed"   # Published outbox event
```

### 12.3 Schema Components

Shared schemas (referenced across domains):
- `IdentityResponse` — unified identity with extensions
- `TenantContext` — bg_code, div_codes, active_div_code, active_branch_code, scope
- `PaginationMeta` — page, page_size, totals
- `ErrorResponse` — standard error envelope
- `PermissionList` — RBAC permission array

---

## Appendix A: Frontend API Client Notes

### A.1 Axios Configuration (LIVE)

```javascript
// kteam-fe-chief/src/lib/api.jsx
const api = axios.create({
    baseURL: '/api/v1',
    withCredentials: true,
    headers: { 'Content-Type': 'application/json' }
});
```

### A.2 Vite Dev Proxy (LIVE)

```javascript
// kteam-fe-chief/vite.config.js
server: {
    proxy: {
        '/api': {
            target: 'http://localhost:8000',
            changeOrigin: true
        }
    }
}
```

### A.3 Frontend Migration Checklist

- [ ] Replace `kuro/user` → `users/me` in `user.jsx`
- [ ] Replace `res.data.user.userid` → `res.data.user.identity_id`
- [x] Replace `res.data.user.accesslevel[]` → `res.data.user.permissions{}` (with levels)
- [ ] Replace `res.data.user.businessgroups[]` → `res.data.user.bg_code`
- [ ] Add `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `scope` to user state
- [ ] Replace `cafe/sessions/start` → `cafe/sessions` (POST)
- [ ] Replace `cafe/sessions/{id}/food` → `cafe-fnb/orders` (POST with `session_id`)
- [ ] Replace `tournaments/tourneyregister` → `tournaments/{id}/register`
- [ ] Update phone input to accept/display E.164 format
- [ ] Handle new error envelope format (`error.code`, `error.details`)
- [ ] **MUST call `/api/v1/tenant/switch/` on tenant change** (see §5.4)

---

## Appendix B: Legacy Endpoints to Remove

| Legacy Endpoint | Status | Replacement |
|---|---|---|
| `GET /api/v1/kuro/user` | ❌ Remove | `GET /api/v1/users/me` |
| `GET /api/v1/kuro/user/{userid}` | ❌ Remove | `GET /api/v1/users/{identity_id}` |
| `POST /api/v1/cafe/sessions/start` | ❌ Remove | `POST /api/v1/cafe/sessions` |
| `POST /api/v1/cafe/sessions/{id}/food` | ❌ Remove | `POST /api/v1/cafe-fnb/orders` |
| `GET /api/v1/tournaments/tourneyregister` | ❌ Remove | `POST /api/v1/tournaments/{id}/register` |
| `GET /api/v1/kuro/accesslevel/{userid}` | ❌ Remove | `GET /api/v1/rbac/user/{identity_id}` |
| `POST /api/v1/kuro/switchgroup` | ❌ Remove | `POST /api/v1/tenant/switch` |
| `GET /api/v1/kuro/businessgroups` | ❌ Remove | `GET /api/v1/tenant/accessible` |

---

## Cross-References

- `multi_tenancy.md` — JWT claims, middleware extraction contract, authority hierarchy
- `CANONICAL_NAMING.md` — frozen canonical names
- `identity_layer.md` — unified identity architecture
- `rbac_system.md` — RBAC resolution engine
- `postgresql_schema.md` — PostgreSQL tenant schema
- `mongodb_schema.md` — MongoDB tenant field naming
- `migration_spec.md` — migration phases and dependencies

---

> **Implementation state:** This spec defines the TARGET endpoint contract. Current LIVE endpoints use legacy paths (`kuro/`, `auth/login` with old response shape). Migration tracked in `migration_spec.md`. Frontend client (`kteam-fe-chief`) must be updated per Appendix A checklist before legacy endpoints are removed.
>
> **Critical:** The middleware extraction bug (legacy field names) is tracked in `tenant-context-audit_a72921.md` (P0). The switch endpoint JWT emission gap is tracked as P1. Both MUST be fixed before this spec can be considered fully implemented.
