# Legacy Eshop Migration Review

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | eshop-legacy-review |
| Entity type | review |
| Short description | Review of legacy eshop backend data and determine migration requirements for KungOS eshop domain |
| Status | draft |
| Generated | 29-06-2026 |

---

## Executive Summary

**The MongoDB product catalog has already been migrated.** The PostgreSQL eshop data has NOT been migrated yet.

| Source | Target | Status |
|--------|--------|--------|
| `products` MongoDB DB | `KungOS_Mongo_One` | ✅ **Already migrated** |
| `kuro-user` PostgreSQL DB | `kuro-cadence` PostgreSQL | ❌ **Not migrated** |

---

## 1. Legacy Eshop Backend

**Location:** `/home/chief/Coding-Projects/kteam legacy/kuro-gaming-dj-backend-develop (2)/`

**Database Configuration:**
```python
DATABASES = {
    'default': {  # PostgreSQL
        'NAME': 'kuro-user',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': '127.0.0.1',
    },
    'mongo': {  # MongoDB
        'ENGINE': 'djongo',
        'NAME': 'products',
    }
}
```

**Django Apps:**
- `users` — CustomUser model (userid PK, phone-based auth)
- `accounts` — Cart, Wishlist, Addresslist
- `orders` — Orders, OrderItems
- `products` — Empty (uses MongoDB)
- `payment` — Empty
- `games` — Empty
- `kuroadmin` — Empty

---

## 2. MongoDB Migration Status: ✅ COMPLETE

### Migration Command

`/home/chief/Coding-Projects/kteam-dj-chief/plat/management/commands/mongo_migrate_eshop.py`

This command migrated product catalog collections from `products` DB to `KungOS_Mongo_One` with canonical tenant fields.

### Migration Details

| Collection | Source Count | Target Count | Tenant Fields | Status |
|------------|--------------|--------------|---------------|--------|
| prods | 2,459 | 2,459 | ✅ bg_code, div_code, branch_code | ✅ Migrated |
| components | 1,614 | 1,614 | ✅ | ✅ Migrated |
| custombuilds | 1,995 | 1,995 | ✅ | ✅ Migrated |
| builds | 258 | 258 | ✅ | ✅ Migrated |
| kgbuilds | 516 | 516 | ✅ | ✅ Migrated |
| accessories | 504 | 504 | ✅ | ✅ Migrated |
| monitors | 156 | 156 | ✅ | ✅ Migrated |
| networking | 17 | 17 | ✅ | ✅ Migrated |
| lists | 3 | 3 | ✅ | ✅ Migrated |
| external | 12 | 12 | ✅ | ✅ Migrated |
| kurodata | 2 | 2 | ✅ | ✅ Migrated |
| presets | 32 | 38 | ✅ | ✅ Migrated (+6 new) |
| cables | 1 | 0 | ❌ | ⚠️ Not in migration script |
| misc | 1 | 5,512 | ✅ | ⚠️ Different data |
| tempproducts | 2 | 0 | ❌ | 🗑️ Test data |

### Migration Script Behavior

```python
# Adds tenant fields to each document
def add_tenant_fields(document: dict) -> dict:
    doc = dict(document)
    doc.setdefault("bg_code", "KURO0001")
    doc.setdefault("div_code", "KURO0001_001")
    doc.setdefault("branch_code", None)  # Branch-agnostic for products
    return doc
```

### Verification

```bash
python3 manage.py mongo_migrate_eshop --validate
```

All 12 collections validated with compound indexes (`idx_tenant_bg_div`, `idx_tenant_bg`).

---

## 3. PostgreSQL Migration Status: ❌ NOT MIGRATED

### Legacy Data (from dump file)

| Table | Count | Description |
|-------|-------|-------------|
| `users_customuser` | 2,468 | Eshop users (userid PK, phone auth) |
| `orders_orders` | 992 | Eshop orders |
| `orders_orderitems` | 1,117 | Order line items |
| `accounts_cart` | 257 | Shopping cart items |
| `accounts_wishlist` | 185 | Wishlist items |
| `accounts_addresslist` | 799 | Saved addresses |
| `users_phonemodel` | 5,948 | OTP history |
| `knox_authtoken` | 2,308 | Auth tokens |

### Current KungOS Eshop Tables (mostly empty)

| Table | Count | Description |
|-------|-------|-------------|
| `eshop_cart` | 0 | New canonical cart (identity_id, bg_code) |
| `eshop_wishlist` | 0 | New canonical wishlist (identity_id, bg_code) |
| `eshop_detail` | 2 | New canonical order detail |
| `users_saved_addresses` | 0 | New canonical addresses (identity_id, bg_code) |

