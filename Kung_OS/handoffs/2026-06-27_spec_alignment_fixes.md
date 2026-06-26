# Spec Alignment Fixes — Execution Handoff

**Date:** 2026-06-27
**Project:** `kteam-dj-chief`
**Status:** Ready for execution
**Estimated Effort:** 3-5 days

---

## Overview

This handoff covers 5 critical fixes to align the codebase with the target state spec:

1. **Fix `division` → `div_code` in Serializers** (30 min)
2. **Implement Full EShop Domain** (2-3 days)
3. **Migrate `teams/kurostaff/` Imports** (1-2 days)
4. **Remove 34 Dead Functions** (2-3 days)
5. **Document Domain Database Usage** (2-3 hours)

---

## Task 1: Fix `division` → `div_code` in Serializers

**Priority:** CRITICAL (Blocks OpenAPI)
**Effort:** 30 minutes
**Dependencies:** None

### Current State

**File:** `users/api/rbac_serializers.py`

```python
class UserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRole
        fields = ['id', 'userid', 'role', 'role_name', 'bg_code', 'division',  # ❌ WRONG
                  'assigned_by', 'assigned_at']

class UserPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPermission
        fields = ['id', 'userid', 'permission', 'perm_code', 'module', 'level',
                  'bg_code', 'division', 'reason', 'expires_at', 'granted_by', 'granted_at']  # ❌ WRONG
```

**Models have `div_code` (canonical):**
- `users/models.py:UserRole.div_code` (line ~200)
- `users/models.py:UserPermission.div_code` (line ~350)

### Fix Required

**File:** `users/api/rbac_serializers.py`

```python
class UserRoleSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.role_name', read_only=True, allow_null=True)

    class Meta:
        model = UserRole
        fields = ['id', 'userid', 'role', 'role_name', 'bg_code', 'div_code',  # ✅ FIXED
                  'assigned_by', 'assigned_at']
        read_only_fields = ['assigned_at']


class UserPermissionSerializer(serializers.ModelSerializer):
    perm_code = serializers.CharField(source='permission.perm_code', read_only=True)
    module = serializers.CharField(source='permission.module', read_only=True)

    class Meta:
        model = UserPermission
        fields = ['id', 'userid', 'permission', 'perm_code', 'module', 'level',
                  'bg_code', 'div_code', 'reason', 'expires_at', 'granted_by', 'granted_at']  # ✅ FIXED
        read_only_fields = ['granted_at']
```

### Verification

```bash
# 1. Check serializer compiles
python -m py_compile users/api/rbac_serializers.py

# 2. Check OpenAPI schema generates
python manage.py spectacular --file openapi-schema.yml

# 3. Verify no remaining `division` references in serializers
grep -n "division" users/api/rbac_serializers.py
# Expected: 0 results (except comments)

# 4. Run RBAC tests
python manage.py test users.tests.RBACTests -v 2
```

---

## Task 2: Implement Full EShop Domain

**Priority:** CRITICAL (Blocks E-Commerce)
**Effort:** 2-3 days
**Dependencies:** Task 1 (OpenAPI must work first)

### Current State

**File:** `domains/eshop/urls.py`

```python
router = DefaultRouter()
# router.register('cart', CartViewSet, basename='cart')  # COMMENTED OUT
# router.register('wishlist', WishlistViewSet, basename='wishlist')  # COMMENTED OUT
# router.register('addresses', AddresslistViewSet, basename='addresses')  # COMMENTED OUT
# router.register('orders', OrderViewSet, basename='orders')  # COMMENTED OUT

urlpatterns = [
    path('', include(router.urls)),
]
```

**Status:** Empty shell — only `__init__.py`, `apps.py`, `urls.py` exist

### Target State (from `ecommerce_spec.md`)

**Required Components:**
1. **Models:** `Cart`, `Wishlist`, `Addresslist`, `Order` (PostgreSQL)
2. **Serializers:** DRF serializers for all models
3. **ViewSets:** CRUD viewsets for cart, wishlist, addresses, orders
4. **Payment Integration:** Cashfree PG, UPI QR generation
5. **Webhook Handler:** Cashfree webhook with HMAC verification

### Implementation Plan

#### Step 1: Create Models (`domains/eshop/models.py`)

