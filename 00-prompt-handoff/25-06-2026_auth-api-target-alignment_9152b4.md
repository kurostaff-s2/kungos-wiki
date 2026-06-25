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

### QC-0: Architectural Alignment Invariants

| Invariant | Canonical Definition | Enforced By |
|-----------|---------------------|-------------|
| **Tenant scope vs active context** | Authorization scope = plural arrays (`div_codes[]`, `branch_codes[]`). Active request context = singular (`div_code`, `branch_code`). | `multi_tenancy.md` + middleware |
| **Identity singular** | `identity_id` is the stable PK. Auth (CustomUser) is linked but not equivalent. Roles from extensions + RBAC. | `identity_spec.md` |
| **Response envelope** | All external APIs return `{status, data, meta}` envelope per `endpoint_contract_spec.md` §3.1. | Serializer base class |
| **Domain-first routing** | URLs begin with domain namespace. Shared primitives (identity, tenant, RBAC) not redefined per domain. | URL conf structure |
| **Canonical tenant names** | `bg_code`, `active_div_code`, `active_branch_code` — no legacy `division`, `branches`, `bgcode` in JWT or responses. | JWT claims + middleware |
| **Extension payloads nullable** | `employee_profile`, `customer_profile`, etc. are null/absent until M1 data backfill completes. | Target contract + maturity rule |

### QC-1: Spec Consistency

| Check | Status | Evidence |
|-------|--------|----------|
| Domain naming consistent across all specs | ✅ | `tournaments_spec.md` (renamed from `gaming_spec.md`), no "Gaming Backend" references |
| API prefix consistent | ✅ | `eshop/` for e-commerce, `tournaments/` for tournaments, `cafe/` + `cafe-fnb/` for cafe |
| Legacy source links removed | ✅ | `KungOS_Endpoint_Design.md` removed from all spec Source lines |
| Endpoint contract spec complete | ✅ | `endpoint_contract_spec.md` covers routing, contracts, migration mapping, errors, pagination, versioning |
| Tenant field naming canonical | ⚠️ Partial | Target = `div_code`/`branch_code` (singular string). Current `UserTenantContext` = `division`/`branches` (JSON arrays). **Resolution:** authorization scope stays plural (`div_codes[]`/`branch_codes[]`), active context is singular. Documented in QC-0. |
| Identity model aligned across specs | ⚠️ Partial | `postgresql_schema.md` + `identity_spec.md` agree on `users_identity` + extensions. Phase 4 model inventory missing `users_team_profile`, `team_memberships`, `users_organization`. **Resolution:** expanded in Phase 0. |

### QC-2: CBM Audit Completeness (CORRECTED)

| Check | Status | Evidence |
|-------|--------|----------|
| Route nodes indexed | ⚠️ Incomplete | §CBM Graph Audit Findings §1 only listed health/ping routes. Missed all domain routes in `backend/urls.py`: `accounts/`, `vendors/`, `orders/`, `products/`, `eshop/`, `teams/`, `search/`, `shared/`, `careers/`, `tournaments/`, `cafe/`, `cafe-fnb/`, `admin/`, `tenant/`. **Resolution:** legacy path inventory measured against root routing graph, not one module. |
| Legacy paths identified for removal | ✅ Corrected | **14 paths in `users/urls.py`** (not 12). Plus **14 duplicate legacy paths in `backend/urls.py`** that must also be removed. Full inventory in Phase 2A. |
| SIMILAR_TO duplicates identified | ✅ Corrected | **9 total duplicates** (not 3): `has_read_access`, `has_write_access`, `get_branch_fallback` (original 3) + `get_accessible_divisions`, `get_all_divisions`, `has_division_write_access`, `check_access`, `check_write_access`, `check_division_write_access` (6 more in `backend/utils.py`). `resolve_access_levels` is **unique to utils.py** — must NOT be deleted. |
| Dead code identified | ✅ | `close_mongo_client` — 0 callers, 0 callees |
| Auth flow traced end-to-end | ⚠️ Fragile | Line numbers (L254-332) are stale-prone. `OrderGateway.get` reference not in actual login method. **Resolution:** trace by function name, not line numbers. |

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

