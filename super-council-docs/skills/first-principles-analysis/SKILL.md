---
name: first-principles-analysis
description: "Systematic first-principles analysis for architecture review, design evaluation, and assumption challenging. Decomposes problems to ground truths, builds solutions upward, stress-tests conclusions. Use when evaluating whether an approach is truly optimal, questioning inherited assumptions, or making foundational decisions with long-term impact."
---

# First Principles Analysis

> Decompose complex problems into irreducible facts. Build solutions upward. Challenge every assumption.

## When to Use

- Evaluating whether an architecture or design is truly optimal
- Questioning "best practices" that may not fit the current context
- Breaking through when conventional solutions feel inadequate
- Making foundational decisions with long-term impact
- Challenging inherited assumptions in legacy systems
- Designing new systems without cargo-culting existing patterns

## Core Process (5 Phases)

### Phase 1: Problem Essence

Strip away implementation details to find the core problem.

1. **State the problem as an outcome, not a solution**
   - ❌ "We need a unified database" (solution-locked)
   - ✅ "Knowledge must survive across sessions and be retrievable by meaning" (outcome)

2. **Apply the "So What?" test** — trace to ground truth:
   ```
   Problem: "We need a unified database"
   So what? → "So agents can share state"
   So what? → "So knowledge persists across sessions"
   So what? → "So agents don't repeat work"
   ← GROUND TRUTH: Save time through knowledge persistence
   ```

3. **JTBD framing:** "What job is this system hired to do?"

4. **Define success criteria** — measurable outcomes, not features.

**Gate:** If the problem is stated as a solution, **stop and reframe**. Everything downstream is tainted if the problem is solution-locked.

---

### Phase 2: Challenge Assumptions

Identify and question every assumption — explicit and implicit.

**Assumption table:**

| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| "We need X because Y" | Technical | What problem was X actually solving? | Keep / Discard / Investigate |

**Assumption categories:**

| Category | Question to Ask |
|----------|----------------|
| Technical | "Must we use this technology or pattern?" |
| Business | "Is this requirement actually fixed?" |
| Resource | "Are these constraints real or perceived?" |
| Historical | "Why was this decision made originally? Do conditions still hold?" |

**Red flags (likely false assumptions):**

- "We've always done it this way"
- "Industry standard says..."
- "Everyone uses X for this"
- "That's too simple to work"

**Three traps to watch for:**

1. **Complexity trap** — solution is more complex than the problem warrants. Test: remove one component. Does the system still solve the core problem? If yes, that component wasn't essential. Repeat.

2. **Analogy trap** — "Company X does it this way, so should we." Test: what problem was Company X actually solving? Is our problem identical in all relevant dimensions? What constraints did they have that we don't?

3. **Legacy trap** — maintaining compatibility with decisions that no longer serve. Test: what was the original reason? Do those conditions still exist? What's the true cost of change vs. cost of maintaining?

---

### Phase 3: Ground Truths

Identify the irreducible facts — the bedrock everything else builds on.

**Categories:**

- **Physics/math constraints** — what cannot be violated? (latency budgets, storage limits, team size)
- **Business invariants** — what must remain true? (compliance, SLAs, data retention)
- **User needs** — what does the user fundamentally require? (independent of implementation)

**Ground truth test (apply to each candidate):**

- Can this be further decomposed? If yes, it's not a ground truth.
- Is this provably true, not just commonly believed?
- Would violating this definitely cause failure?

---

### Phase 4: Reason Upward

Build solutions from ground truths. Each layer must justify itself.

```
Ground Truth → Minimal Solution → Justified Additions → Final Design
     ↑              ↑                    ↑
  (proven)     (sufficient)        (each defended)
```

1. **Start minimal** — what's the simplest thing that satisfies ground truths?

2. **Add only what's necessary** — each addition must justify itself against a ground truth.

3. **Challenge each layer** — "Does this layer earn its complexity?"

