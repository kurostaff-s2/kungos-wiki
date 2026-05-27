# Full Relational State Machine: Persistence + Observability Platform

> **Date:** 2026-05-20
> **Scope:** Replace JSON-blob persistence with normalized SQLite schema + observability infrastructure
> **Current State:** `pipelines.db` has 2 tables (`pipelines`, `translations`) with `state_json` blob
> **Goal:** Normalized schema, append-only event log, queryable context router, automated state linter

---

## 1. Executive Summary

The Super-Agent Council's core intention is a **state machine + observability platform + context service** (Super-Agent-Council.md §3.1, Pipeline Orchestrator.txt §A2, Triple Review §7). Currently we have:

- **PipelineState** — 10-phase state machine with `VALID_TRANSITIONS`, retry/retreat logic
- **Persistence** — JSON files (`~/.council-memory/pipelines/{id}.json`) + thin SQLite wrapper (`pipelines.db`) where the entire state is dumped as `state_json` blob
- **Context** — `_active_recall()` queries memsearch vector store (separate from pipeline state)
- **History** — `ps.history` list of dicts inside the JSON blob

**Problem:** Nothing is queryable. You can't ask "what happened in the last 3 transitions for run X?" or "show all artifacts for file Y" because everything is bundled into a single JSON blob.

**Solution:** Normalize the schema into proper tables with FKs, enums, indexes. Add append-only event_log, normalized artifacts, and a context router service.

---

## 2. Current Architecture (As-Is)

```
┌──────────────────────────────────────────────────────────────┐
│                    SUPER-COUNCIL (Current)                    │
│                                                              │
│  PipelineState (in-memory class)                             │
│  ├── phase: "SCOUT" | "PLAN" | "BUILD" | ...                 │
│  ├── phase_attempts: {"BUILD": 2, "PLAN": 1}                 │
│  ├── global_attempts: 5                                      │
│  ├── history: [{from: "PLAN", to: "BUILD", ...}, ...]       │
│  ├── artifacts: {"PLAN": "/path/to/plan.md", ...}           │
│  └── save() → JSON file + SQLite blob                       │
│                                                              │
│  pipelines.db (SQLite)                                       │
│  ├── pipelines (8 cols, state_json = full dict as TEXT)     │
│  └── translations (4 cols)                                   │
│                                                              │
│  Context: _active_recall() → memsearch (Milvus vector DB)   │
│  └── Separate from pipeline state — no query integration    │
└──────────────────────────────────────────────────────────────┘
```

**What's broken:**
- `state_json` blob: entire PipelineState dict serialized as TEXT — can't query individual fields
- `ps.history`: append-only list inside JSON — no SQL queries, no filtering
- `ps.artifacts`: flat dict — no schema_version, no kind, no produced_by/consumed_by
- No event_log table — transitions only in `ps.history` blob
- No normalized state_executions — retry counts only in `phase_attempts` blob
- No context router — agents get raw prompt strings, not queryable context

---

## 3. Target Architecture (To-Be)

