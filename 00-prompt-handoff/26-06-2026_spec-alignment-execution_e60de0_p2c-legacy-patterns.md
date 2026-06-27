# Phase 2C: Legacy Pattern Cleanup

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 2C of 5 (parallel with 2A, 2B, 2D)
**Dependencies:** Phase 2A (RBAC FK migration must be complete)
**Estimated effort:** ~30 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p2c` |
| Entity type | `handoff` |
| Short description | Replace `user.access == "Super"` pattern (8 sites) with `is_supervisor(permissions)`. Remove `business_accesslevel`/`division_accesslevel` functions. |
| Status | `draft` |
| Source references | `backend/auth_utils.py`, `users/views.py`, `users/api/viewsets.py` |
| Generated | `26-06-2026` |
| Next action / owner | Execute legacy pattern cleanup — replace 8 sites, remove 2 functions |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/views.py` (lines 136, 339, 266, 521)
- `users/api/viewsets.py` (lines 748, 842, 1008)
- `teams/kurostaff/views.py` (line 1254)
- `teams/products.py` (line 899)
- `careers/views.py` (lines 103, 116)
- `domains/search/viewsets.py` (line 63)
- `backend/auth_utils.py` (is_supervisor helper)
**Related codebases:** None

## What This Phase Delivers

All 8 sites using `user.access == "Super"` replaced with `is_supervisor(result['permissions'])`. The `business_accesslevel()` and `division_accesslevel()` functions removed. No legacy `access` field in user data responses. The `is_supervisor()` helper is the single source of truth for supervisor checks.

## Pre-Flight Checklist

- [ ] Phase 2A is marked complete (RBAC uses `identity_id`)
- [ ] `resolve_access(identity_id, bg_code)` returns `permissions` list
- [ ] `is_supervisor()` helper exists in `backend/auth_utils.py`
- [ ] Test baseline established (192 passed, 8 pre-existing failures)

## Implementation Steps

### Step 1: Verify `is_supervisor()` Helper

Read `backend/auth_utils.py` and verify the helper exists:

```python
def is_supervisor(permissions: list) -> bool:
    """Check if user has supervisor-level permissions.
    
    Replaces: user.access == 'Super'
    """
    supervisor_perms = {
        'admin.full',
        'admin.manage',
        'user.admin',
    }
    return bool(set(permissions) & supervisor_perms)
```

**Action:** If not present, add it.

### Step 2: Replace `user.access == "Super"` (8 Sites)

#### Site 1: `users/views.py:136`

**Current:**
```python
userData["access"] = userdetails.access
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
userData["permissions"] = access_result['permissions']
userData["is_supervisor"] = is_supervisor(access_result['permissions'])
```

#### Site 2: `users/views.py:339`

**Current:**
```python
can_manage = kuser.access == "Super" or perm.get('level', 0) >= 2
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
can_manage = is_supervisor(access_result['permissions']) or perm.get('level', 0) >= 2
```

#### Site 3: `users/api/viewsets.py:842`

**Current:**
```python
userdata['access'] = userdetails.access
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
userdata['permissions'] = access_result['permissions']
userdata['is_supervisor'] = is_supervisor(access_result['permissions'])
```

#### Site 4: `teams/kurostaff/views.py:1254`

**Current:**
```python
output_list = inwardinvoice_calce(limit=limit, filters=filters, access=user.access, ...)
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
is_super = is_supervisor(access_result['permissions'])
output_list = inwardinvoice_calce(limit=limit, filters=filters, access='Super' if is_super else 'Regular', ...)
```

**Note:** This site passes `access` to a MongoDB query. The Mongo query may need to be rewritten to not depend on `user.access`. If the query filters by access level, replace with permission-based filtering.

#### Site 5: `teams/products.py:899`

**Current:**
```python
if user.access == "Super":
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
if is_supervisor(access_result['permissions']):
```

#### Site 6: `careers/views.py:103`

**Current:**
```python
if user.access == "Super" or len(entity)>0:
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
if is_supervisor(access_result['permissions']) or len(entity)>0:
```

#### Site 7: `careers/views.py:116`

**Current:**
```python
can_edit = user.access == "Super" or perm.get('level', 0) >= 1
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
can_edit = is_supervisor(access_result['permissions']) or perm.get('level', 0) >= 1
```

#### Site 8: `domains/search/viewsets.py:63`

**Current:**
```python
if hasattr(user, 'access') and 'admin' in str(user.access).lower():
```

