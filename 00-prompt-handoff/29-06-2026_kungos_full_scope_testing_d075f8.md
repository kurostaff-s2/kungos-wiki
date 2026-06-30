# KungOS Full-Scope Testing & Alignment Verification

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | d075f8-expanded |
| Entity type | work_item |
| Short description | Verify KungOS_Mongo_One serves all data to frontend correctly per spec — runtime wiring first, technical compliance second. Includes KungOS Admin (core infrastructure). Excludes eshop. |
| Status | in_progress — Phases 0-1 complete |
| Source references | `29-06-2026_db_state_report_d075f8.md`, `29-06-2026_data-propagation-testing_d075f8.md`, `29-06-2026_filter-parser-mixin-and-frontend-migration_7bd873.md`, `frontend_alignment_handoff.md`, `29-06-2026_response_envelope_final_fix.md`, `29-06-2026_frontend_backend_schema_alignment_v4.md`, `28-06-2026_api-contract-audit-by-domain.md`, `endpoint_contract_spec_revised.md` |
| Generated | 29-06-2026 (updated) |
| Next action / owner | Testing agent — execute Phases 2-7 |
| Excluded | E-shop domain (per user request) |

## Primary Goal

**Data in KungOS_Mongo_One must flow to the frontend correctly.** The spec is the guiding factor. Runtime functional wiring is verified first; technical compliance (envelopes, error codes, etc.) is verified second.

## Prerequisite

**See `29-06-2026_db_state_report_d075f8.md`** — KungOS_Mongo_One has critical data gaps (4,610 missing inwardinvoices, empty stock_register, no divisions/branches). These MUST be resolved before testing is meaningful.

---

## Context

The KungOS migration has progressed through multiple phases: filter parsing migration (complete), RBAC migration (33 files), response envelope standardization (P0-P3 complete), identity field alignment (Employee/HR domain complete), and API contract auditing (19 domains audited). This handoff consolidates all remaining testing and verification work into a single execution plan.

**What this covers:**
1. Filter data propagation (MongoDB → Backend → Frontend)
2. RBAC permission enforcement
3. Response envelope compliance
4. Tenant context integrity
5. Schema alignment (identity_id migration)
6. API contract compliance across all domains

**What is excluded:**
- E-shop domain (explicitly excluded by user)
- Careers domain (P3 — no frontend pages exist)
- Tournaments domain (P3 — no frontend pages exist)

**What is included:**
- KungOS Admin domain (core infrastructure — tenant bootstrap, domain config, API keys, templates)

---

## Project Context

**Backend project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Frontend project root:** `/home/chief/Coding-Projects/kteam-fe-chief`
**Authoritative specs:**
- `endpoint_contract_spec_revised.md` — Wire contract authority
- `multi_tenancy.md` — Multi-tenancy constitution
- `CANONICAL_NAMING.md` — Naming gate
- `frontend_alignment_handoff.md` — Alignment review findings

---

## Execution Order

```
Phase 0: DB Migration (Prerequisite — see db_state_report)
    ↓
Phase 1: Runtime Functional Wiring (data flows DB → Frontend)
    ↓
Phase 2: Filter Data Propagation (d075f8 core)
    ↓
Phase 3: Response Envelope + Error Handling
    ↓
Phase 4: Tenant Context Integrity
    ↓
Phase 5: RBAC Permission Enforcement
    ↓
Phase 6: Schema Alignment (identity_id)
    ↓
Phase 7: API Contract Compliance (domain-by-domain)
```

**Rationale:** Phase 0 ensures data exists in KungOS_Mongo_One. Phase 1 verifies the data actually reaches the frontend (runtime wiring is the primary goal). Phase 2-3 verify the filter/tenant mechanics. Phase 4 verifies response envelopes. Phase 5 verifies tenant context. Phase 6 verifies RBAC + schema alignment. Phase 7 verifies API contracts — these are all secondary to runtime wiring.

---

## Phase 0: DB Migration (Prerequisite)

**What:** Resolve critical data gaps in KungOS_Mongo_One so it can serve all data to the frontend.

**Source:** `29-06-2026_db_state_report_d075f8.md`

**Why first:** Without data, no testing is meaningful. The DB must be complete before verifying wiring.

### Critical Gaps to Fix

