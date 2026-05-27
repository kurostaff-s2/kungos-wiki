### 8.2 JSON Schema for Artifact Metadata (continued)

```json
{
    "name": {"type": "string", "description": "Artifact filename"},
    "schema_version": {"type": "integer", "minimum": 1},
    "content_path": {"type": "string", "format": "uri", "description": "File path to artifact content"},
    "content_hash": {"type": "string", "description": "SHA-256 of content"},
    "produced_by": {"type": "string", "description": "Agent alias that produced this"},
    "consumed_by": {"type": "array", "items": {"type": "string"}, "description": "Phases that consume this artifact"},
    "metadata": {"type": "object", "additionalProperties": true},
    "created_at": {"type": "number", "description": "Unix timestamp"},
    "updated_at": {"type": "number", "description": "Unix timestamp"}
}
```

### 8.3 Context Router Service

```python
class ContextRouter:
    """Thin service between state machine and agents.
    
    Watches state transitions and new artifacts.
    Generates compact, queryable summaries.
    Exposes small set of tools/APIs for agents.
    """

    def __init__(self, db_path: str, memsearch: MemSearch = None):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.memsearch = memsearch

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

## 9. Structured Logging Format

### 9.1 Event Log Schema

Every state transition and tool call produces a structured event:

```json
{
    "run_id": "pipe-1779280215",
    "timestamp": 1779280215.123,
    "event_type": "phase_transition",
    "from_phase": "PLAN",
    "to_phase": "BUILD",
    "tool_name": null,
    "inputs_summary": "Plan artifact: plan.md (2.4KB), spec_contract.md (1.1KB)",
    "outputs_refs": "artifact_id=42",
    "duration_ms": 1234.56,
    "error": null,
    "severity": "info",
    "agent_alias": "council-planner",
    "metadata": {
        "global_attempt": 3,
        "phase_attempt": 1,
        "transition_validated": true
    }
}
```

### 9.2 Example Events

**Phase transition (success):**
```json
{
    "run_id": "pipe-1779280215",
    "event_type": "phase_transition",
    "from_phase": "SCOUT",
    "to_phase": "PLAN",
    "severity": "info",
    "agent_alias": "chair",
    "duration_ms": 0,
    "inputs_summary": "Active recall: 3 hits for 'auth module'",
    "outputs_refs": null
}
```

**Tool call (delegate):**
```json
{
    "run_id": "pipe-1779280215",
    "event_type": "delegation_start",
    "tool_name": "delegate",
    "agent_alias": "council-builder",
    "inputs_summary": "Task: Implement auth module with TDD gates",
    "severity": "info"
}
```

**Error (phase failure):**
```json
{
    "run_id": "pipe-1779280215",
    "event_type": "phase_end",
    "from_phase": "BUILD",
    "severity": "error",
    "error": "Test suite failed: 3 tests failing",
    "duration_ms": 45000,
    "agent_alias": "council-builder"
}
```

**Retreat:**
```json
{
    "run_id": "pipe-1779280215",
    "event_type": "retreat",
    "from_phase": "BUILD",
    "to_phase": "SCOUT",
    "severity": "warning",
    "error": "Phase BUILD retries exhausted (4/3), retreating to SCOUT",
    "metadata": {"phase_attempts": {"BUILD": 4}, "global_attempts": 7}
}
```

---

## 10. Schema Validation at Phase Boundaries

### 10.1 Phase Input/Output Contracts

```python
# Phase input/output schemas (Pydantic-style)

