# llama-swap Slot Persistence & Memory Management Investigation

| Field | Value |
|-------|-------|
| Project ID | `super-council` |
| Primary entity ID | `99070a` |
| Entity type | `session` |
| Short description | Investigate llama-swap slot restore behavior, cache miss after OOM restart, mlock/mmap configuration, and memory management for Qwen3.6-27B MTP model |
| Status | `draft` |
| Source references | See "Project Context" block below |
| Generated | 19-06-2026 |
| Next action / owner | Agent: execute investigation phases in order; focus on Phase 2 (cache miss root cause) as highest priority |

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`

**Key files for this task:**

| File | Purpose |
|------|---------|
| `/home/chief/llama-swap/config.yaml` | llama-swap model config (all 9 models, routing, slotStore) |
| `/home/chief/llama-swap/internal/slotstore/store.go` | Slot save/restore implementation (Save, Restore functions) |
| `/home/chief/llama-swap/internal/slotstore/hook.go` | Swap hook: BeforeStop (save), AfterReady (restore) |
| `/home/chief/.config/systemd/user/llama-swap.service` | Service unit file |
| `/home/chief/.config/systemd/user/llama-swap.service.d/override.conf` | Service override (ExecStartPre, ReadWritePaths) |
| `/home/chief/Coding-Projects/7-council/council-config/slots/qwen-160k-UD-fast/slot-0.bin` | KV cache slot file (2.2 GB) |
| `/home/chief/Coding-Projects/7-council/council-config/slots/qwen-160k-UD-fast/slot-0.json` | Slot metadata (model_id, tokens, timestamps) |
| `/home/chief/Coding-Projects/7-council/council-config/slots/models/Qwen3.6-27B-UD-Q4_K_XL.gguf` | Model on tmpfs (17.9 GB) |

**Related codebases:**

| Path | Purpose |
|------|---------|
| `/home/chief/llama-cpp-latest/` | llama.cpp build (llama-server binary) |
| `/home/chief/llama-swap/` | llama-swap Go source (fork of mostlygeek/llama-swap) |
| `/home/chief/Coding-Projects/7-council/codeneedle/docs/slot-supervisor.py` | Reference: Python slot-supervisor (NOT currently in use) |

---

## Background & Known State

### Architecture

```
Client (Pi/Council) → llama-swap (:9292, Go proxy) → llama-server (:10007, C++)
                                                    ↓
                                            slot-0.bin (tmpfs, 2.2 GB)
