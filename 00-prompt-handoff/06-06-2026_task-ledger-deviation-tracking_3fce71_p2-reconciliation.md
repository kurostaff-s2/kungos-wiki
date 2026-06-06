# Phase 2: Reconciliation Engine

**Parent plan:** `06-06-2026_task-ledger-deviation-tracking_3fce71.md`
**Phase:** 2 of 5
**Dependencies:** Phase 1 (schema migration must be complete)
**Estimated effort:** ~60 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/memory_service/reconciliation.py` (create)
- `super_council/memory_service/store.py` (modify — add reconciliation entry point)

---

## What This Phase Delivers

`TaskReconciler` class that compares ARC-extracted task candidates against existing `work_items`, classifies each as `create`/`merge`/`reopen`/`mark_done`/`ignore_duplicate`, and applies changes with confidence scoring. The critical dedup engine that prevents noise explosion.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (schema migration applied to both databases)
- [ ] `RelationalStore` has CRUD methods for work_items, events, sources
- [ ] `work_items` table has 7-state status model and run_id columns

---

## Implementation Steps

### Step 1: Create `reconciliation.py`

Create `super_council/memory_service/reconciliation.py` with the `TaskReconciler` class.

**1a. Title normalization:**
```python
import re
import unicodedata

def normalize_title(self, title: str) -> str:
    """Normalize title for dedup comparison.
    - Lowercase
    - Strip punctuation
    - Collapse whitespace
    - Remove common prefixes (fix:, feat:, chore:, refactor:)
    """
    # Lowercase
    t = title.lower()
    # Strip punctuation
    t = re.sub(r'[^\w\s]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    # Remove common prefixes
    t = re.sub(r'^(fix|feat|chore|refactor|update|add|remove|delete)\s*[:\-]\s*', '', t)
    return t
```

**1b. Dedup key computation:**
```python
def compute_dedup_key(self, title: str, project_id: str, subsystem: str = None, file_path: str = None) -> str:
    """Compute compound dedup key.
    Key = normalized_title + project_id + optional_subsystem + optional_file_path
    """
    normalized = self.normalize_title(title)
    parts = [normalized, project_id]
    if subsystem:
        parts.append(subsystem.lower().strip())
    if file_path:
        parts.append(file_path.lower().strip())
    return '|'.join(parts)
```

**1c. Title similarity scoring:**
```python
from difflib import SequenceMatcher

def title_similarity(self, title_a: str, title_b: str) -> float:
    """Compute similarity between two titles using token overlap + Levenshtein.
    Returns 0.0 (no match) to 1.0 (exact match).
    """
    norm_a = self.normalize_title(title_a)
    norm_b = self.normalize_title(title_b)

    # Exact match after normalization
    if norm_a == norm_b:
        return 1.0

    # Token overlap (Jaccard similarity)
    tokens_a = set(norm_a.split())
    tokens_b = set(norm_b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    token_sim = intersection / union

    # Sequence matching (handles partial matches)
    seq_sim = SequenceMatcher(None, norm_a, norm_b).ratio()

    # Combined score (weight token overlap higher)
    return 0.6 * token_sim + 0.4 * seq_sim
```

**1d. Evidence keyword classification:**
```python
STATUS_KEYWORDS = {
    'done': ['fixed', 'verified', 'completed', 'done', 'implemented', 'tests passing', 'merged', 'deployed'],
    'blocked': ['blocked by', 'waiting on', 'stuck', 'cannot proceed', 'dependency'],
    'wont_do': ['dropped', 'abandoned', 'not doing', 'out of scope', 'deprecated'],
    'superseded': ['replaced by', 'superseded by', 'new approach', 'replaced with'],
    'open': ['should', 'need to', 'later', 'didn\'t get to', 'todo', 'follow up', 'next'],
}

def classify_from_evidence(self, evidence_text: str) -> Optional[str]:
    """Classify task status from evidence text using keyword matching."""
    text_lower = evidence_text.lower()
    for status, keywords in STATUS_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return status
    return None
```

**1e. Candidate classification:**
```python
def classify_candidate(self, candidate: dict, existing_items: list) -> dict:
    """Classify a task candidate against existing items.
    Returns: {action: str, confidence: float, target_id: str|null, reason: str}
    """
    candidate_title = candidate.get('title', '')
    candidate_project = candidate.get('project_id', '')
    candidate_subsystem = candidate.get('subsystem')
    candidate_evidence = candidate.get('evidence', '')

    # Compute dedup key
    candidate_key = self.compute_dedup_key(candidate_title, candidate_project, candidate_subsystem)

    # Check for exact match
    for item in existing_items:
        item_key = self.compute_dedup_key(item['title'], item['project_id'])
        if candidate_key == item_key:
            # Exact match — determine action from evidence
            evidence_status = self.classify_from_evidence(candidate_evidence)
            if evidence_status == 'done':
                return {'action': 'mark_done', 'confidence': 0.9, 'target_id': item['id'], 'reason': 'exact match + completion evidence'}
            elif evidence_status:
                return {'action': 'update', 'confidence': 0.85, 'target_id': item['id'], 'reason': f'exact match + status evidence: {evidence_status}'}
            else:
                return {'action': 'ignore_duplicate', 'confidence': 0.95, 'target_id': item['id'], 'reason': 'exact match, no status change'}

    # Check for fuzzy match
    best_similarity = 0.0
    best_match = None
    for item in existing_items:
        sim = self.title_similarity(candidate_title, item['title'])
        if sim > best_similarity:
            best_similarity = sim
            best_match = item

    if best_similarity >= 0.75 and best_match:
        # Fuzzy match — determine action from evidence
        evidence_status = self.classify_from_evidence(candidate_evidence)
        if evidence_status == 'done':
            return {'action': 'mark_done', 'confidence': best_similarity * 0.9, 'target_id': best_match['id'], 'reason': f'fuzzy match ({best_similarity:.2f}) + completion evidence'}
        elif evidence_status:
            return {'action': 'update', 'confidence': best_similarity * 0.85, 'target_id': best_match['id'], 'reason': f'fuzzy match ({best_similarity:.2f}) + status evidence'}
        else:
            return {'action': 'ignore_duplicate', 'confidence': best_similarity * 0.9, 'target_id': best_match['id'], 'reason': f'fuzzy match ({best_similarity:.2f}), no status change'}

    # No match — create new
    return {'action': 'create', 'confidence': 0.8, 'target_id': None, 'reason': 'no existing match found'}
```

**1f. Main reconciliation entry point:**
```python
def reconcile(self, arc_delta: dict, project_id: str, store: 'RelationalStore', run_id: str = None, source_summary_id: str = None) -> list:
    """Main reconciliation entry point.
    Input: ARC delta dict with new_tasks[], task_updates[], completed_tasks[], blocked_tasks[], open_questions[]
    Output: List of applied actions with results.
    """
    results = []

    # Get existing items for this project
    existing = store.get_work_items(project_id=project_id, status=None)

    # Process new tasks
    for candidate in arc_delta.get('new_tasks', []):
        candidate['project_id'] = project_id
        classification = self.classify_candidate(candidate, existing)
        result = self._apply_classification(classification, candidate, store, run_id, source_summary_id)
        results.append(result)
        if classification['action'] == 'create':
            existing.append(result.get('item', {}))  # Add to existing for subsequent dedup

    # Process completed tasks
    for candidate in arc_delta.get('completed_tasks', []):
        candidate['project_id'] = project_id
        candidate['evidence'] = candidate.get('evidence', 'completed')
        classification = self.classify_candidate(candidate, existing)
        result = self._apply_classification(classification, candidate, store, run_id, source_summary_id)
        results.append(result)

    # Process blocked tasks
    for candidate in arc_delta.get('blocked_tasks', []):
        candidate['project_id'] = project_id
        candidate['evidence'] = candidate.get('evidence', 'blocked')
        classification = self.classify_candidate(candidate, existing)
        result = self._apply_classification(classification, candidate, store, run_id, source_summary_id)
        results.append(result)

    # Process task updates
    for candidate in arc_delta.get('task_updates', []):
        candidate['project_id'] = project_id
        classification = self.classify_candidate(candidate, existing)
        result = self._apply_classification(classification, candidate, store, run_id, source_summary_id)
        results.append(result)

    # Process open questions (create as proposed tasks)
    for candidate in arc_delta.get('open_questions', []):
        candidate['project_id'] = project_id
        candidate['status'] = 'proposed'
        classification = self.classify_candidate(candidate, existing)
        result = self._apply_classification(classification, candidate, store, run_id, source_summary_id)
        results.append(result)

    return results
```

**1g. Action application with confidence gating:**
```python
def _apply_classification(self, classification: dict, candidate: dict, store: 'RelationalStore', run_id: str = None, source_summary_id: str = None) -> dict:
    """Apply a classification result with confidence gating."""
    action = classification['action']
    confidence = classification['confidence']
    target_id = classification.get('target_id')

    result = {
        'action': action,
        'confidence': confidence,
        'reason': classification['reason'],
        'applied': False,
        'needs_review': confidence < 0.8,  # Medium confidence needs review
    }

    if action == 'create' and confidence >= 0.5:
        # Create new work item
        item = store.get_or_create_work_item(
            project_id=candidate['project_id'],
            kind='task',
            title=candidate['title'],
            description=candidate.get('description', ''),
            priority=candidate.get('priority', 'medium'),
        )
        result['applied'] = True
        result['item'] = item
        # Log event
        store.log_work_item_event(
            task_id=item['id'],
            event_type='created',
            new_status='open',
            run_id=run_id,
            source_summary_id=source_summary_id,
            confidence=confidence,
        )
        # Link source
        store.link_work_item_source(
            task_id=item['id'],
            run_id=run_id,
            source_type='creation',
        )

    elif action == 'mark_done' and confidence >= 0.5:
        # Mark existing item as done
        store.update_work_item_status(target_id, 'done', run_id, source_summary_id)
        result['applied'] = True
        store.log_work_item_event(
            task_id=target_id,
            event_type='completed',
            old_status='open',
            new_status='done',
            run_id=run_id,
            source_summary_id=source_summary_id,
            confidence=confidence,
        )

    elif action == 'update' and confidence >= 0.5:
        # Update existing item (status change from evidence)
        evidence_status = self.classify_from_evidence(candidate.get('evidence', ''))
        if evidence_status:
            store.update_work_item_status(target_id, evidence_status, run_id, source_summary_id)
            result['applied'] = True
            store.log_work_item_event(
                task_id=target_id,
                event_type='status_changed',
                new_status=evidence_status,
                run_id=run_id,
                source_summary_id=source_summary_id,
                confidence=confidence,
            )

    elif action == 'ignore_duplicate':
        result['applied'] = True  # No action needed, but tracked
        result['reason'] += ' (ignored as duplicate)'

    return result
```

### Step 2: Wire into RelationalStore

Add `reconcile_arc_delta()` method to `store.py`:
```python
def reconcile_arc_delta(self, arc_delta: dict, project_id: str, run_id: str = None, source_summary_id: str = None) -> list:
    """Reconcile ARC task delta against existing work items."""
    from .reconciliation import TaskReconciler
    reconciler = TaskReconciler()
    return reconciler.reconcile(
        arc_delta=arc_delta,
        project_id=project_id,
        store=self,
        run_id=run_id,
        source_summary_id=source_summary_id,
    )
```

### Step 3: Test the Reconciliation Engine

Run unit tests for:
- Title normalization produces consistent keys
- Dedup key computation handles optional fields
- Title similarity scoring (exact match = 1.0, no match ≈ 0.0)
- Evidence keyword classification
- Candidate classification (create, mark_done, update, ignore_duplicate)
- Full reconciliation flow with mock store

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/memory_service/reconciliation.py` | TaskReconciler class with dedup, classification, confidence scoring |
| Modify | `super_council/memory_service/store.py` | Add `reconcile_arc_delta()` entry point |

---

## Phase-Specific Tests

1. **Normalization consistency:** `normalize_title("Fix: Add user auth")` == `normalize_title("fix-add-user-auth")` → both produce `add user auth`
2. **Dedup key uniqueness:** Different titles → different keys; same titles → same keys
3. **Similarity scoring:** "Add user auth" vs "Implement user authentication" → score > 0.6
4. **Evidence classification:** "fixed the bug" → 'done'; "blocked by API" → 'blocked'; "should add logging" → 'open'
5. **Candidate classification:** New task → create; duplicate with completion evidence → mark_done; duplicate with no evidence → ignore_duplicate
6. **Confidence gating:** High confidence (0.9) → auto-apply; medium (0.6) → apply with review flag; low (0.3) → skip
7. **Full reconciliation:** 5 duplicate mentions of same task → 1 work item created, 4 ignored

---

## Completion Gate

- [ ] `TaskReconciler` class implemented with all methods
- [ ] Confidence scoring gates auto-apply correctly
- [ ] All phase-specific tests pass
- [ ] `reconcile_arc_delta()` wired into `RelationalStore`
- [ ] No regression in existing `RelationalStore` methods

---

## Notes for Next Phase

Phase 3 (ARC Wiring) expects:
- `TaskReconciler.reconcile()` accepting ARC delta dict
- `RelationalStore.reconcile_arc_delta()` entry point
- Confidence scoring with auto-apply threshold at 0.8
- Evidence keyword classification for status transitions
