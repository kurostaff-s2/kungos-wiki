# Phase 1: Schema Migration

**Parent plan:** `06-06-2026_task-ledger-deviation-tracking_3fce71.md`
**Phase:** 1 of 5
**Dependencies:** None (first phase)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Database:** `/home/chief/.council-memory/council_core.db` (primary), `/home/chief/.council-memory/pipelines.db` (secondary)
**Key files for this phase:**
- `super_council/memory_service/migrations/001_task_ledger_schema.sql` (create)
- `super_council/memory_service/store.py` (modify — add CRUD methods)

---

## What This Phase Delivers

Extended `work_items` table with 7-state status model and run_id provenance linkage. New `plan_deviations` and `plan_deviations_events` tables. CRUD methods in `RelationalStore` for all new tables.

---

## Pre-Flight Checklist

- [ ] Both databases are accessible (`council_core.db` and `pipelines.db`)
- [ ] Migration directory exists or can be created
- [ ] Current `work_items` schema is backed up (copy the table definition)

---

## Implementation Steps

### Step 1: Write Migration SQL

Create `super_council/memory_service/migrations/001_task_ledger_schema.sql` with:

**1a. Extend `work_items` status:**
```sql
-- SQLite doesn't support ALTER TABLE to add CHECK constraints.
-- Recreate table with new constraint.
CREATE TABLE work_items_new (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    parent_id TEXT REFERENCES work_items(id),
    kind TEXT NOT NULL CHECK (kind IN ('pipeline','review','delegation','task','ad_hoc')),
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT CHECK (priority IN ('low','medium','high','critical')),
    phase TEXT,
    assigned_to TEXT,
    due_at TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    external_key TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    updated_by TEXT NOT NULL DEFAULT 'system',
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('proposed','open','in_progress','blocked','done','wont_do','superseded','active','archived')),
    is_deleted INTEGER NOT NULL DEFAULT 0,
    is_indexed INTEGER DEFAULT 0,
    index_failures INTEGER DEFAULT 0,
    first_seen_run_id TEXT REFERENCES workflow_runs(id),
    last_seen_run_id TEXT REFERENCES workflow_runs(id),
    last_touched_run_id TEXT REFERENCES workflow_runs(id)
);
INSERT INTO work_items_new SELECT * FROM work_items;
DROP TABLE work_items;
ALTER TABLE work_items_new RENAME TO work_items;
```

**1b. Create `plan_deviations` table:**
```sql
CREATE TABLE IF NOT EXISTS plan_deviations (
    deviation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    plan_id TEXT,
    run_id TEXT REFERENCES workflow_runs(id),
    title TEXT NOT NULL,
    description TEXT,
    deviation_type TEXT CHECK (deviation_type IN ('planned','unplanned','optimization')),
    severity TEXT CHECK (severity IN ('minor','moderate','major','critical')),
    original_plan_summary TEXT,
    actual_implementation TEXT,
    rationale TEXT,
    risk_assessment TEXT,
    impact_scope TEXT,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','implemented','closed','rejected')),
    decision_author TEXT,
    decision_at TEXT,
    decision_summary TEXT,
    first_seen_run_id TEXT REFERENCES workflow_runs(id),
    source_summary_id TEXT,
    evidence_hash TEXT,
    related_work_item_id TEXT REFERENCES work_items(id),
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    updated_by TEXT NOT NULL DEFAULT 'system',
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    is_deleted INTEGER NOT NULL DEFAULT 0
);
```

**1c. Create `plan_deviations_events` table:**
```sql
CREATE TABLE IF NOT EXISTS plan_deviations_events (
    event_id TEXT PRIMARY KEY,
    deviation_id TEXT NOT NULL REFERENCES plan_deviations(deviation_id),
    run_id TEXT REFERENCES workflow_runs(id),
    source_summary_id TEXT,
    event_type TEXT CHECK (event_type IN ('created','proposed','approved','implemented','closed','rejected')),
    old_status TEXT,
    new_status TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_deviations_events_deviation_id ON plan_deviations_events(deviation_id);
```

