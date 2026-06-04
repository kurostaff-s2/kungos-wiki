# Handoff: Council Unified Database Implementation

**Source spec:** `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md` (v3)
**Architecture analysis:** `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
**Generated:** 04-06-2026
**Goal:** Implement the unified database architecture — projects table, Odysseus merge, unified search/vector, embedding server — enabling project-scoped knowledge management with hybrid search.

---

## Project Context

**Project root:** `/home/chief/Coding-Projects/7-council/super_council/`
**Reference docs:**
- `/home/chief/llm-wiki/super-council-docs/13-council-core-unified-db-draft.md`
- `/home/chief/llm-wiki/super-council-docs/13-council-core-architecture-analysis.md`
**Related codebases:**
- Odysseus: `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/`
- Embedding models: `/home/chief/models/embedding/pplx-embed-v1-0.6b-int8/`
**Key files for this task:**
- Migrations: `/home/chief/Coding-Projects/7-council/migrations/`
- Memory service: `/home/chief/Coding-Projects/7-council/super_council/memory_service/`
- Arc summarizer: `/home/chief/Coding-Projects/7-council/super_council/arc_summarizer/`
- Database: `~/.council-memory/pipelines.db` (current) → `~/.council-memory/council_core.db` (target)

---

## Execution Order

```
Phase 0 (CodeGraph extraction) ──┐
                                  ├──> Phase 1 (Projects + project_id) ──> Phase 3 (Odysseus merge) ──> Phase 5 (Knowledge bridge)
Phase 1A (Embedding server) ──────┘                                        │
                                                                           ├──> Phase 4 (UnifiedVectorStore) ──> Phase 6 (UnifiedSearchRouter)
Phase 2 (Migration infra) ─────────────────────────────────────────────────┘                                        │
                                                                                                                   │
                                                                                                                   ▼
                                                                                                            Phase 7 (Production Wiring)
```

**Parallelizable:** Phase 0 and Phase 1A can run simultaneously. Phase 2 can run alongside Phase 1.
**Sequential:** Phase 3 → Phase 5 → Phase 4 → Phase 6 → Phase 7 (strict dependency chain).

---

## Phase 0: Extract CodeGraph to Separate Database

**What:** Move `cg_*` tables from `pipelines.db` to `codegraph.db`. Reduces main DB from 193MB to ~40MB. Zero code logic changes — pure data move.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/09b_extract_codegraph.sql` | SQL script for extraction |
| Modify | `super_council/code_graph/store.py` | Accept separate DB path |
| Modify | `memory_service/__init__.py` | Pass `codegraph.db` path to CodeGraphStore |
| Modify | `memory_service/config.py` | Add `codegraph_db_path` config option |

**Steps:**

1. **Add config option** — `memory_service/config.py`:
   - Add `codegraph_db_path: Path` to `MemoryConfig` dataclass
   - Default: `Path.home() / ".council-memory" / "codegraph.db"`

2. **Parameterize CodeGraphStore** — `code_graph/store.py`:
   - Change `__init__(self, db_path)` to accept explicit `codegraph_db_path`
   - If path differs from main DB, open separate connection
   - If path is same, use existing connection (backward compat)

3. **Update MemoryService init** — `memory_service/__init__.py`:
   - Pass `config.codegraph_db_path` to `CodeGraphStore()` instead of `self._db_path`

4. **Write extraction script** — `migrations/09b_extract_codegraph.sql`:
   ```sql
   -- Run as Python script (ATTACH doesn't accept parameters)
   -- See Phase 0 step 5
   ```

5. **Write extraction script** — `scripts/extract_codegraph.py`:
   ```python
   import sqlite3, os
   src = os.path.expanduser('~/.council-memory/pipelines.db')
   dst = os.path.expanduser('~/.council-memory/codegraph.db')

   src_conn = sqlite3.connect(src)
   dst_conn = sqlite3.connect(dst)
   dst_conn.execute(f'ATTACH DATABASE "{src}" AS src')

   for table in ['cg_nodes', 'cg_edges', 'cg_files', 'cg_nodes_fts',
                 'cg_nodes_fts_data', 'cg_nodes_fts_idx',
                 'cg_nodes_fts_docsize', 'cg_nodes_fts_config']:
       dst_conn.execute(f'CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM src.{table} WHERE 0')
       dst_conn.execute(f'INSERT INTO {table} SELECT * FROM src.{table}')
   dst_conn.commit()
   dst_conn.execute('DETACH DATABASE src')

   # Drop from source
   for table in ['cg_nodes', 'cg_edges', 'cg_files', 'cg_nodes_fts',
                 'cg_nodes_fts_data', 'cg_nodes_fts_idx',
                 'cg_nodes_fts_docsize', 'cg_nodes_fts_config']:
       src_conn.execute(f'DROP TABLE IF EXISTS {table}')
   src_conn.commit()

   dst_conn.close()
   src_conn.close()
   print(f'CodeGraph extracted to {dst}')
   ```

