# Phase 4A: Orders to PostgreSQL (M4) — Full Inventory

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 4A of 5 (parallel with 4B, 4C)
**Dependencies:** Phase 1A (Full M1 identity migration must be complete — all 8 storage locations migrated, `identity_id` available for all users)
**Estimated effort:** ~90 min / multi-session (data migration + verification)

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p4a` |
| Entity type | `handoff` |
| Short description | Migrate 4 MongoDB collections (estimates, kgorders, tporders, serviceRequest) to PostgreSQL (orders_core + 6 detail tables). 15,925 total records. Normalize phones to identity_id, validate FK integrity, verify financial data loss. |
| Status | `draft` |
| Source references | `migration_spec.md` §5, `postgresql_schema.md`, `orders_spec.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute M4 migration — create tables, migrate data, normalize, validate |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Source databases:** MongoDB (4 collections)
**Target tables:** PostgreSQL `orders_core` + 6 detail tables
**Key files for this phase:**
- `domains/orders/models.py` (Order, Estimate, InStoreOrder, TPOrder, ServiceRequest models)
- `domains/orders/migrations/` (schema migrations)
- `domains/orders/management/commands/migrate_orders.py` (data migration command)
- `users/models.py` (Identity model — for customer_id linkage)
- `plat/tenant/collection.py` (TenantCollection for Mongo reads)
**Related codebases:** None

## What This Phase Delivers

15,925 order records migrated from MongoDB to PostgreSQL. All orders have valid `identity_id` (customer_id FK → `users_identity`). Tenant codes normalized to canonical format (`bg_code`, `div_code`, `branch_code`). Financial data loss check passes (total_amount sum matches legacy). All order CRUD operations use PostgreSQL. Order viewsets functional.

## Migration Inventory (Per migration_spec.md §5.1)

| Source Collection | Mongo Records | Target Table(s) | Notes |
|-------------------|---------------|-----------------|-------|
| `estimates` | — | `orders_core` + `estimate_detail` | Estimates |
| `kgorders` | — | `orders_core` + `in_store_detail` | In-store orders |
| `tporders` | — | `orders_core` + `tp_order_detail` | Third-party orders |
| `serviceRequest` | 1,625 | `orders_core` + `service_detail` | Service requests |
| **Total** | **15,925** | **7 tables** | |

**Note:** Row counts for estimates, kgorders, and tporders not specified in migration_spec.md — must be verified during migration.

## Implementation Steps

### Step 1: Create PostgreSQL Models

Read `migration_spec.md` §5 and `postgresql_schema.md` for target schema. Create models in `domains/orders/models.py`:

```python
class OrderCore(models.Model):
    """Core order table — all order types share this."""
    order_id = models.CharField(max_length=50, primary_key=True)
    order_type = models.CharField(max_length=20)  # 'estimate', 'in_store', 'tp', 'service'
    identity_id = models.ForeignKey(
        'users.Identity',
        on_delete=models.CASCADE,
        db_index=True,
    )
    customer_name = models.CharField(max_length=200, blank=True, default='')
    customer_phone = models.CharField(max_length=20, blank=True, default='')
    bg_code = models.CharField(max_length=10, db_index=True)
    div_code = models.CharField(max_length=20, blank=True, default='')
    branch_code = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(max_length=20, default='pending')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders_core'


class EstimateDetail(models.Model):
    """Estimate-specific details."""
    order = models.OneToOneField(OrderCore, on_delete=models.CASCADE, related_name='estimate_detail')
    estimate_number = models.CharField(max_length=50, blank=True, default='')
    valid_until = models.DateField(null=True, blank=True)
    items_json = models.JSONField(default=dict)  # Legacy items array


class InStoreDetail(models.Model):
    """In-store order details."""
    order = models.OneToOneField(OrderCore, on_delete=models.CASCADE, related_name='in_store_detail')
    table_number = models.CharField(max_length=10, blank=True, default='')
    dine_in = models.BooleanField(default=False)
    items_json = models.JSONField(default=dict)


class TPOrderDetail(models.Model):
    """Third-party order details."""
    order = models.OneToOneField(OrderCore, on_delete=models.CASCADE, related_name='tp_detail')
    platform = models.CharField(max_length=50)  # Swiggy, Zomato, etc.
    platform_order_id = models.CharField(max_length=100, blank=True, default='')
    items_json = models.JSONField(default=dict)


class ServiceDetail(models.Model):
    """Service request details."""
    order = models.OneToOneField(OrderCore, on_delete=models.CASCADE, related_name='service_detail')
    service_type = models.CharField(max_length=50)
    description = models.TextField(blank=True, default='')
    scheduled_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
```

