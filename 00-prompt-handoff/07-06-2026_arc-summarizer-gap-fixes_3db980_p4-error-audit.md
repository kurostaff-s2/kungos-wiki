# Phase 4: Error Pattern Audit

**Parent plan:** `07-06-2026_arc-summarizer-gap-fixes_3db980.md`
**Phase:** 4 of 4 (final)
**Dependencies:** All previous phases complete
**Estimated effort:** ~15 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `arc_summarizer/analyzer.py` — _ERROR_PATTERN definition (verify, likely no changes)
- `super_council.py` — audit for legacy error patterns
- `output_gate.py` — audit for legacy error patterns

## What This Phase Delivers

Verification that `_ERROR_PATTERN` in `analyzer.py` is the sole source of error/blocker detection in the summarization path. No legacy noise patterns (bare "crash", "crashed", "error:") remain in any active code path.

## Pre-Flight Checklist

- [ ] Phases 1-3 are complete and all tests pass
- [ ] Run `pytest tests/ -v` to confirm green state

## Implementation Steps

### Step 1: Audit all error pattern usage

```bash
cd /home/chief/Coding-Projects/7-council/super_council
grep -rn "crash\|error.*pattern\|ERROR_PATTERN\|errors_blockers" --include="*.py" | grep -v __pycache__ | grep -v "test_"
```

Review each match:
- Is it the tightened `_ERROR_PATTERN` from `analyzer.py`? → OK
- Is it a legacy pattern that matches bare "crash"/"crashed"? → Replace or remove
- Is it a test file? → Skip (tests may intentionally test noise patterns)

### Step 2: Verify _ERROR_PATTERN is correct

In `arc_summarizer/analyzer.py`, verify the pattern:

```python
_ERROR_PATTERN = re.compile(
    r'(?:TypeError|ValueError|KeyError|AttributeError|ConnectionError|TimeoutError|'
    r'RuntimeError|IndexError|FileNotFoundError|PermissionError|'
    r'ERROR:\s+\w{2,}|Exception:\s+\w{2,}|Traceback|panic:|fatal:|segfault|SIGSEGV|'
    r'Failed\s+to\s+\w{3,})',
    re.IGNORECASE,
)
```

This should:
- ✅ Match: "TypeError: X", "AttributeError: Y", "ERROR: something meaningful", "Failed to connect"
- ❌ NOT match: bare "crash", "crashed", "error:", "error" (without context)

### Step 3: Verify _extract_signals_from_text() uses the tightened pattern

In `analyzer.py`, verify that `_extract_signals_from_text()` uses `_ERROR_PATTERN` for error extraction:

```python
errors = _ERROR_PATTERN.findall(text)
if errors:
    errors = [e.strip() for e in errors if len(e.strip()) > 4]
    result["errors_blockers"] = list(set(errors))
```

The `len(e.strip()) > 4` filter is the noise guard.

### Step 4: Check for legacy patterns in super_council.py

Search for any error/blocker detection in the summarization handlers:

```bash
grep -n "blocker\|error.*detect\|errors_blockers" super_council.py | head -20
```

If legacy patterns exist, replace with reference to `_ERROR_PATTERN`:

```python
from super_council.arc_summarizer.analyzer import _ERROR_PATTERN
```

### Step 5: Add regression tests

```python
def test_error_pattern_excludes_noise():
    """Bare noise words should NOT match."""
    from super_council.arc_summarizer.analyzer import _ERROR_PATTERN
    noise_texts = [
        "the app crashed",
        "it crashed with a segfault",  # "segfault" would match — this is intentional
        "error: ",
        "crashed",
        "crash",
    ]
    for text in noise_texts:
        matches = _ERROR_PATTERN.findall(text)
        # "segfault" is intentionally matched — it's a real error signal
        if "segfault" not in text.lower():
            assert len(matches) == 0, f"Expected no matches for '{text}', got {matches}"

def test_error_pattern_matches_real_errors():
    """Real error patterns should match."""
    from super_council.arc_summarizer.analyzer import _ERROR_PATTERN
    real_errors = [
        "TypeError: expected str, got int",
        "AttributeError: 'NoneType' object has no attribute 'x'",
        "ERROR: Connection refused",
        "Failed to initialize the database",
        "Traceback (most recent call last):",
        "panic: runtime error",
    ]
    for text in real_errors:
        matches = _ERROR_PATTERN.findall(text)
        assert len(matches) > 0, f"Expected matches for '{text}', got {matches}"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Audit | `arc_summarizer/analyzer.py` | Verify _ERROR_PATTERN is correct (no changes expected) |
| Audit | `super_council.py` | Check for legacy error patterns |
| Audit | `output_gate.py` | Check for legacy error patterns |
| Modify | `tests/test_classification_runtime.py` | Add regression tests for error patterns |

## Phase-Specific Tests

1. **test_error_pattern_excludes_noise** — Bare "crash", "crashed", "error:" do NOT match
2. **test_error_pattern_matches_real_errors** — Real exceptions DO match
3. **All existing tests pass** — No regression

## Completion Gate

- [ ] _ERROR_PATTERN is the sole source of error detection in summarization path
- [ ] No legacy noise patterns remain in active code
- [ ] Regression tests added and passing
- [ ] All 79+ existing tests still pass (no regression)
- [ ] Full test suite: `pytest tests/ -v` passes

## Notes for Final Verification

After all 4 phases are complete:

1. Run the full test suite: `pytest tests/ -v`
2. Verify session summaries include `notable_deviations` when deviation language exists
3. Verify hallucination warnings appear in logs for fabricated claims
4. Verify empty sessions produce no summaries
5. Verify error/blocker detection excludes noise
