# Memory Service

> Unified memory layer: RelationalStore + ContextRouter + MemoryLayer + ReviewService + MemIndex. Single source of truth for all memory operations.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MemoryService                        │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Relational   │  │ Context      │  │ Memory       │  │
│  │ Store        │  │ Router       │  │ Layer        │  │
│  │ (writes)     │  │ (recall)     │  │ (slices)     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐  │
│  │ Review       │  │ MemIndex     │  │ MemSearch    │  │
│  │ Service      │  │ (vector)     │  │ Wrapper      │  │
│  │ (reviews)    │  │ (optional)   │  │ (project)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  FastMCP Server (mcp.server.FastMCP)             │   │
│  │  18 tools + 7 resources + stdio/SSE transport    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Two Access Patterns

| Consumer | Access Method | Transport |
|----------|-------------|-----------|
| **Supervisor** (in-process) | `MemoryService.load()` → `.store`, `.router`, `.layer`, `.review` | Python API (zero overhead) |
| **Pi agent** (external) | `python3 -m super_council.memory_service --mcp-stdio` | FastMCP stdio (JSON-RPC) |

### Key Design Decisions

1. **No MCP subprocess for supervisor** — Supervisor uses direct Python API. No JSON-RPC serialization, no subprocess spawning, no `_call_mcp_tool()` indirection.

2. **FastMCP for external consumers** — Full MCP protocol compliance: tools with auto-schema, resources (`run://`, `review://` URIs), stdio + SSE transport, proper error codes.

3. **Single source of truth** — One `RelationalStore` (writes), one `ContextRouter` (recall), one `MemoryLayer` (slices), one `ReviewService` (reviews). No duplicate data paths.

4. **Graceful degradation** — `MemIndex` (memsearch) and optional `linter`/`enricher` degrade gracefully when unavailable.

## Components

### MemoryService (Entry Point)

```python
from super_council.memory_service import MemoryService

# Load with defaults
service = MemoryService.load()

# Access components
service.store      # RelationalStore (writes)
service.router     # ContextRouter (recall)
service.layer      # MemoryLayer (slices, unified recall)
service.review     # ReviewService (review lifecycle)
service.indexer    # MemIndex (vector indexing, optional)
service.config     # MemoryConfig (from config-subsystem.json)

# Convenience methods
service.recall(query="...", max_tokens=2048)
service.context_slice(run_id="...", max_tokens=1024)
service.run_snapshot(run_id="...")
service.summarize_issues(run_id="...")
service.review_findings(project_id="...", limit=10)
service.health_check()
```

### RelationalStore (Canonical Write Path)

- SQLite with WAL mode, FK enforcement, manual checkpoint
- Schema from `migrations/01_schema.sql` (single source of truth)
- All writes go through public methods (no raw SQL)
- Seeded tables: `workflow_definitions`, `phase_names`, `outcome_types`, `event_types`, `severity_levels`

### ContextRouter (Canonical Recall Path)

- Structured queries over RelationalStore
- Run snapshots, recent events, artifacts, similar runs
- Issue summaries, review findings
- Startup context (Tier 1 knowledge card)

### MemoryLayer (Artifact Management)

- Token-budgeted context slices with artifact boundaries
- Unified three-channel recall: text + structural + execution
- Artifact ingestion, eviction, context slicing
- **Never cuts mid-artifact** — uses `ARTIFACT_BOUNDARY` markers

### ReviewService (Review Lifecycle)

- `start_review(reviewer, target, run_id)` → creates pipeline + workflow_run + seed event
- `log_finding(run_id, severity, summary, fix, evidence, action)` → writes event + artifact
- `record_verdict(run_id, verdict, reason)` → updates status + logs verdict + stores artifact
- All writes route through RelationalStore public methods
- Input validation through OutputGate

### MemIndex (Vector Indexing)

