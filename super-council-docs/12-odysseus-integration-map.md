# Odysseus → Council Integration Map

> **Date:** 2026-06-03
> **Status:** Mapping phase — codegraph indexed, requirements surfaced
> **Scope:** Integrate Odysseus capabilities into Council, replacing AppFlowy/Affine integration
> **Codebase:** `/home/chief/Coding-Projects/7-council/super_council/vendor/odysseus/` (5,703 files, 94K nodes indexed)

---

## 1. Why Odysseus (not AppFlowy/Affine)

**AppFlowy/Affine failed** because they are complex, opinionated workspace systems with undocumented internals, fragile REST APIs, and no clean integration surface. The integration required sync services, binding tables, outbox/inbox dispatchers, and conflict resolution — all for a visual editing surface.

**Odysseus is different:**
- It's a **Python-native, self-hosted AI workspace** — same language, same stack as Council
- It's already vendored inside `super_council/vendor/odysseus/` — no network boundary
- It has **clean Python modules** with explicit APIs, not HTTP-only REST endpoints
- It provides the **AI automation layer** (agent loop, task scheduler, research, memory) that Council needs
- It's designed for **single-user, local-first** operation — matches Council's deployment model

---

## 2. Odysseus Capability Inventory

### 2.1 AI Agent Loop (`src/agent_loop.py`)

**What it does:** Core agent execution engine with tool calling, context management, and model cycling.

**Key functions:**
- `stream_agent_loop()` — Main agent execution loop (line 1342). Handles tool calls, context compaction, model fallback, progress streaming
- `_run_tool()` — Tool execution with security sandboxing (line 2070)
- `_build_system_prompt()` — Dynamic system prompt construction (line 543)
- `_resolve_tool_blocks()` — Tool availability resolution (line 1063)
- `_run_verifier_subagent()` — Self-verification subagent (line 1268)

**Integration value:** This is the AI automation engine. Council can use it to execute tasks, run reviews, and perform autonomous operations without building a separate agent layer.

### 2.2 Task Scheduler (`src/task_scheduler.py`)

**What it does:** Cron-based and event-triggered task execution with serial concurrency control.

**Key features:**
- **Schedule types:** `daily`, `weekly`, `monthly`, `once`, `cron` (full cron expressions)
- **Event triggers:** `session_created`, `document_created`, `memory_added`, `research_completed`, `skill_added`
- **Built-in housekeeping tasks:**
  - `tidy_sessions` — Chat session cleanup (event: 5 sessions created)
  - `tidy_documents` — Document cleanup (event: 5 documents created)
  - `consolidate_memory` — Memory consolidation (event: 5 memories added)
  - `tidy_research` — Research report cleanup (event: research completed)
  - `summarize_emails` — Email summarization (cron: every 2h)
  - `draft_email_replies` — AI auto-reply drafting (cron: every 2h)
  - `extract_email_events` — Email → Calendar event extraction (cron: every 1h)
  - `classify_events` — Calendar event classification (cron: 6AM, 6PM)
  - `check_email_urgency` — Email urgency tagging (cron: every 1h)
  - `mark_email_boundaries` — Email thread boundary marking (cron: every 2h)
  - `audit_skills` — Skill audit (event: 5 skills added)
- **Serial execution:** Single semaphore, strict one-at-a-time execution
- **TTL caching:** Singleflight deduplication for shared fetches
- **Agent integration:** `_run_agent_loop()` — hands tasks to the AI agent for execution
- **Progress tracking:** Live progress updates persisted to DB
- **Abortion/cancellation:** User-stop support with DB state updates

**Integration value:** This is the **AI-operated task automation** system. Council can leverage this for automated workflows, scheduled consolidations, email triage, and event-driven operations.

### 2.3 Memory System (`services/memory/`)

**What it does:** Persistent memory storage with vector search and skill extraction.

**Components:**
- `MemoryManager` — JSON-based memory storage (`services/memory/memory.py`)
- `MemoryVectorStore` — ChromaDB vector search (`services/memory/memory_vector.py`)
- `MemoryExtractor` — LLM-based memory extraction from conversations (`services/memory/memory_extractor.py`)
- `SkillExtractor` — LLM-based skill extraction (`services/memory/skill_extractor.py`)
- `Skill` format — Structured skill definitions with frontmatter (`services/memory/skill_format.py`)

