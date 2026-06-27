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
| Division code | `div_code` | `division`, `div`, `div_code_legacy` |
| Branch code | `branch_code` | `branch`, `branch_code_legacy` |
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

## Exceptions

- `CustomUser.userid` is the Django AUTH_USER_MODEL PK — this is a **different concept** from `identity_id`. Keep as `userid` when referring to the Django user model PK.
- `division_accesslevel()` and `business_accesslevel()` are legacy functions being **removed**, not renamed. Keep as-is in migration documentation.
- `accesslevel` and `businessgroups` are legacy response fields being **removed**, not renamed. Keep as-is in migration documentation.

## Precedence

Canonical naming defers to this document. All phase files MUST use these names in "after" state. "Before" state may show legacy names for migration documentation, but must clearly label them as legacy.

**Source of truth:** This document (`CANONICAL_NAMING.md`).
**Conflict resolution:** See `26-06-2026_spec-alignment-execution_e60de0.md` §Document Precedence Rules.
