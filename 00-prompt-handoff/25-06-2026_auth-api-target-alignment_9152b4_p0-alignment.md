# Phase 0: Architectural Alignment & Contract Freeze

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4-p0` |
| Entity type | `handoff` |
| Short description | Resolve cross-spec inconsistencies: tenant semantics, response envelope, legacy path inventory, SIMILAR_TO audit, model inventory |
| Status | `draft` |
| Parent plan | `25-06-2026_auth-api-target-alignment_9152b4.md` |
| Phase | 0 of 5 |
| Source references | `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`, `llm-wiki/Kung_OS/specs/domain_specs/identity_spec.md`, `llm-wiki/Kung_OS/architecture/multi_tenancy.md`, `llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute spec alignment — owner: agent with spec-edit access |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:** Only the four files listed above
**Key files for this phase:** Documentation only — no code modifications

---

## What This Phase Delivers

No code changes. This phase resolves every cross-spec inconsistency so Phases 1-5 execute against a single source of truth. Produces: canonical tenant field semantics, frozen login response envelope, verified legacy path inventory (28 paths), SIMILAR_TO duplicate inventory (9 functions), and Phase 4 model inventory (9 models).

---

## Pre-Flight Checklist

- [ ] All four reference docs are readable
- [ ] No other agent is modifying these specs concurrently

---

## Implementation Steps

### Step 1: Tenant Semantics — Scope vs Active Context

**File:** `llm-wiki/Kung_OS/architecture/multi_tenancy.md`

1. Add the canonical glossary table (if not present):

| Legacy Field/Claim | Canonical Field | Context |
|-------------------|-----------------|---------|
| `division` (JSON array) | `div_codes[]` (scope) / `active_div_code` (active) | JWT + UserTenantContext |
| `branches` (JSON array) | `branch_codes[]` (scope) / `active_branch_code` (active) | JWT + UserTenantContext |
| `entity[0]` | `active_div_code` | JWT (stale — removed) |
| `bgcode` | `bg_code` | MongoDB documents |
| `branch` | `branch_code` | MongoDB documents |

2. Correct session variables table:

| Variable | Source | Purpose |
|----------|--------|---------|
| `app.current_bg_code` | JWT `bg_code` | Tenant scope (required) |
| `app.current_division` | JWT `active_div_code` | Active division scope |
| `app.current_branch` | JWT `active_branch_code` | Active branch scope |
| `app.current_userid` | JWT `identity_id` | User identity |

3. Add JWT claims target section:

- `bg_code` — string (single BG from active context)
- `div_codes` — array (authorization scope)
- `branch_codes` — array (authorization scope)
- `active_div_code` — string (current active division)
- `active_branch_code` — string or null (current active branch)

### Step 2: Response Envelope Freeze

**File:** `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`

1. Verify §4.2 Target login response matches this exact shape:

```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "refresh_token": "dXJ...",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "identity_id": "ID000001",
            "phone": "+91XXXXXXXXXX",
            "name": "...",
            "bg_code": "KURO0001",
            "active_div_code": "KURO0001_001",
            "active_branch_code": null,
            "roles": ["employee", "customer"],
            "permissions": ["users.view", "orders.create"],
            "is_admin": false
        }
    },
    "meta": {
        "request_id": "req_abc123",
        "timestamp": "2026-06-25T10:00:00Z"
    }
}
```

2. Verify maturity rule is stated: `employee_profile`, `customer_profile`, `player_profile` are **nullable/absent until M1 data backfill completes**.

### Step 3: Legacy Path Inventory Verification

**Files to read:** `users/urls.py`, `backend/urls.py`

1. Count explicit `path()` entries in `users/urls.py` that are NOT router-generated. Verify 14 legacy paths exist (not 12).
2. Count explicit `path()` entries in `backend/urls.py` that duplicate `users/urls.py` paths. Verify 14 duplicates exist.
3. Confirm `pwdreset` and `verify` are `@action` on `AuthViewSet` (router-generated `/auth/pwdreset/` and `/auth/verify/` survive).

**Inventory (must match):**

`users/urls.py` REMOVE (14):
`auth/kuroregister`, `auth/rebregister`, `auth/admin`, `auth/staff`, `auth/reb`, `kuro/user`, `reb/user`, `empprofile`, `pwdreset`, `verify`, `accesslevel`, `employeesdata`, `emp_acc`, `bgSwitch`

