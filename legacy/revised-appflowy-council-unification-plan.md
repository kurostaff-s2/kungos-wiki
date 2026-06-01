# AppFlowy + Council Unified Execution Plan (Revised)

## Status

Revised execution-ready plan for a same-machine, single-user deployment that prioritizes:

- Maximum AppFlowy repo upgradability.
- Maximum practical bidirectionality.
- Clear ownership boundaries.
- One canonical write path for shared business data.
- A refactored Council PostgreSQL model aligned to bounded contexts and consistent naming.

## Executive Summary

This revision replaces the ambiguous “single source of truth + REST sync + council-wins” model with a stricter contract:

- Shared business entities have one canonical owner: **Council Core** in PostgreSQL.
- AppFlowy remains **AppFlowy-owned** for workspace, documents, views, auth, and internal UI tables.
- Bidirectionality is achieved by routing **both Council-originated and AppFlowy-originated edits** through the same canonical API contract, not by letting two databases co-own the same rows.[cite:7][cite:9]
- A single PostgreSQL **cluster** may host both AppFlowy schemas and Council schemas for operational simplicity, but schema ownership stays strict.
- No direct SQL writes into AppFlowy-owned tables are required for normal operation.
- AppFlowy remains upgradeable with standard container upgrades because integration occurs through documented APIs and explicit mappings, not internal table coupling.[cite:7]

## Design Principles

1. **One owner per dataset**: each dataset has one canonical owner; split datasets smaller if needed until ownership is unambiguous.[cite:9]
2. **One canonical write path**: every accepted mutation for shared business data goes through Council Core API.
3. **AppFlowy owns AppFlowy**: AppFlowy internal schemas, auth, documents, boards, views, folders, and workspace metadata are AppFlowy-managed.
4. **Council owns Council domain state**: workflow execution, reviews, findings, artifacts, machine memory, prompts, and knowledge data remain Council-governed.
5. **Bidirectionality without dual ownership**: AppFlowy can initiate edits, but it does not become a second canonical datastore for Council business entities.[cite:7]
6. **Field-level editability**: some entities are shared, but not every field on those entities is editable from every surface.
7. **Optimistic concurrency over silent overwrite**: blanket `council-wins` is removed for shared fields; revision checks and explicit conflict handling are required.[cite:7]
8. **Upgrade-safe integration**: avoid writing to undocumented AppFlowy tables.

## Non-Goals

- No direct joint ownership of identical rows across two systems.
- No reliance on undocumented AppFlowy table internals for canonical business logic.
- No polling-based overwrite loop presented as “true single source of truth.”
- No requirement to preserve legacy SQLite compatibility.

## Target Topology

### Runtime Topology

- One PostgreSQL cluster.
- One AppFlowy stack (Cloud/Web/Worker/Search/GoTrue/Redis/MinIO).
- One Council service set (Core API, execution workers, sync workers, summarizer integrations).
- One Milvus-lite instance for vector search.
- One CodeGraph SQLite/FTS store remains separate.

### Database Topology

PostgreSQL cluster contains these ownership zones:

- `appflowy_*` schemas: owned by AppFlowy services.
- `council_core` schema: canonical shared business entities.
- `council_ops` schema: execution telemetry, audit, outbox, background processing.
- `council_sync` schema: mappings, cursors, incoming mutations, reconciliation records.

This gives operational unity while preserving ownership clarity.

## Ownership Matrix

