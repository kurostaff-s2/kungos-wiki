# Execution Prompt: DB Split + Schema Simplification + Review Streamlining

**Source spec:** `~/llm-wiki/00-prompt-handoff/migration-plan-2026-06-01.md`
**Generated:** 01-06-2026 by chair-agent
**Goal:** Split codegraph into its own DB, simplify enum tables to CHECK constraints, rename memory tables for clarity, streamline review lifecycle, unify work tracking — all while pipelines.db is empty from the codegraph ID collision fix.

---

## Context

pipelines.db was wiped during the codegraph ID collision fix (commit 91c85bf). Only 4 rows survived (2 raw_session_memories, 2 session_diary). This is the perfect window for schema changes since:
- No production data to migrate
- Codegraph prefix fix is already committed and verified (18,856 nodes across 9 projects)
- All consumers are stopped and can be restarted with new schema

---

### Phase 1: CodeGraph DB Split

**What:** Move cg_nodes, cg_edges, cg_files, cg_nodes_fts from pipelines.db to a new codegraph.db. Update all config and code to point to the new DB.

**Files to Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/config.py` | Add `codegraph_db_path` field to MemoryConfig |
| Modify | `super_council/code_graph/sync.py` | Default DB → `codegraph.db`, update all paths |
| Modify | `super_council/code_graph/sync-all.py` | DB_PATH → `~/.council-memory/codegraph.db` |
| Modify | `super_council/code_graph/store.py` | Accept separate `codegraph_db_path`, ATTACH pipelines.db for JOIN tools |
| Modify | `super_council/code_graph/tools.py` | JOIN tools (`similar_fixes`, `related_reviews`) use ATTACH'd pipelines reference |
| Modify | `super_council/code_graph/watch.py` | Default DB → `codegraph.db` |
| Modify | `~/.pi/agent/extensions/codegraph-mcp/index.ts` | DB_PATH → `codegraph.db`, CODEGRAPH_DB_PATH → `codegraph.db` |
| Modify | `config-subsystem.json` | Add `codegraph_db_path` under `memory` section |

**Steps:**

1. Copy cg_* tables from pipelines.db to new codegraph.db:
   ```bash
   python3 -c "
   import sqlite3, shutil
   src = sqlite3.connect('/home/chief/.council-memory/pipelines.db')
   dst = sqlite3.connect('/home/chief/.council-memory/codegraph.db')
   dst.execute('PRAGMA journal_mode=WAL')
   dst.execute('PRAGMA foreign_keys=ON')
   # Copy tables
   for table in ['cg_nodes', 'cg_edges', 'cg_files']:
       rows = src.execute(f'SELECT * FROM {table}').fetchall()
       cols = [d[0] for d in src.execute(f'SELECT * FROM {table} LIMIT 0').description]
       placeholders = ','.join(['?']*len(cols))
       col_names = ','.join(cols)
       dst.execute(f'CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM {table} LIMIT 0')
       # Read schema from source
       schema = src.execute(f'SELECT sql FROM sqlite_master WHERE name=\"{table}\"').fetchone()[0]
       dst.execute(schema)
       dst.executemany(f'INSERT INTO {table} VALUES ({placeholders})', rows)
   dst.commit()
   print(f'Copied: {dst.execute(\"SELECT COUNT(*) FROM cg_nodes\").fetchone()[0]} nodes, {dst.execute(\"SELECT COUNT(*) FROM cg_edges\").fetchone()[0]} edges')
   src.close(); dst.close()
   "
   ```

2. Recreate FTS5 in codegraph.db:
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('/home/chief/.council-memory/codegraph.db')
   conn.execute('DROP TABLE IF EXISTS cg_nodes_fts')
   conn.execute('''CREATE VIRTUAL TABLE cg_nodes_fts USING fts5(
       name, qualified_name, docstring, signature,
       content='cg_nodes', content_rowid='rowid'
   )''')
   conn.execute('''INSERT INTO cg_nodes_fts(rowid, name, qualified_name, docstring, signature)
       SELECT rowid, name, qualified_name, docstring, signature FROM cg_nodes''')
   # Triggers
   for trig in ['cg_nodes_ai', 'cg_nodes_ad', 'cg_nodes_au']:
       sql = conn.execute(f'SELECT sql FROM sqlite_master WHERE type=\"trigger\" AND name=\"{trig}\"').fetchone()
       if sql: conn.execute(sql[0])
   # Views
   conn.execute('CREATE VIEW IF NOT EXISTS nodes AS SELECT * FROM cg_nodes')
   conn.execute('CREATE VIEW IF NOT EXISTS edges AS SELECT source, target, kind, metadata, line, col, provenance FROM cg_edges')
   conn.execute('CREATE VIEW IF NOT EXISTS files AS SELECT * FROM cg_files')
   conn.commit()
   print(f'FTS5: {conn.execute(\"SELECT COUNT(*) FROM cg_nodes_fts\").fetchone()[0]} rows')
   conn.close()
   "
   ```

