# Cafe Platform Domain Specification

**Status:** Spec — TARGET  
**Date:** 2026-05-17  
**Source:** `KungOS_Endpoint_Design.md`, `cafe-council-review.md`, `platform_primitives.md`  
**Purpose:** Authoritative spec for cafe platform domain — sessions, stations, F&B orders, wallet, pricing

---

## 1. Domain Overview

The cafe platform manages gaming cafe operations: station leasing, session billing, F&B orders, wallet transactions, and game catalog.

### 1.1 Domain Boundaries

| Boundary | Inside Domain | Outside Domain |
|---|---|---|
| **Identity** | Walk-in creation, wallet binding | Auth, RBAC, employee management |
| **Sessions** | Station leases, time billing, game selection | Esports tournaments, player rankings |
| **F&B** | Food orders, inventory, pricing | E-commerce orders, procurement |
| **Wallet** | Prepaid balance, transactions, refunds | Payment gateway, inward/outward payments |
| **Pricing** | Price plans, member plans, tiers | Product catalog, e-commerce pricing |

### 1.2 Council Review Decisions (Locked)

From `cafe-council-review.md` (2026-05-13, all three reviewers agree):

| Decision | Status | Rationale |
|---|---|---|
| **Session-attached F&B** | ❌ REJECT | Lifecycle mismatch, inventory integrity risk, God object |
| **Separate `cafe-fnb/` domain** | ✅ ADOPT | Clean bounded context, independent scaling |
| **Protocol chain bypass** | ⚠️ CRITICAL | Domains query DB directly, must enforce protocol usage |
| **Rename `rebellion/cafe/`** | ✅ RENAME | Brand name on generic code is misleading |
| **Session references F&B** | ✅ AGREE | Thin FK or `order_id` reference, not food_charges accumulation |

### 1.3 Lightweight Implementation (GPT-OSS Recommendation)

For 3 cafes at current scale:

| Level | Approach |
|---|---|
| **Database** | All F&B data in existing `kgorders` collection. Session stores `order_id` reference. |
| **Domain** | Lightweight `cafe-fnb/` with only gateway to Mongo (`OrderGateway.get_by_order_id`). No event bus. |
| **Protocol** | Thin adapter layer exposing F&B via existing `ICafeSessionService` contract |
| **Session model** | Delete `food_charges`; add `last_order_id` (nullable). GUI shows real amount via single Mongo lookup. |
| **Endpoint** | Remove all food-order endpoints not yet implemented. Keep FoodOrderModal on hold. |

---

## 2. Session Management

### 2.1 Session Lifecycle

```
Station Available
       │
       ▼
Session Created (game selected, price plan applied)
       │
       ▼
Session Active (time billing, station control)
       │
       ├── F&B Order Placed → OrderGateway → kgorders (MongoDB)
       │
       ▼
Session Ended (final billing, wallet deduction, outbox event)
       │
       ▼
Station Available
```

### 2.2 `caf_platform_sessions` — Session Model

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `cafe_id` | bigint | FK → `caf_platform_cafes.id` |
| `station_id` | bigint | FK → `caf_platform_stations.id` |
| `game_id` | bigint | FK → `caf_platform_games.id` |
| `price_plan_id` | bigint | FK → `caf_platform_price_plans.id` |
| `identity_id` | char(20) | FK → `users_identity.identity_id` (TARGET) |
| `status` | varchar | `active`/`ended`/`cancelled` |
| `start_time` | timestamptz | |
| `end_time` | timestamptz | NULL |
| `total_charges` | decimal(12,2) | Time billing + F&B charges |
| `time_charges` | decimal(12,2) | Time-only billing |
| `food_charges` | decimal(12,2) | **DEPRECATED** — use `last_order_id` reference |
| `last_order_id` | varchar | **NEW** — reference to F&B order in `kgorders` |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Design decision:** `food_charges` column is unused (dead code). Replace with `last_order_id` reference. GUI shows real amount via single Mongo lookup.

### 2.3 `caf_platform_session_leases` — Lease Versioning

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `session_id` | bigint | FK → `caf_platform_sessions.id` |
| `station_id` | bigint | FK → `caf_platform_stations.id` |
| `lease_version` | integer | Version number |
| `start_time` | timestamptz | |
| `end_time` | timestamptz | NULL |
| `status` | varchar | `active`/`released` |
| `created_at` | timestamptz | |

### 2.4 Session End Flow (Critical)

**Current risk:** `session_end()` writes to PostgreSQL (session billing) and MongoDB (F&B charges) in the same request. If PG succeeds but MongoDB fails (or vice versa), the system enters split-brain state.

**Remediation:** F&B operational adapter (`OrderGateway`) must publish an outbox event (`order.placed`) using `plat/outbox/` primitive.

