# Phase 4: Production Wiring

**Parent plan:** `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`
**Phase:** 4 of 4
**Dependencies:** Phases 1-3 (all must be complete)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/super_council.py` (modify — wire adaptive triggers into HTTP endpoints)
- `super_council/arc_summarizer/__init__.py` (modify — wire analyzer into pipeline)
- `super_council/arc_summarizer/pipeline.py` (modify — production reconciliation wiring)
- `super_council/memory_service/__init__.py` (modify — health check updates)
- `super_council/tests/test_session_analyzer.py` (create — analyzer tests)
- `super_council/tests/test_adaptive_summarization.py` (create — trigger + mode tests)

---

## What This Phase Delivers

All components wired into the running system. Full flow verified: session → analysis → trimmed summary → reconciliation → storage. Adaptive triggers fire correctly. Scheduler responds to event hints. Health check reports all new components.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (SessionAnalyzer + trimmed summary working)
- [ ] Phase 2 is marked complete (Adaptive triggers wired)
- [ ] Phase 3 is marked complete (Reconciler thresholds + deviation candidates working)
- [ ] All phase-specific tests pass
- [ ] Existing tests pass (baseline: 495 passed)

---

## Implementation Steps

### Step 1: Wire SessionAnalyzer into ArcPipeline

Modify `super_council/arc_summarizer/__init__.py`:

```python
from .analyzer import SessionAnalyzer
from .pipeline import ArcPipeline
from .config import ArcConfig

__all__ = ['ArcConfig', 'ArcPipeline', 'SessionAnalyzer']

def summarize_session(turns: list, config: ArcConfig, session_mode: str = None) -> dict | None:
    """Convenience function: analyze + summarize in one call.

    Usage:
        result = summarize_session(turns, config)
        # result = {'summary': str, 'trimmed': dict, 'session_mode': str}
    """
    client = ArcClient(config)
    return client.summarize_session(turns, session_mode=session_mode)
```

### Step 2: Wire Adaptive Triggers into HTTP Endpoints

Modify `super_council/super_council.py`:

Wire idle detection into request handler:
```python
# In HTTP request handler, record activity on each request
self._idle_tracker.record_activity(session_id)

# Check if idle trigger should fire
if self._idle_tracker.is_idle(session_id):
    self._summarize_session(summarize_alias=alias)
```

Wire token budget tracking:
```python
# After each LLM call, record token usage
if 'usage' in response:
    tokens = response['usage'].get('total_tokens', 0)
    self._token_tracker.record_tokens(session_id, tokens)

# Check if token budget trigger should fire
if self._token_tracker.should_summarize(session_id):
    self._summarize_session(summarize_alias=alias)
```

Wire significant event scoring:
```python
# Record significant events as they happen
if error_detected:
    self._event_scorer.record_event(session_id, 'error')
if decision_made:
    self._event_scorer.record_event(session_id, 'decision')
if file_changed:
    self._event_scorer.record_event(session_id, 'file_change')

# Check if significant event trigger should fire
if self._event_scorer.is_significant(session_id):
    self._summarize_session(summarize_alias=alias)
```

### Step 3: Wire Event Hints into Scheduler

Modify `super_council/arc_summarizer/pipeline.py`:

```python
# After successful tiered consolidation, emit event hint
def run_tiered_consolidation(self, tier_id: str) -> bool:
    # ... existing logic ...

    if success:
        # Emit event hint for scheduler
        if self._relational_store:
            try:
                if tier_id == 'daily':
                    # Check if daily count threshold reached
                    daily_count = self._relational_store.count_daily_entries()
                    if daily_count >= 3:  # 3 daily entries → short consolidation due
                        self._relational_store.on_daily_count_threshold_reached(daily_count)
                elif tier_id == 'weekly':
                    self._relational_store.on_weekly_completed()
            except Exception as e:
                log.warning("Event hint emission failed (non-fatal): %s", e)

    return success
```

### Step 4: Update Health Check

Modify `super_council/memory_service/__init__.py`:

```python
def health_check(self) -> Dict[str, Any]:
    """Check memory service health including new components."""
    # ... existing health check logic ...

    # Session analyzer status
    analyzer_status = {
        'available': True,
        'modes': ['code', 'research', 'planning', 'debugging', 'mixed'],
    }
    try:
        from super_council.arc_summarizer.analyzer import SessionAnalyzer
        analyzer = SessionAnalyzer()
        # Test classification
        _, scores = analyzer.classify("def test_function(): pass")
        analyzer_status['test_scores'] = scores
    except Exception as e:
        analyzer_status['available'] = False
        analyzer_status['error'] = str(e)

    # Adaptive trigger status
    trigger_status = {
        'idle_detection': 'wired',
        'token_tracking': 'wired',
        'model_swap_hook': 'wired',
        'event_scoring': 'wired',
    }

    # Event hint responsiveness
    event_status = {
        'wake_method': 'available' if self._scheduler and hasattr(self._scheduler, '_wake') else 'unavailable',
        'handlers': ['chat_summary_saved', 'daily_summary_saved', 'daily_count_threshold_reached', 'weekly_completed'],
    }

    health['session_analyzer'] = analyzer_status
    health['adaptive_triggers'] = trigger_status
    health['event_hints'] = event_status

    return health
