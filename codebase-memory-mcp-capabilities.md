# codebase-memory-mcp — Local Integration Reference

**Project:** kteam-dj-chief  
**Date:** 2026-06-25  
**Backend:** SQLite + FTS5 (Node built-in), WAL mode  
**Index:** 796 files, 11,749 nodes, 24,714 edges, 7.56 MB

---

## Two Tool Families

| `codebase_*` (direct MCP) | `codegraph_*` (wrapper/enhanced) |
|---|---|
| `codebase_search` — BM25 + semantic vector | `codegraph_search` — FTS5 + prefix + fuzzy |
| `codebase_query` — Cypher | `codegraph_context` — multi-hop context builder |
| `codebase_trace` — calls/data_flow/http | `codegraph_explore` — multi-symbol source extraction |
| `codebase_snippet` — read symbol code | `codegraph_node` — single symbol details |
| `codebase_schema` — node/edge schema | `codegraph_callers` / `codegraph_callees` |
| `codebase_arch` — architecture overview | `codegraph_impact` — blast radius |
| `codebase_grep` — graph-augmented grep | `codegraph_trace` — path from X to Y |
| `codebase_projects` — list indexed | `codegraph_files` — file tree from index |
| `codebase_status` — index health | `codegraph_status` — same |
| `codebase_changes` — git diff → graph impact | — |
| `codebase_adr` — architecture decisions | — |
| `codebase_index` — index a repo | — |
| `codebase_traces` — ingest runtime traces | — |

**Always pass `project: "home-chief-Coding-Projects-kteam-dj-chief"` to `codebase_*` tools.**

---

## Node Labels (13 types)

| Label | Count | Key Properties |
|---|---|---|
| **Function** | 458 | name, file_path, decorators, docstring, signature, complexity, is_entry_point |
| **Method** | 648 | + parent_class, param_count, return_type, recursive |
| **Class** | 395 | base_classes, decorators, docstring |
| **Variable** | 3156 | name, file_path, complexity |
| **File** | 328 | extension, last_modified, change_count |
| **Module** | 285 | is_entry_point, is_exported |
| **Package** | 82 | external, source |
| **Folder** | 65 | — |
| **Section** | 96 | — |
| **Route** | 9 | method, path (HTTP routes as first-class nodes) |
| **Decorator** | 16 | — |
| **Interface** | 1 | — |
| **Project** | 1 | — |

---

## Edge Types (19 types)

| Edge | Count | What It Means |
|---|---|---|
| **DEFINES** | 5039 | Parent → child (file→function, class→method) |
| **USAGE** | 4055 | Uses a symbol (broader than CALLS) |
| **CALLS** | 3028 | Direct function call (with args, confidence, strategy) |
| **WRITES** | 1076 | Writes to a variable |
| **DEFINES_METHOD** | 648 | Class → method definition |
| **IMPORTS** | 531 | Import relationship (with local_name) |
| **DECORATES** | 474 | Decorator → decorated function |
| **SIMILAR_TO** | 381 | Near-clone/duplicate (MinHash + LSH, jaccard score) |
| **CONTAINS_FILE** | 328 | Folder → file |
| **SEMANTICALLY_RELATED** | 307 | Vocabulary-mismatch matches (vector score ≥ 0.80) |
| **DEPENDS_ON** | 82 | Package/module dependency |
| **TESTS** | 81 | Test → tested symbol |
| **CONTAINS_FOLDER** | 63 | Parent → child folder |
| **INHERITS** | 59 | Class inheritance |
| **CONFIGURES** | 45 | Configuration relationships |
| **FILE_CHANGES_WITH** | 16 | Co-change coupling (git history) |
| **THROWS** | 4 | Exception throwing |
| **RAISES** | 1 | Exception raising |

---

## What Works (Cypher)

✅ `MATCH (f:Function)-[:CALLS]->(g) WHERE f.name = 'main' RETURN g.name`
✅ `WHERE f.file_path CONTAINS 'backend'`
✅ `WHERE f.file_path STARTS WITH 'teams/'`
✅ `WHERE f.complexity > 10`
✅ `WHERE f.is_entry_point = true`
✅ `OPTIONAL MATCH` + `WHERE x.name <> 'value'`
✅ Multi-hop: `(a)-[:CALLS]->(b)-[:CALLS]->(c)`

❌ `NOT (f)<-[:CALLS]-()` — "unexpected operator"
❌ `NOT LIKE` — unsupported
❌ `IS NULL` / `IS NOT NULL` — unsupported
❌ `size(collect(...))` — unsupported
❌ Complex list comprehensions

