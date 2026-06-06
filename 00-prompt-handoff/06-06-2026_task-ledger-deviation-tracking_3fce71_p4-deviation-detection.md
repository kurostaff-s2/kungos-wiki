# Phase 4: Deviation Detection

**Parent plan:** `06-06-2026_task-ledger-deviation-tracking_3fce71.md`
**Phase:** 4 of 5
**Dependencies:** Phase 3 (ARC wiring must be complete)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/arc_summarizer/prompts.py` (modify — add deviation detection prompt)
- `super_council/arc_summarizer/pipeline.py` (modify — add deviation reconciliation step)
- `super_council/memory_service/store.py` (modify — add deviation CRUD if not in Phase 1)

---

## What This Phase Delivers

ARC-powered deviation detection that compares plan/spec documents against implementation summaries and proposes `plan_deviations` records. Captures plan-vs-reality divergence with provenance linkage to work_items.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (schema migration, including `plan_deviations` table)
- [ ] Phase 2 is marked complete (reconciliation engine)
- [ ] Phase 3 is marked complete (ARC wiring for task extraction)
- [ ] `RelationalStore` has deviation CRUD methods

---

## Implementation Steps

### Step 1: Add Deviation Detection Prompt

Add to `super_council/arc_summarizer/prompts.py`:

```python
DEVIATION_DETECTION_PROMPT_TEMPLATE = """**Role:** You are a deviation detection engine. Compare planned architecture/spec against actual implementation and identify divergences.

**Rules:**
1. Compare the plan excerpt against the implementation summary.
2. Identify where implementation diverged from the plan.
3. Classify each deviation: planned (conscious decision), unplanned (unexpected divergence), optimization (intentional improvement).
4. Assess severity: minor (cosmetic), moderate (functional but compatible), major (architectural impact), critical (breaking change).
5. For each deviation, provide: original plan excerpt, actual implementation, rationale (why it diverged), impact scope.
6. Output MUST be valid YAML. No prose outside the YAML block.

**Output Schema:**
```yaml
new_deviations:
  - title: <string — concise deviation title>
    deviation_type: <planned|unplanned|optimization>
    severity: <minor|moderate|major|critical>
    original_plan_summary: <string — what the plan said>
    actual_implementation: <string — what was actually done>
    rationale: <string — why the deviation was needed>
    impact_scope: <string — subsystems/components affected>
    evidence: <string — text signaling the deviation>
deviation_updates:
  - title: <string — matches existing deviation title>
    status: <approved|implemented|closed|rejected>
    decision_summary: <string — what was decided>
    evidence: <string — text signaling the update>
closed_deviations:
  - title: <string — matches existing deviation title>
    closure_reason: <string — why it was closed>
    evidence: <string — text signaling closure>
```

**Plan Excerpt:**
<BEGIN PLAN>
{plan_text}
<END PLAN>

**Implementation Summary:**
<BEGIN IMPLEMENTATION>
{implementation_text}
<END IMPLEMENTATION>

Detect deviations now. Output ONLY the YAML block."""


def build_deviation_detection_prompt(plan_text: str, implementation_text: str) -> str:
    """Build deviation detection prompt."""
    return DEVIATION_DETECTION_PROMPT_TEMPLATE.format(
        plan_text=plan_text or "(no plan excerpt available)",
        implementation_text=implementation_text,
    )
```

### Step 2: Add Deviation Detection to ArcClient

Add to `super_council/arc_summarizer/client.py`:

```python
def detect_deviations(self, plan_text: str, implementation_text: str) -> Optional[dict]:
    """Detect plan-vs-reality deviations.

    Args:
        plan_text: Plan/spec/excerpt describing intended implementation.
        implementation_text: Summary of what was actually implemented.

    Returns:
        Parsed deviation delta dict, or None on failure.
    """
    from .prompts import build_deviation_detection_prompt
    prompt = build_deviation_detection_prompt(plan_text, implementation_text)
    raw = self._call_with_fallback(
        system=SYSTEM_EXTRACTION,
        user=prompt,
        max_tokens=self._config.extraction_max_tokens,
        temperature=0.3,
        retries=1,
        label="deviation-detection",
    )
    if raw:
        from .prompts import parse_task_extraction_yaml
        return parse_task_extraction_yaml(raw)
    return None
