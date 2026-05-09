---
tags: [hardware, llm, inference, optimization, llama-cpp, nvidia, amd]
created: 2026-05-05
updated: 2026-05-05T00:45
sources: [llama.cpp/build/CMakeCache.txt, nvidia-smi, lscpu, /sys/devices/system/cpu/]
related: [[local-ai-stack]], [[ADR-003-llama-cpp]], [[ADR-001-local-llm]]
status: active
---

# Local Hardware

## Summary

Local LLM inference stack on a single workstation. llama.cpp (CUDA) serving Qwen3.6-27B-Q4 on RTX 3090. One optimization opportunity: CPU governor (powersave instead of performance). GPU power limit is a hard ceiling (350 W max) — not actionable.

## Hardware Inventory

### GPU — NVIDIA RTX 3090

| Parameter | Current | Max / Spec | Notes |
|---|---|---|---|
| Architecture | Ampere | — | Compute Capability 8.6 |
| VRAM | 24 GB (24,576 MiB) | — | 21.6 GB used by model, ~2.5 GB free for KV cache |
| Graphics Clock | **1485 MHz** | 2100 MHz | Throttled by power cap (see Issues) |
| Memory Clock | 9501 MHz | 9751 MHz | Near max |
| Power Draw | ~330 W avg | 350 W limit | **Hitting power ceiling** |
| Power Limit | 350 W (default) | 350 W (max configured) | Can raise to 375–400 W |
| Temperature | 73–75 °C | Target 83 °C, Slowdown 95 °C | Thermal headroom: 8–10 °C |
| Fan Speed | 81 % | — | Cooling adequate |
| Performance State | P2 | P0 (max) | Not in P0 due to power cap |
| PCIe | Gen 4 x16 | Gen 4 x16 | Full bandwidth |
| Persistence Mode | Enabled | — | Good — faster startup |
| Driver | 595.71.05 | — | CUDA 13.2 |

### CPU — AMD Ryzen 7 7700

| Parameter | Value | Notes |
|---|---|---|
| Cores / Threads | 8 / 16 | Matches `--threads 16` in llama-server |
| Base Clock | 3800 MHz | — |
| Max Turbo | 5393 MHz | — |
| Governor | **powersave** (all cores) | Should be `performance` for inference |
| Instruction Sets | AVX, AVX2, AVX-512 (F, BW, VL, VBMI, VNNI, BF16), FMA, F16C, BMI2 | Full support |
| L1d / L1i Cache | 256 KiB each | — |
| L2 Cache | 8 MiB (8 instances) | — |
| L3 Cache | 32 MiB (shared) | Good for CPU-side weight caching |

### System

| Parameter | Value | Notes |
|---|---|---|
| RAM | 93 GB DDR | 74 GB available — plenty for CPU offloading |
| Swap | 8 GB (file, priority -2) | Unused — safety net only |
| Storage | TEAM TM8FPK001T 1TB NVMe | Budget-tier (~1000–1200 MB/s). Affects model load time only. |
| NUMA | Single node | — |

## llama.cpp Build Configuration

| Setting | Value | Assessment |
|---|---|---|
| Build Type | Release (`-O3`) | ✅ |
| Version | `b9029-2-gbf76ac77b` | ✅ Recent |
| GGML_CUDA | ON | ✅ |
| GGML_NATIVE | ON | ✅ `-march=native` covers AVX2/AVX-512/FMA/F16C |
| GGML_CUDA_GRAPHS | ON | ✅ Reduced kernel launch overhead |
| GGML_CUDA_FA | ON | ✅ Flash Attention |
| GGML_CUDA_NCCL | ON | ✅ Multi-GPU support compiled in |
| GGML_CUDA_COMPRESSION_MODE | **`size`** | ⚠️ Smallest binary — `speed` or `balance` would be faster |
| GGML_CUDA_FA_ALL_QUANTS | OFF | ⚠️ Flash attention not compiled for all quant types |
| GGML_CUDA_FORCE_MMQ | OFF | ✅ Auto-selects best matmul path |
| GGML_CUDA_NO_VMM | OFF | ✅ Virtual Memory Manager enabled |
| GGML_OPENMP | ON | ✅ Multi-threading for CPU fallback |

## Running Server Configurations

Two server configs optimized for different use cases. Run on separate ports.

### q8_0 — Daily coding (port 8001)

Best for responsive multi-turn sessions. 64K context, full q8_0 KV quality.

```bash
/home/chief/llama.cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8001 \
  --model /home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf \
  --alias qwen3.6-27B-Q4 \
  --jinja \
  --chat-template-kwargs {"preserve_thinking":true} \
  --ctx-size 65536 --fit on --fit-target 1024 \
  --flash-attn on --no-mmap --mlock \
  --cont-batching -np 1 -b 2048 -ub 512 \
  --threads 16 --threads-batch 16 \
  --ctx-checkpoints 8 --checkpoint-every-n-tokens 8192 --cache-reuse 256 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0 \
  --presence-penalty 0.0 --repeat-penalty 1.0 \
  --reasoning on --reasoning-budget 16384
```

| Parameter | Value | Notes |
|---|---|---|
| Context Size | 65,536 tokens | Sweet spot: ~65s PP/turn at full context |
| Batch Size | 2048 / ub 512 | Larger batch = faster PP, smaller ub = less VRAM pressure during gen |
| KV Cache Type | q8_0 | ✅ Highest precision |
| Context Checkpoints | 8 every 8192 tokens | Reduced from 16 — don't persist across turns (SWA invalidation) |
| VRAM | ~21.7 GB | +2.9 GB headroom |

