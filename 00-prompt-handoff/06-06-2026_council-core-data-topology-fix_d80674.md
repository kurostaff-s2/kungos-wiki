# Council Core Data Topology Fix — Master Plan

**Source spec:** First-principles analysis of council_core.db schema (2026-06-06)
**Generated:** 06-06-2026
**Goal:** Eliminate orphaned entries, zombie tables, and unscoped data in council_core.db; establish a foolproof project→work→execution traceability chain.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Database:** `/home/chief/.council-memory/council_core.db` (primary), `/home/chief/.council-memory/memory.db` (deprecated)
**Migration SQL:** `/home/chief/Coding-Projects/7-council/super_council/migrations_council_core/`
**Key files for this task:**
- `memory_service/store.py` — RelationalStore (all DB writes)
- `memory_service/mcp_server.py` — MCP tool handlers (upsert_summary, recall)
- `memory_service/router.py` — ContextRouter (all DB reads)
- `memory_service/db_poller.py` — FTS/vector indexing poller
- `arc_summarizer/pipeline.py` — Arc A380 consolidation pipeline
- `migrations_council_core/` — SQL migration scripts

**Related codebases:** None (self-contained within super_council)

---

## Problem Summary

| Issue | Severity | Evidence |
|---|---|---|
| 167 memory_entries have NULL source_run_id | Critical — orphaned | 100% of entries unlinked to any execution |
| 14 zombie tables across both DBs | High — confusion | Empty copies of deprecated tables |
| `entry_type='diary'` is a catch-all | Moderate — semantic debt | No distinction between agent summaries and Arc output |
| 8 tables lack project_id entirely | High — unscoped data | sessions, notes, documents, rollups, memory_entries |
| Arc pipeline writes to dead memory.db | Critical — data loss | session_diary and consolidation_cache both empty |
| Inconsistent ID naming | Low — confusion | run_id vs source_run_id vs workflow_runs.id |
| No ON DELETE CASCADE | Moderate — orphan risk | Hard deletes create orphans |

---

## Options and Recommendations

### Option A: Minimal Fix (Stop the bleeding)

**Scope:** Drop zombie tables, fix entry_type naming, enforce source_run_id at write time.

**Pros:**
- Fast (~2 hours)
- Low risk — no schema additions
- Fixes immediate orphaning problem
- No migration of existing data

**Cons:**
- project_id scoping remains incomplete
- Arc pipeline still broken
- Legacy tables in memory.db remain (just ignored)

**Recommendation:** ✅ **Do this first** — it's the foundation everything else builds on.

---

### Option B: Full Topology Fix (Complete re-scope)

**Scope:** Option A + add project_id to all unscoped tables + redirect Arc pipeline + retroactive scoping.

**Pros:**
- Every row traceable to a project
- Arc pipeline produces usable data
- Clean architecture going forward
- Full audit trail

**Cons:**
- ~6–8 hours
- Requires migration of 167 existing memory_entries
- Arc pipeline needs testing
- Breaking change for any code assuming global memories

**Recommendation:** ✅ **Do this after Option A validates** — split into two handoff sessions.

---

### Option C: Nuclear Option (Rebuild council_core from scratch)

**Scope:** Drop both DBs, re-run migrations with corrected schema, re-migrate all data with proper FKs.

**Pros:**
- Clean slate, no legacy debt
- Perfect FK enforcement from day one
- Consistent naming throughout

**Cons:**
- ~12+ hours
- Risk of data loss during re-migration
- Downtime during rebuild
- Overkill for current scale (167 entries)

**Recommendation:** ❌ **Skip** — cost outweighs benefit at current data volume. Revisit if table count exceeds 50 or row count exceeds 100K.

---

## Execution Order (DAG)

```
Phase A1: Drop zombie tables          Phase A2: Fix entry_type semantics
  ↓                                       ↓
Phase A1.5: RelationalStore Guards    Phase A3: Enforce source_run_id
  ↓                                       ↓
Phase A1.6: Verified Contextual Res.  Phase A5: Production wiring
  ↓                                       ↑
Phase A4: Tests + verification ──────────┘
```

- A1 and A2 are independent — can run in parallel
- A1.5 depends on A1 (tables must be clean before adding constraints)
- A1.6 depends on A1.5 (G1–G5 must be in place before adding contextual resolver)
- A3 depends on A1.5 (guards must be in place before backfill)
- A4 depends on A1.5 + A1.6 (tests cover all guards)
- A5 depends on all phases (production wiring after all guards verified)

---

## Phase A1: Drop Zombie Tables

**What:** Remove 14 empty/deprecated tables from both council_core.db and memory.db.

**Files:**
- Create: `migrations_council_core/04_drop_zombie_tables.sql`
- Modify: `memory_service/store.py` (remove any dead code referencing dropped tables)

**Steps:**
1. Verify all 14 tables are empty (0 rows) — document proof
2. Write SQL migration: `04_drop_zombie_tables.sql`
   - council_core.db: DROP `session_summaries`, `session_diary`, `raw_session_memories`, `consolidation_cache`, `memories`, `notes`, `documents`
   - memory.db: DROP `session_summaries`, `session_diary`, `raw_session_memories`, `consolidation_cache`, `pipelines`, `artifacts`, `event_log`