6. **Run extraction** — `python3 scripts/extract_codegraph.py`

7. **Verify:**
   - `codegraph.db` exists with cg_* tables
   - `pipelines.db` no longer has cg_* tables
   - CodeGraphStore tools still work (search, callers, callees)

**Tests:**
- CodeGraphStore initializes with separate path
- `codegraph_search("RelationalStore")` returns results
- `codegraph_callers("get_context_slice")` returns results
- `pipelines.db` size reduced by ~150MB

**Dependencies:** None.

---

## Phase 1: Projects Table + project_id on Memory Tables

**What:** The FOUNDATION. Creates `projects` table with slug-based dedup, FTS5 index, and adds `project_id` columns to all knowledge-bearing tables. Enables project-scoped queries.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/10_projects.sql` | projects table + FTS5 + project_id columns |
| Modify | `memory_service/store.py` | `get_or_create_project()`, `_resolve_project()` |
| Modify | `memory_service/layer.py` | `upsert_summary(project_id=...)` with cascade |
| Modify | `memory_service/router.py` | Project-scoped queries |

**Steps:**

1. **Create migration** — `migrations/10_projects.sql`:
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

   -- FTS5 index on projects
   CREATE VIRTUAL TABLE IF NOT EXISTS projects_fts USING fts5(name, description, content='projects', content_rowid='rowid');

   -- Add project_id to session_diary
   ALTER TABLE session_diary ADD COLUMN project_id TEXT REFERENCES projects(id);

   -- Add project_id to raw_session_memories
   ALTER TABLE raw_session_memories ADD COLUMN project_id TEXT REFERENCES projects(id);

   -- Add project_id to consolidation_cache
   ALTER TABLE consolidation_cache ADD COLUMN project_id TEXT REFERENCES projects(id);

   -- Add project_id to artifacts
   ALTER TABLE artifacts ADD COLUMN project_id TEXT REFERENCES projects(id);

   -- Add project_id to memories (if exists)
   -- ALTER TABLE memories ADD COLUMN project_id TEXT REFERENCES projects(id);

   -- Indexes
   CREATE INDEX IF NOT EXISTS idx_session_diary_project ON session_diary(project_id);
   CREATE INDEX IF NOT EXISTS idx_raw_memories_project ON raw_session_memories(project_id);
   CREATE INDEX IF NOT EXISTS idx_consolidation_project ON consolidation_cache(project_id);
   CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
   ```

2. **Add store methods** — `memory_service/store.py`:
   ```python
   def get_or_create_project(self, slug: str, name: str, **metadata) -> str:
       """Return existing project ID or create new one. Never duplicates."""
       existing = self.db.execute(
           "SELECT id FROM projects WHERE slug = ?", (slug,)
       ).fetchone()
       if existing:
           return existing[0]

       new_id = uuid.uuid4().hex
       meta_json = json.dumps(metadata) if metadata else '{}'
       self.db.execute(
           "INSERT OR IGNORE INTO projects (id, slug, name, metadata) VALUES (?, ?, ?, ?)",
           (new_id, slug, name, meta_json)
       )
       winner = self.db.execute(
           "SELECT id FROM projects WHERE slug = ?", (slug,)
       ).fetchone()
       return winner[0]

   def resolve_project_for_text(self, text: str, session_id: str = None) -> Optional[str]:
       """4-channel project resolution cascade."""
       # Channel 1: Explicit (handled by caller)
       # Channel 2: Session → project
       if session_id:
           row = self.db.execute(
               "SELECT project_id FROM sessions WHERE id = ?", (session_id,)
           ).fetchone()
           if row and row[0]:
               return row[0]

       # Channel 3: File paths → codegraph
       import re
       paths = re.findall(r'\b[\w-]+\.(py|ts|js|md|rs|go)\b', text)
       if paths and self.cg_store:
           # Match paths against codegraph files
           for p in paths[:5]:
               row = self.cg_store.db.execute(
                   "SELECT project_id FROM cg_files WHERE path LIKE ? LIMIT 1",
                   (f'%{p}%',)
               ).fetchone()
               if row and row[0]:
                   return row[0]

       # Channel 4: FTS5 keyword match
       keywords = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', text.lower())
       if keywords:
           query = ' OR '.join(keywords[:10])
           row = self.db.execute(
               "SELECT id FROM projects_fts WHERE projects_fts MATCH ?", (query,)
           ).fetchone()
           if row:
               return row[0]

       return None  # Fallback: NULL + late resolution event
   ```

