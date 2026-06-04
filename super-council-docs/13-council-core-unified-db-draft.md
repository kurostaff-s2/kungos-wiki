# Council Core — Unified Database Integration Draft (v3)

> **Date:** 2026-06-04
> **Status:** Revised v3 — embedding consolidation (pplx-embed-v1), review findings incorporated, search architecture unified
> **Scope:** Single SQLite database (`council_core.db`) unifying Council workflow + Odysseus features + knowledge cards + audit trail + unified search
> **CodeGraph:** Separate file (`codegraph.db`) — excluded from council_core
> **Embeddings:** `pplx-embed-v1-0.6b-int8` on `:18099` — single model, ONNX INT8, CPU
> **Vector Store:** Milvus-lite (`~/.memsearch/milvus.db`) — single collection
> **Search:** SearXNG on `:8080` — external service, not DB-resident
> **Review:** PARTIAL → findings verified against actual codebase, all 15 items addressed

---

## 1. Decision: SQLite, Single File, No PostgreSQL

**What exists today:**

| Component | Backend | Location | Status |
|---|---|---|---|
| Council Memory Service | SQLite | `~/.council-memory/pipelines.db` (193 MB + 116 MB WAL) | ✅ Running |
| Odysseus | SQLite | `super_council/vendor/odysseus/data/app.db` (24 tables, mostly empty) | ⚠️ Vendored, not wired |
| PostgreSQL | PostgreSQL | `:5432` | ⚠️ Running, all databases empty |
| CodeGraph | SQLite | `pipelines.db` (embedded, 94K nodes, 257K edges) | ✅ Running, needs extraction |
| SearXNG | HTTP | `:8080` | ✅ Running |
| Embedding (pplx) | ONNX INT8 | `~/models/embedding/pplx-embed-v1-0.6b-int8/` (688 MB) | ⚠️ Model exists, server.py not running |
| Embedding (bge-m3) | ONNX INT8 | `~/.fastembed/` (via memsearch package) | ✅ Running, will be replaced |
| Vector Store | Milvus-lite | `~/.memsearch/milvus.db` (351 entities, 3.9 MB) | ✅ Running |
| ChromaDB | Docker | `:8100` | ❌ Not running, will be removed |

**Decision:** Everything that works is SQLite. PostgreSQL is running but has zero tables. The `council_core.*`, `council_ops.*`, `council_sync.*` schemas referenced in earlier docs are aspirational — they don't exist anywhere.

**Target:** Single SQLite file named `council_core.db` with WAL mode, FK enforcement, and all business data. CodeGraph lives separately.

```
~/.council-memory/
├── council_core.db        — unified business database (NEW, replaces pipelines.db)
├── codegraph.db           — code knowledge graph (extracted, separate)
└── (no vector DB here — Milvus-lite lives in ~/.memsearch/)

~/models/embedding/
└── pplx-embed-v1-0.6b-int8/  — single embedding model (ONNX INT8, 1024d, 32K ctx)

~/.memsearch/
└── milvus.db/                 — single vector store (Milvus-lite, unified_vectors collection)
```

---

## 2. Boundary Rules

**Odysseus owns:**
- Initial research and synthesis
- Notes, drafts, documents, knowledge capture
- UI surface, chat, progress streaming, user-facing orchestration
- Agent planning, tool selection, task decomposition
- LLM abstraction (multi-provider with fallback)
- Context management (budget + compaction)
- Email/Calendar integration
- SearXNG query generation

**Council owns:**
- Canonical persistence (all writes land in `council_core.db`)
- Review lifecycle (start/log/verdict with findings)
- Memory consolidation (ArcPipeline, tiered rollups)
- Event logging and audit trail
- Workflow execution tracking (pipelines, phases)
- Knowledge card materialization
- Code intelligence (separate `codegraph.db`)
- **Unified search routing** (vector + FTS5 + keyword + web)
- **Embedding infrastructure** — single model (`pplx-embed-v1-0.6b`), single HTTP server (`:18099`), single vector store (Milvus-lite)

**Hard rules:**
1. Odysseus may draft and recommend, but all canonical writes go through Council's RelationalStore
2. Council may execute and persist, but does not own conversational UX
3. Odysseus maintains ephemeral session context; Council owns durable memory
4. Odysseus stages notes and research; Council materializes approved artifacts
5. CodeGraph is its own file — never embedded in `council_core.db`
6. **All vector search goes through the Unified Search Router** — no direct ChromaDB/Milvus access from agents
7. **All embeddings go through pplx-embed-v1** — no secondary embedding models (bge-m3, all-MiniLM removed)
8. **Embedding server is the single source** — `:18099` HTTP endpoint. Direct ONNX load only for MicroModelEnricher (async, low-latency path)

---

## 3. Database Architecture

### 3.1 council_core.db (Unified)

```sql
-- Connection config (replaces pipelines.db)
-- Path: ~/.council-memory/council_core.db
-- Mode: WAL, FK ON, autocheckpoint OFF (manual checkpoint on idle)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 0;
PRAGMA cache_size = -8000;  -- 8 MB cache
PRAGMA busy_timeout = 5000;  -- 5s busy timeout
```

### 3.2 codegraph.db (Separate)

```sql
-- Connection config
-- Path: ~/.council-memory/codegraph.db
-- Mode: WAL, read-optimized
-- Access: CodeGraphStore only (memory_service.cg_store)

PRAGMA journal_mode = WAL;
PRAGMA cache_size = -16000;  -- 16 MB cache (search-heavy)
PRAGMA busy_timeout = 10000;
```

### 3.3 SearXNG (External Service)

```
URL: http://127.0.0.1:8080
Transport: HTTP (not DB-resident)
Used by: Odysseus web_search tool, deep_research queries
Config: vendor/odysseus/src/settings.py → search_provider = "searxng"
```

### 3.4 Embedding Server (pplx-embed-v1, Single Model)

```
URL: http://127.0.0.1:18099
Transport: HTTP (OpenAI-compatible /v1/embeddings, /v1/models)
Model: pplx-embed-v1-0.6b-int8 (ONNX INT8, CPU, 1024d, 32K context)
Path: ~/models/embedding/pplx-embed-v1-0.6b-int8/
Server: server.py (existing, needs to be started)
Used by: Memsearch (HTTP client), MicroModelEnricher (direct ONNX), Odysseus (HTTP client)

Why pplx-embed-v1:
- Bidirectional attention (proper embedding architecture, not causal LM)
- 1024 dimensions (same as bge-m3, 2.7x more than all-MiniLM)
- 32K context window (bge-m3 maxes at 8192)
- Perplexity fine-tune (code + multilingual + web data)
- ONNX INT8 quantized (fast CPU inference)
- Replaces: bge-m3-onnx-int8, all-MiniLM-L6-v2

Port choice: :18099 (avoids conflict with memory-service SSE on :18097)
```

### 3.5 Vector Store (Milvus-lite, Single Collection)

```
Path: ~/.memsearch/milvus.db
Backend: Milvus-lite (embedded, no external service)
Collection: unified_vectors (single, replaces memsearch_chunks)
Embedding source: pplx-embed-v1 HTTP (:18099)
Access: Memsearch (MemSearch wrapper), UnifiedVectorStore
Replaces: ChromaDB (odysseus_memories, odysseus_rag)
```

---

### 3.6 What Gets Removed

| Component | Why | Replacement |
|---|---|---|
| bge-m3-onnx-int8 | Duplicate embedding model | pplx-embed-v1 |
| all-MiniLM-L6-v2 | Duplicate, smaller, English-only | pplx-embed-v1 |
| ChromaDB service | External dependency, not running | Milvus-lite (embedded) |
| ChromaDB collections | `odysseus_memories`, `odysseus_rag` | `unified_vectors` in Milvus-lite |
| `UnifiedEmbeddingService` class | Duplicates pplx `server.py` | Use existing server.py |
| Memsearch bge-m3 direct load | ONNX direct → HTTP client | HTTP to :18099 |
| Odysseus EmbeddingClient default | all-MiniLM → pplx | Set EMBEDDING_URL=:18099 |

---

## 4. Schema Design

> **Migration ordering:** Tables are defined in dependency order. `projects` is created first because it's referenced by FKs throughout.

### 4.0 Projects (Created First — FK Anchor)

```sql
-- Projects (canonical identity, dedup via slug UNIQUE)
-- MUST be created before any table that FK-references it
CREATE TABLE projects (
    id TEXT PRIMARY KEY,                -- UUID (system-stable)
    slug TEXT NOT NULL UNIQUE,          -- 'mcp-review' (human-stable, dedup key)
    name TEXT NOT NULL,
    description TEXT,                   -- used for FTS5 keyword resolution
    status TEXT DEFAULT 'active',       -- 'active', 'paused', 'archived'
    priority TEXT,                      -- 'critical', 'high', 'medium', 'low'
    tags TEXT DEFAULT '[]',             -- JSON array
    owner_id TEXT,                      -- username (no users table — see §4.7)
    metadata TEXT DEFAULT '{}',        -- JSON
    created_by TEXT,
    updated_by TEXT,
    revision INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- FTS5 index on projects for Channel 4 of project resolution (keyword match)
CREATE VIRTUAL TABLE projects_fts USING fts5(name, description, content='projects', content_rowid='rowid');
```

### 4.1 Council Tables (Existing, Renamed from pipelines.db)

These tables already exist in `pipelines.db`. They are kept as-is with minor harmonization.

#### Memory & Consolidation

