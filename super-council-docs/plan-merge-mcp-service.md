# Plan: Merge mcp_service into memory_service

## Summary

Remove the standalone mcp_service proxy layer. memory_service runs FastMCP SSE directly on port 18097 with all 22 tools registered. Extension reconnects to memory_service SSE and restores its PendingQueue for client-side retry. Restores correct MCP contract (named tools), eliminates broken proxy, reduces from 2 processes to 1.

## Current State

| Component | Port | Status |
|-----------|------|--------|
| memory_service SSE | 18096 | Running (pid 2042), 22 tools registered but extension doesn't connect here |
| memory_service HTTP | 18098 | Running (pid 2042), backend for mcp_service proxy |
| mcp_service SSE | 18097 | Running (pid 188642), **broken** — drops named tool calls |
| Pi extension | connects to 18097 | Tool calls dropped ("Tool 'upsert_summary' not listed") |

## Framework Decision: Stick with FastMCP

**Decision:** Keep FastMCP (mcp 1.27.1). Debug our integration bugs. Do NOT switch frameworks.

**Research summary:**

| Option | Verdict | Reason |
|--------|---------|--------|
| FastMCP (current) | ✅ Keep | Official SDK, 70% market share, our bugs are integration not framework |
| Raw MCP SDK | ❌ Reject | More boilerplate, no real value — we'd reimplement FastMCP's decorator/schema/transport layers |
| Custom Starlette + SSE | ❌ Reject | Rebuild MCP protocol from scratch, maintenance burden, no payoff |

**Known issues and fixes:**

| Issue | Root Cause | Fix |
|-------|------------|-----|
| SSE on 18096 instead of 18097 | Our integration bug (config loading or startup path), NOT FastMCP bug (`settings.port` correctly stores 18097) | Debug in Unit 1: add `log.info("FastMCP settings.port=%d", handler._mcp.settings.port)` before `handler.run()` |
| Schema mismatch (`arguments: Any`) | FastMCP generates `{"type":"string"}` for `Any` types | Use `**kwargs` in tool handlers (Unit 1) |
| Version outdated (1.27.1 → 1.27.2) | Minor update, no breaking changes | `pip install --upgrade mcp` (Unit 1) |

**Evidence:**
- `FastMCP(port=18097)` → `settings.port = 18097` ✓ (verified via Python REPL)
- `run_sse_async()` uses `self.settings.port` for uvicorn ✓ (verified via source inspection)
- Issue #636 (SSE port control) is **closed** — ephemeral SSE session port is protocol behavior, not a bug
- No FastMCP issues match our port binding symptom — it's our code path, not the framework

**Research-First Gate (per TDD skill):**

| Step | Source | Result |
|------|--------|--------|
| GitHub code search | `modelcontextprotocol/python-sdk` issues | Found #636 (closed, not our issue), #514 (shutdown, low impact) |
| Official docs | FastMCP source (`run_sse_async`, `__init__`) | Port param correctly passed to uvicorn; no framework bug |
| Package registries | PyPI `mcp` 1.27.1 → 1.27.2 | Minor update, no breaking changes |
| Web search | Alternatives (raw SDK, Starlette) | Raw SDK = more boilerplate, no value; Starlette = rebuild MCP protocol |
| Verdict | — | **FastMCP is fine. Our integration has bugs. Debug, don't switch.** |

## Implementation Units

---

### Unit 1: Move memory_service SSE to port 18097

**Scope:** memory_service SSE currently runs on 18096. Extension expects 18097. Move SSE to 18097 so extension connects to the right process after mcp_service is removed.

**Files:**
- `super_council/memory_service/__main__.py` — `_run_mcp_with_http()` port defaults
- `super_council/memory_service/config.py` — verify `MCPConfig.port` default is 18097
- `super_council/memory_service/mcp_server.py` — add debug log for `settings.port`
- `~/.config/systemd/user/memory-service.service` — verify ExecStart flags

**RED:** SSH into machine, run:
```bash
ss -tlnp | grep 18097
# Should show mcp_service (pid 188642), NOT memory_service
ss -tlnp | grep 18096
# Should show memory_service SSE
```
Expected: memory_service NOT on 18097.

