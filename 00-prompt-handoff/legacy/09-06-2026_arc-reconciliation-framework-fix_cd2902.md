# Arc Reconciliation Framework — Findings & Fix Options

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `cd2902` |
| Entity type | `handoff` |
| Short description | Reconciliation framework is purely mechanical extraction — sparse output, missing source tags, noise items pass through. Document findings and options to fix. |
| Status | `draft` |
| Source references | `arc_summarizer/reconcile.py`, `arc_summarizer/pipeline.py`, `memory_service/reconciliation.py`, `arc-reconcile/daily/tasks.md` |
| Generated | `09-06-2026` |
| Next action / owner | Choose fix option, execute Phase 1 (noise filtering + source tags) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `arc_summarizer/reconcile.py`, `arc_summarizer/pipeline.py`, `memory_service/reconciliation.py`
**Related codebases:** None
**Key files for this task:** `arc_summarizer/reconcile.py`, `arc_summarizer/prompts.py`, `arc_summarizer/pipeline.py`

## Current Architecture

```
Raw session data
       ↓
  ARC LLM consolidation (client.py → _call_with_fallback())
       ↓
  arc-memory/daily/ (structured MD: narrative memory, evolving context)
       ↓
  ArcReconciler (reconcile.py) ← PURE CODE, NO LLM
       ↓
  arc-reconcile/daily/ (tasks.md, deviations.md, carry_forward.md)
```

**Design intent:** Memory consolidation preserves running narrative memory. Reconciliation tracks workflow, mistakes, deviations. Split because ARC LLM isn't powerful enough to do both simultaneously.

**Current reality:** Reconciliation is purely mechanical extraction from consolidation outputs. No semantic understanding, no workflow context, no mistake tracking.

## Findings

### F1: Noise items pass through as real items

**Evidence:** `arc-reconcile/daily/tasks.md` contains:
```
## Open
- None identified in the provided session summary.
```

**Root cause:** `_parse_bullet_list()` treats any `- item` line as a real item. No filtering of noise patterns ("None identified", "none", "N/A", etc.).

**Impact:** Reconciliation output is polluted with false items. Downstream consumers can't distinguish real work from LLM filler text.

### F2: No source tags on reconciliation items

**Evidence:** Every item in `tasks.md` lacks traceability:
```
## Completed
- Completed Phase 1 session analyzer implementation.
```

No source file, no session ID, no position context. Impossible to trace back to the original conversation.

**Root cause:** `_extract_tasks()`, `_extract_deviations()`, `_extract_carry_forward()` never capture or propagate source metadata. `_read_latest_consolidation()` doesn't include `_source_file`.

**Impact:** Reconciliation items are orphaned. Can't verify provenance, can't re-examine original context, can't audit decisions.

### F3: Structured YAML fields are lost

**Evidence:** Consolidation output has rich structure:
```yaml
work_completed:
  - what: Fixed the schema count inconsistency
    files: [session_summarization.md]
    functions: [trim_session]
    position: after investigating CPU usage
```

Reconciliation output loses all nested fields:
```
## Completed
- Fixed the schema count inconsistency
```

**Root cause:** `_parse_bullet_list()` only captures `- item` lines, ignoring continuation lines (`files:`, `functions:`, `position:`, `evidence:`).

**Impact:** Positional context, file references, function references, and evidence are all dropped. Reconciliation can't track WHAT files were touched, WHERE in conversation, or WHY the decision was made.

### F4: Deviations are rarely produced

**Evidence:** `arc-reconcile/daily/` only has `tasks.md` — no `deviations.md` or `carry_forward.md`.

**Root cause:** The daily consolidation prompt asks for `deviations` in the output schema, but the ARC LLM rarely produces them (no plan-vs-reality signals in most sessions). The reconciler has no fallback for detecting deviations from other signals.

**Impact:** Plan-vs-reality tracking is effectively non-existent. Deviations only appear when explicitly stated in conversation.

### F5: Reconciliation is purely reactive

**Evidence:** The reconciler only extracts what the ARC LLM already produced. It doesn't independently analyze workflow, detect mistakes, or identify patterns.

**Root cause:** By design — reconciliation was split from consolidation to avoid overloading the ARC LLM. But the mechanical extraction is too dumb to serve the intended purpose.

**Impact:** Reconciliation doesn't track workflow, mistakes, or deviations independently. It's just a copy of the consolidation output with less structure.

## Options to Fix

### Option A: Mechanical improvements (low risk, immediate)

**What:** Fix the extraction pipeline to preserve structure, filter noise, include source tags.

**Changes:**
1. `_parse_bullet_list()` → filter noise patterns ("None identified", "none", "N/A", etc.)
2. `_parse_structured_items()` (new) → parse YAML-like bullet items with nested fields
3. `_extract_tasks()`, `_extract_deviations()`, `_extract_carry_forward()` → use `_parse_structured_items()`, propagate source metadata
4. `_read_latest_consolidation()` → include `_source_file` in parsed dict
5. `_write_reconciliation_file()` → output source tags, position, evidence, files, functions

**Files:** `arc_summarizer/reconcile.py`

**Effort:** ~30 min

**Risk:** Low — purely mechanical changes, no LLM involvement

**Outcome:** Reconciliation output includes source tags, position context, evidence. Noise items filtered. Structured fields preserved.

**Limitation:** Still purely reactive — only extracts what ARC LLM already produced. No independent workflow/mistake detection.

### Option B: Add LLM-based reconciliation (medium risk, higher value)

**What:** Add a separate LLM call for reconciliation — independent of consolidation.

