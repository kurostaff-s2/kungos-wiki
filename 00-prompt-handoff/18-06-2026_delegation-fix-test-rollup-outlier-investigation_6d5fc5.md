# Delegation Hook Fix Verification + Rollup/Outlier Investigation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `6d5fc5` |
| Entity type | `handoff` |
| Short description | Verify subagent delegation recording fix; investigate watcher outlier growth and rollup gaps |
| Status | `in_progress` |
| Source references | Session compaction summary (2026-06-18), `session_watcher.py`, `council-tools/index.ts` |
| Generated | 18-06-2026 |
| Updated | 18-06-2026 (live codebase audit — 26 findings, 4 high, 8 moderate, 4 low) |
| Next action / owner | Pick up Phase 1 (verify delegation fix), then Phase 2 (outlier dedup), then Phase 3 (rollup gap) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Extension root:** `/home/chief/.pi/agent/extensions/council-tools/`
**Key files for this task:**
- `/home/chief/.pi/agent/extensions/council-tools/index.ts` — delegation hook (fixed, needs verification)
- `/home/chief/Coding-Projects/7-council/super_council/memory_service/ingest/session_watcher.py` — outlier logging (needs dedup)
- `/home/chief/Coding-Projects/7-council/super_council/api/council_delegations.py` — delegation API endpoint
- `/home/chief/Coding-Projects/7-council/super_council/memory_service/consolidate/scheduler.py` — consolidation scheduler (missing import)
**Council memory:** `~/.council-memory/`
**Outlier log:** `~/.council-memory/watcher-outliers.json` (corrupted, needs repair)
**DB:** `~/.council-memory/council_core.db`

**Service ports (hard constraint):**
- Backend API (`server.py`): **8000** — `/v1/council/delegations/*`, `/v1/council/recall`, `/v1/council/memory/*`, `/v1/council/review/*`, `/v1/council/pipeline/*`
- Supervisor (`council_main.py`): **8090** — `/v1/council/delegate`, `/v1/council/fanout`, `/v1/council/chain`, `/v1/council/summarize`, `/v1/council/chair-gate`, `/health`
- Memory service SSE: **18097**
- Arc summarizer: **18095**
- Llama-swap: **9292**

**Service status (live, 18-06-2026 20:08 IST):**
- ✅ Arc summarizer: running (LFM2.5-8B-A1B, port 18095)
- ✅ Memory service: running (MCP SSE, port 18097)
- ✅ Backend API: running (port 8000, health OK)
- ❌ Supervisor: **NOT RUNNING** (no `council_main.py` process, port 8090 dead)

---

## Phase 1: Verify Delegation Hook Fix

**What:** Confirm the three fixes in `council-tools/index.ts` work end-to-end. A subagent call should produce a delegation record with real agent name, task text, and response content.

**Files:** `/home/chief/.pi/agent/extensions/council-tools/index.ts`

**Three fixes on disk (verified by audit):**

| Fix | Before (broken) | After (fixed) | Line |
|---|---|---|---|
| Data extraction | `event.result.details.agent` → `undefined` → `"unknown"` | `event.details.results[i].agent` → real name | ~1000 |
| Dead async hook | `pi.events.on("subagent:async-complete")` — nobody emits this | Removed entirely | — |
| Port split | Single `BASE` defaulting to `8090` (wrong) | `SUPERVISOR_BASE` → 8090, `BACKEND_BASE` → 8000 | 175-178 |

**Steps:**

1. **Reload pi extension:** Run `/reload` in the pi TUI to pick up the updated `index.ts`.
2. **Fire a test subagent call:** Use `reviewer-gemma` or any configured agent with a short task (e.g., "Say hello and confirm you are running. Keep it under 30 words.").
3. **Check DB for new record:**
   ```python
   python3 -c "
   import sqlite3, os
   db = sqlite3.connect(os.path.expanduser('~/.council-memory/council_core.db'))
   db.row_factory = sqlite3.Row
   cur = db.cursor()
   cur.execute('''
       SELECT run_id, to_model, role, task, response_length, created_at
       FROM delegation_runs ORDER BY created_at DESC LIMIT 3
   ''')
   for r in cur.fetchall():
       print(dict(r))
   db.close()
   ```
4. **Verify fields are populated:**
   - `to_model` must NOT be `"unknown"` — should be the agent name (e.g., `reviewer-gemma`)
   - `task` must NOT be empty — should contain the actual task text
   - `response_length` must be > 0 — should contain actual output
   - `role` should be correctly derived from agent name (e.g., `"reviewer"`)