```
┌──────────────────────────────────────────────────────────────┐
│              SUPER-COUNCIL (Target)                           │
│                                                              │
│  pipelines.db (SQLite — normalized)                          │
│  ├── workflow_definitions (versioned state-machine schemas) │
│  ├── workflow_runs (run-level: status, timestamps, config)  │
│  ├── state_executions (per-run, per-state: retries, duration)│
│  ├── artifacts (normalized: kind, schema_version, content)  │
│  ├── event_log (append-only: transitions, tools, errors)    │
│  └── indexes (composite on run+state, artifact+kind, etc.)  │
│                                                              │
│  Context Router Service (thin Python layer)                  │
│  ├── get_run_snapshot(run_id) → run + states + artifacts    │
│  ├── get_recent_events(run_id, limit) → last N events       │
│  ├── get_artifacts(run_id, filter) → filtered artifacts     │
│  ├── summarize_run_issues(run_id) → structured summary      │
│  └── find_similar_runs(query) → semantic match via memsearch│
│                                                              │
│  Automated State Linter (validation service)                 │
│  ├── lint_workflow(definition) → unreachable states, etc.   │
│  ├── lint_run(run_id) → "what went wrong?"                  │
│  └── propose_transition(run_id, target) → safe?             │
│                                                              │
│  Phase Schema Validation (at boundaries)                     │
│  ├── validate_input(phase, data) → pass/fail                │
│  ├── validate_output(phase, data) → pass/fail               │
│  └── schema_version tracking per artifact                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Relational Schema (DDL)

### 4.1 Enum Types (SQLite via lookup tables)

SQLite doesn't support `CREATE TYPE ... AS ENUM`. We use lookup tables + CHECK constraints:

```sql
-- Phase names (matches PipelineState.ALL_PHASES)
CREATE TABLE IF NOT EXISTS phase_names (
    name TEXT PRIMARY KEY CHECK(
        name IN ('SCOUT', 'PLAN', 'BUILD', 'COHESIVENESS_REVIEW',
                 'AGENT_VALIDATE', 'PENDING_REVIEW', 'HUMAN_GATE',
                 'INDEX', 'DONE', 'FAILED')
    )
);
INSERT OR IGNORE INTO phase_names VALUES
    ('SCOUT'), ('PLAN'), ('BUILD'), ('COHESIVENESS_REVIEW'),
    ('AGENT_VALIDATE'), ('PENDING_REVIEW'), ('HUMAN_GATE'),
    ('INDEX'), ('DONE'), ('FAILED');

-- Run statuses
CREATE TABLE IF NOT EXISTS run_statuses (
    name TEXT PRIMARY KEY CHECK(
        name IN ('running', 'done', 'failed', 'retreated', 'timeout')
    )
);
INSERT OR IGNORE INTO run_statuses VALUES
    ('running'), ('done'), ('failed'), ('retreated'), ('timeout');

-- Event severity levels
CREATE TABLE IF NOT EXISTS event_severities (
    name TEXT PRIMARY KEY CHECK(
        name IN ('info', 'warning', 'error', 'critical')
    )
);
INSERT OR IGNORE INTO event_severities VALUES
    ('info'), ('warning'), ('error'), ('critical');

-- Artifact kinds
CREATE TABLE IF NOT EXISTS artifact_kinds (
    name TEXT PRIMARY KEY CHECK(
        name IN ('plan', 'build_output', 'review_report', 'test_result',
                 'diff', 'spec_contract', 'verification_criteria',
                 'cohesiveness_report', 'gate_result', 'index_manifest',
                 'recall_context', 'error_log')
    )
);
INSERT OR IGNORE INTO artifact_kinds VALUES
    ('plan'), ('build_output'), ('review_report'), ('test_result'),
    ('diff'), ('spec_contract'), ('verification_criteria'),
    ('cohesiveness_report'), ('gate_result'), ('index_manifest'),
    ('recall_context'), ('error_log');
```

### 4.2 Core Tables

```sql
-- ─── Workflow Definitions (versioned state-machine schemas) ───
CREATE TABLE IF NOT EXISTS workflow_definitions (
    definition_id TEXT PRIMARY KEY,       -- e.g., "default-v1", "tdd-v2"
    name TEXT NOT NULL,                   -- e.g., "default", "tdd"
    version INTEGER NOT NULL DEFAULT 1,
    phases JSON TEXT NOT NULL,            -- ordered phase list
    transitions JSON TEXT NOT NULL,       -- VALID_TRANSITIONS map
    max_phase_retries INTEGER NOT NULL DEFAULT 3,
    max_global_attempts INTEGER NOT NULL DEFAULT 10,
    human_gate_timeout REAL NOT NULL DEFAULT 1800.0,
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    UNIQUE(name, version)
);

-- Seed the default definition (matches current VALID_TRANSITIONS)
INSERT OR IGNORE INTO workflow_definitions
    (definition_id, name, version, phases, transitions, max_phase_retries, max_global_attempts)
