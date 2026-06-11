# Consolidation Pipeline — Open Items Handoff

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `cb4183` |
| Entity type | `handoff` |
| Short description | Execution plan for all open items in the consolidation pipeline: reconciliation filtering, service restoration, quality improvements |
| Status | `draft` |
| Source references | Session summary (compacted), `memory_service/` source tree |
| Generated | 11-06-2026 |
| Next action / owner | Execute P0 items (reconciliation filtering) first |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`

**Key files:**

| File | Purpose |
|------|---------|
| `memory_service/consolidate/config.py` | ArcConfig, timeouts, server settings |
| `memory_service/consolidate/pipeline.py` | Stage 2 pipeline, bundling logic |
| `memory_service/consolidate/prompts.py` | Daily/short tier prompts (v3, trimmed) |
| `memory_service/consolidate/tier_gatherer.py` | Session gathering, bundling helpers |
| `memory_service/consolidate/tier_writer.py` | Consolidation MD rendering |
| `memory_service/reconcile/prompts.py` | Reconciliation prompt (v3, field mapping) |
| `memory_service/reconcile/reconciler.py` | ArcReconciler LLM call |
| `memory_service/reconcile/applicator.py` | Action application to DB |
| `arc_summarizer/start.sh` | Server startup script |
| `upstream-config.json` | Model configs, ctx_size |

**Service files:**
- `~/.config/systemd/user/arc-summarizer.service` — LLM server (active, port 18095)
- `~/.config/systemd/user/memsearch-watch.service` — indexing (DEAD)
- `~/.config/systemd/user/consolidate-daily.timer` — daily consolidation (stopped)
- `~/.config/systemd/user/consolidate-short.timer` — short consolidation (stopped)
- `~/.config/systemd/user/reconcile.timer` — reconciliation (stopped)

**Database:** `/home/chief/.council-memory/council_core.db`

**Current DB state:**

| Table | Count | Notes |
|-------|-------|-------|
| work_items | 434 | 423 proposed (never deduplicated), 15 done, 6 open |
| plan_deviations | 306 | 285 proposed (never deduplicated), 11 approved, 9 closed, 1 implemented |
| knowledge_cards | 0 | Injector produces no output |
| memory_entries | 51 | Consolidation outputs |
| memory_rollups | 89 | Daily/short rollups |
| raw_session_memories | 202 | Session-level memory |
| carry_forward | 5 | Never loaded into reconciliation prompt |
| injection_blacklist | ? | Empty or unpopulated |

---

## Execution Order

```
P0: Reconciliation filtering (blocks P1 reconciliation sweep)
  ↓
P1: Service restoration + re-consolidation + reconciliation sweep
  ↓
P2: Quality improvements (independent, can run in parallel with P1)
```

---

## P0: Reconciliation Prompt Filtering

**What:** Cap existing DB state injected into reconciliation prompt to ~50 items (recency + relevance filtered). Current injection of 434 tasks + 306 deviations produces ~40K tokens, exceeding ctx_size (32768) and causing `400 ERROR: exceed_context_size_error`.

**Problem:**
- Full DB state → 40,224 tokens → exceeds context window → reconciliation never succeeds
- 423 proposed work items and 285 proposed deviations are NEVER deduplicated
- Last successful reconciliation: Jun 10 (before context overflow discovered)

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/reconcile/reconciler.py` | Add filtering logic before prompt assembly |

**Steps:**

1. **Add filtering function** `_filter_existing_state()` in `reconciler.py`:
   - Cap work_items to 50 most recent (ORDER BY created_at DESC)
   - Cap plan_deviations to 30 most recent (ORDER BY created_at DESC)
   - Filter by status: prioritize `proposed`, `open`, `in_progress` over `done`, `closed`
   - Filter by recency: exclude items older than 7 days (configurable)
   - Filter by relevance: keyword match against consolidation summary (optional, Phase 2)

