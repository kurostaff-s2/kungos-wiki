# Super Council 6-Phase Triple Review Report

> **Date:** 2026-05-20
> **Reviewers:** Gemma-4-26B-A4B (architecture), Nemotron-Cascade-2-30B (logic/security), GPT-OSS-20B (diversity)
> **Scope:** 6-phase pipeline model, cohesiveness/integration review strategy, state machine wiring
> **Artifacts:** `working-report-for-super-council.md`, `super-council.py`, `Super-Agent-Council.md`

---

## 1. Verdict Summary

| Reviewer | Model | Verdict | Focus |
|----------|-------|---------|-------|
| **Gemma-4** | Gemma-4-26B-A4B | **PASS** (with structural changes) | Architecture, spec compliance, YAGNI, VRAM |
| **Nemo** | Nemotron-Cascade-2-30B | **FAIL** (3 HIGH, 2 MODERATE, 3 LOW) | Logic correctness, security, edge cases |
| **GPT-OSS** | GPT-OSS-20B | **PARTIAL** (3 HIGH, 3 MODERATE, 6 LOW) | Edge cases, DX, alternatives, i18n, tech debt |

**Combined:** **CONDITIONAL PASS** — architecture sound, but 9 HIGH-severity findings across reviewers must be resolved before production readiness.

---

## 2. Consensus Findings (All Three Agree)

### C1: Cohesiveness Must Be a Dedicated Phase

| Reviewer | Position |
|----------|----------|
| Gemma-4 | ✅ Dedicated phase. "AGENT_VALIDATE is semantic/logic. COHESIVENESS_REVIEW is structural/integration. Separating allows granular error handling." |
| Nemo | ✅ Missing tools (`find_dependents.py`, `check_cohesiveness.py`) must be implemented and wired after BUILD |
| GPT-OSS | ✅ "Extract a dedicated COHESIVENESS_REVIEW phase immediately after BUILD" with mypy/pyright, import-graph, linter, AST duplicate detection, regression baseline |

**Placement (unanimous):** `BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE → HUMAN_GATE → INDEX → DONE`

**What COHESIVENESS_REVIEW does:**
- Static type-checking (mypy/pyright)
- Import-graph analysis (dependency mapping via AST)
- Linting (flake8/ruff)
- Duplicate-function detection via AST
- Regression detection (diff vs. stored baseline indices)

**Why before AGENT_VALIDATE:** Catches integration issues (broken imports, module mismatches) before tests run, preventing misleading test failures.

### C2: Retreat Paths Need Strengthening

| Reviewer | Finding |
|----------|---------|
| Gemma-4 | "BUILD ↔ COHESIVENESS_REVIEW could loop. PipelineState must enforce max_phase_retries and max_global_attempts." |
| Nemo | HIGH: `PipelineState.transition_to` sets FAILED but doesn't force retreat to SCOUT. Can cause BUILD→SCOUT→PLAN→BUILD infinite cycle. |
| GPT-OSS | HIGH: No retreat from HUMAN_GATE to SCOUT. "Conceptual defects could loop permanently." |

**Consensus fix:** Every phase must have a retreat path to SCOUT when retries are exhausted, not just FAILED.

### C3: Reviewer Auto-Dispatch Must Be Wired

| Reviewer | Finding |
|----------|---------|
| Gemma-4 | "If reviewers are async, PipelineState must handle PENDING_REVIEW state" |
| Nemo | HIGH: "Reviewer auto-dispatch not wired — only manual via /v1/council/chain" |
| GPT-OSS | Implicit via DX findings: no status introspection API to track async reviewer state |

**Consensus fix:** Add auto-dispatch hook after AGENT_VALIDATE → HUMAN_GATE transition. Add `PENDING_REVIEW` state to PipelineState.

---

## 3. Unique Recommendations (Each Reviewer's Exclusive Findings)

### Gemma-4 Only (Architecture Lens)

