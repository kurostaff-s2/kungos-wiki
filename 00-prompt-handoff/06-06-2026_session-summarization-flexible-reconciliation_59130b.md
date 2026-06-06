# Flexible Session Summarization & Two-Stage Reconciliation — Master Plan

**Source spec:** Design discussion (session 06-06-2026, four-point approach + two-stage reconciliation proposal)
**Generated:** 06-06-2026
**Goal:** Make session summarization mode-aware with adaptive triggers, and introduce a two-stage reconciliation pipeline (raw → trimmed → reconciliation) for cleaner task matching.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** This handoff document
**Related codebases:** `/home/chief/Coding-Projects/7-council/super_council/` (arc_summarizer, memory_service, super_council.py)
**Key files for this task:**
- `super_council/arc_summarizer/prompts.py` — summarization prompt templates
- `super_council/arc_summarizer/client.py` — ArcClient.summarize_session()
- `super_council/arc_summarizer/pipeline.py` — reconciliation pipeline
- `super_council/arc_summarizer/scheduler.py` — IdleWindowScheduler
- `super_council/memory_service/reconciliation.py` — TaskReconciler
- `super_council/memory_service/store.py` — RelationalStore CRUD methods
- `super_council/super_council.py` — session summarization endpoints, model swap hooks

---

## Background

**Current state:** Session summarization is rigid — single prompt, explicit triggers only (/quit hook or manual HTTP calls). The reconciliation engine works on raw session summaries that include conversational noise. No session mode awareness. No adaptive triggers.

**Problem:** Work slips through when sessions end without a summary. The reconciliation engine sees noisy input, reducing match accuracy. Same summarization prompt for code sessions, research sessions, planning sessions, and debugging sessions.

**Solution:** Four-point approach for flexible summarization + two-stage reconciliation pipeline.

---

## Execution Order (DAG)

```
Phase 1: Session Analyzer + Trimmed Summary (sequential — must complete first)
    ↓
Phase 2: Adaptive Triggers (depends on Phase 1)
    ↓
Phase 3: Reconciler Thresholds + Deviation Candidates (depends on Phase 1, can parallel with Phase 2)
    ↓
Phase 4: Production Wiring (depends on all above)
```

Phases 2 and 3 can execute in parallel after Phase 1 completes.

---

## Phase 1: Session Analyzer + Trimmed Summary

**What:** Heuristic session classifier that detects session mode from content signals. Generates trimmed summary with fixed 11-field schema. Integrates mode-aware summarization into ArcClient.

**Files:**
- Create: `super_council/arc_summarizer/analyzer.py` — SessionAnalyzer class
- Modify: `super_council/arc_summarizer/prompts.py` — superset schema, mode-specific prompts
- Modify: `super_council/arc_summarizer/client.py` — mode-aware summarize_session()

**Steps:**
1. Implement `SessionAnalyzer` class with heuristic classification:
   - Signal counts: code paths mentioned, errors, decisions, source URLs, planning verbs
   - Returns score vector: `{code: float, research: float, planning: float, debugging: float, mixed: float}`
   - Picks highest score as `session_mode`. Falls back to `mixed` when scores are within 0.1 of each other
2. Implement `trim_session()` method:
   - Input: raw session summary text
   - Output: fixed-schema dict with 11 fields (session_id, project_id, run_id, session_type, files_changed, functions_touched, tests_written, errors_blockers, explicit_decisions, completed_work, open_work, notable_deviations)
   - Strips conversational noise, preserves task-bearing signals
3. Update `SUMMARIZATION_PROMPT_TEMPLATE` to include superset schema:
   - All 12 sections (topics, decisions, work_completed, open_items, files_changed, functions_modified, tests_written, bugs_fixed, sources_consulted, key_findings, root_cause, resolution)
   - Mode-specific emphasis via system prompt instructions (e.g., code mode emphasizes files_changed + functions_modified)
4. Update `ArcClient.summarize_session()` to accept `session_mode` parameter:
   - Routes to mode-appropriate prompt variant
   - Returns both human-readable summary AND trimmed structured dict

**Tests:**
- Heuristic classifier correctly identifies code sessions (file paths, function names)
- Heuristic classifier correctly identifies research sessions (source URLs, findings)
- Heuristic classifier correctly identifies planning sessions (decisions, trade-offs)
- Heuristic classifier correctly identifies debugging sessions (errors, root causes)
- Falls back to `mixed` when scores are close
- Trimmed summary preserves all task-bearing signals
- Mode-aware summarization produces correct output format

**Dependencies:** None (first phase)

---

## Phase 2: Adaptive Triggers

**What:** Replace explicit-only trigger model with multi-signal adaptive triggers. Sessions get summarized automatically on idle, turn count, token budget, model swap, and significant events.

**Files:**
- Modify: `super_council/super_council.py` — idle detection, token tracking, model swap hook
- Modify: `super_council/arc_summarizer/scheduler.py` — _wake() method for event hints
- Modify: `super_council/memory_service/__init__.py` — event hint handlers

