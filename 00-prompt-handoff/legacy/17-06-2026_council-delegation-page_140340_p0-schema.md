# Unit 0: Bug Fix + Delegation Schema

**Parent plan:** `17-06-2026_council-delegation-page_140340.md`
**Phase:** 0 of 6
**Dependencies:** none
**Estimated effort:** ~30 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `memory_service/store/relational_store.py` — import new mixin
- `memory_service/store/delegation.py` — new DelegationStoreMixin (create)
- `migrations_council_core/08_delegation_runs.sql` — new migration (create)
- `council_main.py` lines 4860-5270 — fix transition_to bug
- `tests/test_delegation_runs.py` — new tests (create)

## What This Phase Delivers

Fixes the `transition_to` bug where `self.transition_to()` is called on `SlotSupervisor` instead of `PipelineState`. Adds `delegation_runs` table with delegation-specific metadata (from_model, to_model, role, chain_id). Provides RelationalStore methods: `insert_delegation()`, `query_delegations()`, `get_delegation()`.

## Pre-Flight Checklist

- [ ] Read `council_main.py` lines 4860-5270 (delegation code block)
- [ ] Read `memory_service/store/relational_store.py` (understand mixin pattern)
- [ ] Read `migrations_council_core/07_plan_deviations_hallucination.sql` (migration format reference)

## Implementation Steps

### Step 1: Write tests (RED phase)

Create `tests/test_delegation_runs.py` with these tests (must ALL fail initially):

```python
# Use store_with_tiers fixture from conftest.py
test_insert_delegation_creates_row
test_insert_delegation_stores_all_fields
test_insert_delegation_duplicate_chain_id_raises
test_query_delegations_returns_paginated_results
test_query_delegations_search_by_task
test_query_delegations_filter_by_to_model
test_get_delegation_returns_single
test_get_delegation_returns_none_for_missing
test_delegation_table_schema
```

Run: `cd /home/chief/Coding-Projects/7-council && python -m pytest super_council/tests/test_delegation_runs.py -v`
**Expected: ALL tests FAIL (AttributeError: 'RelationalStore' object has no attribute 'insert_delegation')**

### Step 2: Create migration SQL

Create `migrations_council_core/08_delegation_runs.sql`:

```sql
CREATE TABLE IF NOT EXISTS delegation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id TEXT UNIQUE NOT NULL,
    from_model TEXT,
    to_model TEXT NOT NULL,
    role TEXT NOT NULL,
    batch INTEGER DEFAULT 0,
    retry INTEGER DEFAULT 0,
    task TEXT,
    response TEXT,
    response_length INTEGER,
    md_file_path TEXT,
    run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_deleg_created_at ON delegation_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deleg_to_model ON delegation_runs(to_model);
CREATE INDEX IF NOT EXISTS idx_deleg_from_model ON delegation_runs(from_model);
```

### Step 3: Create DelegationStoreMixin

Create `memory_service/store/delegation.py`:

```python
"""DelegationStoreMixin — delegation_runs table operations."""
from typing import Any, Dict, List, Optional

class DelegationStoreMixin:
    """Mixin for delegation_runs table. Accesses self.db (set by RelationalStore)."""

    def insert_delegation(
        self,
        *,
        chain_id: str,
        from_model: Optional[str],
        to_model: str,
        role: str,
        batch: int = 0,
        retry: int = 0,
        task: Optional[str] = None,
        response: Optional[str] = None,
        md_file_path: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> int:
        """Insert delegation record. Returns row id."""
        # Compute response_length from response
        response_length = len(response) if response else 0
        cursor = self.db.cursor()
        cursor.execute(
            "INSERT INTO delegation_runs "
            "(chain_id, from_model, to_model, role, batch, retry, task, response, response_length, md_file_path, run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chain_id, from_model, to_model, role, batch, retry, task, response, response_length, md_file_path, run_id),
        )
        self.db.commit()
        return cursor.lastrowid

    def query_delegations(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        from_model: Optional[str] = None,
        to_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query delegations with pagination and filters. Returns {delegations, total, page, per_page}."""
        # Build WHERE clause dynamically
        # Default ORDER BY created_at DESC
        # Return dict with 'delegations' list and pagination metadata

    def get_delegation(self, chain_id: str) -> Optional[Dict[str, Any]]:
        """Get single delegation by chain_id. Returns dict or None."""
        # SELECT * FROM delegation_runs WHERE chain_id = ?
        # Return dict or None
```

