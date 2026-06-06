# Phase 5: Production Wiring

**Parent plan:** `06-06-2026_task-ledger-deviation-tracking_3fce71.md`
**Phase:** 5 of 5
**Dependencies:** Phases 1-4 (all must be complete)
**Estimated effort:** ~30 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/memory_service/__main__.py` (modify — start reconciliation thread)
- `super_council/arc_summarizer/scheduler.py` (modify — schedule reconciliation after consolidation)
- `super_council/memory_service/test_reconciliation.py` (create — integration tests)

---

## What This Phase Delivers

All components wired into the running system. Full consolidation → extraction → reconciliation → storage flow verified end-to-end. Memory service starts reconciliation thread. Scheduler triggers task and deviation reconciliation after consolidation runs.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (schema migration)
- [ ] Phase 2 is marked complete (reconciliation engine)
- [ ] Phase 3 is marked complete (ARC wiring for task extraction)
- [ ] Phase 4 is marked complete (deviation detection)
- [ ] All phase-specific tests pass

---

## Implementation Steps

### Step 1: Start Reconciliation Thread in Memory Service

Modify `super_council/memory_service/__main__.py`:

```python
# Add reconciliation thread startup
from .reconciliation import TaskReconciler

def start_reconciliation_thread(store, arc_pipeline):
    """Start background reconciliation thread."""
    import threading
    import time

    def reconciliation_loop():
        while True:
            try:
                # Check for pending reconciliations
                # This is triggered by ARC consolidation runs, not polled
                time.sleep(60)  # Check every minute
            except Exception as e:
                log.warning("Reconciliation thread error: %s", e)

    thread = threading.Thread(target=reconciliation_loop, daemon=True)
    thread.start()
    log.info("Reconciliation thread started")
```

### Step 2: Schedule Reconciliation After Consolidation

Modify `super_council/arc_summarizer/scheduler.py`:

```python
# After each tiered consolidation, trigger task reconciliation
def run_consolidation_with_reconciliation(tier_id, pipeline, store):
    """Run consolidation and trigger task/deviation reconciliation."""
    result = pipeline.run_tiered_consolidation(tier_id)
    if result:
        # Task reconciliation is already wired in pipeline.py (Phase 3)
        # Deviation reconciliation is already wired for weekly/bimonthly (Phase 4)
        log.info("Consolidation + reconciliation completed for tier %s", tier_id)
    return result
```

### Step 3: Create Integration Tests

Create `super_council/memory_service/test_reconciliation.py`:

```python
"""Integration tests for task reconciliation pipeline."""
import pytest
import sqlite3
import tempfile
import os

from super_council.memory_service.store import RelationalStore
from super_council.memory_service.reconciliation import TaskReconciler


@pytest.fixture
def test_db():
    """Create in-memory test database with schema."""
    conn = sqlite3.connect(':memory:')
    # Apply migration schema
    with open('migrations/001_task_ledger_schema.sql') as f:
        conn.executescript(f.read())
    return conn


@pytest.fixture
def store(test_db):
    """Create RelationalStore with test database."""
    return RelationalStore(test_db)


@pytest.fixture
def reconciler():
    """Create TaskReconciler."""
    return TaskReconciler()


class TestTitleNormalization:
    def test_lowercase_and_strip(self, reconciler):
        assert reconciler.normalize_title("Fix: Add User Auth") == "add user auth"

    def test_consistent_keys(self, reconciler):
        assert reconciler.normalize_title("fix-add-user-auth") == reconciler.normalize_title("Fix: Add User Auth")

    def test_removes_prefixes(self, reconciler):
        assert reconciler.normalize_title("feat: new feature") == "new feature"
        assert reconciler.normalize_title("chore: cleanup") == "cleanup"


class TestDedupKey:
    def test_exact_match(self, reconciler):
        key1 = reconciler.compute_dedup_key("Add user auth", "project-1")
        key2 = reconciler.compute_dedup_key("Add user auth", "project-1")
        assert key1 == key2

    def test_different_projects(self, reconciler):
        key1 = reconciler.compute_dedup_key("Add user auth", "project-1")
        key2 = reconciler.compute_dedup_key("Add user auth", "project-2")
        assert key1 != key2

    def test_subsystem_differentiation(self, reconciler):
        key1 = reconciler.compute_dedup_key("Add logging", "project-1", "auth")
        key2 = reconciler.compute_dedup_key("Add logging", "project-1", "api")
        assert key1 != key2


class TestSimilarityScoring:
    def test_exact_match(self, reconciler):
        assert reconciler.title_similarity("Add user auth", "Add user auth") == 1.0

    def test_partial_match(self, reconciler):
        sim = reconciler.title_similarity("Add user auth", "Implement user authentication")
        assert sim > 0.5

    def test_no_match(self, reconciler):
        sim = reconciler.title_similarity("Add user auth", "Fix database migration")
        assert sim < 0.3


class TestEvidenceClassification:
    def test_completion_keywords(self, reconciler):
        assert reconciler.classify_from_evidence("fixed the bug") == 'done'
        assert reconciler.classify_from_evidence("tests passing") == 'done'
        assert reconciler.classify_from_evidence("merged PR") == 'done'

    def test_blocking_keywords(self, reconciler):
        assert reconciler.classify_from_evidence("blocked by API") == 'blocked'
        assert reconciler.classify_from_evidence("waiting on review") == 'blocked'

    def test_open_keywords(self, reconciler):
        assert reconciler.classify_from_evidence("should add logging") == 'open'
        assert reconciler.classify_from_evidence("need to fix later") == 'open'