3. Check for code references to dropped tables (grep in `memory_service/`)
4. Remove dead code paths (e.g., `query_session_summaries()`, `query_consolidation_cache()`)
5. Run migration against both DBs
6. Verify: `PRAGMA table_info` on both DBs shows only active tables

**Tests:**
- [ ] `SELECT COUNT(*) FROM sqlite_master WHERE type='table'` — count reduced by 14
- [ ] No code references to dropped table names
- [ ] `python3 -m memory_service` starts without import errors

**Dependencies:** None.

---

## Phase A1.5: RelationalStore Guards (Deduplication + Validation)

**What:** Add five RelationalStore-level guards to prevent duplicate projects, orphaned work items, misassignment, and duplicate runs. All guards are write-time enforcement in `store.py` — every DB write routes through RelationalStore.

**Why RelationalStore?** It is the **single write boundary** for council_core.db. All callers route here:
- MCP tools (`mcp_server.py`) → `self._store.*()`
- HTTP endpoints (`http_endpoints.py`) → `store.*()`
- Arc pipeline (`arc_summarizer/pipeline.py`) → `self._relational_store.*()`
- ContextRouter (`router.py`) → `self._store.*()` (reads only)
- DB poller (`db_poller.py`) → direct `store.db` (FTS indexing only)

**Files:**
- Modify: `memory_service/store.py` — add guards to all write methods
- Create: `migrations_council_core/04b_add_constraints.sql` — UNIQUE indexes
- Modify: `memory_service/mcp_server.py` — expose `resolve_project()` tool

### Guard 1: `resolve_project()` — Only Project Creation Path

**Problem:** `get_or_create_project()` exists but is never called. No application-level deduplication.

**Implementation:**
```python
# store.py — rename and harden
def resolve_project(self, slug: str, name: str = None) -> Dict[str, Any]:
    """Get existing project by slug or create one. ONLY creation path."""
    row = self.db.execute(
        "SELECT id, slug, name, status FROM projects "
        "WHERE slug = ? AND is_deleted = 0",
        (slug,),
    ).fetchone()
    if row:
        return dict(row)
    project_id = str(uuid.uuid4())
    now = self._now_iso()
    label = name or slug
    self.db.execute(
        """INSERT INTO projects (id, slug, name, status, created_at, updated_at,
           updated_by, updated_source, origin_source)
           VALUES (?, ?, ?, 'active', ?, ?, 'system', 'council_core', 'council_core')""",
        (project_id, slug, label, now, now),
    )
    self.db.commit()
    return {"id": project_id, "slug": slug, "name": label, "status": "active"}
```

**MCP tool:**
```python
# mcp_server.py
@self._mcp.tool(name="resolve_project")
def resolve_project(slug: str, name: str = None) -> str:
    """Get or create a project by slug. Returns project_id for use in other tools."""
    project = self._store.resolve_project(slug, name)
    return json.dumps({"project_id": project["id"], "slug": project["slug"]})
```

### Guard 2: UNIQUE Index on (project_id, title) for Work Items

**Problem:** Same work item can be created multiple times in the same project.

**Implementation:**
```sql
-- migrations_council_core/04b_add_constraints.sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_items_project_title
ON work_items(project_id, title) WHERE is_deleted = 0;
```

```python
# store.py — create_work_item() becomes get_or_create_work_item()
def get_or_create_work_item(self, project_id: str, kind: str, title: str, ...) -> Dict[str, Any]:
    """Get existing work item or create one. Dedup by (project_id, title)."""
    row = self.db.execute(
        "SELECT id, project_id, kind, title FROM work_items "
        "WHERE project_id = ? AND title = ? AND is_deleted = 0",
        (project_id, title),
    ).fetchone()
    if row:
        return dict(row)
    # ... proceed with INSERT (unique index catches race conditions)
```

### Guard 3: Semantic Project Validation (Prevent Misassignment)

**Problem:** Valid project_id can be wrong contextually (e.g., "council" vs "test-project").

**Implementation:**
```python
# store.py — add to create_work_item(), upsert_memory_entry(), etc.
def _validate_project(self, project_id: str) -> Dict[str, Any]:
    """Validate project exists, is active, not deleted. Raises ValueError on failure."""
    project = self.db.execute(
        "SELECT id, slug, name, status, is_deleted FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if not project:
        raise ValueError(f"Project {project_id} not found")
    if project['is_deleted']:
        raise ValueError(f"Project {project_id} is soft-deleted")
    if project['status'] == 'archived':
        raise ValueError(f"Project {project_id} ({project['slug']}) is archived")
    return dict(project)
```

**Apply to all write methods that accept project_id:**
- `create_work_item()` → resolve project from work_item_id anchor
- `upsert_memory_entry()` → resolve project from run_id/work_item_id anchors, verify caller claims, stamp canonical project_id
- `create_review()` → resolve project from work_item_id anchor
- `create_workflow_run()` → resolve project from work_item_id anchor