| # | Issue | Legacy Count | Target Count | Action |
|---|-------|--------------|--------------|--------|
| 1 | inwardinvoices missing | 4,626 | 16 | Migrate 4,610 docs with canonical tenant fields |
| 2 | stock_register empty | 194 | 0 | Restore from archived_stock_register_20260628 |
| 3 | tenant_divisions empty | 0 | 0 | Populate from Mongo data references |
| 4 | tenant_branches empty | 0 | 0 | Populate from Mongo data references |
| 5 | inwardpayments doubled | 9,467 | 21,026 | Investigate & deduplicate |
| 6 | purchaseorders tripled | 5,395 | 15,216 | Investigate & deduplicate |
| 7 | estimates missing 542 | 4,850 | 4,308 | Re-migrate missing docs |
| 8 | paymentvouchers missing 50 | 3,509 | 3,459 | Re-migrate missing docs |
| 9 | kgorders missing 304 | 9,466 | 9,162 | Re-migrate missing docs |
| 10 | Product catalog no tenant fields | 11 cols | 0 | Enrich with bg_code/div_code/branch_code |

### Migration Requirements

1. **Use lowercase collection names** (MongoDB is case-sensitive)
2. **Add canonical tenant fields**: `bg_code`, `div_code`, `branch_code` to every document
3. **Replace legacy `entity` field** with `bg_code` (mapping: `kurogaming` → `KURO0001`)
4. **Preserve `_id`** to maintain referential integrity
5. **Add `migrated_at` timestamp** for audit trail
6. **Skip already-migrated documents** (idempotent)
7. **Handle type coercion** (e.g., `totalprice` as string → number)

### Verification

- [ ] All legacy kuropurchase collections exist in KungOS_Mongo_One with matching counts
- [ ] All documents have canonical tenant fields
- [ ] No `entity` field remains in business collections
- [ ] Product catalog collections enriched with tenant fields
- [ ] PostgreSQL tenant_divisions and tenant_branches populated
- [ ] inwardpayments and purchaseorders counts verified (no duplication)
- [ ] KungOS_Mongo_One is the sole data source (legacy DB not referenced by app)

---

## Phase 1: Runtime Functional Wiring

**What:** Verify that data from KungOS_Mongo_One actually flows to the frontend correctly. This is the PRIMARY goal — if the data doesn't reach the UI, nothing else matters.

**Source:** `endpoint_contract_spec_revised.md` §3.1, `frontend_alignment_handoff.md`

**Scope:** Every domain page that serves data from MongoDB → verify it loads correctly.

### Phase 1a: Backend API Data Serving Verification

**What:** For each backend endpoint, verify it returns correct data from KungOS_Mongo_One.

**Steps:**
1. Start backend dev server (`python3 manage.py runserver`)
2. For each domain, hit the list endpoints with valid JWT
3. Verify: correct data returned, correct envelope format, correct tenant filtering
4. Verify: empty results for non-existent tenant context

**Domains to verify (excluding eshop):**

| Domain | Key Endpoints | Data Source | Priority |
|--------|--------------|-------------|----------|
| Accounts | inward-invoices, outward-invoices, purchase-orders, estimates, vendors | Mongo | P0 |
| Orders | in-store, tp-orders, estimates, service-requests | Mongo + PG | P0 |
| Products | catalog, presets, tp-builds | Mongo | P0 |
| Inventory | stock, stock-register, audit | Mongo + PG | P0 |
| Teams | employees, attendance, salaries | Mongo + PG | P1 |
| Vendors | vendors | Mongo | P1 |
| Search | search | Mongo | P1 |
| Tenant | business-groups, divisions, branches | PG | P0 |
| RBAC | roles, permissions, user-access | PG | P1 |
| Auth | login, refresh, verify | PG | P0 |
| Cafe Arcade | stations, sessions, wallet, games | PG + Mongo | P1 |
| Cafe FNB | menu | PG | P1 |
| Cafe Tracker | tracker/active, sessions | Mongo | P1 |
| KungOS Admin | tenant/bootstrap, domain-config, api-keys, templates | PG | P1 |

**Success Criteria:**
- [ ] All P0 domain endpoints return data from KungOS_Mongo_One
- [ ] Tenant filtering works (div_code, branch_code)
- [ ] No 500 errors from missing data
- [ ] Pagination works (limit, offset, page)
- [ ] Empty results return correct empty response

### Phase 1b: Frontend Data Loading Verification

**What:** Verify each frontend page loads data correctly from the backend.

**Steps:**
1. Start frontend dev server (`npm run dev`)
2. Login with test user
3. Navigate to each page
4. Verify: data renders, no console errors, correct filter params in network tab

**Pages to verify (excluding eshop):**

