# Memory Service Full Module Split — Pipeline-Aligned Architecture

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `83c30c` |
| Entity type | `handoff` |
| Short description | Split memory_service into 5 self-contained pipeline stages plus recall, enrichment, and cross-cutting modules |
| Status | `draft` |
| Source references | Analysis from 2026-06-10 codebase audit; target pipeline: Raw JSONL → Canonical MD → ARC LLM → Consolidation → Reconciliation → VectorStore → DB |
| Generated | 10-06-2026 |
| Next action / owner | Execute Phase 1 (scaffold + store.py split) via subagent |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** This handoff document; phase-specific handoffs listed below
**Related codebases:** None (self-contained refactor within super_council)
**Key files for this task:** All files under `memory_service/` (16 files, 16742 total lines) and `arc_summarizer/` (8 files)

---

## Target Pipeline

The split aligns every module to one of five pipeline stages:

```
Stage 1:  Raw JSONL → Canonical MD          (canonical-raw-session-data/)
Stage 2:  Canonical MD → ARC LLM → Outputs  (arc-memory/)
Stage 3:  Consolidation outputs → memsearch  (indexing)
Stage 4:  Consolidation → reconciliation     (arc-reconcile/)
Stage 5:  Reconciliation → VectorStore → DB  (council_core.db)
```

Plus three cross-cutting layers:
- **Recall Layer** — reads from all stages (3-channel unified recall)
- **Enrichment** — local model artifact enrichment, failure classification
- **Transport** — MCP and HTTP servers (unchanged, re-wired)

---

## Target Directory Structure

```
memory_service/
├── __init__.py                  # MemoryService facade (composition root)
├── __main__.py                  # CLI entry point
├── config.py                    # MemoryConfig, MemsearchConfig, MCPConfig
├── errors.py                    # ResolutionResult, ProjectResolutionError, CarryForwardCapError
├── mcp_server.py                # MCP transport layer
├── http_endpoints.py            # HTTP transport layer
│
├── ingest/                      # STAGE 1: Raw JSONL → Canonical MD
│   ├── __init__.py
│   ├── session_watcher.py       # File watching, polling, run loop
│   ├── session_parser.py        # JSONL parsing, text extraction, session classification
│   ├── session_trimmer.py       # Mode-aware session trimming
│   ├── deviation_detector.py    # Deviation detection, classification, typing
│   ├── diary_merger.py          # Diary merge, signal counting
│   └── canonical_writer.py      # MD file writing, project resolution, carry-forward
│
├── consolidate/                 # STAGE 2: Canonical MD → ARC LLM → Consolidation
│   ├── __init__.py
│   ├── pipeline.py              # ArcPipeline (LLM calls, tier orchestration)
│   ├── scheduler.py             # IdleWindowScheduler (background scheduling)
│   ├── tier_gatherer.py         # Input gathering per tier
│   ├── tier_writer.py           # Output writing, DB upsert, MD formatting
│   ├── knowledge_card.py        # Tier-1 knowledge card injection
│   ├── client.py                # ArcClient (LLM HTTP client)
│   ├── config.py                # ArcConfig
│   ├── analyzer.py              # SessionAnalyzer (session mode classification)
│   └── prompts.py               # Tier prompt templates
│
├── index/                       # STAGE 3: Consolidation → Memsearch Indexing
│   ├── __init__.py
│   ├── indexer.py               # Consolidation output → memsearch index
│   ├── file_watcher.py          # Watch arc-memory/ for new consolidation files
│   └── doc_parsers.py           # DailyLogParser, ChatSummaryQuery, Supervisor/Systemd tailers
│
├── reconcile/                   # STAGE 4: Consolidation → Reconciliation Outputs
│   ├── __init__.py
│   ├── reconciler.py            # Unified ArcReconciler (orchestrates dedup, classify, extract, write)
│   ├── dedup.py                 # Normalization, dedup keys, title similarity
│   ├── classifier.py            # Evidence-based classification, candidate analysis
│   ├── extractor.py             # Task/deviation/carry-forward extraction from MD
│   └── writer.py                # Reconciliation MD file writing
│
├── store/                       # STAGE 5: Reconciliation → VectorStore → DB
│   ├── __init__.py
│   ├── vector_store.py          # SQLiteVectorStore (indexing, search, reindex)
│   ├── relational_store.py      # RelationalStore core (pipeline, events, artifacts)
│   ├── session_store.py         # Session diary, raw session memory
│   ├── consolidation_store.py   # Consolidation cache, tier tracking
│   ├── work_items.py            # Work item CRUD, carry-forward
│   ├── deviations.py            # Deviation CRUD, linking
│   ├── projects.py              # Project resolution, validation
│   ├── blacklist.py             # Injection blacklist
│   └── fts.py                   # FTS5 triggers, sync
│
├── recall/                      # RECALL LAYER (reads from all stages)
│   ├── __init__.py
│   ├── router.py                # ContextRouter (run snapshots, events, similar runs)
│   ├── layer.py                 # MemoryLayer (3-channel unified recall, token budgeting)
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── memsearch.py         # Channel: memsearch text recall
│   │   ├── diary.py             # Channel: session diary recall
│   │   ├── execution.py         # Channel: execution history recall
│   │   ├── structural.py        # Channel: code graph structural recall
│   │   ├── work_items.py        # Channel: work item recall
│   │   ├── deviations.py        # Channel: deviation recall
│   │   └── vectors.py           # Channel: unified vector recall
│   └── system_health.py         # System health (NOT a recall channel)
│
├── enrich/                      # ENRICHMENT (cross-cutting)
│   ├── __init__.py
│   └── enricher.py              # MicroModelEnricher (local embedding, summaries, tags)
│
├── review/                      # REVIEW (cross-cutting)
│   ├── __init__.py
│   └── service.py               # ReviewService (start/log/verdict)
│
├── health/                      # HEALTH (cross-cutting)
│   ├── __init__.py
│   └── checker.py               # ServiceHealthChecker
│
└── analytics/                   # ANALYTICS (cross-cutting)
    ├── __init__.py
    └── logger.py                # Embedding/search request logging
```

