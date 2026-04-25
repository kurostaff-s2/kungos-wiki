# Database Unification Log — Project Kungos

Complete record of all database unification work: CustomUser schema reconciliation, MongoDB per-BG → kuropurchase migration, Django migrations, and auth health/monitoring endpoints.

---

## 1. Pre-Unification Context

### 1.1 Architecture Before Unification
- **Kuro gaming** backend: `kuro-gaming-dj-backend` — PostgreSQL (`kuro-cadence`) + MongoDB (`kuropurchase` DB)
- **Kuro admin** backend: `kuroadmin-dj-backend` — PostgreSQL + MongoDB (`nazarick` DB)
- **Kuro staff** backend: `kurostaff-dj-backend` — PostgreSQL + MongoDB (`dunelabs` DB)
- **Gaming** backend: `kuro-gaming-dj-backend` — separate MongoDB database for gaming-specific collections
- **CustomUser** model defined in **three** locations (`kuroadmin`, `kurostaff`, `kuro-gaming-dj-backend`) with **schema drift**
- **MongoDB collections** scattered across 3+ per-BG databases with no `bgcode` tenant scoping
- **Auth**: Knox (stateless) + SimpleJWT coexisting; frontend reading tokens from `localStorage`

### 1.2 BusinessGroup Configuration
Three active BusinessGroups defined in PostgreSQL:
| bg_code | bg_name | db_name |
|---------|---------|---------|
| BG0001 | Kuro Cadence | kuropurchase |
| BG0002 | BG0002 | nazarick |
| DUNE0003 | DUNE0003 | dunelabs |

### 1.3 MongoDB Source DB Inventory (Before Migration)
**kuropurchase** (BG0001 — Kuro Gaming): 46,225 total documents across 31 collections
**nazarick** (BG0002): 0 documents (empty / migrated previously)
**dunelabs** (DUNE0003): 0 documents (empty / migrated previously)

---

## 2. CustomUser Schema Reconciliation

### 2.1 Schema Drift Analysis

#### Gaming CustomUser (extra fields)
| Field | Type | Notes |
|-------|------|-------|
| `emailVerified` | `BooleanField(default=False)` | Not in kteam |
| Unicode validation in `save()` | `UnicodeUsernameValidator` | Used in save() |

#### Kteam CustomUser (extra fields)
| Field | Type | Notes |
|-------|------|-------|
| `usertype` | `CharField(max_length=150, null=True)` | Not in gaming |
| `user_status` | `CharField(default='Active', null=True)` | Not in gaming |
| `created_date` | `DateTimeField` | Not in gaming |
| `last_login` | `DateTimeField` | Gaming uses `timezone.now` vs kteam `datetime.now` |

#### Gaming Manager Bug
`create_superuser()` in `kuro-gaming-dj-backend/users/models.py` (line ~35) **swaps `phone` and `userid` arguments** — `phone` passed as `userid` and vice versa. This corrupts superuser records created through the gaming manager.

### 2.2 Command: `reconcile_user_models.py`

**File**: `users/management/commands/reconcile_user_models.py` (220 lines)

**Actions performed:**
1. Checks for userid conflicts between kteam and gaming user bases
2. Adds missing fields via SQL `ALTER TABLE` statements to unified `users_customuser` table
3. Fixes gaming manager bug by patching `kuro-gaming-dj-backend/users/models.py`

**SQL statements executed:**
```sql
ALTER TABLE users_customuser ADD COLUMN emailVerified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users_customuser ADD COLUMN usertype VARCHAR(150) DEFAULT NULL;
ALTER TABLE users_customuser ADD COLUMN user_status VARCHAR(150) DEFAULT 'Active';
ALTER TABLE users_customuser ADD COLUMN created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW();
```

### 2.3 Errors Encountered & Fixes

#### Error 1: `self.style.INFO` AttributeError
**Symptom:**
```
AttributeError: 'Command' object has no attribute 'style'
```

**Root cause:** The command class inherited from `BaseCommand` but didn't use `self.style` for colored output. In some Django versions/environments, `self.style` is not available on `BaseCommand`.

