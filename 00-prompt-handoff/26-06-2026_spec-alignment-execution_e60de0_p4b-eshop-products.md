# Phase 4B: E-Commerce Product Collections — MongoDB Consolidation (M5)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 4B of 5 (parallel with 4A, 4C)
**Dependencies:** Phase 1A (tenant context must be active; MongoDB consolidation must be in place)
**Estimated effort:** ~45 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p4b` |
| Entity type | `handoff` |
| Short description | Consolidate 13 e-commerce product collections from `kuro-gaming-dj-backend` Mongo into `KungOS_Mongo_One` with tenant fields, indexes, and schema validation. |
| Status | `draft` |
| Source references | `migration_spec.md` §6, `mongodb_schema.md`, `tenant_collection.py` |
| Generated | `26-06-2026` |
| Next action / owner | Execute MongoDB consolidation — export, add tenant fields, import, index, validate |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Source database:** `kuro-gaming-dj-backend` Mongo (separate from `KungOS_Mongo_One`)
**Target database:** `KungOS_Mongo_One` (consolidated Mongo DB)
**Key files for this phase:**
- `plat/tenant/collection.py` (`TenantCollection` wrapper — all e-commerce views must use this)
- `backend/utils.py` (`get_collection` — raw Mongo access)
- `plat/tenant/exceptions.py` (`TenantContextMissing`)
- Source Mongo: `kuro-gaming-dj-backend` database
**Related codebases:** `kuro-gaming-dj-backend` (source of 13 collections)

## What This Phase Delivers

13 e-commerce product collections migrated from `kuro-gaming-dj-backend` Mongo into `KungOS_Mongo_One` with canonical tenant fields (`bg_code`, `div_code`, `branch_code`). Compound indexes on `(bg_code, div_code)` created. JSON Schema validation enabled. All e-commerce views use `TenantCollection` wrapper for tenant-scoped access. No PostgreSQL models — this is a pure MongoDB consolidation.

## Target Collections

| Collection | Purpose | Source DB |
|---|---|---|
| `prods` | Product catalog | `kuro-gaming-dj-backend` |
| `builds` | Pre-built PC builds | `kuro-gaming-dj-backend` |
| `kgbuilds` | Kuro Gaming builds | `kuro-gaming-dj-backend` |
| `custombuilds` | Custom PC builds (ordered, immutable copies) | `kuro-gaming-dj-backend` |
| `components` | Hardware components | `kuro-gaming-dj-backend` |
| `accessories` | PC accessories | `kuro-gaming-dj-backend` |
| `monitors` | Monitor catalog | `kuro-gaming-dj-backend` |
| `networking` | Networking equipment | `kuro-gaming-dj-backend` |
| `external` | External products | `kuro-gaming-dj-backend` |
| `games` | Game catalog | `kuro-gaming-dj-backend` |
| `kurodata` | CMS content | `kuro-gaming-dj-backend` |
| `lists` | Preset lists | `kuro-gaming-dj-backend` |
| `presets` | Preset configurations | `kuro-gaming-dj-backend` |

## Implementation Steps

### Step 1: Export Collections from Source Mongo

Connect to `kuro-gaming-dj-backend` Mongo and export all 13 collections.

```python
from pymongo import MongoClient

SOURCE_URI = "mongodb://<source_host>:27017"
TARGET_URI = "mongodb://<target_host>:27017"

source_db = MongoClient(SOURCE_URI)["kuro-gaming-dj-backend"]
target_db = MongoClient(TARGET_URI)["KungOS_Mongo_One"]

COLLECTIONS = [
    "prods", "builds", "kgbuilds", "custombuilds",
    "components", "accessories", "monitors", "networking",
    "external", "games", "kurodata", "lists", "presets",
]

# Step 1a: Export and count
for coll_name in COLLECTIONS:
    source_coll = source_db[coll_name]
    count = source_coll.count_documents({})
    print(f"  {coll_name}: {count} documents")
