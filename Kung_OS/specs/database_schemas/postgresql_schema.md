# PostgreSQL Schema Specification

**Status:** Spec — LIVE vs TARGET  
**Date:** 2026-05-17  
**Source:** `kungos_v2_db.md` (verified 2026-04-29), `KungOS_Identity_Design.md`  
**Purpose:** Authoritative reference for all PostgreSQL tables, columns, constraints, indexes

---

## 1. Schema Inventory

| Schema Area | LIVE Tables | TARGET Tables | Notes |
|---|---|---|---|
| **Users** | 8 | 8 + 6 new | `users_identity` + 5 extensions + `identity_phone_aliases` |
| **Tenant** | 5 | 5 | Cascade-code models (stable) |
| **RBAC** | 6 | 6 | Normalized tables (stable) |
| **Cafe** | 14 | 14 | Walk-in → identity FK, wallet → identity FK |
| **Platform** | 2 | 2 | Outbox + tenant config (stable) |
| **Orders** | 0 | 7 | `orders_core` + 6 detail tables (Phase 8) |

**Total:** 34 LIVE → 41 TARGET (+ 7 new identity/extension tables, + 7 order tables)

---

## 2. User Schema — LIVE

### 2.1 `users_customuser` (16 cols) — Django Auth Model

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `userid` | varchar | NOT NULL | — | **PRIMARY KEY**, indexed |
| `phone` | varchar | NOT NULL | — | UNIQUE, indexed |
| `username` | varchar | NULL | — | UNIQUE, indexed |
| `email` | varchar | NULL | — | UNIQUE, indexed |
| `name` | varchar | NOT NULL | — | |
| `password` | varchar | NOT NULL | — | |
| `user_status` | varchar | NULL | — | |
| `last_login` | timestamptz | NULL | — | |
| `is_active` | boolean | NOT NULL | — | CHECK constraint |
| `is_staff` | boolean | NOT NULL | — | CHECK constraint |
| `is_superuser` | boolean | NOT NULL | — | CHECK constraint |
| `is_admin` | boolean | NOT NULL | — | CHECK constraint |
| `created_date` | timestamptz | NOT NULL | — | |
| `emailverified` | boolean | NOT NULL | `false` | |

**Anti-pattern:** `USERNAME_FIELD='phone'` — phone is unique but not normalized (E.164). Split identity with `KuroUser`.

### 2.2 `users_kurouser` (42 cols) — Extended Profile

**Anti-pattern:** 42 fields, 39 mapped (31→employee, 3→identity, 4→replaced), 3 dropped. `businessgroups` is JSON (no FK integrity). `roles` is JSON (bypasses RBAC).

**Fields by category:**
- **Identity (3):** `phone_verified`, `idproof_type`, `idproof_number` → move to `users_identity`
- **Employee (31):** `userid`, `role`, `department`, `joining_date`, `salary`, bank details, BFC details, addresses, emergency contact, leave tracking, approval workflow → move to `users_employee`
- **Replaced (4):** `businessgroups` (JSON) → `Identity.bg_code`, `roles` (JSON) → `rbac_user_roles`, `primary_bg` → derived from tenant context, `edit` → dropped (dead code)
- **Dropped (3):** `edit` (dead code), `idproof_*` → identity table, `businessgroups` → tenant context

### 2.3 `users_user_tenant_context` (9 cols) — Session Tenant Scope

| Column | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `userid` | varchar | FK → `users_customuser.userid` |
| `bg_code` | varchar | Current business group |
| `div_codes` | jsonb | JSON list of accessible division codes (canonical) |
| `branch_codes` | jsonb | JSON list of accessible branch codes (canonical) |
| `token_key` | varchar | JWT token for the session |
| `scope` | varchar | `'full'` \| `'division'` \| `'branch'` |

**Note:** The Django model (`users/models.py`) and migration (`users/migrations/0001_initial.py`) both use `div_codes` and `branch_codes` (canonical). The PostgreSQL schema reflects the live target-state.

### 2.4 Other User Tables

| Table | Cols | PK | Notes |
|---|---|---|---|
| `users_accesslevel` | 55 | `id` | **DEPRECATED** — 50+ varchar permission fields. Replaced by RBAC tables. |
| `users_phonemodel` | 4 | `id` | OTP verification |
| `users_switchgroupmodel` | 4 | `id` | BG switching tokens |
| `users_common_counters` | 3 | `id` | Legacy counter tracking |
| `users_businessgroup` | 10 | `id` | **DELETED** — merged into `tenant_business_groups` (migration 0012) |

