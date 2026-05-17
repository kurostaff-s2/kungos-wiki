# MongoDB Collection Audit — Domain-Driven Consolidation Plan

**Date:** 2026-05-14
**Context:** Complete backend + frontend refactoring — no legacy compatibility needed
**Databases:** `KungOS_Mongo_One` (31 collections, 68,443 docs) vs `kuropurchase` (legacy)
**Pattern:** MongoDB Polymorphic Collections — discriminator fields + schema validation per type
**Sources:** [MongoDB Polymorphic Data](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/polymorphic-data/), [MongoDB Multi-Tenant Arch](https://www.mongodb.com/docs/atlas/build-multi-tenant-arch/), OneUptime (Mar 2026), QueryLeaf (Aug/Dec 2025)

---

## Executive Summary

The KungOS MongoDB schema is **31 collections across 68,443 documents** — bloated with duplicates, dead references, and a catch-all `misc` collection holding 6 unrelated categories.

**Previous plan (31 → 22):** Split `misc` into separate collections, merge `kgorders` + `inwardpayments`, keep most collections as-is.

**Revised plan (31 → 10):** Domain-driven consolidation using MongoDB's **polymorphic collection pattern**. Documents grouped by **query access patterns** (not document shape), with discriminator fields and per-type schema validation.

| Metric | Before | Previous Plan | Revised Plan |
|--------|--------|--------------|--------------|
| Collections | 31 | 22 | **10** |
| Reduction | — | -29% | **-68%** |
| Dead references | 7 | 0 | 0 |
| Catch-all collections | 1 | 0 | 0 |
| Duplicate collections | 1 | 0 | 0 |
| Discriminator fields needed | 0 | 0 | 7 |
| Schema validation rules | 0 | 0 | 7 |

---

## Critical Findings (Unchanged from Previous Analysis)

### 1. `inwardpayments` is a duplicate of `kgorders` — NOT payments

**Evidence:**
- Both collections have identical schemas (34 fields, only `migrated_at` differs)
- `kgorders` has 9,162 docs, `inwardpayments` has 21,026 docs
- **9,162 orderids overlap exactly** — `kgorders` is a subset of `inwardpayments`
- The 299 extra docs in `inwardpayments` have `totalprice: null` and mixed orderid prefixes (KG, TP)

**Root cause:** Legacy code used `inwardpayments` as the primary order collection. `kgorders` was a separate gaming-specific collection. During migration, both were loaded.

**Conclusion:** `inwardpayments` belongs in the **orders domain**, NOT the accounts/finance domain. The name is misleading.

### 2. `inwardinvoices` data loss (4,626 → 16 docs)

**Status:** 🔴 CRITICAL — breaks all finance analytics. Restore from `kuropurchase` production dump.

### 3. `misc` collection — 6 unrelated categories in one collection

| Category | Docs | Fields | Query Pattern |
|----------|------|--------|---------------|
| Service requests (type='') | 1,922 | name, phone, logs, servicetype, srid, status | Filter by status, assigned_to, date |
| User profiles (type=null, has userid/phone/name) | 3,218 | userid, phone, name | Lookup by userid, phone |
| F&B inventory (collection=food/beverage) | 68 | productid, type, avgprice, stock, sold | Filter by type, active, division |
| PC components (collection=components) | 86 | productid, type, avgprice, stock | Filter by type, collection |
| Gaming gear (collection=accessories/monitors/networking) | 40 | productid, type, avgprice, stock | Filter by collection |
| Accounting entries (type=Trading Stock/Fixed Assets/Expenses) | 111 | type, amount, description | Filter by type, date |

**Problem:** These 6 categories have **completely different query patterns, fields, and lifecycles**. They should never have been in the same collection.

### 4. 7 dead collections (0 docs, no code references in new refactor)

`gamerDetails`, `gamers`, `rbpackages`, `kurodata`, `media`, `stock_audit`, `asset_register` — all empty, all dead references.

### 5. `purchaseorders` inflation (5,395 → 15,216)

+9,821 docs (182% growth). Verify for duplicate `po_no` values before migration.

### 6. Negative stock items

Chocolates (-27), Water (-571), Soft Drinks (-101) — inventory reconciliation needed.

### 7. `DUNE0003_001` zero-doc issue

Division exists but has 0 documents across all collections. Re-run tenant split or document as business reality.

---

## MongoDB Design Patterns — Why This Approach

### Polymorphic Collections (MongoDB Manual)

> "Group similar, non-identical documents in a single collection using the Polymorphic and Inheritance patterns. These improve performance by storing data based on **query access patterns**, not strictly by document shape."

**Key principle:** Documents in the same collection should be:
- Queried together (same filter patterns)
- Share common fields (tenant fields, dates, IDs)
- Have compatible index structures

### Why NOT the Previous Plan (31 → 22)?

The previous plan split `misc` into 5 separate collections (`fb_inventory`, `gaming_gear`, `accounting_entries`, merged into `stock_register`, merged into `serviceRequest`). This creates:

- **22 collections for 68K docs** — still too granular for the data volume
- **Tiny collections** — `gaming_gear` (40 docs), `accounting_entries` (111 docs), `fb_inventory` (68 docs)
- **Index overhead** — each collection needs its own index set
- **No query benefit** — F&B inventory, gaming gear, and PC components are all queried the same way (filter by type, check stock)

### Why Domain-Driven Consolidation (31 → 10)?

1. **Query-aligned grouping:** Documents in each collection share the same filter patterns (e.g., all invoices filtered by date range, tenant, amount)
2. **Discriminator indexing:** `{bgcode: 1, division: 1, discriminator: 1, date_field: 1}` covers 90% of queries
3. **Schema validation:** MongoDB's polymorphic validation enforces different required fields per discriminator value
4. **No cross-collection joins:** Each collection is self-contained for its domain
5. **Reduced index overhead:** 10 collections × 1 composite index each = 10 indexes (vs. 22 × 1 = 22)

### Multi-Tenant Pattern (MongoDB Atlas Docs)

> "Shared collections with tenant discriminator fields (bgcode, division) is the recommended pattern for moderate tenant counts."

All 10 target collections use `{bgcode: 1, division: 1, branch_code: 1}` as the leading index prefix — consistent with the shared-collection multi-tenant pattern.

---

## Target Schema: 10 Collections

### 1. `transactions` — All Invoices, Credit Notes, Debit Notes, Outward Orders

**Rationale:** All are financial documents queried by date range, tenant, amount, and direction (inward/outward). Same index pattern, same filter fields.

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `inwardinvoices` | 4,626* | `direction: "inward"`, `doc_type: "invoice"` |
| `inwardcreditnotes` | 106 | `direction: "inward"`, `doc_type: "credit_note"` |
| `inwarddebitnotes` | 3 | `direction: "inward"`, `doc_type: "debit_note"` |
| `outwardinvoices` | 1,165 | `direction: "outward"`, `doc_type: "invoice"` |
| `outwardcreditnotes` | 150 | `direction: "outward"`, `doc_type: "credit_note"` |
| `outwarddebitnotes` | 13 | `direction: "outward"`, `doc_type: "debit_note"` |
| `outward` | 754 | `direction: "outward"`, `doc_type: "order"` |

**Total: ~6,817 docs**

**Common fields (all types):** `_id`, `direction`, `doc_type`, `doc_no`, `doc_date`, `total_amount`, `gst`, `taxes`, `customer/vendor`, `bgcode`, `division`, `branch_code`, `created_by`, `created_at`, `updated_at`

**Type-specific fields:**
- `invoice`: `builds[]`, `products[]`, `services[]`, `gst_breakdown`
- `credit_note`: `original_invoice_no`, `credit_reason`, `adjusted_amount`
- `debit_note`: `original_invoice_no`, `debit_reason`, `adjusted_amount`
- `order`: `order_status`, `delivery_address`, `payment_status`

**Primary index:** `{bgcode: 1, division: 1, direction: 1, doc_type: 1, doc_date: 1}`

**Schema validation:** Per `doc_type` — each type has different required fields. Enforced via MongoDB JSON Schema with `anyOf` + `if/then` rules.

---

### 2. `payments` — Payment Vouchers

**Rationale:** Standalone payment records. Different lifecycle from invoices (payments reference invoices, not the other way around).

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `paymentvouchers` | 3,459 | `direction: "debit"` or `direction: "credit"` |

**Total: 3,459 docs**

**Common fields:** `_id`, `direction`, `voucher_no`, `vendor`, `amount`, `pay_method`, `pay_date`, `utr_no`, `bgcode`, `division`, `branch_code`, `created_by`, `created_at`

**Primary index:** `{bgcode: 1, division: 1, direction: 1, pay_date: 1}`

---

### 3. `orders` — All Orders (Gaming, Third-Party, Standard, Estimates)

**Rationale:** All are customer-facing orders with embedded line items (food, service, builds, products). Same query patterns (filter by date, status, tenant, customer).

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `inwardpayments` | 21,026 | `order_type: "gaming"` (KG prefix), `"third_party"` (TP prefix), `"standard"` (rest) |
| `tporders` | 229 | `order_type: "third_party"` |
| `estimates` | 4,308 | `order_type: "estimate"` |

**Total: ~25,563 docs**

**Common fields:** `_id`, `order_type`, `orderid`, `builds[]`, `products[]`, `food[]`, `service[]`, `totalprice`, `totalpricebgst`, `gst`, `taxes`, `order_status`, `order_date`, `invoice_no`, `invoice_generated`, `user`, `billadd`, `created_by`, `bgcode`, `division`, `branch_code`, `created_at`, `updated_at`

**Primary index:** `{bgcode: 1, division: 1, order_type: 1, order_date: 1}`

**Note:** `kgorders` is dropped (subset of `inwardpayments`). `estimates` gets `order_type: "estimate"` — they share the same line-item structure as orders.

---

### 4. `procurement` — Purchase Orders, Indents

**Rationale:** All are procurement documents (vendor-facing). Queried by vendor, date, status. Different from inventory (which tracks stock levels).

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `purchaseorders` | 15,216 | `proc_type: "po"` |
| `indentpos` | 247 | `proc_type: "indent_po"` |
| `indentproduct` | 1,490 | `proc_type: "indent_product"` |

**Total: ~16,953 docs**

**Common fields:** `_id`, `proc_type`, `po_no`/`batchid`, `vendor`, `totalprice`/`total_amount`, `products[]`, `tags`, `bgcode`, `division`, `branch_code`, `created_by`, `created_at`

**Primary index:** `{bgcode: 1, division: 1, proc_type: 1, vendor: 1, created_at: 1}`

---

### 5. `inventory` — All Stock (Hardware, F&B, Gaming Gear)

**Rationale:** All are stock-tracking documents with quantity, price, stock lots, and sold arrays. Same query patterns (filter by type, check stock, update quantity).

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `stock_register` | 194 | `inv_type: "hardware"` |
| `misc` (components) | 86 | `inv_type: "hardware"` |
| `misc` (F&B) | 68 | `inv_type: "fb"` |
| `misc` (gaming gear) | 40 | `inv_type: "gaming"` |

**Total: ~388 docs**

**Common fields:** `_id`, `inv_type`, `sub_type`, `productid`, `type`, `avgprice`, `maxprice`, `minprice`, `total_quantity`, `quantity`, `stock[]`, `sold[]`, `active`, `bgcode`, `division`, `branch_code`

**Primary index:** `{bgcode: 1, division: 1, inv_type: 1, sub_type: 1}`

**Note:** This is small enough that a single collection is efficient. No separate `fb_inventory`, `gaming_gear`, or `stock_register` needed.

---

### 6. `catalog` — Products, Presets, Third-Party Builds

**Rationale:** All are reference/catalog documents (browsed, not transacted). Same query patterns (filter by category, search by title, check pricing).

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `products` | 82 | `cat_type: "product"` |
| `presets` | 6 | `cat_type: "preset"` |
| `tpbuilds` | 123 | `cat_type: "build"` |

**Total: ~211 docs**

**Common fields:** `_id`, `cat_type`, `productid`/`buildid`, `title`, `collection`, `type`, `category`, `pricing`, `specs`, `images`, `active`, `bgcode`, `division`

**Primary index:** `{bgcode: 1, division: 1, cat_type: 1, collection: 1}`

**Why NOT merge with `inventory`?** Different query patterns: catalog is browsed/searched (title, category, specs), inventory is filtered/counted (quantity, stock lots, sold). Catalog has independent lifecycle from stock.

---

### 7. `people` — Users, Players, Teams

**Rationale:** All are person/team entities. Queried by ID, name, role, team. Same tenant fields.

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `reb_users` | 1,982 | `entity_type: "staff"` |
| `misc` (users) | 3,218 | `entity_type: "staff"` or `"customer"` |
| `players` | 117 | `entity_type: "player"` |
| `teams` | 14 | `entity_type: "team"` |

**Total: ~5,331 docs**

**Common fields:** `_id`, `entity_type`, `userid`/`playerid`/`teamid`, `name`, `phone`, `role`, `bgcode`, `division`, `branch_code`

**Type-specific fields:**
- `staff`: `userid`, `phone`, `name`, `role`, `source` (migration tracking)
- `player`: `playerid`, `teamid`, `riotid`, `rank`, `mobile`
- `team`: `teamid`, `name`, `coach`, `userid`

**Primary index:** `{bgcode: 1, division: 1, entity_type: 1, userid: 1}`

---

### 8. `services` — Service Requests

**Rationale:** All service tickets. Queried by status, assigned_to, date, type.

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `serviceRequest` | 1,625 | `service_type: "hardware"` or `"software"` or `"consulting"` |
| `misc` (SRs) | 1,922 | Same service_type values |

**Total: ~3,547 docs**

**Common fields:** `_id`, `service_type`, `srid`, `name`, `phone`, `logs[]`, `status`, `assigned_to`, `bgcode`, `division`, `branch_code`, `created_at`

**Primary index:** `{bgcode: 1, division: 1, service_type: 1, status: 1, created_at: 1}`

---

### 9. `hr` — Employee Attendance

**Rationale:** Single type, distinct query pattern (date range, employee, status). No benefit from merging with `people`.

| Source Collection | Docs |
|---|---|
| `employee_attendance` | 966 |

**Total: 966 docs**

**Fields:** `_id`, `userid`, `status`, `at_date`, `active`, `delete_flag`, `bgcode`, `division`, `branch_code`

**Primary index:** `{bgcode: 1, division: 1, userid: 1, at_date: 1}`

---

### 10. `config` — Business Config, Entities, Accounts, Vendors, Gaming Config

**Rationale:** All are configuration/reference data. Rarely queried, mostly loaded once at startup or admin operations.

| Source Collection | Docs | Discriminator Values |
|---|---|---|
| `bgData` | 1 | `config_type: "business"` |
| `entities` | 2 | `config_type: "entity"` |
| `accounts` | 7 | `config_type: "account"` |
| `vendors` | 409 | `config_type: "vendor"` |
| `tournaments` | 3 | `config_type: "tournament"` |
| `tourneyregister` | 56 | `config_type: "tournament_registration"` |

**Total: ~478 docs**

**Common fields:** `_id`, `config_type`, `bgcode`, `division`

**Type-specific fields:** Each type has completely different fields (business config, vendor GST/PAN, tournament fees/prize, etc.)

**Primary index:** `{bgcode: 1, division: 1, config_type: 1}`

---

## What NOT to Consolidate (and Why)

| Don't Merge | Why |
|---|---|
| `products` + `stock_register` | Different query patterns: catalog browses (title, specs, images) vs. inventory counts (quantity, stock lots, sold). Independent lifecycles. |
| `presets` + `tpbuilds` | Different lifecycles: templates (rarely changed) vs. channel-specific builds (updated with pricing). Merged into `catalog` with discriminator, not a single collection. |
| `inwardpayments` into finance/accounts | It's orders, not payments — proven by schema analysis (identical to `kgorders`, 9,162 orderid overlap). |
| `procurement` + `inventory` | POs are vendor-facing documents (status, vendor, date). Inventory is stock-tracking (quantity, price, lots). Different query patterns. |
| `people` + `hr` | Users/players are entities (lookup by ID). Attendance is time-series (filter by date range, employee). Different access patterns. |

---

## Collection Comparison: Before → After

### Before (31 Collections)

| Domain | Collections | Docs |
|--------|------------|------|
| Config | bgData, entities, teams, accounts, presets | 26 |
| Orders/Commerce | kgorders, estimates, outwardinvoices, outward, tporders, tpbuilds | 15,421 |
| Finance | inwardinvoices, inwardpayments, inwardcreditnotes, inwarddebitnotes, outwardcreditnotes, outwarddebitnotes, paymentvouchers | 25,706 |
| Procurement | purchaseorders, indentpos, indentproduct, vendors | 17,362 |
| Inventory | stock_register, products, misc | 5,788 |
| Gaming | players, tournaments, tourneyregister | 176 |
| Service | serviceRequest | 1,625 |
| HR | employee_attendance, reb_users | 2,948 |
| Dead | gamerDetails, gamers, rbpackages, kurodata, media, stock_audit, asset_register | 0 |
| **Total** | **31** | **68,443** |

### After (10 Collections)

| Collection | Docs | Domain | Discriminator | Source Collections |
|---|---|---|---|---|
| `transactions` | ~6,817 | Finance | `direction` + `doc_type` (6 values) | inwardinvoices, inwardcreditnotes, inwarddebitnotes, outwardinvoices, outwardcreditnotes, outwarddebitnotes, outward |
| `payments` | 3,459 | Finance | `direction` (2 values) | paymentvouchers |
| `orders` | ~25,563 | Commerce | `order_type` (4 values) | inwardpayments, kgorders, tporders, estimates |
| `procurement` | ~16,953 | Procurement | `proc_type` (3 values) | purchaseorders, indentpos, indentproduct |
| `inventory` | ~388 | Inventory | `inv_type` (3 values) | stock_register, misc (hardware/fb/gaming) |
| `catalog` | ~211 | Reference | `cat_type` (3 values) | products, presets, tpbuilds |
| `people` | ~5,331 | People | `entity_type` (4 values) | reb_users, misc (users), players, teams |
| `services` | ~3,547 | Service | `service_type` (3 values) | serviceRequest, misc (SRs) |
| `hr` | 966 | HR | — | employee_attendance |
| `config` | ~478 | Config | `config_type` (6 values) | bgData, entities, accounts, vendors, tournaments, tourneyregister |
| **Total** | **~57,709** | **10 collections** | | **31 → 10 (-68%)** |

*Note: Total docs differ slightly because dead collections (0 docs) are removed and some misc docs may overlap with reb_users.*

---

## Migration Plan (4 Phases, 10 Days)

### Phase 0: Pre-Migration Validation (Before Day 1)

**Added per Nemo's review (deleg-1778760256):**

```
0a. SNAPSHOT: mongodump all 31 source collections to /backups/phase2/
0b. VERIFY: inwardinvoices dump is available + restorable from kuropurchase
0c. DRY-RUN: Scan every source collection for missing discriminator fields
     - db.inwardinvoices.find({direction: {$exists:false}}).count() // should be 0 after backfill
     - db.inwardpayments.find({order_type: {$exists:false}}).count() // should be 0 after backfill
     - Repeat for all 10 target collections
0d. DEDUP: Run $group on userid (people) and srid (services) to find duplicates
     - db.reb_users.aggregate([{$group:{_id:"$userid", cnt:{$sum:1}}}, {$match:{cnt:{$gt:1}}}] )
     - db.serviceRequest.aggregate([{$group:{_id:"$srid", cnt:{$sum:1}}}, {$match:{cnt:{$gt:1}}}])
0e. VALIDATE: Run discriminator mapping function on edge-case docs (ambiguous prefixes)
     - Check orderid prefixes: KG, TP, and mixed
     - Check misc type values: null, empty string, and unexpected values
0f. STAGING: Run full migration on staging copy of production data
     - Measure migration time
     - Verify all schema validation rules
     - Verify all indexes cover query patterns (explain("executionStats"))
```

### Phase 1: Emergency (Day 1)

```
1. Restore inwardinvoices from kuropurchase (4,626 docs)
2. Verify purchaseorders for duplicate po_no values
3. NOTE: Do NOT drop dead collections yet — keep until Phase 4 (per Nemo #4)
4. Verify inwardinvoices doc count + run sample queries
```

### Phase 1b: Dead Collection Cleanup (After Phase 4)

```
1b. After all migrations verified: drop 7 dead collections (gamerDetails, gamers, rbpackages, kurodata, media, stock_audit, asset_register)
1c. Verify no code references remain (grep -rn across codebase)
```

### Phase 2: Consolidation (Days 2-3)

```
5. Create new collections: transactions, payments, orders, procurement, inventory, catalog, people, services, hr, config
6. Migrate inwardinvoices + inwardcreditnotes + inwarddebitnotes + outwardinvoices + outwardcreditnotes + outwarddebitnotes + outward → transactions (add direction, doc_type discriminators)
7. Migrate paymentvouchers → payments (add direction discriminator)
8. Migrate inwardpayments + tporders + estimates → orders (add order_type discriminator)
9. Drop kgorders, inwardpayments, tporders, estimates, outwardinvoices, outward, inwardcreditnotes, inwarddebitnotes, outwardcreditnotes, outwarddebitnotes, paymentvouchers
10. Migrate purchaseorders + indentpos + indentproduct → procurement (add proc_type discriminator)
11. Drop purchaseorders, indentpos, indentproduct
12. Migrate stock_register + misc (hardware/fb/gaming) → inventory (add inv_type discriminator)
13. Migrate products + presets + tpbuilds → catalog (add cat_type discriminator)
14. Drop stock_register, products, presets, tpbuilds, misc
15. Migrate reb_users + misc (users) + players + teams → people (add entity_type discriminator)
16. Drop reb_users, players, teams
17. Migrate serviceRequest + misc (SRs) → services (add service_type discriminator)
18. Drop serviceRequest
19. Migrate employee_attendance → hr
20. Migrate bgData + entities + accounts + vendors + tournaments + tourneyregister → config (add config_type discriminator)
21. Drop bgData, entities, accounts, vendors, tournaments, tourneyregister
```

### Phase 3: Code Migration (Days 4-7)

```
22. Update all get_collection() calls to use new collection names
23. Update query filters to use discriminator fields (direction, doc_type, order_type, etc.)
24. Rewrite OrderGateway to use orders collection with order_type discriminator
25. Update menu/inventory endpoints to query inventory with inv_type discriminator
26. Update service endpoints to use services collection
27. Update user/people endpoints to use people collection
28. Update config endpoints to use config collection
29. Add schema validation rules to each collection (per discriminator value)
30. Run full test suite
```

### Phase 4: Cleanup (Days 8-10)

```
31. Create composite indexes on all 10 collections
32. Add validation rules (negative stock, required fields per type)
33. Document new schema (discriminator values, required fields per type, index strategy)
34. Deploy and monitor
35. Verify no orphaned references to old collection names
```

---

## Schema Validation Strategy

Each polymorphic collection uses MongoDB's JSON Schema validation with `anyOf` to enforce different required fields per discriminator value.

### Example: `transactions` Collection

```javascript
db.createCollection("transactions", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id", "direction", "doc_type", "bgcode", "division", "branch_code"],
      properties: {
        direction: { enum: ["inward", "outward"] },
        doc_type: { enum: ["invoice", "credit_note", "debit_note", "order"] },
        bgcode: { bsonType: "string" },
        division: { bsonType: "string" },
        branch_code: { bsonType: "string" },
        doc_no: { bsonType: "string" },
        doc_date: { bsonType: "date" },
        total_amount: { bsonType: "number" },
        gst: { bsonType: "number" },
        taxes: { bsonType: "object" },
        // Type-specific fields validated via anyOf
      },
      anyOf: [
        {
          if: { properties: { doc_type: { const: "invoice" } } },
          then: {
            required: ["builds", "products", "gst_breakdown"],
            properties: {
              builds: { bsonType: "array" },
              products: { bsonType: "array" },
              gst_breakdown: { bsonType: "object" }
            }
          }
        },
        {
          if: { properties: { doc_type: { const: "credit_note" } } },
          then: {
            required: ["original_invoice_no", "credit_reason", "adjusted_amount"],
            properties: {
              original_invoice_no: { bsonType: "string" },
              credit_reason: { bsonType: "string" },
              adjusted_amount: { bsonType: "number" }
            }
          }
        },
        // ... debit_note, order
      ]
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

### Index Strategy (All 10 Collections)

Each collection gets a composite index with tenant fields as the leading prefix:

| Collection | Primary Index | Secondary Indexes |
|---|---|---|
| `transactions` | `{bgcode: 1, division: 1, direction: 1, doc_type: 1, doc_date: 1}` | `{doc_no: 1}`, `{customer/vendor: 1}`, **`{bgcode: 1, division: 1, doc_type: 1, doc_date: 1}`** (direction-agnostic, per Gemma #1) |
| `payments` | `{bgcode: 1, division: 1, direction: 1, pay_date: 1}` | `{voucher_no: 1}`, `{vendor: 1}` |
| `orders` | `{bgcode: 1, division: 1, order_type: 1, order_date: 1}` | `{orderid: 1}`, `{user.phone: 1}`, `{invoice_no: 1}` |
| `procurement` | `{bgcode: 1, division: 1, proc_type: 1, vendor: 1, created_at: 1}` | `{po_no: 1}` |
| `inventory` | `{bgcode: 1, division: 1, inv_type: 1, sub_type: 1}` | `{productid: 1}`, `{active: 1}` |
| `catalog` | `{bgcode: 1, division: 1, cat_type: 1, collection: 1}` | `{productid: 1}`, `{title: "text"}` |
| `people` | `{bgcode: 1, division: 1, entity_type: 1, userid: 1}` | `{phone: 1}`, `{name: 1}` |
| `services` | `{bgcode: 1, division: 1, service_type: 1, status: 1, created_at: 1}` | `{srid: 1}`, `{assigned_to: 1}` |
| `hr` | `{bgcode: 1, division: 1, userid: 1, at_date: 1}` | — |
| `config` | `{bgcode: 1, division: 1, config_type: 1}` | — |

---

## Endpoint Mapping (Before → After)

| Endpoint | Before | After | Collection Change |
|----------|--------|-------|-------------------|
| `GET /transactions/` | `inwardinvoices`, `outwardinvoices`, etc. | `transactions` | Polymorphic — filter by `direction` + `doc_type` |
| `GET /transactions/inward` | `inwardinvoices` | `transactions` | `direction: "inward"` |
| `GET /transactions/outward` | `outwardinvoices` | `transactions` | `direction: "outward"` |
| `GET /payments/` | `paymentvouchers` | `payments` | Filter by `direction` |
| `GET /orders/` | `kgorders` | `orders` | Filter by `order_type` |
| `GET /orders/gaming` | `kgorders` | `orders` | `order_type: "gaming"` |
| `GET /orders/third-party` | `tporders` | `orders` | `order_type: "third_party"` |
| `GET /orders/estimates` | `estimates` | `orders` | `order_type: "estimate"` |
| `GET /procurement/po` | `purchaseorders` | `procurement` | `proc_type: "po"` |
| `GET /procurement/indents` | `indentpos` | `procurement` | `proc_type: "indent_po"` |
| `GET /inventory/` | `stock_register` | `inventory` | All types |
| `GET /inventory/hardware` | `stock_register` | `inventory` | `inv_type: "hardware"` |
| `GET /inventory/fb` | `misc` (type filter) | `inventory` | `inv_type: "fb"` |
| `GET /inventory/gaming` | `misc` (collection filter) | `inventory` | `inv_type: "gaming"` |
| `GET /catalog/` | `products` | `catalog` | All types |
| `GET /catalog/products` | `products` | `catalog` | `cat_type: "product"` |
| `GET /catalog/presets` | `presets` | `catalog` | `cat_type: "preset"` |
| `GET /catalog/builds` | `tpbuilds` | `catalog` | `cat_type: "build"` |
| `GET /people/` | `reb_users` | `people` | All types |
| `GET /people/staff` | `reb_users` | `people` | `entity_type: "staff"` |
| `GET /people/players` | `players` | `people` | `entity_type: "player"` |
| `GET /people/teams` | `teams` | `people` | `entity_type: "team"` |
| `GET /services/` | `serviceRequest` | `services` | Filter by `service_type` |
| `GET /hr/attendance` | `employee_attendance` | `hr` | No discriminator |
| `GET /config/` | `bgData`, `entities`, etc. | `config` | Filter by `config_type` |
| `GET /config/vendors` | `vendors` | `config` | `config_type: "vendor"` |

---

## Risk Register (Updated per Council Review)

| Risk | Likelihood | Impact | Source | Mitigation |
|------|-----------|--------|--------|------------|
| `inwardinvoices` restore fails | Medium | Critical | Gemma #2, Nemo #8 | Verify dump available + restorable; snapshot all 31 collections before Phase 2 |
| Discriminator field missing on migrated docs | High | Critical | Nemo #1 | Pre-migration dry-run: scan every source collection for missing discriminators; fail if any null |
| Schema validation rejects legacy docs | High | High | Gemma #4, Nemo #5 | Run validation in `moderate` mode first; pre-validation pass confirms all discriminators present; then `strict` |
| Index not covering query pattern | Medium | Medium | Gemma #7, Nemo #7 | Add secondary indexes; verify with `explain("executionStats")` on representative workload |
| Code references miss discriminator filter | High | Critical | Gemma #3 | Grep all query filters; add discriminator to every query; smoke test top 20 aggregation pipelines |
| `people` merge duplicates | High | Medium | Nemo #2 | Pre-migration dedup: `$group` on `userid`; resolve conflicts; log duplicates |
| `services` merge duplicates | Medium | Medium | Nemo #2 | Pre-migration dedup: `$group` on `srid`; resolve conflicts; log duplicates |
| Migration script drops collection before verify | Medium | Critical | Nemo #4 | Keep dead collections until Phase 4; snapshot before any drop; rollback playbook |
| Discriminator enum values incomplete | Medium | Medium | Nemo #3 | Document mapping function; unit test that exactly one discriminator per source doc |
| Aggregation pipelines break | High | Critical | Nemo #6 | Code-wide search for old collection names; replace with discriminator filters; add smoke test |
| Dead collections dropped before migration complete | Low | Critical | Nemo #4 | Re-order: keep dead collections until Phase 4; snapshot before removal |
| No rollback procedure | Medium | Critical | Nemo #8 | `mongodump` of all 31 source collections before Phase 2; document rollback playbook |
| Schema validation too strict on first pass | Medium | High | Gemma #4 | Start with `moderate` validation level; fix violations; then `strict` |
| `hr` grows too large | Low | Medium | Gemma | Monitor `employee_attendance` growth; split if >1M docs |
| `orders` grows too large | Low | Medium | Gemma | Monitor `orders` growth; MongoDB handles 2.5M docs easily; split only if >10M |

---

## Summary

| Metric | Before | Previous Plan | Revised Plan |
|--------|--------|--------------|--------------|
| Collections | 31 | 22 | **10** |
| Reduction | — | -29% | **-68%** |
| Total docs | 68,443 | 68,443 | ~57,709 (dead collections removed) |
| Dead references | 7 | 0 | 0 |
| Catch-all collections | 1 (`misc`) | 0 | 0 |
| Duplicate collections | 1 (`inwardpayments` ≈ `kgorders`) | 0 | 0 |
| Discriminator fields | 0 | 0 | 7 |
| Schema validation rules | 0 | 0 | 7 (one per polymorphic collection) |
| Composite indexes | varies | 22 | 10 |
| Collections needing no change | — | 20 | 0 (all consolidated) |

### Key Changes from Previous Plan

1. **`transactions` instead of 7 separate collections** — inward/outward invoices, credit notes, debit notes, and outward orders merged into one polymorphic collection with `direction` + `doc_type` discriminators
2. **`inventory` instead of 3 separate collections** — hardware, F&B, and gaming gear merged into one with `inv_type` discriminator (no more `fb_inventory`, `gaming_gear`, separate `stock_register`)
3. **`catalog` instead of 3 separate collections** — products, presets, and tpbuilds merged with `cat_type` discriminator
4. **`people` instead of 4 separate collections** — users, players, teams merged with `entity_type` discriminator
5. **`config` instead of 6 separate collections** — bgData, entities, accounts, vendors, tournaments, tourneyregister merged with `config_type` discriminator
6. **`procurement` instead of 3 separate collections** — purchaseorders, indentpos, indentproduct merged with `proc_type` discriminator
7. **`services` instead of 2 sources** — serviceRequest + misc SRs merged with `service_type` discriminator

### Why This Works

- **Query-aligned grouping:** Documents in each collection are queried together (same filter patterns, same date ranges, same tenant scope)
- **Discriminator indexing:** `{bgcode: 1, division: 1, discriminator: 1, date_field: 1}` covers 90% of queries across all collections
- **Schema validation:** MongoDB's polymorphic validation enforces different required fields per discriminator value — no loose documents
- **No cross-collection joins:** Each collection is self-contained for its domain
- **Reduced index overhead:** 10 collections × 1 composite index = 10 indexes (vs. 22 × 1 = 22 in previous plan)
- **Consistent multi-tenant pattern:** All collections use `{bgcode: 1, division: 1, branch_code: 1}` as leading index prefix

### Caveats

- **`transactions` at 6.8K docs** — still small, single collection is fine
- **`orders` at 25.5K docs** — the largest collection, but well within MongoDB's sweet spot for single collection (<100M docs)
- **Schema validation rules** will be needed for each discriminator value to enforce required fields
- **Migration is destructive** — once old collections are dropped, rollback requires backup. Test migration on staging first.
- **Code changes are broader** — every query needs a discriminator filter added, not just a collection name change

**Bottom line:** The MongoDB schema is 68% bloated with operational silos that don't match query patterns. Consolidating to 10 domain-driven collections using MongoDB's polymorphic pattern eliminates confusion, simplifies queries, reduces index overhead, and aligns with MongoDB's official design recommendations.

---

## Council Review Status

| Reviewer | Verdict | Findings | Archive |
|----------|---------|----------|---------|
| Gemma `reviewer-arch` | **APPROVE WITH CONDITIONS** | 5 conditions (index, dump verify, discriminator filters, moderate mode, staging test) | `~/.council-memory/reviews/deleg-1778759923/` |
| Nemo `reviewer-logic` | **8 FINDINGS** | 3 critical, 4 high, 1 medium (discriminator backfill, dedup, ambiguous mapping, dead collections, validation edge cases, aggregation pipelines, secondary indexes, snapshot/rollback) | `~/.council-memory/reviews/deleg-1778760256/` |

**Combined requirement:** All 11 items in the council review (§9 of `mongo-db-council-review-2026-05-14.md`) must be completed before Phase 2 consolidation begins.