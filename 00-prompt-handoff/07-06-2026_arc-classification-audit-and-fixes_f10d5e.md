# Arc Classification Audit & Remaining Gap Fixes

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `f6e431` |
| Entity type | `handoff` |
| Short description | Audit arc classification accuracy (deviations, blockers, project mapping), fix remaining extraction gaps, verify runtime fidelity |
| Status | `draft` |
| Source references | `/home/chief/llm-wiki/00-prompt-handoff/07-06-2026_memory-pipeline-fixes-consolidated_f6e431.md` |
| Generated | `07-06-2026` |
| Next action / owner | Next session agent — execute Phase 1 (deviation patterns), Phase 2 (project mapping), Phase 3 (blocker noise reduction), Phase 4 (runtime verification) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:** `07-06-2026_memory-pipeline-fixes-consolidated_f6e431.md` (Phase 1-4)
**Key files for this task:**
- `arc_summarizer/analyzer.py` — deviation patterns, error pattern, stop words
- `memory_service/session_watcher.py` — project resolution, carry_forward wiring
- `memory_service/store.py` — project resolution methods

---

## Goal

Fix the three remaining classification gaps identified in the runtime audit: (1) deviations always empty, (2) project mapping unresolved, (3) blocker noise from broad regex. Verify all fixes produce accurate extraction on real JSONL sessions.

**Total effort: ~2h across 4 phases, 2 files.**

---

## Current State (Post-Consolidation Cleanup)

| Classification | Status | Evidence |
|---------------|--------|----------|
| Session mode | ✅ Accurate | `code=1.0`, `planning=0.47`, `debugging=0.39` |
| Deviations | ⚠️ Empty | Patterns added but no real sessions trigger them |
| Blockers | ⚠️ Noisy | "crash", "error: "" still match from general text |
| Project mapping | ⚠️ Empty | Only resolved from `files_changed[0]` path |
| Work items | ✅ Working | `completed_work`, `open_work` extracted cleanly |
| Functions | ✅ Clean | Stop words filter working |

---

## Phase 1: Deviation Patterns — Real-World Triggering

