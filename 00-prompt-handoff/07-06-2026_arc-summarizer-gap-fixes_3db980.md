# Arc Summarizer Gap Fixes

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `3db980` |
| Entity type | `handoff` |
| Short description | Wire trim_session(), validate_source_fidelity(), and content gates into the active summarization pipeline |
| Status | `draft` |
| Source references | Research findings from session audit (2026-06-07) |
| Generated | 07-06-2026 |
| Next action / owner | Subagent (builder) — execute Phase 1 first |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `/home/chief/llm-wiki/Chief-Workstation/arc-summarizer-status.md`
**Key files for this task:**

| File | Role |
|------|------|
| `arc_summarizer/__init__.py` | ArcSummarizer entry point — summarize_session() |
| `arc_summarizer/analyzer.py` | SessionAnalyzer — trim_session(), classify(), _extract_signals_from_text() |
| `arc_summarizer/client.py` | ArcClient — HTTP client for model calls |
| `arc_summarizer/prompts.py` | Prompt templates including deviation detection |
| `arc_summarizer/pipeline.py` | ArcPipeline — consolidation, deviation reconciliation |
| `output_gate.py` | OutputGate — validate_source_fidelity() |
| `super_council.py` | _summarize_chat() handler — minimum content gate |
| `memory_service/store.py` | upsert_session_diary() — session diary storage |

## Background

The arc summarizer has three layers of deviation detection (regex, LLM, pipeline reconciliation) and one layer of hallucination detection (source-fidelity keyword overlap). The code is comprehensive but four gaps prevent it from producing visible output:

1. **trim_session() not wired** — `SessionAnalyzer.trim_session()` exists but is never called in the summarization path, so `notable_deviations` is never populated.
2. **validate_source_fidelity() not wired** — `OutputGate.validate_source_fidelity()` exists and is tested but is not called during session summarization.
3. **Empty session summaries** — No minimum content gate before calling the summarizer, producing near-blank summaries.
4. **Noise in error/blocker detection** — Generic patterns may still leak through in some paths.

## Execution Order

```
Phase 1 (trim_session wiring) ──┐
                                 ├── Phase 3 (content gate) ──┐
Phase 2 (hallucination guard) ──┘                            ├── Phase 4 (error audit)
                                                              (all previous complete)
```

- **Phase 1 & 2:** Can run in parallel (different files, no shared mutations)
- **Phase 3:** Depends on Phase 1 (needs trimmed summary structure for content evaluation)
- **Phase 4:** Depends on all previous (audit after changes are complete)

---

## Phase 1: Wire trim_session() → notable_deviations

**What:** Call `SessionAnalyzer.trim_session()` in `ArcSummarizer.summarize_session()` after the model returns raw summary text. Log and persist `notable_deviations` when found.

**Files:** `arc_summarizer/__init__.py`

**Steps:**

1. In `ArcSummarizer.summarize_session()` (line ~103), after `self._client.summarize_session()` returns `raw_summary`:
   - Instantiate `SessionAnalyzer()` (already imported at top of file)
   - Call `analyzer.trim_session(raw_summary, session_mode=session_mode)`
   - If `trimmed.get("notable_deviations")` is non-empty, log at INFO level
   - If `trimmed.get("errors_blockers")` is non-empty, log at DEBUG level

2. Return a tuple or dict from `summarize_session()`:
   ```python
   return {
       "summary": raw_summary,
       "trimmed": trimmed,
       "session_mode": session_mode,
   }
   ```
   **OR** keep backward compatibility by returning the string and storing trimmed data as an instance property:
   ```python
   self._last_trimmed = trimmed
   ```
   **Decision:** Use the dict return — it's cleaner and callers can extract what they need. Check all callers of `summarize_session()` and update them to handle the dict return.

3. Verify callers:
   - `arc_summarizer/__init__.py:48` — module-level `summarize_session()` convenience function
   - Any other callers via grep

**Tests:**
- Existing tests in `tests/test_classification_runtime.py` should still pass
- Add test: `test_trim_session_populates_deviations` — feed summary text with "expected X but got Y" pattern, verify `notable_deviations` is non-empty

**Dependencies:** None (Phase 1 is independent)

---

## Phase 2: Wire validate_source_fidelity_raw()

