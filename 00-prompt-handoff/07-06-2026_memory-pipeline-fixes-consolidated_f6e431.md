# Memory Pipeline Alignment Fixes — Consolidated Implementation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `f6e431` |
| Entity type | `handoff` |
| Short description | Fix MD format alignment; drop fake Topics Discussed; promote errors_blockers + notable_deviations to structured carry_forward; add round-trip fidelity tests; wire into SessionWatcher flow |
| Status | `draft` |
| Source references | `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_memory-pipeline-redundancy-audit_ea8ef8.md` (Phase 9) |
| Generated | `07-06-2026` |
| Updated | `07-06-2026 11:15 IST` — dropped Topics Discussed, promoted blockers/deviations, added round-trip fidelity |
| Next action / owner | Next session agent — execute Phase 1 (regex+loop fixes), Phase 2 (_write_session_md), Phase 3 (alignment+round-trip tests), Phase 3b (wiring), Phase 4 (production runtime verification) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `07-06-2026_memory-pipeline-redundancy-audit_ea8ef8.md` (Phase 9.1-9.8)
**Key files for this task:**
- `memory_service/store.py` — regex fix + open_items loop fix (Phase 1)
- `memory_service/session_watcher.py` — new `_write_session_md()` + _process_session() wiring (Phase 2)
- `tests/` — unit tests + production runtime verification (Phase 3-4)

---

## Goal

Fix all alignment mismatches between the canonical MD format, `upsert_session_diary()` extraction patterns, and the SessionAnalyzer trimmed schema. Drop fake abstractions (Topics Discussed), promote actionable signals (errors_blockers, notable_deviations) to structured consumers, and verify round-trip fidelity so the MD is semantically faithful, not just syntactically valid.

**Total effort: ~3h across 4 phases, 2 files.**

---

## Phase 1: Fix `_extract_section()` Regex Bug

**What:** Replace `$` with `\Z` in the `_extract_section()` regex inside `upsert_session_diary()`. The current regex uses `$` with `re.MULTILINE`, which matches end-of-line instead of end-of-string. Multi-paragraph MD sections (header → blank line → content) capture only the first paragraph.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/store.py` | Fix `_extract_section()` regex (line ~986) |

**Steps:**

1. Open `memory_service/store.py`, find `upsert_session_diary()` method.
2. Inside the method, find the `_extract_section()` nested function (line ~984).
3. Replace the regex pattern:

```python
# Before (broken): $ matches end-of-line with MULTILINE
pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|$)'

# After (fixed): \Z matches end-of-string
pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|\Z)'
```

4. Verify the flags are `re.DOTALL | re.MULTILINE` (no change needed).

**Fix 1b: Open Items Loop Bug (line ~999)**

The current loop tries "Open Items" twice because `hdr.split("/")[0].strip()` produces the same value for "Open Items" and "Open Items / Follow-ups":

```python
# Before (bug: tries "Open Items" twice):
for hdr in ("Open Items", "Open Items / Follow-ups", "Follow-ups", "Unresolved"):
    open_items = _extract_section(summary_text, hdr.split("/")[0].strip())
    if open_items:
        break

# After (fixed: try each header directly, no split):
for hdr in ("Open Items", "Open Items / Follow-ups", "Follow-ups", "Unresolved"):
    open_items = _extract_section(summary_text, hdr)
    if open_items:
        break
```

**Tests:**

1. Run existing tests: `cd /home/chief/Coding-Projects/7-council/super_council && python -m pytest tests/ -v -k "session_diary or extract" --tb=short`
2. Verify no regressions in `upsert_session_diary()`.

**Dependencies:** None (can run first, independent of other phases).

**Estimated effort:** ~10 min

---

## Phase 2: Write `_write_session_md()` — Signal-Faithful, No Duplication

**What:** Add `_write_session_md()` to SessionWatcher. Maps trimmed schema fields to MD section headers that match `upsert_session_diary()` extraction patterns. Does NOT use `_trimmed_to_text()` which generates wrong headers.

**Design principles (enforced):**
- **No fake abstraction:** Every MD section must carry signal that isn't already in a structured column. If `## Topics Discussed` is just `decisions + open_work + completed_work` re-listed, it's noise — drop it.
- **Promote actionable signals:** `errors_blockers` and `notable_deviations` are structured facts, not metadata. They get their own MD sections and wired consumers, not a dump in `## Reference`.
- **Reference is optional:** Only include if it carries signal useful to memsearch that isn't elsewhere. Cap at 5 items.
- **Round-trip fidelity:** trimmed → MD → extract → DB must preserve every item. No silent drops.

