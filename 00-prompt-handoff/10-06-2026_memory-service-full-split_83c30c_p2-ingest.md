# Phase 2: Split session_watcher.py → ingest/ (Stage 1)

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 2 of 9
**Dependencies:** Phase 1 (needs `store/session_store.py`)
**Estimated effort:** ~45 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `memory_service/session_watcher.py` (1116 lines) → 6 files under `memory_service/ingest/`
**Related codebases:** None

## What This Phase Delivers

Splits `session_watcher.py` (1116 lines) into 6 focused modules aligned to the Stage 1 pipeline: Raw JSONL → Canonical MD.

Each module owns one transformation step:

```
JSONL file → [parser] → turns → [classifier] → mode → [trimmer] → trimmed dict
    → [deviation_detector] → deviations → [diary_merger] → merged dict
    → [canonical_writer] → .md file in canonical-raw-session-data/
```

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete
- [ ] `memory_service/store/` package exists with `session_store.py`
- [ ] `python -c "from super_council.memory_service.store import RelationalStore"` succeeds

## Implementation Steps

### Step 1: Create `ingest/session_parser.py`

Extract JSONL parsing, text extraction, session classification:

```python
# ingest/session_parser.py
"""Stage 1: JSONL parsing and session classification."""

from pathlib import Path
from typing import List, Dict, Optional

class SessionParser:
    """Parse JSONL session files into structured turns."""

    @staticmethod
    def parse_jsonl(path: Path) -> List[Dict]:
        """Parse JSONL file into list of turn dicts.

        Moved from SessionWatcher._parse_jsonl()
        """
        # ... verbatim from session_watcher.py ...

    @staticmethod
    def extract_text(content) -> str:
        """Extract text content from tool result or message.

        Moved from SessionWatcher._extract_text()
        """
        # ... verbatim ...

    @staticmethod
    def classify(turns: List[Dict]) -> str:
        """Classify session mode from turns.

        Moved from SessionWatcher._classify()
        Returns one of: 'code', 'research', 'planning', 'debugging', 'mixed'
        """
        # ... verbatim ...
```

### Step 2: Create `ingest/session_trimmer.py`

```python
# ingest/session_trimmer.py
"""Stage 1: Mode-aware session trimming."""

class SessionTrimmer:
    """Trim sessions based on classified mode."""

    @staticmethod
    def trim(turns, session_mode: str, max_tokens: int = None) -> Dict:
        """Trim session turns to essential content.

        Moved from SessionWatcher._trim_session()
        Returns trimmed dict with summary, decisions, plan items.
        """
        # ... verbatim ...
```

### Step 3: Create `ingest/deviation_detector.py`

```python
# ingest/deviation_detector.py
"""Stage 1: Deviation detection and classification."""

class DeviationDetector:
    """Detect plan deviations from session content."""

    @staticmethod
    def detect(trimmed: Dict) -> List[Dict]:
        """Detect deviations from trimmed session.

        Moved from SessionWatcher._detect_deviations()
        """
        # ... verbatim ...

    @staticmethod
    def classify_deviation(decision: str, plan_items: List[Dict]) -> Optional[str]:
        """Classify deviation type.

        Moved from SessionWatcher._classify_deviation()
        """
        # ... verbatim ...

    @staticmethod
    def detect_deviation_type(decision: str, plan_text: str) -> str:
        """Detect specific deviation type.

        Moved from SessionWatcher._detect_deviation_type()
        """
        # ... verbatim ...
```

### Step 4: Create `ingest/diary_merger.py`

```python
# ingest/diary_merger.py
"""Stage 1: Diary merge and signal counting."""

class DiaryMerger:
    """Merge trimmed session with existing diary entries."""

    @staticmethod
    def merge(trimmed: Dict, jsonl_path: Path) -> Dict:
        """Merge trimmed session with diary.

        Moved from SessionWatcher._merge_with_diary()
        """
        # ... verbatim ...

    @staticmethod
    def parse_diary_field(text) -> List[str]:
        """Parse diary field into list items.

        Moved from SessionWatcher._parse_diary_field()
        """
        # ... verbatim ...

    @staticmethod
    def count_signals(trimmed: Dict) -> int:
        """Count signal items in trimmed session.

        Moved from SessionWatcher._count_signals()
        """
        # ... verbatim ...
```

