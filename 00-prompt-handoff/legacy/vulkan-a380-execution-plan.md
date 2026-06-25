# Vulkan Build Plan: Intel Arc A380 + LFM2.5-8B-A1B-UD-Q3_K_XL

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `531c5d` |
| Entity type | `handoff` |
| Short description | Build and benchmark llama.cpp Vulkan backend for Q3_K_XL MoE on Arc A380 |
| Status | `proposed` |
| Generated | 14-06-2026 |

---

## System State (Verified)

| Component | Status | Details |
|-----------|--------|---------|
| OS | ✅ Ubuntu 24.04.4 LTS | Kernel 6.17.0-35-generic |
| GPU | ✅ Intel Arc A380 (DG2) | `0b:00.0`, Gigabyte, i915 driver |
| Vulkan | ✅ GPU id 2 detected | `Intel(R) Arc(tm) A380 Graphics (DG2)` |
| ANV Driver | ✅ `libvulkan_intel.so` | Vulkan 1.4, Mesa 25.2.8 |
| oneAPI | ✅ 2026.0 | icx/icpx at `/opt/intel/oneapi/compiler/2026.0/bin/` |
| glslc | ✅ Installed | `/home/chief/.local/bin/glslc` |
| spirv-headers | ✅ 1.6.1 | Ubuntu package |
| spirv-tools | ✅ 2025.1 | Ubuntu package |
| libvulkan-dev | ✅ 1.3.275 | Ubuntu package |
| cmake | ✅ 3.28.3 | |
| llama.cpp | ✅ commit 4988f6e | `~/Coding-Projects/7-council/llama-forks/arc-llm/` |
| Model | ✅ Q3_K_XL 3.8GB | `~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf` |

**All prerequisites are satisfied. Zero blocking dependencies.**

---

## Step 1: Build Vulkan Backend

```bash
cd ~/Coding-Projects/7-council/llama-forks/arc-llm/

# Clean build directory
rm -rf build-vulkan

# Configure - Vulkan only, Release mode
cmake -B build-vulkan \
  -DGGML_VULKAN=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -j$(nproc)

# Build
cmake --build build-vulkan --config Release -j$(nproc)
```

**Expected duration:** 5-10 minutes (Vulkan compiles faster than SYCL since no SPIR-V JIT at build time)

**Expected output:**
```
-- Found Vulkan: /usr/lib/x86_64-linux-gnu/libvulkan.so
-- ggml_vulkan: building Vulkan backend
...
[100%] Built target llama-bench
[100%] Built target llama-server
```

**Verification:**
```bash
# Check binaries exist
ls -la build-vulkan/bin/llama-{server,bench,cli}

# Quick smoke test - does it detect the A380?
GGML_VK_VISIBLE_DEVICES=2 ./build-vulkan/bin/llama-cli \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  -ngl 99 -n 1 -p "test" 2>&1 | head -20
```

Expected detection line:
```
ggml_vulkan: Using Intel(R) Arc(tm) A380 Graphics (DG2) (Intel open-source Mesa driver) | uma: 0 | fp16: 1 | warp size: 32
```

---

## Step 2: Smoke Test (Model Load + 1 Token)

```bash
GGML_VK_VISIBLE_DEVICES=2 ./build-vulkan/bin/llama-cli \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  -ngl 99 \
  -n 4 \
  -c 2048 \
  -t 8 \
  -p "Hello, this is a test." \
  2>&1 | tee /tmp/vulkan-smoke-test.log
```

**Pass criteria:**
- [ ] No crash / segfault
- [ ] Model loads fully to GPU0 (Vulkan0)
- [ ] All 37/37 layers offloaded (MoE model has many expert layers)
- [ ] Coherent output (not random tokens)
- [ ] VRAM usage ~4-5GB (from logs)

**If random output appears:**
```bash
# FP16 workaround (known issue on some Intel Arc + Mesa combos)
GGML_VK_VISIBLE_DEVICES=2 GGML_VK_DISABLE_F16=1 ./build-vulkan/bin/llama-cli \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  -ngl 99 -n 4 -c 2048 -t 8 -p "Hello, this is a test."
```

