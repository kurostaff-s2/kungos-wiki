# Cross-Reference: db_testing-claude.md vs. kungos_mongo_divergence.md

**Date:** 2026-04-28

---

## What db_testing-claude Gets Right (11/11 — Excellent Coverage)

| Topic | Verdict | Notes |
|---|---|---|
| 7 wrong PG table names | ✅ Exact match | All corrected to `caf_platform_*` |
| Accesslevel varchar not integer | ✅ Exact match | Only `id` and `analytics` are integer |
| UserTenantContext `scope` not `scope_type` | ✅ Exact match | Confirmed in ground truth |
| OutboxEvent PK = `event_id` (uuid) | ✅ Exact match | Not `id` (bigint) |
| Wallet balance has no default | ✅ Exact match | Must be supplied by app |
| MongoDB DB name `KungOS_Mongo_One` | ✅ Exact match | Underscores, not camelCase |
| gamers/stations/cafepayments → PostgreSQL | ✅ Exact match | Moved to `caf_platform_*` tables |
| `reb_users` not `rebusers` | ✅ Exact match | Underscore in collection name |
| Entity distribution 56.8%/43.2% | ✅ Exact match | Only 2 entities, no legacy |
| 21 collections without tenant fields | ✅ Exact match | Same 21 collections identified |
| Management command existence | ✅ Exact match | 9 confirmed exists, 2 confirmed missing |

**The entire PostgreSQL schema validation and MongoDB schema validation in db_testing-claude is correct.** The 5 correction tables it includes match our ground-truth findings exactly.

---

## What db_testing-claude Misses (5/5 — Major Gaps)

| Gap | Impact | db_testing-claude Coverage |
|---|---|---|
| **13 gaming collections missing** | Gaming storefront broken | ❌ Not covered at all |
| **kuro-gaming-dj-backend not merged** | No gaming apps in INSTALLED_APPS | ❌ Not covered |
| **5 gaming PG models missing** | Cart, Wishlist, Addresslist, Orders, OrderItems | ❌ Not covered |
| **Per-BG routing stale line numbers** | Line refs may drift over time | ✅ Lines 288/339 still correct but fragile |
| **`tempproducts` collection referenced by gaming code** | Would fail if gaming code runs | ❌ Not covered |

The db_testing-claude file was generated from the **kungos_db_test_plan.md** ground-truth dump, which only covered the PostgreSQL schema and MongoDB collection structure. It never considered the gaming backend integration gap.

---

## What db_testing-claude Has Wrong (Code Quality)

### Syntax Errors — `[^0]` Instead of `[0]`

The code uses `[^0]` throughout (likely an artifact of markdown rendering or copy-paste). **This would cause SyntaxError on every test:**

```python
# WRONG (db_testing-claude):
row[^0]: {"type": row[^1], "nullable": row[^2] == "YES"}
cur.fetchone()[^0]
[r[^0] for r in rows]
k[^0] == "bgcode"

# CORRECT:
row[0]: {"type": row[1], "nullable": row[2] == "YES"}
cur.fetchone()[0]
[r[0] for r in rows]
k[0] == "bgcode"
```

**Count: 22 instances of `[^0]` across all 5 files.** Every single one would cause a `SyntaxError`.

### Other Code Issues

| Issue | Location | Severity |
|---|---|---|
| `settings.MONGO_URI` vs `settings.MONGO_DB_URI` | `conftest.py` | ⚠️ Would fail — setting is `MONGO_DB_URI` |
| `MONGO_DB_NAME` in conftest but not used consistently | `test_db_schema_mongodb.py` | ⚠️ Uses `mongo_db` fixture directly |
| `test_no_tenant_collections_acknowledged` is trivial | `test_db_schema_mongodb.py` | 🟡 `assert count >= 0` does nothing |
| `test_document_count` tolerance too wide | `test_db_schema_mongodb.py` | 🟡 2000 doc tolerance on 68k total |
| `test_per_BG_routing_static_scan` hardcodes line numbers | `test_tenant_isolation.py` | 🟡 Should search all lines, not just 288/339 |

---

## What's Worth Incorporating Into Our Plan

### ✅ Copy-Paste Worthy (After Fixing Syntax)

1. **`test_db_schema_postgres.py`** — 45 tests, all correct assertions, just needs `[^0]` → `[0]` fix
2. **`test_db_schema_mongodb.py`** — 25 tests, excellent structure with `TENANT_SCOPED_COLLECTIONS`/`NO_TENANT_COLLECTIONS`/`MISSING_COLLECTIONS` lists
3. **`test_data_quality.py`** — 20 tests, all correct SQL queries against actual table/column names
4. **`tests/conftest.py`** — Helper functions `pg_columns()`, `pg_table_exists()`, `pg_indexes()`, `pg_unique_cols()` are solid

### ⚠️ Needs Adjustment

5. **`test_tenant_isolation.py`** — Good structure but:
   - Change per-BG scan to search all lines (not hardcoded 288/339)
   - Fix `settings.MONGO_URI` → `settings.MONGO_DB_URI`
   - The `test_wrong_bgcode_returns_empty` test needs `TenantContextMissing` raised before context is set — current code sets context first, then checks. Should test both: (a) missing context raises, (b) wrong context returns empty.

6. **`test_migration_commands.py`** — Good but:
   - `test_dry_run_reports_47k_docs` should use 68,441 (current count) not 47,009 (old count from backup file)
   - Add test for `reconcile_user_models` command existence

### ❌ Not Worth Incorporating

7. **Nothing** — all 5 files have value, but everything needs the `[^0]` → `[0]` fix

---

## Recommended Action

**Merge db_testing-claude into our plan with 3 changes:**

1. **Fix all `[^0]` → `[0]`** (22 instances) — mechanical change
2. **Add a 6th test file: `test_gaming_integration.py`** — covers the gaps:
   - Verify 13 gaming collections are MISSING (not yet merged)
   - Verify 5 gaming apps are NOT in INSTALLED_APPS
   - Verify 5 gaming PG models do NOT exist
   - Verify kuro-gaming-dj-backend code references collections that don't exist
   - Mark all as `pytest.mark.skip(reason="Phase 3: gaming integration pending")` with tracking
3. **Fix `settings.MONGO_URI` → `settings.MONGO_DB_URI`** in conftest

This gives us a **complete test suite** that covers:
- ✅ PostgreSQL schema (11 tables, 190+ columns)
- ✅ MongoDB schema (30 collections, 68k docs)
- ✅ Migration commands (9 existing, 2 missing)
- ✅ Tenant isolation (wrapper, routing scan, RLS)
- ✅ Data quality (wallets, sessions, stations, price plans)
- ✅ Gaming integration status (13 missing collections, 5 missing apps)
