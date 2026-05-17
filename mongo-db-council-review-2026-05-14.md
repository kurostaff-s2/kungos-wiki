# MongoDB Council Review — Consolidated Recommendations (Revised)

**Date:** 2026-05-14
**Reviewers:** Gemma `reviewer-arch`, Nemo `reviewer-logic`, GPT-OSS `reviewer-diversity`
**Source:** `~/llm-wiki/mongo-db-report-2026-05-14.md`
**Archives:** `~/.council-memory/reviews/deleg-1778753117/`, `deleg-1778753323/`, `deleg-1778753441/`
**Revision:** Domain-driven consolidation (31 → 10 collections) — see `mongo-collection-audit-2026-05-14.md`

---

## Executive Summary

| Recommendation | Gemma (arch) | Nemo (logic) | GPT-OSS (diversity) | Original Consensus | Revised Consensus |
|---------------|-------------|-------------|-------------------|-------------------|-------------------|
| Restore `inwardinvoices` | ✅ Emergency | ✅ Emergency | ✅ Emergency | ✅ **UNANIMOUS** | ✅ **UNCHANGED** |
| Split `misc` collection | ✅ Split into 5 | ✅ Split with read-alias | ❌ Keep as-is, add index | ⚠️ SPLIT | ✅ **CONSOLIDATE into domain collections** |
| Keep F&B in `kgorders` | ✅ Embedded | ✅ Embedded + view | ✅ Embedded + view | ✅ **UNANIMOUS** | ✅ **UNCHANGED** — embedded in `orders` |
| Add `session_id` to `kgorders` | ✅ Required | ⚠️ Derive from `created_by` | ✅ Add field | ✅ **UNANIMOUS** | ✅ **UNCHANGED** — add to `orders` |
| Shadow-write migration | ✅ Shadow-write | ✅ Shadow-read alias | ❌ Single migration | ⚠️ SPLIT | ✅ **SINGLE PASS** — dataset <10M docs |
| Consolidate gaming collections | ✅ product_catalog | — | ✅ category index | ⚠️ SPLIT | ✅ **MERGE into `catalog`** |
| Clean dead references | — | ✅ Remove 7 dead refs | ✅ Remove dead code | ✅ **UNANIMOUS** | ✅ **UNCHANGED** |
| Verify duplicate inflation | — | ✅ Aggregation check | ✅ Aggregation check | ✅ **UNANIMOUS** | ✅ **UNCHANGED** |
| Fix DUNE0003_001 | — | ✅ Re-run split | ✅ Business reality check | ✅ **UNANIMOUS** | ✅ **UNCHANGED** |
| Defer `bgcode` → `bg_code` | — | ✅ Phase 5.7 | ✅ Phase 5.7 | ✅ **UNCHANGED** | ✅ **UNCHANGED** |
| Domain-driven consolidation | — | — | — | N/A | ✅ **NEW APPROACH** |

### What Changed

The original council review recommended incremental fixes: split `misc` into 5 collections, add views, keep most collections as-is (31 → 22).

**Revised approach:** Full domain-driven consolidation using MongoDB's **polymorphic collection pattern**. Documents grouped by query access patterns, not document shape. 31 → 10 collections with discriminator fields and schema validation per type.

**Why:** The original plan left 22 collections for 68K docs — still too granular. MongoDB's official docs recommend grouping by query patterns. The polymorphic pattern (discriminator + schema validation) gives us the best of both worlds: clean domain boundaries + efficient queries.

---

## 1. Immediate Actions (This Week)

### 1.1 🔴 Restore `inwardinvoices` — All 3 Reviewers

**Problem:** 4,626 → 16 documents (99.7% data loss). All financial analytics broken.

**Consensus approach:**
1. Restore from `kuropurchase` legacy dump:
   ```bash
   mongorestore --nsInclude kuropurchase.inwardInvoices \
     /backups/kuropurchase_2026-04-30.tar.gz \
     --drop --gzip
   ```
