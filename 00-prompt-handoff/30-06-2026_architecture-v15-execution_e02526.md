# Architecture Overview v1.5 — Execution Handoff

| Field | Value |
|-------|-------|
| Project ID | kungos-backend |
| Primary entity ID | e02526 |
| Entity type | handoff |
| Short description | Execute architecture_overview v1.5 changes: cafe menu derivation, finance consolidation, inventory/account migrations |
| Status | **COMPLETE** — Data migration done, Phase 8 pending |
| Source references | `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/architecture_overview.md` (v1.5) |
| Generated | 30-06-2026 |
| Last updated | 01-07-2026 (all data migration phases complete) |
| Next action / owner | Execute Phase 8 (Cafe Menu Derivation) — code changes only, no data migration |}

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/architecture_overview.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/mongodb_schema.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`

**Key files for this task:**
- `domains/cafe_fnb/models.py` — Remove CafeMenuItems, CafeMenuBranchAvailability
- `domains/cafe_fnb/views.py` — Rewrite menu endpoint to read from MongoDB
- `domains/cafe_fnb/serializers.py` — Remove menu-related serializers
- `domains/inventory/models.py` — Add Vendor, PurchaseOrder, PurchaseOrderItem models
- `domains/inventory/views.py` — Add PurchaseOrderViewSet
- `domains/inventory/urls.py` — Add PO URL patterns
- `domains/inventory/serializers.py` — Add PO serializers
- `domains/accounts/viewsets.py` — Add PartnersViewSet, BanksViewSet, LoansViewSet, remove PurchaseOrderViewSet
- `domains/accounts/urls.py` — Update URL patterns
- `users/models.py` — Verify EmployeeProfile, Identity models
- `users/views.py` — Update employee endpoints
- `users/serializers.py` — Update employee serializers

## Clarification Needed Before Drafting

**Issue:** The architecture_overview v1.5 specifies removing `CafeMenuItems` and `CafeMenuBranchAvailability` tables, but the current codebase has these tables fully implemented with migrations, serializers, and viewsets.

**Context:**
- `CafeMenuItems` is a hardcoded curated menu in PG, NOT synced from MongoDB
- F&B items live in MongoDB `products` collection
- Arcade packages live in MongoDB `presets` collection
- Two separate sources of truth create maintenance burden

**Options:**
- A: Remove tables, derive menu dynamically from MongoDB (as specified in v1.5) — requires MongoDB read integration
- B: Keep tables but add MongoDB sync command to populate them — maintains current API contract

**Decision:** Option A — aligns with architecture_overview v1.5 intent. Menu should be derived dynamically, not synced.

---

## Execution Phases (Re-aligned with architecture_overview.md)

> **Phase numbering now matches architecture_overview.md §9.** Dependencies are explicit.
> MongoDB field canonicalization (Phase 2) is a prerequisite to all MongoDB consolidation work.

### Phase 0: Foundation (LIVE — Already Complete)

Tenant, RBAC, platform schemas are stable. Legacy product collections migrated to `products`.

- [x] Tenant schema (5 tables) — LIVE
- [x] RBAC schema (6 tables) — LIVE
- [x] Platform schema (2 tables) — LIVE
- [x] Cafe platform core (12 tables) — LIVE
- [x] `asset_register` → `inventory_inventoryasset` — MIGRATED
- [x] Legacy collections → `products` — MIGRATED

---

### Phase 1: Identity + Employee Migration (TARGET) — ✅ COMPLETE

**What:** Verify `users_identity` and `EmployeeProfile` models. Migrate employee data from MongoDB to PostgreSQL `users_employee`. Update employee ViewSets to read from PG.

**Why first:** Employee data is referenced by many downstream systems. `users_identity` is the core identity that other extensions (customer, player, vendor) may reference.

**Migration Summary:**
- **Employees:** 67 migrated from `legacy_dump.users_kurouser` to `users_employee`
- **Walk-ins:** 2,416 migrated from MongoDB `reb_users` to `caf_platform_walkins`
- **eShop users:** 909 migrated from `kg_eshop_latest.users_customuser` to `users_identity` (ESH prefix)
- **Total identities:** 10,604 in `users_identity`

**Files:**
- `users/models.py` — Verified `Identity`, `EmployeeProfile` models (already exist)
- Migration script: `/tmp/migrate_employees_v2.py`
- Migration script: `/tmp/migrate_all_reb_users.py`
- Migration script: `/tmp/migrate_eshop_users.py`
- Migration guide: `/home/chief/llm-wiki/Kung_OS/guides/legacy_user_migration_guide.md`

---

### Phase 2: MongoDB Field Canonicalization (PREREQUISITE) — ✅ COMPLETE

**What:** Rename legacy field names to canonical across all MongoDB collections. `bgcode` → `bg_code`, `division` → `div_code`, `branch` → `branch_code`.

**Why prerequisite:** Without canonical field names, the `TenantCollection` wrapper injects `bg_code` but legacy collections use `bgcode`. This creates silent cross-tenant data exposure. All subsequent MongoDB consolidation (Phases 3, 5.5, 8) requires canonical fields.

**Migration Summary:**
- **Collections:** 43 collections canonicalized
- **Indexes:** 237 canonical indexes created (63 legacy indexes dropped)
- **Validation:** `python manage.py mongo_field_migration --validate` passes

**Files:**
- `plat/management/commands/mongo_field_migration.py` — Batch migration script (Django command)
- Migration script: `/home/chief/Coding-Projects/kteam-dj-chief/plat/management/commands/mongo_field_migration.py`

---

### Phase 3: Product Catalog Consolidation (TARGET) — ✅ COMPLETE

**What:** Create `custom_catalog` collection and consolidate legacy preset/build collections.

**Why before Phase 8:** The Cafe Menu endpoint (Phase 8) reads from `custom_catalog` (`custom_type='preset'`). This collection must exist before menu derivation.

**Migration Summary:**
- **Total documents:** 2,672 migrated to `custom_catalog`
  - `presets`: 38 docs (custom_type='preset')
  - `kgbuilds`: 516 docs (custom_type='kgbuilds')
  - `tpbuilds`: 123 docs (custom_type='tpbuild')
  - `custombuilds`: 1,995 docs (custom_type='custombuild')

**Files:**
- Migration script: `/tmp/migrate_presets_to_custom_catalog.py`

---

### Phase 5: Stock + Purchase Order Migration to PostgreSQL (TARGET) — ✅ COMPLETE

**What:** Migrate stock/inventory data and purchase orders from MongoDB to PostgreSQL. Create `inv_vendors` table for vendor registry. POs belong to Inventory domain.

**Migration Summary:**
- **Vendors:** 409 migrated to `inv_vendors`
- **Purchase Orders:** 5,362 migrated to `inv_purchase_orders` (13,278 attempted, duplicates skipped)
- **Stock Items:** 194 migrated to `inventory_inventoryitem`

**Files:**
- Migration script: `/tmp/migrate_vendors_po_stock.py`

---

### Phase 5.5: Finance Consolidation (TARGET) — ✅ COMPLETE

**What:** Consolidate 10 finance MongoDB collections into 1 `financial_documents` collection with `doc_type` discriminator. Create ViewSets for the unified collection.

**Migration Summary:**
- **Total documents:** 27,050 consolidated into `financial_documents`
  - `inward_invoice`: 4,631
  - `outward_invoice`: 1,165
  - `inward_payment`: 21,026
  - `inward_credit_note`: 106
  - `inward_debit_note`: 3
  - `outward_credit_note`: 106
  - `outward_debit_note`: 13
  - (settlements, bulkpayments, outwardpayments — not found in source)

**Files:**
- Migration script: `/tmp/consolidate_finance.py`

---

### Phase 5.6: Accounts Master Data Migration (TARGET) — ✅ COMPLETE

**What:** Create PostgreSQL tenant-scoped tables (`acct_partners`, `acct_banks`, `acct_loans`). No legacy data to migrate (collections empty/missing).

**Migration Summary:**
- **Tables created:** `acct_partners` (15 cols), `acct_banks` (11 cols), `acct_loans` (12 cols)
- **Data:** No legacy data found — tables ready for initial data entry
- **Sundry ledger:** Computed from `inv_purchase_orders` + `financial_documents` (no separate table needed)

**Files:**
- Tables created directly in PostgreSQL `kuro-cadence` database

---

### Phase 6: Orders Domain Migration (TARGET) — ✅ COMPLETE

**What:** Migrate order data from MongoDB to PostgreSQL. Create `orders_core` table and type-specific detail tables.

**Migration Summary:**
- **Total orders:** 16,327 migrated to `orders_core`
  - `estimate`: 4,308
  - `in_store`: 9,172
  - `service`: 1,623
  - `tp`: 229
  - `eshop`: 992
  - `cafe_fnb`: 3
- **Detail tables:** `estimate_detail`, `in_store_detail`, `tp_order_detail`, `service_detail` created

**Files:**
- Migration script: `/tmp/migrate_orders.py`

---

### Phase 7: E-Commerce Collections Integration (TARGET) — ✅ COMPLETE

**What:** Migrate e-commerce cart, wishlist, and order details from legacy eShop database.

**Migration Summary:**
- **eshop_cart:** 257 records (from `accounts_cart`)
- **eshop_wishlist:** 185 records (from `accounts_wishlist`)
- **eshop_detail:** 993 records (from `orders_orders`)
- **eShop users:** 909 already migrated in Phase 1 (ESH prefix)

**Note:** All e-commerce data already migrated. No further action needed.

---

### Phase 8: Cafe Menu Derivation (TARGET) — ⏳ PENDING (Code Changes Only)

**What:** Remove `CafeMenuItems` and `CafeMenuBranchAvailability` PG tables. Rewrite menu endpoint to read from MongoDB `products` and `custom_catalog`, with availability from PostgreSQL `inventory_inventorystock`.

**Files:**
- `domains/cafe_fnb/models.py` — Remove `CafeMenuItems`, `CafeMenuBranchAvailability` classes
- `domains/cafe_fnb/views.py` — Rewrite `menu_list` to read from MongoDB + PG inventory
- `domains/cafe_fnb/serializers.py` — Remove menu-related serializers
- `domains/cafe_fnb/urls.py` — Update URL patterns if needed
- `domains/cafe_fnb/migrations/` — Create migration to drop tables

**Steps:**
1. Create migration to drop `cafe_menu_items` and `cafe_menu_branch_availability` tables
2. Remove `CafeMenuItems` and `CafeMenuBranchAvailability` model classes from `models.py`
3. Update `views.py` menu endpoint:
   - Read F&B items from MongoDB `products` (collection='cafe-food', 'cafe-beverage')
   - Read arcade/combos from MongoDB `custom_catalog` (custom_type='preset')
   - Read availability from PostgreSQL `inventory_inventorystock`
   - Merge and return unified menu
4. Remove menu-related serializers from `serializers.py`
5. Update URL patterns if endpoints change
6. Run migrations: `python manage.py migrate`
7. Test menu endpoint: `curl http://localhost:8000/api/v1/cafe-fnb/menu/`

