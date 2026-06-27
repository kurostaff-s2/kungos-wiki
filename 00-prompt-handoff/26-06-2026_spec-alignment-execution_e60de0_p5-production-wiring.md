# Phase 5: Production Wiring & Verification

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 5 of 5 (final)
**Dependencies:** All Phase 1-4 complete
**Estimated effort:** ~30 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p5` |
| Entity type | `handoff` |
| Short description | End-to-end verification of all alignment changes. Full test suite, integration tests, health checks. |
| Status | `draft` |
| Source references | All spec documents |
| Generated | `26-06-2026` |
| Next action / owner | Execute production wiring — run full test suite, verify all endpoints, update docs |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `pytest.ini` (test configuration)
- `backend/urls.py` (verify all routes)
- `backend/settings.py` (verify middleware)
- All test files
**Related codebases:** None

## What This Phase Delivers

Full test suite passes with 0 regressions. All spec endpoints accessible and functional. Tenant isolation verified. MongoDB collections use canonical field names. PostgreSQL FK integrity verified. Standard response envelope active. Standard error handling active. Documentation updated.

## Pre-Flight Checklist

- [ ] Phase 1A (Identity migration) complete
- [ ] Phase 1B (MongoDB field rename) complete
- [ ] Phase 1C (Cafe schema) complete
- [ ] Phase 2A (RBAC FK) complete
- [ ] Phase 2B (Login response) complete
- [ ] Phase 2C (Legacy patterns) complete
- [ ] Phase 2D (RBAC URLs) complete
- [ ] Phase 3A (Response envelope) complete
- [ ] Phase 3B (Error handling) complete
- [ ] Phase 3C (Legacy endpoints) complete
- [ ] Phase 4A (Orders PG) complete
- [ ] Phase 4B (E-Commerce) complete
- [ ] Phase 4C (Legacy cleanup) complete

## Implementation Steps

### Step 1: Run Full Test Suite

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
pytest tests/ -v --tb=short
```

**Expected:** All tests pass with 0 regressions. Pre-existing 8 auth 404s excluded.

### Step 2: Verify All Spec Endpoints

```bash
# Auth endpoints (spec §4.1: auth under /api/v1/auth/ namespace)
curl http://localhost:8000/api/v1/auth/login/
curl http://localhost:8000/api/v1/auth/refresh/

# User endpoints
curl http://localhost:8000/api/v1/users/me/
curl http://localhost:8000/api/v1/users/lookup?phone=+919876543210

# RBAC endpoints
curl http://localhost:8000/api/v1/rbac/roles/
curl http://localhost:8000/api/v1/rbac/permissions/
curl http://localhost:8000/api/v1/rbac/user/ID001/

# Tenant endpoints
curl http://localhost:8000/api/v1/tenant/current/

# Cafe endpoints
curl http://localhost:8000/api/v1/cafe/sessions/
curl http://localhost:8000/api/v1/cafe/stations/
curl http://localhost:8000/api/v1/cafe/wallet/

# E-shop endpoints
curl http://localhost:8000/api/v1/eshop/products/
```

### Step 3: Verify Login Response Shape (Spec §4.2)

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "+919876543210", "password": "test"}'
```

**Expected response (verbatim from endpoint contract spec §4.2):**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJhbG...",
        "token_type": "Bearer",
        "expires_in": 3600,
        "user": {
            "identity_id": "ID000001",
            "phone": "+919876543210",
            "bg_code": "KURO0001",
            "active_div_code": "KURO0001_001",
            "active_branch_code": "BRANCH001",
            "roles": ["branch_supervisor"],
            "permissions": ["orders.read"],
            "email": "john@example.com"
        }
    },
    "meta": {
        "request_id": "req-abc123",
        "timestamp": "2026-06-26T12:00:00Z"
    }
}
```

**Field placement rules:**
- `access_token`, `token_type`, `expires_in` → top-level `data`
- `user.identity_id`, `user.phone`, `user.bg_code`, `user.active_div_code`, `user.active_branch_code`, `user.roles`, `user.permissions`, `user.email` → nested under `data.user`
- `bg_code` = accessible tenant scope; `active_div_code`/`active_branch_code` = active session context (single values, not arrays)


### Step 4: Verify Tenant Isolation

```python
# Test that tenant A cannot access tenant B's data
def test_tenant_isolation():
    # Login as tenant A user (spec §4.2: /api/v1/auth/login)
    response_a = client.post('/api/v1/auth/login/', data=tenant_a_credentials)
    token_a = response_a.data['data']['access_token']
    
    # Try to access tenant B's data
    response = client.get('/api/v1/orders/', HTTP_AUTHORIZATION=f'Bearer {token_a}')
    
    # Verify all results belong to tenant A
    for order in response.data['data']:
        assert order['bg_code'] == 'KURO0001'
```

### Step 5: Verify PostgreSQL FK Integrity

```python
def test_fk_integrity():
    # All orders have valid identity_id
    from domains.orders.models import Order
    from users.models import Identity
    
    for order in Order.objects.all():
        assert Identity.objects.filter(identity_id=order.identity_id).exists()
```

### Step 6: Verify MongoDB Field Naming

```python
def test_mongo_field_naming():
    from backend.mongo import get_database
    db = get_database()
    
    for collection_name in db.list_collection_names():
        sample = db[collection_name].find_one()
        if sample:
            assert 'bgcode' not in sample, f"Legacy field 'bgcode' found in {collection_name}"
            assert 'bg_code' in sample or 'bg_code' not in [k for k in sample.keys() if 'bg' in k.lower()], \
                f"Missing canonical field 'bg_code' in {collection_name}"
```

### Step 7: Update Documentation

Update the following documents to reflect completed alignment:

1. `llm-wiki/Kung_OS/architecture/rbac_system.md` — Update to reflect `identity_id`-based RBAC
2. `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` — Mark completed endpoints
3. `llm-wiki/00-prompt-handoff/26-06-2026_spec-alignment-execution_e60de0.md` — Mark complete

## Post-Wiring Tests (GATE)

- [ ] Full test suite passes (0 regressions)
- [ ] Login response matches spec shape
- [ ] RBAC resolution works end-to-end
- [ ] Tenant isolation verified (no cross-tenant leakage)
- [ ] All spec endpoints accessible
- [ ] MongoDB collections use canonical field names
- [ ] PostgreSQL FK integrity verified
- [ ] Standard response envelope active
- [ ] Standard error handling active
- [ ] Health check endpoint reports all components ok
- [ ] Documentation updated

## Stronger Migration Verification

### Per-Source Row Reconciliation

For each data migration phase, verify row counts match:

```python
def verify_row_counts(source_db, target_db, source_collections, target_collections):
    for src_coll, tgt_coll in zip(source_collections, target_collections):
        src_count = source_db[src_coll].count_documents({})
        tgt_count = target_db[tgt_coll].count_documents({})
        assert src_count == tgt_count, f"Row count mismatch: {src_coll}={src_count}, {tgt_coll}={tgt_count}"
```

### Audit Tables

Create audit tables to track migration progress:

```python
class MigrationAudit(models.Model):
    phase = models.CharField(max_length=50)
    source = models.CharField(max_length=100)
    target = models.CharField(max_length=100)
    row_count = models.IntegerField()
    verified_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey('users.Identity', on_delete=models.CASCADE)
```

### Sampled Record Diffs

For each migration, sample 100 records and verify field-by-field match:

```python
def verify_sampled_records(source_db, target_db, collection_name, sample_size=100):
    import random
    src_docs = list(source_db[collection_name].find({}))
    sample = random.sample(src_docs, min(sample_size, len(src_docs)))
    
    for doc in sample:
        src_id = doc['_id']
        tgt_doc = target_db[collection_name].find_one({'_id': src_id})
        
        # Verify canonical fields
        assert doc.get('bg_code') == tgt_doc.get('bg_code'), f"bg_code mismatch for {src_id}"
        assert doc.get('div_code') == tgt_doc.get('div_code'), f"div_code mismatch for {src_id}"
        assert doc.get('branch_code') == tgt_doc.get('branch_code'), f"branch_code mismatch for {src_id}"
```

### Alerting/Observability Gates

Configure monitoring alerts for rollout day:

- **Error rate:** Alert if error rate > 1% for any endpoint
- **Latency:** Alert if p99 latency > 500ms for any endpoint
- **Row count mismatch:** Alert if any migration has row count mismatch > 0
- **FK constraint violations:** Alert on any FK constraint violation
- **Tenant isolation failures:** Alert on any cross-tenant data access

## Completion Gate

- [ ] All post-wiring tests pass
- [ ] No regression in existing tests
- [ ] All spec requirements met
- [ ] Documentation updated
- [ ] Files committed
- [ ] Handoff marked `complete`
- [ ] Per-source row reconciliation verified
- [ ] Audit tables created and populated
- [ ] Sampled record diffs pass (100 records per collection)
- [ ] Monitoring alerts configured and tested

## Consistency Rules

**This phase defers to:**
- Wire shapes: `endpoint_contract_spec.md` (all endpoints)
- Migration ordering: `migration_spec.md` (all phases)
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Response shapes (use spec verbatim)
- Migration steps (use spec validation gates)
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._
