# Review: Migration Data Integrity Audit Handoff (df1c39)

| Field | Value |
|-------|-------|
| Project ID | `kungos-backend` |
| Primary entity ID | `df1c39` |
| Entity type | `review` |
| Short description | Five-axis review of the migration data integrity audit handoff document |
| Status | `completed` |
| Source | `30-06-2026_migration-data-integrity-audit_df1c39.md` |
| Generated | `30-06-2026` |
| Verdict | **PASS with findings** — 2 critical, 3 high, 3 moderate, 2 low |

---

## Axis 1: Spec Compliance

### Finding 1.1 — Missing: Three ViewSets read from DROPPED collections (CRITICAL)

**severity:** `high`
**summary:** `OutwardPaymentViewSet`, `SettlementsViewSet`, `BulkPaymentViewSet` all reference dropped MongoDB collections — endpoints are silently broken.

**evidence:**
- `accounts/viewsets.py:311` — `COLLECTION_NAME = 'outwardpayments'` (DROPPED)
- `accounts/viewsets.py:1353` — `COLLECTION_NAME = 'settlements'` (DROPPED)
- `accounts/viewsets.py:1188` — `COLLECTION_NAME = 'bulk_payments'` (DROPPED)
- MongoDB verification: all four collections (`outwardpayments`, `settlements`, `bulkpayments`, `bulk_payments`) confirmed DROPPED
- `financial_documents` has 0 records for `outward_payment`, `settlement`, `bulk_payment` doc_types

**recommended action:** Add a dedicated section in Phase 2 for these three broken endpoints. Either (a) restore from backup if data exists elsewhere, or (b) mark endpoints as deprecated with a 410 Gone response. Do not leave them silently returning empty results.

**related plan unit:** Phase 2 (Data Migration Fixes), Phase 4A (Finance ViewSets)
**autofixable:** false

### Finding 1.2 — Missing: `paymentvouchers` has an existing ViewSet (MODERATE)

**severity:** `moderate`
**summary:** The handoff says `paymentvouchers` (3,459 docs) was "NOT migrated" but doesn't note that `PaymentVoucherViewSet` already exists in `accounts/viewsets.py:371` and reads from the old collection.

**evidence:**
- `accounts/viewsets.py:371-376` — `class PaymentVoucherViewSet` with `COLLECTION_NAME = 'paymentvouchers'`
- This ViewSet is functional (reads from existing MongoDB collection) but is NOT consolidated into `financial_documents`

**recommended action:** Add `PaymentVoucherViewSet` to the Phase 4A rewrite list. When finance ViewSets are migrated to read `financial_documents`, include `paymentvouchers` in the consolidation AND update this ViewSet.

**related plan unit:** Phase 4A (Finance ViewSets)
**autofixable:** false

### Finding 1.3 — Missing: Duplicate `PurchaseOrderViewSet` not addressed (HIGH)

**severity:** `high`
**summary:** Two `PurchaseOrderViewSet` classes exist — one in `accounts/viewsets.py:436` and one in `orders/viewsets.py:682`. Both are registered at different URL paths (`/accounts/purchase-orders` and `/orders/purchase-orders`).

**evidence:**
- `accounts/viewsets.py:436` — `class PurchaseOrderViewSet(BaseAccountsViewSet)` reads MongoDB `purchaseorders`
- `orders/viewsets.py:682` — `class PurchaseOrderViewSet(BaseOrdersViewSet)` reads MongoDB `purchaseorders`
- `accounts/urls.py:79-84` — registered at `/accounts/purchase-orders`
- `orders/urls.py:48-53` — registered at `/orders/purchase-orders`
- Both read from the same MongoDB collection with identical logic

**recommended action:** Phase 4D should explicitly address this duplication. Consolidate to a single ViewSet in `inventory/viewsets.py` (where the PG table lives) at `/inventory/purchase-orders`. Deprecate or remove the two existing copies.

**related plan unit:** Phase 4D (Purchase Order ViewSet Migration)
**autofixable:** false

---

## Axis 2: Correctness

### Finding 2.1 — Incorrect: `inventory_indent` table exists but is empty (MODERATE)

**severity:** `moderate`
**summary:** The handoff states "`inventory_indent` table does NOT exist in PostgreSQL" — this is factually incorrect. The table exists (created by Django migrations for the `Indent` model) but has 0 rows.

**evidence:**
- `domains/inventory/models.py:422` — `class Indent(models.Model)` with full schema
- `domains/inventory/models.py:454` — `class IndentItem(models.Model)` with full schema
- PG verification: `inventory_indent` (0 rows), `inventory_indentitem` (0 rows) — tables exist, empty

**recommended action:** Correct the handoff to state: "`inventory_indent` and `inventory_indentitem` tables exist (Django models present) but contain 0 rows — data was never migrated from `indentpos`/`indentproduct`." This changes the Phase 2 scope: no table creation needed, only data migration.

**related plan unit:** Phase 2 Step 6, Phase 3D
**autofixable:** true
**autofix applied:** pending (handoff not yet updated)

### Finding 2.2 — Incorrect: `ServiceRequestViewSet` reads from `service_detail`, not `serviceRequest` (MODERATE)

