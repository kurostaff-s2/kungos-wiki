# Vulkan Setup Research for Intel Arc (A380) — LLM Inference

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `531c5d` |
| Entity type | `handoff` |
| Short description | Research Vulkan backend as alternative to SYCL for LFM MoE benchmarking on Intel Arc A380 |
| Status | `draft` |
| Generated | 14-06-2026 |
| Sources | GitHub issues #19918, #22413, discussions #12570, #10879, #23313; blog posts; llama.cpp source |

---

## Executive Summary

**Vulkan is a viable (and often superior) alternative to SYCL for Intel Arc GPUs running LLM inference via llama.cpp.** For MoE models specifically, Vulkan has a critical advantage: it supports `mul_mat_id` (MoE expert dispatch) for ALL quantization types including IQ4_NL, whereas SYCL's MoE dispatch hard-codes a switch that excludes IQ4_NL.

### Key Finding: MoE + IQ4_NL Gap

| Backend | IQ4_NL MoE kernel | Token gen (MoE) |
|---------|-------------------|-----------------|
| **SYCL** | ❌ NOT in `ggml_sycl_mul_mat_vec_q_id()` switch | Falls back to slow generic path (~0.56 t/s) |
| **Vulkan** | ✅ Iterates `GGML_TYPE_COUNT` — all quants supported | Full GPU acceleration expected |

The SYCL MoE dispatch at `mmvq.cpp` supports: Q4_0, Q4_1, Q5_0, Q5_1, Q8_0, Q2_K, Q3_K, Q4_K, Q5_K, Q6_K, MXFP4, NVFP4. **IQ4_NL is absent.**

---

## Performance Evidence

### Issue #19918: A770 MoE — Vulkan 6.8x faster than SYCL

| Metric | SYCL | Vulkan | Ratio |
|--------|------|--------|-------|
| Prompt processing | 600 t/s | 1100 t/s | 1.8x |
| Token generation | **10 t/s** | **68 t/s** | **6.8x** |
| Model | Qwen3.5-35B-A3B (MoE) | | |

**Caveat:** On Linux with PCIe 3.0 + dual A770, one user reported SYCL staying stable at 25 t/s while Vulkan degraded to 10 t/s over context. Hardware/OS dependent.

### Issue #22413: Battlemage (B50/B70) — SYCL "brutally bad"

- B50/B70 on Linux: SYCL performance near CPU speed on some systems
- Same user: "best results out of llama.cpp-vulkan on Windows"
- Vulkan has "received more love" (per issue reporter)
- SYCL developer (NeoZhangJianyu) acknowledges: "SYCL backend is slower than Vulkan is the truth"

### Discussion #23313: SYCL Benchmark Table (May-June 2026)

Selected data points for Arc A380 (the card in question):

| Model | GPU | FP16/FA | pp512 | tg128 |
|-------|-----|---------|-------|-------|
| llama-2-7b.Q4_0 | Arc A380 | fp16/0 | 495 t/s | 23.8 t/s |
| llama-2-7b.Q4_0 | Arc A380 | fp16/1 | 363 t/s | 25.6 t/s |
| llama-2-7b.Q4_0 | Arc A380 | fp32/0 | 226 t/s | 23.8 t/s |

For reference, A770 SYCL: 59-67 t/s tg128. B70 SYCL: 72-106 t/s tg128.

---

## Vulkan Setup Guide

### Prerequisites (Ubuntu/Debian)

```bash
# 1. Install Intel GPU driver (Mesa-based, open source)
sudo apt install intel-media-va-driver-non-free libmfx1 libvulkan1

# 2. Install Vulkan development dependencies
sudo apt-get install libvulkan-dev glslc spirv-headers

# 3. Verify Vulkan is working
vulkaninfo | grep -i "intel\|arc\|device"
# Should show: Intel(R) Arc(tm) A380 Graphics (DG2)
```

### Build llama.cpp with Vulkan

