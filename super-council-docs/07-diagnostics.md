# Diagnostics & Troubleshooting

> Debug techniques, common issues, and recovery procedures for the super-council.

## Health Checks

### Supervisor Status

```bash
# Quick health check
curl http://127.0.0.1:8090/health
# → {"ok": true, "supported_features": {...}}

# Detailed stats
curl http://127.0.0.1:8090/status
# → {swaps, cache_hits, uptime, current_alias, errors}

# Upstream metrics
curl http://127.0.0.1:8090/metrics
# → llama-server internal metrics
```

### Memsearch Stats

```bash
curl http://127.0.0.1:8090/v1/council/memsearch-stats
# → {"available": true, "total_chunks": 470, "indexed_sources": [...]}
```

## Common Issues

### 1. Delegation Returns 409

**Symptom:** `{"error": "Delegation already in progress", "status": 409}`

**Cause:** Concurrent delegation attempt. Delegation lock held by another request.

**Fix:** Wait for current delegation to complete. Check `/status` for `_delegating` state.

### 2. Delegation Returns 503

**Symptom:** `{"error": "System unstable — swap-back failed", "status": 503}`

**Cause:** `_system_error` set (swap-back failed twice consecutively).

**Fix:**
```bash
# Option A: Wait for auto-recovery (30s intervals, 5 attempts max)
# Option B: Manual restart
curl -X POST http://127.0.0.1:8090/v1/council/restart
```

### 3. Slot Restore Fails

**Symptom:** Restore timeout or checksum mismatch.

**Cause:** Slot bin corrupted or config hash changed.

**Fix:**
```bash
# Check slot metadata
cat ~/tmp/llama-slots/<alias>/<config_hash>/slot-0.json

# Invalidate slot (forces cold start)
rm ~/tmp/llama-slots/<alias>/<config_hash>/slot-0.bin*
rm ~/tmp/llama-slots/<alias>/<config_hash>/slot-0.json

# Restart upstream to reload model
curl -X POST http://127.0.0.1:8090/v1/council/restart
```

### 4. Pipeline Stuck in Phase

**Symptom:** Pipeline not advancing, same phase repeated.

**Cause:** Phase retries exhausted → retreat to SCOUT. Or global ceiling hit → FAILED.

**Debug:**
```python
from super_council.super_council import PipelineState
ps = PipelineState.from_file("pipe-abc123")
print(f"Phase: {ps.phase}")
print(f"Status: {ps.status}")
print(f"Global attempts: {ps.global_attempts}/{ps.max_global_attempts}")
print(f"Phase attempts: {ps.phase_attempts}")
print(f"History: {ps.history}")
```

### 5. FK Constraint Violation

**Symptom:** `IntegrityError: FOREIGN KEY constraint failed`

**Cause:** Artifact enrichment called before artifact exists in DB.

**Fix:** Ensure `_record_transition()` completes before `enrich_artifact()`. The pipeline flow handles this automatically.

### 6. Context Budget Exhaustion in Delegation

**Symptom:** Delegation loop exits early with truncated response.

**Cause:** Cumulative tokens exceed 80% of context limit.

**Debug:** Check logs for `Pre-send budget exceeded` messages.

**Fix:** Reduce task size or use model with larger context.

### 7. Server Flags Not Passed to Upstream

**Symptom:** Model runs with wrong settings (no MTP, no flash attention, wrong sampling params). Performance significantly worse than debug server.

**Cause:** `server_flags` not wired from config to `build_args()`. Or `upstream-config.json` not loaded.

**Debug:**
```bash
# Check if supervisor is loading upstream config
tail -5 /tmp/super-council.log | grep "Loaded"
# Should show: "Loaded 14 models from .../upstream-config.json (subsystem config: .../config-subsystem.json)"

# Verify server_flags are populated
python3 -c "
import sys; sys.path.insert(0, '.')
from super_council.super_council import ModelRegistry
reg = ModelRegistry('super_council/config-subsystem.json', 'super_council/upstream-config.json')
cfg = reg.get_config('qwen-160k-UD-fast')
print(f'server_flags keys: {len(cfg.server_flags)}')
print(f'alias: {cfg.alias}')
"
# Should show: server_flags keys: 20, alias: qwen-160k-UD-fast
```

**Fix:** Ensure `--upstream-config` points to `upstream-config.json` (default). Verify `server_flags=extra` in `ModelRegistry.load()`.

### 8. Config Hash Mismatch (Cold Starts)

**Symptom:** Every request triggers a cold start (~165s prefill) instead of slot restore.

**Cause:** Config hash changed (model path, ctx_size, ngl, ctk, ctv, upstream_bin). Existing slot bins from old config are incompatible.

**Debug:**
```bash
# Check current config hash
python3 -c "
import sys; sys.path.insert(0, '.')
from super_council.super_council import ModelRegistry
reg = ModelRegistry('super_council/config-subsystem.json', 'super_council/upstream-config.json')
cfg = reg.get_config('qwen-160k-UD-fast')
print(f'Current hash: {cfg.config_hash()}')
"
# Check existing slot hashes
ls ~/Coding-Projects/7-council/super_council/slots/Qwen3.6-27B-UD-Q4_K_XL/
```

