# E-Commerce Domain Specification

**Status:** Spec — TARGET  
**Date:** 2026-05-17  
**Source:** `eshop_legacy_review.md`, `KungOS_Endpoint_Design.md`, `KungOS_v2.md`  
**Purpose:** Authoritative spec for e-commerce domain (package: `eshop`) — cart, orders, payment, fulfillment, procurement

---

## 1. Domain Overview

The e-commerce domain (package: `eshop`) handles online retail operations: product catalog, cart, wishlist, addresses, orders, payment processing, and procurement bridging.

### 1.1 Domain Boundaries

| Boundary | Inside Domain | Outside Domain |
|---|---|---|
| **Identity** | Customer lookup via `users_identity` | Auth, RBAC, employee management |
| **Orders** | E-commerce orders (`eshop_detail`) | In-store orders, estimates, service requests |
| **Payment** | Cashfree PG, UPI QR generation | Wallet transactions, inward/outward payments |
| **Procurement** | Indent generation from orders | Purchase orders, inventory management |
| **Catalog** | Products, builds, components, accessories | Cafe game catalog, esports tournaments |

### 1.2 Legacy Apps (from `kuro-gaming-dj-backend`)

| Legacy App | Model/Component | Database | Key Rules |
|---|---|---|---|
| `accounts` | `Cart`, `Wishlist` | PostgreSQL | String bindings for `productid` (Mongo catalog) |
| `accounts` | `Addresslist` | PostgreSQL | Immutable address edit pattern |
| `orders` | `Orders`, `OrderItems` | PostgreSQL | PC cabinet shipping surcharge, Cashfree surcharge |
| `orders` | Custom PC cloning | Mongo (`custombuilds`) | `"KCPB"` prefix → immutable copy |
| `payment` | Cashfree PG Integrator | API Gateway | Sandbox + prod APIs, webhook verification |
| `payment` | UPI QR Engine | Local Code | Dynamic UPI strings → Base64 PNG |

---

## 2. Product Catalog

### 2.1 MongoDB Collections (Gaming, Phase 3b)

| Collection | Purpose | Notes |
|---|---|---|
| `prods` | Product catalog | |
| `builds` | Pre-built PC builds | |
| `kgbuilds` | Kuro Gaming builds | |
| `custombuilds` | Custom PC builds (ordered) | Immutable copies of ordered builds |
| `components` | Hardware components | |
| `accessories` | PC accessories | |
| `monitors` | Monitor catalog | |
| `networking` | Networking equipment | |
| `external` | External products | |
| `games` | Game catalog | |
| `presets` | Preset configurations | |

### 2.2 Custom PC Build Duplication

**Rule:** Every ordered Custom PC Build (`"KCPB"` prefix) is cloned to an immutable record in `custombuilds` to preserve ordered hardware specifications historically.

**Flow:**
1. Customer orders product with `"KCPB"` prefix
2. System clones the record in `custombuilds` collection
3. Clone marked `used = True`
4. Sequential ID assigned (`"KCPB24" + 8-digit seq`)
5. Order item linked to clone

**Guardrail:** Cloning must be executed inside a PG transaction using `transaction.on_commit` or outbox event processor. Prevents PyMongo from inserting ghost custom builds when PG transactions roll back.

---

## 3. Cart & Wishlist

### 3.1 Cart

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `user_id` | varchar | FK → `users_identity.identity_id` (TARGET) |
| `productid` | varchar | String binding (Mongo catalog) |
| `category` | varchar | Product category |
| `quantity` | integer | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 3.2 Wishlist

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `user_id` | varchar | FK → `users_identity.identity_id` (TARGET) |
| `productid` | varchar | String binding (Mongo catalog) |
| `created_at` | timestamptz | |

---

## 4. Address Management

### 4.1 Immutable Address Edit Pattern

**Rule:** If an address has `is_used = True`, editing it marks the old one as `delete_flag = True` and inserts a **new cloned record** to protect old order invoices.

**Rationale:** Tax and financial audit trails require immutable address records. In-place updates would corrupt historical invoices.

### 4.2 Address Schema (TARGET)

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `identity_id` | char(20) | FK → `users_identity.identity_id` (TARGET) |
| `address_type` | varchar | `bill`/`ship`/`registered`/`office`/`warehouse` |
| `address_line1` | varchar(150) | |
| `address_line2` | varchar(150) | NULL |
| `city` | varchar(150) | |
| `state` | varchar(150) | |
| `country` | varchar(100) | Default `India` |
| `pincode` | varchar(10) | |
| `phone_no` | varchar | |
| `is_default` | boolean | |
| `is_used` | boolean | Default `false` — marks address as used in orders |
| `delete_flag` | boolean | Default `false` — marks address as decommissioned |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Design decision:** Address storage links directly to `users_identity` (not `CustomUser`). Preserves immutable edit pattern for tax invoicing integrity.

---

## 5. Order Management

### 5.1 Order Types

| Type | Source | Storage | Notes |
|---|---|---|---|
| **E-commerce** | Online checkout | `orders_core` + `eshop_detail` (PG) | Cashfree/UPI payment |
| **In-store** | Cafe/retail | `orders_core` + `in_store_detail` (PG) | F&B, walk-in |
| **TP** | Third-party | `orders_core` + `tp_order_detail` (PG) | |
| **Service** | Service requests | `orders_core` + `service_detail` (PG) | |
| **Estimate** | Quotes | `orders_core` + `estimate_detail` (PG) | |

### 5.2 `orders_core` — Shared Fields

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `orderid` | varchar | UNIQUE, sequential |
| `order_type` | varchar | ENUM: `eshop`/`in_store`/`tp`/`service`/`estimate` |
| `status` | varchar | ENUM: `pending`/`confirmed`/`processing`/`shipped`/`delivered`/`cancelled` |
| `total_amount` | decimal(12,2) | |
| `customer_id` | char(20) | FK → `users_identity.identity_id` |
| `division` | varchar | Division code |
| `bg_code` | varchar(10) | FK → `tenant_business_groups.bg_code` |
| `billadd` | jsonb | Billing address (snapshot) |
| `products` | jsonb | Product list (snapshot) |
| `channel` | varchar | `online`/`in_store`/`tp` |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 5.3 `eshop_detail` — E-Commerce Specific

| Field | Type | Notes |
|---|---|---|
| `order_id` | bigint | **PRIMARY KEY**, FK → `orders_core.id` |
| `payment_option` | varchar | `cashfree`/`upi`/`cod` |
| `pay_reference` | varchar | Payment gateway reference |
| `upi_address` | varchar | UPI ID |
| `order_expiry` | timestamptz | Order expiration |
| `fees` | decimal(12,2) | Processing fees |
| `tax` | decimal(12,2) | CGST/SGST/IGST |
| `discount` | decimal(12,2) | |
| `shipping` | decimal(12,2) | + Rs. 500 flat × quantity for tower cabinets |
| `timeline_*` | timestamptz | 12 timeline fields |

### 5.4 Order Surcharge Rules

| Rule | Condition | Amount |
|---|---|---|
| **PC Cabinet Shipping** | Item is "tower" (Cabinet) | Rs. 500 flat × quantity |
| **Cashfree Processing** | Payment method is Cashfree | 2% flat on total |

### 5.5 Deprecate & Recover Pattern

**Rule:** If customer alters payment options at checkout, old order is marked deleted, and items are **automatically re-populated** back into their cart so their cart isn't lost.

---

## 6. Payment Processing

### 6.1 Cashfree Payment Gateway

| Aspect | Value |
|---|---|
| **Sandbox** | `sandbox.cashfree.com` |
| **Production** | `api.cashfree.com` |
| **Webhook** | `cfresponse` (payment verification) |
| **Redirect** | `cfredirect` (return URL) |
| **Surcharge** | 2% flat processing fee |

### 6.2 UPI QR Code Generation

