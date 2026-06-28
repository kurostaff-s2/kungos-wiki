# Cafe F&B Orders — Target State Specification

**Status:** Draft — Proposal  
**Date:** 2026-06-27  
**Source:** Architecture analysis, `cafe_spec.md`, `postgresql_schema.md`, `data_mapping.md`  
**Purpose:** Define target state for cafe gaming F&B orders — PostgreSQL `orders_core` + `cafe_fnb_detail`  
**Depends on:** Phase 8 migration (M4: orders to PostgreSQL)

---

## 1. Problem Statement

### 1.1 Current State (Broken)

The `cafe_spec.md` (Phase 2B interim) says:
> "All F&B data in existing `kgorders` collection."

**But `kgorders` is:**
- Legacy MongoDB collection for **in-store retail orders** (physical store, eshop products)
- Being migrated to PostgreSQL `in_store_detail` in Phase 8
- Designed for restaurant-style orders (table numbers, `dine_in: true`)

**Result:** Schema mismatch → 500 Internal Server Error on `GET /api/v1/cafe-fnb/orders`

### 1.2 Legacy Collection Disposition

| Collection | Purpose | Target |
|------------|---------|--------|
| `kgorders` | In-store retail orders (physical store) | → PostgreSQL `in_store_detail` (Phase 8) |
| `offline_orders` | Same as `kgorders` (alt name) | → PostgreSQL `in_store_detail` |
| **No cafe F&B collection** | — | — |

**Key finding:** There is **no legacy cafe F&B collection** in MongoDB. The `cafe_spec.md`'s reference to `kgorders` is incorrect.

### 1.3 Target State Gap

| Domain | Current Storage | Target Storage | Status |
|--------|----------------|----------------|--------|
| Arcade Sessions | PostgreSQL `caf_platform_sessions` | ✅ Already PG | Done |
| Arcade Billing | Embedded in session | ✅ Already PG | Done |
| **Cafe F&B Orders** | MongoDB `kgorders` (WRONG) | ❓ **Undefined** | **Gap** |
| In-store Retail | MongoDB `kgorders` | PostgreSQL `in_store_detail` | Phase 8 |
| E-commerce | MongoDB (Phase 3b deferred) | PostgreSQL `eshop_detail` | Phase 3b |

---

## 2. Target Architecture

### 2.1 Design Decision

**All orders live in PostgreSQL.** Follow the Phase 8 pattern: unified `orders_core` with domain-specific detail tables.

