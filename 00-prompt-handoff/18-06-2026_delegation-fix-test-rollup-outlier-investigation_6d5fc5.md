# Delegation Hook Fix Verification + Rollup/Outlier Investigation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `6d5fc5` |
| Entity type | `handoff` |
| Short description | Verify subagent delegation recording fix; investigate watcher outlier growth and rollup gaps |
| Status | `draft` |
| Source references | Session compaction summary (2026-06-18), `session_watcher.py`, `council-tools/index.ts` |
| Generated | 18-06-2026 |
| Next action / owner | Pick up Phase 1 (verify delegation fix), then Phase 2 (outlier dedup), then Phase 3 (rollup gap) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Extension root:** `/home/chief/.pi/agent/extensions/council-tools/`
**Key files for this task:**
- `/home/chief/.pi/agent/extensions/council-tools/index.ts` — delegation hook (fixed, needs verification)
- `/home/chief/Coding-Projects/7-council/super_council/memory_service/ingest/session_watcher.py` — outlier logging (needs dedup)
- `/home/chief/Coding-Projects/7-council/super_council/api/council_delegations.py` — delegation API endpoint
**Council memory:** `~/.council-memory/`
**Outlier log:** `~/.council-memory/watcher-outliers.json` (corrupted, needs repair)
**DB:** `~/.council-memory/council_core.db`

**Service ports (hard constraint):**
- Backend API (`server.py`): **8000** — `/v1/council/delegations/*`, `/v1/council/recall`, `/v1/council/memory/*`, `/v1/council/review/*`, `/v1/council/pipeline/*`
- Supervisor (`council_main.py`): **8090** — `/v1/council/delegate`, `/v1/council/fanout`, `/v1/council/chain`, `/v1/council/summarize`, `/v1/council/chair-gate`, `/health`
- Memory service SSE: **18097**
- Arc summarizer: **18095**
- Llama-swap: **9292**

---

## Phase 1: Verify Delegation Hook Fix

**What:** Confirm the three fixes in `council-tools/index.ts` work end-to-end. A subagent call should produce a delegation record with real agent name, task text, and response content.

**Files:** `/home/chief/.pi/agent/extensions/council-tools/index.ts`

**Three fixes on disk (not yet verified):**

| Fix | Before (broken) | After (fixed) |
|---|---|---|
| Data extraction | `event.result.details.agent` → `undefined` → `"unknown"` | `event.details.results[i].agent` → real name |
| Dead async hook | `pi.events.on("subagent:async-complete")` — nobody emits this | Removed entirely |
| Port split | Single `BASE` defaulting to `8090` (wrong) | `SUPERVISOR_BASE` → 8090, `BACKEND_BASE` → 8000 |

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

---

## Phase 2: Fix Outlier Deduplication + File Corruption

**What:** The outlier log (`~/.council-memory/watcher-outliers.json`) grows unbounded because the same files are logged every 5-minute scan cycle. Additionally, the file is corrupted due to a race condition in concurrent writes.

**Root causes (two bugs):**

### Bug 2A: No deduplication guard

In `session_watcher.py`, `_log_outlier()` appends blindly every scan cycle. The condition `MD exists in main dir + raw_session in DB + no rollup` is stable — it doesn't change between scans. So the same `(trace_id, reason)` pair is logged every 300 seconds.

**Evidence:** The outlier file has ~780 entries. Many entries repeat the same `trace_id` + `reason` combination at 5-minute intervals.

### Bug 2B: Race condition in file writes

`_log_outlier()` uses read-modify-write without locking:
```python
raw = self._outlier_file.read_text(...)  # Thread A reads
outliers = json.loads(raw)               # Thread A parses
# ... Thread B reads same content ...
outliers.append(...)                     # Thread A appends
tmp_path.write_text(json.dumps(outliers))  # Thread A writes [A, B]
tmp_path.rename(self._outlier_file)        # Thread A overwrites with [A, B]
# ... Thread B writes [A, B] too, overwriting A's work ...
```

**Evidence:** File contains `] {...} ]` — two JSON arrays concatenated. The `]` from one write followed by `{` from another.

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
| `_log_outlier()` method | Add dedup check: skip if `(trace_id, reason)` already logged within cooldown window |
| `_log_outlier()` method | Add `threading.Lock()` or switch to JSONL append-only format |
| `_OUTLIER_FILE` constant | Consider renaming to `.jsonl` if switching format |
| `_MAX_OUTLIERS` constant | Keep as cap, but implement via line-count trim instead of array trim |

**Tests:**
- [ ] Run two scan cycles (or wait 5 minutes), verify same `(trace_id, reason)` is NOT logged twice
- [ ] Verify outlier file is valid JSON (or valid JSONL) after concurrent writes
- [ ] Verify file size doesn't grow unbounded (respects `_MAX_OUTLIERS` cap)
- [ ] Repair existing corrupted file

**Dependencies:** Phase 1 (verify delegation fix first, ensures no regression).

---

## Phase 3: Investigate Rollup Gaps

**What:** 15 of 70 raw session files have MD in `canonical-raw-session-data/` and records in `raw_session_memories`, but NO consolidation rollup exists in `memory_rollups`. Understand why and determine if this is expected or a bug.

**Background:**
- The consolidation pipeline (Arc A380, Granite-4.1-3B on port 18095) processes raw session MD files into rollups
- Rollups are stored in `memory_rollups` table with `source_file` and `source_id` columns
- The `_rollup_exists_for_source_file()` check triggers the outlier log when no rollup exists

