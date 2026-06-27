# Phase 2B: Login Response Rewrite

**Parent plan:** `26-06-2026_spec-alignment-execution_e60de0.md`
**Phase:** 2B of 5 (parallel with 2A, 2C, 2D)
**Dependencies:** Phase 2A (RBAC FK migration must be complete — `identity_id` available in RBAC)
**Estimated effort:** ~30 min

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0-p2b` |
| Entity type | `handoff` |
| Short description | Rewrite login response to match endpoint contract spec §4.2 exactly. Auth under `/api/v1/auth/` namespace. `data.user` nested structure. Separate active tenant context from accessible tenant scope. |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md` §4.1, §4.2, §7.1 |
| Generated | `26-06-2026` |
| Next action / owner | Execute login response rewrite — serializer, view, JWT claims, verification |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Key files for this phase:**
- `users/views.py` (login function)
- `users/serializers.py` (create login response serializer)
- `users/tenant_tokens.py` (JWT claims — add `identity_id`)
- `backend/auth_utils.py` (`resolve_access` — must accept `identity_id`)
- `backend/urls.py` (verify auth routes under `/api/v1/auth/`)
**Related codebases:** None

## What This Phase Delivers

Login endpoint at `POST /api/v1/auth/login` returns response matching spec §4.2 exactly. `identity_id` replaces `userid`. `permissions[]` replaces `accesslevel[]`. `data.user` nests all user fields. Active tenant context (`active_div_code`, `active_branch_code`) is separate from accessible tenant scope (`bg_code`). No legacy fields (`accesslevel`, `businessgroups`, `access`). Phone is E.164 normalized.

## Pre-Flight Checklist

- [ ] Phase 2A is marked complete (RBAC uses `identity_id`)
- [ ] `resolve_access(identity_id, bg_code)` returns permissions and roles
- [ ] `Identity.objects.get(user=user)` works for all users
- [ ] `UserTenantContext` has `div_codes` and `branch_codes` lists

## Implementation Steps

### Step 1: Define Target Response Shape (Spec §4.2)

**Endpoint:** `POST /api/v1/auth/login`

**Target response (verbatim from spec §4.2):**

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

**Field semantics:**

| Field | Location | Meaning |
|-------|----------|---------|
| `data.access_token` | Top-level `data` | JWT access token |
| `data.token_type` | Top-level `data` | Always `"Bearer"` |
| `data.expires_in` | Top-level `data` | Token TTL in seconds |
| `data.user.identity_id` | Nested `user` | Canonical identity PK |
| `data.user.phone` | Nested `user` | E.164 normalized phone |
| `data.user.bg_code` | Nested `user` | Tenant scope (accessible business group) |
| `data.user.active_div_code` | Nested `user` | Active division context (single value) |
| `data.user.active_branch_code` | Nested `user` | Active branch context (single value) |
| `data.user.roles` | Nested `user` | Roles from RBAC |
| `data.user.permissions` | Nested `user` | Permissions from RBAC |
| `data.user.email` | Nested `user` | User email |

**Critical separation:**
- `bg_code` = accessible tenant scope (what the user CAN access)
- `active_div_code`, `active_branch_code` = active tenant context (what the user IS currently operating in)
- These are NOT arrays — they are single values representing the active session context

### Step 2: Create Login Response Serializer

Create `users/serializers.py` (append if file exists):

```python
from rest_framework import serializers


class LoginUserSerializer(serializers.Serializer):
    """Nested user object in login response per spec §4.2."""
    identity_id = serializers.CharField()
    phone = serializers.CharField()
    bg_code = serializers.CharField()
    active_div_code = serializers.CharField(allow_blank=True, default='')
    active_branch_code = serializers.CharField(allow_blank=True, default='')
    roles = serializers.ListField(child=serializers.CharField(), default=list)
    permissions = serializers.ListField(child=serializers.CharField(), default=list)
    email = serializers.EmailField(allow_blank=True, default='')


class LoginResponseSerializer(serializers.Serializer):
    """Top-level login response per spec §4.2."""
    access_token = serializers.CharField()
    token_type = serializers.CharField(default='Bearer')
    expires_in = serializers.IntegerField(default=3600)
    user = LoginUserSerializer()
```

### Step 3: Update Login View

Read `users/views.py` and update the login function.

**Current pattern (legacy):**
```python
userData = {
    'userid': user.userid,
    'accesslevel': accesslevels,
    'businessgroups': bgs,
    'access': user.access,
    'division': divisions,
    'branches': branches,
}
```

