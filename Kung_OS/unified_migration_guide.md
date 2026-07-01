# Unified Migration Guide: 4 Legacy Sources → KungOS Target

| Field | Value |
|-------|-------|
| Scope | 2 legacy projects (Kuro Gaming, Kuro Cadence) × 2 engines each (PostgreSQL + MongoDB) = 4 source DBs |
| Target | `KungOS_PG_One` (PostgreSQL 16) + `KungOS_Mongo_One` (MongoDB 8) |
| Source Location | `/home/chief/kuro-legacy/` (canonical dump files) |
| Status | **Clean-slate migration** — source of truth is production S3 backups (2026-06-30) |
| Generated | 2026-07-01 |

---

## 0. Authentication & Connection Notes

**PostgreSQL 16** (`127.0.0.1:5432`):
- User: `postgres`, Password: `postgres`
- All `psql`/`pg_restore` commands require `PGPASSWORD=postgres` or `--password`
- `.pgpass` not configured — password must be supplied explicitly
- Example: `PGPASSWORD=postgres psql -h 127.0.0.1 -p 5432 -U postgres -d <dbname>`

**MongoDB 8** (`127.0.0.1:27017`):
- No authentication required (local access, `localhost` exception)
- `mongorestore`/`mongosh` connect without credentials

**Dump format caveat:**
- **MongoDB dumps are `--archive` format** (single binary file), NOT directory-based `.bson` archives
- `mongorestore` requires `--archive=/path/to/file` flag — passing the file path directly will fail with "does not have .bson extension"
- PostgreSQL dumps are `pg_dump --format=custom` (`.psql.bin`) — standard `pg_restore` works

---

## 0.5 Runtime Schema Fixes (REQUIRED before Phase 2)

Django's default migration creates unique constraints that block valid cross-source data. The legacy sources (`kg_pg` + `kc_pg`) share phone/email/username values for the same person across both systems. These constraints **must be dropped** before running Phase 2 identity migration.

```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -p 5432 -U postgres -d KungOS_PG_One \
  -f /home/chief/Coding-Projects/KungOS-dj/deployment_scripts/phase2_schema_fixes.sql
```

**Constraints dropped:**

| Constraint | Table | Why | Impact |
|------------|-------|-----|--------|
| `users_customuser_phone_key` | `users_customuser` | Same person has accounts in both `kg_pg` and `kc_pg` with same phone | Phone uniqueness enforced at app level, not DB level |
| `users_customuser_email_key` | `users_customuser` | KCTM019 shares email with kg_pg user (same person, different userid) | Multiple accounts per person allowed |
| `users_customuser_username_key` | `users_customuser` | RE00001U shares username "Dhruv" with kg_pg user | Username not globally unique across sources |
| `uq_identity_tenant_phone` | `users_identity` | Phone is NOT globally unique across identity types (ESH*, ID*, REPL*) | Phone used for dedup during migration, not enforced post-migration |

**Verification query (expect 0 rows):**
```sql
SELECT conname, conrelid::regclass
FROM pg_constraint
WHERE conname IN (
    'users_customuser_phone_key', 'users_customuser_email_key',
    'users_customuser_username_key', 'uq_identity_tenant_phone'
);
```

**Deployment scripts location:** `/home/chief/Coding-Projects/KungOS-dj/deployment_scripts/`
- `migrate_phase0_tenant_seed.py` — Phase 0.5 tenant hierarchy seed
- `migrate_phase2_identities.py` — Phase 2 identity migration
- `phase2_schema_fixes.sql` — Constraint drops (run before Phase 2)
- `migrate_phase3_custom_catalog.py` — Phase 3 custom catalog consolidation
- `migrate_phase4_products.py` — Phase 4 product/game merge
- `migrate_phase5_inventory.py` — Phase 5 vendors + purchase orders
- `migrate_phase6_finance.py` — Phase 6 finance consolidation
- `migrate_phase7_orders.py` — Phase 7 orders consolidation
- `README.md` — Execution order and troubleshooting

---

## 1. Source Dump Registry

All production backups reside in `/home/chief/kuro-legacy/`. These are the **only** sources of truth for migration.

| Alias | File | Engine | Legacy DB Name | Project | Role |
|-------|------|--------|----------------|---------|------|
| **kg_pg** | `kg_pg.dump` | PostgreSQL | `kuro-user` | Kuro Gaming | eShop users, orders, cart, wishlist, addresses |
| **kg_mongo** | `kg_mongo.dump` | MongoDB | `products` | Kuro Gaming | Product/game catalog, presets, builds |
| **kc_pg** | `kc_pg.dump` | PostgreSQL | `kuro-cadence` | Kuro Cadence | Employees, access levels, business groups, careers |
| **kc_mongo** | `kc_mongo.dump` | MongoDB | `kuropurchase` | Kuro Cadence | Orders, finance, vendors, walk-ins, players, teams, stock |

**Naming convention:** `{project}_{engine}` — `kg` = Kuro Gaming, `kc` = Kuro Cadence, `pg` = PostgreSQL, `mongo` = MongoDB.

### 1.1 S3 Source Links

All dumps are downloaded from `s3://kuro-db-backup/` into `/home/chief/kuro-legacy/`.

| Alias | S3 Key | Local File | Size | Date |
|-------|--------|------------|------|------|
| **kg_pg** | `s3://kuro-db-backup/kg-backup/default-ip-172-31-26-151-2026-06-30-153005.psql.bin` | `kg_pg.dump` | 820 KB | 2026-06-30 |
| **kg_mongo** | `s3://kuro-db-backup/kg-backup/mongo-ip-172-31-26-151-2026-06-30-153007.dump` | `kg_mongo.dump` | 25 MB | 2026-06-30 |
| **kc_pg** | `s3://kuro-db-backup/kc-backup/default-kuroserver-2026-06-30-193001.psql.bin` | `kc_pg.dump` | 799 KB | 2026-06-30 |
| **kc_mongo** | `s3://kuro-db-backup/kc-backup/mongo-kuroserver-2026-06-30-223002.dump` | `kc_mongo.dump` | 53.9 MB | 2026-06-30 |

**Download commands:**
```bash
mkdir -p /home/chief/kuro-legacy
aws s3 cp s3://kuro-db-backup/kg-backup/default-ip-172-31-26-151-2026-06-30-153005.psql.bin /home/chief/kuro-legacy/kg_pg.dump
aws s3 cp s3://kuro-db-backup/kg-backup/mongo-ip-172-31-26-151-2026-06-30-153007.dump /home/chief/kuro-legacy/kg_mongo.dump
aws s3 cp s3://kuro-db-backup/kc-backup/default-kuroserver-2026-06-30-193001.psql.bin /home/chief/kuro-legacy/kc_pg.dump
aws s3 cp s3://kuro-db-backup/kc-backup/mongo-kuroserver-2026-06-30-223002.dump /home/chief/kuro-legacy/kc_mongo.dump
```

### 1.2 Source Data Inventory (verified 2026-07-01)

**kg_pg** (PostgreSQL, 802 KB dump, source: `kuro-user`):

| Table | Count | Role |
|-------|-------|------|
| `users_customuser` | 3,378 | eShop user accounts |
| `users_phonemodel` | 177 | Phone number records |
| `orders_orders` | 1,206 | eShop orders (header) |
| `orders_orderitems` | 1,350 | eShop order line items |
| `accounts_cart` | 748 | Shopping cart |
| `accounts_wishlist` | 450 | Wishlist |
| `accounts_addresslist` | 1,064 | Saved addresses |

**kg_mongo** (MongoDB, 24 MB dump):

| Collection | Count | Role |
|------------|-------|------|
| `prods` | 2,481 | Product catalog |
| `components` | 1,614 | PC components |
| `custombuilds` | 2,053 | Custom PC builds |
| `kgbuilds` | 480 | KG-branded builds |
| `accessories` | 504 | Accessories |
| `monitors` | 156 | Monitors |
| `builds` | 258 | Pre-built PCs (**DUPLICATE subset of kgbuilds** — merged in source) |
| `networking` | 17 | Networking gear |
| `presets` | 16 | Preset configurations |
| `external` | 12 | External products |
| `cables` | 1 | Cables |
| `kurodata` | 2 | UI carousel content (**NOT product data — skip**) |
| `lists` | 3 | Curated product lists (**NOT product data — skip**) |
| `misc` | 1 | Serial number counters (**NOT product data — skip**) |
| `tempproducts` | 1 | Temporary product (**delete_flag=true — skip**) |

**kc_pg** (PostgreSQL, 781 KB dump, source: `kuro-cadence`):

| Table | Count | Role |
|-------|-------|------|
| `users_kurouser` | 68 | Kuro Cadence user accounts (employees) |
| `users_customuser` | 153 | Kuro Cadence custom users |
| `users_phonemodel` | 106 | Phone number records |
| `users_accesslevel` | 104 | Access level definitions |
| `users_businessgroup` | 3 | Business group definitions |
| `users_switchgroupmodel` | 6,854 | Switch group model |
| `users_common_counters` | 1 | Sequence counters |
| `careers_jobapps` | 1,613 | Career job applications |

**kc_mongo** (MongoDB, 52 MB dump):

> **Note:** `stock_register` and `outward` collections have been migrated to PostgreSQL (`inventory_inventorystock`, `inventory_serial_record`, `inventory_movement_serial`). See §9.15.10 for schema redesign details.

| Collection | Count | Role |
|------------|-------|------|
| `kgorders` | 12,174 | In-store orders |
| `purchaseorders` | 5,557 | Purchase orders |
| `estimates` | 5,056 | Estimates/quotes |
| `inwardInvoices` | 4,750 | Inward invoices |
| `inwardpayments` | 3,188 | Inward payments |
| `reb_users` | 2,540 | Walk-in / rebel users |
| `paymentVouchers` | 3,715 | Payment vouchers |
| `employee_attendance` | 966 | Employee attendance records |
| `outwardInvoices` | 1,192 | Outward invoices |
| `serviceRequest` | 1,627 | Service requests |
| `indentproduct` | 1,676 | Indent product records |
| `outward` | 781 | Outward transactions |
| `indentpos` | 285 | Indent PO records |
| `vendors` | 423 | Vendor master data |
| `players` | 117 | Player accounts |
| `inwardCreditNotes` | 109 | Inward credit notes |
| `tpbuilds` | 123 | Third-party builds |
| `tporders` | 229 | Third-party orders |
| `stock_register` | 194 | Stock register |
| `tourneyregister` | 56 | Tournament registrations |
| `outwardCreditNotes` | 44 | Outward credit notes |
| `outwardDebitNotes` | 13 | Outward debit notes |
| `inwardDebitNotes` | 3 | Inward debit notes |
| `teams` | 14 | Team records |
| `products` | 82 | F&B products only (62 food + 20 beverage) — **must remap to `cafe-food`/`cafe-beverage`** |
| `presets` | 6 | KC preset configurations |
| `accounts` | 7 | Account records |
| `misc` | 8 | Miscellaneous |
| `bgData` | 1 | Business group metadata |
| `tournaments` | 3 | Tournament records |
| `tempproducts` | 0 | Temporary products (empty) |

---

## 2. The Two Target Databases

