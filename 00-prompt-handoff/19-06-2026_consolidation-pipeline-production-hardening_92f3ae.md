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
1. **Hard-enforce single-task-in-flight:** The queue already serializes, but the LLM can hold multiple tasks in KV cache. After each request completes, explicitly cancel all other tasks via `POST /v1/chat/message` or `DELETE /slots/{id}`.
2. **Reduce `consolidation_max_tokens` to 4096** (or configurable per-tier). Daily tier needs ~2K output, not 8K.
3. **Add KV cache monitoring:** If `tg < 5 tok/s` for >60s, cancel current task, clear cache, retry with smaller prompt.

---

### Gap 3: No DB-Backed Request Tracking

**Current:** The LLM queue uses in-memory `Future` objects. No DB record of which session is being consolidated, what state it's in, or what error occurred.

**Evidence:** When the memory service was killed (PID 269150 → 300330), all in-flight requests were lost. The `session_lifecycle` table had no `error` column to record partial failures. The queue worker blocked on `future.result(timeout=1260)` for 20 minutes waiting for responses from dead processes.

**Impact:** No visibility into pipeline state. No recovery from partial failures. No audit trail.

**Fix:** Add a `consolidation_requests` table:

```sql
CREATE TABLE IF NOT EXISTS consolidation_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    tier_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',  -- queued, submitted, generating, complete, failed, cancelled
    submitted_at TEXT,
    completed_at TEXT,
    llama_task_id INTEGER,
    error TEXT,
    output_rollup_id TEXT,
    UNIQUE(trace_id, tier_id, status)
);
```

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

**Fix:** Replace blocking `future.result()` with periodic health checks:
1. After submitting request to LLM, start a health-check timer (every 30s).
2. If LLM is unreachable OR all slots are idle (request was lost), cancel and retry.
3. Max total wait time per request: `timeout_seconds` (configurable, default 600s).
4. On timeout: mark `consolidation_requests.status = 'failed'` with error message.

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
   - Create table with schema above (Gap 3).
   - Add `upsert_consolidation_request(trace_id, tier_id, status, **kwargs)` method.
   - Add `update_consolidation_request(id, status, error=None, output_rollup_id=None)` method.
   - Add `get_active_requests()` method (returns rows where status IN ('queued', 'submitted', 'generating')).

2. **Add explicit task cancellation to `llm_queue.py`:**
   - After `_process_request` completes (success or failure), call `_cancel_all_other_tasks(current_task_id)`.
   - `_cancel_all_other_tasks(task_id)`: GET `/slots`, find all tasks where `id_task != task_id AND is_processing`, send `POST /v1/chat/message` with `{"slot_id": N, "content": ""}` or equivalent cancel mechanism.
   - Log cancelled tasks.

3. **Add DB tracking to queue submissions:**
   - In `ArcClient._call_with_fallback()`, before `self._queue.submit()`, call `store.upsert_consolidation_request(trace_id, tier_id, status='queued')`.
   - After `future.result()`, update status to 'complete' or 'failed'.
   - Pass `trace_id` and `tier_id` through the queue (add to `QueuedRequest` dataclass).

4. **Add fail-fast health check to `_worker_loop`:**
   - After submitting HTTP request, start a timer.
   - Every 30 seconds, check if LLM is healthy (`GET /v1/models`).
   - If unhealthy AND all slots idle → request was lost, cancel and retry.
   - If total elapsed > `timeout_seconds` → mark as failed, don't retry.

5. **Remove stale `_clear_prompt_cache()` method:**
   - Current implementation only reads `/slots` (read-only). Replace with actual cache clear via cancel.

**Tests:**
- [ ] Unit test: `LLMRequestQueue` submits one request, completes, cancels others.
- [ ] Unit test: `consolidation_requests` table created, upserted, queried.
- [ ] Integration test: Queue worker detects dead LLM, marks request as failed within 60s.

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
   - If `consolidation_requests` shows active request for a tier → skip that tier.
   - If `consolidation_requests` shows failed request → retry with backoff.

3. **Add error visibility to lifecycle dashboard:**
   - Backend API (`api/consolidation_status.py`) already returns `error` field from `session_lifecycle`.
   - Frontend (`PipelineView.tsx`) already displays error states.
   - Verify the dashboard shows `consolidation_requests` status (new table).