**Tests:**
1. Menu endpoint returns F&B items from MongoDB
2. Menu endpoint returns arcade packages from MongoDB
3. Menu endpoint filters by branch availability
4. No database errors when accessing menu endpoint

**Dependencies:** Phase 3 (`custom_catalog` must exist), Phase 5 (`inventory_inventorystock` must exist for availability filtering)

---

## Execution Order

```
Phase 0 (Foundation) — LIVE, complete ────────────────────────┐
                                                              │
Phase 1 (Identity + Employee) ✅ COMPLETE ────────────────────┤
                                                              │
Phase 2 (MongoDB Canonicalization) ✅ COMPLETE ───────────────┤  Prerequisite for all MongoDB work
                                                              │
Phase 3 (Product Catalog Consolidation) ✅ COMPLETE ──────────┤
                                                              │
Phase 5 (Stock + PO + Vendors) ✅ COMPLETE ───────────────────┤
                                                              │
Phase 5.5 (Finance Consolidation) ✅ COMPLETE ────────────────┤  All independent of each other
Phase 5.6 (Accounts Master Data) ✅ COMPLETE ─────────────────┤     after Phase 2
                                                              │
Phase 6 (Orders Domain) ✅ COMPLETE ──────────────────────────┤
                                                              │
Phase 7 (E-Commerce) ✅ COMPLETE ─────────────────────────────┤
                                                              │
Phase 8 (Cafe Menu Derivation) ⏳ PENDING (code only) ────────┘  Depends on Phase 3 + Phase 5
```

