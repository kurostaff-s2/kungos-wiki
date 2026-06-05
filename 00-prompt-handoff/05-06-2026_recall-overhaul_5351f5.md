# Recall Overhaul — Task Handoff

**Source spec:** Research findings from 2026-06-05 analysis session (memory architecture audit, first-principles analysis)
**Generated:** 05-06-2026
**Goal:** Fix the recall system so the agent gets relevant results, not noise. Three problems: broken DB→Milvus bridge, noisy channels, no relevance gating.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:**
- `/home/chief/Coding-Projects/7-council/three-tier-injection-plan.md` — L1/L2/L3 design
- `/home/chief/llm-wiki/00-prompt-handoff/memory-architecture-roadmap-2026-06-05.md` — routing decisions
**Key files for this task:** Listed per phase below
**Related codebases:** None (single project, Python + SQLite + Milvus)

---

## Research Findings (Read Before Executing)

The following was verified against the live codebase. Do not re-investigate — execute.

### Finding 1: DbIndexPoller Bug (Critical)

**File:** `memory_service/db_poller.py`

The `DbIndexPoller._poll_table()` method marks rows `is_indexed=1` even when the Milvus upsert fails silently. The `_upsert_records()` method returns 0 on failure but doesn't raise an exception. Result:

- **186 rows** in pipelines.db marked `is_indexed=1` (raw_session_memories: 132, session_diary: 26, consolidation_cache: 2, artifacts: 26)
- **0 entities** in Milvus from DB sources (verified: 300 entities, 299 are session-trace files, 1 is daily log)
- Rows are never retried because the poller queries `WHERE is_indexed = 0`

**Fix:** Only mark `is_indexed=1` after successful upsert. On failure, leave row at 0 for retry. Add failure counter with exponential backoff.

### Finding 2: Milvus Index is 100% Noise

**Current composition:**
- 94% session-trace files (`/tmp/trace-trace-*.md`) — raw conversation transcripts
- 6% other files
- 2% chat summaries (stale, from May 16)
- 2% consolidation files
- 0% DB-indexed governance data

**After fixing Finding 1, expected composition:**
- DB-indexed content (raw_session_memories, session_diary, consolidation_cache, artifacts) should dominate
- Session-trace files are noisy — consider deprioritizing or excluding

### Finding 3: unified_recall Returns Noise

**File:** `memory_service/layer.py` → `unified_recall()`

Current behavior: fires 8 channels, returns everything, no relevance threshold.

| Channel | Query-Relevant? | Current Behavior |
|---------|----------------|------------------|
| memsearch | ✅ Yes (vector) | Returns top 5, scores 0.47–0.50 (noise) |
| artifacts | ❌ No | Returns last 5 regardless of query |
| review findings | ❌ No | Returns last 10 regardless of query |
| structural | ⚠️ Broad keywords | Fires on "phase", "state", "gate" |
| execution | ✅ Yes | find_similar_runs, query-relevant |
| diary | ❌ No | Returns last 5 regardless of query |
| recent_context | ❌ No | **Guaranteed 3072 chars** regardless of query |
| raw_traces | ❌ No | Returns last 10 regardless of query |

**Result:** 6 of 8 channels are blind firehoses. Token budget (4096) is consumed by guaranteed inclusions before query-relevant results matter.

### Finding 4: Embedding Model Quality

The embedding model (pplx-embed-v1-0.6b) returns:
- **0.953** for genuinely relevant matches (good)
- **0.500** for irrelevant matches (noise floor)
- **Threshold 0.60** filters false positives effectively — returns empty rather than wrong

**Conclusion:** The model is fine. The problem is no threshold gate. An honest empty response is better than confident noise.

---

## Execution Order (DAG)

```
Phase 1 (fix poller) → Phase 2 (re-index) → Phase 3 (scope gating)
                                                    ↓
                                              Phase 4 (threshold)
                                                    ↓
                                              Phase 5 (wiring + tests)
```