```
┌─────────────────────────────────────────────────────────────────┐
│                    TARGET STATE (PostgreSQL)                    │
├─────────────────────────────────────────────────────────────────┤
│  orders_core (13 cols)                                          │
│  ├── estimate_detail (estimates)                                │
│  ├── in_store_detail (kgorders)                                 │
│  ├── tp_order_detail (tporders)                                 │
│  ├── service_detail (serviceRequest)                            │
│  ├── eshop_detail (e-commerce)                                  │
│  └── cafe_fnb_detail (cafe gaming F&B) ← NEW                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Why PostgreSQL, Not MongoDB?

| Criterion | PostgreSQL | MongoDB |
|-----------|------------|---------|
| **Relational integrity** | ✅ FK to sessions, wallets, identities | ❌ No referential integrity |
| **ACID transactions** | ✅ Single transaction for session end + F&B | ❌ Split-brain risk |
| **Tenant isolation** | ✅ Standard `(bg_code, div_code)` indexes | ✅ `TenantCollection` wrapper |
| **Reporting/analytics** | ✅ Structured queries | ❌ JSONB limits aggregation |
| **Consistency** | ✅ All orders in one system | ❌ Split between PG + Mongo |

---

## 3. Schema Design

### 3.1 `orders_core` — Unified Orders Table

**Shared by all order types.** Already defined in `postgresql_schema.md` Section 7.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | bigint | NOT NULL | — | **PRIMARY KEY** |
| `orderid` | varchar(50) | NOT NULL | — | **UNIQUE**, business key |
| `order_type` | varchar(20) | NOT NULL | — | ENUM: `estimate`, `in_store`, `tp`, `service`, `eshop`, `cafe_fnb` |
| `status` | varchar(20) | NOT NULL | `'pending'` | ENUM: `pending`, `confirmed`, `preparing`, `ready`, `completed`, `cancelled` |
| `total_amount` | decimal(12,2) | NOT NULL | — | Total order amount |
| `identity_id` | char(20) | NULL | — | FK → `users_identity.identity_id` |
| `delete_flag` | boolean | NOT NULL | `False` | Soft delete flag |
| `bg_code` | varchar(10) | NOT NULL | — | FK → `tenant_business_groups.bg_code` |
| `div_code` | varchar(20) | NOT NULL | — | FK → `tenant_divisions.div_code` |
| `branch_code` | varchar(30) | NULL | — | FK → `tenant_branches.branch_code` |
| `products` | jsonb | NOT NULL | `[]` | Order items (structured) |
| `channel` | varchar(50) | NOT NULL | — | Order channel (e.g., `cafe`, `eshop`, `in_store`) |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

**Indexes:**
- `idx_orders_core_type`: `(order_type)` — filter by order type
- `idx_orders_core_identity`: `(identity_id)` — identity order history
- `idx_orders_core_tenant`: `(bg_code, div_code)` — tenant isolation
- `idx_orders_core_status`: `(status)` — status filtering

### 3.2 `cafe_fnb_detail` — Cafe F&B Specific Fields

**NEW TABLE** — extends `orders_core` with cafe gaming F&B fields.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `order` | bigint | NOT NULL | — | **PRIMARY KEY**, FK → `orders_core.id`, CASCADE |
| `session_id` | bigint | NULL | — | FK → `caf_platform_sessions.id`, CASCADE (NULL for walk-ins) |
| `identity_id` | char(20) | NOT NULL | — | FK → `users_identity.identity_id`, CASCADE (REQUIRED) |
| `items` | jsonb | NOT NULL | `[]` | F&B items: `[{name, qty, price, category}]` |
| `payment_method` | varchar(20) | NOT NULL | `'cash'` | ENUM: `wallet`, `cash`, `upi` |
| `order_source` | varchar(20) | NOT NULL | `'kiosk'` | ENUM: `kiosk`, `staff`, `mobile`, `web` |
| `prepared_at` | timestamptz | NULL | — | When F&B was prepared |
| `completed_at` | timestamptz | NULL | — | When F&B was handed to customer |

**Indexes:**
- `idx_cafe_fnb_session`: `(session_id)` — session F&B lookup
- `idx_cafe_fnb_identity`: `(identity_id)` — identity order history
- `idx_cafe_fnb_payment`: `(payment_method)` — payment filtering

**Constraints:**
- `chk_cafe_fnb_requires_session_or_identity`: CHECK (`session_id` IS NOT NULL OR `identity_id` IS NOT NULL) — F&B must be linked to session OR identity (walk-ins)
- `chk_cafe_fnb_payment_method`: CHECK (`payment_method` IN ('wallet', 'cash', 'upi'))
- `chk_cafe_fnb_order_source`: CHECK (`order_source` IN ('kiosk', 'staff', 'mobile', 'web'))

### 3.3 `cafe_fnb_refunds` — Refund Tracking

**NEW TABLE** — tracks all F&B refunds for audit trail.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | bigint | NOT NULL | — | **PRIMARY KEY** |
| `order` | bigint | NOT NULL | — | FK → `cafe_fnb_detail.order`, CASCADE |
| `refund_type` | varchar(20) | NOT NULL | — | ENUM: `full`, `partial`, `item` |
| `amount` | decimal(12,2) | NOT NULL | — | Refund amount |
| `reason` | varchar(255) | NOT NULL | — | Refund reason |
| `refunded_by` | char(20) | NULL | — | FK → `users_identity.identity_id` |
| `created_at` | timestamptz | NOT NULL | — | Refund timestamp |

**Indexes:**
- `idx_cafe_fnb_refunds_order`: `(order)` — order refund history
- `idx_cafe_fnb_refunds_created`: `(created_at)` — date filtering

**Constraints:**
- `chk_cafe_fnb_refund_amount`: CHECK (`amount` > 0) — refund must be positive
- `chk_cafe_fnb_refund_type`: CHECK (`refund_type` IN ('full', 'partial', 'item'))

### 3.4 Sample Document → Row Mapping

**OrderCore row:**
```python
OrderCore(
    orderid='CFNB000001',
    order_type='cafe_fnb',
    status='completed',
    total_amount=250.00,
    identity_id='ID000001',
    bg_code='KURO0001',
    div_code='KURO0001_001',
    branch_code='KURO0001_001_001',
    products=[{'name': 'Coffee', 'qty': 2, 'price': 100.00}, {'name': 'Burger', 'qty': 1, 'price': 150.00}],
    channel='cafe',
)
```

**CafeFnbDetail row:**
```python
CafeFnbDetail(
    order=1,  # FK → orders_core.id
    session=42,  # FK → caf_platform_sessions.id
    items=[{'name': 'Coffee', 'qty': 2, 'price': 50.00, 'category': 'beverage'}, {'name': 'Burger', 'qty': 1, 'price': 150.00, 'category': 'food'}],
    payment_method='wallet',
    order_source='kiosk',
    prepared_at=timezone.now(),
    completed_at=timezone.now(),
)
```

---

## 4. Integration with Cafe Arcade

### 4.1 Session End Flow (Updated)

**Current (broken):** Session end writes to PG, F&B in MongoDB `kgorders` (schema mismatch).

**Target:** Session end writes to PG only. F&B charged to wallet in same transaction.

```python
from django.db import transaction
from django.utils import timezone
from cafe_arcade.models import CafeWallet

