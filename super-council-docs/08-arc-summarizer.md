# ARC Summarizer — Tiered Memory Consolidation on Intel Arc A380

> Memory consolidation routed through llama.cpp router mode on the Arc A380 via SYCL. Single-owner pipeline: only `memory-service` submits consolidation requests. Tier-specific model routing: 2.6B for daily, 1.2B for higher tiers.

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
1. **Scheduler** (`scheduler.py`) — Identifies sessions needing consolidation (daily, short, weekly, bimonthly windows)
2. **Gather** — Reads raw MD files or upstream rollups via `source_rollup_ids`
3. **Prompt** — Constructs tier-specific prompt with system prompt + context
4. **Call** — Sends to ArcClient (HTTP to llama.cpp router on :18093)
5. **Parse** — Extracts structured fields from Markdown response
6. **Write** — Upserts to `memory_rollups` via `RelationalStore.upsert_memory_rollup()`
7. **Index** — Triggers SqliteIndexer to embed new rollup

**Key methods:**
- `process_consolidation_request(request)` — Main entry point
- `_build_prompt(tier, context)` — Tier-specific prompt construction
- `_call_arc(context, prompt)` — HTTP call via ArcClient
- `_parse_response(response)` — Markdown extraction → structured dict
- `_write_rollup(rollup_data)` — DB upsert via RelationalStore

### ArcClient (`memory_service/consolidate/client.py`)

HTTP client with retry logic. Talks to llama.cpp router on :18093.

**Features:**
- Exponential backoff retry (3 attempts, 1s base)
- Timeout: 600s (10 min) for long consolidation prompts
- Fallback to main upstream (Qwen on RTX 3090) if router is down
- Health check: `GET /v1/health` before submission
- Model-aware routing: selects model per tier via `config.get_model_for_tier()`
- `cache_prompt: False` in payload to clear KV cache between requests

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
- Populates `source_rollup_ids` for higher-tier lineage
- Sets TTL based on tier (14d daily, 30d short, 60d weekly, 90d bimonthly)
- Embeds `summary_text` as primary vector target
- Tracks `model_used` in DB for auditability

### ConsolidationStore (`memory_service/store/consolidation_store.py`)

Database operations for `memory_rollups` table.

**Key methods:**
- `upsert_memory_rollup(...)` — Insert or replace rollup
- `get_memory_rollups(...)` — Query with filters (tier, source, date, project)
- `get_rollup_by_id(id)` — Single rollup lookup
- `get_rollups_by_source(source_id)` — All rollups for a source

### SessionStore (`memory_service/store/session_store.py`)

Session lifecycle tracking. `session_diary` table dropped 2026-06-12, replaced by `memory_rollups`.

**Key methods:**
- `upsert_session_lifecycle(...)` — Track session state
- `get_sessions_needing_consolidation(...)` — Pipeline input
- `link_rollup_to_session(...)` — Connect rollup to session

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

### Daily Tier — v2 Team Leader Format

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

### Higher Tiers — User Intent Tracking

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

The `ArcSummarizer` facade class was removed (2026-06-16). It was never instantiated in production — `council_main.py` had `self._arc = None` and the startup consolidation block was dead code.

## Deduplication

### Daily Tier: Deterministic IDs

Daily rollups use `f"rollup-daily-{source_id}"` as the rollup ID. Combined with `INSERT OR REPLACE`, this guarantees one rollup per session. No new duplicates can form.

### Source File as Canonical Key

`source_file` is the canonical primary key across:
- `session_lifecycle` — tracks session state
- `consolidation_requests` — tracks consolidation status
- `memory_rollups` — stores consolidation output

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
Description=ARC Router (llama.cpp router mode)
After=network.target

[Service]
Type=simple
ExecStart=/home/chief/llama-cpp-latest/build/bin/llama-server \
  --host 127.0.0.1 \
  --port 18093 \
  --models /home/chief/models/arc-router/models.ini \
  --models-max 1 \
  --models-autoload \
  --threads 4 \
  --ubatch-size 2048 \
  --batch-size 4096 \
  --ctx-size 32768 \
  --gpu-split 1 \
  -ngl 999 \
  -ctk q8_0 \
  -ctv q8_0 \
  --mlock \
  --no-mmap
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