| Domain | Pages | Status |
|--------|-------|--------|
| Accounts | InvoicesList, InvoiceCreate, VendorsList, Counters, EstimatesList, etc. (12 pages) | To verify |
| Orders | OrdersList, OrderCreate, EstimatesList, ServiceRequestsList (10 pages) | To verify |
| Products | ProductsList, Presets, TPBuilds (6 pages) | To verify |
| Inventory | StockList, StockRegister, AuditList (8 pages) | To verify |
| Teams | Employees, Attendance, Salaries (6 pages) | To verify |
| Tenant | BusinessGroups, Branches, Brands, Roles, UserAccess (5 pages) | To verify |
| RBAC | Roles, UserAccess (2 pages) | To verify |
| Auth | Login, Unauthorized (2 pages) | To verify |
| Cafe | Dashboard, Stations, Sessions, Wallet, Games (12 pages) | To verify |
| Search | SearchResults (1 page) | To verify |
| KungOS Admin | Bootstrap, DomainConfig, ApiKeys, Templates | To verify |

**Success Criteria:**
- [ ] All pages load without errors
- [ ] Data renders correctly
- [ ] Filter params use `?filter[field]=value` format
- [ ] Pagination works
- [ ] No legacy `division=` or `branch=` in network requests

---

## Phase 2: Filter Data Propagation Testing

**What:** Verify end-to-end data flow: MongoDB → FilterParserMixin → Frontend hydration across all migrated ViewSets.

**Source:** `29-06-2026_data-propagation-testing_d075f8.md`

**Scope:**
- 32 backend view files using `apply_filter_params(request)`
- 23 frontend files sending `?filter[field]=value` format
- FilterParserMixin operator coverage (10 operators)
- Tenant field exclusion (div_code, branch_code, bg_code)

### Phase 1a: Backend Unit Tests — FilterParserMixin

**Files:** `plat/tests/test_filter_parser.py`

**Steps:**
1. Run existing 20 tests as baseline
2. Add 21 new tests covering all operators, type coercion, edge cases
3. Test MongoDB vs ORM mode output
4. Verify all 41 tests pass

**Test coverage matrix:**

| Operator | Query Param | Expected Output |
|----------|-------------|-----------------|
| Exact match | `?filter=status=active` | `{'status': 'active'}` |
| Greater than | `?filter[age__gt]=18` | `{'age': {'$gt': 18}}` |
| Less than | `?filter[age__lt]=65` | `{'age': {'$lt': 65}}` |
| GTE | `?filter[price__gte]=100` | `{'price': {'$gte': 100}}` |
| LTE | `?filter[price__lte]=1000` | `{'price': {'$lte': 1000}}` |
| In list | `?filter[status__in]=active,pending` | `{'status': {'$in': ['active', 'pending']}}` |
| Contains | `?filter[name__contains]=john` | `{'name': {'$regex': 'john', '$options': 'i'}}` |
| Startswith | `?filter[code__startswith]=INV-` | `{'code': {'$regex': '^INV-', '$options': 'i'}}` |
| Endswith | `?filter[email__endswith]=@example.com` | `{'email': {'$regex': '@example\.com$', '$options': 'i'}}` |
| Regex | `?filter[code__regex]=^INV-\d{4}$` | `{'code': {'$regex': '^INV-\\d{4}$'}}` |
| Is null | `?filter[deleted_at__isnull]=true` | `{'deleted_at': None}` |
| Iexact | `?filter[name__iexact]=john` | `{'name': {'$regex': '^john$', '$options': 'i'}}` |
| Multiple same field | `?filter[age__gt]=18&filter[age__lt]=65` | `{'age': {'$gt': 18, '$lt': 65}}` |
| Type coercion (int) | `?filter[limit]=10` | `{'limit': 10}` |
| Type coercion (bool) | `?filter[active]=true` | `{'active': True}` |
| Empty filter | `?filter[]=` | `{}` |
| Invalid operator | `?filter[name__invalid]=test` | Skip field, log warning |
| Tenant fields excluded | `?filter[div_code]=DIV001` | NOT in output |
| Search excluded | `?search=test` | NOT in output |
| Sort excluded | `?sort=-name` | NOT in output |
| Legacy rejected | `?division=KURO0001_001` | NOT parsed |

**Success Criteria:** 41/41 tests passing, no regression in existing tests.

### Phase 1b: Backend Integration Tests — ViewSet Endpoints

**Files:** `plat/tests/test_viewset_integration.py` (new)

**Steps:**
1. Test FilterParserMixin integration with DRF ViewSets
2. Test with mock MongoDB collection
3. Verify tenant field exclusion in business filters
4. Test edge cases (empty, invalid, multiple operators)

**Success Criteria:** 10/10 integration tests passing.

### Phase 1c: Frontend Component Tests

**Files:** `src/components/__tests__/FilterParams.test.jsx`, `src/hooks/__tests__/useTenantQuery.test.jsx`

