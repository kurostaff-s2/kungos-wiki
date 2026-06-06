# Phase 1: Session Analyzer + Trimmed Summary

**Parent plan:** `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`
**Phase:** 1 of 4
**Dependencies:** None (first phase)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/arc_summarizer/analyzer.py` (create — SessionAnalyzer class)
- `super_council/arc_summarizer/prompts.py` (modify — superset schema, mode-specific prompts)
- `super_council/arc_summarizer/client.py` (modify — mode-aware summarize_session())

---

## What This Phase Delivers

Heuristic session classifier that detects session mode from content signals. Generates trimmed summary with fixed 11-field schema. Integrates mode-aware summarization into ArcClient.

**Session modes:** `code`, `research`, `planning`, `debugging`, `mixed`
**Score vector:** Each mode gets 0.0-1.0 score. Highest wins. If two scores within 0.1, default to `mixed`.

---

## Pre-Flight Checklist

- [ ] No prior phases required
- [ ] Arc summarizer module exists at `super_council/arc_summarizer/`
- [ ] Existing tests pass (baseline: 495 passed)

---

## Implementation Steps

### Step 1: Create SessionAnalyzer Class

Add to `super_council/arc_summarizer/analyzer.py`:

```python
"""Session Analyzer — heuristic classifier + trimmed summary generator.

Detects session mode from content signals (code paths, errors, decisions,
URLs, planning verbs). Generates trimmed summary with fixed 11-field schema.

Heuristic-first: no extra model call for classification.
"""
import re
from typing import Dict, List, Optional, Tuple

# ── Signal Patterns ─────────────────────────────────────────────────────

CODE_SIGNALS = [
    r'\bdef\s+\w+',           # function definitions
    r'\bclass\s+\w+',          # class definitions
    r'\.py[":\s]',            # Python file references
    r'\.ts[":\s]',            # TypeScript file references
    r'\.js[":\s]',            # JavaScript file references
    r'import\s+',             # import statements
    r'from\s+\w+\s+import',   # from imports
    r'git\s+(add|commit|push|diff)',  # git commands
    r'pytest|unittest',       # test frameworks
    r'\bTODO\b|\bFIXME\b',    # code markers
]

RESEARCH_SIGNALS = [
    r'https?://\S+',          # URLs
    r'\b(?:RFC|PR|issue|PR\s+\d+)\b',  # references
    r'\b(?:search|lookup|find|explore)\b',  # research verbs
    r'\b(?:api|documentation|docs)\b',  # doc references
    r'\b(?:benchmark|compare|evaluate)\b',  # evaluation verbs
]

PLANNING_SIGNALS = [
    r'\b(?:plan|design|architecture|approach)\b',  # planning nouns
    r'\b(?:should|must|need to|will)\b',  # planning modals
    r'\b(?:trade-off|decision|option|alternative)\b',  # decision words
    r'\b(?:phase|stage|milestone|sprint)\b',  # planning structure
    r'\b(?:estimate|budget|timeline|deadline)\b',  # planning constraints
]

DEBUGGING_SIGNALS = [
    r'\b(?:error|exception|bug|crash|fail)\b',  # error words
    r'\b(?:traceback|stack\s*trace|core\s*dump)\b',  # debugging artifacts
    r'\b(?:root\s*cause|debug|investigate|diagnose)\b',  # debugging verbs
    r'\b(?:assert|assertion|invariant)\b',  # debugging tools
    r'Error:|Exception:|Traceback',  # error patterns
]

# ── Trimmed Summary Schema ──────────────────────────────────────────────

TRIMMED_SCHEMA_FIELDS = [
    'session_id', 'project_id', 'run_id', 'session_type',
    'files_changed', 'functions_touched', 'tests_written',
    'errors_blockers', 'explicit_decisions', 'completed_work',
    'open_work', 'notable_deviations',
]


