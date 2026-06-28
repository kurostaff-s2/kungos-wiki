# Tenant Context Refactoring — Execution Prompt

**Generated:** 2026-06-28  
**Foundation:** Locked specs — `multi_tenancy_revised.md`, `endpoint_contract_spec_revised.md`, `CANONICAL_NAMING.md`  
**Predecessor:** `28-06-2026_tenant-context-audit_a72921.md` (audit findings)  
**Priority:** P0 — Middleware extraction bug breaks all tenant isolation  
**Estimated effort:** 6–8 hours (P0: 1.5h, P1: 3h, P2: 1.5h, P3: 1h, Testing: 1h)

---

## Execution Order

1. **P0: Fix middleware + MongoDB wrapper** (1.5 hours) — Restore tenant isolation
2. **P1: Fix switch endpoint + frontend sync** (3 hours) — Spec compliance
3. **P2: Fix correctness issues** (1.5 hours) — Align frontend/backend
4. **P3: Cleanup** (1 hour) — Remove legacy code, dead code
5. **Verification** (1 hour) — Run full test suite, manual verification

---

## Foundational Principles (All Phases Must Comply)

Per `multi_tenancy_revised.md` and `endpoint_contract_spec_revised.md`:

1. **JWT is authoritative source** — Every request-time tenant context MUST come from JWT claims: `bg_code`, `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `identity_id`, `scope`
2. **Middleware extraction contract** — MUST use canonical claim names (not legacy `entity`, `branches`, `userid`)
3. **TenantCollection extraction contract** — MUST use canonical ContextVar keys (`div_codes`, `branch_codes`)
4. **Switch endpoint MUST emit JWT** — Must call `generate_tenant_token()` after updating `UserTenantContext`
5. **Frontend MUST call backend on switch** — Local-only switching causes state drift and cross-tenant data leakage
6. **Login response MUST include full context** — `div_codes`, `branch_codes`, `scope` are mandatory fields
7. **Active-context convention** — `div_codes[0]` is always the active division, `branch_codes[0]` is always the active branch. `active_div_code` and `active_branch_code` are explicit aliases that MUST always equal `div_codes[0]` and `branch_codes[0]` respectively.
8. **Refresh token delivery** — Delivered ONLY as HttpOnly cookie — not in JSON body (prevents XSS exposure)
9. **Public/HMAC exceptions** — Public catalog endpoints (no auth) and HMAC webhooks (signature verification) are explicit exceptions to JWT authority rule. Webhook tenant-resolution: After HMAC verification, tenant context resolved from payment/order record in payload, NOT from `request.auth`.
10. **Canonical naming** — `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `identity_id`, `bg_code` (not `entity`, `branches`, `userid`, `division`)

---

## Phase 1: P0 — Restore Tenant Isolation (1.5 hours)

### 1A. Fix Middleware Field Names

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/plat/observability/middleware.py`  
**Method:** `TenantContextMiddleware.process_request()` (lines 50–80)

**Current state (BROKEN):**
```python
div_codes = token.get("entity", [])           # ❌ "entity" doesn't exist in JWT
branch_codes = token.get("branches", [])      # ❌ "branches" doesn't exist in JWT
identity_id = token.get("userid", "")         # ❌ legacy name (canonical: identity_id)
```

**Required state (LOCKED):**
```python
# Multi-tenancy Constitution §Middleware Extraction Contract
div_codes = token.get("div_codes", [])
branch_codes = token.get("branch_codes", [])
identity_id = token.get("identity_id", "")
bg_code = token.get("bg_code", "")
active_div_code = token.get("active_div_code", "")
active_branch_code = token.get("active_branch_code", "")
scope = token.get("scope", "full")
```

**Change:**
1. Replace `token.get("entity", [])` → `token.get("div_codes", [])`
2. Replace `token.get("branches", [])` → `token.get("branch_codes", [])`
3. Replace `token.get("userid", "")` → `token.get("identity_id", "")`
4. Add extraction of `bg_code`, `active_div_code`, `active_branch_code`, `scope` (currently missing)
5. Update session variable names to match `multi_tenancy_revised.md` §Session Variables:
   - `app.current_bg_code` = `bg_code`
   - `app.current_division` = `active_div_code`
   - `app.current_branch` = `active_branch_code`
   - `app.current_userid` = `identity_id`

**Verification:**
- [ ] ContextVar contains non-empty `div_codes`, `branch_codes`, `identity_id` after login
- [ ] RLS session variables set to correct values (not empty strings)
- [ ] All downstream consumers inherit correct context

---

### 1B. Fix MongoDB Wrapper Field Names

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/plat/tenant/collection.py`  
**Method:** `TenantCollection` (lines 40–70)