```

### Step 3: Add Deviation Reconciliation to Pipeline

Add to `super_council/arc_summarizer/pipeline.py`:

```python
def reconcile_deviations(self, plan_text: str, implementation_text: str, project_id: str = None, run_id: str = None, source_summary_id: str = None) -> Optional[list]:
    """Detect deviations and reconcile against existing plan_deviations.

    Args:
        plan_text: Plan/spec excerpt.
        implementation_text: Implementation summary.
        project_id: Target project for deviation reconciliation.
        run_id: Current run ID for provenance linkage.
        source_summary_id: Source summary ID for provenance linkage.

    Returns:
        List of reconciliation results, or None if no deviations detected.
    """
    if not self._relational_store:
        log.warning("Deviation reconciliation: no relational store configured")
        return None

    # Resolve project_id
    if not project_id:
        try:
            resolution = self._relational_store.resolve_project_from_context(is_system_operation=True)
            if resolution.is_writable:
                project_id = resolution.project_id
        except Exception as e:
            log.warning("Deviation reconciliation: could not resolve project_id: %s", e)
            return None

    # Detect deviations
    deviation_delta = self._client.detect_deviations(plan_text, implementation_text)
    if not deviation_delta:
        log.info("Deviation reconciliation: no deviations detected")
        return None

    # Count detected signals
    total_signals = sum(
        len(deviation_delta.get(k, []))
        for k in ('new_deviations', 'deviation_updates', 'closed_deviations')
    )
    if total_signals == 0:
        log.info("Deviation reconciliation: no deviation signals")
        return None

    log.info("Deviation reconciliation: %d signals detected, processing for project %s", total_signals, project_id)

    # Process new deviations
    results = []
    for deviation in deviation_delta.get('new_deviations', []):
        try:
            dev = self._relational_store.create_deviation(
                project_id=project_id,
                title=deviation['title'],
                deviation_type=deviation.get('deviation_type', 'unplanned'),
                severity=deviation.get('severity', 'moderate'),
                original_plan_summary=deviation.get('original_plan_summary'),
                actual_implementation=deviation.get('actual_implementation'),
                rationale=deviation.get('rationale'),
                impact_scope=deviation.get('impact_scope'),
                run_id=run_id,
                source_summary_id=source_summary_id,
            )
            results.append({'action': 'created', 'deviation': dev})
        except Exception as e:
            log.warning("Deviation creation failed: %s", e)

    # Process deviation updates
    for update in deviation_delta.get('deviation_updates', []):
        try:
            # Find matching deviation by title
            existing = self._relational_store.get_deviations(project_id=project_id)
            for dev in existing:
                if dev['title'] == update['title']:
                    self._relational_store.update_deviation_status(
                        deviation_id=dev['deviation_id'],
                        new_status=update.get('status', 'implemented'),
                        decision_summary=update.get('decision_summary'),
                        run_id=run_id,
                    )
                    self._relational_store.log_deviation_event(
                        deviation_id=dev['deviation_id'],
                        event_type=update.get('status', 'implemented'),
                        run_id=run_id,
                        source_summary_id=source_summary_id,
                    )
                    results.append({'action': 'updated', 'deviation_id': dev['deviation_id']})
                    break
        except Exception as e:
            log.warning("Deviation update failed: %s", e)

    # Process closed deviations
    for closure in deviation_delta.get('closed_deviations', []):
        try:
            existing = self._relational_store.get_deviations(project_id=project_id)
            for dev in existing:
                if dev['title'] == closure['title']:
                    self._relational_store.update_deviation_status(
                        deviation_id=dev['deviation_id'],
                        new_status='closed',
                        decision_summary=closure.get('closure_reason'),
                        run_id=run_id,
                    )
                    self._relational_store.log_deviation_event(
                        deviation_id=dev['deviation_id'],
                        event_type='closed',
                        run_id=run_id,
                        source_summary_id=source_summary_id,
                    )
                    results.append({'action': 'closed', 'deviation_id': dev['deviation_id']})
                    break
        except Exception as e:
            log.warning("Deviation closure failed: %s", e)

    log.info("Deviation reconciliation: %d results processed", len(results))
    return results
```

### Step 4: Wire Deviation Detection into Weekly/Bimonthly Consolidation

Add to `super_council/arc_summarizer/pipeline.py` in `run_tiered_consolidation()`:

```python
# After task reconciliation (for weekly/bimonthly tiers only):
if tier_id in ('weekly', 'bimonthly') and summary_id:
    try:
        # Gather plan text from memory_entries or architecture docs
        plan_text = self._gather_plan_text(project_id)
        # Use consolidation output as implementation text
        implementation_text = consolidation_text
        if plan_text and implementation_text:
            self.reconcile_deviations(
                plan_text=plan_text,
                implementation_text=implementation_text,
                run_id=None,
                source_summary_id=summary_id,
            )
    except Exception as e:
        log.warning("Deviation reconciliation failed (non-fatal): %s", e)
```

### Step 5: Add Deviation Query Methods

Ensure `RelationalStore` has:
```python
def get_deviations_for_project(self, project_id: str, status: str = None) -> List[Dict[str, Any]]:
    """Get all deviations for a project, optionally filtered by status."""

def get_open_deviations(self, project_id: str = None) -> List[Dict[str, Any]]:
    """Get open (not closed/rejected) deviations."""

def get_deviation_with_tasks(self, deviation_id: str) -> Dict[str, Any]:
    """Get deviation with related work_items."""
```

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/arc_summarizer/prompts.py` | Add deviation detection prompt |
| Modify | `super_council/arc_summarizer/client.py` | Add `detect_deviations()` method |
| Modify | `super_council/arc_summarizer/pipeline.py` | Add `reconcile_deviations()` step |
| Modify | `super_council/memory_service/store.py` | Add deviation query methods |

---

## Phase-Specific Tests

1. **Deviation detection prompt returns valid YAML:** Feed plan + implementation → parse YAML → verify structure
2. **Deviation detection identifies mismatches:** Plan says "use X" + implementation says "used Y" → deviation detected
3. **Deviation types are correct:** Conscious change → 'planned'; unexpected → 'unplanned'; improvement → 'optimization'
4. **Severity assessment is reasonable:** Cosmetic change → 'minor'; architectural change → 'major'
5. **Deviation records are created:** New deviation → stored in `plan_deviations` with correct fields
6. **Deviation updates work:** Existing deviation → status updated → event logged
7. **Deviation closure works:** Closed deviation → status → 'closed' → event logged
8. **Provenance linkage is correct:** run_id and source_summary_id stored correctly

---

## Completion Gate

- [ ] Deviation detection prompt added to `prompts.py`
- [ ] `detect_deviations()` method added to `ArcClient`
- [ ] `reconcile_deviations()` step wired into `ArcPipeline`
- [ ] Deviation detection runs after weekly/bimonthly consolidation
- [ ] All phase-specific tests pass
- [ ] No regression in existing ARC pipeline methods

---

## Notes for Next Phase

Phase 5 (Production Wiring) expects:
- Task reconciliation wired into consolidation pipeline
- Deviation detection wired into weekly/bimonthly consolidation
- All CRUD methods in `RelationalStore`
- Provenance linkage working for both tasks and deviations