```

- **llama-swap** (Go binary, PID 61992): model swap proxy, systemd user service
- **llama-server** (C++ binary, PID 62124): child process, launched by llama-swap
- **Model**: Qwen3.6-27B-UD-Q4_K_XL on tmpfs, 17.9 GB, all 99 layers on GPU (ngl=99)
- **Speculative decoding**: MTP (Multi-Token Prediction), `--spec-type draft-mtp --spec-draft-n-max 3`
- **Context**: `--ctx-size 110592` (less than `n_ctx_train=262144`)

### Current Server Flags (Qwen model only)

```
--flash-attn on --mlock        ← NOTE: --no-mmap is MISSING (all other 8 models have it)
--cont-batching -np 1 -b 512 -ub 512
--threads 16 --threads-batch 16
--cache-ram 16192
--spec-type draft-mtp --spec-draft-n-max 3
--spec-draft-type-k f16 --spec-draft-type-v f16
```

### Timeline (June 19, 2026)

| Time (IST) | Event |
|---|---|
| 15:53:00 | Previous llama-swap instance saved slot: 61114 tokens |
| 21:32:08 | Last request before OOM: 98KB response, 1m29s duration |
| **21:35:36** | **OOM KILL** — previous llama-swap (PID 32533) killed by OOM killer |
| 21:35:36 | Previous instance consumed: 50min 13s CPU, **13.2G memory peak**, 0B swap |
| 21:35:38 | systemd marked service as `Failed with result 'oom-kill'` |
| 21:35:43 | systemd restart: ExecStartPre copies model to tmpfs (`cp -n`) |
| 21:35:43 | llama-swap (PID 61992) starts, slotstore hook configured (9 models) |
| 21:35:55 | llama-server starts, VRAM check: 15 MB free (< 1024 MB threshold) |
| 21:36:00 | Health check passed |
| **21:36:03** | **Slot restore complete: 61114 tokens** (saved_at=15:53, restored_at=16:06 UTC) |
| 21:37:55 | First request: **cache_tokens=0**, input_tokens=60375, duration=120s |
| 21:38:30 | Second request: **cache_tokens=0**, input_tokens=1317, duration=154s |
| 21:39:12 | Third request: **cache_tokens=0**, input_tokens=34936, duration=42s |
| 21:39:15 | Fourth request: **cache_tokens=35075**, input_tokens=19, duration=3s ← first cache hit |

### Process Memory State (current, PID 62124)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| VmPeak | 159 GB | Virtual address space (mmap'd model + allocations) |
| VmSize | 159 GB | Current virtual size |
| **VmLck** | **698 MB** | **Locked pages — only 698 MB despite --mlock** |
| VmHWM | 17.8 GB | High water mark (peak RSS) |
| VmRSS | 11.9 GB | Currently resident in RAM |
| VmSwap | 0 | Nothing swapped to disk |
| Threads | 22 | Main + batch threads + CUDA threads |

### tmpfs Mount

```
tmpfs on /home/chief/Coding-Projects/7-council/council-config/slots
  type tmpfs (rw,relatime,size=50331648k,inode64,huge=within_size,noswap)
  Size: 48G, Used: 20G, Available: 29G
```

- Model file (17.9 GB) + slot bin (2.2 GB) = ~20 GB on tmpfs
- `noswap` flag: tmpfs pages cannot be swapped to disk, but CAN be evicted to make room

---

## Issues to Investigate

### Issue 1: Cache Miss After Slot Restore (HIGH PRIORITY)

**Observation:** Slot restore reported 61114 tokens restored, but the first 3 requests after restart all show `cache_tokens=0`. The fourth request shows `cache_tokens=35075` (cache warming).

**Hypotheses (ranked by likelihood):**

1. **Conversation context mismatch:** The restored slot contains the KV cache from the PREVIOUS conversation session. The first request after restart sent a NEW conversation (different system prompt, different messages), so llama.cpp couldn't match the restored cache to the new prompt. The full prefill was necessary.

2. **Slot restore timing:** The slot was restored at 21:36:03, but the first request at 21:37:55 may have been sent BEFORE llama-server fully initialized the slot state. Check if there's a race condition between restore completion and request readiness.

3. **MTP draft context incompatibility:** With `--spec-type draft-mtp`, the MTP draft heads may not be compatible with restored KV cache. The "creating MTP draft context" log (128 lines) may indicate the draft context was rebuilt from scratch, invalidating the restored cache.

4. **f_keep truncation:** llama.cpp uses `f_keep` parameter to determine how many initial tokens to preserve from the restored cache. If the new prompt diverges early, the entire cache could be discarded.

**Investigation needed:**
- Check the actual prompt sent in request 0 vs the restored context
- Examine llama-server logs for `f_keep`, `n_matched`, or cache match statistics
- Check if MTP speculative decoding has known issues with slot restore
- Test: send the EXACT same prompt that was in the saved slot and measure cache_tokens

### Issue 2: Missing `--no-mmap` on Qwen Model (MEDIUM PRIORITY)

**Observation:** The Qwen model config has `--mlock` but NOT `--no-mmap`. All other 8 models in the config have BOTH flags: `--no-mmap --mlock`.

```yaml
# Qwen (MISSING --no-mmap):
--flash-attn on --mlock

