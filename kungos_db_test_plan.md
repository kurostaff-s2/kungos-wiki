# KungOS v2 — Database Testing Plan

**Ground-truthed:** 2026-04-29 (verified against live databases)  
**Sources:** PostgreSQL 16 introspection, MongoDB 8 introspection (`KungOS_Mongo_One`), kuro-gaming-dj-backend code scan, `backend/utils.py` routing scan, Django `INSTALLED_APPS` scan  
**Purpose:** Validate schema integrity, tenant isolation, migration safety, data quality, and gaming integration status

---

## Synthesis Summary

Three sources were consolidated:
1. **Original kungos_db_test_plan.md** — initial ground-truth dump of table names, columns, collections
2. **db_testing-claude.md** — AI-generated test code that was cross-referenced against ground truth (11/11 topics matched; code had `[^0]` syntax errors)
3. **kungos_mongo_divergence.md** — analysis of spec vs. reality (13 gaming collections missing, gaming backend unmerged, DB name discrepancy, cafe platform moved to PG)

**Key decisions from synthesis:**
- All PostgreSQL table/column names, types, constraints, and indexes are from live introspection
- MongoDB data from live `KungOS_Mongo_One` introspection (30 collections, 68,441 docs)
- Gaming gap documented from kuro-gaming-dj-backend code scan and INSTALLED_APPS check
- `db_testing-claude` test code is the implementation reference (after fixing `[^0]` → `[0]`)

---

## 1. PostgreSQL Schema Validation

### 1.1 Table Inventory (35 tables across 4 schema areas)

All names are **exact** — verified via `information_schema.tables`. No aliases or heuristics.

#### Users Schema (7 tables)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `users_customuser` | 16 | `userid` | CustomUser model, `USERNAME_FIELD='phone'` |
| `users_accesslevel` | 55 | `id` | 50+ permission fields are **varchar** (not integer) |
| `users_user_tenant_context` | 9 | `id` | Field is `scope` (not `scope_type`) |
| `users_businessgroup` | 10 | `id` | Maps bg_code → db_name (legacy routing) |
| `users_kurouser` | 36 | `id` | Extended user profile |
| `users_phonemodel` | 4 | `id` | OTP verification |
| `users_switchgroupmodel` | 4 | `id` | BG switching tokens |
| `users_common_counters` | 3 | `id` | Legacy counter tracking |

#### Platform Schema (2 tables)

| Table | Cols | PK | Notes |
|---|---|---|---|
| `platform_outbox_events` | 11 | `event_id` (uuid) | NOT `id` (bigint) — confirmed |
| `platform_tenant_config` | 11 | `bg_code` | UNIQUE + PK on bg_code; 6 jsonb cfg columns |

#### Cafe Platform Schema (14 tables)

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

## 2. MongoDB Schema Validation

### 2.1 Database

**Name:** `KungOS_Mongo_One` (underscores)  
**Spec says:** `kuropurchase` (wrong — only exists in management command help text)  
**MongoDB version:** 8

### 2.2 Collection Inventory (30 collections, 68,441 docs)

#### Tenant-Scoped Collections (30 collections, 68,441 docs) — 100% bgcode/entity/branch ✅

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
| `bgData` | 1 | ✅ | ✅ | ✅ | ❌ | BG metadata — **needs compound index** |
| `inwardCreditNotes` | 106 | ✅ | ✅ | ✅ | ✅ | Inward credit notes |
| `inwardDebitNotes` | 3 | ✅ | ✅ | ✅ | ✅ | Inward debit notes |
| `inwardInvoices` | 16 | ✅ | ✅ | ✅ | ✅ | Inward invoices |
| `outwardDebitNotes` | 13 | ✅ | ✅ | ✅ | ✅ | Outward debit notes |

**Note:** `reb_users` (with underscore) — NOT `rebusers` (no underscore).

**Migration note:** All tenant fields were populated by `restore_kuropurchase.py`. The legacy dump in `/home/chief/Coding-Projects/db/` contains pre-migration data (without `bgcode`/`branch`).

### 2.3 Entity Distribution

**Total:** 68,441 docs across 2 entities only. **No legacy/None entity.**

