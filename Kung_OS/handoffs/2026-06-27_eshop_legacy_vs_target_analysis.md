# E-Shop Legacy vs Target Spec — Detailed Gap Analysis

**Date:** 2026-06-27  
**Purpose:** Compare legacy `kuro-gaming-dj-backend` implementation against target `ecommerce_spec.md` to identify what should be included in Phase 1

---

## 1. Cart Implementation

### Legacy (`accounts/views.py` → `getCart()`)

**Response Structure:**
```json
{
    "products": [
        {
            "productid": "KCPB2400000001",
            "category": "custombuilds",
            "quantity": 1,
            "title": "Custom PC Build XYZ",
            "prod_url": "/product/...",
            "img_url": ["image1.jpg"],
            "status": "In Stock",
            "max_limit": 5,
            "price": 42000.00,
            "components": [...]
        }
    ],
    "carttotal": 42000.00
}
```

**Key Behaviors:**
1. **Product Detail Joining:** Joins MongoDB product catalog for title, images, price, status, components
2. **Stock Checking:** 
   - If `status == "In Stock"` and category is not "build"/"custombuilds":
     - Sets `max_limit` from MongoDB `quantity` field
     - If cart quantity > stock, caps quantity to stock limit
3. **Cart Total:** Sums `price × quantity` for all items
4. **Response:** Returns `{products: [...], carttotal: number}`

### Target Spec (`ecommerce_spec.md` §3.1)

**Cart Model:**
| Field | Type | Notes |
|-------|------|-------|
| `id` | bigint | PRIMARY KEY |
| `user_id` | varchar | FK → `users_identity.identity_id` |
| `productid` | varchar | String binding (Mongo catalog) |
| `category` | varchar | Product category |
| `quantity` | integer | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**API Contract (§8.1):**
- `GET /api/v1/eshop/cart` — Current user cart
- `POST /api/v1/eshop/cart` — Add to cart
- `PATCH /api/v1/eshop/cart/{id}` — Update cart item
- `DELETE /api/v1/eshop/cart/{id}` — Remove from cart

**No mention of:** stock checking, cart total, product detail joining in cart endpoints

### Gap Analysis

| Feature | Legacy | Target Spec | Recommendation |
|---------|--------|-------------|----------------|
| **Product details** | Joined in GET response | Not mentioned | **Include in Phase 1** — Cart is useless without product info (title, image, price) |
| **Stock checking** | Caps quantity to stock limit | Not mentioned | **Include in Phase 1** — Prevents ordering out-of-stock items |
| **Cart total** | Calculated and returned | Not mentioned | **Include in Phase 1** — Essential for UX (show total before checkout) |
| **Response structure** | `{products: [...], carttotal: number}` | Not specified | **Adapt legacy structure** — Proven UX pattern |

**Recommendation:** Refactor legacy `getCart()` to work with new architecture:
- Replace `userid` with `identity_id`
- Replace MongoDB product lookup with new product catalog API (Phase 3b)
- Keep stock checking logic (adapt to new schema)
- Keep cart total calculation
- Return enriched product data in GET response

---

## 2. Wishlist Implementation

### Legacy (`accounts/views.py` → `getWishlist()`)

**Response Structure:**
```json
[
    {
        "productid": "KCPB2400000001",
        "category": "custombuilds",
        "title": "Custom PC Build XYZ",
        "prod_url": "/product/...",
        "img_url": ["image1.jpg"],
        "status": "In Stock",
        "price": 42000.00,
        "components": [...]
    }
]
```

**Key Behaviors:**
1. **Product Detail Joining:** Same as cart — joins MongoDB for title, images, price, status, components
2. **No stock checking** (wishlist is just a save-for-later list)
3. **No total calculation** (wishlist items may not be purchased)

### Target Spec (`ecommerce_spec.md` §3.2)

