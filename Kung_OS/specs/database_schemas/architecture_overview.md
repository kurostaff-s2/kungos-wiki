# KungOS Database Architecture Overview

**Status:** DRAFT — Source of Truth  
**Date:** 2026-07-01  
**Version:** 1.5  
**Purpose:** Authoritative reference for all database collections, tables, data flow, and migration status

### Status Legend

| Tag | Meaning | Where to find it |
|-----|---------|------------------|
| `LIVE` | Exists in database today | Current schema, active queries |
| `TARGET` | Planned, not yet implemented | Migration scripts pending |
| `DEFERRED` | Documented but intentionally not yet built | Separate legacy DB or Phase 3b |

**Three Lanes:**
- **LIVE now** — What exists in the database today
- **TARGET later** — What's planned for future migration
- **Contract-stable** — APIs/interfaces that are storage-agnostic (work with any backend)

### Revision History

| Version | Date | Change |
|---------|------|--------|
| 1.5 | 2026-07-01 | Vendors moved from `users_organization` to `inv_vendors` (Inventory domain). `vendor_code` preserved as PK. Phase 2 (MongoDB canonicalization) added as prerequisite. Phase ordering re-aligned. |

### Field Naming Convention

TARGET uses canonical field names (`bg_code`, `div_code`, `branch_code`). The `TenantCollection` wrapper injects canonical names on write. Phase 2 migration renames all documents and indexes to canonical names. Legacy field names (`bgcode`, `division`, `branch`) are no longer supported — all code paths use target state.

---

## 1. Architecture Summary

KungOS uses a **dual-database architecture** with clear separation of concerns:

| Layer | Storage | Purpose | Status |
|-------|---------|---------|--------|
| **Product Catalog** | MongoDB | Names, prices, descriptions, specs, configurations | LIVE |
| **Inventory Tracking** | PostgreSQL | Stock quantities, serial numbers, movements, purchase orders | TARGET |
| **Financial (Transactional)** | MongoDB | Invoices, payments, credit/debit notes, settlements | TARGET |
| **Financial (Master Data)** | PostgreSQL | Partners, banks, loans (tenant-scoped) | TARGET |
| **Orders & Transactions** | PostgreSQL | Customer orders, estimates, service requests | TARGET |
| **User & Tenant** | PostgreSQL | Identities, roles, tenant hierarchy, employees | LIVE |
| **Cafe Platform** | PostgreSQL | Sessions, wallets, pricing, games | LIVE |
| **E-Commerce** | PostgreSQL + MongoDB | Cart, wishlist (PG) + product catalog (MongoDB) | TARGET |
| **RBAC** | PostgreSQL | Permissions, roles, user assignments | LIVE |
| **Platform** | PostgreSQL | Outbox events, tenant config | LIVE |

**Key Principle:** MongoDB stores the **catalog** (what items exist). PostgreSQL stores the **inventory** (how many exist, where they are).

**Contract-Stable APIs:** ViewSets and endpoints are storage-agnostic — they work the same whether data is in MongoDB or PostgreSQL. Migration changes the backend, not the API.

---

## 2. MongoDB Collections

### 2.1 LIVE Collections (Current State)

> **Note:** `products` collection uses discriminator fields (`collection='...'`) to separate sub-catalogs. All collections use tenant scoping via `bg_code`/`div_code`/`branch_code` (canonical).

| Collection | Purpose | ViewSet |
|------------|---------|---------|  
| `products` | Main product catalog (F&B, hardware, etc.) | `ProductViewSet` |
| ↳ `builds` | Legacy builds catalog | `ProductViewSet` |
| ↳ `components` | Hardware components | `ProductViewSet` |
| ↳ `accessories` | PC accessories | `ProductViewSet` |
| ↳ `monitors` | Monitor catalog | `ProductViewSet` |
| ↳ `networking` | Networking equipment | `ProductViewSet` |
| ↳ `external` | External products | `ProductViewSet` |
| ↳ `indentproduct` | Purchase requisitions (complex structure) | `IndentViewSet` |
| `misc` | Brands config | `BrandsViewSet` |
| **Finance (LIVE — 10 collections)** | | |
| ↳ `inwardinvoices` | Purchase invoices | `InwardInvoiceViewSet` |
| ↳ `outwardinvoices` | Sales invoices | `OutwardInvoiceViewSet` |
| ↳ `inwardpayments` | Purchase payments | `InwardPaymentViewSet` |
| ↳ `outwardpayments` | Sales payments | `OutwardPaymentViewSet` |
| ↳ `inwardcreditnotes` | Inward credit notes | `InwardCreditNoteViewSet` |
| ↳ `inwarddebitnotes` | Inward debit notes | `InwardDebitNoteViewSet` |
| ↳ `outwardcreditnotes` | Outward credit notes | `OutwardCreditNoteViewSet` |
| ↳ `outwarddebitnotes` | Outward debit notes | `OutwardDebitNoteViewSet` |
| ↳ `settlements` | Settlements | `SettlementsViewSet` |
| ↳ `bulkpayments` | Bulk payments | `BulkPaymentViewSet` |
| **Employee (LIVE — 4 collections)** | | |
| ↳ `employees` | Employee records | — |
| ↳ `empadminlist` | Admin employee list | — |
| ↳ `empdashlist` | Dashboard employee list | — |
| ↳ `employee_attendance` | Attendance records | — |

### 2.2 TARGET Collections (Future State)

| Collection | Purpose | ViewSet |
|------------|---------|---------|  
| `products` (`collection='cafe-food'`) | Cafe food items (meal sets, combos) | `ProductViewSet` |
| `products` (`collection='cafe-beverage'`) | Cafe beverages (specialty coffee, etc.) | `ProductViewSet` |
| `custom_catalog` (`custom_type='preset'`) | Arcade packages, PC build presets, cafe combos | `CustomCatalogViewSet` |
| `custom_catalog` (`custom_type='tpbuild'`) | Channel-specific build variants (DEFERRED) | `CustomCatalogViewSet` |
| `custom_catalog` (`custom_type='kgbuilds'`) | Kuro Gaming pre-built variants | `CustomCatalogViewSet` |
| `custom_catalog` (`custom_type='custombuilds'`) | Custom PC builds | `CustomCatalogViewSet` |
| `custom_catalog` OR `products` (draft) | Pending approval items | `ProductViewSet`, `CustomCatalogViewSet` |
| `financial_documents` | **Consolidated finance** (10 → 1 collection) | All finance ViewSets |

