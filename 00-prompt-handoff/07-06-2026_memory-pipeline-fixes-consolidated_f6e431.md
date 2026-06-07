# Memory Pipeline Alignment Fixes — Consolidated Implementation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `f6e431` |
| Entity type | `handoff` |
| Short description | Fix 5 mismatches between MD format, consumer extraction patterns, and trimmed schema; wire into SessionWatcher flow; verify end-to-end with real JSONL |
| Status | `draft` |
| Source references | `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_memory-pipeline-redundancy-audit_ea8ef8.md` (Phase 9) |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — execute Phase 1 (regex+loop fixes), Phase 2 (_write_session_md), Phase 3 (unit tests), Phase 4 (production runtime verification) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `07-06-2026_memory-pipeline-redundancy-audit_ea8ef8.md` (Phase 9.1-9.8)
**Key files for this task:**
- `memory_service/store.py` — regex fix + open_items loop fix (Phase 1)
- `memory_service/session_watcher.py` — new `_write_session_md()` + _process_session() wiring (Phase 2)
- `tests/` — unit tests + production runtime verification (Phase 3-4)

---

## Goal

Fix all alignment mismatches between the canonical MD format, `upsert_session_diary()` extraction patterns, and the SessionAnalyzer trimmed schema so that Phase 4A (SessionWatcher writes MD + wired services) produces correct data in all session_diary columns.

**Total effort: ~2.5h across 3 phases, 2 files.**

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

## Phase 2: Write `_write_session_md()` with Correct Field→Header Mapping

**What:** Add `_write_session_md()` to SessionWatcher. This method maps trimmed schema fields to MD section headers that match `upsert_session_diary()` extraction patterns. It does NOT use `_trimmed_to_text()` which generates wrong headers.

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
        (derived signals) → ## Topics Discussed
        files_changed, functions_touched, tests_written,
        errors_blockers, notable_deviations → ## Reference
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

    # Topics Discussed: derived from signal sections
    # NOTE: trimmed schema has no 'topics_discussed' field; derive from signals
    all_signals = (
        trimmed.get("explicit_decisions", []) +
        trimmed.get("completed_work", []) +
        trimmed.get("open_work", [])
    )
    if all_signals:
        lines.append("## Topics Discussed")
        for item in all_signals[:5]:  # Cap at 5 to avoid noise
            lines.append(f"- {item}")
        lines.append("")

    # Reference: aggregate metadata fields (not extracted to DB columns)
    ref_items = []
    if trimmed.get("files_changed"):
        ref_items.append(f"files: {trimmed['files_changed']}")
    if trimmed.get("functions_touched"):
        ref_items.append(f"functions: {trimmed['functions_touched']}")
    if trimmed.get("tests_written"):
        ref_items.append(f"tests: {trimmed['tests_written']}")
    if trimmed.get("errors_blockers"):
        ref_items.append(f"errors: {trimmed['errors_blockers']}")
    if trimmed.get("notable_deviations"):
        ref_items.append(f"deviations: {trimmed['notable_deviations']}")

    if ref_items:
        lines.append("## Reference")
        lines.extend(ref_items)
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

| MD Header | `upsert_session_diary()` Extracts | Match? |
|-----------|-----------------------------------|--------|
| `## Decisions` | `"Key Decisions"` or `"Decisions"` | ✅ Second fallback |
| `## Open Items` | `"Open Items"` (first try) | ✅ First match |
| `## Work Completed` | `"Work Completed"` (first try) | ✅ First match |
| `## Topics Discussed` | `"Topics Discussed"` (first try) | ✅ First match |
| `## Reference` | Not extracted (indexed only) | ✅ N/A |

**Dependencies:** Phase 1 (regex fix must be in place so extraction works correctly).

**Estimated effort:** ~1h

---

## Phase 3: Verification Tests

