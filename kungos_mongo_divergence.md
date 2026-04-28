# KungOS MongoDB Divergence: Spec vs. Reality

**Database:** `KungOS_Mongo_One` (underscores, not camelCase)  
**Spec Source:** [`KungOS_v2.md`](./KungOS_v2.md) + [`kungos-cafe-platform.md`](./kungos-cafe-platform.md)  
**Verified:** 2026-04-28

---

## TL;DR

The MongoDB database has **diverged significantly from the spec** in three major ways:

1. **13/13 gaming collections are missing** — the kuro-gaming-dj-backend (5 apps, 12+ collections, 25 endpoints) has NOT been merged into kteam-dj-chief. The `products` DB that held this data no longer exists, and the collections were never migrated to `KungOS_Mongo_One`.
2. **The database name is wrong in the spec** — spec references `kuropurchase` as the MongoDB name; reality is `KungOS_Mongo_One`.
3. **The cafe platform moved to PostgreSQL** — `gamers`, `stations`, `cafepayments` were planned as MongoDB collections but implemented as `caf_platform_*` PG tables instead.

---

## 1. Database Name

| Spec | Reality |
|---|---|
| `kuropurchase` (mentioned in migration tools section) | `KungOS_Mongo_One` |

The spec says: *"Parse MongoDB 8.0+ concurrent dump, restore with entity population"* into `kuropurchase`. All actual code, management commands, and migrations use `KungOS_Mongo_One`. The `kuropurchase` name exists only in the management command help text and docs.

---

## 2. Gaming Collections — ALL MISSING

The spec calls for **13 gaming MongoDB collections** to be added to `KungOS_Mongo_One` as part of the kuro-gaming-dj-backend integration:

### Spec vs. Reality

| # | Spec Collection | Spec DB | Actual Status | Docs |
|---|---|---|---|---|
| 1 | `prods` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 2 | `builds` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 3 | `kgbuilds` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 4 | `custombuilds` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 5 | `components` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 6 | `accessories` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 7 | `monitors` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 8 | `networking` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 9 | `external` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 10 | `games` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 11 | `kurodata` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 12 | `lists` | KungOS_Mongo_One | ❌ **MISSING** | — |
| 13 | `presets` | KungOS_Mongo_One | ✅ **EXISTS** | 6 |

**Result: 12/13 gaming collections missing (92%). Only `presets` exists.**

### Root Cause

The kuro-gaming-dj-backend codebase exists at `/home/chief/Coding-Projects/kuro-gaming-dj-backend` but:
- None of the 5 gaming apps (`accounts`, `products`, `orders`, `payment`, `games`) are in `INSTALLED_APPS`
- No gaming PostgreSQL models (`Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems`) exist in the PG database
- The separate `products` MongoDB database (which held the gaming data) no longer exists
- The gaming backend code still references `db["prods"]`, `db["builds"]`, `db["kgbuilds"]`, etc. — but these collections don't exist in any database
- Gaming views reference 13 collection names via variables: `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `presets`, `kurodata`, `lists`, `tempproducts`

### What the Gaming Code Expects

The kuro-gaming-dj-backend products views reference these collections:

```python
# products/views.py
build_collection = 'builds'
kgbuild_collection = 'kgbuilds'
prod_collection = 'prods'
custombuild_collection = 'custombuilds'
comp_collection = 'components'
accessory_collection = 'accessories'
monitor_collection = 'monitors'
networking_collection = 'networking'
external_collection = 'external'

