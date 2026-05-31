# Arc Summarizer — Tiered Memory Consolidation on Intel Arc A380

> Memory consolidation, session summarization, and knowledge extraction routed to Granite-4.1-3B on the Arc A380 via SYCL llama-server. Implements a **Temporal Memory Pyramid** with four consolidation tiers (daily → 3-day → weekly → bi-weekly), each producing progressively abstract summaries.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Temporal Memory Pyramid                              │
│                                                                             │
│  Bi-Weekly Overview (15d)    ← digests weekly reviews                      │
│  ┌─────────────────────────┐   window=15d, ttl=60d, source=weekly          │
│  │ consolidation_cache     │   prompt: strategic themes, corrections        │
│  │ (consol-bimonthly-*)    │   output: executive summary, knowledge base    │
│  └────────────┬────────────┘                                                │
│               │                                                             │
│  Weekly Review (7d)        ← digests 3-day digests                         │
│  ┌─────────────────────────┐   window=7d, ttl=30d, source=short            │
│  │ session_diary           │   prompt: milestones, velocity, lessons       │
│  │ (consol-weekly-*)       │   output: milestones, projects, risks          │
│  └────────────┬────────────┘                                                │
│               │                                                             │
│  3-Day Digest (3d)           ← digests daily summaries                     │
│  ┌─────────────────────────┐   window=3d, ttl=14d, source=daily            │
│  │ session_diary           │   prompt: narrative, threads, blockers        │
│  │ (consol-short-*)        │   output: work threads, carried-forward        │
│  └────────────┬────────────┘                                                │
│               │                                                             │
│  24-Hour Diary (1d)            ← reads raw session_diary entries           │
│  ┌─────────────────────────┐   window=1d, ttl=7d, source=raw               │
│  │ session_diary           │   prompt: decisions, completed, open items    │
│  │ (consol-daily-*)        │   output: tasks, files, errors                │
│  └────────────┬────────────┘                                                │
│               │                                                             │
│  Raw Material                                              │                │
│  ┌─────────────────────────┐                                │                │
│  │ session_diary (sess-*)  │ ← Pi extension hook            │                │
│  │ chat-summaries/         │ ← chat session endings         │                │
│  │ daily/                  │ ← council daily logs           │                │
│  └─────────────────────────┘                                │                │
└─────────────────────────────────────────────────────────────┘                │
```

## Provenance Separation

Every entry carries a prefix that reveals its origin:

| Prefix | Table | Source | Mechanism |
|--------|-------|--------|------------|
| `consol-daily-*` | `session_diary` | Arc A380 | Tiered consolidation (daily) |
| `consol-short-*` | `session_diary` | Arc A380 | Tiered consolidation (3-day) |
| `consol-weekly-*` | `session_diary` | Arc A380 | Tiered consolidation (weekly) |
| `consol-bimonthly-*` | `consolidation_cache` | Arc A380 | Tiered consolidation (bi-weekly) |
| `consol-*` | `consolidation_cache` | Arc A380 | Legacy startup consolidation |
| `sess-*` | `session_diary` | Mechanical | Pi extension hook or `memory.upsert_summary` |

**Design principle:** `consolidation_cache` = Arc A380 only. `session_diary` = mechanical upsert + tiered daily/short/weekly. Provenance is traceable from prefix alone.

## Module Structure

| File | Purpose |
|------|---------|
| `arc_summarizer/__init__.py` | `ArcSummarizer` facade — unified entry point |
| `arc_summarizer/config.py` | `ArcConfig` — loads from `config-subsystem.json["consolidation"]` |
| `arc_summarizer/client.py` | `ArcClient` — HTTP client with retry + fallback |
| `arc_summarizer/pipeline.py` | `ArcPipeline` — consolidation pipeline + tiered execution |
| `arc_summarizer/prompts.py` | Prompt templates (legacy + tier-specific) for Granite-4.1-3B |
| `arc_summarizer/scheduler.py` | `IdleWindowScheduler` — adaptive, CPU-aware background scheduling |
| `arc_summarizer/start.sh` | systemd wrapper — sources oneAPI, starts llama-server |

## Tier Configuration

```python
TIER_CONFIGS = {
    "daily":     {"window_days": 1,  "ttl_days": 7,  "input_source": "raw",     "max_input_chars": 30_000},
    "short":     {"window_days": 3,  "ttl_days": 14, "input_source": "daily",   "max_input_chars": 20_000},
    "weekly":    {"window_days": 7,  "ttl_days": 30, "input_source": "short",   "max_input_chars": 15_000},
    "bimonthly": {"window_days": 15, "ttl_days": 60, "input_source": "weekly",  "max_input_chars": 10_000},
}
```

## Scheduler: IdleWindowScheduler

Replaces fixed cron with adaptive, workstation-aware scheduling. Three mechanisms:

### Primary: Idle-Window Background Thread

```
IdleWindowScheduler (daemon thread)
  → wakes every CHECK_INTERVAL (30 min default)
  → gate: Arc healthy? → health_check() latency < 2s
  → gate: System idle? → CPU < 60% (psutil)
  → find overdue tiers → last_run_at vs window_days
  → run due tiers in pyramid order (daily → short → weekly → bimonthly)
  → MAX_RUNS_PER_CYCLE = 2 (spread across wake cycles)
  → CASCADE_DELAY = 2s between tiers (DB settle time)