**Current state (BROKEN):**
```python
div_codes = ctx.get("entity", [])           # ❌ legacy key
branch_codes = ctx.get("branches", [])      # ❌ legacy key
```

**Required state (LOCKED):**
```python
# Multi-tenancy Constitution §TenantCollection Extraction Contract
div_codes = ctx.get("div_codes", [])
branch_codes = ctx.get("branch_codes", [])
```

**Change:**
1. Replace `ctx.get("entity", [])` → `ctx.get("div_codes", [])`
2. Replace `ctx.get("branches", [])` → `ctx.get("branch_codes", [])`

**Verification:**
- [ ] MongoDB queries include `bg_code` filter
- [ ] MongoDB queries include `div_code` filter (for division-scoped queries)
- [ ] No cross-tenant data leakage in test data

---

## Phase 2: P1 — Spec Compliance (3 hours)

### 2A. Add JWT Emission to Switch Endpoint

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/tenant/context_views.py`  
**Method:** `TenantContextViewSet.switch()` (lines 66–120)

**Current state (BROKEN):**
```python
# Updates UserTenantContext DB row
UserTenantContext.objects.update_or_create(
    userid=identity_id,
    bg_code=request_data.get("bg_code"),
    # ... updates div_codes, branch_codes, scope, etc.
)
# Returns permissions — does NOT generate new JWT
return Response({"permissions": permissions})
```

**Required state (LOCKED):**
```python
# endpoint_contract_spec_revised.md §5.3 Tenant Switching — JWT Emission Requirement
# 1. Validate requested bg_code against user's Identity
# 2. Update UserTenantContext with new context
# 3. Generate NEW JWT with updated canonical claims
# 4. Set new JWT as HttpOnly cookie
# 5. Return response envelope with updated context data

from users.tenant_tokens import generate_tenant_token

# Update UserTenantContext
UserTenantContext.objects.update_or_create(
    userid=identity_id,
    defaults={
        "bg_code": request_data["bg_code"],
        "div_codes": request_data["div_codes"],
        "branch_codes": request_data["branch_codes"],
        "active_div_code": request_data["active_div_code"],
        "active_branch_code": request_data["active_branch_code"],
        "scope": request_data["scope"],
    }
)

# Generate NEW JWT
jwt_payload = generate_tenant_token(identity_id, bg_code, div_codes, branch_codes, 
                                     active_div_code, active_branch_code, scope)
response = Response({"status": "success", "data": updated_context})
response.set_cookie("access_token", jwt_payload["access_token"], httponly=True, ...)
return response
```

**Change:**
1. Import `generate_tenant_token` from `users.tenant_tokens`
2. After `update_or_create`, call `generate_tenant_token()` with updated context
3. Set new JWT as HttpOnly cookie (same cookie name as original)
4. Return response with updated context data (not just permissions)

**Verification:**
- [ ] New JWT contains updated `bg_code`, `div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`, `scope`
- [ ] Cookie is set with correct attributes (HttpOnly, same domain/path)
- [ ] Subsequent API calls use new JWT with updated tenant context

---

### 2B. Wire Frontend to Call `/tenant/switch/`

**File:** `/home/chief/Coding-Projects/kteam-fe-chief/src/components/layout/TenantSelector.jsx`  
**Methods:** `handleBgSelect`, `handleDivSelect`, `handleBranchSelect`

**Current state (BROKEN):**
```javascript
// TenantContext.jsx — Legacy state variables (singular, camelCase)
const [bgCode, setBgCodeState] = useState(...);
const [division, setDivisionState] = useState(...);  // ❌ Singular string, not array
const [branch, setBranchState] = useState(...);      // ❌ Singular string, not array