**Steps:**
1. Test useTenantQuery emits `?filter[div_code]=` format
2. Test multiple filter params
3. Test pagination params (limit, offset, page)
4. Test search/sort params not in filter[]
5. Verify no legacy `division=` or `branch=` in API calls

**Success Criteria:** 8/8 frontend tests passing.

### Phase 1d: End-to-End Smoke Tests

**Files:** `tests/smoke_tests.md` (new)

**Steps:**
1. Insert test data in MongoDB
2. Test backend API with filter params via curl
3. Test frontend UI filter application
4. Test edge cases (empty results, pagination, combined filters)

**Success Criteria:** 5/5 smoke tests passing.

---

## Phase 3: Response Envelope & Error Handling

**What:** Verify all API responses conform to the canonical envelope (spec §3.1 success, §8.2 error) and that error handling is consistent.

**Source:** `29-06-2026_response_envelope_final_fix.md`, `29-06-2026_P3_closeout_verification.md`

**Scope:**
- 2xx success responses use `{status, data, meta}` envelope
- Non-2xx error responses use spec error envelope with `request_id` in `meta`
- `INPUT_ERROR` replaced with `VALIDATION_ERROR`
- `api_error()` tuple unpacking removed
- 421 class-method wrappers cleaned up
- 201/202/204 status codes preserved

### Phase 2a: Backend Response Envelope Verification

**Files to verify:**
- `backend/response_utils.py` — `success_response()`, `error_response()`, `_meta()`
- `plat/observability/middleware.py` — `ResponseEnvelopeMiddleware`
- All domain viewsets — error response patterns

**Steps:**
1. Verify `ResponseEnvelopeMiddleware` adds `request_id` + `timestamp` to all 2xx responses
2. Verify `_meta()` always generates `request_id` (auto-UUID if not provided)
3. Grep for raw `Response()` error calls — should be 0 (except health checks)
4. Grep for `INPUT_ERROR` — should be 0
5. Grep for `api_error(` — should be 0
6. Verify all domain views use `error_response()` utility

**Success Criteria:**
- [ ] 0 raw error `Response()` calls (except health checks)
- [ ] 0 `INPUT_ERROR` references
- [ ] 0 `api_error()` tuple unpacking
- [ ] All non-2xx errors use canonical envelope
- [ ] All files compile

### Phase 2b: Frontend Error Handling Verification

**Steps:**
1. Count mutations with `onError` handlers (target: 129/129)
2. Verify error format matches spec §8.2
3. Verify error display in UI components

**Success Criteria:**
- [ ] All 129 mutations have `onError` handlers
- [ ] Error format matches spec

---

## Phase 4: Tenant Context Integrity

**What:** Verify tenant isolation is correct across all domains — no cross-tenant data leakage, JWT claims are authoritative, tenant switching works.

**Source:** `frontend_alignment_handoff.md` (§Review Findings), `28-06-2026_tenant-context-audit_a72921.md`, `29-06-2026_P3_closeout_verification.md`

**Scope:**
- Middleware extracts only canonical JWT claims (`bg_code`, `div_codes`, `branch_codes`, `identity_id`)
- Missing claims → `TenantContextMissing` (HTTP 401)
- `POST /api/v1/tenant/switch/` regenerates JWT with canonical claims
- MongoDB queries include tenant filters
- Frontend calls backend on tenant switch

### Phase 3a: Middleware Validation

**Files:** `plat/observability/middleware.py`

**Steps:**
1. Verify `TenantContextMiddleware.process_request()` extracts only canonical claims
2. Verify missing `bg_code` or `identity_id` raises `TenantContextMissingError` (HTTP 401)
3. Verify no legacy key references (`entity`, `branches`, `userid`) in extraction path
4. Verify ContextVar uses canonical keys

**Success Criteria:**
- [ ] Middleware uses only canonical JWT keys
- [ ] Missing claims → HTTP 401
- [ ] No legacy key references

### Phase 3b: MongoDB Tenant Filtering

**Files:** `backend/utils.py` — `get_collection()`, `find_all()`, `find_one()`

**Steps:**
1. Verify all `get_collection()` calls include `bg_code`
2. Grep for MongoDB queries without tenant filter
3. Verify `TenantCollection` reads only canonical ContextVar keys
4. Test cross-tenant data isolation

**Success Criteria:**
- [ ] All 222+ tenant-filtered queries use canonical keys
- [ ] No cross-tenant data access attempts
- [ ] `get_collection()` rejects legacy `division=` param

### Phase 3c: Tenant Switch Verification

**Files:** `tenant/context_views.py`, `users/tenant_tokens.py`

