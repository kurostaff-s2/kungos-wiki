# Architecture Analysis: Decoupling Recall Tools from Supervisor

## Current State

### Service Map
| Service | Port | Status | Role |
|---------|------|--------|------|
| memory_service | 18096 | UP | MCP SSE: recall, logs, review, memsearch |
| supervisor | 8090 | DOWN | HTTP fallback for SSE failures |
| pi LLM | 8091 | UP | Local model inference |
| searxng | 8080 | UP | Web search |
| ragflow | 6333 | DOWN | MemSearch backend |

### Critical Finding: Log Subsystems Are ALREADY in memory_service
The `unified_log_recall` tool is already exposed as an MCP tool on the memory service. The log parsers (`DailyLogParser`, `ChatSummaryQuery`, `SupervisorLogTailer`) live in `memory_service/log_parsers.py`. The `MemoryLayer.unified_log_recall()` method queries all channels directly.

**The supervisor dependency is ONLY the HTTP fallback** — when SSE fails, the extension falls back to `callSupervisor("/v1/council/memory/unified", body)`.

### Call Flow (broken)
```
recall.unified() 
  → callMemoryTool("council-recall", params, "/v1/council/memory/unified", fallbackBody)
     → SSE to memory_service (18096) ← WORKING but failing in extension
     → FALLBACK: callSupervisor("/v1/council/memory/unified", ...) ← DOWN → NETWORK_ERROR
```

## Root Cause Analysis

The SSE connection to memory_service works (curl test passes), but the `McpSseClient` in the extension fails because:
1. After pi reload, the SSE client reconnects but may hit ASGI state issues
2. The 10s timeout on SSE handshake can expire during cold starts
3. When SSE fails, the fallback routes to the supervisor which is down

## Options

### Option A: Replace Supervisor Fallback with Persistent Queue (RECOMMENDED)

**What:** Remove all supervisor HTTP fallbacks from `callMemoryTool`. Replace with the persistent queue + exponential backoff pattern we just built for upserts.

**Changes:**
1. Remove `fallbackPath`/`fallbackBody` parameters from `callMemoryTool`
2. On SSE failure, queue the request for retry with backoff (2s→4s→8s→...→5min)
3. Background drain loop retries until success or 10 attempts
4. For synchronous tools (recall), return cached/partial results from local state while queue drains

**Pros:**
- Zero new services — uses existing memory_service
- Log subsystems already independent (in memory_service)
- Survives hours of downtime with persistent queue
- Minimal code changes (~50 lines)
- Consistent pattern with upsert queue

**Cons:**
- Recall tools become async (queue + callback) instead of synchronous
- Need local cache for partial results during downtime

**Effort:** Low (1-2 hours)

---

### Option B: New Log Service (Overkill)

**What:** Extract log subsystems to a new independent service (e.g., `log_service` on port 18097).

**Changes:**
1. New Python service with FastAPI/starlette
2. Move `log_parsers.py`, `ServiceHealthChecker`, daily/chat/supervisor log channels
3. New systemd service, config, health checks
4. Extension routes log queries to new service

**Pros:**
- Complete isolation — memory_service downtime doesn't affect logs
- Independent scaling and deployment

**Cons:**
- New service to maintain, monitor, restart
- Data duplication (logs already on disk, just need different query interface)
- Split brain: which service owns `event_log` table?
- Adds operational complexity for no real gain

**Effort:** High (4-8 hours + ongoing maintenance)

---

### Option C: MCP SSE as Independent Subsystem (Not Recommended Now)

**What:** Extract the MCP SSE transport from memory_service into a standalone gateway.

**Changes:**
1. New `mcp_gateway` service handles SSE connections, session management
2. memory_service becomes stateless backend (HTTP-only)
3. Gateway manages reconnection, backoff, tool routing

**Pros:**
- Clean separation of transport and business logic
- Gateway can handle connection pooling, load balancing
- Better fault isolation