// TenantSelector.jsx — Local-only switching
const handleBgSelect = (bgCode) => {
    setBgCodeState(bgCode);
    localStorage.setItem('bg-code', bgCode);
    onSwitchTenant?.(bgCode);  // Just calls parent callback
    // ❌ No API call to /tenant/switch/
};
```

**Required state (LOCKED):**
```javascript
// endpoint_contract_spec_revised.md §5.4 Frontend Tenant Switching Contract
// 1. Call POST /api/v1/tenant/switch/
// 2. Include new context in request body
// 3. Process new JWT cookie from response
// 4. Update local state with response data
// 5. NOT switch via local state alone

// Clean break: Remove legacy state, use only canonical state
const [divCodes, setDivCodes] = useState([]);        // Array of division codes
const [branchCodes, setBranchCodes] = useState([]);  // Array of branch codes
const [activeDivCode, setActiveDivCode] = useState('');
const [activeBranchCode, setActiveBranchCode] = useState(null);
const [scope, setScope] = useState('full');

const handleBgSelect = async (bgCode) => {
    try {
        // Call backend switch endpoint
        const response = await api.post('/tenant/switch/', {
            bg_code: bgCode,
            active_div_code: bgCode + '_001',  // Default first division
            active_branch_code: bgCode + '_001_001'  // Default first branch
        });
        
        const data = response.data;
        
        // Update canonical state only (clean break from legacy)
        setDivCodes(data.div_codes);
        setBranchCodes(data.branch_codes);
        setActiveDivCode(data.active_div_code);
        setActiveBranchCode(data.active_branch_code);
        setScope(data.scope);
        
        localStorage.setItem('bg-code', data.bg_code);
        localStorage.setItem('div-codes', JSON.stringify(data.div_codes));
        localStorage.setItem('branch-codes', JSON.stringify(data.branch_codes));
        
        onSwitchTenant?.(data);
    } catch (error) {
        console.error('Tenant switch failed:', error);
        // Revert local state on failure
    }
};
```

**Change:**
1. Add async API call to `POST /api/v1/tenant/switch/` in all handle methods
2. Add new state variables for canonical fields (`divCodes`, `branchCodes`, `activeDivCode`, `activeBranchCode`, `scope`)
3. Remove all legacy state variables (`bgCode`, `division`, `branch`)
4. Include request body schema:
   ```json
   {
       "bg_code": "KURO0002",
       "active_div_code": "KURO0002_001",
       "active_branch_code": "KURO0002_001_001"
   }
   ```
5. Handle errors (revert local state on failure)

**Clean break note:** This is a full migration — no backward compatibility with legacy state variables. All components must be updated to use canonical state variables (`divCodes`, `branchCodes`, `activeDivCode`, `activeBranchCode`, `scope`).

**Verification:**
- [ ] Backend receives switch request on UI interaction
- [ ] `UserTenantContext` DB row updated after switch
- [ ] New JWT received and stored as cookie
- [ ] Frontend state matches backend state after switch
- [ ] Subsequent API calls use new tenant context

---

### 2C. Include Full Context in Login Response

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/users/views.py`  
**Method:** `_build_login_response()` (lines ~200–250)