### 2.3 LEGACY Collections (To Be Removed)

| Collection | Target | Notes |
|------------|--------|-------|
| `presets` | `custom_catalog` (`custom_type='preset'`) | Arcade packages, PC build presets, cafe combos |
| `tpbuilds` | `custom_catalog` (`custom_type='tpbuild'`) | Channel-specific build variants |
| `kgbuilds` | `custom_catalog` (`custom_type='kgbuilds'`) | Kuro Gaming pre-built variants |
| `custombuilds` | `custom_catalog` (`custom_type='custombuilds'`) | Custom PC builds |
| `tempproducts` | `custom_catalog` OR `products` (draft) | Pending approval items |





---

## 3. PostgreSQL Tables

### 3.1 Inventory Domain

#### LIVE (Current State)

| Table | Purpose |
|-------|---------|
| `inventory_inventoryasset` | Equipment assets — Tracks asset_code, serial_number, asset_type, status |
| `inventory_asset_depreciation` | Asset depreciation — Tracks method, rate, accumulated_depreciation, book_value |

#### TARGET (Future State)

| Table | Purpose | Source |
|-------|---------|--------|
| `inv_vendors` | Vendor registry — Suppliers/service providers. PK = `vendor_code` (string, preserved from MongoDB). Multi-state GST in JSONB `gstdetails`. | `vendors` (MongoDB) |
| `inventory_inventoryitem` | Item registry — Tracks item_code, category, collection, base_price | `stock_register` (merged) |
| `inventory_inventorystock` | Branch stock quantities — Tracks stock_quantity, reserved_quantity, available_quantity per branch | `stock_register` |
| `inventory_inventorymovement` | Stock movements — Tracks movement_type, quantity, reference_id, sr_nos | `stock_register` |
| `inv_purchase_orders` | Purchase orders — **Inventory domain** — POs triggered by stock replenishment. `vendor_code` FK → `inv_vendors` | `purchase_orders` (MongoDB) |
| `inv_purchase_order_items` | PO line items — FK → `inventory_inventoryitem`, FK → `inv_purchase_orders` | `purchase_orders` (MongoDB) |

**Why `inv_vendors` (not `users_organization`):**
- Vendors are referenced by `vendor_code` (string) across POs, invoices, debit/credit notes — not by an opaque FK
- `vendor_code` is embedded in PO numbers, invoice IDs, and debit note IDs (e.g., `KCTM0001` → `KCTM-PO-000001`)
- Vendors have procurement-specific fields (multi-state GST, payment terms, registration addresses) unrelated to identity
- `users_organization` is for teams + identity-linked entities; vendors are not users

**Purchase Order Flow (TARGET):**
```
indentproduct (MongoDB) → inv_purchase_orders (PG) → inventory_inventorymovement (stock-in)
                                      ↓
                            inward_invoice (financial_documents)
```

**Vendor Reference Pattern:**
```python
# inv_purchase_orders.vendor_code → inv_vendors.vendor_code (string FK)
# NOT: inv_purchase_orders.vendor_id → users_organization.org_id
```


### 3.1a Accounts Domain — TARGET (Master Data)

Tenant-scoped master data. Sundry ledger is computed from `inv_purchase_orders` + `financial_documents`, not stored separately.

| Table | Purpose | Source |
|-------|---------|--------|
| `acct_partners` | Business partners (creditors + debtors) — Unified, `partner_type` discriminator | `partners` (MongoDB) |
| `acct_banks` | Bank accounts — Tenant-scoped | `banks` (MongoDB) |
| `acct_loans` | Loans — Tenant-scoped | `loans` (MongoDB) |

### 3.2 Orders Domain — TARGET (Phase 8)

| Table | Purpose | Source |
|-------|---------|--------|
| `orders_core` | Core order record — Shared by all order types | `estimates`, `kgorders`, `tporders`, `serviceRequest` |
| `estimate_detail` | Estimate order details — FK → orders_core | `estimates` |
| `in_store_detail` | In-store order details — FK → orders_core | `kgorders` |
| `tp_order_detail` | TP order details — FK → orders_core | `tporders` |
| `service_detail` | Service order details — FK → orders_core | `serviceRequest` |
| `eshop_detail` | E-commerce order details — FK → orders_core | New |

> **Note:** Purchase orders are in Inventory Domain (§3.1), not Orders Domain.

### 3.3 Cafe Domain

#### LIVE (Current State)

| Table | Purpose |
|-------|---------|
| `caf_platform_cafes` | Cafe registry |
| `caf_platform_stations` | Station registry |
| `caf_platform_sessions` | Session tracking |
| `caf_platform_session_leases` | Session lease versioning |
| `caf_platform_station_commands` | Station remote control |
| `caf_platform_station_events` | Station event log |
| `caf_platform_wallets` | Customer wallets — FK → CustomUser (LIVE), FK → users_identity (TARGET) |
| `caf_platform_wallet_transactions` | Wallet transactions — FK wallet_id → wallets, FK created_by_id → CustomUser |
| `caf_platform_price_plans` | Arcade pricing |
| `caf_platform_member_plans` | Member plans |
| `caf_platform_games` | Game catalog |
| `caf_platform_auth_tokens` | Auth tokens |
| `caf_platform_users` | **DEPRECATED** — Replaced by `users_identity` (TARGET) |
| `caf_platform_walkins` | Walk-in customers — TARGET: `identity_id` FK → users_identity (currently: `phone` UNIQUE) |

#### TARGET (Future State)

| Table | Purpose |
|-------|---------|
| `cafe_fnb_detail` | F&B order details — Linked to orders_core |
| `cafe_fnb_refunds` | F&B refunds — Linked to cafe_fnb_detail |

### 3.4 User & Tenant Domain

#### LIVE (Current State)

