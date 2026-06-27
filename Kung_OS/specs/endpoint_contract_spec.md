# KungOS Endpoint Contract Specification

**Status:** Draft — aligned to target architecture  
**Date:** 2026-06-25  
**Scope:** Backend URL routing, response contracts, access rules for KTeam FE + E-Commerce (`eshop/`) + Cafe Platform + Tournaments  
**Depends on:** Identity Layer (§identity_layer), Multi-Tenancy (§multi_tenancy), RBAC System (§rbac_system), Platform Primitives (§platform_primitives)  
**Source:** Target architecture reconciliation  

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
11. [OpenAPI Contract](#11-openapi-contract)

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
| `/cafe/` | Cafe (arcade) | `domains/cafe_arcade/` | Sessions, stations, wallet, pricing |
| `/cafe-fnb/` | Cafe (F&B) | `domains/cafe_fnb/` | F&B orders, menu |
| `/eshop/` | E-Commerce | `eshop/` | Products, cart, orders, payments |
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
        path('auth/', include('users.auth_urls')),

        # Identity
        path('users/', include('users.urls')),

        # Multi-tenancy
        path('tenant/', include('tenant.urls')),

        # RBAC
        path('rbac/', include('users.rbac_urls')),

        # Cafe — arcade (sessions, stations, wallet, pricing)
        path('cafe/', include('domains/cafe_arcade/urls')),

        # Cafe — F&B (orders, menu)
        path('cafe-fnb/', include('domains/cafe_fnb/urls')),

        # E-Commerce
        path('eshop/', include('eshop.urls')),

        # Tournaments
        path('tournaments/', include('domains/tournaments/urls')),

        # Admin (cross-domain)
        path('admin/', include('admin.urls'))
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
| `GET` | `/api/v1/auth/me` | Current session info | JWT |

### 4.2 Login Response Contract

**Legacy (LIVE):**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "user": {
            "userid": "KCTM006",
            "phone": "9876543210",
            "name": "John Doe",
            "bg_code": "KURO0001",
            "accesslevel": ["user_view", "order_create"],
            "is_admin": false
        }
    }
}
```

**Target:**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "refresh_token": "dXJ...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "identity_id": "ID000001",
            "phone": "+919876543210",
            "name": "John Doe",
            "email": "john@example.com",
            "bg_code": "KURO0001",
            "active_div_code": "KURO0001_001",
            "active_branch_code": null,
            "roles": ["employee", "customer"],
            "permissions": ["users.view", "orders.create"],
            "is_admin": false
        }
    }
}
```

### 4.3 Auth Migration Notes

| Legacy Field | Target Field | Change |
|---|---|---|
| `user.userid` | `user.identity_id` | New PK format |
| `user.phone` (raw) | `user.phone` (E.164) | Normalized |
| `user.bg_code` | `user.bg_code` | Unchanged |
| — | `user.active_div_code` | Added |
| — | `user.active_branch_code` | Added |
| `user.accesslevel[]` | `user.permissions[]` | RBAC perm_codes |
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

### 5.1 Context Injection

All authenticated requests carry tenant context from `users_user_tenant_context`:

```python
# Middleware: TenantContextMiddleware
class TenantContextMiddleware:
    def process_request(self, request):
        ctx = UserTenantContext.objects.get(token_key=request.jwt.tenant_key)
        request.bg_code = ctx.bg_code
        request.div_codes = ctx.div_codes  # was: ctx.division (JSON)
        request.branch_codes = ctx.branch_codes  # was: ctx.branches (JSON)
        request.scope = ctx.scope  # 'full' | 'division' | 'branch'
```

### 5.2 Query Scoping Rules

| Scope | Query Filter | Example |
|---|---|---|
| `full` | `bg_code = X` | BG admin sees all divisions |
| `division` | `bg_code = X AND div_code IN (...)` | Division manager |
| `branch` | `bg_code = X AND div_code = Y AND branch_code IN (...)` | Branch staff |

### 5.3 Tenant Switching

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/tenant/accessible` | List accessible BGs/divisions | JWT |
| `POST` | `/api/v1/tenant/switch` | Switch tenant context | JWT |
| `GET` | `/api/v1/tenant/current` | Current tenant context | JWT |

**Switch response:**
```json
{
    "status": "success",
    "data": {
        "bg_code": "KURO0002",
        "active_div_code": "KURO0002_001",
        "scope": "division",
        "token_key": "new_tenant_key_abc"
    }
}
```

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
            "department": "Engineering",
            "joining_date": "2024-01-15"
        },
        "customer_profile": {
            "registered": true,
            "order_count": 15,
            "total_spent": 25000.00
        }
    }
}
```

### 6.2 Cafe — Arcade (`/api/v1/cafe/`)

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

