# Phase 3: ARC Wiring

**Parent plan:** `06-06-2026_task-ledger-deviation-tracking_3fce71.md`
**Phase:** 3 of 5
**Dependencies:** Phase 2 (reconciliation engine must be complete)
**Estimated effort:** ~45 min

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Key files for this phase:**
- `super_council/arc_summarizer/prompts.py` (modify — add task extraction prompt)
- `super_council/arc_summarizer/pipeline.py` (modify — add reconciliation step)
- `super_council/arc_summarizer/client.py` (modify — add task extraction endpoint)

---

## What This Phase Delivers

ARC pipeline extended to extract structured task deltas from session summaries and route them through the reconciliation engine into `work_items`. Closes the loop: session → ARC → reconciliation → storage.

---

## Pre-Flight Checklist

- [ ] Phase 1 is marked complete (schema migration)
- [ ] Phase 2 is marked complete (reconciliation engine)
- [ ] `TaskReconciler.reconcile()` works with ARC delta dict
- [ ] `RelationalStore.reconcile_arc_delta()` entry point exists

---

## Implementation Steps

### Step 1: Add Task Extraction Prompt

Add to `super_council/arc_summarizer/prompts.py`:

```python
TASK_EXTRACTION_PROMPT_TEMPLATE = """**Role:** You are a task extraction engine. Extract structured work signals from session summaries.

**Rules:**
1. Extract ONLY explicitly stated work items. Do NOT infer tasks from general discussion.
2. For each task, include: title, description (if available), priority (low/medium/high/critical), subsystem (if identifiable), evidence (the exact text that signals this task).
3. Classify each signal: new_task, task_update, completed_task, blocked_task, open_question, ignored_candidate.
4. For ignored candidates, include reason: vague, hypothetical, duplicate, not_actionable.
5. Output MUST be valid YAML. No prose outside the YAML block.

**Output Schema:**
```yaml
new_tasks:
  - title: <string — concise task title>
    description: <string — context or details>
    priority: <low|medium|high|critical>
    subsystem: <string — component or module, if identifiable>
    evidence: <string — exact text signaling this task>
task_updates:
  - title: <string — matches existing task title>
    description: <string — updated context>
    priority: <low|medium|high|critical>
    evidence: <string — text signaling the update>
completed_tasks:
  - title: <string — matches existing task title>
    evidence: <string — text signaling completion>
blocked_tasks:
  - title: <string — matches existing task title>
    blocker: <string — what is blocking>
    evidence: <string — text signaling the block>
open_questions:
  - title: <string — question or follow-up>
    context: <string — surrounding context>
    evidence: <string — text signaling the question>
ignored_candidates:
  - title: <string — candidate that was ignored>
    reason: <vague|hypothetical|duplicate|not_actionable>
```

**Source Material:**
<BEGIN MATERIAL>
{input_material}
<END MATERIAL>

Extract the structured task signals now. Output ONLY the YAML block."""


def build_task_extraction_prompt(input_material: str) -> str:
    """Build task extraction prompt."""
    return TASK_EXTRACTION_PROMPT_TEMPLATE.format(input_material=input_material)


def parse_task_extraction_yaml(yaml_text: str) -> dict:
    """Parse task extraction YAML into structured delta dict."""
    import yaml
    try:
        data = yaml.safe_load(yaml_text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Fallback: use _parse_yaml_fallback from client.py
    from .client import _parse_yaml_fallback
    return _parse_yaml_fallback(yaml_text) or {}
```

### Step 2: Add Task Extraction to ArcClient

Add to `super_council/arc_summarizer/client.py`:

```python
def extract_tasks(self, session_text: str) -> Optional[dict]:
    """Extract structured task signals from session text.

    Args:
        session_text: Session summary or consolidation output text.

    Returns:
        Parsed task delta dict, or None on failure.
    """
    prompt = build_task_extraction_prompt(session_text)
    raw = self._call_with_fallback(
        system=SYSTEM_EXTRACTION,
        user=prompt,
        max_tokens=self._config.extraction_max_tokens,
        temperature=0.3,
        retries=1,
        label="task-extraction",
    )
    if raw:
        from .prompts import parse_task_extraction_yaml
        return parse_task_extraction_yaml(raw)
    return None
```

### Step 3: Add Reconciliation Step to Pipeline

Modify `super_council/arc_summarizer/pipeline.py`:

