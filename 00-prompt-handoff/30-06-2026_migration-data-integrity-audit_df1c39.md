# Migration Data Integrity Audit & Code Wiring Remediation

| Field | Value |
|-------|-------|
| Project ID | `kungos-backend` |
| Primary entity ID | `df1c39` |
| Entity type | `handoff` |
| Short description | Audit legacy vs. migrated data across all databases, fix data loss gaps, create missing Django models/ViewSets, and wire code to read from migrated data locations |
| Status | `draft` |
| Source references | `llm-wiki/Kung_OS/guides/phase3_5_5_5_6_migration_plan.md`, `llm-wiki/00-prompt-handoff/30-06-2026_architecture-v15-execution_e02526.md` |
| Generated | `30-06-2026` |
| Next action / owner | Execute Phase 1 (Data Integrity Audit) — compare `kuropurchase` / `kg_eshop_latest` legacy sources against `KungOS_Mongo_One` and `kuro-cadence` target databases |

---

## Executive Summary

The architecture v1.5 migration plan claims Phases 3, 5, 5.5, 5.6, 6, and 7 are "COMPLETE" (data migrated). A thorough review of the actual data across three databases (`KungOS_Mongo_One`, `kuropurchase`, `kg_eshop_latest`) and the PostgreSQL target (`kuro-cadence`) reveals:

1. **Data was migrated, but code was NOT updated** — Finance, Orders, and Purchase Order ViewSets still read from legacy MongoDB collections, not the new consolidated tables.
2. **Significant data loss** — 44 `outward_credit_note` documents, 14 vendors, 738 estimates, 2,972 kgorders, 551 reb_users, and 3,459 paymentvouchers are missing from migrated data.
3. **Missing Django infrastructure** — `inv_purchase_orders`, `inv_vendors`, `acct_partners`, `acct_banks`, `acct_loans` tables exist but have no Django models, ViewSets, or URL patterns.
4. **Schema mismatches** — The Django `Vendor` model has 20+ fields but `inv_vendors` table has only 9 columns.
5. **Canonicalization incomplete** — `financial_documents` and `custom_catalog` are missing required `bg_code` indexes.