def end_session(session_id: int, bg_code: str) -> dict:
    """End session, charge F&B, update wallet — all in one transaction."""
    with transaction.atomic():
        session = CafPlatformSession.objects.select_related(
            'cafe', 'station', 'game', 'price_plan'
        ).get(id=session_id)
        
        # 1. Calculate time charges
        time_charges = calculate_time_charges(session)
        
        # 2. Load F&B orders for this session
        fnb_orders = CafeFnbDetail.objects.filter(session=session).select_related('order')
        fnb_total = sum(order.order.total_amount for order in fnb_orders)
        
        # 3. Update session
        session.status = 'ended'
        session.end_time = timezone.now()
        session.time_charges = time_charges
        session.total_charges = time_charges + fnb_total
        session.save()
        
        # 4. Charge wallet (if wallet payment)
        wallet = CafeWallet.objects.filter(identity=session.identity).first()
        if wallet and wallet.balance >= session.total_charges:
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='debit',
                amount=session.total_charges,
                balance_after=wallet.balance - session.total_charges,
                reference=f'session_{session.id}',
                description=f'Session end: {session.time_charges} + F&B {fnb_total}',
            )
            wallet.balance -= session.total_charges
            wallet.save()
        
        # 5. Update customer stats (synchronous, no outbox needed)
        customer = session.identity.users_customer
        customer.order_count += len(fnb_orders)
        customer.total_spent += fnb_total
        customer.last_order_date = timezone.now().date()
        customer.save()
        
        return {
            'session_id': session.id,
            'time_charges': time_charges,
            'fnb_total': fnb_total,
            'total_charges': session.total_charges,
            'fnb_orders': [
                {'orderid': o.order.orderid, 'total': o.order.total_amount}
                for o in fnb_orders
            ],
        }
```

### 4.2 F&B Order Creation Flow

```python
import uuid
from django.db import transaction

def create_fnb_order(session_id: int, items: list, payment_method: str, order_source: str) -> dict:
    """Create F&B order linked to session."""
    with transaction.atomic():
        session = CafPlatformSession.objects.get(id=session_id, status='active')
        
        # Calculate total
        total = sum(item['qty'] * item['price'] for item in items)
        
        # Generate unique order ID (UUID4 to avoid collisions)
        orderid = f'CFNB{uuid.uuid4().hex[:12].upper()}'
        
        # Create order_core row
        order = OrderCore.objects.create(
            orderid=orderid,
            order_type='cafe_fnb',
            status='pending',
            total_amount=total,
            identity_id=session.identity_id,
            bg_code=session.cafe.bg_code,
            div_code=session.cafe.div_code,
            branch_code=session.cafe.branch_code,
            products=[{'name': item['name'], 'qty': item['qty'], 'price': item['price']} for item in items],
            channel='cafe',
        )
        
        # Create cafe_fnb_detail row
        CafeFnbDetail.objects.create(
            order=order,
            session=session,
            identity=session.identity,
            items=items,
            payment_method=payment_method,
            order_source=order_source,
        )
        
        return {
            'orderid': order.orderid,
            'total': total,
            'items': items,
        }
