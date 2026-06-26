# Phase 4B: E-Commerce Product Collections (M5)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 4B of 5 (parallel with 4A, 4C)
**Dependencies:** Phase 1A (Identity data migration must be complete)
**Estimated effort:** ~45 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p4b` |
| Entity type | `handoff` |
| Short description | Implement e-commerce product collections in PostgreSQL. 12 collections total. |
| Status | `draft` |
| Source references | `migration_spec.md`, `postgresql_schema.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute e-commerce migration — create models, migrate data, update viewsets |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `domains/eshop/models.py` (new/updated models)
- `domains/eshop/migrations/` (new migrations)
- `domains/eshop/viewsets.py` (update to use PostgreSQL)
- `tests/test_eshop_products.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

E-commerce product collections implemented in PostgreSQL. 12 collections total. Product catalog functional via `/api/v1/eshop/` endpoints.

## Implementation Steps

### Step 1: Create PostgreSQL Models

Read `migration_spec.md` for target schema. Create models in `domains/eshop/models.py`:

```python
class Product(models.Model):
    product_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    bg_code = models.CharField(max_length=10, db_index=True)
    category = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    stock_quantity = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ProductVariant(models.Model):
    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    variant_name = models.CharField(max_length=100)
    variant_value = models.CharField(max_length=100)
    price_modifier = models.DecimalField(max_digits=8, decimal_places=2, default=0)
```

### Step 2: Generate Migrations

```bash
python manage.py makemigrations domains.eshop
python manage.py migrate domains.eshop
```

### Step 3: Implement Viewsets

Update `domains/eshop/viewsets.py` with product CRUD operations.

### Step 4: Wire Routes

Ensure `/api/v1/eshop/` routes are configured in `backend/urls.py`.

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/eshop/models.py` | PostgreSQL models |
| Create | `domains/eshop/migrations/` | Schema migrations |
| Modify | `domains/eshop/viewsets.py` | Product CRUD |
| Create | `tests/test_eshop_products.py` | Verify functionality |

## Completion Gate

- [ ] Product models created
- [ ] E-shop endpoints functional
- [ ] Product data integrity verified
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed
