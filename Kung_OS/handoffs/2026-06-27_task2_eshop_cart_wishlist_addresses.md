# Task 2: Implement EShop Cart/Wishlist/Addresses — Execution Handoff

**Date:** 2026-06-27  
**Project:** `kteam-dj-chief`  
**Phase:** Phase 1 — Core Spec Alignment  
**Task:** Task 2 of 5  
**Priority:** CRITICAL (Blocks E-Commerce)  
**Effort:** 1 day  
**Dependencies:** Task 1 (Fix `division` → `div_code` in Serializers) ✅ Complete

---

## Overview

Implement e-commerce cart, wishlist, and addresses functionality by migrating from the legacy `kuro-gaming-dj-backend` to the new `domains/eshop/` package in `kteam-dj-chief`.

**Current Status:** Models, serializers, viewsets, URLs, and migrations are **already created** in `domains/eshop/`. This task focuses on:
1. Verifying the implementation against the legacy code
2. Applying migrations
3. Integration testing
4. Fixing any gaps or issues

---

## Legacy Backend Reference

**Location:** `/home/chief/Coding-Projects/kuro-gaming-dj-backend/`

### Legacy Models (`accounts/models.py`)

```python
class Cart(models.Model):
    userid = ForeignKey(CustomUser)
    cartid = CharField(max_length=200, unique=True, primary_key=True)
    productid = CharField(max_length=150)
    category = CharField(max_length=150)
    quantity = IntegerField(default=1)

class Wishlist(models.Model):
    userid = ForeignKey(CustomUser)
    wishid = CharField(max_length=200, unique=True, primary_key=True)
    productid = CharField(max_length=150)
    category = CharField(max_length=150)
    sfl = BooleanField(default=False)

class Addresslist(models.Model):
    userid = ForeignKey(CustomUser)
    addressid = CharField(max_length=200, unique=True, primary_key=True)
    fullname = CharField(max_length=150)
    phone = PhoneNumberField()
    altphone = PhoneNumberField()
    pincode = CharField(max_length=6)
    addressline1 = CharField(max_length=150)
    addressline2 = CharField(max_length=150, blank=True)
    landmark = CharField(max_length=150, blank=True)
    city = CharField(max_length=150)
    state = CharField(max_length=150)
    gstin = CharField(max_length=150, blank=True)
    pan = CharField(max_length=150, blank=True)
    is_default = BooleanField(default=False)
    is_used = BooleanField(default=False)
    delete_flag = BooleanField(default=False)
```

### Legacy Views (`accounts/views.py`)

| Endpoint | Method | Function |
|----------|--------|----------|
| `/cartitems` | GET/POST/DELETE | `cartItems` |
| `/wishlist` | GET/POST/DELETE | `wishList` |
| `/addresslist` | GET/POST/DELETE | `addressList` |

**Key Behaviors:**
- **Cart:** Add/update/remove items, calculate totals, check stock limits
- **Wishlist:** Add/remove items, deduplicate by (userid, productid)
- **Addresses:** CRUD with immutable edit pattern (clone-on-edit for used addresses)
- **Authentication:** `TokenAuthentication` (DRF Knox)
- **Response Format:** JSON with product details joined from MongoDB

---

## New Implementation (`domains/eshop/`)

### Models (`domains/eshop/models.py`)

```python
class Cart(models.Model):
    identity = ForeignKey(Identity)  # → users_identity.identity_id
    productid = CharField(max_length=50)
    category = CharField(max_length=50, blank=True, default='')
    quantity = PositiveIntegerField(default=1)
    bg_code = CharField(max_length=10, blank=True, default='')

class Wishlist(models.Model):
    identity = ForeignKey(Identity)
    productid = CharField(max_length=50)
    bg_code = CharField(max_length=10, blank=True, default='')
    # UniqueConstraint(identity, productid)

class Address(models.Model):
    identity = ForeignKey(Identity)
    address_type = CharField(choices=[bill, ship, registered, office, warehouse])
    address_line1 = CharField(max_length=150)
    address_line2 = CharField(max_length=150, blank=True)
    city = CharField(max_length=150)
    state = CharField(max_length=150)
    country = CharField(max_length=100, default='India')
    pincode = CharField(max_length=10)
    phone_no = CharField(max_length=20, blank=True)
    is_default = BooleanField(default=False)
    is_used = BooleanField(default=False)
    delete_flag = BooleanField(default=False)
    bg_code = CharField(max_length=10, blank=True, default='')
```

### Key Differences from Legacy

| Aspect | Legacy | New |
|--------|--------|-----|
| **User Reference** | `userid` (CharField) | `identity` (FK → Identity) |
| **Primary Key** | UUID (cartid, wishid, addressid) | Django AutoField (`id`) |
| **Tenant Scoping** | None | `bg_code` field on all models |
| **Address Type** | None | `address_type` choices |
| **Phone** | `PhoneNumberField` | `phone_no` (CharField) |
| **Gstin/Pan** | Yes | No (add if needed) |
| **Landmark** | Yes | No (add if needed) |
| **Address2** | `addressline2` | `address_line2` |