---

## 3. User Schema — TARGET

### 3.1 `users_identity` — Core Identity (NEW)

**Replaces:** `CustomUser` (auth identity), `reb_users` (customers), `employee_attendance.userid` (employees), `players.userid` (players), `serviceRequest.phone` (requestors), `caf_platform_walkins` (walk-ins), `caf_platform_users` (cafe users)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, sequential (`ID000001`) |
| `phone` | varchar | NOT NULL | — | UNIQUE per tenant (`bg_code` + `phone`), E.164 normalized |
| `name` | varchar(200) | NOT NULL | — | Full display name |
| `email` | varchar | NULL | — | UNIQUE, indexed |
| `bg_code` | varchar(10) | NOT NULL | — | FK → `tenant_business_groups.bg_code`, indexed |
| `div_code` | varchar(20) | NOT NULL | — | FK → `tenant_divisions.div_code`, indexed |
| `branch_code` | varchar(30) | NULL | — | FK → `tenant_branches.branch_code`, indexed |
| `status` | varchar(20) | NOT NULL | `'active'` | CHECK: `active`/`suspended`/`inactive` |
| `phone_verified` | boolean | NOT NULL | `false` | From `KuroUser.phone_verified` |
| `idproof_type` | varchar(50) | NULL | — | From `KuroUser.idproof_type` |
| `idproof_number` | varchar(50) | NULL | — | From `KuroUser.idproof_number` |
| `user` | varchar | NULL | — | **OneToOne** → `users_customuser.userid` (nullable) |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

**Indexes:**
- `idx_identity_tenant_phone`: `(bg_code, phone)` — composite unique
- `idx_identity_tenant`: `(bg_code, div_code)` — tenant scope
- `idx_identity_email`: `(email)` — lookup
- `idx_identity_status`: `(status)` — filtering

**Constraints:**
- `uq_identity_tenant_phone`: UNIQUE `(bg_code, phone)`
- `chk_identity_status`: CHECK `status IN ('active', 'suspended', 'inactive')`

**Design decisions:**
- `identity_id` is PK — not `phone` (phones change), not `CustomUser.userid` (format varies)
- `phone` is tenant-scoped unique — same number can exist in different tenants
- No `identity_type` column — roles derived from which extension tables have rows
- `user` FK is nullable — phone-only identities don't need auth records

### 3.2 `identity_phone_aliases` — Associated Numbers (NEW)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | bigint | NOT NULL | — | **PRIMARY KEY** |
| `identity_id` | char(20) | NOT NULL | — | FK → `users_identity.identity_id`, CASCADE |
| `phone` | varchar | NOT NULL | — | Normalized E.164 |
| `alias_type` | varchar(20) | NOT NULL | `'secondary'` | `secondary`/`previous`/`shared`/`emergency` |
| `is_active` | boolean | NOT NULL | `true` | |
| `created_at` | timestamptz | NOT NULL | — | |

**Constraints:**
- `uq_identity_alias_phone`: UNIQUE `(identity_id, alias_type, phone)`

**Django model note:** `class Meta: db_table = 'identity_phone_aliases'` — Django would default to `users_phone_alias` which doesn't match the schema spec.

### 3.3 `users_employee` — Employee Extension (NEW)

**Replaces:** `KuroUser` (employee fields), `employee_attendance.userid` (Mongo)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, FK → `users_identity.identity_id`, CASCADE |
| `userid` | varchar(20) | NOT NULL | — | Employee ID (e.g. `KCTM006`), UNIQUE |
| `role` | varchar(20) | NOT NULL | — | `tech`/`admin`/`staff`/`manager` |
| `department` | varchar(100) | NULL | — | |
| `joining_date` | date | NOT NULL | — | |
| `salary` | decimal(12,2) | NULL | — | |
| `bank_name` | varchar(150) | NULL | — | |
| `bank_account_no` | varchar(50) | NULL | — | |
| `bank_ifsc` | varchar(20) | NULL | — | |
| `bank_branch` | varchar(150) | NULL | — | |
| `bfc_*` | varchar(200) | NULL | — | 5 BFC fields |
| `gender` | varchar(20) | NULL | — | |
| `dob` | date | NULL | — | |
| `pan` | varchar(10) | NULL | — | |
| `perm_address_*` | varchar(150) | NULL | — | 5 permanent address fields |
| `pres_address_*` | varchar(150) | NULL | — | 5 present address fields |
| `emerg_name` | varchar(150) | NULL | — | |
| `emerg_phone` | varchar | NULL | — | |
| `paid_offs` | integer | NOT NULL | `0` | |
| `available_offs` | integer | NOT NULL | `0` | |
| `festival_offs` | integer | NOT NULL | `0` | |
| `created_by` | varchar(150) | NULL | — | |
| `approved_by` | varchar(150) | NULL | — | |
| `approved_date` | timestamptz | NULL | — | |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

