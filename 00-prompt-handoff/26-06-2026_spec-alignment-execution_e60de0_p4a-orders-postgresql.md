# Phase 4A: Orders to PostgreSQL (M4)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 4A of 5 (parallel with 4B, 4C)
**Dependencies:** Phase 1A (Identity data migration must be complete)
**Estimated effort:** ~60 min / multi-session

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p4a` |
| Entity type | `handoff` |
| Short description | Migrate orders data from MongoDB (4 collections) to PostgreSQL (7 tables). |
| Status | `draft` |
| Source references | `migration_spec.md`, `postgresql_schema.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute orders migration — create models, migrate data, update viewsets |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `domains/orders/models.py` (new/updated models)
- `domains/orders/migrations/` (new migrations)
- `domains/orders/viewsets.py` (update to use PostgreSQL)
- `teams/kurostaff/views.py` (update order queries)
- `tests/test_orders_postgresql.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

Orders data migrated from MongoDB (4 collections) to PostgreSQL (7 tables). All order CRUD operations use PostgreSQL. Data integrity verified (no data loss). Order viewsets functional.

## Implementation Steps

### Step 1: Create PostgreSQL Models

Read `migration_spec.md` for target schema. Create models in `domains/orders/models.py`:

```python
class Order(models.Model):
    order_id = models.CharField(max_length=50, primary_key=True)
    identity_id = models.CharField(max_length=20, db_index=True)
    bg_code = models.CharField(max_length=10, db_index=True)
    div_code = models.CharField(max_length=20, blank=True, default='')
    branch_code = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(max_length=20, default='pending')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class OrderItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_id = models.CharField(max_length=50)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
```

### Step 2: Generate Migrations

```bash
python manage.py makemigrations domains.orders
python manage.py migrate domains.orders
```

### Step 3: Migrate Data from MongoDB

Create data migration script:

```python
# In domains/orders/management/commands/migrate_orders.py
from backend.mongo import get_database
from domains.orders.models import Order, OrderItem

def migrate_orders():
    db = get_database()
    orders_col = db['orders']  # or whatever the Mongo collection is named
    
    for mongo_order in orders_col.find():
        order, created = Order.objects.get_or_create(
            order_id=mongo_order.get('order_id', str(mongo_order['_id'])),
            defaults={
                'identity_id': mongo_order.get('identity_id', ''),
                'bg_code': mongo_order.get('bg_code', mongo_order.get('bgcode', '')),
                'div_code': mongo_order.get('div_code', mongo_order.get('division', '')),
                'status': mongo_order.get('status', 'pending'),
                'total_amount': mongo_order.get('total_amount', 0),
            }
        )
        
        # Migrate items
        for item in mongo_order.get('items', []):
            OrderItem.objects.get_or_create(
                order=order,
                product_id=item.get('product_id', ''),
                defaults={
                    'quantity': item.get('quantity', 1),
                    'unit_price': item.get('unit_price', 0),
                    'total_price': item.get('total_price', 0),
                }
            )
```

### Step 4: Update Viewsets

Update `domains/orders/viewsets.py` to use PostgreSQL models instead of MongoDB queries.

### Step 5: Verify Data Integrity

```python
def verify_migration():
    mongo_count = get_database()['orders'].count_documents({})
    pg_count = Order.objects.count()
    assert mongo_count == pg_count, f"Mismatch: Mongo={mongo_count}, PG={pg_count}"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/orders/models.py` | PostgreSQL models |
| Create | `domains/orders/migrations/` | Schema migrations |
| Create | `domains/orders/management/commands/migrate_orders.py` | Data migration |
| Modify | `domains/orders/viewsets.py` | Use PostgreSQL models |
| Modify | `teams/kurostaff/views.py` | Update order queries |
| Create | `tests/test_orders_postgresql.py` | Verify migration |

## Completion Gate

- [ ] All order data migrated to PostgreSQL
- [ ] Order CRUD functional
- [ ] Data integrity verified (no data loss)
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed
