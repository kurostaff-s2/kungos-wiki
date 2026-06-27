# Phase 4C: Legacy Cleanup

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 4C of 5 (parallel with 4A, 4B)
**Dependencies:** Phase 1C (Cafe schema migrations must be applied)
**Estimated effort:** ~15 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p4c` |
| Entity type | `handoff` |
| Short description | Drop `misc` MongoDB collection (100% duplicate). Drop `caf_platform_users` table. Clean up deprecated artifacts. |
| Status | `draft` |
| Source references | `migration_spec.md`, `mongodb_schema.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute legacy cleanup — drop collections/tables, verify no references |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `backend/mongo.py` (remove `misc` collection references)
- `users/migrations/` (drop `caf_platform_users`)
- `tests/test_legacy_cleanup.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

`misc` MongoDB collection dropped (100% duplicate of `reb_users`). `caf_platform_users` table dropped. No code references to dropped collections/tables. No runtime errors.

## Implementation Steps

### Step 1: Verify No Code References `misc` Collection

```bash
grep -rn "'misc'\|\"misc\"" --include="*.py" | grep -v __pycache__ | grep -v venv/ | grep -v test_
```

### Step 2: Drop `misc` Collection

```python
from backend.mongo import get_database
db = get_database()
db['misc'].drop()
```

### Step 3: Verify No Code References `caf_platform_users`

```bash
grep -rn "caf_platform_users\|CafPlatformUser" --include="*.py" | grep -v __pycache__ | grep -v venv/ | grep -v test_
```

### Step 4: Drop `caf_platform_users` Table

Create migration:

```python
# In users/migrations/000X_drop_caf_platform_users.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('users', '000X_previous'),
    ]
    operations = [
        migrations.RunSQL('DROP TABLE IF EXISTS caf_platform_users'),
    ]
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/mongo.py` | Remove `misc` references |
| Create | `users/migrations/000X_drop_caf_platform_users.py` | Drop table |
| Create | `tests/test_legacy_cleanup.py` | Verify cleanup |

## Completion Gate

- [ ] `misc` collection dropped
- [ ] `caf_platform_users` table dropped
- [ ] No code references remaining
- [ ] No runtime errors
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Consistency Rules

**This phase defers to:**
- Migration ordering: `migration_spec.md` §7 (M7: Legacy Cleanup)
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Migration steps beyond what the spec defines
- Response shapes (Phase 3A handles response envelope)
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._