4. **Compare alternatives (when the solution space isn't clear):**

   | Option | Pros | Cons | Cost | Confidence |
   |--------|------|------|------|------------|
   | A | ... | ... | ~X hrs | High/Med/Low |

   Only compare when ground truths point to multiple valid paths. If one path is clear, document why and move on.

5. **Cost awareness** — note the order-of-magnitude cost of alternatives:
   ```
   Alternative cost: ~X engineer-hours (setup: Y, maintenance: Z%/month)
   Benefit realized: [What you'd actually get for the cost]
   ```

---

### Phase 5: Validate

Ensure the reasoning chain is sound and conclusions won't go stale.

1. **Trace back to ground truths** — every design decision must link to a ground truth. If a decision can't be traced, it's an assumption dressed as a conclusion.

2. **Stress test** — "What breaks this?" Identify 2-3 failure scenarios:
   ```
   1. If [condition changes]: [what breaks, how it fails]
   2. If [scale increases]: [what breaks, how it fails]
   3. If [dependency fails]: [what breaks, how it fails]
   ```

3. **Revisit triggers** — every conclusion has an expiration. Define invalidation conditions:
   ```
   Revisit when:
   - Team size exceeds N
   - Traffic pattern diverges significantly
   - [Domain-specific condition]
   ```

---

## Output Template

```markdown
## First Principles Analysis: [Topic]

### 1. Problem Essence
**Core problem:** [One sentence — outcome, not solution]
**So what? chain:** [Trace to ground truth]
**Success criteria:** [Measurable outcomes]

### 2. Assumptions Challenged
| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|

### 3. Ground Truths
1. [Irreducible fact — provably true, not decomposable]
2. [Irreducible fact]
3. [Irreducible fact]

### 4. Reasoning Chain
Ground Truth → [Inference] → [Inference] → Solution

### 5. Conclusion
**Recommended approach:** [Description]
**Key insight:** [What the analysis revealed]
**Trade-offs acknowledged:** [What we're accepting]
**Confidence:** High / Medium / Low — [based on what evidence]
**Revisit when:** [Invalidation conditions]

### Stress Test
1. If [scenario]: [what breaks]
2. If [scenario]: [what breaks]

### Alternative Cost
**[Alternative]:** ~X engineer-hours — [benefit realized]
```

---

## Quick Reference Checklist

- [ ] Problem stated as outcome, not solution (passes "So what?" test)
- [ ] All assumptions explicitly listed and categorized
- [ ] Each assumption challenged with a specific question
- [ ] Ground truths are irreducible (can't be decomposed further)
- [ ] Solution built upward from ground truths, not downward from conventions
- [ ] Every design decision traceable to a ground truth
- [ ] Stress test identifies 2-3 failure scenarios
- [ ] Revisit triggers defined for key conclusions

---

## Brief Example: Microservices Review

**Context:** B2B SaaS, 12 engineers, CTO proposes microservices because "Netflix does it."

### 1. Problem Essence
**Core problem:** Enable faster development velocity and independent scaling
**So what? chain:** "We need microservices" → so teams deploy independently → so features ship faster → so we respond to customers quickly
**GROUND TRUTH:** Ship features faster to respond to customers

### 2. Assumptions Challenged
| Assumption | Category | Challenge | Verdict |
|------------|----------|-----------|---------|
| Netflix uses microservices, so should we | Analogy | Netflix has 2000+ engineers. We have 12. | Discard |
| Need independent deployability | Technical | Deploy conflicts: 2/month (not a pain point) | Investigate |
| Services need independent scaling | Technical | All components scale together, no hot spots | Discard |

### 3. Ground Truths
1. Team size is 12 engineers across 2 teams — both touch most features
2. Traffic is uniform — no component needs independent scaling
3. Deployment frequency is 10x/week — currently works fine
4. Engineers spend 30% time on infrastructure — already a high burden

### 4. Reasoning Chain
```
GT: Team size is 12
  → Microservices coordination overhead > benefit at this scale
GT: Traffic is uniform
  → Independent scaling benefit is zero
GT: 30% time on infrastructure
  → Microservices would push this to 50%+
Conclusion: Modular monolith now, extract services later if needed
```

### 5. Conclusion
**Recommended approach:** Modular monolith with clear internal boundaries
**Key insight:** Desire for microservices was analogy-driven (Netflix), not pain-driven. Real problems (deploy conflicts, scaling) don't exist yet.
**Trade-offs:** Less "modern" architecture; will need to refactor if scaling patterns change
**Confidence:** High — based on current metrics and team structure
**Revisit when:** Team exceeds 25 engineers, or component traffic diverges significantly

### Stress Test
1. If team grows to 50: module boundaries become service boundaries; extraction is planned
2. If one module gets 10x traffic: modular boundaries enable clean extraction
3. If two teams need different tech stacks: module isolation enables per-module language choice

### Alternative Cost
**Microservices now:** ~6.5 engineer-months setup + 20% ongoing tax — benefit realized: near zero (problems don't exist yet)

---

## Boundaries

**Will:**
- Challenge assumptions systematically
- Identify ground truths from first principles
- Build reasoning chains from fundamentals
- Reveal when conventional wisdom doesn't apply
- Define revisit triggers so conclusions don't go stale

**Will Not:**
- Dismiss all existing solutions as wrong
- Spend unlimited time on every decision (reserve for important choices)
- Ignore practical constraints in favor of theoretical purity
- Guarantee the "best" solution (reveals better reasoning, not perfect answers)
- Replace architecture review (use a dedicated skill for 6-axis review)