| # | Finding | Why Only Gemma Saw It |
|---|---------|----------------------|
| G1 | **Split-brain architecture risk** — `subagent()` bypasses `/delegate`, so Phase 2 features (worktrees, recall) are unreachable. Recommends Option B (modify pi-subagents) over Option A (standalone endpoint) | Architectural consistency concern — others focused on code-level bugs |
| G2 | **PENDING_REVIEW state needed** — async reviewers create a state machine gap; system assumes "done" while reviewer still processing | State machine completeness — others didn't model async reviewer states |
| G3 | **VRAM swap overhead warning** — any new reviewer role must be evaluated for cycle-time impact | Performance/infrastructure lens — others focused on logic/security |
| G4 | **YAGNI validation** — MigrationManager + PipelineState complexity is justified, not over-engineering | Architectural cost/benefit analysis — unique to architecture review |
| G5 | **AST fragility risk** — `find_dependents.py` must handle dynamic Python patterns to avoid false negatives | Tool reliability concern — others assumed tools would work |

### Nemo Only (Logic/Security Lens)

| # | Finding | Why Only Nemo Saw It |
|---|---------|----------------------|
| N1 | **Path-traversal/symlink risk** — `MigrationManager.migrate_json_to_sqlite` reads from arbitrary `json_dir` without canonical-path validation | Security-specific concern — others didn't check file I/O paths |
| N2 | **Unvalidated tool names in `_delegate`** — malicious callers could inject unknown tool names | Injection attack vector — unique to security review |
| N3 | **Recall-then-validate stale worktree** — if worktree creation fails, recalled solution assumed valid without validation | Race condition in delegation flow — others missed the worktree failure path |
| N4 | **Slot-lock race during crash** — partial slot writes could be read by subsequent delegations | Concurrency/crash-recovery — unique to logic review |
| N5 | **Phase naming inconsistency** — code uses `GATE`, design uses `HUMAN_GATE` | Code/design alignment — others didn't check naming consistency |

### GPT-OSS Only (Diversity Lens)

| # | Finding | Why Only GPT Saw It |
|---|---------|----------------------|
| D1 | **INDEX silently swallows failures** — INDEX→[DONE, FAILED] could transition to DONE on failure | Edge case in state transitions — others focused on BUILD/VALIDATE |
| D2 | **Global attempt ceiling of 10 too restrictive** — hard-coded; should be per-phase parameterized | Configuration flexibility — others didn't question the number |
| D3 | **No diff-check before BUILD** — "no-op" builds waste cycles; should short-circuit | Efficiency optimization — others assumed BUILD always produces changes |
| D4 | **No human-gate timeout** — stalled human blocks entire pipeline | User-behavior edge case — others assumed humans respond |
| D5 | **Unicode normalization gap** — non-ASCII spec titles could break `active_recall()` | Internationalization — unique to diversity review |
| D6 | **No back-pressure/async queueing** — phase transitions block until subagent completes | Concurrency pattern — others didn't model queue depth |
| D7 | **Failed diffs discarded** — no debugging artifact preserved when phase fails | Developer experience — others focused on pipeline correctness, not debugging |
| D8 | **No status introspection API** — only POST endpoints, no GET for phase status | DX/API design — others didn't consider developer workflow |
| D9 | **Stale file-lock watchdog needed** — `fcntl.flock` deadlocks if worker dies | Lock management edge case — others noted locks but not stale scenarios |

---

## 4. Complete Finding Matrix