| Aspect | Value |
|---|---|
| **Library** | `pyqrcode` (local) |
| **Format** | Base64 PNG stream |
| **UPI String** | `upi://pay?pa=BHARATPE...` |
| **Delivery** | Direct to frontend (no third-party dependency) |

**Design decision:** Keep the dynamic UPI QR PNG generator. It is highly local and robust, minimizing discrete third-party API dependencies (aligned with local-first stack rules).

### 6.3 Webhook Security

**Current risk:** `payment/views.py` lacks strict HMAC signature validation for incoming Cashfree notify webhook (`cfresponse`). Webhook spoofing risk.

**Remediation:** Implement HMAC-SHA256 verification using Cashfree client secret:

```python
import hmac
import hashlib
import base64

def verify_cashfree_signature(payload_string, signature, secret_key):
    computed = base64.b64encode(
        hmac.new(
            secret_key.encode('utf-8'),
            payload_string.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    return hmac.compare_digest(computed, signature)
```

---

## 7. Order Conversion Pipeline (Enterprise Bridge)

### 7.1 Flow

When an online checkout completes successfully via Cashfree, a background webhook triggers the internal `orderconversion` endpoint.

```
Customer Pays on Website
       │
       ▼
Cashfree Webhook / Redirect (cfresponse / cfredirect)
       │
       ▼
POST /api/v1/kurostaff/orderconversion
       │
       ▼
┌─────────────────────────────────────┐
│  Order Conversion Pipeline          │
│                                     │
│  1. Check if order already exists   │
│  2. Fetch e-shop order detail       │
│  3. Generate offline order in Mongo │
│  4. Map items: presets & products   │
│  5. Calculate CGST/SGST/IGST tax    │
│  6. Save to kgorders & inwardpayments│
│  7. Trigger creating_indent()       │
│  8. Generate procurement requisitions│
└─────────────────────────────────────┘
```

### 7.2 The Procurement Gap

**Risk:** This process operates entirely on MongoDB. If the e-commerce customer's PG database updates, but the webhook to MongoDB fails, the order is confirmed online but **the warehouse receives no procurement indent request** to purchase the hardware.

**Remediation:** Integrate `orderconversion` pipeline with `plat/outbox/` system so that order payment triggers a durable outbox event (`order.payment_verified`) which is processed reliably.

---

## 8. API Contract

### 8.1 E-Commerce Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/eshop/products` | Product catalog | Public |
| `GET` | `/api/v1/eshop/products/{id}` | Product detail | Public |
| `GET` | `/api/v1/eshop/cart` | Current user cart | JWT |
| `POST` | `/api/v1/eshop/cart` | Add to cart | JWT |
| `PATCH` | `/api/v1/eshop/cart/{id}` | Update cart item | JWT |
| `DELETE` | `/api/v1/eshop/cart/{id}` | Remove from cart | JWT |
| `GET` | `/api/v1/eshop/wishlist` | Current user wishlist | JWT |
| `POST` | `/api/v1/eshop/wishlist` | Add to wishlist | JWT |
| `GET` | `/api/v1/eshop/addresses` | User addresses | JWT |
| `POST` | `/api/v1/eshop/addresses` | Create address | JWT |
| `PATCH` | `/api/v1/eshop/addresses/{id}` | Update address (clone if used) | JWT |
| `POST` | `/api/v1/eshop/checkout` | Create order | JWT |
| `GET` | `/api/v1/eshop/orders` | User orders | JWT |
| `GET` | `/api/v1/eshop/orders/{id}` | Order detail | JWT |
| `POST` | `/api/v1/eshop/payment/initiate` | Initiate payment | JWT |
| `POST` | `/api/v1/eshop/payment/webhook` | Cashfree webhook | HMAC |
| `GET` | `/api/v1/eshop/payment/upi-qr` | Generate UPI QR | JWT |

### 8.2 Response Contract — Order