class TestCandidateClassification:
    def test_new_task(self, reconciler):
        candidate = {'title': 'New feature', 'project_id': 'proj-1', 'evidence': 'should add X'}
        result = reconciler.classify_candidate(candidate, [])
        assert result['action'] == 'create'

    def test_duplicate_ignored(self, reconciler, store):
        # Create existing item
        store.get_or_create_work_item(project_id='proj-1', kind='task', title='Add user auth')
        existing = store.get_work_items(project_id='proj-1')
        candidate = {'title': 'Add user auth', 'project_id': 'proj-1', 'evidence': 'mentioned again'}
        result = reconciler.classify_candidate(candidate, existing)
        assert result['action'] == 'ignore_duplicate'

    def test_completion_detected(self, reconciler, store):
        store.get_or_create_work_item(project_id='proj-1', kind='task', title='Fix bug X')
        existing = store.get_work_items(project_id='proj-1')
        candidate = {'title': 'Fix bug X', 'project_id': 'proj-1', 'evidence': 'fixed and verified'}
        result = reconciler.classify_candidate(candidate, existing)
        assert result['action'] == 'mark_done'


class TestFullReconciliation:
    def test_no_duplicates_across_sessions(self, reconciler, store):
        """Same task mentioned 5 times → 1 work item created, 4 ignored."""
        project_id = 'test-proj'
        for i in range(5):
            arc_delta = {
                'new_tasks': [{'title': 'Add user auth', 'priority': 'high', 'evidence': f'session {i}'}],
            }
            results = reconciler.reconcile(arc_delta, project_id, store)
            assert len(results) == 1
            if i == 0:
                assert results[0]['action'] == 'create'
            else:
                assert results[0]['action'] == 'ignore_duplicate'

        # Verify only 1 work item exists
        items = store.get_work_items(project_id=project_id)
        assert len(items) == 1


class TestEndToEndFlow:
    def test_session_to_storage(self, store):
        """Full flow: ARC delta → reconciliation → work_items → provenance."""
        project_id = 'e2e-test'
        arc_delta = {
            'new_tasks': [
                {'title': 'Implement feature X', 'priority': 'high', 'evidence': 'need to build X'},
            ],
            'completed_tasks': [
                {'title': 'Fix bug Y', 'evidence': 'fixed and verified'},
            ],
        }

        # Reconcile
        results = store.reconcile_arc_delta(arc_delta, project_id, run_id='test-run-1', source_summary_id='test-summary-1')

        # Verify new task created
        items = store.get_work_items(project_id=project_id)
        assert len(items) >= 1

        # Verify provenance linkage
        for item in items:
            if item['title'] == 'Implement feature X':
                events = store.get_work_item_events(item['id'])
                assert any(e['event_type'] == 'created' for e in events)
```

### Step 4: Run Integration Tests

```bash
cd /home/chief/Coding-Projects/7-council
python -m pytest super_council/memory_service/test_reconciliation.py -v
```

### Step 5: Verify Health Check

Ensure memory service health check includes reconciliation status:

```python
# In health.py or __main__.py
def check_reconciliation_status():
    """Check if reconciliation thread is running and healthy."""
    return {
        'reconciliation_thread': 'running',  # or 'stopped'
        'last_reconciliation': last_reconciliation_time,  # or 'never'
        'pending_reconciliations': pending_count,
    }
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/__main__.py` | Start reconciliation thread |
| Modify | `super_council/arc_summarizer/scheduler.py` | Schedule reconciliation after consolidation |
| Create | `super_council/memory_service/test_reconciliation.py` | Integration tests |

---

## Post-Wiring Tests (GATE — must pass before marking complete)

- [ ] Memory service starts and responds to health checks
- [ ] ARC consolidation runs and produces task deltas
- [ ] Reconciliation engine processes deltas without errors
- [ ] Work items are created/updated in `work_items` table
- [ ] Deviation records are created in `plan_deviations` table
- [ ] Provenance linkage (run_id, source_summary_id) is correct
- [ ] Duplicate tasks are not created across multiple consolidations
- [ ] All integration tests pass (`pytest super_council/memory_service/test_reconciliation.py -v`)
- [ ] All existing tests still pass (no regression)
- [ ] Health check includes reconciliation status
- [ ] **Bimonthly experiment gate verified:** First post-deployment bimonthly run produces non-empty, non-thin output. If output is thin (<3 meaningful entries) or empty, drop bimonthly tier and promote `weekly` to top tier. This is a hard decision, not a revisit trigger.

---

## Completion Gate

- [ ] Reconciliation thread starts with memory service
- [ ] Task reconciliation triggers after each consolidation run
- [ ] Deviation detection triggers after weekly/bimonthly consolidation
- [ ] Full end-to-end flow verified (session → ARC → reconciliation → storage)
- [ ] All post-wiring tests pass
- [ ] No regression in existing tests
- [ ] Health check reports reconciliation status

---

## Notes for Completion

This is the final phase. After all post-wiring tests pass, the full system is operational:

1. **Session summaries** are produced by ARC consolidation
2. **Task signals** are extracted from consolidation output
3. **Reconciliation** deduplicates against existing work_items
4. **Work items** are created/updated with provenance linkage
5. **Deviations** are detected and tracked for plan-vs-reality context
6. **Health check** reports reconciliation status

The system is now resilient against data loss — all task context, deviation context, and provenance linkage is stored in canonical tables with event audit trails.
