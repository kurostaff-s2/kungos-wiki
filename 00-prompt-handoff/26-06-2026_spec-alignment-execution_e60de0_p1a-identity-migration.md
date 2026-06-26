# Phase 1A: Identity Data Migration (M1)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 1A of 5 (parallel with 1B, 1C)
**Dependencies:** None (can start immediately)
**Estimated effort:** ~60 min / multi-session (data migration + verification)

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p1a` |
| Entity type | `handoff` |
| Short description | Migrate `users_kurouser` data into `users_identity`. Populate `identity_id` for all existing users. |
| Status | `draft` |
| Source references | `postgresql_schema.md`, `migration_spec.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute data migration — verify Identity model, backfill data, update FKs |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/models.py` (Identity model, CustomUser model)
- `users/management/commands/migrate_identity.py` (existing migration command)
- `users/migrations/0001_initial.py` (existing migration)
- `backend/auth_utils.py` (resolve_access — may need identity_id support)
- `users/tenant_tokens.py` (JWT claims — may need identity_id)
**Related codebases:** None

## What This Phase Delivers

All existing `CustomUser` records have corresponding `Identity` records with valid `identity_id`. The `Identity.user` OneToOne relationship is populated. `UserTenantContext.identity_id` is backfilled for all active sessions. No orphaned `CustomUser` records exist without an `Identity` counterpart.

This is the foundation for all subsequent phases — RBAC FK migration (2A), Cafe schema alignment (1C), and Orders migration (4A) all depend on `identity_id` being available.

## Pre-Flight Checklist

- [ ] Phase 8B is marked complete (Commit `70b892d`)
- [ ] Test baseline established: 192 passed, 8 failed (pre-existing)
- [ ] `Identity` model exists in `users/models.py` (verify schema)
- [ ] Database is accessible for migration

## Implementation Steps

### Step 1: Verify Identity Model Schema

Read `users/models.py` and verify the `Identity` model has all required fields per spec:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `identity_id` | CharField(20, PK) | Yes | Primary key |
| `phone` | CharField (E.164) | Yes | Unique per tenant |
| `bg_code` | CharField(10) | Yes | FK → tenant |
| `div_code` | CharField(20) | Yes | FK → tenant |
| `branch_code` | CharField(20) | Yes | FK → tenant |
| `status` | CharField with CHECK | Yes | active/inactive/suspended |
| `user` | OneToOne → CustomUser | No | Nullable |
| `phone_verified` | BooleanField | Yes | Default False |
| `idproof_type` | CharField | No | Nullable |
| `idproof_number` | CharField | No | Nullable |
| `created_at` | DateTimeField | Yes | Auto |
| `updated_at` | DateTimeField | Yes | Auto |

**Action:** If any field is missing, add it to the model and generate a migration.

### Step 2: Review Existing Migration Command

Read `users/management/commands/migrate_identity.py` and verify it:
- Iterates all `CustomUser` objects
- Creates `Identity` records with correct data
- Sets `Identity.user` FK
- Handles duplicate phone numbers (per-tenant uniqueness)
- Updates `UserTenantContext.identity_id`

**Action:** If the command is incomplete, update it to handle all cases.

### Step 3: Implement Data Migration

If `migrate_identity.py` is not complete, implement the migration logic:

```python
# Pseudocode for migration command
for user in CustomUser.objects.all():
    phone = normalize_e164(user.phone)  # or user.mobile
    bg_code = get_user_bg_code(user)  # from UserTenantContext or default
    identity_id = generate_identity_id(user)  # UUID-based or phone-based
    
    identity, created = Identity.objects.get_or_create(
        identity_id=identity_id,
        defaults={
            'phone': phone,
            'bg_code': bg_code,
            'user': user,
            'status': 'active',
        }
    )
    
    # Update UserTenantContext
    UserTenantContext.objects.filter(userid=user.userid).update(
        identity_id=identity_id
    )