```json
{
    "orderid": "ESH000001",
    "order_type": "eshop",
    "status": "confirmed",
    "total_amount": 45000.00,
    "customer_id": "ID000001",
    "bg_code": "KURO0001",
    "division": "KURO0001_001",
    "billadd": {
        "line1": "123 Main St",
        "city": "Bangalore",
        "state": "Karnataka",
        "pincode": "560001"
    },
    "products": [
        {
            "productid": "KCPB2400000001",
            "name": "Custom PC Build",
            "quantity": 1,
            "price": 42000.00
        }
    ],
    "payment": {
        "option": "cashfree",
        "reference": "CF123456789",
        "fees": 840.00,
        "tax": 2100.00,
        "shipping": 500.00
    },
    "timeline": {
        "created_at": "2026-05-17T10:00:00Z",
        "payment_verified_at": "2026-05-17T10:05:00Z",
        "order_confirmed_at": "2026-05-17T10:06:00Z"
    }
}
```

---

## 9. Integration Points

### 9.1 Identity Domain

- Customer lookup via `users_identity.identity_id`
- Address storage linked to `users_identity`
- Order `customer_id` → `users_identity.identity_id`

### 9.2 Procurement Domain

- `orderconversion` pipeline generates procurement indents
- Indent generation via `creating_indent()` → `indentproduct` collection (MongoDB)

### 9.3 Payment Domain

- Cashfree PG integration (sandbox + prod)
- UPI QR code generation (local, `pyqrcode`)
- Webhook signature verification (HMAC-SHA256)

### 9.4 Outbox Pattern

- `order.payment_verified` event → triggers `orderconversion` pipeline
- `order.placed` event → updates customer metrics (`order_count`, `total_spent`)
- Custom PC cloning via `transaction.on_commit`

---

## 10. Guardrails

### 10.1 Transaction Integrity

All order writes must use `transaction.on_commit` for MongoDB side-effects:

```python
from django.db import transaction
from plat.outbox.service import publish_event

def complete_order(order):
    with transaction.atomic():
        order.status = 'confirmed'
        order.save()

        # Queue MongoDB writes in outbox
        transaction.on_commit(lambda: publish_event(
            event_type='order.payment_verified',
            payload={
                'order_id': order.id,
                'orderid': order.orderid,
                'customer_id': order.customer_id,
            }
        ))
```

### 10.2 Address Immutability

```python
def update_address(address_id, updates):
    address = Address.objects.get(id=address_id)
    if address.is_used:
        # Clone address, mark old as decommissioned
        address.delete_flag = True
        address.save()

        new_address = Address.objects.create(
            identity_id=address.identity_id,
            **{**address.__dict__, **updates},
            delete_flag=False,
        )
        return new_address
    else:
        # In-place update
        for key, value in updates.items():
            setattr(address, key, value)
        address.save()
        return address
```

### 10.3 Webhook Security

All Cashfree webhooks must verify HMAC-SHA256 signature before processing.

---

## 11. Migration Notes

### 11.1 From Legacy E-Shop

| Legacy | Target | Change |
|---|---|---|
| `Addresslist.user_id` → `CustomUser` | `Address.identity_id` → `users_identity` | FK change |
| `Orders.user_id` → `CustomUser` | `orders_core.customer_id` → `users_identity` | FK change |
| `Cart.user_id` → `CustomUser` | `Cart.user_id` → `users_identity` | FK change |
| `Wishlist.user_id` → `CustomUser` | `Wishlist.user_id` → `users_identity` | FK change |
| `custombuilds` (Mongo) | `custombuilds` (Mongo) + outbox event | Outbox integration |
| `orderconversion` (direct Mongo) | `orderconversion` (outbox event) | Outbox integration |

### 11.2 Phase 3b Gaming Collections

12 gaming collections from `kuro-gaming-dj-backend` deferred to Phase 3b. See `migration_spec.md` (M5).

---

> **Implementation state:** Target architecture only. Legacy e-shop codebase in `kuro-gaming-dj-backend`. Integration deferred to Phase 3b (gaming) and Phase 8 (orders). Outbox integration required for transaction integrity.