**Wishlist Model:**
| Field | Type | Notes |
|-------|------|-------|
| `id` | bigint | PRIMARY KEY |
| `user_id` | varchar | FK → `users_identity.identity_id` |
| `productid` | varchar | String binding (Mongo catalog) |
| `created_at` | timestamptz | |

**No mention of:** product detail joining, stock checking, total calculation

### Gap Analysis

| Feature | Legacy | Target Spec | Recommendation |
|---------|--------|-------------|----------------|
| **Product details** | Joined in GET response | Not mentioned | **Include in Phase 1** — Wishlist is useless without product info |
| **Stock status** | Included (`In Stock`/`Out of Stock`) | Not mentioned | **Include in Phase 1** — Shows availability |

**Recommendation:** Refactor legacy `getWishlist()` to work with new architecture.

---

## 3. Address Implementation

### Legacy (`accounts/models.py` → `Addresslist`)

**Full Schema:**
```python
class Addresslist(models.Model):
    userid = ForeignKey(CustomUser)
    addressid = CharField(max_length=200, unique=True, primary_key=True)  # UUID
    created_at = DateTimeField
    updated_at = DateTimeField
    companyname = CharField(max_length=150, blank=True, null=True)
    fullname = CharField(max_length=150)
    phone = PhoneNumberField()
    altphone = PhoneNumberField(blank=True)
    pincode = CharField(max_length=6)
    addressline1 = CharField(max_length=150)
    addressline2 = CharField(max_length=150, blank=True)
    landmark = CharField(max_length=150, blank=True)
    city = CharField(max_length=150)
    state = CharField(max_length=150)
    gstin = CharField(max_length=150, blank=True, null=True)
    pan = CharField(max_length=150, blank=True, null=True)
    is_default = BooleanField(default=False)
    is_used = BooleanField(default=False)
    delete_flag = BooleanField(default=False)
```

**Legacy Views (`addressList`):**
- **GET:** Returns all addresses with `getAddresses()` helper
- **POST (create):**
  - If `is_default=True`, normalize existing addresses (set all to `is_default=False`)
  - Create new address with UUID
- **POST (update):**
  - If address `is_used=True`: clone new address, mark old as `delete_flag=True`
  - If `is_default=True`, normalize existing addresses
  - Otherwise: in-place update
- **DELETE:**
  - If `is_used=True`: mark as `delete_flag=True` (soft delete)
  - Otherwise: hard delete

### Target Spec (`ecommerce_spec.md` §4.2)

**Address Schema (TARGET):**
| Field | Type | Notes |
|-------|------|-------|
| `id` | bigint | PRIMARY KEY |
| `identity_id` | char(20) | FK → `users_identity.identity_id` |
| `address_type` | varchar | `bill`/`ship`/`registered`/`office`/`warehouse` |
| `address_line1` | varchar(150) | |
| `address_line2` | varchar(150) | NULL |
| `city` | varchar(150) | |
| `state` | varchar(150) | |
| `country` | varchar(100) | Default `India` |
| `pincode` | varchar(10) | |
| `phone_no` | varchar | |
| `is_default` | boolean | |
| `is_used` | boolean | Default `false` |
| `delete_flag` | boolean | Default `false` |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### Gap Analysis — Address Schema

| Field | Legacy | Target Spec | Missing? | Recommendation |
|-------|--------|-------------|----------|----------------|
| `companyname` | ✅ Yes | ❌ No | **YES** | **Include** — B2B orders need company name |
| `fullname` | ✅ Yes | ❌ No | **YES** | **Include** — Contact person name |
| `phone` | ✅ Yes (PhoneNumberField) | `phone_no` (varchar) | **YES** | **Include** — Primary contact phone |
| `altphone` | ✅ Yes (PhoneNumberField) | ❌ No | **YES** | **Include** — Alternate contact phone |
| `landmark` | ✅ Yes | ❌ No | **YES** | **Include** — Helpful for delivery |
| `gstin` | ✅ Yes | ❌ No | **YES** | **Include** — B2B tax invoice |
| `pan` | ✅ Yes | ❌ No | **YES** | **Include** — B2B tax invoice |
| `address_type` | ❌ No | ✅ Yes | — | **Keep** — New feature, good addition |
| `country` | ❌ No | ✅ Yes (default India) | — | **Keep** — Good for future intl. |
| `pincode` | 6 chars | 10 chars | — | **Use 10** — More flexible |
| `is_default` | ✅ Yes | ✅ Yes | — | **Keep** |
| `is_used` | ✅ Yes | ✅ Yes | — | **Keep** |
| `delete_flag` | ✅ Yes | ✅ Yes | — | **Keep** |

