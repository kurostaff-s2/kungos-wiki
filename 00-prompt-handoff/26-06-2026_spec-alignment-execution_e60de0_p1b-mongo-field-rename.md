# Phase 1B: MongoDB Field Rename (M3)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 1B of 5 (parallel with 1A, 1C)
**Dependencies:** None (can start immediately, parallel with 1A)
**Estimated effort:** ~60 min / multi-session (audit + migration + verification)

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p1b` |
| Entity type | `handoff` |
| Short description | Rename tenant fields across all MongoDB collections: `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code`. |
| Status | `draft` |
| Source references | `mongodb_schema.md`, `migration_spec.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute MongoDB field rename — audit collections, migrate data, update queries |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `backend/mongo.py` (TenantCollection class)
- `teams/kurostaff/views.py` (MongoDB queries)
- `teams/financial.py` (MongoDB queries)
- `teams/estimates.py` (MongoDB queries)
- `teams/service_requests.py` (MongoDB queries)
- `teams/products.py` (MongoDB queries)
- `teams/outward_invoices.py` (MongoDB queries)
- `teams/inward_invoices.py` (MongoDB queries)
- `teams/employees.py` (MongoDB queries)
- `domains/*/viewsets.py` (MongoDB queries)
- `careers/views.py` (MongoDB queries)
**Related codebases:** None

## What This Phase Delivers

All MongoDB collections use canonical field names: `bg_code` (not `bgcode`), `div_code` (not `division`), `branch_code` (not `branch`). The `TenantCollection` class injects canonical field names. All query code uses canonical names. Cross-tenant isolation is verified (no data leakage).

**Critical risk:** During migration window, both old and new field names must be supported. If `TenantCollection` injects `bg_code` but the collection still uses `bgcode`, tenant isolation fails silently.

## Pre-Flight Checklist

- [ ] Phase 8B is marked complete (Commit `70b892d`)
- [ ] MongoDB connection is accessible
- [ ] Backup of MongoDB collections taken (before migration)
- [ ] List of all MongoDB collections and their field names identified

## Implementation Steps

### Step 1: Audit MongoDB Collections

Identify all MongoDB collections and their current field names:

```python
# Run in Django shell
from backend.mongo import get_database
db = get_database()
for collection_name in db.list_collection_names():
    collection = db[collection_name]
    sample = collection.find_one()
    if sample:
        print(f"\n{collection_name}:")
        for key in sample.keys():
            if 'bg' in key.lower() or 'div' in key.lower() or 'branch' in key.lower():
                print(f"  - {key}")
```

**Expected findings:**
- `bgcode` (legacy) → should be `bg_code`
- `division` (legacy) → should be `div_code`
- `branch` (legacy) → should be `branch_code`

### Step 2: Audit Code References

Search for all code references to legacy field names:

```bash
# Search for bgcode
grep -rn "bgcode\|bg_code" --include="*.py" | grep -v __pycache__ | grep -v venv/

# Search for division (in MongoDB context)
grep -rn "'division'\|\"division\"\|division=" --include="*.py" | grep -v __pycache__ | grep -v venv/

# Search for branch (in MongoDB context)
grep -rn "'branch'\|\"branch\"\|branch=" --include="*.py" | grep -v __pycache__ | grep -v venv/
```

**Create a mapping of all files that need updates.**

### Step 3: Update TenantCollection

Read `backend/mongo.py` and verify `TenantCollection` uses canonical field names:

```python
class TenantCollection:
    def __init__(self, collection_name, bg_code):
        self.collection = get_database()[collection_name]
        self.bg_code = bg_code
    
    def find(self, **kwargs):
        # Inject bg_code (canonical name)
        kwargs['bg_code'] = self.bg_code
        return self.collection.find(kwargs)
    
    def find_one(self, **kwargs):
        kwargs['bg_code'] = self.bg_code
        return self.collection.find_one(kwargs)
```

**Critical:** If `TenantCollection` currently injects `bgcode` (legacy), change it to `bg_code`. Add an assertion to verify the field exists in the result:

```python
def find(self, **kwargs):
    kwargs['bg_code'] = self.bg_code
    results = list(self.collection.find(kwargs))
    # Assert tenant isolation
    for doc in results:
        assert doc.get('bg_code') == self.bg_code, \
            f"Tenant isolation violation: expected {self.bg_code}, got {doc.get('bg_code')}"
    return results
```

### Step 4: Migrate Data

Create a migration script for each collection:

```python
# Pseudocode for data migration
def migrate_collection(collection_name, old_field, new_field):
    collection = db[collection_name]
    
    # Find documents with old field
    count = collection.count_documents({old_field: {'$exists': True}})
    print(f"Migrating {count} documents in {collection_name}")
    
    # Rename field
    collection.update_many(
        {old_field: {'$exists': True}},
        [{'$set': {new_field: f"${old_field}"}}],
        # Remove old field after rename
        [{'$unset': [old_field]}]
    )
    
    # Verify migration
    remaining = collection.count_documents({old_field: {'$exists': True}})
    print(f"Remaining with old field: {remaining}")
    assert remaining == 0
```

**Run for each collection:**
- `migrate_collection('orders', 'bgcode', 'bg_code')`
- `migrate_collection('orders', 'division', 'div_code')`
- `migrate_collection('orders', 'branch', 'branch_code')`
- (repeat for all collections)

### Step 5: Update Query Code

Update all files that reference legacy field names. Use the mapping from Step 2.

