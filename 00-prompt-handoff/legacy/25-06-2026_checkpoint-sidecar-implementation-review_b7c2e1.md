# Checkpoint Sidecar + Hybrid Search Fix — Implementation Review Handoff

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `b7c2e1` |
| Entity type | `implementation-review` |
| Short description | Review handoff for fixing post-swap full prompt re-processing on hybrid models (Qwen3.6) |
| Status | `ready-for-review` |
| Related handoff | `25-06-2026_checkpoint-persistence-investigation_a0a428.md` (investigation phases) |
| Prior debug session | `22-06-2026_slot-restore-discrepancy-debug_3f8a2c.md` |
| Generated | 25-06-2026 |
| Next action / owner | Reviewer → approve phased plan → implement Phase A (hybrid search) then Phase B (sidecar) + SGM |

---

## Executive Summary

**Problem:** After SGM swaps a hybrid model (Qwen3.6-27B) back in, the first request forces a **full prompt re-process** (~30–35s for ~32k tokens) even though SGM successfully restores `slot-0.bin` KV state.

**SGM restore is confirmed working** (25-Jun-2026 journal: `RESTORE Qwen-27B-5UD: 29089 tokens` in 139ms, swapbak intact). Do not invest in SGM restore fixes for this bug — the gap is llama.cpp checkpoints.

**Root cause is two independent gaps**, both required for a fix on hybrid models:

1. **In-memory checkpoint search is broken for hybrid/recurrent models** — checkpoints may exist but are never selected (`cur.pos_min < pos_min_thold` is always false when `pos_min` equals full sequence length).
2. **Checkpoints are not persisted across child process restarts** — `SLOT_SAVE` / `SLOT_RESTORE` only call `llama_state_seq_save/load_file()`; `slot.prompt.checkpoints` starts empty on every fresh child.

**SGM slot bin restore alone is insufficient.** Nemotron (standard transformer) works because in-session checkpoints survive without a swap; on swap-back, nemotron also needs sidecar persistence unless the checkpoint-reset path is bypassed.

**Proposed fix (two parts, ship in order):**

| Phase | Change | Repo | Unblocks |
|-------|--------|------|----------|
| **A** | Hybrid/recurrent checkpoint search + lower creation threshold | `main-llama` | In-session reuse; restored sidecars become usable |
| **B** | Persist `slot.prompt.checkpoints` as `slot-0.bin.checkpoints` on save/restore | `main-llama` | Survives child restart |
| **C** | Backup/restore/invalidate `.checkpoints` alongside `.bin` | `super-go-manager` | Survives SGM swap cycle |

Phase A alone fixes **turn 2+ within the same child**. Phases B+C fix **swap-back**. All three are required for the production swap path.

---

## New Evidence (25 Jun 2026 — Qwen-27B-5UD)

### Confirmed incident: swap-back with successful SGM restore, failed checkpoint layer

This incident was initially misread as a **cold start** (no slot on disk) because llama-server logs alone show no restore line and the first request does full prefill. **SGM user journal proves restore succeeded.** The failure is entirely in llama.cpp's in-memory checkpoint layer on a fresh child.

**How to pull SGM logs** (runs as a **user** unit, not system):

```bash
journalctl --user -u super-go-manager \
  --since "2026-06-25 22:06:00" --until "2026-06-25 22:07:00"
# system unit returns nothing:
# journalctl -u super-go-manager  →  -- No entries --
```

Service file: `~/.config/systemd/user/super-go-manager.service`

### SGM journal — full swap cycle (22:06:03–22:06:41)

**Swap out (Qwen → nemotron):**

```
22:06:03  PROXY REQUEST: model=nemotron-cascade current=Qwen-27B-5UD
22:06:03  SWAP-PROXY START: Qwen-27B-5UD -> nemotron-cascade
22:06:03  SAVE Qwen-27B-5UD: 29089 tokens, 1116.1 MiB (166.4ms)
22:06:05  STATE CHANGE: Qwen-27B-5UD loaded -> unloaded (port=54287)
22:06:12  COLD START [nemotron-cascade]: no metadata   ← expected, nemotron has no slot
22:06:12  ✓ WINDOW CLOSED: cold start, child port 50939 ready (no KV cache)
```

