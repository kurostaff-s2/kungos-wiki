# Phase 2: Adaptive Triggers

**Parent plan:** `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`
**Phase:** 2 of 4
**Dependencies:** Phase 1 (SessionAnalyzer must be complete)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/super_council.py` (modify — idle detection, token tracking, model swap hook)
- `super_council/arc_summarizer/scheduler.py` (modify — _wake() method for event hints)
- `super_council/memory_service/__init__.py` (modify — event hint handlers)

---

## What This Phase Delivers

Replace explicit-only trigger model with multi-signal adaptive triggers. Sessions get summarized automatically on idle, turn count, token budget, model swap, and significant events. Scheduler responds to event hints via _wake() method.

**Trigger signals:**
- Idle for N minutes (default: 5)
- Turn count threshold (existing, keep)
- Token budget nearing threshold
- Model swap (before context loss)
- Explicit summarize command (existing, keep)
- Significant event score

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (SessionAnalyzer + trimmed summary working)
- [ ] ArcClient.summarize_session() accepts session_mode parameter
- [ ] Existing tests pass (baseline: 495 passed)

---

## Implementation Steps

### Step 1: Add Idle Detection to Session Management

Add to `super_council/super_council.py`:

```python
import threading
import time
from datetime import datetime, timedelta

class SessionIdleTracker:
    """Track session idle time for adaptive summarization triggers.

    Thread-safe last-activity timestamp tracking.
    """
    def __init__(self, idle_threshold_minutes: int = 5):
        self._idle_threshold = timedelta(minutes=idle_threshold_minutes)
        self._last_activity: Dict[str, float] = {}  # session_id -> timestamp
        self._lock = threading.Lock()

    def record_activity(self, session_id: str) -> None:
        """Record activity for a session."""
        with self._lock:
            self._last_activity[session_id] = time.monotonic()

    def is_idle(self, session_id: str) -> bool:
        """Check if session has been idle beyond threshold."""
        with self._lock:
            last = self._last_activity.get(session_id)
            if last is None:
                return False  # No activity recorded yet
            return (time.monotonic() - last) >= self._idle_threshold.total_seconds()

    def get_idle_seconds(self, session_id: str) -> float:
        """Get idle time in seconds for a session."""
        with self._lock:
            last = self._last_activity.get(session_id)
            if last is None:
                return 0.0
            return time.monotonic() - last
```

Wire into HTTP request handler to record activity on each request.

### Step 2: Add Cumulative Token Tracking

Add to `super_council/super_council.py`:

```python
class SessionTokenTracker:
    """Track cumulative token usage per session.

    Triggers pre-emptive summarization when approaching context limit.
    """
    def __init__(self, warning_threshold: float = 0.8, max_tokens: int = 8000):
        self._warning_threshold = warning_threshold
        self._max_tokens = max_tokens
        self._session_tokens: Dict[str, int] = {}
        self._lock = threading.Lock()

    def record_tokens(self, session_id: str, tokens: int) -> None:
        """Record token usage for a session."""
        with self._lock:
            self._session_tokens[session_id] = self._session_tokens.get(session_id, 0) + tokens

    def should_summarize(self, session_id: str) -> bool:
        """Check if session has approached token budget warning threshold."""
        with self._lock:
            used = self._session_tokens.get(session_id, 0)
            return used >= (self._max_tokens * self._warning_threshold)

    def get_usage_ratio(self, session_id: str) -> float:
        """Get token usage ratio (0.0-1.0)."""
        with self._lock:
            used = self._session_tokens.get(session_id, 0)
            return min(used / self._max_tokens, 1.0)
```

### Step 3: Hook into Model Swap

Add to `super_council/super_council.py` in the `_swap_model` method:

```python
def _swap_model(self, new_alias: str) -> dict:
    """Swap to a different model.

    Triggers pre-summary before context loss.
    """
    # Pre-summary hook: summarize before losing context
    try:
        session_id = self._get_current_session_id()
        if session_id:
            self._summarize_session_before_swap(session_id)
    except Exception as e:
        log.warning("Pre-swap summary failed (non-fatal): %s", e)

    # ... existing swap logic ...

def _summarize_session_before_swap(self, session_id: str) -> None:
    """Summarize session before model swap to preserve context."""
    messages = self._get_session_messages(session_id)
    if messages:
        result = self._summarize_chat(messages)
        if result.get('status') == 200:
            log.info("Pre-swap summary written for session %s", session_id)
```

### Step 4: Add Significant Event Scoring

Add to `super_council/super_council.py`:

```python
class SignificantEventScorer:
    """Score session significance for adaptive summarization triggers.

    Simple heuristic: errors + decisions + file changes = significant.
    """
    # Signal weights
    WEIGHT_ERROR = 3
    WEIGHT_DECISION = 2
    WEIGHT_FILE_CHANGE = 2
    WEIGHT_TEST = 1
    WEIGHT_DELEGATION = 2

    THRESHOLD_SIGNIFICANT = 5  # Minimum score to trigger summarization

    def __init__(self):
        self._session_scores: Dict[str, int] = {}
        self._lock = threading.Lock()

    def record_event(self, session_id: str, event_type: str) -> None:
        """Record a significant event for a session."""
        weight = getattr(self, f'WEIGHT_{event_type.upper()}', 1)
        with self._lock:
            self._session_scores[session_id] = self._session_scores.get(session_id, 0) + weight

    def is_significant(self, session_id: str) -> bool:
        """Check if session has accumulated significant events."""
        with self._lock:
            return self._session_scores.get(session_id, 0) >= self.THRESHOLD_SIGNIFICANT

    def get_score(self, session_id: str) -> int:
        """Get significance score for a session."""
        with self._lock:
            return self._session_scores.get(session_id, 0)
