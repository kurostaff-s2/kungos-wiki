# Phase 7: Cross-Cutting Modules (enrich/, review/, health/, analytics/)

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 7 of 9
**Dependencies:** Phase 1 (needs `store/` package)
**Estimated effort:** ~20 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** 4 flat files → 4 packages under `memory_service/`
**Related codebases:** `micro_model.py` imported by `MemoryService._init_components()`; `review_service.py` shim in super_council/ root

## What This Phase Delivers

Moves 4 cross-cutting modules into their own packages. These are self-contained — no complex splits needed, just moves and import path updates.

| Current File | New Package | Lines | Action |
|-------------|-------------|-------|--------|
| `micro_model.py` | `enrich/enricher.py` | 805 | Move |
| `review.py` | `review/service.py` | 210 | Move |
| `health.py` | `health/checker.py` | 267 | Move |
| `analytics.py` | `analytics/logger.py` | 191 | Move |

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete
- [ ] `memory_service/store/` package exists
- [ ] `python -c "from super_council.memory_service import MemoryService"` succeeds

## Implementation Steps

### Step 1: Move `micro_model.py` → `enrich/enricher.py`

```bash
mv memory_service/../micro_model.py memory_service/enrich/enricher.py
```

Update imports inside the file (change absolute to relative where applicable):

```python
# If micro_model.py imports from memory_service:
# OLD:
from super_council.memory_service.store import RelationalStore

# NEW:
from ..store import RelationalStore
```

Wire `enrich/__init__.py`:

```python
# enrich/__init__.py
"""Enrichment — local model artifact enrichment, failure classification."""
from .enricher import MicroModelEnricher

__all__ = ["MicroModelEnricher"]
```

### Step 2: Move `review.py` → `review/service.py`

```bash
mv memory_service/review.py memory_service/review/service.py
```

Update imports:

```python
# OLD:
from .store import RelationalStore

# NEW:
from ..store import RelationalStore
```

Wire `review/__init__.py`:

```python
# review/__init__.py
"""Review — review lifecycle (start, log, verdict)."""
from .service import ReviewService

__all__ = ["ReviewService"]
```

Update shim:

```python
# review_service.py (super_council/ root):
from super_council.memory_service.review.service import ReviewService  # noqa: F401
```

### Step 3: Move `health.py` → `health/checker.py`

```bash
mv memory_service/health.py memory_service/health/checker.py
```

Update imports:

```python
# OLD:
from .store import RelationalStore

# NEW:
from ..store import RelationalStore
```

Wire `health/__init__.py`:

```python
# health/__init__.py
"""Health — service health checking."""
from .checker import ServiceHealthChecker

__all__ = ["ServiceHealthChecker"]
```

### Step 4: Move `analytics.py` → `analytics/logger.py`

```bash
mv memory_service/analytics.py memory_service/analytics/logger.py
```

No import updates needed (analytics.py has no internal memory_service imports).

Wire `analytics/__init__.py`:

```python
# analytics/__init__.py
"""Analytics — embedding and search request logging."""
from .logger import (
    get_analytics_dir,
    set_analytics_dir,
    log_embedding_request,
    log_search_request,
    get_analytics_summary,
)

__all__ = [
    "get_analytics_dir",
    "set_analytics_dir",
    "log_embedding_request",
    "log_search_request",
    "get_analytics_summary",
]
```

### Step 5: Update `memory_service/__init__.py` imports

```python
# OLD:
from super_council.micro_model import MicroModelEnricher
from .review import ReviewService
from .health import ServiceHealthChecker

# NEW:
from .enrich.enricher import MicroModelEnricher
from .review.service import ReviewService
from .health.checker import ServiceHealthChecker
```

### Step 6: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -c "from super_council.memory_service.enrich import MicroModelEnricher; print('OK')"
python -c "from super_council.memory_service.review import ReviewService; print('OK')"
python -c "from super_council.memory_service.health import ServiceHealthChecker; print('OK')"
python -c "from super_council.memory_service.analytics import get_analytics_summary; print('OK')"
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.health_check())"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Move | `micro_model.py` → `enrich/enricher.py` | MicroModelEnricher |
| Move | `review.py` → `review/service.py` | ReviewService |
| Move | `health.py` → `health/checker.py` | ServiceHealthChecker |
| Move | `analytics.py` → `analytics/logger.py` | Analytics logging |
| Modify | `enrich/__init__.py` | Re-export MicroModelEnricher |
| Modify | `review/__init__.py` | Re-export ReviewService |
| Modify | `health/__init__.py` | Re-export ServiceHealthChecker |
| Modify | `analytics/__init__.py` | Re-export analytics functions |
| Modify | `memory_service/__init__.py` | Update import paths |
| Modify | `review_service.py` (super_council root) | Update import path |
| Delete | `micro_model.py` (super_council root) | Moved to enrich/ |
| Delete | `review.py` | Moved to review/ |
| Delete | `health.py` | Moved to health/ |
| Delete | `analytics.py` | Moved to analytics/ |

## Phase-Specific Tests

1. **Import test:** All four packages importable from `memory_service.<package>`
2. **Composition test:** `MemoryService.load()` initializes enricher, review, health components

## Completion Gate

- [ ] All 4 packages created with `__init__.py` re-exports
- [ ] Old flat files deleted
- [ ] Shim files updated
- [ ] `python -m memory_service --health` reports healthy
- [ ] No import errors

## Notes for Next Phase

- Phase 8 (composition root) wires all packages together
- The `MemoryService._init_components()` method needs to update all import paths
