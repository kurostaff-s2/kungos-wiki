# Arc Summarizer: Extraction Accuracy & Deviation Detection Fix

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `6b7b43` |
| Entity type | `handoff` |
| Short description | Fix arc summarizer extraction accuracy — decisions missing, open items hallucinated from conversation noise, deviation detection empty |
| Status | `draft` |
| Source references | `~/.council-memory/sessions/2026-06-07T15-34-41-582Z_*.md`, `super_council/arc_summarizer/analyzer.py`, `super_council/memory_service/session_watcher.py`, `super_council/output_gate.py` |
| Generated | 07-06-2026 |
| Next action / owner | Execute Phase 1 (ground truth isolation test), then Phase 2-4 sequentially |

## Problem Statement

The arc summarizer produces structured session summaries with three accuracy failures:

1. **Decisions missing:** Ground truth has 4 decisions; arc summary extracts `none`. The decision regex `(?:decision|decided|chose|going\s+with|settled\s+on)` requires explicit trigger words that don't appear in implicit decisions (e.g., "Use actual HTTP endpoints instead of planned ones").

2. **Open items hallucinated:** Ground truth has `open_items: None` (all chains completed); arc summary invents 17 open items from conversation fragments ("find the JSONL file", "verify the migration", "run the tests"). The open work regex `(?:need\s+to|TODO|FIXME|next\s+(?:step|action)|open\s+(?:item|question)|still\s+need)` matches any conversational fragment containing "need to".

3. **Deviations empty:** Ground truth has plan-vs-reality gaps (used actual HTTP endpoints instead of planned `/v1/council/*`); `notable_deviations` is empty because the deviation regex requires explicit expectation-vs-reality language that doesn't appear in the conversation.