```

### 4.3 Walk-in Order Creation (No Session)

When `session_id` is NULL (walk-in customer at cafe counter):

```python
def create_walkin_fnb_order(identity_id: str, items: list, payment_method: str, order_source: str) -> dict:
    """Create F&B order for walk-in customer (no session)."""
    with transaction.atomic():
        # Calculate total
        total = sum(item['qty'] * item['price'] for item in items)
        
        # Generate unique order ID
        orderid = f'CFNB{uuid.uuid4().hex[:12].upper()}'
        
        # Get tenant context from identity
        identity = UsersIdentity.objects.get(identity_id=identity_id)
        customer = identity.users_customer
        
        # Create order_core row
        order = OrderCore.objects.create(
            orderid=orderid,
            order_type='cafe_fnb',
            status='pending',
            total_amount=total,
            identity_id=identity_id,
            bg_code=customer.bg_code,
            div_code=customer.div_code,
            branch_code=customer.branch_code,
            products=[{'name': item['name'], 'qty': item['qty'], 'price': item['price']} for item in items],
            channel='cafe',
        )
        
        # Create cafe_fnb_detail row (session_id = NULL)
        CafeFnbDetail.objects.create(
            order=order,
            session=None,
            identity=identity,
            items=items,
            payment_method=payment_method,
            order_source=order_source,
        )
        
        return {
            'orderid': order.orderid,
            'total': total,
            'items': items,
        }
```

**Key differences from session-based orders:**
- `session_id` is NULL
- `identity_id` is REQUIRED (walk-in must be identified)
- Wallet charged directly to identity's wallet (no session wallet)
- No session billing impact
- Customer counters updated normally

### 4.4 Wallet Deduction on Session End

**Current:** `food_charges` column deprecated, `last_order_id` reference used.

**Target:** Direct wallet deduction in session end transaction. No `last_order_id` reference needed.

```python
# Old (interim):
session.last_order_id = order.orderid  # Reference to MongoDB doc
food_total = 0  # Fallback until OrderGateway lookup implemented

# New (target):
fnb_orders = CafeFnbDetail.objects.filter(session=session)
fnb_total = sum(order.order.total_amount for order in fnb_orders)
# Direct calculation, no MongoDB lookup needed
```

### 4.5 Order Status Transitions

**Current:** Status tracked in `orders_core.status` field.

**Target:** Define valid status transitions.

```python
ORDER_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('confirmed', 'Confirmed'),
    ('preparing', 'Preparing'),
    ('ready', 'Ready'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]
```

**Valid transitions:**
- `pending` → `confirmed` (order accepted by kitchen)
- `confirmed` → `preparing` (kitchen started)
- `preparing` → `ready` (F&B ready for pickup)
- `ready` → `completed` (handed to customer)
- Any → `cancelled` (cancelled by staff/customer)

**Invalid transitions:**
- `completed` → `pending` (no re-opening)
- `cancelled` → any (no reactivation)

**Implementation:**
```python
def update_order_status(order_id: int, new_status: str, updated_by: str) -> dict:
    """Update order status with transition validation."""
    order = OrderCore.objects.get(id=order_id)
    
    # Validate transition
    valid_transitions = {
        'pending': ['confirmed', 'cancelled'],
        'confirmed': ['preparing', 'cancelled'],
        'preparing': ['ready', 'cancelled'],
        'ready': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': [],
    }
    
    if new_status not in valid_transitions.get(order.status, []):
        raise ValidationError(f"Invalid transition: {order.status} → {new_status}")
    
    order.status = new_status
    order.updated_by = updated_by
    order.updated_at = timezone.now()
    order.save()
    
    return {'orderid': order.orderid, 'status': new_status}
