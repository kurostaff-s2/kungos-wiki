# Execution Prompt: AppFlowy Integration v2.1

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md`
**Generated:** 01-06-2026 by pi task-handoff
**Goal:** Implement the Council ↔ AppFlowy bidirectional integration with PostgreSQL schemas, outbox-driven projection, revision-aware inbound sync, and binding lifecycle management.

---

## Context

Current state: Council runs on SQLite (`RelationalStore` in `super_council/memory_service/store.py`). AppFlowy bridge exists (`council_appflowy_bridge.py`) with basic push/pull but no outbox pattern, no revision concurrency, no binding table, and no field-level editability.

Target state: PostgreSQL cluster with strict schema ownership (`council_core`, `council_ops`, `council_sync`), Council Core API as sole canonical write boundary, transactional outbox for outbound projection, revision-aware inbound sync with allowlist enforcement, and persisted binding lifecycle.

---

### Phase 1: PostgreSQL Schema Foundation

**What:** Create all PostgreSQL schemas and tables per §5 of the spec. Replace SQLite `RelationalStore` with PostgreSQL-backed `CouncilDatabase`.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/council_db/schema.py` | SQLAlchemy base + all `council_core` models |
| Create | `super_council/council_db/ops_models.py` | All `council_ops` models |
| Create | `super_council/council_db/sync_models.py` | All `council_sync` models |
| Create | `super_council/council_db/engine.py` | Engine creation, schema autogeneration, role setup |
| Create | `migrations_pg/001_create_schemas.sql` | Raw SQL for schema + role creation |
| Create | `migrations_pg/002_core_tables.sql` | All `council_core` table DDL |
| Create | `migrations_pg/003_ops_tables.sql` | All `council_ops` table DDL |
| Create | `migrations_pg/004_sync_tables.sql` | All `council_sync` table DDL |
| Modify | `super_council/memory_service/store.py` | Add PostgreSQL compatibility layer or deprecate path |

**Steps:**

1. Create `council_app` PostgreSQL role with schema ownership per §11.3.
2. Create `council_core`, `council_ops`, `council_sync` schemas with `AUTHORIZATION council_app`.
3. Revoke all write access to `appflowy_*` schemas for `council_app`.
4. Implement all `council_core` models as SQLAlchemy declarative classes with exact columns from §5.2 DDL.
5. Implement all `council_ops` models (no revision columns per §5.3 clarification).
6. Implement all `council_sync` models with exact constraints from §5.4 DDL.
7. Create engine factory that reads `DATABASE_URL` from environment.
8. Run schema migration against a test PostgreSQL instance.
9. Verify all CHECK constraints, UNIQUE constraints, and FK relationships.

**Tests:**

1. **Schema creation:** Run migration → assert all schemas exist with correct ownership.
2. **Base column contract:** Insert row into each `council_core` table with minimal fields → assert all base columns populated with correct defaults.
3. **Status constraint:** Attempt `INSERT` with `status='blocked'` into `work_items` → assert `CHECK` violation.
4. **Outbox uniqueness:** Insert two `outbox_events` with same `(entity_type, council_id, mutation_type, payload_revision)` → assert `UNIQUE` violation.
5. **Privilege isolation:** Attempt `INSERT` into `appflowy_public` as `council_app` → assert `PERMISSION DENIED`.

**Dependencies:** None.

---

### Phase 2: Council Core API