**Root cause:** The session analyzer extracts signals from the *conversation trace* (our chat) rather than the *session diary* (ground truth written by chain runners). The `OutputGate.validate_source_fidelity_raw()` passes these hallucinations because keyword overlap exists — the words are real, just misclassified as work items.

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council`
**Reference docs:** `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_arc-summarizer-extraction-fix_6b7b43.md`
**Related codebases:** None
**Key files for this task:**
- `arc_summarizer/analyzer.py` — signal extraction regex patterns
- `arc_summarizer/__init__.py` — ArcSummarizer class, summarize_session() pipeline
- `memory_service/session_watcher.py` — SessionWatcher, _trim_session(), _write_session_md()
- `output_gate.py` — OutputGate, validate_source_fidelity_raw()

## Phase Structure

### Phase 1: Ground Truth Isolation Test

**What:** Prove the issue is in the extraction source (conversation trace) not the arc summarizer logic, by running the analyzer directly against the canonical MD file.

**Files:** `tests/test_extraction_ground_truth.py` (create)

**Steps:**
1. Read the canonical MD file: `~/.council-memory/sessions/2026-06-07T15-34-41-582Z_019ea2b8-d0ae-7686-bbd0-d681361840f3.md`
2. Parse it into the 12-field schema using `_try_structured_extract()` from `analyzer.py`
3. Assert that decisions, open_items, and work_completed match the session diary ground truth
4. Read the conversation trace (same session ID from `index_staging/memory_entries/`)
5. Parse it using `_extract_signals_from_text()` from `analyzer.py`
6. Assert that decisions are missing, open items are hallucinated, deviations are empty
7. Document the delta between the two extraction paths

**Tests:**
- `test_structured_extract_from_canonical_md` — MD file produces correct 12-field schema
- `test_signal_extract_from_conversation` — conversation trace produces noisy/incomplete signals
- `test_delta_between_paths` — quantify the accuracy gap (decisions missing, open items hallucinated)

**Dependencies:** None

---

### Phase 2: Diary-First Extraction in SessionWatcher

**What:** Make the session watcher check the session diary (ground truth) BEFORE extracting signals from the conversation trace. Diary data is canonical; conversation signals are advisory augmentation only.

**Files:** `memory_service/session_watcher.py` (modify)

**Steps:**
1. Add `_merge_with_diary()` method to `SessionWatcher` that:
   - Queries `session_diary` by session ID
   - If diary exists with decisions, use them as `explicit_decisions` (override extraction)
   - If diary exists with open_items, use them as `open_work` (override extraction)
   - If diary exists with work_completed, merge with extracted `completed_work` (deduplicate)
2. Modify `_trim_session()` to call `_merge_with_diary()` after `_extract_signals_from_text()`
3. Add `_diary_to_trimmed()` helper to convert diary row dict to trimmed schema dict
4. Update `_write_session_md()` to use merged data

**Tests:**
- `test_merge_with_diary_overrides_decisions` — diary decisions replace extracted decisions
- `test_merge_with_diary_overrides_open_items` — diary open_items replace extracted open_work
- `test_merge_with_diary_merges_work_completed` — diary work_completed deduplicates with extraction
- `test_trim_session_uses_diary_first` — full pipeline test with diary data present

**Dependencies:** Phase 1 (must confirm the issue is in extraction source)

---

### Phase 3: Tighten Open Work Regex + Intent Filter

**What:** Remove overly broad open work patterns ("need to", "still need", "next step") and add an intent filter to distinguish plan fragments from real open work items.

**Files:** `arc_summarizer/analyzer.py` (modify), `output_gate.py` (modify)

**Steps:**
1. In `analyzer.py`, replace the open work regex with tighter patterns:
   ```python
   # REMOVE: "need to", "next step", "open item", "still need" (too broad)
   # KEEP: explicit markers that signal intentional open work
   _OPEN_WORK_PATTERN = re.compile(
       r'(?:TODO|FIXME|HACK|XXX|BLOCKER|HANGING|UNRESOLVED)[:\s]+(.+?)(?:\.|,|$)',
       re.IGNORECASE,
   )
   ```
2. In `output_gate.py`, add `_is_plan_fragment()` method:
   ```python
   def _is_plan_fragment(self, claim: str) -> bool:
       """Check if a claim is a plan fragment rather than completed work."""
       plan_indicators = [
           r'\bneed\s+to\b', r'\bshould\b', r'\bwill\b', r'\bwould\b',
           r'\bcan\b', r'\bmight\b', r'\bmay\b', r'\bTODO\b', r'\bFIXME\b',
       ]
       return any(re.search(pattern, claim, re.IGNORECASE) for pattern in plan_indicators)
   ```
3. In `validate_source_fidelity_raw()`, filter out plan fragments before reporting hallucination candidates
4. In `validate_source_fidelity()`, add intent check for `completed_work` claims

**Tests:**
- `test_open_work_regex_rejects_conversation_noise` — "find the JSONL file" not extracted as open work
- `test_open_work_regex_accepts_todo_markers` — "TODO: fix auth bug" extracted as open work
- `test_plan_fragment_filter` — plan fragments filtered from hallucination candidates
- `test_intent_check_in_structured_validation` — completed_work claims checked for intent

**Dependencies:** None (can run in parallel with Phase 2)

---

### Phase 4: Deviation Detection from Diary Deltas

**What:** Detect plan-vs-reality deviations by comparing session diary decisions against the original plan references (carry_forward items, work_items). If a decision differs from the plan, it's a deviation.

**Files:** `arc_summarizer/analyzer.py` (modify), `memory_service/session_watcher.py` (modify)

**Steps:**
1. In `session_watcher.py`, add `_detect_deviations()` method that:
   - Gets carry_forward items for the session's project_id
   - Compares diary decisions against carry_forward text
   - If decision differs from plan (keyword overlap < 0.5), classify as deviation
   - Classify deviation type: `planned` (conscious choice), `unplanned` (unexpected), `optimization` (improvement)
2. Add deviations to trimmed summary as `notable_deviations`
3. Wire deviations to `carry_forward(kind="deviation")` in `_wire_carry_forward()`
4. Update `_write_session_md()` to include `## Deviations` section

**Tests:**
- `test_detect_deviations_from_carry_forward` — deviations detected when decision differs from plan
- `test_deviation_classification` — planned/unplanned/optimization classified correctly
- `test_deviations_wired_to_carry_forward` — deviations written to carry_forward table
- `test_deviations_in_session_md` — deviations appear in canonical MD file

**Dependencies:** Phase 2 (diary data must be available)

---

### Phase 5: Production Wiring & Regression Tests

