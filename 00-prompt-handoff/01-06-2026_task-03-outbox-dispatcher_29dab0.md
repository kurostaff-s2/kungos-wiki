# Task 03: Outbox Dispatcher & Binding Lifecycle

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §7.1, §5.4 binding lifecycle
**Generated:** 01-06-2026
**Goal:** Push canonical changes from Council to AppFlowy with binding management, auto-projection, and exponential backoff.

---

## Scope

Background worker that reads `outbox_events`, resolves bindings, calls AppFlowy REST API, and tracks delivery state.

---

### Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/workers/outbox.py` | OutboxDispatcher: select, resolve, deliver |
| Create | `super_council/workers/binding_manager.py` | Binding lifecycle (create, orphan, repair) |
| Modify | `super_council/appflowy_sync.py` | Add binding-aware push methods |
| Create | `tests/workers/test_outbox_dispatcher.py` | Dispatcher delivery tests |
| Create | `tests/workers/test_binding_lifecycle.py` | Binding creation/orphan tests |
| Create | `tests/workers/test_outbox_backoff.py` | Retry/backoff tests |

---

### Steps

1. **Select pending:** `SELECT ... FROM outbox_events WHERE delivery_state='pending' ORDER BY available_at FOR UPDATE SKIP LOCKED`.
2. **Resolve binding:** Lookup `appflowy_bindings` by `(entity_type, council_id)`.
3. **Auto-projection:** If binding missing AND auto-projection enabled for entity type → call AppFlowy REST to create row → capture `appflowy_row_id` → INSERT binding with `state='active'`.
4. **Orphan check:** If binding `state='orphaned'` → skip delivery, log warning.
5. **Delivery:** Call AppFlowy REST `PUT /api/workspace/{ws}/database/{db}/row` with mapped cells.
6. **Success:** Set `delivery_state='sent'`, update `binding.last_synced_revision`.
7. **Transient failure:** Increment `attempts`, set `delivery_state='failed'`, compute next backoff (2s, 4s, 8s), set `available_at = now() + backoff`.
8. **Dead letter:** After 3 failures, set `delivery_state='dead_letter'`.
9. **Orphan scanner:** Periodic job that checks if bound AppFlowy rows still exist → mark `orphaned` if not → log to `sync_conflicts`.

---

### Binding Lifecycle Rules (from spec §5.4)

1. **Auto-projection on Council create:** dispatcher creates AppFlowy row if no binding exists, captures `appflowy_row_id`, stores binding.
2. **Manual binding:** admin-only command to link existing Council entity to existing AppFlowy row (validate entity type, database ID, row ID).
3. **Unbound entities:** valid in Council, invisible in AppFlowy until projected or manually linked.
4. **Orphaned bindings:** marked `state='orphaned'`, logged to `sync_conflicts`, excluded from delivery until repaired.

---

### Constraints

- Use `FOR UPDATE SKIP LOCKED` to prevent duplicate processing across workers.
- Max 3 attempts per event. After 3rd failure → `dead_letter`.
- Backoff sequence: 2s, 4s, 8s (exponential).
- Never write directly to AppFlowy schemas — only through REST API.
- Binding `last_synced_revision` updated only after confirmed delivery.

---

### Success Criteria

- [ ] Pending outbox events delivered to AppFlowy with correct field mapping
- [ ] Missing binding triggers auto-projection (creates AppFlowy row + binding)
- [ ] Orphaned bindings excluded from delivery
- [ ] Transient failures retried with 2s/4s/8s backoff
- [ ] 3 failures → `dead_letter` state
- [ ] `last_synced_revision` updated on success
- [ ] `FOR UPDATE SKIP LOCKED` prevents duplicate processing

---

### Tests

1. **Happy path:** Seed pending event + active binding → run dispatcher → assert `delivery_state='sent'` + `last_synced_revision` updated.
2. **Auto-projection:** Seed pending event without binding → run dispatcher → assert binding created with valid `appflowy_row_id`.
3. **Orphan skip:** Seed event with `orphaned` binding → run dispatcher → assert event NOT delivered, binding still `orphaned`.
4. **Retry backoff:** Mock AppFlowy failure (500) → assert 3 attempts with increasing delays → assert `dead_letter`.
5. **SKIP LOCKED:** Two workers select simultaneously → assert each processes different events (no duplicates).
6. **Dead letter state:** After 3 failures → assert `delivery_state='dead_letter'` and no further retries.

---

### Dependencies

Task 01 (schemas), Task 02 (Council Core API generates outbox events).