**Steps:**
1. Add idle detection to session management:
   - Track last_activity timestamp per session
   - Trigger summarization when idle > N minutes (configurable, default: 5)
   - Thread-safe timestamp tracking
2. Add cumulative token tracking during session:
   - Track per-session token usage (already partially done in `_parse_daily_log_stats`)
   - Trigger pre-emptive summarization when approaching context limit
3. Hook into model swap (`_swap_model`):
   - Trigger summarization before context is lost
   - Preserve session state across model changes
4. Add significant event scoring:
   - Simple heuristic: errors + decisions + file changes = significant
   - Trigger summarization when score exceeds threshold
5. Add `_wake()` method to `IdleWindowScheduler`:
   - `threading.Event` to signal immediate check cycle
   - Called on: chat_summary_saved, daily_summary_saved, daily_count_threshold_reached, weekly_completed
6. Wire event hints into memory service:
   - `chat_summary_saved` → wake scheduler for daily consolidation
   - `daily_count_threshold_reached` → wake for short consolidation

**Tests:**
- Idle detection triggers summarization after N minutes
- Turn count threshold triggers summarization (existing, verify)
- Token budget threshold triggers pre-emptive summarization
- Model swap triggers summarization before context loss
- Significant event score triggers summarization
- _wake() method wakes scheduler immediately
- Event hints trigger consolidation without waiting for time-based cycle

**Dependencies:** Phase 1 (needs session analyzer for mode detection)

---

## Phase 3: Reconciler Thresholds + Deviation Candidates

**What:** Tighten reconciliation threshold banding. Add subsystem alignment check for borderline matches. Create deviation candidates from plan-vs-reality signals in trimmed summaries.

**Files:**
- Modify: `super_council/memory_service/reconciliation.py` — threshold bands, subsystem alignment
- Modify: `super_council/arc_summarizer/pipeline.py` — deviation candidate creation
- Modify: `super_council/memory_service/store.py` — deviation CRUD (if not already complete)

**Steps:**
1. Update threshold banding in `TaskReconciler`:
   - `>= 0.90`: auto-merge / exact-equivalent
   - `0.80–0.89`: safe merge if project AND subsystem align
   - `0.50–0.79`: candidate only, require review or secondary evidence
   - `< 0.50`: no match, create new
2. Add subsystem alignment check for 0.80-0.89 band:
   - Verify same project_id AND same subsystem/file_path before auto-merge
   - Falls back to candidate-only if subsystem doesn't align
3. Add deviation candidate creation from borderline matches:
   - When fuzzy match is 0.50-0.79 AND evidence suggests plan-vs-reality divergence
   - Create deviation candidate instead of new task
   - Bridges reconciliation engine with deviation detection system
4. Add raw session fallback for low-confidence matches:
   - Store raw summary reference (file path) alongside trimmed summary
   - Load raw text only when confidence is 0.50-0.79 and human review is triggered

**Tests:**
- Threshold 0.90+ auto-merges correctly
- Threshold 0.80-0.89 requires subsystem alignment
- Threshold 0.50-0.79 creates candidate only
- Threshold < 0.50 creates new task
- Deviation candidate created from borderline match with divergence evidence
- Raw session fallback loads only on low-confidence matches

**Dependencies:** Phase 1 (needs trimmed summary with structured signals)

---

## Phase 4: Production Wiring

**What:** Wire all components into running system. Verify full flow: session → analysis → trimmed summary → reconciliation → storage. Verify adaptive triggers fire correctly. Verify scheduler responds to event hints.

**Files:**
- Modify: `super_council/super_council.py` — wire adaptive triggers into HTTP endpoints
- Modify: `super_council/arc_summarizer/__init__.py` — wire analyzer into pipeline
- Create: `super_council/tests/test_session_analyzer.py` — analyzer tests
- Create: `super_council/tests/test_adaptive_summarization.py` — trigger + mode tests

**Steps:**
1. Wire SessionAnalyzer into ArcPipeline:
   - `summarize_session()` calls `SessionAnalyzer.classify()` before summarization
   - Passes `session_mode` to prompt builder
2. Wire adaptive triggers into super_council.py:
   - Idle detection in session management
   - Token budget tracking in daily log
   - Model swap hook in `_swap_model`
3. Wire event hints into scheduler:
   - `chat_summary_saved` → `_wake()` call
   - `daily_count_threshold_reached` → `_wake()` call
4. Run end-to-end integration test:
   - Session with code signals → classified as `code` mode → trimmed summary → reconciliation
   - Session idle > 5 minutes → adaptive trigger → summary written
   - Model swap → pre-summary hook → summary preserved
   - Chat summary saved → scheduler wakes → daily consolidation runs
5. Verify health check includes new components:
   - Session analyzer status
   - Adaptive trigger status
   - Event hint responsiveness

**Post-Wiring Tests (GATE — must pass before marking complete):**
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
- [ ] Health check reports all new components