---

## Step 3: Benchmark Suite

### 3A. llama-bench (standardized)

```bash
# Standard benchmark
GGML_VK_VISIBLE_DEVICES=2 ./build-vulkan/bin/llama-bench \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  -ngl 99 \
  -fa 0,1 2>&1 | tee /tmp/vulkan-bench-q3k-standard.log
```

This produces the standard table with pp512, tg128, pp4096, tg256, etc.

### 3B. Server Mode Benchmark (realistic workload)

```bash
# Start server
GGML_VK_VISIBLE_DEVICES=2 ./build-vulkan/bin/llama-server \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  --port 18095 \
  -ngl 99 \
  -c 4096 \
  -t 8 \
  --threads-batch 8 \
  --batch-size 2048 \
  --ubatch-size 256 \
  2>&1 | tee /tmp/vulkan-server-q3k.log &
SERVER_PID=$!

# Wait for warmup
sleep 120

# Send benchmark prompt (4096-token input, 512 output tokens)
curl -s http://localhost:18095/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "LFM2.5-8B-A1B-UD-Q3_K_XL",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "$(head -c 16000 ~/llm-wiki/00-prompt-handoff/trace-85a9cdb8.md 2>/dev/null || echo "Explain the architecture of Mixture of Experts models in detail, including routing mechanisms, expert capacity, and training strategies.")"}
    ],
    "max_tokens": 512,
    "temperature": 0.3
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
usage = data.get('usage', {})
print(f'Input tokens: {usage.get(\"prompt_tokens\", \"?\")}')
print(f'Output tokens: {usage.get(\"completion_tokens\", \"?\")}')
print(f'Total time: {data.get(\"timings\", {}).get(\"total\", \"?\")}')
" 2>&1 | tee /tmp/vulkan-server-bench.log

# Cleanup
kill $SERVER_PID 2>/dev/null
```

### 3C. Offload Comparison (full vs partial)

```bash
for ngl in 99 64 32 0; do
  echo "=== -ngl $ngl ==="
  GGML_VK_VISIBLE_DEVICES=2 ./build-vulkan/bin/llama-bench \
    -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
    -ngl $ngl \
    -fa 0 2>&1 | grep -E "model|pp512|tg128"
  echo ""
done | tee /tmp/vulkan-bench-q3k-ngl-sweep.log
```

### 3D. FP16 vs FP32 Comparison

```bash
for f16_flag in "" "GGML_VK_DISABLE_F16=1"; do
  label="${f16_flag:-FP16 (default)}"
  echo "=== $label ==="
  $f16_flag GGML_VK_VISIBLE_DEVICES=2 ./build-vulkan/bin/llama-bench \
    -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
    -ngl 99 \
    -fa 0 2>&1 | grep -E "model|pp512|tg128"
  echo ""
done | tee /tmp/vulkan-bench-q3k-fp16-compare.log
```

---

## Step 4: Cross-Backend Comparison (Vulkan vs SYCL)

Run the same benchmark on both backends for direct comparison:

```bash
echo "=== SYCL (existing build) ==="
ONEAPI_DEVICE_SELECTOR="level_zero:0" \
  ./build-sycl/bin/llama-bench \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  -ngl 99 \
  -fa 0 2>&1 | grep -E "model|pp512|tg128"

echo ""
echo "=== Vulkan ==="
GGML_VK_VISIBLE_DEVICES=2 \
  ./build-vulkan/bin/llama-bench \
  -m ~/models/LFM2.5-8B-A1B-UD-Q3_K_XL.gguf \
  -ngl 99 \
  -fa 0 2>&1 | grep -E "model|pp512|tg128"
```

Repeat for IQ4_NL and Q4_K_XL variants too.

---

## Step 5: Save Results