# All others (correct):
--flash-attn on --no-mmap --mlock
```

**Impact:** Without `--no-mmap`, llama.cpp memory-maps the model file. The OS can page out mmap'd regions even with `--mlock` in certain conditions (mlock locks pages after they're faulted in, but mmap allows the OS to manage page tables differently). With `--no-mmap`, the model is read directly into memory via `read()`, then `mlock()` locks those pages — more reliable for preventing pageouts.

**However:** Since the model is on tmpfs (RAM-backed), mmap should still be fast. The real question is whether tmpfs pages can be evicted under memory pressure. The `noswap` mount option prevents swap, but tmpfs pages CAN be reclaimed by the kernel's page cache pressure.

**Investigation needed:**
- Add `--no-mmap` to Qwen config and measure startup time difference
- Monitor tmpfs page eviction under load (check `/proc/meminfo` for `Shmem` vs `Buffers`)
- Check if the 698 MB VmLck is sufficient or if more should be locked

### Issue 3: OOM Kill Root Cause (MEDIUM PRIORITY)

**Observation:** Previous llama-swap instance (PID 32533) was OOM-killed after consuming 13.2 GB peak memory. The systemd service has `MemoryMax=24G` (from override).

**Questions:**
- Why did 13.2 GB trigger OOM? The limit is 24G.
- Was this the llama-swap process itself or the llama-server child?
- Did the OOM happen during a swap operation or during normal inference?
- Is the `arc-summarizer` process (PID 2023, running LFM2.5-8B on :18095) contributing to system-wide memory pressure?

**Investigation needed:**
- Check `dmesg | grep -i oom` for OOM killer details
- Check if system-wide memory was exhausted (not just cgroup limit)
- Monitor memory usage during long-running sessions
- Consider if `--cache-ram 16192` (16 GB) is too high given 24 GB cgroup limit

### Issue 4: `--swa-full` Flag Relevance (LOW PRIORITY)

**Observation:** User asked about `--swa full` flag. This is `--swa-full` in llama.cpp: "use full-size SWA cache (default: false)".

**Finding:** SWA = Sliding Window Attention. This flag is for models that use sliding window attention (e.g., Gemma, Phi). It controls whether the KV cache uses full-size windows or optimized truncated windows. **This is NOT related to memory swapping.**

**Conclusion:** `--swa-full` is NOT needed for Qwen3.6-27B (which uses standard attention, not SWA). Only relevant for Gemma models in the config.

### Issue 5: MTP Draft Context "Slow" (RESOLVED)

**Observation:** User noted "creating MTP draft context against the target model" appears 128 times and seems slow.

**Finding:** All 128 lines share the SAME millisecond timestamp (`0.04.740.925`). This is verbose logging from llama.cpp's MTP initialization loop (one log per draft head). The actual processing time is negligible — the 128 lines are logged near-simultaneously.

**Conclusion:** Not a real performance issue. The verbose logging creates the illusion of slowness. The actual bottleneck is elsewhere (model loading, slot restore, or prompt prefill).

---

## Investigation Phases

### Phase 1: Reproduce & Measure Cache Behavior

**What:** Reproduce the post-restart cache miss pattern with controlled testing.

**Steps:**
1. Send a known prompt to the Qwen model and let it generate a response (build up cache)
2. Check metrics: `curl -s http://127.0.0.1:9292/api/events` — note cache_tokens progression
3. Trigger a controlled restart: `systemctl --user restart llama-swap`
4. Immediately after restart, send the EXACT SAME prompt
5. Measure: cache_tokens, prompt_per_second, total duration
6. Compare with sending a DIFFERENT prompt (control group)

**Expected outcomes:**
- If cache_tokens > 0 with same prompt: slot restore IS working, original issue was context mismatch
- If cache_tokens = 0 with same prompt: slot restore has a bug (MTP incompatibility, timing, or format issue)

**Verification:**
- [ ] Same prompt after restart shows cache_tokens > 0
- [ ] Different prompt after restart shows cache_tokens = 0 (expected)
- [ ] Prompt processing speed is consistent with cache hit/miss