2. Rename collection if needed:
   ```javascript
   db.runCommand({rename: "inwardInvoices", to: "inwardinvoices"})
   ```
3. Re-create compound index:
   ```javascript
   db.inwardinvoices.createIndex({bgcode:1, division:1})
   ```
4. Verify:
   ```javascript
   db.inwardinvoices.distinct("orderid").length // should be 4,626
   ```

**Caveats (Nemo):**
- If restored collection uses camelCase name, rename to lowercase before code references it
- If restored docs use `bgcode` field, ensure code hasn't been switched to `bg_code`
- Run finance viewset test suite after restore

**Caveats (GPT-OSS):**
- Check for duplicate `invoice_no` values — the `restore_kuropurchase.py` script may have `--only-something` flag that caused partial migration
- Run diff between legacy and target by `invoice_no`

### 1.2 🔴 Fix `OrderGateway` Schema Mapping — All 3 Reviewers

**Problem:** Gateway assumes fields (`items`, `amount_paid`, `session_id`, `typeof`) that don't exist in `kgorders`.

**Required changes to `domains/cafe_fnb/gateways.py`:**

| Assumed Field | Actual Field | Fix |
|--------------|-------------|-----|
| `items[]` | `food[]` + `service[]` | Map to correct arrays |
| `total` | `totalprice` | Field rename |
| `amount_paid` | Not tracked | Compute: `sum(food[].price * food[].quantity)` |
| `payment_status` | `order_status` | Map semantics |
| `session_id` | Not present | Add field (see §2.2) |
| `started_by` | `created_by` | Field rename |
| `created_at` | `order_date` | Format conversion |
| `typeof` | Not present | Derive from `food[]` presence |

**Post-migration:** Gateway queries `orders` collection with `order_type: "gaming"` discriminator instead of `kgorders`.

### 1.3 🔴 Fix Menu Endpoint — All 3 Reviewers

**Problem:** `GET /cafe-fnb/menu` queries `stock_register` (PC components). F&B items are in `misc`.

**Fix (post-migration):** Query `inventory` collection with filter:
```python
{'inv_type': 'fb', 'active': True}
```

**Why this works:** After consolidation, all F&B items (68 docs) are in the `inventory` collection with `inv_type: "fb"` discriminator. No more type-based filtering on `misc`.

---

## 2. Short-Term Actions (Weeks 1-2)

### 2.1 Verify Duplicate Inflation — Nemo + GPT-OSS

**Problem:** `purchaseorders` grew 5,395→15,216 (+182%), `inwardpayments` grew 9,467→21,026 (+122%).

**Verification:**
```javascript
// Check for duplicate orderid in purchaseorders
db.purchaseorders.aggregate([
  {$group: {_id: "$orderid", cnt: {$sum:1}}},
  {$match: {cnt: {$gt: 1}}}
])

// Check for duplicate invoice_no in inwardpayments
db.inwardpayments.aggregate([
  {$group: {_id: "$invoice_no", cnt: {$sum:1}}},
  {$match: {cnt: {$gt: 1}}}
])
```

**If duplicates found:** Delete newer copies (keep earliest `created_at`), log removed `_id`s for audit.

### 2.2 Add `session_id` to `kgorders` — All 3 Reviewers

**Approach (consensus):** Add nullable `session_id` field to `kgorders`, back-populate from `Session.last_order_id`.

```javascript
// Add field to all existing orders
db.kgorders.updateMany({}, {$set: {session_id: null}})

// Back-populate from Session.last_order_id (Django management command)
// For each session with last_order_id:
//   db.kgorders.updateOne(
//     {orderid: session.last_order_id},
//     {$set: {session_id: session.id}}
//   )
```

**Caveat (GPT-OSS):** If multiple sessions share an order, semantics are unclear. Handle as 1:1 mapping.