| Dataset / Concern | Canonical owner | Canonical storage | May be edited from Council UI / workers | May be edited from AppFlowy UI | Write path | Conflict rule | Notes |
|---|---|---|---|---|---|---|---|
| Projects | Council Core | `council_core.projects` | Yes | Yes | Council Core API | Revision check; manual reconcile if stale | AppFlowy may expose project metadata as a database row |
| Work items | Council Core | `council_core.work_items` | Yes | Yes | Council Core API | Revision check; field-level merge | This is the main shared planning object |
| Workflow runs | Council Core | `council_core.workflow_runs` | Yes | No direct edits | Council Core API | Council-only | Display in AppFlowy as read model |
| Workflow steps / state transitions | Council Core | `council_ops.workflow_steps` | Yes | No | Council Core API | Council-only | Operational execution history |
| Workflow artifacts | Council Core | `council_ops.workflow_artifacts` | Yes | Limited attach/comment only | Council Core API | Council-only for generated content | Human annotations may live separately |
| Reviews | Council Core | `council_core.reviews` | Yes | Limited | Council Core API | Council owns verdict fields | AppFlowy may edit review notes / dispositions if mapped |
| Review findings | Council Core | `council_core.review_findings` | Yes | Yes for triage fields only | Council Core API | Shared triage fields use revision check | Severity/evidence may remain Council-controlled |
| Prompt templates | Council Core | `council_core.prompt_templates` | Yes | Yes | Council Core API | Revision check | AppFlowy document/database is editing surface, not owner |
| Knowledge cards | Council Core | `council_core.knowledge_cards` | Yes | Yes | Council Core API | Revision check | Human edits allowed on title/tags/notes; provenance stays Council-owned |
| Memory entries / session diary | Council Core | `council_core.memory_entries` | Yes | Limited | Council Core API | Council-owned body, AppFlowy comments optional | Consolidated memory remains canonical in Council |
| Consolidation tiers / rollups | Council Core | `council_core.memory_rollups` | Yes | No direct edits | Council Core API | Council-only | Display-only in AppFlowy |
| Audit events | Council Ops | `council_ops.audit_events` | Yes | No | Council Core API / internal writer | Append-only | Not user-editable |
| System events | Council Ops | `council_ops.system_events` | Yes | No | Internal writer | Append-only | Replaces overloaded event log semantics |
| Sync cursors / bindings | Council Sync | `council_sync.*` | Yes | No | Sync service only | Internal | Integration plumbing |
| AppFlowy workspace / auth / folders / board config / views | AppFlowy | `appflowy_*` | No direct writes | Yes | AppFlowy APIs | AppFlowy-owned | Council may read via API or read-only DB access if needed |
| AppFlowy documents / blocks | AppFlowy | `appflowy_*` | Only through documented AppFlowy API | Yes | AppFlowy APIs + mapping layer | AppFlowy-owned structure; canonical business content may map back to Council Core | Do not treat raw blocks as canonical Council state |

## Canonical Data Contract

Every Council-owned canonical entity uses the same base contract.

### Required Base Columns