5. **Check the MD file exists:** The `md_file_path` in the DB should point to a real file under `~/.council-memory/reviews/`.

**Tests:**
- [ ] New delegation record appears in DB within 5 seconds of subagent completion
- [ ] `to_model` = actual agent name, NOT `"unknown"`
- [ ] `task` = actual task text, NOT empty string
- [ ] `response_length` > 0
- [ ] MD file exists at `md_file_path`
- [ ] Console log shows `[council] Subagent completed: agent=<name> success=true`

**Dependencies:** None (Phase 1 is independent).

### Phase 1 Audit Findings

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | **moderate** | `callSupervisor()` (line 784) is dead code — defined but never called | Remove the function |
| 2 | **low** | `TEMPLATES` dict has no runtime validation — typo in `template:name` returns `UNKNOWN_TEMPLATE` (acceptable but could be tighter) | Consider `Object.keys(TEMPLATES).includes(name)` with helpful error |
| 3 | **info** | `review.verdict` auto-records delegation by parsing `run_id.split("-")[1]` for alias — fragile if run_id format changes | Document format contract or use explicit reviewer param |

---

## Phase 2: Fix Outlier Deduplication + File Corruption

**What:** The outlier log (`~/.council-memory/watcher-outliers.json`) grows unbounded because the same files are logged every 5-minute scan cycle. Additionally, the file is corrupted due to a race condition in concurrent writes.

**Live evidence (18-06-2026):**
- File: 787 lines, 29KB, corrupted at line 782 (`]  {` pattern)
- Valid entries before corruption: **130**
- Unique `(trace_id, reason)` pairs: **12**
- Max duplicates per pair: **14x** (trace-a348d4aa logged 14 times)
- All 12 unique pairs share the same reason: `"in main dir, ingested, but no consolidation rollup exists"`

**Root causes (two bugs — confirmed):**

### Bug 2A: No deduplication guard

In `session_watcher.py`, `_log_outlier()` appends blindly every scan cycle. The condition `MD exists in main dir + raw_session in DB + no rollup` is **stable** — it doesn't change between scans. So the same `(trace_id, reason)` pair is logged every 300 seconds.

### Bug 2B: Race condition in file writes

`_log_outlier()` uses read-modify-write without locking:
```python
raw = self._outlier_file.read_text(...)  # Thread A reads
outliers = json.loads(raw)               # Thread A parses
# ... Thread B reads same content ...
outliers.append(...)                     # Thread A appends
tmp_path.write_text(json.dumps(outliers))  # Thread A writes [A, B]
tmp_path.rename(self._outlier_file)        # Thread A overwrites
# ... Thread B writes [A, B] too, corrupting with ]  { ...
```

**Evidence:** File contains `]  {` at line 782 — two JSON arrays concatenated. The `]` from one write followed by `{` from another.

**Steps:**

1. **Repair the corrupted outlier file:**
   ```python
   # Parse up to the first valid ], discard corruption after
   # Or just truncate and start fresh (outlier log is advisory only)
   ```

2. **Add deduplication guard to `_log_outlier()`:**
   - Before appending, check if `(trace_id, reason)` already exists in the outlier list
   - Use a composite key: `f"{trace_id}:{reason}"` in a set for O(1) lookup
   - Only append if the composite key is new
   - Alternative: add a `last_logged` timestamp per `(trace_id, reason)` and only re-log after a configurable interval (e.g., 1 hour)

3. **Fix race condition:**
   - Add a `threading.Lock()` specifically for outlier file writes (separate from `self._lock` which is for in-progress tracking)
   - Or use file locking (`fcntl.flock`) for cross-process safety
   - Or switch to append-only mode (one JSON object per line, no array wrapper) — simplest and most robust

4. **Consider append-only format (recommended):**
   ```json
   {"timestamp":"...","trace_id":"...","source_file":"...","reason":"..."}
   {"timestamp":"...","trace_id":"...","source_file":"...","reason":"..."}
   ```
   - Each line is a standalone JSON object (JSONL format)
   - Atomic writes via `os.write()` (single syscall, no read-modify-write)
   - Dedup via in-memory set of `(trace_id, reason)` pairs
   - No corruption possible even with concurrent writes

**File to modify:** `/home/chief/Coding-Projects/7-council/super_council/memory_service/ingest/session_watcher.py`

**Specific changes in `session_watcher.py`:**