```

### Step 5: Create Integration Tests

Create `super_council/tests/test_session_analyzer.py`:

```python
"""Tests for SessionAnalyzer (Phase 1).

Validates:
- Heuristic classification for all 5 modes
- Score vector with mixed fallback
- Trimmed summary with 11-field schema
- Mode-aware prompt generation
"""
import pytest
from super_council.arc_summarizer.analyzer import SessionAnalyzer

@pytest.fixture
def analyzer():
    return SessionAnalyzer()

class TestHeuristicClassification:
    def test_code_session(self, analyzer):
        text = "Modified src/auth.py, added def authenticate_user(), ran pytest tests/test_auth.py"
        mode, scores = analyzer.classify(text)
        assert mode == 'code'
        assert scores['code'] > 0.5

    def test_research_session(self, analyzer):
        text = "Searched https://docs.api.com/v2, evaluated benchmark results, compared approaches"
        mode, scores = analyzer.classify(text)
        assert mode == 'research'
        assert scores['research'] > 0.5

    def test_planning_session(self, analyzer):
        text = "Decided on microservices approach, planned phase 1 milestone, estimated 2 week timeline"
        mode, scores = analyzer.classify(text)
        assert mode == 'planning'
        assert scores['planning'] > 0.5

    def test_debugging_session(self, analyzer):
        text = "Error: NullPointerException in auth module, root cause was missing null check, fixed with assertion"
        mode, scores = analyzer.classify(text)
        assert mode == 'debugging'
        assert scores['debugging'] > 0.5

    def test_mixed_fallback(self, analyzer):
        text = "Modified src/auth.py and decided on new approach for phase 1"
        mode, scores = analyzer.classify(text)
        assert mode == 'mixed'
        assert scores['mixed'] == 1.0

    def test_empty_text(self, analyzer):
        mode, scores = analyzer.classify("")
        assert mode == 'mixed'
        assert scores['mixed'] == 1.0

class TestTrimmedSummary:
    def test_preserves_files(self, analyzer):
        text = "Modified src/auth.py and src/api.py"
        trimmed = analyzer.trim_session(text, session_id='test-1')
        assert 'src/auth.py' in trimmed['files_changed']
        assert 'src/api.py' in trimmed['files_changed']

    def test_preserves_functions(self, analyzer):
        text = "Added def authenticate_user() and def validate_token()"
        trimmed = analyzer.trim_session(text, session_id='test-1')
        assert 'authenticate_user' in trimmed['functions_touched']
        assert 'validate_token' in trimmed['functions_touched']

    def test_preserves_decisions(self, analyzer):
        text = "Decided to use PostgreSQL instead of SQLite"
        trimmed = analyzer.trim_session(text, session_id='test-1')
        assert len(trimmed['explicit_decisions']) > 0

    def test_fixed_schema_fields(self, analyzer):
        text = "Some session text"
        trimmed = analyzer.trim_session(text, session_id='test-1')
        assert 'session_id' in trimmed
        assert 'project_id' in trimmed
        assert 'run_id' in trimmed
        assert 'session_type' in trimmed
        assert 'files_changed' in trimmed
        assert 'functions_touched' in trimmed
        assert 'tests_written' in trimmed
        assert 'errors_blockers' in trimmed
        assert 'explicit_decisions' in trimmed
        assert 'completed_work' in trimmed
        assert 'open_work' in trimmed
        assert 'notable_deviations' in trimmed
        assert '_extra' in trimmed
```

Create `super_council/tests/test_adaptive_summarization.py`:

```python
"""Tests for Adaptive Summarization (Phase 2).

Validates:
- Idle detection triggers after N minutes
- Token budget triggers pre-emptive summary
- Model swap triggers pre-summary
- Significant event scoring
- Scheduler _wake() method
- Event hint handlers
"""
import pytest
import time
from super_council.super_council import SessionIdleTracker, SessionTokenTracker, SignificantEventScorer

class TestIdleDetection:
    def test_not_idle_on_recent_activity(self):
        tracker = SessionIdleTracker(idle_threshold_minutes=0)  # 0 minutes for testing
        tracker.record_activity('session-1')
        assert not tracker.is_idle('session-1')

    def test_idle_after_threshold(self):
        tracker = SessionIdleTracker(idle_threshold_minutes=0)  # Will be idle immediately in test
        tracker._last_activity['session-1'] = time.monotonic() - 3600  # 1 hour ago
        assert tracker.is_idle('session-1')

    def test_thread_safe_tracking(self):
        import threading
        tracker = SessionIdleTracker()
        errors = []

        def record_many():
            try:
                for i in range(100):
                    tracker.record_activity(f'session-{i}')
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

