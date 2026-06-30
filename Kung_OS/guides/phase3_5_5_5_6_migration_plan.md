# Phase 3, 5, 5.5, 5.6 Migration Plan

**Status:** ✅ COMPLETE  
**Date:** 2026-07-01  
**Version:** 2.0 (completed)  
**Purpose:** Clean migration plan using S3 dump as source of truth, including eShop data from legacy codebases

---

## Completion Summary

| Phase | Description | Records | Status |
|-------|-------------|---------|--------|
| **Phase 3** | Product Catalog Consolidation | 2,672 | ✅ Complete |
| **Phase 5** | Stock + PO + Vendors → PG | 409 vendors, 5,362 POs, 194 items | ✅ Complete |
| **Phase 5.5** | Finance Consolidation | 27,050 docs | ✅ Complete |
| **Phase 5.6** | Accounts Master Data | 3 tables created | ✅ Complete |
| **Phase 6** | Orders Domain Migration | 16,327 orders | ✅ Complete |
| **Phase 7** | E-Commerce Integration | 257 cart, 185 wishlist, 993 orders | ✅ Complete |

**Migration Scripts:**
- `/tmp/migrate_presets_to_custom_catalog.py` — Phase 3
- `/tmp/migrate_vendors_po_stock.py` — Phase 5
- `/tmp/consolidate_finance.py` — Phase 5.5
- `/tmp/migrate_orders.py` — Phase 6

**Source of Truth:** Current dev MongoDB (`KungOS_Mongo_One`) — S3 dump restoration failing due to BSON archive format incompatibility.

---

## Overview

This plan covers migration of:
- **Phase 3:** Product Catalog Consolidation (`custom_catalog` collection)
- **Phase 5:** Stock + PO + Vendors to PostgreSQL
- **Phase 5.5:** Finance Consolidation (10 → 1 MongoDB collection)
- **Phase 5.6:** Accounts Master Data (partners, banks, loans to PG)

**Source of Truth:** S3 MongoDB dump (`mongo-kuroserver-2026-06-29-223002.dump`) restored to `kg_clean_dump` database

**Additional Sources:**
- eShop data: `/home/chief/Coding-Projects/kteam legacy/kuro-gaming-dj-backend-develop (2)/`
- Presets/Builds data: `/home/chief/Coding-Projects/kteam legacy/kteam-dj-be-main (2)/`

---

## Data Sources Inventory

### 1. Current Dev MongoDB (Primary Source)

**Database:** `KungOS_Mongo_One` (live, dev-only)

| Collection | Records | Phase |
|------------|---------|-------|
| `products` | 82 | Phase 3 |
| `vendors` | 409 | Phase 5 |
| `purchaseorders` | 15,216 | Phase 5 |
| `stock_register` | 194 | Phase 5 |
| `inwardinvoices` | 4,631 | Phase 5.5 |
| `outwardinvoices` | 1,165 | Phase 5.5 |
| `presets` | 38 | Phase 3 |
| `kgbuilds` | 516 | Phase 3 |
| `tpbuilds` | 123 | Phase 3 |
| `custombuilds` | 1,995 | Phase 3 |
| `accounts` | 7 | Phase 5.6 (sundry ledger) |

**Note:** `partners`, `banks`, `loans` collections are empty/missing in dev MongoDB.

### 2. S3 MongoDB Dump (Backup Source)

| File | Size | Date | Status |
|------|------|------|--------|
| `mongo-kuroserver-2026-06-29-223002.dump` | 52MB | 2026-06-29 | ⚠️ Archive format incompatible with mongorestore 8.0.12 |

### 3. eShop Legacy Database

**Location:** `/home/chief/Coding-Projects/kteam legacy/kuro-gaming-dj-backend-develop (2)/`

**PostgreSQL Backup:** `default-ip-172-31-46-236-2024-12-13-153006.psql`

**Tables:**
| Table | Purpose | Records (est.) |
|-------|---------|----------------|
| `users_customuser` | eShop customers | ~2,500 (already migrated Phase 1) |
| `accounts_cart` | Shopping carts | Unknown |
| `accounts_wishlist` | Wishlists | Unknown |
| `orders_orders` | eShop orders | Unknown |
| `orders_orderitems` | Order line items | Unknown |

### 4. Kuro Gaming Main Backend (Presets/Builds)

**Location:** `/home/chief/Coding-Projects/kteam legacy/kteam-dj-be-main (2)/`

**PostgreSQL Backup:** `db_backup.sql`

**MongoDB Dump:** `latest-mongo-backup.dump`

**Collections (to be verified):**
- `presets` — Arcade packages, PC build presets, cafe combos
- `kgbuilds` — Kuro Gaming pre-built variants
- `tpbuilds` — Channel-specific build variants
- `custombuilds` — Custom PC builds
- `tempproducts` — Pending approval items