| Location | Change |
|---|---|
| `_log_outlier()` method (line 208) | Add dedup check: skip if `(trace_id, reason)` already logged within cooldown window |
| `_log_outlier()` method (line 208) | Add `threading.Lock()` or switch to JSONL append-only format |
| `_OUTLIER_FILE` constant (line 46) | Consider renaming to `.jsonl` if switching format |
| `_MAX_OUTLIERS` constant (line 48) | Keep as cap, but implement via line-count trim instead of array trim |
| `_wake()` method (line 228) | Replace `except Exception: pass` with `except Exception as e: log.debug(...)` |
| Imports (line 30) | Remove unused `Any`, `List` from `typing` |

**Tests:**
- [ ] Run two scan cycles (or wait 5 minutes), verify same `(trace_id, reason)` is NOT logged twice
- [ ] Verify outlier file is valid JSON (or valid JSONL) after concurrent writes
- [ ] Verify file size doesn't grow unbounded (respects `_MAX_OUTLIERS` cap)
- [ ] Repair existing corrupted file

**Dependencies:** Phase 1 (verify delegation fix first, ensures no regression).

### Phase 2 Audit Findings

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 4 | **high** | `_log_outlier()` has NO dedup guard — same entries logged every 300s forever | Add `(trace_id, reason)` dedup set |
| 5 | **high** | `_wake()` swallows ALL exceptions silently (`except Exception: pass`) — no logging | Add `log.debug()` or `log.warning()` in except block |
| 6 | **moderate** | `FILE_IDLE_SECONDS = 600` (10 min) — `_wait_idle()` blocks the watcher thread per file. Multiple active sessions serialize processing | Consider reducing to 120s or making non-blocking |
| 7 | **moderate** | `_MAX_OUTLIERS = 200` is meaningless with dedup bug — trims old duplicates of same entries, no actual cap on unique tracking | Becomes meaningful once dedup is fixed |
| 8 | **low** | Unused imports: `Any`, `List` from `typing` (line 30) | Remove |

---

## Phase 3: Investigate Rollup Gaps

**What:** 18 of 73 raw session files have MD in `canonical-raw-session-data/` and records in `raw_session_memories`, but NO consolidation rollup exists in `memory_rollups`. Understand why and determine if this is expected or a bug.

**Background:**
- The consolidation pipeline (Arc A380, LFM2.5-8B-A1B on port 18095) processes raw session MD files into rollups
- Rollups are stored in `memory_rollups` table with `source_file` and `source_id` columns
- The `_rollup_exists_for_source_file()` check triggers the outlier log when no rollup exists
- **Critical: 165 of 248 daily rollups have `source_file = NULL` AND `trace_id = NULL`**

### Critical Discovery: Join Key Mismatch

The `_rollup_exists_for_source_file()` method queries:
```sql
SELECT source_id FROM memory_rollups
WHERE source_file = ? AND source_id IS NOT NULL LIMIT 1
```

But **165 daily rollups have `source_file = NULL`**. This means:
- Even though these sessions WERE consolidated, the check can NEVER find them
- Sessions are flagged as "no rollup" even though consolidation DID happen
- The outlier log fires for sessions that actually have rollups — just not findable by `source_file`

**Root cause:** The 165 NULL rollups were written by an older code path (before the `write_raw`/`_write_tier_output` split). When YAML parsing failed, only `write_raw()` was called (MD written, NO DB upsert). When later re-run, `_write_tier_output()` may have been called without `source_id`/`source_file` parameters.

### Live DB State (18-06-2026)

| Metric | Value |
|--------|-------|
| Total `raw_session_memories` | 73 |
| Total `memory_rollups` | 263 |
| Rollups with `source_file` | 83 |
| Rollups without `source_file` | 180 |
| Daily rollups with `source_id` | 83 |
| Daily rollups without `source_id` | 165 |
| Sessions without rollup (by `trace_id` join) | **18** (handoff said 15, grew by 3) |
| Multiple rollups per `source_file` | 13 files have 2-6 rollups each (max 6x) |

### Sessions Without Rollup (18 total)

