# Speculative decoding flags discussion
_Exported on 6/24/2026 at 00:38:31 GMT+5:30 from Cursor (3.1.15)_

---

**User**

but it worked with the MTP speculative decoding flags (spec-type = draft-mtp, spec-draft-n-max, etc.) from the model qwen-160k-UD-fast earlier  

Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.760.279 I srv    load_model: initializing slots, n_slots = 1
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.778.138 I common_context_can_seq_rm: the context supports bounded partial sequence removal
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.811.519 I common_speculative_impl_draft_mtp: adding speculative implementation 'draft-mtp'
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.811.523 I common_speculative_impl_draft_mtp: - n_max=3, n_min=0, p_min=0.00, n_embd=5120, backend_sampling=1
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.811.525 I common_speculative_impl_draft_mtp: - gpu_layers=-1, cache_k=f16, cache_v=f16, ctx_tgt=yes, ctx_dft=yes, devices=[default]
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.931 I srv    load_model: speculative decoding context initialized
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.934 I slot   load_model: id  0 | task -1 | new slot, n_ctx = 110592
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.959 I srv    load_model: prompt cache is enabled, size limit: 16192 MiB
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.960 I srv    load_model: use `--cache-ram 0` to disable the prompt cache
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.960 I srv    load_model: for more info see https://github.com/ggml-org/llama.cpp/pull/16391
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.961 I srv    load_model: context checkpoints enabled, max = 16, min spacing = 256
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.897.975 I srv          init: idle slots will be saved to prompt cache upon starting a new task
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.908.426 I init: chat template, example_format: '<|im_start|>system
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] You are a helpful assistant<|im_end|>
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] <|im_start|>user
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] Hello<|im_end|>
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] <|im_start|>assistant
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] Hi there<|im_end|>
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] <|im_start|>user
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] How are you?<|im_end|>
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] <|im_start|>assistant
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] <think>
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] '
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.916.336 I srv          init: init: chat template, thinking = 1
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.916.371 I srv  llama_server: model loaded
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.916.375 I srv  llama_server: server is listening on http://127.0.0.1:55335
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.916.514 I srv    operator(): child server monitoring thread started, waiting for EOF on stdin...
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] cmd_child_to_router:state:{"state":"ready","payload":{"id":"qwen-160k-UD-fast","aliases":["qwen-160k-UD-fast"],"tags":[],"object":"model","created":1782235895,"owned_by":"llamacpp","meta":{"vocab_type":2,"n_vocab":248320,"n_ctx":110592,"n_ctx_train":262144,"n_embd":5120,"n_params":27320697856,"size":17898102784}}}
Jun 23 23:01:35 kuro-machine llama-server[214234]: [55335] 0.02.916.646 I srv  update_slots: all slots are idle
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.787.710 I srv  update_slots: all slots are idle
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.788.159 I srv  update_slots: all slots are idle
Jun 23 23:01:37 kuro-machine llama-server[214234]: 43.14.429.404 I srv  proxy_reques: proxying request to model qwen-160k-UD-fast on port 55335
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.910.973 I srv    operator(): Chat format: peg-native
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.959.775 I slot get_availabl: id  0 | task -1 | selected slot by id (0)
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.960.929 I reasoning-budget: activated, budget=8096 tokens
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.960.958 I slot launch_slot_: id  0 | task 2 | processing task, is_child = 0
Jun 23 23:01:37 kuro-machine llama-server[214234]: [55335] 0.04.960.991 W slot update_slots: id  0 | task 2 | forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory, see https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)
Jun 23 23:01:40 kuro-machine llama-server[214234]: [55335] 0.08.366.892 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   3584, progress = 0.06, t =   3.41 s / 1052.29 tokens per second

---

**Cursor**

You're comparing MTP speculative decoding that worked on `qwen-160k-UD-fast` with a failing setup — I'll trace how this project configures those flags and what differs per model.


You're right — those logs show MTP speculative decoding working correctly on `qwen-160k-UD-fast`. Nothing in them indicates MTP failed.

## What the logs confirm

The important lines are all success paths:

```
common_speculative_impl_draft_mtp: adding speculative implementation 'draft-mtp'
  n_max=3, n_min=0, p_min=0.00, n_embd=5120, backend_sampling=1
  cache_k=f16, cache_v=f16, ctx_tgt=yes, ctx_dft=yes
speculative decoding context initialized
model loaded
```

That means:
- `draft-mtp` registered and initialized
- Draft context (`ctx_dft`) is live alongside the target
- Draft KV cache is `f16` with `n_max=3`
- The model loaded and served a request

The prompt run at **1052 tok/s** on 3584 tokens is normal prefill — MTP mainly speeds up **generation**, not prompt processing.

## The SWA warning is separate

```
forcing full prompt re-processing due to lack of cache data
(likely due to SWA or hybrid/recurrent memory)
```

That is **not** an MTP failure. It means llama.cpp could not reuse a context checkpoint for this prompt prefix (common on Qwen3.6’s hybrid/SWA memory), so it reprocessed the full prompt from scratch. Inference still ran; you just did not get a prefix cache hit on that request.

## Where the MTP flags come from

Your `llama-swap` config has the exact flags that produced those log lines:

```38:50:/home/chief/llama-swap/config.yaml
        --spec-type draft-mtp --spec-draft-n-max 3
        ...
        --spec-draft-type-k f16 --spec-draft-type-v f16
```

That matches the log: `n_max=3`, `cache_k=f16`, `cache_v=f16`.

By contrast, `models/super-router/models.ini` for `qwen-160k-UD-fast` currently has **no** `spec-type` / `spec-draft-n-max` entries — only trunk KV settings (`q8_0`), `swa-full`, slot path, etc. So if this run came through super-router (port 18094 → SGM), MTP was likely coming from a prior config version or another source, not from the current `models.ini`.

## Bottom line

MTP speculative decoding on `qwen-160k-UD-fast` is working as configured. The SWA/cache warning is about prompt checkpoint reuse, not speculative decoding.