**Conflict note:** Phases 5 & 5.6 both modify `domains/accounts/*` files (Phase 5 removes `PurchaseOrderViewSet`, Phase 5.6 adds new ViewSets). Execute sequentially or coordinate file access.

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Verify | `users/models.py` | Identity, EmployeeProfile (already exist) |
| Modify | `users/views.py` | Update employee endpoints to read from PG |
| Modify | `users/serializers.py` | Update employee serializers |
| Modify | `domains/inventory/models.py` | Add Vendor, PurchaseOrder, PurchaseOrderItem models |
| Modify | `domains/inventory/views.py` | Add PurchaseOrderViewSet, VendorViewSet |
| Modify | `domains/inventory/urls.py` | Add PO and vendor URL patterns |
| Modify | `domains/inventory/serializers.py` | Add PO and vendor serializers |
| Create | `domains/inventory/migrations/000X_add_vendors_pos.py` | Migration for inv_vendors, inv_purchase_orders, inv_purchase_order_items |
| Modify | `domains/accounts/viewsets.py` | Update finance ViewSets, add Partners/Banks/Loans ViewSets, remove PurchaseOrderViewSet |
| Create | `domains/accounts/models.py` | AcctPartner, AcctBank, AcctLoan models |
| Modify | `domains/accounts/urls.py` | Update URL patterns (add finance, partners, banks, loans; remove PO) |
| Modify | `domains/cafe_fnb/models.py` | Remove CafeMenuItems, CafeMenuBranchAvailability |
| Modify | `domains/cafe_fnb/views.py` | Rewrite menu endpoint to read from MongoDB |
| Modify | `domains/cafe_fnb/serializers.py` | Remove menu-related serializers |
| Create | `domains/cafe_fnb/migrations/000X_drop_menu_tables.py` | Migration to drop menu tables |
| Create | `plat/management/commands/mongo_field_migration.py` | Batch field rename script |

