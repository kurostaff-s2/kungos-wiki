# Business Logic Data Audit — Migration, Consolidation & Dedup Handoff

| Field | Value |
|-------|-------|
| Project ID | `kungos-backend` |
| Primary entity ID | `7111e7` |
| Entity type | `handoff` |
| Short description | Business logic audit of actual data across all four databases, with handoff for migration repairs, data consolidation, and deduplication |
| Status | `draft` |
| Source references | `llm-wiki/00-prompt-handoff/30-06-2026_migration-data-integrity-audit_df1c39.md`, live database queries (30-06-2026) |
| Generated | `30-06-2026` |
| Next action / owner | Execute Phase 1 (Data Enrichment & Backfill) — add missing `bg_code`/`branch_code`/`div_code` to pre-consolidation records, then re-migrate |

---

## Executive Summary

A business logic audit of the actual data across four databases (`kuropurchase`, `KungOS_Mongo_One`, `kg_eshop_latest`, `kuro-cadence`) reveals three root causes for data loss:

1. **Pre-consolidation records missing tenant fields** — 4,673 records across 7 collections in `kuropurchase` were never migrated to `KungOS_Mongo_One` because they lack `bg_code`, `branch_code`, `div_code`. These are legitimate business records (estimates, orders, vendors, users) from before the multi-tenant schema was introduced.

2. **Internal credit notes excluded from consolidation** — 44 `KGCN-` series (KungOS Credit Note) documents in `outwardcreditnotes` were not migrated to `financial_documents` because the consolidation script only processed vendor-issued credit notes, not internally generated ones.

3. **eShop phone dedup skipped 73% of users** — 2,469 of 3,378 eShop users were not migrated because their phone numbers already exist in `users_identity` from walk-in/employee records. This is intentional dedup, but it orphaned their orders, carts, and wishlists.

Additionally, the `purchaseorders` collection is a **mixed-domain collection** containing both actual purchase orders (9,990) and expense/payment records (3,685). Only 5,362 were migrated to PostgreSQL — the migration filtered by `po_no` presence but missed expense records that also have `po_no`.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:** `llm-wiki/00-prompt-handoff/30-06-2026_migration-data-integrity-audit_df1c39.md`
**Key files for this task:**
- `plat/management/commands/migrate_legacy_eshop.py` — eShop migration (needs dedup fix)
- `/tmp/consolidate_finance.py` — finance consolidation (needs KGCN + paymentvouchers)
- Migration scripts for `kuropurchase` → `KungOS_Mongo_One` (need tenant field enrichment)

**Databases:**
- MongoDB `kuropurchase` — Original legacy source (pre-consolidation)
- MongoDB `KungOS_Mongo_One` — Current canonical MongoDB (post-consolidation, with gaps)
- PostgreSQL `kg_eshop_latest` — Legacy eShop (pre-migration)
- PostgreSQL `kuro-cadence` — Current target (post-migration)

---

## Root Cause Analysis

### Root Cause 1: Missing Tenant Fields (4,673 records)

**Evidence:** Every missing record across all 7 collections lacks `bg_code` (and typically `branch_code`, `div_code`). The migration scripts filtered for records WITH these fields.

| Collection | kuropurchase | KungOS_Mongo_One | Missing | All Missing Lack bg_code? |
|---|---|---|---|---|
| `estimates` | 5,052 | 4,308 | **744** | ✅ 744/744 |
| `kgorders` | 12,134 | 9,162 | **2,972** | ✅ 2,972/2,972 |
| `vendors` | 423 | 409 | **14** | ✅ 14/14 |
| `reb_users` | 2,533 | 1,982 | **551** | ✅ 551/551 |
| `indentpos` | 283 | 247 | **36** | ✅ 36/36 |
| `indentproduct` | 1,649 | 1,490 | **159** | ✅ 159/159 |
| `serviceRequest` | 1,627 | 1,625 | **2** | ✅ 2/2 |
| `inwardInvoices` | 4,750 | 4,631 | **135** | ✅ 135/135 |
| `outwardInvoices` | 1,192 | 1,165 | **27** | ✅ (inferred, same pattern) |
| `paymentVouchers` | 3,715 | 3,459 | **256** | ✅ (inferred, same pattern) |
| `outwardCreditNotes` | 44 | 150 | — | KungOS has more (2nd source) |
| **Total** | — | — | **4,673+** | — |