```sql
-- Extracted session memories (from conversations)
-- Council's trace-based extraction — raw YAML/text from agent sessions
CREATE TABLE raw_session_memories (
    trace_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    raw_text TEXT,
    project_id TEXT REFERENCES projects(id),  -- resolved at insert or late-bound
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER,
    is_indexed INTEGER DEFAULT 0
);
CREATE INDEX idx_raw_memories_project ON raw_session_memories(project_id);

-- Consolidation cache (ArcPipeline output)
CREATE TABLE consolidation_cache (
    cache_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    continuity_notes TEXT,
    preferences TEXT,          -- JSON
    active_context TEXT,
    decisions TEXT,            -- JSON array
    unresolved TEXT,           -- JSON array
    project_id TEXT REFERENCES projects(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER,
    is_active INTEGER DEFAULT 1,
    is_probation INTEGER DEFAULT 0,
    is_indexed INTEGER DEFAULT 0
);
CREATE INDEX idx_consolidation_project ON consolidation_cache(project_id);

-- Consolidation tier definitions (seeded config, not user data)
CREATE TABLE consolidation_tiers (
    tier_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    ttl_days INTEGER NOT NULL,
    schedule_cron TEXT,
    input_source TEXT NOT NULL,
    output_target TEXT NOT NULL,
    last_run_at TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Session diary (daily summaries, Arc output)
CREATE TABLE session_diary (
    summary_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    session_context TEXT,
    decisions TEXT,            -- JSON array
    open_items TEXT,           -- JSON array
    work_completed TEXT,
    project_id TEXT REFERENCES projects(id),  -- resolved via 4-channel cascade
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER,
    is_indexed INTEGER DEFAULT 0,
    consolidation_tier TEXT,
    ttl_phase TEXT
);
CREATE INDEX idx_session_diary_project ON session_diary(project_id);
```

#### Workflow & Execution

```sql
-- Pipeline definitions (TDD workflows)
CREATE TABLE pipelines (
    pipeline_id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    task_hash TEXT NOT NULL,
    project_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    global_attempts INTEGER,
    metadata TEXT,             -- JSON
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Workflow definitions (phase transitions)
CREATE TABLE workflow_definitions (
    workflow_name TEXT PRIMARY KEY,
    phases TEXT NOT NULL,      -- JSON array
    transitions TEXT NOT NULL, -- JSON object
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Workflow runs (active phase execution)
CREATE TABLE workflow_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL REFERENCES pipelines(pipeline_id),
    project_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

-- Execution artifacts (phase outputs)
CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES workflow_runs(run_id),
    phase TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_indexed INTEGER DEFAULT 0
);

-- Review findings (from ReviewService)
CREATE TABLE review_findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    severity TEXT,             -- 'critical', 'high', 'moderate', 'low', 'info'
    summary TEXT,
    fix TEXT,
    details TEXT,
    content TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Event log (system events, audit trail)
CREATE TABLE event_log (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata TEXT,             -- JSON
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_event_log_type ON event_log(event_type);
CREATE INDEX idx_event_log_severity ON event_log(severity);
```

> **Removed `pipelines_archive`:** Duplicate of `pipelines`. Replaced with soft-delete pattern (§4.8 Retention Policies).

### 4.2 Odysseus Tables (Merged In, Harmonized)

These tables come from Odysseus but are harmonized to Council's schema conventions: TEXT PKs, TEXT timestamps, JSON metadata columns, **FK constraints preserved**.

#### Sessions & Chat (Created Before Other Tables That Reference Sessions)

```sql
-- Chat sessions (from Odysseus, harmonized)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    model TEXT NOT NULL,
    owner_id TEXT,             -- username (no users table — see §4.7)
    project_id TEXT REFERENCES projects(id),  -- for project resolution chain (channel 2)
    has_rag INTEGER DEFAULT 0,
    is_archived INTEGER DEFAULT 0,
    folder TEXT,
    headers TEXT,              -- JSON
    last_accessed TEXT,
    last_message_at TEXT,
    is_important INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    mode TEXT,                 -- 'chat', 'agent', 'research'
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER         -- TTL for session cleanup (§4.8)
);
CREATE INDEX idx_sessions_project ON sessions(project_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- Chat messages
CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,        -- 'user', 'assistant', 'system', 'tool'
    content TEXT NOT NULL,
    metadata TEXT,             -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);
```

#### Task Scheduling

```sql
-- Scheduled tasks (from Odysseus TaskScheduler)
CREATE TABLE scheduled_tasks (
    id TEXT PRIMARY KEY,
    owner_id TEXT,             -- username
    name TEXT NOT NULL,
    prompt TEXT,
    task_type TEXT,            -- 'llm', 'action'
    action TEXT,               -- 'tidy_sessions', 'consolidate_memory', etc.
    schedule TEXT,             -- 'daily', 'weekly', 'monthly', 'once', 'cron'
    scheduled_time TEXT,       -- HH:MM for daily/weekly/monthly
    scheduled_day INTEGER,     -- 0-6 for weekly
    scheduled_date TEXT,       -- ISO date for 'once'
    cron_expression TEXT,      -- for 'cron' type
    trigger_event TEXT,        -- 'session_created', 'memory_added', 'consolidation_completed'
    trigger_count INTEGER,     -- fire after N events
    trigger_counter INTEGER DEFAULT 0,
    next_run TEXT,             -- ISO timestamp
    last_run TEXT,
    status TEXT DEFAULT 'active',  -- 'active', 'paused', 'archived'
    output_target TEXT,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    model TEXT,
    endpoint_url TEXT,
    run_count INTEGER DEFAULT 0,
    max_steps INTEGER,
    timezone TEXT,             -- IANA timezone
    metadata TEXT DEFAULT '{}', -- JSON
    is_enabled INTEGER DEFAULT 1,
    is_builtin INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_scheduled_tasks_next_run ON scheduled_tasks(next_run);
CREATE INDEX idx_scheduled_tasks_status ON scheduled_tasks(status);

-- Task runs (execution history)
CREATE TABLE task_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
        -- 'queued', 'running', 'succeeded', 'failed', 'aborted'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms REAL,
    result TEXT,               -- live progress or final result
    error TEXT,
    tokens_used INTEGER,
    steps TEXT,                -- JSON array of execution steps
    model TEXT,
    attempt_count INTEGER DEFAULT 1,
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_task_runs_status ON task_runs(status);
CREATE INDEX idx_task_runs_task ON task_runs(task_id);
```

#### Memories

```sql
-- Extracted memories (from Odysseus MemoryExtractor)
-- STRUCTURED facts from LLM extraction — distinct from raw_session_memories (raw trace text)
-- Boundary rule: raw_session_memories = raw YAML/text traces; memories = structured facts
-- Dedup rule: before INSERT, check MemoryVectorStore.find_similar(text, threshold=0.92)
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    category TEXT,             -- 'preference', 'fact', 'decision', 'context'
    source TEXT,               -- 'conversation', 'research', 'extraction', 'manual'
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id),  -- resolved at insert
    confidence REAL,           -- 0.0-1.0
    tags TEXT DEFAULT '[]',    -- JSON array
    related_memory_ids TEXT DEFAULT '[]',
    tier TEXT,                 -- 'daily', 'short', 'weekly', 'bimonthly'
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER,
    is_indexed INTEGER DEFAULT 0
);
CREATE INDEX idx_memories_category ON memories(category);
CREATE INDEX idx_memories_source ON memories(source);
CREATE INDEX idx_memories_session ON memories(session_id);
CREATE INDEX idx_memories_project ON memories(project_id);
```

#### Documents

```sql
-- Documents (from Odysseus, harmonized)
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id),  -- for project-scoped queries
    title TEXT NOT NULL,
    language TEXT,
    content TEXT NOT NULL DEFAULT '',
    version_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_archived INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',    -- JSON array
    metadata TEXT DEFAULT '{}', -- JSON
    created_by TEXT,
    updated_by TEXT,
    revision INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_documents_session ON documents(session_id);
CREATE INDEX idx_documents_project ON documents(project_id);
```

#### Notes

```sql
-- Notes (from Odysseus, harmonized)
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    title TEXT,
    body TEXT,
    items TEXT,                -- JSON array for checklist items
    note_type TEXT,            -- 'text', 'checklist', 'quote', 'image'
    tags TEXT DEFAULT '[]',    -- JSON array
    is_pinned INTEGER DEFAULT 0,
    is_archived INTEGER DEFAULT 0,
    due_date TEXT,
    source TEXT,               -- 'manual', 'ai_extraction', 'research', 'arc_consolidation'
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id),  -- resolved from source or cascade
    metadata TEXT DEFAULT '{}', -- JSON
    created_by TEXT,
    updated_by TEXT,
    revision INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_notes_session ON notes(session_id);
CREATE INDEX idx_notes_project ON notes(project_id);
```

#### Agent Configuration

