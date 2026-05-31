# Memory Service

> Unified memory layer: RelationalStore + ContextRouter + MemoryLayer + ReviewService + MemIndex. Single source of truth for all memory operations.

## Architecture

### Single-Service Architecture (since 2026-05-30)

```
┌─────────────────────────────────────────────────────────────┐
│  Pi Extension (council-tools/index.ts)                      │
│  - 12 LLM-callable tools + 9 commands                       │
│  - Auto-upsert: message_end hook (score ≥ 4 → upsert)       │
│  - Connects to memory_service SSE on :18097                 │
│  - PendingQueue: file-based retry (~/.council-memory/       │
│    extension-pending/) with exponential backoff             │
└─────────────────────┬───────────────────────────────────────┘
                      │ SSE (MCP protocol)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  memory_service (SSE:18097, HTTP:18098)                     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Relational   │  │ Context      │  │ Memory       │      │
│  │ Store        │  │ Router       │  │ Layer        │      │
│  │ (writes)     │  │ (recall)     │  │ (slices)     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│  ┌──────┴───────┐  ┌──────┴───────┐               │        │
│  │ Review       │  │ MemIndex     │               │        │
│  │ Service      │  │ (vector)     │               │        │
│  │ (reviews)    │  │ └→ MemSearch │               │        │
│  │              │  │   (owned)    │               │        │
│  └──────────────┘  └──────────────┘               │        │
│                                                    │        │
│  ┌─────────────────────────────────────────────────┐│        │
│  │  HTTP Endpoints (http_endpoints.py)             ││        │
│  │  - ToolRegistry: 22 tool handlers               ││        │
│  │  - POST /v1/memory/tool/{tool_name}             ││        │
│  │  - GET  /v1/memory/tools (discovery)            ││        │
│  │  - GET  /v1/memory/health                       ││        │
│  └─────────────────────────────────────────────────┘│        │
│                                                     │        │
│  ┌──────────────────────────────────────────────────┐│       │
│  │  FastMCP Server (mcp.server.FastMCP)            ││       │
│  │  22 tools + 7 resources + stdio/SSE transport   ││       │
│  └──────────────────────────────────────────────────┘│       │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
              ~/.council-memory/pipelines.db
```

### Dependency Isolation

**`super_council.py` has zero direct MemSearch dependency.** All vector indexing and search
route through `memory_service.indexer` (single source of truth).

```
super_council.py
  └── memory_service.indexer.*    (Python API)
        └── MemIndex              (owns lifecycle, config, locking)
              └── MemSearch       (external package, owned by memory service only)
```

Removed in 2026-05-28 refactor:
- `CouncilMemory._auto_index_file()` → replaced by `MemIndex.index_file()`
- `_active_recall()` MemSearch boilerplate → `memory_service.indexer.search()`
- `_active_recall_structured()` MemSearch boilerplate → `memory_service.indexer.search()`
- Health endpoint MemSearch stats → `memory_service.indexer.stats()`
- Raw `from memsearch import MemSearch` import → eliminated

Domain logic preserved in SlotSupervisor: shell-injection guard, phase filtering,
token budget formatting, client-side type filtering.

### Two Access Patterns

| Consumer | Access Method | Transport |
|----------|-------------|-----------|
| **Supervisor** (in-process) | `MemoryService.load()` → `.store`, `.router`, `.layer`, `.review` | Python API (zero overhead) |
| **Pi agent** (stdio) | `python3 -m super_council.memory_service --mcp-stdio` | FastMCP stdio (JSON-RPC) |
| **Pi extension** (SSE) | Persistent SSE connection to `memory_service :18097/sse` | FastMCP SSE → HTTP proxy → memory_service :18098 |
| **External clients** | `--mcp-sse` or `--mcp-streamable-http` | FastMCP SSE / streamable-http |

### Key Design Decisions

1. **No MCP subprocess for supervisor** — Supervisor uses direct Python API. No JSON-RPC serialization, no subprocess spawning, no `_call_mcp_tool()` indirection.