```

**Validation gate:** All 13 collections exist in source with non-zero document counts.

### Step 2: Add Tenant Fields to Each Document

Every document in every collection must have canonical tenant fields. Since these are product catalog collections (not user data), they belong to a specific business group.

```python
# Step 2a: Determine tenant assignment
# E-commerce products belong to a specific BG (e.g., Kuro Gaming)
DEFAULT_BG_CODE = "KURO0001"  # Adjust based on actual tenant assignment
DEFAULT_DIV_CODE = "KURO0001_001"  # Default division
DEFAULT_BRANCH_CODE = None  # Products are typically branch-agnostic

def add_tenant_fields(document: dict) -> dict:
    """Add canonical tenant fields to a document."""
    document = dict(document)  # Don't mutate source
    document.setdefault("bg_code", DEFAULT_BG_CODE)
    document.setdefault("div_code", DEFAULT_DIV_CODE)
    document.setdefault("branch_code", DEFAULT_BRANCH_CODE)
    return document

# Step 2b: Transform all documents in batch
batch_size = 1000
for coll_name in COLLECTIONS:
    source_coll = source_db[coll_name]
    target_coll = target_db[coll_name]
    
    cursor = source_coll.find({})
    batch = []
    for doc in cursor:
        doc = add_tenant_fields(doc)
        batch.append(doc)
        
        if len(batch) >= batch_size:
            target_coll.insert_many(batch)
            batch = []
    
    # Insert remaining
    if batch:
        target_coll.insert_many(batch)
    
    print(f"  {coll_name}: migrated")
```

**Validation gate:**
```python
# Verify all documents have tenant fields
for coll_name in COLLECTIONS:
    target_coll = target_db[coll_name]
    missing_bg = target_coll.count_documents({"bg_code": {"$exists": False}})
    missing_div = target_coll.count_documents({"div_code": {"$exists": False}})
    assert missing_bg == 0, f"{coll_name}: {missing_bg} docs missing bg_code"
    assert missing_div == 0, f"{coll_name}: {missing_div} docs missing div_code"
```

### Step 3: Create Compound Indexes

Create `(bg_code, div_code)` compound indexes on all 13 collections for efficient tenant-scoped queries.

```python
for coll_name in COLLECTIONS:
    target_coll = target_db[coll_name]
    
    # Create compound tenant index
    target_coll.create_index(
        [("bg_code", 1), ("div_code", 1)],
        name="idx_tenant_bg_div"
    )
    
    # Create individual bg_code index for tenant-only queries
    target_coll.create_index(
        [("bg_code", 1)],
        name="idx_tenant_bg"
    )
    
    print(f"  {coll_name}: indexes created")
```

**Validation gate:**
```python
# Verify indexes exist
for coll_name in COLLECTIONS:
    target_coll = target_db[coll_name]
    indexes = target_coll.index_information()
    assert "idx_tenant_bg_div" in indexes, f"{coll_name}: missing compound index"
    assert "idx_tenant_bg" in indexes, f"{coll_name}: missing bg_code index"
```

### Step 4: Enable JSON Schema Validation

Enable schema validation on all collections to enforce canonical field presence and format.

```python
# Step 4a: Define JSON Schema validator
SCHEMA_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["bg_code"],
        "properties": {
            "bg_code": {
                "bsonType": "string",
                "pattern": "^[A-Z]{4}\\d{4}$",
                "description": "Business group code — required"
            },
            "div_code": {
                "bsonType": "string",
                "pattern": "^[A-Z]{4}\\d{4}_\\d{3}$",
                "description": "Division code"
            },
            "branch_code": {
                "bsonType": ["string", "null"],
                "description": "Branch code (nullable for branch-agnostic products)"
            }
        }
    }
}

