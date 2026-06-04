# Task Handoff: Odysseus → Council Core Schema Unification

**Source spec:** `13-council-core-architecture-analysis.md`, `13-council-core-unified-db-draft.md`, `12-odysseus-integration-map.md`
**Generated:** 04-06-2026
**Goal:** Merge Odysseus app.db columns into Council Core schema — include governance columns, media/gallery, extensibility, AI classification, token budgeting, and UI chrome. Produce unified migration SQL + updated CouncilCoreStore.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Reference docs:**
- `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
- `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md`
- `/home/chief/llm-wiki/super-council-docs/12-odysseus-integration-map.md`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/` (source of truth for Odysseus column definitions)
**Key files for this task:**
- `/home/chief/Coding-Projects/7-council/migrations_council_core/01_core_tables.sql` — modify
- `/home/chief/Coding-Projects/7-council/migrations_council_core/02_fts5_indexes.sql` — modify
- `/home/chief/Coding-Projects/7-council/super_council/memory_service/council_core_store.py` — modify
- `~/.council-memory/council_core.db` — target database (apply migrations)

---

## Background & Corrections

**Key correction from previous analysis:** Odysseus is a **single-user system**, not multi-user. This changes the inclusion criteria:

| Previously Recommended | Correction | New Recommendation |
|---|---|---|
| EXCLUDE: Media/gallery | User uploads images/documents for AI analysis | **INCLUDE** |
| EXCLUDE: Extensibility (webhooks, integrations, mcp_servers, user_tools) | Used for upload→analyze pipeline | **INCLUDE** |
| EXCLUDE: UI chrome (color, label, sort_order, image_url, repeat) | Single-user workspace needs visual organization | **INCLUDE** |
| EXCLUDE: AI classification | Already built, useful for auto-categorization | **INCLUDE** (unified) |
| EXCLUDE: Token budgeting | Already built, useful for cost tracking | **INCLUDE** (unified) |
| DEFER: Email traceability | Not needed now | **DEFER** (unchanged) |
| DEFER: Calendar | Not wired yet | **DEFER** (unchanged) |

---

## Execution Order (DAG)

```
Phase 0 (Poison Prevention Layer) ──> Phase 1 (Schema Design) ──┐
                                                                    ├──> Phase 2 (Migration SQL) ──> Phase 3 (CouncilCoreStore) ──> Phase 4 (Apply + Verify)
Phase 1B (Column Audit) ───────────────────────────────────────────┘
```

- **Phase 0:** MUST complete first. All subsequent phases depend on poison prevention being in place.
- **Phase 1 + 1B:** Can run in parallel (design + audit)
- **Phase 2:** Depends on Phase 1 completion

---

## Phase 0: Poison Prevention Layer — RelationalStore Principle Compliance

**What:** Implement the RelationalStore hard guards that prevent poisonous DB writes. Currently **3/14 principles implemented** (WAL, FK, checkpoint). This phase adds the remaining 11.

**Why:** CouncilCoreStore currently has zero runtime guards against poison writes. An agent hallucination can write garbage directly to the DB with no audit trail, no validation, no rollback. RelationalStore (pipelines.db) has 14 guards — CouncilCoreStore needs the same.

**Gap Analysis (current state):**

| Principle | RelationalStore | CouncilCoreStore | Risk |
|---|---|---|---|
| WAL mode | ✅ | ✅ | — |
| FK enforcement | ✅ | ✅ | — |
| Manual checkpoint | ✅ | ✅ | — |
| Schema from migrations/ | ✅ | ❌ Wrong path (`migrations_council_core/`) | **HIGH** |
| Atomic transitions (`BEGIN IMMEDIATE...COMMIT`) | ✅ | ❌ Autocommit per-INSERT | **HIGH** |
| ROLLBACK on error | ✅ | ❌ No transaction wrapper | **HIGH** |
| Audit trail (`audit_events`) | ✅ | ❌ No audit table | **HIGH** |
| Write boundary enforcement | ✅ Logged per-request | ❌ No boundary check | **HIGH** |
| OutputGate validation | ✅ Before storage | ❌ No gate | **HIGH** |
| Bypass tracking | ✅ bypass + user + justification | ❌ No logging | **HIGH** |
| MemoryLayer unified write path | ✅ Artifacts → MemoryLayer | ❌ Direct SQL | **HIGH** |
| Injection blacklist | ✅ `upsert_injection_blacklist()` | ❌ No detection | **HIGH** |
| Enum table seeding | ✅ `_seed_enum_tables()` | ❌ CHECK only | Medium |
| Phase registry sync | ✅ `_sync_phase_registry()` | ❌ No registry | Medium |

### Implementation Steps

#### 0A. Audit Events Table (Migration SQL)

Add to `migrations_council_core/01_core_tables.sql`:

```sql
-- Audit events table (mirrors RelationalStore.audit_events)
-- Every write through CouncilCoreStore logs an audit event.
-- write_boundary_enforced: was the write validated before storage?
-- gate_valid: did OutputGate validation pass?
-- bypass: was a guard bypassed? If so, bypass_user + bypass_justification required.
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    endpoint TEXT NOT NULL,           -- e.g., 'create_work_item', 'search_knowledge_cards'
    method TEXT NOT NULL,             -- 'INSERT', 'UPDATE', 'DELETE', 'SELECT'
    result_status INTEGER,            -- HTTP-style: 200=ok, 400=validation_fail, 500=error
    write_boundary_enforced BOOLEAN NOT NULL DEFAULT 1,
    gate_valid BOOLEAN NOT NULL DEFAULT 1,
    bypass BOOLEAN NOT NULL DEFAULT 0,
    bypass_user TEXT,
    bypass_justification TEXT,
    details TEXT,
    table_name TEXT,                  -- which table was written
    record_id TEXT,                   -- which record
    action TEXT,                      -- 'create', 'update', 'delete'
    actor TEXT,                       -- 'system', 'agent', 'user', 'migration'
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_events_endpoint ON audit_events(endpoint);
CREATE INDEX IF NOT EXISTS idx_audit_events_table ON audit_events(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_events_bypass ON audit_events(bypass) WHERE bypass = 1;
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at);
```

#### 0B. Injection Blacklist Table (Migration SQL)

```sql
-- Injection blacklist (mirrors RelationalStore.injection_blacklist)
-- Tracks repeated injection patterns. When failure_count >= threshold,
-- the pattern is blocked automatically (is_active=1).
CREATE TABLE IF NOT EXISTS injection_blacklist (
    blacklist_id TEXT PRIMARY KEY,
    pattern_type TEXT NOT NULL,       -- 'prompt_injection', 'sql_injection', 'schema_violation'
    pattern TEXT NOT NULL,            -- the detected pattern (hashed for privacy)
    failure_count INTEGER NOT NULL DEFAULT 1,
    threshold INTEGER NOT NULL DEFAULT 3,
    first_failure_at TEXT NOT NULL,
    last_failure_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_injection_blacklist_type ON injection_blacklist(pattern_type);
CREATE INDEX IF NOT EXISTS idx_injection_blacklist_active ON injection_blacklist(is_active) WHERE is_active = 1;
```

#### 0C. CouncilCoreStore — Transaction Wrapper

Replace direct `self.db.execute()` with transaction-aware writes:

```python
def _atomic_write(self, sql: str, params: tuple, table: str, action: str, endpoint: str) -> Dict[str, Any]:
    """Execute a write inside BEGIN IMMEDIATE...COMMIT with ROLLBACK on error.

    Logs audit event regardless of outcome.
    Returns dict with success status and audit_id.
    """
    cursor = self.db.cursor()
    audit_id = None
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(sql, params)
        # Log audit event (inside same transaction)
        audit_id = self._log_audit(
            cursor=cursor,
            endpoint=endpoint,
            method=action.upper(),
            table=table,
            result_status=200,
            write_boundary_enforced=True,
            gate_valid=True,
        )
        cursor.execute("COMMIT")
        return {"success": True, "audit_id": audit_id}
    except Exception as e:
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            pass
        # Log failed audit (best-effort, outside transaction)
        self._log_audit(
            endpoint=endpoint,
            method=action.upper(),
            table=table,
            result_status=500,
            write_boundary_enforced=True,
            gate_valid=False,
            details=str(e),
        )
        raise
```

#### 0D. CouncilCoreStore — Audit Logging Method

```python
def _log_audit(
    self,
    *,
    endpoint: str,
    method: str,
    table: str = None,
    record_id: str = None,
    action: str = None,
    actor: str = "system",
    result_status: int = 200,
    write_boundary_enforced: bool = True,
    gate_valid: bool = True,
    bypass: bool = False,
    bypass_user: str = None,
    bypass_justification: str = None,
    details: str = None,
    cursor: sqlite3.Cursor = None,
) -> str:
    """Insert audit event. Returns audit_id."""
    audit_id = str(uuid.uuid4())[:8]
    now = _utcnow_iso()
    exec_cursor = cursor or self.db.cursor()
    exec_cursor.execute("""
        INSERT INTO audit_events
        (id, timestamp, endpoint, method, result_status,
         write_boundary_enforced, gate_valid, bypass, bypass_user,
         bypass_justification, details, table_name, record_id, action, actor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        audit_id, now, endpoint, method, result_status,
        write_boundary_enforced, gate_valid, bypass, bypass_user,
        bypass_justification, details, table, record_id, action, actor,
    ))
    return audit_id
```

#### 0E. CouncilCoreStore — OutputGate Validation

Add content validation before all `create_*` methods:

```python
def _validate_content(self, table: str, data: Dict[str, Any]) -> bool:
    """Validate content before storage. Prevents poison writes.

    Checks:
    1. No NULL in NOT NULL columns
    2. No values exceeding column type constraints
    3. No injection patterns (check against blacklist)
    4. Content length within reasonable bounds
    5. JSON columns are valid JSON
    """
    # Check injection blacklist
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 0:
            if self._is_blacklisted(value):
                self._upsert_injection_blacklist("content_injection", value)
                return False
    # Check JSON columns
    json_columns = {'metadata', 'tags', 'sections', 'ai_metadata', 'headers'}
    for key in json_columns:
        if key in data and data[key] and isinstance(data[key], str):
            try:
                json.loads(data[key])
            except json.JSONDecodeError:
                return False
    return True

def _is_blacklisted(self, text: str) -> bool:
    """Check if text matches an active injection blacklist pattern."""
    row = self.db.execute("""
        SELECT 1 FROM injection_blacklist
        WHERE pattern = ? AND is_active = 1
    """, (hashlib.sha256(text.encode()).hexdigest()[:16],)).fetchone()
    return row is not None

def _upsert_injection_blacklist(self, pattern_type: str, pattern: str, threshold: int = 3) -> None:
    """Record or increment a blacklist failure."""
    pattern_hash = hashlib.sha256(pattern.encode()).hexdigest()[:16]
    blacklist_id = f"bl-{pattern_type}-{pattern_hash}"
    now = _utcnow_iso()
    existing = self.db.execute(
        "SELECT failure_count, threshold, is_active FROM injection_blacklist "
        "WHERE blacklist_id = ?", (blacklist_id,)).fetchone()
    if existing:
        new_count = existing[0] + 1
        is_active = 1 if new_count >= existing[1] else existing[2]
        self.db.execute(
            "UPDATE injection_blacklist SET failure_count = ?, last_failure_at = ?, is_active = ? "
            "WHERE blacklist_id = ?",
            (new_count, now, is_active, blacklist_id),
        )
    else:
        is_active = 1 if threshold <= 1 else 0
        self.db.execute(
            "INSERT INTO injection_blacklist "
            "(blacklist_id, pattern_type, pattern, failure_count, threshold, "
            " first_failure_at, last_failure_at, is_active) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
            (blacklist_id, pattern_type, pattern_hash, threshold, now, now, is_active),
        )
```

#### 0F. CouncilCoreStore — Migration Path Fix

Make migration path configurable (not hardcoded):

```python
def __init__(self, db_path: str, migrations_dir: str = None):
    # ...
    self._migrations_dir = migrations_dir or os.path.join(
        os.path.dirname(__file__), "..", "..", "migrations_council_core"
    )
    # Or better: align with RelationalStore pattern
    # self._migrations_dir = os.path.join(os.path.dirname(__file__), "..", "..", "migrations")
```

#### 0G. MemoryLayer Wiring

Add MemoryLayer reference to CouncilCoreStore (mirrors RelationalStore):

```python
def __init__(self, db_path: str, memory_layer: Optional["MemoryLayer"] = None):
    # ...
    self.memory_layer: Optional["MemoryLayer"] = memory_layer
```

Route knowledge_cards and memory_entries through MemoryLayer for vector indexing:

```python
def create_knowledge_card(self, topic, title, body, ...):
    # ...
    result = self._atomic_write(sql, params, "knowledge_cards", "create", "create_knowledge_card")
    # Route through MemoryLayer for vector indexing
    if self.memory_layer:
        self.memory_layer.ingest_artifact(
            run_id=source_run_id,
            phase="knowledge",
            key=f"card:{card_id}",
            content=f"{topic}: {title} — {body[:2000]}",
        )
    return result
```

### Files to Create/Modify (Phase 0)

| Action | File | Purpose |
|--------|------|---------|
| Modify | `migrations_council_core/01_core_tables.sql` | Add `audit_events` + `injection_blacklist` tables |
| Modify | `memory_service/council_core_store.py` | Add `_atomic_write()`, `_log_audit()`, `_validate_content()`, `_is_blacklisted()`, `_upsert_injection_blacklist()` |
| Modify | `memory_service/council_core_store.py` | Add `memory_layer` param to `__init__` |
| Modify | `memory_service/council_core_store.py` | Wrap all `create_*` methods in `_atomic_write()` |
| Modify | `memory_service/council_core_store.py` | Add `_validate_content()` call before all INSERTs |
| Modify | `memory_service/config.py` | Add `council_core_migrations_dir` config |

### Phase 0 Success Criteria

- [ ] `audit_events` table exists in council_core.db
- [ ] `injection_blacklist` table exists in council_core.db
- [ ] All `create_*` methods use `_atomic_write()` (BEGIN IMMEDIATE...COMMIT)
- [ ] ROLLBACK verified: inject error mid-transaction → no partial write
- [ ] `_validate_content()` rejects invalid JSON in JSON columns
- [ ] `_is_blacklisted()` blocks patterns with `is_active=1`
- [ ] `_upsert_injection_blacklist()` increments failure_count, activates at threshold
- [ ] Every write logs to `audit_events` (success and failure)
- [ ] Bypass tracking works: `bypass=1` requires `bypass_user` + `bypass_justification`
- [ ] MemoryLayer reference wired (even if None, the path exists)
- [ ] Migration path is configurable (not hardcoded)
- [ ] All existing tests pass (no regression)

### Anti-Patterns to Avoid