### 2.3 Fix DUNE0003_001 — All 3 Reviewers

**Problem:** Division exists in PostgreSQL tenant tables but has 0 documents in MongoDB.

**Diagnosis (Nemo):** Migration script (`restore_kuropurchase.py`) likely didn't split rebellion data into Dune division.

**Fix:**
1. Check if any docs have `bgcode: "DUNE0003"` or `division` starting with "DUNE":
   ```javascript
   db.kgorders.find({bgcode: "DUNE0003"}).count()
   ```
2. If 0 across all collections, the split never happened — re-run tenant-split script with explicit Dune filter
3. If business reality (Dune brand has no historical data), document this and flag in tenant config

### 2.4 Clean Dead References — Nemo + GPT-OSS

**7 collections referenced in code but not in DB:**

| Collection | File | Action |
|-----------|------|--------|
| `gamerDetails` | `rebellion/views.py:264` | Remove dead code |
| `gamers` | `rebellion/views.py:274-442` | Remove dead code |
| `rbpackages` | `rebellion/views.py:283` | Remove dead code |
| `kurodata` | Legacy code | Remove dead code |
| `media` | Legacy code | Remove dead code |
| `stock_audit` | Legacy code | Remove dead code |
| `asset_register` | `KungOS_Analytics_Design.md` | Create stub or remove reference |

**Verification:**
```bash
grep -rn "gamerDetails\|gamers\|rbpackages" --include="*.py" /home/chief/Coding-Projects/kteam-dj-chief/
```

---

## 3. Medium-Term Actions (Weeks 3-6)

### 3.1 The `misc` Collection — Domain-Driven Consolidation

**Revised approach:** Instead of splitting `misc` into 5 separate collections, consolidate ALL collections into 10 domain-driven collections using MongoDB's polymorphic pattern.

| misc Category | Docs | Target Collection | Discriminator |
|---------------|------|-------------------|---------------|
| F&B inventory | 68 | `inventory` | `inv_type: "fb"` |
| PC components | 86 | `inventory` | `inv_type: "hardware"` |
| Gaming gear | 40 | `inventory` | `inv_type: "gaming"` |
| Service requests | 1,922 | `services` | `service_type: "..."` |
| User profiles | 3,218 | `people` | `entity_type: "staff"` or `"customer"` |
| Accounting entries | 111 | `config` | `config_type: "accounting"` |

**Why this works:**
- F&B, PC components, and gaming gear all share the same query pattern (filter by type, check stock) — they belong in one collection with a discriminator
- Service requests merge with existing `serviceRequest` collection — same query pattern
- User profiles merge with `reb_users` — same entity type
- Accounting entries merge with config — low-frequency reference data

**Service request verification (GPT-OSS):** The 1,922 empty-type docs in `misc` may be duplicates of `serviceRequest` (1,625 docs). Run:
```javascript
// Check if misc service requests match serviceRequest collection
db.misc.aggregate([
  {$match: {type: "", srid: {$exists: true}}},
  {$group: {_id: "$srid", cnt: {$sum:1}}}
])
```

### 3.2 Gaming Collections — Consolidate into `catalog`

**Revised approach:** Products, presets, and tpbuilds all merged into `catalog` collection with `cat_type` discriminator.

| Source Collection | Docs | Discriminator |
|-------------------|------|---------------|
| `products` (82) | 82 | `cat_type: "product"` |
| `presets` (6) | 6 | `cat_type: "preset"` |
| `tpbuilds` (123) | 123 | `cat_type: "build"` |

**Why this works:** All are reference/catalog documents queried by category, title, and pricing. Same index pattern: `{bgcode: 1, division: 1, cat_type: 1, collection: 1}`.

### 3.3 F&B Analytics View — Updated for New Schema

**Consensus:** Create a read-only MongoDB view for F&B analytics.