VALUES ('default-v1', 'default', 1,
    '["SCOUT","PLAN","BUILD","COHESIVENESS_REVIEW","AGENT_VALIDATE","PENDING_REVIEW","HUMAN_GATE","INDEX","DONE","FAILED"]',
    '{"SCOUT":["PLAN","FAILED"],"PLAN":["BUILD","SCOUT","FAILED"],"BUILD":["COHESIVENESS_REVIEW","SCOUT","FAILED"],
     "COHESIVENESS_REVIEW":["AGENT_VALIDATE","BUILD","SCOUT","FAILED"],
     "AGENT_VALIDATE":["PENDING_REVIEW","COHESIVENESS_REVIEW","BUILD","SCOUT","FAILED"],
     "PENDING_REVIEW":["HUMAN_GATE","AGENT_VALIDATE","FAILED"],
     "HUMAN_GATE":["INDEX","SCOUT","PLAN","BUILD","FAILED"],
     "INDEX":["DONE","FAILED"],"DONE":[],"FAILED":["SCOUT","DONE"]}',
    3, 10
);

-- ─── Workflow Runs (run-level state) ───
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,              -- pipeline_id (UUID)
    workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(definition_id),
    project_id TEXT NOT NULL DEFAULT 'default',
    task TEXT NOT NULL,
    current_phase TEXT NOT NULL REFERENCES phase_names(name),
    status TEXT NOT NULL DEFAULT 'running' REFERENCES run_statuses(name),
    global_attempts INTEGER NOT NULL DEFAULT 0,
    retreat_target TEXT NOT NULL DEFAULT 'SCOUT' REFERENCES phase_names(name),
    started_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    completed_at REAL,
    metadata JSON TEXT,                   -- arbitrary run-level metadata
    UNIQUE(run_id)
);

-- ─── State Executions (per-run, per-state: retries, duration, outcome) ───
CREATE TABLE IF NOT EXISTS state_executions (
    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    phase TEXT NOT NULL REFERENCES phase_names(name),
    attempt_number INTEGER NOT NULL,      -- 1, 2, 3 for retries within this phase
    outcome TEXT NOT NULL CHECK(outcome IN ('success', 'failure', 'retreat', 'timeout', 'global_ceiling')),
    duration_ms REAL,
    error TEXT,
    started_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    completed_at REAL,
    artifact_id INTEGER REFERENCES artifacts(artifact_id),  -- primary artifact from this execution
    UNIQUE(run_id, phase, attempt_number)
);

-- ─── Normalized Artifacts (produced/consumed by states and agents) ───
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    phase TEXT NOT NULL REFERENCES phase_names(name),
    kind TEXT NOT NULL REFERENCES artifact_kinds(name),
    schema_version INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,                   -- e.g., "plan.md", "build.diff", "review.json"
    content TEXT,                         -- inline content (for small artifacts)
    content_path TEXT,                    -- file path (for large artifacts)
    content_hash TEXT,                    -- SHA-256 of content for dedup
    produced_by TEXT,                     -- agent alias that produced this (e.g., "council-builder")
    metadata JSON TEXT,                   -- arbitrary artifact metadata
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);

-- ─── Append-Only Event Log (transitions, tool calls, decisions, errors) ───
CREATE TABLE IF NOT EXISTS event_log (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    timestamp REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    event_type TEXT NOT NULL CHECK(
        event_type IN ('phase_transition', 'phase_start', 'phase_end',
                       'tool_call', 'tool_result', 'error', 'warning',
                       'delegation_start', 'delegation_end', 'recall_hit',
                       'gate_check', 'gate_pass', 'gate_fail',
                       'retreat', 'human_gate_wait', 'human_gate_timeout',
                       'index_start', 'index_end', 'swap_start', 'swap_end')
    ),
    from_phase TEXT REFERENCES phase_names(name),
    to_phase TEXT REFERENCES phase_names(name),
    tool_name TEXT,                       -- e.g., "read", "edit", "bash", "delegate"
    inputs_summary TEXT,                  -- truncated input summary (≤500 chars)
    outputs_refs TEXT,                    -- artifact_id(s) or file refs
    duration_ms REAL,
    error TEXT,
    severity TEXT NOT NULL DEFAULT 'info' REFERENCES event_severities(name),
    agent_alias TEXT,                     -- which agent performed this action
    metadata JSON TEXT                    -- arbitrary event metadata
);