```python
from django.db import transaction
from plat.outbox.service import publish_event

def end_session(session):
    with transaction.atomic():
        session.status = 'ended'
        session.end_time = timezone.now()
        session.total_charges = calculate_final_charges(session)
        session.save()

        # Queue F&B write in outbox (not direct Mongo call)
        transaction.on_commit(lambda: publish_event(
            event_type='fnb.session_billing',
            payload={
                'session_id': session.id,
                'last_order_id': session.last_order_id,
                'total_charges': session.total_charges,
            }
        ))
```

---

## 3. Station Management

### 3.1 `caf_platform_stations` — Station Registry

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `cafe_id` | bigint | FK → `caf_platform_cafes.id` |
| `code` | varchar | Station code (e.g. `ST-001`), UNIQUE `(cafe_id, code)` |
| `label` | varchar | Display name |
| `status` | varchar | `available`/`occupied`/`maintenance` |
| `ip_address` | varchar | Station IP |
| `mac_address` | varchar | Station MAC |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 3.2 `caf_platform_station_commands` — Remote Control

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `station_id` | bigint | FK → `caf_platform_stations.id` |
| `command_type` | varchar | `lock`/`unlock`/`restart`/`shutdown` |
| `payload` | jsonb | Command parameters |
| `status` | varchar | `pending`/`executed`/`failed` |
| `response` | jsonb | Station response |
| `created_at` | timestamptz | |
| `executed_at` | timestamptz | NULL |
| `created_by_id` | varchar | FK → `users_customuser.userid` |

### 3.3 `caf_platform_station_events` — Event Log

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `station_id` | bigint | FK → `caf_platform_stations.id` |
| `event_type` | varchar | `connected`/`disconnected`/`error` |
| `payload` | jsonb | Event data |
| `created_at` | timestamptz | |

---

## 4. F&B Orders (Lightweight)

### 4.1 `cafe-fnb/` Domain Structure

```
cafe-fnb/
├── models.py      — FoodOrder, MenuItem (lightweight)
├── services.py    — OrderGateway (Mongo adapter)
├── views.py       — F&B order endpoints
├── urls.py        — URL routing
└── protocols.py   — ICafeFnbService (Protocol interface)
```

### 4.2 OrderGateway — MongoDB Adapter

```python
class OrderGateway:
    """Lightweight gateway to MongoDB kgorders collection.

    Reads from legacy MongoDB but exposes clean domain format.
    Uses TenantCollection wrapper for tenant isolation.
    """

    def __init__(self):
        self.collection = get_collection('kgorders')

    def get_by_order_id(self, order_id: str) -> dict:
        """Get order by ID with tenant filtering."""
        return self.collection.find_one({'orderid': order_id})

    def create_order(self, order: dict) -> str:
        """Create order with tenant context injection."""
        result = self.collection.insert_one(order)
        return str(result.inserted_id)

    def update_order(self, order_id: str, updates: dict) -> bool:
        """Update order with tenant context injection."""
        result = self.collection.update_one(
            {'orderid': order_id},
            {'$set': updates}
        )
        return result.modified_count > 0
```

### 4.3 F&B Order Flow

```
Customer selects food items
       │
       ▼
POST /api/v1/cafe-fnb/orders/ (payload includes session_id)
       │
       ▼
OrderGateway.create_order() → kgorders (MongoDB)
       │
       ▼
Session.last_order_id = order.orderid (reference, not embedding)
       │
       ▼
GUI shows real amount via single Mongo lookup
```

**Endpoint change:** `POST /cafe/sessions/<id>/food` → `POST /cafe-fnb/orders/` (payload includes `session_id`)

---

## 5. Wallet Management

### 5.1 `caf_platform_wallets` — Wallet Model

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `wallet_id` | varchar | UNIQUE |
| `identity_id` | char(20) | FK → `users_identity.identity_id` (**TARGET**) |
| `balance` | decimal(12,2) | Current balance |
| `status` | varchar | `active`/`suspended`/`closed` |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Critical change:** `customer_id` FK → `users_customuser.userid` (LIVE) → `identity_id` FK → `users_identity.identity_id` (TARGET). Allows walk-ins to have wallets.

### 5.2 `caf_platform_wallet_transactions` — Transaction Log

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `wallet_id` | bigint | FK → `caf_platform_wallets.id` |
| `transaction_type` | varchar | `credit`/`debit`/`refund` |
| `amount` | decimal(12,2) | |
| `balance_after` | decimal(12,2) | |
| `reference` | varchar | Reference ID (session, order, etc.) |
| `description` | varchar | |
| `created_by_id` | varchar | FK → `users_customuser.userid` |
| `created_at` | timestamptz | |

---

## 6. Pricing & Members

### 6.1 `caf_platform_price_plans` — Price Plans

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `cafe_id` | bigint | FK → `caf_platform_cafes.id` |
| `name` | varchar | Plan name |
| `price` | decimal(12,2) | Price per unit |
| `duration` | integer | Duration (minutes) |
| `config` | jsonb | Plan configuration |
| `is_active` | boolean | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### 6.2 `caf_platform_member_plans` — Member Tiers

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `plan_id` | varchar | UNIQUE |
| `tier` | varchar | `edge`/`titan`/`s` |
| `discount_percentage` | decimal(5,2) | |
| `is_active` | boolean | |
| `created_at` | timestamptz | |