```python
from django.db import models
from users.models import Identity

class Cart(models.Model):
    user = models.ForeignKey(Identity, on_delete=models.CASCADE, related_name='cart_items')
    productid = models.CharField(max_length=50)  # MongoDB catalog reference
    category = models.CharField(max_length=50)
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eshop_cart'

class Wishlist(models.Model):
    user = models.ForeignKey(Identity, on_delete=models.CASCADE, related_name='wishlist_items')
    productid = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'eshop_wishlist'

class Addresslist(models.Model):
    user = models.ForeignKey(Identity, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=20)  # bill/ship/registered/office/warehouse
    address_line1 = models.CharField(max_length=150)
    address_line2 = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=150)
    state = models.CharField(max_length=150)
    country = models.CharField(max_length=100, default='India')
    pincode = models.CharField(max_length=10)
    phone_no = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False)
    delete_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eshop_addresses'
```

#### Step 2: Create Serializers (`domains/eshop/serializers.py`)

```python
from rest_framework import serializers
from .models import Cart, Wishlist, Addresslist

class CartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        fields = ['id', 'productid', 'category', 'quantity', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class WishlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wishlist
        fields = ['id', 'productid', 'created_at']
        read_only_fields = ['id', 'created_at']

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Addresslist
        fields = ['id', 'address_type', 'address_line1', 'address_line2', 'city', 
                  'state', 'country', 'pincode', 'phone_no', 'is_default', 'is_used']
        read_only_fields = ['id', 'is_used']
```

#### Step 3: Create ViewSets (`domains/eshop/viewsets.py`)

```python
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from .models import Cart, Wishlist, Addresslist
from .serializers import CartSerializer, WishlistSerializer, AddressSerializer

class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user.identity_id)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user.identity_id)

class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user.identity_id)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user.identity_id)

class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Addresslist.objects.filter(
            user=self.request.user.identity_id,
            delete_flag=False
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user.identity_id)

    def perform_update(self, serializer):
        address = self.get_object()
        if address.is_used:
            # Clone address (immutable edit pattern)
            address.delete_flag = True
            address.save()
            
            new_address = Addresslist.objects.create(
                user=address.user,
                **serializer.validated_data,
            )
            serializer.instance = new_address
        else:
            serializer.save()
```

#### Step 4: Update URLs (`domains/eshop/urls.py`)

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import CartViewSet, WishlistViewSet, AddressViewSet

router = DefaultRouter()
router.register('cart', CartViewSet, basename='cart')
router.register('wishlist', WishlistViewSet, basename='wishlist')
router.register('addresses', AddressViewSet, basename='addresses')

urlpatterns = [
    path('', include(router.urls)),
]
```

#### Step 5: Create Migration

```bash
python manage.py makemigrations eshop
python manage.py migrate eshop
```

### Verification

```bash
# 1. Check models compile
python -m py_compile domains/eshop/models.py

# 2. Check serializers compile
python -m py_compile domains/eshop/serializers.py

# 3. Check viewsets compile
python -m py_compile domains/eshop/viewsets.py

# 4. Run migrations
python manage.py makemigrations eshop
python manage.py migrate eshop

# 5. Test endpoints
curl -X GET http://localhost:8000/api/v1/eshop/cart/ -H "Authorization: Bearer <token>"
curl -X GET http://localhost:8000/api/v1/eshop/wishlist/ -H "Authorization: Bearer <token>"
curl -X GET http://localhost:8000/api/v1/eshop/addresses/ -H "Authorization: Bearer <token>"