### Step 4: Wire mixin into RelationalStore

In `memory_service/store/relational_store.py`:
1. Add import: `from .delegation import DelegationStoreMixin`
2. Add `DelegationStoreMixin` to the class inheritance list (after FtsStoreMixin)

### Step 5: Fix transition_to bug in council_main.py

In `council_main.py`, the delegation code block (~lines 4860-5270):

**Current (broken):**
```python
# Line 4867: ps created inside nested try
ps = self._get_or_create_pipeline(None, deleg_task, project_id)
# ... many lines later at line 5234 ...
self.transition_to("DELEGATION", outcome="success", artifact_path=resp_content)
self.transition_to("DONE", outcome="success")
```

**Fix:**
1. Hoist `ps` variable so it's accessible in the delegation save block (or restructure the try/except so `ps` stays in scope)
2. Replace `self.transition_to(...)` with `ps.transition_to(...)`
3. After `save_delegation_response()`, call `self.relational_store.insert_delegation(...)` with:
   - `chain_id=chain_id`
   - `from_model=original_alias or "unknown"`
   - `to_model=target_alias`
   - `role=role`
   - `batch=batch_num`
   - `retry=retry_num`
   - `task=task`
   - `response=resp_content`
   - `md_file_path=saved_deleg_path`
   - `run_id=pipeline_id`

### Step 6: Run tests (GREEN phase)

Run: `cd /home/chief/Coding-Projects/7-council && python -m pytest super_council/tests/test_delegation_runs.py -v`
**Expected: ALL tests PASS**

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `memory_service/store/delegation.py` | DelegationStoreMixin with insert/query/get methods |
| Create | `migrations_council_core/08_delegation_runs.sql` | Schema migration |
| Create | `tests/test_delegation_runs.py` | Unit tests for delegation methods |
| Modify | `memory_service/store/relational_store.py` | Import DelegationStoreMixin, add to inheritance |
| Modify | `council_main.py` (lines 4860-5270) | Fix `self.transition_to()` → `ps.transition_to()`, wire `insert_delegation()` |

## Phase-Specific Tests

1. `test_insert_delegation_creates_row` — insert one delegation, SELECT count = 1
2. `test_insert_delegation_stores_all_fields` — verify from_model, to_model, role, chain_id, etc.
3. `test_insert_delegation_duplicate_chain_id_raises` — UNIQUE constraint on chain_id
4. `test_query_delegations_returns_paginated_results` — insert 5, page 1 per_page=2 → returns 2
5. `test_query_delegations_search_by_task` — filter by LIKE %search%
6. `test_query_delegations_filter_by_to_model` — exact match on to_model
7. `test_get_delegation_returns_single` — retrieve by chain_id
8. `test_get_delegation_returns_none_for_missing` — nonexistent chain_id → None
9. `test_delegation_table_schema` — PRAGMA table_info shows all columns

## Completion Gate

- [ ] All 9 tests pass
- [ ] Migration SQL creates table with correct schema
- [ ] DelegationStoreMixin composed into RelationalStore
- [ ] `council_main.py` uses `ps.transition_to()` not `self.transition_to()`
- [ ] `insert_delegation()` called after successful delegation save
- [ ] No regression in existing tests (`pytest super_council/tests/ -v`)

## Notes for Next Phase

- Unit 1 (API) expects `query_delegations()` returns `{delegations: [...], total: N, page: P, per_page: PP}`
- Unit 2 (backfill) expects `insert_delegation()` with all parameters
- `from_model` can be NULL for historical delegations (not enforced at DB level)