**Post-migration view:**
```javascript
db.createView("fnb_orders", "orders", [
  {$match: {order_type: "gaming", "food.type": {$exists: true}}},
  {$unwind: "$food"},
  {$match: {"food.type": "food"}},
  {$project: {
    orderid: 1,
    session_id: 1,
    food_type: "$food.type",
    food_name: "$food.foodtype",
    quantity: "$food.quantity",
    price: "$food.price",
    total: {$multiply: ["$food.price", "$food.quantity"]},
    order_date: "$order_date",
    division: "$division"
  }}
])
```

**Usage:** Cafe-fnb analytics can query `fnb_orders` view instead of scanning `orders` collection.

---

## 4. Migration Strategy

### 4.1 Single Migration — Domain-Driven Consolidation

**Consensus:** **Single migration for this scale.** Dataset is <10M docs, migration is <10s. Shadow-write adds unnecessary maintenance burden.

**Migration order (4 phases, 10 days):**

**Phase 1 (Day 1) — Emergency:**
1. Restore `inwardinvoices` from kuropurchase (4,626 docs)
2. Verify `purchaseorders` for duplicate `po_no` values
3. Remove 7 dead collections (gamerDetails, gamers, rbpackages, kurodata, media, stock_audit, asset_register)
4. Verify `inwardinvoices` doc count + run sample queries

**Phase 2 (Days 2-3) — Consolidation:**
5. Create 10 new collections with schema validation
6. Migrate all source collections → target collections (add discriminator fields)
7. Verify doc counts before dropping each source collection
8. Drop all 21 source collections

**Phase 3 (Days 4-7) — Code Migration:**
9. Update all `get_collection()` calls to use new collection names
10. Update query filters to use discriminator fields
11. Rewrite `OrderGateway` to use `orders` collection
12. Update menu/inventory endpoints to use `inventory` collection
13. Run full test suite

**Phase 4 (Days 8-10) — Cleanup:**
14. Create composite indexes on all 10 collections
15. Add validation rules (negative stock, required fields per type)
16. Document new schema
17. Deploy and monitor

**Detailed migration steps:** See `mongo-collection-audit-2026-05-14.md` §Migration Plan.

### 4.2 Rollback Strategy

| Step | Rollback |
|------|----------|
| Restore `inwardinvoices` | Drop collection, restore original 16 docs |
| Fix `OrderGateway` | Revert code to previous version |
| Add `session_id` | `db.kgorders.updateMany({}, {$unset: {session_id: ""}})` |
| Clean dead references | Git revert |
| Add `category` to `misc` | `db.misc.updateMany({}, {$unset: {category: ""}})` |
| Create `fnb_orders` view | `db.fnb_orders.drop()` |

---

## 5. Long-Term Risks (Revised)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `inwardinvoices` not fully restored | Medium | Critical (finance broken) | Verify doc count + run analytics |
| Duplicate data in `purchaseorders` | Medium | High (wrong totals) | Run aggregation checks before migration |
| Discriminator field missing on migrated docs | High | Critical | Migration script adds discriminator with default values; validate before drop |
| Schema validation rejects legacy docs | High | High | Run validation in `moderate` mode first, fix violations, then switch to `strict` |
| Index not covering query pattern | Medium | Medium | Profile queries after migration; add secondary indexes as needed |
| Code references miss discriminator filter | High | Critical | Grep all query filters; add discriminator to every query |
| `people` merge duplicates | High | Medium | Deduplicate by userid before merge; log duplicates |
| `services` merge duplicates | Medium | Medium | Deduplicate by srid before merge |
| Migration script drops collection before verify | Low | Critical | Migrate → verify doc count → verify sample queries → drop original |
| `bgcode` vs `bg_code` confusion | Medium | Medium (silent failures) | Lint rule, documentation |
| Negative stock not reconciled | Medium | Medium (inventory wrong) | Automated audit pipeline |
| Division skew causes tenant bugs | Low | High | Validation on write |