# kuroadmin/views.py
preset_collection = 'presets'
misc_collection = 'misc'
kurodata_collection = 'kurodata'
tempprod_collection = 'tempproducts'
```

Plus `lists` (referenced directly as `db['lists']`) and `games` (games app).

---

## 3. Cafe Platform — MongoDB → PostgreSQL Migration

The spec planned these as MongoDB collections but they were implemented as PostgreSQL tables instead:

| Spec Collection | Actual Implementation | Status |
|---|---|---|
| `gamers` | `caf_platform_sessions` (PG), `caf_platform_users` (PG) | ✅ Implemented in PG |
| `cafepayments` | `caf_platform_wallet_transactions` (PG) | ✅ Implemented in PG |
| `stations` | `caf_platform_stations` (PG) | ✅ Implemented in PG |
| `game_library` | `caf_platform_games` (PG) | ✅ Implemented in PG |
| `wallets` | `caf_platform_wallets` (PG) | ✅ Implemented in PG |
| `price_plans` | `caf_platform_price_plans` (PG) | ✅ Implemented in PG |
| `member_plans` | `caf_platform_member_plans` (PG) | ✅ Implemented in PG |
| `cafes` | `caf_platform_cafes` (PG) | ✅ Implemented in PG |

This is a **positive divergence** — the cafe platform was correctly moved to PostgreSQL for relational integrity (FKs, transactions, complex queries).

---

## 4. Existing Collections — What's Actually There

### Legacy Collections (Pre-Consolidation)

| Collection | Docs | Tenant Fields | Notes |
|---|---|---|---|
| `purchaseorders` | 15,216 | bgcode ✅ entity ✅ branch ✅ | ~99.96% kurogaming |
| `inwardpayments` | 21,026 | bgcode ✅ entity ✅ branch ✅ | ~81% rebellion |
| `estimates` | 4,308 | bgcode ✅ entity ✅ branch ✅ | 100% kurogaming |
| `inwardInvoices` | 16 | — | No tenant fields |
| `outwardDebitNotes` | 13 | — | No tenant fields |
| `misc` | 5,512 | bgcode ✅ entity ✅ branch ✅ | Mixed entity |
| `products` | 82 | bgcode ✅ entity ✅ branch ✅ | Retail products |
| `accounts` | 7 | bgcode ✅ entity ✅ branch ✅ | 100% kurogaming |
| `players` | 117 | bgcode ✅ entity ✅ branch ✅ | Esports players |
| `tournaments` | 3 | bgcode ✅ entity ✅ branch ✅ | Esports tournaments |
| `reb_users` | 1,982 | bgcode ✅ entity ✅ branch ✅ | Rebellion users |
| `kgorders` | 9,162 | — | Kuro Gaming orders (no tenant fields) |
| `tporders` | 229 | — | TP orders |
| `tpbuilds` | 123 | — | TP builds |
| `serviceRequest` | 1,625 | — | Service requests |
| `outward` | 754 | — | Outward docs |
| `outwardInvoices` | 1,165 | — | Outward invoices |
| `outwardCreditNotes` | 150 | — | Outward credit notes |
| `paymentVouchers` | 3,459 | — | Payment vouchers |
| `stock_register` | 194 | — | Stock register |
| `indentpos` | 247 | — | Indent positions |
| `indentproduct` | 1,490 | — | Indent products |
| `employee_attendance` | 966 | — | Employee attendance |
| `vendors` | 409 | — | Vendor records |
| `teams` | 14 | — | Teams |
| `tourneyregister` | 56 | — | Tournament registrations |
| `bgData` | 1 | — | BG metadata |
| `inwardCreditNotes` | 106 | — | Inward credit notes |

**Total: 30 collections, 68,441 documents**

### Collections WITH Tenant Fields (10 collections, 49,356 docs)

All have `(bgcode, entity)` compound index. **Zero documents with null/empty bgcode.**

### Collections WITHOUT Tenant Fields (20 collections, 19,085 docs)

These legacy collections have NOT been migrated to include `bgcode`, `entity`, `branch` fields. They include:
- Order-related: `kgorders`, `tporders`, `tpbuilds`, `outward`, `outwardInvoices`, `outwardCreditNotes`
- Financial: `paymentVouchers`, `inwardpayments` (has tenant fields — wait, this does)
- Inventory: `stock_register`, `indentpos`, `indentproduct`
- Admin: `employee_attendance`, `vendors`, `teams`, `bgData`
- Service: `serviceRequest`, `tourneyregister`
- Other: `inwardInvoices`, `outwardDebitNotes`, `inwardCreditNotes`

---

## 5. What the Spec Says vs. What Exists

### Spec Claim: "12 MongoDB collections added to kuropurchase"

**Reality:** 0 of the 12 collections exist. The gaming backend was never merged.

### Spec Claim: "bgcode field to all 12 gaming MongoDB collections"

**Reality:** 0 gaming collections exist, so 0 have bgcode.

### Spec Claim: "5 gaming PostgreSQL models (Cart, Wishlist, Addresslist, Orders, OrderItems)"

**Reality:** 0 gaming PostgreSQL models exist. The kuro-gaming-dj-backend models (`Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems`) are defined in the separate repo but have NOT been integrated into kteam-dj-chief.

### Spec Claim: "consolidate MongoDB tenancy routing from per-BG databases to a single database"

**Reality:** Partially achieved. The single DB `KungOS_Mongo_One` exists and contains data from multiple entities. However:
- 20 of 30 collections still lack tenant fields
- Old per-BG routing code still exists in `backend/utils.py` (lines 288, 339)
- The `get_collection()` function still falls back to `client[bg.db_name]` for some callers

---

## 6. Impact Assessment

### Blocking Issues

| Issue | Impact | Fix Required |
|---|---|---|
| 12/13 gaming collections missing | **Gaming storefront cannot function** | Migrate gaming data from backup or source DB |
| Gaming apps not in INSTALLED_APPS | **No gaming API endpoints** | Add 5 apps to INSTALLED_APPS, create PG models |
| Per-BG routing still in utils.py | **Tenant isolation not fully enforced** | Replace `client[bg.db_name]` with `TenantCollection` |
| 20 collections lack tenant fields | **Tenant filtering incomplete** | Migrate legacy data to include bgcode/entity/branch |

### Non-Blocking

| Issue | Impact | Fix Required |
|---|---|---|
| DB name discrepancy (`kuropurchase` vs `KungOS_Mongo_One`) | Documentation only | Update spec docs |
| `tempproducts` collection referenced by gaming code | Would fail if gaming code runs | Create collection or remove reference |
| Missing `games` collection | Game catalog API would fail | Create collection during gaming integration |

---

## 7. Recommended Actions

### Phase 1 (Pre-Gaming Integration)

1. **Remove per-BG routing** in `backend/utils.py` lines 288, 339 — replace with `TenantCollection`
2. **Create missing tenant fields** on 20 legacy collections — add bgcode/entity/branch to `kgorders`, `tporders`, `tpbuilds`, `outward`, `outwardInvoices`, `outwardCreditNotes`, `paymentVouchers`, `stock_register`, `indentpos`, `indentproduct`, `employee_attendance`, `vendors`, `teams`, `serviceRequest`, `tourneyregister`, `inwardInvoices`, `outwardDebitNotes`, `inwardCreditNotes`, `bgData`
3. **Verify** all 30 collections have tenant fields and `(bgcode, entity)` indexes

### Phase 2 (Gaming Integration)

1. **Merge kuro-gaming-dj-backend** apps into kteam-dj-chief
2. **Create gaming PG models** (`Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems`)
3. **Migrate gaming collections** from backup/source to `KungOS_Mongo_One`
4. **Add bgcode/entity** to all 13 gaming collections
5. **Wire up** 25 gaming API endpoints
6. **Migrate** `kurogg-nextjs` frontend pages to `kteam-fe-chief`

### Phase 3 (Post-Merge)

1. **Retire** `kuro-gaming-dj-backend` repo
2. **Remove** `tempproducts` collection reference
3. **Verify** gaming collection counts match expected volumes