**Current state (INCOMPLETE):**
```python
# Returns only bg_code, active_div_code, active_branch_code
return {
    "identity_id": identity.identity_id,
    "bg_code": user_tenant_context.bg_code,
    "active_div_code": user_tenant_context.active_div_code,
    "active_branch_code": user_tenant_context.active_branch_code,
    # ❌ Missing: div_codes, branch_codes, scope
}
```

**Required state (LOCKED):**
```python
# endpoint_contract_spec_revised.md §4.2 Login Response Contract
# Mandatory fields: identity_id, bg_code, div_codes, branch_codes, 
#                   active_div_code, active_branch_code, scope, roles, permissions
return {
    "identity_id": identity.identity_id,
    "bg_code": user_tenant_context.bg_code,
    "div_codes": user_tenant_context.div_codes,
    "branch_codes": user_tenant_context.branch_codes,
    "active_div_code": user_tenant_context.active_div_code,
    "active_branch_code": user_tenant_context.active_branch_code,
    "scope": user_tenant_context.scope,
    "roles": roles,  # Derived from extensions
    "permissions": permissions,  # RBAC perm_codes
}
```

**Change:**
1. Add `div_codes`, `branch_codes`, `scope` to login response
2. Ensure `roles` and `permissions` are included (already present?)

**Verification:**
- [ ] Login response includes all mandatory fields from §4.2
- [ ] Frontend initializes with correct `div_codes`, `branch_codes`, `scope` on first login
- [ ] `TenantContext.jsx` seeds from correct fields (not `userDetails.division`)

**Frontend seeding update (TenantContext.jsx) — Clean Break:**
```javascript
// Current (BROKEN): Reads userDetails.division (singular, may not exist)
const serverDivision = Array.isArray(userDetails.division)
    ? userDetails.division[0]
    : userDetails.division;

// Required (LOCKED): Read canonical fields from login response
const serverDivCodes = userDetails.div_codes || [];  // Array
const serverBranchCodes = userDetails.branch_codes || [];  // Array
const serverActiveDivCode = userDetails.active_div_code || (serverDivCodes[0] || '');
const serverActiveBranchCode = userDetails.active_branch_code || (serverBranchCodes[0] || null);
const serverScope = userDetails.scope || 'full';

// Active-context convention: div_codes[0] = active division, branch_codes[0] = active branch
// active_div_code and active_branch_code are explicit aliases that MUST always equal div_codes[0] and branch_codes[0]
if (serverActiveDivCode !== (serverDivCodes[0] || '')) {
    console.warn('Active division mismatch: active_div_code !== div_codes[0]');
}
if (serverActiveBranchCode !== (serverBranchCodes[0] || null)) {
    console.warn('Active branch mismatch: active_branch_code !== branch_codes[0]');
}

// Clean break: Seed only canonical state (remove legacy state seeding)
setDivCodes(serverDivCodes);
setBranchCodes(serverBranchCodes);
setActiveDivCode(serverActiveDivCode);
setActiveBranchCode(serverActiveBranchCode);
setScope(serverScope);

// Remove legacy state variables entirely:
// - const [bgCode, setBgCodeState] = useState(...)  // ❌ REMOVE
// - const [division, setDivisionState] = useState(...)  // ❌ REMOVE
// - const [branch, setBranchState] = useState(...)  // ❌ REMOVE
```

---

## Phase 3: P2 — Correctness (1.5 hours)

### 3A. Scope `useDivisions` to BG

**File:** `/home/chief/Coding-Projects/kteam-fe-chief/src/hooks/useDivisions.jsx`

**Current state (BROKEN):**
```javascript
// Query key doesn't include bgCode — stale data on BG switch
const { data } = useQuery(["tenant-divisions"], fetchDivisions, {
    staleTime: 5 * 60 * 1000,  // 5 minutes
});
```

**Required state (LOCKED):**
```javascript
// Query key must include bgCode to refetch on BG switch
const { data } = useQuery(
    ["tenant-divisions", bgCode],  // ✅ Includes bgCode
    () => fetchDivisions(bgCode),
    {
        staleTime: 5 * 60 * 1000,
        enabled: !!bgCode,  // Only fetch if bgCode is set
    }
);
```

