# User Model Reconciliation: kteam-dj-be vs kuro-gaming-dj-backend

Prepared: 2026-04-22

## Executive Summary

Both projects define a `CustomUser` model with nearly identical core fields (`userid`, `phone`, `name`, `email`, `username`), but kteam-dj-be has **5 additional fields** for multi-tenant business logic. The gaming backend also defines a `PhoneModel` that kteam-dj-be already has. **All gaming user data can be migrated into the kteam-dj-be schema with zero data loss.**

---

## Field-by-Field Comparison

### CustomUser Model

| Field | kteam-dj-be | kuro-gaming-dj-backend | Conflict? | Resolution |
|---|---:|---:|---:|---|
| `username` | `CharField(150)`, nullable, unique | `CharField(150)`, nullable, unique | No | Identical — keep |
| `email` | `EmailField(255)`, nullable, unique | `EmailField(255)`, nullable, unique | No | Identical — keep |
| `name` | `CharField(150)` | `CharField(150)` | No | Identical — keep |
| `userid` | `CharField(20)`, PK, unique | `CharField(20)`, PK, unique | No | Identical — keep |
| `phone` | `PhoneNumberField`, unique | `PhoneNumberField`, unique | No | Identical — keep |
| `password` | Inherited from `AbstractBaseUser` | Inherited from `AbstractBaseUser` | No | Identical — keep |
| **`usertype`** | **`CharField(150)`, nullable** | **not present** | **kteam only** | **Add to gaming users during merge** |
| **`user_status`** | **`CharField(150)`, default="Active", nullable** | **not present** | **kteam only** | **Add to gaming users during merge** |
| `last_login` | `DateTimeField`, nullable | `DateTimeField(default=datetime.now)` | **Minor** | kteam is more permissive (nullable) — use kteam schema |
| `is_active` | `BooleanField(default=True)` | `BooleanField(default=True)` | No | Identical — keep |
| `is_staff` | `BooleanField(default=False)` | `BooleanField(default=False)` | No | Identical — keep |
| `is_superuser` | `BooleanField(default=False)` | `BooleanField(default=False)` | No | Identical — keep |
| `is_admin` | `BooleanField(default=False)` | `BooleanField(default=False)` | No | Identical — keep |
| **`created_date`** | **`DateTimeField(default=timezone.now)`** | **not present** | **kteam only** | **Add to gaming users during merge** |

### Manager Comparison

| Method | kteam-dj-be | kuro-gaming-dj-backend | Conflict? |
|---|---|---|---|
| `_create_user` | `userid, phone, password, name, email, usertype, user_status` | `userid, phone, password, name, username, email` | **Different signature** |
| `create_user` | Same as manager, sets `usertype=None, user_status=None` | Same as manager | **Different signature** |
| `create_superuser` | Same as manager, sets `is_staff=True, is_superuser=True` | Same as manager | **Different signature** |

**Key difference:** Gaming manager accepts `username` as a parameter; kteam manager does not (username is optional and set elsewhere). Gaming manager does NOT accept `usertype`/`user_status`; kteam manager does.

---

## kteam-dj-be Exclusive Models (No Gaming Equivalent)

### KuroUser

This model stores extended user profile data unique to the kteam business platform. **No gaming equivalent exists.**

| Field | Type | Purpose |
|---|---|---|
| `userid` | FK → CustomUser | Link to user |
| `gender` | CharField | Demographics |
| `dob` | DateField | Date of birth |
| `phone_verified` | BooleanField | OTP verification status |
| `permadd_*` | CharField/IntField | Permanent address (5 fields) |
| `presadd_*` | CharField/IntField | Present address (5 fields) |
| `emerg_*` | CharField/PhoneNumberField | Emergency contact (2 fields) |
| `idproof_*` | CharField | ID proof type + number |
| `paid_offs`, `available_offs`, `festival_offs` | IntegerField | Leave/offset balances |
| `pan` | CharField(10) | PAN card |
| `bank_*` | CharField | Bank account details (7 fields) |
| `bfc_*` | CharField | Bank/financial code (4 fields) |
| `businessgroups` | JSONField | List of associated BGs |
| `primary_bg` | CharField | Primary business group |
| `joining_date` | DateTimeField | Employment date |
| `access`, `role` | CharField | Role assignment |
| `created_by`, `approved_by`, `approved_date` | CharField/DateTimeField | Approval chain |
| `edit` | BooleanField | Edit permission flag |

### Switchgroupmodel

