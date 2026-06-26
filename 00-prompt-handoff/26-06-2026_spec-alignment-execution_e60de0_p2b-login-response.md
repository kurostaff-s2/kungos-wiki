# Phase 2B: Login Response Rewrite

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 2B of 5 (parallel with 2A, 2C, 2D)
**Dependencies:** Phase 2A (RBAC FK migration must be complete)
**Estimated effort:** ~30 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p2b` |
| Entity type | `handoff` |
| Short description | Rewrite login response to match spec §4.2 target shape. Replace `userid` with `identity_id`, `accesslevel` with `permissions[]`, add required fields. |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md` §4.2 |
| Generated | `26-06-2026` |
| Next action / owner | Execute login response rewrite — create serializer, update views, verify shape |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/views.py` (login function, lines 100-350)
- `users/api/viewsets.py` (user profile endpoint, lines 800-900)
- `users/serializers.py` (if exists, otherwise create)
- `users/tenant_tokens.py` (JWT token generation)
- `tests/test_login_response.py` (existing tests)
**Related codebases:** None

## What This Phase Delivers

Login response matches spec §4.2 target shape exactly. Returns `identity_id` (not `userid`), `permissions[]` (not `accesslevel[]`), `refresh_token`, `token_type`, `expires_in`, `roles[]`, `active_div_code`, `active_branch_code`. Phone is E.164 normalized. No legacy fields (`accesslevel`, `businessgroups`, `access`) in response.

## Pre-Flight Checklist

- [ ] Phase 2A is marked complete (RBAC uses `identity_id`)
- [ ] `resolve_access(identity_id, bg_code)` works correctly
- [ ] `Identity` model has `identity_id` for all users
- [ ] JWT claims include `identity_id`

## Implementation Steps

### Step 1: Define Target Response Shape

Per spec §4.2, the login response must be:

```json
{
    "status": "success",
    "data": {
        "identity_id": "ID001",
        "phone": "+919876543210",
        "bg_code": "KURO0001",
        "active_div_code": "DIV001",
        "active_branch_code": "BRANCH001",
        "token": "eyJhbG...",
        "refresh_token": "dGhpcyBpcy...",
        "token_type": "Bearer",
        "expires_in": 3600,
        "permissions": ["admin.full", "orders.read", "invoices.outward"],
        "roles": ["branch_supervisor", "order_manager"],
        "profile": {
            "name": "John Doe",
            "email": "john@example.com"
        }
    },
    "meta": {
        "request_id": "req-abc123",
        "timestamp": "2026-06-26T12:00:00Z"
    }
}
```

### Step 2: Create Login Response Serializer

Create `users/login_serializers.py`:

```python
from rest_framework import serializers

class LoginResponseSerializer(serializers.Serializer):
    identity_id = serializers.CharField()
    phone = serializers.CharField()
    bg_code = serializers.CharField()
    active_div_code = serializers.CharField(allow_blank=True, default='')
    active_branch_code = serializers.CharField(allow_blank=True, default='')
    token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField(default='Bearer')
    expires_in = serializers.IntegerField(default=3600)
    permissions = serializers.ListField(child=serializers.CharField())
    roles = serializers.ListField(child=serializers.CharField())
    profile = serializers.DictField()
```

### Step 3: Update Login View

Read `users/views.py` and update the login function:

**Current pattern (legacy):**
```python
userData = {
    'userid': user.userid,
    'accesslevel': accesslevels,
    'businessgroups': bgs,
    'access': user.access,
    'division': divisions,
    'branches': branches,
    # ... other legacy fields
}
```

**New pattern:**
```python
from backend.auth_utils import resolve_access
from users.models import Identity, UserTenantContext

# Get identity
identity = Identity.objects.get(user=user)

# Get tenant context
tenant_ctx = UserTenantContext.objects.get(
    userid=user.userid,
    bg_code=bg_code
)

# Resolve permissions
access_result = resolve_access(identity.identity_id, bg_code)

# Build response
login_data = {
    'identity_id': identity.identity_id,
    'phone': normalize_e164(identity.phone),
    'bg_code': bg_code,
    'active_div_code': tenant_ctx.div_codes[0] if tenant_ctx.div_codes else '',
    'active_branch_code': tenant_ctx.branch_codes[0] if tenant_ctx.branch_codes else '',
    'token': auth_token,
    'refresh_token': refresh_token,
    'token_type': 'Bearer',
    'expires_in': 3600,
    'permissions': access_result['permissions'],
    'roles': [role.role_code for role in access_result.get('roles', [])],
    'profile': {
        'name': user.full_name or '',
        'email': user.email or '',
    },
}