**What:** Implement the canonical write boundary with revision-aware mutations and idempotency.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/api/core.py` | CouncilCoreAPI with POST/GET/PATCH/command endpoints |
| Create | `super_council/api/idempotency.py` | Idempotency-Key store and validation |
| Create | `super_council/api/revision.py` | Revision-based concurrency helpers |
| Create | `super_council/api/middleware.py` | X-Source-System, X-Actor-Id header extraction |
| Create | `tests/test_core_api.py` | API endpoint tests |
| Create | `tests/test_idempotency.py` | Idempotency-Key tests |

**Steps:**

1. Implement `CouncilCoreAPI` class with resource routing for all `council_core` entities.
2. Implement `POST /v1/<resource>` with `Idempotency-Key` enforcement and outbox event generation.
3. Implement `PATCH /v1/<resource>/{id}` with `expected_revision` check, `Idempotency-Key`, and field-level allowlist enforcement.
4. Implement `POST /v1/<resource>/{id}/commands/<cmd>` for non-CRUD transitions.
5. Implement `GET /v1/<resource>/{id}` for canonical state fetch.
6. Implement `GET /v1/<resource>?updated_since=...` for sync/export.
7. Enforce `X-Source-System` and `X-Actor-Id` headers on all writes.
8. Return `409` on stale `expected_revision`, `403` on forbidden field edit.
9. Atomic transaction: canonical row update + outbox event INSERT in one `BEGIN...COMMIT`.

**Tests:**

1. **Create with idempotency:** POST with same `Idempotency-Key` twice → assert same entity returned, only one row created.
2. **Revision check:** PATCH with stale `expected_revision` → assert `409`.
3. **Field allowlist:** PATCH `kind` field from `X-Source-System: appflowy` → assert `403`.
4. **Transactional outbox:** PATCH entity → assert exactly one `outbox_events` row with correct `payload_revision`.
5. **Source tracking:** PATCH with `X-Source-System: appflowy` → assert `updated_source='appflowy'` on entity.

**Dependencies:** Phase 1 (schemas must exist).

---

### Phase 3: Outbox Dispatcher & Binding Lifecycle

**What:** Implement outbound projection from Council to AppFlowy with binding management.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/workers/outbox.py` | OutboxDispatcher worker |
| Create | `super_council/workers/binding_manager.py` | Binding lifecycle logic |
| Modify | `super_council/appflowy_sync.py` | Add binding-aware push methods |
| Create | `tests/test_outbox_dispatcher.py` | Outbox delivery tests |
| Create | `tests/test_binding_lifecycle.py` | Binding creation/orphan tests |

**Steps:**

1. Implement `OutboxDispatcher.select_pending()` with `FOR UPDATE SKIP LOCKED`.
2. Implement binding resolution: lookup `appflowy_bindings` by `(entity_type, council_id)`.
3. Implement auto-projection: if binding missing and auto-projection enabled, create AppFlowy row via REST API, capture `appflowy_row_id`, store binding.
4. Implement outbound delivery: call AppFlowy REST `PUT` to update row cells.
5. Implement success path: set `delivery_state='sent'`, update `binding.last_synced_revision`.
6. Implement failure path: increment `attempts`, exponential backoff (2s, 4s, 8s), move to `dead_letter` after 3 failures.
7. Implement orphaned binding detection: periodic scan for inaccessible AppFlowy rows → mark `state='orphaned'`.
8. Integrate with `CouncilCoreAPI` so every canonical write triggers an outbox event.

**Tests:**

1. **Outbox delivery:** Seed pending outbox event + binding → run dispatcher → assert `delivery_state='sent'`.
2. **Auto-projection:** Seed outbox event without binding → run dispatcher → assert binding created with valid `appflowy_row_id`.
3. **Retry backoff:** Mock AppFlowy failure → assert 3 attempts with 2s/4s/8s delays → assert `dead_letter`.
4. **Orphaned detection:** Mock AppFlowy row deletion → run scan → assert binding marked `orphaned`.
5. **Idempotent delivery:** Run dispatcher twice on same event → assert no duplicate AppFlowy API calls (event already `sent`).

**Dependencies:** Phase 2 (Council Core API must generate outbox events).

---

### Phase 4: Inbound Sync with Revision Awareness

