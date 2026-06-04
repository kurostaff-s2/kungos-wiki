# Phase 7: Production Wiring

**Parent plan:** `04-06-2026_council-unified-db-implementation_326ac3.md`
**Phase:** 7 of 7 (FINAL)
**Dependencies:** Phases 0-6 ALL complete
**Estimated effort:** ~45 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Key files for this phase:**
- `memory_service/__init__.py` (MODIFY)
- `memory_service/config.py` (MODIFY)
- `memory_service/mcp_server.py` (MODIFY)
- `scripts/verify_unified_db.py` (CREATE)

## What This Phase Delivers

The final integration. All previous phases produced components that exist as code. This phase wires them together, executes the migration, starts all services, and verifies the full system works end-to-end. **This phase is the gate — nothing is complete until the verification script passes.**

## Pre-Flight Checklist

- [ ] Phase 0: CodeGraph extracted to `codegraph.db`
- [ ] Phase 1: `projects` table exists with FTS5
- [ ] Phase 1A: pplx embedding server running on `:18099`
- [ ] Phase 2: Migration script exists and dry-run passes
- [ ] Phase 3: Odysseus tables created in migrations
- [ ] Phase 4: UnifiedVectorStore implemented
- [ ] Phase 5: Knowledge bridge tables created
- [ ] Phase 6: UnifiedSearchRouter implemented
- [ ] `pipelines.db` backup exists

## Implementation Steps

### Step 1: Execute Database Migration

```bash
# Stop memory-service
systemctl --user stop memory-service.service

# Run migration
cd /home/chief/Coding-Projects/7-council/
python3 scripts/migrate_council_core.py

# Verify migration
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.council-memory/council_core.db')
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print(f'Tables in council_core.db: {len(tables)}')
for t in sorted(tables):
    count = conn.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
    print(f'  {t:40s} {count:>10}')
conn.close()
"
```

### Step 2: Execute Odysseus Data Migration

```bash
cd /home/chief/Coding-Projects/7-council/
python3 scripts/migrate_odysseus_data.py
```

### Step 3: Execute CodeGraph Extraction (if not already done)

```bash
cd /home/chief/Coding-Projects/7-council/
python3 scripts/extract_codegraph.py
```

### Step 4: Update Config Defaults

Modify `memory_service/config.py`:

```python
_DEFAULT_DB_PATH = Path.home() / ".council-memory" / "council_core.db"
```

### Step 5: Wire MemoryService Components

Modify `memory_service/__init__.py`. Add to `_init_components()`:

```python
# 8. UnifiedVectorStore — single vector backend
try:
    from .vector_store import UnifiedVectorStore
    self._vector_store = UnifiedVectorStore(
        embedding_url="http://127.0.0.1:18099"
    )
    log.info("UnifiedVectorStore initialized")
except Exception as e:
    log.warning("UnifiedVectorStore init failed: %s", e)

# 9. UnifiedSearchRouter — single search interface
try:
    if self._vector_store and self._store and self._cg_store:
        from .search_router import UnifiedSearchRouter
        self._search_router = UnifiedSearchRouter(
            vector_store=self._vector_store,
            db=self._store.db,
            codegraph_store=self._cg_store,
        )
        log.info("UnifiedSearchRouter initialized")
except Exception as e:
    log.warning("UnifiedSearchRouter init failed: %s", e)
```

### Step 6: Register MCP Tools

Modify `memory_service/mcp_server.py`. Add new tools:

```python
# Unified search tool
@mcp.tool()
async def unified_search(
    query: str,
    mode: str = "hybrid",
    project_id: str = None,
    type_filter: str = None,
    top_k: int = 10,
) -> Dict:
    """Search across all backends (vector, keyword, web).

    Args:
        query: Search query text
        mode: 'vector', 'keyword', 'hybrid', or 'web'
        project_id: Filter by project (optional)
        type_filter: Filter by type ('code', 'spec', 'doc', 'review')
        top_k: Max results per backend
    """
    if not service._search_router:
        return {"error": "UnifiedSearchRouter not available"}

    filters = {}
    if project_id:
        filters["project_id"] = project_id
    if type_filter:
        filters["type"] = type_filter

    return service._search_router.search(
        query, mode=mode, top_k=top_k, **filters
    )
```

