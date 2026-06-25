# CBM-MCP Tool Guide: Effective Utilization

**Project:** codebase-memory-mcp  
**Date:** 2026-06-25  
**Tools:** `codebase_*` (MCP direct) + `codegraph_*` (wrapper/enhanced)

---

## Quick Reference: Which Tool For What

| Task | Best Tool | Why |
|------|-----------|-----|
| "Find function X" | `codegraph_search` | FTS5 + prefix + fuzzy, faster than grep |
| "How does X work?" | `codegraph_context` | Search + graph traversal + code extraction in one call |
| "Show me X, Y, Z source" | `codegraph_explore` | Multi-symbol, grouped by file, budget-aware |
| "Who calls X?" | `codegraph_callers` | Reverse call graph, precise |
| "What does X call?" | `codegraph_callees` | Forward call graph |
| "What breaks if I change X?" | `codegraph_impact` | Multi-hop blast radius, grouped by file |
| "How does X reach Y?" | `codegraph_trace` | Full path with dynamic-dispatch hops |
| "Find text pattern + context" | `codebase_grep` | grep enriched with graph relationships |
| "List project files" | `codegraph_files` | From index, not filesystem |
| "High-level architecture" | `codebase_arch` | Clusters, hotspots, boundaries, layers |
| "Index a new repo" | `codebase_index` | Full graph indexing |
| "Check for dead code" | `codebase_search` with `min_degree=0` | Finds disconnected nodes |
| "Find duplicates" | `codebase_query` over `SIMILAR_TO` edges | MinHash-based near-clone detection |
| "Trace data flow" | `codebase_trace` mode=data_flow | Arg-to-param mapping |
| "Architecture decisions" | `codebase_adr` | Store/query ADRs |
| "Git diff → graph impact" | `codebase_changes` | Pre-commit analysis |

---

## Tool Families

### `codebase_*` (Direct MCP)
- Pass `project: "home-chief-Coding-Projects-kteam-dj-chief"` to all calls
- `codebase_search`: BM25 + semantic vector hybrid
- `codebase_query`: Cypher (see Cypher limitations below)
- `codebase_trace`: calls / data_flow / http modes
- `codebase_snippet`: Read a single symbol's source
- `codebase_arch`: Architecture overview (clusters, hotspots, layers)

### `codegraph_*` (Wrapper/Enhanced)
- No project parameter needed (auto-resolved)
- `codegraph_search`: FTS5 + prefix matching + Levenshtein fuzzy
- `codegraph_context`: **Best single tool** — combines search, graph traversal, and code extraction
- `codegraph_explore`: Multi-symbol source extraction with adaptive budget
- `codegraph_node`: Single symbol details (signature, docstring, location)
- `codegraph_callers` / `codegraph_callees`: Precise call graph traversal
- `codegraph_impact`: Blast radius analysis (depth 2-10)
- `codegraph_trace`: Path from symbol X to symbol Y

---

## Common Patterns

### 1. Dead Code Detection
```
Step 1: codebase_search(label="Function", min_degree=0, max_degree=1, exclude_entry_points=true)
Step 2: For each candidate → codegraph_callers(symbol) to confirm 0 callers
Step 3: codebase_trace(mode="data_flow") to confirm no data-flow connections
Step 4: codegraph_impact(depth=2) — 0 affected = safe to delete
```

**Caveat:** Django/DRF framework hooks (`__str__`, `save`, `validate`, `authenticate`) appear as low-degree but are dynamically dispatched. Filter these out.

### 2. Duplicate Detection
```
Step 1: codebase_query("MATCH (f:Function)-[:SIMILAR_TO]->(g:Function) WHERE f.name = g.name RETURN f.name, f.file_path, g.file_path")
Step 2: For each pair → grep imports to determine which copy is primary
Step 3: Switch imports to primary, delete secondary
```

### 3. Impact Analysis Before Refactor
```
Step 1: codegraph_impact(symbol, depth=2) — see blast radius
Step 2: codegraph_callers(symbol) — see direct callers
Step 3: codegraph_trace(from=caller, to=symbol) — verify call paths
Step 4: If blast radius > 50 symbols → write tests first
```

### 4. Understanding a Flow
```
Step 1: codegraph_context(task="how does login work") — broad context
Step 2: codegraph_trace(from="login", to="_issue_jwt_tokens") — specific path
Step 3: codegraph_explore(query="login, _issue_jwt_tokens, for_user") — read all source
```

### 5. Architecture Exploration
```
Step 1: codebase_arch(aspects=["all"]) — full overview
Step 2: codebase_query("MATCH (f:Function) WHERE f.complexity > 10 RETURN f.name, f.file_path, f.complexity ORDER BY f.complexity DESC LIMIT 20") — complex functions
Step 3: codegraph_impact(symbol, depth=2) for each hotspot
```

---

## Cypher Limitations (codebase_query)