If you want MTP guaranteed on the super-router path (not just llama-swap), add to `models.ini`:

```ini
spec-type = draft-mtp
spec-draft-n-max = 3
spec-draft-type-k = f16
spec-draft-type-v = f16
```

Want me to add those to `models.ini` and align `super-go-manager/config.yaml` with the llama-swap MTP settings?

---

**User**

issue is super-go-manager is actually successfully restoing the tokens from slot bin and preventing ull prompt re-processing during model swaps

---

**Cursor**

SGM slot restore is working and should skip full prompt re-processing — I'll trace how that restore reaches the child server and when the SWA/cache warning still fires anyway.


You're right — I mixed up two different caching layers. **SGM slot restore is what prevents full prompt re-processing across model swaps**, and that path is working.

## Two different mechanisms

| Layer | What it does | When it matters |
|-------|--------------|-----------------|
| **SGM slot bin restore** | Saves/restores full KV state via `slot-0.bin` across unload/reload | Model swaps (qwen → gemma → qwen) |
| **llama.cpp prompt cache / checkpoints** | Reuses prefix within a single child process session | Same child, same or similar prompt |

The SWA warning in your earlier log:

```
forcing full prompt re-processing due to lack of cache data
```

comes from the **second** layer — llama.cpp's internal checkpoint logic when it can't find a usable context checkpoint. That is **not** the same as SGM slot restore failing.

## What SGM actually does on swap

The swap flow in `super-go-manager` is deliberate:

1. **Save** current model's KV to `slot-0.bin`
2. **Unload** / load target model
3. **Restore** target's `slot-0.bin` via `POST /slots/0?action=restore`
4. **Block proxy** until `n_restored > 0` (swap lock + `restoring` flag)
5. **Pin `id_slot: 0`** so the restored slot isn't lost to slot drift

```1139:1144:/home/chief/Coding-Projects/7-council/super-go-manager/main.go
	// Pin id_slot: 0 for slot-persistence models to prevent slot drift.
	// Without this, the child may pick a different idle slot than the one
	// we restored, resulting in cache misses.
	if m.HasSlotPersistence(alias) {
		payload["id_slot"] = 0
```

When that works and the incoming prompt prefix matches the restored tokens, you get cache hits like **108 new tokens** (32,729 cached) — not a full 35K-token reprocess.

## Why that log still showed full reprocessing

The `n_tokens = 3584, progress = 0.06` line in your 23:01 log is almost certainly **not** a successful post-swap restore hit. Common causes:

- **Trigger load** — the 1-token request that wakes the model runs with an empty slot *before* restore
- **Fresh child** — new port, no prior session checkpoints
- **Prefix mismatch** — council delegation sends a different system prompt, so `get_common_prefix()` finds little overlap even though KV was restored

The handoff doc already captured this: swap-back with matching prefix = cache hit; swap-back with fresh delegation prompt = expected miss.

## Corrected picture

- **MTP speculative decoding** — working (`draft-mtp` initialized, speeds generation)
- **SGM slot restore** — working (prevents full reprocess on swap when prefix matches)
- **SWA checkpoint warning** — internal llama.cpp path on requests where in-process checkpoints can't help; not evidence that SGM restore failed

So the architecture is: **SGM owns cross-swap KV continuity; MTP owns faster token generation; llama.cpp's SWA warning is a third, in-session concern.**

If you're still seeing full reprocess on swap-back with the *same* conversation (not a new delegation prompt), the next thing to check is whether the request hits the child **after** `WINDOW CLOSED: slot restored` and with `id_slot: 0` pinned — not whether MTP flags are present. Want me to trace a specific swap cycle from journalctl to confirm timing?

---

**User**

un 23 23:37:17 kuro-machine llama-server[264894]: [42469] 0.03.042.348 I srv          init: init: chat template, thinking = 1
Jun 23 23:37:17 kuro-machine llama-server[264894]: [42469] 0.03.042.382 I srv  llama_server: model loaded
Jun 23 23:37:17 kuro-machine llama-server[264894]: [42469] 0.03.042.387 I srv  llama_server: server is listening on http://127.0.0.1:42469
Jun 23 23:37:17 kuro-machine llama-server[264894]: [42469] 0.03.042.505 I srv    operator(): child server monitoring thread started, waiting for EOF on stdin...
Jun 23 23:37:17 kuro-machine llama-server[264894]: [42469] cmd_child_to_router:state:{"state":"ready","payload":{"id":"qwen-160k-UD-fast","aliases":["qwen-160k-UD-fast"],"tags":[],"object":"model","created":1782238037,"owned_by":"llamacpp","meta":{"vocab_type":2,"n_vocab":248320,"n_ctx":110592,"n_ctx_train":262144,"n_embd":5120,"n_params":27320697856,"size":17898102784}}}
Jun 23 23:37:17 kuro-machine llama-server[264894]: [42469] 0.03.042.607 I srv  update_slots: all slots are idle
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.451.958 I srv  update_slots: all slots are idle
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.452.356 I srv  update_slots: all slots are idle
Jun 23 23:37:18 kuro-machine llama-server[264894]: 4.16.790.681 I srv  proxy_reques: proxying request to model qwen-160k-UD-fast on port 42469
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.508.725 I srv    operator(): Chat format: peg-native
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.529.303 I slot get_availabl: id  0 | task -1 | selected slot by id (0)
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.530.511 I reasoning-budget: activated, budget=8096 tokens
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.530.535 I slot launch_slot_: id  0 | task 2 | processing task, is_child = 0
Jun 23 23:37:18 kuro-machine llama-server[264894]: [42469] 0.04.530.557 W slot update_slots: id  0 | task 2 | forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory, see https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)
Jun 23 23:37:21 kuro-machine llama-server[264894]: [42469] 0.07.859.652 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   3584, progress = 0.18, t =   3.33 s / 1076.57 tokens per second
Jun 23 23:37:22 kuro-machine llama-server[264894]: [42469] 0.08.335.092 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   4096, progress = 0.21, t =   3.80 s / 1076.61 tokens per second
Jun 23 23:37:22 kuro-machine llama-server[264894]: [42469] 0.08.819.153 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   4608, progress = 0.24, t =   4.29 s / 1074

