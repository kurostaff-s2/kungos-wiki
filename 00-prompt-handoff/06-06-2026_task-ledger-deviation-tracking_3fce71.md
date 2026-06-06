# Task Ledger & Deviation Tracking — Master Plan

**Source spec:** First-principles analysis (session 06-06-2026, corrected evaluation post-data-loss discovery)
**Generated:** 06-06-2026
**Goal:** Implement structured task ledger with reconciliation engine and deviation tracking, wired into ARC consolidation pipeline.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Database:** `/home/chief/.council-memory/council_core.db` (primary), `/home/chief/.council-memory/pipelines.db` (secondary)
**Reference docs:** This handoff document
**Related codebases:** `/home/chief/Coding-Projects/7-council/super_council/` (memory_service, arc_summarizer)
**Key files for this task:**
- `super_council/memory_service/store.py` — RelationalStore (schema + CRUD)
- `super_council/arc_summarizer/pipeline.py` — ARC consolidation pipeline
- `super_council/arc_summarizer/prompts.py` — ARC prompt templates
- `super_council/arc_summarizer/client.py` — ARC HTTP client

---

## Background

The Council Core database was accidentally deleted during prior task implementation. Evidence of prior usage: ~2MB daily logs (May 11 → June 4), 149 chat summaries, 5 weeks of active development. Current row counts (2 work_items, 27 diary entries) reflect data loss, not low usage.

**Problem:** No structured task tracking, no dedup engine, no deviation context. Every session mention of a task spawns noise. Plan-vs-reality divergence is untracked.

**Solution:** Task ledger with reconciliation engine + deviation tracking, fed by ARC structured output.

---

## Execution Order (DAG)

```
Phase 1: Schema Migration (sequential — must complete first)
    ↓
Phase 2: Reconciliation Engine (depends on Phase 1)
    ↓
Phase 3: ARC Wiring (depends on Phase 2)
    ↓
Phase 4: Deviation Detection (depends on Phase 3, can parallel with Phase 5 prep)
    ↓
Phase 5: Production Wiring (depends on all above)
```

All phases are sequential. No parallel fan-out — each phase depends on prior schema/state.

---

## Phase 1: Schema Migration

**What:** Extend `work_items` with 7-state status model, add `plan_deviations` + `plan_deviations_events` tables, add run_id provenance linkage.

**Files:**
- Create: `super_council/memory_service/migrations/001_task_ledger_schema.sql`
- Modify: `super_council/memory_service/store.py` (add CRUD methods)

**Steps:**
1. Write migration SQL for `work_items` status extension (ALTER TABLE or recreate with new CHECK constraint)
2. Write migration SQL for `plan_deviations` table (15 columns per proposal)
3. Write migration SQL for `plan_deviations_events` table
4. Add `first_seen_run_id`, `last_seen_run_id`, `last_touched_run_id` to `work_items`
5. Apply migrations to both `council_core.db` and `pipelines.db`
6. Add CRUD methods to `RelationalStore`: `create_work_item()`, `update_work_item_status()`, `get_work_item_events()`, `create_deviation()`, `update_deviation_status()`, `get_deviations()`
7. Verify schema with `PRAGMA table_info` on both databases

**Tests:**
- Schema migration applies cleanly to both databases
- All CRUD methods return expected types
- Status transitions respect CHECK constraints
- Run_id provenance is stored and retrievable

**Dependencies:** None (first phase)

---

## Phase 2: Reconciliation Engine

**What:** Build dedup engine that compares ARC-extracted task candidates against existing `work_items` and classifies each as `create`, `merge`, `reopen`, `mark_done`, or `ignore_duplicate`.

**Files:**
- Create: `super_council/memory_service/reconciliation.py`
- Modify: `super_council/memory_service/store.py` (add reconciliation entry points)

**Steps:**
1. Implement `TaskReconciler` class with methods:
   - `normalize_title(title: str) -> str` — lowercase, strip punctuation, collapse whitespace
   - `compute_dedup_key(title: str, project_id: str, subsystem: str = None) -> str` — compound identity
   - `classify_candidate(candidate: dict, existing_items: list) -> str` — returns create/merge/reopen/mark_done/ignore_duplicate
   - `reconcile(arc_delta: dict, project_id: str) -> list` — main entry point, returns list of actions
2. Implement title similarity scoring (Levenshtein or token overlap) for fuzzy matching
3. Implement status transition logic based on evidence keywords:
   - "fixed", "verified", "tests passing" → mark_done
   - "should", "need to", "later", "didn't get to" → create or preserve open
   - "blocked by" → blocked
4. Wire into `RelationalStore` as `reconcile_arc_delta(arc_delta, project_id)`
5. Add confidence scoring: high (>0.8) → auto-apply, medium (0.5-0.8) → apply with flag, low (<0.5) → human review

**Tests:**
- Normalization produces consistent keys for equivalent titles
- Dedup correctly identifies duplicates across sessions
- Status transitions apply correct keywords
- Confidence scoring gates auto-apply correctly
- Reconciliation doesn't create duplicates when same task is mentioned 5 times

