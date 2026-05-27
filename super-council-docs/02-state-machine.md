# State Machine

> Two state machines: `PipelineState` (6-phase pipeline) and `ChairGateState` (TDD gate validation).

## PipelineState (6-Phase Pipeline)

### Phase Flow

```
SCOUT → PLAN → BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE
     → PENDING_REVIEW → HUMAN_GATE → INDEX → DONE | FAILED
```

### Valid Transitions

```python
VALID_TRANSITIONS = {
    SCOUT:               [PLAN, FAILED],
    PLAN:                [BUILD, SCOUT, FAILED],
    BUILD:               [COHESIVENESS_REVIEW, SCOUT, FAILED],
    COHESIVENESS_REVIEW: [AGENT_VALIDATE, BUILD, SCOUT, FAILED],
    AGENT_VALIDATE:      [PENDING_REVIEW, COHESIVENESS_REVIEW, BUILD, SCOUT, FAILED],
    PENDING_REVIEW:      [HUMAN_GATE, AGENT_VALIDATE, FAILED],
    HUMAN_GATE:          [INDEX, SCOUT, PLAN, BUILD, FAILED],
    INDEX:               [DONE, FAILED],
    DONE:                [],       # terminal
    FAILED:              [SCOUT, DONE],  # reprobe or abort
}
```

### Phase Descriptions

| Phase | Executor | Purpose |
|-------|----------|---------|
| **SCOUT** | `_run_scout()` | Active recall + workspace analysis. Queries memsearch for past solutions. |
| **PLAN** | `_run_plan()` | Delegate to planner agent. Creates implementation plan with units, dependencies, verification steps. |
| **BUILD** | `_run_build()` | Delegate to builder agent with TDD gates. Checks git diff before delegating (skips if no changes). |
| **COHESIVENESS_REVIEW** | `_run_cohesiveness_check()` | Co-chair (goal-checker-co-chair) reviews: does built code cohere with plan? Falls back to static analysis (mypy/lint). |
| **AGENT_VALIDATE** | `_run_agent_validate()` | **PRIMARY REVIEW PHASE.** Dispatches reviewer agent via `_resolve_reviewer_alias()`. Auto-selects from: `reviewer-logic` (Nemotron), `reviewer-arch` (Gemma), `reviewer-diversity` (GPT-OSS). Stores reviewer task ID. |
| **PENDING_REVIEW** | `_run_pending_review()` | Returns stored reviewer result. Waits for async review completion. |
| **HUMAN_GATE** | `_run_human_gate()` | Human approval checkpoint. Timeout: 30 min default. |
| **INDEX** | `_run_index()` | Index artifacts into memsearch. Routes failure → FAILED (not DONE). |
| **DONE** | — | Terminal. Pipeline complete. |
| **FAILED** | — | Terminal. Can reprobe (→SCOUT) or abort (→DONE). |

### Reviewer Auto-Dispatch

The `AGENT_VALIDATE` phase automatically selects a reviewer alias based on task context:

| Reviewer | Alias | Model | Focus |
|----------|-------|-------|-------|
| Logic/Security | `reviewer-logic` | Nemotron-Cascade-2-30B | Logic errors, security, correctness |
| Architecture | `reviewer-arch` | Gemma-4-26B-A4B | Architecture, design patterns, spec compliance |
| Diversity | `reviewer-diversity` | GPT-OSS-20B | Edge cases, diverse perspectives, creative solutions |

**Use pipeline for all reviews** — the state machine manages context, retry logic, and artifact persistence. Do NOT bypass the pipeline with direct delegation for reviews.

### Retry & Retreat Logic

```
Per-phase retry limit: 3 (parameterized via max_phase_retries)
Global attempt ceiling: 10 (parameterized via max_global_attempts or COUNCIL_MAX_GLOBAL_ATTEMPTS env var)
Retreat target: SCOUT (default when retries exhausted)
```