---

**Cursor**

This looks like a post-restore request still hitting full reprocess — I'll trace whether SGM restore ran before this request and why llama.cpp's checkpoint path may reset `n_past` anyway.


This log is the gap between **SGM restore succeeding** and **llama.cpp actually skipping prefill**.

## What this log shows

| Time | Event |
|------|-------|
| 23:37:17 | Fresh child on port **42469** finishes loading |
| 23:37:18 | Task 2 arrives (~1.5s later) |
| 23:37:18 | `forcing full prompt re-processing` |
| 23:37:21–22 | Full prefill: 3584 → 4096 → 4608 tokens (~**20k** total at progress 0.18) |

So this is not a small cache miss — the child is re-running the entire prompt from token 0 at ~1076 tok/s.

## SGM restore vs llama.cpp prefill are different layers

SGM does its job correctly:

1. `POST /slots/0?action=restore` → `llama_state_seq_load_file()` loads KV + tokens into slot 0
2. SGM logs `RESTORE … N tokens` / `WINDOW CLOSED`
3. Request is proxied with `id_slot: 0` pinned

But on the **first real request** after that, llama.cpp runs this path in `update_slots`:

```2834:3007:/home/chief/main-llama/llama.cpp/tools/server/server-context.cpp
// 1. n_past = common prefix match (should be high if restore + prompt align)
n_past = slot.prompt.tokens.get_common_prefix(input_tokens);
// ...
// 2. For SWA/hybrid/bounded-seq-rm models with ctx-checkpoints enabled:
if (pos_min >= pos_min_thold) {
    // search slot.prompt.checkpoints — EMPTY on fresh child after slot restore
    bool do_reset = it == slot.prompt.checkpoints.rend();
    if (do_reset) {
        // THIS IS YOUR WARNING LINE
        SLT_WRN(slot, "forcing full prompt re-processing due to lack of cache data ...");
        n_past = 0;  // throws away the prefix match
    }
}
// 3. Then wipes KV from position 0 and re-decodes everything
slot.prompt.tokens.keep_first(n_past);  // n_past=0 → clear tokens
common_context_seq_rm(ctx_tgt, slot.id, p0, -1);  // clear restored KV
```

**Slot bin restore loads KV state but does not populate `slot.prompt.checkpoints`.**  
Qwen3.6 uses bounded partial sequence removal (`common_context_can_seq_rm` in your earlier logs) with `ctx-checkpoints = 16`. For that architecture, llama.cpp requires an in-memory checkpoint to trust existing KV. No checkpoint → reset `n_past` to 0 → full reprocess — even though SGM just injected the slot bin.

That is why you can see both:
- SGM: `RESTORE qwen-160k-UD-fast: 32837 tokens ✓`
- llama-server: `forcing full prompt re-processing` on task 2

## When it *does* work (the 108-new-token case)

The handoff doc's cache hit (`108 new tokens, 32,729 cached`) happens when `pos_min < pos_min_thold` — the checkpoint block is **skipped**, `n_past` from the common-prefix match is kept, and only new tokens are decoded.

That depends on context length, `swa-full`, and memory layout after restore. It is not guaranteed on every swap-back, which is why you see inconsistent behavior.

## What this specific log likely is

Given timing (child born 23:37:17, request 23:37:18) and ~20k-token full prefill, either:

1. **Checkpoint reset after successful restore** (most likely if SGM restore ran first) — bin injected, then llama.cpp discarded it
2. **Prefix mismatch** — restored tokens don't match the incoming council prompt (`n_past` starts at 0 before checkpoint logic)
3. **Request beat restore** — less likely if traffic goes through SGM with swap lock, but possible on direct super-router access

## The actual bug

SGM slot persistence and llama.cpp's SWA/checkpoint prefill logic are **not integrated**. Restore succeeds at the HTTP/bin level; llama.cpp's prompt scheduler does not treat restored KV as valid without checkpoints.

**Fix options** (in order of practicality):

1. **llama.cpp patch** — if KV is populated from slot restore and `get_common_prefix` matches, skip the checkpoint reset (trust restored state)
2. **Persist checkpoints in slot bin** — save/restore `slot.prompt.checkpoints` alongside KV (larger, more complex)
3. **Disable `ctx-checkpoints`** for slot-persisted models — may affect MTP speculative checkpointing
4. **Verify prefix match** — rule out council sending a different system prompt on swap-back

Want me to draft the llama.cpp patch (option 1) or pull SGM + llama-server logs around 23:37:17–18 to confirm whether restore completed before task 2?

---

