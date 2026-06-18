# Consolidation Pipeline — Production Hardening

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `b653b6` (memory-pipeline-audit) |
| Entity type | `handoff` |
| Short description | Single-owner, single-task-at-a-time consolidation pipeline with DB-tracked completion, error flagging, KV-cache-safe token budgets, and no duplicate pipelines |
| Status | `draft` |
| Source references | See "Project Context" below |
| Generated | 19-06-2026 |
| Next action / owner | Execute Phase 1 (LLM Queue hardening) → Phase 2 (Scheduler + lifecycle DB) → Phase 3 (Config + performance) → Phase 4 (Verification) |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`

**Key files for this task:**

| File | Role |
|------|------|
| `memory_service/consolidate/llm_queue.py` | Single-threaded LLM request queue (core serialization point) |
| `memory_service/consolidate/client.py` | ArcClient — HTTP client, routes through queue |
| `memory_service/consolidate/pipeline.py` | ArcPipeline — sequential session processing, tiered consolidation |
| `memory_service/consolidate/scheduler.py` | IdleWindowScheduler — adaptive consolidation triggers |
| `memory_service/consolidate/config.py` | ArcConfig — token limits, retries, timeouts |
| `memory_service/consolidate/tier_gatherer.py` | Input gathering for non-daily tiers |
| `memory_service/consolidate/tier_writer.py` | Output writing + DB upsert |
| `memory_service/ingest/session_watcher.py` | JSONL → MD ingestion, lifecycle DB updates |
| `memory_service/store/session_store.py` | `session_lifecycle` table, upsert/finalize |
| `council_main.py` | Council supervisor (consolidation disabled, line 8956) |

**Database:** `/home/chief/.council-memory/council_core.db` (SQLite, contains `session_lifecycle` table)

**Systemd services:**
- `arc-summarizer.service` — `llama-server` on port 18095 (LFM2.5-8B-A1B-UD-Q4_K_XL, Intel A380 SYCL)
- `memory-service.service` — FastAPI server on port 18098 (owns consolidation exclusively)
- `council-backend.service` — REST API on port 18099
- `council-supervisor.service` — council_main.py on port 8090 (consolidation disabled)

---

## Problem Statement

The consolidation pipeline has **five production-readiness gaps** that cause silent failures, data loss, and hours-long processing blackouts:

### Gap 1: Duplicate Pipeline Owners

**Current:** `council_main.py` (PID 208706) and `memory-service` (PID 317112) both have `ArcPipeline` instances. Both submit to the same LLM. When one restarts, the other's requests collide.

**Evidence:** `council_main.py` submitted `consolidation-daily` requests (tasks 78, 79) that failed with HTTP 500 after LLM restart. The memory service's startup catch-up was skipped because the LLM was "busy" (from council_main's requests).

**Impact:** Unpredictable failures, wasted GPU time, no clear ownership boundary.

**Fix:** council_main's `_init_arc_summarizer()` already disabled (line 8956). **Permanent fix:** Remove `ArcSummarizer` import and `self._arc` attribute from council_main entirely. Document the ownership boundary.

---

### Gap 2: KV Cache Exhaustion → Token Generation at <1 tok/s

**Current:** `consolidation_max_tokens = 8192`. A380 SYCL backend generates at **0.58 tok/s** under KV cache pressure. Each session takes ~2.4 hours instead of ~7 minutes.

**Evidence:** LLM timing logs show `tg = 0.58 t/s` and `tg = 0.81 t/s` for tasks 133 and 159 (both generating ~8K tokens simultaneously).

**Root cause:** Two tasks in the KV cache simultaneously (tasks 133 + 159). The A380 has limited VRAM. When both tasks hold ~16K prompt tokens + ~8K generation tokens each, the cache overflows and the GPU falls back to CPU-backed computation.

**Impact:** 20 sessions × 2.4 hours = 48 hours total. Pipeline appears "stuck" for hours.

**Fix:** Three-part:
1. **Hard-enforce single-task-in-flight:** The queue already serializes, but the LLM can hold multiple tasks in KV cache. After each request completes, explicitly cancel all other tasks via slot erase (see Cancellation Mechanism below).
2. **Reduce `consolidation_max_tokens` to 4096** (or configurable per-tier). Daily tier needs ~2K output, not 8K.
3. **Add KV cache monitoring:** If `tg < 5 tok/s` for >60s, cancel current task, clear cache, retry with smaller prompt.

---

### Gap 3: No DB-Backed Request Tracking

**Current:** The LLM queue uses in-memory `Future` objects. No DB record of which session is being consolidated, what state it's in, or what error occurred.

**Evidence:** When the memory service was killed (PID 269150 → 300330), all in-flight requests were lost. The `session_lifecycle` table had no `error` column to record partial failures. The queue worker blocked on `future.result(timeout=1260)` for 20 minutes waiting for responses from dead processes.

**Impact:** No visibility into pipeline state. No recovery from partial failures. No audit trail.

**Fix:** Add a `consolidation_requests` table. Use `source_file` as the canonical primary key — same PK as `session_lifecycle` and FK in `memory_rollups`. One key, zero confusion.

```sql
CREATE TABLE IF NOT EXISTS consolidation_requests (
    source_file TEXT PRIMARY KEY,       -- same PK as session_lifecycle
    tier_id TEXT NOT NULL,              -- daily/short/weekly/bimonthly
    status TEXT NOT NULL DEFAULT 'queued',  -- queued, submitted, generating, complete, failed, cancelled
    submitted_at TEXT,
    completed_at TEXT,
    llama_task_id INTEGER,
    error TEXT,
    output_rollup_id TEXT,
    UNIQUE(source_file, tier_id)        -- one active request per file+tier
);
```

**Canonical key chain:**
```
session_lifecycle.source_file  =PK=  consolidation_requests.source_file  =FK=  memory_rollups.source_file
```

For higher tiers (short/weekly/bimonthly) that consolidate multiple rollups into one, use synthetic key `batch:<tier>:<date>` (e.g., `batch:short:2026-06-18`). Same column, same mental model.

Every queue submission writes a row. On completion/failure, update status + error. The scheduler queries this table instead of filesystem glob.

---

### Gap 4: SessionWatcher Reprocessing Same Files

**Current:** SessionWatcher polls every 300 seconds. It reprocesses the same JSONL file even when the MD already exists and `session_lifecycle` shows `md_written=1`.

**Evidence:** Logs show `trace-a9344e90` processed at 00:00:39, 00:05:41, and 00:10:43. Each reprocessing calls `store.upsert_raw_session_memory()` which re-reads the 2.7MB JSONL, re-extracts conversation, and re-writes the MD files.

**Root cause:** The `_should_process` guard checks `_md_exists_anywhere(trace_id)`. If the MD file exists, it checks JSONL mtime. But the JSONL mtime can change (e.g., touched by filesystem operations), causing reprocessing. Additionally, the guard doesn't check `session_ended=1` in `session_lifecycle`.

**Impact:** Wasted CPU, unnecessary DB writes, potential race conditions with consolidation pipeline.

**Fix:** Strengthen the guard:
1. If `session_lifecycle` has `md_written=1 AND session_ended=1` → skip unconditionally.
2. If MD file exists AND `session_lifecycle.updated_at` is recent (<5 min) → skip.
3. Add a cooldown: if same file was processed within last 600 seconds → skip.

---

### Gap 5: Queue Worker Blocks Indefinitely on Dead LLM

**Current:** `_worker_loop` calls `future.result(timeout=1260)` (21 minutes). If the LLM dies or the connection drops, the worker blocks for the full timeout.

**Evidence:** Queue worker (PID 300330) blocked since 23:42:39 waiting for response to seq=1. Expected timeout ~24:03:39. All GPU slots consumed by orphaned tasks.

**Impact:** Pipeline completely stalls until timeout expires. No fail-fast mechanism.

**Fix:** Pre-submit health check + maintain 1200s timeout for active generations:
1. **Before submitting:** `GET /v1/models` with 3-second timeout. If unreachable → fail fast, don't submit. Prevents orphaned requests to dead LLM.
2. **After submitting:** Keep 1200s timeout (matches A380's long prompt processing times). The LLM is healthy at submit time, so let it run.
3. **On timeout:** Mark `consolidation_requests.status = 'failed'` with error message. Connection close triggers server-side `SERVER_TASK_TYPE_CANCEL`.
4. **Rationale:** Reducing timeouts causes premature cancellation of valid long prompts. Pre-submit check catches the actual problem (dead LLM) before it wastes GPU time.

---

## Execution Order

```
Phase 1 (LLM Queue hardening) ──→ Phase 2 (Scheduler + lifecycle DB) ──→ Phase 3 (Config + performance) ──→ Phase 4 (Verification)
```

**Phases 1-3 are sequential.** Phase 4 validates all changes end-to-end.

---

## Phase 1: LLM Queue Hardening

**What:** Make the LLM queue production-ready: single-task-in-flight guarantee, explicit task cancellation, DB-backed request tracking, fail-fast on dead LLM.

**Files:**
- Modify: `memory_service/consolidate/llm_queue.py`
- Modify: `memory_service/consolidate/client.py`
- Modify: `memory_service/store/session_store.py` (add `consolidation_requests` table)

**Steps:**

1. **Add `consolidation_requests` table to `session_store.py`:**
   - Create table with schema above (Gap 3). `source_file` is the canonical PK.
   - Add `upsert_consolidation_request(source_file, tier_id, status, **kwargs)` method.
   - Add `update_consolidation_request(source_file, status, error=None, output_rollup_id=None)` method.
   - Add `get_active_requests()` method (returns rows where status IN ('queued', 'submitted', 'generating')).
   - Add `get_failed_requests()` method (returns rows where status = 'failed').

2. **Add explicit task cancellation to `llm_queue.py`:**

   **Primary (B): Slot erase via `--slot-save-path`:**
   - Add `--slot-save-path /tmp/llama-slots` to `arc_summarizer/start.sh`.
   - After `_process_request` completes, call `_cancel_all_other_tasks()`.
   - `_cancel_all_other_tasks()`: GET `/slots`, find all slots where `id_task IS NOT NULL AND is_processing`, send `POST /slots/{id}?action=erase` for each.
   - Log erased slots. Requires `--slot-save-path` flag (adds ~10s startup cost).

   **Fallback (A): Streaming + connection close:**
   - If `--slot-save-path` is unavailable (server not restarted yet), use streaming mode.
   - Add `"stream": true` to all LLM requests.
   - Read response until completion. On timeout/error, close connection → triggers server-side `SERVER_TASK_TYPE_CANCEL` → `slot.release()`.
   - This is the native llama.cpp cancel path (same as UI Stop button).

3. **Add DB tracking to queue submissions:**
   - In `ArcClient._call_with_fallback()`, before `self._queue.submit()`, call `store.upsert_consolidation_request(source_file, tier_id, status='queued')`.
   - After `future.result()`, update status to 'complete' or 'failed'.
   - Pass `source_file` and `tier_id` through the queue (add to `QueuedRequest` dataclass).
   - `source_file` = the JSONL path for daily tier, or `batch:<tier>:<date>` for higher tiers.

4. **Add pre-submit health check to `_worker_loop`:**
   - **Before** `urlopen()`: `GET /v1/models` with 3-second timeout.
   - If unreachable → raise `LLMUnreachableError`, mark request as 'failed' with error message.
   - If reachable → proceed with `urlopen()` using full 1200s timeout.
   - Rationale: Catches dead LLM before submitting. Keeps 1200s timeout for active generations (long prompts on A380).

5. **Replace stale `_clear_prompt_cache()` method:**
   - Current implementation only reads `/slots` (read-only). Replace with slot erase (primary) or connection close (fallback).
   - Add `_wait_for_idle_slots(timeout=30)` helper: polls `/slots` until all `is_processing == false`.

**Tests:**
- [ ] Unit test: `LLMRequestQueue` submits one request, completes, erases other slots via `POST /slots/{id}?action=erase`.
- [ ] Unit test: `consolidation_requests` table created with `source_file` PK, upserted, queried.
- [ ] Unit test: Pre-submit health check (`GET /v1/models`) fails fast when LLM unreachable.
- [ ] Integration test: Queue worker detects dead LLM before submitting, marks request as 'failed' within 3s.
- [ ] Integration test: Fallback streaming mode closes connection, triggers server-side cancel.

**Dependencies:** None.

---

## Phase 2: Scheduler + Lifecycle DB

**What:** Strengthen SessionWatcher guard, make scheduler DB-first for all decisions, add error visibility to lifecycle dashboard.

**Files:**
- Modify: `memory_service/ingest/session_watcher.py`
- Modify: `memory_service/consolidate/scheduler.py`
- Modify: `memory_service/store/session_store.py` (extend `session_lifecycle`)

**Steps:**

1. **Strengthen SessionWatcher guard (`_should_process`):**
   - Check `session_lifecycle` first: if `md_written=1 AND session_ended=1` → skip unconditionally.
   - If `md_written=1 AND rollup_id IS NOT NULL` → skip (fully consolidated).
   - Add cooldown: if `updated_at` within last 600 seconds → skip.
   - Log skip reason for debugging.

2. **Make scheduler DB-first for tier decisions:**
   - `_find_due_tiers()` should query `consolidation_requests` table for active/pending requests.
   - If `consolidation_requests` shows active request (status IN ('submitted', 'generating')) → skip that tier.
   - If `consolidation_requests` shows failed request → retry with backoff.
   - Query uses `source_file` as join key with `session_lifecycle`.

3. **Add error visibility to lifecycle dashboard:**
   - Backend API (`api/consolidation_status.py`) already returns `error` field from `session_lifecycle`.
   - Frontend (`PipelineView.tsx`) already displays error states.
   - Verify the dashboard shows `consolidation_requests` status (new table).

4. **Add `consolidation_status` endpoint for active requests:**
   - New API endpoint: `GET /v1/consolidation/active-requests`
   - Returns: list of active `consolidation_requests` with status, source_file, tier_id, submitted_at, error.

**Tests:**
- [ ] Unit test: SessionWatcher skips already-processed sessions (all guard paths).
- [ ] Unit test: Scheduler skips tiers with active requests.
- [ ] Integration test: API returns active requests correctly.

**Dependencies:** Phase 1 (needs `consolidation_requests` table).

---

## Phase 3: Config + Performance

**What:** Right-size token budgets, add KV cache monitoring, prevent cache exhaustion.

**Files:**
- Modify: `memory_service/consolidate/config.py`
- Modify: `memory_service/consolidate/llm_queue.py` (KV cache monitoring)
- Modify: `memory_service/consolidate/pipeline.py` (per-tier max_tokens)

**Steps:**

1. **Reduce `consolidation_max_tokens` from 8192 to 4096:**
   - Daily tier: 4092 tokens (sufficient for ~2K output).
   - Short tier: 2048 tokens.
   - Weekly tier: 1024 tokens.
   - Bimonthly tier: 512 tokens.
   - Add per-tier config in `ArcConfig`.

2. **Add KV cache monitoring to `_process_request`:**
   - After each request starts, poll `/slots` every 10 seconds.
   - Extract `tg` (tokens/sec generation) from timing logs or slot state.
   - If `tg < 5 tok/s` for >60 seconds → log warning, consider cancelling.
   - If `tg < 2 tok/s` for >120 seconds → cancel current task, clear cache, retry with smaller prompt (reduce max_tokens by 50%).

3. **Add per-request timeout:**
   - Each tier has a max processing time (daily: 10min, short: 5min, weekly: 3min, bimonthly: 2min).
   - If exceeded → cancel, mark as failed, record error.

4. **Add `consolidation_requests` timeout column:**
   - Track `expected_completion_at` (submitted_at + tier_timeout).
   - Scheduler checks for overdue requests and cancels them.

**Tests:**
- [ ] Unit test: Per-tier max_tokens applied correctly.
- [ ] Integration test: KV cache monitoring detects slow generation, triggers cancel.
- [ ] Integration test: Per-request timeout enforced.

**Dependencies:** Phase 1 (needs DB tracking), Phase 2 (needs scheduler integration).

---

## Phase 4: Production Verification

**What:** Wire all components, run end-to-end, verify pipeline processes 20 sessions without stalling.

**Files:**
- Modify: systemd service files (if needed)
- No new files

**Steps:**

1. **Restart all services in clean order:**
   - Stop: `memory-service`, `council-backend`, `council-supervisor`
   - Restart: `arc-summarizer` (clear KV cache)
   - Start: `memory-service` (loads new code)
   - Start: `council-backend`
   - Start: `council-supervisor`

2. **Verify single-owner guarantee:**
   - `ss -tnp | grep 18095` → only memory-service and council-supervisor (health check only)
   - `curl /slots` → all slots idle

3. **Trigger consolidation:**
   - `POST /v1/consolidation/trigger?tier=daily` (or wait for scheduler)
   - Monitor: `journalctl -u memory-service -f`

4. **Verify pipeline processes sessions:**
   - Watch for "Sequential processing [N/20]" logs.
   - Watch for "consolidation-daily succeeded" logs.
   - Verify `consolidation_requests` table shows complete status.
   - Verify `session_lifecycle` shows `rollup_id` for each session.

5. **Verify performance:**
   - Each session completes in <10 minutes (with 4096 max_tokens).
   - No KV cache exhaustion (tg > 10 tok/s throughout).
   - No duplicate requests.

6. **Verify error handling:**
   - Kill LLM mid-processing → queue detects failure, marks request as failed.
   - Restart LLM → pipeline resumes from failed request.

**Post-Wiring Tests (GATE):**
- [ ] All 20 sessions consolidated successfully
- [ ] `consolidation_requests` table shows all complete
- [ ] `session_lifecycle` shows rollup_id for all sessions
- [ ] No duplicate pipeline owners (only memory-service submits)
- [ ] KV cache never exhausted (tg > 10 tok/s)
- [ ] SessionWatcher doesn't reprocess already-processed files
- [ ] Frontend dashboard shows correct status
- [ ] All existing tests still pass (`pnpm check`, `pytest`)

**Marking Complete:** The task is NOT complete until all post-wiring tests pass.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/consolidate/llm_queue.py` | Task cancellation, DB tracking, fail-fast, KV monitoring |
| Modify | `memory_service/consolidate/client.py` | Pass source_file/tier_id through queue |
| Modify | `memory_service/consolidate/config.py` | Per-tier max_tokens |
| Modify | `memory_service/consolidate/pipeline.py` | Use per-tier max_tokens, DB tracking |
| Modify | `memory_service/consolidate/scheduler.py` | DB-first tier decisions |
| Modify | `memory_service/ingest/session_watcher.py` | Strengthen guard |
| Modify | `memory_service/store/session_store.py` | `consolidation_requests` table |
| Modify | `memory_service/api/consolidation_status.py` | Active requests endpoint |
| Modify | `arc_summarizer/start.sh` | Add `--slot-save-path /tmp/llama-slots` flag |
| Modify | `council_main.py` | Remove ArcSummarizer entirely (already disabled) |
| Create | `tests/test_consolidation_queue.py` | Queue hardening tests |
| Create | `tests/test_consolidation_requests.py` | DB tracking tests |