3. Drop cg_* tables from pipelines.db:
   ```sql
   DROP TABLE IF EXISTS cg_nodes_fts;
   DROP TRIGGER IF EXISTS cg_nodes_ai; DROP TRIGGER IF EXISTS cg_nodes_ad; DROP TRIGGER IF EXISTS cg_nodes_au;
   DROP TABLE IF EXISTS cg_nodes; DROP TABLE IF EXISTS cg_edges; DROP TABLE IF EXISTS cg_files;
   DROP VIEW IF EXISTS nodes; DROP VIEW IF EXISTS edges; DROP VIEW IF EXISTS files;
   ```

4. Update config.py: add `codegraph_db_path: Path = field(default=~/.council-memory/codegraph.db)`
5. Update sync.py: replace `~/.council-memory/pipelines.db` with `~/.council-memory/codegraph.db` in all defaults
6. Update sync-all.py: `DB_PATH = Path.home() / ".council-memory" / "codegraph.db"`
7. Update store.py: constructor accepts `codegraph_db_path`, JOIN tools ATTACH pipelines.db
8. Update tools.py: `_find_related_events()` and `_find_related_findings()` use ATTACH'd pipelines connection
9. Update watch.py: default `--db-path` → `codegraph.db`
10. Update TS extension: `DB_PATH` and `CODEGRAPH_DB_PATH` → `codegraph.db`

**Tests:**
- [ ] `codegraph_search(query="ExtensionAPI")` returns results from codegraph.db
- [ ] `pipelines.db` has zero cg_* tables
- [ ] `codegraph.db` has 18,856 nodes, 41,794 edges, 1,515 files
- [ ] TS extension `codegraph_status` reports correct counts
- [ ] JOIN tools (`similar_fixes`, `related_reviews`) work with ATTACH

**Dependencies:** none

---

### Phase 2: Memory Table Renames

**What:** Rename session_diary → working_memory, consolidation_cache → long_term_memory. Update prefixes from trace-/sess-/consol- to rawmem-/workmem-/longmem-.