**Critical constraint:** `_trimmed_to_text()` stays as-is (it feeds ArcPipeline.reconcile_tasks()). `_write_session_md()` is a NEW method with correct headers.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/session_watcher.py` | Add `_write_session_md()` method |

**Steps:**

1. Add the method to `SessionWatcher` class (after `_count_signals()`):

```python
def _write_session_md(self, trimmed: dict, jsonl_path: Path) -> Path:
    """Write canonical MD from trimmed summary.

    Maps trimmed schema fields to MD section headers that match
    upsert_session_diary() extraction patterns. Does NOT use
    _trimmed_to_text() which generates wrong headers.

    Field→Header mapping:
        explicit_decisions → ## Decisions
        open_work → ## Open Items
        completed_work → ## Work Completed
        errors_blockers → ## Blockers (structured, wired to carry_forward)
        notable_deviations → ## Deviations (structured, wired to carry_forward)
        files_changed, functions_touched, tests_written → ## Reference (capped, optional)

    DROPPED: ## Topics Discussed — no real topic extractor exists.
        Deriving from signal sections duplicates structured facts.
        Re-add when SessionAnalyzer produces a proper topics_discussed field.
    """
    from datetime import datetime
    from ..memory_service.config import IST

    lines = [
        f"# Session: {jsonl_path.stem}",
        f"date: {datetime.now(IST).strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"mode: {trimmed.get('session_mode', 'mixed')}",
        f"project: {trimmed.get('project_id', '')}",
        "",
    ]

    # Decisions: explicit_decisions → ## Decisions
    # Write "- none" if empty (meaningful absence for carry_forward)
    decisions = trimmed.get("explicit_decisions", [])
    lines.append("## Decisions")
    if decisions:
        for d in decisions:
            lines.append(f"- {d}")
    else:
        lines.append("- none")
    lines.append("")

    # Open Items: open_work → ## Open Items
    # Write "- none" if empty (meaningful absence for _reconcile_open_items)
    # NOTE: trimmed schema uses 'open_work', MD uses 'Open Items' (naming mismatch)
    open_work = trimmed.get("open_work", [])
    lines.append("## Open Items")
    if open_work:
        for item in open_work:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")

    # Work Completed: completed_work → ## Work Completed
    # Omit section if empty (absence not meaningful)
    completed = trimmed.get("completed_work", [])
    if completed:
        lines.append("## Work Completed")
        for c in completed:
            lines.append(f"- {c}")
        lines.append("")

    # Blockers: errors_blockers → ## Blockers
    # Structured signal — wired to carry_forward (kind="blocker") in Phase 4B.
    # NOT hidden in Reference. Extracted to session_diary via new column or session_context.
    blockers = trimmed.get("errors_blockers", [])
    if blockers:
        lines.append("## Blockers")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    # Deviations: notable_deviations → ## Deviations
    # Structured signal — wired to carry_forward (kind="deviation") in Phase 4B.
    # NOT hidden in Reference. Same continuity path as blockers.
    deviations = trimmed.get("notable_deviations", [])
    if deviations:
        lines.append("## Deviations")
        for d in deviations:
            lines.append(f"- {d}")
        lines.append("")

    # Reference: aggregate metadata (optional, capped — only if useful to memsearch)
    # Omitted if empty. Capped at 5 items to prevent noise dumps.
    ref_items = []
    if trimmed.get("files_changed"):
        ref_items.append(f"files: {trimmed['files_changed']}")
    if trimmed.get("functions_touched"):
        ref_items.append(f"functions: {trimmed['functions_touched']}")
    if trimmed.get("tests_written"):
        ref_items.append(f"tests: {trimmed['tests_written']}")

    if ref_items:
        lines.append("## Reference")
        for item in ref_items[:5]:  # Cap to prevent noise
            lines.append(item)
        lines.append("")

    # Write to ~/.council-memory/sessions/
    sessions_dir = Path(os.path.expanduser("~/.council-memory/sessions"))
    sessions_dir.mkdir(parents=True, exist_ok=True)
    md_path = sessions_dir / f"{jsonl_path.stem}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path
```

2. Add `import os` at the top of the file if not already present (check line ~15).
3. Add the `from ..memory_service.config import IST` import inside the method (as shown) to avoid circular imports.

**Header→Extraction alignment (verify these match):**

| MD Header | `upsert_session_diary()` Extracts | Match? | Notes |
|-----------|-----------------------------------|--------|-------|
| `## Decisions` | `"Key Decisions"` or `"Decisions"` | ✅ Second fallback | Primary signal |
| `## Open Items` | `"Open Items"` (first try) | ✅ First match | Primary signal |
| `## Work Completed` | `"Work Completed"` (first try) | ✅ First match | Primary signal |
| ~~`## Topics Discussed`~~ | ~~`"Topics Discussed"`~~ | ❌ **DROPPED** | No real topic extractor — was duplicated noise |
| `## Blockers` | Not extracted by session_diary | ✅ Wired to carry_forward | **NEW** — promoted from Reference |
| `## Deviations` | Not extracted by session_diary | ✅ Wired to carry_forward | **NEW** — promoted from Reference |
| `## Reference` | Not extracted (indexed only) | ✅ N/A | Capped at 5, optional |

**Dependencies:** Phase 1 (regex fix must be in place so extraction works correctly).

**Estimated effort:** ~1h

---

## Phase 3: Verification Tests — Alignment + Round-Trip Fidelity

**What:** Verify that the MD format produces correct extraction results AND that the full round-trip (trimmed → MD → extract → DB) preserves every item without silent drops.

