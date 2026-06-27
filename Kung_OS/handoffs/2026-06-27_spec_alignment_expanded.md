# Spec Alignment Fixes — Expanded Handoff (3 Phases)

**Date:** 2026-06-27
**Project:** `kteam-dj-chief`
**Status:** Ready for execution
**Total Estimated Effort:** 13-19 days

---

## Overview

This expanded handoff resolves all inconsistencies identified in the spec review. It's organized into 3 phases:

- **Phase 1 (3-5 days):** Core spec alignment fixes (original handoff)
- **Phase 2 (5-7 days):** Foundational infrastructure (outbox, tenant isolation, identity migration)
- **Phase 3 (5-7 days):** Domain-specific features (EShop orders, walk-in management, protocol enforcement)

---

## Tenant Context Rule (Applies to All Phases)

**Tenant context is set at the middleware layer, not per-request.** `TenantContextMiddleware` populates `request.bg_code`, `request.div_codes`, `request.branch_codes`, and `request.scope` from the JWT on every authenticated request. Webhook endpoints (HMAC-authenticated) have no `request.user`; they resolve tenant context from the domain entity being verified.

**Rule:** Derive `bg_code` from one of:
1. `request.bg_code` — set by `TenantContextMiddleware` on authenticated requests
2. The resolved domain entity (e.g. `session.bg_code`, `order.bg_code`) — for webhooks and cross-store operations
3. **Never** `request.user.bg_code` — the user object may not exist (HMAC endpoints, walk-ins, service accounts)

---

## Phase 1: Core Spec Alignment (3-5 days)

*Original handoff tasks — no changes required.*

### Task 1: Fix `division` → `div_code` in Serializers (30 min)
- **Priority:** CRITICAL (Blocks OpenAPI)
- **Effort:** 30 minutes
- **Dependencies:** None

### Task 2: Implement EShop Cart/Wishlist/Addresses (1 day)
- **Priority:** CRITICAL (Blocks E-Commerce)
- **Effort:** 1 day
- **Dependencies:** Task 1

### Task 3: Migrate `teams/kurostaff/` Imports (1-2 days)
- **Priority:** HIGH (Spec violation)
- **Effort:** 1-2 days
- **Dependencies:** None

### Task 4: Remove 34 Dead Functions (1 day)
- **Priority:** HIGH (Maintenance burden)
- **Effort:** 1 day
- **Dependencies:** Task 3

### Task 5: Document Domain Database Usage (2-3 hours)
- **Priority:** MEDIUM (Documentation)
- **Effort:** 2-3 hours
- **Dependencies:** None

**Phase 1 Completion Criteria:**
- [ ] OpenAPI schema generates without errors
- [ ] EShop cart/wishlist/addresses endpoints work
- [ ] No `teams.kurostaff.views` imports remain
- [ ] 23 dead functions removed
- [ ] Domain database usage documented

---

## Phase 2: Foundational Infrastructure (5-7 days)

### Task 6: Adopt and Complete Existing Outbox Primitive (1 day)

**Priority:** CRITICAL (Transaction integrity)
**Effort:** 1 day
**Dependencies:** Phase 1 complete

#### Context

`plat/outbox/` is a **Constitution-level platform primitive** (`architecture/platform_primitives.md`). It is already implemented with:

| File | Purpose |
|------|---------|
| `models.py` | Outbox entry model (action, payload, status, retry_count) |
| `service.py` | Outbox service API (create, process, retry) |
| `worker.py` | Background worker that processes pending outbox entries |

The PostgreSQL table `platform_outbox_events` (11 cols, PK `event_id` uuid) is **LIVE and stable** (`postgresql_schema.md` §8). This task extends the primitive with domain event handlers — it does **not** create a parallel implementation.

**Do not:** Create new files in `plat/outbox/` that duplicate `models.py`, `service.py`, or `worker.py`. Do not create a table named `outbox_events`.

#### Implementation Steps

**Step 1: Register Domain Outbox Event Handlers**

Extend `plat/outbox/worker.py` to dispatch the three domain event types. Add handlers in their respective domain packages:

**File:** `domains/cafe_fnb/outbox_handlers.py` (NEW)

```python
"""Outbox event handler for F&B session billing."""
from plat.tenant.collection import TenantCollection


def handle_fnb_session_billing(event: dict):
    """Write final session charges to MongoDB via TenantCollection."""
    session_id = event['session_id']
    total_charges = event['total_charges']
    bg_code = event['bg_code']
    
    collection = TenantCollection.get_collection('caf_platform_sessions')
    collection.update_one(
        {'_id': session_id, 'bg_code': bg_code},
        {'$set': {
            'total_charges': total_charges,
            'status': 'ended',
        }}
    )
```

**File:** `domains/eshop/outbox_handlers.py` (NEW)

```python
"""Outbox event handlers for EShop order lifecycle."""
from users.models import Identity, Customer


def handle_order_placed(event: dict):
    """Update customer order metrics after order creation."""
    customer_id = event['customer_id']
    total_amount = event['total_amount']
    
    try:
        identity = Identity.objects.get(identity_id=customer_id)
        if hasattr(identity, 'customer_profile'):
            customer = identity.customer_profile
            customer.order_count += 1
            customer.total_spent = (customer.total_spent or 0) + total_amount
            customer.save(
                update_fields=['order_count', 'total_spent']
            )
    except Identity.DoesNotExist:
        pass  # Walk-in order, no customer extension yet


def handle_order_payment_verified(event: dict):
    """Trigger order conversion pipeline after payment verification."""
    order_id = event['order_id']
    # Integrate with existing orderconversion pipeline
    # See ecommerce_spec.md for pipeline details
    pass
```

**Step 2: Wire Outbox Publishing in Domain Viewsets**

Replace direct MongoDB writes with `OutboxService.publish_on_commit()`. Derive tenant context from the **resolved domain entity** (not `request.user.bg_code`), because not all endpoints are user-authenticated.

**File:** `domains/cafe_arcade/views.py` (session_end)

```python
from plat.outbox.service import OutboxService

def end_session(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    
    with transaction.atomic():
        session.status = 'ended'
        session.end_time = timezone.now()
        session.total_charges = calculate_final_charges(session)
        session.save()
        
        # Queue F&B write in outbox (not direct Mongo call)
        # Tenant context derived from the session entity itself,
        # which is already scoped by RLS/TenantCollection.
        OutboxService.publish_on_commit(
            event_type='fnb.session_billing',
            payload={
                'session_id': session.id,
                'last_order_id': session.last_order_id,
                'total_charges': session.total_charges,
                'bg_code': session.bg_code,
            },
        )
```

**File:** `domains/eshop/viewsets.py` (checkout)

