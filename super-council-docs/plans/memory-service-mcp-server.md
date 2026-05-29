# Plan: Standalone Memory MCP Server

> Extract memory subsystem from super_council.py into independent `memory_service/` module with its own MCP server process. Enables recall tools without supervisor running.

## Current State

```
pi (agent)
  ↓ MCP stdio
supervisor subprocess (super_council --mcp-stdio)
  ↓ in-process
  RelationalStore → SQLite
  ContextRouter    → queries
  MemoryLayer      → three-channel recall
  CouncilMemory    → memsearch indexing
```

**Problem:** All recall tools die when supervisor stops. No standalone memory access.

## Target State

```
pi (agent)
  ↓ MCP stdio (stdio transport)
memory_service subprocess (python -m memory_service --mcp-stdio)
  ↓ in-process
  MemoryStore      → SQLite (pipelines.db)
  ContextRouter    → queries (unchanged)
  MemoryLayer      → three-channel recall (unchanged)
  MemIndex         → memsearch indexing (from CouncilMemory)
```

```
supervisor (super_council)
  ↓ HTTP or shared DB
memory_service subprocess
```

## Module Structure

```
memory_service/
  __init__.py          # MemoryService facade
  __main__.py          # CLI entry: --mcp-stdio, --http, --health
  config.py            # MemoryConfig (loads from config-subsystem.json["memory"])
  store.py             # MemoryStore (from RelationalStore, memory-specific tables)
  router.py            # ContextRouter (unchanged, moves here)
  layer.py             # MemoryLayer (unchanged, moves here)
  index.py             # MemIndex (from CouncilMemory._auto_index_file)
  mcp_server.py        # MCP tool registry (from super_council/mcp_server.py recall tools)
  prompts.py           # Recall prompt templates (if any extracted)
```

## Implementation Units

### Unit 1: Module Skeleton + Config

**Goal:** `memory_service/` directory with `__init__.py`, `config.py`, `__main__.py`

**Files:**
- `memory_service/__init__.py` — `MemoryService` facade class
- `memory_service/config.py` — `MemoryConfig` dataclass
- `memory_service/__main__.py` — CLI entry point

**Config schema:**
```json
{
  "memory": {
    "db_path": "~/.council-memory/pipelines.db",
    "memory_base": "~/.council-memory",
    "memsearch": {
      "enabled": true,
      "milvus_uri": "~/.memsearch/milvus.db",
      "collection": "memsearch_chunks"
    },
    "mcp": {
      "transport": "stdio",
      "tools": ["council-recall", "get_context_slice", "get_recent_events",
                "get_run_snapshot", "summarize_run_issues", "get_review_findings",
                "memsearch_index_file"]
    }
  }
}
```

**Acceptance:**
- `python -m memory_service --help` works
- `MemoryConfig.load()` reads from `config-subsystem.json["memory"]`
- No dependencies on super_council.py

---

### Unit 2: Store Layer (MemoryStore)

**Goal:** Extract memory-specific RelationalStore operations into `MemoryStore`

**Source:** `super_council/relational_store.py`

**Moves:**
| Method | Purpose |
|--------|---------|
| `query_consolidation_cache()` | Memory cache queries |
| `upsert_consolidation_cache()` | Memory cache writes |
| `activate_consolidation_cache()` | Cache activation |
| `query_pipelines()` | Pipeline state queries |
| `get_pipeline()` | Single pipeline query |
| `query_events()` | Event history |
| `query_artifacts()` | Artifact queries |

**Stays in super_council:**
- Pipeline transition logic (`_next_attempt`, `_record_transition`)
- Pipeline state machine integration

**Acceptance:**
- `MemoryStore.load(db_path)` creates SQLite connection
- All query methods work independently
- No pipeline state machine dependency

---

### Unit 3: Router + Layer (Move, Don't Change)

**Goal:** Move `context_router.py` and `memory_layer.py` into `memory_service/`

**Changes:**
- `context_router.py` → `memory_service/router.py` — update imports only
- `memory_layer.py` → `memory_service/layer.py` — update imports only

**Dependencies:**
- `ContextRouter` needs `MemoryStore` (was `RelationalStore`)
- `MemoryLayer` needs `MemoryStore` + `ContextRouter`

**Acceptance:**
- `ContextRouter` returns same results as before
- `MemoryLayer.unified_recall()` works with `MemoryStore`
- All recall tool outputs identical to current

---

### Unit 4: Index Service (MemIndex)

**Goal:** Extract memsearch indexing from `CouncilMemory` class

**Source:** `CouncilMemory._auto_index_file()` (super_council.py line 420-474)

**Moves:**
| Method | Purpose |
|--------|---------|
| `index_file(path, project_id)` | Index file into memsearch |
| `search(query, limit)` | Memsearch vector search |
| `stats()` | Memsearch collection stats |

**Dependencies:**
- `memsearch` Python package (optional, graceful degradation)
- `fcntl.flock()` for lock file

**Acceptance:**
- `MemIndex.index_file()` works standalone
- Graceful no-op if memsearch not installed
- Lock file behavior preserved

---

### Unit 5: MCP Server

**Goal:** MCP tool registry with all recall tools

**Source:** `super_council/mcp_server.py` (recall tool definitions)