```bash
# Consolidate all results
cat > /home/chief/llm_bench_vulkan_q3k_results.json << 'EOF'
{
  "model": "LFM2.5-8B-A1B-UD-Q3_K_XL",
  "model_size_gb": 3.8,
  "backend": "Vulkan",
  "gpu": "Intel Arc A380 (DG2)",
  "vulkan_device": 2,
  "driver": "Mesa 25.2.8 ANV",
  "llama_cpp_commit": "4988f6e",
  "timestamp": "2026-06-14T00:00:00Z",
  "results": {
    "standard_bench": "see /tmp/vulkan-bench-q3k-standard.log",
    "ngl_sweep": "see /tmp/vulkan-bench-q3k-ngl-sweep.log",
    "fp16_compare": "see /tmp/vulkan-bench-q3k-fp16-compare.log",
    "cross_backend": "see /tmp/vulkan-sycl-comparison.log",
    "server_bench": "see /tmp/vulkan-server-bench.log"
  }
}
EOF
```

---

## Expected Results (Estimates)

Based on community data (A380 SYCL: 23.8 tg128 for 7B Q4_0, A770 Vulkan 6.8x faster on MoE):

| Metric | Q3_K_XL Vulkan (estimated) | Q3_K_XL SYCL (estimated) |
|--------|---------------------------|--------------------------|
| pp512 | 400-600 t/s | 400-600 t/s (similar) |
| tg128 | 18-30 t/s | 15-25 t/s |
| MoE expert dispatch | Full GPU (mul_mat_id) | Full GPU (Q3_K kernel exists) |
| Model load | ~2 min | ~2 min |
| VRAM usage | ~4.5 GB | ~4.5 GB |

**Key unknown:** Whether Vulkan + Q3_K on A380 matches or exceeds SYCL + Q3_K. Both have MoE kernel support for Q3_K, so the delta should be smaller than the IQ4_NL gap.

---

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FP16 produces random output | Medium | High | `GGML_VK_DISABLE_F16=1` fallback |
| Vulkan build fails (missing deps) | Low | Medium | All deps verified present |
| MoE performance still poor | Low | High | Vulkan iterates all quant types for mul_mat_id |
| VRAM OOM with KV cache | Low | Medium | Q3_K_XL is 3.8GB, 2GB headroom |
| Context degradation over long prompts | Medium | Medium | Test with -c 4096 and -c 8192 |

---

## Files Created/Modified

| Action | File | Purpose |
|--------|------|---------|
| Create | `build-vulkan/` | Vulkan build directory |
| Create | `/tmp/vulkan-smoke-test.log` | Smoke test output |
| Create | `/tmp/vulkan-bench-q3k-*.log` | Benchmark logs |
| Create | `/tmp/vulkan-server-*.log` | Server benchmark logs |
| Create | `/home/chief/llm_bench_vulkan_q3k_results.json` | Consolidated results |
| Modify | `vulkan-intel-arc-research.md` | Update with actual results |

---

## Decision Points After Testing

1. **If Vulkan tg128 > SYCL tg128 by >10%:** Use Vulkan as primary backend for all models
2. **If within 10%:** Use Vulkan for IQ4_NL (only option with MoE), SYCL for Q3_K/Q4_K (similar performance, less overhead)
3. **If Vulkan < SYCL:** Use SYCL for Q3_K/Q4_K, Vulkan only for IQ4_NL
4. **If FP16 broken:** Document `GGML_VK_DISABLE_F16=1` as required; re-benchmark with FP32

---

## Sources

- [GitHub Issue #19918](https://github.com/ggml-org/llama.cpp/issues/19918) - Vulkan 6.8x faster on MoE (A770)
- [GitHub Issue #22413](https://github.com/ggml-org/llama.cpp/issues/22413) - SYCL brutal on Battlemage
- [GitHub Discussion #23313](https://github.com/ggml-org/llama.cpp/discussions/23313) - SYCL benchmark table (A380 data)
- [r/IntelArc AUR package thread](https://www.reddit.com/r/IntelArc/comments/1tlcvbi/) - Vulkan faster than SYCL on Linux + Mesa
- [sbonner0.github.io](https://sbonner0.github.io/posts/intel-arc/) - Arch Linux Vulkan setup guide
- [llama.cpp docs/build.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md) - Official build instructions