### Guard 4: One Running Run Per Work Item

**Problem:** Multiple workflow runs can be created for the same work item simultaneously.

**Implementation:**
```sql
-- migrations_council_core/04b_add_constraints.sql
-- Partial index: only enforces uniqueness for running runs
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_one_active
ON workflow_runs(work_item_id) WHERE run_state = 'running' AND is_deleted = 0;
```

```python
# store.py — in ensure_workflow_run()
def ensure_workflow_run(self, run_id: str, work_item_id: str, project_id: str, ...) -> None:
    """Ensure a workflow run exists. Prevents duplicate running runs."""
    # Check for existing running run
    existing = self.db.execute(
        "SELECT id FROM workflow_runs "
        "WHERE work_item_id = ? AND run_state = 'running' AND is_deleted = 0",
        (work_item_id,),
    ).fetchone()
    if existing and existing[0] != run_id:
        raise ValueError(
            f"Work item {work_item_id} already has a running run: {existing[0]}"
        )
    # ... proceed with INSERT
```

### Guard 5: Memory Entry Project Scoping (from Phase A3)

**Problem:** 167 memory_entries have NULL project_id.

**Implementation:** Covered in Phase A3. This phase establishes the resolver-first contract that A3 enforces on all writes.

**Steps:**
1. Run `04b_add_constraints.sql` against council_core.db
2. Add `_validate_project()` method to RelationalStore (called by resolver after anchor resolution)
3. Add `resolve_project()` MCP tool
4. Update `create_work_item()` → `get_or_create_work_item()` with dedup
5. Add resolver-first calls to all project-scoped write methods (resolve from anchors, verify claims, stamp canonical project_id)
6. Add `ensure_workflow_run()` duplicate-run check

**Tests:**
- [ ] `resolve_project("council")` returns existing project (no duplicate)
- [ ] `resolve_project("new-slug")` creates new project
- [ ] `get_or_create_work_item()` returns existing on duplicate (project_id, title)
- [ ] `_validate_project(nonexistent_uuid)` raises ValueError
- [ ] `_validate_project(archived_project_id)` raises ValueError
- [ ] Two concurrent `ensure_workflow_run()` for same work_item → second fails
- [ ] UNIQUE indexes enforced (direct INSERT with duplicate fails)

**Dependencies:** A1 (tables must be clean before adding constraints).

---

## Phase A1.6: Verified Contextual Resolver (G6–G11)

**What:** Replace naive project validation with a **verified contextual resolver** that ensures semantic ownership, not just referential legitimacy. The server stamps the final `project_id` on write — caller claims are inputs to validation, not trusted ownership.

**Core insight:** G1/G3 validate that a project *exists*, not that it's the *right* project. A valid active project can still be the wrong project for the work. This phase closes that gap.

**Resolution priority (authoritative, not heuristic):**
```
authoritative binding > explicit slug claim (verified) > path heuristic (advisory only) > fail_closed
```

**Never silently default to "council"** for ambiguous project work — that converts uncertainty into silent misassignment.

**Files:**
- Modify: `memory_service/store.py` — add `resolve_project_from_context()`, `workspace_bindings` table
- Modify: `memory_service/mcp_server.py` — structured error responses
- Create: `migrations_council_core/04c_workspace_bindings.sql` — binding table
- Create: `memory_service/errors.py` — typed exceptions + structured error payloads

### Authoritative Anchors

| Anchor | Strength | Source |
|---|---|---|
| `work_item_id` | **Authoritative** | Already bound to project via FK |
| `run_id` | **Authoritative** | Already bound to work_item/project via FK |
| `workspace_bindings` table | **Authoritative** | Persisted root-path-to-project mapping |
| `external_key` | **Authoritative** | Already validated during sync |
| File path (raw) | **Advisory only** | Useful hint, not binding without table entry |
| Caller-supplied `project_id` | **Claim to verify** | Must match resolved project |

### Guard 6: Resolution Anchor Required for Writes

**Problem:** No write may rely solely on arbitrary `project_id` unless the endpoint is explicitly system-scoped.

**Implementation:**
```python
# store.py
class ResolutionResult:
    """Result of project resolution. Server uses this, not caller's claim."""
    def __init__(
        self,
        project_id: str,
        slug: str,
        basis: str,  # "work_item_id", "run_id", "workspace_binding", "explicit_slug", "system_scope"
        confidence: str,  # "authoritative", "verified", "heuristic", "ambiguous"
        candidates: list = None,
    ):
        self.project_id = project_id
        self.slug = slug
        self.basis = basis
        self.confidence = confidence
        self.candidates = candidates or []

    @property
    def is_writable(self) -> bool:
        """Can we write with this resolution?"""
        return self.confidence in ("authoritative", "verified")

    @property
    def is_system_scope(self) -> bool:
        """Is this a system-scoped operation (allowed to default to council)?"""
        return self.basis == "system_scope"
```

### Guard 7: Anchor Agreement

**Problem:** Multiple supplied anchors must resolve to the same project.

