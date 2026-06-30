# Accounts Domain Spec

**Status:** Active — 47/55 endpoints migrated to ViewSets (85% complete)  
**Base Path:** `/api/v1/accounts/`  
**Last Updated:** 2026-06-29  
**Authority:** `endpoint_contract_spec_revised.md` (§6.2, §8, §9, §11.2)

---

## Overview

The Accounts domain provides RESTful endpoints for all financial operations: invoices (inward/outward), payments (inward/outward), payment vouchers, purchase orders, credit/debit notes, ledger accounts (sundry creditors/debtors), partners, banks, loans, financial reports, bulk payments, analytics, settlements, and data exports.

**Module inventory:** 13 modules, 47 migrated endpoints, 8 pending (see Migration Status).

---

## Error Handling

All endpoints return the standard error envelope defined in `endpoint_contract_spec_revised.md` §8.2:

```json
{
    "status": "error",
    "error": {
        "code": "PERMISSION_DENIED",
        "message": "You do not have permission to view this resource",
        "details": {
            "required_permission": "accounts.inward-invoices.view",
            "tenant_scope": "division"
        }
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

**Standard error codes** (see locked contract §8.1): `VALIDATION_ERROR`, `AUTH_REQUIRED`, `AUTH_EXPIRED`, `PERMISSION_DENIED`, `NOT_FOUND`, `TENANT_ISOLATION`, `TENANT_CONTEXT_MISSING`, `CONFLICT`, `RATE_LIMITED`, `INTERNAL_ERROR`.

**Accounts-specific errors:**
- `ACCOUNT_NOT_FOUND` — 404 when ledger account/partner/bank/loan not found
- `INVALID_ACCOUNT_TYPE` — 400 when `type` filter value is not a recognized account type
- `EXPORT_TYPE_UNKNOWN` — 400 when export type is not in the allowed set
- `PERIOD_INVALID` — 400 when period parameter is not in `ALLOWED_PERIODS`

---

## Authentication

All endpoints require JWT authentication via HttpOnly cookie (`jwt_token`).

**Header convention:** When a Bearer token is used (e.g., for non-browser clients), the locked contract §4.1.1 defines the header as `Authorization: Bearer <access_token>`.

**Refresh token:** Delivered ONLY as HttpOnly cookie. Per locked contract §4.2 the cookie name should be `refresh_token`; current backend uses `jwt_refresh` (see MG-6). The refresh token is NOT included in the JSON response body.

**RBAC permission pattern:** `accounts.{resource}.{action}` where action is `view` (level ≥ 1), `edit` (level ≥ 2), or `admin` (level ≥ 3).

---

## Multi-Tenancy

All endpoints are tenant-scoped per `endpoint_contract_spec_revised.md` §5.1-5.2.

**JWT tenant context (extracted from every request):**

| Claim | Type | Purpose |
|-------|------|---------|
| `bg_code` | string | Active business group (required) |
| `div_codes` | string[] | All accessible division codes |
| `branch_codes` | string[] | All accessible branch codes |
| `active_div_code` | string | Current active division (= `div_codes[0]`) |
| `active_branch_code` | string\|null | Current active branch (= `branch_codes[0]`) |
| `scope` | string | Scope level: `'full'` \| `'division'` \| `'branch'` |
| `identity_id` | string | User identity |

> **Locked contract invariant (§4.2):** `active_div_code == div_codes[0]` and `active_branch_code == branch_codes[0]` MUST hold at all times. If they diverge, the JWT is stale and must be regenerated. The UserTenantContext model stores these as separate fields, but they are derived from and must always equal the first element of their respective arrays.

**Scope-based query filtering:**

| Scope | MongoDB Filter | Example |
|-------|---------------|---------|
| `full` | `{ bg_code: X }` | BG admin sees all divisions |
| `division` | `{ bg_code: X, div_code: { $in: div_codes } }` | Division manager |
| `branch` | `{ bg_code: X, div_code: Y, branch_code: { $in: branch_codes } }` | Branch staff |

**Tenant isolation:** Cross-tenant access attempts return `TENANT_ISOLATION` (403) per locked contract §8.3.

---

## Pagination & Filtering

All list endpoints support `endpoint_contract_spec_revised.md` §9.1-9.2:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | `1` | Page number (1-indexed) |
| `page_size` | int | `20` | Items per page (max 100) |
| `sort` | string | `updated_date` | Sort field (`-` prefix for desc) |
| `filter[field]=value` | string | — | Exact match filter |
| `search` | string | — | Full-text search |

---

## Common Request/Response Patterns

**Success envelope** (all endpoints):
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

**List response envelope:**
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

---

## Modules

### 1. Inward Invoices (Purchase Invoices)

**Base path:** `/api/v1/accounts/inward-invoices`  
**ViewSet:** `InwardInvoiceViewSet`  
**Collection:** `inwardinvoices`  
**Status:** ✅ Migrated — Full CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/inward-invoices` | `accounts.inward-invoices.view` | List inward invoices |
| `POST` | `/inward-invoices` | `accounts.inward-invoices.edit` | Create inward invoice |
| `GET` | `/inward-invoices/{id}` | `accounts.inward-invoices.view` | Invoice detail |
| `PATCH` | `/inward-invoices/{id}` | `accounts.inward-invoices.edit` | Update invoice |
| `DELETE` | `/inward-invoices/{id}` | `accounts.inward-invoices.admin` | Delete invoice |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[status]`, `filter[party]`, `search`

**Request schema (POST):**
```json
{
    "party": "P000001",
    "party_name": "Acme Suppliers",
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-06-01",
    "due_date": "2026-07-01",
    "amount": 15000.00,
    "tax_amount": 2700.00,
    "total_amount": 17700.00,
    "currency": "INR",
    "status": "draft",
    "items": [
        {
            "description": "Widget A",
            "quantity": 10,
            "unit_price": 1000.00,
            "total": 10000.00
        }
    ],
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d0",
    "party": "P000001",
    "party_name": "Acme Suppliers",
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-06-01",
    "due_date": "2026-07-01",
    "amount": 15000.00,
    "tax_amount": 2700.00,
    "total_amount": 17700.00,
    "currency": "INR",
    "status": "draft",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001",
    "created_at": "2026-06-01T10:00:00Z",
    "updated_at": "2026-06-01T10:00:00Z"
}
```

**Tenant scoping:** All queries filtered by JWT tenant context. `division` scope filters by `div_code IN (div_codes)`. `branch` scope further filters by `branch_code`.

---

### 2. Outward Invoices (Sales Invoices)

**Base path:** `/api/v1/accounts/outward-invoices`  
**ViewSet:** `OutwardInvoiceViewSet`  
**Collection:** `outwardinvoices`  
**Status:** ✅ Migrated — Full CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/outward-invoices` | `accounts.outward-invoices.view` | List outward invoices |
| `POST` | `/outward-invoices` | `accounts.outward-invoices.edit` | Create outward invoice |
| `GET` | `/outward-invoices/{id}` | `accounts.outward-invoices.view` | Invoice detail |
| `PATCH` | `/outward-invoices/{id}` | `accounts.outward-invoices.edit` | Update invoice |
| `DELETE` | `/outward-invoices/{id}` | `accounts.outward-invoices.admin` | Delete invoice |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[status]`, `filter[party]`, `search`

**Request schema (POST):**
```json
{
    "party": "C000001",
    "party_name": "Acme Retailers",
    "invoice_number": "OUT-2026-001",
    "invoice_date": "2026-06-01",
    "due_date": "2026-07-01",
    "amount": 25000.00,
    "tax_amount": 4500.00,
    "total_amount": 29500.00,
    "currency": "INR",
    "status": "draft",
    "items": [
        {
            "description": "Service Package A",
            "quantity": 5,
            "unit_price": 5000.00,
            "total": 25000.00
        }
    ],
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d1",
    "party": "C000001",
    "party_name": "Acme Retailers",
    "invoice_number": "OUT-2026-001",
    "invoice_date": "2026-06-01",
    "amount": 25000.00,
    "tax_amount": 4500.00,
    "total_amount": 29500.00,
    "status": "draft",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 3. Inward Payments (Purchase Payments)

**Base path:** `/api/v1/accounts/inward-payments`  
**ViewSet:** `InwardPaymentViewSet`  
**Collection:** `inwardpayments`  
**Status:** ✅ Migrated — Full CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/inward-payments` | `accounts.inward-payments.view` | List inward payments |
| `POST` | `/inward-payments` | `accounts.inward-payments.edit` | Create inward payment |
| `GET` | `/inward-payments/{id}` | `accounts.inward-payments.view` | Payment detail |
| `PATCH` | `/inward-payments/{id}` | `accounts.inward-payments.edit` | Update payment |
| `DELETE` | `/inward-payments/{id}` | `accounts.inward-payments.admin` | Delete payment |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[party]`, `filter[payment_mode]`, `search`

**Request schema (POST):**
```json
{
    "party": "P000001",
    "party_name": "Acme Suppliers",
    "amount": 17700.00,
    "payment_mode": "bank_transfer",
    "reference_number": "TXN-2026-001",
    "payment_date": "2026-06-15",
    "against_invoice": "INV-2026-001",
    "currency": "INR",
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d2",
    "party": "P000001",
    "amount": 17700.00,
    "payment_mode": "bank_transfer",
    "reference_number": "TXN-2026-001",
    "payment_date": "2026-06-15",
    "status": "completed",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 4. Outward Payments (Sales Payments)

**Base path:** `/api/v1/accounts/outward-payments`  
**ViewSet:** `OutwardPaymentViewSet`  
**Collection:** `outwardpayments`  
**Status:** ✅ Migrated — Full CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/outward-payments` | `accounts.outward-payments.view` | List outward payments |
| `POST` | `/outward-payments` | `accounts.outward-payments.edit` | Create outward payment |
| `GET` | `/outward-payments/{id}` | `accounts.outward-payments.view` | Payment detail |
| `PATCH` | `/outward-payments/{id}` | `accounts.outward-payments.edit` | Update payment |
| `DELETE` | `/outward-payments/{id}` | `accounts.outward-payments.admin` | Delete payment |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[party]`, `filter[payment_mode]`, `search`

**Request schema (POST):**
```json
{
    "party": "C000001",
    "party_name": "Acme Retailers",
    "amount": 29500.00,
    "payment_mode": "upi",
    "reference_number": "UPI-2026-001",
    "payment_date": "2026-06-15",
    "against_invoice": "OUT-2026-001",
    "currency": "INR",
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d3",
    "party": "C000001",
    "amount": 29500.00,
    "payment_mode": "upi",
    "reference_number": "UPI-2026-001",
    "payment_date": "2026-06-15",
    "status": "completed",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 5. Payment Vouchers

**Base path:** `/api/v1/accounts/payment-vouchers`  
**ViewSet:** `PaymentVoucherViewSet`  
**Collection:** `paymentvouchers`  
**Status:** ✅ Migrated — Full CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/payment-vouchers` | `accounts.payment-vouchers.view` | List payment vouchers |
| `POST` | `/payment-vouchers` | `accounts.payment-vouchers.edit` | Create payment voucher |
| `GET` | `/payment-vouchers/{id}` | `accounts.payment-vouchers.view` | Voucher detail |
| `PATCH` | `/payment-vouchers/{id}` | `accounts.payment-vouchers.edit` | Update voucher |
| `DELETE` | `/payment-vouchers/{id}` | `accounts.payment-vouchers.admin` | Delete voucher |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[voucher_type]`, `search`

**Request schema (POST):**
```json
{
    "voucher_number": "PV-2026-001",
    "voucher_type": "payment",
    "date": "2026-06-15",
    "party": "P000001",
    "party_name": "Acme Suppliers",
    "amount": 17700.00,
    "payment_mode": "bank_transfer",
    "reference_number": "TXN-2026-001",
    "against_entries": [
        {
            "document_type": "inward_invoice",
            "document_id": "6660a1b2c3d4e5f6a7b8c9d0",
            "amount": 17700.00
        }
    ],
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d4",
    "voucher_number": "PV-2026-001",
    "voucher_type": "payment",
    "date": "2026-06-15",
    "party": "P000001",
    "amount": 17700.00,
    "status": "posted",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 6. Purchase Orders

**Base path:** `/api/v1/accounts/purchase-orders`  
**ViewSet:** `PurchaseOrderViewSet`  
**Collection:** `purchaseorders`  
**Status:** ✅ Migrated — Full CRUD

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/purchase-orders` | `accounts.purchase-orders.view` | List purchase orders |
| `POST` | `/purchase-orders` | `accounts.purchase-orders.edit` | Create purchase order |
| `GET` | `/purchase-orders/{id}` | `accounts.purchase-orders.view` | Order detail |
| `PATCH` | `/purchase-orders/{id}` | `accounts.purchase-orders.edit` | Update order |
| `DELETE` | `/purchase-orders/{id}` | `accounts.purchase-orders.admin` | Delete order |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[status]`, `filter[party]`, `search`

**Request schema (POST):**
```json
{
    "po_number": "PO-2026-001",
    "party": "P000001",
    "party_name": "Acme Suppliers",
    "order_date": "2026-06-01",
    "delivery_date": "2026-06-15",
    "status": "draft",
    "items": [
        {
            "item_code": "ITEM-001",
            "description": "Widget A",
            "quantity": 100,
            "unit_price": 1000.00,
            "total": 100000.00
        }
    ],
    "total_amount": 100000.00,
    "currency": "INR",
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d5",
    "po_number": "PO-2026-001",
    "party": "P000001",
    "order_date": "2026-06-01",
    "total_amount": 100000.00,
    "status": "draft",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 7. Credit/Debit Notes

**Base paths:** `/api/v1/accounts/{outward-credit-notes|outward-debit-notes|inward-credit-notes|inward-debit-notes}`  
**ViewSets:** `OutwardCreditNoteViewSet`, `OutwardDebitNoteViewSet`, `InwardCreditNoteViewSet`, `InwardDebitNoteViewSet`  
**Status:** ✅ Migrated — Full CRUD (all 4 types)

#### 7a. Outward Credit Notes (Business Issues)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/outward-credit-notes` | `accounts.outward-credit-notes.view` | List credit notes issued |
| `POST` | `/outward-credit-notes` | `accounts.outward-credit-notes.edit` | Create credit note |
| `GET` | `/outward-credit-notes/{id}` | `accounts.outward-credit-notes.view` | Note detail |
| `PATCH` | `/outward-credit-notes/{id}` | `accounts.outward-credit-notes.edit` | Update note |
| `DELETE` | `/outward-credit-notes/{id}` | `accounts.outward-credit-notes.admin` | Delete note |

**Request schema (POST):**
```json
{
    "party": "C000001",
    "party_name": "Acme Retailers",
    "note_number": "CN-OUT-2026-001",
    "note_date": "2026-06-10",
    "amount": 5000.00,
    "tax_amount": 900.00,
    "total_amount": 5900.00,
    "against_invoice": "OUT-2026-001",
    "reason": "Damaged goods returned",
    "items": [
        {
            "description": "Widget A (return)",
            "quantity": 5,
            "unit_price": 1000.00,
            "total": 5000.00
        }
    ]
}
```

#### 7b. Outward Debit Notes (Business Issues)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/outward-debit-notes` | `accounts.outward-debit-notes.view` | List debit notes issued |
| `POST` | `/outward-debit-notes` | `accounts.outward-debit-notes.edit` | Create debit note |
| `GET` | `/outward-debit-notes/{id}` | `accounts.outward-debit-notes.view` | Note detail |
| `PATCH` | `/outward-debit-notes/{id}` | `accounts.outward-debit-notes.edit` | Update note |
| `DELETE` | `/outward-debit-notes/{id}` | `accounts.outward-debit-notes.admin` | Delete note |

#### 7c. Inward Credit Notes (Vendor Issues)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/inward-credit-notes` | `accounts.inward-credit-notes.view` | List credit notes received |
| `POST` | `/inward-credit-notes` | `accounts.inward-credit-notes.edit` | Create credit note |
| `GET` | `/inward-credit-notes/{id}` | `accounts.inward-credit-notes.view` | Note detail |
| `PATCH` | `/inward-credit-notes/{id}` | `accounts.inward-credit-notes.edit` | Update note |
| `DELETE` | `/inward-credit-notes/{id}` | `accounts.inward-credit-notes.admin` | Delete note |

#### 7d. Inward Debit Notes (Vendor Issues)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/inward-debit-notes` | `accounts.inward-debit-notes.view` | List debit notes received |
| `POST` | `/inward-debit-notes` | `accounts.inward-debit-notes.edit` | Create debit note |
| `GET` | `/inward-debit-notes/{id}` | `accounts.inward-debit-notes.view` | Note detail |
| `PATCH` | `/inward-debit-notes/{id}` | `accounts.inward-debit-notes.edit` | Update note |
| `DELETE` | `/inward-debit-notes/{id}` | `accounts.inward-debit-notes.admin` | Delete note |

**Tenant scoping (all 4 types):** Same as Inward Invoices (§1).

---

### 8. Sundry Ledger (Sundry Creditors/Debtors)

**Base path:** `/api/v1/accounts/sundry-ledger`  
**ViewSet:** `AccountsViewSet`  
**Collection:** `accounts`  
**Status:** ✅ Migrated — List, Create, Update  
**Backend gap:** Destroy not registered in urls.py (ViewSet has `destroy` method but URL not configured)

> **Naming note:** The locked contract uses `/accounts/accounts` for this endpoint. This spec uses `/accounts/sundry-ledger` to avoid the confusing self-referential name. The backend must rename the URL path from `/accounts/accounts` to `/accounts/sundry-ledger` to match. This is a **backend gap** — the current backend registers `path('accounts', ...)` which maps to `/api/v1/accounts/accounts`.

**Current backend state:** All master data (sundry accounts, partners, banks, loans) is collapsed into a single `/accounts/accounts` endpoint with a `type` query param filter. The locked contract defines them as separate endpoints. See §8.1-8.3 for the target state.

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/sundry-ledger` | `accounts.sundry-ledger.view` | List sundry ledger accounts |
| `POST` | `/sundry-ledger` | `accounts.sundry-ledger.edit` | Create sundry ledger account |
| `PATCH` | `/sundry-ledger/{id}` | `accounts.sundry-ledger.edit` | Update account |

**Query params (list):** `page`, `page_size`, `sort`, `filter[type]` (`creditor` \| `debtor`), `filter[div_code]`, `search`

> **Note:** Destroy (`DELETE /sundry-ledger/{id}`) is not registered in `urls.py` — the ViewSet has a `destroy` method but the URL path is not configured. See Migration Status table.

**Request schema (POST):**
```json
{
    "code": "30000",
    "name": "Acme Suppliers Pvt Ltd",
    "type": "creditor",
    "phone": "+919876543210",
    "email": "billing@acme.com",
    "address": "123 Industrial Area, Mumbai",
    "opening_balance": 50000.00,
    "opening_balance_direction": "debit",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d6",
    "code": "30000",
    "name": "Acme Suppliers Pvt Ltd",
    "type": "creditor",
    "phone": "+919876543210",
    "opening_balance": 50000.00,
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 8.1 Partners (Target State — Backend Gap)

**Base path:** `/api/v1/accounts/partners`  
**ViewSet:** `PartnersViewSet` (not yet implemented)  
**Collection:** `partners`  
**Status:** ⏳ **Backend gap** — locked contract defines this endpoint; current backend collapses into `/accounts/accounts` with `type=partner`

**Target endpoints:**

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/partners` | `accounts.partners.view` | List partners |
| `POST` | `/partners` | `accounts.partners.edit` | Create partner |
| `GET` | `/partners/{id}` | `accounts.partners.view` | Partner detail |
| `PATCH` | `/partners/{id}` | `accounts.partners.edit` | Update partner |
| `DELETE` | `/partners/{id}` | `accounts.partners.admin` | Delete partner |

**Request schema (POST):**
```json
{
    "code": "PAR-001",
    "name": "Acme Retailers Pvt Ltd",
    "partner_type": "customer",
    "phone": "+919876543210",
    "email": "orders@acme.com",
    "address": "456 Commerce Street, Delhi",
    "gst_number": "27AABCU9603R1ZM",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Current backend workaround:** `GET /accounts/accounts?type=partner` returns partners filtered by type. This is NOT the target contract.

---

### 8.2 Banks (Target State — Backend Gap)

**Base path:** `/api/v1/accounts/banks`  
**ViewSet:** `BanksViewSet` (not yet implemented)  
**Collection:** `banks`  
**Status:** ⏳ **Backend gap** — locked contract defines this endpoint; current backend collapses into `/accounts/accounts` with `type=bank`

**Target endpoints:**

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/banks` | `accounts.banks.view` | List bank accounts |
| `POST` | `/banks` | `accounts.banks.edit` | Create bank account |
| `GET` | `/banks/{id}` | `accounts.banks.view` | Bank detail |
| `PATCH` | `/banks/{id}` | `accounts.banks.edit` | Update bank |
| `DELETE` | `/banks/{id}` | `accounts.banks.admin` | Delete bank |

**Request schema (POST):**
```json
{
    "code": "BNK-001",
    "bank_name": "State Bank of India",
    "branch": "Mumbai Main",
    "account_number": "1234567890",
    "ifsc_code": "SBIN0001234",
    "account_type": "current",
    "currency": "INR",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Current backend workaround:** `GET /accounts/accounts?type=bank` returns banks filtered by type. This is NOT the target contract.

---

### 8.3 Loans (Target State — Backend Gap)

**Base path:** `/api/v1/accounts/loans`  
**ViewSet:** `LoansViewSet` (not yet implemented)  
**Collection:** `loans`  
**Status:** ⏳ **Backend gap** — locked contract defines this endpoint; current backend collapses into `/accounts/accounts` with `type=loan`

**Target endpoints:**

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/loans` | `accounts.loans.view` | List loans |
| `POST` | `/loans` | `accounts.loans.edit` | Create loan |
| `GET` | `/loans/{id}` | `accounts.loans.view` | Loan detail |
| `PATCH` | `/loans/{id}` | `accounts.loans.edit` | Update loan |
| `DELETE` | `/loans/{id}` | `accounts.loans.admin` | Delete loan |

**Request schema (POST):**
```json
{
    "code": "LN-001",
    "lender": "HDFC Bank",
    "borrower": "KURO0001",
    "principal": 500000.00,
    "interest_rate": 10.5,
    "start_date": "2026-01-01",
    "end_date": "2031-01-01",
    "EMI": 10750.00,
    "currency": "INR",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Current backend workaround:** `GET /accounts/accounts?type=loan` returns loans filtered by type. This is NOT the target contract.

---

### 9. Financial Reports

All report endpoints are read-only (`GET` list only). No create/update/delete.

#### 9a. Financial Position

**Endpoint:** `GET /api/v1/accounts/financials`  
**ViewSet:** `FinancialsViewSet`  
**Permission:** `accounts.financials.view`  
**Status:** ✅ Migrated

**Query params:** `filter[div_code]`, `date_from`, `date_to`, `report_type`

**Response example:**
```json
{
    "status": "success",
    "data": {
        "total_inward_invoices": 1500000.00,
        "total_outward_invoices": 2500000.00,
        "total_inward_payments": 1200000.00,
        "total_outward_payments": 2000000.00,
        "outstanding_receivables": 500000.00,
        "outstanding_payables": 300000.00,
        "net_position": 200000.00
    },
    "meta": { "request_id": "req_abc123", "timestamp": "2026-06-25T10:00:00Z" }
}
```

#### 9b. Balance Sheet

**Endpoint:** `GET /api/v1/accounts/balance-sheet`  
**ViewSet:** `BalanceSheetViewSet`  
**Permission:** `accounts.balance-sheet.view`  
**Status:** ✅ Migrated

#### 9c. Profit & Loss

**Endpoint:** `GET /api/v1/accounts/profit-loss`  
**ViewSet:** `ProfitLossViewSet`  
**Permission:** `accounts.profit-loss.view`  
**Status:** ✅ Migrated

#### 9d. Revenue / Sales

**Endpoint:** `GET /api/v1/accounts/revenue`  
**ViewSet:** `RevenueViewSet`  
**Permission:** `accounts.revenue.view`  
**Status:** ✅ Migrated

#### 9e. Expenditure / Purchase

**Endpoint:** `GET /api/v1/accounts/expenditure`  
**ViewSet:** `ExpenditureViewSet`  
**Permission:** `accounts.expenditure.view`  
**Status:** ✅ Migrated

#### 9f. ITC & GST

**Endpoint:** `GET /api/v1/accounts/itc-gst`  
**ViewSet:** `ITCGSTViewSet`  
**Permission:** `accounts.itc-gst.view`  
**Status:** ✅ Migrated

**Tenant scoping (all reports):** Reports are aggregated by `bg_code` from JWT. `division` scope further filters to `div_code IN (div_codes)`. `branch` scope further filters to specific branch.

---

### 10. Bulk Payments

**Base path:** `/api/v1/accounts/bulk-payments`  
**ViewSet:** `BulkPaymentViewSet`  
**Status:** ✅ Migrated

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/bulk-payments` | `accounts.bulk-payments.view` | List bulk payment batches |
| `POST` | `/bulk-payments` | `accounts.bulk-payments.edit` | Create bulk payment batch |

**Request schema (POST):**
```json
{
    "payment_mode": "bank_transfer",
    "reference_number": "BULK-2026-001",
    "payment_date": "2026-06-15",
    "entries": [
        {
            "party": "P000001",
            "party_name": "Acme Suppliers",
            "amount": 17700.00,
            "against_invoice": "INV-2026-001"
        },
        {
            "party": "P000002",
            "party_name": "Beta Suppliers",
            "amount": 25000.00,
            "against_invoice": "INV-2026-002"
        }
    ]
}
```

**Response example:**
```json
{
    "status": "success",
    "data": {
        "id": "6660a1b2c3d4e5f6a7b8c9d7",
        "reference_number": "BULK-2026-001",
        "total_entries": 2,
        "total_amount": 42700.00,
        "status": "processed",
        "created_at": "2026-06-15T10:00:00Z"
    },
    "meta": { "request_id": "req_abc123", "timestamp": "2026-06-25T10:00:00Z" }
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 11. Analytics

**Endpoint:** `GET /api/v1/accounts/analytics`  
**ViewSet:** `AnalyticsViewSet`  
**Permission:** `accounts.analytics.view`  
**Status:** ✅ Migrated

**Query params:** `period` (`day` \| `week` \| `month` \| `quarter` \| `year`), `filter[div_code]`, `metric` (`revenue` \| `expenses` \| `profit` \| `invoices` \| `payments`)

**Response example:**
```json
{
    "status": "success",
    "data": {
        "period": "month",
        "metric": "revenue",
        "total": 2500000.00,
        "comparison": {
            "previous_period": 2200000.00,
            "change_percent": 13.6
        },
        "breakdown": [
            { "date": "2026-06-01", "amount": 800000.00 },
            { "date": "2026-06-02", "amount": 900000.00 }
        ]
    },
    "meta": { "request_id": "req_abc123", "timestamp": "2026-06-25T10:00:00Z" }
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 12. Settlements

**Base path:** `/api/v1/accounts/settlements`  
**ViewSet:** `SettlementsViewSet`  
**Status:** ✅ Migrated

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/settlements` | `accounts.settlements.view` | List settlements |
| `POST` | `/settlements` | `accounts.settlements.edit` | Create settlement |

**Query params (list):** `page`, `page_size`, `sort`, `filter[div_code]`, `filter[status]`, `search`

**Request schema (POST):**
```json
{
    "party": "P000001",
    "party_name": "Acme Suppliers",
    "settlement_date": "2026-06-30",
    "total_invoices": 5,
    "total_amount": 85000.00,
    "total_payments": 85000.00,
    "balance": 0.00,
    "status": "settled",
    "notes": ""
}
```

**Response example (list item):**
```json
{
    "id": "6660a1b2c3d4e5f6a7b8c9d8",
    "party": "P000001",
    "settlement_date": "2026-06-30",
    "total_amount": 85000.00,
    "balance": 0.00,
    "status": "settled",
    "bg_code": "KURO0001",
    "div_code": "KURO0001_001"
}
```

**Tenant scoping:** Same as Inward Invoices (§1).

---

### 13. Exports

> **Locked contract (§6.2):** Three distinct resource-style endpoints.  
> **Current backend:** Implements resource-style paths correctly. Also has a generic `export_data` fallback.

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| `GET` | `/export/inward-invoices` | `accounts.inward-invoices.view` | Export inward invoices (CSV/PDF) |
| `GET` | `/export/outward-invoices` | `accounts.outward-invoices.view` | Export outward invoices (CSV/PDF) |
| `GET` | `/export/inward-payments` | `accounts.inward-payments.view` | Export inward payments (CSV/PDF) |
| `GET` | `/export` | `accounts.inward-invoices.view` | Generic export by `type` param (**non-canonical fallback** — do not depend on this) |

**Query params (all export endpoints):**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `duration` | string | `curr_month` | Time period (`curr_month`, `last_month`, `curr_fy`, `last_fy`, `curr_quarter`, `last_quarter`, `monthly`, `quarterly`, `yearly`) |
| `format` | string | `json` | Output format (`json`, `csv`) |
| `div_code` | string | — | Division filter |

**Response example (JSON export):**
```json
{
    "status": "success",
    "data": [
        {
            "invoice_number": "INV-2026-001",
            "party": "P000001",
            "invoice_date": "2026-06-01",
            "amount": 15000.00,
            "tax_amount": 2700.00,
            "total_amount": 17700.00,
            "status": "paid"
        }
    ],
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z",
        "period": "curr_month",
        "export_type": "inward-invoices"
    }
}
```

**Response example (CSV export):** Returns `text/csv` with `Content-Disposition: attachment; filename="inward-invoices.csv"`.

**Tenant scoping:** Exports are scoped to JWT tenant context. `division` scope limits to `div_code IN (div_codes)`. `branch` scope further limits.

---

## Migration Status

| Module | Status | Endpoints | Notes |
|--------|--------|-----------|-------|
| Inward Invoices | ✅ Complete | Full CRUD | Migrated |
| Outward Invoices | ✅ Complete | Full CRUD | Migrated |
| Inward Payments | ✅ Complete | Full CRUD | Migrated |
| Outward Payments | ✅ Complete | Full CRUD | Migrated |
| Payment Vouchers | ✅ Complete | Full CRUD | Migrated |
| Purchase Orders | ✅ Complete | Full CRUD | Migrated |
| Credit/Debit Notes | ✅ Complete | 4 × Full CRUD | Migrated |
| Sundry Ledger | ✅ Complete | List/Create/Update | Destroy not registered in URLs (ViewSet has method, URL not configured) |
| Partners | ⏳ Backend gap | — | Collapsed into `/accounts/accounts` |
| Banks | ⏳ Backend gap | — | Collapsed into `/accounts/accounts` |
| Loans | ⏳ Backend gap | — | Collapsed into `/accounts/accounts` |
| Financial Reports | ✅ Complete | 6 read-only endpoints | Migrated |
| Bulk Payments | ✅ Complete | List/Create | Migrated |
| Analytics | ✅ Complete | List | Migrated |
| Settlements | ✅ Complete | List/Create | Migrated |
| Exports | ✅ Complete | 3 resource + 1 generic | Migrated |
| Legacy (teams/financial.py) | ⏳ Pending | — | Must be fully migrated |

**Overall:** 47/55 endpoints migrated (85% complete). 3 master data endpoints (partners, banks, loans) are backend gaps against the locked contract.

---

## Data Models

### Transactional Models
- `InwardInvoice` — Purchase invoices
- `OutwardInvoice` — Sales invoices
- `InwardPayment` — Purchase payments
- `OutwardPayment` — Sales payments
- `PaymentVoucher` — Payment vouchers
- `PurchaseOrder` — Purchase orders
- `OutwardCreditNote` — Credit notes issued
- `OutwardDebitNote` — Debit notes issued
- `InwardCreditNote` — Credit notes received
- `InwardDebitNote` — Debit notes received
- `Settlement` — Settlements

### Master Data Models
- `SundryCreditor` / `SundryDebtor` — Ledger accounts (currently in `accounts` collection)
- `Partner` — Business partners (target: separate `partners` collection)
- `Bank` — Bank accounts (target: separate `banks` collection)
- `Loan` — Loans (target: separate `loans` collection)

### Report Models
- `FinancialPosition` — Financial position aggregation
- `ITCGST` — Input Tax Credit & GST
- `Revenue` — Sales/revenue
- `Expenditure` — Purchase/expenditure
- `ProfitLoss` — Profit & loss statement
- `BalanceSheet` — Balance sheet

---

## RBAC Permission Codes

| Permission Code | Description |
|----------------|-------------|
| `accounts.inward-invoices.view` | View inward invoices |
| `accounts.inward-invoices.edit` | Create/update inward invoices |
| `accounts.inward-invoices.admin` | Delete inward invoices |
| `accounts.outward-invoices.view` | View outward invoices |
| `accounts.outward-invoices.edit` | Create/update outward invoices |
| `accounts.outward-invoices.admin` | Delete outward invoices |
| `accounts.inward-payments.view` | View inward payments |
| `accounts.inward-payments.edit` | Create/update inward payments |
| `accounts.inward-payments.admin` | Delete inward payments |
| `accounts.outward-payments.view` | View outward payments |
| `accounts.outward-payments.edit` | Create/update outward payments |
| `accounts.outward-payments.admin` | Delete outward payments |
| `accounts.payment-vouchers.view` | View payment vouchers |
| `accounts.payment-vouchers.edit` | Create/update payment vouchers |
| `accounts.payment-vouchers.admin` | Delete payment vouchers |
| `accounts.purchase-orders.view` | View purchase orders |
| `accounts.purchase-orders.edit` | Create/update purchase orders |
| `accounts.purchase-orders.admin` | Delete purchase orders |
| `accounts.outward-credit-notes.view` | View outward credit notes |
| `accounts.outward-credit-notes.edit` | Create/update outward credit notes |
| `accounts.outward-credit-notes.admin` | Delete outward credit notes |
| `accounts.outward-debit-notes.view` | View outward debit notes |
| `accounts.outward-debit-notes.edit` | Create/update outward debit notes |
| `accounts.outward-debit-notes.admin` | Delete outward debit notes |
| `accounts.inward-credit-notes.view` | View inward credit notes |
| `accounts.inward-credit-notes.edit` | Create/update inward credit notes |
| `accounts.inward-credit-notes.admin` | Delete inward credit notes |
| `accounts.inward-debit-notes.view` | View inward debit notes |
| `accounts.inward-debit-notes.edit` | Create/update inward debit notes |
| `accounts.inward-debit-notes.admin` | Delete inward debit notes |
| `accounts.sundry-ledger.view` | View sundry ledger accounts |
| `accounts.sundry-ledger.edit` | Create/update sundry ledger accounts |
| `accounts.partners.view` | View partners (target) |
| `accounts.partners.edit` | Create/update partners (target) |
| `accounts.partners.admin` | Delete partners (target) |
| `accounts.banks.view` | View banks (target) |
| `accounts.banks.edit` | Create/update banks (target) |
| `accounts.banks.admin` | Delete banks (target) |
| `accounts.loans.view` | View loans (target) |
| `accounts.loans.edit` | Create/update loans (target) |
| `accounts.loans.admin` | Delete loans (target) |
| `accounts.financials.view` | View financial reports |
| `accounts.balance-sheet.view` | View balance sheet |
| `accounts.profit-loss.view` | View profit & loss |
| `accounts.revenue.view` | View revenue reports |
| `accounts.expenditure.view` | View expenditure reports |
| `accounts.itc-gst.view` | View ITC & GST reports |
| `accounts.bulk-payments.view` | View bulk payments |
| `accounts.bulk-payments.edit` | Create bulk payments |
| `accounts.analytics.view` | View analytics |
| `accounts.settlements.view` | View settlements |
| `accounts.settlements.edit` | Create settlements |

---

## References

- **URL Configuration:** `domains/accounts/urls.py`
- **ViewSets:** `domains/accounts/viewsets.py`
- **Services:** `domains/accounts/services.py`
- **Financials:** `domains/accounts/financials/`
- **Expenditure:** `domains/accounts/expenditure/`
- **Sales:** `domains/accounts/sales/`
- **Tax:** `domains/accounts/tax/`
- **Locked contract:** `endpoint_contract_spec_revised.md` §6.2, §8, §9, §11.2
- **Multi-tenancy:** `endpoint_contract_spec_revised.md` §5.1-5.2
- **Canonical naming:** `CANONICAL_NAMING.md`

---

**Document Status:** Working spec — suitable for active frontend/backend alignment. **Not locked.**  
**Previous version:** Created 2026-06-29 (RF-7 response).  
**Lock-ready after:** Backend implements /accounts/partners, /accounts/banks, /accounts/loans endpoints; renames /accounts/accounts → /accounts/sundry-ledger; registers destroy on sundry-ledger; resolves auth transport deviation (HttpOnly cookie vs. Bearer per locked contract).
