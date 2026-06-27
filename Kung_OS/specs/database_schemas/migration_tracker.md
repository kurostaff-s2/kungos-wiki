# KungOS Data Migration Tracker

**Version:** 1.0
**Date:** 2026-06-27
**Status:** Ready for Deployment

---

## Executive Summary

This tracker documents the complete data migration from MongoDB to PostgreSQL for KungOS. All migrations have been tested and validated in the development environment. This document provides the exact execution sequence, validation checks, and rollback procedures for production deployment.

**Migration Scope:**
- Phase 4A: Orders (estimates, kgorders, tporders, serviceRequest) — **COMPLETED**
- Phase 4B: E-Commerce Products — **COMPLETED**
- Phase 4C: Legacy Cleanup — **COMPLETED**

---

## Pre-Deployment Checklist

- [ ] Production database backup completed
- [ ] MongoDB connection verified from production server
- [ ] PostgreSQL connection verified from application server
- [ ] Migration scripts reviewed by DBA
- [ ] Rollback procedure documented and tested
- [ ] Monitoring alerts configured for migration duration
- [ ] Maintenance window scheduled
- [ ] Team on standby during migration

---

## Phase 4A: Orders Migration

**Status:** ✅ Completed (Development)
**Production Execution:** Pending

### Source Collections

| Collection | Record Count | Order Type |
|------------|--------------|------------|
| estimates | 4,308 | estimate |
| kgorders | 9,162 | in_store |
| tporders | 229 | tp |
| serviceRequest | 1,625 | service |
| **Total** | **15,324** | |

### Target Tables

| Table | Records | FK Reference |
|-------|---------|--------------|
| orders_core | 15,324 | customer → users.identity |
| estimate_detail | 4,308 | order → orders_core |
| in_store_detail | 9,162 | order → orders_core |
| tp_order_detail | 229 | order → orders_core |
| service_detail | 1,625 | order → orders_core |
| eshop_detail | 0 | order → orders_core |

### Execution Steps

```bash
# 1. Verify source data
python3 manage.py migrate_orders --validate

# Expected output:
# ✅ Row count reconciliation:
#    estimate: 4308 in PostgreSQL
#    in_store: 9162 in PostgreSQL
#    tp: 229 in PostgreSQL
#    service: 1625 in PostgreSQL
# ✅ FK integrity: ~347 orders without customer (walk-ins)
# ✅ Tenant codes: 0 invalid bg_code
# ✅ Financial total: ₹1,129,900,701.72

# 2. Run dry run (validation only)
python3 manage.py migrate_orders --dry-run

# 3. Execute migration
python3 manage.py migrate_orders

# 4. Post-migration validation
python3 manage.py migrate_orders --validate
```

### Validation Checks

| Check | Expected | Status |
|-------|----------|--------|
| Total records migrated | 15,324 | ✅ |
| Estimate records | 4,308 | ✅ |
| In-store records | 9,162 | ✅ |
| TP records | 229 | ✅ |
| Service records | 1,625 | ✅ |
| Invalid bg_code | 0 | ✅ |
| Walk-in orders (no customer) | ~347 | ✅ |
| Financial total | ₹1.13B | ✅ |

### Known Data Issues

1. **Email in phone field**: Some documents have email addresses in `user.phone` field. These are migrated to `customer_email` instead.
2. **Empty date strings**: Empty strings converted to `NULL` for DateField columns.
3. **Walk-in orders**: ~347 orders have no linked customer (unregistered users). These are valid and expected.

### Rollback Procedure

```bash
# 1. Stop application
systemctl stop kungos

# 2. Drop migrated tables
python3 -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    tables = ['estimate_detail', 'in_store_detail', 'tp_order_detail', 'service_detail', 'eshop_detail', 'orders_core']
    for table in tables:
        cursor.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
"

# 3. Restore from backup
# (Restore PostgreSQL from pre-migration backup)

# 4. Restart application
systemctl start kungos
```

---

## Phase 4B: E-Commerce Products Migration

**Status:** ✅ Completed (Development)
**Target:** Consolidate into `KungOS_Mongo_One`

### Scope

- 12 e-commerce product collections migrated from `products` DB to `KungOS_Mongo_One`
- Canonical tenant fields injected (bg_code, div_code, branch_code)
- Compound indexes created (bg_code, div_code)
- JSON Schema validation enabled

### Migration Results

| Collection | Records | Status |
|------------|---------|--------|
| prods | 2,459 | ✅ |
| builds | 258 | ✅ |
| kgbuilds | 516 | ✅ |
| custombuilds | 1,995 | ✅ |
| components | 1,614 | ✅ |
| accessories | 504 | ✅ |
| monitors | 156 | ✅ |
| networking | 17 | ✅ |
| external | 12 | ✅ |
| kurodata | 2 | ✅ |
| lists | 3 | ✅ |
| presets | 38 | ✅ |
| **Total** | **7,574** | ✅ |

### Execution Steps

```bash
# 1. Validate
python3 manage.py mongo_migrate_eshop --validate

# 2. Dry run
python3 manage.py mongo_migrate_eshop --dry-run

# 3. Execute
python3 manage.py mongo_migrate_eshop

# 4. Post-migration validation
python3 manage.py mongo_migrate_eshop --validate
```

---

## Phase 4C: Legacy Cleanup

**Status:** ✅ Completed (Development)

### Target Removals