**Indexes:** `userid`, `role`, `department`

### 3.4 `users_customer` — Customer Extension (NEW)

**Merges:** `reb_users` (1,979), `misc` (1,979 duplicate), `orders.user.phone` (727 unregistered), `serviceRequest.phone` (1,328 requestors)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, FK → `users_identity.identity_id`, CASCADE |
| `registered` | boolean | NOT NULL | `false` | True = in `reb_users` (has login/auth) |
| `is_requestor` | boolean | NOT NULL | `false` | True = has filed service requests |
| `order_count` | integer | NOT NULL | `0` | Denormalized, updated via outbox events |
| `total_spent` | decimal(12,2) | NOT NULL | `0` | Denormalized, updated via outbox events |
| `last_order_date` | date | NULL | — | |
| `service_count` | integer | NOT NULL | `0` | Denormalized, updated via outbox events |
| `last_service_date` | date | NULL | — | |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

**Indexes:** `registered`, `is_requestor`, `order_count`, `total_spent`

### 3.5 `users_player` — Player Extension (NEW)

**Replaces:** `players` collection (MongoDB, 117 docs, 59 unique)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `identity_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, FK → `users_identity.identity_id`, CASCADE |
| `player_id` | varchar(20) | NOT NULL | — | Player ID (e.g. `REPL000001`), UNIQUE |
| `team_id` | varchar(20) | NULL | — | FK → `users_organization.org_id` |
| `riot_id` | varchar(100) | NULL | — | Riot Games ID |
| `rank` | varchar(50) | NULL | — | Current rank |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

**Indexes:** `player_id`, `team_id`, `rank`

### 3.6 `users_organization` — Organizations (NEW)

**Merges:** `teams` (14), `vendors` (409)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `org_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, sequential (`ORG00001`) |
| `org_type` | varchar(20) | NOT NULL | — | `team`/`vendor`, indexed |
| `name` | varchar(200) | NOT NULL | — | |
| `bg_code` | varchar(10) | NOT NULL | — | FK → `tenant_business_groups.bg_code` |
| `div_code` | varchar(20) | NOT NULL | — | FK → `tenant_divisions.div_code` |
| `created_at` | timestamptz | NOT NULL | — | |
| `updated_at` | timestamptz | NOT NULL | — | |

**Indexes:** `(bg_code, div_code)`, `org_type`

### 3.7 `users_vendor_profile` — Vendor Extension (NEW)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `org_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, FK → `users_organization.org_id`, CASCADE |
| `gstin` | varchar(15) | NOT NULL | — | UNIQUE |
| `pan` | varchar(10) | NULL | — | |
| `address` | text | NULL | — | |
| `payment_type` | varchar(50) | NULL | — | |
| `contact_phone` | varchar | NULL | — | |
| `contact_email` | varchar | NULL | — | |

### 3.8 `users_team_profile` — Team Extension (NEW)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `org_id` | char(20) | NOT NULL | — | **PRIMARY KEY**, FK → `users_organization.org_id`, CASCADE |
| `team_id` | varchar(20) | NOT NULL | — | UNIQUE |
| `coach` | varchar(150) | NULL | — | |

