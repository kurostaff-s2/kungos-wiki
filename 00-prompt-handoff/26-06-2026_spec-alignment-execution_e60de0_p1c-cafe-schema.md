# Phase 1C: Cafe Schema Migrations (M2)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 1C of 5 (parallel with 1A, 1B)
**Dependencies:** Phase 1A (Identity data migration must be complete for FK)
**Estimated effort:** ~30 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p1c` |
| Entity type | `handoff` |
| Short description | Apply unapplied migrations 0001-0003 for cafe schema alignment. Drop `caf_platform_users`. Align `caf_walkin_sessions` to use `identity_id` FK. |
| Status | `draft` |
| Source references | `postgresql_schema.md`, `migration_spec.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute cafe schema migrations — review, apply, verify |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `domains/cafe_arcade/migrations/0001_initial.py`
- `domains/cafe_arcade/migrations/0002_walkin_sessions.py`
- `domains/cafe_arcade/migrations/0003_drop_platform_users.py`
- `domains/cafe_arcade/models.py`
- `domains/cafe_arcade/views.py`
- `tests/test_cafe_schema.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

Cafe schema migrations 0001-0003 applied. `caf_walkin_sessions` uses `identity_id` FK. `caf_platform_users` table dropped. FK integrity verified on all cafe tables.

## Pre-Flight Checklist

- [ ] Phase 1A is marked complete (Identity data migration done)
- [ ] `Identity` model has `identity_id` for all users
- [ ] Cafe migrations 0001-0003 exist (review for correctness)
- [ ] Database is accessible for migration

## Implementation Steps

### Step 1: Review Unapplied Migrations

Read each migration file and verify:

1. **0001_initial.py** — Creates initial cafe schema tables
2. **0002_walkin_sessions.py** — Adds `identity_id` FK to walk-in sessions
3. **0003_drop_platform_users.py** — Drops `caf_platform_users` table

**Verify:**
- Migration dependencies are correct
- FK references point to correct tables
- No circular dependencies

### Step 2: Apply Migrations

```bash
python manage.py migrate domains.cafe_arcade
```

**Verify:**
- All migrations apply cleanly
- No FK constraint violations
- `caf_platform_users` table dropped

### Step 3: Update Cafe Models

Read `domains/cafe_arcade/models.py` and verify:

```python
class WalkInSession(models.Model):
    session_id = models.CharField(max_length=50, primary_key=True)
    identity_id = models.ForeignKey(
        'users.Identity',
        on_delete=models.CASCADE,
        db_index=True,
    )
    station_id = models.CharField(max_length=50)
    bg_code = models.CharField(max_length=10, db_index=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)
    status = models.CharField(max_length=20, default='active')
```

**Action:** If `identity_id` is missing, add it and generate a migration.

### Step 4: Update Cafe Views

Read `domains/cafe_arcade/views.py` and verify all queries use `identity_id`:

```python
# Instead of: WalkInSession.objects.filter(user=user)
# Use: WalkInSession.objects.filter(identity_id=identity_id)
```

### Step 5: Verify FK Integrity

```python
def test_cafe_fk_integrity():
    from domains.cafe_arcade.models import WalkInSession
    from users.models import Identity
    
    for session in WalkInSession.objects.all():
        if session.identity_id:
            assert Identity.objects.filter(identity_id=session.identity_id).exists()
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Read/Verify | `domains/cafe_arcade/migrations/0001_initial.py` | Review migration |
| Read/Verify | `domains/cafe_arcade/migrations/0002_walkin_sessions.py` | Review migration |
| Read/Verify | `domains/cafe_arcade/migrations/0003_drop_platform_users.py` | Review migration |
| Modify | `domains/cafe_arcade/models.py` | Ensure identity_id FK |
| Modify | `domains/cafe_arcade/views.py` | Use identity_id in queries |
| Create | `tests/test_cafe_schema.py` | Verify schema |

## Phase-Specific Tests

Create `tests/test_cafe_schema.py`:

1. **Test migrations applied:**
   ```python
   def test_cafe_migrations_applied():
       from django.db import connection
       with connection.cursor() as cursor:
           cursor.execute("SELECT * FROM caf_walkin_sessions LIMIT 1")
           columns = [col[0] for col in cursor.description]
           assert 'identity_id' in columns
   ```

2. **Test caf_platform_users dropped:**
   ```python
   def test_caf_platform_users_dropped():
       from django.db import connection
       with connection.cursor() as cursor:
           cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'caf_platform_users')")
           exists = cursor.fetchone()[0]
           assert not exists
   ```

3. **Test FK integrity:**
   ```python
   def test_cafe_fk_integrity():
       from domains.cafe_arcade.models import WalkInSession
       from users.models import Identity
       
       for session in WalkInSession.objects.all():
           if session.identity_id:
               assert Identity.objects.filter(identity_id=session.identity_id).exists()
   ```

## Completion Gate

- [ ] All migrations applied cleanly
- [ ] `caf_walkin_sessions.identity_id` FK valid
- [ ] `caf_platform_users` table dropped
- [ ] Cafe views use `identity_id`
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Notes for Next Phase

- Phase 4C (Legacy cleanup) depends on this phase — `caf_platform_users` must be dropped first.
- Phase 2A (RBAC FK) is independent — can run in parallel.
- After this phase, cafe tables use `identity_id` consistently.

## Consistency Rules

**This phase defers to:**
- Migration ordering: `migration_spec.md` §4 (M4: Cafe Schema Migrations)
- PostgreSQL schema: `postgresql_schema.md`
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Response shapes (Phase 2B handles login response)
- Mongo field names (Phase 1B handles field rename)
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._