2. **FastMCP for external consumers** — Full MCP protocol compliance: tools with auto-schema, resources (`run://`, `review://` URIs), three transports (stdio, SSE, streamable-http), proper error codes. SSE enables persistent connections with zero reconnect overhead for subsequent calls.

3. **Single source of truth** — One `RelationalStore` (writes), one `ContextRouter` (recall), one `MemoryLayer` (slices), one `ReviewService` (reviews). No duplicate data paths.

4. **Graceful degradation** — `MemIndex` (memsearch) and optional `linter`/`enricher` degrade gracefully when unavailable.

5. **Transport extracted to memory_service** — SSE transport, retry queue, and backoff logic moved from memory_service into a standalone `memory_service` package. memory_service becomes a stateless HTTP backend. memory_service handles connection management, tool proxying, and failure recovery independently.

---

## memory_service (Standalone Transport Layer)

> SSE transport with retry queue and exponential backoff. Proxies tool calls to memory_service HTTP backend. Survives hours of downtime with persistent queue.

**Added:** 2026-05-30
**Location:** `super_council/memory_service/`
**Port:** 18097 (SSE)
**Backend:** memory_service HTTP on 18098

### Why Extracted?

The original architecture ran FastMCP SSE transport inside memory_service. This created two problems:

1. **Tight coupling** — SSE connection state, retry logic, and business logic shared the same process. A transport-layer bug could crash the entire memory service.

2. **No independent retry** — When SSE failed, the extension fell back to supervisor HTTP (port 8090). When supervisor was down, calls were lost. There was no persistent queue to survive downtime.

The extraction decouples transport from business logic:

| Concern | Before | After |
|---------|--------|-------|
| SSE transport | Inside memory_service | Standalone memory_service |
| Retry queue | Extension-side (PendingQueue) | memory_service-side (PersistentQueue) |
| Fallback | Supervisor HTTP (:8090) | memory_service HTTP (:18098) |
| Schema discovery | Hardcoded in extension | Auto-discovered from backend |
| Process isolation | Single process | Two independent processes |

### Architecture

```
Extension (:18097) ──SSE──> memory_service ──HTTP──> memory_service (:18098)
                                    │
                                    │ on failure
                                    ▼
                           PersistentQueue
                           (~/.council-memory/mcp-pending/)
                                    │
                                    │ background drain loop
                                    ▼
                           Retry with exponential backoff
                           2s → 4s → 8s → 16s → ... → max 5min
                           Max 10 retries → purge stale entries
```

### Components

#### MCPTransport (`transport.py`)

FastMCP SSE server that proxies tool calls to memory_service HTTP backend.

**Startup flow:**
1. Fetch available tools from `GET :18098/v1/memory/tools`
2. Register proxy handler for each tool (dynamic, zero schema duplication)
3. Start FastMCP SSE server on configured port (default 18097)
4. Start background drain loop in separate thread

**Proxy call flow:**
1. Client calls tool via SSE: `tools/call({name: "council-recall", arguments: {...}})`
2. Proxy handler forwards to `POST :18098/v1/memory/tool/council-recall`
3. On success: return result to client (~15ms total)
4. On failure: queue entry in PersistentQueue, return error JSON with `queued: true`

**Proxy handler signature:**
```python
def handler(arguments: Any = None) -> str:
    """Proxy handler for a discovered tool.
    
    arguments: dict of tool parameters (passed through to backend)
    returns: JSON string (backend response or error with queue info)
    """
    return self._proxy_call(tool_name, arguments)
```

All proxy handlers accept `arguments: Any = None`. FastMCP generates flexible schemas that accept any JSON object. Backend validates parameters in `http_endpoints.py`.

#### PersistentQueue (`retry.py`)

File-based persistent queue that survives process crashes and restarts.

**Storage:** `~/.council-memory/mcp-pending/{entry_id}.json`

**Entry format:**
```json
{
  "id": "d8b24fc19f526060",
  "tool_name": "upsert_summary",
  "params": {"summary_text": "...", "source": "auto-detected-assistant-message"},
  "attempts": 6,
  "next_try": 1780104565.034
}
```

**Exponential backoff:**

