# Memory Pipeline Redundancy Audit — Architecture Review & Fine-Tuning

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `ea8ef8` |
| Entity type | `handoff` |
| Short description | Audit all memory pipeline paths (JSONL → DB → index), identify redundant writes, propose streamlined architecture with single write + single index per insight |
| Status | `draft` |
| Source references | `/tmp/pipeline-analysis.md`, `memory_service/session_watcher.py`, `arc_summarizer/pipeline.py`, `memory_service/store.py`, `memory_service/http_endpoints.py` |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — review analysis, validate assumptions, implement Phase 1 (SessionWatcher → session_diary), then evaluate Phase 2+ |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_session-watcher-live-verification-report_a43f69.md` — live verification report
- `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_runtime-event-verification-report_a43f69.md` — runtime verification report
**Related codebases:** `/home/chief/.pi/agent/sessions/` (Pi session JSONL source)
**Key files for this task:**
- `memory_service/session_watcher.py` — SessionWatcher (JSONL → trim → reconcile)
- `memory_service/store.py` — RelationalStore (all DB write paths)
- `memory_service/http_endpoints.py` — HTTP tool dispatcher (upsert_summary endpoint)
- `memory_service/__init__.py` — MemoryService (upsert_session_diary, event hints)
- `arc_summarizer/pipeline.py` — ArcPipeline (tiered consolidation, reconciliation)
- `arc_summarizer/__init__.py` — ArcSummarizer (consolidate, summarize_session)
- `memory_service/sqlite_indexer.py` — SqliteIndexer (DB → memsearch poller)
- `memory_service/vector_store.py` — UnifiedVectorStore (session_diary → Milvus)
- `memory_service/layer.py` — MemoryLayer (artifact ingestion, recall)

---

## Phase 0: Complete Analysis (Pre-Read for Executing Agent)

### 0.1 Problem Essence

**Core problem:** Session knowledge must survive across sessions and be retrievable by meaning — without redundant writes that waste ARC calls, DB space, and indexing cycles.

**So what? chain:**
- "We have redundant DB writes" → so the same content exists in multiple tables
- So what? → so recall queries hit overlapping data, ARC sees duplicates, indexing re-processes the same content
- So what? → so we waste compute (ARC calls, embeddings, FTS triggers) and risk inconsistent state
- So what? → so agents can't trust the knowledge base, and verification becomes hard
- ← **GROUND TRUTH:** Each session insight should be written once, indexed once, and retrievable from one path.

**JTBD:** "When a session ends, extract what matters and make it searchable — without duplicates."

**Success criteria:**
- Each JSONL file processed exactly once (verified ✅ with idle fix)
- Each insight written to exactly one canonical table
- Each table indexed by exactly one indexer
- ARC called only when new, unique content is available

### 0.2 Assumptions Challenged

| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| "session_diary and memory_entries serve different purposes" | Historical | session_diary = manual upserts, memory_entries = ARC output + raw. But both contain session summaries. Consolidation reads from memory_entries, not session_diary. | **Discard** — they overlap |
| "consolidation_cache is needed for ARC output" | Technical | consolidation_cache has 0 rows. ArcPipeline writes to memory_entries (entry_type='diary') instead. Schema exists but is unused. | **Discard** — dead table |
| "raw_session_memories is needed for auto-detected messages" | Technical | 0 rows. The `upsert_summary` endpoint routes `auto-detected-assistant-message` here, but no production path generates this source type. | **Investigate** — may be dead |
| "SqliteIndexer should NOT index session_diary" | Technical | Comment in sqlite_indexer.py says session_diary is "handled by UnifiedVectorStore". But this means session_diary content is NOT searchable via memsearch (poller). | **Discard** — creates search gap |
| "work_items should be indexed by SqliteIndexer" | Technical | work_items are indexed by poller AND created by SessionWatcher reconciliation. Same task signal exists in both. | **Keep but dedup** |
| "UnifiedVectorStore should index consolidation_cache" | Technical | consolidation_cache is empty. Indexing an empty table is a no-op. | **Discard** — waste |

### 0.3 Ground Truths

1. **JSONL is the durable source of truth** — Pi writes JSONL files. All downstream knowledge derives from these files. They are read-only.
2. **Each session produces exactly one set of insights** — A JSONL file contains one conversation. The insights (decisions, tasks, context) are fixed once the session ends.
3. **ARC is expensive** — Each ARC call costs compute time and tokens. Calling ARC on the same content multiple times is waste.
4. **Search must be unified** — Users query once and get results from all knowledge. Fragmented search paths (memsearch for some tables, Milvus for others) create blind spots.
5. **work_items are actionable, not archival** — 109 of 112 work_items are "proposed" (never promoted). They're task signals, not archival records. They shouldn't duplicate session content.

---

## Phase 1: Current Architecture — As-Built

### 1.1 Data Flow Map (6 paths, 5 write targets, 2 indexers)

```
JSONL files (Pi sessions dir, ~/.pi/agent/sessions/)
  │
  ├─→ SessionWatcher._scan_and_process() [daemon, 15s poll]
  │    │
  │    ├─→ _parse_jsonl() → turns (list of {role, content})
  │    ├─→ _classify() → session_mode (code/research/mixed)
  │    ├─→ _trim_session() → structured dict
  │    │    └─→ SessionAnalyzer.trim_session()
  │    ├─→ _reconcile() → ArcPipeline.reconcile_tasks()
  │    │    ├─→ ArcClient.extract_tasks() → ARC call #1 (task extraction)
  │    │    └─→ RelationalStore.reconcile_arc_delta() → work_items INSERT
  │    └─→ _wake("daily_summary_saved") → IdleWindowScheduler
  │
  │    NOTE: SessionWatcher does NOT write session_diary.
  │    NOTE: SessionWatcher does NOT write memory_entries.
  │    NOTE: Only creates work_items via reconciliation.
  │
  ├─→ upsert_summary (HTTP: POST /v1/memory/tool/upsert_summary)
  │    │
  │    ├─→ source=="auto-detected-assistant-message"
  │    │    └─→ store.upsert_raw_session_memory() → raw_session_memories INSERT
  │    │         [0 rows in production — DEAD PATH]
  │    │
  │    └─→ else (structured entries)
  │         └─→ store.upsert_session_diary() → session_diary INSERT
  │              ├─→ parses summary_text into structured fields
  │              ├─→ extracts: decisions, open_items, work_completed, session_context
  │              └─→ _wake_scheduler("daily_summary_saved")
  │
  ├─→ ArcPipeline.run_tiered_consolidation(tier_id) [scheduler-triggered]
  │    │
  │    ├─→ _gather_tier_input(tier_id) → reads memory_entries or memory_rollups
  │    │    ├─→ tier="daily" → memory_entries(entry_type="raw") or "diary"
  │    │    └─→ tier="short/weekly/bimonthly" → memory_rollups or memory_entries
  │    │
  │    ├─→ ArcClient.consolidate_tiered() → ARC call #2 (narrative consolidation)
  │    │    └─→ Returns YAML with: narrative, summary, decisions, open_items, etc.
  │    │
  │    ├─→ _write_tier_output() → memory_entries INSERT (entry_type="diary")
  │    │    └─→ store.upsert_memory_entry(entry_type="diary", tier=tier_id, ...)
  │    │
  │    ├─→ reconcile_tasks() → work_items INSERT (may duplicate SessionWatcher writes)
  │    │    └─→ ArcClient.extract_tasks() → ARC call #3 (task extraction from consolidation)
  │    │
  │    └─→ reconcile_deviations() [weekly/bimonthly only]
  │         └─→ plan_deviations INSERT
  │
  └─→ [NO PATH: JSONL → session_diary directly]
       [NO PATH: JSONL → memory_entries directly]
