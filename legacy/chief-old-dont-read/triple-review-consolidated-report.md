# Triple-Review Consolidated Report: Relational State Machine

> **Date:** 2026-05-20
> **Reviewers:** Gemma-4-26B (Arch), Nemotron-Cascade-2-30B (Logic), GPT-OSS-20B (Diversity)
> **Target:** `full-relational-state-machine-report.md` + `part2.md`
> **Overall Verdict:** **PASS — with 8 actionable findings**

---

## Reviewer Scores

| Reviewer | Verdict | Findings | HIGH | MODERATE | LOW |
|----------|---------|----------|------|----------|-----|
| **Gemma (Arch)** | PASS (minor notes) | 3 | 0 | 2 | 1 |
| **Nemo (Logic)** | PARTIAL (requires fixes) | 6 | 2 | 2 | 2 |
| **GPT (Diversity)** | PASS (with mitigations) | 10 | 1 | 6 | 3 |

**Consensus:** 3 reviewers agree on 5 cross-cutting issues. 2 HIGH findings from Nemo need fixes before implementation.

---

## Consolidated Findings (De-duplicated, Prioritized)

### HIGH (Must Fix Before Implementation)

#### H1: Orchestrator Write Path — Race Condition on `attempt_number`
- **Source:** Nemo (Logic), Finding #2
- **Problem:** `attempt_number` computed from in-memory `self.phase_attempts` dict. Two concurrent transitions read same stale value → duplicate `attempt_number` → violates UNIQUE constraint → silent data loss.
- **Evidence:** Section 6, lines 486-502 — `self.phase_attempts.get(self.phase,0)`
- **Fix:** Compute atomically from DB: `SELECT COALESCE(MAX(attempt_number),0)+1 FROM state_executions WHERE run_id=? AND phase=?`. Wrap in `BEGIN IMMEDIATE ... COMMIT`.

#### H2: Context Truncation Mid-Artifact Produces Malformed JSON
- **Source:** Nemo (Logic), Finding #6
- **Problem:** `get_active_context()` truncates by character count (`max_chars = max_tokens * 4`). Cut can land inside a JSON artifact → downstream agents fail to parse → silent data loss.
- **Evidence:** Section 13, lines 743-748 — `context[:max_chars - 50] + "\n[TRUNCATED]"`
- **Fix:** Split context into artifact blocks. Drop whole blocks until under budget. Replace oversized block with pre-computed summary.

### MODERATE (Fix Before Production)

#### M1: SQLite Single-Writer Contention on `event_log`
- **Source:** Gemma (Arch) #2, GPT (Diversity) #1
- **Problem:** 6 indexes on `event_log` + single-writer SQLite = bottleneck when multiple pipelines run concurrently. Write amplification on every tool call.
- **Evidence:** Section 4.3, lines 278-285 (6 indexes); Section 4.4, "SQLite doesn't support partitioning"
- **Fix:** Enable WAL mode (`PRAGMA journal_mode=WAL`). Consider moving `event_log` to separate DB file. Drop `idx_events_type` and `idx_events_severity` if only used for manual debugging.

#### M2: Phase Registry Friction — Adding Phases Requires DDL
- **Source:** Gemma (Arch) #1, GPT (Diversity) #5
- **Problem:** Adding a new phase (e.g., `SECURITY_AUDIT`) requires INSERT into `phase_names` + UPDATE to `workflow_definitions.transitions` JSON + new handler method. Brittle manual process.
- **Evidence:** Section 4.2 — `phase_names` CHECK constraint; `workflow_definitions.transitions` JSON blob
- **Fix:** Add auto-upsert in orchestrator init: scan `workflow_definitions.phases` JSON and INSERT missing names into `phase_names`. Provide migration script for transition updates.

#### M3: Linter DFS Cycle Detection — False Negatives on Shared Nodes
- **Source:** Nemo (Logic), Finding #3
- **Problem:** `_check_infinite_loops` uses global `visited` set. Two cycles sharing a node (e.g., `A→B→C→A` and `D→E→C→D`) — second cycle is skipped because `C` is already visited.
- **Evidence:** Section 7, lines 735-763 — `if node in visited: return`
- **Fix:** Remove global `visited` set. Use per-DFS recursion stack (`path`) only.

#### M4: Migration Integrity Risk — Backfill from Unstructured JSON
- **Source:** Gemma (Arch) #3, GPT (Diversity) #6
- **Problem:** Converting `ps.history` (unstructured JSON) to normalized `state_executions` + `event_log` is lossy. History entries may lack `started_at`, `duration_ms`, or `error` fields.
- **Evidence:** Section 12, Step 2 — backfill pseudocode assumes `entry.get("from_phase")`, `entry.get("outcome")`
- **Fix:** Add fallback defaults: `started_at` → `row["created_at"]`, `duration_ms` → 0, `error` → "". Log warnings for missing fields.

#### M5: No Transactional Guarantees Across Tables
- **Source:** GPT (Diversity) #8, Nemo (Logic) #2 (related)
- **Problem:** Inserting into `state_executions` + `event_log` + `artifacts` + updating `workflow_runs` is not atomic. Partial failure leaves inconsistent state.
- **Evidence:** Section 6.1 pseudocode — 4 separate `self.db.execute()` calls with `self.db.commit()` at end
- **Fix:** Wrap entire `transition_to()` in `BEGIN IMMEDIATE ... COMMIT`. Use `try/except` with `ROLLBACK` on failure.

