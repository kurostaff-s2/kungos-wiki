# Phase 1: Scaffold Directory Structure + Split store.py

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 1 of 9
**Dependencies:** None (foundational phase)
**Estimated effort:** ~60 min (3357-line file split into 8 modules)

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `memory_service/store.py` (3357 lines) → 8 new files under `memory_service/store/`
**Related codebases:** None

## What This Phase Delivers

Creates the new directory structure and splits `store.py` (3357 lines) into 8 domain-cohesive modules. This is the foundation — all other phases depend on the store modules being in place.

The split follows domain boundaries, not method counts:

| New Module | Lines (approx) | Responsibility | Methods moved from store.py |
|-----------|----------------|----------------|----------------------------|
| `relational_store.py` | ~600 | Core: pipeline transitions, events, artifacts, DB connection | `_create_tables`, `_seed_definitions`, `_seed_enum_tables`, `_sync_phase_registry`, `_record_transition`, `checkpoint`, `close`, `create_audit_table`, `log_audit_event`, `count_bypasses_last_24h`, `upsert_pipeline`, `find_active_pipeline`, `query_pipelines`, `get_pipeline`, `register_translation`, `lookup_translation`, `archive_terminal_pipelines`, `_archive_old_runs`, `log_event`, `store_artifact`, `update_workflow_run_status`, `ensure_workflow_run`, `store_artifact_summary`, `store_event_window_summary`, `store_failure_classification`, `get_workflow_definitions`, `get_phase_info` |
| `session_store.py` | ~500 | Session diary, raw session memory | `upsert_session_diary`, `_extract_section`, `query_session_diary`, `_parse_raw_session_text`, `_extract_clean_conversation`, `_annotate_prose`, `_clean_user_message`, `_write_raw_session_md`, `upsert_raw_session_memory`, `query_raw_session_memories` |
| `consolidation_store.py` | ~200 | Consolidation cache, tier tracking | `upsert_consolidation_cache`, `query_consolidation_cache`, `activate_consolidation_cache`, `query_consolidation_tiers`, `update_tier_last_run`, `update_tier_reconciled_at` |
| `work_items.py` | ~400 | Work item CRUD, carry-forward | `create_work_item`, `get_or_create_work_item`, `update_work_item_status`, `get_work_item`, `get_work_items`, `get_work_item_events`, `create_carry_forward`, `reassert_carry_forward`, `expire_carry_forward`, `decrement_carry_forward_cycles`, `get_carry_forward`, `get_carry_forward_items` |
| `deviations.py` | ~300 | Deviation CRUD, linking | `create_deviation`, `update_deviation_status`, `get_deviation`, `get_deviations`, `link_deviation_to_work_item` |
| `projects.py` | ~600 | Project resolution, validation | `resolve_project`, `get_or_create_project`, `list_projects`, `resolve_project_from_context`, `_verify_claim`, `backfill_project_id`, `backfill_source_run_id`, `_validate_project` |
| `blacklist.py` | ~200 | Injection blacklist | `upsert_injection_blacklist`, `query_injection_blacklist`, `unblacklist_pattern`, `is_blacklisted` |
| `fts.py` | ~150 | FTS5 triggers, sync | `_ensure_fts_triggers` |
| `reconcile_bridge.py` | ~150 | Reconciliation DB operations | `reconcile_open_items` |

Plus `__init__.py` that re-exports `RelationalStore` as the unified class (composed from all sub-modules via mixin or delegation).

## Pre-Flight Checklist

- [ ] `memory_service/store.py` exists and is 3357 lines
- [ ] No uncommitted changes in `memory_service/`
- [ ] `python -c "from super_council.memory_service import MemoryService"` works

## Implementation Steps

### Step 1: Create directory structure

Create all target directories:

```bash
mkdir -p memory_service/store
mkdir -p memory_service/ingest
mkdir -p memory_service/consolidate
mkdir -p memory_service/index
mkdir -p memory_service/reconcile
mkdir -p memory_service/recall/channels
mkdir -p memory_service/enrich
mkdir -p memory_service/review
mkdir -p memory_service/health
mkdir -p memory_service/analytics
```

Create empty `__init__.py` in each:

```bash
for dir in store ingest consolidate index reconcile recall recall/channels enrich review health analytics; do
    touch "memory_service/$dir/__init__.py"
done
```

### Step 2: Build `store/relational_store.py`

This is the core module. It contains the `RelationalStore` class with:
- `__init__()` — DB connection, WAL mode, FK enforcement, table creation, seeding
- All pipeline transition methods
- All event/artifact storage methods
- All workflow definition methods

**Key:** The `RelationalStore` class must compose (not inherit from) the sub-modules. Use a delegation pattern:

```python
# store/relational_store.py
class RelationalStore:
    def __init__(self, db_path, cg_db_path=None, memory_layer=None):
        self._db_path = db_path
        self._cg_db_path = cg_db_path
        self.memory_layer = memory_layer
        # DB connection setup (from original __init__)
        self.db = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        # ... PRAGMA settings ...
        self._create_tables()
        self._seed_definitions()
        self._seed_enum_tables()
        self._sync_phase_registry()
        self.create_audit_table()
        self._ensure_fts_triggers()
        # Compose sub-modules
        self._pipeline = _PipelineStore(self.db)
        self._events = _EventStore(self.db)
        self._artifacts = _ArtifactStore(self.db)
        self._sessions = SessionStore(self.db)
        self._consolidation = ConsolidationStore(self.db)
        self._work_items = WorkItemStore(self.db)
        self._deviations = DeviationStore(self.db)
        self._projects = ProjectStore(self.db)
        self._blacklist = BlacklistStore(self.db)
        # ... codegraph connection ...

    # Delegate public API
    def upsert_pipeline(self, ...):
        return self._pipeline.upsert_pipeline(...)
```

**Alternative (simpler):** Keep `RelationalStore` as a single class in `relational_store.py` that uses `from .session_store import *` etc. to import helper functions. This avoids the composition overhead while still splitting the file.

**Recommendation:** Use the simpler approach — keep `RelationalStore` as one class, but split methods into separate files that the class imports. Each sub-module exports functions or inner classes that `RelationalStore` mixes in:

```python
# store/relational_store.py
from .session_store import SessionStoreMixin
from .consolidation_store import ConsolidationStoreMixin
from .work_items import WorkItemStoreMixin
from .deviations import DeviationStoreMixin
from .projects import ProjectStoreMixin
from .blacklist import BlacklistStoreMixin
from .fts import FtsStoreMixin

class RelationalStore(SessionStoreMixin, ConsolidationStoreMixin, WorkItemStoreMixin,
                       DeviationStoreMixin, ProjectStoreMixin, BlacklistStoreMixin, FtsStoreMixin):
    """Unified SQLite store. Core pipeline + event + artifact methods."""
    def __init__(self, db_path, cg_db_path=None, memory_layer=None):
        # ... setup ...
        # Each mixin's __init__ is not called — they use self.db directly
```

Each mixin accesses `self.db` (set by `RelationalStore.__init__`). This is the cleanest approach — no delegation overhead, clean file split, single class interface.

### Step 3: Extract `store/session_store.py`

Move all session-related methods from `store.py` into a `SessionStoreMixin` class:

```python
# store/session_store.py
class SessionStoreMixin:
    """Session diary and raw session memory storage. Mixin for RelationalStore."""

    def upsert_session_diary(self, summary_text, source_path, alias="unknown"):
        # ... moved verbatim from store.py ...

    def _extract_section(self, text, header):
        # ... moved verbatim ...

    def query_session_diary(self, ...):
        # ... moved verbatim ...

    def _parse_raw_session_text(self, raw_text):
        # ... moved verbatim ...

    def _extract_clean_conversation(self, raw_text):
        # ... moved verbatim ...

    def _annotate_prose(self, ...):
        # ... moved verbatim ...

    def _clean_user_message(self, text):
        # ... moved verbatim ...

    def _write_raw_session_md(self, ...):
        # ... moved verbatim ...

    def upsert_raw_session_memory(self, ...):
        # ... moved verbatim ...

    def query_raw_session_memories(self, ...):
        # ... moved verbatim ...
```

**Note:** `_parse_raw_session_text` calls `_extract_clean_conversation` and `_annotate_prose`. All three must be in the same mixin (they are).