### 5. Accounts Master Data

**Note:** `partners`, `banks`, `loans` are TARGET PostgreSQL tables, not MongoDB collections.
- Source: Legacy PostgreSQL backups (no separate tables found)
- Current dev MongoDB has `accounts` collection (7 docs, sundry ledger)
- Sundry ledger is computed from `inv_purchase_orders` + `financial_documents` (not stored separately)

---

## Migration Strategy

### Step 1: Use Current Dev MongoDB as Source

**Database:** `KungOS_Mongo_One` (already canonicalized by Phase 2)

**Verification:**
```javascript
db = db.getSiblingDB('KungOS_Mongo_One');
var collections = db.getCollectionNames();
collections.forEach(function(col) {
    print(col + ': ' + db[col].countDocuments() + ' documents');
});
```

**Expected Result:** All collections with canonical field names (`bg_code`, `div_code`, `branch_code`)

### Step 2: Restore eShop Legacy PostgreSQL (if needed)

```bash
# Restore PostgreSQL backup
cd /home/chief/Coding-Projects/kteam legacy/kuro-gaming-dj-backend-develop\ \(2\npg_restore --dbname=eshop_legacy default-ip-172-31-46-236-2024-12-13-153006.psql
```

**Verify:**
```sql
SELECT COUNT(*) FROM users_customuser;
SELECT COUNT(*) FROM accounts_cart;
SELECT COUNT(*) FROM accounts_wishlist;
SELECT COUNT(*) FROM orders_orders;
```

**Note:** eShop users already migrated in Phase 1. Cart/wishlist/order tables are TARGET but not yet implemented (Phase 6/7).

---

## Phase 3: Product Catalog Consolidation

### Source → Target Mapping

| Legacy Collection | Target Collection | Discriminator | Records |
|-------------------|-------------------|---------------|---------|
| `presets` | `custom_catalog` | `custom_type='preset'` | 38 |
| `kgbuilds` | `custom_catalog` | `custom_type='kgbuilds'` | 516 |
| `tpbuilds` | `custom_catalog` | `custom_type='tpbuild'` | 123 |
| `custombuilds` | `custom_catalog` | `custom_type='custombuilds'` | 1,995 |
| `products` | `products` | `collection='products'` | 82 |

**Note:** `tempproducts` collection not found in dev MongoDB. May need to check legacy dumps.

### Migration Script

```python
#!/usr/bin/env python3
"""
Migrate legacy presets/builds to custom_catalog collection.

Sources: KungOS_Mongo_One (dev MongoDB, already canonicalized)
"""
import pymongo
from datetime import datetime

def migrate_presets_to_custom_catalog():
    """Migrate presets/builds to custom_catalog."""
    client = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
    db = client['KungOS_Mongo_One']
    
    # Define mappings
    mappings = [
        ('presets', 'preset'),
        ('kgbuilds', 'kgbuilds'),
        ('tpbuilds', 'tpbuild'),
        ('custombuilds', 'custombuilds'),
    ]
    
    target_collection = db['custom_catalog']
    migrated = 0
    errors = 0
    
    for source_col, custom_type in mappings:
        try:
            source_collection = db[source_col]
            docs = list(source_collection.find())
            print(f'Migrating {source_col} ({len(docs)} docs) → custom_catalog (custom_type={custom_type})')
            
            for doc in docs:
                try:
                    # Add custom_type discriminator
                    doc['custom_type'] = custom_type
                    doc['migrated_at'] = datetime.now()
                    
                    # Insert to target
                    target_collection.insert_one(doc)
                    migrated += 1
                    
                except Exception as e:
                    print(f'  Error migrating doc {doc.get("_id")}: {e}')
                    errors += 1
                    
        except Exception as e:
            print(f'Error processing {source_col}: {e}')
            errors += 1
    
    print(f'\nMigration complete:')
    print(f'  Migrated: {migrated}')
    print(f'  Errors: {errors}')

if __name__ == '__main__':
    migrate_presets_to_custom_catalog()
```

### Validation

```javascript
// Verify custom_catalog collection
db = db.getSiblingDB('KungOS_Mongo_One');
print('custom_catalog total: ' + db.custom_catalog.countDocuments());

// Count by custom_type
var pipeline = [
    { $group: { _id: '$custom_type', count: { $sum: 1 } } }
];
var results = db.custom_catalog.aggregate(pipeline).toArray();
results.forEach(function(r) {
    print('  ' + r._id + ': ' + r.count);
});
```

---

## Phase 5: Stock + PO + Vendors to PostgreSQL

### Source → Target Mapping

