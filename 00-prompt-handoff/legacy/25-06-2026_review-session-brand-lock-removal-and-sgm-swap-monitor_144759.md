# Review Session — Brand Lock Removal + SGM Swap Persistence Monitor

| Field | Value |
|-------|-------|
| Project ID | `kteam-dj-chief` |
| Primary entity ID | `144759` |
| Entity type | `review` |
| Short description | Sequential review of brand-lock-removal plan against codebase/spec, while monitoring SGM swap persistence for Qwen-27B and subagent tool accuracy |
| Status | `draft` |
| Source references | `25-06-2026_brand-lock-removal-and-spec-alignment_dce6ae.md`, `gaming_spec.md`, `cafe_spec.md`, `ecommerce_spec.md`, `identity_spec.md` |
| Generated | 25-06-2026 |
| Next action / owner | Execute Phase 1 (Nemo review) sequentially, then Phase 2 (Gemma), then Phase 3 (GPT) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/kteam-dj-chief`
**Reference docs:** `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/`
**Plan under review:** `/home/chief/llm-wiki/00-prompt-handoff/25-06-2026_brand-lock-removal-and-spec-alignment_dce6ae.md`
**Related handoffs:** `23-06-2026_llama-swap-sgm-decoupling_541155.md`
**Key files for this task:** See plan — `backend/urls.py`, `backend/settings.py`, `domains/*/`, `backend/utils.py`

---

## Session Goals

1. **Spec alignment review:** Verify the brand-lock-removal plan matches actual codebase state and domain specs.
2. **SGM swap persistence monitor:** Confirm Qwen-27B model persists correctly across subagent swaps (model doesn't reset, context carries through).
3. **Subagent tool accuracy monitor:** Verify Nemo, Gemma, and GPT reviewers each use tools (`read`, `bash`, `codegraph_*`) correctly when swapped in via SGM.

## Execution Model

- **Sequential only.** Three reviewers execute one at a time: Nemo → Gemma → GPT.
- Each reviewer receives the same plan + codebase context.
- After each review, record findings and swap to next reviewer.
- Monitor SGM swap behavior at each transition.

---

## Phase 1: Nemo Review (reviewer-nemo)

**Agent:** `reviewer-nemo` (Nemotron-Cascade-2-30B)
**Focus:** Logic and spec alignment — verify plan claims match actual code state.
**Dependencies:** None.

### Steps

1. **SGM Swap Checkpoint A:** Before invoking Nemo, note current model/slot state.
2. **Invoke Nemo** with task: Review the plan at `25-06-2026_brand-lock-removal-and-spec-alignment_dce6ae.md` against the actual codebase at `/home/chief/Coding-Projects/kteam-dj-chief/` and specs at `/home/chief/llm-wiki/Kung_OS/specs/domain_specs/`. Focus on:
   - Are all Phase 1 deletions actually complete? (grep for remaining imports)
   - Do Phase 2 URL changes match `backend/urls.py`?
   - Do Phase 3 naming changes match actual function names in code?
   - Do Phase 4 domain splits match actual directory structure?
   - Are Phase 5 pending items accurately described?
   - Does the spec alignment checklist match reality?
3. **SGM Swap Checkpoint B:** After Nemo completes, note:
   - Did Qwen-27B persist or reset?
   - Did Nemo use tools (`read`, `bash`, `codegraph_*`) correctly?
   - Any tool injection failures?
4. **Record findings** in structured format (see template below).

### Monitoring Checklist

- [ ] SGM swap to Nemo: model state before/after
- [ ] Nemo tool usage: which tools called, any failures
- [ ] Nemo review quality: findings accurate, evidence-backed
- [ ] SGM swap back: model state preserved?

---

## Phase 2: Gemma Review (reviewer-gemma)

**Agent:** `reviewer-gemma` (Gemma-4-26B-A4B)
**Focus:** Architecture review — verify domain split, URL structure, package organization.
**Dependencies:** Phase 1 complete.

### Steps

1. **SGM Swap Checkpoint C:** Note model/slot state before Gemma.
2. **Invoke Gemma** with task: Review the same plan from an architecture perspective. Focus on:
   - Is the domain split (`cafe_arcade/` + `cafe_fnb/`) architecturally sound?
   - Are URL namespaces clean and non-overlapping?
   - Does the legacy package removal plan (kuroadmin/kurostaff) have correct dependency analysis?
   - Are there circular dependencies or missing imports?
   - Does the collection rename plan (`reb_users` → `users_legacy`) account for all references?
3. **SGM Swap Checkpoint D:** After Gemma completes, note:
   - Did Qwen-27B persist or reset?
   - Did Gemma use tools correctly?
   - Any tool injection failures?
4. **Record findings** in structured format.

### Monitoring Checklist

- [ ] SGM swap to Gemma: model state before/after
- [ ] Gemma tool usage: which tools called, any failures
- [ ] Gemma review quality: findings accurate, evidence-backed
- [ ] SGM swap back: model state preserved?

---

## Phase 3: GPT Review (reviewer-gpt)

**Agent:** `reviewer-gpt` (GPT-OSS-20B)
**Focus:** Diverse perspective — fresh eyes, edge cases, things Nemo/Gemma might miss.
**Dependencies:** Phase 2 complete.

### Steps

1. **SGM Swap Checkpoint E:** Note model/slot state before GPT.
2. **Invoke GPT** with task: Review the same plan looking for edge cases, risks, and things the first two reviewers might have missed. Focus on:
   - Residual risks not in the plan's risk table.
   - Missing migration steps (DB collections, data integrity).
   - Test coverage gaps.
   - Whether the "known divergences" are truly acceptable.
   - Any remaining brand-specific code not yet caught.
3. **SGM Swap Checkpoint F:** After GPT completes, note:
   - Did Qwen-27B persist or reset?
   - Did GPT use tools correctly?
   - Any tool injection failures?
4. **Record findings** in structured format.

### Monitoring Checklist

- [ ] SGM swap to GPT: model state before/after
- [ ] GPT tool usage: which tools called, any failures
- [ ] GPT review quality: findings accurate, evidence-backed
- [ ] SGM swap back: model state preserved?

---

## Phase 4: Consolidation Report

**What:** Merge findings from all three reviewers into a single report. Identify consensus findings, disagreements, and SGM swap persistence results.
**Dependencies:** Phases 1-3 complete.

### Report Structure

```markdown
## Review Consolidation

### Consensus Findings (2+ reviewers agreed)
- [Finding with evidence]

### Divergent Findings (reviewers disagreed)
- [Finding A vs Finding B]

### SGM Swap Persistence Results
| Transition | Model Persisted | Tools Worked | Notes |
|------------|-----------------|--------------|-------|
| Parent → Nemo | ✅/❌ | ✅/❌ | |
| Nemo → Parent | ✅/❌ | ✅/❌ | |
| Parent → Gemma | ✅/❌ | ✅/❌ | |
| Gemma → Parent | ✅/❌ | ✅/❌ | |
| Parent → GPT | ✅/❌ | ✅/❌ | |
| GPT → Parent | ✅/❌ | ✅/❌ | |

### Subagent Tool Accuracy
| Reviewer | Tools Used | Tool Failures | Accuracy |
|----------|-----------|---------------|----------|
| Nemo | | | |
| Gemma | | | |
| GPT | | | |

### Recommended Actions
1. [Action based on findings]
```

---

## Constraints

- **Sequential execution only.** No parallel reviewers.
- **Same plan for all reviewers.** Don't modify the plan between reviews.
- **Record SGM state at every swap.** Before and after each transition.
- **Evidence-first findings.** All review claims must cite file paths and line numbers.

## Success Criteria

- [ ] All three reviewers complete reviews sequentially
- [ ] SGM swap persistence documented for all 6 transitions
- [ ] Subagent tool accuracy recorded for all three reviewers
- [ ] Consolidation report produced with consensus/divergent findings
- [ ] Review findings saved to handoff directory

## SGM Swap Persistence — What to Watch

From previous session (`23-06-2026_llama-swap-sgm-decoupling_541155.md`):
- Root cause was SGM proxy misconfiguration preventing proper tool injection
- Mellum reviewer lacked tool access despite config having `tools:` field
- Monitor: Do Nemo, Gemma, GPT all receive tools correctly via SGM swap?
- Monitor: Does Qwen-27B model state persist across swaps (no reset to default)?

---

## Finding Template (use for each reviewer)

```markdown
### Reviewer: [nemo/gemma/gpt]

**SGM State Before:** [model, slot, config]
**SGM State After:** [model, slot, config]
**Model Persisted:** ✅/❌

**Tool Usage:**
- `read`: ✅/❌ ([count] calls)
- `bash`: ✅/❌ ([count] calls)
- `codegraph_*`: ✅/❌ ([count] calls)
- Other: [list]

**Findings:**
1. **[Severity]** [Summary] — [Evidence: file:line] — [Fix/Recommendation]
2. ...

**Quality Notes:**
- Did reviewer cite evidence? ✅/❌
- Did reviewer use tools to verify claims? ✅/❌
- Were findings accurate (spot-checked)? ✅/❌
```

## Next Steps After Session

1. Save consolidation report to `/home/chief/llm-wiki/00-prompt-handoff/`
2. If SGM swap persistence issues found, create follow-up handoff for SGM fix
3. If spec alignment issues found, update the plan document
4. Commit all findings to wiki