### Serializers (`domains/eshop/serializers.py`)

- `CartSerializer` — CRUD with auto-populate identity/bg_code
- `WishlistSerializer` — CRUD with auto-populate identity/bg_code
- `AddressSerializer` — CRUD with **immutable edit pattern** (clone-on-edit for used addresses)

### ViewSets (`domains/eshop/viewsets.py`)

- `CartViewSet` — ModelViewSet with queryset filtering
- `WishlistViewSet` — ModelViewSet with destroy override
- `AddressViewSet` — ModelViewSet with perform_update override for clone-on-edit

### URLs (`domains/eshop/urls.py`)

```python
router = DefaultRouter()
router.register('cart', CartViewSet, basename='cart')
router.register('wishlist', WishlistViewSet, basename='wishlist')
router.register('addresses', AddressViewSet, basename='addresses')
```

**Registered in:** `backend/urls.py` line 25:
```python
path('eshop/', include('domains.eshop.urls')),
```

---

## Implementation Checklist

### Phase 1: Verification (30 min)

- [ ] Review `domains/eshop/models.py` against legacy `accounts/models.py`
- [ ] Review `domains/eshop/serializers.py` against legacy `accounts/serializers.py`
- [ ] Review `domains/eshop/viewsets.py` against legacy `accounts/views.py`
- [ ] Identify gaps (fields missing, behaviors not implemented)
- [ ] Document decisions for any intentional deviations

### Phase 2: Migration Application (15 min)

- [ ] Apply migration: `python3 manage.py migrate domains_eshop`
- [ ] Verify tables created: `eshop_cart`, `eshop_wishlist`, `eshop_addresses`
- [ ] Check indexes and constraints

### Phase 3: Gap Fixing (30 min)

Based on target spec, most gaps are **intentional** (not bugs). Only fix if implementation deviates from spec:

- [ ] Verify models match target spec §3.1 (Cart, Wishlist) and §4.2 (Address)
- [ ] Verify serializers exclude non-spec fields (gstin, pan, landmark, etc.)
- [ ] Verify viewsets do NOT implement stock checking or product detail joining
- [ ] Verify phone_no is CharField (not PhoneNumberField)
- [ ] Update URL patterns if needed (currently matches spec §8.1)

### Phase 4: Testing (1 hour)

- [ ] Test cart endpoints (GET, POST, PUT, DELETE)
- [ ] Test wishlist endpoints (GET, POST, DELETE)
- [ ] Test address endpoints (GET, POST, PUT, DELETE)
- [ ] Test immutable edit pattern (edit used address → clone)
- [ ] Test tenant isolation (bg_code filtering)
- [ ] Test identity scoping (user can only see own data)

### Phase 5: Documentation (30 min)

- [ ] Update OpenAPI schema (run `python3 manage.py spectacular`)
- [ ] Document API endpoints in wiki
- [ ] Document data model in wiki
- [ ] Add examples for each endpoint

---

## Acceptance Criteria

- [ ] All three viewsets (Cart, Wishlist, Address) respond correctly
- [ ] Cart stores `productid` as string binding (no product detail joining)
- [ ] Cart does NOT check stock (stock validation at checkout per spec)
- [ ] Wishlist deduplicates by (identity, productid)
- [ ] Addresses use immutable edit pattern (clone-on-edit for used addresses)
- [ ] Addresses schema matches target spec (minimal Phase 1 schema)
- [ ] Phone is CharField (frontend validation per spec)
- [ ] Cart does NOT calculate totals (frontend responsibility per spec)
- [ ] Tenant isolation works (bg_code filtering)
- [ ] Identity scoping works (user can only see own data)
- [ ] Migrations applied successfully
- [ ] OpenAPI schema generates without errors
- [ ] All endpoints tested with Postman/curl

---

## Open Questions — RESOLVED by Target Spec

All open questions have been resolved by the [E-Commerce Domain Specification](/home/chief/llm-wiki/Kung_OS/specs/domain_specs/ecommerce_spec.md):

### 1. Product Detail Joining ✅ RESOLVED
**Spec §3.1, §8.1:** Cart stores `productid` as "String binding (Mongo catalog)". The API contract shows products with just `productid`, `name`, `quantity`, `price` at the **order level**, not cart level.

**Decision:** Cart stores only `productid` + `category`. Product details (title, images, price) are:
- Resolved by the **frontend** using `/api/v1/eshop/products/{id}` endpoint
- Snapshot at **order creation** time (stored in `orders_core.products` as JSONB)

**Rationale:** Separates cart data from catalog data. Enables catalog updates without cart edits. Reduces cart payload size.

**Implementation:** Cart viewset does NOT join product details. Add comment in serializer documenting this design decision.

---

### 2. Stock Checking ✅ RESOLVED
**Spec §3.1:** Cart model has no stock-related fields. The spec does not mention stock checking for cart operations.

**Decision:** Stock checking belongs at **order creation** (checkout), not cart management. Cart is a holding area, not a purchase.