### Step 2: Generate Schema Migrations

```bash
python manage.py makemigrations domains.orders
python manage.py migrate domains.orders
```

**Verify:**
- All 7 tables created
- All indexes built
- All CHECK constraints pass
- All FK constraints in place

### Step 3: Implement Data Migration Command

Create `domains/orders/management/commands/migrate_orders.py`:

```python
from django.core.management.base import BaseCommand
from domains.orders.models import OrderCore, EstimateDetail, InStoreDetail
from domains.orders.models import TPOrderDetail, ServiceDetail
from users.models import Identity
from backend.mongo import get_database


class Command(BaseCommand):
    help = 'Migrate orders from MongoDB to PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument('--validate', action='store_true', help='Run validation checks')
        parser.add_argument('--source', type=str, help='Mongo URI (optional)')

    def handle(self, *args, **options):
        if options['validate']:
            self.validate_migration()
            return

        self.stdout.write('Starting M4 orders migration...')
        
        db = get_database(options.get('source'))
        
        # Migrate each collection
        collections = [
            ('estimates', 'estimate'),
            ('kgorders', 'in_store'),
            ('tporders', 'tp'),
            ('serviceRequest', 'service'),
        ]
        
        total_migrated = 0
        for coll_name, order_type in collections:
            count = self.migrate_collection(db, coll_name, order_type)
            total_migrated += count
            self.stdout.write(f'  Migrated {coll_name}: {count} records')
        
        self.stdout.write(f'Total migrated: {total_migrated} records')
        self.stdout.write(self.style.SUCCESS('M4 migration complete'))

    def migrate_collection(self, db, coll_name: str, order_type: str) -> int:
        """Migrate a single Mongo collection."""
        coll = db[coll_name]
        count = 0
        
        for mongo_doc in coll.find({}):
            # Normalize tenant fields
            bg_code = mongo_doc.get('bg_code') or mongo_doc.get('bgcode', '')
            div_code = mongo_doc.get('div_code') or mongo_doc.get('division', '')
            branch_code = mongo_doc.get('branch_code') or mongo_doc.get('branch', '')
            
            # Normalize phone to identity_id
            phone = mongo_doc.get('user', {}).get('phone', '') if isinstance(mongo_doc.get('user'), dict) else mongo_doc.get('user_phone', '')
            identity_id = self.resolve_identity_id(phone)
            
            # Create order
            order_id = mongo_doc.get('orderid') or mongo_doc.get('_id')
            order, created = OrderCore.objects.get_or_create(
                order_id=str(order_id),
                defaults={
                    'order_type': order_type,
                    'identity_id': identity_id,
                    'customer_name': mongo_doc.get('user', {}).get('name', '') if isinstance(mongo_doc.get('user'), dict) else '',
                    'customer_phone': phone,
                    'bg_code': bg_code,
                    'div_code': div_code,
                    'branch_code': branch_code,
                    'status': mongo_doc.get('status', 'pending'),
                    'total_amount': float(mongo_doc.get('total_amount', 0)),
                }
            )
            
            # Create type-specific detail
            if order_type == 'estimate':
                EstimateDetail.objects.update_or_create(
                    order=order,
                    defaults={
                        'estimate_number': mongo_doc.get('estimate_number', ''),
                        'valid_until': mongo_doc.get('valid_until', None),
                        'items_json': mongo_doc.get('items', {}),
                    }
                )
            elif order_type == 'in_store':
                InStoreDetail.objects.update_or_create(
                    order=order,
                    defaults={
                        'table_number': mongo_doc.get('table_number', ''),
                        'dine_in': mongo_doc.get('dine_in', False),
                        'items_json': mongo_doc.get('items', {}),
                    }
                )
            elif order_type == 'tp':
                TPOrderDetail.objects.update_or_create(
                    order=order,
                    defaults={
                        'platform': mongo_doc.get('platform', ''),
                        'platform_order_id': mongo_doc.get('platform_order_id', ''),
                        'items_json': mongo_doc.get('items', {}),
                    }
                )
            elif order_type == 'service':
                ServiceDetail.objects.update_or_create(
                    order=order,
                    defaults={
                        'service_type': mongo_doc.get('service_type', ''),
                        'description': mongo_doc.get('description', ''),
                        'scheduled_date': mongo_doc.get('scheduled_date', None),
                        'completed_date': mongo_doc.get('completed_date', None),
                    }
                )
            
            count += 1
        
        return count

    def resolve_identity_id(self, phone: str) -> str:
        """Resolve phone to identity_id."""
        if not phone:
            return ''
        
        # Normalize phone
        from users.utils import normalize_phone
        e164 = normalize_phone(phone)
        if not e164:
            return ''
        
        # Lookup identity
        try:
            identity = Identity.objects.get(phone=e164)
            return identity.identity_id
        except Identity.DoesNotExist:
            # Create walk-in identity for unregistered users
            from django.utils import timezone
            identity_id = f"ID{Identity.objects.count() + 1:06d}"
            identity = Identity.objects.create(
                identity_id=identity_id,
                phone=e164,
                name='Walk-in Customer',
                bg_code='KURO0001',
                status='active',
                phone_verified=False,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return identity_id
```