---

## Execution Order (DAG)

```
Phase 1: Scaffold + store.py split          ← START HERE (foundational)
    │
Phase 2: ingest/ (Stage 1)                  ← depends on Phase 1 (needs session_store.py)
    │
Phase 3: consolidate/ (Stage 2)             ← depends on Phase 1 (needs consolidation_store.py)
    │
Phase 4: index/ (Stage 3)                   ← depends on Phase 1
    │
Phase 5: reconcile/ (Stage 4)               ← depends on Phase 1
    │
Phase 6: recall/ (Recall Layer)             ← depends on Phase 1, 2, 3, 4, 5
    │
Phase 7: Cross-cutting (enrich/, review/, health/, analytics/)  ← depends on Phase 1
    │
Phase 8: Composition Root + Transport       ← depends on ALL phases
    │
Phase 9: E2E Verification                   ← FINAL GATE
```

**Parallelism:** Phases 2-5 can execute in parallel once Phase 1 is complete. Phase 6 depends on all stage modules. Phase 7 is independent of Phases 2-6.

---

## Phase Handoff Files

Each phase has a serialized handoff document:

| File | Phase | Description |
|------|-------|-------------|
| `10-06-2026_memory-service-full-split_83c30c_p1-scaffold-store.md` | 1 | Scaffold directory structure + split store.py (3357 → 8 modules) |
| `10-06-2026_memory-service-full-split_83c30c_p2-ingest.md` | 2 | Split session_watcher.py → ingest/ package (Stage 1) |
| `10-06-2026_memory-service-full-split_83c30c_p3-consolidate.md` | 3 | Move arc_summarizer/ → consolidate/ + split pipeline.py (Stage 2) |
| `10-06-2026_memory-service-full-split_83c30c_p4-index.md` | 4 | Create index/ package from log_parsers.py (Stage 3) |
| `10-06-2026_memory-service-full-split_83c30c_p5-reconcile.md` | 5 | Merge reconciliation.py + ArcReconciler → reconcile/ (Stage 4) |
| `10-06-2026_memory-service-full-split_83c30c_p6-recall.md` | 6 | Split layer.py → recall/ + channels/ (Recall Layer) |
| `10-06-2026_memory-service-full-split_83c30c_p7-crosscutting.md` | 7 | Move enrich/, review/, health/, analytics/ (Cross-cutting) |
| `10-06-2026_memory-service-full-split_83c30c_p8-composition.md` | 8 | Wire MemoryService facade + MCP + HTTP (Composition Root) |
| `10-06-2026_memory-service-full-split_83c30c_p9-e2e.md` | 9 | E2E runtime verification (no mocks, real pipeline) |

---

## Global Constraints

### Import Rules

1. **Pipeline stages may only depend on `store/` (Stage 5) and shared modules (`config.py`, `errors.py`).** No cross-stage imports. Stage 1 cannot import from Stage 4.
2. **Recall layer depends on all stages.** This is allowed — recall is a read-only fan-out.
3. **`MemoryService` facade is the single composition point.** All cross-module wiring happens in `__init__.py`.
4. **No circular imports.** If Module A needs Module B, A imports B — never both. Break cycles by extracting shared interfaces.
5. **Preserve public API.** External callers (`super_council.py`, `mcp_server.py` in super_council root, `voice_pipeline/`) must continue to work with `from super_council.memory_service import MemoryService`.