```

### Fallback A: Startup Catch-Up

On service start, `_run_startup_catch_up()` finds overdue tiers and runs them in a background thread. Non-blocking — never delays HTTP listener startup. Skips if Arc unhealthy.

### Fallback B: Lazy-on-Recall

`ContextRouter.get_recent_diary(days=N)` triggers on-demand consolidation when no fresh digest exists. Falls back to raw entry aggregation if consolidation fails or Arc is down.

## Tiered Consolidation Flow

```
run_tiered_consolidation(tier_id)
  → _gather_tier_input(tier_id)   # raw material or lower-tier digests
  → build_tier_consolidation_prompt(input, tier_id)  # tier-specific template
  → ArcClient.consolidate_tiered() # POST to Arc server :18095
  → _write_tier_output()           # session_diary with consolidation_tier=tier_id
  → update_tier_last_run()         # consolidation_tiers.last_run_at
```

## Tier-Specific Prompts

Each tier has a prompt template in `TIER_PROMPT_TEMPLATES` dict (`prompts.py`):

| Tier | Abstraction | Key Output Fields |
|------|-------------|-------------------|
| `daily` | Concrete (files, functions, errors) | summary, decisions, work_completed, open_items, key_files, key_functions |
| `short` | Narrative (work threads, progress) | narrative, work_threads[], carried_forward[], new_open_items[] |
| `weekly` | Thematic (milestones, velocity) | theme, completed_milestones[], active_projects[], lessons_learned[], risks[] |
| `bimonthly` | Strategic (direction, corrections) | executive_summary, major_achievements[], course_corrections[], knowledge_base[] |

Each prompt includes a **"Previously Captured"** section to prevent cross-tier duplication.

## API Reference

### ArcClient (HTTP)

| Method | Purpose |
|--------|---------|
| `consolidate(input_material)` | POST legacy consolidation prompt → YAML |
| `consolidate_tiered(input_material, tier_id)` | POST tier-specific prompt → YAML |
| `summarize_session(turns, max_tokens)` | POST session turns → summary |
| `extract_knowledge(text, schema)` | POST text + schema → parsed dict |
| `health_check()` | GET /v1/models → health status |

### ArcPipeline (orchestration)

| Method | Purpose |
|--------|---------|
| `run_consolidation()` | Legacy pipeline: gather → call → write → cache → activate → inject |
| `run_tiered_consolidation(tier_id)` | Tiered pipeline: gather → call → write → update timestamp |
| `_gather_tier_input(tier_id)` | Read source material within window_days |
| `_write_tier_output(tier_id, output)` | Write to session_diary with tier prefix |
| `inject_tier1()` | Query cache → format knowledge card |

### IdleWindowScheduler (adaptive scheduling)

| Method | Purpose |
|--------|---------|
| `start()` | Launch daemon thread (idempotent) |
| `stop()` | Signal thread to stop |
| `_check_cycle()` | One wake: gates → run due tiers |
| `_arc_healthy()` | Gate: Arc server responds |
| `_system_idle()` | Gate: CPU < threshold (psutil) |
| `_find_due_tiers()` | Overdue: `last_run_at` vs `window_days`, pyramid order |
| `_run_startup_catch_up()` | Fallback A: run overdue tiers on service start |

### ContextRouter (recall)

| Method | Purpose |
|--------|---------|
| `get_recent_diary(days, max_tokens)` | Lazy recall: digest → consolidate → raw fallback |
| `_format_digest_entry(entry)` | Format tier digest as readable text |
| `_aggregate_raw_entries(days)` | Fallback: combine raw entries by section |

### RelationalStore (tier methods)

| Method | Purpose |
|--------|---------|
| `query_consolidation_tiers()` | All tier definitions from registry |
| `update_tier_last_run(tier_id, timestamp)` | Mark tier as run |
| `query_session_diary(consolidation_tier=...)` | Filter by tier |

## Schema

### `consolidation_tiers` Table (Migration 06)

```sql
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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%fZ', 'now'))
);

