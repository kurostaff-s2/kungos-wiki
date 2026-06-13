# LFM Quantization + MoE SYCL Benchmark

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `531c5d` |
| Entity type | `handoff` |
| Short description | Benchmark LFM2.5-8B-A1B quantization variants (Q4_K_XL vs IQ4_NL) on SYCL Arc A380, isolate MoE kernel bottleneck, optimise t/s and prompt processing speeds |
| Status | `draft` |
| Source references | `~/llm_test_lfm_arc_q4_trace85a.json`, `/tmp/lfm_arc_*.log`, `build-sycl/bin/llama-server` |
| Generated | 13-06-2026 |
| Next action / owner | Execute Phase 1 (baseline bench), then Phase 2 (optimise), then Phase 3 (compare) |

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/llama-forks/arc-llm/`
**Key files for this task:**
- `build-sycl/bin/llama-server` — SYCL build (Arc A380, Intel level_zero)
- `build-cpu-avx512/bin/llama-server` — CPU AVX512 build (Ryzen 7700, zen4)
- `ggml/src/ggml-sycl/mmvq.cpp` — MoE kernel dispatch (line 2412-2472)
- `ggml/src/ggml-sycl/vecdotq.hpp` — Quantization vec_dot kernels
- `/home/chief/models/LFM2.5-8B-A1B-UD-Q4_K_XL.gguf` — 5.0GB model
- `/home/chief/models/LFM2.5-8B-A1B-UD-IQ4_NL.gguf` — 4.1GB model
**Reference docs:** `~/llm-wiki/00-prompt-handoff/13-06-2026_consolidation-prompt-and-model-review_936dd2.md`

---

## Background

### Problem Statement

LFM2.5-8B-A1B-UD (MoE architecture) runs catastrophically slow on SYCL Arc A380 with IQ4_NL quantization (0.56 t/s) compared to Q4_K_XL (14+ t/s). Both use the same SYCL backend. Root cause: **MoE expert kernel dispatch in `ggml_sycl_mul_mat_vec_q_id()` supports Q4_K but NOT IQ4_NL** — the IQ4_NL path falls back to a slow generic/cpu-offload path during token generation.

### Known Data Points

| Metric | Q4_K_XL (5.0GB) | IQ4_NL (4.1GB) |
|--------|------------------|-----------------|
| **Prompt processing** | 297 → 82 t/s (degrades with context) | 237 → 82 t/s (similar) |
| **Token generation** | **14.06 t/s** (MoE kernel exists) | **0.56 t/s** (MoE kernel missing) |
| **GPU fit** | `failed to fit params` → partial offload | Fits fully on GPU (-ngl 99) |
| **Model load time** | ~22 min (first run) | ~2.5 min |
| **VRAM usage** | Partial (some layers CPU) | Full (all layers GPU) |

### Key Discovery

The MoE dispatch at `mmvq.cpp:2412-2472` has kernels for: Q4_0, Q4_1, Q5_0, Q5_1, Q8_0, Q2_K, Q3_K, Q4_K, Q5_K, Q6_K, MXFP4, NVFP4. **IQ4_NL is absent.** When IQ4_NL model hits MoE layers, it falls back to a slow path.

### Caveats

- RTX 3090 is occupied by Qwen3.6-27B (port 8091) — cannot use for testing
- Arc A380 has 6GB VRAM — Q4_K_XL (5GB) leaves little headroom for KV cache
- Previous attempt to add IQ4_NL MoE kernel crashed in `ggml_sycl_mul_mat` — kernel signature may be incompatible
- AMD Raphael iGPU (Ryzen 7700 integrated) has Vulkan support but shares system RAM

---

## Execution Plan

### Phase 1: Baseline Benchmark (no consolidation, raw speeds only)

**What:** Measure prompt processing (pp) and token generation (t/s) speeds for both quantization variants across different offload strategies. No full pipeline — just raw inference speeds via llama-bench or targeted curl requests.

**Files:** None to modify. Use existing `build-sycl/bin/llama-server` and `build-cpu-avx512/bin/llama-server`.

**Test matrix:**

| Config | Model | -ngl | -ctk/-ctv | -np | Backend |
|--------|-------|------|-----------|-----|---------|
| A | Q4_K_XL | 99 (full) | q8_0/q8_0 | 1 | SYCL |
| B | Q4_K_XL | 32 (partial) | q8_0/q8_0 | 1 | SYCL+CPU |
| C | Q4_K_XL | 64 (mid) | q8_0/q8_0 | 1 | SYCL+CPU |
| D | IQ4_NL | 99 (full) | q8_0/q8_0 | 1 | SYCL |
| E | IQ4_NL | 32 (partial) | q8_0/q8_0 | 1 | SYCL+CPU |
| F | IQ4_NL | 64 (mid) | q8_0/q8_0 | 1 | SYCL+CPU |
| G | IQ4_NL | 99 (full) | q4_0/q4_0 | 1 | SYCL |
| H | IQ4_NL | 32 (partial) | q4_0/q4_0 | 1 | SYCL+CPU |

**Steps:**
1. For each config, start llama-server on port 18095
2. Wait for warmup (model loaded + chat template resolved)
3. Run `llama-bench` style measurement:
   - Send a 4096-token prompt (use trace-85a9cdb8.md truncated to ~16K chars ≈ 4K tokens)
   - Measure prompt processing speed (t/s for input)
   - Measure generation speed (t/s for output, request 512 output tokens)
   - Run 3 iterations, discard first (cold cache), average remaining 2
4. Record: pp_t/s, gen_t/s, model_load_time, vramp_usage (from logs)
5. Save results to `/home/chief/llm_bench_lfm_matrix.json`

**Prompt for benchmarking (reuse across all configs):**
```
Use trace-85a9cdb8.md truncated to ~16K chars (~4096 tokens).
System prompt: "You are a helpful assistant."
User prompt: [truncated trace content]
Request: max_tokens=512, temperature=0.3
```

**Tests:**
- [ ] All 8 configs complete without crash
- [ ] Results saved with timestamps, config params, and raw timing logs
- [ ] Each config shows both pp_t/s and gen_t/s

**Output format (JSON):**
```json
{
  "config": "A",
  "model": "Q4_K_XL",
  "ngl": 99,
  "ctk": "q8_0",
  "ctv": "q8_0",
  "backend": "SYCL",
  "model_load_time_s": 1320,
  "runs": [
    {"run": 1, "pp_t/s": 82.3, "gen_t/s": 14.1, "pp_tokens": 4096, "gen_tokens": 512, "pp_time_s": 49.8, "gen_time_s": 36.3},
    {"run": 2, "pp_t/s": 85.1, "gen_t/s": 14.3, "...": "..."},
    {"run": 3, "pp_t/s": 84.7, "gen_t/s": 14.2, "...": "..."}
  ],
  "avg_gen_t/s": 14.25,
  "avg_pp_t/s": 84.9
}
```

**Dependencies:** None (Phase 1 is independent).

---

### Phase 2: Optimise Best Configs

**What:** Take the top 2 configs from Phase 1 (highest gen_t/s) and optimise further by tuning server parameters.

**Parameters to tune (one at a time, measure delta):**

| Parameter | Current | Test values | Purpose |
|-----------|---------|-------------|---------|
| `--threads` | 8 | 4, 8, 12, 16 | CPU thread parallelism |
| `--threads-batch` | 8 | 4, 8, 16 | Batch processing threads |
| `--batch-size` | 2048 | 1024, 2048, 4096 | Token batch size |
| `--ubatch-size` | 256 | 128, 256, 512 | Micro-batch size |
| `--cache-ram` | 4096 | 2048, 4096, 8192 | KV cache RAM limit |
| `--cache-reuse` | 512 | 256, 512, 1024 | KV chunk reuse threshold |
| `-ctk/-ctv` | q8_0 | q4_0, q5_0, q8_0 | KV cache quantization |

**Steps:**
1. For each top config, baseline the current params
2. Vary one parameter at a time, measure gen_t/s and pp_t/s
3. Keep changes that improve gen_t/s by >5% without degrading pp_t/s by >10%
4. Produce final optimised config for each model variant

**Tests:**
- [ ] Each parameter change measured independently
- [ ] Final optimised configs documented with all params
- [ ] No crashes during tuning

**Dependencies:** Phase 1 complete.

---

### Phase 3: Comparative Analysis

**What:** Produce a side-by-side comparison report with recommendations.

**Steps:**
1. Compile Phase 1+2 results into comparison table
2. Identify: fastest config, most VRAM-efficient, best balance
3. Flag: which quantization variant wins for consolidation workload
4. Recommend: production config (model + params) for Arc A380

**Output:** Update `/home/chief/llm-wiki/00-prompt-handoff/13-06-2026_lfm-quant-moe-sycl-bench_531c5d.md` with results table.

**Tests:**
- [ ] Comparison table includes all 8 base configs + optimised variants
- [ ] Clear recommendation with evidence
- [ ] Caveats documented (what wasn't tested, unknowns)

**Dependencies:** Phase 2 complete.

---

## Constraints

- **No full pipeline tests** — raw inference speeds only (pp_t/s and gen_t/s)
- **No consolidation prompt** — use simple system + user prompt for speed measurement
- **Port 18095 only** — do not touch port 8091 (Qwen occupied)
- **Arc A380 only for SYCL** — no RTX 3090 testing
- **3 runs per config** — discard first (cold cache), average remaining 2
- **Max 512 output tokens** — keep generation phase bounded
- **~4096 input tokens** — standardised prompt size across all configs

---

## Success Criteria

- [ ] All 8 base configs benchmarked without crashes
- [ ] Results saved to `/home/chief/llm_bench_lfm_matrix.json`
- [ ] Top 2 configs optimised with parameter tuning
- [ ] Side-by-side comparison produced
- [ ] Clear recommendation: which quant variant + config for production
- [ ] Raw timing logs preserved in `/tmp/lfm_bench_*.log`

---

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `/home/chief/llm_bench_lfm_matrix.json` | Benchmark results matrix |
| Create | `/tmp/lfm_bench_*.log` | Raw server timing logs per config |
| Modify | `13-06-2026_lfm-quant-moe-sycl-bench_531c5d.md` | Append results table after completion |

---

## Clarification Needed

**Issue:** Should CPU AVX512 build be included in the benchmark matrix (configs I-J)?

**Context:** CPU build completed but test was aborted (took too long). May provide useful comparison point for MoE performance.

**Options:**
- A: Skip CPU — focus on SYCL optimisation (faster iteration)
- B: Include 2 CPU configs (IQ4_NL full + partial) for reference

**Recommendation:** A — skip CPU for now. SYCL is the production target. CPU can be Phase 4 if time permits.

**Blocking:** No — proceed with SYCL-only matrix (8 configs).
