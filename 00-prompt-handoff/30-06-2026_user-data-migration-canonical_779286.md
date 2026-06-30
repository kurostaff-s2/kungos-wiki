# Clean User Data Migration to Canonical Target

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `779286` |
| Entity type | `handoff` |
| Short description | Wipe dev target (`KungOS_PG_One` / `kuro-cadence`) and re-migrate all user data from eShop PG, KungOS Mongo, and legacy Mongo with consistent identity format and phone-based dedup |
| Status | `draft` |
| Source references | `30-06-2026_business-logic-data-audit_7111e7.md`, `migrate_identity.py`, `migrate_legacy_eshop.py` |
| Generated | `30-06-2026` |
| Next action / owner | Execute Phase 0 (truncate + schema reset) |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/30-06-2026_business-logic-data-audit_7111e7.md` (data audit + remediation plan)
- `/home/chief/Coding-Projects/kteam-dj-chief/users/management/commands/migrate_identity.py` (existing MongoDB identity migration)
- `/home/chief/Coding-Projects/kteam-dj-chief/plat/management/commands/migrate_legacy_eshop.py` (existing eShop migration)
**Key files for this task:**
- CREATE: `/home/chief/Coding-Projects/kteam-dj-chief/users/management/commands/migrate_users_canonical.py` (master migration command)
- MODIFY: `migrate_legacy_eshop.py` (fix extension table inserts)
- MODIFY: `migrate_identity.py` (add phone-based dedup against eShop)

---

## Goal

Wipe the dev target database (`KungOS_PG_One` / `kuro-cadence`) and re-migrate **all user data** from every source into a clean, consistent state with:

- **One identity per phone** — no duplicates across sources
- **Consistent identity ID format** — `ESH*` for eShop, `ID*` for walk-ins, `KCTM*`/`KCAD*` for employees, `REPL*` for players
- **Complete extension tables** — every identity has its corresponding profile row
- **Phone-based dedup** — eShop users inserted first; subsequent sources resolve by phone and either link or skip

---

## Source Inventory

### Source 1: `kg_eshop_latest` (PostgreSQL — legacy eShop)

| Table | Count | Notes |
|-------|-------|-------|
| `users_customuser` | 3,378 | All have unique non-empty phones. `userid` is 10-digit numeric varchar. |
| `accounts_addresslist` | 1,064 | FK to `userid`. |
| `accounts_cart` | 748 | FK to `userid`. |
| `accounts_wishlist` | 450 | FK to `userid`. |
| `orders_orders` | 1,206 | FK to `userid`. |
| `orders_orderitems` | 1,350 | FK to `orders_orders.orderid`. |

**Phone format:** `098765 4321` (space-separated, 5+6 digits with leading 0). All 3,378 phones are unique within eShop.

### Source 2: `KungOS_Mongo_One` (MongoDB — canonical consolidated)

| Collection | Count | Target Extension | Key Fields |
|------------|-------|-----------------|------------|
| `reb_users` | 1,982 | `users_customer` | `phone`, `name`, `bg_code`, `div_code`, `branch_code` |
| `players` | 117 | `users_player` | `mobile`, `name`, `playerid` (REPL*), `riotid`, `rank`, `teamid`, `bg_code` |
| `serviceRequest` | 1,625 | `users_customer` | `phone`, `name`, `bg_code` |
| `teams` | 14 | `users_team_profile` → `users_organization` | `name`, `teamid` (RETE*), `coach`, `userid`, `bg_code` |
| `vendors` | 409 | `users_vendor_profile` → `users_organization` | `name`, `vendor_code`, `pan`, `gstdetails[].gst.gstin`, `payment_type`, `regaddress`, `bg_code` |
| `employee_attendance` | 966 (31 unique) | `users_employee` | `userid` (KCTM/KCAD), `status`, `at_date`, `bg_code` |
| `orders` | 0 | — | Empty collection. |

**Phone format:** Mixed — `reb_users` uses `098765 4321` (matches eShop), `players` uses `6302659913` (no space), `serviceRequest` uses `7305400842` (no space). **Phone normalization is required.**

**Tenant fields:** All records have `bg_code`, `div_code`, `branch_code` from prior enrichment migration.

### Source 3: `kuropurchase` (MongoDB — legacy, pre-consolidation)

| Collection | Count | Notes |
|------------|-------|-------|
| `reb_users` | 2,533 | Superset of KungOS_Mongo_One (551 extra records). Many lack `bg_code`. |
| `players` | 117 | Same as KungOS. |
| `serviceRequest` | 1,627 | 2 extra vs KungOS. |
| `vendors` | 423 | 14 extra vs KungOS. |

**Do NOT use as primary source.** `KungOS_Mongo_One` is the enriched, tenant-tagged canonical. Only reference `kuropurchase` for records missing from KungOS (the 551 gap in `reb_users`).

---

## Target Schema (`KungOS_PG_One` / `kuro-cadence`)

### Core Tables

| Table | Primary Key | Key Constraint | Purpose |
|-------|-------------|----------------|---------|
| `users_identity` | `identity_id` | UNIQUE(`bg_code`, `phone`) | Canonical identity record |
| `identity_phone_aliases` | `id` | UNIQUE(`identity_id`, `alias_type`, `phone`) | Alternate phone numbers for same identity |

### Extension Tables (FK → `users_identity.identity_id`)

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `users_customuser` | `userid` | Django auth user (eShop + employees). FK: `user_id` → `users_identity` |
| `users_customer` | `identity_id` | Customer profile (order_count, total_spent, etc.) |
| `users_player` | `identity_id` | Player profile (riot_id, rank, team) |
| `users_employee` | `identity_id` | Employee profile (bank, address, BFC, etc.) |
| `users_saved_addresses` | `id` | Address book (UNIQUE: `identity_id`, `bg_code`, `delete_flag`) |

### Organization Tables (FK → `users_organization.org_id`)

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `users_organization` | `org_id` | Organization (vendor, team, etc.) |
| `users_vendor_profile` | `organization_id` | Vendor details (GSTIN, PAN, payment_type) |
| `users_team_profile` | `organization_id` | Team details (team_id, coach) |

### eShop Tables (FK → `users_identity.identity_id`)

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| `eshop_cart` | `id` | Shopping cart |
| `eshop_wishlist` | `id` | Wishlist (UNIQUE: `identity_id`, `productid`) |
| `eshop_detail` | `order_id` | Order details (1:1 with `orders_core`) |
| `orders_core` | `id` | Order header (FK: `customer_id` → `users_identity`) |

### Tenant Context

| Table | Purpose |
|-------|---------|
| `users_user_tenant_context` | Multi-tenant access scope (bg_code, div_codes, branch_codes) |

---

## Migration Order (Strict Sequential)

The migration order is defined by FK constraints and dedup requirements:

```
Phase 0: TRUNCATE + Schema Reset
    ↓