**Replace with:**
```python
access_result = resolve_access(identity_id, bg_code)
has_admin = any('admin' in p for p in access_result['permissions'])
```

### Step 3: Remove `business_accesslevel()` Function

Read `users/views.py:266` and `users/api/viewsets.py:748,1008`.

**Action:**
1. Remove `business_accesslevel()` function from `users/views.py`
2. Remove callers from `users/api/viewsets.py`
3. Replace with RBAC role assignment:

```python
# Instead of: business_accesslevel(data, userid=userid, reqFrom=request.user.userid)
# Use:
from users.models import UserRole, Role

role = Role.objects.get(role_code='branch_supervisor')
UserRole.objects.create(
    identity_id=identity_id,
    role=role,
    bg_code=bg_code,
)
```

### Step 4: Remove `division_accesslevel()` Function

Read `users/views.py:521`.

**Action:**
1. Remove `division_accesslevel()` function from `users/views.py`
2. Replace with RBAC role assignment (division-scoped):

```python
# Instead of: division_accesslevel(division, bg_code, delete=False)
# Use:
UserRole.objects.create(
    identity_id=identity_id,
    role=role,
    bg_code=bg_code,
    div_code=division,  # Division-scoped role
)
```

### Step 5: Verify No Remaining Legacy References

```bash
# Search for remaining user.access references
grep -rn "user\.access\|userdetails\.access" --include="*.py" | grep -v __pycache__ | grep -v venv/ | grep -v test_

# Search for remaining business_accesslevel references
grep -rn "business_accesslevel\|division_accesslevel" --include="*.py" | grep -v __pycache__ | grep -v venv/
```

**Expected:** No results (except in test files verifying removal).

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/views.py` | Replace 4 legacy sites, remove 2 functions |
| Modify | `users/api/viewsets.py` | Replace 3 legacy sites |
| Modify | `teams/kurostaff/views.py` | Replace 1 legacy site |
| Modify | `teams/products.py` | Replace 1 legacy site |
| Modify | `careers/views.py` | Replace 2 legacy sites |
| Modify | `domains/search/viewsets.py` | Replace 1 legacy site |
| Read | `backend/auth_utils.py` | Verify is_supervisor() exists |
| Create | `tests/test_legacy_pattern_cleanup.py` | Verify all patterns replaced |

## Phase-Specific Tests

Create `tests/test_legacy_pattern_cleanup.py`:

1. **Test no user.access references remain:**
   ```python
   def test_no_user_access_references():
       import subprocess
       result = subprocess.run(
           ['grep', '-rn', 'user.access', '--include=*.py', '.'],
           capture_output=True, text=True, cwd=settings.BASE_DIR
       )
       # Exclude test files and __pycache__
       lines = [l for l in result.stdout.split('\n') if l and '__pycache__' not in l and 'test_' not in l]
       assert len(lines) == 0, f"Remaining user.access references: {lines}"
   ```

2. **Test is_supervisor works correctly:**
   ```python
   def test_is_supervisor_with_admin_full():
       assert is_supervisor(['admin.full']) == True
   
   def test_is_supervisor_with_read_only():
       assert is_supervisor(['orders.read']) == False
   ```

3. **Test business_accesslevel removed:**
   ```python
   def test_business_accesslevel_removed():
       from users import views
       assert not hasattr(views, 'business_accesslevel')
   ```

4. **Test division_accesslevel removed:**
   ```python
   def test_division_accesslevel_removed():
       from users import views
       assert not hasattr(views, 'division_accesslevel')
   ```

## Completion Gate

- [ ] All 8 `user.access` sites migrated to `is_supervisor()`
- [ ] `business_accesslevel()` function removed
- [ ] `division_accesslevel()` function removed
- [ ] No legacy `access` field in user data responses
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Notes for Next Phase

- Phase 2B (Login response) is independent — can run in parallel.
- Phase 3C (Legacy endpoint removal) depends on this phase — legacy patterns must be cleaned up first.
- After this phase, `user.access` is no longer used for authorization decisions. The `CustomUser.access` field can be deprecated (not removed yet — may still be used for display purposes).

## Consistency Rules

**This phase defers to:**
- Wire shapes: `endpoint_contract_spec.md`
- Migration ordering: `migration_spec.md`
- Canonical naming: `CANONICAL_NAMING.md`

**This phase does NOT redefine:**
- Response shapes beyond what the spec allows
- Migration steps beyond what the spec defines
- Wire field names (use canonical names)

## Spec Contradictions

_None documented._