### QC-5: Target Spec Alignment (CORRECTED)

| Spec Document | Aligned To | Status | Notes |
|---------------|------------|--------|-------|
| `endpoint_contract_spec.md` | Target architecture | ✅ | Full routing, contracts, migration mapping |
| `identity_spec.md` | `postgresql_schema.md` TARGET | ✅ | `users_identity` + extensions |
| `multi_tenancy.md` | Canonical field names | ⚠️ | Session variables reference stale `entity[0]`/`branches[0]` — fixed in this alignment |
| `rbac_system.md` | RBAC over Accesslevel | ✅ | `rbac_*` tables replace `users_accesslevel` |
| `tournaments_spec.md` | Tournaments domain only | ✅ | E-commerce backend integration owned by `ecommerce_spec.md` |
| `ecommerce_spec.md` | `eshop/` prefix | ✅ | Product catalog, cart, orders, payments |
| `cafe_spec.md` | `cafe/` + `cafe-fnb/` split | ✅ | Arcade (sessions) + F&B (orders) |

**Normative precedence (when docs conflict):**
1. `endpoint_contract_spec.md` — wire contracts (response shapes, routes, envelopes)
2. `postgresql_schema.md` — physical storage (table names, columns, constraints)
3. `multi_tenancy.md` — tenant semantics (scope, middleware, session context)
4. `identity_spec.md` — person modeling (identity, extensions, lookup)
5. `migration_spec.md` — timing and rollout ordering

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

## Phase 0: Architectural Alignment & Contract Freeze

**What:** Resolve cross-spec inconsistencies before any code changes. No code modifications — only documentation alignment and contract definitions.

**Dependencies:** None.

**Completion gates:**
- [ ] All spec files agree on canonical tenant field semantics (scope vs active context)
- [ ] Login response envelope shape frozen in `endpoint_contract_spec.md`
- [ ] Legacy path inventory verified against root URL graph (both `users/urls.py` AND `backend/urls.py`)
- [ ] SIMILAR_TO duplicate inventory complete (9 functions, not 3)
- [ ] Phase 4 model inventory matches `postgresql_schema.md` §3 completely
- [ ] `multi_tenancy.md` session variables aligned with target JWT claims
- [ ] Shared utility ownership documented

### 0A. Tenant Semantics: Scope vs Active Context

**Problem:** `UserTenantContext` stores `division` (JSON array) and `branches` (JSON array). Target spec says `div_code` (string) and `branch_code` (string). This is not a rename — it's a cardinality mismatch.

**Resolution:** Formal two-layer model:

| Layer | Fields | Storage | Source |
|-------|--------|---------|--------|
| **Authorization scope** | `div_codes[]`, `branch_codes[]` | `UserTenantContext.division` (JSONB), `UserTenantContext.branches` (JSONB) | All divisions/branches user can access |
| **Active tenant context** | `active_div_code` (singular), `active_branch_code` (singular) | Request-level (`request.active_div_code`) | Derived from scope + tenant switch or default |

**JWT claims (target):**
- `bg_code` — string (single BG from active context)
- `div_codes` — array (authorization scope: all accessible divisions)
- `branch_codes` — array (authorization scope: all accessible branches)
- `active_div_code` — string (current active division)
- `active_branch_code` — string or null (current active branch)

**Middleware (`multi_tenancy.md` session variables, corrected):**

| Variable | Source | Purpose |
|----------|--------|--------|
| `app.current_bg_code` | JWT `bg_code` | Tenant scope (required) |
| `app.current_division` | JWT `active_div_code` | Active division scope |
| `app.current_branch` | JWT `active_branch_code` | Active branch scope |
| `app.current_userid` | JWT `identity_id` (or `userid` legacy) | User identity |

**Field mapping table (legacy → canonical):**

| Legacy Field/Claim | Canonical Field | Context |
|-------------------|-----------------|---------|
| `division` (JSON array) | `div_codes[]` (scope) / `active_div_code` (active) | JWT + UserTenantContext |
| `branches` (JSON array) | `branch_codes[]` (scope) / `active_branch_code` (active) | JWT + UserTenantContext |
| `entity[0]` | `active_div_code` | JWT (stale — removed) |
| `bgcode` | `bg_code` | MongoDB documents |
| `branch` | `branch_code` | MongoDB documents |

