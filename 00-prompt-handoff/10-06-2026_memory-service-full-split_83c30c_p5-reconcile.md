# Phase 5: Merge reconciliation.py + ArcReconciler → reconcile/ (Stage 4)

**Parent plan:** `10-06-2026_memory-service-full-split_83c30c.md`
**Phase:** 5 of 9
**Dependencies:** Phase 1 (needs `store/work_items.py`, `store/deviations.py`)
**Estimated effort:** ~40 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:** `memory_service/reconciliation.py` (640 lines) + `arc_summarizer/reconcile.py` (773 lines) → 5 files under `memory_service/reconcile/`
**Related codebases:** `arc_summarizer/reconcile.py` is imported by `test_e2e_chain.py`

## What This Phase Delivers

Merges the two reconciliation modules into one cohesive `reconcile/` package. Eliminates the artificial split between `TaskReconciler` (dedup/classify) and `ArcReconciler` (file I/O, extraction).

The unified reconciler reads consolidation MD from `arc-memory/`, extracts tasks/deviations/carry-forward, deduplicates against existing state, and writes reconciliation MD to `arc-reconcile/`.

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete
- [ ] `memory_service/store/work_items.py` and `store/deviations.py` exist
- [ ] `python -c "from super_council.memory_service.store import RelationalStore"` succeeds

## Implementation Steps

### Step 1: Create `reconcile/dedup.py`

Normalization, dedup keys, title similarity — from `TaskReconciler`:

```python
# reconcile/dedup.py
"""Stage 4: Task normalization, deduplication, similarity matching."""

import re
import math
from typing import Dict, Optional

class DedupEngine:
    """Normalize titles, compute dedup keys, measure similarity."""

    @staticmethod
    def normalize_title(title: str) -> str:
        """Normalize task title for comparison.

        Moved from TaskReconciler.normalize_title()
        """
        # ... verbatim ...

    @staticmethod
    def compute_dedup_key(title: str, project_id: str = "") -> str:
        """Compute deduplication key from normalized title.

        Moved from TaskReconciler.compute_dedup_key()
        """
        # ... verbatim ...

    @staticmethod
    def title_similarity(title_a: str, title_b: str) -> float:
        """Compute title similarity (0.0 to 1.0).

        Moved from TaskReconciler.title_similarity()
        """
        # ... verbatim ...
```

### Step 2: Create `reconcile/classifier.py`

Evidence-based classification, candidate analysis — from `TaskReconciler`:

```python
# reconcile/classifier.py
"""Stage 4: Evidence-based classification and candidate analysis."""

from typing import Dict, List, Optional

class ReconciliationClassifier:
    """Classify reconciliation candidates from evidence."""

    @staticmethod
    def classify_from_evidence(evidence_text: str) -> Optional[str]:
        """Classify task/deviation from evidence text.

        Moved from TaskReconciler.classify_from_evidence()
        """
        # ... verbatim ...

    @staticmethod
    def classify_candidate(candidate: Dict, existing_items: List[Dict]) -> Dict:
        """Classify a reconciliation candidate against existing items.

        Moved from TaskReconciler.classify_candidate()
        """
        # ... verbatim ...

    @staticmethod
    def classify_deviation_candidate(candidate: Dict, existing_deviations: List[Dict]) -> Dict:
        """Classify a deviation candidate.

        Moved from TaskReconciler._classify_deviation_candidate()
        """
        # ... verbatim ...

    @staticmethod
    def apply_classification(candidate: Dict, classification: str) -> Dict:
        """Apply classification result to candidate.

        Moved from TaskReconciler._apply_classification()
        """
        # ... verbatim ...
```

### Step 3: Create `reconcile/extractor.py`

Task/deviation/carry-forward extraction from MD — from `ArcReconciler`:

```python
# reconcile/extractor.py
"""Stage 4: Task, deviation, and carry-forward extraction from MD files."""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional

class ReconciliationExtractor:
    """Extract structured data from consolidation/reconciliation MD files."""

    @staticmethod
    def parse_consolidation_md(content: str) -> Dict[str, any]:
        """Parse consolidation MD into structured dict.

        Moved from ArcReconciler._parse_consolidation_md()
        """
        # ... verbatim ...

    @staticmethod
    def parse_reconciliation_md(content: str) -> List[Dict]:
        """Parse reconciliation MD into list of items.

        Moved from ArcReconciler._parse_reconciliation_md()
        """
        # ... verbatim ...

    @staticmethod
    def extract_tasks(consolidation: Dict) -> List[Dict]:
        """Extract tasks from consolidation output.

        Moved from ArcReconciler._extract_tasks()
        """
        # ... verbatim ...

    @staticmethod
    def extract_deviations(consolidation: Dict) -> List[Dict]:
        """Extract deviations from consolidation output.

        Moved from ArcReconciler._extract_deviations()
        """
        # ... verbatim ...

    @staticmethod
    def extract_carry_forward(consolidation: Dict) -> List[Dict]:
        """Extract carry-forward items from consolidation output.

        Moved from ArcReconciler._extract_carry_forward()
        """
        # ... verbatim ...

    @staticmethod
    def parse_bullet_list(text: str) -> List[str]:
        """Parse bullet list from MD text.

        Moved from ArcReconciler._parse_bullet_list()
        """
        # ... verbatim ...

    @staticmethod
    def parse_structured_items(text: str) -> List[Dict]:
        """Parse structured items from MD text.

        Moved from ArcReconciler._parse_structured_items()
        """
        # ... verbatim ...
```