### 6.3 `caf_platform_games` — Game Catalog

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `cafe_id` | bigint | FK → `caf_platform_cafes.id` |
| `name` | varchar | Game name |
| `category` | varchar | Game category |
| `is_active` | boolean | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

---

## 7. Walk-in Management

### 7.1 `caf_platform_walkins` — Walk-in Model

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `identity_id` | char(20) | FK → `users_identity.identity_id` (**TARGET**) |
| `phone` | varchar | **DEPRECATED** — phone lives in `users_identity` |
| `name` | varchar | Display name |
| `created_at` | timestamptz | |

**Changes:**
- `phone` uniqueness dropped — phone lives in `users_identity` only
- `identity_id` FK added — links to `users_identity`
- `CafeUser` replaced by `users_identity`

### 7.2 Walk-in → Customer Migration Path

```
Walk-in creates identity (phone-only, user=NULL)
       │
       ▼
Walk-in registers (creates CustomUser account)
       │
       ▼
Identity.user FK set → CustomUser.userid
       │
       ▼
Identity now has customer_profile extension
       │
       ▼
Walk-in record updated (identity_id unchanged)
```

---

## 8. API Contract

### 8.1 Cafe Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/cafe/sessions` | List sessions | JWT |
| `POST` | `/api/v1/cafe/sessions` | Create session | JWT |
| `GET` | `/api/v1/cafe/sessions/{id}` | Session detail | JWT |
| `POST` | `/api/v1/cafe/sessions/{id}/end` | End session | JWT |
| `GET` | `/api/v1/cafe/stations` | List stations | JWT |
| `POST` | `/api/v1/cafe/stations/{id}/command` | Station command | JWT |
| `GET` | `/api/v1/cafe/wallet` | Wallet balance | JWT |
| `POST` | `/api/v1/cafe/wallet/topup` | Wallet top-up | JWT |
| `GET` | `/api/v1/cafe/wallet/transactions` | Transaction history | JWT |
| `GET` | `/api/v1/cafe/games` | Game catalog | Public |
| `GET` | `/api/v1/cafe/price-plans` | Price plans | Public |
| `GET` | `/api/v1/cafe/member-plans` | Member plans | Public |

### 8.2 F&B Endpoints (Lightweight)

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/cafe-fnb/menu` | Menu items | Public |
| `POST` | `/api/v1/cafe-fnb/orders` | Create order | JWT |
| `GET` | `/api/v1/cafe-fnb/orders/{id}` | Order detail | JWT |

---

## 9. Integration Points

### 9.1 Identity Domain

- Walk-in creation → `users_identity` (phone-only, `user=NULL`)
- Wallet binding → `users_identity.identity_id` (not `CustomUser`)
- Session `identity_id` → `users_identity.identity_id`

### 9.2 Outbox Pattern

- `fnb.session_billing` event → triggers F&B MongoDB write after PG commit
- `wallet.transaction` event → updates wallet balance

### 9.3 E-Commerce Domain

- F&B orders stored in `kgorders` (MongoDB) — shared with e-commerce
- Order conversion pipeline may reference cafe orders

---

## 10. Guardrails

### 10.1 Transaction Integrity

All session-end operations must use `transaction.on_commit` for MongoDB side-effects:

```python
from django.db import transaction
from plat.outbox.service import publish_event

def end_session(session):
    with transaction.atomic():
        session.status = 'ended'
        session.end_time = timezone.now()
        session.save()

        # Queue F&B write in outbox
        transaction.on_commit(lambda: publish_event(
            event_type='fnb.session_billing',
            payload={
                'session_id': session.id,
                'last_order_id': session.last_order_id,
            }
        ))
```

### 10.2 Protocol Enforcement

All domains must use protocol interfaces, not direct DB queries:

```python
from cafe.protocols import ICafeSessionService

class CafeSessionService(ICafeSessionService):
    def create_session(self, cafe_id: int, station_id: int, game_id: int) -> Session:
        # Implementation
        pass

    def end_session(self, session_id: int) -> Session:
        # Implementation with outbox event
        pass
```

### 10.3 Tenant Isolation

All cafe queries must include tenant context (`bg_code`, `div_code`):

```python
# Via TenantCollection wrapper
collection = get_collection('kgorders')
orders = collection.find({'session_id': session_id})  # bg_code auto-injected
```

---

> **Implementation state:** Cafe platform is LIVE with 14 PostgreSQL tables. Walk-in identity FK and wallet binding changes require migration (see `migration_spec.md` M2). F&B domain separation is lightweight (no event bus, single Mongo adapter). Session-end outbox integration required for transaction integrity.
