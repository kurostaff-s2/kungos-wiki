# Pipeline Audit: memsearch Spec vs Current Implementation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `5fbb7c` |
| Entity type | `handoff` |
| Short description | Audit whether the current memory_service pipeline implements memsearch spec functionalities and achieves quality in runtime recalls |
| Status | `draft` |
| Source references | memsearch spec (below), `/home/chief/Coding-Projects/7-council/super_council/memory_service/` |
| Generated | 12-06-2026 |
| Next action / owner | Execute audit phases; report gaps with evidence |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** memsearch spec (inline below), pipeline architecture files
**Related codebases:** none
**Key files for this task:**
- `memory_service/__init__.py` — service entry point, component wiring
- `memory_service/ingest/session_watcher.py` — JSONL → canonical MD pipeline
- `memory_service/consolidate/pipeline.py` — Arc LLM consolidation pipeline
- `memory_service/consolidate/tier_writer.py` — MD file + DB upsert
- `memory_service/reconcile/reconciler.py` — LLM-driven reconciliation
- `memory_service/store/vector_store.py` — SQLite-vec vector store
- `memory_service/recall/layer.py` — unified recall orchestration
- `memory_service/recall/channels/` — all recall channels
- `memory_service/mcp_server.py` — MCP transport (SSE)

## Spec Requirements (from memsearch design)

### Core Architecture
1. **Markdown as source of truth** — memories are `.md` files, human-readable, editable, version-controllable
2. **Shadow index** — vector store is a derived, rebuildable cache (not the source of truth)
3. **Cross-agent memory sharing** — memories flow across Claude Code, OpenClaw, OpenCode, Codex CLI
4. **Plugin architecture** — agent users install plugin, get persistent memory with zero effort
5. **CLI/Python API** — agent developers use `index`, `search`, `expand`, `watch`, `compact` commands

### Recall Architecture
6. **3-layer progressive retrieval** — search → expand → transcript
7. **Hybrid search** — dense vector + BM25 sparse + RRF reranking
8. **Smart dedup** — SHA-256 content hashing skips unchanged content
9. **Live sync** — file watcher auto-indexes in real time

### Use Cases
10. **Resume debugging threads** — ask how a similar Redis, Docker, database, or deployment issue was fixed last time
11. **Recover decision rationale** — find why the project chose one architecture, library, migration path, or API design over another
12. **Trace feature history** — understand how a feature evolved across sessions, including files changed and tradeoffs discussed
13. **Do code archaeology** — ask when and why a module, config, or workflow was changed before touching it again
14. **Find the right session to resume** — ask which previous conversation covered a topic, recover relevant context, continue from there
15. **Carry context across agents** — keep Claude Code, Codex CLI, OpenClaw, OpenCode working from the same project memory

## Audit Phases

### Phase 1: Architecture Audit — Core Design Principles

**What:** Verify whether the current pipeline implements the core architectural principles from the spec.

**Steps:**

1. **Markdown as source of truth**
   - Verify: `session_watcher.py` writes canonical MD files to `~/.council-memory/`
   - Verify: `tier_writer.py` writes consolidation output to `arc-memory/daily/`, `arc-memory/short/`, etc.
   - Verify: MD files are human-readable, editable, version-controllable (git-tracked)
   - Check: Are MD files the authoritative source, or is the DB the source?
   - Check: Can MD files be edited manually and re-indexed?

2. **Shadow index (rebuildable cache)**
   - Verify: `vector_store.py` can be rebuilt from scratch without data loss
   - Verify: `reindex_db_tables()` and `reindex_existing_data()` can regenerate the entire index
   - Check: If vector store DB is deleted, can it be fully rebuilt from MD files + relational DB?
   - Check: Is there a `memsearch compact` equivalent?

3. **Cross-agent memory sharing**
   - Verify: MCP server (`mcp_server.py`) exposes recall tools to multiple agent clients
   - Check: Can multiple agents connect simultaneously via SSE?
   - Check: Is there a plugin for Claude Code, OpenClaw, OpenCode, Codex CLI?
   - Check: Do agents share the same `~/.council-memory/` directory?

4. **Plugin architecture**
   - Check: Is there a plugin/install mechanism for agent users?
   - Check: Is the MCP server the "plugin" equivalent?