**Business impact:** These are NOT junk records. Sampled missing estimates have `estimate_no`, `orderid`, `totalprice`, customer data, and confirmed orders. They represent real revenue that is invisible in the canonical system.

**Remediation:** Enrich missing records with default tenant fields (`bg_code: 'KURO0001'`, `div_code: 'KURO0001_001'`, `branch_code: 'KURO0001_001_001'`) and re-migrate.

### Root Cause 2: Internal Credit Notes Not Consolidated (44 records)

**Evidence:** `outwardcreditnotes` has 150 documents. `financial_documents` has 106 `outward_credit_note` records. The 44 missing all have `creditnote_no` matching pattern `KGCN-*` (KungOS Credit Note). The 106 migrated have vendor credit note patterns (`KA-C-*`, `ADS620-*`, `HGR-*`, etc.).

**Business impact:** Internal credit notes represent adjustments/refunds issued BY KungOS (not received from vendors). These are needed for accurate financial reporting.

**Sample missing:**
- `KGCN-001` through `KGCN-010+` — amounts ranging from ₹1,427 to ₹348,000
- All have proper `bg_code`, `branch_code`, `div_code`
- All have `vendor: undefined` (internally issued, no vendor)

**Remediation:** Add `outwardcreditnotes` with `creditnote_no` starting with `KGCN` to the consolidation script.

### Root Cause 3: eShop Phone Dedup (2,469 users skipped)

**Evidence:** All 2,469 skipped eShop users have phone numbers that already exist in `users_identity` with non-ESH prefix (walk-in/employee identities). The migration uses `ON CONFLICT (identity_id) DO NOTHING` but the UNIQUE constraint is on `(bg_code, phone)` — so phone conflicts cause silent INSERT failures.

**Business impact:** 73% of eShop users were not migrated. Their orders (993 migrated out of 1,206 = 213 skipped), carts (257/748 = 491 skipped), and wishlists (185/450 = 265 skipped) are either orphaned or lost.

**The 909 migrated users** are those whose phones did NOT conflict — likely new customers who only exist in eShop.

**Remediation options:**
- **A (merge):** Link eShop user data to existing identity (update name/email on the existing record). This preserves the identity but loses eShop-specific data.
- **B (separate):** Create ESH-prefixed identities with a `source_identity_id` FK to the existing record. This preserves both but creates logical duplicates.
- **C (skip with linkage):** Don't create new identities, but create a `users_eshop_profile` table that links eShop data to existing identities by phone.

**Recommendation:** Option C — create a linkage table. This is the cleanest approach: one canonical identity per phone, with eShop-specific data (order history, cart, wishlist) linked via phone number.

### Root Cause 4: Mixed-Domain `purchaseorders` Collection

**Evidence:** The `purchaseorders` collection contains:

| Category | Count | Characteristics |
|---|---|---|
| Actual POs | 9,990 | Has `po_no`, no `type` field, has `vendor` |
| Expense/Payment records | 3,685 | Has `type` (e.g., "Expenses - Salaries"), has `pv_no`, `amount`, `pay_method` |
| Unclassified | 1,541 | No `type`, no `po_no` — drafts or junk |

**Business impact:** The PG `inv_purchase_orders` table has 5,362 rows — roughly half the actual POs. The migration likely filtered by `po_no` presence but had other exclusion criteria. The 3,685 expense records should NOT be in `inv_purchase_orders` — they belong in `financial_documents` or a new `expenses` table.

**Remediation:** Separate the collection into two migrations: (1) actual POs → `inv_purchase_orders`, (2) expense records → `financial_documents` (doc_type=`expense`) or new `expenses` table.

---

## Phase 1: Data Enrichment & Backfill

**What:** Add missing tenant fields (`bg_code`, `branch_code`, `div_code`) to pre-consolidation records in `kuropurchase`, then re-migrate to `KungOS_Mongo_One`.