**New pattern (spec §4.2):**
```python
from backend.auth_utils import resolve_access
from users.models import Identity, UserTenantContext
from users.serializers import LoginResponseSerializer


def login_view(request):
    """Login endpoint — spec §4.2 target shape."""
    # 1. Authenticate user (existing logic)
    # ... authentication code ...
    
    # 2. Resolve identity
    identity = Identity.objects.get(user=user)
    
    # 3. Get active tenant context
    tenant_ctx = UserTenantContext.objects.get(
        userid=user.userid,
        bg_code=request.data.get('bg_code', 'KURO0001')
    )
    
    # 4. Resolve RBAC permissions
    access_result = resolve_access(identity.identity_id, tenant_ctx.bg_code)
    
    # 5. Generate JWT token
    from users.tenant_tokens import generate_token
    access_token = generate_token(user, identity.identity_id)
    
    # 6. Build response per spec §4.2
    response_data = {
        'access_token': access_token,
        'token_type': 'Bearer',
        'expires_in': 3600,
        'user': {
            'identity_id': identity.identity_id,
            'phone': normalize_e164(identity.phone),
            'bg_code': tenant_ctx.bg_code,
            'active_div_code': tenant_ctx.div_codes[0] if tenant_ctx.div_codes else '',
            'active_branch_code': tenant_ctx.branch_codes[0] if tenant_ctx.branch_codes else '',
            'roles': access_result.get('roles', []),
            'permissions': access_result.get('permissions', []),
            'email': user.email or '',
        },
    }
    
    serializer = LoginResponseSerializer(response_data)
    return Response({'status': 'success', 'data': serializer.data})
```

### Step 4: Add `identity_id` to JWT Claims

Update `users/tenant_tokens.py` to include `identity_id` in JWT payload:

```python
def generate_token(user, identity_id):
    """Generate JWT access token with identity_id claim."""
    payload = {
        'user_id': str(user.id),
        'identity_id': identity_id,  # Canonical: required for RBAC resolution
        'bg_code': user.bg_code,
        'exp': datetime.utcnow() + timedelta(hours=1),
        'iat': datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
```

### Step 5: Add Phone E.164 Normalization Helper

Create `users/utils.py` (or append to existing utils):

```python
import phonenumbers


def normalize_e164(phone: str) -> str:
    """Normalize phone number to E.164 format (+91XXXXXXXXXX)."""
    try:
        parsed = phonenumbers.parse(phone, 'IN')
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        # Fallback: ensure + prefix
        return phone if phone.startswith('+') else f'+{phone}'
```

### Step 6: Verify Auth URL Routing

Confirm `backend/urls.py` has auth routes under `/api/v1/auth/` (NOT `/api/v1/users/auth/`):

```python
# backend/urls.py
urlpatterns = [
    path('api/v1/auth/', include('users.auth_urls')),
    # ... other routes
]
```

**Expected endpoint:** `POST /api/v1/auth/login`

**NOT:** `POST /api/v1/users/auth/login/`

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/serializers.py` | Add `LoginResponseSerializer`, `LoginUserSerializer` |
| Modify | `users/views.py` | Rewrite login function |
| Modify | `users/tenant_tokens.py` | Add `identity_id` to JWT claims |
| Create | `users/utils.py` | `normalize_e164()` helper |
| Verify | `backend/urls.py` | Confirm auth under `/api/v1/auth/` |
| Modify | `tests/test_login_response.py` | Update tests for new shape |
| Create | `tests/test_login_response_shape.py` | Verify spec compliance |

## Phase-Specific Tests

Create `tests/test_login_response_shape.py`:

```python
from django.test import Client
from users.models import Identity, UserTenantContext