### Step 4: Extract `store/consolidation_store.py`

```python
# store/consolidation_store.py
class ConsolidationStoreMixin:
    """Consolidation cache and tier tracking. Mixin for RelationalStore."""

    def upsert_consolidation_cache(self, ...):
    def query_consolidation_cache(self, ...):
    def activate_consolidation_cache(self, ...):
    def query_consolidation_tiers(self, ...):
    def update_tier_last_run(self, ...):
    def update_tier_reconciled_at(self, ...):
```

### Step 5: Extract `store/work_items.py`

```python
# store/work_items.py
from ..errors import CarryForwardCapError

class WorkItemStoreMixin:
    """Work item CRUD and carry-forward. Mixin for RelationalStore."""

    def create_work_item(self, ...):
    def get_or_create_work_item(self, ...):
    def update_work_item_status(self, ...):
    def get_work_item(self, ...):
    def get_work_items(self, ...):
    def get_work_item_events(self, ...):
    def create_carry_forward(self, ...):
    def reassert_carry_forward(self, ...):
    def expire_carry_forward(self, ...):
    def decrement_carry_forward_cycles(self, ...):
    def get_carry_forward(self, ...):
    def get_carry_forward_items(self, ...):
```

### Step 6: Extract `store/deviations.py`

```python
# store/deviations.py
class DeviationStoreMixin:
    """Deviation CRUD and linking. Mixin for RelationalStore."""

    def create_deviation(self, ...):
    def update_deviation_status(self, ...):
    def get_deviation(self, ...):
    def get_deviations(self, ...):
    def link_deviation_to_work_item(self, ...):
```

### Step 7: Extract `store/projects.py`

This is the largest mixin (~600 lines). Contains project resolution, validation, backfill:

```python
# store/projects.py
from ..errors import ProjectResolutionError

class ProjectStoreMixin:
    """Project resolution, validation, backfill. Mixin for RelationalStore."""

    def resolve_project(self, slug, name=None):
    def get_or_create_project(self, slug, name=None):
    def list_projects(self, status="active"):
    def resolve_project_from_context(self, ...):
    def _verify_claim(self, ...):
    def backfill_project_id(self, default_slug="council"):
    def backfill_source_run_id(self):
    def _validate_project(self, project_id):
```

### Step 8: Extract `store/blacklist.py`

```python
# store/blacklist.py
class BlacklistStoreMixin:
    """Injection blacklist. Mixin for RelationalStore."""

    def upsert_injection_blacklist(self, ...):
    def query_injection_blacklist(self, ...):
    def unblacklist_pattern(self, ...):
    def is_blacklisted(self, ...):
```

### Step 9: Extract `store/fts.py`

```python
# store/fts.py
class FtsStoreMixin:
    """FTS5 trigger management. Mixin for RelationalStore."""

    def _ensure_fts_triggers(self):
        # ... moved verbatim ...
```

### Step 10: Extract `store/reconcile_bridge.py`

```python
# store/reconcile_bridge.py
class ReconcileBridgeMixin:
    """Reconciliation DB operations. Mixin for RelationalStore."""

    def reconcile_open_items(self, ...):
        # ... moved verbatim ...
```

### Step 11: Wire `store/__init__.py`

```python
# store/__init__.py
"""Stage 5: Reconciliation → VectorStore → DB.

Exports RelationalStore composed from domain mixins.
"""
from .relational_store import RelationalStore
from .vector_store import SQLiteVectorStore

__all__ = ["RelationalStore", "SQLiteVectorStore"]
```

### Step 12: Move `vector_store.py` → `store/vector_store.py`

Move verbatim. Remove `UnifiedVectorStore` subclass. Export `SQLiteVectorStore` as the single class. Update any internal references.

### Step 13: Update `memory_service/__init__.py` imports

The `MemoryService._init_components()` method imports from `.store`. Update:

```python
# OLD:
from .store import RelationalStore

# NEW:
from .store import RelationalStore  # still works via store/__init__.py
```

This should work without changes because `store/__init__.py` re-exports `RelationalStore`.

### Step 14: Verify shim files

