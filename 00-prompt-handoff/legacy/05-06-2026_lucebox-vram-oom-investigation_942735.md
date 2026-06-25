# Lucebox VRAM OOM Investigation & Analysis

**Source spec:** Live OOM crash log + lucebox-hub source code
**Generated:** 05-06-2026 by codegraph-memsearch investigation
**Goal:** Deep-dive into the VRAM OOM crash when running Qwen3.6-27B Q4_K_XL + DFlash drafter on RTX 3090 (24 GiB), produce exact memory accounting, and deliver actionable configuration fixes.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/llama-forks/lucebox-hub/`
**Server source:** `/home/chief/Coding-Projects/7-council/llama-forks/lucebox-hub/server/src/`
**Key backend:** `/home/chief/Coding-Projects/7-council/llama-forks/lucebox-hub/server/src/qwen35/`
**GGUF deps:** `/home/chief/Coding-Projects/7-council/llama-forks/lucebox-hub/server/deps/llama.cpp/`
**Models:** `/home/chief/models/Qwen3.6-27B/`
**Reference:** https://github.com/Luce-Org/lucebox-hub

**Key files for this task:**

| File | Relevance |
|------|-----------|
| `server/src/qwen35/qwen35_backend.cpp` | Backend init, cache creation, prefill loop, spec decode |
| `server/src/qwen35/qwen35_target_graph.cpp` | KV cache allocation, SSM state, rollback buffers, snapshot logic |
| `server/src/qwen35/graph_builders.cpp` | gallocr graph building, attention mask sizing |
| `server/src/kv_quant.cpp` | KV cache type resolution (TQ3_0 auto-select) |
| `server/src/common/snapshot_backend.h` | Snapshot backend selection (CPU vs GPU) |
| `server/src/common/step_graph.h` | gallocr allocator container |
| `server/src/server/server_main.cpp` | CLI config parsing, auto-TQ3 selection |
| `server/include/dflash27b.h` | Hardcoded model constants |
| `server/src/internal.h` | TargetWeights, TargetCache, DraftWeights structs |
| `server/deps/llama.cpp/ggml/src/ggml-common.h` | block_tq3_0 definition (14 bytes/32 elements) |

**Related codebases:** llama.cpp (ggml CUDA backend, flash attention kernels)

---

## Problem Statement

The lucebox server crashes with CUDA OOM during prefill of a 10,526-token prompt:

```
Command:
  dflash_server <target.gguf> --model-name qwen-UD-Dflash \
    --draft <drafter.gguf> --ddtree --ddtree-budget 16 \
    --fa-window 2048 --max-ctx 46768 --host 127.0.0.1 --port 8091

OOM point:
  [snap] alloc right-sized: cur_pos=10240 buf=489.62 MiB backend=CPU
  CUDA error: out of memory
    cuMemCreate(&handle, reserve_size, &prop, 0)