**1d. Create `carry_forward` table (typed structured payload, not TEXT blobs):**
```sql
CREATE TABLE IF NOT EXISTS carry_forward (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    tier TEXT NOT NULL CHECK (tier IN ('daily','short','weekly','bimonthly')),
    kind TEXT NOT NULL CHECK (kind IN ('unresolved_work','risk','continuity_note','decision_pending','blocker')),  -- bounded enum, not freeform
    text TEXT NOT NULL,  -- the carry-forward content
    priority TEXT CHECK (priority IN ('low','medium','high','critical')),
    source_entry_id TEXT,  -- provenance: which consolidation entry produced this item
    expires_after_tier INTEGER NOT NULL DEFAULT 2,  -- expires after N same-tier cycles unless reasserted
    ttl_runs INTEGER,  -- alternative: expires after N runs regardless of tier
    is_reasserted INTEGER NOT NULL DEFAULT 0,  -- was this item explicitly reasserted in a later cycle?
    reasserted_at TEXT,  -- when was it last reasserted?
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','consumed')),
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_carry_forward_project_tier ON carry_forward(project_id, tier);
CREATE INDEX IF NOT EXISTS idx_carry_forward_expires ON carry_forward(expires_after_tier, is_reasserted);

-- Constraint: max 5 active carry-forward items per (project_id, tier)
-- Enforced at application layer (RelationalStore), not SQL (SQLite lacks row-level triggers for this pattern)
```

**1e. Create `work_item_events` table (for status transition audit trail):**
```sql
CREATE TABLE IF NOT EXISTS work_item_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES work_items(id),
    run_id TEXT REFERENCES workflow_runs(id),
    source_summary_id TEXT,
    event_type TEXT CHECK (event_type IN ('created','status_changed','updated','merged','completed','archived')),
    old_status TEXT,
    new_status TEXT,
    evidence_span TEXT,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_work_item_events_task_id ON work_item_events(task_id);
```

**1f. Create `work_item_sources` table (for multi-run provenance):**
```sql
CREATE TABLE IF NOT EXISTS work_item_sources (
    source_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES work_items(id),
    run_id TEXT NOT NULL REFERENCES workflow_runs(id),
    source_type TEXT CHECK (source_type IN ('mention','creation','update','completion','blocking')),
    excerpt_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_work_item_sources_task_id ON work_item_sources(task_id);
```

### Step 2: Apply Migrations

Apply the migration SQL to both `council_core.db` and `pipelines.db`:
```python
import sqlite3
for db_path in ['/home/chief/.council-memory/council_core.db', '/home/chief/.council-memory/pipelines.db']:
    conn = sqlite3.connect(db_path)
    with open('migrations/001_task_ledger_schema.sql') as f:
        conn.executescript(f.read())
    conn.close()
```

### Step 3: Add CRUD Methods to RelationalStore

Add the following methods to `store.py`:

**3a. Work item methods:**
```python
def update_work_item_status(self, work_item_id: str, new_status: str, run_id: str = None, source_summary_id: str = None) -> Dict[str, Any]:
    """Update work item status and log the transition event."""

def log_work_item_event(self, task_id: str, event_type: str, old_status: str = None, new_status: str = None, run_id: str = None, source_summary_id: str = None, confidence: float = None) -> str:
    """Log a work item status transition event."""

def link_work_item_source(self, task_id: str, run_id: str, source_type: str, excerpt_hash: str = None) -> str:
    """Link a work item to a source run for provenance."""

def get_work_item_events(self, task_id: str) -> List[Dict[str, Any]]:
    """Get all events for a work item."""
```

**3c. Carry-forward methods (typed, bounded, capped):**
```python
def upsert_carry_forward(self, project_id: str, tier: str, kind: str, text: str, priority: str = 'medium', source_entry_id: str = None, expires_after_tier: int = 2) -> Dict[str, Any]:
    """Create or reassert a carry-forward item.
    Enforces: max 5 active items per (project_id, tier).
    Enforces: kind must be in bounded enum.
    Enforces: expires_after_tier defaults to 2 same-tier cycles.
    """
    # Check cap: max 5 active items per (project_id, tier)
    active_count = self.db.execute(
        "SELECT COUNT(*) FROM carry_forward "
        "WHERE project_id = ? AND tier = ? AND status = 'active' AND is_deleted = 0",
        (project_id, tier),
    ).fetchone()[0]
    if active_count >= 5:
        # Expire the oldest item to make room
        self.db.execute(
            "UPDATE carry_forward SET status = 'expired' "
            "WHERE project_id = ? AND tier = ? AND status = 'active' AND is_deleted = 0 "
            "ORDER BY created_at ASC LIMIT 1",
            (project_id, tier),
        )
        self.db.commit()

    item_id = str(uuid.uuid4())
    now = self._now_iso()
    self.db.execute(
        "INSERT INTO carry_forward (id, project_id, tier, kind, text, priority, source_entry_id, expires_after_tier, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, project_id, tier, kind, text, priority, source_entry_id, expires_after_tier, now, now),
    )
    self.db.commit()
    return {'id': item_id, 'project_id': project_id, 'tier': tier, 'kind': kind, 'text': text}

def expire_carry_forward(self, project_id: str, tier: str, cycles_since_reassert: int = 2) -> int:
    """Expire carry-forward items that haven't been reasserted within their TTL.
    Returns number of items expired.
    """
    # Items expire after N same-tier cycles unless reasserted
    cutoff = datetime.now(IST) - timedelta(days=cycles_since_reassert * 7)  # rough estimate
    self.db.execute(
        "UPDATE carry_forward SET status = 'expired' "
        "WHERE project_id = ? AND tier = ? AND status = 'active' AND is_deleted = 0 "
        "AND (is_reasserted = 0 OR reasserted_at < ?)",
        (project_id, tier, cutoff.isoformat()),
    )
    self.db.commit()
    return self.db.changes()

def get_active_carry_forward(self, project_id: str, tier: str) -> List[Dict[str, Any]]:
    """Get active carry-forward items for a project+tier.
    Returns at most 5 items (enforced at insert time).
    """
    rows = self.db.execute(
        "SELECT id, project_id, tier, kind, text, priority, source_entry_id, expires_after_tier, is_reasserted, created_at, updated_at "
        "FROM carry_forward "
        "WHERE project_id = ? AND tier = ? AND status = 'active' AND is_deleted = 0 "
        "ORDER BY priority DESC, created_at DESC "
        "LIMIT 5",
        (project_id, tier),
    ).fetchall()
    return [dict(r) for r in rows]
```