2. **Add config params** to `ArcConfig` (or `config-subsystem.json`):
   - `reconcile_max_work_items: 50`
   - `reconcile_max_deviations: 30`
   - `reconcile_recency_days: 7`
   - `reconcile_status_priority: [proposed, open, in_progress, blocked, done, wont_do, superseded]`

3. **Update prompt assembly** to use filtered state instead of full DB dump.

4. **Add logging** of filter stats (e.g., "Filtered 434→48 work items, 306→27 deviations").

**Tests:**
- [ ] Filter function returns ≤50 items when DB has 400+
- [ ] Filter prioritizes `proposed`/`open` over `done`/`closed`
- [ ] Filter respects recency window (7 days default)
- [ ] Prompt token count stays under ctx_size (32768) with filtered state
- [ ] All existing tests still pass

**Dependencies:** None (P0, standalone)

---

## P1: Service Restoration + Re-consolidation + Reconciliation Sweep

**What:** Restart stopped services, re-consolidate unprocessed files, run full reconciliation sweep.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/consolidate/pipeline.py` | Verify bundling fix covers all edge cases |
| Modify | `memory_service/consolidate/tier_gatherer.py` | Verify bundling in gather phase |

**Steps:**

### P1A: Restart Services

1. **Restart `memsearch-watch.service`** — currently DEAD; new consolidations not being indexed
   - Check service file for errors
   - Verify memsearch DB is accessible (`/home/chief/.council-memory/codegraph.db`)
   - Start service, verify active

2. **Restart consolidation timers** — `consolidate-daily.timer` and `consolidate-short.timer` are stopped
   - Enable + start both timers
   - Verify next run time is scheduled

3. **Restart reconciliation timer** — `reconcile.timer` is stopped
   - Enable + start timer (after P0 filtering is complete)
   - Verify next run time is scheduled

### P1B: Re-consolidate Unprocessed Files

**Context:** The bundling fix was applied AFTER most sessions were processed. 47 NEW format files may need re-processing with bundling logic.

1. **Check raw sessions** — verify all files are processed or identify backlog
   - Current state: 0 unprocessed files in raw_sessions (all moved to processed/)
   - If all processed: no action needed (bundling fix applies to future sessions)
   - If backlog exists: re-run pipeline with bundling enabled

2. **Verify bundling logic** — check that `_group_sessions_by_trace_id()` and `_bundle_session_parts()` are working:
   - Test with known multi-part session (e.g., `trace-20260610-225844-2b420834` — 5 parts)
   - Confirm all parts are processed together
   - Confirm all parts moved to `processed/` after bundling

3. **Run manual consolidation** if backlog exists:
   - Trigger daily consolidation manually
   - Verify bundled sessions produce richer output (3+ work_completed, specific files)

### P1C: Run Full Reconciliation Sweep

1. **After P0 filtering is complete**, run reconciliation manually:
   - Use filtered state (≤50 items)
   - Process all 85 daily + 3 short consolidations
   - Verify deduplication reduces 423 proposed → reasonable count

2. **Verify reconciliation output quality:**
   - `action=update` always has `target_id != null`
   - Task titles ≤80 characters
   - `files`/`functions` populated from `work_completed`
   - `carried_forward` split (from_previous/to_next) handled correctly

3. **Apply reconciliation actions** to DB:
   - Verify applicator handles all action types
   - Check no duplicate work items created
   - Verify deviation deduplication

**Tests:**
- [ ] All services active (arc-summarizer, memsearch-watch, consolidate timers, reconcile timer)
- [ ] Bundling produces richer output than single-part processing
- [ ] Reconciliation completes without context overflow
- [ ] Proposed work items reduced from 423 to <100 after dedup
- [ ] Proposed deviations reduced from 285 to <50 after dedup
- [ ] All existing tests still pass

**Dependencies:** P0 (reconciliation filtering) must complete first

---

## P2: Quality Improvements (Parallel Fan-out)

Three independent tasks that can run in parallel after P1.

### P2A: Injection Blacklist + Quality Threshold

**What:** Filter low-signal sessions before consolidation to reduce noise.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/consolidate/pipeline.py` | Add quality threshold check |
| Modify | `memory_service/consolidate/config.py` | Add quality threshold config |