| Attempt | Delay | Cumulative |
|---------|-------|------------|
| 1 | 2s | 2s |
| 2 | 4s | 6s |
| 3 | 8s | 14s |
| 4 | 16s | 30s |
| 5 | 32s | 62s |
| 6 | 64s | 126s |
| 7 | 128s | 254s |
| 8 | 256s | 510s |
| 9 | 300s (max) | 810s |
| 10 | 300s (max) | 1110s → **purged if still failing** |

**Background drain loop:**
- Runs in daemon thread, polls every 2s (or sooner if entries ready)
- `get_ready()` returns entries where `next_try <= now` and `attempts < max_retries`
- On success: `mark_success()` deletes entry from queue
- On failure: `mark_retry()` increments attempts, schedules next try
- `purge_stale()` removes entries that exceeded max retries

**Idempotency:** `upsert_summary` uses `INSERT OR REPLACE` on `summary_id` primary key. Duplicate calls are no-ops. Other tools (recall, review) are read-only or have natural idempotency.

#### MCPConfig (`config.py`)

```python
@dataclass
class RetryConfig:
    max_retries: int = 10
    base_delay_ms: int = 2_000       # 2s initial delay
    max_delay_ms: int = 300_000      # 5min max delay
    queue_dir: str = "~/.council-memory/mcp-pending"

@dataclass
class MCPConfig:
    host: str = "127.0.0.1"
    port: int = 18097
    backend_url: str = "http://127.0.0.1:18098"
    tools: List[str] = field(default_factory=list)  # empty = all tools
    retry: RetryConfig = field(default_factory=RetryConfig)
```

Loaded from `config-subsystem.json["memory_service"]` or environment variables.

### CLI

```bash
# Start SSE server (normal operation)
python3 -m super_council.memory_service --sse

# Health check (exits immediately)
python3 -m super_council.memory_service --health

# Run drain loop once (manual retry)
python3 -m super_council.memory_service --drain

# Verbose mode
python3 -m super_council.memory_service --sse --verbose
```

### systemd Service

```ini
# ~/.config/systemd/user/memory-service.service
[Unit]
Description=Council Memory Service — SSE transport with retry and backoff
After=memory-service.service
Requires=memory-service.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 -m super_council.memory_service --sse
WorkingDirectory=/home/chief/Coding-Projects/7-council
Environment=PYTHONPATH=/home/chief/Coding-Projects/7-council
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=2
MemoryMax=512M
StandardOutput=journal
StandardError=journal
SyslogIdentifier=memory-service

[Install]
WantedBy=default.target
```

### Queue Inspection

```bash
# List pending entries
ls ~/.council-memory/mcp-pending/

# View entry details
cat ~/.council-memory/mcp-pending/{entry_id}.json

# Query via unified_log_recall
unified_log_recall(query="", channels="mcp_queue")
```

### Failure Modes

| Scenario | Behavior |
|----------|----------|
| memory_service down | Calls queued, retry with backoff, survive hours |
| memory_service crashes | Queue persists on disk, drain loop resumes on restart |
| Extension crashes | Queue persists, memory_service continues draining |
| Network partition | Same as memory_service down — queue + retry |
| Queue full (disk) | New entries fail, logged to journal |
| 10 retries exceeded | Entry purged, logged as stale |

---

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
- Schema from migrations `01_schema.sql` → `05_rename_to_session_diary.sql` (applied in order)
- All writes go through public methods (no raw SQL)
- Seeded tables: `workflow_definitions`, `phase_names`, `outcome_types`, `event_types`, `severity_levels`

#### Three Write Channels for Session Memory

| Channel | Table | Method | Provenance |
|---------|-------|--------|------------|
| **Arc A380 pipeline** | `consolidation_cache` | `upsert_consolidation_cache()` | `consol-*` — Granite-4.1-3B output |
| **Mechanical upsert** | `session_diary` | `upsert_session_diary()` | `sess-*` — auto-detected or manual |
| **Todo reconciliation** | `session_diary` (read) | `reconcile_open_items()` | deduped open items across entries |