**Problem:** `OutputGate.validate_source_fidelity()` expects a structured dict with `completed_work` and `explicit_decisions` keys. The raw summary text from the model is Markdown, not structured. Two options:

- **Option A:** Parse Markdown summary into structured fields before validation (requires a parser)
- **Option B:** Add `validate_source_fidelity_raw(summary_text: str, source_turns: list)` that does keyword-level overlap without requiring structured input

**Decision:** Option B — lower effort, same protection level.

**Files:** `output_gate.py`, `arc_summarizer/__init__.py`

**Steps:**

1. In `output_gate.py`, add a new method to `OutputGate`:

```python
def validate_source_fidelity_raw(
    self,
    summary_text: str,
    source_turns: List[Dict[str, str]],
    threshold: float = 0.25,
) -> ValidationResult:
    """Check raw summary text against source turns for hallucination.

    Extracts significant phrases from the summary and verifies that
    supporting keywords exist in the source conversation turns.

    Uses a lower threshold (25%) than structured validation (30%) because
    raw text may contain paraphrased claims.
    """
    if not source_turns:
        return ValidationResult(
            valid=False,
            reason="No source turns available to verify claims",
            hallucination_candidates=[summary_text[:200]],
        )

    source_text = " ".join(
        t.get("content", "") for t in source_turns if t.get("content")
    ).lower()

    # Extract sentence-level claims from summary (split on double-newline or period+space)
    import re
    sentences = re.split(r'(?:\n\n|\. )', summary_text.lower())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    hallucination_candidates = []
    for sentence in sentences:
        if not self._claim_has_evidence(sentence, source_text, threshold=threshold):
            # Truncate for logging
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

2. In `arc_summarizer/__init__.py`, in `ArcSummarizer.summarize_session()`, after getting `raw_summary`:

```python
if raw_summary:
    from super_council.output_gate import OutputGate
    gate = OutputGate()
    fidelity = gate.validate_source_fidelity_raw(raw_summary, turns)
    if not fidelity.valid:
        log.warning(
            "Source fidelity warning in session summary: %d candidates: %s",
            len(fidelity.hallucination_candidates),
            fidelity.hallucination_candidates[:3],  # Log first 3
        )
    # Non-blocking: still return the summary
```

3. Add tests to `tests/test_hallucination_guard.py`:
   - `test_validate_source_fidelity_raw_passes` — summary with evidence in source
   - `test_validate_source_fidelity_raw_fails` — summary with fabricated claims
   - `test_validate_source_fidelity_raw_empty_source` — no source turns

**Dependencies:** None (Phase 2 is independent of Phase 1)

---

## Phase 3: Minimum Content Gate

**What:** Prevent empty/near-blank session summaries by checking content volume before calling the model.

**Files:** `super_council.py` (_summarize_chat), `arc_summarizer/__init__.py` (summarize_session)

**Steps:**

1. In `super_council.py`, in `_summarize_chat()` (line ~7324), before calling the external summarizer:

```python
# Minimum content gate — don't waste model calls on empty sessions
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
```

2. In `arc_summarizer/__init__.py`, in `ArcSummarizer.summarize_session()`, after model returns:

```python
if raw_summary and len(raw_summary.strip()) < 50:
    log.warning(
        "Session summary too short (%d chars), may indicate model failure",
        len(raw_summary),
    )
    # Still return — caller can decide
```

3. In `_summarize_session()` (line ~7222), add similar gate before calling the external summarizer:

```python
# Already has a check: len(log_content.strip().splitlines()) < 5
# Additional: check for actual content volume
if len(log_content.strip()) < 300:
    return {"status": 200, "message": "Log too short to summarize"}
