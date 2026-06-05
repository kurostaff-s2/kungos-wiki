# Arc Consolidation Pipeline — Improvement Plan

**Source spec:** Consolidation analysis from 2026-06-06 session (this handoff)
**Generated:** 06-06-2026
**Goal:** Restructure the tiered consolidation pipeline so each tier produces durable, carry-forward state rather than narrative summaries that collapse under compression.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/arc_summarizer/`
**Key files for this task:**
- `prompts.py` — Tier-specific prompt templates (TIER_PROMPT_TEMPLATES dict)
- `pipeline.py` — ArcPipeline class, `_gather_tier_input()`, `_write_tier_output()`, TIER_CONFIGS
- `client.py` — ArcClient, `consolidate_tiered()` method
- `scheduler.py` — IdleWindowScheduler (no changes expected)
**Reference docs:** `/home/chief/llm-wiki/super-council-docs/08-arc-summarizer.md`
**Related codebases:** None (self-contained within arc_summarizer module)

---

## Current State (Baseline)

### How it works today

Four consolidation tiers run in pyramid order (daily → short → weekly → bimonthly). Each tier reads entries from `memory_entries` or `memory_rollups`, sends them to Granite-4.1-3B on `:18095`, and writes structured YAML output back to `memory_entries` as `entry_type='diary'`.

| Tier | Window | Max Input | Source | TTL |
|---|---|---|---|---|
| daily | 1 day | 30,000 chars | raw/diary entries | 7d |
| short | 3 days | 20,000 chars | daily outputs | 14d |
| weekly | 7 days | 15,000 chars | short outputs | 30d |
| bimonthly | 15 days | 10,000 chars | weekly outputs | 60d |

### Known failure modes (from actual output)

- **Bimonthly produces empty output** — 4 levels of compression with 10K char budget leaves no signal.
- **Short tier lost context** — 3 days of daily summaries compressed to one open item (190 chars).
- **No carry-forward mechanism** — Open items from daily get absorbed into short narrative, then disappear by weekly.
- **Input is undifferentiated text dumps** — Each entry is `--- Entry: id (date) --- Title: ... Body: ...` with no signals or structure. The model has to parse messy text to find decisions, errors, and files.

### Consumption paths

1. **Tier 1 knowledge card** → prepended into every upstream LLM system prompt. This is the *only* path where consolidation output actively influences agent behavior.
2. **Higher-tier input** — Each tier's output feeds the tier above.
3. **`recall.unified()`** — Text-channel recall searches `memory_entries` body text.

---

## Formalized Tier Contract

Every tier follows this contract:

1. **Daily** reads raw/diary entries **plus** prior daily `carry_forward`.
2. **Short** reads daily outputs **plus** prior short `carried_forward`.
3. **Weekly** reads short outputs **plus** prior weekly unresolved risks/priorities.
4. **Bimonthly** reads weekly outputs **plus** prior strategic continuity notes.
5. **Every output** contains: summary/narrative, structured fields, and `carry_forward`.
6. **No tier above daily** should ever read raw entries directly.

This implements the **same-tier carry-forward injection** pattern: when generating today's daily summary, include yesterday's `carry_forward` items so the model knows what must survive compression. When generating a short summary, include the prior short's `carried_forward`. Continuity is improved by selectively re-injecting unresolved state instead of relying only on the current retrieval window.

---

## Open Decisions

### OD-1: Bimonthly tier viability

**Issue:** Bimonthly currently produces empty output. Even with improved prompts and carry-forward injection, 4 levels of compression with a 10K char budget may not yield useful strategic summaries.

**Options:**
- **A:** Keep bimonthly with carry-forward injection. The strategic continuity notes from prior runs give the model explicit state to preserve, which may produce non-empty output.
- **B:** Drop bimonthly entirely. Give weekly a 15K budget and make it the top tier. Simpler pyramid, less cascade failure.
- **C:** Keep bimonthly but change its input source to read *both* weekly outputs AND the prior bimonthly continuity notes (not just weekly). This gives it more signal.

**Recommendation:** A — implement carry-forward first, measure output quality, then decide. If bimonthly still produces empty output after carry-forward injection, drop it.

### OD-2: Carry-forward persistence mechanism

**Issue:** Where does the carry-forward state live? It needs to be queryable by the next same-tier run.

**Options:**
- **A:** Store as a dedicated field in `memory_entries` (add `carry_forward` JSON column). `_gather_tier_input()` queries for the latest entry with the same tier and extracts the `carry_forward` field.
- **B:** Store as a separate `tier_carry_forward` table (tier_id → JSON blob). Simpler query, no schema migration on memory_entries.
- **C:** Embed carry-forward directly in the tier's output body (as YAML field). `_gather_tier_input()` parses the body YAML to extract it.

**Recommendation:** A — keeps everything in one table, consistent with the existing `memory_entries` pattern. Requires adding a `carry_forward` column (TEXT, nullable, default NULL).

### OD-3: Structured input blocks — scope

**Issue:** The proposed `[ENTRY]` structured blocks (id, timestamp, entry_type, project, artifacts, signals) improve model parsing but add implementation cost.

**Options:**
- **A:** Full structured blocks for daily tier only. Higher tiers already read YAML from lower tiers, so they don't need it.
- **B:** Structured blocks for all tiers. Consistent format, but redundant for short/weekly/bimonthly.
- **C:** Skip structured blocks entirely. Implement carry-forward and synthesis instructions first (higher ROI), defer structured input.

**Recommendation:** A — daily tier is the only one that reads raw text. Structured blocks there improve the entire pyramid's input quality.

---

## Phases

### Phase 1: Schema — Add `carry_forward` field to memory_entries

**What:** Add a `carry_forward` TEXT column to `memory_entries` for storing JSON carry-forward state between same-tier runs.

**Files:**
- Create: `super_council/migrations_pg/00N_add_carry_forward.sql` (migration)
- Modify: `super_council/memory_service/store.py` — `query_memory_entries()` returns `carry_forward`; `upsert_memory_entry()` accepts `carry_forward` parameter

**Steps:**
1. Create SQLite migration to add `carry_forward TEXT DEFAULT NULL` to `memory_entries`.
2. Update `query_memory_entries()` to include `carry_forward` in SELECT.
3. Update `upsert_memory_entry()` to accept and write `carry_forward`.
4. Run migration against `~/.council-memory/council_core.db`.

**Tests:**
- Insert entry with `carry_forward` → query returns it.
- Insert entry without `carry_forward` → query returns NULL.
- Existing rows unaffected.

**Dependencies:** None.

---

### Phase 2: Prompt — Restructure all four tier prompts

**What:** Rewrite `TIER_PROMPT_TEMPLATES` in `prompts.py` to implement the formalized contract: schema-first, synthesis instructions, carry-forward injection, and explicit output schema with `carry_forward` field.

**Files:**
- Modify: `super_council/arc_summarizer/prompts.py` — `TIER_PROMPT_TEMPLATES` dict (4 entries)

**Steps:**
1. **Daily prompt** — Add `carry_forward` and `key_errors` to output schema. Add instruction: "Do not restate input. Extract only durable state." Add `carry_forward` field: items that must remain visible tomorrow.
2. **Short prompt** — Add synthesis instruction: "Do not list each input separately. Synthesize patterns across the whole window." Add `carried_forward` field (items persisting from prior short run + newly emerged). Distinguish `carried_forward` from `new_open_items`.
3. **Weekly prompt** — Add synthesis instruction. Replace thin `theme` with `next_week_focus` and `priority_shifts`. Add `persistent_risks` field.
4. **Bimonthly prompt** — Add synthesis instruction. Add `strategic_continuity` field. Keep `course_corrections` and `knowledge_base`.
5. Every prompt must accept a `{carry_forward_context}` placeholder that the pipeline injects from the prior same-tier run.

**Daily output schema (example):**
```yaml
summary: <concise overview>
decisions:
  - what: <decision>
    context: <why/where>
    confidence: high|medium|low