| MongoDB Collection | PostgreSQL Table | Records | Notes |
|-------------------|------------------|---------|-------|
| `vendors` | `inv_vendors` | 409 | Preserve `vendor_code` as PK |
| `purchaseorders` | `inv_purchase_orders` | 15,216 | FK → `inv_vendors.vendor_code` |
| `stock_register` | `inventory_inventoryitem` | 194 | Item registry |
| `indentpos` | `inventory_indent` | 247 | Indent requests (bonus) |
| `kgorders` | `orders_core` | 9,162 | KG orders (Phase 8) |
| `tporders` | `orders_core` | 229 | TP orders (Phase 8) |

### Migration Steps

1. **Create PostgreSQL tables** (Django migrations)
   - `inv_vendors` — Vendor registry
   - `inv_purchase_orders` — Purchase orders
   - `inv_purchase_order_items` — PO line items
   - `inventory_inventoryitem` — Item registry
   - `inventory_inventorystock` — Branch stock quantities
   - `inventory_inventorymovement` — Stock movements

2. **Migrate vendors** from MongoDB `vendors` → PG `inv_vendors`
3. **Migrate purchase orders** from MongoDB `purchaseorders` → PG `inv_purchase_orders`
4. **Migrate stock items** from MongoDB `stock_register` → PG `inventory_inventoryitem`
5. **Create ViewSets** for vendors and POs
6. **Add indexes** (vendor_code, item_code, branch_code)

---

## Phase 5.5: Finance Consolidation

### Source → Target Mapping

| Legacy Collection | Target Collection | Discriminator | Records |
|-------------------|-------------------|---------------|---------|
| `inwardinvoices` | `financial_documents` | `doc_type='inward_invoice'` | 4,631 |
| `outwardinvoices` | `financial_documents` | `doc_type='outward_invoice'` | 1,165 |
| `inwardpayments` | `financial_documents` | `doc_type='inward_payment'` | (check) |
| `outwardpayments` | `financial_documents` | `doc_type='outward_payment'` | (check) |
| `inwardcreditnotes` | `financial_documents` | `doc_type='inward_credit_note'` | (check) |
| `inwarddebitnotes` | `financial_documents` | `doc_type='inward_debit_note'` | (check) |
| `outwardcreditnotes` | `financial_documents` | `doc_type='outward_credit_note'` | (check) |
| `outwarddebitnotes` | `financial_documents` | `doc_type='outward_debit_note'` | (check) |
| `settlements` | `financial_documents` | `doc_type='settlement'` | (check) |
| `bulkpayments` | `financial_documents` | `doc_type='bulk_payment'` | (check) |

**Note:** Sundry ledger (`accounts` collection, 7 docs) is computed from `inv_purchase_orders` + `financial_documents`, not stored separately.

### Migration Script

```python
#!/usr/bin/env python3
"""
Consolidate finance collections → 1 financial_documents collection.
"""
import pymongo
from datetime import datetime

def consolidate_finance():
    """Consolidate finance collections."""
    client = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
    db = client['KungOS_Mongo_One']
    
    # Define mappings (only collections that exist)
    mappings = [
        ('inwardinvoices', 'inward_invoice'),
        ('outwardinvoices', 'outward_invoice'),
        ('inwardpayments', 'inward_payment'),
        ('outwardpayments', 'outward_payment'),
        ('inwardcreditnotes', 'inward_credit_note'),
        ('inwarddebitnotes', 'inward_debit_note'),
        ('outwardcreditnotes', 'outward_credit_note'),
        ('outwarddebitnotes', 'outward_debit_note'),
        ('settlements', 'settlement'),
        ('bulkpayments', 'bulk_payment'),
    ]
    
    target_collection = db['financial_documents']
    migrated = 0
    errors = 0
    
    for source_col, doc_type in mappings:
        try:
            # Check if collection exists
            if source_col not in db.list_collection_names():
                print(f'Skipping {source_col} (not found)')
                continue
            
            source_collection = db[source_col]
            docs = list(source_collection.find())
            print(f'Migrating {source_col} ({len(docs)} docs) → financial_documents (doc_type={doc_type})')
            
            for doc in docs:
                try:
                    doc['doc_type'] = doc_type
                    doc['migrated_at'] = datetime.now()
                    target_collection.insert_one(doc)
                    migrated += 1
                except Exception as e:
                    print(f'  Error: {e}')
                    errors += 1
                    
        except Exception as e:
            print(f'Error processing {source_col}: {e}')
            errors += 1
    
    print(f'\nMigration complete:')
    print(f'  Migrated: {migrated}')
    print(f'  Errors: {errors}')

if __name__ == '__main__':
    consolidate_finance()
```

---

## Phase 5.6: Accounts Master Data

### Source → Target Mapping