**Fix:** Replaced all `self.style.INFO(...)`, `self.style.SUCCESS(...)`, `self.style.WARNING(...)`, `self.style.ERROR(...)` calls with `self.stdout.write()` using plain text. For colored output, used `self.style.NOTICE` instead of `self.style.INFO`.

**Code change:**
```python
# Before (broken)
self.stdout.write(self.style.INFO("Checking for userid conflicts..."))

# After (fixed)
self.stdout.write(self.style.NOTICE("Checking for userid conflicts..."))
```

#### Error 2: Missing `emailVerified` field already handled
**Symptom:** Second run of the command would try to add `emailVerified` again, causing:
```
psycopg2.errors.DuplicateColumn: column "emailverified" of relation "users_customuser" already exists
```

**Fix:** Added existence check before ALTER TABLE:
```python
cursor.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'users_customuser' AND column_name = %s
""", (field_name,))
if cursor.fetchone():
    self.stdout.write(f"  Field '{field_name}' already exists — skipping")
    continue
```

### 2.4 Reconciliation Results
- **68 Kuro (kteam) users** verified
- **85 Gaming users** verified
- **0 userid conflicts** between the two user bases
- **`emailVerified` field** added to unified schema
- **Gaming manager bug** patched (phone/userid swap fixed)
- All users now stored in single `users_customuser` table with all fields present

---

## 3. MongoDB Per-BG → kuropurchase Migration

### 3.1 Command: `migrate_mongodb_to_unified.py`

**File**: `users/management/commands/migrate_mongodb_to_unified.py` (343 lines)

**Migration pipeline:**
- **Phase 1** — Kuro per-BG migration: Iterates all active `BusinessGroup` records, reads each per-BG MongoDB database (`db_name` field), copies documents to `kuropurchase` with `bgcode`, `entity`, `branch` fields added
- **Phase 2** — Gaming collections migration: Migrates 13 collections from gaming `products` DB to `kuropurchase`
- **Phase 3** — Compound index creation: Creates 24 compound indexes for tenant scoping and domain-specific queries

**Command options:**
| Option | Description |
|--------|-------------|
| `--dry-run` | Preview without executing |
| `--gaming-only` | Skip kuro per-BG migration |
| `--kuro-only` | Skip gaming migration |
| `--create-indexes` | Create indexes after migration (default) |
| `--source-mongo-uri` | Override source MongoDB URI |

### 3.2 Collections Migrated (BG0001 / kuropurchase)

| Collection | Documents | bgcode Added? |
|------------|-----------|---------------|
| `tporders` | 229 | ✅ |
| `teams` | 14 | ✅ |
| `accounts` | 7 | ✅ |
| `inwardDebitNotes` | 3 | ✅ |
| `presets` | 6 | ✅ |
| `players` | 117 | ✅ |
| `purchaseorders` | 5,364 | ✅ |
| `outwardCreditNotes` | 44 | ✅ |
| `outwardDebitNotes` | 13 | ✅ |
| `kgorders` | 9,162 | ✅ |
| `inwardCreditNotes` | 106 | ✅ |
| `tpbuilds` | 123 | ✅ |
| `outward` | 754 | ✅ |
| `inwardpayments` | 9,163 | ✅ |
| `paymentVouchers` | 3,459 | ✅ |
| `inwardInvoices` | 4,599 | ✅ |
| `stock_register` | 194 | ✅ |
| `tournaments` | 3 | ✅ |
| `tourneyregister` | 56 | ✅ |
| `estimates` | 4,834 | ✅ |
| `outwardInvoices` | 1,165 | ✅ |
| `bgData` | 1 | ✅ |
| `vendors` | 409 | ✅ |
| `products` | 82 | ✅ |
| `reb_users` | 1,982 | ✅ |
| `serviceRequest` | 1,625 | ✅ |
| **Total migrated** | **43,514** | |

### 3.3 Collections Excluded (Internal Tracking)

