# Task 08: AppFlowy UI Verification for Single-User Readiness

**Source spec:** `~/.llm-wiki/super-council-docs/12-appflowy-integration-v2.1.md` §7.4, §7.5, §8
**Generated:** 01-06-2026
**Goal:** Verify every AppFlowy database, column, view, and edit surface works correctly for single-user operation. Confirm field mappings, editability, and visual presentation match the spec.

---

## Scope

Manual + automated UI verification against a real AppFlowy Cloud instance. Tests the visual workspace, not just the REST API. Validates that the integration is ready for a human user.

---

### Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/ui/test_appflowy_databases.py` | Database existence and column verification |
| Create | `tests/ui/test_appflowy_field_mappings.py` | Field mapping correctness |
| Create | `tests/ui/test_appflowy_editability.py` | Edit surface verification |
| Create | `tests/ui/test_appflowy_views.py` | Board/calendar/list view verification |
| Create | `tests/ui/fixtures/appflowy_ui_driver.py` | Playwright/Selenium driver for AppFlowy |
| Create | `docs/appflowy-ui-checklist.md` | Manual verification checklist |

---

### AppFlowy Databases to Verify

Per spec §4 (Ownership Matrix) and §8 (Field Mapping Appendix):

1. **Work Items** — primary planning board
2. **Reviews** — review tracking
3. **Findings** — review finding triage
4. **Prompt Templates** — prompt library
5. **Knowledge Cards** — knowledge base

---

### Verification Checklist per Database

#### Work Items Database

**Columns exist (from §8.1):**

| Column | Type | Editable | Verified |
|--------|------|----------|----------|
| `Title` | Text | Yes | [ ] |
| `Description` | Long text | Yes | [ ] |
| `Priority` | Select (low/medium/high/critical) | Yes | [ ] |
| `Due Date` | Date/Timestamp | Yes | [ ] |
| `Tags` | Multi-select | Yes | [ ] |
| `Assigned To` | Text | Yes | [ ] |
| `Kind` | Select (read-only display) | No | [ ] |
| `Phase` | Text (read-only display) | No | [ ] |
| `Status` | Text (read-only, soft lifecycle) | No | [ ] |

**Views to verify:**
- [ ] List view (default, sorted by Due Date)
- [ ] Board view (grouped by Priority or Status)
- [ ] Calendar view (grouped by Due Date)

**Edit tests:**
- [ ] Edit `Title` → change propagates to Council within poll interval
- [ ] Edit `Priority` → change propagates to Council
- [ ] Attempt edit `Kind` → column is read-only (or edit rejected by inbound sync)
- [ ] Attempt edit `Status` → column is read-only (or edit rejected by inbound sync)

---

#### Reviews Database

**Columns exist (from §8.2):**

| Column | Type | Editable | Verified |
|--------|------|----------|----------|
| `Target` | Text | No | [ ] |
| `Reviewer` | Text | No | [ ] |
| `State` | Select (read-only) | No | [ ] |
| `Verdict` | Select (read-only) | No | [ ] |
| `Notes` | Long text | Yes | [ ] |

**Edit tests:**
- [ ] Edit `Notes` → change propagates to Council
- [ ] Attempt edit `Verdict` → rejected
- [ ] Attempt edit `State` → rejected

---

#### Findings Database

**Columns exist (from §8.3):**

| Column | Type | Editable | Verified |
|--------|------|----------|----------|
| `Title` | Text | No | [ ] |
| `Summary` | Long text | No | [ ] |
| `Severity` | Select (read-only) | No | [ ] |
| `State` | Select (triage) | Yes | [ ] |
| `Owner Note` | Long text | Yes | [ ] |
| `Recommended Fix` | Long text | No | [ ] |
| `Evidence` | Long text | No | [ ] |

**Edit tests:**
- [ ] Edit `State` (triage) → change propagates to Council
- [ ] Edit `Owner Note` → change propagates to Council
- [ ] Attempt edit `Severity` → rejected
- [ ] Attempt edit `Evidence` → rejected

---

#### Prompt Templates Database

**Columns exist (from §8.4):**

| Column | Type | Editable | Verified |
|--------|------|----------|----------|
| `Name` | Text | Yes | [ ] |
| `Model Family` | Text (read-only) | No | [ ] |
| `Template Body` | Long text | Yes | [ ] |
| `Tags` | Multi-select | Yes | [ ] |
| `Status` | Select (draft/active/archived) | Yes | [ ] |

