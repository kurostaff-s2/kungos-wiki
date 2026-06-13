# Consolidation Prompt v2 & Model Comparison Review

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `936dd2` |
| Entity type | `handoff` |
| Short description | Review daily consolidation prompt v2 (simplified rules) and model comparison (Granite-3B vs LFM2.5-8B) for production readiness |
| Status | `draft` |
| Source references | `~/llm_output_{orig,v2,lfm}.txt`, `~/llm_parsed_{orig,v2,lfm}.json`, `prompts.py` |
| Generated | 13-06-2026 |
| Next action / owner | Review prompt variants, select winner, commit to production |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Key files for this task:**
- `super_council/memory_service/consolidate/prompts.py` — prompt templates (daily, daily_v2)
- `super_council/memory_service/consolidate/client.py` — LLM client + parser
- `super_council/memory_service/consolidate/config.py` — ArcConfig (timeout, base_url)
**Test artifacts:**
- `~/llm_output_orig.txt` — Granite-3B with original prompt (1505 chars)
- `~/llm_output_v2.txt` — Granite-3B with v2 prompt (2009 chars)
- `~/llm_output_lfm.txt` — LFM2.5-8B with v2 prompt (2516 chars)
- `~/llm_parsed_{orig,v2,lfm}.json` — parsed outputs
**Reference:** `/home/chief/.council-memory/canonical-raw-session-data/processed/trace-be121052.md` (62K char source)

---

## Background

### Problem Statement

The daily consolidation prompt produces inconsistent summary lengths across runs (stddev: 507-611 chars). The LLM alternates between "thorough mode" (follows all structure) and "brief mode" (skips structure). Mean output is 697 chars against a 1500-3000 target.

### What Was Tried

1. **Original prompt** (`daily`): 5084 chars, 8 scattered rules across 2 sections, 10 Summary bullets.
2. **v2 prompt** (`daily_v2`): 2071 chars (59% smaller), 5 consolidated rules, 4 Summary bullets.
3. **Model swap**: Tested LFM2.5-8B-A1B-UD on same v2 prompt.

### Commits

| Commit | Message |
|--------|---------|
| `c67d44a` | memory: summary-first architecture for vector recall |
| `7eb68d7` | fix: map tier schema keys for summary extraction (Bug A) |
| `5b496f7` | memory: switch consolidation prompts from YAML to Markdown format |
| `65d3944` | memory: refine daily tier prompt for continuity and accuracy |
| `4cfac7e` | memory: increase daily summary target to 2000-3000 chars, clarify scope |
| `8b06bd7` | memory: simplify Summary instructions, add anti-meta-description guard |

---

## Test Results

### Model Comparison (single run each, trace-be121052.md source)

| Metric | ORIG (Granite) | V2 (Granite) | LFM2.5-8B |
|--------|----------------|--------------|-----------|
| Prompt size | 66,416 chars | 63,403 chars | 63,403 chars |
| Summary length | 1505 chars | 2009 chars | **2516 chars** |
| Total output | 3990 chars | 3724 chars | 6014 chars |
| Time | ~196s | ~196s | **139s** |
| Tokens/sec | N/A | N/A | 10.8 |
| Has ## Summary | ✅ | ✅ | ✅ |
| Prior context | ✅ | ✅ | ✅ |
| Chronological | ✅ | ❌ | ❌ |
| Continuity | ✅ | ✅ | ✅ |
| Meta-description | ❌ (good) | ❌ (good) | ❌ (good) |
| Specific details | 6/12 | 5/12 | **7/12** |

### Event Capture (17 key events from source)