```

**Tests:**
- Add test: `test_summarize_chat_skips_insufficient_content` — feed messages with <500 total chars, verify early return
- Add test: `test_summarize_chat_proceeds_with_sufficient_content` — feed messages with >500 chars, verify model is called

**Dependencies:** Phase 1 (needs trimmed summary structure to evaluate content quality in future enhancements)

---

## Phase 4: Error Pattern Audit

**What:** Verify that the tightened `_ERROR_PATTERN` in `analyzer.py` is the sole source of error/blocker detection in the summarization path. Remove any legacy patterns that produce noise.

**Files:** `analyzer.py` (verify), `super_council.py` (audit), `output_gate.py` (audit)

**Steps:**

1. Audit all files for error/blocker pattern usage:
   ```bash
   grep -rn "crash\|error.*pattern\|ERROR_PATTERN\|errors_blockers" --include="*.py" | grep -v __pycache__ | grep -v test_
   ```

2. Verify `_ERROR_PATTERN` in `analyzer.py` is the sole source:
   - Should NOT match bare "crash", "crashed", "error:"
   - Should match specific exception types: TypeError, ValueError, AttributeError, etc.
   - Should match "ERROR:" with meaningful message (2+ word chars)

3. If legacy patterns exist in `super_council.py` or other files, replace with reference to `_ERROR_PATTERN`:
   ```python
   from super_council.arc_summarizer.analyzer import _ERROR_PATTERN
   ```

4. Verify the `errors_blockers` field in trimmed summaries uses the tightened pattern:
   - In `_extract_signals_from_text()`, the error extraction should use `_ERROR_PATTERN`
   - Filter: `len(e.strip()) > 4` to exclude noise

**Tests:**
- Add regression test: `test_error_pattern_excludes_noise` — verify "crashed", "crash", "error:" do NOT match
- Add test: `test_error_pattern_matches_real_errors` — verify "TypeError: X", "AttributeError: Y" DO match

**Dependencies:** All previous phases complete

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/__init__.py` | Wire trim_session(), validate_source_fidelity_raw(), update return type |
| Modify | `output_gate.py` | Add validate_source_fidelity_raw() method |
| Modify | `super_council.py` | Add minimum content gates in _summarize_chat() and _summarize_session() |
| Audit | `analyzer.py` | Verify _ERROR_PATTERN is correct (no changes expected) |
| Create | `tests/test_trim_session_integration.py` | Tests for trim_session wiring |
| Modify | `tests/test_hallucination_guard.py` | Add tests for validate_source_fidelity_raw() |
| Modify | `tests/test_classification_runtime.py` | Add content gate tests |

## Constraints

- **Non-blocking validation:** Both trim_session() and validate_source_fidelity_raw() must be non-blocking. If they fail or produce warnings, the summary is still saved. The goal is visibility, not gatekeeping.
- **Backward compatibility:** If `summarize_session()` return type changes from `str` to `dict`, all callers must be updated. No partial migrations.
- **No new dependencies:** Do not add new Python packages. Use only stdlib and existing project dependencies.
- **Log levels:** Warnings for fidelity issues (INFO for deviations, WARNING for hallucination candidates, DEBUG for routine trimmed data).
- **Threshold tuning:** The 25% threshold for raw fidelity and 500-char minimum are starting points — they can be adjusted after observing real data.

## Success Criteria

- [ ] Phase 1: `trim_session()` is called in `summarize_session()`, `notable_deviations` is populated when deviation language exists in summary
- [ ] Phase 2: `validate_source_fidelity_raw()` is called after model returns summary, hallucination candidates are logged at WARNING level
- [ ] Phase 3: Sessions with <500 chars of content are skipped (no model call, no empty summary saved)
- [ ] Phase 4: `_ERROR_PATTERN` is the sole source of error detection; no legacy noise patterns remain
- [ ] All existing tests pass (no regression) — run `pytest tests/ -v`
- [ ] New tests pass for each phase
- [ ] Session summaries include `notable_deviations` section when deviations are detected
- [ ] Hallucination warnings appear in logs when summary claims lack source evidence

## Caveats & Uncertainty

1. **Return type change risk:** Changing `summarize_session()` from `str` to `dict` may affect callers outside the arc_summarizer module. Grep thoroughly before changing.
2. **Threshold calibration:** The 25% fidelity threshold and 500-char minimum are educated guesses. May need adjustment after 1-2 days of real usage.
3. **Performance impact:** `trim_session()` and `validate_source_fidelity_raw()` add ~50-100ms of processing per summary. Acceptable for /quit-time summarization, but could matter if called frequently.
4. **SessionAnalyzer import cycle:** `output_gate.py` importing from `arc_summarizer` could create circular imports. If so, use lazy imports (inside methods).