**Steps:**

1. **Populate `injection_blacklist` table** — add known low-signal patterns:
   - Sessions with <50 chars of unique content (after stripping Reference sections)
   - Sessions with 0 file operations (purely conversational)
   - Sessions matching trivial patterns ("hi" → "Hi!", "system logged out")

2. **Add quality threshold** to pipeline:
   - Config: `consolidation_min_chars: 200` (tunable)
   - Skip sessions below threshold (log as "skipped: below quality threshold")
   - Count skipped sessions in logs

3. **Verify blacklist is checked** before ARC LLM calls:
   - Add blacklist check in `_process_raw_sessions_sequentially()`
   - Log blacklisted sessions

**Tests:**
- [ ] Sessions <200 chars are skipped
- [ ] Blacklisted sessions don't reach ARC LLM
- [ ] Skipped sessions logged with reason
- [ ] No regression in existing tests

**Dependencies:** None (independent)

### P2B: Knowledge Card Injector Debug

**What:** `knowledge_cards` table exists but injector produces 0 output. Debug and fix.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/store/` — locate injector | Fix injection logic |
| Create | Test for knowledge card injection | Verify output |

**Steps:**

1. **Locate knowledge card injector** — find where `knowledge_cards` should be populated:
   - Search for `knowledge_card` in `memory_service/` codebase
   - Check if injector is wired to ARC LLM or runs separately

2. **Debug why output is empty:**
   - Check if injector is called at all (add logging)
   - Check if ARC LLM prompt includes knowledge card extraction instructions
   - Check if YAML schema includes `knowledge_cards` field

3. **Fix injection:**
   - If prompt missing: add `knowledge_cards[]` to daily tier YAML schema
   - If injector broken: fix parsing/storage logic
   - If not wired: add to pipeline

4. **Verify with test:**
   - Run consolidation on known substantive session
   - Check `knowledge_cards` table for new entries

**Tests:**
- [ ] Knowledge card injector produces output for substantive sessions
- [ ] Cards stored in `knowledge_cards` table
- [ ] Cards indexed in `knowledge_cards_fts`
- [ ] No regression in existing tests

**Dependencies:** None (independent)

### P2C: Clean Up + Maintenance

**What:** Fix stale paths, outdated comments, config mismatches.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/start.sh` | Update comment (ctx-size says 36864, actual is 32768) |
| Modify | `arc_summarizer/oneapi-env.txt` | Remove stale PATH entries (points to old `/home/chief/llama.cpp/build/bin/`) |

**Steps:**

1. **Fix `start.sh` comment** — line 12 says `--ctx-size 36864` but actual is `--ctx-size 32768`. Update comment to match.

2. **Fix `oneapi-env.txt`** — remove stale PATH entries pointing to old llama.cpp build directory.

3. **Verify upstream-config.json alignment** — confirm `ctx_size: 32768` matches start.sh `--ctx-size 32768`. (Already aligned after revert.)

4. **Verify all tests pass** — run full test suite.

**Tests:**
- [ ] Comments match actual values
- [ ] No stale paths in environment files
- [ ] Config files aligned (ctx_size matches everywhere)
- [ ] All existing tests pass

**Dependencies:** None (independent)

---

## Constraints

- **No sudo access** — all changes must work within user-space systemd
- **Arc A380 GPU only** — 6GB VRAM, Level Zero, GDDR6 224 GB/s
- **Model:** `granite-4.1-3b-Q4_K_M.gguf` (~2GB)
- **Context window:** 32768 tokens (hard limit)
- **Timeout:** 1200s (20 min) for ARC LLM calls
- **KV cache quantization:** q8_0 (halves memory bandwidth)
- **oneDNN not viable** — crashes on Arc A380 (`ggml_sycl_op_mul_mat` at line 3093). Use `GGML_SYCL_DISABLE_DNN=1` if oneDNN is linked.
- **Bundling strategy** — multi-part sessions grouped by trace ID, concatenated, processed as one unit
- **Character limits** — relaxed (no hard ≤80, "concise" guidance). Accuracy over brevity.
- **Title constraint** — ≤80 characters for task titles (enforced in prompt)