### Step 4: Run Migration

```bash
python manage.py migrate_orders --source=mongodb://<host>:27017
```

**Verify:**
- Row count reconciliation per source
- 0 orphaned order rows
- 0 invalid tenant codes
- 0 orders without customer_id
- Financial data loss check passes
- All indexes built
- All CHECK constraints pass

### Step 5: Update Viewsets

Update `domains/orders/viewsets.py` to use PostgreSQL models instead of MongoDB queries:

```python
from domains.orders.models import OrderCore, EstimateDetail, InStoreDetail
from domains.orders.models import TPOrderDetail, ServiceDetail
from rest_framework import viewsets


class OrderViewSet(viewsets.ModelViewSet):
    """Order viewset — uses PostgreSQL."""
    queryset = OrderCore.objects.all()
    serializer_class = OrderSerializer
    
    def get_queryset(self):
        # Tenant-scoped queries
        bg_code = self.request.user.bg_code
        return OrderCore.objects.filter(bg_code=bg_code)


class EstimateViewSet(viewsets.ModelViewSet):
    queryset = OrderCore.objects.filter(order_type='estimate')
    serializer_class = EstimateSerializer


class InStoreViewSet(viewsets.ModelViewSet):
    queryset = OrderCore.objects.filter(order_type='in_store')
    serializer_class = InStoreSerializer


class TPOrderViewSet(viewsets.ModelViewSet):
    queryset = OrderCore.objects.filter(order_type='tp')
    serializer_class = TPOrderSerializer


class ServiceRequestViewSet(viewsets.ModelViewSet):
    queryset = OrderCore.objects.filter(order_type='service')
    serializer_class = ServiceRequestSerializer
```

### Step 6: Wire Routes

Ensure order routes are configured in `backend/urls.py`:

```python
# backend/urls.py
from domains.orders import urls as orders_urls

urlpatterns = [
    # ... existing routes
    path('api/v1/orders/', include(orders_urls)),
]
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/orders/models.py` | PostgreSQL models (7 tables) |
| Create | `domains/orders/migrations/` | Schema migrations |
| Create | `domains/orders/management/commands/migrate_orders.py` | Data migration command |
| Modify | `domains/orders/viewsets.py` | Use PostgreSQL models |
| Modify | `domains/orders/urls.py` | Wire routes |
| Modify | `backend/urls.py` | Include orders URLs |
| Create | `tests/test_orders_postgresql.py` | Verify migration |
| Create | `tests/test_orders_financial.py` | Verify financial data integrity |

## Phase-Specific Tests

Create `tests/test_orders_postgresql.py`:

1. **Test row count reconciliation:**
   ```python
   def test_row_count_reconciliation():
       # Verify counts match (exact numbers depend on source data)
       assert OrderCore.objects.filter(order_type='estimate').count() > 0
       assert OrderCore.objects.filter(order_type='in_store').count() > 0
       assert OrderCore.objects.filter(order_type='tp').count() > 0
       assert OrderCore.objects.filter(order_type='service').count() > 0
   ```