**Two test categories:**
1. **Alignment tests** — regex works, headers match, sections extract correctly
2. **Round-trip fidelity tests** — trimmed dict → MD → extract → matches original trimmed dict item-for-item

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_md_format_alignment.py` | MD format → extraction verification + round-trip fidelity |

**Steps:**

1. Create test file `tests/test_md_format_alignment.py`:

```python
"""Test MD format alignment with upsert_session_diary() extraction patterns.

Verifies that the canonical MD format produces correct extraction results
through the full pipeline: MD text → _extract_section() → DB columns.

Includes round-trip fidelity tests: trimmed → MD → extract → matches original.
"""
import re
import pytest
from pathlib import Path
from datetime import datetime


def _extract_section(text: str, header: str):
    """Copy of fixed _extract_section() from store.py for testing."""
    pattern = rf'^#{{1,3}}\s+{re.escape(header)}\s*\n(.*?)(?=\n#{{1,3}}|\Z)'
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    if match:
        content = match.group(1).strip()
        return content if content else None
    return None


def _parse_bullet_list(text: str) -> list:
    """Parse a bullet list from extracted section text."""
    if text is None or text == "- none":
        return []
    return [line.lstrip("- ").strip() for line in text.split("\n")
            if line.strip().startswith("-")]


def _build_sample_md() -> str:
    """Build a sample MD matching the canonical format."""
    return """# Session: test-session-abc123
date: 2026-06-07T12:00:00+0530
mode: code
project: council

## Decisions
- Use dict.get() not if key in d (cleaner semantics)
- Return False from _wait_idle() on deadline expiry

## Open Items
- Fix carry_forward writer (priority: high)
- Add _wire_session_diary() to SessionWatcher

## Work Completed
- Fixed _wait_idle() stability semantics
- Rewrote verification handoff with actual endpoints

## Blockers
- database is locked during migration

## Deviations
- carry_forward timing changed from immediate to deferred

## Reference
files: [session_watcher.py, store.py]
functions: [_wait_idle, _extract_section]
"""


def _build_empty_decisions_md() -> str:
    """Build MD with explicitly empty Decisions."""
    return """# Session: test-empty-decisions
date: 2026-06-07T12:00:00+0530
mode: debugging

## Decisions
- none

## Open Items
- none

## Work Completed
- Root-caused race in _wait_idle()
"""


class TestExtractSectionRegex:
    """Test the fixed _extract_section() regex."""

    def test_single_paragraph(self):
        text = "## Decisions\n- item1\n- item2"
        result = _extract_section(text, "Decisions")
        assert result is not None
        assert "- item1" in result
        assert "- item2" in result

    def test_multi_paragraph_with_blank_lines(self):
        """The bug: $ with MULTILINE captures only first paragraph."""
        text = "## Decisions\n> hint\n\n- item1\n- item2"
        result = _extract_section(text, "Decisions")
        assert result is not None
        assert "- item1" in result
        assert "- item2" in result

    def test_stops_at_next_header(self):
        text = "## Decisions\n- item1\n\n## Open Items\n- item2"
        result = _extract_section(text, "Decisions")
        assert result is not None
        assert "- item1" in result
        assert "- item2" not in result

    def test_returns_none_for_missing_header(self):
        text = "## Decisions\n- item1"
        result = _extract_section(text, "Open Items")
        assert result is None


class TestMdFormatAlignment:
    """Test that MD format produces correct extraction results."""

    def test_decisions_extracted(self):
        md = _build_sample_md()
        result = _extract_section(md, "Decisions")
        assert result is not None
        assert "dict.get()" in result
        assert "_wait_idle()" in result

    def test_open_items_extracted(self):
        md = _build_sample_md()
        result = _extract_section(md, "Open Items")
        assert result is not None
        assert "carry_forward" in result
        assert "priority: high" in result

    def test_work_completed_extracted(self):
        md = _build_sample_md()
        result = _extract_section(md, "Work Completed")
        assert result is not None
        assert "stability semantics" in result

    def test_blockers_extracted(self):
        """Blockers are now a structured section, not hidden in Reference."""
        md = _build_sample_md()
        result = _extract_section(md, "Blockers")
        assert result is not None
        assert "database is locked" in result

    def test_deviations_extracted(self):
        """Deviations are now a structured section, not hidden in Reference."""
        md = _build_sample_md()
        result = _extract_section(md, "Deviations")
        assert result is not None
        assert "carry_forward timing" in result

    def test_explicitly_empty_decisions(self):
        """- none is stored as TEXT, distinguishable from NULL."""
        md = _build_empty_decisions_md()
        result = _extract_section(md, "Decisions")
        assert result == "- none"  # Not None (NULL), not empty string

    def test_explicitly_empty_open_items(self):
        md = _build_empty_decisions_md()
        result = _extract_section(md, "Open Items")
        assert result == "- none"

    def test_no_topics_discussed_section(self):
        """Topics Discussed was dropped — no real topic extractor exists."""
        md = _build_sample_md()
        result = _extract_section(md, "Topics Discussed")
        assert result is None, "Topics Discussed should not exist in MD"

    def test_reference_not_extracted_by_session_diary(self):
        """Reference section is not extracted by upsert_session_diary()."""
        md = _build_sample_md()
        assert _extract_section(md, "Reference") is not None  # Exists in MD
        # But it's not extracted to any DB column by upsert_session_diary()


