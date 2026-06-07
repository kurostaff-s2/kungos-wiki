# Memory Pipeline Redundancy Audit — Streamlined Architecture with Carry-Forward Integration

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `ea8ef8` |
| Entity type | `handoff` |
| Short description | Streamline JSONL→MD→DB pipeline, integrate carry_forward for deviation/project/missed-task tracking, drop dead tables, separate review service |
| Status | `in_progress` |
| Source references | `memory_service/session_watcher.py`, `arc_summarizer/pipeline.py`, `memory_service/store.py`, `memory_service/sqlite_indexer.py`, `memory_service/vector_store.py`, `memory_service/layer.py` |
| Generated | `07-06-2026` (updated `07-06-2026`) |
| Next action / owner | Next session agent — implement Phase 4A (SessionWatcher→MD→wired services), then Phase 4B (carry_forward integration), then Phase 4C (cleanup) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Database:** `~/.council-memory/council_core.db` (3.9MB, live)
**JSONL source:** `~/.pi/agent/sessions/` (20+ session files)
**Reference docs:**
- `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_session-watcher-live-verification-report_a43f69.md`
- `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_runtime-event-verification-report_a43f69.md`

**Key files:**
| File | Role |
|------|------|
| `memory_service/session_watcher.py` | SessionWatcher (JSONL→trim→reconcile) |
| `memory_service/store.py` | RelationalStore (all DB write paths) |
| `memory_service/http_endpoints.py` | HTTP tool dispatcher |
| `memory_service/__init__.py` | MemoryService (component wiring) |
| `arc_summarizer/pipeline.py` | ArcPipeline (tiered consolidation) |
| `arc_summarizer/scheduler.py` | IdleWindowScheduler (trigger, not writer) |
| `memory_service/sqlite_indexer.py` | SqliteIndexer (DB→memsearch) |
| `memory_service/vector_store.py` | UnifiedVectorStore (session_diary→Milvus) |
| `memory_service/layer.py` | MemoryLayer (recall, system_health) |
| `memory_service/review.py` | ReviewService (separate domain) |

---

## Phase 0: Problem Essence

### 0.1 Core Problem

**Session knowledge must survive across sessions and be retrievable — without redundant writes, dead tables, or orphaned tracking modules.**

**So what? chain:**
- "We have redundant DB writes" → same content in multiple tables (session_diary vs memory_entries diary)
- So what? → recall queries hit overlapping data, ARC sees duplicates, indexing re-processes
- So what? → wasted compute (ARC calls, embeddings, FTS triggers) + inconsistent state
- So what? → carry_forward has zero writers, deviations have no carry-forward link, missed tasks vanish
- ← **GROUND TRUTH:** Each session insight written once, indexed once, tracked across tiers via carry_forward.

**JTBD:** "When a session ends, extract what matters, make it searchable, and carry forward what's unresolved — without duplicates or orphaned data."

**Success criteria:**
- [ ] Each JSONL file processed exactly once → MD (canonical intermediate)
- [ ] MD wired to session_diary (narrative) + work_items (tasks) + memindex (search)
- [ ] ArcPipeline writes memory_rollups (not memory_entries diary)
- [ ] carry_forward tracks deviations, missed tasks, project continuity
- [ ] Dead tables dropped (consolidation_cache, raw_session_memories)
- [ ] Review service separate (council/subagent domain only)
- [ ] Single indexer handles all tables (SqliteIndexer + UnifiedVectorStore unified)

---

## Phase 1: Current Architecture — As-Built

### 1.1 Data Flow Map (6 paths, 5 write targets, 2 indexers, 1 orphan)

```
JSONL files (~/.pi/agent/sessions/**/*.jsonl, read-only, 20+ files)
  │
  ├─→ SessionWatcher._scan_and_process() [daemon, 15s poll]
  │    │
  │    ├─→ _parse_jsonl() → turns: [{role, content}]
  │    ├─→ _classify() → session_mode (code/research/mixed)
  │    ├─→ _trim_session() → trimmed dict
  │    │    └─→ SessionAnalyzer.trim_session()
  │    ├─→ _reconcile() → ArcPipeline.reconcile_tasks()
  │    │    ├─→ ArcClient.extract_tasks() → ARC CALL #1
  │    │    └─→ RelationalStore.reconcile_arc_delta() → work_items INSERT
  │    └─→ _wake("daily_summary_saved") → IdleWindowScheduler
  │
  │    NOTE: SessionWatcher does NOT write session_diary.
  │    NOTE: SessionWatcher does NOT write memory_entries.
  │    NOTE: SessionWatcher does NOT write MD to disk.
  │    NOTE: Only creates work_items via reconciliation.
  │
  ├─→ upsert_summary (HTTP: POST /v1/memory/tool/upsert_summary)
  │    │
  │    ├─→ source=="auto-detected-assistant-message"
  │    │    └─→ store.upsert_raw_session_memory() → raw_session_memories [DEAD, 0 rows]
  │    │
  │    └─→ else (structured entries)
  │         └─→ store.upsert_session_diary() → session_diary INSERT
  │              ├─→ parses summary_text → decisions, open_items, work_completed
  │              └─→ _wake_scheduler("daily_summary_saved")
  │
  ├─→ super_council.py chat summary path
  │    │
  │    ├─→ ARC/LLM summarization → summary_text (Markdown)
  │    ├─→ Save to ~/.council-memory/chat-summaries/*.md
  │    ├─→ MemIndex.index_file() → memsearch (Milvus)
  │    ├─→ upsert_session_diary() → session_diary INSERT
  │    └─→ _wake_scheduler("chat_summary_saved")
  │
  ├─→ ArcPipeline.run_tiered_consolidation(tier_id) [scheduler-triggered]
  │    │
  │    ├─→ _gather_tier_input(tier_id)
  │    │    ├─→ tier="daily" → memory_entries(raw) or memory_entries(diary)
  │    │    └─→ tier="short/weekly/bimonthly" → memory_rollups or memory_entries
  │    │
  │    ├─→ ArcClient.consolidate_tiered() → ARC CALL #2
  │    │    └─→ Returns YAML: narrative, summary, decisions, open_items
  │    │
  │    ├─→ _write_tier_output() → memory_entries INSERT (entry_type="diary")
  │    │    └─→ store.upsert_memory_entry(entry_type="diary", tier=tier_id, ...)
  │    │    └─→ NOTE: Comment says "Replaces session_diary (zombie table)"
  │    │          but session_diary is NOT zombie — it's the canonical narrative store
  │    │
  │    ├─→ reconcile_tasks() → work_items INSERT (may duplicate SessionWatcher)
  │    │    └─→ ArcClient.extract_tasks() → ARC CALL #3
  │    │
  │    └─→ reconcile_deviations() [weekly/bimonthly only]
  │         └─→ plan_deviations INSERT
  │
  └─→ [ORPHAN: carry_forward]
       ├─→ Schema exists: id, project_id, tier, kind, text, priority
       ├─→ linked_work_item_id, linked_deviation_id (FOREIGN KEYS)
       ├─→ Writer: create_carry_forward() — EXISTS, ZERO CALLERS
       ├─→ Reader: ArcPipeline._gather_plan_text() — READS, RETURNS NOTHING
       ├─→ 1 stale row (expired, "Need to finish API")
       └─→ STATUS: DEAD WRITER, LIVE READER (reads nothing)
```

### 1.2 Indexing Layer (3 indexers, partial overlap, 1 gap)