### Step 5: Create `ingest/canonical_writer.py`

```python
# ingest/canonical_writer.py
"""Stage 1: Canonical MD file writing, project resolution, carry-forward."""

from pathlib import Path
from typing import Optional

class CanonicalWriter:
    """Write canonical MD files and wire project/carry-forward state."""

    def __init__(self, relational_store, pipeline=None, scheduler=None):
        self._store = relational_store
        self._pipeline = pipeline
        self._scheduler = scheduler

    def write_session_md(self, trimmed: Dict, jsonl_path: Path) -> Path:
        """Write session MD to canonical-raw-session-data/.

        Moved from SessionWatcher._write_session_md()
        """
        # ... verbatim ...

    def upsert_session_diary(self, trimmed: Dict, jsonl_path: Path) -> None:
        """Upsert session diary entry.

        Moved from SessionWatcher._upsert_session_diary()
        """
        # ... verbatim ...

    def resolve_project(self, trimmed: Dict, jsonl_path: Path) -> str:
        """Resolve project from session context.

        Moved from SessionWatcher._resolve_project()
        """
        # ... verbatim ...

    def wire_carry_forward(self, trimmed: Dict, jsonl_path: Path) -> None:
        """Wire carry-forward items from session.

        Moved from SessionWatcher._wire_carry_forward()
        """
        # ... verbatim ...

    def wake(self, event_name: str) -> None:
        """Wake consolidation scheduler.

        Moved from SessionWatcher._wake()
        """
        # ... verbatim ...
```

### Step 6: Rewrite `ingest/session_watcher.py`

The `SessionWatcher` class becomes the orchestrator — it composes the sub-modules and runs the watch loop:

```python
# ingest/session_watcher.py
"""Stage 1: Session file watcher and pipeline orchestrator.

Watches Pi session JSONL files, processes them through the Stage 1 pipeline,
and writes canonical MD files to canonical-raw-session-data/.
"""

from pathlib import Path
from typing import Optional
import logging
import threading
import time

from .session_parser import SessionParser
from .session_trimmer import SessionTrimmer
from .deviation_detector import DeviationDetector
from .diary_merger import DiaryMerger
from .canonical_writer import CanonicalWriter

log = logging.getLogger(__name__)

class SessionWatcher:
    """Watch JSONL files and process through Stage 1 pipeline."""

    def __init__(self, pipeline=None, scheduler=None, memory_service=None):
        self._pipeline = pipeline
        self._scheduler = scheduler
        self._memory_service = memory_service
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_count = 0

        # Compose sub-modules
        self._parser = SessionParser()
        self._trimmer = SessionTrimmer()
        self._deviation_detector = DeviationDetector()
        self._diary_merger = DiaryMerger()
        self._writer = CanonicalWriter(
            relational_store=memory_service.store if memory_service else None,
            pipeline=pipeline,
            scheduler=scheduler,
        )

    def start(self) -> None:
        """Start the watch loop thread."""
        # ... verbatim from original ...

    def stop(self) -> None:
        """Stop the watch loop."""
        # ... verbatim ...

    def _run_loop(self) -> None:
        """Main watch loop."""
        # ... verbatim ...

    def _scan_and_process(self) -> None:
        """Scan for new JSONL files and process them."""
        # ... verbatim ...

    def _wait_idle(self, path: Path, initial_mtime: float) -> bool:
        """Wait for file to become idle (no more writes)."""
        # ... verbatim ...

    def _is_in_progress(self, path: Path, current_mtime: float) -> bool:
        """Check if file is still being written."""
        # ... verbatim ...

    def _process_session(self, jsonl_path: Path) -> None:
        """Process one JSONL file through the full Stage 1 pipeline.

        Orchestrates: parse → classify → trim → detect deviations → merge diary → write MD
        """
        # Call sub-modules in pipeline order
        turns = self._parser.parse_jsonl(jsonl_path)
        session_mode = self._parser.classify(turns)
        trimmed = self._trimmer.trim(turns, session_mode)
        deviations = self._deviation_detector.detect(trimmed)
        merged = self._diary_merger.merge(trimmed, jsonl_path)
        signals = self._diary_merger.count_signals(merged)
        md_path = self._writer.write_session_md(merged, jsonl_path)
        self._writer.upsert_session_diary(merged, jsonl_path)
        project_id = self._writer.resolve_project(merged, jsonl_path)
        self._writer.wire_carry_forward(merged, jsonl_path)
        self._writer.wake("session_processed")
        self._processed_count += 1

    def _check_health(self) -> dict:
        """Check health of Stage 1 components."""
        # ... verbatim ...

    def stats(self) -> dict:
        """Return processing statistics."""
        # ... verbatim ...
```