4. **Add `consolidation_status` endpoint for active requests:**
   - New API endpoint: `GET /v1/consolidation/active-requests`
   - Returns: list of active `consolidation_requests` with status, trace_id, tier_id, submitted_at, error.

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
| Modify | `memory_service/consolidate/client.py` | Pass trace_id/tier_id through queue |
| Modify | `memory_service/consolidate/config.py` | Per-tier max_tokens |
| Modify | `memory_service/consolidate/pipeline.py` | Use per-tier max_tokens, DB tracking |
| Modify | `memory_service/consolidate/scheduler.py` | DB-first tier decisions |
| Modify | `memory_service/ingest/session_watcher.py` | Strengthen guard |
| Modify | `memory_service/store/session_store.py` | `consolidation_requests` table |
| Modify | `memory_service/api/consolidation_status.py` | Active requests endpoint |
| Modify | `council_main.py` | Remove ArcSummarizer entirely (already disabled) |
| Create | `tests/test_consolidation_queue.py` | Queue hardening tests |
| Create | `tests/test_consolidation_requests.py` | DB tracking tests |

---

## Constraints

- **Single owner:** Only `memory-service` may submit consolidation requests. No other process may call the LLM for consolidation.
- **Single task in flight:** Only one LLM request may be active at any time. The queue enforces this, but the LLM KV cache must be cleared between requests.
- **DB-backed state:** All pipeline state must be in `session_lifecycle` and `consolidation_requests`. No in-memory-only state.
- **Fail-fast:** If LLM is unreachable, detect within 60 seconds. Never block for 20+ minutes.
- **No silent failures:** Every failed request must have an error recorded in DB.
- **Token budget:** Total prompt + generation tokens must fit in A380 VRAM. Monitor `tg` to detect cache pressure.

---

## Success Criteria

- [ ] Only one process (memory-service) submits consolidation requests
- [ ] Only one LLM task active at any time (KV cache clear between requests)
- [ ] All requests tracked in `consolidation_requests` table with status + error
- [ ] Dead LLM detected within 60 seconds, request marked as failed
- [ ] SessionWatcher doesn't reprocess already-processed files
- [ ] All 20 pending sessions consolidated in <3 hours (not 48)
- [ ] Frontend dashboard shows real-time pipeline status
- [ ] All existing tests pass (no regression)
- [ ] Pipeline recovers from LLM restart without manual intervention

---

## Caveats & Uncertainty

1. **LLM cancel mechanism:** llama.cpp's `/slots` endpoint may not support task cancellation. May need to use `POST /v1/chat/message` with empty content or restart the LLM. **Needs verification.**
2. **KV cache monitoring:** The `/slots` endpoint reports `tg` (tokens/sec generation) in timing logs, but not in the JSON response. May need to parse logs or use a different endpoint. **Needs verification.**
3. **A380 SYCL performance:** The model runs at ~333 tok/s prompt processing but only ~5 tok/s generation under normal conditions. The 0.58 tok/s observed was under KV cache pressure. Normal generation speed needs baseline measurement. **Needs verification.**
4. **Per-tier max_tokens:** 4092 for daily tier may be too small for large sessions. Monitor output quality after reduction. **May need tuning.**
5. **council_main ArcSummarizer removal:** If council_main has other dependencies on `self._arc` (e.g., health checks), those need to be migrated to the memory-service API. **Needs audit.**

---

## Clarification Needed Before Drafting

**Issue:** LLM task cancellation mechanism is uncertain.

**Context:** llama.cpp's `/slots` endpoint is read-only (GET). There's no documented cancel endpoint. The old code used `POST /v1/chat/message` but that endpoint doesn't exist on this fork.

**Options:**
- A: Restart `arc-summarizer.service` to clear KV cache (nuclear option, loses all state)
- B: Send `POST /v1/chat/completions` with `stream: true` then immediately close connection (may work, may not)
- C: Add a custom cancel endpoint to llama.cpp fork (requires C++ changes)
- D: Accept that cancellation isn't possible; rely on timeout + retry instead

**Recommendation:** Option D (timeout + retry) is safest. The queue already has per-request timeout. If a request times out, the LLM will eventually free the slot. Add a "graceful cancel" via connection close as a best-effort.

**Blocking:** No — can proceed with timeout-based approach. Cancel is optimization.
