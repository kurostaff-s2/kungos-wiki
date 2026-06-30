# Cafe Menu: Catalog in MongoDB, Inventory in PG — Derived Menu View

**Created:** 2026-07-01  
**Updated:** 2026-07-01 (revised after split-brain analysis)  
**Priority:** HIGH  
**Status:** Analysis Complete — Implementation Required

---

## 📋 **Executive Summary**

**Issue:** The `cafe_menu_items` PostgreSQL table is a hardcoded snapshot (migration 0005) with no connection to the actual sources of truth:
- **Catalog** (names, prices, descriptions) lives in MongoDB `presets` and `products` collections
- **Inventory** (stock, availability) lives in PostgreSQL `inventory_inventoryitem` / `inventory_inventorystock`
- **Arcade pricing** lives in PostgreSQL `caf_platform_price_plans`

The menu is a dead copy that drifts from reality the moment anyone edits a preset or product.

**Architecture Decision:** Keep catalog in MongoDB, keep inventory/pricing in PostgreSQL. The menu is a **derived view** (read-side projection) that joins both. No consolidation of catalog into PG — preserve the existing split.

---

## 🔍 **Current State Analysis**

### **PostgreSQL `cafe_menu_items` (50 items)** — Hardcoded Snapshot

| Source Type | Count | Source ID Pattern | Matches MongoDB? |
|-------------|-------|-------------------|------------------|
| F&B | 19 | `TINTHU2510000001`, `TINCOC2510000006`, etc. | ⚠️ IDs match, but stale |
| Arcade | 31 | `PRE2500001`–`PRE2500033` | ❌ Orphaned IDs |

**Migration 0005** (`domains/cafe_fnb/migrations/0005_populate_menu_from_mongodb.py`) contains literal lists `FNB_PRODUCTS` and `ARCADE_PACKAGES` — no MongoDB queries.

**Migration 0007** (`domains/cafe_fnb/migrations/0007_populate_branch_availability.py`) contains literal dict `ARCADE_PRICING` — no MongoDB queries.

### **MongoDB Sources of Truth**

#### Catalog: `presets` collection (PresetViewSet)
```javascript
{
  _id: ObjectId,
  title: "PC 144Hz",
  type: "pc144hz",
  branch_code: "KURO0001_001_001",
  bg_code: "KURO0001",
  div_code: "001",
  list: [
    { item_code: "...", name: "...", price: 100, duration: 60 }
  ]
}
```
- Arcade packages (topups, memberships, happypasses) live here
- Also used for PC build presets (Grace Timing, etc.)
- **This is the catalog of truth for arcade packages**

#### Catalog: `products` collection (ProductViewSet)
- F&B products (soft drinks, energy drinks, coffee, meals)
- 82 documents with `productid`, `title`, `price`, `category`
- **This is the catalog of truth for F&B items**

### **PostgreSQL Inventory** (already migrated)

| Table | Purpose |
|-------|---------|
| `inventory_inventoryitem` | Item registry (2,294 items) |
| `inventory_inventorystock` | Branch-level stock quantities |
| `inventory_inventorymovement` | Movement audit trail |
| `caf_platform_price_plans` | Arcade hourly pricing |

### **The Split Brain**

```
┌─────────────────────┐     ┌─────────────────────┐
│  MongoDB (Catalog)   │     │  PostgreSQL (Inventory)│
│                      │     │                          │
│  presets (arcade)    │     │  inventory_inventorystock│
│  products (F&B)      │     │  caf_platform_price_plans│
└──────────┬───────────┘     └──────────┬───────────────┘
           │                             │
           └──────────┬──────────────────┘
                      │
              ┌───────▼────────┐
              │ cafe_menu_items │  ← HARDCODED COPY (not joined!)
              │ (hardcoded in   │
              │  migration 0005)│
              └────────────────┘
```

The menu should be: **Catalog (MongoDB) + Inventory/Availability (PG) → derived menu view**

But it currently is: **Hardcoded snapshot, disconnected from both sources**

---

## ⚠️ **The Split Brain Problem**

### **1. Catalog vs. Menu: Two Sources, No Connection**

