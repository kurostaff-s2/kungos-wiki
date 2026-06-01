# AppFlowy Self-Host + Council Unification Plan

> **Date:** 2026-06-01
> **Scope:** Same-machine AppFlowy deployment + full council refactor + complete feature synthesis
> **Policy:** No backward compatibility. SQLite DB erased. Fresh start.
> **References:** [appflowy-integration-analysis.md](appflowy-integration-analysis.md), [01-overview.md](01-overview.md), [08-arc-summarizer.md](08-arc-summarizer.md)

---

## Executive Summary

**Single PostgreSQL instance** hosts both council domain tables and AppFlowy schemas. `CouncilDatabase` (SQLAlchemy ORM) replaces RelationalStore + ContextRouter + ReviewService + MemoryLayer. AppFlowy provides the visual management layer (documents, databases, boards, calendar views). No sync adapter — council writes to PostgreSQL, AppFlowy reads from PostgreSQL, one source of truth.

### What Changes

| Component | Before (SQLite) | After (PostgreSQL + AppFlowy) | Status |
|-----------|----------------|------------------------------|--------|
| RelationalStore | SQLite CRUD, raw SQL | CouncilDatabase.pipelines (domain methods) | REPLACE |
| ContextRouter | Raw SQL queries | CouncilDatabase.recall (SQLAlchemy) | REPLACE |
| ReviewService | Fake pipelines | CouncilDatabase.reviews (native tables) | REPLACE |
| MemoryLayer | Token-budgeted slicing | CouncilDatabase.recall + AppFlowy documents | REPLACE |
| CouncilMemory | Markdown files | EventLog table + AppFlowy documents | REPLACE |
| Arc Summarizer | Writes to SQLite | Writes to PostgreSQL + AppFlowy documents | INTEGRATE |
| MemIndex | Milvus-lite (unchanged) | Milvus-lite + pgvector bridge | EXTEND |
| CodeGraph | SQLite FTS5 (unchanged) | SQLite FTS5 (stays separate) | KEEP |
| AppFlowy | Not deployed | docker-compose, same machine | NEW |

### What Stays Separate

| Component | Backend | Reason |
|-----------|---------|--------|
| CodeGraph (`codegraph.db`) | SQLite FTS5 | FTS5 is SQLite-native; pg_trgm is different |
| MemIndex (Milvus) | Milvus-lite | Vector search, not relational |
| AppFlowy auth | PostgreSQL (`auth` schema) | GoTrue managed, untouched |
| AppFlowy tables | PostgreSQL (`appflowy_public`) | AppFlowy managed, council reads only |

### AI Strategy: Arc Summarizer First

**Initial approach:** Point AppFlowy AI directly at Arc Summarizer (port 18095) via Azure OpenAI-compatible endpoint. No proxy, no cloud API keys.

**Verified:** Both endpoints support OpenAI API (`/v1/chat/completions`):
- `http://127.0.0.1:18095/v1/chat/completions` — Arc Summarizer (Granite-4.1-3B on Arc A380)
- `http://127.0.0.1:8091/v1/chat/completions` — Main llama.cpp (Qwen3.6-27B on RTX 3090)

**Fallback path (if Arc performance is insufficient):**
1. Add lightweight AI proxy (port 8099) — routes summarization to Arc, chat to main LLM
2. Or switch to cloud provider (OpenAI/Azure) for specific use cases

**Codebase verification:**
- `AppFlowy-Cloud/libs/indexer/src/vector/embedder.rs:57` — `AI_AZURE_OPENAI_API_BASE` supported
- `arc_summarizer/client.py:193` — uses `/v1/chat/completions` (OpenAI-compatible)
- `arc_summarizer/config.py:26` — `server_url: http://127.0.0.1:18095`

---

## Phase 0: AppFlowy Deployment

### docker-compose Configuration