**User**

Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.498.105 I slot print_timing: id  0 | task 1029 |       total time =     559.05 ms /   180 tokens
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.498.106 I slot print_timing: id  0 | task 1029 |    graphs reused =       1023
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.498.641 I slot      release: id  0 | task 1029 | stop processing: n_tokens = 19509, truncated = 0
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.498.681 I srv  update_slots: all slots are idle
Jun 23 23:54:03 kuro-machine llama-server[264894]: 21.01.751.220 I srv  proxy_reques: proxying request to model nemotron-cascade on port 35373
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.601.906 I srv    operator(): Chat format: peg-native
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.639.501 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, sim_best = 0.996 (> 0.100 thold), f_keep = 0.998
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.640.190 I reasoning-budget: activated, budget=8192 tokens
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.640.233 I slot launch_slot_: id  0 | task 1103 | processing task, is_child = 0
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.640.248 I slot update_slots: id  0 | task 1103 | Checking checkpoint with [19329, 19329] against 19470...
Jun 23 23:54:03 kuro-machine llama-server[264894]: [35373] 0.17.644.154 W slot update_slots: id  0 | task 1103 | restored context checkpoint (pos_min = 19329, pos_max = 19329, n_tokens = 19330, n_past = 19330, size = 47.618 MiB)
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.122.648 I reasoning-budget: deactivated (natural end)
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.128.853 I slot print_timing: id  0 | task 1103 | prompt eval time =     137.34 ms /   219 tokens (    0.63 ms per token,  1594.63 tokens per second)
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.128.855 I slot print_timing: id  0 | task 1103 |        eval time =     351.27 ms /    57 tokens (    6.16 ms per token,   162.27 tokens per second)
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.128.855 I slot print_timing: id  0 | task 1103 |       total time =     488.61 ms /   276 tokens
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.128.856 I slot print_timing: id  0 | task 1103 |    graphs reused =       1078
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.129.402 I slot      release: id  0 | task 1103 | stop processing: n_tokens = 19605, truncated = 0
Jun 23 23:54:04 kuro-machine llama-server[264894]: [35373] 0.18.129.441 I srv  update_slots: all slots are idle
Jun 23 23:54:05 kuro-machine llama-server[264894]: [35373] 0.19.195.755 I srv  update_slots: all slots are idle
Jun 23 23:54:05 kuro-machine llama-server[264894]: 21.04.124.574 I srv    unload_lru: models_max limit reached, removing LRU name=nemotron-cascade
Jun 23 23:54:05 kuro-machine llama-server[264894]: 21.04.124.577 I srv        unload: stopping model instance name=nemotron-cascade
Jun 23 23:54:05 kuro-machine llama-server[264894]: 21.04.124.597 I srv    operator(): stopping model instance name=nemotron-cascade
Jun 23 23:54:05 kuro-machine llama-server[264894]: [35373] 0.19.885.338 I srv    operator(): exit command received, exiting...
Jun 23 23:54:05 kuro-machine llama-server[264894]: [35373] 0.19.885.359 I srv    operator(): operator(): cleaning up before exit...
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.426 I srv    operator(): instance name=nemotron-cascade exited with status 0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.530 I srv          load: spawning server instance with name=qwen-160k-UD-fast on port 48045
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.555 I srv          load: spawning server instance with args:
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.557 I srv          load:   /home/chief/main-llama/llama.cpp/build/bin/llama-server
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.557 I srv          load:   --cache-reuse
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.558 I srv          load:   8192
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.558 I srv          load:   --host
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.558 I srv          load:   127.0.0.1
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.558 I srv          load:   --jinja
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.558 I srv          load:   --min-p
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.559 I srv          load:   0.0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.559 I srv          load:   --mlock
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.559 I srv          load:   --port
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.559 I srv          load:   48045
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.559 I srv          load:   --presence-penalty
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   0.0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   --reasoning-budget
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   8096
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   --repeat-penalty
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   1.0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   --slot-save-path
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.560 I srv          load:   /home/chief/Coding-Projects/7-council/council-config/slots/kv-slots/qwen-160k-UD-fast
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.561 I srv          load:   --spec-draft-n-max
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.562 I srv          load:   3
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   --cache-type-k-draft
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   q8_0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   --cache-type-v-draft
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   q8_0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   --spec-type
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   draft-mtp
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   --swa-full
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.563 I srv          load:   --temperature
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.564 I srv          load:   0.6
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.564 I srv          load:   --top-k
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.564 I srv          load:   20
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.565 I srv          load:   --top-p
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.565 I srv          load:   0.95
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.565 I srv          load:   --alias
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.565 I srv          load:   qwen-160k-UD-fast
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.566 I srv          load:   --batch-size
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.566 I srv          load:   512
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.566 I srv          load:   --ctx-size
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.566 I srv          load:   110592
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.566 I srv          load:   --cont-batching
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.566 I srv          load:   --cache-ram
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.567 I srv          load:   16192
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.567 I srv          load:   --cache-type-k
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.567 I srv          load:   q8_0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.567 I srv          load:   --cache-type-v
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.567 I srv          load:   q8_0
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.567 I srv          load:   --swa-checkpoints
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   16
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   --flash-attn
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   true
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   --model
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   /home/chief/Coding-Projects/7-council/council-config/slots/models/Qwen3.6-27B-UD-Q4_K_XL.gguf
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   --n-gpu-layers
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   99
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.568 I srv          load:   --parallel
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   1
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   --reasoning
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   auto
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   --threads
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   16
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   --threads-batch
Jun 23 23:54:06 kuro-machine llama-server[264894]: 21.04.414.569 I srv          load:   16
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.020.615 I log_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.020.617 I device_info:
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.148.570 I   - CUDA0   : NVIDIA GeForce RTX 3090 (24126 MiB, 23847 MiB free)
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.148.580 I   - CPU     : AMD Ryzen 7 7700 8-Core Processor (95707 MiB, 95707 MiB free)
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.148.670 I system_info: n_threads = 16 (n_threads_batch = 16) / 16 | CUDA : ARCHS = 860 | USE_GRAPHS = 1 | PEER_MAX_BATCH_SIZE = 128 | FA_ALL_QUANTS = 1 | CPU : SSE3 = 1 | SSSE3 = 1 | AVX = 1 | AVX2 = 1 | F16C = 1 | FMA = 1 | BMI2 = 1 | AVX512 = 1 | AVX512_VBMI = 1 | AVX512_VNNI = 1 | AVX512_BF16 = 1 | LLAMAFILE = 1 | OPENMP = 1 | REPACK = 1 |
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.148.702 I srv          init: running without SSL
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.148.755 I srv          init: using 15 threads for HTTP server
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.149.029 I srv         start: binding port with default address family
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.150.224 I srv  llama_server: loading model
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.150.228 I srv    load_model: loading model '/home/chief/Coding-Projects/7-council/council-config/slots/models/Qwen3.6-27B-UD-Q4_K_XL.gguf'
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.467.605 I srv    load_model: [spec] estimated memory usage of MTP context is 849.78 MiB
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.467.628 I common_init_result: fitting params to device memory ...
Jun 23 23:54:06 kuro-machine llama-server[264894]: [48045] 0.00.467.637 I common_init_result: (for bugs during this step try to reproduce them with -fit off, or provide --verbose logs if the bug only occurs with -fit on)
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.529.790 W llama_context: n_ctx_seq (110592) < n_ctx_train (262144) -- the full capacity of the model will not be utilized
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.607.035 I common_init_from_params: warming up the model with an empty run - please wait ... (--no-warmup to disable)
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.681.210 I srv    load_model: creating MTP draft context against the target model '/home/chief/Coding-Projects/7-council/council-config/slots/models/Qwen3.6-27B-UD-Q4_K_XL.gguf'
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.681.242 W llama_context: n_ctx_seq (110592) < n_ctx_train (262144) -- the full capacity of the model will not be utilized
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.746.380 W srv    load_model: cache_reuse is not supported by this context, it will be disabled
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.746.386 W srv    load_model: swa_full is not supported by this model, it will be disabled
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.746.386 I srv    load_model: initializing slots, n_slots = 1
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.763.541 I common_context_can_seq_rm: the context supports bounded partial sequence removal
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.797.893 I common_speculative_impl_draft_mtp: adding speculative implementation 'draft-mtp'
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.797.896 I common_speculative_impl_draft_mtp: - n_max=3, n_min=0, p_min=0.00, n_embd=5120, backend_sampling=1
Jun 23 23:54:08 kuro-machine llama-server[264894]: [48045] 0.02.797.898 I common_speculative_impl_draft_mtp: - gpu_layers=-1, cache_k=q8_0, cache_v=q8_0, ctx_tgt=yes, ctx_dft=yes, devices=[default]
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.581 I srv    load_model: speculative decoding context initialized
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.585 I slot   load_model: id  0 | task -1 | new slot, n_ctx = 110592
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.611 I srv    load_model: prompt cache is enabled, size limit: 16192 MiB
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.611 I srv    load_model: use `--cache-ram 0` to disable the prompt cache
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.611 I srv    load_model: for more info see https://github.com/ggml-org/llama.cpp/pull/16391
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.612 I srv    load_model: context checkpoints enabled, max = 16, min spacing = 256
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.883.629 I srv          init: idle slots will be saved to prompt cache upon starting a new task
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.894.009 I init: chat template, example_format: '<|im_start|>system
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] You are a helpful assistant<|im_end|>
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] <|im_start|>user
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] Hello<|im_end|>
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] <|im_start|>assistant
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] Hi there<|im_end|>
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] <|im_start|>user
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] How are you?<|im_end|>
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] <|im_start|>assistant
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] <think>
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] '
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.901.720 I srv          init: init: chat template, thinking = 1
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.901.755 I srv  llama_server: model loaded
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.901.759 I srv  llama_server: server is listening on http://127.0.0.1:48045
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] cmd_child_to_router:state:{"state":"ready","payload":{"id":"qwen-160k-UD-fast","aliases":["qwen-160k-UD-fast"],"tags":[],"object":"model","created":1782239049,"owned_by":"llamacpp","meta":{"vocab_type":2,"n_vocab":248320,"n_ctx":110592,"n_ctx_train":262144,"n_embd":5120,"n_params":27320697856,"size":17898102784}}}
Jun 23 23:54:09 kuro-machine llama-server[264894]: [48045] 0.02.902.036 I srv  update_slots: all slots are idle
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.083.541 I srv  update_slots: all slots are idle
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.083.987 I srv  update_slots: all slots are idle
Jun 23 23:54:10 kuro-machine llama-server[264894]: 21.08.551.168 I srv  proxy_reques: proxying request to model qwen-160k-UD-fast on port 48045
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.159.699 I srv    operator(): Chat format: peg-native
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.188.304 I slot get_availabl: id  0 | task -1 | selected slot by id (0)
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.189.188 I reasoning-budget: activated, budget=8096 tokens
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.189.210 I slot launch_slot_: id  0 | task 2 | processing task, is_child = 0
Jun 23 23:54:10 kuro-machine llama-server[264894]: [48045] 0.04.189.229 W slot update_slots: id  0 | task 2 | forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory, see https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)
Jun 23 23:54:13 kuro-machine llama-server[264894]: [48045] 0.07.515.038 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   3584, progress = 0.11, t =   3.33 s / 1077.63 tokens per second
Jun 23 23:54:14 kuro-machine llama-server[264894]: [48045] 0.07.987.933 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   4096, progress = 0.13, t =   3.80 s / 1078.26 tokens per second
Jun 23 23:54:14 kuro-machine llama-server[264894]: [48045] 0.08.467.219 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   4608, progress = 0.14, t =   4.28 s / 1077.14 tokens per second
Jun 23 23:54:15 kuro-machine llama-server[264894]: [48045] 0.08.946.538 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   5120, progress = 0.16, t =   4.76 s / 1076.24 tokens per second
Jun 23 23:54:15 kuro-machine llama-server[264894]: [48045] 0.09.430.992 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   5632, progress = 0.18, t =   5.24 s / 1074.45 tokens per second
Jun 23 23:54:16 kuro-machine llama-server[264894]: [48045] 0.09.916.313 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   6144, progress = 0.19, t =   5.73 s / 1072.80 tokens per second
Jun 23 23:54:16 kuro-machine llama-server[264894]: [48045] 0.10.407.299 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   6656, progress = 0.21, t =   6.22 s / 1070.43 tokens per second
Jun 23 23:54:17 kuro-machine llama-server[264894]: [48045] 0.10.898.151 I slot print_timing: id  0 | task 2 | prompt processing, n_tokens =   7168, progress = 0.23, t =   6.71 s / 1068