class SessionAnalyzer:
    """Heuristic session classifier + trimmed summary generator.

    Detects session mode from content signals. Generates trimmed summary
    with fixed 11-field schema. No extra model call for classification.

    Usage:
        analyzer = SessionAnalyzer()
        mode, scores = analyzer.classify(raw_text)
        trimmed = analyzer.trim_session(raw_text, session_id, project_id)
    """

    def classify(self, text: str) -> Tuple[str, Dict[str, float]]:
        """Classify session mode from content signals.

        Args:
            text: Raw session summary or conversation text.

        Returns:
            (session_mode, score_vector) where score_vector is
            {code: float, research: float, planning: float, debugging: float, mixed: float}
        """
        if not text or not text.strip():
            return 'mixed', {'code': 0.0, 'research': 0.0, 'planning': 0.0, 'debugging': 0.0, 'mixed': 1.0}

        text_lower = text.lower()

        # Count signals for each mode
        code_score = self._count_signals(text_lower, CODE_SIGNALS)
        research_score = self._count_signals(text_lower, RESEARCH_SIGNALS)
        planning_score = self._count_signals(text_lower, PLANNING_SIGNALS)
        debugging_score = self._count_signals(text_lower, DEBUGGING_SIGNALS)

        # Normalize to 0.0-1.0 range (logarithmic scaling to prevent dominance)
        import math
        max_signals = max(code_score, research_score, planning_score, debugging_score, 1)
        code_norm = min(math.log1p(code_score) / math.log1p(max_signals), 1.0) if max_signals > 0 else 0.0
        research_norm = min(math.log1p(research_score) / math.log1p(max_signals), 1.0) if max_signals > 0 else 0.0
        planning_norm = min(math.log1p(planning_score) / math.log1p(max_signals), 1.0) if max_signals > 0 else 0.0
        debugging_norm = min(math.log1p(debugging_score) / math.log1p(max_signals), 1.0) if max_signals > 0 else 0.0

        scores = {
            'code': round(code_norm, 2),
            'research': round(research_norm, 2),
            'planning': round(planning_norm, 2),
            'debugging': round(debugging_norm, 2),
        }

        # Pick highest score
        best_mode = max(scores, key=scores.get)
        best_score = scores[best_mode]

        # Check if second-best is within 0.1 (fallback to mixed)
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2 and (sorted_scores[0] - sorted_scores[1]) < 0.1:
            scores['mixed'] = 1.0
            return 'mixed', scores

        scores['mixed'] = 0.0
        return best_mode, scores

    @staticmethod
    def _count_signals(text: str, patterns: List[str]) -> int:
        """Count matching signals in text."""
        count = 0
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            count += len(matches)
        return count

    def trim_session(
        self,
        raw_text: str,
        session_id: str = None,
        project_id: str = None,
        run_id: str = None,
    ) -> Dict[str, any]:
        """Generate trimmed summary from raw session text.

        Strips conversational noise, preserves task-bearing signals.
        Returns fixed-schema dict with 11 fields.

        Args:
            raw_text: Raw session summary or conversation text.
            session_id: Optional session identifier.
            project_id: Optional project identifier.
            run_id: Optional run identifier.

        Returns:
            Dict with fixed 11-field schema.
        """
        session_type, _ = self.classify(raw_text)

        # Extract signals using regex patterns
        files_changed = self._extract_files(raw_text)
        functions_touched = self._extract_functions(raw_text)
        tests_written = self._extract_tests(raw_text)
        errors_blockers = self._extract_errors(raw_text)
        decisions = self._extract_decisions(raw_text)
        completed_work = self._extract_completed(raw_text)
        open_work = self._extract_open_items(raw_text)
        deviations = self._extract_deviations(raw_text)

        return {
            'session_id': session_id,
            'project_id': project_id,
            'run_id': run_id,
            'session_type': session_type,
            'files_changed': files_changed,
            'functions_touched': functions_touched,
            'tests_written': tests_written,
            'errors_blockers': errors_blockers,
            'explicit_decisions': decisions,
            'completed_work': completed_work,
            'open_work': open_work,
            'notable_deviations': deviations,
            '_extra': {},  # Extensibility catch-all
        }

    @staticmethod
    def _extract_files(text: str) -> List[str]:
        """Extract file paths from text."""
        patterns = [
            r'(?:path|file|modified|changed|created)\s+[:=]?\s*([a-zA-Z0-9_/.-]+\.\w+)',
            r'`([a-zA-Z0-9_/.-]+\.\w+)`',
        ]
        files = []
        for pattern in patterns:
            files.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(files))  # Deduplicate

    @staticmethod
    def _extract_functions(text: str) -> List[str]:
        """Extract function/method names from text."""
        patterns = [
            r'\bdef\s+(\w+)',
            r'\bfunction\s+(\w+)',
            r'(?:function|method|func)\s+[:=]?\s*(\w+)',
        ]
        funcs = []
        for pattern in patterns:
            funcs.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(funcs))

    @staticmethod
    def _extract_tests(text: str) -> List[str]:
        """Extract test-related signals from text."""
        patterns = [
            r'(?:test|spec)\s+[:=]?\s*["\']?(\w+)',
            r'pytest\s+.*?(\w+)',
        ]
        tests = []
        for pattern in patterns:
            tests.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(tests))

    @staticmethod
    def _extract_errors(text: str) -> List[str]:
        """Extract error/blocker signals from text."""
        patterns = [
            r'(?:error|exception|bug|crash|fail(?:ed|ure)?|block(?:ed|er)?)\s*[:=]?\s*["\']?([^.]+)',
        ]
        errors = []
        for pattern in patterns:
            errors.extend(re.findall(pattern, text, re.IGNORECASE))
        return [e.strip() for e in set(errors) if e.strip()]

    @staticmethod
    def _extract_decisions(text: str) -> List[str]:
        """Extract explicit decisions from text."""
        patterns = [
            r'(?:decision|decided|chose|selected|went with)\s*[:=]?\s*["\']?([^.]+)',
        ]
        decisions = []
        for pattern in patterns:
            decisions.extend(re.findall(pattern, text, re.IGNORECASE))
        return [d.strip() for d in set(decisions) if d.strip()]

    @staticmethod
    def _extract_completed(text: str) -> List[str]:
        """Extract completed work from text."""
        patterns = [
            r'(?:completed|done|finished|implemented|deployed|merged)\s*[:=]?\s*["\']?([^.]+)',
        ]
        completed = []
        for pattern in patterns:
            completed.extend(re.findall(pattern, text, re.IGNORECASE))
        return [c.strip() for c in set(completed) if c.strip()]

    @staticmethod
    def _extract_open_items(text: str) -> List[str]:
        """Extract open/unresolved items from text."""
        patterns = [
            r'(?:open|pending|todo|follow\s*up|need\s*to|should\s*(?:add|fix|implement))\s*[:=]?\s*["\']?([^.]+)',
        ]
        items = []
        for pattern in patterns:
            items.extend(re.findall(pattern, text, re.IGNORECASE))
        return [i.strip() for i in set(items) if i.strip()]

    @staticmethod
    def _extract_deviations(text: str) -> List[str]:
        """Extract notable deviations from text."""
        patterns = [
            r'(?:deviation|diverged|changed\s*from|instead\s*of|original(?:ly)?\s*(?:planned|intended))\s*[:=]?\s*["\']?([^.]+)',
        ]
        deviations = []
        for pattern in patterns:
            deviations.extend(re.findall(pattern, text, re.IGNORECASE))
        return [d.strip() for d in set(deviations) if d.strip()]