**Edit tests:**
- [ ] Edit `Name` → change propagates to Council
- [ ] Edit `Template Body` → change propagates to Council
- [ ] Edit `Status` → change propagates to Council
- [ ] Attempt edit `Model Family` → rejected

---

#### Knowledge Cards Database

**Columns exist (from §8.5):**

| Column | Type | Editable | Verified |
|--------|------|----------|----------|
| `Topic` | Text | No | [ ] |
| `Title` | Text | Yes | [ ] |
| `Body` | Long text | Yes | [ ] |
| `Tags` | Multi-select | Yes | [ ] |
| `Confidence` | Number (read-only) | No | [ ] |
| `Source Run` | Text (read-only) | No | [ ] |

**Edit tests:**
- [ ] Edit `Title` → change propagates to Council
- [ ] Edit `Body` → change propagates to Council
- [ ] Edit `Tags` → change propagates to Council
- [ ] Attempt edit `Confidence` → rejected
- [ ] Attempt edit `Source Run` → rejected

---

### Automated UI Testing Strategy

**Tool:** Playwright (headless Chromium) against real AppFlowy Cloud instance.

**Approach:**
1. Navigate to AppFlowy workspace.
2. Open each database.
3. Verify columns exist with correct types.
4. Attempt edits on editable columns → assert propagation to Council.
5. Attempt edits on read-only columns → assert rejection or UI prevention.
6. Verify views render correctly (board, calendar, list).

**Fixture:** `appflowy_ui_driver.py` provides:
- `navigate_to_database(database_name)` → opens database view
- `get_columns()` → returns list of column definitions
- `edit_row_cell(row_id, column_name, new_value)` → edits a cell
- `assert_cell_value(row_id, column_name, expected)` → verifies cell content
- `assert_council_state(entity_type, council_id, expected_fields)` → verifies Council side

---

### Manual Verification Checklist

Save as `docs/appflowy-ui-checklist.md` for human sign-off:

```markdown
## AppFlowy UI Verification Checklist

### Setup
- [ ] AppFlowy Cloud running (docker-compose up)
- [ ] Council PostgreSQL running with all schemas
- [ ] Outbox Dispatcher running
- [ ] Inbound Sync running
- [ ] Test data seeded (at least 1 item per entity type)

### Work Items
- [ ] All 9 columns present with correct types
- [ ] Editable columns accept changes
- [ ] Read-only columns cannot be edited (or edits rejected)
- [ ] Board view groups by Priority/Status
- [ ] Calendar view shows Due Dates
- [ ] Changes propagate to Council within 30 seconds

### Reviews
- [ ] All 5 columns present
- [ ] Notes editable, others read-only
- [ ] Changes propagate to Council

### Findings
- [ ] All 7 columns present
- [ ] State and Owner Note editable, others read-only
- [ ] Changes propagate to Council

### Prompt Templates
- [ ] All 5 columns present
- [ ] Name, Template Body, Tags, Status editable
- [ ] Model Family read-only
- [ ] Changes propagate to Council

### Knowledge Cards
- [ ] All 6 columns present
- [ ] Title, Body, Tags editable
- [ ] Confidence, Source Run, Topic read-only
- [ ] Changes propagate to Council

### Cross-Cutting
- [ ] No Council-only data visible in AppFlowy that shouldn't be
- [ ] No AppFlowy edits silently lost
- [ ] Conflict scenarios handled gracefully (user sees rejection, not crash)
- [ ] Dead-letter events visible in operational dashboard
- [ ] Binding status visible (active/orphaned/disabled)
```

---

### Constraints

- Tests against REAL AppFlowy Cloud instance (not mock).
- Each edit test must verify BOTH sides: AppFlowy cell updated AND Council entity updated.
- Propagation timeout: 30 seconds max (polling interval).
- Read-only columns: verify either UI prevents edit OR inbound sync rejects it.

---

### Success Criteria

- [ ] All 5 databases exist in AppFlowy with correct columns
- [ ] All editable columns propagate changes to Council
- [ ] All read-only columns reject AppFlowy edits
- [ ] Board, calendar, and list views render correctly
- [ ] Manual checklist completed with all items checked
- [ ] No data loss or silent failures observed
- [ ] Single-user workflow is complete and usable

---

### Dependencies

Tasks 01-07 (all components implemented and E2E tested).