Phases 1-2 are sequential. Phase 3 can start after Phase 1 (doesn't need re-indexed data). Phase 4 depends on Phase 3. Phase 5 depends on all.

---

## Phase 1: Fix DbIndexPoller Bug

**What:** Fix the silent upsert failure so rows are only marked `is_indexed=1` after successful Milvus upsert. Add failure tracking with exponential backoff.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/db_poller.py` | Fix `_poll_table()` to mark indexed only after success |
| Modify | `memory_service/store.py` | Add `index_failures` column to tables with `is_indexed` |
| Create | `migrations/02_index_failures.sql` | Migration for new column |

**Steps:**

1. **Add migration** — `migrations/02_index_failures.sql`:
   ```sql
   ALTER TABLE raw_session_memories ADD COLUMN index_failures INTEGER DEFAULT 0;
   ALTER TABLE session_diary ADD COLUMN index_failures INTEGER DEFAULT 0;
   ALTER TABLE consolidation_cache ADD COLUMN index_failures INTEGER DEFAULT 0;
   ALTER TABLE artifacts ADD COLUMN index_failures INTEGER DEFAULT 0;
   ```

2. **Fix `_poll_table()`** — In `db_poller.py`, change the upsert flow:
   - Only mark `is_indexed=1` after `_upsert_records()` returns count > 0
   - On failure, increment `index_failures` column
   - If `index_failures >= 5`, log warning but don't retry (circuit breaker)
   - Add exponential backoff: skip row for `2^failures` poll cycles

3. **Reset already-broken rows** — One-time fix:
   ```python
   # Reset rows that were falsely marked as indexed
   for table in ['raw_session_memories', 'session_diary', 'consolidation_cache', 'artifacts']:
       db.execute(f'UPDATE {table} SET is_indexed = 0 WHERE is_indexed = 1')
       db.commit()
   ```

4. **Add logging** — Log upsert success/failure with row counts for observability.

**Tests:**
- [ ] `_poll_table()` marks row indexed only after successful upsert
- [ ] Failed upsert increments `index_failures`, leaves `is_indexed=0`
- [ ] Row with `index_failures >= 5` is skipped (circuit breaker)
- [ ] Existing tests still pass

**Dependencies:** None

---

## Phase 2: Re-Index DB Content

**What:** Trigger the poller to index the 186 unindexed rows. Verify content lands in Milvus.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/__main__.py` | Add CLI command for manual re-index |
| Create | `tests/test_db_poller_reindex.py` | Verify DB→Milvus bridge works |

**Steps:**

1. **Add CLI command** — `memory_service/__main__.py`:
   ```
   python3 -m memory_service reindex [--force]
   ```
   - `--force` resets all `is_indexed=0` before polling
   - Runs one poll cycle synchronously (not background thread)
   - Reports: rows processed, chunks created, entities upserted

2. **Run re-index** — Execute the command, verify output:
   ```
   $ python3 -m memory_service reindex --force
   DbIndexPoller: reset 186 rows to is_indexed=0
   DbIndexPoller: raw_session_memories → 132 rows, 248 chunks upserted
   DbIndexPoller: session_diary → 27 rows, 45 chunks upserted
   DbIndexPoller: consolidation_cache → 2 rows, 5 chunks upserted
   DbIndexPoller: artifacts → 26 rows, 38 chunks upserted
   Total: 186 rows, 336 chunks upserted to Milvus
   ```

3. **Verify in Milvus** — Query Milvus to confirm DB sources exist:
   ```python
   # Should return entities with source prefix "raw_session_memories:", "session_diary:", etc.
   results = client.query(collection_name='memsearch_chunks', filter='source like "raw_session_memories:%"', limit=10)
   assert len(results) > 0, "DB content not in Milvus"
   ```

**Tests:**
- [ ] CLI command runs and reports counts
- [ ] Milvus contains entities with DB source prefixes
- [ ] Search returns DB-indexed content (not just file traces)
- [ ] `is_indexed=1` only for successfully upserted rows

**Dependencies:** Phase 1 complete

---

## Phase 3: Scope Gating

**What:** Replace the 8 blind channels with scoped recall. One tool, one `scope` parameter, channels fire based on scope.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/layer.py` | Replace `unified_recall()` with scoped version |
| Modify | `memory_service/mcp_server.py` | Update `council-recall` tool schema |
| Modify | `.pi/agent/extensions/council-tools/index.ts` | Update Pi extension tool |

**Steps:**

1. **Define scope→channel mapping** in `layer.py`:
   ```python
   SCOPE_CHANNELS = {
       None:      ['memsearch'],                    # default: vector only
       'decision':['memsearch', 'diary'],           # what did we decide?
       'repair':  ['memsearch', 'execution'],       # how do I fix this?
       'recent':  ['recent_context'],               # what just happened?
       'run':     ['memsearch', 'artifacts', 'execution'],  # what happened in run X?
       'architecture': ['memsearch', 'structural'], # how does X work?
       'all':     ['memsearch', 'diary', 'execution', 'recent_context', 'artifacts', 'structural', 'raw_traces'],
   }
   ```

2. **Modify `unified_recall()`** — Accept `scope` parameter:
   - Look up channels from `SCOPE_CHANNELS[scope]`
   - Fire ONLY those channels (no blind inclusions)
   - Remove guaranteed 3072-char recent_context default
   - Remove "last N regardless of query" pattern from all channels

3. **Make each channel query-relevant:**
   - **memsearch:** Already query-relevant (vector search) ✅
   - **diary:** Filter by query keywords (FTS5 on session_diary)
   - **execution:** Already query-relevant (find_similar_runs) ✅
   - **artifacts:** Filter by query keywords (FTS5 on artifacts)
   - **structural:** Keep keyword gate but narrow to: "workflow", "pipeline", "phase", "transition"
   - **recent_context:** Only fire when scope="recent" or scope="all"

4. **Update MCP tool schema** — Add `scope` parameter to `council-recall`:
   ```python
   scope: Optional[str] = None,  # "decision" | "repair" | "recent" | "run" | "architecture" | "all"
   ```

5. **Update Pi extension** — Add `scope` parameter to `recall.unified` tool.

**Tests:**
- [ ] `recall(query="X")` fires memsearch only (default scope)
- [ ] `recall(query="X", scope="repair")` fires memsearch + execution only
- [ ] `recall(query="X", scope="recent")` fires recent_context only
- [ ] No channel returns results unrelated to query
- [ ] Token budget respected (no guaranteed inclusions)

**Dependencies:** None (can start after Phase 1, doesn't need re-indexed data)

---

## Phase 4: Threshold Gating

**What:** Add similarity threshold to memsearch results. Results below threshold are dropped. Empty response is better than noise.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/layer.py` | Add threshold filter to memsearch results |
| Modify | `memory_service/config.py` | Add `recall_threshold` config option |

**Steps:**

1. **Add config option** — `config.py`:
   ```python
   recall_threshold: float = 0.60  # Minimum similarity score for results
   ```

2. **Apply threshold in `unified_recall()`** — After memsearch results:
   ```python
   threshold = self._config.recall_threshold  # default 0.60
   filtered_results = [r for r in ms_results if r.get('score', 0) >= threshold]
   ```

3. **Handle empty results** — When no results pass threshold:
   - Return `{"channels": {}, "fused_context": "", "note": "No results above threshold"}`
   - Agent interprets empty as "no prior knowledge available"
   - Better than returning irrelevant results

4. **Add threshold override** — Allow per-call override:
   ```python
   threshold: Optional[float] = None,  # Override config default
   ```

**Tests:**
- [ ] Results below threshold are filtered out
- [ ] Empty response when no results pass threshold
- [ ] Threshold override works per-call
- [ ] Default threshold (0.60) filters false positives

**Dependencies:** Phase 3 complete

---

## Phase 5: Production Wiring + Verification

**What:** Wire all changes into the running system. Verify end-to-end recall works.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/__main__.py` | Start poller on service launch |
| Create | `tests/test_recall_overhaul_e2e.py` | End-to-end verification |

**Steps:**

1. **Start poller on service launch** — Ensure `DbIndexPoller` starts when memory service launches:
   ```python
   # In __main__.py or service startup
   poller = DbIndexPoller(db=store.db, config=config)
   poller.start(interval=30)
   ```

2. **Run re-index** — Execute Phase 2 CLI command to index all 186 rows.

3. **Verify Milvus composition** — DB-indexed content should now be majority:
   ```
   DB:raw_session_memories  ~250 entities
   DB:session_diary         ~45 entities
   DB:consolidation_cache   ~5 entities
   DB:artifacts             ~38 entities
   file:session-trace       ~299 entities (existing, will be diluted)
   ```

4. **Run recall test queries** — Verify scoped, thresholded recall:
   ```python
   # Test 1: Default scope (memsearch only)
   result = layer.unified_recall(query="memory architecture", scope=None)
   assert 'memsearch' in result['channels']
   assert 'recent_context' not in result['channels']  # not in default scope
   assert all(r['score'] >= 0.60 for r in result['channels']['memsearch']['results'])

   # Test 2: Repair scope
   result = layer.unified_recall(query="auth test failure", scope="repair")
   assert 'memsearch' in result['channels']
   assert 'execution' in result['channels']
   assert 'diary' not in result['channels']  # not in repair scope

   # Test 3: Empty response (no relevant results)
   result = layer.unified_recall(query="xyz nonexistent topic", scope=None)
   assert result['fused_context'] == '' or 'no results' in result.get('note', '')
   ```

5. **Verify MCP tool works** — Test through MCP transport:
   ```
   POST /tools/call { name: "council-recall", arguments: { query: "memory architecture", scope: "architecture" } }
   ```

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] Memory service starts and poller is running
- [ ] Milvus contains DB-indexed content (verified via query)
- [ ] `recall.unified()` returns scoped results (not all channels)
- [ ] Threshold filters results (no false positives below 0.60)
- [ ] Empty response for queries with no relevant results
- [ ] MCP tool `council-recall` works with scope parameter
- [ ] Pi extension `recall.unified` works with scope parameter
- [ ] All existing tests still pass (no regression)

**Dependencies:** Phases 1-4 complete

---

## Constraints

- **No new dependencies** — Use existing: sqlite3, Milvus, memsearch, FastMCP
- **Backward compatible** — `scope=None` (default) must work like current memsearch-only recall
- **Graceful degradation** — If Milvus is down, fall back to FTS5 (already implemented)
- **Token budget** — All responses must respect `max_tokens` parameter (default 4096)
- **No blocking** — DbIndexPoller must never block the main thread
- **Single source of truth** — All writes through RelationalStore, all reads through ContextRouter/MemoryLayer

---

## Success Criteria

- [ ] DbIndexPoller marks rows indexed only after successful upsert (Phase 1)
- [ ] 186 DB rows re-indexed to Milvus (Phase 2)
- [ ] Milvus contains DB-indexed content (verified: source prefix starts with `raw_session_memories:`, `session_diary:`, etc.)
- [ ] `recall.unified()` supports `scope` parameter, fires only relevant channels (Phase 3)
- [ ] No blind inclusions (no guaranteed 3072-char recent_context, no "last N regardless of query") (Phase 3)
- [ ] Similarity threshold filters results, empty response better than noise (Phase 4)
- [ ] Memory service starts with poller running (Phase 5)
- [ ] End-to-end recall test passes: query → scoped channels → thresholded results → provenanced output (Phase 5)
- [ ] All existing tests still pass (no regression)

---

## Caveats & Uncertainty

1. **Milvus embedding model** — Uses `pplx-embed-v1-0.6b` via local proxy at `http://127.0.0.1:18099/v1`. If this proxy is down, embeddings fail. The poller should handle this gracefully (already does via try/except).

2. **Session-trace files** — 299 existing entities in Milvus are session traces. These are noisy but not harmful. Consider a future phase to de-prioritize them (lower weight in RRF fusion) or exclude them entirely.

3. **Threshold calibration** — 0.60 is the starting point based on trial data. May need adjustment based on real usage. Too high = empty results. Too low = noise returns. Monitor and tune.

4. **Scope taxonomy** — The 6 scopes (default, decision, repair, recent, run, architecture) are based on observed query patterns. May need expansion as new patterns emerge. The `SCOPE_CHANNELS` dict is extensible.

5. **DB path** — The service uses `pipelines.db` (197 MB), not `memory.db` (452 KB, empty). Do not confuse the two. The config default is correct (`_DEFAULT_DB_PATH = ~/.council-memory/pipelines.db`).

---

## File Map (Complete)

| Action | File | Phase | Purpose |
|--------|------|-------|---------|
| Modify | `memory_service/db_poller.py` | 1 | Fix silent upsert failure |
| Modify | `memory_service/store.py` | 1 | Add index_failures column handling |
| Create | `migrations/02_index_failures.sql` | 1 | Migration for new column |
| Modify | `memory_service/__main__.py` | 2 | Add reindex CLI command |
| Create | `tests/test_db_poller_reindex.py` | 2 | Verify DB→Milvus bridge |
| Modify | `memory_service/layer.py` | 3,4 | Scope gating + threshold |
| Modify | `memory_service/mcp_server.py` | 3 | Update tool schema |
| Modify | `.pi/agent/extensions/council-tools/index.ts` | 3 | Update Pi extension |
| Modify | `memory_service/config.py` | 4 | Add recall_threshold config |
| Create | `tests/test_recall_overhaul_e2e.py` | 5 | End-to-end verification |
