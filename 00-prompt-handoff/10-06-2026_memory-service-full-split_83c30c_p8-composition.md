# Phase 8: Composition Root + Transport Wiring

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 8 of 9
**Dependencies:** Phases 1-7 (all packages must exist)
**Estimated effort:** ~30 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `memory_service/__init__.py` (rewrite), `memory_service/mcp_server.py` (update imports), `memory_service/http_endpoints.py` (update imports)
**Related codebases:** `super_council.py`, `voice_pipeline/`, `mcp_server.py` in super_council/ root

## What This Phase Delivers

Rewires the `MemoryService` facade to compose all new packages. Updates MCP and HTTP transport layers to use new import paths. This is the integration phase — no new code, just wiring.

## Pre-Flight Checklist

- [ ] Phases 1-7 are marked complete
- [ ] All packages exist: `store/`, `ingest/`, `consolidate/`, `index/`, `reconcile/`, `recall/`, `enrich/`, `review/`, `health/`, `analytics/`
- [ ] `python -c "from super_council.memory_service.store import RelationalStore; print('OK')"` succeeds for each package

## Implementation Steps

### Step 1: Rewrite `memory_service/__init__.py`

The `MemoryService` facade must compose all new packages:

```python
# memory_service/__init__.py
"""Memory Service — Single source of truth for memory operations.

Pipeline-aligned architecture:
  Stage 1 (ingest/):     Raw JSONL → Canonical MD
  Stage 2 (consolidate/): Canonical MD → ARC LLM → Consolidation
  Stage 3 (index/):      Consolidation → Memsearch Indexing
  Stage 4 (reconcile/):  Consolidation → Reconciliation Outputs
  Stage 5 (store/):      Reconciliation → VectorStore → DB

  Recall Layer (recall/):  Three-channel unified recall
  Enrichment (enrich/):    Local model artifact enrichment
  Transport (mcp_server/, http_endpoints/): MCP + HTTP servers
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.expanduser("~/.council-memory/council_core.db")
_CODEGRAPH_DB_PATH = os.path.expanduser("~/.council-memory/codegraph.db")


class MemoryService:
    """Unified interface for all memory operations.

    Composition root: wires all pipeline stages, recall layer,
    and cross-cutting concerns into a single facade.
    """

    def __init__(
        self,
        db_path: str = None,
        cg_db_path: str = None,
        config_path: Optional[Path] = None,
    ):
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._cg_db_path = cg_db_path or _CODEGRAPH_DB_PATH
        self._config_path = config_path
        self._config = None

        # Stage 5: Store
        self._store = None

        # Recall Layer
        self._router = None
        self._layer = None

        # Cross-cutting
        self._review = None
        self._vector_store = None
        self._cg_store = None

        # Stage 2: Consolidation
        self._pipeline = None
        self._scheduler = None

        # Enrichment
        self._enricher = None

        # Stage 1: Ingestion
        self._session_watcher = None

        # Reconciliation thread
        self._reconciliation_thread: Optional[threading.Thread] = None
        self._reconciliation_running = False

        self._init_components()

    def _init_components(self) -> None:
        """Initialize all components from new package structure."""

        # 1. Stage 5: RelationalStore
        try:
            from .store import RelationalStore
            self._store = RelationalStore(self._db_path, cg_db_path=self._cg_db_path)
        except Exception as e:
            log.error("RelationalStore init failed: %s", e)
            raise

        # 2. Recall Layer: ContextRouter
        try:
            from .recall.router import ContextRouter
            self._router = ContextRouter(self._store)
        except Exception as e:
            log.warning("ContextRouter init failed: %s", e)

        # 3. Recall Layer: MemoryLayer
        try:
            from .recall.layer import MemoryLayer
            self._layer = MemoryLayer(self._store, context_router=self._router)
        except Exception as e:
            log.warning("MemoryLayer init failed: %s", e)

        # Back-reference
        if self._store and self._layer:
            self._store.memory_layer = self._layer

        # 4. Review
        try:
            from .review.service import ReviewService
            self._review = ReviewService(self._store)
        except Exception as e:
            log.warning("ReviewService init failed: %s", e)

        # 5. Vector Store
        try:
            from .store.vector_store import SQLiteVectorStore, _DB_INDEX_TABLES
            from .config import MemoryConfig
            config = MemoryConfig.load(config_path=self._config_path)
            self._vector_store = SQLiteVectorStore(
                db=self._store.db,
                embedding_url=config.memsearch.embedding_url,
            )
            if self._vector_store._available:
                log.info("SQLiteVectorStore initialized (available=True)")
                # Wire to MemoryLayer
                if self._layer:
                    self._layer._vector_store = self._vector_store
                # Index arc-reconcile + DB tables (verbatim from original)
                # ... [keep original indexing logic] ...
            else:
                log.warning("SQLiteVectorStore unavailable (non-fatal)")
        except Exception as e:
            log.warning("SQLiteVectorStore init failed (non-fatal): %s", e)

        # 6. CodeGraphStore
        try:
            from super_council.code_graph.store import CodeGraphStore
            self._cg_store = CodeGraphStore(self._cg_db_path)
            if self._cg_store and self._layer:
                self._layer._cg_store = self._cg_store
        except Exception as e:
            log.warning("CodeGraphStore init failed: %s", e)

        # 7. Stage 2: ArcPipeline
        try:
            from .consolidate.pipeline import ArcPipeline
            from .consolidate.config import ArcConfig
            arc_config = ArcConfig.load(config_path=self._config_path)
            self._pipeline = ArcPipeline(arc_config, self._store)
            if self._router:
                self._router._consolidation_pipeline = self._pipeline
        except Exception as e:
            log.warning("ArcPipeline init failed: %s", e)

        # 8. Stage 2: IdleWindowScheduler
        try:
            if self._pipeline is not None:
                from .consolidate.scheduler import IdleWindowScheduler
                self._scheduler = IdleWindowScheduler(self._pipeline)
                self._scheduler.start()
                # Startup catch-up (verbatim)
                import threading
                threading.Thread(
                    target=self._scheduler._run_startup_catch_up,
                    name="consolidation-catchup",
                    daemon=True,
                ).start()
        except Exception as e:
            log.warning("IdleWindowScheduler init failed: %s", e)

        # 9. Reconciliation thread
        try:
            if self._pipeline is not None and self._store is not None:
                self._start_reconciliation_thread()
        except Exception as e:
            log.warning("Reconciliation thread init failed: %s", e)

        # 10. Enrichment: MicroModelEnricher
        try:
            from .enrich.enricher import MicroModelEnricher
            self._enricher = MicroModelEnricher(
                self._store,
                model_alias=os.path.expanduser("~/models/embedding/pplx-embed-v1-0.6b-int8"),
            )
        except Exception as e:
            log.warning("MicroModelEnricher init failed: %s", e)

        # 11. Stage 1: SessionWatcher
        try:
            from .ingest.session_watcher import SessionWatcher
            self._session_watcher = SessionWatcher(
                pipeline=self._pipeline,
                scheduler=self._scheduler,
                memory_service=self,
            )
            self._session_watcher.start()
        except Exception as e:
            log.warning("SessionWatcher init failed: %s", e)

    # ... [keep all property methods, convenience methods, health_check verbatim] ...
    # Update only the import paths inside methods if they reference old modules

    @classmethod
    def load(cls, db_path=None, config_path=None) -> "MemoryService":
        if db_path is None:
            db_path = _DEFAULT_DB_PATH
        return cls(db_path=db_path, config_path=config_path)

    # Properties (keep verbatim, update docstrings if needed)
    @property
    def store(self):
        return self._store

    @property
    def router(self):
        return self._router

    @property
    def layer(self):
        return self._layer

    @property
    def review(self):
        return self._review

    @property
    def cg_store(self):
        return self._cg_store

    @property
    def pipeline(self):
        return self._pipeline

    @property
    def scheduler(self):
        return self._scheduler

    @property
    def enricher(self):
        return self._enricher

    @property
    def session_watcher(self):
        return self._session_watcher

    @property
    def vector_store(self):
        return self._vector_store

    @property
    def config(self):
        if self._config is None:
            try:
                from .config import MemoryConfig
                self._config = MemoryConfig.load(config_path=self._config_path)
            except Exception:
                from .config import MemoryConfig
                self._config = MemoryConfig()
        return self._config

    # Convenience methods (keep verbatim)
    def recall(self, query, max_tokens=2048, project_id=None, type_filter=None, phase=None):
        if not self._layer:
            return {"error": "MemoryLayer not available", "channels": {}}
        return self._layer.unified_recall(
            query=query, max_tokens=max_tokens,
            project_id=project_id, type_filter=type_filter, phase=phase,
        )

    def context_slice(self, run_id, max_tokens=1024):
        if not self._layer:
            return {"error": "MemoryLayer not available"}
        return self._layer.get_context_slice(run_id=run_id, max_tokens=max_tokens)

    def run_snapshot(self, run_id):
        if not self._router:
            return {"error": "ContextRouter not available"}
        return self._router.get_run_snapshot(run_id=run_id)

    def summarize_issues(self, run_id):
        if not self._router:
            return {"error": "ContextRouter not available"}
        return self._router.summarize_run_issues(run_id=run_id)

    def review_findings(self, project_id=None, limit=10):
        if not self._router:
            return []
        return self._router.get_review_findings(project_id=project_id, limit=limit)

    def recent_events(self, run_id=None, limit=10):
        if not self._router:
            return []
        return self._router.get_recent_events(run_id=run_id, limit=limit)

    def upsert_session_diary(self, summary_text, source_path, alias="unknown"):
        if not self._store:
            return ""
        diary_id = self._store.upsert_session_diary(
            summary_text=summary_text, source_path=source_path, alias=alias,
        )
        self._wake_scheduler("daily_summary_saved")
        return diary_id

    def _wake_scheduler(self, event_name):
        try:
            if self._scheduler is not None and hasattr(self._scheduler, "_handle_event_hint"):
                self._scheduler._handle_event_hint(event_name)
        except Exception:
            pass

    def _start_reconciliation_thread(self):
        # ... verbatim from original ...
        pass

    def health_check(self):
        # ... verbatim from original, update component names ...
        pass


__all__ = ["MemoryService"]
```