- `id UUID PRIMARY KEY`
- `external_key TEXT NULL`
- `revision BIGINT NOT NULL DEFAULT 1`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_by TEXT NOT NULL`
- `updated_source TEXT NOT NULL` — e.g. `council`, `appflowy`, `sync_worker`, `system`
- `origin_source TEXT NOT NULL`
- `status TEXT NOT NULL`
- `is_deleted BOOLEAN NOT NULL DEFAULT false`

### Required Mutation Semantics

- Every mutable request must include either `expected_revision` or an idempotency key.
- Successful write increments `revision`.
- Rejected stale writes return `409 conflict`.
- System-generated side effects are emitted to an outbox in the same transaction.
- Source attribution is mandatory for all writes.

## Revised PostgreSQL Schema Contract

### Schema 1: `council_core`

This schema stores canonical business data that may be shared across Council and AppFlowy.

#### `council_core.projects`
- `id UUID PK`
- `slug TEXT UNIQUE`
- `name TEXT NOT NULL`
- `description TEXT`
- `status TEXT NOT NULL CHECK (status IN ('active','paused','archived'))`
- base columns

#### `council_core.work_items`
- `id UUID PK`
- `project_id UUID NOT NULL REFERENCES council_core.projects(id)`
- `parent_id UUID NULL REFERENCES council_core.work_items(id)`
- `kind TEXT NOT NULL CHECK (kind IN ('pipeline','review','delegation','task','ad_hoc'))`
- `title TEXT NOT NULL`
- `description TEXT`
- `priority TEXT CHECK (priority IN ('low','medium','high','critical'))`
- `status TEXT NOT NULL CHECK (status IN ('active','blocked','done','failed','cancelled'))`
- `phase TEXT NULL`
- `assigned_to TEXT NULL`
- `due_at TIMESTAMPTZ NULL`
- `tags TEXT[] NOT NULL DEFAULT '{}'`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- base columns

#### `council_core.workflow_runs`
- `id UUID PK`
- `work_item_id UUID NOT NULL REFERENCES council_core.work_items(id)`
- `project_id UUID NOT NULL REFERENCES council_core.projects(id)`
- `run_state TEXT NOT NULL CHECK (run_state IN ('queued','running','succeeded','failed','cancelled'))`
- `current_phase TEXT NULL`
- `started_at TIMESTAMPTZ NULL`
- `finished_at TIMESTAMPTZ NULL`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `summary TEXT NULL`
- base columns

#### `council_core.reviews`
- `id UUID PK`
- `project_id UUID NOT NULL REFERENCES council_core.projects(id)`
- `work_item_id UUID NULL REFERENCES council_core.work_items(id)`
- `target_ref TEXT NOT NULL`
- `reviewer TEXT NOT NULL`
- `review_state TEXT NOT NULL CHECK (review_state IN ('open','in_progress','passed','failed','partial','dismissed'))`
- `verdict TEXT NULL`
- `notes TEXT NULL`
- base columns

#### `council_core.review_findings`
- `id UUID PK`
- `review_id UUID NOT NULL REFERENCES council_core.reviews(id)`
- `finding_state TEXT NOT NULL CHECK (finding_state IN ('open','accepted','waived','fixed','duplicate'))`
- `severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info'))`
- `title TEXT NOT NULL`
- `summary TEXT NOT NULL`
- `recommended_fix TEXT NULL`
- `evidence TEXT NULL`
- `owner_note TEXT NULL`
- base columns

#### `council_core.prompt_templates`
- `id UUID PK`
- `name TEXT NOT NULL`
- `model_family TEXT NOT NULL`
- `template_body TEXT NOT NULL`
- `status TEXT NOT NULL CHECK (status IN ('active','draft','archived'))`
- `tags TEXT[] NOT NULL DEFAULT '{}'`
- `variables JSONB NOT NULL DEFAULT '{}'::jsonb`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- base columns

#### `council_core.knowledge_cards`
- `id UUID PK`
- `topic TEXT NOT NULL`
- `title TEXT NOT NULL`
- `body TEXT NOT NULL`
- `tags TEXT[] NOT NULL DEFAULT '{}'`
- `confidence DOUBLE PRECISION NULL`
- `source_run_id UUID NULL REFERENCES council_core.workflow_runs(id)`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- base columns

#### `council_core.memory_entries`
- `id UUID PK`
- `entry_type TEXT NOT NULL CHECK (entry_type IN ('raw','summary','diary','incident','decision'))`
- `tier TEXT NOT NULL CHECK (tier IN ('daily','short','weekly','bimonthly','manual'))`
- `title TEXT NOT NULL`
- `body TEXT NOT NULL`
- `sections JSONB NOT NULL DEFAULT '{}'::jsonb`
- `source_run_id UUID NULL REFERENCES council_core.workflow_runs(id)`
- `expires_at TIMESTAMPTZ NULL`
- base columns

#### `council_core.memory_rollups`
- `id UUID PK`
- `tier TEXT NOT NULL`
- `window_start TIMESTAMPTZ NOT NULL`
- `window_end TIMESTAMPTZ NOT NULL`
- `content TEXT NOT NULL`
- `summary JSONB NOT NULL DEFAULT '{}'::jsonb`
- `expires_at TIMESTAMPTZ NULL`
- base columns

### Schema 2: `council_ops`

This schema stores operational state and append-only records.

