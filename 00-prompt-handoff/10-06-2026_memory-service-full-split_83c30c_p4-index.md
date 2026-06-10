# Phase 4: Create index/ Package from log_parsers.py (Stage 3)

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 4 of 9
**Dependencies:** Phase 1 (needs `store/` package)
**Estimated effort:** ~20 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `memory_service/log_parsers.py` (306 lines) → `memory_service/index/doc_parsers.py` + new `indexer.py` + `file_watcher.py`
**Related codebases:** None

## What This Phase Delivers

Creates the `index/` package (Stage 3: Consolidation → Memsearch Indexing). Moves `log_parsers.py` into `index/doc_parsers.py` and creates the indexing orchestration layer.

Stage 3 is the simplest stage — it watches `arc-memory/` for new consolidation files and indexes them.

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete
- [ ] `memory_service/store/` package exists
- [ ] `python -c "from super_council.memory_service.store import RelationalStore"` succeeds

## Implementation Steps

### Step 1: Move `log_parsers.py` → `index/doc_parsers.py`

Move verbatim. Update internal imports if any (there are none — it's self-contained).

```bash
mv memory_service/log_parsers.py memory_service/index/doc_parsers.py
```

### Step 2: Create `index/indexer.py`

The consolidation output indexer — watches for new files and triggers indexing:

```python
# index/indexer.py
"""Stage 3: Consolidation output → memsearch indexing."""

import logging
from pathlib import Path
from typing import List, Dict, Optional

from .doc_parsers import DailyLogParser, ChatSummaryQuery

log = logging.getLogger(__name__)


class ConsolidationIndexer:
    """Index consolidation outputs for memsearch recall.

    Watches arc-memory/ for new consolidation MD files.
    Triggers indexing via the configured memsearch backend.
    """

    def __init__(self, memory_base: str = "~/.council-memory"):
        self._memory_base = Path(memory_base).expanduser()
        self._arc_memory_dir = self._memory_base / "arc-memory" / "daily"
        self._parser = DailyLogParser()
        self._chat_summary = ChatSummaryQuery()

    def index_new_files(self) -> int:
        """Scan arc-memory/ for new files and index them.

        Returns count of newly indexed files.
        """
        # Implementation: scan directory, parse new files, trigger indexing
        pass

    def index_consolidation_file(self, path: Path) -> bool:
        """Index a single consolidation MD file.

        Args:
            path: Path to consolidation MD file in arc-memory/

        Returns:
            True if successfully indexed.
        """
        try:
            parsed = self._parser.parse_file(str(path))
            # Trigger memsearch indexing
            log.info("Indexed consolidation file: %s (%d entries)", path, len(parsed))
            return True
        except Exception as e:
            log.error("Failed to index %s: %s", path, e)
            return False

    def index_chat_summaries(self, days_back: int = 7) -> int:
        """Index recent chat summaries.

        Args:
            days_back: Number of days to look back

        Returns:
            Count of indexed summaries.
        """
        summaries = self._chat_summary.list_recent(days_back=days_back)
        # Trigger indexing for each summary
        log.info("Indexed %d chat summaries", len(summaries))
        return len(summaries)
```

### Step 3: Create `index/file_watcher.py`

```python
# index/file_watcher.py
"""Stage 3: File watcher for arc-memory/ directory."""

import logging
import time
import threading
from pathlib import Path
from typing import Optional, Callable

log = logging.getLogger(__name__)


class ConsolidationFileWatcher:
    """Watch arc-memory/ for new consolidation files.

    Triggers indexing callback when new files appear.
    """

    def __init__(self, watch_dir: Path, on_new_file: Callable[[Path], None], poll_interval: float = 5.0):
        self._watch_dir = watch_dir
        self._on_new_file = on_new_file
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_files: set = set()

    def start(self) -> None:
        """Start the watch loop."""
        self._running = True
        self._known_files = set(self._watch_dir.iterdir()) if self._watch_dir.exists() else set()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="consolidation-file-watcher")
        self._thread.start()

    def stop(self) -> None:
        """Stop the watch loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        """Main watch loop."""
        while self._running:
            try:
                self._scan()
            except Exception as e:
                log.error("File watcher error: %s", e)
            time.sleep(self._poll_interval)

    def _scan(self) -> None:
        """Scan for new files."""
        if not self._watch_dir.exists():
            return
        current = set(self._watch_dir.iterdir())
        new_files = current - self._known_files
        for f in new_files:
            if f.is_file() and f.suffix == ".md":
                self._on_new_file(f)
        self._known_files = current
```

### Step 4: Wire `index/__init__.py`

```python
# index/__init__.py
"""Stage 3: Consolidation outputs → memsearch indexing.

Watches arc-memory/ for new consolidation files and indexes them.
"""
from .indexer import ConsolidationIndexer
from .file_watcher import ConsolidationFileWatcher
from .doc_parsers import DailyLogParser, ChatSummaryQuery, SupervisorLogTailer, SystemdLogTailer

__all__ = [
    "ConsolidationIndexer",
    "ConsolidationFileWatcher",
    "DailyLogParser",
    "ChatSummaryQuery",
    "SupervisorLogTailer",
    "SystemdLogTailer",
]
```

### Step 5: Delete old `log_parsers.py`

```bash
rm memory_service/log_parsers.py
```

### Step 6: Update any imports

Search for `from .log_parsers import` or `from memory_service.log_parsers import` and update to `from .index.doc_parsers import` or `from memory_service.index.doc_parsers import`.

Check `layer.py` (system_health method uses DailyLogParser, ChatSummaryQuery):

```python
# In layer.py system_health():
# OLD:
from .log_parsers import DailyLogParser, ChatSummaryQuery

# NEW:
from .index.doc_parsers import DailyLogParser, ChatSummaryQuery
```

### Step 7: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -c "from super_council.memory_service.index import ConsolidationIndexer, DailyLogParser; print('OK')"
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.health_check())"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Move | `log_parsers.py` → `index/doc_parsers.py` | Document parsers (DailyLogParser, ChatSummaryQuery, tailers) |
| Create | `index/indexer.py` | Consolidation output indexer |
| Create | `index/file_watcher.py` | File watcher for arc-memory/ |
| Modify | `index/__init__.py` | Re-export all Stage 3 classes |
| Modify | `layer.py` | Update import from log_parsers → index.doc_parsers |
| Delete | `log_parsers.py` | Replaced by index/ package |

## Phase-Specific Tests

1. **Import test:** `python -c "from super_council.memory_service.index import ConsolidationIndexer, DailyLogParser; print('OK')"` — must succeed
2. **Parser test:** `python -c "from super_council.memory_service.index.doc_parsers import DailyLogParser; p = DailyLogParser(); print('OK')"` — must succeed

## Completion Gate

- [ ] `index/` package created with 3 modules
- [ ] `log_parsers.py` deleted
- [ ] All imports updated (especially in `layer.py`)
- [ ] `python -m memory_service --health` reports healthy
- [ ] No import errors

## Notes for Next Phase

- Phase 5 (reconcile/) is independent of Phase 4
- The `ConsolidationFileWatcher` is not wired into `MemoryService` yet — that happens in Phase 8