This handoff defines the remediation work across five phases.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief/`
**Reference docs:**
- `llm-wiki/Kung_OS/guides/phase3_5_5_5_6_migration_plan.md`
- `llm-wiki/00-prompt-handoff/30-06-2026_architecture-v15-execution_e02526.md`
**Key files for this task:**
- `domains/accounts/models.py` — Add Partner, Bank, Loan models
- `domains/accounts/viewsets.py` — Rewrite all finance ViewSets to read `financial_documents`
- `domains/accounts/urls.py` — Add routes for Partners, Banks, Loans
- `domains/inventory/models.py` — Fix Vendor model, add PurchaseOrder model
- `domains/inventory/viewsets.py` — Add VendorViewSet, PurchaseOrderViewSet
- `domains/inventory/urls.py` — Add routes for Vendors, PurchaseOrders
- `domains/orders/viewsets.py` — Rewrite all order ViewSets to read `orders_core`
- `plat/management/commands/mongo_field_migration.py` — Add missing `bg_code` indexes
- `plat/management/commands/migrate_legacy_eshop.py` — Fix eShop migration skip logic

**Legacy data sources:**
- MongoDB `kuropurchase` database — Original legacy data (pre-consolidation)
- MongoDB `KungOS_Mongo_One` database — Current "canonical" MongoDB (post-consolidation, with gaps)
- PostgreSQL `kg_eshop_latest` database — Legacy eShop data (pre-migration)
- PostgreSQL `kuro-cadence` database — Current target (post-migration)

---

## Phase 1: Data Integrity Audit (Evidence Collection)

**What:** Systematically compare every legacy data source against the migrated target to produce a definitive data-loss report. This phase produces evidence, not fixes.

**Dependencies:** None.

**Steps:**

1. **Compare `kuropurchase` → `KungOS_Mongo_One` for all shared collections:**

   | Collection | kuropurchase | KungOS_Mongo_One | Gap | Direction |
   |---|---|---|---|---|
   | `estimates` | 5,052 | 4,308 | **744 missing** | kuropurchase has more |
   | `vendors` | 423 | 409 | **14 missing** | kuropurchase has more |
   | `purchaseorders` | 5,555 | 15,216 | **9,661 extra in KungOS** | KungOS has more (1,824 have null `po_no`) |
   | `kgorders` | 12,134 | 9,162 | **2,972 missing** | kuropurchase has more |
   | `serviceRequest` | 1,627 | 1,625 | **2 missing** | kuropurchase has more |
   | `indentpos` | 283 | 247 | **36 missing** | kuropurchase has more |
   | `reb_users` | 2,533 | 1,982 | **551 missing** | kuropurchase has more |
   | `presets` | 6 | 38 | **32 extra in KungOS** | KungOS has more |
   | `inwardinvoices` | 0 | 4,631 | — | Only in KungOS (different source) |
   | `outwardinvoices` | 0 | 1,165 | — | Only in KungOS (different source) |
   | `inwardpayments` | 3,148 | 21,026 | **17,878 extra in KungOS** | KungOS has more (different source) |
   | `outwardcreditnotes` | 44 | 150 | **106 extra in KungOS** | KungOS has more |
   | `paymentvouchers` | 0 | 3,459 | — | Only in KungOS (not in kuropurchase) |
   | `misc` | 8 | 5,512 | **5,504 extra in KungOS** | KungOS has more (different source) |

   **Action:** For each "missing" gap, produce a list of IDs that exist in legacy but not in target. Save to `/tmp/data_audit/missing_<collection>.json`.

2. **Compare `KungOS_Mongo_One` → `financial_documents` (consolidation audit):**

   | Source Collection | Source Count | financial_documents (by doc_type) | Gap |
   |---|---|---|---|
   | `inwardinvoices` | 4,631 | 4,631 | ✅ |
   | `outwardinvoices` | 1,165 | 1,165 | ✅ |
   | `inwardpayments` | 21,026 | 21,026 | ✅ |
   | `inwardcreditnotes` | 106 | 106 | ✅ |
   | `inwarddebitnotes` | 3 | 3 | ✅ |
   | `outwardcreditnotes` | 150 | **106** | **❌ 44 lost** |
   | `outwarddebitnotes` | 13 | 13 | ✅ |
   | `paymentvouchers` | 3,459 | **0** | **❌ 3,459 NOT migrated** |
   | `outwardpayments` | **DROPPED** | **0** | **❌ Data lost — check backup** |
   | `settlements` | **DROPPED** | **0** | **❌ Data lost — check backup** |
   | `bulkpayments` | **DROPPED** | **0** | **❌ Data lost — check backup** |

   **Action:** For the 44 missing `outward_credit_note` documents, find their `_id` values in `KungOS_Mongo_One.outwardcreditnotes` that are NOT in `financial_documents`. Save to `/tmp/data_audit/missing_outward_credit_notes.json`.

   **Action:** For the three DROPPED collections (`outwardpayments`, `settlements`, `bulkpayments`), check if data exists in `latest-mongo-backup.dump` or `kuropurchase` database. Save findings to `/tmp/data_audit/dropped_collections_recovery.md`.

   **Action:** For the 44 missing `outward_credit_note` documents, find their `_id` values in `KungOS_Mongo_One.outwardcreditnotes` that are NOT in `financial_documents`. Save to `/tmp/data_audit/missing_outward_credit_notes.json`.

3. **Compare `kg_eshop_latest` → `kuro-cadence` (eShop migration audit):**

   | Source Table | Source Count | Target Table | Target Count | Gap |
   |---|---|---|---|---|
   | `users_customuser` | 3,378 | `users_identity` (ESH prefix) | 909 | **2,469 skipped** (likely phone dedup) |
   | `accounts_cart` | 748 | `eshop_cart` | 257 | **491 skipped** |
   | `accounts_wishlist` | 450 | `eshop_wishlist` | 185 | **265 skipped** |
   | `orders_orders` | 1,206 | `eshop_detail` | 993 | **213 skipped** |
   | `orders_orderitems` | 1,350 | (embedded in eshop_detail?) | — | Unknown |
   | `accounts_addresslist` | 1,064 | `users_saved_addresses` | ? | Unknown |

   **Action:** Determine why ~60-73% of eShop data was skipped. Check if migration logic filters by `is_active`, `delete_flag`, or phone dedup. Save analysis to `/tmp/data_audit/eshop_skip_analysis.md`.

4. **Verify `inv_purchase_orders` data quality:**

   - 15,216 POs in MongoDB `purchaseorders`
   - 5,362 POs in `inv_purchase_orders` PG table
   - **9,854 POs NOT migrated** — determine why (null `po_no`? duplicate? status filter?)
   - Save analysis to `/tmp/data_audit/po_migration_gap.md`.

5. **Verify `inventory_inventoryitem` count:**

   - Handoff claims 194 items
   - Actual: 2,294 in `inventory_inventoryitem` and 2,294 in `inventory_items_backup_20260628`
   - `stock_register` (MongoDB source) has 194 — the handoff confused source with target
   - Update documentation to reflect correct count.

6. **Check `indentpos` and `indentproduct` status:**

   - Migration plan mentions `indentpos` → `inventory_indent` (bonus)
   - `inventory_indent` and `inventory_indentitem` tables DO exist (Django `Indent`/`IndentItem` models present at `domains/inventory/models.py:422`) but contain **0 rows** — data was never migrated
   - `indentproduct` (1,649 docs) was not mentioned in any plan
   - Determine if these should be migrated or are deprecated.

**Tests:**
- [ ] All gap reports saved to `/tmp/data_audit/`
- [ ] Each report includes: collection name, source count, target count, gap count, sample missing IDs
- [ ] Summary spreadsheet produced with all gaps

**Output artifacts:**
- `/tmp/data_audit/missing_estimates.json`
- `/tmp/data_audit/missing_vendors.json`
- `/tmp/data_audit/missing_kgorders.json`
- `/tmp/data_audit/missing_reb_users.json`
- `/tmp/data_audit/missing_outward_credit_notes.json`
- `/tmp/data_audit/eshop_skip_analysis.md`
- `/tmp/data_audit/po_migration_gap.md`
- `/tmp/data_audit/indent_status.md`

---

## Phase 2: Data Migration Fixes

**What:** Re-migrate the identified gaps from Phase 1. This phase executes data repairs, not code changes.

**Dependencies:** Phase 1 (must have evidence of what's missing).

**Steps:**

1. **Fix `outward_credit_note` data loss (44 documents):**

   - Re-run the consolidation script for `outwardcreditnotes` with `upsert=True`
   - Verify all 150 documents are now in `financial_documents`
   - **Files:** Modify `/tmp/consolidate_finance.py` or create a new repair script

2. **Fix `paymentvouchers` not migrated (3,459 documents):**

   - Add `paymentvouchers` → `financial_documents` (doc_type=`payment_voucher`) to consolidation
   - Map fields: `po_no`, `vendor`, `amount`, `paid_by`, `pay_method`, `pay_account`, `pay_date`
   - **Files:** Modify `/tmp/consolidate_finance.py` or create repair script

2b. **Recover dropped collections (`outwardpayments`, `settlements`, `bulkpayments`):**

   - Check `latest-mongo-backup.dump` for these collections
   - Check `kuropurchase` database for equivalent collections
   - If recoverable: migrate to `financial_documents` with appropriate doc_types
   - If NOT recoverable: document as permanent data loss, mark ViewSets as deprecated (410 Gone)
   - **Files:** Create recovery script or deprecation notice

3. **Fix `kuropurchase` → `KungOS_Mongo_One` gaps:**

   - Re-migrate 744 missing estimates, 14 missing vendors, 2,972 missing kgorders, 551 missing reb_users, 36 missing indentpos, 2 missing serviceRequest
   - Use `upsert=True` to avoid duplicates
   - **Files:** Create repair script

4. **Fix `inv_purchase_orders` migration gap (9,854 POs not migrated):**

   - Determine if the 9,854 POs are valid (have non-null `po_no`) or junk
   - If valid: re-run migration with corrected filter
   - If junk: document and clean up
   - **Files:** Modify `/tmp/migrate_purchase_orders.py` or create repair script

5. **Fix eShop migration skip rates:**

   - Review migration logic for phone dedup / `is_active` filtering
   - If skips were intentional (dedup), document the dedup logic
   - If skips were bugs, re-run with corrected logic
   - **Files:** Modify `/tmp/migrate_eshop_users.py` or `plat/management/commands/migrate_legacy_eshop.py`

6. **Migrate `indentpos`/`indentproduct` to existing tables:**

   - `inventory_indent` and `inventory_indentitem` tables already exist (Django `Indent`/`IndentItem` models at `domains/inventory/models.py:422`)
   - Map `indentpos` → `inventory_indent` and `indentproduct` → `inventory_indentitem`
   - Migrate 247 indentpos + 1,649 indentproduct records
   - **Files:** Create data migration script (no Django migration needed — tables exist)

**Tests:**
- [ ] `financial_documents` has 150 `outward_credit_note` (was 106)
- [ ] `financial_documents` has 3,459 `payment_voucher` (was 0)
- [ ] Dropped collections (`outwardpayments`, `settlements`, `bulkpayments`) recovered or documented as permanent loss
- [ ] `KungOS_Mongo_One` has 5,052 estimates (was 4,308)
- [ ] `KungOS_Mongo_One` has 423 vendors (was 409)
- [ ] `KungOS_Mongo_One` has 12,134 kgorders (was 9,162)
- [ ] `KungOS_Mongo_One` has 2,533 reb_users (was 1,982)
- [ ] eShop skip rates documented or fixed
- [ ] `inventory_indent` table has data (was 0 rows)
- [ ] Dropped collection ViewSets (`OutwardPaymentViewSet`, `BulkPaymentViewSet`, `SettlementsViewSet`) either restored or deprecated

**Constraints:**
- **Never delete source data** — only add missing records via upsert
- **Preserve original `_id` / primary keys** — maintain lineage
- **Log every repair** — produce an audit trail of what was fixed

---

## Phase 3: Django Model Creation & Schema Alignment

**What:** Create Django models for all PG tables that lack them, and fix schema mismatches.

**Dependencies:** Phase 1 (audit complete). Phase 2 (data fixes) can run in parallel.

### 3A: Fix `inv_vendors` Model Mismatch

**Current state:** Django `Vendor` model has 20+ fields (`pan`, `gstin`, `regaddress`, `shipaddress`, `contact_person`, `payment_type`, `bg_code`, `div_code`, etc.) but `inv_vendors` table has only 9 columns (`vendor_code`, `name`, `phone`, `email`, `address`, `gstdetails`, `created_at`, `updated_at`, `vendor_type`).

**Options:**
- **A:** Alter `inv_vendors` table to add missing columns (expands schema, allows future enrichment)
- **B:** Simplify Django `Vendor` model to match existing 9 columns (minimal risk, matches reality)

**Recommendation:** Option B — match model to existing table. If additional vendor fields are needed later, add them via a separate migration with a clear business requirement.

**Files:** `domains/inventory/models.py`

### 3B: Create `PurchaseOrder` Model

**Current state:** `inv_purchase_orders` table exists (5,362 rows, 11 columns) but no Django model.

**Table columns:** `po_no`, `vendor_code`, `total_amount`, `branch_code`, `bg_code`, `div_code`, `created_by`, `created_date`, `status`, `created_at`, `updated_at`

**Files:** `domains/inventory/models.py`

### 3C: Create `Partner`, `Bank`, `Loan` Models

**Current state:** `acct_partners` (15 cols), `acct_banks` (11 cols), `acct_loans` (12 cols) exist but have no Django models.

**Table schemas:**

```
acct_partners: partner_code, name, partner_type, contact_person, phone, email,
               address, gstin, pan, bg_code, div_code, branch_code, is_active,
               created_at, updated_at