3. **Update MemoryLayer** — `memory_service/layer.py`:
   - Add `project_id` parameter to `ingest_artifact()`
   - Pass through to `store.ingest_artifact()`
   - Update `upsert_summary()` to resolve project via cascade

4. **Update ContextRouter** — `memory_service/router.py`:
   - Add `project_id` filter to `get_recent_events()`, `get_run_snapshot()`, `get_artifacts()`
   - Filter `session_diary` queries by `project_id`

5. **Verify:**
   - `projects` table exists with UNIQUE slug
   - `projects_fts` virtual table works
   - `get_or_create_project("test", "Test")` returns same UUID on repeated calls
   - Memory tables have `project_id` column
   - FTS5 search on projects works

**Tests:**
- `test_get_or_create_project_dedup()` — same slug → same UUID
- `test_resolve_project_channel2()` — session with project_id → resolved
- `test_resolve_project_channel4()` — text with project keywords → FTS5 match
- `test_project_id_on_memory_tables()` — ALTER TABLE applied

**Dependencies:** None.

---

## Phase 1A: Start pplx Embedding Server

**What:** Start the pplx-embed-v1 HTTP server on port `:18099`. Existing code, just not running.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py` | Verify port is `:18099` |
| Create | `~/.config/systemd/user/pplx-embedding.service` | systemd user service |
| Create | `memory_service/embedding_health.py` | Health check utility |

**Steps:**

1. **Verify server.py** — Check `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py`:
   - Port is `18099`
   - Endpoints: `/v1/embeddings`, `/v1/models`
   - Health endpoint: `/health`

2. **Create systemd service** — `~/.config/systemd/user/pplx-embedding.service`:
   ```ini
   [Unit]
   Description=pplx-embed-v1 Embedding Server
   After=network.target

   [Service]
   Type=simple
   ExecStart=/usr/bin/python3 /home/chief/models/embedding/pplx-embed-v1-0.6b-int8/server.py
   Restart=on-failure
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=default.target
   ```

3. **Start and enable:**
   ```bash
   systemctl --user daemon-reload
   systemctl --user start pplx-embedding.service
   systemctl --user enable pplx-embedding.service
   ```

4. **Verify:**
   ```bash
   curl -s http://127.0.0.1:18099/v1/models
   curl -s http://127.0.0.1:18099/health
   ```

5. **Create health check** — `memory_service/embedding_health.py`:
   ```python
   import httpx
   def check_embedding_server(url="http://127.0.0.1:18099"):
       try:
           resp = httpx.get(f"{url}/health", timeout=3.0)
           return resp.status_code == 200
       except Exception:
           return False
   ```

**Tests:**
- Server responds on `:18099`
- `/v1/models` returns model list
- `/v1/embeddings` accepts and returns embeddings
- Health check returns True

**Dependencies:** None. Runs in parallel with Phase 0.

---

## Phase 2: Migration Infrastructure

**What:** Prepare the migration infrastructure — migration ordering, rollback capability, config updates.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `scripts/migrate_council_core.py` | Main migration script |
| Modify | `memory_service/config.py` | Update `_DEFAULT_DB_PATH` to `council_core.db` |
| Create | `memory_service/migrations/README.md` | Migration order documentation |

**Steps:**

1. **Create migration script** — `scripts/migrate_council_core.py`:
   ```python
   """Migration script: pipelines.db → council_core.db

   Usage: python3 scripts/migrate_council_core.py --dry-run
          python3 scripts/migrate_council_core.py

   Steps:
   1. Stop memory-service
   2. Copy pipelines.db → council_core.db
   3. Run migrations/10_projects.sql through migrations/NN_latest.sql
   4. Update config to point to council_core.db
   5. Restart memory-service
   """
   import argparse
   import os
   import shutil
   import sqlite3
   import subprocess
   import sys
   from pathlib import Path

   SRC_DB = Path.home() / ".council-memory" / "pipelines.db"
   DST_DB = Path.home() / ".council-memory" / "council_core.db"
   MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

   def run_migrations(db_path: Path, dry_run: bool = False):
       """Run all migrations in order."""
       migration_files = sorted(
           f for f in os.listdir(MIGRATIONS_DIR)
           if f.endswith('.sql') and int(f.split('_')[0]) >= 10
       )

       if dry_run:
           print(f"[DRY RUN] Would run {len(migration_files)} migrations:")
           for f in migration_files:
               print(f"  - {f}")
           return

       conn = sqlite3.connect(str(db_path))
       for f in migration_files:
           print(f"Running migration: {f}")
           sql = Path(MIGRATIONS_DIR / f).read_text()
           try:
               conn.executescript(sql)
           except sqlite3.OperationalError as e:
               if 'duplicate' in str(e).lower() or 'already exists' in str(e).lower():
                   print(f"  Skipped (already applied): {f}")
               else:
                   raise
       conn.commit()
       conn.close()
       print(f"Migrations complete.")

   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument('--dry-run', action='store_true')
       args = parser.parse_args()

       if not SRC_DB.exists():
           print(f"ERROR: Source DB not found: {SRC_DB}")
           sys.exit(1)

       if args.dry_run:
           print(f"[DRY RUN] Would copy {SRC_DB} → {DST_DB}")
           run_migrations(DST_DB, dry_run=True)
           return

       # Step 1: Stop memory-service
       print("Stopping memory-service...")
       subprocess.run(['systemctl', '--user', 'stop', 'memory-service.service'], check=True)

       # Step 2: Backup
       backup = Path.home() / ".council-memory" / "pipelines.db.backup"
       shutil.copy2(SRC_DB, backup)
       print(f"Backup created: {backup}")

       # Step 3: Copy
       shutil.copy2(SRC_DB, DST_DB)
       print(f"Copied: {SRC_DB} → {DST_DB}")

       # Step 4: Run migrations
       run_migrations(DST_DB)

       # Step 5: Update config (handled by config.py default change)
       print("Migration complete. Update config-subsystem.json if needed.")
       print("Run: systemctl --user start memory-service.service")

   if __name__ == '__main__':
       main()
   ```

2. **Update config default** — `memory_service/config.py`:
   - Change `_DEFAULT_DB_PATH` from `pipelines.db` to `council_core.db`
   - Add deprecation warning if `pipelines.db` is used

3. **Run dry run** — `python3 scripts/migrate_council_core.py --dry-run`

**Tests:**
- Dry run lists all migrations correctly
- Migration script handles already-applied migrations gracefully
- Config default points to `council_core.db`

**Dependencies:** Phase 1 (migration SQL must exist).

---

## Phase 3: Odysseus Table Merge

**What:** Harmonize Odysseus tables into `council_core.db`. Rename columns, add FK constraints, add `project_id`.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/11_odysseus_sessions.sql` | sessions + chat_messages tables |
| Create | `migrations/11b_odysseus_memories.sql` | memories table (NEW) |
| Create | `migrations/11c_odysseus_notes.sql` | notes table |
| Create | `migrations/11d_odysseus_documents.sql` | documents table (NEW) |
| Create | `migrations/11e_odysseus_agents.sql` | crew_members + model_endpoints |
| Create | `migrations/11f_odysseus_tasks.sql` | scheduled_tasks + task_runs (NEW) |
| Create | `migrations/11g_odysseus_calendar.sql` | calendars + calendar_events (NEW) |
| Create | `scripts/migrate_odysseus_data.py` | Data migration from app.db |