```
SqliteIndexer (Poller) — DB rows → markdown → memsearch (Milvus)
  Polls every 30s, writes to staging dir, calls memsearch.index()
  Tables indexed:
    ├─ memory_entries        (235 rows) → "memory_entries:{id}"
    ├─ memory_rollups        (2 rows)   → "memory_rollups:{id}"
    ├─ review_findings       (11 rows)  → "review_findings:{id}"
    ├─ work_items            (118 rows) → "work_items:{id}"
    ├─ knowledge_cards       (0 rows)   → "knowledge_cards:{id}"
    ├─ chat_messages         (9 rows)   → "chat_messages:{id}"
    ├─ notes                 (0 rows)   → "notes:{id}"
    └─ documents             (0 rows)   → "documents:{id}"
  NOT indexed: session_diary, raw_session_memories, consolidation_cache,
               carry_forward, plan_deviations, plan_deviations_events

UnifiedVectorStore — session_diary + consolidation_cache → Milvus (direct)
  Uses pplx-embed-v1 on :18099 for embeddings
  Tables indexed:
    ├─ session_diary         (5 rows)   → source="session_diary"
    └─ consolidation_cache   (0 rows)   → source="consolidation_cache" [DEAD]
  NOT indexed: memory_entries, work_items, carry_forward, plan_deviations

MemIndex (index.py) — Individual files → memsearch
  Used by: super_council.py (chat summary files), manual indexing
  NOT used by: SessionWatcher (no MD files written)
```

### 1.3 DB State (Production, Post-Idle Fix)

| Table | Rows | Entry Types | Status | Indexed By |
|-------|------|-------------|--------|------------|
| `memory_entries` | 235 | 200 raw, 29 diary, 7 summary | Active | SqliteIndexer (memsearch) + FTS |
| `session_diary` | 5 | all manual/test upserts | Active | UnifiedVectorStore (Milvus) + FTS |
| `work_items` | 118 | 115 proposed, 3 open | Active | SqliteIndexer (memsearch) + FTS |
| `memory_rollups` | 2 | weekly (stale) | Active | SqliteIndexer (memsearch) |
| `plan_deviations` | 1 | unplanned (test) | Active | SqliteIndexer (memsearch) + FTS |
| `plan_deviations_events` | 2 | created, status_changed | Active | **NOT indexed** |
| `carry_forward` | 1 | unresolved_work (expired) | **ORPHAN** | **NOT indexed** |
| `reviews` | 2 | active | Active | SqliteIndexer (memsearch) + FTS |
| `review_findings` | 11 | various severities | Active | SqliteIndexer (memsearch) + FTS |
| `workflow_runs` | 3 | AGENT_VALIDATE | Active | **NOT indexed** |
| `projects` | 2 | council, test-project | Active | **NOT indexed** |
| `workspace_bindings` | 2 | path→project mapping | Active | **NOT indexed** |
| `chat_messages` | 9 | — | Active | SqliteIndexer (memsearch) + FTS |
| `artifacts` | 26 | — | Active | FTS triggers (internal) |
| `event_log` | 29 | — | Active | FTS triggers (internal) |
| `consolidation_cache` | 0 | — | **DEAD** | UnifiedVectorStore (no-op) |
| `raw_session_memories` | 0 | — | **DEAD** | Neither |
| `knowledge_cards` | 0 | — | Empty | SqliteIndexer (no-op) |
| `notes` | 0 | — | Empty | SqliteIndexer (no-op) |
| `documents` | 0 | — | Empty | SqliteIndexer (no-op) |

### 1.4 The Three Narrative Tables — What Is What?

| Table | Purpose | Writer | Rows | Indexed |
|-------|---------|--------|------|---------|
| **`session_diary`** | Structured session narrative (decisions, open_items, work_completed) | `upsert_session_diary()` (chat summaries, HTTP) | 5 | Milvus + FTS |
| **`memory_entries`** | Unified memory store (raw, diary, summary) | ArcPipeline, MCP server | 235 | memsearch + FTS |
| **`memory_rollups`** | ARC tiered consolidation output | `upsert_memory_rollup()` — **NEVER CALLED** | 2 | memsearch |

**The disconnect:** ArcPipeline writes to `memory_entries` (entry_type="diary") with comment "Replaces session_diary (zombie table)." But session_diary is the canonical narrative store with structured fields. memory_rollups is the intended ARC output table but has zero callers.

**Result:** Narrative is fragmented across 3 tables. session_diary (5 structured) + memory_entries diary (29 semi-structured) + memory_rollups (2 stale).

---

## Phase 2: Redundancy & Gap Audit

### 2.1 Redundancy #1: Same JSONL → 2 ARC Calls

**Path A:** JSONL → SessionWatcher → ArcClient.extract_tasks() → work_items
**Path B:** JSONL → (later) → ArcPipeline.consolidate_tiered() → memory_entries(diary)

Both derive from same JSONL, both call ARC. Could be one call producing narrative + tasks.

**Impact:** Medium. ~52 ARC calls/day (20 sessions × 2 calls + 12 consolidation cycles).

### 2.2 Redundancy #2: session_diary vs memory_entries(diary) — Same Purpose, 2 Tables

**session_diary:** Structured fields (decisions, open_items, work_completed). 5 rows. Milvus + FTS.
**memory_entries(diary):** Semi-structured body text. 29 rows. memsearch + FTS.

Same session narrative, two schemas, two search backends.

**Impact:** High. `recall.unified()` hits both channels. Same insight appears twice with different metadata.

### 2.3 Redundancy #3: work_items Indexed by Poller + Derived from ARC

work_items created by ARC reconciliation AND indexed by SqliteIndexer. Same task signal exists as structured row + markdown export.

**Impact:** Low-Medium. Not true duplicate — work_items are actionable, memsearch is searchable. But text embedded twice.

### 2.4 Gap #1: carry_forward — Dead Writer, Live Reader

| Aspect | Status |
|--------|--------|
| Schema | ✅ Complete (id, project_id, tier, kind, text, priority, linked_work_item_id, linked_deviation_id) |
| Writer method | ✅ `create_carry_forward()` exists |
| Callers | ❌ **ZERO** — no production code calls it |
| Reader | ✅ `ArcPipeline._gather_plan_text()` reads carry_forward |
| Data | 1 stale row (expired, "Need to finish API") |
| Linked tables | `linked_work_item_id` → work_items, `linked_deviation_id` → plan_deviations |
| Indexing | ❌ **NOT indexed** (no memsearch, no FTS) |

**Impact:** High. carry_forward is designed to track unresolved work, deviations, and project continuity across consolidation tiers. Without writers, it's a ghost table.

### 2.5 Gap #2: plan_deviations_events Not Indexed

Deviation audit trail exists (2 rows) but is not searchable via memsearch or FTS. Can't query "what deviations were approved?" or "when was deviation X closed?"

**Impact:** Medium. Deviation history is opaque.

### 2.6 Gap #3: SessionWatcher Does NOT Write session_diary

SessionWatcher processes JSONL but only creates work_items. No session_diary entry, no MD file, no narrative summary.

**Impact:** High. ~20 JSONL files processed, only 5 session_diary entries (all manual). Most sessions have tasks but no narrative.

### 2.7 Dead Tables

| Table | Rows | Schema | Indexed | Action |
|-------|------|--------|---------|--------|
| `consolidation_cache` | 0 | ✅ | ✅ (Milvus, no-op) | **DROP** |
| `raw_session_memories` | 0 | ✅ | ❌ | **DROP** |

---

## Phase 3: Proposed Streamlined Architecture

### 3.1 Principle: One Write (MD), Wired Consumers, Separate Review

```
JSONL files (source of truth, read-only)
  │
  └─→ SessionWatcher (single pipeline, 15s poll)
       │
       ├─→ _parse_jsonl() → turns
       ├─→ _classify() → session_mode
       ├─→ _trim_session() → trimmed dict
       │
       ├─→ _write_session_md() → MD file (CANONICAL WRITE)
       │    └─→ ~/.council-memory/sessions/{timestamp}.md
       │
       ├─→ WIRED CONSUMERS (independent, parallel-safe):
       │    │
       │    ├─→ _wire_session_diary() → session_diary (CANONICAL NARRATIVE)
       │    │    └─→ decisions, open_items, work_completed, session_context
       │    │
       │    ├─→ _wire_work_items() → work_items (CANONICAL TASK LEDGER)
       │    │    └─→ TaskReconciler (fuzzy dedup, confidence gating)
       │    │
       │    └─→ _wire_memindex() → memsearch (VECTOR SEARCH)
       │         └─→ MemIndex.index_file() (fire-and-forget)
       │
       └─→ _wake("session_processed") → IdleWindowScheduler
```

### 3.2 The MD Format (Canonical Intermediate)