### turbo4 hybrid — Deep refactoring (port 8002)

50% more context for sessions with many open files. K=q8_0, V=turbo4.

```bash
GGML_CUDA_GRAPH_OPT=1 /home/chief/llama-cpp-turboquant/build/bin/llama-server \
  --host 127.0.0.1 --port 8002 \
  --model /home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf \
  --alias qwen3.6-27B-Q4-turbo \
  --jinja \
  --chat-template-kwargs {"preserve_thinking":true} \
  --ctx-size 96512 --fit on --fit-target 1024 \
  --flash-attn on --no-mmap --mlock \
  --cont-batching -np 1 -b 2048 -ub 512 \
  --threads 16 --threads-batch 16 \
  --ctx-checkpoints 8 --checkpoint-every-n-tokens 12288 --cache-reuse 256 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 \
  -ctk q8_0 -ctv turbo4 \
  --presence-penalty 0.0 --repeat-penalty 1.0 \
  --reasoning on --reasoning-budget 16384
```

| Parameter | Value | Notes |
|---|---|---|
| Context Size | 96,512 tokens | ~96s PP/turn at full context |
| KV Cache | K=q8_0, V=turbo4 | ~5–10% slower per token, 50% more context |
| Context Checkpoints | 8 every 12,288 tokens | Larger interval (turbo4 KV is smaller) |
| VRAM | ~22.4 GB | +2.2 GB headroom |

### When to use which

| Scenario | Config | Reason |
|---|---|---|
| Daily coding, quick iterations | **q8_0 @ 64K** (port 8001) | Faster turns, better quality |
| Deep refactoring, many files | **turbo4 @ 96K** (port 8002) | More context for the session |
| Single-shot analysis (no turns) | Either at max ctx | Checkpoints work within single generation |

### Turn latency by context size

Every turn reprocesses the full context (SWA invalidates checkpoints between turns). PP speed ~1000 tok/s, gen speed ~35 tok/s.

| Context | PP time | +500 tok gen | +2K tok gen | Total (500t) | Total (2K) |
|---|---|---|---|---|---|
| 16K | 16s | 14s | 57s | 31s | 74s |
| 32K | 33s | 14s | 57s | 47s | 90s |
| **64K** (q8 config) | **66s** | 14s | 57s | **80s** | **123s** |
| **96K** (turbo config) | **96s** | 14s | 57s | **110s** | **153s** |
| 121K | 121s | 14s | 57s | 135s | 178s |

### Agentic coding session profile

Context grows as the agent reads files and makes changes. Each turn pays full PP cost.

| Session phase | Context | PP time | Gen (1.5K) | Total/turn |
|---|---|---|---|---|
| Setup + repo map | 8K | 8s | 43s | 51s |
| After 3 file reads | 18K | 18s | 43s | 61s |
| After plan + 2 edits | 30K | 30s | 43s | 73s |
| After review + fixes | 45K | 45s | 43s | 88s |
| Deep refactoring | 60K | 60s | 43s | 103s |
| Full session | 80K | 80s | 43s | 123s |

## Issues & Recommendations

### HIGH — GPU Power Limit Throttling (not actionable)

**Problem:** GPU power limit is at the stock 350 W default. The card hits this cap during inference and throttles graphics clocks down to ~1485 MHz from a potential 2100 MHz. This is a **~30–40% throughput loss**.

**Status:** ❌ **No-go** — hardware does not support raising the power limit beyond 350 W (max configured = 350 W). Cannot bump to 375–400 W. This throttling is permanent on this card.

**Evidence:**
- `SW Power Cap: Active` in clocks event reasons
- Graphics clock 1485 MHz vs max 2100 MHz
- Temperature 75 °C vs target 83 °C — thermal headroom exists
- Average power draw 330 W — consistently near limit

**Expected impact:** N/A — cannot be resolved without different hardware. Accept ~30-40% throughput loss as a hard ceiling on this card.

### MEDIUM — CPU Governor on `powersave`

**Problem:** All 8 cores are on `powersave` governor. For a dedicated inference workload, this adds frequency transition latency.

**Evidence:**
- `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor` → all `powersave`
- Available governors: `performance powersave`
- AMD `hw_pstate` driver is in use (CPPC)

**Fix:**
```bash
# One-time
sudo cpupower frequency-set -g performance

# Persistent — systemd service or grub parameter
# Add to /etc/default/grub:
# GRUB_CMDLINE_LINUX_DEFAULT="... cpufreq.default_governor=performance"
# Then: sudo update-grub && sudo reboot
```

**Expected impact:** Lower latency on CPU-bound phases (batch preprocessing, KV cache operations on CPU).

### LOW — CUDA Compression Mode = `size`

**Problem:** `GGML_CUDA_COMPRESSION_MODE` is set to `size` on **both** builds (main llama.cpp and turboquant). This tells nvcc (the CUDA compiler) to generate smaller binaries by skipping some inlining and optimization passes. The kernels run slower — more indirect calls, less register usage.

| Mode | Binary size | Kernel speed | What it does |
|---|---|---|---|
| `size` | Smaller (~8.9 MB server) | Slower | Fewer optimizations, less inlining |
| `speed` | Larger (~15–20 MB server) | Faster | Aggressive inlining, unrolling, more registers |
| `balance` | Medium | Medium | Middle ground |

CUDA kernels are compiled at build time into PTX/SASS. On a dev machine with unlimited disk, `speed` is always the right choice. The binary being bigger is nothing, but kernel execution can be noticeably faster — especially for the small kernels that run every token (dequantize, matmul, attention).

