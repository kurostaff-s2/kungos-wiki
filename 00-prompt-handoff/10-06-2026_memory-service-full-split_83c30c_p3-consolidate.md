# Phase 3: Move arc_summarizer/ → consolidate/ + Split pipeline.py (Stage 2)

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 3 of 9
**Dependencies:** Phase 1 (needs `store/consolidation_store.py`)
**Estimated effort:** ~45 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `arc_summarizer/` (8 files) → `memory_service/consolidate/` + split `pipeline.py` (696 lines) into 4 modules
**Related codebases:** `arc_summarizer/` is imported by `test_e2e_chain.py`, `super_council.py`

## What This Phase Delivers

Moves `arc_summarizer/` into `memory_service/consolidate/` and splits `pipeline.py` into focused modules. Creates a shim `arc_summarizer/__init__.py` for backward compatibility.

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete
- [ ] `memory_service/store/consolidation_store.py` exists
- [ ] `python -c "from super_council.arc_summarizer import ArcPipeline"` succeeds

## Implementation Steps

### Step 1: Move arc_summarizer/ files into consolidate/

Move these files verbatim (no changes):

| Source | Destination |
|--------|-------------|
| `arc_summarizer/client.py` | `memory_service/consolidate/client.py` |
| `arc_summarizer/config.py` | `memory_service/consolidate/config.py` |
| `arc_summarizer/analyzer.py` | `memory_service/consolidate/analyzer.py` |
| `arc_summarizer/prompts.py` | `memory_service/consolidate/prompts.py` |
| `arc_summarizer/scheduler.py` | `memory_service/consolidate/scheduler.py` |

### Step 2: Split `pipeline.py` → 4 modules

#### `consolidate/pipeline.py` — Core ArcPipeline class

Keep the `ArcPipeline` class but extract large methods into sub-modules:

```python
# consolidate/pipeline.py
"""Stage 2: ArcPipeline — tiered consolidation orchestration."""

from .tier_gatherer import TierGatherer
from .tier_writer import TierWriter
from .knowledge_card import KnowledgeCardInjector

class ArcPipeline:
    """Tiered consolidation pipeline on Arc A380."""

    def __init__(self, arc_config, relational_store):
        self._config = arc_config
        self._store = relational_store
        self._gatherer = TierGatherer(self._config, self._store)
        self._writer = TierWriter(self._config, self._store)
        self._injector = KnowledgeCardInjector(self._config, self._store)
        # ... client setup ...

    def run_tiered_consolidation(self, tier_id: str) -> bool:
        """Run full tiered consolidation: gather → LLM → write → reconcile."""
        # ... orchestration logic ...
        input_text = self._gatherer.gather(tier_id)
        # ... LLM call ...
        self._writer.write(tier_id, output)
        # ... reconciliation calls ...

    def tier1_knowledge_card(self) -> Optional[str]:
        return self._injector.inject()

    def health_check(self) -> dict:
        # ... verbatim ...
```

#### `consolidate/tier_gatherer.py` — Input gathering

```python
# consolidate/tier_gatherer.py
"""Stage 2: Tier input gathering."""

class TierGatherer:
    """Gather input material for each consolidation tier."""

    def __init__(self, arc_config, relational_store):
        self._config = arc_config
        self._store = relational_store

    def gather(self, tier_id: str) -> Optional[str]:
        """Gather input for a specific tier.

        Dispatches to tier-specific gatherers.
        """
        if tier_id == "daily":
            return self._gather_daily()
        # ... other tiers ...

    def _gather_raw_session_mds(self) -> Optional[str]:
        """Gather raw session MDs from canonical-raw-session-data/.

        Moved from ArcPipeline._gather_raw_session_mds()
        """
        # ... verbatim ...

    def _gather_consolidated_mds(self) -> Optional[str]:
        """Gather consolidated MDs from arc-memory/.

        Moved from ArcPipeline._gather_consolidated_mds()
        """
        # ... verbatim ...

    def _gather_plan_text(self, tier_id: str) -> Optional[str]:
        """Gather plan text for reconciliation.

        Moved from ArcPipeline._gather_plan_text()
        """
        # ... verbatim ...
```

#### `consolidate/tier_writer.py` — Output writing