### Step 4: Create `reconcile/writer.py`

Reconciliation MD file writing — from `ArcReconciler`:

```python
# reconcile/writer.py
"""Stage 4: Reconciliation MD file writing."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

class ReconciliationWriter:
    """Write reconciliation outputs to arc-reconcile/."""

    def __init__(self, memory_base: str = "~/.council-memory"):
        self._memory_base = Path(memory_base).expanduser()
        self._reconcile_dir = self._memory_base / "arc-reconcile" / "daily"
        self._reconcile_dir.mkdir(parents=True, exist_ok=True)

    @property
    def reconcile_dir(self) -> Path:
        return self._reconcile_dir

    def write_tasks(self, tasks: List[Dict], tier_id: str) -> Path:
        """Write task reconciliation to arc-reconcile/daily/tasks.md.

        Moved from ArcReconciler._write_reconciliation_file() — task variant
        """
        # ... verbatim (adapted for tasks) ...

    def write_deviations(self, deviations: List[Dict], tier_id: str) -> Path:
        """Write deviation reconciliation to arc-reconcile/daily/deviations.md.

        Moved from ArcReconciler._write_reconciliation_file() — deviation variant
        """
        # ... verbatim (adapted for deviations) ...

    def _write_reconciliation_file(self, filename: str, items: List[Dict], tier_id: str) -> Path:
        """Write reconciliation file.

        Moved from ArcReconciler._write_reconciliation_file()
        """
        # ... verbatim ...
```

### Step 5: Create `reconcile/reconciler.py`

The unified `ArcReconciler` — orchestrates dedup, classify, extract, write:

```python
# reconcile/reconciler.py
"""Stage 4: Unified reconciliation orchestrator.

Replaces TaskReconciler + ArcReconciler with single cohesive unit.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .dedup import DedupEngine
from .classifier import ReconciliationClassifier
from .extractor import ReconciliationExtractor
from .writer import ReconciliationWriter

log = logging.getLogger(__name__)


class Reconciler:
    """Unified reconciliation: consolidation MD → tasks/deviations/carry-forward → arc-reconcile/.

    Replaces TaskReconciler (dedup/classify) and ArcReconciler (file I/O/extraction).
    """

    def __init__(self, memory_base: str = "~/.council-memory", relational_store=None):
        self._memory_base = Path(memory_base).expanduser()
        self._store = relational_store

        # Compose sub-modules
        self._dedup = DedupEngine()
        self._classifier = ReconciliationClassifier()
        self._extractor = ReconciliationExtractor()
        self._writer = ReconciliationWriter(memory_base)

    @property
    def reconcile_dir(self) -> Path:
        return self._writer.reconcile_dir

    def reconcile_tier(self, tier_id: str) -> bool:
        """Reconcile a single tier: read → extract → dedup → classify → write.

        Moved from ArcReconciler.reconcile_tier()
        """
        # Read latest consolidation
        consolidation = self._read_latest_consolidation(tier_id)
        if not consolidation:
            log.warning("No consolidation found for tier %s", tier_id)
            return False

        # Extract structured data
        tasks = self._extractor.extract_tasks(consolidation)
        deviations = self._extractor.extract_deviations(consolidation)
        carry_forward = self._extractor.extract_carry_forward(consolidation)

        # Read existing state
        existing = self._read_existing_state(tier_id)

        # Dedup and classify
        deduped_tasks = self._dedup_and_classify_tasks(tasks, existing.get("tasks", []))
        deduped_deviations = self._dedup_and_classify_deviations(deviations, existing.get("deviations", []))

        # Write reconciliation outputs
        self._writer.write_tasks(deduped_tasks, tier_id)
        self._writer.write_deviations(deduped_deviations, tier_id)

        log.info("Reconciled tier %s: %d tasks, %d deviations, %d carry-forward",
                 tier_id, len(deduped_tasks), len(deduped_deviations), len(carry_forward))
        return True

    def reconcile_all_tiers(self) -> Dict[str, bool]:
        """Reconcile all tiers.

        Moved from ArcReconciler.reconcile_all_tiers()
        """
        # ... verbatim ...

    def _read_latest_consolidation(self, tier_id: str) -> Optional[Dict]:
        """Read latest consolidation MD for tier.

        Moved from ArcReconciler._read_latest_consolidation()
        """
        # ... verbatim ...

    def _read_existing_state(self, tier_id: str) -> Dict:
        """Read existing reconciliation state.

        Moved from ArcReconciler._read_existing_state()
        """
        # ... verbatim ...

    def _dedup_and_classify_tasks(self, tasks: List[Dict], existing: List[Dict]) -> List[Dict]:
        """Dedup and classify tasks against existing state."""
        result = []
        for task in tasks:
            dedup_key = self._dedup.compute_dedup_key(task.get("title", ""))
            # Check against existing
            is_dup = any(
                self._dedup.title_similarity(task.get("title", ""), e.get("title", "")) > 0.85
                for e in existing
            )
            if not is_dup:
                classified = self._classifier.classify_candidate(task, existing)
                result.append(classified)
        return result

    def _dedup_and_classify_deviations(self, deviations: List[Dict], existing: List[Dict]) -> List[Dict]:
        """Dedup and classify deviations against existing state."""
        result = []
        for dev in deviations:
            classified = self._classifier.classify_deviation_candidate(dev, existing)
            result.append(classified)
        return result
```