```

### 4.6 Order Cancellation Flow

**Current:** No cancellation flow defined.

**Target:** Define cancellation workflow.

```python
def cancel_order(order_id: int, reason: str, cancelled_by: str) -> dict:
    """Cancel order with reason."""
    order = OrderCore.objects.get(id=order_id)
    
    if order.status == 'completed':
        raise ValidationError("Cannot cancel completed order")
    
    if order.status == 'cancelled':
        raise ValidationError("Order already cancelled")
    
    order.status = 'cancelled'
    order.cancelled_by = cancelled_by
    order.cancelled_at = timezone.now()
    order.cancel_reason = reason
    order.save()
    
    # Reverse wallet charge (if wallet payment)
    if order.payment_method == 'wallet':
        wallet = CafeWallet.objects.filter(identity=order.identity).first()
        if wallet:
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='refund',
                amount=order.total_amount,
                balance_after=wallet.balance + order.total_amount,
                reference=f'cancel_{order.id}',
                description=f'Order cancelled: {reason}',
            )
            wallet.balance += order.total_amount
            wallet.save()
    
    return {'orderid': order.orderid, 'status': 'cancelled'}
```

---

## 5. Migration Plan

### 5.1 Phase 8 Migration (M4) — Updated Scope

**Original scope:** 4 MongoDB collections → `orders_core` + 6 detail tables.

**Updated scope:** Add `cafe_fnb_detail` to Phase 8.

| Migration | Scope | Risk | Status |
|-----------|-------|------|--------|
| M4a | `estimates` → `estimate_detail` | MEDIUM | Not started |
| M4b | `kgorders` → `in_store_detail` | MEDIUM | Not started |
| M4c | `tporders` → `tp_order_detail` | LOW | Not started |
| M4d | `serviceRequest` → `service_detail` | LOW | Not started |
| **M4e** | **Create `cafe_fnb_detail` table** | **LOW** | **Not started** |
| M4f | `eshop` → `eshop_detail` (Phase 3b) | MEDIUM | Deferred |

### 5.2 Django Migration

```python
# cafe_arcade/migrations/0004_cafe_fnb_orders.py
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('cafe_arcade', '0003_session_order_ref'),
        ('orders', '0001_initial'),  # Phase 8 migration
    ]
    
    operations = [
        migrations.CreateModel(
            name='CafeFnbDetail',
            fields=[
                ('order', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True,
                    serialize=False,
                    to='orders.ordercore'
                )),
                ('session', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='cafe_arcade.cafplatformsession'
                )),
                ('identity', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='users_identity.identity_id'
                )),
                ('items', models.JSONField(default=list)),
                ('payment_method', models.CharField(
                    choices=[('wallet', 'Wallet'), ('cash', 'Cash'), ('upi', 'UPI')],
                    default='cash',
                    max_length=20
                )),
                ('order_source', models.CharField(
                    choices=[('kiosk', 'Kiosk'), ('staff', 'Staff'), ('mobile', 'Mobile'), ('web', 'Web')],
                    default='kiosk',
                    max_length=20
                )),
                ('prepared_at', models.DateTimeField(null=True)),
                ('completed_at', models.DateTimeField(null=True)),
            ],
            options={
                'db_table': 'cafe_fnb_detail',
            },
        ),
        migrations.AddIndex(
            model_name='cafe_fnb_detail',
            index=models.Index(
                fields=['session'],
                name='idx_cafe_fnb_session'
            ),
        ),
        migrations.AddIndex(
            model_name='cafe_fnb_detail',
            index=models.Index(
                fields=['identity'],
                name='idx_cafe_fnb_identity'
            ),
        ),
        migrations.AddConstraint(
            model_name='cafe_fnb_detail',
            constraint=models.CheckConstraint(
                check=Q(session_id__isnull=False) | Q(identity_id__isnull=False),
                name='chk_cafe_fnb_requires_session_or_identity'
            ),
        ),
    ]