**Integration value:** Replaces/augments Council's memory layer. Provides semantic search, skill management, and automatic extraction from conversations.

### 2.4 Deep Research (`services/research/`, `src/deep_research.py`)

**What it does:** Multi-step research with LLM-in-the-loop source gathering, reading, and synthesis.

**Components:**
- `ResearchService` — High-level API (`services/research/service.py`)
- `ResearchHandler` — Core execution with progress callbacks (`services/research/research_handler.py`)
- `ResearchResult` — Structured output with sources, summary, sections
- Source extraction with relevance scoring
- Markdown report generation

**Integration value:** Council can use this for autonomous research tasks, knowledge card generation, and evidence gathering for reviews.

### 2.5 Built-in Actions (`src/builtin_actions.py`)

**What it does:** Pre-built AI actions for common operations.

**Key actions:**
- `action_classify_events` — Calendar event classification (line 570)
- `action_mark_email_boundaries` — Email thread boundary detection (line 763)
- `action_learn_sender_signatures` — Email signature learning (line 970)
- `action_test_skills` — Skill validation (line 1298)
- `action_check_email_urgency` — Email urgency tagging (line 1626)
- `_try_ai_tidy_group` — AI-based tidying (line 109)

**Integration value:** Ready-made AI operations that Council can trigger via task scheduler or directly.

### 2.6 MCP Integration (`src/mcp_manager.py`, `src/builtin_mcp.py`)

**What it does:** MCP (Model Context Protocol) server management and built-in MCP tools.

**Integration value:** Council already has MCP client/server (`mcp_client.py`, `mcp_server.py`). Odysseus MCP tools can be plugged in directly.

### 2.7 Documents (`services/docs/`)

**What it does:** Document processing, editing, and management.

**Integration value:** Note-taking and document editing surface for Council.

### 2.8 Email (`src/email_thread_parser.py`, CalDAV sync)

**What it does:** IMAP/SMTP email with AI triage, CalDAV calendar sync.

**Integration value:** Email integration for Council's inbox/operations.

### 2.9 LLM Core (`src/llm_core.py`)

**What it does:** Multi-provider LLM abstraction with fallback, streaming, concurrency control.

**Key features:**
- Provider support: vLLM, llama.cpp, Ollama, OpenRouter, OpenAI, Anthropic
- Concurrency control with rate limiting
- Streaming with SSE support
- Automatic fallback on errors
- Temperature/parameter management

**Integration value:** Council can use this as the LLM abstraction layer instead of building its own.

### 2.10 Context Management (`src/context_budget.py`, `src/context_compactor.py`)

**What it does:** Token-budgeted context management with automatic compaction.

**Integration value:** Essential for long-running agent sessions and memory recall.

---

## 3. Council Current State

### 3.1 Existing Modules

| Module | Purpose | Status |
|---|---|---|
| `api/core.py` | Council Core API (canonical write boundary) | Exists |
| `api/outbox_writer.py` | Transactional outbox writes | Exists |
| `api/revision.py` | Revision-based concurrency | Exists |
| `api/idempotency.py` | Idempotency key management | Exists |
| `api/field_policy.py` | Field-level editability | Exists |
| `api/dead_letter.py` | Dead letter inspection | Exists |
| `memory_service/` | Unified memory (RelationalStore, ContextRouter, MemoryLayer) | Exists |
| `context_router.py` | Context routing for recall | Exists |
| `memory_layer.py` | Three-channel memory layer | Exists |
| `arc_summarizer/` | Arc pipeline for consolidation | Exists |
| `code_graph/` | CodeGraph store and sync | Exists |
| `appflowy_sync.py` | AppFlowy sync (to be replaced) | Exists, deprecated |
| `council_appflowy_bridge.py` | AppFlowy bridge (to be replaced) | Exists, deprecated |
| `execution_queue.py` | Execution queue | Exists |
| `event_ingestion.py` | Event ingestion | Exists |
| `mcp_client.py` / `mcp_server.py` | MCP client/server | Exists |