```

Wire into existing event logging (errors, decisions, file changes, delegations).

### Step 5: Add _wake() to IdleWindowScheduler

Add to `super_council/arc_summarizer/scheduler.py`:

```python
def __init__(self, pipeline):
    self._pipeline = pipeline
    self._running = False
    self._thread: Optional[threading.Thread] = None
    self._started = False
    self._wake_event = threading.Event()  # For event-driven wake

# In _run_loop():
def _run_loop(self) -> None:
    """Main scheduler loop. Sleeps between check cycles or wakes on events."""
    while self._running:
        try:
            # Wait for either timeout or wake event
            self._wake_event.wait(timeout=self.CHECK_INTERVAL)
            self._wake_event.clear()
            self._check_cycle()
        except Exception as e:
            log.warning("Scheduler cycle error: %s", e)

def _wake(self) -> None:
    """Signal immediate check cycle (event-driven wake).

    Called when: chat_summary_saved, daily_summary_saved,
    daily_count_threshold_reached, weekly_completed.
    """
    self._wake_event.set()
    log.debug("Scheduler woken by event hint")
```

### Step 6: Wire Event Hints into Memory Service

Add to `super_council/memory_service/__init__.py`:

```python
def on_chat_summary_saved(self) -> None:
    """Event hint: chat summary saved, wake scheduler for daily consolidation."""
    if self._scheduler:
        self._scheduler._wake()

def on_daily_summary_saved(self) -> None:
    """Event hint: daily summary saved, check if short consolidation is due."""
    if self._scheduler:
        self._scheduler._wake()

def on_daily_count_threshold_reached(self, count: int) -> None:
    """Event hint: daily count threshold reached, trigger short consolidation."""
    if self._scheduler:
        self._scheduler._wake()

def on_weekly_completed(self) -> None:
    """Event hint: weekly consolidation completed, trigger deviation detection."""
    if self._scheduler:
        self._scheduler._wake()
```

Wire into existing summary save paths:
- `save_chat_summary()` → `on_chat_summary_saved()`
- `upsert_session_diary()` → `on_daily_summary_saved()`
- `reconcile_tasks()` → check daily count → `on_daily_count_threshold_reached()`
- `run_tiered_consolidation()` → `on_weekly_completed()` for weekly/bimonthly

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council.py` | Idle detection, token tracking, model swap hook, event scoring |
| Modify | `arc_summarizer/scheduler.py` | _wake() method for event hints |
| Modify | `memory_service/__init__.py` | Event hint handlers |

---

## Phase-Specific Tests

1. **Idle detection triggers after N minutes:** Session idle > 5 min → should_summarize returns True
2. **Turn count threshold triggers:** Turn count > threshold → should_summarize returns True (existing, verify)
3. **Token budget triggers pre-emptive summary:** Token usage > 80% → should_summarize returns True
4. **Model swap triggers pre-summary:** _swap_model() called → summary written before swap
5. **Significant event score triggers:** Score >= 5 → is_significant returns True
6. **_wake() wakes scheduler immediately:** Event hint → _wake_event set → check cycle runs
7. **Event hints trigger consolidation:** chat_summary_saved → scheduler wakes → daily consolidation runs
8. **Thread-safe tracking:** Concurrent activity records → no race conditions

---

## Completion Gate

- [ ] SessionIdleTracker implemented with thread-safe tracking
- [ ] SessionTokenTracker implemented with warning threshold
- [ ] Model swap pre-summary hook wired
- [ ] SignificantEventScorer implemented with weighted signals
- [ ] _wake() method added to IdleWindowScheduler
- [ ] Event hints wired into memory service
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests

---

## Notes for Next Phase

Phase 3 (Reconciler Thresholds) expects:
- Trimmed summaries available from Phase 1
- Adaptive triggers firing summaries that feed into reconciliation
- Event hints ensuring timely consolidation

Phase 4 (Production Wiring) expects:
- All adaptive triggers wired and tested
- Event hints flowing through scheduler
- Pre-summary hooks preserving context on model swap

**Ownership boundary for Phase 4 wiring:**
- Runtime (`super_council.py`) PRODUCES session signals: calls `_record_activity()`, `_add_tokens()`, `_record_event()`
- Scheduler CONSUMES signals and DECIDES when to act: runs `_check_idle()`, `_check_token_budget()`, `_check_event_score()`
- The scheduler never queries the runtime for state. The runtime pushes; the scheduler reacts.
- No new abstraction layer needed — direct method calls (Option C)
