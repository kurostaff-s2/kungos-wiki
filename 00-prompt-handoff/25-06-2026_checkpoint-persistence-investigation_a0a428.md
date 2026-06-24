# Checkpoint Persistence Investigation — Hybrid Model Slot Restore

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `a0a428` |
| Entity type | `session` |
| Short description | Investigate why checkpoint sidecar persistence alone won't fix Qwen3.6 slot restore, and validate the two-bug fix path |
| Status | `draft` |
| Source references | `llm-wiki/00-prompt-handoff/cursor_speculative_decoding_flags_discu.md`, llama.cpp #22384, #24055, #20955, ik_llama #1762 |
| Generated | 25-06-2026 |
| Next action / owner | Investigate agent — validate Bug 1 reproduction, prototype hybrid search fix, measure checkpoint sidecar impact |

## Project Context

**Project root:** `/home/chief/main-llama/llama.cpp`
**Reference docs:** `/home/chief/llm-wiki/00-prompt-handoff/cursor_speculative_decoding_flags_discu.md`
**Related codebases:** `/home/chief/Coding-Projects/7-council/super-go-manager/` (SGM slot persistence)
**Key files for this task:**
- `/home/chief/main-llama/llama.cpp/tools/server/server-context.cpp` — checkpoint search/creation logic
- `/home/chief/main-llama/llama.cpp/include/llama.h` — `llama_model_is_hybrid()` / `llama_model_is_recurrent()`
- `/home/chief/main-llama/llama.cpp/common/common.h` — `common_prompt_checkpoint` struct

## Background

Qwen3.6-27B (Gated DeltaNet hybrid architecture) forces full prompt re-processing (~30s for 32k tokens) on every model swap-back, despite SGM slot bin restore succeeding. Nemotron (standard transformer) does NOT have this problem — it hits checkpoints and processes only new tokens.

The proposed fix was "port ik_llama's checkpoint sidecar persistence to main-llama + extend SGM." Research found this is **insufficient** — two unfixed bugs in main-llama block the fix.

## Known Bugs

### Bug 1 — Checkpoint search broken for hybrid models (BLOCKS the fix)

**Location:** `server-context.cpp:2983`

```cpp
return cur.pos_min < pos_min_thold || cur.pos_min == 0;
```

For hybrid/recurrent models, `llama_memory_seq_pos_min()` always returns the full sequence length. The condition `cur.pos_min < pos_min_thold` is **always false** — no checkpoint is ever found valid, even when 16 good checkpoints exist in memory.