---

## Constraints

- **Single owner:** Only `memory-service` may submit consolidation requests. No other process may call the LLM for consolidation.
- **Single task in flight:** Only one LLM request may be active at any time. The queue enforces this, but the LLM KV cache must be cleared between requests.
- **DB-backed state:** All pipeline state must be in `session_lifecycle` and `consolidation_requests`. No in-memory-only state.
- **Fail-fast:** If LLM is unreachable, detect within 3 seconds (pre-submit `GET /v1/models`). Never block for 20+ minutes.
- **Canonical key:** `source_file` is the single tracking key across `session_lifecycle`, `consolidation_requests`, and `memory_rollups`. No `trace_id` in new code.
- **No silent failures:** Every failed request must have an error recorded in DB.
- **Token budget:** Total prompt + generation tokens must fit in A380 VRAM. Monitor `tg` to detect cache pressure.

---

## Success Criteria

- [ ] Only one process (memory-service) submits consolidation requests
- [ ] Only one LLM task active at any time (KV cache clear between requests)
- [ ] All requests tracked in `consolidation_requests` table with status + error
- [ ] Dead LLM detected within 3 seconds (pre-submit health check), request marked as failed
- [ ] `source_file` used as canonical key throughout (no `trace_id` in new code)
- [ ] SessionWatcher doesn't reprocess already-processed files
- [ ] All 20 pending sessions consolidated in <3 hours (not 48)
- [ ] Frontend dashboard shows real-time pipeline status
- [ ] All existing tests pass (no regression)
- [ ] Pipeline recovers from LLM restart without manual intervention