**Key settings:**
- `--models-max 1`: Hot-swap mode (one model in VRAM)
- `--models-autoload`: Loads from models.ini
- `-ctk q8_0 -ctv q8_0`: Q8_0 KV cache (required for fidelity)
- `--ctx-size 32768`: 32K context window

### config-subsystem.json

```json
{
  "consolidation": {
    "enabled": true,
    "arc_server": "http://127.0.0.1:18093",
    "model": "LFM2-2.6B-Transcript-Q8_0",
    "tier_model": {
      "daily": "LFM2-2.6B-Transcript-Q8_0",
      "short": "LFM2.5-1.2B-Instruct-Q8_0",
      "weekly": "LFM2.5-1.2B-Instruct-Q8_0",
      "bimonthly": "LFM2.5-1.2B-Instruct-Q8_0"
    },
    "daily_window_hours": 24,
    "short_window_days": 3,
    "weekly_window_days": 7,
    "bimonthly_window_days": 15,
    "scheduler_interval_seconds": 300,
    "max_queue_depth": 5,
    "timeout_seconds": 600
  }
}
```

## Database

### memory_rollups Table

Primary table for all consolidation output. Replaced `consolidation_cache` (zombie, 0 rows) and `session_diary` (dropped 2026-06-12).

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT PK | Rollup ID (`rollup-{tier}-{source_id}`) |
| `tier` | TEXT | `daily`, `short`, `weekly`, `bimonthly` |
| `source_file` | TEXT | Canonical source file path |
| `source_id` | TEXT | Source session ID |
| `source_rollup_ids` | TEXT | JSON array of upstream rollup MD filenames |
| `summary_text` | TEXT | Primary consolidation output (vector embedding target) |
| `vector_text` | TEXT | Structured fields as YAML/JSON |
| `decisions` | TEXT | Extracted key decisions |
| `work_completed` | TEXT | Completed work items |
| `open_items` | TEXT | Open/carry-forward items |
| `session_context` | TEXT | Session context/narrative |
| `model_used` | TEXT | Model alias that produced this rollup |
| `ttl_days` | INTEGER | Time-to-live in days |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### consolidation_requests Table

Tracks consolidation pipeline requests and status.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT PK | Request ID |
| `source_file` | TEXT | Canonical source file |
| `tier` | TEXT | Target tier |
| `status` | TEXT | `pending`, `processing`, `completed`, `failed` |
| `model_used` | TEXT | Model that processed this request |
| `error` | TEXT | Error message on failure |
| `rollup_id` | TEXT | Resulting rollup ID |
| `created_at` | TIMESTAMP | Request time |
| `completed_at` | TIMESTAMP | Completion time |

### session_lifecycle Table

Tracks session state and consolidation linkage.

| Column | Type | Purpose |
|--------|------|---------|
| `source_file` | TEXT PK | Canonical source file path |
| `rollup_id` | TEXT | Linked rollup ID (NULL = not consolidated) |
| `state` | TEXT | `new`, `consolidated`, `failed` |
| `updated_at` | TIMESTAMP | Last state change |

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| Router down | Fallback to main upstream (Qwen on RTX 3090) |
| LLM output failure | `partial failure: not all 1 parts succeeded` — logged, session marked failed |
| Queue full | Backpressure: blocks new requests until queue drains |
| Empty summary_text | Rollup created but no content — typically LLM generation failure |
| Duplicate detection | `INSERT OR REPLACE` on deterministic IDs prevents new duplicates |
| Model swap failure | Router logs error, request fails, retry with fallback |

## Known Issues

1. **~24 unlinked sessions** — Failed with `partial failure` during initial consolidations. Rollups exist but not linked to sessions.
2. **~12 empty `summary_text` rollups** — Mostly legacy; 1 recent has populated `vector_text`. LLM output generation failures.
3. **~10 sessions with legacy duplicate rollups** — Pre-June 16, timestamp-based IDs. Frozen artifacts.
4. **Reconciliation status error** — `Invalid status: 'completed'. Must be one of frozenset({'open', 'superseded', 'proposed', 'in_progress', 'done', 'blocked', 'wont_do'})`. Pre-existing bug unrelated to 2.6B model.

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