The product catalog (names, prices, descriptions) lives in MongoDB:
- `products` collection → F&B items (82 docs)
- `presets` collection → Arcade packages (6+ docs with `list` arrays)

But `cafe_menu_items` in PG has a hardcoded copy. When someone edits a preset price in MongoDB (via `PresetViewSet`), the change **never reaches** `cafe_menu_items`. The menu is a dead snapshot.

### **2. Inventory Availability Not Referenced**

`cafe_menu_items.available` is hardcoded `True`. The actual stock data lives in `inventory_inventorystock` (PG). There's no FK, no join, no sync — the menu can show items as available when stock is zero, or hide items that are in stock.

### **3. Arcade Pricing Duplicated**

Arcade packages exist in two places with no linkage:
- MongoDB `presets.list[]` — the catalog definition (name, price, duration)
- PG `caf_platform_price_plans` — the billing rates
- PG `cafe_menu_items` — a hardcoded copy of neither

### **4. No Sync Path**

There is no management command, cron job, signal, or trigger that bridges MongoDB catalog → PG menu. The only "sync" is re-running migration 0005 manually.

---

## 🎯 **Root Cause**

**Migration 0005** used hardcoded literal lists instead of querying MongoDB. This was likely done as a quick Phase 8 data seed, but it created a permanent inconsistency because:

1. **No sync mechanism was built** — the migration populates once, never again
2. **The architecture assumes catalog stays in MongoDB** — the inventory domain docstring explicitly states: "Product catalog (titles, descriptions, images, pricing, specs) lives in MongoDB."
3. **The menu was designed as a standalone table** — `cafe_menu_items` has its own `name`, `price`, `category` fields instead of referencing the catalog

**The fix is NOT to move catalog to PG.** The fix is to make the menu a derived view that reads from both sources.

---

## 📐 **Proposed Solution: Derived Menu View**

### **Architecture**

```
┌──────────────────────┐     ┌──────────────────────────┐
│  MongoDB (Catalog)    │     │  PostgreSQL (Inventory)   │
│                       │     │                            │
│  presets              │     │  inventory_inventorystock  │
│  products             │     │  caf_platform_price_plans  │
│                       │     │  cafe_menu_branch_avail.   │
└──────────┬────────────┘     └──────────┬─────────────────┘
           │                              │
           └──────────┬───────────────────┘
                      │
         ┌────────────▼────────────┐
         │  sync_cafe_menu (job)    │
         │  ─────────────────────   │
         │  Reads: catalog (MongoDB)│
         │  Reads: stock (PG)       │
         │  Writes: cafe_menu_items │
         │         cafe_menu_branch │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │  menu_list (endpoint)    │
         │  ─────────────────────   │
         │  Reads: cafe_menu_items  │
         │  (PG, fast reads)        │
         └─────────────────────────┘
```

### **Key Design Decisions**

1. **Catalog stays in MongoDB** — `presets` and `products` remain the source of truth for names, prices, descriptions
2. **Inventory stays in PostgreSQL** — `inventory_inventorystock` remains the source of truth for stock quantities
3. **Menu is a derived projection** — `cafe_menu_items` is populated by a sync job that joins both sources
4. **Arcade packages follow the presets pattern** — they live in MongoDB `presets`, the sync job flattens `presets.list[]` into `cafe_menu_items` rows

### **Sync Job: `sync_cafe_menu`**

```python
# management/commands/sync_cafe_menu.py
"""
Sync cafe menu from catalog (MongoDB) + inventory (PostgreSQL).

Usage:
    python manage.py sync_cafe_menu --dry-run
    python manage.py sync_cafe_menu
"""

def handle(self, *args, **options):
    mongo = get_mongo_client()['KungOS_Mongo_One']
    
    # 1. Arcade packages from presets
    for preset in mongo['presets'].find({}):
        for item in preset.get('list', []):
            CafeMenuItems.objects.update_or_create(
                source_type='arcade',
                source_id=item.get('item_code', str(preset['_id'])),
                defaults={
                    'name': item['name'],
                    'category': preset['type'],
                    'price': item['price'],
                    'duration_minutes': item.get('duration'),
                    'station_type': preset['type'],
                    'available': True,  # arcade = always available
                }
            )
    
    # 2. F&B items from products + stock
    for product in mongo['products'].find({'delete_flag': {'$ne': True}}):
        item_code = product['productid']
        # Check stock availability
        stock = InventoryStock.objects.filter(
            item__item_code=item_code
        ).first()
        CafeMenuItems.objects.update_or_create(
            source_type='fnb',
            source_id=item_code,
            defaults={
                'name': product['title'],
                'category': product.get('category', 'snack'),
                'price': product.get('price', 0),
                'available': stock.available_quantity > 0 if stock else False,
            }
        )
```