**3b. Deviation methods:**
```python
def create_deviation(self, project_id: str, title: str, deviation_type: str, severity: str = 'moderate', plan_id: str = None, run_id: str = None, original_plan_summary: str = None, actual_implementation: str = None, rationale: str = None, impact_scope: str = None, source_summary_id: str = None, related_work_item_id: str = None) -> Dict[str, Any]:
    """Create a new plan deviation record."""

def update_deviation_status(self, deviation_id: str, new_status: str, decision_author: str = None, decision_summary: str = None, run_id: str = None) -> Dict[str, Any]:
    """Update deviation status and log the event."""

def log_deviation_event(self, deviation_id: str, event_type: str, old_status: str = None, new_status: str = None, run_id: str = None, source_summary_id: str = None, notes: str = None) -> str:
    """Log a deviation status transition event."""

def get_deviations(self, project_id: str = None, status: str = None, deviation_type: str = None) -> List[Dict[str, Any]]:
    """Get deviations with optional filters."""

def get_open_deviations(self, project_id: str = None) -> List[Dict[str, Any]]:
    """Get open (not closed/rejected) deviations."""
```

### Step 4: Verify Schema

Run `PRAGMA table_info` on all new/modified tables in both databases. Verify:
- `work_items` has `first_seen_run_id`, `last_seen_run_id`, `last_touched_run_id` columns
- `work_items` CHECK constraint includes all 7 status values
- `plan_deviations` has all 15+ columns
- `plan_deviations_events` has correct columns
- `work_item_events` has correct columns
- `work_item_sources` has correct columns

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/memory_service/migrations/001_task_ledger_schema.sql` | Schema migration SQL |
| Modify | `super_council/memory_service/store.py` | Add CRUD methods for work_items, deviations, events, sources |

---

## Phase-Specific Tests

1. **Schema migration applies cleanly:** Run migration on both databases, verify no errors
2. **Status CHECK constraint works:** Try inserting invalid status → should fail
3. **Run_id provenance stored:** Create work item with run_id → verify columns are populated
4. **Deviation CRUD works:** Create → update → query deviation → verify all fields
5. **Event logging works:** Log status transition → query events → verify event is recorded
6. **Source linkage works:** Link work item to source run → query sources → verify linkage
7. **Carry-forward cap enforced:** Insert 6 items for same (project_id, tier) → only 5 active, oldest expired
8. **Carry-forward kind is bounded:** Insert with invalid kind → CHECK constraint fails
9. **Carry-forward expiration works:** Create item with expires_after_tier=2 → after 2 cycles without reassert → status = 'expired'
10. **Carry-forward is typed JSON:** Verify all fields are structured (kind, text, priority, source_entry_id, expires_after_tier) — no freeform TEXT blobs

---

## Completion Gate

- [ ] Migration SQL file created and tested on both databases
- [ ] All CRUD methods added to `RelationalStore`
- [ ] Schema verified with `PRAGMA table_info` on both databases
- [ ] All phase-specific tests pass
- [ ] No regression in existing `RelationalStore` methods

---

## Notes for Next Phase

Phase 2 (Reconciliation Engine) expects:
- `work_items` table with 7-state status and run_id columns
- `work_item_events` table for audit trail
- `work_item_sources` table for provenance
- CRUD methods: `update_work_item_status()`, `log_work_item_event()`, `link_work_item_source()`, `get_work_item_events()`
