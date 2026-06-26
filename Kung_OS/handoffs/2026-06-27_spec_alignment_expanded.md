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

### Task 6: Implement Outbox Pattern (2 days)

**Priority:** CRITICAL (Transaction integrity)
**Effort:** 2 days
**Dependencies:** Phase 1 complete

#### Current State
- Direct MongoDB writes from PostgreSQL views
- Split-brain risk: PG succeeds, MongoDB fails (or vice versa)

#### Target State
- All domain writes use `plat/outbox/` primitive
- Outbox events: `order.placed`, `order.payment_verified`, `fnb.session_billing`

#### Implementation Steps

**Step 1: Create Outbox Service (`plat/outbox/service.py`)**

```python
"""Outbox pattern service for durable event publishing."""
from django.db import transaction
from django.utils import timezone
import json

class OutboxEvent:
    def __init__(self, event_type: str, payload: dict, bg_code: str):
        self.event_type = event_type
        self.payload = payload
        self.bg_code = bg_code
        self.created_at = timezone.now()

class OutboxService:
    """Publish events to outbox table for reliable processing."""
    
    @staticmethod
    def publish(event_type: str, payload: dict, bg_code: str):
        """Publish event to outbox table."""
        event = OutboxEvent(event_type, payload, bg_code)
        
        # Insert into outbox table
        from plat.outbox.models import OutboxEvent as OutboxEventModel
        OutboxEventModel.objects.create(
            event_type=event.event_type,
            payload=json.dumps(event.payload),
            bg_code=event.bg_code,
            created_at=event.created_at,
        )
    
    @staticmethod
    def publish_on_commit(event_type: str, payload: dict, bg_code: str):
        """Publish event after successful PG commit."""
        transaction.on_commit(
            lambda: OutboxService.publish(event_type, payload, bg_code)
        )
```

**Step 2: Create Outbox Model (`plat/outbox/models.py`)**

```python
from django.db import models
from django.utils import timezone

class OutboxEvent(models.Model):
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    bg_code = models.CharField(max_length=10, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'outbox_events'
        indexes = [
            models.Index(fields=['event_type', 'created_at']),
            models.Index(fields=['bg_code', 'created_at']),
        ]
```

**Step 3: Create Outbox Processor (`plat/outbox/processor.py`)**

```python
"""Background processor for outbox events."""
import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

class OutboxProcessor:
    """Process outbox events in background."""
    
    @staticmethod
    def process_pending():
        """Process all unprocessed outbox events."""
        cutoff = timezone.now() - timedelta(minutes=5)
        pending = OutboxEvent.objects.filter(
            processed_at__isnull=True,
            created_at__lt=cutoff
        )
        
        for event in pending:
            try:
                OutboxProcessor._process_event(event)
            except Exception as e:
                logger.error(f"Outbox event {event.id} failed: {e}")
                event.error_message = str(e)
                event.save()
    
    @staticmethod
    def _process_event(event: OutboxEvent):
        """Process a single outbox event."""
        if event.event_type == 'order.placed':
            OutboxProcessor._handle_order_placed(event)
        elif event.event_type == 'order.payment_verified':
            OutboxProcessor._handle_order_payment_verified(event)
        elif event.event_type == 'fnb.session_billing':
            OutboxProcessor._handle_fnb_session_billing(event)
        else:
            logger.warning(f"Unknown outbox event type: {event.event_type}")
        
        event.processed_at = timezone.now()
        event.save()
    
    @staticmethod
    def _handle_order_placed(event: OutboxEvent):
        """Handle order.placed event."""
        # Update customer metrics via outbox handler
        from identity.outbox_handlers import update_customer_order_metrics
        update_customer_order_metrics(event.payload)
    
    @staticmethod
    def _handle_order_payment_verified(event: OutboxEvent):
        """Handle order.payment_verified event."""
        # Trigger order conversion pipeline
        from eshop.outbox_handlers import process_order_conversion
        process_order_conversion(event.payload)
    
    @staticmethod
    def _handle_fnb_session_billing(event: OutboxEvent):
        """Handle fnb.session_billing event."""
        # Update F&B order in MongoDB
        from cafe_fnb.outbox_handlers import update_session_billing
        update_session_billing(event.payload)
```

