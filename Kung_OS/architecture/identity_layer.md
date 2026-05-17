# Identity Layer

**Status:** Constitution (stable, long-lived)
**Last updated:** 2026-05-16

---

## Principle

One identity record per person. Type-specific data lives in extension tables. Organizations (teams, vendors) are separate from people.

---

## Current State

KungOS manages identity across 7 user types in 8 storage locations. This is an anti-pattern — the same person can exist in multiple places with no canonical reference.

### PostgreSQL User Tables

| Table | PK | Purpose |
|-------|-----|---------|
| `users_customuser` | `userid` | Django auth model, `USERNAME_FIELD='phone'`, 16 columns |
| `users_kurouser` | `id` | Extended profile, 42 columns, FK to CustomUser |
| `users_user_tenant_context` | `id` | Active session tenant scope |
| `users_phonemodel` | `id` | OTP verification |
| `users_switchgroupmodel` | `id` | BG switching tokens |

### MongoDB Identity Collections

| Collection | Docs | Purpose |
|------------|------|---------|
| `reb_users` | 1,982 | Rebellion users |
| `misc` (users) | 3,218 | 100% duplicate of reb_users |
| `players` | 117 | Esports players (50% duplication) |
| `vendors` | 409 | Vendor records |
| `teams` | 14 | Esports teams |

### Key Overlaps

- `reb_users` ↔ `misc`: 100% duplicate
- `orders.user.phone` ↔ `reb_users`: 73% match
- `serviceRequest.phone` ↔ `reb_users`: 2.3% match
- `players.mobile` ↔ `reb_users.phone`: 20% match

### Anti-Patterns

- **Split identity:** `CustomUser` (auth, 16 cols) + `KuroUser` (profile, 42 cols). `KuroUser.businessgroups` is JSON (no FK integrity). `KuroUser.roles` is JSON (bypasses RBAC).
- **Phone uniqueness conflict:** `CafeWalkin.phone` is `unique=True`, which conflicts with `CustomUser.phone` uniqueness.
- **Redundant projection:** `CafeUser` is a thin projection of `CustomUser` — same data, different table.
- **Wallet ownership:** `CafeWallet.customer` FK → `CustomUser`, but walk-ins have wallets too.

---

## Target Architecture

### Core Identity Table

```
users_identity (core — 1 row per person)
├── identity_id   — PK, sequential (ID000001)
├── phone         — UNIQUE, normalized E.164 (+91XXXXXXXXXX)
├── name, email
├── bg_code, div_code, branch_code — tenant context
├── status        — active / suspended / inactive
├── phone_verified
├── idproof_type, idproof_number
└── user          — OneToOne to CustomUser (nullable)
```

### Person Extensions

```
users_employee   — employees only (extends users_identity)
users_customer   — customers (merges reb_users + serviceRequest)
users_player     — players (replaces Mongo players collection)
```

### Organization Extensions

```
users_organization (core — teams, vendors)
├── users_vendor_profile   — vendor-specific data
└── users_team_profile     — team-specific data
```

### Key Design Decisions

- **`identity_id` is the PK** — not `phone` (phones change), not `CustomUser.userid` (format varies).
- **`phone` is tenant-scoped unique** — `(bg_code, phone)` composite unique.
- **No `identity_type` column** — roles derived from which extension tables have rows. A person can be both a customer and a player.
- **`CustomUser` preserved as Django auth model** — linked via nullable OneToOne. Phone-only identities (unregistered customers, walk-ins) don't have a `CustomUser` record.
- **Organizations separate from people** — different query patterns, growth rates, schemas.

---

## Cafe Platform Alignment

### Current Problems

- `CafeWalkin.phone` is `unique=True` — conflicts with `CustomUser.phone` uniqueness.
- `CafeUser` is a thin projection of `CustomUser` — redundant data.
- `CafeWallet.customer` FK → `CustomUser` — but walk-ins have wallets too.

### Resolution

- `CafeWalkin` links to `users_identity` via FK (phone uniqueness dropped).
- `CafeUser` replaced by `users_identity`.
- Wallet links to `users_identity` instead of polymorphic walkin/user.

---

## Architecture Decisions

### Why `identity_id` as PK, Not Phone?

Phones change. People get new numbers, lose old ones, have multiple numbers. `identity_id` is immutable and sequential.

### Why No `identity_type` Column?

A person can be a customer, a player, and an employee simultaneously. Type columns create rigid categorization. Extension tables allow fluid roles.

### Why Preserve CustomUser?

`CustomUser` is Django's auth model. Replacing it requires migrating authentication, sessions, password hashing, and admin integration. Linking via OneToOne is safer — `CustomUser` handles auth, `users_identity` handles identity.

### Why Organizations Separate from People?

Teams and vendors have different schemas, growth rates, and query patterns. A vendor has GST/PAN/bank details. A team has players/coach/tournament history. Neither fits a person schema.

---

> **Implementation state:** The target architecture (`users_identity` + extensions) is not yet implemented. Current state uses `CustomUser` + `KuroUser`. See `operations/` for migration tracking.