**Rationale:** Cart items can exceed stock limits (customer may not purchase all items). Stock validation happens at checkout when order is placed.

**Implementation:** Cart viewset does NOT check stock. Add note in API docs that quantities are not validated against stock at cart level.

---

### 3. Missing Address Fields ✅ RESOLVED
**Spec §4.2 — Address Schema (TARGET):**

| Field | In Spec? | Notes |
|-------|----------|-------|
| `gstin` | ❌ No | Not in target schema |
| `pan` | ❌ No | Not in target schema |
| `landmark` | ❌ No | Not in target schema |
| `altphone` | ❌ No | Not in target schema |
| `address_type` | ✅ Yes | `bill`/`ship`/`registered`/`office`/`warehouse` |
| `country` | ✅ Yes | Default `India` |

**Decision:** Follow the target spec exactly. The target schema is intentionally minimal for Phase 1, covering 95% of use cases.

**Rationale:** Core fields (address, city, state, pincode, phone) handle most shipping scenarios. Fields like gstin/pan are B2B-specific and can be added in Phase 2 if needed.

**Implementation:** Current models match target spec. No changes needed.

---

### 4. Phone Validation ✅ RESOLVED
**Spec §4.2:** `phone_no` is `varchar` with no mention of `PhoneNumberField`.

**Decision:** Use `CharField(max_length=20)` with no special validation. Phone validation is the frontend's responsibility.

**Rationale:** Pragmatic approach. Phone format validation is frontend responsibility. Backend can add validation later if needed (e.g., for SMS notifications).

**Implementation:** Current model is correct (`phone_no = CharField(max_length=20, blank=True, default='')`). No changes needed.

---

### 5. Cart Total Calculation ✅ RESOLVED
**Spec §8.1 — API Contract:** Cart endpoints return cart items, but there's no `carttotal` field in the response contract.

**Decision:** Cart total is calculated by the **frontend** using item prices from product catalog. Not part of cart API response.

**Rationale:** Cart total requires product pricing (Phase 3b). Phase 1 focuses on data management. Frontend calculates total from product catalog API.

**Implementation:** Cart viewset/serializer does NOT calculate totals. Add comment documenting this design decision.

---

## Summary of Decisions

| Aspect | Legacy Approach | Target Spec Decision | Rationale |
|--------|----------------|---------------------|-----------| **Separated data from catalog.** Cart stores `productid` as string binding to MongoDB. Frontend resolves details via `/api/v1/eshop/products/{id}`. Reduces cart payload, enables catalog updates without cart edits. |
| **Stock checking** | Validated in cart viewset | Validated at **order creation** (checkout) | Cart is a holding area, not a purchase. Stock validation belongs at checkout when order is placed. |
| **Address schema** | gstin, pan, landmark, altphone | Minimal schema for Phase 1 | Phased delivery. Core fields (address, city, state, pincode, phone) cover 95% of use cases. Add gstin/pan for B2B if needed in Phase 2. |
| **Phone validation** | Backend PhoneNumberField | Frontend validation (CharField) | Pragmatic. Phone format validation is frontend responsibility. Backend can add validation later if needed. |
| **Cart total** | Calculated in viewset | Frontend responsibility | Cart total requires product pricing (Phase 3b). Phase 1 focuses on data management. Frontend calculates total from product catalog. |

**Design Philosophy:** Phase 1 = **data management** (CRUD for cart, wishlist, addresses). Phase 3 = **business logic** (pricing, stock, checkout). This separation enables phased delivery and keeps Phase 1 simple.

---

## Files to Modify

| File | Action |
|------|--------|
| `domains/eshop/models.py` | Review and fix gaps |
| `domains/eshop/serializers.py` | Review and fix gaps |
| `domains/eshop/viewsets.py` | Review and fix gaps |
| `domains/eshop/urls.py` | Review and fix gaps |
| `domains/eshop/migrations/0001_initial.py` | Regenerate if models change |
| `backend/settings.py` | Verify `domains.eshop` registered |
| `backend/urls.py` | Verify eshop URLs included |

---

## Legacy Code Reference

**Legacy accounts/views.py:** `/home/chief/Coding-Projects/kuro-gaming-dj-backend/accounts/views.py`  
**Legacy accounts/models.py:** `/home/chief/Coding-Projects/kuro-gaming-dj-backend/accounts/models.py`  
**Legacy accounts/serializers.py:** `/home/chief/Coding-Projects/kuro-gaming-dj-backend/accounts/serializers.py`  
**Legacy accounts/urls.py:** `/home/chief/Coding-Projects/kuro-gaming-dj-backend/accounts/urls.py`

---

## Notes

- The new implementation uses `Identity` model instead of `CustomUser` (spec alignment)
- The new implementation uses `bg_code` for tenant scoping (spec alignment)
- The new implementation uses Django AutoField instead of UUID primary keys (simpler)
- The immutable edit pattern is preserved from legacy (clone-on-edit for used addresses)
- Product detail joining is intentionally NOT implemented (to be done by frontend or separate endpoint)

---

**Ready for execution.**