| Entity | Type | Status | Notes |
|--------|------|--------|-------|
| `caf_platform_users` | PostgreSQL table | ✅ Dropped | Empty table, dead model |
| `misc` | MongoDB collection | ⚠️ Deferred | NOT a duplicate — has 1,299 unique phones |

### Execution Steps

```bash
# 1. Apply migration to drop caf_platform_users
python3 manage.py migrate cafe_arcade 0004

# 2. Verify table dropped
python3 -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django; django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'caf_platform_users'\")
    print('Dropped' if cursor.fetchone() is None else 'Still exists')
"
```

### Validation

- [x] caf_platform_users table dropped
- [x] CafeUser model removed
- [x] No broken imports
- [x] All tests passing (70/70)
- [x] misc collection NOT dropped (has unique data)

### Known Issue: misc Collection

The spec claims `misc` is a "100% duplicate" of `reb_users`, but analysis shows:
- `misc`: 5,512 docs, 3,279 unique phones
- `reb_users`: 1,982 docs, 1,980 unique phones
- **Overlap**: 1,980 phones
- **misc-only**: 1,299 phones (unique data not in reb_users)

**Recommendation**: Defer drop until proper migration plan is created.

---

## Deployment Sequence

```
1. Pre-flight checks (15 min)
   ├─ Verify backups
   ├─ Check connections
   └─ Confirm maintenance window

2. Phase 4A Execution (30-60 min)
   ├─ Dry run validation
   ├─ Execute migration
   └─ Post-migration validation

3. Phase 4B Execution (2-4 hours)
   ├─ Inventory collections
   ├─ Define schema
   ├─ Execute migration
   └─ Validate

4. Phase 4C Execution (30 min)
   ├─ Verify no references
   ├─ Drop legacy entities
   └─ Validate

5. Post-deployment (1 hour)
   ├─ Run full test suite
   ├─ Smoke test critical paths
   └─ Monitor for 24 hours
```

**Total Estimated Duration:** 4-6 hours

---

## Monitoring & Alerts

### During Migration

- **Database connection pool**: Monitor for connection exhaustion
- **Migration command output**: Log all stdout/stderr
- **PostgreSQL slow queries**: Enable query logging
- **MongoDB read throughput**: Monitor for lock contention

### Post-Migration (24 hours)

- **Application errors**: Alert on any 5xx errors
- **Database performance**: Monitor query latency
- **Data consistency**: Run reconciliation checks hourly
- **User reports**: Track support tickets for data issues

---

## Contact & Escalation

| Role | Name | Contact |
|------|------|---------|
| Migration Lead | [TBD] | [TBD] |
| DBA | [TBD] | [TBD] |
| On-call Engineer | [TBD] | [TBD] |

---

## Appendix A: Migration Command Reference

### Orders Migration

```bash
# Validate without executing
python3 manage.py migrate_orders --validate

# Dry run (shows counts, no writes)
python3 manage.py migrate_orders --dry-run

# Execute migration
python3 manage.py migrate_orders

# Custom source (if needed)
python3 manage.py migrate_orders --source mongodb://user:pass@host:port/db
```

### Validation Output Format

```
Running validation checks...

✅ Row count reconciliation:
   estimate: 4308 in PostgreSQL
   in_store: 9162 in PostgreSQL
   tp: 229 in PostgreSQL
   service: 1625 in PostgreSQL

✅ FK integrity: 347 orders without customer (walk-ins)
✅ Tenant codes: 0 invalid bg_code
✅ Financial total: ₹1,129,900,701.72

✅ Detail tables:
   estimate_detail: 4308
   in_store_detail: 9162
   tp_order_detail: 229
   service_detail: 1625
   eshop_detail: 0 (Phase 4B)
```

---

## Appendix B: Field Mapping Reference

### MongoDB → PostgreSQL Field Mapping

| MongoDB Field | PostgreSQL Field | Type | Notes |
|---------------|------------------|------|-------|
| `_id` | `order_id` | varchar(50) | Unique identifier |
| `user.name` | `customer_name` | varchar(200) | From user dict |
| `user.phone` | `customer_phone` | varchar(50) | E.164 normalized |
| `user.phone` (if email) | `customer_email` | varchar(254) | Email detection |
| `user.email` | `customer_email` | varchar(254) | Direct email |
| `bg_code` | `bg_code` | varchar(10) | Tenant code |
| `div_code` | `div_code` | varchar(20) | Division code |
| `branch_code` | `branch_code` | varchar(30) | Branch code |
| `total_amount` / `totalprice` | `total_amount` | decimal(12,2) | Financial |
| `status` | `status` | varchar(20) | Order status |
| `products` | `products` | JSON | Product list |
| `billadd` | `bill_address` | JSON | Billing address |

---

## Appendix C: Test Results

### Development Environment

```
Ran 70 tests in 0.234s
OK
```

### Test Coverage

- OrderCore model fields and constraints
- Customer FK relationship (Identity)
- Detail table relationships (one-to-one)
- Cascade delete behavior
- PROTECT on customer deletion
- Financial data storage
- Product JSON data
- Email field handling
- Date field handling (nullable)
- Walk-in orders (no customer)
- Unique constraints
- Default values
- MongoDB field naming (bg_code canonical)
- MongoDB compound indexes
- E-commerce collection counts
- Tenant isolation (bg_code filter)
- caf_platform_users table dropped
- CafeUser model removed
- RLS tables list updated
- misc collection status (deferred)

---

**Document Version History:**

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-27 | Initial creation |