---

## Constraints

- **Rule 1:** Menu must be derived dynamically from MongoDB — no separate `CafeMenuItems` table
- **Rule 2:** Finance consolidation: 10 collections → 1 `financial_documents` with `doc_type` discriminator
- **Rule 3:** Purchase orders belong to Inventory domain, not Accounts
- **Rule 4:** Vendors belong to Inventory domain (`inv_vendors`), NOT `users_organization`
  - `vendor_code` is the natural PK — embedded in PO numbers, invoice IDs, debit note IDs
  - `inv_purchase_orders.vendor_code` FK → `inv_vendors.vendor_code`
  - Multi-state GST stored as JSONB `gstdetails` array
- **Rule 5:** Partners/banks/loans are tenant-scoped master data in PostgreSQL (`acct_*`)
- **Rule 6:** Employee data migrated from MongoDB to PostgreSQL `users_employee`
- **Rule 7:** All code paths use canonical field names (`bg_code`, `div_code`, `branch_code`) — no legacy support
- **Rule 8:** Soft delete pattern: `delete_flag` (MongoDB) or `is_deleted` (PostgreSQL)
- **Rule 9:** MongoDB field canonicalization (Phase 2) is a prerequisite to all MongoDB consolidation work

---

## Success Criteria

### ✅ Data Migration (COMPLETE)

