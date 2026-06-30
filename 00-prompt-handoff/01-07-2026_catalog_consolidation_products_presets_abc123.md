# Catalog Consolidation: All MongoDB Collections → 2 Collections

**Created:** 2026-07-01  
**Updated:** 2026-07-01 (revised: 2 collections, not 1)  
**Phase:** M6 — Product Catalog Consolidation  
**Priority:** HIGH  
**Estimated Effort:** 3-4 hours  
**Dependencies:** Phase 4B (E-Commerce Products Migration) ✅ Complete; Inventory PG migration ✅ Complete

---

## 📋 **Executive Summary**

**Goal:** Consolidate all MongoDB catalog/inventory collections into exactly **2 collections**:

| Collection | Purpose | Holds |
|------------|---------|-------|
| `presets` | Configurations, builds, time-based packages | Presets, tpbuilds, tempproducts, misc, arcade packs |
| `products` | Physical/digital goods catalog | Products, stock_register items, indent products |

**Rationale:** Two fundamentally different lifecycles:
- **Presets** = templates, configurations, time-based services (edit frequently, no stock tracking)
- **Products** = goods with SKUs, pricing, categories (managed by inventory system)

The inventory domain already handles stock tracking in PostgreSQL. The catalog (names, prices, descriptions, specs) stays in MongoDB — but consolidated into 2 collections instead of 10+.

---

## 🔍 **Current State: 10+ Collections**

### **Active Catalog Collections (in MongoDB)**

| Collection | ViewSet | Count (est.) | Purpose |
|------------|---------|-------------|---------|
| `products` | ProductViewSet | 82 | Main product catalog (F&B, components, SKUs) |
| `presets` | PresetViewSet | 6+ | Build presets, arcade packages (time-based) |
| `tpbuilds` | TPBuildViewSet | 123 | Third-party builds (channel-specific) |
| `stock_register` | InventoryViewSet | 194 | Stock with serial numbers |
| `tempproducts` | TempProductViewSet | ? | Draft products |
| `misc` | shared/services.py | ? | Misc data, presetsCollection |
| `indentproduct` | IndentViewSet | ? | Purchase request items |

### **Legacy Collections (migrated to PG, may still have data)**

| Collection | Migrated To | Status |
|------------|-------------|--------|
| `builds` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `kgbuilds` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `custombuilds` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `components` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `accessories` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `monitors` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `networking` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `external` | `inventory_inventoryitem` | Migrated (Phase 8) |
| `stock_audit` | — | Empty |
| `asset_register` | `inventory_inventoryasset` | Migrated (Phase 8) |

### **Why 2, Not 1?**

The original plan (single `catalog` collection with `cat_type` discriminator) conflates two things:

1. **Presets/configurations** — templates, builds, time-based packages. Edited frequently. No stock. Referenced by arcade sessions, PC builds, gaming packages.
2. **Products/goods** — physical or digital items with SKUs. Tracked by inventory. Has categories, HSN codes, GST rates, weights.

These have different:
- **Update frequency** (presets change daily, products change weekly)
- **Query patterns** (presets: filter by type/branch; products: filter by category/search)
- **Lifecycle** (presets: create/edit/archive; products: create/stock/sell/reorder)
- **Referents** (presets: referenced by `caf_platform_sessions.price_plan`; products: referenced by `inventory_inventorystock`)

---

## 🎯 **Scope**

### **In Scope**

#### Collection 1: `presets` (configurations & builds)