```

### Step 2: Update Prompts with Superset Schema

Add to `super_council/arc_summarizer/prompts.py`:

```python
# ── Superset Summarization Schema ───────────────────────────────────────

SUMMARIZATION_SUPERSET_SCHEMA = """**Output Schema (include all sections that have content, skip empty ones):**
```yaml
topics:
  - <string — topic discussed>
decisions:
  - what: <string — the decision>
    context: <string — why>
work_completed:
  - <string — completed task>
open_items:
  - <string — unresolved item>
files_changed:
  - <string — file path>
functions_modified:
  - <string — function or class name>
tests_written:
  - <string — test name or description>
bugs_fixed:
  - <string — bug description>
sources_consulted:
  - <string — URL or source reference>
key_findings:
  - <string — finding or insight>
root_cause:
  - <string — root cause identified>
resolution:
  - <string — how it was resolved>
```

**Session Mode:** {session_mode}
**Emphasis:** {mode_emphasis}

**Source Material:**
<BEGIN MATERIAL>
{input_material}
<END MATERIAL>

Summarize now. Output ONLY the YAML block."""

MODE_EMPHASIS = {
    'code': 'Emphasize: files_changed, functions_modified, tests_written, bugs_fixed',
    'research': 'Emphasize: sources_consulted, key_findings, topics',
    'planning': 'Emphasize: decisions, open_items, topics',
    'debugging': 'Emphasize: root_cause, resolution, bugs_fixed, errors',
    'mixed': 'Balance all sections equally',
}


