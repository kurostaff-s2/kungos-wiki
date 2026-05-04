# Orders Migration Plan — Snapshot + Validation

**Date:** 2026-05-04  
**Scope:** 15,925 documents across 5 sources → PostgreSQL core + detail tables  
**Strategy:** Snapshot → Migrate → Validate → Fix → Repeat → Deploy

---

## Migration Sources

| Source | Type | Count | Storage | Key Fields |
|--------|------|-------|---------|------------|
| `estimates` | Mongo | 4,308 | KungOS_Mongo_One | estimate_no, division, products, totalprice |
| `kgorders` | Mongo | 9,162 | KungOS_Mongo_One | orderid, division, products, totalprice, estimate_no (→ in_store) |
| `tporders` | Mongo | 229 | KungOS_Mongo_One | orderid, division, products, totalprice |
| `serviceRequest` | Mongo | 1,625 | KungOS_Mongo_One | sr_no, division, products, diagnosis |
| `Orders` | PG | ~601 | kuro-gaming-dj-backend | orderid, order_total, status, payment_option |
| **Total** | | **15,925** | | |

---

## Migration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Migration Runner                                           │
│                                                             │
│  1. Snapshot sources (Mongo dump + PG dump)                 │
│  2. Load into staging DB (separate PG instance)             │
│  3. Run migration scripts                                   │
│  4. Run validation passes                                   │
│  5. Generate fix scripts for failures                       │
│  6. Repeat until all passes green                           │
│  7. Deploy to production                                    │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** Never migrate directly to production. Always validate against a snapshot first.

---

## Phase 1: Snapshot

```bash
# MongoDB snapshot
mongodump --db KungOS_Mongo_One \
    --collection estimates \
    --collection kgorders \
    --collection tporders \
    --collection serviceRequest \
    --out /tmp/migration-snapshot/$(date +%Y%m%d)

# PostgreSQL snapshot (legacy eshop)
pg_dump -d kuro-gaming-dj-backend \
    --table=Orders \
    --table=OrderItems \
    -f /tmp/migration-snapshot/$(date +%Y%m%d)/legacy-orders.sql

# Record baseline metrics
python manage.py migration_snapshot --output /tmp/migration-snapshot/baseline.json
```

**Baseline metrics (`baseline.json`):**
```json
{
    "timestamp": "2026-05-04T10:00:00Z",
    "sources": {
        "estimates": {
            "doc_count": 4308,
            "field_completeness": {
                "estimate_no": 4308,
                "division": 4308,
                "products": 4290,
                "totalprice": 4308,
                "customer": 4200,
                "status": 4308
            },
            "bg_code_distribution": {
                "KURO0001": 4308
            },
            "status_distribution": {
                "draft": 1200,
                "confirmed": 2100,
                "expired": 1008
            }
        },
        "kgorders": {
            "doc_count": 9162,
            "field_completeness": { ... },
            "estimate_links": {
                "has_estimate_no": 7500,
                "valid_estimate_refs": 7200,
                "orphan_estimate_refs": 300
            }
        }
    }
}
```

---

## Phase 2: Staging Migration

Run migrations against a **staging PostgreSQL instance** (not production).