**Design constraints:**
1. **Section headers must match consumer extraction patterns** — `upsert_session_diary()._extract_section()` uses regex `^#{1,3}\s+{header}` to parse sections. Headers MUST match.
2. **Small decisions must survive** — A decision like "use `dict.get()` not `if key in d`" is small but high-value for carry_forward. Must not be buried or filtered.
3. **Noise must be excluded at the trim step** — The MD format doesn't filter; the SessionAnalyzer.trim_session() does. Format just structures what survives.
4. **Empty sections are omitted** — Don't write `## Decisions\n\n` if there are none. Keeps the MD compact.
5. **Signal sections precede reference data** — Decisions, Open Items, Work Completed are extracted to DB columns. Reference data is indexed but not structured.

```markdown
# Session: {jsonl_path.stem}
date: {ISO date}
mode: {session_mode}
project: {project_id}

## Decisions
- Decision text (rationale when non-obvious)
- Small decision (because X)

## Open Items
- Item (priority: high|medium|low)
- Follow-up (priority: medium)

## Work Completed
- Task-bearing completion 1
- Task-bearing completion 2

## Topics Discussed
- Topic 1
- Topic 2

## Reference
files: [{file1}, {file2}]
functions: [{func1}, {func2}]
tests: [{test1}]
errors: [{error1}]
deviations: [{deviation1}]
```

**Format rules:**
- No blockquotes (`> `) — they add noise to extracted DB columns
- No `---` separators — `_extract_section()` captures until next `##` header; `---` would leak into preceding section
- Front-matter uses `key: value` (not `##` headers) — avoids regex interference
- Inline metadata uses `(key: value)` — parseable, doesn't break list extraction

**Empty section policy (absent vs. explicitly empty):**

`_extract_section()` returns `None` for missing sections → stored as `NULL` in DB. Consumers (`_reconcile_open_items`, carry_forward creation) treat `NULL` as "skip this entry." This loses the distinction between "no items" and "items not tracked."

| Section | Empty Strategy | Rationale |
|---------|---------------|-----------|
| **Decisions** | Write `- none` | carry_forward + ArcPipeline need to know "no decisions made" vs. "not tracked" |
| **Open Items** | Write `- none` | "All resolved" is actionable; NULL means "skip" in `_reconcile_open_items()` |
| **Work Completed** | Omit section | "Nothing done" is rare, not actionable. NULL is fine. |
| **Topics Discussed** | Omit section | Context is additive; missing topics don't break downstream |
| **Reference** | Omit section | Purely indexable; absence is never meaningful |

**Why `- none` and not `NULL`?** `_extract_section()` returns `content if content else None`. If the section exists with `- none`, it returns `"- none"` (truthy) → stored as TEXT. Consumers can distinguish:
- `NULL` → section not present (legacy/unknown)
- `"- none"` → section present, explicitly empty (meaningful absence)
- `"- item1\n- item2"` → section present, has items

**Example (code session, no decisions):**
```markdown
## Decisions
- none

## Open Items
- Fix carry_forward writer (priority: high)

## Work Completed
- Fixed _wait_idle() stability semantics
```

**Example (debugging session, nothing open):**
```markdown
## Decisions
- none

## Open Items
- none

## Work Completed
- Root-caused and fixed race condition in _wait_idle()

## Reference
files: [session_watcher.py]
errors: [file re-processed on every poll cycle]
```

### 3.2a Format Design Rationale

**Why these exact headers?** They match the consumer extraction patterns:

| Section Header | Consumer | Extracts To | Regex Match |
|---------------|----------|-------------|-------------|
| `## Decisions` | `upsert_session_diary()` | `decisions` column | `^#{1,3}\s+Decisions` ✅ |
| `## Open Items` | `upsert_session_diary()` | `open_items` column | `^#{1,3}\s+Open Items` ✅ |
| `## Work Completed` | `upsert_session_diary()` | `work_completed` column | `^#{1,3}\s+Work Completed` ✅ |
| `## Topics Discussed` | `upsert_session_diary()` | `session_context` | `^#{1,3}\s+Topics Discussed` ✅ |
| `## Reference` | SqliteIndexer (full text) | memsearch chunks | N/A (not extracted) |

**Noise reduction strategy (three layers):**

| Layer | Where | What | Example |
|-------|-------|------|---------|
| **L1: Trim filter** | SessionAnalyzer.trim_session() | Drops conversational filler, trivial actions | "Ran tests" → dropped |
| **L2: Section discipline** | MD format | Each item belongs to exactly one section. No repetition. | A decision goes in Decisions, not also in Completed |
| **L3: Omit empties** | _write_session_md() | Don't write sections with zero items | No decisions → no `## Decisions` block |

**Small decision preservation:**

1. **Decisions section is first** — Highest visual priority, first extracted by consumers
2. **No minimum threshold** — Even one decision writes the section
3. **Inline rationale** — `(because X)` format makes small decisions self-documenting
4. **Not buried under Completed** — Decisions are a separate section, not nested
5. **Extracted to DB column** — `upsert_session_diary()` writes to `decisions` TEXT column, indexed by FTS5 + Milvus

**Front-matter uses `key: value` (not `##` headers):**
- Avoids interference with section extraction regex
- Easy to parse: `re.match(r'^([^:]+):\s*(.+)$', line)`
- Not extracted to DB columns (metadata only)

**No blockquotes or separators in the MD:**
- Blockquotes (`> `) add noise to extracted DB columns
- `---` separators leak into preceding section via `_extract_section()` regex
- Format is self-documenting through section headers alone

### 3.2b Regex Bug: `_extract_section()` Truncates Multi-Paragraph Sections

**Bug:** `store.py` `_extract_section()` uses `$` in the lookahead with `re.MULTILINE`, which matches end-of-**line** not end-of-**string**. Multi-paragraph sections (header → blank line → content) capture only the first paragraph.

**Evidence:**
```python
# Current regex (broken):
pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|$)'  # $ matches EOL with MULTILINE

# Test: section with blockquote + blank line + list
# Input: "## Decisions\n> hint\n\n- item1\n- item2"
# Output: "> hint" (only first paragraph, list items lost)
```

**Fix:** Replace `$` with `\Z` (end-of-string anchor):
```python
# Fixed regex:
pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|\Z)'  # \Z matches end-of-string
```

**Files to modify:** `memory_service/store.py` — `_extract_section()` inside `upsert_session_diary()`

**Tests:**
1. `test_extract_section_single_paragraph` — captures single paragraph
2. `test_extract_section_multi_paragraph` — captures all paragraphs including blank lines
3. `test_extract_section_with_list` — captures list items after blank line
4. `test_extract_section_stops_at_next_header` — doesn't leak into next section

**Why MD?** Human-readable, parseable by any service, indexable by MemIndex, versionable (git-tracked), format SessionAnalyzer already produces.

### 3.3 carry_forward Integration — The Missing Link

carry_forward is the bridge between sessions, deviations, and project tracking. It tracks what carries across consolidation tiers.

```
carry_forward schema (existing, no changes needed):
├── id, project_id, tier, kind, text, priority
├── source_entry_id, source_summary_id
├── linked_work_item_id  → work_items (missed tasks, unresolved work)
├── linked_deviation_id  → plan_deviations (plan-vs-reality gaps)
├── expires_after_tier, remaining_cycles, is_reasserted
└── created_at, updated_at, expired_at

carry_forward kinds (existing):
├── "unresolved_work"  → work_items that stay "proposed" across sessions
├── "risk"             → project risks identified during sessions
└── "continuity_note"  → decisions/context that span sessions

carry_forward lifecycle:
├── Created: ArcPipeline after consolidation (NEW writer)
├── Decrement: Each tier run decrements remaining_cycles
├── Reassert: If still relevant, reset cycles (is_reasserted=1)
├── Expire: When remaining_cycles=0, set expired_at
└── Cap: Max 5 active items per (project_id, tier)
```

**carry_forward creation triggers (NEW):**

