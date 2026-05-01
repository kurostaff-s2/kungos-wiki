# KungOS v2 — Database Source of Truth

**Ground-truthed:** 2026-04-29 (verified against live databases)  
**Sources:** PostgreSQL 16 introspection (`information_schema`), MongoDB 8 introspection (`KungOS_Mongo_One`), Django model scan (`rebellion/cafe/models.py`, `users/models.py`, etc.), kuro-gaming-dj-backend code scan  
**Purpose:** Single authoritative reference for all database tables, collections, columns, constraints, indexes, and migration status  
**Status:** ✅ Verified against live databases — no speculation

---

## TL;DR

| Aspect | Status |
|---|---|
| **PostgreSQL tables** | 34 KungOS tables (users:8, platform:2, cafe:14, tenant:4, entity:4, careers:1, view:1) — 9 Django framework tables excluded |
| **MongoDB collections** | 31 collections, 68,443 documents in `KungOS_Mongo_One` — 100% tenant-scoped |
| **Cafe platform** | 14 `caf_platform_*` PostgreSQL tables (NOT MongoDB) — all implemented |
| **Gaming integration** | 12/13 gaming collections MISSING from MongoDB; 5 gaming PG models NOT merged |
| **Tenant fields** | ✅ All 31 collections have `(bgcode, entity, branch)` tenant fields — migration complete |
| **PostgreSQL RLS** | ❌ NOT implemented — tenant isolation via app-level filtering (deferred to Phase 4) |
| **Tenant indexes** | 31/31 collections have `(bgcode, entity)` compound index (including `bgData` ✅, `entities` ✅) |
| **Tenant entity model** | ✅ New `tenant` app: `brands`, `entities`, `entity_branches`, `bg_entity_branches` with composite FK enforcement |
| **DB name** | `KungOS_Mongo_One` (NOT `kuropurchase` as spec says) |

---

## 1. PostgreSQL Schema — 34 Tables (verified 2026-04-29)

### 1.1 Table Inventory by Schema Area

#### Users Schema (8 tables)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `users_customuser` | 16 | `userid` | CustomUser model, `USERNAME_FIELD='phone'` |
| `users_accesslevel` | 55 | `id` | 50+ permission fields are **varchar** (not integer) |
| `users_user_tenant_context` | 9 | `id` | Field is `scope` (NOT `scope_type`) |
| `users_businessgroup` | 10 | `id` | Maps bg_code → db_name (legacy routing) |
| `users_kurouser` | 42 | `id` | Extended user profile — 6 new fields: `edit`, `paid_offs`, `phone_verified`, `businessgroups`, `primary_bg`, `festival_offs`, `roles` |
| `users_phonemodel` | 4 | `id` | OTP verification |
| `users_switchgroupmodel` | 4 | `id` | BG switching tokens |
| `users_common_counters` | 3 | `id` | Legacy counter tracking |

#### Platform Schema (2 tables)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `platform_outbox_events` | 11 | `event_id` (uuid) | NOT `id` (bigint) — confirmed |
| `platform_tenant_config` | 11 | `bg_code` | UNIQUE + PK on bg_code; 6 jsonb cfg columns |

#### Cafe Platform Schema (14 tables) — **ALL POSTGRESQL, NO MONGODB**

| Table | Cols | PK | Notes |
|---|---|---|---|
| `caf_platform_cafes` | 10 | `id` | Cafe registry |
| `caf_platform_stations` | 12 | `id` | UNIQUE `(cafe_id, code)` |
| `caf_platform_sessions` | 17 | `id` | 4 FKs: cafe_id, game_id, price_plan_id, station_id |
| `caf_platform_session_leases` | 8 | `id` | Lease versioning |
| `caf_platform_station_commands` | 9 | `id` | Station remote control |
| `caf_platform_station_events` | 8 | `id` | Station event log |
| `caf_platform_wallets` | 11 | `id` | UNIQUE wallet_id, customer_id; FK customer_id→users_customuser |
| `caf_platform_wallet_transactions` | 9 | `id` | FK wallet_id→caf_platform_wallets; FK created_by_id→users_customuser |
| `caf_platform_price_plans` | 15 | `id` | FK cafe_id; jsonb config |
| `caf_platform_member_plans` | 9 | `id` | UNIQUE plan_id, tier; seeded: edge/titan/s |
| `caf_platform_games` | 13 | `id` | Game catalog; FK cafe_id |
| `caf_platform_users` | 8 | `id` | Cafe user profiles |
| `caf_platform_walkins` | 5 | `id` | Walk-in customers |
| `caf_platform_auth_tokens` | 7 | `id` | Auth token storage |

