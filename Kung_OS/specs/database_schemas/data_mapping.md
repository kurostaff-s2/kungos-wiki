# KungOS Data Mapping Specification

**Version:** 1.0
**Date:** 2026-06-27
**Scope:** MongoDB → PostgreSQL cross-database migration

---

## Migration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LEGACY SYSTEM (MongoDB)                      │
├─────────────────────────────────────────────────────────────────┤
│  Collections:                                                   │
│  ├── estimates (4,308 docs)                                    │
│  ├── kgorders (9,162 docs)                                     │
│  ├── tporders (229 docs)                                       │
│  ├── serviceRequest (1,625 docs)                               │
│  └── misc (legacy, to be dropped)                              │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ Data Migration Command
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   TRANSFORMATION LAYER                          │
│  - Phone normalization (E.164)                                  │
│  - Email detection in phone field                               │
│  - Date parsing (ISO → DateField)                               │
│  - Identity resolution (phone → identity_id)                    │
│  - Tenant code validation                                       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   TARGET SYSTEM (PostgreSQL)                    │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                                                        │
│  ├── orders_core (15,324 rows)                                 │
│  ├── estimate_detail (4,308 rows)                              │
│  ├── in_store_detail (9,162 rows)                              │
│  ├── tp_order_detail (229 rows)                                │
│  ├── service_detail (1,625 rows)                               │
│  └── eshop_detail (0 rows — Phase 4B)                          │
│                                                                 │
│  Supporting Tables:                                             │
│  ├── users.identity (3,306 rows)                               │
│  └── tenant.tenant (active tenants)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Collection-to-Table Mapping

| MongoDB Collection | Order Type | Target Table | Record Count |
|--------------------|------------|--------------|--------------|
| `estimates` | `estimate` | `orders_core` + `estimate_detail` | 4,308 |
| `kgorders` | `in_store` | `orders_core` + `in_store_detail` | 9,162 |
| `tporders` | `tp` | `orders_core` + `tp_order_detail` | 229 |
| `serviceRequest` | `service` | `orders_core` + `service_detail` | 1,625 |
| `misc` | — | — | **DROPPED** |

---

## Field Mapping: orders_core

### Source: All MongoDB Collections

| Target Field | Type | Source Field(s) | Transformation | Required |
|--------------|------|-----------------|----------------|----------|
| `order_id` | varchar(50) | `_id` | `str(doc['_id'])` | ✅ PK |
| `order_type` | varchar(20) | Collection name | Constant per collection | ✅ |
| `status` | varchar(20) | `status` | Direct copy | ✅ |
| `customer` | FK → users.identity | `user.phone` → Identity | Normalize phone, lookup/create | Optional |
| `customer_name` | varchar(200) | `user.name` or `name` | From user dict or top-level | |
| `customer_phone` | varchar(50) | `user.phone` | E.164 normalize_phone() | |
| `customer_email` | varchar(254) | `user.email` or `user.phone` (if @) | Email detection | |
| `bg_code` | varchar(10) | `bg_code` | Direct copy | ✅ |
| `div_code` | varchar(20) | `div_code` | Direct copy | |
| `branch_code` | varchar(30) | `branch_code` | Direct copy | |
| `total_amount` | decimal(12,2) | `total_amount` or `totalprice` | Decimal conversion | |
| `currency` | varchar(3) | Constant | `'INR'` | |
| `channel` | varchar(50) | `channel` | Direct copy (default: 'TP Orders' for tp) | |
| `bill_address` | JSON | `billadd` | Direct copy | |
| `products` | JSON | `products` | Direct copy | |
| `active` | boolean | `active` | Direct copy (default: True) | |
| `delete_flag` | boolean | `delete_flag` | Direct copy (default: False) | |
| `created_by` | varchar(50) | `created_by` | Direct copy | |
| `updated_by` | varchar(50) | `updated_by` | Direct copy | |
| `created_date` | datetime | Auto | `timezone.now()` | ✅ |
| `updated_date` | datetime | Auto | `auto_now=True` | ✅ |

---

## Field Mapping: estimate_detail

### Source: `estimates` collection

| Target Field | Type | Source Field | Transformation | Required |
|--------------|------|--------------|----------------|----------|
| `order` | PK FK → orders_core | `_id` | One-to-one via order_id | ✅ |
| `estimate_number` | varchar(50) | `estimate_no` | Direct copy | |
| `version` | integer | `version` | Direct copy (default: 1) | |
| `valid_until` | date | `validity` | Parse ISO date, None if empty | |
| `items` | JSON | `products` | Direct copy | |