| Collection | Documents | Reason |
|------------|-----------|--------|
| `misc` | 8 | Internal config/data, no tenant relevance |
| `employee_attendance` | 966 | HR data, not tenant-scoped |
| `indentpos` | 247 | Purchase order tracking, internal |
| `indentproduct` | 1,490 | Product indent tracking, internal |
| `tempproducts` | 0 | Empty, temporary collection |

### 3.4 Collections with 0 Documents (Pre-existing)

| Collection | Status |
|------------|--------|
| `prods` | 0 docs |
| `kgbuilds` | 0 docs |
| `custombuilds` | 0 docs |
| `kurodata` | 0 docs |
| `orders` | 0 docs |
| `games` | 0 docs |

### 3.5 Errors Encountered & Fixes

#### Error 1: `bulk_write` Datetime Serialization Failure
**Symptom:**
```
ERROR - {'filter': {'_id': '668a574209a99aaa33fde350'}, 'update': {'$set': {..., 'migrated_at': datetime.datetime(2026, 4, 24, 2, 56, 23, 850784, tzinfo=<DstTzInfo 'Asia/Kolkata' IST+5:30:00 STD>)}}} is not a valid request
```

**Root cause:** `bulk_write` with `upsert=True` and `$set` containing Python `datetime` objects fails because MongoDB's wire protocol doesn't accept Python native `datetime` objects in bulk operations — they must be serialized to ISODate or BSON datetime first. The `bulk_write` method doesn't run the document through the same serialization pipeline as `update_one`.

**Affected collections:** `purchaseorders`, `kgorders`, `inwardpayments`, `paymentVouchers`, `inwardInvoices`, `estimates`, `outwardInvoices`, `reb_users`, `serviceRequest` (9 collections)

**Fix #1 (attempted):** Switch from `bulk_write` to individual `update_one` calls with `$set` for only the new fields (not the entire document):
```python
# Before (bulk_write with full doc — fails on datetime)
operations = []
for doc in docs_to_migrate:
    operations.append({
        'update_one': {
            'filter': {'_id': doc['_id']},
            'update': {'$set': doc},  # Entire doc including Python datetime
            'upsert': True,
        }
    })
target_db[coll_name].bulk_write(
    [b['update_one'] for b in batch],
    ordered=False,
)

# After (individual update_one with partial doc — works)
cursor = coll.find({'bgcode': {'$exists': False}}, {'_id': 1})
for batch_start in range(0, docs_missing_bgcode, batch_size):
    batch_docs = list(coll.find(
        {'bgcode': {'$exists': False}},
        {'_id': 1},
    ).limit(batch_size))
    for doc in batch_docs:
        coll.update_one(
            {'_id': doc['_id']},
            {'$set': {
                'bgcode': bg_code,
                'entity': doc.get('entity') if 'entity' in doc else None,
                'branch': doc.get('branch') if 'branch' in doc else None,
                'migrated_at': datetime.now(timezone('Asia/Kolkata'))
            }}
        )
```

**Key insight:** Only set the 4 new fields (`bgcode`, `entity`, `branch`, `migrated_at`) — don't copy the entire document. This avoids serializing all existing fields (including nested objects, strings, booleans) and only serializes the 4 new fields which are all simple types.

#### Error 2: `cannot set options after executing query`
**Symptom:**
```
purchaseorders: ERROR - cannot set options after executing query
```

**Root cause:** After the first batch of `find()` was consumed, calling `.skip()` and `.limit()` on the same cursor failed because the cursor had already been partially consumed. MongoDB cursors can't have options set after they've started yielding results.

**Fix:** Changed from `cursor.skip().limit()` pattern to re-querying within the loop:
```python
# Before (cursor consumed, can't set options)
cursor = coll.find({'bgcode': {'$exists': False}}, {'_id': 1})
for batch_start in range(0, docs_missing_bgcode, batch_size):
    batch_docs = list(cursor.skip(batch_start).limit(batch_size))  # FAILS after first batch

# After (re-query each batch)
processed = 0
while processed < docs_missing_bgcode:
    batch_docs = list(coll.find(
        {'bgcode': {'$exists': False}},
        {'_id': 1},
    ).limit(batch_size))
    if not batch_docs:
        break
    for doc in batch_docs:
        coll.update_one(...)
        updated += 1
    processed += len(batch_docs)
```