### Code Movement Rules

1. **Extract, don't rewrite.** Move existing code verbatim first. Refactor only to resolve import paths. No behavioral changes during the split.
2. **One class/function per file where it creates a natural boundary.** If a class has 800+ lines, split by cohesive responsibility.
3. **`__init__.py` exports must match old module exports.** Every symbol importable from `memory_service.store` before must be importable from `memory_service.store` after (via `__init__.py` re-export).
4. **Remove `UnifiedVectorStore` subclass.** It adds no value over `SQLiteVectorStore`. Export `SQLiteVectorStore` as the single class.

### Testing Rules

1. **No mock tests.** Every test uses real classes, real files, real databases.
2. **Stage-level smoke tests:** One test per stage that exercises the actual pipeline step (e.g., Stage 1: write JSONL → watch → verify MD file created).
3. **E2E runtime test:** One test that runs the full 5-stage pipeline end-to-end with real data.
4. **Regression gate:** `python -m memory_service --health` must return `{"healthy": true}` after every phase.

---

## Success Criteria

- [ ] All 16 original `memory_service/*.py` files replaced by new modular structure
- [ ] All 8 `arc_summarizer/*.py` files moved into `memory_service/consolidate/`
- [ ] `from super_council.memory_service import MemoryService` works identically
- [ ] `python -m memory_service --mcp-stdio` starts and accepts tool calls
- [ ] `python -m memory_service --health` reports all components healthy
- [ ] MCP tools `recall.unified`, `recall.context_slice`, `recall.run_snapshot` return correct results
- [ ] Stage 1 E2E: JSONL file appears → SessionWatcher processes → canonical MD written
- [ ] Stage 2 E2E: ArcPipeline runs tiered consolidation → arc-memory/ output created
- [ ] Stage 4 E2E: ArcReconciler processes consolidation → arc-reconcile/ output created
- [ ] Stage 5 E2E: SQLiteVectorStore indexes reconciliation output → searchable
- [ ] No circular imports (verified by `python -c "from super_council.memory_service import MemoryService"`)
- [ ] No behavioral regressions (all existing functionality preserved)
- [ ] `arc_summarizer/` directory removed (all content migrated)

---

## Caveats & Uncertainty

1. **`arc_summarizer/` is imported by `super_council.py` and external callers.** The `ArcSummarizer` class is used directly. The split must maintain backward compatibility via `arc_summarizer/__init__.py` shim OR update all callers. **Recommendation:** Keep `arc_summarizer/` as a shim package that re-exports from `memory_service.consolidate/` to minimize blast radius.

2. **`memory_layer.py`, `memory_config.py`, `relational_store.py`, `context_router.py`, `review_service.py` in `super_council/` root** are shim files that re-export from `memory_service/`. They must continue working.

3. **`test_e2e_chain.py` imports from `arc_summarizer/` directly.** Will need import path updates or shim preservation.

4. **`store.py` inter-method dependencies are deep.** Methods like `upsert_session_diary()` call `_extract_section()` which calls `_parse_raw_session_text()`. The split must preserve these internal call chains within the same sub-module.

5. **`layer.py` system_health() method** queries consolidation metrics, log channels, session diary, workflow state, failures, supervisor log, MCP queue. This is NOT a recall channel — it belongs in `health/checker.py` or `recall/system_health.py` as a standalone concern.

6. **The `micro_model.py` import path** (`from super_council.micro_model import MicroModelEnricher`) is used by `MemoryService._init_components()`. Must update to `from .enrich.enricher import MicroModelEnricher`.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Import breakage across phases | After each phase, run `python -c "from super_council.memory_service import MemoryService"` as a gate |
| Behavioral regression | No code rewriting — extract verbatim, fix imports only |
| `arc_summarizer/` callers break | Maintain shim package with re-exports |
| DB schema changes | None — this is a code reorganization only |
| Test failures | Run `python -m memory_service --health` after each phase |

---

## Execution Model

1. Execute Phase 1 (scaffold + store.py split) — this is the foundation
2. Execute Phases 2-5 in parallel (or sequentially if preferred)
3. Execute Phase 6 (recall layer) — depends on all stages
4. Execute Phase 7 (cross-cutting) — independent
5. Execute Phase 8 (composition root) — wires everything
6. Execute Phase 9 (E2E verification) — final gate

Each phase is a self-contained subagent task. Read the phase handoff file, execute, verify the completion gate, then proceed.