**Change:**
1. Include `bgCode` in React Query key
2. Pass `bgCode` to `fetchDivisions` function
3. Add `enabled: !!bgCode` to prevent fetch on init

**Verification:**
- [ ] Divisions refetch when BG changes
- [ ] No stale division data after BG switch

---

### 3B. Deprecate Legacy `bgSwitch` Endpoint

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/users/views.py`  
**File:** `/home/chief/Coding-Projects/kteam-dj-chief/users/urls.py`

**Current state (RISK):**
- Both `/api/v1/users/bgswitch/` (legacy) and `/api/v1/tenant/switch/` (new) are active
- Legacy endpoint doesn't emit JWT (same bug as P1-1)

**Required state (LOCKED):**
```python
# Add deprecation warning to legacy endpoint
# Redirect to new endpoint or return 410 Gone after frontend migration completes

@deprecated  # Add deprecation decorator
def bgSwitch(request):
    """DEPRECATED: Use /api/v1/tenant/switch/ instead."""
    # Option 1: Return 410 Gone
    # return HttpResponse(status=410)
    
    # Option 2: Redirect with warning
    # return JsonResponse({"error": "DEPRECATED", "replacement": "/api/v1/tenant/switch/"})
    
    # Option 3: Keep functional but log deprecation warning
    logger.warning("Legacy bgSwitch endpoint called — should use /tenant/switch/")
    # ... existing logic ...
```

**Change:**
1. Add deprecation warning/log to legacy `bgSwitch` view
2. (Optional) Return 410 Gone after frontend migration is complete
3. Update any remaining frontend references to use `/tenant/switch/`

**Verification:**
- [ ] No frontend code calls legacy `/users/bgswitch/`
- [ ] Legacy endpoint logs deprecation warning when called
- [ ] (Optional) Legacy endpoint returns 410 Gone

---

## Phase 4: P3 — Cleanup (1 hour)

### 4A. Remove `request.data._mutable` Hack

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/users/api/viewsets.py`  
**Method:** `bgswitch` action (line ~1107)

**Current state (FRAGILE):**
```python
request.data._mutable = True  # ❌ Depends on DRF internals
request.data['bg_code'] = bg_code
```

**Required state (LOCKED):**
```python
# Use proper request data handling — don't mutate QueryDict
bg_code = request.data.get("bg_code")
# ... use bg_code without mutating request.data ...
```

**Change:**
1. Remove `request.data._mutable = True`
2. Extract `bg_code` from `request.data` without mutation
3. Use extracted value in logic

**Verification:**
- [ ] `bgswitch` viewset still works correctly
- [ ] No DRF internal dependencies

---

### 4B. Audit `token_key` on UserTenantContext

**File:** `/home/chief/Coding-Projects/kteam-dj-chief/users/models.py`  
**Field:** `UserTenantContext.token_key`

**Current state (UNCERTAIN):**
```python
token_key = models.CharField(max_length=512, blank=True, null=True)
# Stores str(request.auth) — JWT string
# Not referenced by resolve_access, middleware, or TenantCollection
# Only used in switch endpoint as pass-through
```

**Required state (LOCKED):**
```python
# Option 1: Remove if truly dead code
# Option 2: Document purpose if used for token invalidation
# Option 3: Keep but add comment explaining usage

# If removing:
# token_key = models.CharField(...)  # REMOVED — no longer used

# If keeping:
token_key = models.CharField(
    max_length=512, 
    blank=True, 
    null=True,
    help_text="JWT token key for invalidation (if used)"
)
```

**Change:**
1. Search codebase for references to `token_key`
2. If unused: remove field (add migration)
3. If used: document purpose in model help_text

**Verification:**
- [ ] No references to `token_key` in codebase (or documented usage)
- [ ] No regressions in switch endpoint

---