```python
# After ArcPipeline.run_tiered_consolidation() completes:

# 1. Unresolved work: open_items from session_diary that have no matching work_item
for open_item in consolidation.get("open_items", []):
    if not work_item_exists(open_item):
        store.create_carry_forward(
            project_id=project_id,
            tier=tier_id,
            kind="unresolved_work",
            text=open_item,
            priority="high",
            source_summary_id=rollup_id,
        )

# 2. Deviations: plan_deviations that are approved but not yet linked to carry_forward
for deviation in store.get_deviations(project_id=project_id, status="approved"):
    if not deviation.has_carry_forward():
        store.create_carry_forward(
            project_id=project_id,
            tier=tier_id,
            kind="continuity_note",
            text=f"Deviation: {deviation['title']} ({deviation['severity']})",
            linked_deviation_id=deviation['id'],
            source_summary_id=rollup_id,
        )

# 3. Missed tasks: work_items that stayed "proposed" for N+ sessions
for item in store.get_work_items(project_id=project_id, status="proposed"):
    if item.age_sessions() >= 3:
        store.create_carry_forward(
            project_id=project_id,
            tier=tier_id,
            kind="unresolved_work",
            text=f"Missed task: {item['title']} (proposed for {item.age_sessions()} sessions)",
            linked_work_item_id=item['id'],
            priority="high",
            source_summary_id=rollup_id,
        )
```

### 3.4 ArcPipeline → memory_rollups (Not memory_entries diary)

```
Current:  _write_tier_output() → store.upsert_memory_entry(entry_type="diary", ...)
Proposed: _write_tier_output() → store.upsert_memory_rollup(tier=tier_id, content=body, ...)

Rationale:
  + memory_rollups has proper schema for tiered consolidation (window_start, window_end, tier)
  + memory_rollups is the intended ARC output table (docstring says so)
  + memory_entries(diary) overlaps session_diary purpose (confusion)
  + carry_forward reads memory_rollups via _gather_plan_text()
  + After migration, memory_entries(diary) can be deprecated
```

### 3.5 Review Service — Separate Domain

```
ReviewService (INDEPENDENT, NOT part of JSONL→MD flow)
├── Operates on: work_items, code changes, plans, deviations
├── NOT triggered by: session processing, JSONL changes
├── Triggered by: humans, subagents, council review cycles
│
├── start_review(reviewer, target) → reviews + workflow_runs
├── log_finding(run_id, severity, summary) → review_findings + event_log + artifacts
└── record_verdict(run_id, verdict) → reviews (PASS/FAIL/PARTIAL)
│
Tables: reviews (2), review_findings (11), workflow_runs (3)
Indexed: SqliteIndexer (memsearch) + FTS
Isolation: No dependency on JSONL→MD flow
```

### 3.6 Indexing — Unified Coverage

```
SqliteIndexer (Channel A): DB → markdown → memsearch
  Tables: memory_entries, memory_rollups, work_items, review_findings,
          session_diary [NEW], plan_deviations [NEW], plan_deviations_events [NEW],
          carry_forward [NEW], chat_messages, knowledge_cards, notes, documents

UnifiedVectorStore (Channel B): session_diary → Milvus (direct embeddings)
  [consolidation_cache DROPPED]

MemIndex (Channel C): MD files → memsearch
  Used by: SessionWatcher._wire_memindex() [NEW], super_council.py (chat summaries)
```

### 3.7 Architectural Decision: Single Canonical MD vs. Multiple Extracted MDs

**Decision:** Single canonical MD file per session, written once by SessionWatcher. Each wired consumer reads from that one file and extracts its needed sections.

**Alternatives considered:**
- **A. Multiple MDs per session** — One MD per extractor type (session_diary.md, work_items.md, memindex.md, etc.)
- **B. Single canonical MD** — One comprehensive MD, consumers read and extract independently

**Chosen: B (Single Canonical MD)**

#### Problem Essence

**Core problem:** Each session's knowledge must be extracted into structured consumers (session_diary, work_items, memindex, carry_forward) — written once, consumed many times, without duplication or drift.

**So what? chain:**
- "Should we write one MD or many?" → So each consumer gets data in its format
- So what? → So extractors don't compete or duplicate effort
- So what? → So when the JSONL changes, downstream state stays consistent
- So what? → So we don't have multiple partial extractions that diverge
- ← **GROUND TRUTH:** One authoritative extraction per session, multiple consumers read what they need.

**JTBD:** "When a session ends, produce one canonical representation that each downstream service can independently consume — without coordination overhead between extractors."

#### Assumptions Challenged

| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| "Different extractors need different formats" | Technical | session_diary needs narrative, work_items needs tasks, memindex needs text — all present in one MD | **Discard** |
| "Multiple MDs reduce coupling between extractors" | Architectural | Extractors are already decoupled via the wiring model; coupling is in the *write*, not the *read* | **Discard** |
| "One MD is a bottleneck if extractors have different schemas" | Technical | Extractors read the MD, don't modify it. Read concurrency is free | **Discard** |
| "The JSONL is too large/raw for direct consumption" | Technical | True — but trimming produces the MD, not multiple MDs | **Keep** (justifies the MD layer) |
| "MemIndex needs its own file for chunking" | Technical | MemIndex.index_file() accepts any MD path; doesn't need exclusive ownership | **Discard** |
| "Separate MDs enable independent versioning" | Historical | No versioning strategy exists for per-extractor files. Git doesn't track them | **Discard** |

#### Ground Truths

1. **JSONL is the immutable source** — 20+ files, read-only, never modified. All downstream state derives from it.
2. **Each consumer has different extraction needs** — session_diary wants `## Decisions`, work_items wants `## Open Work`, memindex wants the whole file chunked. These are *read* differences, not *write* differences.
3. **One session = one truth** — If three MD files diverge (tasks extracted differently than decisions), there's no arbiter. Consistency requires one source.
4. **Extractors are readers, not writers** — The wiring model (`_wire_session_diary()`, `_wire_work_items()`, `_wire_memindex()`) reads the MD and writes to its own table. They don't modify the MD.
5. **ARC calls are the expensive operation** — ~52/day. Every additional extraction path that requires a separate ARC call is a cost multiplier. One MD = one trim = one ARC call.

#### Reasoning Chain

```
GT: JSONL is immutable source
  → All downstream state must derive from it
  → Multiple derivations risk divergence

GT: One session = one truth
  → One canonical representation per session
  → Multiple MDs = multiple partial truths = inconsistency risk

GT: Extractors are readers, not writers
  → They consume the MD, don't produce it
  → Multiple MDs adds write complexity for no read benefit

GT: ARC calls are expensive (~52/day)
  → Each extraction path that needs ARC = cost multiplier
  → One MD, one trim, one ARC call = minimal cost

GT: Consumers have different read needs
  → session_diary reads narrative sections
  → work_items reads task sections
  → memindex reads full file
  → All satisfied by ONE comprehensive MD

Inference: Single canonical MD minimizes writes (1), eliminates divergence (0),
          serves all consumers (3+), and costs one ARC call.

Inference: Multiple MDs would require N writes, N potential divergence points,
          N ARC calls (if each needs trimming), with zero additional capability.

SOLUTION: One canonical MD, wired consumers read what they need.
```

#### Stress Test

1. **If two consumers need conflicting extractions:** They read the same MD but extract differently. No conflict — they write to separate tables. The MD doesn't enforce a single interpretation.
2. **If the MD format needs to evolve:** One format to maintain, not N. Consumers add/ignore sections. Backward compatible (missing sections = empty extraction).
3. **If one consumer fails:** Others still read the MD. No cascade failure. The MD is independent of consumer health.

#### Alternative Cost

**Multiple MDs (N=3):** ~4 engineer-hours setup (coordinator, 3 writers, sync logic) + ongoing maintenance of 3 extraction paths — benefit realized: near zero (consumers are already decoupled by table, not by file).

#### Consistency with Proposal Points

| Proposal Point | Compatibility |
|----------------|---------------|
| 1. carry_forward wiring | ✅ Reads from canonical MD's `## Open Items` + `## Blockers` + `## Deviations` |
| 2. carry_forward lifecycle | ✅ Lifecycle in ArcPipeline, not in MD. MD is just input |
| 3. ArcPipeline → memory_rollups | ✅ ArcPipeline reads canonical MD via `_gather_tier_input()` |
| 4. Review service separate | ✅ Correctly isolated. Doesn't read session MDs |
| 5. Dead tables dropped | ✅ Simplifies write targets. Fewer fragmentation points |
| 6. Indexing expanded | ✅ SqliteIndexer reads DB tables. MD feeds DB tables. Single source |
| 7. Phase 4B is critical | ✅ Without Phase 4B, carry_forward has no writers regardless of MD strategy |
| 8. Topics Discussed dropped | ✅ No real topic extractor — was duplicated noise |

