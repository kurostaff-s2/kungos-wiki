# Code Graph Subsystem

> Structural code recall via two MCP servers reading the same `pipelines.db`. Python server provides 12 tools (10 codegraph + 2 JOIN). TypeScript server provides 10 tools including `context` and `explore`. Zero data duplication — TS reads via SQLite views.

## Architecture

```
Pi agent
├── Python MCP (:18096 SSE)
│   ├── 10 codegraph tools (search, node, callers, callees, impact, trace, status, files, neighbors, children)
│   └── 2 JOIN tools (similar_fixes, related_reviews)
│       └── CodeGraphStore → pipelines.db (cg_* tables)
│
└── TS Extension (~/.pi/agent/extensions/codegraph-mcp/)
    ├── 10 TS tools (search, context, explore, node, callers, callees, impact, trace, files, status)
    └── vendor/codegraph/dist/bin/codegraph.js → pipelines.db (via views: nodes, edges, files)
```

**Two servers, one DB.** Python tools query `cg_*` tables directly. TS tools query via SQLite views (`nodes` → `cg_nodes`, `edges` → `cg_edges`, `files` → `cg_files`). WAL mode enables concurrent reads without conflicts.

## Database Schema

All data lives in `~/.council-memory/pipelines.db`.

### Core Tables

| Table | Purpose |
|-------|---------|
| `cg_nodes` | Code symbols (functions, classes, methods, variables) |
| `cg_edges` | Relationships (calls, references, contains, imports) |
| `cg_files` | Indexed file metadata |
| `cg_nodes_fts` | FTS5 virtual table (content-synced with `cg_nodes` via rowid) |
| `review_findings` | Review findings for `related_reviews` tool (backfilled from `event_log`) |

### SQLite Views (TS compatibility)

```sql
CREATE VIEW nodes AS SELECT * FROM cg_nodes;
CREATE VIEW edges AS SELECT source, target, kind, metadata, line, col, provenance FROM cg_edges;
CREATE VIEW files AS SELECT * FROM cg_files;
```

TS server expects table names `nodes`, `edges`, `files`. Views expose our `cg_*` tables under those names. **Read-only** — writes go to `cg_*` tables only.

### FTS5 Triggers

Three triggers keep `cg_nodes_fts` in sync with `cg_nodes`:

| Trigger | Fires On | Action |
|---------|----------|--------|
| `cg_nodes_ai` | INSERT | Add new row to FTS5 |
| `cg_nodes_ad` | DELETE | Delete row from FTS5 |
| `cg_nodes_au` | UPDATE | Delete old + insert new in FTS5 |

## Indexing

### Full Re-index

```bash
cd ~/Coding-Projects/7-council/super_council

# Step 1: Run codegraph binary (populates .codegraph/codegraph.db)
node vendor/codegraph/dist/bin/codegraph.js init /path/to/project
# → Scans files, parses code, resolves refs → .codegraph/codegraph.db

# Step 2: Sync to pipelines.db (ATTACH + COPY to cg_* tables)
python3 code_graph/sync.py /path/to/project /home/chief/.council-memory/pipelines.db
# → Upserts nodes/edges/files, rebuilds FTS5, ensures triggers

# Force re-index (ignore cache)
python3 code_graph/sync.py /path/to/project --force
```

### FTS5 Rebuild Only

```bash
# Fix FTS5 drift or broken triggers (no Node.js needed)
python3 code_graph/sync.py --rebuild-fts
```

### Automated Re-indexing

`watch.py` provides three modes:

```bash
# Polling mode
python3 code_graph/watch.py /path/to/project --interval 120 --debounce 30

# inotify mode (instant, requires inotify-tools)
python3 code_graph/watch.py /path/to/project --inotify

# One-shot (for cron)
python3 code_graph/watch.py /path/to/project --once
```

State file: `~/.council-memory/watch-state.json` (tracks source DB hash to prevent re-index loops).

### `codegraph affected` — CI/Test Impact Analysis

Upstream CLI tool (v0.9.x). Traces import dependencies transitively to find which test files are affected by changed source files.

