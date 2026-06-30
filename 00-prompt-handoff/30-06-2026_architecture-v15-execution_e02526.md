# Architecture Overview v1.5 — Execution Handoff

| Field | Value |
|-------|-------|
| Project ID | kungos-backend |
| Primary entity ID | e02526 |
| Entity type | handoff |
| Short description | Execute architecture_overview v1.5 changes: cafe menu derivation, finance consolidation, inventory/account migrations |
| Status | draft |
| Source references | `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/architecture_overview.md` (v1.5) |
| Generated | 30-06-2026 |
| Next action / owner | Execute Phase 1 (Cafe Menu) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:**
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/architecture_overview.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/mongodb_schema.md`
- `/home/chief/llm-wiki/Kung_OS/specs/database_schemas/postgresql_schema.md`

**Key files for this task:**
- `domains/cafe_fnb/models.py` — Remove CafeMenuItems, CafeMenuBranchAvailability
- `domains/cafe_fnb/views.py` — Rewrite menu endpoint to read from MongoDB
- `domains/inventory/models.py` — Add purchase order models
- `domains/accounts/viewsets.py` — Add PartnersViewSet, BanksViewSet, LoansViewSet
- `users/models.py` — Verify EmployeeProfile, Identity models

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

**Recommendation:** Option A — aligns with architecture_overview v1.5 intent. Menu should be derived dynamically, not synced.

**Blocking:** Yes — need confirmation on Option A before proceeding.

---

## Execution Phases

### Phase 1: Cafe Menu Derivation (TARGET)

**What:** Remove `CafeMenuItems` and `CafeMenuBranchAvailability` PG tables. Rewrite menu endpoint to read from MongoDB `products` (collection='cafe-food', 'cafe-beverage') and `custom_catalog` (custom_type='preset'), with availability from PostgreSQL `inventory_inventorystock`.

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

**Dependencies:** None (Phase 1 is independent)

---

### Phase 2: Finance Consolidation (TARGET)

**What:** Consolidate 9 finance MongoDB collections into 1 `financial_documents` collection with `doc_type` discriminator. Create ViewSets for the unified collection.

**Files:**
- `domains/accounts/services.py` — Add finance document service
- `domains/accounts/viewsets.py` — Add consolidated ViewSets
- `domains/accounts/urls.py` — Update URL patterns
- MongoDB — Migrate data from 9 collections to 1

**Steps:**
1. Create `financial_documents` MongoDB collection
2. Migrate data from 9 collections:
   - `inwardinvoices` → `financial_documents` (`doc_type='inward_invoice'`)
   - `outwardinvoices` → `financial_documents` (`doc_type='outward_invoice'`)
   - `inwardpayments` → `financial_documents` (`doc_type='inward_payment'`)
   - `outwardpayments` → `financial_documents` (`doc_type='outward_payment'`)
   - `inwardcreditnotes` → `financial_documents` (`doc_type='inward_credit_note'`)
   - `inwarddebitnotes` → `financial_documents` (`doc_type='inward_debit_note'`)
   - `outwardcreditnotes` → `financial_documents` (`doc_type='outward_credit_note'`)
   - `outwarddebitnotes` → `financial_documents` (`doc_type='outward_debit_note'`)
   - `settlements` → `financial_documents` (`doc_type='settlement'`)
   - `bulkpayments` → `financial_documents` (`doc_type='bulk_payment'`)
3. Create `FinancialDocument` service class with discriminator filtering
4. Create consolidated ViewSets (or keep existing ViewSets but route to unified collection)
5. Update URL patterns
6. Add indexes on `financial_documents` (`doc_type`, `bg_code`, `div_code`)
7. Test finance endpoints

**Tests:**
1. Finance endpoints return data from unified collection
2. Discriminator filtering works correctly
3. All 9 document types accessible

**Dependencies:** None (Phase 2 is independent)

---

### Phase 3: Purchase Orders to Inventory Domain (TARGET)

**What:** Move PurchaseOrderViewSet from Accounts to Inventory domain. Create `inv_purchase_orders` and `inv_purchase_order_items` PG tables. Migrate data from MongoDB `purchase_orders`.

**Files:**
- `domains/inventory/models.py` — Add `PurchaseOrder`, `PurchaseOrderItem` models
- `domains/inventory/views.py` — Add `PurchaseOrderViewSet`
- `domains/inventory/urls.py` — Add PO URL patterns
- `domains/inventory/serializers.py` — Add PO serializers
- `domains/accounts/viewsets.py` — Remove `PurchaseOrderViewSet`
- `domains/accounts/urls.py` — Remove PO URL patterns
- PostgreSQL — Create `inv_purchase_orders`, `inv_purchase_order_items` tables
- MongoDB — Migrate `purchase_orders` data

**Steps:**
1. Create `PurchaseOrder` and `PurchaseOrderItem` models in `inventory/models.py`
2. Create migrations for new PG tables
3. Run migrations: `python manage.py migrate`
4. Create `PurchaseOrderViewSet` in `inventory/views.py`
5. Add URL patterns in `inventory/urls.py`
6. Create serializers in `inventory/serializers.py`
7. Remove `PurchaseOrderViewSet` from `accounts/viewsets.py`
8. Remove PO URL patterns from `accounts/urls.py`
9. Migrate data from MongoDB `purchase_orders` to PG tables
10. Test PO endpoints

**Tests:**
1. PO endpoints accessible from Inventory domain
2. PO creation works
3. PO listing filters by tenant
4. PO items reference inventory items correctly

**Dependencies:** Phase 1 (cafe menu) should be complete, but Phase 3 is otherwise independent

---

### Phase 4: Accounts Master Data Migration (TARGET)

**What:** Migrate partners, banks, loans from MongoDB to PostgreSQL tenant-scoped tables (`acct_partners`, `acct_banks`, `acct_loans`). Create ViewSets for these tables.

**Files:**
- `domains/accounts/models.py` — Add `AcctPartner`, `AcctBank`, `AcctLoan` models
- `domains/accounts/viewsets.py` — Add `PartnersViewSet`, `BanksViewSet`, `LoansViewSet`
- `domains/accounts/urls.py` — Add URL patterns
- PostgreSQL — Create `acct_partners`, `acct_banks`, `acct_loans` tables
- MongoDB — Migrate data

**Steps:**
1. Create `AcctPartner`, `AcctBank`, `AcctLoan` models in `accounts/models.py`
2. Create migrations for new PG tables
3. Run migrations: `python manage.py migrate`
4. Create `PartnersViewSet`, `BanksViewSet`, `LoansViewSet` in `accounts/viewsets.py`
5. Add URL patterns in `accounts/urls.py`
6. Migrate data from MongoDB `partners`, `banks`, `loans` to PG tables
7. Test endpoints

**Tests:**
1. Partners/Banks/Loans endpoints accessible
2. Data migrated correctly
3. Tenant scoping works (users see only their BG data)

**Dependencies:** None (Phase 4 is independent)

---

### Phase 5: Employee Migration to PG (TARGET)

**What:** Migrate employee collections from MongoDB to PostgreSQL `users_employee` table. Update ViewSets to read from PG.

**Files:**
- `users/models.py` — Verify `EmployeeProfile` model
- `users/views.py` — Update employee endpoints to read from PG
- PostgreSQL — Create `users_employee` table (verify exists)
- MongoDB — Migrate `employees`, `empadminlist`, `empdashlist` data

**Steps:**
1. Verify `EmployeeProfile` model exists in `users/models.py`
2. Verify `users_employee` table exists in PostgreSQL
3. Migrate data from MongoDB `employees`, `empadminlist`, `empdashlist` to PG
4. Update employee ViewSets to read from PG `users_employee`
5. Test employee endpoints

**Tests:**
1. Employee endpoints return data from PG
2. Employee filtering by role works
3. Employee filtering by is_active works

**Dependencies:** Phase 1 (cafe menu) should be complete, but Phase 5 is otherwise independent

---

## Execution Order

```
Phase 1 (Cafe Menu) ──────────────────────────────────┐
                                                       │
