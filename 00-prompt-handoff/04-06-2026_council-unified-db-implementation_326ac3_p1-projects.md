# Phase 1: Projects Table + project_id on Memory Tables

**Parent plan:** `04-06-2026_council-unified-db-implementation_326ac3.md`
**Phase:** 1 of 7
**Dependencies:** None (foundational — build first)
**Estimated effort:** ~60 min

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/`
**Key files for this phase:**
- `migrations/10_projects.sql` (CREATE)
- `memory_service/store.py` (MODIFY)
- `memory_service/layer.py` (MODIFY)
- `memory_service/router.py` (MODIFY)

## What This Phase Delivers

The `projects` table — the single most impactful missing piece. Every piece of knowledge in the system needs to belong to a project. Without this, you cannot scope queries, deduplicate work, or resolve orphaned memories. This phase creates the table, the FTS5 index, the resolution cascade, and adds `project_id` columns to all knowledge-bearing tables.

## Pre-Flight Checklist

- [ ] `pipelines.db` is accessible at `~/.council-memory/pipelines.db`
- [ ] Memory service is running (or can be restarted)
- [ ] No other migrations are pending

## Implementation Steps

### Step 1: Create Migration SQL

Create `migrations/10_projects.sql`:

```sql
-- Projects table (FK anchor — must be created first)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    priority TEXT,
    tags TEXT DEFAULT '[]',
    owner_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_by TEXT,
    updated_by TEXT,
    revision INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now', '+5 hours', '+30 minutes')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now', '+5 hours', '+30 minutes'))
);

-- FTS5 virtual table for keyword search
CREATE VIRTUAL TABLE IF NOT EXISTS projects_fts USING fts5(name, description, content='projects', content_rowid='rowid');

-- Add project_id to existing knowledge tables
ALTER TABLE session_diary ADD COLUMN project_id TEXT REFERENCES projects(id);
ALTER TABLE raw_session_memories ADD COLUMN project_id TEXT REFERENCES projects(id);
ALTER TABLE consolidation_cache ADD COLUMN project_id TEXT REFERENCES projects(id);
ALTER TABLE artifacts ADD COLUMN project_id TEXT REFERENCES projects(id);

-- Indexes for project-scoped queries
CREATE INDEX IF NOT EXISTS idx_session_diary_project ON session_diary(project_id);
CREATE INDEX IF NOT EXISTS idx_raw_memories_project ON raw_session_memories(project_id);
CREATE INDEX IF NOT EXISTS idx_consolidation_project ON consolidation_cache(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug);
```

### Step 2: Apply Migration

```bash
cd /home/chief/Coding-Projects/7-council/
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.council-memory/pipelines.db')
conn = sqlite3.connect(db)
sql = open('migrations/10_projects.sql').read()
conn.executescript(sql)
conn.commit()
conn.close()
print('Migration applied')
"
```

### Step 3: Add Store Methods

Modify `memory_service/store.py`. Add after `_sync_phase_registry()`:

```python
def get_or_create_project(self, slug: str, name: str, **metadata) -> str:
    """Return existing project ID or create new one. Never duplicates.

    slug is the human-stable identifier. 'mcp-review' always -> same UUID.
    """
    # Step 1: Look up by slug
    existing = self.db.execute(
        "SELECT id FROM projects WHERE slug = ?", (slug,)
    ).fetchone()
    if existing:
        return existing[0]

    # Step 2: INSERT OR IGNORE (race-condition safe)
    import uuid
    new_id = uuid.uuid4().hex
    import json
    meta_json = json.dumps(metadata) if metadata else '{}'
    self.db.execute(
        "INSERT OR IGNORE INTO projects (id, slug, name, metadata) VALUES (?, ?, ?, ?)",
        (new_id, slug, name, meta_json)
    )

    # Step 3: Return the winner
    winner = self.db.execute(
        "SELECT id FROM projects WHERE slug = ?", (slug,)
    ).fetchone()
    return winner[0]

