# Phase 3: Minimum Content Gate

**Parent plan:** `07-06-2026_arc-summarizer-gap-fixes_3db980.md`
**Phase:** 3 of 4
**Dependencies:** Phase 1 (trimmed summary structure available for future quality evaluation)
**Estimated effort:** ~20 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council.py` — _summarize_chat() and _summarize_session() methods
- `arc_summarizer/__init__.py` — ArcSummarizer.summarize_session() method

## What This Phase Delivers

Sessions with insufficient content (<500 chars total) are skipped before calling the model. This prevents empty/near-blank summaries from being saved. The gate is applied at three points: the chat summary handler, the session summary handler, and the Arc summarizer.

## Pre-Flight Checklist

- [ ] Read `_summarize_chat()` in `super_council.py` (line ~7324) — understand current flow
- [ ] Read `_summarize_session()` in `super_council.py` (line ~7222) — understand current flow
- [ ] Note that `_summarize_session()` already has a line-count check (`< 5 lines`)

## Implementation Steps

### Step 1: Add content gate to _summarize_chat()

In `super_council.py`, in `_summarize_chat()` method, add the gate BEFORE the model call:

```python
def _summarize_chat(self, messages: list, summarize_alias: Optional[str] = None) -> dict:
    # ... existing alias resolution ...

    if not messages or len(messages) < 2:
        return {"status": 200, "message": "Too few messages to summarize"}

    # Phase 3: Minimum content gate
    total_content = sum(len(m.get("content", "")) for m in messages)
    MIN_SUMMARY_CHARS = 500  # ~100 words of actual conversation
    if total_content < MIN_SUMMARY_CHARS:
        log.info(
            "CHAT SUMMARY: skipped — insufficient content (%d chars < %d threshold)",
            total_content, MIN_SUMMARY_CHARS,
        )
        return {
            "status": 200,
            "message": f"Insufficient content to summarize ({total_content} chars)",
        }

    # ... rest of method (build summary prompt, call model, save) ...
```

### Step 2: Add content gate to _summarize_session()

In `super_council.py`, in `_summarize_session()` method, enhance the existing check:

```python
def _summarize_session(self, summarize_alias: Optional[str] = None) -> dict:
    # ... existing alias resolution ...

    daily_path = self.memory._daily_path()
    if not daily_path.exists():
        return {"status": 200, "message": "No log to summarize"}

    log_content = daily_path.read_text(encoding="utf-8")

    # Existing check: too few lines
    if len(log_content.strip().splitlines()) < 5:
        return {"status": 200, "message": "Too few entries to summarize"}

    # Phase 3: Content volume check
    if len(log_content.strip()) < 300:
        return {"status": 200, "message": "Log too short to summarize"}

    # ... rest of method ...
```

### Step 3: Add content warning to ArcSummarizer.summarize_session()

In `arc_summarizer/__init__.py`, after model returns:

```python
def summarize_session(self, turns: list, max_tokens: int = 256, session_mode: str = None) -> str | None:
    # ... existing classification and model call ...

    raw_summary = self._client.summarize_session(turns, max_tokens, session_mode=session_mode)

    if raw_summary and len(raw_summary.strip()) < 50:
        log.warning(
            "Session summary too short (%d chars), may indicate model failure or empty session",
            len(raw_summary),
        )

    # ... rest of method (trim_session, fidelity check) ...
    return raw_summary
```

### Step 4: Add tests

In `tests/test_classification_runtime.py` or a new test file:

```python
def test_summarize_chat_skips_insufficient_content():
    """Messages with <500 total chars should be skipped."""
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    # Mock the handler and verify early return
    # ... test implementation ...

def test_summarize_chat_proceeds_with_sufficient_content():
    """Messages with >500 total chars should proceed to model."""
    messages = [
        {"role": "user", "content": "x" * 300},
        {"role": "assistant", "content": "y" * 300},
    ]
    # Mock the handler and verify model is called
    # ... test implementation ...
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council.py` | Add content gates in _summarize_chat() and _summarize_session() |
| Modify | `arc_summarizer/__init__.py` | Add content warning after model returns |
| Modify | `tests/test_classification_runtime.py` | Add content gate tests |

## Phase-Specific Tests

1. **test_summarize_chat_skips_insufficient_content** — <500 chars → early return
2. **test_summarize_chat_proceeds_with_sufficient_content** — >500 chars → model called
3. **test_summarize_session_skips_short_log** — <300 chars → early return
4. **All existing tests pass** — No regression

## Completion Gate

- [ ] Content gate added to _summarize_chat() with 500-char threshold
- [ ] Content gate added to _summarize_session() with 300-char threshold
- [ ] Content warning added to ArcSummarizer.summarize_session() with 50-char threshold
- [ ] All 3 new tests pass
- [ ] All existing tests pass (no regression)
- [ ] Empty sessions no longer produce blank summaries

## Notes for Next Phase

Phase 4 (error audit) is the final step — it audits all changes to ensure no legacy noise patterns remain.
