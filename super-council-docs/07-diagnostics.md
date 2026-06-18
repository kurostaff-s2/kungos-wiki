# Diagnostics & Troubleshooting

> Debug techniques, common issues, and recovery procedures for the super-council.

## Health Checks

### llama-swap Status

```bash
# Service status
systemctl --user status llama-swap.service

# Running models
curl http://127.0.0.1:9292/running
# → {"running": [{"model": "qwen-160k-UD-fast", "state": "ready", ...}]}

# All models
curl http://127.0.0.1:9292/v1/models
# → {"models": [{"id": "qwen-160k-UD-fast", ...}]}

# Slot persistence status
curl http://127.0.0.1:9292/api/slots/status
# → [{"model_id": "qwen-160k-UD-fast", "enabled": true, "slot_count": 0, ...}]

# Manual slot save/restore
curl -X POST http://127.0.0.1:9292/api/slots/save/qwen-160k-UD-fast
curl -X POST http://127.0.0.1:9292/api/slots/restore/qwen-160k-UD-fast
curl -X POST http://127.0.0.1:9292/api/slots/cleanup
```

### Memory Service Status

```bash
# Service status
systemctl --user status memory-service.service

# MCP SSE endpoint
curl http://127.0.0.1:18097/sse
```

### Memsearch Stats

```bash
# Service status
systemctl --user status memsearch-watch.service

# Milvus port check
ss -tlnp | grep 19530

# DB location
ls -la ~/.memsearch/milvus.db/
```

### Arc LLM Status

```bash
# Service status (port 18095)
curl http://127.0.0.1:18095/health
```

## Common Issues

### 1. Slot Restore Fails

**Symptom:** Restore timeout or checksum mismatch in llama-swap logs.

**Cause:** Slot bin corrupted or config hash changed (model path, ctx_size, ngl, ctk, ctv).

**Fix:**
```bash
# Check slot metadata
cat ~/Coding-Projects/7-council/council-config/slots/<model_id>/<config_hash>/slot-0.json

# Invalidate slot (forces cold start)
rm ~/Coding-Projects/7-council/council-config/slots/<model_id>/<config_hash>/slot-0.bin*
rm ~/Coding-Projects/7-council/council-config/slots/<model_id>/<config_hash>/slot-0.json

# Or trigger cleanup for all models
curl -X POST http://127.0.0.1:9292/api/slots/cleanup
```

### 2. llama-swap OOM Kill

**Symptom:** Service restarts unexpectedly, `MemoryMax` exceeded.

**Cause:** `MemoryMax` in systemd unit too low for model's RSS + swap usage.

**Fix:**
```bash
# Check current limit
grep MemoryMax ~/.config/systemd/user/llama-swap.service
# Should be 8G for 27B models

# Reload and restart
systemctl --user daemon-reload
systemctl --user restart llama-swap.service
```

### 3. Stream Errors (Stream ended without finish_reason)

**Symptom:** LLM responses cut off mid-stream, `Connection error` in logs.

**Cause:** llama-server overloaded (CPU at 100%) or OOM-killed. Check `MemoryMax` and VRAM usage.

**Fix:**
```bash
# Check llama-swap logs for OOM
journalctl --user -u llama-swap.service --no-pager -n 50 | grep -i "oom\|kill\|memory"

# Check VRAM
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

# If VRAM is near 24GB, reduce context size or batch size
```

### 4. Milvus Lite WAL Corruption

**Symptom:** `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc0` in memsearch-watch logs.

**Cause:** Corrupted WAL database (unclean shutdown, OOM kill, or memsearch bug).

**Fix:**
```bash
# Backup and delete corrupted DB
mv ~/.memsearch/milvus.db ~/.memsearch/milvus.db.bak
systemctl --user restart memsearch-watch.service
# Service will rebuild index from source directories
```

### 5. Config Hash Mismatch (Cold Starts)

**Symptom:** Every request triggers a cold start (~165s prefill) instead of slot restore.

**Cause:** Config hash changed (model path, ctx_size, ngl, ctk, ctv, upstream_bin). Existing slot bins from old config are incompatible.

**Fix:** Clear stale slot bins to force fresh save with new hash:
```bash
rm -rf ~/Coding-Projects/7-council/council-config/slots/<model_id>/<old-hash>/
```

### 6. Pipeline Stuck in Phase

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

### 7. Worktree Cleanup Failure

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

1. Check llama-swap logs: `journalctl --user -u llama-swap.service --no-pager -n 100`
2. Check memory service logs: `journalctl --user -u memory-service.service --no-pager -n 100`
3. Check Tier 1 memory: `tail -50 ~/.council-memory/daily/YYYY-MM-DD.md`
4. Check pipeline state: `cat ~/.council-memory/pipelines/<pipeline_id>.json`
5. Check phase state: `cat ~/.council-memory/phase-state/<task_id>.json`

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

## Recovery Procedures

### llama-swap Restart

```bash
# Restart llama-swap (preserves slots if model is healthy)
systemctl --user restart llama-swap.service

# Check for OOM kills
journalctl --user -u llama-swap.service --no-pager -n 50 | grep -i "oom\|kill\|memory"
```

### Memory Service Restart

```bash
systemctl --user restart memory-service.service
```

### Memsearch Rebuild

```bash
# If Milvus DB is corrupted
mv ~/.memsearch/milvus.db ~/.memsearch/milvus.db.bak
systemctl --user restart memsearch-watch.service
```

### Emergency Recovery

```bash
# Only if systemd restart fails:
# 1. Check if llama-server is running
ps aux | grep llama-server

# 2. Check llama-swap logs
journalctl --user -u llama-swap.service --no-pager -n 200 | grep -i error

# 3. Manual restart (LAST RESORT — loses in-flight KV cache)
# Do NOT use kill -9. Use SIGTERM:
systemctl --user stop llama-swap.service
systemctl --user start llama-swap.service
```

## Performance Tuning

### Swap Timing

- **Cold start:** ~165s (full prefill, no slot available)
- **Slot restore:** ~5s (from tmpfs, slot available)
- **First swap pays prefill:** Slot reuse pays off from 2nd visit onward

### Context Budget

| Model | Context | Pre-send threshold (80%) |
|-------|---------|--------------------------|
| qwen-160k-UD-fast | 110K | 88K |
| qwen-uhn-fast | 98K | 78.4K |
| gemma-4-26b | 98K | 78.4K |
| nemotron-cascade | 98K | 78.4K |
| mellum2-12b | 98K | 78.4K |

### WAL Checkpointing

- `wal_autocheckpoint = 0` (manual only)
- Checkpoint after each transition commit
- Prevents WAL file growth during long pipelines

## Log Analysis

### llama-swap Log Patterns

```
INFO slotstore hook configured models=11           # Slot persistence active
INFO slotstore: restore triggered model=...        # Slot restore on startup
INFO <qwen-160k-UD-fast> Health check passed       # Model ready
INFO Request 127.0.0.1 "POST /v1/chat/completions"  # Active request
```

### Council Memory Patterns

```
| Time | Event | Model | Detail | Status | Duration |
|------|-------|-------|--------|--------|----------|
| 14:23 | chat | qwen-160k-UD-fast | 12,400→12,847 (+447) [HIT] | 200 | 31200ms |
| 14:24 | deleg | qwen-160k-UD-fast→reviewer-logic | task:2,400ch ✅ | 200 | 18400ms |
| 14:25 | ⚠️ COMPACT | qwen-160k-UD-fast | 12,847→8,901 (-31%) | — | — |
```

**COMPACT warning:** Token count dropped >30% → KV cache compaction detected.