**Dependencies:** None.

**Steps:**

1. **Identify all records missing `bg_code` in `kuropurchase`:**

   For each collection (`estimates`, `kgorders`, `vendors`, `reb_users`, `indentpos`, `indentproduct`, `serviceRequest`, `inwardInvoices`, `outwardInvoices`, `paymentVouchers`), find documents where `bg_code` is null/missing.

2. **Enrich with default tenant fields:**

   ```javascript
   // For each collection without bg_code:
   db.<collection>.updateMany(
     { bg_code: { $exists: false } },
     { $set: {
         bg_code: "KURO0001",
         div_code: "KURO0001_001",
         branch_code: "KURO0001_001_001"
       }
     }
   )
   ```

   **Caveat:** This assumes all pre-consolidation records belong to the single KURO0001 tenant. If multi-tenant data exists in kuropurchase, this must be verified first.

3. **Re-migrate enriched records to `KungOS_Mongo_One`:**

   Use upsert (`updateMany` with `upsert: true`) to add missing records without duplicating existing ones.

4. **Verify counts match:**

   | Collection | Target Count |
   |---|---|
   | `estimates` | 5,052 |
   | `kgorders` | 12,134 |
   | `vendors` | 423 |
   | `reb_users` | 2,533 |
   | `indentpos` | 283 |
   | `indentproduct` | 1,649 |
   | `serviceRequest` | 1,627 |
   | `inwardinvoices` | 4,750+ (may have 2nd source records too) |
   | `outwardinvoices` | 1,192+ |
   | `paymentvouchers` | 3,715+ |

**Tests:**
- [ ] All collections in `KungOS_Mongo_One` match or exceed `kuropurchase` counts
- [ ] No duplicate records introduced (verify by `_id` uniqueness)
- [ ] All migrated records have `bg_code`, `branch_code`, `div_code`

**Output artifacts:**
- `/tmp/data_audit/enrichment_log.md` — what was enriched, counts before/after
- `/tmp/data_audit/remigration_counts.md` — counts after re-migration

---

## Phase 2: Finance Consolidation Repairs

**What:** Fix the three gaps in `financial_documents`: KGCN credit notes, paymentvouchers, and dropped collections.

**Dependencies:** None (can run in parallel with Phase 1).

**Steps:**

1. **Migrate 44 missing KGCN credit notes:**

   ```javascript
   // In KungOS_Mongo_One:
   db.outwardcreditnotes.find({ creditnote_no: { $regex: "^KGCN" } }).forEach(doc => {
     doc.doc_type = "outward_credit_note";
     doc.migrated_at = new Date();
     db.financial_documents.insertOne(doc);
   })
   ```

   **Verify:** `financial_documents` should have 150 `outward_credit_note` (was 106).

2. **Migrate 3,459 `paymentvouchers` to `financial_documents`:**

   Map fields:
   - `doc_type: "payment_voucher"`
   - Keep: `pv_no`, `po_no`, `vendor`, `amount`, `paid_by`, `pay_method`, `pay_account`, `pay_date`, `pay_ref_utr`, `narration`, `settled`, `status`
   - Add: `migrated_at: new Date()`

   **Verify:** `financial_documents` should have 3,459 `payment_voucher` (was 0).

3. **Assess dropped collections (`outwardpayments`, `settlements`, `bulkpayments`):**

   - Check if these exist in `kuropurchase` database (different collection names?)
   - Check `latest-mongo-backup.dump` for recoverable data
   - If found: migrate to `financial_documents` with appropriate doc_types
   - If NOT found: document as permanent data loss

   **kuropurchase does NOT have these collections** — they were likely in the second source database that was merged into KungOS. If the backup doesn't have them, mark ViewSets as deprecated (410 Gone).

4. **Migrate expense records from `purchaseorders` collection:**

   The 3,685 records with `type` field (Expenses - X) should be migrated to `financial_documents` with `doc_type: "expense"`:
   - Map: `type` → `expense_category`, `pv_no` → `reference_no`, `amount` → `amount`
   - Keep: `pay_method`, `pay_account`, `pay_date`, `narration`, `fin_year`