```python
from plat.outbox.service import OutboxService

class CheckoutViewSet(viewsets.ViewSet):
    def create(self, request):
        # Create order in PG (RLS enforces tenant scope)
        order = OrderCore.objects.create(
            orderid=generate_orderid(),
            order_type='eshop',
            status='pending',
            total_amount=request.data['total_amount'],
            customer=request.user.identity_id,
            bg_code=request.bg_code,        # From TenantContextMiddleware
            div_code=request.active_div_code,
            billadd=request.data['billadd'],
            products=request.data['products'],
            channel='online',
        )
        
        # Create eshop_detail
        EshopDetail.objects.create(
            order=order,
            payment_option=request.data.get('payment_option', 'cashfree'),
        )
        
        # Queue payment verification in outbox
        # Tenant context from the order entity just created
        OutboxService.publish_on_commit(
            event_type='order.placed',
            payload={
                'order_id': order.id,
                'orderid': order.orderid,
                'customer_id': order.customer_id,
                'total_amount': order.total_amount,
                'bg_code': order.bg_code,
            },
        )
        
        return Response({'order_id': order.id}, status=201)
```

**File:** `domains/eshop/payment/views.py` (webhook)

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
import hmac
import hashlib
import base64
from plat.outbox.service import OutboxService


def verify_cashfree_signature(payload_string, signature, secret_key):
    """Verify Cashfree webhook signature."""
    computed = base64.b64encode(
        hmac.new(
            secret_key.encode('utf-8'),
            payload_string.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    return hmac.compare_digest(computed, signature)


class CashfreeWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # Verify HMAC signature
        signature = request.headers.get('X-CF-SIGNATURE')
        if not verify_cashfree_signature(
            request.body.decode('utf-8'),
            signature,
            settings.CASHFREE_SECRET_KEY
        ):
            return Response({'error': 'Invalid signature'}, status=400)
        
        # Resolve tenant context from the order record, NOT request.user
        # (this endpoint is HMAC-authenticated, not JWT-authenticated)
        order = OrderCore.objects.get(orderid=request.data['order_id'])
        
        # Queue payment verification in outbox
        OutboxService.publish_on_commit(
            event_type='order.payment_verified',
            payload={
                'order_id': order.id,
                'orderid': order.orderid,
                'payment_reference': request.data['payment_id'],
                'bg_code': order.bg_code,
            },
        )
        
        return Response({'status': 'received'}, status=202)
```

**Tenant context rule:** Derive `bg_code` from one of:
1. `request.bg_code` — set by `TenantContextMiddleware` on authenticated requests
2. The resolved domain entity (e.g. `session.bg_code`, `order.bg_code`) — for webhooks and cross-store operations
3. Never `request.user.bg_code` — the user object may not exist (HMAC endpoints, walk-ins, service accounts)

#### Verification

```bash
# 1. Verify existing outbox primitive is intact
python manage.py shell -c "
from plat.outbox.models import OutboxEvent
from plat.outbox.service import OutboxService
from plat.outbox.worker import OutboxWorker
print('Outbox primitive: OK')
"

# 2. Verify platform_outbox_events table exists
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'platform_outbox_events'\")
    cols = [row[0] for row in cursor.fetchall()]
    print(f'platform_outbox_events columns: {cols}')
"

# 3. Test outbox publishing via domain viewset
# (create an order via checkout endpoint, verify outbox event created)

# 4. Test outbox processing
python manage.py process_outbox

# 5. Verify no duplicate outbox files
find plat/outbox/ -type f | sort
# Expected: models.py, service.py, worker.py, __init__.py
```

---

### Task 7: Prove Tenant Isolation by Behavior (1 day)

**Priority:** CRITICAL (Security)
**Effort:** 1 day
**Dependencies:** Phase 1 complete

#### Context

Tenant isolation is enforced at two levels:
- **PostgreSQL:** Row-Level Security (RLS) via session variables set by `TenantContextMiddleware`. The middleware sets `app.current_bg_code`, `app.current_division`, `app.current_branch`. Policies filter silently at the DB level.
- **MongoDB:** `TenantCollection` wrapper injects `bg_code` into every query. Raw PyMongo calls bypass this layer.

**SQL-substring checks are not proof of safety.** With RLS, the SQL text may not contain `bg_code` at all, yet isolation is still enforced. Real proof requires behavioral tests that set one tenant's session context and query another tenant's data.

#### Implementation Steps

**Step 1: Create Behavioral Tenant Isolation Test Suite (`tests/test_tenant_isolation.py`)**

```python
from django.test import TestCase, override_settings
from django.db import connection
from users.models import Identity, CustomUser
from tenant.models import BusinessGroup, Division
from orders.models import OrderCore
from plat.tenant.collection import TenantCollection
from plat.tenant.rls import enable_rls, disable_rls


class PostgresTenantIsolationTests(TestCase):
    """Prove PostgreSQL tenant isolation via RLS behavior."""
    
    def setUp(self):
        # Create two business groups
        self.bg1 = BusinessGroup.objects.create(bg_code='BGTEST01', name='Test BG 1')
        self.bg2 = BusinessGroup.objects.create(bg_code='BGTEST02', name='Test BG 2')
        
        # Create divisions
        self.div1 = Division.objects.create(
            div_code='BGTEST01_001', bg_code='BGTEST01', name='Test Division 1'
        )
        self.div2 = Division.objects.create(
            div_code='BGTEST02_001', bg_code='BGTEST02', name='Test Division 2'
        )
    
    @override_settings(
        DATABASES={'default': {...}}  # Use test database with RLS policies
    )
    def test_cross_tenant_data_invisible_under_rls(self):
        """Prove: querying with BGTEST01's session vars returns zero BGTEST02 rows."""
        # Create data in both tenants
        order_bg1 = OrderCore.objects.create(
            orderid='ISOTEST001',
            order_type='eshop',
            status='pending',
            total_amount=100,
            bg_code='BGTEST01',
            div_code='BGTEST01_001',
        )
        order_bg2 = OrderCore.objects.create(
            orderid='ISOTEST002',
            order_type='eshop',
            status='pending',
            total_amount=200,
            bg_code='BGTEST02',
            div_code='BGTEST02_001',
        )
        
        # Set RLS session variables to BGTEST01
        with connection.cursor() as cursor:
            cursor.execute("SET app.current_bg_code = 'BGTEST01'")
            cursor.execute("SET app.current_division = 'BGTEST01_001'")
        
        # Query all orders — RLS should filter to BGTEST01 only
        results = list(OrderCore.objects.all())
        result_ids = {o.id for o in results}
        
        self.assertIn(order_bg1.id, result_ids)
        self.assertNotIn(order_bg2.id, result_ids)
    
    @override_settings(
        DATABASES={'default': {...}}
    )
    def test_division_scope_filters_correctly(self):
        """Prove: division-scoped user sees only their division's data."""
        order_div1 = OrderCore.objects.create(
            orderid='ISOTEST003',
            order_type='eshop',
            status='pending',
            total_amount=100,
            bg_code='BGTEST01',
            div_code='BGTEST01_001',
        )
        order_div2 = OrderCore.objects.create(
            orderid='ISOTEST004',
            order_type='eshop',
            status='pending',
            total_amount=200,
            bg_code='BGTEST01',
            div_code='BGTEST01_002',
        )
        
        # Set RLS to division scope (BGTEST01, only div1)
        with connection.cursor() as cursor:
            cursor.execute("SET app.current_bg_code = 'BGTEST01'")
            cursor.execute("SET app.current_division = 'BGTEST01_001'")
        
        results = list(OrderCore.objects.all())
        result_ids = {o.id for o in results}
        
        self.assertIn(order_div1.id, result_ids)
        self.assertNotIn(order_div2.id, result_ids)
    
    def test_rls_policies_exist(self):
        """Verify RLS policies are enabled on tenant-scoped tables."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT tablename, policyname 
                FROM pg_policies 
                WHERE policyname LIKE 'tenant_isolation%%'
                ORDER BY tablename
            """)
            policies = cursor.fetchall()
        
        # At minimum: orders_core, users_identity, cafe sessions
        policy_tables = {p[0] for p in policies}
        self.assertIn('orders_core', policy_tables)
        self.assertIn('users_identity', policy_tables)


class MongoTenantIsolationTests(TestCase):
    """Prove MongoDB tenant isolation via TenantCollection behavior."""
    
    def test_tenant_collection_injects_bg_code(self):
        """Prove: TenantCollection auto-injects bg_code into query filters."""
        from unittest.mock import patch
        
        with patch('plat.tenant.collection.get_mongo_client') as mock_client:
            collection = TenantCollection.get_collection('test_collection')
            # Verify bg_code is in the collection's filter
            self.assertIn('bg_code', collection._filters)
    
    def test_tenant_collection_raises_without_context(self):
        """Prove: TenantCollection raises TenantContextMissing without context."""
        from plat.tenant.exceptions import TenantContextMissing
        
        with self.assertRaises(TenantContextMissing):
            TenantCollection.get_collection('test_collection', bg_code=None)
    
    def test_no_raw_pymongo_in_domain_code(self):
        """Verify no raw PyMongo calls bypass TenantCollection in domain code."""
        import subprocess
        result = subprocess.run(
            ['grep', '-rn', 'MongoClient(', '--include=*.py', 
             'domains/', 'eshop/', 'plat/'],
            capture_output=True, text=True
        )
        # Should only find imports or management commands
        lines = [l for l in result.stdout.split('\n') 
                 if l and 'import' not in l 
                 and 'management/commands' not in l
                 and '__pycache__' not in l]
        self.assertEqual(len(lines), 0, f"Raw PyMongo calls found: {lines}")


class TenantCodeHardeningTests(TestCase):
    """Verify no hardcoded tenant codes leak into production code."""
    
    def test_no_hardcoded_kuro_code(self):
        """Verify no hardcoded 'KURO0001' in production code."""
        import subprocess
        result = subprocess.run(
            ['grep', '-rn', "'KURO0001'", '--include=*.py',
             'domains/', 'eshop/', 'users/', 'plat/'],
            capture_output=True, text=True
        )
        # Should only find in tests or migrations
        lines = [l for l in result.stdout.split('\n') 
                 if l and 'test_' not in l 
                 and 'migration' not in l
                 and '__pycache__' not in l]
        self.assertEqual(len(lines), 0, f"Hardcoded tenant codes found: {lines}")
```

**Step 2: Add Tenant Isolation to CI/CD**

**File:** `.github/workflows/ci.yml` (or equivalent)

```yaml
- name: Run tenant isolation tests
  run: |
    python manage.py test tests.test_tenant_isolation -v 2
```

**Step 3: Centralize Scope Resolution**

Create a scope resolver mixin that expands query filters based on the user's active scope (`full`, `division`, `branch`). This ensures views don't stop at BG-only filtering.

**File:** `plat/tenant/scoping.py` (NEW)

```python
"""Centralized tenant scope resolution for query filtering."""
from django.db.models import Q


class TenantScopingMixin:
    """Mixin that applies tenant scope to querysets."""
    
    def get_tenant_scope(self, request):
        """Extract scope from request (set by TenantContextMiddleware)."""
        return {
            'bg_code': request.bg_code,
            'div_codes': getattr(request, 'div_codes', [request.active_div_code]),
            'branch_codes': getattr(request, 'branch_codes', []),
            'scope': getattr(request, 'scope', 'full'),
        }
    
    def apply_tenant_scope(self, queryset, request):
        """Apply tenant scope filter to queryset based on active scope."""
        scope = self.get_tenant_scope(request)
        bg_code = scope['bg_code']
        
        if scope['scope'] == 'full':
            return queryset.filter(bg_code=bg_code)
        
        elif scope['scope'] == 'division':
            div_codes = scope['div_codes']
            if len(div_codes) == 1:
                return queryset.filter(bg_code=bg_code, div_code=div_codes[0])
            return queryset.filter(bg_code=bg_code, div_code__in=div_codes)
        
        elif scope['scope'] == 'branch':
            div_code = scope['div_codes'][0] if scope['div_codes'] else None
            branch_codes = scope['branch_codes']
            if div_code and branch_codes:
                return queryset.filter(
                    bg_code=bg_code,
                    div_code=div_code,
                    branch_code__in=branch_codes,
                )
            return queryset.filter(bg_code=bg_code, div_code=div_code)
        
        return queryset.filter(bg_code=bg_code)
```

#### Verification

```bash
# 1. Run behavioral tenant isolation tests
python manage.py test tests.test_tenant_isolation -v 2

# 2. Verify RLS policies are enabled
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"SELECT tablename, policyname FROM pg_policies WHERE policyname LIKE 'tenant_isolation%%'\")
    for row in cursor.fetchall():
        print(f'{row[0]}: {row[1]}')
"

# 3. Verify no raw PyMongo calls in domain code
grep -rn "MongoClient(" --include="*.py" domains/ eshop/ plat/ | grep -v import | grep -v management/commands | grep -v __pycache__

# 4. Verify no hardcoded tenant codes
grep -rn "'KURO0001'" --include="*.py" domains/ eshop/ users/ plat/ | grep -v test_ | grep -v migration | grep -v __pycache__

# 5. Run full test suite
python manage.py test -v 2
```

---

### Task 8: Implement Phone Normalization (0.5 days)

**Priority:** HIGH (Identity lookup)
**Effort:** 0.5 days
**Dependencies:** Phase 1 complete

#### Implementation Steps

**Step 1: Create Phone Normalization Utility (`users/utils.py`)**

```python
"""Phone normalization utilities."""
import re
import phonenumbers
from phonenumbers import PhoneNumberFormat

def normalize_phone(raw_phone: str, region: str = 'IN') -> str:
    """Normalize phone to E.164 format."""
    cleaned = re.sub(r'[^\d+]', '', raw_phone)
    parsed = phonenumbers.parse(cleaned, region)
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

def validate_phone(phone: str, region: str = 'IN') -> bool:
    """Validate phone number."""
    try:
        parsed = phonenumbers.parse(phone, region)
        return phonenumbers.is_valid_number(parsed)
    except phonenumbers.NumberParseException:
        return False

# Test cases
assert normalize_phone("9876543210") == "+919876543210"
assert normalize_phone("+919876543210") == "+919876543210"
assert normalize_phone("02223456789") == "+912223456789"
assert normalize_phone("00919876543210") == "+919876543210"
```

**Step 2: Update Identity Creation to Use Normalization**

**File:** `users/api/viewsets.py` (register)

```python
from users.utils import normalize_phone, validate_phone

class RegisterViewSet(viewsets.ViewSet):
    def create(self, request):
        phone = normalize_phone(request.data['phone'])
        
        if not validate_phone(phone):
            return Response({'error': 'Invalid phone number'}, status=400)
        
        # Create identity with normalized phone
        # Tenant context from middleware (request.bg_code, request.active_div_code)
        identity = Identity.objects.create(
            phone=phone,
            name=request.data['name'],
            bg_code=request.bg_code,
            div_code=request.active_div_code,
        )
        
        return Response({'identity_id': identity.identity_id}, status=201)
```

**Step 3: Add Phone Normalization Tests**

**File:** `tests/test_phone_normalization.py`

```python
from django.test import TestCase
from users.utils import normalize_phone, validate_phone

class PhoneNormalizationTests(TestCase):
    def test_normalize_indian_mobile(self):
        self.assertEqual(normalize_phone("9876543210"), "+919876543210")
    
    def test_normalize_indian_landline(self):
        self.assertEqual(normalize_phone("02223456789"), "+912223456789")
    
    def test_normalize_already_e164(self):
        self.assertEqual(normalize_phone("+919876543210"), "+919876543210")
    
    def test_validate_valid_phone(self):
        self.assertTrue(validate_phone("+919876543210"))
    
    def test_validate_invalid_phone(self):
        self.assertFalse(validate_phone("123"))
```

#### Verification

```bash
# 1. Run phone normalization tests
python manage.py test tests.test_phone_normalization -v 2

# 2. Test phone normalization in shell
python manage.py shell -c "
from users.utils import normalize_phone
print(normalize_phone('9876543210'))  # Should print +919876543210
"
```

---

### Task 9: Identity Migration (2-3 days)

**Priority:** HIGH (Foundational)
**Effort:** 2-3 days
**Dependencies:** Task 6, 7, 8 complete

#### Authority

This task is governed by `migration_spec.md` §2 (M1: Identity Consolidation). The migration spec defines the full dedup flow, conflict resolution, cross-reference merges, and 13 validation gates. The management commands below are **illustrative examples** of the per-source migration pattern — they are not the complete migration design.

**Critical constraints from the spec:**
- Identity lookup key is **composite** `(bg_code, phone)` — NOT phone alone
- Phone uniqueness is tenant-scoped: same number in different tenants is valid
- **No hardcoded tenant fallbacks** — tenant values must come from the source records
- Dedup requires name fuzzy matching (85% threshold) and conflict flagging
- Migration must pass all 13 validation gates before deployment

#### Implementation Steps

**Step 1: Create Unified Migration Command (`users/management/commands/migrate_identity.py`)**

This single command handles all sources per `migration_spec.md` §2.1. It is a template — implement per-source migration logic following the pattern below.

```python
"""
Unified identity migration command.

Authority: migration_spec.md §2 (M1: Identity Consolidation)
This command is a template. Implement per-source migration logic
following the pattern below. The full design includes:
- Dedup by normalized phone with name fuzzy matching (85% threshold)
- Cross-reference merges (serviceRequest↔reb_users, players↔reb_users, etc.)
- 13 validation gates (§2.3 of migration_spec.md)
- Rollback strategy (§2.5 of migration_spec.md)
"""
from django.core.management.base import BaseCommand, CommandError
from users.utils import normalize_phone


class Command(BaseCommand):
    help = 'Migrate identities from MongoDB sources to users_identity + extensions'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--source', type=str, required=True,
            choices=['reb_users', 'players', 'vendors', 'teams', 
                     'service_requests', 'order_phones', 'employee_attendance'],
            help='Source collection to migrate'
        )
        parser.add_argument(
            '--validate', action='store_true',
            help='Run validation gates after migration'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview migration without writing'
        )
    
    def handle(self, *args, **options):
        source = options['source']
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(f'Migrating from {source}...')
        
        # Get source collection via TenantCollection (per-tenant iteration)
        from plat.tenant.collection import TenantCollection
        source_collection = TenantCollection.get_collection(source)
        
        # Phase 1: Extract and normalize
        records = []
        for doc in source_collection.find({}, {'_id': 0}):
            phone_raw = doc.get('phone') or doc.get('mobile')
            if not phone_raw:
                self.stdout.write(self.style.WARNING(
                    f'Skipping record without phone: {doc.get("name", "unknown")}'
                ))
                continue
            
            phone = normalize_phone(phone_raw)
            
            # Tenant context from the source record itself — NEVER hardcode
            bg_code = doc.get('bg_code')
            div_code = doc.get('div_code')
            
            if not bg_code:
                self.stdout.write(self.style.ERROR(
                    f'Skipping record without bg_code: {doc.get("name", "unknown")}'
                ))
                continue
            
            records.append({
                'phone': phone,
                'bg_code': bg_code,
                'div_code': div_code,
                'name': doc.get('name', ''),
                'raw_doc': doc,
            })
        
        # Phase 2: Lookup or create identity using COMPOSITE key (bg_code, phone)
        from users.models import Identity
        
        for rec in records:
            if dry_run:
                self.stdout.write(f'  DRY RUN: {rec["phone"]} @ {rec["bg_code"]}')
                continue
            
            # COMPOSITE lookup: (bg_code, phone) — NOT phone alone
            # This prevents cross-tenant identity collapse
            identity, created = Identity.objects.get_or_create(
                bg_code=rec['bg_code'],
                phone=rec['phone'],
                defaults={
                    'name': rec['name'],
                    'div_code': rec['div_code'],
                }
            )
            
            if created:
                self.stdout.write(f'  Created: {identity.identity_id} ({rec["phone"]})')
            else:
                # Update name if empty (first creator wins for other fields)
                if not identity.name or identity.name == '':
                    identity.name = rec['name']
                    identity.save(update_fields=['name'])
        
        # Phase 3: Create extension records (per-source)
        if source == 'reb_users':
            self._migrate_customer_extensions(records, dry_run)
        elif source == 'players':
            self._migrate_player_extensions(records, dry_run)
        elif source in ('vendors', 'teams'):
            self._migrate_org_extensions(records, source, dry_run)
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'{source} migration complete'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{source} dry run complete'))
    
    def _migrate_customer_extensions(self, records, dry_run):
        """Create users_customer extensions for migrated identities."""
        from users.models import Identity, Customer
        
        for rec in records:
            if dry_run:
                continue
            try:
                identity = Identity.objects.get(
                    bg_code=rec['bg_code'], phone=rec['phone']
                )
                Customer.objects.update_or_create(
                    identity=identity,
                    defaults={
                        'registered': rec['raw_doc'].get('registered', False),
                        'order_count': rec['raw_doc'].get('order_count', 0),
                        'total_spent': rec['raw_doc'].get('total_spent', 0),
                    }
                )
            except Identity.DoesNotExist:
                pass
    
    def _migrate_player_extensions(self, records, dry_run):
        """Create users_player extensions for migrated identities."""
        from users.models import Identity, Player
        
        for rec in records:
            if dry_run:
                continue
            try:
                identity = Identity.objects.get(
                    bg_code=rec['bg_code'], phone=rec['phone']
                )
                Player.objects.update_or_create(
                    identity=identity,
                    defaults={
                        'player_id': rec['raw_doc'].get('player_id'),
                        'team_id': rec['raw_doc'].get('team_id'),
                        'riot_id': rec['raw_doc'].get('riot_id'),
                        'rank': rec['raw_doc'].get('rank'),
                    }
                )
            except Identity.DoesNotExist:
                pass
    
    def _migrate_org_extensions(self, records, source, dry_run):
        """Create users_organization extensions for migrated orgs."""
        from users.models import Organization, VendorProfile, TeamProfile
        
        for rec in records:
            if dry_run:
                continue
            doc = rec['raw_doc']
            org_type = 'vendor' if source == 'vendors' else 'team'
            
            Organization.objects.update_or_create(
                org_id=doc.get('org_id') or doc.get('team_id'),
                defaults={
                    'org_type': org_type,
                    'name': doc.get('name', ''),
                    'bg_code': rec['bg_code'],
                    'div_code': rec['div_code'],
                }
            )
            
            if org_type == 'vendor':
                VendorProfile.objects.update_or_create(
                    org_id=doc.get('org_id'),
                    defaults={
                        'gstin': doc.get('gstin'),
                        'pan': doc.get('pan'),
                        'address': doc.get('address'),
                    }
                )
            else:
                TeamProfile.objects.update_or_create(
                    org_id=doc.get('org_id') or doc.get('team_id'),
                    defaults={
                        'team_id': doc.get('team_id'),
                        'coach': doc.get('coach'),
                    }
                )