# 6. Run OpenAPI schema generation
python manage.py spectacular --file openapi-schema.yml
```

---

## Task 3: Migrate `teams/kurostaff/` Imports

**Priority:** HIGH (Spec violation — "TO BE REMOVED")
**Effort:** 1-2 days
**Dependencies:** None (can run in parallel with Task 2)

### Current State

**Importers (20+ files):**
```bash
# Files importing from teams.kurostaff.views
users/api/viewsets.py:254
teams/financial.py:23
teams/views.py:132
teams/export_utils.py:23
teams/estimates.py:22
teams/service_requests.py:22
teams/employees.py:22
teams/split_views.py:35
teams/constants.py:23
teams/analytics.py:22
teams/products.py:22
teams/outward_invoices.py:23
teams/inward_invoices.py:22
teams/stock_audit.py:23
teams/infrastructure.py:22
domains/shared/viewsets.py:200
domains/products/viewsets.py:265,481,677,1068
domains/orders/viewsets.py:78,156,258,327,356,462,497,536,560
domains/vendors/viewsets.py:133
```

**Functions to Migrate:**
| Function | Current Location | Target Domain |
|----------|-----------------|---------------|
| `getCounters` | `teams/kurostaff/views.py:242` | `domains/shared/` |
| `ancode` | `teams/kurostaff/views.py:71` | `domains/shared/` |
| `numcode` | `teams/kurostaff/views.py:83` | `domains/shared/` |
| `getStates` | `teams/kurostaff/views.py:61` | `domains/shared/` |
| `getfinancialyear` | `teams/kurostaff/views.py:186` | `domains/shared/` |
| `getEstimates` | `teams/kurostaff/views.py:197` | `domains/orders/` |
| `creating_kgorders` | `teams/kurostaff/views.py:2434` | `domains/orders/` |
| `getTPOrders` | `teams/kurostaff/views.py:765` | `domains/orders/` |
| `getkgorders` | `teams/kurostaff/views.py:2155` | `domains/orders/` |
| `inventory_post` | `teams/kurostaff/views.py:725` | `domains/products/` |

### Implementation Plan

#### Step 1: Create Target Modules

**File:** `domains/shared/utils.py`

```python
"""Shared utility functions migrated from teams/kurostaff/views.py"""