```

**Edge cases to handle:**
- Users without phone numbers (generate UUID-based identity_id)
- Users with multiple `UserTenantContext` records (one per BG)
- Duplicate phone numbers across tenants (per-tenant uniqueness)
- Inactive/suspended users (preserve status)

### Step 4: Run Migration

```bash
python manage.py migrate_identity
```

**Verify:**
- Count of `Identity` records equals count of `CustomUser` records
- No `CustomUser` without corresponding `Identity`
- `Identity.user` FK populated for all records
- `UserTenantContext.identity_id` backfilled

### Step 5: Create Database Migration

Generate a Django migration that:
- Ensures `Identity` model schema is correct
- Adds any missing columns
- Creates database-level constraints (CHECK on status, unique on phone+bg_code)

```bash
python manage.py makemigrations users
python manage.py migrate users
```

### Step 6: Update JWT Claims

Verify `users/tenant_tokens.py` includes `identity_id` in JWT payload:

```python
payload = {
    'user_id': str(user.id),
    'userid': user.userid,
    'identity_id': identity_id,  # Must be present
    'bg_code': bg_code,
    # ... other claims
}
```

**Action:** If `identity_id` is missing from JWT claims, add it.

### Step 7: Update `resolve_access()` for `identity_id`

Verify `backend/auth_utils.py` `resolve_access()` can query by `identity_id`:

```python
def resolve_access(identity_id, bg_code):
    # Query RBAC tables by identity_id
    roles = UserRole.objects.filter(identity_id=identity_id, bg_code=bg_code)
    # ... resolve permissions
```

**Action:** If `resolve_access()` still queries by `userid`, update it to support `identity_id`.

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Read/Verify | `users/models.py` | Verify Identity model schema |
| Read/Update | `users/management/commands/migrate_identity.py` | Data migration logic |
| Create | `users/migrations/000X_identity_schema.py` | Schema migration (if needed) |
| Read/Update | `users/tenant_tokens.py` | Add identity_id to JWT claims |
| Read/Update | `backend/auth_utils.py` | Support identity_id in resolve_access |
| Create | `tests/test_identity_migration.py` | Verify migration results |

## Phase-Specific Tests

Create `tests/test_identity_migration.py`:

1. **Test all users have Identity records:**
   ```python
   def test_all_users_have_identity():
       user_count = CustomUser.objects.count()
       identity_count = Identity.objects.count()
       assert identity_count >= user_count
   ```

2. **Test Identity.user FK populated:**
   ```python
   def test_identity_user_fk_populated():
       orphaned = Identity.objects.filter(user__isnull=True)
       assert orphaned.count() == 0
   ```

3. **Test UserTenantContext.identity_id backfilled:**
   ```python
   def test_tenant_context_identity_id():
       missing = UserTenantContext.objects.filter(identity_id__exact='')
       assert missing.count() == 0
   ```

4. **Test no orphaned CustomUser:**
   ```python
   def test_no_orphaned_customuser():
       for user in CustomUser.objects.all():
           assert Identity.objects.filter(user=user).exists()
   ```

5. **Test JWT contains identity_id:**
   ```python
   def test_jwt_contains_identity_id():
       # Generate token and verify identity_id present
       token = generate_token(user)
       payload = decode_token(token)
       assert 'identity_id' in payload
   ```

## Completion Gate

- [ ] Identity model schema verified (all fields present)
- [ ] Data migration command runs successfully
- [ ] All `CustomUser` records have `Identity` counterparts
- [ ] `Identity.user` FK populated
- [ ] `UserTenantContext.identity_id` backfilled
- [ ] JWT claims include `identity_id`
- [ ] `resolve_access()` supports `identity_id`
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests (192 passed, 8 pre-existing failures)
- [ ] Files committed

## Notes for Next Phase

- Phase 1B (MongoDB field rename) can run in parallel — no dependency on this phase.
- Phase 2A (RBAC FK migration) depends on this phase — `identity_id` must be available.
- Phase 1C (Cafe schema) depends on this phase — walk-in sessions need `identity_id` FK.
- After this phase, `CustomUser.userid` is still the AUTH_USER_MODEL PK. The transition to `identity_id` as primary key happens in Phase 2A.