#### `council_ops.workflow_steps`
- `id UUID PK`
- `workflow_run_id UUID NOT NULL REFERENCES council_core.workflow_runs(id)`
- `phase TEXT NOT NULL`
- `attempt_number INTEGER NOT NULL DEFAULT 1`
- `outcome TEXT NOT NULL CHECK (outcome IN ('success','failure','retreat','retry','cancelled'))`
- `error_text TEXT NULL`
- `duration_ms DOUBLE PRECISION NULL`
- `started_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `finished_at TIMESTAMPTZ NULL`
- unique `(workflow_run_id, phase, attempt_number)`

#### `council_ops.workflow_artifacts`
- `id UUID PK`
- `workflow_run_id UUID NOT NULL REFERENCES council_core.workflow_runs(id)`
- `artifact_key TEXT NOT NULL`
- `artifact_type TEXT NOT NULL`
- `content_uri TEXT NULL`
- `inline_content TEXT NULL`
- `sha256 TEXT NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

#### `council_ops.system_events`
- `id UUID PK`
- `event_type TEXT NOT NULL`
- `severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info'))`
- `entity_type TEXT NULL`
- `entity_id UUID NULL`
- `message TEXT NOT NULL`
- `details JSONB NOT NULL DEFAULT '{}'::jsonb`
- `occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()`

#### `council_ops.audit_events`
- `id UUID PK`
- `actor TEXT NOT NULL`
- `source TEXT NOT NULL`
- `action TEXT NOT NULL`
- `entity_type TEXT NOT NULL`
- `entity_id UUID NULL`
- `request_id TEXT NULL`
- `payload JSONB NOT NULL DEFAULT '{}'::jsonb`
- `result_code INTEGER NULL`
- `occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()`

#### `council_ops.outbox_events`
- `id UUID PK`
- `aggregate_type TEXT NOT NULL`
- `aggregate_id UUID NOT NULL`
- `event_type TEXT NOT NULL`
- `event_revision BIGINT NOT NULL`
- `payload JSONB NOT NULL`
- `status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed','dead_letter'))`
- `available_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

#### `council_ops.job_queue`
- `id UUID PK`
- `job_type TEXT NOT NULL`
- `payload JSONB NOT NULL`
- `job_state TEXT NOT NULL CHECK (job_state IN ('pending','running','done','failed','dead_letter'))`
- `attempts INTEGER NOT NULL DEFAULT 0`
- `last_error TEXT NULL`
- `available_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Schema 3: `council_sync`

This schema stores AppFlowy integration state.

#### `council_sync.entity_bindings`
- `id UUID PK`
- `entity_type TEXT NOT NULL`
- `council_id UUID NOT NULL`
- `appflowy_object_type TEXT NOT NULL`
- `appflowy_object_id TEXT NOT NULL`
- `binding_state TEXT NOT NULL CHECK (binding_state IN ('active','orphaned','pending','disabled'))`
- `last_synced_revision BIGINT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- unique `(entity_type, council_id)`
- unique `(appflowy_object_type, appflowy_object_id)`

#### `council_sync.incoming_mutations`
- `id UUID PK`
- `source_system TEXT NOT NULL DEFAULT 'appflowy'`
- `source_event_id TEXT NOT NULL`
- `entity_type TEXT NOT NULL`
- `binding_id UUID NULL REFERENCES council_sync.entity_bindings(id)`
- `payload JSONB NOT NULL`
- `normalized_patch JSONB NULL`
- `expected_revision BIGINT NULL`
- `mutation_state TEXT NOT NULL CHECK (mutation_state IN ('received','validated','applied','rejected','needs_review'))`
- `rejection_reason TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- unique `(source_system, source_event_id)`