**Dependencies:** Phase 1 (schema must exist)

---

## Phase 3: ARC Wiring

**What:** Extend ARC pipeline to emit structured task deltas and route them through the reconciliation engine into `work_items`.

**Files:**
- Modify: `super_council/arc_summarizer/prompts.py` (add task extraction prompt)
- Modify: `super_council/arc_summarizer/pipeline.py` (add task reconciliation step)
- Modify: `super_council/arc_summarizer/client.py` (add task extraction endpoint)

**Steps:**
1. Add `TASK_EXTRACTION_PROMPT_TEMPLATE` to `prompts.py`:
   - Input: session summary text
   - Output: structured JSON with `new_tasks[]`, `task_updates[]`, `completed_tasks[]`, `blocked_tasks[]`, `open_questions[]`, `ignored_candidates[]`
2. Add `extract_tasks(session_text: str) -> dict` method to `ArcClient`
3. Add `reconcile_tasks()` step to `ArcPipeline.run_tiered_consolidation()`:
   - After consolidation YAML is parsed, extract task signals
   - Route through `RelationalStore.reconcile_arc_delta()`
   - Store results in `work_items` with provenance linkage
4. Add `build_task_extraction_prompt()` and `parse_task_extraction_yaml()` to prompts.py
5. Ensure ARC output includes `source_summary_id` and `run_id` for provenance

**Tests:**
- Task extraction prompt returns valid JSON/YAML
- Reconciliation step doesn't crash on empty ARC output
- Task items are created with correct provenance linkage
- Duplicate tasks are not created across multiple consolidations

**Dependencies:** Phase 2 (reconciliation engine must exist)

---

## Phase 4: Deviation Detection

**What:** Enable ARC to detect plan-vs-reality deviations and propose `plan_deviations` records.

**Files:**
- Modify: `super_council/arc_summarizer/prompts.py` (add deviation detection prompt)
- Modify: `super_council/arc_summarizer/pipeline.py` (add deviation reconciliation step)
- Modify: `super_council/memory_service/store.py` (add deviation CRUD if not in Phase 1)

**Steps:**
1. Add `DEVIATION_DETECTION_PROMPT_TEMPLATE` to `prompts.py`:
   - Input: plan/spec excerpt + implementation summary
   - Output: structured JSON with `new_deviations[]`, `deviation_updates[]`, `closed_deviations[]`
   - Deviation types: `planned`, `unplanned`, `optimization` (3 types, not 4)
2. Add `detect_deviations(plan_text: str, implementation_text: str) -> dict` to `ArcClient`
3. Add `reconcile_deviations()` step to `ArcPipeline`:
   - Compare architecture/spec documents against implementation summaries
   - Route through deviation reconciliation
   - Store in `plan_deviations` with provenance linkage
4. Link deviations to related work_items via `plan_deviation_id` foreign key
5. Add query methods: `get_deviations_for_project()`, `get_open_deviations()`, `get_deviation_with_tasks()`

**Tests:**
- Deviation detection identifies clear plan-vs-reality mismatches
- Deviation records are created with correct linkage to work_items
- Deviation status transitions work (proposed → approved → implemented → closed)
- Query methods return correct results

**Dependencies:** Phase 3 (ARC wiring must exist)

---

## Phase 5: Production Wiring

**What:** Wire all components into the running system. Verify full consolidation → extraction → reconciliation → storage flow.

**Files:**
- Modify: `super_council/memory_service/__main__.py` (start reconciliation thread)
- Modify: `super_council/arc_summarizer/scheduler.py` (schedule reconciliation after consolidation)
- Create: `super_council/memory_service/test_reconciliation.py` (integration tests)

**Steps:**
1. Add reconciliation thread to memory_service startup
2. Schedule task reconciliation after each ARC consolidation run
3. Schedule deviation detection after each weekly/bimonthly consolidation
4. Run end-to-end test: session summary → ARC consolidation → task extraction → reconciliation → work_items
5. Verify health check includes reconciliation status
6. Verify all existing tests still pass (no regression)

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] Memory service starts and responds to health checks
- [ ] ARC consolidation runs and produces task deltas
- [ ] Reconciliation engine processes deltas without errors
- [ ] Work items are created/updated in `work_items` table
- [ ] Deviation records are created in `plan_deviations` table
- [ ] Provenance linkage (run_id, source_summary_id) is correct
- [ ] Duplicate tasks are not created across multiple consolidations
- [ ] All existing tests still pass (no regression)