**`upsert_session_diary(summary_text, source_path, alias)`** — The mechanical upsert. Parses Markdown sections from the summary text (`##` or `###` Key Decisions, Topics Discussed, Work Completed, Open Items, Models Used) and stores structured fields. Matches both `##` and `###` headers via `#{1,3}` regex. Generates `sess-{timestamp}-{alias_hash}` ID. Sets 14-day TTL. Writes to `session_diary` (NOT `consolidation_cache`).

**`reconcile_open_items(days_back=14)`** — Deduplicates open items across all diary entries. Groups by normalized text (lowercase, stripped bullet/number prefixes), counts occurrences, tracks first/last seen dates. Returns `{items: [{text, count, first_seen, last_seen}], total_raw, total_unique}`.

**`upsert_consolidation_cache(...)`** — Arc-only. Writes raw YAML output from Granite-4.1-3B consolidation pipeline. Supports probation/activation lifecycle. Generates `consol-*` IDs. **Not fed by session_diary** — consolidation_cache remains Arc-only for provenance traceability.

### ContextRouter (Canonical Recall Path)

- Structured queries over RelationalStore — **all recall routes through ContextRouter**
- Run snapshots, recent events, artifacts, similar runs
- Issue summaries, review findings
- Session diary queries (text search across decisions, open_items, work_completed, raw_text)
- Startup context (Tier 1 knowledge card)

**Methods:**

| Method | Source | Purpose |
|--------|--------|---------|
| `get_run_snapshot(run_id)` | workflow_runs + state_executions + artifacts | Full run state |
| `get_recent_events(run_id, limit)` | event_log | Last N events |
| `get_artifacts(run_id, phase, key)` | artifacts | Filtered artifacts |
| `summarize_run_issues(run_id)` | state_executions + event_log | Failure correlation |
| `find_similar_runs(query, project_id)` | pipelines + workflow_runs | Text-match on tasks |
| `get_review_findings(project_id, limit)` | event_log + workflow_runs | Review findings/verdicts |
| `query_session_diary(query, limit, days_back)` | session_diary | Auto-upserted summaries |
| `get_startup_context(max_tokens)` | consolidation_cache | Tier 1 knowledge card |

### MemoryLayer (Artifact Management)

- Token-budgeted context slices with artifact boundaries
- **Two recall methods:**
  - `unified_recall()` — Four-channel recall (text + structural + execution + diary)
  - `unified_log_recall()` — Multi-channel log recall (8 channels + service health + MCP status)
- Unified four-channel recall (all routed through ContextRouter):

| Channel | Source | When Included |
|---------|--------|---------------|
| **Text Memory** | memsearch + ContextRouter.get_artifacts() + get_review_findings() | Always |
| **Structural Graph** | RelationalStore.get_workflow_definitions() | Only when query contains `phase/workflow/pipeline/transition/state/gate/tdd` |
| **Execution History** | ContextRouter.find_similar_runs() | Only runs from last 3 days |
| **Session Diary** | ContextRouter.query_session_diary() | When query matches diary entries; skips entries with no structured fields |

- Artifact ingestion, eviction, context slicing
- **Never cuts mid-artifact** — uses `ARTIFACT_BOUNDARY` markers
- Fallback: direct DB queries when ContextRouter unavailable

### ReviewService (Review Lifecycle)

- `start_review(reviewer, target, run_id)` → creates pipeline + workflow_run + seed event
- `log_finding(run_id, severity, summary, fix, evidence, action)` → writes event + artifact
- `record_verdict(run_id, verdict, reason)` → updates status + logs verdict + stores artifact
- All writes route through RelationalStore public methods
- Input validation through OutputGate

### MemIndex (Vector Indexing)

**Full documentation:** [11-memsearch.md](11-memsearch.md) — MemSearch architecture, Milvus schema, indexing pipeline, direct text upsert.

- Wraps memsearch for project-aware indexing
- File type inference: `code`, `spec`, `doc`, `review`
- Graceful degradation when memsearch unavailable
- Fire-and-forget with `fcntl.flock()` (released on process death)

### ProjectAwareMemSearch (MemSearch Wrapper)

**Full documentation:** [11-memsearch.md](11-memsearch.md)