**Tests:**
- [ ] `financial_documents` has 150 `outward_credit_note` (was 106)
- [ ] `financial_documents` has 3,459 `payment_voucher` (was 0)
- [ ] `financial_documents` has 3,685 `expense` (was 0) — if Option A chosen
- [ ] Dropped collections assessed (recovered or documented as permanent loss)

---

## Phase 3: Purchase Order Separation & Migration

**What:** Separate the mixed-domain `purchaseorders` collection and migrate clean POs to PostgreSQL.

**Dependencies:** Phase 1 (tenant field enrichment must happen first).

**Steps:**

1. **Separate actual POs from expense records:**

   ```javascript
   // Actual POs: have po_no, no type field
   const actualPOs = db.purchaseorders.find({
     po_no: { $ne: null, $ne: "" },
     $or: [{ type: null }, { type: { $exists: false } }],
     creditnoteid: { $exists: false },
     pv_no: { $exists: false }
   });
   // Count: ~9,990

   // Expense records: have type field
   const expenseRecords = db.purchaseorders.find({
     type: { $ne: null, $ne: "" }
   });
   // Count: ~3,685
   ```

2. **Migrate actual POs to `inv_purchase_orders`:**

   Current: 5,362 rows. Target: ~9,990 rows.
   - Use upsert on `po_no` to avoid duplicates
   - Map: `po_no`, `vendor` → `vendor_code`, `totalprice` → `total_amount`, `branch_code`, `bg_code`, `div_code`, `created_by`, `created_date`, `status` (default 'draft' if null)

3. **Handle the 1,541 unclassified records (no type, no po_no):**

   - Inspect sample: are these drafts, cancelled POs, or junk?
   - If they have `pv_no` or `amount`: they're expense records missing the `type` field
   - If they have neither: likely junk/drafts — document and skip

4. **Verify `inv_vendors` FK constraint:**

   The 14 newly migrated vendors (Phase 1) must exist in `inv_vendors` before their POs can be migrated (FK constraint on `vendor_code`).

**Tests:**
- [ ] `inv_purchase_orders` has ~9,990 rows (was 5,362)
- [ ] No FK violations on `vendor_code`
- [ ] All POs have non-null `po_no`
- [ ] Expense records NOT in `inv_purchase_orders`

---

## Phase 4: eShop Dedup Resolution

**What:** Resolve the 2,469 skipped eShop users and their orphaned data.

**Dependencies:** None (can run in parallel with Phases 1-3).

**Steps:**

1. **Create `users_eshop_profile` linkage table:**

   ```sql
   CREATE TABLE users_eshop_profile (
       identity_id VARCHAR(20) PRIMARY KEY,
       email VARCHAR(255),
       name VARCHAR(200),
       is_active BOOLEAN DEFAULT true,
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );
   ```

   This stores eShop-specific user data linked to the canonical `users_identity` by `identity_id` (which matches the phone-based identity).

2. **For the 2,469 "skipped" users:**

   - Find their existing identity by phone: `SELECT identity_id FROM users_identity WHERE phone = <eshop_phone>`
   - Insert eShop profile data into `users_eshop_profile` with that `identity_id`
   - Update `eshop_cart`, `eshop_wishlist`, `eshop_detail` to reference the existing `identity_id` (not ESH-prefixed)

3. **For the 909 already-migrated ESH users:**

   - These already have ESH-prefixed `identity_id` in `users_identity`
   - Their carts/wishlists/orders reference the ESH ID
   - **No action needed** — they're already correctly linked

4. **Re-migrate orphaned eShop data:**

   - **Orders:** 213 skipped orders — match by userid → existing identity, insert into `orders_core` + `eshop_detail`
   - **Carts:** 491 skipped cart items — match by userid → existing identity, insert into `eshop_cart`
   - **Wishlists:** 265 skipped wishlists — match by userid → existing identity, insert into `eshop_wishlist`
   - **Addresses:** Match by userid → existing identity, insert into `users_saved_addresses`