**Steps:**

1. **Identify the 15 files without rollups:**
   ```python
   python3 -c "
   import sqlite3, os
   db = sqlite3.connect(os.path.expanduser('~/.council-memory/council_core.db'))
   db.row_factory = sqlite3.Row
   cur = db.cursor()
   cur.execute('''
       SELECT rsm.source_file, rsm.trace_id, rsm.source_id, rsm.created_at
       FROM raw_session_memories rsm
       LEFT JOIN memory_rollups mr ON rsm.source_file = mr.source_file
       WHERE mr.source_id IS NULL
       ORDER BY rsm.created_at DESC
   ''')
   for r in cur.fetchall():
       print(f'{r[\"trace_id\"]} | {r[\"source_id\"]} | {r[\"source_file\"]} | {r[\"created_at\"]}')
   db.close()
   ```

2. **For each file, check:**
   - Does the MD file exist in `~/.council-memory/canonical-raw-session-data/`?
   - Is the MD file complete (not a `.tmp` staging file)?
   - Is the file too large for the Arc summarizer's context window?
   - Was the consolidation pipeline running when the file was created?
   - Check Arc summarizer logs for errors on these specific files

3. **Check consolidation pipeline health:**
   - Is `arc-summarizer.service` running? (`systemctl --user status arc-summarizer.service`)
   - Is the IdleWindowScheduler waking properly after session processing?
   - Check `~/.council-memory/` for consolidation error logs

4. **Determine if this is expected:**
   - Some sessions may be too new (consolidation runs on a schedule, not instantly)
   - Some may have failed consolidation (check Arc LLM logs at port 18095)
   - Some may be below the consolidation threshold (too short to warrant a rollup)

5. **Produce a report:**
   - How many are genuinely missing vs. just not yet processed
   - What's blocking the ones that should have been processed
   - Recommendation: trigger manual consolidation, fix pipeline, or accept as expected

**Tests:**
- [ ] List all 15 files with missing rollups
- [ ] For each: MD exists? complete? size? age?
- [ ] Arc summarizer health check (`curl http://127.0.0.1:18095/v1/models`)
- [ ] Consolidation pipeline logs checked for errors
- [ ] Report: count of genuinely missing vs. pending vs. expected

**Dependencies:** Phase 2 (fix outlier dedup first, so the investigation isn't polluted by new duplicate entries).

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Verify | `~/.pi/agent/extensions/council-tools/index.ts` | Delegation hook fixes (Phase 1) |
| Modify | `~/Coding-Projects/7-council/super_council/memory_service/ingest/session_watcher.py` | Outlier dedup + race condition fix (Phase 2) |
| Repair | `~/.council-memory/watcher-outliers.json` | Corrupted outlier file (Phase 2) |
| Query | `~/.council-memory/council_core.db` | Rollup gap investigation (Phase 3) |
| Check | `~/.council-memory/canonical-raw-session-data/` | MD file existence for rollup gap (Phase 3) |

---

## Constraints

- **No raw SQL from agents:** All DB queries in this handoff are for human investigation. Agent-accessible tools must use `recall.*` MCP tools.
- **Server ports are fixed:** Backend = 8000, Supervisor = 8090. Do not change these without updating all references.
- **Outlier log is advisory only:** It's a debugging artifact. Losing historical entries during repair is acceptable.
- **Extension reload required:** Any changes to `index.ts` require `/reload` in pi TUI to take effect.
- **Supervisor may not be running:** Port 8090 may refuse connections if `council_main.py` isn't started. Only backend (8000) endpoints are guaranteed available.

---

## Success Criteria

- [ ] Phase 1: Subagent delegation records appear in DB with correct `agent`, `task`, `response` fields
- [ ] Phase 1: No `"unknown"` agent names in new delegation records
- [ ] Phase 2: Outlier dedup prevents same `(trace_id, reason)` from logging twice within cooldown window
- [ ] Phase 2: Outlier file is valid format (no `] {...} ]` corruption)
- [ ] Phase 2: Outlier file size respects `_MAX_OUTLIERS` cap
- [ ] Phase 3: Report produced identifying why 15 files lack rollups (missing/pending/expected)
- [ ] Phase 3: Arc summarizer health verified
- [ ] All existing functionality preserved (no regression in watcher processing, delegation recording, or consolidation pipeline)

---

## Caveats & Uncertainty

1. **Supervisor availability:** `council_main.py` (port 8090) may not be running. If `/council-delegate` or `/council-chain` commands are needed, the supervisor must be started first. The delegation recording endpoint (Phase 1) uses the backend (8000), which IS running.

2. **Outlier file format change:** Switching from JSON array to JSONL is a breaking change for any consumer of the outlier file. If nothing reads it programmatically (it's advisory/debugging only), this is safe.

3. **Rollup timing:** Consolidation may not be instantaneous. Some "missing" rollups may just be pending the next consolidation cycle. The investigation should distinguish between genuinely failed and not-yet-processed.

4. **Source ID vs trace_id:** The DB uses `source_file` as the join key between `raw_session_memories` and `memory_rollups`. The `source_id` (UUID) is NOT unique because sub-runs inherit the parent's UUID (70 files map to 63 unique UUIDs). This was documented in the session summary but may affect rollup queries.

5. **Reprocess counts reset on restart:** The `_reprocess_counts` dict is in-memory only. After `watch.service` restarts, reprocess counts reset to 0, potentially allowing reprocessing of files that were already at the limit.