### 3.9 `team_memberships` — Team-to-Person Mapping (NEW)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | bigint | NOT NULL | — | **PRIMARY KEY** |
| `team_id` | varchar(20) | NOT NULL | — | FK → `users_team_profile.org_id` |
| `identity_id` | char(20) | NULL | — | FK → `users_identity.identity_id`, SET_NULL |
| `phone` | varchar | NULL | — | For unregistered members |
| `name` | varchar(200) | NULL | — | For unregistered members |
| `role_in_team` | varchar(20) | NOT NULL | `'member'` | `captain`/`member`/`substitute` |
| `bg_code` | varchar(10) | NOT NULL | — | Tenant scoping |
| `created_at` | timestamptz | NOT NULL | — | |

**Constraints:**
- `chk_membership_has_reference`: CHECK `(identity_id IS NOT NULL) OR (phone IS NOT NULL)` — allows unregistered members
- `uq_team_identity`: UNIQUE `(team_id, identity_id)` WHERE `identity_id IS NOT NULL`
- `uq_team_phone`: UNIQUE `(team_id, phone)` WHERE `phone IS NOT NULL`

**Django model note:** `class Meta: db_table = 'team_memberships'` — Django would default to `users_team_membership` which doesn't match the schema spec.

---

## 4. Tenant Schema — LIVE = TARGET (Stable)

| Table | PK | FKs | Notes |
|---|---|---|---|
| `tenant_business_groups` | `bg_code` | — | Legal entity. Code = first 4 letters of legal name + seq |
| `tenant_divisions` | `div_code` | `bg` → `tenant_business_groups.bg_code` | Operational division |
| `tenant_branches` | `branch_code` | `division` → `tenant_divisions.div_code` | Physical outlet |
| `tenant_bank_accounts` | `bank_code` | `bg` → `tenant_business_groups.bg_code` | Bank account per BG |
| `tenant_division_addresses` | `address_code` | `division` → `tenant_divisions.div_code` | Bill/shipping addresses |

**Current data:** 2 BGs, 4 Divisions, 6 Branches

---

## 5. RBAC Schema — LIVE = TARGET (Stable)

| Table | PK | FKs | Notes |
|---|---|---|---|
| `rbac_permissions` | `perm_code` | — | Permission registry (35 perms) |
| `rbac_roles` | `role_code` | `parent_role` → self | Single-level inheritance |
| `rbac_role_permissions` | `(role_code, perm_code)` | FK → both | Level 0-3 |
| `rbac_user_roles` | `id` | `userid` → `CustomUser`, `role` → `rbac_roles` | Scoped by `bg_code` + `division` |
| `rbac_user_role_branches` | `(user_role_id, branch_code)` | FK → `rbac_user_roles.id` | Branch-level scoping |
| `rbac_user_permissions` | `(userid, perm_code, bg_code, division)` | FK → `CustomUser.userid`, `rbac_permissions.perm_code` | Direct overrides |

**Resolution engine:** `users/permissions.py` — `resolve_permission()` cascades: exact division → BG-wide → global. Max-level wins.

---

## 6. Cafe Schema — LIVE vs TARGET

### 6.1 Changes Required

| Table | LIVE | TARGET | Change |
|---|---|---|---|
| `caf_platform_walkins` | `phone` UNIQUE | `identity_id` FK → `users_identity` | Drop phone uniqueness, add identity FK |
| `caf_platform_wallets` | `customer_id` FK → `users_customuser` | `identity_id` FK → `users_identity` | **Critical** — walk-ins need wallets |
| `caf_platform_users` | Thin projection of `CustomUser` | **REPLACED** by `users_identity` | Drop table, migrate to identity |

### 6.2 Cafe Table Inventory (14 tables, all PostgreSQL)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `caf_platform_cafes` | 12 | `id` | Cafe registry |
| `caf_platform_stations` | 14 | `id` | UNIQUE `(cafe_id, code)` |
| `caf_platform_sessions` | 17 | `id` | 4 FKs: cafe_id, game_id, price_plan_id, station_id |
| `caf_platform_session_leases` | 8 | `id` | Lease versioning |
| `caf_platform_station_commands` | 9 | `id` | Station remote control |
| `caf_platform_station_events` | 8 | `id` | Station event log |
| `caf_platform_wallets` | 11 | `id` | **TARGET:** `identity_id` FK → `users_identity` |
| `caf_platform_wallet_transactions` | 9 | `id` | FK wallet_id → wallets, FK created_by_id → CustomUser |
| `caf_platform_price_plans` | 15 | `id` | FK cafe_id, jsonb config |
| `caf_platform_member_plans` | 9 | `id` | UNIQUE `plan_id`, `tier` |
| `caf_platform_games` | 13 | `id` | Game catalog, FK cafe_id |
| `caf_platform_users` | 8 | `id` | **TARGET:** REPLACED by `users_identity` |
| `caf_platform_walkins` | 5 | `id` | **TARGET:** `identity_id` FK → `users_identity` |
| `caf_platform_auth_tokens` | 7 | `id` | Auth token storage |

