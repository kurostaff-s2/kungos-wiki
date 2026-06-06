# Phase 3: Reconciler Thresholds + Deviation Candidates

**Parent plan:** `06-06-2026_session-summarization-flexible-reconciliation_59130b.md`
**Phase:** 3 of 4
**Dependencies:** Phase 1 (trimmed summary must be available)
**Can parallel with:** Phase 2 (Adaptive Triggers)
**Estimated effort:** ~40 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/memory_service/reconciliation.py` (modify — threshold bands, subsystem alignment)
- `super_council/arc_summarizer/pipeline.py` (modify — deviation candidate creation)
- `super_council/memory_service/store.py` (modify — deviation CRUD if needed)

---

## What This Phase Delivers

Tighter reconciliation threshold banding. Subsystem alignment check for borderline matches. Deviation candidates created from plan-vs-reality signals in trimmed summaries.

**New threshold banding:**
| Score | Action |
|-------|--------|
| >= 0.90 | Auto-merge / exact-equivalent |
| 0.80–0.89 | Safe merge if project AND subsystem align |
| 0.50–0.79 | Candidate only, require review or secondary evidence |
| < 0.50 | No match, create new task or deviation candidate |

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (trimmed summary available)
- [ ] SessionAnalyzer.trim_session() returns 11-field schema
- [ ] Existing reconciler tests pass (baseline: 36 tests)

---

## Implementation Steps

### Step 1: Update Threshold Banding

Modify `super_council/memory_service/reconciliation.py`:

```python
# Replace existing threshold logic in classify_candidate()

# Current: >= 0.8 auto-apply, 0.5-0.8 flag, < 0.5 skip
# New: >= 0.90 auto-merge, 0.80-0.89 with alignment, 0.50-0.79 candidate only

if best_similarity >= 0.90 and best_match:
    # High confidence — auto-merge regardless of subsystem
    evidence_status = self.classify_from_evidence(candidate_evidence)
    if evidence_status == 'done':
        return {
            'action': 'mark_done',
            'confidence': best_similarity,
            'target_id': best_match['id'],
            'reason': f'high-confidence match ({best_similarity:.2f}) + completion evidence',
        }
    elif evidence_status:
        return {
            'action': 'update',
            'confidence': best_similarity,
            'target_id': best_match['id'],
            'reason': f'high-confidence match ({best_similarity:.2f}) + status evidence',
        }
    else:
        return {
            'action': 'ignore_duplicate',
            'confidence': best_similarity,
            'target_id': best_match['id'],
            'reason': f'high-confidence match ({best_similarity:.2f}), no status change',
        }

elif best_similarity >= 0.80 and best_match:
    # Medium-high confidence — require subsystem alignment
    candidate_subsystem = candidate.get('subsystem') or candidate.get('file_path')
    match_subsystem = best_match.get('subsystem') or best_match.get('file_path')

    if candidate_subsystem and match_subsystem and candidate_subsystem == match_subsystem:
        # Subsystems align — safe merge
        evidence_status = self.classify_from_evidence(candidate_evidence)
        if evidence_status:
            return {
                'action': 'update',
                'confidence': best_similarity,
                'target_id': best_match['id'],
                'reason': f'medium-high match ({best_similarity:.2f}) + aligned subsystem + evidence',
            }
        return {
            'action': 'ignore_duplicate',
            'confidence': best_similarity,
            'target_id': best_match['id'],
            'reason': f'medium-high match ({best_similarity:.2f}) + aligned subsystem, no status change',
        }
    else:
        # Subsystems don't align — candidate only
        return {
            'action': 'candidate_review',
            'confidence': best_similarity,
            'target_id': best_match['id'],
            'reason': f'medium-high match ({best_similarity:.2f}) but subsystem mismatch, needs review',
            'needs_review': True,
        }

elif best_similarity >= 0.50 and best_match:
    # Medium confidence — candidate only, require secondary evidence
    return {
        'action': 'candidate_review',
        'confidence': best_similarity,
        'target_id': best_match['id'],
        'reason': f'medium match ({best_similarity:.2f}), needs secondary evidence',
        'needs_review': True,
    }