**Implementation:**
```python
def resolve_project_from_context(
    self,
    work_item_id: str = None,
    run_id: str = None,
    file_path: str = None,
    explicit_project_id: str = None,
    explicit_slug: str = None,
    is_system_operation: bool = False,
) -> ResolutionResult:
    """Resolve project from context. Server stamps final project_id."""
    resolved: List[Tuple[str, str, str]] = []  # (project_id, basis, confidence)

    # 1. Authoritative: work_item_id → project
    if work_item_id:
        row = self.db.execute(
            "SELECT project_id FROM work_items WHERE id = ? AND is_deleted = 0",
            (work_item_id,),
        ).fetchone()
        if row:
            resolved.append((row[0], "work_item_id", "authoritative"))

    # 2. Authoritative: run_id → workflow_runs → project
    if run_id:
        row = self.db.execute(
            "SELECT project_id FROM workflow_runs WHERE id = ? AND is_deleted = 0",
            (run_id,),
        ).fetchone()
        if row:
            resolved.append((row[0], "run_id", "authoritative"))

    # 3. Authoritative: workspace binding
    if file_path:
        # Walk up directory tree to find binding
        path = Path(file_path).resolve()
        for part in [path] + list(path.parents):
            row = self.db.execute(
                "SELECT project_id FROM workspace_bindings WHERE path = ?",
                (str(part),),
            ).fetchone()
            if row:
                resolved.append((row[0], "workspace_binding", "authoritative"))
                break

    # 4. Verified: explicit slug claim
    if explicit_slug:
        row = self.db.execute(
            "SELECT id FROM projects WHERE slug = ? AND is_deleted = 0 AND status = 'active'",
            (explicit_slug,),
        ).fetchone()
        if row:
            resolved.append((row[0], "explicit_slug", "verified"))

    # 5. Claim to verify: explicit project_id
    if explicit_project_id:
        # Only accept if it agrees with authoritative anchors
        if resolved and all(r[0] == explicit_project_id for r in resolved):
            resolved.append((explicit_project_id, "explicit_claim_verified", "verified"))
        elif not resolved:
            # No anchors to verify against — treat as claim
            row = self.db.execute(
                "SELECT id FROM projects WHERE id = ? AND is_deleted = 0 AND status = 'active'",
                (explicit_project_id,),
            ).fetchone()
            if row:
                resolved.append((explicit_project_id, "explicit_claim_unverified", "heuristic"))

    # 6. System scope exception
    if is_system_operation and not resolved:
        row = self.db.execute(
            "SELECT id FROM projects WHERE slug = 'council' AND is_deleted = 0",
        ).fetchone()
        if row:
            resolved.append((row[0], "system_scope", "verified"))

    # Resolve: check agreement
    if not resolved:
        return ResolutionResult(
            project_id=None, slug=None, basis="none",
            confidence="ambiguous", candidates=[]
        )

    # All anchors must agree
    unique_ids = set(r[0] for r in resolved)
    if len(unique_ids) > 1:
        # Conflict — fail closed
        return ResolutionResult(
            project_id=None, slug=None, basis="conflict",
            confidence="ambiguous",
            candidates=[{"id": uid, "basis": [r[1] for r in resolved if r[0] == uid]} for uid in unique_ids]
        )

    # Highest confidence wins
    best = max(resolved, key=lambda r: {"authoritative": 3, "verified": 2, "heuristic": 1}.get(r[2], 0))
    project = self.db.execute(
        "SELECT slug FROM projects WHERE id = ?", (best[0],),
    ).fetchone()

    return ResolutionResult(
        project_id=best[0],
        slug=project[0] if project else "unknown",
        basis=best[1],
        confidence=best[2],
        candidates=[{"id": r[0], "basis": r[1]} for r in resolved],
    )
```

### Guard 8: Claim Verification

**Problem:** If caller supplies `project_id` or `slug`, it must match the resolved project.

**Implementation:**
```python
# In all write methods:
def upsert_memory_entry(self, ..., project_id: str = None, run_id: str = None, ...) -> str:
    # Resolve from context
    resolution = self.resolve_project_from_context(
        run_id=run_id,
        explicit_project_id=project_id,
    )

    if not resolution.is_writable and not resolution.is_system_scope:
        raise ProjectResolutionError(
            code="PROJECT_RESOLUTION_AMBIGUOUS",
            message="Cannot determine project. Multiple candidates or no anchors.",
            provided={"project_id": project_id, "run_id": run_id},
            resolved=None,
            candidates=resolution.candidates,
            suggested_action="Provide work_item_id or run_id for authoritative resolution.",
        )

    # Verify claim matches resolution
    if project_id and project_id != resolution.project_id:
        raise ProjectResolutionError(
            code="PROJECT_RESOLUTION_MISMATCH",
            message=f"Provided project_id '{project_id}' does not match resolved project.",
            provided={"project_id": project_id},
            resolved={"project_id": resolution.project_id, "slug": resolution.slug, "basis": resolution.basis},
            suggested_action=f"Retry with project_id='{resolution.project_id}' or omit to let server assign.",
        )

    # Server stamps final project_id
    final_project_id = resolution.project_id
    # ... proceed with INSERT using final_project_id
```