### 6.3 Cafe — F&B (`/api/v1/cafe-fnb/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/cafe-fnb/menu` | Menu items | Public |
| `POST` | `/cafe-fnb/orders` | Create order | JWT |
| `GET` | `/cafe-fnb/orders/{id}` | Order detail | JWT |

### 6.4 E-Commerce (`/api/v1/eshop/`)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/eshop/products` | Product catalog | Public |
| `GET` | `/eshop/products/{id}` | Product detail | Public |
| `GET` | `/eshop/cart` | Current user cart | JWT |
| `POST` | `/eshop/cart` | Add to cart | JWT |
| `PATCH` | `/eshop/cart/{id}` | Update cart item | JWT |
| `DELETE` | `/eshop/cart/{id}` | Remove from cart | JWT |
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

### 6.5 Tournaments (`/api/v1/tournaments/`)

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

### 7.2 Legacy → Target Field Mapping (Frontend Contract)

| Legacy Response Path | Target Response Path | Change |
|---|---|---|
| `res.data.user.userid` | `res.data.user.identity_id` | New PK |
| `res.data.user.phone` (raw) | `res.data.user.phone` (E.164) | Normalized |
| `res.data.user.businessgroups[]` | `res.data.user.bg_code` | Single BG from tenant context |
| `res.data.user.accesslevel[]` | `res.data.user.permissions[]` | RBAC perm_codes |
| `res.data.user.roles` (JSON) | `res.data.user.roles[]` | Derived from extensions |
| `res.data.user.primary_bg` | `res.data.user.bg_code` | From tenant context |
| — | `res.data.user.active_div_code` | New field |
| — | `res.data.user.active_branch_code` | New field |
| `res.data.user.employee.*` | `res.data.user.employee_profile.*` | Nested extension |
| `res.data.user.customer.*` | `res.data.user.customer_profile.*` | Nested extension |
| `session.food_charges` | `session.last_order_id` | Reference, not amount |
| `wallet.customer_id` | `wallet.identity_id` | FK target changed |
| `address.user_id` | `address.identity_id` | FK target changed |
| `cart.user_id` | `cart.user_id` | Same name, FK → `users_identity` |
| `order.user_id` | `order.customer_id` | Renamed, FK → `users_identity` |

### 7.3 Frontend Transition Strategy

**Phase 1 (dual-mode):** Backend returns both legacy and target field names in response. Frontend reads new names; legacy names present for safety.

**Phase 2 (target-only):** Legacy field names removed. Frontend fully migrated.

**Ponytail note:** Skip dual-mode if frontend migration is immediate. Add a response serializer adapter layer instead — one place to map, not two fields everywhere.

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
|---|---|
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
| `division` (JSON array) | `div_codes[]` (scope) + `active_div_code` (active) | JWT + UserTenantContext | Phase 0 |
| `branches` (JSON array) | `branch_codes[]` (scope) + `active_branch_code` (active) | JWT + UserTenantContext | Phase 0 |
| `entity[0]` | `active_div_code` | JWT (stale) | Phase 0 |
| `bgcode` | `bg_code` | MongoDB documents | M3 (Phase 5.7) |
| `branch` | `branch_code` | MongoDB documents | M3 (Phase 5.7) |
| `userid` (PK) | `identity_id` | All person references | M1 (Phase 4) |
| `accesslevel[]` | `permissions[]` | Login response | Phase 2 |

### 11.2 Response Envelope Authority

**`endpoint_contract_spec.md` is the sole authority for wire contracts.** All other specs reference this document for response shapes, route definitions, and error formats. Do not redefine login response shapes in handoff notes or domain specs.

### 11.3 Extension Payload Maturity

`employee_profile`, `customer_profile`, `player_profile`, and other extension-derived subobjects are **nullable/absent until M1 data backfill completes**. The contract defines the shape; data availability follows migration timing. Return `null` or omit — do not fabricate empty objects.

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
- `TenantContext` — bg_code, active_div_code, active_branch_code, scope
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
- [ ] Replace `res.data.user.accesslevel[]` → `res.data.user.permissions[]`
- [ ] Replace `res.data.user.businessgroups[]` → `res.data.user.bg_code`
- [ ] Add `active_div_code` / `active_branch_code` to user state
- [ ] Replace `cafe/sessions/start` → `cafe/sessions` (POST)
- [ ] Replace `cafe/sessions/{id}/food` → `cafe-fnb/orders` (POST with `session_id`)
- [ ] Replace `tournaments/tourneyregister` → `tournaments/{id}/register`
- [ ] Update phone input to accept/display E.164 format
- [ ] Handle new error envelope format (`error.code`, `error.details`)

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

> **Implementation state:** This spec defines the TARGET endpoint contract. Current LIVE endpoints use legacy paths (`kuro/`, `auth/login` with old response shape). Migration tracked in `migration_spec.md`. Frontend client (`kteam-fe-chief`) must be updated per Appendix A checklist before legacy endpoints are removed.