```bash
# Pass files directly
codegraph affected src/auth.py src/api.py

# Pipe from git diff
git diff --name-only HEAD | codegraph affected --stdin

# Filter to specific test pattern
codegraph affected src/auth.py --filter "tests/test_*"

# JSON output for scripting
codegraph affected src/auth.py --json

# Quiet mode (file paths only)
git diff --name-only HEAD | codegraph affected --stdin --quiet
```

**CI example:**
```bash
#!/bin/bash
AFFECTED=$(git diff --name-only HEAD | codegraph affected --stdin --quiet)
if [ -n "$AFFECTED" ]; then
  pytest $AFFECTED
else
  echo "No affected tests"
fi
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--stdin` | Read file list from stdin | `false` |
| `-d, --depth` | Max dependency traversal depth | `5` |
| `-f, --filter` | Glob pattern for test files | auto-detect |
| `-j, --json` | Output as JSON | `false` |
| `-q, --quiet` | Output file paths only | `false` |

Not exposed as an MCP tool — use the CLI directly in CI/scripts.

## Python MCP Server

### Tool Registration

Tools registered in `memory_service/mcp_server.py` via `_register_codegraph_tools()`:

```python
def _register_codegraph_tools(self) -> None:
    from super_council.code_graph.tools import TOOL_REGISTRY, TOOL_DESCRIPTIONS
    cg = self._cg_store
    for name, handler in TOOL_REGISTRY.items():
        description = TOOL_DESCRIPTIONS.get(name, "")
        tool_func = self._mcp.tool(name=name, description=description)(
            self._make_tool_wrapper(handler, cg)
        )
```

`MemoryMCPHandler.__init__` accepts optional `cg_store`:
- If provided, uses it directly
- If not, creates `CodeGraphStore(config.db_path)`
- If creation fails, tools return error JSON (graceful degradation)

### 12 Python Tools

| Tool | Handler | Description |
|------|---------|-------------|
| `codegraph_search` | `tool_search` | FTS5 symbol search |
| `codegraph_node` | `tool_node` | Single symbol details + callers/callees trail |
| `codegraph_callers` | `tool_callers` | Incoming calls/references |
| `codegraph_callees` | `tool_callees` | Outgoing calls/references |
| `codegraph_impact` | `tool_impact` | Blast radius analysis (BFS incoming) |
| `codegraph_trace` | `tool_trace` | Shortest call path between two symbols |
| `codegraph_status` | `tool_status` | Index health (files/nodes/edges) |
| `codegraph_files` | `tool_files` | Indexed file tree |
| `codegraph_neighbors` | `tool_neighbors` | Callers + callees + siblings |
| `codegraph_children` | `tool_children` | Container children (class members, etc.) |
| `similar_fixes` | `tool_similar_fixes` | JOIN cg_nodes with event_log |
| `related_reviews` | `tool_related_reviews` | JOIN cg_nodes with review_findings |

All tools return formatted Markdown strings (truncated to 15,000 chars).

### JOIN Tools

#### similar_fixes — JOIN with event_log

Maps event_log columns to tool-expected names:

| event_log column | → Tool field |
|-------------------|-------------|
| `message` | → `summary` |
| `metadata` | → `content` |
| `occurred_at` | → `created_at` |

Searches: full path, basename — both in `message` and `metadata`.

#### related_reviews — JOIN with review_findings

```sql
CREATE TABLE IF NOT EXISTS review_findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT,
    severity TEXT,
    summary TEXT,
    fix TEXT,
    details TEXT,
    content TEXT,
    created_at TEXT
);
```

Backfilled from `event_log` during sync. Searches: full path, basename, stem — in `summary` and `content`.

Both JOIN tools return empty results (no errors) if schemas differ from expected.

## TypeScript Extension

### Extension Location

`~/.pi/agent/extensions/codegraph-mcp/index.ts` — spawns TS server via stdio, registers 10 tools.

### How It Works