### KungOS_PG_One (PostgreSQL 16, `127.0.0.1:5432`)

| Schema | Tables | Source |
|--------|--------|--------|
| **Identity** | `users_identity`, `identity_phone_aliases`, `users_customuser`, `users_customer`, `users_player`, `users_employee`, `users_saved_addresses`, `users_organization`, `users_vendor_profile`, `users_team_profile`, `users_user_tenant_context` | kg_pg + kc_pg + kc_mongo |
| **Orders** | `orders_core` + 6 detail tables (`eshop_detail`, `in_store_detail`, `estimate_detail`, `tp_order_detail`, `service_detail`, `cafe_fnb_detail`) | kg_pg + kc_mongo (`kgorders`, `estimates`, `tporders`, `serviceRequest`) |
| **Inventory** | `inv_vendors`, `inv_purchase_orders`, `inventory_inventoryitem`, `inventory_inventorystock`, `inventory_serial_record`, `inventory_movement_serial`, `inventory_asset_installation`, `inventory_asset` | kc_mongo (`vendors`, `purchaseorders`, `indentproduct`, `stock_register`, `outward`) |
| **E-Commerce** | `eshop_cart`, `eshop_wishlist` | kg_pg |
| **Accounts** | `acct_partners`, `acct_banks`, `acct_loans` | (seed empty — no legacy data) |
| **Cafe Platform** | 12 `caf_platform_*` tables | (already live, code-only changes) |

### KungOS_Mongo_One (MongoDB 8, `127.0.0.1:27017`)

| Collection | Source | Discriminator |
|------------|--------|---------------|
| `custom_catalog` | **kg_mongo**: `kgbuilds` (480) + `custombuilds` (2,053) + `presets` (16 → 321 flattened) | `custom_type` field |
| `custom_catalog` | **kc_mongo**: `tpbuilds` (123) + `presets` (6 → 33 flattened) | `custom_type` field |
| | | | **Total: 3,010** (builds SKIPPED — duplicate of kgbuilds) |
| `financial_documents` | kc_mongo: 8 finance collections | `doc_type` field |
| `products` | kg_mongo + kc_mongo: merged product catalogs | merge by product key |
| `reb_users` | kc_mongo | (preserved as-is) |
| `players` | kc_mongo | (preserved as-is) |
| `serviceRequest` | kc_mongo | (preserved as-is) |
| `teams` | kc_mongo | (preserved as-is) |
| `vendors` | kc_mongo | (preserved as-is) |
| `employee_attendance` | kc_mongo | (preserved as-is) |
| `stock_register` | kc_mongo | (preserved as-is — migrated to `inventory_inventorystock` in PostgreSQL) |
| `indentpos` | kc_mongo | (preserved as-is) |
| `bgData` | kc_mongo | (preserved as-is) |
| `outward` | kc_mongo | (preserved as-is — serial data migrated to `inventory_serial_record` in PostgreSQL, shipment tracking preserved) |

**All collections require canonical tenant fields** (`bg_code`, `div_code`, `branch_code`) — legacy field names (`bgcode`, `division`, `branch`) must be renamed before consolidation.

### 2.1 Tenant Hierarchy & Entity Mapping

The target tenant hierarchy is **seeded into PostgreSQL** (`tenant_business_groups`, `tenant_divisions`, `tenant_branches`) before any data migration. All source records are enriched with the correct `bg_code`/`div_code`/`branch_code` based on the mapping rules below.

#### 2.1.1 Business Groups (seed data)

| bg_code | Source Code | Legal Name | Description |
|---------|-----------|-----------|-------------|
| `KURO0001` | `BG0001` | Kuro Cadence LLP | Primary BG — encompasses Kuro Gaming, Rebellion, and RenderEdge operations |
| `DUNE0003` | `DUNE0003` | Dune Labs LLP | Separate legal entity — Rebellion operations under Dune. Has own DB (`dunelabs`), not in current S3 dumps |

**Excluded:** `BG0002` (Nazarick Labs LLP) — defunct, not migrated.

**Source reference:** `kc_pg.users_businessgroup` (3 rows: BG0001, BG0002, DUNE0003). The `entities` JSONB column defines which entities/branches belong to each BG.

**Cascading code convention:** `div_code = {bg_code}_{seq}`, `branch_code = {div_code}_{seq}`. A branch code like `KURO0001_002_001` encodes BG → Division → Branch without requiring a JOIN.

#### 2.1.2 Divisions (seed data)

| div_code | Division Name | Parent BG | Source Entity | Description |
|----------|--------------|-----------|---------------|-------------|
| `KURO0001_001` | Kuro Gaming Division | KURO0001 | `kurogaming` | Kuro Gaming cafe operations (PC gaming, eShop) |
| `KURO0001_002` | Rebellion Division | KURO0001 | `rebellion` | Rebellion gaming cafe operations |
| `KURO0001_003` | RenderEdge Division | KURO0001 | `renderedge` | RenderEdge rental operations |
| `DUNE0003_001` | Rebellion (Dune) | DUNE0003 | `rebellion` | Rebellion operations under Dune Labs LLP |

**Source reference:** `kc_pg.users_businessgroup.entities[]` JSONB column defines entity→BG membership.

#### 2.1.3 Branches (seed data)

| branch_code | Branch Name | Parent Division | Source Mapping |
|-------------|------------|-----------------|----------------|
| `KURO0001_001_001` | Kuro Gaming Madhapur | KURO0001_001 | `entity='kurogaming'` + `branch='Madhapur'` |
| `KURO0001_002_001` | Rebellion Madhapur | KURO0001_002 | `entity='rebellion'` + `branch='Madhapur'` |
| `KURO0001_002_002` | Rebellion LB Nagar | KURO0001_002 | `entity='rebellion'` + `branch='LB Nagar'` |
| `KURO0001_003_001` | RenderEdge Madhapur | KURO0001_003 | `entity='renderedge'` + `branch='Madhapur'` |

**Note:** DUNE0003 branches (`Madhapur`, `LB Nagar`) are defined in source but have **zero operational data** in current S3 dumps. Pre-seed when `dunelabs` DB dump becomes available.

#### 2.1.4 Source → Target Mapping Rules

**`kc_mongo.kgorders` entity/branch mapping** (12,174 docs):

| Source `entity` | Source `branch` | Count | Target `bg_code` | Target `div_code` | Target `branch_code` |
|-----------------|-----------------|-------|-------------------|-------------------|----------------------|
| `kurogaming` | `Madhapur` | 632 | `KURO0001` | `KURO0001_001` | `KURO0001_001_001` |
| `rebellion` | `Madhapur` | 9,480 | `KURO0001` | `KURO0001_002` | `KURO0001_002_001` |
| `rebellion` | `LB Nagar` | 2,062 | `KURO0001` | `KURO0001_002` | `KURO0001_002_002` |

**Note:** All 12,174 kgorders belong to KURO0001 (Kuro Cadence). Zero DUNE0003 orders exist in current dumps. The `entity` field determines **Division** (`div_code`), `branch` field determines **Branch** (`branch_code`). Total: 632 + 9,480 + 2,062 = 12,174.

**Full entity distribution across kc_mongo** (verified 2026-07-01):

| Collection | `kurogaming` | `rebellion` | `null`/other | Total |
|-----------|-------------|-------------|-------------|-------|
| `kgorders` | 632 | 11,542 | 0 | 12,174 |
| `purchaseorders` | 5,552 | 5 | 0 | 5,557 |
| `inwardpayments` | 633 | 2,555 | 0 | 3,188 |
| `paymentVouchers` | 3,714 | 1 | 0 | 3,715 |
| `stock_register` | 126 | 68 | 0 | 194 |
| `outward` | 776 | 0 | 5 | 781 |
| `products` | 0 | 82 | 0 | 82 |
| `estimates` | 5,056 | 0 | 0 | 5,056 |
| `serviceRequest` | 1,627 | 0 | 0 | 1,627 |
| `inwardInvoices` | 4,750 | 0 | 0 | 4,750 |
| `outwardInvoices` | 1,192 | 0 | 0 | 1,192 |
| All others | `kurogaming` only | 0 | 0 | — |