| Table | Purpose |
|-------|---------|
| `tenant_business_groups` | Business groups — Legal entity. Code = first 4 letters of legal name + seq |
| `tenant_divisions` | Divisions — FK → tenant_business_groups |
| `tenant_branches` | Branches — FK → tenant_divisions |
| `tenant_bank_accounts` | Bank accounts — FK → tenant_business_groups |
| `tenant_division_addresses` | Division addresses — FK → tenant_divisions |
| `users_customuser` | Auth model (Django) — 16 cols. USERNAME_FIELD='phone'. Being replaced by users_identity |
| `users_kurouser` | Extended profile — 42 cols. 39 mapped (31→employee, 3→identity, 4→replaced), 3 dropped |
| `users_user_tenant_context` | Session tenant scope — `div_codes`/`branch_codes` as JSONB lists |
| `users_accesslevel` | **DEPRECATED** — Permission registry. 55 cols. Replaced by RBAC tables |
| `users_phonemodel` | OTP verification |
| `users_switchgroupmodel` | BG switching tokens |
| `users_common_counters` | **LEGACY** — Legacy counter tracking |

#### TARGET (Future State)

| Table | Purpose |
|-------|---------|
| `users_identity` | Core identity — Replaces CustomUser, reb_users, employees, players |
| `identity_phone_aliases` | Associated phone numbers |
| `users_employee` | Employee extension — FK → users_identity. Merges `employees`, `empadminlist`, `empdashlist` (MongoDB) |
| `employee_attendance` | Attendance records — New table. FK → users_identity. Merges `employee_attendance` (MongoDB) |
| `users_customer` | Customer extension — FK → users_identity |
| `users_player` | Player extension — FK → users_identity |
| `users_organization` | Organizations (teams only) — `org_type='team'` |
| `users_team_profile` | Team extension — FK → users_organization |
| `team_memberships` | Team-to-person mapping |

> **Note:** Vendors are NOT in `users_organization`. They live in `inv_vendors` (Inventory Domain, §3.1).
> Vendors are procurement entities, not identity entities. Referenced by `vendor_code` (string), not `org_id` FK.

### 3.5 RBAC Domain — LIVE (Stable)

| Table | Purpose |
|-------|---------|
| `rbac_permissions` | Permission registry — 35 permissions |
| `rbac_roles` | Role registry — Single-level inheritance |
| `rbac_role_permissions` | Role-permission mapping — Level 0-3 |
| `rbac_user_roles` | User-role assignment — Scoped by bg_code + div_code |
| `rbac_user_role_branches` | Branch-level scoping — FK → rbac_user_roles |
| `rbac_user_permissions` | Direct permission overrides |

**Resolution engine:** `users/permissions.py` — `resolve_permission()` cascades: exact div_code → BG-wide → global. Max-level wins.

### 3.6 E-Commerce Domain — TARGET

| Table | Purpose |
|-------|---------|
| `eshop_cart` | Shopping cart — FK → users_identity, productid (ref MongoDB `products`) |
| `eshop_wishlist` | Wishlist — FK → users_identity, productid (ref MongoDB `products`) |
| `eshop_detail` | E-commerce order details — FK → orders_core |

> **Note:** No schema spec exists yet. Refer to e-commerce backend for deferred details.

### 3.7 Platform Domain — LIVE (Stable)

| Table | Purpose |
|-------|---------|
| `platform_outbox_events` | Outbox pattern — Cross-store consistency, uuid event_id PK |
| `platform_tenant_config` | Tenant configuration — Per BG settings, PK on bg_code |

---

## 4. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MONGODB (Catalog + Finance Layer)                  │
│                                                                                 │
│  ┌─────────────────────────────────────────────────┐                            │
│  │   products (LIVE + MIGRATED)                    │                            │
│  │  collection='products'    — Main catalog        │                            │
│  │  collection='builds'        — builds (MIGRATED) │                            │
│  │  collection='components'    — components        │                            │
│  │  collection='accessories'   — accessories       │                            │
│  │  collection='monitors'      — monitors          │                            │
│  │  collection='networking'    — networking        │                            │
│  │  collection='external'      — external          │                            │
│  │  collection='cafe-food'     — cafe food (TGT)   │                            │
│  │  collection='cafe-beverage' — cafe drinks(TGT)  │                            │
│  │  collection='indentproduct' — purchase reqs     │                            │
│  │  collection='draft'         — pending approval  │                            │
│  └───────────────────────┬─────────────────────────┘                            │
│                          │                                                      │
│  ┌─────────────────────────────────────────────────┐                            │
│  │   custom_catalog (LEGACY + DEFERRED)            │                            │
│  │  custom_type='preset'     — presets (LEGACY)    │                            │
│  │  custom_type='tpbuild'    — tpbuilds (DEFERRED) │                            │
│  │  custom_type='kgbuilds'   — kgbuilds (LEGACY)   │                            │
│  │  custom_type='custombuilds' — custombuilds      │                            │
│  └───────────────────────┬─────────────────────────┘                            │
│                          │                                                      │
│                          ▼                                                      │
│  ┌─────────────────────────────────────────────────┐                            │
│  │   financial_documents (TARGET — Consolidated)   │                            │
│  │  doc_type='inward_invoice'   — Inward invoices  │                            │
│  │  doc_type='outward_invoice'  — Outward invoices │                            │
│  │  doc_type='inward_payment'   — Inward payments  │                            │
│  │  doc_type='outward_payment'  — Outward payments │                            │
│  │  doc_type='credit_note'      — Credit notes     │                            │
│  │  doc_type='debit_note'       — Debit notes      │                            │
│  │  doc_type='settlement'       — Settlements      │                            │
│  │  doc_type='bulk_payment'     — Bulk payments    │                            │
│  └─────────────────────────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           POSTGRESQL (Transaction Layer)                        │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │ inventory_      │  │  inv_           │  │   orders_       │                 │
│  │ (TARGET)        │  │  purchase_      │  │ (TARGET)        │                 │
│  │                 │  │   (TARGET)      │  │                 │                 │
│  │ - Stock qty     │  │                 │  │ - All orders    │                 │
│  │ - Branch stock  │  │ - POs           │  │ - Estimates     │                 │
│  │ - Available qty │  │ - PO items      │  │ - TP orders     │                 │
│  │                 │  │ - From indent-  │  │ - Service       │                 │
│  │                 │  │   product       │  │                 │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │  acct_          │  │  eshop_         │  │  users_         │                 │
│  │    (TARGET)     │  │    (TARGET)     │  │   (TARGET)      │                 │
│  │                 │  │                 │  │                 │                 │
│  │ - Partners      │  │ - Shopping cart │  │ - Employees     │                 │
│  │ - Banks         │  │ - Wishlist      │  │ - Customers     │                 │
│  │ - Loans         │  │ - Ref MongoDB   │  │ - Players       │                 │
│  │                 │  │   productid     │  │ - Attendance    │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │  caf_platform_  │  │  rbac_          │  │  tenant_        │                 │
│  │   (LIVE)        │  │    (LIVE)       │  │    (LIVE)       │                 │
│  │                 │  │                 │  │                 │                 │
│  │ - Gaming        │  │ - Permissions   │  │ - BGs           │                 │
│  │   sessions      │  │ - Roles         │  │ - Divisions     │                 │
│  │ - Wallets       │  │ - User roles    │  │ - Branches      │                 │
│  │ - Pricing       │  │ - Direct perms  │  │ - Bank accts    │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐                                      │
│  │  platform_      │  │ inventory_      │                                      │
│  │   (LIVE)        │  │ asset_*         │                                      │
│  │                 │  │   (LIVE)        │                                      │
│  │ - Outbox events │  │                 │                                      │
│  │ - Tenant config │  │ - Assets        │                                      │
│  │                 │  │ - Depreciation  │                                      │
│  └─────────────────┘  └─────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Collection-to-Table Mapping