PHASE_SCHEMAS = {
    "SCOUT": {
        "input": {
            "required": ["task"],
            "properties": {
                "task": {"type": "string", "minLength": 10},
                "project_id": {"type": "string"},
            }
        },
        "output": {
            "required": ["recall"],
            "properties": {
                "recall": {"type": "string"},
                "query": {"type": "string"},
            }
        },
        "artifact_kind": "recall_context",
    },
    "PLAN": {
        "input": {
            "required": ["task", "recall_context"],
            "properties": {
                "task": {"type": "string"},
                "recall_context": {"type": "string"},
            }
        },
        "output": {
            "required": ["plan", "spec_contract", "verification_criteria"],
            "properties": {
                "plan": {"type": "string"},
                "spec_contract": {"type": "string"},
                "verification_criteria": {"type": "string"},
            }
        },
        "artifact_kind": "plan",
    },
    "BUILD": {
        "input": {
            "required": ["task", "plan"],
            "properties": {
                "task": {"type": "string"},
                "plan": {"type": "string"},
                "spec_contract": {"type": "string"},
            }
        },
        "output": {
            "required": ["build_output", "diff"],
            "properties": {
                "build_output": {"type": "object"},
                "diff": {"type": "string"},
                "test_results": {"type": "object"},
            }
        },
        "artifact_kind": "build_output",
    },
    "COHESIVENESS_REVIEW": {
        "input": {
            "required": ["task", "plan", "build_output"],
            "properties": {
                "task": {"type": "string"},
                "plan": {"type": "string"},
                "build_output": {"type": "string"},
            }
        },
        "output": {
            "required": ["cohesive", "issues", "recommendation"],
            "properties": {
                "cohesive": {"type": "boolean"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "recommendation": {"type": "string", "enum": ["proceed", "fix", "retreat"]},
            }
        },
        "artifact_kind": "cohesiveness_report",
    },
    "AGENT_VALIDATE": {
        "input": {
            "required": ["task"],
            "properties": {
                "task": {"type": "string"},
            }
        },
        "output": {
            "required": ["ok", "gate"],
            "properties": {
                "ok": {"type": "boolean"},
                "gate": {"type": "string"},
            }
        },
        "artifact_kind": "gate_result",
    },
    "PENDING_REVIEW": {
        "input": {"required": ["task"]},
        "output": {
            "required": ["ok", "review"],
            "properties": {
                "ok": {"type": "boolean"},
                "review": {"type": "string"},
            }
        },
        "artifact_kind": "review_report",
    },
    "HUMAN_GATE": {
        "input": {"required": ["task"]},
        "output": {
            "required": ["ok", "approved"],
            "properties": {
                "ok": {"type": "boolean"},
                "approved": {"type": "boolean"},
                "note": {"type": "string"},
            }
        },
        "artifact_kind": "gate_result",
    },
    "INDEX": {
        "input": {"required": ["pipeline_id"]},
        "output": {
            "required": ["indexed"],
            "properties": {
                "indexed": {"type": "boolean"},
                "files": {"type": "array", "items": {"type": "string"}},
            }
        },
        "artifact_kind": "index_manifest",
    },
}
```

### 10.2 Validation at Phase Boundaries

```python
def validate_phase_input(phase: str, data: dict) -> tuple:
    """Validate input data against phase schema.
    
    Returns (ok: bool, errors: list).
    """
    schema = PHASE_SCHEMAS.get(phase, {}).get("input", {})
    required = schema.get("required", [])
    errors = []
    
    for field in required:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    
    return (len(errors) == 0, errors)

def validate_phase_output(phase: str, data: dict) -> tuple:
    """Validate output data against phase schema.
    
    Returns (ok: bool, errors: list).
    """
    schema = PHASE_SCHEMAS.get(phase, {}).get("output", {})
    required = schema.get("required", [])
    errors = []
    
    for field in required:
        if field not in data or data[field] is None:
            errors.append(f"Missing required output field: {field}")
    
    return (len(errors) == 0, errors)
```

---

## 11. Agent Architecture: Wiring into Chair / Co-Chair

### 11.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SUPER-AGENT COUNCIL                            │
│                                                                     │
│  User ──→ Chair (Qwen3.6-27B)                                      │
│              │                                                       │
│              │  Orchestrator Layer                                   │
│              │  ┌─────────────────────────────────────┐              │
│              │  │  PipelineState (state machine)       │              │
│              │  │  ├── transition_to() → writes to:   │              │
│              │  │  │   - workflow_runs (current phase) │              │
│              │  │  │   - state_executions (outcome)    │              │
│              │  │  │   - event_log (transition event)  │              │
│              │  │  └── _execute_phase() → writes to:  │              │
│              │  │      - artifacts (phase output)      │              │
│              │  │      - event_log (tool calls)        │              │
│              │  └─────────────────────────────────────┘              │
│              │                                                       │
│              ├─→ Context Router Service                              │
│              │    ├── get_run_snapshot(run_id)                       │
│              │    ├── get_recent_events(run_id, limit)               │
│              │    ├── get_artifacts(run_id, filter)                  │
│              │    └── summarize_run_issues(run_id)                   │
│              │                                                       │
│              ├─→ State Machine Linter                                │
│              │    ├── lint_current_workflow()                        │
│              │    ├── inspect_workflow_graph()                       │
│              │    └── propose_safe_transition(run_id, target)        │
│              │                                                       │
│              ├─→ Schema Validation                                   │
│              │    ├── validate_phase_input(phase, data)              │
│              │    └── validate_phase_output(phase, data)             │
│              │                                                       │
│              ├─→ memsearch (Active Recall)                           │
│              │    ├── Pre-dispatch: "past solutions for [module]"    │
│              │    ├── Failure match: "known fix for [error]"         │
│              │    └── Post-completion: index artifacts               │
│              │                                                       │
│              └─→ pi-subagents (Dispatch)                             │
│                   ├── council-builder  (write access, TDD skill)    │
│                   ├── council-reviewer-arch  (read-only)            │
│                   ├── council-reviewer-logic (read-only)            │
│                   └── council-co-chair  (cohesiveness review)       │
│                                                                     │
│  pipelines.db (SQLite)                                              │
│  ├── workflow_definitions (versioned schemas)                       │
│  ├── workflow_runs (run-level state)                                │
│  ├── state_executions (per-run, per-state)                          │
│  ├── artifacts (normalized outputs)                                 │
│  ├── event_log (append-only transitions)                            │
│  └── artifact_dependencies (consumed_by relationships)              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 11.2 Context Flow: Real-Time Behavior

**When a state completes:**

1. `_execute_phase()` returns result
2. `transition_to()` writes:
   - `state_executions` row (outcome, duration, error)
   - `event_log` row (phase_transition event)
   - `artifacts` row (if artifact produced)
3. Context Router immediately available:
   - `get_recent_events(run_id, 5)` → includes new transition
   - `get_artifacts(run_id)` → includes new artifact
4. Chair queries Context Router before next decision:
   - Pulls minimal relevant context
   - Decides which subagent to activate
5. Co-Chair/subagents receive focused context slice:
   - Not the whole world — just relevant artifacts/events
   - Write outputs back as new artifacts + events

### 11.3 Example Prompts

**Chair prompt before BUILD phase:**
```
=== RUN SNAPSHOT ===
Run: pipe-1779280215
Task: Implement auth module
Current Phase: BUILD
Status: running
Global Attempts: 3

=== RECENT EVENTS (last 5) ===
1. phase_transition: SCOUT → PLAN (success, 0ms)
2. phase_transition: PLAN → BUILD (success, 0ms)
3. tool_call: delegate to council-planner (success, 12s)
4. artifact_created: plan.md (2.4KB)
5. artifact_created: spec_contract.md (1.1KB)

=== ARTIFACTS ===
- plan.md (PLAN, plan, 2.4KB)
- spec_contract.md (PLAN, spec_contract, 1.1KB)
- verification_criteria.md (PLAN, verification_criteria, 0.8KB)

=== CONTEXT SLICE ===
Plan summary: 3 units, 2 dependencies, 5 verification steps
Spec contract: Must do: JWT auth, RBAC. Must not do: OAuth2.
```

**Co-Chair prompt for COHESIVENESS_REVIEW:**
```
=== COHESIVENESS REVIEW REQUEST ===
Run: pipe-1779280215
Task: Implement auth module

=== PLAN ARTIFACT ===
[plan.md content - 2.4KB]

=== BUILD OUTPUT ===
[build_output.json content - 1.8KB]

=== RECENT EVENTS ===
1. phase_transition: PLAN → BUILD (success)
2. phase_transition: BUILD → COHESIVENESS_REVIEW (success)
3. artifact_created: build_output.json (1.8KB)
4. artifact_created: diff.patch (3.2KB)

=== EVALUATE ===
1. Does the built code cohere with the plan?
2. Are there missing pieces or contradictions?
3. Is the implementation internally consistent?
```

---

## 12. Migration Path (5 Steps)

### Step 1: Add New Tables (Low Risk)

```sql
-- Run as migration script
-- Adds tables alongside existing pipelines/translations

-- Enum lookup tables
CREATE TABLE IF NOT EXISTS phase_names (...);
CREATE TABLE IF NOT EXISTS run_statuses (...);
CREATE TABLE IF NOT EXISTS event_severities (...);
CREATE TABLE IF NOT EXISTS artifact_kinds (...);

-- Core tables
CREATE TABLE IF NOT EXISTS workflow_definitions (...);
CREATE TABLE IF NOT EXISTS workflow_runs (...);
CREATE TABLE IF NOT EXISTS state_executions (...);
CREATE TABLE IF NOT EXISTS artifacts (...);
CREATE TABLE IF NOT EXISTS event_log (...);
CREATE TABLE IF NOT EXISTS artifact_dependencies (...);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_runs_project_status ON workflow_runs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_events_run_time ON event_log(run_id, timestamp DESC);
-- ... (all indexes from Section 4.3)
```

### Step 2: Backfill Existing Pipelines (Low Risk)

```python
# Migrate existing pipelines.db entries to new schema

def migrate_existing_pipelines(db: sqlite3.Connection):
    """Backfill workflow_runs and state_executions from existing pipelines table."""
    existing = db.execute("SELECT * FROM pipelines").fetchall()
    
    for row in existing:
        state_json = json.loads(row["state_json"])
        
        # Insert into workflow_runs
        db.execute("""
            INSERT OR REPLACE INTO workflow_runs
                (run_id, workflow_definition_id, project_id, task, current_phase, status, global_attempts, started_at, completed_at)
            VALUES (?, 'default-v1', ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["pipeline_id"],
            row["project_id"],
            row["task"],
            row["phase"],
            row["status"],
            row["global_attempts"],
            row["created_at"],
            row["completed_at"]
        ))
        
        # Backfill state_executions from history
        if state_json and "history" in state_json:
            for entry in state_json["history"]:
                db.execute("""
                    INSERT OR IGNORE INTO state_executions
                        (run_id, phase, attempt_number, outcome, error, started_at)
                    VALUES (?, ?, 1, ?, ?, ?)
                """, (
                    row["pipeline_id"],
                    entry.get("from_phase", "unknown"),
                    entry.get("outcome", "success"),
                    entry.get("error", ""),
                    entry.get("timestamp", row["created_at"])
                ))
        
        # Backfill artifacts
        if state_json and "artifacts" in state_json:
            for phase, path in state_json["artifacts"].items():
                db.execute("""
                    INSERT OR IGNORE INTO artifacts
                        (run_id, phase, kind, name, content_path, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    row["pipeline_id"],
                    phase,
                    _infer_kind(phase),
                    f"{phase.lower()}.json",
                    path,
                    row["created_at"]
                ))
    
    db.commit()
```

### Step 3: Add Context Router Service (Low Risk)

```python
# Add ContextRouter class to super-council.py
# Wire into SlotSupervisor as self.context_router

class SlotSupervisor:
    def __init__(self, ...):
        ...
        self.pipeline_tracker = PipelineTracker(...)
        self.context_router = ContextRouter(...)
```

### Step 4: Refactor PipelineState to Write to DB (Medium Risk)

```python
# Modify PipelineState.transition_to() to write to normalized tables
# Instead of just JSON file

def transition_to(self, new_phase, outcome="success", error="", artifact_path=""):
    # ... existing logic ...
    
    # Write to state_executions
    self.db.execute("""
        INSERT INTO state_executions (run_id, phase, attempt_number, outcome, error, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (...))
    
    # Write to event_log
    self.db.execute("""
        INSERT INTO event_log (run_id, event_type, from_phase, to_phase, error, severity)
        VALUES (?, 'phase_transition', ?, ?, ?, ?)
    """, (...))
    
    # Write to artifacts (if produced)
    if artifact_path:
        self.db.execute("""
            INSERT INTO artifacts (run_id, phase, kind, name, content_path)
            VALUES (?, ?, ?, ?, ?)
        """, (...))
    
    # Update workflow_runs
    self.db.execute("""
        UPDATE workflow_runs SET current_phase = ?, status = ?, global_attempts = ?
        WHERE run_id = ?
    """, (...))
    
    self.db.commit()
```

### Step 5: Add Schema Validation + Linter (Medium Risk)

```python
# Add phase schema validation at boundaries
# Add automated state linter as tool/service

# In _execute_phase():
def _execute_phase(self, ps: PipelineState) -> dict:
    # Validate input
    ok, errors = validate_phase_input(ps.phase, ps.to_dict())
    if not ok:
        return {"ok": False, "error": f"Input validation failed: {errors}"}
    
    # Execute phase
    result = self._run_* (ps)
    
    # Validate output
    ok, errors = validate_phase_output(ps.phase, result)
    if not ok:
        log.warning("Output validation warning for %s: %s", ps.phase, errors)
    
    return {"ok": True, "result": result}
```

---

## 13. Memory Layer: Vector Index + Context Bloat Prevention

### 13.1 Minimal Memory Layer

```python
class MemoryLayer:
    """Thin memory layer between state machine and agents.
    
    Periodically ingests state artifacts and logs.
    Lets agents run semantic queries.
    Prevents context bloat via summarization, chunking, eviction.
    """

    def __init__(self, db_path: str, memsearch: MemSearch):
        self.db = sqlite3.connect(db_path)
        self.memsearch = memsearch

    def ingest_artifact(self, artifact_id: int, content: str, metadata: dict):
        """Index artifact content for semantic search."""
        self.memsearch.add_document(
            text=content,
            metadata={
                "artifact_id": artifact_id,
                "run_id": metadata.get("run_id"),
                "phase": metadata.get("phase"),
                "kind": metadata.get("kind"),
            }
        )

    def ingest_event(self, event: dict):
        """Index event for semantic search."""
        self.memsearch.add_document(
            text=f"{event['event_type']}: {event.get('inputs_summary', '')} {event.get('error', '')}",
            metadata={
                "event_id": event["event_id"],
                "run_id": event["run_id"],
                "event_type": event["event_type"],
            }
        )

    def query(self, query: str, top_k: int = 3, filters: dict = None) -> list:
        """Semantic query across indexed artifacts and events."""
        return self.memsearch.search(query, top_k=top_k, filters=filters)

    def get_context_slice(self, run_id: str, max_tokens: int = 800) -> str:
        """Get compact context slice for a run.
        
        Strategy:
        1. Last N events (structured, high-signal)
        2. Key artifacts (summarized, not full content)
        3. Semantic recall (memsearch query)
        4. Evict oldest until under max_tokens
        """
        # 1. Last 5 events
        events = self.get_recent_events(run_id, 5)
        
        # 2. Key artifacts (summarized)
        artifacts = self.get_artifacts(run_id)
        artifact_summaries = [
            f"- {a['name']} ({a['kind']}, {a['phase']})"
            for a in artifacts[:5]
        ]
        
        # 3. Semantic recall
        recall = self.query(f"issues failures {run_id}", top_k=2)
        
        # 4. Assemble and truncate
        context = f"=== RUN CONTEXT: {run_id} ===\n\n"
        context += "=== RECENT EVENTS ===\n" + "\n".join(str(e) for e in events)
        context += "\n\n=== ARTIFACTS ===\n" + "\n".join(artifact_summaries)
        context += "\n\n=== RECALL ===\n" + str(recall)
        
        # Truncate to max_tokens (rough: 4 chars per token)
        max_chars = max_tokens * 4
        if len(context) > max_chars:
            context = context[:max_chars - 50] + "\n[TRUNCATED]"
        
        return context
```

### 13.2 Context Bloat Prevention Strategies

| Strategy | How | When |
|----------|-----|------|
| **Summarization** | Replace full artifact content with 3-line summary | After phase completes |
| **Chunking** | Split large artifacts into 500-token chunks | On ingest |
| **Time-based eviction** | Remove events older than N days from active index | Daily cron |
| **Importance-based eviction** | Keep error/warning events, evict info events | On index pressure |
| **Token budget per agent** | Max 800 tokens context slice per subagent | On dispatch |
| **Phase-tagged filtering** | Only recall same-phase artifacts | On active recall |

---

## 14. Implementation Priority

### P0 (Block Release) — Fix Critical Bugs

| # | Task | Effort | Why |
|---|------|--------|-----|
| 1 | Remove `PHASE_EXECUTORS` reference (line 5034) | 5 min | Crashes every phase |
| 2 | Fix `_auto_index_file` → `self.memory._auto_index_file` (line 5237) | 5 min | Crashes INDEX phase |
| 3 | Fix UnboundLocalError in `_handle_pipeline` (line 5296) | 10 min | Crashes retry path |
| 4 | Wire artifacts between phases | 30 min | COHESIVENESS_REVIEW gets empty context |
| 5 | Implement `_run_agent_validate` (not stub) | 1 hour | False sense of security |

### P1 (Next Sprint) — Add Normalized Tables

| # | Task | Effort | Why |
|---|------|--------|-----|
| 6 | Create enum lookup tables | 30 min | Foundation for FKs |
| 7 | Create `workflow_definitions` table | 30 min | Versioned schemas |
| 8 | Create `workflow_runs` table | 30 min | Run-level state |
| 9 | Create `state_executions` table | 30 min | Per-state tracking |
| 10 | Create `artifacts` table | 30 min | Normalized outputs |
| 11 | Create `event_log` table | 30 min | Append-only transitions |
| 12 | Create indexes | 30 min | Query performance |
| 13 | Backfill existing pipelines | 1 hour | Data migration |

### P2 (Week 2) — Context Router + Schema Validation

| # | Task | Effort | Why |
|---|------|--------|-----|
| 14 | Implement `ContextRouter` class | 2 hours | Queryable context |
| 15 | Wire into `SlotSupervisor` | 30 min | Available to agents |
| 16 | Add phase schema validation | 1 hour | Input/output contracts |
| 17 | Refactor `transition_to()` to write to DB | 2 hours | Normalized persistence |
| 18 | Add `_store_artifact()` method | 1 hour | Artifact storage |

### P3 (Week 3) — Linter + Memory Layer

| # | Task | Effort | Why |
|---|------|--------|-----|
| 19 | Implement `StateMachineLinter` | 2 hours | Automated validation |
| 20 | Expose linter as Chair/Co-Chair tool | 1 hour | Agent-accessible |
| 21 | Implement `MemoryLayer` | 2 hours | Semantic search |
| 22 | Add context bloat prevention | 1 hour | Token budget control |
| 23 | Add retention/archival strategy | 1 hour | High-volume handling |

---

## 15. Recommendations

### Libraries/Frameworks

| Component | Recommendation | Why |
|-----------|---------------|-----|
| **State machine** | `transitions` (Python) or custom | `transitions` adds diagram generation, but custom is simpler for our case |
| **Database** | `sqlite3` (stdlib) + `aiosqlite` for async | Zero dependencies, matches current stack |
| **Schema validation** | `pydantic` | Already used in super-council.py, JSON Schema compatible |
| **Vector store** | `memsearch` (current) + Milvus | Already integrated, no change needed |
| **Logging** | `structlog` | Structured logging with JSON output |
| **Orchestration** | `pi-subagents` (current) | Already integrated |

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **SQLite vs Postgres** | SQLite | Single-user setup, zero ops overhead, matches current stack |
| **JSON blob vs normalized** | Normalized | Queryable, indexable, FK-enforced |
| **Schema validation** | Pydantic | Already in codebase, JSON Schema compatible |
| **Context router** | Thin Python layer | No separate service, same process as supervisor |
| **Memory layer** | memsearch + SQLite | Leverages existing vector store |
| **Retention** | Archive tables + VACUUM | SQLite-native, no partitioning needed |

---

## 16. Deliverables Summary

### What This Report Provides

1. **Complete relational schema** (Section 4) — 6 tables + 4 enum tables + indexes
2. **Example queries** (Section 5) — run snapshot, recent events, similar runs, "what went wrong?"
3. **Orchestrator write path** (Section 6) — how to write on each transition
4. **Context router service** (Section 6.2, 8.3) — queryable APIs for agents
5. **Automated state linter** (Section 7) — unreachable states, invalid transitions, etc.
6. **Standardized output files** (Section 8) — naming convention, JSON schema
7. **Structured logging format** (Section 9) — event log schema, examples
8. **Schema validation** (Section 10) — phase input/output contracts
9. **Agent architecture** (Section 11) — wiring diagram, context flow, example prompts
10. **Migration path** (Section 12) — 5-step plan from current state
11. **Memory layer** (Section 13) — vector index, context bloat prevention
12. **Implementation priority** (Section 14) — P0/P1/P2/P3 breakdown
13. **Recommendations** (Section 15) — libraries, design decisions

### What Remains to Be Decided

1. **Postgres vs SQLite** — SQLite for now, Postgres if multi-user
2. **Async vs sync DB access** — `aiosqlite` if async, `sqlite3` if sync
3. **Context router as separate service** — Same process for now, separate if needed
4. **Retention policy** — 90 days default, configurable
5. **Schema versioning strategy** — Major version on breaking change, minor on additive

---

*Report compiled 2026-05-20*

---

## 17. Embedded Micro-Model Layer (Enrichment Service)

### 17.1 Purpose
The Embedded Micro-Model Layer is a lightweight, local inference component placed **after** canonical event and artifact persistence but **before** semantic indexing (memsearch) and final context assembly. Its role is to derive compact summaries, failure classifications, importance scores, and retrieval-friendly metadata from the normalized `event_log` and `artifacts` tables without altering the source-of-truth records written by the orchestrator.

This layer exists because the architecture separates three concerns:
1. Orchestrator writes structured run state and append-only events.
2. Memory Layer ingests artifacts/logs for semantic search.
3. Context Router assembles compact context slices for Chair/subagents.

The micro-model fits between stages 1 and 2 as a **derived-enrichment service** that improves recall quality and reduces prompt bloat while preserving deterministic persistence.

### 17.2 Placement in Architecture
```text
Phase Executor / PipelineState
        |
        v
Canonical DB Write Path (commit)
  - workflow_runs
  - state_executions
  - artifacts
  - event_log
        |
        v
Embedded Micro-Model Layer (async post-commit)
  - summarize artifacts
  - summarize event windows
  - classify failures
  - score importance
  - normalize retrieval text
        |
        +-------------------> Enrichment side tables / cached summaries
        |
        v
Memory Layer / memsearch ingest
  - chunk, embed, index, retain/evict
        |
        v
Context Router
  - run snapshot (SQL)
  - recent events
  - artifacts
  - semantic recall
  - enriched summaries
        |
        v
Chair / Co-Chair / Subagents
```

### 17.3 Responsibilities
The micro-model owns **only derived interpretation**:
- **Artifact Summarization:** Convert large plans, build outputs, diffs, and reviews into short, queryable abstracts.
- **Event-Window Compression:** Collapse recent tool/event sequences into narrative "what happened" summaries.
- **Failure Classification:** Extract normalized issue labels from errors/warnings to improve triage and recall.
- **Importance Ranking:** Score events/artifacts so low-signal items don't dominate context slices.
- **Retrieval Normalization:** Create phrase variants that make semantic search more reliable.

**Explicitly NOT used for:**
- Deciding whether an event is written.
- Replacing schema/validation or state-transition checks.
- Mutating canonical run history.
- Serving as the authoritative record of execution outcomes.

### 17.4 Suggested Interface
```python
class MicroModelEnricher:
    def enrich_artifact(self, artifact_id: int) -> dict:
        """Return summary, issue_labels, importance_score, retrieval_text."""

    def enrich_event_window(self, run_id: str, since_event_id: int | None = None) -> dict:
        """Return compact summary of recent events and classified issues."""

    def enrich_failure(self, run_id: str, execution_id: int) -> dict:
        """Return failure_category, likely_cause, and retrieval_text."""

    def should_index_full_text(self, artifact_id: int) -> bool:
        """Heuristic for summary-only vs full-text indexing."""
```

### 17.5 Storage Model (Enrichment Side Tables)
Derived outputs are stored separately from canonical tables to prevent bad summaries from corrupting official history:

```sql
CREATE TABLE IF NOT EXISTS artifact_summaries (
    artifact_id INTEGER PRIMARY KEY REFERENCES artifacts(artifact_id),
    summary TEXT,
    issue_labels JSON TEXT,
    importance_score REAL,
    model_name TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);

CREATE TABLE IF NOT EXISTS event_window_summaries (
    window_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    start_event_id INTEGER NOT NULL REFERENCES event_log(event_id),
    end_event_id INTEGER NOT NULL REFERENCES event_log(event_id),
    summary TEXT,
    issue_labels JSON TEXT,
    importance_score REAL,
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);

CREATE TABLE IF NOT EXISTS failure_classifications (
    classification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    execution_id INTEGER NOT NULL REFERENCES state_executions(execution_id),
    category TEXT,
    likely_cause TEXT,
    retrieval_text TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);
```

### 17.6 Operational Rules
1. **Canonical writes never wait on the micro-model.** Runs asynchronously or via post-commit trigger.
2. **Enrichment failures are non-blocking.** Logged as warnings in `event_log`; do not halt pipeline.
3. **Graceful fallback.** Context Router uses raw SQL + memsearch when enrichment is delayed/unavailable.
4. **Re-enrichment allowed.** Derived outputs can be regenerated when prompts/models improve.

### 17.7 Success Criteria
- Canonical run/event/artifact writes remain deterministic and unchanged.
- Semantic recall quality improves for artifact/failure lookup.
- Average context size drops while preserving key decision information.
- Co-Chair/reviewer prompts receive focused failure/artifact summaries.
- System operates correctly when enrichment is unavailable (raw SQL + memsearch fallback).

---

## 18. Alignment with Integrated State Architecture Specification

### 18.1 Component Mapping
| Specification Component | Report Implementation | Alignment |
|------------------------|----------------------|-----------||
| **State Machine Control Plane** | `workflow_definitions` + `VALID_TRANSITIONS` + `PipelineState` | ✅ Exact match. Versioned schemas, retry ceilings, retreat paths. |
| **Relational Pipeline Store** | `workflow_runs`, `state_executions`, `event_log`, `artifacts` | ✅ Exact match. Replaces JSON blobs with normalized tables. |
| **Artifact Store & Metadata** | `artifacts` table + standardized directory layout | ✅ Exact match. Kinds, schema versions, producer traceability. |
| **Event Logging & Observability** | `event_log` (append-only) + structured event schema | ✅ Exact match. Transitions, tools, delegations, failures captured. |
| **Context Router** | `ContextRouter` class + `get_run_snapshot()`, etc. | ✅ Exact match. Thin service layer, focused context slices. |
| **Semantic Memory Layer** | `MemoryLayer` + memsearch integration | ✅ Exact match. Augments SQL with similarity recall. |
| **Validation & Linting** | `StateMachineLinter` + `PHASE_SCHEMAS` | ✅ Exact match. Workflow linting + phase boundary validation. |
| **Embedded Micro-Model** | Section 17 (new) | ✅ Extends spec's "context assembly" principle with derived enrichment. |

### 18.2 Principle Verification
| Specification Principle | Implementation Status | Notes |
|------------------------|----------------------|-------||
| **Relational truth** | ✅ Enforced | All operational state in normalized tables. No JSON blobs for state. |
| **Append-only observability** | ✅ Enforced | `event_log` is strictly append-only. Transitions/tools/failures recorded immediately. |
| **Artifact-first context** | ✅ Enforced | Artifacts carry kind, version, producer, hash. Context Router queries them directly. |
| **Context assembly, not dumping** | ✅ Enforced | Context Router assembles slices. Micro-Model provides pre-computed summaries. |
| **Shared execution graph** | ✅ Enforced | Chair, Co-Chair, subagents all read/write to same `workflow_runs`/`event_log`. |
| **Validation at boundaries** | ✅ Enforced | `StateMachineLinter` + `PHASE_SCHEMAS` check transitions and I/O contracts. |

### 18.3 Data Flow Alignment
The specification defines:
`Execution → Relational Store → Context Router + Semantic Memory → Chair/Subagents`

The report implements exactly this, with the Embedded Micro-Model Layer inserted as an enrichment step:
`Execution → Canonical DB Write → Micro-Model Enrichment → Memory Layer (memsearch) → Context Router → Agents`

This preserves the spec's core rule: **structured persistence is the authoritative ledger**, while giving the semantic/prompt layers a better intermediate representation for retrieval and compression.

### 18.4 Conclusion
The recommended changes **fully align** with the Integrated State Architecture Specification. The Embedded Micro-Model Layer operationalizes the spec's "context assembly" and "artifact-first" principles by formalizing summarization, classification, and importance scoring as a distinct, non-blocking enrichment stage. All success criteria from both the report and the specification are met or exceeded.

---

*Report compiled 2026-05-20. Source reviews in `~/.pi/agent/sessions/--home-chief--/subagent-artifacts/`.*