---

## Cancellation Mechanism (RESOLVED)

**Primary (B): Slot erase via `--slot-save-path`:**
- Add `--slot-save-path /tmp/llama-slots` to `arc_summarizer/start.sh`.
- Enables `POST /slots/{id}?action=erase` — forcefully clears slot's KV cache.
- Works regardless of streaming mode. Requires server restart (~10s cost).
- Source: `server-context.cpp` line 2323 (`SERVER_TASK_TYPE_SLOT_SAVE` handler).

**Fallback (A): Streaming + connection close:**
- Add `"stream": true` to all LLM requests.
- On timeout/error, close HTTP connection → triggers `server_response_reader::stop()` → posts `SERVER_TASK_TYPE_CANCEL` → `slot.release()`.
- Same mechanism as llama.cpp UI Stop button (`AbortController.abort()`).
- Source: `server-queue.cpp` line 431, `server-context.cpp` line 2230.

**Decision:** Implement B first (server config change). If server restart is blocked, A works immediately (code-only change). Both achieve same outcome.

## Caveats & Uncertainty

1. **KV cache monitoring:** The `/slots` endpoint reports `tg` (tokens/sec generation) in timing logs, but not in the JSON response. May need to parse logs or use a different endpoint. **Needs verification.**
2. **A380 SYCL performance:** The model runs at ~333 tok/s prompt processing but only ~5 tok/s generation under normal conditions. The 0.58 tok/s observed was under KV cache pressure. Normal generation speed needs baseline measurement. **Needs verification.**
3. **Per-tier max_tokens:** 4092 for daily tier may be too small for large sessions. Monitor output quality after reduction. **May need tuning.**
4. **council_main ArcSummarizer removal:** If council_main has other dependencies on `self._arc` (e.g., health checks), those need to be migrated to the memory-service API. **Needs audit.**
5. **`--slot-save-path` startup cost:** Adding the flag adds ~10s to server startup. Acceptable for production but note for rapid restart scenarios.

---

## Clarification Needed Before Drafting

**RESOLVED:** LLM task cancellation mechanism is now verified.

- **Primary:** `--slot-save-path` flag enables `POST /slots/{id}?action=erase` (forceful KV cache clear).
- **Fallback:** Streaming requests + connection close triggers native `SERVER_TASK_TYPE_CANCEL`.
- Both mechanisms verified in llama.cpp source (`server-context.cpp`, `server-queue.cpp`).

**No further clarification needed.** Ready to execute Phase 1.