**Dependencies:** Phases 1-3 (all must be complete)

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `arc_summarizer/analyzer.py` | SessionAnalyzer: heuristic classifier + trimmed summary |
| Modify | `arc_summarizer/prompts.py` | Superset schema, mode-specific prompts |
| Modify | `arc_summarizer/client.py` | Mode-aware summarize_session() |
| Modify | `arc_summarizer/pipeline.py` | Deviation candidate creation from borderline matches |
| Modify | `arc_summarizer/scheduler.py` | _wake() method for event hints |
| Modify | `memory_service/reconciliation.py` | Threshold bands, subsystem alignment |
| Modify | `memory_service/store.py` | Deviation CRUD (if needed) |
| Modify | `memory_service/__init__.py` | Event hint handlers |
| Modify | `super_council.py` | Adaptive triggers, idle detection, token tracking |
| Modify | `arc_summarizer/__init__.py` | Wire analyzer into pipeline |
| Create | `tests/test_session_analyzer.py` | Analyzer tests |
| Create | `tests/test_adaptive_summarization.py` | Trigger + mode tests |

---

## Constraints

- **One summarizer, no role sprawl:** Keep one summarizer prompt family with session_mode switch. Do not create multiple summarizer roles.
- **Heuristic-first classifier:** No extra model call for classification. Use signal counts (code paths, errors, decisions, URLs, planning verbs).
- **Fixed 11-field schema:** The trimmed summary schema is a contract. All downstream consumers (ARC, reconciliation, deviation detection) depend on it. Extensible via `_extra` catch-all field.
- **Raw fidelity preserved:** Raw session logs are never modified. Trimmed summary is a derived artifact. Raw text is consulted only on low-confidence matches.
- **Threshold stability:** The matcher sees structured signals (trimmed summary), not full chat noise. Thresholds are calibrated against trimmed input.
- **Decision order enforced:** Exact match → same project + fuzzy match → same project + subsystem + fuzzy evidence → fallback to new task or deviation candidate.
- **No event bus:** Use direct internal signals (chat_summary_saved, daily_summary_saved, daily_count_threshold_reached, weekly_completed). No general-purpose messaging subsystem.
- **Backward compatible:** Existing summarization behavior works as default fallback when session_mode is not detected.

---

## Success Criteria

- [ ] SessionAnalyzer classifies sessions into 5 modes with heuristic signals
- [ ] Trimmed summary preserves all task-bearing signals in fixed 11-field schema
- [ ] Mode-aware summarization produces correct output per session type
- [ ] Adaptive triggers fire on: idle, turn count, token budget, model swap, significant events
- [ ] Scheduler responds to event hints via _wake() method
- [ ] Reconciler uses new threshold banding (0.90/0.80/0.50)
- [ ] Subsystem alignment check prevents over-merging in 0.80-0.89 band
- [ ] Deviation candidates created from borderline matches with divergence evidence
- [ ] Full end-to-end flow verified (session → analysis → summary → reconciliation → storage)
- [ ] All existing tests still pass (no regression)
- [ ] Health check reports all new components

---

## Caveats & Uncertainty

1. **Heuristic classifier accuracy:** Mixed sessions (code + planning) will produce close scores. Score vector fallback to `mixed` handles this, but may miss nuanced sessions. Model-based classifier (Phase C) addresses this if heuristics prove insufficient.

2. **Token tracking adds overhead:** Cumulative token tracking during session requires per-request accounting. Current `_parse_daily_log_stats` is post-hoc. Real-time tracking adds minor latency.

3. **Idle detection thread safety:** Last-activity timestamp tracking must be thread-safe in the HTTP server. Use `threading.Lock` or atomic operations.

4. **Schema evolution risk:** The 11-field trimmed summary is a contract. Adding/removing fields requires migration if downstream consumers depend on specific fields. The `_extra` catch-all mitigates this.

5. **Event hint timing:** _wake() signals immediate check cycle, but the scheduler may be mid-cycle. Use `threading.Event` for non-blocking wake.

6. **Raw session fallback complexity:** Loading raw text on low-confidence matches adds I/O. Only triggered when confidence is 0.50-0.79 AND human review is needed. Acceptable tradeoff.

---

## Clarification Notes

- **Session modes:** 5 modes chosen (code, research, planning, debugging, mixed) based on observed session patterns. `mixed` is the fallback when scores are close, not a sixth mode.
- **Score vector:** Each mode gets a 0.0-1.0 score. Highest score wins. If two scores are within 0.1, default to `mixed`. This prevents forced classification on ambiguous sessions.
- **Trimmed schema:** 11 fields chosen to cover all task-bearing signals. `_extra` field allows extensibility without breaking the contract.
- **Threshold banding:** New bands (0.90/0.80/0.50) are tighter than current (0.8/0.5). Calibrated against trimmed summary input, not raw session text.
- **Event hints:** 4 signals chosen (chat_summary_saved, daily_summary_saved, daily_count_threshold_reached, weekly_completed) to cover the consolidation pyramid without a full event bus.