**Fix:** Rebuild both with `-DGGML_CUDA_COMPRESSION_MODE=speed`.

```bash
# Main llama.cpp
cd /home/chief/llama.cpp/build
cmake .. -DGGML_CUDA=ON -DGGML_CUDA_COMPRESSION_MODE=speed -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Turboquant
cd /home/chief/llama-cpp-turboquant/build
cmake .. -DGGML_CUDA=ON -DGGML_CUDA_COMPRESSION_MODE=speed -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

**Expected impact:** Faster CUDA kernel execution at cost of larger binary (~100–200 MB additional). Probably the single biggest performance gain available without hardware changes.

### LOW — Sampling Params for Code Generation

**Problem:** Temperature 0.6 and top-k 20 are tuned for general chat, not code generation.

**Recommended for code:**
- `--temp 0.3` (more deterministic)
- `--top-k 10` (narrower candidate set)
- `--top-p 0.9` (slightly tighter)
- Keep `--min-p 0.05`

**Note:** This is a per-session change, not a hardware issue. Consider separate server instances or dynamic parameter switching.

### INFO — No Systemd Service

The llama-server is started manually (PID 19900). No systemd unit file exists. Consider creating one for auto-restart on crash and easier management.

### INFO — Budget NVMe

TEAM TM8 is a budget-tier NVMe (~1000–1200 MB/s). Only affects model load time at startup (one-time, ~10–15 seconds for 17 GB model). No impact on inference throughput since model is in VRAM.

## llama-cpp-turboquant Build

Fork of llama.cpp with TurboQuant KV cache quantization (turbo2/3/4). Same base as main llama.cpp but with additional low-bit KV cache formats.

| Setting | Value | vs main llama.cpp |
|---|---|---|
| Version | `feature-turboquant-kv-cache-b9066-11a241d` | Same base + turboquant fork |
| GGML_CUDA_COMPRESSION_MODE | `size` | ⚠️ Same issue — rebuild with `speed` |
| **GGML_CUDA_FA_ALL_QUANTS** | **ON** | ✅ **Better** — main has this OFF |
| GGML_CUDA_GRAPHS | ON | ✅ Same |
| GGML_CUDA_FA | ON | ✅ Same |
| GGML_NATIVE | ON | ✅ Same |
| Binary size | 8.9 MB | — |

### TurboQuant KV Cache Formats

| Type | Block | Bytes/128 values | Bits/value | Compression vs fp16 | KV per token |
|---|---|---|---|---|---|
| **q8_0** | 32 | — | 8.0 | 1× (baseline) | **256 KiB** |
| **turbo4** | 128 | 68 | 4.25 | 3.8× | **136 KiB** |
| q4_0 | 32 | 18 | 5.625 | 2.8× | 144 KiB |
| turbo3 | 128 | 14 | 3.5 | 4.6× | 28 KiB |
| turbo2 | 128 | 10 | 2.5 | 6.4× | 20 KiB |

turbo4 uses **WHT (Walsh-Hadamard Transform) rotation + 4-bit PolarQuant** with 16 optimal centroids, nibble-packed. CUDA dequantize kernels and FA template instances are compiled for all turbo× cross-types.

### Performance Impact vs plain llama.cpp

With `-ctk q8_0 -ctv turbo4` (hybrid K=q8_0, V=turbo4):

| Phase | Impact | Why |
|---|---|---|
| **Prompt processing (pp)** | ~5–10% slower | WHT rotation + PolarQuant encode on V cache per token batch |
| **Token generation** | ~5–10% slower | turbo4 dequant on each new token vs q8_0 simple scale |
| **Flash attention** | Same or faster | `FA_ALL_QUANTS=ON` — dedicated turbo4↔q8_0 FA kernels |

The trade-off: ~5–10% per-token slowdown to get significantly larger context within the same VRAM budget.

### Context scaling with checkpoints

Context checkpoints let llama.cpp evict old KV cache between save points. The KV cache only holds tokens since the last checkpoint, not the full context. This is why 121K+ context fits on 24 GB **within a single request**.

| Config | KV Type | Checkpoints | Interval | Max Context | VRAM | Headroom |
|---|---|---|---|---|---|---|
| q8_0 (64K) | q8_0 + q8_0 | 8 | 8,192 | 65K | ~21.7 GB | +2.9 GB |
| q8_0 (121K) | q8_0 + q8_0 | 16 | 8,192 | 121K | ~22.8 GB | +1.8 GB |
| turbo4 hybrid (96K) | q8_0 + turbo4 | 8 | 12,288 | 96K | ~22.4 GB | +2.2 GB |
| turbo4 hybrid (163K) | q8_0 + turbo4 | 16 | 10,240 | 163K | ~22.8 GB | +1.8 GB |
| Full turbo4 (245K) | turbo4 + turbo4 | 16 | 15,360 | 245K | ~22.8 GB | +1.8 GB |

### ⚠️ Qwen3 SWA checkpoint invalidation (critical)

**Observed behavior:** Qwen3's hybrid attention (sliding window + global layers) **invalidates all checkpoints between API calls**. Every new conversation turn triggers:

```
forcing full prompt re-processing due to lack of cache data
(likely due to SWA or hybrid/recurrent memory)
erased invalidated context checkpoint (pos_min = ..., n_tokens = ..., size = 149.626 MiB)
```

**What this means:**
- Checkpoints work **within a single generation** (VRAM management during long reasoning)
- Checkpoints do **NOT persist across turns** — every new request reprocesses the entire context from scratch
- Effective checkpoint count for conversations: **0**
- At 100K context, every turn costs ~100 seconds of prompt processing before generation starts
- The original crash at 26.5K was likely a transient VRAM spike during checkpoint creation in a full reprocess

**Impact on turbo4 configs:** The turbo4 hybrid (`-ctk q8_0 -ctv turbo4`) won't solve this — it's an architectural limitation of Qwen3's SWA, not a KV cache format issue.

**Workarounds:**
- Keep conversation context short (under 30K) for responsive multi-turn use
- Use single long generations (codebase analysis, document processing) where checkpoints help
- `--cache-reuse` helps if the same prompt prefix repeats across requests
- See: [llama.cpp PR #13194](https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)

## Benchmark Reference Points

| Metric | Current (estimated) | Theoretical (if power limit were raiseable) |
|---|---|---|
| GPU graphics clock | 1485 MHz | ~1800–2000 MHz sustained |
| Power utilization | 330/350 W (94%) | 330/375+ W (88%+) |
| Tokens/sec (generation) | ~25–35 tok/s | ~35–50 tok/s |
| Batch processing | Baseline | ~20–30% faster |

> ⚠️ **Theoretical column is aspirational only** — power limit cannot be raised on this card. Current numbers are the hard ceiling. Right-sized upgrade path: RTX 4090 (450W, 32 GB VRAM) or used 3090 Ti (same 350W but higher clocks).

## DFlash Speculative Decoding

### What is DFlash?

**DFlash** = *Block Diffusion for Flash Speculative Decoding*

| Field | Detail |
|---|---|
| Paper | [arXiv:2602.06036](https://arxiv.org/abs/2602.06036) (Feb 2026) |
| Authors | Jian Chen, Yesheng Liang, Zhijian Liu (z-lab) |
| GitHub | [z-lab/dflash](https://github.com/z-lab/dflash) — 2,503 ⭐ |
| Concept | Lightweight **block diffusion** draft model for speculative decoding |

**How it works:**
```
Traditional speculative decoding:  Draft model generates tokens sequentially (AR)
DFlash:                            Diffusion model generates ALL draft tokens in PARALLEL (single forward pass)
```

The DFlash model is a small diffusion-based draft model that:
1. Extracts context features from the target model
2. Generates a block of draft tokens in **one parallel pass** (not sequentially)
3. Target model verifies all draft tokens in parallel
4. **6x speedup** claimed, 2.5x faster than EAGLE-3

### DFlash Draft Models (z-lab/HuggingFace)

| Model | Size | Target | Downloads |
|---|---|---|---|
| `z-lab/Qwen3.6-27B-DFlash` | 3.5 GB | Qwen3.6-27B | 24,768 |
| `z-lab/Qwen3.6-35B-A3B-DFlash` | ~4 GB | Qwen3.6-35B-A3B | 49,120 |
| `z-lab/Qwen3.5-27B-DFlash` | 3.5 GB | Qwen3.5-27B | 25,109 |
| `z-lab/Qwen3.5-9B-DFlash` | 2.1 GB | Qwen3.5-9B | 11,583 |
| `z-lab/gpt-oss-20b-DFlash` | 1.6 GB | gpt-oss-20b | 2,076 |

All models are in **safetensors** format — need GGUF conversion for llama.cpp.

### Backend Compatibility

| Backend | DFlash Support | Status |
|---|---|---|
| **vLLM** | ✅ Native | `--speculative-config '{"method": "dflash"...}'` |
| **SGLang** | ✅ Native | `--speculative-algorithm DFLASH` |
| **Transformers** | ✅ Native | Python API |
| **MLX** (Apple) | ✅ Via fork | `bstnxbt/dflash-mlx` |
| **llama.cpp main** | ❌ Not supported | Diffusion draft not in upstream |
| **llama-cpp-turboquant** | ❌ Not supported | No diffusion support |
| **buun-llama-cpp** | ✅ **Native** | `--spec-type dflash` |

### buun-llama-cpp — DFlash-enabled llama.cpp fork

**[spiritbuun/buun-llama-cpp](https://github.com/spiritbuun/buun-llama-cpp)** — 552 ⭐, actively maintained (pushed 2026-05-05)

Fork of `TheTom/llama-cpp-turboquant` with **native DFlash support** integrated into llama.cpp. This is the **only** llama.cpp fork with working DFlash speculative decoding.

**Superset of turboquant** — includes everything from turboquant (turbo2/3/4, TCQ, flash attention) plus:
- DFlash block-diffusion speculative decoding
- DDTree verification (`--tree-budget`)
- Adaptive draft length + p_min confidence threshold
- Multi-slot DFlash support (`--dflash-max-slots`)
- GPU cross-attention ring buffer for hidden states
- Sliding window cap on drafter cross-attention (prevents VRAM growth)

#### DFlash CLI Arguments

```
--spec-type dflash                              # Enable DFlash speculative decoding
--spec-draft-model PATH  (or -md PATH)          # Path to DFlash draft model (GGUF)
--draft 16                                      # Max draft tokens (default)
--draft-min 0                                   # Min draft tokens
--tree-budget 0                                 # 0 = flat, >0 = DDTree verification
--dflash-max-slots 1                            # Concurrent slots with DFlash state
--draft-topk 1                                  # Top-K candidates per position
--spec-draft-model-replace TARGET DRAFT         # Token replacement rules
```

**Auto-safety:** The fork auto-caps `-b/-ub` to 256/64 when DFlash is active to prevent OOM on 24 GB GPUs. Override with `-ub 512 -b 2048` for ~30% faster prefill at +2-3 GB VRAM cost.

#### Build Instructions

```bash
git clone https://github.com/spiritbuun/buun-llama-cpp.git
cd buun-llama-cpp