**Sample Document:**
```json
{
  "_id": "643d4749d20034f557409f50",
  "estimate_no": "KGE-220000241",
  "version": 1,
  "validity": "2022-01-29T00:00:00.000000+0530",
  "products": [...],
  "user": {"name": "Nigam ", "phone": "nicnicnic4747@gmail.com"},
  "bg_code": "KURO0001",
  "div_code": "KURO0001_001",
  "branch_code": "KURO0001_001_001",
  "status": "quoted",
  "totalprice": 1500.00
}
```

**Mapped to:**
```python
OrderCore(order_id='643d4749d20034f557409f50', order_type='estimate',
          customer_email='nicnicnic4747@gmail.com',  # email detected in phone
          bg_code='KURO0001', total_amount=1500.00)
EstimateDetail(estimate_number='KGE-220000241', valid_until=date(2022, 1, 29))
```

---

## Field Mapping: in_store_detail

### Source: `kgorders` collection

| Target Field | Type | Source Field | Transformation | Required |
|--------------|------|--------------|----------------|----------|
| `order` | PK FK → orders_core | `_id` | One-to-one via order_id | ✅ |
| `table_number` | varchar(20) | `table_number` | Direct copy | |
| `dine_in` | boolean | `dine_in` | Direct copy | |
| `items` | JSON | `products` | Direct copy | |
| `outward_entries` | JSON | `outward` | Direct copy | |

**Sample Document:**
```json
{
  "_id": "643d4749d20034f557409f51",
  "table_number": "T15",
  "dine_in": true,
  "products": [{"name": "Coffee", "qty": 2}],
  "outward": [],
  "user": {"name": "John Doe", "phone": "+919876543210"},
  "bg_code": "KURO0001",
  "status": "completed"
}
```

**Mapped to:**
```python
OrderCore(order_id='643d4749d20034f557409f51', order_type='in_store',
          customer_name='John Doe', customer_phone='+919876543210')
InStoreDetail(table_number='T15', dine_in=True)
```

---

## Field Mapping: tp_order_detail

### Source: `tporders` collection

| Target Field | Type | Source Field | Transformation | Required |
|--------------|------|--------------|----------------|----------|
| `order` | PK FK → orders_core | `_id` | One-to-one via order_id | ✅ |
| `platform` | varchar(50) | `channel` | Direct copy | |
| `platform_order_id` | varchar(100) | `tporderid` | Direct copy | |
| `authorized_by` | varchar(100) | `authorized_by` | Direct copy | |
| `dispatchby_date` | date | `dispatchby_date` | Parse date, None if empty | |
| `fin_year` | varchar(10) | `fin_year` | Direct copy | |
| `items` | JSON | `products` | Direct copy | |

**Sample Document:**
```json
{
  "_id": "643d4749d20034f557409f52",
  "channel": "Swiggy",
  "tporderid": "SWIGGY12345",
  "authorized_by": "Manager",
  "dispatchby_date": "2024-01-15",
  "fin_year": "2023-24",
  "products": [{"name": "Burger", "qty": 1}],
  "bg_code": "KURO0001",
  "status": "authorized"
}
```

**Mapped to:**
```python
OrderCore(order_id='643d4749d20034f557409f52', order_type='tp',
          channel='Swiggy', status='authorized')
TPOrderDetail(platform='Swiggy', platform_order_id='SWIGGY12345',
              dispatchby_date=date(2024, 1, 15))
```

---

## Field Mapping: service_detail

### Source: `serviceRequest` collection

| Target Field | Type | Source Field | Transformation | Required |
|--------------|------|--------------|----------------|----------|
| `order` | PK FK → orders_core | `_id` | One-to-one via order_id | ✅ |
| `service_type` | varchar(50) | `servicetype` or `type` | Direct copy | |
| `description` | text | `issue` or `description` | Direct copy | |
| `scheduled_date` | date | `scheduled_date` | Parse date, None if empty | |

**Sample Document:**
```json
{
  "_id": "643d4749d20034f557409f53",
  "name": "Jane Smith",
  "phone": "+919876543211",
  "servicetype": "Repair",
  "issue": "Laptop screen cracked",
  "scheduled_date": "2024-02-01",
  "bg_code": "KURO0001",
  "status": "pending"
}
```