**Files to Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/store.py` | All table references renamed |
| Modify | `super_council/memory_service/router.py` | Query methods target new table names |
| Modify | `super_council/memory_service/layer.py` | Unified recall channels updated |
| Modify | `super_council/memory_service/mcp_server.py` | MCP tool handlers updated |
| Modify | `super_council/memory_service/http_endpoints.py` | Endpoint handlers updated |
| Modify | `super_council/memory_service/db_poller.py` | Poll targets updated |
| Modify | `super_council/arc_summarizer/pipeline.py` | Tier output targets updated |
| Modify | `super_council/mcp_server.py` | Legacy MCP references updated |
| Modify | `super_council/super_council.py` | CouncilMemory references updated |
| Create | `migrations/09_rename_to_working_memory.sql` | ALTER TABLE session_diary RENAME TO working_memory |
| Create | `migrations/10_rename_to_long_term_memory.sql` | ALTER TABLE consolidation_cache RENAME TO long_term_memory |
| Modify | `tests/test_consolidation_metrics.py` | Table name assertions |
| Modify | `tests/test_db_poller.py` | Table name assertions |
| Modify | `tests/test_lazy_recall.py` | Table name assertions |
| Modify | `tests/test_tiered_consolidation.py` | Table name assertions |

**Steps:**

1. Run SQL renames on pipelines.db:
   ```sql
   ALTER TABLE session_diary RENAME TO working_memory;
   ALTER TABLE consolidation_cache RENAME TO long_term_memory;
   -- Update consolidation_tiers references
   UPDATE consolidation_tiers SET output_target = 'working_memory' WHERE output_target = 'session_diary';
   UPDATE consolidation_tiers SET output_target = 'long_term_memory' WHERE output_target = 'consolidation_cache';
   ```

2. Migrate surviving prefixes (4 rows):
   ```sql
   UPDATE raw_session_memories SET trace_id = REPLACE(trace_id, 'trace-', 'rawmem-') WHERE trace_id LIKE 'trace-%';
   UPDATE working_memory SET summary_id = REPLACE(summary_id, 'consol-', 'workmem-') WHERE summary_id LIKE 'consol-%';
   ```

3. Update store.py: replace all `session_diary` → `working_memory`, `consolidation_cache` → `long_term_memory`
4. Update router.py: `query_session_diary()` → `query_working_memory()`, `query_consolidation_cache()` → `query_long_term_memory()`
5. Update layer.py: unified recall channel names
6. Update arc_summarizer/pipeline.py: tier output table names
7. Update all test files: table name assertions
8. Create migration SQL files for idempotent schema loading

**Tests:**
- [ ] `SELECT * FROM working_memory` returns 2 rows with workmem-* prefixes
- [ ] `SELECT * FROM long_term_memory` returns 0 rows (table exists)
- [ ] `consolidation_tiers` output_target values updated
- [ ] No references to `session_diary` or `consolidation_cache` in Python code (grep check)
- [ ] `query_working_memory()` returns structured results

**Dependencies:** Phase 1 (table drops must complete first)

---

### Phase 3: Enum Simplification → CHECK Constraints

**What:** Drop 4 enum tables (phase_names, outcome_types, event_types, severity_levels). Replace FK references with CHECK constraints in DDL. Move seed values to Python constants.

**Files to Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/store.py` | Remove `_seed_enum_tables()`, remove `_sync_phase_registry()`, add VALID_* constants |
| Modify | `super_council/memory_service/store.py` | Remove `INSERT OR IGNORE INTO event_types` from `log_event()` |
| Modify | `migrations/01_schema.sql` | Replace FK references with CHECK constraints |
| Create | `migrations/11_check_constraints.sql` | Full DDL with CHECK constraints (idempotent recreate) |

**Steps:**

1. Define Python constants in store.py:
   ```python
   VALID_PHASES = frozenset(["SCOUT","PLAN","BUILD","COHESIVENESS_REVIEW","AGENT_VALIDATE","PENDING_REVIEW","HUMAN_GATE","INDEX","DELEGATION","DONE","FAILED"])
   VALID_OUTCOMES = frozenset(["success","failure","retreat","global_ceiling","skip"])
   VALID_EVENT_TYPES = frozenset(["transition","error","warning","info","checkpoint","retreat","global_ceiling","delegation","review-finding","review-verdict"])
   VALID_SEVERITIES = frozenset(["critical","high","moderate","low","info","error","warning"])
   ```

2. Drop enum tables:
   ```sql
   DROP TABLE IF EXISTS phase_names;
   DROP TABLE IF EXISTS outcome_types;
   DROP TABLE IF EXISTS event_types;
   DROP TABLE IF EXISTS severity_levels;
   ```