cmake -B build \
  -DGGML_CUDA=ON \
  -DGGML_NATIVE=ON \
  -DGGML_CUDA_FA=ON \
  -DGGML_CUDA_FA_ALL_QUANTS=ON \
  -DGGML_CUDA_COMPRESSION_MODE=speed \
  -DCMAKE_BUILD_TYPE=Release

cmake --build build -j$(nproc)
```

#### Example DFlash Server Command

```bash
./build/bin/llama-server \
  -m /path/to/Qwen3.6-27B-Q4.gguf \
  --spec-type dflash \
  --spec-draft-model /path/to/Qwen3.6-27B-DFlash.gguf \
  --draft 16 \
  -ngl 99 -fa \
  -ctk q8_0 -ctv turbo4 \
  --ctx-size 96512 \
  --fit on --fit-target 1024 \
  --cont-batching -np 1 \
  --threads 16 --threads-batch 16 \
  --ctx-checkpoints 8 --checkpoint-every-n-tokens 12288 \
  --cache-reuse 256 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 \
  --reasoning on --reasoning-budget 16384
```

### VRAM Analysis for DFlash on RTX 3090

| Component | VRAM | Notes |
|---|---|---|
| Target model (Q4_K_XL) | ~13.5 GB | Weights on GPU |
| KV cache (96K, q8_0+turbo4) | ~5-6 GB | With checkpoints |
| DFlash draft model | ~3.5 GB | Needs GGUF conversion |
| Runtime / buffers | ~1-2 GB | Threads, CUDA graphs |
| **Total** | **~23-25 GB** | **Tight — may spill to RAM** |

Current usage without DFlash: **21.7 GB / 24 GB** (2.4 GB free)

Adding DFlash draft: **21.7 + 3.5 = 25.2 GB** → exceeds VRAM by 1.2 GB

`--fit on` will spill draft to system RAM (75 GB available). Generation works but draft speed drops when on CPU.

### Alternatives to DFlash (available now)

| Approach | Speedup | Effort | VRAM Impact | Available |
|---|---|---|---|---|
| **ngram-map-k4v** (built-in) | ~1.2-1.5x | 1 flag | None | ✅ Current server |
| **ngram-mod** (built-in) | ~1.3-1.8x | 1 flag | Minimal (~16 MB) | ✅ Current server |
| **buun-llama-cpp + DFlash** | ~2-6x claimed | Rebuild + GGUF convert | +3.5 GB | 🔧 Needs work |
| **vLLM + DFlash** | ~2-6x claimed | Full stack switch | Needs FP16 model | ❌ Won't fit 24 GB |

#### Enable ngram speculative decoding (immediate win)

```bash
# Add to current server command:
--spec-type ngram-map-k4v --spec-ngram-size-n 8 --spec-ngram-size-m 8 --spec-ngram-min-hits 2 --draft-max 64
```

Best for: repetitive text, code refactoring, reasoning models that repeat thinking in answers.

### Open Questions

- [ ] Does z-lab provide GGUF conversions of DFlash models, or do we need to convert?
- [ ] Does buun-llama-cpp have a GGUF conversion script for diffusion draft models?
- [ ] What's the real-world speedup on Qwen3.6-27B with DFlash vs ngram spec?
- [ ] Does DFlash work with Qwen3's SWA (sliding window attention) hybrid layers?
- [ ] Can DFlash draft model be quantized further (current 3.5 GB is safetensors FP16/FP32)?

## Stability Analysis — 120K Active Context (80% of 150K)

### Live Snapshot (2026-05-05 00:45)

Captured during active generation at ~120K context usage (PI session using 80% of 150K ctx).

#### GPU — Live vs Estimated

| Metric | Live (measured) | Estimated | Delta | Notes |
|--------|----------------|-----------|-------|-------|
| VRAM used | **22,131 MiB** (21.6 GB) | ~20.5 GB | +1.1 GB | Higher than estimated |
| VRAM free | **1,996 MiB** (1.95 GB) | ~3.5 GB | -1.5 GB | Less headroom than expected |
| GPU util | **98%** | — | — | Actively generating |
| Mem util | **61%** | — | — | Memory bus activity |
| Temperature | **78°C** | 73-75°C | +3-5°C | Warmer under sustained load |
| Power draw | **337W** | ~330W | +7W | At power ceiling |
| Power limit | **350W** | 350W | — | Stock default |
| Fan speed | **91%** | 81% | +10% | Working harder |

#### Process — Live vs Estimated

| Metric | Live (measured) | Estimated | Delta |
|--------|----------------|-----------|-------|
| RSS | **2.97 GB** (3,119,492 kB) | ~2.8 GB | +0.17 GB |
| Locked (mlock) | **0.67 GB** (698,404 kB) | ~0.7 GB | -0.03 GB |
| Swap | **0.00 GB** | 0.0 GB | ✅ Match |
| HWM (peak) | **2.97 GB** | — | — | At peak now |
| Threads | **22** | 16+runtime | ✅ Expected |
| CPU% | **61.8%** | ~40% | +22% | Higher during generation |
| Uptime | **59 min** | — | — | Recent restart |

#### System — Live

| Metric | Value | Notes |
|--------|-------|-------|
| RAM total | 93 GB | — |
| RAM used | 19 GB | 20% utilization |
| RAM free | 36 GB | — |
| RAM available | **74 GB** | Massive safety net for --fit spill |
| Swap | 0B / 8 GB | Unused |
| Load avg | 1.21, 1.19, 1.22 | Healthy |

### Running Server Command (live)

```bash
GGML_CUDA_GRAPH_OPT=1 /home/chief/llama-cpp-turboquant/build/bin/llama-server \
  --host 127.0.0.1 --port 8002 \
  --model /home/chief/models/Qwen3.6-27B/Qwen3.6-27B-UD-Q4_K_XL.gguf \
  --alias qwen3.6-27B-Q4-turbo \
  --jinja --chat-template-kwargs {"preserve_thinking":true} \
  --ctx-size 160000 --fit on --flash-attn on --no-mmap --mlock \
  --cont-batching -np 1 -b 2048 -ub 1024 \
  --threads 16 --threads-batch 16 \
  --ctx-checkpoints 6 --checkpoint-every-n-tokens 16384 \
  --cache-reuse 1024 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 \
  -ctk q8_0 -ctv turbo4 \
  --presence-penalty 0.0 --repeat-penalty 1.0 \
  --reasoning on --reasoning-budget 16384