- ❌ Direct `self.db.execute(INSERT)` without transaction wrapper → ✅ Always `_atomic_write()`
- ❌ No audit logging → ✅ Every write logs to `audit_events`
- ❌ Silent failures (exception swallowed) → ✅ ROLLBACK + audit log + re-raise
- ❌ No content validation → ✅ `_validate_content()` before every INSERT
- ❌ Hardcoded migration path → ✅ Configurable via `__init__` param
- ❌ MemoryLayer bypass → ✅ Route through MemoryLayer when available

---

## Phase 1: Schema Design — Unified Column Specification

**What:** Define the final column specification for every table, merging Odysseus columns with Council governance columns.

**Dependencies:** Phase 0 (poison prevention tables must be in migration SQL first).
- **Phase 3:** Depends on Phase 2 (needs final schema)
- **Phase 4:** Depends on Phase 3 (needs updated store)

---

## Phase 1: Schema Design — Unified Column Specification

**What:** Define the final column specification for every table, merging Odysseus columns with Council governance columns.

**Output:** A complete column specification document (embedded in the migration SQL as comments).

### Unified Column Convention

Every table gets these governance columns (Council adds these):

```sql
revision INTEGER NOT NULL DEFAULT 1,
created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
updated_by TEXT NOT NULL DEFAULT 'system',
updated_source TEXT NOT NULL DEFAULT 'council',
origin_source TEXT NOT NULL DEFAULT 'council',
status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
is_deleted INTEGER NOT NULL DEFAULT 0
```

### Unified AI Classification + Token Budgeting

Instead of separate columns scattered across tables, create **one unified tracking pattern**:

```sql
-- Unified AI metadata column (replaces ai_classification, ai_content_hash separately)
ai_metadata TEXT DEFAULT '{}',  -- JSON: {classification: "...", content_hash: "...", confidence: 0.0, model: "..."}

-- Unified token budgeting (replaces total_input_tokens, total_output_tokens per-session)
-- Stored at the session level, not per-message
-- Also tracks per-operation tokens for research/task runs
```

### Table-by-Table Specification

#### `sessions` (merged Odysseus + Council)

| Column | Source | Type | Notes |
|---|---|---|---|
| `id` | Both | TEXT PK | |
| `name` | Both | TEXT NOT NULL | |
| `endpoint_url` | Odysseus | TEXT NOT NULL | |
| `model` | Both | TEXT NOT NULL | |
| `owner` | Odysseus | TEXT | Single-user, no FK |
| `has_rag` | Odysseus (`rag`) | INTEGER DEFAULT 0 | Renamed from `rag` |
| `is_archived` | Odysseus (`archived`) | INTEGER DEFAULT 0 | Renamed from `archived` |
| `folder` | Odysseus | TEXT | |
| `headers` | Odysseus | TEXT (JSON) | |
| `last_accessed` | Odysseus | TEXT | |
| `last_message_at` | Odysseus | TEXT | |
| `is_important` | Odysseus | INTEGER DEFAULT 0 | |
| `message_count` | Odysseus | INTEGER | |
| `total_input_tokens` | Odysseus | INTEGER DEFAULT 0 | **KEPT** — token budgeting |
| `total_output_tokens` | Odysseus | INTEGER DEFAULT 0 | **KEPT** — token budgeting |
| `mode` | Odysseus | TEXT | 'chat', 'agent', 'research' |
| `crew_member_id` | Odysseus | TEXT | Agent persona reference |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** — project scoping |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** — unified AI classification |
| Governance columns | Council | — | revision, created_at, updated_at, updated_by, updated_source, origin_source, status, is_deleted |

#### `chat_messages` (merged)

| Column | Source | Notes |
|---|---|---|
| `id` | Both | TEXT PK |
| `session_id` | Both | FK → sessions(id) |
| `role` | Both | TEXT NOT NULL |
| `content` | Both | TEXT NOT NULL |
| `metadata` | Both | TEXT (JSON) |
| `timestamp` | Both | TEXT |
| Governance columns | Council | **ADDED** |

#### `notes` (merged — keep ALL Odysseus columns)

| Column | Source | Notes |
|---|---|---|
| `id` | Both | TEXT PK |
| `owner` | Odysseus | TEXT |
| `title` | Both | TEXT |
| `content` | Both | TEXT |
| `items` | Odysseus | TEXT (JSON array) |
| `note_type` | Odysseus | TEXT |
| `color` | Odysseus | TEXT | **KEPT** — UI chrome |
| `label` | Odysseus | TEXT | **KEPT** — UI chrome |
| `is_pinned` | Odysseus (`pinned`) | INTEGER DEFAULT 0 | **KEPT** — renamed |
| `is_archived` | Odysseus (`archived`) | INTEGER DEFAULT 0 | **KEPT** — renamed |
| `due_date` | Odysseus | TEXT | |
| `source` | Odysseus | TEXT | |
| `session_id` | Odysseus | FK → sessions(id) | |
| `sort_order` | Odysseus | INTEGER | **KEPT** — UI chrome |
| `image_url` | Odysseus | TEXT | **KEPT** — UI chrome |
| `repeat` | Odysseus | TEXT | **KEPT** — UI chrome |
| `ai_classification` | Odysseus | TEXT | **KEPT** — will be merged into ai_metadata |
| `ai_content_hash` | Odysseus | TEXT | **KEPT** — will be merged into ai_metadata |
| `agent_session_id` | Odysseus | TEXT | |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** — supersedes ai_classification + ai_content_hash |
| Governance columns | Council | **ADDED** |