- Adds `project_id` tagging and filtering to memsearch
- Client-side filtering (memsearch v0.4.x lacks server-side filter_expr)

## MCP Server (FastMCP)

### Transport

#### memory_service (SSE Transport — Primary for Extension)

```bash
# SSE transport server (standalone, with retry queue)
python3 -m super_council.memory_service --sse
# Binds to config.mcp.host:config.mcp.port (default 127.0.0.1:18097)
# Proxies tool calls to memory_service HTTP on :18098
# Queues failed calls for retry with exponential backoff

# Health check
python3 -m super_council.memory_service --health

# Manual drain (retry pending calls once)
python3 -m super_council.memory_service --drain
```

#### memory_service (HTTP Backend + Legacy SSE)

```bash
# HTTP backend (used by memory_service proxy)
# Runs on :18098 alongside existing SSE on :18096
# Exposes: POST /v1/memory/tool/{name}, GET /v1/memory/tools, GET /v1/memory/health

# Legacy SSE (direct connection, no retry queue)
python3 -m super_council.memory_service --mcp-sse
# Binds to :18096 (deprecated — use memory_service :18097 instead)

# stdio (for Pi agent — subprocess per call)
python3 -m super_council.memory_service --mcp-stdio

# Streamable HTTP (alternative HTTP transport)
python3 -m super_council.memory_service --mcp-streamable-http

# Health check
python3 -m super_council.memory_service --health

# One-shot recall
python3 -m super_council.memory_service --recall "query" --max-tokens 512
```

### SSE Protocol Flow (via memory_service)

```
Extension                    memory_service                  memory_service
   │                              │                              │
   │──── GET /sse ───────────────>│                              │
   │<─── event: endpoint ─────────│                              │
   │<─── data: /messages/?sid=x    │                              │
   │                              │                              │
   │── POST /messages/?sid=x ────>│  (initialize)                │
   │<─── event: message ──────────│  (init response)             │
   │                              │                              │
   │── POST /messages/?sid=x ────>│  (tools/call council-recall) │
   │                              │── POST /v1/memory/tool/     ->│
   │                              │   council-recall ────────────>│
   │                              │<── JSON response ────────────│
   │<─── event: message ─────────│  (tool result)                │
   │                              │                              │
   │                              │  On failure:                 │
   │                              │  → Queue to PersistentQueue  │
   │                              │  → Return error + queued:true│
   │                              │  → Background drain retries  │
   │                              │                              │
```

### HTTP Backend Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/memory/tool/{tool_name}` | POST | Generic tool dispatcher (22 tools) |
| `/v1/memory/tools` | GET | List available tools (discovery) |
| `/v1/memory/health` | GET | Health check (status, components, tools_available) |

**Request format:**
```json
POST /v1/memory/tool/council-recall
{
  "query": "architecture",
  "max_tokens": 4096
}
```

**Response format:**
```json
{
  "query": "architecture",
  "channels": {"text": {...}, "diary": {...}},
  "fused_context": "...",
  "token_budget": 4096
}
```

### Tools (22 total)

| Tool | Description | Delegates To |
|------|-------------|-------------|
| `council-recall` | Four-channel unified recall | MemoryLayer.unified_recall() |
| `unified_log_recall` | Multi-channel log recall + service health | MemoryLayer.unified_log_recall() |
| `get_context_slice` | Token-budgeted context slice | MemoryLayer.get_context_slice() |
| `get_recent_events` | Recent execution events | ContextRouter.get_recent_events() |
| `get_run_snapshot` | Full run snapshot | ContextRouter.get_run_snapshot() |
| `summarize_run_issues` | Issue summary with severity | ContextRouter.summarize_run_issues() |
| `get_review_findings` | Recent review findings | ContextRouter.get_review_findings() |
| `query_session_diary` | Query auto-upserted session diary | ContextRouter.query_session_diary() |
| `reconcile_open_items` | Deduplicate todos across diary entries | RelationalStore.reconcile_open_items() |
| `memsearch_index_file` | Index file into memsearch | MemIndex.index_file() |
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
| `upsert_summary` | Mechanical session diary upsert + operation logging | RelationalStore.upsert_session_diary() |