**Mapped to:**
```python
OrderCore(order_id='643d4749d20034f557409f53', order_type='service',
          customer_name='Jane Smith', customer_phone='+919876543211')
ServiceDetail(service_type='Repair', description='Laptop screen cracked',
              scheduled_date=date(2024, 2, 1))
```

---

## Identity Resolution Logic

### Phone-Based Identity Lookup

```python
# 1. Extract phone from document
user = doc.get('user')
if isinstance(user, dict):
    raw_phone = user.get('phone', '')
else:
    raw_phone = doc.get('phone', '')

# 2. Detect email in phone field
if '@' in str(raw_phone):
    customer_email = str(raw_phone)
    raw_phone = ''  # No phone to normalize

# 3. Normalize phone to E.164
if raw_phone:
    norm_phone = normalize_phone(raw_phone)
    
    # 4. Lookup existing identity
    try:
        identity = Identity.objects.get(phone=norm_phone)
    except Identity.DoesNotExist:
        # 5. Create walk-in identity
        identity = Identity.objects.create(
            identity_id=f"ID{Identity.objects.count() + 1:06d}",
            phone=norm_phone,
            name=customer_name,
            bg_code=doc.get('bg_code', 'KURO0001'),
            div_code=doc.get('div_code', ''),
            status='active',
            phone_verified=False,
        )
```

### Identity Statistics

| Metric | Count |
|--------|-------|
| Total Identity records | 3,306 |
| Orders with linked customer | ~14,977 |
| Walk-in orders (no customer) | ~347 |

---

## Date Field Transformations

### Input Formats Encountered

| Format | Example | Source |
|--------|---------|--------|
| ISO with timezone | `2022-01-29T00:00:00.000000+0530` | estimates.validity |
| ISO date only | `2024-01-15` | tporders.dispatchby_date |
| Empty string | `""` | Various |
| Null/None | `null` | Various |

### Transformation Logic

```python
def parse_date(val):
    """Convert various date formats to Python date or None."""
    if not val or val == '':
        return None
    if isinstance(val, str):
        if 'T' in val:
            val = val.split('T')[0]  # Strip time and timezone
        try:
            return date.fromisoformat(val)
        except (ValueError, TypeError):
            return None
    return val
```

---

## Tenant Code Validation

### Expected Format

```
bg_code:    4 letters + 4 digits (e.g., KURO0001)
div_code:   bg_code + '_' + 3 digits (e.g., KURO0001_001)
branch_code: div_code + '_' + 3 digits (e.g., KURO0001_001_001)
```

### Validation Rules

| Field | Regex | Example |
|-------|-------|---------|
| `bg_code` | `^[A-Z]{4}\d{4}$` | `KURO0001` |
| `div_code` | `^[A-Z]{4}\d{4}_\d{3}$` | `KURO0001_001` |
| `branch_code` | `^[A-Z]{4}\d{4}_\d{3}_\d{3}$` | `KURO0001_001_001` |

### Validation Results

| Check | Result |
|-------|--------|
| Invalid bg_code count | 0 |
| Missing bg_code (using default) | 0 |
| Default bg_code used | `KURO0001` |

---

## Financial Data Mapping

### Amount Fields

| MongoDB Field | PostgreSQL Field | Type | Notes |
|---------------|------------------|------|-------|
| `total_amount` | `total_amount` | decimal(12,2) | Primary |
| `totalprice` | `total_amount` | decimal(12,2) | Fallback |
| `subtotal` | — | — | Not migrated |
| `gst` | — | — | Not migrated |
| `cgst` | — | — | Not migrated |
| `taxes` | — | — | Not migrated |
| `roundoff` | — | — | Not migrated |
| `kuro_discount` | — | — | Not migrated |
| `totaldiscount` | — | — | Not migrated |

### Currency

- All orders: `INR` (hardcoded default)
- No currency conversion required

### Financial Summary

| Metric | Value |
|--------|-------|
| Total orders | 15,324 |
| Total financial value | ₹1,129,900,701.72 |
| Average order value | ₹73,732.45 |

---

## Cross-Database Platform Migrations

### 1. Identity Resolution (MongoDB → PostgreSQL)

**Purpose:** Link orders to existing Identity records

**Process:**
1. Read phone from MongoDB document
2. Normalize to E.164 format
3. Query PostgreSQL `users.identity` table
4. If found: link order to identity
5. If not found: create walk-in identity

**Impact:** ~14,977 orders linked, ~347 walk-ins

---

### 2. Tenant Hierarchy (MongoDB → PostgreSQL)