```bash
cd /path/to/llama.cpp

# Clean build
rm -rf build-vulkan

# Configure
cmake -B build-vulkan -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release

# Build
cmake --build build-vulkan --config Release -j$(nproc)
```

### Run with Vulkan

```bash
# Basic inference
./build-vulkan/bin/llama-cli -m "PATH_TO_MODEL" -p "Hello" -ngl 99

# Server mode
./build-vulkan/bin/llama-server -m "PATH_TO_MODEL" -ngl 99 --port 18095

# Benchmark
./build-vulkan/bin/llama-bench -m "PATH_TO_MODEL" -ngl 99
```

### Expected Vulkan Detection Output

```
ggml_vulkan: Found 1 Vulkan devices:
ggml_vulkan: 0 = Intel(R) Arc(tm) A380 Graphics (DG2) (Intel open-source Mesa driver) | uma: 0 | fp16: 1 | warp size: 32 | matrix cores: none
```

### Arch Linux Specific

```bash
# AUR packages for Vulkan
yay -S vulkan-intel vulkan-headers vulkan-icd-loader glslang spirv-headers

# Then same cmake build as above
```

---

## Known Issues & Workarounds

### 1. FP16 Random Output (Intel Arc, older platforms)

**Symptom:** Model generates random/gibberish tokens with Vulkan + FP16.

**Fix:** `GGML_VK_DISABLE_F16=1 ./build/bin/llama-cli ...`

**Status:** Fixed in recent llama.cpp (March 2026). Try without the flag first; fall back if needed.