### Guard 9: Ambiguity Fail-Closed

**Problem:** Multiple candidate projects means no write.

**Implementation:** Already handled in `resolve_project_from_context()` — returns `confidence="ambiguous"` with candidate list. `is_writable` is `False`.

### Guard 10: Server-Stamped project_id

**Problem:** Persistence uses only resolved canonical `project_id`, never caller's raw claim.

**Implementation:** All write methods use `resolution.project_id` (server-resolved), never `project_id` parameter directly. The parameter is treated as a claim to verify.

### Guard 11: System-Scope Exception

**Problem:** "Default to council" is reasonable for genuine internal system operations, dangerous as a generic fallback.

**Implementation:**
```python
# Narrow allowlist: only truly internal/cache-like writes may default to council.
# Ordinary summary writes (inline-summary, auto-detected) are NOT system-scoped
# unless provably internal (e.g., system health checks, internal diagnostics).
SYSTEM_OPERATIONS = {
    "upsert_consolidation_cache": True,   # Internal cache, no user content
    "upsert_injection_blacklist": True,   # Internal guard, no user content
    "upsert_phase_names": True,            # Internal registry
    "upsert_event_types": True,            # Internal registry
    "upsert_outcome_types": True,          # Internal registry
    "upsert_severity_levels": True,        # Internal registry
}

# upsert_summary is NOT system-scoped — it carries user/agent content.
# It requires anchors (run_id, work_item_id) or explicit project resolution.
def upsert_summary(summary_text, source="inline-summary", project_id=None, run_id=None, ...) -> str:
    resolution = store.resolve_project_from_context(
        run_id=run_id,
        explicit_project_id=project_id,  # Claim to verify
        is_system_operation=False,        # Never system-scoped for content writes
    )
    if not resolution.is_writable:
        raise ProjectResolutionError(
            code="PROJECT_RESOLUTION_AMBIGUOUS",
            message="Summary writes require a project anchor. Provide run_id or resolve_project(slug) first.",
            provided={"project_id": project_id, "run_id": run_id},
            candidates=resolution.candidates,
            suggested_action="Call resolve_project(slug) to get project_id, or provide run_id.",
        )
```

### Structured Error Payload

**Problem:** Current `{"error": "Project X not found"}` tells the agent what failed, not how to repair.

**Implementation:**
```python
# memory_service/errors.py
class ProjectResolutionError(Exception):
    """Structured error for agent self-correction."""
    def __init__(
        self,
        code: str,
        message: str,
        provided: dict = None,
        resolved: dict = None,
        candidates: list = None,
        suggested_action: str = None,
        retryable: bool = True,
    ):
        self.payload = {
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "provided": provided or {},
                "resolved": resolved,
                "candidates": candidates or [],
                "suggested_action": suggested_action,
            }
        }
        super().__init__(message)

# Error codes:
# PROJECT_NOT_FOUND — requested project doesn't exist
# PROJECT_ARCHIVED — project exists but is archived
# PROJECT_DELETED — project is soft-deleted
# PROJECT_RESOLUTION_AMBIGUOUS — multiple candidates, no agreement
# PROJECT_RESOLUTION_MISMATCH — caller claim doesn't match resolved
# PROJECT_ANCONFLICT — authoritative anchors disagree
```

**MCP tool handler:**
```python
@self._mcp.tool(name="upsert_summary")
def upsert_summary(summary_text: str, source: str = "inline-summary", ...) -> str:
    try:
        # ... validation and write
    except ProjectResolutionError as e:
        return json.dumps(e.payload, indent=2)
    except ValueError as e:
        return json.dumps({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(e),
                "retryable": False,
            }
        }, indent=2)
```

### workspace_bindings Table

```sql
-- migrations_council_core/04c_workspace_bindings.sql
CREATE TABLE IF NOT EXISTS workspace_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id),
    binding_type TEXT NOT NULL DEFAULT 'workspace_root'
        CHECK (binding_type IN ('workspace_root', 'project_root', 'vendor_root')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now')),
    created_by TEXT NOT NULL DEFAULT 'system',
    UNIQUE(path, project_id)
);

-- Seed: current known workspaces
INSERT OR IGNORE INTO workspace_bindings (path, project_id, binding_type)
VALUES
    ('/home/chief/Coding-Projects/7-council', 'afee346a-0de1-4683-afcf-914a417c553c', 'workspace_root'),
    ('/home/chief/llm-wiki', 'afee346a-0de1-4683-afcf-914a417c553c', 'project_root');
```

**Steps:**
1. Create `workspace_bindings` table + seed current workspaces
2. Add `ResolutionResult` class to `store.py`
3. Add `resolve_project_from_context()` method
4. Add `ProjectResolutionError` exception class
5. Update all write methods to call resolver before validation
6. Replace raw `ValueError` strings with typed exceptions
7. Update MCP tool handlers to return structured error JSON

