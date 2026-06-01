# Task 05: Knowledge Cards Full Integration

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §7.5, §8.5, §10.1  
**Generated:** 01-06-2026  
**Status:** Corrected replacement for misaligned prompt  
**Goal:** Wire knowledge cards through the complete bidirectional flow: canonical API endpoints, outbound projection, inbound sync, field policy enforcement, and consistency validation.

---

## Scope

End-to-end integration of knowledge cards as a shared Council-owned entity projected into AppFlowy.

This task verifies that the schema contract, field policy, AppFlowy mapping, and inbound allowlist all agree exactly.

---

## Files to Create or Modify

| Action | File | Purpose |
|---|---|---|
| Modify | `super_council/api/core.py` | Add `knowledge_cards` resource endpoints |
| Modify | `super_council/api/field_policy.py` | Add knowledge-card editability policy |
| Modify | `super_council/workers/outbox.py` | Add knowledge-card outbound projection mapping |
| Modify | `super_council/workers/inbound.py` | Add `knowledge_card` to `FIELD_ALLOWLIST` |
| Modify | `super_council/appflowy_sync.py` | Add `push_knowledge_card` with §8.5 mapping |
| Create | `tests/integration/test_knowledge_cards_e2e.py` | End-to-end knowledge-card tests |

---

## Knowledge Cards Contract

### Schema (§5.2)

`council_core.knowledge_cards` contains:

- `topic`
- `title`
- `body`
- `tags`
- `confidence`
- `source_run_id`
- `metadata`
- standard base columns (`revision`, `updated_source`, `origin_source`, `status`, `is_deleted`, etc.)

### Field Policy (§7.5)

| Field | Council Edit | AppFlowy Edit |
|---|---|---|
| `title` | Yes | Yes |
| `body` | Yes | Yes |
| `tags` | Yes | Yes |
| `confidence` | Yes | No |
| `source_run_id` | Yes | No |
| `metadata` | Yes | No |
| `topic` | Yes | No |
| `status` | Yes | No |

### AppFlowy Mapping (§8.5)

| Council Field | AppFlowy Column | Editable in AppFlowy | Notes |
|---|---|---|---|
| `topic` | `Topic` | No | Display only |
| `title` | `Title` | Yes | Main human-facing title |
| `body` | `Body` | Yes | Main content |
| `tags` | `Tags` | Yes | Multi-select or text list |
| `confidence` | `Confidence` | No | Derived/system-owned |
| `source_run_id` | `Source Run` | No | Derived/system-owned |
| `metadata` | hidden/internal | No | Not user-editable |

### Inbound Allowlist (§10.1)

```python
FIELD_ALLOWLIST = {
    "knowledge_card": {"title", "body", "tags"}
}
```

**Correction:** The editable field is `tags`, not `tables`.

---

## Steps

1. Add `knowledge_cards` to Council Core API resource routing for `POST`, `GET`, `PATCH`, and command endpoints.
2. Add knowledge-card policy to `field_policy.py` with AppFlowy-editable fields limited to `title`, `body`, and `tags`.
3. Implement outbound projection in `outbox.py` and `appflowy_sync.py` using the §8.5 field mapping.
4. Add `"knowledge_card": {"title", "body", "tags"}` to the inbound worker `FIELD_ALLOWLIST`.
5. Reject inbound attempts to mutate `confidence`, `source_run_id`, `metadata`, `topic`, or `status` from AppFlowy.
6. Verify exact consistency between policy table, mapping table, and inbound allowlist.
7. Add end-to-end tests covering create, project, inbound edit, forbidden-field rejection, and revision tracking.

---

## Constraints

- Allowlist, policy table, and mapping table must match exactly.
- `confidence`, `source_run_id`, `metadata`, `topic`, and `status` are Council-only fields.
- `topic` is projected to AppFlowy as read-only display metadata.
- `metadata` must not be exposed as a user-editable AppFlowy field.
- All inbound approved edits must flow through Council Core API with `expected_revision`.

---

## Success Criteria

- [ ] Knowledge cards can be created through Council Core API.
- [ ] Knowledge cards project to AppFlowy with the correct field mapping.
- [ ] `title`, `body`, and `tags` edits from AppFlowy are applied to Council.
- [ ] `confidence`, `source_run_id`, `metadata`, `topic`, and `status` edits from AppFlowy are rejected.
- [ ] `FIELD_ALLOWLIST["knowledge_card"]` matches the policy table and mapping table exactly.
- [ ] Successful edits increment revision correctly.

---

## Tests

1. **Policy consistency:** Assert `FIELD_ALLOWLIST["knowledge_card"] == {"title", "body", "tags"}` and matches the editable fields in the policy table and mapping table.
2. **Create and project:** POST a knowledge card and assert AppFlowy row creation with correct field mapping.
3. **Inbound approved edit:** Edit `title` in AppFlowy and assert `inbound_changes.state = 'applied'` plus canonical entity update.
4. **Inbound forbidden edit:** Edit `confidence` in AppFlowy and assert `inbound_changes.state = 'rejected'` with `rejection_reason = 'forbidden_field'`.
5. **Revision tracking:** Apply two sequential approved edits and assert revision increments twice.
6. **Mapping validation:** Assert AppFlowy `Topic` matches Council `topic` and remains read-only.

---

## Dependencies

- Task 02: Council Core API
- Task 03: Outbox Dispatcher and Binding Lifecycle
- Task 04: Inbound Sync with Revision Awareness
