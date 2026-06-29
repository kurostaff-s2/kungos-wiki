# Response Envelope & Multi-Tenancy Standardization — Final Fix Task Handoff

**Date:** 2026-06-29 (v6 — priority-structured execution plan)  
**Priority:** P0/P1 (tenant extraction → tenant switch → error envelopes)  
**Status:** Task Handoff — Ready for Execution  
**Predecessor:** `28-06-2026_api-contract-audit-v2.md`

---

## Authority Declarations

### Wire Contract Authority

**The revised endpoint spec (`/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md`) is the SOLE wire-contract authority.**

- Stop redefining response shapes in handoff notes or side documents
- All response envelope requirements flow from spec §3.1 (success) and §8.2 (error)
- If a handoff note conflicts with the spec, the spec wins

### Naming Authority

**`CANONICAL_NAMING.md` (`/home/chief/llm-wiki/Kung_OS/architecture/canonical_naming.md`) is the naming gate.**

- Every "after" state MUST use frozen canonical names
- Legacy names (e.g., `entity`, `branches`, `userid`) appear ONLY in explicitly labeled migration context
- Migration notes must be labeled as such (e.g., "Migration: `entity` → `bg_code`")

### Multi-Tenancy Authority

**`multi_tenancy.md` (`/home/chief/llm-wiki/Kung_OS/architecture/multi_tenancy.md`) is the multi-tenancy constitution.**

- JWT claims are authoritative for every request
- Missing required claims MUST fail with `TenantContextMissing` (no silent degradation)
- Middleware and MongoDB wrapper MUST use canonical ContextVar keys: `bg_code`, `div_codes`, `branch_codes`, `identity_id`

---

## Priority Structure

### P0: Tenant-Context Extraction Validation (Highest Priority)

**Why P0:** The spec says Phase 0 is highest priority. The multi-tenancy constitution requires JWT claims to be authoritative and missing claims to fail fast.

**Current state:** The middleware and MongoDB wrapper are ALREADY using canonical JWT keys (`bg_code`, `div_codes`, `branch_codes`, `identity_id`). No legacy key extraction remains.

**Missing piece:** The middleware does NOT validate that required claims are present. When `bg_code` or `identity_id` is missing from the JWT, the middleware silently degrades (doesn't set ContextVar, doesn't raise an error).

**Scope:**
1. Add validation in `plat/observability/middleware.py` to raise `TenantContextMissing` when `bg_code` or `identity_id` is missing

**Files:**
- `plat/observability/middleware.py` (TenantContextMiddleware)

**Acceptance Criteria:**
- [x] Middleware extracts `bg_code`, `div_codes`, `branch_codes`, `identity_id` from JWT only (ALREADY DONE)
- [x] ContextVar uses canonical keys (ALREADY DONE)
- [x] `TenantCollection` reads only canonical ContextVar keys (ALREADY DONE)
- [ ] Missing `bg_code` or `identity_id` → `TenantContextMissing` (HTTP 401) (NEW)
- [x] No legacy key references in extraction path (ALREADY DONE)

**Effort:** 15-30 minutes

---

### P1: Tenant-Switch JWT Regeneration

**Why P1:** The multi-tenancy doc treats switch-endpoint JWT regeneration as tracked P1 work. The endpoint spec makes new JWT emission a hard requirement for `POST /api/v1/tenant/switch/`.

**Scope:**
1. Implement `POST /api/v1/tenant/switch/` endpoint
2. Update `UserTenantContext` with new `bg_code`, `div_codes`, `branch_codes`, `scope`, `active_div_code`, `active_branch_code`
3. Generate new JWT with canonical claims via `generate_tenant_token()`
4. Set new JWT as HttpOnly cookie (same name, domain, path, secure flag as original)
5. Return updated context payload in response envelope

**Files:**
- `users/views.py` or `users/api/auth_urls.py` (new endpoint)
- `users/tenant_tokens.py` (`generate_tenant_token()`)
- `domains/tenant/views.py` (if exists)