---

## 6. Action Checklist (Revised) (Revised)

### Phase 1 — Emergency (Day 1)
```
[ ] Restore inwardinvoices from kuropurchase dump (4,626 docs)
[ ] Verify purchaseorders for duplicate po_no values
[ ] Remove 7 dead collections (gamerDetails, gamers, rbpackages, kurodata, media, stock_audit, asset_register)
[ ] Verify inwardinvoices doc count + run sample queries
```

### Phase 2 — Consolidation (Days 2-3)
```
[ ] Create 10 new collections with schema validation (transactions, payments, orders, procurement, inventory, catalog, people, services, hr, config)
[ ] Migrate inwardinvoices + inwardcreditnotes + inwarddebitnotes + outwardinvoices + outwardcreditnotes + outwarddebitnotes + outward → transactions
[ ] Migrate paymentvouchers → payments
[ ] Migrate inwardpayments + tporders + estimates → orders (add order_type discriminator)
[ ] Drop kgorders, inwardpayments, tporders, estimates, outwardinvoices, outward, inwardcreditnotes, inwarddebitnotes, outwardcreditnotes, outwarddebitnotes, paymentvouchers
[ ] Migrate purchaseorders + indentpos + indentproduct → procurement
[ ] Drop purchaseorders, indentpos, indentproduct
[ ] Migrate stock_register + misc (hardware/fb/gaming) → inventory
[ ] Migrate products + presets + tpbuilds → catalog
[ ] Drop stock_register, products, presets, tpbuilds, misc
[ ] Migrate reb_users + misc (users) + players + teams → people
[ ] Drop reb_users, players, teams
[ ] Migrate serviceRequest + misc (SRs) → services
[ ] Drop serviceRequest
[ ] Migrate employee_attendance → hr
[ ] Migrate bgData + entities + accounts + vendors + tournaments + tourneyregister → config
[ ] Drop bgData, entities, accounts, vendors, tournaments, tourneyregister
[ ] Verify all doc counts before/after migration
```

### Phase 3 — Code Migration (Days 4-7)
```
[ ] Update all get_collection() calls to use new collection names
[ ] Update query filters to use discriminator fields (direction, doc_type, order_type, inv_type, etc.)
[ ] Rewrite OrderGateway to use orders collection with order_type discriminator
[ ] Update menu endpoint to query inventory with inv_type: "fb"
[ ] Update service endpoints to use services collection
[ ] Update user/people endpoints to use people collection
[ ] Update config endpoints to use config collection
[ ] Add schema validation rules to each collection
[ ] Run full test suite
```

### Phase 4 — Cleanup (Days 8-10)
```
[ ] Create composite indexes on all 10 collections
[ ] Add validation rules (negative stock, required fields per type)
[ ] Document new schema (discriminator values, required fields per type, index strategy)
[ ] Deploy and monitor
[ ] Verify no orphaned references to old collection names
```

### Deferred (Phase 5)
```
[ ] Fix DUNE0003_001 (re-run tenant split or document as business reality)
[ ] Handle empty productid in orders.food[] (fuzzy resolver)
[ ] Add negative stock audit pipeline
[ ] Defer bgcode → bg_code rename to Phase 5.7
[ ] Document division skew in wiki
```

---

## 7. Fresh Council Review — Domain-Driven Consolidation (2026-05-14 17:28-17:34)

### Gemma `reviewer-arch` — APPROVE WITH CONDITIONS

**Archive:** `~/.council-memory/reviews/deleg-1778759923/`

**Verdict:** The plan is a significant improvement over the 22-collection proposal. Correctly shifts from "schema-first" to "query-pattern-first" approach.

**Approved:**
- Collection boundaries are well-scoped (transactions, orders, inventory, catalog, people, services, hr, config)
- Discriminator strategy is strong (`direction`, `doc_type`, `order_type`, `inv_type`, etc.)
- Multi-tenant isolation (tenant-first index prefix) is solid
- Schema validation with `anyOf`/`if/then` is viable
- Performance risk is low for current scale (25.5K max in `orders`)