Merges:
- `presets` → stays as `presets`
- `tpbuilds` → merged into `presets` (they're channel-specific preset variants)
- `tempproducts` → merged into `presets` (draft configurations)
- `misc` → merged into `presets` (misc data that's actually configuration)

Add discriminator field `preset_type`:
| `preset_type` | Source | Description |
|---------------|--------|-------------|
| `preset` | `presets` | Build presets, arcade packages |
| `tpbuild` | `tpbuilds` | Third-party channel builds |
| `temp` | `tempproducts` | Draft/temporary items |
| `misc` | `misc` | Miscellaneous configurations |

#### Collection 2: `products` (goods catalog)

Merges:
- `products` → stays as `products`
- `stock_register` → merged into `products` (stock items are products with serial numbers)
- `indentproduct` → merged into `products` (indent items are product requests)

No discriminator needed — all are product-type items. Different data shapes handled via optional fields + `collection` field for lineage.

### **Out of Scope**

- ❌ Inventory tracking (PG: `inventory_inventoryitem`, `inventory_inventorystock`) — **already consolidated**
- ❌ Orders (PG: `orders_core`) — **already consolidated**
- ❌ E-commerce collections (`prods`) — separate spec
- ❌ Financial collections (`accounts`, `payments`, `invoices`) — separate domain
- ❌ Station/gamer data (`gamers`, `gamerDetails`) — separate domain
- ❌ Tournament data (`tournaments`, `tourneyregister`) — separate domain
- ❌ Employee data (`employees`, `employee_attendance`) — separate domain

---

## 📐 **Schema Design**

### **Collection 1: `presets`**

```javascript
{
  // ── Common (all preset_types) ──
  _id: ObjectId,
  preset_type: "preset" | "tpbuild" | "temp" | "misc",  // REQUIRED discriminator
  collection: "presets" | "tpbuilds" | "tempproducts" | "misc",  // Legacy source
  
  // ── Identity ──
  productid: String,         // Unique identifier
  title: String,             // Display name
  slug: String,              // URL-friendly identifier
  
  // ── Configuration (varies by preset_type) ──
  type: String,              // pc144hz, pc240hz, vr, ps5, etc.
  list: Array,               // { item_code, name, price, duration } — arcade/package items
  build_components: Array,   // Component productids — PC builds
  channel: String,           // Sales channel (tpbuilds)
  total_price: Number,       // Calculated total
  
  // ── Metadata ──
  description: String,
  images: Array,
  specs: Object,
  config: JSON,              // Flexible config per type
  
  // ── Tenant ──
  bg_code: String,
  div_code: String,
  branch_code: String,
  
  // ── Lifecycle ──
  active: Boolean,
  delete_flag: Boolean,
  created_by: String,
  updated_by: String,
  created_date: DateTime,
  updated_date: DateTime
}
```

**Indexes:**
```javascript
db.presets.createIndex({ bg_code: 1, div_code: 1, preset_type: 1 })
db.presets.createIndex({ bg_code: 1, div_code: 1, branch_code: 1 })
db.presets.createIndex({ bg_code: 1, div_code: 1, active: 1 })
db.presets.createIndex({ type: 1 })
db.presets.createIndex({ productid: 1 }, { unique: true })
```

### **Collection 2: `products`**

```javascript
{
  // ── Identity ──
  _id: ObjectId,
  collection: "products" | "stock_register" | "indentproduct",  // Legacy source
  
  // ── Product catalog fields ──
  productid: String,         // Unique identifier (REQUIRED)
  title: String,             // Display name
  description: String,
  type: String,              // Category type
  category: String,          // Sub-category
  
  // ── Pricing ──
  price: Number,
  msrp: Number,
  cost: Number,
  avgprice: Number,
  
  // ── Tax & logistics ──
  hsncode: String,
  gst_rate: Number,
  weight: Number,
  dimensions: Object,
  
  // ── Stock (from stock_register) ──
  serial_no: String,         // If serialized
  upc_no: String,
  ean_no: String,
  quantity: Number,          // Stock quantity
  branch_code: String,       // Stock branch
  
  // ── Media ──
  images: Array,
  specs: Object,
  
  // ── Tenant ──
  bg_code: String,
  div_code: String,
  
  // ── Lifecycle ──
  active: Boolean,
  delete_flag: Boolean,
  is_consumable: Boolean,
  created_by: String,
  updated_by: String,
  created_date: DateTime,
  updated_date: DateTime
}
```

**Indexes:**
```javascript
db.products.createIndex({ bg_code: 1, div_code: 1 })
db.products.createIndex({ bg_code: 1, div_code: 1, active: 1, delete_flag: 1 })
db.products.createIndex({ productid: 1 }, { unique: true })
db.products.createIndex({ category: 1 })
db.products.createIndex({ type: 1 })
```

---

## 🏗️ **Implementation Plan**

### **Phase 1: Migration Script**

```python
# plat/management/commands/migrate_catalog_consolidation.py
"""
Consolidate all MongoDB catalog collections → 2 collections.

presets:    presets + tpbuilds + tempproducts + misc
products:   products + stock_register + indentproduct

Usage:
    python manage.py migrate_catalog_consolidation --dry-run
    python manage.py migrate_catalog_consolidation
    python manage.py migrate_catalog_consolidation --validate
"""

from django.core.management.base import BaseCommand
from backend.utils import get_collection, get_mongo_client, decode_result


class Command(BaseCommand):
    help = 'Consolidate MongoDB catalog → presets + products (2 collections)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--validate', action='store_true')

    def handle(self, *args, **options):
        if options['validate']:
            self.validate()
            return
        if options['dry_run']:
            self.dry_run()
            return
        self.execute()

    def dry_run(self):
        db = get_mongo_client()['KungOS_Mongo_One']
        self.stdout.write('=== Current Collections ===')
        for col in ['presets', 'tpbuilds', 'tempproducts', 'misc',
                     'products', 'stock_register', 'indentproduct']:
            count = db[col].count_documents({})
            self.stdout.write(f'  {col}: {count}')
        self.stdout.write('')
        self.stdout.write('=== Target ===')
        self.stdout.write('  presets:    presets + tpbuilds + tempproducts + misc')
        self.stdout.write('  products:   products + stock_register + indentproduct')

    def execute(self):
        db = get_mongo_client()['KungOS_Mongo_One']
        presets_col = db['presets']
        products_col = db['products']

        # ── Merge into presets ──
        self.stdout.write('Merging into presets...')
        for src_col, preset_type in [
            ('presets', 'preset'),
            ('tpbuilds', 'tpbuild'),
            ('tempproducts', 'temp'),
            ('misc', 'misc'),
        ]:
            for doc in db[src_col].find({}):
                doc['preset_type'] = preset_type
                doc['collection'] = src_col
                # Ensure unique productid
                if 'productid' not in doc:
                    doc['productid'] = str(doc['_id'])
                presets_col.replace_one(
                    {'productid': doc['productid']}, doc, upsert=True
                )
            self.stdout.write(f'  {src_col} → presets ({preset_type}): done')

        # ── Merge into products ──
        self.stdout.write('Merging into products...')
        for src_col in ['products', 'stock_register', 'indentproduct']:
            for doc in db[src_col].find({}):
                doc['collection'] = src_col
                # Ensure unique productid
                if 'productid' not in doc:
                    doc['productid'] = str(doc['_id'])
                products_col.replace_one(
                    {'productid': doc['productid']}, doc, upsert=True
                )
            self.stdout.write(f'  {src_col} → products: done')

        # ── Create indexes ──
        self.stdout.write('Creating indexes...')
        presets_col.create_index([('bg_code', 1), ('div_code', 1), ('preset_type', 1)])
        presets_col.create_index([('bg_code', 1), ('div_code', 1), ('active', 1)])
        presets_col.create_index([('productid', 1)], unique=True)
        presets_col.create_index([('type', 1)])

        products_col.create_index([('bg_code', 1), ('div_code', 1), ('active', 1), ('delete_flag', 1)])
        products_col.create_index([('productid', 1)], unique=True)
        products_col.create_index([('category', 1)])
        products_col.create_index([('type', 1)])

        self.stdout.write(self.style.SUCCESS('✅ Consolidation complete'))

    def validate(self):
        presets = get_collection('presets')
        products = get_collection('products')

        self.stdout.write('=== Presets ===')
        for pt in ['preset', 'tpbuild', 'temp', 'misc']:
            count = presets.count_documents({'preset_type': pt})
            self.stdout.write(f'  {pt}: {count}')
        self.stdout.write(f'  total: {presets.count_documents({})}')

        self.stdout.write('=== Products ===')
        for col in ['products', 'stock_register', 'indentproduct']:
            count = products.count_documents({'collection': col})
            self.stdout.write(f'  {col}: {count}')
        self.stdout.write(f'  total: {products.count_documents({})}')
```

### **Phase 2: ViewSet Updates**

#### Update `PresetViewSet` → reads from consolidated `presets`

```python
class PresetViewSet(BaseProductsViewSet):
    """Build presets & configurations.
    
    Consolidated from: presets, tpbuilds, tempproducts, misc
    Collection: presets (with preset_type discriminator)
    """
    COLLECTION_NAME = 'presets'
    PERMISSION_CODENAME = 'presets'

    def list(self, request):
        filters = self.apply_filter_params(request)
        # If no preset_type filter, default to all
        collection, tenant_filter = self.get_collection(request)
        # ... existing implementation with filters
```

#### Update `ProductViewSet` → reads from consolidated `products`

```python
class ProductViewSet(BaseProductsViewSet):
    """Product catalog.
    
    Consolidated from: products, stock_register, indentproduct
    Collection: products
    """
    COLLECTION_NAME = 'products'
    PERMISSION_CODENAME = 'products'
```

#### Remove or redirect old ViewSets

| Old ViewSet | Action |
|-------------|--------|
| `TPBuildViewSet` | Redirect to `PresetViewSet` with `preset_type=tpbuild` filter |
| `TempProductViewSet` | Redirect to `PresetViewSet` with `preset_type=temp` filter |
| `InventoryViewSet` (stock_register) | Redirect to `ProductViewSet` with `collection=stock_register` filter |
| `IndentViewSet` | Redirect to `ProductViewSet` with `collection=indentproduct` filter |

#### URL routing — preserve old endpoints via redirects

```python
# domains/products/urls.py
# Old endpoints still work — just point to consolidated ViewSets
path('presets', PresetViewSet.as_view({'get': 'list', 'post': 'create'}))
path('tp-builds', PresetViewSet.as_view({'get': 'list'}))  # preset_type=tpbuild
path('tempproducts', PresetViewSet.as_view({'get': 'list'}))  # preset_type=temp
path('products', ProductViewSet.as_view({'get': 'list', 'post': 'create'}))
path('inventory', ProductViewSet.as_view({'get': 'list'}))  # collection=stock_register
```

### **Phase 3: Update Cafe Menu Sync**

The `sync_cafe_menu` command (from separate handoff) reads from:
- `presets` collection → arcade packages (now includes tpbuilds, tempproducts, misc)
- `products` collection → F&B items (now includes stock_register, indentproduct)

No changes needed to the sync logic — it already reads from these collection names.

### **Phase 4: Validation**

```bash
# 1. Dry run
python manage.py migrate_catalog_consolidation --dry-run

# 2. Execute
python manage.py migrate_catalog_consolidation

# 3. Validate
python manage.py migrate_catalog_consolidation --validate

# Expected:
# === Presets ===
#   preset: 6
#   tpbuild: 123
#   temp: ?
#   misc: ?
#   total: ~150+
# === Products ===
#   products: 82
#   stock_register: 194
#   indentproduct: ?
#   total: ~300+
```

---

## 📊 **Rollback Plan**

```bash
# 1. Drop consolidated collections
python3 -c "
from backend.utils import get_mongo_client
db = get_mongo_client()['KungOS_Mongo_One']
db['presets'].drop()
db['products'].drop()
print('✅ Dropped consolidated collections')
"

# 2. Verify originals intact
python3 -c "
from backend.utils import get_mongo_client
db = get_mongo_client()['KungOS_Mongo_One']
for col in ['presets', 'tpbuilds', 'tempproducts', 'misc',
            'products', 'stock_register', 'indentproduct']:
    print(f'{col}: {db[col].count_documents({})}')
"
```

---

## ⚠️ **Risks & Mitigations**

| Risk | Impact | Mitigation |
|------|--------|------------|
| `productid` collisions between collections | HIGH | Use `{productid: 1}` unique index; `replace_one` with upsert handles duplicates |
| Field name mismatches (e.g., `title` vs `name`) | MEDIUM | Map legacy fields during migration; preserve both |
| ViewSet regression after consolidation | MEDIUM | Preserve old URL endpoints via redirects; gradual cutover |
| Frontend breakage | LOW | No frontend changes in this phase; API contract preserved |
| `misc` collection has non-preset data | LOW | Filter by `type` field in `misc`; skip non-preset entries |

---

## 📝 **Post-Migration Checklist**

- [ ] Migration script created (`plat/management/commands/migrate_catalog_consolidation.py`)
- [ ] Dry run completed (counts match expectations)
- [ ] Migration executed
- [ ] Validation passed (counts per `preset_type` / `collection` correct)
- [ ] All ViewSets updated to read from consolidated collections
- [ ] Old URL endpoints redirected to new ViewSets
- [ ] All tests passing
- [ ] Manual API validation (presets, products, tp-builds, inventory endpoints)
- [ ] Cafe menu sync verified against new collections
- [ ] Rollback procedure documented
- [ ] Original collections preserved (not dropped)

---

## 🔗 **References**

- **Cafe menu analysis:** `01-07-2026_cafe_menu_preset_inconsistency_xyz789.md`
- **Inventory migration:** `domains/inventory/migrations/0002_migrate_legacy_inventory.py`
- **Current ViewSets:** `domains/products/viewsets.py`
- **MongoDB audit spec:** `/home/chief/llm-wiki/mongo-collection-audit-2026-05-14.md` §5-6

---

## 📅 **Timeline**

| Step | Duration | Dependencies |
|------|----------|--------------|
| Phase 1: Migration script | 30 min | None |
| Phase 2: ViewSet updates | 60 min | Phase 1 |
| Phase 3: Cafe menu sync verification | 15 min | Phase 1 |
| Phase 4: Validation | 30 min | Phase 2-3 |
| **Total** | **~2.5 hours** | — |

---

**Status:** ✅ Analysis Complete — Ready for Implementation  
**Assigned to:** Backend Developer  
**Reviewer:** Tech Lead  
**Last Updated:** 2026-07-01
