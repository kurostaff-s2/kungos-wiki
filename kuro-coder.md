---
tags: [a4000, rtx-3060, kuro-coder, code-generation, debugging, data-parsing, turboquant, dual-gpu, team]
created: 2026-05-06
status: design
related: [[Local-Hardware]], [[ADR-003-llama-cpp]]
---

# Kuro-Coder — Dual-GPU Team Coding Station

## Summary

Standalone dual-GPU coding workstation for team code generation, debugging, and data parsing. **RTX A4000 (16 GB)** carries the primary coder model. **RTX 3060 12GB (used)** hosts two fast-lane models for instant debugging and parsing. No council pipeline — focused tooling for developers.

**Total VRAM: 28 GB across two GPUs. Total GPU cost: ~$500 (both used).**

## Hardware

### GPUs

| GPU | VRAM | Role | Models |
|---|---|---|---|
| **RTX A4000** (16 GB GDDR6, GA102, 140W, PCIe x16) | 16 GB | Primary coder | Qwen3-Coder-30B-A3B (one model) |
| **RTX 3060 12GB** (GA106, 170W, PCIe x16, used ~$200) | 12 GB | Fast lane | Ministral-8B + Nemotron-Nano-4B (two models) |

### Platform

| Component | Option A (AM5) | Option B (AM4) | Notes |
|---|---|---|---|
| CPU | Ryzen 5 7500F (6C/12T, 5.0 GHz) | Ryzen 5 5700 (8C/16T, 4.1 GHz) | GPU does 95% of work |
| Motherboard | MSI B650 Tomahawk | MSI B550 Tomahawk | Slot 1: x16, Slot 2: x4 |
| RAM | 64 GB DDR5-5600 (~$90) | 64 GB DDR4-3200 (~$65) | `--fit` spill target |
| PSU | 600W 80+ Gold | 600W 80+ Gold | Peak ~375W (A4000 140 + 3060 170 + CPU 65) |
| **Platform cost** | **~$440** | **~$340** | Excluding GPUs |

**AM4 vs AM5:** Pick AM4 to save $100 — the GPU does the work. Pick AM5 for PCIe Gen4 on the A4000 and CPU upgrade path. Second slot is x4 on both boards — acceptable for the 3060 fast lane (models are small, not bandwidth-bound).

### Why Not RTX 5060 Ti 8G?

| Spec | 5060 Ti 8G | 3060 12G | Winner |
|---|---|---|---|
| VRAM | 8 GB GDDR7 | 12 GB GDDR6 | **3060** — 50% more VRAM |
| Bandwidth | 448 GB/s (28 Gbps) | 360 GB/s (15 Gbps) | 5060 Ti — irrelevant for 4-8B models |
| CUDA Cores | 4608 | 3584 | 5060 Ti — but both are overkill for fast lane |
| Co-resident models | 1 (8 GB too tight) | 2 (12 GB comfortable) | **3060** |
| Price | ~$400 new | ~$200 used | **3060** — half the cost |

8 GB cannot fit two co-resident models (Ministral Q6 6 GB + Nano Q6 3.5 GB = 9.5 GB). The 3060's 12 GB fits both with 2.5 GB headroom, at half the price. GDDR7 speed doesn't matter when the models are small.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  RTX A4000 (16 GB) — Slot 1, PCIe x16                       │
│                                                              │
│  Server: Deep Work (port 8002)                               │
│  Qwen3-Coder-30B-A3B  IQ4_XS  ·  ~15 GB VRAM                │
│  Code generation, refactoring, large file analysis           │
│  Context: ~20K (q8_0 KV)                                    │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  RTX 3060 12GB (12 GB) — Slot 2, PCIe x4                    │
│                                                              │
│  Server A: Ministral-8B  q6_K  ·  ~6 GB VRAM  (port 8001)   │
│  Structured critique, code review, format checking           │
│                                                              │
│  Server B: Nemotron-Nano-4B  q6_K  ·  ~3.5 GB VRAM (port 8003)│
│  Debugging, data parsing, quick Q&A                          │
│                                                              │
│  Headroom: ~2.5 GB for KV growth                             │
└─────────────────────────────────────────────────────────────┘
```

## Model Roster

### Primary Coder — Qwen3-Coder-30B-A3B (A4000)

| Property | Value |
|---|---|
| **Arch** | MoE (30B total, ~3B active per token) |
| **Quant** | IQ4_XS (16 GB file) |
| **KV** | q8_0 + q8_0 |
| **Context** | 20,000 tokens |
| **Total VRAM** | ~15 GB / 16 GB |
| **Headroom** | ~1 GB |
| **On Disk** | ✅ `qwen3-coder/Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf` |

**Why this model:**
- 30B MoE coder — SOTA for code generation in this class
- MoE = only ~3B active per token — faster than a dense 14B
- IQ4_XS = 16 GB, fits on A4000 with room for 20K context
- Code-specialized pretraining on massive code corpora

### Fast Lane — Ministral-8B (3060)

| Property | Value |
|---|---|
| **Quant** | Q6_K (6.2 GB) |
| **KV** | q8_0 |
| **Context** | 32K |
| **Total VRAM** | ~6 GB / 12 GB (shared with Nano) |
| **On Disk** | ✅ `mistral/Ministral-8B-Instruct-2410-Q6_K.gguf` |

**Why:** Structured output specialist, strong at code review and format checking.

### Fast Lane — Nemotron-Nano-4B (3060)

| Property | Value |
|---|---|
| **Quant** | Q6_K (3.8 GB) |
| **KV** | q8_0 |
| **Context** | 32K |
| **Total VRAM** | ~3.5 GB / 12 GB (shared with Ministral) |
| **On Disk** | ✅ `nvidia/NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf` |

**Why:** NVIDIA reasoning at 4B, strong at debugging and data parsing.

## Server Commands

### Ministral-8B (3060, port 8001)

```bash
# Force GPU 1 (3060)
export CUDA_VISIBLE_DEVICES=1