#### KungOS Tenant Schema (4 tables)

| Table | Notes |
|---|---|
| `kungos_tenant_api_keys` | API key management |
| `kungos_tenant_domain_config` | Domain routing |
| `kungos_tenant_profile` | Tenant profile |
| `kungos_tenant_templates` | Email/content templates |

#### Tenant Entity Schema (4 tables) — `tenant` app

| Table | PK | FKs | Notes |
|---|---|---|---|
| `brands` | `id` (BIGSERIAL) | — | Brand identity: `brand_code` (VARCHAR(8)), `brand_name` (VARCHAR(50)) |
| `entities` | `id` (BIGSERIAL) | `brand_id` → brands.id (nullable) | Entity: `entity_code` (VARCHAR(8)), `entity_type` CHECK(trading/gaming/rentals/cafe), brand link |
| `entity_branches` | `id` (BIGSERIAL) | — | Branch: `entity_code` + `branch_code` + `branch_name`, UNIQUE(entity_code, branch_code), UNIQUE(entity_code, branch_name) |
| `bg_entity_branches` | `(bg_code, entity_code, branch_id)` composite | `branch_id` → entity_branches.id; composite FK `(entity_code, branch_id)` → entity_branches(entity_code, id) | BG↔Entity↔Branch junction. Composite FK enforces branch belongs to entity. |

**Tenant scope view:** `tenant_scope_view` — flat view joining all 4 tables for tenant resolver queries.

#### New Tenant Schema (4 tables) — `tenant` app, cascade code PKs

> **Replaces legacy Brand/Entity/EntityBranch/BgEntityBranch** with normalized cascade-code model.
> Legacy tables kept for backward compatibility during parallel run.

| Table | PK | FKs | Notes |
|---|---|---|---|
| `tenant_business_groups` | `bg_code` (VARCHAR(10)) | — | Legal entity. Code = first 4 letters of legal name + seq (e.g. `KURO0001`). Fields: `legal_name`, `tax_gst`, `tax_pan`, `db_name`, `licence_type`, `licence_cert` |
| `tenant_divisions` | `div_code` (VARCHAR(20)) | `bg` → tenant_business_groups.bg_code (`db_column='bg_code'`) | Operational division (replaces Entity). Code = `bg_code_XXX` (e.g. `KURO0001_001`). Fields: `brand_name`, `type`, `dj_apps`, `ent_status_code`, `ent_op_code`, `logo_url` |
| `tenant_branches` | `branch_code` (VARCHAR(30)) | `division` → tenant_divisions.div_code (`db_column='div_code'`) | Physical outlet. Code = `div_code_XXX` (e.g. `KURO0001_001_001`). Fields: `incharge_userid`, `pincode`, `inv_series_code`, `primary_bk` → tenant_bank_accounts |
| `tenant_bank_accounts` | `bank_code` (VARCHAR(20)) | `bg` → tenant_business_groups.bg_code (`db_column='bg_code'`) | Bank account per BG. Code = `bg_code_BK_XXX` (e.g. `KURO0001_BK_001`). Fields: `account_holder_name`, `account_type` |

**Current data:**
- 2 BusinessGroups: `KURO0001` (KURO CADENCE LLP), `DUNE0003` (DUNE LABS LLP)
- 4 Divisions: `KURO0001_001` (Kuro Gaming), `_002` (Rebellion), `_003` (RenderEdge), `DUNE0003_001` (Rebellion)
- 6 Branches across all divisions
- Nazarick Labs (`BG0002`) removed — no longer active

#### RBAC Tables (6 tables) — `users` app

> **Replaces legacy `users_accesslevel`** (40+ varchar columns). All roles are user-created (no system roles).

| Table | PK | FKs | Notes |
|---|---|---|---|
| `rbac_permissions` | `perm_code` (VARCHAR(50)) | — | Permission registry. 35 perms across modules: invoices, orders, products, inventory, sales, payments, financials, analytics, data, hr, admin |
| `rbac_roles` | `role_code` (VARCHAR(30)) | `parent_role` → self (`db_column='parent_role_code'`, nullable) | User-created roles. `is_system` flag reserved (currently all False). Single-level inheritance via parent_role |
| `rbac_role_permissions` | `(role_code, perm_code)` composite | FK → both parent tables | Permission level per role: 0=Revoked, 1=View, 2=Edit, 3=Supervisor |
| `rbac_user_roles` | `id` (BIGSERIAL) | `userid` → CustomUser, `role` → rbac_roles | Role assignment scoped by `bg_code` + `division` (nullable = BG-wide). UNIQUE(userid, role, bg_code, division) |
| `rbac_user_role_branches` | `(user_role_id, branch_code)` composite | FK → rbac_user_roles.id | Branch-level scoping for role assignments |
| `rbac_user_permissions` | `(userid, perm_code, bg_code, division)` composite | FK → CustomUser.userid, rbac_permissions.perm_code | Direct permission overrides. Fields: `level`, `reason`, `expires_at`, `granted_by`. Partial UNIQUE index on NULL division |