### 5.1 MongoDB → MongoDB (Legacy → Products Catalog)

| Source Collection | Target Collection | Discriminator |
|-------------------|-------------------|---------------|
| `builds` | `products` | `collection='builds'` |
| `components` | `products` | `collection='components'` |
| `accessories` | `products` | `collection='accessories'` |
| `monitors` | `products` | `collection='monitors'` |
| `networking` | `products` | `collection='networking'` |
| `external` | `products` | `collection='external'` |
| — | `products` | `collection='cafe-food'` (TARGET) |
| — | `products` | `collection='cafe-beverage'` (TARGET) |

### 5.2 MongoDB → PostgreSQL (Migrated)

| MongoDB Collection | PostgreSQL Table(s) | Migration Status |
|-------------------|---------------------|------------------|
| `asset_register` | `inventory_inventoryasset` | ✅ Phase 8 |
| `stock_register` | `inventory_inventorystock` | 🔜 TO BE MIGRATED |
| `vendors` | `inv_vendors` | 🔜 TO BE MIGRATED (Inventory domain, vendor_code preserved as PK) |
| `indentpos` | `inv_purchase_orders` | 🔜 TO BE MIGRATED |
| `purchase_orders` | `inv_purchase_orders` + `inv_purchase_order_items` | 🔜 TO BE MIGRATED (Inventory domain) |
| `partners` | `acct_partners` | 🔜 TO BE MIGRATED (Accounts master data) |
| `banks` | `acct_banks` | 🔜 TO BE MIGRATED (Accounts master data) |
| `loans` | `acct_loans` | 🔜 TO BE MIGRATED (Accounts master data) |
| `employees` | `users_employee` | 🔜 TO BE MIGRATED (Phase 1) |
| `empadminlist` | `users_employee` | 🔜 TO BE MIGRATED (Phase 1) |
| `empdashlist` | `users_employee` | 🔜 TO BE MIGRATED (Phase 1) |
| `employee_attendance` | `employee_attendance` | 🔜 TO BE MIGRATED (New PG table) |

### 5.3 MongoDB → MongoDB (Consolidation)

| Source Collection | Target Collection | Discriminator |
|-------------------|-------------------|---------------|
| `presets` | `custom_catalog` | `custom_type='preset'` (includes arcade + cafe combos) |
| `tpbuilds` | `custom_catalog` | `custom_type='tpbuild'` |
| `kgbuilds` | `custom_catalog` | `custom_type='kgbuilds'` |
| `custombuilds` | `custom_catalog` | `custom_type='custombuilds'` |
| `tempproducts` | `custom_catalog` OR `products` | `custom_type='draft'` OR `collection='draft'` |
| `products` | `products` | `collection='products'` |
| `indentproduct` | `products` | `collection='indentproduct'` |
| `misc` | **Excluded** | Brands config only |

### 5.4 MongoDB → MongoDB (Finance Consolidation)

9 collections → 1 collection with `doc_type` discriminator.

| Source Collection | Target Collection | Discriminator |
|-------------------|-------------------|---------------|
| `inwardinvoices` | `financial_documents` | `doc_type='inward_invoice'` |
| `outwardinvoices` | `financial_documents` | `doc_type='outward_invoice'` |
| `inwardpayments` | `financial_documents` | `doc_type='inward_payment'` |
| `outwardpayments` | `financial_documents` | `doc_type='outward_payment'` |
| `inwardcreditnotes` | `financial_documents` | `doc_type='inward_credit_note'` |
| `inwarddebitnotes` | `financial_documents` | `doc_type='inward_debit_note'` |
| `outwardcreditnotes` | `financial_documents` | `doc_type='outward_credit_note'` |
| `outwarddebitnotes` | `financial_documents` | `doc_type='outward_debit_note'` |
| `settlements` | `financial_documents` | `doc_type='settlement'` |
| `bulkpayments` | `financial_documents` | `doc_type='bulk_payment'` |

### 5.5 MongoDB → PostgreSQL (Employee Migration)

4 collections → 2 PG tables.

| Source Collection | Target Table | Notes |
|-------------------|--------------|-------|
| `employees` | `users_employee` | Core employee data |
| `empadminlist` | `users_employee` | Filter by `role IN ('admin', 'manager')` |
| `empdashlist` | `users_employee` | Filter by `is_active=true` |
| `employee_attendance` | `employee_attendance` | New PG table, FK → users_identity |

---

## 6. ViewSet-to-Collection Mapping

> **Contract-Stable:** ViewSets are storage-agnostic — they work the same whether data is in MongoDB or PostgreSQL. Migration changes the backend, not the API.

### 6.1 Product Domain

| ViewSet | Collection(s) | Status |
|---------|---------------|--------|
| `ProductViewSet` | `products` (LIVE) | LIVE |
| `CustomCatalogViewSet` | `custom_catalog` (TARGET) | TARGET |
| `TPBuildViewSet` | `custom_catalog` (custom_type='tpbuild') (TARGET) | TARGET |
| `TempProductViewSet` | `custom_catalog` OR `products` (draft) (TARGET) | TARGET |
| `IndentViewSet` | `indentproduct` (MongoDB) (LIVE) | LIVE |
| `BrandsViewSet` | `misc` (MongoDB) (LIVE) | LIVE |

### 6.2 Inventory Domain

