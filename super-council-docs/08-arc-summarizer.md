# ARC Summarizer — Tiered Memory Consolidation on Intel Arc A380

> Memory consolidation routed through llama.cpp router mode on the Arc A380 via SYCL. Single-owner pipeline: only `memory-service` submits consolidation requests. Tier-specific model routing: 2.6B for daily, 1.2B for higher tiers. Multi-parser fallback chain with raw MD safety net.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Temporal Memory Pyramid                              │
│                                                                             │
│  Bi-Weekly Overview (15d)    ← digests weekly reviews                      │
│  ┌─────────────────────────┐   window=15d, ttl=60d, source=weekly          │
│  │ memory_rollups          │   prompt: strategic themes, corrections        │
│  │ (rollup-bimonthly-*)    │   output: executive summary, knowledge base    │
│  │ Model: LFM2.5-1.2B      │   (router hot-swaps from daily model)         │
│  └─────────────────────────┘                                                │
│               │                                                             │
│  Weekly Review (7d)        ← digests 3-day digests                         │
│  ┌─────────────────────────┐   window=7d, ttl=30d, source=short            │
│  │ memory_rollups          │   prompt: milestones, velocity, lessons       │
│  │ (rollup-weekly-*)       │   output: milestones, projects, risks          │
│  │ Model: LFM2.5-1.2B      │                                               │
│  └─────────────────────────┘                                                │
│               │                                                             │
│  3-Day Digest (3d)           ← digests daily summaries                     │
│  ┌─────────────────────────┐   window=3d, ttl=14d, source=daily            │
│  │ memory_rollups          │   prompt: narrative, threads, blockers        │
│  │ (rollup-short-*)        │   output: work threads, carried-forward        │
│  │ Model: LFM2.5-1.2B      │                                               │
│  └─────────────────────────┘                                                │
│               │                                                             │
│  Daily Rollup (per session)    ← reads canonical raw MD files              │
│  ┌─────────────────────────┐   source=raw, deterministic ID                │
│  │ memory_rollups          │   prompt: v2 Team Leader format              │
│  │ (rollup-daily-{src_id}) │   output: summary, decisions, work, open items │
│  │ Model: LFM2-2.6B        │   (Transcript specialist)                     │
│  └─────────────────────────┘                                                │
│               │                                                             │
│  Raw MD Files                      ← canonical source of truth             │
│  ┌─────────────────────────┐   ~/.council-memory/canonical-raw-session-data/│
│  │ canonical-raw-.../      │   Deterministic naming:                       │
│  │                         │   trace-{hash}.md                             │
│  └─────────────────────────┘                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Hardware

| Component | Spec |
|-----------|------|
| GPU | Intel Arc A380 (5.7 GB VRAM) |
| Daily Model | LFM2-2.6B-Transcript-Q8_0 (2.6 GB) |
| Higher-Tier Model | LFM2.5-1.2B-Instruct-Q8_0 (1.2 GB) |
| Backend | SYCL (oneAPI) via llama.cpp router |
| Port | 18093 (router) |
| Service | `arc-router.service` (systemd user) |
| Router Mode | `--models-max 1` (hot-swap, single model in VRAM) |

**Model selection rationale (2026-06-20):**
- **LFM2-2.6B-Transcript** for daily tier: Optimized for transcript/meeting summarization. Produces structured narratives with decision attribution and intent tracking. ~52s per session.
- **LFM2.5-1.2B-Instruct** for short/weekly/bimonthly: Faster synthesis of upstream rollups. ~50s per tier.
- **Router mode** (`--models-max 1`): Automatic hot-swapping between models on limited VRAM. Single endpoint (127.0.0.1:18093).
- **Q8_0 quantization**: Required for context fidelity (lower precision degrades output).
- **Context window**: 32K tokens (accommodates 82K char max daily input ~20K tokens + output).

### Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Daily (2.6B) PP | ~25 t/s | Steady-state on A380 |
| Daily (2.6B) TG | ~476 t/s | Token generation |
| Daily duration | ~52s | End-to-end per session |
| Higher-tier (1.2B) PP | ~24 t/s | Steady-state on A380 |
| Higher-tier (1.2B) TG | ~463 t/s | Token generation |
| Higher-tier duration | ~50s | End-to-end per tier |
| Typical output | 4-6K chars | Varies with session length |
| Router hot-swap | <1s | Automatic model swap |

**Legacy (2026-06-14):** LFM2.5-8B-A1B-UD-Q4_K_XL on port 18095. Replaced by router mode (2026-06-20) for tier-specific routing and reduced latency.

## Pipeline Components

### ArcPipeline (`memory_service/consolidate/pipeline.py`)

Single entry point for all consolidation. Instantiated by `memory_service/__init__.py`.

**Flow:**
1. **Scheduler** (`scheduler.py`) - Identifies sessions needing consolidation (daily, short, weekly, bimonthly windows)
2. **Gather** - Reads raw MD files or upstream rollups via `TierGatherer`
3. **Prompt** - Constructs tier-specific prompt with system prompt + context
4. **Call** - Sends to ArcClient (HTTP to llama.cpp router on :18093)
5. **Parse** - Extracts structured fields from Markdown response (5-parser fallback chain)
6. **Write** - Upserts to `memory_rollups` via `TierWriter.write()` or `TierWriter.write_raw()`
7. **Index** - Triggers SqliteIndexer to embed new rollup

**Key methods:**
- `run_tiered_consolidation(tier_id)` - Main entry point, dispatches to tier-specific processor
- `_process_raw_sessions_sequentially()` - Processes raw MD files for daily tier
- `_process_tiered_consolidation(tier_id)` - Processes higher-tier rollups
- `reconcile_tasks()` - Reconciles extracted tasks with workflow runs
- `reconcile_deviations()` - Reconciles detected deviations with plan deviations
- `health_check()` - Returns router/queue health status
- `tier1_knowledge_card()` - Returns latest daily rollup for prompt injection

### ArcClient (`memory_service/consolidate/client.py`)

HTTP client with retry logic and multi-parser fallback chain. Talks to llama.cpp router on :18093.

**Features:**
- Exponential backoff retry (3 attempts, 1s base)
- Timeout: 600s (10 min) for long consolidation prompts
- Fallback to main upstream (Qwen on RTX 3090) if router is down
- Health check: `GET /v1/health` before submission
- Model-aware routing: selects model per tier via `config.get_model_for_tier()`
- `cache_prompt: False` in payload to clear KV cache between requests
- **5-parser fallback chain** (2026-06-21): `_parse_yaml_strict()` → `_parse_yaml_fallback()` → `_extract_sections_regex()` → `_extract_minimal()` → returns `None`
- When parser returns `None`, raw MD is upserted to DB with `parse_status="failed"` (safety net)

### LLMRequestQueue (`memory_service/consolidate/llm_queue.py`)

Request queue with priority scheduling and performance tracking.

**Features:**
- Priority queue: daily > short > weekly > bimonthly
- Performance logging: TG (tokens/sec generation), PP (tokens/sec prompt processing)
- Queue depth monitoring
- Backpressure: blocks new requests when queue is full
- Router mode: each request specifies model, router handles hot-swap
- KV cache clearing: `cache_prompt: False` prevents context bleed

### TierWriter (`memory_service/consolidate/tier_writer.py`)

Writes consolidation output to `memory_rollups` table.

**Key responsibilities:**
- Generates deterministic rollup IDs: `rollup-{tier}-{source_id}`
- `INSERT OR REPLACE` for daily tier (prevents duplicates)
- Sets TTL based on tier (7d daily, 14d short, 30d weekly, 60d bimonthly)
- Embeds `summary_text` as primary vector target
- Tracks `model_used` in DB for auditability
- **Two write paths:**
  - `write()` - Normal path: formatted MD → parse → structured fields → DB upsert
  - `write_raw()` - Fallback path: raw LLM output → DB upsert with `parse_status="failed"`