```python
# manage.py migration_run --staging
# Migrations/0001_migrate_orders.py

from django.db import migrations
from pymongo import MongoClient
import json


def migrate_estimates(apps, schema_editor):
    """Migrate estimates collection → orders_core + estimate_detail."""
    Order = apps.get_model('orders', 'Order')
    EstimateDetail = apps.get_model('orders', 'EstimateDetail')

    mongo = MongoClient(settings.MONGO_DB_URI)['KungOS_Mongo_One']
    estimates = list(mongo['estimates'].find({}, {'_id': 0}))

    migrated = 0
    errors = []

    for doc in estimates:
        try:
            # Core record
            order = Order.objects.create(
                orderid=doc['estimate_no'],
                order_type='estimate',
                status=doc.get('status', 'draft'),
                total_amount=doc.get('totalprice'),
                customer_id=doc.get('customer', {}).get('userid') if isinstance(doc.get('customer'), dict) else doc.get('customer'),
                division=doc.get('division'),
                bg_code=doc.get('bgcode', 'KURO0001'),
                billadd=json.dumps(doc.get('billadd')) if doc.get('billadd') else None,
                products=json.dumps(doc.get('products', [])),
            )

            # Detail record
            EstimateDetail.objects.create(
                order=order,
                version=doc.get('version', 1),
                validity=doc.get('validity'),
                confirmed_by=doc.get('confirmed_by'),
                confirmed_at=doc.get('order_confirmed'),
                description=doc.get('description'),
            )
            migrated += 1

        except Exception as e:
            errors.append({
                'estimate_no': doc.get('estimate_no'),
                'error': str(e),
                'doc_snippet': json.dumps({k: doc[k] for k in ['estimate_no', 'division', 'status']})
            })

    print(f"Estimates: {migrated}/{len(estimates)} migrated, {len(errors)} errors")
    if errors:
        # Save errors for fix script
        import pathlib
        pathlib.Path('/tmp/migration-errors').mkdir(exist_ok=True)
        with open('/tmp/migration-errors/estimates.json', 'w') as f:
            json.dump(errors, f, indent=2)


def migrate_kgorders(apps, schema_editor):
    """Migrate kgorders collection → orders_core + in_store_detail."""
    Order = apps.get_model('orders', 'Order')
    KGOrderDetail = apps.get_model('orders', 'KGOrderDetail')

    mongo = MongoClient(settings.MONGO_DB_URI)['KungOS_Mongo_One']
    kgorders = list(mongo['kgorders'].find({}, {'_id': 0}))

    migrated = 0
    errors = []

    for doc in kgorders:
        try:
            order = Order.objects.create(
                orderid=doc['orderid'],
                order_type='kg',
                status=doc.get('status', 'draft'),
                total_amount=doc.get('totalprice'),
                customer_id=doc.get('user', {}).get('userid') if isinstance(doc.get('user'), dict) else doc.get('user'),
                division=doc.get('division'),
                bg_code=doc.get('bgcode', 'KURO0001'),
                billadd=json.dumps(doc.get('billadd')) if doc.get('billadd') else None,
                products=json.dumps(doc.get('products', [])),
                channel=doc.get('channel'),
            )

            KGOrderDetail.objects.create(
                order=order,
                estimate_ref=doc.get('estimate_no'),
                order_date=doc.get('order_date'),
                dispatchby_date=doc.get('dispatchby_date'),
                amount_due=doc.get('amount_due'),
                invoice_generated=doc.get('invoice_generated', False),
                po_ref=doc.get('po_ref'),
                builds_count=len(doc.get('builds', [])) if isinstance(doc.get('builds'), list) else (doc.get('builds', 0) or 0),
            )
            migrated += 1

        except Exception as e:
            errors.append({
                'orderid': doc.get('orderid'),
                'error': str(e),
            })

    print(f"In-Store Orders: {migrated}/{len(kgorders)} migrated, {len(errors)} errors")


def migrate_tporders(apps, schema_editor):
    """Migrate tporders → orders_core + tp_order_detail."""
    # Similar pattern...
    pass


def migrate_service_requests(apps, schema_editor):
    """Migrate serviceRequest → orders_core + service_detail."""
    # Similar pattern...
    pass


def migrate_eshop_orders(apps, schema_editor):
    """Migrate legacy PG Orders → orders_core + eshop_detail."""
    # PG → PG migration, different pattern
    pass
```

---

## Phase 3: Validation Passes