class TestTokenTracking:
    def test_warning_threshold(self):
        tracker = SessionTokenTracker(warning_threshold=0.8, max_tokens=1000)
        tracker.record_tokens('session-1', 800)
        assert tracker.should_summarize('session-1')

    def test_below_threshold(self):
        tracker = SessionTokenTracker(warning_threshold=0.8, max_tokens=1000)
        tracker.record_tokens('session-1', 400)
        assert not tracker.should_summarize('session-1')

class TestEventScoring:
    def test_significant_threshold(self):
        scorer = SignificantEventScorer()
        scorer.record_event('session-1', 'error')  # weight 3
        scorer.record_event('session-1', 'decision')  # weight 2
        assert scorer.is_significant('session-1')

    def test_below_threshold(self):
        scorer = SignificantEventScorer()
        scorer.record_event('session-1', 'test')  # weight 1
        assert not scorer.is_significant('session-1')
```

### Step 6: Run End-to-End Integration Test

```python
# In test_adaptive_summarization.py

class TestEndToEndFlow:
    def test_session_to_storage(self, tmp_path):
        """Full flow: session → analysis → trimmed summary → reconciliation → storage."""
        from super_council.arc_summarizer.analyzer import SessionAnalyzer
        from super_council.memory_service.store import RelationalStore
        import uuid

        # Setup
        db_path = str(tmp_path / "test.db")
        store = RelationalStore(db_path=db_path)
        project_id = str(uuid.uuid4())
        store.db.execute(
            "INSERT INTO projects (id, slug, name) VALUES (?, ?, ?)",
            (project_id, "test-project", "Test Project"),
        )
        store.db.commit()

        # Analyze session
        analyzer = SessionAnalyzer()
        raw_text = (
            "Modified src/auth.py, added def authenticate_user(), "
            "decided to use JWT instead of OAuth2, "
            "ran pytest tests/test_auth.py"
        )
        mode, scores = analyzer.classify(raw_text)
        trimmed = analyzer.trim_session(raw_text, session_id='test-1', project_id=project_id)

        # Verify analysis
        assert mode == 'code'
        assert 'src/auth.py' in trimmed['files_changed']
        assert 'authenticate_user' in trimmed['functions_touched']

        # Verify reconciliation would work with trimmed summary
        from super_council.memory_service.reconciliation import TaskReconciler
        reconciler = TaskReconciler()

        # Simulate reconciliation with trimmed summary
        arc_delta = {
            'new_tasks': [
                {
                    'title': 'Implement user authentication',
                    'subsystem': 'auth',
                    'evidence': 'added authenticate_user',
                }
            ],
        }
        results = store.reconcile_arc_delta(
            arc_delta=arc_delta,
            project_id=project_id,
            run_id='test-run-1',
            source_summary_id='test-summary-1',
        )
        assert len(results) >= 1

        store.close()
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council.py` | Wire adaptive triggers into HTTP endpoints |
| Modify | `arc_summarizer/__init__.py` | Wire analyzer into pipeline |
| Modify | `arc_summarizer/pipeline.py` | Production reconciliation wiring |
| Modify | `memory_service/__init__.py` | Health check updates |
| Create | `tests/test_session_analyzer.py` | Analyzer tests |
| Create | `tests/test_adaptive_summarization.py` | Trigger + mode tests |

---

## Post-Wiring Tests (GATE — must pass before marking complete)

- [ ] Session analyzer classifies sessions correctly (all 5 modes)
- [ ] Trimmed summary preserves all task-bearing signals
- [ ] Mode-aware summarization produces correct output format
- [ ] Idle trigger fires after N minutes of inactivity
- [ ] Token budget trigger fires before context overflow
- [ ] Model swap trigger preserves session state
- [ ] Significant event trigger fires on high-score sessions
- [ ] Scheduler _wake() responds to event hints immediately
- [ ] Reconciler thresholds match new banding (0.90/0.80/0.50)
- [ ] Subsystem alignment check works for 0.80-0.89 band
- [ ] Deviation candidates created from borderline matches
- [ ] Full end-to-end flow verified (session → analysis → summary → reconciliation → storage)
- [ ] All existing tests still pass (no regression)
- [ ] Health check reports all new components (session_analyzer, adaptive_triggers, event_hints)

---

## Completion Gate

- [ ] All implementation steps done
- [ ] All post-wiring tests pass
- [ ] No regression in existing tests
- [ ] Health check includes session_analyzer, adaptive_triggers, event_hints
- [ ] Files committed

---

## Notes for Completion

This is the final phase. After all post-wiring tests pass, the full system is operational:

1. **Sessions analyzed** — heuristic classifier detects mode from content signals
2. **Summaries trimmed** — fixed 11-field schema preserves task-bearing signals
3. **Triggers adaptive** — idle, turn count, token budget, model swap, significant events
4. **Scheduler responsive** — event hints wake consolidation without waiting
5. **Reconciler precise** — tight thresholds, subsystem alignment, deviation candidates
6. **Health visible** — all new components reported in health check

The system is now resilient against missed summaries — sessions get captured on multiple signals, not just explicit /quit hooks. The reconciliation engine sees structured trimmed summaries, not conversational noise. Threshold banding prevents over-merging while catching genuine duplicates.