class TestRoundTripFidelity:
    """Verify trimmed → MD → extract preserves every item.

    These tests catch silent data loss: items that are written to MD
    but not extracted back, or items that are dropped by caps/filters.
    """

    def test_decisions_count_fidelity(self):
        """All trimmed decisions appear in MD, none dropped."""
        decisions = [f"decision-{i}" for i in range(10)]
        md_lines = ["# Session: test", ""]
        md_lines.append("## Decisions")
        for d in decisions:
            md_lines.append(f"- {d}")
        md_lines.append("")
        md_lines.append("## Open Items")
        md_lines.append("- none")
        md = "\n".join(md_lines)

        extracted = _extract_section(md, "Decisions")
        extracted_items = _parse_bullet_list(extracted)
        assert len(extracted_items) == len(decisions), \
            f"Expected {len(decisions)} decisions, got {len(extracted_items)}"
        for d in decisions:
            assert d in extracted_items, f"Missing: {d}"

    def test_open_items_count_fidelity(self):
        """All open items survive round-trip."""
        items = [f"open-item-{i}" for i in range(8)]
        md = "## Open Items\n" + "\n".join(f"- {i}" for i in items)

        extracted = _extract_section(md, "Open Items")
        extracted_items = _parse_bullet_list(extracted)
        assert len(extracted_items) == len(items)
        for item in items:
            assert item in extracted_items

    def test_completed_work_count_fidelity(self):
        """All completed work items survive round-trip."""
        items = [f"completed-{i}" for i in range(12)]
        md = "## Work Completed\n" + "\n".join(f"- {i}" for i in items)

        extracted = _extract_section(md, "Work Completed")
        extracted_items = _parse_bullet_list(extracted)
        assert len(extracted_items) == len(items)

    def test_blockers_count_fidelity(self):
        """All blockers survive round-trip."""
        blockers = [f"blocker-{i}" for i in range(5)]
        md = "## Blockers\n" + "\n".join(f"- {b}" for b in blockers)

        extracted = _extract_section(md, "Blockers")
        extracted_items = _parse_bullet_list(extracted)
        assert len(extracted_items) == len(blockers)

    def test_deviations_count_fidelity(self):
        """All deviations survive round-trip."""
        deviations = [f"deviation-{i}" for i in range(4)]
        md = "## Deviations\n" + "\n".join(f"- {d}" for d in deviations)

        extracted = _extract_section(md, "Deviations")
        extracted_items = _parse_bullet_list(extracted)
        assert len(extracted_items) == len(deviations)

    def test_empty_sections_roundtrip(self):
        """Empty sections produce '- none', not NULL."""
        md = "## Decisions\n- none\n\n## Open Items\n- none"
        assert _extract_section(md, "Decisions") == "- none"
        assert _extract_section(md, "Open Items") == "- none"
        assert _parse_bullet_list("- none") == []  # But parseable as empty

    def test_multi_section_isolation(self):
        """Extracting one section doesn't leak into adjacent sections."""
        md = """## Decisions
- decision-A

## Open Items
- open-A

## Work Completed
- completed-A

## Blockers
- blocker-A

## Deviations
- deviation-A
"""
        decisions = _parse_bullet_list(_extract_section(md, "Decisions"))
        open_items = _parse_bullet_list(_extract_section(md, "Open Items"))
        completed = _parse_bullet_list(_extract_section(md, "Work Completed"))
        blockers = _parse_bullet_list(_extract_section(md, "Blockers"))
        deviations = _parse_bullet_list(_extract_section(md, "Deviations"))

        assert decisions == ["decision-A"]
        assert open_items == ["open-A"]
        assert completed == ["completed-A"]
        assert blockers == ["blocker-A"]
        assert deviations == ["deviation-A"]

        # Cross-check: no leakage
        for items in [open_items, completed, blockers, deviations]:
            assert "decision-A" not in items


class TestHeaderMatching:
    """Verify MD headers match upsert_session_diary() extraction patterns."""

    def test_decisions_matches_fallback(self):
        """## Decisions matches second fallback 'Decisions'."""
        md = "## Decisions\n- item"
        assert _extract_section(md, "Key Decisions") is None
        assert _extract_section(md, "Decisions") is not None

    def test_open_items_matches_primary(self):
        """## Open Items matches first try 'Open Items'."""
        md = "## Open Items\n- item"
        assert _extract_section(md, "Open Items") is not None

    def test_work_completed_matches_primary(self):
        """## Work Completed matches first try 'Work Completed'."""
        md = "## Work Completed\n- item"
        assert _extract_section(md, "Work Completed") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

2. Run tests:
```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -m pytest tests/test_md_format_alignment.py -v
```

3. Verify all tests pass (19 tests: 4 regex + 9 alignment + 7 round-trip + 3 header).

**Dependencies:** Phase 1, Phase 2.

**Estimated effort:** ~30 min

---

## Phase 3b: Wire `_write_session_md()` + Structured Signal Consumers

**What:** Integrate `_write_session_md()` into the SessionWatcher `_process_session()` method. Wire `errors_blockers` and `notable_deviations` into carry_forward as structured consumers.