**Tests:**
- [ ] All 3,378 eShop users have a corresponding identity (either ESH-prefixed or linked via phone)
- [ ] All 1,206 eShop orders are in `orders_core` (order_type='eshop')
- [ ] All 748 cart items are in `eshop_cart`
- [ ] All 450 wishlists are in `eshop_wishlist`
- [ ] No orphaned references (cart/wishlist/order pointing to non-existent identity)

---

## Phase 5: Indent Data Migration

**What:** Migrate `indentpos` and `indentproduct` to the existing empty PostgreSQL tables.

**Dependencies:** Phase 1 (tenant field enrichment).

**Steps:**

1. **Migrate `indentpos` → `inventory_indent`:**

   - 283 records (after Phase 1 enrichment)
   - Map: `vendor`, `products[]` → flattened to `inventory_indentitem`, `totalprice`, `batchid`, `fin_year`, `branch_code`, `bg_code`, `div_code`
   - The `products` array needs to be split into `inventory_indentitem` rows

2. **Migrate `indentproduct` → `inventory_indent` (separate category):**

   - 1,649 records (after Phase 1 enrichment)
   - These have `vendor: 'instock'` — internal procurement indents
   - Same mapping as indentpos

3. **Verify:**

   - `inventory_indent` should have 1,932 rows (283 + 1,649)
   - `inventory_indentitem` should have N rows (sum of all `products[]` array lengths)

**Tests:**
- [ ] `inventory_indent` has 1,932 rows (was 0)
- [ ] `inventory_indentitem` has data (was 0)
- [ ] All indent items reference valid indent parent

---

## Phase 6: Production Validation

**What:** Full system validation after all data repairs.

**Dependencies:** Phases 1-5 complete.

**Steps:**

1. **Count verification:**

   | Database | Collection/Table | Expected Count |
   |---|---|---|
   | KungOS_Mongo_One | estimates | 5,052 |
   | KungOS_Mongo_One | kgorders | 12,134 |
   | KungOS_Mongo_One | vendors | 423 |
   | KungOS_Mongo_One | reb_users | 2,533 |
   | KungOS_Mongo_One | indentpos | 283 |
   | KungOS_Mongo_One | indentproduct | 1,649 |
   | KungOS_Mongo_One | serviceRequest | 1,627 |
   | KungOS_Mongo_One | financial_documents (outward_credit_note) | 150 |
   | KungOS_Mongo_One | financial_documents (payment_voucher) | 3,459 |
   | kuro-cadence | inv_purchase_orders | ~9,990 |
   | kuro-cadence | inv_vendors | 423 |
   | kuro-cadence | orders_core (eshop) | 1,206 |
   | kuro-cadence | eshop_detail | 1,206 |
   | kuro-cadence | eshop_cart | 748 |
   | kuro-cadence | eshop_wishlist | 450 |
   | kuro-cadence | inventory_indent | 1,932 |
   | kuro-cadence | users_identity | 10,604 + linkage (no new rows, just profiles) |

2. **Integrity checks:**
   - [ ] No FK violations in PostgreSQL
   - [ ] All `financial_documents` have valid `doc_type`
   - [ ] All `orders_core` have matching detail rows
   - [ ] All `inv_purchase_orders` reference valid `inv_vendors`

3. **Application checks:**
   - [ ] `python manage.py check` passes
   - [ ] `python manage.py migrate --check` passes
   - [ ] All ViewSets return correct data

---

## Constraints

