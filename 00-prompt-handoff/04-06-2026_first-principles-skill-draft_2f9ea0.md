# Handoff: First Principles Analysis Skill — Draft & Refine

**Source analysis:** `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
**Research findings:** Memory summary `sess-20260604-172046-995cf20a` (FPF, awesome-skills, O'Reilly, AWS Well-Architected)
**Generated:** 04-06-2026
**Goal:** Draft a production-ready first-principles analysis skill document that synthesizes FPF rigor, awesome-skills practicality, and AWS Well-Architected dimensions into a single actionable skill for reviewing, auditing, analyzing, and structuring systems.

---

## Project Context

**Project root:** `/home/chief/llm-wiki/super-council-docs/skills/`
**Reference docs:**
- `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md` (target architecture)
- `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md` (analysis findings)
- FPF framework: `https://github.com/ailev/FPF` (gist: `jtprogru/dbf54077d191d575ace39b6245702be8`)
- awesome-skills first-principles: `https://github.com/awesome-skills/first-principles-skill`
**Key files for this task:**
- Create: `/home/chief/llm-wiki/super-council-docs/skills/first-principles-analysis/SKILL.md`
- Create: `/home/chief/llm-wiki/super-council-docs/skills/first-principles-analysis/references/fpf-patterns.md`
- Create: `/home/chief/llm-wiki/super-council-docs/skills/first-principles-analysis/references/output-template.md`
- Create: `/home/chief/llm-wiki/super-council-docs/skills/first-principles-analysis/examples/council-architecture-review.md`

---

## What This Task Delivers

A first-principles analysis skill that fills the gap identified in research: no existing skill combines **FPF's rigor** (evidence tracing, trust scoring, revisit triggers) with **awesome-skills' practicality** (5-phase process, anti-patterns) and **AWS Well-Architected's dimensions** (6-axis review). The skill must be usable for architecture reviews, system audits, design analysis, and structural evaluation.

---

## Research Findings to Incorporate

### Finding 1: The 5-Phase Process Is Converged

The community has converged on this structure. Use it as-is:

```
Phase 1: Problem Essence     → outcome statement, not solution
Phase 2: Challenge Assumptions → assumption table with verdicts
Phase 3: Ground Truths       → irreducible facts
Phase 4: Reason Upward       → reasoning chain (fact → inference → conclusion)
Phase 5: Validate            → trace back to ground truths, stress test
```

**Source:** awesome-skills/first-principles-skill, FPF B.5 (Canonical Reasoning Cycle)

### Finding 2: "Problem in Outcomes, Not Solutions" Is Gate #1

This is the single most critical pattern. If the problem is solution-locked, everything downstream is tainted.

**Must include in skill:**
- The "So what?" test (FPF E.12 — trace to ground truth)
- JTBD framing: "What job is this system hired to do?"
- Anti-pattern: "We need [tool]" vs "We need [outcome]"
- The complexity/analogy/legacy trap detection from awesome-skills

**Source:** awesome-skills, JTBD framework, HBR problem framing research

**Example from our analysis:**
```
❌ "We need a UnifiedSearchRouter" (solution-locked)
✅ "Agents must query all knowledge sources through a single interface without knowing which backend serves which data" (outcome)
```

### Finding 3: FPF's Trust & Assurance Calculus (F-G-R) Is Missing Everywhere

Every finding in an analysis should be scored on three axes:

| Axis | Question | Scale |
|---|---|---|
| **Formality (F)** | How rigorously is this proven? | F0 (anecdote) → F9 (machine-verified) |
| **ClaimScope (G)** | What does this claim cover? | Narrow (one case) → Broad (all cases) |
| **Reliability (R)** | How confident are we? | R0 (guess) → R3 (evidence-backed) |

**Must include:** A trust scoring section in the output template. Every finding gets an F-G-R score.

**Source:** FPF B.3 (Trust & Assurance Calculus), C.2 (KD-CAL)

### Finding 4: Evidence Decay & Revisit Triggers Are Missing Everywhere

Findings go stale. The skill must include:

- **Evidence TTL:** How long is this finding valid? (e.g., "API version check — valid until next release")
- **Revisit triggers:** What conditions invalidate this finding? (e.g., "If team grows to 25+, reconsider monolith decision")
- **Epistemic debt tracking:** Which findings need re-verification?

**Source:** FPF B.3.4 (Evidence Decay & Epistemic Debt)

### Finding 5: 6-Axis Architecture Review Is the Standard

The AWS Well-Architected framework has converged as the standard review dimensions:

| Axis | Question | What to Check |
|---|---|---|
| **Scalability** | Can it grow? | Bottlenecks, SPOFs, horizontal vs vertical |
| **Resilience** | What breaks first? | Failure modes, recovery time, data loss risk |
| **Observability** | Can you see what's happening? | Logs, metrics, traces, alerts |
| **Maintainability** | Can someone else work on it? | Documentation, modularity, test coverage |
| **Security** | Is it defensible? | AuthN/Z, encryption, least privilege, threat model |
| **Cost Efficiency** | Does complexity earn its keep? | Complexity tax, operational burden, ROI |