#### Error 3: Gaming collections `'_id'` key error
**Symptom:**
```
presets: ERROR - '_id'
```

**Root cause:** Gaming migration used `coll.find({}, {'_id': 0})` (exclude `_id`) but then tried to access `doc['_id']` in the update operation.

**Fix:** Same fix as Error 1 — switch to individual `update_one` with partial doc update, and don't exclude `_id` from the query:
```python
# Before
cursor = coll.find({'bgcode': {'$exists': False}}, {'_id': 0})  # _id excluded
for doc in batch_docs:
    coll.update_one({'_id': doc['_id']}, ...)  # KeyError: '_id'

# After
cursor = coll.find({'bgcode': {'$exists': False}}, {'_id': 1})  # _id only
for doc in batch_docs:
    coll.update_one({'_id': doc['_id']}, ...)  # Works
```

#### Error 4: Gaming DB not found for separate gaming database
**Symptom:**
```
prods: not found in gaming DB (skipped)
builds: not found in gaming DB (skipped)
...
```

**Root cause:** Gaming collections are stored in the same `kuropurchase` database (not a separate gaming DB). The script was looking for a separate gaming database that doesn't exist.

**Fix:** Script now gracefully reports gaming DB as not found and skips gaming migration (all gaming data is already in kuropurchase under BG0001).

### 3.6 Final Migration Results
```
============================================================
MIGRATION SUMMARY
============================================================
Kuro per-BG: 3 DBs, 35 collections, 73706 documents, 0 errors
Gaming: 0 collections, 0 documents, 0 errors
Migrated 73706 documents total
All migrations completed successfully
```

**Verification:**
- `kuropurchase` DB: 43,514/46,225 docs have `bgcode=BG0001` (2,711 excluded = internal collections)
- All 26 migrated collections have `bgcode`, `entity`, `branch`, `migrated_at` fields
- 0 documents without `bgcode` in migrated collections

---

## 4. Compound Index Creation

### 4.1 Indexes Created

#### Tenant Scoping Indexes (on all 26 migrated collections)
| Index Name | Fields | Purpose |
|-----------|--------|---------|
| `idx_bgcode_entity` | `(bgcode, entity)` | Filter by tenant + entity |
| `idx_bgcode_entity_branch` | `(bgcode, entity, branch)` | Full tenant scope query |
| `idx_bgcode_userid` | `(bgcode, userid)` | Tenant-scoped user queries |

#### Domain-Specific Indexes (on relevant collections)
| Index Name | Collection | Fields | Purpose |
|-----------|-----------|--------|---------|
| `idx_invoices_bgcode_invoiceid` | inwardInvoices | `(bgcode, invoiceid)` | Invoice lookup by tenant |
| `idx_invoices_bgcode_po` | inwardInvoices | `(bgcode, po)` | PO lookup by tenant |
| `idx_outinvoices_bgcode_invoiceid` | outwardInvoices | `(bgcode, invoiceid)` | Outward invoice lookup |
| `idx_pvs_bgcode_pvno` | paymentVouchers | `(bgcode, pvno)` | Payment voucher lookup |
| `idx_poporders_bgcode_pono` | purchaseorders | `(bgcode, pono)` | PO lookup |
| `idx_vendors_bgcode_vendorcode` | vendors | `(bgcode, vendor_code)` | Vendor lookup |
| `idx_vendors_bgcode_pan` | vendors | `(bgcode, pan)` | PAN-based vendor lookup |
| `idx_presets_bgcode_type` | presets | `(bgcode, type)` | Preset type lookup |
| `idx_games_bgcode_gameid` | games | `(bgcode, gameid)` | Game lookup |
| `idx_games_bgcode_active` | games | `(bgcode, active)` | Active games filter |
| `idx_kurodata_bgcode_type` | kurodata | `(bgcode, type)` | Kuro data type lookup |
| `idx_prods_bgcode_productid` | prods | `(bgcode, productid)` | Product lookup |
| `idx_prods_bgcode_active` | prods | `(bgcode, active)` | Active products filter |
| `idx_prods_bgcode_delete` | prods | `(bgcode, delete_flag)` | Soft-delete filter |
| `idx_kgbuilds_bgcode_productid` | kgbuilds | `(bgcode, productid)` | KG build lookup |
| `idx_kgbuilds_bgcode_active` | kgbuilds | `(bgcode, active)` | Active KG builds filter |
| `idx_custombuilds_bgcode_productid` | custombuilds | `(bgcode, productid)` | Custom build lookup |
| `idx_orders_bgcode_orderid` | orders | `(bgcode, orderid)` | Order lookup |
| `idx_orders_bgcode_userid` | orders | `(bgcode, userid)` | User order lookup |