- Wraps memsearch for project-aware indexing
- File type inference: `code`, `spec`, `doc`, `review`
- Graceful degradation when memsearch unavailable
- Fire-and-forget with `fcntl.flock()` (released on process death)

### ProjectAwareMemSearch (MemSearch Wrapper)

**Location:** `memory_service/memsearch_wrapper.py` (extracted from `super_council.py`)

- Adds `project_id` tagging and filtering to memsearch
- Client-side filtering (memsearch v0.4.x lacks server-side filter_expr)
- Type dimension: `code`, `spec`, `doc`, `review`
- Self-contained: only depends on `memsearch` package + stdlib
- Re-exported from `super_council.py` for backward compatibility

## MCP Server (FastMCP)

### Transport

```bash
# stdio (for Pi agent)
python3 -m super_council.memory_service --mcp-stdio

# Health check
python3 -m super_council.memory_service --health

# One-shot recall
python3 -m super_council.memory_service --recall "query" --max-tokens 512
```

### Tools (18 total)

| Tool | Description | Delegates To |
|------|-------------|-------------|
| `council-recall` | Three-channel unified recall | MemoryLayer.unified_recall() |
| `get_context_slice` | Token-budgeted context slice | MemoryLayer.get_context_slice() |
| `get_recent_events` | Recent execution events | ContextRouter.get_recent_events() |
| `get_run_snapshot` | Full run snapshot | ContextRouter.get_run_snapshot() |
| `summarize_run_issues` | Issue summary with severity | ContextRouter.summarize_run_issues() |
| `get_review_findings` | Recent review findings | ContextRouter.get_review_findings() |
| `council-index` | Index file into memsearch | MemIndex.index_file() |
| `review.start` | Start new review run | ReviewService.start_review() |
| `review.log` | Log review finding | ReviewService.log_finding() |
| `review.verdict` | Finalize review verdict | ReviewService.record_verdict() |
| `inspect_workflow_graph` | Workflow phase graph | RelationalStore.get_workflow_definitions() |
| `recall_startup_context` | Tier 1 knowledge card | ContextRouter.get_startup_context() |
| `council-query-pipelines` | Query pipelines with filters | RelationalStore.query_pipelines() |
| `council-get-pipeline` | Get pipeline by ID | RelationalStore.get_pipeline() |
| `get_phase_schemas` | Phase info from registry | RelationalStore.get_phase_info() |
| `get_run_artifacts` | Artifacts for a run | ContextRouter.get_artifacts() |
| `get_review_verdict` | Verdict for a run | ContextRouter.get_run_snapshot() → artifacts |
| `lint_current_workflow` | Lint workflow transitions | StateMachineLinter.lint() (graceful degradation) |

**Optional tools** (registered only if enricher available):
- `summarize_artifact` — MicroModelEnricher.summarize_artifact()
- `classify_failure` — MicroModelEnricher.classify_failure()

### Resources (7 total)

| Resource URI | Description |
|-------------|-------------|
| `run://{runid}/snapshot` | Full run snapshot (info + executions + artifacts) |
| `run://{runid}/events/recent` | Recent events for a run |
| `run://{runid}/artifacts` | Artifacts for a run (metadata only) |
| `workflow://definitions/current` | Current workflow definition |
| `phase://schemas/{phase}` | Phase info from registry |
| `review://findings` | Recent review findings |
| `review://verdict/{runid}` | Review verdict for a run |

### MCP Client Usage

```python
from super_council.mcp_client import MCPClient

client = MCPClient()
client.connect(timeout=15)

# Call tools
result = client.call_tool("council-recall", query="auth refactor", max_tokens=2048)
result = client.call_tool("review.start", reviewer="nemotron", target="code review")
result = client.call_tool("get_run_snapshot", run_id="pipe-abc123")

# List tools
tools = client.list_tools()  # ['council-recall', 'get_context_slice', ...]

client.disconnect()
```

## Tool Availability Matrix

### When Supervisor is Running (HTTP API)