**Swap back (nemotron → Qwen) — the incident:**

```
22:06:36  PROXY REQUEST: model=Qwen-27B-5UD current=nemotron-cascade
22:06:36  SWAP-PROXY START: nemotron-cascade -> Qwen-27B-5UD
22:06:36  BACKUP: slot-0.bin backed up for Qwen-27B-5UD (before trigger)
22:06:37  STATE CHANGE: Qwen-27B-5UD unloaded -> loading (port=56963)
22:06:40  model ready on port 56963
22:06:40  BACKUP: restored slot-0.bin from swapbak for Qwen-27B-5UD
22:06:41  RESTORE Qwen-27B-5UD: 29089 tokens (139.0ms)
22:06:41  VERIFY: child port 56963 slot state: n_prompt_tokens=0, n_ctx=88064
22:06:41  ✓ WINDOW CLOSED: slot restored (29089 tokens), child port 56963 now has KV cache
22:06:41  SWAP-PROXY READY: Qwen-27B-5UD proxying request (slot restored)
```

### Layer status for this incident

| Layer | Status | Evidence |
|-------|--------|----------|
| SGM save before swap-out | **OK** | `SAVE … 29089 tokens` at 22:06:03 |
| SGM swapbak (trigger protection) | **OK** | backed up before trigger, restored from `.swapbak` before HTTP restore |
| SGM HTTP restore to child | **OK** | `RESTORE … 29089 tokens (139.0ms)` |
| SGM proxy gating | **OK** | `WINDOW OPEN` → restore → `WINDOW CLOSED` → then proxy |
| llama.cpp KV in child | **OK** (loaded) | 29k tokens restored via `llama_state_seq_load_file` |
| llama.cpp checkpoints in child | **FAIL** | empty on fresh child → full reprocess on first request |
| `n_prompt_tokens=0` in VERIFY | **Expected** | means "no prompt processed yet", not "KV empty" |

**Later save (same session, ~5 min after):** `slot-0.json` on disk shows `slot_tokens: 39026` at `saved_at` 22:11:55 — conversation continued after the swap-back; not relevant to the 22:06:41 incident token count (29089).

### llama-server journal — same incident (port 56963)

Child loads with checkpoints enabled:

```
context checkpoints enabled, max = 64, min spacing = 256
n_ctx = 88064
server is listening on http://127.0.0.1:56963
```

First proxied request immediately after SGM `WINDOW CLOSED` (~22:06:41):

```
reasoning-budget: activated, budget=8096 tokens
slot launch_slot_: id  0 | task 2 | processing task
forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory, ...)
prompt processing, n_tokens = 3584, progress = 0.12, t = 3.44 s / 1041 tok/s
...continues through full context...
```

**Interpretation:**

- Child logs **never** print a line on successful `POST /slots/0?action=restore` — absence in llama-server journal does **not** mean restore failed. Always correlate with SGM `RESTORE` line.
- `ctx-checkpoints = 64` in `models.ini` only controls **in-process** checkpoint retention — it does not persist across child restart.
- ~1040 tok/s prefill confirms **full re-process** despite 29k KV tokens already in slot 0.
- Chat format `peg-native`, MTP `draft-mtp` initialized at load — speculative decoding is unrelated to this failure.
- **This is the canonical repro:** SGM restore succeeds + llama.cpp checkpoint reset = full prefill.

**Contrast (nemotron, same stack, warm session — no swap):**

```
restored context checkpoint (n_past = 19330)
prompt processing, n_tokens = 219, ...
```

### Misread trap (for reviewers)

| Observation | Wrong conclusion | Correct conclusion |
|-------------|------------------|-------------------|
| No restore line in llama-server log | Slot not restored | Child restore is silent; check SGM journal |
| `n_prompt_tokens=0` after restore | KV empty | No prompt run yet; restore populates KV separately |
| Full prefill at ~1000 tok/s | SGM failed | KV may be loaded; checkpoint layer reset `n_past` to 0 |
| No `slot-0.json` at request time | Cold start | Metadata is written on **save**, not required before restore if bin exists; this incident had metadata from 22:06:03 save |