#### `documents` (merged)

| Column | Source | Notes |
|---|---|---|
| `id` | Both | TEXT PK |
| `session_id` | Both | FK → sessions(id) |
| `title` | Both | TEXT NOT NULL |
| `language` | Both | TEXT |
| `current_content` | Both | TEXT NOT NULL |
| `version_count` | Both | INTEGER |
| `is_active` | Both | INTEGER DEFAULT 1 |
| `is_archived` | Odysseus (`archived`) | INTEGER DEFAULT 0 | Renamed |
| `owner` | Odysseus | TEXT |
| `tidy_verdict` | Odysseus | TEXT | **KEPT** — AI analysis result |
| `source_email_uid` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `source_email_folder` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `source_email_account_id` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `source_email_message_id` | Odysseus | TEXT | **DEFERRED** — nullable, add later |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** |
| Governance columns | Council | **ADDED** |

#### `memories` (merged)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `text` | Odysseus | TEXT NOT NULL |
| `category` | Odysseus | TEXT |
| `source` | Odysseus | TEXT |
| `owner` | Odysseus | TEXT |
| `session_id` | Odysseus | FK → sessions(id) |
| `timestamp` | Odysseus | INTEGER |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `confidence` | Council draft | REAL | **ADDED** — from unified draft §4.2 |
| `tags` | Council draft | TEXT DEFAULT '[]' | **ADDED** |
| `tier` | Council draft | TEXT | **ADDED** — consolidation tier |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** |
| Governance columns | Council | **ADDED** |

#### `gallery_images` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `filename` | Odysseus | TEXT NOT NULL UNIQUE |
| `prompt` | Odysseus | TEXT NOT NULL |
| `model` | Odysseus | TEXT |
| `size` | Odysseus | TEXT |
| `quality` | Odysseus | TEXT |
| `tags` | Odysseus | TEXT |
| `ai_tags` | Odysseus | TEXT (JSON) | **KEPT** — AI analysis |
| `session_id` | Odysseus | FK → sessions(id) |
| `album_id` | Odysseus | FK → gallery_albums(id) |
| `owner` | Odysseus | TEXT |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `favorite` | Odysseus | INTEGER DEFAULT 0 | **KEPT** — UI chrome |
| `file_hash` | Odysseus | TEXT(64) |
| `taken_at` | Odysseus | TEXT |
| `camera_make` | Odysseus | TEXT |
| `camera_model` | Odysseus | TEXT |
| `gps_lat` | Odysseus | TEXT |
| `gps_lng` | Odysseus | TEXT |
| `width` | Odysseus | INTEGER |
| `height` | Odysseus | INTEGER |
| `file_size` | Odysseus | INTEGER |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| `ai_metadata` | Unified | TEXT (JSON) DEFAULT '{}' | **NEW** — unified analysis results |
| Governance columns | Council | **ADDED** |

#### `gallery_albums` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `description` | Odysseus | TEXT |
| `cover_id` | Odysseus | TEXT FK → gallery_images(id) |
| `owner` | Odysseus | TEXT |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| Governance columns | Council | **ADDED** |

#### `editor_drafts` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `owner` | Odysseus | TEXT |
| `name` | Odysseus | TEXT NOT NULL |
| `source_image_id` | Odysseus | TEXT FK → gallery_images(id) |
| `width` | Odysseus | INTEGER |
| `height` | Odysseus | INTEGER |
| `payload` | Odysseus | TEXT NOT NULL (JSON) |
| `thumbnail` | Odysseus | TEXT |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `project_id` | Council | TEXT FK → projects(id) | **ADDED** |
| Governance columns | Council | **ADDED** |

#### `signatures` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `owner` | Odysseus | TEXT |
| `name` | Odysseus | TEXT NOT NULL |
| `data_png` | Odysseus | TEXT NOT NULL (base64) |
| `width` | Odysseus | INTEGER |
| `height` | Odysseus | INTEGER |
| `svg` | Odysseus | TEXT |
| Governance columns | Council | **ADDED** |

#### `integrations` (NEW — from Odysseus, for upload→analyze pipeline)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `owner` | Odysseus | TEXT |
| `name` | Odysseus | TEXT NOT NULL |
| `type` | Odysseus | TEXT NOT NULL |
| `config` | Odysseus | TEXT (JSON) |
| `is_enabled` | Odysseus | INTEGER DEFAULT 1 |
| Governance columns | Council | **ADDED** |

#### `mcp_servers` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `transport` | Odysseus | TEXT NOT NULL |
| `command` | Odysseus | TEXT |
| `args` | Odysseus | TEXT |
| `env` | Odysseus | TEXT (JSON) |
| `url` | Odysseus | TEXT |
| `is_enabled` | Odysseus | INTEGER DEFAULT 1 |
| `oauth_config` | Odysseus | TEXT (JSON) |
| `disabled_tools` | Odysseus | TEXT (JSON) |
| Governance columns | Council | **ADDED** |

