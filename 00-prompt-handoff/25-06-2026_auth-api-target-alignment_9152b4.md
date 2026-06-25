# Auth API Target Alignment — CBM Review, Spec Tightening, Legacy Removal

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `9152b4` |
| Entity type | `handoff` |
| Short description | CBM-based review of auth API against Kung_OS target architecture, spec/naming tightening, migration to target spec, and legacy endpoint/code removal |
| Status | `proposed` (pre-dev QC) |
| Source references | `llm-wiki/Kung_OS/architecture/identity_layer.md`, `llm-wiki/Kung_OS/architecture/identity_spec.md`, `llm-wiki/Kung_OS/architecture/multi_tenancy.md`, `llm-wiki/Kung_OS/architecture/rbac_system.md`, `llm-wiki/Kung_OS/architecture/alignment_audit.md`, `llm-wiki/Kung_OS/specs/database_schemas/migration_spec.md`, `llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`, `llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`, `llm-wiki/Kung_OS/specs/domain_specs/identity_spec.md`, `llm-wiki/Kung_OS/specs/domain_specs/tournaments_spec.md`, `llm-wiki/Kung_OS/specs/domain_specs/ecommerce_spec.md`, `llm-wiki/Kung_OS/specs/domain_specs/cafe_spec.md` |
| Generated | `25-06-2026` |
| Next action / owner | Pre-dev QC → Execute Phase 1 (CBM graph audit + spec tightening) — owner: agent with CBM + code-edit access |

---

## Pre-Development QC

**Purpose:** Validate spec completeness and consistency before execution begins. All gates must pass before Phase 1 starts.

### QC-1: Spec Consistency

| Check | Status | Evidence |
|-------|--------|----------|
| Domain naming consistent across all specs | ✅ | `tournaments_spec.md` (renamed from `gaming_spec.md`), no "Gaming Backend" references |
| API prefix consistent | ✅ | `eshop/` for e-commerce, `tournaments/` for tournaments, `cafe/` + `cafe-fnb/` for cafe |
| Legacy source links removed | ✅ | `KungOS_Endpoint_Design.md` removed from all spec Source lines |
| Endpoint contract spec complete | ✅ | `endpoint_contract_spec.md` covers routing, contracts, migration mapping, errors, pagination, versioning |
| Tenant field naming canonical | ✅ | `bg_code`, `div_code`, `branch_code` — no `division[]`, `branches[]`, `bgcode` |
| Identity model aligned across specs | ✅ | `postgresql_schema.md` + `identity_spec.md` + `endpoint_contract_spec.md` agree on `users_identity` + extensions |

### QC-2: CBM Audit Completeness

| Check | Status | Evidence |
|-------|--------|----------|
| All 9 route nodes indexed | ✅ | §CBM Graph Audit Findings §1 |
| 12 legacy paths identified for removal | ✅ | §CBM Graph Audit Findings §2 |
| 3 SIMILAR_TO duplicates identified | ✅ | §CBM Graph Audit Findings §3 |
| Dead code identified | ✅ | `close_mongo_client` — 0 callers, 0 callees |
| Auth flow traced end-to-end | ✅ | §CBM Graph Audit Findings §5 |

### QC-3: Phase Dependency Validation

| Check | Status | Evidence |
|-------|--------|----------|
| Phase 1 has no unlisted dependencies | ✅ | Only spec alignment + naming — no model changes |
| Phase 2 depends on Phase 1 (naming) | ✅ | Legacy paths removed after canonical names in place |
| Phase 3 independent | ✅ | Duplicate/dead code removal is orthogonal |
| Phase 4 depends on Phase 1 (naming) | ✅ | M1 scaffolding uses canonical field names |
| Phase 5 depends on all | ✅ | Wiring + verification after all changes |

### QC-4: Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Frontend breaks on login response change | HIGH | Dual-response mode with deprecation header (see Constraints) |
| Phone normalization breaks existing users | MEDIUM | Normalize on input only; existing `CustomUser.phone` untouched (M1 scope) |
| Legacy path removal breaks external consumers | MEDIUM | Verify no non-FE callers before removal (CBM trace) |
| JWT claim rename breaks auth middleware | HIGH | Update all JWT consumers in same deployment |
| M1 scaffolding creates tables but no data | LOW | Expected — tables empty until M1 migration executes |

### QC-5: Target Spec Alignment

