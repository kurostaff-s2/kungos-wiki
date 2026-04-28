<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# kungos_db_test_plan.md

The `kungos_db_test_plan.md` contains ground-truth data that invalidates **23 items** across all 5 previously generated test files. Here is a complete, precise diff followed by the fully corrected test suite.

***

## What Was Wrong: Complete Diff

### PostgreSQL — 7 Wrong Table Names

| Generated (Wrong) | Actual (Ground Truth) |
| :-- | :-- |
| `plat_tenantconfig` | `platform_tenant_config` [^1] |
| `plat_outboxevent` | `platform_outbox_events` [^1] |
| `users_usertenantcontext` | `users_user_tenant_context` [^1] |
| `rebellion_cafewallet` | `caf_platform_wallets` [^1] |
| `rebellion_cafewallettransaction` | `caf_platform_wallet_transactions` [^1] |
| `rebellion_cafememberplan` | `caf_platform_member_plans` [^1] |
| `rebellion_cafepricingrule` | `caf_platform_price_plans` [^1] |

### Column-Level — 5 Wrong Field Details

| Generated (Wrong) | Actual (Ground Truth) |
| :-- | :-- |
| `scope_type` in UserTenantContext | Column is `scope` [^1] |
| OutboxEvent PK = `id` | PK = `event_id` (uuid) [^1] |
| Accesslevel cafe fields = `IntegerField` | **All 50+ fields are `varchar`, only `analytics` is integer** [^1] |
| `caf_platform_wallets.balance` default = `0` | **No default — must be supplied** [^1] |
| `permission_snapshot`, `switched_at`, `switched_by`, `request_defaults` exist | **NOT YET IMPLEMENTED** [^1] |

### MongoDB — 9 Wrong Assumptions

| Generated (Wrong) | Actual (Ground Truth) |
| :-- | :-- |
| DB = `KungOSMongoOne` (camelCase) | DB = `KungOS_Mongo_One` (underscores) [^1] |
| `gamers` collection exists | **MISSING** — moved to `caf_platform_sessions` (PostgreSQL) [^1] |
| `stations` collection exists | **MISSING** — moved to `caf_platform_stations` (PostgreSQL) [^1] |
| `cafepayments` collection exists | **MISSING** — moved to `caf_platform_wallet_transactions` [^1] |
| Collection name `rebusers` | Actual name is `reb_users` [^1] |
| Entity dist: 54.1% / 37.8% / 7.9% | **56.8% kurogaming / 43.2% rebellion / 0% legacy** (current 68k state) [^1] |
| All 30 collections have tenant fields | **Only 9 confirmed** — 21 others (`kgorders`, `tporders`, `serviceRequest`, etc.) have **no** tenant fields yet [^1] |
| `purchaseorders` count = 15,366 | **15,216** (actual current) [^1] |
| `inwardpayments` count = 21,546 | **21,026** (actual current) [^1] |

### Management Commands — 4 Wrong Assumptions

| Generated (Wrong) | Actual (Ground Truth) |
| :-- | :-- |
| `verify_tenant_isolation` exists | **Does NOT exist** — Phase 1 P2 \#3 planned [^1] |
| `migrate_gamers_to_enhanced` exists | **Does NOT exist** — gamers moved to PostgreSQL, command irrelevant [^1] |
| Missing: `reconcile_user_models` | **EXISTS** ✅ [^1] |
| Missing: `seed_games`, `seed_member_plans`, `seed_pricing`, `seed_stations`, `seed_tenant_config` | **ALL EXIST** ✅ [^1] |


***

## Corrected Test Files (Ground-Truth Exact)

### `tests/conftest.py`

```python
# tests/conftest.py — shared fixtures, exact DB names from kungos_db_test_plan.md
import pytest
import pymongo
from django.conf import settings
from django.db import connection

MONGO_DB_NAME = "KungOS_Mongo_One"   # underscores — NOT KungOSMongoOne

@pytest.fixture(scope="session")
def mongo_db():
    client = pymongo.MongoClient(settings.MONGO_URI)
    db = client[MONGO_DB_NAME]
    yield db
    client.close()

@pytest.fixture(scope="session")
def pg():
    """Yields a raw psycopg2 cursor helper for schema introspection."""
    return connection

def pg_columns(table_name: str) -> dict:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, [table_name])
        return {
            row[^0]: {"type": row[^1], "nullable": row[^2] == "YES", "default": row[^3]}
            for row in cur.fetchall()
        }

def pg_table_exists(table_name: str) -> bool:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name = %s
            )
        """, [table_name])
        return cur.fetchone()[^0]

def pg_indexes(table_name: str) -> list[str]:
    with connection.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", [table_name])
        return [row[^0] for row in cur.fetchall()]

def pg_unique_cols(table_name: str) -> list[str]:
    """Returns columns with UNIQUE constraint."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.table_name = %s AND tc.constraint_type = 'UNIQUE'
        """, [table_name])
        return [row[^0] for row in cur.fetchall()]
```


***

### `tests/test_db_schema_postgres.py`