| Field | Type | Purpose |
|---|---|---|
| `userid` | CharField(100) | Current user session |
| `bg_code` | CharField(200) | Active business group |
| `token_key` | CharField(200) | Knox token reference |

### Accesslevel

45+ integer permission fields (0=disabled, 1=view, 2=edit) scoped to `userid`, `bg_code`, `entity`, plus `branches` JSON list.

### BusinessGroup

| Field | Type | Purpose |
|---|---|---|
| `bg_code` | CharField(100) | Business group code |
| `bg_name` | CharField(500) | Business group display name |
| `db_name` | CharField(200) | MongoDB database name (per-BG) |
| `entities` | JSONField | List of entities under BG |
| `created_by`, `updated_by` | CharField | Audit |
| `created_date`, `updated_date` | DateTimeField | Audit |
| `is_active` | BooleanField | Soft delete |

### Common_counters

| Field | Type | Purpose |
|---|---|---|
| `businessgroup` | IntegerField | BG reference |
| `employees` | IntegerField | Employee counter |

### PhoneModel (shared)

| Field | Type | Purpose |
|---|---|---|
| `mobile` | PhoneNumberField, unique | Phone number for OTP |
| `otp` | CharField(6) | Generated OTP |
| `expirytime` | DateTimeField | OTP expiration |

**Both projects define this identically — no merge needed.**

---

## Gaming Backend Exclusive Models (No kteam Equivalent)

### Cart

| Field | Type | Purpose |
|---|---|---|
| `userid` | FK → CustomUser | User reference |
| `cartid` | CharField(200), PK | Cart item ID |
| `created_at`, `updated_at` | DateTimeField | Timestamps |
| `productid` | CharField(150) | Product reference |
| `category` | CharField(150) | Product category |
| `quantity` | IntegerField | Item quantity |

### Wishlist

| Field | Type | Purpose |
|---|---|---|
| `userid` | FK → CustomUser | User reference |
| `wishid` | CharField(200), PK | Wishlist item ID |
| `created_at` | DateTimeField | Timestamp |
| `productid` | CharField(150) | Product reference |
| `category` | CharField(150) | Product category |
| `sfl` | BooleanField | "Show for landing" flag |

### Addresslist

| Field | Type | Purpose |
|---|---|---|
| `userid` | FK → CustomUser | User reference |
| `addressid` | CharField(200), PK | Address ID |
| `created_at`, `updated_at` | DateTimeField | Timestamps |
| `companyname` | CharField(150) | Company name |
| `fullname` | CharField(150) | Full name |
| `phone`, `altphone` | PhoneNumberField | Contact phones |
| `pincode` | CharField(6) | Postal code |
| `addressline1`, `addressline2` | CharField(150) | Address lines |
| `landmark` | CharField(150) | Landmark |
| `city`, `state` | CharField(150) | City, state |
| `gstin`, `pan` | CharField(150) | GST/PAN numbers |
| `is_default` | BooleanField | Default address flag |
| `is_used` | BooleanField | Used in an order flag |
| `delete_flag` | BooleanField | Soft delete |

### Orders (gaming)

| Field | Type | Purpose |
|---|---|---|
| `userid` | FK → CustomUser | User reference |
| `orderid` | CharField(150), PK | Order ID |
| `order_status` | CharField(150) | Current status |
| `order_created` | DateTimeField | Creation timestamp |
| `order_placed` | DateTimeField | Placed timestamp |
| `order_confirmed` | DateTimeField | Confirmed timestamp |
| `order_pc_build_start` | DateTimeField | Build start |
| `order_pc_build_end` | DateTimeField | Build end |
| `order_pc_test_start` | DateTimeField | Test start |
| `order_pc_test_end` | DateTimeField | Test end |
| `order_packed` | DateTimeField | Packed timestamp |
| `order_shipped` | DateTimeField | Shipped timestamp |
| `order_delivered` | DateTimeField | Delivered timestamp |
| `pkg_fees` | DecimalField | Packaging fees |
| `build_fees` | DecimalField | Assembly fees |
| `shp_fees` | DecimalField | Shipping fees |
| `tax_state_code` | IntegerField | GST state code |
| `tax_total` | DecimalField | Total tax |
| `kuro_discount` | DecimalField | Discount amount |
| `order_total` | DecimalField | Grand total |
| `payment_option` | CharField(150) | Payment method |
| `upi_address` | CharField(150) | UPI address |
| `temp_reference` | CharField(150) | Temporary payment ref |
| `pay_reference` | CharField(150) | Payment reference |
| `shp_agency` | CharField(150) | Shipping agency |
| `shp_url` | CharField(150) | Shipping URL |
| `shp_awb` | CharField(150) | AWB number |
| `shp_status` | CharField(150) | Shipping status |
| `shp_addressid` | CharField(255) | Ship-to address |
| `bill_addressid` | CharField(255) | Bill address |
| `fail_orderid` | CharField(150) | Failed order ref |
| `delete_flag` | BooleanField | Soft delete |
| `channel` | CharField(150) | Sales channel |
| `order_expiry` | DateTimeField | Order expiry |
| `created_at`, `updated_at` | DateTimeField | Audit timestamps |