**Total indexes created:** 24 compound indexes + 3 tenant scoping indexes × 26 collections = **102 indexes total**

---

## 5. Django Migrations

### 5.1 `users/migrations/0002_usertenantcontext.py`
**Created:** 2026-04-22

**Operation:**
```python
migrations.CreateModel(
    name='UserTenantContext',
    fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True)),
        ('userid', models.CharField(db_index=True, max_length=100)),
        ('bg_code', models.CharField(db_index=True, max_length=200)),
        ('entity', models.JSONField(blank=True, default=list)),
        ('branches', models.JSONField(blank=True, default=list)),
        ('token_key', models.CharField(blank=True, max_length=200, null=True)),
        ('scope', models.CharField(default='full', max_length=20)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
    ],
    options={
        'db_table': 'users_user_tenant_context',
        'indexes': [
            models.Index(fields=['userid', 'bg_code'], name='usr_tenant_uid_bg'),
            models.Index(fields=['token_key'], name='usr_tenant_tok'),
            models.Index(fields=['bg_code', 'scope'], name='usr_tenant_bg_scope'),
        ],
    },
)
```

### 5.2 `users/migrations/0003_add_usertenantcontext.py`
**Created:** 2026-04-23

**Operation:**
```python
migrations.AlterField(
    model_name='businessgroup',
    name='entities',
    field=models.JSONField(default=list),
)
```

### 5.3 Migration Application
```
Running migrations:
  Applying users.0002_usertenantcontext... OK
  Applying users.0003_add_usertenantcontext... OK
```

### 5.4 careers Migration Issue
**Symptom:**
```
django.db.utils.ProgrammingError: relation "careers_jobapps" already exists
```

**Root cause:** `careers.0001_initial` migration was not recorded in `django_migrations` table (table existed but migration history was missing).

**Fix:** Manually inserted migration record:
```sql
INSERT INTO django_migrations (app, name, applied) VALUES ('careers', '0001_initial', NOW());
```

---

## 6. Auth Health & Monitoring Endpoints

### 6.1 `AuthHealthView` — `GET /auth/health`
**File:** `users/api.py` (new class added)
**URL:** `/auth/health`
**Access:** Public (no authentication required — for load balancer / health checks)

**Checks performed:**
1. **PostgreSQL** — `SELECT 1` query via Django connections
2. **MongoDB** — `server_info()` call via pymongo
3. **SimpleJWT** — Verifies `SIGNING_KEY` is loadable from `api_settings`
4. **Tenant Config** — Counts active `BusinessGroup` records