**Tests:**
- [ ] `resolve_project_from_context(work_item_id=...)` returns authoritative resolution
- [ ] `resolve_project_from_context(run_id=...)` returns authoritative resolution
- [ ] `resolve_project_from_context(file_path=...)` uses workspace_bindings
- [ ] Two anchors with different projects → `confidence="ambiguous"`, `is_writable=False`
- [ ] Caller `project_id` mismatches resolved → `PROJECT_RESOLUTION_MISMATCH`
- [ ] No anchors, no explicit → `confidence="ambiguous"`, fail closed
- [ ] System operation with no anchors → resolves to "council" (system_scope)
- [ ] Non-system operation with no anchors → fail closed (no silent default)
- [ ] Structured error payload has all fields: code, message, retryable, provided, resolved, candidates, suggested_action
- [ ] MCP tool returns structured error JSON (not raw string)

**Dependencies:** A1.5 (G1–G5 must be in place first).

---

## Phase A2: Fix entry_type Semantics

**What:** Rename `diary` → `summary` for agent-produced entries; reserve `diary` for Arc output; add `consolidation` type.

**Files:**
- Create: `migrations_council_core/05_fix_entry_types.sql`
- Modify: `memory_service/store.py` — `upsert_memory_entry()` CHECK constraint
- Modify: `memory_service/mcp_server.py` — `upsert_summary()` routing logic

**Steps:**
1. Migrate existing data:
   ```sql
   UPDATE memory_entries SET entry_type='summary'
   WHERE entry_type='diary' AND origin_source='inline-summary';
   UPDATE memory_entries SET entry_type='summary'
   WHERE entry_type='diary' AND origin_source='auto-detected-assistant-message';
   -- Note: auto-detected should already be 'raw', but fix any mis-tagged
   ```
2. Update CHECK constraint in `store.py`:
   ```python
   entry_type IN ('raw', 'summary', 'diary', 'consolidation', 'incident', 'decision')
   ```
3. Update `upsert_summary()` routing:
   - `source == "auto-detected-assistant-message"` → `entry_type="raw"` (keep)
   - `source == "inline-summary"` → `entry_type="summary"` (NEW)
   - `source contains "consolidation"` → `entry_type="consolidation"` (NEW)
   - `source contains "arc"` → `entry_type="diary"` (reserved for Arc)
   - Everything else → `entry_type="summary"` (default)
4. Verify distribution:
   - `raw`: auto-detected messages
   - `summary`: agent-produced summaries (was `diary`)
   - `diary`: 0 rows (reserved for Arc)
   - `consolidation`: 0 rows (reserved for Arc full consolidation)

**Tests:**
- [ ] All 167 entries have valid entry_type (no raw `diary` from inline-summary)
- [ ] New CHECK constraint enforced (INSERT with invalid type fails)
- [ ] `upsert_summary` with `source="inline-summary"` produces `entry_type="summary"`

**Dependencies:** None (parallel with A1).

---

## Phase A3: Enforce source_run_id at Write Time (Resolver-First)

**What:** All write paths resolve project from authoritative anchors, verify caller claims, stamp canonical project_id, and persist authoritative source_run_id only. The resolver is the mandatory write contract — every write must pass through it.

**Invariant:** No write path may persist caller-supplied `project_id` directly. The server stamps the final `project_id` from the resolution result.

**Files:**
- Modify: `memory_service/mcp_server.py` — add `project_id`, `run_id` params to `upsert_summary()`
- Modify: `memory_service/store.py` — resolver-first in `upsert_memory_entry()` (resolve anchors, verify claims, stamp canonical project_id)
- Create: `migrations_council_core/06_enforce_source_run_id.sql` (ALTER TABLE + backfill)

**Steps:**
1. Add `project_id` column to `memory_entries`:
   ```sql
   ALTER TABLE memory_entries ADD COLUMN project_id TEXT REFERENCES projects(id);
   ```
2. Backfill existing entries:
   ```sql
   -- All existing entries are from the council project (system-scoped)
   UPDATE memory_entries SET project_id = 'afee346a-0de1-4683-afcf-914a417c553c'
   WHERE project_id IS NULL;
   ```
3. For `source_run_id`: since none are set, backfill based on `created_at` matching nearest `workflow_runs.started_at`:
   ```sql
   -- INFERRED provenance: temporal matching is best-effort, not authoritative
   -- Mark as low-confidence: origin_source='temporal-backfill', confidence='inferred'
   UPDATE memory_entries SET source_run_id = (
       SELECT id FROM workflow_runs
       WHERE started_at <= memory_entries.created_at
       ORDER BY started_at DESC LIMIT 1
   ), origin_source = 'temporal-backfill'
   WHERE source_run_id IS NULL;
   ```
   **Provenance marking:** All temporal backfills are flagged as `inferred` confidence. They are advisory links, not authoritative truth. Future writes with real anchors supersede them.