| ViewSet | Collection(s) | Status |
|---------|---------------|--------|
| `InventoryViewSet` | `inventory_inventorystock` (PG) (TARGET) | TARGET |
| `AssetRegisterViewSet` | `inventory_inventoryasset` (PG) (LIVE) | LIVE |
| `StockAuditViewSet` | `inventory_inventorymovement` (PG) (TARGET) | TARGET |
| `PurchaseOrderViewSet` | `inv_purchase_orders` (PG) (TARGET) | TARGET |
| `VendorViewSet` | `inv_vendors` (PG) (TARGET) | TARGET |

> **Note:** `PurchaseOrderViewSet` is in Inventory domain, not Accounts. POs are inventory management (triggered by stock replenishment), not financial operations.
> `VendorViewSet` is in Inventory domain (procurement), not in `users_organization` (identity).

### 6.3 Accounts Domain

| ViewSet | Collection(s) | Status |
|---------|---------------|--------|
| `InwardInvoiceViewSet` | `financial_documents` (`doc_type='inward_invoice'`) (TARGET) | TARGET |
| `OutwardInvoiceViewSet` | `financial_documents` (`doc_type='outward_invoice'`) (TARGET) | TARGET |
| `InwardPaymentViewSet` | `financial_documents` (`doc_type='inward_payment'`) (TARGET) | TARGET |
| `OutwardPaymentViewSet` | `financial_documents` (`doc_type='outward_payment'`) (TARGET) | TARGET |
| `InwardCreditNoteViewSet` | `financial_documents` (`doc_type='inward_credit_note'`) (TARGET) | TARGET |
| `InwardDebitNoteViewSet` | `financial_documents` (`doc_type='inward_debit_note'`) (TARGET) | TARGET |
| `OutwardCreditNoteViewSet` | `financial_documents` (`doc_type='outward_credit_note'`) (TARGET) | TARGET |
| `OutwardDebitNoteViewSet` | `financial_documents` (`doc_type='outward_debit_note'`) (TARGET) | TARGET |
| `SettlementsViewSet` | `financial_documents` (`doc_type='settlement'`) (TARGET) | TARGET |
| `BulkPaymentViewSet` | `financial_documents` (`doc_type='bulk_payment'`) (TARGET) | TARGET |
| `PartnersViewSet` | `acct_partners` (PG) (TARGET) | TARGET |
| `BanksViewSet` | `acct_banks` (PG) (TARGET) | TARGET |
| `LoansViewSet` | `acct_loans` (PG) (TARGET) | TARGET |

---

## 7. Draft Workflow

### 7.1 Draft Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│  Draft Created                                                  │
│  - custom_catalog: custom_type='draft', is_draft=True          │
│  - products: collection='draft', is_draft=True                 │
│  - target_type / target_collection: where to promote to        │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Approval Action                                                │
│  - POST /products/drafts/{id}/approve                          │
│  - POST /products/custom-catalog/drafts/{id}/approve           │
│  - Update discriminator in-place                                │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Approved Document                                              │
│  - custom_catalog: custom_type='preset' / 'tpbuild' / etc.     │
│  - products: collection='products' / 'indentproduct'           │
│  - is_draft=False                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Draft Schema Fields

```javascript
// custom_catalog document (draft)
{
  custom_type: 'draft',
  is_draft: true,
  target_type: 'preset' | 'tpbuild' | 'kgbuilds' | 'custombuilds',
  approved_by: String,
  approved_date: DateTime,
  // ... rest of fields
}

// products document (draft)
{
  collection: 'draft',
  is_draft: true,
  target_collection: 'products' | 'indentproduct',
  approved_by: String,
  approved_date: DateTime,
  // ... rest of fields
}
```

---

## 8. Cafe Menu Architecture

### 8.1 Menu Derivation

The cafe menu is derived dynamically from MongoDB catalog collections — no separate `CafeMenuItems` table needed.

```
┌─────────────────────────────────────────────────────────────────┐
│  MongoDB (Catalog)                                              │
│                                                                 │
│  products (collection='cafe-food') → Cafe food items           │
│  products (collection='cafe-beverage') → Cafe beverages        │
│  custom_catalog (custom_type='preset') → Arcade packages       │
│                                          + Cafe combos           │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Menu API (ViewSet)                                             │
│  - Reads F&B from products                                     │
│  - Reads arcade/combos from custom_catalog                     │
│  - Checks availability from inventory_inventorystock (PG)      │
│  - Returns unified menu                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Menu API Implementation

```python
# cafe_fnb/views.py — Menu endpoint
def get_menu(branch_code: str):
    # Get F&B items from products
    fnb_items = db.products.find(
        {"collection": {"$in": ["cafe-food", "cafe-beverage"]}}
    )
    
    # Get arcade packages + cafe combos from custom_catalog
    catalog_items = db.custom_catalog.find(
        {"custom_type": "preset"}
    )
    
    # Get branch availability from PostgreSQL
    availability = db.inventory_inventorystock.find(
        {"branch_code": branch_code, "stock_quantity": {"$gt": 0}}
    )
    
    # Merge and return
    return fnb_items + catalog_items