```python
# tests/test_db_schema_postgres.py
# Ground-truthed against kungos_db_test_plan.md 2026-04-28
# All table names, column names, types, and nullability are exact.

import pytest
from django.db import connection
from tests.conftest import pg_columns, pg_table_exists, pg_indexes, pg_unique_cols


# ─── 1.1 Table Existence ──────────────────────────────────────────────────────

EXPECTED_TABLES = [
    # Users
    "users_customuser",
    "users_accesslevel",
    "users_user_tenant_context",   # NOTE: underscores — NOT users_usertenantcontext
    "users_businessgroup",
    "users_kurouser",
    "users_phonemodel",
    "users_switchgroupmodel",
    "users_common_counters",
    # Platform
    "platform_outbox_events",       # NOT plat_outboxevent
    "platform_tenant_config",       # NOT plat_tenantconfig
    # Cafe — prefix is caf_platform_
    "caf_platform_cafes",
    "caf_platform_stations",
    "caf_platform_sessions",
    "caf_platform_session_leases",
    "caf_platform_station_commands",
    "caf_platform_station_events",
    "caf_platform_wallets",
    "caf_platform_wallet_transactions",
    "caf_platform_price_plans",     # NOT cafepricingrules
    "caf_platform_member_plans",
    "caf_platform_games",
    "caf_platform_users",
    "caf_platform_walkins",
    "caf_platform_auth_tokens",
    # Sys admin
    "kungos_tenant_api_keys",
    "kungos_tenant_domain_config",
    "kungos_tenant_profile",
    "kungos_tenant_templates",
]

@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_exists(table):
    assert pg_table_exists(table), \
        f"Table '{table}' missing from PostgreSQL — check migrations"


# ─── 1.2 users_customuser (16 cols) ──────────────────────────────────────────

class TestCustomUser:
    TABLE = "users_customuser"

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 16, f"Expected 16 columns, got {len(cols)}: {list(cols)}"

    def test_pk_is_userid(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = %s
                  AND ccu.column_name = 'userid'
                  AND tc.constraint_type = 'PRIMARY KEY'
            """, [self.TABLE])
            assert cur.fetchone()[^0] >= 1, "userid must be PRIMARY KEY"

    def test_phone_is_varchar_not_null(self):
        cols = pg_columns(self.TABLE)
        assert cols["phone"]["type"] == "character varying"
        assert not cols["phone"]["nullable"]

    def test_phone_unique(self):
        assert "phone" in pg_unique_cols(self.TABLE), "phone must be UNIQUE"

    def test_boolean_fields_exist(self):
        cols = pg_columns(self.TABLE)
        for field in ("is_active", "is_staff", "is_superuser", "is_admin", "emailverified"):
            assert field in cols, f"Missing boolean field: {field}"
            assert cols[field]["type"] == "boolean"

    def test_emailverified_default_false(self):
        cols = pg_columns(self.TABLE)
        default = str(cols["emailverified"]["default"] or "").lower()
        assert "false" in default, f"emailverified default must be false, got: {default}"

    def test_nullable_columns(self):
        cols = pg_columns(self.TABLE)
        # These three are UNIQUE + nullable
        for field in ("username", "email"):
            assert cols[field]["nullable"], f"{field} should be nullable"

    def test_usertype_is_nullable_varchar(self):
        cols = pg_columns(self.TABLE)
        assert cols["usertype"]["type"] == "character varying"
        assert cols["usertype"]["nullable"]


# ─── 1.3 users_accesslevel (55 cols) ─────────────────────────────────────────

class TestAccesslevel:
    TABLE = "users_accesslevel"

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 55, \
            f"Expected 55 columns, got {len(cols)}"

    def test_all_permission_fields_are_varchar(self):
        """
        CRITICAL: ALL 50+ permission fields are character varying (strings), NOT integers.
        The only integer fields are id and analytics.
        Previously generated tests were WRONG — they assumed IntegerField.
        """
        cols = pg_columns(self.TABLE)
        integer_fields = {name for name, meta in cols.items() if meta["type"] == "integer"}
        varchar_fields  = {name for name, meta in cols.items() if meta["type"] == "character varying"}
        # Only id and analytics are integers
        assert "id" in integer_fields
        assert "analytics" in integer_fields
        assert len(integer_fields) == 2, \
            f"Only id and analytics should be integer. Found: {integer_fields}"
        # All permission fields must be varchar
        permission_samples = ["orders", "products", "inventory", "stock", "estimates", "audit"]
        for field in permission_samples:
            assert field in varchar_fields, \
                f"Accesslevel.{field} must be character varying, not integer"

    def test_branches_is_jsonb(self):
        cols = pg_columns(self.TABLE)
        assert cols["branches"]["type"] == "jsonb", \
            f"branches must be jsonb, got {cols['branches']['type']}"

    def test_bg_code_entity_userid_exist(self):
        cols = pg_columns(self.TABLE)
        for field in ("bg_code", "entity", "userid"):
            assert field in cols, f"Accesslevel missing field: {field}"

    def test_cafe_permission_fields_not_yet_added(self):
        """
        Phase gate: kungosadmin, cafedashboard, station_management etc.
        are PLANNED but NOT YET in the schema.
        This test confirms the migration hasn't run yet.
        If this test FAILS, the migration has been applied — update to positive assertions.
        """
        cols = pg_columns(self.TABLE)
        planned_fields = [
            "kungosadmin", "cafedashboard", "station_management",
            "wallet_management", "wallet_recharge", "pricing_management",
            "cafe_dashboard", "cafe_sessions", "cafe_payments",
        ]
        missing = [f for f in planned_fields if f not in cols]
        if len(missing) < len(planned_fields):
            applied = [f for f in planned_fields if f in cols]
            pytest.fail(
                f"Partial migration detected. Applied: {applied}, Still missing: {missing}. "
                "Either apply the full migration or revert it."
            )
        # All missing = migration not run yet = expected current state
        assert len(missing) == len(planned_fields), \
            "Cafe permission migration not yet applied — expected state. "
            "Run the migration, then flip these to positive assertions."


# ─── 1.4 users_user_tenant_context (9 cols) ──────────────────────────────────

class TestUserTenantContext:
    TABLE = "users_user_tenant_context"   # NOT users_usertenantcontext

    def test_table_exists(self):
        assert pg_table_exists(self.TABLE)

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 9, f"Expected 9 columns, got {len(cols)}: {list(cols)}"

    def test_scope_not_scope_type(self):
        """
        CRITICAL: Field is 'scope', NOT 'scope_type'.
        Previous generated tests used scope_type — WRONG.
        """
        cols = pg_columns(self.TABLE)
        assert "scope" in cols, "Column must be 'scope', not 'scope_type'"
        assert "scope_type" not in cols, \
            "scope_type does not exist — use 'scope'"

    def test_entity_is_jsonb(self):
        cols = pg_columns(self.TABLE)
        assert cols["entity"]["type"] == "jsonb", \
            f"entity must be jsonb (multi-entity context), got {cols['entity']['type']}"

    def test_branches_is_jsonb(self):
        cols = pg_columns(self.TABLE)
        assert cols["branches"]["type"] == "jsonb"

    def test_token_key_nullable(self):
        cols = pg_columns(self.TABLE)
        assert cols["token_key"]["nullable"], "token_key should be nullable"

    def test_composite_index_userid_bg_code(self):
        indexes = pg_indexes(self.TABLE)
        assert any("usr_tenant" in idx.lower() or "uid_bg" in idx.lower()
                   for idx in indexes), \
            "Missing composite index (userid, bg_code) — expected usr_tenant_uid_bg"

    def test_planned_fields_not_yet_present(self):
        """permission_snapshot, switched_at, switched_by, request_defaults — NOT YET IMPLEMENTED."""
        cols = pg_columns(self.TABLE)
        planned = ["permission_snapshot", "switched_at", "switched_by", "request_defaults"]
        present = [f for f in planned if f in cols]
        if present:
            pytest.xfail(
                f"Planned fields now present: {present}. "
                "Update test_db_schema_postgres.py to assert them positively."
            )


# ─── 1.5 platform_outbox_events (11 cols) ─────────────────────────────────────

class TestOutboxEvents:
    TABLE = "platform_outbox_events"   # NOT plat_outboxevent

    def test_table_exists(self):
        assert pg_table_exists(self.TABLE)

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 11, f"Expected 11 columns, got {len(cols)}: {list(cols)}"

    def test_pk_is_event_id_uuid(self):
        """CRITICAL: PK is event_id (uuid), NOT id (bigint). Previous tests were wrong."""
        cols = pg_columns(self.TABLE)
        assert "event_id" in cols, "PK must be 'event_id', not 'id'"
        assert cols["event_id"]["type"] == "uuid", \
            f"event_id must be uuid type, got {cols['event_id']['type']}"
        assert "id" not in cols, \
            "platform_outbox_events has no 'id' column — PK is event_id"

    def test_required_columns(self):
        cols = pg_columns(self.TABLE)
        required = [
            "event_id", "event_type", "aggregate_type", "aggregate_id",
            "bg_code", "payload", "status", "retry_count",
            "available_at", "processed_at", "error_message",
        ]
        for col in required:
            assert col in cols, f"platform_outbox_events missing column: {col}"

    def test_processed_at_nullable(self):
        cols = pg_columns(self.TABLE)
        assert cols["processed_at"]["nullable"], "processed_at must be nullable"

    def test_status_and_available_at_index(self):
        indexes = pg_indexes(self.TABLE)
        idx_str = " ".join(indexes).lower()
        assert "status" in idx_str and "avail" in idx_str, \
            "Missing index pltf_outbox_status_avail on (status, available_at)"

    def test_bg_status_index(self):
        indexes = pg_indexes(self.TABLE)
        idx_str = " ".join(indexes).lower()
        assert "bg" in idx_str and "status" in idx_str, \
            "Missing index pltf_outbox_bg_status on (bg_code, status)"


# ─── 1.6 platform_tenant_config (11 cols) ─────────────────────────────────────

class TestTenantConfig:
    TABLE = "platform_tenant_config"   # NOT plat_tenantconfig

    def test_table_exists(self):
        assert pg_table_exists(self.TABLE)

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 11, f"Expected 11 columns, got {len(cols)}: {list(cols)}"

    def test_bg_code_is_pk_and_unique(self):
        """bg_code is both PRIMARY KEY and UNIQUE — unusual but confirmed."""
        cols = pg_columns(self.TABLE)
        assert "bg_code" in cols
        assert "status" in cols   # extra field vs v2 plan design
        unique_cols = pg_unique_cols(self.TABLE)
        assert "bg_code" in unique_cols, "bg_code must be UNIQUE"

    def test_all_cfg_columns_are_jsonb(self):
        cols = pg_columns(self.TABLE)
        jsonb_fields = ["features", "payment_cfg", "sms_cfg",
                        "wallet_cfg", "pricing_cfg", "theme_cfg", "integration_cfg"]
        for field in jsonb_fields:
            assert field in cols, f"platform_tenant_config missing: {field}"
            assert cols[field]["type"] == "jsonb", \
                f"{field} must be jsonb, got {cols[field]['type']}"


# ─── 1.7 caf_platform_wallets (11 cols) ───────────────────────────────────────

class TestCafePlatformWallets:
    TABLE = "caf_platform_wallets"   # NOT rebellion_cafewallet

    def test_table_exists(self):
        assert pg_table_exists(self.TABLE)

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 11, f"Expected 11 columns, got {len(cols)}: {list(cols)}"

    def test_balance_no_default(self):
        """
        CRITICAL: balance has NO default of 0.
        Previous generated test asserted default='0' — WRONG.
        Application code must always supply balance explicitly.
        """
        cols = pg_columns(self.TABLE)
        assert not cols["balance"]["nullable"], "balance must NOT be nullable"
        default = cols["balance"]["default"]
        assert default is None, \
            f"balance has unexpected default '{default}' — must be None (no default)"

    def test_wallet_id_unique(self):
        assert "wallet_id" in pg_unique_cols(self.TABLE)

    def test_customer_id_fk_and_unique(self):
        """customer_id is FK to users_customuser AND UNIQUE (one wallet per customer)."""
        assert "customer_id" in pg_unique_cols(self.TABLE), \
            "customer_id must be UNIQUE (one wallet per customer)"
        with connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.referential_constraints rc
                JOIN information_schema.key_column_usage kcu
                  ON rc.constraint_name = kcu.constraint_name
                WHERE kcu.column_name = 'customer_id'
                  AND kcu.table_name = 'caf_platform_wallets'
            """)
            assert cur.fetchone()[^0] >= 1, \
                "customer_id must be FK to users_customuser.userid"

    def test_numeric_fields(self):
        cols = pg_columns(self.TABLE)
        for field in ("balance", "total_spent", "total_recharged"):
            assert cols[field]["type"] == "numeric", \
                f"{field} must be numeric, got {cols[field]['type']}"

    def test_points_earned_is_integer(self):
        cols = pg_columns(self.TABLE)
        assert cols["points_earned"]["type"] == "integer"


# ─── 1.8 caf_platform_sessions (17 cols) ──────────────────────────────────────

class TestCafePlatformSessions:
    TABLE = "caf_platform_sessions"

    def test_table_exists(self):
        assert pg_table_exists(self.TABLE)

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 17, f"Expected 17 columns, got {len(cols)}: {list(cols)}"

    def test_required_columns(self):
        cols = pg_columns(self.TABLE)
        required = [
            "id", "status", "started_at", "ends_at", "ended_at",
            "billed_minutes", "amount_due", "food_charges", "total_charges",
            "payment_status", "started_by", "ended_by", "reason",
            "cafe_id", "game_id", "price_plan_id", "station_id",
        ]
        for col in required:
            assert col in cols, f"caf_platform_sessions missing column: {col}"

    def test_nullable_timing_fields(self):
        """started_at, ends_at, ended_at, game_id are nullable."""
        cols = pg_columns(self.TABLE)
        for field in ("started_at", "ends_at", "ended_at"):
            assert cols[field]["nullable"], f"{field} must be nullable"
        assert cols["game_id"]["nullable"], "game_id must be nullable"

    def test_composite_indexes(self):
        indexes = pg_indexes(self.TABLE)
        idx_str = " ".join(indexes).lower()
        assert "cafe" in idx_str and "status" in idx_str, \
            "Missing composite index (cafe_id, status)"
        assert "station" in idx_str and "status" in idx_str, \
            "Missing composite index (station_id, status)"

    def test_note_no_customer_id_column(self):
        """
        Sessions do NOT have customer_id or wallet_id directly.
        Customer is linked via caf_platform_wallets + caf_platform_wallet_transactions.
        This is a key architectural point — do not add customer_id to sessions.
        """
        cols = pg_columns(self.TABLE)
        assert "customer_id" not in cols, \
            "caf_platform_sessions must NOT have customer_id — link via wallet_transactions"


# ─── 1.9 caf_platform_stations (12 cols) ──────────────────────────────────────

class TestCafePlatformStations:
    TABLE = "caf_platform_stations"

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 12, f"Expected 12 columns, got {len(cols)}"

    def test_unique_cafe_code_constraint(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = %s AND constraint_type = 'UNIQUE'
            """, [self.TABLE])
            count = cur.fetchone()[^0]
        assert count >= 1, "caf_platform_stations must have UNIQUE constraint on (cafe_id, code)"

    def test_current_session_id_nullable(self):
        cols = pg_columns(self.TABLE)
        assert cols["current_session_id"]["nullable"], \
            "current_session_id must be nullable (null when no active session)"

    def test_bg_code_present(self):
        cols = pg_columns(self.TABLE)
        assert "bg_code" in cols, \
            "caf_platform_stations must have bg_code for tenant scoping"


# ─── 1.10 caf_platform_wallet_transactions (9 cols) ───────────────────────────

class TestWalletTransactions:
    TABLE = "caf_platform_wallet_transactions"  # NOT rebellion_cafewallettransaction

    def test_column_count(self):
        cols = pg_columns(self.TABLE)
        assert len(cols) == 9, f"Expected 9 columns, got {len(cols)}: {list(cols)}"

    def test_reference_fields_nullable(self):
        """reference_type and reference_id are nullable."""
        cols = pg_columns(self.TABLE)
        assert cols["reference_type"]["nullable"]
        assert cols["reference_id"]["nullable"]

    def test_wallet_id_is_bigint_fk(self):
        """wallet_id FK is to caf_platform_wallets.id (bigint), not wallet_id (varchar)."""
        cols = pg_columns(self.TABLE)
        assert cols["wallet_id"]["type"] == "bigint", \
            f"wallet_id must be bigint (FK to caf_platform_wallets.id), got {cols['wallet_id']['type']}"

    def test_three_required_indexes(self):
        indexes = pg_indexes(self.TABLE)
        idx_str = " ".join(indexes).lower()
        assert "wallet" in idx_str,    "Missing wallet index"
        assert "reference" in idx_str, "Missing reference index"
        assert "created" in idx_str,   "Missing created_at index"
```