---

## Success Criteria

### P0 (Reconciliation Filtering)
- [ ] Reconciliation prompt stays under 32768 tokens with full DB state
- [ ] Filter returns ≤50 work items, ≤30 deviations
- [ ] Filter prioritizes `proposed`/`open` over `done`/`closed`
- [ ] All existing tests pass

### P1 (Service Restoration + Sweep)
- [ ] All 5 services active (arc-summarizer, memsearch-watch, 2 consolidate timers, reconcile timer)
- [ ] Bundling produces richer output (3+ work_completed, specific files)
- [ ] Reconciliation completes without context overflow
- [ ] Proposed work items reduced from 423 to <100
- [ ] Proposed deviations reduced from 285 to <50
- [ ] All existing tests pass

### P2 (Quality Improvements)
- [ ] Low-signal sessions filtered (<200 chars or blacklisted)
- [ ] Knowledge cards populated (>0 entries)
- [ ] Config files aligned (no stale paths/comments)
- [ ] All existing tests pass

---

## Caveats & Uncertainty

1. **oneDNN crash is hardware-specific** — confirmed crash on Arc A380 (Ponte Vecchio). May work on newer Intel GPUs (Arc B-series, Data Center Max). If GPU changes, re-test Option C build.

2. **KV cache bottleneck is hardware-limited** — 5-6 t/s at 24K context with q8_0 is the best achievable on Arc A380. Only way to improve: smaller context, smaller model, or faster GPU.

3. **Bundling may produce large prompts** — 6-part bundle = ~68K chars = ~22K tokens. At 27 t/s prompt processing + 6.75 t/s generation, expect 546-600s total runtime. 1200s timeout provides headroom.

4. **Reconciliation dedup quality depends on prompt** — Granite-4.1-3B is instruction-following focused but may still miss semantic matches. Manual review of dedup results recommended.

5. **Knowledge card injector may not exist** — table exists but code may be unimplemented. May require new prompt field + storage logic.

6. **Raw sessions all processed** — 0 unprocessed files means bundling fix applies to future sessions only. Historical sessions were processed without bundling (lower quality).

---

## Files to Create/Modify (Summary)

| Priority | Action | File | Purpose |
|----------|--------|------|---------|
| P0 | Modify | `memory_service/reconcile/reconciler.py` | Add `_filter_existing_state()` |
| P0 | Modify | `memory_service/consolidate/config.py` | Add reconcile filter config |
| P1 | N/A | systemd services | Restart memsearch, timers |
| P2A | Modify | `memory_service/consolidate/pipeline.py` | Add quality threshold |
| P2A | Modify | `memory_service/consolidate/config.py` | Add min_chars config |
| P2B | Modify | `memory_service/store/` | Fix knowledge card injector |
| P2C | Modify | `arc_summarizer/start.sh` | Fix comment |
| P2C | Modify | `arc_summarizer/oneapi-env.txt` | Remove stale paths |

---

## Notes for Next Session

- **Server is running** on port 18095 with ctx-size 32768 and q8_0 KV cache
- **All 19 tests pass** (5 skipped — DB-dependent)
- **Daily prompt v3** is trimmed (4903 chars) with CRITICAL RULES section
- **Short tier prompt** handles `carried_forward.from_previous/to_next` and `user_intention`
- **Reconciler prompt** has explicit field→action mapping
- **Option C build** exists at `build-option-c/` but oneDNN crashes — use `GGML_SYCL_DISABLE_DNN=1` if needed
- **GPU frequency** stays at 2450 MHz (max) under load — speed drop is KV cache bandwidth, not power state