#### `unified_log_recall` — Multi-Channel Log Recall

Added 2026-05-30. Queries across all log sources with token budgeting and service health reporting.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | (required) | Search query text |
| `max_tokens` | int | 4096 | Token budget for fused context |
| `days_back` | int | 7 | Only entries from last N days |
| `channels` | string | null | Comma-separated channel names (null = all) |
| `severity` | string | null | Filter events by severity level |

**Channels queried:**

| Channel | Source | Parser |
|---------|--------|-------|
| `system_events` | event_log table | SQL LIKE match |
| `session_diary` | session_diary table | ContextRouter.query_session_diary() |
| `consolidation` | consolidation_cache table | RelationalStore.query_consolidation_cache() |
| `daily_logs` | `~/.council-memory/daily/*.md` | DailyLogParser (markdown tables) |
| `chat_summaries` | `~/.council-memory/chat-summaries/*.md` | ChatSummaryQuery (sectioned markdown) |
| `workflow_state` | workflow_runs table | SQL LIKE match |
| `failures` | state_executions (outcome=failure) | SQL query |
| `service_logs` | journalctl (memory-service + memory-service) | SystemdLogTailer (journal query + errors) |
| `mcp_queue` | `~/.council-memory/mcp-pending/` | PersistentQueue inspection |
| `supervisor_log` | journalctl (fallback: `/tmp/super-council.log`) | SystemdLogTailer → SupervisorLogTailer |

**Response format:**

```json
{
  "query": "memory",
  "service_health": {
    "services": {
      "supervisor": {"status": "down", "port": 8090},
      "memory_service": {
        "status": "running", "port": 18098,
        "http_status": "healthy", "systemd": "active",
        "details": "HTTP backend for memory_service proxy"
      },
      "memory_service": {
        "status": "running", "port": 18097,
        "tcp_status": "listening", "systemd": "active",
        "details": "SSE transport with retry and backoff"
      },
      "arc_summarizer": {"status": "running", "port": 18095},
      "memsearch": {"status": "available"},
      "web_search": {"status": "available"},
      "sse_sessions": {
        "status": "connected", "port": 18097,
        "active_sessions": 1,
        "pi_extension": {"connected": true, "pid": 12345}
      }
    },
    "last_check": "2026-05-30T...",
    "check_duration_ms": 3252.4
  },
  "mcp_server": {
    "memory_service": {
      "host": "127.0.0.1", "port": 18097,
      "transport": "sse", "status": "running",
      "sse_endpoint": "http://127.0.0.1:18097/sse",
      "details": "SSE transport with retry and backoff"
    },
    "memory_service": {
      "host": "127.0.0.1", "port": 18098,
      "status": "running",
      "http_endpoint": "http://127.0.0.1:18098/v1/memory/health",
      "details": "HTTP backend for memory_service proxy"
    },
    "architecture": "Extension → memory_service (SSE:18097) → memory_service (HTTP:18098)"
  },
  "channels": {
    "system_events": {"matches": 9, "context": "..."},
    "service_logs": {"matches": 15, "errors": 2, "context": "..."},
    "mcp_queue": {"matches": 1, "pending": 1, "context": "..."},
    ...
  },
  "fused_context": "## Service Health\nmemory_service: running (18097), memory_service: running (18098)\n\n## service_logs (15 matches)\n...",
  "token_budget": 4096,
  "context_length": 6741
}
```

**Log Parsers** (`memory_service/log_parsers.py`):

| Class | Purpose | Format |
|-------|---------|--------|
| `DailyLogParser` | Parse daily council logs | Markdown tables: `\| Time \| Event \| Model \| Detail \| Status \| Duration \|` |
| `ChatSummaryQuery` | Parse chat session summaries | Sectioned markdown: Topics Discussed, Key Decisions, Work Completed, Open Items |
| `SupervisorLogTailer` | Tail supervisor log (legacy) | Plain text with timestamps, tail N lines, keyword search |
| `SystemdLogTailer` | Query systemd journal for memory-service + memory-service | journalctl: tail, search, get_recent, get_errors |