```

### 8.3 Migration: Hardcoded CafeMenuItems → MongoDB

| Source | Target | Notes |
|--------|--------|-------|
| `CafeMenuItems` (PG, hardcoded) | `products` (`collection='cafe-food'`) | Migrate F&B items |
| `CafeMenuItems` (PG, hardcoded) | `products` (`collection='cafe-beverage'`) | Migrate beverage items |
| `presets` (MongoDB) | `custom_catalog` (`custom_type='preset'`) | Arcade packages + cafe combos |
| `CafeMenuBranchAvailability` (PG) | **Removed** | Availability derived from `inventory_inventorystock` |

> **Note:** Phase 8 (Cafe Menu Sync) is removed. Menu is derived dynamically, not synced to PG.

---

## 9. Migration Plan

> Unified phase plan. Cross-references the architecture overview, mongodb_schema.md, and postgresql_schema.md.

### Phase 0: Foundation (LIVE)

Already complete. Tenant, RBAC, and platform schemas are stable.

- [x] Tenant schema (5 tables) — LIVE
- [x] RBAC schema (6 tables) — LIVE
- [x] Platform schema (2 tables) — LIVE
- [x] Cafe platform core (12 tables) — LIVE
- [x] `asset_register` → `inventory_inventoryasset` — MIGRATED
- [x] Legacy collections (`builds`, `components`, `accessories`, `monitors`, `networking`, `external`) → `products` — MIGRATED

### Phase 1: Identity + Employee Migration (TARGET)

Migrate user data from MongoDB + legacy PG tables to unified `users_identity` + extensions. Migrate employee collections to PG.

- [ ] Create `users_identity` table (char(20) PK, `ID000001` sequence)
- [ ] Migrate `reb_users` → `users_identity` + `users_customer`
- [ ] Migrate `players` → `users_identity` + `users_player`
- [ ] Migrate `teams` → `users_organization` + `users_team_profile`
> **Note:** Vendors are NOT migrated here. They go to `inv_vendors` (Inventory Domain, Phase 5).
- [ ] Create `identity_phone_aliases` table
- [ ] Create `users_employee` table
- [ ] Migrate `employees` (MongoDB) → `users_employee`
- [ ] Migrate `empadminlist` (MongoDB) → `users_employee` (filter by role)
- [ ] Migrate `empdashlist` (MongoDB) → `users_employee` (filter by is_active)
- [ ] Create `employee_attendance` table (PG)
- [ ] Migrate `employee_attendance` (MongoDB) → `employee_attendance` (PG)
- [ ] Migrate `KuroUser` employee fields → `users_employee`
- [ ] Migrate `KuroUser` identity fields → `users_identity`
- [ ] Update `caf_platform_wallets` FK: CustomUser → users_identity
- [ ] Update `caf_platform_walkins` FK: phone → identity_id
- [ ] Deprecate `caf_platform_users` (replaced by users_identity)
- [ ] Create indexes on `users_identity` (`bg_code`, `phone`, `email`, `status`)

### Phase 2: MongoDB Field Canonicalization

Rename legacy field names to canonical across all MongoDB collections.

- [ ] Batch migration: rename fields across all 31 collections (1000 docs/batch)
- [ ] Index rebuild: drop legacy indexes, create canonical indexes
- [ ] Schema validation: enable JSON Schema requiring canonical fields
- [ ] Validation gates: `python manage.py mongo_field_migration --validate`
- [ ] Verify all code paths use canonical field names (no legacy support)

### Phase 3: Product Catalog Consolidation (TARGET)

Create `custom_catalog` and consolidate legacy preset/build collections.

- [ ] Create `custom_catalog` collection
- [ ] Merge `presets` → `custom_catalog` (`custom_type='preset'`)
- [ ] Merge `kgbuilds` → `custom_catalog` (`custom_type='kgbuilds'`) — from legacy e-commerce DB
- [ ] Flatten `presets.list[]` → `custom_catalog` (`custom_type='cafe-arcade'`)
- [ ] Add draft workflow fields (`is_draft`, `target_type`, etc.)
- [ ] Create indexes on `custom_catalog`
- [ ] Create `CustomCatalogViewSet`

### Phase 4: Draft Workflow (TARGET)

Implement product draft/approval workflow.

- [ ] Add `is_draft`, `target_type`, `target_collection` fields to `custom_catalog` and `products`
- [ ] Create approval endpoints (`POST /products/drafts/{id}/approve`)
- [ ] Update ViewSets to filter by `is_draft`
- [ ] Create `TempProductViewSet`

### Phase 5: Stock + Purchase Order Migration to PostgreSQL (TARGET)

Migrate stock/inventory data and purchase orders from MongoDB to PostgreSQL. POs belong to Inventory domain, not Accounts.

- [ ] Verify collection name: `stock_register` or `stock`?
- [ ] Create `inventory_inventoryitem` table
- [ ] Create `inventory_inventorystock` table
- [ ] Create `inventory_inventorymovement` table
- [ ] Migrate stock data → PG tables
- [ ] Create `inv_purchase_orders` table (Inventory domain)
- [ ] Create `inv_purchase_order_items` table
- [ ] Create `inv_vendors` table (vendor_code PK, multi-state GST in JSONB gstdetails)
- [ ] Migrate `vendors` (MongoDB) → `inv_vendors` (PG) — preserve vendor_code as PK
- [ ] Migrate `purchase_orders` (MongoDB) → `inv_purchase_orders` + `inv_purchase_order_items`
- [ ] Migrate `indentpos` (MongoDB) → `inv_purchase_orders` (if not same as `purchase_orders`)
- [ ] Update `InventoryViewSet` to read from PG
- [ ] Move `PurchaseOrderViewSet` from Accounts to Inventory domain
- [ ] Create `VendorViewSet` in Inventory domain
- [ ] Add FK: `inv_purchase_order_items.item_code` → `inventory_inventoryitem.item_code`
- [ ] Add FK: `inv_purchase_orders.vendor_code` → `inv_vendors.vendor_code`
- [ ] Add indexes (`vendor_code`, `item_code`, `branch_code`, `item_id+branch_code` unique)
- [ ] Drop/archive `stock_register`, `purchase_orders`, `indentpos`, `vendors` from MongoDB

### Phase 5.5: Finance Consolidation (TARGET)

Consolidate 9 finance collections → 1 collection with `doc_type` discriminator.

- [ ] Create `financial_documents` collection
- [ ] Migrate `inwardinvoices` → `financial_documents` (`doc_type='inward_invoice'`)
- [ ] Migrate `outwardinvoices` → `financial_documents` (`doc_type='outward_invoice'`)
- [ ] Migrate `inwardpayments` → `financial_documents` (`doc_type='inward_payment'`)
- [ ] Migrate `outwardpayments` → `financial_documents` (`doc_type='outward_payment'`)
- [ ] Migrate `inwardcreditnotes` → `financial_documents` (`doc_type='inward_credit_note'`)
- [ ] Migrate `inwarddebitnotes` → `financial_documents` (`doc_type='inward_debit_note'`)
- [ ] Migrate `outwardcreditnotes` → `financial_documents` (`doc_type='outward_credit_note'`)
- [ ] Migrate `outwarddebitnotes` → `financial_documents` (`doc_type='outward_debit_note'`)
- [ ] Migrate `settlements` → `financial_documents` (`doc_type='settlement'`)
- [ ] Migrate `bulkpayments` → `financial_documents` (`doc_type='bulk_payment'`)
- [ ] Create indexes on `financial_documents` (`doc_type`, `bg_code`, `div_code`)
- [ ] Update all finance ViewSets to read from `financial_documents` with discriminator filtering
- [ ] Drop/archive old finance collections from MongoDB

### Phase 5.6: Accounts Master Data Migration (TARGET)

Migrate partners, banks, loans from MongoDB to PostgreSQL tenant-scoped tables.

- [ ] Create `acct_partners` table (PG, tenant-scoped)
- [ ] Create `acct_banks` table (PG, tenant-scoped)
- [ ] Create `acct_loans` table (PG, tenant-scoped)
- [ ] Migrate `partners` (MongoDB) → `acct_partners`
- [ ] Migrate `banks` (MongoDB) → `acct_banks`
- [ ] Migrate `loans` (MongoDB) → `acct_loans`
- [ ] Sundry ledger: computed from `inv_purchase_orders` + `financial_documents` (no separate table)
- [ ] Update `PartnersViewSet`, `BanksViewSet`, `LoansViewSet` to read from PG
- [ ] Drop/archive `partners`, `banks`, `loans` from MongoDB

### Phase 6: Orders Domain Migration (Phase 8, TARGET)

Migrate order data from MongoDB to PostgreSQL.

- [ ] Create `orders_core` table (13 cols, order_type ENUM)
- [ ] Create `estimate_detail`, `in_store_detail`, `tp_order_detail`, `service_detail`, `eshop_detail`
- [ ] Migrate `estimates` → `orders_core` + `estimate_detail`
- [ ] Migrate `kgorders` → `orders_core` + `in_store_detail`
- [ ] Migrate `tporders` → `orders_core` + `tp_order_detail`
- [ ] Migrate `serviceRequest` → `orders_core` + `service_detail`
- [ ] Update order ViewSets to read from PG

### Phase 7: E-Commerce Collections Integration (Phase 3b, DEFERRED)

Integrate legacy e-commerce collections from separate database.

- [ ] Migrate `tpbuilds` → `custom_catalog` (`custom_type='tpbuild'`)
- [ ] Migrate `custombuilds` → `custom_catalog` (`custom_type='custombuilds'`)
- [ ] Migrate `tempproducts` → draft workflow
- [ ] Create `eshop_cart`, `eshop_wishlist` tables
- [ ] Create `eshop_detail` table
- [ ] Update ViewSets for e-commerce endpoints

### Phase 8: Cafe Menu Derivation (TARGET)

Derive cafe menu dynamically from MongoDB catalog — no separate `CafeMenuItems` table.

- [ ] Migrate hardcoded `CafeMenuItems` → `products` (`collection='cafe-food'`, `collection='cafe-beverage'`)
- [ ] Migrate `presets` → `custom_catalog` (`custom_type='preset'`) — includes arcade packages + cafe combos
- [ ] Update Menu ViewSet to read from `products` + `custom_catalog` dynamically
- [ ] Remove `CafeMenuBranchAvailability` (availability derived from `inventory_inventorystock`)
- [ ] Remove `sync_cafe_menu` management command (no longer needed)
- [ ] Add indexes on `products` (`collection`, `active`, `delete_flag`)
- [ ] Add indexes on `custom_catalog` (`custom_type`, `bg_code`, `div_code`)

---

## 10. Index Strategy

### 10.1 MongoDB Indexes

> All 31 LIVE collections have `(bg_code, div_code)` compound index (canonical).

```javascript
// custom_catalog (TARGET — Phase 1)
db.custom_catalog.createIndex({ bg_code: 1, div_code: 1, custom_type: 1 })
db.custom_catalog.createIndex({ bg_code: 1, div_code: 1, branch_code: 1 })
db.custom_catalog.createIndex({ productid: 1 }, { unique: true })
db.custom_catalog.createIndex({ type: 1 })