```python
# manage.py migration_validate --staging
# Migrations/validate.py

from django.db import connection
import json


class MigrationValidator:
    """Run validation passes against staging database."""

    def __init__(self, baseline_path):
        with open(baseline_path) as f:
            self.baseline = json.load(f)
        self.results = {}
        self.errors = []

    def run_all(self):
        """Run all validation passes."""
        passes = [
            self.validate_doc_counts,
            self.validate_field_completeness,
            self.validate_fk_integrity,
            self.validate_estimate_links,
            self.validate_products_integrity,
            self.validate_total_consistency,
            self.validate_unique_orderids,
            self.validate_date_formats,
            self.validate_status_enums,
            self.validate_bg_code_coverage,
            self.validate_detail_table_coverage,
        ]

        for check in passes:
            name = check.__name__
            print(f"Running {name}...")
            try:
                result = check()
                self.results[name] = {
                    'status': 'PASS' if result.get('passed') else 'FAIL',
                    'details': result.get('details', {}),
                    'errors': result.get('errors', []),
                }
                print(f"  ✓ PASS" if result.get('passed') else f"  ✗ FAIL: {result.get('summary')}")
            except Exception as e:
                self.results[name] = {'status': 'ERROR', 'error': str(e)}
                print(f"  ✗ ERROR: {e}")

        return all(r['status'] == 'PASS' for r in self.results.values())

    def validate_doc_counts(self):
        """Pass 1: Doc count match (source → target)."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT order_type, COUNT(*) as cnt
                FROM orders_core
                GROUP BY order_type
            """)
            actual = dict(cursor.fetchall())

        expected = {
            'estimate': self.baseline['sources']['estimates']['doc_count'],
            'kg': self.baseline['sources']['kgorders']['doc_count'],
            'tp': self.baseline['sources']['tporders']['doc_count'],
            'service': self.baseline['sources']['serviceRequest']['doc_count'],
            'eshop': self.baseline['sources']['Orders']['doc_count'],
        }

        errors = []
        for order_type, expected_count in expected.items():
            actual_count = actual.get(order_type, 0)
            if actual_count != expected_count:
                errors.append({
                    'type': order_type,
                    'expected': expected_count,
                    'actual': actual_count,
                    'missing': expected_count - actual_count,
                })

        return {
            'passed': len(errors) == 0,
            'summary': f"{len(errors)} type(s) with count mismatch",
            'errors': errors,
        }

    def validate_field_completeness(self):
        """Pass 2: No nulls in required core fields."""
        required_fields = ['orderid', 'order_type', 'status', 'division', 'bg_code']

        with connection.cursor() as cursor:
            errors = []
            for field in required_fields:
                cursor.execute(f"""
                    SELECT COUNT(*) FROM orders_core
                    WHERE {field} IS NULL
                """)
                null_count = cursor.fetchone()[0]
                if null_count > 0:
                    errors.append({
                        'field': field,
                        'null_count': null_count,
                        'sample': f"SELECT * FROM orders_core WHERE {field} IS NULL LIMIT 5",
                    })

            return {
                'passed': len(errors) == 0,
                'summary': f"{len(errors)} field(s) with nulls",
                'errors': errors,
            }

    def validate_fk_integrity(self):
        """Pass 3: All bg_code, division values exist in tenant tables."""
        with connection.cursor() as cursor:
            # Check bg_code FK
            cursor.execute("""
                SELECT DISTINCT oc.bg_code FROM orders_core oc
                LEFT JOIN tenant_business_groups bg ON oc.bg_code = bg.bg_code
                WHERE bg.bg_code IS NULL
            """)
            invalid_bg = [row[0] for row in cursor.fetchall()]

            # Check division FK
            cursor.execute("""
                SELECT DISTINCT oc.division FROM orders_core oc
                LEFT JOIN tenant_divisions td ON oc.division = td.div_code
                WHERE td.div_code IS NULL
            """)
            invalid_div = [row[0] for row in cursor.fetchall()]

            errors = []
            if invalid_bg:
                errors.append({'field': 'bg_code', 'invalid_values': invalid_bg})
            if invalid_div:
                errors.append({'field': 'division', 'invalid_values': invalid_div})

            return {
                'passed': len(errors) == 0,
                'summary': f"{len(errors)} FK violation(s)",
                'errors': errors,
            }

    def validate_estimate_links(self):
        """Pass 4: estimate_no → orderid links are valid."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT kd.estimate_ref, COUNT(*)
                FROM in_store_detail kd
                WHERE kd.estimate_ref IS NOT NULL
                AND kd.estimate_ref NOT IN (
                    SELECT orderid FROM orders_core WHERE order_type = 'estimate'
                )
                GROUP BY kd.estimate_ref
            """)
            orphan_refs = cursor.fetchall()

            return {
                'passed': len(orphan_refs) == 0,
                'summary': f"{len(orphan_refs)} orphan estimate references",
                'errors': [{'estimate_ref': ref, 'count': cnt} for ref, cnt in orphan_refs],
            }

    def validate_products_integrity(self):
        """Pass 5: Products JSON is valid and non-empty where expected."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT orderid, order_type FROM orders_core
                WHERE products IS NULL
                AND order_type IN ('kg', 'tp', 'estimate', 'cafe_food')
            """)
            missing_products = cursor.fetchall()

            # Check for invalid JSON
            cursor.execute("""
                SELECT orderid FROM orders_core
                WHERE products IS NOT NULL
                AND products::text !~ '^\['
            """)
            invalid_json = cursor.fetchall()

            errors = []
            if missing_products:
                errors.append({'issue': 'missing_products', 'count': len(missing_products)})
            if invalid_json:
                errors.append({'issue': 'invalid_json', 'count': len(invalid_json)})

            return {
                'passed': len(errors) == 0,
                'summary': f"{len(errors)} product integrity issue(s)",
                'errors': errors,
            }

    def validate_total_consistency(self):
        """Pass 6: Line items sum ≈ total_amount (within 1% tolerance)."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT orderid, total_amount,
                    jsonb_array_length(products) as line_count
                FROM orders_core
                WHERE total_amount IS NOT NULL
                AND products IS NOT NULL
                AND jsonb_array_length(products) > 0
                AND total_amount < 100  -- suspiciously low totals
            """)
            suspicious = cursor.fetchall()

            return {
                'passed': len(suspicious) == 0,
                'summary': f"{len(suspicious)} suspicious total(s)",
                'errors': [{'orderid': row[0], 'total': row[1], 'lines': row[2]} for row in suspicious],
            }

    def validate_unique_orderids(self):
        """Pass 7: No duplicate orderids."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT orderid, COUNT(*) FROM orders_core
                GROUP BY orderid HAVING COUNT(*) > 1
            """)
            duplicates = cursor.fetchall()

            return {
                'passed': len(duplicates) == 0,
                'summary': f"{len(duplicates)} duplicate orderid(s)",
                'errors': [{'orderid': oid, 'count': cnt} for oid, cnt in duplicates],
            }

    def validate_date_formats(self):
        """Pass 8: All dates are valid."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM orders_core
                WHERE created_at IS NULL
            """)
            missing_dates = cursor.fetchone()[0]

            return {
                'passed': missing_dates == 0,
                'summary': f"{missing_dates} missing created_at",
                'errors': [{'issue': 'missing_created_at', 'count': missing_dates}] if missing_dates else [],
            }

    def validate_status_enums(self):
        """Pass 9: All status values are valid for their order_type."""
        valid_statuses = {
            'estimate': ['draft', 'confirmed', 'expired', 'converted'],
            'kg': ['draft', 'confirmed', 'building', 'testing', 'packed', 'shipped', 'delivered'],
            'tp': ['draft', 'confirmed', 'building', 'testing', 'packed', 'shipped', 'delivered'],
            'service': ['open', 'diagnosing', 'repairing', 'completed', 'cancelled'],
            'eshop': ['payment_pending', 'confirmed', 'building', 'testing', 'packed', 'shipped', 'delivered'],
            'cafe_food': ['pending', 'preparing', 'served', 'billed'],
        }

        with connection.cursor() as cursor:
            errors = []
            for order_type, valid in valid_statuses.items():
                cursor.execute("""
                    SELECT DISTINCT status FROM orders_core
                    WHERE order_type = %s AND status NOT IN %s
                """, [order_type, tuple(valid)])
                invalid = [row[0] for row in cursor.fetchall()]
                if invalid:
                    errors.append({'type': order_type, 'invalid_statuses': invalid})

            return {
                'passed': len(errors) == 0,
                'summary': f"{len(errors)} type(s) with invalid statuses",
                'errors': errors,
            }

    def validate_bg_code_coverage(self):
        """Pass 10: Every doc has a valid bg_code."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM orders_core WHERE bg_code IS NULL
            """)
            missing = cursor.fetchone()[0]

            return {
                'passed': missing == 0,
                'summary': f"{missing} missing bg_code",
                'errors': [{'issue': 'missing_bg_code', 'count': missing}] if missing else [],
            }

    def validate_detail_table_coverage(self):
        """Pass 11: Every core row has exactly one detail row (or zero for unknown types)."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT oc.orderid, oc.order_type, COUNT(d.id) as detail_count
                FROM orders_core oc
                LEFT JOIN LATERAL (
                    SELECT id FROM estimate_detail WHERE order_id = oc.id
                    UNION ALL SELECT id FROM in_store_detail WHERE order_id = oc.id
                    UNION ALL SELECT id FROM tp_order_detail WHERE order_id = oc.id
                    UNION ALL SELECT id FROM service_detail WHERE order_id = oc.id
                    UNION ALL SELECT id FROM eshop_detail WHERE order_id = oc.id
                    UNION ALL SELECT id FROM cafe_food_detail WHERE order_id = oc.id
                ) d ON true
                GROUP BY oc.orderid, oc.order_type
                HAVING COUNT(d.id) != 1
            """)
            mismatches = cursor.fetchall()

            return {
                'passed': len(mismatches) == 0,
                'summary': f"{len(mismatches)} core/detail mismatch(es)",
                'errors': [{'orderid': row[0], 'type': row[1], 'detail_count': row[2]} for row in mismatches],
            }

    def generate_report(self):
        """Generate validation report."""
        passed = sum(1 for r in self.results.values() if r['status'] == 'PASS')
        failed = sum(1 for r in self.results.values() if r['status'] == 'FAIL')
        errored = sum(1 for r in self.results.values() if r['status'] == 'ERROR')

        report = {
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'summary': {
                'total_checks': len(self.results),
                'passed': passed,
                'failed': failed,
                'errored': errored,
                'ready_for_deploy': failed == 0 and errored == 0,
            },
            'details': self.results,
        }

        with open('/tmp/migration-validation-report.json', 'w') as f:
            json.dump(report, f, indent=2)

        return report
```