### 0B. Response Envelope Freeze

**Problem:** Handoff spec §1B shows flat login response. `endpoint_contract_spec.md` §4.2 shows envelope-wrapped response. Two different shapes.

**Resolution:** `endpoint_contract_spec.md` §3.1 envelope is authoritative. Login response:

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

**Maturity rule:** `employee_profile`, `customer_profile`, `player_profile` are **nullable until M1 data backfill completes**. Fields absent or null — not missing from contract.

### 0C. Legacy Path Inventory (Corrected)

**`users/urls.py` — 14 paths to REMOVE (was incorrectly counted as 12):**

| Legacy Path | Forwards To | REMOVE |
|-------------|-------------|--------|
| `auth/kuroregister` | `register/kuro/` | ✅ |
| `auth/rebregister` | `register/reb/` | ✅ |
| `auth/admin` | `auth/login` (role inferred) | ✅ |
| `auth/staff` | `auth/login` (role inferred) | ✅ |
| `auth/reb` | `auth/login` (role inferred) | ✅ |
| `kuro/user` | `users/me/` | ✅ |
| `reb/user` | `users/me/` | ✅ |
| `empprofile` | `users/profile/` | ✅ |
| `pwdreset` | `auth/pwdreset/` (router-generated) | ✅ |
| `verify` | `auth/verify/` (router-generated) | ✅ |
| `accesslevel` | `access-levels/` | ✅ |
| `employeesdata` | `users/employees/` | ✅ |
| `emp_acc` | `users/emp_acc/` | ✅ |
| `bgSwitch` | `users/bgswitch/` | ✅ |

**`users/urls.py` — 5 paths to KEEP:**

| Path | Reason |
|------|--------|
| `auth/login` | Primary login entry |
| `auth/refresh` | Primary refresh entry |
| `auth/logout` | Primary logout entry |
| `auth/health` | Health check |
| `auth/monitoring/401` | Admin metrics |

**`backend/urls.py` — 14 duplicate legacy paths to REMOVE:**

| Legacy Path | Also In | REMOVE |
|-------------|---------|--------|
| `api/v1/bgSwitch` | `users/urls.py` | ✅ |
| `api/v1/accesslevel` | `users/urls.py` | ✅ |
| `api/v1/pwdreset` | `users/urls.py` + router | ✅ |
| `api/v1/verify` | `users/urls.py` + router | ✅ |
| `api/v1/empprofile` | `users/urls.py` | ✅ |
| `api/v1/employeesdata` | `users/urls.py` | ✅ |
| `api/v1/kuro/user` | `users/urls.py` | ✅ |
| `api/v1/reb/user` | `users/urls.py` | ✅ |
| `api/v1/emp_acc` | `users/urls.py` | ✅ |
| `api/v1/auth/login` | `users/urls.py` + router | ✅ — keep only router-generated |
| `api/v1/auth/kuroregister` | `users/urls.py` | ✅ |
| `api/v1/auth/rebregister` | `users/urls.py` | ✅ |
| `api/v1/auth/refresh` | `users/urls.py` + `CookieTokenRefreshView` | ✅ — keep only `users/urls.py` copy |
| `api/v1/auth/logout` | `users/urls.py` | ✅ — keep only `users/urls.py` copy |

**pwdreset/verify clarification:** These exist as `@action` on `AuthViewSet` → DefaultRouter generates `/auth/pwdreset/` and `/auth/verify/` automatically. The bare paths (`pwdreset`, `verify`) in both `users/urls.py` AND `backend/urls.py` are legacy aliases — remove both. The router-generated canonical paths survive.

**auth/login/refresh/logout clarification:** Three copies exist (router, `users/urls.py`, `backend/urls.py`). After cleanup: keep `users/urls.py` explicit paths for login/logout/refresh. Remove `backend/urls.py` duplicates. Router-generated duplicates for `pwdreset`/`verify` are canonical.

### 0D. SIMILAR_TO Duplicate Inventory (Corrected)

**9 total duplicates across `backend/auth_utils.py` and `backend/utils.py`:**