---

## 7. Orders Schema — TARGET (Phase 8, Planned)

**Replaces:** 4 MongoDB collections (`estimates`, `kgorders`, `tporders`, `serviceRequest`)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `orders_core` | 13 | `id` | Shared by all order types |
| `estimate_detail` | 5 | `order_id` | FK → `orders_core.id` |
| `in_store_detail` | 9 | `order_id` | FK → `orders_core.id` |
| `tp_order_detail` | 7 | `order_id` | FK → `orders_core.id` |
| `service_detail` | 5 | `order_id` | FK → `orders_core.id` |
| `eshop_detail` | 22 | `order_id` | FK → `orders_core.id` |

**`orders_core` columns:** `id`, `orderid` (UNIQUE), `order_type` (ENUM), `status` (ENUM), `total_amount`, `customer_id` → `users_identity.identity_id`, `division`, `bg_code`, `billadd` (JSONB), `products` (JSONB), `channel`, `created_at`, `updated_at`

---

## 8. Platform Schema — LIVE = TARGET (Stable)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `platform_outbox_events` | 11 | `event_id` (uuid) | Outbox pattern for cross-store consistency |
| `platform_tenant_config` | 11 | `bg_code` | UNIQUE + PK on `bg_code`; 6 jsonb cfg columns |

---

## 9. Index Strategy

### 9.1 Tenant-First Indexing

All tables with tenant context carry compound indexes on `(bg_code, div_code)`. This enables:
- Query-level tenant filtering without joins
- RLS policy efficiency
- Cross-tenant audit queries

### 9.2 Identity Indexes

| Index | Table | Fields | Purpose |
|---|---|---|---|
| `idx_identity_tenant_phone` | `users_identity` | `(bg_code, phone)` | Universal lookup by normalized phone |
| `idx_identity_tenant` | `users_identity` | `(bg_code, div_code)` | Tenant-scoped identity queries |
| `idx_identity_email` | `users_identity` | `(email)` | Email lookup |
| `idx_identity_status` | `users_identity` | `(status)` | Status filtering |

### 9.3 Extension Table Indexes

All extension tables are indexed on the FK to `users_identity.identity_id` (which is also the PK). Additional indexes on query-heavy columns (`userid`, `player_id`, `registered`, `order_count`, `total_spent`).

---

## 10. Guardrails

### 10.1 Foreign Key Integrity

```sql
-- Identity extensions cascade on delete
ALTER TABLE users_employee
  ADD CONSTRAINT fk_employee_identity
  FOREIGN KEY (identity_id) REFERENCES users_identity(identity_id) ON DELETE CASCADE;

ALTER TABLE users_customer
  ADD CONSTRAINT fk_customer_identity
  FOREIGN KEY (identity_id) REFERENCES users_identity(identity_id) ON DELETE CASCADE;

ALTER TABLE users_player
  ADD CONSTRAINT fk_player_identity
  FOREIGN KEY (identity_id) REFERENCES users_identity(identity_id) ON DELETE CASCADE;
```

### 10.2 Composite Tenant Constraints

```sql
-- Phone uniqueness within tenant
CREATE UNIQUE INDEX uq_identity_tenant_phone
  ON users_identity (bg_code, phone);
```

### 10.3 Check Constraints

```sql
-- Status validation
ALTER TABLE users_identity
  ADD CONSTRAINT chk_identity_status
  CHECK (status IN ('active', 'suspended', 'inactive'));

-- Membership has reference
ALTER TABLE team_memberships
  ADD CONSTRAINT chk_membership_has_reference
  CHECK ((identity_id IS NOT NULL) OR (phone IS NOT NULL));
```

---

> **Implementation state:** Tenant, RBAC, and platform schemas are LIVE and stable. Identity schema is TARGET only — requires migration (see `migration_spec.md`). Orders schema is PLANNED (Phase 8). Cafe schema changes require migration 0001-0003.