Phase 2 (Finance Consolidation) ──────────────────────┤
                                                       ├── All phases independent
Phase 3 (Purchase Orders) ────────────────────────────┤
                                                       │
Phase 4 (Accounts Master Data) ───────────────────────┤
                                                       │
Phase 5 (Employee Migration) ─────────────────────────┘
```

**Note:** All phases are independent and can be executed in parallel by separate agents.

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `domains/cafe_fnb/models.py` | Remove CafeMenuItems, CafeMenuBranchAvailability |
| Modify | `domains/cafe_fnb/views.py` | Rewrite menu endpoint to read from MongoDB |
| Modify | `domains/cafe_fnb/serializers.py` | Remove menu-related serializers |
| Create | `domains/cafe_fnb/migrations/000X_drop_menu_tables.py` | Migration to drop menu tables |
| Modify | `domains/accounts/services.py` | Add finance document service |
| Modify | `domains/accounts/viewsets.py` | Add consolidated ViewSets, remove PurchaseOrderViewSet |
| Modify | `domains/accounts/urls.py` | Update URL patterns |
| Modify | `domains/inventory/models.py` | Add PurchaseOrder, PurchaseOrderItem models |
| Modify | `domains/inventory/views.py` | Add PurchaseOrderViewSet |
| Modify | `domains/inventory/urls.py` | Add PO URL patterns |
| Modify | `domains/inventory/serializers.py` | Add PO serializers |
| Modify | `users/models.py` | Verify EmployeeProfile model |
| Modify | `users/views.py` | Update employee endpoints |

---

## Constraints

- **Rule 1:** Menu must be derived dynamically from MongoDB — no separate `CafeMenuItems` table
- **Rule 2:** Finance consolidation: 9 collections → 1 `financial_documents` with `doc_type` discriminator
- **Rule 3:** Purchase orders belong to Inventory domain, not Accounts
- **Rule 4:** Partners/banks/loans are tenant-scoped master data in PostgreSQL
- **Rule 5:** Employee data migrated from MongoDB to PostgreSQL `users_employee`
- **Rule 6:** All code paths use canonical field names (`bg_code`, `div_code`, `branch_code`) — no legacy support
- **Rule 7:** Soft delete pattern: `delete_flag` (MongoDB) or `is_deleted` (PostgreSQL)

---

## Success Criteria

- [ ] Cafe menu endpoint reads from MongoDB `products` (collection='cafe-food', 'cafe-beverage')
- [ ] Cafe menu endpoint reads from MongoDB `custom_catalog` (custom_type='preset')
- [ ] Cafe menu endpoint filters by branch availability from PostgreSQL `inventory_inventorystock`
- [ ] `CafeMenuItems` and `CafeMenuBranchAvailability` tables dropped
- [ ] Finance endpoints read from unified `financial_documents` collection
- [ ] Purchase OrderViewSet in Inventory domain, not Accounts
- [ ] Partners/Banks/Loans ViewSets in Accounts domain, reading from PG
- [ ] Employee endpoints read from PostgreSQL `users_employee`
- [ ] All endpoints return correct data
- [ ] No database errors
- [ ] All existing tests still pass (no regression)

---

## Post-Wiring Tests (GATE — must pass before marking complete)

- [ ] Menu endpoint responds to HTTP requests
- [ ] Menu endpoint returns F&B items from MongoDB
- [ ] Menu endpoint returns arcade packages from MongoDB
- [ ] Menu endpoint filters by branch availability
- [ ] Finance endpoints respond to HTTP requests
- [ ] Finance endpoints return data from unified collection
- [ ] PO endpoints respond to HTTP requests
- [ ] PO creation works
- [ ] Partners/Banks/Loans endpoints respond to HTTP requests
- [ ] Employee endpoints respond to HTTP requests
- [ ] All existing tests still pass (no regression)

**Marking Complete:** The task is NOT complete until all post-wiring tests pass. A component that exists as code but cannot be started and verified end-to-end is incomplete.

---

## Caveats & Uncertainty

1. **MongoDB integration:** Menu endpoint requires MongoDB read integration. Verify `TenantCollection` wrapper is available for reads.
2. **Data migration:** Finance consolidation requires migrating 9 collections to 1. Estimate: ~50,000 documents. Plan for batch migration (1000 docs/batch).
3. **Purchase order data:** `purchase_orders` MongoDB collection structure needs verification. May require schema mapping.
4. **Employee data:** `employees`, `empadminlist`, `empdashlist` MongoDB collections may have overlapping data. Plan for deduplication.
5. **Backward compatibility:** Removing `CafeMenuItems` tables is a breaking change. Coordinate with frontend team if needed.

---

## Next Steps

1. **Confirm Option A** (remove CafeMenuItems, derive from MongoDB) — see Clarification section
2. **Execute Phase 1** (Cafe Menu Derivation)
3. **Execute Phase 2** (Finance Consolidation)
4. **Execute Phase 3** (Purchase Orders to Inventory)
5. **Execute Phase 4** (Accounts Master Data Migration)
6. **Execute Phase 5** (Employee Migration to PG)
7. **Run post-wiring tests**
8. **Commit and push**
