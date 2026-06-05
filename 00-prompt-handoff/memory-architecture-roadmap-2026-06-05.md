# Memory Architecture: First-Principles Roadmap

> **Date:** 2026-06-05
> **Scope:** Complete recall tool consolidation, L2/L3 implementation, routing decision, framework decision
> **Based on:** three-tier-injection-plan.md v1.0, live codebase audit, first-principles analysis

---

## Part 1: Current State Verification

### What the Analysis Got Right

The comprehensive analysis correctly identified:
- **L1 works** — `get_startup_context()` in router.py:598, wired into MCP as `recall_startup_context`
- **L2/L3 are missing** — No `get_dispatch_context()` or `get_repair_context()` in ContextRouter
- **Circuit breaker exists but unused** — `injection_blacklist` table in store.py but zero callers
- **Recency weighting partial** — `apply_recency_weighting()` exists in layer.py but not wired into L1

### What the Analysis Missed (Codebase Audit)

The analysis proposed consolidating to 3 tools (`recall`, `recall.logs`, `recall.index`). But the **actual current state** is more nuanced:

**Existing recall tools (22 MCP tools, ~12 recall-related):**

| Tool | Backend | Read/Write | Status |
|------|---------|------------|--------|
| `council-recall` | MemoryLayer.unified_recall() | READ | ✅ Working (3-channel) |
| `get_context_slice` | MemoryLayer | READ | ✅ Working |
| `get_recent_events` | ContextRouter | READ | ✅ Working |
| `get_run_snapshot` | ContextRouter | READ | ✅ Working |
| `summarize_run_issues` | ContextRouter | READ | ✅ Working |
| `get_review_findings` | ContextRouter | READ | ✅ Working |
| `query_session_diary` | ContextRouter | READ | ✅ Working |
| `recall_startup_context` | ContextRouter | READ | ✅ Working (L1) |
| `unified_log_recall` | MemoryLayer | READ | ✅ Working |
| `memsearch_index_file` | MemIndex | WRITE | ✅ Working |
| `memsearch_status` | MemIndex | READ | ✅ Working |
| `upsert_summary` | RelationalStore | WRITE | ✅ Working |
| `review.start` | ReviewService→RelationalStore | WRITE | ✅ Working |
| `review.log` | ReviewService→RelationalStore | WRITE | ✅ Working |
| `review.verdict` | ReviewService→RelationalStore | WRITE | ✅ Working |