**Flow on failure:**
1. Phase fails → `transition_to(phase, outcome="failure", error=...)`
2. `phase_attempts[phase]` increments
3. If `> max_phase_retries` → **retreat to SCOUT** (reset phase_attempts)
4. `global_attempts` increments on every phase entry (including retreats)
5. If `> max_global_attempts` → **FAILED** (terminal)

### Transition Recording (Atomic)

Every transition writes to RelationalStore:
- `state_executions` — phase, attempt_number, outcome, error, duration_ms
- `artifacts` — phase, key, content (from artifact_path)
- `event_log` — event_type, severity, message, occurred_at
- `workflow_runs` — phase, status (updated)

**HIGH-1 fix:** IntegrityError on transition → in-memory state NOT advanced (no split-brain).

**HIGH-2 fix:** `attempt_number` from DB-primary `_next_attempt()` (not in-memory counter).

### Schema Validation (Unit 5)

Each phase has input/output contracts:

```python
PHASE_SCHEMAS = {
    "SCOUT": {"input": {}, "output": {"recall": list, "query": str}},
    "PLAN": {"input": {"SCOUT": dict}, "output": {"ok": (bool, str)}},
    "BUILD": {"input": {"PLAN": dict}, "output": {"ok": (bool, str)}},
    # ... etc
}
```

Validation is **non-blocking** (logs warnings, doesn't stop execution). Defensive, not stop-the-line.

### Persistence

- State serialized to `~/.council-memory/pipelines/{pipeline_id}.json`
- `PipelineState.from_file(pipeline_id)` loads existing or creates new
- `save()` called on every transition

## ChairGateState (TDD Gate Validation)

### Phase Ordering

```
RED → GREEN → REFACTOR
```

### 5-Step Gate

1. **Phase ordering** — Cannot regress (GREEN → RED blocked)
2. **Tool audit** — Only allowed tools for phase
3. **Git-diff constraints** — Changes must match allowed paths
4. **Failure-signature/no-op detection** — Same error or identical patch → escalate
5. **Test outcome** — RED must fail, GREEN/REFACTOR must pass

### Repair Loop

```python
should_continue_repair(failure_output, diff) -> {ok, reason, escalate}
```

**Escalation triggers:**
- `repair_count >= max_repairs` (default 3)
- Repeated failure signature (same error pattern)
- No-op patch (identical `canonical_diff_hash`)
- Semantic-equivalent patch (same behavior, different syntax)

### Persistence

- State serialized to `~/.council-memory/phase-state/{task_id}.json`
- Fields: `phase`, `repair_count`, `failure_signatures`, `patch_hashes`, `semantic_patch_hashes`
- `save()` called on every `record_repair_attempt()` and `advance_phase()`

## StateMachineLinter

### 8 Checks

| Check | Severity | Description |
|-------|----------|-------------|
| `unreachable_states` | CRITICAL | Phase with no incoming transitions |
| `invalid_targets` | CRITICAL | Transition targets non-existent phase |
| `missing_handlers` | HIGH | Phase without `_run_*()` method |
| `dead_ends` | HIGH | Non-terminal phase with no outgoing transitions |
| `infinite_loops` | MODERATE | Cycles in transition graph |
| `orphaned_transitions` | MODERATE | Transition from phase not in `ALL_PHASES` |
| `retreat_paths` | LOW | Verify retreat paths to SCOUT exist |
| `asymmetric_transitions` | LOW | A→B exists but B→A doesn't |

### Usage

```python
from super_council.state_linter import StateMachineLinter
from super_council.super_council import PipelineState

linter = StateMachineLinter(
    phases=list(PipelineState.ALL_PHASES),
    transitions=dict(PipelineState.VALID_TRANSITIONS),
    terminal_phases=set(PipelineState.TERMINAL_PHASES),
)
findings = linter.lint()
for f in findings:
    print(f"[{f['severity']}] {f['check']}: {f['message']}")
```

**Expected findings:** 7 MODERATE (retreat cycles), 20+ LOW (asymmetric). 0 CRITICAL, 0 HIGH.