---

**Cursor**

This log is a perfect A/B comparison in the same session. It pins down exactly what's happening.

## Side-by-side: warm child vs fresh swap

**nemotron-cascade (port 35373) — same process, checkpoints warm**

```
selected slot by LCP similarity, sim_best = 0.996, f_keep = 0.998
Checking checkpoint with [19329, 19329] against 19470...
restored context checkpoint (pos_min = 19329, n_tokens = 19330, n_past = 19330)
prompt eval time = 137.34 ms / 219 tokens   ← only 219 tokens decoded
```

19,330 tokens of context reused. Checkpoint hit. **488 ms total.**

**qwen-160k-UD-fast (port 48045) — fresh child after LRU unload**

```
23:54:06  unload nemotron-cascade
23:54:06  spawn qwen-160k-UD-fast on port 48045
23:54:09  model loaded, slots idle
23:54:10  task 2 → forcing full prompt re-processing
23:54:13  prompt processing, n_tokens = 3584, progress = 0.11  ← ~32k total
```

No checkpoint line. Full prefill at ~1077 tok/s. **~30 seconds of wasted compute.**

Same router, same hour. The only difference is nemotron stayed warm with in-memory checkpoints; qwen is a brand-new child with an empty checkpoint list.

## SGM restore vs llama.cpp checkpoints

