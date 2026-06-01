# Task 02: Council Core API

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §6
**Generated:** 01-06-2026
**Goal:** Implement the canonical write boundary with revision-aware mutations, idempotency, and transactional outbox.

---

## Scope

HTTP API service. Every write to `council_core` data flows through this. No writes bypass it.

---

### Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/api/core.py` | CouncilCoreAPI: POST/GET/PATCH/command endpoints |
| Create | `super_council/api/idempotency.py` | Idempotency-Key store (DB-backed) |
| Create | `super_council/api/revision.py` | Revision-based concurrency helpers |
| Create | `super_council/api/middleware.py` | X-Source-System, X-Actor-Id extraction |
| Create | `super_council/api/outbox_writer.py` | Transactional outbox event writer |
| Create | `super_council/api/field_policy.py` | Field-level editability enforcement |
| Create | `tests/api/test_core_endpoints.py` | API endpoint tests |
| Create | `tests/api/test_idempotency.py` | Idempotency-Key tests |
| Create | `tests/api/test_revision_conflicts.py` | Revision conflict tests |
| Create | `tests/api/test_field_policy.py` | Field allowlist tests |

---

### Steps

1. **Engine setup:** Create SQLAlchemy engine from `DATABASE_URL`. Session factory with autocommit=False.
2. **Resource routing:** Register endpoints for all `council_core` entities: `projects`, `work_items`, `workflow_runs`, `reviews`, `review_findings`, `prompt_templates`, `knowledge_cards`, `memory_entries`, `memory_rollups`.
3. **POST (create):** Accept entity payload → generate UUID → INSERT into canonical table → INSERT `outbox_events` row → COMMIT atomically. Require `Idempotency-Key`.
4. **PATCH (update):** Accept `expected_revision` + patch payload → UPDATE WHERE `revision = expected_revision` → if 0 rows affected, return `409` → INSERT `outbox_events` → COMMIT. Require `Idempotency-Key`.
5. **PATCH field policy:** Extract `X-Source-System`. If `appflowy`, enforce `FIELD_ALLOWLIST` from §10.1. Forbidden fields → `403`.
6. **Commands:** `POST /v1/<resource>/{id}/commands/<cmd>` for non-CRUD transitions. Require `Idempotency-Key`.
7. **GET (fetch):** Return canonical state with current revision.
8. **GET (sync):** `?updated_since=...` for export/sync consumers.
9. **Idempotency store:** Persist `(idempotency_key, response_body, status_code)` → on duplicate key, return cached response without re-executing.
10. **Header enforcement:** Reject writes without `X-Source-System` or `X-Actor-Id`.

---

### Constraints

- Every mutation transaction: canonical row update + outbox INSERT in same `BEGIN...COMMIT`.
- `Idempotency-Key` required on POST, PATCH, and command endpoints.
- `expected_revision` required on PATCH. Stale revision → `409`.
- `X-Source-System: appflowy` triggers field allowlist enforcement.
- `prompt_templates.status` allows `('active','draft','archived')` — exception to soft-lifecycle-only rule.
- No direct ORM writes bypassing the API.

---

### Success Criteria

- [ ] POST creates entity + outbox event atomically
- [ ] PATCH with correct `expected_revision` updates entity + increments revision
- [ ] PATCH with stale `expected_revision` returns `409`
- [ ] PATCH from `appflowy` source with forbidden field returns `403`
- [ ] Duplicate `Idempotency-Key` returns cached response without side effects
- [ ] Missing `X-Source-System` or `X-Actor-Id` rejected
- [ ] GET returns entity with current revision
- [ ] GET with `updated_since` filters correctly

---

### Tests

1. **Create idempotency:** POST with key `abc-123` → 201. POST again with key `abc-123` → same entity, no duplicate row.
2. **Revision bump:** PATCH with `expected_revision=1` → assert entity revision becomes 2.
3. **Stale revision:** PATCH with `expected_revision=1` when entity is at revision 3 → assert `409`.
4. **Field allowlist:** PATCH `work_items.kind` with `X-Source-System: appflowy` → assert `403`. PATCH `work_items.title` with same header → assert `200`.
5. **Transactional outbox:** PATCH entity → assert exactly one `outbox_events` row with `payload_revision` matching new entity revision.
6. **Source tracking:** PATCH with `X-Source-System: appflowy` → assert `updated_source='appflowy'` and `updated_by` from `X-Actor-Id`.
7. **Missing headers:** PATCH without `X-Source-System` → assert rejection (400 or 401).
8. **Command idempotency:** POST command with same key twice → assert only one execution.

---

### Dependencies

Task 01 (PostgreSQL schemas must exist).