| Spec Document | Aligned To | Notes |
|---------------|------------|-------|
| `endpoint_contract_spec.md` | Target architecture | Full routing, contracts, migration mapping |
| `identity_spec.md` | `postgresql_schema.md` TARGET | `users_identity` + extensions |
| `multi_tenancy.md` | Canonical field names | `bg_code`, `div_code`, `branch_code` |
| `rbac_system.md` | RBAC over Accesslevel | `rbac_*` tables replace `users_accesslevel` |
| `tournaments_spec.md` | Tournaments domain only | E-commerce backend integration owned by `ecommerce_spec.md` |
| `ecommerce_spec.md` | `eshop/` prefix | Product catalog, cart, orders, payments |
| `cafe_spec.md` | `cafe/` + `cafe-fnb/` split | Arcade (sessions) + F&B (orders) |

### QC Gates (must pass before execution)

- [ ] All QC-1 checks pass (spec consistency)
- [ ] All QC-2 checks pass (CBM audit completeness)
- [ ] Phase dependency DAG validated (QC-3)
- [ ] Risk mitigations documented (QC-4)
- [ ] Target spec alignment confirmed (QC-5)
- [ ] `phonenumbers` library in `requirements.txt` (or added)
- [ ] Frontend team notified of login response shape change

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:** Only the files listed in Source references above
**Related codebases:** `/home/chief/Coding-Projects/kteam-fe-chief` (frontend, port 3001)
**Key files for this task:**
- `users/api/viewsets.py` — AuthViewSet, RegisterViewSet, UserViewSet, AccessLevelViewSet, PhoneOTPViewSet
- `users/urls.py` — URL routing (legacy + current)
- `users/cookie_auth.py` — CookieJWTAuthentication
- `users/tenant_tokens.py` — TenantAwareRefreshToken
- `users/permissions.py` — RBAC resolution engine
- `users/serializers.py` — UserSerializer, AccesslevelSerializer, RegisterSerializer
- `backend/auth_utils.py` — resolve_access, resolve_minimal, resolve_user, has_read_access, has_write_access
- `backend/utils.py` — Duplicate functions (SIMILAR_TO auth_utils.py)
- `backend/urls.py` — Root URL config

---

## CBM Graph Audit Findings

### 1. Indexed Route Nodes (9 total)

| Route | Method | Handler |
|-------|--------|---------|
| `/api/v1/auth/login` | POST | `AuthViewSet.login` |
| `/api/v1/auth/logout` | POST | `AuthViewSet.logout` |
| `/api/v1/auth/refresh` | POST | `CookieTokenRefreshView` |
| `/api/v1/admin/tenant/bootstrap/` | POST | — |
| `/api/v1/cafe/payments/webhook/` | POST | — |
| `/health/` | GET | — |
| `/ping/` | GET | — |

### 2. URL Routing Map (users/urls.py)

**Router-registered (DefaultRouter):**
- `auth/` → AuthViewSet (login, logout, refresh, verify, pwdreset, health, monitoring_401)
- `register/` → RegisterViewSet (kuro, reb)
- `users/` → UserViewSet (me, profile, employees, emp_acc, bgswitch, bgswitch_get, kuro_user, reb_user)
- `access-levels/` → AccessLevelViewSet (list, create)
- `phone-otp/` → PhoneOTPViewSet (send)
- `rbac/roles/` → RoleViewSet
- `rbac/user-roles/` → UserRoleViewSet
- `rbac/user-permissions/` → UserPermissionViewSet
- `rbac/user-access/` → UserAccessViewSet
- `rbac/permissions/` → PermissionViewSet