SGM's slot bin restore (`POST /slots/0?action=restore`) loads KV state + token list into slot 0. It does **not** populate `slot.prompt.checkpoints`.

On Qwen3.6 with bounded partial sequence removal + `swa-checkpoints 16`, the next request needs an in-memory checkpoint to trust existing KV. Fresh child → no checkpoints → this path fires:

```
forcing full prompt re-processing due to lack of cache data
n_past = 0
```

Then KV from the slot restore gets wiped and the full ~32k prompt is re-decoded.

SGM can log `RESTORE … 19509 tokens ✓` and you still see this — the bin was injected, then llama.cpp's checkpoint scheduler threw it away.

## What the spawn args also tell us

`models.ini` was updated — MTP flags are now in the router preset:

```
--spec-type draft-mtp --spec-draft-n-max 3
--slot-save-path .../kv-slots/qwen-160k-UD-fast
--swa-full --swa-checkpoints 16
```

But on load, Qwen3.6 disables two of those:

```
cache_reuse is not supported by this context, it will be disabled
swa_full is not supported by this model, it will be disabled
```

So Qwen runs with real SWA (`n_swa > 0`), which makes the checkpoint requirement **stricter** — exactly why nemotron-style checkpoint hits work in-session but post-swap restore doesn't.

## The timeline on this swap

| Time | Event |
|------|-------|
| 23:54:03 | nemotron finishes task 1103 with checkpoint reuse (219 tokens) |
| 23:54:05 | LRU evicts nemotron (`models_max=1`) |
| 23:54:06–09 | qwen spawns fresh on 48045, loads ~3s |
| 23:54:10 | task 2 arrives — `selected slot by id (0)` (SGM pinned) |
| 23:54:10 | checkpoint miss → full reprocess |

~1 second between ready and task 2. Even if SGM restore completed in that window, the checkpoint list is still empty on a fresh child — so you get full reprocess regardless.

## What actually needs fixing

This isn't an SGM bug. SGM is doing its job. The gap is in llama.cpp:

**After slot bin restore, trust the restored KV when `get_common_prefix()` matches — don't require in-memory checkpoints that only exist mid-session.**

Options:
1. **llama.cpp patch** — skip the checkpoint reset when KV is populated from slot restore + prefix matches (smallest fix)
2. **Persist checkpoints in slot bin** — save/restore `slot.prompt.checkpoints` alongside KV (heavier)
3. **Accept the cost** — first request after every swap pays full prefill (~30s for 32k tokens on qwen)

The nemotron log proves the mechanism works when checkpoints exist. The qwen log proves fresh children after swap don't have them, even with SGM slot restore.

Want me to draft the llama.cpp patch for option 1?

---

**User**

will it work if we disabled check points?

---

**Cursor**

Tracing whether disabling checkpoints skips the reset path or only stops checkpoint creation.


**No — not by config alone.** Setting `--swa-checkpoints 0` in `models.ini` will not fix post-swap slot restore on Qwen.

## Why

Checkpoints do two separate jobs in llama.cpp:

| Job | Controlled by `n_ctx_checkpoints`? |
|-----|-------------------------------------|
| **Creating** checkpoints during a session | Yes — only when `> 0` |
| **Searching** checkpoints on each request and resetting `n_past` if none found | **No** — always runs |

The code that causes your warning is **not** gated on checkpoint config:

```2971:3007:/home/chief/main-llama/llama.cpp/tools/server/server-context.cpp
if (pos_min >= pos_min_thold) {
    // search slot.prompt.checkpoints — empty on fresh child after swap
    bool do_reset = it == slot.prompt.checkpoints.rend();
    if (do_reset) {
        SLT_WRN(slot, "forcing full prompt re-processing ...");
        n_past = 0;
    }
}
```

With checkpoints disabled you get:
- No checkpoints ever created mid-session
- Same empty-list search on every request where `pos_min >= pos_min_thold`
- Same `do_reset` → same full reprocess

So qwen after swap would still hit the warning. You'd also lose what nemotron just showed you working:

```
restored context checkpoint (n_past = 19330)
prompt eval = 219 tokens   ← this path requires checkpoints
```

## What would actually help

**Option A — config + small patch (most practical test)**  
Gate that reset block on `n_ctx_checkpoints > 0`:

```cpp
if (params_base.n_ctx_checkpoints > 0 && pos_min >= pos_min_thold) {
    // existing checkpoint search / reset logic
}
```

Then `--swa-checkpoints 0` means: trust `n_past` from common-prefix match + SGM slot restore, don't require in-memory checkpoints.

**Option B — proper fix**  
After slot bin restore, if `get_common_prefix()` matches, skip the reset even when checkpoints are enabled.

**Option C — persist checkpoints in slot bin**  
Heavier; saves/restores `slot.prompt.checkpoints` alongside KV.

## Tradeoffs of disabling checkpoints (with patch)