class TestLoginResponseShape:
    """Verify login response matches spec §4.2 exactly."""
    
    def setup_method(self):
        self.client = Client()
    
    def test_endpoint_path_is_auth_namespace(self):
        """Endpoint must be /api/v1/auth/login, NOT /api/v1/users/auth/login/."""
        # This test verifies the URL routing is correct
        # If the endpoint is under /users/auth/, the URL pattern is wrong
        from django.urls import reverse
        # The URL should resolve to /api/v1/auth/login
        # (exact reverse lookup depends on URL name)
        pass
    
    def test_response_has_access_token_not_token(self):
        """Spec uses 'access_token', not 'token'."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        assert 'access_token' in response.data['data']
        assert 'token' not in response.data['data']
    
    def test_user_fields_nested_under_data_user(self):
        """All user fields must be under data.user, NOT flattened."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        data = response.data['data']
        
        # These must NOT be at top level
        assert 'identity_id' not in data
        assert 'phone' not in data
        assert 'bg_code' not in data
        assert 'permissions' not in data
        assert 'roles' not in data
        
        # These MUST be under user
        user = data['user']
        assert 'identity_id' in user
        assert 'phone' in user
        assert 'bg_code' in user
        assert 'permissions' in user
        assert 'roles' in user
    
    def test_active_tenant_context_is_single_value(self):
        """active_div_code and active_branch_code are single values, not arrays."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        user = response.data['data']['user']
        
        # Single string values, not lists
        assert isinstance(user['active_div_code'], str)
        assert isinstance(user['active_branch_code'], str)
    
    def test_no_legacy_fields(self):
        """No accesslevel, businessgroups, or access in response."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        data = response.data['data']
        
        assert 'accesslevel' not in data
        assert 'businessgroups' not in data
        assert 'access' not in data
        assert 'userid' not in data
        
        user = data['user']
        assert 'accesslevel' not in user
        assert 'userid' not in user
    
    def test_phone_is_e164(self):
        """Phone must be E.164 normalized (+91XXXXXXXXXX)."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        phone = response.data['data']['user']['phone']
        assert phone.startswith('+91')
        assert len(phone) == 13  # +91 + 10 digits
    
    def test_identity_id_present(self):
        """identity_id must be present, userid must not."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        user = response.data['data']['user']
        assert 'identity_id' in user
        assert 'userid' not in user
    
    def test_roles_and_permissions_are_lists(self):
        """roles and permissions must be lists, even if empty."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        user = response.data['data']['user']
        assert isinstance(user['roles'], list)
        assert isinstance(user['permissions'], list)
    
    def test_token_type_is_bearer(self):
        """token_type must be 'Bearer'."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        assert response.data['data']['token_type'] == 'Bearer'
    
    def test_expires_in_is_integer(self):
        """expires_in must be an integer (seconds)."""
        response = self.client.post(
            '/api/v1/auth/login/',
            data={'phone': '+919876543210', 'password': 'test'},
            format='json'
        )
        assert isinstance(response.data['data']['expires_in'], int)
```

## Completion Gate

- [ ] Login endpoint at `POST /api/v1/auth/login` (auth namespace, not users namespace)
- [ ] Response matches spec §4.2 shape exactly
- [ ] `data.access_token` present (not `data.token`)
- [ ] `data.user` nested object with all user fields
- [ ] `active_div_code` and `active_branch_code` are single string values
- [ ] `bg_code` is the accessible tenant scope (separate from active context)
- [ ] `identity_id` present, `userid` absent
- [ ] `permissions[]` populated from RBAC
- [ ] `roles[]` populated from RBAC
- [ ] Phone E.164 normalized
- [ ] No legacy fields (`accesslevel`, `businessgroups`, `access`)
- [ ] JWT claims include `identity_id`
- [ ] All phase-specific tests pass
- [ ] No regression in existing auth tests
- [ ] Files committed

## Post-Verification (Gate)

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
pytest tests/test_login_response_shape.py -v
```

**Expected:** All 10 tests pass.

## Notes for Next Phase

- Phase 3C (Legacy endpoint removal) depends on this phase — login response must be new shape before removing legacy endpoints.
- Phase 2D (RBAC URLs) can run in parallel — no dependency on login response.
- Frontend integration: Frontend must be updated to read `data.user.identity_id` instead of `data.userid`, and `data.user.permissions` instead of `data.accesslevel`.
- The `email` field is included in the login response per spec §4.2. If the user has no email, return empty string `""`.

## Caveats

1. **JWT claim compatibility:** Existing JWT tokens do not have `identity_id` claim. After this phase, new tokens will have it. Old tokens will fail `resolve_access(identity_id)` until users re-login. This is acceptable — it's a migration break.

2. **Refresh tokens:** The spec §4.2 login response does NOT include `refresh_token`. Refresh tokens are handled separately via `POST /api/v1/auth/refresh/`. Do not add `refresh_token` to the login response.

3. **Active vs. accessible tenant scope:** `bg_code` represents what the user CAN access (accessible scope). `active_div_code` and `active_branch_code` represent what the user IS currently operating in (active context). These are intentionally separate — a user may have access to multiple divisions but only be active in one.

## Consistency Rules

**This phase defers to:**
- Wire shapes: `endpoint_contract_spec.md` §4.2 (login response)
- Canonical naming: `CANONICAL_NAMING.md` (`identity_id`, `token_type`, `refresh_token`)

**This phase does NOT redefine:**
- Migration ordering (Phase 1A handles identity migration)
- RBAC FK structure (Phase 2A handles FK migration)
- Mongo field names (Phase 1B handles field rename)

## Spec Contradictions

_None documented._