#### `webhooks` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `url` | Odysseus | TEXT NOT NULL |
| `secret` | Odysseus | TEXT |
| `events` | Odysseus | TEXT NOT NULL |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `last_triggered_at` | Odysseus | TEXT |
| `last_status_code` | Odysseus | INTEGER |
| `last_error` | Odysseus | TEXT |
| Governance columns | Council | **ADDED** |

#### `user_tools` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | TEXT PK |
| `name` | Odysseus | TEXT NOT NULL |
| `description` | Odysseus | TEXT |
| `icon` | Odysseus | TEXT |
| `html_content` | Odysseus | TEXT NOT NULL |
| `scope` | Odysseus | TEXT NOT NULL |
| `session_id` | Odysseus | FK → sessions(id) |
| `owner` | Odysseus | TEXT |
| `is_pinned` | Odysseus | INTEGER DEFAULT 0 |
| `is_active` | Odysseus | INTEGER DEFAULT 1 |
| `version` | Odysseus | INTEGER |
| `author` | Odysseus | TEXT |
| Governance columns | Council | **ADDED** |

#### `user_tool_data` (NEW — from Odysseus)

| Column | Source | Notes |
|---|---|---|
| `id` | Odysseus | INTEGER PK (autoincrement) |
| `tool_id` | Odysseus | FK → user_tools(id) |
| `key` | Odysseus | TEXT NOT NULL |
| `value` | Odysseus | TEXT |
| Governance columns (lite) | Council | created_at, updated_at only |

---

## Phase 1B: Column Audit — Odysseus app.db Inventory

**What:** Dump the full schema from Odysseus app.db and verify every column is accounted for in the unified spec.