**3a. Add method to ArcPipeline:**
```python
def reconcile_tasks(self, consolidation_text: str, tier_id: str, project_id: str = None, run_id: str = None, source_summary_id: str = None) -> Optional[list]:
    """Extract tasks from consolidation output and reconcile against existing work items.

    Args:
        consolidation_text: Raw YAML/text output from ARC consolidation.
        tier_id: Tier identifier that produced this consolidation.
        project_id: Target project for task reconciliation.
        run_id: Current run ID for provenance linkage.
        source_summary_id: Source summary ID for provenance linkage.

    Returns:
        List of reconciliation results, or None if no tasks extracted.
    """
    if not self._relational_store:
        log.warning("Task reconciliation: no relational store configured")
        return None

    # Resolve project_id
    if not project_id:
        try:
            resolution = self._relational_store.resolve_project_from_context(is_system_operation=True)
            if resolution.is_writable:
                project_id = resolution.project_id
        except Exception as e:
            log.warning("Task reconciliation: could not resolve project_id: %s", e)
            return None

    # Extract tasks from consolidation text
    arc_delta = self._client.extract_tasks(consolidation_text)
    if not arc_delta:
        log.info("Task reconciliation: no tasks extracted from consolidation")
        return None

    # Count extracted signals
    total_signals = sum(
        len(arc_delta.get(k, []))
        for k in ('new_tasks', 'task_updates', 'completed_tasks', 'blocked_tasks', 'open_questions', 'ignored_candidates')
    )
    if total_signals == 0:
        log.info("Task reconciliation: no task signals in extraction")
        return None

    log.info("Task reconciliation: %d signals extracted, reconciling for project %s", total_signals, project_id)

    # Reconcile against existing work items
    results = self._relational_store.reconcile_arc_delta(
        arc_delta=arc_delta,
        project_id=project_id,
        run_id=run_id,
        source_summary_id=source_summary_id,
    )

    # Log summary
    applied = sum(1 for r in results if r.get('applied'))
    needs_review = sum(1 for r in results if r.get('needs_review'))
    log.info("Task reconciliation: %d applied, %d need review, %d total", applied, needs_review, len(results))

    return results
```

**3b. Wire into consolidation pipeline:**
```python
# In run_tiered_consolidation(), after step 5 (_write_tier_output):
if summary_id:
    # Reconcile tasks from consolidation output
    try:
        # Re-extract consolidation text for task extraction
        consolidation_text = self._gather_tier_input(tier_id)
        if consolidation_text:
            self.reconcile_tasks(
                consolidation_text=consolidation_text,
                tier_id=tier_id,
                run_id=None,  # Will be set by caller if available
                source_summary_id=summary_id,
            )
    except Exception as e:
        log.warning("Task reconciliation failed (non-fatal): %s", e)
```

### Step 4: Add Task Extraction to Scheduler

Modify `super_council/arc_summarizer/scheduler.py` to trigger task reconciliation after each consolidation run:

```python
# After each tiered consolidation, call reconcile_tasks()
# This is already wired in Step 3b, but ensure the scheduler passes run_id
```

### Step 5: Verify End-to-End Flow

Test the full flow:
1. ARC consolidation produces YAML output
2. Task extraction parses YAML into structured delta
3. Reconciliation compares against existing work_items
4. New tasks are created, duplicates are ignored, completed tasks are marked done
5. Provenance linkage (run_id, source_summary_id) is correct

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/arc_summarizer/prompts.py` | Add task extraction prompt and parsing |
| Modify | `super_council/arc_summarizer/client.py` | Add `extract_tasks()` method |
| Modify | `super_council/arc_summarizer/pipeline.py` | Add `reconcile_tasks()` step to consolidation pipeline |

---

## Phase-Specific Tests

1. **Task extraction prompt returns valid YAML:** Feed session summary → parse YAML → verify structure
2. **Task extraction identifies signals:** "Fix bug X" → new_task; "Completed Y" → completed_task; "Blocked by Z" → blocked_task
3. **Reconciliation step doesn't crash on empty output:** Empty consolidation → no errors
4. **New tasks are created:** New task signal → work_item created with correct provenance
5. **Duplicates are ignored:** Same task mentioned twice → only 1 work_item created
6. **Completed tasks are marked done:** Completion evidence → existing task status → 'done'
7. **Provenance linkage is correct:** run_id and source_summary_id stored in work_item_events

---

## Completion Gate

- [ ] Task extraction prompt added to `prompts.py`
- [ ] `extract_tasks()` method added to `ArcClient`
- [ ] `reconcile_tasks()` step wired into `ArcPipeline`
- [ ] Full end-to-end flow verified (session → ARC → reconciliation → storage)
- [ ] All phase-specific tests pass
- [ ] No regression in existing ARC pipeline methods

---

## Notes for Next Phase

Phase 4 (Deviation Detection) expects:
- Task extraction prompt template and parsing functions
- `ArcClient.extract_tasks()` method
- `ArcPipeline.reconcile_tasks()` method
- Provenance linkage working (run_id, source_summary_id)