**Steps:**

1. **Create session tables** — `migrations/11_odysseus_sessions.sql`:
   ```sql
   CREATE TABLE IF NOT EXISTS sessions (
       id TEXT PRIMARY KEY,
       name TEXT NOT NULL,
       endpoint_url TEXT NOT NULL,
       model TEXT NOT NULL,
       owner_id TEXT,
       project_id TEXT REFERENCES projects(id),
       has_rag INTEGER DEFAULT 0,
       is_archived INTEGER DEFAULT 0,
       folder TEXT,
       headers TEXT,
       last_accessed TEXT,
       last_message_at TEXT,
       is_important INTEGER DEFAULT 0,
       message_count INTEGER DEFAULT 0,
       total_input_tokens INTEGER DEFAULT 0,
       total_output_tokens INTEGER DEFAULT 0,
       mode TEXT,
       metadata TEXT DEFAULT '{}',
       created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now', '+5 hours', '+30 minutes')),
       updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now', '+5 hours', '+30 minutes')),
       expires_at INTEGER
   );

   CREATE TABLE IF NOT EXISTS chat_messages (
       id TEXT PRIMARY KEY,
       session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
       role TEXT NOT NULL,
       content TEXT NOT NULL,
       metadata TEXT,
       created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now', '+5 hours', '+30 minutes'))
   );

   CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
   CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
   ```