**Confidence: High** — Consumers are readers, JSONL is immutable, ARC calls are the bottleneck. Multiple MDs solve a non-problem (consumer coupling) while creating new problems (write coordination, divergence).

**Revisit when:** Session count exceeds 10,000 (caching becomes material), or a consumer needs a fundamentally different representation (binary embeddings, not text).

---

## Phase 4: Implementation Plan

### Phase 4A: SessionWatcher Writes MD + Wired Services (Immediate, Low Risk)

**What:** SessionWatcher writes MD file, then wires session_diary + work_items + memindex.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/session_watcher.py` | Add `_write_session_md()`, `_wire_session_diary()`, `_wire_memindex()` |

**Steps:**
1. Add `_write_session_md(trimmed, jsonl_path)` → writes MD to `~/.council-memory/sessions/`
2. Add `_wire_session_diary(trimmed, jsonl_path)` → calls `upsert_session_diary()`
3. Add `_wire_memindex(md_path)` → fire-and-forget MemIndex.index_file()
4. Rename `_reconcile()` → `_wire_work_items()` (clarifies wiring model)
5. Update `_process_session()` to call all wired consumers

**Tests:**
1. `test_process_session_writes_md_file` — MD file exists after processing
2. `test_process_session_creates_session_diary` — session_diary count increases
3. `test_wire_memindex_indexes_file` — memsearch has chunks from MD
4. `test_wire_work_items_creates_tasks` — work_items created from MD

**Dependencies:** None

**Estimated effort:** ~2 hours

### Phase 4B: ArcPipeline → memory_rollups + carry_forward Integration (Medium Effort)

**What:** ArcPipeline writes to memory_rollups (not memory_entries diary). Creates carry_forward entries after consolidation.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/pipeline.py` | Change `_write_tier_output()` → `_write_to_rollups()`, add `_create_carry_forwards()` |
| Modify | `memory_service/store.py` | Add `get_missed_tasks()`, `get_unresolved_work()` helpers |

**Steps:**
1. Change `_write_tier_output()` to call `store.upsert_memory_rollup()` instead of `store.upsert_memory_entry()`
2. Add `_create_carry_forwards(tier_id, consolidation)` after consolidation completes:
   - Scan open_items → create carry_forward (kind="unresolved_work")
   - Scan approved deviations → create carry_forward (kind="continuity_note", linked_deviation_id)
   - Scan proposed work_items aged 3+ sessions → create carry_forward (kind="unresolved_work", linked_work_item_id)
3. Add `_decrement_carry_forward_cycles(tier_id)` to expire old items
4. Update `_gather_tier_input()` to read memory_rollups for all tiers (not just non-daily)
5. Migrate 29 existing memory_entries(diary) rows → memory_rollups (one-time script)

**Tests:**
1. `test_write_to_rollups_creates_memory_rollup` — memory_rollups count increases
2. `test_create_carry_forwards_from_open_items` — carry_forward created for unresolved work
3. `test_create_carry_forwards_from_deviations` — carry_forward linked to plan_deviations
4. `test_create_carry_forwards_from_missed_tasks` — carry_forward linked to aged work_items
5. `test_decrement_carry_forward_cycles` — remaining_cycles decreases, expired_at set
6. `test_carry_forward_cap_enforced` — max 5 per (project_id, tier)

**Dependencies:** Phase 4A (session_diary must exist for _gather_tier_input)

**Estimated effort:** ~4 hours

### Phase 4C: Drop Dead Tables + Index carry_forward (Cleanup)

**What:** Remove dead tables, add carry_forward + deviation tables to SqliteIndexer.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `migrations_council_core/` | Add migration to drop tables |
| Modify | `memory_service/store.py` | Remove dead methods |
| Modify | `memory_service/sqlite_indexer.py` | Add carry_forward, plan_deviations, plan_deviations_events to `_POLL_TABLES` |
| Modify | `memory_service/http_endpoints.py` | Remove auto-detected routing |
| Modify | `memory_service/vector_store.py` | Remove consolidation_cache indexing |

**Steps:**
1. Create migration SQL: `DROP TABLE IF EXISTS consolidation_cache; DROP TABLE IF EXISTS raw_session_memories;`
2. Remove `upsert_consolidation_cache()`, `query_consolidation_cache()` from store.py
3. Remove `upsert_raw_session_memory()`, `query_raw_session_memories()` from store.py
4. Remove consolidation_cache from UnifiedVectorStore.reindex_existing_data()
5. Add carry_forward, plan_deviations, plan_deviations_events to SqliteIndexer `_POLL_TABLES`
6. Simplify upsert_summary endpoint (remove auto-detected routing)
7. Deprecate `memory_entries` entry_type="diary" (migrate to memory_rollups in Phase 4B)

**Tests:**
1. All existing tests pass after removal
2. Migration is idempotent (safe to re-run)
3. carry_forward, plan_deviations indexed by SqliteIndexer

**Dependencies:** Phase 4B (migrate diary→rollups first)

**Estimated effort:** ~2 hours

### Phase 4D: Merge Indexers (Larger Refactor, Optional)

**What:** UnifiedVectorStore indexes all tables currently handled by SqliteIndexer. Drop SqliteIndexer.

**NOTE:** Deferred until Phase 4A-4C are stable. Current dual-indexer model works. Merge only if Milvus capacity is verified for ~400+ entries.

**Estimated effort:** ~8 hours (deferred)

---

## Phase 5: Execution Order & Dependencies

```
Phase 4A (SessionWatcher→MD+wired services) ────┐
                                                  │
Phase 4B (memory_rollups + carry_forward) ────────┤  All parallel except 4B→4C
                                                  │
Phase 4C (drop dead + index carry_forward) <──────┤  4C after 4B (migration)
                                                  │
Phase 4D (merge indexers) <───────────────────────┘  Deferred until stable
```

---

## Phase 6: Complete Table Inventory (Post-Streamlining)

| Table | Role | Writer | Rows | Indexed | Status |
|-------|------|--------|------|---------|--------|
| **session_diary** | Canonical narrative | SessionWatcher._wire_session_diary() | 5→20+ | Milvus + memsearch + FTS | ✅ ACTIVE |
| **work_items** | Canonical task ledger | SessionWatcher._wire_work_items() + ArcPipeline.reconcile_tasks() | 118 | memsearch + FTS | ✅ ACTIVE |
| **memory_rollups** | Integrated ARC consolidation | ArcPipeline._write_to_rollups() | 2→growing | memsearch + FTS | ✅ ACTIVE (rewired) |
| **memory_entries** | Raw/intermediate capture | MCP server (auto-detected + inline) | 207 | memsearch + FTS | ✅ ACTIVE (diary deprecated) |
| **carry_forward** | Cross-tier tracking | ArcPipeline._create_carry_forwards() | 0→growing | memsearch + FTS | ✅ ACTIVE (rewired) |
| **plan_deviations** | Plan-vs-reality tracking | ArcPipeline.reconcile_deviations() | 1 | memsearch + FTS | ✅ ACTIVE |
| **plan_deviations_events** | Deviation audit trail | store.create/update_deviation() | 2 | memsearch [NEW] | ✅ ACTIVE |
| **reviews** | Review lifecycle | ReviewService.start_review() | 2 | memsearch + FTS | ✅ ACTIVE (separate) |
| **review_findings** | Review findings | ReviewService.log_finding() | 11 | memsearch + FTS | ✅ ACTIVE (separate) |
| **workflow_runs** | Execution tracking | ReviewService + pipeline | 3 | — | ✅ ACTIVE |
| **projects** | Project registry | store.resolve_project() | 2 | — | ✅ ACTIVE |
| **workspace_bindings** | Path→project mapping | Manual | 2 | — | ✅ ACTIVE |
| **chat_messages** | Chat history | — | 9 | memsearch + FTS | ✅ ACTIVE |
| **artifacts** | Run artifacts | MemoryLayer.ingest_artifact() | 26 | FTS | ✅ ACTIVE |
| **event_log** | System events | store.log_event() | 29 | FTS | ✅ ACTIVE |
| `consolidation_cache` | — | — | 0 | — | ❌ **DROP** |
| `raw_session_memories` | — | — | 0 | — | ❌ **DROP** |