3. Recreate core tables with CHECK constraints (see Phase 3A DDL in source spec). Key changes:
   - `phase TEXT NOT NULL CHECK (phase IN (...))` instead of `REFERENCES phase_names`
   - `outcome TEXT NOT NULL CHECK (outcome IN (...))` instead of `REFERENCES outcome_types`
   - `event_type TEXT NOT NULL CHECK (event_type IN (...))` instead of `REFERENCES event_types`
   - `severity TEXT NOT NULL CHECK (severity IN (...))` instead of `REFERENCES severity_levels`

4. Update store.py:
   - Remove `_seed_enum_tables()` method
   - Remove `_sync_phase_registry()` method
   - Remove `INSERT OR IGNORE INTO event_types` from `log_event()`
   - Remove enum seeding from `__init__()`

5. Create migration SQL file for idempotent schema loading

**Tests:**
- [ ] `INSERT INTO event_log` with invalid event_type → IntegrityError
- [ ] `INSERT INTO state_executions` with invalid outcome → IntegrityError
- [ ] `INSERT INTO event_log` with valid "review-finding" event_type → success
- [ ] No enum tables exist in sqlite_master
- [ ] `_seed_enum_tables()` no longer called in RelationalStore.__init__()

**Dependencies:** Phase 2 (table renames must complete first)

---

### Phase 4: Review Streamlining

**What:** Create dedicated `reviews` + `review_findings` tables. Rewrite ReviewService to use them instead of fake pipelines. Pass real project_id through review lifecycle.

**Files to Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Rewrite | `super_council/memory_service/review.py` | New ReviewService with reviews table |
| Modify | `super_council/memory_service/http_endpoints.py` | review.start/log/verdict handlers |
| Modify | `super_council/memory_service/mcp_server.py` | MCP tool handlers |
| Modify | `super_council/memory_service/router.py` | `get_review_findings()` queries new table |
| Modify | `super_council/mcp_server.py` | Legacy MCP handlers |
| Modify | `super_council/super_council.py` | Supervisor review integration |
| Create | `migrations/12_reviews_tables.sql` | reviews + review_findings tables |

**Steps:**

1. Create tables:
   ```sql
   CREATE TABLE reviews (
       review_id TEXT PRIMARY KEY,
       reviewer TEXT NOT NULL,
       target TEXT NOT NULL,
       project_id TEXT NOT NULL,
       work_id TEXT,
       status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','passed','failed','partial')),
       started_at TEXT NOT NULL,
       finished_at TEXT
   );
   CREATE INDEX idx_reviews_project ON reviews(project_id, status);
   CREATE INDEX idx_reviews_work ON reviews(work_id);

   CREATE TABLE review_findings (
       finding_id TEXT PRIMARY KEY,
       review_id TEXT NOT NULL REFERENCES reviews(review_id),
       severity TEXT NOT NULL CHECK (severity IN ('critical','high','moderate','low','info')),
       summary TEXT NOT NULL,
       fix TEXT,
       evidence TEXT,
       action TEXT,
       created_at TEXT NOT NULL
   );
   CREATE INDEX idx_findings_review ON review_findings(review_id, severity);
   ```

2. Rewrite ReviewService (see Phase 4B in source spec):
   - `start_review(reviewer, target, project_id, work_id=None)` → INSERT INTO reviews
   - `log_finding(review_id, severity, summary, fix, evidence, action)` → INSERT INTO review_findings
   - `record_verdict(review_id, verdict, reason, raw_output=None)` → UPDATE reviews + event_log

3. Update http_endpoints.py: review.start accepts `project_id` parameter
4. Update router.py: `get_review_findings(project_id)` queries reviews + review_findings
5. Update MCP server handlers

**Tests:**
- [ ] `review.start_review('nemotron', 'auth', '7-council')` → returns review_id
- [ ] `review.log_finding(review_id, 'high', 'Missing validation')` → returns finding_id
- [ ] `review.record_verdict(review_id, 'FAIL', 'Needs validation')` → updates status
- [ ] `get_review_findings(project_id='7-council')` returns findings
- [ ] No fake `mcp-review-*` pipelines created in pipelines table

