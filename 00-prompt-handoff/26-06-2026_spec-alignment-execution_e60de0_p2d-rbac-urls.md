# Phase 2D: /rbac/ URL Namespace

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 2D of 5 (parallel with 2A, 2B, 2C)
**Dependencies:** Phase 2A (RBAC FK migration must be complete)
**Estimated effort:** ~20 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p2d` |
| Entity type | `handoff` |
| Short description | Create `users/rbac_urls.py` and route under `/api/v1/rbac/`. Expose roles, permissions, assignments, user lookup. |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md` §2.1 |
| Generated | `26-06-2026` |
| Next action / owner | Execute /rbac/ URL namespace — create urls.py, register viewsets, wire routes |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/rbac_urls.py` (new file)
- `backend/urls.py` (add /rbac/ route)
- `users/api/viewsets.py` (existing viewsets to register)
- `tests/test_rbac_urls.py` (new tests)
**Related codebases:** None

## What This Phase Delivers

The `/api/v1/rbac/` URL namespace is registered and functional. Exposes role CRUD, permission CRUD, user-role assignments, and user lookup by `identity_id`. All endpoints accessible via standard DRF routing.

## Pre-Flight Checklist

- [ ] Phase 2A is marked complete (RBAC uses `identity_id`)
- [ ] `RoleViewSet`, `PermissionViewSet`, `UserRoleViewSet` exist in `users/api/viewsets.py`
- [ ] DRF router is configured in `backend/urls.py`

## Implementation Steps

### Step 1: Create `users/rbac_urls.py`

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from users.api import viewsets

router = DefaultRouter()
router.register('roles', viewsets.RoleViewSet, basename='rbac-role')
router.register('permissions', viewsets.PermissionViewSet, basename='rbac-permission')
router.register('user-roles', viewsets.UserRoleViewSet, basename='rbac-user-role')
router.register('user-permissions', viewsets.UserPermissionViewSet, basename='rbac-user-permission')

urlpatterns = [
    path('', include(router.urls)),
]
```

### Step 2: Add Route to `backend/urls.py`

```python
# In backend/urls.py, inside api/v1/ include:
path('rbac/', include('users.rbac_urls')),
```

### Step 3: Implement User Lookup Endpoint

Create a viewset for user lookup by `identity_id`:

```python
# In users/api/viewsets.py
class RbacUserViewSet(viewsets.ReadOnlyModelViewSet):
    """Lookup user RBAC data by identity_id."""
    queryset = Identity.objects.all()
    serializer_class = RbacUserSerializer
    lookup_field = 'identity_id'
    
    def retrieve(self, request, identity_id=None):
        identity = self.get_object()
        access_result = resolve_access(identity_id, self.bg_code)
        
        return Response({
            'identity_id': identity_id,
            'permissions': access_result['permissions'],
            'roles': access_result.get('roles', []),
            'div_codes': access_result['div_codes'],
            'branch_codes': access_result['branch_codes'],
        })
```

Register in `rbac_urls.py`:
```python
router.register('user', viewsets.RbacUserViewSet, basename='rbac-user')
```

### Step 4: Implement Role Lookup Endpoint

```python
class RbacRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Lookup role by role_code."""
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    lookup_field = 'role_code'
    
    def retrieve(self, request, role_code=None):
        role = self.get_object()
        permissions = role.permissions.all()
        
        return Response({
            'role_code': role.role_code,
            'role_name': role.role_name,
            'description': role.description,
            'permissions': [p.code for p in permissions],
        })
```

Register in `rbac_urls.py`:
```python
router.register('role', viewsets.RbacRoleViewSet, basename='rbac-role-detail')
```

### Step 5: Verify Endpoints

Test all endpoints:

```bash
# Roles
curl http://localhost:8000/api/v1/rbac/roles/
curl http://localhost:8000/api/v1/rbac/role/branch_supervisor/

# Permissions
curl http://localhost:8000/api/v1/rbac/permissions/

# User lookup
curl http://localhost:8000/api/v1/rbac/user/ID001/

# User roles
curl http://localhost:8000/api/v1/rbac/user-roles/
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `users/rbac_urls.py` | RBAC URL routing |
| Modify | `backend/urls.py` | Add /rbac/ route |
| Modify | `users/api/viewsets.py` | Add RbacUserViewSet, RbacRoleViewSet |
| Create | `tests/test_rbac_urls.py` | Verify endpoints |

## Phase-Specific Tests

Create `tests/test_rbac_urls.py`:

1. **Test /rbac/ namespace accessible:**
   ```python
   def test_rbac_namespace_accessible():
       response = client.get('/api/v1/rbac/')
       assert response.status_code in [200, 401, 403]  # 200 if public, 401/403 if auth required
   ```

2. **Test role lookup:**
   ```python
   def test_role_lookup():
       response = client.get('/api/v1/rbac/role/branch_supervisor/')
       assert response.status_code == 200
       assert 'permissions' in response.data
   ```

3. **Test user lookup by identity_id:**
   ```python
   def test_user_lookup_by_identity_id():
       response = client.get('/api/v1/rbac/user/ID001/')
       assert response.status_code == 200
       assert 'permissions' in response.data
   ```

4. **Test permissions list:**
   ```python
   def test_permissions_list():
       response = client.get('/api/v1/rbac/permissions/')
       assert response.status_code == 200
   ```

## Completion Gate

- [ ] `/api/v1/rbac/` namespace registered
- [ ] Role CRUD endpoints functional
- [ ] Permission CRUD endpoints functional
- [ ] User lookup by `identity_id` functional
- [ ] Role lookup by `role_code` functional
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests
- [ ] Files committed

## Notes for Next Phase

- Phase 3A (Response envelope) is independent — can run in parallel.
- Phase 3C (Legacy endpoint removal) depends on this phase — /rbac/ endpoints must be available before removing legacy endpoints.
- After this phase, RBAC operations are accessible via standard REST endpoints.