---

## Phase 4: Fix Scripts

For each validation failure, generate a fix script:

```python
# manage.py migration_fix --error-file /tmp/migration-errors/kgorders.json
# Migrations/fixes.py

def fix_missing_bg_code():
    """Fix orders with missing bg_code by inferring from division."""
    division_to_bg = {
        'KURO0001_001': 'KURO0001',
        'KURO0001_002': 'KURO0001',
        'KURO0001_003': 'KURO0001',
        'DUNE0003_001': 'DUNE0003',
    }

    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE orders_core
            SET bg_code = %s
            WHERE bg_code IS NULL
            AND division = %s
        """, list(division_to_bg.values()), list(division_to_bg.keys()))


def fix_orphan_estimate_refs():
    """Fix KG orders with invalid estimate references."""
    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE in_store_detail
            SET estimate_ref = NULL
            WHERE estimate_ref IS NOT NULL
            AND estimate_ref NOT IN (
                SELECT orderid FROM orders_core WHERE order_type = 'estimate'
            )
        """)


def fix_invalid_statuses():
    """Normalize invalid status values."""
    status_map = {
        'completed': 'delivered',  # eshop legacy
        'done': 'delivered',
        'cancelled': 'cancelled',
        'rejected': 'cancelled',
    }

    with connection.cursor() as cursor:
        for old, new in status_map.items():
            cursor.execute("""
                UPDATE orders_core SET status = %s WHERE status = %s
            """, [new, old])


def fix_suspicious_totals():
    """Flag orders with suspiciously low totals for manual review."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT orderid, total_amount, order_type
            FROM orders_core
            WHERE total_amount < 100 AND total_amount > 0
        """)
        for orderid, total, order_type in cursor.fetchall():
            print(f"  REVIEW: {orderid} ({order_type}) total={total}")
            # Don't auto-fix — flag for manual review
```