**Step 4: Create Outbox Management Command (`plat/management/commands/process_outbox.py`)**

```python
from django.core.management.base import BaseCommand
from plat.outbox.processor import OutboxProcessor

class Command(BaseCommand):
    help = 'Process pending outbox events'
    
    def handle(self, *args, **options):
        self.stdout.write('Processing outbox events...')
        OutboxProcessor.process_pending()
        self.stdout.write(self.style.SUCCESS('Outbox processing complete'))
```

**Step 5: Update Domain Viewsets to Use Outbox**

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
        OutboxService.publish_on_commit(
            event_type='fnb.session_billing',
            payload={
                'session_id': session.id,
                'last_order_id': session.last_order_id,
                'total_charges': session.total_charges,
            },
            bg_code=request.user.bg_code
        )
```

**File:** `domains/eshop/viewsets.py` (checkout)

```python
from plat.outbox.service import OutboxService

class CheckoutViewSet(viewsets.ViewSet):
    def create(self, request):
        # Create order in PG
        order = OrderCore.objects.create(...)
        
        # Queue payment verification in outbox
        OutboxService.publish_on_commit(
            event_type='order.placed',
            payload={
                'order_id': order.id,
                'orderid': order.orderid,
                'customer_id': order.customer_id,
                'total_amount': order.total_amount,
            },
            bg_code=request.user.bg_code
        )
        
        return Response({'order_id': order.id}, status=201)
```

**File:** `domains/eshop/payment/views.py` (webhook)

```python
from plat.outbox.service import OutboxService

def cashfree_webhook(request):
    # Verify HMAC signature
    if not verify_cashfree_signature(...):
        return Response({'error': 'Invalid signature'}, status=400)
    
    # Queue payment verification in outbox
    OutboxService.publish_on_commit(
        event_type='order.payment_verified',
        payload={
            'order_id': request.data['order_id'],
            'payment_reference': request.data['payment_id'],
        },
        bg_code=request.user.bg_code
    )
    
    return Response({'status': 'received'}, status=202)
```

#### Verification

```bash
# 1. Run migrations
python manage.py makemigrations outbox
python manage.py migrate outbox

# 2. Test outbox publishing
python manage.py shell -c "
from plat.outbox.service import OutboxService
OutboxService.publish('test.event', {'key': 'value'}, 'KURO0001')
"

# 3. Test outbox processing
python manage.py process_outbox

# 4. Verify outbox events created
python manage.py shell -c "
from plat.outbox.models import OutboxEvent
print(f'Outbox events: {OutboxEvent.objects.count()}')
"
```

---

### Task 7: Implement Tenant Isolation Verification (1 day)

**Priority:** CRITICAL (Security)
**Effort:** 1 day
**Dependencies:** Phase 1 complete

#### Implementation Steps

**Step 1: Create Tenant Isolation Test Suite (`tests/test_tenant_isolation.py`)**

```python
from django.test import TestCase
from users.models import Identity, CustomUser
from tenant.models import BusinessGroup, Division