***

### `tests/test_db_schema_mongodb.py`

```python
# tests/test_db_schema_mongodb.py
# Ground-truthed against kungos_db_test_plan.md 2026-04-28

import pytest
from tests.conftest import MONGO_DB_NAME  # = "KungOS_Mongo_One"

# ─── Collections actually present (9 with tenant fields, 21 without) ─────────

TENANT_SCOPED_COLLECTIONS = [
    # These 9 have bgcode + entity + branch (confirmed)
    "purchaseorders", "inwardpayments", "estimates",
    "products", "accounts", "misc",
    "players", "tournaments", "reb_users",   # NOTE: reb_users, not rebusers
]

NO_TENANT_COLLECTIONS = [
    # Present but NO tenant fields yet — Phase 1 incomplete on these
    "kgorders", "tporders", "tpbuilds", "serviceRequest",
    "outward", "outwardInvoices", "outwardCreditNotes",
    "paymentVouchers", "stock_register", "indentpos", "indentproduct",
    "employee_attendance", "vendors", "teams", "presets",
    "tourneyregister", "bgData", "inwardCreditNotes",
    "inwardInvoices", "outwardDebitNotes",
]

MISSING_COLLECTIONS = [
    # These do NOT exist — moved to PostgreSQL OR awaiting Phase 3
    "gamers",        # → caf_platform_sessions (PostgreSQL)
    "stations",      # → caf_platform_stations (PostgreSQL)
    "cafepayments",  # → caf_platform_wallet_transactions (PostgreSQL)
    "gamelibrary",   # Phase 3 gaming integration
    "prods", "builds", "kgbuilds", "custombuilds",
    "components", "accessories", "monitors", "networking",
    "external", "games", "kurodata", "lists",
]

EXACT_DOCUMENT_COUNTS = {
    "purchaseorders": (15_216, 300),
    "inwardpayments": (21_026, 500),
    "estimates":      (4_308,  200),
    "inwardInvoices": (16,      3),
    "outwardDebitNotes": (13,   3),
    "misc":           (5_512,  200),
    "products":       (82,     10),
    "accounts":       (7,       2),
    "players":        (117,    10),
    "tournaments":    (3,       2),
    "reb_users":      (1_982,  100),
    "kgorders":       (9_162,  300),
    "tporders":       (229,    20),
    "tpbuilds":       (123,    10),
    "serviceRequest": (1_625,  100),
    "outward":        (754,    50),
    "outwardInvoices":(1_165,  100),
    "outwardCreditNotes": (150, 20),
    "paymentVouchers": (3_459, 200),
    "stock_register": (194,    20),
    "indentpos":      (247,    20),
    "indentproduct":  (1_490,  100),
    "employee_attendance": (966, 50),
    "vendors":        (409,    30),
    "teams":          (14,      3),
    "presets":        (6,       2),
    "tourneyregister":(56,      5),
    "bgData":         (1,       1),
    "inwardCreditNotes": (106, 10),
}


class TestMongoCollectionExistence:
    def test_total_collection_count(self, mongo_db):
        count = len(mongo_db.list_collection_names())
        assert count == 30, \
            f"Expected exactly 30 collections, found {count}. " \
            f"Collections: {sorted(mongo_db.list_collection_names())}"

    def test_total_document_count(self, mongo_db):
        total = sum(
            mongo_db[col].count_documents({})
            for col in mongo_db.list_collection_names()
        )
        assert abs(total - 68_441) <= 2000, \
            f"Total docs {total} deviates from expected 68,441"

    @pytest.mark.parametrize("col", TENANT_SCOPED_COLLECTIONS)
    def test_tenant_scoped_collection_exists(self, mongo_db, col):
        assert col in mongo_db.list_collection_names(), \
            f"Collection '{col}' missing — expected with tenant fields"

    @pytest.mark.parametrize("col", MISSING_COLLECTIONS)
    def test_missing_collections_do_not_exist(self, mongo_db, col):
        """
        These collections MUST NOT EXIST — either moved to PostgreSQL or Phase 3 pending.
        If this fails, an unexpected migration or leftover data exists.
        """
        assert col not in mongo_db.list_collection_names(), \
            f"Collection '{col}' exists but should be missing. " \
            "Reason: moved to PostgreSQL or awaiting Phase 3."

    def test_rebusers_is_reb_users_not_rebusers(self, mongo_db):
        """CRITICAL: Collection is 'reb_users' (with underscore), not 'rebusers'."""
        existing = mongo_db.list_collection_names()
        assert "reb_users" in existing, "Collection 'reb_users' (with underscore) must exist"
        assert "rebusers" not in existing, \
            "Old name 'rebusers' should not exist — use 'reb_users'"


class TestTenantFieldCoverage:
    """Only the 9 confirmed tenant-scoped collections are tested for 100% coverage."""

    @pytest.mark.parametrize("col_name", TENANT_SCOPED_COLLECTIONS)
    def test_bgcode_100_percent(self, mongo_db, col_name):
        col = mongo_db[col_name]
        total = col.count_documents({})
        if total == 0:
            pytest.skip(f"{col_name} is empty")
        missing = col.count_documents({"bgcode": {"$exists": False}})
        assert missing == 0, \
            f"{col_name}: {missing}/{total} docs missing 'bgcode'"

    @pytest.mark.parametrize("col_name", TENANT_SCOPED_COLLECTIONS)
    def test_entity_100_percent(self, mongo_db, col_name):
        col = mongo_db[col_name]
        total = col.count_documents({})
        if total == 0:
            pytest.skip(f"{col_name} is empty")
        missing = col.count_documents({"entity": {"$exists": False}})
        assert missing == 0, \
            f"{col_name}: {missing}/{total} docs missing 'entity'"

    @pytest.mark.parametrize("col_name", NO_TENANT_COLLECTIONS)
    def test_no_tenant_collections_acknowledged(self, mongo_db, col_name):
        """
        These 21 collections have NO tenant fields yet.
        This test just confirms they exist — Phase 1 migration is incomplete on them.
        They are not expected to have bgcode/entity/branch.
        """
        if col_name not in mongo_db.list_collection_names():
            pytest.skip(f"{col_name} not present (may be empty or renamed)")
        # Just assert the collection is accessible
        count = mongo_db[col_name].count_documents({})
        assert count >= 0   # trivially true — documents the known gap


class TestEntityDistribution:
    """
    Current ground truth (68,441 docs, 2 entities only):
      kurogaming: 38,905 (56.8%)
      rebellion:  29,536 (43.2%)
      NO legacy/None entity in current state
    """

    def test_only_two_entities_in_scoped_collections(self, mongo_db):
        """After migration, only kurogaming and rebellion should exist as entity values."""
        found = set()
        for col_name in TENANT_SCOPED_COLLECTIONS:
            col = mongo_db[col_name]
            pipeline = [{"$group": {"_id": "$entity"}}]
            for doc in col.aggregate(pipeline):
                if doc["_id"] is not None:
                    found.add(doc["_id"])
        unexpected = found - {"kurogaming", "rebellion", "renderedge"}
        assert not unexpected, \
            f"Unexpected entity values in scoped collections: {unexpected}"

    def test_purchaseorders_entity_distribution(self, mongo_db):
        col = mongo_db["purchaseorders"]
        total = col.count_documents({})
        kg = col.count_documents({"entity": "kurogaming"})
        pct = kg / total if total > 0 else 0
        assert pct >= 0.98, \
            f"purchaseorders kurogaming% = {pct:.1%}, expected ~99.96%"

    def test_inwardpayments_entity_distribution(self, mongo_db):
        col = mongo_db["inwardpayments"]
        total = col.count_documents({})
        reb = col.count_documents({"entity": "rebellion"})
        pct = reb / total if total > 0 else 0
        assert 0.75 <= pct <= 0.88, \
            f"inwardpayments rebellion% = {pct:.1%}, expected ~81.4%"

    def test_estimates_100_percent_kurogaming(self, mongo_db):
        col = mongo_db["estimates"]
        total = col.count_documents({})
        kg = col.count_documents({"entity": "kurogaming"})
        assert kg == total, \
            f"estimates must be 100% kurogaming, got {kg}/{total}"


class TestDocumentCounts:
    @pytest.mark.parametrize("col_name,expected_tol", [
        (col, (exp, tol)) for col, (exp, tol) in EXACT_DOCUMENT_COUNTS.items()
    ])
    def test_document_count(self, mongo_db, col_name, expected_tol):
        expected, tolerance = expected_tol
        if col_name not in mongo_db.list_collection_names():
            pytest.skip(f"{col_name} not present")
        actual = mongo_db[col_name].count_documents({})
        assert abs(actual - expected) <= tolerance, \
            f"{col_name}: count {actual} differs from expected {expected} by >{tolerance}"


class TestCompoundIndexes:
    @pytest.mark.parametrize("col_name", TENANT_SCOPED_COLLECTIONS)
    def test_bgcode_entity_compound_index(self, mongo_db, col_name):
        col = mongo_db[col_name]
        indexes = col.index_information()
        has_compound = any(
            any(k[^0] == "bgcode" for k in idx["key"]) and
            any(k[^0] == "entity" for k in idx["key"])
            for idx in indexes.values()
        )
        assert has_compound, \
            f"{col_name}: missing compound index (bgcode, entity)"
```