```

### KV Cache Math — Verified Against Live Data

| Component | Calculation | Estimated | Live Proxy | Match? |
|-----------|-------------|-----------|------------|--------|
| Model weights (Q4_K_XL) | 27B × 0.5 bytes | 13.5 GB | 22.1 - 8.6 = 13.5 GB | ✅ |
| Active KV (6 CP × 16384) | 6 × 16384 × 493 KB | 4.8 GB | ~5.0 GB (proxy) | ✅ |
| Checkpoint storage | 6 × cumulative | ~2 GB RAM | 2.97 GB RSS total | ✅ |
| CUDA graphs + runtime | — | 1.5 GB | ~1.5 GB (proxy) | ✅ |
| **Total VRAM** | | **20.5 GB** | **22.1 GB** | ⚠️ +1.6 GB overhead |
| **Free VRAM** | | **3.5 GB** | **2.0 GB** | ⚠️ Less than expected |

**The 1.6 GB gap** is unaccounted overhead: CUDA context, flash attention buffers, cuBLAS workspace, driver allocations. Always add **+2 GB buffer** to estimates.

### OOM Risk Assessment

| Scenario | VRAM Spike | Headroom | Risk | Outcome |
|----------|-----------|----------|------|---------|
| Steady generation | +0 GB | 2.0 GB | 🟢 **None** | Stable — proven by 98% util |
| Cache reuse (1024 match) | +1-2 GB | 0-1 GB | 🟡 **Medium** | `--fit` spills to RAM, slight slowdown |
| New turn (reprocess 120K) | +4-6 GB | -2 to -4 GB | 🔴 **High** | `--fit` saves you, 10-30s pause |
| SWA invalidation | +4-6 GB | -2 to -4 GB | 🔴 **High** | Full reprocess spike, slowdown |
| Reasoning maxed (16K) | +2-3 GB | -1 to -1 GB | 🟡 **Medium** | Tight but manageable |
| PI hits 140K+ context | +3-4 GB | -1 to -2 GB | 🔴 **High** | Heavy spill, severe slowdown |

### Why 6 Checkpoints × 16384 Is Insufficient at 120K

```
Checkpoint coverage: 6 × 16,384 = 98,304 tokens
Uncovered gap: 120,000 - 98,304 = 21,696 tokens (18% of context)
Active KV between checkpoints: 16,384 × 493 KB = 8.1 GB (too large!)
```

The large interval (16,384) means each checkpoint segment is **8.1 GB** — bigger than available VRAM. `--fit on` handles this by spilling, but it causes slowdowns.

### Stability Recommendations

#### Immediate (change flags, no rebuild):

| Flag | Current | Recommended | Why |
|------|---------|-------------|-----|
| `--ctx-checkpoints` | 6 | **16** | Cover full 120K (16 × 8192 = 131K) |
| `--checkpoint-every-n-tokens` | 16384 | **8192** | Smaller segments (4 GB vs 8 GB) |
| `--cache-reuse` | 1024 | **256** | Fewer KV shift spikes |
| `-b` (batch) | 2048 | **1024** | Lower per-batch VRAM spike |
| `-ub` (ubatch) | 1024 | **512** | Smaller GPU operations |
| `--fit-target` | (default) | **512** | More aggressive CPU offload |

**Expected result:** VRAM drops to ~20 GB, headroom increases to ~4.5 GB, turn-boundary pauses eliminated.

#### With buun-llama-cpp rebuild:

| Change | Effect |
|--------|--------|
| `-ctk turbo3_tcq -ctv turbo3_tcq` | KV 5× smaller → 120K uses ~2.6 GB vs ~13 GB |
| `--ctx-size 131072` | 128K context, stable |
| `--spec-type dflash` | 2-3× generation speed |
| `--ctx-checkpoints 16 --checkpoint-every-n-tokens 8192` | Full coverage |

**Expected result:** 128K context at ~19 GB VRAM, 5.5 GB headroom, 60-90 tok/s generation.

### Bottom Line

| Question | Answer |
|----------|--------|
| Will it crash? | **No** — `--fit on` + 74 GB RAM = safety net |
| Stable during generation? | **Yes** — proven by live 98% GPU util |
| Stable between turns? | **Marginal** — 2 GB free, spikes hit 24-26 GB |
| Slowdown at turn boundaries? | **Yes** — 10-30s pauses expected at 120K+ |
| Stable at full 150K? | **No** — heavy spill, severe slowdown |
| Quick fix? | Increase checkpoints to 16×8192, reduce batch to 1024/512 |
| Best fix? | buun + TCQ (turbo3_tcq) = stable at 128K+ with DFlash speed |

## Reference: 7-step Council-Build-Council Pipeline

> **Source:** [r/LocalLLM — "I Ralph-looped Opus overnight"](https://www.reddit.com/r/LocalLLM/comments/1t4cqro/) by u/yes_i_tried_google (May 2026)
> **PDF:** [[cold backfilling context.pdf]]
> **Status:** Unmerged PRs, proof-of-concept — not yet reproducible without cherry-picks

Multi-model coding pipeline on a **single GPU** using llama.cpp slot persistence to eliminate cold-start prefill overhead during model swaps.

### Hardware (reference build)

| Component | Spec |
|---|---|
| CPU | Ryzen 9950X |
| GPU | **Single RTX 3090 Ti** (24 GB) |
| RAM | 96 GB DDR5 Samsung 9100 |
| Storage | 2 TB Gen5 NVMe |

### Pipeline Stages

```
Spec → Review → Plan → Build → Code Review → Security Review → UAT Review
```

All models serialize through one GPU slot. Parallel from the orchestrator's perspective; `llama-swap` executes sequentially.

### Model Roster & Inferred Quantizations

| Role | Model | Inferred Quant | Context | Notes |
|---|---|---|---|---|
| **Chair** (orchestrator) | Qwen3.6-27B | **q4_K_M** | 130–138K | GGUF in system RAM, ngl ~48 |
| **Builder** | Qwen3-coder-30B | **q4_K_M** | ~50K | GGUF in system RAM, ctx forced 262K→196K |
| **Reviewer** | Gemma-4-31B | **q4_K_M** | ~19K | Primary reviewer |
| **Reviewer** | GPT-OSS-20B | **q4_K_M or q5_K_M** | ~20K | Could fit q5 in 24 GB |
| **Reviewer** | Qwen3.6-27B | **q4_K_M** | ~20K | Same as Chair |
| **Reviewer** | Nemotron-Cascade-2-30B | **q4_K_M** | ~20K | |
| **Reviewer** | Qwen3.6-35B | **q4_K_M** | ~20K | Tightest fit at q4 |
| **Tiny Council** | Ministral-8B | **q6_K** | — | Co-resident, no swap cost |
| **Tiny Council** | Nemotron-Nano-4B | **q6_K** | — | Co-resident, no swap cost |
| **Tiny Council** | Qwen3-4B | **q6_K** | — | Co-resident, no swap cost |

**Quant inference rationale:**

- **Large models → q4_K_M**: Build error references `q4/q4` (KV cache quant). 27–35B at q4 = 14–18 GB weights, leaving room for KV. q5 would exceed 24 GB for 30B+ models.
- **Tiny Council → q6_K**: Three models co-resident in ~11 GB VRAM. q6_K totals ~10.9 GB (5.5 + 2.7 + 2.7). q5_K_M would be ~9.1 GB (too low), q8_0 ~16 GB (too high).
- **GGUF in system RAM**: Chair + Builder weights kept in 96 GB DDR5 for fast load cycles.

### Model Architecture & Role Breakdown

| Role | Model | Arch | Training | What It Brings |
|---|---|---|---|---|
| **Chair** (orchestrator) | Qwen3.6-27B | Dense | Instruct | Routes tasks, manages pipeline flow, holds full context across stages |
| **Builder** | Qwen3-Coder-30B-A3B | MoE | **Code-trained** | Writes actual code — only model with code-specific pretraining. 1M context variant handles large files |
| **Reviewer** | Gemma-4-31B-it | Dense | Instruct | Google's voice — catches style issues, architecture concerns, different training lineage from Qwen |
| **Reviewer** | GPT-OSS-20B | Dense | Instruct | OpenAI's voice — different tokenizer, different failure modes, catches what others miss |
| **Reviewer** | Qwen3.6-27B | Dense | Instruct | Same as Chair — reviews with orchestrator's perspective, consistency check |
| **Reviewer** | Nemotron-Cascade-2-30B-A3B | MoE | Instruct | NVIDIA's reasoning strength — strong at logic errors, edge cases, security-adjacent issues |
| **Reviewer** | Qwen3.6-35B | Dense | Instruct | Largest model in the council — final authority on complex decisions, catches subtle bugs smaller models skip |
| **Tiny Council** | Ministral-8B | Dense | Instruct | Structured output / tool-use specialist — fast 3-way critique, no swap cost |
| **Tiny Council** | Nemotron-Nano-4B | Dense | Instruct | NVIDIA's lightweight reasoning — quick sanity checks, co-resident |
| **Tiny Council** | Qwen3-4B | Dense | Instruct | Broad generalist — third perspective in parallel critique, co-resident |

**Diversity strategy:**

- **4 training lineages** — Qwen (Alibaba), Gemma (Google), GPT-OSS (OpenAI), Nemotron (NVIDIA)
- **2 architectures** — Dense (consistent behavior) + MoE (specialized expert routing)
- **1 code-specialist** — Qwen3-Coder is the only model pretrained on code corpora
- **3 size tiers** — 4-8B (Tiny Council, instant), 20-27B (reviewers), 30-35B (Builder/Chair)

**Why diversity matters:** Different models make different mistakes. Running code through 5 distinct training lineages catches more bugs than any single model, even a larger one. The Tiny Council (3 co-resident small models) gives instant parallel feedback without GPU swaps.

### The Problem: Cold Prefill on Every Swap

Without persistent KV cache, every model re-entry pays full prefill:

| Model Role | Context | Prefill Time |
|---|---|---|
| Chair (Qwen3.6-27B) | 130K | **~165 s** |
| Reviewers | ~20K | **~30 s** |
| Coders | ~50K | **~60 s** |

Full session (spec + 3 builders + review + security + UAT + 2 remediation): **~22 minutes of pure prefill waste**.

### The Solution: Slot Persistence via Unmerged PRs

Two PRs by **@European-tech** cherry-picked into a custom llama.cpp build:

| PR | Title | What it does |
|---|---|---|
| [#20819](https://github.com/ggml-org/llama.cpp/pull/20819) | Persist context checkpoints across slot save/restore | Companion `<file>.checkpoints` (magic `0x4C4C4350` "LLCP"). Without this, hybrid/recurrent models (Qwen3) fall back to full reprocess on restore. |
| [#20822](https://github.com/ggml-org/llama.cpp/pull/20822) | Auto-save/restore slot state in router mode | `--auto-save-slots` / `--auto-restore-slots`. Load-bearing piece — dropped T2 from 171s → 6.5s. |

**Both PRs still open, not merged.** Blocked by llama.cpp's AI-generated content policy (bot flagged them despite author disclosure).

### Python Supervisor (`slot-supervisor.py`)

Custom wrapper around `llama-server`:

1. **Hashes normalized message prefixes** (strips volatile `<TS>`, `<DATE>`, `<EPOCH>`, `<CLOCK>` injected by opencode)
2. **Pokes `/slots/0?action=restore`** before forwarding each request
3. **Hardlinks** `<prefix_hash>.bin` ↔ `<full_hash>.bin` so prefix-matching hits cache via either key
4. Slot bins on Gen5 NVMe; Linux page cache acts as implicit RAM tier (~3 GB/s restore)

### Results

| Metric | Without Slots | With Slots |
|---|---|---|
| Chair restore (138K KV) | ~165 s prefill | **801 ms restore → 4.7 s to result** |
| Reviewer restore (19K KV) | ~30 s prefill | **160–651 ms restore → 27–64 s (gen-dominated)** |
| Full swap cycle (save + restore) | — | **~2 s** |
| Full session overhead | **~22 min** | **~65 s** |
| Tiny council 3-way critique | — | **19.4 s end-to-end** (no swap cost) |

### Caveats

- **Byte-compatible KV only**: Same model, same `--ctx-size`, same `-ctk/-ctv` quant, same arch flags. Change any → invalidate bins.
- **First visit pays prefill**: Slot reuse pays off from 2nd visit onward.
- **Worth it only if ctx-heavy AND swap-heavy**: Single-model setups get nothing.
- **opencode system prompt instability**: `OPENCODE_EXPERIMENTAL_CACHE_STABILIZATION=1` required (PR #14743).
- **Both PRs unmerged**: Requires cherry-pick or custom build.

### Related GitHub PRs

| PR | Author | State | Relevance |
|---|---|---|---|
| [#20819](https://github.com/ggml-org/llama.cpp/pull/20819) | European-tech | 🔴 Open | Checkpoint persistence — cherry-picked by OP |
| [#20822](https://github.com/ggml-org/llama.cpp/pull/20822) | European-tech | 🔴 Open | Auto-save/restore — cherry-picked by OP |
| [#20955](https://github.com/ggml-org/llama.cpp/pull/20955) | European-tech | ✅ Closed | Checkpoint recovery on truncation failure — supersedes parts of #20819/#20822. Comment by @llukas: "auto-save/auto-restore could be an option not unconditional behavior" |

**Key insight from PRs:** The same problem the OP solved (full reprocess on slot restore for hybrid models) is exactly what these PRs target. PR #20955 was closed (likely merged into main or superseded). The maintainer comment suggests auto-save should be opt-in, not default — relevant if we ever implement this.

**Why PRs are stuck:** llama.cpp's automated bot flags AI-assisted PRs. @European-tech disclosed AI usage but the bot still blocks them (new contributor + multiple open PRs policy).

## Change Log

| Date | Change |
|---|---|
| 2026-05-05 | Initial hardware audit and analysis |
| 2026-05-05 | Added turboquant build analysis, KV cache format comparison, hybrid config, checkpoint scaling table, GGML_CUDA_COMPRESSION_MODE explanation |
| 2026-05-05 | Revised configs for conversational use: q8_0 @ 64K (port 8001), turbo4 hybrid @ 96K (port 8002), reduced checkpoints to 8, added turn latency tables, SWA invalidation analysis |
| 2026-05-05 | Added DFlash speculative decoding section: paper research, z-lab models, buun-llama-cpp fork, build instructions, VRAM analysis, alternatives |
| 2026-05-05 | Added stability analysis: live snapshot at 120K context, live vs estimated VRAM comparison, OOM risk assessment, checkpoint insufficiency analysis, immediate + rebuild recommendations |
| 2026-05-06 | Added 7-step Council-Build-Council reference section: multi-model pipeline from r/LocalLLM, model roster with inferred quantizations, slot persistence via unmerged PRs #20819/#20822, GitHub PR research |
| 2026-05-06 | Marked GPU power limit as no-go — hardware max is 350 W, cannot raise. Updated benchmark table to aspirational-only. |
| 2026-05-06 | Added Model Architecture & Role Breakdown — arch type (dense/MoE), training type, and what each model contributes to the council pipeline. |