```

### 1.2 Indexing Layer (2 indexers, partial overlap)

```
SqliteIndexer (Poller) — exports DB → markdown → memsearch (Milvus via memsearch API)
  Polls every cycle, writes to staging dir, calls memsearch.index()
  Tables indexed:
    ├─ memory_entries        (232 rows) → "memory_entries:{id}"
    ├─ memory_rollups        (2 rows)   → "memory_rollups:{id}"
    ├─ review_findings       (11 rows)  → "review_findings:{id}"
    ├─ work_items            (112 rows) → "work_items:{id}"
    ├─ knowledge_cards       (0 rows)   → "knowledge_cards:{id}"
    ├─ chat_messages         (9 rows)   → "chat_messages:{id}"
    ├─ notes                 (0 rows)   → "notes:{id}"
    └─ documents             (0 rows)   → "documents:{id}"
  NOT indexed: session_diary, raw_session_memories, consolidation_cache

UnifiedVectorStore — session_diary + consolidation_cache → Milvus (direct)
  Uses pplx-embed-v1 on :18099 for embeddings
  Tables indexed:
    ├─ session_diary         (5 rows)   → source="session_diary"
    └─ consolidation_cache   (0 rows)   → source="consolidation_cache" [DEAD]
  NOT indexed: memory_entries, work_items, raw_session_memories