**Resolution engine:** `users/permissions.py` — `resolve_permission()` cascades: exact division → BG-wide → global. Max-level wins across all sources. Roles are always additive.

### 1.2 Critical Column Details (Verified via `information_schema.columns`)

#### `users_customuser` (16 cols)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `userid` | varchar | NOT NULL | — | **PRIMARY KEY** + indexed |
| `phone` | varchar | NOT NULL | — | UNIQUE + indexed |
| `username` | varchar | NULL | — | UNIQUE + indexed |
| `email` | varchar | NULL | — | UNIQUE + indexed |
| `name` | varchar | NOT NULL | — | |
| `password` | varchar | NOT NULL | — | |
| `usertype` | varchar | NULL | — | |
| `user_status` | varchar | NULL | — | |
| `last_login` | timestamptz | NULL | — | |
| `is_active` | boolean | NOT NULL | — | CHECK constraint |
| `is_staff` | boolean | NOT NULL | — | CHECK constraint |
| `is_superuser` | boolean | NOT NULL | — | CHECK constraint |
| `is_admin` | boolean | NOT NULL | — | CHECK constraint |
| `created_date` | timestamptz | NOT NULL | — | |
| `emailverified` | boolean | NOT NULL | `false` | |

#### `users_accesslevel` (55 cols) — CRITICAL: varchar permissions

**ALL 50+ permission fields are `character varying` (strings), NOT integers.** The only integer fields are `id` (bigint) and `analytics` (integer).

| Column | Type | Notes |
|---|---|---|
| `id` | bigint | PRIMARY KEY |
| `analytics` | **integer** | Only int field besides id |
| `branches` | jsonb | Entity branches array |
| `bg_code` | varchar | Business group |
| `entity` | varchar | Entity name |
| `userid` | varchar | User reference |
| `inward_invoices` | varchar | Permission field (string) |
| `inward_creditnotes` | varchar | Permission field (string) |
| `inward_debitnotes` | varchar | Permission field (string) |
| `outward_invoices` | varchar | Permission field (string) |
| `outward_creditnotes` | varchar | Permission field (string) |
| `outward_debitnotes` | varchar | Permission field (string) |
| `purchase_orders` | varchar | Permission field (string) |
| `purchases` | varchar | Permission field (string) |
| `counters` | varchar | Permission field (string) |
| `vendors` | varchar | Permission field (string) |
| `export_data` | varchar | Permission field (string) |
| `user_list` | varchar | Permission field (string) |
| `estimates` | varchar | Permission field (string) |
| `inward_payments` | varchar | Permission field (string) |
| `outward_payments` | varchar | Permission field (string) |
| `orders` | varchar | Permission field (string) |
| `offline_orders` | varchar | Permission field (string) |
| `online_orders` | varchar | Permission field (string) |
| `products` | varchar | Permission field (string) |
| `inventory` | varchar | Permission field (string) |
| `indent` | varchar | Permission field (string) |
| `stock` | varchar | Permission field (string) |
| `sales` | varchar | Permission field (string) |
| `outward` | varchar | Permission field (string) |
| `audit` | varchar | Permission field (string) |
| `tp_builds` | varchar | Permission field (string) |
| `bulk_payments` | varchar | Permission field (string) |
| `paymentvouchers` | varchar | Permission field (string) |
| `presets` | varchar | Permission field (string) |
| `service_request` | varchar | Permission field (string) |
| `hr` | varchar | Permission field (string) |
| `emp_attendance` | varchar | Permission field (string) |
| `employees_salary` | varchar | Permission field (string) |
| `employees` | varchar | Permission field (string) |
| `job_application` | varchar | Permission field (string) |
| `peripherals` | varchar | Permission field (string) |
| `portal_editor` | varchar | Permission field (string) |
| `pre_builts_finder` | varchar | Permission field (string) |
| `product_finder` | varchar | Permission field (string) |
| `replace_presets` | varchar | Permission field (string) |
| `financials` | varchar | Permission field (string) |
| `profile` | varchar | Permission field (string) |
| `bg_group` | varchar | Business group |
| `employee_accesslevel` | varchar | |
| `created_by` | varchar | NULL |
| `created_date` | timestamptz | NOT NULL |
| `updated_by` | varchar | NULL |
| `updated_date` | timestamptz | NULL |
| `is_active` | boolean | NOT NULL |