| trace_id | source_file | created_at |
|----------|-------------|------------|
| trace-71343f2a | .../2026-06-18T14-35-30-000Z_.../session.jsonl | 2026-06-18T20:06:56 |
| trace-a9344e90 | .../2026-06-18T11-35-45-940Z_.../session.jsonl | 2026-06-18T20:04:31 |
| trace-d5749692 | .../2026-06-18T13-41-37-300Z_.../90eae3e2/run-0/session.jsonl | 2026-06-18T19:42:22 |
| trace-b461ac4b | .../2026-06-18T13-41-37-300Z_.../0cae4a86/run-0/session.jsonl | 2026-06-18T19:22:21 |
| trace-2c163162 | .../2026-06-18T13-41-37-300Z_.../session.jsonl | 2026-06-18T19:12:17 |
| trace-ac67b36a | .../2026-06-17T20-51-58-117Z_.../d091bd26/run-0/session.jsonl | 2026-06-18T18:02:59 |
| trace-62208f7b | .../2026-06-17T20-51-58-117Z_.../5877c64c/run-0/session.jsonl | 2026-06-18T18:02:58 |
| trace-6ceeda09 | .../2026-06-17T16-13-32-089Z_.../8a518e2d/run-0/session.jsonl | 2026-06-18T18:02:57 |
| trace-2ce1b086 | .../2026-06-17T16-13-32-089Z_.../217457e1/run-0/session.jsonl | 2026-06-18T18:02:56 |
| trace-549af104 | .../2026-06-17T16-13-32-089Z_.../3ce75edd/run-0/session.jsonl | 2026-06-18T18:02:54 |
| trace-ec3abdfa | .../2026-06-17T21-48-13-717Z_.../fab7f702/run-0/session.jsonl | 2026-06-18T18:02:53 |
| trace-c94bcda5 | .../2026-06-17T16-13-32-089Z_.../session.jsonl | 2026-06-18T18:02:52 |
| trace-6b9dbecb | .../2026-06-18T09-34-08-078Z_.../session.jsonl | 2026-06-18T18:02:49 |
| trace-a348d4aa | .../2026-06-17T22-41-01-332Z_.../session.jsonl | 2026-06-18T18:02:48 |
| trace-8146e6cb | .../2026-06-17T20-51-58-117Z_.../session.jsonl | 2026-06-18T18:02:45 |
| trace-555cce45 | .../2026-06-17T12-19-24-348Z_.../session.jsonl | 2026-06-18T18:02:36 |
| trace-f2a5c472 | .../2026-06-14T19-43-00-243Z_.../session.jsonl | 2026-06-15T20:19:33 |
| trace-85a9cdb8 | .../2026-06-13T09-28-06-185Z_.../session.jsonl | 2026-06-14T16:58:27 |

**Pattern:** Many are `run-0/session.jsonl` subagent sessions (nested paths). The oldest two (trace-f2a5c472, trace-85a9cdb8) are from June 13-14 and may have been processed before the current pipeline version.

**Steps:**

1. **Identify the 18 files without rollups:** (table above, already enumerated)

2. **For each file, check:**
   - Does the MD file exist in `~/.council-memory/canonical-raw-session-data/`?
   - Is the MD file complete (not a `.tmp` staging file)?
   - Is the file too large for the Arc summarizer's context window?
   - Was the consolidation pipeline running when the file was created?
   - Check Arc summarizer logs for errors on these specific files

3. **Check consolidation pipeline health:**
   - Arc summarizer: ✅ running (LFM2.5-8B-A1B, port 18095, healthy)
   - Memory service: ✅ running (MCP SSE, port 18097)
   - IdleWindowScheduler: ✅ waking on idle detection (logs show "5.0 min idle, triggering summarization")
   - **BUG: `_llm_capacity_available()` is DEAD** — missing `import json` in `scheduler.py` (line 356 calls `json.loads()` but `json` is never imported). Caught by bare `except Exception:` which returns `True` — the LLM capacity gate always passes.

4. **Determine if this is expected:**
   - Some sessions may be too new (consolidation runs on a schedule, not instantly)
   - Some may have failed consolidation (check Arc LLM logs at port 18095)
   - Some may be below the consolidation threshold (too short to warrant a rollup)
   - **165 daily rollups have NULL `source_id` — the dedup guard (`query_existing_rollup`) can't find them, risking unnecessary re-consolidation**

5. **Produce a report:**
   - How many are genuinely missing vs. just not yet processed
   - What's blocking the ones that should have been processed
   - Recommendation: trigger manual consolidation, fix pipeline, or accept as expected

**Tests:**
- [ ] List all 18 files with missing rollups
- [ ] For each: MD exists? complete? size? age?
- [ ] Arc summarizer health check (`curl http://127.0.0.1:18095/v1/models`)
- [ ] Consolidation pipeline logs checked for errors
- [ ] Report: count of genuinely missing vs. pending vs. expected
- [ ] Fix `import json` in `scheduler.py`