```sql
-- Crew members (agent personas)
CREATE TABLE crew_members (
    id TEXT PRIMARY KEY,
    owner_id TEXT,             -- username
    name TEXT NOT NULL,
    avatar TEXT,
    username TEXT,
    personality TEXT,
    model TEXT,
    endpoint_url TEXT,
    greeting TEXT,
    enabled_tools TEXT DEFAULT '[]', -- JSON array
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    is_default_assistant INTEGER DEFAULT 0,
    timezone TEXT,
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Model endpoints (LLM providers)
-- api_key uses EncryptedText type (Fernet encryption at rest) — see §4.7
CREATE TABLE model_endpoints (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT,              -- EncryptedText (Fernet, not plaintext)
    is_enabled INTEGER DEFAULT 1,
    hidden_models TEXT DEFAULT '[]', -- JSON array
    cached_models TEXT DEFAULT '[]', -- JSON array
    pinned_models TEXT DEFAULT '[]', -- JSON array
    model_type TEXT,             -- 'openai', 'ollama', 'vllm', 'llamacpp'
    supports_tools INTEGER DEFAULT 0,
    owner_id TEXT,             -- username
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

#### Calendar

```sql
-- Calendars
CREATE TABLE calendars (
    id TEXT PRIMARY KEY,
    owner_id TEXT,             -- username
    name TEXT NOT NULL,
    color TEXT,
    source TEXT,               -- 'caldav', 'ics', 'manual'
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Calendar events
CREATE TABLE calendar_events (
    id TEXT PRIMARY KEY,
    calendar_id TEXT NOT NULL REFERENCES calendars(id),
    uid TEXT NOT NULL,          -- iCalendar UID
    summary TEXT NOT NULL,
    description TEXT,
    location TEXT,
    dtstart TEXT NOT NULL,      -- ISO timestamp
    dtend TEXT NOT NULL,
    is_all_day INTEGER DEFAULT 0,
    is_utc INTEGER DEFAULT 0,
    rrule TEXT,                -- recurrence rule
    color TEXT,
    status TEXT,               -- 'confirmed', 'tentative', 'cancelled'
    importance TEXT,           -- 'high', 'normal', 'low'
    event_type TEXT,           -- AI-classified: 'meeting', 'deadline', 'reminder', etc.
    last_pinged TEXT,
    source TEXT,               -- 'caldav', 'ics', 'email_extraction', 'manual'
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_calendar_events_calendar ON calendar_events(calendar_id);
CREATE INDEX idx_calendar_events_dtstart ON calendar_events(dtstart);
```

### 4.3 Bridge Tables (New)

These tables connect Odysseus's extraction/research with Council's governance.

#### Knowledge Cards

```sql
-- Knowledge cards (research → structured knowledge)
-- Created by: Odysseus deep_research → Council materialization
-- Consumed by: Unified Search Router, MemoryLayer slices
CREATE TABLE knowledge_cards (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL,            -- 0.0-1.0
    tags TEXT DEFAULT '[]',     -- JSON array
    sources TEXT DEFAULT '[]',  -- JSON array: [{url, title, relevance, snippet}]
    related_memory_ids TEXT DEFAULT '[]',
    related_research_ids TEXT DEFAULT '[]',
    project_id TEXT REFERENCES projects(id),  -- resolved at creation
    tier TEXT,                  -- 'daily', 'short', 'weekly', 'bimonthly'
    is_active INTEGER DEFAULT 1,
    is_indexed INTEGER DEFAULT 0,
    created_by TEXT,            -- 'agent', 'user', 'system'
    source_system TEXT,         -- 'odysseus_research', 'manual', 'memory_consolidation'
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER
);
CREATE INDEX idx_knowledge_cards_topic ON knowledge_cards(topic);
CREATE INDEX idx_knowledge_cards_tier ON knowledge_cards(tier);
CREATE INDEX idx_knowledge_cards_project ON knowledge_cards(project_id);
```

#### Audit Trail (with retention policy)

```sql
-- Lightweight audit trail with TTL-based retention
-- old_value/new_value store JSON snapshots of CHANGED fields only (not full row)
-- expires_at = 90 days from creation (configurable via config-subsystem.json)
CREATE TABLE audit_trail (
    id TEXT PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    action TEXT NOT NULL,       -- 'create', 'update', 'delete'
    old_value TEXT,             -- JSON snapshot of CHANGED fields only
    new_value TEXT,             -- JSON snapshot of CHANGED fields only
    actor TEXT,                 -- 'system', 'agent', 'user'
    source_system TEXT,         -- 'odysseus', 'council', 'memory_service'
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at INTEGER          -- TTL: 90 days default (§4.8)
);
CREATE INDEX idx_audit_trail_table ON audit_trail(table_name);
CREATE INDEX idx_audit_trail_record ON audit_trail(record_id);
CREATE INDEX idx_audit_trail_expires ON audit_trail(expires_at);
```

#### Research Reports

```sql
-- Research reports (from Odysseus deep_research)
CREATE TABLE research_reports (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    summary TEXT NOT NULL,
    sections TEXT DEFAULT '[]', -- JSON array of {title, content}
    sources TEXT DEFAULT '[]',  -- JSON array: [{url, title, snippet, relevance}]
    tokens_used INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    knowledge_card_id TEXT REFERENCES knowledge_cards(id),
    session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'active', -- 'active', 'archived'
    created_by TEXT,
    metadata TEXT DEFAULT '{}', -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_research_reports_session ON research_reports(session_id);
CREATE INDEX idx_research_reports_card ON research_reports(knowledge_card_id);
```

#### Work Items

```sql
-- Work items (todo lists, tasks, issues with phase tracking)
CREATE TABLE work_items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    kind TEXT NOT NULL,                 -- 'task', 'bug', 'feature', 'research', 'review'
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open',         -- 'open', 'in_progress', 'blocked', 'done', 'cancelled'
    priority TEXT,                      -- 'critical', 'high', 'medium', 'low'
    phase TEXT DEFAULT 'SCOUT',         -- current phase in state machine
    phase_history TEXT DEFAULT '[]',    -- JSON: [{from, to, at, by}]
    tags TEXT DEFAULT '[]',             -- JSON array
    assigned_to TEXT,
    due_date TEXT,
    related_pipeline_id TEXT REFERENCES pipelines(pipeline_id),
    related_run_id TEXT REFERENCES workflow_runs(run_id),
    related_research_id TEXT REFERENCES research_reports(id),
    related_review_id TEXT REFERENCES review_findings(finding_id),  -- FK added (§4.2 fix)
    metadata TEXT DEFAULT '{}',         -- JSON
    created_by TEXT,
    updated_by TEXT,
    revision INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_work_items_project ON work_items(project_id);
CREATE INDEX idx_work_items_status ON work_items(status);
CREATE INDEX idx_work_items_phase ON work_items(phase);
```

### 4.4 Project Identity & Phase Mechanics

#### Duplicate-Free Project Identity

**Problem:** Two agents (or the same agent at different times) try to create "mcp-review". Without dedup, you get two UUIDs for the same project.

**Solution: `slug UNIQUE` + `INSERT OR IGNORE` + re-read pattern.**

```python
def get_or_create_project(slug: str, name: str, **metadata) -> str:
    """Return existing project ID or create new one. Never duplicates.

    slug is the human-stable identifier. 'mcp-review' always → same UUID.
    """
    # Step 1: Look up by slug
    existing = db.execute(
        "SELECT id FROM projects WHERE slug = ?", (slug,)
    ).fetchone()
    if existing:
        return existing[0]  # return existing UUID

    # Step 2: INSERT OR IGNORE (race-condition safe)
    new_id = uuid4().hex
    db.execute("""
        INSERT OR IGNORE INTO projects (id, slug, name, metadata)
        VALUES (?, ?, ?, ?)
    """, (new_id, slug, name, json.dumps(metadata)))

    # Step 3: Return the winner (new_id if we won, existing if we lost the race)
    winner = db.execute(
        "SELECT id FROM projects WHERE slug = ?", (slug,)
    ).fetchone()
    return winner[0]
```

| Scenario | Result |
|---|---|
| Agent A creates "mcp-review" | `slug` unique → INSERT succeeds → returns UUID-α |
| Agent B creates "mcp-review" | `slug` unique → INSERT IGNORED → lookup returns UUID-α |
| A + B simultaneous | SQLite serializes `INSERT OR IGNORE` → one wins, both read same UUID |
| Agent recreates after restart | Lookup by slug → returns UUID-α |

**Rule:** `slug` is human-stable ("mcp-review"). `id` is system-stable (UUID). Everything internal uses `id`. Everything external uses `slug`. Lookup is always by `slug`.

#### Phase State Machine

**Defined in `workflow_definitions` table (seeded data):**

```
SCOUT → PLAN → BUILD → COHESIVENESS_REVIEW → AGENT_VALIDATE
    → PENDING_REVIEW → HUMAN_GATE → INDEX → DONE
                                         ↘ FAILED (from any phase)
                                         ↘ DELEGATION (from most phases)
```

**Transition method (validates against state machine):**

```python
def transition_work_item_phase(work_item_id: str, to_phase: str, actor: str = "system"):
    """Transition a work item to a new phase. Validates against state machine."""
    current = db.execute(
        "SELECT phase, phase_history, revision FROM work_items WHERE id = ?",
        (work_item_id,)
    ).fetchone()

    # Validate: is this transition allowed?
    allowed = get_allowed_transitions(current.phase)
    if to_phase not in allowed:
        return {"error": f"invalid: {current.phase} → {to_phase}", "allowed": allowed}

    # Execute: atomic update with history append
    new_history = json.loads(current.phase_history) + [{
        "from": current.phase, "to": to_phase,
        "at": now_iso(), "by": actor,
    }]
    db.execute("""
        UPDATE work_items SET phase = ?, phase_history = ?,
            revision = revision + 1, updated_at = ?
        WHERE id = ?
    """, (to_phase, json.dumps(new_history), now_iso(), work_item_id))

    # Terminal phase: link to pipeline completion
    if to_phase in ('DONE', 'FAILED'):
        db.execute("""
            UPDATE pipelines SET phase = ?, status = ?, completed_at = ?
            WHERE pipeline_id = (
                SELECT related_pipeline_id FROM work_items WHERE id = ?
            )
        """, (to_phase, 'done' if to_phase == 'DONE' else 'failed', now_iso(), work_item_id))
```

### 4.5 Project Resolution Chain (Fixed)

**Problem:** An agent calls `upsert_summary(summary_text)` without knowing which project it belongs to. How do we prevent orphaned or mis-tagged entries?

**Solution: 4-channel resolution cascade. Every summary gets a project_id or fires a late-resolution event.**

> **Channel 5 removed:** "Vector similarity to projects.description" was unimplementable (no embedding column, no FTS5 index, no mechanism). Replaced with FTS5 keyword match as Channel 4.

```
upsert_summary(summary_text, source, project_id?, session_id?)
  ↓
┌─────────────────────────────────────────────────────┐
│ Channel 1: Explicit project_id (if provided)        │
│   → validate exists in projects table, done         │
└──────────────────┬──────────────────────────────────┘
                   │ not provided
                   ↓
┌─────────────────────────────────────────────────────┐
│ Channel 2: Active session → project                 │
│   SELECT project_id FROM sessions WHERE id=?        │
└──────────────────┬──────────────────────────────────┘
                   │ no session or session unbound
                   ↓
┌─────────────────────────────────────────────────────┐
│ Channel 3: File paths in text → codegraph           │
│   Extract paths: regex r'\w+\.py|\.ts|\.md'        │
│   Match against cg_files → derive project slug      │
└──────────────────┬──────────────────────────────────┘
                   │ no paths or no match
                   ↓
┌─────────────────────────────────────────────────────┐
│ Channel 4: FTS5 keyword match on projects           │
│   SELECT id FROM projects_fts                       │
│   WHERE projects_fts MATCH ?                        │
│   → match against summary_text keywords             │
│   → threshold: ≥ 1 match in name OR description     │
└──────────────────┬──────────────────────────────────┘
                   │ no match
                   ↓
┌─────────────────────────────────────────────────────┐
│ Fallback: INSERT with project_id=NULL               │
│   → fire event: summary_needs_tagging               │
│   → Arc daily tier resolves batch (late binding)    │
└─────────────────────────────────────────────────────┘
```

**FTS5-based resolution (replaces Channel 5 vector similarity):**

```python
def _resolve_project_fts5(summary_text: str) -> Optional[str]:
    """Match summary text against projects using FTS5 keyword search.

    Extracts keywords from summary_text and searches projects_fts.
    Returns project_id if match found, else None.
    """
    import re

    # Extract meaningful keywords (nouns, project-like terms)
    keywords = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', summary_text.lower())
    # Build FTS5 query: OR-join of top 10 keywords
    query = ' OR '.join(keywords[:10])

    row = db.execute(
        "SELECT id FROM projects_fts WHERE projects_fts MATCH ?",
        (query,)
    ).fetchone()

    return row[0] if row else None
```

**Late resolution (Arc daily tier):**

```python
def _resolve_untagged_summaries(self):
    """Batch-resolve untagged summaries during daily consolidation."""
    untagged = db.execute("""
        SELECT summary_id, session_context FROM session_diary
        WHERE project_id IS NULL
        ORDER BY created_at DESC LIMIT 50
    """).fetchall()

    for summary_id, text in untagged:
        project_id = resolve_project_for_summary(text)
        if project_id:
            db.execute(
                "UPDATE session_diary SET project_id = ? WHERE summary_id = ?",
                (project_id, summary_id)
            )
    return len(untagged)
```

**Guarantee:**

| State | Meaning |
|---|---|
| `project_id = valid UUID` | Resolved at insert time (channels 1-4) |
| `project_id = NULL + event fired` | Will be resolved by Arc daily tier |
| `project_id = NULL + expires_at past` | Pruned by vacuum, never resolved |

**Never:** duplicate project UUID (slug UNIQUE). **Never:** permanently orphaned summary (resolution cascade + late resolution + expiry).

### 4.6 System Tables (Reference Data)

> **Note:** These are seeded config, not user data. Consider migrating to Python constants/enums for simpler deployment (§4.7).

```sql
-- Event type definitions (seeded at migration time)
CREATE TABLE event_types (
    type_name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1
);

-- Phase name definitions (seeded at migration time)
CREATE TABLE phase_names (
    phase_name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1
);

-- Severity level definitions (seeded at migration time)
CREATE TABLE severity_levels (
    level TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    weight INTEGER NOT NULL  -- for sorting/filtering
);

-- Outcome type definitions (seeded at migration time)
CREATE TABLE outcome_types (
    type_name TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    is_positive INTEGER
);
```

### 4.7 Design Notes

#### Owner Model (No Users Table)

`owner_id` across `scheduled_tasks`, `crew_members`, `calendars`, `model_endpoints`, `projects` is a **TEXT username**, not a FK to a users table. This matches the actual Odysseus implementation where ownership is tracked as a string identifier.

- **No `users` table** — ownership is username-based, not user-ID-based
- **Single admin** — current Odysseus uses `auth.json` for auth, not DB-resident users
- **Legacy rows** — `_migrate_assign_legacy_owner()` backfills NULL owners to first admin user

#### API Key Encryption

`model_endpoints.api_key` is declared as `TEXT` in the schema but is handled by Odysseus's `EncryptedText` SQLAlchemy type decorator (Fernet encryption at rest). The encryption/decryption happens transparently at the ORM layer. **Do not store plaintext API keys.**

#### Reference Data Migration Path

The system tables (`event_types`, `phase_names`, `severity_levels`, `outcome_types`) are seeded at migration time. Long-term, migrate these to Python constants/enums to eliminate runtime dependency on DB config tables.

### 4.8 Retention Policies

| Table | TTL Column | Default TTL | Cleanup Mechanism |
|---|---|---|---|
| `chat_messages` | `sessions.expires_at` (via FK) | 90 days | Session-level TTL cascade |
| `audit_trail` | `expires_at` | 90 days | `VACUUM` on idle |
| `session_diary` | `expires_at` | 14 days | ArcPipeline vacuum |
| `raw_session_memories` | `expires_at` | 14 days | ArcPipeline vacuum |
| `consolidation_cache` | `expires_at` | Per-tier (7-60 days) | ArcPipeline vacuum |
| `task_runs` | (no TTL) | Indefinite | Manual archive |
| `artifacts` | (no TTL) | 90 days | `MemoryLayer.evict_old_artifacts()` |
| `memories` | `expires_at` | Per-tier | ArcPipeline vacuum |
| `knowledge_cards` | `expires_at` | Per-tier | ArcPipeline vacuum |

**Cleanup schedule:**
- **Daily:** ArcPipeline checks `expires_at` on memory/consolidation tables
- **Weekly:** `VACUUM` on `audit_trail` + `chat_messages` (via session cascade)
- **Monthly:** `MemoryLayer.evict_old_artifacts(retention_days=90)`

---

## 5. Schema Summary

### Table Count

| Category | Tables | Purpose |
|---|---|---|
| **Projects** | 1 | projects (+ projects_fts) |
| **Memory & Consolidation** | 4 | raw_session_memories, consolidation_cache, session_diary, memories |
| **Workflow & Execution** | 4 | pipelines, workflow_definitions, workflow_runs, artifacts |
| **Review & Audit** | 3 | review_findings, event_log, audit_trail |
| **Task Scheduling** | 2 | scheduled_tasks, task_runs |
| **Documents & Notes** | 2 | documents, notes |
| **Sessions & Chat** | 2 | sessions, chat_messages |
| **Agent Configuration** | 2 | crew_members, model_endpoints |
| **Calendar** | 2 | calendars, calendar_events |
| **Knowledge Bridge** | 4 | knowledge_cards, research_reports, work_items, projects (shared) |
| **System Reference** | 4 | event_types, phase_names, severity_levels, outcome_types |
| **Total** | **31** | |

> **Note:** `pipelines_archive` removed (soft-delete pattern). `consolidation_tiers` removed from count (seeded config, not data table). FTS5 virtual tables (`projects_fts`) are auxiliary, not counted separately.

### CodeGraph (Separate File: codegraph.db)

| Table | Rows | Purpose |
|---|---|---|
| cg_nodes | 94K | Functions, classes, methods, types |
| cg_edges | 257K | Call relationships, dependencies |
| cg_files | 5.7K | Source file index |
| cg_nodes_fts* | 94K | FTS5 full-text search |

**Not in council_core.db.** Accessed via `memory_service.cg_store` (CodeGraphStore).

---

## 6. Integration Flows

### 6.1 Memory Lifecycle

```
Conversation (Odysseus chat)
  ↓
MemoryExtractor (Odysseus, background)
  → extracts facts, preferences, decisions
  ↓
INSERT council_core.memories (source='conversation')
  → dedup via MemoryVectorStore.find_similar(text, threshold=0.92)
  ↓
ArcPipeline (Council, scheduled)
  → reads memories + raw_session_memories
  → produces consolidation_cache entries
  → tiers: daily → short → weekly → bimonthly
  ↓
ContextRouter (Council, on recall)
  → unified query across memories, consolidation_cache, session_diary
  → returns token-budgeted context slice
```

**Single DB benefit:** No cross-DB joins. ArcPipeline reads and writes the same file.

### 6.2 Research → Knowledge Card

```
User query (via Odysseus chat)
  ↓
DeepResearch (Odysseus)
  → LLM plans sub-questions
  → web_search via SearXNG (:8080)
  → iterates: search → extract → synthesize
  ↓
INSERT council_core.research_reports
  → query, summary, sections, sources, tokens, duration
  ↓
Auto-create knowledge card (if confidence ≥ threshold)
  → INSERT council_core.knowledge_cards
  → topic, summary, confidence, tags, sources
  → source_system='odysseus_research'
  ↓
INSERT council_core.audit_trail
  → table='knowledge_cards', action='create', source_system='odysseus'
  ↓
Unified Search Router indexes knowledge_card.topic + summary
```

### 6.3 Task Scheduling → Workflow Execution

```
Scheduled task fires (TaskScheduler, Odysseus)
  → cron or event trigger
  ↓
INSERT council_core.task_runs (status='queued')
  ↓
Agent loop executes (Odysseus)
  → tool calls, context management, model cycling
  ↓
UPDATE council_core.task_runs (status='running' → 'succeeded'/'failed')
  → result, tokens_used, steps, duration_ms
  ↓
If task creates work items:
  → INSERT council_core.work_items
  → INSERT council_core.audit_trail
  ↓
Event logged:
  → INSERT council_core.event_log
```

### 6.4 Review Lifecycle

```
Review started (Council ReviewService)
  ↓
INSERT council_core.event_log (event_type='review_start')
  ↓
Review findings logged
  → INSERT council_core.review_findings
  → run_id, severity, summary, fix, details
  ↓
Review verdict recorded
  → INSERT council_core.event_log (event_type='review_verdict')
  → metadata: {verdict: 'PASS'/'FAIL'/'PARTIAL', reason: ...}
  ↓
Findings visible to:
  → ContextRouter (structured recall)
  → MemoryLayer (context slices)
  → Pi extension (review_findings tool)
  → Unified Search Router (vector + keyword)
```

### 6.5 Arc → Odysseus Note-Making Flow

**Not AppFlowy/Affine sync.** This is a single-DB, single-process data transformation (YAML → note body). No network, no external API, no conflict resolution.

```
Arc Summarizer (Council, background)
  → 4 tiers produce YAML (decisions, work_completed, open_items, narrative, milestones)
  → INSERT session_diary (YAML as structured fields)
  → INSERT event_log (event_type='consolidation_completed', metadata={tier_id, output_yaml})
  ↓
TaskScheduler (Odysseus, event-triggered)
  → trigger: event='consolidation_completed', count=1 (fire immediately)
  → polls event_log for event_type='consolidation_completed' (new rows since last check)
  ↓
action_create_notes_from_consolidation (Odysseus builtin action)
  → parses YAML → formats markdown body
  → INSERT notes / documents with project_id from source session_diary
  ↓
User sees: "3 new notes from daily consolidation" in Odysseus UI
```

**Trigger mechanism (polling, not pub/sub):**
- TaskScheduler maintains a cursor: `last_consolidation_event_id`
- On each scheduled tick: `SELECT * FROM event_log WHERE event_type='consolidation_completed' AND event_id > ?`
- Processes new rows, advances cursor
- Polling interval: 60s (configurable)

**Tier → Note/Document Mapping:**

| Tier | YAML Output | Odysseus Artifact | Table | note_type |
|---|---|---|---|---|
| daily | summary, decisions, work_completed, open_items | Daily log note | `notes` | `text` |
| daily | open_items → checklist | Action items note | `notes` | `checklist` |
| short | narrative, work_threads, carried_forward | Work thread document | `documents` | — |
| weekly | theme, milestones, lessons_learned, risks | Weekly review document | `documents` | — |
| bimonthly | executive_summary, achievements, corrections | Strategic overview | `documents` | — |
| bimonthly | knowledge_base[] | Knowledge cards | `knowledge_cards` | — |

**Why this isn't AppFlowy integration:**

| Dimension | AppFlowy/Affine | Arc → Odysseus |
|---|---|---|
| Databases | 2 (PostgreSQL ↔ PostgreSQL) | 1 (SQLite) |
| Processes | 2+ (sync workers) | 1 (memory_service) |
| Network | REST API calls | None |
| Sync direction | Bidirectional | Unidirectional |
| Conflict resolution | Required | N/A (single writer) |
| Complexity | Full sync engine | SQL INSERT + formatting |

### 6.6 SearXNG Integration

```
Odysseus agent needs web info
  ↓
web_search tool (Odysseus)
  → HTTP GET http://127.0.0.1:8080/search?q=...
  → SearXNG returns: [{title, url, snippet}]
  ↓
Agent uses results for:
  → DeepResearch (iterative search rounds)
  → General knowledge queries
  → Tool execution context
  ↓
Results stored in:
  → research_reports.sources (structured)
  → task_runs.steps (execution trace)
```

**SearXNG is external.** No DB tables for search. It's an HTTP service on `:8080`.

---

## 7. Unified Search Architecture

> **Revised v3:** Embedding consolidation — one model (`pplx-embed-v1`), one vector store (Milvus-lite), one HTTP server (`:18099`). Replaces bge-m3, all-MiniLM, and ChromaDB.

### 7.1 Current State (Fragmented)

| Capability | Backend | Embedding Model | Status |
|---|---|---|---|
| Council memsearch | Milvus-lite (`~/.memsearch/milvus.db`) | `gpahal/bge-m3-onnx-int8` (ONNX) | ✅ Running → **replaced by pplx** |
| Odysseus memory vector | ChromaDB (`:8100`) | `all-MiniLM-L6-v2` (fastembed) | ❌ Not running → **replaced by pplx** |
| Odysseus RAG vector | ChromaDB (`:8100`) | HTTP API or fastembed | ❌ Not running → **replaced by pplx** |
| Artifact enrichment | ONNX direct | `pplx-embed-v1-0.6b-int8` | ⚠️ Model exists, server.py not running |
| CodeGraph search | FTS5 (`codegraph.db`) | N/A (keyword) | ✅ Running |
| Web search | SearXNG (`:8080`) | N/A (external) | ✅ Running |

**Problems:**
- Three embedding models on disk (bge-m3, all-MiniLM, pplx) — inconsistent scores, wasted RAM
- Two vector backends (Milvus + ChromaDB) — double storage, double maintenance
- No unified query interface — agents must know which backend to hit
- ChromaDB requires external service (`:8100`) — adds deployment complexity
- No hybrid search (vector + keyword combined)
- pplx model (best model) is only used for enrichment, not search

### 7.2 Target Architecture (Unified)

```
                    ┌──────────────────────────┐
                    │  pplx-embed-v1:18097      │
                    │  OpenAI-compatible HTTP   │
                    │  /v1/embeddings           │
                    │  ONNX INT8, CPU, 1024d    │
                    │  32K context window       │
                    └──────────┬───────────────┘
                               │
              ┌────────────────┼───────────────┐
              │                │               │
              ▼                ▼               ▼
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │ Vector Store  │ │ Enrichment   │ │ Keyword/     │
     │ (Milvus-lite) │ │ (MicroModel) │ │ FTS5         │
     │              │ │              │ │              │
     │ • memories   │ │ • artifact   │ │ • projects   │
     │ • knowledge  │ │   summary    │ │ • codegraph  │
     │ • documents  │ │ • failure    │ │ • event_log  │
     │ • notes      │ │   class      │ │ • artifacts  │
     │ • search     │ │ • dedup      │ │              │
     └──────────────┘ └──────────────┘ └──────────────┘
```

**Three clients, one model:**

| Client | Connection | Latency | Why |
|---|---|---|---|
| **Memsearch** | HTTP to `:18099` | ~50ms | Batch embeddings for search queries |
| **MicroModelEnricher** | Direct ONNX load | ~5ms | Async thread pool, no HTTP overhead |
| **Odysseus** | HTTP to `:18099` | ~50ms | Memory vector + RAG, same as Memsearch |

### 7.3 Embedding Server (pplx-embed-v1, Existing Code)

**No new code needed.** The pplx `server.py` already exists at `~/models/embedding/pplx-embed-v1-0.6b-int8/server.py`. It's an OpenAI-compatible HTTP server with `/v1/embeddings` and `/v1/models` endpoints.

**What needs to happen:**
1. Start `server.py` on port `:18099` (avoid conflict with memory-service SSE on `:18097`)
2. Add HTTP→ONNX fallback from Odysseus's `get_embedding_client()` pattern
3. Point Memsearch at `http://127.0.0.1:18099/v1/embeddings`
4. Point Odysseus at `http://127.0.0.1:18099/v1/embeddings` (set `EMBEDDING_URL`)

**Why pplx-embed-v1 over bge-m3:**
| Dimension | pplx-embed-v1-0.6b | bge-m3-onnx-int8 | all-MiniLM-L6-v2 |
|---|---|---|---|
| Architecture | Bidirectional (proper encoder) | Bidirectional | Transformer (CLS token) |
| Dimensions | 1024 | 1024 | 384 |
| Context window | 32K tokens | 8K tokens | 512 tokens |
| Multilingual | Yes (Qwen3 base) | Yes (100+ langs) | English only |
| Code-aware | Yes (Perplexity fine-tune) | Yes (trained on code) | No |
| ONNX INT8 | Yes | Yes | Yes |
| Model size | 688 MB | ~450 MB | ~80 MB |
| Training data | Web + code + multilingual | MS MARCO + NQ | Wiki + web |
| Bidirectional attn | ✅ 28 layers | ✅ | ✅ |

**Trade-off:** pplx is larger (688 MB vs 450 MB for bge-m3) but has 4x context window and Perplexity's fine-tuning on code + web data. For a system that indexes code, specs, and multilingual docs, the context window and fine-tuning matter more than raw size.

### 7.4 Unified Vector Store

**Single Milvus-lite collection replaces both ChromaDB and MemIndex.**

```python
# memory_service/vector_store.py
class UnifiedVectorStore:
    """Single vector store for all semantic search.

    Replaces:
    - ChromaDB (Odysseus memory vector + RAG) — removed
    - MemIndex (Council memsearch) — retained, unified

    Collection: unified_vectors
    Backend: Milvus-lite (~/.memsearch/milvus.db)
    Embedding: pplx-embed-v1 HTTP (:18099) or direct ONNX
    """

    COLLECTION_NAME = "unified_vectors"

    # Source types for routing and filtering
    SOURCES = ("memory", "knowledge_card", "document", "note", "artifact", "session_diary")

    def __init__(self, embedding_url: str = "http://127.0.0.1:18099"):
        self._embed_url = embedding_url
        self._client = None
        self._collection = None

    def index(self, source: str, source_id: str, text: str, metadata: Dict = None):
        """Index a text chunk into the unified vector store.

        Args:
            source: One of SOURCES (memory, knowledge_card, document, etc.)
            source_id: Primary key of the source record
            text: Text to embed and index
            metadata: Additional metadata (project_id, type, tags, etc.)
        """
        embeddings = self._embed.encode([text]).tolist()
        data = [{
            "source": source,
            "source_id": source_id,
            "text": text,
            "embedding": embeddings[0],
            **(metadata or {}),
        }]
        self._collection.upsert(data=data)

    def search(self, query: str, top_k: int = 10, filters: Dict = None) -> List[Dict]:
        """Search across all indexed sources.

        Args:
            query: Search query text
            top_k: Max results
            filters: Dict of field filters (source, project_id, type, etc.)

        Returns:
            List of {source, source_id, text, score, metadata}
        """
        embeddings = self._embed.encode([query]).tolist()
        results = self._collection.query(
            query_embeddings=embeddings,
            n_results=top_k,
            filter_expr=self._build_filter(filters),
        )
        return self._format_results(results)

    def dedup_check(self, text: str, threshold: float = 0.92) -> Optional[str]:
        """Check if a near-duplicate exists. Returns source_id if found.

        Replaces MemoryVectorStore.find_similar() from Odysseus.
        """
        embeddings = self._embed.encode([text]).tolist()
        results = self._collection.query(
            query_embeddings=embeddings,
            n_results=1,
        )
        if results and results["distances"][0][0] < (1.0 - threshold):
            return results["ids"][0][0]
        return None
```

**Migration from ChromaDB:**
- ChromaDB collections (`odysseus_memories`, `odysseus_rag`) → re-embed into Milvus-lite `unified_vectors`
- ChromaDB service (`:8100`) → removed, no longer needed
- Odysseus `MemoryVectorStore` → replaced by `UnifiedVectorStore.dedup_check()`
- Odysseus `VectorRAG` → replaced by `UnifiedVectorStore.search(source='document')`

### 7.5 Unified Search Router

**Single query interface for all search capabilities.**

```python
# memory_service/search_router.py
class UnifiedSearchRouter:
    """Unified search interface. Routes queries to appropriate backend.

    Usage:
        router = UnifiedSearchRouter()
        results = router.search("how does unified_recall work", project_id="super_council")

    Routing strategy:
    1. Vector search (Milvus-lite) — semantic similarity
    2. FTS5 search (SQLite) — keyword match
    3. Hybrid (RRF fusion) — combined ranking
    4. Web search (SearXNG) — external knowledge
    """

    def __init__(self, vector_store, db, codegraph_store):
        self._vector = vector_store
        self._db = db
        self._cg = codegraph_store

    def search(self, query: str, mode: str = "hybrid", **filters) -> Dict:
        """Search across all backends.

        Args:
            query: Search query text
            mode: 'vector', 'keyword', 'hybrid', 'web'
            **filters: project_id, type, source, severity, etc.

        Returns:
            Dict with results from each backend, fused if hybrid mode.
        """
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
        """Reciprocal Rank Fusion (RRF) to combine vector + keyword results.

        RRF score = 1 / (k + rank) where k=61 (standard constant).
        Higher score = better combined ranking.
        """
        k = 61
        scores: Dict[str, float] = {}  # source_id → combined score

        for backend_name, hits in backends.items():
            if not hits:
                continue
            for rank, hit in enumerate(hits, 1):
                sid = f"{backend_name}:{hit['source_id']}"
                scores[sid] = scores.get(sid, 0) + 1 / (k + rank)

        # Sort by combined score, deduplicate by source_id
        seen = set()
        fused = []
        for sid, score in sorted(scores.items(), key=lambda x: -x[1]):
            _, source_id = sid.split(":", 1)
            if source_id not in seen:
                fused.append({"source_id": source_id, "rrf_score": round(score, 4)})
                seen.add(source_id)
        return fused[:10]
```

### 7.6 FTS5 Indexes (Expanded)

```sql
-- Projects (Channel 4 of project resolution)
CREATE VIRTUAL TABLE projects_fts USING fts5(name, description, content='projects', content_rowid='rowid');

-- Knowledge cards (semantic + keyword search)
CREATE VIRTUAL TABLE knowledge_cards_fts USING fts5(topic, summary, content='knowledge_cards', content_rowid='rowid');

-- Documents (RAG-like keyword search)
CREATE VIRTUAL TABLE documents_fts USING fts5(title, content, content='documents', content_rowid='rowid');

-- Notes (keyword search)
CREATE VIRTUAL TABLE notes_fts USING fts5(title, body, content='notes', content_rowid='rowid');
```

### 7.7 Search Module Comparison (Before → After)

| Capability | Before (Fragmented) | After (Unified) |
|---|---|---|
| **Vector backend** | Milvus-lite + ChromaDB (2) | Milvus-lite (1) |
| **Embedding model** | bge-m3 + all-MiniLM + pplx (3) | pplx-embed-v1-0.6b (1) |
| **Embedding source** | Separate HTTP/ONNX per backend | pplx server.py (`:18099`) + direct ONNX |
| **Memory dedup** | ChromaDB MemoryVectorStore | UnifiedVectorStore.dedup_check() |
| **RAG search** | ChromaDB VectorRAG | UnifiedVectorStore.search(source='document') |
| **Council memsearch** | Milvus MemIndex (bge-m3) | Milvus MemIndex (pplx HTTP) |
| **Artifact enrichment** | MicroModelEnricher (pplx ONNX) | MicroModelEnricher (pplx ONNX, unchanged) |
| **Keyword search** | LIKE queries (ad-hoc) | FTS5 indexes (structured) |
| **Code search** | CodeGraphStore FTS5 | CodeGraphStore FTS5 (unchanged) |
| **Web search** | SearXNG (separate) | SearXNG (routed via SearchRouter) |
| **Hybrid search** | None | RRF fusion (vector + keyword) |
| **Query interface** | 5 separate APIs | 1 router (`router.search()`) |
| **ChromaDB dependency** | Required (`:8100`) | Removed |
| **Model disk usage** | ~1.2 GB (3 models) | 688 MB (1 model) |

### 7.8 Migration Path

1. **Phase 1 (start pplx server):** Run `server.py` on `:18099`. Add HTTP→ONNX fallback pattern from Odysseus's `get_embedding_client()`. Health check at `/health`.
2. **Phase 2 (point Memsearch at pplx):** Change `embedding_provider` from `"onnx"` (bge-m3 direct) → HTTP URL `http://127.0.0.1:18099/v1/embeddings`. Re-index existing 351 entities.
3. **Phase 3 (wire MicroModelEnricher into memory-service):** Currently only in `super_council.py`. Add to memory-service MCP server init. Uses direct ONNX load (low-latency async path).
4. **Phase 4 (point Odysseus at pplx):** Set `EMBEDDING_URL=http://127.0.0.1:18099/v1/embeddings` in Odysseus env. Drop all-MiniLM default.
5. **Phase 5 (cleanup):** Delete bge-m3 model files (~450 MB), delete all-MiniLM cache (~80 MB), remove ChromaDB from docker-compose + code.

---

## 8. Integration Flows (Updated)

### 8.1 Memory Lifecycle (with dedup)

```
Conversation (Odysseus chat)
  ↓
MemoryExtractor (Odysseus, background)
  → extracts facts, preferences, decisions
  ↓
Dedup check: UnifiedVectorStore.dedup_check(text, threshold=0.92)
  → if duplicate: skip INSERT, log warning
  ↓
INSERT council_core.memories (source='conversation')
  → index into UnifiedVectorStore (source='memory')
  ↓
ArcPipeline (Council, scheduled)
  → reads memories + raw_session_memories
  → produces consolidation_cache entries
  → tiers: daily → short → weekly → bimonthly
  ↓
ContextRouter (Council, on recall)
  → UnifiedSearchRouter.search(query, mode='hybrid')
  → returns token-budgeted context slice
```

### 8.2 Unified Recall Flow

```
recall.unified("how does X work")
  ↓
┌─────────────────────────────────────────────────────┐
│ Channel 1: Text Memory                              │
│   → UnifiedVectorStore.search(query, top_k=5)       │
│   → Session diary (DB query)                        │
│   → Consolidation cache (DB query)                  │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────┐
│ Channel 2: Structural Graph                         │
│   → CodeGraphStore.search(query, kind='function')   │
│   → Workflow definitions (if workflow query)        │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────┐
│ Channel 3: Execution History                        │
│   → ContextRouter.find_similar_runs(query)          │
│   → Recent events (DB query)                        │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────┐
│ Fusion: Token-budgeted context slice                │
│   → RRF fusion of vector + keyword results          │
│   → Token budget enforcement (max_tokens * 4 chars) │
│   → Artifact-aware (never cuts mid-artifact)        │
└─────────────────────────────────────────────────────┘
```

---

## 9. What Each Side Forgoes

### Odysseus stops:
- Independent memory persistence (feeds `council_core.memories` only)
- Separate database file (all data in `council_core.db`)
- Direct canonical writes (through Council RelationalStore)
- Research result storage (drafts → `council_core.research_reports` → `knowledge_cards`)
- **Independent vector backend (ChromaDB) — uses Milvus-lite UnifiedVectorStore**
- **Independent embedding model (all-MiniLM) — uses pplx-embed-v1 HTTP (:18099)

### Council stops:
- Aspirational PostgreSQL schemas (`council_core.*`, `council_ops.*`, `council_sync.*`)
- Rich conversational UX (Odysseus owns chat)
- Autonomous agent execution (delegates to Odysseus)
- Task scheduling (uses Odysseus TaskScheduler)
- Memory extraction (uses Odysseus MemoryExtractor)

### What stays simple:
- One SQLite file for business data
- One SQLite file for code graph
- One HTTP service for web search
- **One vector store (Milvus-lite) — replaces ChromaDB + MemIndex**
- **One embedding model (pplx-embed-v1-0.6b) — replaces bge-m3 + all-MiniLM**
- **One embedding server (:18099) — OpenAI-compatible HTTP**
- No connection pooling, no migration tooling, no user management
- WAL mode handles concurrency

---

## 10. Risks & Caveats

### High Risk
1. **Data migration from pipelines.db** — Must stop memory_service, copy DB, extract codegraph, add tables, restart. Any step failure leaves DB in inconsistent state. **Mitigation:** Keep `pipelines.db` as backup until verified. **Fixed migration script (§11.1).**
2. **ChromaDB removal** — Odysseus depends on ChromaDB for memory vector + RAG. Must re-embed all data into Milvus-lite before removing ChromaDB. **Mitigation:** ChromaDB not running — zero migration cost. Immediate removal.
3. **Odysseus ORM compatibility** — Odysseus uses SQLAlchemy with VARCHAR/DATETIME types. Harmonized schema uses TEXT. **Mitigation:** SQLAlchemy's String/DateTime map to SQLite TEXT transparently. Test each module independently.

### Medium Risk
4. **CodeGraphStore path change** — Currently shares `pipelines.db`. Moving to `codegraph.db` requires updating `CodeGraphStore.__init__()` to accept separate path. **Mitigation:** Parameterize path in MemoryService config.
5. **Concurrent access** — Odysseus and Council may write simultaneously. WAL mode handles reads, but write contention needs testing. **Mitigation:** busy_timeout = 5s, retry logic in RelationalStore.
6. **pplx model size** — 688 MB ONNX INT8 vs 80 MB for all-MiniLM. **Mitigation:** ONNX int8 quantization keeps CPU inference viable; HTTP server pattern allows remote fallback.

### Low Risk
7. **SearXNG availability** — External HTTP dependency. If `:8080` is down, web_search fails. **Mitigation:** Existing fallback in Odysseus LLM core.
8. **DB size growth** — `council_core.db` will grow with chat messages, memories, research reports. **Mitigation:** TTL-based expiry (§4.8), vacuum on idle.

---

## 11. Migration Plan (Fixed)

### 11.1 From pipelines.db → council_core.db

```bash
# Step 1: Stop memory_service
systemctl --user stop memory-service.service

# Step 2: Copy and rename
cp ~/.council-memory/pipelines.db ~/.council-memory/council_core.db

# Step 3: Extract codegraph tables to separate file
python3 -c "
import sqlite3, os

src = os.path.expanduser('~/.council-memory/council_core.db')
dst = os.path.expanduser('~/.council-memory/codegraph.db')

# Attach source, copy cg_* tables to new DB
dst_conn = sqlite3.connect(dst)
src_conn = sqlite3.connect(src)

# ATTACH with string formatting (NOT parameterized — SQLite bug)
dst_conn.execute('ATTACH DATABASE \"' + src + '\" AS src')

for table in ['cg_nodes', 'cg_edges', 'cg_files', 'cg_nodes_fts',
              'cg_nodes_fts_data', 'cg_nodes_fts_idx',
              'cg_nodes_fts_docsize', 'cg_nodes_fts_config']:
    # Create table structure
    dst_conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {table}
        AS SELECT * FROM src.{table} WHERE 0
    ''')
    # Copy data
    dst_conn.execute(f'INSERT INTO {table} SELECT * FROM src.{table}')

dst_conn.commit()
dst_conn.execute('DETACH DATABASE src')
dst_conn.close()
src_conn.close()
"

# Step 4: Drop cg_* tables from council_core.db
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.council-memory/council_core.db')
conn = sqlite3.connect(db)
for table in ['cg_nodes', 'cg_edges', 'cg_files', 'cg_nodes_fts',
              'cg_nodes_fts_data', 'cg_nodes_fts_idx',
              'cg_nodes_fts_docsize', 'cg_nodes_fts_config']:
    conn.execute(f'DROP TABLE IF EXISTS {table}')
conn.commit()
conn.close()
"

# Step 5: Create new tables (in dependency order)
# 5a. Projects first (FK anchor)
# 5b. Sessions (referenced by other tables)
# 5c. All other tables
# (run migration.sql script)

# Step 6: Add FTS5 indexes
# (run fts5_migration.sql script)

# Step 7: Update memory_service config
# Change _DEFAULT_DB_PATH to ~/.council-memory/council_core.db

# Step 8: Update CodeGraphStore to use ~/.council-memory/codegraph.db

# Step 9: Restart memory_service
systemctl --user start memory-service.service
```

> **Fix applied:** `ATTACH DATABASE` uses string formatting (`'ATTACH DATABASE \"' + src + '\" AS src'`) instead of parameterized `?` placeholder. SQLite's ATTACH does not accept parameterized paths.

### 11.2 Add Odysseus Tables

Migration script adds all Odysseus-harmonized tables and bridge tables to `council_core.db`. Data migration from `vendor/odysseus/data/app.db` is minimal (mostly empty tables).

**Migration SQL order (dependency-safe):**

```sql
-- 1. Projects (FK anchor — must be first)
CREATE TABLE projects (...);
CREATE VIRTUAL TABLE projects_fts USING fts5(...);

-- 2. Sessions (referenced by FKs in scheduled_tasks, memories, documents, notes, crew_members)
CREATE TABLE sessions (...);
CREATE TABLE chat_messages (...);

-- 3. Calendars (referenced by calendar_events)
CREATE TABLE calendars (...);
CREATE TABLE calendar_events (...);

-- 4. Knowledge bridge (referenced by work_items, research_reports)
CREATE TABLE knowledge_cards (...);
CREATE TABLE research_reports (...);

-- 5. Work items (references projects, pipelines, workflow_runs, research_reports, review_findings)
CREATE TABLE work_items (...);

-- 6. Scheduled tasks (references sessions)
CREATE TABLE scheduled_tasks (...);
CREATE TABLE task_runs (...);

-- 7. Memories (references sessions, projects)
CREATE TABLE memories (...);

-- 8. Documents (references sessions, projects)
CREATE TABLE documents (...);

-- 9. Notes (references sessions, projects)
CREATE TABLE notes (...);

-- 10. Agent config (references sessions)
CREATE TABLE crew_members (...);
CREATE TABLE model_endpoints (...);

-- 11. Audit trail (no FK deps)
CREATE TABLE audit_trail (...);

-- 12. FTS5 indexes
CREATE VIRTUAL TABLE knowledge_cards_fts USING fts5(...);
CREATE VIRTUAL TABLE documents_fts USING fts5(...);
CREATE VIRTUAL TABLE notes_fts USING fts5(...);

-- 13. Seed reference data
INSERT INTO event_types VALUES (...);
INSERT INTO phase_names VALUES (...);
INSERT INTO severity_levels VALUES (...);
INSERT INTO outcome_types VALUES (...);
INSERT INTO consolidation_tiers VALUES (...);
```

### 11.3 Update Connection Strings

| Component | Old | New |
|---|---|---|
| MemoryService (RelationalStore) | `~/.council-memory/pipelines.db` | `~/.council-memory/council_core.db` |
| MemoryService (CodeGraphStore) | `~/.council-memory/pipelines.db` | `~/.council-memory/codegraph.db` |
| Odysseus (all tables) | `vendor/odysseus/data/app.db` | `~/.council-memory/council_core.db` |
| SearXNG | `http://127.0.0.1:8080` | `http://127.0.0.1:8080` (unchanged) |
| **Vector Store** | **ChromaDB (`:8100`)** | **Milvus-lite (`~/.memsearch/milvus.db`)** |
| **Embedding** | **bge-m3 ONNX + all-MiniLM** | **pplx-embed-v1 HTTP (`:18099`)** |
| **MicroModelEnricher** | **pplx ONNX direct (super_council only)** | **pplx ONNX direct (memory-service too)** |

---

## 12. Decisions Needed

1. **Migration timing:** Do this now (pipelines.db has data) or after Odysseus wiring (minimal data, cleaner)?
2. **Odysseus ORM:** Keep SQLAlchemy layer or rewrite models for raw SQLite?
   - **Recommendation:** Keep SQLAlchemy. Its String/DateTime types map to SQLite TEXT transparently. The "harmonization" is mostly cosmetic.
3. **Backup strategy:** Keep `pipelines.db` alongside `council_core.db` during transition?
   - **Recommendation:** Yes, until full verification.
4. **Index strategy:** Add FTS5 to `knowledge_cards`, `documents`, `notes` or rely on vector search?
   - **Recommendation:** FTS5 + vector (hybrid). FTS5 for keyword precision, vector for semantic recall.
5. **SearXNG persistence:** Store search results in `research_reports.sources` or keep ephemeral?
6. **Embedding model:** ~~bge-m3-onnx-int8 vs all-MiniLM~~ → **DECIDED: pplx-embed-v1-0.6b** (bidirectional, 32K ctx, Perplexity fine-tune, ONNX INT8). Replaces both bge-m3 and all-MiniLM.
7. **ChromaDB removal:** Immediate cutover or parallel run?
   - **Recommendation:** Immediate — ChromaDB is not running. Zero migration cost.
8. **Embedding server port:** `:18099` (avoids memory-service SSE on `:18097`) or embed into memory-service?
   - **Recommendation:** `:18099` standalone. Simpler, no port conflict, easier to restart independently.
9. **MicroModelEnricher in memory-service:** Wire it into the MCP server or keep in super_council only?
   - **Recommendation:** Wire into memory-service. Enrichment is a core function that should be available via MCP tools.

---

## 13. Detailed System Comparison & Analysis

### 13.1 Context Management

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **Budget model** | `context_budget.py` — adaptive, model-aware | `get_context_slice()` — token-budgeted, artifact-aware | **Odysseus** |
| **Budget computation** | `compute_input_token_budget(configured, context_length, explicit)` — scales to model's window at 85% headroom | `max_tokens * 4` (chars-per-token estimate) — fixed multiplier | **Odysseus** |
| **Compaction trigger** | `COMPACT_THRESHOLD = 0.85` — at 85% of context window | Budget exceeded during slice assembly | **Tie** |
| **Compaction method** | LLM self-summarization (`SELF_SUMMARY_SYSTEM_PROMPT`) — structured, dense format | `_summarize_block()` — cached lookup or heuristic placeholder | **Odysseus** |
| **Tool message safety** | `_sanitize_tool_messages()` — drops orphaned tool messages | None (artifacts, not chat messages) | **Odysseus** |
| **Artifact awareness** | None — operates on chat messages | Never cuts mid-artifact, drops whole blocks until under budget | **Council** |
| **Eviction** | None — relies on compaction | `evict_old_artifacts(retention_days=90)` — TTL-based cleanup | **Council** |

**Analysis:** Odysseus's context management is built for long-running agent loops. Council's is built for structured workflow runs. **Odysseus should own context management; Council's artifact awareness grafted on.**

### 13.2 Unified Search (Revised v3)

| Dimension | Before (Fragmented) | After (Unified) |
|---|---|---|
| **Vector backends** | 2 (Milvus + ChromaDB) | 1 (Milvus-lite) |
| **Embedding models** | 3 (bge-m3 + all-MiniLM + pplx) | 1 (pplx-embed-v1-0.6b) |
| **Embedding server** | None (direct ONNX per client) | 1 HTTP server (`:18099`) + direct ONNX for enrichment |
| **Query interface** | 5 separate APIs | 1 router |
| **Hybrid search** | None | RRF fusion (vector + keyword) |
| **Keyword search** | LIKE queries | FTS5 indexes |
| **Dedup** | ChromaDB MemoryVectorStore | UnifiedVectorStore.dedup_check() |
| **Code search** | CodeGraphStore FTS5 | CodeGraphStore FTS5 (unchanged) |
| **Web search** | SearXNG (separate) | SearXNG (routed) |
| **Deployment** | ChromaDB service required | No external service (Milvus-lite embedded) |
| **Model disk usage** | ~1.2 GB (3 models) | 688 MB (1 model) |

**Analysis:** Unified search eliminates 2 dependencies (ChromaDB service, bge-m3 + all-MiniLM models), adds hybrid search capability, provides single query interface, and saves ~530 MB disk. **Net positive.**

### 13.3 Memory Injection

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **Injection point** | `_build_system_prompt()` | `unified_recall()` — three-channel | **Council** |
| **Injection format** | Raw memory text | Token-budgeted context slice | **Council** |
| **Project scoping** | None | `project_id` filter | **Council** |
| **Phase filtering** | None | `phase` filter | **Council** |
| **Type filtering** | None | `type_filter` (code/spec/doc/review) | **Council** |

**Analysis:** Council's injection is more structured and filterable. **Council owns injection.**

### 13.4 Memory Recall

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **Recall method** | ChromaDB cosine similarity | Three-channel recall | **Council** |
| **Vector backend** | ChromaDB (fastembed) | Milvus (MemIndex) | **Tie → Unified** |
| **Text channel** | Keyword search (Jaccard) | MemSearch vector + artifacts + event_log | **Council** |
| **Structural channel** | None | Workflow definitions, phase transitions | **Council** |
| **Execution channel** | None | Recent events, run snapshots | **Council** |
| **Consolidation** | Periodic audit (LLM dedup) | 4-tier ArcPipeline | **Council** |

**Analysis:** Council's three-channel recall is more comprehensive. **Council's recall structure + unified vector backend.**

### 13.5 Graph/Tree Features

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **Code graph** | None | `CodeGraphStore` — FTS5 + structural | **Council** |
| **Call graph** | None | `codegraph_callers()` / `codegraph_callees()` | **Council** |
| **Impact analysis** | None | `codegraph_impact()` — blast radius | **Council** |
| **Path tracing** | None | `codegraph_trace()` — call path | **Council** |

**Analysis:** Council exclusively owns code intelligence. **Council retains full ownership.**

### 13.6 Memory Extraction

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **Extraction trigger** | After each LLM response (automatic) | Manual entry only | **Odysseus** |
| **Extraction method** | LLM extracts facts from last N messages | None (manual upsert) | **Odysseus** |
| **Periodic audit** | `audit_memories()` — LLM dedup + rewrite | TTL-based expiry only | **Odysseus** |

**Analysis:** Odysseus exclusively owns extraction. **Odysseus retains full ownership; writes to Council's storage.**

### 13.7 Consolidation & Decay

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **Consolidation tiers** | None (flat memory) | 4 tiers (daily → short → weekly → bimonthly) | **Council** |
| **Consolidation model** | Periodic audit (LLM dedup) | Arc A380 (Granite-4.1-3B) | **Council** |
| **Decay windows** | None (manual expiry) | Tier-specific (7-60 days) | **Council** |
| **Scheduler** | None | `IdleWindowScheduler` — adaptive, CPU-aware | **Council** |

**Analysis:** Council exclusively owns consolidation. **Council retains full ownership.**

### 13.8 Integration Surface

| Dimension | Odysseus | Council | Winner |
|---|---|---|---|
| **MCP tools** | `manage_memory` (1 tool) | 12 tools (council-recall, etc.) | **Council** |
| **SSE transport** | None | Persistent SSE on :18097 | **Council** |
| **Health checks** | None | `/v1/memory/health` endpoint | **Council** |

**Analysis:** Council has more mature integration surface. **Council owns the integration layer.**

---

## 14. Options & Suggestions

### Suggestion 1: Odysseus Owns Context Management, Council Owns Storage

**Rationale:** Odysseus's `context_budget.py` + `context_compactor.py` are more sophisticated for agent loops. Council's `get_context_slice()` is better for artifact management.

**Result:** Model-aware budgeting + LLM compaction + artifact awareness + TTL eviction.

### Suggestion 2: Unified Search Router (This Spec)

**Rationale:** Fragmented search backends add complexity. Unified router provides single interface.

**Result:** 1 vector store, 1 embedding model, 1 query interface, 0 external services (ChromaDB removed).

### Suggestion 3: Council Recall Structure + Odysseus Extraction Engine

**Rationale:** Council's three-channel recall is more comprehensive. Odysseus's extraction is automatic and LLM-based.

**Result:** Automatic extraction + structured recall + tiered consolidation.

### Suggestion 4: Unified Skill System

**Rationale:** Odysseus extracts skills automatically. Council has no skill system.

**Result:** Automatic skill extraction + structured storage + filtered injection.

### Suggestion 5: Council CodeGraph + Odysseus Context Building

**Rationale:** Council has full code intelligence. Odysseus has better context building for agent loops.

**Result:** Code intelligence + adaptive compaction for large code contexts.

### Suggestion 6: Merge Consolidation Tiers with Odysseus Audit

**Rationale:** Council's 4-tier consolidation is comprehensive. Odysseus's periodic audit cleans duplicates.

**Result:** Tiered consolidation + duplicate cleanup + short-circuit optimization.

### Suggestion 7: Unified MCP Tool Surface

**Rationale:** Council has 12 MCP tools. Odysseus has 1 (`manage_memory`). Unified surface is better.

**Result:** Single tool surface, all features accessible via MCP protocol.

---

## 15. Next Steps

### Embedding Consolidation (Priority 1)
1. **Start pplx server.py on :18099** — existing code, just not running. Add to systemd or memory-service startup.
2. **Add HTTP→ONNX fallback** — borrow pattern from Odysseus's `get_embedding_client()` for resilience.
3. **Point Memsearch at pplx HTTP** — change `embedding_provider` from `"onnx"` (bge-m3) → HTTP URL.
4. **Wire MicroModelEnricher into memory-service** — currently only in `super_council.py`.
5. **Set Odysseus EMBEDDING_URL** — `http://127.0.0.1:18099/v1/embeddings`. Drop all-MiniLM default.
6. **Delete bge-m3 + all-MiniLM** — save ~530 MB disk.
7. **Remove ChromaDB** — from docker-compose + code. Not running, zero migration cost.

### Database Migration (Priority 2)
8. **Write migration.sql** — dependency-ordered CREATE TABLE statements
9. **Write fts5_migration.sql** — FTS5 index creation
10. **Implement UnifiedVectorStore** — replace ChromaDB + MemIndex
11. **Implement UnifiedSearchRouter** — single query interface with RRF fusion
12. **Update MemoryService config** — new DB paths, unified search config
13. **Integration test** — memory lifecycle, research → knowledge card, unified search
14. **Verify SearXNG wiring** — web_search tool through Odysseus → SearXNG :8080
15. **Delete pipelines.db** — only after full verification

---

## 16. Review Findings — Resolution Log

| # | Severity | Finding | Status | Resolution |
|---|---|---|---|---|
| 1 | Critical | Migration script `ATTACH DATABASE ?` won't run | ✅ Fixed | String formatting in §11.1 |
| 2 | Critical | Table count says 27, actual is 31 | ✅ Fixed | Corrected to 31 in §5 |
| 3 | High | `memories` vs `raw_session_memories` overlap | ✅ Clarified | Boundary rule + dedup in schema comments |
| 4 | High | `session_id` missing FK on 5 tables | ✅ Fixed | FK constraints added to all session_id columns |
| 5 | High | `work_items.related_review_id` has no FK | ✅ Fixed | `REFERENCES review_findings(finding_id)` added |
| 6 | High | Channel 5 vector similarity unimplementable | ✅ Fixed | Replaced with FTS5 keyword match (Channel 4) |
| 7 | Moderate | `pipelines_archive` duplicates `pipelines` | ✅ Fixed | Removed. Soft-delete pattern noted in §4.8 |
| 8 | Moderate | `audit_trail` will bloat | ✅ Fixed | Changed to changed-fields-only + `expires_at` (90d TTL) |
| 9 | Moderate | `chat_messages` has no TTL | ✅ Fixed | `sessions.expires_at` with cascade |
| 10 | Moderate | `projects` defined after FK-referencing tables | ✅ Fixed | Projects moved to §4.0 (first), migration order documented |
| 11 | Moderate | Decision 2 false dichotomy | ✅ Fixed | Recommendation: keep SQLAlchemy (String→TEXT transparent) |
| 12 | Low | Reference data as tables | ✅ Noted | §4.7 design note, migration path to Python constants |
| 13 | Low | API keys in plaintext | ✅ Fixed | `EncryptedText` type preserved, noted in §4.7 |
| 14 | Low | `owner_id` has no users table | ✅ Clarified | §4.7: username-based ownership, no FK |
| 15 | Low | Arc→Odysseus trigger has no mechanism | ✅ Fixed | Polling mechanism documented in §6.5 |
| 16 | High | Three embedding models on disk (bge-m3, all-MiniLM, pplx) | ✅ Fixed | Consolidated to pplx-embed-v1 (§3.4, §7.3) |
| 17 | High | `UnifiedEmbeddingService` class duplicates pplx `server.py` | ✅ Fixed | Use existing server.py, no new code (§7.3) |
| 18 | Moderate | MicroModelEnricher not wired into memory-service | ⚠️ Planned | Wire into MCP server init (§15, step 4) |
| 19 | Moderate | pplx server.py not running | ⚠️ Planned | Start on :18099, add to systemd (§15, step 1) |
| 20 | Moderate | Memsearch uses bge-m3 direct ONNX, not HTTP | ⚠️ Planned | Point at pplx HTTP :18099 (§15, step 3) |
| 21 | Low | ChromaDB not running — zero migration cost | ✅ Noted | Immediate removal, no parallel run needed (§12.7) |
| 22 | Low | bge-m3 model wastes ~450 MB disk | ✅ Fixed | Delete after Memsearch switch (§15, step 6) |

---

*This document supersedes the PostgreSQL-based schema design in earlier docs. The `council_core.*`, `council_ops.*`, `council_sync.*` PostgreSQL schemas are retired in favor of the unified SQLite approach.*

*Review: 22 findings total. 15 from initial review (v2), 7 from embedding consolidation review (v3). All verified against actual codebase (pipelines.db schema, Odysseus SQLAlchemy models, memory_service source, micro_model.py, pplx server.py).*