acct_banks: id, bank_code, name, branch, ifsc_code, account_type, account_number,
            partner_id (FK→acct_partners), is_active, created_at, updated_at

acct_loans: id, loan_code, partner_id (FK→acct_partners), loan_type,
            principal_amount, interest_rate, start_date, end_date,
            outstanding_amount, status, created_at, updated_at
```

**Files:** `domains/accounts/models.py`

### 3D: Create `InventoryIndent` Model

**Current state:** `indentpos` and `indentproduct` collections exist in MongoDB but no PG table or Django model.

**Files:** `domains/inventory/models.py` (after Phase 2 creates the table)

**Tests:**
- [ ] `python manage.py check` passes
- [ ] `python manage.py makemigrations --check` detects no uncommitted changes
- [ ] Each model can be queried: `Vendor.objects.count()`, `PurchaseOrder.objects.count()`, etc.

---

## Phase 4: ViewSet & URL Wiring

**What:** Create ViewSets and URL patterns for all new models, and rewrite existing ViewSets to read from migrated data locations.

**Dependencies:** Phase 3 (models created).

### 4A: Finance ViewSets — Rewrite to Read `financial_documents`

**Current state:** All finance ViewSets use `COLLECTION_NAME` pointing to old MongoDB collections:

| ViewSet | COLLECTION_NAME | Collection Status |
|---|---|---|
| `InwardInvoiceViewSet` | `inwardinvoices` | ✅ Exists (4,631 docs) |
| `OutwardInvoiceViewSet` | `outwardinvoices` | ✅ Exists (1,165 docs) |
| `InwardPaymentViewSet` | `inwardpayments` | ✅ Exists (21,026 docs) |
| `OutwardPaymentViewSet` | `outwardpayments` | ❌ **DROPPED** — data lost |
| `InwardCreditNoteViewSet` | `inwardcreditnotes` | ✅ Exists (106 docs) |
| `InwardDebitNoteViewSet` | `inwarddebitnotes` | ✅ Exists (3 docs) |
| `OutwardCreditNoteViewSet` | `outwardcreditnotes` | ✅ Exists (150 docs) |
| `OutwardDebitNoteViewSet` | `outwarddebitnotes` | ✅ Exists (13 docs) |
| `PaymentVoucherViewSet` | `paymentvouchers` | ✅ Exists (3,459 docs) |
| `BulkPaymentViewSet` | `bulk_payments` | ❌ **DROPPED** — data lost |
| `SettlementsViewSet` | `settlements` | ❌ **DROPPED** — data lost |

**Change:** For collections that still exist, replace MongoDB queries with queries against `financial_documents` filtered by `doc_type`. For DROPPED collections (`OutwardPaymentViewSet`, `BulkPaymentViewSet`, `SettlementsViewSet`), either restore from backup or mark endpoints as deprecated (410 Gone).

**Approach:** Use Option B (raw MongoDB queries targeting `financial_documents`) for Phase 4 execution. Create a separate handoff for Option C (migrate `financial_documents` to PostgreSQL) after Phase 5 is complete.

**Files:** `domains/accounts/viewsets.py`

### 4B: Orders ViewSets — Rewrite to Read PG Tables

**Current state:** Order ViewSets read from MongoDB collections:

| ViewSet | COLLECTION_NAME | Target PG Table |
|---|---|---|
| `EstimateViewSet` | `estimates` | `orders_core` (order_type='estimate') + `estimate_detail` |
| `InStoreViewSet` | `kgorders` | `orders_core` (order_type='in_store') + `in_store_detail` |
| `TPOrderViewSet` | `tporders` | `orders_core` (order_type='tp_order') + `tp_order_detail` |
| `ServiceRequestViewSet` | `service_detail` (MongoDB, 0 docs) | `service_detail` (PG, 1,623 rows) |
| `OrdersViewSet` | aggregates `estimates`+`tporders`+`kgorders` | `orders_core` (all types) |

**Change:** Replace MongoDB queries with Django ORM queries. `ServiceRequestViewSet` must read from the PG `service_detail` table (schema: `order_id`, `service_type`, `description`, `scheduled_date`, `completed_date`), NOT from `orders_core`.

**Files:** `domains/orders/viewsets.py`

### 4C: Create New ViewSets

| ViewSet | Model | Router Name |
|---|---|---|
| `VendorViewSet` | `Vendor` | `vendors` |
| `PurchaseOrderViewSet` | `PurchaseOrder` | `purchase-orders` (move from Accounts to Inventory) |
| `PartnerViewSet` | `Partner` | `partners` |
| `BankViewSet` | `Bank` | `banks` |
| `LoanViewSet` | `Loan` | `loans` |

**Files:**
- `domains/inventory/viewsets.py` — Add VendorViewSet, PurchaseOrderViewSet
- `domains/accounts/viewsets.py` — Add PartnerViewSet, BankViewSet, LoanViewSet
- `domains/inventory/urls.py` — Add vendor, purchase-order routes
- `domains/accounts/urls.py` — Add partner, bank, loan routes

### 4D: Purchase Order ViewSet Consolidation

**Current state:** Two `PurchaseOrderViewSet` classes exist:
- `accounts/viewsets.py:436` — registered at `/accounts/purchase-orders`, reads MongoDB `purchaseorders`
- `orders/viewsets.py:682` — registered at `/orders/purchase-orders`, reads MongoDB `purchaseorders`

Both are functionally identical (same collection, same logic).

**Change:** Consolidate to a single `PurchaseOrderViewSet` in `inventory/viewsets.py` reading from `inv_purchase_orders` via Django ORM, registered at `/inventory/purchase-orders`. Deprecate the two existing copies (return 410 Gone with migration notice).

**Files:** `domains/accounts/viewsets.py` (deprecate), `domains/orders/viewsets.py` (deprecate), `domains/inventory/viewsets.py` (add), `domains/accounts/urls.py` (deprecate route), `domains/orders/urls.py` (deprecate route), `domains/inventory/urls.py` (add route)

**Tests:**
- [ ] All finance endpoints return data from `financial_documents`
- [ ] All order endpoints return data from `orders_core`
- [ ] New ViewSets are accessible via their URL routes
- [ ] `python manage.py check` passes
- [ ] No regression in existing endpoints (Inventory, E-Shop, Cafe F&B)

---

## Phase 5: Canonicalization Completion & Production Validation

**What:** Add missing `bg_code` indexes, run full validation, and verify end-to-end.

**Dependencies:** Phases 1–4 complete.

**Steps:**

1. **Add `bg_code` indexes:**

   - `financial_documents`: `db.financial_documents.createIndex({bg_code: 1})`
   - `custom_catalog`: `db.custom_catalog.createIndex({bg_code: 1})`
   - Verify via `mongo_field_migration --validate`

2. **Clean up legacy collections (optional but recommended):**

   - Document which old collections are now deprecated
   - Either drop them or rename with `_deprecated_` prefix
   - Old collections still present: `inwardinvoices`, `outwardinvoices`, `inwardpayments`, `inwardcreditnotes`, `inwarddebitnotes`, `outwardcreditnotes`, `outwarddebitnotes`, `presets`, `kgbuilds`, `tpbuilds`, `custombuilds`

3. **Full system validation:**

   - `python manage.py check` — passes
   - `python manage.py migrate --check` — passes
   - `mongo_field_migration --validate` — passes
   - All ViewSets return correct data from correct sources
   - End-to-end API tests pass

4. **Update documentation:**

   - Correct `inventory_inventoryitem` count (2,294, not 194)
   - Document `paymentvouchers` migration
   - Document eShop skip rates and dedup logic
   - Update handoff completion status

**Post-Wiring Tests (GATE — must pass before marking complete):**

- [ ] `python manage.py check` passes
- [ ] `python manage.py migrate --check` passes
- [ ] `mongo_field_migration --validate` passes (no missing indexes)
- [ ] Finance endpoints read from `financial_documents` (not old collections)
- [ ] Order endpoints read from `orders_core` (not old collections)
- [ ] Purchase Order endpoints read from `inv_purchase_orders` (PG, not MongoDB)
- [ ] Vendor endpoints functional (`/vendors/`)
- [ ] Partner, Bank, Loan endpoints functional
- [ ] Duplicate `PurchaseOrderViewSet` consolidated to single location (`/inventory/purchase-orders`)
- [ ] `ServiceRequestViewSet` reads from PG `service_detail` (not empty MongoDB)
- [ ] Dropped collection ViewSets (`OutwardPaymentViewSet`, `BulkPaymentViewSet`, `SettlementsViewSet`) either restored or return 410 Gone
- [ ] `financial_documents` has 150 `outward_credit_note` (gap fixed)
- [ ] `financial_documents` has 3,459 `payment_voucher` (gap fixed)
- [ ] Dropped collections (`outwardpayments`, `settlements`, `bulkpayments`) recovered or ViewSets deprecated
- [ ] All existing tests still pass (no regression)
- [ ] Server starts and responds to requests on all routes
- [ ] Documentation updated with correct counts and status

**Marking Complete:** This task is NOT complete until all post-wiring tests pass. A component that exists as code but cannot be verified end-to-end is incomplete.

---

## Constraints

- **No data deletion without explicit approval** — Legacy collections are not to be dropped until all gaps are verified and repaired.
- **Preserve lineage** — Every migrated record must retain its original `_id` or primary key for audit traceability.
- **One phase at a time** — Each phase must pass its tests before proceeding to the next.
- **Evidence-first** — Phase 1 must produce complete audit artifacts before Phase 2 executes any repairs.
- **Schema alignment** — Django models must match actual database tables. If they diverge, either alter the table or simplify the model — never leave them inconsistent.
- **Language consistency** — Use precise terms: "KungOS_Mongo_One" (not "main DB"), "kuropurchase" (not "legacy"), "financial_documents" (not "consolidated"), "orders_core" (not "orders table").

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/accounts/models.py` | Add Partner, Bank, Loan models |
| Modify | `domains/accounts/viewsets.py` | Rewrite finance ViewSets, add Partner/Bank/Loan ViewSets, remove PurchaseOrderViewSet |
| Modify | `domains/accounts/urls.py` | Add partner/bank/loan routes, remove purchase-order route |
| Modify | `domains/inventory/models.py` | Fix Vendor model, add PurchaseOrder model, add InventoryIndent model |
| Modify | `domains/inventory/viewsets.py` | Add VendorViewSet, PurchaseOrderViewSet |
| Modify | `domains/inventory/urls.py` | Add vendor/purchase-order routes |
| Modify | `domains/orders/viewsets.py` | Rewrite all order ViewSets to read `orders_core` |
| Modify | `plat/management/commands/mongo_field_migration.py` | Add missing `bg_code` index creation |
| Create | `/tmp/data_audit/` (directory) | Data integrity audit artifacts |
| Create | Repair scripts for data gaps | Re-migrate missing records |
| Modify | `llm-wiki/00-prompt-handoff/30-06-2026_architecture-v15-execution_e02526.md` | Update completion status |
| Modify | `llm-wiki/Kung_OS/guides/phase3_5_5_5_6_migration_plan.md` | Correct counts, add paymentvouchers |