work_completed:
  - <task>
open_items:
  - <unresolved item>
key_files:
  - <path>
key_functions:
  - <name>
key_errors:
  - <error or failure>
carry_forward:
  - <item that must remain visible tomorrow>
```

**Short output schema:**
```yaml
narrative: <coherent multi-day work story>
work_threads:
  - name: <string>
    status: active|blocked|completed
    progress: <what happened across the window>
    blockers: [<string>]
carried_forward:
  - <item persisting from prior period>
new_open_items:
  - <newly emerged item>
```

**Weekly output schema:**
```yaml
theme: <dominant theme of the week>
completed_milestones:
  - name: <string>
    significance: <why it matters>
active_projects:
  - name: <string>
    phase: <string>
    velocity: ahead|on_track|behind
lessons_learned:
  - lesson: <string>
    context: <string>
next_week_focus:
  - <priority for next period>
persistent_risks:
  - <recurring or long-lived risk>
```

**Bimonthly output schema:**
```yaml
executive_summary: <high-level overview>
major_achievements:
  - achievement: <string>
    impact: <downstream effect>
course_corrections:
  - original_direction: <string>
    correction: <string>
    reason: <string>
knowledge_base:
  - topic: <string>
    insight: <string>
strategic_continuity:
  - <note for next period>