| Function | auth_utils.py | utils.py | Action |
|----------|--------------|----------|--------|
| `has_read_access` | ✅ | ✅ | DELETE utils.py copy |
| `has_write_access` | ✅ | ✅ | DELETE utils.py copy |
| `get_branch_fallback` | ✅ | ✅ | DELETE utils.py copy |
| `get_accessible_divisions` | ✅ | ✅ | DELETE utils.py copy |
| `get_all_divisions` | ✅ | ✅ | DELETE utils.py copy |
| `has_division_write_access` | ✅ | ✅ | DELETE utils.py copy |
| `check_access` | ✅ | ✅ | DELETE utils.py copy |
| `check_write_access` | ✅ | ✅ | DELETE utils.py copy |
| `check_division_write_access` | ✅ | ✅ | DELETE utils.py copy |

**Functions unique to `backend/utils.py` (DO NOT DELETE):**

| Function | Used By | Keep |
|----------|---------|------|
| `resolve_access_levels` | `backend/auth_utils.py` (imported at L109) | ✅ Canonical caller |
| `get_mongo_client` | MongoDB access | ✅ Singleton |
| `close_mongo_client` | — | ❌ Dead (0 callers) |
| `find_all`, `find_one`, etc. | MongoDB helpers | ✅ But fix param name inconsistency (see 0F) |

### 0E. Shared Utility Ownership

| Module | Owns | Delete After |
|--------|------|-------------|
| `backend/auth_utils.py` | Access resolution: `resolve_access`, `resolve_minimal`, `resolve_user`, `has_*_access`, `check_*`, `get_*_divisions` | — |
| `backend/utils.py` | MongoDB helpers: `get_mongo_client`, `find_*`, `count_*`, `aggregate`, `update_*`, `insert_*`, `delete_*` + `resolve_access_levels` | — |
| `plat/tenant/` | Tenant isolation: `TenantCollection`, RLS, schema validation | — |
| `users/permissions.py` | RBAC resolution: `resolve_permission` | — |

**MongoDB helper param name inconsistency (fix in Phase 3):**
- `find_all` accepts `div_code`/`branch_code` (canonical) ✅
- `find_one`, `count_documents`, `aggregate`, `update_many`, `insert_one`, `delete_many` accept `division`/`branch` (legacy) ❌
- **Fix:** All helpers accept canonical names first. Legacy aliases in a single compatibility shim.

### 0F. Compatibility Matrix

| Legacy Field/Path | Canonical Replacement | Adapter Behavior | Removal Milestone |
|------------------|----------------------|------------------|-------------------|
| `division` (JSON array) | `div_codes[]` (scope) + `active_div_code` (active) | Dual-read middleware | Phase 0 complete |
| `branches` (JSON array) | `branch_codes[]` (scope) + `active_branch_code` (active) | Dual-read middleware | Phase 0 complete |
| `bgcode` (MongoDB) | `bg_code` | Dual-read middleware | M3 (Phase 5.7) |
| `branch` (MongoDB) | `branch_code` | Dual-read middleware | M3 (Phase 5.7) |
| `entity[0]` (JWT) | `active_div_code` | Removed from JWT | Phase 0 complete |
| `userid` (PK) | `identity_id` | FK linkage via `user` field | M1 (Phase 4) |
| `accesslevel[]` (flat perms) | `permissions[]` (RBAC perm_codes) | `AccesslevelSerializer` removed | Phase 2 |
| `division` (Accesslevel model) | `div_code` | `.values(div_code=F('division'))` adapter | Phase 2 |
| Legacy URL paths (14+14) | Canonical routes | 404 after removal | Phase 2 |

---

## Phase 1: Spec Tightening & Naming Canonicalization

**What:** Tighten naming inconsistencies between current code and target spec. No model changes — only field names, response shapes, and constants.

**Dependencies:** None (can run in parallel with Phase 2).

### 1A. Canonical Tenant Field Names

**See Phase 0A for the scope vs active context resolution.**

**Current (non-canonical):**
- `division` (JSON array in JWT, MongoDB, `UserTenantContext`)
- `branches` (JSON array in JWT, MongoDB, `UserTenantContext`)
- `bgcode` (MongoDB, some views)
- `entity[0]` (JWT — stale, no such field in target)

