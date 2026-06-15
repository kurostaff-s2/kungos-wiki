# Projects & Work Tables — Wiring Handoff

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `16-06-2026_projects-work-tables-wiring_95339e` |
| Entity type | `handoff` |
| Short description | Wire orphaned `plan_deviations` + `plan_deviations_events` tables to API and frontend; audit remaining gaps in Projects & Work domain |
| Status | `draft` |
| Source references | This session (recall trace-0c9f9358, 2026-06-16) |
| Generated | 16-06-2026 |
| Next action / owner | Review → approve/reject → execute Phase 1 (API routes) |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`

**Key files for this task:**

| File | Role |
|------|------|
| `api/core.py` | `RESOURCE_MAP` — add deviation routes |
| `api/core.py` | `CouncilCoreAPI` class — generic CRUD handles new resources automatically |
| `frontend/shared/council-types.ts` | TypeScript types — add `PlanDeviation`, `PlanDeviationEvent` |
| `frontend/packages/web-core/src/shared/hooks/council/useCouncilWorkItems.ts` | Pattern to mirror for `useCouncilDeviations` |
| `frontend/packages/web-core/src/pages/kanban/CouncilKanbanContainer.tsx` | Kanban board — add deviation badge/panel |
| `memory_service/reconcile/reconciler.py` | Writes to `plan_deviations` (34 rows, write-only) |
| `memory_service/store/relational_store.py` | `get_deviations()`, `resolve_project()` — existing store methods |

**Database:** `~/.council-memory/council_core.db` (SQLite dev, PostgreSQL production)

**Related codebases:** None (self-contained within super_council)

---

## Problem Statement

The `plan_deviations` (34 rows) and `plan_deviations_events` (38 rows) tables are **write-only from the ArcReconciler**. No API route, no frontend hook, no UI surface. A human or agent cannot inspect, filter, search, or act on deviations through any interface.

### Current State

| Table | Rows | API | Frontend | Data Flow |
|-------|------|-----|----------|-----------|
| `projects` | 3 | ✓ CRUD | ✓ (org-level, sunsetted) | Full |
| `work_items` | 4 | ✓ CRUD | ✓ kanban | Full |
| `plan_deviations` | 34 | ✗ | ✗ | Write-only (reconciler) |
| `plan_deviations_events` | 38 | ✗ | ✗ | Write-only (reconciler) |
| `phase_names` | 11 | ✗ (MCP only) | ✗ | Pipeline-only, not kanban |

### Architecture Context

- **Two phase systems exist and are NOT the same:**
  - `phase_names` (11 rows) = Council pipeline execution phases (SCOUT → PLAN → BUILD → ... → DONE/FAILED). Used by `pipelines` and `state_executions`.
  - `work_items.phase` (free-text) = Kanban column position. Frontend hardcodes 6 phases (`DEFAULT_KANBAN_PHASES`). No FK to `phase_names`.
- **The `CouncilCoreAPI` is generic:** Adding a resource to `RESOURCE_MAP` automatically registers POST/GET/PATCH/command routes. No per-resource handler code needed.
- **`ProjectKanban` is dead code** (zero imports). `CouncilKanbanContainer` (via `LocalProjectKanban`) is the active kanban board.

---

## Phase 1: API Routes for Deviations

**What:** Add `plan_deviations` and `plan_deviations_events` to the API so they're readable and writable via the existing generic CRUD.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `api/core.py` | Add two entries to `RESOURCE_MAP` |

**Steps:**

1. In `api/core.py`, add to `RESOURCE_MAP`:
   ```python
   "plan-deviations": {"table": "plan_deviations", "entity_type": "plan_deviation"},
   "plan-deviation-events": {"table": "plan_deviations_events", "entity_type": "plan_deviation_event"},
   ```
2. Verify routes register: `GET /v1/plan-deviations`, `GET /v1/plan-deviations/{id}`, `POST /v1/plan-deviations`, `PATCH /v1/plan-deviations/{id}`, same for events.
3. Verify the generic CRUD handles the table columns correctly (no schema changes needed — table already has `revision`, `is_deleted`, `updated_at`, etc.).

**Tests:**
- `GET /v1/plan-deviations` returns 34 items (or current count)
- `GET /v1/plan-deviations/{id}` returns single deviation
- `POST /v1/plan-deviations` creates new deviation with auto-generated `id`, `revision=1`
- `PATCH /v1/plan-deviations/{id}` updates fields with revision check
- `GET /v1/plan-deviation-events` returns 38 items
- Existing `work-items` routes still work (no regression)

**Dependencies:** None

---

## Phase 2: Frontend Types + Hooks

**What:** TypeScript types and React Query hooks for deviations, mirroring the work items pattern.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `frontend/shared/council-types.ts` | Add `PlanDeviation`, `PlanDeviationEvent` types |
| Create | `frontend/packages/web-core/src/shared/hooks/council/useCouncilDeviations.ts` | Fetch + mutate deviations |
| Modify | `frontend/packages/web-core/src/shared/hooks/council/index.ts` | Export new hooks |

**Steps:**

1. In `council-types.ts`, add types matching the `plan_deviations` schema:
   ```typescript
   export interface PlanDeviation {
     id: string;
     project_id: string;
     work_item_id: string | null;
     deviation_type: string;  // "planned" | "unplanned"
     severity: string;
     title: string;
     description: string | null;
     original_expectation: string | null;
     actual_implementation: string | null;
     rationale: string | null;
     status: string;  // "proposed" | "approved" | "implemented" | "closed" | "rejected"
     confidence: number | null;
     created_at: string;
     updated_at: string;
     closed_at: string | null;
     is_deleted: number;
     // ... remaining columns
   }
   ```
2. Create `useCouncilDeviations.ts` mirroring `useCouncilWorkItems.ts`:
   - `useCouncilDeviations(projectId?)` — fetch all, filter by project client-side
   - `useCreateDeviation()` — POST mutation
   - `useUpdateDeviation()` — PATCH mutation with revision handling
3. Export from `index.ts`.

**Tests:**
- Types compile without errors
- Hook fetches deviations and filters by `project_id`
- Create mutation succeeds with proper idempotency headers
- Update mutation handles revision correctly

**Dependencies:** Phase 1 (API routes must exist)

---

## Phase 3: Deviation Surface in Kanban

**What:** Make deviations visible in the UI. Two options — pick one during execution.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `frontend/packages/web-core/src/pages/kanban/CouncilKanbanContainer.tsx` | Add deviation badge to work item cards |
| Modify | `frontend/packages/ui/src/components/KanbanCardContent.tsx` | Accept deviation count prop |

**Option A — Badge on work item cards (minimal):**
- Count deviations per `work_item_id`
- Render a small badge (e.g., triangle icon + count) on cards that have deviations
- Click badge → expand inline deviation list or open side panel

**Option B — Separate deviations panel (more surface):**
- Add a toggle/tab in `CouncilKanbanContainer` header: "Board" | "Deviations"
- Deviations view: table/list of deviations for the project, filterable by type/severity/status
- Click deviation → detail panel (similar to work item detail)

**Recommendation:** Option A first (badge), Option B as follow-up if deviations are frequently inspected.

**Steps (Option A):**
1. In `CouncilKanbanContainer`, fetch deviations alongside work items
2. Build a `Map<work_item_id, deviation[]>` lookup
3. Pass deviation count to `KanbanCard` rendering
4. Render badge when count > 0

**Tests:**
- Cards with deviations show badge
- Cards without deviations show no badge
- Badge count matches actual deviation count for that work item
- No performance regression (34 deviations is small; verify with 100+ if scaled)

**Dependencies:** Phase 2 (hooks must exist)

---

## Phase 4: Dead Code Cleanup

**What:** Remove `ProjectKanban.tsx` and `ProjectSunsetPage.tsx` — zero imports, fully replaced by `LocalProjectKanban` → `CouncilKanbanContainer`.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Delete | `frontend/packages/web-core/src/pages/kanban/ProjectKanban.tsx` | Dead code |
| Delete | `frontend/packages/web-core/src/pages/kanban/ProjectSunsetPage.tsx` | Dead code |

**Steps:**
1. Confirm zero imports: `grep -rn "ProjectKanban\|ProjectSunsetPage" frontend/` (should only find self-references)
2. Delete both files
3. Verify no build errors

**Tests:**
- Frontend builds without errors
- Kanban board still renders at `/projects/$projectId`
- No console errors for missing imports

**Dependencies:** None (can run in parallel with Phases 1-3)

---

## Execution Order

```
Phase 1 (API routes) ──→ Phase 2 (types + hooks) ──→ Phase 3 (kanban UI)
                                              ↗