```

**Tests:**
- `build_tier_consolidation_prompt()` produces valid prompt for each tier.
- Prompt contains `{carry_forward_context}` placeholder.
- Prompt contains synthesis instruction for non-daily tiers.

**Dependencies:** None (can run in parallel with Phase 1).

---

### Phase 3: Pipeline — Implement carry-forward injection in `_gather_tier_input()`

**What:** Modify `_gather_tier_input()` in `pipeline.py` to query the latest same-tier entry, extract its `carry_forward` field, and inject it into the prompt.

**Files:**
- Modify: `super_council/arc_summarizer/pipeline.py` — `_gather_tier_input()` method
- Modify: `super_council/arc_summarizer/client.py` — `consolidate_tiered()` to accept and pass carry_forward context

**Steps:**
1. In `_gather_tier_input()`, after gathering normal input entries, query `memory_entries` for the latest entry with the same `tier` value and non-NULL `carry_forward`.
2. Format the carry-forward context as a structured block:
   ```
   ## Prior Carry-Forward (from last {tier_id} run)
   - item1
   - item2
   ```
3. Append this block to the input material BEFORE the `{input_material}` placeholder in the prompt.
4. Update `build_tier_consolidation_prompt()` in `prompts.py` to accept a `carry_forward_context` parameter and inject it into the prompt template.
5. In `_write_tier_output()`, parse the model's YAML response to extract the `carry_forward` field and store it in the `carry_forward` column of `memory_entries`.

**Tests:**
- `_gather_tier_input('daily')` includes carry-forward block when prior entry exists.
- `_gather_tier_input('daily')` works without carry-forward when no prior entry exists.
- `_write_tier_output()` stores `carry_forward` in DB.
- Full pipeline: run daily tier twice → second run includes first run's carry_forward.

**Dependencies:** Phase 1 (schema), Phase 2 (prompts).

---

### Phase 4: Pipeline — Implement structured input blocks for daily tier

**What:** Modify the daily tier's input gathering to wrap each entry in a structured `[ENTRY]` block with id, timestamp, entry_type, project, artifacts, and signals.

**Files:**
- Modify: `super_council/arc_summarizer/pipeline.py` — `_gather_tier_input()` for `input_source == "raw"`

**Steps:**
1. When `tier_id == 'daily'` and `input_source == 'raw'`, format each entry as:
   ```
   [ENTRY]
   id: {entry_id}
   timestamp: {created_at}
   entry_type: {entry_type}
   project: {project_id or "unknown"}
   title: {title}
   body:
   {body text}
   [/ENTRY]
   ```
2. Derive `signals` from body content (heuristic): `decision=true` if "decided" or "chosen" appears; `task_done=true` if "completed" or "done" appears; `error=true` if "error" or "failed" or "crash" appears.
3. Extract `artifacts` from body (heuristic): file paths matching `*/` patterns.
4. Keep the existing truncation logic (4000 chars per entry body, max_chars total).

**Tests:**
- Daily input contains `[ENTRY]` blocks with all fields.
- Signals are derived correctly from body text.
- Non-daily tiers unaffected (still read YAML from lower tiers).

**Dependencies:** Phase 1 (schema for project_id access).

---

### Phase 5: Tests — Full pipeline integration

**What:** End-to-end tests that verify the carry-forward cycle works across tier runs.

**Files:**
- Modify: `super_council/tests/test_tiered_consolidation.py` (existing)
- Create: `super_council/tests/test_carry_forward_injection.py`

**Steps:**
1. **Test carry-forward round-trip:** Seed a daily entry with `carry_forward: ["item-A"]` → run `_gather_tier_input('daily')` → assert carry-forward block appears in output.
2. **Test tier isolation:** Assert short tier does NOT read raw entries. Assert weekly tier does NOT read short entries directly (reads rollups).
3. **Test synthesis instruction presence:** Assert short/weekly/bimonthly prompts contain "Do not list each input separately."
4. **Test empty input handling:** No prior carry-forward → prompt works without it.
5. **Test truncation:** Entries over 4000 chars are truncated with "...(truncated)".
6. **Test full cascade:** Seed daily → run daily → seed short input from daily output → run short → verify carried_forward populated.

**Dependencies:** Phases 1-4.

---

### Phase 6: Production Wiring — Deploy and verify

**What:** Restart memory service, trigger a test consolidation cycle, verify carry-forward state persists.

**Steps:**
1. Run migration against `~/.council-memory/council_core.db`.
2. Restart `memory-service.service` via `systemctl --user restart memory-service`.
3. Verify service starts cleanly (check journalctl for IdleWindowScheduler init).
4. Force-trigger a daily consolidation cycle (via HTTP endpoint or direct Arc call).
5. Verify output contains `carry_forward` field.
6. Verify `carry_forward` stored in `memory_entries` DB.
7. Force-trigger a second daily cycle → verify carry-forward from first run is injected into second run's prompt.
8. Check journalctl logs for any errors.

**Post-Wiring Tests (GATE):**
- [ ] Memory service starts without errors
- [ ] Arc server responds to consolidation request
- [ ] Daily output contains `carry_forward` field
- [ ] `carry_forward` persisted in `memory_entries.carry_forward` column
- [ ] Second daily run includes prior carry-forward in prompt
- [ ] Short/weekly prompts contain synthesis instructions
- [ ] All existing tests pass (no regression)
- [ ] Bimonthly output is non-empty (or documented as OD-1 pending)

**Dependencies:** Phases 1-5.

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `super_council/migrations_pg/00N_add_carry_forward.sql` | Add `carry_forward` column |
| Modify | `super_council/arc_summarizer/prompts.py` | Restructure all 4 tier prompts |
| Modify | `super_council/arc_summarizer/pipeline.py` | Carry-forward injection, structured input |
| Modify | `super_council/arc_summarizer/client.py` | Pass carry_forward to consolidate_tiered |
| Modify | `super_council/memory_service/store.py` | Query/write `carry_forward` |
| Create | `super_council/tests/test_carry_forward_injection.py` | Integration tests |
| Modify | `super_council/tests/test_tiered_consolidation.py` | Update existing tests |

---

## Constraints

- **No tier above daily reads raw entries.** The pyramid contract is strict.
- **Carry-forward is optional.** If no prior entry exists, the prompt works without it.
- **Backward compatible.** Existing entries without `carry_forward` are unaffected.
- **No schema changes to `memory_rollups`.** Carry-forward lives only in `memory_entries`.
- **Prompt templates must remain valid Python f-strings.** No breaking the `TIER_PROMPT_TEMPLATES` dict structure.
- **Granite-4.1-3B is the model.** Prompts must be compatible with its instruction-following capabilities (strict YAML output, no reasoning traces).

---

## Success Criteria

- [ ] Daily consolidation output includes `carry_forward` and `key_errors` fields
- [ ] Short/weekly/bimonthly prompts contain synthesis instructions
- [ ] Carry-forward from prior same-tier run is injected into next run's prompt
- [ ] Carry-forward state persists in `memory_entries.carry_forward` column
- [ ] Second consecutive daily run includes first run's carry-forward
- [ ] Bimonthly output is non-empty (or OD-1 decision documented)
- [ ] All existing tests pass (no regression)
- [ ] Memory service restarts cleanly with new code
- [ ] Tier 1 knowledge card includes carry-forward items when injected

---

## Caveats & Uncertainty

- **OD-1 (bimonthly viability):** If bimonthly still produces empty output after carry-forward injection, the decision to drop it (Option B) should be made. This is not a blocking decision — implement carry-forward first, measure, then decide.
- **OD-2 (persistence mechanism):** Recommendation A (column on memory_entries) is chosen. If migration is complex, Option B (separate table) is the fallback.
- **OD-3 (structured input scope):** Recommendation A (daily only) is chosen. If signals derivation proves unreliable, defer Phase 4 and implement carry-forward first (Phases 1-3).
- **Model behavior:** Granite-4.1-3B's ability to follow synthesis instructions ("do not list each input separately") is untested. If it ignores the instruction, the prompt may need stronger constraints or a different model.
- **Carry-forward drift:** Over many cycles, carry-forward items may accumulate without being resolved. Consider a TTL or max-count limit (e.g., max 5 carry-forward items, oldest dropped).