# Step 4b: Apply validation to each collection
# Note: MongoDB requires creating a new collection with validator,
# then dropping the old one. For existing collections, use collMod.
for coll_name in COLLECTIONS:
    target_db.command({
        "collMod": coll_name,
        "validator": SCHEMA_VALIDATOR,
        "validationLevel": "moderate",  # Warn but don't block existing bad docs
        "validationAction": "warn"
    })
    print(f"  {coll_name}: schema validation enabled (moderate)")
```

**Validation gate:**
```python
# Test schema validation
test_doc = {"_id": "test_invalid", "bg_code": "INVALID"}
try:
    target_db["prods"].insert_one(test_doc)
    print("  ⚠️ Schema validation not blocking (expected for moderate level)")
except Exception as e:
    print(f"  ✅ Schema validation blocking invalid docs: {e}")
```

### Step 5: Update E-Commerce Views to Use `TenantCollection`

All e-commerce views must use `TenantCollection` for tenant-scoped access. This ensures all queries are automatically filtered by `bg_code`, `div_code`, and `branch_code`.

```python
# domains/eshop/views.py — Example usage
from plat.tenant.collection import TenantCollection

class ProductViewSet:
    """E-commerce product viewset using TenantCollection."""
    
    def list(self, request):
        products = TenantCollection("prods")
        docs = products.find({})  # Auto-filtered by tenant context
        return Response([self._to_serialized(doc) for doc in docs])
    
    def retrieve(self, request, pk=None):
        products = TenantCollection("prods")
        doc = products.find_one({"product_id": pk})
        if not doc:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(self._to_serialized(doc))
    
    def create(self, request):
        products = TenantCollection("prods")
        doc = products.insert_one(request.data)
        return Response({"product_id": doc.inserted_id}, status=201)
    
    def _to_serialized(self, doc):
        """Convert Mongo document to response format."""
        return {
            "product_id": doc.get("product_id") or doc.get("_id"),
            "name": doc.get("name"),
            "description": doc.get("description"),
            "price": doc.get("price"),
            "stock_quantity": doc.get("stock_quantity", 0),
            "is_active": doc.get("is_active", True),
        }
```

**Collections mapping for views:**

| ViewSet | TenantCollection Name |
|---|---|
| Product list/detail | `prods` |
| Build list/detail | `builds` |
| KG Build list/detail | `kgbuilds` |
| Custom Build list/detail | `custombuilds` |
| Component list/detail | `components` |
| Accessory list/detail | `accessories` |
| Monitor list/detail | `monitors` |
| Networking list/detail | `networking` |
| External product list/detail | `external` |
| Game list/detail | `games` |
| CMS content | `kurodata` |
| Preset list/detail | `lists`, `presets` |

**Note:** The `lists` collection name conflicts with Python keywords. Use `TenantCollection("lists")` directly — do not rename.

### Step 6: Wire Routes

Ensure e-commerce routes are configured in `backend/urls.py`:

```python
# backend/urls.py
from domains.eshop import urls as eshop_urls

urlpatterns = [
    # ... existing routes
    path('api/v1/eshop/', include(eshop_urls)),
]
```

Update `domains/eshop/urls.py` to register viewsets:

```python
# domains/eshop/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from domains.eshop.views import (
    ProductViewSet, BuildViewSet, KGBuildViewSet,
    ComponentViewSet, AccessoryViewSet, MonitorViewSet,
    NetworkingViewSet, ExternalProductViewSet, GameViewSet,
)

router = DefaultRouter()
router.register('products', ProductViewSet, basename='product')
router.register('builds', BuildViewSet, basename='build')
router.register('kg-builds', KGBuildViewSet, basename='kg-build')
router.register('components', ComponentViewSet, basename='component')
router.register('accessories', AccessoryViewSet, basename='accessory')
router.register('monitors', MonitorViewSet, basename='monitor')
router.register('networking', NetworkingViewSet, basename='networking')
router.register('external', ExternalProductViewSet, basename='external')
router.register('games', GameViewSet, basename='game')