These files in `super_council/` root re-export from `memory_service/`:
- `relational_store.py` → `from super_council.memory_service.store import RelationalStore`
- `memory_layer.py` → `from super_council.memory_service.layer import MemoryLayer`
- `context_router.py` → `from super_council.memory_service.router import ContextRouter`
- `review_service.py` → `from super_council.memory_service.review import ReviewService`

Verify they still work after the split.

### Step 15: Phase Gate

Run the verification command:

```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.health_check())"
```

Must return `{"healthy": true, ...}` with no import errors.

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `memory_service/store/__init__.py` | Re-export RelationalStore, SQLiteVectorStore |
| Create | `memory_service/store/relational_store.py` | Core RelationalStore class + pipeline/event/artifact methods |
| Create | `memory_service/store/session_store.py` | SessionStoreMixin (diary, raw session) |
| Create | `memory_service/store/consolidation_store.py` | ConsolidationStoreMixin (cache, tiers) |
| Create | `memory_service/store/work_items.py` | WorkItemStoreMixin (CRUD, carry-forward) |
| Create | `memory_service/store/deviations.py` | DeviationStoreMixin (CRUD, linking) |
| Create | `memory_service/store/projects.py` | ProjectStoreMixin (resolution, validation) |
| Create | `memory_service/store/blacklist.py` | BlacklistStoreMixin (injection blacklist) |
| Create | `memory_service/store/fts.py` | FtsStoreMixin (FTS5 triggers) |
| Create | `memory_service/store/reconcile_bridge.py` | ReconcileBridgeMixin (reconciliation DB ops) |
| Move | `memory_service/vector_store.py` → `memory_service/store/vector_store.py` | Vector store into store/ package |
| Create | `memory_service/ingest/__init__.py` | Empty (Phase 2 populates) |
| Create | `memory_service/consolidate/__init__.py` | Empty (Phase 3 populates) |
| Create | `memory_service/index/__init__.py` | Empty (Phase 4 populates) |
| Create | `memory_service/reconcile/__init__.py` | Empty (Phase 5 populates) |
| Create | `memory_service/recall/__init__.py` | Empty (Phase 6 populates) |
| Create | `memory_service/recall/channels/__init__.py` | Empty (Phase 6 populates) |
| Create | `memory_service/enrich/__init__.py` | Empty (Phase 7 populates) |
| Create | `memory_service/review/__init__.py` | Empty (Phase 7 populates) |
| Create | `memory_service/health/__init__.py` | Empty (Phase 7 populates) |
| Create | `memory_service/analytics/__init__.py` | Empty (Phase 7 populates) |
| Modify | `memory_service/__init__.py` | Update imports if needed |
| Delete | `memory_service/store.py` | Replaced by store/ package |
| Delete | `memory_service/vector_store.py` | Moved to store/vector_store.py |

## Phase-Specific Tests

1. **Import test:** `python -c "from super_council.memory_service.store import RelationalStore; print('OK')"` — must succeed
2. **Composition test:** `python -c "from super_council.memory_service.store import RelationalStore; rs = RelationalStore(':memory:'); rs.upsert_pipeline(task='test', project_id='test', phase='RED'); print('OK')"` — must succeed (in-memory DB)
3. **Mixin test:** Verify each mixin method is accessible on `RelationalStore` instance: `hasattr(rs, 'upsert_session_diary')`, `hasattr(rs, 'resolve_project')`, etc.

## Completion Gate

- [ ] All 8 mixin files created under `store/`
- [ ] `store.py` deleted (replaced by `store/` package)
- [ ] `vector_store.py` moved to `store/vector_store.py`
- [ ] All 10 sub-directories created with `__init__.py`
- [ ] `python -c "from super_council.memory_service import MemoryService"` succeeds
- [ ] `python -m memory_service --health` reports healthy
- [ ] All mixin methods accessible on `RelationalStore` instance
- [ ] Shim files (`relational_store.py`, etc.) still work

## Notes for Next Phase

- Phase 2 (ingest/) needs `session_store.py` to exist for project resolution and carry-forward wiring
- Phase 3 (consolidate/) needs `consolidation_store.py` for cache/tier operations
- The `RelationalStore` mixin pattern establishes the pattern for all subsequent splits