## Phase 5: Verification (1 hour)

### 5A. Run Full Test Suite

```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
python manage.py test --verbosity=2
```

**Expected:** All tests pass. No regressions.

### 5B. Manual Verification Checklist

**Backend:**
- [ ] Login returns full context (`div_codes`, `branch_codes`, `scope`)
- [ ] Middleware extracts canonical field names from JWT
- [ ] ContextVar contains correct values after login
- [ ] RLS session variables set correctly
- [ ] MongoDB queries include tenant filter
- [ ] `/tenant/switch/` emits new JWT with updated claims
- [ ] Legacy `/users/bgswitch/` logs deprecation warning

**Frontend:**
- [ ] Login initializes with correct `div_codes`, `branch_codes`, `scope`
- [ ] Tenant switch calls `/tenant/switch/` on UI interaction
- [ ] New JWT received and stored as cookie
- [ ] Frontend state matches backend state after switch
- [ ] Divisions refetch on BG switch
- [ ] No stale tenant data after switch
- [ ] **No legacy state variables remain** (`bgCode`, `division`, `branch` removed)
- [ ] **All components use canonical state** (`divCodes`, `branchCodes`, `activeDivCode`, `activeBranchCode`, `scope`)

**Integration:**
- [ ] Cross-tenant data isolation works (user can't see data from other tenants)
- [ ] Tenant switch persists across page refresh (JWT cookie)
- [ ] All API calls use correct tenant context

---

## Reference: Locked Specs

- **`multi_tenancy_revised.md`** — Multi-tenancy Constitution (JWT authority, middleware contract, TenantCollection contract)
- **`endpoint_contract_spec_revised.md`** — Endpoint contracts (§4.2 Login, §5.1 Context Injection, §5.3 Switch, §5.4 Frontend)
- **`CANONICAL_NAMING.md`** — Frozen canonical names (`div_codes`, `branch_codes`, `active_div_code`, `active_branch_code`)

---

## Reference: Audit Findings

- **`28-06-2026_tenant-context-audit_a72921.md`** — Confirmed bugs (P0-1, P0-2, P1-1, P1-2, P1-3, P1-4, P2-1, P2-2, P2-3, P3-1, P3-2)

---

## Edge Cases & Uncertainties

1. **`update_or_create` lookup key:** Uses only `userid` (not `userid + bg_code`). Multi-BG support would need composite key or separate rows. Not fixed in this pass — flagged for future design.

2. **`resolve_access` fallback:** DB fallback masks middleware bug in testing. Integration tests must verify ContextVar explicitly.

3. **Frontend branch regex:** `/^[A-Z]+\d+_\d+_\d+$/` assumes fixed pattern. If backend changes code format, frontend clears valid branches. Maintenance burden.

4. **Legacy endpoint coexistence:** Both `/users/bgswitch/` and `/tenant/switch/` active. Deprecation timeline not specified — should be added to migration spec.

5. **JWT cookie attributes:** Must match original JWT cookie (domain, path, secure flag, same-origin policy). Verify in implementation.

---

## Success Criteria

- [ ] All P0 bugs fixed (middleware + MongoDB wrapper use canonical names)
- [ ] All P1 bugs fixed (switch endpoint emits JWT, frontend calls backend)
- [ ] All P2 bugs fixed (divisions scoped to BG, legacy endpoint deprecated)
- [ ] All P3 bugs fixed (no fragile hacks, dead code removed)
- [ ] Full test suite passes
- [ ] Manual verification checklist complete
- [ ] No cross-tenant data leakage
- [ ] Frontend/backend state aligned after tenant switch
- [ ] JWT is authoritative source of tenant context for every request

---

*Execution prompt generated: 2026-06-28*  
*Foundation: Locked specs (multi_tenancy_revised.md, endpoint_contract_spec_revised.md, CANONICAL_NAMING.md)*  
*Priority: P0 — Restore tenant isolation before any other work*