```

### 5.3 Application Code Changes

| File | Change | Priority |
|------|--------|----------|
| `domains/cafe_fnb/gateways.py` | Replace MongoDB `OrderGateway` with Django ORM | HIGH |
| `domains/cafe_fnb/views.py` | Update views to use ORM | HIGH |
| `domains/cafe_fnb/serializers.py` | Update serializers for PG schema | HIGH |
| `domains/cafe_arcade/models.py` | Remove `last_order_id` field (no longer needed) | MEDIUM |
| `domains/cafe_arcade/views.py` | Update `session_end()` to use direct calculation | MEDIUM |
| `users/models.py` | Update `users_customer` counters (order_count, total_spent) | LOW |

### 5.4 Migration Validation

```
✅ Row count reconciliation per source:
   estimates: 4,308 source → 4,308 output (0 dropped)
   kgorders: 9,162 source → 9,162 output (0 dropped)
   tporders: 229 source → 229 output (0 dropped)
   serviceRequest: 1,625 source → 1,625 output (0 dropped)

✅ Schema validation: all `cafe_fnb_detail` rows have valid session FK
✅ Tenant isolation: all rows have valid bg_code, div_code, branch_code
✅ FK integrity: 0 orphaned cafe_fnb_detail rows
✅ Customer counters: order_count, total_spent sums match legacy orders
✅ Index creation: all indexes built
✅ Constraint validation: all CHECK constraints pass
```

---

## 6. API Contract

### 6.1 Endpoints (Updated)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/api/v1/cafe-fnb/menu` | Menu items (from `stock_register`) | Public |
| `POST` | `/api/v1/cafe-fnb/orders` | Create F&B order (linked to session) | JWT |
| `GET` | `/api/v1/cafe-fnb/orders/{id}` | Order detail | JWT |
| `GET` | `/api/v1/cafe-fnb/orders` | List orders (with pagination + filters) | JWT |
| `GET` | `/api/v1/cafe-fnb/orders/session/{session_id}` | F&B orders for session | JWT |

### 6.2 Response Schema

**`OrderResponse`:**
```json
{
  "orderid": "CFNB2026062712000142",
  "order_type": "cafe_fnb",
  "status": "completed",
  "total_amount": 250.00,
  "identity": {
    "identity_id": "ID000001",
    "name": "John Doe",
    "phone": "+919876543210"
  },
  "session": {
    "session_id": 42,
    "station_code": "ST-001",
    "start_time": "2026-06-27T12:00:00Z",
    "end_time": null
  },
  "items": [
    {"name": "Coffee", "qty": 2, "price": 50.00, "category": "beverage"},
    {"name": "Burger", "qty": 1, "price": 150.00, "category": "food"}
  ],
  "payment_method": "wallet",
  "order_source": "kiosk",
  "created_at": "2026-06-27T12:05:00Z",
  "completed_at": "2026-06-27T12:15:00Z"
}
```

---

## 7. Guardrails

### 7.1 Transaction Integrity

All session-end operations must use `transaction.atomic()`:

```python
with transaction.atomic():
    # 1. Update session
    # 2. Charge wallet
    # 3. Update customer counters
    # 4. Mark F&B orders as completed
```

### 7.2 Tenant Isolation

All cafe F&B queries must include tenant context:

```python
# Via ORM (automatic with Django)
CafeFnbDetail.objects.filter(
    order__bg_code=request.bg_code,
    order__div_code=request.div_code,
)

# Or via session FK
CafeFnbDetail.objects.filter(
    session__cafe__bg_code=request.bg_code,
    session__cafe__div_code=request.div_code,
)
```

### 7.3 Soft Deletes

All orders use soft delete (no hard deletes):

```python
class OrderCore(models.Model):
    delete_flag = models.BooleanField(default=False)
    
    def delete(self):
        self.delete_flag = True
        self.status = 'cancelled'
        self.save()
```

**Note:** `delete_flag` is included in `orders_core` schema (Section 3.1).

---

## 8. Decisions (Resolved Open Questions)

### 8.1 Walk-in F&B Without Session

**Decision:** Allow `session_id = NULL`, but require `identity_id`