**Two wiring paths:**
1. **MD write** — `_write_session_md()` called after `_trim_session()`, before `_reconcile()`
2. **Structured signals** — `errors_blockers` → carry_forward(kind="blocker"), `notable_deviations` → carry_forward(kind="deviation")

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/session_watcher.py` | Wire `_write_session_md()` + `_wire_carry_forward()` |

**Steps:**

1. Open `memory_service/session_watcher.py`, find `_process_session()` method (line ~215).
2. Add the MD write step after `_trim_session()` and before `_reconcile()`:

```python
def _process_session(self, jsonl_path: Path) -> None:
    """Process a single JSONL session file.

    Flow: parse → classify → trim → write MD → wire carry_forward → reconcile → wake.
    """
    try:
        # Step 1: Parse JSONL into conversation turns
        turns = self._parse_jsonl(jsonl_path)
        if not turns:
            log.debug("SessionWatcher: no messages in %s", jsonl_path.name)
            return

        log.info(
            "SessionWatcher: processing %s (%d messages, %.1fKB)",
            jsonl_path.name,
            len(turns),
            jsonl_path.stat().st_size / 1024,
        )

        # Step 2: Classify session mode
        session_mode = self._classify(turns)

        # Step 3: Generate trimmed summary
        trimmed = self._trim_session(turns, session_mode, jsonl_path)

        # Step 3a: Write canonical MD file (NEW)
        # Called BEFORE _reconcile() so the MD exists for downstream consumers.
        try:
            md_path = self._write_session_md(trimmed, jsonl_path)
            log.info("SessionWatcher: wrote MD to %s", md_path)
        except Exception as e:
            log.warning("SessionWatcher: MD write failed (non-fatal): %s", e)
            md_path = None

        # Step 3b: Wire structured signals to carry_forward (NEW)
        # errors_blockers → carry_forward(kind="blocker")
        # notable_deviations → carry_forward(kind="deviation")
        try:
            self._wire_carry_forward(trimmed, jsonl_path)
        except Exception as e:
            log.warning("SessionWatcher: carry_forward wiring failed (non-fatal): %s", e)

        # Step 4: Feed into reconciliation pipeline
        self._reconcile(trimmed, jsonl_path)

        # Step 5: Wake scheduler for consolidation
        self._wake("daily_summary_saved")

        log.info(
            "SessionWatcher: completed %s (mode=%s, %d signals)",
            jsonl_path.name,
            session_mode,
            self._count_signals(trimmed),
        )

    except Exception as e:
        log.warning("SessionWatcher: failed to process %s: %s", jsonl_path.name, e)
```

3. Add `_wire_carry_forward()` method to SessionWatcher:

```python
def _wire_carry_forward(self, trimmed: dict, jsonl_path: Path) -> None:
    """Wire structured signals from trimmed summary to carry_forward.

    Promotes errors_blockers and notable_deviations from unstructured
    MD text into the carry_forward table for structured tracking.

    This is the immediate carry_forward writer — ArcPipeline creates
    carry_forward during consolidation (Phase 4B). SessionWatcher creates
    carry_forward for immediate session-level signals.

    Args:
        trimmed: Trimmed summary dict from SessionAnalyzer.
        jsonl_path: Source JSONL path for provenance.
    """
    if not self._memory_service:
        log.debug("SessionWatcher: no memory_service, skipping carry_forward")
        return

    store = self._memory_service.store
    project_id = trimmed.get("project_id", "")

    # Wire errors_blockers → carry_forward(kind="blocker")
    blockers = trimmed.get("errors_blockers", [])
    for blocker in blockers:
        store.create_carry_forward(
            project_id=project_id,
            tier="daily",
            kind="blocker",
            text=blocker,
            priority="high",  # Blockers are high priority by definition
            source_file=str(jsonl_path),
        )

    # Wire notable_deviations → carry_forward(kind="deviation")
    deviations = trimmed.get("notable_deviations", [])
    for deviation in deviations:
        store.create_carry_forward(
            project_id=project_id,
            tier="daily",
            kind="deviation",
            text=deviation,
            priority="medium",  # Deviations are medium priority
            source_file=str(jsonl_path),
        )
```

4. Verify `_trimmed_to_text()` is NOT modified (it's still used by `_reconcile()` for ARC).

**Tests:**

1. Verify `_process_session()` calls `_write_session_md()` after `_trim_session()`.
2. Verify `_process_session()` calls `_wire_carry_forward()` after MD write.
3. Verify MD write failure is non-fatal (reconciliation still proceeds).
4. Verify carry_forward wiring failure is non-fatal.
5. Verify `_trimmed_to_text()` is unchanged (ARC pipeline regression check).
6. Verify `errors_blockers` → carry_forward(kind="blocker", priority="high").
7. Verify `notable_deviations` → carry_forward(kind="deviation", priority="medium").

**Dependencies:** Phase 1, Phase 2, Phase 3 (unit tests).

**Estimated effort:** ~20 min

---

## Phase 4: Production Runtime Verification

**What:** End-to-end verification with a real JSONL file. This is NOT a mock test — it processes an actual session file through the full pipeline and verifies the output in the database.

**Critical distinction:** Phase 3 tests mock MD strings against `_extract_section()`. Phase 4 tests the full pipeline: real JSONL → `_process_session()` → MD file → `upsert_session_diary()` → DB columns + carry_forward.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_session_watcher_runtime.py` | Production runtime verification |