### Step 7: Start Services

```bash
# Start embedding server (if not already running)
systemctl --user start pplx-embedding.service
sleep 3
curl -s http://127.0.0.1:18099/health

# Start memory-service
systemctl --user start memory-service.service
sleep 3
curl -s http://127.0.0.1:18097/v1/memory/health
```

### Step 8: Run Verification Script

Create `scripts/verify_unified_db.py`:

```python
#!/usr/bin/env python3
"""End-to-end verification of unified database architecture."""
import sqlite3
import httpx
import sys
from pathlib import Path

def main():
    errors = []
    db = Path.home() / ".council-memory" / "council_core.db"
    cg = Path.home() / ".council-memory" / "codegraph.db"

    # Check 1: council_core.db exists
    if not db.exists():
        errors.append(f"council_core.db not found at {db}")
    else:
        print(f"[OK] council_core.db exists ({db.stat().st_size / 1024 / 1024:.1f} MB)")

    # Check 2: codegraph.db exists
    if not cg.exists():
        errors.append(f"codegraph.db not found at {cg}")
    else:
        print(f"[OK] codegraph.db exists ({cg.stat().st_size / 1024 / 1024:.1f} MB)")

    # Check 3-10: Table checks
    if db.exists():
        conn = sqlite3.connect(str(db))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        required_tables = [
            'projects', 'sessions', 'chat_messages', 'memories',
            'notes', 'documents', 'crew_members', 'model_endpoints',
            'scheduled_tasks', 'calendars', 'calendar_events',
            'knowledge_cards', 'research_reports', 'work_items', 'audit_trail',
            'pipelines', 'workflow_runs', 'artifacts', 'event_log',
            'session_diary', 'raw_session_memories', 'consolidation_cache',
        ]

        for table in required_tables:
            if table in tables:
                count = conn.execute(f'SELECT COUNT(*) FROM [{table}]').fetchone()[0]
                print(f"[OK] {table:30s} ({count} rows)")
            else:
                errors.append(f"Missing table: {table}")

        # Check FTS5 tables
        fts_tables = [t for t in tables if t.endswith('_fts')]
        print(f"[OK] FTS5 tables: {', '.join(fts_tables) or 'none'}")

        # Check project_id columns
        for table in ['session_diary', 'raw_session_memories', 'consolidation_cache', 'artifacts']:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            if 'project_id' in cols:
                print(f"[OK] {table} has project_id column")
            else:
                errors.append(f"{table} missing project_id column")

        # Check cg_* tables are NOT in council_core.db
        cg_tables = [t for t in tables if t.startswith('cg_')]
        if cg_tables:
            errors.append(f"cg_* tables still in council_core.db: {cg_tables}")
        else:
            print("[OK] No cg_* tables in council_core.db")

        conn.close()

    # Check codegraph.db
    if cg.exists():
        cg_conn = sqlite3.connect(str(cg))
        cg_tables = [r[0] for r in cg_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'cg_nodes' in cg_tables:
            count = cg_conn.execute('SELECT COUNT(*) FROM cg_nodes').fetchone()[0]
            print(f"[OK] cg_nodes in codegraph.db ({count} rows)")
        else:
            errors.append("cg_nodes not found in codegraph.db")
        cg_conn.close()

    # Check embedding server
    try:
        resp = httpx.get("http://127.0.0.1:18099/health", timeout=3.0)
        if resp.status_code == 200:
            print("[OK] Embedding server responding on :18099")
        else:
            errors.append(f"Embedding server returned {resp.status_code}")
    except Exception as e:
        errors.append(f"Embedding server unreachable: {e}")

    # Check memory service
    try:
        resp = httpx.get("http://127.0.0.1:18097/v1/memory/health", timeout=3.0)
        if resp.status_code == 200:
            print("[OK] Memory service responding on :18097")
        else:
            errors.append(f"Memory service returned {resp.status_code}")
    except Exception as e:
        errors.append(f"Memory service unreachable: {e}")

    # Summary
    print(f"\n{'='*60}")
    if errors:
        print(f"FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  [FAIL] {e}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)

if __name__ == '__main__':
    main()
```