**Evidence:** Commit `db94854ff` (#24411) added a TODO acknowledging this:
```cpp
// [TAG_CHECKPOINTS_FIX_POS_MIN]
// TODO: here we incorrectly determine that the saved checkpoint data covers the [pos_min, pos_max] range
//       this is not true for SWA models
```

**Proposed fix** (from llama.cpp #22384, tested by Gastón Parravicini on Qwen3.6-27B Q4_K_M, RTX 3090):
```cpp
if (llama_model_is_recurrent(model) || llama_model_is_hybrid(model)) {
    return cur.pos_max <= pos_next;
}
return cur.pos_min < pos_min_thold || cur.pos_min == 0;
```

**Status:** NOT merged in main-llama HEAD (`67e9fd3`). Issue #22384 closed Apr 26, 2026 (closed as fixed, but no merged PR found). ik_llama #1762 still OPEN.

### Bug 2 — Checkpoint creation threshold too high

Checkpoint creation requires `n_tokens >= 64`. Short follow-up prompts never generate checkpoints. The #22384 fix lowers this to 4 for hybrid models. **Not merged.**

### Bug 3 — Checkpoint sidecar persistence not implemented

Slot save/restore (`SLOT_SAVE`/`SLOT_RESTORE`) persists KV + tokens via `llama_state_seq_save_file()` but does NOT persist `slot.prompt.checkpoints`. PR #20955 attempted this but was closed without merge (AI-generated content rejection). ik_llama has `save_checkpoints_to_file()` / `load_checkpoints_from_file()` but same Bug 1 blocks it.

## Investigation Phases

### Phase 1: Reproduce Bug 1 with instrumentation

**What:** Confirm that `pos_min` always equals full sequence length for Qwen3.6, and that checkpoint search fails even when checkpoints exist.

**Files:** `tools/server/server-context.cpp` (temporary instrumentation only)

**Steps:**
1. Add debug logging in the checkpoint search lambda to print `pos_min`, `pos_min_thold`, `cur.pos_min`, `cur.pos_max`, `pos_next` for each checkpoint examined
2. Build main-llama with instrumentation
3. Run Qwen3.6-27B through super-router with `--swa-checkpoints 16`
4. Generate a multi-turn conversation (2+ turns) to create checkpoints
5. On turn 2+, capture logs showing: checkpoint exists, search examines it, `pos_min` value, search rejects it
6. Compare with Nemotron (or any non-hybrid model) showing the same search succeeding

**Tests:**
- [ ] Qwen3.6 logs show `pos_min == full_sequence_length` on every checkpoint examination
- [ ] Qwen3.6 logs show `cur.pos_min < pos_min_thold` evaluating to false for all checkpoints
- [ ] Nemotron (or non-hybrid) logs show the same check succeeding with same checkpoint count

**Dependencies:** None

### Phase 2: Prototype the hybrid search fix

**What:** Apply the ~10-line fix from #22384 and measure whether in-session checkpoint reuse works for Qwen3.6.

**Files:** `tools/server/server-context.cpp` (checkpoint search lambda, checkpoint creation threshold)

**Steps:**
1. Apply the hybrid search fix (use `cur.pos_max <= pos_next` for hybrid/recurrent models)
2. Lower checkpoint creation threshold to 4 for hybrid models
3. Build main-llama
4. Run same multi-turn test as Phase 1
5. Measure: does turn 2+ now hit checkpoints? (look for `restored context checkpoint` log line)
6. Measure prefill time: should drop from ~30s full reprocess to sub-second incremental

**Tests:**
- [ ] Qwen3.6 turn 2+ shows `restored context checkpoint` instead of `forcing full prompt re-processing`
- [ ] Prefill time drops from ~30s to <1s for incremental turns
- [ ] Non-hybrid models (Nemotron) still work correctly (no regression)
- [ ] MTP speculative decoding still functions (`graphs reused` count remains high)

**Dependencies:** Phase 1

### Phase 3: Measure checkpoint sidecar size and I/O cost

**What:** Quantify the `.checkpoints` sidecar file size and save/restore latency for Qwen3.6.

**Files:** `tools/server/server-context.cpp` (temporary save instrumentation), SGM slot handling

**Steps:**
1. Port `save_checkpoints_to_file()` from ik_llama (or PR #20955) into main-llama as a standalone function
2. Hook into `SLOT_SAVE` to write `{filepath}.checkpoints` alongside `{filepath}.bin`
3. After a long session (~19k tokens), measure the `.checkpoints` file size
4. Measure time to save (should be <100ms on NVMe)
5. Measure time to load into fresh child (should be <500ms)
6. Compare with existing `slot-0.bin` size (~1-2 GB for Qwen3.6)

**Tests:**
- [ ] `.checkpoints` file size measured and documented for Qwen3.6 at 19k tokens
- [ ] Save time < 100ms, restore time < 500ms
- [ ] Restored child has `slot.prompt.checkpoints` populated (non-empty)
- [ ] Combined with Phase 2 fix: checkpoint search finds restored checkpoint

**Dependencies:** Phase 2 (need hybrid search fix to verify restored checkpoints are found)

### Phase 4: SGM integration assessment

**What:** Determine what SGM changes are needed to handle `.checkpoints` sidecar files.

**Files:** `/home/chief/Coding-Projects/7-council/super-go-manager/main.go`

**Steps:**
1. Audit SGM `BackupSlot()`, `RestoreSlot()`, `CopySlot()` — do they copy all files in slot directory or only `slot-0.bin`?
2. Identify minimal changes to handle `.checkpoints` sidecar alongside `.bin`
3. Assess whether `slot-0.bin.tokens.json` (ik_llama format) is also needed or if main-llama token list is sufficient
4. Document the SGM changes required (diff estimate)

**Tests:**
- [ ] SGM backup/restore cycle preserves `.checkpoints` file
- [ ] SGM swap with `.checkpoints` file produces fast restore (combined with Phase 2+3)

**Dependencies:** Phase 3

### Phase 5: End-to-end validation

**What:** Full swap cycle with all fixes applied — verify the original problem is solved.

**Steps:**
1. Apply Phase 2 fix (hybrid search) + Phase 3 fix (sidecar persistence) + Phase 4 changes (SGM)
2. Run Qwen3.6 through super-router
3. Generate long conversation (~19k tokens)
4. Swap to Nemotron, then swap back to Qwen3.6
5. Verify: swap-back processes only new tokens (not full 32k reprocess)
6. Measure total swap latency including checkpoint sidecar I/O

**Tests:**
- [ ] Swap-back prefill: <1s incremental (not ~30s full reprocess)
- [ ] Total swap time (unload + load + restore) documented
- [ ] MTP speculative decoding active after swap (`draft-mtp` initialized)
- [ ] No regression on non-hybrid models

**Dependencies:** Phases 1-4

## Execution Order

```
Phase 1 (reproduce) → Phase 2 (prototype fix) → Phase 3 (measure sidecar) → Phase 4 (SGM changes) → Phase 5 (E2E)
```

Phases 1-3 are sequential (each depends on previous). Phase 4 can run in parallel with Phase 3 (SGM code audit is independent). Phase 5 requires all previous.

## Caveats & Uncertainty

1. **Checkpoint creation TODO (`TAG_CHECKPOINTS_FIX_POS_MIN`):** The checkpoint *creation* code also has a known issue where `pos_min`/`pos_max` ranges may be incorrect for SWA models. This could cause subtle cache bugs even with the search fix. The TODO is at the creation site, not just the search site.

2. **`swa_full` disabled for Qwen3.6:** Spawn args include `--swa-full` but Qwen3.6 logs `swa_full is not supported by this model, it will be disabled`. This means Qwen runs with real SWA (`n_swa > 0`), which makes checkpoint requirements stricter. The fix must work with real SWA, not `swa_full`.

3. **`cache_reuse` disabled:** Qwen3.6 logs `cache_reuse is not supported by this context, it will be disabled`. This is separate from checkpoints but means another caching mechanism is unavailable.

4. **Checkpoint format stability:** `common_prompt_checkpoint` struct contains `std::vector<uint8_t>` blobs (tgt, dft, spec). File serialization format is not versioned — llama.cpp updates could break persisted checkpoints.

5. **PR #20955 was closed without merge:** The checkpoint sidecar implementation exists in that PR but was rejected. Re-implementing it requires clean, non-AI-generated code.

6. **ik_llama compatibility:** ik_llama has checkpoint sidecar code but same Bug 1 (#1762 open). ik_llama cannot be drop-in replaced with SGM without significant changes (no router mode, different slot API).

## Success Criteria

- [ ] Bug 1 reproduced with logged evidence (pos_min values, search failure)
- [ ] Hybrid search fix validated: Qwen3.6 in-session checkpoint reuse works
- [ ] Checkpoint sidecar size and I/O latency measured for Qwen3.6
- [ ] SGM integration scope documented with diff estimate
- [ ] End-to-end swap cycle: Qwen3.6 swap-back processes only new tokens
- [ ] No regression on Nemotron or other non-hybrid models
- [ ] MTP speculative decoding remains functional after all changes

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify (temp) | `tools/server/server-context.cpp` | Phase 1: debug instrumentation |
| Modify | `tools/server/server-context.cpp` | Phase 2: hybrid search fix |
| Modify | `tools/server/server-context.cpp` | Phase 2: checkpoint creation threshold |
| Modify | `tools/server/server-context.cpp` | Phase 3: checkpoint sidecar save/load |
| Modify | `super-go-manager/main.go` | Phase 4: handle `.checkpoints` sidecar |

## Constraints

- **Do not break non-hybrid models:** Every change must be gated on `llama_model_is_hybrid()` / `llama_model_is_recurrent()` to avoid regressions.
- **Do not add dependencies:** Use existing `llama_state_seq_*` APIs and stdlib only.
- **Preserve MTP speculative decoding:** Checkpoint changes must not break `draft-mtp` initialization or `spec_ckpt` state.
- **SGM backward compatible:** SGM must still work with slots that lack `.checkpoints` files (graceful degradation).
