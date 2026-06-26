# Phase 2A: RBAC FK Migration (userid → identity_id)

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 2A of 5 (parallel with 2B, 2C, 2D)
**Dependencies:** Phase 1A (Identity data migration must be complete)
**Estimated effort:** ~45 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p2a` |
| Entity type | `handoff` |
| Short description | Migrate all RBAC table FKs from `userid` to `identity_id`. Update `rbac_user_roles`, `rbac_user_permissions`, `rbac_user_role_branches`. |
| Status | `draft` |
| Source references | `postgresql_schema.md`, `rbac_system.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute RBAC FK migration — add identity_id column, backfill, switch FK, drop userid |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/models.py` (UserRole, UserPermission, UserRoleBranch models)
- `backend/auth_utils.py` (resolve_access function)
- `users/migrations/` (new migration)
- `tests/test_rbac_native_resolution.py` (existing tests)
**Related codebases:** None

## What This Phase Delivers

All RBAC tables (`rbac_user_roles`, `rbac_user_permissions`, `rbac_user_role_branches`) reference `identity_id` instead of `userid`. The `resolve_access()` function queries by `identity_id`. No orphaned RBAC records exist. All existing RBAC tests pass with `identity_id` as the primary key.

## Pre-Flight Checklist

- [ ] Phase 1A is marked complete (all `CustomUser` have `Identity` records)
- [ ] `Identity.identity_id` is populated for all users
- [ ] `UserTenantContext.identity_id` is backfilled
- [ ] Existing RBAC tests pass (81/81 migration tests)

## Implementation Steps

### Step 1: Add `identity_id` Column to RBAC Models

Read `users/models.py` and add `identity_id` field to each RBAC model:

```python
class UserRole(models.Model):
    # Existing fields
    user = models.ForeignKey('users.CustomUser', ...)
    role = models.ForeignKey('users.Role', ...)
    bg_code = models.CharField(...)
    
    # NEW: identity_id (nullable initially)
    identity_id = models.CharField(
        max_length=20, blank=True, null=True, db_index=True,
        help_text="Identity ID (replaces user FK)",
    )
    
    class Meta:
        db_table = 'rbac_user_roles'

class UserPermission(models.Model):
    # Existing fields
    user = models.ForeignKey('users.CustomUser', ...)
    permission = models.ForeignKey('users.Permission', ...)
    bg_code = models.CharField(...)
    
    # NEW: identity_id
    identity_id = models.CharField(
        max_length=20, blank=True, null=True, db_index=True,
    )
    
    class Meta:
        db_table = 'rbac_user_permissions'

class UserRoleBranch(models.Model):
    # Existing fields
    user_role = models.ForeignKey('users.UserRole', ...)
    branch_code = models.CharField(...)
    
    # NEW: identity_id
    identity_id = models.CharField(
        max_length=20, blank=True, null=True, db_index=True,
    )
    
    class Meta:
        db_table = 'rbac_user_role_branches'
```

**Generate migration:**
```bash
python manage.py makemigrations users
```

### Step 2: Backfill `identity_id`

Create a data migration that populates `identity_id` from the `Identity` model:

```python
# In users/migrations/000X_rbac_identity_fk.py
def backfill_identity_id(apps, schema_editor):
    UserRole = apps.get_model('users', 'UserRole')
    UserPermission = apps.get_model('users', 'UserPermission')
    UserRoleBranch = apps.get_model('users', 'UserRoleBranch')
    Identity = apps.get_model('users', 'Identity')
    
    # Backfill UserRole
    for user_role in UserRole.objects.all():
        identity = Identity.objects.filter(user=user_role.user).first()
        if identity:
            user_role.identity_id = identity.identity_id
            user_role.save(update_fields=['identity_id'])
    
    # Backfill UserPermission
    for user_perm in UserPermission.objects.all():
        identity = Identity.objects.filter(user=user_perm.user).first()
        if identity:
            user_perm.identity_id = identity.identity_id
            user_perm.save(update_fields=['identity_id'])
    
    # Backfill UserRoleBranch (via UserRole)
    for branch in UserRoleBranch.objects.all():
        if branch.user_role.identity_id:
            branch.identity_id = branch.user_role.identity_id
            branch.save(update_fields=['identity_id'])