-- ─── Artifact Dependencies (consumed_by relationships) ───
CREATE TABLE IF NOT EXISTS artifact_dependencies (
    consumer_artifact_id INTEGER NOT NULL REFERENCES artifacts(artifact_id),
    producer_artifact_id INTEGER NOT NULL REFERENCES artifacts(artifact_id),
    PRIMARY KEY (consumer_artifact_id, producer_artifact_id)
);
```

### 4.3 Indexes

```sql
-- Run snapshot queries
CREATE INDEX IF NOT EXISTS idx_runs_project_status ON workflow_runs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON workflow_runs(started_at DESC);

-- State execution queries
CREATE INDEX IF NOT EXISTS idx_executions_run_phase ON state_executions(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_executions_run_outcome ON state_executions(run_id, outcome);
CREATE INDEX IF NOT EXISTS idx_executions_phase_outcome ON state_executions(phase, outcome);

-- Artifact queries
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_phase ON artifacts(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(kind);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind_run ON artifacts(kind, run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(content_hash);

-- Event log queries (the most critical)
CREATE INDEX IF NOT EXISTS idx_events_run ON event_log(run_id);
CREATE INDEX IF NOT EXISTS idx_events_run_time ON event_log(run_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_events_run_type ON event_log(run_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity ON event_log(severity);
CREATE INDEX IF NOT EXISTS idx_events_run_severity ON event_log(run_id, severity);

-- Workflow definition queries
CREATE INDEX IF NOT EXISTS idx_workflow_name_version ON workflow_definitions(name, version);
```

### 4.4 Partitioning / Retention Strategy

SQLite doesn't support table partitioning. For high-volume usage:

```sql
-- Retention: archive old runs older than N days
-- Strategy: move completed runs to archive tables periodically

CREATE TABLE IF NOT EXISTS event_log_archive AS SELECT * FROM event_log WHERE 0;
CREATE TABLE IF NOT EXISTS state_executions_archive AS SELECT * FROM state_executions WHERE 0;
CREATE TABLE IF NOT EXISTS artifacts_archive AS SELECT * FROM artifacts WHERE 0;

-- Retention policy (run via cron or scheduled task):
-- 1. Identify runs older than retention_days (e.g., 90 days)
-- 2. Move their events/executions/artifacts to archive tables
-- 3. DELETE from main tables
-- 4. VACUUM to reclaim space

-- Example retention query:
-- INSERT INTO event_log_archive
-- SELECT * FROM event_log
-- WHERE run_id IN (
--     SELECT run_id FROM workflow_runs
--     WHERE status IN ('done', 'failed')
--     AND completed_at < strftime('%s', 'now', '-90 days')
-- );
-- DELETE FROM event_log WHERE run_id IN (...);
```

---

## 5. Example Queries & Materialized Views

### 5.1 Run Snapshot (states with statuses and timestamps)

```sql
-- Complete snapshot of a run: current state + all phase executions
SELECT
    wr.run_id,
    wr.task,
    wr.current_phase,
    wr.status,
    wr.global_attempts,
    wr.started_at,
    wr.completed_at,
    se.phase AS executed_phase,
    se.attempt_number,
    se.outcome,
    se.duration_ms,
    se.error,
    a.name AS artifact_name,
    a.kind AS artifact_kind,
    a.produced_by
FROM workflow_runs wr
LEFT JOIN state_executions se ON wr.run_id = se.run_id
LEFT JOIN artifacts a ON se.artifact_id = a.artifact_id
WHERE wr.run_id = ?
ORDER BY se.execution_id;
```

### 5.2 Compact Context View (last N events + artifacts)

```sql
-- Last N events for a run (for agent context injection)
SELECT
    el.event_id,
    el.event_type,
    el.from_phase,
    el.to_phase,
    el.tool_name,
    el.inputs_summary,
    el.outputs_refs,
    el.duration_ms,
    el.error,
    el.severity,
    el.agent_alias,
    strftime('%Y-%m-%d %H:%M:%S', el.timestamp, 'unixepoch') AS human_time
FROM event_log el
WHERE el.run_id = ?
ORDER BY el.timestamp DESC
LIMIT ?;

-- Artifacts for a specific file/path
SELECT
    a.artifact_id,
    a.phase,
    a.kind,
    a.name,
    a.content,
    a.content_path,
    a.produced_by,
    a.schema_version
FROM artifacts a
WHERE a.run_id = ?
AND (a.name LIKE ? OR a.content_path LIKE ?)
ORDER BY a.created_at DESC;
```

### 5.3 Find Similar Past Runs

```sql
-- By tag/project/task similarity
SELECT
    wr.run_id,
    wr.task,
    wr.project_id,
    wr.status,
    wr.current_phase,
    wr.completed_at,
    -- Count of successful phases
    (SELECT COUNT(*) FROM state_executions se
     WHERE se.run_id = wr.run_id AND se.outcome = 'success') AS successful_phases,
    -- Count of failures
    (SELECT COUNT(*) FROM state_executions se
     WHERE se.run_id = wr.run_id AND se.outcome = 'failure') AS failed_phases
FROM workflow_runs wr
WHERE wr.project_id = ?
AND wr.status IN ('done', 'failed')
AND wr.task LIKE ?  -- fuzzy task match
ORDER BY wr.completed_at DESC
LIMIT 10;

-- By artifact kind (e.g., "find runs that produced a plan")
SELECT DISTINCT
    wr.run_id,
    wr.task,
    wr.status,
    a.name,
    a.kind,
    a.produced_by
FROM workflow_runs wr
JOIN artifacts a ON wr.run_id = a.run_id
WHERE a.kind = ?
ORDER BY wr.completed_at DESC
LIMIT 10;
```

### 5.4 Last Successful Execution of State S for Run X

```sql
-- Last successful execution of a specific phase
SELECT
    se.execution_id,
    se.phase,
    se.attempt_number,
    se.duration_ms,
    se.started_at,
    se.completed_at,
    a.name AS artifact_name,
    a.kind AS artifact_kind
FROM state_executions se
LEFT JOIN artifacts a ON se.artifact_id = a.artifact_id
WHERE se.run_id = ?
AND se.phase = ?
AND se.outcome = 'success'
ORDER BY se.execution_id DESC
LIMIT 1;
```

### 5.5 "What Went Wrong?" Diagnostic Query

```sql
-- Structured explanation of failures in a run
SELECT
    se.phase,
    se.attempt_number,
    se.error,
    se.duration_ms,
    el.event_type,
    el.tool_name,
    el.inputs_summary,
    el.severity,
    strftime('%Y-%m-%d %H:%M:%S', el.timestamp, 'unixepoch') AS time
FROM state_executions se
LEFT JOIN event_log el ON (
    el.run_id = se.run_id
    AND el.timestamp BETWEEN se.started_at AND COALESCE(se.completed_at, se.started_at + 1)
    AND el.severity IN ('error', 'critical')
)
WHERE se.run_id = ?
AND se.outcome IN ('failure', 'retreat')
ORDER BY se.execution_id, el.timestamp;
```

---

## 6. Orchestrator Write Path (per transition)

### 6.1 How the Orchestrator Writes on Each Transition

```python
# Pseudocode: what happens on each phase transition

def transition_to(self, new_phase, outcome="success", error="", artifact_path=""):
    """Execute transition with full DB writes."""

    # 1. Record state execution
    attempt = self.phase_attempts.get(self.phase, 0) + (1 if outcome == "failure" else 0)
    self.db.execute("""
        INSERT INTO state_executions
            (run_id, phase, attempt_number, outcome, duration_ms, error, started_at, completed_at, artifact_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        self.pipeline_id,
        self.phase,
        attempt,
        outcome,
        elapsed_ms,
        error,
        start_time,
        time.time(),
        artifact_id  # if artifact was produced
    ))

    # 2. Record event log entry
    self.db.execute("""
        INSERT INTO event_log
            (run_id, event_type, from_phase, to_phase, duration_ms, error, severity, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        self.pipeline_id,
        "phase_transition",
        self.phase,
        new_phase,
        elapsed_ms,
        error,
        "error" if outcome == "failure" else "info",
        json.dumps({"global_attempt": self.global_attempts})
    ))

    # 3. Record artifact (if produced)
    if artifact_path:
        artifact_id = self._store_artifact(
            run_id=self.pipeline_id,
            phase=self.phase,
            kind=self._infer_artifact_kind(self.phase),
            name=f"{self.phase.lower()}.json",
            content_path=artifact_path,
            produced_by=self.current_alias
        )

    # 4. Update workflow_runs
    self.db.execute("""
        UPDATE workflow_runs
        SET current_phase = ?, status = ?, global_attempts = ?
        WHERE run_id = ?
    """, (new_phase, self.status, self.global_attempts, self.pipeline_id))

    # 5. Handle retreat
    if self.phase_attempts[self.phase] > self.max_phase_retries:
        self.db.execute("""
            INSERT INTO event_log (run_id, event_type, from_phase, to_phase, error, severity)
            VALUES (?, 'retreat', ?, ?, ?, 'warning')
        """, (self.pipeline_id, self.phase, self.retreat_target,
              f"retries exhausted", "warning"))
        self.phase = self.retreat_target

    self.db.commit()
```

### 6.2 How Chair / Co-Chair Context Service Reads

```python
class ContextRouter:
    """Thin service between state machine and agents."""

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row

    def get_run_snapshot(self, run_id: str) -> dict:
        """Complete snapshot of a run for Chair decision-making."""
        run = self.db.execute(
            "SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        executions = self.db.execute(
            "SELECT * FROM state_executions WHERE run_id = ? ORDER BY execution_id",
            (run_id,)
        ).fetchall()
        artifacts = self.db.execute(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at",
            (run_id,)
        ).fetchall()
        return {
            "run": dict(run),
            "executions": [dict(e) for e in executions],
            "artifacts": [dict(a) for a in artifacts],
        }

    def get_recent_events(self, run_id: str, limit: int = 20) -> list:
        """Last N events for a run (for agent context injection)."""
        events = self.db.execute(
            """SELECT * FROM event_log
               WHERE run_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (run_id, limit)
        ).fetchall()
        return [dict(e) for e in events]

    def get_artifacts(self, run_id: str, kind: str = None, phase: str = None) -> list:
        """Filtered artifacts for a run."""
        query = "SELECT * FROM artifacts WHERE run_id = ?"
        params = [run_id]
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        if phase:
            query += " AND phase = ?"
            params.append(phase)
        query += " ORDER BY created_at DESC"
        return [dict(row) for row in self.db.execute(query, params).fetchall()]

    def summarize_run_issues(self, run_id: str) -> dict:
        """Structured summary of failures for Co-Chair analysis."""
        failures = self.db.execute(
            """SELECT se.phase, se.attempt_number, se.error, se.duration_ms,
                      COUNT(el.event_id) AS error_count
               FROM state_executions se
               LEFT JOIN event_log el ON (
                   el.run_id = se.run_id
                   AND el.timestamp BETWEEN se.started_at AND COALESCE(se.completed_at, se.started_at + 1)
                   AND el.severity IN ('error', 'critical')
               )
               WHERE se.run_id = ? AND se.outcome IN ('failure', 'retreat')
               GROUP BY se.phase, se.attempt_number
               ORDER BY se.execution_id""",
            (run_id,)
        ).fetchall()
        return {
            "run_id": run_id,
            "failures": [dict(f) for f in failures],
            "total_failures": len(failures),
        }

    def find_similar_runs(self, project_id: str, task_fragment: str, limit: int = 5) -> list:
        """Find past runs by project and task similarity."""
        runs = self.db.execute(
            """SELECT wr.run_id, wr.task, wr.status, wr.current_phase,
                      wr.completed_at,
                      (SELECT COUNT(*) FROM state_executions se
                       WHERE se.run_id = wr.run_id AND se.outcome = 'success') AS successful_phases
               FROM workflow_runs wr
               WHERE wr.project_id = ?
               AND wr.status IN ('done', 'failed')
               AND wr.task LIKE ?
               ORDER BY wr.completed_at DESC
               LIMIT ?""",
            (project_id, f"%{task_fragment}%", limit)
        ).fetchall()
        return [dict(r) for r in runs]
```

---

## 7. Automated State-Machine Linter

### 7.1 What It Checks

| Check | Description | Severity |
|-------|-------------|----------|
| **Unreachable states** | States with no incoming transitions from any other state | HIGH |
| **Invalid transitions** | Transitions to non-existent states | HIGH |
| **Missing handlers** | States without corresponding `_run_*` methods | HIGH |
| **Non-terminal dead-ends** | Non-terminal states with no outgoing transitions | HIGH |
| **Infinite loops** | Cycles that don't include a terminal state or retry limit | MODERATE |
| **Orphaned transitions** | Transitions from states that aren't in the phase list | MODERATE |
| **Missing retreat paths** | States without a retreat-to-SCOUT or FAILED option | LOW |
| **Asymmetric transitions** | State A→B exists but B→A doesn't (if expected) | INFO |

### 7.2 Implementation

```python
class StateMachineLinter:
    """Automated validation of state-machine definitions."""

    def __init__(self, phases: List[str], transitions: Dict[str, List[str]], handlers: Dict[str, str]):
        self.phases = set(phases)
        self.transitions = transitions
        self.handlers = handlers  # phase -> method name

    def lint(self) -> List[dict]:
        """Run all checks. Returns list of findings."""
        findings = []
        findings.extend(self._check_unreachable())
        findings.extend(self._check_invalid_targets())
        findings.extend(self._check_missing_handlers())
        findings.extend(self._check_dead_ends())
        findings.extend(self._check_infinite_loops())
        findings.extend(self._check_retreat_paths())
        return findings

    def _check_unreachable(self) -> List[dict]:
        """States with no incoming transitions."""
        reachable = set()
        for from_phase, to_phases in self.transitions.items():
            reachable.update(to_phases)
        # SCOUT is always reachable (start state)
        unreachable = self.phases - reachable - {"SCOUT", "DONE", "FAILED"}
        return [
            {"severity": "high", "check": "unreachable", "phase": p,
             "message": f"State {p} has no incoming transitions"}
            for p in unreachable
        ]

    def _check_invalid_targets(self) -> List[dict]:
        """Transitions to non-existent states."""
        findings = []
        for from_phase, to_phases in self.transitions.items():
            for target in to_phases:
                if target not in self.phases:
                    findings.append({
                        "severity": "high", "check": "invalid_target",
                        "transition": f"{from_phase} → {target}",
                        "message": f"Transition targets non-existent state {target}"
                    })
        return findings

    def _check_missing_handlers(self) -> List[dict]:
        """States without corresponding _run_* methods."""
        terminal = {"DONE", "FAILED"}
        findings = []
        for phase in self.phases - terminal:
            handler = self.handlers.get(phase)
            if not handler:
                findings.append({
                    "severity": "high", "check": "missing_handler",
                    "phase": phase,
                    "message": f"State {phase} has no execution handler"
                })
        return findings

    def _check_dead_ends(self) -> List[dict]:
        """Non-terminal states with no outgoing transitions."""
        terminal = {"DONE", "FAILED"}
        findings = []
        for phase in self.phases - terminal:
            if not self.transitions.get(phase):
                findings.append({
                    "severity": "high", "check": "dead_end",
                    "phase": phase,
                    "message": f"Non-terminal state {phase} has no outgoing transitions"
                })
        return findings

    def _check_infinite_loops(self) -> List[dict]:
        """Cycles without terminal state or retry limit."""
        # DFS to find cycles
        cycles = []
        visited = set()

        def dfs(node, path):
            if node in path:
                cycle = path[path.index(node):] + [node]
                if "DONE" not in cycle and "FAILED" not in cycle:
                    cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            for next_phase in self.transitions.get(node, []):
                dfs(next_phase, path[:])
            path.pop()

        for phase in self.phases:
            dfs(phase, [])

        return [
            {"severity": "moderate", "check": "infinite_loop",
             "cycle": " → ".join(c),
             "message": f"Cycle {' → '.join(c)} without terminal state"}
            for c in cycles
        ]

    def _check_retreat_paths(self) -> List[dict]:
        """States without retreat-to-SCOUT or FAILED option."""
        findings = []
        for phase, targets in self.transitions.items():
            if phase in ("DONE", "FAILED"):
                continue
            if "SCOUT" not in targets and "FAILED" not in targets:
                findings.append({
                    "severity": "low", "check": "missing_retreat",
                    "phase": phase,
                    "message": f"State {phase} has no retreat path to SCOUT or FAILED"
                })
        return findings
```

### 7.3 Chair / Co-Chair Tool Interface

```python
# Exposed as tools callable by Chair/Co-Chair agents

def inspect_workflow_graph(workflow_id: str = "default-v1") -> dict:
    """Return the workflow graph as a queryable structure."""
    # Returns phases, transitions, handlers, lint findings
    pass

def explain_last_run(run_id: str) -> str:
    """Structured explanation of what went wrong in the last run."""
    # Uses summarize_run_issues() + event_log analysis
    pass

def propose_safe_transition(run_id: str, target_phase: str) -> dict:
    """Check if a transition is safe and propose it."""
    # Validates against VALID_TRANSITIONS + current state
    pass

def lint_current_workflow() -> List[dict]:
    """Run automated linter on current workflow definition."""
    # Returns list of findings with severity
    pass
```

---

## 8. Standardized Output Files as Shared Context

### 8.1 File Naming Convention

```
~/.council-memory/artifacts/{run_id}/
├── SCOUT/
│   └── recall_context.json          # Active recall results
├── PLAN/
│   ├── plan.md                       # Implementation plan
│   ├── spec_contract.md              # Requirements contract
│   └── verification_criteria.md      # Verification criteria
├── BUILD/
│   ├── build_output.json             # Builder agent output
│   ├── diff.patch                    # Git diff of changes
│   └── test_results.json             # Test outcomes
├── COHESIVENESS_REVIEW/
│   └── cohesiveness_report.json      # Co-chair review output
├── AGENT_VALIDATE/
│   └── gate_result.json              # Chair gate validation
├── PENDING_REVIEW/
│   └── review_report.json            # Reviewer output
├── HUMAN_GATE/
│   └── approval.json                 # Human approval record
├── INDEX/
│   └── index_manifest.json           # Indexing results
└── metadata.json                     # Run-level metadata
```

### 8.2 JSON Schema for Artifact Metadata

```json
{
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "artifact-metadata-v1",
    "type": "object",
    "required": ["run_id", "phase", "kind", "name", "schema_version", "created_at"],
    "properties": {
        "run_id": {"type": "string", "format": "uuid"},
        "phase": {"type": "string", "enum": ["SCOUT", "PLAN", "BUILD", "COHESIVENESS_REVIEW", "AGENT_VALIDATE", "PENDING_REVIEW", "HUMAN_GATE", "INDEX", "DONE", "FAILED"]},
        "kind": {"type": "string", "enum": ["plan", "build_output", "review_report", "test_result", "diff", "spec_contract", "verification_criteria", "cohesiveness_report", "gate_result", "index_manifest", "recall_context", "error_log"]},
        "name": {"type": "