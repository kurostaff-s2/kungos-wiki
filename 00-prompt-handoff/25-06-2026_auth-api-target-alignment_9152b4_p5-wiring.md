# Phase 5: Production Wiring & Verification

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4-p5` |
| Entity type | `handoff` |
| Short description | End-to-end verification of auth flow post-changes, frontend compatibility check, CBM re-index |
| Status | `draft` |
| Parent plan | `25-06-2026_auth-api-target-alignment_9152b4.md` |
| Phase | 5 of 5 |
| Source references | `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` §4.2, `25-06-2026_auth-api-target-alignment_9152b4.md` §5B |
| Generated | `26-06-2026` |
| Next action / owner | Execute wiring verification — owner: agent with code-edit + test access |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend, port 3001)
**Key files for this phase:**
- `users/api/viewsets.py` — verify auth flow end-to-end
- `users/urls.py` — verify canonical routes only
- `backend/urls.py` — verify no legacy duplicates
- `kteam-fe-chief/src/actions/user.jsx` — adapt to new login response shape (if needed)

---

## What This Phase Delivers

End-to-end verification that all Phases 0-4 produce a working auth system. Canonical routes respond correctly, legacy paths return 404, JWT claims are canonical, login response matches envelope shape, phone normalization works, frontend login flow functions, and CBM re-index shows no new duplicates.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (canonical naming + response shape)
- [ ] Phase 2 is marked complete (legacy paths removed)
- [ ] Phase 3 is marked complete (duplicates removed)
- [ ] Phase 4 is marked complete (M1 scaffolding)
- [ ] Django server can start (`python manage.py runserver`)

---

## Implementation Steps

### 5A. Backend Verification

**Step 5A-1: Start server**

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
python manage.py runserver 0.0.0.0:8000
```

**Step 5A-2: Verify canonical routes**

```bash
# Login (should return envelope-wrapped response)
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210"}' | python -m json.tool

# Verify response shape:
# - Has "status", "data", "meta" keys
# - data.user has "active_div_code", "active_branch_code" (not "division", "branches")
# - data.user has "identity_id" (not "userdata")
# - No "accesslevel" field

# User me (should return envelope-wrapped response)
curl -X GET http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <token>" | python -m json.tool

# Refresh
curl -X POST http://localhost:8000/api/v1/auth/refresh/ | python -m json.tool

# Logout
curl -X POST http://localhost:8000/api/v1/auth/logout/ | python -m json.tool

# Router-generated paths (should work)
curl -X POST http://localhost:8000/api/v1/auth/pwdreset/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210"}' | python -m json.tool

curl -X POST http://localhost:8000/api/v1/auth/verify/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210", "otp": "123456"}' | python -m json.tool
```

**Step 5A-3: Verify legacy paths return 404**

```bash
# users/urls.py legacy paths
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/auth/admin
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/kuro/user
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/empprofile
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/bgSwitch
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/accesslevel

# backend/urls.py legacy paths
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/auth/login   # should 404 (backend copy removed)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/auth/kuroregister
```

All should return `404`.

**Step 5A-4: Verify JWT claims**

```bash
# Decode JWT from login response
python3 -c "
import jwt, json
token = '<access_token_from_login>'
decoded = jwt.decode(token, options={'verify_signature': False})
print(json.dumps(decoded, indent=2))
# Verify:
# - Has 'div_codes' (array), NOT 'division'
# - Has 'branch_codes' (array), NOT 'branches'
# - Has 'active_div_code' (string)
# - Has 'active_branch_code' (string or null)
# - Has 'bg_code' (string)
# - Does NOT have 'entity'
"
```

**Step 5A-5: Verify phone normalization**

```bash
# Login with raw phone (no country code)
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210"}' | python -m json.tool
# Verify: data.user.phone is "+919876543210" (E.164)
```

### 5B. Frontend Compatibility

**Step 5B-1: Verify FE login flow**

1. Ensure `kteam-fe-chief` is running on port 3001.
2. Navigate to login page.
3. Attempt login with valid credentials.
4. Verify: login succeeds, user data displays correctly.

**Step 5B-2: Adapt FE if needed**

If login fails due to response shape change:
1. Open `kteam-fe-chief/src/actions/user.jsx`.
2. Update response parsing to match new envelope shape:
   - Old: `response.user.userdata` → New: `response.data.user`
   - Old: `response.user.division` → New: `response.data.user.active_div_code`
   - Old: `response.user.accesslevel` → New: `response.data.user.permissions`

### 5C. CBM Re-index

**Step 5C-1: Re-index codebase**

```bash
codebase_index /home/chief/Coding-Projects/kteam-dj-chief
```

**Step 5C-2: Verify no new issues**

1. Check for new SIMILAR_TO edges in `users/` or `backend/auth_utils.py`.
2. Verify dead code count unchanged.
3. Verify route nodes reflect only canonical paths.

### 5D. Run Existing Test Suite

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
pytest tests/ -v --tb=short 2>&1 | tail -30
# Or: python manage.py test users --verbosity=2
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify (if needed) | `kteam-fe-chief/src/actions/user.jsx` | Adapt to new login response shape |
| Read | `users/urls.py` | Verify only canonical paths remain |
| Read | `backend/urls.py` | Verify no legacy duplicates remain |

---

## Phase-Specific Tests

1. **Login returns envelope shape:** `POST /api/v1/auth/login/` → `{status, data, meta}` with correct user fields.
2. **User me returns envelope shape:** `GET /api/v1/users/me/` → same structure.
3. **JWT claims canonical:** Decoded JWT has `div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`. No `division`, `branches`, `entity`.
4. **Phone normalized:** Raw `9876543210` → `+919876543210` in response.
5. **Legacy paths 404:** All 28 removed paths return 404.
6. **Router-generated paths work:** `/auth/pwdreset/`, `/auth/verify/` return expected responses.
7. **Frontend login works:** `http://localhost:3001` login flow completes successfully.
8. **No regression:** All existing tests pass.
9. **CBM clean:** No new SIMILAR_TO edges, no new dead code.

---

## Completion Gate

- [ ] `POST /api/v1/auth/login/` returns envelope-wrapped target response shape
- [ ] `GET /api/v1/users/me/` returns envelope-wrapped target response shape
- [ ] `POST /api/v1/auth/logout/` blacklists token
- [ ] `POST /api/v1/auth/refresh/` rotates token
- [ ] `POST /api/v1/auth/pwdreset/` works (router-generated)
- [ ] `POST /api/v1/auth/verify/` works (router-generated)
- [ ] All legacy paths return 404
- [ ] Phone normalization: raw input → E.164 in response
- [ ] JWT claims use `div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`
- [ ] All existing tests pass (no regression)
- [ ] Frontend login flow works on `http://localhost:3001`
- [ ] CBM re-index shows no new duplicates or dead code

---

## Notes for Next Phase

This is the final phase. Upon completion, the master handoff (9152b4) is complete. M1 data migration is a separate handoff per `migration_spec.md`.