- **No data deletion** — Legacy collections in `kuropurchase` are read-only. Only add/enrich, never delete.
- **Preserve lineage** — Every migrated record retains its original `_id` or primary key.
- **One phase at a time** — Each phase must pass its tests before proceeding.
- **Tenant field assumption** — Phase 1 assumes all pre-consolidation records belong to `KURO0001`. If multi-tenant data exists in `kuropurchase`, this must be verified before enrichment.
- **eShop dedup is intentional** — The 2,469 "skipped" users are NOT a bug. They are legitimate dedup. The fix is linkage, not duplicate creation.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `/tmp/data_audit/enrichment_script.js` | MongoDB script to add tenant fields |
| Create | `/tmp/data_audit/remigration_script.js` | MongoDB script to re-migrate enriched records |
| Modify | `/tmp/consolidate_finance.py` | Add KGCN credit notes + paymentvouchers |
| Create | `/tmp/data_audit/expense_migration.py` | Migrate expense records from purchaseorders |
| Create | `/tmp/data_audit/po_separation.py` | Separate POs from expenses, migrate clean POs |
| Create | `/tmp/data_audit/eshop_dedup_fix.py` | Link skipped eShop users to existing identities |
| Create | `/tmp/data_audit/indent_migration.py` | Migrate indentpos/indentproduct to PG |
| Create | `plat/management/commands/migrate_indents.py` | Django command for indent migration |
| Modify | `plat/management/commands/migrate_legacy_eshop.py` | Fix eShop dedup logic |

---

## Success Criteria

- [ ] All 4,673+ pre-consolidation records enriched and re-migrated (Phase 1)
- [ ] `financial_documents` has 150 `outward_credit_note` and 3,459 `payment_voucher` (Phase 2)
- [ ] Dropped collections (`outwardpayments`, `settlements`, `bulkpayments`) assessed and resolved (Phase 2)
- [ ] `inv_purchase_orders` has ~9,990 clean POs, no expense records (Phase 3)
- [ ] All 3,378 eShop users linked to canonical identities (Phase 4)
- [ ] All eShop orders, carts, wishlists migrated (Phase 4)
- [ ] `inventory_indent` and `inventory_indentitem` populated (Phase 5)
- [ ] No FK violations in PostgreSQL (Phase 6)
- [ ] `python manage.py check` and `migrate --check` pass (Phase 6)
- [ ] All ViewSets return correct data from correct sources (Phase 6)

---

## Caveats & Uncertainty

1. **Single-tenant assumption for kuropurchase:** Phase 1 assumes ALL pre-consolidation records belong to `KURO0001`. If `kuropurchase` contains multi-tenant data, the enrichment must be more nuanced. **Verify before executing.**

2. **Second source database identity:** `KungOS_Mongo_One` has records not in `kuropurchase` (16 `inwardinvoices`, thousands of `inwardpayments`, `paymentvouchers`, `outwardcreditnotes`). The source of these records is unknown. **Identify before re-migrating to avoid overwriting.**

3. **Dropped collections recovery:** `outwardpayments`, `settlements`, `bulkpayments` were dropped during consolidation. They don't exist in `kuropurchase`. Recovery depends on `latest-mongo-backup.dump` having these collections. **Check backup before Phase 2.**

4. **`purchaseorders` unclassified records (1,541):** These have no `type` AND no `po_no`. They could be drafts, cancelled records, or data entry errors. **Inspect before deciding to migrate or discard.**

5. **eShop order items:** The legacy `orders_orderitems` table (1,350 rows) is not clearly mapped to the target schema. The migration script embeds items as JSON in `orders_core.products`. **Verify this is the intended design.**

6. **`custom_catalog` (2,672 docs):** This collection has no PG table and no Django model. It contains gaming center pricing presets. **Determine if this should be migrated to PG or remain in MongoDB.**

7. **`outward` collection (754 in KungOS, 781 in kuropurchase):** Not mentioned in any migration plan. Contains 27 missing records (no bg_code). **Determine purpose before migrating.**

---

## Language Consistency

- **`kuropurchase`** — Original legacy MongoDB source (not "legacy DB")
- **`KungOS_Mongo_One`** — Current canonical MongoDB (not "main DB")
- **`kg_eshop_latest`** — Legacy eShop PostgreSQL (not "old eShop")
- **`kuro-cadence`** — Current PostgreSQL target (not "new DB")
- **`financial_documents`** — Consolidated finance collection in MongoDB (not "consolidated")
- **`pre-consolidation records`** — Records missing `bg_code`/`branch_code`/`div_code` (not "old records")
- **`tenant field enrichment`** — Adding default `bg_code`/`branch_code`/`div_code` to pre-consolidation records
- **`phone dedup`** — eShop users whose phones match existing identities (not "duplicate users")