```

### 1.3 DB State (Production, Post-Idle Fix)

| Table | Rows | Entry Types | Status | Indexed By |
|-------|------|-------------|--------|------------|
| `memory_entries` | 232 | 197 raw, 30 diary, 5 summary | Active | SqliteIndexer (memsearch) |
| `session_diary` | 5 | all manual upserts | Active | UnifiedVectorStore (Milvus) |
| `work_items` | 112 | 109 proposed, 3 open | Active | SqliteIndexer (memsearch) |
| `consolidation_cache` | 0 | — | **DEAD** | UnifiedVectorStore (Milvus, no-op) |
| `raw_session_memories` | 0 | — | **DEAD** | Neither |
| `memory_rollups` | 2 | — | Active | SqliteIndexer (memsearch) |
| `chat_messages` | 9 | — | Active | SqliteIndexer (memsearch) |
| `review_findings` | 11 | — | Active | SqliteIndexer (memsearch) |
| `artifacts` | 26 | — | Active | FTS triggers (internal) |
| `event_log` | 29 | — | Active | FTS triggers (internal) |

### 1.4 Key Code Paths

**SessionWatcher._process_session()** — `memory_service/session_watcher.py:207`
```
_parse_jsonl() → _classify() → _trim_session() → _reconcile() → _wake()
```
Writes: `work_items` (via ArcPipeline.reconcile_tasks → reconcile_arc_delta)
Does NOT write: `session_diary`, `memory_entries`, `consolidation_cache`

**upsert_summary HTTP endpoint** — `memory_service/http_endpoints.py:324`
```
if source == "auto-detected-assistant-message":
    → store.upsert_raw_session_memory() → raw_session_memories [DEAD]
else:
    → store.upsert_session_diary() → session_diary