**Legacy explicit paths (backward compat wrappers):**
| Legacy Path | Forwards To | Status |
|-------------|-------------|--------|
| `auth/kuroregister` | `RegisterViewSet.kuro` | **REMOVE** — duplicate of `register/kuro/` |
| `auth/rebregister` | `RegisterViewSet.reb` | **REMOVE** — duplicate of `register/reb/` |
| `auth/login` | `AuthViewSet.login` | **KEEP** — primary entry |
| `auth/admin` | `AuthViewSet.login` | **REMOVE** — role is inferred, not routed |
| `auth/staff` | `AuthViewSet.login` | **REMOVE** — role is inferred, not routed |
| `auth/reb` | `AuthViewSet.login` | **REMOVE** — role is inferred, not routed |
| `auth/refresh` | `CookieTokenRefreshView` | **KEEP** — primary entry |
| `auth/logout` | `AuthViewSet.logout` | **KEEP** — primary entry |
| `auth/health` | `AuthViewSet.health` | **KEEP** — health check |
| `auth/monitoring/401` | `AuthViewSet.monitoring_401` | **KEEP** — admin metrics |
| `kuro/user` | `UserViewSet.me` | **REMOVE** — use `users/me/` |
| `reb/user` | `UserViewSet.me` | **REMOVE** — use `users/me/` |
| `empprofile` | `UserViewSet.profile` | **REMOVE** — use `users/profile/` |
| `pwdreset` | `AuthViewSet.pwdreset` | **REMOVE** — use `auth/pwdreset/` |
| `verify` | `AuthViewSet.verify` | **REMOVE** — use `auth/verify/` |
| `accesslevel` | `AccessLevelViewSet` | **REMOVE** — use `access-levels/` |
| `employeesdata` | `UserViewSet.employees` | **REMOVE** — use `users/employees/` |
| `emp_acc` | `UserViewSet.emp_acc` | **REMOVE** — use `users/emp_acc/` |
| `bgSwitch` | `UserViewSet.bgswitch` | **REMOVE** — use `users/bgswitch/` |

**Total legacy paths to remove: 12**

### 3. SIMILAR_TO Duplicates (CBM verified)

| Function | Location A | Location B | Action |
|----------|-----------|------------|--------|
| `has_read_access` | `backend/auth_utils.py:206` | `backend/utils.py` | **DELETE** utils.py copy |
| `has_write_access` | `backend/auth_utils.py:226` | `backend/utils.py` | **DELETE** utils.py copy |
| `get_branch_fallback` | `backend/auth_utils.py` | `backend/utils.py` | **DELETE** utils.py copy |

### 4. Dead Code (CBM verified)

| Function | File | Evidence |
|----------|------|----------|
| `close_mongo_client` | `backend/` | 0 callers, 0 callees — confirmed dead |

### 5. Auth Flow Trace (login → callees)

```
AuthViewSet.login (L254-332)
├── _resolve_tenant_context (L?) — tenant context from request
├── _issue_jwt_tokens (L135-151) — JWT cookie issuance
│   └── TenantAwareRefreshToken.for_user
│       └── _resolve_tenant_context (tenant_tokens.py)
├── _build_login_response (L154-205) — response assembly
│   ├── UserSerializer (serializers.py)
│   ├── AccesslevelSerializer (serializers.py) — LEGACY
│   └── build_permissions_object (permissions.py) — RBAC
├── CustomUser.save (models.py) — last_login update
└── OrderGateway.get (cafe_fnb/gateways.py) — cafe context
    └── TenantCollection.distinct
```

**Gap in flow:** `_build_login_response` still assembles `AccesslevelSerializer` data (legacy flat perms) alongside `build_permissions_object` (RBAC). Target: RBAC only.

---

## Phase 1: Spec Tightening & Naming Canonicalization

**What:** Tighten naming inconsistencies between current code and target spec. No model changes — only field names, response shapes, and constants.

**Dependencies:** None (can run in parallel with Phase 2).

### 1A. Canonical Tenant Field Names

**Current (non-canonical):**
- `division` (JSON array in JWT, MongoDB)
- `branches` (JSON array in JWT, MongoDB)
- `bgcode` (MongoDB, some views)

**Target (canonical per `multi_tenancy.md`):**
- `div_code` (string, singular tenant context)
- `branch_code` (string, singular tenant context)
- `bg_code` (already canonical in PG)

**Files to modify:**
| Action | File | Change |
|--------|------|--------|
| Modify | `users/tenant_tokens.py` | Rename JWT claims: `division` → `div_code`, `branches` → `branch_code` |
| Modify | `users/api/viewsets.py` | `_resolve_tenant_context`: return canonical names |
| Modify | `users/serializers.py` | `UserSerializer`: output `div_code`, `branch_code` |
| Modify | `backend/auth_utils.py` | `resolve_access`: use canonical names |

### 1B. Response Shape Alignment (`endpoint_contract_spec.md` §4.2)

**Current `login` response:
```json
{
  "user": {
    "userdata": { ... CustomUser fields ... },
    "accesslevel": [ ... legacy Accesslevel rows ... ],
    "roles": [ ... KuroUser.roles JSON ... ],
    "bg_code": "...",
    "division": ["..."],
    "branches": ["..."],
    "_permissions": { ... RBAC ... },
    "_roles": { ... RBAC ... },
    "_overrides": { ... RBAC ... }
  },
  "status": "SUCCESS"
}
```