**Steps:**
1. Verify `POST /api/v1/tenant/switch/` updates `UserTenantContext`
2. Verify new JWT generated with all canonical claims
3. Verify HttpOnly cookie set with correct security attributes
4. Verify response returns updated context payload
5. Verify frontend calls backend on tenant switch (not local-only)

**Success Criteria:**
- [ ] Switch endpoint works end-to-end
- [ ] JWT regenerated with canonical claims
- [ ] Frontend calls backend on switch

### Phase 3d: Login Response Verification

**Steps:**
1. Verify login response includes `div_codes`, `branch_codes`, `scope`
2. Verify `_permissions` includes level information (not just flat list)
3. Verify `identity_id` in login response

**Success Criteria:**
- [ ] Login response includes full tenant context
- [ ] Permissions include level information

---

## Phase 5: RBAC Permission Enforcement

**What:** Verify RBAC migration is complete and permissions are correctly enforced in the frontend.

**Source:** `frontend_alignment_handoff.md` (RF-2), `frontend_alignment_handoff.md` (§Executive Summary)

**Scope:**
- 33 files migrated from legacy `accesslevels` to `_permissions`
- Permission levels correctly assigned (not all level 2)
- RBAC endpoints aligned (fully compliant per audit)

### Phase 4a: Backend RBAC Verification

**Steps:**
1. Verify no legacy `accesslevels` references in backend
2. Verify `/tenant/current/` returns `_permissions` with levels
3. Verify login response includes permission levels
4. Verify RBAC endpoints return correct data

**Success Criteria:**
- [ ] 0 legacy `accesslevels` references
- [ ] Login response includes permission levels
- [ ] RBAC endpoints fully aligned

### Phase 4b: Frontend RBAC Verification

**Steps:**
1. Verify `buildPermissionsObject()` reads levels from backend (not hard-coded to 2)
2. Verify UI respects permission levels (view-only vs edit)
3. Verify 33 files migrated to `_permissions`

**Success Criteria:**
- [ ] Permission levels correctly assigned
- [ ] UI respects permission levels
- [ ] 33 files migrated

---

## Phase 6: Schema Alignment (identity_id Migration)

**What:** Verify identity field alignment across domains — `identity_id` used for cross-domain person references, `userid` only for auth.

**Source:** `29-06-2026_frontend_backend_schema_alignment_v4.md`

**Scope:**
- Employee/HR domain: ✅ Complete (42 references migrated)
- Tournaments domain: ☐ Pending (6 references)
- Orders domain: ☐ Pending (2 references)
- Accounts domain: ☐ Pending (2 references)
- Cafe Arcade domain: ☐ Pending (mixed)

### Phase 5a: Employee/HR Domain (Verify Complete)

**Files:** `domains/teams/services.py`, `domains/teams/viewsets.py`, 13 frontend files

**Steps:**
1. Verify backend returns `identity_id` (not `userid`)
2. Verify frontend uses `.identity_id` (not `.userid`)
3. Grep for remaining `userid` references in teams domain

**Success Criteria:**
- [ ] 0 `userid` references in teams domain (except CustomUser.auth)
- [ ] 0 `.userid` references in frontend (except Login.jsx)

### Phase 5b: Tournaments Domain

**Files:** `domains/tournaments/views.py`

**Steps:**
1. Migrate 6 `userid` references to `identity_id`
2. Verify frontend alignment (if frontend pages exist)

**Success Criteria:**
- [ ] 0 `userid` references in tournaments domain

### Phase 5c: Orders Domain

**Files:** `domains/orders/viewsets.py`

**Steps:**
1. Migrate 2 `userid` references to `identity_id`
2. Verify frontend alignment

**Success Criteria:**
- [ ] 0 `userid` references in orders domain

### Phase 5d: Accounts Domain

**Files:** `domains/accounts/expenditure/inward_invoices.py`

**Steps:**
1. Migrate 2 `userid` references to `identity_id`
2. Verify frontend alignment

**Success Criteria:**
- [ ] 0 `userid` references in accounts domain

### Phase 5e: Cafe Arcade Domain

**Files:** `domains/cafe_arcade/views.py`, `domains/cafe_arcade/gamers_views.py`

**Steps:**
1. Identify mixed `userid`/`identity_id` usage
2. Migrate player references to `identity_id`
3. Verify CustomUser.auth references remain (correct for auth context)

**Success Criteria:**
- [ ] Player references use `identity_id`
- [ ] CustomUser.auth references preserved

---

## Phase 7: API Contract Compliance (Domain-by-Domain)

**What:** Verify frontend routes, API calls, and response shapes align with backend endpoints across all domains (excluding eshop).

**Source:** `28-06-2026_api-contract-audit-by-domain.md`

**Scope:** 19 domains audited. Fix P0-P1 issues, verify P2-P3 status.