### Step 2: Update `mcp_server.py` imports

```python
# OLD imports in mcp_server.py:
from .store import RelationalStore
from .router import ContextRouter
from .layer import MemoryLayer
from .review import ReviewService

# NEW imports:
from .store import RelationalStore
from .recall.router import ContextRouter
from .recall.layer import MemoryLayer
from .review.service import ReviewService
```

### Step 3: Update `http_endpoints.py` imports

Same pattern — update any internal imports to new paths.

### Step 4: Update `__main__.py` imports

```python
# OLD:
from .mcp_server import MemoryMCPHandler
from .http_endpoints import create_app

# These should still work (no path change for mcp_server.py and http_endpoints.py)
```

### Step 5: Wire ArcPipeline → Reconciler delegation

Update `consolidate/pipeline.py` to delegate reconciliation to the `reconcile/` package:

```python
# In consolidate/pipeline.py:
def reconcile_tasks(self, consolidation_text: str, tier_id: str, ...) -> Optional[list]:
    """Reconcile tasks from consolidation output."""
    try:
        from ..reconcile.reconciler import Reconciler
        reconciler = Reconciler(relational_store=self._store)
        # Delegate to reconciler
        return reconciler.reconcile_tier(tier_id)
    except Exception as e:
        log.warning("Task reconciliation failed: %s", e)
        return None
```