**Missing Fields Summary:**
- `companyname` — B2B company name
- `fullname` — Contact person
- `phone` — Primary phone (legacy uses PhoneNumberField)
- `altphone` — Alternate phone
- `landmark` — Delivery landmark
- `gstin` — GST number (B2B tax)
- `pan` — PAN number (B2B tax)

### Gap Analysis — Address Behaviors

| Behavior | Legacy | Target Spec | Missing? | Recommendation |
|----------|--------|-------------|----------|----------------|
| **Immutable edit** | ✅ Clone-on-edit for used addresses | ✅ Yes (§4.1, §10.2) | — | **Keep** |
| **Default normalization** | ✅ Set all others to `is_default=False` when new default | Not mentioned | **YES** | **Include** — Prevents multiple defaults |
| **Soft delete for used** | ✅ Mark `delete_flag=True` instead of hard delete | ✅ Yes (§4.1) | — | **Keep** |

---

## 4. Recommendations

### Cart & Wishlist

**Refactor legacy implementation** (don't strip features):
1. Replace `userid` with `identity_id`
2. Replace MongoDB product lookup with new product catalog API
3. Keep product detail joining (title, images, price, status)
4. Keep stock checking (cap quantity to stock limit)
5. Keep cart total calculation
6. Adapt response structure to DRF conventions

### Address

**Extend target schema** to include missing fields:
```python
class Address(models.Model):
    # ... existing fields ...
    companyname = CharField(max_length=150, blank=True, default='')
    fullname = CharField(max_length=150)
    phone = CharField(max_length=20)  # or PhoneNumberField
    altphone = CharField(max_length=20, blank=True, default='')
    landmark = CharField(max_length=150, blank=True, default='')
    gstin = CharField(max_length=150, blank=True, default='')
    pan = CharField(max_length=150, blank=True, default='')
```

**Implement default normalization** in viewset:
```python
def perform_create(self, serializer):
    if serializer.validated_data.get('is_default'):
        Address.objects.filter(
            identity=self.request.user.identity_id,
            bg_code=self.request.bg_code,
        ).update(is_default=False)
    serializer.save(...)
```

---

## 5. Updated Implementation Checklist

### Cart ViewSet
- [ ] Refactor `getCart()` to join product details
- [ ] Refactor stock checking logic
- [ ] Calculate cart total in GET response
- [ ] Return `{products: [...], carttotal: number}` structure

### Wishlist ViewSet
- [ ] Refactor `getWishlist()` to join product details
- [ ] Include product status (In Stock/Out of Stock)

### Address ViewSet
- [ ] Extend model with missing fields (companyname, fullname, phone, altphone, landmark, gstin, pan)
- [ ] Update serializer to include all fields
- [ ] Implement default normalization (only one default per user)
- [ ] Keep immutable edit pattern (clone-on-edit for used addresses)
- [ ] Keep soft delete for used addresses

### Migrations
- [ ] Regenerate migration for Address model changes
- [ ] Apply migration

---

**Next Step:** Awaiting decision on whether to:
1. Refactor legacy cart/wishlist implementation (include stock checking, product details, totals)
2. Extend address schema with missing fields
3. Proceed with current minimal implementation (as per spec)