---

## Architecture

```
council_main (:8090)
    → super-go-manager (:9293)     slot-0.bin + sidecars on disk
        → super-router (:18094)    main-llama llama-server, --models-max 1
            → child llama-server   dynamic port, per-model preset from models.ini
```

### Slot artifact layout (target)

```
council-config/slots/kv-slots/{alias}/
├── slot-0.bin                    # KV + token list (existing, via llama_state_seq_*)
├── slot-0.bin.checkpoints        # NEW: serialized slot.prompt.checkpoints
├── slot-0.bin.swapbak            # SGM backup during swap (bin only today → extend)
├── slot-0.bin.checkpoints.swapbak  # NEW: checkpoint backup during swap
└── {config_hash}/
    └── slot-meta.json            # SGM metadata (unchanged)
```

**Not required:** `slot-0.bin.tokens.json` (ik_llama format). main-llama embeds tokens in the bin via `llama_state_seq_save_file(..., tokens.data(), token_count)`.

### Two caching layers (reviewers must keep these separate)

| Layer | Mechanism | Survives child restart? | Survives SGM swap today? |
|-------|-----------|-------------------------|--------------------------|
| KV bin | `POST /slots/0?action=restore` → `llama_state_seq_load_file` | Yes (if file on disk) | Yes (SGM manages) |
| Context checkpoints | `slot.prompt.checkpoints` in RAM | **No** | **No** |

On first request after restore, `update_slots` (~2971–3007 in `server-context.cpp`):

1. `get_common_prefix()` may set high `n_past` from restored tokens.
2. If `pos_min >= pos_min_thold` and no valid checkpoint in `slot.prompt.checkpoints` → `do_reset = true` → `n_past = 0` → full prefill.

---

## Phase A — Hybrid Checkpoint Search (main-llama)

### Location

`main-llama/llama.cpp/tools/server/server-context.cpp` — checkpoint search lambda, ~2976–2984.

### Current code (broken for hybrid)

```cpp
if (cur.pos_max > pos_next) {
    return false;
}
return cur.pos_min < pos_min_thold || cur.pos_min == 0;
```

For hybrid/recurrent models, `llama_memory_seq_pos_min()` returns the **full sequence length**, so `cur.pos_min < pos_min_thold` is false for every checkpoint even when `pos_max` is valid.

### Proposed fix (gate on model type)

```cpp
if (cur.pos_max > pos_next) {
    return false;
}
if (llama_model_is_recurrent(model) || llama_model_is_hybrid(model)) {
    return cur.pos_max <= pos_next;  // pos_next check above already guards pos_max > pos_next
}
return cur.pos_min < pos_min_thold || cur.pos_min == 0;
```

Reference: llama.cpp #22384 (Gastón Parravicini, Qwen3.6-27B Q4_K_M). **Not merged** in main-llama HEAD as of this handoff. ik_llama #1762 still open for the same issue.

### Secondary change — checkpoint creation threshold