**Dependencies:** Phase 2 (fix outlier dedup first, so the investigation isn't polluted by new duplicate entries).

### Phase 3 Audit Findings

| # | Severity | File | Issue | Fix |
|---|----------|------|-------|-----|
| 10 | **high** | `session_watcher.py:190` | `_rollup_exists_for_source_file()` can NEVER find 165 daily rollups (all have `source_file = NULL`). Sessions flagged as "no rollup" even though consolidation DID happen. | Also check by `trace_id` or `source_id`, not just `source_file` |
| 11 | **high** | `scheduler.py:356` | **Missing `import json`.** `_llm_capacity_available()` calls `json.loads()` but `json` is never imported. Caught by bare `except Exception:` → returns `True`. LLM capacity gate is DEAD. | Add `import json` to imports (line 15) |
| 12 | **moderate** | `pipeline.py` | 165 daily rollups have `source_id = NULL`. Dedup guard (`query_existing_rollup(tier="daily", source_id=...)`) can't find them. Sessions could be re-consolidated unnecessarily. | Backfill `source_id` from MD headers or accept as legacy data |
| 13 | **moderate** | `memory_rollups` | Multiple rollups per `source_file` (up to 6x). No uniqueness constraint on `(source_file, tier)`. | Add unique constraint or investigate re-processing root cause |
| 14 | **low** | DB schema | `source_id` non-uniqueness: 70 files map to 63 unique UUIDs (sub-runs inherit parent UUID). Affects rollup queries that assume uniqueness. | Document or add `(source_id, tier)` unique constraint with conflict resolution |

---

## Dead Code Across Codebase

| # | File | Line | Dead Code | Action |
|---|------|------|-----------|--------|
| 15 | `index.ts` | 784 | `callSupervisor()` — defined, never called (1 occurrence = definition only) | Remove |
| 16 | `tier_writer.py` | 368 | `_format_file_card()` — defined but never called (KnowledgeCardInjector has its own version) | Remove |
| 17 | `council_delegations.py` | 174-175 | Duplicate imports: `import os` and `from pathlib import Path` inside `handle_record_delegation()` (already at module level lines 13-14) | Remove function-level imports |
| 18 | `council_delegations.py` | 163 | `import time` inside function (needed in function but inconsistent with module-level style) | Move to module-level import |

---

## Things Needing Tightening

| # | Severity | File | Issue | Fix |
|---|----------|------|-------|-----|
| 19 | **high** | `scheduler.py:15-20` | Missing `import json` — LLM capacity check is dead | Add `import json` |
| 20 | **high** | `session_watcher.py:208` | No dedup in `_log_outlier()` — unbounded growth | Add `(trace_id, reason)` dedup set |
| 21 | **high** | `session_watcher.py:208` | Race condition in file writes | Add `threading.Lock()` or switch to JSONL |
| 22 | **moderate** | `session_watcher.py:228` | `_wake()` swallows exceptions silently | Add `log.debug()` in except block |
| 23 | **moderate** | `pipeline.py:409,413` | **Duplicate log statement:** Two consecutive `log.info("Sequential: %s complete (%d parts moved to processed/)")` — first logs `moved` count, second logs `len(parts)`. Confusing. | Remove one |
| 24 | **moderate** | `council_delegations.py:194` | `from_model="supervisor"` is hardcoded. Subagent delegations come from the extension (not supervisor). | Use `from_model="extension"` or derive from actual caller |
| 25 | **moderate** | `session_watcher.py:248` | `_should_process()` calls `_generate_trace_id()` which reads JSONL header before `_wait_idle()`. If JSONL is still being written, header read could fail or return partial data. | Move trace_id generation after `_wait_idle()` |
| 26 | **low** | `session_watcher.py:30` | Unused `Any`, `List` imports | Remove |

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Verify | `~/.pi/agent/extensions/council-tools/index.ts` | Delegation hook fixes (Phase 1) |
| Modify | `~/Coding-Projects/7-council/super_council/memory_service/ingest/session_watcher.py` | Outlier dedup + race condition fix (Phase 2) |
| Modify | `~/Coding-Projects/7-council/super_council/memory_service/consolidate/scheduler.py` | Missing `import json` (Phase 3) |
| Modify | `~/Coding-Projects/7-council/super_council/memory_service/consolidate/pipeline.py` | Duplicate log statement (audit finding) |
| Modify | `~/Coding-Projects/7-council/super_council/api/council_delegations.py` | Duplicate imports, `from_model` hardcode (audit finding) |
| Modify | `~/Coding-Projects/7-council/super_council/memory_service/consolidate/tier_writer.py` | Dead `_format_file_card()` (audit finding) |
| Repair | `~/.council-memory/watcher-outliers.json` | Corrupted outlier file (Phase 2) |
| Query | `~/.council-memory/council_core.db` | Rollup gap investigation (Phase 3) |
| Check | `~/.council-memory/canonical-raw-session-data/` | MD file existence for rollup gap (Phase 3) |

---

## Constraints

- **No raw SQL from agents:** All DB queries in this handoff are for human investigation. Agent-accessible tools must use `recall.*` MCP tools.
- **Server ports are fixed:** Backend = 8000, Supervisor = 8090. Do not change these without updating all references.
- **Outlier log is advisory only:** It's a debugging artifact. Losing historical entries during repair is acceptable.
- **Extension reload required:** Any changes to `index.ts` require `/reload` in pi TUI to take effect.
- **Supervisor may not be running:** `council_main.py` (port 8090) is NOT running. Only backend (8000) endpoints are guaranteed available. The delegation recording endpoint (Phase 1) uses the backend (8000), which IS running.
- **`_rollup_exists_for_source_file()` is broken for 165 rollups:** These have `source_file = NULL`. Any fix to the outlier log must account for this — the check will always return False for sessions consolidated before the `source_file` field was populated.

---

## Success Criteria

- [ ] Phase 1: Subagent delegation records appear in DB with correct `agent`, `task`, `response` fields
- [ ] Phase 1: No `"unknown"` agent names in new delegation records
- [ ] Phase 2: Outlier dedup prevents same `(trace_id, reason)` from logging twice within cooldown window
- [ ] Phase 2: Outlier file is valid format (no `] {...} ]` corruption)
- [ ] Phase 2: Outlier file size respects `_MAX_OUTLIERS` cap
- [ ] Phase 3: Report produced identifying why 18 files lack rollups (missing/pending/expected)
- [ ] Phase 3: Arc summarizer health verified
- [ ] Audit: `import json` added to `scheduler.py`
- [ ] Audit: Dead code removed (`callSupervisor`, `_format_file_card`, duplicate imports)
- [ ] Audit: `_wake()` logs exceptions instead of swallowing silently
- [ ] Audit: Duplicate log statement removed from `pipeline.py`
- [ ] All existing functionality preserved (no regression in watcher processing, delegation recording, or consolidation pipeline)

---

## Caveats & Uncertainty

1. **Supervisor availability:** `council_main.py` (port 8090) is NOT running. If `/council-delegate` or `/council-chain` commands are needed, the supervisor must be started first. The delegation recording endpoint (Phase 1) uses the backend (8000), which IS running.

2. **Outlier file format change:** Switching from JSON array to JSONL is a breaking change for any consumer of the outlier file. If nothing reads it programmatically (it's advisory/debugging only), this is safe.

3. **Rollup timing:** Consolidation may not be instantaneous. Some "missing" rollups may just be pending the next consolidation cycle. The investigation should distinguish between genuinely failed and not-yet-processed.

4. **Source ID vs trace_id:** The DB uses `source_file` as the join key between `raw_session_memories` and `memory_rollups`. The `source_id` (UUID) is NOT unique because sub-runs inherit the parent's UUID (70 files map to 63 unique UUIDs). This was documented in the session summary but may affect rollup queries.

5. **Reprocess counts reset on restart:** The `_reprocess_counts` dict is in-memory only. After `watch.service` restarts, reprocess counts reset to 0, potentially allowing reprocessing of files that were already at the limit.

6. **165 legacy rollups with NULL metadata:** These were written by an older pipeline version. The dedup guard (`query_existing_rollup`) and outlier check (`_rollup_exists_for_source_file`) can't find them. Either backfill `source_id`/`source_file` from MD headers, or accept these as legacy data that won't be re-processed (since the MD files are already in `processed/`).

7. **`_wait_idle` blocks the watcher thread:** With `FILE_IDLE_SECONDS = 600`, a single active session can block the entire watcher for 10 minutes. If multiple sessions are active, processing is serialized. Consider reducing this or making it non-blocking.

8. **Multiple rollups per source_file:** 13 source_files have 2-6 rollups each. This could be from re-processing (session grew, triggered re-consolidation) or a bug in the dedup guard. Investigate whether the `source_id`-based dedup in `_process_raw_sessions_sequentially` is working correctly.
