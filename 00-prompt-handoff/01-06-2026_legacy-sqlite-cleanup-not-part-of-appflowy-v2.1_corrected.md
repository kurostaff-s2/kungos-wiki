# Legacy SQLite Cleanup and Decoupling (Not Part of AppFlowy Integration v2.1)

**Source context:** Corrected replacement for the misaligned prompt `01-06-2026_db-split-schema-simplify-review-streamline_2a0e10-2.md`  
**Generated:** 01-06-2026  
**Status:** Explicitly separated from AppFlowy Integration v2.1  
**Goal:** Preserve useful legacy cleanup work as an optional, out-of-band migration stream without mixing it into the PostgreSQL/AppFlowy v2.1 execution plan.

---

## Scope

This document is **not** part of the AppFlowy v2.1 implementation stream.

It captures optional cleanup work for the legacy SQLite-based subsystem so it can be scheduled separately, either before decommissioning SQLite or during archival/refactoring.

---

## Why this replacement exists

The original prompt mixed SQLite-specific changes with the PostgreSQL/AppFlowy v2.1 rollout.

That is a scope error because v2.1 is explicitly a PostgreSQL-based execution contract with no backward SQLite compatibility requirement.

This corrected document keeps the legacy cleanup ideas available while preventing accidental coupling to the AppFlowy integration program.

---

## Relationship to v2.1

### In scope for AppFlowy v2.1

- `council_core`, `council_ops`, `council_sync` PostgreSQL schemas
- Council Core API as sole canonical write path
- transactional outbox
- revision-aware inbound sync
- binding lifecycle
- AppFlowy REST-only integration

### Out of scope for AppFlowy v2.1

- refactoring SQLite `pipelines.db` as a production persistence layer
- codegraph split as a dependency of the AppFlowy integration rollout
- renaming SQLite memory tables as part of the AppFlowy integration critical path
- review-streamlining work implemented only in legacy SQLite storage
- work-item redesign that bypasses the v2.1 PostgreSQL schema contract

---

## Optional Legacy Cleanup Workstreams

### Workstream A — CodeGraph DB split

**Goal:** Move `cg_*` tables to `codegraph.db` for cleaner separation from legacy operational data.

**Deliverables:**

- `codegraph.db` with copied `cg_nodes`, `cg_edges`, `cg_files`, and FTS tables
- updated codegraph config paths
- verification that tooling reads from `codegraph.db`

**Condition:** Do this only if the legacy SQLite subsystem must remain operational during or after v2.1 rollout.

### Workstream B — SQLite memory-table naming cleanup

**Goal:** Rename legacy tables for clarity if the old subsystem is still supported temporarily.

**Examples:**

- `session_diary` → `working_memory`
- `consolidation_cache` → `long_term_memory`

**Condition:** Optional only. Do not block v2.1 on this.

### Workstream C — SQLite enum simplification

**Goal:** Replace legacy enum tables with `CHECK` constraints in SQLite if that subsystem continues to run.

**Condition:** Optional only. Not required by AppFlowy v2.1.

### Workstream D — Legacy review-service cleanup

**Goal:** Simplify old SQLite review tracking if the legacy service must remain available during transition.

**Condition:** If the v2.1 PostgreSQL review model is being implemented, prefer finishing that instead of extending the legacy review path.

---

## Scheduling Guidance

Use this document only in one of these cases:

1. You need a short-lived bridge while SQLite still serves some local workflows.
2. You want to archive the old subsystem cleanly before removal.
3. You want to keep CodeGraph operational but separate from legacy pipeline storage.

Do **not** schedule these tasks as blockers for Tasks 01 through 08 of the AppFlowy v2.1 program.

---

## Decision Rules

- If a task changes PostgreSQL `council_*` schemas or Council Core API behavior, it belongs to AppFlowy v2.1.
- If a task only changes SQLite `pipelines.db`, legacy codegraph storage, or old memory-service table names, it belongs here.
- If a task affects both, split it into two independently schedulable prompts.

---

## Success Criteria

- [ ] Legacy cleanup work is clearly separated from AppFlowy v2.1.
- [ ] No SQLite-only task is treated as a prerequisite for the PostgreSQL/AppFlowy rollout.
- [ ] Any retained legacy workstream has its own schedule, owner, and shutdown decision.
- [ ] CodeGraph split, if desired, is executed as an independent change.

---

## Dependencies

None for AppFlowy v2.1.

These workstreams are optional and independently schedulable.