---

## Success Criteria

- [ ] All data gaps identified in Phase 1 are repaired (Phase 2)
- [ ] All PG tables have corresponding Django models (Phase 3)
- [ ] All ViewSets read from migrated data locations (Phase 4)
- [ ] All URL routes are functional and return correct data (Phase 4)
- [ ] `mongo_field_migration --validate` passes (Phase 5)
- [ ] `python manage.py check` and `migrate --check` pass (Phase 5)
- [ ] No regression in existing functionality (Phase 5)
- [ ] Documentation reflects actual state, not aspirational claims (Phase 5)
- [ ] Full end-to-end API verification passes (Phase 5)

---

## Caveats & Uncertainty

1. **Source of `KungOS_Mongo_One` data:** It's unclear whether `KungOS_Mongo_One` was merged from multiple sources (kuropurchase + another database). The `inwardinvoices`, `outwardinvoices`, `inwardpayments`, `paymentvouchers`, `misc` collections exist in KungOS but NOT in kuropurchase. This suggests a second source database was merged. **The executing agent must identify this source before re-migrating.**

2. **eShop skip rates:** The migration skipped ~60-73% of legacy eShop data. This may be intentional (phone dedup against existing walk-ins/employees) or a bug. **The executing agent must determine the skip logic before re-running.**