urlpatterns = [
    path('', include(router.urls)),
]
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `plat/tenant/mongo_migration.py` | Migration script (Steps 1-4) |
| Modify | `domains/eshop/views.py` | Use `TenantCollection` for all data access |
| Modify | `domains/eshop/urls.py` | Register viewsets |
| Modify | `backend/urls.py` | Wire `/api/v1/eshop/` routes |
| Create | `tests/test_eshop_tenant.py` | Verify tenant isolation on e-commerce |

## Phase-Specific Tests

Create `tests/test_eshop_tenant.py`:

1. **Test all collections migrated with tenant fields:**
   ```python
   def test_all_collections_have_tenant_fields():
       for coll_name in COLLECTIONS:
           docs = db[coll_name].find({})
           for doc in docs:
               assert 'bg_code' in doc, f"{coll_name}: missing bg_code"
               assert 'div_code' in doc, f"{coll_name}: missing div_code"
   ```

2. **Test compound indexes exist:**
   ```python
   def test_compound_indexes_exist():
       for coll_name in COLLECTIONS:
           indexes = db[coll_name].index_information()
           assert "idx_tenant_bg_div" in indexes
   ```

3. **Test TenantCollection filters by tenant:**
   ```python
   def test_tenant_collection_filters():
       # Set tenant context to KURO0001
       with tenant_context("KURO0001"):
           products = TenantCollection("prods")
           docs = list(products.find({}))
           for doc in docs:
               assert doc["bg_code"] == "KURO0001"
   ```

4. **Test tenant isolation (cross-tenant leak prevention):**
   ```python
   def test_cross_tenant_isolation():
       # Query as KURO0001, verify no KURO0002 docs returned
       with tenant_context("KURO0001"):
           products = TenantCollection("prods")
           docs = list(products.find({}))
           for doc in docs:
               assert doc["bg_code"] == "KURO0001"
   ```

5. **Test schema validation blocks invalid inserts:**
   ```python
   def test_schema_validation():
       # Insert doc without bg_code — should be rejected or warned
       bad_doc = {"_id": "test", "name": "Invalid"}
       result = db["prods"].insert_one(bad_doc)
       # With moderate level, this should warn but not block
       assert result.acknowledged
   ```

## Completion Gate

- [ ] All 13 collections exported from `kuro-gaming-dj-backend`
- [ ] All documents have `bg_code`, `div_code`, `branch_code` fields
- [ ] Compound indexes `(bg_code, div_code)` created on all collections
- [ ] JSON Schema validation enabled (moderate level)
- [ ] All e-commerce views use `TenantCollection` wrapper
- [ ] Routes wired under `/api/v1/eshop/`
- [ ] Tenant isolation verified (no cross-tenant data leak)
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Post-Migration Verification (Gate)

```python
python manage.py test tests/test_eshop_tenant.py -v 2
```

**Expected:**
- ✅ All 13 collections have tenant fields (0 missing)
- ✅ All compound indexes built
- ✅ TenantCollection filters correctly
- ✅ Cross-tenant isolation verified
- ✅ Schema validation active
- ✅ All eshop endpoints accessible via `/api/v1/eshop/`

## Notes for Next Phase

- Phase 4C (Legacy cleanup) can run in parallel — it drops the old `misc` collection and legacy patterns.
- Phase 5 (Production wiring) depends on this phase — must verify e-shop endpoints respond correctly.
- The 12 collections stay in MongoDB (`KungOS_Mongo_One`). No PostgreSQL models are created.
- The `TenantCollection` wrapper is the only valid access pattern — direct `get_collection()` calls must not be used in application code.

## Consistency Rules

**This phase defers to:**
- Migration ordering: `migration_spec.md` §6 (M6: E-Commerce Products Consolidation)
- MongoDB schema: `mongodb_schema.md` (TenantCollection wrapper)
- Canonical naming: `CANONICAL_NAMING.md` (`bg_code`, `div_code`, `branch_code`)

**This phase does NOT redefine:**
- Response shapes (Phase 3A handles response envelope)
- PostgreSQL schema (Phase 4A handles orders)
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._