### Phase 2: Examine llama-server Slot Restore Internals

**What:** Understand how llama-server handles slot restore with MTP speculative decoding.

**Steps:**
1. Check llama-server source for slot restore + MTP interaction:
   ```bash
   grep -rn "mtp\|spec_draft\|slot.*restore\|n_matched" /home/chief/llama-cpp-latest/src/ --include="*.cpp" | grep -i "slot\|restore\|cache" | head -30
   ```
2. Check if MTP draft context is rebuilt on slot restore (would invalidate KV cache)
3. Check llama.cpp `common.cpp` or `server.cpp` for `f_keep` behavior with restored slots
4. Look for `llama_kv_cache_seq_keep` or similar calls in the restore path

**Key files:**
- `/home/chief/llama-cpp-latest/src/llama.cpp` — core KV cache operations
- `/home/chief/llama-cpp-latest/examples/server/server.cpp` — slot restore endpoint
- `/home/chief/llama-cpp-latest/src/llama-sampling.cpp` — MTP speculative decoding

**Verification:**
- [ ] Identified whether MTP draft context rebuild invalidates restored KV cache
- [ ] Documented the slot restore → cache match code path
- [ ] Found any known issues in llama.cpp GitHub regarding MTP + slot restore

### Phase 3: Memory Configuration Audit

**What:** Audit and fix memory management flags.

**Steps:**
1. **Add `--no-mmap` to Qwen config:**
   - Edit `/home/chief/llama-swap/config.yaml`
   - Change `--flash-attn on --mlock` to `--flash-attn on --no-mmap --mlock`
   - Restart llama-swap, measure startup time difference
   - Check VmLck after startup (should be higher with --no-mmap + --mlock)

2. **Evaluate `--cache-ram` setting:**
   - Current: `--cache-ram 16192` (16 GB for KV cache)
   - With 24 GB cgroup limit and 17.9 GB model, this may be too aggressive
   - Consider reducing to 8192 or 10240 to leave headroom

3. **Check tmpfs eviction behavior:**
   ```bash
   # Monitor tmpfs page cache
   cat /proc/meminfo | grep -E "Shmem|Buffers|Cached|MemFree"
   # Check if model file is in page cache
   vmtouch -v /home/chief/Coding-Projects/7-council/council-config/slots/models/Qwen3.6-27B-UD-Q4_K_XL.gguf 2>/dev/null || echo "vmtouch not installed"
   ```

