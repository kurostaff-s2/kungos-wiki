# Task 07: E2E Wiring and Integration Tests

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §14  
**Generated:** 01-06-2026  
**Status:** Corrected replacement for misaligned prompt  
**Goal:** Verify the full PostgreSQL → Council Core API → Outbox Dispatcher → AppFlowy REST → Inbound Sync loop against the v2.1 acceptance criteria.

---

## Scope

Integration test suite for the full bidirectional flow.

These tests validate acceptance criteria and real component boundaries, not isolated unit behavior.

---

## Files to Create

| Action | File | Purpose |
|---|---|---|
| Create | `tests/e2e/conftest.py` | Shared fixtures for PostgreSQL, API, workers, and mock AppFlowy |
| Create | `tests/e2e/test_council_to_appflowy.py` | Outbound projection flows |
| Create | `tests/e2e/test_appflowy_to_council.py` | Inbound sync flows |
| Create | `tests/e2e/test_bidirectional_sync.py` | Round-trip flows |
| Create | `tests/e2e/test_conflict_resolution.py` | Revision conflicts and forbidden-field cases |
| Create | `tests/e2e/test_idempotency_e2e.py` | End-to-end idempotency checks |
| Create | `tests/e2e/test_acceptance_criteria.py` | Direct verification of §14 criteria |
| Create | `tests/e2e/fixtures/appflowy_mock_server.py` | Mock AppFlowy REST server using documented endpoints only |

---

## Test Methodology

Each test follows Arrange → Act → Assert.

Each assertion must verify state across all relevant layers:

- PostgreSQL rows, revisions, outbox entries, bindings, and inbound records
- Council Core API responses and status codes
- OutboxDispatcher delivery state changes
- Mock AppFlowy row state
- Inbound worker effects and rejection logs

---

## Acceptance Criterion Tests

### AC1 — Canonical write isolation

- POST a work item.
- Assert the canonical row is created in `council_core.work_items`.
- Assert Council does not write directly into AppFlowy-owned schemas.

### AC2 — Outbound projection comes from outbox

- POST a work item.
- Assert exactly one `outbox_events` row exists.
- Run dispatcher.
- Assert AppFlowy row creation and `delivery_state = 'sent'`.

### AC3 — Failed AppFlowy API call cannot lose canonical change

- Mock a 500 from AppFlowy during dispatch.
- Assert the Council entity remains persisted with the correct revision.
- Assert the outbox row remains retryable or failed, not lost.

### AC4 — Idempotent retry does not duplicate outbox rows

- PATCH an entity with `Idempotency-Key: abc`.
- Repeat the same PATCH with the same key.
- Assert there is still only one outbox row for that mutation revision.

### AC5 — AppFlowy edits route through Council Core API

- Edit an approved AppFlowy field such as `title`.
- Assert the inbound worker issues a revision-aware PATCH through Council Core API.
- Assert `inbound_changes.expected_revision` is populated.

### AC6 — Forbidden AppFlowy edits are rejected and logged

- Edit a Council-only field such as `kind`.
- Assert the edit is rejected and logged with `rejection_reason = 'forbidden_field'`.

### AC7 — Restart safety

- Process several inbound changes.
- Kill the inbound worker mid-cycle.
- Restart it.
- Assert no lost changes and no duplicate processing.

### AC8 — Council-only fields stay Council-only

- For each shared entity type, attempt AppFlowy edits to Council-only fields.
- Assert all are rejected.

### AC9 — Knowledge-card policy consistency

- Assert `FIELD_ALLOWLIST["knowledge_card"] == {"title", "body", "tags"}`.
- Assert it matches the editable fields in the policy table and mapping table.
- Validate both allowed and forbidden knowledge-card edits end to end.

### AC10 — Upgrade-safe integration contract

- Verify the integration layer uses only the documented AppFlowy REST endpoints listed in the v2.1 contract.
- Fail the test if any undocumented endpoint or direct AppFlowy-schema write path is used.
- Optionally vary harmless response details within the documented contract, but do not assume compatibility with arbitrary breaking response-shape changes.

---

## Cross-Component Flow Tests

1. **Full round-trip (work item):** create in Council → project to AppFlowy → edit approved field in AppFlowy → inbound sync applies through Council Core API → revision increments → outbound sync converges.
2. **Conflict detection:** Council update advances revision before inbound AppFlowy edit applies → inbound PATCH returns `409` → change is logged as `stale_revision`.
3. **Multi-entity sync:** create work item, review, and knowledge card → assert projection and bindings for all.
4. **Orphan recovery:** delete AppFlowy row → mark binding `orphaned` → repair binding manually → assert delivery resumes.
5. **Dead-letter recovery:** force repeated delivery failures → move event to `dead_letter` → replay → assert successful delivery.

---

## Mock AppFlowy Server

The mock server must implement only the documented endpoints used by the v2.1 contract:

- `POST /api/workspace/{ws}/database/{db}/row`
- `PUT /api/workspace/{ws}/database/{db}/row`
- `GET /api/workspace/{ws}/database/{db}/row/updated`
- `GET /api/workspace/{ws}/database/{db}/row/detail`
- `GET /api/workspace/{ws}/database/{db}/fields`
- `GET /api/workspace/{ws}/database/{db}`

The mock may support failure injection, delay injection, and contract-valid response variants.

---

## Constraints

- Tests must run against real PostgreSQL, not SQLite.
- AppFlowy interactions must go through the mock server, not a live AppFlowy instance.
- Each test must isolate database state.
- Tests must validate component boundaries, not just final values.
- AC10 must verify upgrade safety by endpoint usage and schema isolation, not by assuming resilience to arbitrary undocumented API changes.

---

## Success Criteria

- [ ] All 10 v2.1 acceptance criteria are verified by dedicated tests.
- [ ] Full round-trip flow passes.
- [ ] Conflict detection and `409` handling pass.
- [ ] Restart safety passes.
- [ ] Dead-letter recovery passes.
- [ ] Mock AppFlowy server supports failure injection and contract-valid variants.
- [ ] CI can run the full suite reliably.

---

## Dependencies

- Tasks 01 through 06
