# Canonical Naming Scheme — Source of Truth

**Effective:** Immediately
**Owner:** Modernization Owner
**Last verified:** 2026-06-26

## Frozen Canonical Names

These are the **only** valid names for these concepts across all phases, specs, and code:

| Concept | Canonical Name | Examples of Non-Canonical (FORBIDDEN) |
|---------|---------------|--------------------------------------|
| Identity primary key | `identity_id` | `userid`, `identityId`, `user_id` |
| Business group code | `bg_code` | `bgcode`, `bg`, `business_group` |
| Division code (singular) | `div_code` | `division`, `div`, `div_code_legacy` |
| Division scope (array) | `div_codes` | `division[]`, `entity`, `divisions` |
| Branch code (singular) | `branch_code` | `branch`, `branch_code_legacy` |
| Branch scope (array) | `branch_codes` | `branches[]`, `branchs` |
| Active division | `active_div_code` | `entity[0]`, `active_division` |
| Active branch | `active_branch_code` | `branches[0]`, `active_branch` |
| Request ID | `request_id` | `requestId`, `req_id`, `reqId` |
| Refresh token | `refresh_token` | `refreshToken`, `refresh` |
| Token type | `token_type` | `tokenType`, `type` |

## Rules

1. **One name per concept** — Never use two names for the same concept in the same file.
2. **Canonical wins** — If a file uses a non-canonical name, replace it with the canonical name.
3. **Legacy references are explanatory only** — When documenting migration, you may show the old name in a "before" context, but the "after" state must use the canonical name exclusively.
4. **No camelCase** — All canonical names use snake_case.
5. **No abbreviations** — Use the full canonical name, not shortened variants.

## Audit Checklist

Before finalizing any phase document, verify:

- [ ] No `bgcode` — use `bg_code`
- [ ] No `division` (in Mongo field context) — use `div_code`
- [ ] No `branch` (in Mongo field context) — use `branch_code`
- [ ] No `userid` (in RBAC FK context) — use `identity_id`
- [ ] No `requestId` — use `request_id`
- [ ] No `refreshToken` — use `refresh_token`
- [ ] No `tokenType` — use `token_type`
- [ ] No `entity` (JWT/ContextVar) — use `div_codes`
- [ ] No `branches` (JWT/ContextVar) — use `branch_codes`
- [ ] No `entity[0]` / `branches[0]` — use `active_div_code` / `active_branch_code`

## Exceptions

- `CustomUser.userid` is the Django AUTH_USER_MODEL PK — this is a **different concept** from `identity_id`. Keep as `userid` when referring to the Django user model PK.
- `division_accesslevel()` and `business_accesslevel()` are legacy functions being **removed**, not renamed. Keep as-is in migration documentation.
- `accesslevel` and `businessgroups` are legacy response fields being **removed**, not renamed. Keep as-is in migration documentation.
- `div_codes[0]` and `branch_codes[0]` are the active division/branch by convention — `active_div_code` and `active_branch_code` are explicit aliases for clarity.

## Precedence

Canonical naming defers to this document. All phase files MUST use these names in "after" state. "Before" state may show legacy names for migration documentation, but must clearly label them as legacy.

**Source of truth:** This document (`CANONICAL_NAMING.md`).
**Conflict resolution:** See `26-06-2026_spec-alignment-execution_e60de0.md` §Document Precedence Rules.