2. **Create memories table** — `migrations/11b_odysseus_memories.sql`:
   ```sql
   CREATE TABLE IF NOT EXISTS memories (
       id TEXT PRIMARY KEY,
       text TEXT NOT NULL,
       category TEXT,
       source TEXT,
       session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
       project_id TEXT REFERENCES projects(id),
       confidence REAL,
       tags TEXT DEFAULT '[]',
       related_memory_ids TEXT DEFAULT '[]',
       tier TEXT,
       created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+05:30', 'now', '+5 hours', '+30 minutes')),
       expires_at INTEGER,
       is_indexed INTEGER DEFAULT 0
   );

   CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
   CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
   ```

3. **Create notes table** — `migrations/11c_odysseus_notes.sql` (per draft §4.2)

4. **Create documents table** — `migrations/11d_odysseus_documents.sql` (per draft §4.2)

5. **Create agent config tables** — `migrations/11e_odysseus_agents.sql` (crew_members, model_endpoints)

6. **Create task scheduling tables** — `migrations/11f_odysseus_tasks.sql` (scheduled_tasks, task_runs)

7. **Create calendar tables** — `migrations/11g_odysseus_calendar.sql` (calendars, calendar_events)

8. **Create data migration script** — `scripts/migrate_odysseus_data.py`:
   ```python
   """Migrate data from Odysseus app.db to council_core.db.

   Column mappings:
   - sessions.owner → sessions.owner_id
   - sessions.rag → sessions.has_rag
   - sessions.archived → sessions.is_archived
   - memories.owner → (dropped, use sessions.owner_id via FK)
   """
   import sqlite3
   from pathlib import Path

   SRC = Path.home() / "Coding-Projects/7-council/super_council/vendor/odysseus/data/app.db"
   DST = Path.home() / ".council-memory" / "council_core.db"

   def migrate_sessions():
       src = sqlite3.connect(str(SRC))
       dst = sqlite3.connect(str(DST))
       src.row_factory = sqlite3.Row
       dst.row_factory = sqlite3.Row

       rows = src.execute("SELECT * FROM sessions").fetchall()
       for row in rows:
           dst.execute("""
               INSERT OR IGNORE INTO sessions (
                   id, name, endpoint_url, model, owner_id, has_rag, is_archived,
                   folder, headers, last_accessed, last_message_at, is_important,
                   message_count, total_input_tokens, total_output_tokens, mode,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           """, (
               row['id'], row['name'], row['endpoint_url'], row['model'],
               row['owner'],  # owner → owner_id
               int(row['rag'] or False),  # rag → has_rag
               int(row['archived'] or False),  # archived → is_archived
               row['folder'], row['headers'], row['last_accessed'],
               row['last_message_at'], int(row['is_important'] or False),
               row['message_count'], row['total_input_tokens'],
               row['total_output_tokens'], row['mode'],
               row['created_at'], row['updated_at']
           ))

       dst.commit()
       src.close()
       dst.close()
       print(f"Migrated {len(rows)} sessions")

   if __name__ == '__main__':
       migrate_sessions()
   ```

9. **Run migration** — `python3 scripts/migrate_odysseus_data.py`

**Tests:**
- All Odysseus tables exist in `council_core.db`
- Column mappings are correct (owner → owner_id, rag → has_rag, etc.)
- FK constraints work (INSERT with invalid session_id fails)
- Data migrated correctly (row counts match)

**Dependencies:** Phase 1 (projects table must exist for FK references).

---

## Phase 4: Unified Vector Store

**What:** Single Milvus-lite collection replacing ChromaDB + MemIndex fragmentation. Source tagging, dedup, filtering.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `memory_service/vector_store.py` | UnifiedVectorStore class |
| Modify | `memory_service/index.py` | Replace MemIndex with UnifiedVectorStore |
| Modify | `memory_service/memsearch_wrapper.py` | Route through UnifiedVectorStore |
| Modify | `vendor/odysseus/src/memory_vector.py` | Replace ChromaDB with HTTP call |

**Steps:**