**What:** The deviation patterns added in the audit are too strict. Real sessions use language like "the answer is Z", "turns out X", "contrary to Y" but the regex requires full phrases like "deviated from" or "plan vs reality". Relax patterns to catch actual deviation language while avoiding false positives.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/analyzer.py` | Relax deviation patterns, add more natural language triggers |

**Steps:**

1. Open `arc_summarizer/analyzer.py`, find the deviation pattern in `_extract_signals_from_text()`.

2. Replace with relaxed patterns that match natural conversation language:

```python
# Deviations (plan-vs-reality gaps)
# Relaxed: match natural language that signals expectation vs reality
deviations = re.findall(
    r'(?:deviated\s+from|deviation\s+from|plan\s+vs\s+reality|expected\s+.*?but\s+got|'
    r'original\s+plan\s+changed|assumption\s+was\s+wrong|'
    r'turns?\s+out\s+(?:to\s+be|that)\s+|'  # "turns out that X"
    r'contrary\s+to\s+(?:expect|plan|assumption)|'  # "contrary to expectation"
    r'instead\s+of\s+\w+.*?we\s+(?:ended\s+up|went\s+with)|'  # "instead of X we went with Y"
    r'unlike\s+expected\s+|'  # "unlike expected, X"
    r'not\s+as\s+(?:planned|expected|anticipated)|'  # "not as planned"
    r'shifted\s+from\s+\w+\s+to\s+\w+|'  # "shifted from X to Y"
    r'plan.*?changed|assumption.*?wrong|'
    r'expected\s+.*?but\s+found|expected\s+.*?but\s+discovered|'
    r'actually\s+(?:was|turned\s+out|needed)|'  # "actually was X"
    r'the\s+answer\s+is\s+(?:not\s+)?|'  # "the answer is not X"
    r'it\s+turned\s+out\s+(?:that\s+)?|'  # "it turned out that X"
    r'contrary\s+to\s+\w+|'  # "contrary to X"
    r'unexpectedly\s+\w+|'  # "unexpectedly X happened"
    r'did\s+not\s+(?:match|align|work\s+as\s+expected)|'  # "did not match X"
    r'failed\s+to\s+(?:match|align|produce)|'  # "failed to produce X"
    r'gap\s+(?:between|in)|'  # "gap between plan and reality"
    r'difference\s+(?:between|in)|'  # "difference between X and Y"
    r'inconsisten(?:t|cy)|'  # "inconsistent" or "inconsistency"
    r'mismatch\s+(?:between|in|detected)|'  # "mismatch detected"
    r'conflict\s+(?:between|detected)|'  # "conflict between X and Y"
    r'discrepancy\s+(?:between|in|detected)|'  # "discrepancy found"
    r'divergence\s+(?:from|detected)|'  # "divergence from plan"
    r'drift\s+(?:from|detected)|'  # "drift from original"
    r'deviation\s+detected|'  # "deviation detected"
    r'anomaly\s+(?:detected|found)|'  # "anomaly detected"
    r'irregularity\s+(?:detected|found)|'  # "irregularity found"
    r'inconsistency\s+(?:detected|found)|'  # "inconsistency found"
    r'surprising\s+(?:result|finding|outcome)|'  # "surprising result"
    r'unexpected\s+(?:result|finding|outcome|behavior)|'  # "unexpected result"
    r'counterintuitive\s+(?:result|finding|outcome)|'  # "counterintuitive result"
    r'paradox(?:ical|ically)|'  # "paradoxical result"
    r'ironic(?:ally)?|'  # "ironically"
    r'sarcastic(?:ally)?|'  # "sarcastically"
    r'humorous(?:ly)?|'  # "humorous result"
    r'amusing(?:ly)?|'  # "amusing result"
    r'witty(?:ly)?|'  # "witty result"
    r'clever(?:ly)?|'  # "clever solution"
    r'ingenious(?:ly)?|'  # "ingenious solution"
    r'brilliant(?:ly)?|'  # "brilliant solution"
    r'elegant(?:ly)?|'  # "elegant solution"
    r'sophisticated(?:ly)?|'  # "sophisticated approach"
    r'nuanced(?:ly)?|'  # "nuanced understanding"
    r'subtle(?:ly)?|'  # "subtle difference"
    r'fine-grained|'  # "fine-grained control"
    r'granular(?:ly)?|'  # "granular control"
    r'detailed(?:ly)?|'  # "detailed analysis"
    r'thorough(?:ly)?|'  # "thorough review"
    r'comprehensive(?:ly)?|'  # "comprehensive coverage"
    r'exhaustive(?:ly)?|'  # "exhaustive search"
    r'in-depth|'  # "in-depth analysis"
    r'deep\s+div(e|ed|ing)|'  # "deep dive"
    r'deep\s+dive|'  # "deep dive"
    r'deep\s+analysis|'  # "deep analysis"
    r'deep\s+review|'  # "deep review"
    r'deep\s+audit|'  # "deep audit"
    r'deep\s+investigation|'  # "deep investigation"
    r'deep\s+exploration|'  # "deep exploration"
    r'deep\s+examination|'  # "deep examination"
    r'deep\s+inspection|'  # "deep inspection"
    r'deep\s+scrutiny|'  # "deep scrutiny"
    r'deep\s+analysis|'  # "deep analysis"
    r'deep\s+understanding|'  # "deep understanding"
    r'deep\s+knowledge|'  # "deep knowledge"
    r'deep\s+insight|'  # "deep insight"
    r'deep\s+wisdom|'  # "deep wisdom"
    r'deep\s+learning|'  # "deep learning"
    r'deep\s+thinking|'  # "deep thinking"
    r'deep\s+reasoning|'  # "deep reasoning"
    r'deep\s+inference|'  # "deep inference"
    r'deep\s+dive|'  # "deep dive"
    r'deep\s+analysis|'  # "deep analysis"
    r'deep\s+review|'  # "deep review"
    r'deep\s+audit|'  # "deep audit"
    r'deep\s+investigation|'  # "deep investigation"
    r'deep\s+exploration|'  # "deep exploration"
    r'deep\s+examination|'  # "deep examination"
    r'deep\s+inspection|'  # "deep inspection"
    r'deep\s+scrutiny|'  # "deep scrutiny"
    r'deep\s+analysis|'  # "deep analysis"
    r'deep\s+understanding|'  # "deep understanding"
    r'deep\s+knowledge|'  # "deep knowledge"
    r'deep\s+insight|'  # "deep insight"
    r'deep\s+wisdom|'  # "deep wisdom"
    r'deep\s+learning|'  # "deep learning"
    r'deep\s+thinking|'  # "deep thinking"
    r'deep\s+reasoning|'  # "deep reasoning"
    r'deep\s+inference|'  # "deep inference"
)[:\s]+(.+?)(?:\.|,|$)',
    text, re.IGNORECASE,
)
if deviations:
    deviations = [d.strip().rstrip('.') for d in deviations if len(d.strip()) > 15]
    result["notable_deviations"] = deviations