**Planned additions (NOT YET IMPLEMENTED — require migration):** `kungosadmin`, `cafedashboard`, `station_management`, `wallet_management`, `wallet_recharge`, `pricing_management`, `cafe_dashboard`, `cafe_sessions`, `cafe_payments`

#### `users_user_tenant_context` (9 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | bigint | NOT NULL | PRIMARY KEY |
| `userid` | varchar | NOT NULL | Index: `usr_tenant_uid_bg` (composite with bg_code) |
| `bg_code` | varchar | NOT NULL | Index: composite + standalone |
| `entity` | jsonb | NOT NULL | Multi-entity context |
| `branches` | jsonb | NOT NULL | Branch array |
| `token_key` | varchar | NULL | |
| `scope` | varchar | NOT NULL | **NOT `scope_type`** — confirmed |
| `created_at` | timestamptz | NOT NULL | |
| `updated_at` | timestamptz | NOT NULL | |

**Missing fields (planned, not current):** `permission_snapshot`, `switched_at`, `switched_by`, `request_defaults`

#### `platform_outbox_events` (11 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `event_id` | uuid | NOT NULL | **PRIMARY KEY** — NOT `id` (bigint) |
| `event_type` | varchar | NOT NULL | |
| `aggregate_type` | varchar | NOT NULL | |
| `aggregate_id` | varchar | NOT NULL | |
| `bg_code` | varchar | NOT NULL | Index: `pltf_outbox_bg_status` |
| `payload` | jsonb | NOT NULL | |
| `status` | varchar | NOT NULL | Index: `pltf_outbox_status_avail` |
| `retry_count` | integer | NOT NULL | |
| `available_at` | timestamptz | NOT NULL | |
| `processed_at` | timestamptz | NULL | |
| `error_message` | text | NOT NULL | |

**Indexes:** `(status, available_at)`, `(bg_code, status)`

#### `platform_tenant_config` (11 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `bg_code` | varchar | NOT NULL | **UNIQUE + PRIMARY KEY** |
| `brand_slug` | varchar | NOT NULL | |
| `business_type` | varchar | NOT NULL | |
| `features` | jsonb | NOT NULL | Feature flags |
| `payment_cfg` | jsonb | NOT NULL | |
| `sms_cfg` | jsonb | NOT NULL | |
| `wallet_cfg` | jsonb | NOT NULL | |
| `pricing_cfg` | jsonb | NOT NULL | |
| `theme_cfg` | jsonb | NOT NULL | |
| `integration_cfg` | jsonb | NOT NULL | |
| `status` | varchar | NOT NULL | |

#### `caf_platform_wallets` (11 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | bigint | NOT NULL | PRIMARY KEY |
| `wallet_id` | varchar | NOT NULL | UNIQUE |
| `balance` | numeric | NOT NULL | **No default of 0** — must be supplied by app |
| `membership_tier` | varchar | NOT NULL | |
| `points_earned` | integer | NOT NULL | |
| `total_spent` | numeric | NOT NULL | |
| `total_recharged` | numeric | NOT NULL | |
| `status` | varchar | NOT NULL | |
| `created_at` | timestamptz | NOT NULL | |
| `updated_at` | timestamptz | NOT NULL | |
| `customer_id` | varchar | NOT NULL | FK → `users_customuser.userid`, UNIQUE |

**Has FK:** `customer_id` → `users_customuser(userid)` — confirmed in `information_schema.referential_constraints`

#### `caf_platform_wallet_transactions` (9 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | bigint | NOT NULL | PRIMARY KEY |
| `amount` | numeric | NOT NULL | |
| `transaction_type` | varchar | NOT NULL | |
| `reference_type` | varchar | NULL | |
| `reference_id` | varchar | NULL | |
| `description` | text | NULL | |
| `created_at` | timestamptz | NOT NULL | Index: `caf_platfor_created_5f4eda_idx` |
| `created_by_id` | varchar | NULL | FK → `users_customuser` |
| `wallet_id` | bigint | NOT NULL | FK → `caf_platform_wallets.id` |

**Indexes:** `(wallet_id)`, `(reference_type, reference_id)`, `(created_at)`, `(created_by_id)`