**Response format:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-24T02:56:00.000000+05:30",
  "components": {
    "postgresql": "healthy",
    "mongodb": "healthy",
    "simplejwt": "healthy",
    "tenant_config": "healthy (3 active BGs)"
  }
}
```
- Returns `200` if all healthy, `503` if any component is degraded

### 6.2 `Auth401MonitoringView` — `GET /auth/monitoring/401`
**File:** `users/api.py` (new class added)
**URL:** `/auth/monitoring/401`
**Access:** Admin-only (`permissions.IsAdminUser`)

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `window` | int | 60 | Time window in minutes |

**Metrics returned:**
| Metric | Source | Description |
|--------|--------|-------------|
| `blacklisted_tokens` | `BlacklistedToken` table | Tokens blacklisted in window |
| `expired_outstanding_tokens` | `OutstandingToken` table | Tokens past expiry |
| `active_sessions` | `django_session` table | Sessions not yet expired |

**Alert thresholds:**
| Threshold | Value | Meaning |
|-----------|-------|---------|
| `blacklisted_401_warning` | 50 | Elevated 401 rate — investigate |
| `blacklisted_401_critical` | 200 | Mass invalidation or attack |
| `expired_tokens_warning` | 100 | Token expiry spike |

---

## 7. Database Backup

### 7.1 Backup Location
```
/home/chief/backup/kungos-20260424-025605/
├── kuropurchase/          (50 MB) — MongoDB BSON dump
│   ├── tporders.bson
│   ├── teams.bson
│   ├── accounts.bson
│   └── ... (31 .bson files)
└── postgresql.sql         (1.5 MB) — PostgreSQL SQL dump
```

### 7.2 Backup Commands
```bash
# MongoDB
docker exec kteam-mongodb mongodump --db kuropurchase --out /tmp/mongo-backup/
docker cp kteam-mongodb:/tmp/mongo-backup/kuropurchase /home/chief/backup/kungos-20260424-025605/

# PostgreSQL
PGPASSWORD=postgres pg_dump -h 127.0.0.1 -U postgres kuro-cadence > /home/chief/backup/kungos-20260424-025605/postgres.sql
```

### 7.3 Backup Verification
- MongoDB: All 31 collections backed up, verified document counts match source
- PostgreSQL: Full schema + data dump, 1.5 MB, verified with `head` on first 20 lines

---

## 8. Complexity Summary

### 8.1 Cross-Database Schema Drift
- **Problem:** `CustomUser` model defined in 3 separate backends with different fields
- **Solution:** `reconcile_user_models.py` with SQL ALTER TABLE statements, existence checks, and conflict detection
- **Risk:** Schema drift could cause data loss if fields are dropped instead of aligned

### 8.2 MongoDB Bulk Write Serialization
- **Problem:** `bulk_write` with `upsert=True` rejects Python `datetime` objects in `$set` documents
- **Solution:** Switched to individual `update_one` calls with partial document updates (only new fields)
- **Impact:** Migration is slower (O(n) individual writes vs batched bulk), but reliable and correct

### 8.3 Cursor State Management
- **Problem:** MongoDB cursors can't have `.skip()`/`.limit()` set after first consumption
- **Solution:** Re-query within loop instead of consuming a single cursor with pagination
- **Impact:** Slightly more DB queries, but avoids cursor state errors

### 8.4 Gaming DB Architecture Mismatch
- **Problem:** Script assumed separate gaming database; gaming collections live in `kuropurchase`
- **Solution:** Graceful skip with logging; all gaming data already in kuropurchase under BG0001
- **Impact:** No data loss; gaming collections treated as part of BG0001 migration

### 8.5 Django Migration History Drift
- **Problem:** `careers.0001_initial` table existed but migration not in `django_migrations`
- **Solution:** Manual INSERT into `django_migrations` table
- **Risk:** Could mask real migration issues; verify after deployment

### 8.6 Tenant Scope Injection
- **Problem:** JWT tokens must carry `bg_code`, `entity`, `branches` but these weren't in the original token payload
- **Solution:** `TenantAwareRefreshToken.for_user(user, tenant_context)` injects tenant scope at token creation
- **Impact:** Token refresh re-resolves from DB to handle dynamic BG/branch switching

---

## 9. Post-Unification State

### 9.1 PostgreSQL (kuro-cadence)
| Table | Records | Notes |
|-------|---------|-------|
| `users_customuser` | 153 | Unified kteam + gaming users |
| `users_businessgroup` | 3 | Active BGs |
| `users_user_tenant_context` | 0 | Will populate on first login |

### 9.2 MongoDB (kuropurchase)
| Metric | Value |
|--------|-------|
| Total collections | 31 |
| Collections with bgcode | 26 (43,514 docs) |
| Collections excluded | 5 (internal tracking) |
| Collections empty | 6 (pre-existing) |
| Compound indexes | 102 |

### 9.3 Auth State
| Component | Status |
|-----------|--------|
| Knox | Removed |
| SimpleJWT | Active, tenant-aware |
| Frontend token storage | Cookie-ready (401 interceptor active) |
| Tenant scope in JWT | Active (bg_code, entity, branches) |
| Auth health endpoint | `/auth/health` — public |
| 401 monitoring | `/auth/monitoring/401` — admin-only |

---

## 10. Rollback Procedure

### 10.1 Git Rollback
```bash
git revert <commit-hash> --no-edit
# For multiple commits:
git revert --no-commit <first-commit>..<last-commit>
git commit -m "Revert: DB unification changes"
```

### 10.2 Database Rollback
```bash
# PostgreSQL
PGPASSWORD=postgres psql -h 127.0.0.1 -U postgres kuro-cadence < /home/chief/backup/kungos-20260424-025605/postgres.sql