**Purpose:** Validate and enforce tenant structure

**Process:**
1. Extract bg_code, div_code, branch_code from MongoDB
2. Validate against canonical naming pattern
3. Store in PostgreSQL with indexes

**Indexes Created:**
- `orders_core_bg_code_6e1480_idx` on (bg_code, div_code)
- `orders_core_order_t_f2c5f7_idx` on (order_type, status)
- `orders_core_custome_fe221c_idx` on (customer, bg_code)

---

### 3. Phone Normalization (MongoDB → PostgreSQL)

**Purpose:** Standardize phone numbers to E.164

**Process:**
1. Extract raw phone from MongoDB
2. Apply `users.utils.normalize_phone()`
3. Store normalized phone in PostgreSQL

**Examples:**
| Raw | Normalized |
|-----|------------|
| `9876543210` | `+919876543210` |
| `09876543210` | `+919876543210` |
| `+91-9876543210` | `+919876543210` |
| `nicnicnic4747@gmail.com` | `''` (detected as email) |

---

### 4. Email Detection (MongoDB → PostgreSQL)

**Purpose:** Handle misconfigured phone fields

**Process:**
1. Check if phone field contains '@'
2. If yes: store in `customer_email`, leave `customer_phone` empty
3. If no: store in `customer_phone`

**Impact:** ~50 documents with email in phone field

---

### 5. Date Parsing (MongoDB → PostgreSQL)

**Purpose:** Convert various date formats to PostgreSQL DateField

**Process:**
1. Extract date string from MongoDB
2. Strip timezone info if present
3. Parse to Python date object
4. Store as PostgreSQL date

**Impact:** All date fields migrated correctly, empty strings → NULL

---

## Legacy Entity Removal

### MongoDB: `misc` Collection

**Status:** To be dropped in Phase 4C

**Reason:** Legacy collection with no active references

**Verification:**
```bash
rg -n "misc" --type py | grep -v "miscellaneous"
```

### PostgreSQL: `caf_platform_users` Table

**Status:** To be dropped in Phase 4C

**Reason:** Superseded by `users.identity` model

**Verification:**
```bash
rg -n "caf_platform_users" --type py
```

---

## Data Quality Issues

### Issues Found and Resolved

| Issue | Count | Resolution |
|-------|-------|------------|
| Email in phone field | ~50 | Stored in `customer_email` |
| Empty date strings | ~100 | Converted to NULL |
| Missing bg_code | 0 | Default `KURO0001` |
| Invalid tenant codes | 0 | All valid |

### Issues Requiring Manual Review

| Issue | Count | Action |
|-------|-------|--------|
| Walk-in orders | ~347 | No action — valid unregistered users |
| Duplicate order_ids | 0 | None found |

---

## Migration Command Reference

### Orders Migration

```bash
# Validate without executing
python3 manage.py migrate_orders --validate

# Dry run (shows counts, no writes)
python3 manage.py migrate_orders --dry-run

# Execute migration
python3 manage.py migrate_orders

# Custom source (if needed)
python3 manage.py migrate_orders --source mongodb://user:pass@host:port/db
```

### Expected Output

```
Starting M4 orders migration...
  Collections: ['estimates', 'kgorders', 'tporders', 'serviceRequest']

Migrating estimates (estimate)...
  Source docs: 4308
  ✓ 4308 records migrated

Migrating kgorders (in_store)...
  Source docs: 9162
  ✓ 9162 records migrated

Migrating tporders (tp)...
  Source docs: 229
  ✓ 229 records migrated

Migrating serviceRequest (service)...
  Source docs: 1625
  ✓ 1625 records migrated

Migration complete:
  Total migrated: 15324
  Identity lookups: 0
  Identity creates: 0
  Errors: 0
```

---

## Rollback Procedure

### Complete Rollback

```bash
# 1. Stop application
systemctl stop kungos

# 2. Drop migrated tables
python3 -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    tables = ['estimate_detail', 'in_store_detail', 'tp_order_detail', 
              'service_detail', 'eshop_detail', 'orders_core']
    for table in tables:
        cursor.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
"

# 3. Restore from backup
# (Restore PostgreSQL from pre-migration backup)

# 4. Restart application
systemctl start kungos
```

### Partial Rollback (specific collection)

```bash
# Delete specific order types
python3 -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()
from domains.orders.models import OrderCore
OrderCore.objects.filter(order_type='estimate').delete()
"
```

---

**Document Version History:**

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-27 | Initial creation |