**Dependencies:** Phases 1-4 (all must be complete)

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/memory_service/migrations/001_task_ledger_schema.sql` | Schema migration SQL |
| Create | `super_council/memory_service/reconciliation.py` | Task reconciliation engine |
| Create | `super_council/memory_service/test_reconciliation.py` | Integration tests |
| Modify | `super_council/memory_service/store.py` | Add CRUD methods for work_items, deviations, events |
| Modify | `super_council/arc_summarizer/prompts.py` | Add task extraction + deviation detection prompts |
| Modify | `super_council/arc_summarizer/pipeline.py` | Add reconciliation steps to consolidation pipeline |
| Modify | `super_council/arc_summarizer/client.py` | Add task extraction + deviation detection endpoints |
| Modify | `super_council/memory_service/__main__.py` | Start reconciliation thread |
| Modify | `super_council/arc_summarizer/scheduler.py` | Schedule reconciliation after consolidation |

---

## Constraints

- **Raw summaries never directly mutate canonical tasks** — ARC emits deltas, reconciliation applies, `work_items` holds truth.
- **Same deviation types everywhere** — `planned`, `unplanned`, `optimization` (3 types only, no `emergency`).
- **Provenance is mandatory** — every task update and deviation record stores `source_summary_id` and `run_id`.
- **Dedup before create** — reconciliation always checks existing items before creating new ones.
- **Confidence gates auto-apply** — high confidence (>0.8) auto-applies; medium (0.5-0.8) flags for review; low (<0.5) requires human confirmation.
- **Both databases updated** — migrations apply to `council_core.db` and `pipelines.db`.
- **No zombie tables** — all writes route through `memory_entries` / `work_items` / `plan_deviations` (not `session_diary` or `consolidation_cache`).
- **carry_forward is typed JSON, not TEXT blobs** — bounded schema: `{kind, text, priority, source_entry_id, expires_after_tier}`. No freeform prose persistence.
- **Carry-forward accumulation is capped** — max 5 items per tier; items must be explicit unresolved work, risk, or continuity notes; items expire after 2 same-tier cycles unless reasserted. This is a Phase 1 rule, not a caveat.
- **Bimonthly tier is an experiment gate** — implemented but treated as provisional. If first post-deployment verification run produces thin or empty output, drop bimonthly and promote `weekly` to top tier. Default assumption: weekly is the de facto top useful tier unless bimonthly proves otherwise.

---

## Success Criteria

- [ ] `work_items` has 7-state status model (`proposed`, `open`, `in_progress`, `blocked`, `done`, `wont_do`, `superseded`)
- [ ] `plan_deviations` table exists with 15 columns and companion events table
- [ ] Reconciliation engine deduplicates tasks across sessions (no duplicates when same task mentioned 5+ times)
- [ ] ARC emits structured task deltas after each consolidation run
- [ ] Task deltas are reconciled and stored in `work_items` with provenance linkage
- [ ] Deviation detection identifies plan-vs-reality mismatches
- [ ] Deviation records are linked to related work_items
- [ ] Full end-to-end flow verified: session → ARC → reconciliation → storage
- [ ] All existing tests still pass (no regression)
- [ ] Memory service starts and runs reconciliation thread without errors

---

## Caveats & Uncertainty

1. **Schema migration risk:** ALTER TABLE with CHECK constraint changes may require table recreation in SQLite. Test on a copy first.
2. **ARC output quality:** Task extraction depends on Granite-4.1-3B producing valid YAML/JSON. Fallback parsing must handle malformed output gracefully.
3. **Dedup accuracy:** Title normalization + fuzzy matching may produce false merges (different tasks with similar titles) or false negatives (same task with different phrasing). Confidence scoring mitigates but doesn't eliminate.
4. **Database consistency:** Two databases (`council_core.db` and `pipelines.db`) must stay in sync. Consider consolidating to one database in a future migration.
5. **Performance:** Reconciliation runs after every consolidation. If consolidations are frequent, reconciliation must be fast (<500ms per run).
6. **Bimonthly tier is provisional** — implemented as experiment gate. If first verification run is thin/empty, drop to weekly-top-tier. This is a hard decision, not a revisit trigger.

---

## Clarification Notes

- **Status model:** 7 states chosen based on proposal, but 4 states (`open`, `blocked`, `done`, `wont_do`) cover 90% of cases. Build all 7 now to avoid migration later.
- **Deviation types:** 3 types (`planned`, `unplanned`, `optimization`) instead of proposed 4. `emergency` is a subset of `unplanned` with higher severity, not a distinct type.
- **Dedup key:** Compound identity (`normalized_title + project_id + optional_subsystem`) is the reconciliation key. Subsystem is optional — if not provided, falls back to title + project_id only.
- **carry_forward is typed JSON:** Bounded schema `{kind, text, priority, source_entry_id, expires_after_tier}` — no freeform TEXT blobs. Ages better than stringly-typed persistence.
- **Carry-forward safeguards are Phase 1 rules:** Max 5 items per tier; items must be explicit unresolved work, risk, or continuity notes; items expire after 2 same-tier cycles unless reasserted. This prevents the carry-forward channel from becoming a second source of compression pollution.
- **Bimonthly is an experiment gate:** Implemented but treated as provisional. If first post-deployment verification run produces thin (<3 meaningful entries) or empty output, drop bimonthly and promote `weekly` to top tier. Default assumption: weekly is the de facto top useful tier unless bimonthly proves otherwise. This keeps the pyramid from preserving an expensive, low-yield stage purely out of symmetry.