---

## Phase 7: Constraints

- **Read-only on JSONL:** Never modify Pi's session files. Touch only for mtime during testing.
- **Non-destructive:** Do not delete existing records. Use migrations for schema changes.
- **Backward compatible:** Existing recall paths must work during migration.
- **Idempotent migrations:** All schema changes safe to re-run.
- **No ARC call increase:** Target 50% reduction (combine extract + consolidate).
- **Search parity:** All previously searchable content remains searchable.
- **carry_forward cap:** Max 5 active items per (project_id, tier). Enforced by store.
- **Review isolation:** Review service has no dependency on JSONL→MD flow.

---

## Phase 8: Caveats & Uncertainty

1. **carry_forward writer timing:** Creating carry_forward entries after consolidation means there's a delay between session processing and carry_forward creation. If a session is interrupted, carry_forward may not reflect the latest state. **Mitigation:** SessionWatcher also creates carry_forward for immediate open_items.

2. **memory_rollups migration:** 29 memory_entries(diary) rows need migration to memory_rollups. The schemas differ (memory_entries has id/entry_type/tier/title/body; memory_rollups has id/tier/window_start/window_end/content/summary). **Mitigation:** Migration script maps fields, sets window_start/window_end from created_at.

3. **carry_forward dedup:** If the same open_item appears in multiple sessions, carry_forward could create duplicates. **Mitigation:** Check existing carry_forward entries before creating (fuzzy match on text + project_id).

4. **SqliteIndexer adding tables:** Adding carry_forward, plan_deviations, plan_deviations_events increases indexing load. **Mitigation:** These are small tables (1-2 rows each). Negligible impact.

5. **UnifiedVectorStore capacity:** Currently indexes ~5 session_diary entries. After adding session_diary to SqliteIndexer, both indexers cover session_diary. **Decision:** Keep both (Milvus for semantic search, memsearch for chunk-based search). They serve different query patterns.

---

## Phase 9: Alignment Audit — Mismatches & Gaps

**Status:** 4 mismatches found, 1 gap identified. All block Phase 4A if unaddressed.

### 9.1 Mismatch #1 (CRITICAL): `_trimmed_to_text()` Uses Wrong Headers

**Problem:** `SessionWatcher._trimmed_to_text()` generates headers that don't match the MD format or consumer extraction patterns.

| Current Output | MD Format Needs | Consumer Extracts | Match? |
|--------------|-----------------|-------------------|--------|
| `## Completed Work` | `## Work Completed` | `"Work Completed"` or `"Completed"` | ❌ |
| `## Explicit Decisions` | `## Decisions` | `"Key Decisions"` or `"Decisions"` | ❌ |
| `## Open Work` | `## Open Items` | `"Open Items"` | ❌ |
| `## Files Changed` | `## Reference` (files line) | N/A (not extracted) | ⚠️ |
| `## Functions Touched` | `## Reference` (functions line) | N/A (not extracted) | ⚠️ |
| `## Tests Written` | `## Reference` (tests line) | N/A (not extracted) | ⚠️ |
| `## Errors Blockers` | `## Reference` (errors line) | N/A (not extracted) | ⚠️ |
| `## Notable Deviations` | `## Reference` (deviations line) | N/A (not extracted) | ⚠️ |

**Impact:** If `_write_session_md()` copies `_trimmed_to_text()` output verbatim, `upsert_session_diary()` would extract **zero sections** (all headers miss). Every DB column would be NULL.

**Fix:** `_write_session_md()` must NOT use `_trimmed_to_text()`. It must map trimmed fields to MD headers explicitly:

```python
def _write_session_md(self, trimmed: dict, jsonl_path: Path) -> Path:
    """Write canonical MD from trimmed summary.
    
    Maps trimmed schema fields to MD section headers that match
    consumer extraction patterns. Does NOT use _trimmed_to_text()
    which generates wrong headers.
    """
    lines = [
        f"# Session: {jsonl_path.stem}",
        f"date: {datetime.now().isoformat()}",
        f"mode: {trimmed.get('session_mode', 'mixed')}",
        f"project: {trimmed.get('project_id', '')}",
        "",
    ]
    
    # Decisions: explicit_decisions → ## Decisions
    decisions = trimmed.get("explicit_decisions", [])
    if decisions:
        lines.append("## Decisions")
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")
    else:
        lines.append("## Decisions")
        lines.append("- none")  # Meaningful absence
        lines.append("")
    
    # Open Items: open_work → ## Open Items
    open_work = trimmed.get("open_work", [])
    if open_work:
        lines.append("## Open Items")
        for item in open_work:
            lines.append(f"- {item}")
        lines.append("")
    else:
        lines.append("## Open Items")
        lines.append("- none")  # Meaningful absence
        lines.append("")
    
    # Work Completed: completed_work → ## Work Completed
    completed = trimmed.get("completed_work", [])
    if completed:
        lines.append("## Work Completed")
        for c in completed:
            lines.append(f"- {c}")
        lines.append("")
    
    # Reference: aggregate metadata fields
    ref_items = []
    if trimmed.get("files_changed"):
        ref_items.append(f"files: {trimmed['files_changed']}")
    if trimmed.get("functions_touched"):
        ref_items.append(f"functions: {trimmed['functions_touched']}")
    if trimmed.get("tests_written"):
        ref_items.append(f"tests: {trimmed['tests_written']}")
    if trimmed.get("errors_blockers"):
        ref_items.append(f"errors: {trimmed['errors_blockers']}")
    if trimmed.get("notable_deviations"):
        ref_items.append(f"deviations: {trimmed['notable_deviations']}")
    
    if ref_items:
        lines.append("## Reference")
        lines.extend(ref_items)
        lines.append("")
    
    md_path = self._sessions_dir / f"{jsonl_path.stem}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path
```

**Files to modify:** `memory_service/session_watcher.py` — add `_write_session_md()`

### 9.2 Mismatch #2 (HIGH): `## Topics Discussed` Has No Source

**Problem:** The MD format includes `## Topics Discussed` which feeds `session_context` in `upsert_session_diary()`. But the SessionAnalyzer trimmed schema has no `topics_discussed` field.

| Source | Field | Exists? |
|--------|-------|---------|
| SessionAnalyzer trimmed schema | `topics_discussed` | ❌ No |
| SessionAnalyzer trimmed schema | `session_mode` | ✅ Yes (front-matter only) |
| upsert_session_diary() | `session_context` from Topics + Models | ⚠️ Will be NULL |

**Impact:** `session_context` column will be NULL for all SessionWatcher-generated entries. Future sessions lose broader context.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| A. Add `topics_discussed` to SessionAnalyzer | Complete coverage | Requires model prompt change + regex patterns |
| B. Derive from `completed_work` + `explicit_decisions` | No code changes | Approximation, not true "topics" |
| C. Omit `## Topics Discussed` from MD | Simple | `session_context` stays NULL |
| D. Use `session_mode` as proxy | Already available | Too coarse-grained |

**Recommendation:** **B (derive from completed_work + explicit_decisions)** for Phase 4A. Add proper `topics_discussed` extraction to SessionAnalyzer as a follow-up.

```python
# Derive topics from signal sections
all_signals = (
    trimmed.get("completed_work", []) +
    trimmed.get("explicit_decisions", []) +
    trimmed.get("open_work", [])
)
if all_signals:
    lines.append("## Topics Discussed")
    for topic in all_signals[:5]:  # Cap at 5 to avoid noise
        lines.append(f"- {topic}")
    lines.append("")
```

### 9.3 Mismatch #3 (MEDIUM): `open_items` vs `open_work` Field Name

