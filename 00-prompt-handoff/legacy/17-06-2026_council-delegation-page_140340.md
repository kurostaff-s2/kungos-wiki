# Council Delegation Runs Page — Execution Handoff

| Field | Value |
|-------|-------|
| Project ID | `super-council` + `kteam-fe-chief` |
| Primary entity ID | `deleg-page-140340` |
| Entity type | `handoff` |
| Short description | Fix delegation DB tracking bug, add delegation_runs table, backfill 236 historical records, build frontend page |
| Status | `draft` |
| Source references | `/home/chief/Coding-Projects/kteam-fe-chief/docs/plans/council-delegation-page.md` |
| Generated | `17-06-2026` |
| Next action / owner | Execute Unit 0 (bug fix + schema) → pick up phase doc `p0-schema.md` |

## Project Context

**Project root (backend):** `/home/chief/Coding-Projects/7-council/super_council/`
**Project root (frontend):** `/home/chief/Coding-Projects/kteam-fe-chief/`
**Reference docs:** `/home/chief/Coding-Projects/kteam-fe-chief/docs/plans/council-delegation-page.md`
**Key files for this task:** See per-phase handoff docs below
**Related codebases:** Both projects (backend API + frontend React)

## Summary

Council delegation runs (model-to-model task delegation) are saved to filesystem MD files but NOT persisted to `council_core.db`. The DB write path is broken: `self.transition_to()` is called on `SlotSupervisor` but the method lives on `PipelineState`. This handoff fixes the bug, adds a `delegation_runs` table with delegation-specific metadata, backfills the 236 historical delegations, and builds a frontend page to browse them.

## Execution Order

```
Unit 0 (schema + bug fix) ──→ Unit 2 (backfill migration) ──→ Unit 1 (API endpoints) ──→ Unit 3 (frontend list)
                                                                         └──→ Unit 4 (sidebar + route) [parallel with Unit 3]
                                                                         └──→ Unit 5 (detail view) [after Unit 3]
```

## Phase Handoffs

| Phase | File | Description | Dependencies |
|-------|------|-------------|--------------|
| Unit 0 | `p0-schema-bugfix.md` | Bug fix + delegation_runs table + RelationalStore methods | none |
| Unit 1 | `p1-api-endpoints.md` | Backend API: list, detail, raw endpoints | Unit 0 |
| Unit 2 | `p2-backfill-migration.md` | Backfill 236 historical delegations from MD files | Unit 0 |
| Unit 3 | `p3-frontend-list.md` | Frontend list view (table, search, pagination) | Unit 1 |
| Unit 4 | `p4-sidebar-route.md` | Sidebar nav + route registration | none (parallel) |
| Unit 5 | `p5-frontend-detail.md` | Detail view + MD file link | Unit 3 |

## File Map (All Units)

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/migrations_council_core/08_delegation_runs.sql` | Schema migration |
| Create | `super_council/memory_service/store/delegation.py` | DelegationStoreMixin |
| Create | `super_council/api/council_delegations.py` | API endpoints |
| Create | `super_council/scripts/backfill_delegations.py` | Migration script |
| Create | `super_council/tests/test_delegation_runs.py` | Unit tests |
| Create | `kteam-fe-chief/src/pages/Council/Delegations.jsx` | List page |
| Create | `kteam-fe-chief/src/pages/Council/DelegationDetail.jsx` | Detail page |
| Modify | `super_council/council_main.py` | Fix `self.transition_to()` → `ps.transition_to()` + wire `insert_delegation()` |
| Modify | `super_council/memory_service/store/relational_store.py` | Import DelegationStoreMixin |
| Modify | `super_council/server.py` | Mount delegation routes |
| Modify | `kteam-fe-chief/src/routes/main.jsx` | Register `/council/delegations` route |
| Modify | `kteam-fe-chief/src/data/sidebar-nav.js` | Add Council section |

## Constraints

- **DB-primary:** All new delegations must be written to `delegation_runs` table. Filesystem MD files are artifacts only.
- **No auth:** Endpoints are unauthenticated (confirmed by user).
- **From model inference:** Historical delegations without supervisor log correlation get `from_model = 'unknown'`. Future delegations write from_model directly.
- **Idempotent migration:** Backfill script skips rows where `chain_id` already exists.
- **Follow existing patterns:** RelationalStore mixins, migration SQL format, frontend DataTable components.
- **TDD:** Tests before implementation. RED → GREEN → REFACTOR.

## Success Criteria

- [ ] `self.transition_to()` bug fixed (no more `'SlotSupervisor' object has no attribute 'transition_to'` errors)
- [ ] `delegation_runs` table exists with correct schema
- [ ] 236 historical delegations backfilled (run backfill script once)
- [ ] Future delegations automatically written to DB
- [ ] API returns delegation list with pagination, search, filters
- [ ] Frontend page displays delegation data in table
- [ ] Detail view shows full task + response
- [ ] "Open MD" link opens raw file in new tab
- [ ] All existing tests still pass (no regression)

## Post-Wiring Verification

- [ ] Trigger a delegation → `SELECT * FROM delegation_runs ORDER BY id DESC LIMIT 1` shows the record
- [ ] Frontend page loads at `/council/delegations` with delegation data
- [ ] Search by model name filters results
- [ ] Click delegation row → detail view with full task + response
- [ ] "Open MD" button opens raw file