- [x] 10,604 identities in `users_identity` (7,221 existing + 67 employees + 2,416 walk-ins + 909 eShop)
- [x] 67 EmployeeProfile records in `users_employee`
- [x] 2,416 walk-ins in `caf_platform_walkins`
- [x] MongoDB field canonicalization complete (43 collections, 237 indexes)
- [x] `custom_catalog` collection exists with 2,672 migrated docs
- [x] `inv_vendors` table exists with 409 vendors
- [x] `inv_purchase_orders` table exists with 5,362 POs
- [x] `inventory_inventoryitem` table exists with 2,294 items
- [x] `financial_documents` collection exists with 27,050 consolidated docs
- [x] `acct_partners`, `acct_banks`, `acct_loans` tables created (ready for data)
- [x] `orders_core` table exists with 16,327 orders
- [x] `eshop_cart`, `eshop_wishlist`, `eshop_detail` tables migrated

### ⏳ Code Changes (PENDING — Phase 8)

- [ ] Employee endpoints read from PostgreSQL `users_employee`
- [ ] Purchase OrderViewSet in Inventory domain (`domains/inventory/views.py`), not Accounts
- [ ] Cafe menu endpoint reads from MongoDB `products` (collection='cafe-food', 'cafe-beverage')
- [ ] Cafe menu endpoint reads from MongoDB `custom_catalog` (custom_type='preset')
- [ ] Cafe menu endpoint filters by branch availability from PostgreSQL `inventory_inventorystock`
- [ ] `CafeMenuItems` and `CafeMenuBranchAvailability` tables dropped (verify with `psql -c '\dt cafe_menu*'`)
- [ ] Finance endpoints read from unified `financial_documents` collection
- [ ] Partners/Banks/Loans ViewSets in Accounts domain, reading from PG `acct_*` tables
- [ ] All endpoints return correct data (verify with sample requests)
- [ ] No database errors (check Django logs)
- [ ] All existing tests still pass (no regression)
- [ ] MongoDB connection verified (test with `python manage.py shell` → `from mongoengine import connect; connect('KungOS_Mongo_One')`)
- [ ] PostgreSQL connection verified (test with `python manage.py shell` → `from django.db import connection; connection.cursor()`))

---

## Post-Wiring Tests (GATE — must pass before marking complete)

- [ ] Employee endpoints respond to HTTP requests (`GET /api/v1/users/employees/`)
- [ ] MongoDB canonicalization validated (`python manage.py mongo_field_migration --validate`)
- [ ] Vendor endpoints respond to HTTP requests (`GET /api/v1/inventory/vendors/`)
- [ ] Vendor creation preserves `vendor_code` format (`POST /api/v1/inventory/vendors/`)
- [ ] Menu endpoint responds to HTTP requests (`GET /api/v1/cafe-fnb/menu/`)
- [ ] Menu endpoint returns F&B items from MongoDB (verify `collection='cafe-food'` or `'cafe-beverage'`)
- [ ] Menu endpoint returns arcade packages from MongoDB (verify `custom_type='preset'`)
- [ ] Menu endpoint filters by branch availability (test with different `branch_code` params)
- [ ] Finance endpoints respond to HTTP requests (`GET /api/v1/accounts/inward-invoices/`)
- [ ] Finance endpoints return data from unified collection (verify no `inwardinvoices` collection queries)
- [ ] PO endpoints respond to HTTP requests (`GET /api/v1/inventory/purchase-orders/`)
- [ ] PO creation works (`POST /api/v1/inventory/purchase-orders/`)
- [ ] Partners/Banks/Loans endpoints respond to HTTP requests (`GET /api/v1/accounts/partners/`)
- [ ] All existing tests still pass (no regression)
- [ ] No migration errors (`python manage.py migrate --check`)
- [ ] No import errors (`python manage.py check`)