3. **Purchase order quality:** 1,824 of 15,216 POs in `KungOS_Mongo_One` have null/empty `po_no`. These may be junk records. **The executing agent must assess data quality before migrating.**

4. **`indentpos`/`indentproduct` purpose:** These collections contain procurement indent data. It's unclear if they're still in active use or deprecated. **The executing agent should verify with the business before investing in migration.**

5. **`financial_documents` as MongoDB vs PG:** The consolidation script put `financial_documents` in MongoDB, but the long-term architecture seems to prefer PostgreSQL. **The executing agent should confirm whether Option B (keep MongoDB) or Option C (migrate to PG) is the intended direction.**

6. **Dropped collections (`outwardpayments`, `settlements`, `bulkpayments`):** These three MongoDB collections were dropped during consolidation WITHOUT being migrated to `financial_documents`. The ViewSets that read them (`OutwardPaymentViewSet`, `SettlementsViewSet`, `BulkPaymentViewSet`) are silently broken. **The executing agent must check `latest-mongo-backup.dump` and `kuropurchase` database for recoverable data before deciding whether to restore or deprecate.**

7. **Duplicate `PurchaseOrderViewSet`:** Two identical ViewSets exist at `/accounts/purchase-orders` and `/orders/purchase-orders`. **The executing agent must consolidate to a single location and deprecate the duplicate.**