```
Pi extension (TypeScript)
    ↓ spawn stdio
vendor/codegraph/dist/bin/codegraph.js serve --mcp --path /path/to/project
    ↓ reads via views
pipelines.db (nodes → cg_nodes, edges → cg_edges, files → cg_files)
```

The TS server reads `pipelines.db` directly via SQLite views. No data duplication, no cross-process sync needed for reads.

### Environment Variables

The extension sets these env vars when spawning the TS server:

| Variable | Value | Purpose |
|----------|-------|---------|
| `CODEGRAPH_NO_DAEMON` | `1` | Bypass shared daemon (direct mode) |
| `CODEGRAPH_SKIP_MIGRATIONS` | `1` | Skip v2/v3/v4 migrations (would ALTER views) |
| `CODEGRAPH_FTS5_TABLE` | `cg_nodes_fts` | Override FTS5 table name |
| `CODEGRAPH_CONTENT_TABLE` | `cg_nodes` | Join FTS5 to `cg_nodes` via rowid (view hides rowid) |
| `CODEGRAPH_DB_PATH` | `~/.council-memory/pipelines.db` | Point at our DB instead of `.codegraph/codegraph.db` |

**Why rowid join:** The `nodes` view doesn't expose `rowid` (SQLite views of TEXT-PK tables hide it). FTS5 must join directly to `cg_nodes` via `rowid` in external-content mode.

### 10 TS Tools

| Tool | Description |
|------|-------------|
| `codegraph_search` | FTS5 + LIKE + fuzzy search |
| `codegraph_context` | Build context (search + traverse + extract) — **not in Python** |
| `codegraph_explore` | Multi-symbol source explorer (adaptive sizing) — **not in Python** |
| `codegraph_node` | Single symbol details |
| `codegraph_callers` | Reverse call graph |
| `codegraph_callees` | Forward call graph |
| `codegraph_impact` | Blast radius analysis |
| `codegraph_trace` | Call path tracing (dynamic dispatch) |
| `codegraph_files` | Project file listing |
| `codegraph_status` | Index statistics |

### Connect-Time Catch-Up

Before the first query, the extension checks if any `.py` source file is newer than `.codegraph/codegraph.db`. If so, it runs:
1. `codegraph index` (incremental — only changed files)
2. `sync.py` (copy to `pipelines.db`)

This ensures the agent never gets stale index data after code edits, even with the daemon disabled. Runs once per extension lifetime (not per query).

### Tool Overlap

| Tool | Python | TS | Notes |
|------|--------|----|-------|
| `codegraph_search` | ✅ | ✅ | Identical functionality |
| `codegraph_node` | ✅ | ✅ | Python includes callers/callees trail |
| `codegraph_callers` | ✅ | ✅ | Identical |
| `codegraph_callees` | ✅ | ✅ | Identical |
| `codegraph_impact` | ✅ | ✅ | Identical |
| `codegraph_trace` | ✅ | ✅ | TS includes dynamic-dispatch hops |
| `codegraph_files` | ✅ | ✅ | Identical |
| `codegraph_status` | ✅ | ✅ | Identical |
| `codegraph_neighbors` | ✅ | ❌ | Python-only |
| `codegraph_children` | ✅ | ❌ | Python-only |
| `similar_fixes` | ✅ | ❌ | Python-only (JOIN event_log) |
| `related_reviews` | ✅ | ❌ | Python-only (JOIN review_findings) |
| `codegraph_context` | ❌ | ✅ | TS-only (257 lines, task-based) |
| `codegraph_explore` | ❌ | ✅ | TS-only (722 lines, multi-file) |

**Total: 22 unique tools** (12 Python + 10 TS, 10 shared + 4 Python-only + 2 TS-only).

## File Locations