**Target (two-layer model, per Phase 0A):**

| Layer | Field | Type | Source |
|-------|-------|------|--------|
| Authorization scope | `div_codes[]` | array | `UserTenantContext.division` (JSONB) |
| Authorization scope | `branch_codes[]` | array | `UserTenantContext.branches` (JSONB) |
| Active context | `active_div_code` | string | Derived from scope + switch |
| Active context | `active_branch_code` | string/null | Derived from scope + switch |
| Active context | `bg_code` | string | JWT / middleware |

**Note:** `UserTenantContext.division` and `UserTenantContext.branches` remain JSONB arrays (authorization scope). The singular `active_div_code`/`active_branch_code` in the target refers to the **active request context**, not the stored scope. No model rename needed — just documentation alignment.

**Files to modify:**
| Action | File | Change |
|--------|------|--------|
| Modify | `users/tenant_tokens.py` | JWT claims: `division` → `div_codes`, `branches` → `branch_codes`, add `active_div_code`, `active_branch_code`. Remove `entity`. |
| Modify | `users/api/viewsets.py` | `_resolve_tenant_context`: return canonical names (scope arrays + active singular) |
| Modify | `users/serializers.py` | `UserSerializer`: output `div_code` (active), `branch_code` (active), `div_codes[]` (scope) |
| Modify | `backend/auth_utils.py` | `resolve_access`: use canonical names |
| Modify | `backend/utils.py` | MongoDB helpers: accept canonical param names (`div_code`/`branch_code`) consistently |

### 1B. Response Shape Alignment (`endpoint_contract_spec.md` §4.2)

**See Phase 0B for the envelope freeze.**

**Current `login` response:**
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

**Target `login` response (envelope-wrapped, per `endpoint_contract_spec.md` §3.1):**
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

**Maturity rule:** `employee_profile`, `customer_profile`, `player_profile` are **nullable/absent until M1 data backfill completes**. The contract defines the shape; data availability follows migration timing. Do not fabricate empty objects — return `null` or omit.

