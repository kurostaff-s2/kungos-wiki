# AppFlowy Integration Architecture v2.1

> **Date:** 2026-06-01  
> **Scope:** Same-machine, single-user deployment. Council PostgreSQL + AppFlowy Cloud (Docker).  
> **Policy:** No backward compatibility with SQLite. AppFlowy remains upgrade-safe: no fork, no undocumented table access, no direct SQL writes into AppFlowy-owned schemas.  
> **Status:** Finalized execution document, revised after validation review.

---

## 1. Purpose

This document defines the final execution-ready integration contract between Council and AppFlowy for the single-user deployment.

It replaces earlier ambiguous language around “one source of truth,” “council-wins,” and generalized sync services with a stricter model:

- Council is the canonical owner of shared business entities.
- AppFlowy is the visual workspace and editing surface.
- Every write to Council-owned data goes through the Council Core API.
- AppFlowy integration uses documented REST APIs only.
- Synchronization is intentionally minimal and pragmatic for single-user operation.

This v2.1 revision incorporates the validated review corrections: explicit lifecycle separation for `status`, missing base columns on `memory_rollups`, outbox idempotency protection, knowledge-card field policy, binding lifecycle rules, persisted snapshot hash semantics, and placeholder-only secrets handling. [file:35]

---

## 2. Design Principles

1. **One owner per dataset.** Each dataset has exactly one canonical owner.
2. **One canonical write path.** Every mutation to Council-owned data goes through the Council Core API.
3. **AppFlowy stays upgrade-safe.** Integration uses documented AppFlowy REST endpoints only.
4. **Revision-based concurrency.** Shared entities require `expected_revision`; stale writes return `409 conflict`.
5. **Field-level editability.** Only explicitly approved fields may be edited from AppFlowy.
6. **Transactional outbox.** Canonical write and outbound sync event are persisted in the same database transaction.
7. **Single-user pragmatism.** Reconciliation is a lightweight exception path, not a generalized workflow engine.
8. **No silent overwrite.** There is no blanket “council-wins” policy for shared editable fields.
9. **Lifecycle separation.** Entity-specific state lives in entity-specific state columns; generic `status` is reserved for soft lifecycle only. [file:35]
10. **Idempotent mutation contract.** Create, patch, and command endpoints all support idempotent retries. [file:35]

---

## 3. Target Topology

### 3.1 Runtime