def resolve_project_for_text(self, text: str, session_id: str = None) -> Optional[str]:
    """4-channel project resolution cascade.

    Channel 1: Explicit project_id (handled by caller)
    Channel 2: Active session -> project
    Channel 3: File paths in text -> codegraph -> project slug
    Channel 4: FTS5 keyword match on projects
    Fallback: None (caller inserts with project_id=NULL)
    """
    import re
    import json

    # Channel 2: Session -> project
    if session_id:
        row = self.db.execute(
            "SELECT project_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row and row[0]:
            return row[0]

    # Channel 3: File paths -> codegraph
    paths = re.findall(r'\b[\w-]+\.(py|ts|js|md|rs|go)\b', text)
    if paths and self._cg_store:
        for p in paths[:5]:
            try:
                row = self._cg_store.db.execute(
                    "SELECT DISTINCT substr(path, 1, 50) FROM cg_files WHERE path LIKE ? LIMIT 1",
                    (f'%{p}%',)
                ).fetchone()
                if row:
                    # Derive project from path (heuristic: first dir component)
                    # TODO: Map to actual project slug
                    pass
            except Exception:
                pass

    # Channel 4: FTS5 keyword match
    keywords = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', text.lower())
    if keywords:
        query = ' OR '.join(keywords[:10])
        try:
            row = self.db.execute(
                "SELECT id FROM projects_fts WHERE projects_fts MATCH ?", (query,)
            ).fetchone()
            if row:
                return row[0]
        except Exception:
            pass

    return None
```

### Step 4: Update MemoryLayer

Modify `memory_service/layer.py`. Update `ingest_artifact()` to accept `project_id`:

```python
def ingest_artifact(
    self,
    run_id: str,
    phase: str,
    key: str,
    content: str,
    content_type: str = "text/plain",
    project_id: str = None,
) -> str:
    """Store an artifact with metadata."""
    import uuid
    artifact_id = str(uuid.uuid4())
    now = datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S.%f+05:30")

    # Check if project_id column exists (migration may not have run yet)
    cols = [r[1] for r in self._db.execute('PRAGMA table_info(artifacts)').fetchall()]
    if 'project_id' in cols:
        self._db.execute(
            "INSERT OR REPLACE INTO artifacts "
            "(artifact_id, run_id, phase, key, content, content_type, project_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (artifact_id, run_id, phase, key, content, content_type, project_id, now),
        )
    else:
        self._db.execute(
            "INSERT OR REPLACE INTO artifacts "
            "(artifact_id, run_id, phase, key, content, content_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (artifact_id, run_id, phase, key, content, content_type, now),
        )
    self._db.commit()
    return artifact_id
```

### Step 5: Update ContextRouter

Modify `memory_service/router.py`. Add `project_id` filter to existing methods:

```python
def get_recent_events(self, run_id: str, limit: int = 10, project_id: str = None) -> List[Dict[str, Any]]:
    """Return last N events for a run, optionally filtered by project."""
    conditions = ["run_id = ?"]
    params = [run_id]

    if project_id:
        # Join with workflow_runs to filter by project
        conditions.append("project_id = ?")
        params.append(project_id)

    rows = self._db.execute(
        f"SELECT event_id, event_type, severity, message, metadata, occurred_at "
        f"FROM event_log WHERE run_id IN ("
        f"  SELECT run_id FROM workflow_runs WHERE {' AND '.join(conditions)}"
        f") ORDER BY occurred_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    # ... rest of method unchanged
```

### Step 6: Seed Initial Projects

```bash
python3 -c "
import sqlite3, os, uuid
db = os.path.expanduser('~/.council-memory/pipelines.db')
conn = sqlite3.connect(db)

# Seed from existing pipelines
existing_projects = conn.execute('SELECT DISTINCT project_id FROM pipelines WHERE project_id != \"\"').fetchall()
for (pid,) in existing_projects:
    slug = pid.lower().replace(' ', '-').replace('_', '-')
    conn.execute('''
        INSERT OR IGNORE INTO projects (id, slug, name) VALUES (?, ?, ?)
    ''', (pid, slug, pid))

conn.commit()
print(f'Seeded {len(existing_projects)} projects from existing pipelines')
conn.close()
"
```

## Files to Create/Modify

| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/10_projects.sql` | Projects table + FTS5 + project_id columns |
| Modify | `memory_service/store.py` | `get_or_create_project()`, `resolve_project_for_text()` |
| Modify | `memory_service/layer.py` | `ingest_artifact(project_id=...)` |
| Modify | `memory_service/router.py` | `project_id` filter on queries |

## Phase-Specific Tests

1. **test_get_or_create_project_dedup:** Call `get_or_create_project("test-slug", "Test")` twice → same UUID both times.
2. **test_slug_unique:** INSERT with duplicate slug → ignored (INSERT OR IGNORE).
3. **test_project_id_on_tables:** `PRAGMA table_info(session_diary)` includes `project_id`.
4. **test_fts5_search:** INSERT project with name "mcp-review", search `projects_fts MATCH 'mcp'` → returns row.
5. **test_resolve_channel4:** Text containing project keywords → FTS5 match returns project_id.

## Completion Gate

- [ ] `migrations/10_projects.sql` created and applied
- [ ] `projects` table exists with UNIQUE slug
- [ ] `projects_fts` virtual table exists
- [ ] `project_id` column exists on session_diary, raw_session_memories, consolidation_cache, artifacts
- [ ] `get_or_create_project()` deduplicates by slug
- [ ] `resolve_project_for_text()` returns project_id for known projects
- [ ] All phase-specific tests pass
- [ ] No regression in existing tests

## Notes for Next Phase

- Phase 2 (Migration Infrastructure) expects `migrations/10_projects.sql` to exist
- Phase 3 (Odysseus merge) expects `projects` table for FK references
- The `resolve_project_for_text()` Channel 3 (file paths → codegraph) is a heuristic stub — refine after Phase 0 (CodeGraph extraction) provides better path resolution