def getCounters(dbname="", misctype="", db_name=None, divisions_list=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:242"""
    # Copy function body from teams/kurostaff/views.py
    ...

def ancode(num, digits=4):
    """Migrated from teams/kurostaff/views.py:71"""
    # Copy function body
    ...

def numcode(num, digits):
    """Migrated from teams/kurostaff/views.py:83"""
    # Copy function body
    ...

def getStates(db_name=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:61"""
    # Copy function body
    ...

def getfinancialyear(month=None, year=None):
    """Migrated from teams/kurostaff/views.py:186"""
    # Copy function body
    ...
```

**File:** `domains/orders/utils.py`

```python
"""Order utility functions migrated from teams/kurostaff/views.py"""

def getEstimates(estimate_no=None, version=None, limit=0, page=0, db=None, divisions_list=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:197"""
    # Copy function body
    ...

def creating_kgorders(orderData={}, userid="", db_name=None, divisions_list=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:2434"""
    # Copy function body
    ...

def getTPOrders(filters, limit=0, divisions_list=None, db_name=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:765"""
    # Copy function body
    ...

def getkgorders(filters, limit=0, specific_fields={}, db_name=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:2155"""
    # Copy function body
    ...
```

**File:** `domains/products/utils.py`

```python
"""Product utility functions migrated from teams/kurostaff/views.py"""

def inventory_post(request, inv_data, db_name=None, divisions_list=None, create_journal=None, bg=None, bg_code=None):
    """Migrated from teams/kurostaff/views.py:725"""
    # Copy function body
    ...
```

#### Step 2: Update All Importers

**Pattern:**
```python
# BEFORE
from teams.kurostaff.views import getCounters, ancode, numcode, getStates, getfinancialyear

# AFTER
from domains.shared.utils import getCounters, ancode, numcode, getStates, getfinancialyear
```

**Files to Update (19 files):**
1. `users/api/viewsets.py:254`
2. `teams/financial.py:23`
3. `teams/views.py:132`
4. `teams/export_utils.py:23`
5. `teams/estimates.py:22`
6. `teams/service_requests.py:22`
7. `teams/employees.py:22`
8. `teams/split_views.py:35`
9. `teams/constants.py:23`
10. `teams/analytics.py:22`
11. `teams/products.py:22`
12. `teams/outward_invoices.py:23`
13. `teams/inward_invoices.py:22`
14. `teams/stock_audit.py:23`
15. `teams/infrastructure.py:22`
16. `domains/shared/viewsets.py:200`
17. `domains/products/viewsets.py:265,481,677,1068`
18. `domains/orders/viewsets.py:78,156,258,327,356,462,497,536,560`
19. `domains/vendors/viewsets.py:133`

#### Step 3: Remove URL Registration

**File:** `teams/urls.py`

```python
# BEFORE (line 5)
from teams.kurostaff.views import tporders, kgorders, vendors, inwardinvoices

# AFTER
# Remove this line
```

#### Step 4: Delete `teams/kurostaff/` Package

```bash
rm -rf teams/kurostaff/
```

### Verification

```bash
# 1. Check no remaining imports from teams.kurostaff.views
grep -rn "from teams.kurostaff.views import\|import teams.kurostaff.views" --include="*.py" | grep -v __pycache__ | grep -v venv/
# Expected: 0 results (except tests)

# 2. Check kurostaff directory deleted
ls -la teams/kurostaff/
# Expected: No such file or directory

# 3. Run all tests
python manage.py test -v 2

# 4. Check URL routing
python manage.py show_urls | grep kurostaff
# Expected: 0 results
```

---

## Task 4: Remove 34 Dead Functions

**Priority:** HIGH (Maintenance burden)
**Effort:** 2-3 days
**Dependencies:** Task 3 (must complete first)

### Current State

**File:** `teams/kurostaff/views.py` (before migration)

**Total Functions:** 54
**Wired to URLs:** 20
**Dead Functions:** 34

### Dead Functions List

| Function | Line | Purpose | Status |
|----------|------|---------|--------|
| `num2words` | 89 | Number to words conversion | DEAD |
| `convert_number` | 105 | Number conversion | DEAD |
| `fetch_resources` | 112 | PDF resource fetching | DEAD |
| `add_page_numbers` | 117 | PDF page numbers | DEAD |
| `exporttopdf` | 159 | PDF export | DEAD |
| `states` | 229 | States endpoint (FBV) | ⚠️ WIRING ISSUE |
| `getVendors` | 268 | Vendor lookup | DEAD |
| `counters` | 279 | Counters endpoint (FBV) | ⚠️ WIRING ISSUE |
| `getbrands` | 323 | Brand lookup | DEAD |
| `brands` | 338 | Brands endpoint (FBV) | ⚠️ WIRING ISSUE |
| `vendors` | 376 | Vendors endpoint (FBV) | ⚠️ WIRING ISSUE |
| `inv_aggregate` | 511 | Inventory aggregation | DEAD |
| `invCalculations` | 541 | Inventory calculations (FBV) | ⚠️ WIRING ISSUE |
| `inventory` | 566 | Inventory endpoint (FBV) | ⚠️ WIRING ISSUE |
| `create_journalfunc` | 648 | Journal creation | DEAD |
| `create_inventory` | 681 | Inventory creation | DEAD |
| `outwardentry` | 961 | Outward entry | DEAD |
| `outward` | 1023 | Outward endpoint (FBV) | ⚠️ WIRING ISSUE |
| `paypendingInvoices` | 1106 | Payment processing | DEAD |
| `_parse_invoice_date` | 1160 | Date parsing helper | DEAD |
| `inwardinvoice_calce` | 1176 | Invoice calculation | DEAD |
| `getInwardCreditNotes` | 1458 | Credit note lookup | DEAD |
| `getInwardDebitNotes` | 1657 | Debit note lookup | DEAD |
| `emp_att_filters` | 1902 | Attendance filters | DEAD |
| `getting_attendance_data` | 1925 | Attendance data | DEAD |
| `dashboard_filters` | 2077 | Dashboard filters | DEAD |
| `_safe_int` | 2129 | Safe int conversion | DEAD |
| `_format_date_to_iso` | 2137 | Date formatting | DEAD |
| `creating_indent` | 2212 | Indent creation | DEAD |
| `indent` | 2270 | Indent endpoint (FBV) | ⚠️ WIRING ISSUE |
| `kgorders` | 2501 | KG orders endpoint (FBV) | ⚠️ WIRING ISSUE |
| `check_list` | 2673 | Check list endpoint | ⚠️ WIRING ISSUE |
| `buildgeneration` | 2736 | Build generation | DEAD |
| `prodgeneration` | 2765 | Product generation | DEAD |
| `orderconversion` | 2791 | Order conversion (FBV) | ⚠️ WIRING ISSUE |

**Note:** Functions marked "⚠️ WIRING ISSUE" are actually wired but use Function-Based View pattern instead of ViewSet.

### Implementation Plan

#### Step 1: Document Dead Functions

Create `teams/kurostaff/DEAD_FUNCTIONS.md`:

```markdown
# Dead Functions in teams/kurostaff/views.py

**Total Functions:** 54
**Wired to URLs:** 20
**Dead Functions:** 34

## Dead Utility Functions (Not Used Anywhere)

| Function | Line | Purpose |
|----------|------|---------|
| `num2words` | 89 | Number to words conversion |
| `convert_number` | 105 | Number conversion |
| `fetch_resources` | 112 | PDF resource fetching |
| `add_page_numbers` | 117 | PDF page numbers |
| `exporttopdf` | 159 | PDF export |
| `getVendors` | 268 | Vendor lookup |
| `inv_aggregate` | 511 | Inventory aggregation |
| `create_journalfunc` | 648 | Journal creation |
| `create_inventory` | 681 | Inventory creation |
| `outwardentry` | 961 | Outward entry |
| `paypendingInvoices` | 1106 | Payment processing |
| `_parse_invoice_date` | 1160 | Date parsing helper |
| `inwardinvoice_calce` | 1176 | Invoice calculation |
| `getInwardCreditNotes` | 1458 | Credit note lookup |
| `getInwardDebitNotes` | 1657 | Debit note lookup |
| `emp_att_filters` | 1902 | Attendance filters |
| `getting_attendance_data` | 1925 | Attendance data |
| `dashboard_filters` | 2077 | Dashboard filters |
| `_safe_int` | 2129 | Safe int conversion |
| `_format_date_to_iso` | 2137 | Date formatting |
| `creating_indent` | 2212 | Indent creation |
| `buildgeneration` | 2736 | Build generation |
| `prodgeneration` | 2765 | Product generation |

## Functions to Remove

Delete these 23 functions from `teams/kurostaff/views.py`.
```

#### Step 2: Remove Dead Functions

After Task 3 completes, remove the 23 dead utility functions from `teams/kurostaff/views.py`.

#### Step 3: Verify No Active References

```bash
# Check for active references to dead functions
grep -rn "num2words\|convert_number\|fetch_resources\|add_page_numbers\|exporttopdf" --include="*.py" | grep -v __pycache__ | grep -v venv/
# Expected: 0 results (except in this documentation)

# Check for active references to other dead functions
grep -rn "getVendors\|inv_aggregate\|create_journalfunc\|create_inventory\|outwardentry\|paypendingInvoices" --include="*.py" | grep -v __pycache__ | grep -v venv/
# Expected: 0 results (except in this documentation)
```

---

## Task 5: Document Domain Database Usage

**Priority:** MEDIUM (Documentation)
**Effort:** 2-3 hours
**Dependencies:** None (can run in parallel)

### Current State

Multiple domains use MongoDB without Django models. This is by design for legacy data, but needs documentation.

### Domains Using MongoDB (No Django Models)

| Domain | Location | MongoDB Collections | Rationale |
|--------|----------|---------------------|-----------|
| `domains/products/` | `domains/products/` | `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `presets` | Legacy gaming catalog |
| `domains/search/` | `domains/search/` | Various search indices | Performance |
| `domains/shared/` | `domains/shared/` | `misc` (counters, inventory metadata) | Legacy counter data |
| `domains/tournaments/` | `domains/tournaments/` | Tournament data | Legacy esports data |
| `domains/teams/` | `domains/teams/` | Employee attendance, inventory | Legacy HR data |
| `domains/vendors/` | `domains/vendors/` | Vendor data | Legacy vendor catalog |

### Domains Using PostgreSQL (Django Models)

| Domain | Location | Models |
|--------|----------|--------|
| `domains/orders/` | `domains/orders/` | `OrderCore`, `EstimateDetail`, `InStoreDetail`, `TPOrderDetail`, `ServiceDetail` |
| `domains/cafe_fnb/` | `domains/cafe_fnb/` | `Menu`, `Package`, `Order` |
| `domains/eshop/` | `domains/eshop/` | `Cart`, `Wishlist`, `Addresslist`, `Order` (after Task 2) |
| `users/` | `users/` | `CustomUser`, `Identity`, `Role`, `Permission`, `UserRole`, `UserPermission` |
| `tenant/` | `tenant/` | `BusinessGroup`, `Division`, `Branch`, `BankAccount` |

### Cafe Domain Architecture (By Design)

| Domain | Purpose | URL Mount |
|--------|---------|-----------|
| `domains/cafe_arcade/` | Arcade stations, hourly/time-based rental, station connections | `/api/v1/cafe/` |
| `domains/cafe_fnb/` | Food & Beverage orders, menu | `/api/v1/cafe-fnb/` |
| `domains/cafe/` | Shared cafe functions (billing consolidation, etc.) | `/api/v1/cafe/shared/` (Phase 9) |

**Status:** `domains/cafe/` is an empty shell reserved for Phase 9. Current cafe functionality is split between `cafe_arcade/` and `cafe_fnb/`.

### Documentation File

**Create:** `KUNGOS_DOMAIN_DATABASE_USAGE.md`

```markdown
# KungOS Domain Database Usage

**Date:** 2026-06-27
**Purpose:** Document which domains use PostgreSQL vs MongoDB

## PostgreSQL Domains (Django Models)

| Domain | Models | Notes |
|--------|--------|-------|
| `domains/orders/` | OrderCore, EstimateDetail, ... | Primary order storage |
| `domains/cafe_fnb/` | Menu, Package, Order | F&B orders |
| `domains/eshop/` | Cart, Wishlist, Addresslist, Order | E-commerce (Phase 4B) |
| `users/` | CustomUser, Identity, Role, ... | Auth and RBAC |
| `tenant/` | BusinessGroup, Division, Branch, ... | Multi-tenancy |

## MongoDB Domains (No Django Models)

| Domain | Collections | Rationale |
|--------|-------------|-----------|
| `domains/products/` | prods, builds, kgbuilds, ... | Legacy gaming catalog |
| `domains/search/` | Various | Performance |
| `domains/shared/` | misc | Legacy counter data |
| `domains/tournaments/` | Tournament data | Legacy esports |
| `domains/teams/` | Employee attendance, inventory | Legacy HR |
| `domains/vendors/` | Vendor data | Legacy vendor catalog |

## Cafe Domain Architecture

| Domain | Purpose | URL |
|--------|---------|-----|
| `domains/cafe_arcade/` | Arcade stations, hourly rental | `/api/v1/cafe/` |
| `domains/cafe_fnb/` | Food & Beverage orders | `/api/v1/cafe-fnb/` |
| `domains/cafe/` | Shared cafe functions (Phase 9) | `/api/v1/cafe/shared/` |

**Note:** `domains/cafe/` is an empty shell reserved for Phase 9. Current functionality is split between arcade and F&B.
```

---

## Execution Order

```
Day 1:
  Morning: Task 1 (Fix serializers) — 30 min
  Morning: Task 5 (Document domains) — 2-3 hours
  Afternoon: Task 2 (Implement EShop) — Steps 1-4

Day 2:
  Morning: Task 2 (Implement EShop) — Step 5 (migration), verification
  Afternoon: Task 3 (Migrate kurostaff imports) — Steps 1-3

Day 3:
  Morning: Task 3 (Migrate kurostaff imports) — Step 4 (delete package), verification
  Afternoon: Task 4 (Remove dead functions) — Steps 1-2

Day 4-5:
  Buffer for testing, debugging, and documentation
```

---

## Verification Checklist

- [ ] `division` → `div_code` fixed in `users/api/rbac_serializers.py`
- [ ] OpenAPI schema generates without errors
- [ ] EShop models created and migrated
- [ ] EShop serializers created
- [ ] EShop viewsets created
- [ ] EShop URLs registered
- [ ] All 20+ kurostaff imports migrated to domain modules
- [ ] `teams/kurostaff/` package deleted
- [ ] `teams/kurostaff/urls.py` removed from `teams/urls.py`
- [ ] 23 dead functions removed from `teams/kurostaff/views.py`
- [ ] No remaining references to dead functions
- [ ] Domain database usage documented
- [ ] All tests passing
- [ ] No URL routing errors

---

## Risk Mitigation

### Risk: EShop Migration Fails
**Mitigation:** Keep `domains/eshop/urls.py` with commented-out viewsets until fully tested

### Risk: kurostaff Migration Breaks 20+ Files
**Mitigation:** 
1. Create target modules first
2. Update one file at a time
3. Run tests after each file
4. Keep `teams/kurostaff/` as fallback until all imports verified

### Risk: Dead Functions Still Referenced
**Mitigation:**
1. Run grep before deletion
2. Document all dead functions
3. Verify no active references after deletion

---

## Success Criteria

1. **OpenAPI works:** `python manage.py spectacular --file openapi-schema.yml` succeeds
2. **EShop endpoints work:** All 16 e-commerce endpoints return valid responses
3. **No kurostaff imports:** 0 files import from `teams.kurostaff.views`
4. **No dead functions:** 23 dead functions removed, 0 active references
5. **Documentation complete:** Domain database usage documented

---

**Handoff prepared:** 2026-06-27
**Ready for execution:** Yes
**Next step:** Begin Task 1