| Path | Purpose |
|------|---------|
| `super_council/code_graph/__init__.py` | Package exports |
| `super_council/code_graph/store.py` | CodeGraphStore API + FTS5 escaping |
| `super_council/code_graph/sync.py` | Indexing + schema auto-creation + views + FTS rebuild |
| `super_council/code_graph/sync-all.py` | Multi-project sync orchestrator |
| `super_council/code_graph/tools.py` | 12 MCP tool handlers + JOIN helpers |
| `super_council/code_graph/watch.py` | Automated re-indexing watcher |
| `super_council/vendor/codegraph/` | Vendored codegraph (colbymchenry) |
| `super_council/vendor/codegraph/src/db/index.ts` | Option B: migration skip + DB path override |
| `super_council/vendor/codegraph/src/db/queries.ts` | Option B: FTS5 table + content table override |
| `~/.pi/agent/extensions/codegraph-mcp/index.ts` | Pi extension (10 TS tools via stdio) |
| `~/.council-memory/pipelines.db` | SQLite database (shared Python + TS) |
| `~/.council-memory/sync-all.json` | Multi-project config (9 project paths) |
| `~/.council-memory/watch-state.json` | Watcher state |

## Implementation Notes

### FTS5 Special Characters

Filenames with `.`, `/`, `[`, `]`, `(`, `)`, `-` are auto-escaped via `CodeGraphStore._escape_fts5()` — wraps in double quotes for literal matching.

### sqlite3.Row Access

`sqlite3.Row` objects don't support `.get()` — use `row['column'] or default` instead.

### Output Format

All tools return formatted Markdown strings (not JSON), truncated to 15,000 chars. Tools are consumed by LLM agents — Markdown is more readable and token-efficient than JSON.

### Graceful Degradation

If `CodeGraphStore` creation fails, all Python tools return `{"error": "CodeGraphStore unavailable"}`. If JOIN schemas differ, JOIN tools return empty results. The subsystem functions independently of memory layer state.

### Schema Resilience

The `sync.py` script is self-healing — it auto-creates all required tables and views on every sync. This means:
- `pipelines.db` can be wiped and rebuilt from scratch without manual schema setup
- Views (`nodes`, `edges`, `files`) are recreated every sync — no stale view issues
- FTS5 triggers are fixed/recreated — no broken trigger issues
- The `--rebuild-fts` flag works standalone (no Node.js needed) for FTS5 drift fixes

## Current Index

| Metric | Value |
|--------|-------|
| Files indexed | 1,510 |
| Nodes | 18,848 |
| Edges | 41,806 |
| FTS5 rows | 18,848 |
| DB size | 11.16 MB |

### Indexed Projects (9)

| # | Project | Nodes | Language |
|---|---------|-------|----------|
| 1 | `super_council` | 1,746 | Python |
| 2 | `kteam-fe-chief` | 2,947 | JavaScript |
| 3 | `kurogg-nextjs` | 1,161 | JavaScript/JSX |
| 4 | `rebellion-nextjs` | 73 | JavaScript/JSX |
| 5 | `renderedge-nextjs` | 299 | JavaScript/JSX |
| 6 | `kteam-dj-chief` | 3,597 | Python |
| 7 | `kteam legacy` | 3,727 | JavaScript/JSX |
| 8 | `pi-coding-agent/dist` | 5,157 | TypeScript |
| 9 | `.pi/agent/extensions` | 143 | TypeScript |

### Languages

| Language | Nodes |
|----------|-------|
| JavaScript | 7,361 |
| Python | 6,534 |
| JSX | 2,752 |
| TypeScript | 2,132 |
| TSX | 67 |
| XML | 2 |

### Schema Auto-Creation

`sync.py` now auto-creates the full schema on every sync (idempotent, survives DB wipes):
- `_ensure_schema()` — creates `cg_nodes`, `cg_edges`, `cg_files`, `cg_nodes_fts`
- `_ensure_views()` — creates `nodes`, `edges`, `files` views for TS server compatibility
- `_ensure_fts_triggers()` — creates `cg_nodes_ai/ad/au` triggers

### Multi-Project Sync

`sync-all.py` orchestrates indexing across all 9 projects:
```bash
# Full sync (all projects)
python3 super_council/code_graph/sync-all.py --force

# Add a project
python3 super_council/code_graph/sync-all.py --add /path/to/project

# List configured projects
python3 super_council/code_graph/sync-all.py --list
```

Config: `~/.council-memory/sync-all.json`