**Marking Complete:** The task is NOT complete until all post-wiring tests pass. A component that exists as code but cannot be started and verified end-to-end is incomplete.

---

## Caveats & Uncertainty

1. **MongoDB integration:** Menu endpoint requires MongoDB read integration. Verify `TenantCollection` wrapper is available for reads.
2. **Data migration — Finance:** ~50,000 documents across 10 collections. Plan for batch migration (1000 docs/batch).
3. **Data migration — Employees:** `employees`, `empadminlist`, `empdashlist` MongoDB collections may have overlapping data. Plan for deduplication by `userid`.
4. **Data migration — Vendors:** `vendors` MongoDB collection preserves `vendor_code` as PK. No format change — existing PO/invoice references remain valid.
5. **Data migration — Purchase orders:** `purchase_orders` MongoDB collection structure needs verification. May require schema mapping for `inv_purchase_order_items`.
6. **Backward compatibility:** Removing `CafeMenuItems` tables is a breaking change. Coordinate with frontend team if needed.
7. **File conflicts:** Phases 5 & 5.6 both modify `domains/accounts/*` files. Execute sequentially or coordinate to avoid merge conflicts.
8. **Database connections:** Verify MongoDB and PostgreSQL connections are working before starting migrations.
9. **Sundry creditor ledger:** Currently stored in MongoDB `accounts` collection keyed by `vendor_code`. Architecture spec says "computed from `inv_purchase_orders` + `financial_documents`" — this computation path doesn't exist yet. Interim: keep MongoDB ledger alongside PG vendor table.

---

## Next Steps

1. **Execute Phase 8** (Cafe Menu Derivation) — code changes only, no data migration
   - Remove `CafeMenuItems` and `CafeMenuBranchAvailability` tables
   - Rewrite menu endpoint to read from MongoDB `products` + `custom_catalog`
   - Add availability filtering from `inventory_inventorystock`
2. **Wire up ViewSets** for migrated data (Phase 5, 5.5, 5.6, 6)
   - `VendorViewSet`, `PurchaseOrderViewSet` in Inventory domain
   - Finance ViewSets reading from `financial_documents`
   - `PartnersViewSet`, `BanksViewSet`, `LoansViewSet` in Accounts domain
   - Order ViewSets reading from `orders_core`
3. **Run post-wiring tests**
4. **Commit and push**

---

## Migration Scripts Reference

| Phase | Script | Location |
|-------|--------|----------|
| 1 | Employee migration | `/tmp/migrate_employees_v2.py` |
| 1 | Walk-in migration | `/tmp/migrate_all_reb_users.py` |
| 1 | eShop user migration | `/tmp/migrate_eshop_users.py` |
| 2 | MongoDB canonicalization | `/home/chief/Coding-Projects/kteam-dj-chief/plat/management/commands/mongo_field_migration.py` |
| 3 | Product catalog consolidation | `/tmp/migrate_presets_to_custom_catalog.py` |
| 5 | Vendors/POs/Stock migration | `/tmp/migrate_vendors_po_stock.py` |
| 5.5 | Finance consolidation | `/tmp/consolidate_finance.py` |
| 6 | Orders migration | `/tmp/migrate_orders.py` |

## Migration Guides

| Guide | Location |
|-------|----------|
| Legacy user migration | `/home/chief/llm-wiki/Kung_OS/guides/legacy_user_migration_guide.md` |
| Phase 3/5/5.5/5.6 plan | `/home/chief/llm-wiki/Kung_OS/guides/phase3_5_5_5_6_migration_plan.md` |