**Key insight:** The routing is already clean:
- **All reads** go through ContextRouter or MemoryLayer (which wraps ContextRouter)
- **All writes** go through ReviewService → RelationalStore or directly to RelationalStore
- **Exception:** `memsearch_index_file` writes directly to Milvus (acceptable — it's vector indexing, not state)

---

## Part 2: First-Principles Analysis

### 1. Problem Essence

**Core problem:** The agent wastes turns selecting among 12+ similar recall tools, getting fragmented or irrelevant context.

**So what? chain:**
- "12 recall tools" → Agent picks wrong one → Gets incomplete context → Repeats work or hallucinates
- "So what?" → Wasted turns = wasted time + tokens
- "So what?" → Agent can't reliably build on past work → Each session starts cold

**JTBD:** "When I need context about past work, I want ONE reliable entry point that returns the right slice — fast, relevant, provenanced."

**Success criteria:**
1. ≤1 tool call for 90% of recall needs
2. Results carry provenance (source, date, score)
3. Latency < 2s end-to-end
4. Token budget enforced at retrieval, not after

### 2. Assumptions Challenged

| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| "We need to consolidate to 3 tools" | Historical | `council-recall` already IS the unified tool. The fragmentation is in **specialized tools** (snapshot, events, findings) that serve real use cases | **Investigate** — consolidate only the overlapping ones |
| "All reads through ContextRouter" | Technical | MemoryLayer.unified_recall() already does 3-channel recall. ContextRouter is a query layer; MemoryLayer is the fusion layer | **Keep both** — ContextRouter for queries, MemoryLayer for fusion |
| "All writes through RelationalStore" | Technical | Already true. upsert_summary → RelationalStore, review.* → ReviewService → RelationalStore | **Already correct** — no change needed |
| "SQLAlchemy would help" | Technical | SQLite + raw SQL works fine for this scale (<10K rows). SQLAlchemy adds ORM overhead for no benefit | **Discard** — raw sqlite3 is the right choice |
| "The agent can't pick the right tool" | Resource | True for 12 similar tools. But 3-4 well-named tools are fine | **Reduce, don't eliminate** — keep specialized tools for specific needs |

### 3. Ground Truths

1. **Token budget is hard:** ~4096 tokens per recall call. Anything beyond is discarded.
2. **Read/write separation already exists:** ContextRouter (reads) + RelationalStore (writes) is working.
3. **One fusion tool exists:** `council-recall` (→ `recall.unified` in Pi) already does 3-channel recall.
4. **Latency matters:** Embedding latency is ~155ms. Multiple sequential calls = timeout risk.
5. **Provenance is in the data:** Results already carry [source/score] tags from memsearch.
6. **Scale is small:** <10K rows in SQLite. No need for ORM or connection pooling.

### 4. Reasoning Chain

```
GT: council-recall already does 3-channel recall
  → The "consolidate to 3 tools" proposal is partially done
  → What's missing: L2/L3 injection, not tool consolidation
  
GT: Read/write routing already works
  → ContextRouter = read queries, RelationalStore = writes
  → No architectural change needed for routing
  
GT: SQLAlchemy adds overhead for no benefit
  → SQLite with <10K rows doesn't need ORM
  → Raw sqlite3 with WAL mode is sufficient
  → Discard SQLAlchemy
  
GT: L2/L3 are the real gaps
  → L2: get_dispatch_context() doesn't exist
  → L3: get_repair_context() doesn't exist
  → These are the priority, not tool consolidation
```

### 5. Conclusion

**Recommended approach:** Keep existing routing (ContextRouter reads, RelationalStore writes). Complete L2/L3. Consolidate only truly overlapping tools. Stay with raw sqlite3.

**Key insight:** The analysis was right about the symptoms (fragmentation, missing L2/L3) but wrong about the cure (massive tool consolidation). The real fix is completing the planned architecture, not restructuring what already works.

**Trade-offs acknowledged:**
- Keeping specialized tools means slightly more choice for the agent (but well-named tools are fine)
- Not adopting SQLAlchemy means manual SQL (but at this scale, it's a feature, not a bug)
- Prioritizing L2/L3 over tool consolidation means fragmentation persists but with working core features

**Confidence:** High — based on actual codebase audit, not just plan documents

---

## Part 3: Routing Decision

### Question: Should all read-only tools route through ContextRouter?

**Answer: YES, with MemoryLayer as the fusion layer.**

Current routing (already correct):
```
Agent calls recall tool
  → MCP Server (mcp_server.py)
    → ContextRouter (router.py) — structured queries
    → MemoryLayer (layer.py) — fusion, token budgeting, 3-channel recall
      → ContextRouter — for artifact/event queries
      → MemIndex — for vector search
      → RelationalStore — for direct DB queries (fallback)
```

The only exception is `unified_log_recall` which queries external log sources (daily logs, systemd journal). This correctly stays in MemoryLayer since ContextRouter doesn't handle file-based logs.

### Question: Should all write tools route through RelationalStore?

**Answer: YES, already true.**

Current write routing:
```
upsert_summary → RelationalStore.upsert_session_diary() / upsert_raw_session_memory()
review.start   → ReviewService.start_review() → RelationalStore
review.log     → ReviewService.log_finding() → RelationalStore
review.verdict → ReviewService.record_verdict() → RelationalStore
```

The only "write" that bypasses RelationalStore is `memsearch_index_file` → Milvus directly, which is correct (vector index is separate from relational state).

### Question: Should we adopt SQLAlchemy?

**Answer: NO.**

| Factor | Raw sqlite3 | SQLAlchemy |
|--------|-------------|------------|
| Complexity | Low — direct SQL | Medium — ORM layer, sessions, declarative base |
| Performance | Direct — no overhead | ~10-20% overhead for ORM mapping |
| Scale fit | Perfect for <10K rows | Overkill for <10K rows |
| Migration | Manual SQL files (already working) | Alembic migrations (adds tooling) |
| Team familiarity | Python stdlib | Additional dependency |
| WAL mode | Direct PRAGMA control | Works but less transparent |

**Verdict:** Raw sqlite3 is the right choice. The codebase already has:
- WAL mode + FK enforcement
- Migration files in `migrations/`
- Parameterized queries (no SQL injection)
- Row factory for dict-like access

Adding SQLAlchemy would be a refactor for refactor's sake.

---

## Part 4: Roadmap

### Phase 0: Tool Consolidation (Quick Wins) — 2-3 hours

**Goal:** Reduce recall tool count from 12 to 6 by merging overlapping tools.

**Merge these:**
- `get_context_slice` → fold into `recall.unified` with `scope="slice"` parameter
- `get_recent_events` → fold into `recall.unified` with `scope="events"` parameter
- `get_run_snapshot` → fold into `recall.unified` with `scope="snapshot"` parameter
- `summarize_run_issues` → fold into `recall.unified` with `scope="issues"` parameter
- `get_review_findings` → fold into `recall.unified` with `scope="findings"` parameter

**Keep as-is (unique capabilities):**
- `recall.unified` — 3-channel recall (primary entry point)
- `unified_log_recall` — log sources (different data, different channels)
- `recall_startup_context` — L1 specific (will be replaced by L2/L3)
- `memsearch_status` — diagnostics only
- `memsearch_index_file` — vector indexing (write operation)

**Implementation:**
1. Add `scope` parameter to `council-recall` MCP tool
2. Route scopes to existing ContextRouter/MemoryLayer methods
3. Deprecate individual tools (keep working, mark as deprecated in descriptions)
4. Update Pi extension tool descriptions to favor `recall.unified`

**Tests:** Verify `recall.unified(scope="snapshot", run_id="...")` returns same data as `get_run_snapshot(run_id="...")`

### Phase 1: L2 — Pre-Dispatch Injection — 3-4 hours

**Goal:** Implement `get_dispatch_context()` in ContextRouter.

**Steps:**
1. **New ContextRouter method:** `get_dispatch_context(task, phase, project_id, max_tokens=1024)`
   - memsearch vector search on task description (top 3)
   - RelationalStore artifact search (phase + project filtered)
   - Review findings (project-scoped, recent 5)
   - Deduplication + token budget enforcement
   - Return formatted `<historical_reference>` block

2. **New MCP tool:** `recall.dispatch_context`
   - Parameters: task, phase, project_id, max_tokens
   - Routes to ContextRouter.get_dispatch_context()

3. **New Pi extension tool:** `recall.dispatch_context`
   - Exposes MCP tool to agent

4. **Wire into SlotSupervisor:** `_inject_tier2_dispatch_context()`
   - Called in `_delegate()` before model swap
   - Injects `<historical_reference>` block into task prompt

**Tests:**
- `test_dispatch_context_returns_task_relevant_memory()`
- `test_dispatch_context_respects_token_budget()`
- `test_dispatch_context_filters_by_phase()`
- `test_dispatch_context_deduplicates()`

### Phase 2: L3 — Adaptive Repair Injection — 3-4 hours

**Goal:** Implement `get_repair_context()` in ContextRouter.

**Steps:**
1. **New ContextRouter method:** `get_repair_context(error_signature, phase, max_tokens=2048)`
   - Query `failure_classifications` for matching error patterns
   - Query `artifact_summaries` for error keywords
   - memsearch vector search on error string
   - RED Gate validation on recalled solutions
   - Deduplication + token budget enforcement
   - Return formatted `<repair_hints>` block

2. **New MCP tool:** `recall.repair_context`
   - Parameters: error_signature, phase, max_tokens
   - Routes to ContextRouter.get_repair_context()

3. **New Pi extension tool:** `recall.repair_context`

4. **Wire into SlotSupervisor:** `_inject_tier3_repair_context()`
   - Called in `_execute_phase()` on repair attempt (attempt > 1)
   - Injects `<repair_hints>` block into repair prompt

**Tests:**
- `test_repair_context_returns_error_matches()`
- `test_repair_context_validates_via_red_gate()`
- `test_repair_context_respects_token_budget()`

### Phase 3: Circuit Breaker Wiring — 2-3 hours

**Goal:** Wire `injection_blacklist` into all three tiers.

**Steps:**
1. **ContextRouter method:** `get_blacklist_status(pattern_type)`
   - Query `injection_blacklist` for active entries
2. **SlotSupervisor methods:**
   - `_check_circuit_breaker(pattern, pattern_type)` — is pattern blacklisted?
   - `_record_injection_failure(pattern, pattern_type, error)` — record failure
3. **Wire into all three tiers:** Check blacklist before injection, record failures
4. **New MCP tool:** `recall.blacklist_status`

**Tests:**
- `test_circuit_breaker_blocks_blacklisted_pattern()`
- `test_circuit_breaker_activates_after_threshold()`
- `test_injection_failure_recorded()`

### Phase 4: Recency Weighting — 1-2 hours

**Goal:** Wire `apply_recency_weighting()` into all three tiers.

**Steps:**
1. Ensure `MemoryLayer.apply_recency_weighting()` is production-ready
2. Apply in `get_startup_context()` — older consolidation entries truncated first
3. Apply in `get_dispatch_context()` — older entries get lower priority
4. Apply in `get_repair_context()` — older solutions get lower priority

**Tests:**
- `test_recency_weighting_in_tier1()`
- `test_recency_weighting_in_tier2()`
- `test_recency_weighting_in_tier3()`

### Phase 5: Golden Path E2E — 2-3 hours

**Goal:** End-to-end tests for all three tiers.

**Tests:**
- `test_golden_path_tier1_startup()` — consolidation → cache → injection
- `test_golden_path_tier2_dispatch()` — task → dispatch context → injection
- `test_golden_path_tier3_repair()` — error → repair context → RED gate → injection
- `test_golden_path_circuit_breaker()` — repeated failure → blacklist → blocked
- `test_golden_path_recency_weighting()` — old vs new → correct priority
- `test_golden_path_token_budget()` — all tiers respect max_tokens

---

## Part 5: Final Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent (Pi)                               │
│                                                                 │
│  recall.unified(query, scope, ...)  ← ONE entry point           │
│  recall.logs(query, channels, ...)  ← ops-only                  │
│  memory.upsert_summary(text)       ← write path                 │
│  review.start/log/verdict          ← write path                 │
└──────────────┬──────────────────────────────────────────────────┘
               │ MCP (SSE)
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Server (mcp_server.py)                  │
│                                                                 │
│  council-recall       → MemoryLayer.unified_recall()            │
│  unified_log_recall   → MemoryLayer.unified_log_recall()        │
│  recall_startup       → ContextRouter.get_startup_context()     │
│  recall.dispatch      → ContextRouter.get_dispatch_context()    │
│  recall.repair        → ContextRouter.get_repair_context()      │
│  upsert_summary       → RelationalStore.upsert_*()              │
│  review.*             → ReviewService → RelationalStore         │
└──────────────┬──────────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌──────────────┐  ┌──────────────┐
│ ContextRouter │  │ MemoryLayer  │
│ (queries)     │  │ (fusion)     │
│               │  │              │
│ get_run_      │  │ unified_     │
│   snapshot    │  │   recall()   │
│ get_recent_   │  │              │
│   events      │  │ get_context_ │
│ get_artifacts │  │   slice()    │
│ get_startup_  │  │              │
│   context     │  │ apply_recency│
│ get_dispatch_ │  │   _weighting │
│   context     │  │              │
│ get_repair_   │  │ unified_log_ │
│   context     │  │   recall()   │
└──────┬───────┘  └──────┬───────┘
       │                 │
       ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RelationalStore (store.py)                     │
│                                                                 │
│  SQLite (WAL mode, FK enforcement)                              │
│  pipelines | workflow_runs | artifacts | event_log               │
│  state_executions | artifact_summaries | failure_classifications │
│  consolidation_cache | injection_blacklist | session_diary       │
│  raw_session_memories                                             │
│                                                                 │
│  All writes flow here. All reads via ContextRouter/MemoryLayer. │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 6: Stress Test

1. **If scope="all" returns too much:** Token budget (max_tokens) cuts it. Agent can re-query with narrower scope.
2. **If memsearch is slow:** FTS5 + LIKE provide keyword fallback. Parallel execution means fast channels don't wait.
3. **If Milvus goes down:** Graceful degradation to DB-only (already implemented in unified_recall).
4. **If L2 injection bloats prompts:** Token budget (1024 default) + recency weighting prevents bloat.
5. **If circuit breaker is too aggressive:** Configurable threshold (default 3), manual override via MCP.

---

## Part 7: Revisit Triggers

- **Tool consolidation:** Revisit if agent tool selection improves (better LLM routing)
- **SQLAlchemy:** Revisit if DB grows beyond 100K rows or team needs ORM features
- **L2/L3 budgets:** Revisit if token budgets are consistently exceeded or underutilized
- **Circuit breaker threshold:** Revisit if false positives/negatives are observed

---

## Summary

| Decision | Verdict | Rationale |
|----------|---------|-----------|
| Consolidate to 3 tools? | **Partial** — merge overlapping ones, keep unique | `council-recall` already does 3-channel recall |
| All reads through ContextRouter? | **YES** — already true | Clean separation of concerns |
| All writes through RelationalStore? | **YES** — already true | Single source of truth |
| Adopt SQLAlchemy? | **NO** | Overhead for no benefit at current scale |
| Complete L2/L3? | **YES** — highest priority | Real missing features, not theoretical |
| Wire circuit breaker? | **YES** — after L2/L3 | Safety mechanism for new features |
| Wire recency weighting? | **YES** — with L2/L3 | Quality improvement for all tiers |

**Total effort:** ~15-18 hours across 5 phases
**Priority order:** Phase 1 (L2) → Phase 2 (L3) → Phase 3 (circuit breaker) → Phase 4 (recency) → Phase 0 (tool consolidation) → Phase 5 (E2E)