### Works
- `MATCH (f:Function)-[:CALLS]->(g) WHERE f.name = 'main' RETURN g.name`
- `WHERE f.file_path CONTAINS 'backend'`
- `WHERE f.file_path STARTS WITH 'teams/'`
- `WHERE f.complexity > 10`
- `WHERE f.is_entry_point = true`
- `OPTIONAL MATCH` + `WHERE x.name <> 'value'`
- Multi-hop: `(a)-[:CALLS]->(b)-[:CALLS]->(c)`

### Does NOT Work
- `NOT (f)<-[:CALLS]-()` — "unexpected operator"
- `NOT LIKE` — unsupported
- `IS NULL` / `IS NOT NULL` — unsupported
- `size(collect(...))` — unsupported
- Complex list comprehensions

### Workarounds
- Need "no callers"? Use `codegraph_callers(symbol)` — returns empty if none
- Need "count of callers"? Use `codebase_search(min_degree=0, max_degree=1)` and filter in memory
- Need complex aggregation? Fetch the list, process externally

---

## Node Labels (13 types)

| Label | Use Case |
|-------|----------|
| Function | Standalone functions |
| Method | Class methods |
| Class | Class definitions |
| Variable | Module/class variables |
| File | Source files |
| Module | Python modules |
| Package | External/internal packages |
| Folder | Directory structure |
| Section | Code sections |
| Route | HTTP routes (method + path) |
| Decorator | Decorator definitions |
| Interface | Protocol/interface definitions |
| Project | Root project node |

## Edge Types (19 types)

| Edge | Meaning | Key Use |
|------|---------|---------|
| CALLS | Direct function call | Call graph traversal |
| USAGE | Uses a symbol (broader) | Dependency analysis |
| DEFINES | Parent → child | Structure navigation |
| IMPORTS | Import relationship | Import graph |
| SIMILAR_TO | Near-clone (MinHash) | Duplicate detection |
| SEMANTICALLY_RELATED | Vector match ≥ 0.80 | Concept-based discovery |
| TESTS | Test → tested symbol | Test coverage analysis |
| INHERITS | Class inheritance | Inheritance chains |
| FILE_CHANGES_WITH | Co-change coupling | Refactoring impact |
| WRITES | Writes to variable | Data flow |
| DECORATES | Decorator → function | Decorator analysis |

---

## Best Practices

### 1. Start Broad, Then Narrow
```
codebase_arch() → codegraph_context(task) → codegraph_trace(from, to) → codegraph_explore(query)
```
Don't start with grep. The graph knows relationships text search can't see.

### 2. Use `codegraph_context` as Your First Tool
It combines search + graph traversal + code extraction. One call replaces search → node → callers → read.

### 3. For Dead Code, Cross-Reference
```
codebase_search(min_degree=0) → codegraph_callers → codebase_trace(data_flow) → codegraph_impact
```
One tool gives candidates, others confirm.

### 4. Semantic Search for Intent, BM25 for Names
- `semantic_query=["authentication flow"]` → finds auth-adjacent code even without "auth" in name
- `query="resolve_access"` → precise symbol match
- BM25 scores are more reliable than semantic scores for symbol lookup

### 5. Impact Before Changes
Always run `codegraph_impact(symbol, depth=2)` before modifying a function. If blast radius > 20, write tests first.

### 6. Entry Points vs Dead Code
Functions with 0 callers might be:
- Entry points (scripts, management commands)
- URL-mapped views (Django routes)
- Framework hooks (`__str__`, `save`, `validate`)
- Actually dead code

Filter entry points with `exclude_entry_points=true`. For views, check URL configs. For framework hooks, know they're dynamically dispatched.

### 7. The Graph is a Snapshot
Run `codebase_changes()` to check if the index is stale. Re-index with `codebase_index()` after significant changes.

---

## Anti-Patterns

### ❌ Using grep when graph tools exist
`grep -rn "resolve_access"` misses dynamic dispatch, imports aliased as different names, and framework hooks. The graph follows actual relationships.

### ❌ Chaining search → node → callers manually
`codegraph_context(task="how does X work")` does all three in one call.

### ❌ Assuming 0 callers = dead code
Django views, DRF serializers, management commands, and framework hooks are dynamically dispatched. Always verify with import checks.

### ❌ Using Cypher NOT operators
They're unsupported. Use `codegraph_callers` for individual checks instead.

### ❌ Ignoring SIMILAR_TO edges
381 duplicate edges are already detected. Query them before manually searching for duplicates.

---

## Project-Specific Notes (kteam-dj-chief)

- **Project ID:** `home-chief-Coding-Projects-kteam-dj-chief` (always pass to `codebase_*` tools)
- **Core auth function:** `resolve_access` (backend/auth_utils.py) — 215-symbol blast radius
- **Data access:** Everything routes through `get_collection` (275 callers) and `OrderGateway.get` (336 callers)
- **Known dead code:** `backend/views_diagnostic.py`, `backend/cron.py`, `brands/`, `core/` packages
- **Known duplicates:** 3 functions in `backend/utils.py` mirrored in `backend/auth_utils.py`
- **Test coverage:** 81 TEST edges — primarily in `tests/test_access_control.py`