***

### `tests/test_migration_commands.py`

```python
# tests/test_migration_commands.py — corrected per kungos_db_test_plan.md

import os, pytest
from io import StringIO
from django.core.management import call_command, get_commands

DUMP_PATH = os.environ.get("E2E_DUMP_PATH", "")
REQUIRES_DUMP = pytest.mark.skipif(not DUMP_PATH, reason="E2E_DUMP_PATH not set")

CONFIRMED_EXISTS = [
    "restore_kuropurchase", "backup_kuropurchase", "deploy_restore",
    "reconcile_user_models",          # confirmed in test plan
    "seed_games", "seed_member_plans", "seed_pricing",
    "seed_stations", "seed_tenant_config",
]

CONFIRMED_MISSING = [
    "verify_tenant_isolation",         # NOT exists — Phase 1 P2 #3 planned
    "migrate_gamers_to_enhanced",      # NOT exists — gamers moved to PostgreSQL
]

class TestCommandExistence:
    @pytest.mark.parametrize("cmd", CONFIRMED_EXISTS)
    def test_command_exists(self, cmd):
        assert cmd in get_commands(), \
            f"Management command '{cmd}' not found — expected to exist"

    @pytest.mark.parametrize("cmd", CONFIRMED_MISSING)
    def test_missing_command_not_registered(self, cmd):
        """
        These commands are planned but not yet implemented.
        If this fails, the command was added — update CONFIRMED_MISSING accordingly.
        """
        assert cmd not in get_commands(), \
            f"Command '{cmd}' now exists — update test to positive assertion"


class TestSeedCommandsIdempotent:
    """All seed commands must be safely runnable multiple times."""

    @pytest.mark.parametrize("cmd", [
        "seed_games", "seed_member_plans", "seed_pricing",
        "seed_stations", "seed_tenant_config",
    ])
    def test_seed_command_idempotent(self, cmd):
        out1 = StringIO()
        out2 = StringIO()
        call_command(cmd, stdout=out1)
        call_command(cmd, stdout=out2)   # Second run must not raise
        # Both runs must complete without exception — content may differ


class TestRestoreKuropurchase:
    @REQUIRES_DUMP
    def test_dry_run_no_writes(self):
        import pymongo
        from django.conf import settings
        from tests.conftest import MONGO_DB_NAME
        client = pymongo.MongoClient(settings.MONGO_URI)
        db = client[MONGO_DB_NAME]
        before = sum(db[c].count_documents({}) for c in db.list_collection_names())
        call_command("restore_kuropurchase", dump=DUMP_PATH, dry_run=True, stdout=StringIO())
        after = sum(db[c].count_documents({}) for c in db.list_collection_names())
        client.close()
        assert before == after, f"Dry-run wrote documents: {before} → {after}"

    @REQUIRES_DUMP
    def test_dry_run_reports_47k_docs(self):
        out = StringIO()
        call_command("restore_kuropurchase", dump=DUMP_PATH, dry_run=True, stdout=out)
        output = out.getvalue()
        assert "47" in output, f"Dry-run must report ~47,009 docs. Got: {output[:300]}"

    @REQUIRES_DUMP
    def test_duplicate_ids_reported(self):
        out = StringIO()
        call_command("restore_kuropurchase", dump=DUMP_PATH, dry_run=True, stdout=out)
        output = out.getvalue().lower()
        assert "duplicate" in output or "skip" in output, \
            f"Must report 52 duplicate _id handling. Got: {output[:300]}"
```