**GREEN:**
1. **Upgrade FastMCP:** `pip install --upgrade mcp` (1.27.1 → 1.27.2)
2. **Add debug log** in `mcp_server.py` before `self._mcp.run()`: `log.info("FastMCP settings.port=%d host=%s", self._mcp.settings.port, self._mcp.settings.host)`
3. **Restart and check logs:** `systemctl --user restart memory-service` → `journalctl --user -u memory-service -n 20`
   - If log shows `settings.port=18096` → config loading bug (check `MemoryConfig.load()` → `MCPConfig` defaults)
   - If log shows `settings.port=18097` but uvicorn runs on 18096 → FastMCP bug (file issue, use raw uvicorn as workaround)
4. **Fix root cause** based on log evidence
5. **Remove debug log** after fix
6. Verify: `ss -tlnp | grep 18097` shows memory_service (NOT mcp_service)

**Verification:**
```bash
ss -tlnp | grep -E "1809[678]"
# Expected:
# 18097 → memory_service (SSE)
# 18098 → memory_service (HTTP)
# 18096 → nothing
```

**Dependencies:** none

**Notes:**
- Port 18096 mystery: config says 18097, `settings.port` stores 18097, but uvicorn runs on 18096. Debug log will reveal if it's config loading or FastMCP internals.
- If FastMCP truly ignores `port` for SSE (unlikely given source code), fallback: wrap in raw uvicorn with explicit port.

---

### Unit 2: Verify 22 tools work over SSE on 18097

**Scope:** Confirm all 22 tools are callable via SSE on the new port. Focus on `upsert_summary` (the broken one) and `council-recall` (the working one).

**Files:** none (verification only)

**RED:** Before mcp_service is stopped, test that memory_service SSE on 18097 accepts tool calls:
```bash
# Connect to SSE and call upsert_summary
curl -s -N http://127.0.0.1:18097/sse &
# Then POST tool call to messages endpoint
# Expected: upsert_summary works (direct to RelationalStore)
```

**GREEN:**
1. Stop mcp_service: `systemctl --user stop mcp-service 2>/dev/null; kill $(pgrep -f "mcp_service.*--sse") 2>/dev/null`
2. Test SSE connection: `curl -s -N http://127.0.0.1:18097/sse` (should return `event: endpoint`)
3. Test tool call via Pi extension or manual SSE client
4. Verify `upsert_summary` writes to `raw_session_memories` (not `session_diary`)
5. Verify `_try_index_raw_memory()` fires (check `is_indexed=1`)

**Verification:**
```sql
-- New entry should appear with is_indexed=1
SELECT trace_id, source_file, is_indexed, created_at
FROM raw_session_memories
ORDER BY created_at DESC LIMIT 1;
```

**Dependencies:** Unit 1

---

### Unit 3: Restore extension PendingQueue

**Scope:** The extension's `PendingQueue` was removed during mcp_service extraction. Restore it so the extension can queue failed calls and retry with exponential backoff.

**Files:**
- `~/.pi/agent/extensions/council-tools/index.ts` — add PendingQueue class + integrate into `callMemoryTool()`

**RED:** Call a tool when memory_service is down:
```typescript
// Stop memory_service
// Call callMemoryTool("upsert_summary", {...})
// Expected: error, no retry, call lost
```

**GREEN:**
1. Add `PendingQueue` class to index.ts (port from `mcp_service/retry.py` pattern):
   - File-based queue: `~/.council-memory/extension-pending/`
   - `add(toolName, params)` → JSON file with entry_id
   - `getReady()` → entries where `nextTry <= now` and `attempts < maxRetries`
   - `markSuccess(entryId)` → delete file
   - `markRetry(entryId)` → increment attempts, schedule backoff
   - Exponential backoff: 2s → 4s → 8s → ... → 5min max, 10 retries
2. Integrate into `callMemoryTool()`:
   ```typescript
   async function callMemoryTool(toolName, params) {
     try {
       return await memoryClient.callTool(toolName, params);
     } catch (err) {
       const entryId = pendingQueue.add(toolName, params);
       console.warn(`[council] queued for retry: id=${entryId} tool=${toolName}`);
       throw err; // Let caller know, queue handles retry
     }
   }
   ```