Run it:
```bash
python3 scripts/verify_unified_db.py
```

### Step 9: ChromaDB Cleanup

```bash
# Remove ChromaDB imports from memory_service
grep -r "chroma" memory_service/ || echo "No ChromaDB imports found (clean)"

# Remove ChromaDB from Odysseus
grep -r "chroma" vendor/odysseus/src/memory_vector.py || echo "No ChromaDB in Odysseus (clean)"

# Remove ChromaDB from docker-compose (if exists)
grep -r "chroma" docker-compose*.yml 2>/dev/null || echo "No ChromaDB in docker-compose (clean)"
```

### Step 10: Remove Deprecated Tables

```bash
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.council-memory/council_core.db')
conn = sqlite3.connect(db)

# Drop pipelines_archive
conn.execute('DROP TABLE IF EXISTS pipelines_archive')
print('Dropped pipelines_archive')

# Drop translations (if work_items exists)
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
if 'work_items' in tables:
    conn.execute('DROP TABLE IF EXISTS translations')
    print('Dropped translations')
else:
    print('Skipping translations drop (work_items not yet created)')

conn.commit()
conn.close()
"
```

### Step 11: Model Cleanup

```bash
# Remove bge-m3 model (if exists)
rm -rf ~/.fastembed/bge-m3* 2>/dev/null && echo "Removed bge-m3" || echo "bge-m3 not found (already clean)"

# Remove all-MiniLM cache (if exists)
find ~/.cache -name "*MiniLM*" -type d -exec rm -rf {} + 2>/dev/null && echo "Removed all-MiniLM" || echo "all-MiniLM not found (already clean)"
```

### Step 12: Final Integration Test

```bash
# Test 1: Project creation
python3 -c "
from memory_service.store import RelationalStore
store = RelationalStore('~/.council-memory/council_core.db')
pid = store.get_or_create_project('test-project', 'Test Project')
pid2 = store.get_or_create_project('test-project', 'Different Name')
assert pid == pid2, f'Dedup failed: {pid} != {pid2}'
print(f'[OK] Project dedup works: {pid}')
"

# Test 2: Memory service health
curl -s http://127.0.0.1:18097/v1/memory/health | python3 -m json.tool

# Test 3: Embedding server
curl -s http://127.0.0.1:18099/v1/models | python3 -m json.tool

# Test 4: CodeGraph search
python3 -c "
from super_council.code_graph.store import CodeGraphStore
cg = CodeGraphStore('~/.council-memory/codegraph.db')
results = cg.search('RelationalStore')
print(f'[OK] CodeGraph search returned {len(results)} results')
"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/__init__.py` | Wire UnifiedVectorStore + UnifiedSearchRouter |
| Modify | `memory_service/config.py` | Default DB path → council_core.db |
| Modify | `memory_service/mcp_server.py` | Register unified_search tool |
| Create | `scripts/verify_unified_db.py` | End-to-end verification |

## Completion Gate

- [ ] `council_core.db` exists with all expected tables
- [ ] `codegraph.db` exists with cg_* tables extracted
- [ ] `projects` table has UNIQUE slug constraint
- [ ] `project_id` column on all memory tables
- [ ] All Odysseus tables exist with correct mappings
- [ ] Knowledge bridge tables exist
- [ ] Embedding server responds on `:18099`
- [ ] Memory service responds on `:18097`
- [ ] CodeGraph tools work with separate DB
- [ ] UnifiedVectorStore indexes and retrieves
- [ ] UnifiedSearchRouter returns fused results
- [ ] ChromaDB removed from all imports
- [ ] `pipelines_archive` table dropped
- [ ] `scripts/verify_unified_db.py` passes ALL checks (exit code 0)
- [ ] All existing tests pass (no regression)
- [ ] End-to-end flow: project creation → memory storage → search → recall

## Notes

This is the FINAL phase. If the verification script fails, diagnose and fix before marking complete. The system is NOT complete until `scripts/verify_unified_db.py` exits with code 0 and all checks show [OK].