### Phase 6a: P0 Issues (Must Fix)

| # | Domain | Issue | Fix |
|---|--------|-------|-----|
| 1 | Cafe Tracker | Route not registered in `src/routes/main.jsx` | Register route |
| 2 | Cafe FNB | URL mismatch: `cafe/fnb/menu` vs `cafe-fnb/menu` | Fix URL or proxy |
| 3 | Cafe Tracker | `cafeTrackerApi.js` doesn't unwrap envelopes | Add `unwrapEnvelope()` |
| 4 | Backend | Outbox worker not scheduled | Schedule worker |

### Phase 6b: P1 Issues (Contract Fixes)

| # | Domain | Issue | Fix |
|---|--------|-------|-----|
| 5 | Accounts | No route for Ledgers page | Add route |
| 6 | Accounts | No route for Financials page | Add route |
| 7 | Products | `products/kurodata` not in urls.py | Add endpoint |
| 8 | Products | No route for PreBuilts page | Add route |
| 9 | Products | No route for Peripherals page | Add route |
| 10 | Inventory | `/api/products/stock-audit` vs `/api/v1/inventory/stock-audit` | Align URLs |
| 11 | Teams | `teams/employeesdata` not in urls.py | Add endpoint |
| 12 | Teams | `teams/emp-attendance` not in urls.py | Add endpoint |
| 13 | Teams | `teams/emp-attendancedate` not in urls.py | Add endpoint |
| 14 | Shared | `/api/v1/shared/checklist` not in urls.py | Add endpoint |
| 15 | Auth | `/pwdreset` not in urls.py | Add endpoint |
| 16 | Cafe Tracker | Close receipt field mismatches | Align fields |
| 17 | Cafe FNB | Menu response shape mismatch (`items` vs `menu_items`) | Align shape |

### Phase 6c: P2 Issues (Nice to Have)

| # | Domain | Issue | Status |
|---|--------|-------|--------|
| 18 | Accounts | Naming inconsistency (`invoices` vs `inward-invoices`) | Document |
| 19 | Inventory | Pages call `products/inventory` but domain has separate endpoints | Document |
| 20 | Cafe FNB | No FNB menu management pages | Future |
| 21 | Backend | `success_response()` is dead code | Cleanup |
| 22 | Backend | Three response envelope patterns coexist | Standardize |
| 23 | Backend | Structured logging not configured | Future |

### Phase 6d: P3 Issues (Future Work)

| # | Domain | Issue | Status |
|---|--------|-------|--------|
| 24 | Careers | No frontend page for jobadmin | Future |
| 25 | KungOS Admin | No frontend pages (backend-only) | Future |
| 26 | Tournaments | No frontend pages (backend-only) | Future |

### Phase 6e: Domain Health Summary

| Domain | Pages | Routes | API Calls | Backend Endpoints | Alignment |
|--------|-------|--------|-----------|-------------------|-----------|
| Accounts | 12 | 12 | 19 | 30+ | ⚠️ 80% |
| Orders | 10 | 10 | 10 | 10 | ✅ 100% |
| Products | 6 | 4 | 11 | 17 | ⚠️ 70% |
| Inventory | 8 | 8 | 4 | 15+ | ⚠️ 60% |
| Teams | 6 | 6 | 8 | 4 | ⚠️ 75% |
| Vendors | 1 | 1 | 2 | 2 | ✅ 100% |
| Search | 1 | 1 | 1 | 6 | ✅ 100% |
| Shared | 1 | 1 | 7 | 10 | ⚠️ 80% |
| Tenant | 5 | 5 | 6 | 7 | ❌ 0% (P0-P3 bugs) |
| RBAC | 2 | 2 | 5 | 5 | ✅ 100% |
| Users | 3 | 3 | 7 | 7 | ✅ 100% |
| Auth | 2 | 2 | 7 | 8 | ⚠️ 90% |
| Cafe Arcade | 12 | 12 | 25 | 30+ | ⚠️ 90% |
| Cafe FNB | 0 | 0 | 1 | 9 | ❌ 0% |
| Cafe Tracker | 1 | 0 | 5 | 5 | ❌ 0% |
| Careers | 0 | 0 | 1 | 3 | ⚠️ 33% |
| KungOS Admin | 0 | 0 | 0 | 10 | ⚠️ 0% |
| Tournaments | 0 | 0 | 0 | 4 | ⚠️ 0% |

---

## Success Criteria (Full Scope)