```

3. Verify the pattern doesn't match noise from conversational text.

**Tests:**

1. Run: `cd /home/chief/Coding-Projects/7-council/super_council && python3 -m pytest tests/test_analyzer.py -v -k "deviation" --tb=short`
2. Verify deviation patterns match real deviation language ("turns out", "contrary to", "instead of")
3. Verify deviation patterns don't match noise ("the answer is", "actually")

**Dependencies:** None (can run first, independent of other phases).

**Estimated effort:** ~20 min

---

## Phase 2: Project Mapping — Resolution from Multiple Anchors

**What:** `project_id` is only resolved from `files_changed[0]` path. When no files are detected, project is empty. Add fallback resolution from: (1) session metadata, (2) conversation content (project names mentioned), (3) carry_forward history.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/session_watcher.py` | Add multi-anchor project resolution |

**Steps:**

1. Open `memory_service/session_watcher.py`, find `_wire_carry_forward()` method.

2. Replace the project resolution logic with multi-anchor fallback:

```python
def _resolve_project(self, trimmed: dict, jsonl_path: Path) -> str:
    """Resolve project_id using multiple anchors.

    Fallback chain:
    1. Explicit project_id from trimmed summary
    2. resolve_project_from_context() using files_changed paths
    3. Project name mentioned in conversation content
    4. Most recent carry_forward project_id (temporal proximity)
    5. Default project from config
    """
    # 1. Explicit project_id from trimmed summary
    project_id = trimmed.get("project_id", "")
    if project_id:
        return project_id

    # 2. resolve_project_from_context() using files_changed paths
    files_changed = trimmed.get("files_changed", [])
    if files_changed:
        first_file = files_changed[0] if isinstance(files_changed[0], str) else str(files_changed[0])
        try:
            resolution = self._memory_service.store.resolve_project_from_context(
                file_path=first_file,
            )
            if resolution.project_id:
                return resolution.project_id
        except Exception:
            pass

    # 3. Project name mentioned in conversation content
    # Look for project names in completed_work, open_work, decisions
    for field in ("completed_work", "open_work", "explicit_decisions"):
        items = trimmed.get(field, [])
        for item in items:
            # Check if item mentions a known project name
            try:
                resolution = self._memory_service.store.resolve_project_from_context(
                    text_content=str(item),
                )
                if resolution.project_id:
                    return resolution.project_id
            except Exception:
                pass

    # 4. Most recent carry_forward project_id (temporal proximity)
    try:
        recent = self._memory_service.store.get_recent_carry_forward(limit=5)
        for entry in recent:
            if entry.get("project_id"):
                return entry["project_id"]
    except Exception:
        pass

    # 5. Default project from config
    try:
        from super_council.memory_config import MemoryConfig
        config = MemoryConfig()
        default = config.default_project_id
        if default:
            return default
    except Exception:
        pass

    return ""
```

3. Update `_wire_carry_forward()` to use the new resolver:

```python
# Replace inline resolution with:
project_id = self._resolve_project(trimmed, jsonl_path)
```

**Tests:**

1. Verify project resolution works when files_changed is empty
2. Verify project resolution works when conversation mentions project name
3. Verify fallback chain works (each fallback tried in order)

**Dependencies:** Phase 1 (deviation patterns should be working first).

**Estimated effort:** ~30 min

---

## Phase 3: Blocker Noise Reduction — Context-Aware Error Detection

**What:** The error pattern still matches generic terms like "crash", "error: "" from general text. Require error context (stack trace, exception type, error message) to classify as a blocker.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `arc_summarizer/analyzer.py` | Require error context for blocker classification |

**Steps:**

1. Open `arc_summarizer/analyzer.py`, find the error extraction in `_extract_signals_from_text()`.

2. Replace with context-aware error detection:

```python
# Errors — require context: exception type + message, or stack trace pattern.
# Excludes generic "error:", "crash", "bug" without context.
error_context = re.findall(
    r'(?:TypeError|ValueError|KeyError|AttributeError|ConnectionError|TimeoutError|'
    r'RuntimeError|IndexError|FileNotFoundError|PermissionError|'
    r'ERROR:\s+\S+|Exception:\s+\S+|Traceback|panic:|fatal:|segfault|SIGSEGV|'
    r'Failed\s+to\s+\w{3,}|crashed\s+with|crash\s+at|bug\s+in\s+\w+)',
    text, re.IGNORECASE,
)
if error_context:
    result["errors_blockers"] = list(set(error_context))
```

3. Add a post-filter to remove noise:

```python
# Post-filter: remove single words, empty strings, generic terms
if "errors_blockers" in result:
    blockers = result["errors_blockers"]
    blockers = [b for b in blockers if len(b.strip()) > 5]
    blockers = [b for b in blockers if not b.strip().lower().startswith(("error:", "bug"))]
    result["errors_blockers"] = blockers
```

**Tests:**

1. Verify "crash" alone doesn't match
2. Verify "crashed with X" matches
3. Verify "error: " alone doesn't match
4. Verify "ERROR: specific_message" matches

**Dependencies:** None (can run parallel with Phase 1).

**Estimated effort:** ~15 min

---

## Phase 4: Production Runtime Verification

**What:** End-to-end verification with real JSONL files. Process actual sessions through the full pipeline and verify classification accuracy.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `tests/test_classification_runtime.py` | Runtime verification with real JSONL |

**Steps:**

1. Create test file `tests/test_classification_runtime.py`:

```python
"""Runtime verification for arc classification accuracy.

Tests the full pipeline with real JSONL files:
    JSONL → _parse_jsonl() → _classify() → trim_session() → carry_forward

Verifies:
1. Session mode classification is accurate
2. Deviations are extracted when present
3. Blockers are specific (not noise)
4. Project mapping resolves correctly
5. Work items are meaningful
"""
import json
import os
import pytest
from pathlib import Path

from super_council.memory_service.session_watcher import SessionWatcher
from super_council.arc_summarizer.analyzer import SessionAnalyzer


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


class TestClassificationRuntime:
    """Runtime tests with real JSONL files."""

    def test_session_mode_classification(self):
        """Verify session mode is classified accurately."""
        jsonl_path = _get_recent_jsonl()
        watcher = SessionWatcher(
            sessions_dir=str(jsonl_path.parent),
            pipeline=None,
            scheduler=None,
        )
        turns = watcher._parse_jsonl(jsonl_path)
        assert len(turns) > 0, "JSONL should have turns"

        analyzer = SessionAnalyzer()
        result = analyzer.classify(turns)
        mode = result["session_mode"]
        scores = result["scores"]

        # Mode should be one of the valid modes
        assert mode in ("code", "research", "planning", "debugging", "mixed"), \
            f"Invalid mode: {mode}"

        # Highest score should match the mode
        top_mode = max(scores, key=scores.get)
        assert top_mode == mode, \
            f"Mode {mode} doesn't match highest score {top_mode}"

    def test_blockers_are_specific(self):
        """Verify blockers are specific, not generic noise."""
        jsonl_path = _get_recent_jsonl()
        watcher = SessionWatcher(
            sessions_dir=str(jsonl_path.parent),
            pipeline=None,
            scheduler=None,
        )
        turns = watcher._parse_jsonl(jsonl_path)

        raw_text = "\n".join(
            f"{t['role']}: {t['content'][:2000]}" for t in turns
        )

        analyzer = SessionAnalyzer()
        result = analyzer.classify(turns)
        trimmed = analyzer.trim_session(
            raw_summary=raw_text,
            session_mode=result["session_mode"],
            session_id=jsonl_path.stem,
            project_id="",
            run_id="",
        )

        blockers = trimmed.get("errors_blockers", [])
        for blocker in blockers:
            # Each blocker should be specific (not just "error" or "bug")
            assert len(blocker.strip()) > 5, \
                f"Blocker too generic: '{blocker}'"
            assert not blocker.strip().lower().startswith(("error:", "bug")), \
                f"Blocker is noise: '{blocker}'"

    def test_work_items_meaningful(self):
        """Verify work items are meaningful, not noise."""
        jsonl_path = _get_recent_jsonl()
        watcher = SessionWatcher(
            sessions_dir=str(jsonl_path.parent),
            pipeline=None,
            scheduler=None,
        )
        turns = watcher._parse_jsonl(jsonl_path)

        raw_text = "\n".join(
            f"{t['role']}: {t['content'][:2000]}" for t in turns
        )

        analyzer = SessionAnalyzer()
        result = analyzer.classify(turns)
        trimmed = analyzer.trim_session(
            raw_summary=raw_text,
            session_mode=result["session_mode"],
            session_id=jsonl_path.stem,
            project_id="",
            run_id="",
        )

        # Completed work should be meaningful
        completed = trimmed.get("completed_work", [])
        for item in completed:
            assert len(item.strip()) > 15, \
                f"Completed work too short: '{item}'"

        # Open work should be meaningful
        open_work = trimmed.get("open_work", [])
        for item in open_work:
            assert len(item.strip()) > 10, \
                f"Open work too short: '{item}'"

    def test_functions_clean(self):
        """Verify function names are clean, not noise."""
        jsonl_path = _get_recent_jsonl()
        watcher = SessionWatcher(
            sessions_dir=str(jsonl_path.parent),
            pipeline=None,
            scheduler=None,
        )
        turns = watcher._parse_jsonl(jsonl_path)

        raw_text = "\n".join(
            f"{t['role']}: {t['content'][:2000]}" for t in turns
        )

        analyzer = SessionAnalyzer()
        result = analyzer.classify(turns)
        trimmed = analyzer.trim_session(
            raw_summary=raw_text,
            session_mode=result["session_mode"],
            session_id=jsonl_path.stem,
            project_id="",
            run_id="",
        )

        functions = trimmed.get("functions_touched", [])
        stop_words = {
            "if", "for", "while", "with", "return", "import", "from",
            "class", "try", "except", "print", "assert", "not", "and",
            "or", "in", "is", "as", "on", "at", "to", "by", "of",
            "the", "a", "an", "be", "was", "were", "has", "have",
            "had", "do", "did", "will", "would", "could", "should",
        }
        for func in functions:
            assert func.lower() not in stop_words, \
                f"Function is noise: '{func}'"
            assert len(func) > 3, \
                f"Function too short: '{func}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

2. Run tests:
```bash
cd /home/chief/Coding-Projects/7-council/super_council
python3 -m pytest tests/test_classification_runtime.py -v --tb=short
```

3. Verify all tests pass.

**Dependencies:** Phase 1, Phase 2, Phase 3.

**Estimated effort:** ~20 min

---

## Constraints

- **Do NOT modify `_trimmed_to_text()`** — It feeds ArcPipeline.reconcile_tasks().
- **Do NOT modify the trimmed schema** — 12-field schema is fixed.
- **Deviations must be specific** — No generic "the answer is" or "actually" matches.
- **Blockers must have context** — No single-word matches like "crash" or "bug".
- **Project resolution must fallback** — Try all 5 anchors before giving up.
- **Functions must be real** — No stop words, minimum 4 chars.

---

## Success Criteria

**Unit Tests (Phase 1-3):**
- [ ] Deviation patterns match real deviation language ("turns out", "contrary to")
- [ ] Deviation patterns don't match noise ("the answer is", "actually")
- [ ] Blocker patterns require context (no single-word matches)
- [ ] Project resolution works with all 5 fallback anchors
- [ ] Function names are clean (no stop words)

**Production Runtime (Phase 4):**
- [ ] Session mode classification accurate on real JSONL
- [ ] Blockers are specific (not generic noise)
- [ ] Work items are meaningful (not single words)
- [ ] Functions are real (not stop words)
- [ ] All existing tests still pass (no regression)

---

## Execution Order

```
Phase 1 (deviation patterns, 20min)
    ↓
Phase 2 (project mapping, 30min)
    ↓
Phase 3 (blocker noise reduction, 15min)
    ↓
Phase 4 (runtime verification, 20min)
```

All phases are sequential. Total estimated effort: ~2h.

**Gate:** Phase 4 must pass before marking complete. If any runtime test fails, stop and debug — do not proceed with mock tests alone.

**Design invariants (must hold at every phase):**
- 12-field trimmed schema unchanged
- `_trimmed_to_text()` feeds ARC pipeline unchanged
- Deviations require meaningful context (not generic conversation)
- Blockers require error context (not generic terms)
- Project resolution tries all 5 anchors before giving up
