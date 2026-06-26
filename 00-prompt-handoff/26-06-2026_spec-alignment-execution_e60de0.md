# Spec Alignment Execution Plan

| Field | Value |
|-------|-------|
| Project ID | `kungos-rbac-migration` |
| Primary entity ID | `e60de0` |
| Entity type | `handoff` |
| Short description | Execute codebase alignment against target architectural spec across endpoint, database, and legacy-cleanup dimensions |
| Status | `draft` |
| Source references | `endpoint_contract_spec.md`, `postgresql_schema.md`, `mongodb_schema.md`, `migration_spec.md`, `26-06-2026_phase8b-backward-compat-removal_7f2a.md` |
| Generated | `26-06-2026` |
| Next action / owner | Execute Phase 1A (Identity data migration) — depends on Phase 8B completion |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/mongodb_schema.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/migration_spec.md`
- `/home/chief/llm-wiki/Kung_OS/architecture/rbac_system.md`
**Key files for this task:** See phase-specific handoffs

## Prerequisites

- [ ] Phase 8B (backward-compat removal) complete — Commit `70b892d`, Tests 209 passed, 8 pre-existing failures
- [ ] All 81 migration-specific tests passing
- [ ] Test baseline established: 192 passed, 8 failed (pre-existing auth 404s)

## Execution Order (DAG)

```
Phase 1A (Identity data migration) ─────────────────────────┐
Phase 1B (MongoDB field rename) ────────────────────────────┤
Phase 1C (Cafe schema migrations) ──────────────────────────┤
                                                             ▼
Phase 2A (RBAC FK: userid → identity_id) ──────────────────┐
Phase 2B (Login response rewrite) ──────────────────────────┤
Phase 2C (Legacy pattern cleanup) ──────────────────────────┤
Phase 2D (/rbac/ URL namespace) ────────────────────────────┤
                                                             ▼
Phase 3A (Standard response envelope) ──────────────────────┐
Phase 3B (Standard error handling) ─────────────────────────┤
Phase 3C (Legacy endpoint removal) ─────────────────────────┤
                                                             ▼
Phase 4A (Orders to PostgreSQL) ────────────────────────────┐
Phase 4B (E-Commerce product collections) ──────────────────┤
Phase 4C (Legacy cleanup: misc, caf_platform_users) ────────┤
                                                             ▼