**Pattern replacements:**
- `doc['bgcode']` → `doc['bg_code']`
- `doc.get('bgcode')` → `doc.get('bg_code')`
- `{'bgcode': value}` → `{'bg_code': value}`
- `doc['division']` → `doc['div_code']`
- `doc.get('division')` → `doc.get('div_code')`
- `{'division': value}` → `{'div_code': value}`
- `doc['branch']` → `doc['branch_code']`
- `doc.get('branch')` → `doc.get('branch_code')`
- `{'branch': value}` → `{'branch_code': value}`

**Be careful with `division` — it's a common word. Only replace in MongoDB context (document fields, query filters).**

### Step 6: Add Backward-Compat Read Path (Temporary)

During migration window (1 sprint), support both old and new field names:

```python
def get_tenant_field(doc, field_name):
    """Get tenant field with backward compat."""
    # Try canonical name first
    value = doc.get(field_name)
    if value is not None:
        return value
    
    # Fall back to legacy name
    legacy_map = {
        'bg_code': 'bgcode',
        'div_code': 'division',
        'branch_code': 'branch',
    }
    legacy_name = legacy_map.get(field_name)
    if legacy_name and legacy_name in doc:
        return doc[legacy_name]
    
    return None
```

**Action:** Add this helper to `backend/mongo.py` and use it in all query code. Remove after 1 sprint verification.

### Step 7: Verify Tenant Isolation

Test that cross-tenant data isolation works:

```python
def test_tenant_isolation():
    # Create two tenants
    bg_a = 'KURO0001'
    bg_b = 'KURO0002'
    
    # Query tenant A's data
    col_a = TenantCollection('orders', bg_a)
    results_a = list(col_a.find())
    
    # Verify all results belong to tenant A
    for doc in results_a:
        assert doc.get('bg_code') == bg_a, \
            f"Tenant isolation violation: expected {bg_a}, got {doc.get('bg_code')}"
    
    # Query tenant B's data
    col_b = TenantCollection('orders', bg_b)
    results_b = list(col_b.find())
    
    # Verify no overlap
    ids_a = {doc['_id'] for doc in results_a}
    ids_b = {doc['_id'] for doc in results_b}
    assert ids_a.isdisjoint(ids_b), "Cross-tenant data leakage detected"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/mongo.py` | TenantCollection field names + backward compat |
| Modify | `teams/kurostaff/views.py` | Update MongoDB query field names |
| Modify | `teams/financial.py` | Update MongoDB query field names |
| Modify | `teams/estimates.py` | Update MongoDB query field names |
| Modify | `teams/service_requests.py` | Update MongoDB query field names |
| Modify | `teams/products.py` | Update MongoDB query field names |
| Modify | `teams/outward_invoices.py` | Update MongoDB query field names |
| Modify | `teams/inward_invoices.py` | Update MongoDB query field names |
| Modify | `teams/employees.py` | Update MongoDB query field names |
| Modify | `domains/*/viewsets.py` | Update MongoDB query field names |
| Modify | `careers/views.py` | Update MongoDB query field names |
| Create | `tests/test_mongo_field_rename.py` | Verify field naming + tenant isolation |

## Phase-Specific Tests

Create `tests/test_mongo_field_rename.py`:

1. **Test canonical field names in TenantCollection:**
   ```python
   def test_tenant_collection_uses_canonical_fields():
       col = TenantCollection('test', 'KURO0001')
       # Verify bg_code is injected (not bgcode)
       assert 'bg_code' in col.find().limit(1)
   ```

2. **Test backward compat helper:**
   ```python
   def test_backward_compat_helper():
       doc_legacy = {'bgcode': 'KURO0001'}
       doc_canonical = {'bg_code': 'KURO0001'}
       assert get_tenant_field(doc_legacy, 'bg_code') == 'KURO0001'
       assert get_tenant_field(doc_canonical, 'bg_code') == 'KURO0001'
   ```

3. **Test tenant isolation:**
   ```python
   def test_tenant_isolation():
       # As above — verify no cross-tenant leakage
       pass
   ```

4. **Test no legacy field names in code:**
   ```python
   def test_no_legacy_field_names_in_code():
       # Grep for legacy field names in Python files
       # Exclude backward compat helper
       pass
   ```

## Completion Gate

- [ ] All MongoDB collections migrated to canonical field names
- [ ] `TenantCollection` injects `bg_code` (not `bgcode`)
- [ ] All query code uses canonical field names
- [ ] Backward compat helper added (temporary)
- [ ] Tenant isolation verified (no cross-tenant leakage)
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Notes for Next Phase

- Phase 1A (Identity migration) is independent — can run in parallel.
- Phase 2A (RBAC FK migration) depends on Phase 1A, not this phase.
- After this phase, legacy field names are supported via backward compat helper for 1 sprint.
- Remove backward compat helper after 1 sprint verification (no legacy fields in any collection).

## Caveats

1. **Silent failure risk:** If `TenantCollection` injects `bg_code` but the collection still uses `bgcode`, queries return empty results (no error). **Mitigation:** Add assertion in `TenantCollection.find()` that verifies expected field exists in results.

2. **Division field ambiguity:** `division` is a common word. Only replace in MongoDB document context (not Django model fields, URL parameters, or variable names).

3. **Data migration atomicity:** MongoDB `update_many` is atomic per document but not across the collection. If migration is interrupted, some documents may have new names and others old. **Mitigation:** Run migration during low-traffic window. Use backward compat helper during transition.