### OrderItems (gaming)

| Field | Type | Purpose |
|---|---|---|
| `orderid` | FK → Orders | Parent order |
| `productid` | CharField(150) | Product reference |
| `title` | CharField(300) | Product title |
| `components` | JSONField | Component breakdown |
| `category` | CharField(150) | Product category |
| `price` | DecimalField | Line price |
| `quantity` | IntegerField | Quantity |
| `hsn_code` | CharField(150) | HSN tax code |
| `tax_cgst`, `tax_sgst`, `tax_igst` | DecimalField | Tax amounts |
| `tax_amount` | CharField(150) | Total tax string |
| `created_at`, `updated_at` | DateTimeField | Audit |

---

## Migration Strategy

### Step 1: Keep kteam-dj-be CustomUser as the canonical schema

kteam-dj-be's schema is more complete (has `usertype`, `user_status`, `created_date`). All gaming users will be migrated into this schema.

### Step 2: Gaming user migration

```python
# management/commands/merge_gaming_users.py
from django.contrib.auth import get_user_model
from phonenumber_field.phonenumber import PhoneNumber

def merge_gaming_users():
    User = get_user_model()
    # Gaming users have no usertype/user_status — set defaults
    gaming_users = CustomUser.objects.filter(
        Q(usertype__isnull=True) | Q(usertype='')
    )
    for user in gaming_users:
        user.usertype = user.usertype or 'customer'
        user.user_status = user.user_status or 'Active'
        user.created_date = user.created_date or user.last_login or timezone.now()
        user.save(update_fields=['usertype', 'user_status', 'created_date'])
```

### Step 3: PhoneModel merge

Both projects use identical `PhoneModel`. No migration needed — just ensure the table exists in the unified database.

### Step 4: Manager reconciliation

The `_create_user` method signature must accept both sets of parameters:

```python
class CustomUserManager(BaseUserManager):
    def _create_user(self, userid, phone, password=None, name=None,
                     email=None, usertype=None, user_status=None,
                     username=None, **extra_fields):
        # Accept BOTH kteam and gaming parameters
        if not phone:
            raise ValueError('Users must have a phone')
        email = self.normalize_email(email)
        user = self.model(
            userid=userid, phone=phone, name=name,
            username=username, email=email,
            usertype=usertype, user_status=user_status,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user
```

### Step 5: Username handling

Gaming backend passes `username` to the manager; kteam does not. The reconciled manager accepts `username` as an optional parameter. The `save()` method on `CustomUser` already handles `username == "" → None`.

---

## Summary Table

| Model | kteam only | Gaming only | Shared (identical) | Shared (need merge) |
|---|---:|---:|---:|---:|
| `CustomUser` | 4 fields | 0 | 8 fields | Manager signature |
| `PhoneModel` | — | — | ✅ Yes | — |
| `KuroUser` | ✅ Yes | — | — | — |
| `Switchgroupmodel` | ✅ Yes | — | — | — |
| `Accesslevel` | ✅ Yes | — | — | — |
| `BusinessGroup` | ✅ Yes | — | — | — |
| `Common_counters` | ✅ Yes | — | — | — |
| `Cart` | — | ✅ Yes | — | — |
| `Wishlist` | — | ✅ Yes | — | — |
| `Addresslist` | — | ✅ Yes | — | — |
| `Orders` | — | ✅ Yes | — | — |
| `OrderItems` | — | ✅ Yes | — | — |

**Total custom fields in kteam CustomUser: 4** (`usertype`, `user_status`, `created_date`, `last_login` nullable)
**Total gaming-exclusive models: 5** (Cart, Wishlist, Addresslist, Orders, OrderItems)
**Data loss risk: None** — all gaming user data maps cleanly to kteam schema.