**Dependencies:** Phase 3 (CHECK constraints must be in place)

---

### Phase 5: Unified Work Items

**What:** Create `work_items` table that tracks ALL work (pipelines, reviews, delegations, ad-hoc). Replace `translations` table with parent_work_id self-references.

**Files to Modify:**

| Action | File | Purpose |
|--------|------|---------|
| Modify | `super_council/memory_service/store.py` | Add work_items CRUD methods, update upsert_pipeline |
| Modify | `super_council/super_council.py` | _get_or_create_pipeline creates work_items entry |
| Modify | `super_council/memory_service/review.py` | start_review creates work_items entry |
| Create | `migrations/13_work_items.sql` | work_items table, drop translations |

**Steps:**

1. Create table:
   ```sql
   CREATE TABLE work_items (
       work_id TEXT PRIMARY KEY,
       project_id TEXT NOT NULL,
       work_type TEXT NOT NULL CHECK (work_type IN ('pipeline','review','delegation','ad-hoc')),
       task TEXT NOT NULL,
       task_hash TEXT NOT NULL,
       parent_work_id TEXT REFERENCES work_items(work_id),
       status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','done','failed')),
       metadata TEXT,
       created_at TEXT NOT NULL,
       finished_at TEXT,
       UNIQUE(task_hash, project_id, work_type)
   );
   CREATE INDEX idx_work_project ON work_items(project_id, status);
   CREATE INDEX idx_work_parent ON work_items(parent_work_id);
   CREATE INDEX idx_work_type ON work_items(work_type, status);

   -- Link pipelines to work_items
   ALTER TABLE pipelines ADD COLUMN work_id TEXT REFERENCES work_items(work_id);
   DROP TABLE IF EXISTS translations;
   ```

2. Add CRUD methods to store.py:
   ```python
   def create_work_item(self, work_id, project_id, work_type, task, parent_work_id=None, metadata=None):
       task_hash = hashlib.sha256(f"{task}::{project_id}::{work_type}".encode()).hexdigest()[:32]
       self.db.execute("""INSERT INTO work_items (work_id, project_id, work_type, task, task_hash, parent_work_id, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (work_id, project_id, work_type, task, task_hash, parent_work_id, metadata, self._now_iso()))
       return work_id

   def query_work_items(self, project_id=None, work_type=None, status=None):
       query = "SELECT * FROM work_items WHERE 1=1"
       params = []
       if project_id: query += " AND project_id = ?"; params.append(project_id)
       if work_type: query += " AND work_type = ?"; params.append(work_type)
       if status: query += " AND status = ?"; params.append(status)
       return [dict(r) for r in self.db.execute(query, params).fetchall()]
   ```

3. Update `upsert_pipeline()` to also create work_items entry
4. Update ReviewService.start_review() to create work_items entry
5. Update `_delegate()` to create work_items entry with parent_work_id

**Tests:**
- [ ] `create_work_item('test-1', '7-council', 'pipeline', 'test task')` → returns work_id
- [ ] `query_work_items(project_id='7-council')` returns entries
- [ ] `translations` table no longer exists
- [ ] `pipelines` table has `work_id` column
- [ ] Delegation creates work_item with parent_work_id

**Dependencies:** Phase 4 (reviews table must exist)

---

### Phase 6: Verification & Smoke Tests

**What:** Run comprehensive verification across all phases.

**Steps:**

1. **Phase 1 verification:**
   ```bash
   python3 -c "
   import sqlite3
   cg = sqlite3.connect('/home/chief/.council-memory/codegraph.db')
   pl = sqlite3.connect('/home/chief/.council-memory/pipelines.db')
   assert cg.execute('SELECT COUNT(*) FROM cg_nodes').fetchone()[0] == 18856
   assert not pl.execute(\"SELECT name FROM sqlite_master WHERE name='cg_nodes'\").fetchone()
   print('Phase 1: OK')
   cg.close(); pl.close()
   "
   ```