```text
┌──────────────────────────────────────────────────────────────────┐
│                     Same Machine                                 │
│                                                                  │
│  ┌─────────────────────┐    ┌──────────────────────────────────┐ │
│  │  Council Services   │    │  AppFlowy Stack (docker-compose) │ │
│  │                     │    │                                  │ │
│  │  CouncilCoreAPI     │◄──►│  appflowy_cloud  (Rust, :8000)  │ │
│  │  ExecutionWorker    │    │  appflowy_web    (React, :3000) │ │
│  │  ReviewWorker       │    │  appflowy_worker (Rust)         │ │
│  │  MemoryWorker       │    │  gotrue           (auth)        │ │
│  │  OutboxDispatcher   │    │  appflowy_search (Rust, :4002)  │ │
│  │  AppFlowyInboundSync│    │  minio            (S3, :9000)   │ │
│  │  ArcPipeline        │    │  redis            (internal)    │ │
│  │  ArcClient          │    │  nginx            (:8080/:8443) │ │
│  │                     │    │                                  │ │
│  └─────────┬───────────┘    └──────────────┬───────────────────┘ │
│            │ REST API                       │                     │
│            ▼                                ▼                     │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  PostgreSQL Cluster (single instance)                    │    │
│  │                                                          │    │
│  │  council_core.*   — canonical business entities          │    │
│  │  council_ops.*    — execution telemetry, audit, jobs     │    │
│  │  council_sync.*   — bindings, outbox, inbound, conflicts │    │
│  │  appflowy_*.*     — AppFlowy-owned schemas               │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Milvus-lite — vector search                                    │
│  CodeGraph SQLite — FTS5                                        │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Database ownership

| Schema | Owner | Council Privilege | AppFlowy Privilege |
|---|---|---|---|
| `council_core` | Council | Full read/write | None |
| `council_ops` | Council | Full read/write | None |
| `council_sync` | Council | Full read/write | None |
| `appflowy_*` | AppFlowy | No write access; optional read-only diagnostics | Full read/write |

**Rule:** Council never writes directly into AppFlowy-owned schemas.

---

## 4. Ownership Matrix

| Dataset | Canonical Owner | Canonical Storage | AppFlowy Editable? | Canonical Write Path | Conflict Rule |
|---|---|---|---|---|---|
| Projects | Council Core | `council_core.projects` | Yes, approved metadata only | Council Core API | Revision check |
| Work items | Council Core | `council_core.work_items` | Yes, approved fields only | Council Core API | Revision + field allowlist |
| Workflow runs | Council Core | `council_core.workflow_runs` | No | Council Core API | Council-only |
| Workflow steps | Council Ops | `council_ops.workflow_steps` | No | Internal writer | Append/update internal only |
| Workflow artifacts | Council Ops | `council_ops.workflow_artifacts` | No direct edit | Internal writer | Council-only |
| Reviews | Council Core | `council_core.reviews` | Limited notes only | Council Core API | Council owns verdict/state |
| Review findings | Council Core | `council_core.review_findings` | Triage fields only | Council Core API | Revision on editable fields |
| Prompt templates | Council Core | `council_core.prompt_templates` | Yes | Council Core API | Revision check |
| Knowledge cards | Council Core | `council_core.knowledge_cards` | Yes, approved fields only | Council Core API | Revision + field allowlist [file:35] |
| Memory entries | Council Core | `council_core.memory_entries` | No | Council Core API | Council-only |
| Memory rollups | Council Core | `council_core.memory_rollups` | No | Council Core API | Council-only |
| Audit events | Council Ops | `council_ops.audit_events` | No | Internal writer | Append-only |
| System events | Council Ops | `council_ops.system_events` | No | Internal writer | Append-only |
| Job queue | Council Ops | `council_ops.job_queue` | No | Internal writer | Internal orchestration |
| Workspace/auth/folders/views | AppFlowy | `appflowy_*` | Yes | AppFlowy APIs | AppFlowy-owned |

---

## 5. Schema Contract

### 5.1 `council_core` — canonical business entities

Every table in `council_core` includes these required base columns:

```sql
id UUID PRIMARY KEY,
external_key TEXT NULL,
revision BIGINT NOT NULL DEFAULT 1,
created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
updated_by TEXT NOT NULL,
updated_source TEXT NOT NULL DEFAULT 'council',
origin_source TEXT NOT NULL DEFAULT 'council',
status TEXT NOT NULL DEFAULT 'active',
is_deleted BOOLEAN NOT NULL DEFAULT false
```

Allowed `updated_source` values:

- `council`
- `appflowy`
- `sync_worker`
- `system`

Allowed `status` values in `council_core` are restricted to soft lifecycle only:

- `active`
- `archived`

**Rule:** Entity-specific state belongs in the entity's own state column, such as `run_state`, `review_state`, or `finding_state`. `status` is not used for execution progress or review verdict state. Tables where a separate soft-lifecycle flag is unnecessary may omit `status` only by explicit design exception approved in this document. [file:35]

### 5.2 Core tables

#### `council_core.projects`

```sql
CREATE TABLE council_core.projects (
    id UUID PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
```

#### `council_core.work_items`

```sql
CREATE TABLE council_core.work_items (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES council_core.projects(id),
    parent_id UUID REFERENCES council_core.work_items(id),
    kind TEXT NOT NULL CHECK (kind IN ('pipeline','review','delegation','task','ad_hoc')),
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT CHECK (priority IN ('low','medium','high','critical')),
    phase TEXT NULL,
    assigned_to TEXT NULL,
    due_at TIMESTAMPTZ NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_work_items_project ON council_core.work_items(project_id);
CREATE INDEX idx_work_items_status ON council_core.work_items(status);
CREATE INDEX idx_work_items_kind_status ON council_core.work_items(kind, status);
```

#### `council_core.workflow_runs`

```sql
CREATE TABLE council_core.workflow_runs (
    id UUID PRIMARY KEY,
    work_item_id UUID NOT NULL REFERENCES council_core.work_items(id),
    project_id UUID NOT NULL REFERENCES council_core.projects(id),
    run_state TEXT NOT NULL DEFAULT 'queued'
        CHECK (run_state IN ('queued','running','succeeded','failed','cancelled')),
    current_phase TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT NULL,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_workflow_runs_work_item ON council_core.workflow_runs(work_item_id);
CREATE INDEX idx_workflow_runs_state ON council_core.workflow_runs(run_state);
```

#### `council_core.reviews`

```sql
CREATE TABLE council_core.reviews (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES council_core.projects(id),
    work_item_id UUID REFERENCES council_core.work_items(id),
    target_ref TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'open'
        CHECK (review_state IN ('open','in_progress','passed','failed','partial','dismissed')),
    verdict TEXT NULL,
    notes TEXT NULL,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_reviews_project ON council_core.reviews(project_id);
CREATE INDEX idx_reviews_state ON council_core.reviews(review_state);
```

#### `council_core.review_findings`

```sql
CREATE TABLE council_core.review_findings (
    id UUID PRIMARY KEY,
    review_id UUID NOT NULL REFERENCES council_core.reviews(id),
    finding_state TEXT NOT NULL DEFAULT 'open'
        CHECK (finding_state IN ('open','accepted','waived','fixed','duplicate')),
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    recommended_fix TEXT NULL,
    evidence TEXT NULL,
    owner_note TEXT NULL,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_findings_review ON council_core.review_findings(review_id);
CREATE INDEX idx_findings_severity ON council_core.review_findings(severity);
```

#### `council_core.prompt_templates`

```sql
CREATE TABLE council_core.prompt_templates (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    model_family TEXT NOT NULL,
    template_body TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    variables JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','draft','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_prompts_model ON council_core.prompt_templates(model_family);
```

#### `council_core.knowledge_cards`

```sql
CREATE TABLE council_core.knowledge_cards (
    id UUID PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    confidence DOUBLE PRECISION NULL,
    source_run_id UUID REFERENCES council_core.workflow_runs(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_knowledge_topic ON council_core.knowledge_cards USING GIN(tags);
```

#### `council_core.memory_entries`

```sql
CREATE TABLE council_core.memory_entries (
    id UUID PRIMARY KEY,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('raw','summary','diary','incident','decision')),
    tier TEXT NOT NULL CHECK (tier IN ('daily','short','weekly','bimonthly','manual')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_run_id UUID REFERENCES council_core.workflow_runs(id),
    expires_at TIMESTAMPTZ NULL,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_memory_tier ON council_core.memory_entries(tier);
CREATE INDEX idx_memory_expires ON council_core.memory_entries(expires_at);
```

#### `council_core.memory_rollups`

```sql
CREATE TABLE council_core.memory_rollups (
    id UUID PRIMARY KEY,
    tier TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    content TEXT NOT NULL,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NULL,
    external_key TEXT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    updated_source TEXT NOT NULL DEFAULT 'council',
    origin_source TEXT NOT NULL DEFAULT 'council',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_rollups_tier ON council_core.memory_rollups(tier);
```

### 5.3 `council_ops` — operational state

`council_ops` tables are operational and append-only or orchestration-oriented by design, and intentionally omit the revision-based concurrency columns from the `council_core` base contract. [file:35]

#### `council_ops.workflow_steps`

```sql
CREATE TABLE council_ops.workflow_steps (
    id UUID PRIMARY KEY,
    workflow_run_id UUID NOT NULL REFERENCES council_core.workflow_runs(id),
    phase TEXT NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    outcome TEXT NOT NULL CHECK (outcome IN ('success','failure','retreat','retry','cancelled')),
    error_text TEXT NULL,
    duration_ms DOUBLE PRECISION NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    UNIQUE (workflow_run_id, phase, attempt_number)
);
CREATE INDEX idx_steps_run ON council_ops.workflow_steps(workflow_run_id);
```

#### `council_ops.workflow_artifacts`

```sql
CREATE TABLE council_ops.workflow_artifacts (
    id UUID PRIMARY KEY,
    workflow_run_id UUID NOT NULL REFERENCES council_core.workflow_runs(id),
    artifact_key TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    content_uri TEXT NULL,
    inline_content TEXT NULL,
    sha256 TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_artifacts_run ON council_ops.workflow_artifacts(workflow_run_id);
CREATE INDEX idx_artifacts_run_key ON council_ops.workflow_artifacts(workflow_run_id, artifact_key);
```

#### `council_ops.system_events`

```sql
CREATE TABLE council_ops.system_events (
    id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    entity_type TEXT NULL,
    entity_id UUID NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_type ON council_ops.system_events(event_type, severity);
CREATE INDEX idx_events_time ON council_ops.system_events(occurred_at DESC);
```

#### `council_ops.audit_events`

```sql
CREATE TABLE council_ops.audit_events (
    id UUID PRIMARY KEY,
    actor TEXT NOT NULL,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NULL,
    request_id TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_code INTEGER NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_time ON council_ops.audit_events(occurred_at DESC);
```

#### `council_ops.job_queue`

```sql
CREATE TABLE council_ops.job_queue (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    job_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (job_state IN ('pending','running','done','failed','dead_letter')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_state ON council_ops.job_queue(job_state, available_at)
    WHERE job_state = 'pending';
```

**Clarification:** `job_queue` is worker orchestration state only. It is not a business record and is never projected as a canonical entity.

### 5.4 `council_sync` — integration surface

This schema is intentionally minimal for single-user deployment.

#### Core tables

1. `appflowy_bindings`
2. `outbox_events`
3. `inbound_changes` only if AppFlowy-to-Council editing is enabled

#### Optional table

4. `sync_conflicts` as a lightweight exception log

#### `council_sync.appflowy_bindings`

```sql
CREATE TABLE council_sync.appflowy_bindings (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL,
    council_id UUID NOT NULL,
    appflowy_database_id TEXT NOT NULL,
    appflowy_row_id TEXT NOT NULL,
    last_synced_revision BIGINT,
    last_seen_cells_hash TEXT NULL,
    state TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active','orphaned','disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_type, council_id),
    UNIQUE (appflowy_database_id, appflowy_row_id)
);
```

#### Binding lifecycle

1. **Auto-projection on Council create:** when an entity type is configured for AppFlowy projection, the create path writes the canonical row first, then creates an outbox event. The dispatcher creates the AppFlowy row if no binding exists, captures the returned `appflowy_row_id`, and stores the binding. [file:35]
2. **Manual binding:** an operator may link an existing Council entity to an existing AppFlowy row through an admin-only command that validates entity type, database ID, and row ID before inserting the binding. [file:35]
3. **Unbound entities:** a Council entity without a binding remains canonical and valid but is not visible in AppFlowy until projected or manually linked. [file:35]
4. **Orphaned bindings:** if a bound AppFlowy row or database is deleted or inaccessible, the binding is marked `state = 'orphaned'`, logged to `sync_conflicts` or `system_events`, and excluded from normal outbound delivery until repaired. [file:35]

#### `council_sync.outbox_events`

```sql
CREATE TABLE council_sync.outbox_events (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL,
    council_id UUID NOT NULL,
    mutation_type TEXT NOT NULL CHECK (mutation_type IN ('created','updated','deleted')),
    payload_revision BIGINT NOT NULL,
    payload JSONB NOT NULL,
    delivery_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (delivery_state IN ('pending','sent','failed','dead_letter')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_type, council_id, mutation_type, payload_revision)
);
CREATE INDEX idx_outbox_pending ON council_sync.outbox_events(delivery_state, available_at)
    WHERE delivery_state = 'pending';
CREATE INDEX idx_outbox_entity ON council_sync.outbox_events(entity_type, council_id);
```

#### `council_sync.inbound_changes`

```sql
CREATE TABLE council_sync.inbound_changes (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL,
    council_id UUID NOT NULL,
    appflowy_row_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB NOT NULL,
    revision_at_change BIGINT,
    expected_revision BIGINT,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending','applied','rejected','skipped')),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inbound_pending ON council_sync.inbound_changes(state)
    WHERE state = 'pending';
```

#### `council_sync.sync_conflicts` (optional)

```sql
CREATE TABLE council_sync.sync_conflicts (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL,
    council_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    council_value JSONB NOT NULL,
    appflowy_value JSONB NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('stale_revision','forbidden_field','mapping_drift','missing_binding')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 6. Canonical API Contract

Council Core API is the only write boundary for all Council-owned shared data.

### 6.1 Resource rules

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/<resource>` | Create; requires `Idempotency-Key` |
| `GET` | `/v1/<resource>/{id}` | Fetch canonical state |
| `PATCH` | `/v1/<resource>/{id}` | Partial update with `expected_revision` and `Idempotency-Key` [file:35] |
| `POST` | `/v1/<resource>/{id}/commands/<cmd>` | Non-CRUD transition; requires `Idempotency-Key` |
| `GET` | `/v1/<resource>?updated_since=...` | Sync/export |

### 6.2 Required headers

| Header | Required on | Purpose |
|---|---|---|
| `Idempotency-Key` | Create, patch, and command endpoints | Prevent duplicate mutation and duplicate outbox rows [file:35] |
| `X-Source-System` | All writes | `council`, `appflowy`, `sync_worker`, `system` |
| `X-Actor-Id` | All writes | Audit attribution |

### 6.3 Update example

```http
PATCH /v1/work-items/0c7d...
X-Source-System: appflowy
X-Actor-Id: user-1
Idempotency-Key: 7df090c6-5d1d-4f83-85af-d43df5f6e1d7
Content-Type: application/json

{
  "expected_revision": 12,
  "patch": {
    "title": "Tighten AppFlowy sync contract",
    "priority": "high",
    "due_at": "2026-06-04T12:00:00Z",
    "tags": ["appflowy", "sync"]
  }
}
```

Successful response:

```json
{
  "id": "0c7d...",
  "revision": 13,
  "updated_source": "appflowy",
  "status": "active"
}
```

### 6.4 Conflict responses

| Code | Meaning | Action |
|---|---|---|
| `200` | Applied; revision incremented | Normal |
| `409` | Stale `expected_revision` | Refetch and retry manually or via worker |
| `403` | Forbidden field edit | Log conflict, reject |
| `202` | Needs human review | Record conflict or route to inbox |

---

## 7. AppFlowy Integration Contract

### 7.1 Outbound flow: Council → AppFlowy

```text
1. Council Core writes canonical row + outbox event in one transaction.
2. OutboxDispatcher selects pending events with FOR UPDATE SKIP LOCKED.
3. Dispatcher resolves binding via council_sync.appflowy_bindings.
4. If binding is missing and auto-projection is enabled, Dispatcher creates the AppFlowy row and stores the binding.
5. Dispatcher calls documented AppFlowy REST endpoint.
6. Dispatcher marks event sent or failed/dead_letter.
7. Binding.last_synced_revision is updated after successful delivery.
```

Transactional pattern:

```sql
BEGIN;
UPDATE council_core.work_items
SET title = :title,
    revision = revision + 1,
    updated_at = now(),
    updated_by = :actor,
    updated_source = :source
WHERE id = :id
  AND revision = :expected_revision;

INSERT INTO council_sync.outbox_events (
    id, entity_type, council_id, mutation_type, payload_revision, payload
) VALUES (
    :event_id, 'work_item', :id, 'updated', :new_revision, :payload::jsonb
);
COMMIT;
```

### 7.2 Inbound flow: AppFlowy → Council

```text
1. AppFlowyInboundSync polls AppFlowy documented row-updated endpoint.
2. For each changed row, it fetches full row detail.
3. It resolves the row binding.
4. It canonicalizes the cells payload and computes a snapshot hash.
5. It compares the snapshot hash to binding.last_seen_cells_hash.
6. For each changed editable field:
   a. allowlist check
   b. mapping transform
   c. expected_revision check
   d. PATCH to Council Core API
7. It records applied/rejected/skipped result.
8. It updates binding.last_seen_cells_hash.
```

**Important:** Inbound diffing must not rely only on process memory. `last_seen_cells_hash` in `appflowy_bindings` is the persisted restart-safe mechanism. [file:35]

### 7.3 Snapshot hash contract

`last_seen_cells_hash` is computed as **SHA-256 over canonical JSON** of the full AppFlowy cell payload for the row, with these rules: [file:35]

1. Object keys sorted lexicographically.
2. No insignificant whitespace.
3. Stable serialization for arrays in their original AppFlowy-provided order unless the field type is explicitly order-insensitive.
4. Nulls preserved.
5. UTF-8 encoding before hashing.

This hash is used only for restart-safe change detection, not for conflict resolution authority. [file:35]

### 7.4 Documented AppFlowy endpoints used

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/workspace/{ws}/database/{db}/row` | `POST` | Create row |
| `/api/workspace/{ws}/database/{db}/row` | `PUT` | Update or upsert row |
| `/api/workspace/{ws}/database/{db}/row/updated` | `GET` | Detect recently changed rows |
| `/api/workspace/{ws}/database/{db}/row/detail` | `GET` | Fetch full row cells |
| `/api/workspace/{ws}/database/{db}/fields` | `GET` | Fetch field definitions |
| `/api/workspace/{ws}/database/{db}` | `GET` | Discover databases |

### 7.5 Field-level write policy

#### Work items

| Field | Council Edit | AppFlowy Edit |
|---|---|---|
| `title` | Yes | Yes |
| `description` | Yes | Yes |
| `priority` | Yes | Yes |
| `due_at` | Yes | Yes |
| `tags` | Yes | Yes |
| `assigned_to` | Yes | Yes |
| `kind` | Yes | No |
| `phase` | Yes | No |
| `metadata` | Yes | No |
| `status` | Yes | No |

#### Reviews and findings

| Field | Council Edit | AppFlowy Edit |
|---|---|---|
| `notes` | Yes | Yes |
| `finding_state` | Yes | Yes, triage only |
| `owner_note` | Yes | Yes |
| `review_state` | Yes | No |
| `verdict` | Yes | No |
| `severity` | Yes | No |
| `evidence` | Yes | No |

#### Prompt templates

| Field | Council Edit | AppFlowy Edit |
|---|---|---|
| `name` | Yes | Yes |
| `template_body` | Yes | Yes |
| `tags` | Yes | Yes |
| `status` | Yes | Yes |
| `usage_metrics` | Yes | No |

#### Knowledge cards

| Field | Council Edit | AppFlowy Edit |
|---|---|---|
| `title` | Yes | Yes |
| `body` | Yes | Yes |
| `tags` | Yes | Yes |
| `confidence` | Yes | No |
| `source_run_id` | Yes | No |
| `metadata` | Yes | No |
| `topic` | Yes | No |
| `status` | Yes | No |

---

## 8. Field Mapping Appendix

Every AppFlowy database must have an explicit field map checked into source control.

### 8.1 Work items map

| Council Field | AppFlowy Column | Editable in AppFlowy | Notes |
|---|---|---|---|
| `id` | hidden/internal binding | No | Stored in binding table, not user-editable |
| `title` | `Title` | Yes | Primary row title |
| `description` | `Description` | Yes | Rich text or long text |
| `priority` | `Priority` | Yes | Select mapped to enum |
| `due_at` | `Due Date` | Yes | Timestamp/date mapping |
| `tags` | `Tags` | Yes | Multi-select/text list |
| `assigned_to` | `Assigned To` | Yes | Text for single-user v2 |
| `kind` | `Kind` | No | Read-only display |
| `phase` | `Phase` | No | Read-only display |
| `status` | `Status` | No | Read-only soft lifecycle |

### 8.2 Reviews map

| Council Field | AppFlowy Column | Editable in AppFlowy | Notes |
|---|---|---|---|
| `target_ref` | `Target` | No | Display only |
| `reviewer` | `Reviewer` | No | Display only |
| `review_state` | `State` | No | Council-owned |
| `verdict` | `Verdict` | No | Council-owned |
| `notes` | `Notes` | Yes | Human annotation |

### 8.3 Findings map

| Council Field | AppFlowy Column | Editable in AppFlowy | Notes |
|---|---|---|---|
| `title` | `Title` | No | Display only |
| `summary` | `Summary` | No | Display only |
| `severity` | `Severity` | No | Council-owned |
| `finding_state` | `State` | Yes | Triage field |
| `owner_note` | `Owner Note` | Yes | Human note |
| `recommended_fix` | `Recommended Fix` | No | Display only |
| `evidence` | `Evidence` | No | Display only |

### 8.4 Prompt templates map

| Council Field | AppFlowy Column | Editable in AppFlowy | Notes |
|---|---|---|---|
| `name` | `Name` | Yes | Template label |
| `model_family` | `Model Family` | No | Display only unless future approval |
| `template_body` | `Template Body` | Yes | Main editable content |
| `tags` | `Tags` | Yes | Multi-select/text list |
| `status` | `Status` | Yes | Draft/active/archived |

### 8.5 Knowledge cards map

| Council Field | AppFlowy Column | Editable in AppFlowy | Notes |
|---|---|---|---|
| `topic` | `Topic` | No | Display only |
| `title` | `Title` | Yes | Editable human-facing title |
| `body` | `Body` | Yes | Main content |
| `tags` | `Tags` | Yes | Multi-select/text list |
| `confidence` | `Confidence` | No | Derived/system-owned |
| `source_run_id` | `Source Run` | No | Derived/system-owned |
| `metadata` | hidden/internal | No | Not user-editable |

---

## 9. Services

### 9.1 Final service inventory

| Service | Purpose | File |
|---|---|---|
| `CouncilCoreAPI` | Canonical write boundary | `api/core.py` |
| `ExecutionWorker` | Workflow execution | `workers/execution.py` |
| `ReviewWorker` | Review execution | `workers/review.py` |
| `MemoryWorker` | Memory consolidation and rollups | `workers/memory.py` |
| `OutboxDispatcher` | Pushes canonical changes to AppFlowy | `workers/outbox.py` |
| `AppFlowyInboundSync` | Polls AppFlowy and submits allowed edits to Council Core API | `workers/inbound.py` |

### 9.2 Removed services

| Removed | Replaced By | Reason |
|---|---|---|
| `AppFlowyOutboundSync` | `OutboxDispatcher` | Outbox already tracks outbound state |
| `InboundMutationService` | `AppFlowyInboundSync` | Simplified single-user normalization |
| `ReconciliationService` | `sync_conflicts` or inbox | Single-user exceptions do not justify a service |

---

## 10. Reference Worker Contracts

### 10.1 `AppFlowyInboundSync`

```python
FIELD_ALLOWLIST = {
    "work_item": {"title", "description", "priority", "due_at", "tags", "assigned_to"},
    "review": {"notes"},
    "review_finding": {"finding_state", "owner_note"},
    "prompt_template": {"name", "template_body", "tags", "status"},
    "knowledge_card": {"title", "body", "tags"},
}
```

Execution rules:

1. Pull changed rows from AppFlowy.
2. Resolve binding.
3. Canonicalize cell payload.
4. Compute SHA-256 snapshot hash.
5. Compare with `last_seen_cells_hash`; skip if unchanged.
6. For changed fields, enforce allowlist.
7. Fetch canonical entity and verify `expected_revision`.
8. Apply mapped patch via Council Core API.
9. Record result in `inbound_changes` if enabled.
10. Persist new snapshot hash.

### 10.2 `OutboxDispatcher`

Execution rules:

1. Select pending outbox events ordered by `available_at`.
2. Resolve binding or create binding if auto-projection is enabled.
3. Call AppFlowy REST update.
4. On success, set `delivery_state = 'sent'` and update `last_synced_revision`.
5. On transient failure, increment attempts and back off.
6. After max retries, move to `dead_letter`.

Backoff policy:

- Base delay: 2 seconds
- Retry sequence: 2s, 4s, 8s
- Max attempts: 3
- After third failure: `dead_letter`

---

## 11. Deployment Contract

### 11.1 AppFlowy stack

AppFlowy runs in Docker with `nginx`, `postgres`, `redis`, `gotrue`, `appflowy_cloud`, `appflowy_worker`, `appflowy_search`, and `appflowy_web`.

### 11.2 Council database connection

Council connects to the same PostgreSQL cluster used by AppFlowy, but only owns its own schemas.

```python
DATABASE_URL = "postgresql://council_app:{{COUNCIL_DB_PASSWORD}}@postgres:5432/appflowy"
```

**Security rule:** credentials shown in this document are placeholders only. Real values must come from environment variables, Docker secrets, or a secrets manager. [file:35]

### 11.3 PostgreSQL privileges

```sql
CREATE ROLE council_app WITH LOGIN PASSWORD '{{COUNCIL_DB_PASSWORD}}';
GRANT CONNECT ON DATABASE appflowy TO council_app;

CREATE SCHEMA IF NOT EXISTS council_core AUTHORIZATION council_app;
CREATE SCHEMA IF NOT EXISTS council_ops AUTHORIZATION council_app;
CREATE SCHEMA IF NOT EXISTS council_sync AUTHORIZATION council_app;

REVOKE ALL ON SCHEMA appflowy_public FROM council_app;
GRANT USAGE ON SCHEMA appflowy_public TO council_app;
GRANT SELECT ON ALL TABLES IN SCHEMA appflowy_public TO council_app;
```

**Rule:** Council has no write privileges to AppFlowy schemas.

---

## 12. Implementation Sequence

### Phase 1: Foundation

1. Create `council_core`, `council_ops`, and `council_sync` schemas.
2. Create canonical tables and indexes.
3. Create `council_app` role and lock down AppFlowy schema permissions.
4. Implement `CouncilCoreAPI` with revision-aware `POST`, `GET`, `PATCH`, and command endpoints.
5. Require `Idempotency-Key` on create, patch, and command mutations. [file:35]

### Phase 2: Projection to AppFlowy

1. Create AppFlowy databases for work items, reviews, findings, prompts, and knowledge cards.
2. Check in entity field maps.
3. Implement `appflowy_bindings` lifecycle logic.
4. Implement transactional outbox writes from Council Core API with `payload_revision`.
5. Implement `OutboxDispatcher`.

### Phase 3: Inbound edits

1. Enable only the approved editable fields.
2. Implement polling via documented AppFlowy row update endpoints.
3. Persist `last_seen_cells_hash` in bindings.
4. Implement canonical JSON hashing and SHA-256 snapshot generation. [file:35]
5. Implement revision-aware PATCH flow to Council Core API.
6. Enable `inbound_changes` and optional `sync_conflicts` logging.

### Phase 4: Hardening

1. Add dead-letter inspection view.
2. Add structured operational dashboards in AppFlowy.
3. Add retry and alert metrics.
4. Verify restart safety and idempotency.
5. Add orphaned-binding detection scan.

---

## 13. Non-Goals

These are explicitly out of scope for v2.1:

- Multi-user collaborative conflict resolution
- General-purpose bidirectional sync engine
- Direct SQL integration with AppFlowy internal tables
- AppFlowy schema customization through undocumented internals
- Semantic auto-merge beyond simple field-level revision rules

---

## 14. Acceptance Criteria

The integration is considered complete only when all conditions below are true:

1. Council can create and update canonical entities without any direct writes to AppFlowy schemas.
2. Every outbound projection to AppFlowy is driven by `outbox_events`.
3. A failed AppFlowy API call cannot lose the canonical change.
4. Duplicate retry of the same create, patch, or command mutation does not create duplicate outbox rows. [file:35]
5. AppFlowy edits to approved fields are routed through Council Core API with `expected_revision`.
6. Forbidden AppFlowy edits are rejected and logged.
7. Restarting the inbound worker does not lose change detection because snapshot state is persisted.
8. `kind`, `phase`, verdict fields, and other Council-only fields cannot be mutated from AppFlowy.
9. Knowledge-card editable fields and non-editable fields match both the policy tables and the inbound allowlist. [file:35]
10. AppFlowy can be upgraded independently because integration depends only on documented REST endpoints.

---

## 15. Final Decisions

- Use one PostgreSQL cluster for operations convenience.
- Keep strict schema ownership boundaries.
- Use Council Core API as the sole canonical write path.
- Keep AppFlowy as upgrade-safe visual workspace.
- Keep `council_sync` minimal: bindings, outbox, inbound; conflicts optional.
- Persist inbound snapshot hash in the database.
- Use SHA-256 over canonical JSON for persisted row snapshot hashing. [file:35]
- Require idempotency support on patch mutations as well as create and command paths. [file:35]
- Treat `status` as soft lifecycle only; treat entity-specific state as separate domain state. [file:35]
- Do not use a generalized reconciliation service for single-user deployment.

This is the final v2.1 execution contract.