def build_summarization_prompt_with_mode(turns: list, session_mode: str = 'mixed') -> str:
    """Build mode-aware session summarization prompt.

    Args:
        turns: List of {"role": str, "content": str} conversation turns.
        session_mode: Detected session mode (code, research, planning, debugging, mixed).

    Returns:
        Complete prompt string ready for the model.
    """
    history = "\n".join(
        f"{t.get('role', '?').title()}: {t.get('content', '')}"
        for t in turns[-20:]
    )
    emphasis = MODE_EMPHASIS.get(session_mode, MODE_EMPHASIS['mixed'])
    return SUMMARIZATION_SUPERSET_SCHEMA.format(
        session_mode=session_mode,
        mode_emphasis=emphasis,
        input_material=history,
    )
```

### Step 3: Update ArcClient.summarize_session()

Add to `super_council/arc_summarizer/client.py`:

```python
def summarize_session(
    self,
    turns: List[dict],
    max_tokens: int = 256,
    session_mode: str = None,
) -> Optional[dict]:
    """Summarize a conversation session with mode awareness.

    Takes conversation turns, detects session mode (if not provided),
    and produces a structured summary with both human-readable text
    and trimmed signals.

    Args:
        turns: List of {"role": str, "content": str} conversation turns.
        max_tokens: Maximum output tokens.
        session_mode: Optional session mode override (code, research, planning, debugging, mixed).

    Returns:
        Dict with "summary" (text) and "trimmed" (structured signals), or None on failure.
    """
    # Detect session mode if not provided
    if session_mode is None:
        from .analyzer import SessionAnalyzer
        analyzer = SessionAnalyzer()
        text = "\n".join(t.get('content', '') for t in turns[-10:])
        session_mode, _ = analyzer.classify(text)

    # Build mode-aware prompt
    from .prompts import build_summarization_prompt_with_mode
    prompt = build_summarization_prompt_with_mode(turns, session_mode)

    raw = self._call_with_fallback(
        system=SYSTEM_EXTRACTION,  # Use extraction system for structured output
        user=prompt,
        max_tokens=max_tokens,
        temperature=0.3,
        retries=1,
        label="session-summarization",
    )
    if not raw:
        return None

    # Parse YAML response
    trimmed = self._parse_yaml(raw)
    if not trimmed:
        trimmed = {}

    # Generate human-readable summary from trimmed data
    from .prompts import render_consolidation_yaml
    summary_text = render_consolidation_yaml(trimmed)

    return {
        'summary': summary_text,
        'trimmed': trimmed,
        'session_mode': session_mode,
    }
```

### Step 4: Export from __init__.py

Add to `super_council/arc_summarizer/__init__.py`:

```python
from .analyzer import SessionAnalyzer
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `arc_summarizer/analyzer.py` | SessionAnalyzer: heuristic classifier + trimmed summary |
| Modify | `arc_summarizer/prompts.py` | Superset schema, mode-specific prompts |
| Modify | `arc_summarizer/client.py` | Mode-aware summarize_session() |
| Modify | `arc_summarizer/__init__.py` | Export SessionAnalyzer |

---

## Phase-Specific Tests

1. **Code session classified correctly:** Text with function definitions, file paths → mode = `code`
2. **Research session classified correctly:** Text with URLs, API references → mode = `research`
3. **Planning session classified correctly:** Text with decisions, trade-offs → mode = `planning`
4. **Debugging session classified correctly:** Text with errors, tracebacks → mode = `debugging`
5. **Mixed fallback on close scores:** Text with equal code + planning signals → mode = `mixed`
6. **Trimmed summary preserves signals:** Raw text with files, functions, decisions → all extracted
7. **Mode-aware prompt includes emphasis:** Code mode → emphasis on files_changed, functions_modified
8. **summarize_session returns structured dict:** Includes summary, trimmed, session_mode fields

---

## Completion Gate

- [ ] SessionAnalyzer class implemented with heuristic classification
- [ ] Score vector returns 5 modes with 0.0-1.0 scores
- [ ] Mixed fallback when scores within 0.1
- [ ] Trimmed summary generates fixed 11-field schema
- [ ] Superset schema added to prompts.py
- [ ] Mode-specific emphasis instructions included
- [ ] ArcClient.summarize_session() accepts session_mode, returns structured dict
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests

---

## Notes for Next Phase

Phase 2 (Adaptive Triggers) expects:
- SessionAnalyzer available for mode detection during idle/trigger events
- Trimmed summary schema for downstream reconciliation
- Mode-aware summarization working end-to-end