1. **Create UnifiedVectorStore** — `memory_service/vector_store.py`:
   ```python
   class UnifiedVectorStore:
       COLLECTION_NAME = "unified_vectors"
       SOURCES = ("memory", "knowledge_card", "document", "note", "artifact", "session_diary")

       def __init__(self, embedding_url: str = "http://127.0.0.1:18099"):
           self._embed_url = embedding_url
           self._client = httpx.Client(timeout=httpx.Timeout(connect=3.0, read=30.0))
           self._milvus = None  # Lazy init

       def _embed(self, texts: List[str]) -> List[List[float]]:
           resp = self._client.post(f"{self._embed_url}/v1/embeddings", json={
               "input": texts, "model": "pplx-embed-v1"
           })
           resp.raise_for_status()
           data = resp.json()
           return [e["embedding"] for e in data["data"]]

       def index(self, source: str, source_id: str, text: str, metadata: Dict = None):
           embeddings = self._embed([text])
           # Upsert into Milvus-lite collection
           ...

       def search(self, query: str, top_k: int = 10, filters: Dict = None) -> List[Dict]:
           embeddings = self._embed([query])
           # Query Milvus-lite with filter
           ...

       def dedup_check(self, text: str, threshold: float = 0.92) -> Optional[str]:
           embeddings = self._embed([text])
           # Query top-1, check distance
           ...
   ```

2. **Replace MemIndex** — `memory_service/index.py`:
   - Change `MemIndex` to use `UnifiedVectorStore` internally
   - Maintain backward-compatible API

3. **Update Odysseus** — `vendor/odysseus/src/memory_vector.py`:
   - Replace ChromaDB collection with HTTP call to `UnifiedVectorStore`
   - Or: point at Milvus-lite directly (simpler, avoids HTTP proxy)

4. **Verify:**
   - `UnifiedVectorStore` indexes and retrieves documents
   - `dedup_check` returns existing ID for near-duplicate text
   - Source filtering works (`source='memory'` returns only memories)

**Tests:**
- `test_index_and_search()` — index a doc, search for it, find it
- `test_dedup_check()` — near-duplicate text returns existing ID
- `test_source_filtering()` — filter by source returns correct subset
- `test_embedding_server_fallback()` — graceful degradation if server down

**Dependencies:** Phase 1A (embedding server must be running).

---

## Phase 5: Knowledge Bridge Tables

**What:** Create tables for knowledge cards, research reports, work items, and audit trail.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `migrations/12_knowledge_bridge.sql` | All bridge tables |

**Steps:**

1. **Create migration** — `migrations/12_knowledge_bridge.sql`:
   - `knowledge_cards` table (per draft §4.3)
   - `research_reports` table (per draft §4.3)
   - `work_items` table (per draft §4.3)
   - `audit_trail` table (per draft §4.3)
   - FTS5 indexes: `knowledge_cards_fts`, `documents_fts`, `notes_fts`

2. **Verify:**
   - All tables exist with correct FK constraints
   - FTS5 indexes work
   - INSERT with invalid FK fails

**Tests:**
- `test_knowledge_card_create()` — INSERT with valid project_id succeeds
- `test_work_item_phase_transition()` — phase history appends correctly
- `test_audit_trail_ttl()` — expires_at is set correctly
- `test_fts5_knowledge_cards()` — FTS5 search returns results

**Dependencies:** Phase 3 (sessions table for FK references).

---

## Phase 6: Unified Search Router

**What:** Single query interface for ALL search capabilities. RRF fusion of vector + keyword results.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Create | `memory_service/search_router.py` | UnifiedSearchRouter class |
| Modify | `memory_service/mcp_server.py` | Add `unified_search` tool |
| Modify | `memory_service/__init__.py` | Initialize search router |

**Steps:**

1. **Create search router** — `memory_service/search_router.py`:
   ```python
   class UnifiedSearchRouter:
       def __init__(self, vector_store, db, codegraph_store):
           self._vector = vector_store
           self._db = db
           self._cg = codegraph_store

       def search(self, query: str, mode: str = "hybrid", **filters) -> Dict:
           results = {"query": query, "mode": mode, "backends": {}}

           if mode in ("vector", "hybrid"):
               results["backends"]["vector"] = self._search_vector(query, filters)

           if mode in ("keyword", "hybrid"):
               results["backends"]["keyword"] = self._search_fts5(query, filters)

           if mode == "web":
               results["backends"]["web"] = self._search_web(query)

           if mode == "hybrid":
               results["fused"] = self._rrf_fuse(results["backends"])

           return results

       def _rrf_fuse(self, backends: Dict) -> List[Dict]:
           k = 61
           scores: Dict[str, float] = {}
           for backend_name, hits in backends.items():
               if not hits:
                   continue
               for rank, hit in enumerate(hits, 1):
                   sid = f"{backend_name}:{hit['source_id']}"
                   scores[sid] = scores.get(sid, 0) + 1 / (k + rank)

           seen = set()
           fused = []
           for sid, score in sorted(scores.items(), key=lambda x: -x[1]):
               _, source_id = sid.split(":", 1)
               if source_id not in seen:
                   fused.append({"source_id": source_id, "rrf_score": round(score, 4)})
                   seen.add(source_id)
           return fused[:10]
   ```