**Rationale:** Walk-ins (no station session) can still buy food/drinks at the cafe counter. F&B order must be linked to a customer for billing, reporting, and loyalty. Session is optional — F&B is the primary entity.

**Schema:**
```python
class CafeFnbDetail(models.Model):
    session = models.ForeignKey(
        'caf_platform_sessions',
        on_delete=models.SET_NULL,
        null=True,  # ALLOW NULL for walk-ins
        blank=True
    )
    identity = models.ForeignKey(
        'users_identity',
        on_delete=models.CASCADE,  # REQUIRED for walk-ins
        null=False,
        blank=False
    )
    
    class Meta:
        constraints = [
            # At least one of session or identity must exist
            models.CheckConstraint(
                check=Q(session_id__isnull=False) | Q(identity_id__isnull=False),
                name='chk_cafe_fnb_requires_session_or_identity'
            ),
        ]
```

**API impact:**
- `POST /api/v1/cafe-fnb/orders` accepts optional `session_id`
- If `session_id` provided: F&B charged to session wallet
- If `session_id` NULL: F&B charged to identity wallet directly

**Note:** `identity_id` is ALWAYS required (even for session-based orders). The constraint ensures at least one of `session_id` or `identity_id` is present, but `identity_id` is required by schema.

---

### 8.2 Refund Workflow

**Decision:** Partial refunds via `cafe_fnb_refunds` table, full refunds via order cancellation

**Rationale:** Partial refunds (wrong item, quality issue) are common. Full refunds require order cancellation (status → `cancelled`). Refunds must link to original order for audit trail.

**Schema:**
```python
class CafeFnbRefund(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(CafeFnbDetail, on_delete=models.CASCADE)
    refund_type = models.CharField(max_length=20, choices=[
        ('full', 'Full Refund'),
        ('partial', 'Partial Refund'),
        ('item', 'Item Refund'),
    ])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    refunded_by = models.ForeignKey('users_identity', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'cafe_fnb_refunds'
```

**Workflow:**
```python
def process_refund(order_id: int, refund_type: str, amount: Decimal, reason: str, item_id: int = None) -> dict:
    """Process F&B refund."""
    with transaction.atomic():
        detail = CafeFnbDetail.objects.select_related('order').get(order=order_id)
        original_order = detail.order
        
        # Validate refund eligibility
        if original_order.status == 'cancelled':
            raise ValidationError("Order already cancelled")
        
        # Validate refund amount
        if refund_type == 'full':
            new_status = 'cancelled'
            refund_amount = original_order.total_amount
        elif refund_type == 'partial':
            new_status = 'completed'
            if amount > original_order.total_amount:
                raise ValidationError("Refund amount exceeds order total")
            refund_amount = amount
        else:  # item refund
            new_status = 'completed'
            if item_id is None:
                raise ValidationError("Item ID required for item refund")
            item = next((i for i in original_order.products if i['id'] == item_id), None)
            if item is None:
                raise ValidationError(f"Item {item_id} not found in order")
            refund_amount = item['qty'] * item['price']
        
        # Create refund record
        refund = CafeFnbRefund.objects.create(
            order=detail,
            refund_type=refund_type,
            amount=refund_amount,
            reason=reason,
            refunded_by=request.identity,
        )
        
        # Reverse wallet charge (if wallet payment)
        wallet = CafeWallet.objects.filter(identity=original_order.identity).first()
        if wallet:
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='refund',
                amount=refund_amount,
                balance_after=wallet.balance + refund_amount,
                reference=f'refund_{refund.id}',
                description=f'Refund: {reason}',
            )
            wallet.balance += refund_amount
            wallet.save()
        
        # Update order status
        original_order.status = new_status
        original_order.total_amount -= refund_amount
        original_order.save()
        
        return {
            'refund_id': refund.id,
            'original_order': original_order.orderid,
            'refund_amount': refund_amount,
            'new_status': new_status,
        }
```

**Guardrails:**
- Refunds only allowed within 24 hours of order completion
- Refunds require manager approval for amounts > ₹500
- Refund history visible in order detail view
- Item refunds require `item_id` parameter

---

### 8.3 Menu Caching Strategy

**Decision:** Cache menu in Redis, invalidate on stock changes