### Step 7: Wire `ingest/__init__.py`

```python
# ingest/__init__.py
"""Stage 1: Raw JSONL → Canonical MD.

Pipeline: JSONL → parse → classify → trim → detect deviations → merge diary → write MD
"""
from .session_watcher import SessionWatcher
from .session_parser import SessionParser
from .session_trimmer import SessionTrimmer
from .deviation_detector import DeviationDetector
from .diary_merger import DiaryMerger
from .canonical_writer import CanonicalWriter

__all__ = [
    "SessionWatcher",
    "SessionParser",
    "SessionTrimmer",
    "DeviationDetector",
    "DiaryMerger",
    "CanonicalWriter",
]
```

### Step 8: Update `memory_service/__init__.py`

Update the SessionWatcher import:

```python
# OLD:
from .session_watcher import SessionWatcher

# NEW:
from .ingest.session_watcher import SessionWatcher
```

### Step 9: Delete old `session_watcher.py`

```bash
rm memory_service/session_watcher.py
```

### Step 10: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -c "from super_council.memory_service.ingest import SessionWatcher, SessionParser, SessionTrimmer; print('OK')"
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.health_check())"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `memory_service/ingest/session_parser.py` | JSONL parsing, text extraction, classification |
| Create | `memory_service/ingest/session_trimmer.py` | Mode-aware session trimming |
| Create | `memory_service/ingest/deviation_detector.py` | Deviation detection and classification |
| Create | `memory_service/ingest/diary_merger.py` | Diary merge, signal counting |
| Create | `memory_service/ingest/canonical_writer.py` | MD file writing, project resolution, carry-forward |
| Rewrite | `memory_service/ingest/session_watcher.py` | Orchestrator (composes sub-modules) |
| Modify | `memory_service/ingest/__init__.py` | Re-export all Stage 1 classes |
| Modify | `memory_service/__init__.py` | Update SessionWatcher import path |
| Delete | `memory_service/session_watcher.py` | Replaced by ingest/ package |

## Phase-Specific Tests

1. **Import test:** `python -c "from super_council.memory_service.ingest import SessionWatcher; print('OK')"` — must succeed
2. **Pipeline test:** Write a test JSONL file to a temp dir, point SessionWatcher at it, verify canonical MD is produced

## Completion Gate

- [ ] All 6 ingest/ modules created
- [ ] `session_watcher.py` deleted from memory_service/ root
- [ ] `SessionWatcher` importable from `memory_service.ingest`
- [ ] `SessionWatcher._process_session()` calls sub-modules in correct order
- [ ] `python -m memory_service --health` reports healthy
- [ ] No import errors in `MemoryService.load()`

## Notes for Next Phase

- Phase 3 (consolidate/) is independent of Phase 2
- The `CanonicalWriter` depends on `store/session_store.py` (Phase 1) for diary upsert and project resolution