### 3.2 What Council Has That Odysseus Doesn't

- **Revision-based concurrency control** (Council's `revision` column pattern)
- **Schema ownership model** (council_core, council_ops, council_sync)
- **Outbox/inbox dispatch pattern** (transactional event delivery)
- **Review lifecycle** (reviews, findings, verdicts)
- **Memory consolidation pipeline** (ArcPipeline, tiered rollups)
- **CodeGraph integration** (FTS5, structural graph)
- **RelationalStore** (canonical write boundary with migrations)

### 3.3 What Odysseus Has That Council Needs

- **AI agent loop** (autonomous task execution)
- **Task scheduler** (cron + event-driven automation)
- **Deep research** (multi-step research with synthesis)
- **Memory extraction** (LLM-based memory/skill extraction from conversations)
- **Built-in AI actions** (email triage, event classification, etc.)
- **LLM abstraction** (multi-provider with fallback)
- **Context management** (budget + compaction)
- **MCP tool ecosystem** (browser, shell, file tools)
- **Email/Calendar integration** (IMAP/SMTP, CalDAV)
- **Document editing** (multi-tab markdown editor)

---

## 4. Integration Architecture

### 4.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                     Council + Odysseus                       │
│                                                              │
│  ┌──────────────────────┐    ┌────────────────────────────┐ │
│  │   Council Core API   │    │   Odysseus Agent Layer     │ │
│  │                      │    │                            │ │
│  │  • Canonical writes  │◄──►│  • stream_agent_loop()    │ │
│  │  • Revision control  │    │  • _run_tool()             │ │
│  │  • Idempotency       │    │  • _build_system_prompt()  │ │
│  │  • Field policy      │    │  • _run_verifier_subagent()│ │
│  │  • Outbox dispatch   │    │                            │ │
│  └──────────┬───────────┘    └────────────┬───────────────┘ │
│             │                             │                  │
│             ▼                             ▼                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Task Automation Layer                      │ │
│  │                                                         │ │
│  │  TaskScheduler (Odysseus)                              │ │
│  │  • Cron schedules (daily/weekly/monthly/once/cron)     │ │
│  │  • Event triggers (session_created, memory_added, ...) │ │
│  │  • Housekeeping tasks (tidy, consolidate, summarize)   │ │
│  │  • Serial execution with semaphore                     │ │
│  │  • Agent handoff (_run_agent_loop)                     │ │
│  └────────────────────────┬──────────────────────────────┘ │
│                           │                                  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Memory & Knowledge Layer                    │ │
│  │                                                         │ │
│  │  Council: RelationalStore + ContextRouter + MemoryLayer │ │
│  │  Odysseus: MemoryManager + MemoryVectorStore            │ │
│  │          MemoryExtractor + SkillExtractor               │ │
│  │          Skill format (frontmatter + markdown)          │ │
│  └────────────────────────┬──────────────────────────────┘ │
│                           │                                  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Research & Notes Layer                      │ │
│  │                                                         │ │
│  │  Odysseus: ResearchService + ResearchHandler            │ │
│  │          Deep research with source extraction           │ │
│  │          Document processing (services/docs/)           │ │
│  │          Note-taking (markdown editor)                  │ │
│  └────────────────────────┬──────────────────────────────┘ │
│                           │                                  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              PostgreSQL (single instance)                │ │
│  │                                                         │ │
│  │  council_core.*   — canonical business entities         │ │
│  │  council_ops.*    — execution telemetry, audit, jobs    │ │
│  │  council_sync.*   — bindings, outbox, inbound           │ │
│  │  Odysseus tables  — tasks, runs, memory, documents      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ChromaDB — vector search (shared)                           │
│  CodeGraph SQLite — FTS5 (shared)                            │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Integration Points

#### IP-1: Agent Loop → Council Core API

**Problem:** Odysseus agent loop needs to write to Council-owned data.
**Solution:** Agent tools call Council Core API endpoints. Every write goes through revision control and idempotency.

**Implementation:**
- Odysseus `agent_tools` register Council API endpoints as MCP tools
- Tool calls include `X-Source-System: agent`, `X-Actor-Id`, `Idempotency-Key`
- Council API enforces field policy and revision checks

#### IP-2: Task Scheduler → Council Work Items

**Problem:** Odysseus tasks need to map to Council work items.
**Solution:** Task scheduler creates/updates Council work items via Core API.

**Implementation:**
- `TaskScheduler` creates `council_core.work_items` on task creation
- Task runs map to `council_core.workflow_runs`
- Task results stored in `council_ops.workflow_artifacts`
- Housekeeping tasks trigger Council memory consolidation

#### IP-3: Memory Unification

**Problem:** Two memory systems (Council RelationalStore + Odysseus MemoryManager).
**Solution:** Odysseus memory writes go through Council MemoryLayer. Vector store is shared.

**Implementation:**
- Odysseus `MemoryManager` writes to `council_core.memory_entries`
- `MemoryVectorStore` uses shared ChromaDB
- `MemoryExtractor` produces entries for Council consolidation pipeline
- `SkillExtractor` produces entries for `council_core.knowledge_cards`

#### IP-4: Research → Knowledge Cards

**Problem:** Research results need to become persistent knowledge.
**Solution:** ResearchService produces knowledge cards via Council Core API.

**Implementation:**
- `ResearchResult` → `council_core.knowledge_cards` on completion
- Sources stored in `metadata` JSONB
- Confidence derived from source relevance scores
- Tags extracted from topic/query

#### IP-5: Built-in Actions → Council Operations

**Problem:** Odysseus actions (email triage, event classification) need Council audit trail.
**Solution:** Actions log to `council_ops.system_events` and `council_ops.audit_events`.

**Implementation:**
- Each action execution creates audit event
- Results stored as workflow artifacts
- Errors routed to dead letter queue

---

## 5. Implementation Plan

### Phase 0: Foundation (Week 1-2)

**Goal:** Establish integration boundary and shared infrastructure.

- [ ] Remove AppFlowy sync code (`appflowy_sync.py`, `council_appflowy_bridge.py`)
- [ ] Add Odysseus task tables to `council_core` schema
- [ ] Wire Odysseus `TaskScheduler` to Council DB
- [ ] Create agent tool registry for Council Core API
- [ ] Establish shared ChromaDB connection

**Deliverables:**
- Schema migrations for task tables
- Agent tool definitions for Council API
- Odysseus-Council integration module

### Phase 1: Agent Loop Integration (Week 3-4)

**Goal:** Odysseus agent can execute tasks through Council Core API.

- [ ] Implement Council API tools in Odysseus agent
- [ ] Wire `stream_agent_loop()` to Council work items
- [ ] Implement revision-aware tool calls
- [ ] Add idempotency to agent mutations
- [ ] Test: agent creates/updates work items through Council API

**Deliverables:**
- Agent tool implementations
- Revision-aware mutation flow
- Integration tests

### Phase 2: Task Automation (Week 5-6)

**Goal:** Scheduled and event-driven tasks execute with AI automation.

- [ ] Map Odysseus housekeeping tasks to Council workflows
- [ ] Wire event triggers to Council event bus
- [ ] Implement `_run_agent_loop` handoff from TaskScheduler
- [ ] Add progress tracking to Council workflow runs
- [ ] Test: scheduled tasks execute, produce Council artifacts

**Deliverables:**
- Task-to-workflow mapping
- Event trigger integration
- Progress tracking

### Phase 3: Memory Unification (Week 7-8)

**Goal:** Single memory system with extraction and vector search.

- [ ] Odysseus MemoryManager writes to `council_core.memory_entries`
- [ ] MemoryExtractor produces entries for ArcPipeline
- [ ] SkillExtractor produces knowledge cards
- [ ] Shared ChromaDB for vector search
- [ ] Test: memory round-trip, skill extraction, vector recall

**Deliverables:**
- Unified memory layer
- Extraction pipelines
- Vector search integration

### Phase 4: Research Integration (Week 9-10)

**Goal:** Deep research produces knowledge cards and reports.

- [ ] ResearchService integrates with Council Core API
- [ ] Research results → knowledge cards automatically
- [ ] Source extraction and relevance scoring
- [ ] Progress streaming to Council workflow runs
- [ ] Test: research → knowledge card round-trip

**Deliverables:**
- Research integration module
- Knowledge card generation
- Source management

### Phase 5: Notes & Documents (Week 11-12)

**Goal:** Note-taking and document editing surface.

- [ ] Document service integration with Council
- [ ] Note storage in `council_core` schema
- [ ] Markdown editor with AI assistance
- [ ] Document search via CodeGraph + ChromaDB
- [ ] Test: create/edit/search documents

**Deliverables:**
- Document integration
- Note-taking surface
- AI-assisted editing

### Phase 6: Hardening (Week 13-14)

**Goal:** Production readiness.

- [ ] Remove all AppFlowy references
- [ ] Audit trail for all agent operations
- [ ] Dead letter inspection for failed tasks
- [ ] Restart safety for task scheduler
- [ ] Performance testing
- [ ] Security review of agent tool sandboxing

**Deliverables:**
- Clean codebase (no AppFlowy)
- Operational dashboards
- Security audit

---

## 6. Schema Additions

### 6.1 Task Tables (new in `council_core`)

```sql
-- Scheduled tasks (from Odysseus TaskScheduler)
CREATE TABLE council_core.scheduled_tasks (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    name TEXT NOT NULL,
    action TEXT NOT NULL,  -- 'tidy_sessions', 'consolidate_memory', etc.
    schedule TEXT CHECK (schedule IN ('daily','weekly','monthly','once','cron')),
    scheduled_time TEXT,  -- HH:MM for daily/weekly/monthly
    scheduled_day INTEGER,  -- 0-6 for weekly
    scheduled_date TIMESTAMPTZ,  -- for 'once'
    cron_expression TEXT,  -- for 'cron'
    timezone TEXT,  -- IANA timezone
    trigger_type TEXT CHECK (trigger_type IN ('schedule','event')),
    trigger_event TEXT,  -- 'session_created', 'memory_added', etc.
    trigger_count INTEGER,  -- fire after N events
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    is_builtin BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);

-- Task runs (maps to Odysseus TaskRun)
CREATE TABLE council_core.task_runs (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES council_core.scheduled_tasks(id),
    work_item_id UUID REFERENCES council_core.work_items(id),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','succeeded','failed','aborted','dead_letter')),
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    duration_ms DOUBLE PRECISION NULL,
    result TEXT NULL,  -- live progress or final result
    error TEXT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_runs_status ON council_core.task_runs(status);
CREATE INDEX idx_task_runs_task ON council_core.task_runs(task_id);
```

### 6.2 Research Tables (new in `council_core`)

```sql
CREATE TABLE council_core.research_reports (
    id UUID PRIMARY KEY,
    work_item_id UUID REFERENCES council_core.work_items(id),
    query TEXT NOT NULL,
    summary TEXT NOT NULL,
    sections TEXT[] NOT NULL DEFAULT '{}',
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{url, title, snippet, relevance}]
    tokens_used INTEGER NOT NULL DEFAULT 0,
    duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    knowledge_card_id UUID REFERENCES council_core.knowledge_cards(id),
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
```

### 6.3 Notes Tables (new in `council_core`)

```sql
CREATE TABLE council_core.notes (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,  -- markdown
    tags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_notes_tags ON council_core.notes USING GIN(tags);
```

---

## 7. Key Files Reference

### Odysseus (vendor/odysseus/)

| File | Purpose | Lines |
|---|---|---|
| `src/agent_loop.py` | Core agent execution loop | ~2100 |
| `src/task_scheduler.py` | Task scheduling and execution | ~2400 |
| `src/builtin_actions.py` | Built-in AI actions | ~1700 |
| `src/llm_core.py` | LLM abstraction with fallback | ~1500 |
| `src/context_budget.py` | Token budget management | ~300 |
| `src/context_compactor.py` | Context compaction | ~400 |
| `src/memory.py` | Memory management | ~500 |
| `src/memory_vector.py` | Vector memory store | ~400 |
| `services/memory/memory.py` | Memory service | ~200 |
| `services/memory/memory_extractor.py` | Memory extraction | ~300 |
| `services/memory/skill_extractor.py` | Skill extraction | ~300 |
| `services/memory/skill_format.py` | Skill format (frontmatter) | ~450 |
| `services/research/service.py` | Research service | ~170 |
| `services/research/research_handler.py` | Research execution | ~500 |
| `src/deep_research.py` | Deep research core | ~800 |
| `src/mcp_manager.py` | MCP server management | ~400 |
| `src/builtin_mcp.py` | Built-in MCP tools | ~300 |
| `src/agent_tools.py` | Agent tool definitions | ~600 |
| `src/tool_execution.py` | Tool execution engine | ~400 |
| `src/tool_security.py` | Tool security sandboxing | ~300 |
| `services/docs/service.py` | Document service | ~200 |
| `src/document_processor.py` | Document processing | ~400 |
| `src/email_thread_parser.py` | Email thread parsing | ~300 |
| `src/caldav_sync.py` | CalDAV calendar sync | ~400 |
| `src/topic_analyzer.py` | Topic analysis | ~200 |
| `src/research_utils.py` | Research utilities | ~300 |

### Council (super_council/)

| File | Purpose |
|---|---|
| `api/core.py` | Council Core API |
| `api/outbox_writer.py` | Transactional outbox |
| `api/revision.py` | Revision control |
| `api/idempotency.py` | Idempotency keys |
| `api/field_policy.py` | Field editability |
| `memory_service/` | Unified memory service |
| `arc_summarizer/` | Arc consolidation pipeline |
| `code_graph/` | CodeGraph integration |
| `execution_queue.py` | Execution queue |
| `event_ingestion.py` | Event ingestion |

---

## 8. Risks & Caveats

### 8.1 High Risk

1. **Database schema conflict:** Odysseus uses SQLite (`data/app.db`) while Council uses PostgreSQL. Need to migrate Odysseus tables to PostgreSQL with Council's schema conventions.
2. **Agent security:** Odysseus agent has shell/file access. Must enforce Council's security model (field policy, revision control) on all agent mutations.
3. **Concurrency model:** Odysseus uses serial execution (semaphore). Council may need parallel execution for some workflows.

### 8.2 Medium Risk

4. **Memory model mismatch:** Odysseus uses JSON files + ChromaDB. Council uses RelationalStore + Milvus. Need unified storage layer.
5. **Odysseus version lock:** Vendored Odysseus is at a specific commit. Upstream changes may break integration. Need to track upstream or fork.
6. **Test coverage:** Odysseus has 300+ tests but they test Odysseus in isolation. Integration tests for Council+Odysseus don't exist yet.

### 8.3 Low Risk

7. **Configuration overlap:** Both systems have settings/preferences. Need unified configuration.
8. **Logging overlap:** Both have logging systems. Need consistent log format.
9. **Static assets:** Odysseus has a web UI. Council may or may not want to integrate the UI.

---

## 9. Decisions Needed

1. **Odysseus as vendor vs. fork:** Keep vendored (simpler, harder to update) or fork (more control, more maintenance)?
2. **Database strategy:** Migrate Odysseus tables to Council PostgreSQL or keep separate SQLite with bridge layer?
3. **UI strategy:** Use Odysseus web UI as Council's frontend, build separate UI, or hybrid?
4. **Memory unification:** Replace Council's RelationalStore memory with Odysseus's, or merge both?
5. **Agent scope:** Full agent access (shell, files, MCP) or restricted to Council API tools only?
6. **Email/Calendar:** Integrate Odysseus's email/Calendar directly or keep as separate services?

---

## 10. Next Steps

1. **Decision on integration strategy** (items in §9)
2. **Schema migrations** for task/research/notes tables
3. **Remove AppFlowy code** (cleanup)
4. **Build agent tool bridge** (Odysseus → Council Core API)
5. **Wire TaskScheduler to Council DB**
6. **Integration tests** for each phase

---

*This document replaces the AppFlowy integration approach. The odyssey integration doc (`12-odseey-integration.md`) should be updated or archived once this integration path is confirmed.*