**Graceful degradation:** Each channel catches exceptions independently. Failed channels return `{"matches": 0, "context": "", "error": "..."}` without affecting other channels. Service health always included regardless of channel selection.

#### Auto-Detection Hook (Pi Extension `message_end`)

The Pi extension (`council-tools/index.ts`) installs a `message_end` hook that fires after every assistant message. It performs **purely mechanical** pattern detection via a multi-signal scorer (replaced the 10-header binary check in 2026-05-30):

**Scoring channels:**

| Signal | Pattern | Points |
|--------|---------|--------|
| **High-signal headers** | `##` or `###` Key Decisions, Topics Discussed, Work Completed, Session Summary, Research Findings | 3pts each |
| **Medium-signal headers** | `##` or `###` Open Items, Follow-ups, Decisions, Recommendations, Analysis, Updates, Changes, Summary, Findings, Results, Completed, Next Steps, Action Items | 1pt each |
| **Multi-sections** | 3+ total sections (## or ###) | 2pts |
| **Subsection tree** | 1+ ## parent + 3+ ### children | 2pts |
| **List density** | 5+ list items (bullets `-`, `*`, `+` OR numbered `1.`, `2)`, etc.) | 1pt |
| **Low code ratio** | <10% code block characters | 1pt |
| **Subsections-only penalty** | 3+ ### with zero ## | -2pts (soft) |

**Threshold:** 4 points → triggers `upsert_summary` MCP tool.

**Anti-noise vetoes** (immediate SKIP, no scoring):

| Veto | Detection |
|------|-----------|
| **Error log** | Text starts with `ERROR`, `WARN`, `Traceback`, or `File ".*`, line \d+` |
| **Code-heavy** | Code blocks exceed 30% of total text |
| **API docs** | 2+ API patterns matched: `` `name` (type, required) ``, `## Parameters`, `## Response Format`, `## Request Body`, `## Error Codes` |
| **Too short** | Text < 200 characters |

**Test results (8/8 passing):**

| Case | Expected | Got | Score |
|------|----------|-----|-------|
| Updates Applied (1 ## + 4 ### + 11 bullets) | CATCH | CATCH | 7 |
| Error log | VETO | VETO (error_log) | — |
| Code-heavy (3 code blocks) | VETO | VETO (code_heavy) | — |
| Research summary (3 high + 2 medium headers) | CATCH | CATCH | 15 |
| Simple prose review | SKIP | SKIP | 1 |
| Short message (< 200 chars) | VETO | VETO (too_short) | — |
| API docs (param + ## Error Codes) | VETO | VETO (api_doc) | — |
| Review with ### + numbered items | CATCH | CATCH | 6 |

**Operation flow:**
1. Score ≥ 4 → triggers `upsert_summary` MCP tool
2. Writes to `session_diary` table with `source: "auto-detected-assistant-message"`
3. Generates `sess-{timestamp}-{alias_hash}` ID
4. Parses `##` and `###` headers into structured fields (decisions, open_items, work_completed, session_context)
5. **No model involvement** — purely regex matching + DB insert
6. **~15ms latency** via persistent SSE connection (no reconnect overhead)
7. Graceful degradation on failure (catches errors, logs to console)

This implements the "write → manage → read" memory loop: summaries are captured automatically during conversation, without the agent needing to explicitly call `memory.upsert_summary()`.

**Session Diary in Recall:** Auto-upserted diary entries are surfaced via `ContextRouter.query_session_diary()` in the unified recall pipeline. Entries with no structured fields (all NULL decisions/open_items/work_completed) are skipped. Text search across all structured fields.

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

### Via `memory_service` (Standalone — 3 transports)

| Tool | Available | Notes |
|------|-----------|-------|
| All 22 tools above | ✅ | Via FastMCP stdio / SSE / streamable-http |
| All 7 resources | ✅ | Via FastMCP resource protocol |
| Model swapping | ❌ | Supervisor-only |
| Chat completions | ❌ | Supervisor-only |
| Delegation | ❌ | Supervisor-only |
| Fanout | ❌ | Supervisor-only |
| Pipeline advancement | ❌ | Supervisor-only |

**Transport selection:**

| Transport | Flag | Use Case |
|-----------|------|----------|
| stdio | `--mcp-stdio` | Pi agent subprocess (per-call spawn) |
| SSE | `--mcp-sse` | Persistent connection (Pi extension, external clients) |
| streamable-http | `--mcp-streamable-http` | Alternative HTTP transport |

SSE binds to `config.mcp.host:config.mcp.port` (default `127.0.0.1:18096`).

**The `memory_service` is purely the memory/recall/review layer.** It does NOT handle model swapping, chat completions, delegation, or pipeline state machine advancement. Those require the supervisor's proxy architecture and upstream llama-server management.

## Configuration

### config-subsystem.json (memory + memory_service sections)

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
      "transport": "sse",
      "host": "127.0.0.1",
      "port": 18097,
      "http_port": 18098
    },
    "consolidation_ttl_days": 14,
    "consolidation_probation_enabled": true,
    "tier1_max_tokens": 512
  },
  "memory_service": {
    "host": "127.0.0.1",
    "port": 18097,
    "backend_url": "http://127.0.0.1:18098",
    "retry": {
      "max_retries": 10,
      "base_delay_ms": 2000,
      "max_delay_ms": 300000,
      "queue_dir": "~/.council-memory/mcp-pending"
    }
  }
}
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `COUNCIL_DB_PATH` | Override database path | `~/.council-memory/pipelines.db` |
| `COUNCIL_MCP_HOST` | memory_service SSE host | `127.0.0.1` |
| `COUNCIL_MCP_PORT` | memory_service SSE port | `18097` |
| `COUNCIL_MEMORY_HOST` | memory_service HTTP host | `127.0.0.1` |
| `COUNCIL_MEMORY_PORT` | memory_service HTTP port | `18098` |

## Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `mcp>=1.0.0` | FastMCP server + stdio client | ✅ |
| `memsearch` | Vector indexing (optional) | ⚠️ Graceful degradation |
| `faiss` | ANN search (via memsearch) | ⚠️ Via memsearch |
| `milvus-lite` | Vector DB (via memsearch) | ⚠️ Via memsearch |

## File Locations

### memory_service (HTTP Backend + Business Logic)

| Component | Path |
|-----------|------|
| MemoryService | `super_council/memory_service/__init__.py` |
| RelationalStore | `super_council/memory_service/store.py` |
| ContextRouter | `super_council/memory_service/router.py` |
| MemoryLayer | `super_council/memory_service/layer.py` |
| ReviewService | `super_council/memory_service/review.py` |
| MemIndex | `super_council/memory_service/index.py` |
| ProjectAwareMemSearch | `super_council/memory_service/memsearch_wrapper.py` |
| HTTP Endpoints | `super_council/memory_service/http_endpoints.py` |
| FastMCP Server | `super_council/memory_service/mcp_server.py` |
| Health Checker | `super_council/memory_service/health.py` |
| Log Parsers | `super_council/memory_service/log_parsers.py` |
| CLI entry point | `super_council/memory_service/__main__.py` |
| Config | `super_council/memory_service/config.py` |

### memory_service (SSE Transport + Retry)

| Component | Path |
|-----------|------|
| MCPTransport | `super_council/memory_service/transport.py` |
| PersistentQueue | `super_council/memory_service/retry.py` |
| Config | `super_council/memory_service/config.py` |
| CLI entry point | `super_council/memory_service/__main__.py` |

### Extension (Pi Client)

| Component | Path |
|-----------|------|
| council-tools | `~/.pi/agent/extensions/council-tools/index.ts` |

### Data Files

| Resource | Path |
|----------|------|
| Database | `~/.council-memory/pipelines.db` |
| Memsearch DB | `~/.memsearch/milvus.db` |
| Daily logs | `~/.council-memory/daily/*.md` |
| Chat summaries | `~/.council-memory/chat-summaries/*.md` |
| MCP pending queue | `~/.council-memory/mcp-pending/*.json` |
| Extension state | `~/.council-memory/extension-state/` |