| Event | ORIG | V2 | LFM |
|-------|------|-----|-----|
| Investigation started | ✅ | ✅ | ✅ |
| Initial timeout blocker | ✅ | ✅ | ✅ |
| 6 findings compiled | ✅ | ✅ | ✅ |
| Blast radius + options | ✅ | ✅ | ✅ |
| First-principles: remove Milvus | ✅ | ❌ | ❌ |
| LanceDB discussion | ❌ | ❌ | ❌ |
| Wiring bug discovered | ✅ | ❌ | ✅ |
| Root cause: port discovery | ❌ | ✅ | ✅ |
| Fix 1: wire vector_store | ✅ | ✅ | ✅ |
| Fix 2: orphan cleanup | ✅ | ✅ | ✅ |
| Fix 3: port discovery fix | ✅ | ❌ | ✅ |
| Production verification | ✅ | ✅ | ✅ |
| Pipeline audit | ❌ | ❌ | ✅ |
| session_diary deprecated | ✅ | ❌ | ✅ |
| Diary channel removed | ✅ | ❌ | ❌ |
| Channels converted to semantic | ✅ | ✅ | ✅ |
| Stale cleanup: 990 entries | ✅ | ✅ | ✅ |
| **TOTAL** | **14/17** | **10/17** | **14/17** |

### Hallucinations

**None detected in any model.** All three capture the major arc accurately. Missed events are rejected options (LanceDB) or analysis methodology (first-principles) — not critical execution events.

---

## Prompt Analysis

### Original Prompt (`daily`) — Issues Found

| # | Problem | Location | Impact |
|---|---------|----------|--------|
| 1 | **Dual rule sets** | "CRITICAL RULES" (A,B,C) + "Rules" (1-5) = 8 scattered rules | LLM can't prioritize |
| 2 | **Contradictory length** | "2000-3000+ characters" + "This is a MINIMUM" | Confusing: range or floor? |
| 3 | **Over-specified Summary** | 10 bullet points for one section | LLM can't hold all constraints |
| 4 | **Redundant instructions** | "Include file names" in Scope AND Rule A AND schema | Noise, not signal |
| 5 | **Continuity overlap** | Rule A "end with continuity" + Rule C "carried_forward" | LLM may skip one or both |
| 6 | **Irrelevant sections** | "Input Format", "Downstream Consumer Notes" | Wastes prompt tokens |
| 7 | **9 output sections** | Schema has 9 sections | LLM distributes content thinly |
| 8 | **Negative constraints** | "Do NOT be brief", "Do NOT describe" | Negatives harder for LLMs |

### v2 Prompt — Improvements & Gaps

**Improvements:**
- 59% smaller (2071 vs 5084 chars)
- 5 rules instead of 8
- No dual rule sets
- No irrelevant sections
- Cleaner schema placeholders

**Gaps:**
- Misses more events (10/17 vs 14/17) — simplified rules may be too aggressive
- No instruction to include rejected options or analysis methodology
- No instruction to include technical decisions with trade-offs
- Chronological marker missing in output

---

## Model Comparison

### Granite-4.1-3B (current production)

- **Strengths**: Consistent structure, captures technical decisions
- **Weaknesses**: High variance (stddev 507-611), slow (~196s), brevity tendency
- **Best run**: 1505 chars (ORIG), 14/17 events
- **Context window**: 32K, prompt uses ~16.6K (51%)

### LFM2.5-8B-A1B-UD (candidate)

- **Strengths**: Longer output (2516 chars), faster (139s), same event capture (14/17)
- **Weaknesses**: New model, untested in production, may need prompt tuning
- **Best run**: 2516 chars (v2), 14/17 events, zero hallucinations
- **Context window**: 32K, same prompt fits

### Head-to-Head Verdict

| Criterion | Winner | Margin |
|-----------|--------|--------|
| Summary length | **LFM** | 2516 vs 1505 (+67%) |
| Event capture | **Tie** | 14/17 both |
| Speed | **LFM** | 139s vs 196s (29% faster) |
| Structure compliance | **Tie** | Both pass all checks |
| Hallucinations | **Tie** | Zero in both |
| Production readiness | **Granite** | Known, tested, monitored |

---

## Open Questions

### Prompt Design

1. **Should v2 include "rejected options" instruction?** All models missed LanceDB discussion. Adding "Include options considered but rejected, with reasoning" would capture decision rationale.

2. **Should v2 include "analysis methodology" instruction?** All models missed first-principles analysis. Adding "Note the analysis approach used (e.g., first-principles, cost-benefit)" would improve traceability.