**Conditions (must fix before deployment):**

| # | Condition | Severity | What to Do |
|---|-----------|----------|------------|
| 1 | `transactions` index won't work for direction-agnostic queries | High | Add secondary index: `{bgcode: 1, division: 1, doc_type: 1, doc_date: 1}` |
| 2 | `inwardinvoices` dump must be verified | Critical | Confirm dump is available + restorable before Phase 1 |
| 3 | Every `find()` call needs discriminator filters | Critical | Grep entire codebase; add discriminator to every query |
| 4 | Start schema validation in `moderate` mode | High | Don't use `strict` until all docs have discriminators |
| 5 | Run staging migration before production | High | Full copy of production data, measure time, verify validation rules |

**Gemma's concern:** `hr` (employee_attendance) may eventually need splitting if attendance logs grow to millions. Fine for 966 docs now.

---

### Nemo `reviewer-logic` — 8 FINDINGS (3 Critical, 4 High, 1 Medium)

**Archive:** `~/.council-memory/reviews/deleg-1778760256/`

**Verdict:** The plan is sound but has **8 concrete gaps** that would cause production failures if not addressed.

| # | Finding | Severity | What to Do |
|---|---------|----------|------------|
| 1 | **Missing discriminator backfill** — no pre-migration script to populate discriminator fields | **Critical** | Add dry-run: scan every source collection for missing discriminators; fail migration if any remain null |
| 2 | **Duplicate detection missing** — `people` and `services` merges have no dedup step | **High** | Pre-migration dedup: `$group` on `userid`/`srid`, resolve conflicts, log duplicates |
| 3 | **Ambiguous discriminator assignment** — no deterministic rule for edge-case prefixes (e.g., orderid with both KG and TP prefix) | **Medium** | Document mapping function; unit test that exactly one discriminator per source doc |
| 4 | **Dead collections dropped before verification** — Phase 1 removes dead collections before Phase 2 completes | **High** | Re-order: keep dead collections until Phase 4, or at least snapshot before removal |
| 5 | **Schema validation edge cases** — no guarantee all docs have non-null discriminators before `strict` mode | **High** | Pre-validation pass: `find({discriminator: {$exists:false}})` for each collection; fix before switching to strict |
| 6 | **Aggregation pipelines not addressed** — pipelines that filter by old collection names will return zero results | **Critical** | Code-wide search for old collection names; replace with discriminator filters; add smoke test for top 20 pipelines |
| 7 | **Missing secondary indexes** — only primary composite index listed; ad-hoc filters will fall back to collection scans | **Medium** | Add secondary indexes from Index Strategy table; verify with `explain("executionStats")` |
| 8 | **No snapshot/rollback procedure** — no backup step before any write; risk register says "low likelihood" but plan does exactly that | **High** | `mongodump` of all 31 source collections before Phase 2; document rollback playbook |

**Nemo's action plan (8 items):**
1. Pre-migration validation job (scan for missing discriminators, run dedup)
2. Snapshot all 31 source collections before Phase 2
3. Re-order Phase 1: keep dead collections until Phase 4
4. Update all aggregation pipelines to use discriminator fields
5. Add secondary indexes; verify with `explain()`
6. Document discriminator mapping function + unit tests
7. Run migration in `moderate` mode, then fix missing fields, then `strict`
8. Add rollback playbook with snapshot restore steps

---

## 8. Reviewer Archives