```python
# consolidate/tier_writer.py
"""Stage 2: Tier output writing, DB upsert, MD formatting."""

class TierWriter:
    """Write consolidation outputs to arc-memory/ and DB."""

    def __init__(self, arc_config, relational_store):
        self._config = arc_config
        self._store = relational_store

    def write(self, tier_id: str, output: dict) -> Optional[str]:
        """Write tier output: MD file + DB upsert.

        Returns path to written MD file.
        """
        md_path = self._write_tier_output(tier_id, output)
        self._upsert_rollup_to_db(output, tier_id)
        return md_path

    def _write_tier_output(self, tier_id: str, output: dict) -> Optional[str]:
        """Write tier output MD file.

        Moved from ArcPipeline._write_tier_output()
        """
        # ... verbatim ...

    def _upsert_rollup_to_db(self, output: dict, tier_id: str) -> None:
        """Upsert consolidation rollup to DB.

        Moved from ArcPipeline._upsert_rollup_to_db()
        """
        # ... verbatim ...

    def _format_consolidation_md(self, output: dict) -> str:
        """Format consolidation output as MD.

        Moved from ArcPipeline._format_consolidation_md()
        """
        # ... verbatim ...

    def _format_file_card(self, path: str, content: str) -> Optional[str]:
        """Format file card for MD output.

        Moved from ArcPipeline._format_file_card()
        """
        # ... verbatim ...
```

#### `consolidate/knowledge_card.py` — Tier-1 injection

```python
# consolidate/knowledge_card.py
"""Stage 2: Tier-1 knowledge card injection."""

class KnowledgeCardInjector:
    """Inject Tier-1 knowledge cards into consolidation pipeline."""

    def __init__(self, arc_config, relational_store):
        self._config = arc_config
        self._store = relational_store

    def inject(self) -> Optional[str]:
        """Inject Tier-1 knowledge card.

        Moved from ArcPipeline.inject_tier1()
        """
        # ... verbatim ...
```

### Step 3: Move reconciliation methods from pipeline.py

The `reconcile_tasks()` and `reconcile_deviations()` methods in `ArcPipeline` should call the `reconcile/` package (Phase 5). For now, keep them in `pipeline.py` as thin wrappers that will be updated in Phase 8:

```python
# In consolidate/pipeline.py
def reconcile_tasks(self, consolidation_text: str, tier_id: str, ...) -> Optional[list]:
    """Reconcile tasks from consolidation output.

    TODO(Phase 8): Delegate to reconcile.reconciler.Reconciler
    """
    # ... keep verbatim for now ...

def reconcile_deviations(self, consolidation_text: str, tier_id: str, ...) -> Optional[list]:
    """Reconcile deviations from consolidation output.

    TODO(Phase 8): Delegate to reconcile.reconciler.Reconciler
    """
    # ... keep verbatim for now ...
```

### Step 4: Wire `consolidate/__init__.py`

```python
# consolidate/__init__.py
"""Stage 2: Canonical MD → ARC LLM → Consolidation Outputs.

Pipeline: gather inputs → LLM consolidation → write outputs → reconcile
"""
from .pipeline import ArcPipeline
from .scheduler import IdleWindowScheduler
from .tier_gatherer import TierGatherer
from .tier_writer import TierWriter
from .knowledge_card import KnowledgeCardInjector
from .client import ArcClient
from .config import ArcConfig
from .analyzer import SessionAnalyzer

__all__ = [
    "ArcPipeline",
    "IdleWindowScheduler",
    "TierGatherer",
    "TierWriter",
    "KnowledgeCardInjector",
    "ArcClient",
    "ArcConfig",
    "SessionAnalyzer",
]
```

### Step 5: Create `arc_summarizer/` shim package

Replace `arc_summarizer/__init__.py` with re-exports to maintain backward compatibility:

```python
# arc_summarizer/__init__.py (SHIM — do not delete)
"""Arc Summarizer shim — re-exports from memory_service.consolidate.

Maintains backward compatibility for external callers.
"""
from super_council.memory_service.consolidate.config import ArcConfig
from super_council.memory_service.consolidate.client import ArcClient
from super_council.memory_service.consolidate.pipeline import ArcPipeline
from super_council.memory_service.consolidate.analyzer import SessionAnalyzer

# Backward-compatible ArcSummarizer class
class ArcSummarizer:
    """Unified interface — delegates to consolidate/ package."""
    def __init__(self, config, relational_store=None):
        self._config = config
        self._client = ArcClient(config)
        self._pipeline = ArcPipeline(config, relational_store)

    @property
    def pipeline(self):
        return self._pipeline

    @property
    def client(self):
        return self._client

    @classmethod
    def load(cls, fallback_url=None):
        config = ArcConfig.load()
        if fallback_url:
            config.server_url = fallback_url
        return cls(config)

    def consolidate(self):
        return self._pipeline.run_tiered_consolidation("daily")

    def summarize_session(self, turns, session_mode=None):
        return self._client.summarize_session(turns, session_mode=session_mode)

    def extract_knowledge(self, text, schema):
        return self._client.extract_knowledge(text, schema)

    def inject_tier1(self):
        return self._pipeline.tier1_knowledge_card()

__all__ = ["ArcConfig", "ArcClient", "ArcPipeline", "ArcSummarizer", "SessionAnalyzer"]
```