| Category | Endpoint | Available |
|----------|----------|-----------|
| Health | `GET /health`, `/status`, `/metrics` | ✅ |
| Chat | `POST /v1/chat/completions` | ✅ |
| Delegation | `POST /v1/council/delegate` | ✅ |
| Fanout | `POST /v1/council/fanout` | ✅ |
| Chain | `POST /v1/council/chain` | ✅ |
| Pipeline | `POST /v1/council/pipeline` | ✅ |
| Recall | `POST /v1/council/recall` | ✅ |
| Memory (unified) | `POST /v1/council/memory/unified` | ✅ |
| Memory (context) | `POST /v1/council/memory/context_slice` | ✅ |
| Memory (events) | `POST /v1/council/memory/recent_events` | ✅ |
| Memory (snapshot) | `POST /v1/council/memory/run_snapshot` | ✅ |
| Memory (issues) | `POST /v1/council/memory/summarize_issues` | ✅ |
| Memory (findings) | `POST /v1/council/memory/review_findings` | ✅ |
| Review (start) | `POST /v1/council/review/start` | ✅ |
| Review (log) | `POST /v1/council/review/log` | ✅ |
| Review (verdict) | `POST /v1/council/review/verdict` | ✅ |
| Index | `POST /v1/council/index` | ✅ |
| Summarize | `POST /v1/council/summarize` | ✅ |
| Benchmark | `POST /v1/council/benchmark` | ✅ |
| Chair Gate | `POST /v1/council/chair-gate` | ✅ |
| Restart | `POST /v1/council/restart` | ✅ |
| Supervisor restart | `POST /v1/council/supervisor-restart` | ✅ |

### Via `memory_service --mcp-stdio` (Standalone)

| Tool | Available | Notes |
|------|-----------|-------|
| All 18 tools above | ✅ | Via FastMCP stdio |
| All 7 resources | ✅ | Via FastMCP resource protocol |
| Model swapping | ❌ | Supervisor-only |
| Chat completions | ❌ | Supervisor-only |
| Delegation | ❌ | Supervisor-only |
| Fanout | ❌ | Supervisor-only |
| Pipeline advancement | ❌ | Supervisor-only |

**The `memory_service` is purely the memory/recall/review layer.** It does NOT handle model swapping, chat completions, delegation, or pipeline state machine advancement. Those require the supervisor's proxy architecture and upstream llama-server management.

## Configuration

### config-subsystem.json (memory section)

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
      "host": "127.0.0.1",
      "port": 18096
    },
    "consolidation_ttl_days": 14,
    "consolidation_probation_enabled": true,
    "tier1_max_tokens": 512
  }
}
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `COUNCIL_DB_PATH` | Override database path | `~/.council-memory/pipelines.db` |

## Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `mcp>=1.0.0` | FastMCP server + stdio client | ✅ |
| `memsearch` | Vector indexing (optional) | ⚠️ Graceful degradation |
| `faiss` | ANN search (via memsearch) | ⚠️ Via memsearch |
| `milvus-lite` | Vector DB (via memsearch) | ⚠️ Via memsearch |

## File Locations

| Component | Path |
|-----------|------|
| MemoryService | `super_council/memory_service/__init__.py` |
| RelationalStore | `super_council/memory_service/store.py` |
| ContextRouter | `super_council/memory_service/router.py` |
| MemoryLayer | `super_council/memory_service/layer.py` |
| ReviewService | `super_council/memory_service/review.py` |
| MemIndex | `super_council/memory_service/index.py` |
| ProjectAwareMemSearch | `super_council/memory_service/memsearch_wrapper.py` |
| FastMCP Server | `super_council/memory_service/mcp_server.py` |
| CLI entry point | `super_council/memory_service/__main__.py` |
| MCP Client | `super_council/mcp_client.py` |
| Config | `super_council/memory_service/config.py` |
| Database | `~/.council-memory/pipelines.db` |
| Memsearch DB | `~/.memsearch/milvus.db` |