2. **Register as MCP tool** — `memory_service/mcp_server.py`:
   - Add `unified_search` tool
   - Parameters: `query`, `mode`, `project_id`, `type_filter`

3. **Wire into MemoryService** — `memory_service/__init__.py`:
   - Initialize `UnifiedSearchRouter` with vector_store, db, cg_store
   - Expose via `self._search_router`

4. **Verify:**
   - `router.search("how does RelationalStore work", mode="hybrid")` returns fused results
   - Vector and keyword backends both contribute
   - RRF fusion deduplicates by source_id

**Tests:**
- `test_hybrid_search()` — returns results from both vector + keyword
- `test_rrf_fusion()` — correctly combines ranks
- `test_web_search()` — SearXNG pass-through works
- `test_project_filter()` — project_id filter applied correctly

**Dependencies:** Phase 4 (UnifiedVectorStore), Phase 1 (projects for FTS5).

---

## Phase 7: Production Wiring

**What:** Wire all components into a running system. Execute migration. Verify full flow end-to-end.

**Files:**
| Action | File | Purpose |
|--------|------|---------|
| Modify | `memory_service/__init__.py` | Wire all new components |
| Modify | `memory_service/config.py` | Final config defaults |
| Modify | `memory_service/mcp_server.py` | Register new tools |
| Create | `scripts/verify_unified_db.py` | End-to-end verification script |

**Steps:**

1. **Execute migration** — `python3 scripts/migrate_council_core.py`:
   - Stop memory-service
   - Copy pipelines.db → council_core.db
   - Run migrations 10 through 12
   - Start memory-service

2. **Execute data migration** — `python3 scripts/migrate_odysseus_data.py`:
   - Migrate sessions, memories, notes, documents from app.db

3. **Execute CodeGraph extraction** — `python3 scripts/extract_codegraph.py`:
   - Move cg_* tables to codegraph.db

4. **Start embedding server** — `systemctl --user start pplx-embedding.service`

5. **Start memory-service** — `systemctl --user start memory-service.service`

6. **Run verification script** — `scripts/verify_unified_db.py`:
   ```python
   """End-to-end verification of unified database architecture."""
   import sqlite3
   import httpx
   from pathlib import Path

   def verify():
       db = Path.home() / ".council-memory" / "council_core.db"
       cg = Path.home() / ".council-memory" / "codegraph.db"

       # Check 1: council_core.db exists
       assert db.exists(), f"council_core.db not found at {db}"

       # Check 2: codegraph.db exists
       assert cg.exists(), f"codegraph.db not found at {cg}"

       # Check 3: projects table exists
       conn = sqlite3.connect(str(db))
       tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
       assert 'projects' in tables, "projects table missing"
       assert 'projects_fts' in tables, "projects_fts table missing"

       # Check 4: project_id on memory tables
       for table in ['session_diary', 'raw_session_memories', 'consolidation_cache', 'artifacts']:
           cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
           assert 'project_id' in cols, f"{table} missing project_id column"

       # Check 5: Odysseus tables exist
       for table in ['sessions', 'chat_messages', 'memories', 'notes', 'documents',
                      'crew_members', 'model_endpoints', 'scheduled_tasks', 'calendars']:
           assert table in tables, f"{table} table missing"

       # Check 6: Knowledge bridge tables
       for table in ['knowledge_cards', 'research_reports', 'work_items', 'audit_trail']:
           assert table in tables, f"{table} table missing"

       # Check 7: Embedding server
       resp = httpx.get("http://127.0.0.1:18099/health", timeout=3.0)
       assert resp.status_code == 200, "Embedding server not responding"

       # Check 8: Memory service health
       resp = httpx.get("http://127.0.0.1:18097/v1/memory/health", timeout=3.0)
       assert resp.status_code == 200, "Memory service not responding"

       # Check 9: CodeGraph not in council_core.db
       assert 'cg_nodes' not in tables, "cg_nodes still in council_core.db"

       # Check 10: CodeGraph in codegraph.db
       cg_conn = sqlite3.connect(str(cg))
       cg_tables = [r[0] for r in cg_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
       assert 'cg_nodes' in cg_tables, "cg_nodes not in codegraph.db"

       conn.close()
       cg_conn.close()
       print("All checks passed!")

   if __name__ == '__main__':
       verify()
   ```

