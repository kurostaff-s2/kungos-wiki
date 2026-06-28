# Spec Documents Review and Tightening — Multi-Tenancy + Endpoint Contract

| Field | Value |
|-------|-------|
| Project ID | kung-os |
| Primary entity ID | spec-review-004b33 |
| Entity type | handoff |
| Short description | Review multi_tenancy.md and endpoint_contract_spec.md for completeness, ambiguity, and deviation scope. Produce tightened versions that leave no room for implementation drift. |
| Status | draft |
| Source references | multi_tenancy.md, endpoint_contract_spec.md, CANONICAL_NAMING.md, tenant-context-audit_a72921.md (findings), platform_primitives.md |
| Generated | 28-06-2026 |
| Next action / owner | Read both specs, identify gaps/ambiguities, produce revised drafts with deviations eliminated |

---

## Project Context

**Project root (backend):** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Project root (frontend):** `/home/chief/Coding-Projects/kteam-fe-chief/`
**Reference docs:** `/home/chief/llm-wiki/Kung_OS/architecture/multi_tenancy.md`, `/home/chief/llm-wiki/Kung_OS/specs/endpoint_contract_spec.md`, `/home/chief/llm-wiki/Kung_OS/CANONICAL_NAMING.md`
**Related docs:** `/home/chief/llm-wiki/Kung_OS/architecture/platform_primitives.md`, `/home/chief/llm-wiki/Kung_OS/architecture/rbac_system.md`
**Key files for this task:** The two spec documents above (read-only analysis, output is revised drafts)

---

## Goal

Review `multi_tenancy.md` and `endpoint_contract_spec.md` for **completeness, ambiguity, and deviation scope**. The tenant-context-audit revealed that the middleware implementation diverged from the spec because the spec did not define the extraction contract explicitly enough. The goal is to make the specs **self-sufficient** — an implementing agent should not need to infer behavior from code, other docs, or convention.

**Definition of "self-sufficient":** Every implementation decision required by the spec is stated explicitly in the spec. No cross-referencing needed for core contracts. No "as defined elsewhere" for critical paths.

---

## Scope

### In Scope
1. `multi_tenancy.md` — Architecture doc for tenant hierarchy, isolation, JWT claims, middleware, RLS, MongoDB
2. `endpoint_contract_spec.md` — Endpoint contracts, including §5 Tenant Context Rules
3. Cross-references between the two (consistency check)
4. Gaps identified by tenant-context-audit findings (P0-P3)

### Out of Scope
1. Domain-specific specs (cafe, eshop, tournaments, etc.)
2. Database schema specs (postgresql_schema.md, mongodb_schema.md)
3. Migration specs (migration_spec.md, migration_tracker.md)
4. RBAC spec (rbac_system.md) — reference only for consistency

---

## Phase 1: Gap Analysis — multi_tenancy.md

**What:** Read `multi_tenancy.md` line by line and identify every statement that is ambiguous, incomplete, or allows multiple interpretations.

**Steps:**

1. **JWT Claims section** — Verify the JWT claims table is the *single source of truth*. Check:
   - Are all claim names, types, and sources explicitly defined?
   - Is the distinction between "scope" (array, all accessible) and "active" (singular, current selection) unambiguous?
   - Does it specify which claims are *required* vs *optional*?
   - Does it specify which claims are *mutable* (change on switch) vs *immutable* (fixed at login)?

2. **Middleware section** — The tenant-context-audit revealed the middleware extracted wrong fields. Check:
   - Does the spec define the *exact extraction contract* (which JWT claim → which session variable / ContextVar)?
   - Does it specify the *fallback behavior* when a claim is missing?
   - Does it specify the *error behavior* when tenant context cannot be resolved?
   - Does it define the *order of operations* (extract → validate → set session vars → set ContextVar)?

3. **Session variables section** — Check:
   - Are all session variable names explicitly listed with source and purpose?
   - Does it specify which variables are *required* (must be set) vs *optional*?
   - Does it specify the *default value* when source is empty/missing?