```

### Step 2: Add Deviation Candidate Creation

Add to `super_council/memory_service/reconciliation.py`:

```python
def _classify_deviation_candidate(
    self,
    candidate: dict,
    existing_items: list,
    trimmed_summary: dict = None,
) -> Optional[dict]:
    """Check if a borderline match suggests a plan-vs-reality deviation.

    When fuzzy match is 0.50-0.79 AND evidence suggests the implementation
    diverged from the original plan, create a deviation candidate instead
    of a new task.

    Args:
        candidate: Task candidate dict.
        existing_items: List of existing work items.
        trimmed_summary: Optional trimmed summary with deviation signals.

    Returns:
        Deviation candidate dict, or None if no deviation detected.
    """
    candidate_title = candidate.get('title', '')
    candidate_evidence = candidate.get('evidence', '')

    # Check for deviation signals in evidence
    deviation_keywords = [
        'instead of', 'changed from', 'diverged', 'original plan',
        'intended', 'planned', 'approach changed', 'switched to',
        'not using', 'abandoned', 'replaced with',
    ]
    evidence_lower = candidate_evidence.lower()
    has_deviation_signal = any(kw in evidence_lower for kw in deviation_keywords)

    # Check trimmed summary for notable_deviations
    if trimmed_summary and trimmed_summary.get('notable_deviations'):
        has_deviation_signal = True

    if not has_deviation_signal:
        return None

    # Find borderline match
    best_similarity = 0.0
    best_match = None
    for item in existing_items:
        sim = self.title_similarity(candidate_title, item['title'])
        if sim > best_similarity:
            best_similarity = sim
            best_match = item

    # Only create deviation candidate for borderline matches (0.50-0.79)
    if best_similarity < 0.50 or best_similarity >= 0.80:
        return None

    return {
        'action': 'create_deviation_candidate',
        'confidence': best_similarity,
        'candidate_title': candidate_title,
        'existing_title': best_match['title'] if best_match else None,
        'evidence': candidate_evidence,
        'deviation_type': 'unplanned',  # Default type
        'severity': 'moderate',  # Default severity
    }
```

### Step 3: Wire Deviation Candidates into Pipeline

Add to `super_council/arc_summarizer/pipeline.py`:

```python
def reconcile_tasks_with_deviations(
    self,
    consolidation_text: str,
    tier_id: str,
    trimmed_summary: dict = None,
    project_id: str = None,
    run_id: str = None,
    source_summary_id: str = None,
) -> Optional[dict]:
    """Reconcile tasks with deviation candidate creation.

    Extends reconcile_tasks() to also create deviation candidates
    from borderline matches with plan-vs-reality signals.

    Args:
        consolidation_text: Raw YAML/text output from ARC consolidation.
        tier_id: Tier identifier.
        trimmed_summary: Optional trimmed summary from SessionAnalyzer.
        project_id: Target project.
        run_id: Current run ID for provenance.
        source_summary_id: Source summary ID for provenance.

    Returns:
        Dict with 'tasks' (reconciliation results) and 'deviations' (deviation candidates).
    """
    # Run standard task reconciliation
    task_results = self.reconcile_tasks(
        consolidation_text=consolidation_text,
        tier_id=tier_id,
        project_id=project_id,
        run_id=run_id,
        source_summary_id=source_summary_id,
    )

    # Check for deviation candidates
    deviation_candidates = []
    if trimmed_summary:
        from ..memory_service.reconciliation import TaskReconciler
        reconciler = TaskReconciler()

        # Get existing items for deviation candidate check
        existing = self._relational_store.get_work_items(project_id=project_id) if project_id else []

        # Check each open work item for deviation signals
        for open_item in trimmed_summary.get('open_work', []):
            candidate = {
                'title': open_item,
                'evidence': open_item,  # Use as both title and evidence
            }
            dev_candidate = reconciler._classify_deviation_candidate(
                candidate, existing, trimmed_summary
            )
            if dev_candidate:
                deviation_candidates.append(dev_candidate)

        # Check notable_deviations directly
        for deviation_text in trimmed_summary.get('notable_deviations', []):
            deviation_candidates.append({
                'action': 'create_deviation_candidate',
                'confidence': 0.7,
                'candidate_title': deviation_text,
                'evidence': deviation_text,
                'deviation_type': 'unplanned',
                'severity': 'moderate',
            })

    # Create deviation records from candidates
    deviations_created = []
    if deviation_candidates and project_id:
        for candidate in deviation_candidates:
            try:
                dev = self._relational_store.create_deviation(
                    project_id=project_id,
                    deviation_type=candidate.get('deviation_type', 'unplanned'),
                    severity=candidate.get('severity', 'moderate'),
                    title=candidate.get('candidate_title', ''),
                    description=candidate.get('evidence', ''),
                    original_expectation=candidate.get('existing_title', ''),
                    run_id=run_id,
                    source_summary_id=source_summary_id,
                )
                deviations_created.append(dev)
            except Exception as e:
                log.warning("Deviation candidate creation failed: %s", e)

    return {
        'tasks': task_results,
        'deviations': deviations_created,
    }