**Fix:** Clear stale slot bins to force fresh save with new hash:
```bash
rm -rf ~/Coding-Projects/7-council/super_council/slots/<model>/<old-hash>/
```

### 9. Worktree Cleanup Failure

**Symptom:** Stale worktrees in `~/.council-memory/worktrees/`.

**Cause:** Delegation interrupted before cleanup.

**Fix:**
```bash
# Manual cleanup
rm -rf ~/.council-memory/worktrees/<task_id>
git worktree remove ~/.council-memory/worktrees/<task_id> 2>/dev/null
```

## Debug Techniques

### Root Cause Tracing

Trace backward through the call chain:

1. Check supervisor log: `tail -100 /tmp/slot-supervisor.log`
2. Check Tier 1 memory: `tail -50 ~/.council-memory/daily/YYYY-MM-DD.md`
3. Check pipeline state: `cat ~/.council-memory/pipelines/<pipeline_id>.json`
4. Check phase state: `cat ~/.council-memory/phase-state/<task_id>.json`

### Defense-in-Depth Validation

Add validation at every layer:

1. **Input:** Validate payload fields before processing
2. **Transition:** Validate `VALID_TRANSITIONS` before state change
3. **Database:** FK enforcement blocks orphaned rows
4. **Output:** Schema validation on phase results

### Condition-Based Waiting

Replace arbitrary timeouts with condition polling:

```python
# Instead of: time.sleep(5)
# Use: Poll until condition met
while not condition_met():
    time.sleep(0.2)  # 200ms poll interval
```

## State Machine Linting

```python
from super_council.state_linter import StateMachineLinter
from super_council.super_council import PipelineState

linter = StateMachineLinter(
    phases=list(PipelineState.ALL_PHASES),
    transitions=dict(PipelineState.VALID_TRANSITIONS),
    terminal_phases=set(PipelineState.TERMINAL_PHASES),
)
findings = linter.lint()

# Check for critical issues
critical = [f for f in findings if f['severity'] == 'CRITICAL']
if critical:
    print("CRITICAL issues found:")
    for f in critical:
        print(f"  {f['check']}: {f['message']}")
```

## Recovery Procedures

### Soft Recovery (Upstream Restart)

```bash
curl -X POST http://127.0.0.1:8090/v1/council/restart
```

- Saves slot → stops llama-server → starts llama-server → waits for health → restores slot
- Use after upstream crashes or model loading issues

### Hard Recovery (Supervisor Restart)

```bash
curl -X POST http://127.0.0.1:8090/v1/council/supervisor-restart
```

- Saves slot → stops upstream → `os.execv` replaces process in-place
- Use after supervisor code changes, config changes, or persistent errors

### Emergency Recovery

```bash
# Only if restart hooks fail:
# 1. Check if llama-server is running
ps aux | grep llama-server

# 2. Check supervisor log for errors
tail -200 /tmp/slot-supervisor.log | grep -i error

# 3. Manual restart (LAST RESORT — loses in-flight KV cache)
# Do NOT use kill -9. Use SIGTERM:
kill $(pgrep -f slot-supervisor) 2>/dev/null
kill $(pgrep -f llama-server) 2>/dev/null
```

## Performance Tuning

### Swap Timing

- **Cold start:** ~165s (full prefill)
- **Slot restore:** ~5s (from tmpfs)
- **Overlap swap:** ~3s savings (parallel VRAM wait + model load)

### Context Budget

| Model | Context | Pre-send threshold (80%) |
|-------|---------|--------------------------|
| qwen3.6-27B-chair | 96K | 76.8K |
| reviewer-logic | 131K | 104.8K |
| builder | 120K | 96K |
| specialist-coder | 100K | 80K |

### WAL Checkpointing

- `wal_autocheckpoint = 0` (manual only)
- Checkpoint after each transition commit
- Prevents WAL file growth during long pipelines

## Log Analysis

### Supervisor Log Patterns

```
DELEGATION START: chair → reviewer-logic        # Delegation initiated
DELEGATION: task length=2400 chars, timeout=300  # Task details
Saved chair slot before delegation               # Slot saved
DELEGATION: active recall injected (512 chars)   # Recall added
DELEG-ROUND[0→reviewer-logic]: 2 msgs, 3200 chars  # Round start
Pre-send budget exceeded (round 5, 96000/120000)  # Context budget hit
=== DELEGATION END: reviewer-logic → chair ===   # Swap-back complete
```

### Council Memory Patterns

```
| Time | Event | Model | Detail | Status | Duration |
|------|-------|-------|--------|--------|----------|
| 14:23 | chat | qwen3.6-27B-chair | 12,400→12,847 (+447) [HIT] | 200 | 31200ms |
| 14:24 | deleg | qwen3.6-27B-chair→reviewer-logic | task:2,400ch ✅ | 200 | 18400ms |
| 14:25 | ⚠️ COMPACT | qwen3.6-27B-chair | 12,847→8,901 (-31%) | — | — |
```

**COMPACT warning:** Token count dropped >30% → KV cache compaction detected.