// products (LIVE + MIGRATED)
db.products.createIndex({ bg_code: 1, div_code: 1 })
db.products.createIndex({ bg_code: 1, div_code: 1, active: 1, delete_flag: 1 })
db.products.createIndex({ productid: 1 }, { unique: true })
db.products.createIndex({ category: 1 })
db.products.createIndex({ type: 1 })

// All collections use canonical field names (bg_code, div_code, branch_code)
// reb_users: (bg_code, phone)
// players: (bg_code, playerid)
// vendors: (bg_code, gstin)
// employee_attendance: (bg_code, userid)
// kgorders: (bg_code, orderid)
// tporders: (bg_code, orderid)
// estimates: (bg_code, estimateid)
// serviceRequest: (bg_code, sr_no)
```

### 10.2 PostgreSQL Indexes

> LIVE tables already indexed. TARGET tables: indexes created as part of migration.

```sql
-- users_identity (TARGET — Phase 1)
CREATE UNIQUE INDEX uq_identity_tenant_phone ON users_identity (bg_code, phone);
CREATE INDEX idx_identity_tenant ON users_identity (bg_code, div_code);
CREATE INDEX idx_identity_email ON users_identity (email);
CREATE INDEX idx_identity_status ON users_identity (status);

-- inventory_* (TARGET — Phase 5)
CREATE INDEX idx_inv_item_code ON inventory_inventoryitem (item_code);
CREATE INDEX idx_inv_item_category ON inventory_inventoryitem (category);
CREATE INDEX idx_inv_item_collection ON inventory_inventoryitem (collection);
CREATE INDEX idx_inv_stock_item ON inventory_inventorystock (item_id);
CREATE INDEX idx_inv_stock_branch ON inventory_inventorystock (branch_code);
CREATE UNIQUE INDEX uq_inv_stock_item_branch ON inventory_inventorystock (item_id, branch_code);

-- inv_purchase_orders (TARGET — Phase 5, Inventory domain)
CREATE UNIQUE INDEX uq_inv_po_po_number ON inv_purchase_orders (po_number);
CREATE INDEX idx_inv_po_vendor ON inv_purchase_orders (vendor_id);
CREATE INDEX idx_inv_po_status ON inv_purchase_orders (status);
CREATE INDEX idx_inv_po_div_code ON inv_purchase_orders (div_code);
CREATE INDEX idx_inv_po_item ON inv_purchase_order_items (item_code);

-- financial_documents (TARGET — Phase 5.5)
db.financial_documents.createIndex({ doc_type: 1, bg_code: 1, div_code: 1 })
db.financial_documents.createIndex({ doc_type: 1, status: 1 })
db.financial_documents.createIndex({ party: 1 })