Phase 5 (Production Wiring & Verification)
```

**Parallel opportunities:**
- Phase 1A, 1B, 1C can execute in parallel (no interdependencies)
- Phase 2A, 2B, 2C, 2D can execute in parallel (all depend on Phase 1 completion)
- Phase 3A, 3B, 3C can execute in parallel (all depend on Phase 2 completion)
- Phase 4A, 4B, 4C can execute in parallel (all depend on Phase 3 completion)

## Phase Summary

| Phase | Name | Priority | Effort | Risk |
|-------|------|----------|--------|------|
| 1A | Identity data migration (M1) | P0 | High | High |
| 1B | MongoDB field rename (M3) | P0 | High | High |
| 1C | Cafe schema migrations (M2) | P2 | Medium | Medium |
| 2A | RBAC FK: userid → identity_id | P0 | High | High |
| 2B | Login response rewrite | P1 | Medium | Medium |
| 2C | Legacy pattern cleanup | P1 | Low | Medium |
| 2D | /rbac/ URL namespace | P1 | Low | Low |
| 3A | Standard response envelope | P2 | Medium | Low |
| 3B | Standard error handling | P2 | Medium | Low |
| 3C | Legacy endpoint removal | P3 | Low | Low |
| 4A | Orders to PostgreSQL (M4) | P3 | High | High |
| 4B | E-Commerce product collections (M5) | P3 | Medium | Low |
| 4C | Legacy cleanup (misc, caf_platform_users) | P3 | Low | Low |
| 5 | Production Wiring & Verification | P0 | Medium | High |

## Phase 1A: Identity Data Migration (M1)

**What:** Migrate `users_kurouser` data into `users_identity`. Populate `identity_id` for all existing users. Establish `Identity.user` OneToOne relationships.

**Files:**
- Create: `users/management/commands/migrate_identity.py` (update existing)
- Modify: `users/models.py` (verify Identity model)
- Modify: `users/migrations/` (new migration)
- Create: `tests/test_identity_migration.py`

**Steps:**
1. Verify `Identity` model schema matches spec (all fields present)
2. Implement data migration: iterate `CustomUser` objects, create `Identity` records
3. Generate `identity_id` (use existing phone or UUID-based)
4. Set `Identity.user` FK for each record
5. Update `UserTenantContext.identity_id` for all active sessions
6. Verify no orphaned `CustomUser` records without `Identity`

**Tests:**
- All existing users have corresponding `Identity` records
- `Identity.user` OneToOne is populated
- `UserTenantContext.identity_id` is backfilled
- No data loss during migration

**Dependencies:** None (can start immediately)

**Completion Gate:**
- [ ] All `CustomUser` records have `Identity` counterparts
- [ ] `Identity.user` FK populated
- [ ] `UserTenantContext.identity_id` backfilled
- [ ] No regression in existing tests

## Phase 1B: MongoDB Field Rename (M3)

**What:** Rename tenant fields across all MongoDB collections: `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code`.

**Files:**
- Modify: `backend/mongo.py` (TenantCollection)
- Modify: All MongoDB query files in `teams/`, `domains/`, `careers/`
- Create: `tests/test_mongo_field_rename.py`

**Steps:**
1. Audit all MongoDB collection names and field names
2. Create migration script for each collection
3. Update `TenantCollection` to use canonical field names
4. Update all query code to use canonical names
5. Add backward-compat read path (temporary, 1 sprint)
6. Remove backward-compat path after verification

**Tests:**
- All MongoDB queries use canonical field names
- `TenantCollection` injects `bg_code` (not `bgcode`)
- Cross-tenant isolation verified (no data leakage)

**Dependencies:** None (can start in parallel with 1A)

**Completion Gate:**
- [ ] All collections use canonical field names
- [ ] Tenant isolation verified
- [ ] No regression in MongoDB-dependent tests

## Phase 1C: Cafe Schema Migrations (M2)

**What:** Apply unapplied migrations 0001-0003 for cafe schema alignment. Drop `caf_platform_users`. Align `caf_walkin_sessions` to use `identity_id` FK.

**Files:**
- Modify: `domains/cafe_arcade/migrations/0001_initial.py`
- Modify: `domains/cafe_arcade/migrations/0002_walkin_sessions.py`
- Modify: `domains/cafe_arcade/migrations/0003_drop_platform_users.py`
- Modify: `domains/cafe_arcade/models.py`

**Steps:**
1. Review unapplied migrations for correctness
2. Apply migration 0001 (initial cafe schema)
3. Apply migration 0002 (walk-in sessions with identity FK)
4. Apply migration 0003 (drop `caf_platform_users`)
5. Verify FK integrity on `caf_walkin_sessions`

**Tests:**
- All cafe migrations apply cleanly
- `caf_walkin_sessions.identity_id` FK valid
- `caf_platform_users` table dropped

**Dependencies:** Phase 1A (needs `Identity` data first)

**Completion Gate:**
- [ ] All migrations applied
- [ ] FK integrity verified
- [ ] Cafe endpoints functional

## Phase 2A: RBAC FK Migration (userid → identity_id)

**What:** Migrate all RBAC table FKs from `userid` to `identity_id`. Update `rbac_user_roles`, `rbac_user_permissions`, `rbac_user_role_branches`.

**Files:**
- Modify: `users/models.py` (UserRole, UserPermission, UserRoleBranch)
- Create: `users/migrations/` (new migration)
- Modify: `backend/auth_utils.py` (resolve_access)
- Create: `tests/test_rbac_identity_fk.py`

**Steps:**
1. Add `identity_id` column to RBAC tables (nullable initially)
2. Backfill `identity_id` from `Identity` model
3. Switch FK from `userid` to `identity_id`
4. Update `resolve_access()` to query by `identity_id`
5. Remove `userid` column from RBAC tables

**Tests:**
- RBAC queries work with `identity_id`
- `resolve_access()` returns correct permissions
- No orphaned RBAC records

**Dependencies:** Phase 1A (needs `Identity` data)

**Completion Gate:**
- [ ] All RBAC tables use `identity_id` FK
- [ ] `resolve_access()` works with `identity_id`
- [ ] No regression in RBAC tests

## Phase 2B: Login Response Rewrite

**What:** Rewrite login response to match spec §4.2 target shape. Replace `userid` with `identity_id`, `accesslevel` with `permissions[]`, add `refresh_token`, `token_type`, `expires_in`, `roles[]`.

**Files:**
- Modify: `users/views.py` (login function)
- Modify: `users/api/viewsets.py` (user profile endpoint)
- Modify: `users/serializers.py` (login response serializer)
- Create: `tests/test_login_response.py`

**Steps:**
1. Create `LoginResponseSerializer` matching spec
2. Update login view to use new serializer
3. Populate `active_div_code`, `active_branch_code` from `UserTenantContext`
4. Add `refresh_token` generation
5. Normalize phone to E.164
6. Remove `accesslevel[]`, `businessgroups[]` from response

**Tests:**
- Login response matches spec shape
- `identity_id` present, `userid` absent
- `permissions[]` populated from RBAC
- Phone E.164 normalized

**Dependencies:** Phase 2A (needs RBAC with `identity_id`)

**Completion Gate:**
- [ ] Login response matches spec
- [ ] All required fields present
- [ ] No regression in auth tests

## Phase 2C: Legacy Pattern Cleanup

**What:** Replace `user.access == "Super"` pattern (8 sites) with `is_supervisor(permissions)`. Remove `business_accesslevel`/`division_accesslevel` functions.

**Files:**
- Modify: `users/views.py` (lines 136, 339, 266, 521)
- Modify: `users/api/viewsets.py` (lines 748, 842, 1008)
- Modify: `teams/kurostaff/views.py` (line 1254)
- Modify: `teams/products.py` (line 899)
- Modify: `careers/views.py` (lines 103, 116)
- Modify: `domains/search/viewsets.py` (line 63)
- Create: `tests/test_legacy_pattern_cleanup.py`

**Steps:**
1. Replace `user.access == "Super"` with `is_supervisor(result['permissions'])`
2. Remove `business_accesslevel()` function and callers
3. Remove `division_accesslevel()` function and callers
4. Replace `userData["access"]` with `userData["permissions"]`
5. Verify all 8 sites migrated

**Tests:**
- No `user.access` references remain outside `kurostaff` internal queries
- `is_supervisor()` used consistently
- `business_accesslevel` function removed

**Dependencies:** Phase 2A (needs RBAC with `identity_id`)

**Completion Gate:**
- [ ] All 8 `user.access` sites migrated
- [ ] `business_accesslevel` removed
- [ ] `division_accesslevel` removed
- [ ] No regression in tests

## Phase 2D: /rbac/ URL Namespace

**What:** Create `users/rbac_urls.py` and route under `/api/v1/rbac/`. Expose roles, permissions, assignments, user lookup.

**Files:**
- Create: `users/rbac_urls.py`
- Modify: `backend/urls.py` (add `/rbac/` route)
- Modify: `users/api/viewsets.py` (ensure viewsets are routable)
- Create: `tests/test_rbac_urls.py`

**Steps:**
1. Create `rbac_urls.py` with router configuration
2. Register `RoleViewSet`, `PermissionViewSet`, `UserRoleViewSet`, `UserPermissionViewSet`
3. Add `path('rbac/', include('users.rbac_urls'))` to `backend/urls.py`
4. Implement `GET /rbac/user/{identity_id}` endpoint
5. Implement `GET /rbac/role/{role_code}` endpoint

**Tests:**
- All `/api/v1/rbac/` endpoints accessible
- Role/permission CRUD works
- User lookup by `identity_id` works

**Dependencies:** Phase 2A (needs RBAC with `identity_id`)

**Completion Gate:**
- [ ] `/api/v1/rbac/` namespace registered
- [ ] All spec endpoints implemented
- [ ] Endpoints functional

## Phase 3A: Standard Response Envelope

**What:** Create middleware for standard response envelope: `{status, data, meta}` wrapping all API responses.

**Files:**
- Create: `backend/middleware/response_envelope.py`
- Modify: `backend/settings.py` (add middleware)
- Create: `tests/test_response_envelope.py`

**Steps:**
1. Create `ResponseEnvelopeMiddleware`
2. Wrap successful responses in `{status: "success", data: ..., meta: {...}}`
3. Inject `request_id` (UUID) and `timestamp` (ISO 8601)
4. Exclude non-JSON responses (files, redirects)
5. Add to `MIDDLEWARE` settings

**Tests:**
- All JSON responses wrapped in envelope
- `request_id` present and unique
- `timestamp` ISO 8601 format
- Non-JSON responses excluded

**Dependencies:** None (can run in parallel with Phase 2)

**Completion Gate:**
- [ ] Middleware active
- [ ] All JSON responses wrapped
- [ ] Non-JSON responses excluded
- [ ] No regression in tests

## Phase 3B: Standard Error Handling

**What:** Implement standard error codes (`VALIDATION_ERROR`, `PERMISSION_DENIED`, `TENANT_ISOLATION`, etc.) in `{status, error, meta}` envelope.

**Files:**
- Create: `backend/exceptions.py`
- Create: `backend/exception_handlers.py`
- Modify: `backend/settings.py` (REST_FRAMEWORK exception handler)
- Create: `tests/test_error_handling.py`

**Steps:**
1. Define standard error codes enum
2. Create custom exception classes
3. Implement DRF exception handler
4. Map HTTP status codes to error codes
5. Add to `REST_FRAMEWORK` settings

**Tests:**
- Validation errors return `VALIDATION_ERROR`
- Permission denied returns `PERMISSION_DENIED`
- All errors wrapped in standard envelope
- Error codes match spec

**Dependencies:** Phase 3A (needs envelope middleware)

**Completion Gate:**
- [ ] Standard error codes defined
- [ ] Exception handler active
- [ ] All errors wrapped
- [ ] No regression in tests

## Phase 3C: Legacy Endpoint Removal

**What:** Remove legacy endpoints per spec Appendix B. Clean up `/kuro/user` alias and other deprecated routes.

**Files:**
- Modify: `users/urls.py` (remove legacy routes)
- Modify: `users/api/viewsets.py` (remove legacy actions)
- Modify: `domains/cafe_arcade/urls.py` (remove legacy actions)
- Create: `tests/test_legacy_endpoint_removal.py`

**Steps:**
1. Audit all legacy endpoints
2. Remove `/kuro/user` alias
3. Remove `cafe/sessions/start` legacy action
4. Remove any other Appendix B endpoints
5. Verify no 404 regressions for active endpoints

**Tests:**
- Legacy endpoints return 404 (removed)
- Active endpoints still functional
- No broken internal references

**Dependencies:** Phase 2B (login response must be new shape first)

**Completion Gate:**
- [ ] All legacy endpoints removed
- [ ] Active endpoints functional
- [ ] No 404 regressions

## Phase 4A: Orders to PostgreSQL (M4)

**What:** Migrate orders data from MongoDB (4 collections) to PostgreSQL (7 tables). Align with `orders_*` schema.

**Files:**
- Modify: `domains/orders/models.py`
- Create: `domains/orders/migrations/`
- Modify: `domains/orders/viewsets.py`
- Modify: `teams/kurostaff/views.py` (order-related queries)
- Create: `tests/test_orders_postgresql.py`

**Steps:**
1. Create PostgreSQL models for orders schema
2. Generate migrations
3. Migrate data from MongoDB to PostgreSQL
4. Update viewsets to use PostgreSQL models
5. Update `teams/kurostaff/views.py` to query PostgreSQL
6. Verify data integrity

**Tests:**
- All order data migrated
- PostgreSQL queries return correct data
- Order CRUD operations functional

**Dependencies:** Phase 1A (needs `Identity` for FK)

**Completion Gate:**
- [ ] All orders migrated to PostgreSQL
- [ ] Order CRUD functional
- [ ] No data loss

## Phase 4B: E-Commerce Product Collections (M5)

**What:** Implement e-commerce product collections in PostgreSQL. 12 collections total.

**Files:**
- Modify: `domains/eshop/models.py`
- Create: `domains/eshop/migrations/`
- Modify: `domains/eshop/viewsets.py`
- Create: `tests/test_eshop_products.py`

**Steps:**
1. Create PostgreSQL models for product collections
2. Generate migrations
3. Implement viewsets for product CRUD
4. Wire up `/api/v1/eshop/` routes
5. Verify product catalog functionality

**Tests:**
- Product CRUD operations functional
- E-shop endpoints accessible
- Product data integrity

**Dependencies:** Phase 1A (needs `Identity` for FK)

**Completion Gate:**
- [ ] Product models created
- [ ] E-shop endpoints functional
- [ ] No regression in tests

## Phase 4C: Legacy Cleanup

**What:** Drop `misc` MongoDB collection (100% duplicate of `reb_users`). Drop `caf_platform_users` table. Clean up other deprecated artifacts.

**Files:**
- Modify: `backend/mongo.py` (remove `misc` collection references)
- Modify: `users/migrations/` (drop `caf_platform_users`)
- Create: `tests/test_legacy_cleanup.py`

**Steps:**
1. Verify no code references `misc` collection
2. Drop `misc` collection from MongoDB
3. Verify no code references `caf_platform_users`
4. Drop `caf_platform_users` table
5. Clean up any other deprecated artifacts

**Tests:**
- No code references dropped collections/tables
- No runtime errors from missing collections
- No regression in tests

**Dependencies:** Phase 1C (cafe migrations must be applied first)

**Completion Gate:**
- [ ] `misc` collection dropped
- [ ] `caf_platform_users` table dropped
- [ ] No code references remaining
- [ ] No regression in tests

## Phase 5: Production Wiring & Verification

**What:** End-to-end verification of all alignment changes. Full test suite, integration tests, health checks.

**Steps:**
1. Run full test suite — verify 0 regressions
2. Run integration tests for each domain
3. Verify login flow end-to-end
4. Verify RBAC resolution end-to-end
5. Verify tenant isolation
6. Verify MongoDB field naming consistency
7. Verify PostgreSQL FK integrity
8. Verify all spec endpoints accessible

**Post-Wiring Tests (GATE):**
- [ ] Full test suite passes (0 regressions)
- [ ] Login response matches spec shape
- [ ] RBAC resolution works end-to-end
- [ ] Tenant isolation verified (no cross-tenant leakage)
- [ ] All spec endpoints accessible
- [ ] MongoDB collections use canonical field names
- [ ] PostgreSQL FK integrity verified
- [ ] Standard response envelope active
- [ ] Standard error handling active
- [ ] Health check endpoint reports all components ok

**Completion Gate:**
- [ ] All post-wiring tests pass
- [ ] No regression in existing tests
- [ ] All spec requirements met
- [ ] Documentation updated

## Constraints

- **0 test regressions:** No existing test may break. Pre-existing 8 auth 404s excluded.
- **Atomic migrations:** Database migrations must be atomic (no partial state).
- **Tenant isolation:** No cross-tenant data exposure at any point.
- **Backward compatibility during transition:** Maintain both old and new field names during migration window (1 sprint max).
- **Identity-first:** All person references use `identity_id` after Phase 2A. No new `userid` references.
- **Spec compliance:** Endpoints must match spec contract exactly (URL, method, response shape).

## Success Criteria

- [ ] All P0 items complete (Identity migration, MongoDB rename, RBAC FK, Production wiring)
- [ ] All P1 items complete (Login response, legacy patterns, /rbac/ namespace)
- [ ] All P2 items complete (Response envelope, error handling, Cafe migrations)
- [ ] All P3 items complete (Orders PG, E-Commerce, legacy cleanup)
- [ ] Full test suite passes with 0 regressions
- [ ] All spec endpoints accessible and functional
- [ ] Tenant isolation verified
- [ ] Documentation updated to reflect completed alignment

## Caveats & Uncertainty

1. **MongoDB field rename (Phase 1B):** The `TenantCollection` injects `bg_code` but legacy collections use `bgcode`. During migration window, both names must be supported. Risk of silent cross-tenant data exposure if mismatch occurs. **Mitigation:** Add assertion in `TenantCollection` that verifies expected field exists.

2. **Identity data migration (Phase 1A):** `CustomUser.userid` is the Django AUTH_USER_MODEL PK. All FK references across cafe, eshop, orders, and RBAC tables must be updated. **Mitigation:** Two-phase migration — add `identity_id` column, backfill, switch FK, drop `userid`.

3. **Login response rewrite (Phase 2B):** Frontend may depend on current response shape. **Mitigation:** Coordinate with frontend team before deploying. Consider versioned endpoint (`/auth/login/v2`).

4. **`user.access == "Super"` in `teams/kurostaff/views.py:1254`:** Passes `user.access` to a MongoDB query (`inwardinvoice_calce`). Replacing with `is_supervisor()` alone won't fix the query logic — the Mongo query may need to be rewritten.

5. **Standard response envelope (Phase 3A):** Wrapping all responses changes wire contract. Third-party integrations may break. **Mitigation:** Exclude third-party endpoints from middleware.

## Serialized Phase Handoffs

Individual phase handoff docs are generated separately:

| Phase | Filename |
|-------|----------|
| 1A | `26-06-2026_spec-alignment-execution_e60de0_p1a-identity-migration.md` |
| 1B | `26-06-2026_spec-alignment-execution_e60de0_p1b-mongo-field-rename.md` |
| 1C | `26-06-2026_spec-alignment-execution_e60de0_p1c-cafe-schema.md` |
| 2A | `26-06-2026_spec-alignment-execution_e60de0_p2a-rbac-fk-migration.md` |
| 2B | `26-06-2026_spec-alignment-execution_e60de0_p2b-login-response.md` |
| 2C | `26-06-2026_spec-alignment-execution_e60de0_p2c-legacy-patterns.md` |
| 2D | `26-06-2026_spec-alignment-execution_e60de0_p2d-rbac-urls.md` |
| 3A | `26-06-2026_spec-alignment-execution_e60de0_p3a-response-envelope.md` |
| 3B | `26-06-2026_spec-alignment-execution_e60de0_p3b-error-handling.md` |
| 3C | `26-06-2026_spec-alignment-execution_e60de0_p3c-legacy-endpoints.md` |
| 4A | `26-06-2026_spec-alignment-execution_e60de0_p4a-orders-postgresql.md` |
| 4B | `26-06-2026_spec-alignment-execution_e60de0_p4b-eshop-products.md` |
| 4C | `26-06-2026_spec-alignment-execution_e60de0_p4c-legacy-cleanup.md` |
| 5 | `26-06-2026_spec-alignment-execution_e60de0_p5-production-wiring.md` |