```

### Step 3: Switch FK from `userid` to `identity_id`

Update `resolve_access()` in `backend/auth_utils.py`:

```python
def resolve_access(identity_id, bg_code):
    """Resolve access for a user by identity_id.
    
    Replaces legacy resolve_access(userid, bg_code).
    """
    # Query by identity_id
    roles = UserRole.objects.filter(
        identity_id=identity_id,
        bg_code=bg_code
    ).select_related('role')
    
    permissions = set()
    div_codes = set()
    branch_codes = set()
    
    for user_role in roles:
        # Get role permissions
        role_perms = user_role.role.permissions.all()
        permissions.update([p.code for p in role_perms])
        
        # Get branch scoping
        branches = UserRoleBranch.objects.filter(
            user_role=user_role,
            identity_id=identity_id
        )
        branch_codes.update([b.branch_code for b in branches])
    
    # Add direct permissions
    direct_perms = UserPermission.objects.filter(
        identity_id=identity_id,
        bg_code=bg_code
    )
    permissions.update([p.permission.code for p in direct_perms])
    
    return {
        'permissions': list(permissions),
        'div_codes': list(div_codes),
        'branch_codes': list(branch_codes),
    }
```

**Update all callers of `resolve_access()` to pass `identity_id` instead of `userid`.**

### Step 4: Remove `userid` Column

After verification, remove the `user` FK from RBAC models:

```python
class UserRole(models.Model):
    # REMOVED: user = models.ForeignKey('users.CustomUser', ...)
    role = models.ForeignKey('users.Role', ...)
    bg_code = models.CharField(...)
    identity_id = models.CharField(max_length=20, db_index=True)  # Now required
    
    class Meta:
        db_table = 'rbac_user_roles'
        unique_together = [('identity_id', 'role', 'bg_code')]
```

**Generate migration:**
```bash
python manage.py makemigrations users
python manage.py migrate users
```

### Step 5: Update Tests

Update `tests/test_rbac_native_resolution.py` to use `identity_id`:

```python
def test_resolve_access_by_identity_id():
    identity = Identity.objects.create(
        identity_id='ID001',
        phone='+919876543210',
        bg_code='KURO0001',
        status='active',
    )
    
    UserRole.objects.create(
        identity_id='ID001',
        role=role,
        bg_code='KURO0001',
    )
    
    result = resolve_access('ID001', 'KURO0001')
    assert 'admin.full' in result['permissions']
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/models.py` | Add identity_id to UserRole, UserPermission, UserRoleBranch |
| Create | `users/migrations/000X_rbac_identity_fk.py` | Schema + data migration |
| Modify | `backend/auth_utils.py` | Update resolve_access() to use identity_id |
| Modify | `tests/test_rbac_native_resolution.py` | Update tests to use identity_id |
| Create | `tests/test_rbac_identity_fk.py` | New tests for identity_id FK |

## Phase-Specific Tests

Create `tests/test_rbac_identity_fk.py`:

1. **Test RBAC queries work with identity_id:**
   ```python
   def test_rbac_query_by_identity_id():
       UserRole.objects.create(
           identity_id='ID001',
           role=role,
           bg_code='KURO0001',
       )
       result = UserRole.objects.filter(identity_id='ID001')
       assert result.count() == 1
   ```

2. **Test resolve_access with identity_id:**
   ```python
   def test_resolve_access_identity_id():
       result = resolve_access('ID001', 'KURO0001')
       assert 'permissions' in result
       assert 'div_codes' in result
   ```

3. **Test no orphaned RBAC records:**
   ```python
   def test_no_orphaned_rbac_records():
       # All UserRole records have valid identity_id
       orphaned = UserRole.objects.filter(identity_id__exact='')
       assert orphaned.count() == 0
   ```

4. **Test backward compat during transition:**
   ```python
   def test_backward_compat_userid():
       # During transition, both userid and identity_id should work
       pass
   ```

## Completion Gate

- [ ] `identity_id` column added to all RBAC tables
- [ ] `identity_id` backfilled from `Identity` model
- [ ] `resolve_access()` queries by `identity_id`
- [ ] All callers of `resolve_access()` updated
- [ ] `user` FK removed from RBAC tables (after verification)
- [ ] All phase-specific tests pass
- [ ] No regression in existing RBAC tests (81/81)
- [ ] Files committed

## Notes for Next Phase

- Phase 2B (Login response) depends on this phase — needs `identity_id` in RBAC.
- Phase 2C (Legacy patterns) depends on this phase — needs `is_supervisor()` with `identity_id`.
- Phase 2D (RBAC URLs) depends on this phase — needs `identity_id` endpoints.
- After this phase, `CustomUser.userid` is no longer referenced by RBAC tables. The `CustomUser` model still exists as AUTH_USER_MODEL but RBAC is fully `identity_id`-based.