```

**Step 2: Run Per-Source Migrations**

```bash
# Run each source independently
python manage.py migrate_identity --source=reb_users --validate
python manage.py migrate_identity --source=players --validate
python manage.py migrate_identity --source=vendors --validate
python manage.py migrate_identity --source=teams --validate
python manage.py migrate_identity --source=service_requests --validate
python manage.py migrate_identity --source=order_phones --validate
python manage.py migrate_identity --source=employee_attendance --validate
```

**Step 3: Run Validation Gates**

Per `migration_spec.md` §2.3, all 13 gates must pass:

```bash
python manage.py shell -c "
from users.models import Identity, Customer, Player, Organization

# Gate 1: Row count reconciliation
print(f'Identities: {Identity.objects.count()}')
print(f'Customers: {Customer.objects.count()}')
print(f'Players: {Player.objects.count()}')
print(f'Organizations: {Organization.objects.count()}')

# Gate 2: Phone uniqueness per tenant
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"\"\"
        SELECT bg_code, phone, COUNT(*) 
        FROM users_identity 
        GROUP BY bg_code, phone 
        HAVING COUNT(*) > 1
    \"\"\")
    dupes = cursor.fetchall()
    if dupes:
        print(f'FAIL: Duplicate (bg_code, phone) found: {dupes}')
    else:
        print('PASS: No duplicate (bg_code, phone)')