```

**Hardware:** RTX 3090, 24,126 MiB VRAM, compute 8.6
**Target model:** Qwen3.6-27B-UD-Q4_K_XL (17 GB file, 15.73 GiB on GPU)
**Drafter model:** dflash-draft-3.6-q4_k_m (1,008 MiB file, ~1 GiB on GPU)

---

## Preliminary Findings (from initial investigation)

### Static VRAM Budget (confirmed from source)

| Component | Size | Source |
|---|---|---|
| Target weights (Q4_K_XL) | 16,108 MiB | Log output |
| Drafter weights (Q4_K_M) | 1,008 MiB | File size |
| KV cache (TQ3_0, 16 layers, ctx=46848) | 641 MiB | `256 × 46848 × 4 × 14/32 × 32` |
| SSM state (48 delta, F32) | 144 MiB | `128² × 48 × 4 × 48` |
| Conv state (48 delta, F32) | 6 MiB | `3 × 10240 × 4 × 48` |
| SSM state snapshots (F32) | 144 MiB | Same shape as SSM state |
| Conv state snapshots (F32) | 6 MiB | Same shape as conv state |
| SSM intermediates (Q8_0) | 612 MiB | `128² × 48 × 17 × 48` |
| Conv input cache (F32) | 36 MiB | `19 × 10240 × 4 × 48` |
| Target features (BF16) | 200 MiB | `5 × 5120 × 4096 × 2` |
| Feature mirror (F32) | 400 MiB | `5 × 5120 × 4096 × 4` |
| **Static total** | **19,303 MiB (18.85 GiB)** | |
| **Remaining headroom** | **4,823 MiB (4.71 GiB)** | |

### Dynamic VRAM (the hidden killers)

The static budget leaves 4.7 GiB headroom, but dynamic allocations exceed this:

1. **gallocr graph allocator** — Holds live intermediates for the 64-layer forward pass. Source comment at `qwen35_target_graph.cpp:853` notes "~50 MB per layer × 48 layers" for delta-net intermediates. Even with optimized cpy-into-cache path, peak liveness is estimated **1.5-2.5 GiB**.

2. **Flash attention kernel scratch** — Scales with `kv_len`. At chunk 20 (kv_len=10,752), Q/K/V materialization + internal workspace estimated **1-2 GiB**.

3. **Attention mask** — Allocated at `max_ctx + n_tokens` = `(46768+512) × 512 × 2` = **46 MiB** (F16). Host-side input but inflates gallocr reservation.

**Estimated total: 21-22 GiB**, but gallocr is a *growing* allocator — it expands monotonically within a request. By chunk 20, the cumulative growth pushes past 24 GiB.

### Why chunk 20 specifically?

The prefill processes 512 tokens per chunk. At chunk 20:
- `cur_pos = 10,240` — snapshot boundary (snap_pos=10,516 falls in this chunk)
- Snapshot saves to CPU RAM (489 MiB) — succeeds
- Next chunk: `kv_len = 10,752` — gallocr tries to expand for larger FA graph
- `ggml_gallocr_alloc_graph()` calls `cuMemCreate()` for expanded buffer
- **OOM** — no VRAM remaining

---

## Phases

### Phase 1: Verify Static Budget with Runtime Profiling

**What:** Instrument the code to print exact VRAM usage after each allocation, confirming or correcting the static estimates.

**Files:** Read-only investigation (no modifications needed initially).

**Steps:**
1. Check if `nvidia-smi` or `cudaMemGetInfo()` calls exist in the codebase for runtime VRAM reporting.
2. Add temporary `cudaMemGetInfo()` calls at key allocation points:
   - After target model load
   - After drafter load
   - After `create_target_cache()`
   - After `migrate_prefill_cache()`
   - After each prefill chunk's `ggml_gallocr_alloc_graph()`
3. Build and run with the failing configuration.
4. Record VRAM free/total at each checkpoint.
5. Compare against static estimates.

**Alternative (no rebuild):** Run with `CUDA_VISIBLE_DEVICES=0` and `nvidia-smi -l 1` in parallel to capture VRAM usage over time. Correlate timestamps with server log output.

**Tests:** VRAM measurements match (or explain deviation from) static calculations within ±5%.

**Dependencies:** None.

---

### Phase 2: Profile gallocr Growth During Prefill

**What:** Measure how the gallocr buffer grows across prefill chunks, identifying the exact chunk where VRAM exhaustion occurs.

**Files:**
- Read: `server/src/qwen35/graph_builders.cpp` (gallocr creation)
- Read: `server/src/qwen35/qwen35_backend.cpp` (prefill loop, line ~821-950)

**Steps:**
1. In `build_target_step()` (graph_builders.cpp:226), add logging after `ggml_gallocr_alloc_graph()`:
   ```cpp
   size_t size = 0;
   ggml_gallocr_get_buffer_size(sg.alloc, &size);
   fprintf(stderr, "[gallocr] chunk @%d kv_len=%d alloc_size=%.1f MiB\n",
           kv_start, kv_start + n_tokens, size / 1024.0 / 1024.0);
   ```
2. Similarly log after `ggml_backend_graph_compute()` to catch compute-time allocations.
3. Build and run with failing config.
4. Plot gallocr size vs. chunk number.
5. Identify: does gallocr grow monotonically? At what chunk does it exceed remaining VRAM?

**Tests:** gallocr growth curve matches expected pattern (grows with kv_len, plateaus or jumps at attention layers).

**Dependencies:** Phase 1 (baseline VRAM numbers).

---

### Phase 3: Quantify Flash Attention Scratch Space

**What:** Measure the FA kernel's temporary workspace allocation at various kv_len values.

**Files:**
- Read: `server/deps/llama.cpp/ggml/src/ggml-cuda/` (FA kernel implementation)
- Read: `server/src/qwen35/qwen35_target_graph.cpp` (FA call site, `ggml_flash_attn_ext`)

**Steps:**
1. Find the FA kernel scratch allocation in `ggml-cuda.cu` or `fattn.cu`.
2. Identify the scratch size formula as a function of (kv_len, n_q_heads, n_kv_heads, head_dim).
3. Compute scratch sizes for kv_len = 512, 5120, 10240, 15360.
4. Cross-check with `cudaMemGetInfo()` delta during FA compute.
5. Determine if FA scratch is the dominant dynamic allocation.

**Tests:** FA scratch formula verified against runtime measurements.

**Dependencies:** Phase 1.

---

### Phase 4: Configuration Sensitivity Analysis

**What:** Systematically test how each configuration parameter affects VRAM usage, producing a VRAM-vs-parameter curve.

**Parameters to test:**

| Parameter | Values to test | Expected impact |
|---|---|---|
| `--max-ctx` | 4096, 8192, 16384, 32768, 46768 | KV cache + gallocr intermediates |
| `--fa-window` | 0, 512, 1024, 2048 | FA scratch during decode |
| `--ddtree-budget` | 4, 8, 16, 22 | SSM intermediates + conv input cache |
| `--draft` (present/absent) | with/without drafter | Drafter weights + feature mirror |
| `--cache-type-k/v` | tq3_0, q8_0, q4_0 | KV cache size |

**Steps:**
1. For each parameter, run the server with the target value.
2. Send a standardized prompt (e.g., 5120 tokens) and measure peak VRAM via `nvidia-smi`.
3. Record: peak VRAM, whether OOM occurs, tokens processed before OOM.
4. Produce a table: parameter → peak VRAM → headroom.
5. Identify the "sweet spot" configuration for 24 GiB.

**Tests:** Each configuration either runs to completion or OOMs at a predictable point.

**Dependencies:** Phase 1-3 (understanding of allocation sources).

---

### Phase 5: Produce Optimal Configuration Recommendations

**What:** Synthesize findings into actionable configuration recommendations for different use cases.

**Steps:**
1. Define target profiles:
   - **Max context:** Longest possible context that fits in 24 GiB
   - **Max speed:** Highest throughput (aggressive spec decode, moderate context)
   - **Balanced:** Reasonable context + spec decode on 24 GiB
2. For each profile, specify exact CLI arguments.
3. Document trade-offs: what you gain, what you lose.
4. Include VRAM budget table for each profile.
5. Flag any code-level optimizations that could reduce VRAM (e.g., lazy gallocr growth, FA scratch reduction).

**Output:** Markdown document with configuration recipes.

**Dependencies:** All previous phases.

---

### Phase 6: Code-Level Optimization Opportunities

**What:** Identify code changes that could reduce VRAM usage without sacrificing functionality.

**Files to audit:**
- `server/src/qwen35/qwen35_target_graph.cpp` — cache allocation strategies
- `server/src/qwen35/graph_builders.cpp` — gallocr sizing, attention mask allocation
- `server/src/qwen35/qwen35_backend.cpp` — prefill chunking, scratch release
- `server/src/common/step_graph.h` — gallocr lifecycle

**Specific areas to investigate:**

1. **Attention mask over-allocation:** Currently allocated at `max_ctx + n_tokens` from the first chunk. Could be right-sized to `kv_start + 2*n_tokens`.

2. **gallocr buffer reuse:** The gallocr grows monotonically. Could `release_scratch()` be called between prefill chunks? (Currently only called between requests.)

3. **SSM intermediate quantization:** Currently Q8_0 (1 byte/element). Could Q4_0 or TQ3_0 work? Would save ~50% on the 612 MiB intermediate buffer.

4. **Feature mirror reduction:** Currently F32 at full draft_ctx_max. Could be BF16 or quantized.

5. **Lazy rollback allocation:** `migrate_prefill_cache()` allocates all rollback tensors upfront. Could they be allocated lazily (only when spec decode actually needs them)?

6. **Prefill-only cache optimization:** The cache starts as `prefill_only=true` but is immediately migrated to full cache. Could the migration be deferred until the first spec-decode step?

**Steps:**
1. For each opportunity, estimate VRAM savings.
2. Assess implementation complexity (low/medium/high).
3. Assess quality/speed impact (none/minimal/significant).
4. Prioritize by savings/complexity ratio.
5. Produce a ranked list with code-level descriptions.

**Tests:** Each optimization's VRAM impact verified with targeted measurement.

**Dependencies:** Phase 1-4.

---

## Constraints

- **Read-only first:** Do not modify source code until Phase 1 profiling approach is confirmed.
- **Reproducibility:** All measurements must be reproducible with the same model files and hardware.
- **No model changes:** Investigation is scoped to runtime configuration and code optimization — not model re-quantization or architecture changes.
- **Single GPU:** All analysis assumes one RTX 3090 (24 GiB). Multi-GPU configurations are out of scope.
- **Evidence-first:** Every claim about VRAM usage must be backed by either (a) exact formula from source code, or (b) runtime measurement.

---

## Success Criteria

- [ ] Static VRAM budget verified against runtime measurements (±5% tolerance)
- [ ] gallocr growth curve measured and documented across prefill chunks
- [ ] Flash attention scratch space formula identified and quantified
- [ ] Configuration sensitivity table produced (5+ parameters × 3+ values each)
- [ ] Three configuration profiles documented (max context, max speed, balanced)
- [ ] Each profile tested and verified to run without OOM
- [ ] Code-level optimization opportunities identified, ranked, and described
- [ ] Final report produced with all findings, tables, and recommendations
- [ ] Report saved to `/home/chief/llm-wiki/` with clear structure

---

## Caveats & Uncertainty

1. **gallocr internals:** The ggml_gallocr allocator's exact memory layout is opaque — it uses a SAT-based solver for tensor placement. Peak usage depends on tensor liveness analysis, which is hard to predict statically.

2. **FA kernel implementation:** The flash attention kernel's scratch space depends on the specific CUDA kernel variant selected at runtime ( varies by GPU architecture, quantization types, sequence length). The exact formula may not be documented.

3. **CUDA memory fragmentation:** Even if total allocations fit within 24 GiB, fragmentation can cause OOM. `cuMemCreate` may fail for a large contiguous request even when sufficient total free memory exists.

4. **Draft model variability:** The drafter's VRAM footprint depends on its architecture (layers, heads, head_dim). The 1,008 MiB file size is a proxy — actual GPU residency may differ based on quantization format and backend behavior.

5. **Prefill chunk size:** The default 512-token chunk (`DFLASH27B_PREFILL_UBATCH`) affects both peak kv_len per chunk and the number of chunks. Changing this changes the OOM point.

---

## Execution Order

```
Phase 1 (baseline VRAM) ──┐
                           ├──► Phase 5 (recommendations)