### ConsolidationStore (`memory_service/store/consolidation_store.py`)

Database operations for `memory_rollups` table.

**Key methods:**
- `upsert_memory_rollup(...)` - Insert or replace rollup with structured fields
- `get_memory_rollups(...)` - Query with filters (tier, source, date, project, include_expired)
- `query_consolidation_tiers()` - Returns all tier configs with last_run/reconciled timestamps
- `update_tier_last_run(tier_id, timestamp)` - Updates scheduler last_run_at
- `update_tier_reconciled_at(tier_id, timestamp)` - Marks tier as reconciled
- `create_knowledge_card(...)` - Creates/updates knowledge card from rollup
- `search_knowledge_cards(...)` - Searches knowledge cards by query

### SessionStore (`memory_service/store/session_store.py`)

Session lifecycle tracking. `session_diary` table dropped 2026-06-12, replaced by `memory_rollups`.

**Note:** `session_lifecycle` table is referenced by code but not created in migrations - it exists in live DB from manual creation. See [Schema Notes](#schema-notes) below.

**Key methods:**
- `upsert_raw_session_memory(...)` - Stage raw session text, produce canonical MD files, record in session_lifecycle
- `finalize_trace_file(trace_id, total_parts)` - Rename .tmp staging files to final .md
- `query_session_lifecycle(...)` - Query session lifecycle records for pipeline
- `upsert_consolidation_request(...)` - Track consolidation request status
- `get_consolidation_requests(...)` - Get pending/processing consolidation requests

## Router Mode

### Configuration

```ini
# /home/chief/models/arc-router/models.ini
# Uses absolute paths (router resolves working directory differently)

[main]
models = /home/chief/models/LFM2-2.6B-Transcript-Q8_0.gguf,/home/chief/models/LFM2.5-1.2B-Instruct-Q8_0.gguf
models_max = 1
```

**Key settings:**
- `--models-max 1`: Only one model loaded in VRAM at a time (hot-swap)
- `--models-autoload`: Loads models from `models.ini`
- Absolute paths in `models.ini`: Required due to router working directory resolution
- Single endpoint: `http://127.0.0.1:18093` handles all tiers

### Tier-to-Model Routing

```python
# config.py
TIER_MODEL = {
    "daily": "LFM2-2.6B-Transcript-Q8_0",
    "short": "LFM2.5-1.2B-Instruct-Q8_0",
    "weekly": "LFM2.5-1.2B-Instruct-Q8_0",
    "bimonthly": "LFM2.5-1.2B-Instruct-Q8_0",
}
```

Router automatically unloads current model and loads requested model. Swap latency: <1s.

### KV Cache Clearing

`cache_prompt: False` in every request payload. Prevents KV cache reuse across requests, ensuring fresh generation and consistent testing. Without this, context bleed causes output degradation.

## Prompt Strategy

### Daily Tier - v2 Team Leader Format

```
This is a software development session transcript. USER is the team lead who sets goals
and direction. ASSISTANT is a team member who executes tasks and provides
recommendations. ACTION lines show file edits and commands executed. FLAG lines
mark destructive operations.

Provide a detailed chronological summary of the session for historical archives
and retrieval. Cover the sequence of events: what was attempted, what succeeded
or failed, and what was decided. Include only the important and relevant file
names, function names, error messages, and config values.

List the key decisions that were made. For each, attribute it clearly:
- Driver (USER): The team lead directed this decision
- Recommended (ASSISTANT): The team member proposed this, team lead accepted
- Conflict (USER vs ASSISTANT): Team lead overrode a recommendation or vice versa

List the action items and unresolved items. For each, note who initiated it:
- Requested by USER: Team lead explicitly asked for this
- Identified by ASSISTANT: Team member flagged this as needed
- Unresolved: Still pending with no clear owner

List the main topics and technical subjects discussed. Be specific about what
was explored, tested, or evaluated.

Critically assess execution vs. user intent. This is the most important section.
Flag where:
- The team lead's goal was achieved as stated (success)
- The execution deviated from what the team lead wanted (and why)
- The team lead overlooked something or made an incorrect assumption
- The team member misunderstood the team lead's direction
- The team lead changed direction mid-session (note the shift and trigger)

Be accurate. Only include what is explicitly stated or clearly implied. If unsure,
mark confidence as low and note the ambiguity.
```

**Rationale (2026-06-20):**
- LFM2-2.6B-Transcript is optimized for meeting/transcript summarization
- Model produces `**Bold:**` headers natively (not `##` Markdown)
- Parser handles both formats via regex
- v2 format produces 4-6K chars with structured output
- Better than v3 (disambiguation rules) which triggers technical documentation mode
- Better than v1 (strict schema) which causes hallucinations

### Higher Tiers - User Intent Tracking

Short, weekly, and bimonthly tiers include:
- **User Intent** section: What the user wanted to achieve
- **matched_intent** field: `yes|partial|no` on milestones/achievements
- **Goal shift tracking**: Where goals shifted or were abandoned

## Single Consolidation Owner

**Only `memory-service` submits consolidation requests.** No other process calls the Arc pipeline directly.

```
ArcPipeline (memory_service)
  └── ArcClient
        └── LLMRequestQueue
              └── llama.cpp router (:18093, --models-max 1)
                    ├── LFM2-2.6B-Transcript-Q8_0 (daily)
                    └── LFM2.5-1.2B-Instruct-Q8_0 (short/weekly/bimonthly)
```

The `ArcSummarizer` facade class was removed (2026-06-16). It was never instantiated in production - `council_main.py` had `self._arc = None` and the startup consolidation block was dead code.

## Deduplication

### Daily Tier: Deterministic IDs

Daily rollups use `f"rollup-daily-{source_id}"` as the rollup ID. Combined with `INSERT OR REPLACE`, this guarantees one rollup per session. No new duplicates can form.

### Source File as Canonical Key

`source_file` is the canonical primary key across:
- `session_lifecycle` - tracks session state
- `consolidation_requests` - tracks consolidation status
- `memory_rollups` - stores consolidation output

Pipeline checks `rollup_id IS NOT NULL` in `session_lifecycle` to skip already-consolidated sessions.

### Legacy Duplicates

Pre-June 16 rollups used timestamp-based IDs (`rollup-daily-{timestamp}-{uuid}`), creating 2-6 duplicates per session for ~10 sessions (June 12-14). These are frozen legacy artifacts; the deterministic ID scheme prevents recurrence.

## Higher-Tier Lineage

Tiers above daily track upstream sources via `source_rollup_ids` (JSON array of MD filenames). This ensures:
- Weekly rollups know which daily rollups they digest
- Bi-weekly rollups know which weekly rollups they digest
- Full lineage traceability from any rollup back to raw MD files

## MD File Naming

```
~/.council-memory/canonical-raw-session-data/trace-{hash}.md
```

Hash is content-based (SHA-256 prefix). Files are deduplicated at the filesystem level before pipeline processing.

## Configuration

### arc-router.service

```ini
# ~/.config/systemd/user/arc-router.service
[Unit]
Description=ARC Router - llama.cpp router mode (2.6B + 1.2B hot-swap)
Documentation=file:///home/chief/llm-wiki/super-council-docs/08-arc-summarizer.md
After=network.target

[Service]
Type=simple
ExecStart=/home/chief/Coding-Projects/7-council/llama-forks/llama-vulkan-a380/build-sycl-prod/bin/llama-server \
    --models-dir /home/chief/models/arc-router \
    --models-preset /home/chief/models/arc-router/models.ini \
    --models-max 1 \
    --models-autoload \
    --host 127.0.0.1 \
    --port 18093 \
    --threads 8 \
    --threads-batch 8 \
    -b 512 \
    -ctk q8_0 \
    -ctv q8_0
Restart=on-failure
RestartSec=10
StandardOutput=append:/tmp/arc-router.log
StandardError=append:/tmp/arc-router.log

[Install]
WantedBy=default.target
```

**Key settings:**
- `--models-max 1`: Hot-swap mode (one model in VRAM)
- `--models-autoload`: Loads from models.ini
- `-ctk q8_0 -ctv q8_0`: Q8_0 KV cache (required for fidelity)
- `-b 512`: Batch size 512
- `--threads 8`: 8 CPU threads
- Binary path: `llama-forks/llama-vulkan-a380/build-sycl-prod/bin/llama-server` (Vulkan/SYCL build for Arc A380)

### config-subsystem.json

```json
{
  "consolidation": {
    "model": "LFM2-2.6B-Transcript-Q8_0",
    "server_url": "http://127.0.0.1:18093",
    "timeout_seconds": 600,
    "max_retries": 3,
    "fallback_to_main": true,
    "roles": [
      "memory-consolidation",
      "session-summarization",
      "knowledge-extraction"
    ],
    "tier_model": {
      "daily": "LFM2-2.6B-Transcript-Q8_0",
      "short": "LFM2.5-1.2B-Instruct-Q8_0",
      "weekly": "LFM2.5-1.2B-Instruct-Q8_0",
      "bimonthly": "LFM2.5-1.2B-Instruct-Q8_0"
    }
  }
}
```

**Key settings:**
- `server_url`: Router endpoint (was `arc_server` in legacy config)
- `max_retries`: Parser retry count (3 attempts)
- `fallback_to_main`: Fall back to Qwen on RTX 3090 if router down
- `roles`: Consolidation task classifications
- `tier_model`: Model routing per tier (2.6B for daily, 1.2B for higher tiers)

## Database

### memory_rollups Table

Primary table for all consolidation output. Replaced `consolidation_cache` (zombie, 0 rows) and `session_diary` (dropped 2026-06-12).

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT PK | Rollup ID (`rollup-{tier}-{source_id}`) |
| `tier` | TEXT | `daily`, `short`, `weekly`, `bimonthly` |
| `window_start` | TEXT | Start of consolidation window |
| `window_end` | TEXT | End of consolidation window |
| `summary_text` | TEXT | Primary consolidation output (vector embedding target) |
| `decisions` | TEXT | Extracted key decisions (JSON array) |
| `work_completed` | TEXT | Completed work items (JSON array) |
| `open_items` | TEXT | Open/carry-forward items (JSON array) |
| `carried_forward` | TEXT | Carry-forward items (JSON object) |
| `deviations` | TEXT | Detected deviations (JSON array) |
| `key_files` | TEXT | Key files involved (JSON array) |
| `key_functions` | TEXT | Key functions touched (JSON array) |
| `trace_id` | TEXT | Source trace ID (nullable) |
| `source_file` | TEXT | Canonical source file path (nullable) |
| `vector_text` | TEXT | Structured fields as YAML/JSON (for embeddings) |
| `is_indexed` | INTEGER | Whether vector embedding exists (0/1) |
| `index_failures` | INTEGER | Count of failed indexing attempts |
| `parse_status` | TEXT | `ok` or `failed` (parser result) |
| `status` | TEXT | `active` or `expired` |
| `created_at` | TEXT | Creation timestamp |
| `updated_at` | TEXT | Last update timestamp |

**Note:** `source_rollup_ids`, `session_context`, `ttl_days`, `model_used`, and `source_id` columns do NOT exist in the current schema. These were removed during the 2026-06-12 flat schema migration.

### consolidation_requests Table

Tracks consolidation pipeline requests and status.

| Column | Type | Purpose |
|--------|------|---------|
| `source_file` | TEXT PK | Canonical source file (primary key, not auto-increment) |
| `tier_id` | TEXT | Target tier (`daily`, `short`, `weekly`, `bimonthly`) |
| `status` | TEXT | `queued`, `processing`, `completed`, `failed` |
| `model_used` | TEXT | Model that processed this request (nullable) |
| `submitted_at` | TEXT | Request submission time (nullable) |
| `completed_at` | TEXT | Completion time (nullable) |
| `llama_task_id` | INTEGER | Llama.cpp task ID (nullable) |
| `error` | TEXT | Error message on failure (nullable) |
| `output_rollup_id` | TEXT | Resulting rollup ID (nullable) |

**Constraint:** `UNIQUE(source_file, tier_id)` - prevents duplicate requests for same source+tier.

### session_lifecycle Table

Tracks session state and consolidation linkage. **Note:** This table is referenced by code but not created in any migration file - it exists in live DB from manual creation. The pipeline queries it for session discovery.

| Column | Type | Purpose |
|--------|------|---------|
| `source_file` | TEXT | Canonical source file path (JSONL) |
| `source_uuid` | TEXT | Session UUID extracted from source file |
| `trace_id` | TEXT | Trace identifier (e.g., `trace-be121052`) |
| `md_written` | INTEGER | Whether MD was written (1 = yes) |
| `md_file_path` | TEXT | Path to first MD file |
| `md_part_count` | INTEGER | Number of MD parts |
| `ingested_at` | TEXT | When session was ingested |
| `md_finalized_at` | TEXT | When MD was finalized |
| `updated_at` | TEXT | Last update timestamp |

**Pipeline usage:** Query for `md_written=1 AND rollup_id IS NULL AND ingested_at >= cutoff` to find sessions needing consolidation.

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| Router down | Fallback to main upstream (Qwen on RTX 3090) |
| LLM output failure | `partial failure: not all 1 parts succeeded` - logged, session marked failed |
| Queue full | Backpressure: blocks new requests until queue drains |
| Empty summary_text | Rollup created but no content - typically LLM generation failure |
| Duplicate detection | `INSERT OR REPLACE` on deterministic IDs prevents new duplicates |
| Model swap failure | Router logs error, request fails, retry with fallback |

## Known Issues

1. **~24 unlinked sessions** - Failed with `partial failure` during initial consolidations. Rollups exist but not linked to sessions.
2. **~12 empty `summary_text` rollups** - Mostly legacy; 1 recent has populated `vector_text`. LLM output generation failures.
3. **~10 sessions with legacy duplicate rollups** - Pre-June 16, timestamp-based IDs. Frozen artifacts.
4. **Reconciliation status error** - `Invalid status: 'completed'. Must be one of frozenset({'open', 'superseded', 'proposed', 'in_progress', 'done', 'blocked', 'wont_do'})`. Pre-existing bug unrelated to 2.6B model.

## File Locations

| Component | Path |
|-----------|------|
| ArcPipeline | `memory_service/consolidate/pipeline.py` |
| ArcClient | `memory_service/consolidate/client.py` |
| LLMRequestQueue | `memory_service/consolidate/llm_queue.py` |
| TierWriter | `memory_service/consolidate/tier_writer.py` |
| Scheduler | `memory_service/consolidate/scheduler.py` |
| Prompts | `memory_service/consolidate/prompts.py` |
| ConsolidationStore | `memory_service/store/consolidation_store.py` |
| SessionStore | `memory_service/store/session_store.py` |
| Router Config | `/home/chief/models/arc-router/models.ini` |
| Router Service | `~/.config/systemd/user/arc-router.service` |
| Database | `~/.council-memory/council_core.db` |
| Raw MD files | `~/.council-memory/canonical-raw-session-data/` |