### Step 6: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council

# Test MemoryService composition
python -c "
from super_council.memory_service import MemoryService
ms = MemoryService.load()
h = ms.health_check()
print('Healthy:', h['healthy'])
print('Components:', h['components'])
"

# Test MCP tools
python -c "
from super_council.memory_service import MemoryService
ms = MemoryService.load()
r = ms.recall('test query')
print('Recall channels:', list(r.get('channels', {}).keys()))
"

# Test shim files
python -c "from super_council.relational_store import RelationalStore; print('OK')"
python -c "from super_council.memory_layer import MemoryLayer; print('OK')"
python -c "from super_council.context_router import ContextRouter; print('OK')"
python -c "from super_council.review_service import ReviewService; print('OK')"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Rewrite | `memory_service/__init__.py` | MemoryService facade with new import paths |
| Modify | `memory_service/mcp_server.py` | Update imports |
| Modify | `memory_service/http_endpoints.py` | Update imports |
| Modify | `consolidate/pipeline.py` | Delegate reconciliation to reconcile/ package |
| Modify | `arc_summarizer/__init__.py` | Ensure shim is complete |

## Phase-Specific Tests

1. **Composition test:** `MemoryService.load()` initializes all components without errors
2. **Health check:** `ms.health_check()` reports all components present
3. **Recall test:** `ms.recall('test')` returns structured results with channel data
4. **Shim test:** All shim files import successfully

## Completion Gate

- [ ] `MemoryService.load()` initializes all components from new packages
- [ ] All component properties return non-None values
- [ ] `ms.recall('test')` returns results
- [ ] `ms.health_check()` reports healthy
- [ ] MCP server starts (`python -m memory_service --mcp-stdio` doesn't crash)
- [ ] All shim files work
- [ ] No import errors anywhere

## Notes for Next Phase

- Phase 9 (E2E) runs the full pipeline with real data
- If any component fails to initialize, diagnose before proceeding to Phase 9