**What:** Implement AppFlowy → Council inbound sync with field allowlist, SHA-256 snapshot hashing, and revision-aware PATCH.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/workers/inbound.py` | AppFlowyInboundSync worker |
| Create | `super_council/workers/snapshot_hash.py` | SHA-256 canonical JSON hashing |
| Modify | `super_council/appflowy_sync.py` | Add polling methods for row-updated endpoint |
| Create | `tests/test_inbound_sync.py` | Inbound change detection tests |
| Create | `tests/test_snapshot_hash.py` | Hash computation tests |

**Steps:**

1. Implement snapshot hash: SHA-256 over canonical JSON (sorted keys, no whitespace, stable array order, nulls preserved, UTF-8).
2. Implement polling: call AppFlowy `/api/workspace/{ws}/database/{db}/row/updated` endpoint.
3. Implement change detection: fetch full row detail → compute snapshot hash → compare with `binding.last_seen_cells_hash` → skip if unchanged.
4. Implement field allowlist enforcement per §10.1 `FIELD_ALLOWLIST` dict.
5. Implement mapping transform: AppFlowy cell values → Council field values.
6. Implement revision-aware PATCH: fetch canonical entity → verify `expected_revision` → PATCH via Council Core API.
7. Implement result recording: INSERT into `inbound_changes` with state `applied`/`rejected`/`skipped`.
8. Implement `last_seen_cells_hash` persistence after successful processing.
9. Implement restart safety: read `last_seen_cells_hash` from DB on worker start, not from process memory.

**Tests:**

1. **Hash consistency:** Same cell payload → same SHA-256 hash (deterministic).
2. **Hash sensitivity:** Change one cell value → different hash.
3. **Allowlist enforcement:** AppFlowy edit to forbidden field → assert `rejected` in `inbound_changes`.
4. **Revision check:** Stale `expected_revision` from AppFlowy → assert `409` from Council Core API.
5. **Restart safety:** Kill worker mid-poll → restart → assert no duplicate processing (hash persisted in DB).
6. **Knowledge card sync:** Edit `title` in AppFlowy → assert applied; edit `confidence` → assert rejected.

**Dependencies:** Phase 2 (Council Core API must accept PATCH with `expected_revision`).

---

### Phase 5: Knowledge Card Integration

**What:** Wire knowledge cards through the full bidirectional flow (schema, API, field policy, AppFlowy mapping).

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/api/core.py` | Add knowledge_cards resource endpoints |
| Modify | `super_council/workers/outbox.py` | Add knowledge_cards projection |
| Modify | `super_council/workers/inbound.py` | Add knowledge_cards to `FIELD_ALLOWLIST` |
| Modify | `super_council/appflowy_sync.py` | Add `push_knowledge_card` with field mapping |

**Steps:**

1. Add `knowledge_cards` to Council Core API resource routing.
2. Add knowledge cards field policy to PATCH allowlist: `title`, `body`, `tags` editable from AppFlowy; `confidence`, `source_run_id`, `metadata`, `topic`, `status` Council-only.
3. Implement outbound projection: map Council fields → AppFlowy columns per §8.5.
4. Implement inbound sync: enforce allowlist for knowledge cards.
5. Verify consistency: allowlist (§10.1) == field policy (§7.5) == field mapping (§8.5).

**Tests:**

1. **Field policy match:** Assert `FIELD_ALLOWLIST["knowledge_card"]` == fields marked "Yes" in §7.5 knowledge cards policy table.
2. **Outbound projection:** Create knowledge card → assert AppFlowy row with correct field mapping.
3. **Inbound edit:** Edit `title` in AppFlowy → assert applied; edit `confidence` → assert rejected.

**Dependencies:** Phase 2, 3, 4 (API, outbox, inbound must exist).

---

### Phase 6: Hardening & Operational Readiness

**What:** Dead-letter inspection, operational dashboards, retry metrics, restart safety verification.

