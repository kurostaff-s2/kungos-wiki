# RAM Disk for LLM Slot Storage — Analysis Report

**Date:** 2026-05-09 (updated with LMCache research)
**System:** RTX 3090 (24GB VRAM), 96GB RAM, TEAMGROUP MP33 1TB NVMe (600TBW)

---

## 1. Current Slot Storage Layout

| Model | slot-0.bin | .checkpoints | model.bin | model.checkpoints | Total |
|---|---|---|---|---|---|
| Qwen3.6-27B-UD-Q4_K_XL | 2.6GB | 2.4GB | 2.8GB | 2.4GB | **10.2GB** |
| Nemotron-Cascade-30B-IQ4_XS | 76MB | 143MB | 76MB | 143MB | **438MB** |
| GPT-OSS-20B-Q4_K_M | 0 | 0 | 0 | 0 | **0** (empty) |
| **Total** | | | | | **11GB** |

**Slot directory:** `/home/chief/Coding-Projects/7-council/council-config/slots/`
**Current location:** NVMe (`/dev/nvme0n1p2`, TEAMGROUP MP33 1TB)

---

## 2. Actual I/O Impact

### Per-Swap Breakdown (Qwen3.6-27B as primary)

Each swap cycle involves:

| Operation | Direction | Size | Notes |
|---|---|---|---|
| `_save_current_slot()` | Write | ~5.0GB | slot-0.bin + checkpoints |
| `_restore_slot()` | Read | ~5.0GB | slot-0.bin + checkpoints |
| `proc.start()` (model load) | Read | ~5.2GB | model.bin + checkpoints (no_mmap=true) |
| Metadata JSON writes | Write | ~200B | negligible |
| **Total per swap** | **~15.2GB** | 10GB read + 5.2GB write | |

### Daily Volume (9.1 swaps/hour = ~218 swaps/day)

| Metric | Value |
|---|---|
| Reads per day | 218 x 10GB = **2.18 TB** |
| Writes per day | 218 x 5.2GB = **1.13 TB** |
| **Total I/O per day** | **3.31 TB** |
| Monthly I/O | ~100 TB |

### NVMe Wear Analysis

**Drive:** TEAMGROUP MP33 1TB (TM8FPK001T)
- **TBW rating:** 600 TBW
- **Warranty:** 5 years
- **DWPD (Drive Writes Per Day):** 600TBW / 1TB / 1825 days = **0.33 DWPD**

**At current workload:**
- Daily writes: 1.13 TB
- DWPD consumed: 1.13 / 0.33 = **3.4x over rated DWPD**
- Days to 600TBW: 600 / 1.13 = **531 days** (~1.5 years)
- **This WILL burn through the warranty endurance** if sustained

**Caveat:** The 3.3TB/day figure includes the Linux page cache reusing reads. Actual physical NVMe writes are lower because:
- Model reads (5.2GB/swap) hit page cache after first load
- Slot restores (5GB/swap) hit page cache for recently-written data
- Actual physical writes are closer to slot saves only: ~1.13TB/day

Even at 1.13TB/day writes:
- Days to 600TBW: **531 days**
- **Still burns warranty in ~1.5 years at this swap rate**

---

## 3. RAM Disk (tmpfs) Analysis

### What Would Move to RAM

Only the **slot bins** (not model weights):
- Qwen3.6-27B slot: ~5GB (slot-0.bin + checkpoints)
- Nemotron slot: ~320MB
- GPT-OSS slot: ~0 (empty)
- **Total slot storage in RAM: ~5.3GB**

### RAM Impact
- Available RAM: 96GB total, 72GB free/available
- Slot storage (all models): ~12GB max
- **After tmpfs: ~48GB still available** (plenty of headroom)

### Performance Gain

| Operation | NVMe (TEAM MP33) | tmpfs (RAM) | Speedup |
|---|---|---|---|
| Slot save (5GB write) | ~2.5s (2GB/s) | ~0.3s (15GB/s+) | **~8x** |
| Slot restore (5GB read) | ~2.5s (2GB/s) | ~0.3s (15GB/s+) | **~8x** |
| Metadata (tiny) | ~0.01s | ~0.001s | negligible |

**Per-swap savings:** ~4.4 seconds (2.5s write + 2.5s read - 0.3s - 0.3s)

### Does Page Cache Already Do This?

**Yes, partially.** Linux page cache keeps recently accessed files in RAM. However:

| Factor | Page Cache | tmpfs |
|---|---|---|
| Slot save (fresh write) | Must flush to NVMe | Stays in RAM |
| Slot restore (read) | Cached if recently written | Always in RAM |
| Model load reads | Cached after first load | N/A (models stay on NVMe) |
| Eviction risk | OS can evict under memory pressure | Never evicted (until unmount) |
| Write amplification | Yes (metadata, journaling, wear leveling) | None |

**Key difference:** Page cache *eventually* writes to NVMe. tmpfs *never* touches NVMe for slot data.

### tmpfs Setup

```bash
# Mount tmpfs for slot storage
sudo mount -t tmpfs -o size=48G tmpfs /home/chief/Coding-Projects/7-council/council-config/slots

# Or make persistent in /etc/fstab (improved options):
# tmpfs /home/chief/Coding-Projects/7-council/council-config/slots tmpfs defaults,size=48G,huge=within_size,noswap,mode=1777 0 0
```

### Improved Mount Options (2026)

Your kernel (6.17.0) supports two additional tmpfs options that are free performance/reliability upgrades:

| Option | What it does | Why it matters |
|---|---|---|
| `huge=within_size` | Uses transparent huge pages (2MB) for large files | Slot files are 1-2.4GB — huge pages reduce page table overhead, ~10-15% faster sequential I/O |
| `noswap` (since Linux 6.4) | Prevents tmpfs pages from being swapped to disk | Guarantees slot data stays in physical RAM — no defeat of the purpose under memory pressure |

**Improved mount command:**
```bash
sudo mount -t tmpfs -o size=48G,huge=within_size,noswap tmpfs /home/chief/Coding-Projects/7-council/council-config/slots
```

**Improved fstab entry:**
```
tmpfs /home/chief/Coding-Projects/7-council/council-config/slots tmpfs defaults,size=48G,huge=within_size,noswap,mode=1777 0 0
```

**Tradeoff:** Slots are volatile — lost on reboot. But slots are just KV cache state; they regenerate on next use.

---

## 4. Recommendations (Ranked)

### 1. Use tmpfs for slot storage — **HIGH IMPACT**
- **Saves:** ~4.4s per swap (37% of swap I/O time)
- **Eliminates:** 1.13TB/day of physical NVMe writes
- **Cost:** 5.3GB RAM (you have 72GB free)
- **Risk:** Slots lost on reboot (regenerate automatically)
- **Verdict:** Do this immediately

### 2. Keep model weights on NVMe — **CORRECT AS-IS**
- Models are 16-20GB each, too large for RAM-only
- Page cache handles repeated loads efficiently
- First load from NVMe is the only slow one; subsequent loads are cached

### 3. Consider `no_mmap: false` for models — **MODERATE IMPACT**
- With mmap: OS page cache handles model reads incrementally
- Second load is near-instant (cached pages)
- Current `no_mmap: true` forces full NVMe read every swap
- **Risk:** mmap may cause issues with some llama.cpp versions on swap-heavy workloads
- **Test before changing**

### 4. Skip slot save when no tokens added — **MODERATE IMPACT**
- Many swaps are model-to-model with no new tokens
- Checking `cached_tokens > 0` before save skips 5GB write
- **Saves:** ~2.5s per skipped swap
- **Implementation:** One-line check in `_save_current_slot()`