/home/chief/buun-llama-cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8001 \
  -m /home/chief/models/mistral/Ministral-8B-Instruct-2410-Q6_K.gguf \
  --alias ministral-8b \
  --jinja \
  --ctx-size 32768 \
  --flash-attn on --no-mmap --mlock \
  -ngl 99 \
  --threads 8 --threads-batch 8 \
  --temp 0.3 --top-p 0.9 --top-k 10 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0
```

### Nemotron-Nano-4B (3060, port 8003)

```bash
# Force GPU 1 (3060)
export CUDA_VISIBLE_DEVICES=1

/home/chief/buun-llama-cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8003 \
  -m /home/chief/models/nvidia/NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf \
  --alias nemotron-nano-4b \
  --jinja \
  --ctx-size 32768 \
  --flash-attn on --no-mmap --mlock \
  -ngl 99 \
  --threads 8 --threads-batch 8 \
  --temp 0.2 --top-p 0.9 --top-k 10 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0
```

### Qwen3-Coder-30B-A3B (A4000, port 8002)

```bash
# Force GPU 0 (A4000)
export CUDA_VISIBLE_DEVICES=0

/home/chief/buun-llama-cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8002 \
  -m /home/chief/models/qwen3-coder/Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf \
  --alias qwen3-coder-30b \
  --jinja \
  --ctx-size 20480 \
  --flash-attn on --no-mmap --mlock \
  -ngl 99 \
  --cont-batching -np 1 -b 1024 -ub 512 \
  --threads 8 --threads-batch 8 \
  --ctx-checkpoints 4 --checkpoint-every-n-tokens 4096 \
  --cache-reuse 256 \
  --temp 0.3 --top-p 0.9 --top-k 10 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0 \
  --reasoning on --reasoning-budget 8192
```

**Note:** `CUDA_VISIBLE_DEVICES` controls GPU assignment. Verify with `nvidia-smi` — GPU 0 = A4000, GPU 1 = 3060 (or swap if detected differently).

## VRAM Budget

### A4000 (16 GB)

| Component | VRAM |
|---|---|
| Qwen3-Coder-30B-A3B (IQ4_XS weights) | ~12 GB |
| KV cache (20K, q8_0+q8_0, MoE smaller dim) | ~3 GB |
| CUDA runtime + flash attention | ~0.5 GB |
| **Total** | **~15.5 GB / 16 GB** |
| **Headroom** | **~0.5 GB** |

### RTX 3060 (12 GB)

| Component | VRAM |
|---|---|
| Ministral-8B (Q6_K weights) | ~5.5 GB |
| Nemotron-Nano-4B (Q6_K weights) | ~3.2 GB |
| KV cache (both, 32K each, q8_0) | ~2.5 GB |
| CUDA runtime | ~0.3 GB |
| **Total** | **~11.5 GB / 12 GB** |
| **Headroom** | **~0.5 GB** |

Both GPUs run near capacity with minimal headroom. Stable during steady generation. KV growth beyond configured context will trigger `--fit` spill to system RAM (64 GB available).

## Use Case Workflows

### Code Generation

```
1. User sends code task to Coder (port 8002)
2. Coder reads context, generates implementation
3. Output piped to Ministral (port 8001) for review
4. Ministral returns critique → user iterates
```

### Debugging

```
1. Paste error + code into Nemotron-Nano (port 8003)
2. Instant analysis — root cause, suggested fix
3. If complex: escalate to Coder with full file context (port 8002)
```

### Data Parsing

```
1. Paste raw data (JSON, CSV, logs) into Nemotron-Nano (port 8003)
2. Prompt: "Parse into structured format, extract X, Y, Z"
3. Nano returns clean output
4. For large datasets (>32K): use Coder (port 8002)
```

### Multi-User

```
User A: Coder (A4000) — code generation
User B: Ministral (3060) — code review
User C: Nemotron-Nano (3060) — debugging
→ All three run simultaneously, isolated GPUs
```

## Build Requirements

| Requirement | Status | Notes |
|---|---|---|
| **buun-llama-cpp** | Clone + build | Superset of turboquant + DFlash |
| **GGML_CUDA** | ON | CUDA support |
| **GGML_CUDA_FA** | ON | Flash attention |
| **GGML_CUDA_FA_ALL_QUANTS** | ON | Cross-type FA kernels |
| **GGML_CUDA_COMPRESSION_MODE** | `speed` | Faster kernels |
| **GGML_NATIVE** | ON | `-march=native` |
| **GGML_CUDA_NCCL** | ON | Multi-GPU support (compiled in) |

```bash
git clone https://github.com/spiritbuun/buun-llama-cpp.git
cd buun-llama-cpp