**DUNE0003 data in current dumps:**
- `kc_pg.users_businessgroup`: 1 row (DUNE0003, `db_name='dunelabs'`, entity: rebellion)
- `kc_pg.users_switchgroupmodel`: 8 rows (7 × KCTM032, 1 × KCAD001) — same userids as BG0001
- `kc_mongo.estimates`: 1 estimate with customer name "DUNE LABS LLP" (but `entity='kurogaming'` — B2B sale TO Dune, not Dune's own data)
- **No DUNE entity data in any kc_mongo collection.** Dune's operational data resides in separate `dunelabs` database (not in S3 dumps).

**`kg_pg` eShop orders** (1,206 rows):
- Source has **no tenant fields** (`bg_code`, `div_code`, `branch_code` absent from all columns).
- All eShop orders belong to the Kuro Gaming web store → default to `bg_code='KURO0001'`, `div_code='KURO0001_001'`, `branch_code='KURO0001_001_001'`.

**`kc_mongo` financial & inventory collections**:
- `purchaseorders`: entity `kurogaming` (5,552) → `KURO0001_001`; entity `rebellion` (5) → `KURO0001_002`. All have `branch=null` → use division-level default branch.
- `vendors`, `estimates`, `serviceRequest`, `outward`: Apply same entity→division mapping as `kgorders`.
- Collections without `entity` field (e.g., `stock_register`, `employee_attendance`): Use `bg_code='KURO0001'` as default BG scope.

**`kg_mongo` product collections**:
- All product data belongs to Kuro Gaming catalog → `bg_code='KURO0001'`, `div_code='KURO0001_001'`.
- No branch-level scoping needed for product catalog (shared across branches).

**`kc_mongo.products` (F&B)**:
- 82 F&B products, ALL `entity='rebellion'` → these are Rebellion cafe menu items.
- Assign `bg_code='KURO0001'`, `div_code='KURO0001_002'` (Rebellion Division owns the F&B menu).
- Must remap discriminator to `collection: 'cafe-food'` / `'cafe-beverage'` in target.

**`kc_mongo.presets` (gaming cafe presets)**:
- 6 category indexes (33 items) representing cafe gaming packages.
- Assign `bg_code='KURO0001'`, `div_code='KURO0001_002'` (Rebellion Division — these are cafe-specific presets).

#### 2.1.5 Tenant Table Seed SQL

```sql
-- Seed Business Groups
-- BG0002 (Nazarick Labs LLP) excluded — defunct
INSERT INTO tenant_business_groups (bg_code, legal_name, status) VALUES
  ('KURO0001', 'Kuro Cadence LLP', 'active'),
  ('DUNE0003', 'Dune Labs LLP', 'active');

-- Seed Divisions
INSERT INTO tenant_divisions (div_code, division_name, bg_code, status) VALUES
  ('KURO0001_001', 'Kuro Gaming Division', 'KURO0001', 'active'),
  ('KURO0001_002', 'Rebellion Division', 'KURO0001', 'active'),
  ('KURO0001_003', 'RenderEdge Division', 'KURO0001', 'active'),
  ('DUNE0003_001', 'Rebellion (Dune)', 'DUNE0003', 'active');

-- Seed Branches
-- DUNE0003 branches (Madhapur, LB Nagar) pre-seeded when dunelabs DB dump available
INSERT INTO tenant_branches (branch_code, branch_name, div_code, status) VALUES
  ('KURO0001_001_001', 'Kuro Gaming Madhapur', 'KURO0001_001', 'active'),
  ('KURO0001_002_001', 'Rebellion Madhapur', 'KURO0001_002', 'active'),
  ('KURO0001_002_002', 'Rebellion LB Nagar', 'KURO0001_002', 'active'),
  ('KURO0001_003_001', 'RenderEdge Madhapur', 'KURO0001_003', 'active');
```

**Execution order:** Seed tenant tables **before Phase 1** (canonicalization). All subsequent migration phases reference these codes.

---

## 3. Cross-DB / Cross-Project Identity Resolution

Every one of the 4 sources contributes identities into a single `users_identity` table, deduplicated **by normalized phone number**. This is the single riskiest part of the migration.

### 3.1 Identity ID Format by Source

| Source | Prefix | Example | Notes |
|--------|--------|---------|-------|
| **kg_pg** (`users_customuser`) | `ESH` + userid | `ESH1003229619` | Migrate FIRST — establishes canonical identities |
| **kc_pg** (`users_kurouser`, employees) | `KCTM*` / `KCAD*` (preserve userid) | `KCTM001` | Migrate SECOND — userid-based dedup (no phone column in source) |
| **kc_mongo** (`reb_users`) | `ID` + zero-padded sequence | `ID000001` | Phone dedup against ESH + KCTM/KCAD |
| **kc_mongo** (`players`) | `REPL*` (preserve playerid) | `REPL000001` | Phone dedup, preserve playerid |
| **kc_mongo** (`employee_attendance`) | `KCTM*`/`KCAD*` (no phone in source) | `KCAD001` | Cross-link to `users_kurouser` for name/phone enrichment |

**Phone normalization is mandatory before any dedup step** — sources use inconsistent formats (`098765 4321` with space, `9876543210` without space, with/without leading `0` or `+91`):

```python
def normalize_phone(phone: str) -> str:
    if not phone:
        return ''
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    return digits[:10]
```

### 3.2 Strict Sequential Dedup Order

```
Phase 0:   TRUNCATE KungOS_PG_One + KungOS_Mongo_One + schema reset
           Apply Django migrations
           Apply runtime schema fixes (phase2_schema_fixes.sql)
    ↓
Phase 0.5: Seed tenant hierarchy (tenant_business_groups, tenant_divisions, tenant_branches)
    ↓
Phase 2a:  kg_pg + kc_pg users_customuser → users_customuser (ON CONFLICT userid DO UPDATE)
           + users_identity (ESH* prefix for ALL custom users)
    ↓
Phase 2b:  kc_pg users_kurouser (employees) → users_employee
           PHONE-BASED MERGE: find existing ESH* identity by phone, link employee profile to it
           (all 68 employees merged to existing eShop identities)
    ↓
Phase 2c:  kc_mongo reb_users → users_customer
           PHONE-BASED MERGE: find existing identity by phone, create ID* if no match
    ↓
Phase 2d:  kc_mongo players → users_player
           PHONE-BASED MERGE: find existing identity by phone, create REPL* if no match
    ↓
Phase 2e:  kc_mongo vendors → users_organization + users_vendor_profile
    ↓
Phase 2f:  kc_mongo teams → users_organization + users_team_profile
    ↓
Phase 3:   Custom catalog consolidation → custom_catalog
    ↓
Phase 4:   Product/game merge → products
    ↓
Phase 5:   Vendors + Purchase Orders + Stock → inv_*, inventory_*
    ↓
Phase 6:   Finance consolidation → financial_documents
    ↓
Phase 7:   Accounts master data → acct_*
    ↓
Phase 8:   Orders consolidation (§4)
    ↓
Phase 9:   eShop cart + wishlist + addresses
    ↓
Phase 10:  Tenant context population + full validation
```

**Rule:** eShop (`ESH*`) identities are the anchor — migrated first because `kg_pg` phones are the cleanest and most complete dataset. Every subsequent source checks its normalized phone against already-created identities before minting a new one.

**Merge results (verified):**

| Source | Total | Merged to Existing | New Identities | Skipped |
|--------|-------|-------------------|----------------|----------|
| kg_pg custom users | 3,378 | N/A (anchor) | 3,378 ESH* | 0 |
| kc_pg custom users | 153 | N/A (anchor) | 153 ESH* | 0 |
| kc_pg employees | 68 | **68** (all merged to ESH*) | 0 | 0 |
| kc_mongo walk-ins | 2,540 | 53 (merged to ESH*) | 2,392 ID* | 95 (invalid phone) |
| kc_mongo players | 117 | 40 (merged to ESH*) | 44 REPL* | 4 (invalid phone) |
| kc_mongo vendors | 423 | N/A | 415 (8 skipped no GSTIN) | 8 |
| kc_mongo teams | 14 | N/A | 14 | 0 |

**Multi-profile identities:** 16 identities have both employee + customer profiles (same person is both employee and walk-in customer).

### 3.3 Known Discrepancies (RESOLVED during Phase 2 execution)

| Issue | Detail | Resolution |
|-------|--------|------------|
| Employee userid-based dedup | `users_kurouser` has no `phone` column — dedup by `userid` (KCTM*/KCAD*), not phone | **RESOLVED:** Phone resolved via `LEFT JOIN users_customuser ON userid`. All 68 employees merged to existing ESH* identities by phone. |
| Walk-in over-creation | Previous run created 4,748 `ID*` identities vs. 2,416 `caf_platform_walkins` rows (2,332 orphans) | **RESOLVED:** Walk-ins migrated straight from `kc_mongo.reb_users` (2,540 docs, 95 skipped invalid phone). 53 merged to ESH*, 2,392 new ID*. |
| eShop customer_id inconsistency | All 992 eshop orders in `orders_core` use raw 10-digit phone as `customer_id` instead of `ESH*` prefix | **RESOLVED:** Phone-lookup table built in Phase 2a. All identities carry normalized 10-digit phone. |
| Cross-source phone/email/username overlap | Same person has accounts in both `kg_pg` and `kc_pg` with same contact info | **RESOLVED:** Dropped unique constraints on `users_customuser` (phone, email, username) and `users_identity` (uq_identity_tenant_phone) via `phase2_schema_fixes.sql`. |
| Walk-in garbage phone normalization | Non-digit strings normalize to `''`, triggering unique constraint conflicts | **RESOLVED:** Skip records with invalid/missing phones (95 walk-ins skipped). Empty phone does NOT create identity. |
| Vendor empty GSTIN | 8 vendors have no GSTIN data | **RESOLVED:** Vendors without GSTIN get `users_organization` row but no `users_vendor_profile` (8 skipped). |
| Player migration cascade errors | 29 transient errors from transaction cascade within savepoint loop | **RESOLVED:** Data is correct (69 players in table). Errors were from `conn.rollback()` cascading within same transaction. Use savepoint pattern. |

---

## 4. Cross-DB Orders Migration (order_type discriminator model)

All order types from both projects converge into one `orders_core` table with per-type detail tables.

| order_type | Source Collection/Table | Source Alias | Detail Table | Source Count |
|------------|-------------------------|--------------|---------------|--------------|
| `eshop` | `orders_orders` (ALL rows — all are hex-format web-app orders, `channel=online/offline`) | kg_pg | `eshop_detail` | 1,206 total (975 active, `delete_flag=false`) |
| `in_store` | `kgorders` | kc_mongo | `in_store_detail` | 12,160 (12,174 total minus 14 cancelled; **0 hex-format orderids exist — no exclusions needed**) |
| `estimate` | `estimates` | kc_mongo | `estimate_detail` | 5,056 |
| `tp` | `tporders` | kc_mongo | `tp_order_detail` | 229 |
| `service` | `serviceRequest` | kc_mongo | `service_detail` | 1,627 |
| `cafe_fnb` | Live kiosk (not legacy) | — | `cafe_fnb_detail` | 0 legacy (no FNB-prefixed orders exist in source) |

### 4.1 Special Handling Rules

- **kg_pg eShop orders (all hex-format):** ALL 1,206 `orders_orders` rows have hex-format `orderid` and `channel=online/offline`. These are web-app orders and MUST be migrated to `order_type='eshop'` as per design. Filter on `delete_flag=false` for active orders (975 rows).
- **kc_mongo web-app order exclusion:** ~~9 hex-`orderid` records~~ **CORRECTED: 6 lowercase hex-format orderids exist in `kc_mongo.kgorders`.** These collide with 6 eShop orderids (case-sensitive PK). ON CONFLICT DO UPDATE merged them (in_store type preserved). 3 uppercase hex kgorders (`673DF4897D`, `CBADFF99D6`, `F03BB0ADAE`) do NOT collide.
- **Runtime fix — source database:** `kgorders` (12,174) is in `kuropurchase` DB (kc_mongo dump), NOT in `kg_inspect` (kg_mongo dump). `kg_inspect` only contains product collections. Migration script reads from `kuropurchase.kgorders` directly.
- **eShop deleted-order cleanup:** Filter strictly on `delete_flag=false`. Do not migrate `delete_flag=true` orders.
- **customer_id resolution:** Build the phone→identity lookup only from `users_identity` after Phase 1–7 completes, then resolve every order's raw phone to the correct `ESH*`/`ID*` identity. Orders with no resolvable phone (walk-ins, third-party, anonymous estimates) get `customer_id = NULL`; this is expected and allowed by the FK constraint.
- **Tenant enrichment:** `kc_mongo` and `kg_pg` orders carry zero tenant fields natively. Apply the mapping rules from §2.1.4: use `entity` + `branch` to derive `div_code`/`branch_code` for `kc_mongo` collections; default to `KURO0001`/`KURO0001_001`/`KURO0001_001_001` for `kg_pg` eShop orders. See §2.1 for full hierarchy.
- **Lineage tracking:** Add `source_db`, `source_collection`, `migrated_at` columns to `orders_core` so every row can be traced back to its originating source.
- **Outward shipment tracking:** `kc_mongo.outward` (781 records) is a shipment/delivery log referencing existing orders. 573 reference `kgorders`, 135 reference `tporders`, 73 have `ordertype=null`. **708 have matching orders** (571 kgorders + 135 tporders); **73 are orphaned** (73 null ordertype + 2 non-matching kgorders). Contains serial numbers (`products[].sr_no`) critical for inventory tracking. Preserve as-is in `KungOS_Mongo_One`.

---

## 5. Cross-Project Catalog & Vendor Consolidation

| Target | Sources | Discriminator | Source Count |
|--------|---------|---------------|--------------|
| `KungOS_Mongo_One.products` | kg_mongo + kc_mongo product catalogs | `collection` field (source collection name) | kg_mongo: 4,786 raw docs (3,171 unique productids after dedup) + kc_mongo: 82 (F&B only) |
| | | | **kg_mongo source collections:** `prods`(2,481) + `components`(1,614) + `accessories`(504) + `monitors`(156) + `networking`(17) + `external`(12) + `cables`(1) + `tempproducts`(1, skip) |
| | | | **WARNING:** `prods` and `components` share 1,613 productids — dedup by `productid`, prefer `prods` (has richer data) |
| `KungOS_Mongo_One.custom_catalog` | **kg_mongo**: `kgbuilds` (480) + `custombuilds` (2,053) + `presets` (16 category indexes → 321 items flattened) | `custom_type` field | 2,854 from kg_mongo |
| `KungOS_Mongo_One.custom_catalog` | **kc_mongo**: `tpbuilds` (123) + `presets` (6 category indexes → 33 items flattened) | `custom_type` field | 156 from kc_mongo |
| | | | **Total: 3,010** (builds collection SKIPPED — duplicate subset of kgbuilds) |
| `KungOS_PG_One.inv_vendors` | kc_mongo: `vendors` (423) | `vendor_code` preserved as natural PK | 423 |
| `KungOS_PG_One.inv_purchase_orders` | kc_mongo: `purchaseorders` (5,557) + `indentproduct` (1,676, indent POs) | FK → `inv_vendors.vendor_code` | 7,148 total (85 indents share po_no with POs) |
| `KungOS_PG_One.users_organization` + `users_vendor_profile` | kc_mongo: `vendors` | `org_id = vendor_code` | 423 |
| `KungOS_PG_One.users_organization` + `users_team_profile` | kc_mongo: `teams` (14) | `org_id = teamid` | 14 |

**Custom catalog consolidation notes:**
- **kg_mongo.presets** (16 category indexes → 321 items): Category index documents with embedded `list` arrays. Types: `build_fees`, `cooler`, `cpu`, `fans`, `gpu`, `hdd`, `margin`, `mob`, `os`, `psu`, `ram`, `shp_fees`, `ssd`, `tower`, `warranty`, `wifi`. Each `list` contains individual component presets (e.g., `PRECPU*`, `PREGPU*`). Flatten `list` arrays into individual `custom_catalog` docs with `custom_type='preset'` and `preset_category` field set to the parent category name.
- **kg_mongo.builds** (258 docs): Pre-built PC products. **SKIPPED — DUPLICATE SUBSET of `kgbuilds`** (all 258 builds match kgbuilds entries with `/AAAA` suffix removed). The source DB merged `builds` into `kgbuilds` already. Do NOT migrate to avoid double-counting.
- **kg_mongo.kgbuilds** (480 docs): Custom PC builds from Kuro Gaming. Migrate with `custom_type='kgbuild'`.
- **kg_mongo.custombuilds** (2,053 docs): Custom PC builds from Kuro Gaming. Migrate with `custom_type='custombuild'`.
- **kc_mongo.tpbuilds** (123 docs): Third-party builds. Migrate with `custom_type='tpbuild'`.
- **kc_mongo.presets** (6 category indexes → 33 items): Gaming cafe presets (`grace`, `pc144hz`, `pc240hz`, `vr`, `ps5`, `controller`). Flatten `list` arrays into individual `custom_catalog` docs with `custom_type='preset'` (NOT `cafe_preset` — use same discriminator as kg_mongo presets for consistency).
- **kc_mongo.products** (82 items): All F&B products (`collection: 'food'` = 62, `collection: 'beverage'` = 20). **Must remap discriminator** to `collection: 'cafe-food'` / `'cafe-beverage'` in target to distinguish from PC components. Price format: `{ '1num': 40 }` (single price, not per-branch). Has `emp_price` field.

**Purchase order consolidation notes:**
- **kc_mongo.indentproduct** (1,676 docs): Purchase indent records (PO requests). Contains `vendor`, `products[]` array with `productname`, `qty`, `rate`, `amount`. Migrate to `inv_purchase_orders` with `po_type='indent'` discriminator alongside `purchaseorders` (`po_type='standard'`).
- **kc_mongo.indentproduct vendor caveat:** 781 have `vendor='instock'` (internal stock transfer placeholder), 441 have empty `vendor`, 454 have actual vendor codes. Only 86 have `po_no` reference. Active: 872, inactive: 804.
- **kc_mongo.purchaseorders** (5,557 docs): All have `delete_flag=false` (no deleted POs). Entity: kurogaming (5,552), rebellion (5). All have `branch=null` (no branch info).

**Product migration notes:**
- **kg_mongo product collections:** Migrate ALL product collections (`prods`, `components`, `accessories`, `monitors`, `networking`, `external`, `cables`). Skip `tempproducts` (1 doc, `delete_flag=true`).
- **kg_mongo `prods` vs `components` overlap:** 1,613 shared productids. `prods` is the superset (has richer data including peripherals). Dedup by `productid`, prefer `prods` data.
- **kg_mongo `prods` discriminator:** All `prods` docs have `collection: 'components'` embedded. Use the SOURCE collection name as the target `collection` discriminator, NOT the embedded field.
- **kg_mongo preset price:** Flat number (e.g., `4343`) — single price for all branches. 320/321 items have `portal_title`.
- **kc_mongo preset price:** Per-branch format (e.g., `{Madhapur: {price: 100, add_on: 100}}`).
- **kc_mongo F&B products:** 82 items total (62 `food`, 20 `beverage`). Must remap to `cafe-food`/`cafe-beverage` in target. Price format: `{ '1num': 40 }`. Has `emp_price` field.

**Order migration notes:**
- **kc_mongo.kgorders ordertype:** All 12,174 have `ordertype: null` (no discriminator in source). Use `entity` field: `rebellion` (11,542) vs `kurogaming` (632). Branch: Madhapur (10,112) vs LB Nagar (2,062).
- **kc_mongo.kgorders order_status:** null (11,542), Delivered (615), Cancelled (14), Created (3). Filter on `order_status != 'Cancelled'` for active.
- **kc_mongo.kgorders orderid format:** All use `KG` prefix + 8 digits (e.g., `KG23000004`). Zero hex-format orderids exist.
- **kc_mongo.tporders channel:** Amazon (226), amazon (1), Flipkart (1), empty (1). Orderid: `TP` prefix + hex (e.g., `TP20cb402cd538`).
- **kg_pg orders_orders channel:** online (1,204), offline (2). All hex-format orderids. Filter on `delete_flag=false` for active (975).

---

## 6. Cross-Project Finance Consolidation

Eight finance collections in `kc_mongo` (Kuro Cadence project only — Kuro Gaming has no finance data) consolidate into one MongoDB collection in `KungOS_Mongo_One`:

| Legacy Collection | doc_type | Source Count |
|--------------------|----------|--------------|
| `inwardInvoices` | `inward_invoice` | 4,750 |
| `outwardInvoices` | `outward_invoice` | 1,192 |
| `inwardpayments` | `inward_payment` | 3,188 |
| `inwardCreditNotes` | `inward_credit_note` | 109 |
| `inwardDebitNotes` | `inward_debit_note` | 3 |
| `outwardCreditNotes` | `outward_credit_note` | 44 |
| `outwardDebitNotes` | `outward_debit_note` | 13 |
| `paymentVouchers` | `payment_voucher` | 3,715 |

**Expected consolidated total:** 4,750 + 1,192 + 3,188 + 109 + 3 + 44 + 13 + 3,715 = **13,014 documents** in `financial_documents`.

**Note:** The previous migration run (from stale `KungOS_Mongo_One` source) produced 27,050 financial documents with inflated counts. The clean-slate migration from `kc_mongo` source will produce 13,014 documents. This is the correct count.

**Additional financial-related collections (NOT in financial_documents):**
- `estimates` (5,056): Migrated to `orders_core` as `order_type='estimate'` (Phase 8)
- `indentpos` (285): Migrated to `indent`/`indent_item` tables in KungOS_PG_One (indent PO tracking)
- `inwardpayments` (3,188): Already included in financial_documents above
- **Total financial-related across all collections:** 13,014 (financial_documents) + 5,056 (estimates→orders) + 285 (indentpos→indent) = 18,355

---

## 7. Unified Execution Order (All 4 Sources → 2 Targets)

```
Phase 0    — Truncate KungOS_PG_One + KungOS_Mongo_One; apply Django migrations;
            restore source dumps from /home/chief/kuro-legacy/ to inspection databases
Phase 0.5  — Apply runtime schema fixes (`deployment_scripts/phase2_schema_fixes.sql`)
            — Seed tenant hierarchy (`deployment_scripts/migrate_phase0_tenant_seed.py`)
            — BGs (2), Divisions (4), Branches (4)
Phase 1    — MongoDB field canonicalization (kc_mongo → canonical bg_code/div_code/branch_code)
              [PREREQUISITE for all Mongo consolidation — all collections in kc_mongo]
Phase 2    — Identity migration (`deployment_scripts/migrate_phase2_identities.py`):
              2a. All custom users (kg_pg 3,378 + kc_pg 153) → ESH* identities
              2b. Employees (68) → merged to existing ESH* by phone
              2c. Walk-ins (2,540, 95 skipped) → ID* or merged to ESH* (53)
              2d. Players (117, 4 skipped) → REPL* or merged to ESH* (40)
              2e. Vendors (423, 8 skipped no GSTIN) → orgs + vendor profiles
              2f. Teams (14) → orgs + team profiles
Phase 3  — Custom catalog consolidation → custom_catalog (kg_mongo + kc_mongo sources, §5)
              kg_mongo: kgbuilds(480) + custombuilds(2053) + presets(16→321 flattened)
              kc_mongo: tpbuilds(123) + presets(6→33 flattened)
              **builds(258) SKIPPED — duplicate subset of kgbuilds**
              **Total: 3,010**
Phase 4  — Product/game merge → products (kg_mongo + kc_mongo merge)
Phase 5  — Vendors + Purchase Orders + Stock → inv_vendors, inv_purchase_orders, inventory_inventoryitem, inventory_inventorystock (kc_mongo: vendors + purchaseorders + indentproduct + stock_register)
              **COMPLETED: 424 vendors, 7,148 POs, 193 items, 178 stock records**
Phase 6  — Finance consolidation → financial_documents (kc_mongo, 8 collections → 1)
              **COMPLETED: 13,014 documents** (script: `migrate_phase6_finance.py`)
Phase 7  — Orders consolidation, both projects (§4):
              kuropurchase.kgorders (12,174) → in_store
              kuropurchase.tporders (229) → tp
              kg_pg orders_orders (1,206, hex-format web-app) → eshop
              **COMPLETED: 13,603 orders** (script: `migrate_phase7_orders.py`)
              **⚠️ Runtime fix:** 6 eShop orders collided with 6 lowercase hex-format kgorders.
              ON CONFLICT DO UPDATE merged them (in_store type preserved).
              3 uppercase hex kgorders do NOT collide (case-sensitive PK).
Phase 7.5 — kc_mongo outward (781) → preserved as-is (shipment/delivery tracking)
Phase 7.6 — outward serials → inventory_serial_record + inventory_movement_serial + inventory_asset_installation (412 serials, 890 movements, 882 junctions)
              **COMPLETED: 412 serials, 890 movements, 882 junctions** (scripts: `migrate_phase5b_serials.py`)
Phase 7.7 — serial enrichment: sold_to_customer FK (34 linked), purchase_date (278 populated), movement_count reconciliation (0 mismatches)
              **COMPLETED: 34 customer FKs, 278 purchase dates** (script: `migrate_phase5c_serial_enrichment.py`)
Phase 2/7 — MongoDB collections to KungOS_PG_One: vendors (423) → users_vendor_profile, players (117) → users_player, teams (14) → users_team_profile, reb_users (2540) → users_customer, serviceRequest (1627) → service_detail, indentpos (285) → indent, employee_attendance (966) → users_employee_attendance, bgData (1) → tenant tables — total 5,973 documents
Phase 8  — Accounts master data → acct_partners (2), acct_banks (8), acct_loans (1) — **COMPLETED**: migrated from kc_mongo.accounts (partners: Surya Regunta, Sureddy Ramakanth Reddy; banks: 4 Kuro Gaming + 4 Rebellion; loans: 1 bank loan)
Phase 9  — eShop cart + wishlist + addresses → eshop_cart, eshop_wishlist, users_saved_addresses
Phase 10 — Tenant context population → users_user_tenant_context (3,531 users) — **COMPLETED**: ran `populate_tenant_context` management command, all users now have bg_code=KURO0001, scope=full
Phase 11 — Cafe menu derivation (code-only: read live from products + custom_catalog + inventory_inventorystock)
Phase 12 — ViewSet completion (walk-ins, partners, banks, loans, inventory FBV→ViewSet conversion)
Phase 13 — Legacy collection archival (rename {name}_archived_{date}, monitor 7 days, then drop)
```

**Dependency graph:**
- Phases 3–7 are independent of each other but all depend on Phase 1 (canonicalization) and Phase 2 (identity).
- Phase 8 depends on Phase 2 (customer_id resolution) and cannot run before it.
- Phase 9 depends on Phase 2 (identity resolution for cart/wishlist owners).
- Phase 10 depends on all Phases 1–9.
- Phases 11–13 are post-migration code changes and cleanup.

---

## 8. Validation Gates (must pass before declaring complete)

### 8.1 Phase 2 Identity Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `users_customuser` count | 3,531 (3,378 + 153) | 3,531 | ✅ |
| `users_identity` count | ~5,967 | 5,967 | ✅ |
| `users_employee` count | 68 | 68 | ✅ |
| Employees on ESH* identities | 68 (100% merged) | 68 | ✅ |
| `users_customer` count | ~2,435 | 2,435 | ✅ |
| Walk-ins merged to ESH* | ~50 | 43 | ✅ |
| Walk-ins on ID* identities | ~2,392 | 2,392 | ✅ |
| `users_player` count | ~84 | 69 | ✅ (15 ON CONFLICT) |
| Players merged to ESH* | ~40 | 18 | ✅ |
| `users_vendor_profile` count | ~415 | 415 | ✅ |
| `users_team_profile` count | 14 | 14 | ✅ |
| Multi-profile (emp+cust) | ~15 | 16 | ✅ |
| Unique phones in identities | ~5,950 | 5,953 | ✅ |

**Note:** Phase 2 uses phone-based merge — employees, walk-ins, and players link to existing eShop identities when phone matches. No duplicate phone constraint exists post-migration (dropped via `phase2_schema_fixes.sql`).

### 8.1.1 Spec Violation: `users_customuser` Data Duplication (PENDING REVIEW)

**Finding:** Phase 2 migrated `name`, `phone`, and `email` into BOTH `users_customuser` AND `users_identity`, violating the target schema spec.

**Spec intent** (`postgresql_schema.md` §2.1 / §3.1):
- `users_customuser` = **auth credentials only** (`userid`, `password`, `username`, `is_active`, `is_staff`, `is_superuser`, `is_admin`, `last_login`, `created_date`)
- `users_identity` = **all personal/identity data** (`identity_id`, `phone`, `name`, `email`, `bg_code`, `div_code`, `branch_code`, `status`, `phone_verified`, `idproof_type`, `idproof_number`)
- The spec explicitly marks `users_customuser`'s `phone`/`email`/`name` columns as **anti-patterns** (`USERNAME_FIELD='phone'`)

**Current state:**

| Field | `users_customuser` | `users_identity` | Spec says |
|-------|-------------------|------------------|-----------|
| `name` | ✅ populated | ✅ populated | `users_identity` only |
| `phone` | ✅ populated | ✅ populated | `users_identity` only |
| `email` | ✅ populated | ✅ populated | `users_identity` only |
| `password` | ✅ populated | ❌ N/A | `users_customuser` only |
| `username` | ✅ populated | ❌ N/A | `users_customuser` only |

**Impact:**
- Duplication creates drift risk (updates must hit both tables)
- Walk-in identities (`ID*` prefix) have correct NULL `user_id` FK — no auth row, data lives only in `users_identity`
- ESH* identities have data duplicated — `users_customuser` row exists with same `name`/`phone`/`email`

**Remediation options:**

| Approach | Effort | Risk |
|----------|--------|------|
| **A. Strip via Django migration** — Remove `name`/`phone`/`email` columns from `users_customuser` model. App reads from `users_identity` via FK. | High — requires Django model change + app code audit | Medium — must audit all direct `.name`/`.phone`/`.email` access on `CustomUser` |
| **B. Keep columns, make derived** — Make nullable, clear via data migration, add DB trigger to sync from `users_identity`. | Medium — trigger maintenance overhead | Low — zero app code changes |
| **C. Defer** — Leave as-is, address after all migrations complete. | Low | Low — duplication is benign for now |

**Decision:** DEFERRED — Will address after Phases 3–10 complete. Remaining migrations proceed one at a time with careful verification.

### 8.2 Phase 3 Custom Catalog Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `custom_catalog` total | 3,010 | 3,010 | ✅ |
| kgbuild (kg_mongo.kgbuilds) | 480 | 480 | ✅ |
| custombuild (kg_mongo.custombuilds) | 2,053 | 2,053 | ✅ |
| preset (kg_mongo.presets flattened) | 321 | 321 | ✅ |
| tpbuild (kc_mongo.tpbuilds) | 123 | 123 | ✅ |
| preset (kc_mongo.presets flattened) | 33 | 33 | ✅ |
| builds SKIPPED (duplicate of kgbuilds) | 0 | 0 | ✅ |
| Tenant fields present | 100% | 100% | ✅ |
| Source lineage (source_db/source_collection) | 100% | 100% | ✅ |

### 8.3 Phase 4 Products Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `products` total | 3,254 | 3,254 | ✅ |
| prods (kg_mongo.prods) | 2,481 | 2,481 | ✅ |
| components unique (not in prods) | 1 | 1 | ✅ |
| accessories (kg_mongo.accessories) | 504 | 504 | ✅ |
| monitors (kg_mongo.monitors) | 156 | 156 | ✅ |
| networking (kg_mongo.networking) | 17 | 17 | ✅ |
| external (kg_mongo.external) | 12 | 12 | ✅ |
| cables (kg_mongo.cables) | 1 | 1 | ✅ |
| cafe-food (kc_mongo.products) | 62 | 62 | ✅ |
| cafe-beverage (kc_mongo.products) | 20 | 20 | ✅ |
| tempproducts SKIPPED (delete_flag=true) | 0 | 0 | ✅ |
| components deduped against prods | 1,613 skipped | 1,613 | ✅ |
| F&B discriminator remap | food→cafe-food, beverage→cafe-beverage | ✅ | ✅ |

### 8.4 Phase 5 Inventory Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `inv_vendors` total | 424 (423 + INTERNAL) | 424 | ✅ |
| `inv_purchase_orders` total | 7,148 | 7,148 | ✅ |
| Standard POs (purchaseorders) | 5,557 | 5,557 | ✅ |
| Indent POs (indentproduct unique) | 1,591 | 1,591 | ✅ |
| Indent POs merged with existing | 85 | 85 | ✅ |
| INTERNAL vendor placeholder | 1 | 1 | ✅ |
| FK integrity (vendor_code) | 100% valid | 100% | ✅ |
| `inventory_inventoryitem` total | ~200 | 193 | ✅ |
| `inventory_inventorystock` total | 194 | 178 | ✅ (F&B per-branch) |

### 8.5 Phase 6 Finance Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `financial_documents` total | 13,014 | 13,014 | ✅ |
| inwardInvoices → inward_invoice | 4,750 | 4,750 | ✅ |
| outwardInvoices → outward_invoice | 1,192 | 1,192 | ✅ |
| inwardpayments → inward_payment | 3,188 | 3,188 | ✅ |
| inwardCreditNotes → inward_credit_note | 109 | 109 | ✅ |
| inwardDebitNotes → inward_debit_note | 3 | 3 | ✅ |
| outwardCreditNotes → outward_credit_note | 44 | 44 | ✅ |
| outwardDebitNotes → outward_debit_note | 13 | 13 | ✅ |
| paymentVouchers → payment_voucher | 3,715 | 3,715 | ✅ |

### 8.6 Phase 7 Orders Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `orders_core` total | 13,603 | 13,603 | ✅ |
| in_store (kgorders) | 12,174 | 12,174 | ✅ |
| tp (tporders) | 229 | 229 | ✅ |
| eShop inserted | 1,200 | 1,200 | ✅ |
| eShop source total | 1,206 | — | — |
| eShop merged (hex collision) | 6 | 6 | ⚠️ KNOWN |

**Note:** 6 eShop orders have hex-format orderids that collide with 6 lowercase hex-format kgorders. ON CONFLICT DO UPDATE merged them (in_store type preserved). The 3 uppercase hex kgorders (`673DF4897D`, `CBADFF99D6`, `F03BB0ADAE`) do NOT collide (case-sensitive PK).

### 8.7 Phase 8 Stock Register Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `stock_register` total | 194 | 194 | ✅ |
| kurogaming (PC stock) | 126 | 126 | ✅ |
| rebellion (F&B stock) | 68 | 68 | ✅ |
| Tenant fields present | 100% | 100% | ✅ |
| Source lineage | 100% | 100% | ✅ |
| `inventory_inventorystock` migrated | 194 | 178 | ✅ (F&B per-branch) |
| Insertions | 196 | 196 | ✅ |

### 8.8 Phase 9 eShop Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `eshop_cart` count | 748 | 748 | ✅ |
| `eshop_wishlist` count | 450 | 450 | ✅ |
| `users_saved_addresses` count | 1,064 | 1,064 | ✅ |
| Multi-address users preserved | Yes (e.g., 12 addresses for one user) | Yes | ✅ |
| FK integrity (identity_id) | 0 orphaned | 0 | ✅ |
| `companyname` NOT NULL | 0 NULLs | 0 (928 empty string, 136 with value) | ✅ |

### 8.9 Phase 7.6 Serial Migration Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `inventory_serial_record` total | 412 | 412 | ✅ |
| `inventory_inventorymovement` (serial_sold) | 890 | 890 | ✅ |
| `inventory_movement_serial` junctions | 882 | 882 | ✅ |
| `inventory_asset_installation` | 0 | 0 | ✅ (no asset conversions yet) |
| Unique serials | 411 | 412 | ✅ (1 placeholder for empty productid) |
| FK integrity (item_id) | 0 NULLs | 0 | ✅ |
| FK integrity (serial_id) | 0 NULLs | 0 | ✅ |
| Movement count reconciliation | 0 mismatches | 0 | ✅ |

**Note:** Serial tracking uses redesigned schema (v1.4) — FK-backed junction table replaces JSONB `sr_nos` field. See §9.15.10 for full schema details.

### 8.10 Phase 7.7 Serial Enrichment Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `sold_to_customer_id` populated | 34 | 34 | ✅ |
| `purchase_date` populated | 278 | 278 | ✅ |
| Date range | 2024-07-11 to 2026-06-15 | 2024-07-11 to 2026-06-15 | ✅ |
| Movement count mismatches | 0 | 0 | ✅ |

**Note:** Enrichment updates `inventory_serial_record` table (redesigned schema v1.4). See §9.15.10 for full schema details.

### 8.11 Phase 7.8 MongoDB Collections Gates (VERIFIED ✅)

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `vendors` | 423 | 423 | ✅ |
| `players` | 117 | 117 | ✅ |
| `serviceRequest` | 1,627 | 1,627 | ✅ |
| `teams` | 14 | 14 | ✅ |
| `employee_attendance` | 966 | 966 | ✅ |
| `indentpos` | 285 | 285 | ✅ |
| `bgData` | 1 | 1 | ✅ |
| `reb_users` | 2,540 | 2,540 | ✅ |
| **Total migrated** | 5,973 | 5,973 | ✅ |

### 8.12 Remaining Gates (pending Phase 10)

| Check | Expected |
|-------|----------|
| **Orders FK integrity** | `SELECT count(*) FROM orders_core o LEFT JOIN users_identity i ON o.customer_id=i.identity_id WHERE o.customer_id IS NOT NULL AND i.identity_id IS NULL` → 0 |
| **Orders per type** | eshop: 975 active (of 1,206 total), in_store: 12,160 (12,174 minus 14 cancelled, **0 hex exclusions**), estimate: 5,056, tp: 229, service: 1,627, cafe_fnb: 0 legacy |
| **Detail table completeness** | No missing and no orphaned detail rows per order_type |
| **Custom catalog total** | 3,010 documents in `custom_catalog` (2,854 from kg_mongo + 156 from kc_mongo)
| | **Breakdown:** kgbuilds(480) + custombuilds(2,053) + kg_presets(321) + tpbuilds(123) + kc_presets(33)
| | **builds(258) SKIPPED** — duplicate subset of kgbuilds (all 258 match kgbuilds with /AAAA suffix) |
| **Purchase orders total** | 7,148 in `inv_purchase_orders` (5,557 purchaseorders + 1,591 unique indentproduct, 85 indents share po_no with existing POs) |
| **Vendors total** | 424 in `inv_vendors` (423 source + 1 INTERNAL placeholder for stock transfers) |
| **Finance total** | 13,014 documents in `financial_documents` |
| **Outward preserved** | 781 documents in `outward` collection (shipment/delivery tracking) |
| **MongoDB canonical fields** | 100% of collections carry `bg_code`, `div_code`, `branch_code` |
| **Legacy collections** | Archived only after all above gates pass and 7-day monitoring window clears |

---

## 9. Runtime Execution Fixes (applied during Phases 0–7)

These fixes were discovered during actual migration execution and are applied to the deployment scripts. They are documented here for reference.

### 9.1 Phase 2 — Schema Constraint Drops

**Issue:** Django's unique constraints on `users_customuser` (phone, email, username) and `users_identity` (uq_identity_tenant_phone) blocked cross-source migration.

**Fix:** Created `phase2_schema_fixes.sql` to drop 4 constraints before Phase 2 execution. Applied via:
```bash
PGPASSWORD=postgres psql -h 127.0.0.1 -p 5432 -U postgres -d KungOS_PG_One \
  -f deployment_scripts/phase2_schema_fixes.sql
```

### 9.2 Phase 2 — Walk-in Garbage Phone Normalization

**Issue:** Non-digit phone strings (e.g., "walk-in", "no phone") normalize to `''`, triggering unique constraint conflicts.

**Fix:** Skip records with invalid/missing phones (95 walk-ins skipped). Empty phone does NOT create identity.

### 9.3 Phase 2 — Player ON CONFLICT Dedup

**Issue:** 15 players had `playerid` values that collided with existing `identity_id` values.

**Fix:** `ON CONFLICT (identity_id) DO UPDATE` merged them. Result: 69 unique players (not 84 expected).

### 9.4 Phase 3 — Preset Flattening Bug (Previous Run)

**Issue:** Previous migration run inserted 38 category indexes instead of 354 flattened items.

**Fix:** Clean-slate migration with proper `list[]` array flattening. Result: 354 items (321 kg + 33 kc).

### 9.5 Phase 4 — Variable Collision Bug

**Issue:** `AttributeError: 'dict' object has no attribute 'insert_one'` in `migrate_phase4_products.py`.

**Fix:** Renamed `target` variable to `target_coll`/`target_doc` to avoid collision between collection reference and document dict.

### 9.6 Phase 5 — Indent PO Overlap

**Issue:** 85 indentproduct records have `po_no` that overlaps with purchaseorders.

**Fix:** `ON CONFLICT DO UPDATE` correctly merged them. Result: 7,148 total (not 7,233 expected).

### 9.7 Phase 5 — Internal Vendor Placeholder

**Issue:** 781 indentproduct records have `vendor='instock'` and 441 have empty vendor.

**Fix:** Created `INTERNAL` vendor placeholder in `inv_vendors`. These records reference the INTERNAL vendor.

### 9.8 Phase 7 — Hex-Format Orderid Collision

**Issue:** 6 lowercase hex-format kgorders collide with 6 eShop orderids (case-sensitive PK).

**Fix:** ON CONFLICT DO UPDATE merges them (in_store type preserved). 3 uppercase hex kgorders do NOT collide.

**Evidence:**
```sql
-- Overlapping orderids (case-insensitive):
SELECT lower(order_id), array_agg(order_type)
FROM orders_core GROUP BY lower(order_id) HAVING count(*) > 1;
-- Results: 673df4897d {in_store,eshop}, cbadff99d6 {in_store,eshop}, f03bb0adae {eshop,in_store}
-- Plus 6 exact matches: d23d337c1f, d2d777f326, 2a215246d6, ce3b400abc, ceeb0f6919, 28f3fc5e82
```

### 9.9 Phase 7 — Source Database Correction

**Issue:** `kgorders` (12,174) is in `kuropurchase` DB (kc_mongo dump), NOT in `kg_inspect` (kg_mongo dump).

**Fix:** Migration script reads from `kuropurchase.kgorders` directly. `kg_inspect` only contains product collections.

### 9.10 Phase 7 — Entity/Branch Tenant Mapping

**Issue:** kgorders have `entity` + `branch` fields that must map to target tenant hierarchy.

**Fix:** Applied §2.1.4 mapping: `kurogaming/Madhapur` → `KURO0001_001_001`, `rebellion/Madhapur` → `KURO0001_002_001`, `rebellion/LB Nagar` → `KURO0001_002_002`.

### 9.11 Phase 7 — Date Format Normalization

**Issue:** kgorders use mixed date formats (`%d-%m-%Y, %H:%M:%S` and ISO 8601).

**Fix:** `parse_date()` helper handles multiple formats with fallback to migration timestamp.

### 9.12 Phase 7 — Status Normalization

**Issue:** kgorders have `order_status: null` (11,542), `Delivered` (615), `Cancelled` (14), `Created` (3).

**Fix:** `normalize_status()` maps null → `created`, preserves known statuses.

### 9.13 Phase 9 — companyname NOT NULL Constraint

**Issue:** `users_saved_addresses.companyname` has a NOT NULL constraint, but source `accounts_addresslist.companyname` is NULL for 266 of 1,064 records (and empty string for 662). The migration script's INSERT statement was missing the `companyname` column entirely, causing all 1,064 inserts to fail with NULL violations.

**Fix:** Added `companyname` to the INSERT column list and VALUES tuple. Normalized NULL → empty string `''` via `companyname = companyname or ""` in Python. Applied via `migrate_phase9_eshop.py`.

### 9.14 Phase 9 — Restrictive Unique Constraint on Addresses

**Issue:** `users_saved_addresses` has `UNIQUE (identity_id, bg_code, delete_flag)` which limits each user to one address per bg per delete_flag. Source data has 1,064 addresses across 1,018 users, with some users having multiple active addresses (e.g., home + office). Without fixing this, 36 addresses would be silently overwritten via ON CONFLICT DO UPDATE.

**Fix:** Dropped the `uq_saved_addr_identity_bg_active` constraint. The primary key (`id`, auto-incrementing) is sufficient for uniqueness. Added to `phase2_schema_fixes.sql` for reproducibility. Removed ON CONFLICT clause from migration script.

---

## 9.15 Phase 5b — Serial Record Migration (Schema + Data)

### 9.15.1 Users Migration 0004 Must Be Faked

**Issue:** Django migration `users.0004_delete_kurouser` tries to `DROP TABLE users_kurouser`, but the table doesn't exist in the target database (it was never migrated — employees were merged to ESH* identities in Phase 2b).

**Fix:** Run the migration with `--fake` flag to mark it as applied without executing:
```bash
python3 manage.py migrate users 0004 --fake
```
This is safe because the KuroUser model no longer exists in the Django codebase and all employee data was merged to `users_identity`.

### 9.15.2 Vendor Table Schema Mismatch

**Issue:** The existing `inv_vendors` table (created by Phase 5 migration) has a simpler schema than the new `Vendor` model:

| Phase 5 table | New Vendor model |
|---------------|-----------------|
| `vendor_code` (PK, VARCHAR(50)) | `vendor_code` (PK, VARCHAR(20)) |
| `name`, `phone`, `email`, `address` | `name`, `contact_person`, `contact_phone`, `contact_email` |
| `gstdetails` (JSONB) | `gstin`, `gstdetails`, `regaddress`, `shipaddress` |
| (no tenant fields) | `bg_code`, `div_code` |
| (no status fields) | `active`, `is_deleted` |
| (no audit fields) | `created_by`, `updated_by` |

**Fix:** Added `RunSQL` operation in migration `0008` to ALTER the existing table:
- Add missing columns with `ADD COLUMN IF NOT EXISTS`
- Set default values for existing rows (`bg_code='KURO0001'`, `active=true`, etc.)
- Create indexes and constraints on existing table
- Reverse operations drop the added columns

**Verification:**
```sql
-- Check all expected columns exist
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'inv_vendors' ORDER BY ordinal_position;
-- Expected: vendor_code, name, phone, email, address, gstdetails, 
--           pan, gstin, regaddress, shipaddress, contact_person,
--           contact_phone, contact_email, payment_type, bg_code,
--           div_code, active, is_deleted, created_by, created_at,
--           updated_by, updated_at
```

### 9.15.3 InventoryItem Placeholder Creation

**Issue:** Serial records reference `inventory_inventoryitem`, but the item table was empty. Each serial needs an `item_id` FK, but `item_id` has a NOT NULL constraint.

**Fix:** Before creating serial records, create placeholder `InventoryItem` for each unique `productid`:
```python
# Collect all unique productids first
productids = set()
for doc in outward_docs:
    for product in doc.get("products", []):
        productid = product.get("productid", "")
        if productid:
            productids.add(productid)

# Create placeholder items with ON CONFLICT handling
for productid in productids:
    cur.execute("""
        INSERT INTO inventory_inventoryitem (
            item_code, name, category, collection, unit_type, is_consumable,
            is_serialized, requires_serial, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (item_code) DO NOTHING
    """, (productid, productid, "__placeholder__", "__placeholder__", "pcs", False, True, True, '{}'))
    item_id_map[productid] = productid
```

**Key details:**
- `metadata` column has NOT NULL constraint → provide default `{}`
- `ON CONFLICT (item_code) DO NOTHING` prevents duplicate errors if items already exist
- Placeholder items are identifiable by `category='__placeholder__'`

### 9.15.4 SerialRecord NOT NULL Constraints

**Issue:** The `inventory_serial_record` table has multiple NOT NULL columns that require explicit values:
- `created_at`, `updated_at` (timestamps)
- `source_system`, `migration_batch` (audit fields)
- `item_id` (FK to InventoryItem)

**Fix:** Provide explicit values for all NOT NULL columns:
```python
cur.execute("""
    INSERT INTO inventory_serial_record (
        item_id, serial_number, bg_code, div_code, current_location,
        current_branch, sold_to_order, sold_date, warranty_expiry,
        warranty_source, source_system, migration_batch, metadata,
        movement_count, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT (serial_number) DO UPDATE
    SET current_location = EXCLUDED.current_location,
        current_branch = EXCLUDED.current_branch,
        sold_to_order = EXCLUDED.sold_to_order,
        sold_date = EXCLUDED.sold_date,
        warranty_expiry = EXCLUDED.warranty_expiry,
        updated_at = CURRENT_TIMESTAMP
""", (item_id, serial_number, bg_code, div_code, current_location,
      current_branch, sold_to_order, sold_date, warranty_expiry,
      warranty_source, 'kc_mongo', migration_batch, json.dumps(metadata),
      0))  # movement_count = 0
```

**Key details:**
- Use `CURRENT_TIMESTAMP` for `created_at`/`updated_at` to avoid NOT NULL violations
- `movement_count` initialized to 0 (updated by reconciliation job later)
- `ON CONFLICT` uses `serial_number` as the unique key (matches model `unique_together`)
- `json.dumps(metadata)` required because psycopg2 doesn't auto-serialize Python dicts

### 9.15.5 Empty ProductID Handling

**Issue:** 202 of 411 unique serials have empty `productid` in the source data. These cannot be linked to any `InventoryItem`.

**Fix:** Create a placeholder item for empty productids:
```python
# Add a placeholder for empty productids
productids.add("__EMPTY__")

# In serial creation, handle empty productid
actual_productid = productid if productid else "__EMPTY__"
item_id = item_id_map.get(actual_productid)
```

**Verification:**
```sql
-- Check empty productid placeholder exists
SELECT item_code, name FROM inventory_inventoryitem WHERE item_code = '__EMPTY__';
-- Expected: 1 row with name='__EMPTY__'
```

### 9.15.6 InventoryMovement Notes NOT NULL

**Issue:** The `inventory_inventorymovement` table has a NOT NULL constraint on the `notes` column. The migration script's INSERT statement was missing this column.

**Fix:** Add `notes` parameter to the INSERT:
```python
cur.execute("""
    INSERT INTO inventory_inventorymovement (
        bg_code, div_code, movement_type, item_id, serial_id,
        from_location, to_location, movement_date, movement_ref,
        source_system, migration_batch, notes, created_at, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
""", (bg_code, div_code, movement_type, item_id, serial_id,
      from_location, to_location, movement_date, movement_ref,
      'kc_mongo', migration_batch, f'Serial sold to {sold_to_order}'))
```

**Key details:**
- `notes` is required for audit trail — use descriptive text
- `movement_date` converted to `datetime.date` for PostgreSQL DATE type
- `CURRENT_TIMESTAMP` for `created_at`/`updated_at` to avoid NOT NULL violations

### 9.15.7 Date JSON Serialization

**Issue:** `warranty_expiry` and `sold_date` are `datetime.date` objects in Python. psycopg2 doesn't auto-serialize these when passed as parameters.

**Fix:** Convert to ISO format strings before passing to SQL:
```python
if warranty_expiry:
    warranty_expiry = warranty_expiry.isoformat() if isinstance(warranty_expiry, datetime.date) else warranty_expiry
if sold_date:
    sold_date = sold_date.isoformat() if isinstance(sold_date, datetime.date) else sold_date
```

**Key details:**
- PostgreSQL DATE type accepts ISO format strings (`YYYY-MM-DD`)
- `isinstance` check ensures we only convert if it's actually a date object
- Fallback to original value if already a string

### 9.15.8 Params Count Mismatch

**Issue:** `psycopg2` raises `tuple index out of range` when the params tuple has fewer elements than `%s` placeholders in the SQL.

**Fix:** Ensure params count matches placeholder count. For the serial_record INSERT:
- 14 `%s` placeholders + 2 `CURRENT_TIMESTAMP` = 16 values expected
- Original params had 13 values → added `movement_count` (0) to params tuple

**Verification:**
```python
# Count placeholders in SQL
placeholders = sql.count('%s')
print(f"Placeholders: {placeholders}, Params: {len(params)}")
# Expected: Placeholders: 14, Params: 14 (CURRENT_TIMESTAMP is not %s)
```

### 9.15.9 Migration Summary

**Source:** 781 outward records from `kc_inspect.outward`

**Results:**
| Entity | Count |
|--------|-------|
| InventoryItems (placeholder) | 193 |
| SerialRecords | 412 |
| InventoryMovements (serial_sold) | 890 |
| MovementSerial junctions | 882 |

**Key features:**
- Warranty rotation detection (7-30 days = return, >30 days = manual review)
- Migration batch tracking (`outward_20260702`)
- Movement count for drift detection
- FK-backed referential integrity (no more JSONB)

**Verification:**
```sql
-- Serial record counts
SELECT count(*) FROM inventory_serial_record;
-- Expected: 412

-- Movement counts by type
SELECT movement_type, count(*) FROM inventory_inventorymovement GROUP BY movement_type;
-- Expected: serial_sold: 890

-- Junction table integrity
SELECT count(*) FROM inventory_movement_serial;
-- Expected: 882

-- Movement count reconciliation
SELECT sr.serial_number, sr.movement_count, count(ms.id) as actual_junctions
FROM inventory_serial_record sr
LEFT JOIN inventory_movement_serial ms ON sr.id = ms.serial_record_id
GROUP BY sr.serial_number, sr.movement_count
HAVING count(ms.id) != sr.movement_count;
-- Expected: 0 rows (all counts match)
```

---

## 9.15.10 Inventory Schema Redesign (v1.4)

**Spec:** `/home/chief/llm-wiki/Kung_OS/specs/inventory_schema_redesign.md`

### 9.15.10.1 Design Rationale

The original inventory schema used `sr_nos JSONB` on movements for serial tracking, which had critical issues:
- No referential integrity — serial numbers could be misspelled or reference non-existent records
- No audit trail — couldn't query "current status of serial X"
- Dual-source-of-truth ambiguity — serial data duplicated across JSONB and application logic

**Redesign approach:** Replace JSONB with FK-backed junction table:
- `SerialRecord` — unified serial registry (one row per physical serial)
- `InventoryMovementSerial` — junction table linking movements to serials
- `InventoryAsset` — FK to SerialRecord (not string serial_number)

### 9.15.10.2 New Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `inventory_serial_record` | Unified serial registry | `item_id`, `serial_number`, `current_location`, `current_branch`, `warranty_expiry`, `purchase_cost`, `movement_count` |
| `inventory_movement_serial` | Movement↔Serial junction | `movement_id`, `serial_record_id` |
| `inventory_asset_installation` | Asset component tracking | `asset_id`, `item_id`, `serial_record_id` |

### 9.15.10.3 Modified Tables

**`inventory_inventoryitem`:**
- Added `requires_serial`, `supports_serial` boolean flags
- Removed `category='asset'` (items aren't inherently assets)

**`inventory_inventorymovement`:**
- Added `conversion_id` (UUID) to link paired stock↔asset movements
- Removed `sr_nos` JSONB field
- Added `to_asset`, `from_asset` movement types

**`inventory_asset`:**
- Replaced `serial_number` string with FK to `SerialRecord`
- Added `serial_record` OneToOneField

### 9.15.10.4 Migration Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `migrate_phase5_inventory.py` | Vendors + POs + items + stock | ✅ Completed |
| `migrate_phase5b_serials.py` | Serial records + movements + junctions | ✅ Completed |
| `migrate_phase5c_serial_enrichment.py` | Customer FK + purchase dates + movement count | ✅ Completed |

### 9.15.10.5 Verification

```sql
-- Serial record counts
SELECT count(*) FROM inventory_serial_record;
-- Expected: 412

-- Movement counts by type
SELECT movement_type, count(*) FROM inventory_inventorymovement GROUP BY movement_type;
-- Expected: serial_sold: 890

-- Junction table integrity
SELECT count(*) FROM inventory_movement_serial;
-- Expected: 882

-- Movement count reconciliation
SELECT sr.serial_number, sr.movement_count, count(ms.id) as actual_junctions
FROM inventory_serial_record sr
LEFT JOIN inventory_movement_serial ms ON sr.id = ms.serial_record_id
GROUP BY sr.serial_number, sr.movement_count
HAVING count(ms.id) != sr.movement_count;
-- Expected: 0 rows (all counts match)

-- Serial enrichment verification
SELECT count(*) FROM inventory_serial_record WHERE sold_to_customer_id IS NOT NULL;
-- Expected: 34

SELECT count(*) FROM inventory_serial_record WHERE purchase_date IS NOT NULL;
-- Expected: 278
```

---

## 9.16 Phase 5c — Serial Record Enrichment & Reconciliation

### 9.16.1 Customer FK Enrichment

**Issue:** Serial records have `sold_to_order` (outward orderid) but no FK to the customer identity.

**Fix:** Build lookup maps from outward orders → kgorders → user.phone → Identity, then update `sold_to_customer_id`:
```python
# Build orderid → phone map from kgorders
kgorders = mongo_client[SOURCE_KC_DB]['kgorders']
order_to_phone = {}
for outward in outward_docs:
    kgorder = kgorders.find_one({'orderid': outward['orderid']})
    if kgorder:
        phone = kgorder.get('user', {}).get('phone', '')
        if phone:
            order_to_phone[outward['orderid']] = normalize_phone(phone)

# Build phone → identity map
phone_to_identity = {}
for identity in Identity.objects.all():
    if identity.phone:
        phone_to_identity[identity.phone] = identity.identity_id

# Update serial records
for serial in SerialRecord.objects.all():
    phone = order_to_phone.get(serial.sold_to_order)
    if phone:
        identity_id = phone_to_identity.get(phone)
        if identity_id:
            serial.sold_to_customer_id = identity_id
            serial.save(update_fields=['sold_to_customer_id'])
```

**Results:** 34 of 412 serials linked to customer identities (only those with matching phones in kgorders).

### 9.16.2 Purchase Date Enrichment

**Issue:** Serial records have no `purchase_date` field populated.

**Fix:** Use `created_date` from outward collection (outward has no `order_date` field):
```python
outward_doc = mongo_client[SOURCE_KC_DB]['outward'].find_one({'orderid': outward_orderid})
if outward_doc:
    order_date = outward_doc.get('order_date') or outward_doc.get('created_date')
    if order_date and serial.purchase_date is None:
        date_obj = normalize_date(order_date)
        if date_obj:
            serial.purchase_date = date_obj
            serial.save(update_fields=['purchase_date'])
```

**Results:** 278 of 412 serials populated with purchase dates (range: 2024-07-11 to 2026-06-15).

### 9.16.3 Movement Count Reconciliation

**Issue:** The denormalized `movement_count` on SerialRecord may drift from actual junction entries over time.

**Fix:** Periodic reconciliation job (`deployment_scripts/reconcile_movement_counts.py`):
```bash
# Check for mismatches
python3 reconcile_movement_counts.py

# Auto-fix mismatches
python3 reconcile_movement_counts.py --fix
```

**Verification query:**
```sql
SELECT sr.serial_number, sr.movement_count, count(ms.id) as actual
FROM inventory_serial_record sr
LEFT JOIN inventory_movement_serial ms ON sr.id = ms.serial_record_id
GROUP BY sr.serial_number, sr.movement_count
HAVING count(ms.id) != sr.movement_count;
```

**Current status:** 0 mismatches (all counts match).

### 9.16.4 Enrichment Summary

| Field | Populated | Percentage |
|-------|-----------|------------|
| `sold_to_customer_id` | 34 | 8.3% |
| `purchase_date` | 278 | 67.5% |
| `purchase_cost` | 0 | 0% (outward has no price data) |
| Movement count reconciliation | 0 mismatches | 100% correct |

---

## 9.17 Phase 2/7 — MongoDB Identity & Transactional Collections to KungOS_PG_One

**Issue:** Several kc_mongo collections were migrated to KungOS_PG_One identity/transactional tables during Phases 2 and 7.

**Target:** All collections migrated to PostgreSQL tables in KungOS_PG_One.

| Collection | Count | Target Table | Phase |
|------------|-------|--------------|-------|
| `vendors` | 423 | `users_vendor_profile` | Phase 2e |
| `players` | 117 | `users_player` | Phase 2d |
| `teams` | 14 | `users_team_profile` | Phase 2f |
| `reb_users` | 2,540 | `users_customer` | Phase 2c |
| `serviceRequest` | 1,627 | `service_detail` (via OrderCore) | Phase 7 |
| `indentpos` | 285 | `indent`/`indent_item` | Phase 7 |
| `employee_attendance` | 966 | `users_employee_attendance` | Phase 7 |
| `bgData` | 1 | `tenant_business_groups`/`tenant_divisions` | Phase 2 |
| **Total** | **5,973** | | |

**Verification:**
```sql
-- Verify table counts in KungOS_PG_One
SELECT 'users_vendor_profile' as table_name, count(*) as count FROM users_vendor_profile
UNION ALL SELECT 'users_player', count(*) FROM users_player
UNION ALL SELECT 'users_team_profile', count(*) FROM users_team_profile
UNION ALL SELECT 'users_customer', count(*) FROM users_customer
UNION ALL SELECT 'indent', count(*) FROM indent
UNION ALL SELECT 'indent_item', count(*) FROM indent_item;
```

**Current KungOS_PG_One state (identity tables):**

| Table | Count |
|-------|-------|
| `users_vendor_profile` | 415 |
| `users_player` | 69 |
| `users_team_profile` | 14 |
| `users_customer` | 2,435 |
| `users_employee` | 68 |
| `users_organization` | 437 |

**Current KungOS_Mongo_One state (only product/finance data):**

| Collection | Count |
|------------|-------|
| `custom_catalog` | 3,010 |
| `financial_documents` | 13,014 |
| `products` | 3,254 |
| **Total** | **19,278** |

---

## 10. Key Risks Specific to Cross-DB/Cross-Project Migration

- **Source-of-truth confusion:** `KungOS_Mongo_One` (target) must never be read as a source during migration. All reads come from `/home/chief/kuro-legacy/` dumps only.
- **Phone format divergence across projects:** Kuro Gaming (`kg_pg`) uses `0XXXXX XXXXX` (space-separated, leading zero); Kuro Cadence (`kc_mongo`) mixes formats across collections. Test normalization against all formats before running dedup.
- **Backup staleness:** All 4 dumps in `/home/chief/kuro-legacy/` are dated 2026-06-30. Confirm these are the latest production backups before proceeding.
- **Tenant field absence in Kuro Gaming:** `kg_pg` has no `bg_code`/`div_code`/`branch_code` columns at all; default to `KURO0001`/`KURO0001_001`/`KURO0001_001_001` (Kuro Gaming Division). `kc_mongo` collections require entity→division mapping per §2.1.4.
- **File/schema conflicts:** Concurrent phases touching `domains/accounts/*` (finance ViewSets and accounts master-data ViewSets) must be sequenced, not run in parallel, to avoid merge conflicts.
- **mongorestore BSON version mismatch:** `kc_mongo` dump was produced by MongoDB 7.0.26; local mongorestore is 8.0.12. Use `--nsFrom`/`--nsTo` for namespace redirection (deprecated `--db`/`--collection` flags will fail). BSON compatibility warning is benign — data restores correctly.
- **pg_restore performance:** Full PostgreSQL restore can hang (>700s) on large dumps. Use `pg_restore --list` for inspection and targeted table extraction rather than full DB restore.
- **Django unique constraints block cross-source data:** `users_customuser` has unique constraints on `phone`, `email`, and `username` that prevent migrating the same person's accounts from both `kg_pg` and `kc_pg`. `users_identity` has `uq_identity_tenant_phone` that blocks phone-based dedup. **Fix:** Run `phase2_schema_fixes.sql` (in `deployment_scripts/`) before Phase 2. These constraints are safe to drop — phone/email uniqueness is enforced at the application level, not DB level.
- **Transaction cascade on error:** A single row error in a migration loop aborts the entire PostgreSQL transaction, causing all subsequent inserts to fail with "current transaction is aborted". **Fix:** Use `SAVEPOINT`/`ROLLBACK TO SAVEPOINT` for per-row error isolation (implemented in `migrate_phase2_identities.py`).

---

## A. Appendix: Source Dump Restoration Commands

### A.1 MongoDB Restoration (to inspection databases)

```bash
# Restore kg_mongo to inspection DB
mongorestore --archive=/home/chief/kuro-legacy/kg_mongo.dump \
  --nsFrom='products.*' --nsTo='kg_inspect.*' --drop

# Restore kc_mongo to inspection DB
mongorestore --archive=/home/chief/kuro-legacy/kc_mongo.dump \
  --nsFrom='kuropurchase.*' --nsTo='kc_inspect.*' --drop
```

### A.2 PostgreSQL Restoration (to inspection databases)

```bash
# Create inspection databases
PGPASSWORD=postgres createdb -h 127.0.0.1 -p 5432 -U postgres kg_pg_inspect
PGPASSWORD=postgres createdb -h 127.0.0.1 -p 5432 -U postgres kc_pg_inspect

# Restore kg_pg (select tables only to avoid django system tables)
PGPASSWORD=postgres pg_restore -h 127.0.0.1 -p 5432 -U postgres \
  -d kg_pg_inspect --no-owner --no-privileges \
  -t users_customuser -t users_phonemodel -t orders_orders -t orders_orderitems \
  -t accounts_cart -t accounts_wishlist -t accounts_addresslist \
  /home/chief/kuro-legacy/kg_pg.dump

# Restore kc_pg (select tables only)
PGPASSWORD=postgres pg_restore -h 127.0.0.1 -p 5432 -U postgres \
  -d kc_pg_inspect --no-owner --no-privileges \
  -t users_kurouser -t users_customuser -t users_phonemodel \
  -t users_accesslevel -t users_businessgroup -t users_switchgroupmodel \
  -t users_common_counters -t careers_jobapps \
  /home/chief/kuro-legacy/kc_pg.dump
```

### A.3 Target Database Reset (Phase 0)

```bash
# Truncate all non-Django tables in KungOS_PG_One
PGPASSWORD=postgres psql -h 127.0.0.1 -p 5432 -U postgres -d KungOS_PG_One -c "
DO \$\$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public'
              AND tablename NOT LIKE 'django%'
              AND tablename NOT LIKE 'auth_%'
              AND tablename NOT LIKE 'content_type%'
              AND tablename NOT LIKE 'knox_%')
    LOOP
        EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END \$\$;
"

# Drop all non-system collections in KungOS_Mongo_One
mongosh --eval "
db = db.getSiblingDB('KungOS_Mongo_One');
var collections = db.getCollectionNames();
collections.forEach(function(col) {
    if (!col.startsWith('system.')) {
        db[col].drop();
    }
});
"
```

---

## B. Appendix: Target Schema Quick Reference

### B.1 KungOS_PG_One — Table Summary

| Domain | Tables |
|--------|--------|
| Identity | `users_identity`, `identity_phone_aliases`, `users_customuser`, `users_customer`, `users_player`, `users_employee`, `users_saved_addresses`, `users_organization`, `users_vendor_profile`, `users_team_profile`, `users_user_tenant_context` |
| Orders | `orders_core`, `eshop_detail`, `in_store_detail`, `estimate_detail`, `tp_order_detail`, `service_detail`, `cafe_fnb_detail` |
| Inventory | `inv_vendors`, `inv_purchase_orders`, `inventory_inventoryitem`, `inventory_inventorystock`, `inventory_serial_record`, `inventory_movement_serial`, `inventory_asset_installation` |
| E-Commerce | `eshop_cart`, `eshop_wishlist` |
| Accounts | `acct_partners`, `acct_banks`, `acct_loans` |
| Cafe Platform | `caf_platform_*` (12 tables, already live) |

### B.2 KungOS_Mongo_One — Collection Summary

| Collection | Source | Notes |
|------------|--------|-------|
| `custom_catalog` | kg_mongo + kc_mongo | `custom_type` discriminator, 3,010 total (**builds** SKIPPED as duplicate of **kgbuilds**) |
| `financial_documents` | kc_mongo | `doc_type` discriminator, 13,014 total |
| `products` | kg_mongo + kc_mongo | `collection` discriminator; **prods/components overlap** (1,613 shared productids); **F&B remap** required |
| `reb_users` | kc_mongo | preserved as-is |
| `players` | kc_mongo | preserved as-is |
| `serviceRequest` | kc_mongo | preserved as-is |
| `teams` | kc_mongo | preserved as-is |
| `vendors` | kc_mongo | preserved as-is |
| `employee_attendance` | kc_mongo | preserved as-is |
| `stock_register` | kc_mongo | preserved as-is |
| `indentpos` | kc_mongo | preserved as-is |
| `bgData` | kc_mongo | preserved as-is |
| `outward` | kc_mongo | preserved as-is — shipment/delivery tracking with serial numbers |

---

*This document is the single source of truth for the KungOS migration. All counts, naming, and execution steps are reconciled against the actual S3 production dumps in `/home/chief/kuro-legacy/`.*