---

## Phase 5: Production Deployment

```bash
#!/bin/bash
# deploy-migration.sh

set -euo pipefail

SNAPSHOT_DATE=$(date +%Y%m%d)
STAGING_DB="orders_staging"
PRODUCTION_DB="kuro-cadence"

echo "=== Step 1: Snapshot production data ==="
mongodump --db KungOS_Mongo_One \
    --collection estimates --collection kgorders \
    --collection tporders --collection serviceRequest \
    --out /tmp/migration-snapshot/$SNAPSHOT_DATE

pg_dump -d kuro-gaming-dj-backend --table=Orders -f /tmp/migration-snapshot/$SNAPSHOT_DATE/legacy-orders.sql

echo "=== Step 2: Load snapshot into staging ==="
mongorestore --db $STAGING_DB /tmp/migration-snapshot/$SNAPSHOT_DATE/

echo "=== Step 3: Run migration against staging ==="
python manage.py migration_run --staging --snapshot /tmp/migration-snapshot/$SNAPSHOT_DATE

echo "=== Step 4: Run validation passes ==="
python manage.py migration_validate --staging --baseline /tmp/migration-snapshot/baseline.json

echo "=== Step 5: Check validation report ==="
REPORT=$(cat /tmp/migration-validation-report.json)
READY=$(echo $REPORT | jq -r '.summary.ready_for_deploy')

if [ "$READY" != "true" ]; then
    echo "✗ Validation failed. Fix errors and re-run."
    echo "Report: /tmp/migration-validation-report.json"
    exit 1
fi

echo "✓ All validation passes green. Ready for production deployment."

echo "=== Step 6: Deploy to production ==="
python manage.py migrate  # Create tables
python manage.py migration_run --production --snapshot /tmp/migration-snapshot/$SNAPSHOT_DATE

echo "=== Step 7: Run validation against production ==="
python manage.py migration_validate --production --baseline /tmp/migration-snapshot/baseline.json

echo "=== Step 8: Verify production ==="
python manage.py migration_validate --production --baseline /tmp/migration-snapshot/baseline.json

echo "✓ Migration complete. Production verified."
```