### **What Changes**

| Component | Before | After |
|-----------|--------|-------|
| `cafe_menu_items` | Hardcoded snapshot | Synced from MongoDB + PG |
| `sync_cafe_menu` | Doesn't exist | New management command |
| `menu_list` endpoint | Queries PG (works as-is) | No change needed — already queries PG |
| Migration 0005 | Hardcoded data | Can be made a no-op or removed |
| Migration 0007 | Hardcoded pricing | Sync job handles branch pricing |

### **What Doesn't Change**

- MongoDB `presets` collection — still the catalog source
- MongoDB `products` collection — still the F&B catalog source
- PostgreSQL `inventory_inventorystock` — still the stock source
- PostgreSQL `caf_platform_price_plans` — still the billing source
- The `menu_list` API endpoint — already queries PG correctly

---

## 📝 **Implementation: `sync_cafe_menu` Command**

```python
# domains/cafe_fnb/management/commands/sync_cafe_menu.py
"""
Sync cafe menu from catalog (MongoDB) + inventory (PostgreSQL).

Arcade packages: catalog from MongoDB presets.list[], always available
F&B items:       catalog from MongoDB products, availability from PG inventory

Usage:
    python manage.py sync_cafe_menu --dry-run
    python manage.py sync_cafe_menu
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Q
from backend.utils import get_mongo_client
from domains.cafe_fnb.models import CafeMenuItems, CafeMenuBranchAvailability
from domains.inventory.models import InventoryStock, InventoryItem


class Command(BaseCommand):
    help = 'Sync cafe menu from MongoDB catalog + PostgreSQL inventory'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    CATEGORY_MAP = {
        'soft_drink': 'soft_drink',
        'energy_drink': 'energy_drink',
        'coffee': 'coffee',
        'meal': 'meal',
        'snack': 'snack',
    }

    STATION_TYPE_MAP = {
        'pc144hz': '144hz',
        'pc240hz': '240hz',
        'vr': 'vr',
        'ps5': 'ps5',
    }

    def handle(self, *args, **options):
        if options['dry_run']:
            self.dry_run()
            return
        self.sync_menu()

    def dry_run(self):
        db = get_mongo_client()['KungOS_Mongo_One']
        fnb_count = db['products'].count_documents({'delete_flag': {'$ne': True}})
        arcade_count = sum(
            len(p.get('list', [])) for p in db['presets'].find({})
        )
        self.stdout.write(f'F&B catalog items (MongoDB): {fnb_count}')
        self.stdout.write(f'Arcade menu items (from presets.list): {arcade_count}')
        self.stdout.write('Run without --dry-run to sync.')

    def sync_menu(self):
        db = get_mongo_client()['KungOS_Mongo_One']
        
        # ── Arcade packages from presets ──
        arcade_count = 0
        for preset in db['presets'].find({}):
            preset_type = preset.get('type', 'unknown')
            for item in preset.get('list', []):
                source_id = item.get('item_code') or str(preset.get('_id', ''))
                CafeMenuItems.objects.update_or_create(
                    source_type='arcade',
                    source_id=source_id,
                    defaults={
                        'name': item.get('name', preset.get('title', '')),
                        'category': preset_type,
                        'subcategory': 'topup',  # default; presets define subcategory
                        'price': Decimal(str(item.get('price', 0))),
                        'duration_minutes': item.get('duration'),
                        'station_type': self.STATION_TYPE_MAP.get(preset_type, ''),
                        'available': True,  # arcade = always available
                        'membership': item.get('membership', False),
                    }
                )
                arcade_count += 1
        
        # ── F&B items from products + stock ──
        fnb_count = 0
        for product in db['products'].find({'delete_flag': {'$ne': True}}):
            item_code = product.get('productid', '')
            if not item_code:
                continue
            
            # Check stock availability from PG
            try:
                inv_item = InventoryItem.objects.get(item_code=item_code)
                stock = InventoryStock.objects.filter(item=inv_item).first()
                is_available = stock.available_quantity > 0 if stock else False
            except InventoryItem.DoesNotExist:
                is_available = True  # no stock tracking = always available
            
            CafeMenuItems.objects.update_or_create(
                source_type='fnb',
                source_id=item_code,
                defaults={
                    'name': product.get('title', item_code),
                    'category': self.CATEGORY_MAP.get(
                        product.get('category', ''), 'snack'
                    ),
                    'price': Decimal(str(product.get('price', 0))),
                    'available': is_available,
                }
            )
            fnb_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ Synced: {fnb_count} F&B + {arcade_count} Arcade items'
        ))
```