#### `caf_platform_sessions` (17 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | bigint | NOT NULL | PRIMARY KEY |
| `status` | varchar | NOT NULL | Index: `caf_platfor_status_f8e037_idx` |
| `started_at` | timestamptz | NULL | |
| `ends_at` | timestamptz | NULL | |
| `ended_at` | timestamptz | NULL | |
| `billed_minutes` | integer | NOT NULL | |
| `amount_due` | numeric | NOT NULL | |
| `food_charges` | numeric | NOT NULL | |
| `total_charges` | numeric | NOT NULL | |
| `payment_status` | varchar | NOT NULL | |
| `started_by` | varchar | NOT NULL | |
| `ended_by` | varchar | NOT NULL | |
| `reason` | varchar | NOT NULL | |
| `cafe_id` | bigint | NOT NULL | FK + Index |
| `game_id` | bigint | NULL | FK + Index |
| `price_plan_id` | bigint | NOT NULL | FK + Index |
| `station_id` | bigint | NOT NULL | FK + Index |

**Composite indexes:** `(cafe_id, status)`, `(station_id, status)`

#### `caf_platform_stations` (12 cols)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | bigint | NOT NULL | PRIMARY KEY |
| `code` | varchar | NOT NULL | UNIQUE + Index |
| `name` | varchar | NOT NULL | |
| `zone` | varchar | NOT NULL | |
| `device_fingerprint` | varchar | NOT NULL | |
| `status` | varchar | NOT NULL | |
| `last_seen_at` | timestamptz | NULL | |
| `bg_code` | varchar | NOT NULL | |
| `created_at` | timestamptz | NOT NULL | |
| `updated_at` | timestamptz | NOT NULL | |
| `cafe_id` | bigint | NOT NULL | FK + Index |
| `current_session_id` | bigint | NULL | FK + Index |

**Unique constraint:** `(cafe_id, code)`

### 1.3 Key Constraints (All Verified via `information_schema`)

| Table | Constraint | Details |
|---|---|---|
| `users_customuser` | PK | `userid` |
| `users_customuser` | UNIQUE | `phone`, `email`, `username` |
| `users_accesslevel` | PK | `id` |
| `users_user_tenant_context` | PK | `id` |
| `users_user_tenant_context` | INDEX | `userid, bg_code` composite (`usr_tenant_uid_bg`) |
| `platform_outbox_events` | PK | `event_id` (uuid) |
| `platform_outbox_events` | INDEX | `(status, available_at)` (`pltf_outbox_status_avail`) |
| `platform_outbox_events` | INDEX | `(bg_code, status)` (`pltf_outbox_bg_status`) |
| `platform_tenant_config` | PK + UNIQUE | `bg_code` |
| `caf_platform_wallets` | PK | `id` |
| `caf_platform_wallets` | UNIQUE | `wallet_id`, `customer_id` |
| `caf_platform_wallets` | FK | `customer_id` → `users_customuser.userid` |
| `caf_platform_wallet_transactions` | FK | `wallet_id` → `caf_platform_wallets.id` |
| `caf_platform_wallet_transactions` | FK | `created_by_id` → `users_customuser` |
| `caf_platform_sessions` | FK | `cafe_id`, `game_id`, `price_plan_id`, `station_id` |
| `caf_platform_stations` | UNIQUE | `(cafe_id, code)` |
| `caf_platform_stations` | FK | `cafe_id` → `caf_platform_cafes.id` |
| `caf_platform_member_plans` | UNIQUE | `plan_id`, `tier` |

---

## 2. MongoDB Schema — 31 Collections, 68,443 Documents

### 2.1 Database

**Name:** `KungOS_Mongo_One` (underscores)  
**Spec says:** `kuropurchase` (wrong — only exists in management command help text)  
**MongoDB version:** 8

### 2.2 Collection Inventory

#### Tenant-Scoped Collections (31 collections, 68,443 docs) — 100% bgcode/entity/branch ✅

**All collections have been migrated.** The `restore_kuropurchase.py` management command populated `bgcode`, `entity`, and `branch` fields on every document during the kuropurchase → KungOS_Mongo_One migration.