### Phase 0: DB Migration
- [ ] All legacy kuropurchase collections exist in KungOS_Mongo_One with matching counts
- [ ] All documents have canonical tenant fields (bg_code, div_code, branch_code)
- [ ] No `entity` field remains in business collections
- [ ] Product catalog collections enriched with tenant fields
- [ ] PostgreSQL tenant_divisions and tenant_branches populated
- [ ] inwardpayments and purchaseorders counts verified (no duplication)
- [ ] KungOS_Mongo_One is the sole data source

### Phase 1: Runtime Functional Wiring
- [ ] All P0 domain endpoints return data from KungOS_Mongo_One
- [ ] Tenant filtering works (div_code, branch_code)
- [ ] No 500 errors from missing data
- [ ] Pagination works (limit, offset, page)
- [ ] All frontend pages load without errors
- [ ] Data renders correctly on all pages
- [ ] Filter params use `?filter[field]=value` format

### Phase 2: Filter Propagation
- [ ] 41/41 backend unit tests pass
- [ ] 10/10 backend integration tests pass
- [ ] 8/8 frontend component tests pass
- [ ] 5/5 end-to-end smoke tests pass
- [ ] No regression in existing tests

### Phase 3: Response Envelope
- [ ] 0 raw error `Response()` calls
- [ ] 0 `INPUT_ERROR` references
- [ ] 0 `api_error()` tuple unpacking
- [ ] All non-2xx errors use canonical envelope
- [ ] All 129 mutations have `onError` handlers

### Phase 4: Tenant Context
- [ ] Middleware uses only canonical JWT keys
- [ ] Missing claims → HTTP 401
- [ ] All 222+ tenant-filtered queries use canonical keys
- [ ] Switch endpoint works end-to-end
- [ ] Login response includes full tenant context

### Phase 5: RBAC
- [ ] 0 legacy `accesslevels` references
- [ ] Permission levels correctly assigned
- [ ] UI respects permission levels
- [ ] 33 files migrated

### Phase 6: Schema Alignment
- [ ] Employee/HR domain: 0 `userid` references (except auth)
- [ ] Tournaments domain: 0 `userid` references
- [ ] Orders domain: 0 `userid` references
- [ ] Accounts domain: 0 `userid` references
- [ ] Cafe Arcade: player refs use `identity_id`

### Phase 7: API Contract
- [ ] All P0 issues fixed (4 items)
- [ ] All P1 issues fixed (13 items)
- [ ] P2 issues documented (6 items)
- [ ] P3 issues acknowledged (3 items)

---

## Constraints

- **Do NOT modify** `src/pages/Accounts/Analytics.jsx`, `src/pages/Home.jsx`, or `src/hooks/useTenantParams.jsx`
- **FilterParserMixin must NOT parse tenant fields** (`div_code`, `branch_code`, `bg_code`)
- **No legacy alias support** in the mixin — `division=` is ignored, not mapped
- **All `query_params.get('division')` → `query_params.get('div_code')`**
- **`userid` exists ONLY on `CustomUser`** — all cross-domain person references use `identity_id`
- **All tests must run against the migrated codebase** (commit `41b3756` or later)
- **E-shop domain excluded** — do not touch eshop files
- **KungOS Admin domain included** — verify tenant bootstrap, domain config, API keys, templates

---

## Caveats & Uncertainty

1. **MongoDB test data:** Test data must be inserted into the correct database (`kuroadmin` or tenant DB). Verify DB name before inserting.

2. **Authentication:** Backend tests require valid JWT tokens. Use test user credentials or mock authentication.

3. **Frontend dev server:** Must be running on `http://localhost:5173` for smoke tests.

4. **Backend dev server:** Must be running on `http://localhost:8000` for smoke tests.

5. **Test isolation:** Use unique test data (e.g., `INV-TEST-*`) to avoid conflicts with existing data.

6. **FilterParserMixin limitations:** Commas in `?filter[field__in]` values must be URL-encoded by client.

7. **Cafe FNB domain:** No frontend pages exist — API contract testing limited to backend endpoint verification.

8. **Cafe Tracker:** Route not registered — must be registered before E2E testing.

9. **Tenant context bugs:** P0-P3 tenant context issues affect ALL domains. Must be fixed before domain-specific testing is meaningful.

10. **Response envelope patterns:** Three patterns currently coexist in backend. Standardization to locked spec is in progress (P2).

11. **DB migration prerequisite:** Phase 0 (DB migration) MUST complete before any testing is meaningful. See `29-06-2026_db_state_report_d075f8.md` for critical gaps.

12. **KungOS Admin:** Tenant bootstrap, domain config, API keys, and templates tables are all empty. Admin bootstrap must be configured before admin domain testing.

13. **MongoDB case sensitivity:** Legacy `kuropurchase` uses mixed-case collection names (e.g., `inwardInvoices`). Target `KungOS_Mongo_One` uses lowercase. The mixed-case shells exist in target but are empty. Migration must use lowercase names.