2. **Test FK integrity (identity_id):**
   ```python
   def test_fk_integrity_identity():
       orphaned = OrderCore.objects.filter(identity_id='').count()
       assert orphaned == 0, f"{orphaned} orders without identity_id"
   ```

3. **Test tenant codes:**
   ```python
   def test_valid_tenant_codes():
       invalid = OrderCore.objects.exclude(bg_code__regex='^[A-Z]{4}\\d{4}$')
       assert invalid.count() == 0
   ```

4. **Test financial data loss:**
   ```python
   def test_financial_data_loss():
       # Compare total_amount sum with legacy Mongo
       pg_total = OrderCore.objects.aggregate(total=Sum('total_amount'))['total']
       mongo_total = get_database()['kgorders'].aggregate(
           total={'$sum': '$total_amount'}
       )['total']
       assert abs(pg_total - mongo_total) < 0.01, "Financial data loss detected"
   ```

5. **Test order types:**
   ```python
   def test_order_types():
       types = OrderCore.objects.values_list('order_type', flat=True).distinct()
       assert 'estimate' in types
       assert 'in_store' in types
       assert 'tp' in types
       assert 'service' in types
   ```

6. **Test detail tables populated:**
   ```python
   def test_detail_tables_populated():
       assert EstimateDetail.objects.count() > 0
       assert InStoreDetail.objects.count() > 0
       assert TPOrderDetail.objects.count() > 0
       assert ServiceDetail.objects.count() > 0
   ```

7. **Test viewsets functional:**
   ```python
   def test_viewsets_return_data():
       from rest_framework.test import APIClient
       client = APIClient()
       response = client.get('/api/v1/orders/')
       assert response.status_code == 200
   ```

## Completion Gate

- [ ] All 4 Mongo collections migrated (estimates, kgorders, tporders, serviceRequest)
- [ ] 7 PostgreSQL tables created (orders_core + 6 detail tables)
- [ ] Row count reconciliation per source (15,925 total)
- [ ] FK integrity: 0 orphaned order rows
- [ ] Tenant codes: 0 invalid bg_code/div_code
- [ ] Customer linkage: 0 orders without customer_id
- [ ] Financial data loss check: total_amount sum matches legacy
- [ ] Index creation: all indexes built
- [ ] Constraint validation: all CHECK constraints pass
- [ ] Order viewsets functional
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Post-Migration Verification (Gate)

```bash
python manage.py migrate_orders --validate
```

**Expected output:**
```
✅ Row count reconciliation:
   estimates: X source → X output (0 dropped)
   kgorders: X source → X output (0 dropped)
   tporders: X source → X output (0 dropped)
   serviceRequest: 1625 source → 1625 output (0 dropped)

✅ FK integrity: 0 orphaned order rows
✅ Tenant codes: 0 invalid bg_code/div_code
✅ Customer linkage: 0 orders without customer_id
✅ Financial data loss check: total_amount sum matches legacy
✅ Index creation: all indexes built
✅ Constraint validation: all CHECK constraints pass
```

## Notes for Next Phase

- Phase 4B (E-commerce products) can run in parallel — no dependency on this phase.
- Phase 4C (Legacy cleanup) can run in parallel — drops old Mongo collections after verification.
- Phase 5 (Production wiring) depends on this phase — must verify order endpoints respond correctly.
- Legacy MongoDB collections remain untouched (eventual cleanup, not blocking).
- The `orders.user.phone` field in Mongo is normalized to `identity_id` in PostgreSQL.

## Consistency Rules

**This phase defers to:**
- Migration ordering & data transformation: `migration_spec.md` §5 (M4: Orders to PostgreSQL)
- PostgreSQL schema: `postgresql_schema.md` (orders_core + 6 detail tables)
- Canonical naming: `CANONICAL_NAMING.md` (`identity_id`, `bg_code`, `div_code`, `branch_code`)

**This phase does NOT redefine:**
- Response shapes (Phase 3A handles response envelope)
- Mongo field names (Phase 1B handles field rename)
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._