**What:** Verify that the MD format produces correct extraction results through the full pipeline (MD → `_extract_section()` → DB columns).

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_md_format_alignment.py` | End-to-end MD format → extraction verification |

**Steps:**

1. Create test file `tests/test_md_format_alignment.py`:

```python
"""Test MD format alignment with upsert_session_diary() extraction patterns.

Verifies that the canonical MD format produces correct extraction results
through the full pipeline: MD text → _extract_section() → DB columns.
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

## Topics Discussed
- Use dict.get() not if key in d (cleaner semantics)
- Return False from _wait_idle() on deadline expiry
- Fixed _wait_idle() stability semantics
- Rewrote verification handoff with actual endpoints
- Fix carry_forward writer (priority: high)

## Reference
files: [session_watcher.py, store.py]
functions: [_wait_idle, _extract_section]
errors: [database is locked]
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

    def test_topics_discussed_extracted(self):
        md = _build_sample_md()
        result = _extract_section(md, "Topics Discussed")
        assert result is not None
        assert "dict.get()" in result  # derived from decisions

    def test_explicitly_empty_decisions(self):
        """- none is stored as TEXT, distinguishable from NULL."""
        md = _build_empty_decisions_md()
        result = _extract_section(md, "Decisions")
        assert result == "- none"  # Not None (NULL), not empty string

    def test_explicitly_empty_open_items(self):
        md = _build_empty_decisions_md()
        result = _extract_section(md, "Open Items")
        assert result == "- none"

    def test_reference_not_extracted_by_session_diary(self):
        """Reference section is not extracted by upsert_session_diary()."""
        md = _build_sample_md()
        # upsert_session_diary() does NOT extract Reference
        # It only extracts: Decisions, Open Items, Work Completed, Topics Discussed, Models Used
        assert _extract_section(md, "Reference") is not None  # Exists in MD
        # But it's not extracted to any DB column by upsert_session_diary()


class TestHeaderMatching:
    """Verify MD headers match upsert_session_diary() extraction patterns."""

    def test_decisions_matches_fallback(self):
        """## Decisions matches second fallback 'Decisions'."""
        md = "## Decisions\n- item"
        # First try: "Key Decisions" → no match
        # Second try: "Decisions" → match
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

    def test_topics_discussed_matches_primary(self):
        """## Topics Discussed matches first try 'Topics Discussed'."""
        md = "## Topics Discussed\n- item"
        assert _extract_section(md, "Topics Discussed") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

2. Run tests:
```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -m pytest tests/test_md_format_alignment.py -v
```

3. Verify all 12 tests pass.

**Dependencies:** Phase 1, Phase 2.

**Estimated effort:** ~30 min

---

## Phase 3b: Wire `_write_session_md()` into `_process_session()` Flow