5. **CLI/Python API**
   - Check: Is there a CLI with `index`, `search`, `expand`, `watch`, `compact` commands?
   - Check: Is there a Python API for embedding memory in custom agents?
   - Check: What's the equivalent of `memsearch search "query"`?

**Evidence to collect:** File paths, code snippets, runtime verification results.

---

### Phase 2: Recall Architecture Audit — Search Quality

**What:** Verify whether the recall pipeline implements hybrid search, progressive retrieval, dedup, and live sync.

**Steps:**

1. **3-layer progressive retrieval**
   - Check: Does `recall.unified()` implement search → expand → transcript?
   - Check: Is there an "expand" operation that retrieves full MD sections from chunk hashes?
   - Check: Is there a "transcript" operation that retrieves raw `session.jsonl` dialogue?
   - Verify: Current implementation uses channel-based parallel search, not progressive layers

2. **Hybrid search (dense + BM25 + RRF)**
   - Check: Does `vector_store.search()` use BM25 sparse vectors alongside dense embeddings?
   - Check: Is there RRF (Reciprocal Rank Fusion) reranking across dense and sparse results?
   - Verify: Current implementation uses cosine similarity only (dense)
   - Check: Are FTS5 indexes used for BM25-like sparse search?
   - Check: Are FTS5 results fused with vector results via RRF?

3. **Smart dedup (SHA-256 content hashing)**
   - Check: Does `vector_store.index()` compute SHA-256 hash before embedding?
   - Check: Are unchanged chunks skipped (no API call to embedding model)?
   - Verify: Current implementation embeds every row on reindex — no content hash check

4. **Live sync (file watcher)**
   - Verify: `session_watcher.py` detects new JSONL files and processes them
   - Check: Is there a file watcher on `arc-memory/` for manual MD edits?
   - Check: Is there a `memsearch watch` equivalent that auto-indexes file changes?
   - Verify: Current implementation uses scheduled consolidation, not real-time file watching

**Evidence to collect:** Code paths, missing features, runtime test results.

---

### Phase 3: Runtime Recall Quality — Use Case Verification

**What:** Execute runtime recall tests against each specified use case and measure quality.

**Pre-flight:** Ensure `memory-service` is running (`systemctl --user status memory-service`).

**Test methodology:** For each use case, execute `recall.unified()` with representative queries and evaluate:
- **Relevance:** Do results match the query intent? (score 1-5)
- **Completeness:** Do results include sufficient context to act on? (score 1-5)
- **Latency:** Is response time acceptable (<2s for single channel, <5s for all)? (pass/fail)
- **Structured data:** Are decisions, open items, deviations surfaced as structured fields? (yes/no)

**Test queries (execute against live service):**

```python
from memory_service import MemoryService
ms = MemoryService.load()

# Use case 10: Resume debugging threads
result = ms.layer.unified_recall(
    query="how was the Milvus lock contention bug fixed",
    scope='repair', max_tokens=8192
)

# Use case 11: Recover decision rationale
result = ms.layer.unified_recall(
    query="why was LanceDB rejected in favor of SQLite-vec",
    scope='decision', max_tokens=8192
)

# Use case 12: Trace feature history
result = ms.layer.unified_recall(
    query="how did the recall channel architecture evolve",
    scope='all', max_tokens=8192
)

# Use case 13: Code archaeology
result = ms.layer.unified_recall(
    query="when was the vector store migrated from Milvus to SQLite-vec",
    scope='architecture', max_tokens=8192
)

# Use case 14: Find right session to resume
result = ms.layer.unified_recall(
    query="session about memory service pipeline audit",
    scope='run', max_tokens=8192
)

# Use case 15: Cross-agent context
result = ms.layer.unified_recall(
    query="memory service current status and health",
    scope='status', max_tokens=8192
)
```

**For each test, record:**
- Query text
- Scope used
- Latency (ms)
- Active channels (count + names)
- Match count per channel
- Fused context length (chars)
- Relevance score (1-5) with evidence
- Completeness score (1-5) with evidence
- Structured data present? (yes/no, which fields)

**Quality threshold:** Each use case must score ≥3 on relevance AND ≥3 on completeness to pass.

---