3. Add background drain loop (runs every 2s when extension is loaded):
   - `getReady()` → retry each via `callMemoryTool()` → `markSuccess()` or `markRetry()`
   - Stop draining if no pending entries

**Verification:**
1. Stop memory_service
2. Trigger upsert_summary (via assistant message that scores ≥ 4)
3. Check `~/.council-memory/extension-pending/` — entry should exist
4. Start memory_service
5. Within 2s, entry should be retried and deleted
6. Check `raw_session_memories` — new entry with `is_indexed=1`

**Dependencies:** none (can run in parallel with Unit 1)

---

### Unit 4: Update extension connection + remove mcp_service references

**Scope:** Extension connects to port 18097. After mcp_service removal, this is memory_service SSE. Update extension to remove mcp_service-specific logic and references.

**Files:**
- `~/.pi/agent/extensions/council-tools/index.ts` — update comments, remove mcp_service references

**RED:** Check extension for mcp_service references:
```bash
grep -n "mcp_service\|mcp-service\|18097" ~/.pi/agent/extensions/council-tools/index.ts
# Should find references to mcp_service that need updating
```

**GREEN:**
1. Update `MEMORY_PORT` comment: "18097" → "memory_service SSE port (was mcp_service)"
2. Remove any mcp_service-specific error handling (e.g., "mcp_service will retry" messages — now "PendingQueue will retry")
3. Update `unified_log_recall` channel descriptions: `mcp_queue` → `extension_queue`
4. Update tool descriptions that reference mcp_service

**Verification:**
```bash
grep -c "mcp_service" ~/.pi/agent/extensions/council-tools/index.ts
# Expected: 0 (or only in historical comments)
```

**Dependencies:** Unit 3

---

### Unit 5: Remove mcp_service package and systemd unit

**Scope:** Delete the mcp_service package, systemd unit, and pending queue directory. Clean up completely.

**Files:**
- `super_council/mcp_service/` — delete entire directory
- `~/.config/systemd/user/mcp-service.service` — delete
- `~/.council-memory/mcp-pending/` — delete (queue data migrated to extension-pending)

**RED:** Verify mcp_service is not needed:
```bash
# Check if anything references mcp_service
grep -r "mcp_service\|mcp-service" ~/Coding-Projects/7-council/super_council/ --include="*.py" --include="*.json" --include="*.md" | grep -v "mcp_service/" | grep -v ".pyc"
# Should find only docs and this plan
```

**GREEN:**
1. Stop mcp_service: `systemctl --user stop mcp-service 2>/dev/null; systemctl --user disable mcp-service 2>/dev/null`
2. Kill any remaining processes: `pkill -f "mcp_service.*--sse"`
3. Delete package: `rm -rf ~/Coding-Projects/7-council/super_council/mcp_service/`
4. Delete systemd unit: `rm ~/.config/systemd/user/mcp-service.service`
5. Reload systemd: `systemctl --user daemon-reload`
6. Delete old queue: `rm -rf ~/.council-memory/mcp-pending/`
7. Verify port 18097 is free for memory_service: `ss -tlnp | grep 18097` (should show nothing or memory_service)

**Verification:**
```bash
# No mcp_service processes
pgrep -f "mcp_service" || echo "No mcp_service processes ✓"

# No mcp_service package
ls ~/Coding-Projects/7-council/super_council/mcp_service/ 2>&1 | grep "No such file"

# No systemd unit
systemctl --user status mcp-service 2>&1 | grep "not found"

# Port 18097 available for memory_service
ss -tlnp | grep 18097 || echo "Port 18097 free ✓"
```

**Dependencies:** Unit 1, Unit 2 (verify memory_service works on 18097 first)

---

### Unit 6: Update documentation

**Scope:** Update 09-memory-service.md and MEMORY.md to reflect new architecture.

**Files:**
- `~/llm-wiki/super-council-docs/09-memory-service.md` — remove mcp_service section, update architecture diagram
- `~/.pi/agent/memory/MEMORY.md` — update services table, remove mcp_service

**RED:** Check docs for mcp_service references:
```bash
grep -c "mcp_service\|mcp-service" ~/llm-wiki/super-council-docs/09-memory-service.md
# Should find many references
```