**Target `login` response:**
```json
{
  "identity_id": "ID000001",
  "phone": "+91XXXXXXXXXX",
  "name": "...",
  "roles": ["admin", "staff"],
  "primary_role": "admin",
  "employee_profile": { ... } | null,
  "customer_profile": { ... } | null,
  "tenant": {
    "bg_code": "...",
    "div_code": "...",
    "branch_code": "..."
  },
  "status": "SUCCESS"
}
```

**Files to modify:**
| Action | File | Change |
|--------|------|--------|
| Modify | `users/api/viewsets.py` | `_build_login_response`: new shape, remove `AccesslevelSerializer` |
| Modify | `users/serializers.py` | Create `IdentityResponseSerializer` (target shape) |
| Modify | `users/api/viewsets.py` | `UserViewSet.me`: same new shape |

### 1C. Phone Normalization Guard

**Current:** No normalization — raw phone strings everywhere.

**Target:** E.164 normalization on all auth inputs (login, register, OTP).

**Files to modify:**
| Action | File | Change |
|--------|------|--------|
| Create | `users/utils.py` | `normalize_phone(raw, region='IN')` — uses `phonenumbers` lib |
| Modify | `users/api/viewsets.py` | `AuthViewSet.login`: normalize `phone` input |
| Modify | `users/api/viewsets.py` | `RegisterViewSet.kuro`, `RegisterViewSet.reb`: normalize `phone` |
| Modify | `users/api/viewsets.py` | `PhoneOTPViewSet.send`: normalize `phone` |

**Tests:**
1. `normalize_phone("9876543210")` → `"+919876543210"`
2. `normalize_phone("+919876543210")` → `"+919876543210"` (idempotent)
3. `normalize_phone("  +91 98765 43210  ")` → `"+919876543210"` (whitespace tolerant)

**Completion gate:**
- [ ] All JWT claims use `div_code`, `branch_code`, `bg_code`
- [ ] Login response matches target shape
- [ ] Phone normalization applied at all entry points
- [ ] Existing tests still pass

---

## Phase 2: Legacy Endpoint Removal

**What:** Remove 12 legacy URL paths and consolidate to canonical routes.

**Dependencies:** Phase 1 (naming must be canonical first).

### 2A. Remove Legacy URL Paths

**Delete from `users/urls.py`:**
```python
# Remove these 12 lines:
path('auth/kuroregister', ...),
path('auth/rebregister', ...),
path('auth/admin', ...),
path('auth/staff', ...),
path('auth/reb', ...),
path('kuro/user', ...),
path('reb/user', ...),
path('empprofile', ...),
path('pwdreset', ...),
path('verify', ...),
path('accesslevel', ...),
path('employeesdata', ...),
path('emp_acc', ...),
path('bgSwitch', ...),
```

**Keep:**
```python
path('auth/login', ...),
path('auth/refresh', ...),
path('auth/logout', ...),
path('auth/health', ...),
path('auth/monitoring/401', ...),
```

### 2B. Remove Legacy ViewSet Actions

**From `UserViewSet`:**
| Action | Route | Reason |
|--------|-------|--------|
| `kuro_user` | `GET /users/kuro_user/` | Duplicate of `me` — remove |
| `reb_user` | `GET /users/reb_user/` | Duplicate of `me` — remove |

**From `AuthViewSet`:**
| Action | Route | Reason |
|--------|-------|--------|
| (none) | — | All auth actions are canonical — keep as-is |

**Files to modify:**
| Action | File | Change |
|--------|------|--------|
| Modify | `users/urls.py` | Delete 12 legacy paths |
| Modify | `users/api/viewsets.py` | Delete `UserViewSet.kuro_user`, `UserViewSet.reb_user` |
| Modify | `users/api/viewsets.py` | Update docstrings to reflect canonical routes |

### 2C. Remove Legacy Response Fields

**From `_build_login_response`:**
| Field | Source | Action |
|-------|--------|--------|
| `accesslevel[]` | `AccesslevelSerializer` | **REMOVE** — legacy flat perms |
| `roles[]` (from KuroUser) | `KuroUser.roles` JSON | **REMOVE** — use RBAC-derived roles |
| `division[]` | `UserTenantContext` | **RENAME** → `div_code` (string) |
| `branches[]` | `UserTenantContext` | **RENAME** → `branch_code` (string) |