### Schema Comparison

| Legacy Eshop | Current KungOS | Notes |
|--------------|----------------|-------|
| `users_customuser` (userid PK) | `users_identity` (identity_id PK) | Different auth model |
| `accounts_cart` (userid FK) | `eshop_cart` (identity_id FK) | Canonical tenant fields |
| `accounts_wishlist` (userid FK) | `eshop_wishlist` (identity_id FK) | Canonical tenant fields |
| `accounts_addresslist` (userid FK) | `users_saved_addresses` (identity_id FK) | Canonical tenant fields |
| `orders_orders` (userid FK) | `orders_core` (customer_id FK) | Different order model |
| `orders_orderitems` | N/A | Integrated into orders_core |

---

## 4. Migration Requirements

### 4.1 MongoDB: ✅ Already Complete

No action needed. The product catalog is fully migrated to `KungOS_Mongo_One` with canonical tenant fields.

### 4.2 PostgreSQL: Needs Migration

The legacy eshop PostgreSQL data (2,468 users, 992 orders, etc.) needs to be migrated to the current KungOS schema.

#### Migration Challenges

1. **User Model Mismatch**
   - Legacy: `users_customuser` with `userid` PK, phone-based auth
   - Current: `users_identity` with `identity_id` PK, unified identity layer
   - Migration: Map legacy users to `users_identity` + `users_customuser`

2. **Schema Transformation**
   - Legacy tables use `userid` FK
   - Current tables use `identity_id` FK + `bg_code`
   - Migration: Transform FK references and add tenant fields

3. **Order Model Mismatch**
   - Legacy: `orders_orders` + `orders_orderitems`
   - Current: `orders_core` + `eshop_detail` + `InventoryItemEshopLink`
   - Migration: Reconstruct orders in new schema

4. **Data Quality**
   - Legacy data may have inconsistencies (duplicate phones, invalid emails)
   - Migration: Validate and clean data before migration

#### Recommended Migration Approach

1. **Phase 1: Users**
   - Migrate `users_customuser` → `users_identity` + `users_customuser`
   - Map `userid` → `identity_id`
   - Preserve phone numbers for auth

2. **Phase 2: Addresses**
   - Migrate `accounts_addresslist` → `users_saved_addresses`
   - Add `identity_id` and `bg_code` fields

3. **Phase 3: Cart & Wishlist**
   - Migrate `accounts_cart` → `eshop_cart`
   - Migrate `accounts_wishlist` → `eshop_wishlist`
   - Update FK references to `identity_id`

4. **Phase 4: Orders**
   - Migrate `orders_orders` → `orders_core` + `eshop_detail`
   - Migrate `orders_orderitems` → order items in `eshop_detail`
   - Add `bg_code` and `branch_code` fields

5. **Phase 5: Cleanup**
   - Drop legacy tables or mark as archived
   - Update application code to use new schema
   - Verify data integrity

---

## 5. Decision Points

### 5.1 Should Legacy Eshop Data Be Migrated?

**Arguments for migration:**
- 2,468 existing users with order history
- 992 historical orders for reporting
- Customer continuity

**Arguments against migration:**
- Legacy schema is fundamentally different
- Migration is complex and risky
- Current eshop domain is being built from scratch
- Legacy users may no longer be active

**Recommendation:** Migrate only if there's business requirement to preserve historical data. Otherwise, archive the legacy data and start fresh.

### 5.2 What About the Legacy Eshop Backend?

The legacy eshop backend (`kuro-gaming-dj-backend-develop`) is no longer used. The current KungOS has a new eshop domain in `domains/eshop/` with:
- `models.py` — Cart, Wishlist, EshopDetail
- `services.py` — Cart, wishlist, order creation
- `views.py` — API endpoints
- `urls.py` — Route configuration

**Recommendation:** Decommission legacy eshop backend. Use current KungOS eshop domain.

---

## 6. Next Steps

1. **Decide on legacy data migration** — Business decision needed
2. **If migrating:**
   - Create Django management command for PostgreSQL migration
   - Test migration on staging database
   - Run migration on production
   - Verify data integrity
3. **If not migrating:**
   - Archive legacy dump files
   - Document data availability
   - Update handoff to reflect fresh eshop start

---

*Review generated: 29-06-2026*
*Legacy eshop backend: `/home/chief/Coding-Projects/kteam legacy/kuro-gaming-dj-backend-develop (2)/`*
*Legacy eshop PostgreSQL dump: `default-ip-172-31-46-236-2024-12-13-153006.psql`*
*Legacy eshop MongoDB dump: `mongo-ip-172-31-46-236-2024-12-13-153008.dump`*