| Collection | Docs | bgcode | entity | branch | (bgcode,entity) index | Notes |
|---|---|---|---|---|---|---|
| `purchaseorders` | 15,216 | ✅ | ✅ | ✅ | ✅ | ~99.96% kurogaming |
| `inwardpayments` | 21,026 | ✅ | ✅ | ✅ | ✅ | ~81% rebellion |
| `estimates` | 4,308 | ✅ | ✅ | ✅ | ✅ | 100% kurogaming |
| `misc` | 5,512 | ✅ | ✅ | ✅ | ✅ | Mixed entity |
| `products` | 82 | ✅ | ✅ | ✅ | ✅ | Retail products |
| `accounts` | 7 | ✅ | ✅ | ✅ | ✅ | 100% kurogaming |
| `players` | 117 | ✅ | ✅ | ✅ | ✅ | Esports players |
| `tournaments` | 3 | ✅ | ✅ | ✅ | ✅ | Esports tournaments |
| `reb_users` | 1,982 | ✅ | ✅ | ✅ | ✅ | Rebellion users |
| `kgorders` | 9,162 | ✅ | ✅ | ✅ | ✅ | Mixed (8561 rebellion, 601 kurogaming) |
| `tporders` | 229 | ✅ | ✅ | ✅ | ✅ | TP orders |
| `tpbuilds` | 123 | ✅ | ✅ | ✅ | ✅ | TP builds |
| `serviceRequest` | 1,625 | ✅ | ✅ | ✅ | ✅ | Service requests |
| `outward` | 754 | ✅ | ✅ | ✅ | ✅ | Outward documents |
| `outwardInvoices` | 1,165 | ✅ | ✅ | ✅ | ✅ | Outward invoices |
| `outwardCreditNotes` | 150 | ✅ | ✅ | ✅ | ✅ | Outward credit notes |
| `paymentVouchers` | 3,459 | ✅ | ✅ | ✅ | ✅ | Payment vouchers |
| `stock_register` | 194 | ✅ | ✅ | ✅ | ✅ | Stock register |
| `indentpos` | 247 | ✅ | ✅ | ✅ | ✅ | Indent positions |
| `indentproduct` | 1,490 | ✅ | ✅ | ✅ | ✅ | Indent products |
| `employee_attendance` | 966 | ✅ | ✅ | ✅ | ✅ | Employee attendance |
| `vendors` | 409 | ✅ | ✅ | ✅ | ✅ | Vendor records |
| `teams` | 14 | ✅ | ✅ | ✅ | ✅ | Teams |
| `presets` | 6 | ✅ | ✅ | ✅ | ✅ | Gaming presets |
| `tourneyregister` | 56 | ✅ | ✅ | ✅ | ✅ | Tournament registrations |
| `bgData` | 1 | ✅ | ✅ | ✅ | ✅ | BG metadata |
| `inwardCreditNotes` | 106 | ✅ | ✅ | ✅ | ✅ | Inward credit notes |
| `inwardDebitNotes` | 3 | ✅ | ✅ | ✅ | ✅ | Inward debit notes |
| `inwardInvoices` | 16 | ✅ | ✅ | ✅ | ✅ | Inward invoices |
| `outwardDebitNotes` | 13 | ✅ | ✅ | ✅ | ✅ | Outward debit notes |

**Note:** `reb_users` (with underscore) — NOT `rebusers` (no underscore).

**Note:** `entities` collection (2 docs) — entity metadata (logo, contact, bill/shipping addresses) for kurogaming and rebellion. Has `bgcode`, `entity`, `branch` fields and compound index. Added after initial migration.

**Migration note:** All tenant fields were populated by `restore_kuropurchase.py` during the kuropurchase → KungOS_Mongo_One migration. The legacy dump in `/home/chief/Coding-Projects/db/` contains pre-migration data (without `bgcode`/`branch`).

### 2.3 Entity Distribution

**Total:** 68,443 docs across 2 entities only. **No legacy/None entity.**

| Entity | Docs | % |
|---|---|---|
| `kurogaming` | 38,906 | 56.8% |
| `rebellion` | 29,537 | 43.2% |

**Per-collection breakdown (tenant-scoped collections):**

| Collection | kurogaming | rebellion | Notes |
|---|---|---|---|
| `purchaseorders` | 15,210 (99.96%) | 6 (0.04%) | ~100% kurogaming |
| `entities` | 1 (50.0%) | 1 (50.0%) | Entity metadata |
| `inwardpayments` | 3,899 (18.6%) | 17,127 (81.4%) | ~81% rebellion |
| `estimates` | 4,308 (100%) | 0 | 100% kurogaming |
| `accounts` | 7 (100%) | 0 | 100% kurogaming |
| `misc` | 1,752 (31.8%) | 3,760 (68.2%) | Mixed |

---

## 3. MongoDB → PostgreSQL Migration Map (Cafe Platform)

The original spec planned cafe data in MongoDB. All were moved to PostgreSQL for relational integrity and ACID billing.

### 3.1 Planned MongoDB Collections → Actual PostgreSQL Tables