-- Seeded with 4 tiers: daily, short, weekly, bimonthly
```

### `session_diary` Extensions

```sql
ALTER TABLE session_diary ADD COLUMN consolidation_tier TEXT DEFAULT NULL;
ALTER TABLE session_diary ADD COLUMN ttl_phase TEXT DEFAULT 'active';
CREATE INDEX idx_session_diary_tier ON session_diary(consolidation_tier);
```

## Configuration

### config-subsystem.json

```json
{
  "consolidation": {
    "model": "granite-4.1-3b",
    "server_url": "http://127.0.0.1:18095",
    "timeout_seconds": 120,
    "max_retries": 3,
    "fallback_to_main": true,
    "roles": ["memory-consolidation", "session-summarization", "knowledge-extraction"]
  }
}
```

### systemd Service

```
~/.config/systemd/user/arc-summarizer.service
```

- **ExecStart:** `arc_summarizer/start.sh` (sources oneAPI, starts llama-server)
- **Model:** `~/Coding-Projects/chief-s2s/models/granite-4.1-3b-Q4_K_M.gguf`
- **Port:** 18095
- **Memory limit:** 8G
- **Restart:** on-failure, 10s delay

## MemoryService Integration

ArcPipeline and IdleWindowScheduler are wired into `MemoryService` as canonical components:

```python
service = MemoryService.load()
service.pipeline        # ArcPipeline — tiered consolidation
service.scheduler       # IdleWindowScheduler — background scheduling
service.router._consolidation_pipeline  # Lazy-on-recall reference
```

On init: ArcPipeline created from config, wired to ContextRouter for lazy-on-recall. IdleWindowScheduler started as daemon thread. Startup catch-up runs in background thread.

## Consolidation Metrics

`MemoryLayer._get_consolidation_metrics()` queries DB state and returns structured dict:

```python
{
    "tiers": {"daily": {"last_run_at": ..., "overdue": bool, "entries_count": int}, ...},
    "ttl_distribution": {"active": int, "aging": int, "expired": int, "total": int, "expiring_within_24h": int},
    "consolidation_cache": {"total_entries": int, "active": int, "probation": int, "expired": int},
    "injection_blacklist": {"active_patterns": int, "total_patterns": int},
}
```

Wired into `unified_log_recall()` as always-included section (like `service_health`). Fused context includes `## Consolidation Metrics` summary.

Also available via `MemoryService.health_check()` → `arc_server` section.

## Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_tiered_consolidation.py` | 24 | Schema, store methods, prompts, pipeline, client |
| `test_idle_scheduler.py` | 20 | Due detection, CPU gating, cycle logic, lifecycle, catch-up |
| `test_lazy_recall.py` | 12 | Tier mapping, fresh digest, on-demand, fallback, aggregation |
| `test_consolidation_metrics.py` | 17 | Metrics queries, overdue detection, TTL, cache, blacklist, integration |
| **Total** | **93** | All passing |

## What Does NOT Change

- **`consolidation_cache` / `session_diary` separation** — Provenance traceability preserved
- **Arc A380 routing** — Health gate + fallback pattern unchanged
- **Pi extension `message_end` hook** — Mechanical upsert to `session_diary` unchanged
- **Legacy `run_consolidation()`** — Kept for backward compatibility

## File Locations

| Resource | Path |
|----------|------|
| Module source | `~/Coding-Projects/7-council/super_council/arc_summarizer/` |
| Scheduler | `~/Coding-Projects/7-council/super_council/arc_summarizer/scheduler.py` |
| Router | `~/Coding-Projects/7-council/super_council/memory_service/router.py` |
| Store | `~/Coding-Projects/7-council/super_council/memory_service/store.py` |
| MemoryService | `~/Coding-Projects/7-council/super_council/memory_service/__init__.py` |
| Config | `~/Coding-Projects/7-council/super_council/config-subsystem.json` |
| Memory config | `~/Coding-Projects/7-council/super_council/memory-config.json` |
| systemd service | `~/.config/systemd/user/arc-summarizer.service` |
| Start script | `~/Coding-Projects/7-council/super_council/arc_summarizer/start.sh` |
| Model file | `~/Coding-Projects/chief-s2s/models/granite-4.1-3b-Q4_K_M.gguf` |
| Semantic memory | `~/.council-memory/semantic-memory/` |
| Chat summaries | `~/.council-memory/chat-summaries/` |
| Database | `~/.council-memory/pipelines.db` |
| Migrations | `~/Coding-Projects/7-council/migrations/` |
| Tests | `~/Coding-Projects/7-council/super_council/tests/` |