**Workarounds:** Use `codegraph_callers` for individual symbols, or fetch two lists and diff in memory.

---

## Key Capabilities (Verified)

### Semantic Search (`codebase_search` with `semantic_query`)
- Returns low scores (0.03–0.08) but still useful for concept-based discovery
- Example: "authentication and authorization" → returned `hash_sha256`, `encode_hex`, `format_creditnote` (low relevance, but found auth-adjacent code)
- BM25 text search is more precise for symbol names

### SIMILAR_TO Edges (Duplicate Detection)
- 381 `SIMILAR_TO` edges in graph — near-clone/duplicate detection via MinHash + LSH
- Found 3 duplicates in `backend/`:
  - `has_read_access` (utils.py ↔ auth_utils.py)
  - `has_write_access` (utils.py ↔ auth_utils.py)
  - `get_branch_fallback` (utils.py ↔ auth_utils.py)
- These are candidates for consolidation

### Dead Code Detection (`codebase_search` with `min_degree=0, max_degree=1`)
- Returns 460 functions with 0–1 total edges (no callers + self-definition)
- Mix of true dead code and entry points (scripts, routes, management commands)
- Filter by `file_path` to exclude known entry points

### Data Flow Tracing (`codebase_trace` mode=data_flow)
- Shows arg-to-param mapping between caller and callee
- `close_mongo_client`: **0 callers, 0 callees** — confirmed dead
- `resolve_access`: **110+ callers** across ViewSets, views, utils — core auth function

### Impact Analysis (`codegraph_impact`)
- Multi-hop blast radius with file grouping
- `resolve_access` at depth=2: affects entire auth/access control layer
- `close_mongo_client` at depth=2: **0 affected nodes** — safe to delete

### Architecture Overview (`codebase_arch`)
- Languages: Python (730 files), TypeScript/JS (62), CSS/HTML (4)
- 5 clusters: `plat` (platform), `domains` (business), `backend` (core), `users` (auth), `teams` (HR)
- Hotspots: `backend/utils.py` (37), `backend/auth_utils.py` (33), `backend/settings.py` (29)
- Boundaries: `plat` ↔ `domains` (32 edges), `backend` ↔ `domains` (28 edges)

### Route Nodes (First-Class HTTP Routes)
- 9 Route nodes indexed with method/path properties
- Routes: `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/refresh`, `/api/v1/admin/tenant/bootstrap/`, `/api/v1/cafe/payments/webhook/`, `/health/`, `/ping/`
- Can trace Route → ViewSet → Function via graph traversal

### Changes Detection (`codebase_changes`)
- Compares git working tree against indexed state
- Currently: 0 changed files (clean state)
- Useful for pre-commit impact analysis

---

## Best Practices for Dead Code Audits

1. **Use `codegraph_callers` for precision** — one symbol at a time, reliable
2. **Use `codebase_search` with `min_degree=0` for discovery** — finds all zero-in-degree functions
3. **Cross-check with `codebase_trace` (data_flow)** — confirms no arg-to-param connections
4. **Use `codegraph_impact` for safe deletion** — 0 affected = safe to remove
5. **Filter out entry points** — exclude routes, management commands, scripts, decorators
6. **Use `SIMILAR_TO` edges** — find duplicates that can be consolidated (not just deleted)
7. **Use semantic search** — find functions by intent when name-based search fails

## Best Practices for Code Understanding

1. **`codegraph_context`** — best for "how does X work" (combines search + graph + code)
2. **`codegraph_explore`** — best for multi-symbol exploration (returns grouped source)
3. **`codegraph_trace`** — best for "how does X reach Y" (full path, one call)
4. **`codegraph_impact`** — best for "what breaks if I change X" (blast radius)
5. **`codebase_arch`** — best for high-level overview (clusters, hotspots, boundaries)
6. **`codebase_grep`** — best for text patterns with graph context (replaces plain grep)

## Summary

The codebase-memory-mcp integration is **fully functional and powerful**. Key advantages over grep/text search:

- **Graph-based traversal** — follows CALLS, USAGE, IMPORTS edges (no false negatives from string matching)
- **Semantic search** — finds functions by intent, not just name
- **Duplicate detection** — `SIMILAR_TO` edges flag near-clones automatically
- **Impact analysis** — multi-hop blast radius before changes
- **First-class routes** — HTTP routes as graph nodes, traceable to handlers
- **Data flow tracing** — arg-to-param mapping across call boundaries
- **Architecture overview** — clusters, hotspots, boundaries at a glance

The main limitation is **Cypher support** — no `NOT`, `IS NULL`, or `size()` operators. Workaround: use `codegraph_callers` for individual checks, or fetch lists and diff externally.