4. Update `upsert_summary()` MCP tool — **resolver-first, not direct validation**:
   ```python
   def upsert_summary(
       summary_text: str,
       source: str = "inline-summary",
       project_id: str = None,  # Claim to verify, not trusted
       run_id: str = None,       # Anchor for resolution
   ) -> str:
       # Resolver-first: resolve project from authoritative anchors
       # Summary writes are NOT system-scoped — they carry user/agent content
       resolution = store.resolve_project_from_context(
           run_id=run_id,
           explicit_project_id=project_id,  # Treated as claim, not truth
           is_system_operation=False,        # Content writes require anchors
       )

       # Fail closed on ambiguity (no silent default)
       if not resolution.is_writable:
           raise ProjectResolutionError(
               code="PROJECT_RESOLUTION_AMBIGUOUS",
               message="Summary writes require a project anchor. Provide run_id or resolve_project(slug) first.",
               provided={"project_id": project_id, "run_id": run_id},
               candidates=resolution.candidates,
               suggested_action="Call resolve_project(slug) to get project_id, or provide run_id.",
           )

       # Verify claim matches resolution
       if project_id and project_id != resolution.project_id:
           raise ProjectResolutionError(
               code="PROJECT_RESOLUTION_MISMATCH",
               message=f"Claimed project_id '{project_id}' does not match resolved '{resolution.slug}'.",
               provided={"project_id": project_id},
               resolved={"project_id": resolution.project_id, "slug": resolution.slug, "basis": resolution.basis},
               suggested_action=f"Retry with project_id='{resolution.project_id}' or omit to let server assign.",
           )

       # Server stamps final project_id (never caller's raw claim)
       final_project_id = resolution.project_id
       final_source_run_id = run_id  # Only from authoritative anchor, never inferred

       cache_id = store.upsert_memory_entry(
           entry_type=resolve_entry_type(source),
           body=summary_text,
           project_id=final_project_id,       # Server-stamped
           source_run_id=final_source_run_id, # From anchor
           source=source,
       )
   ```
5. Update `upsert_memory_entry()` — **resolver-first semantics**:
   - `project_id` is always server-stamped from `ResolutionResult.project_id`
   - `source_run_id` is only set from authoritative anchors (`run_id`, `work_item_id`)
   - Temporal backfills are marked `origin_source='temporal-backfill'`, `confidence='inferred'`
   - **No direct raw parameter validation** — all validation flows through resolver

**Tests:**
- [ ] All 167 entries now have `project_id` set
- [ ] `upsert_summary(run_id="nonexistent")` fails with `PROJECT_RESOLUTION_AMBIGUOUS`
- [ ] `upsert_summary(project_id="nonexistent")` fails with `PROJECT_NOT_FOUND`
- [ ] Only system-scoped writes may omit anchors (non-system → fail closed)
- [ ] Temporal backfills are marked `origin_source='temporal-backfill'`, `confidence='inferred'`
- [ ] No write path persists caller-supplied `project_id` directly (invariant test)

**Dependencies:** A1.6 (resolver must be in place before A3).

---

## Phase A4: Tests + Verification

**What:** Comprehensive test suite for new schema and write paths.

**Files:**
- Create: `tests/test_data_topology.py`

**Steps:**
1. **Orphan detection test:**
   ```python
   def test_no_orphaned_memory_entries():
       """Every memory_entry must have project_id."""
       orphans = store.db.execute(
           "SELECT COUNT(*) FROM memory_entries WHERE project_id IS NULL"
       ).fetchone()[0]
       assert orphans == 0, f"{orphans} orphaned entries"
   ```
2. **FK integrity test:** Every `source_run_id` points to existing `workflow_runs.id`
3. **entry_type distribution test:** No `diary` entries from non-Arc sources
4. **Write path test:** `upsert_summary()` with valid/invalid params
5. **Zombie table test:** Dropped tables don't exist
6. **FTS consistency test:** `memory_entries_fts` count matches `memory_entries` count

**Tests:**
- [ ] All 6 new tests pass
- [ ] All existing tests still pass (no regression)
- [ ] `python3 -m pytest tests/ -v` — full suite green

**Dependencies:** A1, A2, A3 complete.

---

## Phase A5: Production Wiring

**What:** Restart memory service, verify poller, run end-to-end upsert→recall flow.

**Files:**
- Modify: `memory_service/__main__.py` (if needed for new params)

**Steps:**
1. Run all migrations in order: 01 → 02 → 03 → 04 → 05 → 06
2. Restart memory service: `systemctl --user restart memory-service.service`
3. Verify health: `curl http://127.0.0.1:18096/health`
4. Trigger poller cycle: verify FTS indexes are consistent
5. End-to-end test:
   - Call `resolve_project("council")` → get project_id
   - Call `upsert_summary("test entry", source="inline-summary", run_id="review-...")` → verify anchored
   - Verify entry in `memory_entries` with correct `entry_type`, `project_id`, `source_run_id`
   - Call `recall.unified("test entry")` — verify it's found
   - Verify FTS search works: `memory_entries_fts MATCH 'test entry'`