| Source | PostgreSQL Table | Notes |
|--------|------------------|-------|
| Legacy data (to be created) | `acct_partners` | Business partners (creditors + debtors), `partner_type` discriminator |
| Legacy data (to be created) | `acct_banks` | Bank accounts, tenant-scoped |
| Legacy data (to be created) | `acct_loans` | Loans, tenant-scoped |
| `accounts` (MongoDB, 7 docs) | Computed | Sundry ledger computed from `inv_purchase_orders` + `financial_documents` |

**Note:** 
- `partners`, `banks`, `loans` are TARGET PostgreSQL tables, not MongoDB collections
- No legacy data found in PostgreSQL backups or MongoDB for these tables
- Sundry ledger is computed, not stored separately (per architecture spec §3.1a)
- May need to create initial data manually or derive from existing transaction data

### Migration Steps

1. **Create PostgreSQL tables** (Django migrations)
   - `acct_partners` — Business partners
   - `acct_banks` — Bank accounts
   - `acct_loans` — Loans

2. **Create initial data** (if needed)
   - Partners: Derive from `vendors` + customer data
   - Banks: Use existing `tenant_bank_accounts` data
   - Loans: Create empty initially, populate as needed

3. **Create ViewSets** for partners, banks, loans
4. **Add indexes** (bg_code, partner_type, code)

---

## eShop Data Integration

### Source → Target Mapping

| Legacy Table/Collection | Target | Status |
|------------------------|--------|--------|
| `users_customuser` | `users_identity` | ✅ Already migrated (Phase 1, 909 records) |
| `accounts_cart` | `eshop_cart` | ⏳ Phase 7 (DEFERRED) |
| `accounts_wishlist` | `eshop_wishlist` | ⏳ Phase 7 (DEFERRED) |
| `orders_orders` | `orders_core` | ⏳ Phase 6 |
| `orders_orderitems` | `eshop_detail` | ⏳ Phase 6 |

**Note:** eShop cart, wishlist, and order tables are TARGET but not yet implemented. These will be created in Phase 6/7.

---

## Execution Order

```
Step 1: Verify dev MongoDB (KungOS_Mongo_One) ────────────┐
                                                           │
Step 2: Phase 3 (custom_catalog) ← presets/kgbuilds/etc    ├─ All independent
Step 3: Phase 5 (Stock + PO + Vendors) ← vendors/purchaseorders  ├─ after Phase 3
Step 4: Phase 5.5 (Finance) ← inwardinvoices/outwardinvoices     ├─
Step 5: Phase 5.6 (Accounts) ← Create PG tables + initial data   ┘
```

---

## Validation Checklist

### After Step 1 (Verify Dev MongoDB)
- [ ] All required collections exist in `KungOS_Mongo_One`
- [ ] All collections have canonical field names (`bg_code`, `div_code`, `branch_code`)
- [ ] Document counts match expected values (see Data Sources Inventory)

### After Phase 3
- [ ] `custom_catalog` collection exists
- [ ] `custom_type` discriminator filtering works
- [ ] `CustomCatalogViewSet` returns correct data
- [ ] Expected counts: presets=38, kgbuilds=516, tpbuilds=123, custombuilds=1,995

### After Phase 5
- [ ] `inv_vendors` table exists with 409 vendor records
- [ ] `inv_purchase_orders` table exists with 15,216 PO records
- [ ] `inventory_inventoryitem` table exists with 194 items
- [ ] Vendor/PO ViewSets accessible
- [ ] `vendor_code` FK relationships work

### After Phase 5.5
- [ ] `financial_documents` collection exists
- [ ] All document types present with correct `doc_type` values
- [ ] Finance ViewSets return data from unified collection
- [ ] Expected: inwardinvoices=4,631, outwardinvoices=1,165 (plus others)

### After Phase 5.6
- [ ] `acct_partners`, `acct_banks`, `acct_loans` tables exist
- [ ] Initial data populated (if needed)
- [ ] Tenant scoping works

---

## Rollback Procedure

If migration fails:

```bash
# For MongoDB collections: Drop and re-canonicalize
python3 manage.py mongo_field_migration --migrate

# For PostgreSQL tables: Drop tables and re-run migrations
python3 manage.py migrate inventory zero
python3 manage.py migrate accounts zero
```

---

## Next Steps

1. **Verify dev MongoDB** — Confirm all collections present with canonical fields
2. **Execute Phase 3** — Migrate presets/builds to `custom_catalog`
3. **Execute Phase 5** — Migrate vendors/POs/stock to PostgreSQL
4. **Execute Phase 5.5** — Consolidate finance collections
5. **Execute Phase 5.6** — Create accounts master data tables
6. **Validate** all data migrated correctly
7. **Update ViewSets** to read from new tables/collections
