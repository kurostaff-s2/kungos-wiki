# Phase 2: Wire validate_source_fidelity_raw()

**Parent plan:** `07-06-2026_arc-summarizer-gap-fixes_3db980.md`
**Phase:** 2 of 4
**Dependencies:** None (independent of Phase 1)
**Estimated effort:** ~45 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `output_gate.py` — OutputGate class, add new method
- `arc_summarizer/__init__.py` — Wire the call in summarize_session()
- `tests/test_hallucination_guard.py` — Add new tests

## What This Phase Delivers

`OutputGate.validate_source_fidelity_raw(summary_text, source_turns)` is called after every session summarization. It verifies that claims in the summary have supporting evidence in the source conversation. Hallucination candidates are logged at WARNING level. The check is non-blocking — the summary is still saved even if claims are unverified.

## Pre-Flight Checklist

- [ ] Read `output_gate.py` fully — understand existing `validate_source_fidelity()` and `_claim_has_evidence()`
- [ ] Read `tests/test_hallucination_guard.py` — understand existing test patterns
- [ ] Verify no circular import risk: `output_gate.py` should NOT import from `arc_summarizer`

## Implementation Steps

### Step 1: Add validate_source_fidelity_raw() to OutputGate

In `output_gate.py`, add a new method to the `OutputGate` class:

```python
def validate_source_fidelity_raw(
    self,
    summary_text: str,
    source_turns: List[Dict[str, str]],
    threshold: float = 0.25,
) -> ValidationResult:
    """Check raw summary text against source turns for hallucination.

    Extracts sentence-level claims from the summary and verifies that
    supporting keywords exist in the source conversation turns.

    Uses a lower threshold (25%) than structured validation (30%) because
    raw text may contain paraphrased claims.

    Args:
        summary_text: Raw summary text (Markdown or plain text).
        source_turns: List of {role, content} conversation turns.
        threshold: Minimum fraction of claim words found in source (default 0.25).

    Returns:
        ValidationResult with .valid flag and .hallucination_candidates list.
    """
    if not summary_text or not summary_text.strip():
        return ValidationResult(valid=True)  # Empty summary — nothing to verify

    if not source_turns:
        return ValidationResult(
            valid=False,
            reason="No source turns available to verify claims",
            hallucination_candidates=[summary_text[:200]],
        )

    # Build source text corpus
    source_text = " ".join(
        t.get("content", "") for t in source_turns if t.get("content")
    ).lower()

    # Extract sentence-level claims from summary
    import re
    sentences = re.split(r'(?:\n\n|\. )', summary_text.lower())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    if not sentences:
        return ValidationResult(valid=True)  # No substantial claims to verify

    hallucination_candidates = []
    for sentence in sentences:
        if not self._claim_has_evidence(sentence, source_text, threshold=threshold):
            truncated = sentence[:120] + ("..." if len(sentence) > 120 else "")
            hallucination_candidates.append(truncated)

    if hallucination_candidates:
        return ValidationResult(
            valid=False,
            reason=f"{len(hallucination_candidates)} claim(s) lack source evidence",
            hallucination_candidates=hallucination_candidates,
        )

    return ValidationResult(valid=True)
```

### Step 2: Wire the call in ArcSummarizer.summarize_session()

In `arc_summarizer/__init__.py`, after the raw summary is obtained:

```python
if raw_summary:
    # Wire hallucination guard — Phase 2 fix
    try:
        from super_council.output_gate import OutputGate
        gate = OutputGate()
        fidelity = gate.validate_source_fidelity_raw(raw_summary, turns)
        if not fidelity.valid:
            log.warning(
                "Source fidelity warning in session summary: %d candidate(s): %s",
                len(fidelity.hallucination_candidates),
                fidelity.hallucination_candidates[:3],  # Log first 3
            )
    except Exception as e:
        log.debug("Source fidelity check failed (non-fatal): %s", e)
```

**Important:** Use lazy import (`from super_council.output_gate import OutputGate` inside the method) to avoid circular imports. The `arc_summarizer` module is imported by `super_council.py` which may also import `output_gate.py`.

### Step 3: Add tests

In `tests/test_hallucination_guard.py`, add:

```python
def test_validate_source_fidelity_raw_passes(self):
    """Summary with evidence in source should pass."""
    source_turns = [
        {"role": "user", "content": "I implemented the authentication module with JWT tokens."},
        {"role": "assistant", "content": "Great, the JWT implementation looks correct."},
    ]
    summary = "The authentication module was implemented using JWT tokens. The implementation was verified."
    result = self.gate.validate_source_fidelity_raw(summary, source_turns)
    assert result.valid is True

def test_validate_source_fidelity_raw_fails(self):
    """Summary with fabricated claims should fail."""
    source_turns = [
        {"role": "user", "content": "Let me check the database schema."},
        {"role": "assistant", "content": "The schema looks fine."},
    ]
    summary = "The authentication module was completely rewritten. OAuth2 was implemented. The database was migrated to PostgreSQL."
    result = self.gate.validate_source_fidelity_raw(summary, source_turns)
    assert result.valid is False
    assert len(result.hallucination_candidates) > 0

def test_validate_source_fidelity_raw_empty_source(self):
    """No source turns should fail with clear reason."""
    summary = "Some summary text here."
    result = self.gate.validate_source_fidelity_raw(summary, [])
    assert result.valid is False
    assert "No source turns" in result.reason

def test_validate_source_fidelity_raw_empty_summary(self):
    """Empty summary should pass (nothing to verify)."""
    result = self.gate.validate_source_fidelity_raw("", [{"role": "user", "content": "hello"}])
    assert result.valid is True
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `output_gate.py` | Add validate_source_fidelity_raw() method |
| Modify | `arc_summarizer/__init__.py` | Wire the call in summarize_session() |
| Modify | `tests/test_hallucination_guard.py` | Add 4 new tests |

## Phase-Specific Tests

1. **test_validate_source_fidelity_raw_passes** — Summary with evidence → valid=True
2. **test_validate_source_fidelity_raw_fails** — Summary without evidence → valid=False, candidates populated
3. **test_validate_source_fidelity_raw_empty_source** — No source → valid=False
4. **test_validate_source_fidelity_raw_empty_summary** — Empty summary → valid=True
5. **All existing tests pass** — No regression

## Completion Gate

- [ ] validate_source_fidelity_raw() method added to OutputGate
- [ ] Method is called in ArcSummarizer.summarize_session()
- [ ] Hallucination candidates logged at WARNING level
- [ ] Lazy import used (no circular import risk)
- [ ] All 4 new tests pass
- [ ] All existing tests pass (no regression)

## Notes for Next Phase

Phase 3 (content gate) is independent. Phase 4 (error audit) depends on all phases being complete.