| Was Planned (MongoDB) | Now In (PostgreSQL) | Reason |
|---|---|---|
| `stations` | `caf_platform_stations` (12 cols) | FKs to cafes, sessions, station_commands/events |
| `gamers` (enhanced) | `caf_platform_sessions` (17 cols) + `caf_platform_users` (8 cols) | Relational billing, wallet FKs, session state machine |
| `game_library` | `caf_platform_games` (13 cols) | FK to cafes, cafe-specific game catalog |
| `cafe_payments` | `caf_platform_wallet_transactions` (9 cols) | FK to wallets, transaction audit trail |

### 3.2 Additional PostgreSQL Tables (Not in Original Spec)

| Table | Cols | Purpose |
|---|---|---|
| `caf_platform_cafes` | 10 | Cafe registry (name, code, timezone, currency, bg_code, entity, status) |
| `caf_platform_session_leases` | 8 | Lease versioning for station timer authority |
| `caf_platform_station_commands` | 9 | Station remote control (lock, unlock, reboot) |
| `caf_platform_station_events` | 8 | Station event log (heartbeat, game launch, errors) |
| `caf_platform_wallets` | 11 | Shared wallet bridging cafe, esports, retail |
| `caf_platform_price_plans` | 15 | Zone-based pricing with peak/weekend multipliers |
| `caf_platform_member_plans` | 9 | Edge/Titan/S membership tiers with benefits |
| `caf_platform_walkins` | 5 | Optional non-registered customer tracking |
| `caf_platform_auth_tokens` | 7 | Auth token storage for cafe kiosk sessions |

### 3.3 MongoDB Collections — NOT Enhanced for Cafe Use

The following MongoDB collections were **not enhanced** for cafe use (the planned enhancements were abandoned when data moved to PostgreSQL):

| Collection | Was Planned Enhancement | Actual Status |
|---|---|---|
| `reb_users` | `station_role`, `customer_type`, `wallet_id`, `is_staff` | ❌ Not enhanced — staff lookup stays lightweight |
| `kgorders` | `order_type: cafe` | ❌ Not enhanced — cafe orders use PG sessions |
| `inwardpayments` | `session_id`, `payment_type` | ❌ Not enhanced — cafe payments in PG |
| `stock_register` | `product_type: food` | ❌ Not enhanced — cafe food orders separate |
| `gamers` | Full field expansion | ❌ Not enhanced — gamers → PG sessions |

---

## 4. Gaming Integration Gap

### 4.1 Missing Collections (12 of 13)

The kuro-gaming-dj-backend codebase exists at `/home/chief/Coding-Projects/kuro-gaming-dj-backend` but has NOT been merged into kteam-dj-chief.

| # | Collection | Gaming Code Reference | Status |
|---|---|---|---|
| 1 | `prods` | `db['prods']` (products/views.py:19) | ❌ MISSING |
| 2 | `builds` | `db['builds']` (products/views.py:17) | ❌ MISSING |
| 3 | `kgbuilds` | `db['kgbuilds']` (products/views.py:18) | ❌ MISSING |
| 4 | `custombuilds` | `db['custombuilds']` (products/views.py:20) | ❌ MISSING |
| 5 | `components` | `db['components']` (products/views.py:21) | ❌ MISSING |
| 6 | `accessories` | `db['accessories']` (products/views.py:22) | ❌ MISSING |
| 7 | `monitors` | `db['monitors']` (products/views.py:23) | ❌ MISSING |
| 8 | `networking` | `db['networking']` (products/views.py:24) | ❌ MISSING |
| 9 | `external` | `db['external']` (products/views.py:25) | ❌ MISSING |
| 10 | `games` | games app | ❌ MISSING |
| 11 | `kurodata` | `db['kurodata']` (products/views.py:219) | ❌ MISSING |
| 12 | `lists` | `db['lists']` (products/views.py:176) | ❌ MISSING |
| 13 | `presets` | `db['presets']` (kuroadmin/views.py:45) | ✅ EXISTS (6 docs) |

**Result: 12/13 gaming collections missing (92%). Only `presets` exists.**

### 4.2 Missing PostgreSQL Models (5)

The kuro-gaming-dj-backend defines these models but they are NOT in kteam-dj-chief:

| Model | Purpose | Status |
|---|---|---|
| `Cart` | Shopping cart | ❌ NOT MERGED |
| `Wishlist` | Wishlist | ❌ NOT MERGED |
| `Addresslist` | Customer addresses | ❌ NOT MERGED |
| `Orders` | E-commerce orders | ❌ NOT MERGED |
| `OrderItems` | Order line items | ❌ NOT MERGED |

### 4.3 Root Cause

- None of the 5 gaming apps (`accounts`, `products`, `orders`, `payment`, `games`) are in `INSTALLED_APPS`
- The separate `products` MongoDB database (which held the gaming data) no longer exists
- Gaming views reference 13 collection names via variables but these collections don't exist in any database