`users/urls.py` KEEP (5):
`auth/login`, `auth/refresh`, `auth/logout`, `auth/health`, `auth/monitoring/401`

`backend/urls.py` REMOVE (14):
`api/v1/bgSwitch`, `api/v1/accesslevel`, `api/v1/pwdreset`, `api/v1/verify`, `api/v1/empprofile`, `api/v1/employeesdata`, `api/v1/kuro/user`, `api/v1/reb/user`, `api/v1/emp_acc`, `api/v1/auth/login`, `api/v1/auth/kuroregister`, `api/v1/auth/rebregister`, `api/v1/auth/refresh`, `api/v1/auth/logout`

### Step 4: SIMILAR_TO Duplicate Inventory

**Files to read:** `backend/auth_utils.py`, `backend/utils.py`

1. Verify these 9 functions exist in BOTH files (delete utils.py copy):
   `has_read_access`, `has_write_access`, `get_branch_fallback`, `get_accessible_divisions`, `get_all_divisions`, `has_division_write_access`, `check_access`, `check_write_access`, `check_division_write_access`

2. Verify `resolve_access_levels` exists ONLY in `utils.py` and is imported by `auth_utils.py` — DO NOT DELETE.

3. Verify `close_mongo_client` has 0 callers — mark as dead.

### Step 5: Phase 4 Model Inventory

**File to read:** `llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` §3

Verify 9 models are listed:
1. `Identity` → `users_identity`
2. `EmployeeProfile` → `users_employee`
3. `CustomerProfile` → `users_customer`
4. `PlayerProfile` → `users_player`
5. `Organization` → `users_organization`
6. `VendorProfile` → `users_vendor_profile`
7. `TeamProfile` → `users_team_profile`
8. `TeamMembership` → `team_memberships`
9. `PhoneAlias` → `identity_phone_aliases`

### Step 6: Shared Utility Ownership Table

Document in master handoff:

| Module | Owns | Delete After |
|--------|------|-------------|
| `backend/auth_utils.py` | Access resolution functions | — |
| `backend/utils.py` | MongoDB helpers + `resolve_access_levels` | — |
| `plat/tenant/` | Tenant isolation (RLS, schema) | — |
| `users/permissions.py` | RBAC resolution | — |

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `llm-wiki/Kung_OS/architecture/multi_tenancy.md` | Add glossary, correct session vars, JWT claims |
| Modify | `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md` | Verify §4.2 envelope + maturity rule |
| Read | `users/urls.py` | Verify legacy path count (14) |
| Read | `backend/urls.py` | Verify duplicate path count (14) |
| Read | `backend/auth_utils.py` | Verify SIMILAR_TO inventory (9) |
| Read | `backend/utils.py` | Verify SIMILAR_TO + dead code |
| Read | `llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md` | Verify 9-model inventory |

---

## Phase-Specific Tests

1. **Glossary cross-check:** Every legacy field in `multi_tenancy.md` glossary has a canonical replacement.
2. **Envelope consistency:** `endpoint_contract_spec.md` §4.2 matches the frozen shape exactly (field names, nesting, nullability).
3. **Path count:** `users/urls.py` has exactly 14 legacy paths + 5 keep paths. `backend/urls.py` has exactly 14 duplicates.
4. **Duplicate count:** Exactly 9 SIMILAR_TO functions identified. `resolve_access_levels` NOT in delete list.
5. **Model count:** Exactly 9 models in `postgresql_schema.md` §3.

---

## Completion Gate

- [ ] All spec files agree on scope vs active context semantics
- [ ] Login response envelope shape frozen and consistent across all docs
- [ ] Legacy path inventory verified against root URL graph (28 total: 14 per file)
- [ ] SIMILAR_TO duplicate inventory complete (9 functions)
- [ ] Phase 4 model inventory matches `postgresql_schema.md` §3 (9 models)
- [ ] `multi_tenancy.md` session variables aligned with target JWT claims
- [ ] Shared utility ownership documented
- [ ] Compatibility matrix published

---

## Notes for Next Phase

Phase 1 executes code changes against the contracts frozen in this phase. The executing agent must read `multi_tenancy.md` glossary and `endpoint_contract_spec.md` §4.2 before touching code.
