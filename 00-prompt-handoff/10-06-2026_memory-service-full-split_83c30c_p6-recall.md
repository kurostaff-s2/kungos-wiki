# Phase 6: Split layer.py → recall/ + channels/ (Recall Layer)

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 6 of 9
**Dependencies:** Phases 1-5 (needs all stage modules)
**Estimated effort:** ~50 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `memory_service/layer.py` (1755 lines) → `memory_service/recall/layer.py` + 7 channel modules + `system_health.py`; `memory_service/router.py` (890 lines) → `memory_service/recall/router.py`
**Related codebases:** `memory_layer.py` shim in super_council/ root

## What This Phase Delivers

Splits `layer.py` (1755 lines) into the recall layer with pluggable channels. Each recall channel is a self-contained module that queries one data source. `MemoryLayer.unified_recall()` iterates channels, budgets tokens, and fuses results.

Moves `router.py` into `recall/router.py` (no split needed — it's already focused).

## Pre-Flight Checklist

- [ ] Phases 1-5 are marked complete
- [ ] `memory_service/store/`, `ingest/`, `consolidate/`, `index/`, `reconcile/` packages exist
- [ ] `python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print('OK')"` succeeds

## Implementation Steps

### Step 1: Move `router.py` → `recall/router.py`

Move verbatim. Update internal imports:

```python
# OLD (router.py):
from .store import RelationalStore

# NEW (recall/router.py):
from ..store import RelationalStore
```

### Step 2: Create `recall/channels/memsearch.py`

```python
# recall/channels/memsearch.py
"""Channel: Memsearch text recall.

Queries consolidated memory via memsearch (sqlite-vec or external).
"""

class MemsearchChannel:
    """Recall channel: text-based memsearch over consolidated memory."""

    def __init__(self, vector_store=None, store=None):
        self._vector_store = vector_store
        self._store = store

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query memsearch channel.

        Moved from MemoryLayer._channel_memsearch()
        """
        # ... verbatim ...
```

### Step 3: Create `recall/channels/diary.py`

```python
# recall/channels/diary.py
"""Channel: Session diary recall.

Queries session_diary table for recent diary entries matching the query.
"""

class DiaryChannel:
    """Recall channel: session diary."""

    def __init__(self, store):
        self._store = store

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query diary channel.

        Moved from MemoryLayer._channel_diary()
        """
        # ... verbatim ...
```

### Step 4: Create `recall/channels/execution.py`

```python
# recall/channels/execution.py
"""Channel: Execution history recall.

Queries event_log and workflow_run tables for execution history.
"""

class ExecutionChannel:
    """Recall channel: execution history."""

    def __init__(self, store, router):
        self._store = store
        self._router = router

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query execution channel.

        Moved from MemoryLayer._channel_execution()
        """
        # ... verbatim ...
```

### Step 5: Create `recall/channels/structural.py`

```python
# recall/channels/structural.py
"""Channel: Code graph structural recall.

Queries codegraph.db for structural code information.
"""

class StructuralChannel:
    """Recall channel: code graph structural data."""

    def __init__(self, cg_store):
        self._cg_store = cg_store

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query structural channel.

        Moved from MemoryLayer._channel_structural()
        """
        # ... verbatim ...
```

### Step 6: Create `recall/channels/work_items.py`

```python
# recall/channels/work_items.py
"""Channel: Work item recall.

Queries work_items table for active/completed work items.
"""

class WorkItemsChannel:
    """Recall channel: work items."""

    def __init__(self, store):
        self._store = store

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query work items channel.

        Moved from MemoryLayer._channel_work_items()
        """
        # ... verbatim ...
```

### Step 7: Create `recall/channels/deviations.py`

```python
# recall/channels/deviations.py
"""Channel: Deviation recall.

Queries deviations table for active/closed deviations.
"""

class DeviationsChannel:
    """Recall channel: deviations."""

    def __init__(self, store):
        self._store = store

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query deviations channel.

        Moved from MemoryLayer._channel_deviations()
        """
        # ... verbatim ...
```

### Step 8: Create `recall/channels/vectors.py`

```python
# recall/channels/vectors.py
"""Channel: Unified vector recall.

Queries sqlite-vec for semantic similarity search.
"""

class VectorsChannel:
    """Recall channel: unified vector search."""

    def __init__(self, vector_store):
        self._vector_store = vector_store

    def query(self, query: str, max_tokens: int = 1024, **kwargs) -> Optional[Dict]:
        """Query vectors channel.

        Moved from MemoryLayer._channel_unified_vectors()
        """
        # ... verbatim ...
```

### Step 9: Wire `recall/channels/__init__.py`

```python
# recall/channels/__init__.py
"""Recall channels — pluggable data sources for unified recall."""

from .memsearch import MemsearchChannel
from .diary import DiaryChannel
from .execution import ExecutionChannel
from .structural import StructuralChannel
from .work_items import WorkItemsChannel
from .deviations import DeviationsChannel
from .vectors import VectorsChannel

__all__ = [
    "MemsearchChannel",
    "DiaryChannel",
    "ExecutionChannel",
    "StructuralChannel",
    "WorkItemsChannel",
    "DeviationsChannel",
    "VectorsChannel",
]

# Channel registry: name → class
CHANNEL_REGISTRY = {
    "memsearch": MemsearchChannel,
    "diary": DiaryChannel,
    "execution": ExecutionChannel,
    "structural": StructuralChannel,
    "work_items": WorkItemsChannel,
    "deviations": DeviationsChannel,
    "vectors": VectorsChannel,
}
```

### Step 10: Rewrite `recall/layer.py`

The `MemoryLayer` becomes the channel orchestrator:

```python
# recall/layer.py
"""MemoryLayer — Three-channel unified recall with token budgeting.

Orchestrates pluggable recall channels, budgets tokens across channels,
and fuses results into a single response.
"""

import logging
from typing import Any, Dict, List, Optional

from ..store import RelationalStore
from .router import ContextRouter
from .channels import CHANNEL_REGISTRY

log = logging.getLogger(__name__)


# Scope channels — which channels to query for each scope
SCOPE_CHANNELS = {
    "decision": ["memsearch", "diary"],
    "repair": ["memsearch", "execution"],
    "recent": ["execution", "diary"],
    "run": ["memsearch", "execution", "diary"],
    "architecture": ["memsearch", "structural"],
    "all": list(CHANNEL_REGISTRY.keys()),
}


class MemoryLayer:
    """Three-channel unified recall: text + structural + execution.

    Composes pluggable recall channels, budgets tokens, fuses results.
    """

    def __init__(self, store: RelationalStore, context_router: ContextRouter = None,
                 cg_store=None, vector_store=None):
        self._store = store
        self._router = context_router
        self._cg_store = cg_store
        self._vector_store = vector_store

        # Initialize channels
        self._channels = {}
        self._init_channels()

    def _init_channels(self) -> None:
        """Initialize recall channels with dependencies."""
        self._channels["memsearch"] = CHANNEL_REGISTRY["memsearch"](
            vector_store=self._vector_store, store=self._store
        )
        self._channels["diary"] = CHANNEL_REGISTRY["diary"](store=self._store)
        self._channels["execution"] = CHANNEL_REGISTRY["execution"](
            store=self._store, router=self._router
        )
        self._channels["structural"] = CHANNEL_REGISTRY["structural"](cg_store=self._cg_store)
        self._channels["work_items"] = CHANNEL_REGISTRY["work_items"](store=self._store)
        self._channels["deviations"] = CHANNEL_REGISTRY["deviations"](store=self._store)
        self._channels["vectors"] = CHANNEL_REGISTRY["vectors"](vector_store=self._vector_store)

    def unified_recall(self, query: str, max_tokens: int = 4096,
                       scope: str = "all", **kwargs) -> Dict[str, Any]:
        """Three-channel unified recall with token budgeting.

        Moved from MemoryLayer.unified_recall() — refactored to use channels.
        """
        channel_names = SCOPE_CHANNELS.get(scope, SCOPE_CHANNELS["all"])
        tokens_per_channel = max_tokens // len(channel_names) if channel_names else 0

        results = {}
        for name in channel_names:
            channel = self._channels.get(name)
            if channel:
                try:
                    result = channel.query(query, max_tokens=tokens_per_channel, **kwargs)
                    if result:
                        results[name] = result
                except Exception as e:
                    log.warning("Channel %s query failed: %s", name, e)

        return {
            "query": query,
            "scope": scope,
            "channels": results,
            "total_channels": len(channel_names),
            "active_channels": len(results),
        }

    def get_context_slice(self, run_id: str, max_tokens: int = 4096) -> str:
        """Token-budgeted context slice for a run.

        Moved from MemoryLayer.get_context_slice()
        """
        # ... verbatim ...

    def ingest_artifact(self, ...):
        """Ingest an artifact into the memory layer.

        Moved from MemoryLayer.ingest_artifact()
        """
        # ... verbatim ...

    def evict_old_artifacts(self, retention_days: int = 90) -> int:
        """Evict artifacts older than retention period.

        Moved from MemoryLayer.evict_old_artifacts()
        """
        # ... verbatim ...
```

### Step 11: Create `recall/system_health.py`

Extract the `system_health()` method from `layer.py` — it's NOT a recall channel:

```python
# recall/system_health.py
"""System health — consolidation metrics, log channels, service status.

NOT a recall channel. Queries operational state across the memory service.
"""

import logging
from typing import Dict, Any, Optional

from ..index.doc_parsers import DailyLogParser, ChatSummaryQuery

log = logging.getLogger(__name__)


class SystemHealthQuery:
    """Query system health: consolidation metrics, logs, service state."""

    def __init__(self, store, vector_store=None):
        self._store = store
        self._vector_store = vector_store

    def check(self, query: str = "", max_tokens: int = 4096,
              days_back: int = 7, channels: str = None, severity: str = None) -> Dict[str, Any]:
        """Query system health.

        Moved from MemoryLayer.system_health()
        """
        # ... verbatim from layer.py system_health() ...
        # Includes: _get_consolidation_metrics, _query_log_channel,
        # _query_system_events, _query_session_diary_channel,
        # _query_consolidation_channel, _query_daily_logs,
        # _query_chat_summaries, _query_workflow_state,
        # _query_failures, _query_supervisor_log, _query_mcp_queue
```

### Step 12: Wire `recall/__init__.py`

```python
# recall/__init__.py
"""Recall Layer — reads from all pipeline stages.

Three-channel unified recall: text + structural + execution.
Pluggable channels with token budgeting.
"""
from .router import ContextRouter
from .layer import MemoryLayer, SCOPE_CHANNELS
from .system_health import SystemHealthQuery

__all__ = ["ContextRouter", "MemoryLayer", "SCOPE_CHANNELS", "SystemHealthQuery"]
```

### Step 13: Delete old files

```bash
rm memory_service/layer.py
rm memory_service/router.py
```

### Step 14: Update imports everywhere

Search for imports from `layer` and `router`:

```python
# OLD:
from .layer import MemoryLayer
from .router import ContextRouter

# NEW:
from .recall.layer import MemoryLayer
from .recall.router import ContextRouter
```

Update in: `memory_service/__init__.py`, shim files in super_council/ root.

### Step 15: Update shim files

```python
# memory_layer.py (super_council/ root):
from super_council.memory_service.recall.layer import MemoryLayer, SCOPE_CHANNELS  # noqa: F401

# context_router.py (super_council/ root):
from super_council.memory_service.recall.router import ContextRouter  # noqa: F401
```

### Step 16: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -c "from super_council.memory_service.recall import MemoryLayer, ContextRouter; print('OK')"
python -c "from super_council.memory_service.recall.channels import CHANNEL_REGISTRY; print(list(CHANNEL_REGISTRY.keys()))"
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.recall('test'))"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Move | `router.py` → `recall/router.py` | ContextRouter (recall queries) |
| Create | `recall/layer.py` | MemoryLayer (channel orchestrator, token budgeting) |
| Create | `recall/system_health.py` | SystemHealthQuery (consolidation metrics, logs) |
| Create | `recall/channels/memsearch.py` | MemsearchChannel |
| Create | `recall/channels/diary.py` | DiaryChannel |
| Create | `recall/channels/execution.py` | ExecutionChannel |
| Create | `recall/channels/structural.py` | StructuralChannel |
| Create | `recall/channels/work_items.py` | WorkItemsChannel |
| Create | `recall/channels/deviations.py` | DeviationsChannel |
| Create | `recall/channels/vectors.py` | VectorsChannel |
| Modify | `recall/__init__.py` | Re-export MemoryLayer, ContextRouter, SystemHealthQuery |
| Modify | `recall/channels/__init__.py` | CHANNEL_REGISTRY + all channel exports |
| Modify | `memory_service/__init__.py` | Update MemoryLayer, ContextRouter imports |
| Modify | `memory_layer.py` (super_council root) | Update import path |
| Modify | `context_router.py` (super_council root) | Update import path |
| Delete | `layer.py` | Replaced by recall/ package |
| Delete | `router.py` | Moved to recall/router.py |

## Phase-Specific Tests

1. **Import test:** `python -c "from super_council.memory_service.recall import MemoryLayer, ContextRouter; print('OK')"` — must succeed
2. **Channel test:** `python -c "from super_council.memory_service.recall.channels import CHANNEL_REGISTRY; assert len(CHANNEL_REGISTRY) == 7; print('OK')"` — must succeed
3. **Unified recall test:** `python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); r = ms.recall('test'); assert 'channels' in r; print('OK')"` — must succeed

## Completion Gate

- [ ] All 7 channel modules created
- [ ] `layer.py` split into `recall/layer.py` + channels/ + `system_health.py`
- [ ] `router.py` moved to `recall/router.py`
- [ ] `MemoryLayer` composes channels via CHANNEL_REGISTRY
- [ ] `SCOPE_CHANNELS` maps scopes to channel lists
- [ ] Shim files updated
- [ ] `python -m memory_service --health` reports healthy
- [ ] `ms.recall('test')` returns structured results

## Notes for Next Phase

- Phase 7 (cross-cutting) is independent of Phase 6
- The `SystemHealthQuery` replaces the `system_health()` method on `MemoryLayer`
- In Phase 8, `MemoryService.health_check()` will compose `SystemHealthQuery` results
