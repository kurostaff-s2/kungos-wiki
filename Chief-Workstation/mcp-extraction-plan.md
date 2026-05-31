# MCP Extraction Plan

## Goal
Extract FastMCP SSE transport from memory_service into a standalone `mcp_service`. Move retry/backoff/fallback logic into the transport layer. Extension stays thin.

## Architecture After Extraction

```
Extension (council-tools)
  ↓ SSE (port 18097)
[mcp_service: FastMCP SSE + retry queue + backoff + HTTP fallback]
  ↓ HTTP (port 18096)
[memory_service: tools + store + router + layer + review]
  ↓ SQLite
~/.council-memory/pipelines.db
```

## Changes

### 1. memory_service: Add HTTP endpoints

Add lightweight HTTP endpoints to memory_service for all MCP tools. These use the same backend logic but accept HTTP POST instead of MCP SSE.

**File:** `memory_service/http_endpoints.py` (new)
```python
"""HTTP endpoints for memory_service — used by mcp_service as backend."""
from fastapi import APIRouter, Request
import json

router = APIRouter()

@router.post("/v1/memory/tool/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    """Generic tool endpoint — routes to registered tool handler."""
    body = await request.json()
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        raise HTTPException(404, f"Unknown tool: {tool_name}")
    result = handler(**body)
    return result
```

**File:** `memory_service/__init__.py` — add HTTP server startup
```python
# In MemoryService.__init__, start HTTP server alongside MCP
from .http_endpoints import router
from fastapi import FastAPI
app = FastAPI()
app.include_router(router)
# uvicorn runs on port 18096 alongside/existing SSE
```

### 2. mcp_service: New standalone service

**Directory:** `super_council/mcp_service/`
```
mcp_service/
  __init__.py       # MCPService class, entry point
  __main__.py       # CLI: python -m mcp_service --sse
  config.py         # MCPConfig (host, port, backend_url)
  transport.py      # FastMCP SSE server + tool proxy
  retry.py          # Persistent queue + exponential backoff
  fallback.py       # HTTP fallback to memory_service
```

**Key class:** `MCPTransport`
```python
class MCPTransport:
    """Standalone MCP SSE service.
    
    Responsibilities:
    - Run FastMCP SSE server on configured port
    - Proxy tool calls to memory_service HTTP backend
    - Handle retry with exponential backoff on failures
    - Maintain persistent queue for failed calls
    - Idempotency keys for duplicate prevention
    """
    
    def __init__(self, backend_url: str = "http://127.0.0.1:18096"):
        self.backend = backend_url
        self.queue = PersistentQueue()
        self._mcp = FastMCP(name="mcp-service", host="127.0.0.1", port=18097)
        self._register_tools()
    
    async def _proxy_tool(self, tool_name: str, params: dict) -> dict:
        """Proxy tool call to memory_service with retry."""
        # 1. Try HTTP to memory_service (fast path)
        try:
            return await http_post(f"{self.backend}/v1/memory/tool/{tool_name}", params)
        except Exception as e:
            # 2. Queue for retry with backoff
            self.queue.add(tool_name, params)
            raise MCPError(f"Backend unavailable, queued for retry: {e}")
```

**Retry logic:** `retry.py`
```python
class PersistentQueue:
    """Same pattern as council-tools PendingQueue, but server-side."""
    
    PENDING_DIR = "~/.council-memory/mcp-pending"
    MAX_RETRIES = 10
    BASE_DELAY = 2_000  # 2s
    MAX_DELAY = 300_000  # 5min
    
    def add(self, tool_name: str, params: dict) -> str:
        """Add failed call to persistent queue."""
        entry_id = hashlib.sha256(f"{tool_name}-{json.dumps(params, sort_keys=True)}-{time.time()}".encode()).hexdigest()[:16]
        entry = {
            "id": entry_id,
            "tool_name": tool_name,
            "params": params,
            "attempts": 0,
            "next_try": 0,  # immediate
        }
        atomic_write(f"{self.PENDING_DIR}/{entry_id}.json", entry)
        return entry_id
    
    def drain(self, backend_url: str):
        """Background drain loop — retry pending calls."""
        while True:
            entries = self.get_ready()
            for entry in entries:
                try:
                    result = http_post(f"{backend_url}/v1/memory/tool/{entry['tool_name']}", entry['params'])
                    self.remove(entry['id'])  # success
                except:
                    self.update(entry)  # increment attempts, schedule backoff
            time.sleep(self._next_delay())
```

### 3. Extension: Simplify to SSE-only

Remove all fallback logic from council-tools. The extension just connects to mcp_service SSE and sends tool calls.

**File:** `council-tools/index.ts`
```typescript
// Simplified: no fallback, no retry — mcp_service handles it all
const MCP_HOST = process.env.COUNCIL_MCP_HOST ?? "127.0.0.1";
const MCP_PORT = process.env.COUNCIL_MCP_PORT ?? "18097";

async function callMemoryTool(toolName: string, params: Record<string, any>): Promise<any> {
  return await mcpClient.callTool(toolName, params);
  // If this fails, mcp_service already queued it for retry
  // Extension just reports the error to the user
}
```

### 4. Config updates

**File:** `config-subsystem.json`
```json
{
  "mcp_service": {
    "host": "127.0.0.1",
    "port": 18097,
    "backend_url": "http://127.0.0.1:18096",
    "retry": {
      "max_retries": 10,
      "base_delay_ms": 2000,
      "max_delay_ms": 300000
    }
  },
  "memory_service": {
    "host": "127.0.0.1",
    "port": 18096,
    "http_enabled": true
  }
}
```

### 5. systemd services

**File:** `~/.config/systemd/user/mcp-service.service`
```ini
[Unit]
Description=Council MCP Service (SSE transport + retry)
After=memory-service.service

[Service]
ExecStart=/usr/bin/python3 -m mcp_service --sse
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

## Implementation Order

### Step 1: Add HTTP endpoints to memory_service (~2 hours)
- Create `http_endpoints.py` with generic tool router
- Register all existing MCP tools as HTTP endpoints
- Test: `curl -X POST http://127.0.0.1:18096/v1/memory/tool/council-recall -d '{"query":"test"}'`

### Step 2: Create mcp_service package (~3 hours)
- New package under `super_council/mcp_service/`
- FastMCP SSE server that proxies to memory_service HTTP
- Persistent queue + retry logic
- CLI entry point

### Step 3: Update extension to use mcp_service (~1 hour)
- Change `MEMORY_HOST`/`MEMORY_PORT` to `MCP_HOST`/`MCP_PORT`
- Remove supervisor fallback from `callMemoryTool`
- Simplify error handling

### Step 4: Add systemd service + testing (~1 hour)
- systemd unit file for mcp_service
- Health check endpoint
- Integration test: kill memory_service, verify mcp_service queues and retries

## What Stays the Same

- **memory_service business logic** — no changes to store, router, layer, review
- **MCP tool interfaces** — same tool names, same params, same responses
- **Extension tool registration** — same `pi.registerTool` calls, just different backend

## What Changes

- **Transport layer** — extracted to mcp_service with retry/backoff
- **Fallback** — from supervisor HTTP to memory_service HTTP (within mcp_service)
- **Extension** — simplified, no fallback logic
- **Ops** — two services instead of one, but both independent

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| memory_service HTTP adds latency | Same-machine HTTP is ~1ms, negligible vs SSE |
| mcp_service can go down independently | systemd auto-restart, memory_service still works directly |
| Tool registration duplication | mcp_service auto-discovers tools from memory_service `/v1/memory/tools` endpoint |
| Config complexity | Single config file, sensible defaults |