**Files:**

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/api/dead_letter.py` | Dead-letter inspection endpoint |
| Create | `super_council/workers/orphan_scanner.py` | Orphaned binding detection |
| Create | `super_council/workers/metrics.py` | Retry and alert metrics |
| Create | `tests/test_restart_safety.py` | Full restart safety integration tests |

**Steps:**

1. Implement dead-letter inspection: `GET /v1/sync/dead-letter` returning failed outbox events.
2. Implement orphaned binding scanner: periodic job that checks binding validity and marks `orphaned`.
3. Implement retry metrics: track delivery success rate, backoff counts, dead-letter volume.
4. Implement restart safety test: kill inbound worker mid-poll → restart → verify no lost changes.
5. Implement idempotency test: retry same mutation → verify no duplicate outbox rows.
6. Create AppFlowy operational dashboard databases for monitoring sync health.

**Tests:**

1. **Dead-letter inspection:** Seed dead-letter event → GET endpoint → assert event returned with error details.
2. **Orphan detection:** Delete AppFlowy row → run scanner → assert binding marked `orphaned`.
3. **Restart safety:** Inbound worker processes 5 changes → kill → restart → assert exactly 5 changes recorded, no duplicates.
4. **Idempotency:** Retry same PATCH with same `Idempotency-Key` → assert no duplicate outbox row.

**Dependencies:** All previous phases.

---

### Constraints

- **No direct SQL writes to AppFlowy schemas.** Council has `SELECT` only on `appflowy_public`. All AppFlowy mutations go through documented REST endpoints.
- **One canonical write path.** Every mutation to `council_core` data goes through `CouncilCoreAPI`. No direct ORM writes bypassing the API.
- **Revision-based concurrency.** All shared entity updates require `expected_revision`. Stale writes return `409`.
- **Field-level editability.** Only fields in `FIELD_ALLOWLIST` may be edited from AppFlowy. All others return `403`.
- **Transactional outbox.** Canonical row update and outbox event INSERT are in the same `BEGIN...COMMIT`.
- **Idempotent mutations.** `Idempotency-Key` required on POST, PATCH, and command endpoints. Duplicate keys return cached response.
- **Status is soft lifecycle only.** `status` column restricted to `('active','archived')` except `prompt_templates` which also allows `'draft'`. Entity-specific state in `run_state`, `review_state`, `finding_state`.
- **SHA-256 snapshot hash.** `last_seen_cells_hash` computed as SHA-256 over canonical JSON (sorted keys, no whitespace, stable arrays, nulls preserved, UTF-8).
- **No backward SQLite compatibility.** This is a fresh PostgreSQL deployment. SQLite `RelationalStore` may be deprecated but not maintained.
- **Credentials are placeholders.** All passwords in code/config use `{{PLACEHOLDER}}` notation. Real values from environment variables or secrets manager.

---

### Success Criteria

- [ ] All `council_core`, `council_ops`, `council_sync` schemas created with correct ownership and constraints
- [ ] `council_app` role has no write access to `appflowy_*` schemas
- [ ] Council Core API accepts POST/GET/PATCH/commands with revision checks and idempotency
- [ ] PATCH with stale `expected_revision` returns `409`; forbidden field edit returns `403`
- [ ] Every canonical write generates exactly one `outbox_events` row in the same transaction
- [ ] OutboxDispatcher delivers pending events to AppFlowy with exponential backoff (2s, 4s, 8s)
- [ ] Auto-projection creates AppFlowy rows and bindings for unbound entities
- [ ] Inbound sync detects changes via SHA-256 snapshot hash comparison
- [ ] Inbound sync enforces `FIELD_ALLOWLIST` — approved fields applied, forbidden fields rejected
- [ ] `last_seen_cells_hash` persisted in `appflowy_bindings` (not process memory) for restart safety
- [ ] Knowledge cards fully integrated: schema, API, field policy, outbound projection, inbound sync
- [ ] `FIELD_ALLOWLIST["knowledge_card"]` matches §7.5 policy table and §8.5 field mapping
- [ ] Dead-letter events inspectable via API
- [ ] Orphaned bindings detected and marked
- [ ] Restart safety verified: no lost changes, no duplicate processing
- [ ] No plaintext credentials in code or config

---

### Acceptance Criteria (from spec §14)

1. Council can create and update canonical entities without any direct writes to AppFlowy schemas.
2. Every outbound projection to AppFlowy is driven by `outbox_events`.
3. A failed AppFlowy API call cannot lose the canonical change.
4. Duplicate retry of the same create, patch, or command mutation does not create duplicate outbox rows.
5. AppFlowy edits to approved fields are routed through Council Core API with `expected_revision`.
6. Forbidden AppFlowy edits are rejected and logged.
7. Restarting the inbound worker does not lose change detection because snapshot state is persisted.
8. `kind`, `phase`, verdict fields, and other Council-only fields cannot be mutated from AppFlowy.
9. Knowledge-card editable fields and non-editable fields match both the policy tables and the inbound allowlist.
10. AppFlowy can be upgraded independently because integration depends only on documented REST endpoints.