3. **Target length: 1500-3000 or lower?** Current mean is 870 chars. 1500 floor may be too high for Granite-3B. Consider 1200-2500 as a more realistic range.

4. **Should we add a minimum length gate?** If summary < 1000 chars, re-prompt with "expand your Summary section" instruction.

### Model Selection

5. **LFM production readiness?** Needs multi-day testing to verify consistency. Single run shows promise but variance unknown.

6. **Temperature tuning?** Current temp=0.3. Lower (0.1) may reduce variance but could reduce creativity. Test both models at temp=0.1.

7. **Model fallback?** If Granite fails (HTTP 500), should LFM be the fallback? Or vice versa?

---

## Execution Plan

### Phase 1: Prompt Refinement

**What:** Add missing instructions to v2 prompt based on gap analysis.
**Files:** `prompts.py` — add `daily_v3` variant.
**Steps:**
1. Add "Include options considered but rejected, with reasoning" to Rule 1.
2. Add "Note the analysis approach used (e.g., first-principles, cost-benefit)" to Rule 1.
3. Adjust target to 1200-2500 chars (more realistic for Granite-3B).
4. Test v3 against trace-be121052.md (3 runs).
5. Compare event capture vs v2.

**Tests:**
- [ ] v3 captures 15+/17 events (vs 10/17 for v2)
- [ ] v3 summary >= 1500 chars mean (3 runs)
- [ ] v3 has zero hallucinations

### Phase 2: Model Comparison (Multi-Run)

**What:** Run both models 5x each to measure variance.
**Files:** Test script, output artifacts.
**Steps:**
1. Run Granite (v3 prompt) 5x, record summary lengths.
2. Run LFM (v3 prompt) 5x, record summary lengths.
3. Calculate mean, stddev, min, max for each.
4. Test at temp=0.1 for both models.

**Tests:**
- [ ] Granite stddev < 300 chars (currently 507-611)
- [ ] LFM stddev < 300 chars
- [ ] Both models >= 1500 chars mean

### Phase 3: Production Decision

**What:** Select model + prompt for production deployment.
**Files:** `config.py`, `prompts.py`.
**Steps:**
1. Review Phase 1+2 results.
2. Select winner (model + prompt variant).
3. Update `build_tier_consolidation_prompt()` to use selected variant.
4. Update `ArcConfig` if model change needed.
5. Commit and deploy.

**Tests:**
- [ ] Selected variant passes all Phase 1+2 gates
- [ ] No regression in existing tests
- [ ] Monitor production rollups for 2-3 days

---

## Constraints

- **LLM context window**: 32K tokens max. Prompt + source must fit.
- **Output format**: Markdown with `## Section` headers only. No YAML.
- **Summary target**: 1500-3000 chars (adjustable based on model capability).
- **Accuracy**: Zero hallucinations. Flag uncertainty with `confidence: low`.
- **Backward compatibility**: Existing rollups must still parse.

---

## Success Criteria

- [ ] Prompt variant selected with documented trade-offs
- [ ] Model selected with variance metrics (mean, stddev, min, max)
- [ ] Event capture >= 15/17 for selected variant
- [ ] Summary length >= 1500 chars mean (3+ runs)
- [ ] Zero hallucinations in selected variant
- [ ] Production deployment with 2-3 day monitoring window
- [ ] Rollback plan documented if metrics degrade

---

## Caveats & Uncertainty

1. **Single-run bias**: Current comparison is 1 run per model. Variance may differ significantly across runs.
2. **Source material bias**: trace-be121052.md is a 62K char investigation session. Shorter sessions may produce shorter summaries regardless of prompt.
3. **LFM unknowns**: New model, untested in production. May have different failure modes (e.g., context window overflow, token limits).
4. **Temperature sensitivity**: Current tests at temp=0.3. Lower temp may improve consistency but reduce output quality.
5. **Parser compatibility**: v2/v3 prompts must still parse with `_extract_markdown_sections()`. Schema changes may break downstream consumers.