| Entity | Docs | % |
|---|---|---|
| `kurogaming` | 38,905 | 56.8% |
| `rebellion` | 29,536 | 43.2% |

**Per-collection breakdown (tenant-scoped collections):**

| Collection | kurogaming | rebellion | Notes |
|---|---|---|---|
| `purchaseorders` | 15,210 (99.96%) | 6 (0.04%) | ~100% kurogaming |
| `inwardpayments` | 3,899 (18.6%) | 17,127 (81.4%) | ~81% rebellion |
| `estimates` | 4,308 (100%) | 0 | 100% kurogaming |
| `accounts` | 7 (100%) | 0 | 100% kurogaming |
| `misc` | 1,752 (31.8%) | 3,760 (68.2%) | Mixed |

### 2.4 Missing Collections (17 total)

#### Moved to PostgreSQL (4 collections)

| Collection | PG Replacement | Reason |
|---|---|---|
| `gamers` | `caf_platform_sessions` + `caf_platform_users` | Cafe platform moved to PG for relational integrity |
| `cafepayments` | `caf_platform_wallet_transactions` | Wallet transactions in PG |
| `stations` | `caf_platform_stations` | Station registry in PG |
| `game_library` | `caf_platform_games` | Game catalog in PG with FK to cafes |

#### Gaming Integration Not Yet Merged (13 collections)

| Collection | Gaming Code Reference | Status |
|---|---|---|
| `prods` | `db['prods']` (products/views.py:19) | ❌ Phase 3 |
| `builds` | `db['builds']` (products/views.py:17) | ❌ Phase 3 |
| `kgbuilds` | `db['kgbuilds']` (products/views.py:18) | ❌ Phase 3 |
| `custombuilds` | `db['custombuilds']` (products/views.py:20) | ❌ Phase 3 |
| `components` | `db['components']` (products/views.py:21) | ❌ Phase 3 |
| `accessories` | `db['accessories']` (products/views.py:22) | ❌ Phase 3 |
| `monitors` | `db['monitors']` (products/views.py:23) | ❌ Phase 3 |
| `networking` | `db['networking']` (products/views.py:24) | ❌ Phase 3 |
| `external` | `db['external']` (products/views.py:25) | ❌ Phase 3 |
| `games` | games app | ❌ Phase 3 |
| `kurodata` | `db['kurodata']` (products/views.py:219) | ❌ Phase 3 |
| `lists` | `db['lists']` (products/views.py:176) | ❌ Phase 3 |
| `tempproducts` | `db['tempproducts']` (kuroadmin/views.py:45) | ❌ Phase 3 |

### 2.5 Compound Index Coverage

All 9 tenant-scoped collections have the `(bgcode, entity)` compound index.

---

## 3. Gaming Integration Gap (NEW from divergence analysis)

### 3.1 kuro-gaming-dj-backend Status

| Item | Spec | Reality | Impact |
|---|---|---|---|
| 5 Django apps in INSTALLED_APPS | ✅ | ❌ **Not installed** | No gaming API endpoints |
| 13 MongoDB collections in KungOS_Mongo_One | ✅ | ❌ **12/13 missing** | Gaming storefront broken |
| 5 PG models (Cart, Wishlist, etc.) | ✅ | ❌ **None exist** | No gaming data layer |
| Separate `products` MongoDB DB | — | ❌ **Deleted** | Gaming source data lost |
| kurogg-nextjs frontend | ✅ | Retire | Frontend pages need migration |

### 3.2 Gaming Code References (from kuro-gaming-dj-backend scan)

The kuro-gaming-dj-backend repo at `/home/chief/Coding-Projects/kuro-gaming-dj-backend` has:

**Products views reference 13 collections:**
```python
# products/views.py:17-25
build_collection = 'builds'
kgbuild_collection = 'kgbuilds'
prod_collection = 'prods'
custombuild_collection = 'custombuilds'
comp_collection = 'components'
accessory_collection = 'accessories'
monitor_collection = 'monitors'
networking_collection = 'networking'
external_collection = 'external'
# Also: 'presets', 'lists', 'kurodata' (direct strings)
```