**Verification:**
- [ ] Qwen model has `--no-mmap` flag (consistent with all other models)
- [ ] VmLck reflects full model lock (or explains why it doesn't)
- [ ] No OOM kills after configuration change
- [ ] Startup time documented (with and without --no-mmap)

### Phase 4: OOM Kill Root Cause Analysis

**What:** Determine why the previous instance was OOM-killed at 13.2 GB peak.

**Steps:**
1. Check kernel OOM logs:
   ```bash
   dmesg | grep -A 20 -i "oom\|killed process" | tail -40
   ```
2. Check if it was cgroup OOM or system-wide OOM:
   ```bash
   journalctl --user -u llama-swap --no-pager | grep -i "oom\|kill\|memory"
   ```
3. Check current system memory state:
   ```bash
   free -h
   cat /proc/meminfo | head -20
   ```
4. Check if arc-summarizer (PID 2023) is contributing:
   ```bash
   cat /proc/2023/status | grep -E "Vm|Rss|Swap"
   ```

**Verification:**
- [ ] OOM cause identified (cgroup limit vs system-wide vs CUDA memory)
- [ ] Memory limits are appropriate for workload
- [ ] No competing processes causing memory pressure

### Phase 5: Slot Save Timing During OOM

**What:** Verify that slot save completed BEFORE the OOM kill.

**Steps:**
1. Check slot-0.bin modification time vs OOM kill time:
   - slot-0.bin modified: 21:22 (from `ls -la`)
   - OOM kill: 21:35:36
   - **Gap: 13 minutes** — slot was saved well before OOM
2. Check if llama-swap's `BeforeStop` hook was called:
   - OOM kill is abrupt — `BeforeStop` may NOT have been called
   - The slot was saved at 21:22, which was during normal operation (periodic save or explicit save)
3. Verify: does llama-swap save slots periodically or only on swap/stop?

**Key code path:** `hook.go:BeforeStop()` is only called during intentional swap. OOM kill bypasses this entirely.

**Verification:**
- [ ] Confirmed slot save mechanism (periodic vs on-demand)
- [ ] Documented risk: OOM kill may lose unsaved context
- [ ] Recommended: add periodic auto-save or SIGTERM handler

---

## Constraints

- **Do NOT modify running config without testing first** — any config change requires restart and validation
- **Port 9292 is the production proxy** — all Pi/Council traffic goes through llama-swap
- **Port 10007 is the upstream llama-server** — restarts are expected during model swaps
- **tmpfs is volatile** — model file is copied from NVMe on each service start (`ExecStartPre`)
- **Single GPU** — all models serialize through one RTX 3090 (24 GB VRAM)
- **MTP model is the default** — Qwen3.6-27B is the co-chair model; downtime affects all council operations

---

## Success Criteria

- [ ] Root cause of cache miss after slot restore identified (context mismatch vs MTP bug vs timing)
- [ ] Reproducible test case: same prompt after restart → cache hit confirmed or bug documented
- [ ] Qwen model config has `--no-mmap` flag (consistent with all other models)
- [ ] OOM kill root cause identified and mitigated
- [ ] Memory configuration validated (VmLck, cache-ram, cgroup limits)
- [ ] Slot save reliability documented (periodic vs on-demand, OOM safety)
- [ ] `--swa-full` confirmed as NOT needed for Qwen (SWA-only flag)
- [ ] MTP draft context "slowness" confirmed as logging-only (no real delay)
- [ ] All findings documented with evidence (timestamps, metrics, code references)

---

## Caveats & Uncertainty

1. **Cannot capture llama-server stdout directly** — output goes to pipe consumed by llama-swap. The `captureBuffer: 15` config captures last 15 lines, but there's no API endpoint to retrieve them (404 on `/capture`). May need to modify llama-swap to expose capture buffer or redirect stdout to file.

2. **Slot restore internals are opaque** — llama-swap's `Restore()` function calls llama-server's `/slots/0?action=restore` endpoint, but the actual KV cache loading happens inside llama-server. Without access to llama-server's internal logging, we can only infer behavior from cache_tokens metrics.

3. **MTP + slot restore compatibility is unknown** — llama.cpp's MTP speculative decoding may have undocumented interactions with slot restore. The 128 "creating MTP draft context" logs suggest the draft context is rebuilt, which may or may not invalidate the restored KV cache.

4. **OOM kill timing is ambiguous** — the OOM happened at 21:35:36, but we don't know if it was triggered by the llama-swap cgroup limit (24G) or system-wide memory pressure. The arc-summarizer process (PID 2023) running LFM2.5-8B may be contributing.

5. **tmpfs eviction under pressure** — even with `noswap` mount option, tmpfs pages can be reclaimed by the kernel. With only 29 GB available on a 48 GB tmpfs and a 17.9 GB model, there's limited headroom if other processes need memory.

---

## References

- llama-swap config: `/home/chief/llama-swap/config.yaml`
- llama-swap source: `/home/chief/llama-swap/internal/slotstore/` (store.go, hook.go)
- Service unit: `~/.config/systemd/user/llama-swap.service` + override
- llama.cpp help: `/home/chief/llama-cpp-latest/build/bin/llama-server --help`
- Journal: `journalctl --user -u llama-swap --no-pager`
- Metrics API: `curl -s http://127.0.0.1:9292/api/events` (SSE stream)
- Props API: `curl -s http://127.0.0.1:10007/props`