```

**ArcPipeline.run_tiered_consolidation()** — `arc_summarizer/pipeline.py:73`
```
_gather_tier_input() → ArcClient.consolidate_tiered() → _write_tier_output() → reconcile_tasks()
```
Writes: `memory_entries` (entry_type="diary"), `work_items` (via reconciliation)

**RelationalStore.upsert_session_diary()** — `memory_service/store.py:1029`
```
Parses summary_text → extracts sections → INSERT OR REPLACE INTO session_diary
```

**RelationalStore.upsert_raw_session_memory()** — `memory_service/store.py:1095`
```
INSERT OR REPLACE INTO raw_session_memories (trace_id, date, source_file, raw_text, ...)
```

**SqliteIndexer._export_table()** — `memory_service/sqlite_indexer.py:244`
```
Reads DB rows → writes markdown to staging dir → memsearch.index()
```

**UnifiedVectorStore.reindex_existing_data()** — `memory_service/vector_store.py:220`
```
Queries session_diary → embeds → inserts into Milvus
Queries consolidation_cache → embeds → inserts into Milvus [no-op, empty]
```

---

## Phase 2: Redundancy Audit

### 2.1 Redundancy #1: Same JSONL → 2 ARC Calls

**Path A:** JSONL → SessionWatcher → ArcClient.extract_tasks() → work_items
**Path B:** JSONL → (not directly) → ArcPipeline.consolidate_tiered() → memory_entries

These are NOT direct duplicates (different ARC endpoints), but both derive from the same JSONL and both call ARC.

**Impact:** Medium. Two ARC calls per session. Could be one call that produces both narrative summary and task signals.

**Evidence:** Live verification showed SessionWatcher calling `task-extraction` endpoint for each JSONL file (18 files = 18 ARC calls during verification window).

### 2.2 Redundancy #2: session_diary vs memory_entries(diary) — Same Content, 2 Search Paths

**session_diary:** Manual upserts via HTTP. Structured fields (decisions, open_items, work_completed). Indexed by UnifiedVectorStore (Milvus).

**memory_entries (diary):** ARC consolidation output. Semi-structured (body text with headers). Indexed by SqliteIndexer (memsearch).

Both contain session summaries. Same content searchable through two different backends with different semantics (Milvus vector search vs memsearch chunk search).

**Impact:** High. Users/agents query through `recall.unified()` which hits both channels. Same insight appears twice with different metadata.

### 2.3 Redundancy #3: work_items Indexed by Poller + Derived from ARC

work_items are created by ARC reconciliation AND indexed by SqliteIndexer. The same task signal exists as:
- A structured work_item row (with status, kind, priority, project_id)
- A markdown export in memsearch (title + description + metadata)

**Impact:** Low-Medium. Not a true duplicate — work_items are actionable, memsearch is searchable. But the same text is embedded twice.

### 2.4 Redundancy #4: Dead Tables with Live Schemas

| Table | Rows | Schema Exists | Indexed | Maintenance Cost |
|-------|------|--------------|---------|-----------------|
| `consolidation_cache` | 0 | ✅ | ✅ (Milvus, no-op) | Schema + triggers + index config + FTS |
| `raw_session_memories` | 0 | ✅ | ❌ | Schema + triggers + migration SQL |

**Impact:** Low. Dead weight but not actively harmful. Adds confusion during audits.

### 2.5 Critical Gap: SessionWatcher Does NOT Write session_diary

SessionWatcher processes JSONL files but only creates work_items. It does NOT upsert a session_diary entry. This means:

- Session content exists in work_items (task signals only, 109 proposed)
- Session narrative is NOT in session_diary (only 5 entries, all manual)
- Session narrative is NOT in memory_entries (no path from JSONL → memory_entries)
- **Result:** Most sessions have NO searchable narrative summary

**Impact:** High. ~17 JSONL files processed, but only 5 session_diary entries (all from manual verification upserts). The other 12 sessions have work_items but no narrative.

---

## Phase 3: Proposed Streamlined Architecture

### 3.1 Principle: One Write, One Index, One Search Path

```
JSONL files (source of truth, read-only)
  │
  └─→ SessionWatcher (single entry point, 15s poll)
       │
       ├─→ _parse_jsonl() → turns
       ├─→ _classify() → session_mode
       ├─→ _trim_session() → structured dict
       │
       ├─→ ArcClient.extract_and_summarize() → ONE ARC call
       │    │
       │    ├─→ narrative summary (for session_diary)
       │    └─→ task signals (for work_items)
       │
       ├─→ store.upsert_session_diary() → ONE write [NEW]
       │    └─→ session_context, decisions, open_items, work_completed
       │
       ├─→ ArcPipeline.reconcile_tasks() → incremental writes
       │    └─→ only NEW tasks (fuzzy dedup against existing)
       │
       └─→ _wake("session_processed") → scheduler
```

### 3.2 Indexing: Single Unified Indexer

```
UnifiedVectorStore (replaces both SqliteIndexer + current UnifiedVectorStore)
  │
  ├─→ session_diary → Milvus (primary search, all session summaries)
  ├─→ work_items → Milvus (actionable search)
  └─→ memory_entries → Milvus (legacy, phased out)
```

### 3.3 What Changes

| Component | Current | Proposed | Rationale |
|-----------|---------|----------|-----------|
| SessionWatcher output | work_items only | session_diary + work_items | Every session gets a summary |
| ARC calls per session | 2 (extract + consolidate) | 1 (extract_and_summarize) | Combine into single call |
| session_diary writes | Manual upsert only | SessionWatcher + manual | Automated from JSONL |
| memory_entries (diary) | ARC tier output | Deprecated | Merge into session_diary |
| consolidation_cache | 0 rows, dead | Drop or repurpose | No code writes to it |
| raw_session_memories | 0 rows, dead | Drop | No code writes to it |
| SqliteIndexer | 8 tables → memsearch | Drop | UnifiedVectorStore handles all |
| UnifiedVectorStore | session_diary + consolidation_cache | session_diary + work_items | Single search backend |

---

## Phase 4: Implementation Plan

### Phase 4A: SessionWatcher Writes session_diary (Immediate, Low Risk)

**What:** Add `store.upsert_session_diary()` call to SessionWatcher._process_session() after reconciliation.

**Files to Modify:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/session_watcher.py` | Add session_diary write in _process_session() |