**GREEN:**
1. **09-memory-service.md:**
   - Remove "mcp_service (Standalone Transport Layer)" section entirely
   - Update architecture diagram: Extension → memory_service SSE (direct)
   - Update "Two Access Patterns" table: remove mcp_service row
   - Update "SSE Protocol Flow" diagram: remove mcp_service hop
   - Update "Transport" section: memory_service SSE is primary (18097), HTTP is debug-only (18098)
   - Update "Configuration" section: remove mcp_service config
   - Update "File Locations" section: remove mcp_service files
   - Update "Environment Variables" section: remove COUNCIL_MCP_* vars

2. **MEMORY.md:**
   - Services table: remove mcp_service row
   - Subsystems table: remove mcp_service entry
   - Update key paths if needed

**Verification:**
```bash
# Docs should have no mcp_service references (except historical notes)
grep -c "mcp_service" ~/llm-wiki/super-council-docs/09-memory-service.md
# Expected: 0

# MEMORY.md should reflect single service
grep "mcp" ~/.pi/agent/memory/MEMORY.md
# Expected: only "MCP" protocol references, not "mcp_service"
```

**Dependencies:** Unit 5

---

### Unit 7: Backfill indexing for existing raw_session_memories entries

**Scope:** 15 entries in `raw_session_memories` have `is_indexed=0`. Run indexing on them so they're searchable via memsearch.

**Files:**
- `super_council/memory_service/store.py` — verify `_try_index_raw_memory()` is callable
- One-shot script or SQL to trigger backfill

**RED:** Check current indexing status:
```sql
SELECT COUNT(*) FROM raw_session_memories WHERE is_indexed = 0;
-- Expected: 15
```

**GREEN:**
1. Run one-shot backfill (Python one-liner or script):
```python
from super_council.memory_service import MemoryService
service = MemoryService.load()
cursor = service.store.db.execute("SELECT trace_id, raw_text FROM raw_session_memories WHERE is_indexed = 0")
for row in cursor.fetchall():
    service.store._try_index_raw_memory(row['trace_id'], row['raw_text'])
    print(f"Indexed: {row['trace_id']}")
```
2. Verify: `SELECT COUNT(*) FROM raw_session_memories WHERE is_indexed = 1;` → should be 15

**Verification:**
```sql
SELECT trace_id, is_indexed FROM raw_session_memories ORDER BY created_at DESC;
-- All should show is_indexed=1
```

**Dependencies:** Unit 2 (indexing must work first)

---

## Self-Review Checklist

| Check | Status |
|-------|--------|
| Spec coverage | All 7 units cover: port move, tool verification, queue restore, extension update, mcp_service removal, docs, indexing backfill |
| Placeholder scan | No TBDs — all file paths specific, all steps actionable |
| Type consistency | PendingQueue pattern ported from Python (mcp_service/retry.py) to TypeScript (extension) |
| Task boundaries | Each unit is 5-15 minutes of focused work |
| Buildability | Each unit has RED/GREEN/verification — engineer can execute without getting stuck |
| Dependencies ordered | Unit 1 → 2 → 5 (port move → verify → remove). Unit 3 → 4 (queue → update). Unit 6 last (docs). Unit 7 last (backfill). |
| Framework decision | FastMCP retained (researched alternatives, rejected raw SDK and custom Starlette) — documented in plan |

## Execution Order

```
Unit 1 (port 18097) ──→ Unit 2 (verify tools) ──→ Unit 5 (remove mcp_service)
                                                                      │
Unit 3 (PendingQueue) ──→ Unit 4 (extension update)                  │
                                                                      ↓
                                                              Unit 6 (docs)
                                                              Unit 7 (backfill)
```

Units 1-2-5 are the critical path. Units 3-4 can run in parallel. Units 6-7 are final cleanup.

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| SSE port binding mystery (18096 vs 18097) | Blocker | Debug log in Unit 1 reveals root cause; fallback: raw uvicorn wrapper |
| FastMCP upgrade (1.27.1 → 1.27.2) breaks something | Low | Minor version, test in Unit 2; rollback: `pip install mcp==1.27.1` |
| Extension PendingQueue doesn't drain | Lost calls | Manual retry: `ls ~/.council-memory/extension-pending/` |
| upsert_summary still routes to session_diary | Wrong table | HTTP endpoint routing is correct — just needs to be reached |
| Indexing backfill fails | Entries not searchable | Graceful degradation — entries still in DB, just not vector-searchable |
| systemd service fails to restart | Downtime | Manual start: `python3 -m super_council.memory_service --mcp-sse` |