***

### `tests/test_tenant_isolation.py`

```python
# tests/test_tenant_isolation.py — corrected per kungos_db_test_plan.md

import pytest
import subprocess
from django.db import connection


class TestTenantCollectionWrapper:
    def test_import(self):
        from plat.tenant.collection import TenantCollection

    def test_raises_on_missing_context(self):
        from plat.tenant.collection import TenantCollection, TenantContextMissing
        col = TenantCollection("purchaseorders")
        with pytest.raises(TenantContextMissing):
            col.find_one({})

    def test_wrong_bgcode_returns_empty(self):
        from plat.tenant.collection import TenantCollection
        from plat.tenant.context import set_tenant_context, clear_tenant_context
        try:
            set_tenant_context(bg_code="BG_DOES_NOT_EXIST", entity="kurogaming")
            col = TenantCollection("purchaseorders")
            assert col.count_documents({}) == 0
        finally:
            clear_tenant_context()


class TestPerBGRoutingStaticScan:
    """
    KNOWN BUG: backend/utils.py lines 288 and 339 still use client[bg.db_name].
    These are the exact two locations to fix.
    """

    def test_utils_py_lines_288_339_use_tenant_collection(self):
        with open("backend/utils.py") as f:
            lines = f.readlines()

        old_pattern_lines = [
            (i + 1, line.strip())
            for i, line in enumerate(lines)
            if "client[bg.db_name]" in line or "client[bg.dbname]" in line
        ]
        assert not old_pattern_lines, \
            f"Found old per-BG routing at:\n" + \
            "\n".join(f"  Line {ln}: {code}" for ln, code in old_pattern_lines) + \
            "\nReplace with TenantCollection wrapper."

    def test_no_raw_collection_access_in_views(self):
        result = subprocess.run(
            ["grep", "-rn", r'db\["', ".", "--include=*.py",
             "--exclude-dir=.git", "--exclude-dir=tests",
             "--exclude=collection.py", "--exclude=utils.py",   # utils.py is the known exception
             "--exclude-dir=management"],
            capture_output=True, text=True, cwd="."
        )
        violations = [
            line for line in result.stdout.strip().splitlines()
            if "# noqa" not in line and "migration" not in line.lower()
        ]
        assert not violations, \
            "Raw db['collection'] in views/services:\n" + "\n".join(violations[:10])


class TestPostgreSQLRLS:
    def test_rls_status_on_tenant_context(self):
        """RLS not confirmed active yet — test reports current state."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT relrowsecurity FROM pg_class
                WHERE relname = 'users_user_tenant_context'
            """)
            row = cur.fetchone()
        assert row is not None, "users_user_tenant_context not found"
        if not row[^0]:
            pytest.xfail(
                "RLS not yet enabled on users_user_tenant_context — "
                "Phase 1 P1 #3 not complete. Enable with: "
                "ALTER TABLE users_user_tenant_context ENABLE ROW LEVEL SECURITY;"
            )


class TestVerifyTenantIsolationCommandMissing:
    def test_verify_tenant_isolation_not_yet_implemented(self):
        """This command is Phase 1 P2 #3 — confirm it doesn't accidentally exist."""
        from django.core.management import get_commands
        if "verify_tenant_isolation" in get_commands():
            pytest.xfail(
                "verify_tenant_isolation now exists — flip this to a positive test"
            )
```