**Rationale:** Menu queries are read-heavy (kiosk, staff app). Stock changes are rare (compared to queries). Redis provides sub-millisecond reads. Invalidates on `stock_register` updates.

**Implementation:**
```python
# plat/cache/menu.py
from django.core.cache import cache

MENU_CACHE_KEY = 'cafe_menu:{bg_code}:{div_code}'
MENU_CACHE_TTL = 300  # 5 minutes

def get_menu(bg_code: str, div_code: str) -> list[dict]:
    """Get cafe menu with caching."""
    cache_key = f'{MENU_CACHE_KEY}:{bg_code}:{div_code}'
    
    # Try cache first
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    # Query from stock_register (MongoDB)
    menu = StockRegister.objects.filter(
        bg_code=bg_code,
        div_code=div_code,
        category__in=['food', 'beverage', 'snack'],
        stock__gt=0,  # Only items with stock
    ).values(
        'product_name', 'category', 'price', 'description', 'image_url'
    )
    
    # Cache for 5 minutes
    cache.set(cache_key, list(menu), MENU_CACHE_TTL)
    
    return menu

def invalidate_menu_cache(bg_code: str, div_code: str) -> None:
    """Invalidate menu cache on stock changes."""
    cache.delete(f'{MENU_CACHE_KEY}:{bg_code}:{div_code}')
```

**Invalidation triggers:**
```python
# stock_register/views.py
class StockRegisterViewSet(viewsets.ModelViewSet):
    def perform_update(self, serializer):
        old_stock = serializer.instance.stock
        new_stock = serializer.validated_data.get('stock', old_stock)
        
        super().perform_update(serializer)
        
        # Invalidate menu cache if stock changed
        if old_stock != new_stock:
            invalidate_menu_cache(
                serializer.instance.bg_code,
                serializer.instance.div_code,
            )
```

**Fallback:** If Redis unavailable, query `stock_register` directly (MongoDB). Cache is optional optimization.

---

### 8.4 Outbox for Customer Counters

**Decision:** Synchronous update (no outbox needed)

**Rationale:** Customer counters (`order_count`, `total_spent`) are updated on session end. Session end is already in a transaction (PG + wallet + F&B). Adding outbox for counters adds complexity without benefit. Counters are read infrequently (dashboards, reports) — stale by milliseconds is acceptable.

**Implementation:**
```python
def end_session(session_id: int) -> dict:
    with transaction.atomic():
        # ... existing logic ...
        
        # Update customer counters (synchronous)
        customer = session.identity.users_customer
        customer.order_count += len(fnb_orders)
        customer.total_spent += fnb_total
        customer.last_order_date = timezone.now().date()
        customer.save()
        
        return {...}
```

**When outbox WOULD be needed:**
- If customer counters were updated asynchronously (e.g., by a background job)
- If counters were updated by multiple services (cafe, eshop, retail)
- If counters needed real-time consistency across services

**Current state:** Single service (cafe_arcade) updates counters. Synchronous is fine.

**Future consideration:** If Phase 3b (eshop) or Phase 9 (retail) also updates customer counters, consider outbox pattern for cross-domain consistency.

---

## 9. Appendix

### 9.1 Related Specs

- `cafe_spec.md` — Cafe platform domain spec
- `postgresql_schema.md` — PostgreSQL schema (Section 7: Orders)
- `data_mapping.md` — MongoDB → PostgreSQL field mappings
- `mongodb_schema.md` — MongoDB collections (Section 3.2: Orders)

### 9.2 Legacy References

- `KungOS_Endpoint_Design.md` — Legacy endpoint design (mentions `cafe_food_detail`)
- `KUNGOS_INTEGRATION_PLAN.md` — Phase 2B completion (cafe_fnb domain created)
- `KungOS_Consolidated_Reference.md` — Consolidated reference (cafe_fnb gateway pattern)

---

> **Implementation state:** Cafe F&B orders target state is **NOT YET IMPLEMENTED**. Current implementation uses MongoDB `kgorders` (incorrect, schema mismatch). Phase 8 migration (M4) must include `cafe_fnb_detail` table creation and application code updates.