**Kuroadmin views reference 13 collections:**
```python
# kuroadmin/views.py:38-50
prod_collection = 'prods'
build_collection = 'builds'
kgbuild_collection = 'kgbuilds'
custombuild_collection = 'custombuilds'
preset_collection = 'presets'
misc_collection = 'misc'
kurodata_collection = 'kurodata'
tempprod_collection = 'tempproducts'
comp_collection = 'components'
accessory_collection = 'accessories'
monitor_collection = 'monitors'
networking_collection = 'networking'
external_collection = 'external'
```

**Gaming PG models defined but not merged:**
- `accounts.models.Cart` — `cartid`, `productid`, `category`, `quantity`
- `accounts.models.Wishlist` — `wishid`, `productid`, `category`
- `accounts.models.Addresslist` — `addressid`, `fullname`, `phone`, `pincode`, `city`, `state`
- `orders.models.Orders` — 40 fields, 11-stage lifecycle
- `orders.models.OrderItems` — `productid`, `title`, `components`, `price`, `quantity`

### 3.3 Blocking Impact

| Blocker | Blocks | Fix |
|---|---|---|
| 12/13 gaming collections missing | Product catalog, cart, orders, payment | Migrate gaming data from backup/source |
| 5 apps not in INSTALLED_APPS | Any gaming API endpoint | Add apps + create PG models |
| Per-BG routing still in utils.py | Tenant isolation not fully enforced | Replace with TenantCollection |
| bgData missing compound index | Query perf on tenant filter | Add (bgcode, entity) index

---

## 4. Migration Command Tests

### 4.1 Existing Commands (9 commands — Test These)

| Command | Test Focus |
|---|---|
| `restore_kuropurchase` | Dry-run safety, entity population, duplicate handling (52 dupes), `--verify`, `--output report.json` |
| `backup_kuropurchase` | Backup creation, overwrite handling |
| `deploy_restore` | Orchestration sequence (backup → restore → verify) |
| `reconcile_user_models` | User identity reconciliation |
| `seed_games` | Idempotent seeding |
| `seed_member_plans` | Idempotent seeding |
| `seed_pricing` | Idempotent seeding |
| `seed_stations` | Idempotent seeding |
| `seed_tenant_config` | Idempotent seeding |

### 4.2 Missing Commands (2 commands — Mark as Skip)

| Command | Reason |
|---|---|
| `verify_tenant_isolation` | Phase 1 P2 #3 — not yet implemented |
| `migrate_gamers_to_enhanced` | Gamers moved to PostgreSQL — command irrelevant |

### 4.3 Test Scenarios for `restore_kuropurchase`

| Scenario | Expected | Priority |
|---|---|---|
| Dry-run with dump file | Reports doc counts, entity distribution, does NOT write | 🔴 Critical |
| Dry-run without dump | Fails with clear error (not traceback) | 🔴 Critical |
| Entity population | All docs have bgcode, entity, branch populated | 🔴 Critical |
| Duplicate `_id` handling | 52 duplicates skipped, not duplicated | 🔴 Critical |
| `--verify` mode | Reports 0 docs missing entity, 100% coverage | 🔴 Critical |
| `--output report.json` | Valid JSON with entity_distribution key | 🟡 Medium |
| Real restore | Creates collections, populates documents | 🟡 Medium |
| Restore idempotency | Running twice doesn't duplicate documents | 🟡 Medium |

---

## 5. Tenant Isolation Tests

### 5.1 TenantCollection Wrapper

`plat/tenant/collection.py` — **Exists and functional.**

| Test | Expected |
|---|---|
| Import succeeds | `from plat.tenant.collection import TenantCollection` |
| Missing context raises | `TenantContextMissing` when no context set |
| Valid context accepted | `set_tenant_context(bg_code, entity, branches)` works |
| Auto-injects bgcode filter | Every `find()` includes `bgcode` in query |
| Wrong bgcode returns empty | BG9999 sees 0 docs from BG0001 |

### 5.2 Per-BG Routing Scan

**FAILING:** Old pattern `client[bg.db_name]` found in `backend/utils.py`.

| Location | Pattern | Status |
|---|---|---|
| `backend/utils.py:288` | `db = client[bg.db_name]` | ❌ Must be replaced with TenantCollection |
| `backend/utils.py:339` | `db = client[bg.db_name]` | ❌ Must be replaced with TenantCollection |