2. **Phase 2 verification:**
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('/home/chief/.council-memory/pipelines.db')
   tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
   assert 'working_memory' in tables
   assert 'long_term_memory' in tables
   assert 'session_diary' not in tables
   assert 'consolidation_cache' not in tables
   print('Phase 2: OK')
   conn.close()
   "
   ```

3. **Phase 3 verification:**
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('/home/chief/.council-memory/pipelines.db')
   try:
       conn.execute(\"INSERT INTO event_log VALUES ('t','t','invalid','info','t','t','t')\")
       print('Phase 3: FAIL (accepted invalid event_type)')
   except sqlite3.IntegrityError:
       print('Phase 3: OK')
   conn.close()
   "
   ```

4. **Phase 4 verification:**
   ```bash
   python3 -c "
   from super_council.memory_service import MemoryService
   ms = MemoryService.load()
   r = ms.review.start_review('test', 'target', '7-council')
   assert 'review_id' in r
   ms.review.log_finding(r['review_id'], 'high', 'test finding')
   ms.review.record_verdict(r['review_id'], 'PASS', 'all good')
   print('Phase 4: OK')
   "
   ```

5. **Phase 5 verification:**
   ```bash
   python3 -c "
   import sqlite3
   conn = sqlite3.connect('/home/chief/.council-memory/pipelines.db')
   assert 'work_items' in [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
   assert 'translations' not in [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
   print('Phase 5: OK')
   conn.close()
   "
   ```

6. **CodeGraph tools verification:**
   ```bash
   # From pi agent, run: codegraph_search(query="ReviewService")
   # Should return results from codegraph.db
   ```

7. **Grep check — no stale references:**
   ```bash
   grep -rn "session_diary\|consolidation_cache\|event_types\|outcome_types\|severity_levels\|phase_names" \
       super_council/ --include="*.py" | grep -v __pycache__ | grep -v "migrations/" | grep -v "CHECK\|VALID_\|FROZEN"
   # Should return nothing (or only comments/docs)
   ```

**Tests:**
- [ ] All 6 verification scripts pass
- [ ] codegraph_search works from both Python MCP and TS extension
- [ ] No stale table references in Python code
- [ ] Full review lifecycle works end-to-end

**Dependencies:** Phases 1-5

---

### Constraints

- **No data loss:** The 4 surviving rows (2 raw_session_memories, 2 session_diary) must be preserved with prefix migration
- **CHECK constraints must include "review-finding" and "review-verdict":** These are used by ReviewService but were missing from the seed list
- **codegraph.db must use WAL mode:** Required for concurrent reads by Python MCP + TS extension
- **JOIN tools must work across DBs:** similar_fixes and related_reviews query event_log from pipelines.db while searching cg_nodes from codegraph.db
- **ReviewService must accept project_id:** No more hardcoded "mcp-review" — reviews must link to actual projects
- **work_items must be backward-compatible:** Existing pipeline queries must still work (pipelines table kept, linked via work_id)

### Success Criteria

- [ ] codegraph.db exists with 18,856 nodes, 41,794 edges, 1,515 files
- [ ] pipelines.db has zero cg_* tables
- [ ] working_memory and long_term_memory tables exist (no session_diary/consolidation_cache)
- [ ] Zero enum tables (phase_names, outcome_types, event_types, severity_levels dropped)
- [ ] CHECK constraints reject invalid enum values
- [ ] reviews and review_findings tables exist and are functional
- [ ] work_items table exists with parent_work_id self-references
- [ ] translations table dropped (replaced by work_items)
- [ ] codegraph_search returns results from codegraph.db
- [ ] Full review lifecycle (start → log → verdict) works without creating fake pipelines
- [ ] No stale table references in Python code (grep check passes)
- [ ] All smoke tests pass