### Phase 4: Gap Analysis and Recommendations

**What:** Synthesize findings from Phases 1-3 into a gap report with prioritized recommendations.

**Steps:**

1. **Map spec requirements to implementation status:**

| # | Spec Requirement | Implemented | Partial | Missing | Evidence |
|---|-----------------|-------------|---------|---------|----------|
| 1 | Markdown as source of truth | ✅ / ⚠️ / ❌ | | | |
| 2 | Shadow index (rebuildable) | | | | |
| 3 | Cross-agent sharing | | | | |
| 4 | Plugin architecture | | | | |
| 5 | CLI/Python API | | | | |
| 6 | 3-layer progressive retrieval | | | | |
| 7 | Hybrid search (dense+BM25+RRF) | | | | |
| 8 | SHA-256 content dedup | | | | |
| 9 | Live sync / file watcher | | | | |
| 10 | Resume debugging threads | | | | |
| 11 | Recover decision rationale | | | | |
| 12 | Trace feature history | | | | |
| 13 | Code archaeology | | | | |
| 14 | Find session to resume | | | | |
| 15 | Cross-agent context | | | | |

2. **Prioritize gaps by impact:**
   - **P0 (blocking):** Gaps that prevent core use cases from working
   - **P1 (quality):** Gaps that degrade recall quality but don't block
   - **P2 (nice-to-have):** Gaps that add polish but don't affect core functionality

3. **Produce recommendations:**
   - For each P0/P1 gap: specific implementation approach, estimated effort, dependencies
   - For each P2 gap: note for future consideration

**Output:** Completed gap table + prioritized recommendations.

---

### Phase 5: Production Verification

**What:** Final end-to-end verification that the audit is complete and accurate.

**Steps:**

1. Verify all Phase 1-4 steps completed
2. Run full test suite: `cd ~/Coding-Projects/7-council/super_council && python3 -m pytest tests/ -v --tb=short`
3. Verify memory-service is healthy: `systemctl --user status memory-service`
4. Verify no regression in existing recall channels
5. Produce final audit report

**Completion gate:**
- [ ] All 15 spec requirements audited with evidence
- [ ] All 6 use cases tested with quality scores
- [ ] Gap table completed with P0/P1/P2 prioritization
- [ ] Recommendations produced for P0/P1 gaps
- [ ] No regression in existing functionality
- [ ] Audit report saved to `/home/chief/llm-wiki/00-prompt-handoff/`

---

## Constraints

- **Read-only audit:** Do not modify production code during audit. All changes go through separate handoff tasks.
- **Evidence-first:** Every finding must include code paths, runtime output, or data as evidence. No assertions without proof.
- **Runtime verification:** Test against live `memory-service` (PID from `systemctl --user status memory-service`), not mocks.
- **Quality scores must be justified:** Each 1-5 score must include a specific quote or data point from the results.
- **Markdown source of truth check:** If MD files are NOT the authoritative source, flag as P0 gap with evidence.

## Success Criteria

- [ ] All 15 spec requirements mapped to implementation status (✅/⚠️/❌)
- [ ] All 6 use cases tested with relevance + completeness scores
- [ ] Gap table completed with evidence for each entry
- [ ] P0/P1 gaps have specific implementation recommendations
- [ ] No production code modified during audit
- [ ] Audit report saved to handoff directory
- [ ] No regression in existing test suite

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/llm-wiki/00-prompt-handoff/12-06-2026_pipeline-audit-memsearch-spec_5fbb7c_report.md` | Final audit report with gap table |

## Caveats & Uncertainty

- **memsearch spec is aspirational:** The spec describes the ideal architecture. The current pipeline adopted elements but may have diverged. Audit must distinguish between "never implemented" vs "implemented differently."
- **Cross-agent sharing may be out of scope:** If only one agent (pi) uses the memory service, cross-agent sharing may be a future goal, not a current requirement. Flag but don't score as P0 unless confirmed as current requirement.
- **Plugin architecture may be MCP equivalent:** The MCP server may serve the same purpose as the "plugin" in the spec. Evaluate functional equivalence, not name matching.
- **Hybrid search may be phased:** BM25 + RRF may be planned but not yet implemented. Distinguish between "missing" and "planned."