# Gate 3: FK integrity
with connection.cursor() as cursor:
    cursor.execute(\"\"\"
        SELECT COUNT(*) FROM users_customer c
        LEFT JOIN users_identity i ON c.identity_id = i.identity_id
        WHERE i.identity_id IS NULL
    \"\"\")
    orphans = cursor.fetchone()[0]
    print(f'FAIL: {orphans} orphaned customer rows' if orphans else 'PASS: No orphaned customer rows')
"
```

#### Verification

```bash
# 1. Dry run first
python manage.py migrate_identity --source=reb_users --dry-run

# 2. Run with validation
python manage.py migrate_identity --source=reb_users --validate

# 3. Verify composite uniqueness holds
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"\"\"
        SELECT bg_code, phone, COUNT(*) 
        FROM users_identity 
        GROUP BY bg_code, phone 
        HAVING COUNT(*) > 1
    \"\"\")
    print('Duplicate (bg_code, phone):', cursor.fetchall())
"

# 4. Run all validation gates from migration_spec.md §2.3
```

---

## Phase 3: Domain-Specific Features (5-7 days)

### Task 10: Implement EShop Orders and Payment (2 days)

**Priority:** CRITICAL (E-Commerce complete)
**Effort:** 2 days
**Dependencies:** Phase 2 complete

#### Implementation Steps

**Step 1: Create Order Models (`domains/eshop/models.py`)**

```python
from django.db import models
from users.models import Identity

class OrderCore(models.Model):
    """Shared order fields."""
    ORDER_TYPE_CHOICES = [
        ('eshop', 'E-Commerce'),
        ('in_store', 'In-Store'),
        ('tp', 'Third-Party'),
        ('service', 'Service'),
        ('estimate', 'Estimate'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    orderid = models.CharField(max_length=20, unique=True)
    order_type = models.CharField(max_length=10, choices=ORDER_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    customer = models.ForeignKey(Identity, on_delete=models.CASCADE, related_name='orders')
    bg_code = models.CharField(max_length=10)
    div_code = models.CharField(max_length=20)
    billadd = models.JSONField(default=dict)
    products = models.JSONField(default=list)
    channel = models.CharField(max_length=10, default='online')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders_core'

class EshopDetail(models.Model):
    """E-commerce specific order data."""
    PAYMENT_OPTION_CHOICES = [
        ('cashfree', 'Cashfree'),
        ('upi', 'UPI'),
        ('cod', 'Cash on Delivery'),
    ]
    
    order = models.OneToOneField(OrderCore, on_delete=models.CASCADE, related_name='eshop_detail')
    payment_option = models.CharField(max_length=10, choices=PAYMENT_OPTION_CHOICES)
    pay_reference = models.CharField(max_length=100, blank=True)
    upi_address = models.CharField(max_length=50, blank=True)
    order_expiry = models.DateTimeField(null=True, blank=True)
    fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'eshop_detail'
```

**Step 2: Create Order Serializers (`domains/eshop/serializers.py`)**

```python
from rest_framework import serializers
from .models import OrderCore, EshopDetail

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderCore
        fields = ['orderid', 'order_type', 'status', 'total_amount', 
                  'customer', 'bg_code', 'div_code', 'billadd', 'products', 
                  'channel', 'created_at', 'updated_at']
        read_only_fields = ['orderid', 'created_at', 'updated_at']

class EshopDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EshopDetail
        fields = ['order', 'payment_option', 'pay_reference', 'upi_address',
                  'order_expiry', 'fees', 'tax', 'discount', 'shipping']
```

**Step 3: Create Order ViewSets (`domains/eshop/viewsets.py`)**

```python
from rest_framework import viewsets, permissions
from .models import OrderCore, EshopDetail
from .serializers import OrderSerializer, EshopDetailSerializer


class OrderViewSet(viewsets.ModelViewSet, TenantScopingMixin):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Apply tenant scope from middleware (full/division/branch)
        return self.apply_tenant_scope(
            OrderCore.objects.all(), self.request
        )
    
    def perform_create(self, serializer):
        order = serializer.save(
            customer=self.request.user.identity_id,
            bg_code=self.request.bg_code,          # From middleware
            div_code=self.request.active_div_code,  # From middleware
        )
        
        # Create eshop_detail
        EshopDetail.objects.create(
            order=order,
            payment_option='cashfree',  # Default
        )


class CheckoutViewSet(viewsets.ViewSet):
    """Handle checkout and payment initiation."""
    
    def create(self, request):
        # Create order
        # Tenant context from middleware: request.bg_code, request.active_div_code
        order = OrderCore.objects.create(
            orderid=generate_orderid(),
            order_type='eshop',
            status='pending',
            total_amount=request.data['total_amount'],
            customer=request.user.identity_id,
            bg_code=request.bg_code,
            div_code=request.active_div_code,
            billadd=request.data['billadd'],
            products=request.data['products'],
            channel='online',
        )
        
        # Create eshop_detail
        EshopDetail.objects.create(
            order=order,
            payment_option=request.data.get('payment_option', 'cashfree'),
        )
        
        return Response({'order_id': order.id}, status=201)
```

**Step 4: Create Payment Views (`domains/eshop/payment/views.py`)**

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
import hmac
import hashlib
import base64
from plat.outbox.service import OutboxService


def verify_cashfree_signature(payload_string, signature, secret_key):
    """Verify Cashfree webhook signature."""
    computed = base64.b64encode(
        hmac.new(
            secret_key.encode('utf-8'),
            payload_string.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    return hmac.compare_digest(computed, signature)


class CashfreeWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # Verify HMAC signature
        signature = request.headers.get('X-CF-SIGNATURE')
        if not verify_cashfree_signature(
            request.body.decode('utf-8'),
            signature,
            settings.CASHFREE_SECRET_KEY
        ):
            return Response({'error': 'Invalid signature'}, status=400)
        
        # Resolve tenant context from the order record, NOT request.user
        # (this endpoint is HMAC-authenticated, not JWT-authenticated)
        order = OrderCore.objects.get(orderid=request.data['order_id'])
        
        # Queue payment verification in outbox
        OutboxService.publish_on_commit(
            event_type='order.payment_verified',
            payload={
                'order_id': order.id,
                'orderid': order.orderid,
                'payment_reference': request.data['payment_id'],
                'bg_code': order.bg_code,
            },
        )
        
        return Response({'status': 'received'}, status=202)
```

**Step 5: Update EShop URLs (`domains/eshop/urls.py`)**

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import CartViewSet, WishlistViewSet, AddressViewSet, OrderViewSet, CheckoutViewSet
from .payment.views import CashfreeWebhookView

router = DefaultRouter()
router.register('cart', CartViewSet, basename='cart')
router.register('wishlist', WishlistViewSet, basename='wishlist')
router.register('addresses', AddressViewSet, basename='addresses')
router.register('orders', OrderViewSet, basename='orders')

urlpatterns = [
    path('', include(router.urls)),
    path('checkout/', CheckoutViewSet.as_view({'post': 'create'}), name='checkout'),
    path('payment/webhook/', CashfreeWebhookView.as_view(), name='cashfree_webhook'),
]
```

#### Verification

```bash
# 1. Run migrations
python manage.py makemigrations eshop
python manage.py migrate eshop

# 2. Test order creation
curl -X POST http://localhost:8000/api/v1/eshop/checkout/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"total_amount": 45000, "billadd": {...}, "products": [...]}'

# 3. Test order listing
curl -X GET http://localhost:8000/api/v1/eshop/orders/ \
  -H "Authorization: Bearer <token>"

# 4. Run OpenAPI schema generation
python manage.py spectacular --file openapi-schema.yml
```

---

### Task 11: Implement Walk-in Management (1 day)

**Priority:** MEDIUM (Cafe operations)
**Effort:** 1 day
**Dependencies:** Phase 2 complete

#### Implementation Steps

**Step 1: Create Walk-in Model (`domains/cafe_arcade/models.py`)**

```python
from django.db import models
from users.models import Identity

class CafeWalkin(models.Model):
    """Walk-in customer (no auth credentials)."""
    identity = models.ForeignKey(
        Identity, 
        on_delete=models.CASCADE, 
        related_name='walkin_profile'
    )
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'cafe_walkins'
```

**Step 2: Create Walk-in Serializer (`domains/cafe_arcade/serializers.py`)**

```python
from rest_framework import serializers
from .models import CafeWalkin

class CafeWalkinSerializer(serializers.ModelSerializer):
    class Meta:
        model = CafeWalkin
        fields = ['id', 'identity', 'name', 'created_at']
        read_only_fields = ['id', 'identity', 'created_at']
```

**Step 3: Create Walk-in ViewSet (`domains/cafe_arcade/views.py`)**

```python
from rest_framework import viewsets, permissions
from users.models import Identity
from users.utils import normalize_phone
from .models import CafeWalkin
from .serializers import CafeWalkinSerializer


class CafeWalkinViewSet(viewsets.ModelViewSet, TenantScopingMixin):
    serializer_class = CafeWalkinSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return self.apply_tenant_scope(
            CafeWalkin.objects.all(), self.request
        )
    
    def perform_create(self, serializer):
        # Normalize phone
        phone_raw = serializer.validated_data.get('phone', '')
        phone = normalize_phone(phone_raw) if phone_raw else ''
        
        # Create identity with tenant context from middleware
        # (NOT request.user.bg_code — walk-ins may not have auth)
        identity = Identity.objects.create(
            phone=phone,
            name=serializer.validated_data['name'],
            bg_code=self.request.bg_code,
            div_code=self.request.active_div_code,
        )
        
        serializer.save(identity=identity)
```

**Step 4: Update Walk-in URLs (`domains/cafe_arcade/urls.py`)**

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CafeWalkinViewSet

router = DefaultRouter()
router.register('walkins', CafeWalkinViewSet, basename='walkin')

urlpatterns = [
    path('', include(router.urls)),
]
```

#### Verification

```bash
# 1. Run migrations
python manage.py makemigrations cafe_arcade
python manage.py migrate cafe_arcade

# 2. Test walk-in creation
curl -X POST http://localhost:8000/api/v1/cafe/walkins/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "phone": "9876543210"}'

# 3. Test walk-in listing
curl -X GET http://localhost:8000/api/v1/cafe/walkins/ \
  -H "Authorization: Bearer <token>"
```

---

### Task 12: Implement Protocol Enforcement (2-3 days)

**Priority:** HIGH (Spec requirement)
**Effort:** 2-3 days
**Dependencies:** Phase 2 complete

#### Implementation Steps

**Step 1: Create Cafe Protocol Interface (`domains/cafe_arcade/protocols.py`)**

```python
"""Cafe domain protocol interfaces."""
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

class ICafeSessionService(ABC):
    """Protocol for cafe session operations."""
    
    @abstractmethod
    def create_session(self, cafe_id: int, station_id: int, game_id: int, 
                      identity_id: str, price_plan_id: int,
                      bg_code: str, div_code: str) -> 'Session':
        """Create a new session."""
        pass
    
    @abstractmethod
    def end_session(self, session_id: int) -> 'Session':
        """End a session and trigger outbox event."""
        pass
    
    @abstractmethod
    def get_session(self, session_id: int) -> Optional['Session']:
        """Get session by ID."""
        pass
    
    @abstractmethod
    def list_sessions(self, cafe_id: int, bg_code: str, 
                     scope: str = 'full') -> list:
        """List sessions for a cafe, scoped by tenant."""
        pass

class ICafeStationService(ABC):
    """Protocol for cafe station operations."""
    
    @abstractmethod
    def get_station(self, station_id: int) -> Optional['Station']:
        """Get station by ID."""
        pass
    
    @abstractmethod
    def list_stations(self, cafe_id: int, bg_code: str) -> list:
        """List stations for a cafe, scoped by tenant."""
        pass
    
    @abstractmethod
    def send_command(self, station_id: int, command_type: str, payload: dict) -> 'StationCommand':
        """Send command to station."""
        pass
```

**Step 2: Create Tournaments Protocol Interface (`domains/tournaments/protocols.py`)**

```python
"""Tournaments domain protocol interfaces."""
from abc import ABC, abstractmethod
from typing import Optional

class ITournamentsService(ABC):
    """Protocol for tournament operations."""
    
    @abstractmethod
    def create_tournament(self, name: str, game: str, format: str, 
                         max_teams: int, bg_code: str, div_code: str) -> 'Tournament':
        """Create a new tournament."""
        pass
    
    @abstractmethod
    def register_team(self, tournament_id: int, team_id: str, 
                     captain_id: str, bg_code: str) -> 'Registration':
        """Register a team for a tournament."""
        pass
    
    @abstractmethod
    def get_tournament(self, tournament_id: int, bg_code: str) -> Optional['Tournament']:
        """Get tournament by ID, scoped by tenant."""
        pass
    
    @abstractmethod
    def list_tournaments(self, bg_code: str, scope: str = 'full') -> list:
        """List tournaments, scoped by tenant."""
        pass
```

**Step 3: Update Viewsets to Use Protocols**

**File:** `domains/cafe_arcade/views.py`

```python
from .protocols import ICafeSessionService
from .services import CafeSessionService


class SessionViewSet(viewsets.ModelViewSet):
    serializer_class = SessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_service(self) -> ICafeSessionService:
        return CafeSessionService()
    
    def list(self, request):
        service = self.get_service()
        sessions = service.list_sessions(
            cafe_id=request.query_params.get('cafe_id'),
            bg_code=request.bg_code,           # From middleware
            scope=getattr(request, 'scope', 'full'),
        )
        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)
    
    def create(self, request):
        service = self.get_service()
        session = service.create_session(
            cafe_id=request.data['cafe_id'],
            station_id=request.data['station_id'],
            game_id=request.data['game_id'],
            identity_id=request.user.identity_id,
            price_plan_id=request.data['price_plan_id'],
            bg_code=request.bg_code,           # From middleware
            div_code=request.active_div_code,   # From middleware
        )
        serializer = self.get_serializer(session)
        return Response(serializer.data, status=201)
```

**File:** `domains/tournaments/views.py`

```python
from .protocols import ITournamentsService
from .services import TournamentsService


class TournamentViewSet(viewsets.ModelViewSet):
    serializer_class = TournamentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_service(self) -> ITournamentsService:
        return TournamentsService()
    
    def list(self, request):
        service = self.get_service()
        tournaments = service.list_tournaments(
            bg_code=request.bg_code,           # From middleware
            scope=getattr(request, 'scope', 'full'),
        )
        serializer = self.get_serializer(tournaments, many=True)
        return Response(serializer.data)
```

**Step 4: Create Protocol Service Implementations**

**File:** `domains/cafe_arcade/services.py`

```python
from .protocols import ICafeSessionService
from .models import Session


class CafeSessionService(ICafeSessionService):
    def create_session(self, cafe_id, station_id, game_id, identity_id, 
                      price_plan_id, bg_code, div_code):
        session = Session.objects.create(
            cafe_id=cafe_id,
            station_id=station_id,
            game_id=game_id,
            identity_id=identity_id,
            price_plan_id=price_plan_id,
            bg_code=bg_code,
            div_code=div_code,
            status='active',
        )
        return session
    
    def end_session(self, session_id):
        session = Session.objects.get(id=session_id)
        session.status = 'ended'
        session.end_time = timezone.now()
        session.total_charges = calculate_final_charges(session)
        session.save()
        
        # Trigger outbox event — tenant context from the session entity
        from plat.outbox.service import OutboxService
        OutboxService.publish_on_commit(
            event_type='fnb.session_billing',
            payload={
                'session_id': session.id,
                'last_order_id': session.last_order_id,
                'total_charges': session.total_charges,
                'bg_code': session.bg_code,
            },
        )
        
        return session
    
    def get_session(self, session_id):
        return Session.objects.filter(id=session_id).first()
    
    def list_sessions(self, cafe_id, bg_code, scope='full'):
        qs = Session.objects.filter(cafe_id=cafe_id, bg_code=bg_code)
        if scope == 'division':
            # Filter by active division
            pass
        elif scope == 'branch':
            # Filter by active branch
            pass
        return qs
```

**File:** `domains/tournaments/services.py`

```python
from .protocols import ITournamentsService
from .models import Tournament


class TournamentsService(ITournamentsService):
    def create_tournament(self, name, game, format, max_teams, bg_code, div_code):
        tournament = Tournament.objects.create(
            name=name,
            game=game,
            format=format,
            max_teams=max_teams,
            bg_code=bg_code,
            div_code=div_code,
            status='draft',
        )
        return tournament
    
    def register_team(self, tournament_id, team_id, captain_id, bg_code):
        registration = Registration.objects.create(
            tournament_id=tournament_id,
            team_id=team_id,
            captain_id=captain_id,
            bg_code=bg_code,
            status='pending',
        )
        return registration
    
    def get_tournament(self, tournament_id, bg_code):
        return Tournament.objects.filter(
            id=tournament_id, bg_code=bg_code
        ).first()
    
    def list_tournaments(self, bg_code, scope='full'):
        qs = Tournament.objects.filter(bg_code=bg_code)
        if scope == 'division':
            pass
        elif scope == 'branch':
            pass
        return qs
```

#### Verification

```bash
# 1. Verify protocol interfaces exist
ls -la domains/cafe_arcade/protocols.py domains/tournaments/protocols.py

# 2. Verify viewsets use protocols
grep -n "ICafeSessionService\|ITournamentsService" domains/cafe_arcade/views.py domains/tournaments/views.py

# 3. Verify no request.user.bg_code in protocol services
grep -rn "request.user.bg_code" domains/cafe_arcade/services.py domains/tournaments/services.py
# Expected: 0 results

# 4. Run tests
python manage.py test domains.cafe_arcade tests.test_protocols -v 2
```

---

## Execution Timeline

```
Week 1 (Phase 1: 3-5 days):
  Day 1: Task 1 (serializers) + Task 5 (documentation)
  Day 2: Task 2 (EShop cart/wishlist/addresses)
  Day 3: Task 3 (kurostaff migration)
  Day 4: Task 4 (dead functions)
  Day 5: Buffer + Phase 1 verification

Week 2 (Phase 2: 5-7 days):
  Day 6: Task 6 (outbox adoption)
  Day 7-8: Task 7 (tenant isolation)
  Day 9: Task 8 (phone normalization)
  Day 10-12: Task 9 (identity migration)
  Day 13: Buffer + Phase 2 verification

Week 3 (Phase 3: 5-7 days):
  Day 14-15: Task 10 (EShop orders/payment)
  Day 16: Task 11 (walk-in management)
  Day 17-19: Task 12 (protocol enforcement)
  Day 20: Buffer + Phase 3 verification
```

**Total:** 20 days (with buffer)

---

## Phase Completion Criteria

### Phase 1 (Core Spec Alignment)
- [ ] OpenAPI schema generates without errors
- [ ] EShop cart/wishlist/addresses endpoints work
- [ ] No `teams.kurostaff.views` imports remain
- [ ] 23 dead functions removed
- [ ] Domain database usage documented

### Phase 2 (Foundational Infrastructure)
- [ ] Outbox events published via existing `plat/outbox/` primitive
- [ ] `platform_outbox_events` table used (not `outbox_events`)
- [ ] No duplicate outbox files in `plat/outbox/`
- [ ] Tenant isolation proven by behavior (RLS + TenantCollection)
- [ ] Scope resolver centralizes full/division/branch filtering
- [ ] Phone normalization working (E.164 format)
- [ ] Identity migration uses `(bg_code, phone)` composite key
- [ ] No hardcoded tenant fallbacks in migration
- [ ] Migration validation gates pass

### Phase 3 (Domain-Specific Features)
- [ ] EShop orders and payment endpoints work
- [ ] Webhook resolves tenant from order record (not `request.user`)
- [ ] Walk-in management endpoints work
- [ ] Protocol interfaces defined for cafe and tournaments
- [ ] Viewsets use protocol interfaces (not direct DB)
- [ ] No `request.user.bg_code` in domain service code
- [ ] All tests passing

---

## Risk Mitigation

### Risk: Outbox Extension Conflicts with Existing Primitive
**Mitigation:** Only add domain event handler files (`outbox_handlers.py`). Do not modify `plat/outbox/models.py`, `service.py`, or `worker.py`. Verify existing primitive is intact before and after.

### Risk: Identity Migration Breaks Existing Data
**Mitigation:** Run migrations in staging first. Use composite `(bg_code, phone)` lookup key. Run all 13 validation gates from `migration_spec.md` §2.3. Dry-run first.

### Risk: Protocol Enforcement Requires Viewset Refactoring
**Mitigation:** Create protocol interfaces first, refactor viewsets incrementally. Services accept `bg_code`/`div_code` as parameters, resolved by views from middleware context.

### Risk: EShop Payment Integration Requires Cashfree Account
**Mitigation:** Use Cashfree sandbox for development, switch to prod before deployment.

### Risk: Webhook Tenant Context Injection
**Mitigation:** Webhook resolves `bg_code` from the order record, not from request context. HMAC signature verification is the only auth — no user object exists.

---

## Success Metrics

1. **OpenAPI:** Schema generates without errors
2. **EShop:** 16/16 endpoints implemented and tested
3. **Outbox:** Events published via existing `plat/outbox/` primitive, `platform_outbox_events` table
4. **Tenant Isolation:** 0 raw PyMongo calls, 0 hardcoded tenant codes, behavioral isolation tests pass
5. **Identity:** `(bg_code, phone)` composite key enforced, migration validation gates pass
6. **Protocols:** All cafe and tournaments viewsets use protocol interfaces
7. **Tenant Context:** No `request.user.bg_code` in domain code; middleware-derived or entity-resolved
8. **Tests:** 80%+ test coverage

---

## Documentation Updates Required

After execution, update these documents:

1. **`KUNGOS_DOMAIN_DATABASE_USAGE.md`** — Add outbox, identity migration, protocols
2. **`CAFE_COUNCIL_TODO.md`** — Update phase completion status
3. **`migration_spec.md`** — Mark M1 migration as complete
4. **`endpoint_contract_spec.md`** — Add EShop order/payment endpoints

---

**Handoff prepared:** 2026-06-27
**Ready for execution:** Yes
**Next step:** Begin Phase 1, Task 1