Same-machine deployment. Port conflicts resolved (5432 → 5433 for AppFlowy's PostgreSQL).

```yaml
# /home/chief/appflowy/docker-compose.yml
# AppFlowy Cloud - Self-hosted deployment for council integration

services:
  nginx:
    restart: on-failure
    image: nginx
    ports:
      - "8080:80"
      - "8443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf

  minio:
    restart: on-failure
    image: minio/minio
    environment:
      - MINIO_BROWSER_REDIRECT_URL=http://localhost:8080/minio
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-appflowy}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-appflowy_pass}
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    volumes:
      - minio_data:/data

  postgres:
    restart: on-failure
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-postgres}
      - POSTGRES_DB=${POSTGRES_DB:-appflowy}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-appflowy_pass}
    command: ["postgres", "-c", "port=5432"]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres", "-d", "appflowy", "-p", "5432"]
      interval: 5s
      timeout: 5s
      retries: 12
    volumes:
      - appflowy_pg_data:/var/lib/postgresql/data
    # Internal port 5432, no external mapping (council connects via Docker network)

  redis:
    restart: on-failure
    image: redis

  gotrue:
    restart: on-failure
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: "curl --fail http://127.0.0.1:9999/health || exit 1"
      interval: 5s
      timeout: 5s
      retries: 12
      start_period: 40s
    image: appflowyinc/gotrue:latest
    environment:
      - GOTRUE_ADMIN_EMAIL=${GOTRUE_ADMIN_EMAIL:-admin@council.local}
      - GOTRUE_ADMIN_PASSWORD=${GOTRUE_ADMIN_PASSWORD:-council_admin}
      - GOTRUE_DISABLE_SIGNUP=true
      - GOTRUE_SITE_URL=appflowy-flutter://
      - GOTRUE_URI_ALLOW_LIST=**
      - GOTRUE_JWT_SECRET=${GOTRUE_JWT_SECRET:-council_jwt_secret}
      - GOTRUE_JWT_EXP=604800
      - GOTRUE_JWT_ADMIN_GROUP_NAME=supabase_admin
      - GOTRUE_DB_DRIVER=postgres
      - API_EXTERNAL_URL=http://localhost:8080/gotrue
      - DATABASE_URL=postgres://postgres:appflowy_pass@postgres:5432/appflowy?search_path=auth
      - PORT=9999
      - GOTRUE_MAILER_AUTOCONFIRM=true

  appflowy_cloud:
    restart: on-failure
    environment:
      - RUST_LOG=info
      - APPFLOWY_ENVIRONMENT=production
      - APPFLOWY_DATABASE_URL=postgres://postgres:appflowy_pass@postgres:5432/appflowy
      - APPFLOWY_REDIS_URI=redis://redis:6379
      - APPFLOWY_GOTRUE_JWT_SECRET=${GOTRUE_JWT_SECRET:-council_jwt_secret}
      - APPFLOWY_GOTRUE_BASE_URL=http://gotrue:9999
      - APPFLOWY_S3_CREATE_BUCKET=true
      - APPFLOWY_S3_USE_MINIO=true
      - APPFLOWY_S3_MINIO_URL=http://minio:9000
      - APPFLOWY_S3_ACCESS_KEY=${MINIO_ROOT_USER:-appflowy}
      - APPFLOWY_S3_SECRET_KEY=${MINIO_ROOT_PASSWORD:-appflowy_pass}
      - APPFLOWY_S3_BUCKET=appflowy
      - APPFLOWY_ACCESS_CONTROL=false
      - APPFLOWY_DATABASE_MAX_CONNECTIONS=20
      - APPFLOWY_BASE_URL=http://localhost:8080
      - APPFLOWY_WEB_URL=http://localhost:8080
      - AI_ENABLED=true
      - AI_AZURE_OPENAI_API_KEY=local
      - AI_AZURE_OPENAI_API_BASE=http://host.docker.internal:18095/v1
      - AI_AZURE_OPENAI_API_VERSION=2024-02-01
      - DEFAULT_AI_MODEL=granite-4.1-3b
      - DEFAULT_AI_COMPLETION_MODEL=granite-4.1-3b
    image: appflowyinc/appflowy_cloud:latest
    healthcheck:
      test: "curl --fail http://127.0.0.1:8000/api/health || exit 1"
      interval: 5s
      timeout: 5s
      retries: 12
    depends_on:
      gotrue:
        condition: service_healthy

  appflowy_worker:
    restart: on-failure
    image: appflowyinc/appflowy_worker:latest
    environment:
      - RUST_LOG=info
      - APPFLOWY_ENVIRONMENT=production
      - APPFLOWY_WORKER_REDIS_URL=redis://redis:6379
      - APPFLOWY_WORKER_ENVIRONMENT=production
      - APPFLOWY_WORKER_DATABASE_URL=postgres://postgres:appflowy_pass@postgres:5432/appflowy
      - APPFLOWY_WORKER_DATABASE_NAME=appflowy
      - APPFLOWY_S3_USE_MINIO=true
      - APPFLOWY_S3_MINIO_URL=http://minio:9000
      - APPFLOWY_S3_ACCESS_KEY=${MINIO_ROOT_USER:-appflowy}
      - APPFLOWY_S3_SECRET_KEY=${MINIO_ROOT_PASSWORD:-appflowy_pass}
      - APPFLOWY_S3_BUCKET=appflowy
    depends_on:
      postgres:
        condition: service_healthy
      appflowy_cloud:
        condition: service_healthy

  appflowy_search:
    restart: on-failure
    image: appflowyinc/appflowy_search:latest
    environment:
      - RUST_LOG=info
      - APPFLOWY_SEARCH_HOST=[::]
      - APPFLOWY_SEARCH_PORT=4002
      - APPFLOWY_SEARCH_DATABASE_URL=postgres://postgres:appflowy_pass@postgres:5432/appflowy
      - APPFLOWY_SEARCH_REDIS_URL=redis://redis:6379
      - APPFLOWY_S3_USE_MINIO=true
      - APPFLOWY_S3_MINIO_URL=http://minio:9000
      - APPFLOWY_S3_ACCESS_KEY=${MINIO_ROOT_USER:-appflowy}
      - APPFLOWY_S3_SECRET_KEY=${MINIO_ROOT_PASSWORD:-appflowy_pass}
      - APPFLOWY_S3_BUCKET=appflowy
      - APPFLOWY_BACKGROUND_INDEXER_ENABLED=true
      - APPFLOWY_KEYWORD_SEARCH_ENABLED=true
      - APPFLOWY_KEYWORD_WORKER_ENABLED=true
      - APPFLOWY_KEYWORD_INDEX_MAP_SIZE_BYTES=2147483648
      - APPFLOWY_KEYWORD_INDEX_DIR=/var/lib/appflowy/keyword_index
      - APPFLOWY_GOTRUE_JWT_SECRET=${GOTRUE_JWT_SECRET:-council_jwt_secret}
    volumes:
      - keyword_index_data:/var/lib/appflowy/keyword_index
    depends_on:
      postgres:
        condition: service_healthy

  appflowy_web:
    restart: on-failure
    image: appflowyinc/appflowy_web:latest
    depends_on:
      appflowy_cloud:
        condition: service_healthy
    environment:
      - APPFLOWY_BASE_URL=http://localhost:8080
      - APPFLOWY_GOTRUE_BASE_URL=http://localhost:8080/gotrue
      - APPFLOWY_WS_BASE_URL=ws://localhost:8080/ws/v2

volumes:
  appflowy_pg_data:
  minio_data:
  keyword_index_data:
```

### Environment File

```bash
# /home/chief/appflowy/.env
FQDN=localhost
SCHEME=http
WS_SCHEME=ws
APPFLOWY_BASE_URL=http://localhost:8080
APPFLOWY_WEBSOCKET_BASE_URL=ws://localhost:8080/ws/v2

# PostgreSQL (internal, port 5432 on Docker network)
POSTGRES_USER=postgres
POSTGRES_DB=appflowy
POSTGRES_PASSWORD=appflowy_pass

# Redis (internal)
REDIS_HOST=redis
REDIS_PORT=6379

# MinIO (internal)
MINIO_HOST=minio
MINIO_PORT=9000
MINIO_ROOT_USER=appflowy
MINIO_ROOT_PASSWORD=appflowy_pass
AWS_ACCESS_KEY=appflowy
AWS_SECRET=appflowy_pass

# GoTrue
GOTRUE_ADMIN_EMAIL=admin@council.local
GOTRUE_ADMIN_PASSWORD=council_admin
GOTRUE_JWT_SECRET=council_jwt_secret_change_me
GOTRUE_MAILER_AUTOCONFIRM=true
GOTRUE_DISABLE_SIGNUP=true

# AI Configuration — Arc Summarizer (Granite-4.1-3B on Arc A380)
# Routes AppFlowy AI requests to Arc Summarizer via Azure OpenAI-compatible endpoint
AI_ENABLED=true
AI_AZURE_OPENAI_API_KEY=local
AI_AZURE_OPENAI_API_BASE=http://host.docker.internal:18095/v1
AI_AZURE_OPENAI_API_VERSION=2024-02-01
DEFAULT_AI_MODEL=granite-4.1-3b
DEFAULT_AI_COMPLETION_MODEL=granite-4.1-3b

# Future: If Arc performance is insufficient, switch to proxy or cloud provider
# AI_AZURE_OPENAI_API_BASE=http://localhost:8099/v1  # AI Proxy (routes to Arc or main LLM)
```

### Resource Budget

| Resource | AppFlowy Stack | Existing Usage | Total | Available |
|----------|---------------|----------------|-------|-----------|
| RAM | ~4GB | ~16GB | ~20GB | 93GB |
| Disk (images) | ~10GB | ~2GB | ~12GB | 165GB free |
| Disk (data) | ~5GB (grows) | ~550MB | ~5.5GB | 165GB free |
| CPU cores | 2-4 virtual | 4-6 active | 6-8 | 16 threads |
| Ports | 8080, 8443 | 27017, 7700, 8090, 8091, 18095 | — | Clean |

### Deployment Steps

```bash
# 1. Create directory
mkdir -p /home/chief/appflowy/nginx/ssl
cd /home/chief/appflowy

# 2. Write docker-compose.yml + .env (above)

# 3. Write nginx config (minimal, no TLS for local)
cat > nginx/nginx.conf << 'EOF'
events { worker_connections 1024; }
http {
    upstream appflowy { server appflowy_cloud:8000; }
    upstream gotrue { server gotrue:9999; }
    upstream minio { server minio:9000; }
    upstream minio_console { server minio:9001; }
    upstream web { server appflowy_web:3000; }

    server {
        listen 80;
        location /api/ { proxy_pass http://appflowy; proxy_read_timeout 300s; }
        location /workspace/ { proxy_pass http://appflowy; }
        location /gotrue/ { proxy_pass http://gotrue; }
        location /minio/ { proxy_pass http://minio; }
        location /minio-api/ { proxy_pass http://minio; }
        location /ws/ { proxy_pass http://appflowy; proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }
        location / { proxy_pass http://web; }
    }
}
EOF

# 4. Deploy
docker compose up -d

# 5. Verify
curl -s http://localhost:8080/api/health
```

---

## Features That Won't Work (With Current Plan)

### Architecture Conflict (Plan Explicitly Excludes)

| # | AppFlowy Feature | Why It Won't Work | Plan Decision |
|---|-----------------|-------------------|---------------|
| 1 | **AI Chat Chains** (ConversationalRetrieverChain, RelatedQuestionChain, ContextQuestionChain) | Uses AppFlowy's built-in AI service which points to Arc Summarizer. Council owns AI pipeline via ArcClient. | Council owns AI. AppFlowy AI is a passthrough to Granite-4.1-3B |
| 2 | **AI Summary Memory** | Requires AppFlowy AI service running with its own memory layer | Council uses Arc Summarizer's consolidation tiers |
| 3 | **AI Multi-Source Retriever** | Requires AppFlowy AI + SQLite vector backend | Council uses Milvus (MemIndex), not AppFlowy's SQLite vec |
| 4 | **AI Local Completion** | Requires AppFlowy AI service | Council uses Arc Summarizer for completion |
| 5 | **Custom Prompts** (AppFlowy AI database prompts) | Requires AppFlowy AI service | Council has its own PromptService |
| 6 | **SQLite Vector** (`flowy-sqlite-vec`) | Plan uses PostgreSQL pgvector, not SQLite vec | Different vector backend — plan bridges Milvus→pgvector |

**Caveat:** These are all AppFlowy AI features. The plan points AppFlowy AI to Arc Summarizer (Granite-4.1-3B) via `AI_AZURE_OPENAI_API_BASE`. This gives us AI functionality but through council's pipeline, not AppFlowy's native AI layer.

### Deployment Model Conflict (Single-Machine, Single-User)

| # | AppFlowy Feature | Why It Won't Work | Plan Decision |
|---|-----------------|-------------------|---------------|
| 7 | **Cloud Sync** (`flowy-server/af_cloud/`) | Plan is single-machine, no cloud account configured | `GOTRUE_DISABLE_SIGNUP=true`, no cloud sync |
| 8 | **User Management** (multi-user auth, workspace membership, roles) | Plan is single-user (admin@council.local) | GoTrue creates one admin, signup disabled |
| 9 | **Collaboration (Yjs real-time)** | Requires multiple connected clients | Single-user deployment |
| 10 | **Share Entities** (database sharing, invite links, access control) | Requires multi-user | Single-user |

**Caveat:** These would work technically but add no value for a single-user deployment. If you ever add a second user, these become relevant.

### Not Implemented (Plan Mentions but No Code)

| # | Feature | Gap | Effort to Add |
|---|---------|-----|---------------|
| 11 | **Sorting** (multi-field, direction) | AppFlowy UI supports it, but plan doesn't set up sort configs | Low — UI-only, no code |
| 12 | **Notifications** (event-driven, debouncing) | Plan mentions P2 but no `push_notification()` method | Medium — ~50 lines, AppFlowy notification API |
| 13 | **Full-Text Search** (Tantivy) | Plan mentions P1 but no search bridge | Medium — AppFlowy search API + council query routing |
| 14 | **Calendar View** | Plan mentions for consolidation tiers but no view config | Low — UI-only |
| 15 | **Gallery View** | Plan mentions for knowledge cards but no view config | Low — UI-only |
| 16 | **Folder Hierarchy** (workspace → folder → view) | Plan mentions P2 but no folder creation | Medium — AppFlowy folder API |
| 17 | **Calculation** (sum, count, average on database fields) | Plan mentions P2 but no calculation configs | Low — UI-only |
| 18 | **File Entities** (attachments) | Plan has artifacts (text only) but no file upload | Medium — MinIO integration for file storage |
| 19 | **Date/Timezone** (timezone-aware formatting) | Plan uses TIMESTAMPTZ but no timezone config in AppFlowy | Low — UI-only |
| 20 | **Database Sync State** (snapshot management) | Plan doesn't track sync state | Low — informational only |

### Council Features Not Wired to AppFlowy

| # | Council Feature | Why Not in Plan | Effort to Add |
|---|----------------|-----------------|---------------|
| 21 | **MicroModelEnricher** (ONNX embeddings, failure classification) | Plan mentions P1 but no `push_enrichment()` method | Medium — ~30 lines |
| 22 | **Voice Pipeline** (ASR→LLM→TTS, voice-to-task) | Plan mentions P2 but no voice integration | High — requires voice→text→work_item pipeline |
| 23 | **Output Gate** (subagent validation, Chair gate) | Plan mentions P3 | Medium — gate results → Findings database |
| 24 | **State Machine Linter** (8-check validation) | Plan mentions P3 | Low — lint violations → EventLog → AppFlowy |
| 25 | **Service Health Checker** | Plan mentions P3 | Medium — health status → AppFlowy dashboard |
| 26 | **DbIndexPoller** (auto-index council data) | Plan doesn't address | Low — MemIndex already handles this |
| 27 | **DocFileWatcher** (auto-index AppFlowy docs) | Plan doesn't address | Medium — watch AppFlowy doc directory → Milvus |
| 28 | **Event Window Summaries** (temporal aggregation) | Plan has EventLog but no window summaries | Medium — aggregate query → AppFlowy |
| 29 | **Artifact Summaries** (enrichment LEFT JOIN) | Plan has artifacts but no enrichment | Medium — MicroModelEnricher → artifact_summaries table |
| 30 | **CouncilMemory** (daily markdown logging) | Plan replaces with EventLog but no AppFlowy push | Low — EventLog → AppFlowy |
| 31 | **MCP Server → AppFlowy AI** | Plan updates MCP tools but no AppFlowy AI bridge | High — requires AppFlowy AI enabled |
| 32 | **HTTP Endpoints → AppFlowy webhooks** | Plan mentions P2 but no webhook config | Medium — AppFlowy webhook receiver |

---

## Phase 1: CouncilDatabase Architecture

### Unified Schema Design

Single PostgreSQL instance. Council tables in `council` schema. AppFlowy tables in `appflowy_public` schema (managed by AppFlowy). Cross-schema queries via Python, not SQL JOINs.

```sql
-- Council schema creation
CREATE SCHEMA IF NOT EXISTS council;

-- ── Core Pipeline Tables ──────────────────────────────────────────────

CREATE TABLE council.pipelines (
    pipeline_id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    task_hash TEXT NOT NULL,
    project_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN (
        'SCOUT', 'PLAN', 'BUILD', 'COHESIVENESS_REVIEW', 'AGENT_VALIDATE',
        'PENDING_REVIEW', 'HUMAN_GATE', 'INDEX', 'DELEGATION', 'DONE', 'FAILED'
    )),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'done', 'failed')),
    global_attempts INTEGER DEFAULT 0,
    metadata JSONB,
    work_id TEXT REFERENCES council.work_items(work_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_council_pipelines_project ON council.pipelines(project_id);
CREATE INDEX idx_council_pipelines_hash ON council.pipelines(task_hash, project_id);
CREATE INDEX idx_council_pipelines_status ON council.pipelines(status, phase);

CREATE TABLE council.workflow_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL REFERENCES council.pipelines(pipeline_id),
    project_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'done', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_council_runs_pipeline ON council.workflow_runs(pipeline_id);

CREATE TABLE council.state_executions (
    execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES council.workflow_runs(run_id),
    phase TEXT NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'retreat', 'retreat_success')),
    error TEXT,
    duration_ms DOUBLE PRECISION,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(run_id, phase, attempt_number)
);

CREATE INDEX idx_council_executions_run ON council.state_executions(run_id);

-- ── Review Tables (replace fake pipelines) ────────────────────────────

CREATE TABLE council.reviews (
    review_id TEXT PRIMARY KEY,
    reviewer TEXT NOT NULL,
    target TEXT NOT NULL,
    project_id TEXT NOT NULL,
    work_id TEXT REFERENCES council.work_items(work_id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'passed', 'failed', 'partial')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_council_reviews_project ON council.reviews(project_id);
CREATE INDEX idx_council_reviews_status ON council.reviews(status);

CREATE TABLE council.review_findings (
    finding_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES council.reviews(review_id),
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'moderate', 'low', 'info')),
    summary TEXT NOT NULL,
    fix TEXT,
    evidence TEXT,
    action TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_findings_review ON council.review_findings(review_id);
CREATE INDEX idx_council_findings_severity ON council.review_findings(severity);

-- ── Unified Work Items ────────────────────────────────────────────────

CREATE TABLE council.work_items (
    work_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    work_type TEXT NOT NULL CHECK (work_type IN ('pipeline', 'review', 'delegation', 'ad-hoc')),
    task TEXT NOT NULL,
    task_hash TEXT NOT NULL,
    parent_work_id TEXT REFERENCES council.work_items(work_id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'done', 'failed')),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_council_work_project ON council.work_items(project_id);
CREATE INDEX idx_council_work_type ON council.work_items(work_type, status);

-- ── Event Log (replaces CouncilMemory markdown files) ─────────────────

CREATE TABLE council.event_log (
    event_id TEXT PRIMARY KEY,
    run_id TEXT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'transition', 'review-finding', 'review-verdict', 'pipeline-created',
        'pipeline-failed', 'artifact-stored', 'consolidation', 'delegation',
        'slot-swap', 'slot-invalidated', 'health-check', 'error', 'info'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'moderate', 'low', 'info')),
    message TEXT NOT NULL,
    metadata JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_events_run ON council.event_log(run_id);
CREATE INDEX idx_council_events_type ON council.event_log(event_type, severity);
CREATE INDEX idx_council_events_time ON council.event_log(occurred_at DESC);

-- ── Artifacts ─────────────────────────────────────────────────────────

CREATE TABLE council.artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES council.workflow_runs(run_id),
    phase TEXT,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    content_type TEXT DEFAULT 'text/plain',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_artifacts_run ON council.artifacts(run_id);
CREATE INDEX idx_council_artifacts_run_phase ON council.artifacts(run_id, phase);

-- ── Session Diary (Arc Summarizer output) ─────────────────────────────

CREATE TABLE council.session_diary (
    entry_id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('mechanical', 'consolidation', 'test')),
    consolidation_tier TEXT,
    content TEXT NOT NULL,
    sections JSONB,  -- {decisions: [], open_items: [], work_completed: [], ...}
    ttl_phase TEXT DEFAULT 'active' CHECK (ttl_phase IN ('active', 'aging', 'expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_diary_tier ON council.session_diary(consolidation_tier);
CREATE INDEX idx_council_diary_source ON council.session_diary(source);

-- ── Consolidation Tiers Registry ──────────────────────────────────────

CREATE TABLE council.consolidation_tiers (
    tier_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    ttl_days INTEGER NOT NULL,
    input_source TEXT NOT NULL,
    output_target TEXT NOT NULL,
    last_run_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO council.consolidation_tiers (tier_id, label, window_days, ttl_days, input_source, output_target)
VALUES
    ('daily',     '24-Hour Diary',     1,  7,  'raw',       'session_diary'),
    ('short',     '3-Day Digest',      3,  14, 'daily',     'session_diary'),
    ('weekly',    'Weekly Review',     7,  30, 'short',     'session_diary'),
    ('bimonthly', 'Bi-Weekly Overview',15, 60, 'weekly',    'consolidation_cache')
ON CONFLICT (tier_id) DO NOTHING;

-- ── Consolidation Cache (Arc A380 output) ─────────────────────────────

CREATE TABLE council.consolidation_cache (
    cache_id TEXT PRIMARY KEY,
    tier_id TEXT REFERENCES council.consolidation_tiers(tier_id),
    content TEXT NOT NULL,
    summary JSONB,  -- {executive_summary, major_achievements, course_corrections, knowledge_base}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX idx_council_cache_tier ON council.consolidation_cache(tier_id);

-- ── Failure Classifications ───────────────────────────────────────────

CREATE TABLE council.failure_classifications (
    classification_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES council.workflow_runs(run_id),
    error TEXT NOT NULL,
    failure_type TEXT,
    confidence DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Prompt Templates (AppFlowy document sync) ─────────────────────────

CREATE TABLE council.prompt_templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,  -- {tags: [], use_case: '', status: 'active|archived'}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_prompts_model ON council.prompt_templates(model);

-- ── Knowledge Cards (Arc Summarizer extraction) ───────────────────────

CREATE TABLE council.knowledge_cards (
    card_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT[],  -- PostgreSQL array
    source_run_id TEXT,
    confidence DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_knowledge_topic ON council.knowledge_cards USING GIN(tags);

-- ── Audit Trail ───────────────────────────────────────────────────────

CREATE TABLE council.audit_log (
    audit_id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER,
    gate_valid BOOLEAN,
    bypass_reason TEXT,
    metadata JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_audit_time ON council.audit_log(occurred_at DESC);
```

### CouncilDatabase API

```python
"""CouncilDatabase: Council-domain data layer.

Replaces RelationalStore + ContextRouter + ReviewService + MemoryLayer.
Backed by PostgreSQL (SQLAlchemy ORM). No SQLite. No backward compat.
"""
from sqlalchemy import create_engine, Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, ARRAY, check_constraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ
from sqlalchemy.orm import sessionmaker, relationship, declarative_base, Session
from contextlib import contextmanager
from datetime import datetime, timezone

Base = declarative_base()


# ── ORM Models ─────────────────────────────────────────────────────────

class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = ("council_pipelines_pkey", {"schema": "council"})

    pipeline_id = Column(String, primary_key=True)
    task = Column(Text, nullable=False)
    task_hash = Column(String(32), nullable=False)
    project_id = Column(String, nullable=False)
    phase = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="active")
    global_attempts = Column(Integer, server_default="0")
    metadata = Column(JSONB)
    work_id = Column(String, ForeignKey("council.work_items.work_id"))
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())
    completed_at = Column(TIMESTAMPTZ)

    runs = relationship("WorkflowRun", back_populates="pipeline")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = {"schema": "council"}

    run_id = Column(String, primary_key=True)
    pipeline_id = Column(String, ForeignKey("council.pipelines.pipeline_id"))
    project_id = Column(String, nullable=False)
    phase = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="running")
    started_at = Column(TIMESTAMPTZ, server_default=func.now())
    finished_at = Column(TIMESTAMPTZ)

    pipeline = relationship("Pipeline", back_populates="runs")
    executions = relationship("StateExecution", back_populates="run")
    artifacts = relationship("Artifact", back_populates="run")
    events = relationship("EventLog", back_populates="run")


class StateExecution(Base):
    __tablename__ = "state_executions"
    __table_args__ = {"schema": "council"}

    execution_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("council.workflow_runs.run_id"))
    phase = Column(String, nullable=False)
    attempt_number = Column(Integer, nullable=False, server_default="1")
    outcome = Column(String, nullable=False)
    error = Column(Text)
    duration_ms = Column(Float)
    started_at = Column(TIMESTAMPTZ, server_default=func.now())
    finished_at = Column(TIMESTAMPTZ)

    run = relationship("WorkflowRun", back_populates="executions")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = {"schema": "council"}

    review_id = Column(String, primary_key=True)
    reviewer = Column(String, nullable=False)
    target = Column(Text, nullable=False)
    project_id = Column(String, nullable=False)
    work_id = Column(String, ForeignKey("council.work_items.work_id"))
    status = Column(String, nullable=False, server_default="active")
    started_at = Column(TIMESTAMPTZ, server_default=func.now())
    finished_at = Column(TIMESTAMPTZ)

    findings = relationship("ReviewFinding", back_populates="review")


class ReviewFinding(Base):
    __tablename__ = "review_findings"
    __table_args__ = {"schema": "council"}

    finding_id = Column(String, primary_key=True)
    review_id = Column(String, ForeignKey("council.reviews.review_id"))
    severity = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    fix = Column(Text)
    evidence = Column(Text)
    action = Column(Text)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    review = relationship("Review", back_populates="findings")


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = {"schema": "council"}

    work_id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False)
    work_type = Column(String, nullable=False)
    task = Column(Text, nullable=False)
    task_hash = Column(String(32), nullable=False)
    parent_work_id = Column(String, ForeignKey("council.work_items.work_id"))
    status = Column(String, nullable=False, server_default="active")
    metadata = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())
    finished_at = Column(TIMESTAMPTZ)


class EventLog(Base):
    __tablename__ = "event_log"
    __table_args__ = {"schema": "council"}

    event_id = Column(String, primary_key=True)
    run_id = Column(String)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    metadata = Column(JSONB)
    occurred_at = Column(TIMESTAMPTZ, server_default=func.now())

    run = relationship("WorkflowRun", back_populates="events")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = {"schema": "council"}

    artifact_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("council.workflow_runs.run_id"))
    phase = Column(String)
    key = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String, server_default="text/plain")
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    run = relationship("WorkflowRun", back_populates="artifacts")


class SessionDiary(Base):
    __tablename__ = "session_diary"
    __table_args__ = {"schema": "council"}

    entry_id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    consolidation_tier = Column(String)
    content = Column(Text, nullable=False)
    sections = Column(JSONB)
    ttl_phase = Column(String, server_default="active")
    created_at = Column(TIMESTAMPTZ, server_default=func.now())


class ConsolidationTier(Base):
    __tablename__ = "consolidation_tiers"
    __table_args__ = {"schema": "council"}

    tier_id = Column(String, primary_key=True)
    label = Column(String, nullable=False)
    window_days = Column(Integer, nullable=False)
    ttl_days = Column(Integer, nullable=False)
    input_source = Column(String, nullable=False)
    output_target = Column(String, nullable=False)
    last_run_at = Column(TIMESTAMPTZ)
    is_active = Column(Boolean, server_default=True)


class ConsolidationCache(Base):
    __tablename__ = "consolidation_cache"
    __table_args__ = {"schema": "council"}

    cache_id = Column(String, primary_key=True)
    tier_id = Column(String, ForeignKey("council.consolidation_tiers.tier_id"))
    content = Column(Text, nullable=False)
    summary = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    expires_at = Column(TIMESTAMPTZ)


class FailureClassification(Base):
    __tablename__ = "failure_classifications"
    __table_args__ = {"schema": "council"}

    classification_id = Column(String, primary_key=True)
    run_id = Column(String)
    error = Column(Text, nullable=False)
    failure_type = Column(String)
    confidence = Column(Float)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = {"schema": "council"}

    template_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    model = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())


class KnowledgeCard(Base):
    __tablename__ = "knowledge_cards"
    __table_args__ = {"schema": "council"}

    card_id = Column(String, primary_key=True)
    topic = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(ARRAY(String))
    source_run_id = Column(String)
    confidence = Column(Float)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "council"}

    audit_id = Column(String, primary_key=True)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer)
    gate_valid = Column(Boolean)
    bypass_reason = Column(Text)
    metadata = Column(JSONB)
    occurred_at = Column(TIMESTAMPTZ, server_default=func.now())


# ── CouncilDatabase: Domain Service ────────────────────────────────────

class CouncilDatabase:
    """Council-domain data layer.

    Single entry point. Replaces RelationalStore + ContextRouter + ReviewService + MemoryLayer.
    All council operations are domain methods — no raw SQL exposure.
    """

    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine, schema="council")

        # Lazy-loaded domain services
        self._pipelines: "PipelineService" = None
        self._reviews: "ReviewDomain" = None
        self._work: "WorkService" = None
        self._recall: "RecallService" = None
        self._memory: "MemoryService" = None
        self._appflowy: "AppFlowySync" = None
        self._prompts: "PromptService" = None

    @property
    def pipelines(self) -> "PipelineService":
        if self._pipelines is None:
            self._pipelines = PipelineService(self.Session)
        return self._pipelines

    @property
    def reviews(self) -> "ReviewDomain":
        if self._reviews is None:
            self._reviews = ReviewDomain(self.Session)
        return self._reviews

    @property
    def work(self) -> "WorkService":
        if self._work is None:
            self._work = WorkService(self.Session)
        return self._work

    @property
    def recall(self) -> "RecallService":
        if self._recall is None:
            self._recall = RecallService(self.Session)
        return self._recall

    @property
    def memory(self) -> "MemoryService":
        """MemoryLayer replacement — token-budgeted context slices."""
        if self._memory is None:
            self._memory = MemoryService(self.Session)
        return self._memory

    @property
    def appflowy(self) -> "AppFlowySync":
        if self._appflowy is None:
            from .appflowy_sync import AppFlowySync
            self._appflowy = AppFlowySync(self.Session)
        return self._appflowy

    @property
    def prompts(self) -> "PromptService":
        if self._prompts is None:
            self._prompts = PromptService(self.Session)
        return self._prompts

    @contextmanager
    def session(self) -> Session:
        """Session context manager with auto-commit/rollback."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

### Domain Services (Complete API)

```python
# ── PipelineService ────────────────────────────────────────────────────

class PipelineService:
    """Pipeline lifecycle — creation, transition, archival."""

    def __init__(self, Session):
        self._Session = Session

    def create(self, task: str, project_id: str, pipeline_id: str = None) -> Pipeline:
        """Create pipeline + workflow run + work item + seed event. One call."""
        # Implementation: creates Pipeline, WorkflowRun, WorkItem, EventLog in one transaction
        # Pushes to AppFlowy via self._db.appflowy.push_work_item()
        ...

    def transition(self, run_id: str, from_phase: str, to_phase: str,
                   outcome: str = "success", error: str = "",
                   duration_ms: float = 0.0,
                   artifact_key: str = None, artifact_content: str = None) -> dict:
        """Record phase transition atomically. Replaces 5 separate calls."""
        # Implementation: creates StateExecution, EventLog, Artifact, updates WorkflowRun + Pipeline
        # Pushes to AppFlowy via self._db.appflowy.push_transition()
        ...

    def find_active(self, task: str, project_id: str) -> Pipeline | None:
        """Find active pipeline by task hash."""
        ...

    def archive(self, pipeline_id: str) -> None:
        """Move terminal pipeline to archive (status = done/failed)."""
        ...

    def list_by_project(self, project_id: str, status: str = None,
                        limit: int = 50) -> list[Pipeline]:
        """List pipelines for a project."""
        ...


# ── ReviewDomain ───────────────────────────────────────────────────────

class ReviewDomain:
    """Review lifecycle — native tables, no fake pipelines."""

    def __init__(self, Session):
        self._Session = Session

    def start(self, reviewer: str, target: str, project_id: str,
              work_id: str = None) -> Review:
        """Start review. One call — no fake pipeline needed."""
        # Implementation: creates Review + EventLog
        # Pushes to AppFlowy via self._db.appflowy.push_review()
        ...

    def log_finding(self, review_id: str, severity: str, summary: str,
                    fix: str = "", evidence: str = "", action: str = "") -> ReviewFinding:
        """Log finding. One call."""
        # Implementation: creates ReviewFinding + EventLog
        # Pushes to AppFlowy via self._db.appflowy.push_finding()
        ...

    def record_verdict(self, review_id: str, verdict: str, reason: str = "") -> Review:
        """Record verdict. One call."""
        # Implementation: updates Review.status + EventLog
        # Pushes to AppFlowy via self._db.appflowy.push_verdict()
        ...

    def list_findings(self, project_id: str = None, severity: str = None,
                      limit: int = 20) -> list[ReviewFinding]:
        """List findings with optional filters."""
        ...


# ── WorkService ────────────────────────────────────────────────────────

class WorkService:
    """Unified work tracking — pipelines, reviews, delegations, ad-hoc."""

    def __init__(self, Session):
        self._Session = Session

    def upsert(self, work_id: str, project_id: str, work_type: str,
               task: str, status: str = "active", metadata: dict = None,
               parent_work_id: str = None) -> WorkItem:
        """Create or update work item."""
        ...

    def finish(self, work_id: str) -> WorkItem:
        """Mark work item as done."""
        ...

    def list_active(self, project_id: str = None, work_type: str = None) -> list[WorkItem]:
        """List active work items."""
        ...


# ── RecallService ──────────────────────────────────────────────────────

class RecallService:
    """Integrated recall — run snapshots, events, artifacts in one query."""

    def __init__(self, Session):
        self._Session = Session

    def run_snapshot(self, run_id: str) -> dict:
        """Full run snapshot: pipeline + executions + events + artifacts."""
        ...

    def recent_events(self, run_id: str = None, limit: int = 10,
                      severity: str = None) -> list[dict]:
        """Recent events, optionally scoped to a run."""
        ...

    def review_findings(self, project_id: str = None, limit: int = 10) -> list[dict]:
        """Recent review findings with review context."""
        ...

    def similar_runs(self, task: str, project_id: str, limit: int = 5) -> list[dict]:
        """Find similar runs by task hash."""
        ...

    def context_slice(self, run_id: str, max_tokens: int = 4096) -> str:
        """Token-budgeted context slice for LLM prompts."""
        ...


# ── MemoryService ──────────────────────────────────────────────────────

class MemoryService:
    """MemoryLayer replacement — token-budgeted context slices."""

    def __init__(self, Session):
        self._Session = Session

    def get_recent_diary(self, days: int = 7, max_tokens: int = 4096) -> str:
        """Recent session diary, consolidated if available."""
        ...

    def get_consolidation_metrics(self) -> dict:
        """Consolidation health: tiers, TTL, cache stats."""
        ...

    def upsert_summary(self, summary_text: str, source: str = "mechanical",
                       sections: dict = None) -> SessionDiary:
        """Upsert session summary."""
        ...


# ── PromptService ──────────────────────────────────────────────────────

class PromptService:
    """Prompt template management — synced with AppFlowy documents."""

    def __init__(self, Session):
        self._Session = Session

    def upsert(self, template_id: str, name: str, model: str,
               content: str, tags: list = None, use_case: str = "") -> PromptTemplate:
        """Create or update prompt template."""
        ...

    def get(self, template_id: str) -> PromptTemplate | None:
        """Get template by ID."""
        ...

    def list_by_model(self, model: str) -> list[PromptTemplate]:
        """List templates for a model."""
        ...

    def render(self, template_id: str, **kwargs) -> str:
        """Render template with variable substitution."""
        ...
```

---

## Phase 2: AppFlowy Synthesis

### AppFlowy Databases (Council-Managed)

These databases are created in AppFlowy and populated by `AppFlowySync`. Council is the source of truth (PostgreSQL). AppFlowy is the visual layer.

| Database | Purpose | Fields | Views | Auto-Group |
|----------|---------|--------|-------|------------|
| **Work Items** | All council work | work_id, project, type, task, status, priority, created, updated | Board, Grid, Timeline | Status |
| **Pipelines** | Pipeline tracking | pipeline_id, task, phase, status, attempts, duration, created | Board, Grid | Phase |
| **Reviews** | Review lifecycle | review_id, reviewer, target, status, verdict, findings_count, duration | Board, Grid | Status |
| **Findings** | Review findings | finding_id, review, severity, summary, fix, evidence | Grid, Board | Severity |
| **Knowledge Base** | Knowledge cards | card_id, topic, content, tags, source, confidence | Grid, Gallery | Tags |
| **Session Diary** | Consolidated memory | entry_id, tier, content, sections, created | Timeline, Grid | Tier |
| **Prompt Library** | Prompt templates | template_id, name, model, content, tags, status | Grid, Gallery | Model |
| **Audit Log** | System audit | audit_id, endpoint, method, status, gate_valid, bypass, time | Grid | Severity |

### AppFlowy Documents (Council-Managed)

Documents are created by council services for human-readable output:

| Document | Source | Content |
|----------|--------|---------|
| **Daily Log** | Arc Summarizer (daily tier) | Tasks, decisions, files, errors |
| **3-Day Digest** | Arc Summarizer (short tier) | Work threads, carried-forward |
| **Weekly Review** | Arc Summarizer (weekly tier) | Milestones, projects, risks |
| **Bi-Weekly Overview** | Arc Summarizer (bimonthly tier) | Strategic themes, corrections |
| **Session Summaries** | SlotSupervisor (on completion) | Run snapshot, artifacts, verdict |
| **Prompt Templates** | PromptService (bidirectional) | Editable prompts with metadata |

### AppFlowySync Adapter

```python
"""AppFlowySync: Thin REST adapter for AppFlowy databases.

Pushes council data to AppFlowy for visual management.
No sync logic. No polling. Just API calls on state changes.
Council PostgreSQL is the source of truth.
"""
import httpx
import json
from typing import Optional


class AppFlowySync:
    def __init__(self, Session):
        self._Session = Session
        self._client = httpx.Client(
            base_url="http://localhost:8080",
            headers={"Authorization": "Bearer council_jwt_secret_change_me"},
            timeout=30,
        )
        self.workspace_id = "council-workspace"  # from config
        self.databases = {
            "work_items": "db-uuid-1",
            "pipelines": "db-uuid-2",
            "reviews": "db-uuid-3",
            "findings": "db-uuid-4",
            "knowledge_base": "db-uuid-5",
            "session_diary": "db-uuid-6",
            "prompt_library": "db-uuid-7",
            "audit_log": "db-uuid-8",
        }

    def push_work_item(self, work_item) -> None:
        """Push work item to AppFlowy Work Items database."""
        cells = {
            "work_id": work_item.work_id,
            "project": work_item.project_id,
            "type": work_item.work_type,
            "task": work_item.task[:500],
            "status": work_item.status.capitalize(),
            "created": _format_dt(work_item.created_at),
        }
        self._upsert_row(self.databases["work_items"], cells, work_item.work_id)

    def push_pipeline(self, pipeline) -> None:
        """Push pipeline to AppFlowy Pipelines database."""
        cells = {
            "pipeline_id": pipeline.pipeline_id,
            "task": pipeline.task[:500],
            "phase": pipeline.phase,
            "status": pipeline.status.capitalize(),
            "attempts": pipeline.global_attempts,
            "created": _format_dt(pipeline.created_at),
        }
        self._upsert_row(self.databases["pipelines"], cells, pipeline.pipeline_id)

    def push_review(self, review) -> None:
        """Push review to AppFlowy Reviews database."""
        cells = {
            "review_id": review.review_id,
            "reviewer": review.reviewer,
            "target": review.target[:500],
            "status": review.status.capitalize(),
            "created": _format_dt(review.started_at),
        }
        self._upsert_row(self.databases["reviews"], cells, review.review_id)

    def push_finding(self, finding) -> None:
        """Push finding to AppFlowy Findings database."""
        cells = {
            "finding_id": finding.finding_id,
            "review": finding.review_id,
            "severity": finding.severity.capitalize(),
            "summary": finding.summary[:1000],
            "fix": (finding.fix or "")[:500],
        }
        self._upsert_row(self.databases["findings"], cells, finding.finding_id)

    def push_knowledge_card(self, card) -> None:
        """Push knowledge card to AppFlowy Knowledge Base."""
        cells = {
            "card_id": card.card_id,
            "topic": card.topic,
            "content": card.content[:2000],
            "tags": ", ".join(card.tags or []),
            "confidence": card.confidence,
        }
        self._upsert_row(self.databases["knowledge_base"], cells, card.card_id)

    def push_diary_entry(self, entry) -> None:
        """Push diary entry to AppFlowy Session Diary."""
        cells = {
            "entry_id": entry.entry_id,
            "tier": (entry.consolidation_tier or "raw").capitalize(),
            "content": entry.content[:2000],
            "created": _format_dt(entry.created_at),
        }
        self._upsert_row(self.databases["session_diary"], cells, entry.entry_id)

    def push_prompt_template(self, template) -> None:
        """Push prompt template to AppFlowy Prompt Library."""
        cells = {
            "template_id": template.template_id,
            "name": template.name,
            "model": template.model,
            "content": template.content[:2000],
            "tags": json.dumps(template.metadata.get("tags", [])) if template.metadata else "",
        }
        self._upsert_row(self.databases["prompt_library"], cells, template.template_id)

    def create_document(self, title: str, content: str, folder: str = "Council") -> str:
        """Create AppFlowy document (for session summaries, etc.)."""
        # Uses AppFlowy's document API to create block-based document
        ...

    def _upsert_row(self, database_id: str, cells: dict, row_id: str) -> dict:
        """Upsert row in AppFlowy database."""
        url = f"/api/workspace/{self.workspace_id}/database/{database_id}/row"
        resp = self._client.put(url, json={"rows": [{"cells": cells}]})
        resp.raise_for_status()
        return resp.json()
```

---

## Phase 3: Feature Integration Map

### Council Features → AppFlowy Integration

| # | Council Feature | Module | AppFlowy Integration | Priority |
|---|----------------|--------|---------------------|----------|
| 1 | Pipeline lifecycle | PipelineService | Board view, auto-group by phase | P0 |
| 2 | Review lifecycle | ReviewDomain | Board view, auto-group by verdict | P0 |
| 3 | Work items | WorkService | Board/Grid, unified tracking | P0 |
| 4 | Event log | RecallService | Grid view, timeline | P0 |
| 5 | Arc Summarizer | ArcPipeline | Documents (daily/short/weekly/bimonthly) | P0 |
| 6 | Knowledge cards | ArcPipeline.extract_knowledge() | Knowledge Base database | P1 |
| 7 | Session diary | MemoryService | Session Diary database | P1 |
| 8 | Failure classifications | MicroModelEnricher | Findings database, Kanban by severity | P1 |
| 9 | Prompt templates | PromptService | Prompt Library database + Documents | P1 |
| 10 | Audit trail | AuditLog | Audit Log database | P2 |
| 11 | MemIndex | MemIndex | pgvector bridge for unified search | P2 |
| 12 | Voice pipeline | voice_pipeline/ | Voice-to-task creation | P2 |
| 13 | Output Gate | output_gate.py | Review finding validation | P3 |
| 14 | State Machine Linter | state_linter.py | Pipeline integrity notifications | P3 |
| 15 | Service Health | health.py | Monitoring dashboard | P3 |
| 16 | CodeGraph | code_graph/store.py | Code review context (read-only) | P3 |

### AppFlowy Features → Council Integration

| # | AppFlowy Feature | Council Integration | Priority |
|---|-----------------|-------------------|----------|
| 1 | Board Layout | Pipeline status board, review board | P0 |
| 2 | Field Types | Severity select, status select, date, relation | P0 |
| 3 | Grouping | By phase, severity, reviewer, project | P0 |
| 4 | Document Management | Session summaries, prompt templates | P0 |
| 5 | Full-Text Search | Tantivy FTS + council event search | P1 |
| 6 | SQLite Vector | pgvector bridge for semantic search | P2 |
| 7 | Notifications | Pipeline events, review alerts | P2 |
| 8 | Calendar View | Timeline views for consolidation tiers | P2 |
| 9 | Folder Hierarchy | Project-based workspace organization | P2 |
| 10 | Gallery View | Knowledge cards, prompt templates | P3 |
| 11 | Custom Prompts | Council-specific AI prompts | P3 |
| 12 | View Entities | Grid/Board/Calendar/Gallery per database | P3 |

---

## Phase 4: SlotSupervisor Integration

### Before (5 calls for one transition)

```python
# super_council.py — OLD (SQLite)
self.relational_store.upsert_pipeline(...)
self.relational_store.ensure_workflow_run(...)
self.relational_store._record_transition(...)
self.relational_store.log_event(...)
self.relational_store.store_artifact(...)
```

### After (1 call)

```python
# super_council.py — NEW (PostgreSQL + AppFlowy)
result = self.council_db.pipelines.transition(
    run_id=run_id,
    from_phase=from_phase,
    to_phase=to_phase,
    outcome="success",
    artifact_key="plan",
    artifact_content=plan_text,
)
# AppFlowy push happens inside transition() via AppFlowySync
```

### SlotSupervisor Initialization

```python
class SlotSupervisor:
    def __init__(self, config_path: str):
        # OLD:
        # self.relational_store = RelationalStore(db_path)
        # self.context_router = ContextRouter(self.relational_store)
        # self.memory_layer = MemoryLayer(...)
        # self.review_service = ReviewService(self.relational_store)

        # NEW:
        config = load_config(config_path)
        self.council_db = CouncilDatabase(
            database_url=config.database_url  # postgresql://...@localhost:5433/council_db
        )
        # All access through self.council_db.*
```

### Method Mapping (Migration Reference)

| Old Call | New Call | Notes |
|----------|----------|-------|
| `rs.upsert_pipeline(pid, task, project)` | `council_db.pipelines.create(task, project, pid)` | Creates run + work_item + event |
| `rs.ensure_workflow_run(rid, pid)` | (included in create) | No separate call needed |
| `rs._record_transition(rid, phase, outcome)` | `council_db.pipelines.transition(rid, from, to, outcome)` | Atomic |
| `rs.log_event(rid, type, severity, msg)` | (included in transition) | Auto-logged |
| `rs.store_artifact(rid, phase, key, content)` | (included in transition) | Optional artifact |
| `rs.find_active_pipeline(task, project)` | `council_db.pipelines.find_active(task, project)` | Same API |
| `cr.get_run_snapshot(rid)` | `council_db.recall.run_snapshot(rid)` | Same result |
| `cr.get_recent_events(rid, limit)` | `council_db.recall.recent_events(rid, limit)` | Same result |
| `cr.get_recent_diary(days)` | `council_db.memory.get_recent_diary(days)` | Same result |
| `rs.upsert_review(reviewer, target)` | `council_db.reviews.start(reviewer, target, project)` | Native review |
| `rs.log_finding(rid, severity, summary)` | `council_db.reviews.log_finding(rid, severity, summary)` | Same API |
| `rs.record_verdict(rid, verdict)` | `council_db.reviews.record_verdict(rid, verdict)` | Same API |

---

## Phase 5: Arc Summarizer Integration

### Current Flow (SQLite)

```
ArcPipeline.run_tiered_consolidation(tier_id)
  → _gather_tier_input()        # Read from session_diary (SQLite)
  → ArcClient.consolidate_tiered()  # POST to Arc A380
  → _write_tier_output()        # Write to session_diary (SQLite)
  → update_tier_last_run()      # Update consolidation_tiers (SQLite)
```

### New Flow (PostgreSQL + AppFlowy)

```
ArcPipeline.run_tiered_consolidation(tier_id)
  → council_db.memory.get_recent_diary(days=window_days)  # Read from PostgreSQL
  → ArcClient.consolidate_tiered()  # POST to Arc A380 (unchanged)
  → council_db.memory.upsert_summary(output, tier_id)     # Write to PostgreSQL
  → council_db.appflowy.push_diary_entry(entry)           # Push to AppFlowy DB
  → council_db.appflowy.create_document(title, content)   # Push to AppFlowy Doc
  → council_db.recall.update_tier_last_run(tier_id)       # Update PostgreSQL
```

### Knowledge Card Injection

```
ArcPipeline.inject_knowledge_cards(text, schema)
  → ArcClient.extract_knowledge(text, schema)  # POST to Arc A380
  → council_db.memory.upsert_knowledge_cards(cards)  # Write to PostgreSQL
  → council_db.appflowy.push_knowledge_card(card)    # Push to AppFlowy KB
```

---

## Phase 6: AppFlowy Sync Layer (Polling-Based)

### Architecture: Council Writes, AppFlowy Reflects

Council PostgreSQL is the single source of truth. AppFlowy is the visual layer that reflects council state. Changes flow:

1. **Council → AppFlowy (push on every state change)** — `AppFlowySync.push_*()` methods write to AppFlowy databases via documented REST API
2. **AppFlowy → Council (polling for user edits)** — `EventIngestionService` polls `GET /database/{db}/row/updated` (documented AppFlowy OpenAPI endpoint) to detect user-driven changes in the AppFlowy UI
3. **Conflict resolution: Council-wins** — If council and AppFlowy have conflicting state for the same entity, council PostgreSQL is authoritative. AppFlowy user edits that conflict with council state are logged but not applied; non-conflicting edits (e.g., adding a new work item) are accepted.
4. **Voice commands** → Create structured work items in council → Enter execution queue → Push to AppFlowy

### AppFlowy REST API (Stable, Documented Endpoints)

All AppFlowy integration uses the [documented OpenAPI endpoints](https://github.com/AppFlowy-IO/AppFlowy-Docs/blob/main/documentation/appflowy-cloud/openapi/README.md). No fork, no modification, no phantom endpoints.

| Endpoint | Method | Purpose | Used By |
|----------|--------|---------|---------|
| `/api/workspace/{ws}/database/{db}/row` | POST | Create row | `push_*()` methods |
| `/api/workspace/{ws}/database/{db}/row` | PUT | Upsert row | `push_*()` methods |
| `/api/workspace/{ws}/database/{db}/row/updated` | GET | **List recently updated row IDs + timestamps** | `pull_changes()` |
| `/api/workspace/{ws}/database/{db}/row/detail` | GET | **Fetch full row cells** | `pull_changes()` |
| `/api/workspace/{ws}/database/{db}/fields` | GET | List field definitions | Schema validation |
| `/api/workspace/{ws}/database` | GET | List databases | Discovery |

### Modules (5 files, Redis and PostgreSQL LISTEN removed)

| Module | Purpose | File |
|--------|---------|------|
| `CouncilAppFlowyBridge` | Unified integration layer — single entry point | `council_appflowy_bridge.py` |
| `AppFlowySync` | REST adapter: push via POST/PUT, pull via GET /row/updated | `appflowy_sync.py` |
| `EventIngestionService` | **Polling-only** event listener (Redis/PG channels removed) | `event_ingestion.py` |
| `ExecutionQueue` | Priority queue with multi-source ingestion | `execution_queue.py` |
| `VoiceToWorkItem` | Voice transcript → structured task → queue | `voice_to_workitem.py` |
| `ModelContextEnrichment` | Injects AppFlowy changes into Arc context | `model_context_enrichment.py` |

### Removed Components

| Component | Why Removed |
|-----------|-------------|
| Redis pub/sub channel | AppFlowy has no Redis integration; no source of events |
| PostgreSQL LISTEN/NOTIFY | AppFlowy uses separate PostgreSQL; cannot NOTIFY council |
| `setup_pg_listener()` | Dead code — no cross-database NOTIFY possible |
| `check_pg_notifications()` | Dead code — always returned empty list |

### Data Flow (Council → AppFlowy: Push)

```
Council state change (transition, review, work item, etc.)
  → CouncilDatabase domain method writes to PostgreSQL
  → AppFlowySync.push_*() calls PUT /database/{db}/row
  → AppFlowy UI reflects change (next user refresh)
  → If push fails: exponential backoff (3 retries), log warning, council state unaffected
```

### Data Flow (AppFlowy → Council: Polling)

```
User edits row in AppFlowy UI
  → AppFlowy PostgreSQL records update timestamp
  → EventIngestionService._poll_changes() (every 30s)
    → GET /database/{db}/row/updated  (returns [{id, updated_at}, ...])
    → For each updated row:
      → GET /database/{db}/row/detail?row_id={id}  (returns {id, cells})
      → Diff against last-known state (self._known_items)
      → Route to handler (work_item.created, work_item.status_changed, etc.)
      → Handler updates council state + pushes to ExecutionQueue
    → Update self._known_items with current state
  → Council executes task if new work item detected
  → AppFlowySync.push_*() confirms state in visual layer
```

### Data Flow (Voice → Council → AppFlowy)

```
Voice command
  → ASR → transcript
  → VoiceToWorkItem.extract_task() (LLM structuring)
  → ExecutionQueue.enqueue(priority, source="voice")
  → Pipeline auto-creates in council PostgreSQL
  → AppFlowySync.push_work_item() updates visual layer
```

### Data Flow (Arc Summarizer → Council → AppFlowy)

```
Arc Summarizer consolidation
  → ModelContextEnrichment.build_context()
    → Council diary (PostgreSQL)
    → AppFlowy changes (AppFlowySync.get_recent_changes())
    → Execution queue status
    → Health status
    → Recent reviews + knowledge cards
  → Combined context → Arc A380
  → Consolidated output → PostgreSQL
  → AppFlowySync.push_diary_entry() + create_document() → AppFlowy
```

### Polling Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Poll interval | 30 seconds | Balance between freshness and API load |
| Retry on failure | 3 attempts, exponential backoff | Transient network errors |
| Stale detection | >5 consecutive failures → log warning | Operational visibility |
| Council-wins policy | Council state never overwritten by AppFlowy pull | Single source of truth |

### `pull_changes()` Implementation (Corrected)

```python
# BEFORE (broken — calls non-existent endpoint):
resp = self._client.get(
    f"/api/workspace/{self.workspace_id}/database/{db_id}/changes",
    params={"since": since_str},
)

# AFTER (uses documented AppFlowy OpenAPI endpoints):
def pull_changes(self, since: Optional[datetime] = None,
                 database: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pull changes from AppFlowy via documented REST API.

    Uses GET /database/{db}/row/updated to find changed row IDs,
    then GET /database/{db}/row/detail to fetch full cell data.
    """
    changes = []
    dbs_to_check = {database} if database else set(self.databases.keys())

    for db_name in dbs_to_check:
        db_id = self.databases.get(db_name)
        if not db_id:
            continue

        try:
            # Step 1: Get list of updated row IDs
            resp = self._client.get(
                f"/api/workspace/{self.workspace_id}/database/{db_id}/row/updated",
                timeout=15,
            )
            if resp.status_code != 200:
                continue

            updated_rows = resp.json().get("data", [])

            # Step 2: Fetch full details for each updated row
            for row_ref in updated_rows:
                row_id = row_ref.get("id", "")
                if not row_id:
                    continue

                # Skip if we already know about this version
                last_known = self._known_items.get(row_id)
                if last_known and last_known == row_ref.get("updated_at"):
                    continue

                detail_resp = self._client.get(
                    f"/api/workspace/{self.workspace_id}/database/{db_id}/row/detail",
                    params={"row_id": row_id},
                    timeout=15,
                )
                if detail_resp.status_code == 200:
                    row_data = detail_resp.json()
                    changes.append({
                        "entity": db_name,
                        "action": "updated",
                        "data": row_data.get("data", {}),
                        "timestamp": row_ref.get("updated_at", ""),
                    })
                    # Update known state
                    self._known_items[row_id] = row_ref.get("updated_at")

            self._last_sync[db_name] = datetime.now(timezone.utc)

        except Exception as e:
            log.debug("AppFlowySync: pull changes failed for %s: %s", db_name, e)

    if changes:
        log.debug("AppFlowySync: pulled %d changes", len(changes))

    return changes
```

### Architectural Decisions (Rationale)

| Decision | Rationale |
|----------|-----------|
| **Polling only (no Redis/PG LISTEN)** | AppFlowy has no Redis pub/sub integration and uses a separate PostgreSQL instance. Cross-database LISTEN/NOTIFY is impossible. Polling `GET /row/updated` uses the documented OpenAPI and requires no AppFlowy modifications. |
| **Council-wins conflict policy** | Council PostgreSQL is the single source of truth. AppFlowy is a visual reflection. If user edits in AppFlowy conflict with council state, council state is authoritative. Non-conflicting edits (e.g., new work items) are accepted. |
| **Best-effort push** | `push_*()` methods use exponential backoff (3 retries). If push fails, council state is complete and AppFlowy shows stale data until recovery. No compensation transaction needed — council is authoritative. |
| **No AppFlowy fork** | All integration uses documented REST API endpoints. AppFlowy upgrades via `docker pull && docker compose up -d` without council code changes (unless API breaks). |
| **30s poll interval** | Balance between freshness and API load. Acceptable for visual layer. Voice/critical tasks use direct council API (not AppFlowy UI). |
| **`/row/updated` + `/row/detail` two-step** | AppFlowy API returns row IDs + timestamps from `/row/updated`, then full cell data from `/row/detail`. This is the documented pattern; council follows it. |

### API Discovery Notes

- **Original plan used `GET /database/{db}/changes`** — this endpoint does not exist in AppFlowy
- **Correct endpoint: `GET /database/{db}/row/updated`** — returns `[{id: UUID, updated_at: RFC3339}, ...]`
- **Row details: `GET /database/{db}/row/detail?row_id={id}`** — returns `{id: UUID, cells: {field_id: value, ...}}`
- **Source: [AppFlowy OpenAPI spec](https://github.com/AppFlowy-IO/AppFlowy-Docs/blob/main/documentation/appflowy-cloud/openapi/README.md)**
- **All endpoints are versioned and documented** — stable contract for integration

### Execution Queue Priorities

| Priority | Level | Source | Examples |
|----------|-------|--------|----------|
| 1 | Critical | Voice (urgent keywords) | "Fix this now", "urgent bug" |
| 3 | High | AppFlowy (high priority) | User-created high-priority tasks |
| 5 | Normal | Pipeline auto-queue | Dependency-driven tasks |
| 7 | Low | Scheduled recurring | Maintenance, cleanup |
| 10 | Background | Auto-enrichment | Housekeeping, indexing |

### PostgreSQL Schema Addition

```sql
-- Execution Queue (Phase 6)
CREATE TABLE council.execution_queue (
    queue_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    task TEXT NOT NULL,
    task_hash TEXT NOT NULL,
    project_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    triggered_by TEXT NOT NULL DEFAULT 'auto',
    metadata JSONB,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'skipped')),
    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    pipeline_id TEXT,
    error TEXT
);

CREATE INDEX idx_queue_status_priority
    ON council.execution_queue (status, priority, enqueued_at);
CREATE INDEX idx_queue_hash
    ON council.execution_queue (task_hash, status);
```

---

## Implementation Units (Execution Order)

### Unit 1: Infrastructure (Day 1-2)

- [ ] Deploy AppFlowy docker-compose (`/home/chief/appflowy/`)
- [ ] Create council PostgreSQL database + schema
- [ ] Create AppFlowy workspace + 10 databases (8 original + execution_queue + health_monitor)
- [ ] Verify connectivity: `curl http://localhost:8080/api/health`
- [ ] Config: `config-subsystem.json` → `database_url` + `appflowy` section

### Unit 2: CouncilDatabase Core (Day 3-5)

- [ ] Write SQLAlchemy models (14 tables + execution_queue)
- [ ] Implement PipelineService (create, transition, find_active, archive, list)
- [ ] Implement ReviewDomain (start, log_finding, record_verdict, list_findings)
- [ ] Implement WorkService (upsert, finish, list_active)
- [ ] Implement RecallService (run_snapshot, recent_events, review_findings, similar_runs, context_slice)
- [ ] Implement MemoryService (get_recent_diary, consolidation_metrics, upsert_summary)
- [ ] Implement PromptService (upsert, get, list_by_model, render)
- [ ] Tests: Full pipeline lifecycle (RED→GREEN)

### Unit 3: AppFlowySync (Day 6-7)

- [ ] Implement `push_*()` methods using documented endpoints: `POST /database/{db}/row` (create), `PUT /database/{db}/row` (upsert)
- [ ] Implement `pull_changes()` using documented endpoints: `GET /database/{db}/row/updated` + `GET /database/{db}/row/detail`
- [ ] Add retry/backoff to all `push_*()` methods (exponential backoff, 3 retries, log warning on final failure)
- [ ] Wire into domain methods (PipelineService.create → push_work_item, etc.)
- [ ] Tests: Push → verify in AppFlowy UI
- [ ] Tests: Pull changes via `/row/updated` → verify council state update
- [ ] Tests: Push failure → verify council state unaffected (best-effort push)

### Unit 4: SlotSupervisor Rewrite (Day 8-10)

- [ ] Replace `self.relational_store` → `self.council_db`
- [ ] Replace `self.context_router` → `self.council_db.recall`
- [ ] Replace `self.memory_layer` → `self.council_db.memory`
- [ ] Replace `self.review_service` → `self.council_db.reviews`
- [ ] Update all transition calls (5→1)
- [ ] Update all review calls (fake→native)
- [ ] Wire `self.bridge = CouncilAppFlowyBridge(self.council_db, config)`
- [ ] Wire `self.bridge.enqueue_task()` in pipeline creation
- [ ] Wire `self.bridge.process_queue()` in pipeline handler
- [ ] Tests: Full council operation on PostgreSQL

### Unit 5: Arc Summarizer Integration (Day 11-12)

- [ ] Update ArcPipeline to use `council_db.memory` instead of RelationalStore
- [ ] Add `ModelContextEnrichment.build_context()` before consolidation POST
- [ ] Add `on_tier_complete` hook → `AppFlowySync.push_diary_entry()` + `create_document()`
- [ ] Add knowledge card injection → `AppFlowySync.push_knowledge_card()`
- [ ] Tests: Tiered consolidation → PostgreSQL → AppFlowy
- [ ] Tests: Context includes AppFlowy changes

### Unit 6: Sync and Integration (Day 13-14)

- [ ] Implement `EventIngestionService` (polling-only: `GET /row/updated` + `GET /row/detail`; Redis and PostgreSQL LISTEN channels removed)
- [ ] Implement `ExecutionQueue` (priority queue with deduplication)
- [ ] Implement `VoiceToWorkItem` (LLM task extraction + fallback)
- [ ] Implement `ModelContextEnrichment` (AppFlowy changes → Arc context)
- [ ] Implement `CouncilAppFlowyBridge` (unified integration layer)
- [ ] Wire voice_pipeline/http_server.py → VoiceToWorkItem handler
- [ ] Wire mcp_server.py → bridge.enqueue_task() endpoint
- [ ] Tests: Edit row in AppFlowy UI → polling detects change → council handler fires
- [ ] Tests: Voice command → structured task → pipeline execution
- [ ] Tests: Arc consolidation includes AppFlowy context
- [ ] Tests: Push failure → council state unaffected, AppFlowy shows stale data until recovery

### Unit 7: MCP Server Update (Day 15)

- [ ] Update MCP tools to use `CouncilDatabase` API
- [ ] Update MCP resources to query PostgreSQL
- [ ] Add MCP tools: queue.enqueue, queue.dequeue, queue.stats, bridge.status
- [ ] Tests: All 22+ tools functional

### Unit 8: Cleanup (Day 16)

- [ ] Remove SQLite RelationalStore, ContextRouter, ReviewService, MemoryLayer
- [ ] Remove migrations/ directory (PostgreSQL schema is in SQL file)
- [ ] Remove backward compat shims
- [ ] Update documentation
- [ ] Final integration test (full bidirectional flow)

---

## Configuration

```json
// config-subsystem.json — updated
{
  "database": {
    "url": "postgresql://council:council_pass@localhost:5433/council_db",
    "pool_size": 5,
    "max_overflow": 10,
    "pool_pre_ping": true
  },
  "appflowy": {
    "enabled": true,
    "base_url": "http://localhost:8080",
    "workspace_id": "council-workspace",
    "token": "council_jwt_secret_change_me",
    "databases": {
      "work_items": "db-uuid-1",
      "pipelines": "db-uuid-2",
      "reviews": "db-uuid-3",
      "findings": "db-uuid-4",
      "knowledge_base": "db-uuid-5",
      "session_diary": "db-uuid-6",
      "prompt_library": "db-uuid-7",
      "audit_log": "db-uuid-8",
      "execution_queue": "db-uuid-9",
      "health_monitor": "db-uuid-10"
    }
  },
  "bridge": {
    "enabled": true,
    "poll_interval_seconds": 30,
    "poll_retry_max": 3,
    "poll_retry_backoff_base_seconds": 2,
    "stale_warning_after_failures": 5,
    "conflict_policy": "council_wins"
  },
  "consolidation": {
    "model": "granite-4.1-3b",
    "server_url": "http://127.0.0.1:18095",
    "timeout_seconds": 120,
    "max_retries": 3,
    "fallback_to_main": true
  },
  "appflowy_ai": {
    "enabled": true,
    "provider": "arc_summarizer",
    "api_base": "http://host.docker.internal:18095/v1",
    "api_key": "local",
    "api_version": "2024-02-01",
    "default_model": "granite-4.1-3b",
    "fallback": {
      "enabled": false,
      "proxy_port": 8099,
      "cloud_provider": null
    }
  },
  "memindex": {
    "milvus_uri": "~/.council-memory/milvus.db",
    "graceful_degradation": true
  },
  "codegraph": {
    "db_path": "~/.council-memory/codegraph.db"
  }
}
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| PostgreSQL downtime | All council ops halt | Connection health checks, retry logic, fallback to queue |
| AppFlowy API changes | Sync adapter breaks | Feature flag (`appflowy.enabled`), graceful degradation |
| SQLAlchemy ORM overhead | Slight performance hit | Connection pooling, benchmark against SQLite baseline |
| AppFlowy learning curve | Team adoption friction | Pre-built databases + views, documentation |
| Data volume growth | PostgreSQL size increases | TTL phases, archival strategy, pg_partman for event_log |
| Port conflicts | Deployment fails | Fixed ports in plan (8080, 8443, 5433) |
| **Arc Summarizer performance** | AppFlowy AI responses slow (Granite-4.1-3B on Arc A380) | **Fallback: Add AI proxy (port 8099) routing to main LLM or cloud provider** |
| **Arc A380 downtime** | AppFlowy AI unavailable | Health gate + fallback to main llama.cpp (8091) |
| **AppFlowy AI endpoint mismatch** | Azure OpenAI config expects different API | `AI_AZURE_OPENAI_API_BASE` supports any OpenAI-compatible endpoint (verified) |
| **AppFlowy REST API changes** | `push_*()` or `pull_changes()` breaks | Endpoints are in OpenAPI spec (versioned); feature flag (`appflowy.enabled`) for graceful degradation; council state unaffected on push failure |
| **Polling latency** | AppFlowy→council sync up to 30s behind | Acceptable for visual layer; voice/critical tasks use direct council API (not AppFlowy UI) |
| **AppFlowy downtime** | `push_*()` fails silently | Exponential backoff (3 retries); council state is complete; AppFlowy shows last-pushed state until recovery |
| **AppFlowy → Council race conditions** | User edits in AppFlowy conflict with council state | Council-wins policy: council PostgreSQL is authoritative; conflicting AppFlowy edits are logged but not applied; non-conflicting edits (new work items) are accepted |
| **Queue deduplication failure** | Duplicate pipelines | task_hash + status check before pipeline creation |
| **Voice LLM extraction failure** | Poor task structure | Fallback heuristic extraction (keyword-based) |
| **AppFlowy → Council race conditions** | State conflicts | PostgreSQL transactions + SKIP LOCKED on queue dequeue |

---

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Data layer** | RelationalStore (SQLite CRUD) | CouncilDatabase (PostgreSQL, domain methods) |
| **Recall** | ContextRouter (raw SQL) | RecallService (SQLAlchemy queries) |
| **Reviews** | Fake pipelines | Native reviews table |
| **Work tracking** | Pipelines only | Unified work_items + execution queue |
| **Transitions** | 5 separate calls | 1 domain method |
| **AppFlowy** | Not deployed | docker-compose, 10 databases, bidirectional sync |
| **AppFlowy sync** | One-way push | Push on state change + polling via documented REST API (`GET /row/updated`) |
| **Task creation** | Council-only | AppFlowy dashboard, voice, manual, scheduled |
| **Arc Summarizer** | SQLite writes | PostgreSQL + AppFlowy documents + AppFlowy context |
| **Memory** | MemoryLayer (token slicing) | MemoryService (PostgreSQL queries) + AppFlowy awareness |
| **Prompts** | Inline strings | PromptService + AppFlowy Library |
| **Knowledge** | Ad-hoc extraction | Knowledge cards + AppFlowy KB + enrichment push |
| **Voice** | ASR→TTS only | Voice→task→queue→pipeline execution |
| **Backends** | SQLite + Milvus | PostgreSQL + Milvus + AppFlowy PostgreSQL (+ Redis for AppFlowy internal use only; council does not use Redis) |
| **Coupling** | Loose (bolted on) | Tight (council concepts are first-class) |
| **Backward compat** | SQLite migration path | None — fresh start |
| **AppFlowy AI** | Not deployed | Arc Summarizer (Granite-4.1-3B) via Azure OpenAI-compatible endpoint |

**Trade-off:** Tighter coupling means `CouncilDatabase` is council-specific. But it already is — the refactor just makes that explicit and eliminates the impedance mismatch between council logic and data access.

**No backward compatibility.** The SQLite DB is erased. All code paths go through CouncilDatabase. If something breaks, it's a bug — not a migration issue.