class TenantIsolationTests(TestCase):
    """Verify tenant isolation across all domains."""
    
    def setUp(self):
        # Create two business groups
        self.bg1 = BusinessGroup.objects.create(bg_code='BG0001', name='Test BG 1')
        self.bg2 = BusinessGroup.objects.create(bg_code='BG0002', name='Test BG 2')
        
        # Create divisions
        self.div1 = Division.objects.create(
            div_code='BG0001_001', bg_code='BG0001', name='Test Division 1'
        )
        self.div2 = Division.objects.create(
            div_code='BG0002_001', bg_code='BG0002', name='Test Division 2'
        )
    
    def test_mongo_tenant_isolation(self):
        """Verify MongoDB queries are tenant-scoped."""
        from plat.tenant.collection import TenantCollection
        
        # Query should auto-inject bg_code
        collection = TenantCollection.get_collection('test_collection')
        # Verify bg_code is in filter
        self.assertIn('bg_code', collection._filters)
    
    def test_postgres_tenant_isolation(self):
        """Verify PostgreSQL queries include bg_code filter."""
        from orders.models import OrderCore
        
        # Query should include bg_code
        orders = OrderCore.objects.all()
        # Verify SQL includes bg_code filter
        sql = str(orders.query)
        self.assertIn('bg_code', sql)
    
    def test_no_raw_pymongo_calls(self):
        """Verify no raw PyMongo calls bypass tenant isolation."""
        import subprocess
        result = subprocess.run(
            ['grep', '-rn', 'pymongo.MongoClient', '--include=*.py', '.'],
            capture_output=True, text=True
        )
        # Should only find imports, not direct calls
        lines = [l for l in result.stdout.split('\n') if l and 'import' not in l]
        self.assertEqual(len(lines), 0, f"Raw PyMongo calls found: {lines}")
    
    def test_no_hardcoded_tenant_codes(self):
        """Verify no hardcoded tenant codes."""
        import subprocess
        result = subprocess.run(
            ['grep', '-rn', "'KURO0001'", '--include=*.py', '.'],
            capture_output=True, text=True
        )
        # Should only find in tests or migrations
        lines = [l for l in result.stdout.split('\n') if l and 'test_' not in l and 'migration' not in l]
        self.assertEqual(len(lines), 0, f"Hardcoded tenant codes found: {lines}")
```

**Step 2: Add Tenant Isolation to CI/CD**

**File:** `.github/workflows/ci.yml` (or equivalent)

```yaml
- name: Run tenant isolation tests
  run: |
    python manage.py test tests.test_tenant_isolation -v 2
```

**Step 3: Update All Viewsets to Use TenantContext**

**Pattern:**
```python
# BEFORE
def list_orders(request):
    orders = OrderCore.objects.all()  # ❌ No tenant filter

# AFTER
def list_orders(request):
    bg_code = request.user.bg_code  # From JWT/session
    orders = OrderCore.objects.filter(bg_code=bg_code)  # ✅ Tenant filter
```

#### Verification

```bash
# 1. Run tenant isolation tests
python manage.py test tests.test_tenant_isolation -v 2

# 2. Verify no raw PyMongo calls
grep -rn "pymongo.MongoClient" --include="*.py" | grep -v import | grep -v __pycache__

# 3. Verify no hardcoded tenant codes
grep -rn "'KURO0001'" --include="*.py" | grep -v test_ | grep -v migration

