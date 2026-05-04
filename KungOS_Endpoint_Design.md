# KungOS Endpoint Design — API Consolidation Specification

**Status:** Draft — awaiting Phase 4 completion  
**Date:** 2026-05-04  
**Scope:** Backend URL routing, response contracts, access rules for KTeam FE + Gaming Eshop + Cafe Platform  
**Depends on:** KungOS v2 Phase 4 (testing, CI/CD, go-live)  

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [URL Routing Rules](#2-url-routing-rules)
3. [Request/Response Contracts](#3-requestresponse-contracts)
4. [Authentication & Authorization](#4-authentication--authorization)
5. [Tenant Context Rules](#5-tenant-context-rules)
6. [Domain Specifications](#6-domain-specifications)
   - [6.1 Accounts Domain](#61-accounts-domain)
   - [6.2 Orders Domain](#62-orders-domain)
   - [6.3 Eshop Domain](#63-eshop-domain)
   - [6.4 Products Domain](#64-products-domain)
     - [6.4.1 Asset Register Endpoint](#641-asset-register-endpoint)
   - [6.5 Vendors Domain](#65-vendors-domain)
   - [6.6 Teams Domain](#66-teams-domain)
   - [6.7 Cafe Domain](#67-cafe-domain)
   - [6.8 Esports Domain](#68-esports-domain)
   - [6.9 Search Domain](#69-search-domain)
   - [6.10 Shared Domain](#610-shared-domain)
   - [6.11 Admin Domain (MongoDB)](#611-admin-domain-mongodb)
7. [Migration Mapping](#7-migration-mapping)
8. [Error Response Standard](#8-error-response-standard)
9. [Pagination & Filtering](#9-pagination--filtering)
10. [OpenAPI Documentation](#10-openapi-documentation)
11. [Testing Requirements](#11-testing-requirements)

---

## 1. Design Principles

### 1.1 Domain-First Routing

**Rule:** URLs are organized by **business domain**, not by consumer role.

| ❌ Before (role-based) | ✅ After (domain-based) |
|------------------------|------------------------|
| `/api/v1/kuroadmin/vendors` | `/api/v1/vendors/list` |
| `/api/v1/kurostaff/vendors` | `/api/v1/vendors/list` |
| `/api/v1/kuroadmin/tporders` | `/api/v1/orders/tp-orders` |
| `/api/v1/kurostaff/inwardinvoices` | `/api/v1/accounts/inward-invoices` |

**Rationale:** The same resource serves multiple roles. Access control is enforced by RBAC permissions, not URL prefixes. A `kuroadmin` user and a `kurostaff` user call the same endpoint — their permissions determine what data they see.

### 1.2 Single Source of Truth

**Rule:** One endpoint per resource. No duplicates.

| Current Duplicate | Resolution |
|-------------------|------------|
| `kuroadmin/vendors` + `kurostaff/vendors` | Single `vendors/list` view |
| `kuroadmin/tporders` + `kurostaff/tporders` | Single `orders/tp-orders` view |
| `kuroadmin/kgorders` + `kurostaff/kgorders` | Single `orders/in-store` view |
| `kuroadmin/indent` + `kurostaff/indent` | Single `products/indent` view |
| `kuroadmin/inwardinvoices` + `kurostaff/inwardinvoices` | Single `accounts/inward-invoices` view |
| `kuroadmin/employees` + `kuroadmin/empadminlist` + `kuroadmin/empdashlist` | Single `teams/employees` view |

**Implementation:** Pick the most complete view function. If both views differ, merge logic into a single ViewSet.

### 1.3 RESTful Conventions

**Rule:** Endpoints follow RESTful naming with kebab-case.

| Pattern | Example |
|---------|---------|
| Collection (list/create) | `GET/POST /vendors/list` |
| Resource (read/update/delete) | `GET/PATCH/DELETE /vendors/{id}` |
| Sub-resource | `GET /vendors/{id}/invoices` |
| Action | `POST /vendors/{id}/activate` |
| Export | `GET /accounts/export/inward-invoices?duration=month` |

**Naming rules:**
- Plural nouns for collections with `/list` suffix: `vendors/list`, `employees/list`
- `/list` is a structural convention (not a verb) — signals a paginated collection endpoint
- Kebab-case: `payment-vouchers`, `outward-credit-notes`, `stock-audit`
- No action verbs in path: `GET /vendors/list` (not `GET /getVendors`)
- HTTP method implies action: `POST` = create, `PATCH` = update, `DELETE` = remove

### 1.4 Versioning

**Rule:** All API endpoints under `/api/v1/`. No version in individual URLs.

```
/api/v1/vendors/list          ✅
/api/v1/v1/vendors/list       ❌
/api/vendors/list             ❌ (unversioned)
```

### 1.5 Brand Neutrality

**Rule:** Shared resources live in brand-neutral namespaces. Brand identity is handled by `bg_code` tenant context.

| Current | Target | Rationale |
|---------|--------|-----------|
| `rebellion/cafe/wallet` | `cafe/wallet` | Wallet is shared across brands |
| `rebellion/tournaments` | `esports/tournaments` | Esports is a domain, not a brand |
| `kuroadmin/employees` | `teams/employees` | Teams is universal |

---

## 2. URL Routing Rules

### 2.1 Root Structure

```
/api/v1/
├── auth/              # Authentication (login, logout, refresh, verify, pwdreset)
├── users/             # Identity & auth (me, profile, RBAC)
├── tenant/            # Multi-tenant config (business-groups, divisions, branches)
├── admin/             # Sys Admin only (tenant bootstrap, templates, domains, api-keys, mongo-admin)
├── accounts/          # Finance domain
├── orders/            # Orders domain (estimates, in-store, tp, service)
├── eshop/             # E-commerce domain (online retail orders)
├── products/          # Products domain
├── vendors/           # Vendor domain (shared resource)
├── teams/             # Teams domain (onboarding, payroll, employees)
├── cafe/              # Cafe platform domain (sessions, wallet, food-orders)
├── esports/           # Esports domain
├── careers/           # Careers domain
├── search/            # MeiliSearch domain
└── shared/            # Shared utilities
```

**Boundary: `users/` vs `teams/`**

`users/` handles **identity & authentication**: login, logout, profile, password reset, RBAC permissions. It answers "who are you and what can you do?"

`teams/` handles **workforce operations**: employee records, onboarding, attendance, payroll, leave, dashboard. It answers "who works here and how are they managed?"

A user (`users/me`) may or may not be an employee (`teams/employees`). Contractors, vendors, and customers have user accounts but no employee records.

### 2.2 Django URL Configuration

**File:** `backend/urls.py`

```python
urlpatterns = [
    # Health check
    path('health/', health_check, name='health-check'),
    path('ping/', health_check, name='ping'),

    # OpenAPI docs
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API v1 — domain-based routing
    path('api/v1/', include([
        # Auth & Users (already clean)
        path('users/', include('users.urls')),

        # Tenant management (already clean)
        path('tenant/', include('tenant_api.urls')),

        # Sys Admin (already clean)
        path('admin/', include('kungos_admin.urls')),

        # ── Domain modules (new) ──
        path('accounts/', include('kungos_dj.domains.accounts.urls')),
        path('orders/', include('kungos_dj.domains.orders.urls')),
        path('eshop/', include('kungos_dj.domains.eshop.urls')),
        path('products/', include('kungos_dj.domains.products.urls')),
        path('vendors/', include('kungos_dj.domains.vendors.urls')),
        path('teams/', include('kungos_dj.domains.teams.urls')),
        path('search/', include('kungos_dj.domains.search.urls')),
        path('shared/', include('kungos_dj.domains.shared.urls')),

        # Cafe platform (separate Django app, shared multi-tenant)
        path('cafe/', include('cafe.urls')),

        # Esports (moved from rebellion/)
        path('esports/', include('rebellion.esports.urls')),

        # Careers (already clean)
        path('careers/', include('careers.urls')),

    ])),

    # Root-level auth endpoints
    path('api/v1/auth/login', AuthViewSet.as_view({'post': 'login'}), name='unified_login'),
    path('api/v1/auth/logout', AuthViewSet.as_view({'post': 'logout'}), name='jwt_logout'),
    path('api/v1/auth/refresh', CookieTokenRefreshView.as_view(), name='jwt_refresh'),
]
```

### 2.3 Domain Module Structure

**Directory layout:**

```
kungos_dj/
├── domains/                    # New domain-based modules
│   ├── __init__.py
│   ├── accounts/
│   │   ├── __init__.py
│   │   ├── urls.py             # Domain URL routing
│   │   ├── views.py            # ViewSets / function views
│   │   ├── serializers.py      # DRF serializers
│   │   ├── services.py         # Business logic
│   │   └── repositories.py     # Data access (MongoDB/PostgreSQL)
│   ├── orders/
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   └── repositories.py
│   ├── eshop/
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   └── repositories.py
│   ├── products/
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   └── repositories.py
│   ├── vendors/
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   └── repositories.py
│   ├── teams/
│   │   ├── urls.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── services.py
│   │   └── repositories.py
│   ├── search/
│   │   ├── urls.py
│   │   ├── views.py
│   │   └── services.py
│   └── shared/
│       ├── urls.py
│       ├── views.py
│       └── services.py
├── financial.py                # Existing — migrate to domains/accounts/
├── inward_invoices.py          # Existing — migrate to domains/accounts/
├── outward_invoices.py         # Existing — migrate to domains/accounts/
├── products.py                 # Existing — migrate to domains/products/
├── employees.py                # Existing — migrate to domains/teams/
├── stock_audit.py              # Existing — migrate to domains/products/
└── kurostaff/
    └── views.py                # Existing — migrate to appropriate domains/
```

---

## 3. Request/Response Contracts

### 3.1 Response Envelope

**Rule:** All responses use a consistent envelope. No raw data at root level.

```json
{
  "status": "SUCCESS",
  "data": [...],
  "meta": {
    "total": 150,
    "page": 1,
    "per_page": 50,
    "total_pages": 3
  }
}
```

**Error response:**

```json
{
  "status": "FAILURE",
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "You do not have access to perform this action",
    "details": {}
  }
}
```

**Current issues to fix:**
- Some endpoints return raw arrays: `Response(output_list, status=200)` → wrap in envelope
- Some endpoints return mixed formats: `{"error": "..."}` vs `{"status": "FAILURE", "msg": "..."}` → standardize
- Some endpoints return `200` for errors → use proper HTTP status codes

### 3.2 HTTP Status Codes

| Action | Success | Client Error | Server Error |
|--------|---------|--------------|--------------|
| List | `200 OK` | `400 Bad Request` | `500 Internal Server Error` |
| Create | `201 Created` | `400 Bad Request` | `500 Internal Server Error` |
| Read | `200 OK` | `404 Not Found` | `500 Internal Server Error` |
| Update | `200 OK` | `400 Bad Request` / `404` | `500 Internal Server Error` |
| Delete | `204 No Content` | `404 Not Found` | `500 Internal Server Error` |
| Permission denied | — | `403 Forbidden` | — |

### 3.3 Field Naming

**Rule:** Snake_case for all JSON fields. No camelCase.

| ❌ Before | ✅ After |
|-----------|----------|
| `vendorCode` | `vendor_code` |
| `openingBalance` | `opening_balance` |
| `closingBalance` | `closing_balance` |
| `bgCode` | `bg_code` |
| `deleteFlag` | `delete_flag` |

**Current state:** Backend already uses snake_case (MongoDB documents). Frontend maps to snake_case in React Query. No migration needed.

### 3.4 Vendor Response Contract

**Rule:** Vendor endpoints return consistent fields. This fixes the Ledgers page lookup issue.

```json
{
  "status": "SUCCESS",
  "data": [
    {
      "vendor_code": "AMAZ290010",
      "name": "Amazon Web Services",
      "gstin": "29AAMCA1234A1Z5",
      "state": "KA",
      "contact_person": "John Doe",
      "email": "vendor@example.com",
      "phone": "+91-9876543210",
      "address": "123 Main St, Bangalore, KA 560001",
      "division": "DIV001",
      "active": true,
      "delete_flag": false,
      "gstdetails": [
        {
          "gstin": "29AAMCA1234A1Z5",
          "state": "KA",
          "address": "123 Main St, Bangalore"
        }
      ],
      "created_date": "2024-01-15T10:30:00Z",
      "updated_date": "2024-06-01T14:20:00Z"
    }
  ]
}
```

**Ledgers page lookup:**

```js
// Sundy creditor key: "AMAZ290010"
// Vendor lookup: vendors.find(v => v.vendor_code === key)
// Display: vendor.name → "Amazon Web Services"
```

---

## 4. Authentication & Authorization

### 4.1 Authentication

**Rule:** All endpoints require authentication via CookieJWTAuthentication.

```python
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from users.cookie_auth import CookieJWTAuthentication

@api_view(['GET', 'POST'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def vendors_list(request):
    # ...
```

**Exceptions:** `auth/login`, `auth/refresh`, `health/`, `ping/`, OpenAPI docs — no auth required.

### Public Endpoint Exceptions

The following endpoints allow unauthenticated access (`@permission_classes([AllowAny])`). They do not use kiosk tokens or device trust — they rely on **tenant context from the request payload** (station_id → Station.cafe → Cafe.bg_code/div_code/branch_code) and **tenant filtering via bg_code + div_code + branch_code**.

| Endpoint | Method | Why public | Security control |
|----------|--------|------------|------------------|
| `cafe/customer/register` | POST | Walk-in customers have no account yet | Rate limiting, phone validation |
| `cafe/customer/lookup` | POST | Staff enters phone to check-in walk-in | Branch-scoped results only |
| `cafe/sessions/start` | POST | Staff starts session on behalf of customer | Station must be idle, tenant from Station.cafe |

**Middleware interaction:** These routes are whitelisted in `TenantContextMiddleware` (§5.1). The middleware skips its fail-closed `bg_code` check for these POST routes, allowing the view to derive tenant context from `station_id` in the request body. See §5.1 for the two-phase resolution contract.

```python
# rebellion/cafe/views.py
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def session_start(request):
    # No JWT required — staff enters phone at station kiosk
    # Tenant context: station_id → Station.cafe → Cafe.bg_code/div_code/branch_code
    # (middleware skips tenant validation for this whitelisted route)
    station = Station.objects.select_related('cafe').get(
        id=request.data['station_id'],
        status='idle'
    )
    request.bg_code = station.cafe.bg_code
    request.division = station.cafe.div_code
    request.branch = station.cafe.branch_code  # tenant scoping
    # Safe user resolution on AllowAny endpoint — request.user may be AnonymousUser
    started_by = None
    if request.user and request.user.is_authenticated:
        started_by = getattr(request.user, 'userid', None)
    if not started_by:
        started_by = request.data.get('phone', 'anonymous')
    ...
```

### 4.2 Authorization (RBAC)

**Rule:** Permissions are checked at the view level, not the URL level. Same endpoint, different data scope based on role.

```python
from users.permissions import has_permission

@api_view(['GET'])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def vendors_list(request):
    """
    GET /api/v1/vendors/list
    Query params: division, vendor_code, page, per_page
    
    Admin: sees all vendors across all divisions
    Manager: sees vendors in their assigned divisions
    Staff: sees vendors in their division only
    """
    if not has_permission(request.user, 'vendors.view'):
        return Response(
            {"status": "FAILURE", "error": {"code": "PERMISSION_DENIED", "message": "Access denied"}},
            status=403
        )
    
    # Tenant context auto-scopes by division
    vendors = VendorRepository.list(
        bg_code=request.bg_code,
        divisions=get_accessible_divisions(request.user, 'vendors'),
        filters=request.query_params
    )
    
    return Response({"status": "SUCCESS", "data": vendors})
```

### 4.3 Permission Matrix

| Domain | Endpoint | Admin | Manager | Staff | Customer |
|--------|----------|-------|---------|-------|----------|
| **accounts** | `GET /accounts/inward-invoices` | ✅ All | ✅ Division | ✅ Own | ❌ |
| **accounts** | `POST /accounts/inward-invoices` | ✅ | ✅ | ❌ | ❌ |
| **accounts** | `GET /accounts/accounts?type=sundrycreditors` | ✅ All | ✅ Division | ✅ Read | ❌ |
| **accounts** | `GET /accounts/financials` | ✅ | ✅ | ❌ | ❌ |
| **accounts** | `GET /accounts/export/*` | ✅ | ✅ | ❌ | ❌ |
| **orders** | `GET /orders/tp-orders` | ✅ All | ✅ Division | ✅ Own | ❌ |
| **orders** | `POST /orders/tp-orders` | ✅ | ✅ | ✅ | ❌ |
| **orders** | `GET /orders/estimates` | ✅ All | ✅ Division | ✅ Own | ❌ |
| **products** | `GET /products/catalog` | ✅ All | ✅ All | ✅ All | ✅ All |
| **products** | `POST /products/catalog` | ✅ | ❌ | ❌ | ❌ |
| **products** | `GET /products/assets` | ✅ All | ✅ Division | ✅ Branch | ❌ |
| **products** | `POST /products/assets` | ✅ | ✅ | ❌ | ❌ |
| **products** | `POST /products/assets/calculate-depreciation` | ✅ | ✅ | ❌ | ❌ |
| **vendors** | `GET /vendors/list` | ✅ All | ✅ Division | ✅ Read | ❌ |
| **vendors** | `POST /vendors/list` | ✅ | ✅ | ❌ | ❌ |
| **teams** | `GET /teams/employees` | ✅ All | ✅ Division | ✅ Own | ❌ |
| **teams** | `POST /teams/employees` | ✅ | ❌ | ❌ | ❌ |
| **cafe** | `GET /cafe/stations` | ✅ | ✅ | ✅ | ❌ |
| **cafe** | `POST /cafe/sessions/start` | ✅ | ✅ | ✅ | ✅ (walk-in) |
| **cafe** | `GET /cafe/wallet/balance` | ✅ | ✅ | ✅ | ✅ Own |
| **esports** | `GET /esports/tournaments` | ✅ | ✅ | ✅ | ✅ |
| **search** | `GET /search/search` | ✅ | ✅ | ✅ | ✅ |
| **accounts** | `GET /accounts/revenue` | ✅ | ✅ | ❌ | ❌ |
| **accounts** | `GET /accounts/expenditure` | ✅ | ✅ | ❌ | ❌ |
| **orders** | `POST /orders/payment-links` | ✅ | ✅ | ✅ | ❌ |
| **eshop** | `GET /eshop/orders` | ✅ All | ✅ Division | ✅ Read | ✅ Own |
| **eshop** | `POST /eshop/orders` | ✅ | ✅ | ❌ | ✅ (checkout) |
| **cafe** | `POST /cafe/customer/register` | ✅ | ✅ | ✅ | ✅ (public) |
| **cafe** | `POST /cafe/customer/lookup` | ✅ | ✅ | ✅ | ✅ (public) |
| **cafe** | `GET /cafe/customer/profile` | ✅ | ✅ | ✅ | ✅ Own |
| **cafe** | `POST /cafe/wallet/recharge` | ✅ | ✅ | ✅ | ✅ |
| **cafe** | `POST /cafe/sessions/pause` | ✅ | ✅ | ✅ | ❌ |
| **cafe** | `POST /cafe/sessions/resume` | ✅ | ✅ | ✅ | ❌ |
| **cafe** | `POST /cafe/sessions/end` | ✅ | ✅ | ✅ | ❌ |
| **cafe** | `GET /cafe/food-orders` | ✅ All | ✅ Division | ✅ Read | ✅ Own |
| **cafe** | `POST /cafe/food-orders` | ✅ | ✅ | ✅ | ✅ |
| **esports** | `GET /esports/players` | ✅ | ✅ | ✅ | ✅ |
| **esports** | `GET /esports/teams` | ✅ | ✅ | ✅ | ✅ |
| **esports** | `POST /esports/tourney-register` | ✅ | ✅ | ✅ | ✅ |
| **esports** | `GET /esports/gamers` | ✅ | ✅ | ✅ | ✅ |
| **search** | `POST /search/index` | ✅ | ❌ | ❌ | ❌ |
| **search** | `POST /search/update-document` | ✅ | ❌ | ❌ | ❌ |
| **search** | `POST /search/delete-document` | ✅ | ❌ | ❌ | ❌ |
| **search** | `POST /search/drop-index` | ✅ (SysAdmin) | ❌ | ❌ | ❌ |
| **search** | `POST /search/drop-all` | ✅ (SysAdmin) | ❌ | ❌ | ❌ |
| **shared** | `GET /shared/home` | ✅ | ✅ | ✅ | ✅ |

### 4.4 Mandatory Permission Guard Contract

**Rule:** Every endpoint must declare its permission requirement. No endpoint ships without an explicit `@permission_classes` decorator or ViewSet `permission_classes` attribute.

**Default:** `IsAuthenticated` + domain-specific permission codename (e.g., `vendors.view`, `orders.create`).

**Exception list (must be explicitly justified):**
- `auth/login`, `auth/refresh` — pre-authentication
- `health/`, `ping/` — infrastructure
- `cafe/customer/register`, `cafe/customer/lookup`, `cafe/sessions/start` — walk-in kiosk flow (§4.1)
- OpenAPI schema/docs — public documentation

**Enforcement:** `test_permissions.py` validates every URL pattern has a permission class. Endpoints with `AllowAny` fail the test unless listed in the exception whitelist.

---

## 5. Tenant Context Rules

### 5.1 Tenant Context Middleware

**Rule:** Every request carries `bg_code`, `division`, and `branch`. Enforced by middleware.

**Two-phase resolution:**

1. **Phase 1 — Cookie/Session** (authenticated requests): Extract `bg_code`, `div_code`, `branch_code` from JWT cookie or session.
2. **Phase 2 — Body-derived** (public cafe endpoints): If Phase 1 yields nothing AND the route is in the whitelist, defer tenant resolution to the view. The view extracts `bg_code`, `div_code`, `branch_code` from `station_id → Station.cafe → Cafe`.

**Public route whitelist:** Routes that derive tenant context from request payload, not cookies.

```python
# middleware/tenant_context.py
from django.http import JsonResponse

# Public endpoints that derive tenant context from request body (station_id → Station.cafe → Cafe)
PUBLIC_TENANT_ROUTES = {
    'cafe/customer/register',
    'cafe/customer/lookup',
    'cafe/sessions/start',
}

class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for non-API requests
        if not request.path.startswith('/api/v1/'):
            return self.get_response(request)

        # Strip prefix to get domain route: '/api/v1/cafe/sessions/start' → 'cafe/sessions/start'
        route = request.path.replace('/api/v1/', '', 1)

        # Phase 1 — Cookie/Session (authenticated requests)
        request.bg_code = resolve_bg_code(request)
        request.division = resolve_division(request)
        request.branch = resolve_branch(request)

        # If tenant resolved via cookie, proceed normally
        if request.bg_code:
            return self.get_response(request)

        # Phase 2 — Public route exemption
        # Allow whitelisted routes to resolve tenant from request body in the view
        if route in PUBLIC_TENANT_ROUTES and request.method == 'POST':
            # View must extract bg_code from station_id → Station → bg_code
            # View must validate station exists, is active, and belongs to a valid tenant
            return self.get_response(request)

        # Fail closed: reject all other requests without tenant context
        return JsonResponse(
            {"status": "FAILURE", "error": {"code": "TENANT_MISSING", "message": "Tenant context required"}},
            status=400
        )
```

**View-side tenant resolution (public endpoints only):**

```
Tenant hierarchy: bg_code → div_code → branch_code → Station (PC desktop)
Cafe = location entity: bg_code, div_code, branch_code, code, name, timezone, currency
Station = PC desktop: cafe FK, code, zone, status, bg_code, div_code, branch_code (denormalized)
Resolution: station_id → Station.cafe → Cafe.{bg_code, div_code, branch_code}
```

`Station.bg_code/div_code/branch_code` are denormalized from `Cafe` for query efficiency. The authoritative source is `Station.cafe → Cafe`.

```python
# rebellion/cafe/views.py

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def session_start(request):
    """
    POST /api/v1/cafe/sessions/start
    Tenant context derived from station_id → Station.cafe → Cafe.bg_code.
    Middleware skips bg_code validation for this whitelisted route.
    """
    station_id = request.data.get('station_id')
    if not station_id:
        return Response(
            {"status": "FAILURE", "error": {
                "code": "VALIDATION_ERROR",
                "message": "station_id is required"
            }},
            status=400
        )

    # Resolve tenant: station (PC) → cafe (location) → {bg_code, div_code, branch_code}
    try:
        station = Station.objects.select_related('cafe').get(
            id=station_id,
            status='idle'
        )
    except Station.DoesNotExist:
        return Response(
            {"status": "FAILURE", "error": {
                "code": "NOT_FOUND",
                "message": "Station not found or not idle"
            }},
            status=404
        )

    # Set tenant context — use Cafe as authoritative source
    request.bg_code = station.cafe.bg_code
    request.division = station.cafe.div_code
    request.branch = station.cafe.branch_code

    # ... proceed with session creation, scoped to tenant context
```

**Customer register/lookup variants (same pattern):**

```python
# rebellion/cafe/views.py

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def customer_register(request):
    """
    POST /api/v1/cafe/customer/register
    Tenant context: station_id → Station.cafe → Cafe.{bg_code, div_code, branch_code}
    Walkin record persists tenant fields for isolation and lookup.
    """
    station = Station.objects.select_related('cafe').get(
        id=request.data['station_id']
    )
    bg_code = station.cafe.bg_code
    div_code = station.cafe.div_code
    branch_code = station.cafe.branch_code

    # Persist tenant scope on the walk-in record
    walkin = CafeWalkin.objects.create(
        walkin_id=generate_walkin_id(),  # WLN0001, stable ID
        primary_phone=request.data['phone'],
        name=request.data.get('name', ''),
        bg_code=bg_code,
        div_code=div_code,
        branch_code=branch_code,
    )
    # ... proceed with session creation

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def customer_lookup(request):
    """
    POST /api/v1/cafe/customer/lookup
    Tenant context: station_id → Station.cafe → Cafe.{bg_code, div_code, branch_code}
    Results are branch-scoped — same phone at different branches returns different records.
    """
    station = Station.objects.select_related('cafe').get(
        id=request.data['station_id']
    )
    bg_code = station.cafe.bg_code
    div_code = station.cafe.div_code
    branch_code = station.cafe.branch_code

    # Lookup scoped to tenant — prevents cross-tenant phone leakage
    walkin = CafeWalkin.objects.filter(
        primary_phone=request.data['phone'],
        bg_code=bg_code,
        div_code=div_code,
        branch_code=branch_code,
    ).first()
    # ... return walk-in data or 404
```

**Security note:** The whitelist is route-specific and method-restricted (POST only). GET requests to these routes still require authentication. The view must validate that `station_id` references an active station belonging to a valid tenant — no tenant leakage. All public cafe endpoints must both derive tenant context from `station_id` and persist/filter against that same tenant scope in downstream records and queries.

### 5.2 MongoDB Tenant Filtering

**Rule:** All MongoDB queries use `TenantCollection` with automatic tenant filtering.

```python
# repositories/vendors.py
from backend.utils import get_collection

class VendorRepository:
    @staticmethod
    def list(bg_code: str, divisions: list, filters: dict = None):
        collection, tenant_filter = get_collection('vendors', bg_code=bg_code)
        query = {**tenant_filter, "delete_flag": False, "active": True}
        
        if divisions:
            query["division"] = {"$in": divisions}
        
        if filters:
            query.update(filters)
        
        return decode_result(collection.find(query).sort([("name", 1)]))
```

### 5.3 PostgreSQL Tenant Filtering

**General rule:** All PostgreSQL queries filter by tenant ownership fields. Every table carries at minimum `bg_code`. Row-Level Security (RLS) deferred to Phase 4.

**Cafe-specific rule:** Cafe domain uses full tenant cascade (`bg_code` + `div_code` + `branch_code`) via `cafe__` FK lookups or direct tenant fields on tables without cafe FKs (`CafeWalkin`, `CafeUser`).

**Denormalization contract:** Where tenant fields are copied to child tables (`Station.bg_code/div_code/branch_code` from `Cafe`), they are write-time denormalized and read-time indexed. The FK parent (`Station.cafe → Cafe`) is the authoritative source for tenant scope changes.

```python
# repositories/cafe.py
from django.db.models import Q

class StationRepository:
    @staticmethod
    def list(bg_code: str, div_code: str = '', branch_code: str = ''):
        # Station.cafe → Cafe.{bg_code, div_code, branch_code} (authoritative tenant link)
        query = {
            'cafe__bg_code': bg_code,
            'status__in': ['idle', 'in_session'],
        }
        if div_code:
            query['cafe__div_code'] = div_code
        if branch_code:
            query['cafe__branch_code'] = branch_code
        return Station.objects.filter(**query).select_related('cafe')

    @staticmethod
    def lookup_walkin(phone: str, bg_code: str, div_code: str, branch_code: str):
        # CafeWalkin has direct tenant fields (no cafe FK)
        return CafeWalkin.objects.filter(
            primary_phone=phone,
            bg_code=bg_code,
            div_code=div_code,
            branch_code=branch_code,
        ).first()
```

---

## 6. Domain Specifications

### 6.1 Accounts Domain

**Purpose:** Financial operations — invoices, payments, ledgers, vouchers, reports.

**File:** `kungos_dj/domains/accounts/urls.py`

```python
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Inward invoices
    path('inward-invoices', views.InwardInvoiceViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='inward-invoices'),
    path('inward-invoices/<str:id>', views.InwardInvoiceViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='inward-invoice-detail'),

    # Outward invoices
    path('outward-invoices', views.OutwardInvoiceViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='outward-invoices'),
    path('outward-invoices/<str:id>', views.OutwardInvoiceViewSet.as_view({
        'get': 'retrieve', 'patch': 'update'
    }), name='outward-invoice-detail'),

    # Payments
    path('inward-payments', views.InwardPaymentViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='inward-payments'),
    path('outward-payments', views.OutwardPaymentViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='outward-payments'),
    path('payment-vouchers', views.PaymentVoucherViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='payment-vouchers'),

    # Purchase orders
    path('purchase-orders', views.PurchaseOrderViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='purchase-orders'),

    # Credit/Debit notes (outward = business issues, inward = vendor issues)
    path('outward-credit-notes', views.OutwardCreditNoteViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='outward-credit-notes'),
    path('outward-debit-notes', views.OutwardDebitNoteViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='outward-debit-notes'),
    path('inward-credit-notes', views.InwardCreditNoteViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='inward-credit-notes'),
    path('inward-debit-notes', views.InwardDebitNoteViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='inward-debit-notes'),

    # Accounts (sundry creditors/debtors, banks, partners, loans)
    path('accounts', views.AccountsViewSet.as_view({
        'get': 'list', 'post': 'create', 'patch': 'update'
    }), name='accounts'),

    # Financial reports
    path('financials', views.FinancialsViewSet.as_view({
        'get': 'list'
    }), name='financials'),
    path('itc-gst', views.ITCGSTViewSet.as_view({
        'get': 'list'
    }), name='itc-gst'),
    path('analytics', views.AnalyticsViewSet.as_view({
        'get': 'list'
    }), name='analytics'),

    # Settlements
    path('settlements', views.SettlementsViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='settlements'),
    path('bulk-payments', views.BulkPaymentsViewSet.as_view({
        'post': 'create'
    }), name='bulk-payments'),

    # Exports
    path('export/inward-invoices', views.export_inward_invoices, name='export-inward-invoices'),
    path('export/outward-invoices', views.export_outward_invoices, name='export-outward-invoices'),
    path('export/inward-payments', views.export_inward_payments, name='export-inward-payments'),

    # Utilities
    path('copy-sundry-balances', views.copy_sundry_balances, name='copy-sundry-balances'),
    path('update-statement', views.update_statement, name='update-statement'),
    path('upload-invoices', views.upload_invoices, name='upload-invoices'),

    # Financial summaries (revenue/expense reports)
    # Legacy: kuroadmin/sales → accounts/revenue (expanded)
    # Legacy: kuroadmin/purchases → accounts/expenditure (expanded)
    path('revenue', views.revenue, name='revenue'),
    path('expenditure', views.expenditure, name='expenditure'),
]
```

#### 6.1.1 Accounts (Sundry) Endpoint

**Endpoint:** `GET /api/v1/accounts/accounts?type=<type>`

**Query parameters:**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| `type` | Optional | `sundrycreditors`, `sundrydebtors`, `banks`, `partners`, `loans` | Account type filter |
| `date_from` | Optional | ISO date | Start of reconciliation period |
| `date_to` | Optional | ISO date | End of reconciliation period |
| `vendor_code` | Optional | Vendor code | Single vendor ledger detail |

**Response (summary — no date range):**

```json
{
  "status": "SUCCESS",
  "data": {
    "FY2024-25": [
      {
        "AMAZ290010": {
          "opening_balance": 59130.95,
          "credit": 36782.91,
          "debit": 9556.11,
          "closing_balance": 86357.75
        }
      },
      {
        "SHWE360001": {
          "opening_balance": 12000.00,
          "credit": 5000.00,
          "debit": 3000.00,
          "closing_balance": 14000.00
        }
      }
    ],
    "FY2023-24": [
      // ...
    ]
  }
}
```

**Response (ledger detail — with date range):**

When `date_from` and `date_to` are provided, returns brought-forward balance + transactions for reconciliation:

```json
{
  "status": "SUCCESS",
  "data": {
    "brought_forward": {
      "date": "2025-04-01",
      "balance": 59130.95,
      "credit": 0,
      "debit": 0
    },
    "transactions": [
      {
        "date": "2025-04-05",
        "type": "invoice",
        "ref": "INV290010",
        "debit": 15000.00,
        "credit": 0,
        "balance": 74130.95,
        "description": "Invoice for custom PC build"
      },
      {
        "date": "2025-04-10",
        "type": "payment",
        "ref": "PV290010",
        "debit": 0,
        "credit": 20000.00,
        "balance": 54130.95,
        "description": "Payment via NEFT"
      },
      {
        "date": "2025-04-15",
        "type": "credit_note",
        "ref": "CN290010",
        "debit": 0,
        "credit": 3000.00,
        "balance": 51130.95,
        "description": "Credit note for returned component"
      }
    ],
    "closing_balance": {
      "date": "2025-04-30",
      "balance": 51130.95,
      "credit": 23000.00,
      "debit": 15000.00
    }
  }
}
```

**Reconciliation logic:**
- `brought_forward` = closing balance as of `date_from` (from prior period)
- `transactions` = all entries between `date_from` and `date_to` (invoices, payments, credit/debit notes)
- `closing_balance` = brought_forward + sum(debits) - sum(credits)
- Single vendor: add `?vendor_code=AMAZ290010` for that vendor's ledger only

**Transaction source mapping (vendor/expense side):**

Sundry creditors/debtors track **vendor and expense transactions**. Inward payments are customer-side (revenue from orders) and are **not** part of vendor ledger reconciliation.

| `type` | Source Collection | Existing Endpoint | Ref Field | Amount Field | Direction |
|--------|----------------|-------------------|-----------|-------------|------------|
| `invoice` | `inward_invoices` | `accounts/inward-invoices` | `invoice_no` | `totalprice` | credit (+) |
| `payment` | `outward_payments` | `accounts/outward-payments` | `payment_voucher_no` | `amount` | debit (-) |
| `credit_note` | `outward_credit_notes` | `accounts/outward-credit-notes` | `credit_note_no` | `totalprice` | debit (-) |
| `debit_note` | `outward_debit_notes` | `accounts/outward-debit-notes` | `debit_note_no` | `totalprice` | credit (+) |

**Side distinction:**

| Side | Collections | Purpose |
|------|-------------|----------|
| **Revenue (customer)** | `inward_payments`, `outward_invoices` | Customer orders, sales, receipts |
| **Expense (vendor)** | `outward_payments`, `inward_invoices`, `outward_credit_notes`, `outward_debit_notes` | Vendor purchases, payments, adjustments |

**Backend implementation:**
```python
# Pseudocode for ledger detail endpoint
def get_ledger_detail(vendor_code, date_from, date_to):
    # 1. Brought-forward balance (closing balance as of date_from)
    bf = accounts_coll.find_one({
        "type": "sundrycreditors",
        "vendor": vendor_code,
        "period_end": date_from
    })

    # 2. Transactions from source collections (vendor/expense side only)
    # Note: inward_payments are customer-side (revenue), not vendor-side
    invoices = inward_invoices.find({
        "vendor": vendor_code,
        "invoice_date": {"$gte": date_from, "$lte": date_to}
    })
    payments = outward_payments.find({
        "vendor": vendor_code,
        "payment_date": {"$gte": date_from, "$lte": date_to}
    })
    out_credit_notes = outward_credit_notes.find({
        "vendor": vendor_code,
        "credit_note_date": {"$gte": date_from, "$lte": date_to}
    })
    out_debit_notes = outward_debit_notes.find({
        "vendor": vendor_code,
        "debit_note_date": {"$gte": date_from, "$lte": date_to}
    })

    # 3. Merge, sort by date, compute running balance
    transactions = []
    for inv in invoices:
        transactions.append({
            "date": inv["invoice_date"],
            "type": "invoice",
            "ref": inv["invoice_no"],
            "credit": inv["totalprice"],
            "debit": 0,
            "balance": running_balance + inv["totalprice"],
            "description": inv.get("description", "")
        })
    # ... same for payments, out_credit_notes, out_debit_notes

    return {
        "brought_forward": bf,
        "transactions": sorted(transactions, key=lambda x: x["date"]),
        "closing_balance": final_balance
    }
```

**Response (without type):**

```json
{
  "status": "SUCCESS",
  "data": [
    {
      "type": "sundrycreditors",
      "content": { "FY2024-25": [...] }
    },
    {
      "type": "sundrydebtors",
      "content": { "FY2024-25": [...] }
    },
    {
      "type": "banks",
      "content": { "FY2024-25": [...] }
    }
  ]
}
```

**Ledgers page integration:**

```js
// Fetch sundry creditors
const { data: creditorData } = useQuery({
  queryKey: ['accounts', 'sundrycreditors'],
  queryFn: () => fetcher('accounts/accounts?type=sundrycreditors'),
})

// Fetch vendors for name lookup
const { data: vendors = [] } = useQuery({
  queryKey: ['vendors'],
  queryFn: () => fetcher('vendors/list'),
})

// Transform: map vendor codes to names
const rows = creditorData?.flatMap(fy => 
  Object.values(fy).flat().map(item => {
    const code = Object.keys(item)[0]  // "AMAZ290010"
    const balances = item[code]
    const vendor = vendors.find(v => v.vendor_code === code)
    return {
      name: vendor?.name || code,  // "Amazon Web Services" or fallback to code
      ...balances,
      vendor_code: code,
    }
  })
)
```

#### 6.1.2 Financials Endpoint

**Endpoint:** `GET /api/v1/accounts/financials?period=<period>`

**Query parameters:**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| `period` | Optional | `monthly`, `quarterly`, `yearly` | Report period |

**Response:**

```json
{
  "status": "SUCCESS",
  "data": {
    "totalRevenue": 500000,
    "totalExpenses": 350000,
    "profitMargin": 30,
    "chartData": [
      { "period": "Jan", "revenue": 50000, "expenses": 35000 },
      { "period": "Feb", "revenue": 55000, "expenses": 38000 }
    ],
    "vendors": [
      { "name": "Vendor A", "amount": 45000, "percentage": 35 },
      { "name": "Vendor B", "amount": 32000, "percentage": 25 }
    ]
  }
}
```

#### 6.1.3 Revenue Endpoint

**Endpoint:** `GET /api/v1/accounts/revenue?period=<period>`

**Purpose:** All income categories — sales (in-store, TP, service), inward payments, cafe sessions, esports winnings, refunds credit.

**Query parameters:**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| `period` | Optional | `monthly`, `quarterly`, `yearly` | Report period |
| `category` | Optional | `sales`, `inward_payments`, `cafe_sessions`, `esports`, `refunds`, `all` | Filter by category |

**Response:**

```json
{
  "status": "SUCCESS",
  "data": {
    "period": "monthly",
    "total": 500000,
    "breakdown": {
      "sales": 300000,
      "inward_payments": 100000,
      "cafe_sessions": 50000,
      "esports": 25000,
      "refunds": 25000
    },
    "trend": [
      { "period": "Jan", "amount": 45000 },
      { "period": "Feb", "amount": 52000 }
    ],
    "topSources": [
      { "source": "In-store sales", "amount": 180000, "percentage": 36 },
      { "source": "TP orders", "amount": 120000, "percentage": 24 }
    ]
  }
}
```

#### 6.1.4 Expenditure Endpoint

**Endpoint:** `GET /api/v1/accounts/expenditure?period=<period>`

**Purpose:** All expense categories — purchases, utility payments, rent, payroll, other expenses.

**Query parameters:**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| `period` | Optional | `monthly`, `quarterly`, `yearly` | Report period |
| `category` | Optional | `purchases`, `utilities`, `rent`, `payroll`, `other`, `all` | Filter by category |

**Response:**

```json
{
  "status": "SUCCESS",
  "data": {
    "period": "monthly",
    "total": 350000,
    "breakdown": {
      "purchases": 200000,
      "utilities": 15000,
      "rent": 50000,
      "payroll": 70000,
      "other": 15000
    },
    "trend": [
      { "month": "Jan", "total": 320000 },
      { "month": "Feb", "total": 340000 },
      { "month": "Mar", "total": 350000 }
    ]
  }
}
```

#### 6.1.5 Export Endpoint

**Endpoint:** `GET /api/v1/accounts/export/<type>?duration=<duration>`

**Path parameters:**

| Param | Values | Description |
|-------|--------|-------------|
| `type` | `inward-invoices`, `outward-invoices`, `inward-payments` | Export type |

**Query parameters:**

| Param | Values | Description |
|-------|--------|-------------|
| `duration` | `month`, `last_month`, `fy`, `last_fy` | Time range |

**Response:** Excel file (`.xlsx`) with `Content-Disposition: attachment` header.

---

### 6.2 Orders Domain

**Purpose:** Unified order management — estimates, in-store orders, TP orders, service requests, e-commerce orders.

**Architecture:** Core + detail tables in PostgreSQL. Fields shared by 3+ order types go in `orders_core` (dense, zero nulls). Type-specific fields go in 1:1 detail tables. Cafe gaming sessions remain separate (`caf_platform_sessions`) — time-based billing, real-time WebSocket, 100K+/year volume.

**Rationale vs flat table:** Flat table = 58 cols, ~60% null per row. Core + detail = 13 core cols (dense) + 51 detail cols (zero waste). New order type = new detail table, no ALTER TABLE.

**Rationale vs separate collections:** Single PG table = ACID for all types, atomic estimate→order conversion, unified pipeline analytics, referential integrity.

**Storage:**
```
orders_core (13 cols) ──┬── estimate_detail   (5 cols)
                        ├── in_store_detail  (9 cols)
                        ├── tp_order_detail  (7 cols)
                        ├── service_detail   (5 cols)
                        └── eshop_detail     (22 cols)

caf_platform_sessions (17 cols) — gaming sessions (separate)
```

**Migration:** 4 Mongo collections + 1 PG table → core + detail tables. See `~/llm-wiki/orders-migration-plan.md`.

**File:** `kungos_dj/domains/orders/urls.py`

```python
from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # ── Unified endpoints (core table) ──────────────────────
    path('all', views.OrdersUnifiedView.as_view(), name='orders-all'),
    path('pipeline', views.OrdersPipelineView.as_view(), name='orders-pipeline'),
    path('analytics', views.OrdersAnalyticsView.as_view(), name='orders-analytics'),

    # ── Estimates ───────────────────────────────────────────
    path('estimates', views.EstimateViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='estimates'),
    path('estimates/<str:orderid>', views.EstimateViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='estimate-detail'),

    # ── In-Store Orders (custom PC builds, offline channel) ──
    # Legacy: kgorders collection, offline_orders permission
    path('in-store', views.InStoreOrderViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='in-store'),
    path('in-store/<str:orderid>', views.InStoreOrderViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='in-store-detail'),

    # ── TP Orders (pre-built PCs) ───────────────────────────
    path('tp-orders', views.TPOrderViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='tp-orders'),
    path('tp-orders/<str:orderid>', views.TPOrderViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='tp-order-detail'),

    # ── Service Requests ────────────────────────────────────
    path('service-requests', views.ServiceRequestViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='service-requests'),
    path('service-requests/<str:orderid>', views.ServiceRequestViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='service-request-detail'),

    # ── Order Operations ────────────────────────────────────
    path('convert', views.OrderConversionView.as_view(), name='order-convert'),
    path('counters', views.CounterViewSet.as_view({
        'get': 'list'
    }), name='counters'),

    # ── Payment Links (revenue-side, created against orders) ──
    # Legacy: kuroadmin/payment — Cashfree payment link creation
    # Moved to orders: payment link is an order action (customer pays for their order)
    # The payment *record* (once received) lives in accounts/inward-payments
    path('payment-links', views.PaymentLinkViewSet.as_view({
        'post': 'create'
    }), name='payment-links'),
]
```

**Note:** E-commerce orders exposed as `eshop/orders` (see §6.3 Eshop Domain). Cafe food orders exposed as `cafe/food-orders` (see §6.7). Indent moved to `products/indent` (see §6.4 — stock-driven procurement).

#### 6.2.1 Unified Pipeline View

**Endpoint:** `GET /api/v1/orders/all`

**Purpose:** Single endpoint for cross-type pipeline queries (dashboard, analytics, search).

**Query parameters:**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| `type` | Optional | `estimate`, `in_store`, `tp`, `service`, `eshop`, `all` | Filter by order type |
| `division` | Optional | Division code | Filter by division |
| `bg_code` | Optional | BG code | Filter by business group |
| `status` | Optional | Status value or `all` | Filter by status |
| `date_from` | Optional | ISO date | Filter by created_at >= |
| `date_to` | Optional | ISO date | Filter by created_at <= |
| `customer_id` | Optional | Customer ID | Filter by customer |
| `search` | Optional | String | Full-text search across orderid, customer, products |
| `page` | Optional | Integer (default: 1) | Page number |
| `per_page` | Optional | Integer (default: 50, max: 500) | Items per page |

**Response:**

```json
{
  "status": "SUCCESS",
  "data": [
    {
      "orderid": "EST290010",
      "type": "estimate",
      "status": "confirmed",
      "division": "KURO0001_001",
      "bg_code": "KURO0001",
      "total_amount": 125000.00,
      "customer": {
        "id": "USR001",
        "name": "John Doe"
      },
      "channel": "web",
      "created_at": "2026-04-15T10:30:00Z",
      "updated_at": "2026-04-16T14:00:00Z",
      "links": {
        "converted_to": "KG290010",
        "detail": "/api/v1/orders/estimates/EST290010"
      }
    },
    {
      "orderid": "KG290010",
      "type": "in_store",
      "status": "building",
      "division": "KURO0001_001",
      "bg_code": "KURO0001",
      "total_amount": 125000.00,
      "customer": {
        "id": "USR001",
        "name": "John Doe"
      },
      "channel": "store",
      "created_at": "2026-04-16T14:00:00Z",
      "updated_at": "2026-04-17T09:00:00Z",
      "links": {
        "source_estimate": "EST290010",
        "detail": "/api/v1/orders/in-store/KG290010"
      }
    }
  ],
  "meta": {
    "total": 15925,
    "page": 1,
    "per_page": 50,
    "total_pages": 319,
    "breakdown": {
      "estimates": 4308,
      "in_store_orders": 9162,
      "tp_orders": 229,
      "service_requests": 1625,
      "eshop_orders": 601
    }
  }
}
```

#### 6.2.2 Order Conversion Endpoint

**Endpoint:** `POST /api/v1/orders/convert`

**Purpose:** Atomic estimate → order conversion. Creates order record + detail in a single transaction.

**Request body:**

```json
{
  "estimate_id": "EST290010",
  "order_type": "in_store",
  "detail": {
    "order_date": "2026-04-16",
    "dispatchby_date": "2026-04-23",
    "channel": "store"
  }
}
```

**Response:**

```json
{
  "status": "SUCCESS",
  "data": {
    "orderid": "KG290010",
    "type": "in_store",
    "status": "confirmed",
    "source_estimate": "EST290010",
    "total_amount": 125000.00,
    "created_at": "2026-04-16T14:00:00Z"
  }
}
```

**Implementation:** Single PostgreSQL transaction:
```python
with transaction.atomic():
    # 1. Create core record
    order = Order.objects.create(
        orderid=generate_orderid('in_store'),
        order_type='in_store',
        status='confirmed',
        total_amount=estimate.total_amount,
        customer_id=estimate.customer_id,
        division=estimate.division,
        bg_code=estimate.bg_code,
        billadd=estimate.billadd,
        products=estimate.products,
    )
    # 2. Create detail record
    InStoreOrderDetail.objects.create(
        order=order,
        estimate_ref=estimate.orderid,
        order_date=data['detail']['order_date'],
        dispatchby_date=data['detail']['dispatchby_date'],
    )
    # 3. Update estimate status
    estimate.status = 'converted'
    estimate.save()
```

#### 6.2.3 Type-Specific Response Contracts

Each order type returns core fields + type-specific detail fields:

**In-Store Order detail response:**
```json
{
  "core": {
    "orderid": "KG290010",
    "type": "in_store",
    "status": "building",
    "total_amount": 125000.00,
    "division": "KURO0001_001",
    "bg_code": "KURO0001",
    "customer_id": "USR001",
    "channel": "store",
    "created_at": "2026-04-16T14:00:00Z"
  },
  "detail": {
    "estimate_ref": "EST290010",
    "order_date": "2026-04-16",
    "dispatchby_date": "2026-04-23",
    "amount_due": 25000.00,
    "invoice_generated": false,
    "invoice_no": null,
    "po_ref": "PO001",
    "builds_count": 2
  },
  "links": {
    "source_estimate": "/api/v1/orders/estimates/EST290010",
    "payments": "/api/v1/accounts/inward-payments?orderid=KG290010"
  }
}
```

**E-com Order detail response:**
```json
{
  "core": { ... },
  "detail": {
    "payment_option": "upi",
    "pay_reference": "PAY001",
    "pkg_fees": 500.00,
    "build_fees": 2000.00,
    "shp_fees": 150.00,
    "tax_total": 22500.00,
    "discount": 5000.00,
    "shp_agency": "Delhivery",
    "shp_awb": "AWB001",
    "shp_status": "in_transit",
    "placed_at": "2026-04-16T10:00:00Z",
    "confirmed_at": "2026-04-16T10:05:00Z",
    "build_start": "2026-04-17T09:00:00Z",
    "shipped_at": "2026-04-20T14:00:00Z"
  }
}
```

**Service Request detail response:**
```json
{
  "core": { ... },
  "detail": {
    "sr_no": "SR001",
    "warranty_status": "active",
    "warranty_expiry": "2027-04-16",
    "diagnosis": "GPU replacement required",
    "repair_cost": 15000.00
  }
}
```

---

### 6.3 Eshop Domain

**Purpose:** Online e-commerce — retail PC sales, cart, shipping, customer checkout. Separate from operational orders (estimates, in-store builds, TP orders) which are service-driven.

**Storage:** Unified with orders domain (`orders_core` + `eshop_detail` in PostgreSQL). Separate API prefix to distinguish retail commerce from internal operations.

**Ownership:** `kungos_dj/domains/eshop/` — reuses ViewSets from `kungos_dj/domains/orders/views.py`.

**Auth:** All endpoints require authentication. Customers see only their own orders. Staff/admin see division-scoped orders.

**File:** `kungos_dj/domains/eshop/urls.py`

```python
from django.urls import path
from kungos_dj.domains.orders import views as orders_views

app_name = 'eshop'

urlpatterns = [
    path('orders', orders_views.EcomOrderViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='orders'),
    path('orders/<str:orderid>', orders_views.EcomOrderViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='order-detail'),
]
```

**Permission matrix:**

| Endpoint | Admin | Manager | Staff | Customer |
|----------|-------|---------|-------|----------|
| `GET /eshop/orders` | ✅ All | ✅ Division | ✅ Read | ✅ Own |
| `POST /eshop/orders` | ✅ | ✅ | ❌ | ✅ (checkout) |
| `PATCH /eshop/orders/<id>` | ✅ | ✅ | ❌ | ❌ |

---

### 6.4 Products Domain

**Purpose:** Product catalog, builds, inventory, stock management, fixed asset register.

**File:** `kungos_dj/domains/products/urls.py`

```python
from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Product catalog
    path('catalog', views.ProductViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='catalog'),
    path('catalog/<str:productid>', views.ProductViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='product-detail'),

    # TP Builds (prebuilt PC configurations)
    path('tp-builds', views.TPBuildViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='tp-builds'),

    # Custom builds (gaming eshop)
    path('custom-builds', views.CustomBuildViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='custom-builds'),

    # Components (gaming eshop)
    path('components', views.ComponentViewSet.as_view({
        'get': 'list'
    }), name='components'),

    # Accessories (gaming eshop)
    path('accessories', views.AccessoryViewSet.as_view({
        'get': 'list'
    }), name='accessories'),

    # Presets (build presets)
    path('presets', views.PresetViewSet.as_view({
        'get': 'list'
    }), name='presets'),

    # Inventory (stock register + serial lookups + transfers)
    path('inventory', views.InventoryViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='inventory'),
    path('inventory/<str:pk>', views.InventoryViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='inventory-detail'),

    # Asset register (fixed assets — replaces former /products/stock)
    path('assets', views.AssetRegisterViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='assets'),
    path('assets/<str:pk>', views.AssetRegisterViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='asset-detail'),
    path('assets/calculate-depreciation', views.AssetRegisterViewSet.as_view({
        'post': 'calculate_depreciation'
    }), name='calculate-depreciation'),
    path('assets/summary', views.AssetRegisterViewSet.as_view({
        'get': 'summary'
    }), name='asset-summary'),
    path('assets/tax-blocks', views.AssetRegisterViewSet.as_view({
        'get': 'tax_blocks'
    }), name='tax-blocks'),
    path('assets/depreciation-defaults', views.AssetRegisterViewSet.as_view({
        'get': 'depreciation_defaults'
    }), name='depreciation-defaults'),

    # Stock audit (audit trail for stock changes)
    path('stock-audit', views.StockAuditViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='stock-audit'),

    # Indent (purchase requisition — triggered by stock levels, stays in Mongo)
    path('indent', views.IndentViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='indent'),

    # Temp products (draft products)
    path('temp-products', views.TempProductViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='temp-products'),
]
```

#### 6.4.1 Asset Register Endpoint

**Purpose:** Fixed asset management — laptops, furniture, equipment with depreciation tracking per Indian Income Tax Act (Section 35).

**Collection:** `asset_register` (MongoDB)

**Permission:** `inventory` (read/write)

---

**Asset Document Schema**

```json
{
    "asset_no": "FA000001",
    "name": "Dell Latitude 5540",
    "category": "laptop",
    "serial_no": "8XJ2K4L5",
    "vendor": "VEN001",
    "invoice_no": "INV-2024-001",
    "purchase_cost": 85000,
    "purchase_date": "2024-03-15",
    "induction_date": "2024-03-20",
    "salvage_value": 5000,
    "warranty": "3 years",
    "bg_code": "BG001",
    "division_code": "DIV001",
    "branch_code": "BR001",
    "cost_center": "CC-IT-01",
    "department": "Engineering",
    "assigned_to": "EMP001",
    "status": "active",
    "delete_flag": false,
    "depreciation": {
        "block": "BLOCK_I",
        "block_name": "Computers & IT Equipment",
        "method": "wdv",
        "rate": 100,
        "annual_depreciation": 80000,
        "monthly_depreciation": 6666.67,
        "accumulated_depreciation": 20000,
        "book_value": 65000,
        "periods_charged": 3,
        "last_calculated": "2024-06-30"
    },
    "created_by": "EMP001",
    "created_date": "2024-03-20T10:30:00+05:30",
    "updated_by": "EMP001",
    "updated_date": "2024-06-30T12:00:00+05:30"
}
```

---

**GET /products/assets** — List assets

Query params:
| Param | Type | Description |
|-------|------|-------------|
| `bg_code` | string | Filter by business group code |
| `division_code` | string | Filter by division code (aggregates all branches) |
| `branch_code` | string | Filter by branch code |
| `asset_no` | string | Filter by asset number |
| `serial_no` | string | Filter by serial number |
| `category` | string | Filter by category (laptop, furniture, equipment, etc.) |
| `vendor` | string | Filter by vendor code |
| `invoice_no` | string | Filter by purchase invoice number |
| `cost_center` | string | Filter by cost center |
| `department` | string | Filter by department |
| `assigned_to` | string | Filter by assigned person |
| `status` | string | Filter by status (active, disposed, under_maintenance) |

Hierarchical scoping (mutually exclusive, highest specificity wins):
- `?branch_code=BR001` → branch-level assets only
- `?division_code=DIV001` → all branches in division
- `?bg_code=BG001` → all divisions in BG
- no filter → tenant-wide (scoped by tenant middleware)

Response:
```json
{
    "status": "success",
    "data": [ /* asset documents */ ]
}
```

---

**POST /products/assets** — Create or update asset

Create (no query params):
```json
{
    "name": "Dell Latitude 5540",
    "category": "laptop",
    "serial_no": "8XJ2K4L5",
    "vendor": "VEN001",
    "invoice_no": "INV-2024-001",
    "purchase_cost": 85000,
    "purchase_date": "2024-03-15",
    "induction_date": "2024-03-20",
    "salvage_value": 5000,
    "branch_code": "BR001",
    "division_code": "DIV001",
    "cost_center": "CC-IT-01",
    "department": "Engineering",
    "assigned_to": "EMP001"
}
```

Depreciation is **auto-populated** from Indian tax law defaults based on `category`:
| Category | Tax Block | Rate | Method | Life |
|----------|-----------|------|--------|------|
| laptop, desktop, server | Block I | 100% | WDV | 3 yrs |
| ac_split, generator, cctv | Block II | 40% | WDV | 5-15 yrs |
| building, interior_work | Block III | 6% | SL | 10-50 yrs |
| desk, chair, cabinet, sofa | Block IV | 10% | SL | 10 yrs |
| car, suv, motorcycle | Block V | 20% | WDV | 5 yrs |
| delivery_van, truck | Block VI | 10% | WDV | 10 yrs |
| tools, workshop_equipment | Block VII | 20% | WDV | 5-10 yrs |

Override by sending explicit `depreciation` object in request body.

Response:
```json
{
    "status": "success",
    "data": {
        "inserted_id": "...",
        "asset_no": "FA000001",
        "status": "created"
    }
}
```

Update (`?asset_no=FA000001`):
```json
{ "assigned_to": "EMP002", "status": "under_maintenance" }
```

---

**PATCH /products/assets/<id>** — Update asset

**DELETE /products/assets/<id>** — Soft delete (marks `delete_flag=true`, `status=disposed`)

---

**POST /products/assets/calculate-depreciation** — Batch depreciation run

Charges depreciation from `induction_date` (or `last_calculated`) to `as_of` date.
Respects WDV (on book value) vs SL (fixed amount). Never depreciates below `salvage_value`.

Body:
```json
{
    "as_of": "2024-06-30",
    "branch_code": "BR001"  // optional — scope to branch/division
}
```

Response:
```json
{
    "status": "success",
    "data": {
        "as_of": "2024-06-30",
        "assets_updated": 45,
        "method": "Section 35 (WDV/SL per tax block)"
    }
}
```

---

**GET /products/assets/summary** — Hierarchical asset summary

Aggregates assets by branch_code → division_code → bg_code.

Query params:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | string | `division` | `branch`, `division`, or `bg` |
| `status` | string | `active` | Filter by status |

Response:
```json
{
    "status": "success",
    "data": {
        "level": "division",
        "status": "active",
        "groups": [
            {"_id": "DIV001", "count": 45, "total_cost": 1200000, "total_book_value": 980000, "total_depreciation": 220000},
            {"_id": "DIV002", "count": 23, "total_cost": 650000, "total_book_value": 520000, "total_depreciation": 130000}
        ],
        "bg_totals": {"count": 68, "total_cost": 1850000, "total_book_value": 1500000, "total_depreciation": 350000}
    }
}
```

---

**GET /products/assets/tax-blocks** — Reference: all tax blocks + asset classes

Returns `TAX_BLOCKS` (7 blocks) and `ASSET_CLASS_DEFAULTS` (50+ categories) for frontend dropdowns.

---

**GET /products/assets/depreciation-defaults** — Tax defaults for a category

Query params:
| Param | Type | Description |
|-------|------|-------------|
| `category` | string | Asset class (e.g. `laptop`, `desk`, `ac_split`) |

Response:
```json
{
    "status": "success",
    "data": {
        "block": "BLOCK_I",
        "block_name": "Computers & IT Equipment",
        "rate": 100,
        "method": "wdw",
        "useful_life_years": 3,
        "description": "Computers, printers, scanners, fax machines, servers, routers, switches, data centre equipment"
    }
}
```

---

### 6.5 Vendors Domain

**Purpose:** Vendor management — shared resource used by accounts, orders, products.

**File:** `kungos_dj/domains/vendors/urls.py`

```python
from django.urls import path
from . import views

app_name = 'vendors'

urlpatterns = [
    # Vendor list (replaces kuroadmin/vendors + kurostaff/vendors)
    path('list', views.VendorViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='vendor-list'),
    path('list/<str:vendor_code>', views.VendorViewSet.as_view({
        'get': 'retrieve', 'patch': 'update'
    }), name='vendor-detail'),

    # States (GST state codes)
    path('states', views.StateViewSet.as_view({
        'get': 'list'
    }), name='states'),
]
```

#### 6.5.1 Vendor List Response

**Endpoint:** `GET /api/v1/vendors/list`

**Query parameters:**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| `division` | Optional | Division code | Filter by division |
| `vendor_code` | Optional | Vendor code | Lookup by code |
| `page` | Optional | Integer | Page number |
| `per_page` | Optional | Integer (default: 50) | Items per page |

**Response:**

```json
{
  "status": "SUCCESS",
  "data": [
    {
      "vendor_code": "AMAZ290010",
      "name": "Amazon Web Services",
      "gstin": "29AAMCA1234A1Z5",
      "state": "KA",
      "contact_person": "John Doe",
      "email": "vendor@example.com",
      "phone": "+91-9876543210",
      "address": "123 Main St, Bangalore, KA 560001",
      "division": "DIV001",
      "active": true,
      "delete_flag": false,
      "gstdetails": [
        {
          "gstin": "29AAMCA1234A1Z5",
          "state": "KA",
          "address": "123 Main St, Bangalore"
        }
      ],
      "created_date": "2024-01-15T10:30:00Z",
      "updated_date": "2024-06-01T14:20:00Z"
    }
  ],
  "meta": {
    "total": 150,
    "page": 1,
    "per_page": 50,
    "total_pages": 3
  }
}
```

**Key fields for lookup:**
- `vendor_code` — unique identifier (used by sundry creditors/debtors as keys)
- `name` — display name (used in UI tables)
- `gstin` — GST identification number
- `division` — tenant division scope

---

### 6.6 Teams Domain

**Purpose:** Employee management, attendance, payroll.

**File:** `kungos_dj.domains.teams/urls.py`

```python
from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    # Employees
    path('employees', views.EmployeeViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='employees'),
    path('employees/<str:emp_id>', views.EmployeeViewSet.as_view({
        'get': 'retrieve', 'patch': 'update', 'delete': 'destroy'
    }), name='employee-detail'),

    # Attendance
    path('attendance', views.AttendanceViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='attendance'),

    # Dashboard (HR dashboard data)
    path('dashboard', views.HRDashboardView.as_view(), name='hr-dashboard'),

    # Salary
    path('salary', views.SalaryViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='salary'),
]
```

---

### 6.7 Cafe Domain

**Purpose:** Gaming cafe management — stations, sessions, wallet, pricing.

**Architecture note:** Cafe gaming sessions (`caf_platform_sessions`) are **separate** from the unified orders table. Sessions are time-based billing (per-minute) with real-time WebSocket requirements. Cafe **food** orders are exposed under `cafe/food-orders` (same Django app as sessions, multi-tenant via `bg_code`).

**Data store:** All cafe data in **PostgreSQL** `caf_platform_*` tables (14 tables). NOT MongoDB.

```
PostgreSQL caf_platform_* (14 tables):
├── caf_platform_cafes            — Cafe registry (bg_code, div_code, branch_code)
├── caf_platform_stations         — PC stations (cafe FK, zone, status, tenant fields)
├── caf_platform_sessions         — Gaming sessions (station FK, billing, timeline)
├── caf_platform_session_leases   — Lease versioning (offline resilience)
├── caf_platform_station_commands — Cloud → station command delivery
├── caf_platform_station_events   — Append-only audit stream
├── caf_platform_wallets          — Shared wallet (bridges cafe/esports/retail)
├── caf_platform_wallet_transactions — Immutable transaction ledger
├── caf_platform_price_plans      — Zone-based pricing (peak/weekend multipliers)
├── caf_platform_member_plans     — Edge/Titan/S membership tiers
├── caf_platform_games            — Game catalog
├── caf_platform_users            — Cafe user profiles
├── caf_platform_walkins          — Walk-in customer records
└── caf_platform_auth_tokens      — Auth token storage
```

**Tenant fields:** Every `caf_platform_*` table carries `bg_code`. Tables carry full tenant cascade or resolve via FK as shown below.

**Per-table tenant strategy:**

| Table | Tenant fields | Resolution | Notes |
|-------|--------------|------------|-------|
| `caf_platform_cafes` | `bg_code`, `div_code`, `branch_code` | Direct | Authoritative tenant source |
| `caf_platform_stations` | `bg_code`, `div_code`, `branch_code` | Direct + `cafe` FK | Denormalized from Cafe |
| `caf_platform_sessions` | `bg_code` | `cafe` FK, `station` FK | Full cascade via `session.cafe` |
| `caf_platform_session_leases` | `bg_code` | `station` FK | Full cascade via `lease.station.cafe` |
| `caf_platform_station_commands` | `bg_code` | `station` FK | Full cascade via `command.station.cafe` |
| `caf_platform_station_events` | `bg_code` | `station` FK | Full cascade via `event.station.cafe` |
| `caf_platform_price_plans` | `bg_code` | `cafe` FK | Full cascade via `plan.cafe` |
| `caf_platform_member_plans` | `bg_code`, `div_code`, `branch_code` | Direct | Plans scoped to tenant |
| `caf_platform_games` | `bg_code` | `cafe` FK | Full cascade via `game.cafe` |
| `caf_platform_walkins` | `bg_code`, `div_code`, `branch_code` | Direct | No cafe FK — phone-keyed, tenant-scoped |
| `caf_platform_wallets` | — | `walkin` FK or `user` FK | Tenant via owner, not stored redundantly |
| `caf_platform_wallet_transactions` | — | `wallet` FK | Tenant via `transaction.wallet → walkin/user` |
| `caf_platform_users` | `bg_code`, `div_code`, `branch_code` | Direct | Branch-registered cafe users |
| `caf_platform_auth_tokens` | `bg_code` | `user` FK → CustomUser | Full cascade via `token.user` |

**Wallet ownership model:** `CafeWallet` has two nullable FKs — `walkin` (`CafeWalkin`) and `user` (`CafeUser`) — with a `CheckConstraint` requiring exactly one. Tenant scope resolves through the owner relation, not stored redundantly on the wallet row. This avoids sync bugs when a person's branch changes.

**Walk-in identity:** `CafeWalkin` uses `walkin_id` (stable, generated, e.g. `WLN0001`) as the primary lookup key. `primary_phone` + tenant fields have a composite `UniqueConstraint`. `secondary_phones` stored as JSON array. Same person at different branches = different records.

**Uniqueness rules:**
- `CafeWalkin`: `UniqueConstraint(['primary_phone', 'bg_code', 'div_code', 'branch_code'])`
- `CafeWallet`: `UniqueConstraint(['walkin_id', 'bg_code'])` or `UniqueConstraint(['user_id', 'bg_code'])`
- `CafeUser`: `UniqueConstraint(['user_id', 'bg_code', 'div_code', 'branch_code'])`

**Rationale for PostgreSQL (not MongoDB):** Relational integrity (FKs between stations→sessions→wallets), ACID transactions for session billing + wallet deduction, complex queries (revenue reports, station utilization, session timelines), row-level locking for wallet balance updates.

**Payment boundary (`cafe/payments` vs `accounts/inward-payments`):**

`cafe/payments` handles **cafe-specific payment recording** — wallet deductions, session billing settlements, kiosk cash collections. These are operational records scoped to a cafe branch.

`accounts/inward-payments` handles **financial ledger entries** — the accounting record that feeds sundry debtors, revenue reports, and financial statements. A cafe payment *may* create a corresponding inward-payment record for financial reconciliation, but the primary source of truth for cafe billing is `cafe/payments`.

**Rule:** Cafe operations read from `cafe/payments`. Financial reports aggregate from `accounts/inward-payments`. Cross-domain sync is handled by the accounts service consuming cafe payment events.

```
orders_core + detail tables  — estimates, in_store, tp, service, eshop
caf_platform_sessions        — gaming sessions (time-based, real-time, separate)
cafe_food_detail             — cafe food orders (in cafe/ app, not orders/)
```

**File:** `cafe/urls.py` (separate Django app, shared multi-tenant platform)

```python
from django.urls import path
from . import views

app_name = 'cafe'

urlpatterns = [
    # Customer
    path('customer/register', views.customer_register, name='customer-register'),
    path('customer/lookup', views.customer_lookup, name='customer-lookup'),
    path('customer/profile', views.customer_profile, name='customer-profile'),

    # Wallet
    path('wallet/balance', views.wallet_balance, name='wallet-balance'),
    path('wallet/recharge', views.wallet_recharge, name='wallet-recharge'),
    path('wallet/transactions', views.wallet_transactions, name='wallet-transactions'),

    # Stations
    path('stations', views.StationListView.as_view(), name='stations-list'),
    path('stations/<int:id>', views.StationDetailView.as_view(), name='stations-detail'),
    path('stations/<int:id>/status', views.StationStatusUpdateView.as_view(), name='stations-status'),

    # Sessions
    path('sessions/start', views.session_start, name='session-start'),
    path('sessions/pause', views.session_pause, name='session-pause'),
    path('sessions/resume', views.session_resume, name='session-resume'),
    path('sessions/end', views.session_end, name='session-end'),
    path('sessions/extend', views.session_extend, name='session-extend'),
    path('sessions/active', views.session_active, name='session-active'),

    # Pricing
    path('pricing/rules', views.pricing_rules, name='pricing-rules'),
    path('pricing/calculate', views.pricing_calculate, name='pricing-calculate'),

    # Games
    path('games', views.game_library, name='game-library'),

    # Members
    path('members/plans', views.member_plans, name='member-plans'),
    path('members/upgrade', views.member_upgrade, name='member-upgrade'),

    # Dashboard
    path('dashboard/overview', views.dashboard_overview, name='dashboard-overview'),
    path('dashboard/revenue', views.dashboard_revenue, name='dashboard-revenue'),
    path('dashboard/utilization', views.dashboard_utilization, name='dashboard-utilization'),

    # Payments
    path('payments', views.cafe_payments, name='cafe-payments'),
    path('payments/record', views.cafe_payments_record, name='cafe-payments-record'),

    # Food Orders (from kgorders typeof='food', stored in cafe_food_detail)
    path('food-orders', views.CafeFoodOrderViewSet.as_view({
        'get': 'list', 'post': 'create'
    }), name='food-orders'),
    path('food-orders/<str:orderid>', views.CafeFoodOrderViewSet.as_view({
        'get': 'retrieve', 'patch': 'update'
    }), name='food-order-detail'),
]
```

---

### 6.8 Esports Domain

**Purpose:** Esports tournaments, players, teams.

**File:** `rebellion/esports/urls.py` (moved from `rebellion/urls.py`)

```python
from django.urls import path
from . import views

app_name = 'esports'

urlpatterns = [
    path('tournaments', views.tournaments, name='tournaments'),
    path('players', views.players, name='players'),
    path('teams', views.teams, name='teams'),
    path('tourney-register', views.tourneyregister, name='tourney-register'),
    path('gamers', views.gamers, name='gamers'),
]
```

---

### 6.9 Search Domain

**Purpose:** MeiliSearch index operations.

**Authorization:** Read endpoints (`search`, `index`) require `IsAuthenticated`. Write endpoints (`update-document`, `delete-document`) require `search.manage` permission. Destructive endpoints (`drop-index`, `drop-all`) require SysAdmin role.

**File:** `kungos_dj/domains/search/urls.py`

```python
from django.urls import path
from . import views

app_name = 'search'

urlpatterns = [
    path('index', views.millie_index, name='search-index'),
    path('update-document', views.update_document, name='update-document'),
    path('delete-document', views.delete_document, name='delete-document'),
    path('search', views.search_documents, name='search'),
    path('drop-index', views.drop_index, name='drop-index'),
    path('drop-all', views.drop_all_indexes, name='drop-all'),
]
```

---

### 6.10 Shared Domain

**Purpose:** Shared utilities — home data, document generation, SMS, misc.

**Authorization:** All endpoints require `IsAuthenticated`. Admin-portal endpoints require `shared.admin` permission.

**File:** `kungos_dj/domains/shared/urls.py`

```python
from django.urls import path
from . import views

app_name = 'shared'

urlpatterns = [
    path('home', views.home_data, name='home'),
    path('doc-generator', views.doc_generator, name='doc-generator'),
    path('sms-headers', views.sms_headers, name='sms-headers'),
    path('store-data', views.store_data, name='store-data'),
    path('misc-data', views.misc_data, name='misc-data'),
    path('admin-portal', views.admin_portal, name='admin-portal'),
    path('kurodata', views.kurodata, name='kurodata'),
]
```

### 6.11 Admin Domain (MongoDB Operations)

**Purpose:** SysAdmin-only MongoDB administration — collection management.

**Authorization:** All endpoints require SysAdmin role (`admin.mongo_manage` permission).

**File:** `kungos_admin/urls.py` (appended to existing admin routes)

```python
# MongoDB administration (SysAdmin only)
path('mongo/create-collection', views.create_collection, name='admin-create-collection'),
path('mongo/get-collection', views.get_collection, name='admin-get-collection'),
```
```

---

## 7. Migration Mapping

### 7.0 Migration Strategy

**Rule:** Legacy aliases with deprecation headers during migration window. Hard 410 Gone only after all frontend pages are verified on new paths.

**Migration phases:**

| Phase | Action | Duration |
|-------|--------|----------|
| **A — Dedup** | Merge duplicate endpoints (vendors, tporders, kgorders, indent, inwardinvoices) | 1–2 weeks |
| **B — Domain move** | Create new domain URLs. Wire legacy aliases → same view functions. Add deprecation headers. | 2–4 weeks |
| **C — Frontend migrate** | Update all frontend pages to new paths. Verify E2E tests pass. | 2–3 weeks |
| **D — Cutover** | Remove legacy aliases. Old paths return 410 Gone. | Day N |

**Deprecation header on legacy aliases:**

```python
response = Response(data)
response['Deprecation'] = 'true'
response['Sunset'] = '2026-08-01'  # removal date
response['Link'] = '<https://api.kurocadence.com/api/v1/vendors/list>; rel=successor-version'

### 7.1 Accounts Domain

| Current | Target |
|---------|--------|
| `kuroadmin/inwardinvoices` + `kurostaff/inwardinvoices` | `accounts/inward-invoices` |
| `kuroadmin/outwardinvoices` | `accounts/outward-invoices` |
| `kuroadmin/inwardpayments` | `accounts/inward-payments` |
| `kuroadmin/outwardpayments` | `accounts/outward-payments` |
| `kuroadmin/paymentvouchers` | `accounts/payment-vouchers` |
| `kuroadmin/purchaseorders` | `accounts/purchase-orders` |
| `kuroadmin/outwardcreditnotes` | `accounts/outward-credit-notes` | Renamed for symmetry |
| `kuroadmin/outwarddebitnotes`  | `accounts/outward-debit-notes`  | Renamed for symmetry |
| `kurostaff/inwardcreditnotes` | `accounts/inward-credit-notes` |
| `kurostaff/inwarddebitnotes` | `accounts/inward-debit-notes` |
| `kuroadmin/accounts` | `accounts/accounts` |
| `kuroadmin/financials` | `accounts/financials` |
| `kuroadmin/itc-gst` | `accounts/itc-gst` |
| `kuroadmin/analytics` | `accounts/analytics` |
| `kuroadmin/settlements` | `accounts/settlements` |
| `kuroadmin/bulk_payments` | `accounts/bulk-payments` |
| `kuroadmin/exportinwardinvoices` | `accounts/export/inward-invoices` |
| `kuroadmin/exportoutwardinvoices` | `accounts/export/outward-invoices` |
| `kuroadmin/exportinwardpayments` | `accounts/export/inward-payments` |
| `kuroadmin/sales` | `accounts/revenue` | Renamed + expanded (all income sources) |
| `kuroadmin/purchases` | `accounts/expenditure` | Renamed + expanded (all expense categories) |

### 7.2 Orders Domain

**Storage migration:** 4 Mongo collections + 1 PG table → `orders_core` + 6 detail tables (PostgreSQL). Cafe gaming sessions remain in `caf_platform_sessions` (already PG).

| Current | Target | Notes |
|---------|--------|-------|
| `kuroadmin/estimates` | `orders/estimates` | Mongo → `orders_core` + `estimate_detail` |
| `kuroadmin/servicerequest` + `kuroadmin/kuroservices` | `orders/service-requests` | Mongo → `orders_core` + `service_detail` |
| `kuroadmin/tporders` + `kurostaff/tporders` | `orders/tp-orders` | Mongo → `orders_core` + `tp_order_detail` |
| `kuroadmin/kgorders` + `kurostaff/kgorders` | `orders/in-store` | Mongo → `orders_core` + `in_store_detail` |
| `kurostaff/updateorder` | `PATCH /orders/in-store/<id>` | Removed — standard PATCH replaces it |
| `kurostaff/orderconversion` | `orders/convert` | Atomic transaction (core + detail) |
| `kurostaff/counters` | `orders/counters` | Unchanged |
| — | `orders/all` | **NEW** — unified pipeline view |
| — | `orders/pipeline` | **NEW** — pipeline analytics |
| — | `orders/analytics` | **NEW** — cross-type analytics |
| — | `eshop/orders` | **NEW** — legacy PG Orders → `eshop_detail` |
| — | `cafe/food-orders` | **NEW** — cafe food orders (from kgorders typeof='food', in cafe/ app) |
| `kuroadmin/payment` | `orders/payment-links` | Moved to orders (Cashfree link creation against orderid) |

**Migration validation:** See `~/llm-wiki/orders-migration-plan.md` for snapshot → validate → fix → deploy process.

### 7.3 Products Domain

| Current | Target |
|---------|--------|
| `kuroadmin/products` | `products/catalog` |
| `kuroadmin/tpbuilds` | `products/tp-builds` |
| `kuroadmin/presets` | `products/presets` |
| `kuroadmin/tempproducts` | `products/temp-products` |
| `kuroadmin/addproduct` | `POST /products/catalog` | merge into catalog create |
| `kurostaff/inventory` | `products/inventory` | Stock register + serial lookups + transfers |
| `kurostaff/stock` | `products/assets` | **Replaced** — fixed asset register with depreciation |
| `kuroadmin/stockaudit` | `products/stock-audit` |
| `kuroadmin/indent` + `kurostaff/indent` | `products/indent` | Stock-driven procurement (stays in Mongo) |
| — | `products/assets/calculate-depreciation` | **NEW** — batch depreciation run |
| — | `products/assets/summary` | **NEW** — hierarchical asset summary |
| — | `products/assets/tax-blocks` | **NEW** — reference: tax blocks + asset classes |
| — | `products/assets/depreciation-defaults` | **NEW** — defaults per category |

### 7.4 Vendors Domain

| Current | Target |
|---------|--------|
| `kuroadmin/vendors` + `kurostaff/vendors` | `vendors/list` |
| `kurostaff/states` | `vendors/states` |

### 7.5 Teams Domain

| Current | Target |
|---------|--------|
| `kuroadmin/employees` (+ empadminlist, empdashlist) | `teams/employees` |
| `kuroadmin/empattendance` + `kurostaff/emp_attendance` | `teams/attendance` |
| `kurostaff/emp_dashboard` | `teams/dashboard` |

### 7.6 Cafe & Esports Domain

| Current | Target |
|---------|--------|
| `rebellion/cafe/*` | `cafe/*` |
| `rebellion/tournaments` | `esports/tournaments` |
| `rebellion/players` | `esports/players` |
| `rebellion/teams` | `esports/teams` |
| `rebellion/tourneyregister` | `esports/tourney-register` |
| `rebellion/gamers` | `esports/gamers` |

### 7.7 Search & Shared Domain

| Current | Target |
|---------|--------|
| `kuroadmin/millieindex` | `search/index` |
| `kuroadmin/search` | `search/search` |
| `kuroadmin/updatedocument` | `search/update-document` |
| `kuroadmin/deletedocument` | `search/delete-document` |
| `kuroadmin/drop` | `search/drop-index` |
| `kuroadmin/home` | `shared/home` |
| `kuroadmin/doc_generator` | `shared/doc-generator` |
| `kuroadmin/smsheadersapi` | `shared/sms-headers` |
| `kuroadmin/storedata` | `shared/store-data` |
| `kuroadmin/miscdata` | `shared/misc-data` |
| `kuroadmin/adminportal` | `shared/admin-portal` |
| `kuroadmin/kurodata` | `shared/kurodata` |
| `kuroadmin/createcollection` | `shared/create-collection` |
| `kuroadmin/getcollection` | `shared/get-collection` |

---

## 8. Error Response Standard

### 8.1 Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTH_REQUIRED` | 401 | Authentication credentials missing or invalid |
| `PERMISSION_DENIED` | 403 | User lacks permission for this action |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 400 | Request validation failed |
| `TENANT_MISSING` | 400 | Tenant context (bg_code) not resolved |
| `RATE_LIMITED` | 429 | Rate limit exceeded |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### 8.2 Error Response Format

```json
{
  "status": "FAILURE",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "vendor_code": ["This field is required"],
      "gstin": ["Invalid GSTIN format"]
    }
  }
}
```

### 8.3 Implementation

```python
from rest_framework.response import Response
from rest_framework import status

def error_response(exception, code="INTERNAL_ERROR", http_status=500):
    """Standard error response."""
    return Response(
        {
            "status": "FAILURE",
            "error": {
                "code": code,
                "message": str(exception),
                "details": {}
            }
        },
        status=http_status
    )

# Usage
try:
    vendor = VendorRepository.get(vendor_code, bg_code=request.bg_code)
except VendorNotFound:
    return error_response("Vendor not found", code="NOT_FOUND", http_status=404)
except PermissionError:
    return error_response("Access denied", code="PERMISSION_DENIED", http_status=403)
```

---

## 9. Pagination & Filtering

### 9.1 Pagination

**Rule:** All list endpoints use page-number pagination. Default: 50 items per page.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `per_page` | integer | 50 | Items per page (max: 500) |

**Response meta:**

```json
{
  "meta": {
    "total": 150,
    "page": 1,
    "per_page": 50,
    "total_pages": 3
  }
}
```

### 9.2 Filtering

**Rule:** All list endpoints support standard filters via query parameters.

| Filter | Type | Example | Description |
|--------|------|---------|-------------|
| `division` | string | `?division=DIV001` | Filter by division |
| `branch` | string | `?branch=BR001` | Filter by branch |
| `status` | string | `?status=active` | Filter by status |
| `date_from` | date | `?date_from=2024-01-01` | Filter from date |
| `date_to` | date | `?date_to=2024-12-31` | Filter to date |
| `search` | string | `?search=amazon` | Full-text search |
| `sort` | string | `?sort=-created_date` | Sort field (- = desc) |

### 9.3 Implementation

```python
from rest_framework.pagination import PageNumberPagination

class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'per_page'
    max_page_size = 500

class VendorViewSet(viewsets.ModelViewSet):
    pagination_class = StandardPagination
    # ...
```

---

## 10. OpenAPI Documentation

### 10.1 Schema Generation

**Rule:** All endpoints documented via drf-spectacular. Auto-generated OpenAPI 3.0 schema.

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'KungOS API',
    'DESCRIPTION': 'Unified API for KTeam admin platform, gaming eshop, and cafe management',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'accounts', 'description': 'Financial operations'},
        {'name': 'orders', 'description': 'Order management (estimates, in-store, tp, service)'},
        {'name': 'eshop', 'description': 'E-commerce (online retail orders)'},
        {'name': 'products', 'description': 'Product catalog'},
        {'name': 'vendors', 'description': 'Vendor management'},
        {'name': 'teams', 'description': 'Teams (onboarding, payroll, employees)'},
        {'name': 'cafe', 'description': 'Cafe platform (sessions, wallet, food-orders)'},
        {'name': 'esports', 'description': 'Esports'},
        {'name': 'search', 'description': 'Search'},
        {'name': 'shared', 'description': 'Shared utilities'},
    ],
}
```

### 10.2 Endpoint Documentation

```python
from drf_spectacular.utils import extend_schema, extend_schema_view
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse

@extend_schema_view(
    list=extend_schema(
        summary='List vendors',
        description='Retrieve paginated list of vendors. Scoped by user division access.',
        parameters=[
            OpenApiParameter('division', OpenApiTypes.STR, description='Filter by division'),
            OpenApiParameter('vendor_code', OpenApiTypes.STR, description='Lookup by vendor code'),
        ],
        responses={
            200: OpenApiResponse(response=VendorListSerializer, many=True),
            403: OpenApiResponse(response=ErrorSerializer),
        },
        tags=['vendors'],
    ),
)
class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer
    # ...
```

---

## 11. Testing Requirements

### 11.1 Unit Tests

**Rule:** Every view function has unit tests covering:
- Happy path (valid request → correct response)
- Auth failure (no token → 401)
- Permission failure (insufficient role → 403)
- Validation failure (bad data → 400)
- Not found (invalid ID → 404)

```python
# tests/domains/vendors/test_views.py
class VendorListViewTest:
    def test_list_authenticated(self, client, authenticated_user):
        response = client.get('/api/v1/vendors/list')
        assert response.status_code == 200
        assert response.json()['status'] == 'SUCCESS'
        assert isinstance(response.json()['data'], list)

    def test_list_unauthenticated(self, client):
        response = client.get('/api/v1/vendors/list')
        assert response.status_code == 401

    def test_list_permission_denied(self, client, staff_user):
        response = client.get('/api/v1/vendors/list')
        assert response.status_code == 403

    def test_list_with_division_filter(self, client, authenticated_user):
        response = client.get('/api/v1/vendors/list?division=DIV001')
        assert all(v['division'] == 'DIV001' for v in response.json()['data'])
```

### 11.2 Integration Tests

**Rule:** Every domain has integration tests covering:
- Full request → response cycle
- Tenant context isolation
- Cross-domain operations (e.g., order creation → inventory update)

### 11.3 E2E Tests

**Rule:** Playwright E2E tests cover:
- All sidebar navigation routes resolve
- All CRUD operations work end-to-end
- Permission boundaries enforced (admin vs staff vs customer)

### 11.4 Static Route Tests

**Rule:** `test_pages.py` validates all static routes after migration.

### 11.5 Dynamic Route Tests

**Rule:** `test_dynamic_pages.py` validates all dynamic routes with real IDs after migration.

### 11.6 Permission Coverage Tests

**Rule:** Automated test validates every URL pattern against the permission matrix (§4.3). Endpoints with `AllowAny` must appear in the exception whitelist (§4.4).

```python
# tests/test_permission_coverage.py
from django.urls import get_resolver

ALLOW_ANY_WHITELIST = {
    'auth/login',
    'auth/refresh',
    'health-check',
    'ping',
    'schema',
    'swagger-ui',
    'cafe-customer-register',
    'cafe-customer-lookup',
    'session-start',
}

def test_all_endpoints_have_permissions():
    """Every URL must have an explicit permission class."""
    urls = get_resolver(urlconf='backend.urls')
    for pattern in urls.url_patterns:
        if hasattr(pattern, 'callback'):
            view = pattern.callback
            perms = getattr(view, 'permission_classes', None)
            name = getattr(pattern, 'name', None)
            if name in ALLOW_ANY_WHITELIST:
                continue  # whitelisted public endpoint
            assert perms is not None, f"{pattern.pattern} (name={name}) has no permission_classes"
```

**Rule:** Unlisted `AllowAny` endpoints fail CI. The whitelist is maintained in `test_permission_coverage.py` and reviewed during code review.

---

## Appendix A: Frontend Migration Checklist

### A.1 API Path Updates

**File:** `src/lib/api.jsx` (if paths are hardcoded)

```js
// Before
export const ENDPOINTS = {
  VENDORS: 'kuroadmin/vendors',
  INWARD_INVOICES: 'kurostaff/inwardinvoices',
  TP_ORDERS: 'kuroadmin/tporders',
}

// After
export const ENDPOINTS = {
  VENDORS: 'vendors/list',
  INWARD_INVOICES: 'accounts/inward-invoices',
  TP_ORDERS: 'orders/tp-orders',
}
```

### A.2 React Query Key Updates

**File:** `src/queryKeys.js` (if query keys reference endpoint paths)

```js
// Before
export const queryKeys = {
  vendors: ['kuroadmin-vendors'],
  inwardInvoices: ['kurostaff-inwardinvoices'],
}

// After
export const queryKeys = {
  vendors: ['vendors'],
  inwardInvoices: ['accounts', 'inward-invoices'],
}
```

### A.3 Page-by-Page Migration

| Page | Old Endpoint | New Endpoint | File |
|------|-------------|--------------|------|
| VendorsList | `kuroadmin/vendors` | `vendors/list` | `src/pages/Accounts/VendorsList.jsx` |
| InvoiceCreate | `kurostaff/vendors` | `vendors/list` | `src/pages/Accounts/InvoiceCreate.jsx` |
| Ledgers | `kuroadmin/accounts` | `accounts/accounts` | `src/pages/Accounts/Ledgers.jsx` |
| OrdersList | `kurostaff/tporders` | `orders/tp-orders` | `src/pages/Orders/OrdersList.jsx` |
| InwardDebitNotes | `kurostaff/inwarddebitnotes` | `accounts/inward-debit-notes` | `src/pages/InwardDebitNotes.jsx` |
| CreateOutwardDNote | `kurostaff/vendors` | `vendors/list` | `src/pages/CreateOutwardDNote.jsx` |
| IndentList | `kurostaff/indent` | `products/indent` | `src/pages/IndentList.jsx` |

---

## Appendix B: Effort Estimate

| Phase | Task | Effort | Dependencies |
|-------|------|--------|--------------|
| **A** | Deduplicate 5 endpoint pairs | 16–24h | None |
| **B** | Migrate 80+ endpoints to domains | 48–72h | Phase A |
| **B** | Create domain module structure | 8–12h | Phase A |
| **C** | Frontend path migration | 24–36h | Phase B |
| **C** | E2E test updates | 8–12h | Phase C |
| **D** | OpenAPI schema validation | 4–8h | Phase D |
| **Gaming** | Merge gaming backend apps | 28–36h | Phase 1 complete |
| **Cafe** | Move cafe from rebellion/ | 8–12h | Phase 4 complete |
| **Total** | | **140–212h** | |

---

## Appendix C: Vendor Lookup Fix (Immediate)

The Ledgers page shows vendor codes (`AMAZ290010`) instead of names because the `kuroadmin/vendors` and `kurostaff/vendors` endpoints may return different field structures.

**Root cause:** Two separate view functions for the same resource, potentially with different response formats.

**Fix (Phase A priority):**

1. Merge `kuroadmin/vendors` and `kurostaff/vendors` into single `vendors/list` view
2. Standardize response to always include: `vendor_code`, `name`, `gstin`, `division`, `active`
3. Update frontend to use `vendors/list` endpoint
4. Ledgers page lookup: `vendors.find(v => v.vendor_code === key)` → `vendor.name`

---

## TO BE DECIDED — Unified Identity Model

These items define the target architecture but require schema reconciliation before implementation. All ship in the single big-bang deployment.

### TBD-1: Merge kteam + gaming `CustomUser` schemas

**Current state:** kteam and gaming backends each have their own `CustomUser` with different field sets. Both use `userid` as PK and `phone` as a key, but field names, types, and constraints differ.

**Target:** Single `users_customuser` table. One identity per person. `phone` as universal lookup key.

**Decision needed:** Read gaming backend `CustomUser` schema, reconcile field differences, produce merged model.

### TBD-2: Identity vs. role separation

**Target model:**

```
CustomUser (identity — one row per person)
  ├── userid (PK, e.g. USR001)
  ├── phone (universal lookup key)
  └── bg_code, div_code, branch_code (tenant)

Roles (separate tables, FK to CustomUser or CafeWalkin):
  ├── CafeUser — cafe role (member/staff/admin), branch-registered
  ├── TournamentPlayer — esports participant (skills, rank, history)
  └── TeamMembership — team roster (team FK, player FK, role)
```

**Decision needed:** Confirm role table boundaries. Does esports need a separate `TournamentPlayer` or is `CustomUser` + team membership enough?

### TBD-3: Walkin-to-user merge flow

**Target:** `CafeWalkin` is pre-identity. When a walkin registers, create `CustomUser`, link existing walkin, merge wallets.

```
1. Walkin exists: walkin_id=WLN001, phone=98765, tenant=BG/DIV/BR
2. Walkin registers → CustomUser(userid=USR001, phone=98765, tenant=BG/DIV/BR)
3. CafeUser(user=USR001, user_type=member)
4. CafeWalkin.user → USR001 (link, don't delete)
5. Wallet (walkin=WLN001) → resolves to user via walkin.user
```

**Decision needed:** Does `CafeWalkin` get a `user` FK post-registration, or is it archived and replaced? Wallet ownership transfer strategy.

### TBD-4: Esports data migration (MongoDB → PostgreSQL)

**Current:** `players`, `teams`, `tournaments` in MongoDB. No FKs to identity.

**Target:** PostgreSQL tables with FKs to `CustomUser`/`CafeWalkin`.

```
TournamentPlayer:
  player_id (PK)
  user (FK → CustomUser, nullable)
  walkin (FK → CafeWalkin, nullable)
  display_name, skills, rank
  bg_code, div_code, branch_code

EsportsTeam:
  team_id (PK)
  name, captain (FK → TournamentPlayer)
  bg_code

TeamMembership:
  team (FK → EsportsTeam)
  player (FK → TournamentPlayer)
  role (player/substitute/coach)
```

**Decision needed:** Esports MongoDB schema audit. Field mapping from Mongo docs to PG columns. Data migration strategy (deduplication, phone→userid resolution).

### TBD-5: Gaming backend `CustomUser` schema audit

**Blocker for TBD-1 through TBD-4.** Gaming backend `CustomUser` has not been read. Field differences from kteam version are unknown. Cannot produce merged model without it.

**Action:** Read gaming backend `users/models.py` (or equivalent). Produce field-by-field diff. Decide keep/drop/merge for each field.