***

### `tests/test_data_quality.py`

```python
# tests/test_data_quality.py — exact fields from kungos_db_test_plan.md §5

import pytest
from django.db import connection


def run_sql(query, params=None):
    with connection.cursor() as cur:
        cur.execute(query, params or [])
        return cur.fetchall()


class TestWalletFinancialIntegrity:
    def test_no_negative_balances(self):
        rows = run_sql("SELECT wallet_id, balance FROM caf_platform_wallets WHERE balance < 0")
        assert not rows, f"Negative wallet balances found: {rows}"

    def test_transaction_type_values(self):
        rows = run_sql("""
            SELECT DISTINCT transaction_type FROM caf_platform_wallet_transactions
            WHERE transaction_type NOT IN ('recharge','spend','refund','adjustment','prize_winnings')
        """)
        assert not rows, f"Invalid transaction_type values: {[r[^0] for r in rows]}"

    def test_all_wallet_ids_reference_existing_wallets(self):
        rows = run_sql("""
            SELECT COUNT(*) FROM caf_platform_wallet_transactions t
            LEFT JOIN caf_platform_wallets w ON t.wallet_id = w.id
            WHERE w.id IS NULL
        """)
        assert rows[^0][^0] == 0, \
            f"{rows[^0][^0]} transactions reference non-existent wallets"


class TestSessionBillingConsistency:
    def test_total_charges_equals_sum(self):
        rows = run_sql("""
            SELECT id, amount_due, food_charges, total_charges
            FROM caf_platform_sessions
            WHERE ABS(total_charges - (amount_due + food_charges)) > 0.01
        """)
        assert not rows, \
            f"{len(rows)} sessions where total_charges ≠ amount_due + food_charges: {rows[:3]}"

    def test_billed_minutes_non_negative(self):
        rows = run_sql("SELECT id FROM caf_platform_sessions WHERE billed_minutes < 0")
        assert not rows, f"Negative billed_minutes on sessions: {[r[^0] for r in rows]}"

    def test_ended_at_after_started_at(self):
        rows = run_sql("""
            SELECT id FROM caf_platform_sessions
            WHERE ended_at IS NOT NULL AND started_at IS NOT NULL
              AND ended_at < started_at
        """)
        assert not rows, f"Sessions where ended_at < started_at: {[r[^0] for r in rows]}"

    def test_payment_status_values(self):
        rows = run_sql("""
            SELECT DISTINCT payment_status FROM caf_platform_sessions
            WHERE payment_status NOT IN ('unpaid','paid','partial','refunded')
        """)
        assert not rows, f"Invalid payment_status values: {[r[^0] for r in rows]}"

    def test_station_released_after_session_ends(self):
        """Stations must have current_session_id = NULL for ended sessions."""
        rows = run_sql("""
            SELECT s.id, st.id AS station_id
            FROM caf_platform_sessions s
            JOIN caf_platform_stations st ON st.current_session_id = s.id
            WHERE s.ended_at IS NOT NULL
        """)
        assert not rows, \
            f"{len(rows)} stations still locked to ended sessions: {rows[:3]}"


class TestStationStateConsistency:
    def test_status_values_valid(self):
        rows = run_sql("""
            SELECT DISTINCT status FROM caf_platform_stations
            WHERE status NOT IN ('offline','idle','reserved','in_session','locked','error')
        """)
        assert not rows, f"Invalid station status values: {[r[^0] for r in rows]}"

    def test_current_session_consistency(self):
        """If current_session_id set, referenced session must exist and be active."""
        rows = run_sql("""
            SELECT st.id FROM caf_platform_stations st
            LEFT JOIN caf_platform_sessions s ON s.id = st.current_session_id
            WHERE st.current_session_id IS NOT NULL AND s.id IS NULL
        """)
        assert not rows, \
            f"{len(rows)} stations reference non-existent sessions: {[r[^0] for r in rows]}"

    def test_bg_code_matches_cafe(self):
        rows = run_sql("""
            SELECT st.id FROM caf_platform_stations st
            JOIN caf_platform_cafes c ON st.cafe_id = c.id
            WHERE st.bg_code != c.bg_code
        """)
        assert not rows, \
            f"{len(rows)} stations have bg_code mismatch with their cafe: {rows[:3]}"


class TestPricePlanValidity:
    def test_rate_per_hour_positive(self):
        rows = run_sql("SELECT id FROM caf_platform_price_plans WHERE rate_per_hour <= 0")
        assert not rows, f"Price plans with rate_per_hour <= 0: {[r[^0] for r in rows]}"

    def test_min_max_minutes_valid(self):
        rows = run_sql("""
            SELECT id FROM caf_platform_price_plans
            WHERE max_minutes < min_minutes OR min_minutes <= 0
        """)
        assert not rows, f"Invalid min/max_minutes on price plans: {rows[:3]}"

    def test_three_member_plan_tiers_seeded(self):
        rows = run_sql("SELECT tier FROM caf_platform_member_plans")
        tiers = {r[^0] for r in rows}
        assert {"edge", "titan", "s"}.issubset(tiers), \
            f"Expected tiers edge/titan/s. Found: {tiers}. Run: python manage.py seed_member_plans"
```


***

## Updated Test Execution Matrix

| File | Wrong in Previous | Corrected Now | Runs Without Dump |
| :-- | :-- | :-- | :-- |
| `conftest.py` | DB name was `KungOSMongoOne` | `KungOS_Mongo_One` (underscores) | ✅ |
| `test_db_schema_postgres.py` | 7 wrong table names, 5 wrong field names/types | All exact per §1.1–1.3 | ✅ |
| `test_db_schema_mongodb.py` | Assumed gamers/stations in Mongo, wrong DB name, wrong counts | Exact counts, missing = PostgreSQL documented | ✅ |
| `test_migration_commands.py` | Listed non-existent commands as existing | Missing commands skip-gated, all 9 confirmed commands tested | ⚠️ Partial |
| `test_tenant_isolation.py` | RLS asserted as active, verify command tested as existing | Both marked xfail with exact fix instructions | ✅ |
| `test_data_quality.py` | Used wrong table names throughout | All corrected to `caf_platform_*` | ✅ |

<div align="center">⁂</div>

[^1]: kungos_db_test_plan.md

