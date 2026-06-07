# Phase 1: Wire trim_session() → notable_deviations

**Parent plan:** `07-06-2026_arc-summarizer-gap-fixes_3db980.md`
**Phase:** 1 of 4
**Dependencies:** None (can run first)
**Estimated effort:** ~30 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `arc_summarizer/__init__.py` — ArcSummarizer.summarize_session() method
- `arc_summarizer/analyzer.py` — SessionAnalyzer.trim_session() method
- `tests/test_classification_runtime.py` — existing tests to verify no regression

## What This Phase Delivers

`SessionAnalyzer.trim_session()` is called after every session summarization. The 12-field trimmed summary (including `notable_deviations`, `errors_blockers`, `completed_work`) is returned alongside the raw summary text. When deviations are detected, they are logged at INFO level for visibility.

## Pre-Flight Checklist

- [ ] Read `arc_summarizer/__init__.py` fully (current state of summarize_session)
- [ ] Read `arc_summarizer/analyzer.py` trim_session() method signature and return type
- [ ] Grep all callers of `summarize_session()` to understand impact of return type change

## Implementation Steps

### Step 1: Audit callers of summarize_session()

```bash
cd /home/chief/Coding-Projects/7-council/super_council
grep -rn "summarize_session\|\.summarize_session" --include="*.py" | grep -v __pycache__ | grep -v "def summarize_session"
```

Identify all callers and their expected return type.

### Step 2: Modify ArcSummarizer.summarize_session()

In `arc_summarizer/__init__.py`, modify the method to:

1. After `self._client.summarize_session()` returns `raw_summary`:
2. Call `SessionAnalyzer().trim_session(raw_summary, session_mode=session_mode)`
3. Store trimmed data as `self._last_trimmed` (instance property, preserves backward compat)
4. Log `notable_deviations` at INFO level if non-empty
5. Return raw_summary (string, unchanged — preserves backward compatibility)

```python
def summarize_session(
    self,
    turns: list,
    max_tokens: int = 256,
    session_mode: str = None,
) -> str | None:
    # ... existing classification logic ...

    raw_summary = self._client.summarize_session(turns, max_tokens, session_mode=session_mode)

    if raw_summary:
        # Wire trim_session() — Phase 1 fix
        try:
            analyzer = SessionAnalyzer()
            trimmed = analyzer.trim_session(raw_summary, session_mode=session_mode)
            self._last_trimmed = trimmed

            if trimmed.get("notable_deviations"):
                log.info(
                    "Notable deviations in session: %s",
                    trimmed["notable_deviations"],
                )
            if trimmed.get("errors_blockers"):
                log.debug(
                    "Errors/blockers in session: %s",
                    trimmed["errors_blockers"],
                )
        except Exception as e:
            log.debug("trim_session failed (non-fatal): %s", e)

    return raw_summary
```

### Step 3: Add `_last_trimmed` property

Add to the `ArcSummarizer` class:

```python
@property
def last_trimmed(self) -> dict | None:
    """Last trimmed summary from summarize_session()."""
    return getattr(self, '_last_trimmed', None)
```

### Step 4: Update module-level convenience function

In `arc_summarizer/__init__.py`, the `summarize_session()` convenience function (line ~40) should also wire trim_session if it uses ArcClient directly.

### Step 5: Verify backward compatibility

Ensure all callers still receive a `str | None` return value.

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/__init__.py` | Wire trim_session(), add _last_trimmed property |

## Phase-Specific Tests

1. **test_trim_session_called:** Mock `ArcClient.summarize_session()` to return text with "expected X but got Y" pattern. Call `ArcSummarizer.summarize_session()`. Verify `last_trimmed` has `notable_deviations` populated.
2. **test_trim_session_no_regression:** Run existing test suite — all tests should pass.
3. **test_trim_session_empty_summary:** Feed empty summary, verify `last_trimmed` has empty lists (not None).

## Completion Gate

- [ ] trim_session() is called after every summarize_session() call
- [ ] notable_deviations are logged at INFO level when found
- [ ] last_trimmed property returns the structured 12-field dict
- [ ] Return type is still `str | None` (backward compatible)
- [ ] All existing tests pass
- [ ] New test added for trim_session integration

## Notes for Next Phase

Phase 2 (hallucination guard) is independent — can run in parallel. Phase 3 (content gate) may use `last_trimmed` for content quality evaluation.