**Problem:** The carry_forward creation trigger in the doc uses `consolidation.get("open_items", [])` but the SessionAnalyzer trimmed schema uses `open_work`.

| Context | Field Name | Source |
|---------|-----------|--------|
| SessionAnalyzer trimmed | `open_work` | `analyzer.py` TRIMMED_SCHEMA_FIELDS |
| MD section | `## Open Items` | Format spec |
| session_diary column | `open_items` | `upsert_session_diary()` |
| ArcPipeline YAML output | `open_items`, `new_open_items` | `prompts.py` |
| carry_forward trigger (doc) | `consolidation.get("open_items")` | Phase 3.3 |

**Impact:** No actual bug — the carry_forward trigger reads from ARC consolidation YAML (which uses `open_items`), not from the trimmed dict (which uses `open_work`). The naming is inconsistent but the flows don't cross.

**Fix:** Document the naming convention clearly. Consider renaming `open_work` → `open_items` in the trimmed schema for consistency. **Defer to post-Phase 4A** (not blocking).

### 9.4 Mismatch #4 (MEDIUM): `_extract_section()` Regex Bug

**Problem:** Documented in §3.2b. `$` with `re.MULTILINE` matches end-of-line, not end-of-string. Multi-paragraph sections capture only the first paragraph.

**Impact:** Any MD section with blank lines (e.g., list items separated by blank lines) loses content after the first paragraph.

**Fix:** Replace `$` with `\Z` in `_extract_section()` regex. **Must be done before Phase 4A.**

### 9.5 Gap: `notable_deviations` Has No Structured Consumer

**Problem:** The SessionAnalyzer extracts `notable_deviations` (plan-vs-reality signals). The MD format puts them in `## Reference` (indexable but not extracted to any DB column). No consumer reads them structurally.

| Field | MD Location | Extracted To | Consumer |
|-------|------------|--------------|----------|
| `notable_deviations` | `## Reference` (deviations line) | NULL (not extracted) | None |

**Impact:** Deviation signals from sessions are indexed for search but not tracked structurally. `ArcPipeline.reconcile_deviations()` uses ARC detection (plan vs. implementation text), not session-level deviation signals.

**Options:**

| Option | Pros | Cons |
|--------|------|------|
| A. Add `## Deviations` section + DB column | Structured tracking | Requires schema change |
| B. Feed to carry_forward as "risk" kind | Uses existing schema | Loses deviation-specific metadata |
| C. Leave as Reference (current) | Simple | Signals not actionable |

**Recommendation:** **B (feed to carry_forward)** for Phase 4B. If deviation signals prove valuable, add dedicated section + column later.

### 9.6 Summary: What Must Be Fixed Before Phase 4A

| Item | Severity | Block 4A? | Fix Location |
|------|----------|-----------|-------------|
| `_trimmed_to_text()` wrong headers | CRITICAL | ✅ Yes | `session_watcher.py` — write `_write_session_md()` with correct mapping |
| `## Topics Discussed` no source | HIGH | ⚠️ Partial | Derive from signals (see 9.2 recommendation) |
| `_extract_section()` regex bug | MEDIUM | ✅ Yes | `store.py` — replace `$` with `\Z` |
| `open_items` vs `open_work` naming | MEDIUM | ❌ No | Document, defer rename |
| `notable_deviations` no consumer | LOW | ❌ No | Feed to carry_forward in Phase 4B |

### 9.7 Recommended Fixes — Options & Decisions

#### Fix 9.1: `_trimmed_to_text()` Wrong Headers (CRITICAL)

**Options:**

| Option | What Changes | ARC Calls | Risk | Effort |
|--------|-------------|-----------|------|--------|
| **A. Two methods, different headers** | Keep `_trimmed_to_text()` for ARC. Add `_write_session_md()` with correct headers. | Same (~52/day) | Low — ARC input unchanged | ~1h |
| **B. One method, fix headers everywhere** | Fix `_trimmed_to_text()` headers. ARC model doesn't care about header names. | Same | Medium — ARC prompt assumes current format | ~1h |
| **C. One method, drop ARC call** | `_write_session_md()` produces MD. `_wire_work_items()` parses MD directly (no ARC). | **-50%** (~26/day) | High — removes ARC task extraction | ~3h |

**Recommendation: A (two methods)** for Phase 4A. Safest path — ARC pipeline untouched, MD format correct. Evaluate C after 4A proves the MD pipeline works (ARC call reduction is valuable but risky).

**Why not B?** The ARC consolidation prompt in `prompts.py` includes structured examples. Changing header names could affect ARC's parsing. Not worth the risk for Phase 4A.

**Why not C yet?** Removing ARC task extraction is a behavioral change that needs testing. Do it in a separate phase.

#### Fix 9.2: `## Topics Discussed` Has No Source (HIGH)

**Options:**

| Option | What | `session_context` | Effort | Quality |
|--------|------|-------------------|--------|---------|
| **A. Derive from signals** | Concatenate `completed_work` + `explicit_decisions` + `open_work`, cap at 5 | Populated (approximate) | ~15min | Medium — not true "topics" but useful |
| **B. Add to SessionAnalyzer** | New field in TRIMMED_SCHEMA_FIELDS, new extraction regex | Populated (proper) | ~2h | High — requires model prompt changes |
| **C. Use `session_mode`** | Front-matter only, not extracted to DB | NULL | 0 | Low — too coarse |
| **D. Drop from MD** | Remove `## Topics Discussed` section | NULL | 5min | Low — loses context |

**Recommendation: A (derive from signals)** for Phase 4A.

```python
# In _write_session_md(), after Decisions + Open Items + Work Completed:
all_signals = (
    trimmed.get("explicit_decisions", []) +
    trimmed.get("completed_work", []) +
    trimmed.get("open_work", [])
)
if all_signals:
    lines.append("## Topics Discussed")
    for item in all_signals[:5]:  # Cap to avoid noise
        lines.append(f"- {item}")
    lines.append("")
```

**Follow-up:** Add proper `topics_discussed` to SessionAnalyzer (Option B) once 4A is stable.

#### Fix 9.3: `open_items` vs `open_work` Naming (MEDIUM)

**Options:**

| Option | What Changes | Risk | Effort |
|--------|-------------|------|--------|
| **A. Rename in trimmed schema** | `open_work` → `open_items` everywhere (analyzer.py, session_watcher.py, prompts.py) | Medium — touches 4 files, breaks tests | ~2h |
| **B. Document alias** | Add comment: "open_work = open_items (naming inconsistency, defer fix)" | Low — no code changes | ~10min |
| **C. Fix at boundary only** | `_write_session_md()` maps `open_work` → `## Open Items`. Document the mapping. | Low — one file change | ~15min |

**Recommendation: C (fix at boundary)** for now. The mapping exists in `_write_session_md()`:

```python
# open_work → ## Open Items (naming mismatch: trimmed schema uses 'open_work')
open_work = trimmed.get("open_work", [])
if open_work:
    lines.append("## Open Items")
```

**Defer A** (full rename) to a cleanup phase. Consistency improvement, not a bug fix.

#### Fix 9.4: `_extract_section()` Regex Bug (MEDIUM)

**Options:**

| Option | What | Risk | Effort |
|--------|------|------|--------|
| **A. Replace `$` with `\Z`** | `(?=\n#{1,3}\|\Z)` — matches end-of-string | Low — `\Z` is standard Python regex | ~5min |
| **B. Drop `re.MULTILINE`** | Use `re.DOTALL` only, add explicit `^` handling | Medium — changes regex semantics | ~15min |

**Recommendation: A (replace `$` with `\Z`)**. One character change, proven fix.

```python
# Before (broken):
pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|$)'  # $ matches EOL

# After (fixed):
pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|\Z)'  # \Z matches end-of-string
```

**File:** `memory_service/store.py` — `_extract_section()` inside `upsert_session_diary()`

#### Fix 9.5: `notable_deviations` Has No Structured Consumer (LOW)

**Options:**