**Cons:**
- Adds hop latency to every tool call
- New failure point (gateway can go down independently)
- Over-engineering for single-user deployment
- FastMCP already handles SSE transport well

**Effort:** Very High (8-16 hours)

---

## Recommendation: Option A + HTTP Fallback After Retry Exhaustion

### Phase 1: Persistent Queue for ALL Memory Tools (immediate)
1. Remove supervisor fallback from `callMemoryTool`
2. Extend `PendingQueue` to handle all tool types (not just upserts)
3. Queue failed calls with idempotency keys
4. Background drain retries with exponential backoff
5. After 10 retries, try direct HTTP to memory_service (not supervisor)

### Phase 2: Direct HTTP Endpoint on memory_service (robustness)
1. Add HTTP endpoints to memory_service for critical tools:
   - `POST /v1/memory/upsert_summary` (idempotent, for fallback)
   - `POST /v1/memory/recall` (for fallback)
   - `POST /v1/memory/log_recall` (for fallback)
2. These endpoints use the same backend as MCP tools but over HTTP
3. Extension falls back to HTTP after SSE retries exhausted

### Phase 3: Local Cache for Offline Resilience (nice-to-have)
1. Cache recent recall results locally (~/.council-memory/cache/)
2. When both SSE and HTTP fail, serve from cache with staleness warning
3. Cache invalidates on next successful recall

### Why Not Option B or C?
- **B (new log service):** Log subsystems are already in memory_service. Extracting them adds a service for no functional gain.
- **C (MCP gateway):** FastMCP already handles SSE well. The issue is transient failures, not architectural flaws. Persistent queue + HTTP fallback solves the real problem.

## Implementation Plan

### Step 1: Extend PendingQueue for all tool types
```typescript
// Queue entry supports any tool, not just upserts
interface QueuedCall {
  id: string;           // idempotency key
  toolName: string;     // "council-recall", "upsert_summary", etc.
  params: Record<string, any>;
  attempts: number;
  nextTry: number;
  isAsync: boolean;     // true for upserts, false for recall
}
```

### Step 2: Remove supervisor fallback from callMemoryTool
```typescript
async function callMemoryTool(toolName: string, params: Record<string, any>): Promise<any> {
  try {
    return await memoryClient.callTool(toolName, params);
  } catch (err) {
    // Queue for retry instead of supervisor fallback
    const queue = PendingQueue.getInstance();
    queue.addCall(toolName, params);
    throw new Error(`SSE failed, queued for retry: ${err.message}`);
  }
}
```

### Step 3: Add HTTP fallback to memory_service after retries
```typescript
// In PendingQueue._drain(), after MAX_RETRIES:
if (entry.attempts >= MAX_RETRIES) {
  // Try direct HTTP to memory_service (not supervisor)
  const httpResult = await fetch(`http://${MEMORY_HOST}:${MEMORY_PORT}/v1/memory/${entry.toolName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry.params),
  });
  // ... handle result
}
```

### Step 4: Add HTTP endpoints to memory_service
```python
# In memory_service/router.py or new http_endpoints.py
@app.post("/v1/memory/upsert_summary")
async def http_upsert_summary(request: Request):
    """HTTP fallback for upsert_summary when SSE is unavailable."""
    body = await request.json()
    result = mcp_handler.upsert_summary(**body)
    return JSONResponse(result)
```

## Summary

| Option | Effort | Risk | Gain |
|--------|--------|------|------|
| A: Persistent queue + HTTP fallback | Low | Low | High — solves immediate problem |
| B: New log service | High | Medium | Low — logs already independent |
| C: MCP gateway | Very High | High | Low — over-engineering |

**Recommendation:** Option A. It's the minimal change that achieves zero supervisor dependency. The log subsystems are already in memory_service — we just need to stop routing failures to the supervisor and instead retry with backoff + HTTP fallback to memory_service directly.