**Tools to migrate:**
| Tool Name | Handler | Source |
|-----------|---------|--------|
| `council-recall` | `MemoryLayer.unified_recall()` | mcp_server.py line 422+ |
| `get_context_slice` | `ContextRouter.get_context_slice()` | mcp_server.py |
| `get_recent_events` | `ContextRouter.get_recent_events()` | mcp_server.py |
| `get_run_snapshot` | `ContextRouter.get_run_snapshot()` | mcp_server.py |
| `summarize_run_issues` | `ContextRouter.summarize_issues()` | mcp_server.py |
| `get_review_findings` | `ContextRouter.get_review_findings()` | mcp_server.py |
| `memsearch_index_file` | `MemIndex.index_file()` | mcp_server.py |

**MCP Server skeleton:**
```python
# memory_service/mcp_server.py
from mcp.server import MCPServer
from .store import MemoryStore
from .router import ContextRouter
from .layer import MemoryLayer
from .index import MemIndex

class MemoryMCPHandler:
    def __init__(self, store, router, layer, indexer):
        self._store = store
        self._router = router
        self._layer = layer
        self._indexer = indexer
        self._mcp = MCPServer("memory-service")
        self._register_tools()

    def _register_tools(self):
        self._mcp.tool("council-recall")(self._council_recall)
        self._mcp.tool("get_context_slice")(self._get_context_slice)
        # ... etc

    async def _council_recall(self, query, max_tokens=2048, ...):
        return self._layer.unified_recall(query, max_tokens=max_tokens, ...)
```

**Acceptance:**
- `python -m memory_service --mcp-stdio` starts MCP server
- All 7 tools registered and callable
- Tool outputs identical to current supervisor MCP

---

### Unit 6: CLI + Process Management

**Goal:** Standalone process with stdio transport

**CLI modes:**
```bash
# MCP stdio (for pi agent)
python -m memory_service --mcp-stdio

# HTTP server (optional, for external access)
python -m memory_service --http --port 18096

# Health check
python -m memory_service --health

# One-shot recall (CLI usage)
python -m memory_service --recall "past auth fixes" --max-tokens 1024
```

**systemd service:**
```ini
# ~/.config/systemd/user/memory-service.service
[Unit]
Description=Council Memory Service — Standalone MCP Server
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m memory_service --mcp-stdio
WorkingDirectory=/home/chief/Coding-Projects/7-council/memory_service
Restart=on-failure
RestartSec=5
MemoryMax=2G

[Install]
WantedBy=default.target
```

**Acceptance:**
- `systemctl --user start memory-service` starts MCP server
- `systemctl --user status memory-service` shows healthy
- MCP tools available when supervisor is down

---

### Unit 7: Supervisor Integration (Backward Compatibility)

**Goal:** Supervisor uses memory_service instead of inline modules

**Changes in super_council.py:**
```python
# OLD:
self.relational_store = RelationalStore("~/.council-memory/pipelines.db")
self.context_router = ContextRouter(self.relational_store)
self.memory_layer = MemoryLayer(self.relational_store, self.context_router)

# NEW:
from memory_service import MemoryService
self._memory = MemoryService.load()
self.relational_store = self._memory.store  # proxy
self.context_router = self._memory.router   # proxy
self.memory_layer = self._memory.layer      # proxy
```

**MCP routing:**
- If `memory_service` subprocess running → route MCP calls to it
- If not → fall back to inline (current behavior)
- Gradual migration path

**Acceptance:**
- Supervisor still works with inline modules (fallback)
- Supervisor prefers memory_service when available
- No behavior change for existing users

---

## Migration Sequence

```
Unit 1 (skeleton)  →  Unit 2 (store)  →  Unit 3 (router+layer)
                                              ↓
Unit 4 (index)  ←── Unit 5 (MCP)  ←─────────┘
                                              ↓
Unit 6 (CLI)  →  Unit 7 (supervisor integration)
```

**Estimated effort:** 6-8 hours total
- Units 1-3: 2h (skeleton + store + move existing modules)
- Units 4-5: 2h (index extraction + MCP server)
- Unit 6: 1h (CLI + systemd)
- Unit 7: 1-3h (supervisor integration, depends on fallback complexity)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| RelationalStore has pipeline state logic | Unit 2 scope creep | Split cleanly: memory queries vs state transitions |
| MCP tool signatures differ from supervisor | Unit 5 integration | Copy exact tool definitions, don't reimplement |
| Supervisor fallback adds complexity | Unit 7 scope | Phase 1: supervisor uses memory_service directly (no subprocess). Phase 2: add subprocess fallback. |
| Memsearch dependency | Unit 4 | Graceful degradation (already implemented) |

## Rollback Plan

- All old modules stay in `super_council/` until Unit 7 completes
- Supervisor fallback preserves current behavior
- Git revert restores pre-migration state
- No data migration needed (same SQLite database)

## Success Criteria

- [ ] `python -m memory_service --mcp-stdio` starts and registers all 7 tools
- [ ] `recall.unified()` works when supervisor is stopped
- [ ] `systemctl --user start memory-service` works
- [ ] Supervisor still works with memory_service as dependency
- [ ] All recall tool outputs identical to pre-migration
- [ ] No behavior change for existing users