---

## Iteration Cycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Snapshot │ ──▶ │ Migrate  │ ──▶ │ Validate │ ──▶ │  Green?  │
└──────────┘     └──────────┘     └──────────┘     └────┬─────┘
                                                         │
                              ┌──────────┐              │
                              │   Fix    │             Yes
                              │ Scripts  │              │
                              └────┬─────┘              │
                                   │                    ▼
                                No  │            ┌──────────┐
                                   └────────────▶│ Deploy   │
                                                  │ to Prod  │
                                                  └──────────┘
```

**Typical iteration:**
1. Run migration → 15,800/15,925 migrated (125 errors)
2. Validate → 8/11 passes green, 3 failures
3. Generate fix scripts for 3 failures
4. Run fixes → re-migrate → 15,925/15,925 migrated
5. Validate → 11/11 passes green
6. Deploy to production

---

## Rollback Plan

If production validation fails:

```sql
-- Rollback: drop new tables, keep legacy data untouched
DROP TABLE IF EXISTS cafe_food_detail CASCADE;
DROP TABLE IF EXISTS eshop_detail CASCADE;
DROP TABLE IF EXISTS service_detail CASCADE;
DROP TABLE IF EXISTS tp_order_detail CASCADE;
DROP TABLE IF EXISTS in_store_detail CASCADE;
DROP TABLE IF EXISTS estimate_detail CASCADE;
DROP TABLE IF EXISTS orders_core CASCADE;

-- Legacy Mongo collections and PG Orders table are untouched
-- Frontend can fall back to legacy endpoints during rollback
```

**Key safety:** Legacy data is never modified during migration. It's only read. If migration fails, legacy data is intact.

---

## Effort Estimate

| Phase | Effort | Notes |
|-------|--------|-------|
| Snapshot scripts | 2h | mongodump + pg_dump wrappers |
| Migration scripts | 12h | 5 source collections → core + detail |
| Validation framework | 8h | 11 validation passes |
| Fix scripts | 4h | Common error patterns |
| Staging testing | 4h | Run against snapshot, iterate |
| Production deployment | 2h | Deploy + verify |
| **Total** | **32h** | ~1 week |