---

## Execution Status (2026-05-30)

### Completed

| Unit | Status | Details |
|------|--------|---------|
| **1: SSE to 18097** | ✅ DONE | memory_service on 18097 (SSE) + 18098 (HTTP). Config `MCPConfig.port = 18097`. mcp_service stopped+disabled (was crash-looping on port conflict). |
| **2: Verify tools** | ✅ DONE | All 22 tools registered over SSE. `upsert_summary` routing verified: `auto-detected-assistant-message` → `raw_session_memories`, others → `session_diary`. Indexing produces `is_indexed=1`. |

### Completed

| Unit | Status | Details |
|------|--------|---------|
| **1: SSE to 18097** | ✅ DONE | memory_service on 18097 (SSE) + 18098 (HTTP). Config `MCPConfig.port = 18097`. mcp_service stopped+disabled (was crash-looping on port conflict). |
| **2: Verify tools** | ✅ DONE | All 22 tools registered over SSE. `upsert_summary` routing verified: `auto-detected-assistant-message` → `raw_session_memories`, others → `session_diary`. Indexing produces `is_indexed=1`. |
| **3: PendingQueue** | ✅ DONE | `PendingQueue` class added to extension (file-based, `~/.council-memory/extension-pending/`). Integrated into `callMemoryTool()` with catch/retry. Background drain loop (2s interval). Exponential backoff: 2s→4s→8s→...→5min, 10 retries. |
| **4: Extension cleanup** | ✅ DONE | All mcp_service references removed from `index.ts`. Updated comments, channel names (`mcp_queue` → `extension_queue`), error messages. |
| **5: Remove mcp_service** | ✅ DONE | Package deleted. Test file deleted. systemd unit deleted + daemon-reload. Old queue (`~/.council-memory/mcp-pending/`) deleted. References cleaned from `health.py`, `config.py`, `http_endpoints.py`, `layer.py`, `log_parsers.py`, `__main__.py`. |
| **6: Update docs** | ✅ DONE | `09-memory-service.md` updated: architecture diagram (single service), bulk-replaced mcp_service→memory_service refs. `MEMORY.md` clean (0 refs). |
| **7: Backfill indexing** | ✅ DONE | 21 entries backfilled via `_try_index_raw_memory()`. All 23 entries now `is_indexed=1`. Note: `_tag_project`/`_tag_type` Milvus upserts fail with `DataNotMatchException` (embedding field required) — non-critical, indexing itself succeeds. |

### Bugs Fixed During Execution

| Bug | File | Fix |
|-----|------|-----|
| **Indexer back-reference before initialization** | `memory_service/__init__.py` | Moved `self._store.indexer = self._indexer` to AFTER `MemIndex(config)` initialization. Added log: `MemIndex wired to RelationalStore (available=True)`. |
| **SSE `upsert_summary` always writes to `session_diary`** | `memory_service/mcp_server.py` | Added routing logic matching HTTP endpoint: `auto-detected-assistant-message` → `upsert_raw_session_memory()`, others → `upsert_session_diary()`. |
| **`created_at` NOT NULL constraint on `raw_session_memories`** | `memory_service/store.py` | Added `created_at` column to INSERT statement with `datetime.now(IST).isoformat()`. |
| **Embedding model mismatch** | `memory_service/index.py`, `layer.py` | Kept `gpahal/bge-m3-onnx-int8` (HF cached, works via ONNX provider). `micro_model.py` uses `pplx-embed-v1-0.6b-int8` directly (local path, ONNX runtime). |

### MicroModelEnricher Assessment

**Model:** `pplx-embed-v1-0.6B ONNX INT8` (700MB, `~/models/embedding/pplx-embed-v1-0.6b-int8/`)
**Purpose:** Semantic failure classification + artifact summarization
**Actual usage:** 1 row in `artifact_summaries` (test), 0 in `failure_classifications`, 0 in `event_window_summaries`
**Verdict:** Idle — heuristic fallbacks handle the work. Worth keeping as optional enrichment layer, but not critical path.