`create_checkpoint()` (~2146) is only called when enough new tokens have been processed. For hybrid models, lower minimum from 64 → 4 tokens (per #22384) so short follow-up turns create checkpoints.

### Regression guard

- Gate hybrid branch on `llama_model_is_hybrid()` / `llama_model_is_recurrent()` only.
- Run nemotron (or any dense transformer) through same multi-turn test — must still show `restored context checkpoint`.

### Phase A acceptance

- [ ] Qwen-27B-5UD **same child**, turn 2+: `restored context checkpoint`, not `forcing full prompt re-processing`
- [ ] Prefill on turn 2+: hundreds of tokens, not full context at ~1000+ tok/s
- [ ] Nemotron unchanged
- [ ] MTP still active (`draft-mtp`, `graphs reused` in logs)

---

## Phase B — Checkpoint Sidecar Persistence (main-llama)

### Location

`SERVER_TASK_TYPE_SLOT_SAVE` / `SERVER_TASK_TYPE_SLOT_RESTORE` (~2341–2427).

Today:

```cpp
// SAVE: only bin
llama_state_seq_save_file(ctx_tgt, filepath.c_str(), slot->id, tokens.data(), token_count);

// RESTORE: only bin — checkpoints vector stays empty
llama_state_seq_load_file(ctx_tgt, filepath.c_str(), slot->id, ...);
slot->prompt.tokens.insert(tokens);
```

### Proposed behavior

On **SAVE** (after successful bin write):

1. Write `{filepath}.checkpoints` (i.e. `slot-0.bin.checkpoints` when filename is `slot-0.bin`).
2. Serialize `slot.prompt.checkpoints` — one entry per `common_prompt_checkpoint`.

On **RESTORE** (after successful bin load + token insert):

1. If `{filepath}.checkpoints` exists, deserialize into `slot->prompt.checkpoints`.
2. If missing, log info and continue (graceful degradation — same as today).

On **ERASE**: delete `{filepath}.checkpoints` if present.

### Serialization format (proposed — versioned)

Use a distinct magic from ik_llama to avoid silent mis-read:

```
struct file_header {
    uint32_t magic;      // e.g. 'LPCK' (0x4B43504C)
    uint32_t version;    // 1
    uint32_t n_checkpoints;
    uint32_t reserved;
};

per checkpoint {
    int64_t  n_tokens;
    int32_t  pos_min;
    int32_t  pos_max;
    uint64_t data_tgt_len;
    uint64_t data_dft_len;
    uint64_t data_spec_len;
    uint8_t  data_tgt[data_tgt_len];
    uint8_t  data_dft[data_dft_len];   // empty if no draft ctx
    uint8_t  data_spec[data_spec_len]; // MTP / eagle state
}
```

**Do not** reuse ik_llama's single `data[]` blob — main-llama's `common_prompt_checkpoint` has `data_tgt`, `data_dft`, `data_spec` (see `common/common.h:1065–1110`).

### Implementation notes

- Add `save_prompt_checkpoints_to_file()` / `load_prompt_checkpoints_from_file()` in `common/` or anonymous namespace in `server-context.cpp` — keep server-context diff readable.
- Use existing `common_prompt_checkpoint` methods; no new llama API dependencies.
- `data_spec` must round-trip for MTP (`common_speculative_get/set_state` already used in `create_checkpoint`).
- Atomic write: write to `.checkpoints.tmp` then rename (match SGM meta write pattern).

### Phase B acceptance

- [ ] After long session, `slot-0.bin.checkpoints` exists next to bin
- [ ] Manual `POST /slots/0?action=restore` on **same** child after save clears checkpoints: restored checkpoints non-empty (verify via turn-2 behavior or debug log)
- [ ] Missing sidecar: restore still works, falls back to full re-process (no crash)
- [ ] File size documented for ~19k–32k token session

---

## Phase C — SGM Sidecar Integration (super-go-manager)

### Location

`/home/chief/Coding-Projects/7-council/super-go-manager/main.go` — `SlotStore`.

### Current gaps

| Function | Today | Required |
|----------|-------|----------|
| `BackupSlot` | copies `slot-0.bin` only | also `slot-0.bin.checkpoints` → `.checkpoints.swapbak` |
| `restoreFromBackup` | restores bin only | also checkpoint swapbak |
| `InvalidateSlot` | removes `slot-0.bin` only | also `slot-0.bin.checkpoints` (+ swapbak orphans) |
| `ComputeBinChecksum` / hash purge | bin only | **decision needed:** include checkpoints in hash or separate version field in meta |
| HTTP save/restore | `filename: "slot-0.bin"` | no change — child writes sidecar next to filepath automatically |

`council_main.py` `SlotStore.slot_files()` already anticipates `.bin.checkpoints` — SGM should mirror that layout for consistency.

### Suggested helper pattern

```go
func (ss *SlotStore) slotArtifactPaths(alias string) (bin, ckpt, binBak, ckptBak string)
func (ss *SlotStore) copySlotArtifact(src, dst string) error  // skip if src missing
```

`BackupSlot` / restore: call for both bin and ckpt. Missing checkpoint file during backup is OK (old slots).

### Config

`config.yaml` slot_models already includes `Qwen-27B-5UD` and `qwen3.6-35b-a3b`. No config change required unless adding explicit `checkpoint_sidecar: true` flag (optional, default on).

### Phase C acceptance

- [ ] Swap to nemotron and back: `.checkpoints` survives on disk through backup cycle
- [ ] Binary hash purge removes both bin and checkpoints
- [ ] Slots without `.checkpoints` (legacy) still swap with degraded perf

---

## End-to-End Test Plan (Phase D)

**Setup:** Rebuild main-llama, restart super-router, restart SGM.

1. Load `Qwen-27B-5UD` via council; run multi-turn conversation until ~15k–25k tokens in context.
2. Confirm logs show `created context checkpoint` during session.
3. Trigger SGM save (or idle save); verify files:
   - `slot-0.bin`
   - `slot-0.bin.checkpoints` (non-zero size)
4. Swap to another model (e.g. nemotron); wait for unload.
5. Swap back to `Qwen-27B-5UD`.
6. Send follow-up message with same conversation prefix.

**Pass criteria:**

| Signal | Fail (today) | Pass (fixed) |
|--------|--------------|--------------|
| SGM log | `RESTORE Qwen-27B-5UD N tokens` ✓ (already works) | same + no errors on ckpt sidecar when implemented |
| llama-server log | `forcing full prompt re-processing` | `restored context checkpoint` |
| Prefill tokens | ~30k+ @ ~1000 tok/s | ~200–2000 incremental |
| Wall clock | ~30s+ prefill | sub-second to few seconds |

**Also run:** nemotron swap-back (regression), MTP `draft-mtp` still initialized after swap.

---

## Review Checklist

### Correctness

- [ ] Hybrid search fix is gated on `llama_model_is_hybrid` / `llama_model_is_recurrent`
- [ ] Sidecar load populates `slot.prompt.checkpoints` **before** first `update_slots` task on restored slot
- [ ] `data_spec` serialized for MTP models (`Qwen-27B-5UD` has `spec-type = draft-mtp`)
- [ ] ERASE slot removes checkpoint sidecar

### Compatibility

- [ ] Old slots (bin only) still restore — degraded path acceptable
- [ ] SGM backward compatible when `.checkpoints` absent
- [ ] Magic/version in sidecar format for forward evolution

### Performance

- [ ] Sidecar save < 100ms typical (NVMe)
- [ ] Sidecar load < 500ms typical
- [ ] Document approximate sidecar size vs token count

### Out of scope / rejected alternatives

| Alternative | Why not sufficient |
|-------------|-------------------|
| `--ctx-checkpoints 0` | Stops creation; does not fix empty checkpoint vector on restore |
| `--cache-ram 0` | Disables prompt cache, different mechanism |
| Sidecar only (no Phase A) | Restored checkpoints still fail search on hybrid |
| Phase A only (no sidecar) | Same-child OK; swap-back still full re-process |
| Drop-in ik_llama | No super-router mode; different checkpoint struct; same Bug 1 |
| Trust KV-only, skip checkpoint reset | Incorrect for real SWA; llama.cpp explicitly warns |

### Known residual risks

1. **`TAG_CHECKPOINTS_FIX_POS_MIN` on creation** (~2159): checkpoint `pos_min`/`pos_max` ranges may be wrong for SWA at creation time — separate from search fix; monitor for subtle cache bugs.
2. **`swa_full` disabled** for Qwen3.6 at runtime — fix must work with real SWA (`n_swa > 0`).
3. **`cache_reuse` disabled** for this model — orthogonal; do not conflate with checkpoint fix.
4. **Format drift** on llama.cpp upgrades — version field + SGM hash purge on binary change mitigates.

---

## File Change Matrix

| Action | File | Phase |
|--------|------|-------|
| Modify | `main-llama/llama.cpp/tools/server/server-context.cpp` | A, B |
| Add | `main-llama/llama.cpp/common/checkpoint-io.cpp` (or similar) | B |
| Modify | `super-go-manager/main.go` | C |
| Rebuild | `main-llama` → restart super-router | D |
| Restart | `super-go-manager` | D |
| Optional doc | `llm-wiki/.../checkpoint-persistence-investigation_a0a428.md` → mark phases complete | D |

---

## Log Correlation Guide (for reviewers validating on kuro-machine)

**Always pull both journals for swap incidents:**

```bash
# SGM (user service)
journalctl --user -u super-go-manager --since "…" --until "…"

# Router + children (system service)
journalctl -u llama-server --since "…" --until "…"
# or: journalctl | grep -E '\[56963\]|super-go-manager'
```

| Log line | Component | Meaning |
|----------|-----------|---------|
| `SAVE Qwen-27B-5UD: N tokens` | SGM | Slot bin written before swap-out |
| `BACKUP: slot-0.bin backed up for … (before trigger)` | SGM | Protecting bin from trigger idle-save overwrite |
| `BACKUP: restored slot-0.bin from swapbak for …` | SGM | Swapbak applied before HTTP restore |
| `RESTORE Qwen-27B-5UD: N tokens (Xms)` | SGM | **KV bin restore succeeded** — primary success signal |
| `VERIFY: … n_prompt_tokens=0` | SGM | Normal post-restore (no prompt run yet) |
| `✓ WINDOW CLOSED: slot restored (N tokens)` | SGM | Proxy unblocked; KV should be in child |
| `COLD START [alias]: no metadata` / `no slot bin` | SGM | Genuine cold start — no HTTP restore attempted |
| `SWAP-PROXY READY: … (slot restored)` | SGM | Request proxied after restore gate |
| `cmd_child_to_router:state:{"state":"ready"...}` | super-router | Child ready |
| `proxying request to model Qwen-27B-5UD on port N` | super-router | Request routed (after SGM WINDOW CLOSED) |
| *(no line)* | child llama-server | Successful slot restore is **silent** in child logs |
| `forcing full prompt re-processing` | child llama-server | Checkpoint layer failed (may occur **after** SGM restore OK) |
| `restored context checkpoint` | child llama-server | Checkpoint layer OK |
| `created context checkpoint` | child llama-server | In-session checkpoint created |
| `context checkpoints enabled, max = N` | child at load | Config only — not persistence |

---

## Decision Log (for reviewer sign-off)

| # | Decision | Recommendation |
|---|----------|----------------|
| 1 | Ship Phase A before B+C | **Yes** — validates search fix in isolation |
| 2 | Separate `.checkpoints` file vs extend bin format | **Separate file** — matches ik/council_main, no bin format break |
| 3 | Include checkpoints in SGM binary hash purge | **Yes** — purge both on `llama-server` binary change |
| 4 | Interim 5-line "skip reset if KV restored" patch | **No** — breaks SWA correctness; use as debug only |
| 5 | Port ik_llama code verbatim | **No** — adapt for `data_tgt`/`data_dft`/`data_spec` |
| 6 | "No restore in llama-server log = SGM failed" | **No** — use `journalctl --user -u super-go-manager`; 25-Jun incident had `RESTORE … 29089 tokens` |

---

## References

- main-llama `server-context.cpp` checkpoint reset: lines ~2971–3007
- main-llama `common_prompt_checkpoint`: `common/common.h:1065–1110`
- SGM slot backup: `super-go-manager/main.go:449–470`
- Router preset: `/home/chief/models/super-router/models.ini` `[Qwen-27B-5UD]`
- SGM config: `super-go-manager/config.yaml`
- llama.cpp PR #13194 (SWA checkpoint context), #16391 (prompt cache), #20955 (closed — sidecar attempt), #22384 (hybrid search fix), #24411 (TODO pos_min)
- Investigation phases: `25-06-2026_checkpoint-persistence-investigation_a0a428.md`