Phase 1: eShop Users (identity + customuser) [3,378]
    ↓
Phase 2: eShop Addresses [1,064]
    ↓
Phase 3: MongoDB Walk-in Customers (reb_users + serviceRequest) [dedup by phone]
    ↓
Phase 4: MongoDB Players [117]
    ↓
Phase 5: MongoDB Vendors + Organizations [409]
    ↓
Phase 6: MongoDB Teams + Organizations [14]
    ↓
Phase 7: Employees (employee_attendance → 31 unique) [31]
    ↓
Phase 8: eShop Orders + Detail [1,206]
    ↓
Phase 9: eShop Cart + Wishlist [748 + 450]
    ↓
Phase 10: Tenant Context + Validation
```

---

## Phase 0: Truncate + Schema Reset

**What:** Wipe all data from target and re-apply Django migrations to reset schema.

**Steps:**
1. Connect to `KungOS_PG_One` (`kuro-cadence`) as `postgres` user.
2. Execute:
   ```sql
   BEGIN;
   -- Disable FK checks temporarily
   SET session_replication_role = 'replica';
   
   -- Truncate in dependency order (leaf tables first)
   TRUNCATE TABLE eshop_detail CASCADE;
   TRUNCATE TABLE orders_core CASCADE;
   TRUNCATE TABLE eshop_cart CASCADE;
   TRUNCATE TABLE eshop_wishlist CASCADE;
   TRUNCATE TABLE users_saved_addresses CASCADE;
   TRUNCATE TABLE users_customer CASCADE;
   TRUNCATE TABLE users_player CASCADE;
   TRUNCATE TABLE users_employee CASCADE;
   TRUNCATE TABLE users_customuser CASCADE;
   TRUNCATE TABLE identity_phone_aliases CASCADE;
   TRUNCATE TABLE users_vendor_profile CASCADE;
   TRUNCATE TABLE users_team_profile CASCADE;
   TRUNCATE TABLE users_organization CASCADE;
   TRUNCATE TABLE users_user_tenant_context CASCADE;
   TRUNCATE TABLE users_identity CASCADE;
   
   -- Re-enable FK checks
   SET session_replication_role = 'origin';
   COMMIT;
   ```
3. Verify all tables are empty:
   ```sql
   SELECT table_name, count(*) FROM (
     SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'
   ) t
   LEFT JOIN LATERAL (
     SELECT count(*)::int FROM information_schema.columns c 
     WHERE c.table_name = t.table_name AND c.table_schema = 'public'
   ) sub ON true;
   ```
4. Re-apply Django migrations (in case any were rolled back):
   ```bash
   cd /home/chief/Coding-Projects/kteam-dj-chief
   python manage.py migrate --check
   ```

**Tests:**
- [ ] All 15+ tables return `count(*) = 0`
- [ ] `python manage.py migrate --check` reports no pending migrations
- [ ] Schema matches expected (all constraints, indexes, FKs intact)

---

## Phase 1: eShop Users (Identity + CustomUser)

**What:** Migrate all 3,378 eShop users with consistent `ESH` prefix and complete extension table.

**Source:** `kg_eshop_latest.users_customuser`
**Target:** `users_identity` + `users_customuser`

**Identity ID format:** `ESH` + `userid` (e.g., `ESH1003229619`)
**Tenant fields:** `bg_code = 'KURO0001'`, `div_code = 'KURO0001_001'`, `branch_code = 'KURO0001_001_001'`

**Steps:**
1. Create migration script (or modify `migrate_legacy_eshop.py`):
   ```python
   # For each user in kg_eshop_latest.users_customuser:
   # 1. Normalize phone: strip spaces, ensure 10 digits
   normalized_phone = phone.replace(' ', '')
   
   # 2. Insert identity
   INSERT INTO users_identity (
       identity_id, phone, name, email, bg_code, div_code, branch_code,
       status, phone_verified, created_at, updated_at
   ) VALUES (
       'ESH' || userid,
       normalized_phone,
       COALESCE(name, ''),
       COALESCE(email, ''),
       'KURO0001', 'KURO0001_001', 'KURO0001_001_001',
       'active', false, NOW(), NOW()
   )
   ON CONFLICT (identity_id) DO NOTHING;
   
   # 3. Insert customuser (Django auth extension)
   INSERT INTO users_customuser (
       userid, phone, name, email, is_active, password,
       is_staff, is_superuser, is_admin, created_date
   ) VALUES (
       userid,
       normalized_phone,
       COALESCE(name, ''),
       COALESCE(email, ''),
       is_active,
       'pbkdf2_sha256$260000$randomsalt$hashedpassword',  -- placeholder
       false, false, false,
       NOW()
   )
   ON CONFLICT (userid) DO NOTHING;
   
   # 4. Link identity → customuser via user_id FK
   UPDATE users_identity
   SET user_id = userid
   WHERE identity_id = 'ESH' || userid;
   ```

2. **Phone normalization function** (shared across all phases):
   ```python
   def normalize_phone(phone: str) -> str:
       """Normalize phone to 10-digit string without spaces."""
       if not phone:
           return ''
       digits = ''.join(c for c in str(phone) if c.isdigit())
       # Handle Indian numbers: if 9 digits starting with non-zero, prepend 0
       if len(digits) == 9 and digits[0] != '0':
           digits = '0' + digits
       return digits[:10]  # Truncate to 10 digits
   ```

3. Handle email uniqueness: `users_customuser` has UNIQUE constraint on `email`. If multiple eShop users share an email (or have empty email), use `ON CONFLICT (email) DO NOTHING` and log the conflict.

**Expected outcome:**
- `users_identity`: 3,378 rows (all `ESH*` prefix)
- `users_customuser`: ≤3,378 rows (may be less due to email conflicts)
- All phones normalized to 10-digit format

**Tests:**
- [ ] `SELECT count(*) FROM users_identity WHERE identity_id LIKE 'ESH%'` = 3,378
- [ ] `SELECT count(*) FROM users_customuser WHERE userid ~ '^[0-9]+$'` = ≤3,378
- [ ] Zero empty phones in `users_identity`
- [ ] All `ESH*` identities have `user_id` set (FK to customuser)
- [ ] `SELECT count(DISTINCT phone) FROM users_identity` = 3,378 (all unique)

---

## Phase 2: eShop Addresses

**What:** Migrate saved addresses for eShop users.

**Source:** `kg_eshop_latest.accounts_addresslist`
**Target:** `users_saved_addresses`

**Steps:**
1. For each address in `accounts_addresslist`:
   ```sql
   INSERT INTO users_saved_addresses (
       identity_id, bg_code, fullname, phone, altphone, pincode,
       address_line1, address_line2, landmark, city, state, country,
       gstin, pan, is_default, is_used, delete_flag, companyname,
       address_type, created_at, updated_at
   ) VALUES (
       'ESH' || userid,  -- Map to identity_id
       'KURO0001',
       fullname, phone, COALESCE(altphone, ''), pincode,
       addressline1, COALESCE(addressline2, ''), COALESCE(landmark, ''),
       city, state, 'IN',
       COALESCE(gstin, ''), COALESCE(pan, ''),
       is_default, is_used, COALESCE(delete_flag, false),
       COALESCE(companyname, ''),
       'shipping',
       NOW(), NOW()
   )
   ON CONFLICT (identity_id, bg_code, delete_flag) DO NOTHING;
   ```

**Tests:**
- [ ] `SELECT count(*) FROM users_saved_addresses` ≥ 1,064 (or less if addresses reference non-existent users)
- [ ] All `identity_id` values match `ESH*` prefix
- [ ] No orphaned addresses (all FK to existing `users_identity`)

---

## Phase 3: MongoDB Walk-in Customers (Phone Dedup)

**What:** Migrate `reb_users` and `serviceRequest` as walk-in customers, deduplicating by normalized phone against existing eShop identities.

**Source:** `KungOS_Mongo_One.reb_users` (1,982) + `KungOS_Mongo_One.serviceRequest` (1,625)
**Target:** `users_identity` + `users_customer`

**Identity ID format:** `ID` + zero-padded sequence (e.g., `ID000001`)

**Dedup strategy:**
```
FOR EACH walk-in record:
    normalized_phone = normalize_phone(record.phone)
    
    IF normalized_phone is empty:
        SKIP (log warning)
    
    IF phone exists in users_identity (bg_code='KURO0001', phone=normalized_phone):
        -- Phone matches an existing identity (likely eShop)
        existing = lookup_identity_by_phone(bg_code, normalized_phone)
        
        -- Update name if walk-in name is non-empty and different
        IF record.name != '' AND record.name != existing.name:
            UPDATE users_identity SET name = record.name WHERE identity_id = existing.identity_id
        
        -- Record phone alias for lineage
        INSERT INTO identity_phone_aliases (identity_id, phone, alias_type, is_active)
        VALUES (existing.identity_id, normalized_phone, 'walkin', true)
        ON CONFLICT (identity_id, alias_type, phone) DO NOTHING
        
        -- Create or update customer profile
        UPSERT users_customer FOR existing.identity_id
        
        LOG: "Walk-in {name} ({phone}) matched existing identity {existing.identity_id}"
    
    ELSE:
        -- New identity
        new_id = next_identity_id()  -- ID000001, ID000002, ...
        
        INSERT INTO users_identity (...)
        VALUES (new_id, normalized_phone, name, ..., 'KURO0001', div_code, branch_code, ...)
        
        INSERT INTO users_customer (identity_id, registered, is_requestor, ...)
        VALUES (new_id, false, true, ...)  -- walk-ins are requestors
        
        LOG: "New identity {new_id} for walk-in {name} ({phone})"