**Steps:**
1. Run `sqlite3 vendor/odysseus/data/app.db ".schema"` and capture output
2. Cross-reference every column against the Phase 1 spec
3. Flag any Odysseus column not in the spec
4. Flag any spec column not in Odysseus (these are Council additions — verify they're intentional)

**Output:** Audit report as comments in the migration SQL.

---

## Phase 2: Migration SQL — Unified Schema

**What:** Rewrite `migrations_council_core/01_core_tables.sql` with the unified schema.

**Files:**
- `migrations_council_core/01_core_tables.sql` — complete rewrite
- `migrations_council_core/02_fts5_indexes.sql` — add FTS5 for new tables

**Steps:**
1. Keep existing tables (projects, work_items, workflow_runs, reviews, review_findings, prompt_templates, knowledge_cards, memory_entries, memory_rollups, research_reports) — they're correct
2. Rewrite `sessions` with unified columns (has_rag, is_archived, project_id, ai_metadata, governance)
3. Rewrite `chat_messages` with governance columns
4. Rewrite `notes` with ALL Odysseus columns + project_id + ai_metadata + governance
5. Rewrite `documents` with unified columns + governance (email columns as nullable DEFERRED)
6. Rewrite `memories` with project_id, confidence, tags, tier, ai_metadata, governance
7. Add `gallery_images` table
8. Add `gallery_albums` table
9. Add `editor_drafts` table
10. Add `signatures` table
11. Add `integrations` table
12. Add `mcp_servers` table
13. Add `webhooks` table
14. Add `user_tools` table
15. Add `user_tool_data` table
16. Add indexes for all new FK columns and hot-read paths
17. Update `02_fts5_indexes.sql` to add FTS5 for: gallery_images (prompt, ai_tags), editor_drafts (name, payload), integrations (name, type), user_tools (name, description)

**Constraints:**
- **Idempotent:** Every CREATE TABLE uses `IF NOT EXISTS`
- **FK-safe:** All foreign keys reference existing tables (create in dependency order)
- **SQLite types only:** TEXT, INTEGER, REAL — no BOOLEAN, no TIMESTAMPTZ, no JSONB
- **Governance columns on EVERY table:** No exceptions
- **ai_metadata on content-bearing tables:** sessions, notes, documents, memories, gallery_images
- **project_id on all user-data tables:** For project scoping (Gap 4)

---

## Phase 3: CouncilCoreStore — Updated Access Layer

**What:** Update `memory_service/council_core_store.py` to support new tables and unified columns.

**Steps:**
1. Add CRUD for `gallery_images` — create, list, search by tags/ai_tags, get by filename
2. Add CRUD for `gallery_albums` — create, list, get by id
3. Add CRUD for `editor_drafts` — create, list, get by id, update payload
4. Add CRUD for `signatures` — create, list, get by name
5. Add CRUD for `integrations` — create, list, enable/disable
6. Add CRUD for `mcp_servers` — create, list, enable/disable, update config
7. Add CRUD for `webhooks` — create, list, trigger, get last status
8. Add CRUD for `user_tools` — create, list, pin/unpin, enable/disable
9. Add CRUD for `user_tool_data` — get/set by (tool_id, key)
10. Update `get_sessions()` to include `total_input_tokens`, `total_output_tokens`, `ai_metadata`
11. Update `get_notes()` to include all UI chrome columns + `ai_metadata`
12. Update `get_documents()` to include `project_id`, `ai_metadata`
13. Add `get_memories()` method with project_id filter
14. Update `health_check()` to report row counts for all new tables

**Constraints:**
- **No raw SQL in MCP layer:** All queries go through CouncilCoreStore methods
- **Parameterized queries only:** No string concatenation for SQL
- **WAL mode:** All connections use `PRAGMA journal_mode=WAL`

---

## Phase 4: Apply Migrations + Data Migration + Verification

**What:** Apply the unified migration to council_core.db, migrate data from Odysseus app.db, verify end-to-end.

**Steps:**

### 4A. Apply Migration
1. Backup council_core.db: `cp ~/.council-memory/council_core.db ~/.council-memory/council_core.db.backup.pre-unification`
2. Run migration SQL against council_core.db (use ALTER TABLE for existing tables, CREATE TABLE for new ones)
3. Verify all tables exist: `SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`

### 4B. Migrate Odysseus Data
1. Copy `sessions` from app.db → council_core.db (map `rag→has_rag`, `archived→is_archived`)
2. Copy `chat_messages` from app.db → council_core.db
3. Copy `notes` from app.db → council_core.db (map `pinned→is_pinned`, `archived→is_archived`)
4. Copy `documents` from app.db → council_core.db (map `archived→is_archived`)
5. Copy `memories` from app.db → council_core.db (0 rows expected, but migrate schema)
6. Copy `gallery_images` from app.db → council_core.db (if data exists)
7. Copy `gallery_albums` from app.db → council_core.db (if data exists)
8. Copy `editor_drafts` from app.db → council_core.db (if data exists)
9. Copy `integrations` from app.db → council_core.db (if data exists)
10. Copy `mcp_servers` from app.db → council_core.db (if data exists)
11. Copy `webhooks` from app.db → council_core.db (if data exists)
12. Copy `user_tools` from app.db → council_core.db (if data exists)
13. For all migrated rows: set `origin_source='odysseus'`, `updated_source='migration'`

### 4C. Backfill Missing Columns
1. `ALTER TABLE memory_entries ADD COLUMN project_id TEXT REFERENCES projects(id)` (if not present)
2. `ALTER TABLE memory_rollups ADD COLUMN project_id TEXT REFERENCES projects(id)` (if not present)
3. `ALTER TABLE knowledge_cards ADD COLUMN project_id TEXT REFERENCES projects(id)` (if not present)
4. Backfill `ai_metadata` = '{}' for all existing rows in sessions, notes, documents, memories, gallery_images

### 4D. Verification
1. Run `health_check()` — all tables present, row counts match expectations
2. Verify FK integrity: `PRAGMA foreign_key_check`
3. Verify FTS5 indexes: `SELECT COUNT(*) FROM <table>_fts`
4. Verify data migration: compare row counts between app.db and council_core.db
5. Test CouncilCoreStore CRUD for each new table

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `migrations_council_core/01_core_tables.sql` | Add `audit_events` + `injection_blacklist` + unified schema |
| Modify | `migrations_council_core/02_fts5_indexes.sql` | FTS5 for new tables |
| Modify | `memory_service/council_core_store.py` | Phase 0: `_atomic_write()`, `_log_audit()`, `_validate_content()`, `_is_blacklisted()`, `_upsert_injection_blacklist()` |
| Modify | `memory_service/council_core_store.py` | Phase 3: CRUD for all new tables + updated column access |
| Modify | `memory_service/council_core_store.py` | Phase 3: Wrap all `create_*` in `_atomic_write()` |
| Modify | `memory_service/council_core_store.py` | Phase 3: Add `memory_layer` param to `__init__` |
| Create | `migrations_council_core/03_unify_odysseus_columns.sql` | ALTER TABLE + data migration from app.db |
| Modify | `memory_service/config.py` | Add `council_core_migrations_dir` + new table config |

---

## Constraints

- **SQLite only:** No PostgreSQL types. TEXT for PKs, TEXT for timestamps, TEXT for JSON.
- **Idempotent migrations:** Safe to re-run. Use `IF NOT EXISTS`, `ALTER TABLE IF NOT EXISTS` (or check-first pattern).
- **FK enforcement:** `PRAGMA foreign_keys=ON` on all connections.
- **WAL mode:** `PRAGMA journal_mode=WAL` on all connections.
- **SQLite only:** No PostgreSQL types. TEXT for PKs, TEXT for timestamps, TEXT for JSON.
- **Idempotent migrations:** Safe to re-run. Use `IF NOT EXISTS`, `ALTER TABLE IF NOT EXISTS` (or check-first pattern).
- **FK enforcement:** `PRAGMA foreign_keys=ON` on all connections.
- **WAL mode:** `PRAGMA journal_mode=WAL` on all connections.
- **Atomic writes mandatory:** All multi-row writes use `BEGIN IMMEDIATE...COMMIT` with `ROLLBACK` on error. No autocommit for writes.
- **Audit trail mandatory:** Every write logs to `audit_events` (success AND failure). No exceptions.
- **Write boundary enforced:** Every `create_*` method validates content via `_validate_content()` before INSERT.
- **Injection blacklist active:** `_is_blacklisted()` checks before every INSERT. Patterns with `is_active=1` are blocked.
- **Bypass tracking:** If a guard is bypassed, `bypass=1` requires `bypass_user` + `bypass_justification`.
- **MemoryLayer wired:** CouncilCoreStore accepts `memory_layer` param. Artifacts route through MemoryLayer when available.
- **Migration path configurable:** Not hardcoded. Passable via `__init__` param.
- **Governance columns mandatory:** Every table gets revision, created_at, updated_at, updated_by, updated_source, origin_source, status, is_deleted.
- **ai_metadata unified:** Single JSON column replaces scattered ai_classification, ai_content_hash columns. Both old columns KEPT for backward compatibility but deprecated.
- **Token budgeting unified:** total_input_tokens + total_output_tokens on sessions. Per-operation token tracking via metadata JSON on workflow_runs/task_runs.
- **project_id on all user-data tables:** No exceptions. NULL allowed (late binding via 4-channel resolution).
- **No data loss:** Source DBs (app.db, pipelines.db) preserved as backups.
- **Single-user model:** No users table. `owner` is TEXT username, not FK.

---

## Success Criteria

### Poison Prevention (Phase 0 — GATE)
- [ ] `audit_events` table exists in council_core.db
- [ ] `injection_blacklist` table exists in council_core.db
- [ ] All `create_*` methods use `_atomic_write()` (BEGIN IMMEDIATE...COMMIT)
- [ ] ROLLBACK verified: inject error mid-transaction → no partial write
- [ ] `_validate_content()` rejects invalid JSON in JSON columns
- [ ] `_is_blacklisted()` blocks patterns with `is_active=1`
- [ ] `_upsert_injection_blacklist()` increments failure_count, activates at threshold
- [ ] Every write logs to `audit_events` (success AND failure)
- [ ] Bypass tracking works: `bypass=1` requires `bypass_user` + `bypass_justification`
- [ ] MemoryLayer reference wired (even if None, the path exists)
- [ ] Migration path is configurable (not hardcoded)

### Schema Unification (Phases 1-2)
- [ ] `01_core_tables.sql` contains unified schema for all 20+ tables
- [ ] Every table has governance columns (revision, updated_by, origin_source, is_deleted, etc.)
- [ ] `ai_metadata` column on sessions, notes, documents, memories, gallery_images
- [ ] `total_input_tokens` + `total_output_tokens` on sessions (token budgeting)
- [ ] All UI chrome columns kept (color, label, sort_order, image_url, repeat, pinned, favorite)
- [ ] Media/gallery tables present (gallery_images, gallery_albums, editor_drafts, signatures)
- [ ] Extensibility tables present (integrations, mcp_servers, webhooks, user_tools, user_tool_data)
- [ ] `project_id` FK on all user-data tables
- [ ] FTS5 indexes on all content-bearing tables

### Data Migration + Verification (Phase 4)
- [ ] Migration applied to council_core.db without errors
- [ ] Data migrated from app.db (sessions, chat_messages, notes, documents, memories)
- [ ] `PRAGMA foreign_key_check` passes (no FK violations)
- [ ] CouncilCoreStore CRUD works for all new tables
- [ ] `health_check()` reports all tables with correct row counts
- [ ] Source DBs (app.db, pipelines.db) untouched
- [ ] All existing tests pass (no regression)

---

## Caveats & Uncertainty

1. **Email columns are DEFERRED but present as nullable:** `source_email_*` columns exist in documents but are NULL. If email integration is built later, they're ready. If not, they're dead weight (5 nullable TEXT columns).
2. **ai_classification + ai_content_hash kept alongside ai_metadata:** For backward compatibility during transition. Plan to deprecate and remove after 2-4 weeks once all code uses ai_metadata.
3. **crew_member_id on sessions:** Kept because Odysseus agent personas may be useful. But Council's model dispatch is skills-based, not DB-based. May become orphaned if crew_members table is not wired.
4. **Gallery tables may have 0 rows:** Odysseus app.db likely has no gallery data. Tables exist but are empty. Verify before spending time on migration.
5. **mcp_servers overlap:** Council already has MCP via Pi extension. Odysseus mcp_servers table may duplicate this. Consider whether to merge or keep separate.

---

## Stress Test

1. **If Odysseus schema changes upstream:** Migration SQL is idempotent. New columns can be added via ALTER TABLE. Governance columns are stable.
2. **If multi-user is needed later:** `owner` TEXT → FK to users table. Breaking change but contained (one column per table).
3. **If email integration is built:** `source_email_*` columns already exist. Just populate them.
4. **If gallery/media grows large:** `gallery_images` has `file_hash` UNIQUE index for dedup. Consider blob storage migration if >10K images.

---

## Notes for Executor

- Read `vendor/odysseus/data/app.db` schema FIRST to verify column names match the spec
- The `migrate_data.py` in `migrations_council_core/` has existing migration logic — extend it, don't rewrite
- CouncilCoreStore uses `sqlite3.Row` as row_factory — all queries return dicts
- The unified DB draft (`13-council-core-unified-db-draft.md`) has the original design decisions — reference it for rationale