cmake -B build \
  -DGGML_CUDA=ON \
  -DGGML_NATIVE=ON \
  -DGGML_CUDA_FA=ON \
  -DGGML_CUDA_FA_ALL_QUANTS=ON \
  -DGGML_CUDA_COMPRESSION_MODE=speed \
  -DGGML_CUDA_NCCL=ON \
  -DCMAKE_BUILD_TYPE=Release

cmake --build build -j$(nproc)
```

## Systemd Services

### kuro-coder-coder.service (A4000)

```ini
[Unit]
Description=Kuro-Coder Primary (Qwen3-Coder-30B on A4000)
After=network.target

[Service]
Type=simple
User=chief
Environment=CUDA_VISIBLE_DEVICES=0
WorkingDirectory=/home/chief/buun-llama-cpp/build
ExecStart=/home/chief/buun-llama-cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8002 \
  -m /home/chief/models/qwen3-coder/Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf \
  --jinja --ctx-size 20480 --flash-attn on --no-mmap --mlock \
  -ngl 99 --cont-batching -np 1 -b 1024 -ub 512 \
  --threads 8 --threads-batch 8 \
  --ctx-checkpoints 4 --checkpoint-every-n-tokens 4096 \
  --cache-reuse 256 --temp 0.3 --top-p 0.9 --top-k 10 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0 --reasoning on --reasoning-budget 8192
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### kuro-coder-ministral.service (3060)

```ini
[Unit]
Description=Kuro-Coder Review (Ministral-8B on 3060)
After=network.target

[Service]
Type=simple
User=chief
Environment=CUDA_VISIBLE_DEVICES=1
WorkingDirectory=/home/chief/buun-llama-cpp/build
ExecStart=/home/chief/buun-llama-cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8001 \
  -m /home/chief/models/mistral/Ministral-8B-Instruct-2410-Q6_K.gguf \
  --jinja --ctx-size 32768 --flash-attn on --no-mmap --mlock \
  -ngl 99 --threads 8 --threads-batch 8 \
  --temp 0.3 --top-p 0.9 --top-k 10 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### kuro-coder-nano.service (3060)

```ini
[Unit]
Description=Kuro-Coder Debug (Nemotron-Nano-4B on 3060)
After=network.target

[Service]
Type=simple
User=chief
Environment=CUDA_VISIBLE_DEVICES=1
WorkingDirectory=/home/chief/buun-llama-cpp/build
ExecStart=/home/chief/buun-llama-cpp/build/bin/llama-server \
  --host 127.0.0.1 --port 8003 \
  -m /home/chief/models/nvidia/NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf \
  --jinja --ctx-size 32768 --flash-attn on --no-mmap --mlock \
  -ngl 99 --threads 8 --threads-batch 8 \
  --temp 0.2 --top-p 0.9 --top-k 10 --min-p 0.05 \
  -ctk q8_0 -ctv q8_0
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Models Needed

| Model | File | Size | Status |
|---|---|---|---|
| Qwen3-Coder-30B-A3B | `Qwen3-Coder-30B-A3B-Instruct-IQ4_XS.gguf` | 16 GB | ✅ On disk |
| Ministral-8B | `Ministral-8B-Instruct-2410-Q6_K.gguf` | 6.2 GB | ✅ On disk |
| Nemotron-Nano-4B | `NVIDIA-Nemotron-3-Nano-4B-Q6_K.gguf` | 3.8 GB | ✅ On disk |

**All models already on disk. Zero downloads needed.**

## Constraints vs. RTX 3090 (24 GB single GPU)

| Capability | A4000 + 3060 (28 GB, dual) | 3090 (24 GB, single) |
|---|---|---|
| Coder model | 30B MoE | 30B MoE or 27B dense |
| Coder context | 20K (q8_0) | 64-90K (turbo3_tcq) |
| Fast models | 2 co-resident, no spill | 1 co-resident, slight spill |
| Concurrent users | 3 (isolated GPUs) | 1-2 (shared VRAM) |
| DFlash speculative decoding | ❌ No headroom on either GPU | ⚠️ Possible with TCQ |
| Multi-GPU tensor parallelism | ✅ Compiled in | N/A |

## Change Log

| Date | Change |
|---|---|
| 2026-05-06 | Initial design — single A4000, 14B coder + turbo3_tcq 90K context |
| 2026-05-06 | Dual-GPU redesign — A4000 + RTX 3060, 30B coder + two fast models, 3 systemd services, AMD platform options, 5060 Ti evaluation |