| # | Severity | Finding | Gemma | Nemo | GPT | Owner |
|---|----------|---------|-------|------|-----|-------|
| 1 | HIGH | Reviewer auto-dispatch not wired | ⚠️ | ✅ | ⚠️ | Nemo |
| 2 | HIGH | Infinite loop in `transition_to` (no retreat) | ⚠️ | ✅ | ✅ | Nemo+GPT |
| 3 | HIGH | Path-traversal in `MigrationManager` | — | ✅ | — | Nemo |
| 4 | HIGH | BUILD loops without progress (no diff-check) | — | — | ✅ | GPT |
| 5 | HIGH | INDEX failure → DONE (not FAILED) | — | — | ✅ | GPT |
| 6 | HIGH | No retreat from HUMAN_GATE to SCOUT | — | — | ✅ | GPT |
| 7 | MODERATE | Unvalidated tool names in `_delegate` | — | ✅ | — | Nemo |
| 8 | MODERATE | Recall-then-validate stale worktree | — | ✅ | — | Nemo |
| 9 | MODERATE | Global attempt ceiling too restrictive | — | — | ✅ | GPT |
| 10 | MODERATE | Cohesiveness embedded in AGENT_VALIDATE | ✅ | ✅ | ✅ | All |
| 11 | MODERATE | Unicode normalization in recall | — | — | ✅ | GPT |
| 12 | MODERATE | Split-brain: subagent() bypasses /delegate | ✅ | — | — | Gemma |
| 13 | LOW | Missing cohesiveness tools | — | ✅ | ✅ | Nemo+GPT |
| 14 | LOW | Phase naming inconsistency (GATE vs HUMAN_GATE) | — | ✅ | — | Nemo |
| 15 | LOW | Slot-lock race during crash | — | ✅ | — | Nemo |
| 16 | LOW | No human-gate timeout | — | — | ✅ | GPT |
| 17 | LOW | No status introspection API | — | — | ✅ | GPT |
| 18 | LOW | Failed diffs discarded | — | — | ✅ | GPT |
| 19 | LOW | No back-pressure/async queueing | — | — | ✅ | GPT |
| 20 | LOW | Stale file-lock watchdog | — | — | ✅ | GPT |
| 21 | WARNING | VRAM swap latency | ✅ | — | — | Gemma |
| 22 | INFO | AST fragility in find_dependents | ✅ | — | — | Gemma |
| 23 | INFO | PENDING_REVIEW state needed | ✅ | — | ⚠️ | Gemma |

---

## 5. State Machine: Current vs. Proposed

### Current (from working-report)

```
SCOUT   → [PLAN, FAILED]
PLAN    → [BUILD, SCOUT, FAILED]
BUILD   → [AGENT_VALIDATE, SCOUT, FAILED]
AGENT_VALIDATE → [HUMAN_GATE, BUILD, FAILED]
HUMAN_GATE → [INDEX, PLAN, BUILD, FAILED]
INDEX   → [DONE, FAILED]
DONE    → []
FAILED  → [SCOUT, DONE]
```

### Issues Identified

| Issue | Source | Fix |
|-------|--------|-----|
| No COHESIVENESS_REVIEW phase | All three | Insert between BUILD and AGENT_VALIDATE |
| No retreat from HUMAN_GATE to SCOUT | GPT | Add SCOUT to HUMAN_GATE transitions |
| INDEX failure → DONE ambiguity | GPT | Explicit: INDEX success→DONE, failure→FAILED |
| No PENDING_REVIEW state | Gemma | Add for async reviewer dispatch |
| No diff-check before AGENT_VALIDATE | GPT | Short-circuit if BUILD produces no changes |
| No timeout on HUMAN_GATE | GPT | Add timeout → retreat to SCOUT or FAILED |

### Proposed (Consensus)

```
SCOUT               → [PLAN, FAILED]
PLAN                → [BUILD, SCOUT, FAILED]
BUILD               → [COHESIVENESS_REVIEW, SCOUT, FAILED]
                    └─ diff-check: if no changes → COHESIVENESS_REVIEW (skip validate)
COHESIVENESS_REVIEW → [AGENT_VALIDATE, BUILD, SCOUT, FAILED]
                    └─ tools: mypy, import-graph, linter, AST duplicate, regression baseline
AGENT_VALIDATE      → [HUMAN_GATE, COHESIVENESS_REVIEW, BUILD, SCOUT, FAILED]
                    └─ auto-dispatch: enqueue reviewer → PENDING_REVIEW state
PENDING_REVIEW      → [HUMAN_GATE, AGENT_VALIDATE, FAILED]
                    └─ async: blocks HUMAN_GATE until reviewer completes or timeout
HUMAN_GATE          → [INDEX, SCOUT, PLAN, BUILD, FAILED]
                    └─ NEW: SCOUT retreat for conceptual defects
                    └─ timeout: if no response → SCOUT or FAILED
INDEX               → [DONE, FAILED]
                    └─ explicit: success→DONE, failure→FAILED (not ambiguous)
DONE                → []
FAILED              → [SCOUT, DONE]
```