### 5. NVMe wear — **MONITOR, DON'T PANIC**
- At 1.13TB/day writes: 531 days to 600TBW
- With tmpfs (recommendation #1): **0 TB/day writes from slots**
- Remaining writes: OS, logs, other applications
- **tmpfs essentially eliminates the wear concern**

---

## 5. Bottom Line

| Scenario | Swap Time | Daily NVMe Writes | NVMe Lifespan |
|---|---|---|---|
| Current (NVMe slots) | ~16s | 1.13 TB | ~1.5 years |
| With tmpfs slots | ~12s | ~0.1 TB | 10+ years |
| tmpfs + skip empty saves | ~10s | ~0.1 TB | 10+ years |

**The single highest-impact change:** Mount slot storage on tmpfs. 4 seconds saved per swap, zero NVMe wear from slots, 5GB RAM cost.

**Setup command:**
```bash
sudo mount -t tmpfs -o size=48G,huge=within_size,noswap tmpfs /home/chief/Coding-Projects/7-council/council-config/slots
```

**For persistence across reboots** (add to `/etc/fstab`):
```
tmpfs /home/chief/Coding-Projects/7-council/council-config/slots tmpfs defaults,size=48G,huge=within_size,noswap,mode=1777 0 0
```

---

## 6. LMCache — Why It's Not the Right Tool Here

### What is LMCache?

**LMCache** is an enterprise-grade KV cache management system for multi-server LLM inference clusters. It sits between the inference engine (vLLM or SGLang) and the storage stack, implementing a multi-tier hierarchical cache:

```
GPU VRAM (active KV cache)
    ↕ async offload/prefetch
CPU DRAM (pinned memory "hot cache")
    ↕ async write with LRU eviction
Local Disk / NVMe (large local tier)
    ↕ async sync
Remote Storage (Redis, Mooncake, InfiniStore, S3)
```

Key features: chunk-based KV storage (256-token chunks), LRU eviction, on-the-fly compression (CacheGen), NUMA-aware allocation, cross-instance KV cache sharing, controller API for pin/clear/move operations.

**License:** Apache 2.0 (free, permissive, commercial-use OK)

**Sources:** [github.com/LMCache/LMCache](https://github.com/LMCache/LMCache), [docs.lmcache.ai](https://docs.lmcache.ai), [arxiv.org/abs/2510.09665](https://arxiv.org/abs/2510.09665)

### Can LMCache Replace tmpfs for Our Use Case?

**No — they solve fundamentally different problems.**

| What tmpfs does for us | Can LMCache do it? |
|---|---|
| Make `--slot-save-path` writes fast (RAM instead of NVMe) | ❌ No — LMCache doesn't integrate with llama.cpp's `--slot-save-path` |
| Eliminate NVMe wear from slot bin writes | ❌ No — LMCache has no hook into llama.cpp slot persistence |
| Survive model swaps without touching disk | ❌ No — LMCache is a vLLM/SGLang extension, not a filesystem |

**LMCache only works with vLLM and SGLang.** It has zero integration with llama.cpp. Our slot supervisor uses `llama-server` from llama.cpp, which writes slot bins via `--slot-save-path`. LMCache has no mechanism to intercept or accelerate those writes.

### What LMCache Actually Solves

LMCache is designed for **multi-user, multi-GPU serving clusters** where:
- Multiple vLLM instances share KV caches across requests (prefix caching)
- Prefill-decode disaggregation (one server computes KV, another generates)
- Enterprise settings with persistent KV cache across sessions and users

Our setup is **single-user, single-GPU, model-swapping**. We don't have multiple users sharing prefixes. We need fast disk I/O for slot bins. tmpfs is the right tool.

### Could We Use LMCache Instead of llama.cpp?

Technically yes, but it's a complete stack change:
1. Replace `llama-server` with `vLLM + LMCache`
2. Rewrite slot supervisor to use vLLM's API instead of llama.cpp's
3. Lose llama.cpp features we rely on: TurboQuant, `-ctk q8_0 -ctv turbo4`, reasoning format, etc.
4. Gain nothing we need (no multi-user prefix reuse, no cross-instance sharing)

**Not worth it.**

### Latency Comparison

**tmpfs (our proposal):**

| Operation | NVMe (current) | tmpfs (RAM) | Savings |
|---|---|---|
| Slot save (~3.4 GB write) | ~1.7s (2 GB/s) | ~0.2s (15+ GB/s) | **~1.5s** |
| Slot restore (~3.4 GB read) | ~1.7s (2 GB/s) | ~0.2s (15+ GB/s) | **~1.5s** |
| **Total per swap** | **~3.4s** | **~0.4s** | **~3.0s per swap** |

With `huge=within_size` (transparent huge pages), expect another 10-15% improvement on the tmpfs side.

**LMCache benchmarks (not directly comparable):**

LMCache measures TTFT (Time To First Token) for prefix cache hits in multi-user serving:
- Long context prefix hit: ~2.6s → ~924ms median TTFT (~2x improvement)
- Multi-round QA: 3-10x faster than baseline

These numbers measure **skipping prefill computation** via KV cache reuse — not file I/O speed. They're not comparable to our tmpfs use case, which measures slot save/restore I/O latency.

### Bottom Line: tmpfs vs LMCache for Our Setup

| Approach | Swap I/O latency | NVMe wear | Complexity | llama.cpp compatible? |
|---|---|---|---|---|
| Current (NVMe slots) | ~3.4s | 1.13 TB/day | Low | ✅ |
| **tmpfs slots** | **~0.4s** | **0 TB/day** from slots | **Low** (one mount command) | **✅** |
| LMCache (hypothetical) | N/A — different architecture | Depends on backend tier | High (vLLM rewrite) | ❌ |

**Verdict:** tmpfs is the right tool. LMCache is for enterprise multi-GPU clusters with vLLM. For single-GPU local inference with llama.cpp, tmpfs is simpler, faster for slot I/O, and requires zero code changes.