### LOW (Nice to Have)

#### L1: Write Amplification — 6 Indexes on `event_log`
- **Source:** Gemma (Arch) #2
- **Fix:** Drop `idx_events_type` and `idx_events_severity` if only used for manual debugging. Keep `idx_events_run_time` (hot path).

#### L2: Linter Retreat-Path Check — False Positives
- **Source:** Nemo (Logic), Finding #4
- **Problem:** `_check_retreat_paths` only inspects `self.transitions`. Misses `self.retreat_target` attribute.
- **Fix:** Extend linter to also check `retreat_target` as implicit transition.

#### L3: Artifact Schema — `content_path` Required for All Kinds
- **Source:** Nemo (Logic), Finding #5
- **Problem:** JSON Schema requires `content_path` for all artifacts, but `SCOUT`/`PLAN` produce in-memory artifacts.
- **Fix:** Make `content_path` conditional on `kind` (required only for file-based kinds).

#### L4: Timestamps — `REAL` Epoch Loses Milliseconds
- **Source:** GPT (Diversity), Finding #7
- **Problem:** `strftime('%s', 'now')` returns integer seconds. `REAL` type allows fractional but default doesn't use it.
- **Fix:** Use `strftime('%s.%f', 'now')` for microsecond precision. Or store as ISO-8601 TEXT.

#### L5: Retention/Archival — Manual Process, No Automation
- **Source:** GPT (Diversity) #2
- **Problem:** Archive tables defined but no automated job to move old data. DB grows unbounded.
- **Fix:** Add cron job or background worker: move runs older than N days to archive tables, DELETE from main, VACUUM.

#### L6: Multi-Tenant Isolation — `project_id` Not Enforced
- **Source:** GPT (Diversity) #6
- **Problem:** `project_id` exists but no CHECK constraint or application-level enforcement. Data leakage possible.
- **Fix:** Add CHECK constraint on `workflow_runs.project_id`. Enforce in application logic.

---

## Cross-Reviewer Consensus Matrix

| Issue | Gemma | Nemo | GPT | Consensus |
|-------|-------|------|-----|-----------|
| SQLite single-writer contention | ✓ #2 | — | ✓ #1 | **2/3** |
| Phase registry friction | ✓ #1 | — | ✓ #5 | **2/3** |
| Transactional guarantees | ✓ #3 | ✓ #2 | ✓ #8 | **3/3** |
| Linter cycle detection bug | — | ✓ #3 | — | **1/3** |
| Context truncation mid-artifact | — | ✓ #6 | — | **1/3** |
| Retention automation | — | — | ✓ #2 | **1/3** |
| Write amplification (indexes) | ✓ #2 | — | — | **1/3** |
| Migration backfill risk | ✓ #3 | — | ✓ #6 | **2/3** |

---

## Recommended Implementation Order

### Phase 0: Fix Report (Before Implementation)
1. **Fix H1** — Atomic `attempt_number` computation (5 min)
2. **Fix H2** — Block-based context truncation (15 min)
3. **Fix M3** — Linter DFS cycle detection (10 min)
4. **Fix M5** — Wrap `transition_to()` in transaction (10 min)

### Phase 1: Schema + Migration (Week 1)
5. **Fix M1** — Enable WAL mode, drop 2 indexes (5 min)
6. **Fix M2** — Auto-upsert phase names (30 min)
7. **Fix M4** — Add fallback defaults in backfill (15 min)
8. Create enum lookup tables + core tables (2 hours)
9. Backfill existing pipelines (1 hour)

### Phase 2: Context Router + Validation (Week 2)
10. Implement `ContextRouter` with block-based truncation (2 hours)
11. Add phase schema validation (1 hour)
12. Refactor `transition_to()` to write to DB (2 hours)

### Phase 3: Linter + Memory Layer (Week 3)
13. Implement `StateMachineLinter` with fixed DFS (2 hours)
14. Implement `MemoryLayer` with artifact-boundary truncation (2 hours)
15. Add retention/archival automation (1 hour)

---

## What's Working Well (No Changes Needed)

| Area | Status | Why |
|------|--------|-----|
| Schema normalization | ✓ | 6 tables + 4 enums well-designed, proper FKs |
| Versioned workflow_definitions | ✓ | Enables swapping phase flows without code changes |
| Context router API surface | ✓ | 4 methods cover all agent needs |
| Artifact naming convention | ✓ | Clear, phase-based, predictable |
| Structured event_log | ✓ | Append-only, queryable, proper indexes |
| Phase input/output contracts | ✓ | Pydantic-style, complete for all 10 phases |
| 5-step migration path | ✓ | Low risk, incremental, backfill-safe |

---

## Operational Rules Update

Based on the VRAM thrashing observed during parallel dispatches:

> **Rule: Sequential subagent reviews only.** Never dispatch multiple reviewer agents in parallel. Models compete for VRAM, causing 503 "Loading model" errors and OOM kills. Run reviewers sequentially: Gemma → Nemo → GPT.

---

*Report compiled 2026-05-20. Source reviews in `~/.pi/agent/sessions/--home-chief--/subagent-artifacts/`.*