4. **MongoDB TenantCollection section** — Check:
   - Does it define the *exact contract* for how TenantCollection receives tenant context?
   - Does it specify the *error* when context is missing?
   - Does it specify which fields are injected into queries (`bg_code` only, or also `div_code`/`branch_code`)?

5. **UserTenantContext model section** — Check:
   - Does the model description match the actual Django model? (The spec says `division` and `branches` but the model uses `div_codes` and `branch_codes`)
   - Does it specify the *update semantics* (when is it created/updated)?
   - Does it specify the *relationship to JWT* (is it the source of truth, or is the JWT)?

6. **RLS section** — Check:
   - Does it specify which tables have RLS policies?
   - Does it specify the *policy structure* (bypass + tenant_isolation)?
   - Does it specify the *session variable → policy mapping*?

**Output:** Annotated list of gaps with line references and recommended language.

---

## Phase 2: Gap Analysis — endpoint_contract_spec.md

**What:** Read `endpoint_contract_spec.md` and identify every statement that is ambiguous, incomplete, or allows deviation.

**Steps:**

1. **§5 Tenant Context Rules** — The critical section. Check:
   - **§5.1 Context Injection** — The pseudo-code shows `ctx.div_codes` and `ctx.branch_codes` but the actual model uses different field names. Does the spec define the *authoritative field names*?
   - **§5.2 Query Scoping Rules** — Does it specify which scope levels require which filters? (e.g., does `division` scope require `bg_code AND div_code` or just `div_code`?)
   - **§5.3 Tenant Switching** — Does it specify that the switch endpoint *must emit a new JWT*? (Current spec shows `token_key` in response but doesn't mandate JWT refresh)
   - Does it specify the *request body schema* for the switch endpoint?
   - Does it specify the *response schema* including JWT-related fields?

2. **§4 Authentication & Authorization** — Check:
   - **§4.1.1 Header Naming** — Does it specify how the JWT is transmitted (cookie vs header)?
   - **§4.2 Login Response** — Does the target contract include all tenant context fields? (Current target shows `bg_code`, `active_div_code`, `active_branch_code` but NOT `div_codes`, `branch_codes`, `scope`)
   - Does it specify which fields are *always present* vs *conditionally present*?

3. **§11 Compatibility Matrix** — Check:
   - **§11.1 Legacy → Canonical** — Does it cover all legacy field names found in the codebase?
   - Does it specify *removal timeline* for each legacy field?
   - Does it specify *coexistence rules* (can both exist simultaneously)?

4. **§3 Request/Response Contracts** — Check:
   - Does the standard response envelope apply to *all* endpoints or just new ones?
   - Does it specify *which endpoints return which envelope*?

5. **Cross-reference consistency** — Check:
   - Do JWT claim names match between §4, §5, and multi_tenancy.md?
   - Do field names match between §5.1 and the UserTenantContext model?
   - Do session variable names match between multi_tenancy.md and §5?

**Output:** Annotated list of gaps with section references and recommended language.

---

## Phase 3: Deviation Surface Analysis

**What:** Identify every place where an implementing agent could reasonably choose a different implementation than intended.

**Definition of "deviation surface":** Any spec statement that allows multiple valid interpretations, or any missing statement that forces the implementer to guess.

**Categories:**

1. **Missing mandatory statements** — Things that MUST be specified but aren't:
   - "The middleware MUST extract `div_codes` from the JWT claim named `div_codes`" (was missing → led to P0 bug)
   - "The switch endpoint MUST emit a new JWT with updated claims" (was missing → P1 bug)
   - "The frontend MUST call the backend switch endpoint on tenant change" (was missing → P1 bug)

2. **Ambiguous terminology** — Terms that could mean different things:
   - "tenant context" — does this mean the JWT claims, the DB row, the ContextVar, or all three?
   - "active division" — is this the user's current selection, or the first element of `div_codes`?
   - "scope" — does this mean authorization scope (what you CAN access) or active scope (what you ARE accessing)?

3. **Implicit assumptions** — Things assumed but not stated:
   - "The JWT is the source of truth for tenant context" (implied but not stated)
   - "UserTenantContext is updated on every switch" (implied but not stated)
   - "The middleware runs on every request" (implied by middleware pattern but not stated)

4. **Inconsistent naming** — Same concept, different names:
   - `division` vs `div_code` vs `active_div_code` vs `div_codes`
   - `branches` vs `branch_code` vs `active_branch_code` vs `branch_codes`
   - `entity` (legacy) vs `div_codes` (canonical) — both appear in different places

**Output:** Deviation surface map with category, location, risk level, and recommended fix.

---

## Phase 4: Revised Drafts

**What:** Produce revised versions of both specs that eliminate the identified gaps, ambiguities, and deviation surfaces.

**Rules for revised drafts:**

1. **Explicit over implicit** — Every implementation decision is stated. No "as per convention" or "as defined elsewhere" for critical paths.
2. **Mandatory language** — Use MUST/SHOULD/MAY (RFC 2119) for clarity. MUST = no deviation allowed.
3. **Single source of truth** — JWT claims defined once, referenced everywhere. No redefinitions.
4. **Cross-reference with authority** — When referencing another doc, cite the specific section and field. "See multi_tenancy.md §JWT Claims" not "see the multi-tenancy doc".
5. **Field name tables** — Every field name appears in a canonical table with type, source, and purpose. No inline definitions.
6. **Error behavior** — Every critical path specifies what happens on failure (missing claim, empty context, etc.).
7. **Frontend contract** — The spec defines what the frontend MUST do (call backend on switch, etc.), not just what the backend provides.

**Specific changes to make:**

### multi_tenancy.md

1. **Add explicit middleware extraction contract:**
   ```
   The TenantContextMiddleware MUST extract the following claims from the JWT:
   - `bg_code` → `app.current_bg_code` session variable (MUST be non-empty)
   - `div_codes` → used to derive `active_div_code` → `app.current_division`
   - `branch_codes` → used to derive `active_branch_code` → `app.current_branch`
   - `identity_id` → `app.current_userid` session variable
   
   The middleware MUST NOT read legacy field names (`entity`, `branches`, `userid`) from the JWT.
   ```

2. **Fix UserTenantContext model description** (currently says `division`/`branches`, model uses `div_codes`/`branch_codes`):
   ```
   UserTenantContext fields:
   - userid (CharField) — the user
   - bg_code (CharField) — current business group
   - div_codes (JSONField) — list of accessible divisions
   - branch_codes (JSONField) — list of accessible branches
   - token_key (CharField) — JWT token for the session
   - scope (CharField) — 'full' | 'division' | 'branch'
   ```

3. **Add MongoDB TenantCollection contract:**
   ```
   TenantCollection MUST receive tenant context from the ContextVar set by TenantContextMiddleware.
   It MUST inject `bg_code` into every query filter.
   It MUST raise TenantContextMissing if `bg_code` is empty.
   It MUST read `div_codes` and `branch_codes` from the canonical field names (NOT `entity` or `branches`).
   ```

4. **Add JWT authority statement:**
   ```
   The JWT is the authoritative source of tenant context for every request.
   UserTenantContext (DB) is the persistence layer — updated by switch endpoints, read by resolve_access as fallback.
   The ContextVar is the in-memory carrier — populated by middleware from JWT, consumed by application code.
   ```

### endpoint_contract_spec.md

1. **§5.3 Tenant Switching — Add JWT emission requirement:**
   ```
   POST /api/v1/tenant/switch/ MUST:
   1. Validate the requested bg_code against the user's Identity
   2. Update UserTenantContext with new bg_code, div_codes, branch_codes, scope
   3. Generate a new JWT with updated canonical claims (per multi_tenancy.md §JWT Claims)
   4. Set the new JWT as an HttpOnly cookie
   5. Return the response envelope with updated context data
   
   The response MUST include:
   - `bg_code` (string) — new active BG
   - `div_codes` (array) — accessible divisions
   - `branch_codes` (array) — accessible branches
   - `active_div_code` (string) — new active division
   - `active_branch_code` (string | null) — new active branch
   - `scope` (string) — new scope level
   ```

2. **§4.2 Login Response — Add missing tenant fields:**
   ```
   The login response MUST include:
   - `bg_code` (string) — active business group
   - `div_codes` (array) — all accessible divisions
   - `branch_codes` (array) — all accessible branches
   - `active_div_code` (string) — active division
   - `active_branch_code` (string | null) — active branch
   - `scope` (string) — scope level
   - `identity_id` (string) — stable person PK
   ```

3. **Add frontend contract section (§5.4):**
   ```
   §5.4 Frontend Tenant Switching Contract
   
   The frontend MUST:
   1. Call POST /api/v1/tenant/switch/ when the user changes BG/division/branch
   2. Include the new context in the request body
   3. Process the new JWT cookie set by the response
   4. Update local state (React context + localStorage) with the response data
   5. NOT switch tenant context via local state alone (backend must be notified)
   ```

4. **§11.1 Compatibility Matrix — Add middleware extraction row:**
   ```
   | Legacy Field/Claim | Canonical Field | Context | Removal |
   | `entity` (JWT) | `div_codes` | Middleware extraction | Phase 0 (MUST) |
   | `branches` (JWT) | `branch_codes` | Middleware extraction | Phase 0 (MUST) |
   ```

---

## Phase 5: Consistency Verification

**What:** Cross-check the revised drafts against each other and against the live code to ensure no new inconsistencies are introduced.

**Checklist:**

- [ ] JWT claim names identical in multi_tenancy.md and endpoint_contract_spec.md
- [ ] Session variable names identical in multi_tenancy.md and endpoint_contract_spec.md
- [ ] UserTenantContext field names match Django model (`div_codes`, `branch_codes`)
- [ ] Middleware extraction contract matches JWT claims table
- [ ] MongoDB TenantCollection contract matches ContextVar contract
- [ ] Switch endpoint contract includes JWT emission
- [ ] Login response contract includes all tenant fields
- [ ] Frontend contract matches backend switch endpoint
- [ ] Legacy → canonical mapping covers all legacy names in codebase
- [ ] No "as defined elsewhere" for critical paths

---

## Constraints

- **Read-only analysis first** — Do not modify the spec files until the gap analysis is complete and reviewed.
- **Preserve existing structure** — Revisions must maintain the existing TOC and section numbering. Add new sections, don't renumber.
- **RFC 2119 language** — Use MUST/SHOULD/MAY consistently. MUST = no deviation.
- **No new dependencies** — The specs should not reference docs that don't exist yet.
- **Backward compatible** — Revisions must not invalidate existing implementations that are already correct.

---

## Success Criteria

- [ ] Gap analysis complete for both specs (annotated list with line references)
- [ ] Deviation surface map produced (categorized with risk levels)
- [ ] Revised multi_tenancy.md draft saved to handoff directory
- [ ] Revised endpoint_contract_spec.md draft saved to handoff directory
- [ ] Consistency verification checklist passed
- [ ] All P0-P3 findings from tenant-context-audit addressed in revised specs
- [ ] No "as defined elsewhere" for critical paths (middleware extraction, JWT claims, switch contract)
- [ ] Frontend contract explicitly defined (not inferred from backend spec)

---

## Caveats & Uncertainty

1. **The spec may be intentionally incomplete** in some areas (e.g., leaving implementation details to the developer). The review should distinguish between "gaps that enable deviation" and "gaps that enable flexibility."

2. **Some legacy field names may still be in use** by parts of the codebase not covered by the audit. The compatibility matrix should be exhaustive, not just cover known cases.

3. **The frontend contract** is a new addition — the existing specs are backend-centric. Adding frontend requirements may be outside the original scope of the endpoint_contract_spec. Consider whether this belongs in the spec or in a separate frontend integration doc.

4. **RFC 2119 language** may be too prescriptive for some sections (e.g., architecture rationale). Use MUST only for implementation contracts, not for design decisions.

---

*Handoff generated: 28-06-2026*
*Estimated effort: 2–3 hours (Phase 1-2: 1h, Phase 3: 30min, Phase 4: 1h, Phase 5: 30min)*