| | With checkpoints (current) | Checkpoints off + patch |
|--|---------------------------|-------------------------|
| Post-swap qwen | Full ~32k reprocess | Likely fast (if prefix matches) |
| In-session nemotron-style reuse | 219-token eval via checkpoint | Relies on prefix match only |
| MTP draft rollback | Uses `spec_ckpt` during generation (separate from prompt checkpoints) | Should still work |

## Quick test

In `models.ini` for `qwen-160k-UD-fast`, try:

```ini
swa-checkpoints = 0
```

Restart super-router and swap back. **Expect the same full reprocess** unless you also patch `server-context.cpp` as in option A.

Want me to implement option A in your `main-llama` fork? It's a ~5-line change and easy to revert.

---

**User**

1. what about - ersist checkpoints in slot bin — save/restore slot.prompt.checkpoints alongside KV (heavier) ? 2. will unified kv help with this?

---

**Cursor**

Researching how slot save/load handles checkpoints and what unified KV changes for SWA/hybrid models.


## 1. Persisting checkpoints in the slot bin

**Yes, this is the right long-term fix — and you already have a blueprint for it.**

### What exists today

| Layer | Saves KV | Saves checkpoints | Survives child death |
|-------|----------|-------------------|----------------------|
| `slot-0.bin` (SGM save) | Yes | **No** | Yes |
| `--cache-ram` prompt cache | Yes | **Yes** | **No** (RAM, same process) |
| ik_llama slot save | Yes | **Yes** (`slot-0.bin.checkpoints`) | Yes |

main-llama's slot save only calls `llama_state_seq_save_file()` — tokens + KV, nothing else:

```2366:2367:/home/chief/main-llama/llama.cpp/tools/server/server-context.cpp
const llama_tokens & tokens = slot->prompt.tokens.get_tokens();
const size_t nwrite = llama_state_seq_save_file(ctx_tgt, filepath.c_str(), slot->id, tokens.data(), token_count);
```