**Must include:** A 6-axis checklist in the output template.

**Source:** AWS Well-Architected Framework, community architecture review checklists

### Finding 6: Cost Estimation for Alternatives Is Rarely Done

The awesome-skills example shows a powerful pattern:

```markdown
## What [Alternative] Would Have Cost

| Investment | Estimate |
|------------|----------|
| [Item 1]   | [Cost]   |
| [Item 2]   | [Cost]   |
| **Total**  | [Sum]    |

**Benefit realized:** [What you'd actually get for the cost]
```

**Must include:** A cost-comparison section that estimates the effort/cost of each alternative approach.

**Source:** awesome-skills/examples/architecture-review.md

### Finding 7: Pre-Mortem Stress Testing Is Missing

The skill must include a "What breaks this?" phase:

```markdown
## Stress Test

| Attack Vector | What Breaks | Severity | Mitigation |
|---|---|---|---|
| [Scenario] | [Component] | [Critical/High/Med/Low] | [Fix] |
```

**Source:** FPF B.3.2 (Evidence & Validation Logic), pre-mortem methodology

### Finding 8: Multi-Method Comparison Is Rare

Instead of picking one solution, the skill should compare at least 2-3 approaches:

```markdown
## Solution Space

| Option | Pros | Cons | Cost | F-G-R Score |
|---|---|---|---|---|
| A | ... | ... | ... | F2-G1-R2 |
| B | ... | ... | ... | F3-G2-R3 |
| C | ... | ... | ... | F1-G1-R1 |

**Recommendation:** [Option] because [reasoning from ground truths]
```

**Source:** FPF G.5 (Multi-Method Dispatcher), C.19 (E/E-LOG)

---

## Skill Structure (Draft Outline)

```markdown
---
name: first-principles-analysis
description: "Systematic first-principles analysis for architecture review, system audit, design evaluation. Decomposes problems to ground truths, challenges assumptions, scores findings with F-G-R trust calculus."
---

# First Principles Analysis

## When to Use
- [conditions from awesome-skills, expanded]

## Core Process (5 Phases)
### Phase 1: Problem Essence
- Outcome statement (NOT solution)
- JTBD framing
- "So what?" test
- Success criteria (measurable)

### Phase 2: Challenge Assumptions
- Assumption table (category, statement, challenge, verdict)
- Red flags ("we've always done it this way", etc.)
- Anti-patterns: complexity trap, analogy trap, legacy trap

### Phase 3: Ground Truths
- Physics/math constraints
- Business invariants
- User needs
- Ground truth test (can this be further decomposed?)

### Phase 4: Reason Upward
- Minimal solution first
- Add only what's necessary
- Challenge each layer
- Multi-method comparison (2-3 options)
- Cost estimation for each option

### Phase 5: Validate
- Trace back to ground truths
- 6-axis architecture review (scalability, resilience, observability, maintainability, security, cost)
- Pre-mortem stress test
- Weak link identification

## Output Template
[Full template with all sections, F-G-R scoring, revisit triggers]

## Trust & Assurance (F-G-R)
[Scoring guide for Formality, ClaimScope, Reliability]

## Evidence Decay & Revisit Triggers
[How to track staleness, when to re-verify]

## First Principles Checklist
[10-item checklist from research]

## Anti-Patterns
[Complexity trap, analogy trap, legacy trap, cargo cult, solution-locking]

## Quick Reference
[One-page cheat sheet]
```

---

## Implementation Steps

### Step 1: Fetch Latest Research Artifacts

```bash
# FPF core patterns
curl -s "https://gist.githubusercontent.com/jtprogru/dbf54077d191d575ace39b6245702be8/raw/" > /tmp/fpf-reference.md

# awesome-skills first-principles
curl -s "https://raw.githubusercontent.com/awesome-skills/first-principles-skill/main/SKILL.md" > /tmp/awesome-fp-skill.md
curl -s "https://raw.githubusercontent.com/awesome-skills/first-principles-skill/main/references/software-examples.md" > /tmp/awesome-fp-examples.md
curl -s "https://raw.githubusercontent.com/awesome-skills/first-principles-skill/main/examples/architecture-review.md" > /tmp/awesome-fp-arch-review.md
```

### Step 2: Draft the Skill Document

Create `/home/chief/llm-wiki/super-council-docs/skills/first-principles-analysis/SKILL.md` following the outline above. Key requirements:

1. **Lead with the outcome-statement gate** — Phase 1 must explicitly test "is this an outcome or a solution?"
2. **Include F-G-R trust scoring** — every finding gets a score
3. **Include revisit triggers** — every conclusion has a TTL and invalidation conditions
4. **Include 6-axis review** — scalability, resilience, observability, maintainability, security, cost
5. **Include cost estimation** — "what would the alternative cost?"
6. **Include pre-mortem** — "what breaks this?"
7. **Include multi-method comparison** — at least 2-3 options scored
8. **Include anti-patterns** — complexity trap, analogy trap, legacy trap, cargo cult, solution-locking