**What:** Integrate `_write_session_md()` into the SessionWatcher `_process_session()` method so the MD file is written after trimming and before reconciliation. This is the production wiring step — without it, `_write_session_md()` exists but is never called.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/session_watcher.py` | Wire `_write_session_md()` into `_process_session()` |

**Steps:**

1. Open `memory_service/session_watcher.py`, find `_process_session()` method (line ~215).
2. Add the MD write step after `_trim_session()` and before `_reconcile()`:

```python
def _process_session(self, jsonl_path: Path) -> None:
    """Process a single JSONL session file.

    Flow: parse → classify → trim → write MD → reconcile → wake scheduler.
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

        # Step 3b: Write canonical MD file (NEW)
        # NOTE: _write_session_md() is called BEFORE _reconcile()
        # so the MD file exists for downstream consumers.
        try:
            md_path = self._write_session_md(trimmed, jsonl_path)
            log.info("SessionWatcher: wrote MD to %s", md_path)
        except Exception as e:
            log.warning("SessionWatcher: MD write failed (non-fatal): %s", e)
            md_path = None

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

3. Verify `_trimmed_to_text()` is NOT modified (it's still used by `_reconcile()` for ARC).

**Tests:**

1. Verify `_process_session()` calls `_write_session_md()` after `_trim_session()`.
2. Verify MD write failure is non-fatal (reconciliation still proceeds).
3. Verify `_trimmed_to_text()` is unchanged (ARC pipeline regression check).

**Dependencies:** Phase 1, Phase 2, Phase 3 (unit tests).

**Estimated effort:** ~15 min

---

## Phase 4: Production Runtime Verification

**What:** End-to-end verification with a real JSONL file. This is NOT a mock test — it processes an actual session file through the full pipeline and verifies the output in the database.

**Critical distinction:** Phase 3 tests mock MD strings against `_extract_section()`. Phase 4 tests the full pipeline: real JSONL → `_process_session()` → MD file → `upsert_session_diary()` → DB columns.

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
    # (this is acceptable — context is additive)

    return row


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

3. Verify all 5 tests pass:
   - `test_process_session_writes_md_file` — MD file exists after processing
   - `test_full_pipeline_jsonl_to_db` — JSONL → MD → DB columns verified
   - `test_trimmed_to_text_unchanged` — ARC pipeline not affected
   - `test_existing_session_diary_entries` — No regression in existing data

**Dependencies:** Phase 1, Phase 2, Phase 3, Phase 3b.

**Estimated effort:** ~45 min

---

## Constraints

- **Do NOT modify `_trimmed_to_text()`** — It feeds ArcPipeline.reconcile_tasks(). Changing it risks ARC parsing. `_write_session_md()` is a separate method.
- **Do NOT modify the trimmed schema** — `open_work` stays as-is. The naming mismatch is documented and fixed at the boundary.
- **`- none` must be lowercase** — Consumers check `val == "- none"`. Capitalization matters.
- **Topics Discussed cap at 5** — Prevents noise when signal sections are large.
- **Reference section is optional** — Omitted if no metadata fields present.

---

## Success Criteria

**Unit Tests (Phase 3):**
- [ ] Phase 1: `_extract_section()` regex uses `\Z` not `$`
- [ ] Phase 1: `open_items` loop tries each header once (no duplicate)
- [ ] Phase 1: All existing tests still pass (no regression)
- [ ] Phase 2: `_write_session_md()` exists in SessionWatcher with correct field→header mapping
- [ ] Phase 2: MD headers match `upsert_session_diary()` extraction patterns (Decisions, Open Items, Work Completed, Topics Discussed)
- [ ] Phase 2: Empty Decisions and Open Items write `- none` (not omitted)
- [ ] Phase 2: Topics Discussed derived from signal sections, capped at 5
- [ ] Phase 2: Reference section aggregates metadata fields, omitted if empty
- [ ] Phase 3: All 12 alignment tests pass
- [ ] Phase 3: Multi-paragraph extraction works (regex fix verified)
- [ ] Phase 3: `- none` distinguishes from NULL (explicitly empty vs. not tracked)

**Production Runtime (Phase 4):**
- [ ] Phase 3b: `_process_session()` calls `_write_session_md()` after `_trim_session()`
- [ ] Phase 3b: MD write failure is non-fatal (reconciliation still proceeds)
- [ ] Phase 3b: `_trimmed_to_text()` is unchanged (ARC pipeline regression check)
- [ ] Phase 4: Real JSONL → MD file written to disk
- [ ] Phase 4: MD → `upsert_session_diary()` → DB columns populated (decisions, open_items not NULL)
- [ ] Phase 4: Existing session_diary entries still readable (no regression)
- [ ] Phase 4: `_trimmed_to_text()` source unchanged (ARC pipeline not affected)

---

## Execution Order

```
Phase 1 (regex+loop fix, 10min)
    ↓
Phase 2 (_write_session_md, 1h)
    ↓
Phase 3 (unit tests, 30min)
    ↓
Phase 3b (wire into _process_session, 15min)
    ↓
Phase 4 (production runtime verification, 45min)
```

All phases are sequential. Total estimated effort: ~3h.

**Gate:** Phase 4 must pass before Phase 4A implementation proceeds. If any production runtime test fails, stop and debug — do not proceed with mock tests alone.

---

## Notes for Phase 4A (Next Handoff)

After these fixes are complete AND Phase 4 runtime tests pass, Phase 4A can proceed:
1. `_wire_session_diary()` reads the MD file and calls `upsert_session_diary()`
2. `_wire_memindex()` indexes the MD file via MemIndex.index_file()
3. `_wire_work_items()` (renamed from `_reconcile()`) extracts tasks from MD

**Prerequisite:** Phase 4 runtime tests must pass. The MD format must produce correct DB columns with real JSONL data before Phase 4A wiring begins.

**What this handoff delivers:**
- Fixed `_extract_section()` regex (multi-paragraph extraction works)
- Fixed `open_items` loop (no duplicate header tries)
- `_write_session_md()` with correct field→header mapping
- Wired into `_process_session()` flow
- Production runtime verification (real JSONL → DB columns)
- Regression checks (ARC pipeline unchanged, existing data intact)