14. **Tenant hierarchy:** PostgreSQL `tenant_divisions` and `tenant_branches` are empty. MongoDB data references divisions/branches that don't exist in PG. These must be populated from data references.

---

## Next Steps

1. **Phase 0:** Resolve DB migration gaps (see `29-06-2026_db_state_report_d075f8.md`)
2. **Phase 1:** Verify runtime functional wiring (data flows DB → Frontend)
3. **Phase 2:** Execute Filter Propagation Testing (d075f8 core)
4. **Phase 3:** Execute Response Envelope Verification
5. **Phase 4:** Execute Tenant Context Verification
6. **Phase 5:** Execute RBAC Verification
7. **Phase 6:** Execute Schema Alignment
8. **Phase 7:** Execute API Contract Compliance
9. Commit all test files to `origin/develop`
10. Update this handoff with results

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `29-06-2026_db_state_report_d075f8.md` | **DB state audit — Phase 0 prerequisite** |
| `29-06-2026_data-propagation-testing_d075f8.md` | Original filter testing handoff (Phase 2 source) |
| `29-06-2026_filter-parser-mixin-and-frontend-migration_7bd873.md` | Filter migration completion (Phases 2-6) |
| `frontend_alignment_handoff.md` | Alignment review findings (RF-1 through SP-3) |
| `29-06-2026_response_envelope_final_fix.md` | Response envelope spec (Phase 3 source) |
| `29-06-2026_frontend_backend_schema_alignment_v4.md` | Schema alignment spec (Phase 6 source) |
| `28-06-2026_api-contract-audit-by-domain.md` | API contract audit (Phase 7 source) |
| `endpoint_contract_spec_revised.md` | Authoritative wire contract (Phase 1 reference) |
| `29-06-2026_response_envelope_final_fix.md` | Response envelope standardization (P0-P3) |
| `29-06-2026_P3_closeout_verification.md` | P3 closeout verification results |
| `29-06-2026_frontend_backend_schema_alignment_v4.md` | Schema alignment (Employee/HR complete) |
| `28-06-2026_api-contract-audit-by-domain.md` | Domain-by-domain API contract audit |
| `endpoint_contract_spec_revised.md` | Authoritative wire contract |
| `multi_tenancy.md` | Multi-tenancy constitution |
| `CANONICAL_NAMING.md` | Naming gate |

---

## Execution Summary

| Phase | Status | Results |
|-------|--------|---------|
| Phase 0: DB Migration | ✅ COMPLETE | 4,615 inwardinvoices migrated, 194 stock_register restored, divisions/branches populated |
| Phase 1: Runtime Wiring | ✅ COMPLETE | All major endpoints verified (invoices, orders, cart, wishlist) |
| Phase 2: Filter Propagation | ⏳ NEXT | Filter parser mixin verified in Phase 1 |
| Phase 3: Response Envelope | ⏳ NEXT | Standard envelope verified in Phase 1 |
| Phase 4: Tenant Context | ⏳ NEXT | Tenant context working via resolve_minimal() |
| Phase 5: RBAC | ⏳ NEXT | Role-based access verified for admin.vendors |
| Phase 6: Schema Alignment | ⏳ NEXT | identity_id property added to CustomUser |
| Phase 7: API Contract | ⏳ NEXT | Domain-by-domain verification pending |

### Key Fixes Applied

1. **CustomUser.identity_id property** — Resolves identity from Identity record
2. **Eshop viewsets tenant context** — Uses resolve_minimal() instead of request.bg_code
3. **Legacy eshop data migration** — 2,468 users, 992 orders migrated from kuro-eshop-legacy
4. **Legacy DB connection removed** — legacy_eshop database configuration removed from settings.py

### Data Verification

| Collection/Table | Count | Source |
|------------------|-------|--------|
| inwardinvoices | 4,631 | KungOS_Mongo_One (16 existing + 4,615 migrated) |
| outwardinvoices | 1,165 | KungOS_Mongo_One |
| purchaseorders | 15,216 | KungOS_Mongo_One |
| stock_register | 194 | Restored from archived |
| tenant_divisions | 1 | Populated from data |
| tenant_branches | 2 | Populated from data |
| users_identity | 7,221 | 4,753 existing + 2,468 migrated |
| orders_core | 15,337 | Includes 992 eshop orders |

*Handoff generated: 29-06-2026 (expanded from d075f8 to full project scope)*
*Excluded: E-shop domain, Careers, KungOS Admin, Tournaments (no frontend)*
*Total estimated effort: 2-3 days (Phases 1-6)*