Phase 4 (dead code cleanup) ────────────────────────┘  (independent, can run anytime)
```

- **Phases 1→2→3** are sequential (each depends on prior)
- **Phase 4** is independent — can run in parallel with any phase

---

## Constraints

- **No schema changes to `plan_deviations` or `plan_deviations_events`.** Tables are production-ready with revision, is_deleted, updated_at columns.
- **No FK constraint between `work_items.phase` and `phase_names`.** They are different systems (kanban columns vs pipeline phases). Adding a FK would be incorrect.
- **Preserve existing `work_items` wiring.** No changes to `DEFAULT_KANBAN_PHASES`, `resolvePhase()`, or `CouncilKanbanContainer` kanban logic unless explicitly scoped.
- **API must use existing generic CRUD.** Do not write per-resource handlers. The `CouncilCoreAPI` class handles all resources uniformly via `RESOURCE_MAP`.
- **Deviations UI must not block kanban rendering.** If deviation fetch fails, kanban still renders (graceful degradation).

---

## Success Criteria

- [ ] `GET /v1/plan-deviations` returns all deviations (34 rows)
- [ ] `GET /v1/plan-deviations?project_id=X` filters by project (via client-side or query param)
- [ ] `GET /v1/plan-deviation-events` returns all events (38 rows)
- [ ] `POST /v1/plan-deviations` creates deviation with idempotency
- [ ] `PATCH /v1/plan-deviations/{id}` updates with revision check
- [ ] Frontend types compile without errors
- [ ] `useCouncilDeviations` hook fetches and filters correctly
- [ ] Deviations visible in kanban UI (badge or panel)
- [ ] `ProjectKanban.tsx` and `ProjectSunsetPage.tsx` deleted
- [ ] Frontend builds without errors
- [ ] All existing tests pass (no regression)
- [ ] Kanban board renders at `/projects/$projectId` with deviations visible

---

## Caveats & Uncertainty

1. **`plan_deviations` has no `is_deleted` soft-delete in the same pattern as `work_items`.** The table has `status` (proposed/approved/implemented/closed/rejected) but may not have `is_deleted`. Verify before assuming the generic CRUD's soft-delete logic applies. If missing, the generic DELETE may not work — deviations would need hard delete or the table needs the column.

2. **`plan_deviations_events` references `deviation_id` but has no `is_deleted`.** Same concern as above.

3. **The reconciler writes deviations directly to DB** (bypassing API). After wiring the API, the reconciler should ideally use the API for consistency, but that's a follow-up — not blocking for this handoff.

4. **Deviation count per work item:** With 34 deviations and 4 work items, the lookup is trivial. At scale (1000s of deviations), consider server-side aggregation instead of client-side Map construction.

5. **`phase_names` remains MCP-only.** No frontend wiring planned — it's pipeline-internal. If a future feature needs pipeline phase visibility, that's a separate handoff.

---

## Review Questions

Before execution, confirm:

1. **Deviation UI surface:** Badge on cards (Option A) or separate panel (Option B)? Recommendation: A first, B later.
2. **`is_deleted` column:** Does `plan_deviations` need it for soft-delete consistency? Or is `status='closed'` sufficient?
3. **Reconciler API migration:** Should the reconciler use the new API routes instead of direct DB writes? (Recommendation: follow-up, not this handoff.)
4. **Phase 4 timing:** Delete dead code now or after kanban changes are stable? (Recommendation: now — it's independent.)