**What:** Wire all components, run full pipeline end-to-end, verify accuracy against ground truth.

**Files:** All modified files, `tests/test_extraction_integration.py` (create)

**Steps:**
1. Run full session watcher pipeline on a real JSONL file
2. Verify canonical MD file has correct decisions, open items, work completed, deviations
3. Verify `validate_source_fidelity_raw()` catches remaining hallucinations
4. Verify hallucination candidates persisted as `plan_deviations` records
5. Run full test suite — no regressions

**Post-Wiring Tests (GATE):**
- [ ] Session watcher processes JSONL and writes canonical MD
- [ ] MD decisions match session diary ground truth
- [ ] MD open items match session diary ground truth (no hallucinations)
- [ ] MD deviations populated when plan-vs-reality gaps exist
- [ ] `validate_source_fidelity_raw()` rejects plan fragments as hallucination candidates
- [ ] Hallucination candidates persisted as `plan_deviations(deviation_type='hallucination')`
- [ ] All existing tests still pass (no regression)
- [ ] `recall.unified` returns accurate structured data from both channels

**Dependencies:** Phases 2, 3, 4 (all must be complete)

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_extraction_ground_truth.py` | Phase 1: isolation test |
| Modify | `memory_service/session_watcher.py` | Phase 2: diary-first extraction |
| Modify | `arc_summarizer/analyzer.py` | Phase 3: tighten open work regex |
| Modify | `output_gate.py` | Phase 3: intent filter |
| Modify | `memory_service/session_watcher.py` | Phase 4: deviation detection |
| Create | `tests/test_extraction_integration.py` | Phase 5: end-to-end tests |

## Constraints

- **Diary is canonical:** Session diary data overrides all extracted signals. Never replace diary data with extracted data.
- **No silent changes to 12-field schema:** All fields remain the same; only extraction quality changes.
- **Backward compatible:** `_trim_session()` must work when diary data is absent (fallback to extraction).
- **No new dependencies:** Use only existing regex, sqlite3, stdlib.
- **Language consistency:** Use `explicit_decisions` (not `decisions`), `open_work` (not `open_items`), `completed_work` (not `work_completed`) in code. MD headers use `## Decisions`, `## Open Items`, `## Work Completed`.

## Success Criteria

- [ ] Phase 1 proves the issue is in extraction source (conversation vs diary)
- [ ] Phase 2: diary decisions override extracted decisions
- [ ] Phase 2: diary open items override extracted open work
- [ ] Phase 3: open work regex rejects conversation noise
- [ ] Phase 3: intent filter catches plan fragments
- [ ] Phase 4: deviations detected from diary deltas
- [ ] Phase 5: full pipeline produces accurate canonical MD
- [ ] Phase 5: all existing tests pass (no regression)
- [ ] `recall.unified` returns accurate structured data from both channels

## Caveats & Uncertainty

- **Session diary availability:** Not all sessions have diary entries (older sessions, ad-hoc chains). The fallback to conversation extraction must still work.
- **Carry_forward sparsity:** Deviation detection requires carry_forward items. If none exist, no deviations are detected (false negative, not false positive).
- **Intent filter precision:** The plan fragment regex may have false positives (e.g., "we need to discuss this" in a decision context). Monitor and adjust thresholds.
- **Diary schema stability:** If the session diary schema changes, `_diary_to_trimmed()` must be updated. Consider a versioned mapping.

## Execution Order

```
Phase 1 (isolation test)
    ↓
Phase 2 (diary-first) ──→ Phase 4 (deviations)
    ↓
Phase 3 (regex tightening) [parallel with Phase 2]
    ↓
Phase 5 (wiring + regression)
```

Phase 3 can run in parallel with Phase 2. Phase 4 depends on Phase 2. Phase 5 depends on all.

## Notes for Next Phase

- Phase 2 expects `session_diary` table with `summary_id`, `decisions`, `open_items`, `work_completed` columns.
- Phase 3 expects `OutputGate.validate_source_fidelity_raw()` to return `ValidationResult` with `hallucination_candidates` list.
- Phase 4 expects `carry_forward` table with `project_id`, `tier`, `kind`, `text` columns.
- Phase 5 expects all modified files to be committed and indexed.