The in-RAM prompt cache **does** include checkpoints (that's why nemotron worked in-session):

```1663:1670:/home/chief/main-llama/llama.cpp/tools/server/server-task.cpp
states.push_back({
    /*.tokens      =*/ prompt.tokens.clone(),
    /*.data        =*/ { main, drft },
    /*.checkpoints =*/ prompt.checkpoints,
});
```

Your council `SlotStore` already anticipates a sidecar:

```924:927:/home/chief/Coding-Projects/7-council/super_council/council_main.py
return {
    "bin": base.with_suffix(".bin"),
    "ckpt": Path(str(base) + ".bin.checkpoints"),
```

ik_llama implements exactly this on save/restore:

```2841:2891:/home/chief/Coding-Projects/7-council/llama-forks/ik_llama.cpp/examples/server/server-context.cpp
save_checkpoints_to_file(filepath + ".checkpoints", slot->server_cached_prompt.checkpoints);
// ...
llama_state_seq_save_file(ctx, filepath.c_str(), ...);
// restore:
llama_state_seq_load_file(ctx, filepath.c_str(), ...);
load_checkpoints_from_file(filepath + ".checkpoints", slot->server_cached_prompt.checkpoints);
```

### Would it work for qwen swap-back?

**Very likely yes** — it reproduces the nemotron path you already saw:

```
restored context checkpoint (n_past = 19330)
prompt eval = 137 ms / 219 tokens
```

After swap, fresh child would load `slot-0.bin` + `slot-0.bin.checkpoints`, find a matching checkpoint, and skip the full ~32k prefill.

### Cost and caveats

**Size:** Each checkpoint stores partial KV snapshots (tgt + dft + MTP `data_spec`). Your nemotron checkpoint was **47.6 MiB** for one entry; with `swa-checkpoints = 16` you could add **hundreds of MB** beside the existing ~1–2 GB slot bin.

**Save/restore time:** SGM already budgets ~150ms for bin restore; checkpoint sidecar could add seconds on NVMe for large contexts.

**Implementation scope:**
1. Port `save_checkpoints_to_file` / `load_checkpoints_from_file` into main-llama (adapt to `common_prompt_checkpoint` with tgt/dft/spec blobs)
2. Hook into `SLOT_SAVE` / `SLOT_RESTORE` handlers (auto-load `{filepath}.checkpoints` if present)
3. Extend SGM to backup/restore/copy `slot-0.bin.checkpoints` alongside `slot-0.bin` and `swapbak`

**SWA correctness:** main-llama has an open TODO that checkpoint `pos_min`/`pos_max` ranges may be wrong for SWA models — could cause subtle cache bugs even with persistence.

**Checkpoints must exist at save time:** They're created during prompt processing. If you save right after a long session (as SGM does on swap-away), they should be there. A save before any request completes would have an empty checkpoint list — same failure mode as today.

---

## 2. Will unified KV help?

**Not for cross-swap slot restore. It only helps within a single child process.**

### What `kv-unified` does

- Single shared KV buffer across slots (`n_stream = 1`)
- With `--cache-ram` + `--cache-idle-slots`: idle slots are saved to the **in-RAM prompt cache** (including checkpoints), then KV is cleared to free room

```1290:1291:/home/chief/main-llama/llama.cpp/tools/server/server-context.cpp
if (params_base.kv_unified) {
    SRV_INF("%s", "idle slots will be saved to prompt cache and cleared upon starting a new task\n");
```

### Your current config

- `parallel = 1` in `models.ini`
- Default `kv_unified = false` (only auto-enabled when `n_parallel < 0` → 4)
- You're **not** using unified KV today

### Why it doesn't fix swap

LRU unload kills the child → prompt cache (RAM) is gone. Unified KV never crosses process boundaries. SGM's `slot-0.bin` is what survives — and it doesn't include checkpoints regardless of KV mode.

Unified KV **would** help if you:
- Stay on the same child process (no LRU eviction)
- Enable `--kv-unified --cache-ram 16192` (you already have cache-ram)
- Rely on idle-slot → prompt-cache path instead of SGM slot bin

But your architecture uses `models_max=1` with LRU eviction, so children die on every swap. Unified KV doesn't change that.

---

## Recommendation matrix

| Approach | Fixes swap-back prefill? | Effort | Risk |
|----------|--------------------------|--------|------|
| **Checkpoint sidecar** (ik_llama pattern) | Yes (best match to nemotron behavior) | Medium–high | File size, SWA pos bugs |
| **Trust slot restore** (skip reset when prefix matches) | Yes (lighter) | Low (~5 lines) | May be wrong for some SWA edge cases |
| **Disable checkpoints** (config only) | No | Trivial | Makes things worse |
| **Unified KV** | No (swap) / yes (same child) | Config change | Doesn't address your swap path |

**Practical path:** implement the **checkpoint sidecar** in main-llama (you have ik_llama + council `SlotStore` as reference), wire SGM to handle the `.checkpoints` file. That's the architecturally correct fix. A small **trust-restore patch** is a good interim test to confirm the diagnosis before committing to multi-hundred-MB sidecar files.

Want me to start with the sidecar implementation in main-llama, or the interim trust-restore patch first?

---

**User**

would ik llama work with the SGM without any fixes?

---

**Cursor**

Comparing ik_llama's slot save/restore API and file layout with what SGM expects.


**No.** ik_llama would not work with your current SGM + super-router stack without changes. The slot HTTP API is similar, but several layers below it are not compatible.

## What would work (API surface only)

ik_llama’s slot endpoints match what SGM calls:

| SGM expects | ik_llama provides |
|-------------|-------------------|
| `POST /slots/0?action=save` `{"filename":"slot-0.bin"}` | Same |
| `POST /slots/0?action=restore` | Same |
| Response: `n_saved`, `n_restored`, `n_read` | Same field names |
| `GET /slots` | Same (array with `is_processing`, etc.) |

So at the HTTP level, `SlotClient` in SGM would not immediately 404.

## What breaks without fixes

### 1. ik_llama is not a router — it can’t replace super-router

SGM talks to **super-router** on `:18094`, which spawns **child** processes and reports:

```json
{ "status": { "value": "loaded", "args": ["...", "--port", "48045", ...] } }
```

ik_llama’s `/v1/models` is single-model only — no `status.value`, no child port, no LRU unload/spawn:

```1277:1292:/home/chief/Coding-Projects/7-council/llama-forks/ik_llama.cpp/examples/server/server.cpp
const auto handle_models = [...](...) {
    json models = {
        {"object", "list"},
        {"data", { { {"id", params.model_alias}, ... } }}
    };
```

SGM’s `FindLoadedModel`, `WaitForModelLoaded`, and `POST /models/load` all assume **main-llama router mode**. ik has no `/models/load` in its server at all.

### 2. Checkpoint sidecars are not managed by SGM

ik saves three files on slot save:

```
slot-0.bin
slot-0.bin.checkpoints   ← the important one for fast prefill
slot-0.bin.tokens.json
```

SGM only handles `slot-0.bin` and `slot-0.bin.swapbak`:

```449:458:/home/chief/Coding-Projects/7-council/super-go-manager/main.go
func (m *Manager) BackupSlot(alias string) error {
    src := m.store.binPath(alias, "")
    dst := m.backupPath(alias)
    // only copies slot-0.bin — not .checkpoints or .tokens.json
```

Even if the child were ik, the swap backup/restore cycle could leave checkpoint sidecars missing or out of sync. That’s the main benefit of ik over main-llama for your use case.

### 3. Existing slot bins are not portable

Your slots were written by **main-llama** children. ik uses the same underlying `llama_state_seq_*` APIs but is a different fork — state layout, checkpoint format, and token sidecars differ. SGM would also **purge all slots** on binary hash change when you switch binaries.

You’d need a full re-save cycle per model after any binary swap.

### 4. Feature gaps vs your current qwen config

Your spawn args include things ik doesn’t have in this tree:

- `--spec-type draft-mtp` — not in ik_llama
- `--swa-checkpoints 16` — ik has `ctx-checkpoints` but different implementation
- `models.ini` preset router spawning — ik has no `models-preset` / `models-max`

### 5. Architecture mismatch

Your path is:

```
council → SGM (:9293) → super-router (:18094, main-llama) → child (:48xxx, main-llama)
```

ik_llama is a **single-model server**. It doesn’t fit as a drop-in for either the router or the multi-model swap layer without replacing the whole inference topology.

## Summary

| Layer | ik_llama without fixes? |
|-------|-------------------------|
| Slot save/restore HTTP API | Mostly compatible |
| Checkpoint persistence (the actual fix you need) | ik has it; SGM doesn’t copy sidecars |
| Super-router integration | **No** — no router mode |
| SGM swap orchestration | **No** — depends on router status/ports/`/models/load` |
| Existing slot files | **No** — incompatible + hash purge |
| MTP + current model flags | **No** |

## Practical options

1. **Best fit for your stack:** Port ik’s checkpoint sidecar logic into **main-llama** (same binary super-router already spawns), and extend SGM to backup/restore `slot-0.bin.checkpoints` (+ `.tokens.json` if needed).

2. **ik as child only (still needs fixes):** Point super-router at ik binary for specific models, extend SGM sidecar handling, re-save all slots, accept loss of `draft-mtp`.

3. **ik standalone (no SGM router path):** Only makes sense if you drop multi-model LRU swapping entirely.

**Bottom line:** ik_llama has the checkpoint persistence you want, but it won’t plug into SGM + super-router as-is. The smallest path is porting the checkpoint sidecar into main-llama and teaching SGM to handle the extra files — not swapping the whole inference stack to ik.

---

**User**

prepare a hand for a thorough review of the proposal & the implemetation of the  Port ik’s checkpoint sidecar logic into main-llama (same binary super-router already spawns), and extend SGM to backup/restore slot-0.bin.checkpoints (+ .tokens.json if needed); ersist checkpoints in slot bin — save/restore slot.prompt.checkpoints alongside KV (heavier)