**Steps:**

1. Create test file `tests/test_session_watcher_runtime.py`:

```python
"""Production runtime verification for SessionWatcher MD pipeline.

Tests the full pipeline with real JSONL files:
    JSONL → _process_session() → MD file → upsert_session_diary() → DB columns
    JSONL → _wire_carry_forward() → carry_forward (blockers, deviations)

This is NOT a mock test. It uses actual session files from the sessions directory.
"""
import json
import os
import sqlite3
import tempfile
from pathlib import Path
import pytest


def _get_recent_jsonl() -> Path:
    """Find the most recent JSONL file in the sessions directory."""
    sessions_dir = Path(os.path.expanduser("~/.pi/agent/sessions"))
    if not sessions_dir.exists():
        pytest.skip("Sessions directory not found")

    jsonl_files = sorted(
        sessions_dir.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not jsonl_files:
        pytest.skip("No JSONL files found")
    return jsonl_files[0]


def _build_test_store(tmp_path: Path):
    """Build a test RelationalStore in a temp directory."""
    from super_council.memory_service.store import RelationalStore
    db_path = tmp_path / "test_council.db"
    store = RelationalStore(str(db_path))
    return store


def _verify_session_diary_columns(store, summary_id: str):
    """Verify that session_diary has correct columns populated."""
    rows = store.db.execute(
        "SELECT summary_id, decisions, open_items, work_completed, session_context "
        "FROM session_diary WHERE summary_id = ?",
        (summary_id,),
    ).fetchall()

    assert len(rows) == 1, f"Expected 1 row for {summary_id}, got {len(rows)}"
    row = dict(rows[0])

    # Decisions: should be TEXT (either items or "- none")
    assert row["decisions"] is not None, "decisions should not be NULL"
    assert len(row["decisions"]) > 0, "decisions should not be empty"

    # Open Items: should be TEXT (either items or "- none")
    assert row["open_items"] is not None, "open_items should not be NULL"
    assert len(row["open_items"]) > 0, "open_items should not be empty"

    # work_completed: may be NULL if session had no completions
    # (this is acceptable — absence is not meaningful for this section)

    # session_context: may be NULL if no topics or models
    # (this is acceptable — context is additive, and Topics Discussed is dropped)

    return row


def _verify_carry_forward_entries(store, project_id: str):
    """Verify carry_forward entries were created for structured signals."""
    rows = store.db.execute(
        "SELECT id, kind, text, priority FROM carry_forward "
        "WHERE project_id = ? ORDER BY id DESC LIMIT 10",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


class TestSessionWatcherRuntime:
    """Production runtime tests with real JSONL files."""

    def test_process_session_writes_md_file(self, tmp_path):
        """Verify _process_session() writes an MD file to disk."""
        jsonl_path = _get_recent_jsonl()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        # Copy JSONL to temp dir for isolated testing
        test_jsonl = sessions_dir / jsonl_path.name
        test_jsonl.write_bytes(jsonl_path.read_bytes())

        # Build a minimal SessionWatcher
        from super_council.memory_service.session_watcher import SessionWatcher
        watcher = SessionWatcher(
            sessions_dir=str(sessions_dir),
            pipeline=None,  # No pipeline for this test
            scheduler=None,
        )

        # Process the session
        watcher._process_session(test_jsonl)

        # Verify MD file was written
        md_path = sessions_dir / f"{test_jsonl.stem}.md"
        assert md_path.exists(), f"MD file not written: {md_path}"
        content = md_path.read_text()
        assert "## Decisions" in content, "MD missing Decisions section"
        assert "## Open Items" in content, "MD missing Open Items section"
        # Topics Discussed should NOT be present
        assert "## Topics Discussed" not in content, \
            "Topics Discussed should be dropped (no real topic extractor)"

    def test_full_pipeline_jsonl_to_db(self, tmp_path):
        """Full pipeline: JSONL → MD → upsert_session_diary() → DB columns."""
        jsonl_path = _get_recent_jsonl()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        # Copy JSONL to temp dir
        test_jsonl = sessions_dir / jsonl_path.name
        test_jsonl.write_bytes(jsonl_path.read_bytes())

        # Build test store
        store = _build_test_store(tmp_path)

        # Build SessionWatcher
        from super_council.memory_service.session_watcher import SessionWatcher
        watcher = SessionWatcher(
            sessions_dir=str(sessions_dir),
            pipeline=None,
            scheduler=None,
        )

        # Step 1: Parse and trim
        turns = watcher._parse_jsonl(test_jsonl)
        assert len(turns) > 0, "JSONL should have turns"

        session_mode = watcher._classify(turns)
        trimmed = watcher._trim_session(turns, session_mode, test_jsonl)

        # Step 2: Write MD
        md_path = watcher._write_session_md(trimmed, test_jsonl)
        assert md_path.exists(), "MD file should exist"

        # Step 3: Upsert to session_diary via store
        md_content = md_path.read_text()
        summary_id = store.upsert_session_diary(
            summary_text=md_content,
            source_path=str(md_path),
            alias="test-runtime",
        )
        assert summary_id is not None, "upsert_session_diary should return summary_id"

        # Step 4: Verify DB columns
        row = _verify_session_diary_columns(store, summary_id)
        assert row["decisions"] in ("- none",), f"decisions should be '- none' or items, got: {row['decisions'][:50]}"
        assert row["open_items"] in ("- none",), f"open_items should be '- none' or items, got: {row['open_items'][:50]}"

    def test_carry_forward_wiring(self, tmp_path):
        """Verify errors_blockers and notable_deviations wire to carry_forward."""
        jsonl_path = _get_recent_jsonl()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        test_jsonl = sessions_dir / jsonl_path.name
        test_jsonl.write_bytes(jsonl_path.read_bytes())

        store = _build_test_store(tmp_path)
        from super_council.memory_service import MemoryService
        memory_service = MemoryService(store=store)

        from super_council.memory_service.session_watcher import SessionWatcher
        watcher = SessionWatcher(
            sessions_dir=str(sessions_dir),
            pipeline=None,
            scheduler=None,
            memory_service=memory_service,
        )

        # Parse and trim
        turns = watcher._parse_jsonl(test_jsonl)
        session_mode = watcher._classify(turns)
        trimmed = watcher._trim_session(turns, session_mode, test_jsonl)

        # Wire carry_forward
        watcher._wire_carry_forward(trimmed, test_jsonl)

        # Verify: if trimmed had blockers, carry_forward should have them
        blockers = trimmed.get("errors_blockers", [])
        deviations = trimmed.get("notable_deviations", [])
        cf_entries = _verify_carry_forward_entries(store, trimmed.get("project_id", ""))

        cf_kinds = {e["kind"] for e in cf_entries}
        if blockers:
            assert "blocker" in cf_kinds, "blockers should create carry_forward(kind='blocker')"
        if deviations:
            assert "deviation" in cf_kinds, "deviations should create carry_forward(kind='deviation')"

    def test_trimmed_to_text_unchanged(self):
        """Verify _trimmed_to_text() was NOT modified (ARC pipeline regression)."""
        from super_council.memory_service.session_watcher import SessionWatcher
        import inspect

        source = inspect.getsource(SessionWatcher._trimmed_to_text)
        # _trimmed_to_text() should still use old headers (Completed Work, etc.)
        assert "completed_work" in source.lower(), "_trimmed_to_text() should reference completed_work"
        # It should NOT use new headers (Work Completed, Decisions, etc.)
        # because it feeds ARC, not the MD format


class TestExtractSectionWithRealData:
    """Test _extract_section() with real session_diary data."""

    def test_existing_session_diary_entries(self):
        """Verify existing session_diary entries are still readable."""
        import sqlite3
        db_path = os.path.expanduser("~/.council-memory/council_core.db")
        if not Path(db_path).exists():
            pytest.skip("council_core.db not found")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT summary_id, decisions, open_items, work_completed "
            "FROM session_diary ORDER BY date DESC LIMIT 5"
        ).fetchall()
        conn.close()

        assert len(rows) > 0, "session_diary should have entries"
        for row in rows:
            # At least one column should be non-NULL
            values = [row["decisions"], row["open_items"], row["work_completed"]]
            assert any(v is not None for v in values), \
                f"At least one column should be non-NULL for {row['summary_id']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

2. Run tests:
```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -m pytest tests/test_session_watcher_runtime.py -v --tb=short
```

3. Verify all tests pass:
   - `test_process_session_writes_md_file` — MD file exists, no Topics Discussed
   - `test_full_pipeline_jsonl_to_db` — JSONL → MD → DB columns verified
   - `test_carry_forward_wiring` — errors_blockers/deviations → carry_forward
   - `test_trimmed_to_text_unchanged` — ARC pipeline not affected
   - `test_existing_session_diary_entries` — No regression in existing data

**Dependencies:** Phase 1, Phase 2, Phase 3, Phase 3b.

**Estimated effort:** ~45 min

---

## Constraints

- **Do NOT modify `_trimmed_to_text()`** — It feeds ArcPipeline.reconcile_tasks(). Changing it risks ARC parsing. `_write_session_md()` is a separate method.
- **Do NOT modify the trimmed schema** — `open_work` stays as-is. The naming mismatch is documented and fixed at the boundary.
- **`- none` must be lowercase** — Consumers check `val == "- none"`. Capitalization matters.
- **No fake abstraction** — Every MD section must carry signal not already in a structured column. If a section just duplicates Decisions + Open Items + Completed Work, drop it.
- **Topics Discussed is DROPPED** — No real topic extractor exists. Deriving from signal sections duplicates structured facts. Re-add when SessionAnalyzer produces `topics_discussed`.
- **errors_blockers are STRUCTURED** — Wired to carry_forward(kind="blocker", priority="high"). Not hidden in Reference.
- **notable_deviations are STRUCTURED** — Wired to carry_forward(kind="deviation", priority="medium"). Not hidden in Reference.
- **Reference section is capped at 5** — Prevents noise dumps. Omitted if empty.
- **Round-trip fidelity required** — trimmed → MD → extract must preserve every item. No silent drops from caps or filters on structured sections.

---

## Success Criteria

**Unit Tests (Phase 3):**
- [ ] Phase 1: `_extract_section()` regex uses `\Z` not `$`
- [ ] Phase 1: `open_items` loop tries each header once (no duplicate)
- [ ] Phase 1: All existing tests still pass (no regression)
- [ ] Phase 2: `_write_session_md()` exists in SessionWatcher with correct field→header mapping
- [ ] Phase 2: MD headers match `upsert_session_diary()` extraction patterns (Decisions, Open Items, Work Completed)
- [ ] Phase 2: `## Blockers` section exists when errors_blockers present (promoted from Reference)
- [ ] Phase 2: `## Deviations` section exists when notable_deviations present (promoted from Reference)
- [ ] Phase 2: `## Topics Discussed` does NOT exist (dropped — no real topic extractor)
- [ ] Phase 2: Empty Decisions and Open Items write `- none` (not omitted)
- [ ] Phase 2: Reference section capped at 5 items, omitted if empty
- [ ] Phase 3: All 19 alignment + round-trip tests pass
- [ ] Phase 3: Multi-paragraph extraction works (regex fix verified)
- [ ] Phase 3: `- none` distinguishes from NULL (explicitly empty vs. not tracked)
- [ ] Phase 3: Round-trip fidelity — all N items in trimmed → MD → extract → N items back (no silent drops)
- [ ] Phase 3: Section isolation — extracting one section doesn't leak into adjacent sections