**severity:** `moderate`
**summary:** The handoff states `ServiceRequestViewSet` reads from MongoDB `serviceRequest` — it actually reads from `service_detail` (MongoDB, 0 docs). The PG `service_detail` table has 1,623 rows but the ViewSet doesn't read from it.

**evidence:**
- `orders/viewsets.py:818` — `COLLECTION_NAME = 'service_detail'`
- MongoDB `service_detail`: 0 docs (empty collection)
- PG `service_detail`: 1,623 rows
- Handoff Phase 4B says "Replace MongoDB queries with Django ORM queries against `orders_core`" — but `service_detail` is a separate PG table, not a row in `orders_core`

**recommended action:** Correct Phase 4B to specify: `ServiceRequestViewSet` must be rewritten to read from the PG `service_detail` table (not `orders_core`). The `service_detail` PG table schema is: `order_id`, `service_type`, `description`, `scheduled_date`, `completed_date`.

**related plan unit:** Phase 4B (Orders ViewSets)
**autofixable:** true
**autofix applied:** pending (handoff not yet updated)

### Finding 2.3 — Data loss: `outward_payment`, `settlement`, `bulk_payment` dropped without migration (HIGH)

**severity:** `high`
**summary:** The consolidation script dropped `outwardpayments`, `settlements`, and `bulkpayments` collections WITHOUT migrating their data to `financial_documents`. The data is unrecoverable from MongoDB.

**evidence:**
- MongoDB: `outwardpayments`, `settlements`, `bulkpayments`, `bulk_payments` — all DROPPED
- `financial_documents`: 0 records for `outward_payment`, `settlement`, `bulk_payment` doc_types
- Consolidation script (`/tmp/consolidate_finance.py`) did NOT include these collections in `COLLECTION_MAP`
- No backup of these collections identified

**recommended action:** Add to Phase 1 audit: check if these collections exist in the `latest-mongo-backup.dump` or `kuropurchase` database. If recoverable, add to Phase 2 repair. If not, document as permanent data loss and mark ViewSets as deprecated.

**related plan unit:** Phase 1 Step 2, Phase 2
**autofixable:** false

---

## Axis 3: Security

### Finding 3.1 — No security findings

The handoff deals with data migration and code wiring. No security vulnerabilities identified in the plan itself. The constraint "No data deletion without explicit approval" is appropriate.

---

## Axis 4: Maintainability

### Finding 4.1 — Phase ordering suboptimal (LOW)

**severity:** `low`
**summary:** Phase 3 (Django models) is listed as depending on Phase 2 (data fixes). Model creation doesn't require data to be fixed first — models can be created against empty or partial tables.

**evidence:**
- Phase 3 states: "Dependencies: Phase 1 (audit complete), Phase 2 (data fixed)"
- Django models can be created independently of data content
- Phase 3B (PurchaseOrder model) can proceed with 5,362 rows; Phase 3C (Partner/Bank/Loan) can proceed with 0 rows

**recommended action:** Change Phase 3 dependency to "Phase 1 (audit complete)" only. Allow Phase 2 and Phase 3 to run in parallel. This reduces critical path.

**related plan unit:** Phase 3 header
**autofixable:** true
**autofix applied:** pending

### Finding 4.2 — Phase 4A approach options not decided (LOW)

**severity:** `low`
**summary:** Phase 4A presents three options (A: Django MongoDB model, B: raw MongoDB queries, C: migrate to PG) with "Recommendation: Option B for immediate, Option C for long-term." This leaves the executing agent to choose without clear criteria.

**evidence:**
- Phase 4A lists Options A/B/C with recommendation "Option B for immediate fix, Option C for long-term"
- No timeline or criteria for when to transition from B to C

**recommended action:** Either (a) commit to one approach with a clear rationale, or (b) add a decision gate: "Use Option B for Phase 4 execution. Create a separate handoff for Option C migration after Phase 5 is complete."

**related plan unit:** Phase 4A
**autofixable:** true
**autofix applied:** pending

---

## Axis 5: Performance

### Finding 5.1 — No performance findings

The handoff correctly identifies missing `bg_code` indexes as a performance issue. No additional performance concerns.

---

## Summary

| Severity | Count | Issues |
|----------|-------|--------|
| **HIGH** | 3 | Dropped collection ViewSets (1.1), duplicate PurchaseOrderViewSet (1.3), data loss without backup check (2.3) |
| **MODERATE** | 3 | Missing PaymentVoucherViewSet in plan (1.2), incorrect table existence claim (2.1), incorrect collection name (2.2) |
| **LOW** | 2 | Suboptimal phase ordering (4.1), undecided approach (4.2) |
| **Total** | **8** | |

**Verdict: PASS with findings.** The handoff is structurally sound and covers the major gaps. The 3 HIGH findings should be addressed before execution begins (they represent silently broken endpoints and unrecovered data). The 3 MODERATE findings are factual corrections that improve accuracy. The 2 LOW findings are optimization suggestions.

**Blocking for execution:** Finding 1.1 (dropped collection ViewSets) and Finding 2.3 (data loss assessment) must be resolved before Phase 2 begins. The executing agent needs to know which endpoints are permanently broken vs. repairable.

**Non-blocking:** Findings 1.2, 2.1, 2.2, 4.1, 4.2 can be addressed during execution as corrections.