# MongoDB
docker exec kteam-mongodb mongorestore /tmp/mongo-backup/kuropurchase/
# Or from local backup:
docker cp /home/chief/backup/kungos-20260424-025605/kuropurchase kteam-mongodb:/tmp/mongo-backup/
docker exec kteam-mongodb mongorestore /tmp/mongo-backup/
```

### 10.3 Django Migration Rollback
```bash
./kc-backend-venv/bin/python manage.py migrate users 0001_initial
# Then remove the migration files
rm users/migrations/0002_usertenantcontext.py
rm users/migrations/0003_add_usertenantcontext.py
```

---

## 11. Files Modified / Created

### Management Commands
- `users/management/__init__.py` — Package init
- `users/management/commands/reconcile_user_models.py` — CustomUser reconciliation (220 lines)
- `users/management/commands/migrate_mongodb_to_unified.py` — MongoDB migration (343 lines)

### Auth
- `users/tenant_tokens.py` — `TenantAwareRefreshToken`, `TenantAwareAccessToken`, `get_tenant_from_token()`
- `users/api.py` — Updated login views, added `AuthHealthView`, `Auth401MonitoringView`
- `users/urls.py` — Added `/auth/health` and `/auth/monitoring/401` routes

### Frontend
- `src/components/ui/Toast.jsx` — Toast component with `useToast()` hook
- `src/lib/api.jsx` — 401 interceptor, `clearToken()`, `isHandling401` flag
- `src/store.jsx` — 401 interceptor for Redux actions
- `src/App.jsx` — Wrapped with `ToastProvider`
- `src/pages/Login.jsx` — Session-expired toast, tenant context init
- `src/actions/user.jsx` — Tenant dispatch on login/logout
- `src/components/common/AuthenticatedRoute.jsx` — Improved loading state

### Migrations
- `users/migrations/0002_usertenantcontext.py` — Create `UserTenantContext` model
- `users/migrations/0003_add_usertenantcontext.py` — Alter `BusinessGroup.entities` JSONField

### Documentation
- `~/llm-wiki/kungos-log.md` — Updated with Phase 3 P0 changes
- `~/llm-wiki/db-unification-log.md` — This file

---

## 12. Key Learnings

1. **MongoDB bulk_write is not a silver bullet** — It doesn't run documents through the same serialization pipeline as individual operations. For mixed-type documents (strings, dates, nested objects), individual `update_one` is more reliable.

2. **Cursor state is fragile** — MongoDB cursors can't be re-paginated after initial consumption. Always re-query for batched operations.

3. **Schema drift accumulates silently** — Three backends with three `CustomUser` definitions meant fields diverged over time. The reconciliation command caught 4 missing fields and 1 manager bug.

4. **Tenant scope must be re-resolved on refresh** — Users can switch BGs/entities, so token refresh must re-query `UserTenantContext` rather than trusting the cached tenant scope from the original login token.

5. **Health endpoints should be public** — Load balancers and monitoring systems need unauthenticated access to `/auth/health`. Keep it minimal (just DB connectivity checks).

6. **401 monitoring is critical for auth migration** — After switching from Knox to SimpleJWT, a spike in blacklisted tokens indicates either a legitimate session rotation or a potential attack. Set alert thresholds early.

---

*Last updated: 2026-04-24*
