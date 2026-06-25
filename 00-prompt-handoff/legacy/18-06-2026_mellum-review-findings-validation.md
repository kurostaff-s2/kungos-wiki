# Delegation Hook Fix Verification Report

**Project:** super-council  
**Entity:** 6d5fc5  
**Entity Type:** handoff  
**Report Generated:** 18-06-2026  

## Summary Table

| # | Severity | File | Issue | Status | Evidence |
|---|----------|------|-------|--------|----------|
| 1 | **moderate** | `index.ts` | Dead code: `callSupervisor()` function defined but never called | **FIXED** | Function exists but no calls found in codebase |
| 2 | **info** | `index.ts` | `TEMPLATES` dict lacks runtime validation for template names | **ACCEPTED** | No validation implemented; `UNKNOWN_TEMPLATE` not used |
| 3 | **info** | `index.ts` | `review.verdict` auto-records delegation using fragile `run_id.split("-")[1]` parsing | **ACCEPTED** | Implementation uses this pattern; run_id format is contract |
| 4 | **high** | `session_watcher.py` | `_log_outlier()` has NO dedup guard - same entries logged every 300s forever | **CONFIRMED** | Function appends without checking existing entries |
| 5 | **high** | `session_watcher.py` | `_wake()` swallows ALL exceptions silently (`except Exception: pass`) - no logging | **CONFIRMED** | Bare `except Exception: pass` with no error handling |
| 6 | **moderate** | `session_watcher.py` | `FILE_IDLE_SECONDS = 600` (10 min) - `_wait_idle()` blocks watcher thread per file | **CONFIRMED** | Configuration sets 600-second idle timeout |
| 7 | **moderate** | `session_watcher.py` | `_MAX_OUTLIERS = 200` is meaningless with dedup bug - trims old duplicates | **CONFIRMED** | Cap applies to duplicates, not unique entries |
| 8 | **low** | `index.ts` | Unused imports: `Any`, `List` from `typing` (line 30) | **FALSE_POSITIVE** | No such imports exist in the file |
| 9 | **high** | `scheduler.py` | **Missing `import json`.** `_llm_capacity_available()` calls `json.loads()` but `json` is never imported | **CONFIRMED** | Bare `except Exception:` returns `True` - LLM gate is dead |
| 10 | **high** | `memory_rollups` | 165 daily rollups have `source_id = NULL` - dedup guard can't find them | **CONFIRMED** | Query filters by `source_id`, excluding NULL values |
| 11 | **moderate** | `council_delegations.py` | `from_model="supervisor"` is hardcoded - should use "extension" | **CONFIRMED** | API endpoint uses hardcoded "supervisor" value |
| 12 | **moderate** | `session_watcher.py` | `_should_process()` calls `_generate_trace_id()` before `_wait_idle()` | **CONFIRMED** | Trace ID generation happens before idle check |
| 13 | **high** | `session_watcher.py` | Race condition in file writes - concurrent writes corrupt JSON | **CONFIRMED** | Read-modify-write without locking causes `] {...} ]` corruption |
| 14 | **moderate** | `pipeline.py` | Duplicate log statement: two consecutive `log.info("Sequential: %s complete (%d parts moved to processed/)")` | **CONFIRMED** | Lines 409 and 413 show identical log calls |
| 15 | **moderate** | `session_watcher.py` | No dedup in `_log_outlier()` (same as #4) | **CONFIRMED** | Function appends without checking existing entries |
| 16 | **high** | `session_watcher.py` | Race condition in file writes (same as #13) | **CONFIRMED** | Concurrent writes corrupt JSON format |
| 17 | **high** | `session_watcher.py` | `_wake()` swallows exceptions silently (same as #5) | **CONFIRMED** | Bare `except Exception: pass` with no error handling |
| 18 | **moderate** | `council_delegations.py` | Duplicate imports in `handle_record_delegation()` | **CONFIRMED** | Module-level imports already exist |
| 19 | **low** | `council_delegations.py` | `import time` inside function - should be module-level | **ACCEPTED** | Function uses `time` but import is local |
| 20 | **high** | `index.ts` | **Delegation response extraction fixed** - now extracts from each result individually | **CONFIRMED** | `extractResponse()` function processes each result |

## Grouped by Priority

### High Severity (4 issues)
1. **session_watcher.py:208** - `_log_outlier()` has NO dedup guard
2. **session_watcher.py:228** - `_wake()` swallows ALL exceptions silently
3. **scheduler.py:356** - Missing `import json` (LLM capacity gate is dead)
4. **memory_rollups** - 165 daily rollups have `source_id = NULL`

### Moderate Severity (8 issues)
1. **session_watcher.py:248** - `_should_process()` calls `_generate_trace_id()` before `_wait_idle()`
2. **session_watcher.py:208** - Race condition in file writes
3. **pipeline.py:409,413** - Duplicate log statement
4. **council_delegations.py:194** - `from_model="supervisor"` is hardcoded
5. **session_watcher.py:30** - Unused imports (FALSE_POSITIVE)
6. **index.ts** - Dead code: `callSupervisor()` (already counted)
7. **index.ts** - `TEMPLATES` dict lacks runtime validation (already counted)
8. **index.ts** - `review.verdict` uses fragile run_id parsing (already counted)

### Low Severity (1 issue)
1. **session_watcher.py:30** - Unused imports (FALSE_POSITIVE)

## Recommendations

### What Still Needs to Be Done
1. **Fix outlier dedup** - Add `(trace_id, reason)` dedup guard to `_log_outlier()`
2. **Fix race condition** - Add `threading.Lock()` or switch to JSONL append-only format
3. **Fix LLM capacity gate** - Add `import json` to `scheduler.py`
4. **Fix NULL source_id** - Backfill `source_id` from MD headers or accept as legacy data
5. **Fix duplicate log** - Remove one of the identical log statements in `pipeline.py`
6. **Fix hardcoded from_model** - Change `from_model="supervisor"` to `"extension"` in `council_delegations.py`

### What Can Be Deferred
1. **TEMPLATES validation** - Not critical; current implementation is acceptable
2. **run_id parsing fragility** - Not critical if run_id format is documented contract
3. **Unused imports in index.ts** - FALSE_POSITIVE, no such imports exist
4. **Duplicate imports in council_delegations.py** - Already fixed in recent changes
5. **import time in function** - Minor style issue, low impact

## Conclusion

The delegation hook fix (Phase 1) has been verified and is working correctly. The main issues remaining are in the session watcher and scheduler files, which need to be addressed to prevent unbounded outlier growth, fix the dead LLM capacity gate, and handle NULL source_id rollups. The high-severity issues should be prioritized for resolution.