6. Verify no regressions in existing recall paths

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] Memory service starts and responds to health check
- [ ] Poller runs without errors (check logs)
- [ ] FTS search returns results for new entries
- [ ] `recall.unified()` returns results from council_core.db
- [ ] All 167 existing entries have project_id set
- [ ] All existing tests still pass (no regression)
- [ ] No orphaned entries (project_id IS NOT NULL for all)
- [ ] Only system-scoped writes succeed without anchors (non-system → fail closed)
- [ ] Temporal backfills marked `origin_source='temporal-backfill'`, `confidence='inferred'`
- [ ] No write path persists caller-supplied `project_id` directly (invariant verified)
- [ ] Structured error payloads contain all fields: code, message, retryable, provided, resolved, candidates, suggested_action

**Dependencies:** A1–A4 complete.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations_council_core/04_drop_zombie_tables.sql` | DROP 14 deprecated tables |
| Create | `migrations_council_core/04b_add_constraints.sql` | UNIQUE indexes for G2, G4 |
| Create | `migrations_council_core/04c_workspace_bindings.sql` | workspace_bindings table + seed |
| Create | `migrations_council_core/05_fix_entry_types.sql` | Rename diary→summary, add consolidation |
| Create | `migrations_council_core/06_enforce_source_run_id.sql` | Add project_id, backfill, enforce FKs |
| Create | `memory_service/errors.py` | Typed exceptions + structured error payloads |
| Create | `tests/test_data_topology.py` | Orphan detection, FK integrity, write path tests |
| Create | `tests/test_relationalstore_guards.py` | Guard 1-11 unit tests |
| Modify | `memory_service/store.py` | CHECK constraint, new columns, _validate_project(), guards, resolver |
| Modify | `memory_service/mcp_server.py` | resolve_project() tool, new params, structured errors |
| Modify | `memory_service/__main__.py` | If CLI needs new params |

---

## Constraints

- **No data loss:** All 167 existing memory_entries must survive migration
- **FK enforcement:** No INSERT with invalid project_id or source_run_id
- **Resolver-first contract:** All write paths route through `resolve_project_from_context()` — no direct raw parameter validation
- **No caller-supplied project_id persisted:** Server stamps final `project_id` from resolution result; caller claims are inputs to verification only
- **System-scope exception:** Only explicitly declared system operations may map to "council" by default; all other writes fail closed on ambiguity
- **Temporal backfill is inferred:** `source_run_id` from temporal matching is marked `origin_source='temporal-backfill'`, `confidence='inferred'` — advisory, not authoritative
- **FTS consistency:** FTS indexes must match table counts after migration
- **memory.db deprecation:** No new writes to memory.db; reads from it return empty
- **Migration idempotency:** All SQL migrations must be safe to re-run

---

## Success Criteria

- [ ] 14 zombie tables dropped from both DBs
- [ ] `entry_type` correctly categorized (raw/summary/diary/consolidation)
- [ ] All 167 memory_entries have project_id set
- [ ] `upsert_summary()` resolves project from anchors, verifies caller claims, stamps canonical project_id, persists authoritative source_run_id only
- [ ] Zero orphaned entries (every row traceable to a project)
- [ ] FTS indexes consistent with table data
- [ ] Memory service starts, poller runs, health check passes
- [ ] End-to-end upsert→recall flow verified
- [ ] All existing tests pass (no regression)
- [ ] New test suite (6 tests) passes

---

## Caveats & Uncertainty

1. **source_run_id backfill is inferred, not authoritative** — temporal matching (nearest workflow_run by created_at) may produce incorrect links. All backfills are flagged as `origin_source='temporal-backfill'`, `confidence='inferred'`. They are advisory provenance, not authoritative truth. Future writes with real anchors supersede them.
2. **Arc pipeline not fixed in this handoff** — Option B covers Arc redirection. This handoff only fixes the foundation.
3. **memory.db not deleted** — deprecated but retained until Arc pipeline is fully migrated to council_core.
4. **sessions/notes/documents still unscoped** — Option B adds project_id to these tables. They remain global for now.
5. **No ON DELETE CASCADE added** — soft-delete (`is_deleted=1`) is the current policy. Adding CASCADE would be a separate decision.
6. **Resolver-first is mandatory** — A1.6 is the write contract for all later phases. No write path may bypass `resolve_project_from_context()`. Direct raw parameter validation is prohibited.

---

## Options for Next Phase (Option B — Full Topology)

If Option A validates successfully, the next handoff would cover:

1. **Add project_id to sessions, notes, documents, memory_rollups, cg_*** tables
2. **Redirect Arc pipeline** to write to `council_core.memory_rollups` and `council_core.consolidation_cache`
3. **Add ON DELETE CASCADE** or formalize soft-delete policy
4. **Unify ID naming** (document `run_id` vs `source_run_id` convention)
5. **Full integration test** across project→work→run→entry chain

**Estimated effort:** ~6 hours across 4 phases.

---

## Revisit When

- Table count in council_core exceeds 30
- Row count exceeds 100K (reconsider Option C — nuclear rebuild)
- Multi-user/multi-tenant requirements emerge
- Arc pipeline is reactivated (triggers Option B)
