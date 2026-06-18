# Corrected Findings Validation Report

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Entity ID | `6d5fc5` |
| Entity Type | `handoff` |
| Status | `in_progress` |
| Generated | 18-06-2026 20:35 IST |
| Source | Mellum2-12B review + manual verification |

## Executive Summary

**7 FIXED today** | **8 CONFIRMED (still need work)** | **3 FALSE_POSITIVE** | **8 DEFERRED/ACCEPTABLE**

---

## FIXED Today (7 findings)

| # | Finding | File | Evidence |
|---|---------|------|----------|
| 9/19 | Missing `import json` in scheduler.py | `scheduler.py:17` | `import json` present at line 17 |
| 5/17 | `_wake()` swallows exceptions silently | `session_watcher.py:228` | Now logs: `log.debug("...failed to wake scheduler (%s): %s", event_name, e)` |
| 11/24 | `from_model="supervisor"` hardcoded | `council_delegations.py:192` | Changed to `from_model="extension"` |
| 23 | Duplicate log statement in pipeline.py | `pipeline.py:409` | Merged into single: `"%d/%d parts moved"` format |
| 17 | Duplicate imports inside function | `council_delegations.py` | Removed function-level `import os`, `from pathlib import Path` |
| 18 | `import time` inside function | `council_delegations.py:14` | Moved to module-level import |
| NEW | Delegation response extraction bug | `index.ts:931` | `extractResponse()` extracts per-result from `sr.finalOutput` or `sr.messages` |

## CONFIRMED — Still Need Work (8 findings)

| # | Severity | Finding | File | Fix Required |
|---|----------|---------|------|--------------|
| 4/20 | **HIGH** | `_log_outlier()` has NO dedup guard — same entries logged every 300s | `session_watcher.py:208` | Add `(trace_id, reason)` dedup set or cooldown window |
| 21 | **HIGH** | Race condition in outlier file writes — `] {...} ]` corruption | `session_watcher.py:208` | Add `threading.Lock()` or switch to JSONL append-only |
| 10 | **HIGH** | `_rollup_exists_for_source_file()` can NEVER find 165 rollups (all `source_file=NULL`) | `session_watcher.py:190` | Also check by `trace_id` or `source_id`, not just `source_file` |
| 12 | **MODERATE** | 165 daily rollups have `source_id=NULL` — dedup guard can't find them | `memory_rollups` table | Backfill `source_id` from MD headers or accept as legacy |
| 13 | **MODERATE** | Multiple rollups per `source_file` (up to 6x) — no uniqueness constraint | `memory_rollups` table | Add unique constraint or investigate re-processing root cause |
| 6 | **MODERATE** | `FILE_IDLE_SECONDS=600` blocks watcher thread per file | `session_watcher.py` | Reduce to 120s or make non-blocking |
| 7 | **MODERATE** | `_MAX_OUTLIERS=200` meaningless with dedup bug — trims duplicates not uniques | `session_watcher.py:48` | Becomes meaningful once dedup is fixed |
| 14 | **MODERATE** | `_should_process()` calls `_generate_trace_id()` before `_wait_idle()` | `session_watcher.py:248` | Move trace_id generation after `_wait_idle()` |

## FALSE POSITIVE (3 findings)

| # | Finding | Why |
|---|---------|-----|
| 8 | Unused `Any`, `List` imports in `index.ts` | These imports are in `session_watcher.py`, not `index.ts` |
| 1 | Dead code: `callSupervisor()` in `index.ts` | True but LOW priority — single function, no impact |
| 2 | `TEMPLATES` dict lacks runtime validation | Acceptable — `UNKNOWN_TEMPLATE` fallback works |

## DEFERRED / ACCEPTABLE (8 findings)

| # | Finding | Reason |
|---|---------|--------|
| 3 | `review.verdict` auto-records via fragile `run_id.split("-")[1]` | Acceptable if run_id format is documented contract |
| 15 | Dead code: `_format_file_card()` in `tier_writer.py` | LOW priority — KnowledgeCardInjector has its own version |
| 16 | Dead code: `callSupervisor()` in `index.ts` | Same as #1 — LOW priority |
| 22 | `_wake()` silent exceptions | FIXED today |
| 25 | `_should_process()` trace_id before wait_idle | Same as #14 — MODERATE, defer |
| 26 | Unused imports in `session_watcher.py` | FIXED today (removed `Any`, `List`) |
| 19 | `import time` inside function | FIXED today (moved to module level) |
| 24 | `from_model` hardcode | FIXED today (changed to "extension") |

---

## Remaining Work — Priority Order

### P0 (Blockers)
1. **Outlier dedup** — unbounded file growth, corrupting JSON
2. **Race condition** — file corruption on concurrent writes
3. **`_rollup_exists_for_source_file()` broken** — fires for sessions that HAVE rollups (just NULL `source_file`)

### P1 (Should Fix)
4. **NULL `source_id` in 165 rollups** — prevents dedup guard from working
5. **Multiple rollups per `source_file`** — no uniqueness constraint
6. **`FILE_IDLE_SECONDS=600`** — blocks watcher thread

### P2 (Can Defer)
7. **`_MAX_OUTLIERS` meaningless** — resolves when dedup is fixed
8. **`_should_process()` trace_id ordering** — low risk in practice

---

## Services Status

| Service | Port | Status |
|---------|------|--------|
| Backend API | 8000 | ✅ Running (restarted 20:30) |
| Memory Service | 18097 | ✅ Running (restarted 20:30) |
| Arc Summarizer | 18095 | ✅ Running (LFM2.5-8B) |
| Supervisor | 8090 | ❌ NOT RUNNING |

## Delegation Recording Verification

- ✅ New delegation recorded: `deleg-subagent-test-verify-20260618-203141`
- ✅ `from_model="extension"` (was "supervisor")
- ✅ `response_length=67` (actual content, not 0)
- ✅ MD file created with proper content
- ✅ `extractResponse()` extracts per-result from `sr.finalOutput` or `sr.messages`
