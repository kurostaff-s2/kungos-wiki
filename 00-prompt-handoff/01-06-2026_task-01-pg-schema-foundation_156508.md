# Task 01: PostgreSQL Schema Foundation

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §5, §11
**Generated:** 01-06-2026
**Goal:** Create all PostgreSQL schemas, tables, indexes, and role privileges for the Council ↔ AppFlowy integration.

---

## Scope

Pure database work. No application code. Produces a runnable PostgreSQL instance with correct schemas, constraints, and privilege boundaries.

---

### Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations_pg/001_create_schemas_and_roles.sql` | Role creation + schema ownership + privilege isolation |
| Create | `migrations_pg/002_core_tables.sql` | All `council_core` tables with exact DDL from spec §5.2 |
| Create | `migrations_pg/003_ops_tables.sql` | All `council_ops` tables from spec §5.3 |
| Create | `migrations_pg/004_sync_tables.sql` | All `council_sync` tables from spec §5.4 |
| Create | `migrations_pg/005_indexes.sql` | All indexes from spec |
| Create | `tests/db/test_schema_migration.py` | Migration execution tests |
| Create | `tests/db/test_constraints.py` | Constraint verification tests |
| Create | `tests/db/test_privileges.py` | Privilege boundary tests |

---

### Steps

1. **Role creation:** Write SQL to create `council_app` role with `LOGIN PASSWORD '{{COUNCIL_DB_PASSWORD}}'`.
2. **Schema ownership:** Create `council_core`, `council_ops`, `council_sync` schemas with `AUTHORIZATION council_app`.
3. **Privilege isolation:** `REVOKE ALL ON SCHEMA appflowy_* FROM council_app`; `GRANT USAGE` + `GRANT SELECT` only.
4. **Core tables:** Transcribe every DDL from §5.2 exactly. Verify each table has all base columns from §5.1.
5. **Ops tables:** Transcribe every DDL from §5.3. Confirm no revision columns (intentional per §5.3 clarification).
6. **Sync tables:** Transcribe every DDL from §5.4 including `UNIQUE` constraints on `outbox_events`.
7. **Indexes:** Create all indexes from spec. Verify `USING GIN` syntax on array columns.
8. **Run migration:** Execute against a fresh PostgreSQL 15+ instance (Docker or local).
9. **Verify constraints:** Test every `CHECK` constraint with invalid input. Test every `UNIQUE` constraint with duplicate input.

---

### Constraints

- Use exact DDL from spec — no column additions or omissions.
- `status` CHECK constraints must be `('active','archived')` on all tables except `prompt_templates` which allows `('active','draft','archived')`.
- `outbox_events` MUST have `UNIQUE (entity_type, council_id, mutation_type, payload_revision)`.
- No plaintext passwords — use `{{COUNCIL_DB_PASSWORD}}` placeholder.
- `council_ops` tables intentionally omit revision-based columns.

---

### Success Criteria

- [ ] All 3 schemas created with correct `AUTHORIZATION`
- [ ] All `council_core` tables created with every base column from §5.1
- [ ] All `CHECK` constraints enforce correct value sets
- [ ] `UNIQUE` constraint on `outbox_events` prevents duplicate mutations at same revision
- [ ] `council_app` cannot write to `appflowy_*` schemas
- [ ] `memory_rollups` has `origin_source` AND `is_deleted` columns
- [ ] All indexes created successfully
- [ ] Migration is idempotent (safe to re-run)

---

### Tests

1. **Schema existence:** Connect as `council_app` → `SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'council_%'` → assert 3 schemas.
2. **Base column audit:** For each `council_core` table, query `information_schema.columns` → assert all base columns present (`id`, `external_key`, `revision`, `created_at`, `updated_at`, `updated_by`, `updated_source`, `origin_source`, `status`, `is_deleted`).
3. **Status constraint:** `INSERT INTO council_core.work_items (...) VALUES (..., status='blocked', ...)` → assert `CHECK` violation.
4. **Outbox uniqueness:** Insert two rows with same `(entity_type, council_id, mutation_type, payload_revision)` → assert `UNIQUE` violation.
5. **Privilege isolation:** `INSERT INTO appflowy_public.some_table ...` as `council_app` → assert `PERMISSION DENIED`.
6. **FK cascade:** Delete `work_items` row → assert `workflow_runs` FK violation (or cascade if defined).

---

### Dependencies

None. This is the foundation task.
