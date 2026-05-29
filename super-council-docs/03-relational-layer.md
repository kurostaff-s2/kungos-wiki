# Relational Layer

> SQLite-backed relational store with WAL mode, FK enforcement, and structured context queries.

## RelationalStore

### Schema

```sql
-- Core tables
pipelines             -- Pipeline registry (idempotent via task_hash)
workflow_runs         -- Current run state (phase, status)
state_executions      -- Transition history (phase, attempt, outcome, error, duration)
event_log             -- Event timeline (type, severity, message, timestamp)
artifacts             -- Phase artifacts (phase, key, content, created_at)

-- Enrichment tables
artifact_summaries    -- Generated summaries, tags, keywords (FK → artifacts)
failure_classifications -- Error classification (type, confidence) (FK → state_executions)
event_window_summaries -- Event window narratives

-- Memory consolidation tables
consolidation_cache   -- Arc A380 pipeline ONLY (Granite-4.1-3B consolidation output)
                      -- Provenance prefix: consol-*
session_diary         -- Mechanical upsert ONLY (Pi extension hook + manual tool)
                      -- Provenance prefix: sess-*
                      -- Migration 04: created from split of consolidation_cache

-- Reference tables
workflow_definitions  -- Pipeline phase/transition definitions
phase_names           -- Phase registry with display_order
outcome_types         -- Enum: success, failure, retreat, global_ceiling
event_types           -- Enum: transition, error, warning, info
severity_levels       -- Enum: critical, error, warning, info
```

### Table Separation: consolidation_cache vs session_diary

**Design principle: Provenance traceability.** Every entry carries a prefix that reveals its origin:

| Prefix | Table | Source | Mechanism |
|--------|-------|--------|-----------|
| `consol-*` | `consolidation_cache` | Arc A380 (Granite-4.1-3B) | `_run_startup_consolidation()` pipeline |
| `sess-*` | `session_diary` | Mechanical (no model) | Pi extension `message_end` hook or `memory.upsert_summary` tool |
| `test-*` | `session_diary` | Test fixtures | Unit/integration tests |

**consolidation_cache** — Arc A380 pipeline only. Written by `ArcPipeline.run_consolidation()` after Granite-4.1-3B produces YAML output. Supports Tier 1 knowledge card injection, probation/activation lifecycle, and memsearch indexing.

**session_diary** — Mechanical hook only. Written by `RelationalStore.upsert_session_diary()` which parses Markdown sections (`##` or `###` Key Decisions, Topics Discussed, Work Completed, Open Items, etc.) and stores structured fields. Matches both `##` and `###` headers via `#{1,3}` regex. No model involvement — purely pattern detection + DB insert. Implements Karpathy's "ingest immediately" pattern.

**Migration path:** `04_session_summaries.sql` created the original table. `05_rename_to_session_diary.sql` renamed to `session_diary` for clear provenance (consolidation_cache = Arc-only, session_diary = mechanical). Existing `session-*` entries were migrated from `consolidation_cache` into `session_diary`, then removed from `consolidation_cache`. New mechanical upserts write directly to `session_diary`.

### WAL Mode + FK Enforcement

```python
PRAGMA journal_mode = WAL           -- Write-ahead logging
PRAGMA wal_autocheckpoint = 0       -- Manual checkpoint only
PRAGMA foreign_keys = ON            -- FK enforcement enabled
```

**Manual checkpoint** after each transition commit (Unit 2). Prevents WAL file growth.

### Key Methods

```python
# Pipeline management
upsert_pipeline(pipeline_id, project_id, task, phase, status, global_attempts)
find_active_pipeline(task, project_id)  # Dedup: returns existing if task+project match

# Transition recording
_next_attempt(run_id, phase)  # DB-primary attempt counter (HIGH-2 fix)
_record_transition(run_id, from_phase, to_phase, attempt_number, outcome, error, duration_ms, artifact_key, artifact_content)

# Schema queries
get_workflow_definitions(workflow_type)  # Returns phases + transitions
get_phase_info(phase_name)               # Returns phase_name, display_order, description

# Lifecycle
checkpoint()  # WAL checkpoint
close()       # Close connection
```