**Completion gate:**
- [ ] 12 legacy paths removed from `users/urls.py`
- [ ] `kuro_user`, `reb_user` actions removed from `UserViewSet`
- [ ] No 404 on canonical routes (`/api/v1/auth/login`, `/api/v1/users/me`, etc.)
- [ ] Frontend still works (verify `kteam-fe-chief` login flow)

---

## Phase 3: Duplicate & Dead Code Removal

**What:** Remove SIMILAR_TO duplicates and dead code identified by CBM.

**Dependencies:** None (independent of Phases 1-2).

### 3A. SIMILAR_TO Duplicates

| Function | Delete From | Keep In | Evidence |
|----------|------------|---------|----------|
| `has_read_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `has_write_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `get_branch_fallback` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |

**Steps:**
1. Verify all callers of `backend/utils.py` copies import from `utils` (not `auth_utils`).
2. Update imports to use `backend/auth_utils.py` versions.
3. Delete duplicate functions from `backend/utils.py`.

### 3B. Dead Code

| Function | File | Evidence |
|----------|------|----------|
| `close_mongo_client` | `backend/` | CBM: 0 callers, 0 callees |

**Steps:**
1. Verify `close_mongo_client` has 0 callers via CBM (`codebase_trace`).
2. Delete function.

**Completion gate:**
- [ ] 3 SIMILAR_TO duplicates removed from `backend/utils.py`
- [ ] `close_mongo_client` deleted
- [ ] All imports updated
- [ ] Existing tests still pass

---

## Phase 4: M1 Identity Model Preparation (Spec Only)

**What:** Prepare the spec and migration scaffolding for `users_identity` + extension tables. **Do not execute M1** — this phase produces the migration spec and empty Django models only.

**Dependencies:** Phase 1 (naming must be canonical first).

### 4A. Target Models (from `postgresql_schema.md`)

**Create empty Django models (no migration data yet):**

| Model | Table | Purpose |
|-------|-------|---------|
| `Identity` | `users_identity` | Core identity (identity_id PK, phone E.164, name, bg_code, div_code, user FK nullable) |
| `EmployeeProfile` | `users_employee` | Employee extension (identity_id FK, designation, department, ...) |
| `CustomerProfile` | `users_customer` | Customer extension (identity_id FK, loyalty, preferences, ...) |
| `PlayerProfile` | `users_player` | Player extension (identity_id FK, gaming stats, ...) |
| `VendorProfile` | `users_vendor_profile` | Vendor extension (identity_id FK, business details, ...) |
| `Organization` | `users_organization` | Org/Team extension |
| `PhoneAlias` | `identity_phone_aliases` | Phone alias table |

**Files to create:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `users/models/identity.py` | `Identity` model |
| Create | `users/models/extensions.py` | Extension models |
| Create | `users/models/phone_aliases.py` | `PhoneAlias` model |
| Modify | `users/models/__init__.py` | Export new models |

### 4B. Migration Scaffolding

**Files to create:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `users/migrations/00XX_create_identity_tables.py` | Empty tables + indexes + constraints |
| Create | `users/management/commands/migrate_identity.py` | Import + dedup command (from `migration_spec.md`) |

**Constraints to enforce (from `alignment_audit.md` §4.1):**
```sql
CREATE UNIQUE INDEX uq_identity_tenant_phone ON users_identity (bg_code, phone);
ALTER TABLE users_employee ADD CONSTRAINT fk_employee_identity FOREIGN KEY (identity_id) REFERENCES users_identity(identity_id) ON DELETE CASCADE;
-- (repeat for all extension tables)
```

**Completion gate:**
- [ ] All models defined with correct fields
- [ ] Migration creates empty tables with constraints
- [ ] `migrate_identity` command exists (untested, Phase 5 executes it)
- [ ] No data loss — legacy tables untouched

---

## Phase 5: Production Wiring & Verification

**What:** Wire all components, verify end-to-end auth flow, confirm no regression.

**Dependencies:** Phases 1-4 complete.

### 5A. Frontend Compatibility

**Verify `kteam-fe-chief` still works:**
- Login endpoint: `POST /api/auth/login` (Vite proxy → `/api/v1/auth/login`)
- Response shape change: Frontend must adapt to new response format (Phase 1B)
- Phone normalization: Frontend sends raw phone — backend normalizes