### Step 6: Wire `reconcile/__init__.py`

```python
# reconcile/__init__.py
"""Stage 4: Consolidation → Reconciliation Outputs.

Reads consolidation MD, extracts tasks/deviations/carry-forward,
deduplicates, classifies, and writes reconciliation MD to arc-reconcile/.
"""
from .reconciler import Reconciler
from .dedup import DedupEngine
from .classifier import ReconciliationClassifier
from .extractor import ReconciliationExtractor
from .writer import ReconciliationWriter

__all__ = [
    "Reconciler",
    "DedupEngine",
    "ReconciliationClassifier",
    "ReconciliationExtractor",
    "ReconciliationWriter",
]
```

### Step 7: Delete old reconciliation files

```bash
rm memory_service/reconciliation.py
# arc_summarizer/reconcile.py was already handled in Phase 3
```

### Step 8: Create backward-compat shim in arc_summarizer/

If `test_e2e_chain.py` imports `ArcReconciler` directly, add to the shim:

```python
# In arc_summarizer/__init__.py (add to existing shim):
from super_council.memory_service.reconcile.reconciler import Reconciler as ArcReconciler
```

### Step 9: Phase Gate

```bash
cd /home/chief/Coding-Projects/7-council/super_council
python -c "from super_council.memory_service.reconcile import Reconciler, DedupEngine, ReconciliationClassifier; print('OK')"
python -c "from super_council.arc_summarizer import ArcReconciler; print('OK')"  # shim test
python -c "from super_council.memory_service import MemoryService; ms = MemoryService.load(); print(ms.health_check())"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `reconcile/dedup.py` | Normalization, dedup keys, title similarity |
| Create | `reconcile/classifier.py` | Evidence-based classification, candidate analysis |
| Create | `reconcile/extractor.py` | Task/deviation/carry-forward extraction from MD |
| Create | `reconcile/writer.py` | Reconciliation MD file writing |
| Create | `reconcile/reconciler.py` | Unified Reconciler (orchestrates all sub-modules) |
| Modify | `reconcile/__init__.py` | Re-export all Stage 4 classes |
| Modify | `arc_summarizer/__init__.py` | Add ArcReconciler shim |
| Delete | `reconciliation.py` | Replaced by reconcile/ package |

## Phase-Specific Tests

1. **Import test:** `python -c "from super_council.memory_service.reconcile import Reconciler; print('OK')"` — must succeed
2. **Dedup test:** `python -c "from super_council.memory_service.reconcile.dedup import DedupEngine; print(DedupEngine.title_similarity('fix auth bug', 'Fix authentication bug'))"` — should return > 0.8
3. **Shim test:** `python -c "from super_council.arc_summarizer import ArcReconciler; print('OK')"` — must succeed

## Completion Gate

- [ ] All 5 reconcile/ modules created
- [ ] `reconciliation.py` deleted
- [ ] `ArcReconciler` shim works in `arc_summarizer/__init__.py`
- [ ] `Reconciler` composes DedupEngine, ReconciliationClassifier, ReconciliationExtractor, ReconciliationWriter
- [ ] `python -m memory_service --health` reports healthy
- [ ] No import errors

## Notes for Next Phase

- Phase 6 (recall/) is independent of Phase 5
- In Phase 8, `ArcPipeline.reconcile_tasks()` and `reconcile_deviations()` will be updated to delegate to `reconcile.reconciler.Reconciler`