```

**Processing order:**
1. Process `reb_users` first (these are registered walk-in customers).
2. Process `serviceRequest` second (these are service requestors; may overlap with reb_users).
3. Within each collection, deduplicate by phone (same phone = same person).

**Tenant fields:** Use `bg_code`, `div_code`, `branch_code` from the MongoDB record (already enriched).

**Customer profile fields:**
- `registered`: `false` for walk-ins (not registered users)
- `is_requestor`: `true` for serviceRequest, `false` for reb_users
- `order_count`: 0 (will be updated when orders are migrated)
- `total_spent`: 0.00
- `service_count`: count of serviceRequest records for this phone

**Expected outcome:**
- New `ID*` identities for walk-ins with unique phones
- Existing `ESH*` identities enriched with walk-in data (name update, phone alias)
- `users_customer` rows for all walk-in identities
- `identity_phone_aliases` tracking phone-based merges

**Tests:**
- [ ] `SELECT count(*) FROM users_identity WHERE identity_id LIKE 'ID%'` = expected new walk-in count
- [ ] Zero phone conflicts: `SELECT phone, count(*) FROM users_identity GROUP BY phone HAVING count(*) > 1` = empty
- [ ] All walk-in identities have `users_customer` rows
- [ ] `identity_phone_aliases` has entries for merged identities

---

## Phase 4: MongoDB Players

**What:** Migrate esports players with phone-based dedup.

**Source:** `KungOS_Mongo_One.players` (117)
**Target:** `users_identity` + `users_player`

**Identity ID format:** Use existing `playerid` (e.g., `REPL000001`) as `identity_id`. If phone matches existing identity, use that identity_id instead.

**Dedup strategy:** Same as Phase 3 (phone lookup → merge or create new).

**Player profile fields:**
| Target Field | Source Field |
|-------------|-------------|
| `player_id` | `playerid` |
| `team_id` | `teamid` |
| `riot_id` | `riotid` |
| `rank` | `rank` |
| `identity_id` | resolved identity_id (from dedup) |

**Tests:**
- [ ] `SELECT count(*) FROM users_player` = 117
- [ ] All `player_id` values are unique
- [ ] All `identity_id` FKs resolve to existing `users_identity`

---

## Phase 5: MongoDB Vendors + Organizations

**What:** Migrate vendors into `users_organization` + `users_vendor_profile`.

**Source:** `KungOS_Mongo_One.vendors` (409)
**Target:** `users_organization` + `users_vendor_profile`

**Organization ID format:** `ORG` + zero-padded sequence (e.g., `ORG000001`) or preserve `vendor_code` (e.g., `MAKE03001A`) if it fits in 20 chars.

**Steps:**
1. For each vendor:
   ```sql
   -- 1. Create organization
   INSERT INTO users_organization (org_id, org_type, name, bg_code, div_code, created_at, updated_at)
   VALUES (vendor_code, 'vendor', name, bg_code, div_code, NOW(), NOW())
   ON CONFLICT (org_id) DO NOTHING;
   
   -- 2. Create vendor profile
   INSERT INTO users_vendor_profile (
       organization_id, gstin, pan, address, payment_type, contact_phone, contact_email
   ) VALUES (
       vendor_code,
       gstdetails[0].gst.gstin,  -- Extract from nested structure
       COALESCE(pan, ''),
       regaddress.line1 || ', ' || regaddress.line2 || ', ' || regaddress.city || ', ' || regaddress.province || ' ' || regaddress.pincode,
       COALESCE(payment_type, 'Post Paid'),
       '',  -- No contact phone in source
       ''   -- No contact email in source
   )
   ON CONFLICT (organization_id) DO NOTHING;
   ```

2. Handle GSTIN uniqueness: `users_vendor_profile` has UNIQUE on `gstin`. If a vendor has no GSTIN, the field is nullable — skip the constraint.

**Tests:**
- [ ] `SELECT count(*) FROM users_organization WHERE org_type = 'vendor'` = 409
- [ ] `SELECT count(*) FROM users_vendor_profile` = 409
- [ ] All `organization_id` FKs resolve

---

## Phase 6: MongoDB Teams + Organizations

**What:** Migrate esports teams into `users_organization` + `users_team_profile`.

**Source:** `KungOS_Mongo_One.teams` (14)
**Target:** `users_organization` + `users_team_profile`

**Organization ID format:** Use `teamid` (e.g., `RETE000001`) as `org_id`.

**Steps:**
1. For each team:
   ```sql
   INSERT INTO users_organization (org_id, org_type, name, bg_code, div_code, created_at, updated_at)
   VALUES (teamid, 'team', name, bg_code, div_code, NOW(), NOW())
   ON CONFLICT (org_id) DO NOTHING;
   
   INSERT INTO users_team_profile (organization_id, team_id, coach)
   VALUES (teamid, teamid, COALESCE(coach, ''))
   ON CONFLICT (organization_id) DO NOTHING;
   ```

**Tests:**
- [ ] `SELECT count(*) FROM users_organization WHERE org_type = 'team'` = 14
- [ ] `SELECT count(*) FROM users_team_profile` = 14

---

## Phase 7: Employees

**What:** Migrate 31 unique employees from `employee_attendance`.

**Source:** `KungOS_Mongo_One.employee_attendance` (966 records, 31 unique `userid`)
**Target:** `users_identity` + `users_customuser` + `users_employee`

**Identity ID format:** Preserve `userid` (e.g., `KCTM001`, `KCAD001`) as `identity_id`.

**Steps:**
1. Extract unique employees:
   ```javascript
   // MongoDB aggregation to get unique employees
   db.employee_attendance.aggregate([
       { $group: { _id: '$userid' } },
       { $sort: { _id: 1 } }
   ])
   ```

2. For each unique employee:
   ```sql
   -- 1. Create identity (check for phone conflict with eShop/walk-in)
   -- Note: employee_attendance does NOT have phone numbers
   -- Use empty phone or derive from existing customuser data
   INSERT INTO users_identity (
       identity_id, phone, name, bg_code, div_code, branch_code,
       status, phone_verified, created_at, updated_at
   ) VALUES (
       userid,
       '',  -- No phone in source
       '',  -- No name in source (derive from customuser if exists)
       'KURO0001', 'KURO0001_001', 'KURO0001_001_001',
       'active', false, NOW(), NOW()
   )
   ON CONFLICT (identity_id) DO NOTHING;
   
   -- 2. Create customuser (Django auth)
   INSERT INTO users_customuser (
       userid, phone, name, email, is_active, password,
       is_staff, is_superuser, is_admin, created_date
   ) VALUES (
       userid, '', '', '', true,
       'pbkdf2_sha256$260000$randomsalt$hashedpassword',
       false, false, false,
       NOW()
   )
   ON CONFLICT (userid) DO NOTHING;
   
   -- 3. Link identity → customuser
   UPDATE users_identity SET user_id = userid WHERE identity_id = userid;
   
   -- 4. Create employee profile
   INSERT INTO users_employee (
       identity_id, userid, role, department, joining_date,
       bank_name, bank_account_no, bank_ifsc, bank_branch,
       bfc_name, bfc_relation, bfc_phone, bfc_address, bfc_city,
       gender, dob, pan,
       perm_address_line1, perm_address_line2, perm_city, perm_state, perm_pin,
       pres_address_line1, pres_address_line2, pres_city, pres_state, pres_pin,
       emerg_name, emerg_phone,
       paid_offs, available_offs, festival_offs,
       created_by, approved_by, created_at, updated_at
   ) VALUES (
       userid, userid, '', '', NULL,
       '', '', '', '',
       '', '', '', '', '',
       '', NULL, '',
       '', '', '', '', '',
       '', '', '', '', '',
       '', '',
       0, 0, 0,
       '', '', NOW(), NOW()
   )
   ON CONFLICT (identity_id) DO NOTHING;
   ```

3. **Caveat:** `employee_attendance` has no phone, name, or employee details. The 31 unique userids are just attendance records. To populate employee profiles properly, you need the employee master data (which may be in `kuropurchase.reb_users` with KCTM/KCAD userid, or in a separate HR system).

4. **If employee master data exists in reb_users:** Cross-reference by userid pattern. If not, create minimal identities with placeholder data and flag for manual enrichment.

**Tests:**
- [ ] `SELECT count(*) FROM users_identity WHERE identity_id LIKE 'KCTM%' OR identity_id LIKE 'KCAD%'` = 31
- [ ] All employee identities have `users_customuser` rows
- [ ] All employee identities have `users_employee` rows
- [ ] All `user_id` FKs resolve

---

## Phase 8: eShop Orders + Detail

**What:** Migrate eShop orders with customer_id FK to resolved identity.

**Source:** `kg_eshop_latest.orders_orders` (1,206) + `orders_orderitems` (1,350)
**Target:** `orders_core` + `eshop_detail`

**Steps:**
1. For each order:
   ```sql
   -- 1. Insert order header
   INSERT INTO orders_core (
       order_id, order_type, status, customer_name, customer_phone,
       customer_email, bg_code, div_code, branch_code,
       total_amount, currency, channel, bill_address, products,
       active, delete_flag, created_by, created_date, updated_by, updated_date,
       customer_id
   ) VALUES (
       orderid, 'eshop', order_status,
       user_lookup[userid].name, user_lookup[userid].phone, '',
       'KURO0001', 'KURO0001_001', 'KURO0001_001_001',
       order_total, 'INR', COALESCE(channel, 'web'),
       bill_address_json, products_json,
       true, COALESCE(delete_flag, false),
       userid, order_created, userid, order_placed,
       'ESH' || userid  -- customer_id = identity_id
   )
   ON CONFLICT DO NOTHING;
   
   -- 2. Insert order detail (1:1 with order)
   INSERT INTO eshop_detail (
       order_id, shipping_address, payment_method, tracking_number,
       assigned_build_id, billing_address, build_fees, confirmed_at,
       delivered_at, discount_amount, failed_order_id, is_custom_build,
       package_fees, packed_at, payment_done_at, payment_expiry,
       payment_reference, pc_build_ended_at, pc_build_started_at,
       pc_test_ended_at, pc_test_started_at, processing_fees,
       product_total, shipped_at, shipping_agency, shipping_fees, status
   ) VALUES (
       order_core_id,  -- FK to orders_core.id
       shp_address_json, '', COALESCE(shp_awb, ''),
       '', bill_address_json, COALESCE(build_fees, 0), order_confirmed,
       order_delivered, COALESCE(kuro_discount, 0), COALESCE(fail_orderid, ''),
       false, COALESCE(pkg_fees, 0), order_packed,
       NULL, NULL, '',
       NULL, NULL, NULL, NULL,
       0, COALESCE(tax_total, 0), order_shipped,
       COALESCE(shp_agency, ''), COALESCE(shp_fees, 0), order_status
   );
   ```

2. Build `products_json` from `orders_orderitems`:
   ```json
   [
     {"productid": "...", "title": "...", "price": 0, "quantity": 0, "hsn_code": ""},
     ...
   ]
   ```

**Tests:**
- [ ] `SELECT count(*) FROM orders_core WHERE order_type = 'eshop'` = 1,206
- [ ] `SELECT count(*) FROM eshop_detail` = 1,206
- [ ] All `customer_id` FKs resolve to `ESH*` identities
- [ ] Order totals match source

---

## Phase 9: eShop Cart + Wishlist

**What:** Migrate shopping cart and wishlist data.

**Source:** `kg_eshop_latest.accounts_cart` (748) + `accounts_wishlist` (450)
**Target:** `eshop_cart` + `eshop_wishlist`

**Steps:**
1. Cart:
   ```sql
   INSERT INTO eshop_cart (identity_id, bg_code, productid, category, quantity, created_at, updated_at)
   SELECT 'ESH' || userid, 'KURO0001', productid, category, quantity, NOW(), NOW()
   FROM accounts_cart;
   ```

2. Wishlist:
   ```sql
   INSERT INTO eshop_wishlist (identity_id, bg_code, productid, created_at)
   SELECT 'ESH' || userid, 'KURO0001', productid, NOW()
   FROM accounts_wishlist
   ON CONFLICT (identity_id, productid) DO NOTHING;
   ```

**Tests:**
- [ ] `SELECT count(*) FROM eshop_cart` = 748
- [ ] `SELECT count(*) FROM eshop_wishlist` ≤ 450 (deduped by UNIQUE constraint)
- [ ] All `identity_id` FKs resolve

---

## Phase 10: Tenant Context + Validation

**What:** Create `users_user_tenant_context` entries and run full validation.

**Steps:**
1. Create tenant context for all identities:
   ```sql
   INSERT INTO users_user_tenant_context (userid, identity_id, bg_code, div_codes, branch_codes, scope, created_at, updated_at)
   SELECT 
       COALESCE(user_id, identity_id),
       identity_id,
       bg_code,
       ARRAY_TO_JSON(ARRAY[div_code])::jsonb,
       ARRAY_TO_JSON(ARRAY[COALESCE(branch_code, '')])::jsonb,
       CASE 
         WHEN identity_id LIKE 'KCTM%' OR identity_id LIKE 'KCAD%' THEN 'employee'
         WHEN identity_id LIKE 'ESH%' THEN 'customer'
         ELSE 'customer'
       END,
       NOW(), NOW()
   FROM users_identity
   ON CONFLICT DO NOTHING;
   ```

2. **Full validation queries:**
   ```sql
   -- Identity counts by type
   SELECT 
       CASE 
         WHEN identity_id LIKE 'ESH%' THEN 'eshop'
         WHEN identity_id LIKE 'ID%' THEN 'walkin'
         WHEN identity_id LIKE 'REPL%' THEN 'player'
         WHEN identity_id LIKE 'KCTM%' OR identity_id LIKE 'KCAD%' THEN 'employee'
         ELSE 'other'
       END as identity_type,
       count(*) as cnt
   FROM users_identity
   GROUP BY 1;
   
   -- Phone uniqueness check
   SELECT phone, count(*) as cnt
   FROM users_identity
   WHERE phone != ''
   GROUP BY phone
   HAVING count(*) > 1;
   -- Expected: 0 rows
   
   -- Orphaned extension check
   SELECT 'users_customer' as tbl, count(*) FROM users_customer c LEFT JOIN users_identity i ON c.identity_id = i.identity_id WHERE i.identity_id IS NULL
   UNION ALL
   SELECT 'users_player', count(*) FROM users_player p LEFT JOIN users_identity i ON p.identity_id = i.identity_id WHERE i.identity_id IS NULL
   UNION ALL
   SELECT 'users_employee', count(*) FROM users_employee e LEFT JOIN users_identity i ON e.identity_id = i.identity_id WHERE i.identity_id IS NULL;
   -- Expected: all 0
   
   -- Extension completeness
   SELECT 
       (SELECT count(*) FROM users_identity WHERE identity_id LIKE 'ESH%') as eshop_identities,
       (SELECT count(*) FROM users_customuser WHERE userid ~ '^[0-9]+$') as eshop_customusers,
       (SELECT count(*) FROM users_customer) as customers,
       (SELECT count(*) FROM users_player) as players,
       (SELECT count(*) FROM users_employee) as employees,
       (SELECT count(*) FROM users_organization WHERE org_type = 'vendor') as vendors,
       (SELECT count(*) FROM users_organization WHERE org_type = 'team') as teams;
   ```

**Expected final counts:**

| Table | Expected Count | Source |
|-------|---------------|--------|
| `users_identity` | ~5,116+ | 3,378 eShop + ~1,738 walk-in + 117 players + 31 employees (minus phone dedup) |
| `users_customuser` | ~3,409+ | 3,378 eShop + 31 employees |
| `users_customer` | ~1,738+ | Walk-in customers (reb_users + serviceRequest deduped) |
| `users_player` | 117 | Players |
| `users_employee` | 31 | Employees |
| `users_organization` | 423 | 409 vendors + 14 teams |
| `users_vendor_profile` | 409 | Vendors |
| `users_team_profile` | 14 | Teams |
| `users_saved_addresses` | ~1,064 | eShop addresses |
| `eshop_cart` | 748 | eShop cart |
| `eshop_wishlist` | ≤450 | eShop wishlist |
| `orders_core` | 1,206 | eShop orders |
| `eshop_detail` | 1,206 | eShop order detail |
| `identity_phone_aliases` | >0 | Merged identities |
| `users_user_tenant_context` | = `users_identity` count | All identities |

---

## Constraints

1. **No data deletion in legacy sources.** `kg_eshop_latest` and `kuropurchase` are read-only.
2. **Preserve lineage.** Every migrated identity retains source reference via `identity_id` prefix or `identity_phone_aliases`.
3. **Phone normalization is mandatory.** All phones normalized to 10-digit string (no spaces) before dedup comparison.
4. **Single tenant assumption.** All records use `bg_code = 'KURO0001'` unless source data specifies otherwise.
5. **Sequential execution.** Each phase must pass validation before proceeding to the next.
6. **eShop priority.** eShop users are migrated first; their `ESH*` identity_id is canonical for any phone-based merge.
7. **No silent failures.** All constraint violations, conflicts, and skips must be logged with source record identifier.
8. **Employee phone gap.** `employee_attendance` has no phone numbers. Employee identities use empty phone (won't conflict with phone dedup). If employee master data with phone exists elsewhere, merge in a separate step.

---

## Success Criteria

- [ ] Phase 0: Target truncated, schema clean (all tables empty, migrations applied)
- [ ] Phase 1: 3,378 eShop identities with `ESH*` prefix + customuser extension
- [ ] Phase 2: eShop addresses migrated with correct identity_id FK
- [ ] Phase 3: Walk-in customers migrated with zero phone conflicts against eShop
- [ ] Phase 4: 117 players migrated with player profile extension
- [ ] Phase 5: 409 vendors migrated with organization + vendor profile
- [ ] Phase 6: 14 teams migrated with organization + team profile
- [ ] Phase 7: 31 employees migrated with customuser + employee profile
- [ ] Phase 8: 1,206 orders migrated with customer_id FK to identity
- [ ] Phase 9: Cart + wishlist migrated with identity_id FK
- [ ] Phase 10: Tenant context created for all identities
- [ ] Zero phone duplicates in `users_identity` (UNIQUE constraint satisfied)
- [ ] Zero orphaned extension rows (all FKs resolve)
- [ ] `identity_phone_aliases` tracks all phone-based merges
- [ ] Full validation query suite passes

---

## Caveats & Uncertainty

1. **Employee master data missing.** `employee_attendance` only has 31 unique userids with no name/phone/details. Employee profiles will be created with placeholder data. If a separate employee master exists (e.g., HR system, `kuropurchase.reb_users` with KCTM/KCAD pattern), it should be merged post-migration.

2. **Phone normalization ambiguity.** eShop uses `098765 4321` format, MongoDB uses `9876543210` or `7305400842`. The normalization function strips spaces and ensures 10 digits. Edge case: if a MongoDB phone is 9 digits starting with non-zero, it's assumed to be missing a leading 0. **Verify with sample data before executing.**

3. **eShop email conflicts.** `users_customuser` has UNIQUE on `email`. Multiple eShop users may share an email or have empty email. The migration uses `ON CONFLICT (email) DO NOTHING` — this means some eShop users may not get a `users_customuser` row. **Acceptable for dev; may need resolution for production.**

4. **reb_users vs serviceRequest overlap.** Both collections have `phone` + `name`. A person may appear in both (walk-in who also filed a service request). The migration processes reb_users first, then serviceRequest deduplicates by phone. **Verify overlap count before executing.**

5. **Second source database unknown.** From the previous audit: `KungOS_Mongo_One` contains records not in `kuropurchase` (e.g., 16 extra `inwardinvoices`, thousands of `inwardpayments`). The identity of this second source is unknown. **Does not block user migration** (user data is fully accounted for in the sources listed).

6. **ServiceRequest has no userid.** Unlike reb_users, serviceRequest records don't have a userid field — only phone + name. They are treated as anonymous walk-in customers and merged by phone.

7. **Vendor contact_phone is empty.** Vendors in MongoDB have no contact phone field. The `contact_phone` in `users_vendor_profile` will be empty. **Acceptable — vendors don't need phone-based identity.**

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `users/management/commands/migrate_users_canonical.py` | Master migration command (all phases) |
| Modify | `plat/management/commands/migrate_legacy_eshop.py` | Fix users_customuser inserts (email conflict handling) |
| Modify | `users/management/commands/migrate_identity.py` | Add phone-based dedup against eShop identities |

---

## Clarification Needed Before Drafting

**Issue:** Employee master data source is unclear. `employee_attendance` has 31 unique userids but no name/phone/details.

**Context:** The `users_employee` table has 30+ fields (bank details, BFC info, addresses, etc.) that cannot be populated from attendance records alone.

**Options:**
- A: Create minimal employee identities with placeholder data (proceed now, enrich later)
- B: Search for employee master data in `kuropurchase` or other sources before migration
- C: Skip employee migration entirely (defer to separate HR data migration)

**Recommendation:** Option A — create minimal identities so the migration is complete. Flag for manual enrichment.

**Blocking:** No — can proceed with placeholder data.

---

## Execution Notes

1. **Dry-run first.** Execute with `--dry-run` flag to verify counts without writing.
2. **Log all merges.** Every phone-based merge (walk-in → eShop identity) should be logged to `identity_phone_aliases` AND to stdout for audit.
3. **Rollback plan.** If any phase fails, truncate target and re-run from Phase 0. No partial state should persist.
4. **Performance.** Use batch inserts (e.g., `executemany` with 500-row batches) for large collections. MongoDB aggregation for dedup within collections before PG insert.
5. **Transaction safety.** Wrap each phase in a transaction. Commit only after phase validation passes.