### Step 3: Create Reference Files

- `references/fpf-patterns.md` — Key FPF patterns distilled (F-G-R, evidence decay, revisit triggers, Bitter-Lesson Preference)
- `references/output-template.md` — Full output template with all sections
- `references/aws-well-architected.md` — 6-axis review checklist

### Step 4: Create Example Analysis

- `examples/council-architecture-review.md` — Apply the skill to the Council unified DB analysis. Use the findings from `13-council-core-architecture-analysis.md` as source material. Demonstrate:
  - Outcome-stated problem (not "we need a unified DB")
  - Assumption table with verdicts
  - Ground truths from actual codebase state
  - Reasoning chain with multi-method comparison
  - F-G-R scoring on findings
  - 6-axis review
  - Pre-mortem stress test
  - Revisit triggers

### Step 5: Self-Review Against Checklist

| Check | What to Look For |
|---|---|
| Outcome gate | Does Phase 1 explicitly test outcome vs solution? |
| F-G-R scoring | Is trust scoring integrated into output template? |
| Revisit triggers | Does every conclusion have TTL + invalidation conditions? |
| 6-axis review | Are all 6 dimensions covered? |
| Cost estimation | Is there a "what would alternatives cost?" section? |
| Pre-mortem | Is there a "what breaks this?" section? |
| Multi-method | Does the template require 2-3 option comparison? |
| Anti-patterns | Are all 5 anti-patterns documented? |
| Example quality | Does the example demonstrate every section? |
| Actionability | Could an agent follow this without getting stuck? |

---

## Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `skills/first-principles-analysis/SKILL.md` | Main skill document |
| Create | `skills/first-principles-analysis/references/fpf-patterns.md` | FPF patterns reference |
| Create | `skills/first-principles-analysis/references/output-template.md` | Full output template |
| Create | `skills/first-principles-analysis/references/aws-well-architected.md` | 6-axis checklist |
| Create | `skills/first-principles-analysis/examples/council-architecture-review.md` | Worked example |

---

## Constraints

- **Outcome-first:** Every problem statement must pass the "So what?" test before proceeding
- **No solution-locking:** The skill must prevent jumping to solutions before ground truths are established
- **Evidence-backed:** Every finding must have an F-G-R score
- **Revisit-aware:** Every conclusion must have a TTL and invalidation conditions
- **Multi-method:** At least 2-3 options must be compared, not just one
- **Cost-conscious:** Alternatives must include effort/cost estimates
- **Stress-tested:** Pre-mortem analysis is mandatory, not optional

---

## Caveats & Uncertainty

- **FPF is academic:** The FPF framework is comprehensive but abstract. The skill must distill it to practical, actionable steps without losing rigor.
- **F-G-R scoring is subjective:** Formality, ClaimScope, and Reliability scores will vary by analyst. The skill must provide clear anchors (F0-F9 scale, R0-R3 scale) to reduce variance.
- **Revisit triggers are hard to define:** What invalidates a finding depends on context. The skill must provide templates, not rigid rules.
- **Cost estimation is approximate:** The goal is order-of-magnitude comparison, not precise accounting.
- **6-axis review may be overkill for small systems:** The skill should allow scoping down (e.g., skip security axis for internal tools).

---

## Success Criteria

- [ ] SKILL.md exists with all 5 phases documented
- [ ] Outcome-statement gate is explicit in Phase 1
- [ ] F-G-R trust scoring is integrated into output template
- [ ] Revisit triggers and evidence decay are documented
- [ ] 6-axis architecture review checklist is included
- [ ] Cost estimation section is included
- [ ] Pre-mortem stress test section is included
- [ ] Multi-method comparison is required (2-3 options)
- [ ] All 5 anti-patterns are documented with examples
- [ ] Worked example demonstrates every section
- [ ] Self-review checklist passes all 10 items
- [ ] Skill is actionable — an agent could follow it without getting stuck
- [ ] Skill is scoped to one session (~60 min of tool calls to execute)

---

## Notes for Executor

1. **Read the research sources first** — FPF gist, awesome-skills SKILL.md, and examples. Don't start from scratch; synthesize.
2. **The Council analysis is your test case** — `13-council-core-architecture-analysis.md` has real findings that can be re-cast using the new skill format. Use it to validate that the skill works.
3. **Keep it practical** — FPF is 300+ pages of academic framework. Distill to what's actionable. If a pattern doesn't have a concrete step, skip it.
4. **The output template is the most important part** — this is what agents will actually use. Make it copy-paste-ready with clear placeholders.
5. **The example is second most important** — it demonstrates the skill in action. Make it thorough.