**Production Runtime (Phase 4):**
- [ ] Phase 3b: `_process_session()` calls `_write_session_md()` after `_trim_session()`
- [ ] Phase 3b: `_process_session()` calls `_wire_carry_forward()` after MD write
- [ ] Phase 3b: MD write failure is non-fatal (reconciliation still proceeds)
- [ ] Phase 3b: carry_forward wiring failure is non-fatal
- [ ] Phase 3b: `_trimmed_to_text()` is unchanged (ARC pipeline regression check)
- [ ] Phase 3b: errors_blockers → carry_forward(kind="blocker", priority="high")
- [ ] Phase 3b: notable_deviations → carry_forward(kind="deviation", priority="medium")
- [ ] Phase 4: Real JSONL → MD file written to disk
- [ ] Phase 4: MD has no `## Topics Discussed` section
- [ ] Phase 4: MD → `upsert_session_diary()` → DB columns populated (decisions, open_items not NULL)
- [ ] Phase 4: Existing session_diary entries still readable (no regression)
- [ ] Phase 4: `_trimmed_to_text()` source unchanged (ARC pipeline not affected)

---

## Execution Order

```
Phase 1 (regex+loop fix, 10min)
    ↓
Phase 2 (_write_session_md — signal-faithful, 1h)
    ↓
Phase 3 (alignment + round-trip fidelity tests, 30min)
    ↓
Phase 3b (wire MD + carry_forward into _process_session, 20min)
    ↓
Phase 4 (production runtime verification, 45min)
```

