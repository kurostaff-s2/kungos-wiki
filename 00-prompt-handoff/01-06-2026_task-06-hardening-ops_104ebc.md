# Task 06: Hardening & Operational Readiness

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §12 Phase 4
**Generated:** 01-06-2026
**Goal:** Dead-letter inspection, orphaned binding detection, retry metrics, and restart safety verification.

---

## Scope

Operational tooling for monitoring, debugging, and recovery. No new sync logic — just observability and resilience.

---

### Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/api/dead_letter.py` | Dead-letter inspection endpoint |
| Create | `super_council/workers/orphan_scanner.py` | Orphaned binding detection job |
| Create | `super_council/workers/metrics.py` | Retry and delivery metrics |
| Create | `super_council/workers/restart_safety.py` | Restart safety verification helpers |
| Create | `tests/ops/test_dead_letter.py` | Dead-letter inspection tests |
| Create | `tests/ops/test_orphan_scanner.py` | Orphan detection tests |
| Create | `tests/ops/test_restart_safety.py` | Full restart safety tests |

---

### Steps

1. **Dead-letter endpoint:** `GET /v1/sync/dead-letter` returns failed outbox events with `entity_type`, `council_id`, `mutation_type`, `payload_revision`, `last_error`, `attempts`. Support `?entity_type=...` filter.
2. **Dead-letter replay:** `POST /v1/sync/dead-letter/{id}/replay` resets `delivery_state='pending'`, `attempts=0`, `available_at=now()` for manual retry.
3. **Orphan scanner:** Periodic job that iterates `appflowy_bindings` where `state='active'` → calls AppFlowy REST to verify row exists → if 404, mark `state='orphaned'` + INSERT `sync_conflicts` with `reason='missing_binding'`.
4. **Metrics collection:** Track:
   - `outbox_delivery_success_count` / `outbox_delivery_failure_count`
   - `inbound_changes_applied_count` / `inbound_changes_rejected_count`
   - `binding_orphan_count`
   - `dead_letter_count`
   - `retry_backoff_total_ms`
5. **Restart safety test:** Kill inbound worker mid-poll → restart → verify:
   - No changes lost (all processed changes recorded in `inbound_changes`)
   - No changes duplicated (each change appears exactly once)
   - `last_seen_cells_hash` correctly persisted
6. **AppFlowy operational dashboard:** Create AppFlowy databases for monitoring sync health (dead-letter view, delivery metrics, binding status).

---

### Constraints

- Dead-letter replay must not bypass revision checks or idempotency.
- Orphan scanner must not modify bindings for entities currently being processed (use `FOR UPDATE SKIP LOCKED`).
- Metrics must not block sync processing (async or batched writes).
- Restart safety test must simulate real crash (SIGKILL, not graceful shutdown).

---

### Success Criteria

- [ ] Dead-letter events inspectable via API
- [ ] Dead-letter events replayable (reset to pending)
- [ ] Orphaned bindings detected within scan interval
- [ ] Metrics track all key counters
- [ ] Restart safety: no lost changes, no duplicate processing
- [ ] AppFlowy operational dashboard populated with sync health data

---

### Tests

1. **Dead-letter listing:** Seed 3 dead-letter events → GET endpoint → assert all 3 returned with correct fields.
2. **Dead-letter replay:** POST replay → assert event reset to `pending`, `attempts=0`.
3. **Orphan detection:** Delete AppFlowy row → run scanner → assert binding marked `orphaned` + `sync_conflicts` row created.
4. **Metrics accuracy:** Process 10 events (7 success, 3 failure) → assert counters match.
5. **Restart safety (SIGKILL):** Inbound worker processes 5 changes → SIGKILL → restart → assert exactly 5 `inbound_changes` rows, no duplicates.
6. **Restart safety (no hash):** Worker with `last_seen_cells_hash=NULL` → processes all changes → hash persisted.

---

### Dependencies

Tasks 01-05 (all sync components must exist).