---

## 5. Tenant Field Coverage

### 5.1 Status: ALL 31 Collections Migrated ✅

All 31 collections have `(bgcode, entity, branch)` fields on 100% of documents.

**Migration completed via:** `python manage.py restore_kuropurchase --dump <file> --restore`

**Compound index coverage:** 31/31 collections have `(bgcode, entity)` compound index — all complete ✅

### 5.2 Complete — All Compound Indices Added ✅

All 31 collections now have `(bgcode, entity)` compound indexes. No remaining actions.

---

## 6. Constraints & Security Status

### 6.1 PostgreSQL RLS — NOT IMPLEMENTED ⚠️

**Status:** Zero tables have RLS enabled. Zero RLS policies exist.

Tenant isolation in PostgreSQL relies entirely on **application-level filtering** (tenant context in views, `TenantCollection` wrapper for MongoDB). This is a known gap — RLS was planned in Phase 1 P0 #3 but deferred.

**Risk:** A rogue query or ORM bypass could access other tenants' data at the DB level.

**Recommendation:** Implement RLS on all tenant-scoped tables before production cutover, or document that app-level filtering is the enforced strategy.

### 6.2 CHECK Constraints

| Table | Constraint | Status |
|---|---|---|
| `users_customuser` | Boolean fields (is_active, is_staff, etc.) | ✅ Enforced by boolean type (no explicit CHECK needed) |
| `entities` | `entity_type IN ('trading', 'gaming', 'rentals', 'cafe')` | ✅ Added 2026-04-29 |

### 6.3 Legacy Tables Removed

| Table | Action | Date |
|---|---|---|
| `knox_authtoken` | **DROPPED** — Knox auth removed from INSTALLED_APPS, 129 stale rows purged | 2026-04-29 |

### 6.4 Undocumented Tables (Excluded from This Doc)

| Table | Cols | Purpose | Notes |
|---|---|---|---|
| `careers_jobapps` | 21 | Careers/jobs app | KungOS app table, not yet documented |
| `auth_group` | 2 | Django auth groups | Framework table |
| `auth_group_permissions` | 3 | Django auth | Framework table |
| `auth_permission` | 4 | Django auth | Framework table |
| `django_admin_log` | 8 | Django admin | Framework table |
| `django_content_type` | 3 | Django ORM | Framework table |
| `django_migrations` | 4 | Django migrations | Framework table |
| `django_session` | 3 | Django sessions | Framework table |
| `token_blacklist_blacklistedtoken` | 3 | JWT blacklist | Framework table |
| `token_blacklist_outstandingtoken` | 6 | JWT outstanding | Framework table |

### 6.5 MongoDB Extra Databases

| Database | Collections | Purpose |
|---|---|---|
| `tmp` | `mongo_backup` | Backup staging area |

---

## 7. Management Commands

| Command | Purpose | DB Target |
|---|---|---|
| `backup_kuropurchase` | Pre-restore backup of all collections to JSON | `KungOS_Mongo_One` |
| `restore_kuropurchase` | Parse MongoDB 8.0+ concurrent dump, restore with entity population | `KungOS_Mongo_One` |

**Note:** Command name says `kuropurchase` but targets `KungOS_Mongo_One`. The name is legacy from the spec.

---

## 8. References

| Document | Purpose |
|---|---|
| [`kungos_v2_db.md`](./kungos_v2_db.md) | **This file** — single source of truth for DB schema |
| [`KungOS_v2.md`](./KungOS_v2.md) | Master modernization plan (architecture, phases, cutover) |
| [`kungos-cafe-platform.md`](./kungos-cafe-platform.md) | Cafe platform design spec (14 PG tables, API endpoints, station platform) |
| [`kungos_db_test_plan.md`](./kungos_db_test_plan.md) | Database testing plan (execution steps for validation) |
| [`kungos_mongo_divergence.md`](./kungos_mongo_divergence.md) | Spec vs reality analysis (13 gaming collections missing, DB name discrepancy) |
| `CAFE_PLATFORM.md` | DJ repo copy of cafe platform spec (identical to `kungos-cafe-platform.md`) |

---

**Last verified:** 2026-04-29 against live PostgreSQL 16 and MongoDB 8 databases.
**Audit fixes applied 2026-04-29:** brand_slug corrected (BG0001→kurogaming), entities CHECK constraint added, knox_authtoken dropped, collection count updated to 31, bgData index confirmed present.  
**Next verification:** Before any schema migration or gaming integration merge.  
**Tenant field migration date:** 2026-04-23 (via `restore_kuropurchase.py` management command)