**Steps:**
1. In `_process_session()`, after `_reconcile()` and before `_wake()`, add:
   ```python
   self._upsert_session_diary(trimmed, jsonl_path)
   ```
2. Implement `_upsert_session_diary()` that builds summary_text from the trimmed dict and calls `self._memory_service._store.upsert_session_diary()`
3. Handle case where `_memory_service` is None (no-op, log debug)
4. Add to existing tests: verify session_diary entry created after _process_session()

**Tests:**
1. `test_process_session_creates_session_diary` — Full flow, assert session_diary count increases by 1
2. `test_upsert_session_diary_handles_none_memory_service` — No crash when memory_service is None
3. `test_upsert_session_diary_builds_summary_from_trimmed` — trimmed dict → summary_text mapping

**Dependencies:** None (Phase 4B-4D can run in parallel)

**Estimated effort:** ~2 hours

### Phase 4B: Combine ARC Calls (Medium Effort)

**What:** ArcClient.extract_and_summarize() returns both narrative summary and task signals in one call.

**Files to Modify:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/client.py` | Add extract_and_summarize() method |
| Modify | `arc_summarizer/prompts.py` | Add combined prompt template |
| Modify | `memory_service/session_watcher.py` | Use combined call |

**Steps:**
1. Create `extract_and_summarize()` in ArcClient that sends one prompt requesting both narrative summary and task signals
2. Parse combined YAML response into {narrative: str, tasks: dict}
3. Update SessionWatcher to use combined call instead of separate _trim_session() + reconcile_tasks()
4. Add fallback: if combined call fails, use existing separate calls

**Tests:**
1. `test_extract_and_summarize_returns_both` — Assert response has narrative and tasks keys
2. `test_extract_and_summarize_fallback` — On failure, falls back to separate calls
3. Integration test: full SessionWatcher flow with combined call

**Dependencies:** None (can run parallel to 4A)

**Estimated effort:** ~4 hours

### Phase 4C: Drop Dead Tables (Cleanup)

**What:** Remove `consolidation_cache` and `raw_session_memories` from schema and code.

**Files to Modify:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `migrations_council_core/` | Add migration to drop tables |
| Modify | `memory_service/store.py` | Remove upsert/query methods |
| Modify | `memory_service/vector_store.py` | Remove consolidation_cache indexing |
| Modify | `memory_service/http_endpoints.py` | Remove auto-detected routing |

**Steps:**
1. Verify no production code references `consolidation_cache` or `raw_session_memories`
2. Create migration SQL: `DROP TABLE IF EXISTS consolidation_cache; DROP TABLE IF EXISTS raw_session_memories;`
3. Remove `upsert_consolidation_cache()`, `query_consolidation_cache()` from store.py
4. Remove `upsert_raw_session_memory()`, `query_raw_session_memories()` from store.py
5. Remove consolidation_cache from UnifiedVectorStore.reindex_existing_data()
6. Simplify upsert_summary endpoint (remove auto-detected routing)

**Tests:**
1. Verify all existing tests pass after removal
2. Verify migration is idempotent (safe to re-run)

**Dependencies:** None (can run parallel to 4A, 4B)

**Estimated effort:** ~1 hour

### Phase 4D: Merge SqliteIndexer into UnifiedVectorStore (Larger Refactor)

**What:** UnifiedVectorStore indexes all tables currently handled by SqliteIndexer. Drop SqliteIndexer.

**Files to Modify:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/vector_store.py` | Add support for all poller tables |
| Modify | `memory_service/__init__.py` | Remove SqliteIndexer init |
| Delete | `memory_service/sqlite_indexer.py` | Remove poller |

**Steps:**
1. Extend UnifiedVectorStore to index: memory_entries, memory_rollups, review_findings, work_items, knowledge_cards, chat_messages, notes, documents
2. Add dedup by (source, source_id) for all tables
3. Remove SqliteIndexer from MemoryService._init_components()
4. Update Memsearch config to use UnifiedVectorStore as primary indexer