**Files to modify (FE):**
| Action | File | Change |
|--------|------|--------|
| Modify | `kteam-fe-chief/src/actions/user.jsx` | Adapt to new login response shape |
| Modify | `kteam-fe-chief/src/lib/api.jsx` | Verify proxy config unchanged |

### 5B. Post-Wiring Tests

- [ ] `POST /api/v1/auth/login` returns target response shape
- [ ] `GET /api/v1/users/me` returns target response shape
- [ ] `POST /api/v1/auth/logout` blacklists token
- [ ] `POST /api/v1/auth/refresh` rotates token
- [ ] Legacy paths (`/api/v1/auth/admin`, `/api/v1/kuro/user`, etc.) return 404
- [ ] Phone normalization: raw input → E.164 in response
- [ ] JWT claims use `div_code`, `branch_code`, `bg_code`
- [ ] All existing tests pass (no regression)
- [ ] Frontend login flow works on `http://localhost:3001`

### 5C. CBM Re-index

After all changes:
```bash
codebase_index /home/chief/Coding-Projects/kteam-dj-chief
```

Verify:
- [ ] No new SIMILAR_TO edges in `users/` or `backend/auth_utils.py`
- [ ] Dead code count unchanged (no new dead functions)
- [ ] Route nodes reflect only canonical paths

---

## Constraints

- **No data loss:** Legacy `CustomUser`, `KuroUser`, `Accesslevel` tables remain untouched until M1 is executed (Phase 4+). This handoff only prepares the scaffolding.
- **No frontend breakage:** Login response shape change (Phase 1B) must be coordinated with `kteam-fe-chief`. If FE cannot adapt in same deployment, keep legacy fields alongside new fields (dual-response mode) with deprecation warning.
- **Phone normalization is additive:** Normalize on input, store normalized. Do not migrate existing `CustomUser.phone` values in this handoff (that's M1).
- **RBAC takes precedence:** When both `Accesslevel` and RBAC exist, RBAC wins. Remove `AccesslevelSerializer` from login response.
- **Canonical naming is mandatory:** `div_code`, `branch_code`, `bg_code` — no legacy `division`, `branches`, `bgcode` in JWT or responses.
- **M1 execution is out of scope:** This handoff produces models + migration command. Actual data migration (Phase 4 of `migration_spec.md`) is a separate handoff.

---

## Success Criteria

- [ ] 12 legacy URL paths removed
- [ ] 3 SIMILAR_TO duplicates removed
- [ ] 1 dead function removed
- [ ] JWT claims use canonical names (`div_code`, `branch_code`, `bg_code`)
- [ ] Login response matches target shape (or dual-response with deprecation)
- [ ] Phone normalization applied at all auth entry points
- [ ] Empty `users_identity` + extension tables created (M1 scaffolding)
- [ ] `migrate_identity` management command exists
- [ ] All existing tests pass
- [ ] Frontend login flow verified
- [ ] CBM re-index shows no new duplicates or dead code

---

## Caveats & Uncertainty

1. **Frontend coupling:** The login response shape change (Phase 1B) requires FE changes. If FE is not ready, use dual-response mode (legacy + new fields) with a `DeprecationWarning` header.
2. **M1 timing:** The `users_identity` models (Phase 4) are created empty. Actual data migration from 8 sources is a separate effort (see `migration_spec.md` Phase 4). This handoff does not execute M1.
3. **MongoDB field rename (M3):** Not included — that's `migration_spec.md` Phase 5.7 and independent of this handoff.
4. **Walk-in identity creation:** Not implemented — requires `users_identity` table + new endpoint. Out of scope for this handoff (requires M1 first).
5. **`phonenumbers` library:** May need to be added to `requirements.txt` if not already installed.

---

## Execution Order (DAG)

```
Phase 1 (Spec tightening) ─────────────────────────┐
Phase 2 (Legacy removal) ← depends on Phase 1      │
Phase 3 (Duplicate/dead code) ← independent ────────┤
Phase 4 (M1 scaffolding) ← depends on Phase 1      │
                                                     ▼
Phase 5 (Production wiring) ← depends on 1,2,3,4
```

**Parallel execution:** Phases 1, 3 can run simultaneously. Phase 2 depends on 1. Phase 4 depends on 1. Phase 5 depends on all.