### Transition Rules

| Rule | Enforced By | Details |
|------|-------------|---------|
| **Phase ordering** | `ChairGateState.PHASE_ORDER` | RED→GREEN→REFACTOR (TDD); SCOUT→PLAN→BUILD→... (pipeline) |
| **Per-phase retry limit** | `PipelineState.max_phase_retries` | Default 3; on exhaustion → retreat to SCOUT (not FAILED) |
| **Global attempt ceiling** | `PipelineState.max_global_attempts` | Parameterized (default 10); per-phase overrides allowed |
| **Diff-check gate** | BUILD output | If `git diff --stat` = 0 files → skip to COHESIVENESS_REVIEW |
| **Auto-dispatch** | AGENT_VALIDATE → PENDING_REVIEW | Enqueue reviewer task; block HUMAN_GATE until completion or timeout |
| **HUMAN_GATE timeout** | Configurable (default 30min) | On timeout → retreat to SCOUT (not FAILED) |
| **INDEX explicit** | INDEX output | Success → DONE; failure → FAILED with error logged |

---

## 6. Implementation Priority

### P0 (Block Release) — 6 items

| # | Finding | Effort | Reviewer |
|---|---------|--------|----------|
| 1 | Fix infinite-loop in `transition_to` (force retreat to SCOUT) | Small | Nemo+GPT |
| 2 | Wire reviewer auto-dispatch after AGENT_VALIDATE | Medium | Nemo |
| 3 | Patch path-traversal in `MigrationManager` | Small | Nemo |
| 4 | Add diff-check before BUILD (short-circuit no-op) | Small | GPT |
| 5 | Fix INDEX failure → FAILED (not DONE) | Small | GPT |
| 6 | Add HUMAN_GATE retreat to SCOUT | Small | GPT |

### P1 (Next Sprint) — 5 items

| # | Finding | Effort | Reviewer |
|---|---------|--------|----------|
| 7 | Implement cohesiveness tools (`find_dependents.py`, `check_cohesiveness.py`) | Medium | Nemo+GPT |
| 8 | Add `PENDING_REVIEW` state to PipelineState | Small | Gemma |
| 9 | Parameterize global attempt ceiling | Small | GPT |
| 10 | Validate tool names against registry | Small | Nemo |
| 11 | Fix recall-then-validate worktree failure path | Small | Nemo |

### P2 (Backlog) — 8 items

| # | Finding | Effort | Reviewer |
|---|---------|--------|----------|
| 12 | Add HUMAN_GATE timeout | Small | GPT |
| 13 | Add status introspection API (GET `/v1/council/pipeline/<id>`) | Medium | GPT |
| 14 | Preserve failed diffs as debugging artifacts | Small | GPT |
| 15 | Unicode normalization in `active_recall()` | Small | GPT |
| 16 | Phase naming alignment (GATE → HUMAN_GATE) | Small | Nemo |
| 17 | Slot-lock crash-recovery test | Small | Nemo |
| 18 | Back-pressure/async queueing for phase transitions | Medium | GPT |
| 19 | Stale file-lock watchdog | Small | GPT |

---

## 7. How This All Wires Into the State Machine

### Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    SUPER-COUNCIL STATE MACHINE                   │
│                                                                  │
│  PipelineState (state machine)                                  │
│  ├── phase: SCOUT|PLAN|BUILD|COHESIVENESS|VALIDATE|REVIEW|GATE  │
│  │                     |INDEX|DONE|FAILED                       │
│  ├── valid_transitions: Dict[Phase, List[Phase]]               │
│  ├── phase_attempts: Dict[Phase, int]                           │
│  ├── max_phase_retries: int (default 3)                         │
│  ├── max_global_attempts: int (default 10, parameterized)       │
│  └── retreat_on_exhaustion: SCOUT (not FAILED)                  │
│                                                                  │
│  ChairGateState (TDD gate per task)                             │
│  ├── phase: RED|GREEN|REFACTOR                                  │
│  ├── repair_count: int                                          │
│  ├── failure_signatures: List[str]                              │
│  ├── patch_hashes: List[str]                                    │
│  └── semantic_patch_hashes: List[str]                           │
│                                                                  │
│  PipelineTracker (SQLite persistence)                           │
│  ├── pipelines table (pipeline_id, project_id, phase, status)   │
│  └── translations table (task_id → pipeline_id)                 │
│                                                                  │
│  ─── Phase Execution (wired to super-council.py) ───           │
│                                                                  │
│  SCOUT        → _active_recall() + workspace analysis            │
│  PLAN         → Chair writes plan → reviewer-logic reviews       │
│  BUILD        → subagent(council-builder) with TDD gates         │
│  │            → diff-check: git diff --stat                     │
│  │            → if 0 files → skip to COHESIVENESS_REVIEW        │
│  COHESIVENESS → find_dependents.py → check_cohesiveness.py       │
│  │            → tools: mypy, import-graph, linter, AST          │
│  │            → on failure → BUILD (fix structure)              │
│  AGENT_VALID  → _chair_gate() (5-step validation)               │
│  │            → auto-dispatch → PENDING_REVIEW                  │
│  PENDING      → async reviewer completes or timeout              │
│  │            → on timeout → retreat to SCOUT                   │
│  HUMAN_GATE   → POST /v1/council/chair-gate                     │
│  │            → timeout: 30min default                          │
│  │            → on failure → SCOUT (conceptual) or FAILED       │
│  INDEX        → _auto_index_file() (memsearch)                  │
│  │            → success → DONE                                  │
│  │            → failure → FAILED (explicit, not DONE)           │
│  DONE         → terminal                                        │
│  FAILED       → retreat to SCOUT or terminal (DONE)             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Wiring Checklist

- [ ] **PipelineState class** — add `COHESIVENESS_REVIEW`, `PENDING_REVIEW` phases
- [ ] **VALID_TRANSITIONS map** — update with proposed transitions (Section 5)
- [ ] **transition_to()** — force retreat to SCOUT on retry exhaustion (not FAILED)
- [ ] **BUILD phase** — add diff-check (`git diff --stat`) before advancing
- [ ] **COHESIVENESS_REVIEW phase** — implement `find_dependents.py` + `check_cohesiveness.py`
- [ ] **AGENT_VALIDATE phase** — add auto-dispatch hook → PENDING_REVIEW
- [ ] **PENDING_REVIEW phase** — async reviewer with timeout → HUMAN_GATE or SCOUT
- [ ] **HUMAN_GATE phase** — add SCOUT retreat + timeout handling
- [ ] **INDEX phase** — explicit success→DONE / failure→FAILED
- [ ] **MigrationManager** — add canonical-path validation (path-traversal fix)
- [ ] **_delegate()** — validate tool names against registry
- [ ] **recall-then-validate** — abort on worktree creation failure
- [ ] **Global attempt ceiling** — parameterize (env var or config)
- [ ] **Phase naming** — align GATE → HUMAN_GATE throughout codebase

---

## 8. Appendix: Review Source Files

| Review | File | Model |
|--------|------|-------|
| Gemma-4 (Architecture) | `subagent-artifacts/50acf081_council-reviewer-arch_0_output.md` | Gemma-4-26B-A4B |
| Nemo (Logic/Security) | `subagent-artifacts/293ce3fb_council-reviewer-logic_0_output.md` | Nemotron-Cascade-2-30B |
| GPT-OSS (Diversity) | `subagent-artifacts/4e1988a6_council-reviewer-diversity_0_output.md` | GPT-OSS-20B |

---

*Report compiled 2026-05-20. Supersedes individual review outputs. Action items tracked in working-report-for-super-council.md.*