**CookieTokenRefreshView duplication (Issue #13):** `CookieTokenRefreshView` exists as both a standalone `APIView` (L620 `viewsets.py`) AND as `AuthViewSet.refresh` @action (L361). **Action:** Consolidate to `AuthViewSet.refresh` only. Remove standalone `CookieTokenRefreshView` or redirect it to the viewset action.

**Files to modify:**
| Action | File | Change |
|--------|------|--------|
| Modify | `users/api/viewsets.py` | `_build_login_response`: envelope-wrapped shape per §0B, remove `AccesslevelSerializer` |
| Modify | `users/serializers.py` | Create `IdentityResponseSerializer` (target shape) |
| Modify | `users/api/viewsets.py` | `UserViewSet.me`: same envelope-wrapped shape |
| Modify | `users/api/viewsets.py` | Consolidate `CookieTokenRefreshView` → `AuthViewSet.refresh` |

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
- [ ] All JWT claims use `active_div_code`, `active_branch_code`, `bg_code`
- [ ] Login response matches target shape
- [ ] Phone normalization applied at all entry points
- [ ] Existing tests still pass

---

## Phase 2: Legacy Endpoint Removal

**What:** Remove 12 legacy URL paths and consolidate to canonical routes.

**Dependencies:** Phase 1 (naming must be canonical first).

### 2A. Remove Legacy URL Paths

**Delete from `users/urls.py` (14 paths):**
```python
# Remove these 14 lines:
path('auth/kuroregister', ...),
path('auth/rebregister', ...),
path('auth/admin', ...),
path('auth/staff', ...),
path('auth/reb', ...),
path('kuro/user', ...),
path('reb/user', ...),
path('empprofile', ...),
path('pwdreset', ...),       # router-generated /auth/pwdreset/ survives
path('verify', ...),         # router-generated /auth/verify/ survives
path('accesslevel', ...),
path('employeesdata', ...),
path('emp_acc', ...),
path('bgSwitch', ...),
```

**Delete from `backend/urls.py` (14 duplicate legacy paths):**
```python
# Remove these 14 lines (duplicates of users/urls.py paths):
path('api/v1/bgSwitch', ...),
path('api/v1/accesslevel', ...),
path('api/v1/pwdreset', ...),
path('api/v1/verify', ...),
path('api/v1/empprofile', ...),
path('api/v1/employeesdata', ...),
path('api/v1/kuro/user', ...),
path('api/v1/reb/user', ...),
path('api/v1/emp_acc', ...),
path('api/v1/auth/login', ...),      # keep only users/urls.py copy
path('api/v1/auth/kuroregister', ...),
path('api/v1/auth/rebregister', ...),
path('api/v1/auth/refresh', ...),     # keep only users/urls.py copy
path('api/v1/auth/logout', ...),      # keep only users/urls.py copy
```

**Keep in `users/urls.py`:**
```python
path('auth/login', ...),
path('auth/refresh', ...),
path('auth/logout', ...),
path('auth/health', ...),
path('auth/monitoring/401', ...),
```

**pwdreset/verify note:** These are `@action` on `AuthViewSet` → DefaultRouter generates `/auth/pwdreset/` and `/auth/verify/` automatically. The bare explicit `path()` entries in both files are legacy aliases — remove both. The router-generated canonical paths survive.

**Total legacy paths removed: 28** (14 from `users/urls.py` + 14 from `backend/urls.py`).

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
| Modify | `users/urls.py` | Delete 14 legacy paths |
| Modify | `users/api/viewsets.py` | Delete `UserViewSet.kuro_user`, `UserViewSet.reb_user` |
| Modify | `users/api/viewsets.py` | Update docstrings to reflect canonical routes |

### 2C. Remove Legacy Response Fields

**From `_build_login_response`:**
| Field | Source | Action |
|-------|--------|--------|
| `accesslevel[]` | `AccesslevelSerializer` | **REMOVE** — legacy flat perms |
| `roles[]` (from KuroUser) | `KuroUser.roles` JSON | **REMOVE** — use RBAC-derived roles |
| `division[]` | `UserTenantContext` | **RENAME** → `active_div_code` (string) |
| `branches[]` | `UserTenantContext` | **RENAME** → `active_branch_code` (string) |

**Completion gate:**
- [ ] 14 legacy paths removed from `users/urls.py`
- [ ] `kuro_user`, `reb_user` actions removed from `UserViewSet`
- [ ] No 404 on canonical routes (`/api/v1/auth/login`, `/api/v1/users/me`, etc.)
- [ ] Frontend still works (verify `kteam-fe-chief` login flow)

---

## Phase 3: Duplicate & Dead Code Removal

**What:** Remove SIMILAR_TO duplicates and dead code identified by CBM.

**Dependencies:** None (independent of Phases 1-2).

### 3A. SIMILAR_TO Duplicates (9 total)

| Function | Delete From | Keep In | Evidence |
|----------|------------|---------|----------|
| `has_read_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `has_write_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `get_branch_fallback` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `get_accessible_divisions` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `get_all_divisions` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `has_division_write_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `check_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `check_write_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |
| `check_division_write_access` | `backend/utils.py` | `backend/auth_utils.py` | CBM SIMILAR_TO edge |

**Do NOT delete from `backend/utils.py`:**
- `resolve_access_levels` — imported by `backend/auth_utils.py` (L109). This is the canonical caller.
- MongoDB helpers (`get_mongo_client`, `find_*`, `count_*`, `aggregate`, `update_*`, `insert_*`, `delete_*`) — unique to utils.py.
- `get_tenant_context` — unique to utils.py.

### 3B. MongoDB Helper Param Name Consistency

**Current inconsistency:**
- `find_all` accepts `div_code`/`branch_code` (canonical) ✅
- `find_one`, `count_documents`, `aggregate`, `update_many`, `insert_one`, `delete_many` accept `division`/`branch` (legacy) ❌

**Fix:** All helpers accept canonical names (`div_code`/`branch_code`) as primary params. Legacy aliases (`division`/`branch`) accepted via keyword-only compatibility shim, marked `@deprecated`.

### 3C. Dead Code

| Function | File | Evidence |
|----------|------|----------|
| `close_mongo_client` | `backend/utils.py` | CBM: 0 callers, 0 callees |

**Steps:**
1. Verify `close_mongo_client` has 0 callers via CBM (`codebase_trace`).
2. Delete function.

### 3D. Hardcoded Division Name

**`users/api/viewsets.py` L896:** `employees = [{**e, 'division': 'kurogaming'} for e in employees]`
- Hardcoded non-canonical `division` name that won't survive the `active_div_code` rename.
- **Fix:** Replace with canonical `active_div_code` from tenant context.

**Completion gate:**
- [ ] 9 SIMILAR_TO duplicates removed from `backend/utils.py`
- [ ] `close_mongo_client` deleted
- [ ] MongoDB helpers use canonical param names consistently
- [ ] Hardcoded `'division': 'kurogaming'` replaced with canonical `active_div_code`
- [ ] All imports updated
- [ ] Existing tests still pass

## Phase 4: M1 Identity Model Preparation (Spec Only)

**What:** Prepare the spec and migration scaffolding for `users_identity` + extension tables. **Do not execute M1** — this phase produces the migration spec and empty Django models only.

**Dependencies:** Phase 1 (naming must be canonical first).

### 4A. Target Models (from `postgresql_schema.md` §3)

**Complete model inventory (9 models, matching `postgresql_schema.md` exactly):**

| Model | Table | PK | Purpose |
|-------|-------|----|---------|
| `Identity` | `users_identity` | `identity_id` | Core identity (phone E.164, name, bg_code, div_code, user FK nullable) |
| `EmployeeProfile` | `users_employee` | `identity_id` | Employee extension (userid, role, department, ...) |
| `CustomerProfile` | `users_customer` | `identity_id` | Customer extension (registered, order_count, total_spent, ...) |
| `PlayerProfile` | `users_player` | `identity_id` | Player extension (player_id, team_id, rank, ...) |
| `Organization` | `users_organization` | `org_id` | Organizations (org_type: team/vendor, name, bg_code, div_code) |
| `VendorProfile` | `users_vendor_profile` | `org_id` | Vendor extension (gstin, pan, address, ...) |
| `TeamProfile` | `users_team_profile` | `org_id` | Team extension (team_id, coach) |
| `TeamMembership` | `team_memberships` | `id` | Team-to-person mapping (team_id, identity_id, role_in_team) |
| `PhoneAlias` | `identity_phone_aliases` | `id` | Phone alias table (identity_id FK, phone, alias_type) |

**Implementation notes:**
- `PhoneAlias` must declare `class Meta: db_table = 'identity_phone_aliases'` — Django would default to `users_phone_alias` which doesn't match the schema spec.
- `TeamMembership` must declare `class Meta: db_table = 'team_memberships'` — Django would default to `users_team_membership`.
- `TeamMembership` has composite CHECK: `(identity_id IS NOT NULL) OR (phone IS NOT NULL)` — allows unregistered members.
- All extension tables cascade on delete from `users_identity`.

**Files to create:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `users/models/identity.py` | `Identity` model |
| Create | `users/models/extensions.py` | `EmployeeProfile`, `CustomerProfile`, `PlayerProfile` |
| Create | `users/models/organizations.py` | `Organization`, `VendorProfile`, `TeamProfile`, `TeamMembership` |
| Create | `users/models/phone_aliases.py` | `PhoneAlias` model with `Meta.db_table` |
| Modify | `users/models/__init__.py` | Export all new models |

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

**Note:** Router-generated endpoints have trailing slashes (`/api/v1/auth/login/`). Legacy explicit paths had no trailing slash. Django's `APPEND_SLASH` handles redirect, but tests should use canonical trailing-slash URLs.

- [ ] `POST /api/v1/auth/login/` returns envelope-wrapped target response shape
- [ ] `GET /api/v1/users/me/` returns envelope-wrapped target response shape
- [ ] `POST /api/v1/auth/logout/` blacklists token
- [ ] `POST /api/v1/auth/refresh/` rotates token
- [ ] `POST /api/v1/auth/pwdreset/` works (router-generated, was legacy bare path)
- [ ] `POST /api/v1/auth/verify/` works (router-generated, was legacy bare path)
- [ ] Legacy paths (`/api/v1/auth/admin`, `/api/v1/kuro/user`, etc.) return 404
- [ ] `backend/urls.py` legacy paths (`/api/v1/bgSwitch`, `/api/v1/accesslevel`, etc.) return 404
- [ ] Phone normalization: raw input → E.164 in response
- [ ] JWT claims use `div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`
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
- **Canonical naming is mandatory:** `active_div_code`, `active_branch_code`, `bg_code` — no legacy `division`, `branches`, `bgcode` in JWT or responses.
- **M1 execution is out of scope:** This handoff produces models + migration command. Actual data migration (Phase 4 of `migration_spec.md`) is a separate handoff.

---

## Success Criteria

### Phase 0 (Alignment)
- [ ] All spec files agree on scope vs active context semantics
- [ ] Login response envelope shape frozen and consistent across all docs
- [ ] Legacy path inventory verified against root URL graph (28 total: 14 per file)
- [ ] SIMILAR_TO duplicate inventory complete (9 functions)
- [ ] Phase 4 model inventory matches `postgresql_schema.md` §3 completely (9 models)
- [ ] `multi_tenancy.md` session variables aligned with target JWT claims
- [ ] Shared utility ownership documented
- [ ] Compatibility matrix published

### Phase 1-5 (Implementation)
- [ ] 28 legacy URL paths removed (14 from `users/urls.py` + 14 from `backend/urls.py`)
- [ ] 9 SIMILAR_TO duplicates removed from `backend/utils.py`
- [ ] 1 dead function removed (`close_mongo_client`)
- [ ] MongoDB helpers use canonical param names consistently
- [ ] Hardcoded `'division': 'kurogaming'` replaced with canonical `active_div_code`
- [ ] JWT claims use canonical names (`div_codes[]`, `branch_codes[]`, `active_div_code`, `active_branch_code`, `bg_code`). `entity` removed.
- [ ] Login response matches envelope-wrapped target shape (per `endpoint_contract_spec.md` §3.1)
- [ ] `CookieTokenRefreshView` consolidated into `AuthViewSet.refresh`
- [ ] Phone normalization applied at all auth entry points
- [ ] Empty `users_identity` + 8 extension tables created (M1 scaffolding, 9 models total)
- [ ] `PhoneAlias` model declares `Meta.db_table = 'identity_phone_aliases'`
- [ ] `TeamMembership` model declares `Meta.db_table = 'team_memberships'`
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
6. **`backend/urls.py` legacy paths:** The audit revealed 14 legacy paths in `backend/urls.py` that were not in the original spec. These must be removed alongside the `users/urls.py` paths to avoid duplicate live endpoints.
7. **`resolve_access_levels` in `backend/utils.py`:** This function is imported by `backend/auth_utils.py` and must NOT be deleted during Phase 3. Only the 9 SIMILAR_TO duplicates are removed.
8. **Two `utils.py` files:** Phase 1C creates `users/utils.py` (phone normalization). This coexists with `backend/utils.py` (MongoDB helpers + access resolution). Consider `users/phone_utils.py` to avoid confusion.
9. **`CookieTokenRefreshView` consolidation:** Removing the standalone class requires verifying no external code imports it directly. CBM trace needed.
10. **Trailing slash behavior:** Router-generated endpoints have trailing slashes. Tests must use canonical URLs. Django's `APPEND_SLASH` provides redirect but shouldn't be relied upon in tests.

---

## Execution Order (DAG)

```
Phase 0 (Alignment + contract freeze) ─────────────┐
                                                     │
Phase 1 (Spec tightening) ← depends on Phase 0 ─────┤
Phase 2 (Legacy removal) ← depends on Phase 1       │
Phase 3 (Duplicate/dead code) ← depends on Phase 0 ─┤
Phase 4 (M1 scaffolding) ← depends on Phase 1       │
                                                     ▼
Phase 5 (Production wiring) ← depends on 1,2,3,4
```

**Parallel execution:** Phase 0 first (docs only). Then Phases 1, 3 can run simultaneously. Phase 2 depends on 1. Phase 4 depends on 1. Phase 5 depends on all.