Phase 2 (gallocr profile) ─┤
                           ├──► Phase 6 (code optimizations)
Phase 3 (FA scratch) ──────┤
                           │
Phase 4 (config sweep) ────┘
```

Phases 1-4 can run in any order (1 is most foundational). Phase 5 depends on all. Phase 6 depends on 1-4.

---

## Files to Create

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/01-static-budget.md` | Verified static VRAM budget |
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/02-gallocr-profile.md` | gallocr growth measurements |
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/03-fa-scratch.md` | FA scratch space analysis |
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/04-config-sensitivity.md` | Parameter sweep results |
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/05-recommendations.md` | Configuration recipes |
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/06-code-optimizations.md` | Ranked optimization list |
| Create | `/home/chief/llm-wiki/lucebox-vram-analysis/README.md` | Master index + executive summary |

---

## Notes for Executing Agent

- The lucebox project uses a custom build system (CMake). Build instructions are in the project root.
- The server binary is at `server/build/dflash_server` after building.
- Model files are large (17 GB target, 1 GB drafter) — factor into transfer/copy time.
- Use `nvidia-smi -q -d MEMORY -l 1` for 1-second VRAM polling during tests.
- The OOM reproduces reliably with the reported configuration — no need to hunt for race conditions.
- The `release_scratch()` method in `qwen35_backend.cpp` (~line 614) already releases gallocr between requests — investigate why it doesn't help within a single request's prefill loop.