Delete the old `arc_summarizer/` module files (keep only `__init__.py` shim):

```bash
# Keep only the shim
rm arc_summarizer/pipeline.py arc_summarizer/scheduler.py arc_summarizer/client.py \
   arc_summarizer/config.py arc_summarizer/analyzer.py arc_summarizer/prompts.py \
   arc_summarizer/reconcile.py arc_summarizer/__pycache__/*.pyc
```

### Step 6: Update `scheduler.py` imports

`IdleWindowScheduler` imports from `memory_service.config`. Update to relative import:

```python
# OLD:
from ..memory_service.config import IST

# NEW:
from ..config import IST
```

### Step 7: Update `memory_service/__init__.py` imports

```python
# OLD:
from super_council.arc_summarizer.pipeline import ArcPipeline
from super_council.arc_summarizer.config import ArcConfig
from super_council.arc_summarizer.scheduler import IdleWindowScheduler

# NEW:
from .consolidate.pipeline import ArcPipeline
from .consolidate.config import ArcConfig
from .consolidate.scheduler import IdleWindowScheduler
```

### Step 8: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council

# Test new imports
python -c "from super_council.memory_service.consolidate import ArcPipeline, ArcConfig, SessionAnalyzer; print('OK')"

# Test shim
python -c "from super_council.arc_summarizer import ArcSummarizer, ArcPipeline, ArcConfig; print('OK')"

# Test MemoryService
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.health_check())"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Move | `arc_summarizer/client.py` → `consolidate/client.py` | LLM HTTP client |
| Move | `arc_summarizer/config.py` → `consolidate/config.py` | ArcConfig |
| Move | `arc_summarizer/analyzer.py` → `consolidate/analyzer.py` | SessionAnalyzer |
| Move | `arc_summarizer/prompts.py` → `consolidate/prompts.py` | Tier prompt templates |
| Move | `arc_summarizer/scheduler.py` → `consolidate/scheduler.py` | IdleWindowScheduler |
| Split | `arc_summarizer/pipeline.py` → `consolidate/pipeline.py` + `tier_gatherer.py` + `tier_writer.py` + `knowledge_card.py` | Pipeline split |
| Modify | `arc_summarizer/__init__.py` | Shim with re-exports |
| Modify | `memory_service/consolidate/__init__.py` | Re-export all Stage 2 classes |
| Modify | `memory_service/__init__.py` | Update ArcPipeline/ArcConfig/IdleWindowScheduler imports |
| Delete | `arc_summarizer/pipeline.py`, `scheduler.py`, `client.py`, `config.py`, `analyzer.py`, `prompts.py`, `reconcile.py` | Replaced by consolidate/ |

## Phase-Specific Tests

1. **Import test:** `python -c "from super_council.memory_service.consolidate import ArcPipeline; print('OK')"` — must succeed
2. **Shim test:** `python -c "from super_council.arc_summarizer import ArcSummarizer; s = ArcSummarizer.load(); print('OK')"` — must succeed
3. **Composition test:** Verify `ArcPipeline` composes `TierGatherer`, `TierWriter`, `KnowledgeCardInjector`

## Completion Gate

- [ ] All arc_summarizer/ files moved to consolidate/
- [ ] pipeline.py split into 4 modules
- [ ] arc_summarizer/ shim works (backward compatible)
- [ ] `MemoryService.load()` initializes ArcPipeline from new path
- [ ] `python -m memory_service --health` reports healthy
- [ ] No import errors in test_e2e_chain.py (via shim)

## Notes for Next Phase

- Phase 4 (index/) is independent of Phase 3
- Phase 5 (reconcile/) will replace the `reconcile_tasks()` and `reconcile_deviations()` methods in pipeline.py with delegates to the reconcile/ package