### **Branch Pricing**

Branch availability (`cafe_menu_branch_availability`) is handled separately:
- Arcade branch pricing comes from `caf_platform_price_plans` (already in PG)
- F&B branch pricing: no overrides currently, use global `cafe_menu_items.price`
- Migration 0007 data can be preserved as initial branch availability, then managed via the `menu_item_detail` PATCH endpoint

---

## 📊 **Verification Steps**

```bash
# 1. Dry run
python manage.py sync_cafe_menu --dry-run

# 2. Execute sync
python manage.py sync_cafe_menu

# 3. Verify counts
python -c "
from domains.cafe_fnb.models import CafeMenuItems
print(f'F&B: {CafeMenuItems.objects.filter(source_type=\"fnb\").count()}')
print(f'Arcade: {CafeMenuItems.objects.filter(source_type=\"arcade\").count()}')
"

# 4. Verify F&B items reference MongoDB products
python -c "
from backend.utils import get_collection
from domains.cafe_fnb.models import CafeMenuItems
db = get_collection('products')  # MongoDB
for item in CafeMenuItems.objects.filter(source_type='fnb')[:5]:
    exists = db.count_documents({'productid': item.source_id})
    print(f'{item.source_id}: {\"✅\" if exists else \"❌\"}')
"

# 5. Test menu endpoint
curl -H "Authorization: Bearer <token>" \
     "http://localhost:8000/api/v1/cafe-fnb/menu/?branch_code=KURO0001_001_001"
```

---

## ⚠️ **Risks**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sync job runs too slowly | MEDIUM | Use `update_or_create` (batch), not delete+insert |
| MongoDB connection failure | MEDIUM | Circuit breaker (already in `gateways.py`), fallback to cached PG data |
| Arcade items missing from presets | LOW | `update_or_create` preserves existing items not in current presets |
| F&B stock tracking not set up | LOW | If `InventoryItem` doesn't exist for an item, default to `available=True` |

---

## 🔗 **Related**

- **Catalog consolidation plan:** `01-07-2026_catalog_consolidation_products_presets_abc123.md` (updated to 2-collection model)
- **Inventory migration:** `domains/inventory/migrations/0002_migrate_legacy_inventory.py`
- **Menu endpoint:** `domains/cafe_fnb/views.py::menu_list` (queries PG — no change needed)
- **PresetViewSet:** `domains/products/viewsets.py::PresetViewSet` (MongoDB `presets`)
- **ProductViewSet:** `domains/products/viewsets.py::ProductViewSet` (MongoDB `products`)

---

## 📅 **Timeline**

| Step | Duration | Dependencies |
|------|----------|-------------|
| Create `sync_cafe_menu` command | 30 min | None |
| Dry run + validate counts | 15 min | Command created |
| Execute sync | 5 min | Dry run passes |
| Verify menu endpoint | 15 min | Sync complete |
| **Total** | **~1 hour** | — |

---

**Status:** ✅ Analysis Complete — Ready for Implementation  
**Assigned to:** Backend Developer  
**Reviewer:** Tech Lead  
**Last Updated:** 2026-07-01