| Option | What | Schema Change | Effort |
|--------|------|--------------|--------|
| **A. Feed to carry_forward** | ArcPipeline creates carry_forward (kind="risk") from session notable_deviations | No | ~1h (Phase 4B) |
| **B. Add `## Deviations` + DB column** | New MD section, new session_diary column, new extraction | Yes — ALTER TABLE | ~2h |
| **C. Leave in Reference** | Current state — indexed for search, not actionable | No | 0 |

**Recommendation: A (feed to carry_forward)** in Phase 4B. No schema changes, uses existing infrastructure, makes deviation signals actionable.

```python
# In _create_carry_forwards() (Phase 4B):
for deviation in consolidation.get("notable_deviations", []):
    store.create_carry_forward(
        project_id=project_id,
        tier=tier_id,
        kind="risk",
        text=f"Deviation signal: {deviation}",
        priority="medium",
        source_summary_id=rollup_id,
    )
```

### 9.8 Consolidated Fix Plan

| Phase | Item | Option | Effort | Files |
|-------|------|--------|--------|-------|
| **Pre-4A** | 9.4 Regex bug | A (`$` → `\Z`) | 5min | `store.py` |
| **4A** | 9.1 Wrong headers | A (two methods) | 1h | `session_watcher.py` |
| **4A** | 9.2 No topics source | A (derive from signals) | 15min | `session_watcher.py` |
| **4A** | 9.3 Naming mismatch | C (fix at boundary) | 15min | `session_watcher.py` |
| **4B** | 9.5 No deviations consumer | A (feed to carry_forward) | 1h | `pipeline.py` |
| **Post-4A** | 9.3 Full rename | A (optional cleanup) | 2h | 4 files |
| **Post-4A** | 9.2 Proper topics | B (add to SessionAnalyzer) | 2h | `analyzer.py` |

**Total blocking effort: ~2.5h** (regex fix + `_write_session_md()` + topics derivation). All other items deferrable.

**Key trade-off:** Option A for 9.1 (two methods) keeps `_trimmed_to_text()` as-is, so the ARC pipeline is untouched. Safer but leaves technical debt. Option C (drop ARC call) saves ~26 ARC calls/day but requires testing. **Recommend A now, evaluate C after 4A.**

**Phase 4A prerequisite checklist:**
- [ ] Fix `_extract_section()` regex (`$` → `\Z`) in `store.py`
- [ ] Write `_write_session_md()` with correct field→header mapping (NOT `_trimmed_to_text()`)
- [ ] Derive `## Topics Discussed` from signal sections (completed_work + explicit_decisions)
- [ ] Write `- none` for Decisions and Open Items when empty
- [ ] Verify all section headers match `upsert_session_diary()` extraction patterns

---

## Appendix A: carry_forward Deep Dive

### A.1 The carry_forward Schema

```sql
carry_forward (
    id TEXT PRIMARY KEY,
    project_id TEXT,                    -- Links to projects table
    tier TEXT,                          -- daily, short, weekly, bimonthly
    kind TEXT,                          -- unresolved_work, risk, continuity_note
    text TEXT,                          -- The carry-forward content
    priority TEXT,                      -- low, medium, high, critical
    source_entry_id TEXT,               -- Original memory_entry that triggered this
    source_summary_id TEXT,             -- Session summary that created this
    linked_work_item_id TEXT,           -- FK → work_items (missed tasks)
    linked_deviation_id TEXT,           -- FK → plan_deviations (plan gaps)
    expires_after_tier INTEGER,         -- How many tier cycles before expiry
    remaining_cycles INTEGER,           -- Decrement each tier run
    is_reasserted INTEGER,              -- 1 if manually reasserted
    reasserted_at TEXT,                 -- Timestamp of reassertion
    created_at TEXT,
    updated_at TEXT,
    expired_at TEXT                     -- NULL = active, set = expired
)
```

### A.2 carry_forward Creation Triggers

| Trigger | Kind | linked_work_item_id | linked_deviation_id | Priority |
|---------|------|---------------------|---------------------|----------|
| Open item with no matching work_item | unresolved_work | NULL | NULL | high |
| Approved deviation without carry_forward | continuity_note | NULL | deviation.id | high |
| Work item "proposed" for 3+ sessions | unresolved_work | work_item.id | NULL | high |
| Session risk identified by ARC | risk | NULL | NULL | medium |
| Decision spanning multiple sessions | continuity_note | NULL | NULL | medium |

### A.3 carry_forward Lifecycle

```
Created (remaining_cycles = expires_after_tier, e.g., 2)
  │
  ├─→ Tier run (daily): remaining_cycles -= 1 → 1
  │    │
  │    ├─→ Still relevant? → reassert_carry_forward() → reset cycles
  │    └─→ Not relevant? → Let it expire
  │
  ├─→ Tier run (short): remaining_cycles -= 1 → 0
  │    │
  │    └─→ remaining_cycles = 0 → expire_carry_forward() → expired_at = now
  │
  └─→ Expired entries excluded from _gather_plan_text()
       (WHERE expired_at IS NULL)
```

### A.4 carry_forward → _gather_plan_text() Integration

```python
# arc_summarizer/pipeline.py — _gather_plan_text() (EXISTING, reads carry_forward)

def _gather_plan_text(self, tier_id: str) -> Optional[str]:
    """Gather plan/spec text for deviation detection."""
    # 1. Carry-forward items as plan references ──── THIS IS THE READER
    cf_items = self._relational_store.get_carry_forward_items(
        tier=tier_id,
        include_expired=False,
    )
    for item in cf_items:
        parts.append(f"--- Carry Forward ({item['kind']}) ---")
        parts.append(item['text'])
        if item['linked_work_item_id']:
            wi = self._relational_store.get_work_item(item['linked_work_item_id'])
            if wi:
                parts.append(f"  → Work Item: {wi['title']} ({wi['status']})")
        if item['linked_deviation_id']:
            dev = self._relational_store.get_deviation(item['linked_deviation_id'])
            if dev:
                parts.append(f"  → Deviation: {dev['title']} ({dev['severity']}, {dev['status']})")
```

**This reader already exists.** It just has nothing to read because no carry_forward entries are created. Phase 4B fixes this.

---

## Appendix B: Deviation Tracking Map

```
plan_deviations (1 row)
├── id: bef5b211-a6ef-4901-a912-f88b3d8fbe1f
├── project_id: afee346a... (council)
├── work_item_id: aeedc1fa... (Test work item)
├── deviation_type: unplanned
├── severity: major
├── status: approved
├── confidence: 0.85
│
├── plan_deviations_events (2 rows)
│    ├── created: "Test deviation"
│    └── status_changed: proposed→approved
│
└── carry_forward (SHOULD link, currently NULL)
     └── linked_deviation_id: bef5b211... (AFTER Phase 4B)
```

---

## Appendix C: Review Service Isolation

```
ReviewService (memory_service/review.py)
│
├── start_review(reviewer, target, run_id)
│    ├── upsert_pipeline() → pipelines table
│    ├── ensure_workflow_run() → workflow_runs table
│    └── log_event() → event_log table
│
├── log_finding(run_id, severity, summary, fix, evidence)
│    ├── log_event() → event_log table
│    └── store_artifact() → artifacts table
│
└── record_verdict(run_id, verdict, reason)
     └── updates reviews table (PASS/FAIL/PARTIAL)
│
Tables: reviews, review_findings, workflow_runs, event_log, artifacts
Indexed: SqliteIndexer (memsearch) + FTS
Isolation: No dependency on JSONL→MD flow
Trigger: Humans, subagents, council review cycles (NOT session processing)
```

---

## Appendix D: Production Metrics (Baseline)

| Metric | Value |
|--------|-------|
| JSONL files (sessions dir) | 20+ |
| session_diary entries | 5 (all manual) |
| work_items | 118 (115 proposed, 3 open) |
| memory_entries | 235 (200 raw, 29 diary, 7 summary) |
| memory_rollups | 2 (stale, weekly) |
| plan_deviations | 1 (test) |
| carry_forward | 1 (expired, orphaned) |
| reviews | 2 |
| review_findings | 11 |
| ARC calls/day (estimated) | 52+ |
| SqliteIndexer tables | 8 (6 with data) |
| UnifiedVectorStore sources | 2 (1 with data) |
| Dead tables | 2 (consolidation_cache, raw_session_memories) |