**Design:**
1. New prompt template: `RECONCILIATION_PROMPT` — focused on workflow, mistakes, deviations
2. New client method: `reconcile_session()` — calls ARC LLM with reconciliation prompt
3. New pipeline method: `run_reconciliation()` — orchestrates LLM call + mechanical extraction
4. Reconciliation prompt analyzes the SAME annotated conversation but with different goals:
   - Track work flow (what was planned vs. what was done)
   - Detect mistakes (errors, regressions, wrong turns)
   - Identify deviations (plan-vs-reality gaps)
   - Extract lessons learned (patterns, anti-patterns)

**Files:** `arc_summarizer/prompts.py`, `arc_summarizer/client.py`, `arc_summarizer/pipeline.py`, `arc_summarizer/reconcile.py`

**Effort:** ~60 min

**Risk:** Medium — adds another LLM call, increases latency, may overload ARC server

**Outcome:** Reconciliation has independent semantic understanding. Can detect workflow patterns, mistakes, deviations that consolidation misses.

**Caveat:** Requires ARC server to handle two concurrent calls (consolidation + reconciliation). May need timeout adjustment or model scaling.

### Option C: Hybrid — mechanical extraction + heuristic deviation detection (low risk, incremental)

**What:** Keep mechanical extraction, add heuristic-based deviation detection from conversation signals.

**Changes:**
1. Implement Option A (mechanical improvements)
2. Add `_detect_deviations_from_signals()` — heuristic analysis of conversation for:
   - Error patterns → mistakes
   - Plan language vs. completion language → deviations
   - Rework patterns (edit same file multiple times) → workflow issues
3. Wire into `_extract_deviations()` as fallback when LLM produces no deviations

**Files:** `arc_summarizer/reconcile.py`, `arc_summarizer/analyzer.py`

**Effort:** ~45 min

**Risk:** Low — heuristic-based, no LLM involvement

**Outcome:** Better deviation detection without LLM overhead. Still mechanical but more intelligent.

**Limitation:** Heuristics are brittle. May produce false positives. Doesn't achieve full semantic understanding.

## Recommendation

**Start with Option A (mechanical improvements) — already implemented in this session.**

The changes are low risk, immediate value, and don't require LLM changes. They fix the most critical issues (noise filtering, source tags, structured field preservation).

**Then evaluate Option B (LLM-based reconciliation) if:**
- Reconciliation output is still too sparse after Option A
- Independent workflow/mistake detection is required
- ARC server can handle concurrent calls

**Option C (hybrid) is a fallback if Option B is too risky but more intelligence is needed.**

## Implementation Phases

### Phase 1: Mechanical improvements (Option A)

**What:** Fix extraction pipeline to preserve structure, filter noise, include source tags.
**Files:** `arc_summarizer/reconcile.py`
**Steps:**
1. Add noise filtering to `_parse_bullet_list()`
2. Implement `_parse_structured_items()` for YAML-like bullet parsing
3. Update `_extract_tasks()`, `_extract_deviations()`, `_extract_carry_forward()` to use structured parsing
4. Update `_read_latest_consolidation()` to include `_source_file`
5. Update `_write_reconciliation_file()` to output source tags, position, evidence
**Tests:** Verify noise items filtered, structured fields preserved, source tags included
**Dependencies:** None

### Phase 2: LLM-based reconciliation (Option B, optional)

**What:** Add separate LLM call for reconciliation with independent prompt.
**Files:** `arc_summarizer/prompts.py`, `arc_summarizer/client.py`, `arc_summarizer/pipeline.py`
**Steps:**
1. Create `RECONCILIATION_PROMPT` template focused on workflow/mistakes/deviations
2. Add `reconcile_session()` client method
3. Wire into pipeline as separate step after consolidation
4. Update reconciler to consume LLM output + mechanical extraction
**Tests:** Verify LLM call succeeds, output is structured, reconciliation includes independent analysis
**Dependencies:** Phase 1 complete

### Phase 3: Heuristic deviation detection (Option C, optional)

**What:** Add heuristic-based deviation detection from conversation signals.
**Files:** `arc_summarizer/reconcile.py`, `arc_summarizer/analyzer.py`
**Steps:**
1. Implement `_detect_deviations_from_signals()` with error/rework/plan patterns
2. Wire into `_extract_deviations()` as fallback
3. Tune heuristics to reduce false positives
**Tests:** Verify deviation detection works, false positives are acceptable
**Dependencies:** Phase 1 complete

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/reconcile.py` | Noise filtering, structured parsing, source tags |
| Modify | `arc_summarizer/prompts.py` | Reconciliation prompt (Phase 2) |
| Modify | `arc_summarizer/client.py` | Reconciliation LLM call (Phase 2) |
| Modify | `arc_summarizer/pipeline.py` | Wire reconciliation step (Phase 2) |

## Constraints

- **No LLM changes in Phase 1:** Mechanical improvements must not require ARC server changes.
- **Backward compatible:** Existing reconciliation output format must be preserved (add fields, don't remove).
- **Source tags mandatory:** Every reconciliation item must include source file for traceability.
- **Noise filtering mandatory:** "None identified", "none", "N/A" must never appear as real items.

## Success Criteria

- [ ] Noise items filtered from reconciliation output
- [ ] Every reconciliation item includes source tag
- [ ] Structured fields (position, evidence, files, functions) preserved
- [ ] Deviations produced when plan-vs-reality signals exist
- [ ] All existing tests still pass (no regression)
- [ ] Reconciliation output is actionable (can trace back to original session)