Source: [sbonner0.github.io](https://sbonner0.github.io/posts/intel-arc/)

### 2. Vulkan Performance Degradation Over Context

**Symptom:** Token generation speed drops significantly as context grows (e.g., 26 t/s → 10 t/s after 200 tokens).

**Observed on:** Linux + dual A770 + PCIe 3.0

**Possible causes:** Shared memory pressure, driver bugs

**Workaround:** None confirmed. May be hardware/driver specific.

### 3. Windows VRAM Fragmentation

**Symptom:** Can't use more than ~21GB of 32GB VRAM without crashes (B70, Windows).

**Status:** Known issue, Windows-specific. Not applicable to Linux.

### 4. ANV Driver vs Intel Proprietary

- **Mesa ANV driver:** Open-source, works well with Vulkan on Intel Arc
- **Intel proprietary driver:** Less mature for Vulkan compute, better for SYCL/Level Zero
- **Recommendation:** Use Mesa ANV for Vulkan path

---

## Vulkan vs SYCL Decision Matrix

| Factor | Vulkan | SYCL |
|--------|--------|------|
| **MoE + IQ4_NL** | ✅ Full support | ❌ No kernel (falls back to slow path) |
| **MoE + Q4_K** | ✅ Full support | ✅ Full support |
| **Setup complexity** | Simple (apt install) | Complex (oneAPI toolkit, icx/icpx) |
| **FP16 support** | Good (fixed March 2026) | Good |
| **Flash Attention** | Supported | Supported (recently added) |
| **Performance trend** | Improving (more developer focus) | Declining (per SYCL maintainer) |
| **Commercial backing** | Community-driven | NeoZhangJianyu (individual contributor) |
| **Arc A380 tg128 (7B)** | ~24-26 t/s (estimated) | 23.8 t/s (measured) |
| **MoE tg (35B A3B)** | 68 t/s (A770) | 10 t/s (A770) |
| **Driver** | Mesa ANV (open source) | Level Zero (Intel proprietary) |
| **Multi-GPU** | GGML_VK_VISIBLE_DEVICES | ONEAPI_DEVICE_SELECTOR |

---

## Recommendation for LFM Benchmark

### Model Variants Available

| Variant | Size | MoE kernel (SYCL) | Fits A380 6GB VRAM? |
|---------|------|-------------------|---------------------|
| Q4_K_XL | 5.0 GB | ✅ Yes | Tight (little KV cache headroom) |
| Q3_K_XL | 3.8 GB | ✅ Yes | Comfortable (2GB for KV cache) |
| IQ4_NL | 4.1 GB | ❌ No (slow fallback) | OK but needs Vulkan for MoE |

### Primary Recommendation: Add Vulkan + Q3_K Configs

Given that IQ4_NL MoE is catastrophically slow on SYCL (0.56 t/s), add Vulkan configs to the benchmark. **Q3_K_XL is the sweet spot:** has SYCL MoE kernel, fits comfortably on VRAM, and is the smallest variant.

| Config | Model | Backend | -ngl | Notes |
|--------|-------|---------|------|-------|
| V1 | IQ4_NL | Vulkan | 99 | Full GPU, likely viable for MoE |
| V2 | IQ4_NL | Vulkan | 32 | Partial offload |
| V3 | IQ4_NL | Vulkan | 99 | + `GGML_VK_DISABLE_F16=1` if needed |
| V4 | Q4_K_XL | Vulkan | 99 | Compare vs SYCL baseline |
| V5 | Q3_K_XL | Vulkan | 99 | Smallest, most VRAM headroom |
| V6 | Q3_K_XL | Vulkan | 99 | + `GGML_VK_DISABLE_F16=1` if needed |

### Secondary: Keep SYCL as Reference

- SYCL still has value for Q4_K and Q3_K variants (where MoE kernel exists)
- Q3_K_XL (3.8GB) is the best SYCL candidate: MoE kernel supported + comfortable VRAM fit
- Vulkan may have context-dependent degradation (issue #19918)
- Running both backends provides complete picture

### Build Both Backends

```bash
# Vulkan build (simple)
cmake -B build-vulkan -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-vulkan --config Release -j$(nproc)

# SYCL build (existing, keep as-is)
# Already at build-sycl/
```

---

## Caveats

1. **No Vulkan MoE benchmark data for A380 specifically** — the 68 t/s figure is from A770. A380 has fewer Xe cores (8 vs 32) so expect proportionally lower throughput.

2. **FP16 may need disabling** — if random output appears, use `GGML_VK_DISABLE_F16=1`. This trades ~10-20% performance for correctness.

3. **Mesa driver version matters** — ensure `vulkaninfo` shows a recent Mesa version (24.x+). Older versions had shader compilation issues.

4. **VRAM constraints** — A380 has only 6GB. Q4_K_XL (5GB) leaves little headroom. IQ4_NL (4.1GB) fits better. Q3_K_XL (3.8GB) has the most headroom (~2GB for KV cache). Vulkan may have different memory overhead vs SYCL.

5. **MoE pipeline fusion** — Vulkan uses pipeline fusion patterns (topk_moe_early_softmax, etc.) which may behave differently than SYCL's direct kernel dispatch. Performance characteristics may vary.

---

## Source References

1. [GitHub Issue #19918](https://github.com/ggml-org/llama.cpp/issues/19918) — SYCL slower than Vulkan on MoE (A770)
2. [GitHub Issue #22413](https://github.com/ggml-org/llama.cpp/issues/22413) — Brutally bad SYCL on Battlemage
3. [GitHub Discussion #12570](https://github.com/ggml-org/llama.cpp/discussions/12570) — Current status of Intel Arc for llama.cpp
4. [GitHub Discussion #10879](https://github.com/ggml-org/llama.cpp/discussions/10879) — Vulkan performance scoreboard
5. [GitHub Discussion #23313](https://github.com/ggml-org/llama.cpp/discussions/23313) — SYCL performance data table
6. [sbonner0.github.io](https://sbonner0.github.io/posts/intel-arc/) — Arch Linux Arc A750 setup guide (Vulkan)
7. [llama.cpp docs/build.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md) — Official Vulkan build instructions
8. [llama.cpp ggml-vulkan.cpp](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-vulkan/ggml-vulkan.cpp) — Vulkan backend source (mul_mat_id support)
9. [llama.cpp ggml-sycl/mmvq.cpp](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-sycl/mmvq.cpp) — SYCL MoE dispatch (IQ4_NL gap)