```

### Step 4: Add Raw Session Fallback

Add to `super_council/memory_service/reconciliation.py`:

```python
def _load_raw_session(self, raw_path: str) -> Optional[str]:
    """Load raw session text for low-confidence match verification.

    Only called when confidence is 0.50-0.79 and human review is triggered.

    Args:
        raw_path: Path to raw session summary file.

    Returns:
        Raw text content, or None on failure.
    """
    try:
        import pathlib
        path = pathlib.Path(raw_path)
        if path.exists():
            return path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        log.warning("Failed to load raw session: %s", e)
    return None
```

Store raw_path in trimmed summary:
```python
# In SessionAnalyzer.trim_session():
result['_extra']['raw_path'] = raw_path  # If available
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/reconciliation.py` | Threshold bands, subsystem alignment, deviation candidates, raw fallback |
| Modify | `arc_summarizer/pipeline.py` | reconcile_tasks_with_deviations() |

---

## Phase-Specific Tests

1. **Threshold 0.90+ auto-merges:** Similarity >= 0.90 → action = ignore_duplicate or update
2. **Threshold 0.80-0.89 with aligned subsystem:** Similarity 0.80-0.89 + same subsystem → safe merge
3. **Threshold 0.80-0.89 with mismatched subsystem:** Similarity 0.80-0.89 + different subsystem → candidate_review
4. **Threshold 0.50-0.79 candidate only:** Similarity 0.50-0.79 → action = candidate_review
5. **Threshold < 0.50 creates new:** Similarity < 0.50 → action = create
6. **Deviation candidate from borderline match:** 0.50-0.79 + deviation keywords → create_deviation_candidate
7. **Deviation candidate from trimmed summary:** notable_deviations in trimmed → deviation candidates created
8. **Raw session fallback loads on low confidence:** raw_path available → text loaded for review
9. **reconcile_tasks_with_deviations returns both:** tasks and deviations in result dict

---

## Completion Gate

- [ ] Threshold banding updated (0.90/0.80/0.50)
- [ ] Subsystem alignment check for 0.80-0.89 band
- [ ] Deviation candidate creation from borderline matches
- [ ] Deviation candidate creation from trimmed summary signals
- [ ] Raw session fallback for low-confidence matches
- [ ] reconcile_tasks_with_deviations() wired into pipeline
- [ ] All phase-specific tests pass
- [ ] No regression in existing reconciliation tests

---

## Notes for Next Phase

Phase 4 (Production Wiring) expects:
- All threshold bands working correctly
- Deviation candidates flowing from reconciliation to plan_deviations table
- reconcile_tasks_with_deviations() available for production wiring
- Raw session fallback available for human review