-- acct_* (TARGET — Phase 5.6)
CREATE UNIQUE INDEX uq_acct_partner_code ON acct_partners (bg_code, partner_type, code);
CREATE INDEX idx_acct_partner_type ON acct_partners (partner_type);
CREATE UNIQUE INDEX uq_acct_bank_code ON acct_banks (bg_code, code);
CREATE UNIQUE INDEX uq_acct_loan_code ON acct_loans (bg_code, code);

-- orders_core (TARGET — Phase 6)
CREATE UNIQUE INDEX uq_orders_orderid ON orders_core (orderid);
CREATE INDEX idx_orders_type ON orders_core (order_type);
CREATE INDEX idx_orders_status ON orders_core (status);
CREATE INDEX idx_orders_div_code ON orders_core (div_code);
```

---

## 11. Guardrails

### 11.1 Foreign Key Integrity

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

-- Inventory items reference MongoDB productid via item_code
-- No FK constraint (MongoDB is external)

-- Purchase orders (Inventory domain) reference inventory items
ALTER TABLE inv_purchase_order_items
  ADD CONSTRAINT fk_po_item
  FOREIGN KEY (item_code) REFERENCES inventory_inventoryitem (item_code);

-- Purchase orders reference vendors (Inventory domain, not users_organization)
ALTER TABLE inv_purchase_orders
  ADD CONSTRAINT fk_po_vendor
  FOREIGN KEY (vendor_code) REFERENCES inv_vendors (vendor_code);

-- Vendors reference tenant
ALTER TABLE inv_vendors
  ADD CONSTRAINT fk_vendor_bg
  FOREIGN KEY (bg_code) REFERENCES tenant_business_groups (bg_code);

-- Accounts master data references tenant
ALTER TABLE acct_partners
  ADD CONSTRAINT fk_acct_partner_bg
  FOREIGN KEY (bg_code) REFERENCES tenant_business_groups(bg_code);

ALTER TABLE acct_banks
  ADD CONSTRAINT fk_acct_bank_bg
  FOREIGN KEY (bg_code) REFERENCES tenant_business_groups(bg_code);

ALTER TABLE acct_loans
  ADD CONSTRAINT fk_acct_loan_bg
  FOREIGN KEY (bg_code) REFERENCES tenant_business_groups(bg_code);
```

### 11.2 Tenant-First Indexing

All tables with tenant context carry compound indexes on `(bg_code, div_code)`. This enables:
- Query-level tenant filtering without joins
- RLS policy efficiency
- Cross-tenant audit queries

### 11.3 MongoDB Tenant Isolation — Three Layers

1. **`TenantCollection` wrapper** (application-level): Injects `bg_code` into every read/write. Raises `TenantContextMissing` if no active context.
2. **JSON Schema validation** (database-level): Requires `bg_code` as mandatory field. Prevents orphan documents without tenant context.
3. **Tenant-filtered views** (read-only): MongoDB views with `$match: {bg_code: {$ne: ""}}` pipeline.

**Anti-pattern:** Raw PyMongo calls bypass the `TenantCollection` layer. All views must route through `get_collection()` helper.

### 11.4 Soft Delete Pattern

All collections/tables use `delete_flag` (MongoDB) or `is_deleted` (PostgreSQL) for soft deletes. Hard deletes are never used for catalog data.

### 11.5 Check Constraints

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

### 11.6 Composite Tenant Constraints

```sql
-- Phone uniqueness within tenant
CREATE UNIQUE INDEX uq_identity_tenant_phone
  ON users_identity (bg_code, phone);
```

---

## 12. References

- **MongoDB Schema:** `mongodb_schema.md` — LIVE vs TARGET collection details, field naming skew, tenant enforcement
- **PostgreSQL Schema:** `postgresql_schema.md` — LIVE vs TARGET table details, column specs, constraints
- **Migration Spec:** `migration_spec.md` — Detailed migration scripts and steps
- **Data Mapping:** `data_mapping.md` — Field-level mapping between source and target
- **E-Commerce Backend:** Legacy separate database (Phase 3b) — `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets`

---

## 13. Revision History

| Date | Version | Changes |
|------|---------|---------|  
| 2026-07-01 | 1.0 | Initial draft based on catalog consolidation and cafe menu analysis |
| 2026-07-01 | 1.1 | Fixed legacy collection targets (builds/components/etc → products, not PG). Added status tags to all entities. Unified migration plan (Phases 0-9). Consolidated guardrails from PG and MongoDB schema specs. Added field naming skew documentation. Updated data flow diagram. Added missing PG tables. Flagged unresolved issues. |
| 2026-07-01 | 1.2 | Finance consolidation: 9 collections → 1 (`financial_documents`). Purchase orders moved to Inventory domain (`inv_purchase_orders`). Partners/banks/loans moved to PG (`acct_*`). Employee collections migrated to PG (`users_employee`, `employee_attendance`). Added Accounts domain (§3.1a). Updated migration plan (Phases 0-8 with 5.5/5.6 sub-phases). Updated data flow diagram with Accounts domain. |
| 2026-07-01 | 1.3 | Cafe menu redesign: Removed `CafeMenuItems` and `CafeMenuBranchAvailability` PG tables. Added `cafe-food` and `cafe-beverage` discriminators to `products`. Cafe combos merged into `custom_catalog` (`custom_type='preset'`). Menu derived dynamically from MongoDB — no sync command needed. Updated data flow diagram, §3.3, §5.1, §5.3, §8, Phase 8. Removed dual-read middleware references — all code paths use canonical field names (no legacy support). |
| 2026-07-01 | 1.4 | Three-lane structure: Separated all sections into LIVE (current state), TARGET (future state), and contract-stable (storage-agnostic APIs). Removed redundant §2.2/§2.3 sections. Updated §1, §2, §3, §6 to use clear LIVE/TARGET separation. Removed mixed status rows. Fixed naming drift: `rbac_user_roles` scoped by `bg_code + div_code` (not `division`). |
| 2026-07-01 | 1.5 | Naming consistency pass: Fixed `resolve_permission()` cascades description ("exact division" → "exact div_code"). Fixed index names (`idx_inv_po_division` → `idx_inv_po_div_code`, `idx_orders_division` → `idx_orders_div_code`). Fixed §1 mixed status ("LIVE + TARGET" → "LIVE"). |

---

**Status:** DRAFT — Review Required  
**Owner:** Backend Architecture Team  
**Reviewers:** Tech Lead, Backend Developer  
**Last Updated:** 2026-07-01 (v1.5)