# 4. Run full test suite
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
        identity = Identity.objects.create(
            phone=phone,
            name=request.data['name'],
            bg_code=request.data['bg_code'],
            div_code=request.data['div_code'],
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

### Task 9: Implement Identity Migration (2-3 days)

**Priority:** HIGH (Foundational)
**Effort:** 2-3 days
**Dependencies:** Task 6, 7, 8 complete

#### Implementation Steps

**Step 1: Create Customer Identity Migration (`users/management/commands/migrate_customers.py`)**

```python
from django.core.management.base import BaseCommand
from users.models import Identity, Customer

class Command(BaseCommand):
    help = 'Migrate customers from reb_users + misc to users_customer'
    
    def handle(self, *args, **options):
        self.stdout.write('Migrating customers...')
        
        # Migrate from reb_users
        from plat.tenant.collection import TenantCollection
        reb_users = TenantCollection.get_collection('reb_users')
        
        for user in reb_users.find({}, {'_id': 0}):
            phone = user.get('phone')
            if not phone:
                continue
            
            # Normalize phone
            from users.utils import normalize_phone
            phone = normalize_phone(phone)
            
            # Create or get identity
            identity, created = Identity.objects.get_or_create(
                phone=phone,
                defaults={
                    'name': user.get('name', ''),
                    'bg_code': user.get('bg_code', 'KURO0001'),
                    'div_code': user.get('div_code', 'KURO0001_001'),
                }
            )
            
            # Create customer extension
            Customer.objects.update_or_create(
                identity=identity,
                defaults={
                    'registered': user.get('registered', False),
                    'order_count': user.get('order_count', 0),
                    'total_spent': user.get('total_spent', 0),
                }
            )
        
        self.stdout.write(self.style.SUCCESS('Customer migration complete'))
```

**Step 2: Create Player Identity Migration (`users/management/commands/migrate_players.py`)**

```python
from django.core.management.base import BaseCommand
from users.models import Identity, Player

class Command(BaseCommand):
    help = 'Migrate players from MongoDB to users_player'
    
    def handle(self, *args, **options):
        self.stdout.write('Migrating players...')
        
        from plat.tenant.collection import TenantCollection
        players = TenantCollection.get_collection('players')
        
        for player in players.find({}, {'_id': 0}):
            phone = player.get('phone')
            if not phone:
                continue
            
            # Normalize phone
            from users.utils import normalize_phone
            phone = normalize_phone(phone)
            
            # Create or get identity
            identity, created = Identity.objects.get_or_create(
                phone=phone,
                defaults={
                    'name': player.get('name', ''),
                    'bg_code': player.get('bg_code', 'KURO0001'),
                    'div_code': player.get('div_code', 'KURO0001_001'),
                }
            )
            
            # Create player extension
            Player.objects.update_or_create(
                identity=identity,
                defaults={
                    'player_id': player.get('player_id'),
                    'team_id': player.get('team_id'),
                    'riot_id': player.get('riot_id'),
                    'rank': player.get('rank'),
                }
            )
        
        self.stdout.write(self.style.SUCCESS('Player migration complete'))
```

**Step 3: Create Organization Identity Migration (`users/management/commands/migrate_organizations.py`)**

```python
from django.core.management.base import BaseCommand
from users.models import Organization, VendorProfile, TeamProfile

class Command(BaseCommand):
    help = 'Migrate organizations (teams + vendors) to users_organization'
    
    def handle(self, *args, **options):
        self.stdout.write('Migrating organizations...')
        
        # Migrate vendors
        from plat.tenant.collection import TenantCollection
        vendors = TenantCollection.get_collection('vendors')
        
        for vendor in vendors.find({}, {'_id': 0}):
            Organization.objects.update_or_create(
                org_id=vendor.get('org_id'),
                defaults={
                    'org_type': 'vendor',
                    'name': vendor.get('name', ''),
                    'bg_code': vendor.get('bg_code', 'KURO0001'),
                    'div_code': vendor.get('div_code', 'KURO0001_001'),
                }
            )
            
            VendorProfile.objects.update_or_create(
                org_id=vendor.get('org_id'),
                defaults={
                    'gstin': vendor.get('gstin'),
                    'pan': vendor.get('pan'),
                    'address': vendor.get('address'),
                }
            )
        
        # Migrate teams
        teams = TenantCollection.get_collection('teams')
        
        for team in teams.find({}, {'_id': 0}):
            Organization.objects.update_or_create(
                org_id=team.get('org_id'),
                defaults={
                    'org_type': 'team',
                    'name': team.get('name', ''),
                    'bg_code': team.get('bg_code', 'KURO0001'),
                    'div_code': team.get('div_code', 'KURO0001_001'),
                }
            )
            
            TeamProfile.objects.update_or_create(
                org_id=team.get('org_id'),
                defaults={
                    'team_id': team.get('team_id'),
                    'coach': team.get('coach'),
                }
            )
        
        self.stdout.write(self.style.SUCCESS('Organization migration complete'))
```

**Step 4: Run Migrations**

```bash
python manage.py migrate_customers
python manage.py migrate_players
python manage.py migrate_organizations
```

**Step 5: Verify Migrations**

```bash
# Check customer count
python manage.py shell -c "
from users.models import Identity, Customer
print(f'Identities: {Identity.objects.count()}')
print(f'Customers: {Customer.objects.count()}')
"

# Check player count
python manage.py shell -c "
from users.models import Identity, Player
print(f'Players: {Player.objects.count()}')
"

# Check organization count
python manage.py shell -c "
from users.models import Organization
print(f'Organizations: {Organization.objects.count()}')
"
```

#### Verification

```bash
# 1. Run migrations
python manage.py migrate_customers
python manage.py migrate_players
python manage.py migrate_organizations

# 2. Verify counts
python manage.py shell -c "
from users.models import Identity, Customer, Player, Organization
print(f'Identities: {Identity.objects.count()}')
print(f'Customers: {Customer.objects.count()}')
print(f'Players: {Player.objects.count()}')
print(f'Organizations: {Organization.objects.count()}')
"

# 3. Run identity tests
python manage.py test users.tests.IdentityTests -v 2
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
    division = models.CharField(max_length=20)
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
                  'customer', 'bg_code', 'division', 'billadd', 'products', 
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

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return OrderCore.objects.filter(
            customer=self.request.user.identity_id
        )
    
    def perform_create(self, serializer):
        order = serializer.save(
            customer=self.request.user.identity_id,
            bg_code=self.request.user.bg_code,
            division=self.request.user.active_div_code,
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
        order = OrderCore.objects.create(
            orderid=f"ESH{OrderCore.objects.count() + 1:06d}",
            order_type='eshop',
            status='pending',
            total_amount=request.data['total_amount'],
            customer=request.user.identity_id,
            bg_code=request.user.bg_code,
            division=request.user.active_div_code,
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
        # Verify signature
        signature = request.headers.get('X-CF-SIGNATURE')
        if not verify_cashfree_signature(
            request.body.decode('utf-8'),
            signature,
            settings.CASHFREE_SECRET_KEY
        ):
            return Response({'error': 'Invalid signature'}, status=400)
        
        # Queue payment verification in outbox
        from plat.outbox.service import OutboxService
        OutboxService.publish_on_commit(
            event_type='order.payment_verified',
            payload={
                'order_id': request.data['order_id'],
                'payment_reference': request.data['payment_id'],
            },
            bg_code=request.user.bg_code
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
from .models import CafeWalkin
from .serializers import CafeWalkinSerializer

class CafeWalkinViewSet(viewsets.ModelViewSet):
    serializer_class = CafeWalkinSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return CafeWalkin.objects.filter(
            identity__bg_code=self.request.user.bg_code
        )
    
    def perform_create(self, serializer):
        # Create identity for walk-in
        identity = Identity.objects.create(
            phone=serializer.validated_data.get('phone', ''),
            name=serializer.validated_data['name'],
            bg_code=self.request.user.bg_code,
            div_code=self.request.user.active_div_code,
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
  -d '{"name': 'John Doe', 'phone': '9876543210'}'

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
                      identity_id: str, price_plan_id: int) -> 'Session':
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
    def list_sessions(self, cafe_id: int, status: str = 'active') -> list:
        """List sessions for a cafe."""
        pass

class ICafeStationService(ABC):
    """Protocol for cafe station operations."""
    
    @abstractmethod
    def get_station(self, station_id: int) -> Optional['Station']:
        """Get station by ID."""
        pass
    
    @abstractmethod
    def list_stations(self, cafe_id: int) -> list:
        """List stations for a cafe."""
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
                     captain_id: str) -> 'Registration':
        """Register a team for a tournament."""
        pass
    
    @abstractmethod
    def get_tournament(self, tournament_id: int) -> Optional['Tournament']:
        """Get tournament by ID."""
        pass
    
    @abstractmethod
    def list_tournaments(self, status: str = 'open') -> list:
        """List tournaments."""
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
            status=request.query_params.get('status', 'active')
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
            status=request.query_params.get('status', 'open')
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
    def create_session(self, cafe_id, station_id, game_id, identity_id, price_plan_id):
        session = Session.objects.create(
            cafe_id=cafe_id,
            station_id=station_id,
            game_id=game_id,
            identity_id=identity_id,
            price_plan_id=price_plan_id,
            status='active',
        )
        return session
    
    def end_session(self, session_id):
        session = Session.objects.get(id=session_id)
        session.status = 'ended'
        session.end_time = timezone.now()
        session.total_charges = calculate_final_charges(session)
        session.save()
        
        # Trigger outbox event
        from plat.outbox.service import OutboxService
        OutboxService.publish_on_commit(
            event_type='fnb.session_billing',
            payload={
                'session_id': session.id,
                'last_order_id': session.last_order_id,
                'total_charges': session.total_charges,
            },
            bg_code=session.bg_code
        )
        
        return session
    
    def get_session(self, session_id):
        return Session.objects.filter(id=session_id).first()
    
    def list_sessions(self, cafe_id, status='active'):
        return Session.objects.filter(cafe_id=cafe_id, status=status)
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
    
    def register_team(self, tournament_id, team_id, captain_id):
        registration = Registration.objects.create(
            tournament_id=tournament_id,
            team_id=team_id,
            captain_id=captain_id,
            status='pending',
        )
        return registration
    
    def get_tournament(self, tournament_id):
        return Tournament.objects.filter(id=tournament_id).first()
    
    def list_tournaments(self, status='open'):
        return Tournament.objects.filter(status=status)
```

#### Verification

```bash
# 1. Verify protocol interfaces exist
ls -la domains/cafe_arcade/protocols.py domains/tournaments/protocols.py

# 2. Verify viewsets use protocols
grep -n "ICafeSessionService\|ITournamentsService" domains/cafe_arcade/views.py domains/tournaments/views.py

# 3. Run tests
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
  Day 6-7: Task 6 (outbox pattern)
  Day 8: Task 7 (tenant isolation)
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
- [ ] Outbox events published and processed
- [ ] Tenant isolation verified (all queries scoped)
- [ ] Phone normalization working (E.164 format)
- [ ] Customer identity migration complete
- [ ] Player identity migration complete
- [ ] Organization identity migration complete

### Phase 3 (Domain-Specific Features)
- [ ] EShop orders and payment endpoints work
- [ ] Walk-in management endpoints work
- [ ] Protocol interfaces defined for cafe and tournaments
- [ ] Viewsets use protocol interfaces (not direct DB)
- [ ] All tests passing

---

## Risk Mitigation

### Risk: Outbox Pattern Adds Complexity
**Mitigation:** Start with simple outbox table, add processing logic incrementally

### Risk: Identity Migration Breaks Existing Data
**Mitigation:** Run migrations in staging first, verify data integrity

### Risk: Protocol Enforcement Requires Viewset Refactoring
**Mitigation:** Create protocol interfaces first, refactor viewsets incrementally

### Risk: EShop Payment Integration Requires Cashfree Account
**Mitigation:** Use Cashfree sandbox for development, switch to prod before deployment

---

## Success Metrics

1. **OpenAPI:** Schema generates without errors
2. **EShop:** 16/16 endpoints implemented and tested
3. **Tenant Isolation:** 0 raw PyMongo calls, 0 hardcoded tenant codes
4. **Identity:** 100% of customers/players/organizations migrated
5. **Protocols:** All cafe and tournaments viewsets use protocol interfaces
6. **Tests:** 80%+ test coverage

---

## Documentation Updates Required

After execution, update these documents:

1. **`KUNGOS_DOMAIN_DATABASE_USAGE.md`** — Add outbox, identity migration, protocols
2. **`CAFE_COUNCIL_TODO.md`** — Update phase completion status
3. **`migration_spec.md`** — Add outbox, identity migration tasks
4. **`endpoint_contract_spec.md`** — Add EShop order/payment endpoints

---

**Handoff prepared:** 2026-06-27
**Ready for execution:** Yes
**Next step:** Begin Phase 1, Task 1