**Tests:**
1. Verify all tables are indexed after reindex
2. Verify search returns results from all sources
3. Verify dedup works (re-indexing same data doesn't duplicate)

**Dependencies:** Phase 4A, 4B, 4C (must complete first)

**Estimated effort:** ~8 hours

---

## Phase 5: Execution Order & Dependencies

```
Phase 4A (session_diary write) ──┐
                                  ├─→ All parallel, no dependencies
Phase 4B (combine ARC calls) ────┤                                  │
                                  │                                  ▼
Phase 4C (drop dead tables) ─────┤                          Phase 4D
                                  │                        (merge indexers)
                                  │                          ▲
                                  └──────────────────────────┘
```

---

## Constraints

- **Read-only on JSONL:** Never modify Pi's session files. Touch only for mtime updates during testing.
- **Non-destructive:** Do not delete or modify existing database records. Use migrations for schema changes.
- **Backward compatible:** Existing recall paths (memory_entries, session_diary) must continue working during migration.
- **Idempotent migrations:** All schema changes must be safe to re-run on existing databases.
- **No ARC call increase:** Combined call (Phase 4B) must not increase ARC calls. Target: 50% reduction.
- **Search parity:** After merging indexers (Phase 4D), all previously searchable content must remain searchable.

---

## Success Criteria

- [ ] SessionWatcher writes session_diary for every processed JSONL (Phase 4A)
- [ ] Every session has both work_items AND session_diary entry (no more gap)
- [ ] ARC calls per session reduced from 2 to 1 (Phase 4B)
- [ ] Dead tables removed from schema and code (Phase 4C)
- [ ] Single indexer handles all tables (Phase 4D)
- [ ] All existing tests pass (no regression)
- [ ] Live verification: new service processes JSONL → session_diary + work_items in one pass
- [ ] Search returns session summaries from unified backend
- [ ] `consolidation_cache` and `raw_session_memories` tables dropped
- [ ] SqliteIndexer removed from MemoryService init

---

## Caveats & Uncertainty

1. **ARC combined prompt (Phase 4B):** Requires prompt engineering. The current `extract_tasks()` and `consolidate_tiered()` use different prompts. Combining them may require a new prompt that the model hasn't been tuned for. Risk: lower quality output.

2. **UnifiedVectorStore capacity (Phase 4D):** Currently indexes ~5 session_diary entries. After merging, would index 232 memory_entries + 112 work_items + 11 review_findings + others = ~400+ entries. Milvus embedding cost: ~400 * 1024-dim vectors. Need to verify Milvus Lite can handle this.

3. **memory_entries migration:** 232 rows in memory_entries (197 raw, 30 diary, 5 summary). The "diary" entries overlap with session_diary purpose. Decision needed: migrate diary entries to session_diary, or keep both and dedup at query time.

4. **SessionWatcher session_diary format:** Current upsert_session_diary() expects Markdown text with `##` headers. SessionWatcher produces a structured dict. Need to map dict → Markdown format, or add a new upsert path that accepts structured input directly.

---

## Appendix A: Complete Redundancy Analysis

(See `/tmp/pipeline-analysis.md` for the full 290-line analysis with architecture diagrams, assumption challenges, stress tests, and detailed migration strategy.)

### Key Findings Summary

| Finding | Severity | Action |
|---------|----------|--------|
| SessionWatcher does NOT write session_diary | High | Phase 4A |
| 2 ARC calls per session (extract + consolidate) | Medium | Phase 4B |
| consolidation_cache: 0 rows, dead schema | Low | Phase 4C |
| raw_session_memories: 0 rows, dead schema | Low | Phase 4C |
| SqliteIndexer + UnifiedVectorStore partial overlap | Medium | Phase 4D |
| memory_entries(diary) overlaps session_diary purpose | High | Investigate in Phase 4D |

### Production Metrics (Baseline)

| Metric | Value |
|--------|-------|
| JSONL files processed (last 24h) | ~17 |
| session_diary entries | 5 (all manual) |
| work_items created | 112 (109 proposed) |
| ARC calls during verification | 18 (one per JSONL) |
| memory_entries | 232 (197 raw, 30 diary) |
| consolidation_cache | 0 |
| raw_session_memories | 0 |
| SqliteIndexer tables | 8 (6 with data) |
| UnifiedVectorStore sources | 2 (1 with data) |