7. **Verify ChromaDB removed:**
   - No ChromaDB imports in memory_service
   - No ChromaDB in docker-compose
   - Odysseus `memory_vector.py` uses UnifiedVectorStore

8. **Verify cleanup:**
   - `pipelines_archive` table dropped
   - `translations` table dropped (or migrated to work_items)
   - bge-m3 model files deleted
   - all-MiniLM cache deleted

**Post-Wiring Tests (GATE — must pass before marking complete):**
- [ ] `council_core.db` exists and has all expected tables
- [ ] `codegraph.db` exists with cg_* tables
- [ ] `projects` table has UNIQUE slug constraint
- [ ] `project_id` column exists on session_diary, raw_session_memories, consolidation_cache, artifacts
- [ ] All Odysseus tables exist with correct column mappings
- [ ] Knowledge bridge tables exist (knowledge_cards, research_reports, work_items, audit_trail)
- [ ] Embedding server responds on `:18099`
- [ ] Memory service responds on `:18097`
- [ ] CodeGraph tools work (search, callers, callees)
- [ ] UnifiedVectorStore indexes and retrieves
- [ ] UnifiedSearchRouter returns fused results
- [ ] ChromaDB is removed from all imports
- [ ] `pipelines_archive` table is dropped
- [ ] All existing tests still pass (no regression)
- [ ] `scripts/verify_unified_db.py` passes all checks

**Dependencies:** All previous phases.

---

## Constraints

- **SQLite only** — No PostgreSQL. Period.
- **One embedding model** — `pplx-embed-v1-0.6b-int8`. No bge-m3, no all-MiniLM.
- **One vector store** — Milvus-lite. No ChromaDB.
- **Migration is idempotent** — `CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE`.
- **Migration is dependency-ordered** — FK-referenced tables created before referencing tables.
- **No data loss** — `pipelines.db` kept as backup until full verification.
- **WAL mode + FK enforcement** — Preserved from existing `RelationalStore`.
- **No users table** — Ownership is username-based (TEXT, not FK).
- **IST timezone** — All timestamps use IST (+05:30) consistently.
- **FTS5 for keyword search** — No LIKE queries for search.

---

## Caveats & Uncertainty

- **Odysseus SQLAlchemy compatibility:** Odysseus uses SQLAlchemy with VARCHAR/DATETIME. SQLite maps these to TEXT transparently. Test each module independently.
- **Concurrent access:** Odysseus and memory-service may write simultaneously. WAL mode handles reads; write contention needs testing. `busy_timeout = 5s` + retry logic.
- **pplx model size:** 688 MB ONNX INT8. CPU inference is viable but slower than GPU. Monitor latency.
- **SearXNG availability:** External HTTP dependency. If `:8080` is down, web_search fails. Existing fallback in Odysseus LLM core.
- **DB size growth:** `council_core.db` will grow with chat messages, memories, research reports. TTL-based expiry + vacuum on idle.
- **Migration timing:** Must stop memory-service during migration. Plan for ~5 minute downtime.

---

## Success Criteria

- [ ] `council_core.db` replaces `pipelines.db` as the canonical database
- [ ] `codegraph.db` is a separate file with cg_* tables extracted
- [ ] `projects` table exists with slug-based dedup and FTS5 index
- [ ] `project_id` column exists on all knowledge-bearing tables
- [ ] All Odysseus tables merged with correct column mappings
- [ ] Knowledge bridge tables exist (knowledge_cards, research_reports, work_items, audit_trail)
- [ ] pplx-embed-v1 server running on `:18099`
- [ ] UnifiedVectorStore replaces ChromaDB + MemIndex
- [ ] UnifiedSearchRouter provides hybrid search with RRF fusion
- [ ] ChromaDB removed from all code and configurations
- [ ] `pipelines_archive` table dropped (soft-delete pattern)
- [ ] Memory service starts and passes health check
- [ ] All existing tests pass (no regression)
- [ ] `scripts/verify_unified_db.py` passes all checks
- [ ] End-to-end flow verified: memory extraction → storage → recall → consolidation → search