#### `council_sync.outgoing_mutations`
- `id UUID PK`
- `outbox_event_id UUID NOT NULL REFERENCES council_ops.outbox_events(id)`
- `target_system TEXT NOT NULL DEFAULT 'appflowy'`
- `target_object_type TEXT NOT NULL`
- `target_object_id TEXT NULL`
- `payload JSONB NOT NULL`
- `delivery_state TEXT NOT NULL CHECK (delivery_state IN ('pending','sent','failed','dead_letter'))`
- `attempts INTEGER NOT NULL DEFAULT 0`
- `last_error TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

#### `council_sync.reconciliation_queue`
- `id UUID PK`
- `entity_type TEXT NOT NULL`
- `council_id UUID NOT NULL`
- `appflowy_object_id TEXT NOT NULL`
- `reason TEXT NOT NULL`
- `state TEXT NOT NULL CHECK (state IN ('open','resolved','ignored'))`
- `details JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

## Naming Rules

- Schemas use lower snake case.
- Table names use plural snake case.
- Primary key column is always `id`.
- Foreign keys use `<referenced_singular>_id`.
- State columns are specific by meaning: `run_state`, `review_state`, `finding_state`, `job_state`; avoid generic `status` unless the domain is truly generic.
- Free-form JSON is limited to `metadata`, `details`, `sections`, `variables`, or integration payloads.
- Avoid overloaded names like `eventlog`, `workitems`, `knowledgecards`, `prompttemplates`; replace with `system_events`, `work_items`, `knowledge_cards`, `prompt_templates`.
- Avoid mixed abstraction levels inside one table.

## Revised API Contract

## Canonical API Boundary

Council Core API is the canonical boundary for all Council-owned shared data.

- Council workers call it directly.
- AppFlowy-originated edits are normalized by the sync layer, then submitted to it.
- No other component may write canonical Council tables directly.

### Resource Rules

Each resource supports:

- `POST /v1/<resource>` create
- `GET /v1/<resource>/{id}` fetch canonical state
- `PATCH /v1/<resource>/{id}` partial update with `expected_revision`
- `POST /v1/<resource>/{id}/commands/<command>` for non-CRUD transitions
- `GET /v1/<resource>?updated_since=...` for sync/export

### Required Headers

- `Idempotency-Key` on create and command endpoints
- `X-Source-System: council|appflowy|sync_worker|system`
- `X-Actor-Id: ...`

### Example Shared Resources

#### Work item update

`PATCH /v1/work-items/{id}`

Request:

```json
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

Response:

```json
{
  "id": "0c7d...",
  "revision": 13,
  "updated_source": "appflowy",
  "status": "active"
}
```

#### Workflow transition

`POST /v1/workflow-runs/{id}/commands/transition`

```json
{
  "idempotency_key": "run-123-phase-build-2",
  "from_phase": "PLAN",
  "to_phase": "BUILD",
  "outcome": "success",
  "duration_ms": 4182
}
```

#### Review verdict

`POST /v1/reviews/{id}/commands/record-verdict`

```json
{
  "idempotency_key": "review-44-verdict-1",
  "expected_revision": 5,
  "verdict": "failed",
  "notes": "High-severity findings remain unresolved"
}
```

#### Prompt template update

`PATCH /v1/prompt-templates/{id}`

```json
{
  "expected_revision": 8,
  "patch": {
    "template_body": "Revised prompt body...",
    "tags": ["review", "qwen"]
  }
}
```

## AppFlowy Integration Contract

### Inbound: AppFlowy -> Council

Preferred order:

1. Use AppFlowy webhook or event callback if available.
2. If webhook is unavailable for a surface, use polling only as a transport fallback.
3. Polling creates `incoming_mutations`; it does not write canonical tables directly.

Inbound flow:

1. Detect change in AppFlowy object.
2. Resolve binding in `council_sync.entity_bindings`.
3. Transform AppFlowy fields into normalized patch.
4. Enforce field-level edit permissions.
5. Submit patch to Council Core API with `expected_revision`.
6. On success, mark mutation `applied`.
7. On stale revision or forbidden field, mark `rejected` or `needs_review`.

### Outbound: Council -> AppFlowy

Outbound flow:

1. Council Core writes canonical row and outbox event in one transaction.
2. Sync worker consumes `council_ops.outbox_events`.
3. Resolve binding.
4. Build AppFlowy payload.
5. Call documented AppFlowy REST API.
6. Record delivery result in `council_sync.outgoing_mutations`.
7. Update binding `last_synced_revision`.

### Field-Level Write Policy

#### Work items

Editable from both Council and AppFlowy:
- `title`
- `description`
- `priority`
- `due_at`
- `tags`
- `assigned_to`

Editable from Council only:
- `kind`
- `phase`
- machine-generated metadata
- derived run summaries

#### Reviews

Editable from AppFlowy:
- `notes`
- triage fields on findings (`finding_state`, `owner_note`)

Editable from Council only:
- `review_state`
- `verdict`
- `severity`
- `evidence`
- machine-generated rationale

#### Prompt templates

Editable from both:
- `name`
- `template_body`
- `tags`
- `status`

Editable from Council only:
- derived usage metrics
- render/test outputs

## Conflict Handling Contract

### Blanket Rule Removed

Remove “Council PostgreSQL is the single source of truth; app edits are applied if non-conflicting; council wins.”

Replace with:

- Council Core is canonical owner of shared business entities.
- AppFlowy can originate changes to allowed fields.
- Shared fields require revision-aware updates.
- Conflicts are explicit, not silent.

### Conflict Outcomes

- `409 conflict`: stale revision, client should refetch.
- `403 forbidden_field`: attempted edit to non-editable field.
- `202 needs_review`: semantic merge ambiguous, enqueue reconciliation.
- `200 applied`: write accepted and revision incremented.

### Reconciliation Rules

Use reconciliation queue for:

- simultaneous edits on the same shared field
- AppFlowy edit to a Council-derived field
- binding missing or ambiguous
- schema mapping drift after AppFlowy upgrade

## AppFlowy Upgradeability Rules

1. No direct SQL writes into AppFlowy-owned tables.
2. No Council logic depends on undocumented AppFlowy schema shape.
3. AppFlowy upgrades are validated by API compatibility and smoke tests, not manual schema diff patching.
4. Council may keep read-only introspection or read-only SQL access for diagnostics, but this is not required for normal operation.
5. Document every API endpoint used and every field mapping maintained.

## Required Changes to the Previous Plan

### Statements to Remove or Replace

Remove or replace these ideas:

- “No sync adapter; council writes to PostgreSQL, AppFlowy reads from PostgreSQL, one source of truth.”
- “Cross-schema queries via Python, not SQL JOINs” as an architectural centerpiece.
- The separate “Council PostgreSQL on port 5433” design if the goal is a unified operational topology.
- The blanket `council-wins` overwrite policy for user-editable shared fields.

Replace with:

- “Council Core PostgreSQL is the canonical store for shared business entities.”
- “AppFlowy is an integrated editing and visualization surface via documented APIs.”
- “Bidirectionality is implemented through a canonical mutation API and sync workers.”
- “AppFlowy-owned tables remain AppFlowy-managed.”

### Service Layer Changes

Replace the old service picture with:

- `CouncilCoreAPI`
- `ExecutionWorker`
- `ReviewWorker`
- `MemoryWorker`
- `OutboxDispatcher`
- `AppFlowyInboundSync`
- `AppFlowyOutboundSync`
- `ReconciliationWorker`

### Data Layer Changes

Replace the old monolithic `CouncilDatabase` layout with:

- ORM models grouped by schema package:
  - `db.council_core.*`
  - `db.council_ops.*`
  - `db.council_sync.*`
- Domain services grouped by resource:
  - `ProjectService`
  - `WorkItemService`
  - `WorkflowRunService`
  - `ReviewService`
  - `PromptTemplateService`
  - `KnowledgeCardService`
  - `MemoryService`
- Integration services:
  - `AppFlowyBindingService`
  - `InboundMutationService`
  - `OutboundMutationService`
  - `ReconciliationService`

## Recommended Deployment Contract

### PostgreSQL

Use one PostgreSQL cluster with separate users:

- `appflowy_app` owns `appflowy_*`
- `council_app` owns `council_core`, `council_ops`, `council_sync`
- `council_ro` optional read-only troubleshooting user

### Privileges

- AppFlowy user: full access to AppFlowy schemas only.
- Council user: full access to Council schemas; no write privileges to AppFlowy schemas.
- Optional read-only access from Council to selected AppFlowy metadata only if operationally necessary.

### Connection Strategy

- Same cluster, same backup domain.
- Separate SQLAlchemy metadata packages by schema.
- One migration stream for Council schemas, independent of AppFlowy container migrations.

## Migration Plan

### Phase 0: Decision Lock

Approve these decisions:

- Keep AppFlowy upgrade-safe and API-integrated.
- Migrate Council to PostgreSQL for internal architecture quality.
- Use one canonical write path.
- Use one PostgreSQL cluster with strict schema ownership.

### Phase 1: Schema Build

1. Create `council_core`, `council_ops`, `council_sync` schemas.
2. Implement migrations.
3. Add base entity mixins for revisioned records.
4. Create indexes and FK constraints.

### Phase 2: Core API

1. Implement REST API resources and command endpoints.
2. Enforce `expected_revision` and idempotency.
3. Emit outbox events transactionally.
4. Add audit event capture.

### Phase 3: Council Refactor

1. Replace legacy `RelationalStore` with resource services.
2. Route execution workers through `WorkflowRunService`.
3. Route review flows through `ReviewService`.
4. Route prompts, knowledge, and memory through their dedicated services.

### Phase 4: AppFlowy Sync

1. Create entity bindings for shared objects.
2. Implement outbound projections to AppFlowy databases/documents.
3. Implement inbound mutation normalization.
4. Add reconciliation queue and admin review view.

### Phase 5: Cutover

1. Freeze legacy SQLite writes.
2. Backfill Council canonical data to PostgreSQL.
3. Create or bind AppFlowy objects.
4. Enable outbound sync.
5. Enable inbound sync for approved shared entities.
6. Decommission legacy bridge logic.

## Acceptance Criteria

The implementation is accepted only if all are true:

- AppFlowy and Council can both originate edits to approved shared fields.
- Shared edits always go through the same canonical mutation path.
- No normal-path direct writes occur to AppFlowy-owned SQL tables.
- Stale writes are rejected explicitly rather than overwritten silently.
- Every shared entity has a binding and revision history.
- AppFlowy upgrade testing requires API smoke tests, not schema patch surgery.
- Council execution state remains canonical and cannot be corrupted by UI-side edits.
- Prompt templates and work items are truly bidirectional on approved fields.

## Immediate Build Order

1. Lock ownership matrix.
2. Implement new schemas.
3. Stand up Core API with revision contract.
4. Move work items and prompt templates first; these are the best shared entities for real bidirectionality.
5. Move workflow runs and reviews next, but keep machine-only fields Council-owned.
6. Add reconciliation UI in AppFlowy for rejected or ambiguous mutations.
7. Only then remove SQLite and old sync assumptions.

## Final Recommendation

This revised plan is the best balance of unity, bidirectionality, and upgradeability.

- If the priority is true shared editing, use **one canonical owner plus two-way command flow**.
- If the priority is raw simplicity, keep AppFlowy as a mostly read-only projection surface.
- Do not pursue dual ownership of identical rows in two systems; it creates the illusion of unity while increasing reconciliation complexity.[cite:7][cite:9]

The recommended target is therefore:

- **One PostgreSQL cluster**
- **Council Core as canonical owner of shared business entities**
- **AppFlowy as upgrade-safe UI/editor surface**
- **Bidirectionality through canonical API + sync/outbox/reconciliation**
- **Refactored Council schemas aligned by bounded context and naming discipline**