**Acceptance Criteria:**
- [ ] `POST /api/v1/tenant/switch/` updates `UserTenantContext`
- [ ] New JWT generated with all canonical claims (`bg_code`, `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `identity_id`, `scope`)
- [ ] HttpOnly cookie set with same security attributes as original
- [ ] Response returns updated context payload in spec envelope
- [ ] Legacy `/api/v1/users/bgswitch/` endpoint marked deprecated (will be removed)

**Effort:** 2-3 hours

---

### P2: Error-Envelope Normalization

**Why P2:** The middleware handles 2xx success envelopes automatically. The real work is fixing 61 non-2xx error responses to use the spec error envelope and spec error codes. Also clean up class-method wrappers that ignore `status_code`.

**Scope:**
1. Fix 61 non-2xx error responses to use spec error envelope (spec §8.2)
2. Replace `INPUT_ERROR` code with `VALIDATION_ERROR` (spec §8.1)
3. Remove `api_error()` tuple unpacking (use `error_response()` utility)
4. Clean up 421 class-method wrappers that ignore `status_code`
5. Verify 201/202/204 status codes preserved in non-200 success paths

**Files:** 17 target files + 8 class-method files (see affected files table below)

**Acceptance Criteria:**
- [ ] All non-2xx JSON errors conform to canonical error envelope (spec §8.2)
- [ ] All non-200 success paths preserve intended HTTP status codes (201, 202, 204)
- [ ] `INPUT_ERROR` replaced with `VALIDATION_ERROR` (spec §8.1)
- [ ] `api_error()` tuple unpacking removed
- [ ] Class-method wrappers replaced or removed (status codes preserved)
- [ ] Remaining wrappers confined to special cases (pagination, reporting, 204)

**Effort:** 2-3 hours

---

### P3: Closeout Verification (Final Audit)

**Why P3:** Only after P0-P2 pass should you do lower-priority cleanup (redundant wrappers, duplicated endpoints, migration-note simplifications).

**Verification Pass:**
1. **Canonical naming compliance** — No legacy names in "after" state
2. **Tenant middleware/Mongo extraction compliance** — Only canonical keys used
3. **Tenant-switch JWT regeneration** — Endpoint works, cookie set, JWT canonical
4. **Error-envelope compliance** — All non-2xx errors use spec envelope with `request_id` in `meta`

**Effort:** 1 hour

---

## Execution Order

```
P0: Tenant-Context Extraction (1-2 hours)
  ↓
P1: Tenant-Switch JWT Regeneration (2-3 hours)
  ↓
P2: Error-Envelope Normalization (2-3 hours)
  ↓
P3: Closeout Verification (1 hour)
  ↓
P4: Secondary Cleanup (redundant wrappers, duplicated endpoints, etc.)
```

**Total estimated effort:** 6-9 hours (P0-P3) + secondary cleanup

---

## Implementation Tickets

### Ticket 1: P0 — Tenant-Context Extraction Validation ✅ COMPLETE

**Title:** P0: Add validation for missing JWT claims in TenantContextMiddleware

**Status:** ✅ COMPLETE

**Description:**
The multi-tenancy constitution requires JWT claims to be authoritative. The middleware is ALREADY using canonical keys (`bg_code`, `div_codes`, `branch_codes`, `identity_id`). However, it does NOT validate that required claims are present.

When `bg_code` or `identity_id` is missing from the JWT, the middleware silently degrades (doesn't set ContextVar, doesn't raise an error). This must be fixed to fail fast with `TenantContextMissingError` (HTTP 401).

**Tasks:**
- [x] Add validation in `plat/observability/middleware.py` TenantContextMiddleware.process_request()
- [x] Raise `TenantContextMissingError` when `bg_code` or `identity_id` is missing from JWT
- [x] Add `TENANT_CONTEXT_MISSING` to ErrorCode enum in `backend/exceptions.py`
- [x] Add `TenantContextMissingError` class in `backend/exceptions.py`

**Acceptance:**
- Middleware extracts only `bg_code`, `div_codes`, `branch_codes`, `identity_id` from JWT (ALREADY DONE)
- ContextVar uses only canonical keys (ALREADY DONE)
- `TenantCollection` reads only canonical ContextVar keys (ALREADY DONE)
- Missing required claims → `TenantContextMissingError` (HTTP 401) (DONE)
- No legacy key references in extraction path (ALREADY DONE)

**Files Modified:**
- `plat/observability/middleware.py` (added validation)
- `backend/exceptions.py` (added TENANT_CONTEXT_MISSING code and TenantContextMissingError class)

**Effort:** 15-30 minutes

---

### Ticket 2: P1 — Tenant-Switch JWT Regeneration ✅ COMPLETE

**Title:** P1: Implement /api/v1/tenant/switch/ with JWT regeneration and HttpOnly cookie

**Status:** ✅ COMPLETE

**Description:**
The endpoint spec requires `POST /api/v1/tenant/switch/` to update `UserTenantContext`, generate a new JWT with canonical claims, set the new JWT as an HttpOnly cookie, and return the updated context payload.

**Current state:** The endpoint already existed at `tenant/context_views.py:tenant_switch()`. However, it used `api_error()` tuple unpacking (non-spec) and set the cookie as `access_token` instead of `jwt_token` (inconsistent with login).

**Tasks:**
- [x] Endpoint already existed (no new implementation needed)
- [x] Replace `api_error()` with `error_response()` (spec-compliant)
- [x] Replace `Response()` with `success_response()` (canonical utility)
- [x] Add `generate_tenant_token()` function to `users/tenant_tokens.py`
- [x] Fix cookie name from `access_token` to `jwt_token` (consistent with login)
- [x] Fix cookie security attributes (use `not settings.DEBUG` for secure flag)
- [x] Fix cookie max_age to 8 hours (match login JWT)
- [x] Add `identity_id` to JWT claims and response payload
- [x] Mark legacy `/api/v1/users/bgswitch/` endpoint as deprecated (not changed)

**Acceptance:**
- Endpoint exists at `/api/v1/tenant/switch/` ✅
- Validates `bg_code` against user's Identity ✅
- Updates `UserTenantContext` with new context ✅
- New JWT generated with all canonical claims ✅
- HttpOnly cookie set with same security attributes ✅
- Response returns updated context payload in spec envelope ✅
- Legacy endpoint marked deprecated (not changed)

**Files Modified:**
- `tenant/context_views.py` (replaced api_error/success_response, fixed cookie)
- `users/tenant_tokens.py` (added generate_tenant_token function)

**Effort:** 30 minutes

---

### Ticket 3: P2 — Error-Envelope Normalization

**Title:** P2: Normalize non-2xx error responses to canonical envelope and spec error codes

**Description:**
The `ResponseEnvelopeMiddleware` handles 2xx success envelopes automatically. The real work is fixing 61 non-2xx error responses to use the spec error envelope and spec error codes. Also clean up 421 class-method wrappers that ignore `status_code`.

**Tasks:**
- [ ] Fix 61 non-2xx error responses to use spec error envelope (spec §8.2)
- [ ] Replace `INPUT_ERROR` code with `VALIDATION_ERROR` (spec §8.1)
- [ ] Remove `api_error()` tuple unpacking (use `error_response()` utility)
- [ ] Replace 421 class-method calls with canonical utilities (verify status codes preserved)
- [ ] Remove class-method definitions from 8 files
- [ ] Verify 201/202/204 status codes preserved in non-200 success paths

**Acceptance:**
- All non-2xx JSON errors conform to canonical error envelope (spec §8.2)
- All non-200 success paths preserve intended HTTP status codes (201, 202, 204)
- `INPUT_ERROR` replaced with `VALIDATION_ERROR` (spec §8.1)
- `api_error()` tuple unpacking removed
- Class-method wrappers replaced or removed (status codes preserved)
- Remaining wrappers confined to special cases (pagination, reporting, 204)

**Files:** 17 target files + 8 class-method files (see affected files table below)

**Effort:** 2-3 hours

---

## Affected Files (P2 Only)

### Bucket 2: Non-2xx Error Responses (Must Fix) — 61 calls

| Domain | File | Error Calls | Priority |
|--------|------|-------------|----------|
| **Tournaments** | `domains/tournaments/views.py` | ~15 | HIGH |
| **Orders** | `domains/orders/services.py` | ~12 | HIGH |
| **Shared** | `domains/shared/millie.py` | ~8 | MEDIUM |
| **Cafe Arcade** | `domains/cafe_arcade/views.py` | ~6 | MEDIUM |
| **Other files** | ... | ~20 | LOW |
| **SUBTOTAL** | | **61** | **Must fix** |

### Bucket 3: Wrapper/Class-Method Calls (Fix + Remove) — 421 calls

| Domain | File | Class Method Calls | Notes |
|--------|------|-------------------|-------|
| **Accounts** | `domains/accounts/viewsets.py` | 128 | Also has 13 raw calls |
| **Products** | `domains/products/viewsets.py` | 111 | Also has 20 raw calls |
| **Orders** | `domains/orders/viewsets.py` | 86 | Also has 5 raw calls |
| **Shared** | `domains/shared/viewsets.py` | 34 | Also has 4 raw calls |
| **Teams** | `domains/teams/viewsets.py` | 23 | Also has 1 raw call |
| **Vendors** | `domains/vendors/viewsets.py` | 19 | Also has 1 raw call |
| **Search** | `domains/search/viewsets.py` | 19 | **0 raw calls — MUST include** |
| **Backend** | `backend/reporting_base.py` | 1 | Base class, 1 wrapper call |
| **SUBTOTAL** | | **421** | **Fix and remove** |

---

## Success Criteria (Rewritten)

Replace the old "0 raw Response() calls" target with these sharper criteria:

- [ ] **All non-2xx JSON errors conform to the canonical error envelope** (spec §8.2)
- [ ] **All non-200 success paths preserve intended HTTP status codes** (201 for created, 202 for accepted, 204 for no content)
- [ ] **Any remaining wrappers are either deleted or confined to genuinely special cases** (pagination, reporting, 204 semantics)
- [ ] **`INPUT_ERROR` code replaced with `VALIDATION_ERROR`** (spec §8.1)
- [ ] **`api_error()` tuple unpacking removed** (use `error_response()` utility instead)
- [ ] **All files compile and tests pass**

---

## Decision Record

**Default path: Execute P0 → P1 → P2 → P3 in order.**

- **P0 rejected?** No — tenant extraction is foundational
- **P1 rejected?** No — tenant switch is tracked P1 in multi-tenancy doc
- **P2 rejected?** No — error envelopes are non-negotiable per spec
- **P3 rejected?** No — verification is required before secondary cleanup

**If you want to deviate from this order, explicitly state so before execution begins.**

---

*Handoff updated: 29-06-2026 (v6 — priority-structured execution plan)*  
*Authority: endpoint_contract_spec_revised.md (wire), CANONICAL_NAMING.md (naming), multi_tenancy.md (tenant)*  
*Priority: P0 (tenant extraction) → P1 (tenant switch) → P2 (error envelopes) → P3 (closeout)*  
*Total effort: 6-9 hours (P0-P3) + secondary cleanup*