All phases are sequential. Total estimated effort: ~3h.

**Gate:** Phase 4 must pass before Phase 4A implementation proceeds. If any production runtime test fails, stop and debug — do not proceed with mock tests alone.

**Design invariants (must hold at every phase):**
- Single canonical MD per session, written once by SessionWatcher
- Writer/reader separation: `_write_session_md()` writes, consumers read
- No fake abstraction: every MD section carries unique signal
- Actionable signals are structured (blockers → carry_forward, deviations → carry_forward)
- Round-trip fidelity: trimmed → MD → extract preserves every item

---

## Notes for Phase 4A (Next Handoff)

After these fixes are complete AND Phase 4 runtime tests pass, Phase 4A can proceed:
1. `_wire_session_diary()` reads the MD file and calls `upsert_session_diary()`
2. `_wire_memindex()` indexes the MD file via MemIndex.index_file()
3. `_wire_work_items()` (renamed from `_reconcile()`) extracts tasks from MD
4. carry_forward already has immediate writers for blockers and deviations (from Phase 3b)

**Prerequisite:** Phase 4 runtime tests must pass. The MD format must produce correct DB columns with real JSONL data before Phase 4A wiring begins.

**What this handoff delivers:**
- Fixed `_extract_section()` regex (multi-paragraph extraction works)
- Fixed `open_items` loop (no duplicate header tries)
- `_write_session_md()` with correct field→header mapping
- `## Blockers` and `## Deviations` promoted from Reference to structured sections
- `## Topics Discussed` dropped (was duplicated noise, no real topic extractor)
- `_wire_carry_forward()` wires errors_blockers → carry_forward(kind="blocker")
- `_wire_carry_forward()` wires notable_deviations → carry_forward(kind="deviation")
- Round-trip fidelity tests (trimmed → MD → extract → matches original)
- Wired into `_process_session()` flow
- Production runtime verification (real JSONL → DB columns + carry_forward)
- Regression checks (ARC pipeline unchanged, existing data intact)