### FK Constraints

- `artifacts.run_id` → `workflow_runs.run_id`
- `artifact_summaries.artifact_id` → `artifacts.artifact_id`
- `failure_classifications.run_id` → `workflow_runs.run_id`
- `event_window_summaries.run_id` → `workflow_runs.run_id`
- `state_executions.run_id` → `workflow_runs.run_id`

**Result:** Orphaned rows blocked. `IntegrityError` on violation.

### Pipeline Dedup

```python
# Idempotent pipeline creation via task_hash
task_hash = SHA-256(f"{task}::{project_id}")
# UNIQUE constraint on pipelines.task_hash
# find_active_pipeline() checks status NOT IN ('done', 'failed')
```

## ContextRouter

### Structured Queries

```python
# Full run snapshot
get_run_snapshot(run_id) -> {
    "pipeline_id": str,
    "phase": str,
    "status": str,
    "executions": [...],      # state_executions
    "artifacts": [...],       # artifacts (with enrichment if available)
    "events": [...]           # event_log
}

# Recent events
get_recent_events(run_id, limit=10) -> [{event_type, severity, message, occurred_at}]

# Artifacts with filter
get_artifacts(run_id, phase=None, key=None) -> [{artifact_id, phase, key, content, enrichment}]

# Similar runs (semantic search)
find_similar_runs(query, project_id, limit=5) -> [{task, phase, status, score}]

# Issue summary
summarize_run_issues(run_id) -> {
    "failures": [...],         # state_executions with outcome=failure
    "error_events": [...],     # event_log with severity=error
    "total_attempts": int,
    "unique_errors": int
}
```

### Similar Runs Query

Uses `LIKE` matching on task text + phase/status filtering:

```python
find_similar_runs(query="implement auth", project_id="my-project", limit=5)
```

Returns runs with matching task text, ordered by similarity (text overlap).

## MemoryLayer

### Token-Budgeted Context Slices

```python
get_context_slice(run_id, max_tokens=100) -> str
```

**Algorithm:**
1. Query `artifacts` ordered by `created_at DESC` (newest first — MODERATE-2 fix)
2. Build context string with `[phase/key]` headers and `ARTIFACT_BOUNDARY` markers
3. Check token budget before each artifact (4 chars per token estimate)
4. **Never cut mid-artifact** — if budget exceeded, append truncation note and stop
5. Return complete blocks only

**Example output:**
```
[BUILD/output]
build-artifact-content-here
---ARTIFACT_BOUNDARY---
[PLAN/output]
plan-artifact-content-here
---ARTIFACT_BOUNDARY---
[TRUNCATED: [SCOUT/output], 40 chars, 2 lines]
```

### Artifact Ingestion

```python
ingest_artifact(run_id, phase, key, content)
```

- Inserts into `artifacts` table with ISO 8601 timestamp
- FK constraint ensures `run_id` exists in `workflow_runs`

### Eviction

```python
evict_old_artifacts(retention_days=30) -> int  # Returns count of evicted artifacts
```

- Deletes artifacts older than `retention_days`
- Cascades to `artifact_summaries` via FK

## Integration Flow

```
PipelineState.transition_to()
    │
    ├──► RelationalStore._record_transition()
    │       ├──► INSERT INTO state_executions
    │       ├──► INSERT INTO artifacts (if artifact_path)
    │       ├──► INSERT INTO event_log
    │       └──► UPDATE workflow_runs
    │
    ├──► ContextRouter.get_run_snapshot()  # Reads from all tables
    │
    ├──► MemoryLayer.get_context_slice()   # Reads from artifacts
    │
    └──► MicroModelEnricher.enqueue_artifact()  # Async enrichment
            └──► INSERT INTO artifact_summaries
```