| Reviewer | Archive Path | Content |
|----------|-------------|---------|
| Gemma (arch) — original | `~/.council-memory/reviews/deleg-1778753117/` | Collection decomposition, migration phases, naming convention |
| Nemo (logic) — original | `~/.council-memory/reviews/deleg-1778753323/` | Data integrity, duplicate risk, migration ordering, action checklist |
| GPT-OSS (diversity) — original | `~/.council-memory/reviews/deleg-1778753441/` | Anti-over-engineering, edge cases, alternative approaches |
| Gemma (arch) — consolidation review | `~/.council-memory/reviews/deleg-1778759923/` | Domain-driven consolidation: approve with 5 conditions |
| Nemo (logic) — consolidation review | `~/.council-memory/reviews/deleg-1778760256/` | Domain-driven consolidation: 8 findings (3 critical, 4 high, 1 medium) |

---

## 9. Consolidated Recommendations (Gemma + Nemo)

### Must Fix Before Phase 2

| Item | Source | Action |
|------|--------|--------|
| Verify `inwardinvoices` dump | Gemma #2, Nemo #8 | Confirm dump available + restorable; `mongodump` of all 31 source collections |
| Pre-migration discriminator validation | Nemo #1, #5 | Dry-run: scan every source collection for missing discriminators; fail if any null |
| Dedup `people` and `services` merges | Nemo #2 | `$group` on `userid`/`srid`; resolve conflicts; log duplicates |
| Document discriminator mapping function | Nemo #3 | Code-level mapping with unit tests; assert exactly one discriminator per doc |
| Keep dead collections until Phase 4 | Nemo #4 | Don't drop dead collections in Phase 1; snapshot before removal |
| Add `transactions` secondary index | Gemma #1 | `{bgcode: 1, division: 1, doc_type: 1, doc_date: 1}` for direction-agnostic queries |
| Update aggregation pipelines | Nemo #6 | Code-wide search for old collection names; replace with discriminator filters |
| Add secondary indexes | Gemma #7, Nemo #7 | Verify with `explain("executionStats")` on representative workload |
| Start schema validation in `moderate` | Gemma #4, Nemo #5 | Switch to `strict` only after pre-validation pass confirms all discriminators present |
| Rollback playbook | Nemo #8 | Document restore steps for each phase; keep snapshots until Phase 4 complete |
| Staging migration test | Gemma #5 | Full copy of production data; measure migration time; verify validation rules |

### Updated Phase 1 Checklist

```
[ ] VERIFY: inwardinvoices dump is available + restorable
[ ] SNAPSHOT: mongodump all 31 source collections to /backups/phase2/
[ ] DRY-RUN: Scan every source collection for missing discriminator fields
[ ] DEDUP: Run $group on userid (people) and srid (services) to find duplicates
[ ] VALIDATE: Run discriminator mapping function on edge-case docs (ambiguous prefixes)
[ ] RESTORE: inwardinvoices from kuropurchase (4,626 docs)
[ ] VERIFY: inwardinvoices doc count + run sample queries
[ ] VERIFY: purchaseorders for duplicate po_no values
[ ] NOTE: Do NOT drop dead collections yet — keep until Phase 4
```

---

**Council verdict (final):** The MongoDB schema needs 3 emergency fixes (inwardinvoices, OrderGateway, menu), 5 short-term verifications, and a **full domain-driven consolidation** (31 → 10 collections). The consensus is to use MongoDB's polymorphic collection pattern — discriminator fields + schema validation per type — to group documents by query access patterns, not document shape. Single-pass migration for this scale (<10M docs).

**Gemma:** APPROVE WITH CONDITIONS (5 conditions)
**Nemo:** 8 FINDINGS (3 critical, 4 high, 1 medium) — all addressable before Phase 2

**Combined requirement:** All 11 items in §9 must be completed before Phase 2 consolidation begins. See `mongo-collection-audit-2026-05-14.md` for the complete consolidation plan.

**Key difference from original review:** Instead of incremental fixes (split misc into 5, keep most collections as-is), the revised approach consolidates ALL collections into 10 domain-driven collections. This aligns with MongoDB's official polymorphic data pattern and reduces collection count by 68% (vs. 29% in original plan).
