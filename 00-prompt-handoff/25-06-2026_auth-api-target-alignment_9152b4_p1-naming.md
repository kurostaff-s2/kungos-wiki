# Phase 1: Spec Tightening & Naming Canonicalization

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4-p1` |
| Entity type | `handoff` |
| Short description | Canonicalize tenant field names in JWT/serializers, align login response to envelope shape, add phone normalization, consolidate CookieTokenRefreshView |
| Status | `draft` |
| Parent plan | `25-06-2026_auth-api-target-alignment_9152b4.md` |
| Phase | 1 of 5 |
| Source references | `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` §4.2, `llm-wiki/Kung_OS/architecture/multi_tenancy.md` glossary |
| Generated | `26-06-2026` |
| Next action / owner | Execute naming canonicalization — owner: agent with code-edit access |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Key files for this phase:**
- `users/tenant_tokens.py` — JWT claim generation
- `users/api/viewsets.py` — AuthViewSet (login, refresh, _build_login_response, _resolve_tenant_context)
- `users/serializers.py` — UserSerializer, AccesslevelSerializer
- `users/utils.py` — new file (phone normalization)
- `backend/auth_utils.py` — resolve_access (canonicalize param names)

---

## What This Phase Delivers

Three sub-tasks: (1A) JWT claims and serializer output use canonical `div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`. (1B) Login and /users/me responses wrapped in `{status, data, meta}` envelope per `endpoint_contract_spec.md` §4.2. (1C) Phone input normalized to E.164 at all auth entry points.

---

## Pre-Flight Checklist

- [ ] Phase 0 is marked complete (contracts frozen)
- [ ] `multi_tenancy.md` glossary and `endpoint_contract_spec.md` §4.2 are readable
- [ ] `phonenumbers` library installed (`pip show phonenumbers`)

---

## Implementation Steps

### 1A. Canonical Tenant Field Names

**Step 1A-1: JWT claims (`users/tenant_tokens.py`)**

1. Open `users/tenant_tokens.py`.
2. In `_resolve_tenant_context` (or equivalent JWT payload builder):
   - Replace `division` (JSON array) → `div_codes` (array of strings).
   - Replace `branches` (JSON array) → `branch_codes` (array of strings).
   - Add `active_div_code` (string) — first element of scope or from tenant switch.
   - Add `active_branch_code` (string or null) — from tenant switch or null.
   - Remove `entity` claim entirely.
3. Verify `bg_code` is present (not `bgcode`).

**Step 1A-2: ViewSet tenant context (`users/api/viewsets.py`)**

1. In `AuthViewSet._resolve_tenant_context`:
   - Return dict with keys: `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `bg_code`.
   - Do NOT return `division`, `branches`, `entity`.

**Step 1A-3: Serializer output (`users/serializers.py`)**

1. In `UserSerializer` (or create `IdentityResponseSerializer`):
   - Output `active_div_code` (string) — active context.
   - Output `active_branch_code` (string or null) — active context.
   - Output `div_codes` (array) — authorization scope.
   - Output `branch_codes` (array) — authorization scope.
   - Output `bg_code` (string).
   - Do NOT output `division`, `branches`, `entity`.

**Step 1A-4: Auth utils (`backend/auth_utils.py`)**

1. In `resolve_access` and related functions:
   - Accept `bg_code`, `div_codes`, `branch_codes`, `active_div_code` as param names.
   - Do not use `division`, `branches`, `bgcode`.

### 1B. Response Shape Alignment

**Step 1B-1: Create envelope wrapper**

1. In `users/api/viewsets.py`, create a helper:
```python
def _envelope_response(data, status="success", request=None):
    import uuid, datetime
    return {
        "status": status,
        "data": data,
        "meta": {
            "request_id": str(uuid.uuid4())[:12],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    }
```

**Step 1B-2: Rewrite `_build_login_response`**

1. Replace `_build_login_response` to produce:
```python
{
    "access_token": str(access_token),
    "refresh_token": str(refresh_token),
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
        "identity_id": identity_id,
        "phone": phone,
        "name": name,
        "bg_code": bg_code,
        "active_div_code": active_div_code,
        "active_branch_code": active_branch_code,
        "roles": roles_list,
        "permissions": permissions_list,
        "is_admin": is_admin,
    }
}
```
2. Remove `AccesslevelSerializer` from login response entirely.
3. Remove `KuroUser.roles` JSON — use RBAC-derived roles only.
4. Wrap result in `_envelope_response()`.

**Step 1B-3: Rewrite `UserViewSet.me`**

1. Apply same envelope-wrapped shape to `GET /users/me`.
2. Use `IdentityResponseSerializer` if created in 1A-3.

**Step 1B-4: Consolidate `CookieTokenRefreshView`**

1. Trace callers of `CookieTokenRefreshView` (CBM trace or grep).
2. If no external imports: delete standalone class, redirect URL to `AuthViewSet.refresh` action.
3. If external imports exist: keep class but delegate to `AuthViewSet.refresh` internally.

### 1C. Phone Normalization Guard

**Step 1C-1: Create `users/utils.py`**

```python
import phonenumbers

def normalize_phone(raw: str, region: str = "IN") -> str:
    """Normalize phone to E.164. Idempotent, whitespace-tolerant."""
    if not raw:
        return raw
    cleaned = raw.strip()
    try:
        parsed = phonenumbers.parse(cleaned, region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return cleaned
```

**Step 1C-2: Apply at entry points**

1. `AuthViewSet.login` — normalize `phone` before lookup.
2. `RegisterViewSet.kuro` — normalize `phone` before create.
3. `RegisterViewSet.reb` — normalize `phone` before create.
4. `PhoneOTPViewSet.send` — normalize `phone` before send.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `users/tenant_tokens.py` | JWT claims: canonical names |
| Modify | `users/api/viewsets.py` | _resolve_tenant_context, _build_login_response, CookieTokenRefreshView consolidation |
| Modify | `users/serializers.py` | UserSerializer output or new IdentityResponseSerializer |
| Modify | `backend/auth_utils.py` | resolve_access: canonical param names |
| Create | `users/utils.py` | `normalize_phone` function |

---

## Phase-Specific Tests

1. **JWT claims:** Decode JWT from login response — contains `div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`. Does NOT contain `division`, `branches`, `entity`.
2. **Login response shape:** `POST /api/v1/auth/login/` returns `{status, data: {access_token, refresh_token, token_type, expires_in, user}, meta}`.
3. **User me shape:** `GET /api/v1/users/me/` returns same envelope structure.
4. **Phone normalization:** `normalize_phone("9876543210")` → `"+919876543210"`. Idempotent on E.164 input.
5. **No AccesslevelSerializer:** Login response does NOT contain `accesslevel` field.
6. **Existing tests pass:** `pytest users/tests/ -v` (or equivalent test runner).

---

## Completion Gate

- [ ] All JWT claims use `div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`
- [ ] `entity` claim removed from JWT
- [ ] Login response matches envelope-wrapped target shape
- [ ] `GET /users/me` matches envelope-wrapped target shape
- [ ] `CookieTokenRefreshView` consolidated or delegated
- [ ] Phone normalization applied at all 4 auth entry points
- [ ] `AccesslevelSerializer` removed from login response
- [ ] Existing tests still pass

---

## Notes for Next Phase

Phase 2 removes legacy URL paths. After Phase 1 is complete, the canonical routes and response shapes are in place — Phase 2 only needs to delete the old paths and verify no 404s on canonical routes.