serializer = LoginResponseSerializer(login_data)
return Response({'status': 'success', 'data': serializer.data})
```

### Step 4: Update User Profile Endpoint

Read `users/api/viewsets.py` and update the user profile endpoint (lines 800-900):

**Current pattern:**
```python
userdata['access'] = userdetails.access
userdata['accesslevel'] = accesslevels
```

**New pattern:**
```python
identity = Identity.objects.get(user=request.user)
access_result = resolve_access(identity.identity_id, bg_code)

userdata = {
    'identity_id': identity.identity_id,
    'phone': identity.phone,
    'bg_code': bg_code,
    'permissions': access_result['permissions'],
    'roles': access_result.get('roles', []),
    'profile': {
        'name': request.user.full_name,
        'email': request.user.email,
    },
}
```

### Step 5: Add Phone E.164 Normalization

Create helper function:

```python
import phonenumbers

def normalize_e164(phone: str) -> str:
    """Normalize phone number to E.164 format."""
    try:
        parsed = phonenumbers.parse(phone, None)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        # If parsing fails, return as-is with + prefix if missing
        return phone if phone.startswith('+') else f'+{phone}'
```

### Step 6: Generate Refresh Token

Update `users/tenant_tokens.py` to generate refresh tokens:

```python
import jwt
from datetime import datetime, timedelta

def generate_refresh_token(user, identity_id):
    """Generate refresh token."""
    payload = {
        'user_id': str(user.id),
        'identity_id': identity_id,
        'type': 'refresh',
        'exp': datetime.utcnow() + timedelta(days=7),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `users/login_serializers.py` | Login response serializer |
| Modify | `users/views.py` | Update login function |
| Modify | `users/api/viewsets.py` | Update user profile endpoint |
| Modify | `users/tenant_tokens.py` | Add refresh token generation |
| Modify | `tests/test_login_response.py` | Update tests for new response shape |
| Create | `tests/test_login_response_shape.py` | Verify response matches spec |

## Phase-Specific Tests

Create `tests/test_login_response_shape.py`:

1. **Test login response has identity_id:**
   ```python
   def test_login_response_has_identity_id():
       response = client.post('/api/v1/users/auth/login/', data=login_data)
       assert 'identity_id' in response.data['data']
       assert 'userid' not in response.data['data']
   ```

2. **Test login response has permissions:**
   ```python
   def test_login_response_has_permissions():
       response = client.post('/api/v1/users/auth/login/', data=login_data)
       assert 'permissions' in response.data['data']
       assert isinstance(response.data['data']['permissions'], list)
   ```

3. **Test login response has no legacy fields:**
   ```python
   def test_login_response_no_legacy_fields():
       response = client.post('/api/v1/users/auth/login/', data=login_data)
       data = response.data['data']
       assert 'accesslevel' not in data
       assert 'businessgroups' not in data
       assert 'access' not in data
   ```

4. **Test phone is E.164:**
   ```python
   def test_phone_e164_normalized():
       response = client.post('/api/v1/users/auth/login/', data=login_data)
       phone = response.data['data']['phone']
       assert phone.startswith('+')
   ```

5. **Test refresh token present:**
   ```python
   def test_refresh_token_present():
       response = client.post('/api/v1/users/auth/login/', data=login_data)
       assert 'refresh_token' in response.data['data']
       assert response.data['data']['token_type'] == 'Bearer'
   ```

## Completion Gate

- [ ] Login response matches spec §4.2 shape
- [ ] `identity_id` present, `userid` absent
- [ ] `permissions[]` populated from RBAC
- [ ] `refresh_token` present
- [ ] Phone E.164 normalized
- [ ] No legacy fields (`accesslevel`, `businessgroups`, `access`)
- [ ] All phase-specific tests pass
- [ ] No regression in existing auth tests
- [ ] Files committed

## Notes for Next Phase

- Phase 3C (Legacy endpoint removal) depends on this phase — login response must be new shape before removing legacy endpoints.
- Frontend may need to be updated to handle new response shape. Coordinate with frontend team.
- Consider versioned endpoint (`/auth/login/v2`) if frontend cannot be updated simultaneously.

## Caveats

1. **Frontend breakage risk:** If frontend depends on current response shape, this change will break login. **Mitigation:** Coordinate with frontend team. Consider versioned endpoint.

2. **Third-party integrations:** If third-party apps use the login endpoint, they may break. **Mitigation:** Notify third-party developers. Provide migration guide.

3. **Phone normalization edge cases:** Some phone numbers may not parse correctly. **Mitigation:** Fall back to original value with `+` prefix if parsing fails.