**Other raw `db[]` access (migration commands, exempt):**
- `users/management/commands/migrate_mongodb_to_unified.py` — migration tool, acceptable
- `teams/management/commands/restore_full_backup.py` — migration tool, acceptable

### 5.3 PostgreSQL RLS

**Status:** Not yet enforced. `users_user_tenant_context` exists but RLS not confirmed active.

| Test | Expected |
|---|---|
| RLS enabled on tenant tables | `relrowsecurity = True` on `users_user_tenant_context` |
| RLS blocks wrong BG | `SET app.current_bg_code = 'BG9999'` returns 0 rows for BG0001 |

---

## 6. Data Quality Tests

### 6.1 Wallet Financial Integrity

| Test | Expected |
|---|---|
| Balance never negative | All `caf_platform_wallets.balance >= 0` |
| Transaction amounts match | `SUM(amount)` per wallet matches balance delta |
| Transaction type valid | `transaction_type` in (`recharge`, `spend`, `refund`, `adjustment`, `prize_winnings`) |
| No duplicate transactions | `(wallet_id, created_at, amount, transaction_type)` is unique |

### 6.2 Session Billing Consistency

| Test | Expected |
|---|---|
| `total_charges = amount_due + food_charges` | All sessions |
| `billed_minutes >= 0` | All sessions |
| `ended_at >= started_at` | All ended sessions |
| `payment_status` valid | In (`unpaid`, `paid`, `partial`, `refunded`) |
| Station released after end | `caf_platform_stations.current_session_id` is NULL for ended sessions |

### 6.3 Station State Consistency

| Test | Expected |
|---|---|
| `status` valid | In (`offline`, `idle`, `reserved`, `in_session`, `locked`, `error`) |
| `current_session_id` consistency | If not NULL, referenced session exists and status = `in_session` |
| `cafe_id` valid | References existing `caf_platform_cafes` |
| `bg_code` matches cafe | Station bg_code matches its cafe's bg_code |

### 6.4 Price Plan Validity

| Test | Expected |
|---|---|
| `rate_per_hour > 0` | All price plans |
| `min_minutes > 0` | All price plans |
| `max_minutes >= min_minutes` | All price plans |
| `peak_multiplier >= 1.0` | All price plans |
| `weekend_multiplier >= 1.0` | All price plans |
| `billing_mode` valid | In (`hourly`, `flat`, `membership`) |
| `cafe_id` valid | References existing cafe |

### 6.5 Member Plan Validity

| Test | Expected |
|---|---|
| `tier` unique | `edge`, `titan`, `s` (3 tiers seeded) |
| `price_per_month > 0` | All plans |
| `benefits` is valid JSON | All plans |
| `bg_code` valid | References existing business group |

---

## 7. Test File Structure & Implementation Reference

```
tests/
├── conftest.py                        # Shared fixtures (DB connections, helpers)
├── test_db_schema_postgres.py         # §1 — PostgreSQL schema (45 tests)
├── test_db_schema_mongodb.py          # §2 — MongoDB schema (25 tests)
├── test_gaming_integration.py         # §3 — Gaming gap verification (10 tests)
├── test_migration_commands.py         # §4 — Migration commands (12 tests)
├── test_tenant_isolation.py           # §5 — Tenant isolation (10 tests)
├── test_data_quality.py               # §6 — Data quality (20 tests)
└── test_db_performance.py             # §7 — Index performance (8 tests)
```

### Implementation Reference

Use `db_testing-claude.md` as the implementation reference for `conftest.py`, `test_db_schema_postgres.py`, `test_db_schema_mongodb.py`, `test_migration_commands.py`, `test_tenant_isolation.py`, and `test_data_quality.py`.

**Required fix before use:** Replace all `[^0]` with `[0]` (22 instances). This is a syntax error artifact from the source file.

### New File: `test_gaming_integration.py`

This file is not in `db_testing-claude.md` — it must be created to cover the gaming gap:

```
Tests:
- 13 gaming collections are MISSING (not yet merged)
- 5 gaming apps are NOT in INSTALLED_APPS
- 5 gaming PG models do NOT exist
- kuro-gaming-dj-backend code references collections that don't exist
- All marked pytest.mark.skip(reason="Phase 3: gaming integration pending")
```

---

## 8. Test Execution Matrix

| Test File | What It Guards | Tests | Run Without Dump |
|---|---|---|---|
| `test_db_schema_postgres.py` | 35 PG tables, 190+ columns, constraints, indexes | ~45 | ✅ |
| `test_db_schema_mongodb.py` | 30 collections, tenant coverage, entity dist, indexes | ~25 | ✅ |
| `test_gaming_integration.py` | Gaming gap: missing collections, unmerged apps, unmerged models | ~10 | ✅ |
| `test_migration_commands.py` | Dry-run safety, entity population, duplicate handling, `--verify` | ~12 | ⚠️ Partial |
| `test_tenant_isolation.py` | TenantCollection wrapper, per-BG routing scan, RLS status | ~10 | ✅ |
| `test_data_quality.py` | Wallet integrity, session billing, station consistency | ~20 | ✅ |
| `test_db_performance.py` | Index usage, query plans, N+1 detection | ~8 | ✅ |

---

## 9. Quick Run Commands

```bash
# Schema only (fastest, ~5s):
cd /home/chief/Coding-Projects/kteam-dj-chief
python -m pytest tests/test_db_schema_postgres.py tests/test_db_schema_mongodb.py -v

# Isolation only (~5s):
python -m pytest tests/test_tenant_isolation.py -v

# Data quality only (~10s):
python -m pytest tests/test_data_quality.py -v

# Gaming gap only (~5s):
python -m pytest tests/test_gaming_integration.py -v

# Full suite (~60s):
python -m pytest tests/ -k "db_schema or data_quality or tenant_isolation or gaming" -v

# With dump (migration tests):
E2E_DUMP_PATH=/path/to/mongodump python -m pytest tests/test_migration_commands.py -v
```

---

## 10. Phase-Gated Additions

These tests exist in the plan but are gated on future work:

| Test | Depends On | Priority |
|---|---|---|
| Accesslevel cafe permission fields (`kungosadmin`, `cafedashboard`, etc.) | Django migration for new fields | 🟡 Phase 3 |
| `verify_tenant_isolation` management command | Phase 1 P2 #3 | 🟡 Phase 1 |
| Gaming product collections (`prods`, `builds`, etc.) | Phase 3 gaming integration | 🔴 High |
| Gaming MongoDB tenant filtering | Phase 3b multi-tenant | 🟡 Phase 3b |
| Gaming PG models (Cart, Wishlist, etc.) | Phase 3 gaming integration | 🔴 High |
| Station Desktop MongoDB tables | Station Desktop Platform | 🟢 Phase 4 |
| Per-BG routing removal in `backend/utils.py` | TenantCollection migration | 🔴 High |
| `bgData` compound index | None — can run now | 🟢 Immediate |
| Tenant fields on legacy collections | ✅ COMPLETE (2026-04-23) | ✅ Done |

---

## 11. Exit Criteria

The DB testing plan is complete when:

1. **All 35 PostgreSQL schemas** validated against ground-truth (table names, column types, nullability, constraints, indexes)
2. **All 30 MongoDB collections** verified for existence and tenant field coverage (100% bgcode/entity/branch on ALL 30 — migration complete via restore_kuropurchase.py)
3. **Entity distribution** matches expected patterns within 5% tolerance (56.8% kurogaming / 43.2% rebellion)
4. **13 gaming collections confirmed missing** — gaming integration gap documented and tracked
5. **5 gaming apps confirmed not installed** — INSTALLED_APPS gap documented
6. **5 gaming PG models confirmed absent** — data layer gap documented
7. **Migration dry-run** verified: no writes, correct counts, entity population, duplicate handling
8. **Tenant isolation** confirmed: TenantCollection works, per-BG routing removed (0 `client[bg.db_name]` in non-migration code), 0 leaks
9. **Data integrity** verified: wallet balances consistent, session billing correct, station state consistent
10. **Planned fields** (cafe permissions, verify_tenant_isolation, etc.) marked as skip with migration tracking
